// Requêtes de démonstration sur la base du service Restaurant (MongoDB).
// Exécution : ./mongodb/run-queries.sh                      (niveau 2 : base tastigo_restaurant)
//        ou : niveau1/run.sh                                (niveau 1 : base tastigo_niveau1)
// La base peut être choisie avec : mongosh --eval 'var base = "tastigo_niveau1"' requetes.js

db = db.getSiblingDB(typeof base === "undefined" ? "tastigo_restaurant" : base);
print("Base interrogée : " + db.getName());

function titre(texte) {
  print("\n=== " + texte);
}

titre("1. Restaurants publiés à Paris (index statut_ville)");
db.restaurants
  .find(
    { statut: "PUBLIE", "adresse.ville": "Paris" },
    { _id: 0, restaurantId: 1, nom: 1, "adresse.ligne1": 1, version: 1 }
  )
  .sort({ restaurantId: 1 })
  .forEach(printjson);

titre("2. Menu disponible de rest_42, du moins cher au plus cher ($unwind)");
db.restaurants
  .aggregate([
    { $match: { restaurantId: "rest_42" } },
    { $unwind: "$plats" },
    { $match: { "plats.disponible": true } },
    { $project: { _id: 0, platId: "$plats.platId", nom: "$plats.nom", prixCentimes: "$plats.prix.montant" } },
    { $sort: { prixCentimes: 1 } }
  ])
  .forEach(printjson);

titre("3. Recherche plein texte « falafel » dans les plats (index texte)");
db.restaurants
  .find(
    { $text: { $search: "falafel" } },
    { _id: 0, restaurantId: 1, nom: 1, score: { $meta: "textScore" } }
  )
  .sort({ score: { $meta: "textScore" } })
  .forEach(printjson);

titre("4. Plats indisponibles (filtre sur un tableau avec $elemMatch)");
db.restaurants
  .find(
    { plats: { $elemMatch: { disponible: false } } },
    { _id: 0, restaurantId: 1, nom: 1, "plats.$": 1 }
  )
  .forEach(printjson);

titre("5. Nombre de restaurants par ville et par statut ($group)");
db.restaurants
  .aggregate([
    { $group: { _id: { ville: "$adresse.ville", statut: "$statut" }, nombre: { $sum: 1 } } },
    { $project: { _id: 0, ville: "$_id.ville", statut: "$_id.statut", nombre: 1 } },
    { $sort: { ville: 1, statut: 1 } }
  ])
  .forEach(printjson);

titre("6. Prix moyen, minimum et maximum par restaurant");
db.restaurants
  .aggregate([
    { $unwind: "$plats" },
    {
      $group: {
        _id: "$restaurantId",
        nom: { $first: "$nom" },
        nombrePlats: { $sum: 1 },
        prixMoyen: { $avg: "$plats.prix.montant" },
        prixMin: { $min: "$plats.prix.montant" },
        prixMax: { $max: "$plats.prix.montant" }
      }
    },
    { $project: { _id: 0, restaurantId: "$_id", nom: 1, nombrePlats: 1, prixMoyen: { $round: ["$prixMoyen", 0] }, prixMin: 1, prixMax: 1 } },
    { $sort: { restaurantId: 1 } }
  ])
  .forEach(printjson);

titre("7. Outbox : événements par type et état de publication");
db.outbox
  .aggregate([
    { $group: { _id: { type: "$eventType", publie: "$publie" }, nombre: { $sum: 1 } } },
    { $project: { _id: 0, eventType: "$_id.type", publie: "$_id.publie", nombre: 1 } },
    { $sort: { eventType: 1 } }
  ])
  .forEach(printjson);

titre("8. Historique des événements de rest_42 (index par_agregat)");
db.outbox
  .find(
    { aggregateId: "rest_42" },
    { _id: 0, aggregateVersion: 1, eventType: 1, "modification.donneeAgregatModifiee": 1, "modification.nouvelleValeur": 1, publie: 1 }
  )
  .sort({ aggregateVersion: 1 })
  .forEach(printjson);

titre("9. Événements encore à publier (doit être vide quand le relais tourne)");
print(db.outbox.countDocuments({ publie: false }) + " événement(s) en attente");

titre("10. Plan d'exécution de la recherche par identifiant");
const plan = db.restaurants.find({ restaurantId: "rest_42" }).explain("executionStats");
printjson({
  etape: plan.queryPlanner.winningPlan.stage,
  index: plan.queryPlanner.winningPlan.indexName || (plan.queryPlanner.winningPlan.inputStage || {}).indexName,
  documentsExamines: plan.executionStats.totalDocsExamined,
  documentsRetournes: plan.executionStats.nReturned
});

titre("11. Validation du schéma : un prix négatif est refusé");
try {
  db.restaurants.updateOne({ restaurantId: "rest_42" }, { $set: { "plats.0.prix.montant": -5 } });
  print("ERREUR : la mise à jour aurait dû être refusée");
} catch (e) {
  print("refusé par le validateur (code " + e.code + ") : " + e.message);
}
