# -*- coding: utf-8 -*-
"""
geolocalisation_stations.py
------------------------------
Recherche de la station Météociel la plus proche d'un point GPS donné, afin
de permettre une sélection de ville par carte ou par coordonnées plutôt que
par saisie manuelle du nom exact (voir dialogue_localisation.py).

Combine deux fichiers de données locales (aucun accès réseau requis) :

  - cities_database.json : la base de villes/stations Météociel telle que
    générée par le paquet meteociel-api (voir
    meteo_decision.generer_base_villes) - identifiant, noms connus, type de
    station ("secondaire", "amateur", "metar", "synop", "inactive"), pays.

  - stations_gps.json : coordonnées GPS (latitude/longitude) des stations
    françaises de type "secondaire" ou "amateur", pré-calculées hors ligne
    par le script suivant :

      1. L'identifiant Météociel de ces deux types de station encode le
         département + le code commune INSEE + un numéro de station, ex.
         "10005001" -> dept "10", commune "005" -> code INSEE "10005"
         (Amance, Aube), numéro de station "001". (Cas particulier : les
         identifiants commençant par l'ancien département "20" - Corse -
         sont essayés successivement en "2A" puis "2B".)
      2. Ce code INSEE est croisé avec le jeu de données ouvert
         "france-cities" (tawfikyassine/france-cities, lui-même basé sur
         data.gouv.fr / La Poste) pour récupérer la latitude/longitude du
         centre de la commune.

    Couverture obtenue : environ 97 % des stations "secondaire"/"amateur"
    (~91 % de l'ensemble des stations françaises de la base, soit près de
    11 700 stations sur 12 800). Les stations synoptiques historiques
    (identifiants courts type "7482") et certaines stations METAR
    d'aéroport utilisent un autre système d'identifiants (codes OMM/ICAO)
    non couvert par cette dérivation : elles n'ont donc pas de coordonnées
    GPS connues ici, mais restent sélectionnables via la recherche par nom
    classique (elles ne sont simplement pas proposées par la recherche "la
    plus proche").

Ces deux fichiers sont attendus dans le même dossier que ce module.
"""

import json
import math
import os
import unicodedata

_ICI = os.path.dirname(os.path.abspath(__file__))
CHEMIN_CITIES = os.path.join(_ICI, "cities_database.json")
CHEMIN_GPS = os.path.join(_ICI, "stations_gps.json")

# Table de correspondance code INSEE -> code postal, utilisée uniquement pour
# enrichir l'affichage de la recherche par nom (voir rechercher_villes) - un
# même code INSEE a un unique code postal dans ce jeu de données. Fichier
# dérivé du jeu de données ouvert "france-cities" (tawfikyassine/france-cities,
# lui-même basé sur data.gouv.fr / La Poste), au même titre que stations_gps.json.
# Optionnel : son absence désactive seulement l'affichage du code postal, sans
# empêcher la recherche par nom de fonctionner.
CHEMIN_CODES_POSTAUX = os.path.join(_ICI, "codes_postaux_insee.json")

_cache = {"stations": None, "cities_brut": None, "gps_brut": None, "codes_postaux": None}


def stations_disponibles():
    """Indique si les deux fichiers de données nécessaires sont présents."""
    return os.path.exists(CHEMIN_CITIES) and os.path.exists(CHEMIN_GPS)


def _nom_affichage(names):
    """Nom à afficher/à utiliser comme 'ville' Météociel : le premier nom
    connu de la station, avec une capitalisation soignée."""
    if not names:
        return "?"
    return names[0].strip().title()


def charger_stations(force=False):
    """Charge (une seule fois, mise en cache mémoire) la liste des stations
    françaises géolocalisées.

    Renvoie une liste de dicts {"id", "nom", "type", "lat", "lon"} - liste
    vide si les fichiers de données sont absents."""
    if _cache["stations"] is not None and not force:
        return _cache["stations"]

    if not stations_disponibles():
        _cache["stations"] = []
        return []

    with open(CHEMIN_CITIES, encoding="utf-8") as f:
        cities = json.load(f)
    with open(CHEMIN_GPS, encoding="utf-8") as f:
        gps = json.load(f)

    stations = []
    for station_id, coord in gps.items():
        infos = cities.get(station_id)
        if infos is None:
            continue
        stations.append({
            "id": station_id,
            "nom": _nom_affichage(infos.get("names")),
            "type": infos.get("station-type"),
            "lat": coord["lat"],
            "lon": coord["lon"],
        })

    _cache["stations"] = stations
    return stations


def distance_haversine_km(lat1, lon1, lat2, lon2):
    """Distance orthodromique (à vol d'oiseau) entre deux points GPS, en
    kilomètres."""
    rayon_terre_km = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * rayon_terre_km * math.asin(math.sqrt(a))


