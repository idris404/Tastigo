// NIVEAU 1 - Remplissage de la base MongoDB du service Restaurant, sans service programmé.
// Base dédiée : tastigo_niveau1 (n'interfère pas avec tastigo_restaurant du niveau 2).
// Les documents et les événements de l'outbox sont ceux produits par le niveau 2
// (mêmes eventId que dans Events.json).

db = db.getSiblingDB("tastigo_niveau1");

db.restaurants.drop();
db.outbox.drop();

const prix = {
  bsonType: "object",
  required: ["montant", "devise"],
  properties: { montant: { bsonType: ["int", "long"], minimum: 1 }, devise: { enum: ["EUR"] } }
};
const adresse = {
  bsonType: "object",
  required: ["ligne1", "codePostal", "ville"],
  properties: { codePostal: { bsonType: "string", pattern: "^[0-9]{5}$" } }
};

db.createCollection("restaurants", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["restaurantId", "nom", "adresse", "horaires", "statut", "plats", "version"],
      properties: {
        restaurantId: { bsonType: "string", pattern: "^rest_" },
        nom: { bsonType: "string", minLength: 1 },
        adresse: adresse,
        horaires: { bsonType: "array" },
        statut: { enum: ["BROUILLON", "PUBLIE", "INDISPONIBLE"] },
        plats: {
          bsonType: "array",
          items: {
            bsonType: "object",
            required: ["platId", "nom", "prix", "disponible"],
            properties: { prix: prix, disponible: { bsonType: "bool" } }
          }
        },
        version: { bsonType: ["int", "long"], minimum: 1 }
      }
    }
  }
});
db.createCollection("outbox", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["eventId", "eventType", "emetteur", "recepteur", "aggregateId", "aggregateVersion", "modification", "publie"],
      properties: { publie: { bsonType: "bool" }, aggregateVersion: { bsonType: ["int", "long"], minimum: 1 } }
    }
  }
});

db.restaurants.createIndex({ restaurantId: 1 }, { unique: true, name: "restaurantId_unique" });
db.restaurants.createIndex({ statut: 1, "adresse.ville": 1 }, { name: "statut_ville" });
db.restaurants.createIndex({ "plats.nom": "text", nom: "text" }, { default_language: "french", name: "texte_plats" });
db.outbox.createIndex({ eventId: 1 }, { unique: true, name: "eventId_unique" });
db.outbox.createIndex({ publie: 1, _id: 1 }, { name: "a_publier" });
db.outbox.createIndex({ aggregateId: 1, aggregateVersion: 1 }, { name: "par_agregat" });

// ------------------------------------------------------------------ restaurants
const semaine = ["LUNDI", "MARDI", "MERCREDI", "JEUDI", "VENDREDI"];
const horaires = (jours, ouverture, fermeture) => jours.map((jour) => ({ jour, ouverture, fermeture }));
const plat = (platId, nom, categorie, montant, disponible = true) => ({
  platId, nom, categorie, prix: { montant: NumberInt(montant), devise: "EUR" }, disponible
});

const bistrot = {
  restaurantId: "rest_42", nom: "Le Bistrot Vert", telephone: "+33142000000",
  adresse: { ligne1: "12 rue des Lilas", codePostal: "75011", ville: "Paris" },
  horaires: horaires(semaine, "11:30", "22:30"), statut: "PUBLIE",
  plats: [plat("plat_7", "Bowl falafel", "Plat", 1290), plat("plat_8", "Salade grecque", "Plat", 1090), plat("plat_9", "Houmous maison", "Entrée", 650)],
  version: NumberInt(3)
};
const pasta = {
  restaurantId: "rest_51", nom: "Pasta Roma", telephone: "+33143000000",
  adresse: { ligne1: "27 rue Oberkampf", codePostal: "75011", ville: "Paris" },
  horaires: horaires(semaine.concat(["SAMEDI"]), "12:00", "23:00"), statut: "PUBLIE",
  plats: [plat("plat_21", "Penne arrabbiata", "Plat", 1390, false), plat("plat_22", "Lasagnes maison", "Plat", 1490), plat("plat_23", "Tiramisu", "Dessert", 690)],
  version: NumberInt(3)
};
const sakura = {
  restaurantId: "rest_63", nom: "Sakura Sushi", telephone: "+33478000000",
  adresse: { ligne1: "5 rue Mercière", codePostal: "69002", ville: "Lyon" },
  horaires: horaires(["MARDI", "MERCREDI", "JEUDI", "VENDREDI", "SAMEDI", "DIMANCHE"], "11:00", "22:00"), statut: "INDISPONIBLE",
  plats: [plat("plat_31", "Plateau maki", "Plat", 1590), plat("plat_32", "Soupe miso", "Entrée", 450)],
  version: NumberInt(3)
};
const burger = {
  restaurantId: "rest_77", nom: "Burger Lab", telephone: "+33140000000",
  adresse: { ligne1: "3 rue du Faubourg Saint-Denis", codePostal: "75010", ville: "Paris" },
  horaires: horaires(["VENDREDI"], "18:00", "23:30"), statut: "BROUILLON",
  plats: [plat("plat_41", "Burger classique", "Plat", 1190)],
  version: NumberInt(1)
};
db.restaurants.insertMany([bistrot, pasta, sakura, burger]);

