#!/usr/bin/env sh
set -eu

EVENTS="$(docker compose exec -T mongodb mongosh --quiet --eval '
  db = db.getSiblingDB("tastigo_restaurant");
  print(EJSON.stringify(db.outbox.find({publie:false}).sort({aggregateVersion:1}).toArray()));
')"

echo "$EVENTS" | jq -c '.[]' | while IFS= read -r EVENT; do
  EVENT_ID="$(echo "$EVENT" | jq -r '.eventId')"
  EVENT_TYPE="$(echo "$EVENT" | jq -r '.eventType')"
  RESTAURANT_ID="$(echo "$EVENT" | jq -r '.payload.restaurantId')"
  VERSION="$(echo "$EVENT" | jq -r '.aggregateVersion')"

  if docker compose exec -T redis redis-cli -n 2 SISMEMBER evenements:traites "$EVENT_ID" </dev/null | grep -q '^1$'; then
    echo "Déjà traité : $EVENT_ID"
    continue
  fi

  case "$EVENT_TYPE" in
    RestaurantPublie)
      NOM="$(echo "$EVENT" | jq -r '.payload.nom')"
      STATUT="$(echo "$EVENT" | jq -r '.payload.statut')"
      PLAT_ID="$(echo "$EVENT" | jq -r '.payload.plats[0].platId')"
      PLAT_NOM="$(echo "$EVENT" | jq -r '.payload.plats[0].nom')"
      PRIX="$(echo "$EVENT" | jq -r '.payload.plats[0].prix.montant')"
      DISPONIBLE="$(echo "$EVENT" | jq -r '.payload.plats[0].disponible')"
      docker compose exec -T redis redis-cli -n 2 HSET "catalogue:restaurant:$RESTAURANT_ID" restaurantId "$RESTAURANT_ID" nom "$NOM" statut "$STATUT" sourceVersion "$VERSION" </dev/null >/dev/null
      docker compose exec -T redis redis-cli -n 2 SADD "catalogue:restaurant:$RESTAURANT_ID:plats" "$PLAT_ID" </dev/null >/dev/null
      docker compose exec -T redis redis-cli -n 2 HSET "catalogue:restaurant:$RESTAURANT_ID:plat:$PLAT_ID" platId "$PLAT_ID" nom "$PLAT_NOM" prixMontant "$PRIX" prixDevise EUR disponible "$DISPONIBLE" </dev/null >/dev/null
      ;;
    MenuMisAJour)
      PLAT_ID="$(echo "$EVENT" | jq -r '.payload.platId')"
      PRIX="$(echo "$EVENT" | jq -r '.payload.nouvelleValeur.montant')"
      docker compose exec -T redis redis-cli -n 2 HSET "catalogue:restaurant:$RESTAURANT_ID:plat:$PLAT_ID" prixMontant "$PRIX" </dev/null >/dev/null
      docker compose exec -T redis redis-cli -n 2 HSET "catalogue:restaurant:$RESTAURANT_ID" sourceVersion "$VERSION" </dev/null >/dev/null
      ;;
    *)
      echo "Type non pris en charge : $EVENT_TYPE" >&2
      exit 1
      ;;
  esac

  docker compose exec -T redis redis-cli -n 2 SADD evenements:traites "$EVENT_ID" </dev/null >/dev/null
  docker compose exec -T mongodb mongosh --quiet --eval "db=db.getSiblingDB('tastigo_restaurant'); db.outbox.updateOne({eventId:'$EVENT_ID'},{\$set:{publie:true,publieLe:new Date()}})" </dev/null >/dev/null
  echo "Traité : $EVENT_ID ($EVENT_TYPE)"
done
