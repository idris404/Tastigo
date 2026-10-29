# Bases NoSQL utilisées

## MongoDB pour Restaurant

Le service Restaurant conserve le catalogue source dans la base `tastigo_restaurant`. Un restaurant est stocké comme un document contenant son adresse, ses horaires et ses plats. Cette représentation évite des jointures pour la lecture la plus fréquente : afficher un restaurant et son menu.

La collection `restaurants` utilise un validateur JSON Schema et trois index : identifiant unique, recherche par statut et ville, et recherche textuelle sur le nom des plats. La collection `outbox` conserve les événements à publier dans la même base que l'agrégat source.

## Redis pour Commande Livraison et Suivi

Les services Commande, Livraison et Suivi utilisent des bases logiques Redis séparées :

- DB 2 pour les commandes et le catalogue Restaurant répliqué ;
- DB 3 pour les livraisons et le snapshot de commande répliqué ;
- DB 4 pour la projection `SuiviCommande`.

Les `HASH` stockent les champs simples, les `LIST` conservent les lignes et la chronologie, les `SET` assurent l'idempotence des événements et les `STREAM` matérialisent les événements sortants. Redis permet de lire rapidement une commande, une livraison ou un suivi à partir de son identifiant.

## Cohérence et réplication

Le consommateur `scripts/process-mongodb-outbox.sh` lit les événements MongoDB non publiés dans l'ordre de `aggregateVersion`. Il crée le réplica lors de `RestaurantPublie`, met le prix à jour lors de `MenuMisAJour`, mémorise l'`eventId` dans Redis puis marque l'événement comme publié dans MongoDB.

Le script `redis/02_evenements.redis` démontre ensuite les flux Commande vers Livraison et Commande ou Livraison vers Suivi. La cohérence est éventuelle : un court délai peut exister entre la modification de la source et la mise à jour du réplica.
