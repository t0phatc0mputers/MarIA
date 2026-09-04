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
CHEMIN_PREVISIONS = os.path.join(_ICI, "prevision_id.json")

try:
    from meteociel.forecasts import forecast as _meteociel_forecast
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
    "Travail du sol": {
        # Le principal risque est de travailler un sol détrempé (tassement,
        # perte de structure) ; le gel superficiel n'est pas rédhibitoire en
        # lui-même (on évite juste de rouler/piétiner un sol gelé en surface
        # puis boueux en dessous), d'où une simple vigilance.
        "gel_critique": None,
        "gel_vigilance": 0,
        "pluie_max": 5,        # mm cumulés/jour : au delà, sol trop détrempé
        "vent_max": None,
        "temp_ideale": None,
    },
    "Apport de compost": {
        # On évite d'épandre juste avant une forte pluie (lessivage/
        # ruissellement des éléments nutritifs) et par vent fort (dispersion).
        "gel_critique": None, "gel_vigilance": None,
        "pluie_max": 10,
        "vent_max": 30,
        "temp_ideale": None,
    },
    "Apport de fumier": {
        "gel_critique": None, "gel_vigilance": None,
        "pluie_max": 10,
        "vent_max": 30,
        "temp_ideale": None,
    },
    "Paillage": {
        # Un paillage (paille, BRF...) posé juste avant une grosse pluie ou
        # par grand vent tient mal et protège moins bien le sol.
        "gel_critique": None, "gel_vigilance": None,
        "pluie_max": 10,
        "vent_max": 25,
        "temp_ideale": None,
    },
    "Semis direct": {
        "gel_critique": 0,     # en dessous : rédhibitoire (graines/jeunes plantules)
        "gel_vigilance": 3,    # en dessous : pénalité, vigilance
        "pluie_max": 8,        # mm cumulés/jour : au delà, sol trop détrempé pour semer
        "vent_max": 30,        # km/h : au delà, pénalité (dessèchement, levée de graines fines)
        "temp_ideale": (10, 22),
    },
    "Semis en pot/plant": {
        # Semis sous abri/en godets : peu dépendant de la météo extérieure.
        "gel_critique": None, "gel_vigilance": None, "pluie_max": None,
        "vent_max": None, "temp_ideale": None,
    },
    "Plantation": {
        "gel_critique": 0,
        "gel_vigilance": 2,
        "pluie_max": 15,       # une pluie modérée aide la reprise, mais pas trop
        "vent_max": 25,        # le vent stresse les jeunes plants repiqués
        "temp_ideale": (10, 24),
    },
    "Récolte": {
        "gel_critique": None,
        "gel_vigilance": None,
        "pluie_max": 1,        # on préfère récolter au sec
        "vent_max": 40,
        "temp_ideale": (5, 28),
    },
    "Forçage": {
        # Généralement réalisé à l'abri / hors sol.
        "gel_critique": None, "gel_vigilance": None, "pluie_max": None,
        "vent_max": None, "temp_ideale": None,
    },
}

