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

_ICI = os.path.dirname(os.path.abspath(__file__))
CHEMIN_CITIES = os.path.join(_ICI, "cities_database.json")
CHEMIN_GPS = os.path.join(_ICI, "stations_gps.json")

_cache = {"stations": None}


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
