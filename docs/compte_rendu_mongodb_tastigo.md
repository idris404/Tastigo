# Compte rendu — TP MongoDB adapté à Tastigo

**Base utilisée pour les manipulations : `tastigo_training`**  
**Projet : Tastigo — livraison de repas**  
**Date : 29 octobre 2026**  
**Environnement : MongoDB 8.0.34, mongosh 2.6.0, Docker**

## Contexte

Nous avons adapté les exercices du TP MongoDB à notre projet Tastigo. **Nous utilisons notre base d’exercice `tastigo_training`, et non `rental_training`, la base du sujet initial.** Les collections manipulées sont `restaurants`, `commandes` et `livraisons`.

Les documents métier sont issus de notre fichier `Aggregates.json`. Le changement d’adresse est prévu dans `Events.json`. L’horaire du mardi et le livreur `livreur_test_1` sont des données de test utilisées pour les exercices sur les tableaux et la transition de livraison.

Chaque opération ci-dessous présente la **requête complète**, son **résultat exact** extrait de la transcription, puis son **analyse**. Le bloc « Requête complète » contient tout le code à exécuter, jusqu’à sa dernière parenthèse ; le bloc « Résultat exact » contient uniquement la sortie renvoyée par MongoDB. Les erreurs de saisie, les tentatives hors sujet et les répétitions sans intérêt ont été retirées. Le test de doublon E11000 est conservé : son refus est explicitement demandé dans la partie F du TP.

## Partie A — Documents Tastigo et types BSON

### Insertion du restaurant

**Requête complète :**

```javascript
db.restaurants.insertOne({
  type: "Restaurant",
  restaurantId: "rest_42",
  nom: "Le Bistrot Vert",
  telephone: "+33142000000",
  adresse: {
    ligne1: "12 rue des Lilas",
    codePostal: "75011",
    ville: "Paris"
  },
  horaires: [
    {
      jour: "LUNDI",
      ouverture: "11:30",
      fermeture: "22:30"
    }
  ],
  statut: "PUBLIE",
  plats: [
    {
      platId: "plat_7",
      nom: "Bowl falafel",
      prix: {
        montant: 1290,
        devise: "EUR"
      },
      disponible: true
    }
  ],
  version: 3
})
```

**Résultat exact :**

```text
{
  acknowledged: true,
  insertedId: ObjectId('6ae31b97fd9bd6b6168ce5b0')
}
```

**Analyse :**

L’insertion du restaurant dans notre base `tastigo_training` a été acceptée : `acknowledged: true` confirme l’écriture. MongoDB a généré l’identifiant `_id` indiqué dans `insertedId`. Le document regroupe les informations du restaurant, son adresse, ses horaires et ses plats. Le Bowl falafel est disponible au prix de 1 290 centimes, soit 12,90 €. La version du restaurant est 3.

### Lecture du restaurant

**Requête complète :**

```javascript
db.restaurants.findOne({ restaurantId: "rest_42" })
```

**Résultat exact :**

```text
{
  _id: ObjectId('6ae31b97fd9bd6b6168ce5b0'),
  type: 'Restaurant',
  restaurantId: 'rest_42',
  nom: 'Le Bistrot Vert',
  telephone: '+33142000000',
  adresse: { ligne1: '12 rue des Lilas', codePostal: '75011', ville: 'Paris' },
  horaires: [ { jour: 'LUNDI', ouverture: '11:30', fermeture: '22:30' } ],
  statut: 'PUBLIE',
  plats: [
    {
      platId: 'plat_7',
      nom: 'Bowl falafel',
      prix: { montant: 1290, devise: 'EUR' },
      disponible: true
    }
  ],
  version: 3
}
```

**Analyse :**

Le restaurant rest_42 est présent dans notre base tastigo_training. Son adresse est imbriquée, ses horaires et ses plats sont des tableaux. Le plat coûte 1 290 centimes, soit 12,90 €. Le statut est PUBLIE et la version vaut 3.

### Insertion de la commande

**Requête complète :**

```javascript
db.commandes.insertOne({
  type: "Commande",
  commandeId: "cmd_1001",
  client: {
    clientId: "cli_18",
    nom: "Camille Martin",
    telephone: "+33612000000",
    adresseLivraison: {
      ligne1: "8 avenue Parmentier",
      codePostal: "75011",
      ville: "Paris"
    }
  },
  restaurantId: "rest_42",
  lignes: [
    {
      ligneId: "ligne_1",
      platId: "plat_7",
      nomPlat: "Bowl falafel",
      prixUnitaire: {
        montant: 1290,
        devise: "EUR"
      },
      quantite: 2
    }
  ],
  total: {
    montant: 2580,
    devise: "EUR"
  },
  statut: "VALIDEE",
  valideeLe: ISODate("2026-10-07T10:15:00Z"),
  version: 2
})
```

