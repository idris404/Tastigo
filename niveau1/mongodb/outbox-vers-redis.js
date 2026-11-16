// NIVEAU 1 - Relais de l'outbox MongoDB vers Redis, sans service programmé.
// Ce script lit les événements non publiés de tastigo_niveau1.outbox, dans l'ordre, et
// AFFICHE les commandes redis-cli qui :
//   1. publient l'événement sur le flux du bus  (DB 15, evenements:vers:commande) ;
//   2. l'appliquent au réplica du service Commande (DB 12) dans un bloc MULTI/EXEC,
//      avec l'eventId ajouté au SET evenements:traites (idempotence).
// Il marque ensuite l'événement comme publié dans MongoDB.
// Usage : mongosh --quiet outbox-vers-redis.js | redis-cli

db = db.getSiblingDB("tastigo_niveau1");

const BUS = 15;
const COMMANDE = 12;
const q = (valeur) => JSON.stringify(String(valeur)); // chaîne entre guillemets lisible par redis-cli

function champsPlat(rid, p) {
  return [
    `SADD catalogue:restaurant:${rid}:plats ${p.platId}`,
    `HSET catalogue:plat:${rid}:${p.platId} platId ${p.platId} nom ${q(p.nom)} prixMontant ${p.prix.montant} ` +
      `prixDevise ${p.prix.devise} disponible ${p.disponible}`
  ];
}

function appliquer(evt) {
  const m = evt.modification;
  const rid = evt.aggregateId;
  const v = evt.aggregateVersion;
  const lignes = [];
  if (evt.eventType === "RestaurantPublie") {
    const r = m.nouvelleValeur;
    lignes.push(
      `HSET catalogue:restaurant:${rid} restaurantId ${rid} nom ${q(r.nom)} telephone ${q(r.telephone)} statut ${r.statut} ` +
        `adresse.ligne1 ${q(r.adresse.ligne1)} adresse.codePostal ${r.adresse.codePostal} adresse.ville ${q(r.adresse.ville)} ` +
        `sourceVersion ${v} misAJourLe ${evt.occurredAt}`,
      `SADD catalogue:restaurants ${rid}`
    );
    r.plats.forEach((p) => lignes.push(...champsPlat(rid, p)));
  } else if (evt.eventType === "MenuMisAJour") {
    const cle = `catalogue:plat:${rid}:${m.cible.platId}`;
    if (m.cible.champ === "prix") lignes.push(`HSET ${cle} prixMontant ${m.nouvelleValeur.montant} prixDevise ${m.nouvelleValeur.devise}`);
    else if (m.cible.champ === "disponible") lignes.push(`HSET ${cle} disponible ${m.nouvelleValeur}`);
    else lignes.push(...champsPlat(rid, m.nouvelleValeur));
    lignes.push(`HSET catalogue:restaurant:${rid} sourceVersion ${v} misAJourLe ${evt.occurredAt}`);
  } else if (evt.eventType === "StatutRestaurantModifie") {
    lignes.push(`HSET catalogue:restaurant:${rid} statut ${m.nouvelleValeur} sourceVersion ${v} misAJourLe ${evt.occurredAt}`);
  }
  return lignes;
}

db.outbox.find({ publie: false }).sort({ occurredAt: 1 }).forEach((doc) => {
  const evt = Object.assign({}, doc);
  delete evt._id; delete evt.publie; delete evt.creeLe;
  print(`SELECT ${BUS}`);
  print(`XADD evenements:vers:${evt.recepteur} * eventId ${evt.eventId} eventType ${evt.eventType} ` +
    `aggregateId ${evt.aggregateId} aggregateVersion ${evt.aggregateVersion} event ${q(EJSON.stringify(evt, { relaxed: true }))}`);
  print(`SELECT ${COMMANDE}`);
  print("MULTI");
  appliquer(evt).forEach((ligne) => print(ligne));
  print(`SADD evenements:traites ${evt.eventId}`);
  print("EXEC");
  db.outbox.updateOne({ _id: doc._id }, { $set: { publie: true, publieLe: new Date() } });
});
