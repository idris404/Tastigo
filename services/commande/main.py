"""Service Commande : paniers et commandes stockés dans Redis (base logique 2).

Il possède l'agrégat Commande et deux réplicas alimentés par événements :
- le catalogue minimal des restaurants (émis par Restaurant) ;
- l'état des livraisons (émis par Livraison), pour refuser un changement d'adresse
  lorsque le livreur est déjà parti.
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
    etat_evenements,
    marquer_traite,
)
from common.evenements import en_millis, maintenant, nouvel_evenement, vers_json

SERVICE = "commande"
log = logging.getLogger(SERVICE)
r = connexion_service()


# --------------------------------------------------------------------------- clés Redis
def k_restaurant(rid: str) -> str:
    return f"catalogue:restaurant:{rid}"  # HASH : réplica d'un restaurant


def k_plats(rid: str) -> str:
    return f"catalogue:restaurant:{rid}:plats"  # SET : identifiants des plats


def k_plat(rid: str, pid: str) -> str:
    return f"catalogue:plat:{rid}:{pid}"  # HASH : réplica d'un plat


def k_commande(cid: str) -> str:
    return f"commande:{cid}"  # HASH : racine de l'agrégat


def k_lignes(cid: str) -> str:
    return f"commande:{cid}:lignes"  # LIST : ordre des lignes


def k_ligne(cid: str, lid: str) -> str:
    return f"commande:{cid}:ligne:{lid}"  # HASH : ligne avec nom et prix figés


def k_livraison(cid: str) -> str:
    return f"replica:livraison:{cid}"  # HASH : réplica de l'état de livraison


# --------------------------------------------------------------------------- modèles d'entrée
class Adresse(BaseModel):
    ligne1: str = Field(min_length=1)
    codePostal: str = Field(pattern=r"^[0-9]{5}$")
    ville: str = Field(min_length=1)


class Client(BaseModel):
    clientId: str = Field(pattern=r"^cli_")
    nom: str = Field(min_length=1)
    telephone: str
    adresseLivraison: Adresse


class NouvelleCommande(BaseModel):
    client: Client
    restaurantId: str


class NouvelleLigne(BaseModel):
    platId: str
    quantite: int = Field(ge=1, le=50)


# --------------------------------------------------------------------------- lecture
def _cle_numerique(identifiant: str) -> int:
    return int(identifiant.rsplit("_", 1)[-1])


def lire_restaurant_replica(rid: str, source=r) -> dict | None:
    h = source.hgetall(k_restaurant(rid))
    if not h:
        return None
    plats = []
    for pid in sorted(source.smembers(k_plats(rid)), key=_cle_numerique):
        p = source.hgetall(k_plat(rid, pid))
        plats.append(
            {
                "platId": pid,
                "nom": p["nom"],
                "prix": {"montant": int(p["prixMontant"]), "devise": p["prixDevise"]},
                "disponible": p["disponible"] == "true",
            }
        )
    return {
        "restaurantId": rid,
        "nom": h["nom"],
        "telephone": h.get("telephone") or None,
        "adresse": {"ligne1": h["adresse.ligne1"], "codePostal": h["adresse.codePostal"], "ville": h["adresse.ville"]},
        "statut": h["statut"],
        "plats": plats,
        "sourceVersion": int(h["sourceVersion"]),
        "misAJourLe": h.get("misAJourLe"),
    }


def lire_commande(cid: str, source=r) -> dict | None:
    h = source.hgetall(k_commande(cid))
    if not h:
        return None
    lignes = []
    for lid in source.lrange(k_lignes(cid), 0, -1):
        ligne = source.hgetall(k_ligne(cid, lid))
        lignes.append(
            {
                "ligneId": lid,
                "platId": ligne["platId"],
                "nomPlat": ligne["nomPlat"],
                "prixUnitaire": {"montant": int(ligne["prixUnitaireMontant"]), "devise": ligne["prixUnitaireDevise"]},
                "quantite": int(ligne["quantite"]),
            }
        )
    return {
        "commandeId": cid,
        "client": {
            "clientId": h["client.clientId"],
            "nom": h["client.nom"],
            "telephone": h["client.telephone"],
            "adresseLivraison": {
                "ligne1": h["adresseLivraison.ligne1"],
                "codePostal": h["adresseLivraison.codePostal"],
                "ville": h["adresseLivraison.ville"],
            },
        },
        "restaurantId": h["restaurantId"],
        "lignes": lignes,
        "total": {"montant": int(h["totalMontant"]), "devise": h["totalDevise"]},
        "statut": h["statut"],
        "creeLe": h["creeLe"],
        "valideeLe": h.get("valideeLe"),
        "version": int(h["version"]),
    }


def obtenir_commande(cid: str) -> dict:
    commande = lire_commande(cid)
    if commande is None:
        raise HTTPException(404, f"commande {cid} introuvable")
    replica = r.hgetall(k_livraison(cid))
    commande["replicaLivraison"] = (
        {"livraisonId": replica["livraisonId"], "statut": replica["statut"], "sourceVersion": int(replica["sourceVersion"])}
        if replica
        else None
    )
    return commande


def calculer_total(lignes: list[dict]) -> int:
    return sum(l["prixUnitaire"]["montant"] * l["quantite"] for l in lignes)


# --------------------------------------------------------------------------- commandes
def modifier(cid: str, decider) -> dict:
    """Modifie une commande avec un verrou optimiste Redis (WATCH / MULTI / EXEC).

    ``decider(pipe, commande)`` lit et vérifie les règles, puis renvoie une fonction
    ``ecrire(pipe, nouvelle_version)`` qui met en file les écritures de la transaction.
    Si la commande est modifiée par ailleurs entre WATCH et EXEC, redis-py rejoue tout.
    """

    def transaction(pipe):
        commande = lire_commande(cid, pipe)
        if commande is None:
            raise HTTPException(404, f"commande {cid} introuvable")
        ecrire = decider(pipe, commande)
        version = commande["version"] + 1
        pipe.multi()
        pipe.hset(k_commande(cid), "version", version)
        ecrire(pipe, version)

    r.transaction(transaction, k_commande(cid))
    return obtenir_commande(cid)


def creer_commande(entree: NouvelleCommande) -> dict:
    restaurant = lire_restaurant_replica(entree.restaurantId)
    if restaurant is None:
        raise HTTPException(404, f"restaurant {entree.restaurantId} absent du catalogue local (non publié ?)")
    if restaurant["statut"] != "PUBLIE":
        raise HTTPException(409, f"restaurant {restaurant['nom']} {restaurant['statut']}")
    cid = f"cmd_{r.incr('compteur:commande')}"
    cree_le = maintenant()
    client = entree.client
    pipe = r.pipeline()  # MULTI / EXEC
    pipe.hset(
        k_commande(cid),
        mapping={
            "commandeId": cid,
            "restaurantId": entree.restaurantId,
            "statut": "BROUILLON",
            "totalMontant": 0,
            "totalDevise": "EUR",
            "version": 1,
            "creeLe": cree_le,
            "prochaineLigne": 1,
            "client.clientId": client.clientId,
            "client.nom": client.nom,
            "client.telephone": client.telephone,
            "adresseLivraison.ligne1": client.adresseLivraison.ligne1,
            "adresseLivraison.codePostal": client.adresseLivraison.codePostal,
            "adresseLivraison.ville": client.adresseLivraison.ville,
        },
    )
    pipe.zadd(f"commandes:client:{client.clientId}", {cid: en_millis(cree_le)})
    pipe.sadd("commandes:statut:BROUILLON", cid)
    pipe.execute()
    return obtenir_commande(cid)


def ajouter_ligne(cid: str, entree: NouvelleLigne) -> dict:
    def decider(pipe, commande):
        if commande["statut"] != "BROUILLON":
            raise HTTPException(409, "seule une commande BROUILLON peut être modifiée")
        rid = commande["restaurantId"]
        if pipe.hget(k_restaurant(rid), "statut") != "PUBLIE":
            raise HTTPException(409, "le restaurant n'accepte plus de commandes")
        plat = pipe.hgetall(k_plat(rid, entree.platId))
        if not plat:
            raise HTTPException(404, f"plat {entree.platId} absent du catalogue local de {rid}")
        if plat["disponible"] != "true":
            raise HTTPException(409, f"{plat['nom']} est indisponible")
        numero = int(pipe.hget(k_commande(cid), "prochaineLigne"))
        lid = f"ligne_{numero}"
        ligne = {
            "ligneId": lid,
            "platId": entree.platId,
            "nomPlat": plat["nom"],  # snapshot : figé au moment de l'ajout
            "prixUnitaire": {"montant": int(plat["prixMontant"]), "devise": plat["prixDevise"]},
            "quantite": entree.quantite,
        }
        total = calculer_total(commande["lignes"] + [ligne])

        def ecrire(p, _version):
            p.hset(
                k_ligne(cid, lid),
                mapping={
                    "ligneId": lid,
                    "platId": entree.platId,
                    "nomPlat": ligne["nomPlat"],
                    "prixUnitaireMontant": ligne["prixUnitaire"]["montant"],
                    "prixUnitaireDevise": ligne["prixUnitaire"]["devise"],
                    "quantite": entree.quantite,
                },
            )
            p.rpush(k_lignes(cid), lid)
            p.hset(k_commande(cid), mapping={"totalMontant": total, "prochaineLigne": numero + 1})

        return ecrire

    return modifier(cid, decider)


def retirer_ligne(cid: str, lid: str) -> dict:
    def decider(_pipe, commande):
        if commande["statut"] != "BROUILLON":
            raise HTTPException(409, "seule une commande BROUILLON peut être modifiée")
        restantes = [l for l in commande["lignes"] if l["ligneId"] != lid]
        if len(restantes) == len(commande["lignes"]):
            raise HTTPException(404, f"ligne {lid} introuvable")

        def ecrire(p, _version):
            p.lrem(k_lignes(cid), 0, lid)
            p.delete(k_ligne(cid, lid))
            p.hset(k_commande(cid), "totalMontant", calculer_total(restantes))

        return ecrire

    return modifier(cid, decider)


def valider_commande(cid: str) -> dict:
    def decider(pipe, commande):
        if commande["statut"] != "BROUILLON":
            raise HTTPException(409, f"commande déjà {commande['statut']}")
        if not commande["lignes"]:
            raise HTTPException(422, "une commande doit contenir au moins une ligne")
        restaurant = lire_restaurant_replica(commande["restaurantId"], pipe)
        if restaurant is None or restaurant["statut"] != "PUBLIE":
            raise HTTPException(409, "le restaurant n'accepte plus de commandes")
        disponibles = {p["platId"] for p in restaurant["plats"] if p["disponible"]}
        for ligne in commande["lignes"]:
            if ligne["platId"] not in disponibles:
                raise HTTPException(409, f"{ligne['nomPlat']} n'est plus disponible")
        total = {"montant": calculer_total(commande["lignes"]), "devise": "EUR"}
        articles = sum(l["quantite"] for l in commande["lignes"])
        validee_le = maintenant()

        def ecrire(p, version):
            p.hset(k_commande(cid), mapping={"statut": "VALIDEE", "valideeLe": validee_le, "totalMontant": total["montant"]})
            p.smove("commandes:statut:BROUILLON", "commandes:statut:VALIDEE", cid)
            commun = dict(
                event_type="CommandeValidee",
                emetteur=SERVICE,
                aggregate_id=cid,
                aggregate_version=version,
                operation="CREER",
                ancienne=None,
                cible={"commandeId": cid},
                correlation_id=f"corr_{cid}",
                occurred_at=validee_le,
            )
            vers_livraison = nouvel_evenement(
                recepteur="livraison",
                donnee=f"commandeLivrable[{cid}]",
                nouvelle={
                    "commandeId": cid,
                    "client": commande["client"],
                    "restaurant": {k: restaurant[k] for k in ("restaurantId", "nom", "telephone", "adresse")},
                    "nombreArticles": articles,
                    "total": total,
                },
                **commun,
            )
            vers_suivi = nouvel_evenement(
                recepteur="suivi",
                donnee=f"suivis[{cid}]",
                nouvelle={
                    "commandeId": cid,
                    "clientId": commande["client"]["clientId"],
                    "restaurant": {"nom": restaurant["nom"]},
                    "nombreArticles": articles,
                    "total": total,
                    "statut": "COMMANDE_VALIDEE",
                },
                **commun,
            )
            # Outbox locale : écrite dans le même MULTI que l'agrégat.
            p.xadd("outbox", {"event": vers_json(vers_livraison)})
            p.xadd("outbox", {"event": vers_json(vers_suivi)})

        return ecrire

    return modifier(cid, decider)


def modifier_adresse(cid: str, adresse: Adresse) -> dict:
    nouvelle = adresse.model_dump()

    def decider(pipe, commande):
        if commande["statut"] not in ("BROUILLON", "VALIDEE"):
            raise HTTPException(409, f"commande {commande['statut']}")
        ancienne = commande["client"]["adresseLivraison"]
        if ancienne == nouvelle:
            raise HTTPException(409, "adresse identique")
        if commande["statut"] == "VALIDEE":
            statut_livraison = pipe.hget(k_livraison(cid), "statut")
            if statut_livraison in ("EN_ROUTE", "LIVREE"):
                raise HTTPException(409, f"la livraison est déjà {statut_livraison} (réplica Livraison)")

        def ecrire(p, version):
            p.hset(k_commande(cid), mapping={f"adresseLivraison.{k}": v for k, v in nouvelle.items()})
            if commande["statut"] == "VALIDEE":
                evenement = nouvel_evenement(
                    event_type="AdresseLivraisonModifiee",
                    emetteur=SERVICE,
                    recepteur="livraison",
                    aggregate_id=cid,
                    aggregate_version=version,
                    operation="METTRE_A_JOUR",
                    donnee=f"commandeLivrable[{cid}].client.adresseLivraison",
                    cible={"commandeId": cid},
                    ancienne=ancienne,
                    nouvelle=nouvelle,
                    correlation_id=f"corr_{cid}",
                )
                p.xadd("outbox", {"event": vers_json(evenement)})

        return ecrire

    return modifier(cid, decider)


# --------------------------------------------------------------------------- consommation des événements
def _version_source(cle: str) -> int:
    valeur = r.hget(cle, "sourceVersion")
    return int(valeur) if valeur else 0


def _champs_plat(plat: dict) -> dict:
    return {
        "platId": plat["platId"],
        "nom": plat["nom"],
        "prixMontant": plat["prix"]["montant"],
        "prixDevise": plat["prix"]["devise"],
        "disponible": "true" if plat["disponible"] else "false",
    }


def sur_restaurant_publie(evt: dict) -> str:
    rid, version = evt["aggregateId"], evt["aggregateVersion"]
    if _version_source(k_restaurant(rid)) >= version:
        return "ignoré (version déjà appliquée)"
    snapshot = evt["modification"]["nouvelleValeur"]
    pipe = r.pipeline()
    for pid in r.smembers(k_plats(rid)):
        pipe.delete(k_plat(rid, pid))
    pipe.delete(k_plats(rid))
    pipe.hset(
        k_restaurant(rid),
        mapping={
            "restaurantId": rid,
            "nom": snapshot["nom"],
            "telephone": snapshot.get("telephone") or "",
            "statut": snapshot["statut"],
            "adresse.ligne1": snapshot["adresse"]["ligne1"],
            "adresse.codePostal": snapshot["adresse"]["codePostal"],
            "adresse.ville": snapshot["adresse"]["ville"],
            "sourceVersion": version,
            "misAJourLe": evt["occurredAt"],
        },
    )
    pipe.sadd("catalogue:restaurants", rid)
    for plat in snapshot["plats"]:
        pipe.sadd(k_plats(rid), plat["platId"])
        pipe.hset(k_plat(rid, plat["platId"]), mapping=_champs_plat(plat))
    marquer_traite(pipe, evt)
    pipe.execute()
    return "réplica catalogue créé"


def sur_menu_mis_a_jour(evt: dict) -> str:
    cible, version = evt["modification"]["cible"], evt["aggregateVersion"]
    rid, pid, champ = cible["restaurantId"], cible["platId"], cible["champ"]
    applique = _version_source(k_restaurant(rid))
    if applique == 0:
        raise RejetMetier(f"restaurant {rid} absent du réplica")
    if version <= applique:
        return "ignoré (version déjà appliquée)"
    nouvelle = evt["modification"]["nouvelleValeur"]
    pipe = r.pipeline()
    if champ == "prix":
        pipe.hset(k_plat(rid, pid), mapping={"prixMontant": nouvelle["montant"], "prixDevise": nouvelle["devise"]})
    elif champ == "disponible":
        pipe.hset(k_plat(rid, pid), "disponible", "true" if nouvelle else "false")
    elif champ == "plat":
        pipe.sadd(k_plats(rid), pid)
        pipe.hset(k_plat(rid, pid), mapping=_champs_plat(nouvelle))
    else:
        raise RejetMetier(f"champ de menu inconnu : {champ}")
    pipe.hset(k_restaurant(rid), mapping={"sourceVersion": version, "misAJourLe": evt["occurredAt"]})
    marquer_traite(pipe, evt)
    pipe.execute()
    return f"réplica catalogue mis à jour ({champ})"


def sur_statut_restaurant(evt: dict) -> str:
    rid, version = evt["aggregateId"], evt["aggregateVersion"]
    applique = _version_source(k_restaurant(rid))
    if applique == 0:
        raise RejetMetier(f"restaurant {rid} absent du réplica")
    if version <= applique:
        return "ignoré (version déjà appliquée)"
    pipe = r.pipeline()
    pipe.hset(
        k_restaurant(rid),
        mapping={"statut": evt["modification"]["nouvelleValeur"], "sourceVersion": version, "misAJourLe": evt["occurredAt"]},
    )
    marquer_traite(pipe, evt)
    pipe.execute()
    return "réplica catalogue mis à jour (statut)"


def sur_etat_livraison(evt: dict) -> str:
    cible, version = evt["modification"]["cible"], evt["aggregateVersion"]
    cid = cible["commandeId"]
    if version <= _version_source(k_livraison(cid)):
        return "ignoré (version déjà appliquée)"
    nouvelle = evt["modification"]["nouvelleValeur"]
    statut = nouvelle["statut"] if isinstance(nouvelle, dict) else nouvelle
    pipe = r.pipeline()
    pipe.hset(
        k_livraison(cid),
        mapping={"livraisonId": cible["livraisonId"], "statut": statut, "sourceVersion": version, "misAJourLe": evt["occurredAt"]},
    )
    marquer_traite(pipe, evt)
    pipe.execute()
    return "réplica livraison créé" if evt["operationReplica"] == "CREER" else "réplica livraison mis à jour"


GESTIONNAIRES = {
    "RestaurantPublie": sur_restaurant_publie,
    "MenuMisAJour": sur_menu_mis_a_jour,
    "StatutRestaurantModifie": sur_statut_restaurant,
    "LivraisonCreee": sur_etat_livraison,
    "StatutLivraisonModifie": sur_etat_livraison,
}


def traiter(evt: dict) -> str:
    gestionnaire = GESTIONNAIRES.get(evt["eventType"])
    if gestionnaire is None:
        raise RejetMetier(f"type d'événement non géré : {evt['eventType']}")
    return gestionnaire(evt)


# --------------------------------------------------------------------------- application
@asynccontextmanager
async def lifespan(_app: FastAPI):
    r.set("compteur:commande", 1000, nx=True)
    ConsommateurBus(SERVICE, r, traiter).start()
    RelaisOutboxRedis(SERVICE, r).start()
    yield


app = FastAPI(title="Tastigo - service Commande", lifespan=lifespan)


@app.get("/sante")
def sante():
    r.ping()
    return {"service": SERVICE, "base": "Redis DB 2", "statut": "ok"}


@app.get("/catalogue")
def catalogue():
    restaurants = sorted(r.smembers("catalogue:restaurants"), key=_cle_numerique)
    return [lire_restaurant_replica(rid) for rid in restaurants]


@app.get("/catalogue/{restaurant_id}")
def catalogue_restaurant(restaurant_id: str):
    restaurant = lire_restaurant_replica(restaurant_id)
    if restaurant is None:
        raise HTTPException(404, f"restaurant {restaurant_id} absent du réplica")
    return restaurant


@app.post("/commandes", status_code=201)
def creer(entree: NouvelleCommande):
    return creer_commande(entree)


@app.get("/commandes")
def lister(statut: Literal["BROUILLON", "VALIDEE"] = "VALIDEE"):
    return sorted(r.smembers(f"commandes:statut:{statut}"), key=_cle_numerique)


@app.get("/commandes/{commande_id}")
def lire(commande_id: str):
    return obtenir_commande(commande_id)


@app.post("/commandes/{commande_id}/lignes", status_code=201)
def nouvelle_ligne(commande_id: str, entree: NouvelleLigne):
    return ajouter_ligne(commande_id, entree)


@app.delete("/commandes/{commande_id}/lignes/{ligne_id}")
def supprimer_ligne(commande_id: str, ligne_id: str):
    return retirer_ligne(commande_id, ligne_id)


@app.post("/commandes/{commande_id}/valider")
def valider(commande_id: str):
    return valider_commande(commande_id)


@app.put("/commandes/{commande_id}/adresse-livraison")
def changer_adresse(commande_id: str, adresse: Adresse):
    return modifier_adresse(commande_id, adresse)


@app.get("/clients/{client_id}/commandes")
def commandes_client(client_id: str):
    return [obtenir_commande(cid) for cid in r.zrevrange(f"commandes:client:{client_id}", 0, -1)]


@app.get("/evenements")
def evenements():
    return etat_evenements(r)