**Résultat exact :**

```text
{
  acknowledged: true,
  insertedId: ObjectId('6ae31c27fd9bd6b6168ce5b1')
}
```

**Analyse :**

acknowledged: true confirme la prise en compte de l’écriture ; insertedId indique l’identifiant créé. La commande cmd_1001 contient deux bowls à 1 290 centimes, pour un total de 2 580 centimes, soit 25,80 €. Sa version initiale vaut 2. ISODate stocke la date de validation avec un type date BSON.

### Insertion de la livraison

**Requête complète :**

```javascript
db.livraisons.insertOne({
  type: "Livraison",
  livraisonId: "liv_501",
  commandeId: "cmd_1001",
  statut: "EN_PREPARATION",
  livreur: null,
  pourboire: null,
  collecte: {
    restaurantId: "rest_42",
    nom: "Le Bistrot Vert",
    telephone: "+33142000000",
    adresse: {
      ligne1: "12 rue des Lilas",
      codePostal: "75011",
      ville: "Paris"
    }
  },
  destination: {
    clientId: "cli_18",
    nom: "Camille Martin",
    telephone: "+33612000000",
    adresse: {
      ligne1: "8 avenue Parmentier",
      codePostal: "75011",
      ville: "Paris"
    }
  },
  creeLe: ISODate("2026-10-07T10:15:02Z"),
  version: 1
})
```

**Résultat exact :**

```text
{
  acknowledged: true,
  insertedId: ObjectId('6ae31c7bfd9bd6b6168ce5b2')
}
```

**Analyse :**

La livraison liv_501 a été insérée. Elle fait référence à cmd_1001, contient les informations de collecte et de destination et démarre en EN_PREPARATION, sans livreur, à la version 1. L’insertion ne crée aucun événement Redis.

### Affichage des collections

**Requête complète :**

```javascript
show collections
```

**Résultat exact :**

```text
commandes
livraisons
restaurants
```

**Analyse :**

Notre base tastigo_training contient les trois collections métier affichées : commandes, livraisons et restaurants.

### Analyse des types BSON

| Champ ou structure | Type et rôle |
|---|---|
| `_id` | ObjectId généré par MongoDB pour identifier le document |
| `commandeId`, `restaurantId`, `livraisonId` | Identifiants métier sous forme de chaînes |
| `client`, `adresse`, `prix`, `total` | Documents imbriqués |
| `horaires`, `plats`, `lignes` | Tableaux de documents |
| `valideeLe`, `creeLe` | Dates BSON créées avec `ISODate(...)` |
| `disponible` | Booléen |
| `livreur: null` | Aucun livreur affecté au départ |
| `total.montant` | Montant numérique en centimes |

Les types influencent les comparaisons et les calculs : une date BSON n’est pas une chaîne de caractères et un montant numérique n’est pas un texte. Nous conservons les montants en centimes conformément à Tastigo : 2 580 centimes correspondent à 25,80 €.

## Partie B — Vérification du nombre de commandes

### Comptage correct des commandes

**Requête complète :**

```javascript
db.commandes.countDocuments({})
```

**Résultat exact :**

```text
1
```

**Analyse :**

Le résultat 1 confirme qu’une seule commande est enregistrée. Les commandes supplémentaires suggérées pendant l’accompagnement n’ont pas été insérées dans la transcription fournie.

La transcription contient une commande dans cette collection. L’insertion multiple avec `insertMany()` demandée dans le sujet initial n’est pas présentée comme réalisée.

## Partie C — Recherches et projection de champs

### Recherche des commandes validées

**Requête complète :**

```javascript
db.commandes.find({ statut: "VALIDEE" })
```

**Résultat exact :**

