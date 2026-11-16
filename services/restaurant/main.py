"""Service Restaurant : source de vérité du catalogue, stocké dans MongoDB.

Chaque commande modifie l'agrégat Restaurant (un document) et écrit l'événement destiné
au service Commande dans la collection ``outbox`` au sein d'une même transaction MongoDB.
Un relais publie ensuite l'outbox sur le bus Redis Streams.
"""

import logging
import os
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Callable, Literal

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field
from pymongo import MongoClient, ReturnDocument
from pymongo.errors import DuplicateKeyError

from common.bus import connexion_bus
from common.evenements import flux_vers, nouvel_evenement, vers_json

from . import schema, seed

SERVICE = "restaurant"
log = logging.getLogger(SERVICE)

client = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017/?directConnection=true"), tz_aware=True)
db = client[os.environ.get("MONGO_DB", "tastigo_restaurant")]

Jour = Literal["LUNDI", "MARDI", "MERCREDI", "JEUDI", "VENDREDI", "SAMEDI", "DIMANCHE"]
HEURE = r"^[0-2][0-9]:[0-5][0-9]$"


# --------------------------------------------------------------------------- modèles d'entrée
class Prix(BaseModel):
    montant: int = Field(gt=0, description="montant en centimes")
    devise: Literal["EUR"] = "EUR"


class Adresse(BaseModel):
    ligne1: str = Field(min_length=1)
    codePostal: str = Field(pattern=r"^[0-9]{5}$")
    ville: str = Field(min_length=1)


class Horaire(BaseModel):
    jour: Jour
    ouverture: str = Field(pattern=HEURE)
    fermeture: str = Field(pattern=HEURE)


class PlatEntree(BaseModel):
    platId: str | None = Field(default=None, pattern=r"^plat_")
    nom: str = Field(min_length=1)
    categorie: str | None = None
    prix: Prix
    disponible: bool = True


class RestaurantEntree(BaseModel):
    restaurantId: str | None = Field(default=None, pattern=r"^rest_")
    nom: str = Field(min_length=1)
    telephone: str | None = None
    adresse: Adresse
    horaires: list[Horaire] = []
    plats: list[PlatEntree] = []


class Disponibilite(BaseModel):
    disponible: bool


class NouveauStatut(BaseModel):
    statut: Literal["PUBLIE", "INDISPONIBLE"]


# --------------------------------------------------------------------------- outils
def _maintenant() -> datetime:
    return datetime.now(timezone.utc)


def nouvel_id(prefixe: str) -> str:
    compteur = db.compteurs.find_one_and_update(
        {"_id": prefixe}, {"$inc": {"valeur": 1}}, upsert=True, return_document=ReturnDocument.AFTER
    )
    return f"{prefixe}_{compteur['valeur']}"


def vue_plat(plat: dict) -> dict:
    return {k: plat[k] for k in ("platId", "nom", "prix", "disponible")}


def vue_catalogue(restaurant: dict) -> dict:
    """Données minimales copiées dans le réplica du service Commande."""
    return {
        "restaurantId": restaurant["restaurantId"],
        "nom": restaurant["nom"],
        "telephone": restaurant.get("telephone"),
        "adresse": restaurant["adresse"],
        "statut": restaurant["statut"],
        "plats": [vue_plat(p) for p in restaurant["plats"]],
    }


def lire(restaurant_id: str) -> dict:
    restaurant = db.restaurants.find_one({"restaurantId": restaurant_id}, {"_id": 0})
    if restaurant is None:
        raise HTTPException(404, f"restaurant {restaurant_id} introuvable")
    return restaurant


