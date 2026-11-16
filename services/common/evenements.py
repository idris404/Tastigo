"""Enveloppe commune des événements échangés entre les services (voir Events.json)."""

import json
import uuid
from datetime import datetime, timezone

EVENT_VERSION = 1

CHAMPS_OBLIGATOIRES = [
    "eventId",
    "eventType",
    "eventVersion",
    "occurredAt",
    "correlationId",
    "emetteur",
    "recepteur",
    "aggregateId",
    "aggregateVersion",
    "operationReplica",
    "modification",
]


def maintenant() -> str:
    """Date UTC au format ISO 8601, par exemple 2026-10-07T10:15:00.000Z."""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def en_millis(date_iso: str) -> int:
    """Convertit une date ISO 8601 en millisecondes (utilisé comme score de ZSET)."""
    return int(datetime.fromisoformat(date_iso.replace("Z", "+00:00")).timestamp() * 1000)


def nouvel_evenement(
    *,
    event_type: str,
    emetteur: str,
    recepteur: str,
    aggregate_id: str,
    aggregate_version: int,
    operation: str,
    donnee: str,
    ancienne,
    nouvelle,
    correlation_id: str,
    cible: dict | None = None,
    occurred_at: str | None = None,
) -> dict:
    """Construit un événement versionné.

    - ``donnee`` : chemin lisible de la donnée modifiée dans le réplica du récepteur ;
    - ``cible`` : identifiants structurés permettant au récepteur de retrouver cette donnée ;
    - ``ancienne`` / ``nouvelle`` : valeur avant et après la modification.
    """
    if operation not in ("CREER", "METTRE_A_JOUR"):
        raise ValueError(f"operationReplica inconnue : {operation}")
    return {
        "eventId": f"evt_{uuid.uuid4().hex[:20]}",
        "eventType": event_type,
        "eventVersion": EVENT_VERSION,
        "occurredAt": occurred_at or maintenant(),
        "correlationId": correlation_id,
        "emetteur": emetteur,
        "recepteur": recepteur,
        "aggregateId": aggregate_id,
        "aggregateVersion": aggregate_version,
        "operationReplica": operation,
        "modification": {
            "donneeAgregatModifiee": donnee,
            "cible": cible or {},
            "ancienneValeur": ancienne,
            "nouvelleValeur": nouvelle,
        },
    }


def flux_vers(service: str) -> str:
    """Nom du flux Redis Streams (boîte de réception) d'un service sur le bus."""
    return f"evenements:vers:{service}"


def vers_json(evenement: dict) -> str:
    return json.dumps(evenement, ensure_ascii=False, separators=(",", ":"))
