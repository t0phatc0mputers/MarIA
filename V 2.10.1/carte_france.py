# -*- coding: utf-8 -*-
"""
carte_france.py
-----------------
Carte interactive (zoomable à la molette, comme le "Plan de la ferme") des
13 régions de France métropolitaine. Deux TYPES de carte sont proposés,
sélectionnables par l'utilisateur :

  - "Schématique (mailles)" : chaque région est une tuile hexagonale de
    même taille, disposée selon sa position géographique relative (carte
    "en mailles", technique classique de cartographie schématique
    française qui évite que les grandes régions rurales n'écrasent les
    petites régions densément peuplées) ;
  - "Géographique (contours réels)" : les vrais contours des régions,
    issus de données ouvertes (IGN / gregoiredavid/france-geojson),
    simplifiés pour rester légers à afficher.

Pour chacun des deux types de carte, deux indicateurs sont disponibles, au
choix, via un sélecteur :
  - le climat dominant de la région (classification simplifiée),
  - une qualité de sol indicative (type dominant + niveau de fertilité 1-5).

Ces données sont volontairement SCHÉMATIQUES ET À L'ÉCHELLE RÉGIONALE :
chaque région de France présente en réalité une grande diversité interne de
climats et de sols (ex. littoral vs. montagne en PACA, Beauce vs. Sologne en
Centre-Val de Loire...). En particulier, la couche "sol" n'est PAS une carte
géologique au sens strict (les formations géologiques ne suivent pas les
limites administratives) : il s'agit d'une appréciation indicative de la
fertilité dominante par région, faute de données géologiques (BRGM) locales
disponibles hors-ligne. Cette carte donne un premier repère ; pour une
décision agronomique réelle, on se reportera aux données locales (onglet
"Aide à la décision" pour la météo de la commune, onglet "Analyse de sol"
pour une analyse de sol réelle, et le cas échéant la carte géologique
officielle du BRGM - infoterre.brgm.fr).

Ce module est coupé en trois parties, comme plan_ferme.py :
  - données indicatives par région (climat, sol) + contours géographiques
    réels (coordonnées déjà projetées, pas de dépendance à un SIG) ;
  - géométrie pure (dicts, fonctions de calcul de position/couleur) ;
  - classes PyQt (QGraphicsPolygonItem / QGraphicsView) réutilisées par
    gestion_planning_agricole.py pour construire l'onglet "Carte régionale".
"""

import math

from PyQt5.QtCore import Qt, QPointF
from PyQt5.QtGui import QPolygonF, QBrush, QPen, QColor, QFont, QPainter
from PyQt5.QtWidgets import QGraphicsView, QGraphicsPolygonItem, QGraphicsSimpleTextItem


# ------------------------------------------------------------------
# Données indicatives par région
# ------------------------------------------------------------------
CLIMAT_COULEURS = {
    "Océanique franc": "#4fa8d8",
    "Océanique": "#6fb8e0",
    "Océanique dégradé / semi-continental": "#8fc6d8",
    "Semi-continental": "#f0c05a",
    "Montagnard": "#9aa6c9",
    "Méditerranéen": "#e0824a",
}

SOL_COULEURS_NIVEAU = {
    1: "#c98f5e",
    2: "#d3a86e",
    3: "#c7c26a",
    4: "#8fbf5a",
    5: "#4c9a4c",
}
SOL_LABELS_NIVEAU = {
    1: "Faible (sols superficiels / caillouteux)",
    2: "Moyen-faible (sableux / acide)",
    3: "Moyen (très variable selon le secteur)",
    4: "Bon (sols profonds, bien pourvus)",
    5: "Très bon (limons profonds, openfield)",
}

MODES = ["🌦 Climat", "🧪 Qualité du sol"]

TYPES_CARTE = ["🔷 Schématique (mailles)", "🗺️ Géographique (contours réels)"]