```text
[
  {
    _id: ObjectId('6ae31c27fd9bd6b6168ce5b1'),
    type: 'Commande',
    commandeId: 'cmd_1001',
    client: {
      clientId: 'cli_18',
      nom: 'Camille Martin',
      telephone: '+33612000000',
      adresseLivraison: { ligne1: '8 avenue Parmentier', codePostal: '75011', ville: 'Paris' }
    },
    restaurantId: 'rest_42',
    lignes: [
      {
        ligneId: 'ligne_1',
        platId: 'plat_7',
        nomPlat: 'Bowl falafel',
        prixUnitaire: { montant: 1290, devise: 'EUR' },
        quantite: 2
      }
    ],
    total: { montant: 2580, devise: 'EUR' },
    statut: 'VALIDEE',
    valideeLe: ISODate('2026-10-07T10:15:00.000Z'),
    version: 2
  }
]
```

**Analyse :**

Le filtre sur VALIDEE retrouve cmd_1001. Cette recherche permet de consulter les commandes ayant ce statut.

### Recherche des commandes du client

**Requête complète :**

```javascript
db.commandes.find({ "client.clientId": "cli_18" })
```

**Résultat exact :**

```text
[
  {
    _id: ObjectId('6ae31c27fd9bd6b6168ce5b1'),
    type: 'Commande',
    commandeId: 'cmd_1001',
    client: {
      clientId: 'cli_18',
      nom: 'Camille Martin',
      telephone: '+33612000000',
      adresseLivraison: { ligne1: '8 avenue Parmentier', codePostal: '75011', ville: 'Paris' }
    },
    restaurantId: 'rest_42',
    lignes: [
      {
        ligneId: 'ligne_1',
        platId: 'plat_7',
        nomPlat: 'Bowl falafel',
        prixUnitaire: { montant: 1290, devise: 'EUR' },
        quantite: 2
      }
    ],
    total: { montant: 2580, devise: 'EUR' },
    statut: 'VALIDEE',
    valideeLe: ISODate('2026-10-07T10:15:00.000Z'),
    version: 2
  }
]
```

**Analyse :**

La notation client.clientId permet de filtrer sur un champ imbriqué. La commande cmd_1001 appartient au client cli_18 et est donc retournée.

### Recherche par montant minimum

**Requête complète :**

```javascript
db.commandes.find({ "total.montant": { $gte: 2000 } })
```

**Résultat exact :**

```text
[
  {
    _id: ObjectId('6ae31c27fd9bd6b6168ce5b1'),
    type: 'Commande',
    commandeId: 'cmd_1001',
    client: {
      clientId: 'cli_18',
      nom: 'Camille Martin',
      telephone: '+33612000000',
      adresseLivraison: { ligne1: '8 avenue Parmentier', codePostal: '75011', ville: 'Paris' }
    },
    restaurantId: 'rest_42',
    lignes: [
      {
        ligneId: 'ligne_1',
        platId: 'plat_7',
        nomPlat: 'Bowl falafel',
        prixUnitaire: { montant: 1290, devise: 'EUR' },
        quantite: 2
      }
    ],
    total: { montant: 2580, devise: 'EUR' },
    statut: 'VALIDEE',
    valideeLe: ISODate('2026-10-07T10:15:00.000Z'),
    version: 2
  }
]
```

**Analyse :**

L’opérateur $gte sélectionne les montants supérieurs ou égaux à 2 000 centimes. Le total de cmd_1001 est de 2 580 centimes : la commande satisfait ce critère.

### Projection de l’identifiant et du total

**Requête complète :**

```javascript
db.commandes.find(
  {},
  { commandeId: 1, total: 1, _id: 0 }
)
```

**Résultat exact :**

```text
[ { commandeId: 'cmd_1001', total: { montant: 2580, devise: 'EUR' } } ]
```

**Analyse :**

Le filtre vide sélectionne toutes les commandes. La projection affiche commandeId et total, et masque _id. Une seule commande est retournée.

## Partie D — Modification de champs et de tableaux

### Modification conditionnelle de l’adresse

**Requête complète :**

```javascript
db.commandes.updateOne(
  {
    commandeId: "cmd_1001",
    "client.adresseLivraison.ligne1": "8 avenue Parmentier",
    version: 2
  },
  {
    $set: {
      "client.adresseLivraison.ligne1": "10 avenue Parmentier"
    },
    $inc: { version: 1 }
  }
)
```

**Résultat exact :**

```text
{
  acknowledged: true,
  insertedId: null,
  matchedCount: 1,
  modifiedCount: 1,
  upsertedCount: 0
}
```

**Analyse :**

