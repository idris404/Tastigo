"""Validateurs JSON Schema et index MongoDB du service Restaurant."""

from pymongo import ASCENDING, TEXT
from pymongo.database import Database
from pymongo.errors import CollectionInvalid

PRIX = {
    "bsonType": "object",
    "required": ["montant", "devise"],
    "additionalProperties": False,
    "properties": {
        "montant": {"bsonType": ["int", "long"], "minimum": 1, "description": "centimes, > 0"},
        "devise": {"enum": ["EUR"]},
    },
}

ADRESSE = {
    "bsonType": "object",
    "required": ["ligne1", "codePostal", "ville"],
    "properties": {
        "ligne1": {"bsonType": "string", "minLength": 1},
        "codePostal": {"bsonType": "string", "pattern": "^[0-9]{5}$"},
        "ville": {"bsonType": "string", "minLength": 1},
    },
}

RESTAURANT = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": ["restaurantId", "nom", "adresse", "horaires", "statut", "plats", "version"],
        "properties": {
            "restaurantId": {"bsonType": "string", "pattern": "^rest_"},
            "nom": {"bsonType": "string", "minLength": 1},
            "telephone": {"bsonType": "string"},
            "adresse": ADRESSE,
            "horaires": {
                "bsonType": "array",
                "items": {
                    "bsonType": "object",
                    "required": ["jour", "ouverture", "fermeture"],
                    "properties": {
                        "jour": {
                            "enum": ["LUNDI", "MARDI", "MERCREDI", "JEUDI", "VENDREDI", "SAMEDI", "DIMANCHE"]
                        },
                        "ouverture": {"bsonType": "string", "pattern": "^[0-2][0-9]:[0-5][0-9]$"},
                        "fermeture": {"bsonType": "string", "pattern": "^[0-2][0-9]:[0-5][0-9]$"},
                    },
                },
            },
            "statut": {"enum": ["BROUILLON", "PUBLIE", "INDISPONIBLE"]},
            "plats": {
                "bsonType": "array",
                "items": {
                    "bsonType": "object",
                    "required": ["platId", "nom", "prix", "disponible"],
                    "properties": {
                        "platId": {"bsonType": "string", "pattern": "^plat_"},
                        "nom": {"bsonType": "string", "minLength": 1},
                        "categorie": {"bsonType": "string"},
                        "prix": PRIX,
                        "disponible": {"bsonType": "bool"},
                    },
                },
            },
            "version": {"bsonType": ["int", "long"], "minimum": 1},
        },
    }
}

OUTBOX = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": [
            "eventId",
            "eventType",
            "emetteur",
            "recepteur",
            "aggregateId",
            "aggregateVersion",
            "modification",
            "publie",
        ],
        "properties": {
            "eventId": {"bsonType": "string"},
            "eventType": {"bsonType": "string"},
            "emetteur": {"enum": ["restaurant"]},
            "recepteur": {"bsonType": "string"},
            "aggregateId": {"bsonType": "string"},
            "aggregateVersion": {"bsonType": ["int", "long"], "minimum": 1},
            "modification": {"bsonType": "object"},
            "publie": {"bsonType": "bool"},
        },
    }
}


def _collection_validee(db: Database, nom: str, validateur: dict) -> None:
    try:
        db.create_collection(nom, validator=validateur)
    except CollectionInvalid:
        db.command("collMod", nom, validator=validateur)


def initialiser(db: Database) -> None:
    """Crée les collections (avant toute transaction) puis les index. Opérations idempotentes."""
    _collection_validee(db, "restaurants", RESTAURANT)
    _collection_validee(db, "outbox", OUTBOX)

    db.restaurants.create_index([("restaurantId", ASCENDING)], unique=True, name="restaurantId_unique")
    db.restaurants.create_index([("statut", ASCENDING), ("adresse.ville", ASCENDING)], name="statut_ville")
    db.restaurants.create_index([("plats.nom", TEXT), ("nom", TEXT)], default_language="french", name="texte_plats")

    db.outbox.create_index([("eventId", ASCENDING)], unique=True, name="eventId_unique")
    db.outbox.create_index([("publie", ASCENDING), ("_id", ASCENDING)], name="a_publier")
    db.outbox.create_index([("aggregateId", ASCENDING), ("aggregateVersion", ASCENDING)], name="par_agregat")