# row, col : position dans la grille en briques (offset "odd-r"), disposée
# pour évoquer la géographie de la France (Nord en haut, Corse en bas à
# droite). Cf. les cartes en mailles hexagonales des 13 régions.
REGIONS = {
    "Hauts-de-France": dict(
        row=0, col=2,
        climat="Océanique dégradé / semi-continental",
        climat_desc="Climat océanique dégradé, frais et humide ; étés doux ; "
                    "risque de gel tardif au printemps.",
        sol_type="Limons profonds (openfield)",
        sol_niveau=5,
        sol_desc="Sols limoneux profonds et fertiles, très favorables aux "
                 "grandes cultures ; bonne réserve utile en eau.",
    ),
    "Normandie": dict(
        row=1, col=1,
        climat="Océanique franc",
        climat_desc="Climat océanique franc, doux et humide toute l'année, "
                    "faible amplitude thermique.",
        sol_type="Limons et argiles herbagers",
        sol_niveau=4,
        sol_desc="Sols limono-argileux profonds, bien pourvus en matière "
                 "organique, adaptés à l'herbage et au maraîchage.",
    ),
    "Île-de-France": dict(
        row=1, col=2,
        climat="Océanique dégradé / semi-continental",
        climat_desc="Climat océanique dégradé, hivers doux, étés modérément "
                    "chauds, précipitations réparties toute l'année.",
        sol_type="Limons de plateau (Beauce, Brie)",
        sol_niveau=5,
        sol_desc="Limons profonds à très bonne réserve utile, parmi les "
                 "meilleurs sols agricoles français.",
    ),
    "Grand Est": dict(
        row=1, col=3,
        climat="Semi-continental",
        climat_desc="Climat semi-continental marqué, hivers froids, étés "
                    "chauds et orageux, gelées tardives possibles.",
        sol_type="Argilo-calcaires variés",
        sol_niveau=3,
        sol_desc="Sols hétérogènes, souvent argilo-calcaires, favorables à "
                 "la vigne et aux céréales selon les secteurs.",
    ),
    "Bretagne": dict(
        row=2, col=0,
        climat="Océanique franc",
        climat_desc="Climat océanique franc et humide, hivers très doux, "
                    "étés frais, faibles écarts de température.",
        sol_type="Sols acides sur socle granitique/schisteux",
        sol_niveau=3,
        sol_desc="Sols souvent acides et peu profonds, drainage à "
                 "surveiller ; chaulage fréquemment nécessaire.",
    ),
    "Pays de la Loire": dict(
        row=2, col=1,
        climat="Océanique",
        climat_desc="Climat océanique doux, moins pluvieux que la Bretagne, "
                    "bonne luminosité.",
        sol_type="Sols variés, vallées fertiles",
        sol_niveau=4,
        sol_desc="Sols profonds et fertiles dans les vallées (Loire, Maine), "
                 "plus sableux et acides vers l'intérieur des terres.",
    ),
    "Centre-Val de Loire": dict(
        row=2, col=2,
        climat="Océanique dégradé / semi-continental",
        climat_desc="Climat de transition, océanique dégradé, étés assez "
                    "chauds et secs.",
        sol_type="Limons de Beauce / sables de Sologne",
        sol_niveau=3,
        sol_desc="Sols très fertiles en Beauce (limons profonds), plus "
                 "pauvres et sableux en Sologne.",
    ),
    "Bourgogne-Franche-Comté": dict(
        row=2, col=3,
        climat="Semi-continental",
        climat_desc="Climat semi-continental contrasté, hivers froids, étés "
                    "chauds, influence montagnarde à l'est (Jura).",
        sol_type="Argilo-calcaires",
        sol_niveau=3,
        sol_desc="Sols argilo-calcaires typiques, réputés pour la vigne, "
                 "profondeur variable.",
    ),
    "Nouvelle-Aquitaine": dict(
        row=3, col=1,
        climat="Océanique",
        climat_desc="Climat océanique aquitain, doux, étés chauds et "
                    "ensoleillés, hivers doux.",
        sol_type="Sables des Landes à argilo-calcaires",
        sol_niveau=3,
        sol_desc="Grande diversité : sables pauvres des Landes, boulbènes "
                 "limoneuses, argilo-calcaires du Bordelais.",
    ),
    "Auvergne-Rhône-Alpes": dict(
        row=3, col=2,
        climat="Montagnard",
        climat_desc="Climat très contrasté selon l'altitude : semi-"
                    "continental en plaine, montagnard en zone alpine.",
        sol_type="Sols volcaniques et sols de montagne",
        sol_niveau=3,
        sol_desc="Sols volcaniques fertiles en Limagne, sols superficiels "
                 "et pauvres en altitude.",
    ),
    "Occitanie": dict(
        row=4, col=1,
        climat="Méditerranéen",
        climat_desc="Climat méditerranéen sur le littoral, océanique/"
                    "montagnard vers l'ouest et les Pyrénées.",
        sol_type="Argilo-calcaires et alluvions",
        sol_niveau=3,
        sol_desc="Sols contrastés : argilo-calcaires viticoles, alluvions "
                 "fertiles des vallées, garrigues caillouteuses.",
    ),
    "Provence-Alpes-Côte d'Azur": dict(
        row=4, col=2,
        climat="Méditerranéen",
        climat_desc="Climat méditerranéen typique, étés chauds et secs, "
                    "hivers doux, fort ensoleillement.",
        sol_type="Sols caillouteux peu profonds",
        sol_niveau=2,
        sol_desc="Sols souvent superficiels et caillouteux, irrigation "
                 "nécessaire en été, forte minéralité.",
    ),
    "Corse": dict(
        row=5, col=3,
        climat="Méditerranéen",
        climat_desc="Climat méditerranéen insulaire, doux, sécheresse "
                    "estivale marquée sur le littoral.",
        sol_type="Granites et schistes",
        sol_niveau=2,
        sol_desc="Sols acides, peu profonds en montagne ; plaines "
                 "alluviales plus fertiles (Aléria).",
    ),
}

# ------------------------------------------------------------------
# Contours géographiques réels des régions (carte "géographique")
# ------------------------------------------------------------------
# Source : IGN, via le jeu de données ouvert
#   https://github.com/gregoiredavid/france-geojson (régions.geojson)
# Géométries simplifiées (tolérance de Douglas-Peucker ~0.035°, îlots de
# moins de 0.015° d'aire supprimés, 4 polygones les plus grands conservés
# par région) puis projetées en coordonnées planes simples (équirectangulaire
# corrigée par le cosinus de la latitude moyenne de la France, centrée sur
# 2.5°E / 46.6°N, échelle 110 unités/degré) afin de rester légères à
# afficher et de ne dépendre d'aucune bibliothèque SIG à l'exécution.
# Chaque région est une liste d'anneaux (le contiguë principal, puis
# d'éventuelles îles/parties disjointes), chaque anneau une liste de
# points (x, y).