Un document correspond au filtre et un document est modifié. $set remplace le numéro 8 par le numéro 10 ; $inc augmente la version de 2 à 3. Le filtre exige l’ancienne adresse et la version 2. L’écriture sur ce document est atomique. insertedId: null et upsertedCount: 0 indiquent qu’aucun nouveau document n’a été créé. Cette opération ne publie pas l’événement AdresseLivraisonModifiee.

### Vérification de la nouvelle adresse

**Requête complète :**

```javascript
db.commandes.findOne(
  { commandeId: "cmd_1001" },
  { _id: 0, "client.adresseLivraison": 1, version: 1 }
)
```

**Résultat exact :**

```text
{
  client: {
    adresseLivraison: { ligne1: '10 avenue Parmentier', codePostal: '75011', ville: 'Paris' }
  },
  version: 3
}
```

**Analyse :**

La lecture confirme 10 avenue Parmentier et la version 3 dans la commande. Les autres éléments d’adresse restent inchangés. Cela ne prouve pas une mise à jour de l’adresse dans la collection livraisons.

### Premier ajout du mardi avec $addToSet

**Requête complète :**

```javascript
db.restaurants.updateOne(
  { restaurantId: "rest_42" },
  {
    $addToSet: {
      horaires: {
        jour: "MARDI",
        ouverture: "11:30",
        fermeture: "22:30"
      }
    }
  }
)
```

**Résultat exact :**

```text
{
  acknowledged: true,
  insertedId: null,
  matchedCount: 1,
  modifiedCount: 1,
  upsertedCount: 0
}
```

**Analyse :**

matchedCount: 1 et modifiedCount: 1 indiquent que le restaurant a été trouvé et que l’horaire absent a été ajouté. Il s’agit d’un horaire de test pour l’exercice.

### Deuxième ajout identique avec $addToSet

**Requête complète :**

```javascript
db.restaurants.updateOne(
  { restaurantId: "rest_42" },
  {
    $addToSet: {
      horaires: {
        jour: "MARDI",
        ouverture: "11:30",
        fermeture: "22:30"
      }
    }
  }
)
```

**Résultat exact :**

```text
{
  acknowledged: true,
  insertedId: null,
  matchedCount: 1,
  modifiedCount: 0,
  upsertedCount: 0
}
```

**Analyse :**

Le restaurant est trouvé mais modifiedCount vaut 0 : cet élément identique existe déjà. $addToSet évite de l’ajouter à nouveau. Cela n’impose pas l’unicité du seul champ jour pour tous les horaires possibles.

### Lecture des horaires après $addToSet

**Requête complète :**

```javascript
db.restaurants.findOne(
  { restaurantId: "rest_42" },
  { _id: 0, horaires: 1 }
)
```

**Résultat exact :**

```text
{
  horaires: [
    { jour: 'LUNDI', ouverture: '11:30', fermeture: '22:30' },
    { jour: 'MARDI', ouverture: '11:30', fermeture: '22:30' }
  ]
}
```

**Analyse :**

Le tableau contient lundi et une seule entrée pour mardi. Le deuxième essai n’a créé aucun doublon.

### Ajout du même horaire avec $push

**Requête complète :**

```javascript
db.restaurants.updateOne(
  { restaurantId: "rest_42" },
  {
    $push: {
      horaires: {
        jour: "MARDI",
        ouverture: "11:30",
        fermeture: "22:30"
      }
    }
  }
)
```

**Résultat exact :**

```text
{
  acknowledged: true,
  insertedId: null,
  matchedCount: 1,
  modifiedCount: 1,
  upsertedCount: 0
}
```

**Analyse :**

Un document est modifié. Contrairement à $addToSet, $push ajoute l’élément même lorsqu’un élément identique est déjà présent.

### Vérification du doublon

**Requête complète :**

```javascript
db.restaurants.findOne(
  { restaurantId: "rest_42" },
  { _id: 0, horaires: 1 }
)
```

**Résultat exact :**

```text
{
  horaires: [
    { jour: 'LUNDI', ouverture: '11:30', fermeture: '22:30' },
    { jour: 'MARDI', ouverture: '11:30', fermeture: '22:30' },
    { jour: 'MARDI', ouverture: '11:30', fermeture: '22:30' }
  ]
}
```

**Analyse :**

Deux entrées identiques pour mardi apparaissent. Cette lecture démontre que $push autorise les doublons.

### Suppression des horaires du mardi avec $pull

**Requête complète :**

```javascript
db.restaurants.updateOne(
  { restaurantId: "rest_42" },
  { $pull: { horaires: { jour: "MARDI" } } }
)
```

