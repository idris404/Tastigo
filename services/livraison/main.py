"""Service Livraison : acheminement des commandes validées, stocké dans Redis (base logique 3).

Il possède l'agrégat Livraison et un réplica « commande livrable » alimenté par les
événements du service Commande (CommandeValidee, AdresseLivraisonModifiee). Il peut
donc organiser la livraison même si le service Commande est indisponible.
"""

import logging
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from common.bus import (
    ConsommateurBus,
    RejetMetier,
    RelaisOutboxRedis,
    connexion_service,
    derniers_recus,
    etat_evenements,
    marquer_traite,
)
from common.evenements import maintenant, nouvel_evenement, vers_json

SERVICE = "livraison"
log = logging.getLogger(SERVICE)
r = connexion_service()

TRANSITIONS = {"EN_PREPARATION": "EN_ROUTE", "EN_ROUTE": "LIVREE"}
PAR_COMMANDE = "livraisons:par-commande"  # HASH commandeId -> livraisonId (unicité)


def k_replica(cid: str) -> str:
    return f"replica:commande:{cid}"  # HASH : réplica de la commande livrable


def k_livraison(lid: str) -> str:
    return f"livraison:{lid}"  # HASH : racine de l'agrégat Livraison


def k_historique(lid: str) -> str:
    return f"livraison:{lid}:historique"  # LIST : transitions de statut


def k_statut(statut: str) -> str:
    return f"livraisons:statut:{statut}"  # SET : index par statut


class Livreur(BaseModel):
    livreurId: str = Field(pattern=r"^livreur_")
    nom: str = Field(min_length=1)


class NouveauStatut(BaseModel):
    statut: Literal["EN_ROUTE", "LIVREE"]


# --------------------------------------------------------------------------- lecture
def _adresse(h: dict, prefixe: str) -> dict:
    return {k: h[f"{prefixe}.adresse.{k}"] for k in ("ligne1", "codePostal", "ville")}


def lire_replica(cid: str, source=r) -> dict | None:
    h = source.hgetall(k_replica(cid))
    if not h:
        return None
    return {
        "commandeId": cid,
        "nombreArticles": int(h["nombreArticles"]),
        "total": {"montant": int(h["totalMontant"]), "devise": h["totalDevise"]},
        "collecte": {
            "restaurantId": h["collecte.restaurantId"],
            "nom": h["collecte.nom"],
            "telephone": h["collecte.telephone"] or None,
            "adresse": _adresse(h, "collecte"),
        },
        "destination": {
            "clientId": h["destination.clientId"],
            "nom": h["destination.nom"],
            "telephone": h["destination.telephone"],
            "adresse": _adresse(h, "destination"),
        },
        "sourceVersion": int(h["sourceVersion"]),
        "misAJourLe": h["misAJourLe"],
    }


def lire_livraison(lid: str, source=r) -> dict | None:
    h = source.hgetall(k_livraison(lid))
    if not h:
        return None
    replica = lire_replica(h["commandeId"], source) or {}
    historique = [entree.split("|", 1) for entree in source.lrange(k_historique(lid), 0, -1)]
    return {
        "livraisonId": lid,
        "commandeId": h["commandeId"],
        "statut": h["statut"],
        "livreur": {"livreurId": h["livreur.livreurId"], "nom": h["livreur.nom"]} if "livreur.livreurId" in h else None,
        "collecte": replica.get("collecte"),
        "destination": replica.get("destination"),
        "creeLe": h["creeLe"],
        "departLe": h.get("departLe"),
        "livreeLe": h.get("livreeLe"),
        "historique": [{"statut": s, "date": d} for s, d in historique],
        "version": int(h["version"]),
    }


def obtenir(lid: str) -> dict:
    livraison = lire_livraison(lid)
    if livraison is None:
        raise HTTPException(404, f"livraison {lid} introuvable")
    return livraison


# --------------------------------------------------------------------------- commandes
def modifier(lid: str, decider) -> dict:
    """Même principe que Commande : WATCH sur la racine, règles, puis MULTI / EXEC."""

    def transaction(pipe):
        livraison = lire_livraison(lid, pipe)
        if livraison is None:
            raise HTTPException(404, f"livraison {lid} introuvable")
        ecrire = decider(livraison)
        version = livraison["version"] + 1
        pipe.multi()
        pipe.hset(k_livraison(lid), "version", version)
        ecrire(pipe, version)

    r.transaction(transaction, k_livraison(lid))
    return obtenir(lid)


