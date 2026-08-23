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
import json
import os
import re

try:
    from meteociel.forecasts import forecast as _meteociel_forecast
    from meteociel.forecasts import get_forecast_url as _get_forecast_url
    from meteociel.forecasts import TooManyCitiesError as _TooManyCitiesError
    from meteociel import cities as _cities
    from meteociel.stations import station as _meteociel_station
    from meteociel.stations import station_conv as _station_conv, station_wind_dir as _station_wind_dir
    from meteociel import utils as _meteociel_utils
    import requests
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
    Levée par ``recuperer_historique`` quand le nom de ville donné correspond,
    une fois comparé localement à la base de villes françaises (voir
    geolocalisation_stations.rechercher_villes), à plusieurs villes
    françaises distinctes.

    Contrairement à ``forecast`` (voir meteociel.forecasts.TooManyCitiesError),
    ``meteociel.stations.station`` ne lève aucune erreur en cas d'ambiguïté :
    elle choisit silencieusement la première ville trouvée dans sa base, ce
    qui peut être une homonyme d'un autre pays (ex. "Paris" aux États-Unis).
    Cette vérification locale, faite avant tout appel réseau, évite ce
    risque en imposant un choix explicite dès qu'il y a ambiguïté.

    L'attribut ``candidats`` contient la liste des villes concernées (voir
    ``geolocalisation_stations.rechercher_villes`` pour le format), à
    proposer à l'utilisateur (ex. via ``dialogue_localisation``) avant de
    rappeler ``recuperer_historique`` avec le nom exact choisi.
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


def _resoudre_ville_france(ville: str) -> str:
    """
    Tente de lever l'ambiguïté d'un nom de ville en le comparant localement
    (sans appel réseau) aux villes françaises connues de Météociel.

    - Si ``ville`` correspond déjà exactement au nom d'une ville connue
      (l'utilisateur a par exemple déjà choisi/tapé un nom précis), ce nom
      est renvoyé tel quel sans déclencher de demande de choix, même si
      d'autres villes contiennent ce texte en sous-chaîne.
    - Sinon, si une seule ville française correspond, son nom exact est
      renvoyé (le plus fiable pour ``meteociel-api``, qui sinon peut
      sélectionner en silence une homonyme d'un autre pays).
    - Si plusieurs villes françaises correspondent, lève
      ``PlusieursVillesTrouvees``.
    - Si aucune ville française ne correspond (orthographe différente,
      base non générée, ville volontairement étrangère...), ``ville`` est
      renvoyée telle quelle : on laisse alors meteociel-api faire sa
      propre recherche, avec le même comportement qu'auparavant.
    """
    candidats = gs.rechercher_villes(ville, pays="france")
    if not candidats:
        return ville

    texte_normalise = ville.strip().lower()
    correspondance_exacte = [c for c in candidats if c["nom"].lower() == texte_normalise]
    if len(correspondance_exacte) == 1:
        return correspondance_exacte[0]["nom"]

    if len(candidats) == 1:
        return candidats[0]["nom"]

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
# Cache des identifiants de PRÉVISIONS Météociel (recuperer_previsions /
# recommander).
#
# ATTENTION - point important découvert en pratique : Météociel utilise DEUX
# systèmes d'identifiants de ville totalement indépendants :
#   - celui des STATIONS/observations (cities_database.json, utilisé par
#     recuperer_historique - voir plus bas) ;
#   - celui des PRÉVISIONS (utilisé ici), avec sa propre numérotation
#     interne au site (ex. Buc = "78117001" côté station, mais "29067" côté
#     prévisions - https://www.meteociel.fr/previsions/29067/buc.htm).
# Le ``ville_id`` fourni par l'appelant (voir geolocalisation_stations.py /
# dialogue_localisation.py) est TOUJOURS un identifiant du système STATIONS
# (le seul dont on dispose une base locale complète). Il ne peut donc PAS
# être transmis tel quel comme ``city_id`` de ``meteociel.forecasts.forecast``
# - ce serait un identifiant valide, mais pour une tout autre ville.
#
# À la place, ``ville_id`` sert ici de clé de cache stable : la première
# fois qu'une ville est demandée, on résout son VRAI identifiant de
# prévisions (via une recherche par nom, une seule fois, en utilisant le nom
# + code postal le plus précis possible pour limiter le risque d'ambiguïté),
# puis on le mémorise dans un petit fichier local (cache_ids_previsions.json).
# Les appels suivants pour la même ville utilisent directement cet
# identifiant réel : plus aucune recherche par nom nécessaire, donc plus
# aucun risque d'ambiguïté ou d'échec de recherche (le problème rencontré
# sur des villes comme "Buc").
# ---------------------------------------------------------------------------
_CHEMIN_CACHE_PREVISIONS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache_ids_previsions.json")


