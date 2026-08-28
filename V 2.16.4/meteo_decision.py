#!/usr/bin/env python3
"""
Outil d'aide à la décision agronomique basé sur les prévisions météo Météociel.
--------------------------------------------------------------------------------

Ce module s'appuie sur le paquet non officiel ``meteociel-api``
(https://meteociel-api.readthedocs.io/) pour récupérer les prévisions (jusqu'à
3 jours) ou tendances (jusqu'à 10 jours) météo d'une ville, puis applique des
règles agronomiques simples (score pondéré) afin de suggérer le meilleur
moment pour réaliser une action culturale (semis, plantation, récolte...).

Important : il ne s'agit PAS d'une intelligence artificielle prédictive au
sens strict, mais d'un système à base de règles qui formalise des principes
agronomiques de bon sens :
    - éviter le gel pour les semis et plantations,
    - éviter la pluie battante et le vent fort au moment de planter,
    - privilégier le temps sec pour la récolte,
    - etc.
Les recommandations doivent rester indicatives : elles ne remplacent pas
l'observation du terrain ni l'expérience du maraîcher.

Installation requise :
    pip install meteociel-api pandas
"""

import datetime
import os
import re
import json


_ICI = os.path.dirname(os.path.abspath(__file__))

# Source des identifiants ("city_id") Météociel utilisés pour les prévisions
# - voir _construire_index_previsions ci-dessous pour le détail du pourquoi
# ce fichier remplace l'ancien prevision_id.json (doublons non résolus).
CHEMIN_CITIES_OLD = os.path.join(_ICI, "cities_database_old.json")

_cache_previsions = {"index": None}

try:
    from meteociel.forecasts import forecast as _meteociel_forecast
    from meteociel.stations import station_conv as _station_conv, station_wind_dir as _station_wind_dir
    from meteociel.utils import get_data_from_html as _get_data_from_html
    from requests import get as _http_get
    METEOCIEL_AVAILABLE = True
    METEOCIEL_IMPORT_ERROR = None
except ImportError as exc:  # pragma: no cover
    METEOCIEL_AVAILABLE = False
    METEOCIEL_IMPORT_ERROR = exc

try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:  # pragma: no cover
    PANDAS_AVAILABLE = False

import geolocalisation_stations as gs


class PlusieursVillesTrouvees(Exception):
    """
    Levée quand un nom de ville tapé à la main correspond, une fois
    comparé localement à la base de villes françaises (voir
    geolocalisation_stations.rechercher_villes), à plusieurs villes
    françaises distinctes - il faut alors demander explicitement à
    l'utilisateur de préciser laquelle avant tout appel réseau.

    L'attribut ``candidats`` contient la liste des villes concernées (voir
    ``geolocalisation_stations.rechercher_villes`` pour le format - chaque
    candidat inclut son identifiant Météociel ``id``), à proposer à
    l'utilisateur (ex. via ``dialogue_localisation``) avant de rappeler
    ``recuperer_historique_par_id`` avec le city_id choisi.
    """

    def __init__(self, candidats):
        self.candidats = candidats
        aperçu = ", ".join(c["nom"] for c in candidats[:8])
        suffixe = "..." if len(candidats) > 8 else ""
        super().__init__(
            f"Plusieurs villes françaises correspondent à cette recherche : "
            f"{aperçu}{suffixe}. Veuillez préciser (ex. via le bouton de "
            f"localisation, onglet « Recherche par nom »)."
        )


def _resoudre_ville_france_id(ville: str):
    """
    Tente de résoudre un nom de ville tapé à la main vers un identifiant
    Météociel ("city_id") unique, en le comparant localement (sans appel
    réseau) aux villes françaises connues de Météociel (voir
    geolocalisation_stations.rechercher_villes).

    - Si ``ville`` correspond déjà exactement au nom d'une ville connue,
      son (city_id, nom) est renvoyé sans déclencher de demande de choix,
      même si d'autres villes contiennent ce texte en sous-chaîne.
    - Sinon, si une seule ville française correspond, son (city_id, nom)
      est renvoyé.
    - Si plusieurs villes françaises correspondent, lève
      ``PlusieursVillesTrouvees``.
    - Si aucune ville française ne correspond (orthographe différente,
      ville volontairement étrangère...), renvoie ``(None, ville)`` :
      contrairement à l'ancien comportement, on ne tente plus de laisser
      meteociel-api deviner la ville par lui-même (source d'ambiguïté avec
      des homonymes d'autres pays - voir _station_jour_par_id pour le
      détail du problème) ; l'appelant doit alors demander explicitement à
      l'utilisateur de passer par le sélecteur de localisation.
    """
    candidats = gs.rechercher_villes(ville, pays="france")
    if not candidats:
        return None, ville

    texte_normalise = ville.strip().lower()
    correspondance_exacte = [c for c in candidats if c["nom"].lower() == texte_normalise]
    if len(correspondance_exacte) == 1:
        c = correspondance_exacte[0]
        return c["id"], c["nom"]

    if len(candidats) == 1:
        return candidats[0]["id"], candidats[0]["nom"]

    raise PlusieursVillesTrouvees(candidats)