# Regroupement par grande catégorie pour la synthèse hebdomadaire de
# l'onglet "Planning cultural" (ordre : préparation du sol -> semis ->
# plantation -> récolte -> forçage).
CATEGORIES_SEMAINE = [
    ("🚜 Travail du sol & amendements",
     ["Travail du sol", "Apport de compost", "Apport de fumier", "Paillage"]),
    ("🌱 Semis", ["Semis direct", "Semis en pot/plant"]),
    ("🌿 Plantation", ["Plantation"]),
    ("🧺 Récolte", ["Récolte"]),
    ("🏠 Forçage", ["Forçage"]),
]


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
def recuperer_previsions(ville: str, mode: str = "forecasts", modele: str = "gfs"):
    """
    Récupère les prévisions météo Météociel pour une ville donnée.

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


    with open(CHEMIN_PREVISIONS, encoding="utf-8") as f:
        previsions = json.load(f)

    
    return _meteociel_forecast(city_id=previsions.get(ville),city_name=ville.split(' ')[0],  mode=mode, model=modele)


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


def _rapport_non_meteo(action: str) -> str:
    return (
        f"L'action « {action} » est généralement réalisée à l'abri ou hors sol : elle "
        "ne dépend pas directement de la météo extérieure. Aucune analyse météo n'est "
        "nécessaire ; vous pouvez vous fier uniquement aux dates du planning cultural."
    )


def construire_rapport(ville_trouvee: str, evalues):
    """Construit (meilleur_JourEvalue, texte_synthese) à partir d'une liste
    de JourEvalue déjà calculée (voir evaluer_jour). Factorisé pour être
    partagé entre `recommander` (une action) et `recommander_multi`
    (plusieurs actions évaluées sur le même jeu de prévisions)."""
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

    return meilleur, "\n".join(lignes) + conclusion


def verdict_court(meilleur) -> str:
    """Résumé d'une ligne (avec pastille de couleur) à partir du meilleur
    JourEvalue d'une analyse, pour un affichage compact (synthèse
    hebdomadaire notamment)."""
    if meilleur is None:
        return "ℹ️ Non dépendant de la météo."
    if meilleur.score >= 70:
        pastille = "🟢"
    elif meilleur.score >= 40:
        pastille = "🟠"
    else:
        pastille = "🔴"
    return (f"{pastille} Meilleur jour : {formater_date_fr(meilleur.date)} "
            f"(score {meilleur.score:.0f}/100)")


def recommander(action: str, ville: str, mode: str = "forecasts", modele: str = "gfs"):
    """
    Fonction principale de l'outil d'aide à la décision.

    Retourne un tuple (liste_JourEvalue, meilleur_JourEvalue_ou_None, texte_synthese).
    """
    criteres = CRITERES_ACTION.get(action)
    if criteres is None:
        return [], None, f"Action inconnue : {action}"

    if all(v is None for v in criteres.values()):
        return [], None, _rapport_non_meteo(action)

    ville_trouvee, df = recuperer_previsions(ville, mode=mode, modele=modele)
    jours = agreger_par_jour(df)

    if jours.empty:
        return [], None, "Aucune donnée météo exploitable n'a été renvoyée par Météociel."

    evalues = [evaluer_jour(row, criteres) for _, row in jours.iterrows()]
    evalues.sort(key=lambda j: j.date)
    meilleur, texte = construire_rapport(ville_trouvee, evalues)
    return evalues, meilleur, texte


def recommander_multi(actions, ville: str, mode: str = "forecasts", modele: str = "gfs"):
    """Comme `recommander`, mais pour plusieurs actions à la fois : les
    prévisions Météociel ne sont récupérées qu'UNE seule fois (même ville/
    mode/modèle) puis réévaluées avec les critères propres à chaque action -
    utile pour la synthèse hebdomadaire qui peut mélanger plusieurs actions
    (semis, plantation, récolte...) sur la même période.

    Retourne un dict {action: (liste_JourEvalue, meilleur_ou_None, texte)}.
    """
    resultats = {}
    jours = None
    ville_trouvee = None
    erreur_recuperation = None

    for action in actions:
        criteres = CRITERES_ACTION.get(action)
        if criteres is None:
            resultats[action] = ([], None, f"Action inconnue : {action}")
            continue
        if all(v is None for v in criteres.values()):
            resultats[action] = ([], None, _rapport_non_meteo(action))
            continue

        if jours is None and erreur_recuperation is None:
            try:
                ville_trouvee, df = recuperer_previsions(ville, mode=mode, modele=modele)
                jours = agreger_par_jour(df)
            except Exception as exc:  # réseau, ville introuvable, paquet manquant...
                erreur_recuperation = exc

        if erreur_recuperation is not None:
            raise erreur_recuperation

        if jours.empty:
            resultats[action] = ([], None, "Aucune donnée météo exploitable n'a été renvoyée par Météociel.")
            continue

        evalues = [evaluer_jour(row, criteres) for _, row in jours.iterrows()]
        evalues.sort(key=lambda j: j.date)
        meilleur, texte = construire_rapport(ville_trouvee, evalues)
        resultats[action] = (evalues, meilleur, texte)

    return resultats


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

