# -*- coding: utf-8 -*-
"""
qualite_sol.py
---------------
Moteur d'analyse de la qualité du sol pour l'onglet "Qualité des sols".

Toutes les informations saisies par l'utilisateur sont FACULTATIVES
(humidité, pH, texture, matière organique, drainage, N/P/K, calcaire,
salinité...). Le module :

  1. lit les besoins agronomiques des cultures dans fiches_botaniques.FICHES
     (champs libres "sol" et "ph") et en extrait des critères comparables ;
  2. confronte ces critères aux données de sol saisies pour classer les
     cultures en "bien adaptées" / "à éviter" (seuls les critères
     effectivement renseignés par l'utilisateur sont pris en compte) ;
  3. propose des actions concrètes d'amélioration du sol, hiérarchisées
     par urgence.

Aucune donnée n'est obligatoire : l'utilisateur peut ne remplir qu'un seul
champ (ex. juste le pH) et obtenir malgré tout des résultats pertinents.
"""

import re

# ------------------------------------------------------------------
# Choix proposés dans l'interface (utilisés aussi bien par le module que
# par le fichier principal pour construire les QComboBox)
# ------------------------------------------------------------------
NON_RENSEIGNE = "Non renseigné"

CHOIX_TEXTURE = [NON_RENSEIGNE, "Sableux (léger)", "Limoneux", "Limono-argileux", "Argileux (lourd)"]
CHOIX_MATIERE_ORGANIQUE = [NON_RENSEIGNE, "Faible", "Moyenne", "Riche"]
CHOIX_HUMIDITE = [NON_RENSEIGNE, "Sec", "Frais", "Humide", "Détrempé / engorgé"]
CHOIX_DRAINAGE = [NON_RENSEIGNE, "Bon", "Moyen", "Mauvais"]
CHOIX_CALCAIRE = [NON_RENSEIGNE, "Non calcaire", "Peu calcaire", "Calcaire"]
CHOIX_NIVEAU = [NON_RENSEIGNE, "Faible", "Moyen", "Riche"]          # pour N / P / K
CHOIX_SALINITE = [NON_RENSEIGNE, "Faible", "Normale", "Élevée"]

URGENCE_ORDRE = {"urgent": 0, "important": 1, "conseillé": 2}
URGENCE_EMOJI = {"urgent": "🔴", "important": "🟠", "conseillé": "🟢"}
URGENCE_COULEUR = {"urgent": "#c62828", "important": "#e58900", "conseillé": "#2e7d32"}


# ------------------------------------------------------------------
# Extraction des besoins agronomiques à partir du texte libre des fiches
# ------------------------------------------------------------------
def parser_plage_ph(texte_ph):
    """Extrait (min, max) d'une chaîne du type '6,5-7,5 (sensible ...)'."""
    if not texte_ph:
        return None
    m = re.search(r"(\d+[,.]?\d*)\s*-\s*(\d+[,.]?\d*)", texte_ph)
    if not m:
        return None
    lo = float(m.group(1).replace(",", "."))
    hi = float(m.group(2).replace(",", "."))
    return (lo, hi)


def extraire_besoins_sol(fiche):
    """Analyse le champ texte libre 'sol' (+ 'ph') d'une fiche botanique et
    en déduit un petit ensemble de critères structurés. Un critère à None
    signifie que la culture est tolérante sur ce point (pas de préférence
    marquée détectée dans le texte)."""
    texte = (fiche.get("sol") or "").lower()

    besoins = {
        "ph": parser_plage_ph(fiche.get("ph")),
        "texture": None,      # "leger" | "lourd" | "tous" | None (tolérant)
        "richesse": None,     # "riche" | "pauvre" | None
        "drainage": None,     # "bon" | None
        "humidite": None,     # "frais" | "sec" | None
        "calcaire": None,     # "non_calcaire" | None
    }

    if "tous types" in texte:
        besoins["texture"] = "tous"
    elif "léger" in texte or "sableux" in texte:
        besoins["texture"] = "leger"
    elif "lourd" in texte:
        besoins["texture"] = "lourd"

    if "sans excès de matière organique" in texte or "sans fumure fraîche" in texte or "sans cailloux ni fumure" in texte:
        besoins["richesse"] = "pauvre"
    elif "riche" in texte or "humus" in texte or "humifère" in texte or "matière organique" in texte:
        besoins["richesse"] = "riche"

    if "bien drainé" in texte or "très bien drainé" in texte or "drainant" in texte:
        besoins["drainage"] = "bon"

    if "frais" in texte or "humide" in texte:
        besoins["humidite"] = "frais"

    if "non calcaire" in texte:
        besoins["calcaire"] = "non_calcaire"

    return besoins


