# -*- coding: utf-8 -*-
"""
analyse_sol.py
---------------
Portage fidèle de l'outil Excel "Calcul Ferti / Analyse de sol" du GAB IDF
(groupement des agriculteurs bio d'Île-de-France), construit à partir des
références COMIFER / ARVALIS.

Ce module remplace l'ancien onglet heuristique "Qualité des sols"
(qualite_sol.py) par une rubrique unique qui reprend TOUTES les données et
tous les calculs du classeur :

  1. Interprétation d'analyse de sol (onglet Excel "Analyse de Sol") :
     poids de terre fine, CEC, granulométrie / seuils P2O5-K2O, pH été/hiver,
     ratio MO/argile, apport d'amendement pour +1 point de MO, coefficient de
     minéralisation K2, indice de battance IB, stratégie de chaulage (BEB),
     taux de minéralisation de l'azote humifié (Km) et minéralisation
     mensuelle/cumulée de l'humus (Mh) sur les 12 mois.

  2. Bilan de fertilisation azotée COMIFER, sur les 3 niveaux de précision du
     classeur ("1 Bilan Simple", "2 Bilan Intermédiaire", "3 Bilan Avancé"),
     avec la table des besoins NPK par culture (mobilisation/exportation) et
     la dose plafond N réglementaire (arrêté IDF).

  3. Tables de référence consultables : légendes des sigles, teneurs N et PK
     des récoltes (grilles COMIFER 2013/2009), composition et coefficients
     d'équivalence des engrais/amendements, densité du sol par texture,
     seuils P2O5/K2O Olsen (grille COMIFER PKMg Centre Bassin Parisien),
     variabilité saisonnière du pH selon la CEC, sensibilité des cultures aux
     carences en oligo-éléments, stratégie de chaulage. Les tableaux/planches
     que le classeur ne fournit que sous forme d'image (grille nationale
     complète des seuils P/K, grille des coefficients multiplicatifs P/K,
     biodisponibilité des éléments selon le pH...) sont fournis en image dans
     l'onglet "Références" de l'application.

Toutes les formules ci-dessous sont recopiées depuis les cellules du
classeur (voir commentaires "Excel:" au fil du code) ; seules les valeurs
d'exemple du classeur ont été conservées comme valeurs par défaut de
l'interface.

Contact GAB IDF pour toute question sur la méthode : Ernest HENG -
07.86.47.12.59 - e.heng@bioiledefrance.fr
"""

import math

NON_RENSEIGNE = "Non renseigné"

# ====================================================================
# 1. TABLES DE RÉFÉRENCE SAISIES À LA MAIN (tableaux fournis en image
#    dans l'onglet "Aide" du classeur — non lisibles comme cellules)
# ====================================================================

# --- Densité apparente du sol selon la texture (onglet "Aide", tableau
# extrait du guide technique "Les produits organiques utilisables en
# agriculture en Languedoc-Roussillon", Chambre d'Agriculture LR, nov. 2011)
DENSITE_SOL_PAR_TEXTURE = [
    # (appréciation au toucher, texture, code, densité T/m3)
    ("Très fine", "argileuse lourde", "AA", 1.35),
    ("Très fine", "argileuse", "UN", 1.45),
    ("Fine", "argilo-sableuse", "As et AS", 1.55),
    ("Fine", "argile-limono-sableuse", "Si", 1.5),
    ("Fine", "limon-argilo-sableuse", "LE", 1.45),
    ("Fine", "argile-limoneuse et limon argileux", "Al et La", 1.4),
    ("Moyenne", "sablo-argileux et sable-argilo-limoneux", "SA et SAL", 1.5),
    ("Moyenne", "limon sablo-argileuse", "Lsa", 1.5),
    ("Moyenne", "limoneuse", "L", 1.35),
    ("Moyenne", "limon pur", "Ll", 1.45),
    ("Grossière", "limon sableux", "Ls", 1.45),
    ("Grossière", "sableuse et sablo-limoneuse", "S et Sl", 1.4),
    ("Très grossière", "sable", "Ss", 1.35),
]

# --- Seuils P2O5 Olsen et K2O échangeable (mg/kg), grille COMIFER PKMg
# Sept. 2019, région "Centre Bassin parisien" (référence la plus proche du
# contexte Île-de-France de cet outil). Chaque entrée : (Trenf, Timp) pour
# forte / moyenne / faible exigence de la culture. Le maraîchage relève en
# général de la "forte exigence".
SEUILS_P2O5_CENTRE_BASSIN_PARISIEN = {
    "Limons battants":                              {"forte": (50, 80),  "moyenne": (50, 80),  "faible": (20, 70)},
    "Limons de Beauce":                              {"forte": (50, 80),  "moyenne": (50, 60),  "faible": (20, 70)},
    "Sables":                                        {"forte": (50, 80),  "moyenne": (50, 80),  "faible": (20, 70)},
    "Limons sableux":                                {"forte": (50, 80),  "moyenne": (50, 80),  "faible": (20, 70)},
    "Argilo-calcaires superficiels caillouteux":     {"forte": (60, 90),  "moyenne": (60, 90),  "faible": (30, 80)},
    "Argilo-calcaires profonds peu caillouteux":     {"forte": (60, 90),  "moyenne": (60, 90),  "faible": (30, 80)},
    "Argilo-calcaires de Beauce":                    {"forte": (60, 90),  "moyenne": (60, 90),  "faible": (30, 80)},
}

SEUILS_K2O_CENTRE_BASSIN_PARISIEN = {
    "Limons battants":                              {"forte": (170, 300), "moyenne": (120, 180), "faible": (80, 150)},
    "Limons de Beauce":                              {"forte": (200, 400), "moyenne": (150, 220), "faible": (100, 180)},
    "Sables":                                        {"forte": (150, 200), "moyenne": (70, 120),  "faible": (40, 100)},
    "Limons sableux":                                {"forte": (170, 250), "moyenne": (120, 180), "faible": (80, 150)},
    "Argilo-calcaires superficiels caillouteux":     {"forte": (300, 400), "moyenne": (300, 400), "faible": (150, 300)},
    "Argilo-calcaires profonds peu caillouteux":     {"forte": (200, 300), "moyenne": (200, 300), "faible": (100, 180)},
    "Argilo-calcaires de Beauce":                    {"forte": (170, 300), "moyenne": (170, 250), "faible": (100, 200)},
}

TYPES_SOL_CBP = list(SEUILS_P2O5_CENTRE_BASSIN_PARISIEN.keys())
NIVEAUX_EXIGENCE = ["forte", "moyenne", "faible"]

# --- Variabilité saisonnière du pH selon la CEC (onglet "Aide", Tableau
# 5.5, données MEAC). Écart hiver/été utilisé pour affiner le pH minimal
# estival (le classeur utilise par défaut un écart fixe de 0,7 en "Analyse
# de Sol" ; ce tableau donne l'écart réel mesuré selon la classe de CEC).
ECART_PH_SAISONNIER_PAR_CEC = [
    # (libellé classe, CEC max meq/100g exclus, écart hiver-été)
    ("Sols légers (CEC < 7 meq/100g)", 7.0, 1.02),
    ("Sols intermédiaires (7 - 20 meq/100g)", 20.0, 0.72),
    ("Sols lourds (CEC > 20 meq/100g)", float("inf"), 0.47),
]

# --- Sensibilité de quelques cultures légumières aux carences en
# oligo-éléments (onglet "Aide", tableau image ; niveaux "moyen" / "eleve")
OLIGO_ELEMENTS = ["fer", "manganèse", "cuivre", "zinc", "bore", "molybdène"]

SENSIBILITE_OLIGOELEMENTS = {
    "Artichaut":  {"manganèse": "moyen", "bore": "moyen"},
    "Asperge":    {},
    "Broccoli":   {"fer": "eleve", "manganèse": "moyen", "bore": "eleve", "molybdène": "moyen"},
    "Céleri":     {"cuivre": "moyen", "bore": "eleve"},
    "Chou":       {"fer": "eleve", "manganèse": "moyen", "bore": "eleve", "molybdène": "moyen"},
    "Chou-fleur": {"fer": "eleve", "manganèse": "moyen", "cuivre": "moyen", "bore": "eleve", "molybdène": "eleve"},
    "Concombre":  {"fer": "moyen", "manganèse": "eleve", "cuivre": "moyen", "bore": "moyen"},
    "Carotte":    {"cuivre": "eleve", "zinc": "moyen", "bore": "eleve"},
    "Épinard":    {"fer": "eleve", "manganèse": "eleve", "cuivre": "moyen", "molybdène": "eleve"},
    "Haricot":    {"fer": "eleve", "manganèse": "eleve", "zinc": "eleve", "molybdène": "moyen"},
    "Laitue":     {"manganèse": "eleve", "cuivre": "eleve", "bore": "moyen", "molybdène": "eleve"},
    "Melon":      {"manganèse": "moyen", "bore": "moyen", "molybdène": "eleve"},
    "Navet":      {"bore": "eleve"},
    "Radis":      {"manganèse": "eleve", "molybdène": "eleve"},
    "Tomate":     {"manganèse": "moyen", "cuivre": "moyen", "zinc": "moyen", "bore": "moyen", "molybdène": "moyen"},
}

# --- Causes possibles de carences en oligo-éléments (onglet "Aide", tableau
# image ARVALIS) : texte de synthèse par élément (climat / sol / pratiques).
CAUSES_CARENCES_OLIGOELEMENTS = {
    "manganèse": "Favorisée par : sécheresse en automne/hiver ; pH eau > 6,8 ; sol riche en "
                  "sables grossiers, en matière organique, sol léger et aéré ; travail du sol "
                  "trop fin et trop profond ; chaulage.",
    "cuivre": "Favorisée par : pH eau > 6,8 ; sol riche en matière organique ; teneur très "
              "élevée en phosphore assimilable ; chaulage.",
    "zinc": "Favorisée par : printemps froids ; pH eau > 7 ; teneur très élevée en phosphore "
            "assimilable ; apports importants d'engrais phosphatés ; chaulage.",
    "bore": "Favorisée par : sécheresse ; pH eau > 7 ; sols riches en calcaire actif ; sol "
            "sableux ; sol pauvre en matière organique (< 2 %) ; chaulage.",
    "molybdène": "Favorisée par : pH acide ; sol pauvre en matière organique.",
    "fer": "Favorisée par : sols froids et humides ; sol riche en calcaire actif ; variétés "
           "sensibles.",
}

# --- Stratégie de chaulage / apport (onglet "Aide", Tableau 10.5). La
# fonction strategie_chaulage() ci-dessous encode cette grille de décision.

