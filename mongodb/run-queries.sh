#!/usr/bin/env sh
# Exécute les requêtes de démonstration sur la base MongoDB du service Restaurant.
set -eu
cd "$(dirname "$0")/.."
export MSYS_NO_PATHCONV=1  # Git Bash sous Windows : ne pas convertir /workspace

docker compose exec -T mongodb mongosh --quiet /workspace/requetes.js
