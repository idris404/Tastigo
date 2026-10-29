db = db.getSiblingDB("tastigo_restaurant");

db.restaurants.drop();
db.outbox.drop();

db.createCollection("restaurants", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["restaurantId", "nom", "adresse", "horaires", "statut", "plats", "version"],
      properties: {
        restaurantId: { bsonType: "string" },
        nom: { bsonType: "string", minLength: 1 },
        telephone: { bsonType: "string" },
        adresse: {
          bsonType: "object",
          required: ["ligne1", "codePostal", "ville"]
        },
        horaires: { bsonType: "array", minItems: 1 },
        statut: { enum: ["BROUILLON", "PUBLIE", "INDISPONIBLE"] },
        plats: {
          bsonType: "array",
          minItems: 1,
          items: {
            bsonType: "object",
            required: ["platId", "nom", "prix", "disponible"],
            properties: {
              platId: { bsonType: "string" },
              nom: { bsonType: "string", minLength: 1 },
              prix: {
                bsonType: "object",
                required: ["montant", "devise"],
                properties: {
                  montant: { bsonType: ["int", "long"], minimum: 1 },
                  devise: { enum: ["EUR"] }
                }
              },
              disponible: { bsonType: "bool" }
            }
          }
        },
        version: { bsonType: ["int", "long"], minimum: 1 }
      }
    }
  }
});

db.restaurants.createIndex({ restaurantId: 1 }, { unique: true });
db.restaurants.createIndex({ statut: 1, "adresse.ville": 1 });
db.restaurants.createIndex({ "plats.nom": "text" });

db.restaurants.insertMany([
  {
    restaurantId: "rest_42",
    nom: "Le Bistrot Vert",
    telephone: "+33142000000",
    adresse: { ligne1: "12 rue des Lilas", codePostal: "75011", ville: "Paris" },
    horaires: [
      { jour: "LUNDI", ouverture: "11:30", fermeture: "22:30" },
      { jour: "MARDI", ouverture: "11:30", fermeture: "22:30" }
    ],
    statut: "PUBLIE",
    plats: [
      {
        platId: "plat_7",
        nom: "Bowl falafel",
        prix: { montant: NumberInt(1290), devise: "EUR" },
        disponible: true
      },
      {
        platId: "plat_8",
        nom: "Salade grecque",
        prix: { montant: NumberInt(1090), devise: "EUR" },
        disponible: true
      }
    ],
    version: NumberInt(3)
  },
  {
    restaurantId: "rest_51",
    nom: "Pasta Roma",
    telephone: "+33143000000",
    adresse: { ligne1: "8 avenue Parmentier", codePostal: "75011", ville: "Paris" },
    horaires: [
      { jour: "LUNDI", ouverture: "12:00", fermeture: "23:00" }
    ],
    statut: "INDISPONIBLE",
    plats: [
      {
        platId: "plat_21",
        nom: "Penne arrabbiata",
        prix: { montant: NumberInt(1390), devise: "EUR" },
        disponible: false
      }
    ],
    version: NumberInt(1)
  }
]);

db.createCollection("outbox", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["eventId", "eventType", "aggregateId", "aggregateVersion", "payload", "publie"],
      properties: {
        eventId: { bsonType: "string" },
        eventType: { bsonType: "string" },
        aggregateId: { bsonType: "string" },
        aggregateVersion: { bsonType: ["int", "long"] },
        payload: { bsonType: "object" },
        publie: { bsonType: "bool" }
      }
    }
  }
});

db.outbox.createIndex({ eventId: 1 }, { unique: true });
db.outbox.createIndex({ publie: 1, occurredAt: 1 });
db.outbox.insertOne({
  eventId: "evt_restaurant_publie_42_v3",
  eventType: "RestaurantPublie",
  eventVersion: NumberInt(1),
  occurredAt: ISODate("2026-10-07T10:00:00Z"),
  aggregateId: "rest_42",
  aggregateVersion: NumberInt(3),
  emetteur: "restaurant",
  recepteur: "commande",
  payload: {
    restaurantId: "rest_42",
    nom: "Le Bistrot Vert",
    statut: "PUBLIE",
    plats: [
      {
        platId: "plat_7",
        nom: "Bowl falafel",
        prix: { montant: NumberInt(1290), devise: "EUR" },
        disponible: true
      }
    ]
  },
  publie: false
});

print("MongoDB initialise : 2 restaurants et 1 evenement dans l'outbox.");