CONTOURS_REGIONS = {
    'Île-de-France': [
        [(6.8,-272.8), (48.2,-275.8), (57.8,-257.3), (74.5,-247.7), (67.7,-237.5), (73.3,-235.2), (71.9,-223.8), (80.0,-221.9), (68.4,-212.1), (69.1,-196.9), (41.5,-193.6), (41.4,-181.5), (24.3,-168.3), (22.3,-172.6), (-4.2,-167.7), (1.4,-179.0), (-7.4,-189.3), (-19.3,-186.8), (-22.1,-191.9), (-25.4,-186.8), (-40.4,-186.5), (-38.6,-194.0), (-43.1,-204.3), (-52.8,-205.3), (-53.9,-214.9), (-67.8,-226.9), (-68.2,-246.3), (-79.6,-269.1), (-66.3,-273.5), (-59.8,-290.5), (-56.3,-283.2), (-14.3,-284.5), (6.8,-272.8)],
    ],
    'Centre-Val de Loire': [
        [(26.1,-103.9), (32.6,-92.3), (28.5,-79.4), (36.5,-72.7), (39.3,-51.5), (43.5,-47.2), (42.2,-24.9), (26.2,-14.0), (16.2,-15.9), (5.1,-5.9), (8.7,5.1), (-10.6,9.3), (-16.5,19.8), (-53.9,15.9), (-58.4,23.1), (-73.9,19.1), (-81.9,27.8), (-86.5,22.0), (-99.6,24.6), (-97.3,18.5), (-102.3,10.3), (-120.1,-0.2), (-119.9,-13.8), (-135.7,-33.4), (-136.6,-41.2), (-146.0,-44.7), (-143.6,-39.3), (-164.5,-36.5), (-165.9,-49.8), (-175.7,-50.7), (-175.1,-56.6), (-184.9,-61.7), (-183.0,-75.2), (-175.1,-85.9), (-171.4,-111.2), (-160.3,-106.5), (-160.0,-114.7), (-143.8,-118.0), (-145.0,-122.5), (-135.9,-128.4), (-130.4,-136.3), (-131.5,-142.9), (-124.8,-147.7), (-128.9,-161.7), (-119.7,-169.3), (-128.8,-174.7), (-128.0,-185.9), (-131.8,-187.0), (-115.1,-202.5), (-118.2,-206.3), (-115.8,-211.6), (-127.8,-227.1), (-104.7,-236.2), (-104.2,-240.8), (-88.4,-237.7), (-77.7,-257.4), (-68.2,-246.3), (-67.8,-226.9), (-53.9,-214.9), (-52.8,-205.3), (-43.1,-204.3), (-39.4,-198.2), (-39.9,-185.7), (-13.0,-190.6), (1.4,-179.0), (-4.2,-167.7), (22.3,-172.6), (22.8,-168.5), (40.0,-168.7), (47.5,-150.8), (38.5,-143.6), (39.7,-130.6), (26.6,-127.4), (36.0,-106.6), (26.1,-103.9)],
    ],
    'Bourgogne-Franche-Comté': [
        [(85.4,-16.4), (72.4,-5.7), (70.6,-12.3), (52.8,-8.7), (40.5,-19.4), (43.5,-47.2), (39.3,-51.5), (36.5,-72.7), (28.5,-79.4), (32.6,-92.3), (26.1,-103.9), (36.0,-106.6), (26.6,-127.4), (39.7,-130.6), (38.5,-143.6), (47.5,-150.8), (40.0,-168.7), (32.9,-172.3), (41.4,-181.5), (41.5,-193.6), (75.4,-194.7), (84.9,-182.5), (81.3,-174.8), (88.3,-169.3), (94.3,-172.3), (102.0,-152.2), (106.6,-152.0), (106.0,-145.8), (128.7,-151.0), (135.5,-145.8), (155.3,-150.4), (157.6,-157.3), (173.0,-154.9), (178.8,-147.5), (176.4,-143.7), (181.6,-145.3), (188.5,-134.2), (182.7,-129.5), (186.6,-119.4), (191.2,-122.1), (198.4,-115.1), (202.4,-118.9), (208.1,-107.5), (215.8,-109.1), (220.7,-118.5), (241.2,-119.3), (241.3,-134.3), (251.5,-137.7), (259.4,-151.5), (260.7,-146.9), (274.5,-156.6), (280.0,-146.5), (293.9,-149.7), (300.7,-141.4), (310.4,-147.8), (341.3,-125.8), (343.7,-119.3), (340.6,-110.3), (351.0,-101.7), (338.8,-98.3), (340.3,-93.9), (331.0,-82.8), (344.4,-80.8), (335.6,-75.5), (336.7,-70.8), (318.8,-49.6), (297.2,-36.1), (298.7,-19.2), (273.0,2.5), (276.4,6.0), (271.0,17.5), (254.6,36.9), (243.8,37.3), (237.6,28.1), (224.8,36.9), (224.2,30.4), (219.5,31.9), (204.2,10.1), (184.5,8.8), (172.3,46.6), (168.3,46.3), (164.7,32.3), (160.1,36.9), (144.0,33.4), (141.6,45.4), (134.6,48.8), (129.1,44.6), (112.6,47.4), (105.1,42.4), (105.1,34.6), (113.7,30.0), (113.4,15.1), (93.9,6.7), (85.4,-16.4)],
    ],
    'Normandie': [
        [(-273.6,-303.1), (-260.5,-307.5), (-195.5,-296.8), (-163.2,-311.8), (-183.9,-320.1), (-173.4,-342.6), (-144.8,-357.8), (-105.3,-367.1), (-85.4,-381.1), (-79.4,-381.6), (-62.1,-365.0), (-54.1,-348.0), (-61.3,-340.4), (-56.5,-339.1), (-61.2,-327.8), (-56.8,-323.2), (-59.2,-319.4), (-53.6,-319.4), (-59.4,-308.7), (-53.6,-291.1), (-59.8,-293.1), (-67.0,-272.8), (-79.6,-269.9), (-77.8,-261.2), (-74.2,-261.6), (-79.5,-255.7), (-78.6,-250.0), (-86.1,-245.7), (-85.0,-239.9), (-104.2,-240.8), (-104.7,-236.2), (-127.6,-227.5), (-127.0,-221.1), (-115.8,-211.6), (-118.2,-206.3), (-115.2,-202.3), (-130.8,-189.4), (-126.2,-177.2), (-131.5,-173.8), (-137.3,-182.0), (-148.4,-181.5), (-159.1,-189.3), (-160.0,-200.7), (-166.2,-206.9), (-192.8,-195.3), (-192.8,-203.8), (-200.1,-204.2), (-199.9,-212.1), (-204.7,-216.1), (-215.6,-207.2), (-227.5,-210.0), (-246.4,-202.0), (-252.9,-208.9), (-280.2,-213.6), (-293.2,-204.2), (-301.6,-207.8), (-307.7,-222.9), (-291.1,-223.4), (-294.7,-226.1), (-294.6,-227.0), (-292.9,-229.4), (-293.0,-229.9), (-302.7,-229.6), (-311.0,-245.8), (-308.7,-247.4), (-307.2,-255.4), (-306.3,-256.8), (-306.9,-254.5), (-306.4,-252.3), (-306.1,-252.6), (-306.6,-266.9), (-302.7,-266.2), (-309.8,-268.1), (-310.9,-288.1), (-307.5,-288.4), (-311.0,-290.2), (-311.8,-287.1), (-318.3,-299.8), (-317.3,-299.7), (-315.5,-300.5), (-325.7,-304.9), (-331.5,-321.9), (-328.8,-333.6), (-336.2,-342.9), (-311.0,-334.8), (-284.6,-340.5), (-281.8,-330.7), (-286.9,-328.1), (-287.7,-323.3), (-273.6,-303.1)],
    ],
    'Hauts-de-France': [
        [(124.0,-371.7), (131.0,-369.4), (128.9,-349.6), (132.2,-347.3), (122.1,-333.6), (115.3,-332.5), (119.2,-326.8), (116.1,-303.6), (99.9,-308.3), (102.2,-301.9), (86.5,-298.4), (87.1,-287.7), (94.4,-281.3), (84.8,-280.6), (86.0,-272.5), (82.0,-268.3), (89.0,-265.5), (72.6,-246.3), (50.4,-265.4), (48.2,-275.8), (17.8,-270.6), (-14.3,-284.5), (-57.4,-283.9), (-59.9,-292.8), (-52.7,-294.1), (-59.4,-309.0), (-53.6,-319.4), (-59.2,-319.4), (-56.8,-323.2), (-60.6,-334.8), (-56.6,-340.4), (-61.3,-340.4), (-54.1,-348.0), (-62.1,-365.0), (-84.6,-381.1), (-73.5,-396.9), (-61.7,-394.1), (-72.7,-404.6), (-71.4,-413.7), (-64.9,-412.7), (-71.4,-417.7), (-69.3,-432.8), (-68.9,-433.3), (-65.2,-430.1), (-63.5,-429.9), (-69.8,-436.9), (-69.4,-469.8), (-54.4,-479.0), (-24.2,-484.8), (-24.8,-488.9), (3.4,-493.8), (10.0,-478.1), (7.5,-467.4), (16.9,-463.1), (21.9,-453.9), (30.7,-450.2), (34.0,-456.6), (49.2,-460.9), (57.5,-451.1), (59.6,-431.8), (83.8,-428.6), (91.5,-407.3), (94.3,-412.6), (115.2,-413.5), (123.6,-402.3), (129.1,-404.0), (123.0,-388.9), (128.3,-388.9), (130.8,-381.8), (124.0,-371.7)],
    ],
    'Grand Est': [
        [(131.0,-369.4), (147.1,-367.1), (165.8,-373.5), (165.7,-383.3), (175.7,-392.6), (181.2,-389.2), (173.1,-370.7), (180.6,-364.0), (177.7,-351.3), (188.6,-352.1), (201.5,-340.2), (209.4,-340.5), (214.0,-336.0), (212.5,-331.3), (221.3,-329.5), (224.1,-318.9), (247.3,-326.0), (267.7,-313.3), (282.7,-320.6), (305.5,-311.6), (320.3,-282.0), (327.6,-280.7), (327.8,-287.5), (334.5,-288.6), (342.8,-285.0), (344.2,-276.4), (347.7,-281.1), (362.3,-276.7), (373.7,-284.3), (388.1,-270.0), (410.7,-270.4), (433.3,-260.3), (400.7,-218.7), (396.4,-190.1), (383.7,-167.2), (387.1,-150.9), (378.8,-120.7), (384.9,-109.5), (370.6,-91.9), (353.0,-92.7), (355.3,-98.3), (340.6,-110.3), (343.7,-119.3), (341.3,-125.8), (310.4,-147.8), (300.7,-141.4), (293.9,-149.7), (280.0,-146.5), (274.5,-156.6), (260.7,-146.9), (259.4,-151.5), (251.5,-137.7), (241.3,-134.3), (241.2,-119.3), (220.7,-118.5), (215.8,-109.1), (208.1,-107.5), (202.4,-118.9), (198.4,-115.1), (191.2,-122.1), (186.6,-119.4), (182.7,-129.5), (188.5,-134.2), (181.6,-145.3), (176.4,-143.7), (178.8,-147.5), (173.0,-154.9), (157.6,-157.3), (155.3,-150.4), (135.5,-145.8), (128.7,-151.0), (105.5,-146.1), (106.6,-152.0), (102.0,-152.2), (94.3,-172.3), (88.3,-169.3), (81.6,-174.3), (84.4,-183.8), (67.4,-200.6), (68.4,-212.1), (80.0,-221.9), (71.9,-223.8), (73.3,-235.2), (68.0,-237.1), (71.3,-241.1), (68.3,-243.0), (74.6,-243.7), (74.2,-249.3), (89.0,-265.5), (82.0,-268.3), (86.0,-272.5), (84.8,-280.6), (94.4,-281.3), (87.1,-287.7), (86.5,-298.4), (102.2,-301.9), (99.9,-308.3), (116.1,-303.6), (119.2,-326.8), (115.2,-332.3), (122.1,-333.6), (132.2,-347.3), (128.9,-349.6), (131.0,-369.4)],
    ],
    'Pays de la Loire': [
        [(-374.8,-93.3), (-364.1,-94.7), (-362.5,-100.8), (-352.6,-97.8), (-347.6,-102.7), (-346.2,-115.5), (-314.2,-122.0), (-300.7,-135.9), (-283.1,-129.4), (-276.3,-150.2), (-265.7,-154.4), (-272.2,-182.9), (-267.9,-190.1), (-269.1,-210.6), (-252.9,-208.9), (-246.4,-202.0), (-227.5,-210.0), (-215.6,-207.2), (-204.7,-216.1), (-199.9,-212.1), (-200.1,-204.2), (-192.8,-203.8), (-193.3,-196.6), (-192.8,-195.3), (-166.2,-206.9), (-160.0,-200.7), (-158.4,-188.7), (-119.7,-169.3), (-128.9,-161.7), (-124.8,-147.7), (-131.5,-142.9), (-130.4,-136.3), (-135.9,-128.4), (-145.0,-122.5), (-142.5,-119.1), (-160.0,-114.7), (-160.3,-106.5), (-171.4,-111.2), (-175.1,-85.8), (-191.6,-53.5), (-226.3,-53.1), (-234.0,-43.8), (-257.2,-40.8), (-241.8,-23.2), (-243.9,-18.3), (-235.4,-2.4), (-237.4,22.3), (-229.6,23.5), (-238.6,31.4), (-259.3,31.9), (-259.2,25.1), (-279.9,31.3), (-280.2,36.7), (-325.9,11.7), (-329.3,-1.1), (-350.8,-24.1), (-351.8,-31.9), (-348.7,-32.6), (-338.6,-47.2), (-347.9,-56.6), (-358.8,-58.6), (-352.7,-62.3), (-353.0,-73.5), (-362.6,-69.6), (-381.4,-76.0), (-378.1,-80.2), (-382.4,-85.2), (-372.9,-89.4), (-374.8,-93.3)],
    ],
    'Bretagne': [
        [(-344.4,-224.4), (-339.7,-208.1), (-336.6,-217.7), (-342.3,-225.5), (-328.4,-232.3), (-328.6,-221.9), (-307.7,-222.9), (-296.9,-204.8), (-283.7,-213.8), (-269.8,-209.9), (-267.9,-190.1), (-272.2,-182.9), (-265.7,-154.4), (-276.3,-150.2), (-283.1,-129.4), (-300.7,-135.9), (-314.2,-122.0), (-343.1,-117.6), (-352.6,-97.8), (-362.5,-100.8), (-364.1,-94.7), (-376.4,-92.5), (-378.0,-98.2), (-371.9,-98.5), (-387.9,-99.5), (-383.6,-101.4), (-382.4,-104.7), (-386.3,-106.4), (-391.1,-98.1), (-401.7,-97.5), (-409.2,-105.3), (-395.6,-103.5), (-392.2,-109.0), (-392.2,-114.1), (-394.0,-115.3), (-392.7,-111.1), (-394.6,-108.9), (-394.6,-110.3), (-398.9,-112.1), (-397.2,-114.2), (-400.1,-115.0), (-399.3,-112.3), (-405.3,-112.4), (-407.4,-107.2), (-414.0,-116.5), (-410.3,-105.0), (-425.6,-109.5), (-422.0,-95.6), (-426.7,-97.2), (-426.3,-107.8), (-431.6,-114.7), (-423.7,-123.6), (-426.8,-126.8), (-427.8,-124.2), (-429.7,-126.1), (-430.3,-126.3), (-430.9,-125.9), (-428.2,-121.5), (-432.0,-120.5), (-431.9,-114.9), (-442.7,-119.5), (-440.3,-121.2), (-437.3,-119.5), (-436.7,-119.9), (-439.2,-122.0), (-442.3,-121.3), (-443.3,-122.1), (-438.8,-126.3), (-437.0,-129.6), (-437.7,-131.0), (-436.7,-131.4), (-437.6,-131.2), (-438.0,-130.5), (-437.4,-129.0), (-441.7,-125.6), (-445.1,-135.1), (-442.6,-124.6), (-449.9,-120.5), (-455.6,-128.2), (-454.8,-132.3), (-456.6,-135.2), (-456.4,-136.0), (-455.3,-136.9), (-455.2,-137.4), (-456.7,-138.9), (-456.4,-127.9), (-467.1,-129.4), (-470.3,-132.4), (-468.4,-134.1), (-464.8,-134.3), (-464.1,-135.1), (-468.3,-135.4), (-471.1,-132.4), (-471.8,-133.4), (-472.0,-135.9), (-472.3,-137.0), (-472.5,-137.2), (-471.8,-131.7), (-480.4,-130.9), (-489.6,-144.1), (-489.5,-137.9), (-498.8,-138.9), (-502.2,-144.0), (-497.1,-147.1), (-499.5,-147.7), (-498.5,-150.4), (-500.1,-152.2), (-504.6,-143.8), (-499.8,-138.8), (-504.1,-136.3), (-504.8,-140.7), (-507.6,-139.3), (-505.1,-136.0), (-503.3,-135.5), (-505.1,-132.0), (-519.5,-131.8), (-520.3,-145.3), (-531.8,-155.3), (-528.2,-158.2), (-534.0,-154.0), (-547.3,-158.5), (-514.3,-163.8), (-511.9,-171.0), (-526.3,-180.3), (-533.1,-172.5), (-532.3,-181.4), (-538.8,-184.9), (-531.7,-191.6), (-533.6,-187.6), (-531.8,-185.2), (-511.9,-186.6), (-511.3,-185.3), (-512.6,-185.8), (-513.1,-184.2), (-511.4,-182.3), (-500.1,-178.0), (-498.6,-182.1), (-509.3,-181.9), (-512.4,-184.6), (-505.5,-186.7), (-516.7,-188.7), (-511.3,-193.4), (-525.8,-190.0), (-522.1,-195.9), (-514.7,-199.9), (-512.4,-201.9), (-511.7,-203.0), (-545.4,-190.3), (-549.7,-190.3), (-547.7,-194.2), (-551.4,-199.6), (-545.7,-206.3), (-549.9,-211.1), (-544.5,-216.7), (-529.5,-214.0), (-537.5,-217.6), (-527.4,-217.0), (-534.2,-221.0), (-532.4,-224.0), (-521.4,-224.0), (-521.3,-224.2), (-521.8,-224.5), (-524.0,-225.2), (-524.3,-226.0), (-516.2,-228.5), (-513.7,-223.6), (-489.1,-234.0), (-488.0,-221.8), (-485.4,-228.3), (-483.0,-227.8), (-484.1,-226.3), (-481.3,-220.4), (-480.0,-220.7), (-477.7,-233.0), (-459.0,-228.2), (-460.0,-239.5), (-456.1,-242.2), (-456.6,-244.5), (-453.7,-246.3), (-445.7,-242.1), (-435.7,-245.8), (-432.7,-249.7), (-431.0,-245.8), (-433.6,-240.8), (-432.3,-240.2), (-429.5,-246.8), (-421.3,-251.0), (-425.0,-237.6), (-416.4,-244.2), (-419.2,-240.4), (-410.3,-237.0), (-411.5,-233.3), (-391.6,-208.1), (-377.0,-225.0), (-364.1,-229.8), (-364.0,-221.1), (-358.8,-225.1), (-353.5,-217.4), (-349.5,-220.5), (-351.5,-223.8), (-344.4,-224.4)],
    ],
    'Nouvelle-Aquitaine': [
        [(-82.0,27.8), (-73.9,19.1), (-58.4,23.1), (-53.9,15.9), (-18.9,19.1), (4.5,46.9), (8.2,69.7), (-8.5,85.0), (1.7,97.7), (-2.9,110.4), (1.3,115.2), (-0.9,130.0), (2.1,132.9), (-11.3,130.6), (-10.6,139.0), (-23.5,151.6), (-20.3,158.0), (-30.6,169.8), (-27.7,177.6), (-44.7,178.4), (-52.8,184.6), (-65.8,172.3), (-82.4,175.3), (-80.0,189.5), (-90.8,198.4), (-89.5,204.6), (-102.3,212.2), (-105.6,223.1), (-114.8,226.1), (-108.5,244.4), (-117.7,248.1), (-121.2,244.0), (-123.3,251.9), (-117.1,255.7), (-124.5,265.8), (-121.4,270.8), (-129.3,270.1), (-138.9,283.3), (-144.1,277.3), (-166.1,287.0), (-179.4,285.8), (-184.8,290.2), (-184.5,297.4), (-191.7,287.8), (-206.2,295.7), (-203.6,314.9), (-210.1,328.0), (-196.3,331.9), (-190.3,344.1), (-194.0,350.9), (-189.1,347.0), (-186.7,357.9), (-192.4,362.9), (-194.1,376.5), (-203.6,383.3), (-202.7,390.2), (-210.7,395.3), (-212.4,412.2), (-217.9,417.9), (-226.8,414.9), (-231.8,420.1), (-244.3,407.4), (-245.9,399.6), (-275.3,395.1), (-287.9,388.4), (-284.9,383.0), (-290.6,385.7), (-291.3,392.9), (-297.9,390.9), (-300.3,386.5), (-293.4,375.1), (-293.9,367.6), (-305.0,363.6), (-310.5,368.3), (-311.7,362.3), (-319.7,363.5), (-324.0,357.3), (-310.2,348.7), (-298.4,325.3), (-284.2,226.3), (-280.6,220.1), (-279.3,213.7), (-275.8,215.6), (-267.5,214.1), (-267.2,214.6), (-266.2,215.4), (-264.8,214.7), (-277.2,200.6), (-284.3,216.5), (-276.3,123.6), (-271.4,114.1), (-263.7,111.6), (-281.9,101.5), (-282.9,90.0), (-274.6,87.7), (-277.4,81.8), (-273.1,81.5), (-269.4,71.5), (-273.7,65.7), (-268.5,64.8), (-276.7,48.9), (-282.8,48.1), (-268.6,27.6), (-259.2,25.1), (-261.7,30.5), (-243.5,32.7), (-229.6,23.5), (-237.4,22.3), (-234.5,5.7), (-243.9,-18.3), (-241.8,-23.2), (-257.2,-40.8), (-234.0,-43.8), (-226.3,-53.1), (-202.5,-55.9), (-198.7,-50.0), (-185.2,-62.6), (-175.1,-56.6), (-175.7,-50.7), (-165.9,-49.8), (-164.5,-36.5), (-143.6,-39.3), (-146.0,-44.7), (-136.6,-41.2), (-135.7,-33.4), (-119.9,-13.8), (-119.7,0.4), (-102.3,10.3), (-97.3,18.5), (-99.6,24.6), (-86.5,22.0), (-82.0,27.8)],
        [(-281.6,87.6), (-293.7,71.2), (-295.7,60.7), (-282.5,67.8), (-278.7,78.5), (-281.6,87.6)],
    ],
    'Occitanie': [
        [(-54.0,442.9), (-71.9,433.9), (-80.3,439.6), (-86.4,426.9), (-100.8,428.0), (-107.4,419.3), (-135.4,411.2), (-140.2,419.8), (-137.8,430.0), (-161.7,426.3), (-166.6,432.0), (-175.7,424.9), (-193.2,429.9), (-201.1,418.2), (-212.1,413.5), (-210.7,395.3), (-202.7,390.2), (-203.6,383.3), (-194.1,376.5), (-192.4,362.9), (-186.7,357.9), (-189.1,347.0), (-194.0,350.9), (-190.3,344.1), (-196.3,331.9), (-210.1,328.0), (-203.6,314.9), (-206.1,307.1), (-203.0,300.6), (-207.0,297.2), (-191.7,287.8), (-184.5,297.4), (-184.8,290.2), (-179.4,285.8), (-166.1,287.0), (-144.1,277.3), (-137.8,283.0), (-129.3,270.1), (-121.4,270.8), (-124.5,265.8), (-117.1,255.7), (-123.3,251.9), (-121.2,244.0), (-117.7,248.1), (-108.5,244.4), (-114.8,226.1), (-105.6,223.1), (-102.3,212.2), (-91.6,207.4), (-90.8,198.4), (-80.0,189.5), (-82.4,175.3), (-72.7,170.9), (-54.8,184.4), (-33.0,178.6), (-25.1,196.8), (-28.0,209.1), (-22.1,218.3), (-16.2,212.7), (-1.3,214.5), (7.8,193.3), (18.0,182.5), (20.7,192.0), (27.2,189.8), (36.4,215.1), (45.6,188.5), (52.0,191.2), (65.9,178.7), (73.9,196.9), (85.4,189.1), (104.0,204.5), (106.2,220.8), (118.5,241.4), (116.9,250.9), (122.9,248.8), (132.9,256.9), (138.0,248.8), (142.9,247.8), (146.7,254.8), (151.6,248.2), (161.6,254.9), (167.9,265.4), (167.8,277.0), (177.1,284.9), (161.9,300.6), (160.8,320.6), (150.2,319.1), (145.6,327.3), (148.2,331.2), (137.1,334.9), (130.8,345.4), (123.0,342.2), (122.2,335.6), (113.0,335.7), (76.3,366.1), (65.7,365.3), (50.6,378.5), (41.6,397.5), (39.6,428.6), (41.7,446.2), (48.5,449.3), (50.9,458.1), (33.8,453.0), (13.1,461.5), (13.3,468.3), (2.5,469.4), (-18.4,457.8), (-36.6,467.9), (-42.6,456.1), (-58.1,451.8), (-54.0,442.9)],
    ],
    'Auvergne-Rhône-Alpes': [
        [(172.3,46.6), (184.5,8.8), (204.2,10.1), (219.5,31.9), (224.2,30.4), (224.8,36.9), (237.6,28.1), (243.8,37.3), (253.4,37.2), (268.8,20.2), (276.6,24.3), (273.9,38.4), (262.6,42.3), (261.3,51.9), (274.8,50.4), (286.8,41.3), (282.5,35.4), (287.6,25.7), (325.4,22.6), (322.9,27.5), (329.9,35.2), (324.7,50.8), (332.5,52.4), (330.7,60.7), (335.4,59.0), (343.5,74.5), (326.4,84.0), (325.6,96.2), (340.2,105.6), (340.1,120.5), (354.0,131.2), (348.5,140.0), (350.5,147.9), (332.0,160.9), (303.1,164.0), (301.3,169.8), (282.0,163.8), (279.9,174.6), (289.0,176.1), (291.3,192.1), (265.7,194.1), (260.8,202.4), (251.5,202.4), (248.7,214.1), (237.5,214.4), (234.1,226.2), (239.2,230.8), (235.2,234.3), (223.6,231.1), (226.6,237.9), (220.6,239.3), (221.6,245.2), (236.3,249.2), (240.8,256.6), (237.6,267.2), (240.2,269.9), (232.5,265.3), (226.9,273.3), (215.8,262.4), (200.9,260.8), (201.6,251.4), (175.8,260.9), (171.0,250.2), (162.5,249.7), (162.4,256.3), (151.4,248.1), (143.6,254.3), (142.7,247.8), (132.9,256.9), (122.9,248.8), (117.3,251.1), (118.5,241.4), (106.2,220.8), (104.0,204.5), (85.4,189.1), (73.9,196.9), (65.9,178.7), (52.0,191.2), (45.6,188.5), (36.4,215.1), (27.2,189.8), (20.7,192.0), (18.0,182.5), (9.3,190.7), (-2.4,215.3), (-16.2,212.7), (-22.1,218.3), (-28.0,209.1), (-25.1,196.8), (-33.0,178.6), (-27.5,177.1), (-30.6,169.8), (-20.3,158.0), (-23.5,151.6), (-10.6,139.0), (-11.3,130.6), (1.8,133.9), (1.3,115.2), (-2.9,110.4), (1.7,97.7), (-8.5,85.0), (8.4,69.1), (1.1,39.6), (-15.0,28.4), (-12.3,25.9), (-16.4,16.6), (-10.2,9.0), (8.7,5.1), (5.1,-5.9), (15.5,-15.3), (26.2,-14.0), (39.1,-22.0), (52.8,-8.7), (69.7,-12.5), (74.2,-5.6), (83.0,-17.8), (93.9,6.7), (113.4,15.1), (113.7,30.0), (105.6,33.8), (105.7,42.9), (134.6,48.8), (141.6,45.4), (144.0,33.4), (160.1,36.9), (164.7,32.3), (168.3,46.3), (172.3,46.6)],
    ],
    "Provence-Alpes-Côte d'Azur": [
        [(336.2,214.0), (337.7,217.8), (329.0,227.8), (336.2,238.7), (332.0,239.7), (331.6,246.3), (340.8,260.1), (367.2,273.2), (391.3,266.5), (394.4,276.9), (377.7,300.1), (380.2,309.3), (376.9,313.6), (352.0,324.1), (350.4,336.1), (337.3,336.4), (329.2,350.7), (320.9,350.0), (308.7,365.5), (317.3,366.7), (313.4,377.6), (293.6,380.2), (292.1,386.5), (279.7,383.2), (275.8,393.2), (271.4,392.1), (273.1,386.8), (258.5,382.4), (255.5,384.5), (260.5,388.5), (251.8,390.6), (250.0,383.3), (240.9,376.2), (214.8,372.6), (217.2,363.6), (215.5,359.2), (212.7,356.4), (192.7,360.3), (186.7,349.3), (180.9,351.5), (178.4,346.1), (176.0,354.7), (180.1,356.8), (182.7,354.2), (178.0,359.4), (176.5,359.8), (157.6,356.4), (153.5,346.2), (130.8,345.4), (137.1,334.9), (148.2,331.2), (145.6,327.3), (150.2,319.1), (160.8,320.6), (161.9,300.6), (177.2,287.2), (166.8,274.6), (162.5,249.7), (172.3,250.9), (175.8,260.9), (201.6,251.4), (200.7,260.6), (215.8,262.4), (223.3,272.9), (234.5,264.9), (240.2,269.9), (237.6,267.2), (240.8,256.6), (236.6,249.4), (221.6,245.2), (220.6,239.3), (226.6,237.9), (223.6,231.1), (235.2,234.3), (239.2,230.8), (234.1,226.2), (237.5,214.4), (248.7,214.1), (251.5,202.4), (260.8,202.4), (265.7,194.1), (291.3,192.1), (289.0,176.1), (279.9,174.6), (284.2,162.0), (298.7,170.3), (311.8,163.3), (315.5,173.8), (320.9,174.4), (321.3,186.4), (341.9,195.5), (345.9,211.1), (336.2,214.0)],
    ],
    'Corse': [
        [(521.7,521.5), (520.4,544.9), (512.5,550.3), (519.1,551.0), (511.9,557.8), (507.5,570.5), (510.9,570.5), (507.9,575.6), (498.6,572.9), (497.3,563.5), (485.2,562.2), (474.8,553.7), (475.7,546.4), (484.7,540.0), (465.5,534.6), (476.4,517.4), (472.6,513.3), (461.5,517.5), (460.4,509.9), (472.1,500.4), (457.9,489.9), (460.5,487.5), (456.5,479.9), (468.0,476.5), (456.7,465.6), (465.3,460.2), (469.3,442.6), (492.4,435.5), (500.7,425.5), (515.0,430.2), (518.6,404.3), (517.0,396.8), (523.0,394.7), (526.3,397.5), (528.5,417.4), (525.0,431.9), (531.5,445.7), (533.5,484.4), (521.7,521.5)],
    ],
}