def executer(restaurant_id: str, decider: Callable[[dict], tuple[dict, list[dict]]]) -> dict:
    """Exécute une commande sur l'agrégat Restaurant.

    ``decider`` reçoit l'état courant, vérifie les règles métier et renvoie les champs à
    modifier et les événements à produire. L'écriture de l'agrégat (verrou optimiste sur
    ``version``) et celle de l'outbox sont faites dans la même transaction MongoDB.
    """

    def transaction(session):
        actuel = db.restaurants.find_one({"restaurantId": restaurant_id}, {"_id": 0}, session=session)
        if actuel is None:
            raise HTTPException(404, f"restaurant {restaurant_id} introuvable")
        champs, evenements = decider(actuel)
        version = actuel["version"] + 1
        resultat = db.restaurants.update_one(
            {"restaurantId": restaurant_id, "version": actuel["version"]},
            {"$set": {**champs, "version": version, "modifieLe": _maintenant()}},
            session=session,
        )
        if resultat.modified_count != 1:
            raise HTTPException(409, "conflit de version : l'agrégat a été modifié entre-temps")
        for description in evenements:
            evenement = nouvel_evenement(
                emetteur=SERVICE,
                recepteur="commande",
                aggregate_id=restaurant_id,
                aggregate_version=version,
                correlation_id=f"corr_{restaurant_id}",
                **description,
            )
            db.outbox.insert_one({**evenement, "publie": False, "creeLe": _maintenant()}, session=session)

    with client.start_session() as session:
        session.with_transaction(transaction)
    return lire(restaurant_id)


# --------------------------------------------------------------------------- commandes
def creer_restaurant(entree: RestaurantEntree) -> dict:
    restaurant_id = entree.restaurantId or nouvel_id("rest")
    plats = []
    for plat in entree.plats:
        donnees = plat.model_dump(exclude_none=True)
        donnees["platId"] = plat.platId or nouvel_id("plat")
        plats.append(donnees)
    document = {
        "restaurantId": restaurant_id,
        "nom": entree.nom,
        "adresse": entree.adresse.model_dump(),
        "horaires": [h.model_dump() for h in entree.horaires],
        "statut": "BROUILLON",
        "plats": plats,
        "version": 1,
        "creeLe": _maintenant(),
    }
    if entree.telephone:
        document["telephone"] = entree.telephone
    try:
        db.restaurants.insert_one(document)
    except DuplicateKeyError:
        raise HTTPException(409, f"le restaurant {restaurant_id} existe déjà")
    # Un restaurant en brouillon n'est pas visible : aucun événement n'est émis.
    return lire(restaurant_id)


def publier_restaurant(restaurant_id: str) -> dict:
    def decider(r: dict):
        if r["statut"] != "BROUILLON":
            raise HTTPException(409, "le restaurant est déjà publié")
        if not r["horaires"]:
            raise HTTPException(422, "un restaurant publié doit avoir au moins un horaire")
        if not r["plats"]:
            raise HTTPException(422, "un restaurant publié doit avoir au moins un plat")
        publie = {**r, "statut": "PUBLIE"}
        return {"statut": "PUBLIE", "publieLe": _maintenant()}, [
            dict(
                event_type="RestaurantPublie",
                operation="CREER",
                donnee=f"catalogueRestaurants[{restaurant_id}]",
                cible={"restaurantId": restaurant_id},
                ancienne=None,
                nouvelle=vue_catalogue(publie),
            )
        ]

    return executer(restaurant_id, decider)


def _evenement_menu(r: dict, plat_id: str, champ: str, ancienne, nouvelle) -> list[dict]:
    if r["statut"] == "BROUILLON":
        return []  # le catalogue n'a encore jamais été diffusé
    chemin = f"catalogueRestaurants[{r['restaurantId']}].plats[{plat_id}]"
    return [
        dict(
            event_type="MenuMisAJour",
            operation="METTRE_A_JOUR",
            donnee=chemin if champ == "plat" else f"{chemin}.{champ}",
            cible={"restaurantId": r["restaurantId"], "platId": plat_id, "champ": champ},
            ancienne=ancienne,
            nouvelle=nouvelle,
        )
    ]


def ajouter_plat(restaurant_id: str, entree: PlatEntree) -> dict:
    plat = entree.model_dump(exclude_none=True)
    plat["platId"] = entree.platId or nouvel_id("plat")

    def decider(r: dict):
        if any(p["platId"] == plat["platId"] for p in r["plats"]):
            raise HTTPException(409, f"le plat {plat['platId']} existe déjà")
        return {"plats": r["plats"] + [plat]}, _evenement_menu(r, plat["platId"], "plat", None, vue_plat(plat))

    return executer(restaurant_id, decider)