**Résultat exact :**

```text
{
  acknowledged: true,
  insertedId: null,
  matchedCount: 1,
  modifiedCount: 1,
  upsertedCount: 0
}
```

**Analyse :**

Un document est modifié. $pull retire tous les éléments du tableau dont le champ jour vaut MARDI ; il supprime donc les deux occurrences de test.

### Ajout de la date de modification

**Requête complète :**

```javascript
db.restaurants.updateOne(
  { restaurantId: "rest_42" },
  { $set: { updatedAt: new Date() } }
)
```

**Résultat exact :**

```text
{
  acknowledged: true,
  insertedId: null,
  matchedCount: 1,
  modifiedCount: 1,
  upsertedCount: 0
}
```

**Analyse :**

Le restaurant est modifié par l’ajout du champ updatedAt. new Date() crée une date BSON correspondant au moment de l’exécution.

### Lecture finale du restaurant

**Requête complète :**

```javascript
db.restaurants.findOne({ restaurantId: "rest_42" })
```

**Résultat exact :**

```text
{
  _id: ObjectId('6ae31b97fd9bd6b6168ce5b0'),
  type: 'Restaurant',
  restaurantId: 'rest_42',
  nom: 'Le Bistrot Vert',
  telephone: '+33142000000',
  adresse: { ligne1: '12 rue des Lilas', codePostal: '75011', ville: 'Paris' },
  horaires: [ { jour: 'LUNDI', ouverture: '11:30', fermeture: '22:30' } ],
  statut: 'PUBLIE',
  plats: [
    {
      platId: 'plat_7',
      nom: 'Bowl falafel',
      prix: { montant: 1290, devise: 'EUR' },
      disponible: true
    }
  ],
  version: 3,
  updatedAt: ISODate('2026-10-29T14:34:39.842Z')
}
```

**Analyse :**

Seul l’horaire du lundi reste présent. updatedAt vaut exactement la date affichée dans le résultat. Les modifications d’horaires n’ont pas incrémenté le champ version : il reste à 3, car aucune opération $inc n’a été appliquée à ce restaurant.

Un tableau peut conserver une séquence ordonnée, comme une chronologie. Pour une collection de valeurs distinctes, `$addToSet` évite d’ajouter un élément identique, tandis que `$push` autorise les doublons. La règle d’unicité métier doit néanmoins être définie séparément.

## Partie E — Imbrication et référence

Nous conservons dans chaque ligne de commande le nom et le prix du plat au moment de l’achat, ainsi que son identifiant. Cela permet de relire une commande sans dépendre du catalogue actuel, et de conserver le prix payé si le menu change. Restaurant possède les données actuelles du catalogue ; Commande possède la copie historique de l’achat. Une référence seule demanderait une autre lecture et ne suffirait pas à restituer l’ancien prix. La duplication est volontaire ; la taille de chaque commande doit rester limitée.

| Critère | Copie du nom et du prix dans la commande | Référence seule vers le plat |
|---|---|---|
| Lecture de l’historique | Une lecture de commande fournit les lignes historiques | Une lecture du catalogue est nécessaire |
| Changement du catalogue | Le prix payé reste figé | Les données actuelles ne restituent pas l’ancien prix |
| Propriété | Restaurant possède le catalogue ; Commande possède la copie de l’achat | Les informations courantes appartiennent à Restaurant |
| Cohérence | Fidélité au moment de la validation | Dépendance à l’état courant du catalogue |
| Croissance | Le document augmente avec ses lignes, à garder bornées | Document plus petit, mais lectures supplémentaires |

## Partie F — Index et plans de recherche

### Recherche avant index

**Requête complète :**

```javascript
var plan = db.commandes.find({ commandeId: "cmd_1001" }).explain("executionStats")

printjson({
  plan: plan.queryPlanner.winningPlan,
  documentsExamines: plan.executionStats.totalDocsExamined,
  clesExaminees: plan.executionStats.totalKeysExamined,
  documentsRetournes: plan.executionStats.nReturned
})
```

**Résultat exact :**

```text
{
  plan: {
    isCached: false,
    stage: 'COLLSCAN',
    filter: {
      commandeId: {
        '$eq': 'cmd_1001'
      }
    },
    direction: 'forward'
  },
  documentsExamines: 1,
  clesExaminees: 0,
  documentsRetournes: 1
}
```

**Analyse :**

