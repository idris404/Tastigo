# Agrégats et réplicas

Les exemples complets, l'organisation physique des données et les invariants sont dans [`../Aggregates.json`](../Aggregates.json). Les montants sont stockés en centimes pour éviter les erreurs d'arrondi.

Chaque agrégat porte un champ `version` incrémenté à chaque modification. Il sert de verrou optimiste (filtre `version` dans MongoDB, `WATCH` dans Redis) et devient l'`aggregateVersion` des événements émis.

## Agrégat Restaurant (MongoDB)

La racine `Restaurant` protège la cohérence du catalogue. Les plats ne sont modifiés qu'en passant par cette racine.

- Identifiant : `restaurantId`.
- Objets-valeur : `adresse`, `horaires`, `prix`.
- Entités internes : `plats`.
- États : `BROUILLON`, `PUBLIE`, `INDISPONIBLE`.

Le restaurant, son adresse, ses horaires et ses plats forment **un seul document**. Toute commande sur l'agrégat est donc une écriture atomique sur un document, accompagnée de l'écriture de l'outbox dans la même transaction.

## Agrégat Commande (Redis DB 2)

La racine `Commande` protège le panier et son total.

- Identifiant : `commandeId`.
- Entités internes : `lignes`.
- Objets-valeur : `client`, `adresseLivraison`, `prixUnitaire`, `total`.
- États : `BROUILLON`, `VALIDEE`.

Stockage : un `HASH` pour la racine (champs du client aplatis), une `LIST` pour l'ordre des lignes et un `HASH` par ligne. Le nom et le prix d'un plat sont des snapshots : une commande validée reste fidèle à ce que le client a payé.

## Agrégat Livraison (Redis DB 3)

La racine `Livraison` protège les transitions d'acheminement.

- Identifiant : `livraisonId`.
- Référence unique : `commandeId` (`HASH livraisons:par-commande`).
- Objets-valeur : `livreur`.
- États : `EN_PREPARATION`, `EN_ROUTE`, `LIVREE`, avec une `LIST` d'historique.

Les coordonnées de collecte et de destination ne sont pas dupliquées dans l'agrégat : elles sont lues dans le réplica de la commande.

## Projection SuiviCommande (Redis DB 4)

`SuiviCommande` est identifiée par `commandeId`. Elle contient un résumé, le statut affiché et une chronologie (`ZSET` trié par date). C'est un modèle de lecture, pas un agrégat transactionnel.

## Réplicas

Un réplica est une copie locale, partielle et assumée de la donnée d'un autre service. Il porte un champ `sourceVersion` : la dernière `aggregateVersion` appliquée.

| Réplica | Propriétaire | Source | Raison |
|---|---|---|---|
| `catalogueRestaurants` | Commande | Restaurant | vérifier restaurant, plats, prix et disponibilité sans appel synchrone |
| `etatLivraison` | Commande | Livraison | refuser un changement d'adresse après le départ du livreur |
| `commandeLivrable` | Livraison | Commande | livrer même si Commande est indisponible |
| `resumeCommande` + `etatLivraison` | Suivi | Commande, Livraison | répondre à « où en est ma commande ? » en une lecture |

## Compromis

La réplication améliore l'autonomie et la disponibilité, mais la cohérence devient éventuelle. Pendant quelques millisecondes, un récepteur peut afficher une ancienne valeur. Les champs `eventId` et `aggregateVersion` empêchent respectivement les doublons et l'application d'un événement plus ancien que l'état connu.
