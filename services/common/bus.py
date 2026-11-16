"""Bus d'événements Tastigo basé sur Redis Streams.

Chaque service possède une boîte de réception ``evenements:vers:<service>`` sur le bus.
Un producteur n'écrit jamais directement sur le bus pendant une commande : il écrit
l'événement dans sa propre base (outbox) dans la même transaction que l'agrégat, puis
un relais recopie l'outbox vers le bus. Le consommateur lit sa boîte avec un groupe de
consommateurs (XREADGROUP) et n'acquitte (XACK) qu'après avoir appliqué l'événement :
la livraison est donc « au moins une fois », et l'idempotence est assurée par le SET
``evenements:traites`` de la base du récepteur.
"""

import json
import logging
import os
import threading
import time
from typing import Callable

import redis

from .evenements import flux_vers, maintenant

log = logging.getLogger("bus")

TRAITES = "evenements:traites"
REJETES = "evenements:rejetes"
MAX_TENTATIVES = 5


def connexion_bus() -> redis.Redis:
    return redis.Redis.from_url(os.environ.get("BUS_URL", "redis://bus:6379/0"), decode_responses=True)


class RejetMetier(Exception):
    """Événement techniquement valide mais refusé par une règle métier du récepteur.

    Il est acquitté (ne sera pas rejoué) et tracé dans ``evenements:rejetes``.
    """


def connexion_service() -> redis.Redis:
    """Connexion à la base logique Redis propre au service (REDIS_URL se termine par /<db>)."""
    return redis.Redis.from_url(os.environ["REDIS_URL"], decode_responses=True)


def etat_evenements(db: redis.Redis) -> dict:
    """Résumé des événements traités, rejetés et en outbox, pour l'observation."""
    return {
        "traites": db.scard(TRAITES),
        "rejetes": [json.loads(x) for x in db.lrange(REJETES, 0, -1)],
        "outbox": db.xlen("outbox"),
        "dernierRelaye": db.get("outbox:curseur"),
    }


def deja_traite(db: redis.Redis, evenement: dict) -> bool:
    return bool(db.sismember(TRAITES, evenement["eventId"]))


def marquer_traite(pipe, evenement: dict) -> None:
    pipe.sadd(TRAITES, evenement["eventId"])


class ConsommateurBus(threading.Thread):
    """Lit la boîte de réception d'un service et applique chaque événement."""

    def __init__(self, service: str, db: redis.Redis, traiter: Callable[[dict], str]):
        super().__init__(daemon=True, name=f"consommateur-{service}")
        self.service = service
        self.flux = flux_vers(service)
        self.groupe = service
        self.consommateur = f"{service}-1"
        self.bus = connexion_bus()
        self.db = db
        self.traiter = traiter
        self.tentatives: dict[str, int] = {}

    def _creer_groupe(self) -> None:
        try:
            # id "0" : un groupe créé tardivement reçoit aussi les événements déjà publiés.
            self.bus.xgroup_create(self.flux, self.groupe, id="0", mkstream=True)
            log.info("groupe %s créé sur %s", self.groupe, self.flux)
        except redis.ResponseError as erreur:
            if "BUSYGROUP" not in str(erreur):
                raise

    def run(self) -> None:
        while True:
            try:
                self._creer_groupe()
                break
            except redis.ConnectionError:
                log.warning("bus indisponible, nouvelle tentative")
                time.sleep(1)
        while True:
            try:
                # 1) messages déjà délivrés mais non acquittés (reprise après une panne)
                lus = self.bus.xreadgroup(self.groupe, self.consommateur, {self.flux: "0"}, count=20)
                if not lus or not lus[0][1]:
                    # 2) nouveaux messages, attente bloquante de 2 s au maximum
                    lus = self.bus.xreadgroup(
                        self.groupe, self.consommateur, {self.flux: ">"}, count=20, block=2000
                    )
                for _flux, entrees in lus or []:
                    for message_id, champs in entrees:
                        if not self._traiter_message(message_id, champs):
                            time.sleep(1)
                            break
            except redis.ConnectionError:
                log.warning("connexion perdue, nouvelle tentative")
                time.sleep(1)
            except Exception:  # pragma: no cover - filet de sécurité du thread
                log.exception("erreur inattendue du consommateur")
                time.sleep(1)

    def _acquitter(self, message_id: str) -> None:
        self.bus.xack(self.flux, self.groupe, message_id)
        self.tentatives.pop(message_id, None)

    def _traiter_message(self, message_id: str, champs: dict | None) -> bool:
        if not champs or "event" not in champs:
            self._acquitter(message_id)
            return True
        evenement = json.loads(champs["event"])
        description = f"{evenement['eventType']} {evenement['eventId']} ({evenement['emetteur']} -> {self.service})"
        if deja_traite(self.db, evenement):
            log.info("doublon ignoré : %s", description)
            self._acquitter(message_id)
            return True
        try:
            resultat = self.traiter(evenement)
            self.db.sadd(TRAITES, evenement["eventId"])
            log.info("%s : %s", resultat, description)
        except RejetMetier as raison:
            self._rejeter(evenement, str(raison))
            log.warning("rejeté (%s) : %s", raison, description)
        except Exception:
            essais = self.tentatives.get(message_id, 0) + 1
            self.tentatives[message_id] = essais
            log.exception("échec %d/%d : %s", essais, MAX_TENTATIVES, description)
            if essais < MAX_TENTATIVES:
                return False
            self._rejeter(evenement, "échec technique répété")
        self._acquitter(message_id)
        return True

    def _rejeter(self, evenement: dict, raison: str) -> None:
        pipe = self.db.pipeline()
        pipe.rpush(REJETES, json.dumps({"raison": raison, "rejeteLe": maintenant(), "evenement": evenement}))
        marquer_traite(pipe, evenement)
        pipe.execute()


class RelaisOutboxRedis(threading.Thread):
    """Recopie l'outbox locale (STREAM ``outbox`` de la base du service) vers le bus.

    La position du dernier événement relayé est mémorisée dans ``outbox:curseur``.
    Une panne entre XADD et SET peut produire un doublon : le récepteur l'ignore.
    """

    def __init__(self, service: str, db: redis.Redis):
        super().__init__(daemon=True, name=f"relais-{service}")
        self.service = service
        self.db = db
        self.bus = connexion_bus()

    def run(self) -> None:
        while True:
            try:
                curseur = self.db.get("outbox:curseur") or "0-0"
                lus = self.db.xread({"outbox": curseur}, count=50, block=1000)
                for _flux, entrees in lus or []:
                    for message_id, champs in entrees:
                        evenement = json.loads(champs["event"])
                        self.bus.xadd(
                            flux_vers(evenement["recepteur"]),
                            {"event": champs["event"], "eventType": evenement["eventType"]},
                        )
                        self.db.set("outbox:curseur", message_id)
                        log.info(
                            "publié %s %s -> %s",
                            evenement["eventType"],
                            evenement["eventId"],
                            evenement["recepteur"],
                        )
            except redis.ConnectionError:
                log.warning("relais : connexion perdue, nouvelle tentative")
                time.sleep(1)
            except Exception:  # pragma: no cover
                log.exception("relais : erreur inattendue")
                time.sleep(1)
