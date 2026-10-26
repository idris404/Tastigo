# Étape 5 — Projection vers le service Suivi

## Objectif

Le front-end ne doit pas assembler lui-même une réponse provenant de Commande et de Livraison. Le service Suivi prépare une vue directement exploitable, optimisée pour la question : « où en est ma commande ? »

## Agrégat projeté

La forme JSON de `SuiviCommande` se trouve dans [`../Aggregates.json`](../Aggregates.json). Elle contient :

- `commandeId` et `livraisonId` pour la corrélation ;
- le nom du restaurant ;
- le nombre d'articles et le total ;
- un libellé de statut destiné au client ;
- la date de dernière mise à jour ;
- une chronologie ordonnée.

## Transformations

### À la réception de CommandeValidee

1. Compter les quantités des lignes pour produire `nombreArticles`.
2. Conserver uniquement le nom du restaurant, sans ses coordonnées internes.
3. Copier le total déjà calculé par Commande.
4. Créer la première entrée `COMMANDE_VALIDEE`.

### À la réception de LivraisonCreee

1. Rattacher `livraisonId` grâce à `commandeId` et `correlationId`.
2. Convertir `EN_PREPARATION` en « Votre commande est en préparation ».
3. Ajouter cette étape à la chronologie.

### À la réception de StatutLivraisonModifie

1. Remplacer le statut courant.
2. Traduire `EN_ROUTE` en « Votre commande est en route » ou `LIVREE` en « Commande livrée ».
3. Ajouter la nouvelle valeur et sa date à la chronologie, sauf si `eventId` a déjà été traité.

## Pourquoi utiliser des événements ?

Suivi est autonome : il n'effectue aucune jointure distribuée et n'a pas besoin que les services sources soient disponibles au moment de la lecture. Sa projection peut aussi être supprimée puis reconstruite par rejeu des événements, ce qui facilite la correction d'une transformation.

## Limite assumée

Le statut visible est éventuellement cohérent. Après un changement dans Livraison, un court délai peut exister avant sa projection dans Suivi. L'interface peut afficher `derniereMiseAJour` pour rendre ce compromis explicite.
