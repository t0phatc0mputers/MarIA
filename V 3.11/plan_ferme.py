# -*- coding: utf-8 -*-
"""
plan_ferme.py
--------------
Modèle de données, format de fichier texte et outils géométriques pour
l'onglet "Plan de la ferme" (éditeur de rectangles emboîtables, un peu à la
manière d'un schéma LTSpice).

Ce module est volontairement coupé en deux parties :

  - une partie 100% Python "pure" (aucune dépendance à PyQt) qui gère le
    format de fichier texte et la géométrie (recherche du meilleur
    "conteneur" pour emboîter un rectangle) : c'est cette partie qui peut
    être testée indépendamment de l'interface graphique ;
  - une partie PyQt (classes QGraphicsRectItem / QDialog / QGraphicsView)
    qui s'appuie sur la première pour dessiner, éditer et enregistrer le
    plan depuis l'application.

FORMAT DE FICHIER (texte, lisible/éditable à la main)
-------------------------------------------------------
    PLAN_FERME 1
    ECHELLE_X 1.0
    ECHELLE_Y 1.0

    RECT id=1 parent=0
      nom=Zone Nord
      type=Zone
      etat=Terre travaillée
      culture=
      x=20
      y=20
      largeur=800
      hauteur=300

    RECT id=2 parent=1
      nom=Chapelle 1
      type=Chapelle
      etat=Serre
      culture=
      x=40
      y=40
      largeur=200
      hauteur=200
      historique=2022|2023|Tomate
      historique=2023|2024|Haricot

`parent=0` signifie "pas de parent" (rectangle racine, coordonnées dans le
repère de la scène). Pour un rectangle emboîté, x/y sont exprimés dans le
repère local du parent (0,0 = coin haut-gauche du parent) — c'est
exactement la convention utilisée par QGraphicsItem, ce qui simplifie
beaucoup le code d'affichage.

`ECHELLE_X` / `ECHELLE_Y` (optionnelles, valeurs = mètres réels par unité
de dessin, dans le sens largeur/longueur pour X et hauteur pour Y ; 1.0
par défaut chacune) permettent d'interpréter largeur/hauteur comme des
mesures réelles - utilisé notamment pour calculer la surface (m²) de
chaque planche. Séparer les deux axes permet un plan dessiné à une
échelle différente en largeur et en hauteur ; par défaut (les deux
valeurs égales), 1 unité de dessin = 1 mètre dans les deux sens.
Absentes d'un fichier, elles valent 1.0 (comportement historique).
Pour compatibilité avec d'anciens fichiers, une ligne `ECHELLE <valeur>`
(sans suffixe) est encore lue et utilisée pour les deux axes si
`ECHELLE_X`/`ECHELLE_Y` sont absentes.

`historique` (optionnelle, répétable) déclare une culture passée sur ce
rectangle : `historique=<début>|<fin>|<culture>`, où <début> et <fin>
sont une plage de temps en texte libre (année, saison, date...) et
<culture> le nom de la culture qui y a été menée. Contrairement à
`culture=` (la culture *actuellement* en place), `historique=` peut
apparaître plusieurs fois pour accumuler tout le passé cultural de la
parcelle - c'est cette liste qu'utilise le système de rotation de
l'onglet "Création planning cultural" pour ne pas se limiter à la seule
dernière culture connue. Absente d'un fichier, l'historique est une
liste vide (comportement historique inchangé).
"""

import calendar
import datetime
import re

# ------------------------------------------------------------------
# Vocabulaire métier
# ------------------------------------------------------------------
TYPES_ZONE = ["Zone", "Chapelle", "Planche"]
ETATS = ["Non défini", "Serre", "Bâche", "Paille", "Compost", "Terre travaillée"]

COULEUR_PAR_ETAT = {
    "Non défini": "#e0e0e0",
    "Serre": "#a5d6a7",
    "Bâche": "#b0bec5",
    "Paille": "#e6d29e",
    "Compost": "#8d6e63",
    "Terre travaillée": "#a1887f",
}

COULEUR_BORD_PAR_TYPE = {
    "Zone": "#616161",
    "Chapelle": "#1565c0",
    "Planche": "#2e7d32",
}

EPAISSEUR_BORD_PAR_TYPE = {
    "Zone": 1,
    "Chapelle": 3,
    "Planche": 2,
}

COULEUR_ACCENT_PF = "#0b5a9e"


# ------------------------------------------------------------------
# Géométrie pure (pas de dépendance PyQt) : recherche du meilleur parent
# ------------------------------------------------------------------
def rect_contient(conteneur, rect, marge=0.0):
    """conteneur et rect sont des tuples (x, y, largeur, hauteur) exprimés
    dans le MÊME repère (typiquement la scène). Retourne True si conteneur
    contient entièrement rect (avec une petite tolérance de marge)."""
    cx, cy, cw, ch = conteneur
    rx, ry, rw, rh = rect
    return (rx >= cx - marge and ry >= cy - marge and
            rx + rw <= cx + cw + marge and ry + rh <= cy + ch + marge)


def trouver_meilleur_parent(rect_scene, rects_existants, exclure_id=None):
    """rect_scene : tuple (x, y, largeur, hauteur) en coordonnées scène du
    nouveau rectangle. rects_existants : liste de dicts avec au moins
    {id, x_scene, y_scene, largeur, hauteur} (coordonnées ABSOLUES/scène,
    déjà résolues en tenant compte de l'emboîtement éventuel).
    Retourne l'id du plus petit rectangle existant qui contient entièrement
    rect_scene, ou None si aucun ne convient (le nouveau rectangle restera
    à la racine)."""
    meilleur_id, meilleure_surface = None, None
    for r in rects_existants:
        if exclure_id is not None and r["id"] == exclure_id:
            continue
        conteneur = (r["x_scene"], r["y_scene"], r["largeur"], r["hauteur"])
        if rect_contient(conteneur, rect_scene):
            surface = r["largeur"] * r["hauteur"]
            if meilleure_surface is None or surface < meilleure_surface:
                meilleure_surface, meilleur_id = surface, r["id"]
    return meilleur_id


def generer_grille_rectangles(ancre_x, ancre_y, lignes, colonnes, largeur, hauteur,
                               espacement_h, espacement_v):
    """Calcule les (x, y, largeur, hauteur) — dans le même repère que
    ancre_x/ancre_y — d'une grille de `lignes` x `colonnes` rectangles
    identiques, en partant du coin haut-gauche `ancre_x, ancre_y`."""
    resultats = []
    for i in range(lignes):
        for j in range(colonnes):
            x = ancre_x + j * (largeur + espacement_h)
            y = ancre_y + i * (hauteur + espacement_v)
            resultats.append((x, y, largeur, hauteur))
    return resultats