def stations_les_plus_proches(lat, lon, n=8):
    """Renvoie les n stations géolocalisées les plus proches de (lat, lon),
    triées par distance croissante.

    Chaque élément : {"id", "nom", "type", "lat", "lon", "distance_km"}."""
    resultats = []
    for s in charger_stations():
        d = distance_haversine_km(lat, lon, s["lat"], s["lon"])
        resultats.append({**s, "distance_km": d})
    resultats.sort(key=lambda s: s["distance_km"])
    return resultats[:n]


# ---------------------------------------------------------------------------
# Recherche par nom (toutes les villes/stations Météociel connues, pas
# seulement celles géolocalisées) - utilisée par l'onglet "Recherche par nom"
# de la pop-up de localisation, afin de pouvoir choisir une ville dans une
# liste plutôt que de deviner l'orthographe/le code postal exacts attendus
# par Météociel (ce qui provoque sinon une erreur "TooManyCitiesError", ou
# pire, une sélection silencieuse d'une ville homonyme d'un autre pays pour
# l'historique - voir meteo_decision.recuperer_historique).
# ---------------------------------------------------------------------------
def _sans_accents(texte):
    """Normalise une chaîne pour une comparaison insensible aux accents et à
    la casse (ex. 'Chartres' == 'chârtrès')."""
    decompose = unicodedata.normalize("NFD", str(texte))
    return "".join(c for c in decompose if unicodedata.category(c) != "Mn").lower()


def _charger_cities_database_brute():
    """Charge (en cache) l'intégralité de cities_database.json, telle quelle
    (toutes les villes connues de Météociel, tous pays et tous types de
    station confondus - contrairement à charger_stations() qui ne garde que
    celles géolocalisées via stations_gps.json)."""
    if _cache["cities_brut"] is None:
        if os.path.exists(CHEMIN_CITIES):
            with open(CHEMIN_CITIES, encoding="utf-8") as f:
                _cache["cities_brut"] = json.load(f)
        else:
            _cache["cities_brut"] = {}
    return _cache["cities_brut"]


def _charger_gps_brut():
    """Charge (en cache) stations_gps.json tel quel (id -> lat/lon/insee),
    utilisé ici uniquement pour retrouver le code INSEE d'une ville."""
    if _cache["gps_brut"] is None:
        if os.path.exists(CHEMIN_GPS):
            with open(CHEMIN_GPS, encoding="utf-8") as f:
                _cache["gps_brut"] = json.load(f)
        else:
            _cache["gps_brut"] = {}
    return _cache["gps_brut"]


def _charger_codes_postaux():
    """Charge (en cache) la table de correspondance code INSEE -> code
    postal. Renvoie un dict vide si le fichier est absent (dégradation
    silencieuse : la recherche par nom fonctionne toujours, simplement sans
    affichage du code postal)."""
    if _cache["codes_postaux"] is None:
        if os.path.exists(CHEMIN_CODES_POSTAUX):
            with open(CHEMIN_CODES_POSTAUX, encoding="utf-8") as f:
                _cache["codes_postaux"] = json.load(f)
        else:
            _cache["codes_postaux"] = {}
    return _cache["codes_postaux"]


def rechercher_villes(motif, pays="france", limite=200):
    """Recherche locale (hors ligne, sans appel réseau) parmi toutes les
    villes connues de Météociel dont le nom contient ``motif`` (comparaison
    insensible aux accents/à la casse).

    ``pays`` filtre le résultat sur le pays Météociel exact (ex. "france") ;
    passer None ou "" pour ne pas filtrer par pays.

    Renvoie une liste de dicts {"id", "nom", "type", "pays", "code_postal"}
    (``code_postal`` vaut None si inconnu), triée en mettant en premier les
    résultats dont le code postal est connu, puis par ordre alphabétique.
    Liste vide si ``motif`` est vide ou si cities_database.json est absent."""
    motif_normalise = _sans_accents(motif).strip()
    if not motif_normalise:
        return []

    cities = _charger_cities_database_brute()
    gps = _charger_gps_brut()
    codes_postaux = _charger_codes_postaux()

    resultats = []
    for ville_id, infos in cities.items():
        if pays and infos.get("country") != pays:
            continue
        noms = infos.get("names") or []
        if not any(motif_normalise in _sans_accents(n) for n in noms):
            continue
        insee = gps.get(ville_id, {}).get("insee")
        code_postal = codes_postaux.get(insee) if insee else None
        resultats.append({
            "id": ville_id,
            "nom": _nom_affichage(noms),
            "type": infos.get("station-type"),
            "pays": infos.get("country"),
            "code_postal": code_postal,
        })

    resultats.sort(key=lambda r: (r["code_postal"] is None, r["nom"]))
    return resultats[:limite]