# ====================================================================
# 2. DONNÉES EXTRAITES TELLES QUELLES DU CLASSEUR (onglets Légendes,
#    Teneurs N, Teneurs PK, NPK Engrais-amend, 0/1/2/3 Bilan)
# ====================================================================
LEGENDES = [['HCC', "Humidité à la capacité au champ. C'est la quantité d'eau maximal qu'un sol peut retenir"],
 ['HpF',
  "Humidité au point de flétrissement. C'est la quantité d'eau à partir de laquelle la plante ne "
  "peut plus extraire de l'eau du sol (force de sucion de la plante inférieur à la force "
  "électrostatique de l'eau avec les matériaux du sol)"],
 ['ISMO',
  "Indicateur de stabilité Iso-humique. Correspond à la part d'un échantillon de terre qui abonde "
  'la part stable/liée de la MO, qui minéralise lentement, comparativement à la MO labile'],
 ['MO',
  'Matière Organique. Correspond à 1,72 x C (taux de carbone mesuré par carbonisation de '
  "l'échantillon)"],
 ['CEC',
  "Capacité d'échange cationique. Correspond à la quantité de zone d'échange chargée négativement "
  'dans un échantillon, qui permet de connaitre approximativement la capacité du sol à capter les '
  'ions chargé positivement (Ca2+, K+, Mg2+)'],
 ['Trenf',
  'Taux renforcé. Correspond à la teneur minimale en dessous de laquelle une fertilisation '
  'équivalente aux exportations ne suffit plus, et nécessite un renforcement.'],
 ['Timp',
  'Taux Impasse. Correspond à la teneur minimale au-dessus de laquelle aucune perte de rendement '
  'supérieur à 10 % n’est constatée, et l’impasse annuelle de fertilisation possible.'],
 ['CaCO3',
  'Carbonate de Calcium. Correspond à la teneur en "Calcium total". Amendement parfois '
  'naturellement présent, se dissociant en Ca2++ pour la plante et CO32- qui agit comme une base '
  'et augmente le pH du sol'],
 ['K2',
  'Taux de minéralisation de la MO ou du carbone. Peut correspondre au taux de minéralisation de '
  "l'azote à l'équilibre (pas d'apport recent)"],
 ['BEB',
  "Besoin en base. Correspond au besoin d'apport en base (va capter des H+) calculé selon les "
  "modèles et permettant l'augmentation du pH (perte de H+), pour améliorer les conditions de "
  'culture'],
 ['VN',
  "Valeur neutralisante d'un amendement. Corrrespond à la quantité d'oxyde de calcium (base) du "
  'produit, qui va agir sur le pH, et permettant de calculer la dose à épandre'],
 ['Km',
  "Taux de minéralisation de l'azote humifié - azote stable du sol. A considérer selon le pas de "
  'temps choisi : journalier, hebdomadaire, mensuel, annuel, sur la culture. Peut être théorique '
  "(COMIFER), ou mesuré en pratique (analyse de la minéralisation de l'azote)"],
 ['IB',
  "Indice de battance du sol. Permet de quantifier le niveau de battance du sol, c'est-à-dire son "
  "incapacité à maintenir une structure en surface à cause de l'eau apporté. Dépend du pH, de la "
  'composition en argile, MO et limon.'],
 ['JN',
  'Jours normalisés. Nombre de jours équivalents à des jours normalisés, par convention sous '
  'condition de température égal à 15°C et avec une humidité égale à la capacité au champ'],
 ['Mh', "Minéralisation nette de l'Humus du sol"],
 ['MF', "Matière Fraiche = avec eau au moment de l'analyse"],
 ['MS', 'Matière sèche = sans eau'],
 ['PRO',
  "Produit Résiduaire Organique. Correspond à des produits d'origine organiques ayant ou non subis "
  'des traitements'],
 ['Keq',
  "Coefficient d'équivalence d'un apport pour un élément (N,P,K). Correspond à l'efficacité d'un "
  'engrais par rapport à un engrais de référence, pour une durée de culture donnée. Concrètement, '
  "il équivaut au rapport entre la disponibilité potentielle d'un apport en un élément et sa "
  "teneur totale en un élément, sans considération des niveaux d'absorption de la culture et de "
  "l'environnement, pour le temps d'implantation d'une culture donnée"]]