# ------------------------------------------------------------------
# Sérialisation / désérialisation du fichier texte
# ------------------------------------------------------------------
# `historique` n'est volontairement pas listé ici : contrairement aux
# champs ci-dessous (une valeur = une ligne), c'est une liste répétable
# (voir `historique=` dans le docstring du module et serialiser/deserialiser
# ci-dessous).
CHAMPS = ["nom", "type", "etat", "culture", "x", "y", "largeur", "hauteur"]


def serialiser(rects, echelle_x=1.0, echelle_y=None):
    """rects : liste de dicts {id, parent, nom, type, etat, culture,
    x, y, largeur, hauteur, historique}. `historique` (optionnel) est une
    liste de tuples ((debut, fin), culture) - le passé cultural de la
    parcelle. `echelle_x`/`echelle_y` : nombre de mètres réels que
    représente 1 unité de dessin, respectivement en largeur/longueur et en
    hauteur (par défaut 1.0, donc 1 unité = 1 m dans les deux sens). Si
    `echelle_y` est omis, il reprend la valeur de `echelle_x` (échelle
    identique dans les deux sens). Retourne le texte du fichier."""
    if echelle_y is None:
        echelle_y = echelle_x
    lignes = ["PLAN_FERME 1", f"ECHELLE_X {echelle_x}", f"ECHELLE_Y {echelle_y}", ""]
    for r in sorted(rects, key=lambda r: r["id"]):
        lignes.append(f"RECT id={r['id']} parent={r.get('parent', 0)}")
        lignes.append(f"  nom={_echapper(r.get('nom', ''))}")
        lignes.append(f"  type={_echapper(r.get('type', 'Zone'))}")
        lignes.append(f"  etat={_echapper(r.get('etat', 'Non défini'))}")
        lignes.append(f"  culture={_echapper(r.get('culture', ''))}")
        lignes.append(f"  x={r.get('x', 0)}")
        lignes.append(f"  y={r.get('y', 0)}")
        lignes.append(f"  largeur={r.get('largeur', 0)}")
        lignes.append(f"  hauteur={r.get('hauteur', 0)}")
        for (debut, fin), culture_hist in r.get("historique", []) or []:
            lignes.append(f"  historique={_echapper_historique(debut)}|"
                           f"{_echapper_historique(fin)}|{_echapper_historique(culture_hist)}")
        lignes.append("")
    return "\n".join(lignes) + "\n"


def _echapper(texte):
    return str(texte).replace("\n", " ").replace("\r", " ")


def _echapper_historique(texte):
    # En plus des retours à la ligne, on neutralise le séparateur "|" pour
    # ne pas casser le parsing d'une ligne historique=debut|fin|culture.
    return _echapper(texte).replace("|", "/")


_RE_RECT = re.compile(r"^RECT\s+id=(\d+)\s+parent=(\d+)\s*$")
_RE_ECHELLE = re.compile(r"^ECHELLE\s+([0-9.,]+)\s*$")
_RE_ECHELLE_X = re.compile(r"^ECHELLE_X\s+([0-9.,]+)\s*$")
_RE_ECHELLE_Y = re.compile(r"^ECHELLE_Y\s+([0-9.,]+)\s*$")


def _parse_nombre(texte, defaut=1.0):
    try:
        return float(texte.replace(",", "."))
    except ValueError:
        return defaut


def lire_echelles(texte):
    """Renvoie le tuple (echelle_x, echelle_y) (mètres réels par unité de
    dessin, en largeur/longueur puis en hauteur) déclaré en tête du
    fichier. Comportement par défaut / de compatibilité :
      - fichier avec ECHELLE_X et/ou ECHELLE_Y : valeurs lues (1.0 pour
        l'axe manquant) ;
      - fichier avec seulement l'ancienne ligne ECHELLE <valeur> (format
        historique à échelle unique) : la même valeur est utilisée pour
        les deux axes ;
      - fichier sans aucune de ces lignes : 1.0 pour les deux axes (1
        unité de dessin = 1 mètre)."""
    echelle_x = echelle_y = None
    echelle_unique = None
    for brute in texte.splitlines():
        ligne = brute.strip()
        m = _RE_ECHELLE_X.match(ligne)
        if m:
            echelle_x = _parse_nombre(m.group(1))
            continue
        m = _RE_ECHELLE_Y.match(ligne)
        if m:
            echelle_y = _parse_nombre(m.group(1))
            continue
        m = _RE_ECHELLE.match(ligne)
        if m:
            echelle_unique = _parse_nombre(m.group(1))

    if echelle_x is None:
        echelle_x = echelle_unique if echelle_unique is not None else 1.0
    if echelle_y is None:
        echelle_y = echelle_unique if echelle_unique is not None else echelle_x
    return echelle_x, echelle_y


def lire_echelle(texte):
    """Ancienne API (échelle unique) conservée pour compatibilité : renvoie
    l'échelle en largeur/longueur (ECHELLE_X, ou ECHELLE si présente, ou
    1.0). Préférer `lire_echelles` qui renvoie les deux axes."""
    echelle_x, _ = lire_echelles(texte)
    return echelle_x


def deserialiser(texte):
    """Analyse le texte d'un fichier .plan et retourne une liste de dicts
    {id, parent, nom, type, etat, culture, x, y, largeur, hauteur,
    historique} triée par id croissant (historique : liste de tuples
    ((debut, fin), culture), éventuellement vide). Lève ValueError si le
    format est invalide."""
    rects = {}
    courant = None
    for brute in texte.splitlines():
        ligne = brute.rstrip()
        if not ligne.strip():
            continue
        if ligne.startswith("PLAN_FERME"):
            continue
        m = _RE_RECT.match(ligne.strip())
        if m:
            id_, parent = int(m.group(1)), int(m.group(2))
            courant = {"id": id_, "parent": parent, "nom": "", "type": "Zone",
                       "etat": "Non défini", "culture": "", "x": 0.0, "y": 0.0,
                       "largeur": 10.0, "hauteur": 10.0, "historique": []}
            rects[id_] = courant
            continue
        if courant is None:
            continue
        cle_valeur = ligne.strip()
        if "=" not in cle_valeur:
            continue
        cle, _, valeur = cle_valeur.partition("=")
        cle = cle.strip()
        valeur = valeur.strip()
        if cle in ("x", "y", "largeur", "hauteur"):
            try:
                courant[cle] = float(valeur)
            except ValueError:
                courant[cle] = 0.0
        elif cle in ("nom", "type", "etat", "culture"):
            courant[cle] = valeur
        elif cle == "historique":
            parties = valeur.split("|", 2)
            if len(parties) == 3:
                debut, fin, culture_hist = parties
                courant["historique"].append(((debut, fin), culture_hist))

    return [rects[i] for i in sorted(rects)]


