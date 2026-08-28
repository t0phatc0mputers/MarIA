#!/usr/bin/env python3
"""
Gestion du planning cultural maraîcher bio (Île-de-France)
-----------------------------------------------------------
Application PyQt5 permettant de consulter, ajouter, modifier, supprimer
et filtrer des entrées d'un planning cultural agricole, le tout stocké
dans un fichier CSV (planning_cultural.csv).

Format du CSV (séparateur ';') :
    culture ; conduite ; variete_n ; action ; semaine_debut ; semaine_fin ;
    mois_debut ; mois_fin ; commentaire

- culture        : nom de la culture (ex. "Tomate")
- conduite       : "SA" (sous abri) ou "PC" (plein champ)
- variete_n      : numéro de variété/étalement pour cette culture+conduite (1,2,3...)
- action         : Semis direct / Semis en pot/plant / Plantation / Récolte /
                    Conservation / Forçage / Travail du sol / Apport de compost /
                    Apport de fumier / Paillage
- semaine_debut, semaine_fin : semaines de l'année (1-52)
- mois_debut, mois_fin       : mois correspondants (texte, calculés automatiquement)
- commentaire    : remarque libre (variétés conseillées, précautions, etc.)

Installation requise :
    pip install PyQt5 matplotlib pandas meteociel-api

Auteur : généré avec Claude
"""

import csv
import datetime
import os
import sys
import tempfile
import webbrowser

from PyQt5.QtCore import Qt, QDate, QThread, pyqtSignal, QUrl
from PyQt5.QtGui import QFont, QPixmap
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QTabWidget, QVBoxLayout, QHBoxLayout,
    QFormLayout, QGridLayout, QLabel, QLineEdit, QComboBox, QSpinBox, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QPlainTextEdit, QGroupBox, QSplitter, QMessageBox, QFileDialog, QStatusBar,
    QListWidget, QListWidgetItem, QDateEdit, QCompleter, QAction,
    QScrollArea, QFrame, QSizePolicy, QDoubleSpinBox, QProgressBar, QGraphicsScene,
    QTextBrowser, QStackedWidget, QInputDialog,
)

try:
    from PyQt5.QtWebEngineWidgets import QWebEngineView
    WEBENGINE_DISPONIBLE = True
except ImportError:
    WEBENGINE_DISPONIBLE = False

import meteo_decision as md
import fiches_botaniques as fb
import analyse_sol as asol
import rotation_cultures as rc
import plan_ferme as pf
import carte_france as cf
import dialogue_localisation as dl

try:
    import matplotlib
    matplotlib.use("Qt5Agg")
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_qt5agg import (
        FigureCanvasQTAgg as FigureCanvas,
        NavigationToolbar2QT as NavigationToolbar,
    )
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False


CSV_PATH_DEFAULT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "planning_cultural.csv")
DOSSIER_RESSOURCES_SOL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ressources_sol")
FIELDS = ["culture", "conduite", "variete_n", "action", "semaine_debut", "semaine_fin",
          "mois_debut", "mois_fin", "commentaire"]
HEADERS = ["Culture", "Conduite", "Variété n°", "Action", "Sem. début", "Sem. fin",
           "Mois début", "Mois fin", "Commentaire"]

ACTIONS = ["Semis direct", "Semis en pot/plant", "Plantation", "Récolte",
           "Conservation", "Forçage", "Travail du sol", "Apport de compost",
           "Apport de fumier", "Paillage"]

# Sous-ensemble "préparation de la planche" (travail du sol + amendements),
# utilisé pour proposer rapidement ces actions dans le planning.
ACTIONS_PREPARATION_PLANCHE = ["Travail du sol", "Apport de compost",
                                "Apport de fumier", "Paillage"]
CONDUITES = ["SA", "PC"]

MONTH_FR = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
            "septembre", "octobre", "novembre", "décembre"]

JOURS_FR = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]

# Palette simple pour une interface plus lisible / intuitive
COULEUR_OK = "#2e7d32"
COULEUR_ALERTE = "#c62828"
COULEUR_INFO = "#555555"
COULEUR_ACCENT = "#0b5a9e"


def semaine_vers_mois(semaine: int) -> str:
    """Convertit un numéro de semaine (1-52) en nom de mois approximatif."""
    semaine = max(1, min(52, int(semaine)))
    d = datetime.date(2025, 1, 1) + datetime.timedelta(days=(semaine - 1) * 7)
    return MONTH_FR[d.month - 1]