JOURS_FR = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS_FR = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
           "septembre", "octobre", "novembre", "décembre"]

MODES_DISPONIBLES = {
    "Prévisions (3 jours, choix du modèle)": "forecasts",
    "Tendances (10 jours, modèle GFS uniquement)": "trends",
}

MODELES_DISPONIBLES = ["gfs", "wrf", "wrf-1h", "arome", "arome-1h", "arpege-1h", "iconeu", "icond2"]


def formater_date_fr(d: datetime.date) -> str:
    return f"{JOURS_FR[d.weekday()]} {d.day} {MOIS_FR[d.month - 1]}"


# ---------------------------------------------------------------------------
# Critères agronomiques par type d'action (seuils en °C, mm cumulés/jour,
# km/h). Une valeur à ``None`` signifie que le critère n'est pas appliqué
# (action jugée peu dépendante de la météo extérieure).
# ---------------------------------------------------------------------------
CRITERES_ACTION = {
    "Semis direct": {
        "gel_critique": 0,     # en dessous : rédhibitoire (graines/jeunes plantules)
        "gel_vigilance": 3,    # en dessous : pénalité, vigilance
        "pluie_max": 8,        # mm cumulés/jour : au delà, sol trop détrempé pour semer
        "vent_max": 30,        # km/h : au delà, pénalité (dessèchement, levée de graines fines)
        "temp_ideale": (10, 22),
    },
    "Plantation": {
        "gel_critique": 0,
        "gel_vigilance": 2,
        "pluie_max": 15,       # une pluie modérée aide la reprise, mais pas trop
        "vent_max": 25,        # le vent stresse les jeunes plants repiqués
        "temp_ideale": (10, 24),
    },
    "Semis en pot/plant": {
        # Semis sous abri/en godets : peu dépendant de la météo extérieure.
        "gel_critique": None, "gel_vigilance": None, "pluie_max": None,
        "vent_max": None, "temp_ideale": None,
    },
    "Récolte": {
        "gel_critique": None,
        "gel_vigilance": None,
        "pluie_max": 1,        # on préfère récolter au sec
        "vent_max": 40,
        "temp_ideale": (5, 28),
    },
    "Conservation": {
        # Ne dépend pas de la météo du jour même (conditions de stockage).
        "gel_critique": None, "gel_vigilance": None, "pluie_max": None,
        "vent_max": None, "temp_ideale": None,
    },
    "Forçage": {
        # Généralement réalisé à l'abri / hors sol.
        "gel_critique": None, "gel_vigilance": None, "pluie_max": None,
        "vent_max": None, "temp_ideale": None,
    },
}


class JourEvalue:
    def __init__(self, date, temp_min, temp_max, pluie_totale, vent_max, score, alertes):
        self.date = date
        self.temp_min = temp_min
        self.temp_max = temp_max
        self.pluie_totale = pluie_totale
        self.vent_max = vent_max
        self.score = score
        self.alertes = alertes


# ---------------------------------------------------------------------------
# Récupération des données météo
# ---------------------------------------------------------------------------

# Priorité utilisée pour résoudre les cas où plusieurs stations Météociel
# partagent EXACTEMENT le même libellé affiché une fois mis en forme (ex.
# deux stations distinctes du même village - une "secondaire", une
# "amateur" - toutes deux devenues "Bellegarde-Sur-Valserine" dans
# cities_database.json, alors qu'elles s'appelaient distinctement
# "bellegarde" et "bellegarde man" dans cities_database_old.json). Dans ce
# cas on retient la station jugée la plus fiable plutôt que d'en garder une
# au hasard - voir _construire_index_previsions.
_PRIORITE_TYPE_STATION = {
    "secondaire": 0,
    "synop": 1,
    "metar": 1,
    "amateur": 2,
    "inactive": 3,
}


def _priorite_type_station(type_station):
    return _PRIORITE_TYPE_STATION.get(type_station, 99)