def surface_m2(largeur, hauteur, echelle_x=1.0, echelle_y=None):
    """Surface réelle (m²) d'un rectangle dessiné avec largeur/hauteur en
    unités de dessin, compte tenu de l'échelle horizontale (echelle_x,
    mètres réels par unité de largeur/longueur) et verticale (echelle_y,
    mètres réels par unité de hauteur — voir lire_echelles). Si echelle_y
    est omis, il reprend la valeur de echelle_x (échelle identique dans
    les deux sens, comportement historique)."""
    if echelle_y is None:
        echelle_y = echelle_x
    return (largeur * echelle_x) * (hauteur * echelle_y)


def prochain_id(rects):
    if not rects:
        return 1
    return max(r["id"] for r in rects) + 1


# ====================================================================
# Partie PyQt : éditeur graphique
# ====================================================================
from PyQt5.QtCore import Qt, QRectF, QPointF
from PyQt5.QtGui import QColor, QBrush, QPen, QPainter, QKeySequence
from PyQt5.QtWidgets import (
    QGraphicsRectItem, QGraphicsView, QGraphicsScene, QDialog, QDialogButtonBox,
    QSpinBox, QDoubleSpinBox, QComboBox, QLineEdit, QLabel, QFormLayout,
    QVBoxLayout, QHBoxLayout, QCompleter, QMessageBox, QUndoStack, QUndoCommand, QShortcut,
    QPushButton, QTableWidget, QTableWidgetItem, QAbstractItemView, QWidget,
)


class RectangleFerme(QGraphicsRectItem):
    """Un rectangle du plan de ferme (zone, chapelle ou planche). Les
    rectangles peuvent être emboîtés via le mécanisme standard de parenté
    de QGraphicsItem : setParentItem(...) + setPos(...) en coordonnées du
    parent — déplacer un rectangle déplace donc automatiquement tout ce
    qui est emboîté dedans."""

    def __init__(self, id_ferme, largeur, hauteur, type_zone="Zone",
                 etat="Non défini", culture="", nom="", historique=None):
        super().__init__(0, 0, largeur, hauteur)
        self.id_ferme = id_ferme
        self.type_zone = type_zone
        self.etat = etat
        self.culture = culture
        self.nom = nom or f"Zone {id_ferme}"
        # Passé cultural de la parcelle : liste de tuples ((debut, fin),
        # culture), distincte de `culture` (la culture actuellement en
        # place). Voir DialogHistoriqueParcelle et le docstring du module.
        self.historique = list(historique) if historique else []
        self.setFlags(
            QGraphicsRectItem.ItemIsMovable
            | QGraphicsRectItem.ItemIsSelectable
            | QGraphicsRectItem.ItemSendsGeometryChanges
        )
        self.setZValue(id_ferme)

    def definir_dimensions(self, largeur, hauteur):
        self.setRect(0, 0, max(5.0, largeur), max(5.0, hauteur))

    def boundingRect(self):
        # Marge couvrant la bordure la plus épaisse dessinée dans paint()
        # ainsi que le cadre de sélection (2 px) : sans cette marge, Qt ne
        # sait pas qu'il doit effacer ces pixels-là lors d'un déplacement,
        # ce qui laisse une traînée visuelle derrière l'objet déplacé.
        marge = 4
        return self.rect().adjusted(-marge, -marge, marge, marge)

    def paint(self, painter, option, widget=None):
        rect = self.rect()

        couleur_fond = QColor(COULEUR_PAR_ETAT.get(self.etat, "#e0e0e0"))
        couleur_fond.setAlpha(190)
        painter.setBrush(QBrush(couleur_fond))
        largeur_bord = EPAISSEUR_BORD_PAR_TYPE.get(self.type_zone, 1)
        couleur_bord = QColor(COULEUR_BORD_PAR_TYPE.get(self.type_zone, "#616161"))
        stylo_bord = QPen(couleur_bord, largeur_bord)
        stylo_bord.setCosmetic(True)  # épaisseur en pixels écran, constante quel que soit le zoom
        painter.setPen(stylo_bord)
        painter.drawRect(rect)

        if self.isSelected():
            stylo_selection = QPen(QColor("#e91e63"), 2, Qt.DashLine)
            stylo_selection.setCosmetic(True)
            painter.setPen(stylo_selection)
            painter.setBrush(Qt.NoBrush)
            # Pas de rect.adjusted(...) ici : un retrait exprimé en unités de
            # scène (et non en pixels écran) devient énorme une fois zoomé -
            # avec des planches de 1,30 m de haut en dimensions réelles, un
            # retrait de 2 unités de chaque côté rend le rectangle dégénéré
            # (hauteur négative) et le cadre de sélection ne correspond plus
            # du tout au rectangle sélectionné. Le stylo cosmétique dessine
            # déjà un trait d'épaisseur fixe à l'écran, quel que soit le
            # zoom : dessiner directement sur `rect` suffit à bien l'entourer.
            painter.drawRect(rect)

        if rect.width() > 30 and rect.height() > 16:
            stylo_texte = QPen(QColor("#212121"))
            stylo_texte.setCosmetic(True)
            painter.setPen(stylo_texte)
            police = painter.font()
            police.setPointSize(8)
            painter.setFont(police)
            texte = self.nom
            if self.culture:
                texte += f"\n{self.culture}"
            painter.drawText(rect.adjusted(4, 2, -4, -2),
                              Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap, texte)

    def resume(self):
        infos = [self.type_zone]
        if self.etat and self.etat != "Non défini":
            infos.append(self.etat)
        if self.culture:
            infos.append(self.culture)
        return f"{self.nom} ({', '.join(infos)})"


def supprimer_rectangle(scene, item):
    """Supprime un rectangle ET tout ce qui est emboîté dedans."""
    for enfant in list(item.childItems()):
        if isinstance(enfant, RectangleFerme):
            supprimer_rectangle(scene, enfant)
    scene.removeItem(item)


def _tous_les_rectangles(scene):
    return [it for it in scene.items() if isinstance(it, RectangleFerme)]


def sauvegarder_plan(path, scene, echelle_x=1.0, echelle_y=None):
    rects = []
    for item in _tous_les_rectangles(scene):
        parent = item.parentItem()
        rects.append({
            "id": item.id_ferme,
            "parent": parent.id_ferme if isinstance(parent, RectangleFerme) else 0,
            "nom": item.nom, "type": item.type_zone, "etat": item.etat, "culture": item.culture,
            "x": item.pos().x(), "y": item.pos().y(),
            "largeur": item.rect().width(), "hauteur": item.rect().height(),
            "historique": item.historique,
        })
    with open(path, "w", encoding="utf-8") as f:
        f.write(serialiser(rects, echelle_x, echelle_y))