CULTURES_BILAN_AZOTE = [{'type': 'Mob.',
  'famille': 'Alliacées',
  'espece': 'Ail',
  'N': 70,
  'P': 70,
  'K': 150,
  'Mg': None,
  'rendement': None,
  'source': 'ITAB',
  'commentaire': "Peu exigeant. Mobilisation limité en N/P. P intervient au moment de l'émission "
                 'des racines et au début de la bulbaison. K nécessaires pendant toute la durée du '
                 'cycle et en particulier au moment de la bulbaison. Pas de N pendant bulbaison. '
                 'Alliacées => Besoin en soufre'},
 {'type': 'Exp.',
  'famille': 'Alliacées',
  'espece': 'Oignon',
  'N': 120,
  'P': 80,
  'K': 150,
  'Mg': None,
  'rendement': None,
  'source': 'ITAB',
  'commentaire': 'Système racinaire peu développpé et superficiel => Exportations modérées mais '
                 'niveau de fertilisation important. Phase végétative : N important, P/K modéré. '
                 'Phase bulbaison : N provient du feuillage, P/K importants. Alliacées => Besoin '
                 'en soufre. Limiter à 110 U de N pour éviter les maladies en fin de culture'},
 {'type': 'Exp.',
  'famille': 'Alliacées',
  'espece': 'Poireaux',
  'N': 160,
  'P': 60,
  'K': 245,
  'Mg': 18,
  'rendement': '50',
  'source': 'ITAB',
  'commentaire': 'Besoin en N : 180 à 275 kg/ha. Excès de N favrosie les maladies comme rouille et '
                 'mildiou. Alliacées => Besoin en souffre'},
 {'type': 'Mob.',
  'famille': 'Alliacées',
  'espece': 'Poireaux Plants',
  'N': 60,
  'P': 40,
  'K': 50,
  'Mg': None,
  'rendement': None,
  'source': 'ITAB',
  'commentaire': 'Exigeant en fumure. Préférence à minéralisation rapide type guano'},
 {'type': 'Exp.',
  'famille': 'Apiacées',
  'espece': 'Carottes',
  'N': 110,
  'P': 40,
  'K': 200,
  'Mg': 15,
  'rendement': None,
  'source': 'ITAB',
  'commentaire': "CaO : 20 kg/ha. Besoin en N faible les 7 premières semaines. Pas d'amendemants "
                 'organiques juste avant la culture'},
 {'type': 'Mob.',
  'famille': 'Apiacées',
  'espece': 'Carottes',
  'N': 175,
  'P': 91,
  'K': 357,
  'Mg': 25,
  'rendement': 70,
  'source': 'CTIFL',
  'commentaire': 'CaO : 130-180 kg/ha. Besoin en N faible les 7 premières semaines. Pas '
                 "d'amendemants organiques juste avant la culture"},
 {'type': 'Exp.',
  'famille': 'Apiacées',
  'espece': 'Carottes',
  'N': 115,
  'P': 70,
  'K': 340,
  'Mg': 15,
  'rendement': 70,
  'source': 'CTIFL',
  'commentaire': 'CaO : 40-60 kg/ha. Besoin en N faible les 7 premières semaines. Pas '
                 "d'amendemants organiques juste avant la culture"},
 {'type': 'Mob.',
  'famille': 'Apiacées',
  'espece': 'Céleri',
  'N': 250,
  'P': 160,
  'K': 300,
  'Mg': 20,
  'rendement': None,
  'source': 'ITAB',
  'commentaire': 'Aime les sols riche en MO. Attention à la libération tardive de N avant la '
                 'récolte sensibilisant aux pourritures de conservation. Céléri-rave : Excès de N '
                 'entraine diminution du goût, rouille sur pomme et tip-burn. Excès de K : '
                 'symptome de carence MgO. Rave petites brunes et nervures crevassées : Carence en '
                 'bore, excès de fumure K, sols calcaires, sécheresse'},
 {'type': 'Exp.',
  'famille': 'Apiacées',
  'espece': 'Fenouil',
  'N': 120,
  'P': 80,
  'K': 180,
  'Mg': None,
  'rendement': None,
  'source': 'ITAB',
  'commentaire': None},
 {'type': 'Exp.',
  'famille': 'Apiacées',
  'espece': 'Panais',
  'N': 120,
  'P': 100,
  'K': 250,
  'Mg': None,
  'rendement': None,
  'source': 'Voltz',
  'commentaire': "Pas d'amendemants organiques juste avant la culture"},
 {'type': 'Exp.',
  'famille': 'Astéracées',
  'espece': 'Chicorée',
  'N': 80,
  'P': 70,
  'K': 150,
  'Mg': None,
  'rendement': None,
  'source': 'ITAB',
  'commentaire': "Eviter l'excès d'azote favorisant les nécroses marginales des bords de feuilles. "
                 'Carences en bore : feuilles rigides et une atrophie racinaires'},
 {'type': 'Exp.',
  'famille': 'Astéracées',
  'espece': 'Laitue',
  'N': 80,
  'P': 40,
  'K': 170,
  'Mg': 10,
  'rendement': '42',
  'source': 'CTIFL/ITAB',
  'commentaire': 'CaO : 40 kg/ha'},
 {'type': 'Mob.',
  'famille': 'Brassicacées',
  'espece': 'Chou Pom & Brux',
  'N': 200,
  'P': 100,
  'K': 250,
  'Mg': None,
  'rendement': None,
  'source': 'ITAB',
  'commentaire': 'Exigeant en soufre'},
 {'type': 'Exp.',
  'famille': 'Brassicacées',
  'espece': 'Chou Rave',
  'N': 100,
  'P': 60,
  'K': 200,
  'Mg': None,
  'rendement': None,
  'source': 'ITAB',
  'commentaire': None},
 {'type': 'Exp.',
  'famille': 'Brassicacées',
  'espece': 'Chou Fleur & Broc',
  'N': 250,
  'P': 150,
  'K': 300,
  'Mg': None,
  'rendement': None,
  'source': 'ITAB',
  'commentaire': 'Besoins importants au printemps (pas de minéralisation) et étalés'},
 {'type': 'Exp.',
  'famille': 'Brassicacées',
  'espece': 'Navet',
  'N': 90,
  'P': 50,
  'K': 140,
  'Mg': None,
  'rendement': None,
  'source': 'ITAB',
  'commentaire': "Navet d'hiver : complément potassique. Navet de printemps : Engrais organique à "
                 'minéralisation rapide'},
 {'type': 'Exp.',
  'famille': 'Brassicacées',
  'espece': 'Radis bottes',
  'N': 50,
  'P': 25,
  'K': 85,
  'Mg': 5,
  'rendement': '25',
  'source': 'ITAB',
  'commentaire': None},
 {'type': 'Mob.',
  'famille': 'Chénopodiacées',
  'espece': 'Betterave vrac',
  'N': 100,
  'P': 35,
  'K': 185,
  'Mg': None,
  'rendement': None,
  'source': 'ITAB',
  'commentaire': 'Préference Guano ou complément de patenkali si reliquat azoté important'},
 {'type': 'Exp.',
  'famille': 'Chénopodiacées',
  'espece': 'Betterave bottes',
  'N': 50,
  'P': 25,
  'K': 100,
  'Mg': None,
  'rendement': None,
  'source': 'ITAB',
  'commentaire': 'Préference Guano ou complément de patenkali si reliquat azoté important'},
 {'type': 'Exp.',
  'famille': 'Chénopodiacées',
  'espece': 'Blette PC',
  'N': 150,
  'P': 60,
  'K': 220,
  'Mg': None,
  'rendement': None,
  'source': 'ITAB',
  'commentaire': "Fractionner les apports d'azote en cours de culture"},
 {'type': 'Exp.',
  'famille': 'Chénopodiacées',
  'espece': 'Blette SA',
  'N': 250,
  'P': 180,
  'K': 400,
  'Mg': None,
  'rendement': None,
  'source': 'ITAB',
  'commentaire': "Fractionner les apports d'azote en cours de culture"},
 {'type': 'Exp',
  'famille': 'Chénopodiacées',
  'espece': 'Epinards',
  'N': 100,
  'P': 70,
  'K': 250,
  'Mg': None,
  'rendement': '40-60',
  'source': 'ITAB',
  'commentaire': "Les apports d'azote trop important diminuent la teneur en matière sèche et "
                 "augmentent les nitrates dans la plante. L'excès de potasse entrainent des "
                 'carences en bore et magnésium'},
 {'type': 'Exp.',
  'famille': 'Cucurbitacées',
  'espece': 'Concombre',
  'N': 250,
  'P': 160,
  'K': 400,
  'Mg': 40,
  'rendement': '80-120',
  'source': 'CTIFL/ITAB',
  'commentaire': 'Bonne valorisation des apports en matières organiques => Amendement organique '
                 'avant plantation. Sensible au carences minérales'},
 {'type': 'Exp.',
  'famille': 'Cucurbitacées',
  'espece': 'Courgette SA',
  'N': 300,
  'P': 80,
  'K': 450,
  'Mg': 80,
  'rendement': '70-120',
  'source': 'CTIFL/ITAB',
  'commentaire': 'N essentiel au bon développmeent des plantes et reste un élément clé du '
                 "rendement. Pas d'excès : emballement de la végétation, nuit à la nouaison."},
 {'type': 'Mob.',
  'famille': 'Cucurbitacées',
  'espece': 'Courgette PC',
  'N': 150,
  'P': 40,
  'K': 250,
  'Mg': None,
  'rendement': '20-50',
  'source': 'CTIFL/ITAB',
  'commentaire': 'N essentiel au bon développmeent des plantes et reste un élément clé du '
                 "rendement. Pas d'excès : emballement de la végétation, nuit à la nouaison."},
 {'type': 'Mob.',
  'famille': 'Cucurbitacées',
  'espece': 'Melon',
  'N': 150,
  'P': 150,
  'K': 220,
  'Mg': 80,
  'rendement': None,
  'source': 'ITAB',
  'commentaire': 'N/P/Mg :croissance. N/P/K : potentiel de floraison (fc température). Mg/P/<N : '
                 'rendement. P : développement racinaire.(fc température sol). Carence en Bore : '
                 'floraison réduite et fruits craquelés. Carence Mg : décoloration du feuillage.'},
 {'type': 'Exp.',
  'famille': 'Cucurbitacées',
  'espece': 'Melon',
  'N': 155,
  'P': 70,
  'K': 277,
  'Mg': 68,
  'rendement': '30-40',
  'source': 'CTIFL',
  'commentaire': 'N/P/Mg :croissance. N/P/K : potentiel de floraison (fc température). Mg/P/<N : '
                 'rendement. P : développement racinaire.(fc température sol). Carence en Bore : '
                 'floraison réduite et fruits craquelés. Carence Mg : décoloration du feuillage.'},
 {'type': 'Exp.',
  'famille': 'Cucurbitacées',
  'espece': 'Potimarron',
  'N': 120,
  'P': 60,
  'K': 100,
  'Mg': None,
  'rendement': None,
  'source': 'ITAB',
  'commentaire': 'Gourmand en éléments minéraux. Excès de fertilisation préjudiciable à la '
                 'conservation. Apprécie les fumures organiques. Ricin contre les rongeurs'},
 {'type': 'Exp.',
  'famille': 'Fabacées',
  'espece': 'Haricot Plante',
  'N': 170,
  'P': 80,
  'K': 200,
  'Mg': None,
  'rendement': None,
  'source': 'ITAB',
  'commentaire': "Utilise au maximum la richesse du sol. Fixation de l'azote atmosphérique à "
                 "partir du stade de floraison. Petit apport d'azote initial favorise "
                 "l'enracinement et la mise en place de l'association symbiotique pour la fixation "
                 "d'azote. Besoins P/K doivent être couverts (avant semis)"},
 {'type': 'Exp.',
  'famille': 'Fabacées',
  'espece': 'Fèves',
  'N': 50,
  'P': 100,
  'K': 150,
  'Mg': None,
  'rendement': None,
  'source': 'MBIO',
  'commentaire': 'Rendement de 3-4t/ha'},
 {'type': 'Exp.',
  'famille': 'Fabacées',
  'espece': 'Petit Pois Nain Gousse',
  'N': 70,
  'P': 20,
  'K': 35,
  'Mg': None,
  'rendement': None,
  'source': 'ITAB',
  'commentaire': 'Besoin en bore et molybdène important pouvant entrainer une perturbation de la '
                 "croissance. Une carence en molybdène peut bloquer la fixation de l'azote par les "
                 'rhizobium. Une carence en cuivre entrave le remplissage des gousses'},
 {'type': 'Mob.',
  'famille': 'Poacées',
  'espece': 'Mais',
  'N': 180,
  'P': 70,
  'K': 130,
  'Mg': None,
  'rendement': None,
  'source': 'edu.fr',
  'commentaire': None},
 {'type': 'Mob.',
  'famille': 'Solanacées',
  'espece': 'Aubergine',
  'N': 260,
  'P': 70,
  'K': 260,
  'Mg': 40,
  'rendement': None,
  'source': 'ITAB',
  'commentaire': 'Besoin pour une production sous serre de 40 t/ha. Exigeant en souffre. Réagit '
                 'bien aux apports de magnésie MgCO3.'},
 {'type': 'Mob.',
  'famille': 'Solanacées',
  'espece': 'Aubergine SA',
  'N': 490,
  'P': 105,
  'K': 465,
  'Mg': 55,
  'rendement': '100-140',
  'source': 'ITAB',
  'commentaire': 'Exigeant en souffre. Réagit bien aux apports de magnésie MgCO3.'},
 {'type': 'Mob.',
  'famille': 'Solanacées',
  'espece': 'Aubergine PC',
  'N': 210,
  'P': 45,
  'K': 225,
  'Mg': 25,
  'rendement': '30-50',
  'source': 'ITAB',
  'commentaire': 'Exigeant en souffre. Réagit bien aux apports de magnésie MgCO3.'},
 {'type': 'Exp.',
  'famille': 'Solanacées',
  'espece': 'Poivron',
  'N': 150,
  'P': 80,
  'K': 200,
  'Mg': None,
  'rendement': None,
  'source': 'ITAB',
  'commentaire': 'Pour un rendement moyen de 25 t/ha. Eviter les fumures fraiches. Fertilisation '
                 'pendant la préparation de sol.'},
 {'type': 'Exp.',
  'famille': 'Solanacées',
  'espece': 'Poivron SA',
  'N': 340,
  'P': 100,
  'K': 640,
  'Mg': 70,
  'rendement': '30-40',
  'source': 'ITAB',
  'commentaire': 'Eviter les fumures fraiches. Fertilisation pendant la préparation de sol.'},
 {'type': 'Exp.',
  'famille': 'Solanacées',
  'espece': 'Poivron PC',
  'N': 160,
  'P': 40,
  'K': 250,
  'Mg': 35,
  'rendement': '20-30',
  'source': 'ITAB',
  'commentaire': 'Eviter les fumures fraiches. Fertilisation pendant la préparation de sol.'},
 {'type': 'Mob.',
  'famille': 'Solanacées',
  'espece': 'Pomme de terre',
  'N': 100,
  'P': 35,
  'K': 230,
  'Mg': None,
  'rendement': '40-50',
  'source': 'ITAB',
  'commentaire': 'N favorise le développement foliaire, formation et grossissement des tubercules. '
                 'Azote stocké dans le feuillage puis migre dans les tubercules. Apporté en excès, '
                 'il retarde la tubérisation au profit du foliaire (attention donc si primeur. N '
                 'important : Tubercules gros. P favorise le nombre de tubercules. K facilite la '
                 'synthèse des glucides et leur migration dans les tubercules, favorisant les gros '
                 'tubercules.'},
 {'type': 'Exp.',
  'famille': 'Solanacées',
  'espece': 'Tomates',
  'N': 300,
  'P': 100,
  'K': 400,
  'Mg': 150,
  'rendement': None,
  'source': 'ITAB',
  'commentaire': 'Pour un rendement moyen de 80 à 100 t/ha. Apport de fond. Patenkali : 200 à 500 '
                 'kg/ha en complément'},
 {'type': 'Exp.',
  'famille': 'Solanacées',
  'espece': 'Tomates SA',
  'N': 400,
  'P': 136,
  'K': 928,
  'Mg': 118,
  'rendement': '150-250',
  'source': 'CTIFL',
  'commentaire': 'Pour un rendement moyen de 80 à 100 t/ha. Apport de fond. Patenkali : 200 à 500 '
                 'kg/ha en complément'},
 {'type': 'Exp.',
  'famille': 'Solanacées',
  'espece': 'Tomates PC',
  'N': 140,
  'P': 55,
  'K': 232,
  'Mg': 36,
  'rendement': '60',
  'source': 'CTIFL',
  'commentaire': 'Pour un rendement moyen de 80 à 100 t/ha. Apport de fond. Patenkali : 200 à 500 '
                 'kg/ha en complément'},
 {'type': 'Exp.',
  'famille': 'Valérianacées',
  'espece': 'Mache',
  'N': 50,
  'P': 35,
  'K': 85,
  'Mg': 25,
  'rendement': '10-15',
  'source': 'ITAB',
  'commentaire': None},
 {'type': 'Exp.',
  'famille': 'Convolvulacées',
  'espece': 'Patate Douce',
  'N': 100,
  'P': 50,
  'K': 220,
  'Mg': None,
  'rendement': None,
  'source': 'CIRAD',
  'commentaire': "Excès d'azote au-dela de 100 unité provoque un développement végétatif important "
                 'défavorable à la tubérisation.'},
 {'type': 'Mob.',
  'famille': 'Convolvulacées',
  'espece': 'Patate Douce',
  'N': 65,
  'P': 160,
  'K': 100,
  'Mg': None,
  'rendement': None,
  'source': 'CIRAD',
  'commentaire': None}]

