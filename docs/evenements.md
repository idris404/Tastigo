# Découplage et événements

Les contrats sont dans [`../Events.json`](../Events.json). Les exemples sont des événements réellement produits par les services pendant `scripts/demo.py`.

## Enveloppe commune

- `eventId` : identifiant unique utilisé pour l'idempotence ;
- `eventType` et `eventVersion` : nom et version du contrat ;
- `occurredAt` : date UTC du fait métier ;
- `correlationId` : lien entre les événements d'un même parcours (`corr_cmd_1001`) ;
- `emetteur` et `recepteur` : direction du flux ;
- `aggregateId` et `aggregateVersion` : source et ordre des changements ;
- `operationReplica` : `CREER` ou `METTRE_A_JOUR` ;
- `modification` : chemin de la donnée (`donneeAgregatModifiee`), identifiants structurés (`cible`), ancienne et nouvelle valeur.

## Transport : Redis Streams

Le bus est une instance Redis dédiée (`tastigo-bus`). Chaque service possède une boîte de réception `evenements:vers:<service>`. Le récepteur la lit avec un groupe de consommateurs :

1. `XREADGROUP` délivre l'événement ;
2. le service applique la modification dans sa propre base ;
3. `XACK` acquitte l'événement.

Un événement non acquitté (panne pendant le traitement) reste dans la liste des messages en attente du groupe et est relu au redémarrage. Les flux ne sont pas tronqués : ils servent aussi de journal pour reconstruire une projection.

## Publication fiable : outbox transactionnelle

Un service n'écrit jamais sur le bus pendant une commande. Il écrit l'événement dans **sa propre base, dans la même transaction que l'agrégat** :

| Service | Outbox | Atomicité |
|---|---|---|
| Restaurant | collection MongoDB `outbox` | transaction multi-documents (replica set) |
| Commande, Livraison | `STREAM outbox` dans sa base Redis | bloc `MULTI` / `EXEC` |

Un relais recopie ensuite l'outbox sur le bus (`publie: true` dans MongoDB, `outbox:curseur` dans Redis). Si le relais tombe entre la publication et le marquage, l'événement est republié : c'est le récepteur qui gère le doublon.

## Traitement par le récepteur

1. `eventId` déjà présent dans `evenements:traites` : ignoré (idempotence).
2. `aggregateVersion` ≤ `sourceVersion` du réplica : ignoré (ordre).
3. Règle métier violée : l'événement est acquitté et tracé dans `evenements:rejetes`.
4. Sinon : modification du réplica et ajout de l'`eventId` dans le même `MULTI`.

## Flux

| Réplica | Émetteur → récepteur | Création | Mise à jour |
|---|---|---|---|
| Catalogue dans Commande | Restaurant → Commande | `RestaurantPublie` | `MenuMisAJour` (prix, disponibilité, nouveau plat), `StatutRestaurantModifie` |
| Commande livrable dans Livraison | Commande → Livraison | `CommandeValidee` | `AdresseLivraisonModifiee` |
| État de livraison dans Commande | Livraison → Commande | `LivraisonCreee` | `StatutLivraisonModifie` |
| Projection dans Suivi | Commande, Livraison → Suivi | `CommandeValidee` | `LivraisonCreee`, `StatutLivraisonModifie` |

Un restaurant en `BROUILLON` n'émet rien : il n'est jamais visible des autres services. Quand un événement intéresse deux récepteurs avec des besoins différents (`CommandeValidee`), l'émetteur produit deux événements, chacun avec la seule donnée utile à son récepteur.
