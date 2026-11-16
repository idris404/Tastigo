# Définition des services

## Principe de découpage

Une frontière de service suit une responsabilité métier et la propriété de ses données. Aucun service ne lit ni ne modifie la base d'un autre. Les informations qui traversent une frontière passent par un événement publié sur le bus et sont copiées localement par le récepteur (réplica).

Les quatre services sont programmés en Python (FastAPI) et partagent une seule image Docker. Chaque conteneur lance un module différent (`services/<service>/main.py`).

## Service Restaurant (port 8001, MongoDB)

**Responsabilité :** gérer le catalogue proposé aux clients.

- Créer un restaurant en `BROUILLON`, puis le publier.
- Gérer son identité, son adresse, son téléphone et ses horaires.
- Ajouter des plats, modifier leur prix et leur disponibilité.
- Rendre un restaurant `INDISPONIBLE` ou le republier.
- Refuser la publication d'un catalogue incomplet (sans horaire ou sans plat).

Il est le seul propriétaire de l'agrégat `Restaurant`. Un relais publie les événements de son outbox MongoDB vers le service Commande.

## Service Commande (port 8002, Redis DB 2)

**Responsabilité :** construire, calculer et valider une commande.

- Maintenir le catalogue répliqué à partir de `RestaurantPublie`, `MenuMisAJour` et `StatutRestaurantModifie`.
- Créer un panier pour un client et un restaurant publié.
- Ajouter et retirer des lignes en figeant le nom et le prix du plat.
- Calculer le total, valider la commande et modifier l'adresse de livraison.
- Maintenir un réplica de l'état de livraison pour refuser un changement d'adresse quand le livreur est parti.

Il est le seul propriétaire de l'agrégat `Commande`. Une commande validée est un fait historique : une modification ultérieure du menu ne change ni ses lignes ni son total.

## Service Livraison (port 8003, Redis DB 3)

**Responsabilité :** organiser et suivre l'acheminement d'une commande validée.

- Créer le réplica « commande livrable » et une livraison, une seule fois, à la réception de `CommandeValidee`.
- Mettre à jour la destination à la réception de `AdresseLivraisonModifiee`, sauf si la livraison est déjà partie (rejet tracé).
- Affecter un livreur.
- Faire évoluer le statut de `EN_PREPARATION` à `EN_ROUTE` (livreur obligatoire), puis à `LIVREE`.
- Publier `LivraisonCreee` et `StatutLivraisonModifie` vers Suivi et Commande.

Il est le seul propriétaire de l'agrégat `Livraison`. Il n'appelle jamais Commande : les coordonnées de collecte et de destination sont dans son réplica.

## Service Suivi (port 8004, Redis DB 4)

**Responsabilité :** exposer une vue de lecture simple et rapide au client.

- Créer une projection lors de la validation d'une commande.
- Ajouter les informations de livraison lorsqu'elles arrivent, dans n'importe quel ordre.
- Traduire un statut technique en libellé compréhensible.
- Construire une chronologie triée par date.
- Reconstruire toute la projection en rejouant les événements reçus (`POST /admin/reconstruire`).

Il ne porte aucune règle transactionnelle sur la commande ou la livraison.

## Ce qui reste volontairement hors périmètre

Le paiement, l'authentification, la géolocalisation, l'optimisation des tournées, les notifications et l'interface graphique ne sont pas nécessaires pour démontrer le découpage, la réplication et la projection demandés. Les API sont documentées automatiquement par FastAPI (`/docs` sur chaque port).
