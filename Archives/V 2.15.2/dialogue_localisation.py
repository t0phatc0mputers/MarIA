# -*- coding: utf-8 -*-
"""
dialogue_localisation.py
---------------------------
Pop-up "Choisir une localisation" : plusieurs façons de retrouver la ville /
station Météociel voulue, sans avoir à en connaître le nom exact (avec code
postal) attendu par Météociel - ce qui provoque sinon une erreur "plusieurs
villes correspondent" (ou pire, une sélection silencieuse d'une homonyme d'un
autre pays) quand on tape juste un nom de ville dans les champs habituels.

  1. Onglet "🔤 Recherche par nom" : taper le début d'un nom de ville et
     choisir dans la liste qui défile, filtrée aux seules villes françaises
     et affichant le code postal quand il est connu (voir
     geolocalisation_stations.rechercher_villes).
  2. Onglet "🗺️ Carte interactive" : cliquer sur un point de la carte de
     France (nécessite le paquet PyQtWebEngine - voir WEBENGINE_DISPONIBLE).
  3. Onglet "📍 Coordonnées GPS" : saisir directement une latitude/longitude
     (utilisable même sans PyQtWebEngine, ex. copiées depuis une autre
     application de cartographie).

Dans les deux derniers cas, les stations les plus proches (parmi celles pour
lesquelles une position GPS est connue - voir geolocalisation_stations.py)
sont calculées localement (distance orthodromique), sans appel réseau : la
liste s'affiche instantanément, l'utilisateur choisit celle qu'il veut
utiliser (la plus proche n'est pas toujours la plus adaptée - une station
"amateur" peut être hors service, une station "secondaire" un peu plus
loin peut être préférable) puis valide.

Dans tous les cas, le résultat renvoyé par ``choisir_localisation`` inclut
l'identifiant Météociel de la ville choisie (``city_id``, celui de
cities_database.json) quand il est connu - à utiliser en priorité pour
interroger Météociel (voir meteo_decision.py, paramètre ``ville_id`` de
``recommander`` / ``recuperer_previsions`` / ``recuperer_historique``),
plus fiable qu'une recherche par nom (voir la docstring de ces fonctions
et de geolocalisation_stations.py pour le détail).

Utilisation typique, ailleurs dans l'application :

    import dialogue_localisation as dl
    resultat = dl.choisir_localisation(self)   # self = fenêtre parente
    if resultat:
        self.edit_dec_ville.setText(resultat["nom"])
        self.edit_dec_ville.setProperty("meteociel_id", resultat["id"])
"""

import os
import tempfile

from PyQt5.QtCore import Qt, QObject, QUrl, pyqtSignal, pyqtSlot
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLabel, QDoubleSpinBox,
    QPushButton, QListWidget, QListWidgetItem, QDialogButtonBox, QTabWidget,
    QWidget, QMessageBox, QLineEdit,
)

try:
    from PyQt5.QtWebEngineWidgets import QWebEngineView
    from PyQt5.QtWebChannel import QWebChannel
    WEBENGINE_DISPONIBLE = True
    WEBENGINE_IMPORT_ERROR = None
except ImportError as exc:  # pragma: no cover
    WEBENGINE_DISPONIBLE = False
    WEBENGINE_IMPORT_ERROR = exc

import geolocalisation_stations as gs
import carte_localisation as cl


class Pont(QObject):
    """Petit objet exposé au JavaScript de la carte via QWebChannel : reçoit
    les coordonnées du point cliqué (voir carte_localisation._SCRIPT_PONT)
    et les retransmet en signal Qt classique, consommable côté widget."""

    point_clique = pyqtSignal(float, float)

    @pyqtSlot(float, float)
    def point_choisi(self, lat, lon):
        self.point_clique.emit(lat, lon)


