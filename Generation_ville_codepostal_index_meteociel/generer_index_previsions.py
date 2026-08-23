#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generer_index_previsions.py (version autonome)
--------------------------------------------------
Construit un fichier JSON associant chaque commune française connue de
Météociel (déduite de ``cities_database.json`` uniquement - filtre sur le
champ ``"country": "france"``) à son IDENTIFIANT DE PRÉVISIONS Météociel -
c'est-à-dire l'identifiant numérique qu'on trouve dans une URL du type
https://www.meteociel.fr/previsions/29154/buc.htm, DIFFÉRENT du city_id des
stations (la clé de ``cities_database.json``) : les prévisions utilisent
leur propre numérotation, indépendante de celle des stations.

La clé du fichier de sortie est le libellé officiel Météociel "Nom (CP)",
par ex. ``"Buc (78530)": "29154"`` - pas seulement le nom de la commune.
Quand Météociel ne renvoie qu'un seul résultat pour une commune (cas le
plus fréquent), il redirige directement vers la page de prévisions sans
donner le code postal dans la réponse de recherche : ce script fait alors
une seconde requête vers cette page de destination pour aller le chercher
(voir ``_libelle_avec_code_postal``) - ce qui double approximativement le
nombre de requêtes HTTP par rapport à une version qui se contenterait du
nom recherché comme clé.

Un fichier de progression interne (``identifiants_previsions_progres.json``
par défaut, voir ``--progres``) garde la correspondance nom recherché -> 
(identifiant, libelle) pour permettre la reprise : le fichier de sortie
final, lui, ne peut pas servir à ça puisque ses clés (les libellés "Nom
(CP)") ne correspondent pas forcément aux noms recherchés dans
cities_database.json (accents, casse, tirets...).

Contrairement aux versions précédentes, ce script est AUTONOME : il ne
dépend d'aucun des autres fichiers Python du projet (ni meteo_decision.py,
ni geolocalisation_stations.py, ni des fichiers dérivés comme
index_villes.json ou codes_postaux_insee.json), ni même du paquet
meteociel-api (dont le sélecteur HTML de la page de désambiguïsation est de
toute façon cassé - voir ``_chercher_candidats`` ci-dessous, qui fait
l'appel HTTP et le parsing elle-même). Seul ``cities_database.json`` (à
côté de ce script) et le paquet ``requests`` sont nécessaires.

Limite induite par cette autonomie (à noter honnêtement) : sans base de
codes postaux, on ne peut plus départager deux communes françaises
distinctes portant EXACTEMENT le même nom (ex. deux "Balan" dans des
départements différents) - un tel cas, s'il subsiste après le filtre
France ci-dessous, finit dans le fichier d'erreurs plutôt que d'être résolu
au hasard. En pratique, ``cities_database.json`` ne recense qu'environ
12 800 communes (celles ayant une station météo), et une même orthographe
exacte y est rare pour deux communes distinctes, mais Météociel peut malgré
tout renvoyer une telle commune tierce (hors de cette base) dans ses propres
résultats de recherche - c'est afin d'écarter ces communes tierces
(françaises ou étrangères) au maximum que le filtrage ci-dessous se fait
aussi par correspondance exacte du nom recherché.

Utilisation :
    pip install requests
    python generer_index_previsions.py

Options :
    --delai N              délai en secondes entre deux requêtes (défaut 1.0)
    --limite N              nombre max de communes traitées cette exécution
    --sortie chemin.json / --erreurs chemin.json
                            fichiers de sortie (défaut : à côté du script)
    --sauvegarde-tous-les N sauvegarde tous les N succès (défaut 20)
    --debug                 affiche la réponse brute pour la 1re erreur
                            "introuvable" rencontrée, puis s'arrête
    --retenter-ambigus       retente les communes déjà marquées "ambigu"
                            (utile après une évolution du filtrage/de la
                            désambiguïsation ci-dessous)

