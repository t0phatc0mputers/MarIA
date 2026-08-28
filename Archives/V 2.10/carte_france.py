# -*- coding: utf-8 -*-
"""
carte_france.py
-----------------
Carte interactive (zoomable à la molette, comme le "Plan de la ferme") des
13 régions de France métropolitaine, affichées sous forme de tuiles
hexagonales disposées selon leur position géographique relative (carte "en
mailles", technique classique de cartographie schématique française : chaque
région a la même taille visuelle, ce qui évite que les grandes régions
rurales n'écrasent les petites régions densément peuplées).

Deux indicateurs sont disponibles, au choix, via un sélecteur :
  - le climat dominant de la région (classification simplifiée),
  - une qualité de sol indicative (type dominant + niveau de fertilité 1-5).

Ces données sont volontairement SCHÉMATIQUES : chaque région de France
présente en réalité une grande diversité interne de climats et de sols
(ex. littoral vs. montagne en PACA, Beauce vs. Sologne en Centre-Val de
Loire...). Cette carte donne un premier repère à l'échelle régionale ; pour
une décision agronomique réelle, on se reportera aux données locales (onglet
"Aide à la décision" pour la météo de la commune, onglet "Analyse de sol"
pour une analyse de sol réelle).

Ce module est coupé en deux parties, comme plan_ferme.py :
  - données + géométrie pure (dicts, fonctions de calcul de position) ;
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


class TuileRegion(QGraphicsPolygonItem):
    """Une tuile hexagonale représentant une région : couleur selon le mode
    d'affichage courant, surlignée au survol, sélectionnée au clic (le
    module appelant fournit un callback qui reçoit le nom de la région)."""

    def __init__(self, nom, cx, cy, taille=TAILLE_HEX_DEFAUT, callback_clic=None):
        polygone = QPolygonF([QPointF(x, y) for x, y in sommets_hexagone(cx, cy, taille)])
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


def creer_etiquette(nom, cx, cy):
    """Petit texte centré sur la tuile (nom de la région, retour à la ligne
    si trop long pour tenir dans l'hexagone)."""
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