def previsions_disponibles() -> bool:
    """Indique si cities_database_old.json (source des city_id utilisés
    pour les prévisions) est présent."""
    return os.path.exists(CHEMIN_CITIES_OLD)


def _construire_index_previsions(force=False):
    """
    Construit (une seule fois, mise en cache mémoire) l'index "libellé ->
    city_id" utilisé par ``recuperer_previsions``, à partir de
    cities_database_old.json.

    Pourquoi cities_database_old.json plutôt que l'ancien prevision_id.json
    ---------------------------------------------------------------------
    prevision_id.json était un fichier figé, construit séparément sous la
    forme d'un simple dict "libellé affiché -> id". Or de nombreuses villes
    Météociel partagent aujourd'hui le même libellé une fois "embelli" pour
    l'affichage (voir cities_database.json, généré à partir des noms bruts
    de cities_database_old.json) : sur les ~12 800 stations françaises,
    environ 3 600 finissent avec un libellé identique à celui d'une autre
    station du même village (types de station différents - secondaire,
    amateur...). La construction d'un simple dict "libellé -> id" par
    simple écrasement (``d[libelle] = id``) fait alors disparaître
    silencieusement une des deux stations : selon l'ordre de parcours du
    fichier source, on récupère les prévisions d'une station différente de
    celle réellement choisie par l'utilisateur, sans aucun avertissement.
    C'est la source des "doublons" observés.

    On reconstruit donc cet index nous-mêmes, directement depuis
    cities_database_old.json (qui reste la source de vérité pour les
    identifiants), en résolvant explicitement chaque collision de libellé
    par priorité de type de station (voir _PRIORITE_TYPE_STATION, qui
    privilégie les stations officielles "secondaire"/synop/metar avant les
    stations "amateur", elles-mêmes avant les stations "inactive") plutôt
    que par un écrasement arbitraire, et en conservant la trace des
    collisions résolues pour permettre un diagnostic (voir
    ``doublons_previsions``).

    Le libellé utilisé comme clé est construit avec
    ``geolocalisation_stations.etiquette_ville`` - IDENTIQUE au format
    affiché dans le sélecteur de localisation (dialogue_localisation.py),
    en réutilisant les noms "embellis" de cities_database.json quand ils
    sont disponibles pour ce city_id (sinon on retombe sur le nom brut de
    cities_database_old.json) : c'est donc bien le même libellé qui se
    retrouve dans le champ "Ville" de l'application.

    Renvoie un tuple (index, doublons) :
      - index : dict "libellé normalisé (sans accents/casse) -> {'id',
        'libelle_affiche', 'nom_brut', 'type'}" ; ``nom_brut`` est le
        premier nom connu tel quel dans cities_database_old.json, utilisé
        comme ``city_name`` lors de l'appel à meteociel-api (voir
        recuperer_previsions).
      - doublons : dict "libellé affiché -> {'id_retenu', 'ids_ecartes'}",
        uniquement pour les libellés où plusieurs stations sont entrées en
        collision - utile pour un diagnostic éventuel, voir
        ``doublons_previsions``.
    """
    if _cache_previsions["index"] is not None and not force:
        return _cache_previsions["index"]

    if not previsions_disponibles():
        resultat = ({}, {})
        _cache_previsions["index"] = resultat
        return resultat

    with open(CHEMIN_CITIES_OLD, encoding="utf-8") as f:
        cities_old = json.load(f)

    codes_postaux = gs._charger_codes_postaux()
    gps_brut = gs._charger_gps_brut()
    cities_new = gs._charger_cities_database_brute()

    index = {}
    doublons = {}

    for city_id, infos in cities_old.items():
        if infos.get("country") != "france":
            continue
        noms_bruts = infos.get("names") or []
        if not noms_bruts:
            continue

        infos_new = cities_new.get(city_id) or {}
        noms_affiches = infos_new.get("names") or noms_bruts
        nom_affiche = gs._nom_affichage(noms_affiches)

        insee = gps_brut.get(city_id, {}).get("insee")
        code_postal = codes_postaux.get(insee) if insee else None
        type_station = infos.get("station-type")

        libelle = gs.etiquette_ville(nom_affiche, code_postal, type_station)
        cle = gs._sans_accents(libelle)

        entree = {
            "id": city_id,
            "libelle_affiche": libelle,
            "nom_brut": noms_bruts[0],
            "type": type_station,
        }

        existante = index.get(cle)
        if existante is None:
            index[cle] = entree
            continue

        # Collision : deux stations distinctes partagent le même libellé
        # affiché - on garde la plus fiable (voir _PRIORITE_TYPE_STATION)
        # et on note l'id écarté pour diagnostic plutôt que de l'oublier.
        if _priorite_type_station(type_station) < _priorite_type_station(existante["type"]):
            index[cle] = entree
            id_retenu, id_ecarte = city_id, existante["id"]
        else:
            id_retenu, id_ecarte = existante["id"], city_id

        info_doublon = doublons.setdefault(libelle, {"id_retenu": id_retenu, "ids_ecartes": []})
        info_doublon["id_retenu"] = id_retenu
        info_doublon["ids_ecartes"].append(id_ecarte)

    resultat = (index, doublons)
    _cache_previsions["index"] = resultat
    return resultat