def charger_plan(path, scene):
    """Vide la scène et recharge le plan depuis le fichier texte. Retourne
    (prochain_id, echelle_x, echelle_y) - prochain_id à utiliser pour les
    rectangles créés ensuite, echelle_x/echelle_y = mètres réels par unité
    de dessin en largeur/longueur et en hauteur (1.0 chacune si le fichier
    n'en déclare pas)."""
    with open(path, "r", encoding="utf-8") as f:
        texte = f.read()
    rects = deserialiser(texte)
    echelle_x, echelle_y = lire_echelles(texte)

    scene.clear()
    items_par_id = {}
    for r in rects:  # trié par id croissant : le parent existe toujours avant l'enfant
        item = RectangleFerme(r["id"], r["largeur"], r["hauteur"], r["type"], r["etat"],
                               r["culture"], r["nom"], r.get("historique", []))
        scene.addItem(item)
        if r["parent"] and r["parent"] in items_par_id:
            item.setParentItem(items_par_id[r["parent"]])
        item.setPos(r["x"], r["y"])
        items_par_id[r["id"]] = item
    return prochain_id(rects), echelle_x, echelle_y


# --------------------------------------------------------------- Dialogues
_JOURS_SEMAINE = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]
_MOIS_NOMS = ["Janvier", "Février", "Mars", "Avril", "Mai", "Juin", "Juillet",
              "Août", "Septembre", "Octobre", "Novembre", "Décembre"]


class DialogSelectionSemaine(QDialog):
    """Pop-up de sélection d'une semaine, affichée sous forme de calendrier
    mensuel semaine par semaine. Navigation rapide vers un mois donné via
    un combo (nom du mois) et un champ année, en plus des flèches ◀ ▶
    (mois précédent/suivant) et d'un bouton « Aujourd'hui ». Chaque ligne
    du tableau est une semaine complète du lundi au dimanche, il suffit de
    cliquer n'importe où sur la ligne pour choisir toute la semaine - plus
    adapté à un historique cultural (organisé en semaines, comme le reste
    de l'application, cf. semaine_debut/semaine_fin du planning cultural)
    qu'un sélecteur de date au jour près."""

    def __init__(self, parent=None, annee=None, mois=None, titre="Choisir une semaine"):
        super().__init__(parent)
        self.setWindowTitle(titre)
        self.resize(420, 340)
        aujourd_hui = datetime.date.today()
        self._annee = annee or aujourd_hui.year
        self._mois = mois or aujourd_hui.month
        self.semaine_choisie = None  # (annee_iso, semaine_iso, date_debut, date_fin)

        layout = QVBoxLayout(self)

        barre_nav = QHBoxLayout()
        btn_prec = QPushButton("◀")
        btn_prec.setFixedWidth(32)
        btn_prec.setToolTip("Mois précédent")
        btn_prec.clicked.connect(self._mois_precedent)
        barre_nav.addWidget(btn_prec)

        self.combo_mois = QComboBox()
        self.combo_mois.addItems(_MOIS_NOMS)
        self.combo_mois.setCurrentIndex(self._mois - 1)
        self.combo_mois.currentIndexChanged.connect(self._mois_ou_annee_change)
        barre_nav.addWidget(self.combo_mois, 1)

        self.spin_annee = QSpinBox()
        self.spin_annee.setRange(1900, 2100)
        self.spin_annee.setValue(self._annee)
        self.spin_annee.valueChanged.connect(self._mois_ou_annee_change)
        barre_nav.addWidget(self.spin_annee)

        btn_suiv = QPushButton("▶")
        btn_suiv.setFixedWidth(32)
        btn_suiv.setToolTip("Mois suivant")
        btn_suiv.clicked.connect(self._mois_suivant)
        barre_nav.addWidget(btn_suiv)

        btn_aujourd_hui = QPushButton("Aujourd'hui")
        btn_aujourd_hui.setToolTip("Revenir au mois en cours")
        btn_aujourd_hui.clicked.connect(self._aller_a_aujourd_hui)
        barre_nav.addWidget(btn_aujourd_hui)
        layout.addLayout(barre_nav)

        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(["Sem."] + _JOURS_SEMAINE)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemSelectionChanged.connect(self._maj_semaine_choisie)
        self.table.itemDoubleClicked.connect(self._valider_si_semaine)
        layout.addWidget(self.table, 1)

        self.label_selection = QLabel("Cliquez sur une semaine (n'importe quel jour de la ligne).")
        self.label_selection.setWordWrap(True)
        layout.addWidget(self.label_selection)

        boutons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.boutons = boutons
        boutons.accepted.connect(self.accept)
        boutons.rejected.connect(self.reject)
        boutons.button(QDialogButtonBox.Ok).setEnabled(False)
        layout.addWidget(boutons)

        self._remplir_mois()

    def _mois_precedent(self):
        self._mois -= 1
        if self._mois < 1:
            self._mois, self._annee = 12, self._annee - 1
        self._synchroniser_champs_navigation()

    def _mois_suivant(self):
        self._mois += 1
        if self._mois > 12:
            self._mois, self._annee = 1, self._annee + 1
        self._synchroniser_champs_navigation()

    def _aller_a_aujourd_hui(self):
        aujourd_hui = datetime.date.today()
        self._mois, self._annee = aujourd_hui.month, aujourd_hui.year
        self._synchroniser_champs_navigation()

    def _synchroniser_champs_navigation(self):
        """Répercute self._mois/self._annee (changés par ◀ ▶ ou
        « Aujourd'hui ») sur le combo mois et le spin année, sans
        déclencher une double actualisation via leurs signaux."""
        self.combo_mois.blockSignals(True)
        self.spin_annee.blockSignals(True)
        self.combo_mois.setCurrentIndex(self._mois - 1)
        self.spin_annee.setValue(self._annee)
        self.combo_mois.blockSignals(False)
        self.spin_annee.blockSignals(False)
        self._remplir_mois()

    def _mois_ou_annee_change(self, *_args):
        """Sélection directe du mois (combo) ou de l'année (spin) : plus
        rapide que de cliquer ◀ ▶ plusieurs fois pour naviguer loin dans
        le calendrier."""
        self._mois = self.combo_mois.currentIndex() + 1
        self._annee = self.spin_annee.value()
        self._remplir_mois()

    def _remplir_mois(self):
        semaines = calendar.Calendar(firstweekday=0).monthdatescalendar(self._annee, self._mois)
        self.table.setRowCount(len(semaines))
        for row, semaine in enumerate(semaines):
            annee_iso, semaine_iso, _ = semaine[0].isocalendar()
            item_semaine = QTableWidgetItem(f"S{semaine_iso:02d}")
            item_semaine.setData(Qt.UserRole, (annee_iso, semaine_iso, semaine[0], semaine[-1]))
            item_semaine.setTextAlignment(Qt.AlignCenter)
            item_semaine.setFlags(item_semaine.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 0, item_semaine)
            for col, jour in enumerate(semaine, start=1):
                item_jour = QTableWidgetItem(str(jour.day))
                item_jour.setTextAlignment(Qt.AlignCenter)
                item_jour.setFlags(item_jour.flags() & ~Qt.ItemIsEditable)
                if jour.month != self._mois:
                    item_jour.setForeground(QBrush(QColor("#b0b0b0")))
                if jour == datetime.date.today():
                    item_jour.setBackground(QBrush(QColor("#fff3cd")))
                self.table.setItem(row, col, item_jour)
        self.table.clearSelection()
        self.semaine_choisie = None
        self.boutons.button(QDialogButtonBox.Ok).setEnabled(False)
        self.label_selection.setText("Cliquez sur une semaine (n'importe quel jour de la ligne).")

    def _maj_semaine_choisie(self):
        lignes = self.table.selectionModel().selectedRows()
        if not lignes:
            self.semaine_choisie = None
            self.boutons.button(QDialogButtonBox.Ok).setEnabled(False)
            return
        item = self.table.item(lignes[0].row(), 0)
        annee_iso, semaine_iso, date_debut, date_fin = item.data(Qt.UserRole)
        self.semaine_choisie = (annee_iso, semaine_iso, date_debut, date_fin)
        self.label_selection.setText(
            f"Semaine {semaine_iso:02d} de {annee_iso} : du "
            f"{date_debut.strftime('%d/%m/%Y')} au {date_fin.strftime('%d/%m/%Y')}.")
        self.boutons.button(QDialogButtonBox.Ok).setEnabled(True)

    def _valider_si_semaine(self, *_args):
        if self.semaine_choisie is not None:
            self.accept()

    def texte_semaine(self):
        """Renvoie le texte à insérer dans un champ Début/Fin (ex.
        "Semaine 12/2023"), ou "" si aucune semaine n'a été choisie.
        Le texte inclut toujours l'année en 4 chiffres, exploitable par
        onglet_creation_planning._annee_depuis_texte pour le calcul du
        délai de retour entre cultures."""
        if self.semaine_choisie is None:
            return ""
        annee_iso, semaine_iso, _, _ = self.semaine_choisie
        return f"Semaine {semaine_iso:02d}/{annee_iso}"


