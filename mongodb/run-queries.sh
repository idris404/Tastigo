#!/usr/bin/env sh
set -eu

docker compose exec -T mongodb mongosh --quiet /workspace/02_requetes.js