# ------------------------------------------------------------------
# Comparaison sol saisi <-> besoins d'une culture
# ------------------------------------------------------------------
def _texture_utilisateur_vers_tag(texture):
    correspondance = {
        "Sableux (léger)": "sableux",
        "Limoneux": "limoneux",
        "Limono-argileux": "limono_argileux",
        "Argileux (lourd)": "argileux",
    }
    return correspondance.get(texture)


def _score_texture(besoin, tag_utilisateur):
    if besoin is None or besoin == "tous" or tag_utilisateur is None:
        return None
    if besoin == "leger":
        return {"sableux": 2, "limoneux": 2, "limono_argileux": 1, "argileux": 0}.get(tag_utilisateur)
    if besoin == "lourd":
        return {"argileux": 2, "limono_argileux": 2, "limoneux": 1, "sableux": 0}.get(tag_utilisateur)
    return None


def _score_richesse(besoin, mo_utilisateur):
    if besoin is None or mo_utilisateur in (None, NON_RENSEIGNE):
        return None
    if besoin == "riche":
        return {"Riche": 2, "Moyenne": 1, "Faible": 0}.get(mo_utilisateur)
    if besoin == "pauvre":
        return {"Faible": 2, "Moyenne": 1, "Riche": 0}.get(mo_utilisateur)
    return None


def _score_drainage(besoin, drainage_utilisateur):
    if besoin is None or drainage_utilisateur in (None, NON_RENSEIGNE):
        return None
    if besoin == "bon":
        return {"Bon": 2, "Moyen": 1, "Mauvais": 0}.get(drainage_utilisateur)
    return None


def _score_humidite(besoin, humidite_utilisateur):
    if besoin is None or humidite_utilisateur in (None, NON_RENSEIGNE):
        return None
    if besoin == "frais":
        return {"Frais": 2, "Humide": 2, "Sec": 0, "Détrempé / engorgé": 1}.get(humidite_utilisateur)
    return None


def _score_calcaire(besoin, calcaire_utilisateur):
    if besoin is None or calcaire_utilisateur in (None, NON_RENSEIGNE):
        return None
    if besoin == "non_calcaire":
        return {"Non calcaire": 2, "Peu calcaire": 1, "Calcaire": 0}.get(calcaire_utilisateur)
    return None


def _score_ph(besoin_plage, ph_utilisateur):
    if besoin_plage is None or ph_utilisateur is None:
        return None
    lo, hi = besoin_plage
    if lo <= ph_utilisateur <= hi:
        return 2
    marge = 0.5
    if (lo - marge) <= ph_utilisateur <= (hi + marge):
        return 1
    return 0


CRITERES_PONDERATION = {"ph": 3, "texture": 2, "richesse": 2, "drainage": 2, "humidite": 1.5, "calcaire": 1}
LIBELLES_CRITERES = {
    "ph": "pH", "texture": "texture du sol", "richesse": "richesse en matière organique",
    "drainage": "drainage", "humidite": "humidité", "calcaire": "calcaire",
}


def evaluer_culture(fiche, profil):
    """Compare une fiche botanique au profil de sol saisi.
    Retourne (score_pourcentage ou None, nb_criteres_evalues, raisons_positives, raisons_negatives).
    score = None si aucun critère commun n'a pu être évalué (données insuffisantes)."""
    besoins = extraire_besoins_sol(fiche)

    tag_texture = _texture_utilisateur_vers_tag(profil.get("texture"))
    resultats = {
        "ph": _score_ph(besoins["ph"], profil.get("ph")),
        "texture": _score_texture(besoins["texture"], tag_texture),
        "richesse": _score_richesse(besoins["richesse"], profil.get("matiere_organique")),
        "drainage": _score_drainage(besoins["drainage"], profil.get("drainage")),
        "humidite": _score_humidite(besoins["humidite"], profil.get("humidite")),
        "calcaire": _score_calcaire(besoins["calcaire"], profil.get("calcaire")),
    }

    points, poids_total, n_criteres = 0.0, 0.0, 0
    raisons_pos, raisons_neg = [], []
    for critere, score in resultats.items():
        if score is None:
            continue
        poids = CRITERES_PONDERATION[critere]
        points += score * poids
        poids_total += 2 * poids
        n_criteres += 1
        libelle = LIBELLES_CRITERES[critere]
        if score == 2:
            raisons_pos.append(f"{libelle} bien adapté(e)")
        elif score == 0:
            raisons_neg.append(f"{libelle} peu compatible")

    if n_criteres == 0 or poids_total == 0:
        return None, 0, [], []

    score_pct = round(100 * points / poids_total)
    return score_pct, n_criteres, raisons_pos, raisons_neg


