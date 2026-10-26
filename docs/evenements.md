# Étape 4 — Découplage et événements

Les exemples complets sont dans [`../Events.json`](../Events.json). Chaque contrat identifie explicitement l'émetteur, le récepteur, la donnée modifiée et sa nouvelle valeur.

## Enveloppe commune

Tous les événements utilisent les métadonnées suivantes :

- `eventId` : identifiant unique utilisé pour l'idempotence ;
- `eventType` et `eventVersion` : nom et version du contrat ;
- `occurredAt` : date UTC du fait métier ;
- `correlationId` : lien entre les événements d'un même parcours ;
- `emetteur` et `recepteur` : direction du flux ;
- `aggregateId` et `aggregateVersion` : source et ordre des changements ;
- `operationReplica` : `CREER` ou `METTRE_A_JOUR` ;
- `modification` : chemin de la donnée, ancienne valeur et nouvelle valeur.

## Catalogue Restaurant vers Commande

### Création du réplica

`RestaurantPublie` est émis par Restaurant et reçu par Commande. Il crée `catalogueRestaurants[restaurantId]` avec le nom, le statut et le menu minimal.

### Mise à jour du réplica

`MenuMisAJour` transporte précisément le champ changé. Dans l'exemple, le prix de `plat_7` passe de 12,50 € à 12,90 €. Commande met à jour son catalogue, mais ne réécrit pas les commandes déjà validées.

## Commande vers Livraison

### Création du réplica

`CommandeValidee` est émis par Commande et reçu par Livraison. Il crée `commandeLivrable[commandeId]`, puis permet de créer exactement une `Livraison` grâce à l'unicité de `commandeId`.

### Mise à jour du réplica

`AdresseLivraisonModifiee` est accepté tant que la livraison n'est pas partie. Il remplace uniquement le champ d'adresse indiqué. Si l'événement arrive après le passage à `EN_ROUTE`, Livraison le refuse et signale l'échec fonctionnel.

## Vers le service Suivi

- `CommandeValidee` crée la projection initiale.
- `LivraisonCreee` lui ajoute l'identifiant de livraison et le statut initial.
- `StatutLivraisonModifie` remplace le statut courant et ajoute une entrée à la chronologie.

## Traitement fiable

Le producteur enregistre le changement métier et l'événement dans une même transaction locale (*outbox*). Un processus publie ensuite cet événement sur le bus. Le consommateur vérifie `eventId`, contrôle `aggregateVersion`, applique sa transaction locale puis marque l'événement comme traité.

Ce mécanisme autorise une livraison *au moins une fois* : recevoir deux fois le même événement ne produit pas deux livraisons ni deux entrées de chronologie.

## Matrice de couverture

| Réplica | Événement de création | Événement de mise à jour |
|---|---|---|
| Catalogue dans Commande | `RestaurantPublie` | `MenuMisAJour` |
| Commande livrable dans Livraison | `CommandeValidee` | `AdresseLivraisonModifiee` |
| Vue client dans Suivi | `CommandeValidee` | `LivraisonCreee`, `StatutLivraisonModifie` |