Le script reprend automatiquement là où il s'était arrêté (les communes
déjà présentes dans le fichier de sortie ou d'erreurs sont sautées), et
sauvegarde régulièrement pour ne rien perdre en cas d'interruption.
"""

import argparse
import json
import os
import re
import sys
import time
import traceback

import requests

_ICI = os.path.dirname(os.path.abspath(__file__))
CHEMIN_CITIES = os.path.join(_ICI, "cities_database.json")
CHEMIN_SORTIE_DEFAUT = os.path.join(_ICI, "identifiants_previsions.json")
CHEMIN_ERREURS_DEFAUT = os.path.join(_ICI, "identifiants_previsions_erreurs.json")
# Fichier de progression interne : contrairement au fichier de sortie final
# (qui doit rester au format simple "Nom (CP)": id demandé), ce fichier
# garde la correspondance nom_recherche -> {id, libelle} pour permettre la
# reprise (on ne peut pas se resservir des clés du fichier de sortie pour
# ça, puisqu'elles ne sont plus les noms recherchés dans cities_database).
CHEMIN_PROGRES_DEFAUT = os.path.join(_ICI, "identifiants_previsions_progres.json")

# ---------------------------------------------------------------------------
# En-têtes de navigateur réel sur toutes les requêtes : par défaut, la
# bibliothèque 'requests' envoie un User-Agent du type "python-requests/2.x"
# que de nombreux sites bloquent ou traitent différemment (page vide,
# captcha...) - ce qui peut se traduire par un taux d'échec massif et
# systématique plutôt que des échecs isolés sur des villes réellement
# introuvables ou ambiguës.
# ---------------------------------------------------------------------------
_EN_TETES_NAVIGATEUR = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
    "Referer": "https://www.meteociel.fr/",
}


class TooManyCitiesError(Exception):
    """Plusieurs villes correspondent encore à la recherche après filtrage
    France et tentative de correspondance exacte du nom (voir
    ``resoudre_identifiant_previsions``)."""


def _requete(url, **kwargs):
    en_tetes = {**_EN_TETES_NAVIGATEUR, **(kwargs.pop("headers", None) or {})}
    return requests.get(url, headers=en_tetes, timeout=10, **kwargs)


# ---------------------------------------------------------------------------
# Liste des communes à interroger, tirée UNIQUEMENT de cities_database.json
# ---------------------------------------------------------------------------
def _nom_affichage(names):
    """Nom à utiliser comme ville Météociel : le premier nom connu de la
    station, avec une capitalisation soignée - même règle que
    geolocalisation_stations._nom_affichage, pour rester cohérent avec le
    reste de l'application."""
    if not names:
        return "?"
    return names[0].strip().title()


def communes_francaises_uniques():
    """Charge cities_database.json et renvoie la liste dédoublonnée des
    noms de communes françaises (``"country": "france"``), triée pour un
    déroulement reproductible d'une exécution à l'autre.

    Dédoublonnage par nom affiché (insensible à la casse) : plusieurs
    entrées de cities_database.json (une par station) peuvent correspondre
    à la même commune (ex. stations "secondaire" et "amateur" toutes deux
    présentes pour Buc), pour laquelle l'identifiant de prévisions est le
    même - inutile de l'interroger deux fois. Voir la mise en garde en
    en-tête du module sur les rares communes distinctes homonymes."""
    with open(CHEMIN_CITIES, encoding="utf-8") as f:
        cities = json.load(f)

    vus = set()
    noms = []
    for infos in cities.values():
        if infos.get("country") != "france":
            continue
        nom = _nom_affichage(infos.get("names"))
        cle = nom.lower()
        if cle in vus:
            continue
        vus.add(cle)
        noms.append(nom)

    noms.sort(key=str.lower)
    return noms


# ---------------------------------------------------------------------------
# Résolution de l'identifiant de prévisions par nom (recherche + filtrage)
# ---------------------------------------------------------------------------
def _extraire_code_postal(libelle):
    """Extrait un code postal entre parenthèses d'un libellé Météociel du
    type 'Buc (78530)', ou None si absent (ex. homonyme étranger annoté
    d'un nom de pays ou d'un code ISO à 2 lettres)."""
    m = re.search(r"\((\d{4,5})\)\s*$", libelle)
    return m.group(1) if m else None


def _ne_garder_que_france(candidats):
    """Filtre ``candidats`` pour ne garder que des communes vraisemblablement
    françaises. Sans base de codes postaux de référence (ce script n'a
    accès qu'à cities_database.json - voir la mise en garde en en-tête du
    module), on approxime "commune française" par : le libellé se termine
    par un code purement NUMÉRIQUE à 4 ou 5 chiffres entre parenthèses - les
    homonymes étrangers renvoyés par Météociel sont eux annotés d'un nom de
    pays en toutes lettres (ex. "(Brésil)") ou d'un code ISO à 2 lettres
    (ex. "(IN)"), jamais d'un nombre à 4-5 chiffres.

    Approximation, pas une garantie absolue : quelques pays voisins
    (Belgique, Suisse...) ont eux aussi des codes postaux purement
    numériques à 4 chiffres, qui pourraient en théorie être pris à tort
    pour une commune française. Si aucun candidat ne passe ce filtre, la
    liste d'origine est renvoyée inchangée plutôt que de tout écarter."""
    filtres = [(i, l) for i, l in candidats if _extraire_code_postal(l) is not None]
    return filtres or candidats