DOSE_PLAFOND_N = [{'legume': 'Ail automne', 'variante': None, 'nmax': 100},
 {'legume': 'Artichaut', 'variante': 'Artichaut camus 1ère année', 'nmax': 150},
 {'legume': 'Artichaut', 'variante': 'Artichaut camus 2ème année', 'nmax': 150},
 {'legume': 'Artichaut', 'variante': 'Artichaut camus 3ème année', 'nmax': 150},
 {'legume': 'Asperge blanche, Asperge verte',
  'variante': 'Asperge 1ère pousse (20000 plants/ha)',
  'nmax': 150},
 {'legume': 'Asperge blanche, Asperge verte',
  'variante': 'Asperge 2ème pousse (20000 plants/ha)',
  'nmax': 150},
 {'legume': 'Asperge blanche, Asperge verte',
  'variante': 'Asperge 3ème pousse (20000 plants/ha)',
  'nmax': 150},
 {'legume': 'Aubergine', 'variante': 'Sous abri (cycle 6-7 mois)', 'nmax': 500},
 {'legume': 'Aubergine', 'variante': 'Sous abri (cycle 9-10 mois)', 'nmax': 700},
 {'legume': 'Betterave rouge (été-automne)', 'variante': None, 'nmax': 200},
 {'legume': 'Bettes et cardes', 'variante': None, 'nmax': 200},
 {'legume': 'Carotte plein champ', 'variante': 'Carotte cycle cultural d’été', 'nmax': 100},
 {'legume': 'Carotte plein champ', 'variante': 'Carotte cycle cultural de printemps', 'nmax': 100},
 {'legume': 'Carotte plein champ', 'variante': 'Carotte cycle cultural primeur', 'nmax': 100},
 {'legume': 'Céleri branche plein champ', 'variante': None, 'nmax': 350},
 {'legume': 'Céleri rave plein champ', 'variante': None, 'nmax': 200},
 {'legume': 'Chicorée plein champ',
  'variante': 'Chicorée géante maraîchère (récolte octobre)',
  'nmax': 120},
 {'legume': 'Chicorée plein champ',
  'variante': 'Chicorée fine maraîchère (printemps)',
  'nmax': 120},
 {'legume': 'Chicorée plein champ',
  'variante': 'Chicorée fine maraîchère (été-automne)',
  'nmax': 120},
 {'legume': 'Chicorée plein champ',
  'variante': 'Chicorée fine maraîchère (abri-printemps)',
  'nmax': 120},
 {'legume': 'Chicorée plein champ', 'variante': 'Chicorée frisée (été)', 'nmax': 120},
 {'legume': 'Chicorée plein champ', 'variante': 'Chicorée frisée (automne)', 'nmax': 120},
 {'legume': 'Chicorée plein champ', 'variante': 'Chicorée scarole', 'nmax': 120},
 {'legume': 'Chou brocolis', 'variante': None, 'nmax': 150},
 {'legume': 'Chou de Bruxelles plein champ', 'variante': None, 'nmax': 250},
 {'legume': 'Chou-fleur', 'variante': 'Chou-fleur d’été', 'nmax': 200},
 {'legume': 'Chou-fleur', 'variante': 'Chou-fleur d’automne', 'nmax': 200},
 {'legume': 'Chou-fleur', 'variante': 'Chou-fleur d’hiver', 'nmax': 200},
 {'legume': 'Choux pommés', 'variante': 'Choux pommés précoce', 'nmax': 200},
 {'legume': 'Choux pommés', 'variante': 'Choux pommés hiver', 'nmax': 200},
 {'legume': 'Choux pommés', 'variante': 'Choux pommés à choucroute', 'nmax': 200},
 {'legume': 'Concombre', 'variante': 'Concombre plein champ', 'nmax': 200},
 {'legume': 'Concombre', 'variante': 'sous abri (cycle 3 mois)', 'nmax': 300},
 {'legume': 'Concombre', 'variante': 'sous abri (cycle 6-7 mois)', 'nmax': 500},
 {'legume': 'Cornichon', 'variante': 'plein champ', 'nmax': 90},
 {'legume': 'Courgette', 'variante': 'Courgette plein champ', 'nmax': 180},
 {'legume': 'Courgette', 'variante': 'Courgette sous abri', 'nmax': 180},
 {'legume': 'Cresson', 'variante': None, 'nmax': 210},
 {'legume': 'Échalote plein champ', 'variante': None, 'nmax': 120},
 {'legume': 'Endive (Racines) plein champ', 'variante': None, 'nmax': 80},
 {'legume': 'Epinard (1 à 2 coupes) plein champ', 'variante': None, 'nmax': 150},
 {'legume': 'Fenouil plein champ', 'variante': None, 'nmax': 130},
 {'legume': 'Fève (sec) plein champ', 'variante': None, 'nmax': 50},
 {'legume': 'Fraisier', 'variante': 'Fraise saison ex : ELSANTA', 'nmax': 120},
 {'legume': 'Fraisier', 'variante': 'Fraise précoce ex : Gariguette', 'nmax': 120},
 {'legume': 'Fraisier', 'variante': 'Fraise remontante ex : Selva', 'nmax': 120},
 {'legume': 'Framboise', 'variante': None, 'nmax': 210},
 {'legume': 'Groseille', 'variante': None, 'nmax': 210},
 {'legume': 'Haricots à écosser et demi-sec (grain)', 'variante': None, 'nmax': 80},
 {'legume': 'Haricots secs', 'variante': None, 'nmax': 80},
 {'legume': 'Haricot vert (y.c. haricot beurre)', 'variante': None, 'nmax': 80},
 {'legume': 'Haricot vert nain plein champ', 'variante': None, 'nmax': 80},
 {'legume': 'Laitue (plafond par cycle)', 'variante': 'Laitue beurre printemps', 'nmax': 120},
 {'legume': 'Laitue (plafond par cycle)', 'variante': 'Laitue beurre serre automne', 'nmax': 120},
 {'legume': 'Laitue (plafond par cycle)', 'variante': 'Laitue beurre serre hiver', 'nmax': 120},
 {'legume': 'Laitue (plafond par cycle)', 'variante': 'Laitue romaine printemps', 'nmax': 120},
 {'legume': 'Lentilles', 'variante': None, 'nmax': 0},
 {'legume': 'Mâche plein champ', 'variante': 'Mâche', 'nmax': 50},
 {'legume': 'Maïs doux', 'variante': None, 'nmax': 180},
 {'legume': 'Melon', 'variante': 'Melon sans irrigation plein champ', 'nmax': 120},
 {'legume': 'Melon', 'variante': 'Melon sous abri plein champ', 'nmax': 120},
 {'legume': 'Melon', 'variante': 'Melon serre', 'nmax': 120},
 {'legume': 'Navet plein champ', 'variante': None, 'nmax': 20},
 {'legume': 'Pastèque plein champ', 'variante': None, 'nmax': 210},
 {'legume': 'Poireau plein champ', 'variante': None, 'nmax': 200},
 {'legume': 'Poirée plein champ', 'variante': None, 'nmax': 210},
 {'legume': 'Petit pois (grain)', 'variante': None, 'nmax': 50},
 {'legume': 'Pissenlit', 'variante': None, 'nmax': 60},
 {'legume': 'Pois plein champ', 'variante': None, 'nmax': 40},
 {'legume': 'Poivron vert et rouge', 'variante': 'Sous abri (cycle 6-7 mois)', 'nmax': 500},
 {'legume': 'Poivron vert et rouge', 'variante': 'Sous abri (cycle 9-10 mois)', 'nmax': 700},
 {'legume': 'Potiron, courge, citrouille', 'variante': None, 'nmax': 100},
 {'legume': 'Radis', 'variante': None, 'nmax': 100},
 {'legume': 'Rhubarbe', 'variante': None, 'nmax': 100},
 {'legume': 'Salsifi et scorsonères', 'variante': None, 'nmax': 210},
 {'legume': 'Salade autres (plafond par cycle)', 'variante': None, 'nmax': 120},
 {'legume': 'Tomate', 'variante': 'Tomate plein champ', 'nmax': 250},
 {'legume': 'Tomate', 'variante': 'Tomate sous abri (6-7 mois)', 'nmax': 500},
 {'legume': 'Tomate', 'variante': 'Tomate sous abri (9-10 mois)', 'nmax': 700}]

ENGRAIS_AMENDEMENTS = [{'nom': 'Compost bovins',
  'N_kg_t': 6.7,
  'P2O5_kg_t': 3.6,
  'K2O_kg_t': 10.8,
  'MgO_kg_t': 2,
  'C_kg_t': 81.7,
  'KeqN': 0.2,
  'KeqP2O5': 0.7,
  'KeqK2O': 1,
  'KeqMgO': 1,
  'source': 'Arvalis'},
 {'nom': 'Compost de biodéchets mén.',
  'N_kg_t': 13.6,
  'P2O5_kg_t': 7.7,
  'K2O_kg_t': 11.2,
  'MgO_kg_t': 5,
  'C_kg_t': 145,
  'KeqN': 0.5,
  'KeqP2O5': 0.9,
  'KeqK2O': 1,
  'KeqMgO': 1,
  'source': 'Arvalis'},
 {'nom': 'Compost de champignion.',
  'N_kg_t': 5.5,
  'P2O5_kg_t': 3,
  'K2O_kg_t': 5,
  'MgO_kg_t': 1.3,
  'C_kg_t': 87.5,
  'KeqN': 0.5,
  'KeqP2O5': 0.9,
  'KeqK2O': 1,
  'KeqMgO': 1,
  'source': 'Arvalis'},
 {'nom': 'Compost de DV',
  'N_kg_t': 10,
  'P2O5_kg_t': 6,
  'K2O_kg_t': 11,
  'MgO_kg_t': 2.8,
  'C_kg_t': 120,
  'KeqN': 0.05,
  'KeqP2O5': 0.55,
  'KeqK2O': 1,
  'KeqMgO': 1,
  'source': 'Arvalis'},
 {'nom': 'Compost ovins',
  'N_kg_t': 8.4,
  'P2O5_kg_t': 7,
  'K2O_kg_t': 25.7,
  'MgO_kg_t': 2.5,
  'C_kg_t': 99,
  'KeqN': 0.2,
  'KeqP2O5': 0.7,
  'KeqK2O': 1,
  'KeqMgO': 1,
  'source': 'Arvalis'},
 {'nom': 'Farines de viande',
  'N_kg_t': 100,
  'P2O5_kg_t': 46.4,
  'K2O_kg_t': 9.8,
  'MgO_kg_t': 2.4,
  'C_kg_t': 411,
  'KeqN': 0.5,
  'KeqP2O5': 0.9,
  'KeqK2O': 1,
  'KeqMgO': 1,
  'source': 'Arvalis'},
 {'nom': 'Fientes de poules pondeuses',
  'N_kg_t': 39.5,
  'P2O5_kg_t': 37.8,
  'K2O_kg_t': 25.7,
  'MgO_kg_t': 8.7,
  'C_kg_t': 314,
  'KeqN': 0.5,
  'KeqP2O5': 0.85,
  'KeqK2O': 1,
  'KeqMgO': 1,
  'source': 'Arvalis'},
 {'nom': 'Fumiers de bovin <2mois',
  'N_kg_t': 5,
  'P2O5_kg_t': 2.5,
  'K2O_kg_t': 6.5,
  'MgO_kg_t': 1.5,
  'C_kg_t': 70,
  'KeqN': 0.3,
  'KeqP2O5': 0.8,
  'KeqK2O': 1,
  'KeqMgO': 1,
  'source': 'Arvalis'},
 {'nom': 'Fumiers de bovin >2mois',
  'N_kg_t': 5.9,
  'P2O5_kg_t': 2.8,
  'K2O_kg_t': 9.5,
  'MgO_kg_t': 1.6,
  'C_kg_t': 129.2,
  'KeqN': 0.3,
  'KeqP2O5': 0.8,
  'KeqK2O': 1,
  'KeqMgO': 1,
  'source': 'Arvalis'},
 {'nom': 'Fumiers de chevaux',
  'N_kg_t': 5.8,
  'P2O5_kg_t': 3.2,
  'K2O_kg_t': 9.3,
  'MgO_kg_t': 1.7,
  'C_kg_t': 129.5,
  'KeqN': 0.3,
  'KeqP2O5': 0.8,
  'KeqK2O': 1,
  'KeqMgO': 1,
  'source': 'Arvalis'},
 {'nom': 'Fumiers de poules pondeuses',
  'N_kg_t': 30.4,
  'P2O5_kg_t': 25,
  'K2O_kg_t': 26.6,
  'MgO_kg_t': 6.7,
  'C_kg_t': 277.9,
  'KeqN': 0.45,
  'KeqP2O5': 0.85,
  'KeqK2O': 1,
  'KeqMgO': 1,
  'source': 'Arvalis'},
 {'nom': 'Vinasses concentrées',
  'N_kg_t': 25,
  'P2O5_kg_t': 2,
  'K2O_kg_t': 70,
  'MgO_kg_t': 1,
  'C_kg_t': 175,
  'KeqN': 0.5,
  'KeqP2O5': 0.55,
  'KeqK2O': 1,
  'KeqMgO': 1,
  'source': 'Arvalis'},
 {'nom': 'Fumier équin',
  'N_kg_t': 5.8,
  'P2O5_kg_t': 3.2,
  'K2O_kg_t': 9.3,
  'MgO_kg_t': 1.7,
  'C_kg_t': 142,
  'KeqN': 0.3,
  'KeqP2O5': 0.8,
  'KeqK2O': 1,
  'KeqMgO': 1,
  'source': 'IFCE'},
 {'nom': 'Compost de fumier équin',
  'N_kg_t': 6.8,
  'P2O5_kg_t': 4.3,
  'K2O_kg_t': 10.1,
  'MgO_kg_t': 2.8,
  'C_kg_t': 90,
  'KeqN': 0.2,
  'KeqP2O5': 0.7,
  'KeqK2O': 1,
  'KeqMgO': 1,
  'source': 'IFCE'},
 {'nom': 'Fumier de bovin pailleux',
  'N_kg_t': 4.7,
  'P2O5_kg_t': 2.3,
  'K2O_kg_t': 5.6,
  'MgO_kg_t': 1.7,
  'C_kg_t': 87,
  'KeqN': 0.3,
  'KeqP2O5': 0.8,
  'KeqK2O': 1,
  'KeqMgO': 1,
  'source': 'IFCE'},
 {'nom': 'Compost de fumier de bovin',
  'N_kg_t': 6.7,
  'P2O5_kg_t': 3.6,
  'K2O_kg_t': 10.8,
  'MgO_kg_t': 2,
  'C_kg_t': 82,
  'KeqN': 0.2,
  'KeqP2O5': 0.7,
  'KeqK2O': 1,
  'KeqMgO': 1,
  'source': 'IFCE'},
 {'nom': '9/5/0',
  'N_kg_t': 90,
  'P2O5_kg_t': 50,
  'K2O_kg_t': 0,
  'MgO_kg_t': None,
  'C_kg_t': None,
  'KeqN': 0.6,
  'KeqP2O5': 0.9,
  'KeqK2O': 1,
  'KeqMgO': 1,
  'source': 'Fabricant'},
 {'nom': '11/9/0',
  'N_kg_t': 110,
  'P2O5_kg_t': 90,
  'K2O_kg_t': 0,
  'MgO_kg_t': None,
  'C_kg_t': None,
  'KeqN': 0.6,
  'KeqP2O5': 0.9,
  'KeqK2O': 1,
  'KeqMgO': 1,
  'source': 'Fabricant'},
 {'nom': 'Patenkali',
  'N_kg_t': None,
  'P2O5_kg_t': None,
  'K2O_kg_t': 300,
  'MgO_kg_t': 100,
  'C_kg_t': None,
  'KeqN': None,
  'KeqP2O5': None,
  'KeqK2O': 1,
  'KeqMgO': 1,
  'source': 'Fabricant'},
 {'nom': '4/4/3',
  'N_kg_t': 40,
  'P2O5_kg_t': 40,
  'K2O_kg_t': 30,
  'MgO_kg_t': None,
  'C_kg_t': None,
  'KeqN': 0.6,
  'KeqP2O5': 0.9,
  'KeqK2O': 1,
  'KeqMgO': 1,
  'source': 'Fabricant'}]

