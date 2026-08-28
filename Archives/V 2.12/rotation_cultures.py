# -*- coding: utf-8 -*-
"""
rotation_cultures.py
---------------------
Moteur de conseil de rotation des cultures, construit à partir de la base
FICHES de fiches_botaniques.py (famille botanique + fiche de fertilisation
de chacune des 64 cultures du planning).

Principe agronomique appliqué (rotation classique en maraîchage biologique) :

  1. Règle IMPÉRATIVE : ne jamais faire suivre une culture par une autre
     culture de la même famille botanique (accumulation de maladies et
     ravageurs spécifiques, épuisement des mêmes éléments minéraux). Le
     délai de retour conseillé (3 ou 4 ans selon la famille) est repris du
     champ "rotation" de chaque fiche.

  2. Règle RECOMMANDÉE : faire circuler les cultures selon leur besoin en
     azote, du plus exigeant au moins exigeant, en bouclant sur les
     légumineuses qui restaurent la fertilité :

         Légumineuse (fixe l'azote)
                 ↓
         Gourmande (très exigeante) — profite de l'azote laissé au sol
                 ↓
         Moyennement exigeante
                 ↓
         Peu exigeante / racine — "nettoie" la parcelle avant de refaire
         un apport de matière organique et de relancer un cycle
                 ↓
         (retour à une légumineuse ou à un apport de compost)

Ce module ne prétend pas remplacer le jugement de l'agriculteur (pression
parasitaire locale, enherbement, structure du sol...) : il donne une base
de départ raisonnée, à ajuster.
"""

import re

import fiches_botaniques as fb

SEQUENCE_GROUPES = [
    "Légumineuse (fixe l'azote)",
    "Gourmande (très exigeante)",
    "Moyennement exigeante",
    "Peu exigeante (sol reposé / racine)",
]

DELAI_DEFAUT_ANNEES = 3


def classifier_besoin(fiche):
    """Classe une fiche culture dans l'un des 4 groupes de SEQUENCE_GROUPES,
    à partir du texte de son champ "fertilisation"."""
    texte = (fiche.get("fertilisation") or "").lower()
    if "légumineuses" in texte and "azote" in texte:
        return "Légumineuse (fixe l'azote)"
    if "très gourmande" in texte or "gourmande" in texte:
        return "Gourmande (très exigeante)"
    if ("éviter tout apport de matière organique fraîche" in texte
            or "fourchage" in texte or "à l'automne précédent" in texte
            or "peu d'azote" in texte):
        return "Peu exigeante (sol reposé / racine)"
    return "Moyennement exigeante"


def _delai_retour_annees(fiche):
    """Extrait le délai de retour (en années) depuis le champ "rotation"
    (ex. "après 4 ans minimum" -> 4). Repli sur DELAI_DEFAUT_ANNEES si non
    trouvé."""
    texte = fiche.get("rotation") or ""
    m = re.search(r"(\d+)\s*an", texte)
    if m:
        return int(m.group(1))
    return DELAI_DEFAUT_ANNEES


def lister_cultures():
    """Liste triée des noms de cultures disponibles dans la base."""
    return sorted(fb.FICHES.keys())


def rechercher_cultures(texte):
    if not texte:
        return lister_cultures()
    t = texte.strip().lower()
    return sorted(n for n in fb.FICHES if t in n.lower())


def famille_courte(famille):
    """Nom de famille sans la parenthèse d'ancien nom (affichage compact)."""
    return re.sub(r"\s*\(.*?\)", "", famille or "").strip()


def analyser_rotation(culture_nom):
    """Analyse une culture donnée et renvoie un dict :
      - fiche, groupe, famille, delai_retour_annees
      - a_eviter        : cultures de la même famille (règle impérative)
      - recommandees    : cultures du groupe suivant, famille différente
      - possibles       : autres cultures, famille différente, hors "à éviter"
    Chaque culture de la liste est un dict {"nom":..., "famille":..., "groupe":...}.
    """
    fiche = fb.FICHES.get(culture_nom)
    if fiche is None:
        return None

    famille = fiche["famille"]
    groupe = classifier_besoin(fiche)
    delai = _delai_retour_annees(fiche)
    index_groupe = SEQUENCE_GROUPES.index(groupe)
    groupe_recommande = SEQUENCE_GROUPES[(index_groupe + 1) % len(SEQUENCE_GROUPES)]
    groupe_possible = SEQUENCE_GROUPES[(index_groupe + 2) % len(SEQUENCE_GROUPES)]

    a_eviter, recommandees, possibles = [], [], []
    for nom, f in fb.FICHES.items():
        if nom == culture_nom:
            continue
        entree = {"nom": nom, "famille": f["famille"], "groupe": classifier_besoin(f)}
        if f["famille"] == famille:
            a_eviter.append(entree)
        elif entree["groupe"] == groupe_recommande:
            recommandees.append(entree)
        elif entree["groupe"] == groupe_possible:
            possibles.append(entree)

    for liste in (a_eviter, recommandees, possibles):
        liste.sort(key=lambda e: e["nom"])

    return {
        "culture": culture_nom,
        "famille": famille,
        "groupe": groupe,
        "delai_retour_annees": delai,
        "groupe_recommande": groupe_recommande,
        "groupe_possible": groupe_possible,
        "a_eviter": a_eviter,
        "recommandees": recommandees,
        "possibles": possibles,
    }


def cultures_par_groupe():
    """Renvoie {groupe: [noms triés]} pour les 4 groupes de la séquence."""
    out = {g: [] for g in SEQUENCE_GROUPES}
    for nom, f in fb.FICHES.items():
        out[classifier_besoin(f)].append(nom)
    for g in out:
        out[g].sort()
    return out
