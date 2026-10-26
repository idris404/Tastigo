# Étape 2 — Définition des services

## Principe de découpage

Une frontière de service suit une responsabilité métier et la propriété de ses données. Aucun service ne modifie la base d'un autre. Les échanges qui doivent traverser une frontière passent par un contrat d'événement.

## Service Restaurant

**Responsabilité :** gérer le catalogue proposé aux clients.

- Créer et publier un restaurant.
- Gérer son identité, son adresse, son téléphone et ses horaires.
- Ajouter ou modifier les plats, leurs prix et leur disponibilité.
- Refuser la publication d'un catalogue incomplet.

Il est le seul propriétaire de l'agrégat `Restaurant`. Les autres services ne conservent que les champs dont ils ont besoin.

## Service Commande

**Responsabilité :** construire, calculer et valider une commande.

- Recevoir un catalogue minimal répliqué depuis Restaurant.
- Créer un panier pour un client et un restaurant.
- Ajouter et retirer des lignes.
- Figer dans la ligne le nom et le prix affichés au client.
- Calculer le total et valider ou annuler la commande.

Il est le seul propriétaire de l'agrégat `Commande`. Une commande validée est un fait historique : une modification ultérieure du menu ne change ni ses lignes ni son total.

## Service Livraison

**Responsabilité :** organiser et suivre l'acheminement d'une commande validée.

- Créer une livraison de manière idempotente à la réception de `CommandeValidee`.
- Conserver le point de collecte et la destination nécessaires.
- Affecter un livreur.
- Faire évoluer le statut de `EN_PREPARATION` à `EN_ROUTE`, puis à `LIVREE`.
- Enregistrer un éventuel pourboire.

Il est le seul propriétaire de l'agrégat `Livraison`. Il n'a pas besoin d'appeler Commande pour afficher le trajet en cours, car les données utiles ont été copiées dans son propre stockage.

## Service Suivi

**Responsabilité :** exposer une vue de lecture simple et rapide au client.

- Créer une projection lors de la validation d'une commande.
- Ajouter les informations de livraison lorsqu'elles deviennent disponibles.
- Traduire un statut technique en libellé compréhensible.
- Construire une chronologie des étapes.

Ce service est nouveau à l'étape 5. Il ne porte pas de règle transactionnelle sur la commande ou la livraison : sa donnée peut être reconstruite en rejouant les événements.

## Ce qui reste volontairement hors périmètre

Le paiement réel, l'authentification, la géolocalisation temps réel, l'optimisation des tournées et les notifications externes ne sont pas nécessaires pour démontrer le découpage, la réplication et la projection demandés.
