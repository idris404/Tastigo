# Projection vers le service Suivi

## Objectif

Le front-end ne doit pas assembler une réponse provenant de Commande et de Livraison. Le service Suivi prépare une vue directement exploitable pour la question : « où en est ma commande ? » (`GET http://localhost:8004/suivis/{commandeId}`).

## Forme de la projection

Voir `services.suivi` dans [`../Aggregates.json`](../Aggregates.json) :

- `commandeId`, `clientId` et `livraisonId` pour la corrélation ;
- le nom du restaurant, sans ses coordonnées internes ;
- le nombre d'articles et le total ;
- un statut technique et un libellé destiné au client ;
- la date de dernière mise à jour ;
- une chronologie ordonnée.

## Transformations

| Événement reçu | Transformation |
|---|---|
| `CommandeValidee` | copie le résumé (nom du restaurant, nombre d'articles, total) ; statut « Commande validée » s'il n'y a pas encore d'information de livraison ; première étape de chronologie ; indexation par client |
| `LivraisonCreee` | rattache `livraisonId` ; statut « Votre commande est en préparation » |
| `StatutLivraisonModifie` | « Votre commande est en route » ou « Commande livrée » ; nouvelle étape de chronologie |

## Robustesse

- **Ordre d'arrivée** : `CommandeValidee` (émis par Commande) et `LivraisonCreee` (émis par Livraison) peuvent arriver dans n'importe quel ordre. Chaque transformation complète la projection sans écraser l'autre. Le statut n'est remplacé que si la version de la livraison est plus récente (`versionLivraison`).
- **Doublons** : un `eventId` déjà traité est ignoré ; la chronologie est un `ZSET`, donc une même étape ne peut pas apparaître deux fois.
- **Reconstruction** : `POST /admin/reconstruire` supprime la projection puis rejoue toute la boîte de réception `evenements:vers:suivi`. La démonstration vérifie que la projection reconstruite est identique.

## Limite assumée

Le statut visible est éventuellement cohérent : après un changement dans Livraison, quelques millisecondes peuvent s'écouler avant sa projection. Le champ `derniereMiseAJour` rend ce compromis explicite.