def modifier_plat(restaurant_id: str, plat_id: str, champ: str, valeur) -> dict:
    def decider(r: dict):
        plats = [dict(p) for p in r["plats"]]
        plat = next((p for p in plats if p["platId"] == plat_id), None)
        if plat is None:
            raise HTTPException(404, f"le plat {plat_id} n'appartient pas au restaurant {restaurant_id}")
        ancienne = plat[champ]
        if ancienne == valeur:
            raise HTTPException(409, f"{champ} est déjà égal à la valeur demandée")
        plat[champ] = valeur
        return {"plats": plats}, _evenement_menu(r, plat_id, champ, ancienne, valeur)

    return executer(restaurant_id, decider)


def modifier_statut(restaurant_id: str, statut: str) -> dict:
    def decider(r: dict):
        if r["statut"] == "BROUILLON":
            raise HTTPException(409, "un brouillon doit d'abord être publié")
        if r["statut"] == statut:
            raise HTTPException(409, f"le restaurant est déjà {statut}")
        return {"statut": statut}, [
            dict(
                event_type="StatutRestaurantModifie",
                operation="METTRE_A_JOUR",
                donnee=f"catalogueRestaurants[{restaurant_id}].statut",
                cible={"restaurantId": restaurant_id},
                ancienne=r["statut"],
                nouvelle=statut,
            )
        ]

    return executer(restaurant_id, decider)


# --------------------------------------------------------------------------- relais de l'outbox
class RelaisOutboxMongo(threading.Thread):
    """Publie sur le bus les événements de l'outbox MongoDB encore non publiés, dans l'ordre."""

    def __init__(self):
        super().__init__(daemon=True, name="relais-restaurant")
        self.bus = connexion_bus()

    def run(self) -> None:
        while True:
            try:
                for document in db.outbox.find({"publie": False}).sort("_id", 1).limit(50):
                    evenement = {
                        k: v for k, v in document.items() if k not in ("_id", "publie", "publieLe", "creeLe")
                    }
                    self.bus.xadd(
                        flux_vers(evenement["recepteur"]),
                        {"event": vers_json(evenement), "eventType": evenement["eventType"]},
                    )
                    db.outbox.update_one({"_id": document["_id"]}, {"$set": {"publie": True, "publieLe": _maintenant()}})
                    log.info("publié %s %s -> %s", evenement["eventType"], evenement["eventId"], evenement["recepteur"])
                time.sleep(0.5)
            except Exception:
                log.exception("relais : erreur, nouvelle tentative")
                time.sleep(1)


# --------------------------------------------------------------------------- démarrage
def peupler() -> None:
    if db.restaurants.count_documents({}) > 0:
        return
    log.info("base vide : création du jeu de données initial")
    for element in seed.RESTAURANTS:
        restaurant_id = element["restaurant"]["restaurantId"]
        creer_restaurant(RestaurantEntree(**element["restaurant"]))
        for action, *args in element["ensuite"]:
            if action == "publier":
                publier_restaurant(restaurant_id)
            elif action == "prix":
                modifier_plat(restaurant_id, args[0], "prix", {"montant": args[1], "devise": "EUR"})
            elif action == "disponibilite":
                modifier_plat(restaurant_id, args[0], "disponible", args[1])
            elif action == "statut":
                modifier_statut(restaurant_id, args[0])


def initialiser() -> None:
    for essai in range(30):
        try:
            client.admin.command("ping")
            break
        except Exception:
            log.info("attente de MongoDB (%d)", essai + 1)
            time.sleep(1)
    schema.initialiser(db)
    for prefixe in ("rest", "plat"):
        # Les identifiants générés commencent après ceux du jeu de données.
        db.compteurs.update_one({"_id": prefixe}, {"$setOnInsert": {"valeur": 100}}, upsert=True)
    if os.environ.get("SEED", "true") == "true":
        peupler()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    initialiser()
    RelaisOutboxMongo().start()
    yield


app = FastAPI(title="Tastigo - service Restaurant", lifespan=lifespan)


# --------------------------------------------------------------------------- API
@app.get("/sante")
def sante():
    client.admin.command("ping")
    return {"service": SERVICE, "base": "MongoDB", "statut": "ok"}


@app.get("/restaurants")
def lister_restaurants(ville: str | None = None, statut: str | None = None):
    filtre = {}
    if ville:
        filtre["adresse.ville"] = ville
    if statut:
        filtre["statut"] = statut
    return list(db.restaurants.find(filtre, {"_id": 0}).sort("restaurantId", 1))


@app.get("/restaurants/{restaurant_id}")
def lire_restaurant(restaurant_id: str):
    return lire(restaurant_id)