def doublons_previsions():
    """Renvoie le dict des collisions de libellé résolues lors de la
    construction de l'index des prévisions (voir
    _construire_index_previsions) - utile pour vérifier/diagnostiquer les
    doublons, sans effet sur le fonctionnement normal de l'application."""
    _, doublons = _construire_index_previsions()
    return doublons


def resoudre_city_id(ville: str):
    """
    Retrouve l'identifiant Météociel ("city_id") et le nom brut à utiliser
    pour une ville, à partir de son libellé affiché (celui renvoyé par le
    sélecteur de localisation - dialogue_localisation.choisir_localisation -
    ou saisi à la main dans l'application), via l'index construit depuis
    cities_database_old.json (voir _construire_index_previsions).

    Renvoie un tuple (city_id, nom_brut). Si aucune correspondance exacte
    n'est trouvée dans l'index (ex. libellé tapé à la main, sans le code
    postal exact, ou légèrement mal orthographié), renvoie (None, ville) :
    l'appelant (recuperer_previsions) se repliera alors sur la recherche
    par nom faite par meteociel-api lui-même, comme auparavant.
    """
    index, _ = _construire_index_previsions()
    entree = index.get(gs._sans_accents(ville.strip()))
    if entree is None:
        return None, ville
    return entree["id"], entree["nom_brut"]


def recuperer_previsions(ville: str, mode: str = "forecasts", modele: str = "gfs"):
    """
    Récupère les prévisions météo Météociel pour une ville donnée.

    L'identifiant Météociel ("city_id") est résolu localement (sans appel
    réseau) via ``resoudre_city_id``, à partir de cities_database_old.json -
    voir _construire_index_previsions pour le détail (et notamment pourquoi
    ce mécanisme remplace l'ancien fichier prevision_id.json, sujet à des
    doublons non résolus). Quand la résolution réussit, le ``city_id`` et le
    nom brut associé sont transmis à meteociel-api, qui n'a alors plus à
    deviner la bonne ville par recherche de nom (source d'ambiguïté avec
    des homonymes d'autres pays). Si aucune correspondance locale n'est
    trouvée, on retombe sur l'ancien comportement (recherche par nom faite
    par meteociel-api lui-même, avec city_id=None).

    Retourne un tuple (nom_ville_trouvee, dataframe) comme
    ``meteociel.forecasts.forecast``.

    Lève ``RuntimeError`` si ``meteociel-api`` (ou pandas) n'est pas installé.
    Toute autre exception (ex. ``ConnectionError``, ``TooManyCitiesError``,
    problème réseau) est laissée remonter telle quelle à l'appelant.
    """
    if not METEOCIEL_AVAILABLE:
        raise RuntimeError(
            "Le paquet 'meteociel-api' n'est pas installé.\n"
            "Installez-le avec : pip install meteociel-api\n"
            f"(Erreur d'import d'origine : {METEOCIEL_IMPORT_ERROR})"
        )
    if not PANDAS_AVAILABLE:
        raise RuntimeError("Le paquet 'pandas' est requis. Installez-le avec : pip install pandas")

    city_id, nom_brut = resoudre_city_id(ville)
    # Quand city_id n'a pas pu être résolu localement, on conserve
    # l'ancien comportement (seul le premier mot du libellé était transmis
    # comme city_name) ; sinon on transmet le nom brut complet associé à
    # l'id retenu, qui n'a plus qu'un rôle de confirmation/affichage côté
    # meteociel-api puisque city_id suffit à lever toute ambiguïté.
    nom_pour_api = nom_brut.split(" ")[0] if city_id is None else nom_brut

    return _meteociel_forecast(city_id=city_id, city_name=nom_pour_api, mode=mode, model=modele)