COLLSCAN confirme le parcours de la collection. Un seul document est examiné et retourné, et aucune clé n’est consultée.

### Création d’un index unique sur commandeId

**Requête complète :**

```javascript
db.commandes.createIndex(
  { commandeId: 1 },
  { unique: true }
)
```

**Résultat exact :**

```text
commandeId_1
```

**Analyse :**

Le résultat est le nom de l’index créé : commandeId_1. Cet index permet une recherche par identifiant métier et interdit les doublons de commandeId.

### Recherche après index unique

**Requête complète :**

```javascript
var plan = db.commandes.find({ commandeId: "cmd_1001" }).explain("executionStats")

printjson({
  plan: plan.queryPlanner.winningPlan,
  documentsExamines: plan.executionStats.totalDocsExamined,
  clesExaminees: plan.executionStats.totalKeysExamined,
  documentsRetournes: plan.executionStats.nReturned
})
```

**Résultat exact :**

```text
{
  plan: {
    isCached: false,
    stage: 'EXPRESS_IXSCAN',
    keyPattern: '{ commandeId: 1 }',
    indexName: 'commandeId_1'
  },
  documentsExamines: 1,
  clesExaminees: 1,
  documentsRetournes: 1
}
```

**Analyse :**

Le plan EXPRESS_IXSCAN utilise commandeId_1. Une clé et un document sont examinés pour retourner une commande. Nous constatons l’utilisation de l’index, sans démontrer un gain de temps significatif sur ce très petit jeu de données.

### Test d’unicité — refus attendu par le TP

**Requête complète :**

```javascript
db.commandes.insertOne({
  commandeId: "cmd_1001"
})
```

**Résultat exact :**

```text
MongoServerError: E11000 duplicate key error collection: tastigo_training.commandes index: commandeId_1 dup key: { commandeId: "cmd_1001" }
```

**Analyse :**

L’index unique refuse une seconde commande portant cmd_1001. L’erreur E11000 est attendue et constitue la preuve de l’unicité. Aucun document supplémentaire n’est inséré et la commande existante reste inchangée.

### Création de l’index composé

**Requête complète :**

```javascript
db.commandes.createIndex({
  restaurantId: 1,
  statut: 1
})
```

**Résultat exact :**

```text
restaurantId_1_statut_1
```

**Analyse :**

L’index restaurantId_1_statut_1 porte sur restaurantId puis statut. Il correspond au besoin de chercher les commandes d’un restaurant selon leur état.

### Plan de recherche avec l’index composé

**Requête complète :**

```javascript
var planCompose = db.commandes.find({
  restaurantId: "rest_42",
  statut: "VALIDEE"
}).explain("executionStats")

printjson({
  plan: planCompose.queryPlanner.winningPlan,
  documentsExamines: planCompose.executionStats.totalDocsExamined,
  clesExaminees: planCompose.executionStats.totalKeysExamined,
  documentsRetournes: planCompose.executionStats.nReturned
})
```

**Résultat exact :**

```text
{
  plan: {
    isCached: false,
    stage: 'FETCH',
    inputStage: {
      stage: 'IXSCAN',
      keyPattern: {
        restaurantId: 1,
        statut: 1
      },
      indexName: 'restaurantId_1_statut_1',
      isMultiKey: false,
      multiKeyPaths: {
        restaurantId: [],
        statut: []
      },
      isUnique: false,
      isSparse: false,
      isPartial: false,
      indexVersion: 2,
      direction: 'forward',
      indexBounds: {
        restaurantId: [
          '["rest_42", "rest_42"]'
        ],
        statut: [
          '["VALIDEE", "VALIDEE"]'
        ]
      }
    }
  },
  documentsExamines: 1,
  clesExaminees: 1,
  documentsRetournes: 1
}
```

**Analyse :**

IXSCAN consulte l’index restaurantId_1_statut_1 et FETCH récupère le document correspondant. Une clé et un document sont examinés, pour une commande retournée. Les bornes d’index correspondent précisément à rest_42 et VALIDEE.

### Comparaison des résultats

| Recherche | Plan | Documents examinés | Clés examinées | Documents retournés |
|---|---|---:|---:|---:|
| `commandeId` avant index | `COLLSCAN` | 1 | 0 | 1 |
| `commandeId` après index unique | `EXPRESS_IXSCAN` | 1 | 1 | 1 |
| Restaurant et statut après index composé | `FETCH` avec `IXSCAN` | 1 | 1 | 1 |

