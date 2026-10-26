# Étape 3 — Agrégats et réplicas

Les valeurs complètes et cohérentes sont disponibles dans [`../Aggregates.json`](../Aggregates.json). Les montants sont stockés en centimes pour éviter les erreurs d'arrondi.

## Agrégat Restaurant

La racine `Restaurant` protège la cohérence du catalogue. Les entités `Plat` ne sont modifiées qu'en passant par cette racine.

- Identifiant : `restaurantId`.
- Objets-valeur : `adresse`, `horaires`, `prix`.
- Entités internes : `plats`.
- États : `BROUILLON`, `PUBLIE`, `INDISPONIBLE`.

## Agrégat Commande

La racine `Commande` protège le panier et son total.

- Identifiant : `commandeId`.
- Entités internes : `lignes`.
- Objets-valeur : `client`, `adresseLivraison`, `prixUnitaire`, `total`.
- États : `BROUILLON`, `VALIDEE`, `ANNULEE`.

Le nom et le prix d'un plat sont des snapshots. Cette duplication est intentionnelle : elle garantit qu'une commande historique reste fidèle à ce que le client a validé.

## Agrégat Livraison

La racine `Livraison` protège les transitions d'acheminement.

- Identifiant : `livraisonId`.
- Référence unique : `commandeId`.
- Objets-valeur : `collecte`, `destination`, `livreur`, `pourboire`.
- États : `EN_PREPARATION`, `EN_ROUTE`, `LIVREE`.

## Projection SuiviCommande

`SuiviCommande` est identifiée par `commandeId`. Elle contient un résumé, le statut affiché et la chronologie. Bien qu'elle soit présentée avec les agrégats pour répondre au format JSON demandé, c'est un modèle de lecture et non un agrégat transactionnel.

## Réplicas

Un réplica est une copie locale, partielle et assumée de la donnée d'un autre service.

### Catalogue dans Commande

Commande copie `restaurantId`, `nom`, `statut` et les données minimales des plats. Il peut donc vérifier un panier sans accès synchrone à la base Restaurant.

### Commande livrable dans Livraison

Livraison copie les coordonnées de collecte et de destination, le nombre d'articles et le total. Il peut donc poursuivre l'acheminement si Commande est indisponible.

### Résumé et état dans Suivi

Suivi combine une partie de Commande et une partie de Livraison. Cette copie est adaptée à la lecture client et non aux écritures métier.

## Compromis

La réplication améliore l'autonomie et la disponibilité, mais introduit une cohérence éventuelle. Pendant quelques instants, un récepteur peut afficher une ancienne valeur. Les champs `eventId` et `aggregateVersion` limitent respectivement les doublons et les événements appliqués dans le désordre.