def agreger_par_jour(df):
    """Agrège le relevé horaire/tri-horaire Météociel par jour civil."""
    data = df.copy()
    if not pd.api.types.is_datetime64_any_dtype(data["date"]):
        data["date"] = pd.to_datetime(data["date"])
    data["jour"] = data["date"].dt.date
    grouped = data.groupby("jour").agg(
        temp_min=("temperature", "min"),
        temp_max=("temperature", "max"),
        pluie_totale=("rain", "sum"),
        vent_max=("wind_spd", "max"),
    ).reset_index()
    return grouped


def evaluer_jour(row, criteres) -> JourEvalue:
    alertes = []
    score = 100.0

    gel_critique = criteres.get("gel_critique")
    gel_vigilance = criteres.get("gel_vigilance")
    pluie_max = criteres.get("pluie_max")
    vent_max_seuil = criteres.get("vent_max")
    temp_ideale = criteres.get("temp_ideale")

    if gel_critique is not None and row["temp_min"] <= gel_critique:
        score -= 100
        alertes.append(f"Risque de gel ({row['temp_min']:.0f} °C) : action déconseillée.")
    elif gel_vigilance is not None and row["temp_min"] <= gel_vigilance:
        score -= 30
        alertes.append(f"Températures fraîches ({row['temp_min']:.0f} °C) : vigilance.")

    if pluie_max is not None and row["pluie_totale"] > pluie_max:
        score -= 25
        alertes.append(f"Pluie importante prévue ({row['pluie_totale']:.1f} mm cumulés).")

    if vent_max_seuil is not None and row["vent_max"] > vent_max_seuil:
        score -= 20
        alertes.append(f"Vent fort prévu ({row['vent_max']:.0f} km/h).")

    if temp_ideale is not None:
        tmin_id, tmax_id = temp_ideale
        milieu = (row["temp_min"] + row["temp_max"]) / 2
        if milieu < tmin_id:
            score -= (tmin_id - milieu) * 2
        elif milieu > tmax_id:
            score -= (milieu - tmax_id) * 2

    score = max(0.0, min(100.0, score))
    return JourEvalue(row["jour"], row["temp_min"], row["temp_max"],
                       row["pluie_totale"], row["vent_max"], score, alertes)


def recommander(action: str, ville: str, mode: str = "forecasts", modele: str = "gfs"):
    """
    Fonction principale de l'outil d'aide à la décision.

    Retourne un tuple (liste_JourEvalue, meilleur_JourEvalue_ou_None, texte_synthese).
    """
    criteres = CRITERES_ACTION.get(action)
    if criteres is None:
        return [], None, f"Action inconnue : {action}"

    if all(v is None for v in criteres.values()):
        return [], None, (
            f"L'action « {action} » est généralement réalisée à l'abri ou hors sol : elle "
            "ne dépend pas directement de la météo extérieure. Aucune analyse météo n'est "
            "nécessaire ; vous pouvez vous fier uniquement aux dates du planning cultural."
        )

    ville_trouvee, df = recuperer_previsions(ville, mode=mode, modele=modele)
    jours = agreger_par_jour(df)

    if jours.empty:
        return [], None, "Aucune donnée météo exploitable n'a été renvoyée par Météociel."

    evalues = [evaluer_jour(row, criteres) for _, row in jours.iterrows()]
    evalues.sort(key=lambda j: j.date)
    meilleur = max(evalues, key=lambda j: j.score)

    lignes = [f"Ville météo utilisée : {ville_trouvee}", ""]
    for j in evalues:
        marqueur = "   <== meilleur moment" if j is meilleur else ""
        lignes.append(
            f"{formater_date_fr(j.date)} : {j.temp_min:.0f} à {j.temp_max:.0f} °C, "
            f"pluie {j.pluie_totale:.1f} mm, vent max {j.vent_max:.0f} km/h "
            f"-> score {j.score:.0f}/100{marqueur}"
        )
        for a in j.alertes:
            lignes.append(f"      ⚠ {a}")

    if meilleur.score >= 70:
        conclusion = (
            f"\nRecommandation : le {formater_date_fr(meilleur.date)} présente les "
            "meilleures conditions pour réaliser cette action."
        )
    elif meilleur.score >= 40:
        conclusion = (
            f"\nRecommandation : le {formater_date_fr(meilleur.date)} est le jour le "
            "moins défavorable de la période analysée, mais les conditions restent "
            "moyennes. Envisagez de reporter si possible."
        )
    else:
        conclusion = (
            "\nRecommandation : aucun jour de la période analysée ne présente de bonnes "
            "conditions (gel, pluie ou vent important). Il est préférable d'attendre une "
            "fenêtre météo plus favorable et de revérifier dans quelques jours."
        )

    texte = "\n".join(lignes) + conclusion
    return evalues, meilleur, texte


