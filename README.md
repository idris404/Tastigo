# Application de livraison de repas

L'idée est de faire une petite appli de livraison de repas, un peu sur le principe d'Uber Eats mais en beaucoup plus simple. Un client peut voir les restaurants disponibles, regarder ce qu'ils proposent, passer commande et suivre sa livraison.

## Organisation du projet

L'application est séparée en trois services :

- **restaurant** : gère la liste des restaurants et les plats qu'ils proposent (nom, adresse, horaires, menu, prix)
- **commande** : gère les commandes passées par les clients (plats choisis, montant total, validation)
- **livraison** : gère le suivi de la livraison une fois la commande validée (en préparation, en route, livrée)

Chaque service a sa propre API et ils communiquent entre eux en REST.