// ------------------------------------------------------------------ outbox
// Snapshot envoyé au service Commande lors de la publication (version 2).
function catalogue(r, modifs) {
  const plats = r.plats.map((p) => ({ platId: p.platId, nom: p.nom, prix: p.prix, disponible: p.disponible }));
  return Object.assign(
    { restaurantId: r.restaurantId, nom: r.nom, telephone: r.telephone, adresse: r.adresse, statut: "PUBLIE", plats: plats },
    modifs || {}
  );
}
function evenement(eventId, eventType, aggregateId, version, occurredAt, operation, donnee, cible, ancienne, nouvelle) {
  return {
    eventId, eventType, eventVersion: NumberInt(1), occurredAt, correlationId: "corr_" + aggregateId,
    emetteur: "restaurant", recepteur: "commande", aggregateId, aggregateVersion: NumberInt(version),
    operationReplica: operation,
    modification: { donneeAgregatModifiee: donnee, cible, ancienneValeur: ancienne, nouvelleValeur: nouvelle },
    publie: false, creeLe: new Date(occurredAt)
  };
}
const eur = (montant) => ({ montant: NumberInt(montant), devise: "EUR" });

const snapBistrot = catalogue(bistrot);
snapBistrot.plats[0].prix = eur(1250); // prix avant ModifierPrixPlat
const snapPasta = catalogue(pasta);
snapPasta.plats[0].disponible = true; // disponible avant ChangerDisponibilitePlat

db.outbox.insertMany([
  evenement("evt_ded987e8ada840a88c21", "RestaurantPublie", "rest_42", 2, "2026-11-16T14:57:54.883Z", "CREER",
    "catalogueRestaurants[rest_42]", { restaurantId: "rest_42" }, null, snapBistrot),
  evenement("evt_f9877b64aa5942e98e08", "MenuMisAJour", "rest_42", 3, "2026-11-16T14:57:54.889Z", "METTRE_A_JOUR",
    "catalogueRestaurants[rest_42].plats[plat_7].prix", { restaurantId: "rest_42", platId: "plat_7", champ: "prix" }, eur(1250), eur(1290)),
  evenement("evt_3cb1c9b34bc448feb433", "RestaurantPublie", "rest_51", 2, "2026-11-16T14:57:54.901Z", "CREER",
    "catalogueRestaurants[rest_51]", { restaurantId: "rest_51" }, null, snapPasta),
  evenement("evt_5f162f64dafc4e94b1de", "MenuMisAJour", "rest_51", 3, "2026-11-16T14:57:54.907Z", "METTRE_A_JOUR",
    "catalogueRestaurants[rest_51].plats[plat_21].disponible", { restaurantId: "rest_51", platId: "plat_21", champ: "disponible" }, true, false),
  evenement("evt_3351628866af4f9e8d20", "RestaurantPublie", "rest_63", 2, "2026-11-16T14:57:54.918Z", "CREER",
    "catalogueRestaurants[rest_63]", { restaurantId: "rest_63" }, null, catalogue(sakura)),
  evenement("evt_52bcc94d65704bcaa91f", "StatutRestaurantModifie", "rest_63", 3, "2026-11-16T14:57:54.923Z", "METTRE_A_JOUR",
    "catalogueRestaurants[rest_63].statut", { restaurantId: "rest_63" }, "PUBLIE", "INDISPONIBLE")
]);

print("MongoDB tastigo_niveau1 : " + db.restaurants.countDocuments() + " restaurants, " +
  db.outbox.countDocuments({ publie: false }) + " événements en attente dans l'outbox");