def classer_cultures(fiches_dict, profil, top_n=12, bottom_n=8):
    """Classe toutes les cultures des fiches selon leur adéquation au profil
    de sol saisi. Retourne (bien_adaptees, a_eviter), chacune étant une
    liste de dicts {culture, score, raisons}."""
    evaluations = []
    for culture, fiche in fiches_dict.items():
        score, n_criteres, raisons_pos, raisons_neg = evaluer_culture(fiche, profil)
        if score is None:
            continue
        evaluations.append({
            "culture": culture,
            "score": score,
            "n_criteres": n_criteres,
            "raisons": raisons_pos,
            "raisons_negatives": raisons_neg,
        })

    evaluations.sort(key=lambda e: (-e["score"], -e["n_criteres"], e["culture"]))
    bien_adaptees = [e for e in evaluations if e["score"] >= 65][:top_n]

    a_eviter_candidats = sorted(
        [e for e in evaluations if e["score"] <= 40],
        key=lambda e: (e["score"], -e["n_criteres"], e["culture"]),
    )
    a_eviter = a_eviter_candidats[:bottom_n]

    return bien_adaptees, a_eviter


# ------------------------------------------------------------------
# Plan d'action d'amélioration du sol
# ------------------------------------------------------------------
def generer_actions(profil):
    """Construit une liste d'actions recommandées à partir du profil de sol
    saisi (dicts {titre, detail, urgence}), triée par urgence décroissante.
    Si rien n'est renseigné, retourne des conseils génériques de bonnes
    pratiques."""
    actions = []

    ph = profil.get("ph")
    if ph is not None:
        if ph < 5.5:
            actions.append({"titre": "Corriger un pH très acide", "urgence": "urgent",
                             "detail": "Apporter un amendement calcique (chaux agricole, lithothamne) pour "
                                       "remonter progressivement le pH ; fractionner les apports sur plusieurs mois."})
        elif ph < 6.0:
            actions.append({"titre": "Remonter légèrement le pH", "urgence": "important",
                             "detail": "Un léger chaulage ou un apport de cendre de bois modéré peut corriger "
                                       "l'acidité et améliorer la disponibilité des nutriments."})
        elif ph > 8.0:
            actions.append({"titre": "Corriger un pH très basique", "urgence": "urgent",
                             "detail": "Apporter de la matière organique acidifiante (compost de feuilles, "
                                       "écorces) et éviter tout amendement calcaire ; surveiller les carences en fer."})
        elif ph > 7.5:
            actions.append({"titre": "Assouplir un pH élevé", "urgence": "conseillé",
                             "detail": "Privilégier des apports réguliers de compost pour tamponner le pH et "
                                       "limiter les amendements calcaires."})

    mo = profil.get("matiere_organique")
    if mo == "Faible":
        actions.append({"titre": "Enrichir le sol en matière organique", "urgence": "important",
                         "detail": "Apporter 3 à 4 kg/m² de compost mûr ou de fumier bien décomposé, semer un "
                                   "engrais vert et pailler pour reconstituer le stock d'humus."})
    elif mo == "Moyenne":
        actions.append({"titre": "Entretenir le stock de matière organique", "urgence": "conseillé",
                         "detail": "Poursuivre les apports réguliers de compost (1-2 kg/m²/an) et pailler pour "
                                   "maintenir la fertilité du sol."})

    drainage = profil.get("drainage")
    if drainage == "Mauvais":
        actions.append({"titre": "Améliorer le drainage", "urgence": "urgent",
                         "detail": "Créer des buttes ou planches surélevées, incorporer du sable grossier et de "
                                   "la matière organique, envisager un drainage si l'engorgement persiste."})
    elif drainage == "Moyen":
        actions.append({"titre": "Surveiller le drainage", "urgence": "conseillé",
                         "detail": "Éviter le tassement du sol (ne pas circuler sur sol humide) et maintenir une "
                                   "bonne structure grâce aux apports organiques."})

    humidite = profil.get("humidite")
    if humidite == "Détrempé / engorgé":
        actions.append({"titre": "Traiter un sol engorgé", "urgence": "urgent",
                         "detail": "Créer des billons/buttes de culture, curer les fossés d'écoulement et éviter "
                                   "tout travail du sol tant qu'il reste détrempé (risque de tassement durable)."})
    elif humidite == "Sec":
        actions.append({"titre": "Améliorer la rétention d'eau", "urgence": "conseillé",
                         "detail": "Pailler systématiquement, apporter de la matière organique pour améliorer la "
                                   "rétention d'eau et envisager un système d'irrigation au goutte-à-goutte."})

    texture = profil.get("texture")
    if texture == "Argileux (lourd)":
        actions.append({"titre": "Alléger un sol argileux", "urgence": "conseillé",
                         "detail": "Incorporer du compost et du sable grossier, ne jamais travailler le sol "
                                   "humide (tassement), envisager des planches permanentes non tassées."})
    elif texture == "Sableux (léger)":
        actions.append({"titre": "Enrichir un sol sableux", "urgence": "conseillé",
                         "detail": "Apporter régulièrement de la matière organique pour améliorer la rétention "
                                   "d'eau et de nutriments, pailler pour limiter le lessivage."})

    azote = profil.get("azote")
    if azote == "Faible":
        actions.append({"titre": "Corriger une carence en azote", "urgence": "important",
                         "detail": "Semer un engrais vert azoté (trèfle, féverole, vesce) ou apporter un engrais "
                                   "organique azoté (corne broyée, sang séché)."})

    phosphore = profil.get("phosphore")
    if phosphore == "Faible":
        actions.append({"titre": "Corriger une carence en phosphore", "urgence": "conseillé",
                         "detail": "Apporter de la poudre d'os ou du phosphate naturel, particulièrement utile "
                                   "avant plantation des cultures fruitières et racines."})

    potassium = profil.get("potassium")
    if potassium == "Faible":
        actions.append({"titre": "Corriger une carence en potassium", "urgence": "conseillé",
                         "detail": "Apporter de la cendre de bois avec modération ou du sulfate de potasse, "
                                   "utile notamment pour les cultures fruitières (tomate, courge...)."})

    salinite = profil.get("salinite")
    if salinite == "Élevée":
        actions.append({"titre": "Traiter un sol salé", "urgence": "important",
                         "detail": "Lessiver à l'eau douce, apporter de la matière organique, privilégier des "
                                   "cultures tolérantes au sel et éviter les engrais chimiques concentrés."})

    calcaire = profil.get("calcaire")
    if calcaire == "Calcaire":
        actions.append({"titre": "Gérer un sol calcaire", "urgence": "conseillé",
                         "detail": "Privilégier les cultures tolérantes au calcaire, surveiller la chlorose "
                                   "ferrique et apporter de la matière organique acidifiante."})

    if not actions:
        actions = [
            {"titre": "Renseigner le profil de sol", "urgence": "conseillé",
             "detail": "Aucune donnée saisie pour l'instant : renseignez au moins le pH ou la texture pour "
                       "obtenir des recommandations personnalisées."},
            {"titre": "Bonnes pratiques générales", "urgence": "conseillé",
             "detail": "Pratiquer la rotation des cultures, couvrir le sol (paillage, engrais verts) et apporter "
                       "du compost mûr chaque année pour entretenir la fertilité."},
        ]

    actions.sort(key=lambda a: URGENCE_ORDRE.get(a["urgence"], 9))
    return actions


