db = db.getSiblingDB("tastigo_restaurant");

print("\n1. Restaurants publies a Paris");
db.restaurants.find(
  { statut: "PUBLIE", "adresse.ville": "Paris" },
  { _id: 0, restaurantId: 1, nom: 1, "adresse.ville": 1 }
).forEach(printjson);

print("\n2. Menu disponible du restaurant rest_42");
db.restaurants.aggregate([
  { $match: { restaurantId: "rest_42" } },
  { $unwind: "$plats" },
  { $match: { "plats.disponible": true } },
  {
    $project: {
      _id: 0,
      restaurantId: 1,
      nomRestaurant: "$nom",
      platId: "$plats.platId",
      nomPlat: "$plats.nom",
      prix: "$plats.prix"
    }
  }
]).forEach(printjson);

print("\n3. Evenements non publies a envoyer au service Commande");
db.outbox.find(
  { publie: false, recepteur: "commande" },
  { _id: 0 }
).sort({ occurredAt: 1 }).forEach(printjson);

print("\n4. Nombre de restaurants par statut");
db.restaurants.aggregate([
  { $group: { _id: "$statut", nombre: { $sum: 1 } } },
  { $sort: { _id: 1 } }
]).forEach(printjson);