def semaine_actuelle() -> int:
    """Numéro de semaine (1-52) correspondant à la date du jour, selon le
    même découpage que semaine_vers_mois (blocs de 7 jours depuis le 1er
    janvier), pour rester cohérent avec la numérotation du planning."""
    aujourd_hui = datetime.date.today()
    jour_annee = aujourd_hui.timetuple().tm_yday
    semaine = ((jour_annee - 1) // 7) + 1
    return max(1, min(52, semaine))


class WorkerThread(QThread):
    """Fil d'exécution générique pour lancer une fonction bloquante (réseau)
    sans geler l'interface. Émet 'succes' avec le résultat, ou 'echec' avec
    l'exception levée."""
    succes = pyqtSignal(object)
    echec = pyqtSignal(Exception)

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs

    def run(self):
        try:
            resultat = self.fn(*self.args, **self.kwargs)
        except Exception as e:  # réseau, ville introuvable, paquet manquant, etc.
            self.echec.emit(e)
        else:
            self.succes.emit(resultat)


class PlanningApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Gestion du planning cultural maraîcher bio - GAB IDF")
        self.resize(1350, 780)

        self.csv_path = CSV_PATH_DEFAULT
        self.rows = []          # liste de dicts
        self.selected_index = None
        self._visible = []      # liste de (idx, row) actuellement affichés dans le tableau
        self._threads = []      # garde une référence aux threads actifs (évite le garbage collect)

        self._build_menu()
        self._build_statusbar()
        self._build_central()
        self._load_csv(self.csv_path, silent=True)

    # ------------------------------------------------------------------ UI
    def _build_menu(self):
        menubar = self.menuBar()
        filemenu = menubar.addMenu("&Fichier")

        act_ouvrir = QAction("Ouvrir un CSV...", self)
        act_ouvrir.setShortcut("Ctrl+O")
        act_ouvrir.triggered.connect(self.ouvrir_csv)
        filemenu.addAction(act_ouvrir)

        act_enregistrer = QAction("Enregistrer", self)
        act_enregistrer.setShortcut("Ctrl+S")
        act_enregistrer.triggered.connect(self.enregistrer_csv)
        filemenu.addAction(act_enregistrer)

        act_enregistrer_sous = QAction("Enregistrer sous...", self)
        act_enregistrer_sous.setShortcut("Ctrl+Shift+S")
        act_enregistrer_sous.triggered.connect(self.enregistrer_sous)
        filemenu.addAction(act_enregistrer_sous)

        filemenu.addSeparator()
        act_quitter = QAction("Quitter", self)
        act_quitter.setShortcut("Ctrl+Q")
        act_quitter.triggered.connect(self.close)
        filemenu.addAction(act_quitter)

    def _build_statusbar(self):
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self._set_status("Prêt.")

    def _set_status(self, texte):
        self.status_bar.showMessage(texte)

    def _build_central(self):
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        onglet_planning = QWidget()
        onglet_decision = QWidget()
        onglet_graphiques = QWidget()
        onglet_historique = QWidget()
        onglet_fiches = QWidget()
        onglet_rotation = QWidget()
        onglet_sol = QWidget()
        onglet_plan = QWidget()
        onglet_carte = QWidget()

        self.tabs.addTab(onglet_planning, "📋 Planning cultural")
        self.tabs.addTab(onglet_decision, "🌦 Aide à la décision")
        self.tabs.addTab(onglet_graphiques, "📈 Graphiques météo")
        self.tabs.addTab(onglet_historique, "🕘 Historique météo")
        self.tabs.addTab(onglet_fiches, "🌱 Fiches de référence")
        self.tabs.addTab(onglet_rotation, "🔄 Rotation des cultures")
        self.tabs.addTab(onglet_sol, "🧪 Analyse de sol & Fertilisation")
        self.tabs.addTab(onglet_plan, "🚜 Plan de la ferme")
        self.tabs.addTab(onglet_carte, "🗺️ Carte régionale")

        self._build_onglet_planning(onglet_planning)
        self._build_onglet_decision(onglet_decision)
        self._build_onglet_graphiques(onglet_graphiques)
        self._build_onglet_historique(onglet_historique)
        self._build_onglet_fiches(onglet_fiches)
        self._build_onglet_rotation(onglet_rotation)
        self._build_onglet_analyse_sol(onglet_sol)
        self._build_onglet_plan_ferme(onglet_plan)
        self._build_onglet_carte(onglet_carte)

    # ============================================================
    # Onglet "Planning cultural"
    # ============================================================
    def _build_onglet_planning(self, parent):
        layout = QVBoxLayout(parent)

        # --- Zone date du jour + actions de la semaine sélectionnée ---
        box_semaine = QGroupBox("🗓️ Semaine en cours")
        self.box_semaine = box_semaine
        layout_semaine = QVBoxLayout(box_semaine)

        ligne_haut = QHBoxLayout()
        self.lbl_date_jour = QLabel()
        self.lbl_date_jour.setStyleSheet(f"font-weight: bold; color: {COULEUR_ACCENT}; font-size: 11pt;")
        ligne_haut.addWidget(self.lbl_date_jour)
        ligne_haut.addStretch(1)
        ligne_haut.addWidget(QLabel("Semaine sélectionnée (1-52) :"))
        self.spin_semaine_actions = QSpinBox()
        self.spin_semaine_actions.setRange(1, 52)
        ligne_haut.addWidget(self.spin_semaine_actions)
        btn_semaine_actuelle = QPushButton("📍 Revenir à la semaine actuelle")
        ligne_haut.addWidget(btn_semaine_actuelle)
        layout_semaine.addLayout(ligne_haut)

        colonnes_semaine = ["Culture", "Conduite", "Action", "Semaines", "Commentaire"]
        self.table_semaine = QTableWidget(0, len(colonnes_semaine))
        self.table_semaine.setHorizontalHeaderLabels(colonnes_semaine)
        self.table_semaine.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table_semaine.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table_semaine.setAlternatingRowColors(True)
        self.table_semaine.verticalHeader().setVisible(False)
        self.table_semaine.horizontalHeader().setStretchLastSection(True)
        self.table_semaine.setMaximumHeight(170)
        layout_semaine.addWidget(self.table_semaine)

        layout.addWidget(box_semaine)

        # Tous les widgets existent désormais : on connecte les signaux et on
        # initialise sur la semaine actuelle (par défaut).
        self.spin_semaine_actions.valueChanged.connect(self._rafraichir_actions_semaine)
        btn_semaine_actuelle.clicked.connect(self._revenir_semaine_actuelle)
        self._maj_date_jour()
        self.spin_semaine_actions.setValue(semaine_actuelle())

        # --- Zone de filtre / recherche ---
        filtre_box = QGroupBox("Filtrer le planning")
        filtre_layout = QHBoxLayout(filtre_box)

        filtre_layout.addWidget(QLabel("🔎 Recherche (culture) :"))
        self.edit_recherche = QLineEdit()
        self.edit_recherche.setPlaceholderText("Ex. tomate…")
        self.edit_recherche.setClearButtonEnabled(True)
        self.edit_recherche.textChanged.connect(self._rafraichir_tableau)
        filtre_layout.addWidget(self.edit_recherche, 2)

        filtre_layout.addWidget(QLabel("Conduite :"))
        self.cb_filtre_conduite = QComboBox()
        self.cb_filtre_conduite.addItems(["Toutes"] + CONDUITES)
        self.cb_filtre_conduite.currentIndexChanged.connect(self._rafraichir_tableau)
        filtre_layout.addWidget(self.cb_filtre_conduite)

        filtre_layout.addWidget(QLabel("Action :"))
        self.cb_filtre_action = QComboBox()
        self.cb_filtre_action.addItems(["Toutes"] + ACTIONS)
        self.cb_filtre_action.currentIndexChanged.connect(self._rafraichir_tableau)
        filtre_layout.addWidget(self.cb_filtre_action)

        filtre_layout.addWidget(QLabel("Mois :"))
        self.cb_filtre_mois = QComboBox()
        self.cb_filtre_mois.addItems(["Tous"] + MONTH_FR)
        self.cb_filtre_mois.currentIndexChanged.connect(self._rafraichir_tableau)
        filtre_layout.addWidget(self.cb_filtre_mois)

        self.btn_reinit_filtres = QPushButton("Réinitialiser")
        self.btn_reinit_filtres.clicked.connect(self._reinitialiser_filtres)
        filtre_layout.addWidget(self.btn_reinit_filtres)

        layout.addWidget(filtre_box)

        # --- Tableau + formulaire dans un splitter (redimensionnable) ---
        splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(splitter, 1)

        self.table = QTableWidget(0, len(FIELDS))
        self.table.setHorizontalHeaderLabels(HEADERS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(False)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().sectionClicked.connect(self._trier_par)
        self.table.itemSelectionChanged.connect(self._on_select)
        largeurs = [170, 80, 80, 140, 80, 80, 90, 90]
        for i, w in enumerate(largeurs):
            self.table.setColumnWidth(i, w)
        splitter.addWidget(self.table)

        # --- Formulaire d'édition à droite ---
        form_box = QGroupBox("Détail de l'entrée")
        form_box.setMinimumWidth(320)
        form_box.setMaximumWidth(380)
        form_layout = QFormLayout(form_box)

        self.edit_culture = QLineEdit()
        form_layout.addRow("Culture :", self.edit_culture)

        self.cb_conduite = QComboBox()
        self.cb_conduite.addItems(CONDUITES)
        form_layout.addRow("Conduite :", self.cb_conduite)

        self.edit_variete_n = QLineEdit("1")
        form_layout.addRow("Variété n° :", self.edit_variete_n)

        self.cb_action = QComboBox()
        self.cb_action.addItems(ACTIONS)
        form_layout.addRow("Action :", self.cb_action)

        self.spin_semaine_debut = QSpinBox()
        self.spin_semaine_debut.setRange(1, 52)
        form_layout.addRow("Semaine début (1-52) :", self.spin_semaine_debut)

        self.spin_semaine_fin = QSpinBox()
        self.spin_semaine_fin.setRange(1, 52)
        form_layout.addRow("Semaine fin (1-52) :", self.spin_semaine_fin)

        self.txt_commentaire = QPlainTextEdit()
        self.txt_commentaire.setFixedHeight(90)
        form_layout.addRow("Commentaire :", self.txt_commentaire)

        btn_nouvelle = QPushButton("➕ Nouvelle entrée")
        btn_nouvelle.clicked.connect(self._nouvelle_entree)
        btn_ajouter = QPushButton("✅ Ajouter")
        btn_ajouter.clicked.connect(self._ajouter)
        btn_ajouter.setStyleSheet(f"font-weight: bold; color: {COULEUR_OK};")
        btn_modifier = QPushButton("💾 Enregistrer la modification")
        btn_modifier.clicked.connect(self._modifier)
        btn_supprimer = QPushButton("🗑 Supprimer")
        btn_supprimer.clicked.connect(self._supprimer)
        btn_supprimer.setStyleSheet(f"color: {COULEUR_ALERTE};")

        for b in (btn_nouvelle, btn_ajouter, btn_modifier, btn_supprimer):
            b.setMinimumHeight(30)
            form_layout.addRow(b)

        splitter.addWidget(form_box)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)

    def _reinitialiser_filtres(self):
        self.edit_recherche.clear()
        self.cb_filtre_conduite.setCurrentIndex(0)
        self.cb_filtre_action.setCurrentIndex(0)
        self.cb_filtre_mois.setCurrentIndex(0)

    # ------------------------------------------------------- Date & semaine
    def _maj_date_jour(self):
        aujourd_hui = datetime.date.today()
        jour_nom = JOURS_FR[aujourd_hui.weekday()]
        mois_nom = MONTH_FR[aujourd_hui.month - 1]
        self.lbl_date_jour.setText(
            f"📅 Aujourd'hui : {jour_nom} {aujourd_hui.day} {mois_nom} {aujourd_hui.year}"
        )

    def _revenir_semaine_actuelle(self):
        self.spin_semaine_actions.setValue(semaine_actuelle())

    def _rafraichir_actions_semaine(self):
        semaine = self.spin_semaine_actions.value()
        lignes = []
        for r in self.rows:
            try:
                debut = int(r.get("semaine_debut", 0))
                fin = int(r.get("semaine_fin", 0))
            except (ValueError, TypeError):
                continue
            if debut <= fin:
                dans_la_semaine = debut <= semaine <= fin
            else:  # période à cheval sur le changement d'année
                dans_la_semaine = semaine >= debut or semaine <= fin
            if dans_la_semaine:
                lignes.append(r)
        lignes.sort(key=lambda r: (r.get("culture", ""), r.get("conduite", "")))

        self.table_semaine.setRowCount(len(lignes))
        for row_pos, r in enumerate(lignes):
            semaines_txt = f"{r.get('semaine_debut', '')}-{r.get('semaine_fin', '')}"
            valeurs = [r.get("culture", ""), r.get("conduite", ""), r.get("action", ""),
                       semaines_txt, r.get("commentaire", "")]
            for col, v in enumerate(valeurs):
                self.table_semaine.setItem(row_pos, col, QTableWidgetItem(str(v)))

        if semaine == semaine_actuelle():
            self.box_semaine.setTitle(f"🗓️ Semaine en cours (semaine {semaine}) — {len(lignes)} action(s)")
        else:
            self.box_semaine.setTitle(f"🗓️ Semaine {semaine} — {len(lignes)} action(s)")

    # ------------------------------------------------------------ CSV I/O
    def _load_csv(self, path, silent=False):
        self.rows = []
        if os.path.exists(path):
            try:
                with open(path, newline="", encoding="utf-8") as f:
                    reader = csv.DictReader(f, delimiter=";")
                    for r in reader:
                        self.rows.append({k: r.get(k, "") for k in FIELDS})
                self.csv_path = path
                self._set_status(f"{len(self.rows)} entrées chargées depuis {path}")
            except Exception as e:
                if not silent:
                    QMessageBox.critical(self, "Erreur", f"Impossible de lire le fichier :\n{e}")
        else:
            if not silent:
                QMessageBox.information(self, "Info",
                                         "Aucun fichier existant : un nouveau planning vide a été créé.")
            self._set_status("Nouveau planning (aucun fichier chargé).")
        self._rafraichir_tableau()
        if hasattr(self, "table_semaine"):
            self._rafraichir_actions_semaine()
        if hasattr(self, "cb_dec_culture"):
            self._maj_liste_cultures()
        if hasattr(self, "liste_fiches"):
            self._maj_liste_fiches()

    def ouvrir_csv(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Ouvrir un planning CSV", "", "Fichiers CSV (*.csv);;Tous les fichiers (*.*)")
        if path:
            self._load_csv(path)

    def enregistrer_csv(self):
        self._ecrire_csv(self.csv_path)

    def enregistrer_sous(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Enregistrer sous...", "", "Fichiers CSV (*.csv)")
        if path:
            if not path.lower().endswith(".csv"):
                path += ".csv"
            self.csv_path = path
            self._ecrire_csv(path)

    def _ecrire_csv(self, path):
        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=FIELDS, delimiter=";")
                writer.writeheader()
                for r in self.rows:
                    writer.writerow(r)
            self._set_status(f"Enregistré : {path} ({len(self.rows)} entrées)")
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Impossible d'enregistrer :\n{e}")

    # ------------------------------------------------------------ Tableau
    def _lignes_filtrees(self):
        recherche = self.edit_recherche.text().strip().lower()
        f_conduite = self.cb_filtre_conduite.currentText()
        f_action = self.cb_filtre_action.currentText()
        f_mois = self.cb_filtre_mois.currentText()

        result = []
        for idx, r in enumerate(self.rows):
            if recherche and recherche not in r["culture"].lower():
                continue
            if f_conduite != "Toutes" and r["conduite"] != f_conduite:
                continue
            if f_action != "Toutes" and r["action"] != f_action:
                continue
            if f_mois != "Tous" and f_mois not in (r["mois_debut"], r["mois_fin"]):
                continue
            result.append((idx, r))
        return result

    def _rafraichir_tableau(self):
        self._visible = self._lignes_filtrees()
        self.table.blockSignals(True)
        self.table.setRowCount(len(self._visible))
        for row_pos, (idx, r) in enumerate(self._visible):
            for col, field in enumerate(FIELDS):
                item = QTableWidgetItem(str(r.get(field, "")))
                if col == 0:
                    item.setData(Qt.UserRole, idx)
                self.table.setItem(row_pos, col, item)
        self.table.blockSignals(False)
        self._set_status(f"{len(self._visible)} entrée(s) affichée(s) sur {len(self.rows)} au total.")

    def _trier_par(self, col_index):
        col = FIELDS[col_index]
        try:
            self.rows.sort(key=lambda r: (int(r[col]) if str(r[col]).isdigit() else str(r[col])))
        except Exception:
            self.rows.sort(key=lambda r: str(r.get(col, "")))
        self._rafraichir_tableau()

    def _on_select(self):
        items = self.table.selectedItems()
        if not items:
            return
        row_pos = items[0].row()
        idx_item = self.table.item(row_pos, 0)
        if idx_item is None:
            return
        idx = idx_item.data(Qt.UserRole)
        self.selected_index = idx
        r = self.rows[idx]
        self.edit_culture.setText(r.get("culture", ""))
        i = self.cb_conduite.findText(r.get("conduite", "SA"))
        self.cb_conduite.setCurrentIndex(max(0, i))
        self.edit_variete_n.setText(r.get("variete_n", "1"))
        i = self.cb_action.findText(r.get("action", ACTIONS[0]))
        self.cb_action.setCurrentIndex(max(0, i))
        try:
            self.spin_semaine_debut.setValue(int(r.get("semaine_debut", 1)))
            self.spin_semaine_fin.setValue(int(r.get("semaine_fin", 1)))
        except (ValueError, TypeError):
            pass
        self.txt_commentaire.setPlainText(r.get("commentaire", ""))

    # ------------------------------------------------------------ CRUD
    def _lire_formulaire(self):
        sem_d = self.spin_semaine_debut.value()
        sem_f = self.spin_semaine_fin.value()
        culture = self.edit_culture.text().strip()
        if not culture:
            QMessageBox.warning(self, "Champ requis", "Le nom de la culture est requis.")
            return None
        return {
            "culture": culture,
            "conduite": self.cb_conduite.currentText(),
            "variete_n": self.edit_variete_n.text().strip() or "1",
            "action": self.cb_action.currentText(),
            "semaine_debut": str(sem_d),
            "semaine_fin": str(sem_f),
            "mois_debut": semaine_vers_mois(sem_d),
            "mois_fin": semaine_vers_mois(sem_f),
            "commentaire": self.txt_commentaire.toPlainText().strip(),
        }

    def _nouvelle_entree(self):
        self.selected_index = None
        self.table.clearSelection()
        self.edit_culture.clear()
        self.cb_conduite.setCurrentIndex(0)
        self.edit_variete_n.setText("1")
        self.cb_action.setCurrentIndex(0)
        self.spin_semaine_debut.setValue(1)
        self.spin_semaine_fin.setValue(1)
        self.txt_commentaire.clear()
        self.edit_culture.setFocus()

    def _ajouter(self):
        data = self._lire_formulaire()
        if data is None:
            return
        self.rows.append(data)
        self._rafraichir_tableau()
        if hasattr(self, "table_semaine"):
            self._rafraichir_actions_semaine()
        if hasattr(self, "cb_dec_culture"):
            self._maj_liste_cultures()
        if hasattr(self, "liste_fiches"):
            self._maj_liste_fiches()
        self._set_status(f"Entrée ajoutée : {data['culture']} ({data['conduite']})")

    def _modifier(self):
        if self.selected_index is None:
            QMessageBox.information(self, "Info",
                                     "Sélectionnez d'abord une entrée dans le tableau à modifier.")
            return
        data = self._lire_formulaire()
        if data is None:
            return
        self.rows[self.selected_index] = data
        self._rafraichir_tableau()
        if hasattr(self, "table_semaine"):
            self._rafraichir_actions_semaine()
        if hasattr(self, "cb_dec_culture"):
            self._maj_liste_cultures()
        if hasattr(self, "liste_fiches"):
            self._maj_liste_fiches()
        self._set_status(f"Entrée modifiée : {data['culture']} ({data['conduite']})")

    def _supprimer(self):
        if self.selected_index is None:
            QMessageBox.information(self, "Info",
                                     "Sélectionnez d'abord une entrée dans le tableau à supprimer.")
            return
        reponse = QMessageBox.question(
            self, "Confirmation", "Supprimer cette entrée du planning ?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reponse == QMessageBox.Yes:
            del self.rows[self.selected_index]
            self.selected_index = None
            self._rafraichir_tableau()
            if hasattr(self, "table_semaine"):
                self._rafraichir_actions_semaine()
            if hasattr(self, "cb_dec_culture"):
                self._maj_liste_cultures()
            if hasattr(self, "liste_fiches"):
                self._maj_liste_fiches()
            self._set_status("Entrée supprimée.")

    # ============================================================
    # Onglet "Aide à la décision (météo)"
    # ============================================================
    def _build_onglet_decision(self, parent):
        layout = QVBoxLayout(parent)

        info = QLabel(
            "Cet outil applique des règles agronomiques simples (gel, pluie, vent) aux "
            "prévisions Météociel pour suggérer le meilleur moment pour une action. "
            "Ce n'est pas une prédiction garantie : vérifiez toujours l'état du terrain."
        )
        info.setWordWrap(True)
        info.setStyleSheet(f"color: {COULEUR_INFO};")
        layout.addWidget(info)

        if not md.METEOCIEL_AVAILABLE:
            avert = QLabel(
                "⚠ Le paquet 'meteociel-api' n'est pas installé sur cette machine. "
                "Installez-le avec :  pip install meteociel-api"
            )
            avert.setWordWrap(True)
            avert.setStyleSheet(f"color: {COULEUR_ALERTE};")
            layout.addWidget(avert)

        form_box = QGroupBox("Paramètres de l'analyse")
        form_layout = QFormLayout(form_box)

        ligne_culture = QHBoxLayout()
        self.cb_dec_culture = QComboBox()
        self.cb_dec_culture.setEditable(True)
        self.cb_dec_culture.setInsertPolicy(QComboBox.NoInsert)
        self.cb_dec_culture.currentIndexChanged.connect(self._maj_variete_conduite)
        self.cb_dec_culture.editTextChanged.connect(self._maj_variete_conduite)
        ligne_culture.addWidget(self.cb_dec_culture)
        form_layout.addRow("Culture :", ligne_culture)

        ligne_conduite_var = QHBoxLayout()
        self.cb_dec_conduite = QComboBox()
        self.cb_dec_conduite.addItems(["Toutes"] + CONDUITES)
        ligne_conduite_var.addWidget(QLabel("Conduite :"))
        ligne_conduite_var.addWidget(self.cb_dec_conduite)
        ligne_conduite_var.addSpacing(16)
        self.cb_dec_variete = QComboBox()
        self.cb_dec_variete.addItems(["Toutes"])
        ligne_conduite_var.addWidget(QLabel("Variété n° :"))
        ligne_conduite_var.addWidget(self.cb_dec_variete)
        form_layout.addRow("Filtres planning :", ligne_conduite_var)

        self.cb_dec_action = QComboBox()
        self.cb_dec_action.addItems(ACTIONS)
        form_layout.addRow("Action :", self.cb_dec_action)

        ligne_ville = QHBoxLayout()
        self.edit_dec_ville = QLineEdit("Paris (75000)")
        ligne_ville.addWidget(self.edit_dec_ville)
        btn_dec_localiser = QPushButton("📍")
        btn_dec_localiser.setToolTip("Choisir sur une carte ou par coordonnées GPS")
        btn_dec_localiser.setMaximumWidth(36)
        btn_dec_localiser.clicked.connect(lambda: self._choisir_ville(self.edit_dec_ville))
        ligne_ville.addWidget(btn_dec_localiser)
        form_layout.addRow("Ville (Météociel) :", ligne_ville)

        ligne_mode = QHBoxLayout()
        self.cb_dec_mode = QComboBox()
        self.cb_dec_mode.addItems(list(md.MODES_DISPONIBLES.keys()))
        self.cb_dec_mode.currentIndexChanged.connect(self._maj_etat_modele)
        ligne_mode.addWidget(self.cb_dec_mode, 2)
        ligne_mode.addWidget(QLabel("Modèle :"))
        self.cb_dec_modele = QComboBox()
        self.cb_dec_modele.addItems(md.MODELES_DISPONIBLES)
        ligne_mode.addWidget(self.cb_dec_modele)
        form_layout.addRow("Source météo :", ligne_mode)

        self.btn_dec_analyser = QPushButton("🔍 Analyser")
        self.btn_dec_analyser.setMinimumHeight(32)
        self.btn_dec_analyser.setStyleSheet(f"font-weight: bold; color: white; background-color: {COULEUR_ACCENT};")
        self.btn_dec_analyser.clicked.connect(self._lancer_analyse_decision)
        form_layout.addRow(self.btn_dec_analyser)

        layout.addWidget(form_box)

        result_box = QGroupBox("Résultat de l'analyse")
        result_layout = QVBoxLayout(result_box)
        self.txt_dec_resultat = QPlainTextEdit()
        self.txt_dec_resultat.setReadOnly(True)
        self.txt_dec_resultat.setPlainText(
            "Sélectionnez une culture et une action, puis cliquez sur « Analyser ».")
        result_layout.addWidget(self.txt_dec_resultat)
        layout.addWidget(result_box, 1)

        self._maj_liste_cultures()

    def _maj_liste_cultures(self):
        """Met à jour la liste déroulante des cultures depuis le planning chargé."""
        cultures = sorted({r["culture"] for r in self.rows if r.get("culture")})
        texte_actuel = self.cb_dec_culture.currentText()
        self.cb_dec_culture.blockSignals(True)
        self.cb_dec_culture.clear()
        self.cb_dec_culture.addItems(cultures)
        completer = QCompleter(cultures, self.cb_dec_culture)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)
        self.cb_dec_culture.setCompleter(completer)
        if texte_actuel and texte_actuel in cultures:
            self.cb_dec_culture.setCurrentText(texte_actuel)
        elif cultures:
            self.cb_dec_culture.setCurrentIndex(0)
        self.cb_dec_culture.blockSignals(False)
        self._maj_variete_conduite()

    def _maj_variete_conduite(self):
        culture = self.cb_dec_culture.currentText().strip().lower()
        varietes = sorted({str(r.get("variete_n", "1")) for r in self.rows
                            if r.get("culture", "").strip().lower() == culture},
                           key=lambda x: (len(x), x))
        self.cb_dec_variete.blockSignals(True)
        self.cb_dec_variete.clear()
        self.cb_dec_variete.addItems(["Toutes"] + varietes)
        self.cb_dec_variete.blockSignals(False)

    def _maj_etat_modele(self):
        mode = md.MODES_DISPONIBLES.get(self.cb_dec_mode.currentText(), "forecasts")
        self.cb_dec_modele.setEnabled(mode == "forecasts")

    def _lancer_analyse_decision(self):
        culture = self.cb_dec_culture.currentText().strip()
        conduite_sel = self.cb_dec_conduite.currentText()
        variete = self.cb_dec_variete.currentText()
        action = self.cb_dec_action.currentText()
        ville = self.edit_dec_ville.text().strip()
        mode = md.MODES_DISPONIBLES.get(self.cb_dec_mode.currentText(), "forecasts")
        modele = self.cb_dec_modele.currentText()

        if not culture:
            QMessageBox.warning(self, "Champ requis", "Veuillez indiquer une culture.")
            return
        if not ville:
            QMessageBox.warning(self, "Champ requis", "Veuillez indiquer une ville pour la météo.")
            return

        # 1) Vérification calendaire (rapide, locale, pas de réseau)
        conduites_a_tester = CONDUITES if conduite_sel == "Toutes" else [conduite_sel]
        textes_calendrier = []
        for c in conduites_a_tester:
            textes_calendrier.append(
                f"--- Conduite {c} ---\n" +
                md.verifier_calendrier(self.rows, culture, c, action, variete)
            )
        texte_calendrier = "\n\n".join(textes_calendrier)

        self.txt_dec_resultat.setPlainText(
            texte_calendrier + "\n\n⏳ Récupération des prévisions météo Météociel en cours...")
        self.btn_dec_analyser.setEnabled(False)
        self._set_status("Analyse météo en cours...")

        thread = WorkerThread(md.recommander, action, ville, mode=mode, modele=modele)
        thread.succes.connect(lambda resultat: self._analyse_terminee(texte_calendrier, resultat, None))
        thread.echec.connect(lambda erreur: self._analyse_terminee(texte_calendrier, None, erreur))
        thread.finished.connect(lambda: self._nettoyer_thread(thread))
        self._threads.append(thread)
        thread.start()

    def _nettoyer_thread(self, thread):
        if thread in self._threads:
            self._threads.remove(thread)

    def _analyse_terminee(self, texte_calendrier, resultat, erreur):
        self.btn_dec_analyser.setEnabled(True)
        if erreur is not None:
            self.txt_dec_resultat.setPlainText(
                texte_calendrier +
                f"\n\n❌ Impossible de récupérer les données météo Météociel :\n{erreur}"
            )
            self._set_status("Échec de la récupération météo.")
            return
        _, _, texte_meteo = resultat
        self.txt_dec_resultat.setPlainText(texte_calendrier + "\n\n--- Analyse météo ---\n" + texte_meteo)
        self._set_status("Analyse météo terminée.")

    # ============================================================
    # Onglet "Graphiques météo"
    # ============================================================
    def _build_onglet_graphiques(self, parent):
        layout = QVBoxLayout(parent)

        if not MATPLOTLIB_AVAILABLE:
            avert = QLabel("⚠ Le paquet 'matplotlib' n'est pas installé. Installez-le avec :\n"
                            "pip install matplotlib")
            avert.setWordWrap(True)
            avert.setStyleSheet(f"color: {COULEUR_ALERTE};")
            layout.addWidget(avert)
            return

        form_box = QGroupBox("Prévisions météo")
        form_layout = QHBoxLayout(form_box)

        form_layout.addWidget(QLabel("Ville :"))
        self.edit_graph_ville = QLineEdit("Paris (75000)")
        self.edit_graph_ville.setMaximumWidth(180)
        form_layout.addWidget(self.edit_graph_ville)
        btn_graph_localiser = QPushButton("📍")
        btn_graph_localiser.setToolTip("Choisir sur une carte ou par coordonnées GPS")
        btn_graph_localiser.setMaximumWidth(36)
        btn_graph_localiser.clicked.connect(lambda: self._choisir_ville(self.edit_graph_ville))
        form_layout.addWidget(btn_graph_localiser)

        form_layout.addWidget(QLabel("Source :"))
        self.cb_graph_mode = QComboBox()
        self.cb_graph_mode.addItems(list(md.MODES_DISPONIBLES.keys()))
        self.cb_graph_mode.currentIndexChanged.connect(self._maj_etat_modele_graph)
        form_layout.addWidget(self.cb_graph_mode, 2)

        form_layout.addWidget(QLabel("Modèle :"))
        self.cb_graph_modele = QComboBox()
        self.cb_graph_modele.addItems(md.MODELES_DISPONIBLES)
        form_layout.addWidget(self.cb_graph_modele)

        self.btn_graph_charger = QPushButton("📊 Afficher le graphique")
        self.btn_graph_charger.setStyleSheet(f"font-weight: bold; color: white; background-color: {COULEUR_ACCENT};")
        self.btn_graph_charger.clicked.connect(self._lancer_chargement_graphique)
        form_layout.addWidget(self.btn_graph_charger)

        layout.addWidget(form_box)

        self.lbl_graph_status = QLabel("Choisissez une ville puis cliquez sur « Afficher le graphique ».")
        self.lbl_graph_status.setStyleSheet(f"color: {COULEUR_INFO};")
        layout.addWidget(self.lbl_graph_status)

        self.fig_meteo = Figure(figsize=(10, 6.5), dpi=100)
        self.axes_meteo = self.fig_meteo.subplots(2, 2)
        self.fig_meteo.tight_layout(pad=3.0)
        self.canvas_meteo = FigureCanvas(self.fig_meteo)
        layout.addWidget(self.canvas_meteo, 1)
        self.toolbar_meteo = NavigationToolbar(self.canvas_meteo, parent)
        layout.addWidget(self.toolbar_meteo)

        self._dessiner_graphiques_vides()

    def _maj_etat_modele_graph(self):
        mode = md.MODES_DISPONIBLES.get(self.cb_graph_mode.currentText(), "forecasts")
        self.cb_graph_modele.setEnabled(mode == "forecasts")

    def _dessiner_graphiques_vides(self):
        titres = ["Température (°C)", "Précipitations (mm)", "Humidité (%)", "Vent (km/h)"]
        for ax, titre in zip(self.axes_meteo.flat, titres):
            ax.clear()
            ax.set_title(titre)
            ax.text(0.5, 0.5, "Aucune donnée chargée", ha="center", va="center",
                     transform=ax.transAxes, color="#999")
        self.fig_meteo.tight_layout(pad=3.0)
        self.canvas_meteo.draw()

    def _lancer_chargement_graphique(self):
        ville = self.edit_graph_ville.text().strip()
        if not ville:
            QMessageBox.warning(self, "Champ requis", "Veuillez indiquer une ville pour la météo.")
            return
        mode = md.MODES_DISPONIBLES.get(self.cb_graph_mode.currentText(), "forecasts")
        modele = self.cb_graph_modele.currentText()

        self.btn_graph_charger.setEnabled(False)
        self.lbl_graph_status.setText("⏳ Récupération des données Météociel en cours...")

        thread = WorkerThread(md.recuperer_previsions, ville, mode=mode, modele=modele)
        thread.succes.connect(lambda resultat: self._graphique_termine(resultat[0], resultat[1], None))
        thread.echec.connect(lambda erreur: self._graphique_termine(None, None, erreur))
        thread.finished.connect(lambda: self._nettoyer_thread(thread))
        self._threads.append(thread)
        thread.start()

    def _graphique_termine(self, ville_trouvee, df, erreur):
        self.btn_graph_charger.setEnabled(True)
        if erreur is not None:
            self.lbl_graph_status.setText(f"❌ Échec de la récupération météo : {erreur}")
            self.lbl_graph_status.setStyleSheet(f"color: {COULEUR_ALERTE};")
            return

        if df is None or df.empty:
            self.lbl_graph_status.setText("Aucune donnée renvoyée par Météociel.")
            self.lbl_graph_status.setStyleSheet(f"color: {COULEUR_ALERTE};")
            return

        if not md.pd.api.types.is_datetime64_any_dtype(df["date"]):
            df["date"] = md.pd.to_datetime(df["date"])

        dates = df["date"]

        ax_temp, ax_pluie, ax_humid, ax_vent = self.axes_meteo.flat
        for ax in (ax_temp, ax_pluie, ax_humid, ax_vent):
            ax.clear()

        ax_temp.plot(dates, df["temperature"], color="#d9534f", marker="o", markersize=3,
                     label="Température")
        ax_temp.plot(dates, df["windchill"], color="#f0ad4e", linestyle="--", linewidth=1,
                     label="Ressenti")
        ax_temp.axhline(0, color="#337ab7", linewidth=0.8, linestyle=":")
        ax_temp.set_title("Température (°C)")
        ax_temp.legend(fontsize=8)
        ax_temp.grid(True, alpha=0.3)

        ax_pluie.bar(dates, df["rain"], width=0.1, color="#337ab7")
        ax_pluie.set_title("Précipitations (mm)")
        ax_pluie.grid(True, alpha=0.3)

        ax_humid.plot(dates, df["humidity"], color="#5cb85c", marker="o", markersize=3)
        ax_humid.set_title("Humidité (%)")
        ax_humid.set_ylim(0, 100)
        ax_humid.grid(True, alpha=0.3)

        ax_vent.plot(dates, df["wind_spd"], color="#5bc0de", marker="o", markersize=3,
                     label="Vent moyen")
        ax_vent.plot(dates, df["wind_gust"], color="#9370db", linestyle="--", linewidth=1,
                     label="Rafales")
        ax_vent.set_title("Vent (km/h)")
        ax_vent.legend(fontsize=8)
        ax_vent.grid(True, alpha=0.3)

        for ax in (ax_temp, ax_pluie, ax_humid, ax_vent):
            ax.tick_params(axis="x", rotation=30, labelsize=8)

        self.fig_meteo.suptitle(f"Météociel — {ville_trouvee}", fontsize=12)
        self.fig_meteo.tight_layout(pad=3.0, rect=[0, 0, 1, 0.96])
        self.canvas_meteo.draw()

        self.lbl_graph_status.setText(f"✅ Données chargées pour « {ville_trouvee} » ({len(df)} relevés).")
        self.lbl_graph_status.setStyleSheet(f"color: {COULEUR_OK};")

    # ============================================================
    # Onglet "Historique météo"
    # ============================================================
    def _build_onglet_historique(self, parent):
        layout = QVBoxLayout(parent)

        if not MATPLOTLIB_AVAILABLE:
            avert = QLabel("⚠ Le paquet 'matplotlib' n'est pas installé. Installez-le avec :\n"
                            "pip install matplotlib")
            avert.setWordWrap(True)
            avert.setStyleSheet(f"color: {COULEUR_ALERTE};")
            layout.addWidget(avert)
            return

        info = QLabel(
            "Historique des mesures de station Météociel (température, humidité...). "
            "Un appel réseau est effectué par jour de la période sélectionnée : privilégiez "
            "des périodes courtes (quelques jours à quelques semaines)."
        )
        info.setWordWrap(True)
        info.setStyleSheet(f"color: {COULEUR_INFO};")
        layout.addWidget(info)

        form_box = QGroupBox("Période à récupérer")
        form_layout = QHBoxLayout(form_box)

        form_layout.addWidget(QLabel("Ville :"))
        self.edit_hist_ville = QLineEdit("Paris (75000)")
        self.edit_hist_ville.setMaximumWidth(160)
        form_layout.addWidget(self.edit_hist_ville)
        btn_hist_localiser = QPushButton("📍")
        btn_hist_localiser.setToolTip("Choisir sur une carte ou par coordonnées GPS")
        btn_hist_localiser.setMaximumWidth(36)
        btn_hist_localiser.clicked.connect(lambda: self._choisir_ville(self.edit_hist_ville))
        form_layout.addWidget(btn_hist_localiser)

        hier = QDate.currentDate().addDays(-1)
        debut_defaut = hier.addDays(-6)

        form_layout.addWidget(QLabel("Du :"))
        self.date_hist_debut = QDateEdit(debut_defaut)
        self.date_hist_debut.setCalendarPopup(True)
        self.date_hist_debut.setDisplayFormat("dd/MM/yyyy")
        self.date_hist_debut.setMaximumDate(QDate.currentDate())
        form_layout.addWidget(self.date_hist_debut)

        form_layout.addWidget(QLabel("au :"))
        self.date_hist_fin = QDateEdit(hier)
        self.date_hist_fin.setCalendarPopup(True)
        self.date_hist_fin.setDisplayFormat("dd/MM/yyyy")
        self.date_hist_fin.setMaximumDate(QDate.currentDate())
        form_layout.addWidget(self.date_hist_fin)

        form_layout.addStretch(1)

        self.btn_hist_base = QPushButton("🗺 Générer la base de villes (une fois)")
        self.btn_hist_base.clicked.connect(self._lancer_generation_base_villes)
        form_layout.addWidget(self.btn_hist_base)

        self.btn_hist_charger = QPushButton("⬇ Charger l'historique")
        self.btn_hist_charger.setStyleSheet(f"font-weight: bold; color: white; background-color: {COULEUR_ACCENT};")
        self.btn_hist_charger.clicked.connect(self._lancer_chargement_historique)
        form_layout.addWidget(self.btn_hist_charger)

        layout.addWidget(form_box)

        self.lbl_hist_status = QLabel("")
        self.lbl_hist_status.setStyleSheet(f"color: {COULEUR_INFO};")
        layout.addWidget(self.lbl_hist_status)

        self.lbl_hist_valeur = QLabel("Cliquez sur un point du graphique pour afficher sa valeur exacte.")
        self.lbl_hist_valeur.setStyleSheet(f"color: {COULEUR_ACCENT}; font-weight: bold;")
        layout.addWidget(self.lbl_hist_valeur)

        self.fig_hist = Figure(figsize=(10, 6), dpi=100)
        self.ax_hist_temp, self.ax_hist_humid = self.fig_hist.subplots(2, 1, sharex=True)
        self.fig_hist.tight_layout(pad=3.0)
        self.canvas_hist = FigureCanvas(self.fig_hist)
        self.canvas_hist.mpl_connect("button_press_event", self._clic_graphique_historique)
        layout.addWidget(self.canvas_hist, 1)
        toolbar_hist = NavigationToolbar(self.canvas_hist, parent)
        layout.addWidget(toolbar_hist)

        self.df_historique = None
        self._dessiner_historique_vide()

    def _dessiner_historique_vide(self):
        for ax, titre in ((self.ax_hist_temp, "Température (°C)"), (self.ax_hist_humid, "Humidité (%)")):
            ax.clear()
            ax.set_title(titre)
            ax.text(0.5, 0.5, "Aucune donnée chargée", ha="center", va="center",
                     transform=ax.transAxes, color="#999")
        self.fig_hist.tight_layout(pad=3.0)
        self.canvas_hist.draw()

    def _lire_dates_historique(self):
        d1 = self.date_hist_debut.date().toPyDate()
        d2 = self.date_hist_fin.date().toPyDate()
        return d1, d2

    def _choisir_ville(self, champ_ville):
        """Ouvre la pop-up « Choisir une localisation » (carte cliquable ou
        coordonnées GPS) et, si l'utilisateur valide un choix, met à jour le
        champ de saisie 'ville' Météociel fourni."""
        nom = dl.choisir_localisation(self)
        if nom:
            champ_ville.setText(nom)

    def _proposer_choix_villes(self, candidats):
        """Affiche un choix parmi plusieurs villes françaises homonymes (voir
        meteo_decision.PlusieursVillesTrouvees) et, si l'utilisateur en
        choisit une, met à jour le champ 'ville' de l'historique et relance
        automatiquement le chargement avec le nom exact choisi."""
        etiquettes = [
            f"{c['nom']}  —  {c['code_postal']}" if c["code_postal"]
            else f"{c['nom']}  —  ({c['type']})"
            for c in candidats
        ]
        etiquette, ok = QInputDialog.getItem(
            self, "Plusieurs villes correspondent",
            "Cette recherche correspond à plusieurs villes françaises. "
            "Précisez celle voulue :",
            etiquettes, 0, False,
        )
        if not ok:
            self.lbl_hist_status.setText("Chargement annulé : plusieurs villes correspondaient à la recherche.")
            self.lbl_hist_status.setStyleSheet(f"color: {COULEUR_ALERTE};")
            return
        index = etiquettes.index(etiquette)
        self.edit_hist_ville.setText(candidats[index]["nom"])
        self._lancer_chargement_historique()

    def _lancer_generation_base_villes(self):
        if md.base_villes_disponible():
            QMessageBox.information(self, "Info", "La base de villes est déjà disponible sur cette machine.")
            return
        reponse = QMessageBox.question(
            self, "Confirmation",
            "La génération de la base de villes parcourt le site Météociel et peut prendre "
            "plusieurs dizaines de secondes, voire quelques minutes. Continuer ?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reponse != QMessageBox.Yes:
            return
        self.btn_hist_base.setEnabled(False)
        self.lbl_hist_status.setText("⏳ Génération de la base de villes en cours...")

        thread = WorkerThread(md.generer_base_villes)
        thread.succes.connect(lambda _r: self._generation_base_terminee(None))
        thread.echec.connect(lambda erreur: self._generation_base_terminee(erreur))
        thread.finished.connect(lambda: self._nettoyer_thread(thread))
        self._threads.append(thread)
        thread.start()

    def _generation_base_terminee(self, erreur):
        self.btn_hist_base.setEnabled(True)
        if erreur is not None:
            self.lbl_hist_status.setText(f"❌ Échec de la génération : {erreur}")
            self.lbl_hist_status.setStyleSheet(f"color: {COULEUR_ALERTE};")
            return
        self.lbl_hist_status.setText("✅ Base de villes générée avec succès.")
        self.lbl_hist_status.setStyleSheet(f"color: {COULEUR_OK};")

    def _lancer_chargement_historique(self):
        ville = self.edit_hist_ville.text().strip()
        if not ville:
            QMessageBox.warning(self, "Champ requis", "Veuillez indiquer une ville.")
            return
        d1, d2 = self._lire_dates_historique()
        nb_jours = abs((d2 - d1).days) + 1
        if nb_jours > 31:
            reponse = QMessageBox.question(
                self, "Période longue",
                f"La période sélectionnée représente {nb_jours} jours, donc {nb_jours} appels "
                "réseau successifs. Cela peut être long. Continuer ?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reponse != QMessageBox.Yes:
                return

        self.btn_hist_charger.setEnabled(False)
        self.lbl_hist_status.setText("⏳ Récupération de l'historique en cours...")
        self.lbl_hist_status.setStyleSheet(f"color: {COULEUR_INFO};")

        thread = WorkerThread(md.recuperer_historique, ville, d1, d2)
        thread.succes.connect(lambda resultat: self._historique_termine(resultat[0], resultat[1], None))
        thread.echec.connect(lambda erreur: self._historique_termine(None, None, erreur))
        thread.finished.connect(lambda: self._nettoyer_thread(thread))
        self._threads.append(thread)
        thread.start()

    def _historique_termine(self, ville_trouvee, df, erreur):
        self.btn_hist_charger.setEnabled(True)
        if isinstance(erreur, md.PlusieursVillesTrouvees):
            self._proposer_choix_villes(erreur.candidats)
            return
        if erreur is not None:
            self.lbl_hist_status.setText(f"❌ Échec de la récupération : {erreur}")
            self.lbl_hist_status.setStyleSheet(f"color: {COULEUR_ALERTE};")
            return
        if df is None or df.empty:
            self.lbl_hist_status.setText("Aucune donnée renvoyée par Météociel pour cette période.")
            self.lbl_hist_status.setStyleSheet(f"color: {COULEUR_ALERTE};")
            return

        self.df_historique = df

        self.ax_hist_temp.clear()
        self.ax_hist_humid.clear()

        self.ax_hist_temp.plot(df["datetime"], df["temperature"], color="#d9534f", linewidth=1)
        self.ax_hist_temp.axhline(0, color="#337ab7", linewidth=0.8, linestyle=":")
        self.ax_hist_temp.set_title("Température (°C)")
        self.ax_hist_temp.grid(True, alpha=0.3)

        self.ax_hist_humid.plot(df["datetime"], df["humidity"], color="#5cb85c", linewidth=1)
        self.ax_hist_humid.set_title("Humidité (%)")
        self.ax_hist_humid.set_ylim(0, 100)
        self.ax_hist_humid.grid(True, alpha=0.3)
        self.ax_hist_humid.tick_params(axis="x", rotation=30, labelsize=8)

        self.fig_hist.suptitle(f"Historique Météociel — {ville_trouvee}", fontsize=12)
        self.fig_hist.tight_layout(pad=3.0, rect=[0, 0, 1, 0.95])
        self.canvas_hist.draw()

        self.lbl_hist_status.setText(f"✅ Historique chargé pour « {ville_trouvee} » ({len(df)} relevés).")
        self.lbl_hist_status.setStyleSheet(f"color: {COULEUR_OK};")
        self.lbl_hist_valeur.setText("Cliquez sur un point du graphique pour afficher sa valeur exacte.")

    def _clic_graphique_historique(self, event):
        if self.df_historique is None or event.xdata is None:
            return
        import matplotlib.dates as mdates
        clic_dt = mdates.num2date(event.xdata).replace(tzinfo=None)
        df = self.df_historique
        deltas = (df["datetime"] - clic_dt).abs()
        idx = deltas.idxmin()
        ligne = df.loc[idx]
        dt = ligne["datetime"]
        jour_fr = md.JOURS_FR[dt.weekday()]
        mois_fr = md.MOIS_FR[dt.month - 1]
        texte = (f"{jour_fr} {dt.day} {mois_fr} {dt.year} à {dt.hour}h{dt.minute:02d} : "
                 f"température {ligne['temperature']:.1f} °C, humidité {ligne['humidity']:.0f} %")
        self.lbl_hist_valeur.setText(texte)

    # ============================================================
    # Onglet "Fiches de référence" (façon Pokédex)
    # ============================================================
    EMOJIS_CULTURE = {
        "tomate": "🍅", "aubergine": "🍆", "concombre": "🥒", "courgette": "🥒",
        "courge": "🎃", "pastèque": "🍉", "melon": "🍈", "carotte": "🥕",
        "navet": "🥬", "radis": "🥬", "betterave": "🥬", "pomme de terre": "🥔",
        "patate douce": "🍠", "oignon": "🧅", "echalote": "🧅", "échalote": "🧅",
        "ail": "🧄", "poireau": "🥬", "salade": "🥬", "chicorée": "🥬",
        "epinard": "🥬", "épinard": "🥬", "blette": "🥬", "chou": "🥬",
        "haricot": "🫘", "pois": "🫛", "fève": "🫘", "poivron": "🫑",
        "maïs": "🌽", "mais": "🌽", "basilic": "🌿", "persil": "🌿",
        "coriandre": "🌿", "ciboulette": "🌿", "fenouil": "🌿", "céleri": "🌿",
        "panais": "🥕", "rutabaga": "🥬",
    }

    def _emoji_pour_culture(self, culture: str) -> str:
        culture_min = culture.lower()
        for mot, emoji in self.EMOJIS_CULTURE.items():
            if mot in culture_min:
                return emoji
        return "🌱"

    def _build_onglet_fiches(self, parent):
        layout = QHBoxLayout(parent)

        gauche_box = QGroupBox()
        gauche_box.setMaximumWidth(280)
        gauche_layout = QVBoxLayout(gauche_box)

        gauche_layout.addWidget(QLabel("🔎 Rechercher :"))
        self.edit_fiche_recherche = QLineEdit()
        self.edit_fiche_recherche.setClearButtonEnabled(True)
        self.edit_fiche_recherche.textChanged.connect(self._filtrer_liste_fiches)
        gauche_layout.addWidget(self.edit_fiche_recherche)

        self.liste_fiches = QListWidget()
        self.liste_fiches.itemSelectionChanged.connect(self._afficher_fiche_selection)
        gauche_layout.addWidget(self.liste_fiches, 1)

        nav_layout = QHBoxLayout()
        btn_precedent = QPushButton("◀ Précédent")
        btn_precedent.clicked.connect(lambda: self._naviguer_fiche(-1))
        btn_suivant = QPushButton("Suivant ▶")
        btn_suivant.clicked.connect(lambda: self._naviguer_fiche(1))
        nav_layout.addWidget(btn_precedent)
        nav_layout.addWidget(btn_suivant)
        gauche_layout.addLayout(nav_layout)

        layout.addWidget(gauche_box)

        # ---- Partie droite : fiche technique détaillée, défilable ----
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        contenu = QWidget()
        droite_layout = QVBoxLayout(contenu)
        scroll.setWidget(contenu)

        self.lbl_fiche_titre = QLabel("Sélectionnez une culture")
        font_titre = QFont()
        font_titre.setPointSize(16)
        font_titre.setBold(True)
        self.lbl_fiche_titre.setFont(font_titre)
        droite_layout.addWidget(self.lbl_fiche_titre)

        self.lbl_fiche_sous_titre = QLabel("")
        self.lbl_fiche_sous_titre.setWordWrap(True)
        self.lbl_fiche_sous_titre.setStyleSheet(f"color: {COULEUR_INFO};")
        droite_layout.addWidget(self.lbl_fiche_sous_titre)

        self.lbl_fiche_variante = QLabel("")
        self.lbl_fiche_variante.setWordWrap(True)
        self.lbl_fiche_variante.setStyleSheet(f"color: {COULEUR_ACCENT}; font-style: italic;")
        self.lbl_fiche_variante.setVisible(False)
        droite_layout.addWidget(self.lbl_fiche_variante)

        # -- Groupe "carte d'identité" (nom latin, famille, cycle, gel) --
        box_identite = QGroupBox("🧬 Identité & cycle")
        form_identite = QFormLayout(box_identite)
        self.lbl_f_latin = self._creer_ligne_fiche(form_identite, "Nom latin")
        self.lbl_f_famille = self._creer_ligne_fiche(form_identite, "Famille botanique")
        self.lbl_f_cycle = self._creer_ligne_fiche(form_identite, "Temps de croissance")
        self.lbl_f_gel = self._creer_ligne_fiche(form_identite, "Résistance au gel")
        droite_layout.addWidget(box_identite)

        # -- Groupe "conditions de culture" (sol, ph, eau, hygrométrie, exposition) --
        box_conditions = QGroupBox("🌡️ Conditions de culture")
        form_conditions = QFormLayout(box_conditions)
        self.lbl_f_expo = self._creer_ligne_fiche(form_conditions, "Exposition")
        self.lbl_f_sol = self._creer_ligne_fiche(form_conditions, "Qualité du sol")
        self.lbl_f_ph = self._creer_ligne_fiche(form_conditions, "pH du sol")
        self.lbl_f_eau = self._creer_ligne_fiche(form_conditions, "Besoin en eau")
        self.lbl_f_hygro = self._creer_ligne_fiche(form_conditions, "Hygrométrie")
        droite_layout.addWidget(box_conditions)

        # -- Groupe "semis / plantation" (températures, espacement, profondeur) --
        box_semis = QGroupBox("🌱 Semis & plantation")
        form_semis = QFormLayout(box_semis)
        self.lbl_f_tgerm = self._creer_ligne_fiche(form_semis, "Température de germination")
        self.lbl_f_tcroiss = self._creer_ligne_fiche(form_semis, "Température de croissance")
        self.lbl_f_espacement = self._creer_ligne_fiche(form_semis, "Espacement")
        self.lbl_f_profondeur = self._creer_ligne_fiche(form_semis, "Profondeur de semis")
        droite_layout.addWidget(box_semis)

        # -- Groupe "entretien" (fertilisation, rotation) --
        box_entretien = QGroupBox("🧪 Fertilisation & rotation")
        form_entretien = QFormLayout(box_entretien)
        self.lbl_f_fertilisation = self._creer_ligne_fiche(form_entretien, "Fertilisation")
        self.lbl_f_rotation = self._creer_ligne_fiche(form_entretien, "Rotation")
        droite_layout.addWidget(box_entretien)

        # -- Groupe "maladies & ravageurs" --
        box_maladies = QGroupBox("🐛 Maladies & ravageurs courants")
        layout_maladies = QVBoxLayout(box_maladies)
        self.lbl_f_maladies = QLabel("")
        self.lbl_f_maladies.setWordWrap(True)
        layout_maladies.addWidget(self.lbl_f_maladies)
        droite_layout.addWidget(box_maladies)

        # -- Groupe "conseil de culture" --
        box_conseil = QGroupBox("💡 Conseil de culture")
        layout_conseil = QVBoxLayout(box_conseil)
        self.lbl_f_conseil = QLabel("")
        self.lbl_f_conseil.setWordWrap(True)
        self.lbl_f_conseil.setStyleSheet(f"color: {COULEUR_OK};")
        layout_conseil.addWidget(self.lbl_f_conseil)
        droite_layout.addWidget(box_conseil)

        # -- Groupe "calendrier détaillé" (issu du planning CSV) --
        box_calendrier = QGroupBox("🗓️ Calendrier détaillé (ce planning)")
        layout_calendrier = QVBoxLayout(box_calendrier)
        colonnes_fiche = ["Conduite", "Variété n°", "Action", "Semaines", "Mois", "Commentaire"]
        self.table_fiche = QTableWidget(0, len(colonnes_fiche))
        self.table_fiche.setHorizontalHeaderLabels(colonnes_fiche)
        self.table_fiche.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table_fiche.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table_fiche.setAlternatingRowColors(True)
        self.table_fiche.verticalHeader().setVisible(False)
        self.table_fiche.horizontalHeader().setStretchLastSection(True)
        for i, w in enumerate([90, 90, 140, 90, 130]):
            self.table_fiche.setColumnWidth(i, w)
        self.table_fiche.setMinimumHeight(220)
        self.table_fiche.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout_calendrier.addWidget(self.table_fiche)
        droite_layout.addWidget(box_calendrier)

        droite_layout.addStretch(1)

        layout.addWidget(scroll, 1)

        self._maj_liste_fiches()

    def _creer_ligne_fiche(self, form_layout: QFormLayout, libelle: str) -> QLabel:
        """Ajoute une ligne 'libellé : valeur' dans un QFormLayout et renvoie le
        QLabel de valeur (à mettre à jour ensuite via setText)."""
        lbl_libelle = QLabel(libelle)
        lbl_libelle.setStyleSheet("font-weight: bold;")
        lbl_valeur = QLabel("")
        lbl_valeur.setWordWrap(True)
        form_layout.addRow(lbl_libelle, lbl_valeur)
        return lbl_valeur

    def _maj_liste_fiches(self):
        self._toutes_cultures_fiches = sorted({r["culture"] for r in self.rows if r.get("culture")})
        self._filtrer_liste_fiches()

    def _filtrer_liste_fiches(self):
        texte = self.edit_fiche_recherche.text().strip().lower() if hasattr(self, "edit_fiche_recherche") else ""
        cultures = getattr(self, "_toutes_cultures_fiches", [])
        if texte:
            cultures = [c for c in cultures if texte in c.lower()]
        self.liste_fiches.blockSignals(True)
        self.liste_fiches.clear()
        for c in cultures:
            item = QListWidgetItem(f"{self._emoji_pour_culture(c)}  {c}")
            item.setData(Qt.UserRole, c)
            self.liste_fiches.addItem(item)
        self.liste_fiches.blockSignals(False)

    def _naviguer_fiche(self, pas: int):
        taille = self.liste_fiches.count()
        if taille == 0:
            return
        idx = self.liste_fiches.currentRow()
        idx = (idx + pas) if idx >= 0 else 0
        idx = max(0, min(taille - 1, idx))
        self.liste_fiches.setCurrentRow(idx)

    def _afficher_fiche_selection(self):
        item = self.liste_fiches.currentItem()
        if item is None:
            return
        culture = item.data(Qt.UserRole)
        lignes = [r for r in self.rows if r.get("culture") == culture]

        emoji = self._emoji_pour_culture(culture)
        self.lbl_fiche_titre.setText(f"{emoji}  {culture}")

        conduites = sorted({r["conduite"] for r in lignes})
        varietes = sorted({str(r.get("variete_n", "1")) for r in lignes}, key=lambda x: (len(x), x))
        self.lbl_fiche_sous_titre.setText(
            f"Conduite(s) : {', '.join(conduites)}  •  {len(varietes)} variété(s)/étalement(s) référencé(s)")

        # -- Renseignement de la fiche technique agronomique --
        fiche = fb.FICHES.get(culture)
        if fiche is None:
            self.lbl_f_latin.setText("—")
            self.lbl_f_famille.setText("—")
            self.lbl_f_cycle.setText("Aucune fiche technique disponible pour cette culture pour le moment.")
            for lbl in (self.lbl_f_gel, self.lbl_f_expo, self.lbl_f_sol, self.lbl_f_ph, self.lbl_f_eau,
                        self.lbl_f_hygro, self.lbl_f_tgerm, self.lbl_f_tcroiss, self.lbl_f_espacement,
                        self.lbl_f_profondeur, self.lbl_f_fertilisation, self.lbl_f_rotation):
                lbl.setText("—")
            self.lbl_f_maladies.setText("—")
            self.lbl_f_conseil.setText("—")
            self.lbl_fiche_variante.setVisible(False)
        else:
            self.lbl_f_latin.setText(fiche["nom_latin"])
            self.lbl_f_famille.setText(fiche["famille"])
            self.lbl_f_cycle.setText(fiche["cycle"])
            self.lbl_f_gel.setText(fiche["gel"])
            self.lbl_f_expo.setText(fiche["exposition"])
            self.lbl_f_sol.setText(fiche["sol"])
            self.lbl_f_ph.setText(fiche["ph"])
            self.lbl_f_eau.setText(fiche["eau"])
            self.lbl_f_hygro.setText(fiche["hygrometrie"])
            self.lbl_f_tgerm.setText(fiche["temp_germination"])
            self.lbl_f_tcroiss.setText(fiche["temp_croissance"])
            self.lbl_f_espacement.setText(fiche["espacement"])
            self.lbl_f_profondeur.setText(fiche["profondeur_semis"])
            self.lbl_f_fertilisation.setText(fiche["fertilisation"])
            self.lbl_f_rotation.setText(fiche["rotation"])
            self.lbl_f_maladies.setText(fiche["maladies"])
            self.lbl_f_conseil.setText(fiche["conseil"])
            if fiche.get("variante"):
                self.lbl_fiche_variante.setText(f"ℹ️ {fiche['variante']}")
                self.lbl_fiche_variante.setVisible(True)
            else:
                self.lbl_fiche_variante.setVisible(False)

        def cle_tri(r):
            try:
                return (r["conduite"], int(r.get("variete_n", 1)), int(r["semaine_debut"]))
            except (ValueError, TypeError):
                return (r["conduite"], 0, 0)

        lignes_triees = sorted(lignes, key=cle_tri)
        self.table_fiche.setRowCount(len(lignes_triees))
        for row_pos, r in enumerate(lignes_triees):
            semaines = f"{r.get('semaine_debut', '')}-{r.get('semaine_fin', '')}"
            mois = f"{r.get('mois_debut', '')} - {r.get('mois_fin', '')}"
            valeurs = [r.get("conduite", ""), r.get("variete_n", ""), r.get("action", ""),
                       semaines, mois, r.get("commentaire", "")]
            for col, v in enumerate(valeurs):
                self.table_fiche.setItem(row_pos, col, QTableWidgetItem(str(v)))


    # ============================================================
    # Onglet "Rotation des cultures"
    # ============================================================
    def _build_onglet_rotation(self, parent):
        layout = QHBoxLayout(parent)

        scroll_gauche = QScrollArea()
        scroll_gauche.setWidgetResizable(True)
        scroll_gauche.setFrameShape(QFrame.NoFrame)
        scroll_gauche.setMinimumWidth(300)
        scroll_gauche.setMaximumWidth(340)

        gauche = QWidget()
        gl = QVBoxLayout(gauche)
        scroll_gauche.setWidget(gauche)

        intro = QLabel(
            "Choisissez une culture pour savoir quoi mettre après, sur la même planche : "
            "cultures à éviter (même famille botanique) et cultures conseillées, en suivant "
            "un cycle classique légumineuse → gourmande → moyenne → peu exigeante."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet(f"color: {COULEUR_INFO}; font-style: italic; font-size: 9pt;")
        gl.addWidget(intro)

        box = QGroupBox("🔎 Culture actuelle")
        fbl = QVBoxLayout(box)
        self.rot_recherche = QLineEdit()
        self.rot_recherche.setPlaceholderText("Rechercher une culture...")
        self.rot_recherche.textChanged.connect(self._rot_filtrer)
        fbl.addWidget(self.rot_recherche)
        self.rot_liste = QListWidget()
        self.rot_liste.itemSelectionChanged.connect(self._rot_analyser)
        fbl.addWidget(self.rot_liste)
        gl.addWidget(box)
        gl.addStretch(1)

        layout.addWidget(scroll_gauche)

        droite = QWidget()
        dl = QVBoxLayout(droite)
        self.rot_rapport = QTextBrowser()
        dl.addWidget(self.rot_rapport, 2)

        lbl_ref = QLabel("Cultures par groupe (référence complète) :")
        lbl_ref.setStyleSheet("font-weight: bold;")
        dl.addWidget(lbl_ref)
        self.rot_table_groupes = QTableWidget()
        self.rot_table_groupes.setMaximumHeight(200)
        dl.addWidget(self.rot_table_groupes, 1)

        layout.addWidget(droite, 1)

        self._rot_filtrer("")
        self._rot_remplir_table_groupes()
        if self.rot_liste.count():
            self.rot_liste.setCurrentRow(0)

    def _rot_filtrer(self, texte):
        self.rot_liste.clear()
        for nom in rc.rechercher_cultures(texte):
            self.rot_liste.addItem(nom)

    def _rot_remplir_table_groupes(self):
        groupes = rc.cultures_par_groupe()
        lignes = [(g, ", ".join(noms)) for g, noms in groupes.items()]
        self._remplir_table(self.rot_table_groupes, ["Groupe (besoin en azote)", "Cultures"], lignes)
        self.rot_table_groupes.resizeRowsToContents()

    def _rot_analyser(self):
        item = self.rot_liste.currentItem()
        if not item:
            return
        r = rc.analyser_rotation(item.text())
        if not r:
            return
        self.rot_rapport.setHtml(self._generer_rapport_rotation_html(r))

    def _generer_rapport_rotation_html(self, r):
        def titre(t):
            return f'<h3 style="color:{COULEUR_ACCENT}; margin-bottom:2px;">{t}</h3>'

        def liste_cultures(entrees):
            if not entrees:
                return "<i>(aucune dans la base actuelle)</i>"
            return ", ".join(f"{e['nom']} <i>({rc.famille_courte(e['famille'])})</i>" for e in entrees)

        html = [f'<h2 style="color:{COULEUR_ACCENT};">{r["culture"]}</h2>']
        html.append(f"<b>Famille :</b> {r['famille']}<br>")
        html.append(f"<b>Groupe (besoin en azote) :</b> {r['groupe']}<br>")
        html.append(f"<b>Délai de retour conseillé sur la même parcelle :</b> {r['delai_retour_annees']} ans<br>")

        html.append(titre(f"❌ À éviter juste après {r['culture']} (même famille : {rc.famille_courte(r['famille'])})"))
        html.append(f"<p>{liste_cultures(r['a_eviter'])}</p>")

        html.append(titre(f"✅ Recommandé après {r['culture']} ({r['groupe_recommande']})"))
        html.append(f"<p>{liste_cultures(r['recommandees'])}</p>")

        html.append(titre(f"🙂 Aussi possible ({r['groupe_possible']})"))
        html.append(f"<p>{liste_cultures(r['possibles'])}</p>")

        html.append('<p style="font-size:9pt; color:#555;">Règle impérative : jamais deux cultures de la '
                     'même famille botanique à la suite. Règle recommandée : faire suivre les cultures '
                     'gourmandes en azote par des cultures de moins en moins exigeantes, puis relancer un '
                     'cycle avec une légumineuse ou un apport de compost.</p>')
        return "".join(html)

    # ============================================================
    # Onglet "Analyse de sol & Fertilisation" (GAB IDF)
    # ============================================================
    def _build_onglet_analyse_sol(self, parent):
        layout = QVBoxLayout(parent)

        intro = QLabel(
            "Portage de l'outil \"Calcul Ferti / Analyse de sol\" du GAB IDF (COMIFER / ARVALIS). "
            "Interprétation d'analyse de sol, bilan de fertilisation azotée (3 niveaux de précision) "
            "et tables de référence complètes du classeur."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet(f"color: {COULEUR_INFO}; font-style: italic;")
        layout.addWidget(intro)

        sous_tabs = QTabWidget()
        layout.addWidget(sous_tabs, 1)

        onglet_interp = QWidget()
        onglet_bilan = QWidget()
        onglet_refs = QWidget()
        sous_tabs.addTab(onglet_interp, "🧫 Interprétation du sol")
        sous_tabs.addTab(onglet_bilan, "🌿 Bilan azoté (COMIFER)")
        sous_tabs.addTab(onglet_refs, "📚 Références GAB IDF")

        self._build_sol_interpretation(onglet_interp)
        self._build_sol_bilan_azote(onglet_bilan)
        self._build_sol_references(onglet_refs)

    # ---------------- Utilitaires génériques (widgets) ----------------
    def _creer_carte_sol(self, titre, sous_texte, couleur, emoji=""):
        """Petite carte visuelle (QFrame avec liseré coloré)."""
        carte = QFrame()
        carte.setStyleSheet(
            f"QFrame {{ background-color: #f7f7f7; border-left: 5px solid {couleur}; "
            f"border-radius: 4px; padding: 6px; }}"
        )
        carte_layout = QVBoxLayout(carte)
        carte_layout.setContentsMargins(8, 6, 8, 6)
        carte_layout.setSpacing(2)

        lbl_titre = QLabel(f"{emoji}  {titre}" if emoji else titre)
        lbl_titre.setStyleSheet(f"font-weight: bold; color: {couleur};")
        lbl_titre.setWordWrap(True)
        carte_layout.addWidget(lbl_titre)

        if sous_texte:
            lbl_sous = QLabel(sous_texte)
            lbl_sous.setWordWrap(True)
            lbl_sous.setStyleSheet(f"color: {COULEUR_INFO}; font-size: 9pt;")
            carte_layout.addWidget(lbl_sous)

        return carte

    def _vider_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def _creer_spin_labo(self, minimum, maximum, decimales=1, suffixe=""):
        """QDoubleSpinBox pour une valeur facultative : -1 (affiché "Non
        renseigné") sert de sentinelle pour "champ vide", 0 étant une valeur
        de mesure valide."""
        spin = QDoubleSpinBox()
        spin.setRange(-1.0, maximum)
        spin.setDecimals(decimales)
        spin.setSingleStep(1.0 if decimales == 0 else 0.1)
        spin.setSpecialValueText(asol.NON_RENSEIGNE)
        spin.setSuffix(suffixe)
        spin.setValue(minimum if minimum >= 0 else -1.0)
        return spin

    def _lire_spin_labo(self, spin):
        v = spin.value()
        return None if v < 0 else round(v, spin.decimals())

    def _fmt(self, valeur, unite="", nd=2):
        if valeur is None:
            return "—"
        if isinstance(valeur, str):
            return valeur
        return f"{round(valeur, nd):,.{nd}f}".replace(",", " ") + (f" {unite}" if unite else "")

    def _remplir_table(self, table, colonnes, lignes):
        table.clear()
        table.setColumnCount(len(colonnes))
        table.setHorizontalHeaderLabels(colonnes)
        table.setRowCount(len(lignes))
        table.setWordWrap(True)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setAlternatingRowColors(True)
        for i, ligne in enumerate(lignes):
            for j, valeur in enumerate(ligne):
                item = QTableWidgetItem("" if valeur is None else str(valeur))
                table.setItem(i, j, item)
        table.resizeColumnsToContents()
        table.horizontalHeader().setStretchLastSection(True)
        table.verticalHeader().setVisible(False)

    # ---------------- Sous-onglet 1 : Interprétation du sol ----------------
    def _build_sol_interpretation(self, parent):
        layout = QHBoxLayout(parent)

        scroll_gauche = QScrollArea()
        scroll_gauche.setWidgetResizable(True)
        scroll_gauche.setFrameShape(QFrame.NoFrame)
        scroll_gauche.setMinimumWidth(360)
        scroll_gauche.setMaximumWidth(410)

        gauche = QWidget()
        gl = QVBoxLayout(gauche)
        scroll_gauche.setWidget(gauche)

        note = QLabel("Tous les champs sont facultatifs : plus vous en renseignez, plus l'analyse "
                       "est complète. Les valeurs par défaut reprennent l'exemple du classeur GAB IDF.")
        note.setWordWrap(True)
        note.setStyleSheet(f"color: {COULEUR_INFO}; font-style: italic; font-size: 9pt;")
        gl.addWidget(note)

        # -- Poids de terre fine --
        box_ptf = QGroupBox("⚖️ Poids de terre fine")
        f = QFormLayout(box_ptf)
        self.si_profondeur = QDoubleSpinBox()
        self.si_profondeur.setRange(0, 100)
        self.si_profondeur.setValue(20)
        self.si_profondeur.setSuffix(" cm")
        f.addRow("Profondeur :", self.si_profondeur)

        self.si_texture = QComboBox()
        self.si_texture.addItem("— choisir pour pré-remplir la densité —")
        for appreciation, texture, code, densite in asol.DENSITE_SOL_PAR_TEXTURE:
            self.si_texture.addItem(f"{texture} ({code}) — {densite} T/m³", densite)
        self.si_texture.currentIndexChanged.connect(self._si_texture_changee)
        f.addRow("Texture (Aide) :", self.si_texture)

        self.si_densite = QDoubleSpinBox()
        self.si_densite.setRange(0.5, 2.5)
        self.si_densite.setSingleStep(0.01)
        self.si_densite.setDecimals(2)
        self.si_densite.setValue(1.45)
        self.si_densite.setSuffix(" T/m³")
        f.addRow("Densité :", self.si_densite)

        self.si_pierrosite = QDoubleSpinBox()
        self.si_pierrosite.setRange(0, 90)
        self.si_pierrosite.setValue(0)
        self.si_pierrosite.setSuffix(" %")
        f.addRow("Pierrosité :", self.si_pierrosite)
        gl.addWidget(box_ptf)

        # -- CEC --
        box_cec = QGroupBox("🧲 CEC")
        f = QFormLayout(box_cec)
        self.si_cec = self._creer_spin_labo(-1, 60, decimales=1, suffixe=" meq/100g")
        f.addRow("CEC :", self.si_cec)
        gl.addWidget(box_cec)

        # -- Granulométrie / seuils P-K --
        box_granulo = QGroupBox("🏖️ Granulométrie et seuils P2O5 / K2O")
        f = QFormLayout(box_granulo)
        self.si_argile = self._creer_spin_labo(-1, 100, decimales=1, suffixe=" %")
        f.addRow("Argile :", self.si_argile)
        self.si_limons_fins = self._creer_spin_labo(-1, 100, decimales=1, suffixe=" %")
        f.addRow("Limons fins :", self.si_limons_fins)
        self.si_limons_grossiers = self._creer_spin_labo(-1, 100, decimales=1, suffixe=" %")
        f.addRow("Limons grossiers :", self.si_limons_grossiers)
        self.si_sables_fins = self._creer_spin_labo(-1, 100, decimales=1, suffixe=" %")
        f.addRow("Sables fins :", self.si_sables_fins)
        self.si_sables_grossiers = self._creer_spin_labo(-1, 100, decimales=1, suffixe=" %")
        f.addRow("Sables grossiers :", self.si_sables_grossiers)

        self.si_type_sol = QComboBox()
        self.si_type_sol.addItems(asol.TYPES_SOL_CBP)
        f.addRow("Type de sol (grille Centre Bassin parisien) :", self.si_type_sol)

        self.si_exigence = QComboBox()
        self.si_exigence.addItems(["forte (maraîchage)", "moyenne", "faible"])
        f.addRow("Exigence de la culture :", self.si_exigence)

        btn_seuils = QPushButton("🔄 Pré-remplir Trenf/Timp depuis la grille")
        btn_seuils.clicked.connect(self._si_preremplir_seuils)
        f.addRow(btn_seuils)

        self.si_trenf_p2o5 = self._creer_spin_labo(-1, 500, decimales=0, suffixe=" ppm")
        f.addRow("Trenf P2O5 :", self.si_trenf_p2o5)
        self.si_timp_p2o5 = self._creer_spin_labo(-1, 500, decimales=0, suffixe=" ppm")
        f.addRow("Timp P2O5 :", self.si_timp_p2o5)
        self.si_trenf_k2o = self._creer_spin_labo(-1, 800, decimales=0, suffixe=" ppm")
        f.addRow("Trenf K2O :", self.si_trenf_k2o)
        self.si_timp_k2o = self._creer_spin_labo(-1, 800, decimales=0, suffixe=" ppm")
        f.addRow("Timp K2O :", self.si_timp_k2o)
        gl.addWidget(box_granulo)

        # -- Analyse chimique --
        box_chimie = QGroupBox("⚗️ Analyse chimique")
        f = QFormLayout(box_chimie)
        self.si_ph_eau = self._creer_spin_labo(-1, 9.5, decimales=1, suffixe="")
        f.addRow("pH eau (hiver) :", self.si_ph_eau)
        self.si_ph_kcl = self._creer_spin_labo(-1, 9.5, decimales=1, suffixe="")
        f.addRow("pH KCl :", self.si_ph_kcl)
        self.si_caco3 = self._creer_spin_labo(-1, 50, decimales=2, suffixe=" %")
        f.addRow("CaCO3 :", self.si_caco3)
        self.si_cao = self._creer_spin_labo(-1, 10000, decimales=0, suffixe=" ppm")
        f.addRow("CaO :", self.si_cao)
        gl.addWidget(box_chimie)

        # -- Éléments majeurs --
        box_maj = QGroupBox("🧪 Éléments majeurs (Olsen)")
        f = QFormLayout(box_maj)
        self.si_p2o5 = self._creer_spin_labo(-1, 1000, decimales=0, suffixe=" ppm")
        f.addRow("P2O5 :", self.si_p2o5)
        self.si_k2o = self._creer_spin_labo(-1, 1000, decimales=0, suffixe=" ppm")
        f.addRow("K2O :", self.si_k2o)
        self.si_mgo = self._creer_spin_labo(-1, 1000, decimales=0, suffixe=" ppm")
        f.addRow("MgO :", self.si_mgo)
        gl.addWidget(box_maj)

        # -- Oligo-éléments --
        box_oligo = QGroupBox("🔬 Oligo-éléments")
        f = QFormLayout(box_oligo)
        self.si_zn = self._creer_spin_labo(-1, 100, decimales=2, suffixe=" ppm")
        f.addRow("Zn (Zinc) :", self.si_zn)
        self.si_mn = self._creer_spin_labo(-1, 300, decimales=1, suffixe=" ppm")
        f.addRow("Mn (Manganèse) :", self.si_mn)
        self.si_cu = self._creer_spin_labo(-1, 100, decimales=2, suffixe=" ppm")
        f.addRow("Cu (Cuivre) :", self.si_cu)
        self.si_fe = self._creer_spin_labo(-1, 500, decimales=1, suffixe=" ppm")
        f.addRow("Fe (Fer) :", self.si_fe)
        self.si_b = self._creer_spin_labo(-1, 10, decimales=2, suffixe=" ppm")
        f.addRow("B (Bore) :", self.si_b)
        gl.addWidget(box_oligo)

        # -- MO / C/N / Bilan humique --
        box_mo = QGroupBox("🌱 MO, C/N, Bilan humique et chaulage")
        f = QFormLayout(box_mo)
        self.si_mo = self._creer_spin_labo(-1, 30, decimales=2, suffixe=" %")
        f.addRow("Matière organique (MO) :", self.si_mo)
        self.si_carbone = self._creer_spin_labo(-1, 20, decimales=2, suffixe=" %")
        f.addRow("Carbone :", self.si_carbone)
        self.si_azote_total = self._creer_spin_labo(-1, 5, decimales=2, suffixe=" %")
        f.addRow("Azote total :", self.si_azote_total)
        self.si_cn = self._creer_spin_labo(-1, 40, decimales=1, suffixe="")
        f.addRow("C/N :", self.si_cn)
        self.si_temp_moy = self._creer_spin_labo(-1, 30, decimales=1, suffixe=" °C")
        f.addRow("Température moyenne (infoclimat.fr) :", self.si_temp_moy)

        info_amdt = QLabel("Amendement de référence pour les apports MO (par défaut : Compost de "
                            "déchets verts, valeurs de l'exemple GAB IDF) :")
        info_amdt.setWordWrap(True)
        info_amdt.setStyleSheet(f"color: {COULEUR_INFO}; font-size: 9pt;")
        f.addRow(info_amdt)
        self.si_taux_mo_produit = QDoubleSpinBox()
        self.si_taux_mo_produit.setRange(1, 100)
        self.si_taux_mo_produit.setValue(25.0)
        self.si_taux_mo_produit.setSuffix(" % MO")
        f.addRow("Taux de MO du produit :", self.si_taux_mo_produit)
        self.si_ismo_produit = QDoubleSpinBox()
        self.si_ismo_produit.setRange(1, 100)
        self.si_ismo_produit.setValue(80.0)
        self.si_ismo_produit.setSuffix(" % ISMO")
        f.addRow("ISMO du produit :", self.si_ismo_produit)

        self.si_ph_souhaite = QDoubleSpinBox()
        self.si_ph_souhaite.setRange(5, 9)
        self.si_ph_souhaite.setValue(7.5)
        f.addRow("pH souhaité (chaulage) :", self.si_ph_souhaite)
        self.si_caco3_souhaite = QDoubleSpinBox()
        self.si_caco3_souhaite.setRange(0, 50)
        self.si_caco3_souhaite.setValue(3.0)
        self.si_caco3_souhaite.setSuffix(" g/kg")
        f.addRow("CaCO3 souhaité :", self.si_caco3_souhaite)

        self.si_km2828 = self._creer_spin_labo(-1, 100, decimales=1, suffixe=" ‰")
        f.addRow("Km 28°C/28j mesuré (si analyse bio.) :", self.si_km2828)
        gl.addWidget(box_mo)

        btn_layout = QHBoxLayout()
        self.btn_analyser_sol = QPushButton("🔍 Analyser la parcelle")
        self.btn_analyser_sol.setStyleSheet(
            f"QPushButton {{ background-color: {COULEUR_ACCENT}; color: white; "
            f"font-weight: bold; padding: 6px; border-radius: 5px; }}"
        )
        self.btn_analyser_sol.clicked.connect(self._analyser_sol_asol)
        btn_layout.addWidget(self.btn_analyser_sol)
        self.btn_reinit_sol = QPushButton("♻️ Réinitialiser")
        self.btn_reinit_sol.clicked.connect(self._reinitialiser_sol_asol)
        btn_layout.addWidget(self.btn_reinit_sol)
        gl.addLayout(btn_layout)
        gl.addStretch(1)

        layout.addWidget(scroll_gauche)

        # ---------------------------------------------------- Colonne droite : résultats
        droite = QWidget()
        dl = QVBoxLayout(droite)

        self.si_rapport = QTextBrowser()
        self.si_rapport.setOpenExternalLinks(True)
        dl.addWidget(self.si_rapport, 2)

        lbl_table = QLabel("Minéralisation mensuelle de l'humus (Mh) :")
        lbl_table.setStyleSheet("font-weight: bold;")
        dl.addWidget(lbl_table)
        self.si_table_mensuelle = QTableWidget()
        self.si_table_mensuelle.setMaximumHeight(280)
        dl.addWidget(self.si_table_mensuelle, 1)

        layout.addWidget(droite, 1)

        self._analyser_sol_asol()

    def _si_texture_changee(self, index):
        densite = self.si_texture.itemData(index)
        if densite:
            self.si_densite.setValue(densite)

    def _si_preremplir_seuils(self):
        type_sol = self.si_type_sol.currentText()
        exigence = self.si_exigence.currentText().split(" ")[0]
        seuils_p = asol.SEUILS_P2O5_CENTRE_BASSIN_PARISIEN.get(type_sol, {}).get(exigence)
        seuils_k = asol.SEUILS_K2O_CENTRE_BASSIN_PARISIEN.get(type_sol, {}).get(exigence)
        if seuils_p:
            self.si_trenf_p2o5.setValue(seuils_p[0])
            self.si_timp_p2o5.setValue(seuils_p[1])
        if seuils_k:
            self.si_trenf_k2o.setValue(seuils_k[0])
            self.si_timp_k2o.setValue(seuils_k[1])

    def _lire_donnees_sol(self):
        return dict(
            profondeur_cm=self.si_profondeur.value(),
            densite_t_m3=self.si_densite.value(),
            pierrosite_pct=self.si_pierrosite.value(),
            cec=self._lire_spin_labo(self.si_cec),
            argile_pct=self._lire_spin_labo(self.si_argile),
            limons_fins_pct=self._lire_spin_labo(self.si_limons_fins),
            limons_grossiers_pct=self._lire_spin_labo(self.si_limons_grossiers),
            sables_fins_pct=self._lire_spin_labo(self.si_sables_fins),
            sables_grossiers_pct=self._lire_spin_labo(self.si_sables_grossiers),
            type_sol=self.si_type_sol.currentText(),
            trenf_p2o5=self._lire_spin_labo(self.si_trenf_p2o5),
            timp_p2o5=self._lire_spin_labo(self.si_timp_p2o5),
            trenf_k2o=self._lire_spin_labo(self.si_trenf_k2o),
            timp_k2o=self._lire_spin_labo(self.si_timp_k2o),
            ph_eau=self._lire_spin_labo(self.si_ph_eau),
            ph_kcl=self._lire_spin_labo(self.si_ph_kcl),
            caco3_pct=self._lire_spin_labo(self.si_caco3),
            cao_ppm=self._lire_spin_labo(self.si_cao),
            p2o5_ppm=self._lire_spin_labo(self.si_p2o5),
            k2o_ppm=self._lire_spin_labo(self.si_k2o),
            mgo_ppm=self._lire_spin_labo(self.si_mgo),
            zn_ppm=self._lire_spin_labo(self.si_zn),
            mn_ppm=self._lire_spin_labo(self.si_mn),
            cu_ppm=self._lire_spin_labo(self.si_cu),
            fe_ppm=self._lire_spin_labo(self.si_fe),
            b_ppm=self._lire_spin_labo(self.si_b),
            mo_pct=self._lire_spin_labo(self.si_mo),
            carbone_pct=self._lire_spin_labo(self.si_carbone),
            azote_total_pct=self._lire_spin_labo(self.si_azote_total),
            c_n=self._lire_spin_labo(self.si_cn),
            temperature_moy_c=self._lire_spin_labo(self.si_temp_moy),
            taux_mo_produit_pct=self.si_taux_mo_produit.value(),
            ismo_produit_pct=self.si_ismo_produit.value(),
            ph_souhaite=self.si_ph_souhaite.value(),
            caco3_souhaite_g_kg=self.si_caco3_souhaite.value(),
            km_28_28j=self._lire_spin_labo(self.si_km2828),
        )

    def _reinitialiser_sol_asol(self):
        self.si_profondeur.setValue(20)
        self.si_texture.setCurrentIndex(0)
        self.si_densite.setValue(1.45)
        self.si_pierrosite.setValue(0)
        for spin in (self.si_cec, self.si_argile, self.si_limons_fins, self.si_limons_grossiers,
                     self.si_sables_fins, self.si_sables_grossiers, self.si_trenf_p2o5,
                     self.si_timp_p2o5, self.si_trenf_k2o, self.si_timp_k2o, self.si_ph_eau,
                     self.si_ph_kcl, self.si_caco3, self.si_cao, self.si_p2o5, self.si_k2o,
                     self.si_mgo, self.si_zn, self.si_mn, self.si_cu, self.si_fe, self.si_b,
                     self.si_mo, self.si_carbone, self.si_azote_total, self.si_cn,
                     self.si_temp_moy, self.si_km2828):
            spin.setValue(-1.0)
        self.si_type_sol.setCurrentIndex(0)
        self.si_exigence.setCurrentIndex(0)
        self.si_taux_mo_produit.setValue(25.0)
        self.si_ismo_produit.setValue(80.0)
        self.si_ph_souhaite.setValue(7.5)
        self.si_caco3_souhaite.setValue(3.0)
        self._analyser_sol_asol()

    def _analyser_sol_asol(self):
        donnees = self._lire_donnees_sol()
        r = asol.analyser_parcelle(donnees)
        self.si_rapport.setHtml(self._generer_rapport_sol_html(r))
        self._remplir_table_mensuelle(r.get("mineralisation_mensuelle"))

    def _generer_rapport_sol_html(self, r):
        def titre(t):
            return f'<h3 style="color:{COULEUR_ACCENT}; margin-bottom:2px;">{t}</h3>'

        def ligne(label, valeur, unite="", nd=2):
            return f"<b>{label}</b> : {self._fmt(valeur, unite, nd)}<br>"

        html = []
        html.append(titre("⚖️ Poids de terre fine"))
        html.append(ligne("Poids de terre fine", r.get("poids_terre_fine_t_ha"), "T/ha", 0))

        html.append(titre("🧲 CEC"))
        html.append(ligne("CEC", r.get("cec"), "meq/100g"))

        html.append(titre("🌡️ pH"))
        html.append(ligne("pH eau (hiver)", r.get("ph_eau")))
        html.append(ligne("pH KCl", r.get("ph_kcl")))
        html.append(ligne("pH minimal été (écart classeur, -0,7)", r.get("ph_minimal_ete_excel")))
        if r.get("ecart_ph_saisonnier_recommande"):
            libelle, ecart = r["ecart_ph_saisonnier_recommande"]
            html.append(ligne(f"pH minimal été affiné ({libelle}, écart {ecart})",
                               r.get("ph_minimal_ete_affine")))
        html.append('<span style="font-size:9pt; color:#555;">Le pH doit idéalement rester entre '
                     '6 et 7,5 toute l\'année.</span><br>')

        html.append(titre("🧪 Éléments majeurs"))
        html.append(ligne("P2O5", r.get("p2o5_ppm"), "ppm", 0) )
        html.append(ligne("→ soit", r.get("p2o5_kg_ha"), "kg/ha", 0))
        if r.get("categorie_p2o5"):
            html.append(f'<span style="color:{COULEUR_ACCENT};">Positionnement : {r["categorie_p2o5"]}</span><br>')
        html.append(ligne("K2O", r.get("k2o_ppm"), "ppm", 0))
        html.append(ligne("→ soit", r.get("k2o_kg_ha"), "kg/ha", 0))
        if r.get("categorie_k2o"):
            html.append(f'<span style="color:{COULEUR_ACCENT};">Positionnement : {r["categorie_k2o"]}</span><br>')
        html.append(ligne("MgO", r.get("mgo_ppm"), "ppm", 0))
        html.append(ligne("→ soit", r.get("mgo_kg_ha"), "kg/ha", 0))

        oligo = r.get("oligoelements") or {}
        if any(v is not None for v in oligo.values()):
            html.append(titre("🔬 Oligo-éléments"))
            for k, v in oligo.items():
                html.append(ligne(k, v, "ppm"))

        html.append(titre("🌱 MO, C/N, Bilan humique"))
        html.append(ligne("MO", r.get("mo_pct"), "%"))
        html.append(ligne("Carbone", r.get("carbone_pct"), "%"))
        html.append(ligne("Azote total", r.get("azote_total_pct"), "%"))
        html.append(ligne("→ soit", r.get("azote_total_kg_ha"), "kg N/ha"))
        html.append(ligne("C/N", r.get("c_n"), ""))
        seuils_mo = r.get("seuils_mo_argile")
        if seuils_mo:
            html.append("<i>Repères MO selon le taux d'argile :</i><br>")
            for k, v in seuils_mo.items():
                html.append(ligne(f"&nbsp;&nbsp;{k}", v, "%"))
        html.append(ligne("Apport pour +1 point de MO", r.get("apport_mo_plus1point_t_ha"), "T/ha"))
        html.append(ligne("Coefficient de minéralisation K2", r.get("k2_pct"), "%"))
        html.append(ligne("Perte d'humus annuelle", r.get("perte_humus_kg_ha_an"), "kg N/ha/an", 0))
        html.append(ligne("Apport pour compenser la perte annuelle", r.get("apport_compensation_perte_humus_t_ha"), "T/ha"))

        html.append(titre("🧱 Indice de battance"))
        html.append(ligne("IB", r.get("indice_battance"), ""))
        if r.get("categorie_battance"):
            html.append(f'<span style="color:{COULEUR_ACCENT};">{r["categorie_battance"]}</span><br>')

        html.append(titre("🪨 Chaulage (BEB)"))
        html.append(ligne("BEB — option pH", r.get("beb_option_ph_t_ha"), "t/ha"))
        html.append(ligne("BEB — option CaCO3", r.get("beb_option_caco3_t_ha"), "t/ha"))
        if r.get("strategie_chaulage"):
            html.append(f'<span style="font-size:9pt;">{r["strategie_chaulage"]}</span><br>')

        html.append(titre("🧬 Minéralisation de l'azote humifié (Km)"))
        html.append(ligne("Km jour standard (COMIFER)", r.get("km_jour_standard_pour_mille"), "‰"))
        if r.get("km_jour_mesure_pour_mille") is not None:
            html.append(ligne("Km jour mesuré (analyse bio.)", r.get("km_jour_mesure_pour_mille"), "‰"))
        if r.get("mineralisation_mensuelle"):
            html.append(ligne("Mh cumulé sur l'année (voir tableau ci-dessous)",
                               r["mineralisation_mensuelle"][-1]["mh_cumule"], "kg N/ha"))

        return "".join(html)

    def _remplir_table_mensuelle(self, mensuel):
        if not mensuel:
            self.si_table_mensuelle.clear()
            self.si_table_mensuelle.setRowCount(0)
            self.si_table_mensuelle.setColumnCount(0)
            return
        colonnes = ["Mois", "JN mensuel", "Km mensuel (‰)", "Mh (kg N/ha)", "Mh cumulé (kg N/ha)"]
        lignes = [
            (m["mois"], f"{m['jn']:.1f}", f"{m['km_mensuel']:.3f}",
             f"{m['mh']:.1f}", f"{m['mh_cumule']:.1f}")
            for m in mensuel
        ]
        self._remplir_table(self.si_table_mensuelle, colonnes, lignes)

    # ---------------- Sous-onglet 2 : Bilan azoté ----------------
    def _build_sol_bilan_azote(self, parent):
        layout = QHBoxLayout(parent)

        scroll_gauche = QScrollArea()
        scroll_gauche.setWidgetResizable(True)
        scroll_gauche.setFrameShape(QFrame.NoFrame)
        scroll_gauche.setMinimumWidth(380)
        scroll_gauche.setMaximumWidth(430)

        gauche = QWidget()
        gl = QVBoxLayout(gauche)
        scroll_gauche.setWidget(gauche)

        box_cultures = QGroupBox("🥕 Cultures (besoins NPK, mob./exp. GAB IDF)")
        fc = QVBoxLayout(box_cultures)
        self.ba_recherche = QLineEdit()
        self.ba_recherche.setPlaceholderText("Rechercher une culture ou une famille...")
        self.ba_recherche.textChanged.connect(self._ba_filtrer_cultures)
        fc.addWidget(self.ba_recherche)
        self.ba_liste_cultures = QListWidget()
        self.ba_liste_cultures.setMaximumHeight(140)
        fc.addWidget(self.ba_liste_cultures)
        btn_ajouter = QPushButton("➕ Ajouter à la sélection")
        btn_ajouter.clicked.connect(self._ba_ajouter_culture)
        fc.addWidget(btn_ajouter)

        fc.addWidget(QLabel("Cultures sélectionnées (besoins sommés) :"))
        self.ba_liste_selection = QListWidget()
        self.ba_liste_selection.setMaximumHeight(90)
        fc.addWidget(self.ba_liste_selection)
        btn_retirer = QPushButton("➖ Retirer la sélection")
        btn_retirer.clicked.connect(self._ba_retirer_culture)
        fc.addWidget(btn_retirer)
        gl.addWidget(box_cultures)

        self._ba_filtrer_cultures("")

        box_methode = QGroupBox("📐 Méthode de bilan")
        fm = QFormLayout(box_methode)
        self.ba_methode = QComboBox()
        self.ba_methode.addItems(["1. Bilan Simple", "2. Bilan Intermédiaire", "3. Bilan Avancé"])
        self.ba_methode.currentIndexChanged.connect(self._ba_methode_changee)
        fm.addRow("Niveau de précision :", self.ba_methode)
        self.ba_surface = QDoubleSpinBox()
        self.ba_surface.setRange(1, 100000)
        self.ba_surface.setValue(60)
        self.ba_surface.setSuffix(" m²")
        fm.addRow("Surface d'apport :", self.ba_surface)
        gl.addWidget(box_methode)

        box_produit = QGroupBox("🧴 Produit / engrais-amendement choisi")
        fp = QFormLayout(box_produit)
        self.ba_produit_ref = QComboBox()
        self.ba_produit_ref.addItem("— saisie manuelle —")
        for e in asol.ENGRAIS_AMENDEMENTS:
            self.ba_produit_ref.addItem(e["nom"], e)
        self.ba_produit_ref.currentIndexChanged.connect(self._ba_produit_changee)
        fp.addRow("Produit de référence :", self.ba_produit_ref)
        self.ba_pct_n = QDoubleSpinBox(); self.ba_pct_n.setRange(0, 100); self.ba_pct_n.setDecimals(2)
        self.ba_pct_n.setValue(0.58); self.ba_pct_n.setSuffix(" %")
        fp.addRow("NPK PRO — N (%) :", self.ba_pct_n)
        self.ba_pct_p = QDoubleSpinBox(); self.ba_pct_p.setRange(0, 100); self.ba_pct_p.setDecimals(2)
        self.ba_pct_p.setValue(0.32); self.ba_pct_p.setSuffix(" %")
        fp.addRow("NPK PRO — P2O5 (%) :", self.ba_pct_p)
        self.ba_pct_k = QDoubleSpinBox(); self.ba_pct_k.setRange(0, 100); self.ba_pct_k.setDecimals(2)
        self.ba_pct_k.setValue(0.93); self.ba_pct_k.setSuffix(" %")
        fp.addRow("NPK PRO — K2O (%) :", self.ba_pct_k)
        gl.addWidget(box_produit)

        # -- Coefficient sol + Keq (Intermédiaire / Avancé) --
        self.ba_box_coef_keq = QGroupBox("🧮 Coefficients (sol et équivalence)")
        fk = QFormLayout(self.ba_box_coef_keq)
        self.ba_coef_p = QDoubleSpinBox(); self.ba_coef_p.setRange(0, 3); self.ba_coef_p.setDecimals(2)
        self.ba_coef_p.setValue(1.0)
        fk.addRow("Coef. multiplicatif analyse de sol — P2O5 :", self.ba_coef_p)
        self.ba_coef_k = QDoubleSpinBox(); self.ba_coef_k.setRange(0, 3); self.ba_coef_k.setDecimals(2)
        self.ba_coef_k.setValue(1.0)
        fk.addRow("Coef. multiplicatif analyse de sol — K2O :", self.ba_coef_k)
        self.ba_keq_n = QDoubleSpinBox(); self.ba_keq_n.setRange(0.01, 1); self.ba_keq_n.setDecimals(2)
        self.ba_keq_n.setValue(0.3)
        fk.addRow("Keq N :", self.ba_keq_n)
        self.ba_keq_p = QDoubleSpinBox(); self.ba_keq_p.setRange(0.01, 1); self.ba_keq_p.setDecimals(2)
        self.ba_keq_p.setValue(0.8)
        fk.addRow("Keq P2O5 :", self.ba_keq_p)
        self.ba_keq_k = QDoubleSpinBox(); self.ba_keq_k.setRange(0.01, 1); self.ba_keq_k.setDecimals(2)
        self.ba_keq_k.setValue(1.0)
        fk.addRow("Keq K2O :", self.ba_keq_k)
        gl.addWidget(self.ba_box_coef_keq)

        # -- Postes Intermédiaire --
        self.ba_box_intermediaire = QGroupBox("💧 Reliquats et minéralisation (kg/ha)")
        fi = QVBoxLayout(self.ba_box_intermediaire)
        self.ba_table_intermediaire = QTableWidget(1, 3)
        self.ba_table_intermediaire.setHorizontalHeaderLabels(["N", "P2O5", "K2O"])
        self.ba_table_intermediaire.setVerticalHeaderLabels(["Reliquats + minéralisation"])
        for j in range(3):
            self.ba_table_intermediaire.setItem(0, j, QTableWidgetItem("0"))
        self.ba_table_intermediaire.setMaximumHeight(70)
        fi.addWidget(self.ba_table_intermediaire)
        gl.addWidget(self.ba_box_intermediaire)

        # -- Postes Avancé --
        self.ba_box_avance = QGroupBox("💧 Postes détaillés du bilan (kg/ha)")
        fa = QVBoxLayout(self.ba_box_avance)
        lignes_avance = ["Reliquats", "Pertes lixiviation", "Minéralisation humus", "Résidus",
                          "Couverts", "Irrigation", "Autres apports 1", "Autres apports 2"]
        self.ba_table_avance = QTableWidget(len(lignes_avance), 3)
        self.ba_table_avance.setHorizontalHeaderLabels(["N", "P2O5", "K2O"])
        self.ba_table_avance.setVerticalHeaderLabels(lignes_avance)
        for i in range(len(lignes_avance)):
            for j in range(3):
                self.ba_table_avance.setItem(i, j, QTableWidgetItem("0"))
        self.ba_table_avance.setMaximumHeight(220)
        fa.addWidget(self.ba_table_avance)
        note_lix = QLabel("Pertes par lixiviation : seul poste ADDITIONNÉ au besoin (voir abaque "
                           "COMIFER) ; tous les autres postes sont déduits.")
        note_lix.setWordWrap(True)
        note_lix.setStyleSheet(f"color: {COULEUR_INFO}; font-size: 9pt;")
        fa.addWidget(note_lix)
        gl.addWidget(self.ba_box_avance)

        btn_calc = QPushButton("🧮 Calculer le bilan")
        btn_calc.setStyleSheet(
            f"QPushButton {{ background-color: {COULEUR_ACCENT}; color: white; "
            f"font-weight: bold; padding: 6px; border-radius: 5px; }}"
        )
        btn_calc.clicked.connect(self._calculer_bilan_azote)
        gl.addWidget(btn_calc)
        gl.addStretch(1)

        layout.addWidget(scroll_gauche)

        droite = QWidget()
        dl = QVBoxLayout(droite)
        self.ba_rapport = QTextBrowser()
        dl.addWidget(self.ba_rapport, 1)
        layout.addWidget(droite, 1)

        self._ba_methode_changee(0)
        self._calculer_bilan_azote()

    def _ba_filtrer_cultures(self, texte):
        self.ba_liste_cultures.clear()
        for c in asol.rechercher_cultures_bilan(texte):
            label = f"{c['espece']} ({c['type']}, {c['famille']}) — N {self._fmt(c['N'],'',0)} / P {self._fmt(c['P'],'',0)} / K {self._fmt(c['K'],'',0)}"
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, c)
            self.ba_liste_cultures.addItem(item)

    def _ba_ajouter_culture(self):
        item = self.ba_liste_cultures.currentItem()
        if not item:
            return
        c = item.data(Qt.UserRole)
        nouvel_item = QListWidgetItem(f"{c['espece']} ({c['type']})")
        nouvel_item.setData(Qt.UserRole, c)
        self.ba_liste_selection.addItem(nouvel_item)

    def _ba_retirer_culture(self):
        for item in self.ba_liste_selection.selectedItems():
            self.ba_liste_selection.takeItem(self.ba_liste_selection.row(item))

    def _ba_methode_changee(self, index):
        self.ba_box_coef_keq.setVisible(index >= 1)
        self.ba_box_intermediaire.setVisible(index == 1)
        self.ba_box_avance.setVisible(index == 2)

    def _ba_produit_changee(self, index):
        e = self.ba_produit_ref.itemData(index)
        if not e:
            return
        self.ba_pct_n.setValue(e.get("N_kg_t") / 10 if e.get("N_kg_t") else 0)
        self.ba_pct_p.setValue(e.get("P2O5_kg_t") / 10 if e.get("P2O5_kg_t") else 0)
        self.ba_pct_k.setValue(e.get("K2O_kg_t") / 10 if e.get("K2O_kg_t") else 0)
        if e.get("KeqN"):
            self.ba_keq_n.setValue(e["KeqN"])
        if e.get("KeqP2O5"):
            self.ba_keq_p.setValue(e["KeqP2O5"])
        if e.get("KeqK2O"):
            self.ba_keq_k.setValue(e["KeqK2O"])

    def _ba_lire_table(self, table, libelle):
        for i in range(table.rowCount()):
            if table.verticalHeaderItem(i) and table.verticalHeaderItem(i).text() == libelle:
                def val(j):
                    item = table.item(i, j)
                    try:
                        return float(item.text().replace(",", ".")) if item and item.text() else 0.0
                    except ValueError:
                        return 0.0
                return {"N": val(0), "P2O5": val(1), "K2O": val(2)}
        return {"N": 0.0, "P2O5": 0.0, "K2O": 0.0}

    def _calculer_bilan_azote(self):
        besoins = {"N": 0.0, "P2O5": 0.0, "K2O": 0.0}
        noms_cultures = []
        for i in range(self.ba_liste_selection.count()):
            c = self.ba_liste_selection.item(i).data(Qt.UserRole)
            besoins["N"] += c.get("N") or 0
            besoins["P2O5"] += c.get("P") or 0
            besoins["K2O"] += c.get("K") or 0
            noms_cultures.append(c["espece"])

        surface = self.ba_surface.value()
        produit_pct = {"N": self.ba_pct_n.value(), "P2O5": self.ba_pct_p.value(), "K2O": self.ba_pct_k.value()}
        methode_idx = self.ba_methode.currentIndex()

        if methode_idx == 0:
            resultat = asol.bilan_simple(besoins, surface, produit_pct)
        elif methode_idx == 1:
            coef_sol = {"P2O5": self.ba_coef_p.value(), "K2O": self.ba_coef_k.value()}
            reliquats = self._ba_lire_table(self.ba_table_intermediaire, "Reliquats + minéralisation")
            keq = {"N": self.ba_keq_n.value(), "P2O5": self.ba_keq_p.value(), "K2O": self.ba_keq_k.value()}
            resultat = asol.bilan_intermediaire(besoins, surface, produit_pct, coef_sol=coef_sol,
                                                 reliquats_mineralisation=reliquats, keq=keq)
        else:
            coef_sol = {"P2O5": self.ba_coef_p.value(), "K2O": self.ba_coef_k.value()}
            keq = {"N": self.ba_keq_n.value(), "P2O5": self.ba_keq_p.value(), "K2O": self.ba_keq_k.value()}
            postes = {
                lib: self._ba_lire_table(self.ba_table_avance, lib)
                for lib in ["Reliquats", "Pertes lixiviation", "Minéralisation humus", "Résidus",
                            "Couverts", "Irrigation", "Autres apports 1", "Autres apports 2"]
            }
            resultat = asol.bilan_avance(
                besoins, surface, produit_pct, coef_sol=coef_sol,
                reliquats=postes["Reliquats"], pertes_lixiviation=postes["Pertes lixiviation"],
                mineralisation_humus=postes["Minéralisation humus"], residus=postes["Résidus"],
                couverts=postes["Couverts"], irrigation=postes["Irrigation"],
                autres_apports_1=postes["Autres apports 1"], autres_apports_2=postes["Autres apports 2"],
                keq=keq)

        html = [f'<h3 style="color:{COULEUR_ACCENT};">Besoin total (kg/ha)</h3>']
        html.append(f"N : {self._fmt(besoins['N'],'kg/ha',0)} — P2O5 : {self._fmt(besoins['P2O5'],'kg/ha',0)} "
                     f"— K2O : {self._fmt(besoins['K2O'],'kg/ha',0)}<br>")
        html.append(f'<h3 style="color:{COULEUR_ACCENT};">Dose du produit</h3>')
        for nutriment, bloc in resultat.items():
            html.append(f"<b>{nutriment}</b> — NPK à apporter : {self._fmt(bloc['npk_a_apporter_kg_ha'],'kg/ha',1)} "
                        f"→ produit : {self._fmt(bloc['dose_produit_t_ha'],'T/ha',3)} "
                        f"({self._fmt(bloc['dose_produit_kg_surface'],'kg sur la surface',2)})")
            if "dose_produit_kg_surface_avec_keq" in bloc:
                html.append(f" — avec Keq : {self._fmt(bloc['dose_produit_kg_surface_avec_keq'],'kg',2)}")
            html.append("<br>")

        if noms_cultures:
            nom_recherche = noms_cultures[0]
            # "SA"/"PC" en fin de nom (convention de cet outil) -> indice de variante
            variante_indice = None
            if nom_recherche.endswith(" SA"):
                variante_indice = "sous abri"
            elif nom_recherche.endswith(" PC"):
                variante_indice = "plein champ"
            nmax, depasse = asol.verifier_plafond_n(besoins["N"], nom_recherche, variante_indice)
            if nmax is None:
                nmax, depasse = asol.verifier_plafond_n(besoins["N"], nom_recherche.split(" ")[0], variante_indice)
            if nmax is not None:
                couleur = COULEUR_ALERTE if depasse else COULEUR_OK
                verdict = "DÉPASSE le plafond" if depasse else "sous le plafond"
                html.append(f'<p style="color:{couleur};"><b>Dose plafond N (arrêté IDF, {noms_cultures[0]})'
                            f' : {self._fmt(nmax,"kg/ha",0)} — besoin {verdict}.</b></p>')

        self.ba_rapport.setHtml("".join(html))

    # ---------------- Sous-onglet 3 : Références ----------------
    def _build_sol_references(self, parent):
        layout = QVBoxLayout(parent)
        refs_tabs = QTabWidget()
        layout.addWidget(refs_tabs)

        # Légendes
        w = QWidget(); v = QVBoxLayout(w)
        t = QTableWidget()
        self._remplir_table(t, ["Sigle", "Définition"], asol.LEGENDES)
        v.addWidget(t)
        refs_tabs.addTab(w, "Légendes")

        # Teneurs N
        w = QWidget(); v = QVBoxLayout(w)
        t = QTableWidget()
        lignes = [(x["espece"], x["organe"], x["dest"], x["teneur_kg_tMF"], x["rendement_moyen_t_ha"])
                  for x in asol.TENEURS_N_RECOLTE]
        self._remplir_table(t, ["Espèce", "Organe", "Dest.", "Teneur (kg/tMF)", "Rendement moyen (t/ha)"], lignes)
        v.addWidget(t)
        refs_tabs.addTab(w, "Teneurs N (récoltes)")

        # Teneurs PK
        w = QWidget(); v = QVBoxLayout(w)
        t = QTableWidget()
        lignes = [(x["espece"], x["organe"], x["dest"], x["P2O5_kg_tMF"], x["K2O_kg_tMF"], x["MgO_kg_tMF"])
                  for x in asol.TENEURS_PK_RECOLTE]
        self._remplir_table(t, ["Espèce", "Organe", "Dest.", "P2O5 (kg/tMF)", "K2O (kg/tMF)", "MgO (kg/tMF)"], lignes)
        v.addWidget(t)
        refs_tabs.addTab(w, "Teneurs PK (récoltes)")

        # Cultures bilan
        w = QWidget(); v = QVBoxLayout(w)
        t = QTableWidget()
        lignes = [(c["type"], c["famille"], c["espece"], c["N"], c["P"], c["K"], c["Mg"],
                   c["rendement"], c["source"], c["commentaire"]) for c in asol.CULTURES_BILAN_AZOTE]
        self._remplir_table(t, ["Type", "Famille", "Espèce", "N", "P", "K", "Mg", "Rdt (t/ha)",
                                 "Source", "Commentaire"], lignes)
        v.addWidget(t)
        refs_tabs.addTab(w, "Cultures (bilan azoté)")

        # Engrais / amendements
        w = QWidget(); v = QVBoxLayout(w)
        t = QTableWidget()
        lignes = [(e["nom"], e["N_kg_t"], e["P2O5_kg_t"], e["K2O_kg_t"], e["MgO_kg_t"], e["C_kg_t"],
                   e["KeqN"], e["KeqP2O5"], e["KeqK2O"], e["source"]) for e in asol.ENGRAIS_AMENDEMENTS]
        self._remplir_table(t, ["Nom", "N (kg/t)", "P2O5 (kg/t)", "K2O (kg/t)", "MgO (kg/t)", "C (kg/t)",
                                 "Keq N", "Keq P2O5", "Keq K2O", "Source"], lignes)
        v.addWidget(t)
        refs_tabs.addTab(w, "Engrais / amendements")

        # Dose plafond N
        w = QWidget(); v = QVBoxLayout(w)
        recherche = QLineEdit()
        recherche.setPlaceholderText("Filtrer par légume...")
        v.addWidget(recherche)
        t = QTableWidget()
        v.addWidget(t)

        def maj_plafonds(texte=""):
            lignes = [(p["legume"], p["variante"], p["nmax"]) for p in asol.rechercher_dose_plafond_n(texte)]
            self._remplir_table(t, ["Légume", "Variante / type", "Nmax (kg N/ha)"], lignes)

        recherche.textChanged.connect(maj_plafonds)
        maj_plafonds()
        refs_tabs.addTab(w, "Dose plafond N (IDF)")

        # Densité & seuils
        w = QWidget(); v = QVBoxLayout(w)
        v.addWidget(QLabel("Densité apparente du sol selon la texture :"))
        t1 = QTableWidget()
        lignes = [(a, texture, code, d) for a, texture, code, d in asol.DENSITE_SOL_PAR_TEXTURE]
        self._remplir_table(t1, ["Appréciation au toucher", "Texture", "Code", "Densité (T/m³)"], lignes)
        t1.setMaximumHeight(280)
        v.addWidget(t1)
        v.addWidget(QLabel("Seuils P2O5 / K2O Olsen — grille COMIFER PKMg, Centre Bassin parisien :"))
        t2 = QTableWidget()
        lignes = []
        for type_sol in asol.TYPES_SOL_CBP:
            p = asol.SEUILS_P2O5_CENTRE_BASSIN_PARISIEN[type_sol]
            k = asol.SEUILS_K2O_CENTRE_BASSIN_PARISIEN[type_sol]
            lignes.append((type_sol, f"{p['forte'][0]}/{p['forte'][1]}", f"{p['moyenne'][0]}/{p['moyenne'][1]}",
                            f"{p['faible'][0]}/{p['faible'][1]}", f"{k['forte'][0]}/{k['forte'][1]}",
                            f"{k['moyenne'][0]}/{k['moyenne'][1]}", f"{k['faible'][0]}/{k['faible'][1]}"))
        self._remplir_table(t2, ["Type de sol", "P2O5 forte (Trenf/Timp)", "P2O5 moyenne", "P2O5 faible",
                                  "K2O forte (Trenf/Timp)", "K2O moyenne", "K2O faible"], lignes)
        v.addWidget(t2)
        refs_tabs.addTab(w, "Densité & seuils P-K")

        # Planches du classeur (images)
        w = QWidget(); v = QVBoxLayout(w)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        contenu = QWidget()
        vc = QVBoxLayout(contenu)
        planches = [
            ("Seuils P2O5 Olsen — grille nationale COMIFER", "seuils_p2o5_national.png"),
            ("Seuils K2O échangeable — grille nationale COMIFER", "seuils_k2o_national.png"),
            ("Grille de calcul des doses de P2O5 / K2O", "grille_doses_pk.png"),
            ("Sensibilité des cultures aux carences en oligo-éléments", "sensibilite_oligo.png"),
            ("Causes possibles des carences en oligo-éléments", "causes_carences_oligo.png"),
            ("Biodisponibilité des éléments selon le pH", "biodisponibilite_ph.png"),
            ("Variabilité saisonnière du pH selon la CEC", "variabilite_ph.png"),
            ("Stratégie de chaulage (Tableau 10.5)", "strategie_chaulage.png"),
            ("Paramètres du bilan de fertilisation azotée (COMIFER)", "bilan_azote_parametres.png"),
        ]
        for titre_img, nom_fichier in planches:
            lbl_titre = QLabel(titre_img)
            lbl_titre.setStyleSheet(f"font-weight: bold; color: {COULEUR_ACCENT}; margin-top: 8px;")
            vc.addWidget(lbl_titre)
            chemin = os.path.join(DOSSIER_RESSOURCES_SOL, nom_fichier)
            lbl_img = QLabel()
            if os.path.isfile(chemin):
                pixmap = QPixmap(chemin)
                if pixmap.width() > 900:
                    pixmap = pixmap.scaledToWidth(900, Qt.SmoothTransformation)
                lbl_img.setPixmap(pixmap)
            else:
                lbl_img.setText(f"(image introuvable : {nom_fichier})")
            vc.addWidget(lbl_img)
        vc.addStretch(1)
        scroll.setWidget(contenu)
        v.addWidget(scroll)
        refs_tabs.addTab(w, "Planches du classeur")

    # ============================================================
    # Onglet "Plan de la ferme"
    # ============================================================
    def _build_onglet_plan_ferme(self, parent):
        layout = QVBoxLayout(parent)

        # --- Barre d'outils ---
        barre = QHBoxLayout()

        self.btn_pf_select = QPushButton("🖱 Sélection / déplacer")
        self.btn_pf_select.setCheckable(True)
        self.btn_pf_select.setChecked(True)
        self.btn_pf_select.clicked.connect(lambda: self.vue_ferme.definir_mode("select"))
        barre.addWidget(self.btn_pf_select)

        self.btn_pf_dessiner = QPushButton("▭ Dessiner un rectangle")
        self.btn_pf_dessiner.setCheckable(True)
        self.btn_pf_dessiner.clicked.connect(lambda: self.vue_ferme.definir_mode("draw"))
        barre.addWidget(self.btn_pf_dessiner)

        btn_pf_multi = QPushButton("▦ Dessiner plusieurs...")
        btn_pf_multi.clicked.connect(self._pf_dessiner_plusieurs)
        barre.addWidget(btn_pf_multi)

        btn_pf_modifier = QPushButton("✏️ Modifier")
        btn_pf_modifier.clicked.connect(self._pf_modifier_selection)
        barre.addWidget(btn_pf_modifier)

        btn_pf_supprimer = QPushButton("🗑 Supprimer")
        btn_pf_supprimer.setStyleSheet(f"color: {COULEUR_ALERTE};")
        btn_pf_supprimer.clicked.connect(self._pf_supprimer_selection)
        barre.addWidget(btn_pf_supprimer)

        barre.addStretch(1)

        btn_pf_nouveau = QPushButton("🧹 Nouveau plan")
        btn_pf_nouveau.clicked.connect(self._pf_nouveau_plan)
        barre.addWidget(btn_pf_nouveau)

        btn_pf_charger = QPushButton("📂 Charger...")
        btn_pf_charger.clicked.connect(self._pf_charger_plan)
        barre.addWidget(btn_pf_charger)

        btn_pf_enregistrer = QPushButton("💾 Enregistrer")
        btn_pf_enregistrer.clicked.connect(self._pf_enregistrer_plan)
        barre.addWidget(btn_pf_enregistrer)

        btn_pf_enregistrer_sous = QPushButton("💾 Enregistrer sous...")
        btn_pf_enregistrer_sous.clicked.connect(self._pf_enregistrer_plan_sous)
        barre.addWidget(btn_pf_enregistrer_sous)

        layout.addLayout(barre)

        # --- Légende des états ---
        legende = QHBoxLayout()
        legende.addWidget(QLabel("Légende :"))
        for etat, couleur in pf.COULEUR_PAR_ETAT.items():
            pastille = QLabel(f"  {etat}  ")
            pastille.setStyleSheet(
                f"background-color: {couleur}; border: 1px solid #888; "
                f"border-radius: 3px; padding: 1px 4px;"
            )
            legende.addWidget(pastille)
        legende.addStretch(1)
        layout.addLayout(legende)

        # --- Zone de dessin ---
        self.scene_ferme = QGraphicsScene(0, 0, 2000, 1200)
        self.vue_ferme = pf.VueFerme(self.scene_ferme)
        self.vue_ferme.callback_nouveau_rect = self._pf_nouveau_rect_cree
        self.vue_ferme.callback_rects_multi_crees = self._pf_rects_multi_crees
        self.vue_ferme.callback_edition = self._pf_editer_item
        self.vue_ferme.callback_mode_change = self._pf_maj_boutons_mode
        layout.addWidget(self.vue_ferme, 1)

        self.lbl_pf_statut = QLabel(
            "Mode sélection : cliquez-glissez un rectangle pour le déplacer, ou faites un cadre "
            "sur une zone vide pour sélectionner plusieurs éléments. Double-cliquez sur un "
            "rectangle pour modifier ses propriétés. (Molette = zoom.)"
        )
        self.lbl_pf_statut.setWordWrap(True)
        self.lbl_pf_statut.setStyleSheet(f"color: {COULEUR_INFO}; font-style: italic;")
        layout.addWidget(self.lbl_pf_statut)

        self.plan_ferme_path = None

    def _pf_maj_boutons_mode(self, mode):
        self.btn_pf_select.setChecked(mode == "select")
        self.btn_pf_dessiner.setChecked(mode == "draw")
        messages = {
            "select": "Mode sélection : cliquez-glissez un rectangle pour le déplacer, ou faites un "
                      "cadre sur une zone vide pour sélectionner plusieurs éléments. Double-cliquez sur "
                      "un rectangle pour modifier ses propriétés. (Molette = zoom.)",
            "draw": "Mode dessin : cliquez et glissez sur le plan pour tracer un nouveau rectangle "
                    "(déposez-le à l'intérieur d'un autre pour l'y emboîter automatiquement).",
            "draw_multi": "Cliquez une fois sur le plan pour poser le coin haut-gauche de la série "
                          "de rectangles.",
        }
        self.lbl_pf_statut.setText(messages.get(mode, ""))

    def _pf_liste_cultures(self):
        return list(fb.FICHES.keys())

    def _pf_dessiner_plusieurs(self):
        dialog = pf.DialogRectsMultiples(self, cultures=self._pf_liste_cultures())
        if dialog.exec_() == dialog.Accepted:
            self.vue_ferme.parametres_multi = dialog.valeurs()
            self.vue_ferme.definir_mode("draw_multi")

    def _pf_nouveau_rect_cree(self, item):
        # On ouvre directement la fiche de propriétés pour nommer/qualifier
        # le rectangle qui vient d'être tracé à la souris.
        self._pf_editer_item(item)

    def _pf_rects_multi_crees(self, items):
        self._set_status(f"{len(items)} rectangle(s) créé(s).")

    def _pf_editer_item(self, item):
        valeurs = {
            "nom": item.nom, "type": item.type_zone, "etat": item.etat, "culture": item.culture,
            "x": item.pos().x(), "y": item.pos().y(),
            "largeur": item.rect().width(), "hauteur": item.rect().height(),
        }
        dialog = pf.DialogProprietesRect(self, valeurs=valeurs, cultures=self._pf_liste_cultures(),
                                          titre=f"Propriétés — {item.nom}")
        if dialog.exec_() == dialog.Accepted:
            v = dialog.valeurs()
            item.nom = v["nom"]
            item.type_zone = v["type"]
            item.etat = v["etat"]
            item.culture = v["culture"]
            item.definir_dimensions(v["largeur"], v["hauteur"])
            item.setPos(v["x"], v["y"])
            item.update()
            self._set_status(f"Rectangle mis à jour : {item.resume()}")

    def _pf_modifier_selection(self):
        items = [i for i in self.scene_ferme.selectedItems() if isinstance(i, pf.RectangleFerme)]
        if not items:
            QMessageBox.information(self, "Info", "Sélectionnez d'abord un rectangle à modifier.")
            return
        self._pf_editer_item(items[0])

    def _pf_supprimer_selection(self):
        items = [i for i in self.scene_ferme.selectedItems() if isinstance(i, pf.RectangleFerme)]
        if not items:
            QMessageBox.information(self, "Info",
                                     "Sélectionnez d'abord un ou plusieurs rectangles à supprimer.")
            return
        reponse = QMessageBox.question(
            self, "Confirmation",
            f"Supprimer {len(items)} rectangle(s) sélectionné(s) (et ce qui y est emboîté) ?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reponse == QMessageBox.Yes:
            for item in items:
                if item.scene() is not None:  # déjà supprimé si emboîté dans un autre item sélectionné
                    pf.supprimer_rectangle(self.scene_ferme, item)
            self._set_status("Rectangle(s) supprimé(s).")

    def _pf_nouveau_plan(self):
        if self.scene_ferme.items():
            reponse = QMessageBox.question(
                self, "Confirmation",
                "Effacer le plan actuel (les modifications non enregistrées seront perdues) ?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reponse != QMessageBox.Yes:
                return
        self.scene_ferme.clear()
        self.vue_ferme._prochain_id = 1
        self.plan_ferme_path = None
        self._set_status("Nouveau plan de ferme (vide).")

    def _pf_charger_plan(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Charger un plan de ferme", "", "Plans de ferme (*.ferme *.txt);;Tous les fichiers (*.*)")
        if not path:
            return
        try:
            pf.charger_plan(path, self.scene_ferme)
            self.vue_ferme.resynchroniser_prochain_id()
            self.plan_ferme_path = path
            self._set_status(f"Plan chargé : {path}")
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Impossible de charger le plan :\n{e}")

    def _pf_enregistrer_plan(self):
        if not self.plan_ferme_path:
            self._pf_enregistrer_plan_sous()
            return
        try:
            pf.sauvegarder_plan(self.plan_ferme_path, self.scene_ferme)
            self._set_status(f"Plan enregistré : {self.plan_ferme_path}")
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Impossible d'enregistrer le plan :\n{e}")

    def _pf_enregistrer_plan_sous(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Enregistrer le plan sous...", "plan_ferme.ferme", "Plans de ferme (*.ferme)")
        if not path:
            return
        if not path.lower().endswith(".ferme"):
            path += ".ferme"
        self.plan_ferme_path = path
        self._pf_enregistrer_plan()

    # ============================================================
    # Onglet "Carte régionale" (climat & qualité du sol)
    # ============================================================
    def _build_onglet_carte(self, parent):
        layout = QVBoxLayout(parent)

        intro = QLabel(
            "Carte des 13 régions de France métropolitaine, en version schématique (mailles "
            "hexagonales de même taille), géographique (contours réels, QGraphicsView) ou "
            "interactive (carte Leaflet via geopandas/folium, avec classification "
            "automatique des couleurs par mapclassify). Cliquez sur une région (modes "
            "schématique/géographique) ou survolez-la (mode interactif) pour afficher son "
            "climat et la qualité indicative de son sol ; molette pour zoomer/dézoomer, "
            "clic-glisser pour déplacer la carte. Données à l'échelle régionale, donc "
            "volontairement simplifiées - la couche « sol » n'est pas une carte géologique "
            "BRGM, mais une appréciation indicative de fertilité dominante. Pour une "
            "décision réelle, reportez-vous à la météo locale (onglet « Aide à la "
            "décision ») et à une analyse de sol de votre parcelle (onglet « Analyse de "
            "sol »)."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet(f"color: {COULEUR_INFO}; font-style: italic; font-size: 9pt;")
        layout.addWidget(intro)

        barre = QHBoxLayout()
        barre.addWidget(QLabel("Type de carte :"))
        self.carte_combo_type = QComboBox()
        self.carte_combo_type.addItems(cf.TYPES_CARTE)
        self.carte_combo_type.setCurrentIndex(1)  # géographique par défaut
        self.carte_combo_type.currentIndexChanged.connect(self._carte_changer_type)
        barre.addWidget(self.carte_combo_type)

        barre.addSpacing(20)
        barre.addWidget(QLabel("Délimitation par :"))
        self.carte_combo_mode = QComboBox()
        self.carte_combo_mode.addItems(cf.MODES)
        self.carte_combo_mode.currentIndexChanged.connect(self._carte_mode_change)
        barre.addWidget(self.carte_combo_mode)
        barre.addStretch(1)
        self.carte_btn_zoom = QPushButton("🔍 Réinitialiser le zoom")
        self.carte_btn_zoom.clicked.connect(lambda: self.carte_vue.ajuster_vue())
        barre.addWidget(self.carte_btn_zoom)
        self.carte_btn_navigateur = QPushButton("🌐 Ouvrir dans le navigateur")
        self.carte_btn_navigateur.clicked.connect(self._carte_ouvrir_navigateur)
        self.carte_btn_navigateur.setVisible(False)
        barre.addWidget(self.carte_btn_navigateur)
        layout.addLayout(barre)

        self.carte_stack = QStackedWidget()
        layout.addWidget(self.carte_stack, 1)

        # --- Page 0 : cartes QGraphicsView (schématique / géographique) ---
        page_qgv = QWidget()
        layout_qgv = QVBoxLayout(page_qgv)
        layout_qgv.setContentsMargins(0, 0, 0, 0)
        splitter = QSplitter(Qt.Horizontal)
        layout_qgv.addWidget(splitter)

        self.carte_scene = QGraphicsScene()
        self.carte_vue = cf.VueCarteFrance(self.carte_scene)
        self.carte_vue.setMinimumWidth(420)
        splitter.addWidget(self.carte_vue)

        panneau = QWidget()
        pl = QVBoxLayout(panneau)

        box_info = QGroupBox("Région sélectionnée")
        bil = QVBoxLayout(box_info)
        self.carte_label_region = QLabel("—")
        self.carte_label_region.setStyleSheet("font-weight: bold; font-size: 12pt;")
        bil.addWidget(self.carte_label_region)
        self.carte_texte_info = QTextBrowser()
        self.carte_texte_info.setMinimumHeight(200)
        bil.addWidget(self.carte_texte_info)
        pl.addWidget(box_info)

        self.carte_box_legende = QGroupBox("Légende")
        self.carte_legende_layout = QVBoxLayout(self.carte_box_legende)
        pl.addWidget(self.carte_box_legende)
        pl.addStretch(1)

        scroll_panneau = QScrollArea()
        scroll_panneau.setWidgetResizable(True)
        scroll_panneau.setFrameShape(QFrame.NoFrame)
        scroll_panneau.setWidget(panneau)
        scroll_panneau.setMinimumWidth(300)
        scroll_panneau.setMaximumWidth(360)
        splitter.addWidget(scroll_panneau)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        self.carte_stack.addWidget(page_qgv)

        # --- Page 1 : carte interactive Leaflet (geopandas + folium + mapclassify) ---
        page_web = QWidget()
        layout_web = QVBoxLayout(page_web)
        self.carte_web_html_path = os.path.join(tempfile.gettempdir(), "carte_france_gab_idf.html")
        if not cf.CARTE_WEB_DISPONIBLE:
            msg = QLabel(
                "La carte interactive nécessite les paquets Python 'geopandas', 'folium' et "
                "'mapclassify'.\n\nInstallez-les puis relancez l'application :\n"
                "    pip install geopandas folium mapclassify"
            )
            msg.setWordWrap(True)
            msg.setAlignment(Qt.AlignCenter)
            msg.setStyleSheet(f"color: {COULEUR_ALERTE}; font-size: 11pt; padding: 40px;")
            layout_web.addWidget(msg)
            self.carte_webview = None
        elif WEBENGINE_DISPONIBLE:
            self.carte_webview = QWebEngineView()
            layout_web.addWidget(self.carte_webview)
        else:
            msg = QLabel(
                "Le module 'PyQtWebEngine' n'est pas installé : la carte interactive ne peut "
                "pas être affichée directement dans l'application.\n\n"
                "Installez-le avec :\n    pip install PyQtWebEngine\n\n"
                "En attendant, utilisez le bouton « Ouvrir dans le navigateur » ci-dessus."
            )
            msg.setWordWrap(True)
            msg.setAlignment(Qt.AlignCenter)
            msg.setStyleSheet(f"color: {COULEUR_INFO}; font-size: 11pt; padding: 40px;")
            layout_web.addWidget(msg)
            self.carte_webview = None
        self.carte_stack.addWidget(page_web)

        self.carte_tuiles = {}  # nom -> liste de FormeRegion (1 en schématique, 1+ en géographique)
        self.carte_region_courante = (
            "Île-de-France" if "Île-de-France" in cf.REGIONS else next(iter(cf.REGIONS)))

        self._carte_construire_scene()
        self._carte_rafraichir_couleurs()
        self._carte_selectionner(self.carte_region_courante)

    def _carte_construire_scene(self):
        """(Re)construit les éléments graphiques de la carte selon le type
        choisi (schématique ou géographique), en conservant la sélection en
        cours."""
        self.carte_scene.clear()
        self.carte_tuiles = {}

        type_geo = self.carte_combo_type.currentIndex() == 1
        for nom in cf.REGIONS:
            if type_geo:
                parties = cf.parties_contour_region(nom, callback_clic=self._carte_selectionner)
                cx, cy = cf.centre_contour_region(nom)
            else:
                d = cf.REGIONS[nom]
                cx, cy = cf.position_pixel(d["row"], d["col"])
                parties = [cf.TuileRegion(nom, cx, cy, callback_clic=self._carte_selectionner)]

            for partie in parties:
                self.carte_scene.addItem(partie)
            self.carte_scene.addItem(cf.creer_etiquette(nom, cx, cy))
            self.carte_tuiles[nom] = parties

        self.carte_scene.setSceneRect(self.carte_scene.itemsBoundingRect().adjusted(-40, -40, 40, 40))

    def _carte_changer_type(self):
        index_type = self.carte_combo_type.currentIndex()
        est_web = (index_type == 2)
        self.carte_stack.setCurrentIndex(1 if est_web else 0)
        self.carte_btn_zoom.setVisible(not est_web)
        self.carte_btn_navigateur.setVisible(est_web and cf.CARTE_WEB_DISPONIBLE)

        if est_web:
            self._carte_maj_carte_web()
            return

        self._carte_construire_scene()
        self._carte_rafraichir_couleurs()
        self._carte_selectionner(self.carte_region_courante)
        self.carte_vue.ajuster_vue()

    def _carte_mode_change(self):
        """Appelé quand on change "Délimitation par : Climat / Qualité du
        sol" - répercute sur la carte QGraphicsView ou sur la carte Leaflet
        selon le type de carte actuellement affiché."""
        if self.carte_combo_type.currentIndex() == 2:
            self._carte_maj_carte_web()
        else:
            self._carte_rafraichir_couleurs()

    def _carte_maj_carte_web(self):
        """(Re)génère la carte Leaflet (geopandas + folium + mapclassify)
        pour l'indicateur actuellement choisi et l'affiche (QWebEngineView
        si disponible, sinon le bouton "Ouvrir dans le navigateur" reste la
        seule voie d'accès)."""
        if not cf.CARTE_WEB_DISPONIBLE:
            return
        mode_index = self.carte_combo_mode.currentIndex()
        try:
            cf.enregistrer_carte_html(mode_index, self.carte_web_html_path)
        except Exception as e:
            if self.carte_webview is not None:
                self.carte_webview.setHtml(
                    f"<p style='color:red;'>Erreur lors de la génération de la carte : {e}</p>")
            return
        if self.carte_webview is not None:
            self.carte_webview.load(QUrl.fromLocalFile(self.carte_web_html_path))

    def _carte_ouvrir_navigateur(self):
        if not cf.CARTE_WEB_DISPONIBLE:
            return
        self._carte_maj_carte_web()
        webbrowser.open(QUrl.fromLocalFile(self.carte_web_html_path).toString())

    def _carte_rafraichir_couleurs(self):
        mode_index = self.carte_combo_mode.currentIndex()
        for nom, parties in self.carte_tuiles.items():
            couleur = cf.couleur_pour(nom, mode_index)
            for partie in parties:
                partie.definir_couleur(couleur)

        while self.carte_legende_layout.count():
            item = self.carte_legende_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        for libelle, couleur in cf.legende_pour(mode_index):
            ligne = QHBoxLayout()
            carre = QFrame()
            carre.setFixedSize(16, 16)
            carre.setStyleSheet(f"background-color:{couleur}; border:1px solid #555;")
            ligne.addWidget(carre)
            lbl = QLabel(libelle)
            lbl.setWordWrap(True)
            ligne.addWidget(lbl, 1)
            conteneur = QWidget()
            conteneur.setLayout(ligne)
            self.carte_legende_layout.addWidget(conteneur)

    def _carte_selectionner(self, nom):
        self.carte_region_courante = nom
        for autre, parties in self.carte_tuiles.items():
            for partie in parties:
                partie.definir_selection(autre == nom)

        d = cf.REGIONS[nom]
        self.carte_label_region.setText(nom)
        html = (
            f"<b>🌦 Climat :</b> {d['climat']}<br>"
            f"<p style='margin-top:2px;'>{d['climat_desc']}</p>"
            f"<b>🧪 Sol :</b> {d['sol_type']} "
            f"<i>(fertilité indicative : {cf.SOL_LABELS_NIVEAU[d['sol_niveau']]})</i><br>"
            f"<p style='margin-top:2px;'>{d['sol_desc']}</p>"
        )
        self.carte_texte_info.setHtml(html)


def main():
    if WEBENGINE_DISPONIBLE:
        # Doit être positionné avant la création de QApplication pour que
        # QWebEngineView (carte interactive) fonctionne de façon fiable.
        QApplication.setAttribute(Qt.AA_ShareOpenGLContexts)
    app = QApplication(sys.argv)
    app.setApplicationName("Planning cultural maraîcher bio")
    fenetre = PlanningApp()
    fenetre.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