def affecter_livreur(lid: str, livreur: Livreur) -> dict:
    def decider(livraison):
        if livraison["statut"] != "EN_PREPARATION":
            raise HTTPException(409, "un livreur ne peut être affecté qu'à une livraison EN_PREPARATION")

        def ecrire(p, _version):
            p.hset(k_livraison(lid), mapping={"livreur.livreurId": livreur.livreurId, "livreur.nom": livreur.nom})

        return ecrire

    return modifier(lid, decider)


def _evenements_statut(livraison: dict, version: int, ancien: str, nouveau: str, date: str) -> list[dict]:
    cid = livraison["commandeId"]
    commun = dict(
        event_type="StatutLivraisonModifie",
        emetteur=SERVICE,
        aggregate_id=livraison["livraisonId"],
        aggregate_version=version,
        operation="METTRE_A_JOUR",
        cible={"commandeId": cid, "livraisonId": livraison["livraisonId"]},
        ancienne=ancien,
        nouvelle=nouveau,
        correlation_id=f"corr_{cid}",
        occurred_at=date,
    )
    return [
        nouvel_evenement(recepteur="suivi", donnee=f"suivis[{cid}].statutLivraison", **commun),
        nouvel_evenement(recepteur="commande", donnee=f"etatLivraison[{cid}].statut", **commun),
    ]


def changer_statut(lid: str, nouveau: str) -> dict:
    def decider(livraison):
        ancien = livraison["statut"]
        if TRANSITIONS.get(ancien) != nouveau:
            raise HTTPException(409, f"transition interdite : {ancien} -> {nouveau}")
        if nouveau == "EN_ROUTE" and livraison["livreur"] is None:
            raise HTTPException(409, "le passage à EN_ROUTE exige un livreur affecté")
        date = maintenant()

        def ecrire(p, version):
            horodatage = {"departLe": date} if nouveau == "EN_ROUTE" else {"livreeLe": date}
            p.hset(k_livraison(lid), mapping={"statut": nouveau, **horodatage})
            p.smove(k_statut(ancien), k_statut(nouveau), lid)
            p.rpush(k_historique(lid), f"{nouveau}|{date}")
            for evenement in _evenements_statut(livraison, version, ancien, nouveau, date):
                p.xadd("outbox", {"event": vers_json(evenement)})

        return ecrire

    return modifier(lid, decider)


# --------------------------------------------------------------------------- consommation des événements
def _version_source(cid: str) -> int:
    valeur = r.hget(k_replica(cid), "sourceVersion")
    return int(valeur) if valeur else 0


def sur_commande_validee(evt: dict) -> str:
    cid, version = evt["aggregateId"], evt["aggregateVersion"]
    if r.hexists(PAR_COMMANDE, cid):
        return "ignoré (une livraison existe déjà pour cette commande)"
    snapshot = evt["modification"]["nouvelleValeur"]
    client, restaurant = snapshot["client"], snapshot["restaurant"]
    lid = f"liv_{r.incr('compteur:livraison')}"
    cree_le = maintenant()
    pipe = r.pipeline()
    # 1. création du réplica de la commande
    pipe.hset(
        k_replica(cid),
        mapping={
            "commandeId": cid,
            "nombreArticles": snapshot["nombreArticles"],
            "totalMontant": snapshot["total"]["montant"],
            "totalDevise": snapshot["total"]["devise"],
            "collecte.restaurantId": restaurant["restaurantId"],
            "collecte.nom": restaurant["nom"],
            "collecte.telephone": restaurant.get("telephone") or "",
            **{f"collecte.adresse.{k}": v for k, v in restaurant["adresse"].items()},
            "destination.clientId": client["clientId"],
            "destination.nom": client["nom"],
            "destination.telephone": client["telephone"],
            **{f"destination.adresse.{k}": v for k, v in client["adresseLivraison"].items()},
            "sourceVersion": version,
            "misAJourLe": evt["occurredAt"],
        },
    )
    # 2. création de l'agrégat Livraison (une seule par commande)
    pipe.hset(
        k_livraison(lid),
        mapping={"livraisonId": lid, "commandeId": cid, "statut": "EN_PREPARATION", "version": 1, "creeLe": cree_le},
    )
    pipe.hset(PAR_COMMANDE, cid, lid)
    pipe.sadd(k_statut("EN_PREPARATION"), lid)
    pipe.rpush(k_historique(lid), f"EN_PREPARATION|{cree_le}")
    # 3. événements vers Suivi et Commande, dans l'outbox locale
    nouvelle = {"livraisonId": lid, "statut": "EN_PREPARATION", "date": cree_le}
    for recepteur, donnee, operation in (
        ("suivi", f"suivis[{cid}].livraison", "METTRE_A_JOUR"),
        ("commande", f"etatLivraison[{cid}]", "CREER"),
    ):
        evenement = nouvel_evenement(
            event_type="LivraisonCreee",
            emetteur=SERVICE,
            recepteur=recepteur,
            aggregate_id=lid,
            aggregate_version=1,
            operation=operation,
            donnee=donnee,
            cible={"commandeId": cid, "livraisonId": lid},
            ancienne=None,
            nouvelle=nouvelle,
            correlation_id=evt["correlationId"],
            occurred_at=cree_le,
        )
        pipe.xadd("outbox", {"event": vers_json(evenement)})
    marquer_traite(pipe, evt)
    pipe.execute()
    return f"réplica commande et livraison {lid} créés"


