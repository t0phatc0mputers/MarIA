# -*- coding: utf-8 -*-
"""
qualite_sol.py
---------------
Moteur d'analyse de la qualité du sol pour l'onglet "Qualité des sols".

Toutes les informations saisies par l'utilisateur sont FACULTATIVES
(humidité, pH, texture, matière organique, drainage, N/P/K, calcaire,
salinité, CEC, granulométrie...). Le module :

  1. lit les besoins agronomiques des cultures dans fiches_botaniques.FICHES
     (champs libres "sol" et "ph") et en extrait des critères comparables ;
  2. confronte ces critères aux données de sol saisies pour classer les
     cultures en "bien adaptées" / "à éviter" (seuls les critères
     effectivement renseignés par l'utilisateur sont pris en compte) ;
  3. propose des actions concrètes d'amélioration du sol, hiérarchisées
     par urgence, en s'appuyant sur des références agronomiques réelles
     (voir ci-dessous) plutôt que sur de simples catégories qualitatives.

Aucune donnée n'est obligatoire : l'utilisateur peut ne remplir qu'un seul
champ (ex. juste le pH) et obtenir malgré tout des résultats pertinents.

RÉFÉRENCES AGRONOMIQUES UTILISÉES
----------------------------------
Les seuils numériques ci-dessous sont repris de l'outil "Calcul Ferti /
Analyse de sol" du GAB IDF (groupement d'agriculteurs bio d'Île-de-France),
lui-même construit à partir des références COMIFER / ARVALIS :

- Ratio MO/argile (structure du sol) : seuils Minimal 12 %, Raisonnable
  17 %, Optimal 24 % (grille GAB IDF).
- C/N : <10 minéralisation rapide, 10-12 bon équilibre, 12-15 normal,
  >15 réorganisation de l'azote (risque de faim d'azote).
- Seuils P2O5 et K2O (méthode Olsen, mg/kg) par type de sol, pour cultures
  exigeantes (maraîchage) : grille COMIFER "PKMg" région Centre Bassin
  parisien (la plus proche du contexte Île-de-France de cet outil).
- CEC : sols légers < 7 meq/100g, intermédiaires 7-20, lourds/riches > 20
  (Tableau 5.5, données MEAC, repris dans l'onglet "Aide" du classeur).
- Indice de battance (risque de croûte de battance après pluie) : calculé
  à partir de l'argile, des limons et de la MO, seuils <1,4 non battant,
  1,4-1,6 peu battant, 1,6-1,8 battant, >1,8 très battant.
- pH cible 6,0-7,5 toute l'année (fourchette rappelée dans le classeur).

Les calculs de doses précises (chaulage en t/ha, plan de fertilisation NPK
complet) ne sont volontairement PAS repris ici : ils dépendent de mesures
supplémentaires (profondeur, densité, pierrosité...) et d'un calcul avancé
qui a sa place dans un outil dédié plutôt que dans cette analyse de
qualité de sol ; ce module reste à un niveau diagnostic + recommandations
qualitatives.
"""

import re

# ------------------------------------------------------------------
# Choix proposés dans l'interface (utilisés aussi bien par le module que
# par le fichier principal pour construire les QComboBox)
# ------------------------------------------------------------------
NON_RENSEIGNE = "Non renseigné"

CHOIX_TEXTURE = [NON_RENSEIGNE, "Sableux (léger)", "Limoneux", "Limono-argileux", "Argileux (lourd)"]
CHOIX_HUMIDITE = [NON_RENSEIGNE, "Sec", "Frais", "Humide", "Détrempé / engorgé"]
CHOIX_DRAINAGE = [NON_RENSEIGNE, "Bon", "Moyen", "Mauvais"]
CHOIX_CALCAIRE = [NON_RENSEIGNE, "Non calcaire", "Peu calcaire", "Calcaire"]
CHOIX_SALINITE = [NON_RENSEIGNE, "Faible", "Normale", "Élevée"]

URGENCE_ORDRE = {"urgent": 0, "important": 1, "conseillé": 2}
URGENCE_EMOJI = {"urgent": "🔴", "important": "🟠", "conseillé": "🟢"}
URGENCE_COULEUR = {"urgent": "#c62828", "important": "#e58900", "conseillé": "#2e7d32"}