def _libelle_avec_code_postal(prefixe_mode, chemin, repli):
    """Cas de la redirection directe (une seule ville trouvée) : la réponse
    de recherche ne contient pas le code postal, seulement l'URL de la page
    de prévisions. On va donc le chercher sur cette page elle-même, dont la
    balise meta-description / le titre contiennent toujours un segment du
    type « ... pour Buc ( 78530 ) ... ».

    Renvoie ``repli`` (le nom recherché, sans code postal) si la page de
    destination n'a pas pu être récupérée ou n'a pas le format attendu -
    mieux vaut un résultat incomplet qu'une exception qui ferait échouer
    toute la commune."""
    try:
        reponse = _requete(f"https://www.meteociel.fr/{prefixe_mode}/{chemin}")
    except requests.RequestException:
        return repli
    if not reponse.ok:
        return repli
    m = re.search(r"pour\s+([^<(]+?)\s*\(\s*\xa0?\s*(\d{4,5})\s*\xa0?\s*\)", reponse.text)
    if not m:
        return repli
    nom, cp = m.groups()
    nom = nom.replace("\xa0", " ").strip()
    return f"{nom} ({cp})"


def _chercher_candidats(nom_recherche):
    """Interroge directement le moteur de recherche de villes de Météociel
    (prevville.php) et renvoie la liste des candidats ``(identifiant,
    libelle)`` trouvés pour ``nom_recherche``.

    Reproduit à la main la logique de ``meteociel.forecasts.
    get_forecast_url`` (paquet meteociel-api) SANS en dépendre : ce paquet
    plante avec ``AttributeError: 'NoneType' object has no attribute
    'find_all'`` dès que la page de désambiguïsation a une structure HTML
    légèrement différente de celle attendue par son sélecteur
    (``<table border="0" width="300px">``, qui ne correspond plus à rien
    sur le site actuel) - un problème qu'on évite ici en extrayant
    nous-mêmes les candidats par expression régulière, quelle que soit la
    structure exacte de la page.

    Lève ``ValueError`` si Météociel ne renvoie aucun résultat,
    ``ConnectionError`` en cas de problème réseau."""
    reponse = _requete(
        "https://www.meteociel.fr/prevville.php",
        params={"action": "getville", "villeid": "", "ville": nom_recherche, "envoyer": "OK"},
    )
    if not reponse.ok:
        raise ConnectionError(f"connection failed with code: {reponse.status_code}")

    # Cas 1 : un seul résultat -> Météociel redirige directement (balise
    # <script> avec location.href), sans page de choix intermédiaire.
    m_direct = re.search(r"<script lang=javascript>location.href='/([^'^/]+)/([^']+)'", reponse.text)
    if m_direct:
        prefixe_mode, chemin = m_direct.groups()
        id_match = re.match(r"(\d+)/", chemin)
        if id_match:
            identifiant = id_match.group(1)
            libelle = _libelle_avec_code_postal(prefixe_mode, chemin, repli=nom_recherche)
            return [(identifiant, libelle)]

    # Cas 2 : page de choix entre plusieurs villes -> extraction manuelle de
    # tous les candidats (identifiant, libellé), par le même motif que celui
    # utilisé en interne par meteociel-api, mais sans passer par son
    # sélecteur BeautifulSoup cassé.
    candidats = []
    for m in re.finditer(r'<li>\s*<a href="/([^"/]+)/([^"]+)">\s*([^<]+?)\s*</a>\s*</li>', reponse.text):
        _prefixe_mode, chemin, libelle = m.groups()
        id_match = re.match(r"(\d+)/", chemin)
        if not id_match:
            continue
        identifiant = id_match.group(1)
        libelle = libelle.replace("\xa0(\xa0", " (").replace("\xa0)", ")").strip()
        candidats.append((identifiant, libelle))

    if not candidats:
        raise ValueError(f"Aucune ville trouvée par Météociel pour la recherche « {nom_recherche} ».")

    return candidats