class DialogHistoriqueParcelle(QDialog):
    """Pop-up d'édition du passé cultural d'une parcelle (zone, chapelle ou
    planche) : une liste de périodes passées, chacune associée à la
    culture qui y a été menée. Chaque ligne du tableau est une entrée
    ((debut, fin), culture) - début/fin en texte libre (année, saison ou
    date, au choix de l'utilisateur), peu importe l'ordre des lignes.

    Cet historique complet (et pas seulement la dernière culture connue)
    est ensuite exploité par le système de rotation de l'onglet "Création
    planning cultural" (voir onglet_creation_planning.score_rotation) pour
    appliquer un délai de retour propre à chaque culture passée, et pas
    seulement à la plus récente."""

    def __init__(self, parent=None, historique=None, cultures=None,
                 titre="Historique de la parcelle"):
        super().__init__(parent)
        self.setWindowTitle(titre)
        self.resize(560, 380)
        self._cultures = list(cultures or [])

        layout = QVBoxLayout(self)
        info = QLabel(
            "Renseignez les périodes passées de culture de cette parcelle (une ligne par "
            "période, dans l'ordre qui vous convient). Le début et la fin peuvent être saisis "
            "librement (année, saison, date...) ou choisis semaine par semaine via le bouton "
            "📅 - du moment qu'une année à 4 chiffres y apparaît si vous voulez que le délai de "
            "retour entre cultures soit calculé automatiquement.")
        info.setWordWrap(True)
        layout.addWidget(info)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Début", "Fin", "Culture"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        layout.addWidget(self.table, 1)

        for (debut, fin), culture_hist in (historique or []):
            self._ajouter_ligne(debut, fin, culture_hist)

        barre = QHBoxLayout()
        btn_ajouter = QPushButton("➕ Ajouter une période")
        btn_ajouter.clicked.connect(lambda: self._ajouter_ligne("", "", ""))
        barre.addWidget(btn_ajouter)
        btn_supprimer = QPushButton("🗑 Supprimer la ligne sélectionnée")
        btn_supprimer.clicked.connect(self._supprimer_ligne)
        barre.addWidget(btn_supprimer)
        barre.addStretch(1)
        layout.addLayout(barre)

        boutons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        boutons.accepted.connect(self.accept)
        boutons.rejected.connect(self.reject)
        layout.addWidget(boutons)

    def _ajouter_ligne(self, debut, fin, culture_hist):
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setCellWidget(row, 0, self._creer_champ_periode(debut))
        self.table.setCellWidget(row, 1, self._creer_champ_periode(fin))

        combo = QComboBox()
        combo.setEditable(True)
        combo.addItem("")
        combo.addItems(sorted(self._cultures))
        if self._cultures:
            completeur = QCompleter(sorted(self._cultures))
            completeur.setCaseSensitivity(Qt.CaseInsensitive)
            combo.setCompleter(completeur)
        if culture_hist:
            combo.setCurrentText(culture_hist)
        self.table.setCellWidget(row, 2, combo)

    def _creer_champ_periode(self, valeur):
        """Cellule Début/Fin : un champ texte libre (toujours modifiable à
        la main) accompagné d'un bouton 📅 qui ouvre un calendrier
        mensuel semaine par semaine (DialogSelectionSemaine) pour remplir
        le champ sans avoir à taper la date."""
        conteneur = QWidget()
        h = QHBoxLayout(conteneur)
        h.setContentsMargins(2, 0, 2, 0)
        edit = QLineEdit(str(valeur))
        h.addWidget(edit)
        btn = QPushButton("📅")
        btn.setFixedWidth(28)
        btn.setToolTip("Choisir une semaine dans un calendrier")
        btn.clicked.connect(lambda: self._choisir_semaine(edit))
        h.addWidget(btn)
        conteneur.champ_texte = edit
        return conteneur

    def _choisir_semaine(self, edit):
        annee = None
        m = re.search(r"(\d{4})", edit.text())
        if m:
            annee = int(m.group(1))
        dialog = DialogSelectionSemaine(self, annee=annee, titre="Choisir une semaine")
        if dialog.exec_() == dialog.Accepted:
            edit.setText(dialog.texte_semaine())

    def _supprimer_ligne(self):
        lignes = sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True)
        for r in lignes:
            self.table.removeRow(r)

    def valeurs(self):
        """Renvoie la liste ((debut, fin), culture) - les lignes sans nom de
        culture sont ignorées."""
        resultats = []
        for row in range(self.table.rowCount()):
            widget_debut = self.table.cellWidget(row, 0)
            widget_fin = self.table.cellWidget(row, 1)
            combo = self.table.cellWidget(row, 2)
            debut = widget_debut.champ_texte.text().strip() if widget_debut else ""
            fin = widget_fin.champ_texte.text().strip() if widget_fin else ""
            culture_hist = combo.currentText().strip() if combo else ""
            if not culture_hist:
                continue
            resultats.append(((debut, fin), culture_hist))
        return resultats


