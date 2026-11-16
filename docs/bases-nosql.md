# Bases NoSQL utilisées

## MongoDB pour le service Restaurant

Base `tastigo_restaurant`, lancée en replica set à un nœud (`rs0`) pour disposer des transactions.

**Pourquoi MongoDB :**

- l'agrégat `Restaurant` est naturellement un document imbriqué (adresse, horaires, plats) : une lecture renvoie le catalogue complet sans jointure, et une modification de l'agrégat est une écriture atomique sur un seul document ;
- le catalogue a une structure riche et variable (catégories, horaires différents selon les restaurants) : le schéma flexible est encadré par un validateur `$jsonSchema` (champs obligatoires, prix > 0, code postal, statut) ;
- les besoins de lecture (filtre par ville et statut, recherche plein texte dans les plats, statistiques de prix) sont couverts par les index et le pipeline d'agrégation ;
- les transactions multi-documents permettent d'écrire l'agrégat et l'outbox ensemble.

**Collections :** `restaurants` (un document par restaurant), `outbox` (événements à publier), `compteurs` (identifiants).

**Index :** `restaurantId` unique ; `statut + adresse.ville` ; index texte français sur `plats.nom` et `nom` ; `outbox.eventId` unique ; `outbox.publie + _id` pour le relais ; `outbox.aggregateId + aggregateVersion` pour l'historique.

Requêtes de démonstration : [`../mongodb/requetes.js`](../mongodb/requetes.js) (`./mongodb/run-queries.sh`).

## Redis pour Commande, Livraison et Suivi

Une instance `tastigo-redis` avec une base logique par service : DB 2 (Commande), DB 3 (Livraison), DB 4 (Suivi). Chaque service ne se connecte qu'à sa base.

**Pourquoi Redis :**

- les accès sont presque toujours **par identifiant** (une commande, une livraison, un suivi) : le modèle clé-valeur en mémoire répond en moins d'une milliseconde ;
- les changements de statut sont fréquents et courts ; `WATCH` / `MULTI` / `EXEC` donne un verrou optimiste et des écritures atomiques sur plusieurs clés ;
- les structures natives couvrent exactement les besoins :

| Structure | Utilisation |
|---|---|
| `HASH` | racine des agrégats, lignes de commande, réplicas, projection |
| `LIST` | ordre des lignes, historique des transitions, événements rejetés |
| `SET` | index par statut, plats d'un restaurant, `eventId` déjà traités |
| `ZSET` | commandes d'un client et chronologie triées par date |
| `STREAM` | outbox locale de Commande et Livraison |
| `STRING` + `INCR` | génération des identifiants `cmd_1001`, `liv_501` |

- la projection Suivi est un modèle de lecture reconstruisible : un stockage en mémoire, persisté par AOF, suffit.

Requêtes de lecture : [`../redis/requetes.redis`](../redis/requetes.redis) (`./redis/run.sh`).

## Redis Streams pour le bus d'événements

Une instance Redis séparée (`tastigo-bus`) sert de broker. Les Streams apportent les groupes de consommateurs, l'acquittement (`XACK`), la reprise des messages non acquittés et la conservation de l'historique pour le rejeu, sans ajouter Kafka ou RabbitMQ au projet.

## Pourquoi deux technologies

Le catalogue est un document riche lu en entier et peu modifié : c'est le cas d'usage de MongoDB. Les commandes, livraisons et suivis sont de petits objets lus et modifiés par clé, avec des index simples et des statuts qui changent souvent : c'est le cas d'usage de Redis. Chaque service choisit la base adaptée à son agrégat, ce que permet justement l'indépendance des services.
