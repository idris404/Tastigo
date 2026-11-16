#!/usr/bin/env python3
"""Scénario de démonstration et de vérification de Tastigo.

Prérequis : la pile est démarrée (``docker compose up -d --build --wait``).
Le script n'utilise que la bibliothèque standard et appelle les API des quatre
services ; il vérifie à chaque étape que les réplicas et la projection sont mis à
jour par les événements. Il peut être relancé : il crée une nouvelle commande.

Usage : python scripts/demo.py
"""

import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
URL = {
    "restaurant": "http://localhost:8001",
    "commande": "http://localhost:8002",
    "livraison": "http://localhost:8003",
    "suivi": "http://localhost:8004",
}
CLIENT = {
    "clientId": "cli_18",
    "nom": "Camille Martin",
    "telephone": "+33612000000",
    "adresseLivraison": {"ligne1": "8 avenue Parmentier", "codePostal": "75011", "ville": "Paris"},
}
NOUVELLE_ADRESSE = {"ligne1": "10 avenue Parmentier", "codePostal": "75011", "ville": "Paris"}

for flux in (sys.stdout, sys.stderr):
    if hasattr(flux, "reconfigure"):
        flux.reconfigure(encoding="utf-8")

verifications = 0


# --------------------------------------------------------------------------- outils
class ErreurHttp(Exception):
    def __init__(self, code, detail):
        super().__init__(f"HTTP {code} : {detail}")
        self.code, self.detail = code, detail