Les index sont utilisés par les recherches observées. Ils consomment de l’espace et ajoutent du travail aux écritures affectant leurs champs. Le jeu de données ne contient qu’une commande : nous ne prétendons donc pas démontrer un gain de performance à grande échelle.

## Partie G — Pipeline d’agrégation

### Agrégation : filtrage et regroupement

**Requête complète :**

```javascript
db.commandes.aggregate([
  { $match: { statut: "VALIDEE" } },
  {
    $group: {
      _id: "$restaurantId",
      nombreCommandes: { $sum: 1 },
      montantTotalCentimes: { $sum: "$total.montant" },
      montantMoyenCentimes: { $avg: "$total.montant" }
    }
  }
])
```

**Résultat exact :**

```text
[
  {
    _id: 'rest_42',
    nombreCommandes: 1,
    montantTotalCentimes: 2580,
    montantMoyenCentimes: 2580
  }
]
```

**Analyse :**

Le pipeline conserve les commandes validées avec $match, puis les regroupe par restaurant avec $group. Il compte une commande et calcule un total et une moyenne de 2 580 centimes. Ici, _id est la clé de regroupement rest_42, pas l’ObjectId d’un document.

### Agrégation finale : projection et tri

**Requête complète :**

```javascript
db.commandes.aggregate([
  { $match: { statut: "VALIDEE" } },
  {
    $group: {
      _id: "$restaurantId",
      nombreCommandes: { $sum: 1 },
      montantTotalCentimes: { $sum: "$total.montant" },
      montantMoyenCentimes: { $avg: "$total.montant" }
    }
  },
  {
    $project: {
      _id: 0,
      restaurantId: "$_id",
      nombreCommandes: 1,
      montantTotalCentimes: 1,
      montantMoyenCentimes: 1
    }
  },
  { $sort: { restaurantId: 1 } }
])
```

**Résultat exact :**

```text
[
  {
    nombreCommandes: 1,
    montantTotalCentimes: 2580,
    montantMoyenCentimes: 2580,
    restaurantId: 'rest_42'
  }
]
```

**Analyse :**

Le calcul reste identique. $project remplace la clé de regroupement _id par le champ restaurantId dans l’affichage, et $sort trie les résultats par restaurant. Avec une seule commande pour un seul restaurant, le total et la moyenne sont identiques et le tri n’a pas d’effet visible. Le pipeline ne modifie pas les données stockées.

| Étape | Traitement |
|---|---|
| `$match` | Conserve les commandes validées |
| `$group` | Regroupe ces commandes par restaurant et calcule les statistiques |
| `$project` | Choisit les champs affichés et expose la clé de groupe sous `restaurantId` |
| `$sort` | Trie les résumés par restaurant |

Chaque étape reçoit le résultat de la précédente. Le total et la moyenne sont égaux à 2 580 centimes car une seule commande est présente. Ces agrégations ne modifient pas les documents stockés.

## Partie H — Transition conditionnelle atomique

### État initial de la livraison avant transition

**Requête complète :**

```javascript
db.livraisons.findOne(
  { livraisonId: "liv_501" },
  { _id: 0, livraisonId: 1, statut: 1, livreur: 1, version: 1 }
)
```

**Résultat exact :**

```text
{
  livraisonId: 'liv_501',
  statut: 'EN_PREPARATION',
  livreur: null,
  version: 1
}
```

**Analyse :**

La livraison est en EN_PREPARATION, sans livreur, à la version 1. Notre invariant exige un livreur pour passer à EN_ROUTE.

### Affectation d’un livreur de test

**Requête complète :**

```javascript
db.livraisons.updateOne(
  { livraisonId: "liv_501", statut: "EN_PREPARATION" },
  {
    $set: { livreur: { livreurId: "livreur_test_1" } },
    $inc: { version: 1 }
  }
)
```

**Résultat exact :**

```text
{
  acknowledged: true,
  insertedId: null,
  matchedCount: 1,
  modifiedCount: 1,
  upsertedCount: 0
}
```

**Analyse :**

La livraison est trouvée et modifiée. livreur_test_1 est une donnée d’exercice ajoutée pour respecter l’invariant, pas un livreur réel fourni par les fichiers du projet. La version passe de 1 à 2.

### Premier passage à EN_ROUTE

**Requête complète :**