TENEURS_N_RECOLTE = [{'espece': 'Artichaut violet',
  'organe': 'tête',
  'dest': 'F',
  'teneur_kg_tMF': 3.7,
  'unite': 'kg / t MF',
  'rendement_moyen_t_ha': '4.2-6.4'},
 {'espece': 'Artichaut globuleux tête',
  'organe': None,
  'dest': 'F',
  'teneur_kg_tMF': 4.5,
  'unite': 'kg / t MF',
  'rendement_moyen_t_ha': '7-10'},
 {'espece': 'Asperge turion',
  'organe': None,
  'dest': 'F',
  'teneur_kg_tMF': 4,
  'unite': 'kg / t MF',
  'rendement_moyen_t_ha': '3-8'},
 {'espece': 'Aubergine',
  'organe': 'résidus de culture',
  'dest': 'F',
  'teneur_kg_tMF': 3,
  'unite': 'kg / t MF',
  'rendement_moyen_t_ha': '48'},
 {'espece': 'Aubergine',
  'organe': 'fruit',
  'dest': 'F',
  'teneur_kg_tMF': 1.4,
  'unite': 'kg / t MF',
  'rendement_moyen_t_ha': '100-130'},
 {'espece': 'Brocoli',
  'organe': 'tête 17 cm',
  'dest': 'F',
  'teneur_kg_tMF': 4.5,
  'unite': 'kg / t MF',
  'rendement_moyen_t_ha': '11'},
 {'espece': 'Brocoli',
  'organe': 'tête',
  'dest': 'I',
  'teneur_kg_tMF': 4,
  'unite': 'kg / t MF',
  'rendement_moyen_t_ha': '10-20'},
 {'espece': 'Carotte',
  'organe': 'fanes',
  'dest': 'F',
  'teneur_kg_tMF': 2.3,
  'unite': 'kg / t MF',
  'rendement_moyen_t_ha': '13-16'},
 {'espece': 'Carotte',
  'organe': 'racine',
  'dest': 'F',
  'teneur_kg_tMF': 1.2,
  'unite': 'kg / t MF',
  'rendement_moyen_t_ha': '60-65'},
 {'espece': 'Carotte jeune "Amsterdam"',
  'organe': 'racine',
  'dest': 'I',
  'teneur_kg_tMF': 1.1,
  'unite': 'kg / t MF',
  'rendement_moyen_t_ha': '35-45'},
 {'espece': 'Carotte grosse "Flakkee"',
  'organe': 'racine',
  'dest': 'I',
  'teneur_kg_tMF': 1.7,
  'unite': 'kg / t MF',
  'rendement_moyen_t_ha': '75-85'},
 {'espece': 'Céleri branche',
  'organe': 'paré 22 cm',
  'dest': 'I',
  'teneur_kg_tMF': 1.1,
  'unite': 'kg / t MF',
  'rendement_moyen_t_ha': '55-75'},
 {'espece': 'Céleri branche',
  'organe': 'paré 28 cm',
  'dest': 'I',
  'teneur_kg_tMF': 1.3,
  'unite': 'kg / t MF',
  'rendement_moyen_t_ha': '80-90'},
 {'espece': 'Céleri rave',
  'organe': 'racine',
  'dest': 'F',
  'teneur_kg_tMF': 2,
  'unite': 'kg / t MF',
  'rendement_moyen_t_ha': '50-58'},
 {'espece': 'Chicorées, Frisées, Scaroles',
  'organe': 'feuilles',
  'dest': 'F',
  'teneur_kg_tMF': 3.3,
  'unite': 'kg / t MF',
  'rendement_moyen_t_ha': '35'},
 {'espece': 'Chioggia',
  'organe': 'feuilles',
  'dest': 'F',
  'teneur_kg_tMF': 2.2,
  'unite': 'kg / t MF',
  'rendement_moyen_t_ha': '32'},
 {'espece': "Chou-fleur d'hiver",
  'organe': 'tête',
  'dest': 'F',
  'teneur_kg_tMF': 4.3,
  'unite': 'kg / t MF',
  'rendement_moyen_t_ha': '18-23'},
 {'espece': "Chou-fleur d'été et d'automne",
  'organe': 'tête',
  'dest': 'F',
  'teneur_kg_tMF': 2.5,
  'unite': 'kg / t MF',
  'rendement_moyen_t_ha': '30'},
 {'espece': 'Courgette',
  'organe': 'résidus de culture',
  'dest': 'F',
  'teneur_kg_tMF': 2.5,
  'unite': 'kg / t MF',
  'rendement_moyen_t_ha': '28'},
 {'espece': 'Courgette',
  'organe': 'fruit',
  'dest': 'F',
  'teneur_kg_tMF': 2.2,
  'unite': 'kg / t MF',
  'rendement_moyen_t_ha': '35'},
 {'espece': 'Echalote',
  'organe': 'bulbe',
  'dest': 'F',
  'teneur_kg_tMF': 2.3,
  'unite': 'kg / t MF',
  'rendement_moyen_t_ha': '40'},
 {'espece': 'Epinard',
  'organe': 'feuilles',
  'dest': 'I',
  'teneur_kg_tMF': 3.7,
  'unite': 'kg / t MF',
  'rendement_moyen_t_ha': '20-30'},
 {'espece': 'Fenouil',
  'organe': 'bulbe',
  'dest': 'F',
  'teneur_kg_tMF': 1.8,
  'unite': 'kg / t MF',
  'rendement_moyen_t_ha': '22'},
 {'espece': 'Haricot extra fin ou très fin',
  'organe': 'gousse',
  'dest': 'I',
  'teneur_kg_tMF': 3.4,
  'unite': 'kg / t MF',
  'rendement_moyen_t_ha': '10-15'},
 {'espece': 'Haricot flageolet',
  'organe': 'grain',
  'dest': 'I',
  'teneur_kg_tMF': 15,
  'unite': 'kg / t MF',
  'rendement_moyen_t_ha': '4.5-7'},
 {'espece': 'Laitue',
  'organe': 'tête',
  'dest': 'F',
  'teneur_kg_tMF': 1.8,
  'unite': 'kg / t MF',
  'rendement_moyen_t_ha': '50-60'},
 {'espece': 'Mâche',
  'organe': 'feuilles',
  'dest': 'F',
  'teneur_kg_tMF': 4.5,
  'unite': 'kg / t MF',
  'rendement_moyen_t_ha': '4 à 10'},
 {'espece': 'Melon',
  'organe': 'résidus de culture',
  'dest': 'F',
  'teneur_kg_tMF': 3.6,
  'unite': 'kg / t MF',
  'rendement_moyen_t_ha': '14'},
 {'espece': 'Melon',
  'organe': 'fruit',
  'dest': 'F',
  'teneur_kg_tMF': 1.4,
  'unite': 'kg / t MF',
  'rendement_moyen_t_ha': '20-50'},
 {'espece': 'Poireau',
  'organe': 'fût et feuilles',
  'dest': 'F',
  'teneur_kg_tMF': 3.3,
  'unite': 'kg / t MF',
  'rendement_moyen_t_ha': '50'},
 {'espece': 'Pois potager',
  'organe': 'grain',
  'dest': 'I',
  'teneur_kg_tMF': 9.8,
  'unite': 'kg / t MF',
  'rendement_moyen_t_ha': '6.5'},
 {'espece': 'Poivron',
  'organe': 'résidus de culture',
  'dest': 'F',
  'teneur_kg_tMF': 2.7,
  'unite': 'kg / t MF',
  'rendement_moyen_t_ha': '35'},
 {'espece': 'Poivron',
  'organe': 'fruit',
  'dest': 'F',
  'teneur_kg_tMF': 1.4,
  'unite': 'kg / t MF',
  'rendement_moyen_t_ha': '104'},
 {'espece': 'Pomme de terre primeur',
  'organe': 'fanes',
  'dest': 'F',
  'teneur_kg_tMF': 2.6,
  'unite': 'kg / t MF',
  'rendement_moyen_t_ha': '12-15'},
 {'espece': 'Pomme de terre primeur',
  'organe': 'tubercule',
  'dest': 'F',
  'teneur_kg_tMF': 2.8,
  'unite': 'kg / t MF',
  'rendement_moyen_t_ha': '30-40'},
 {'espece': 'Scorsonère',
  'organe': 'racine',
  'dest': 'I',
  'teneur_kg_tMF': 4.9,
  'unite': 'kg / t MF',
  'rendement_moyen_t_ha': '20-30'},
 {'espece': 'Tomate',
  'organe': 'résidus de culture',
  'dest': 'F',
  'teneur_kg_tMF': 3,
  'unite': 'kg / t MF',
  'rendement_moyen_t_ha': '65'},
 {'espece': 'Tomate',
  'organe': 'fruit',
  'dest': 'F',
  'teneur_kg_tMF': 1.5,
  'unite': 'kg / t MF',
  'rendement_moyen_t_ha': '175'},
 {'espece': 'Houblon',
  'organe': 'fruits (cones)',
  'dest': 'I',
  'teneur_kg_tMF': 30,
  'unite': 'kg / t MF',
  'rendement_moyen_t_ha': '1,8'},
 {'espece': 'Houblon',
  'organe': 'résidus de culture',
  'dest': 'I',
  'teneur_kg_tMF': 49.8,
  'unite': 'kg / t MF',
  'rendement_moyen_t_ha': None}]