def appel(service, methode, chemin, corps=None):
    donnees = None if corps is None else json.dumps(corps).encode()
    requete = urllib.request.Request(
        URL[service] + chemin, data=donnees, method=methode, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(requete, timeout=10) as reponse:
            return json.loads(reponse.read() or "null")
    except urllib.error.HTTPError as erreur:
        detail = json.loads(erreur.read() or "{}").get("detail")
        raise ErreurHttp(erreur.code, detail) from None


def get(service, chemin):
    return appel(service, "GET", chemin)


def attendre(description, condition, delai=15, afficher=True):
    """Attend qu'une condition lue dans un autre service devienne vraie (cohérence éventuelle)."""
    debut = time.time()
    while True:
        try:
            resultat = condition()
            if resultat:
                if afficher:
                    print(f"    ... propagé en {int((time.time() - debut) * 1000)} ms")
                return resultat
        except ErreurHttp:
            pass
        if time.time() - debut > delai:
            raise SystemExit(f"ÉCHEC : {description} (délai dépassé)")
        time.sleep(0.1)


def verifier(condition, message):
    global verifications
    if not condition:
        raise SystemExit(f"ÉCHEC : {message}")
    verifications += 1
    print(f"  [OK] {message}")


def titre(texte):
    print(f"\n=== {texte}")


def euros(centimes):
    return f"{centimes / 100:.2f} €".replace(".", ",")


def redis_cli(conteneur, *arguments):
    return subprocess.run(
        ["docker", "compose", "exec", "-T", conteneur, "redis-cli", "--raw", *arguments],
        cwd=RACINE,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    ).stdout


# --------------------------------------------------------------------------- scénario
def main():
    titre("0. Services disponibles")
    for service in URL:
        etat = attendre(f"santé de {service}", lambda s=service: get(s, "/sante"), delai=60, afficher=False)
        print(f"  {service:<10} {etat['base']}")

    titre("1. Catalogue source (Restaurant / MongoDB) et réplica (Commande / Redis DB 2)")
    sources = {r["restaurantId"]: r for r in get("restaurant", "/restaurants")}
    for r in sources.values():
        print(f"  {r['restaurantId']:<8} {r['nom']:<16} {r['adresse']['ville']:<6} {r['statut']:<12} v{r['version']}")
    for rid, source in sources.items():
        if source["statut"] == "BROUILLON":
            continue
        replica = attendre(
            f"réplica de {rid} à jour",
            lambda rid=rid, v=source["version"]: (lambda c: c if c["sourceVersion"] == v else None)(
                get("commande", f"/catalogue/{rid}")
            ),
        )
        prix_source = {p["platId"]: (p["prix"]["montant"], p["disponible"]) for p in source["plats"]}
        prix_replica = {p["platId"]: (p["prix"]["montant"], p["disponible"]) for p in replica["plats"]}
        verifier(
            prix_source == prix_replica and replica["statut"] == source["statut"],
            f"{rid} : réplica identique à la source (version {source['version']}, statut {source['statut']})",
        )
    try:
        get("commande", "/catalogue/rest_77")
        verifier(False, "rest_77 (BROUILLON) ne doit pas être répliqué")
    except ErreurHttp as erreur:
        verifier(erreur.code == 404, "rest_77 (BROUILLON) n'est pas répliqué : il n'a jamais été publié")

    titre("2. Le service Commande travaille sur son réplica local")
    try:
        appel("commande", "POST", "/commandes", {"client": CLIENT, "restaurantId": "rest_63"})
        verifier(False, "une commande sur un restaurant indisponible doit être refusée")
    except ErreurHttp as erreur:
        verifier(erreur.code == 409, f"commande refusée sur rest_63 : {erreur.detail}")
    commande = appel("commande", "POST", "/commandes", {"client": CLIENT, "restaurantId": "rest_42"})
    cid = commande["commandeId"]
    print(f"  commande {cid} créée (BROUILLON)")
    menu = {p["platId"]: p for p in get("commande", "/catalogue/rest_42")["plats"]}
    prix_bowl = menu["plat_7"]["prix"]["montant"]
    commande = appel("commande", "POST", f"/commandes/{cid}/lignes", {"platId": "plat_7", "quantite": 2})
    verifier(
        commande["total"]["montant"] == 2 * prix_bowl,
        f"2 x Bowl falafel à {euros(prix_bowl)} : total {euros(commande['total']['montant'])}",
    )
    commande = appel("commande", "POST", f"/commandes/{cid}/valider")
    verifier(commande["statut"] == "VALIDEE", f"{cid} validée en version {commande['version']}")

    titre("3. CommandeValidee crée le réplica et la livraison (Livraison / Redis DB 3)")
    livraison = attendre("livraison créée", lambda: get("livraison", f"/commandes/{cid}/livraison"))
    lid = livraison["livraisonId"]
    verifier(livraison["statut"] == "EN_PREPARATION", f"livraison {lid} créée EN_PREPARATION")
    replica = get("livraison", f"/replicas/commandes/{cid}")
    verifier(
        replica["destination"]["adresse"] == CLIENT["adresseLivraison"]
        and replica["collecte"]["nom"] == "Le Bistrot Vert"
        and replica["sourceVersion"] == commande["version"],
        f"réplica : collecte {replica['collecte']['nom']}, destination {replica['destination']['adresse']['ligne1']}",
    )
    etat = attendre(
        "réplica livraison dans Commande", lambda: get("commande", f"/commandes/{cid}")["replicaLivraison"]
    )
    verifier(etat["statut"] == "EN_PREPARATION", "Commande connaît l'état de la livraison (LivraisonCreee)")

    titre("4. AdresseLivraisonModifiee met à jour le réplica Livraison")
    commande = appel("commande", "PUT", f"/commandes/{cid}/adresse-livraison", NOUVELLE_ADRESSE)
    replica = attendre(
        "adresse répliquée",
        lambda: (lambda x: x if x["sourceVersion"] == commande["version"] else None)(
            get("livraison", f"/replicas/commandes/{cid}")
        ),
    )
    verifier(
        replica["destination"]["adresse"]["ligne1"] == NOUVELLE_ADRESSE["ligne1"],
        f"nouvelle destination : {replica['destination']['adresse']['ligne1']} (sourceVersion {replica['sourceVersion']})",
    )

    titre("5. MenuMisAJour : le prix change dans Restaurant, le réplica suit, la commande reste figée")
    nouveau_prix = prix_bowl + 50
    restaurant = appel("restaurant", "PUT", "/restaurants/rest_42/plats/plat_7/prix", {"montant": nouveau_prix})
    replica = attendre(
        "prix répliqué",
        lambda: (lambda c: c if c["sourceVersion"] == restaurant["version"] else None)(
            get("commande", "/catalogue/rest_42")
        ),
    )
    plat = next(p for p in replica["plats"] if p["platId"] == "plat_7")
    verifier(plat["prix"]["montant"] == nouveau_prix, f"réplica catalogue : Bowl falafel à {euros(nouveau_prix)}")
    commande = get("commande", f"/commandes/{cid}")
    verifier(
        commande["lignes"][0]["prixUnitaire"]["montant"] == prix_bowl,
        f"{cid} conserve le prix payé {euros(prix_bowl)} (snapshot)",
    )

    titre("6. Projection Suivi (Redis DB 4)")
    suivi = attendre(
        "suivi en préparation",
        lambda: (lambda s: s if s["statutTechnique"] == "EN_PREPARATION" else None)(get("suivi", f"/suivis/{cid}")),
    )
    verifier(
        suivi["resume"]["nombreArticles"] == 2 and suivi["restaurant"]["nom"] == "Le Bistrot Vert",
        f"« {suivi['statutAffiche']} » - {suivi['resume']['nombreArticles']} articles, "
        f"{euros(suivi['resume']['total']['montant'])}",
    )

    titre("7. La livraison progresse")
    try:
        appel("livraison", "PUT", f"/livraisons/{lid}/statut", {"statut": "EN_ROUTE"})
        verifier(False, "EN_ROUTE sans livreur doit être refusé")
    except ErreurHttp as erreur:
        verifier(erreur.code == 409, f"refus : {erreur.detail}")
    appel("livraison", "POST", f"/livraisons/{lid}/livreur", {"livreurId": "livreur_12", "nom": "Samir"})
    appel("livraison", "PUT", f"/livraisons/{lid}/statut", {"statut": "EN_ROUTE"})
    suivi = attendre(
        "suivi en route",
        lambda: (lambda s: s if s["statutTechnique"] == "EN_ROUTE" else None)(get("suivi", f"/suivis/{cid}")),
    )
    verifier(True, f"Suivi : « {suivi['statutAffiche']} »")
    attendre(
        "réplica livraison EN_ROUTE dans Commande",
        lambda: get("commande", f"/commandes/{cid}")["replicaLivraison"]["statut"] == "EN_ROUTE",
    )
    try:
        appel(
            "commande", "PUT", f"/commandes/{cid}/adresse-livraison",
            {"ligne1": "1 place de la République", "codePostal": "75003", "ville": "Paris"},
        )
        verifier(False, "changement d'adresse après le départ doit être refusé")
    except ErreurHttp as erreur:
        verifier(erreur.code == 409, f"Commande refuse le changement d'adresse : {erreur.detail}")
    appel("livraison", "PUT", f"/livraisons/{lid}/statut", {"statut": "LIVREE"})
    suivi = attendre(
        "suivi livré",
        lambda: (lambda s: s if s["statutTechnique"] == "LIVREE" else None)(get("suivi", f"/suivis/{cid}")),
    )
    etapes = [e["statut"] for e in suivi["chronologie"]]
    verifier(
        etapes == ["COMMANDE_VALIDEE", "EN_PREPARATION", "EN_ROUTE", "LIVREE"],
        f"chronologie : {' -> '.join(etapes)}",
    )

    titre("8. Idempotence : un événement redélivré est ignoré")
    sortie = redis_cli("bus", "XREVRANGE", "evenements:vers:suivi", "+", "-", "COUNT", "1").splitlines()
    evenement = json.loads(sortie[2])
    redis_cli("bus", "XADD", "evenements:vers:suivi", "*", "event", sortie[2], "eventType", evenement["eventType"])
    print(f"  {evenement['eventType']} {evenement['eventId']} republié sur le bus")
    time.sleep(1.5)
    apres = get("suivi", f"/suivis/{cid}")
    verifier(apres["chronologie"] == suivi["chronologie"], "doublon ignoré : chronologie inchangée")

    titre("9. Reconstruction de la projection par rejeu des événements")
    resultat = appel("suivi", "POST", "/admin/reconstruire")
    reconstruit = get("suivi", f"/suivis/{cid}")
    verifier(
        reconstruit == apres,
        f"{resultat['evenementsRejoues']} événements rejoués, {resultat['projections']} suivis : projection identique",
    )

    titre("10. Contrats et outbox")
    contrat = json.loads((RACINE / "Events.json").read_text(encoding="utf-8"))
    obligatoires = contrat["convention"]["champsObligatoires"]
    types_attendus = {e["eventType"] for e in contrat["evenements"]}
    vus = set()
    for recepteur in ("commande", "livraison", "suivi"):
        sortie = redis_cli("bus", "XRANGE", "evenements:vers:" + recepteur, "-", "+").splitlines()
        for ligne in sortie:
            if ligne.startswith("{"):
                evt = json.loads(ligne)
                manquants = [c for c in obligatoires if c not in evt]
                if manquants:
                    raise SystemExit(f"ÉCHEC : {evt['eventType']} sans {manquants}")
                vus.add(evt["eventType"])
    verifier(vus <= types_attendus, f"{len(vus)} types d'événements observés, tous conformes à Events.json")
    attendre("outbox Restaurant vidée", lambda: get("restaurant", "/outbox?publie=false") == [])
    verifier(True, "outbox MongoDB : aucun événement en attente")
    rejets = sum(len(get(s, "/evenements")["rejetes"]) for s in ("commande", "livraison", "suivi"))
    verifier(rejets == 0, "aucun événement rejeté par les consommateurs")

    print(
        f"\nVALIDATION_OK verifications={verifications} commande={cid} livraison={lid} "
        f"services=4 bases=MongoDB+Redis bus=RedisStreams"
    )


if __name__ == "__main__":
    try:
        main()
    except urllib.error.URLError as erreur:
        raise SystemExit(f"Services injoignables ({erreur.reason}). Lancer d'abord : docker compose up -d --build --wait")
