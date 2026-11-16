"""Jeu de données initial du service Restaurant.

Les restaurants sont créés en passant par les commandes du service (et non par une
insertion brute) : les événements correspondants sont donc écrits dans l'outbox et le
réplica du service Commande est construit exactement comme en fonctionnement normal.
"""

SEMAINE = ["LUNDI", "MARDI", "MERCREDI", "JEUDI", "VENDREDI"]

RESTAURANTS = [
    {
        "restaurant": {
            "restaurantId": "rest_42",
            "nom": "Le Bistrot Vert",
            "telephone": "+33142000000",
            "adresse": {"ligne1": "12 rue des Lilas", "codePostal": "75011", "ville": "Paris"},
            "horaires": [{"jour": j, "ouverture": "11:30", "fermeture": "22:30"} for j in SEMAINE],
            "plats": [
                {"platId": "plat_7", "nom": "Bowl falafel", "categorie": "Plat", "prix": {"montant": 1250}},
                {"platId": "plat_8", "nom": "Salade grecque", "categorie": "Plat", "prix": {"montant": 1090}},
                {"platId": "plat_9", "nom": "Houmous maison", "categorie": "Entrée", "prix": {"montant": 650}},
            ],
        },
        # Publié en version 2, puis le prix du bowl passe de 12,50 € à 12,90 € (version 3).
        "ensuite": [("publier",), ("prix", "plat_7", 1290)],
    },
    {
        "restaurant": {
            "restaurantId": "rest_51",
            "nom": "Pasta Roma",
            "telephone": "+33143000000",
            "adresse": {"ligne1": "27 rue Oberkampf", "codePostal": "75011", "ville": "Paris"},
            "horaires": [{"jour": j, "ouverture": "12:00", "fermeture": "23:00"} for j in SEMAINE + ["SAMEDI"]],
            "plats": [
                {"platId": "plat_21", "nom": "Penne arrabbiata", "categorie": "Plat", "prix": {"montant": 1390}},
                {"platId": "plat_22", "nom": "Lasagnes maison", "categorie": "Plat", "prix": {"montant": 1490}},
                {"platId": "plat_23", "nom": "Tiramisu", "categorie": "Dessert", "prix": {"montant": 690}},
            ],
        },
        # Publié, puis les penne deviennent indisponibles.
        "ensuite": [("publier",), ("disponibilite", "plat_21", False)],
    },
    {
        "restaurant": {
            "restaurantId": "rest_63",
            "nom": "Sakura Sushi",
            "telephone": "+33478000000",
            "adresse": {"ligne1": "5 rue Mercière", "codePostal": "69002", "ville": "Lyon"},
            "horaires": [{"jour": j, "ouverture": "11:00", "fermeture": "22:00"} for j in SEMAINE[1:] + ["SAMEDI", "DIMANCHE"]],
            "plats": [
                {"platId": "plat_31", "nom": "Plateau maki", "categorie": "Plat", "prix": {"montant": 1590}},
                {"platId": "plat_32", "nom": "Soupe miso", "categorie": "Entrée", "prix": {"montant": 450}},
            ],
        },
        # Publié, puis temporairement fermé.
        "ensuite": [("publier",), ("statut", "INDISPONIBLE")],
    },
    {
        "restaurant": {
            "restaurantId": "rest_77",
            "nom": "Burger Lab",
            "telephone": "+33140000000",
            "adresse": {"ligne1": "3 rue du Faubourg Saint-Denis", "codePostal": "75010", "ville": "Paris"},
            "horaires": [{"jour": "VENDREDI", "ouverture": "18:00", "fermeture": "23:30"}],
            "plats": [
                {"platId": "plat_41", "nom": "Burger classique", "categorie": "Plat", "prix": {"montant": 1190}},
            ],
        },
        # Reste en BROUILLON : il n'est donc jamais répliqué dans Commande.
        "ensuite": [],
    },
]
