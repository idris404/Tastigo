Application de livraison de repas

L'idée est de faire une petite appli de livraison de repas, un peu sur le principe d'Uber Eats mais en beaucoup plus simple. Un client peut voir les restaurants disponibles, regarder ce qu'ils proposent, passer commande et suivre sa livraison.

Organisation du projet

L'application est séparée en trois services :

restaurant : gère la liste des restaurants (nom, adresse, horaires, ouvert ou fermé)

catalogue : gère les plats proposés par chaque restaurant, avec leur prix et leur disponibilité

livraison : gère les commandes et leur statut (en préparation, en route, livrée)

Chaque service a sa propre API et ils communiquent entre eux en REST.