def resoudre_identifiant_previsions(nom_recherche):
    """Résout l'identifiant de prévisions Météociel correspondant à
    ``nom_recherche``. Renvoie le tuple ``(identifiant, libelle)`` où
    ``libelle`` est du type ``"Buc (78530)"`` - c'est ce libellé qui sert
    de clé dans le fichier de sortie final, pas ``nom_recherche`` lui-même
    (qui peut différer légèrement de l'orthographe officielle Météociel et,
    surtout, ne contient pas le code postal).

    1. Si Météociel ne renvoie qu'un seul résultat, il est renvoyé
       directement (cas de loin le plus fréquent).
    2. Sinon, les candidats non français sont écartés (voir
       ``_ne_garder_que_france``).
    3. Sinon, un candidat dont le libellé (nom seul, sans code postal)
       correspond exactement à ``nom_recherche`` est renvoyé s'il est
       unique.
    4. Sinon, s'il ne reste qu'un seul candidat français, il est renvoyé.
    5. Sinon, lève ``TooManyCitiesError`` avec la liste lisible des
       candidats restants (ambiguïté réelle entre plusieurs communes
       françaises homonymes, ex. deux communes fusionnées partageant le
       même code postal - non résoluble sans information supplémentaire)."""
    candidats = _chercher_candidats(nom_recherche)

    if len(candidats) == 1:
        return candidats[0]

    candidats = _ne_garder_que_france(candidats)

    if len(candidats) == 1:
        return candidats[0]

    nom_normalise = nom_recherche.strip().lower()
    exacts = [
        (i, l) for i, l in candidats
        if re.sub(r"\s*\(\d{4,5}\)\s*$", "", l).strip().lower() == nom_normalise
    ]
    if len(exacts) == 1:
        return exacts[0]

    raise TooManyCitiesError(
        "too many cities can match your search, please choose one city in the following list:\n"
        + "\n".join(f"- {libelle}" for _, libelle in candidats)
    )


# ---------------------------------------------------------------------------
# Persistance (chargement/sauvegarde des fichiers de sortie)
# ---------------------------------------------------------------------------
def charger_json(chemin):
    if os.path.exists(chemin):
        with open(chemin, encoding="utf-8") as f:
            return json.load(f)
    return {}


def sauvegarder_json(chemin, donnees):
    # Écriture via un fichier temporaire puis remplacement atomique, pour ne
    # jamais laisser un fichier de sortie tronqué/corrompu en cas
    # d'interruption (Ctrl+C, coupure réseau...) pile pendant l'écriture.
    chemin_tmp = chemin + ".tmp"
    with open(chemin_tmp, "w", encoding="utf-8") as f:
        json.dump(donnees, f, ensure_ascii=False, indent=2, sort_keys=True)
    os.replace(chemin_tmp, chemin)