# ---------------------------------------------------------------------------
# Vérification de la fenêtre calendaire (à partir du CSV planning_cultural)
# ---------------------------------------------------------------------------
def semaine_courante() -> int:
    return datetime.date.today().isocalendar()[1]


def semaine_dans_fenetre(semaine: int, debut: int, fin: int) -> bool:
    """Teste l'appartenance d'une semaine à un intervalle [debut, fin],
    en gérant le cas où l'intervalle chevauche le changement d'année
    (ex. conservation de novembre à février : debut=44, fin=9)."""
    if debut <= fin:
        return debut <= semaine <= fin
    return semaine >= debut or semaine <= fin


def distance_semaines(semaine: int, debut: int) -> int:
    """Nombre de semaines à attendre avant d'atteindre 'debut' (modulo 52)."""
    return (debut - semaine) % 52


def verifier_calendrier(rows, culture: str, conduite: str, action: str, variete_n=None):
    """
    Vérifie si la semaine courante correspond à la fenêtre recommandée du
    planning cultural (issu du CSV) pour la culture/conduite/action donnés.

    ``rows`` est la liste de dictionnaires du planning (mêmes clés que le
    CSV : culture, conduite, variete_n, action, semaine_debut, semaine_fin...).

    Retourne un texte explicatif.
    """
    semaine = semaine_courante()
    correspondances = [
        r for r in rows
        if r["culture"].strip().lower() == culture.strip().lower()
        and r["conduite"] == conduite
        and r["action"] == action
        and (variete_n in (None, "", "Toutes") or str(r.get("variete_n")) == str(variete_n))
    ]

    if not correspondances:
        return (f"Aucune donnée de planning trouvée pour « {culture} » ({conduite}) - "
                f"{action}. Vérifiez l'orthographe ou la sélection de variété.")

    dans_fenetre = []
    hors_fenetre = []
    for r in correspondances:
        try:
            debut = int(r["semaine_debut"])
            fin = int(r["semaine_fin"])
        except (ValueError, TypeError):
            continue
        if semaine_dans_fenetre(semaine, debut, fin):
            dans_fenetre.append((debut, fin))
        else:
            hors_fenetre.append((debut, fin, distance_semaines(semaine, debut)))

    lignes = [f"Semaine actuelle : {semaine}."]
    if dans_fenetre:
        fenetres_txt = ", ".join(f"semaines {d}-{f}" for d, f in dans_fenetre)
        lignes.append(f"✅ Vous êtes dans une période recommandée du planning ({fenetres_txt}).")
    if hors_fenetre and not dans_fenetre:
        hors_fenetre.sort(key=lambda t: t[2])
        prochain = hors_fenetre[0]
        lignes.append(
            f"❌ Hors période recommandée du planning. Prochaine fenêtre : semaines "
            f"{prochain[0]}-{prochain[1]} (dans {prochain[2]} semaine(s))."
        )
    elif hors_fenetre and dans_fenetre:
        lignes.append(f"(D'autres variétés de cette culture ont une fenêtre différente : "
                       + ", ".join(f"semaines {d}-{f}" for d, f, _ in hors_fenetre) + ".)")

    return "\n".join(lignes)


# ---------------------------------------------------------------------------
# Historique météo (mesures de stations Météociel, jour par jour)
# ---------------------------------------------------------------------------
def base_villes_disponible() -> bool:
    """Indique si la base locale des villes (nécessaire pour l'historique) existe déjà."""
    if not METEOCIEL_AVAILABLE:
        return False
    return os.path.exists(_cities.DATABASE_NAME)


def generer_base_villes():
    """
    Génère la base de villes Météociel (fichier JSON local), nécessaire pour
    interroger les stations (historique). Opération à faire une seule fois :
    elle parcourt le site Météociel pour lister toutes les villes connues,
    ce qui peut prendre plusieurs dizaines de secondes, voire quelques minutes.
    """
    if not METEOCIEL_AVAILABLE:
        raise RuntimeError(
            "Le paquet 'meteociel-api' n'est pas installé.\nInstallez-le avec : pip install meteociel-api"
        )
    _cities.generate_database()