TENEURS_PK_RECOLTE = [{'espece': 'Asperge',
  'organe': 'bourgeons',
  'dest': 'I&F',
  'P2O5_kg_tMF': 1.3,
  'K2O_kg_tMF': 3.7,
  'MgO_kg_tMF': 0.2},
 {'espece': 'Artichaut',
  'organe': 'têtes',
  'dest': 'F',
  'P2O5_kg_tMF': 1.3,
  'K2O_kg_tMF': 5.75,
  'MgO_kg_tMF': 0.5},
 {'espece': 'Brocoli',
  'organe': 'tête 18cm',
  'dest': 'I',
  'P2O5_kg_tMF': 1.4,
  'K2O_kg_tMF': 3.95,
  'MgO_kg_tMF': 0.22},
 {'espece': 'Carotte jeune "Amsterdam"',
  'organe': 'racine',
  'dest': 'I',
  'P2O5_kg_tMF': 0.6,
  'K2O_kg_tMF': 3.85,
  'MgO_kg_tMF': 0.3},
 {'espece': 'Carotte grosse',
  'organe': 'racine',
  'dest': 'I',
  'P2O5_kg_tMF': 1,
  'K2O_kg_tMF': 5.5,
  'MgO_kg_tMF': 0.23},
 {'espece': 'Chou de Bruxelles',
  'organe': 'plante entière',
  'dest': 'F',
  'P2O5_kg_tMF': 2,
  'K2O_kg_tMF': 3.7,
  'MgO_kg_tMF': 0.3},
 {'espece': 'Chou fleur automne',
  'organe': 'tête',
  'dest': 'I',
  'P2O5_kg_tMF': 1,
  'K2O_kg_tMF': 3.3,
  'MgO_kg_tMF': 0.2},
 {'espece': 'Chou fleur automne',
  'organe': 'tête couronnée',
  'dest': 'F',
  'P2O5_kg_tMF': 1,
  'K2O_kg_tMF': 4,
  'MgO_kg_tMF': 0.2},
 {'espece': 'Chou fleur hiver',
  'organe': 'tête',
  'dest': 'I',
  'P2O5_kg_tMF': 1.3,
  'K2O_kg_tMF': 4.3,
  'MgO_kg_tMF': 0.2},
 {'espece': 'Chou fleur hiver',
  'organe': 'tête couronnée',
  'dest': 'F',
  'P2O5_kg_tMF': 1.2,
  'K2O_kg_tMF': 4,
  'MgO_kg_tMF': 0.2},
 {'espece': 'Chou pomme',
  'organe': 'tête',
  'dest': 'F',
  'P2O5_kg_tMF': 1.3,
  'K2O_kg_tMF': 4.3,
  'MgO_kg_tMF': 0.25},
 {'espece': 'Courgette',
  'organe': 'fruit',
  'dest': 'F',
  'P2O5_kg_tMF': 0.65,
  'K2O_kg_tMF': 2.1,
  'MgO_kg_tMF': 0.3},
 {'espece': 'Épinard',
  'organe': 'feuilles',
  'dest': 'I',
  'P2O5_kg_tMF': 1.1,
  'K2O_kg_tMF': 7.05,
  'MgO_kg_tMF': 0.65},
 {'espece': 'Haricot vert',
  'organe': 'gousse',
  'dest': 'I',
  'P2O5_kg_tMF': 1.05,
  'K2O_kg_tMF': 3.65,
  'MgO_kg_tMF': 0.45},
 {'espece': 'Haricot flageolet',
  'organe': 'grain',
  'dest': 'I',
  'P2O5_kg_tMF': 4.55,
  'K2O_kg_tMF': 9.4,
  'MgO_kg_tMF': 1.25},
 {'espece': 'Haricot',
  'organe': 'paille',
  'dest': 'I',
  'P2O5_kg_tMF': 2.6,
  'K2O_kg_tMF': 24.1,
  'MgO_kg_tMF': 3.95},
 {'espece': 'Maïs doux',
  'organe': 'épi',
  'dest': 'I',
  'P2O5_kg_tMF': 2.15,
  'K2O_kg_tMF': 3.4,
  'MgO_kg_tMF': 0.55},
 {'espece': 'Melon',
  'organe': 'fruit',
  'dest': 'F',
  'P2O5_kg_tMF': 0.9,
  'K2O_kg_tMF': 4.45,
  'MgO_kg_tMF': 0.45},
 {'espece': 'Navet',
  'organe': 'racine',
  'dest': 'F',
  'P2O5_kg_tMF': 0.7,
  'K2O_kg_tMF': 3.9,
  'MgO_kg_tMF': 0.23},
 {'espece': "Poireau d'hiver",
  'organe': 'fût & feuilles',
  'dest': 'F',
  'P2O5_kg_tMF': 0.8,
  'K2O_kg_tMF': 4.2,
  'MgO_kg_tMF': 0.2},
 {'espece': 'Pois de conserve',
  'organe': 'grainventilé',
  'dest': 'I',
  'P2O5_kg_tMF': 2.95,
  'K2O_kg_tMF': 4,
  'MgO_kg_tMF': 0.7},
 {'espece': 'Pomme de terre ½ primeur',
  'organe': 'tubercule',
  'dest': 'F',
  'P2O5_kg_tMF': 1,
  'K2O_kg_tMF': 7.2,
  'MgO_kg_tMF': 0.4},
 {'espece': "Pomme de terre prim'primeur",
  'organe': 'tubercule',
  'dest': 'F',
  'P2O5_kg_tMF': 0.75,
  'K2O_kg_tMF': 4.5,
  'MgO_kg_tMF': 0.3},
 {'espece': 'Tomate',
  'organe': 'fruit',
  'dest': 'F',
  'P2O5_kg_tMF': 0.5,
  'K2O_kg_tMF': 2.9,
  'MgO_kg_tMF': 0.2},
 {'espece': 'Salade type laitue',
  'organe': 'feuilles',
  'dest': 'F',
  'P2O5_kg_tMF': 0.55,
  'K2O_kg_tMF': 3.5,
  'MgO_kg_tMF': 0.18}]


# ====================================================================
# 3. MOTEUR DE CALCUL — Onglet Excel "Analyse de Sol"
#    (chaque formule reprend exactement la cellule Excel d'origine,
#    rappelée en commentaire "Excel: <cellule> = <formule>")
# ====================================================================


def poids_terre_fine(profondeur_cm, densite_t_m3, pierrosite_pct):
    """Excel: D18 = D16*D15*(100-D17)  -> poids de terre fine (T/ha)."""
    return densite_t_m3 * profondeur_cm * (100 - pierrosite_pct)


def ph_minimal_ete(ph_hiver, ecart=0.7):
    """Excel: D45 = D41-0.7 (écart hivers/été forfaitaire du classeur).
    Le paramètre ``ecart`` peut être affiné avec ECART_PH_SAISONNIER_PAR_CEC
    (tableau 5.5, plus précis selon la CEC réelle du sol)."""
    return ph_hiver - ecart


def ecart_ph_pour_cec(cec):
    """Renvoie (libellé classe, écart hiver-été) le plus représentatif pour
    une CEC donnée, d'après le tableau 5.5 (onglet Aide)."""
    if cec is None:
        return None
    for libelle, seuil_max, ecart in ECART_PH_SAISONNIER_PAR_CEC:
        if cec < seuil_max:
            return libelle, ecart
    return ECART_PH_SAISONNIER_PAR_CEC[-1][0], ECART_PH_SAISONNIER_PAR_CEC[-1][2]


def element_kg_ha(poids_terre_fine_t_ha, teneur_ppm):
    """Excel: D52/D53/D54 = $D$18*D49/1000 -> conversion ppm -> kg/ha."""
    if teneur_ppm is None:
        return None
    return poids_terre_fine_t_ha * teneur_ppm / 1000


def seuils_positionnement(trenf, timp):
    """Excel: D56..D61 (P2O5) et D63..D68 (K2O) -> échelle de positionnement
    Trenf / Timp-10% / Timp / Timp+10% / 2xTimp / 3xTimp."""
    return {
        "Trenf": trenf,
        "Timp -10%": timp * 0.9,
        "Timp": timp,
        "Timp +10%": timp * 1.1,
        "2 x Timp": 2 * timp,
        "3 x Timp": 3 * timp,
    }


def categorie_teneur(valeur_ppm, trenf, timp):
    """Situe une teneur mesurée (ppm) sur l'échelle Trenf/Timp du classeur."""
    if valeur_ppm is None or trenf is None or timp is None:
        return None
    if valeur_ppm < trenf:
        return "< Trenf (renforcement nécessaire)"
    if valeur_ppm < timp * 0.9:
        return "Trenf – Timp -10 %"
    if valeur_ppm < timp:
        return "Timp -10 % – Timp"
    if valeur_ppm < timp * 1.1:
        return "Timp – Timp +10 % (impasse possible)"
    if valeur_ppm < 2 * timp:
        return "Timp +10 % – 2 x Timp"
    if valeur_ppm < 3 * timp:
        return "2 x Timp – 3 x Timp"
    return "> 3 x Timp (excès)"


def seuils_mo_argile(argile_pct):
    """Excel: D90/D91/D92 = 12/17/24 % x argile -> repères MO (%) selon le
    taux d'argile (structure du sol)."""
    if argile_pct is None:
        return None
    return {
        "Minimal (12 %)": 12 / 100 * argile_pct,
        "Raisonnable (17 %)": 17 / 100 * argile_pct,
        "Optimal (24 %)": 24 / 100 * argile_pct,
    }


def apport_amendement_mo(poids_terre_fine_t_ha, taux_mo_produit_pct, ismo_produit_pct):
    """Excel: D97 = D18*1/100/D95*100/D96*100
    Apport (T/ha) de produit pour augmenter la MO du sol d'1 point,
    compte tenu du taux de MO et de l'ISMO du produit choisi."""
    if not taux_mo_produit_pct or not ismo_produit_pct:
        return None
    return poids_terre_fine_t_ha * 1 / 100 / taux_mo_produit_pct * 100 / ismo_produit_pct * 100


def coefficient_k2(temperature_moy_c, argile_pct, caco3_pct):
    """Excel: D101 = 0.03*(1+0.2*(D100-10))*(1/(1+0.005*D26*10))*(1/(1+0.0015*D43*10))*100
    Coefficient de minéralisation annuelle de la MO/du carbone K2
    (Girard et al., 2011), en %."""
    return (0.03 * (1 + 0.2 * (temperature_moy_c - 10))
            * (1 / (1 + 0.005 * argile_pct * 10))
            * (1 / (1 + 0.0015 * caco3_pct * 10))
            * 100)


def perte_humus_annuelle(poids_terre_fine_t_ha, mo_pct, k2_pct):
    """Excel: D104 = D18*D83/100*1000*D101/100 -> perte d'humus (kg N/ha/an)."""
    return poids_terre_fine_t_ha * mo_pct / 100 * 1000 * k2_pct / 100


def apport_compensation_perte_humus(perte_humus_kg_ha_an, taux_mo_produit_pct, ismo_produit_pct):
    """Excel: D107 = D104/1000/D106*100/D105*100 -> apport (T/ha) pour
    compenser la perte annuelle d'humus."""
    if not taux_mo_produit_pct or not ismo_produit_pct:
        return None
    return perte_humus_kg_ha_an / 1000 / ismo_produit_pct * 100 / taux_mo_produit_pct * 100


