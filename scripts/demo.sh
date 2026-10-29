#!/usr/bin/env sh
set -eu

docker compose up -d mongodb redis

for SERVICE in mongodb redis; do
  i=0
  while [ "$(docker inspect --format '{{.State.Health.Status}}' "tastigo-$SERVICE" 2>/dev/null || true)" != "healthy" ]; do
    i=$((i + 1))
    [ "$i" -lt 30 ] || { echo "$SERVICE ne devient pas sain" >&2; exit 1; }
    sleep 1
  done
done

# Réinitialisation déterministe du scénario de démonstration.
docker compose exec -T mongodb mongosh --quiet /workspace/init/01_restaurants.js
docker compose exec -T redis redis-cli -n 2 FLUSHDB >/dev/null
docker compose exec -T redis redis-cli -n 3 FLUSHDB >/dev/null
docker compose exec -T redis redis-cli -n 4 FLUSHDB >/dev/null

./scripts/process-mongodb-outbox.sh
./redis/run.sh 02_evenements.redis

echo "===== VERIFICATION DES REPLICAS ====="
docker compose exec -T redis redis-cli -n 2 HGETALL catalogue:restaurant:rest_42
docker compose exec -T redis redis-cli -n 2 HGETALL catalogue:restaurant:rest_42:plat:plat_7
docker compose exec -T redis redis-cli -n 3 HGETALL replica:commande:cmd_1001
docker compose exec -T redis redis-cli -n 4 HGETALL suivi:cmd_1001
