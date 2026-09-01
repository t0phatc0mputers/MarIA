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
    ECHELLE 1.0

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

`parent=0` signifie "pas de parent" (rectangle racine, coordonnées dans le
repère de la scène). Pour un rectangle emboîté, x/y sont exprimés dans le
repère local du parent (0,0 = coin haut-gauche du parent) — c'est
exactement la convention utilisée par QGraphicsItem, ce qui simplifie
beaucoup le code d'affichage.

`ECHELLE` (optionnelle, valeur = mètres réels par unité de dessin,
1.0 par défaut) permet d'interpréter largeur/hauteur/x/y comme des
mesures réelles - utilisé notamment pour calculer la surface (m²) de
chaque planche. Absente d'un fichier, elle vaut 1.0 (comportement
historique : 1 unité = 1 mètre).
"""

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
CHAMPS = ["nom", "type", "etat", "culture", "x", "y", "largeur", "hauteur"]


def serialiser(rects, echelle=1.0):
    """rects : liste de dicts {id, parent, nom, type, etat, culture,
    x, y, largeur, hauteur}. `echelle` : nombre de mètres réels que
    représente 1 unité de dessin (par défaut 1.0, donc 1 unité = 1 m).
    Retourne le texte du fichier."""
    lignes = ["PLAN_FERME 1", f"ECHELLE {echelle}", ""]
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
        lignes.append("")
    return "\n".join(lignes) + "\n"


def _echapper(texte):
    return str(texte).replace("\n", " ").replace("\r", " ")


_RE_RECT = re.compile(r"^RECT\s+id=(\d+)\s+parent=(\d+)\s*$")
_RE_ECHELLE = re.compile(r"^ECHELLE\s+([0-9.,]+)\s*$")


def lire_echelle(texte):
    """Renvoie l'échelle (mètres réels par unité de dessin) déclarée en
    tête du fichier, ou 1.0 si absente - comportement historique pour les
    fichiers créés avant l'introduction de l'échelle (1 unité = 1 mètre)."""
    for brute in texte.splitlines():
        m = _RE_ECHELLE.match(brute.strip())
        if m:
            try:
                return float(m.group(1).replace(",", "."))
            except ValueError:
                return 1.0
    return 1.0


def deserialiser(texte):
    """Analyse le texte d'un fichier .plan et retourne une liste de dicts
    {id, parent, nom, type, etat, culture, x, y, largeur, hauteur}
    triée par id croissant. Lève ValueError si le format est invalide."""
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
                       "largeur": 10.0, "hauteur": 10.0}
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

    return [rects[i] for i in sorted(rects)]


def surface_m2(largeur, hauteur, echelle=1.0):
    """Surface réelle (m²) d'un rectangle dessiné avec largeur/hauteur en
    unités de dessin, compte tenu de l'échelle (mètres réels par unité —
    voir lire_echelle). La surface est en unités² donc l'échelle
    s'applique au carré."""
    return largeur * hauteur * (echelle ** 2)


def prochain_id(rects):
    if not rects:
        return 1
    return max(r["id"] for r in rects) + 1


# ====================================================================
# Partie PyQt : éditeur graphique
# ====================================================================
from PyQt5.QtCore import Qt, QRectF, QPointF
from PyQt5.QtGui import QColor, QBrush, QPen, QPainter
from PyQt5.QtWidgets import (
    QGraphicsRectItem, QGraphicsView, QGraphicsScene, QDialog, QDialogButtonBox,
    QSpinBox, QDoubleSpinBox, QComboBox, QLineEdit, QLabel, QFormLayout,
    QVBoxLayout, QHBoxLayout, QCompleter, QMessageBox,
)