class DialogProprietesRect(QDialog):
    """Pop-up d'édition (nom, type, état, culture, position, dimensions,
    historique) d'un seul rectangle."""

    def __init__(self, parent=None, valeurs=None, cultures=None, titre="Propriétés du rectangle",
                 echelle_x=1.0, echelle_y=None):
        super().__init__(parent)
        self.setWindowTitle(titre)
        valeurs = valeurs or {}
        self._cultures = cultures
        self._echelle_x = echelle_x
        self._echelle_y = echelle_y if echelle_y is not None else echelle_x
        self.historique = list(valeurs.get("historique", []) or [])

        layout = QVBoxLayout(self)
        form = QFormLayout()
        layout.addLayout(form)

        self.edit_nom = QLineEdit(valeurs.get("nom", ""))
        form.addRow("Nom :", self.edit_nom)

        self.cb_type = QComboBox()
        self.cb_type.addItems(TYPES_ZONE)
        i = self.cb_type.findText(valeurs.get("type", "Zone"))
        self.cb_type.setCurrentIndex(max(0, i))
        form.addRow("Type :", self.cb_type)

        self.cb_etat = QComboBox()
        self.cb_etat.addItems(ETATS)
        i = self.cb_etat.findText(valeurs.get("etat", "Non défini"))
        self.cb_etat.setCurrentIndex(max(0, i))
        form.addRow("État :", self.cb_etat)

        self.edit_culture = QLineEdit(valeurs.get("culture", ""))
        if cultures:
            completeur = QCompleter(sorted(cultures))
            completeur.setCaseSensitivity(Qt.CaseInsensitive)
            self.edit_culture.setCompleter(completeur)
        form.addRow("Culture :", self.edit_culture)

        self.spin_x = self._creer_spin(valeurs.get("x", 0.0))
        form.addRow("Position X :", self.spin_x)
        self.spin_y = self._creer_spin(valeurs.get("y", 0.0))
        form.addRow("Position Y :", self.spin_y)
        self.spin_largeur = self._creer_spin(valeurs.get("largeur", 40.0), minimum=5.0)
        form.addRow("Largeur :", self.spin_largeur)
        self.spin_hauteur = self._creer_spin(valeurs.get("hauteur", 40.0), minimum=5.0)
        form.addRow("Hauteur :", self.spin_hauteur)

        self.lbl_surface = QLabel("")
        self.lbl_surface.setStyleSheet("font-weight: bold;")
        self.spin_largeur.valueChanged.connect(self._maj_surface)
        self.spin_hauteur.valueChanged.connect(self._maj_surface)
        self._maj_surface()
        form.addRow("Surface réelle :", self.lbl_surface)

        ligne_historique = QHBoxLayout()
        self.label_historique = QLabel("")
        self._maj_label_historique()
        ligne_historique.addWidget(self.label_historique, 1)
        btn_historique = QPushButton("📜 Historique de la parcelle...")
        btn_historique.setToolTip(
            "Renseigner les cultures passées de cette parcelle (période + culture), "
            "utilisées par le système de rotation pour appliquer le bon délai de "
            "retour à chacune, pas seulement à la dernière culture connue.")
        btn_historique.clicked.connect(self._editer_historique)
        ligne_historique.addWidget(btn_historique)
        form.addRow("Historique :", ligne_historique)

        boutons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        boutons.accepted.connect(self.accept)
        boutons.rejected.connect(self.reject)
        layout.addWidget(boutons)

    def _maj_label_historique(self):
        n = len(self.historique)
        self.label_historique.setText(f"{n} période(s) enregistrée(s)" if n else "Aucune période enregistrée")

    def _maj_surface(self):
        surface = surface_m2(self.spin_largeur.value(), self.spin_hauteur.value(),
                              self._echelle_x, self._echelle_y)
        self.lbl_surface.setText(f"{surface:,.1f} m²".replace(",", " "))

    def _editer_historique(self):
        dialog = DialogHistoriqueParcelle(
            self, historique=self.historique, cultures=self._cultures,
            titre=f"Historique — {self.windowTitle()}")
        if dialog.exec_() == dialog.Accepted:
            self.historique = dialog.valeurs()
            self._maj_label_historique()

    @staticmethod
    def _creer_spin(valeur, minimum=-100000.0):
        spin = QDoubleSpinBox()
        spin.setRange(minimum, 100000.0)
        spin.setDecimals(1)
        spin.setValue(valeur)
        return spin

    def valeurs(self):
        return {
            "nom": self.edit_nom.text().strip() or "Sans nom",
            "type": self.cb_type.currentText(),
            "etat": self.cb_etat.currentText(),
            "culture": self.edit_culture.text().strip(),
            "x": self.spin_x.value(),
            "y": self.spin_y.value(),
            "largeur": self.spin_largeur.value(),
            "hauteur": self.spin_hauteur.value(),
            "historique": self.historique,
        }