TAILLE_HEX_DEFAUT = 68  # rayon centre-sommet, en unités de scène


# ------------------------------------------------------------------
# Géométrie pure (pas de dépendance PyQt)
# ------------------------------------------------------------------
def position_pixel(row, col, taille=TAILLE_HEX_DEFAUT):
    """Coordonnées (x, y) du centre d'une tuile hexagonale "pointy-top"
    dans une grille en briques (lignes impaires décalées d'une demi-tuile),
    à partir de sa position logique (row, col)."""
    largeur = math.sqrt(3) * taille
    espace_vert = 1.5 * taille
    x = col * largeur + (largeur / 2 if row % 2 else 0)
    y = row * espace_vert
    return x, y


def sommets_hexagone(cx, cy, taille=TAILLE_HEX_DEFAUT):
    """Liste des 6 sommets (x, y) d'un hexagone "pointy-top" centré sur
    (cx, cy). Fonction pure, réutilisable indépendamment de Qt pour les
    tests."""
    pts = []
    for i in range(6):
        angle = math.radians(60 * i - 30)
        pts.append((cx + taille * math.cos(angle), cy + taille * math.sin(angle)))
    return pts


def centre_contour_region(nom):
    """Centre (milieu de la boîte englobante) du plus grand anneau du
    contour géographique réel d'une région, en coordonnées de scène -
    utilisé pour positionner l'étiquette de son nom sur la carte
    "géographique"."""
    plus_grand = max(CONTOURS_REGIONS[nom], key=len)
    xs = [p[0] for p in plus_grand]
    ys = [p[1] for p in plus_grand]
    return (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2


def couleur_pour(nom_region, mode_index):
    """mode_index 0 = climat, 1 = qualité du sol. Renvoie un code couleur
    hexadécimal."""
    d = REGIONS[nom_region]
    if mode_index == 0:
        return CLIMAT_COULEURS[d["climat"]]
    return SOL_COULEURS_NIVEAU[d["sol_niveau"]]


def legende_pour(mode_index):
    """Liste ordonnée de tuples (libellé, couleur) pour la légende du mode
    demandé."""
    if mode_index == 0:
        return list(CLIMAT_COULEURS.items())
    return [(SOL_LABELS_NIVEAU[n], SOL_COULEURS_NIVEAU[n]) for n in sorted(SOL_COULEURS_NIVEAU)]


# ------------------------------------------------------------------
# Classes PyQt
# ------------------------------------------------------------------
COULEUR_BORD_NORMAL = "#3a3a3a"
COULEUR_BORD_SURVOL = "#0b5a9e"
COULEUR_BORD_SELECTION = "#c62828"


class FormeRegion(QGraphicsPolygonItem):
    """Classe de base : un polygone cliquable représentant une région (ou,
    en carte géographique, une partie de région - contigu principal ou
    île). Couleur selon le mode d'affichage courant, surlignée au survol,
    sélectionnée au clic (le module appelant fournit un callback qui
    reçoit le nom de la région). Utilisée aussi bien par TuileRegion (carte
    schématique) que par les contours réels (carte géographique)."""

    def __init__(self, nom, polygone, callback_clic=None):
        super().__init__(polygone)
        self.nom = nom
        self.callback_clic = callback_clic
        self.selectionnee = False
        self.setAcceptHoverEvents(True)
        self.setPen(QPen(QColor(COULEUR_BORD_NORMAL), 2))
        self.setBrush(QBrush(QColor("#cccccc")))
        self.setToolTip(nom)

    def definir_couleur(self, couleur_hex):
        self.setBrush(QBrush(QColor(couleur_hex)))

    def definir_selection(self, selectionnee):
        self.selectionnee = selectionnee
        self._appliquer_pen_repos()

    def _appliquer_pen_repos(self):
        if self.selectionnee:
            self.setPen(QPen(QColor(COULEUR_BORD_SELECTION), 4))
        else:
            self.setPen(QPen(QColor(COULEUR_BORD_NORMAL), 2))

    def hoverEnterEvent(self, event):
        self.setPen(QPen(QColor(COULEUR_BORD_SURVOL), 3))
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self._appliquer_pen_repos()
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event):
        if self.callback_clic:
            self.callback_clic(self.nom)
        super().mousePressEvent(event)