class RectangleFerme(QGraphicsRectItem):
    """Un rectangle du plan de ferme (zone, chapelle ou planche). Les
    rectangles peuvent être emboîtés via le mécanisme standard de parenté
    de QGraphicsItem : setParentItem(...) + setPos(...) en coordonnées du
    parent — déplacer un rectangle déplace donc automatiquement tout ce
    qui est emboîté dedans."""

    def __init__(self, id_ferme, largeur, hauteur, type_zone="Zone",
                 etat="Non défini", culture="", nom=""):
        super().__init__(0, 0, largeur, hauteur)
        self.id_ferme = id_ferme
        self.type_zone = type_zone
        self.etat = etat
        self.culture = culture
        self.nom = nom or f"Zone {id_ferme}"
        self.setFlags(
            QGraphicsRectItem.ItemIsMovable
            | QGraphicsRectItem.ItemIsSelectable
            | QGraphicsRectItem.ItemSendsGeometryChanges
        )
        self.setZValue(id_ferme)

    def definir_dimensions(self, largeur, hauteur):
        self.setRect(0, 0, max(5.0, largeur), max(5.0, hauteur))

    def paint(self, painter, option, widget=None):
        rect = self.rect()

        couleur_fond = QColor(COULEUR_PAR_ETAT.get(self.etat, "#e0e0e0"))
        couleur_fond.setAlpha(190)
        painter.setBrush(QBrush(couleur_fond))
        largeur_bord = EPAISSEUR_BORD_PAR_TYPE.get(self.type_zone, 1)
        couleur_bord = QColor(COULEUR_BORD_PAR_TYPE.get(self.type_zone, "#616161"))
        painter.setPen(QPen(couleur_bord, largeur_bord))
        painter.drawRect(rect)

        if self.isSelected():
            painter.setPen(QPen(QColor("#e91e63"), 2, Qt.DashLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(rect.adjusted(2, 2, -2, -2))

        if rect.width() > 30 and rect.height() > 16:
            painter.setPen(QPen(QColor("#212121")))
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


def sauvegarder_plan(path, scene, echelle=1.0):
    rects = []
    for item in _tous_les_rectangles(scene):
        parent = item.parentItem()
        rects.append({
            "id": item.id_ferme,
            "parent": parent.id_ferme if isinstance(parent, RectangleFerme) else 0,
            "nom": item.nom, "type": item.type_zone, "etat": item.etat, "culture": item.culture,
            "x": item.pos().x(), "y": item.pos().y(),
            "largeur": item.rect().width(), "hauteur": item.rect().height(),
        })
    with open(path, "w", encoding="utf-8") as f:
        f.write(serialiser(rects, echelle))


def charger_plan(path, scene):
    """Vide la scène et recharge le plan depuis le fichier texte. Retourne
    (prochain_id, echelle) - prochain_id à utiliser pour les rectangles
    créés ensuite, echelle = mètres réels par unité de dessin (1.0 si le
    fichier n'en déclare pas)."""
    with open(path, "r", encoding="utf-8") as f:
        texte = f.read()
    rects = deserialiser(texte)
    echelle = lire_echelle(texte)

    scene.clear()
    items_par_id = {}
    for r in rects:  # trié par id croissant : le parent existe toujours avant l'enfant
        item = RectangleFerme(r["id"], r["largeur"], r["hauteur"], r["type"], r["etat"],
                               r["culture"], r["nom"])
        scene.addItem(item)
        if r["parent"] and r["parent"] in items_par_id:
            item.setParentItem(items_par_id[r["parent"]])
        item.setPos(r["x"], r["y"])
        items_par_id[r["id"]] = item
    return prochain_id(rects), echelle


# --------------------------------------------------------------- Dialogues
class DialogProprietesRect(QDialog):
    """Pop-up d'édition (nom, type, état, culture, position, dimensions)
    d'un seul rectangle."""

    def __init__(self, parent=None, valeurs=None, cultures=None, titre="Propriétés du rectangle"):
        super().__init__(parent)
        self.setWindowTitle(titre)
        valeurs = valeurs or {}

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

        boutons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        boutons.accepted.connect(self.accept)
        boutons.rejected.connect(self.reject)
        layout.addWidget(boutons)

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
        }


class DialogRectsMultiples(QDialog):
    """Pop-up de paramétrage avant de dessiner plusieurs rectangles
    d'affilée (une ligne de planches par exemple), avec espacement régulier."""

    def __init__(self, parent=None, cultures=None):
        super().__init__(parent)
        self.setWindowTitle("Dessiner plusieurs rectangles")

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
class VueFerme(QGraphicsView):
    """QGraphicsView spécialisée : gère les modes "sélection" (déplacer /
    sélectionner, avec rubber-band), "dessiner" (clic-glisser pour tracer
    un rectangle) et "dessiner plusieurs" (un clic pose une série de
    rectangles espacés régulièrement, calculée par
    generer_grille_rectangles)."""

    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self.setRenderHint(QPainter.Antialiasing)
        self.mode = "select"
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self._debut_dessin = None
        self._rect_previsualisation = None
        self._prochain_id = 1
        self.parametres_multi = None

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
        self.setDragMode(QGraphicsView.RubberBandDrag if mode == "select" else QGraphicsView.NoDrag)
        if self.callback_mode_change:
            self.callback_mode_change(mode)

    # ---------------------------------------------------------- création
    def _rects_existants_scene(self):
        resultats = []
        for item in _tous_les_rectangles(self.scene()):
            br = item.sceneBoundingRect()
            resultats.append({"id": item.id_ferme, "x_scene": br.x(), "y_scene": br.y(),
                               "largeur": br.width(), "hauteur": br.height(), "_item": item})
        return resultats

    def _creer_rectangle(self, x, y, largeur, hauteur, type_zone="Zone",
                          etat="Non défini", culture="", nom=None):
        existants = self._rects_existants_scene()
        parent_id = trouver_meilleur_parent((x, y, largeur, hauteur), existants)

        id_ = self.prochain_id()
        nom = nom or f"Zone {id_}"
        item = RectangleFerme(id_, largeur, hauteur, type_zone, etat, culture, nom)
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