def sur_adresse_modifiee(evt: dict) -> str:
    cid, version = evt["aggregateId"], evt["aggregateVersion"]
    applique = _version_source(cid)
    if applique == 0:
        raise RejetMetier(f"commande {cid} absente du réplica")
    if version <= applique:
        return "ignoré (version déjà appliquée)"
    lid = r.hget(PAR_COMMANDE, cid)
    statut = r.hget(k_livraison(lid), "statut")
    if statut in ("EN_ROUTE", "LIVREE"):
        raise RejetMetier(f"livraison {lid} déjà {statut}")
    adresse = evt["modification"]["nouvelleValeur"]
    pipe = r.pipeline()
    pipe.hset(
        k_replica(cid),
        mapping={
            **{f"destination.adresse.{k}": v for k, v in adresse.items()},
            "sourceVersion": version,
            "misAJourLe": evt["occurredAt"],
        },
    )
    marquer_traite(pipe, evt)
    pipe.execute()
    return "réplica commande mis à jour (adresse)"


GESTIONNAIRES = {
    "CommandeValidee": sur_commande_validee,
    "AdresseLivraisonModifiee": sur_adresse_modifiee,
}


def traiter(evt: dict) -> str:
    gestionnaire = GESTIONNAIRES.get(evt["eventType"])
    if gestionnaire is None:
        raise RejetMetier(f"type d'événement non géré : {evt['eventType']}")
    return gestionnaire(evt)


# --------------------------------------------------------------------------- application
@asynccontextmanager
async def lifespan(_app: FastAPI):
    r.set("compteur:livraison", 500, nx=True)
    ConsommateurBus(SERVICE, r, traiter).start()
    RelaisOutboxRedis(SERVICE, r).start()
    yield


app = FastAPI(title="Tastigo - service Livraison", lifespan=lifespan)


@app.get("/sante")
def sante():
    r.ping()
    return {"service": SERVICE, "base": "Redis DB 3", "statut": "ok"}


@app.get("/livraisons")
def lister(statut: Literal["EN_PREPARATION", "EN_ROUTE", "LIVREE"] = "EN_PREPARATION"):
    return [lire_livraison(lid) for lid in sorted(r.smembers(k_statut(statut)))]


@app.get("/livraisons/{livraison_id}")
def lire(livraison_id: str):
    return obtenir(livraison_id)


@app.get("/commandes/{commande_id}/livraison")
def livraison_de_commande(commande_id: str):
    lid = r.hget(PAR_COMMANDE, commande_id)
    if lid is None:
        raise HTTPException(404, f"aucune livraison pour {commande_id}")
    return obtenir(lid)


@app.get("/replicas/commandes/{commande_id}")
def replica(commande_id: str):
    donnees = lire_replica(commande_id)
    if donnees is None:
        raise HTTPException(404, f"commande {commande_id} absente du réplica")
    return donnees


@app.post("/livraisons/{livraison_id}/livreur")
def livreur(livraison_id: str, entree: Livreur):
    return affecter_livreur(livraison_id, entree)


@app.put("/livraisons/{livraison_id}/statut")
def statut(livraison_id: str, entree: NouveauStatut):
    return changer_statut(livraison_id, entree.statut)


@app.get("/evenements")
def evenements():
    return etat_evenements(r)


@app.get("/evenements/recus")
def evenements_recus(limite: int = 20):
    return derniers_recus(SERVICE, min(limite, 200))