class TuileRegion(FormeRegion):
    """Une tuile hexagonale représentant une région, pour la carte
    "schématique (mailles)"."""

    def __init__(self, nom, cx, cy, taille=TAILLE_HEX_DEFAUT, callback_clic=None):
        polygone = QPolygonF([QPointF(x, y) for x, y in sommets_hexagone(cx, cy, taille)])
        super().__init__(nom, polygone, callback_clic)


def parties_contour_region(nom, callback_clic=None):
    """Pour la carte "géographique" : renvoie la liste des FormeRegion (une
    par anneau - contigu principal puis îles éventuelles) représentant le
    contour réel d'une région. Tous les éléments renvoyés partagent le même
    nom et déclenchent le même callback : le module appelant doit les
    traiter comme un seul groupe logique (même couleur, même sélection)."""
    return [
        FormeRegion(nom, QPolygonF([QPointF(x, y) for x, y in anneau]), callback_clic)
        for anneau in CONTOURS_REGIONS[nom]
    ]


def creer_etiquette(nom, cx, cy):
    """Petit texte centré sur (cx, cy) (nom de la région, retour à la ligne
    si trop long pour tenir dans une tuile hexagonale - sans effet gênant
    en carte géographique où la place est en général suffisante)."""
    texte = nom.replace(" ", "\n") if len(nom) > 13 else nom
    item = QGraphicsSimpleTextItem(texte)
    item.setFont(QFont("Sans Serif", 7, QFont.DemiBold))
    rect = item.boundingRect()
    item.setPos(cx - rect.width() / 2, cy - rect.height() / 2)
    item.setZValue(1)
    return item


class VueCarteFrance(QGraphicsView):
    """QGraphicsView avec zoom à la molette centré sous le curseur (même
    principe que VueFerme dans plan_ferme.py), et ajustement automatique du
    cadrage au premier affichage de l'onglet."""

    ZOOM_MIN = 0.4
    ZOOM_MAX = 6.0

    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self.setRenderHint(QPainter.Antialiasing)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self._zoom_actuel = 1.0
        self._premier_affichage = True

    def wheelEvent(self, event):
        facteur = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        nouveau_zoom = self._zoom_actuel * facteur
        if nouveau_zoom < self.ZOOM_MIN or nouveau_zoom > self.ZOOM_MAX:
            return
        self._zoom_actuel = nouveau_zoom
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.scale(facteur, facteur)

    def ajuster_vue(self):
        if self.scene() is not None:
            self.fitInView(self.scene().itemsBoundingRect(), Qt.KeepAspectRatio)
            self._zoom_actuel = 1.0

    def showEvent(self, event):
        super().showEvent(event)
        if self._premier_affichage:
            self.ajuster_vue()
            self._premier_affichage = False
