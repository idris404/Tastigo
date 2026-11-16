#!/usr/bin/env sh
# Exécute les requêtes de lecture sur les bases Redis des services puis sur le bus.
set -eu
cd "$(dirname "$0")/.."
export MSYS_NO_PATHCONV=1  # Git Bash sous Windows : ne pas convertir /workspace

filtrer() {
  grep -v -e '^[[:space:]]*#' -e '^[[:space:]]*$' "$1"
}

filtrer redis/requetes.redis | docker compose exec -T redis redis-cli
filtrer redis/bus.redis | docker compose exec -T bus redis-cli