class DialogRectsMultiples(QDialog):
    """Pop-up de paramétrage avant de dessiner plusieurs rectangles
    d'affilée (une ligne de planches par exemple), avec espacement régulier."""

    def __init__(self, parent=None, cultures=None, echelle_x=1.0, echelle_y=None):
        super().__init__(parent)
        self.setWindowTitle("Dessiner plusieurs rectangles")
        self._echelle_x = echelle_x
        self._echelle_y = echelle_y if echelle_y is not None else echelle_x

        layout = QVBoxLayout(self)
        info = QLabel("Après validation, cliquez sur le plan pour poser le coin\n"
                       "haut-gauche de la série de rectangles.")
        info.setWordWrap(True)
        layout.addWidget(info)

        form = QFormLayout()
        layout.addLayout(form)

        self.spin_lignes = QSpinBox()
        self.spin_lignes.setRange(1, 50)
        self.spin_lignes.setValue(1)
        form.addRow("Nombre de lignes :", self.spin_lignes)

        self.spin_colonnes = QSpinBox()
        self.spin_colonnes.setRange(1, 50)
        self.spin_colonnes.setValue(4)
        form.addRow("Nombre de colonnes :", self.spin_colonnes)

        self.spin_largeur = QDoubleSpinBox()
        self.spin_largeur.setRange(1.0, 10000.0)
        self.spin_largeur.setValue(40.0)
        form.addRow("Largeur d'un rectangle :", self.spin_largeur)

        self.spin_hauteur = QDoubleSpinBox()
        self.spin_hauteur.setRange(1.0, 10000.0)
        self.spin_hauteur.setValue(100.0)
        form.addRow("Hauteur d'un rectangle :", self.spin_hauteur)

        self.lbl_surface_multi = QLabel("")
        self.lbl_surface_multi.setStyleSheet("font-weight: bold;")
        self.spin_largeur.valueChanged.connect(self._maj_surface_multi)
        self.spin_hauteur.valueChanged.connect(self._maj_surface_multi)
        form.addRow("Surface réelle (par rectangle) :", self.lbl_surface_multi)

        self.spin_espacement_h = QDoubleSpinBox()
        self.spin_espacement_h.setRange(0.0, 10000.0)
        self.spin_espacement_h.setValue(10.0)
        form.addRow("Espacement horizontal :", self.spin_espacement_h)

        self.spin_espacement_v = QDoubleSpinBox()
        self.spin_espacement_v.setRange(0.0, 10000.0)
        self.spin_espacement_v.setValue(10.0)
        form.addRow("Espacement vertical :", self.spin_espacement_v)

        self.edit_prefixe = QLineEdit("Planche")
        form.addRow("Préfixe du nom :", self.edit_prefixe)

        self.cb_type = QComboBox()
        self.cb_type.addItems(TYPES_ZONE)
        self.cb_type.setCurrentIndex(TYPES_ZONE.index("Planche"))
        form.addRow("Type :", self.cb_type)

        self.cb_etat = QComboBox()
        self.cb_etat.addItems(ETATS)
        form.addRow("État :", self.cb_etat)

        self.edit_culture = QLineEdit()
        if cultures:
            completeur = QCompleter(sorted(cultures))
            completeur.setCaseSensitivity(Qt.CaseInsensitive)
            self.edit_culture.setCompleter(completeur)
        form.addRow("Culture (optionnel) :", self.edit_culture)

        boutons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        boutons.accepted.connect(self.accept)
        boutons.rejected.connect(self.reject)
        layout.addWidget(boutons)

        self._maj_surface_multi()

    def _maj_surface_multi(self):
        surface = surface_m2(self.spin_largeur.value(), self.spin_hauteur.value(),
                              self._echelle_x, self._echelle_y)
        self.lbl_surface_multi.setText(f"{surface:,.1f} m²".replace(",", " "))

    def valeurs(self):
        return {
            "lignes": self.spin_lignes.value(),
            "colonnes": self.spin_colonnes.value(),
            "largeur": self.spin_largeur.value(),
            "hauteur": self.spin_hauteur.value(),
            "espacement_h": self.spin_espacement_h.value(),
            "espacement_v": self.spin_espacement_v.value(),
            "prefixe": self.edit_prefixe.text().strip() or "Rect",
            "type": self.cb_type.currentText(),
            "etat": self.cb_etat.currentText(),
            "culture": self.edit_culture.text().strip(),
        }


# ------------------------------------------------------------------ Vue
class CommandeDeplacement(QUndoCommand):
    """Commande annulable (Ctrl+Z) représentant le déplacement d'un ou
    plusieurs rectangles (glisser-déposer). `deplacements` est une liste
    de tuples (item, ancienne_position, nouvelle_position), toutes deux en
    coordonnées du parent (QPointF, comme item.pos())."""

    def __init__(self, deplacements, description="Déplacer"):
        super().__init__(description)
        self.deplacements = deplacements

    def undo(self):
        for item, ancienne_pos, _ in self.deplacements:
            item.setPos(ancienne_pos)

    def redo(self):
        for item, _, nouvelle_pos in self.deplacements:
            item.setPos(nouvelle_pos)