# --- Seuils P2O5 / K2O Olsen (mg/kg), cultures exigeantes, grille COMIFER
# "PKMg" région Centre Bassin parisien (référence la plus proche du
# contexte Île-de-France) : (Trenf, Timp) par type de sol / texture.
SEUILS_P2O5_PAR_TEXTURE = {
    "Sableux (léger)": (50, 80),
    "Limoneux": (50, 80),
    "Limono-argileux": (50, 80),
    "Argileux (lourd)": (60, 90),
}
SEUILS_K2O_PAR_TEXTURE = {
    "Sableux (léger)": (150, 200),
    "Limoneux": (170, 300),
    "Limono-argileux": (170, 250),
    "Argileux (lourd)": (200, 300),
}
DEFAUT_SEUILS_P2O5 = (50, 80)     # repli si la texture n'est pas renseignée (limons battants)
DEFAUT_SEUILS_K2O = (170, 300)


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


# ------------------------------------------------------------------
# Indicateurs avancés du sol (GAB IDF / COMIFER) — indépendants de toute
# culture précise, utilisés pour affiner le plan d'action et le score
# global de fertilité.
# ------------------------------------------------------------------
def ratio_mo_argile(mo_pourcent, argile_pourcent):
    """Ratio MO/argile en %, indicateur clé de la structure du sol
    (GAB IDF). None si l'un des deux taux manque."""
    if not mo_pourcent or not argile_pourcent or argile_pourcent <= 0:
        return None
    return round(100 * mo_pourcent / argile_pourcent, 1)


def classer_ratio_mo_argile(ratio):
    if ratio is None:
        return None
    if ratio < 12:
        return "Insuffisant"
    if ratio < 17:
        return "Minimal"
    if ratio < 24:
        return "Raisonnable"
    return "Optimal"


def deriver_bucket_mo(mo_pourcent, argile_pourcent=None):
    """Catégorie Faible/Moyenne/Riche utilisée par le moteur de
    correspondance culture <-> sol (evaluer_culture). Utilise le ratio
    MO/argile quand le taux d'argile est connu (plus précis), sinon un
    seuil générique sur le seul taux de MO."""
    if mo_pourcent is None:
        return None
    ratio = ratio_mo_argile(mo_pourcent, argile_pourcent)
    if ratio is not None:
        if ratio < 12:
            return "Faible"
        if ratio < 20:
            return "Moyenne"
        return "Riche"
    if mo_pourcent < 1.5:
        return "Faible"
    if mo_pourcent < 3.0:
        return "Moyenne"
    return "Riche"


def interpreter_cn(cn):
    """Interprète le rapport C/N. Retourne un dict {titre, urgence, detail}
    ou None si le C/N est dans la fourchette d'équilibre (rien à signaler)."""
    if cn is None:
        return None
    if cn < 10:
        return {"titre": "C/N bas : minéralisation rapide", "urgence": "conseillé",
                "detail": f"C/N mesuré : {cn}. La matière organique se dégrade vite : bon pour la disponibilité "
                          "en azote à court terme, mais le stock d'humus peut s'épuiser sans apports organiques "
                          "réguliers."}
    if cn <= 12:
        return None  # bon équilibre, rien à signaler
    if cn <= 15:
        return {"titre": "C/N un peu élevé", "urgence": "conseillé",
                "detail": f"C/N mesuré : {cn}. Minéralisation un peu ralentie : situation encore normale, à "
                          "surveiller si elle continue d'augmenter."}
    return {"titre": "C/N élevé : réorganisation de l'azote", "urgence": "important",
            "detail": f"C/N mesuré : {cn} (> 15). La matière organique immobilise l'azote au lieu de le "
                      "libérer : risque de faim d'azote temporaire pour les cultures exigeantes. Privilégier des "
                      "apports organiques plus décomposés (compost mûr plutôt que résidus frais/paille)."}


def classer_cec(cec):
    """CEC en meq/100g (≈ cmol+/kg). Seuils : sols légers <7, intermédiaires
    7-20, lourds/riches >20 (Tableau 5.5, données MEAC)."""
    if cec is None:
        return None
    if cec < 7:
        return "Faible"
    if cec <= 20:
        return "Intermédiaire"
    return "Élevée"


def positionner_np(valeur, seuils):
    """Positionne une teneur (P2O5 ou K2O, mg/kg Olsen) par rapport au
    couple (Trenf, Timp) : Faible (< Trenf), Moyen (entre les deux),
    Riche (> Timp, situation d'impasse possible)."""
    if valeur is None or seuils is None:
        return None
    trenf, timp = seuils
    if valeur < trenf:
        return "Faible"
    if valeur <= timp:
        return "Moyen"
    return "Riche"