class DialogueChoixLocalisation(QDialog):
    """Pop-up permettant de retrouver la station Météociel la plus proche
    d'un lieu, par clic sur une carte ou par saisie de coordonnées GPS."""

    def __init__(self, parent=None, titre="Choisir une localisation"):
        super().__init__(parent)
        self.setWindowTitle(titre)
        self.resize(760, 580)

        layout = QVBoxLayout(self)

        if not gs.stations_disponibles():
            avert = QLabel(
                "⚠ Données de géolocalisation des stations introuvables "
                "(fichiers cities_database.json / stations_gps.json absents "
                "du dossier de l'application). La recherche ci-dessous ne "
                "renverra aucun résultat."
            )
            avert.setWordWrap(True)
            avert.setStyleSheet("color: #b71c1c;")
            layout.addWidget(avert)

        onglets = QTabWidget()
        layout.addWidget(onglets, 1)

        self._construire_onglet_recherche_nom(onglets)
        self._construire_onglet_carte(onglets)
        self._construire_onglet_gps(onglets)

        layout.addWidget(QLabel("Résultats (ville la plus proche, ou correspondant à la recherche) :"))
        self.liste_resultats = QListWidget()
        self.liste_resultats.itemSelectionChanged.connect(self._maj_bouton_ok)
        layout.addWidget(self.liste_resultats, 1)

        boutons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.bouton_ok = boutons.button(QDialogButtonBox.Ok)
        self.bouton_ok.setEnabled(False)
        boutons.accepted.connect(self.accept)
        boutons.rejected.connect(self.reject)
        layout.addWidget(boutons)

    # ------------------------------------------------------------------
    # Onglet "Recherche par nom"
    # ------------------------------------------------------------------
    def _construire_onglet_recherche_nom(self, onglets):
        onglet = QWidget()
        l = QVBoxLayout(onglet)
        l.addWidget(QLabel(
            "Tapez le début d'un nom de ville : la liste des villes françaises "
            "correspondantes s'affiche ci-dessous, avec le code postal quand il "
            "est connu (pratique si le nom seul correspond à plusieurs communes, "
            "ou pour éviter une homonyme d'un autre pays)."
        ))

        self.edit_recherche_nom = QLineEdit()
        self.edit_recherche_nom.setPlaceholderText("Ex. Chartres, Saint-Martin, Ambérieu...")
        self.edit_recherche_nom.textChanged.connect(self._recherche_nom_changee)
        l.addWidget(self.edit_recherche_nom)
        l.addStretch(1)

        onglets.addTab(onglet, "🔤 Recherche par nom")

    def _recherche_nom_changee(self, texte):
        if len(texte.strip()) < 2:
            self.liste_resultats.clear()
            return
        candidats = gs.rechercher_villes(texte, pays="france", limite=100)
        self.liste_resultats.clear()
        if not candidats:
            item = QListWidgetItem("Aucune ville française trouvée pour cette recherche.")
            item.setFlags(item.flags() & ~Qt.ItemIsSelectable)
            self.liste_resultats.addItem(item)
            return
        for c in candidats:
            if c["code_postal"]:
                texte_item = f"{c['nom']}  —  {c['code_postal']}"
            else:
                texte_item = f"{c['nom']}  —  ({c['type']})"
            item = QListWidgetItem(texte_item)
            item.setData(Qt.UserRole, {"nom": c["nom"], "id": c["id"]})
            self.liste_resultats.addItem(item)
        self.liste_resultats.setCurrentRow(0)

    # ------------------------------------------------------------------
    # Onglet "Carte interactive"
    # ------------------------------------------------------------------
    def _construire_onglet_carte(self, onglets):
        if not WEBENGINE_DISPONIBLE:
            onglet = QWidget()
            l = QVBoxLayout(onglet)
            msg = QLabel(
                "La sélection sur carte nécessite le paquet PyQtWebEngine.\n"
                "Installez-le avec :  pip install PyQtWebEngine\n\n"
                f"(Erreur d'import d'origine : {WEBENGINE_IMPORT_ERROR})\n\n"
                "En attendant, utilisez l'onglet « Coordonnées GPS » ci-contre."
            )
            msg.setWordWrap(True)
            l.addWidget(msg)
            onglets.addTab(onglet, "🗺️ Carte interactive (indisponible)")
            return

        onglet = QWidget()
        l = QVBoxLayout(onglet)
        l.addWidget(QLabel(
            "Cliquez sur la carte à l'endroit voulu : la liste des stations "
            "connues les plus proches se met à jour automatiquement en dessous."
        ))

        self.vue_web = QWebEngineView()
        self._pont = Pont()
        self._canal = QWebChannel()
        self._canal.registerObject("pont", self._pont)
        self.vue_web.page().setWebChannel(self._canal)
        self._pont.point_clique.connect(self._point_carte_choisi)
        l.addWidget(self.vue_web, 1)

        self._charger_carte()
        onglets.addTab(onglet, "🗺️ Carte interactive")

    def _charger_carte(self):
        try:
            chemin = os.path.join(tempfile.gettempdir(), "carte_localisation_meteo.html")
            cl.construire_carte_html(chemin)
            self.vue_web.load(QUrl.fromLocalFile(chemin))
        except Exception as e:
            QMessageBox.warning(
                self, "Carte indisponible",
                f"Impossible de générer la carte interactive :\n{e}\n\n"
                "Utilisez l'onglet « Coordonnées GPS »."
            )

    def _point_carte_choisi(self, lat, lon):
        self.spin_lat.setValue(lat)
        self.spin_lon.setValue(lon)
        self._afficher_stations_proches(lat, lon)

    # ------------------------------------------------------------------
    # Onglet "Coordonnées GPS"
    # ------------------------------------------------------------------
    def _construire_onglet_gps(self, onglets):
        onglet = QWidget()
        l = QVBoxLayout(onglet)
        l.addWidget(QLabel(
            "Saisissez une latitude/longitude (ex. copiées depuis une autre "
            "carte ou un GPS) puis lancez la recherche."
        ))

        form = QFormLayout()
        self.spin_lat = QDoubleSpinBox()
        self.spin_lat.setRange(-90.0, 90.0)
        self.spin_lat.setDecimals(5)
        self.spin_lat.setValue(46.60000)
        form.addRow("Latitude :", self.spin_lat)

        self.spin_lon = QDoubleSpinBox()
        self.spin_lon.setRange(-180.0, 180.0)
        self.spin_lon.setDecimals(5)
        self.spin_lon.setValue(2.50000)
        form.addRow("Longitude :", self.spin_lon)
        l.addLayout(form)

        btn_chercher = QPushButton("🔍 Chercher la station la plus proche")
        btn_chercher.clicked.connect(self._chercher_depuis_coordonnees)
        l.addWidget(btn_chercher)
        l.addStretch(1)

        onglets.addTab(onglet, "📍 Coordonnées GPS")

    def _chercher_depuis_coordonnees(self):
        self._afficher_stations_proches(self.spin_lat.value(), self.spin_lon.value())

    # ------------------------------------------------------------------
    # Résultats (partagés par les deux onglets)
    # ------------------------------------------------------------------
    def _afficher_stations_proches(self, lat, lon):
        self.liste_resultats.clear()
        proches = gs.stations_les_plus_proches(lat, lon, n=8)
        if not proches:
            item = QListWidgetItem("Aucune station géolocalisée trouvée.")
            item.setFlags(item.flags() & ~Qt.ItemIsSelectable)
            self.liste_resultats.addItem(item)
            return
        for s in proches:
            texte = f"{s['nom']}  —  {s['distance_km']:.1f} km  ({s['type']})"
            item = QListWidgetItem(texte)
            item.setData(Qt.UserRole, {"nom": s["nom"], "id": s["id"]})
            self.liste_resultats.addItem(item)
        self.liste_resultats.setCurrentRow(0)

    def _maj_bouton_ok(self):
        items = self.liste_resultats.selectedItems()
        self.bouton_ok.setEnabled(bool(items) and bool(items[0].data(Qt.UserRole)))

    def resultat_choisi(self):
        """Dict {"nom", "id"} correspondant à la sélection dans la liste de
        résultats, ou None si aucune sélection valide."""
        items = self.liste_resultats.selectedItems()
        if items and items[0].data(Qt.UserRole):
            return items[0].data(Qt.UserRole)
        return None


def choisir_localisation(parent=None):
    """Ouvre la pop-up de choix de localisation et renvoie un dict {"nom",
    "id"} (``id`` peut être None si la ville n'a pas d'identifiant connu),
    ou None si l'utilisateur a annulé / n'a rien sélectionné."""
    dialogue = DialogueChoixLocalisation(parent)
    if dialogue.exec_() == QDialog.Accepted:
        return dialogue.resultat_choisi()
    return None
