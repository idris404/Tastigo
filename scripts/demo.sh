#!/usr/bin/env sh
# Démarre la pile complète (bases, bus, services) puis exécute le scénario vérifié.
# Option --reset : repart de bases vides (supprime les volumes Docker du projet).
set -eu
cd "$(dirname "$0")/.."

if [ "${1:-}" = "--reset" ]; then
  docker compose down -v
fi

docker compose up -d --build --wait

if command -v python3 >/dev/null 2>&1; then PY=python3; else PY=python; fi
"$PY" scripts/demo.py

echo
echo "Interface de démonstration : http://localhost:8000"