```javascript
db.livraisons.updateOne(
  {
    livraisonId: "liv_501",
    statut: "EN_PREPARATION",
    "livreur.livreurId": { $exists: true, $ne: null }
  },
  {
    $set: {
      statut: "EN_ROUTE",
      departLe: new Date()
    },
    $inc: { version: 1 }
  }
)
```

**Résultat exact :**

```text
{
  acknowledged: true,
  insertedId: null,
  matchedCount: 1,
  modifiedCount: 1,
  upsertedCount: 0
}
```

**Analyse :**

Le document satisfait les conditions : bon identifiant, état EN_PREPARATION et présence d’un identifiant de livreur non nul. MongoDB modifie le statut, ajoute departLe et augmente la version de 2 à 3 dans une seule opération atomique.

### Deuxième passage identique à EN_ROUTE

**Requête complète :**

```javascript
db.livraisons.updateOne(
  {
    livraisonId: "liv_501",
    statut: "EN_PREPARATION",
    "livreur.livreurId": { $exists: true, $ne: null }
  },
  {
    $set: {
      statut: "EN_ROUTE",
      departLe: new Date()
    },
    $inc: { version: 1 }
  }
)
```

**Résultat exact :**

```text
{
  acknowledged: true,
  insertedId: null,
  matchedCount: 0,
  modifiedCount: 0,
  upsertedCount: 0
}
```

**Analyse :**

matchedCount: 0 et modifiedCount: 0 montrent que la livraison ne correspond plus au filtre : elle est déjà EN_ROUTE. Le deuxième essai ne change ni le document, ni sa version, ni sa date de départ.

### Vérification finale de la livraison

**Requête complète :**

```javascript
db.livraisons.findOne(
  { livraisonId: "liv_501" },
  { _id: 0, statut: 1, livreur: 1, version: 1, departLe: 1 }
)
```

**Résultat exact :**

```text
{
  statut: 'EN_ROUTE',
  livreur: { livreurId: 'livreur_test_1' },
  version: 3,
  departLe: ISODate('2026-10-29T15:33:00.091Z')
}
```

**Analyse :**

La lecture confirme EN_ROUTE, le livreur de test, la version 3 et la date exacte de départ affichée. La transition est acquise dans notre base tastigo_training. Aucun événement Redis et aucune mise à jour de la projection de suivi ne sont prouvés par ces opérations.

### Comparaison des deux exécutions

| Exécution de la transition | `matchedCount` | `modifiedCount` |
|---|---:|---:|
| Première | 1 | 1 |
| Deuxième | 0 | 0 |

Le filtre empêche une deuxième transition `EN_PREPARATION → EN_ROUTE`. La vérification et la mise à jour du document sont atomiques. Cette garantie ne publie pas un événement dans Redis et ne couvre pas les autres documents.

## Bilan

**Les résultats présentés proviennent de notre base `tastigo_training`.** Nous avons manipulé nos agrégats Tastigo, testé les opérateurs de modification, étudié les index, calculé des statistiques et vérifié une transition de livraison conditionnelle.

Le jeu de données contient une commande. Les opérations absentes de la transcription, notamment `insertMany()`, les filtres de lecture sur les dates et sur les tableaux, ainsi que `getIndexes()`, ne sont pas présentées comme effectuées. La projection de suivi et l’échange d’événements Redis restent hors du travail exécuté ici. Aucune suppression de la base n’est rapportée.

## Questions de révision

1. **Document, document imbriqué, tableau, index :** un document représente un objet ; un document imbriqué structure un sous-objet ; un tableau contient plusieurs éléments ; un index facilite certaines recherches et peut imposer l’unicité.
2. **Types BSON sans équivalent fidèle en JSON simple :** notamment ObjectId, Date et Decimal128. Notre séance utilise des ObjectId et des dates BSON ; nos montants sont numériques en centimes.
3. **Frontière des documents :** lire une commande avec ses lignes et ses prix historiques justifie leur imbrication. Le catalogue actuel reste sous la responsabilité du service Restaurant.
4. **Index unique :** il fournit un accès par identifiant métier et une contrainte d’intégrité. L’erreur E11000 confirme le refus du doublon.
5. **Limite de l’atomicité :** la transition concerne un document de livraison. La publication Redis et la modification d’autres documents ne font pas partie de cette opération.
6. **Projection de champs et projection de suivi :** la projection de find() choisit les champs affichés. Le suivi du projet serait un modèle de lecture maintenu par des événements ; il n’est pas construit par ces seules requêtes.
