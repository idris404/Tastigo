#!/usr/bin/env sh
set -eu

SCRIPT_NAME="${1:-02_evenements.redis}"
SCRIPT_PATH="redis/$SCRIPT_NAME"

if [ ! -f "$SCRIPT_PATH" ]; then
  echo "Script introuvable : $SCRIPT_PATH" >&2
  exit 1
fi

grep -v '^[[:space:]]*#' "$SCRIPT_PATH" | docker compose exec -T redis redis-cli