def indice_battance(argile, limons_fins, limons_grossiers, mo, ph):
    """Indice de battance (risque de croûte de battance en surface après
    la pluie). Nécessite argile, limons fins, limons grossiers, MO et pH
    (tous en %, sauf pH) : retourne None si l'un manque."""
    if None in (argile, limons_fins, limons_grossiers, mo, ph):
        return None
    denominateur = argile + 10 * mo
    if denominateur <= 0:
        return None
    ib = (1.5 * limons_fins + 0.75 * limons_grossiers) / denominateur
    if ph > 7:
        ib -= 0.2 * (ph - 7)
    return round(ib, 2)


def classer_battance(ib):
    if ib is None:
        return None
    if ib < 1.4:
        return "Non battant"
    if ib < 1.6:
        return "Peu battant"
    if ib < 1.8:
        return "Battant"
    return "Très battant"


def construire_profil_analyse(brut):
    """Prend le profil "brut" saisi dans l'interface (valeurs numériques
    pH/CEC/argile/MO%/C-N/P2O5/K2O/limons + choix qualitatifs texture/
    humidité/drainage/calcaire/salinité) et retourne un profil enrichi
    avec les indicateurs dérivés (ratio MO/argile, C/N interprété, CEC
    classée, indice de battance, catégories P/K...). C'est ce profil
    enrichi qu'il faut passer à classer_cultures / generer_actions /
    score_global_sol."""
    profil = dict(brut)

    argile = brut.get("argile")
    mo = brut.get("mo_pourcent")
    texture = brut.get("texture")

    profil["matiere_organique"] = deriver_bucket_mo(mo, argile) or NON_RENSEIGNE

    ratio = ratio_mo_argile(mo, argile)
    profil["ratio_mo_argile"] = ratio
    profil["categorie_ratio_mo_argile"] = classer_ratio_mo_argile(ratio)

    seuils_p = SEUILS_P2O5_PAR_TEXTURE.get(texture, DEFAUT_SEUILS_P2O5)
    seuils_k = SEUILS_K2O_PAR_TEXTURE.get(texture, DEFAUT_SEUILS_K2O)
    profil["seuils_p2o5"] = seuils_p
    profil["seuils_k2o"] = seuils_k
    profil["phosphore"] = positionner_np(brut.get("p2o5"), seuils_p) or NON_RENSEIGNE
    profil["potassium"] = positionner_np(brut.get("k2o"), seuils_k) or NON_RENSEIGNE

    profil["interpretation_cn"] = interpreter_cn(brut.get("c_n"))
    profil["categorie_cec"] = classer_cec(brut.get("cec"))

    ib = indice_battance(argile, brut.get("limons_fins"), brut.get("limons_grossiers"), mo, brut.get("ph"))
    profil["indice_battance"] = ib
    profil["categorie_battance"] = classer_battance(ib)

    return profil


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
    ENRICHI (voir construire_profil_analyse), triée par urgence décroissante.
    Si rien n'est renseigné, retourne des conseils génériques de bonnes
    pratiques."""
    actions = []

    ph = profil.get("ph")
    if ph is not None:
        if ph < 5.5:
            actions.append({"titre": "Corriger un pH très acide", "urgence": "urgent",
                             "detail": "Apporter un amendement calcique (chaux agricole, lithothamne) pour "
                                       "remonter progressivement le pH vers la fourchette idéale de 6,0 à 7,5 ; "
                                       "fractionner les apports sur plusieurs mois."})
        elif ph < 6.0:
            actions.append({"titre": "Remonter légèrement le pH", "urgence": "important",
                             "detail": "Un léger chaulage ou un apport de cendre de bois modéré peut corriger "
                                       "l'acidité et améliorer la disponibilité des nutriments (pH cible 6,0 à "
                                       "7,5 toute l'année)."})
        elif ph > 8.0:
            actions.append({"titre": "Corriger un pH très basique", "urgence": "urgent",
                             "detail": "Apporter de la matière organique acidifiante (compost de feuilles, "
                                       "écorces) et éviter tout amendement calcaire ; surveiller les carences en "
                                       "fer, manganèse, zinc et bore, plus fréquentes en sol basique."})
        elif ph > 7.5:
            actions.append({"titre": "Assouplir un pH élevé", "urgence": "conseillé",
                             "detail": "Privilégier des apports réguliers de compost pour tamponner le pH et "
                                       "limiter les amendements calcaires (pH cible 6,0 à 7,5 toute l'année)."})

    # -- Matière organique : ratio MO/argile quand l'argile est connue
    #    (référence GAB IDF : Minimal 12 %, Raisonnable 17 %, Optimal 24 %),
    #    sinon repli sur le seul taux de MO.
    ratio = profil.get("ratio_mo_argile")
    cat_ratio = profil.get("categorie_ratio_mo_argile")
    mo = profil.get("mo_pourcent")
    if cat_ratio == "Insuffisant":
        actions.append({"titre": "Ratio MO/argile insuffisant", "urgence": "urgent",
                         "detail": f"Ratio MO/argile mesuré : {ratio} %, sous le seuil minimal de 12 % "
                                   "(référence GAB IDF) : la structure du sol risque de se dégrader. Apporter "
                                   "3 à 4 kg/m² de compost mûr ou de fumier bien décomposé et semer un engrais "
                                   "vert."})
    elif cat_ratio == "Minimal":
        actions.append({"titre": "Ratio MO/argile à renforcer", "urgence": "important",
                         "detail": f"Ratio MO/argile mesuré : {ratio} % (au-dessus du minimal de 12 % mais sous "
                                   "le niveau raisonnable de 17 %) : poursuivre des apports réguliers de compost "
                                   "pour sécuriser la structure du sol."})
    elif cat_ratio == "Raisonnable":
        actions.append({"titre": "Ratio MO/argile correct, à entretenir", "urgence": "conseillé",
                         "detail": f"Ratio MO/argile mesuré : {ratio} % (fourchette raisonnable 17-24 %) : "
                                   "poursuivre les apports d'entretien (1-2 kg/m²/an de compost) pour le "
                                   "maintenir."})
    elif cat_ratio is None and mo is not None:
        # Pas de taux d'argile connu : repli sur des seuils génériques
        if mo < 1.5:
            actions.append({"titre": "Enrichir le sol en matière organique", "urgence": "important",
                             "detail": f"MO mesurée : {mo} %, plutôt faible. Apporter 3 à 4 kg/m² de compost mûr "
                                       "ou de fumier bien décomposé, semer un engrais vert et pailler pour "
                                       "reconstituer le stock d'humus."})
        elif mo < 3.0:
            actions.append({"titre": "Entretenir le stock de matière organique", "urgence": "conseillé",
                             "detail": f"MO mesurée : {mo} %, dans la moyenne. Poursuivre les apports réguliers "
                                       "de compost (1-2 kg/m²/an) et pailler pour maintenir la fertilité du sol."})

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

    # -- C/N (référence GAB IDF : <10 rapide, 10-12 équilibré, 12-15 normal,
    #    >15 réorganisation de l'azote)
    interp_cn = profil.get("interpretation_cn")
    if interp_cn is not None:
        actions.append(interp_cn)

    # -- P2O5 / K2O (Olsen, mg/kg) positionnés par rapport aux seuils
    #    Trenf/Timp COMIFER du type de sol (région Centre Bassin parisien)
    phosphore = profil.get("phosphore")
    p2o5 = profil.get("p2o5")
    seuils_p = profil.get("seuils_p2o5")
    if phosphore == "Faible" and seuils_p:
        trenf, _ = seuils_p
        actions.append({"titre": "Corriger une carence en phosphore (P2O5)", "urgence": "important",
                         "detail": f"P2O5 Olsen mesuré : {p2o5} mg/kg, sous le seuil de renforcement "
                                   f"({trenf} mg/kg) pour ce type de sol (référence COMIFER, cultures "
                                   "exigeantes). Apporter de la poudre d'os ou du phosphate naturel, "
                                   "particulièrement avant plantation des cultures fruitières et racines."})

    potassium = profil.get("potassium")
    k2o = profil.get("k2o")
    seuils_k = profil.get("seuils_k2o")
    if potassium == "Faible" and seuils_k:
        trenf, _ = seuils_k
        actions.append({"titre": "Corriger une carence en potassium (K2O)", "urgence": "important",
                         "detail": f"K2O Olsen mesuré : {k2o} mg/kg, sous le seuil de renforcement "
                                   f"({trenf} mg/kg) pour ce type de sol (référence COMIFER, cultures "
                                   "exigeantes). Apporter de la cendre de bois avec modération ou du sulfate de "
                                   "potasse, utile notamment pour les cultures fruitières (tomate, courge...)."})

    # -- CEC : influence la fréquence des apports plutôt que leur nature
    cat_cec = profil.get("categorie_cec")
    cec = profil.get("cec")
    if cat_cec == "Faible":
        actions.append({"titre": "CEC faible : fractionner les apports", "urgence": "conseillé",
                         "detail": f"CEC mesurée : {cec} meq/100g (sol léger, pouvoir de rétention limité pour "
                                   "K, Mg, Ca...). Mieux vaut fractionner les apports d'engrais/amendements en "
                                   "plusieurs fois plutôt qu'en un seul, pour limiter les pertes par lessivage."})
    elif cat_cec == "Élevée":
        actions.append({"titre": "CEC élevée : bonne capacité de rétention", "urgence": "conseillé",
                         "detail": f"CEC mesurée : {cec} meq/100g (sol lourd/riche, bon pouvoir tampon). Les "
                                   "apports peuvent être plus espacés dans le temps."})

    # -- Indice de battance (risque de croûte de battance après la pluie)
    cat_battance = profil.get("categorie_battance")
    ib = profil.get("indice_battance")
    if cat_battance in ("Battant", "Très battant"):
        urgence_ib = "important" if cat_battance == "Très battant" else "conseillé"
        actions.append({"titre": f"Sol {cat_battance.lower()} (indice {ib})", "urgence": urgence_ib,
                         "detail": "Risque de croûte de battance en surface après la pluie, gênant la levée des "
                                   "semis fins : privilégier un travail superficiel, un faux-semis, le paillage "
                                   "ou un couvert végétal, et éviter de semer juste avant de fortes pluies."})

    salinite = profil.get("salinite")
    if salinite == "Élevée":
        actions.append({"titre": "Traiter un sol salé", "urgence": "important",
                         "detail": "Lessiver à l'eau douce, apporter de la matière organique, privilégier des "
                                   "cultures tolérantes au sel et éviter les engrais chimiques concentrés."})

    calcaire = profil.get("calcaire")
    if calcaire == "Calcaire":
        actions.append({"titre": "Gérer un sol calcaire", "urgence": "conseillé",
                         "detail": "Privilégier les cultures tolérantes au calcaire, surveiller la chlorose "
                                   "ferrique et les carences en manganèse/zinc/bore (moins disponibles à pH "
                                   "élevé), et apporter de la matière organique acidifiante."})

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


CHAMPS_BRUTS = ["ph", "texture", "humidite", "drainage", "calcaire", "salinite",
                "cec", "argile", "mo_pourcent", "c_n", "p2o5", "k2o",
                "limons_fins", "limons_grossiers"]


def profil_est_vide(profil):
    for champ in CHAMPS_BRUTS:
        v = profil.get(champ)
        if v is not None and v != NON_RENSEIGNE:
            return False
    return True


def score_global_sol(profil):
    """Indicateur global (0-100, ou None si rien renseigné) reflétant la
    fertilité/qualité générale du sol saisi — indépendant de toute culture
    précise, utile pour un affichage synthétique (jauge). Attend le profil
    ENRICHI (voir construire_profil_analyse)."""
    if profil_est_vide(profil):
        return None

    points, poids_total = 0.0, 0.0

    ph = profil.get("ph")
    if ph is not None:
        # Fourchette idéale rappelée dans le classeur GAB IDF : 6,0-7,5 toute l'année
        if 6.0 <= ph <= 7.5:
            s = 2
        elif 5.5 <= ph <= 8.0:
            s = 1
        else:
            s = 0
        points += s * 3
        poids_total += 6

    cat_ratio = profil.get("categorie_ratio_mo_argile")
    mo = profil.get("mo_pourcent")
    if cat_ratio is not None:
        s = {"Insuffisant": 0, "Minimal": 1, "Raisonnable": 2, "Optimal": 2}.get(cat_ratio, 1)
        points += s * 3
        poids_total += 6
    elif mo is not None:
        s = 0 if mo < 1.5 else (1 if mo < 3.0 else 2)
        points += s * 3
        poids_total += 6

    bareme = {
        "drainage": {"Bon": 2, "Moyen": 1, "Mauvais": 0},
        "humidite": {"Frais": 2, "Humide": 1, "Sec": 1, "Détrempé / engorgé": 0},
        "phosphore": {"Riche": 2, "Moyen": 1, "Faible": 0},
        "potassium": {"Riche": 2, "Moyen": 1, "Faible": 0},
        "salinite": {"Faible": 2, "Normale": 2, "Élevée": 0},
    }
    poids_critere = {"drainage": 2, "humidite": 1.5, "phosphore": 1, "potassium": 1, "salinite": 1.5}
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

    cn = profil.get("c_n")
    if cn is not None:
        if 10 <= cn <= 12:
            s = 2
        elif 8 <= cn < 15:
            s = 1
        else:
            s = 0
        points += s * 1.5
        poids_total += 3

    cat_cec = profil.get("categorie_cec")
    if cat_cec is not None:
        s = {"Faible": 1, "Intermédiaire": 2, "Élevée": 2}.get(cat_cec, 1)
        points += s * 1
        poids_total += 2

    if poids_total == 0:
        return None
    return round(100 * points / poids_total)