def _charger_cache_previsions():
    if os.path.exists(_CHEMIN_CACHE_PREVISIONS):
        try:
            with open(_CHEMIN_CACHE_PREVISIONS, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _sauvegarder_cache_previsions(cache):
    try:
        with open(_CHEMIN_CACHE_PREVISIONS, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False)
    except OSError:
        pass  # cache best-effort : un échec d'écriture ne doit jamais interrompre l'application


def _extraire_code_postal(libelle):
    """Extrait un code postal entre parenthèses d'un libellé Météociel du
    type 'Buc (78530)', ou None si absent."""
    m = re.search(r"\((\d{4,5})\)\s*$", libelle)
    return m.group(1) if m else None


def _choisir_parmi_candidats(candidats, nom_recherche, code_postal_attendu):
    """Sélectionne le bon candidat (identifiant, libelle) parmi ``candidats``
    (voir ``_resoudre_id_previsions``) :

    1. Si ``code_postal_attendu`` est connu (déduit localement via
       ``geolocalisation_stations.code_postal_pour_id`` - voir
       ``_resoudre_et_appeler_previsions``) et qu'un seul candidat porte ce
       code postal dans son libellé, ce candidat est renvoyé sans ambiguïté
       possible, quel que soit le nombre total de candidats (c'est le cas
       qui règle définitivement les homonymes comme "Buc").
    2. Sinon, un candidat dont le libellé (nom seul, sans code postal)
       correspond exactement à ``nom_recherche`` est renvoyé s'il est unique.
    3. Sinon, si un seul candidat existe au total, il est renvoyé.
    4. Sinon, lève ``TooManyCitiesError`` avec la liste lisible des
       candidats, pour affichage à l'utilisateur."""
    if code_postal_attendu:
        par_code_postal = [
            (i, l) for i, l in candidats if _extraire_code_postal(l) == str(code_postal_attendu)
        ]
        if len(par_code_postal) == 1:
            return par_code_postal[0][0]

    nom_normalise = nom_recherche.strip().lower()
    par_nom_exact = [
        (i, l) for i, l in candidats
        if re.sub(r"\s*\(\d{4,5}\)\s*$", "", l).strip().lower() == nom_normalise
    ]
    if len(par_nom_exact) == 1:
        return par_nom_exact[0][0]

    if len(candidats) == 1:
        return candidats[0][0]

    raise _TooManyCitiesError(
        "too many cities can match your search, please choose one city in the following list:\n"
        + "\n".join(f"- {libelle}" for _, libelle in candidats)
    )


def _resoudre_id_previsions(nom_recherche, mode, modele, code_postal_attendu=None):
    """Résout l'identifiant de prévisions Météociel correspondant à
    ``nom_recherche`` (nom SEUL, sans code postal - voir la mise en garde
    ci-dessous). Renvoie l'identifiant (str).

    Contourne un bug rencontré en pratique dans meteociel-api 1.1.2
    (``meteociel.forecasts.get_forecast_url``) : dès qu'une recherche par
    nom correspond à PLUSIEURS villes (ce qui est très courant - ex. "Buc"
    correspond à deux communes françaises, sans même compter les homonymes
    étrangers), Météociel affiche une page de choix, mais la structure HTML
    de cette page a changé depuis l'écriture du paquet : le sélecteur qu'il
    utilise pour la retrouver (``<table border="0" width="300px">``) ne
    correspond plus à rien sur la page actuelle, et le paquet plante avec
    ``AttributeError: 'NoneType' object has no attribute 'find_all'`` au
    lieu de lister proprement les villes candidates.

    .. warning::
        ``nom_recherche`` doit être un nom de ville SEUL (ex. "Buc"), PAS
        annoté d'un code postal entre parenthèses (ex. PAS "Buc (78530)") :
        ce format n'est que celui utilisé par Météociel pour AFFICHER ses
        résultats en cas d'ambiguïté (voir ci-dessous), ce n'est pas un
        format que son moteur de recherche accepte en entrée - lui envoyer
        une chaîne ainsi annotée renvoie 0 résultat, aucune ville trouvée.
        Pour désambiguïser via un code postal connu localement (voir
        ``geolocalisation_stations.code_postal_pour_id``), passer celui-ci
        séparément via ``code_postal_attendu`` : la désambiguïsation se fait
        alors nous-mêmes, après coup, sur les libellés renvoyés par
        Météociel (qui eux sont bien annotés du code postal).

    On retente donc d'abord la fonction du paquet (rapide, fonctionne très
    bien pour une recherche qui correspond à une seule ville), puis,
    UNIQUEMENT si elle échoue avec ce AttributeError précis, on refait la
    même requête HTTP et on extrait nous-mêmes les villes candidates par
    expression régulière directement dans la page (même motif que celui
    utilisé en interne par le paquet), sans dépendre du sélecteur de
    tableau cassé.

    Lève ``meteociel.forecasts.TooManyCitiesError`` si plusieurs villes
    correspondent encore (aucune n'est un nom exact ni ne correspond à
    ``code_postal_attendu``), ``ValueError`` si aucune ville n'est trouvée,
    ``ConnectionError`` en cas de problème réseau - comme la fonction
    d'origine."""
    try:
        url = _get_forecast_url(city_name=nom_recherche, mode=mode, model=modele)
        m = re.search(r"/(\d+)/[^/]+\.htm", url)
        if m:
            return m.group(1)
    except AttributeError:
        pass  # page de désambiguïsation à la structure inattendue : repli ci-dessous

    mode_url = {"forecasts": "previsions", "trends": "tendances"}[mode]
    if mode_url == "previsions" and modele != "gfs":
        mode_url = f"{mode_url}-{modele}"

    response = requests.get(
        "https://www.meteociel.fr/prevville.php",
        params={"action": "getville", "villeid": "", "ville": nom_recherche, "envoyer": "OK"},
        timeout=10,
    )
    if not response.ok:
        raise ConnectionError(f"connection failed with code: {response.status_code}")

    candidats = []
    for m in re.finditer(r'<li>\s*<a href="/([^"/]+)/([^"]+)">\s*([^<]+?)\s*</a>\s*</li>', response.text):
        _prefixe_mode, chemin, libelle = m.groups()
        id_match = re.match(r"(\d+)/", chemin)
        if not id_match:
            continue
        identifiant = id_match.group(1)
        libelle = libelle.replace("\xa0(\xa0", " (").replace("\xa0)", ")").strip()
        candidats.append((identifiant, libelle))

    if not candidats:
        raise ValueError(f"Aucune ville trouvée par Météociel pour la recherche « {nom_recherche} ».")

    return _choisir_parmi_candidats(candidats, nom_recherche, code_postal_attendu)


def _resoudre_et_appeler_previsions(ville, ville_id, mode, modele):
    """Résout puis appelle les prévisions/tendances Météociel en utilisant,
    quand c'est possible, l'identifiant de prévisions réel mis en cache
    (voir le commentaire ci-dessus). Renvoie ``(nom_ville, dataframe)``.

    Sans ``ville_id`` (ex. nom tapé à la main sans passer par la pop-up de
    localisation), lève ``PlusieursVillesTrouvees`` si ``ville`` correspond,
    une fois comparée localement à la base de villes françaises, à plusieurs
    communes distinctes - exactement comme ``recuperer_historique`` (voir
    ``_resoudre_ville_france``). Ceci évite de dépendre de la page de
    désambiguïsation de Météociel (fragile - voir ``_resoudre_id_previsions``)
    ou d'une ``TooManyCitiesError`` brute peu exploitable côté interface, et
    unifie le comportement des trois fonctions (prévisions, tendances,
    historique) : dans les trois cas, une ville ambiguë doit être précisée
    explicitement (ex. via le bouton 📍) avant tout appel réseau."""
    if not ville_id:
        ville = _resoudre_ville_france(ville)

    cle_cache = f"id:{ville_id}" if ville_id else f"nom:{ville.strip().lower()}"
    cache = _charger_cache_previsions()
    id_previsions_connu = cache.get(cle_cache)

    if id_previsions_connu:
        try:
            return _meteociel_forecast(city_id=id_previsions_connu, mode=mode, model=modele)
        except Exception:
            # L'identifiant en cache n'est peut-être plus valide (rare :
            # changement côté Météociel) : on invalide et on retente une
            # résolution complète par nom ci-dessous.
            cache.pop(cle_cache, None)

    # Nom de recherche le plus précis possible : si on a un ville_id (donc
    # une ville trouvée via cities_database.json), on en tire son nom réel
    # et, séparément, son code postal quand il est connu (utilisé pour
    # départager nous-mêmes plusieurs résultats Météociel - voir
    # _choisir_parmi_candidats - PAS injecté dans la recherche elle-même :
    # Météociel n'accepte en entrée que le nom seul, "Nom (code postal)"
    # n'étant que son propre format d'AFFICHAGE en cas d'ambiguïté).
    nom_recherche = ville
    code_postal_attendu = None
    if ville_id:
        nom_reel = gs.nom_pour_id(ville_id)
        if nom_reel:
            nom_recherche = nom_reel
            code_postal_attendu = gs.code_postal_pour_id(ville_id)

    id_trouve = _resoudre_id_previsions(nom_recherche, mode, modele, code_postal_attendu)
    cache[cle_cache] = id_trouve
    _sauvegarder_cache_previsions(cache)
    return _meteociel_forecast(city_id=id_trouve, mode=mode, model=modele)


# ---------------------------------------------------------------------------
# Récupération des données météo
# ---------------------------------------------------------------------------
def recuperer_previsions(ville: str, mode: str = "forecasts", modele: str = "gfs", ville_id: str = None):
    """
    Récupère les prévisions météo Météociel pour une ville donnée.

    ``ville_id`` (optionnel) est l'identifiant de la ville dans
    cities_database.json (voir geolocalisation_stations.identifiant_ville /
    dialogue_localisation.py) : quand il est fourni, il est utilisé en
    priorité - non pas transmis tel quel à Météociel (les prévisions ont
    leur propre numérotation, différente de celle des stations - voir le
    commentaire au-dessus de ``_resoudre_et_appeler_previsions``), mais pour
    retrouver puis mettre en cache le véritable identifiant de prévisions de
    cette ville, ce qui rend les appels suivants pour la même ville fiables
    et instantanés (plus de recherche par nom, donc plus de risque
    d'ambiguïté). Sans ``ville_id``, le comportement précédent (recherche
    Météociel par ``ville``) s'applique tel quel.

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

    return _resoudre_et_appeler_previsions(ville, ville_id, mode, modele)


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


def recommander(action: str, ville: str, mode: str = "forecasts", modele: str = "gfs", ville_id: str = None):
    """
    Fonction principale de l'outil d'aide à la décision.

    ``ville_id`` : voir ``recuperer_previsions``.

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

    ville_trouvee, df = recuperer_previsions(ville, mode=mode, modele=modele, ville_id=ville_id)
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


def _depaqueter_vent(resultat):
    """``station_conv`` (voir ``meteociel.stations.station_conv``) renvoie
    un COUPLE de listes (vitesse, rafale) dès qu'au moins une heure de la
    journée comporte une rafale renseignée (format Météociel "12 (18)"),
    mais une simple liste PLATE de vitesses si AUCUNE heure n'en a (fréquent
    pour les stations "secondaire", type de la station de Buc par exemple,
    qui ne remontent pas toujours de rafale) - voir ``meteociel.utils.conv``.
    Un unpack direct en 2 variables (``wind_spd, wind_gust = ...``) plante
    alors avec ``ValueError: too many values to unpack`` (ou "not enough
    values to unpack" selon le nombre d'heures de la journée). Cette
    fonction gère les deux cas et renvoie toujours un couple (vitesse,
    rafale), la rafale étant remplie de ``NaN`` quand elle est absente."""
    if isinstance(resultat, tuple):
        return resultat
    return resultat, [float("nan")] * len(resultat)


def _station_par_id(date: datetime.datetime, city_id: str):
    """Équivalent de ``meteociel.stations.station(date, city_name)``, mais à
    partir d'un ``city_id`` connu directement (au lieu de le retrouver par
    une recherche floue sur le nom via ``meteociel.cities.get_city`` - voir
    sa docstring : en cas d'ambiguïté elle choisit SILENCIEUSEMENT la
    première ville trouvée, ce qui peut être une homonyme d'un autre pays).

    Contrairement aux prévisions (voir plus haut), les STATIONS utilisent
    la même numérotation que cities_database.json : ``city_id`` peut donc
    être transmis directement à Météociel, sans étape de résolution/cache.

    Reproduit le corps de ``meteociel.stations.station`` à l'identique
    (mêmes fonctions de conversion, réutilisées depuis le paquet), en
    sautant uniquement l'appel à ``cities.get_city``. Le nom de ville
    renvoyé est lu dans cities_database.json (voir
    geolocalisation_stations.nom_pour_id)."""
    response = requests.get(
        "https://www.meteociel.fr/temps-reel/obs_villes.php",
        params={
            "affint": 1,
            "code2": city_id,
            "jour2": date.day,
            "mois2": date.month - 1,
            "annee2": date.year,
        },
        timeout=10,
    )
    data = _meteociel_utils.get_data_from_html(
        response,
        {
            "width": "100%",
            "border": "1",
            "cellpadding": "1",
            "cellspacing": "0",
            "bordercolor": "#C0C8FE",
            "bgcolor": "#EBFAF7",
        },
    )
    wind_dir = _station_conv(_station_wind_dir(data[-4][1:]))
    wind_spd, wind_gust = _depaqueter_vent(_station_conv(data[-3][1:]))
    hour_name = "time (local)" if data[0][0] == "Heurelocale" else "time (GMT)"

    nom = gs.nom_pour_id(city_id) or str(city_id)

    return nom, pd.DataFrame.from_dict({
        hour_name: data[0][1:][::-1],
        "visibility": _station_conv(data[-10][1:])[::-1],
        "temperature": _station_conv(data[-9][1:])[::-1],
        "humidity": _station_conv(data[-8][1:])[::-1],
        "dew_point": _station_conv(data[-7][1:])[::-1],
        "wind_dir": wind_dir[::-1],
        "wind_spd": wind_spd[::-1],
        "wind_gust": wind_gust[::-1],
        "pressure": _station_conv(data[-2][1:])[::-1],
    })


def recuperer_historique(ville: str, date_debut: datetime.date, date_fin: datetime.date, ville_id: str = None):
    """
    Récupère l'historique des mesures de station Météociel (température,
    humidité, vent, pression...) pour une ville, jour par jour, entre
    ``date_debut`` et ``date_fin`` (inclus).

    ``ville_id`` (optionnel) est l'identifiant de la ville dans
    cities_database.json (voir geolocalisation_stations.identifiant_ville /
    dialogue_localisation.py) : quand il est fourni, il est utilisé
    directement (même système d'identifiants que les stations - voir
    ``_station_par_id``), ce qui évite tout appel à la recherche par nom de
    meteociel-api et donc tout risque d'ambiguïté ou d'homonyme silencieux.
    Sans ``ville_id``, le comportement précédent (résolution par nom via
    ``_resoudre_ville_france``) s'applique tel quel.

    Effectue un appel réseau par jour de la période (les données de station
    sont fournies par Météociel une journée à la fois). Retourne un tuple
    (nom_ville_trouvee, dataframe) où le dataframe contient une colonne
    ``datetime`` triée par ordre chronologique.

    Lève ``RuntimeError`` si meteociel-api/pandas n'est pas installé ou si la
    base de villes locale n'a pas encore été générée (voir
    ``generer_base_villes``). Toute autre exception réseau est laissée
    remonter telle quelle.
    """
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
    if date_debut > date_fin:
        date_debut, date_fin = date_fin, date_debut

    # Lève l'ambiguïté éventuelle une seule fois, avant les appels réseau
    # (voir PlusieursVillesTrouvees / _resoudre_ville_france ci-dessus) -
    # inutile si on dispose déjà d'un ville_id (aucune ambiguïté possible).
    if not ville_id:
        ville = _resoudre_ville_france(ville)

    jours = []
    d = date_debut
    while d <= date_fin:
        jours.append(d)
        d += datetime.timedelta(days=1)

    trames = []
    ville_trouvee = None
    for jour in jours:
        if ville_id:
            nom, df_jour = _station_par_id(datetime.datetime(jour.year, jour.month, jour.day), ville_id)
        else:
            nom, df_jour = _meteociel_station(datetime.datetime(jour.year, jour.month, jour.day), ville)
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
