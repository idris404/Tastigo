"""Service Suivi : projection de lecture « où en est ma commande ? » (Redis, base logique 4).

La projection SuiviCommande n'est modifiée que par des événements (CommandeValidee,
LivraisonCreee, StatutLivraisonModifie). Elle transforme les données reçues (libellé
client, nombre d'articles, chronologie) et peut être supprimée puis reconstruite en
rejouant la boîte de réception du service sur le bus.
"""

import json
import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from common.bus import (
    REJETES,
    TRAITES,
    ConsommateurBus,
    RejetMetier,
    connexion_bus,
    connexion_service,
    derniers_recus,
    deja_traite,
    etat_evenements,
    marquer_traite,
)
from common.evenements import en_millis, flux_vers, maintenant

SERVICE = "suivi"
log = logging.getLogger(SERVICE)
r = connexion_service()
verrou = threading.Lock()  # sérialise consommation et reconstruction

LIBELLES = {
    "COMMANDE_VALIDEE": "Commande validée, en attente de prise en charge",
    "EN_PREPARATION": "Votre commande est en préparation",
    "EN_ROUTE": "Votre commande est en route",
    "LIVREE": "Commande livrée",
}


def k_suivi(cid: str) -> str:
    return f"suivi:{cid}"  # HASH : projection


def k_chronologie(cid: str) -> str:
    return f"suivi:{cid}:chronologie"  # ZSET : étapes triées par date (score en ms)


def k_client(client_id: str) -> str:
    return f"suivis:client:{client_id}"  # ZSET : commandes d'un client par date


def _derniere_mise_a_jour(pipe, actuel: dict, cid: str, date: str) -> None:
    if date > actuel.get("derniereMiseAJour", ""):
        pipe.hset(k_suivi(cid), "derniereMiseAJour", date)


# --------------------------------------------------------------------------- transformations
def sur_commande_validee(evt: dict) -> str:
    cid = evt["modification"]["cible"]["commandeId"]
    valeur, date = evt["modification"]["nouvelleValeur"], evt["occurredAt"]
    actuel = r.hgetall(k_suivi(cid))
    pipe = r.pipeline()
    pipe.hset(
        k_suivi(cid),
        mapping={
            "commandeId": cid,
            "clientId": valeur["clientId"],
            "nomRestaurant": valeur["restaurant"]["nom"],  # seul le nom est conservé
            "nombreArticles": valeur["nombreArticles"],
            "totalMontant": valeur["total"]["montant"],
            "totalDevise": valeur["total"]["devise"],
        },
    )
    if "statutTechnique" not in actuel:  # LivraisonCreee a pu arriver avant
        pipe.hset(k_suivi(cid), mapping={"statutTechnique": "COMMANDE_VALIDEE", "statutAffiche": LIBELLES["COMMANDE_VALIDEE"]})
    pipe.zadd(k_chronologie(cid), {f"COMMANDE_VALIDEE|{date}": en_millis(date)})
    pipe.zadd(k_client(valeur["clientId"]), {cid: en_millis(date)})
    _derniere_mise_a_jour(pipe, actuel, cid, date)
    marquer_traite(pipe, evt)
    pipe.execute()
    return "projection créée"


def sur_evenement_livraison(evt: dict) -> str:
    cible, version, date = evt["modification"]["cible"], evt["aggregateVersion"], evt["occurredAt"]
    cid = cible["commandeId"]
    valeur = evt["modification"]["nouvelleValeur"]
    statut = valeur["statut"] if isinstance(valeur, dict) else valeur
    actuel = r.hgetall(k_suivi(cid))
    pipe = r.pipeline()
    pipe.hset(k_suivi(cid), mapping={"commandeId": cid, "livraisonId": cible["livraisonId"]})
    applique = version > int(actuel.get("versionLivraison", 0))
    if applique:  # un ancien événement ne remplace pas un statut plus récent
        pipe.hset(
            k_suivi(cid),
            mapping={"statutTechnique": statut, "statutAffiche": LIBELLES[statut], "versionLivraison": version},
        )
    pipe.zadd(k_chronologie(cid), {f"{statut}|{date}": en_millis(date)})
    _derniere_mise_a_jour(pipe, actuel, cid, date)
    marquer_traite(pipe, evt)
    pipe.execute()
    return f"projection mise à jour ({statut})" if applique else "chronologie complétée (statut plus récent conservé)"