class VueFerme(QGraphicsView):
    """QGraphicsView spécialisée : gère les modes "sélection" (déplacer /
    sélectionner, avec rubber-band), "dessiner" (clic-glisser pour tracer
    un rectangle) et "dessiner plusieurs" (un clic pose une série de
    rectangles espacés régulièrement, calculée par
    generer_grille_rectangles)."""

    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self.setRenderHint(QPainter.Antialiasing)
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self.mode = "select"
        # Panning à la souris (clic-glisser sur le fond) plutôt qu'un cadre
        # de sélection multiple (rubber band, qui n'est utilisé nulle part
        # ailleurs dans l'application) : indispensable pour se déplacer sur
        # un plan en dimensions réelles pouvant s'étendre sur des centaines
        # de mètres. Cliquer-glisser directement sur un rectangle continue
        # de le déplacer normalement (ScrollHandDrag ne panoramique que
        # lorsque le clic démarre sur une zone vide de la scène).
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self._debut_dessin = None
        self._rect_previsualisation = None
        self._prochain_id = 1
        self.parametres_multi = None
        self._positions_avant_deplacement = {}
        self._rect_accueil = None

        # Historique annulable (Ctrl+Z / Ctrl+Maj+Z) pour les déplacements
        # de rectangles à la souris.
        self.undo_stack = QUndoStack(self)
        QShortcut(QKeySequence.Undo, self, activated=self.undo_stack.undo)
        QShortcut(QKeySequence.Redo, self, activated=self.undo_stack.redo)

        # Callbacks (fonctions Python simples assignées par la fenêtre principale)
        self.callback_nouveau_rect = None      # appelé après un dessin simple
        self.callback_rects_multi_crees = None  # appelé après la pose d'une série
        self.callback_edition = None           # appelé sur double-clic
        self.callback_mode_change = None       # appelé à chaque changement de mode

    def prochain_id(self):
        n = self._prochain_id
        self._prochain_id += 1
        return n

    def resynchroniser_prochain_id(self):
        rects = _tous_les_rectangles(self.scene())
        self._prochain_id = (max((r.id_ferme for r in rects), default=0)) + 1

    def definir_mode(self, mode):
        self.mode = mode
        self.setDragMode(QGraphicsView.ScrollHandDrag if mode == "select" else QGraphicsView.NoDrag)
        if self.callback_mode_change:
            self.callback_mode_change(mode)

    def ajuster_a_la_vue(self):
        """Recentre et redimensionne le zoom pour que l'ensemble du plan
        tienne dans la fenêtre visible, et redéfinit la zone de la scène
        avec une marge généreuse autour du contenu.

        Indispensable après le chargement d'un plan en dimensions réelles
        (mètres) : sans le redimensionnement du zoom, des planches de
        1,30 m de large s'affichent à peine plus épaisses qu'un trait,
        quasiment invisibles à l'échelle 1 unité = 1 pixel utilisée par
        défaut par QGraphicsView. Sans la marge autour de la sceneRect, le
        défilement (notamment en mode zoomé) se bloque net contre le bord
        de la scène dès qu'on approche de x=0 ou y=0 - une sceneRect
        strictement ajustée au contenu ne laisse aucune place pour
        continuer à glisser au-delà de son bord."""
        rect = self.scene().itemsBoundingRect()
        if rect.isEmpty():
            return
        marge_scene = max(rect.width(), rect.height())  # marge généreuse (~100% de la taille du plan)
        self.scene().setSceneRect(rect.adjusted(-marge_scene, -marge_scene, marge_scene, marge_scene))

        marge_zoom = max(rect.width(), rect.height()) * 0.05 or 1.0
        rect_zoom = rect.adjusted(-marge_zoom, -marge_zoom, marge_zoom, marge_zoom)
        self.fitInView(rect_zoom, Qt.KeepAspectRatio)
        self._rect_accueil = rect_zoom

    def revenir_a_l_accueil(self):
        """Bouton "Home" : revient à la vue précalculée lors du dernier
        ajuster_a_la_vue() (typiquement juste après un chargement), sans
        avoir à recalculer les limites du contenu à chaque clic."""
        rect_accueil = getattr(self, "_rect_accueil", None)
        if rect_accueil is None:
            self.ajuster_a_la_vue()
        else:
            self.fitInView(rect_accueil, Qt.KeepAspectRatio)

    # ---------------------------------------------------------- création
    def _rects_existants_scene(self):
        resultats = []
        for item in _tous_les_rectangles(self.scene()):
            br = item.sceneBoundingRect()
            resultats.append({"id": item.id_ferme, "x_scene": br.x(), "y_scene": br.y(),
                               "largeur": br.width(), "hauteur": br.height(), "_item": item})
        return resultats

    def _creer_rectangle(self, x, y, largeur, hauteur, type_zone="Zone",
                          etat="Non défini", culture="", nom=None, historique=None):
        existants = self._rects_existants_scene()
        parent_id = trouver_meilleur_parent((x, y, largeur, hauteur), existants)

        id_ = self.prochain_id()
        nom = nom or f"Zone {id_}"
        item = RectangleFerme(id_, largeur, hauteur, type_zone, etat, culture, nom, historique)
        self.scene().addItem(item)

        if parent_id is not None:
            parent_item = next(r["_item"] for r in existants if r["id"] == parent_id)
            item.setParentItem(parent_item)
            item.setPos(parent_item.mapFromScene(QPointF(x, y)))
        else:
            item.setPos(QPointF(x, y))
        return item

    def _creer_grille_a(self, point_ancre):
        p = self.parametres_multi
        if not p:
            return
        positions = generer_grille_rectangles(
            point_ancre.x(), point_ancre.y(), p["lignes"], p["colonnes"],
            p["largeur"], p["hauteur"], p["espacement_h"], p["espacement_v"])
        crees = []
        for k, (x, y, w, h) in enumerate(positions, start=1):
            nom = f"{p['prefixe']} {k}"
            item = self._creer_rectangle(x, y, w, h, p["type"], p["etat"], p["culture"], nom)
            crees.append(item)
        if self.callback_rects_multi_crees:
            self.callback_rects_multi_crees(crees)

    # ------------------------------------------------------ événements souris
    def mousePressEvent(self, event):
        if self.mode == "draw" and event.button() == Qt.LeftButton:
            self._debut_dessin = self.mapToScene(event.pos())
            self._rect_previsualisation = QGraphicsRectItem(QRectF(self._debut_dessin, self._debut_dessin))
            self._rect_previsualisation.setPen(QPen(QColor(COULEUR_ACCENT_PF), 1, Qt.DashLine))
            self.scene().addItem(self._rect_previsualisation)
            return
        if self.mode == "draw_multi" and event.button() == Qt.LeftButton:
            point = self.mapToScene(event.pos())
            self._creer_grille_a(point)
            self.definir_mode("select")
            return
        super().mousePressEvent(event)
        if self.mode == "select" and event.button() == Qt.LeftButton:
            # Position de départ de chaque rectangle potentiellement en
            # cours de déplacement (la sélection est déjà à jour après
            # l'appel à super() ci-dessus), pour permettre le Ctrl+Z.
            self._positions_avant_deplacement = {
                item: item.pos() for item in self.scene().selectedItems()
                if isinstance(item, RectangleFerme)}

    def mouseMoveEvent(self, event):
        if self.mode == "draw" and self._rect_previsualisation is not None:
            fin = self.mapToScene(event.pos())
            self._rect_previsualisation.setRect(QRectF(self._debut_dessin, fin).normalized())
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.mode == "draw" and self._rect_previsualisation is not None:
            rect = self._rect_previsualisation.rect().normalized()
            self.scene().removeItem(self._rect_previsualisation)
            self._rect_previsualisation = None
            if rect.width() >= 5 and rect.height() >= 5:
                item = self._creer_rectangle(rect.x(), rect.y(), rect.width(), rect.height())
                if self.callback_nouveau_rect:
                    self.callback_nouveau_rect(item)
            self.definir_mode("select")
            return
        super().mouseReleaseEvent(event)
        if self.mode == "select" and event.button() == Qt.LeftButton and self._positions_avant_deplacement:
            deplacements = [
                (item, ancienne_pos, item.pos())
                for item, ancienne_pos in self._positions_avant_deplacement.items()
                if (item.pos() - ancienne_pos).manhattanLength() > 0.01]
            if deplacements:
                self.undo_stack.push(CommandeDeplacement(deplacements))
            self._positions_avant_deplacement = {}

    def mouseDoubleClickEvent(self, event):
        item = self.itemAt(event.pos())
        while item is not None and not isinstance(item, RectangleFerme):
            item = item.parentItem()
        if isinstance(item, RectangleFerme) and self.callback_edition:
            self.callback_edition(item)
            return
        super().mouseDoubleClickEvent(event)

    def wheelEvent(self, event):
        facteur = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.scale(facteur, facteur)