def indice_battance(argile_pct, limons_fins_pct, limons_grossiers_pct, mo_pct, ph_eau):
    """Excel: D109 = (1.5*D27+0.75*D28)/(D26+10*D83)  [si pH<7]
              D110 = D109-0.2*(D41-7)                  [si pH>7]
    IB < 1,4 : non battant / 1,4-1,6 : peu battant / 1,6-1,8 : battant /
    > 1,8 : très battant."""
    ib = (1.5 * limons_fins_pct + 0.75 * limons_grossiers_pct) / (argile_pct + 10 * mo_pct)
    if ph_eau is not None and ph_eau > 7:
        ib = ib - 0.2 * (ph_eau - 7)
    return ib


def categorie_battance(ib):
    if ib is None:
        return None
    if ib < 1.4:
        return "Sol non battant"
    if ib < 1.6:
        return "Sol peu battant"
    if ib < 1.8:
        return "Sol battant"
    return "Sol très battant"


def beb_option_ph(argile_pct, mo_pct, ph_actuel, ph_souhaite):
    """Excel: D117 = 0.22*(D26*10+5*D83*10)*(EXP(D116/1.5)-EXP(D41/1.5))
    Besoin en base (t/ha) calculé via le pH."""
    return 0.22 * (argile_pct * 10 + 5 * mo_pct * 10) * (math.exp(ph_souhaite / 1.5) - math.exp(ph_actuel / 1.5))


def beb_option_caco3(poids_terre_fine_t_ha, caco3_pct_actuel, caco3_g_kg_souhaite):
    """Excel: D120 = D18*(D119-D43*10)/1000
    Besoin en base (t/ha) calculé via le stock de CaCO3."""
    return poids_terre_fine_t_ha * (caco3_g_kg_souhaite - caco3_pct_actuel * 10) / 1000


def strategie_chaulage(ib, caco3_g_kg, ph_eau, ca_echangeable_g_kg=None):
    """Grille de décision "Stratégie d'apport" (Tableau 10.5, onglet Aide).
    Renvoie un texte de préconisation. ``ca_echangeable_g_kg`` est optionnel :
    si absent, seule la branche pH/CaCO3 est évaluée (option Ca échangeable
    non disponible dans l'analyse de sol de base)."""
    if ib is None:
        return None
    if ib < 1.4:
        classe = "Faible (IB < 1,4)"
        seuil_ph = 7
    elif ib < 1.8:
        classe = "Moyen (1,4 < IB < 1,8)"
        seuil_ph = 7.3
    else:
        classe = "Élevé (IB > 1,8)"
        seuil_ph = 7.5

    caco3_bas = caco3_g_kg is not None and caco3_g_kg < 3
    if ib < 1.4:
        if ph_eau is not None and ph_eau < 7:
            reco = "Apport pour ramener le pH au-dessus de 7. Calcul avec l'option 1 (via pH)."
        else:
            reco = ("Prévoir un apport avant les prochaines cultures exigeantes en Ca "
                    "(entretien) si Ca échangeable < 6,7 g CaO/kg, sinon RAS.")
    else:
        if ph_eau is not None and ph_eau < seuil_ph:
            if caco3_bas:
                reco = ("Redressement = maximum de l'option 1 (via pH) ou de l'option 2 "
                        "(via CaCO3).")
            else:
                reco = f"Ramener le pH au-dessus de {seuil_ph}. Redressement avec l'option 1 (via pH)."
        else:
            if caco3_bas:
                reco = "Remonter le CaCO3 à 3 g/kg. Redressement avec l'option 2 (via CaCO3)."
            else:
                reco = ("Prévoir un apport avant les prochaines cultures exigeantes en Ca "
                        "(entretien) si Ca échangeable < 6,7 g CaO/kg, sinon RAS.")
    return f"Battance : {classe}. {reco}"


def km_jour_standard(argile_pct, caco3_pct):
    """Excel: D125 = 22750/((110+D26*10)*(600+D43*10))
    Taux de minéralisation journalier théorique de l'azote humifié (‰),
    modèle COMIFER (dépend de l'argile et du CaCO3, pas du C/N)."""
    return 22750 / ((110 + argile_pct * 10) * (600 + caco3_pct * 10))


def km_jour_mesure(km_28_28j):
    """Excel: D129 = EXP(0.115*(28-15))*28 ; D130 = D128/D129
    Taux de minéralisation journalier mesuré (‰), si analyse biologique de
    la minéralisation de l'azote (Km à 28°C/28 jours) disponible."""
    jn_28_28 = math.exp(0.115 * (28 - 15)) * 28
    return km_28_28j / jn_28_28, jn_28_28


MOIS = ["Janvier", "Février", "Mars", "Avril", "Mai", "Juin", "Juillet",
        "Août", "Septembre", "Octobre", "Novembre", "Décembre"]
NB_JOURS_MOIS_DEFAUT = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
TEMPERATURE_MOY_DEFAUT = [4.7, 5.7, 8.1, 11.0, 14.3, 18.7, 20.8, 20.1, 17.1, 13.3, 8.3, 5.9]
HUMIDITE_MOY_DEFAUT = [100, 100, 90, 80, 70, 60, 60, 60, 70, 80, 90, 100]


def mineralisation_humus_mensuelle(azote_total_kg_ha, km_jour_pct0, nb_jours=None,
                                    temperatures=None, humidites=None):
    """Excel: lignes 136 à 144 de l'onglet "Analyse de Sol".
    Calcule, pour chacun des 12 mois :
      f(Tmoy) = EXP(0.115*(Tmoy-15)) * nb_jours     -- fonction température
      g(H)    = (20 + 80*Humidité/100) / 100        -- fonction humidité
      JN mensuel = f(Tmoy) * g(H)                   -- jours normalisés
      Km mensuel = Km_jour_standard * JN mensuel
      Mh (kg N/ha) = azote_total_kg_ha/1000 * Km_mensuel
      Mh cumulé
    Renvoie une liste de 12 dict (un par mois)."""
    nb_jours = nb_jours or NB_JOURS_MOIS_DEFAUT
    temperatures = temperatures or TEMPERATURE_MOY_DEFAUT
    humidites = humidites or HUMIDITE_MOY_DEFAUT

    resultats = []
    cumul = 0.0
    for i, mois in enumerate(MOIS):
        f_temp = math.exp(0.115 * (temperatures[i] - 15)) * nb_jours[i]
        g_hum = (20 + 80 * humidites[i] / 100) / 100
        jn = f_temp * g_hum
        km_mensuel = km_jour_pct0 * jn
        mh = azote_total_kg_ha / 1000 * km_mensuel
        cumul += mh
        resultats.append({
            "mois": mois, "nb_jours": nb_jours[i], "temperature": temperatures[i],
            "humidite": humidites[i], "f_temp": f_temp, "g_hum": g_hum, "jn": jn,
            "km_mensuel": km_mensuel, "mh": mh, "mh_cumule": cumul,
        })
    return resultats


def analyser_parcelle(donnees):
    """Reproduit intégralement l'onglet Excel "Analyse de Sol" à partir d'un
    dictionnaire d'entrées ``donnees`` (mêmes clés que les champs saisis en
    colonne D du classeur). Les clés absentes ou None sont simplement
    ignorées (le résultat correspondant reste None). Renvoie un dict de
    résultats structuré par section."""
    g = donnees.get
    res = {}

    # --- Poids de terre fine ---
    profondeur = g("profondeur_cm")
    densite = g("densite_t_m3")
    pierrosite = g("pierrosite_pct")
    ptf = None
    if profondeur is not None and densite is not None and pierrosite is not None:
        ptf = poids_terre_fine(profondeur, densite, pierrosite)
    res["poids_terre_fine_t_ha"] = ptf

    # --- CEC ---
    res["cec"] = g("cec")

    # --- Granulométrie / seuils P2O5-K2O ---
    argile = g("argile_pct")
    limons_fins = g("limons_fins_pct")
    limons_grossiers = g("limons_grossiers_pct")
    res["granulometrie"] = {
        "argile_pct": argile, "limons_fins_pct": limons_fins,
        "limons_grossiers_pct": limons_grossiers,
        "sables_fins_pct": g("sables_fins_pct"), "sables_grossiers_pct": g("sables_grossiers_pct"),
        "type_sol": g("type_sol"),
    }

    trenf_p, timp_p = g("trenf_p2o5"), g("timp_p2o5")
    trenf_k, timp_k = g("trenf_k2o"), g("timp_k2o")
    res["seuils_p2o5"] = seuils_positionnement(trenf_p, timp_p) if (trenf_p and timp_p) else None
    res["seuils_k2o"] = seuils_positionnement(trenf_k, timp_k) if (trenf_k and timp_k) else None

    # --- Analyse chimique : pH ---
    ph_hiver = g("ph_eau")
    res["ph_eau"] = ph_hiver
    res["ph_kcl"] = g("ph_kcl")
    res["caco3_pct"] = g("caco3_pct")
    res["cao_ppm"] = g("cao_ppm")
    ecart_pref = ecart_ph_pour_cec(g("cec")) if g("cec") is not None else None
    res["ecart_ph_saisonnier_recommande"] = ecart_pref
    if ph_hiver is not None:
        res["ph_minimal_ete_excel"] = ph_minimal_ete(ph_hiver, 0.7)
        if ecart_pref is not None:
            res["ph_minimal_ete_affine"] = ph_minimal_ete(ph_hiver, ecart_pref[1])

    # --- Éléments majeurs ---
    p2o5_ppm, k2o_ppm, mgo_ppm = g("p2o5_ppm"), g("k2o_ppm"), g("mgo_ppm")
    if ptf is not None:
        res["p2o5_kg_ha"] = element_kg_ha(ptf, p2o5_ppm)
        res["k2o_kg_ha"] = element_kg_ha(ptf, k2o_ppm)
        res["mgo_kg_ha"] = element_kg_ha(ptf, mgo_ppm)
    res["p2o5_ppm"], res["k2o_ppm"], res["mgo_ppm"] = p2o5_ppm, k2o_ppm, mgo_ppm
    res["categorie_p2o5"] = categorie_teneur(p2o5_ppm, trenf_p, timp_p)
    res["categorie_k2o"] = categorie_teneur(k2o_ppm, trenf_k, timp_k)

    # --- Oligo-éléments ---
    res["oligoelements"] = {
        "Zn (Zinc)": g("zn_ppm"), "Mn (Manganèse)": g("mn_ppm"), "Cu (Cuivre)": g("cu_ppm"),
        "Fe (Fer)": g("fe_ppm"), "B (Bore)": g("b_ppm"),
    }

    # --- MO, C/N, Bilan humique ---
    mo_pct = g("mo_pct")
    carbone_pct = g("carbone_pct")
    azote_total_pct = g("azote_total_pct")
    res["mo_pct"] = mo_pct
    res["carbone_pct"] = carbone_pct
    res["azote_total_pct"] = azote_total_pct
    res["c_n"] = g("c_n")

    azote_total_kg_ha = None
    if ptf is not None and azote_total_pct is not None:
        azote_total_kg_ha = ptf * 1000 * azote_total_pct / 100
    res["azote_total_kg_ha"] = azote_total_kg_ha

    if argile is not None:
        res["seuils_mo_argile"] = seuils_mo_argile(argile)

    taux_mo_produit = g("taux_mo_produit_pct", 25.0)
    ismo_produit = g("ismo_produit_pct", 80.0)
    if ptf is not None:
        res["apport_mo_plus1point_t_ha"] = apport_amendement_mo(ptf, taux_mo_produit, ismo_produit)

    k2 = None
    if g("temperature_moy_c") is not None and argile is not None and res.get("caco3_pct") is not None:
        k2 = coefficient_k2(g("temperature_moy_c"), argile, res["caco3_pct"])
    res["k2_pct"] = k2

    perte_humus = None
    if ptf is not None and mo_pct is not None and k2 is not None:
        perte_humus = perte_humus_annuelle(ptf, mo_pct, k2)
        res["apport_compensation_perte_humus_t_ha"] = apport_compensation_perte_humus(
            perte_humus, taux_mo_produit, ismo_produit)
    res["perte_humus_kg_ha_an"] = perte_humus

    # --- Indice de battance ---
    ib = None
    if None not in (argile, limons_fins, limons_grossiers, mo_pct):
        ib = indice_battance(argile, limons_fins, limons_grossiers, mo_pct, ph_hiver)
    res["indice_battance"] = ib
    res["categorie_battance"] = categorie_battance(ib)

    # --- Chaulage / BEB ---
    ph_souhaite = g("ph_souhaite", 7.5)
    if None not in (argile, mo_pct, ph_hiver):
        res["beb_option_ph_t_ha"] = beb_option_ph(argile, mo_pct, ph_hiver, ph_souhaite)
    caco3_souhaite = g("caco3_souhaite_g_kg", 3.0)
    if ptf is not None and res.get("caco3_pct") is not None:
        res["beb_option_caco3_t_ha"] = beb_option_caco3(ptf, res["caco3_pct"], caco3_souhaite)
    res["strategie_chaulage"] = strategie_chaulage(
        ib, res.get("caco3_pct") * 10 if res.get("caco3_pct") is not None else None, ph_hiver)

    # --- Minéralisation de l'azote humifié (Km) ---
    km_standard = None
    if argile is not None and res.get("caco3_pct") is not None:
        km_standard = km_jour_standard(argile, res["caco3_pct"])
    res["km_jour_standard_pour_mille"] = km_standard

    km_28 = g("km_28_28j")
    if km_28 is not None:
        km_mesure, jn_28 = km_jour_mesure(km_28)
        res["km_jour_mesure_pour_mille"] = km_mesure

    km_retenu = km_28 is not None and res.get("km_jour_mesure_pour_mille") is not None
    km_valeur = res.get("km_jour_mesure_pour_mille") if km_retenu else km_standard
    if km_valeur is not None and azote_total_kg_ha is not None:
        res["mineralisation_mensuelle"] = mineralisation_humus_mensuelle(
            azote_total_kg_ha, km_valeur,
            nb_jours=g("nb_jours_mois"), temperatures=g("temperatures_mensuelles"),
            humidites=g("humidites_mensuelles"))

    return res

