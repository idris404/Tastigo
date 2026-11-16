#!/usr/bin/env sh
# NIVEAU 1 : bases remplies et interrogeables, réplicas mis à jour par événements,
# SANS service programmé (uniquement mongosh et redis-cli).
# Bases utilisées : MongoDB tastigo_niveau1 et Redis DB 12 à 15 (séparées du niveau 2).
set -eu
cd "$(dirname "$0")/.."
export MSYS_NO_PATHCONV=1  # Git Bash sous Windows : ne pas convertir les chemins /niveau1

filtrer() {
  grep -v -e '^[[:space:]]*#' -e '^[[:space:]]*$' "$1"
}
redis() {
  docker compose exec -T redis redis-cli "$@"
}
sans_erreur() {
  # lit la sortie de redis-cli et échoue si une commande a été refusée
  erreurs="$(grep -e '^(error)' -e '^ERR' -e 'EXECABORT' || true)"
  if [ -n "$erreurs" ]; then
    echo "$erreurs" >&2
    exit 1
  fi
}

echo "===== 0. Démarrage de MongoDB et Redis"
docker compose up -d --wait mongodb redis

echo "===== 1. Remplissage de MongoDB (restaurants + outbox)"
docker compose exec -T mongodb mongosh --quiet /niveau1/mongodb/remplir.js

echo "===== 2. Remise à zéro des bases Redis 12 à 15"
for base in 12 13 14 15; do redis -n "$base" FLUSHDB >/dev/null; done

echo "===== 3. Relais de l'outbox MongoDB -> bus -> réplica catalogue de Commande"
docker compose exec -T mongodb mongosh --quiet /niveau1/mongodb/outbox-vers-redis.js | redis | sans_erreur

echo "===== 4. Échanges Commande -> Livraison -> Suivi"
filtrer niveau1/redis/scenario.redis | redis | sans_erreur

echo "===== 5. Requêtes MongoDB"
docker compose exec -T mongodb mongosh --quiet --eval 'var base = "tastigo_niveau1"' /workspace/requetes.js

echo "===== 6. Requêtes Redis"
filtrer niveau1/redis/requetes.redis | redis

echo "===== 7. Vérifications"
verifier() {
  attendu="$1"; shift
  obtenu="$(redis "$@" | tr -d '\r')"
  if [ "$obtenu" != "$attendu" ]; then
    echo "ÉCHEC : $* -> '$obtenu' (attendu '$attendu')" >&2
    exit 1
  fi
  echo "  [OK] $* = $attendu"
}
verifier 3 -n 12 SCARD catalogue:restaurants
verifier 1290 -n 12 HGET catalogue:plat:rest_42:plat_7 prixMontant
verifier 3 -n 12 HGET catalogue:restaurant:rest_42 sourceVersion
verifier false -n 12 HGET catalogue:plat:rest_51:plat_21 disponible
verifier INDISPONIBLE -n 12 HGET catalogue:restaurant:rest_63 statut
verifier 0 -n 12 EXISTS catalogue:restaurant:rest_77
verifier LIVREE -n 12 HGET replica:livraison:cmd_1001 statut
verifier "10 avenue Parmentier" -n 13 HGET replica:commande:cmd_1001 destination.adresse.ligne1
verifier 4 -n 13 HGET replica:commande:cmd_1001 sourceVersion
verifier LIVREE -n 14 HGET suivi:cmd_1001 statutTechnique
verifier 4 -n 14 ZCARD suivi:cmd_1001:chronologie
attente="$(docker compose exec -T mongodb mongosh --quiet --eval 'db.getSiblingDB("tastigo_niveau1").outbox.countDocuments({publie:false})' | tr -d '\r')"
[ "$attente" = "0" ] || { echo "ÉCHEC : $attente événement(s) encore dans l'outbox" >&2; exit 1; }
echo "  [OK] outbox MongoDB tastigo_niveau1 vide"

total=0
for flux in commande livraison suivi; do
  total=$((total + $(redis -n 15 XLEN "evenements:vers:$flux" | tr -d '\r')))
done

echo
echo "NIVEAU1_OK bases=MongoDB+Redis restaurants=4 replicas=4 evenements=$total"