# ---------------------------------------------------------------------------
# Boucle principale
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--delai", type=float, default=1.0,
                         help="Délai en secondes entre deux requêtes (défaut : 1.0)")
    parser.add_argument("--limite", type=int, default=None,
                         help="Nombre maximal de communes à traiter lors de cette exécution "
                              "(défaut : toutes les communes restantes)")
    parser.add_argument("--sortie", default=CHEMIN_SORTIE_DEFAUT,
                         help=f"Fichier de sortie (défaut : {CHEMIN_SORTIE_DEFAUT})")
    parser.add_argument("--erreurs", default=CHEMIN_ERREURS_DEFAUT,
                         help=f"Fichier des échecs/ambiguïtés non résolues (défaut : {CHEMIN_ERREURS_DEFAUT})")
    parser.add_argument("--progres", default=CHEMIN_PROGRES_DEFAUT,
                         help=f"Fichier de progression interne, pour la reprise (défaut : {CHEMIN_PROGRES_DEFAUT})")
    parser.add_argument("--sauvegarde-tous-les", type=int, default=20,
                         help="Sauvegarde le fichier de sortie tous les N succès (défaut : 20)")
    parser.add_argument("--debug", action="store_true",
                         help="Affiche un aperçu brut de la réponse HTTP à la première erreur "
                              "'introuvable' rencontrée (pour vérifier s'il s'agit d'un vrai 0 "
                              "résultat ou d'un blocage/captcha), puis arrête le script.")
    parser.add_argument("--retenter-ambigus", action="store_true",
                         help="Retente les communes déjà marquées 'ambigu' dans le fichier "
                              "d'erreurs (utile après une évolution du filtrage/de la "
                              "désambiguïsation). Les autres types d'erreur ('introuvable', "
                              "'autre') restent sautés comme d'habitude.")
    args = parser.parse_args()

    if args.delai < 0.3:
        print(
            f"⚠ --delai {args.delai}s est très agressif : si Météociel bloque déjà le trafic "
            "automatisé (voir --debug pour vérifier), un délai plus court aggravera un éventuel "
            "blocage IP au lieu de le résoudre. Envisagez d'abord --debug --limite 1 pour "
            "diagnostiquer avant d'accélérer.\n"
        )

    if not os.path.exists(CHEMIN_CITIES):
        print(f"Fichier introuvable : {CHEMIN_CITIES}\n"
              "Lancez ce script depuis le dossier qui contient cities_database.json.")
        sys.exit(1)

    communes = communes_francaises_uniques()
    progres = charger_json(args.progres)
    erreurs = charger_json(args.erreurs)

    if args.retenter_ambigus:
        cles_ambigues = [cle for cle, info in erreurs.items() if info.get("type") == "ambigu"]
        for cle in cles_ambigues:
            del erreurs[cle]
        print(f"(--retenter-ambigus : {len(cles_ambigues)} communes anciennement 'ambigu' "
              f"remises dans le lot à traiter)")

    a_faire = [nom for nom in communes if nom not in progres and nom not in erreurs]

    print(f"{len(communes)} communes françaises au total, {len(progres)} déjà résolues, "
          f"{len(erreurs)} déjà en erreur, {len(a_faire)} restant à traiter.")

    if args.limite:
        a_faire = a_faire[: args.limite]
        print(f"(--limite {args.limite} : {len(a_faire)} communes traitées lors de cette exécution)")

    def resultats_finaux():
        """Reconstruit le dict final "Nom (CP)": id à partir de progres."""
        return {info["libelle"]: info["id"] for info in progres.values()}

    def sauvegarder_tout():
        sauvegarder_json(args.progres, progres)
        sauvegarder_json(args.erreurs, erreurs)
        sauvegarder_json(args.sortie, resultats_finaux())

    depuis_derniere_sauvegarde = 0
    traitees = 0
    try:
        for nom in a_faire:
            try:
                identifiant, libelle = resoudre_identifiant_previsions(nom)
                progres[nom] = {"id": identifiant, "libelle": libelle}
                depuis_derniere_sauvegarde += 1
            except TooManyCitiesError as e:
                erreurs[nom] = {"type": "ambigu", "detail": str(e)}
            except ValueError as e:
                if args.debug:
                    reponse = _requete(
                        "https://www.meteociel.fr/prevville.php",
                        params={"action": "getville", "villeid": "", "ville": nom, "envoyer": "OK"},
                    )
                    print(f"\n--- DEBUG : réponse brute pour « {nom} » ---")
                    print(f"Code HTTP : {reponse.status_code}  |  Taille : {len(reponse.text)} caractères")
                    print(reponse.text[:1000])
                    print("--- fin de l'aperçu (voir --debug) ---\n")
                    print("Arrêt (mode --debug : une seule ville examinée).")
                    sauvegarder_tout()
                    return
                erreurs[nom] = {"type": "introuvable", "detail": str(e)}
            except ConnectionError as e:
                # Problème réseau ponctuel : on ne le compte pas comme une
                # erreur définitive (il sera retenté à la prochaine
                # exécution, la clé n'étant ajoutée ni à resultats ni à
                # erreurs) - mais on interrompt la boucle plutôt que
                # d'enchaîner des échecs (connexion probablement coupée).
                print(f"\nErreur réseau sur « {nom} » : {e}\nArrêt (relancez le script pour reprendre).")
                break
            except Exception as e:  # pragma: no cover - robustesse générale
                erreurs[nom] = {
                    "type": "autre",
                    "detail": f"{type(e).__name__}: {e}",
                    "traceback": traceback.format_exc(),
                }

            traitees += 1
            if nom in progres:
                info = progres[nom]
                statut = f"{info['libelle']} -> {info['id']}"
            else:
                info_erreur = erreurs.get(nom, {})
                statut = f"{info_erreur.get('type', '?')} — {info_erreur.get('detail', '')}"
            print(f"[{traitees}/{len(a_faire)}] {nom} -> {statut}")

            if depuis_derniere_sauvegarde >= args.sauvegarde_tous_les:
                sauvegarder_tout()
                depuis_derniere_sauvegarde = 0

            time.sleep(args.delai)
    except KeyboardInterrupt:
        print("\nInterrompu par l'utilisateur.")
    finally:
        sauvegarder_tout()
        print(f"\nSauvegardé : {len(progres)} résolues -> {args.sortie} "
              f"(clé = \"Nom (CP)\", ex. \"Buc (78530)\": \"29154\")")
        print(f"           {len(erreurs)} en erreur -> {args.erreurs}")
        print("Relancez simplement le script pour reprendre là où il s'est arrêté.")


if __name__ == "__main__":
    main()
