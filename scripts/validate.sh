#!/usr/bin/env sh
set -eu

python3 -m json.tool Aggregates.json >/dev/null
python3 -m json.tool Commands.json >/dev/null
python3 -m json.tool Events.json >/dev/null
docker compose config >/dev/null

[ "$(jq '.services | length' Aggregates.json)" -ge 2 ]
[ "$(jq '.commandes | length' Commands.json)" -ge 1 ]
[ "$(jq '[.evenements[] | select(.operationReplica == "CREER")] | length' Events.json)" -ge 1 ]
[ "$(jq '[.evenements[] | select(.operationReplica == "METTRE_A_JOUR")] | length' Events.json)" -ge 1 ]

docker compose exec -T mongodb mongosh --quiet --eval 'db=db.getSiblingDB("tastigo_restaurant"); if(db.restaurants.countDocuments({}) < 2) quit(1)'
docker compose exec -T redis redis-cli -n 2 EXISTS catalogue:restaurant:rest_42 | grep -q '^1$'
docker compose exec -T redis redis-cli -n 3 EXISTS replica:commande:cmd_1001 | grep -q '^1$'
docker compose exec -T redis redis-cli -n 4 EXISTS suivi:cmd_1001 | grep -q '^1$'
docker compose exec -T redis redis-cli -n 2 HGET catalogue:restaurant:rest_42 sourceVersion | grep -q '^3$'
docker compose exec -T redis redis-cli -n 2 HGET catalogue:restaurant:rest_42:plat:plat_7 prixMontant | grep -q '^1290$'
docker compose exec -T mongodb mongosh --quiet --eval 'db=db.getSiblingDB("tastigo_restaurant"); if(db.outbox.countDocuments({publie:false}) != 0) quit(1)'

echo "VALIDATION_OK services=4 commandes=$(jq '.commandes | length' Commands.json) evenements=$(jq '.evenements | length' Events.json) bases=2"