def _parse_heure_locale(texte: str):
    """Convertit une heure du format Météociel ('14h06') en (heure, minute)."""
    m = re.match(r"\s*(\d+)\s*h\s*(\d+)", str(texte))
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def _recuperer_historique_pour_nom(nom_meteociel: str, date_debut: datetime.date, date_fin: datetime.date):
    """
    Logique commune à ``recuperer_historique`` et
    ``recuperer_historique_par_id`` : effectue les appels réseau jour par
    jour (un appel par jour de la période, les données de station étant
    fournies par Météociel une journée à la fois) et assemble le résultat.

    ``nom_meteociel`` est supposé déjà résolu de façon non ambiguë par
    l'appelant (soit via _resoudre_ville_france pour un nom tapé/choisi
    par libellé, soit via _nom_historique_depuis_id pour un city_id déjà
    connu) : cette fonction ne fait plus aucune résolution/désambiguïsation
    elle-même.

    Retourne un tuple (nom_ville_trouvee, dataframe) - voir
    ``recuperer_historique`` pour le détail du format.
    """
    if date_debut > date_fin:
        date_debut, date_fin = date_fin, date_debut

    jours = []
    d = date_debut
    while d <= date_fin:
        jours.append(d)
        d += datetime.timedelta(days=1)

    trames = []
    ville_trouvee = None
    for jour in jours:
        nom, df_jour = _meteociel_station(datetime.datetime(jour.year, jour.month, jour.day), nom_meteociel)
        ville_trouvee = nom
        df_jour = df_jour.copy()
        # NB : la colonne d'horodatage renvoyée par meteociel-api s'appelle
        # "local hour" (et non "time..."). On la retrouve de façon robuste
        # en cherchant "hour" dans le nom de colonne (insensible à la casse),
        # avec un repli sur "time" au cas où une version future du paquet
        # renommerait la colonne.
        colonne_heure = next(
            (c for c in df_jour.columns if "hour" in c.lower() or c.lower().startswith("time")),
            None,
        )
        if colonne_heure is None:
            raise RuntimeError(
                "Impossible de trouver la colonne d'horodatage dans les données de station "
                f"Météociel pour {jour.isoformat()} (colonnes reçues : {list(df_jour.columns)})."
            )
        horodatages = []
        for val in df_jour[colonne_heure]:
            hm = _parse_heure_locale(val)
            if hm is None:
                horodatages.append(pd.NaT)
                continue
            h, mnt = hm
            horodatages.append(
                datetime.datetime(jour.year, jour.month, jour.day) + datetime.timedelta(hours=h, minutes=mnt)
            )
        df_jour["datetime"] = horodatages
        trames.append(df_jour)

    if not trames:
        return ville_trouvee, pd.DataFrame()

    combined = pd.concat(trames, ignore_index=True)
    combined = combined.dropna(subset=["datetime"]).sort_values("datetime").reset_index(drop=True)
    return ville_trouvee, combined


def _verifier_prerequis_historique():
    """Vérifications communes à ``recuperer_historique`` et
    ``recuperer_historique_par_id`` (paquets installés, base de villes
    Météociel générée) - lève RuntimeError si l'un des prérequis manque."""
    if not METEOCIEL_AVAILABLE:
        raise RuntimeError(
            "Le paquet 'meteociel-api' n'est pas installé.\nInstallez-le avec : pip install meteociel-api"
        )
    if not PANDAS_AVAILABLE:
        raise RuntimeError("Le paquet 'pandas' est requis. Installez-le avec : pip install pandas")
    if not base_villes_disponible():
        raise RuntimeError(
            "La base de villes Météociel n'a pas encore été générée sur cette machine.\n"
            "Cliquez sur « Générer la base de villes » (une seule fois nécessaire), puis réessayez."
        )


def recuperer_historique(ville: str, date_debut: datetime.date, date_fin: datetime.date):
    """
    Récupère l'historique des mesures de station Météociel (température,
    humidité, vent, pression...) pour une ville désignée par son nom/libellé,
    entre ``date_debut`` et ``date_fin`` (inclus).

    À utiliser quand on ne dispose que d'un nom tapé/choisi par libellé
    (ex. saisie manuelle dans le champ "Ville") - préférer
    ``recuperer_historique_par_id`` quand un city_id est disponible (ex.
    sélection via la pop-up de localisation), qui évite toute ambiguïté de
    nom. Peut lever ``PlusieursVillesTrouvees`` si ``ville`` correspond à
    plusieurs villes françaises distinctes (voir _resoudre_ville_france).

    Retourne un tuple (nom_ville_trouvee, dataframe) - voir
    _recuperer_historique_pour_nom pour le détail du format.

    Lève ``RuntimeError`` si meteociel-api/pandas n'est pas installé ou si la
    base de villes locale n'a pas encore été générée (voir
    ``generer_base_villes``). Toute autre exception réseau est laissée
    remonter telle quelle.
    """
    _verifier_prerequis_historique()

    # Lève l'ambiguïté éventuelle une seule fois, avant les appels réseau
    # (voir PlusieursVillesTrouvees / _resoudre_ville_france ci-dessus).
    ville = _resoudre_ville_france(ville)

    return _recuperer_historique_pour_nom(ville, date_debut, date_fin)