@app.get("/restaurants/{restaurant_id}/menu")
def menu_disponible(restaurant_id: str):
    lire(restaurant_id)
    return list(
        db.restaurants.aggregate(
            [
                {"$match": {"restaurantId": restaurant_id}},
                {"$unwind": "$plats"},
                {"$match": {"plats.disponible": True}},
                {
                    "$project": {
                        "_id": 0,
                        "platId": "$plats.platId",
                        "nom": "$plats.nom",
                        "categorie": "$plats.categorie",
                        "prix": "$plats.prix",
                    }
                },
                {"$sort": {"prix.montant": 1}},
            ]
        )
    )


@app.get("/plats/recherche")
def rechercher(q: str = Query(min_length=2)):
    return list(
        db.restaurants.find(
            {"$text": {"$search": q}, "statut": "PUBLIE"},
            {"_id": 0, "restaurantId": 1, "nom": 1, "adresse.ville": 1, "score": {"$meta": "textScore"}},
        ).sort([("score", {"$meta": "textScore"})])
    )


@app.get("/statistiques")
def statistiques():
    return {
        "restaurantsParStatut": list(
            db.restaurants.aggregate(
                [
                    {"$group": {"_id": "$statut", "nombre": {"$sum": 1}}},
                    {"$project": {"_id": 0, "statut": "$_id", "nombre": 1}},
                    {"$sort": {"statut": 1}},
                ]
            )
        ),
        "prixParRestaurant": list(
            db.restaurants.aggregate(
                [
                    {"$unwind": "$plats"},
                    {
                        "$group": {
                            "_id": "$restaurantId",
                            "nom": {"$first": "$nom"},
                            "ville": {"$first": "$adresse.ville"},
                            "nombrePlats": {"$sum": 1},
                            "prixMoyen": {"$avg": "$plats.prix.montant"},
                            "prixMin": {"$min": "$plats.prix.montant"},
                            "prixMax": {"$max": "$plats.prix.montant"},
                        }
                    },
                    {
                        "$project": {
                            "_id": 0,
                            "restaurantId": "$_id",
                            "nom": 1,
                            "ville": 1,
                            "nombrePlats": 1,
                            "prixMoyenCentimes": {"$round": ["$prixMoyen", 0]},
                            "prixMinCentimes": "$prixMin",
                            "prixMaxCentimes": "$prixMax",
                        }
                    },
                    {"$sort": {"restaurantId": 1}},
                ]
            )
        ),
        "evenementsOutbox": list(
            db.outbox.aggregate(
                [
                    {"$group": {"_id": {"type": "$eventType", "publie": "$publie"}, "nombre": {"$sum": 1}}},
                    {"$project": {"_id": 0, "eventType": "$_id.type", "publie": "$_id.publie", "nombre": 1}},
                    {"$sort": {"eventType": 1}},
                ]
            )
        ),
    }


@app.post("/restaurants", status_code=201)
def creer(entree: RestaurantEntree):
    return creer_restaurant(entree)


@app.post("/restaurants/{restaurant_id}/publier")
def publier(restaurant_id: str):
    return publier_restaurant(restaurant_id)


@app.post("/restaurants/{restaurant_id}/plats", status_code=201)
def nouveau_plat(restaurant_id: str, entree: PlatEntree):
    return ajouter_plat(restaurant_id, entree)


@app.put("/restaurants/{restaurant_id}/plats/{plat_id}/prix")
def changer_prix(restaurant_id: str, plat_id: str, prix: Prix):
    return modifier_plat(restaurant_id, plat_id, "prix", prix.model_dump())


@app.put("/restaurants/{restaurant_id}/plats/{plat_id}/disponibilite")
def changer_disponibilite(restaurant_id: str, plat_id: str, entree: Disponibilite):
    return modifier_plat(restaurant_id, plat_id, "disponible", entree.disponible)


@app.put("/restaurants/{restaurant_id}/statut")
def changer_statut(restaurant_id: str, entree: NouveauStatut):
    return modifier_statut(restaurant_id, entree.statut)


@app.get("/outbox")
def lire_outbox(publie: bool | None = None, limite: int = Query(default=50, le=500)):
    filtre = {} if publie is None else {"publie": publie}
    return list(db.outbox.find(filtre, {"_id": 0}).sort("_id", -1).limit(limite))