def profil_est_vide(profil):
    valeurs = [
        profil.get("ph"),
        profil.get("texture"), profil.get("matiere_organique"), profil.get("humidite"),
        profil.get("drainage"), profil.get("calcaire"), profil.get("azote"),
        profil.get("phosphore"), profil.get("potassium"), profil.get("salinite"),
    ]
    return all(v is None or v == NON_RENSEIGNE for v in valeurs)


def score_global_sol(profil):
    """Indicateur global (0-100, ou None si rien renseigné) reflétant la
    fertilité/qualité générale du sol saisi — indépendant de toute culture
    précise, utile pour un affichage synthétique (jauge)."""
    if profil_est_vide(profil):
        return None

    points, poids_total = 0.0, 0.0

    ph = profil.get("ph")
    if ph is not None:
        # Optimum large 6.0-7.0 pour la majorité des cultures maraîchères
        if 6.0 <= ph <= 7.0:
            s = 2
        elif 5.5 <= ph <= 7.5:
            s = 1
        else:
            s = 0
        points += s * 3
        poids_total += 6

    bareme = {
        "matiere_organique": {"Riche": 2, "Moyenne": 1, "Faible": 0},
        "drainage": {"Bon": 2, "Moyen": 1, "Mauvais": 0},
        "humidite": {"Frais": 2, "Humide": 1, "Sec": 1, "Détrempé / engorgé": 0},
        "azote": {"Riche": 2, "Moyen": 1, "Faible": 0},
        "phosphore": {"Riche": 2, "Moyen": 1, "Faible": 0},
        "potassium": {"Riche": 2, "Moyen": 1, "Faible": 0},
        "salinite": {"Faible": 2, "Normale": 2, "Élevée": 0},
    }
    poids_critere = {
        "matiere_organique": 3, "drainage": 2, "humidite": 1.5,
        "azote": 1.5, "phosphore": 1, "potassium": 1, "salinite": 1.5,
    }
    for critere, table in bareme.items():
        valeur = profil.get(critere)
        if valeur in (None, NON_RENSEIGNE):
            continue
        s = table.get(valeur)
        if s is None:
            continue
        poids = poids_critere[critere]
        points += s * poids
        poids_total += 2 * poids

    if poids_total == 0:
        return None
    return round(100 * points / poids_total)