def _charger_cities_old_brute():
    """Charge (en cache) l'intégralité de cities_database_old.json, telle
    quelle - utilisé ici pour retrouver le nom Météociel brut associé à un
    city_id déjà résolu (voir _nom_historique_depuis_id)."""
    if _cache_previsions.get("cities_old_brut") is None:
        if os.path.exists(CHEMIN_CITIES_OLD):
            with open(CHEMIN_CITIES_OLD, encoding="utf-8") as f:
                _cache_previsions["cities_old_brut"] = json.load(f)
        else:
            _cache_previsions["cities_old_brut"] = {}
    return _cache_previsions["cities_old_brut"]


def _nom_historique_depuis_id(city_id):
    """
    Renvoie le nom Météociel brut (tel que connu de
    cities_database_old.json) associé à ``city_id``, à transmettre à
    meteociel.stations.station - voir recuperer_historique_par_id.

    Contrairement aux prévisions (``meteociel.forecasts.forecast`` accepte
    un ``city_id`` direct - voir ``resoudre_city_id`` /
    ``recuperer_previsions``), ``meteociel.stations.station`` n'accepte
    qu'un nom, pas d'identifiant (voir la docstring de
    ``PlusieursVillesTrouvees`` ci-dessus). On retrouve donc ici le nom
    exact associé à CETTE station précise, déjà résolue de façon non
    ambiguë en amont (choisie par l'utilisateur via la pop-up de
    localisation - voir dialogue_localisation.choisir_localisation_avec_id),
    plutôt que de laisser meteociel-api deviner par recherche de nom -
    source d'ambiguïté avec des homonymes d'autres pays.

    Renvoie None si city_id est vide/absent, ou si cities_database_old.json
    est absent ou ne connaît pas cet identifiant (ex. base à régénérer,
    identifiant périmé).
    """
    if not city_id:
        return None
    cities_old = _charger_cities_old_brute()
    infos = cities_old.get(str(city_id))
    if infos is None:
        return None
    noms = infos.get("names") or []
    return noms[0] if noms else None


def recuperer_historique_par_id(city_id, date_debut: datetime.date, date_fin: datetime.date):
    """
    Variante de ``recuperer_historique`` pour le cas où la ville a déjà été
    résolue de façon non ambiguë en amont, typiquement via la pop-up de
    localisation (voir dialogue_localisation.choisir_localisation_avec_id),
    qui renvoie directement l'identifiant Météociel ("city_id") de la
    station choisie plutôt qu'un simple libellé à ré-interpréter.

    Intérêt par rapport à ``recuperer_historique(ville, ...)`` : le nom
    transmis à meteociel-api est retrouvé directement à partir de
    ``city_id`` (donc garanti correspondre à LA station effectivement
    choisie par l'utilisateur), sans repasser par une recherche par nom qui
    pourrait échouer ou lever ``PlusieursVillesTrouvees`` inutilement -
    l'ambiguïté a déjà été levée au moment de la sélection dans la pop-up.

    Mêmes paramètres de dates et même valeur de retour que
    ``recuperer_historique`` (tuple (nom_ville_trouvee, dataframe)).

    Lève ``RuntimeError`` si meteociel-api/pandas n'est pas installé ou si
    la base de villes locale n'a pas encore été générée. Lève
    ``ValueError`` si ``city_id`` ne correspond à aucune station connue de
    cities_database_old.json (fichier absent, ou identifiant inconnu/périmé -
    dans ce cas, se replier sur ``recuperer_historique(nom_affiche, ...)``
    avec le libellé affiché par la pop-up). Toute autre exception réseau
    est laissée remonter telle quelle.
    """
    _verifier_prerequis_historique()

    nom = _nom_historique_depuis_id(city_id)
    if nom is None:
        raise ValueError(
            f"Identifiant de station inconnu ({city_id!r}) : cities_database_old.json "
            "est absent, ou cet identifiant n'y figure pas."
        )

    return _recuperer_historique_pour_nom(nom, date_debut, date_fin)