# ====================================================================
# 4. MOTEUR DE CALCUL — Bilans de fertilisation NPK/azotée
#    (onglets Excel "1 Bilan Simple", "2 Bilan Intermédiaire",
#    "3 Bilan Avancé"). Les 3 niveaux partagent la même table de besoins
#    NPK par culture (CULTURES_BILAN_AZOTE) et le même schéma de calcul de
#    dose, mais diffèrent par la prise en compte (ou non) des apports déjà
#    présents dans le sol (reliquats, minéralisation, résidus...).
# ====================================================================

FACTEUR_SURFACE_CLASSEUR = 1.5  # Excel: E67 = $D$67*1.5 (coefficient du classeur, conservé tel quel)


def rechercher_cultures_bilan(texte):
    """Recherche insensible à la casse dans la table CULTURES_BILAN_AZOTE
    (espèce ou famille). Renvoie la liste des entrées correspondantes."""
    if not texte:
        return list(CULTURES_BILAN_AZOTE)
    t = texte.strip().lower()
    return [c for c in CULTURES_BILAN_AZOTE
            if t in (c["espece"] or "").lower() or t in (c["famille"] or "").lower()]


def rechercher_dose_plafond_n(texte):
    """Recherche insensible à la casse dans la table DOSE_PLAFOND_N
    (arrêté IDF, plafond réglementaire d'azote pour légumes)."""
    if not texte:
        return list(DOSE_PLAFOND_N)
    t = texte.strip().lower()
    return [p for p in DOSE_PLAFOND_N
            if t in (p["legume"] or "").lower() or t in (p["variante"] or "").lower()]


def _dose_produit(npk_a_apporter_kg_ha, surface_m2, produit_pct,
                   facteur_surface=FACTEUR_SURFACE_CLASSEUR):
    """Bloc de calcul commun aux 3 bilans, une fois le NPK net à apporter
    (kg/ha) déterminé : surface d'apport, dose du produit en T/ha et en kg
    sur la surface choisie.
    Excel (Bilan Simple, ex. E67 à E72) :
      surface_apport   = surface_m2 * 1.5
      NPK_kg_surface   = NPK_a_apporter/10000 * surface_apport
      dose_T_ha        = NPK_a_apporter/produit_pct*100/1000
      dose_kg_surface  = NPK_kg_surface/produit_pct*100
    """
    out = {}
    for nutriment, valeur in npk_a_apporter_kg_ha.items():
        pct = produit_pct.get(nutriment)
        surface_apport = surface_m2 * facteur_surface
        npk_kg_surface = valeur / 10000 * surface_apport
        dose_t_ha = (valeur / pct * 100 / 1000) if pct else None
        dose_kg_surface = (npk_kg_surface / pct * 100) if pct else None
        out[nutriment] = {
            "npk_a_apporter_kg_ha": valeur,
            "npk_a_apporter_kg_surface": npk_kg_surface,
            "dose_produit_t_ha": dose_t_ha,
            "dose_produit_kg_surface": dose_kg_surface,
        }
    return out


def bilan_simple(besoins_kg_ha, surface_m2, produit_pct):
    """Excel: "1 Bilan Simple". ``besoins_kg_ha`` = {"N":.., "P2O5":.., "K2O":..}
    (somme des besoins si plusieurs cultures). Pas de prise en compte des
    apports déjà présents dans le sol : NPK à apporter = besoin brut."""
    return _dose_produit(besoins_kg_ha, surface_m2, produit_pct)


def bilan_intermediaire(besoins_kg_ha, surface_m2, produit_pct,
                         coef_sol=None, reliquats_mineralisation=None, keq=None):
    """Excel: "2 Bilan Intermédiaire".
      besoin_avec_coef[N]  = besoin[N]                       (pas de coef sur N)
      besoin_avec_coef[X]  = besoin[X] * coef_sol[X]          (P2O5, K2O)
      NPK_a_apporter        = besoin_avec_coef - reliquats_mineralisation
    Un unique poste "Reliquats et minéralisation" représente ce que le sol
    fournit déjà (voir "3 Bilan Avancé" pour le détail). Le coefficient
    d'équivalence ``keq`` (optionnel) donne en plus la dose corrigée."""
    coef_sol = coef_sol or {}
    reliquats_mineralisation = reliquats_mineralisation or {}
    besoin_avec_coef = {}
    for nutriment, valeur in besoins_kg_ha.items():
        coef = 1.0 if nutriment == "N" else coef_sol.get(nutriment, 1.0)
        besoin_avec_coef[nutriment] = valeur * coef

    npk_a_apporter = {
        nutriment: valeur - reliquats_mineralisation.get(nutriment, 0.0)
        for nutriment, valeur in besoin_avec_coef.items()
    }
    resultat = _dose_produit(npk_a_apporter, surface_m2, produit_pct)
    if keq:
        for nutriment, bloc in resultat.items():
            k = keq.get(nutriment)
            if k and bloc["dose_produit_kg_surface"] is not None:
                bloc["dose_produit_kg_surface_avec_keq"] = bloc["dose_produit_kg_surface"] / k
    return resultat


def bilan_avance(besoins_kg_ha, surface_m2, produit_pct, coef_sol=None,
                  reliquats=None, pertes_lixiviation=None, mineralisation_humus=None,
                  residus=None, couverts=None, irrigation=None,
                  autres_apports_1=None, autres_apports_2=None, keq=None):
    """Excel: "3 Bilan Avancé".
      besoin_avec_coef = besoin * coef_sol (comme Intermédiaire, pas de coef sur N)
      NPK_a_apporter = besoin_avec_coef + pertes_lixiviation
                       - (reliquats + mineralisation_humus + residus + couverts
                          + irrigation + autres_apports_1 + autres_apports_2)
    Traduction du bilan de masse COMIFER : Rf - Ri = Entrées - Sorties, en
    isolant l'apport d'engrais/amendement encore nécessaire (X)."""
    coef_sol = coef_sol or {}

    def get(d, nutriment):
        return (d or {}).get(nutriment, 0.0)

    besoin_avec_coef = {}
    for nutriment, valeur in besoins_kg_ha.items():
        coef = 1.0 if nutriment == "N" else coef_sol.get(nutriment, 1.0)
        besoin_avec_coef[nutriment] = valeur * coef

    npk_a_apporter = {}
    for nutriment, besoin in besoin_avec_coef.items():
        sorties_evitees = (get(reliquats, nutriment) + get(mineralisation_humus, nutriment)
                            + get(residus, nutriment) + get(couverts, nutriment)
                            + get(irrigation, nutriment) + get(autres_apports_1, nutriment)
                            + get(autres_apports_2, nutriment))
        npk_a_apporter[nutriment] = besoin + get(pertes_lixiviation, nutriment) - sorties_evitees

    resultat = _dose_produit(npk_a_apporter, surface_m2, produit_pct)
    if keq:
        for nutriment, bloc in resultat.items():
            k = keq.get(nutriment)
            if k and bloc["dose_produit_kg_surface"] is not None:
                bloc["dose_produit_kg_surface_avec_keq"] = bloc["dose_produit_kg_surface"] / k
    return resultat


def apport_produit_secondaire(dose_kg_surface, surface_m2, produit_pct, keq,
                                facteur_surface=FACTEUR_SURFACE_CLASSEUR):
    """Excel: bloc "Apport n°2" du Bilan Avancé (E88 à E94).
    Calcule ce qu'apporte réellement, en NPK, une dose choisie (kg sur la
    surface) d'un second produit — pour compléter/recouper un premier
    apport ; le résultat est à reporter dans "Autres apports"."""
    out = {}
    for nutriment, dose in dose_kg_surface.items():
        pct = produit_pct.get(nutriment)
        k = keq.get(nutriment) if keq else None
        surface_apport = surface_m2 * facteur_surface
        dose_t_ha = dose * 10000 / surface_apport / 1000 if surface_apport else None
        npk_sans_keq = (dose_t_ha * pct / 100 * 1000) if (dose_t_ha is not None and pct) else None
        npk_avec_keq = (npk_sans_keq * k) if (npk_sans_keq is not None and k) else None
        out[nutriment] = {
            "dose_t_ha": dose_t_ha, "npk_kg_ha_sans_keq": npk_sans_keq,
            "npk_kg_ha_avec_keq": npk_avec_keq,
        }
    return out


def verifier_plafond_n(dose_n_kg_ha, legume, variante=None):
    """Compare une dose d'azote (kg/ha) à la dose plafond réglementaire
    (arrêté IDF) pour un légume donné. Renvoie (nmax, depassement_bool) ou
    (None, None) si le légume n'est pas trouvé."""
    correspondances = rechercher_dose_plafond_n(legume)
    if variante:
        correspondances = [c for c in correspondances
                            if variante.lower() in (c["variante"] or "").lower()] or correspondances
    if not correspondances:
        return None, None
    nmax = correspondances[0]["nmax"]
    if nmax is None:
        return None, None
    return nmax, dose_n_kg_ha > nmax


# --- Coefficients d'équivalence P (KeqP) par type de produit organique
# (onglet "NPK Engrais-amend", bas de page ; pour N, voir Azopro/GREN IDF/
# fournisseur — non tabulé nationalement dans le classeur).
KEQ_P_PAR_TYPE_PRODUIT = {
    "Lisiers et fumiers de porcs": 0.95,
    "Fumiers et viandes de volailles": 0.85,
    "Fumiers de bovins": 0.80,
    "Compost de fumiers de bovins": 0.70,
    "Compost de déchets verts": 0.55,
}