GESTIONNAIRES = {
    "CommandeValidee": sur_commande_validee,
    "LivraisonCreee": sur_evenement_livraison,
    "StatutLivraisonModifie": sur_evenement_livraison,
}


def traiter(evt: dict) -> str:
    gestionnaire = GESTIONNAIRES.get(evt["eventType"])
    if gestionnaire is None:
        raise RejetMetier(f"type d'événement non géré : {evt['eventType']}")
    with verrou:
        return gestionnaire(evt)


# --------------------------------------------------------------------------- lecture
def lire_suivi(cid: str) -> dict | None:
    h = r.hgetall(k_suivi(cid))
    if not h:
        return None
    chronologie = [m.split("|", 1) for m in r.zrange(k_chronologie(cid), 0, -1)]
    return {
        "commandeId": cid,
        "clientId": h.get("clientId"),
        "livraisonId": h.get("livraisonId"),
        "restaurant": {"nom": h.get("nomRestaurant")},
        "resume": {
            "nombreArticles": int(h["nombreArticles"]) if "nombreArticles" in h else None,
            "total": {"montant": int(h["totalMontant"]), "devise": h["totalDevise"]} if "totalMontant" in h else None,
        },
        "statutTechnique": h.get("statutTechnique"),
        "statutAffiche": h.get("statutAffiche"),
        "derniereMiseAJour": h.get("derniereMiseAJour"),
        "chronologie": [{"statut": s, "date": d} for s, d in chronologie],
    }


def reconstruire() -> dict:
    """Supprime la projection puis rejoue tous les événements reçus sur le bus."""
    bus = connexion_bus()
    with verrou:
        cles = list(r.scan_iter("suivi:*")) + list(r.scan_iter("suivis:*")) + [TRAITES, REJETES]
        r.delete(*cles)
        rejoues = 0
        for _id, champs in bus.xrange(flux_vers(SERVICE), "-", "+"):
            evt = json.loads(champs["event"])
            if deja_traite(r, evt):
                continue  # doublon présent sur le bus
            gestionnaire = GESTIONNAIRES.get(evt["eventType"])
            if gestionnaire is None:
                continue
            gestionnaire(evt)
            r.sadd(TRAITES, evt["eventId"])
            rejoues += 1
    projections = sum(1 for cle in r.scan_iter("suivi:*") if not cle.endswith(":chronologie"))
    log.info("projection reconstruite : %d événements rejoués, %d suivis", rejoues, projections)
    return {"evenementsRejoues": rejoues, "projections": projections, "reconstruiteLe": maintenant()}


# --------------------------------------------------------------------------- application
@asynccontextmanager
async def lifespan(_app: FastAPI):
    ConsommateurBus(SERVICE, r, traiter).start()
    yield


app = FastAPI(title="Tastigo - service Suivi", lifespan=lifespan)


@app.get("/sante")
def sante():
    r.ping()
    return {"service": SERVICE, "base": "Redis DB 4", "statut": "ok"}


@app.get("/suivis/{commande_id}")
def suivi(commande_id: str):
    projection = lire_suivi(commande_id)
    if projection is None:
        raise HTTPException(404, f"aucun suivi pour {commande_id}")
    return projection


@app.get("/clients/{client_id}/suivis")
def suivis_client(client_id: str):
    return [lire_suivi(cid) for cid in r.zrevrange(k_client(client_id), 0, -1)]


@app.post("/admin/reconstruire")
def admin_reconstruire():
    return reconstruire()


@app.get("/evenements")
def evenements():
    return etat_evenements(r)


@app.get("/evenements/recus")
def evenements_recus(limite: int = 20):
    return derniers_recus(SERVICE, min(limite, 200))
