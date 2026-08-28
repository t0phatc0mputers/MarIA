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
                    Conservation / Forçage
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

from PyQt5.QtCore import Qt, QDate, QThread, pyqtSignal
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QTabWidget, QVBoxLayout, QHBoxLayout,
    QFormLayout, QGridLayout, QLabel, QLineEdit, QComboBox, QSpinBox, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QPlainTextEdit, QGroupBox, QSplitter, QMessageBox, QFileDialog, QStatusBar,
    QListWidget, QListWidgetItem, QDateEdit, QCompleter, QAction,
    QScrollArea, QFrame, QSizePolicy, QDoubleSpinBox, QProgressBar, QGraphicsScene,
)

import meteo_decision as md
import fiches_botaniques as fb
import qualite_sol as qs
import plan_ferme as pf

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
FIELDS = ["culture", "conduite", "variete_n", "action", "semaine_debut", "semaine_fin",
          "mois_debut", "mois_fin", "commentaire"]
HEADERS = ["Culture", "Conduite", "Variété n°", "Action", "Sem. début", "Sem. fin",
           "Mois début", "Mois fin", "Commentaire"]

ACTIONS = ["Semis direct", "Semis en pot/plant", "Plantation", "Récolte",
           "Conservation", "Forçage"]
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
        onglet_sol = QWidget()
        onglet_plan = QWidget()

        self.tabs.addTab(onglet_planning, "📋 Planning cultural")
        self.tabs.addTab(onglet_decision, "🌦 Aide à la décision")
        self.tabs.addTab(onglet_graphiques, "📈 Graphiques météo")
        self.tabs.addTab(onglet_historique, "🕘 Historique météo")
        self.tabs.addTab(onglet_fiches, "🌱 Fiches de référence")
        self.tabs.addTab(onglet_sol, "🧫 Qualité des sols")
        self.tabs.addTab(onglet_plan, "🚜 Plan de la ferme")

        self._build_onglet_planning(onglet_planning)
        self._build_onglet_decision(onglet_decision)
        self._build_onglet_graphiques(onglet_graphiques)
        self._build_onglet_historique(onglet_historique)
        self._build_onglet_fiches(onglet_fiches)
        self._build_onglet_qualite_sol(onglet_sol)
        self._build_onglet_plan_ferme(onglet_plan)

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

        self.edit_dec_ville = QLineEdit("Paris (75000)")
        form_layout.addRow("Ville (Météociel) :", self.edit_dec_ville)

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
    # Onglet "Qualité des sols"
    # ============================================================
    def _build_onglet_qualite_sol(self, parent):
        layout = QHBoxLayout(parent)

        # ---------------------------------------------------- Colonne gauche : saisie
        scroll_gauche = QScrollArea()
        scroll_gauche.setWidgetResizable(True)
        scroll_gauche.setFrameShape(QFrame.NoFrame)
        scroll_gauche.setMinimumWidth(330)
        scroll_gauche.setMaximumWidth(370)

        gauche_contenu = QWidget()
        gauche_layout = QVBoxLayout(gauche_contenu)
        scroll_gauche.setWidget(gauche_contenu)

        intro = QLabel(
            "Renseignez ce que vous savez de votre parcelle — tous les champs "
            "sont facultatifs. Plus vous en indiquez, plus l'analyse sera précise."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet(f"color: {COULEUR_INFO}; font-style: italic;")
        gauche_layout.addWidget(intro)

        box_sol = QGroupBox("🧪 Caractéristiques du sol")
        form_sol = QFormLayout(box_sol)

        self.spin_sol_ph = QDoubleSpinBox()
        self.spin_sol_ph.setRange(0.0, 9.5)
        self.spin_sol_ph.setSingleStep(0.1)
        self.spin_sol_ph.setDecimals(1)
        self.spin_sol_ph.setSpecialValueText(qs.NON_RENSEIGNE)
        self.spin_sol_ph.setValue(0.0)
        form_sol.addRow("pH :", self.spin_sol_ph)

        self.cb_sol_texture = QComboBox()
        self.cb_sol_texture.addItems(qs.CHOIX_TEXTURE)
        form_sol.addRow("Texture :", self.cb_sol_texture)

        self.cb_sol_humidite = QComboBox()
        self.cb_sol_humidite.addItems(qs.CHOIX_HUMIDITE)
        form_sol.addRow("Humidité :", self.cb_sol_humidite)

        self.cb_sol_drainage = QComboBox()
        self.cb_sol_drainage.addItems(qs.CHOIX_DRAINAGE)
        form_sol.addRow("Drainage :", self.cb_sol_drainage)

        self.cb_sol_calcaire = QComboBox()
        self.cb_sol_calcaire.addItems(qs.CHOIX_CALCAIRE)
        form_sol.addRow("Calcaire :", self.cb_sol_calcaire)

        self.cb_sol_salinite = QComboBox()
        self.cb_sol_salinite.addItems(qs.CHOIX_SALINITE)
        form_sol.addRow("Salinité :", self.cb_sol_salinite)

        gauche_layout.addWidget(box_sol)

        box_chimie = QGroupBox("⚗️ Analyse de laboratoire (optionnel)")
        form_chimie = QFormLayout(box_chimie)

        info_labo = QLabel(
            "Si vous avez une analyse de sol (GAB IDF, chambre d'agriculture...), ces valeurs "
            "affinent l'analyse : ratio MO/argile, C/N, seuils P/K COMIFER, indice de battance."
        )
        info_labo.setWordWrap(True)
        info_labo.setStyleSheet(f"color: {COULEUR_INFO}; font-size: 9pt; font-style: italic;")
        form_chimie.addRow(info_labo)

        self.spin_sol_mo = self._creer_spin_labo(0.0, 30.0, decimales=2, suffixe=" %")
        form_chimie.addRow("Matière organique (MO) :", self.spin_sol_mo)

        self.spin_sol_argile = self._creer_spin_labo(0.0, 100.0, decimales=1, suffixe=" %")
        form_chimie.addRow("Argile :", self.spin_sol_argile)

        self.spin_sol_limons_fins = self._creer_spin_labo(0.0, 100.0, decimales=1, suffixe=" %")
        form_chimie.addRow("Limons fins :", self.spin_sol_limons_fins)

        self.spin_sol_limons_grossiers = self._creer_spin_labo(0.0, 100.0, decimales=1, suffixe=" %")
        form_chimie.addRow("Limons grossiers :", self.spin_sol_limons_grossiers)

        self.spin_sol_cec = self._creer_spin_labo(0.0, 60.0, decimales=1, suffixe=" meq/100g")
        form_chimie.addRow("CEC :", self.spin_sol_cec)

        self.spin_sol_cn = self._creer_spin_labo(0.0, 40.0, decimales=1, suffixe="")
        form_chimie.addRow("C/N :", self.spin_sol_cn)

        self.spin_sol_p2o5 = self._creer_spin_labo(0.0, 1000.0, decimales=0, suffixe=" mg/kg")
        form_chimie.addRow("P2O5 (Olsen) :", self.spin_sol_p2o5)

        self.spin_sol_k2o = self._creer_spin_labo(0.0, 1000.0, decimales=0, suffixe=" mg/kg")
        form_chimie.addRow("K2O (Olsen) :", self.spin_sol_k2o)

        gauche_layout.addWidget(box_chimie)

        btn_layout = QHBoxLayout()
        self.btn_analyser_sol = QPushButton("🔍 Analyser le sol")
        self.btn_analyser_sol.setStyleSheet(
            f"QPushButton {{ background-color: {COULEUR_ACCENT}; color: white; "
            f"font-weight: bold; padding: 6px; border-radius: 5px; }}"
        )
        self.btn_analyser_sol.clicked.connect(self._analyser_sol)
        btn_layout.addWidget(self.btn_analyser_sol)

        self.btn_reinit_sol = QPushButton("♻️ Réinitialiser")
        self.btn_reinit_sol.clicked.connect(self._reinitialiser_sol)
        btn_layout.addWidget(self.btn_reinit_sol)
        gauche_layout.addLayout(btn_layout)

        gauche_layout.addStretch(1)
        layout.addWidget(scroll_gauche)

        # ---------------------------------------------------- Colonne droite : résultats
        scroll_droite = QScrollArea()
        scroll_droite.setWidgetResizable(True)
        scroll_droite.setFrameShape(QFrame.NoFrame)

        droite_contenu = QWidget()
        self.droite_sol_layout = QVBoxLayout(droite_contenu)
        scroll_droite.setWidget(droite_contenu)

        box_score = QGroupBox("📊 Fertilité globale estimée")
        layout_score = QVBoxLayout(box_score)
        self.lbl_score_sol = QLabel("Renseignez au moins un critère pour lancer l'analyse.")
        self.lbl_score_sol.setStyleSheet("font-weight: bold; font-size: 13pt;")
        layout_score.addWidget(self.lbl_score_sol)
        self.barre_score_sol = QProgressBar()
        self.barre_score_sol.setRange(0, 100)
        self.barre_score_sol.setValue(0)
        self.barre_score_sol.setTextVisible(True)
        layout_score.addWidget(self.barre_score_sol)
        self.droite_sol_layout.addWidget(box_score)

        self.box_cultures_ok = QGroupBox("✅ Cultures bien adaptées à ce sol")
        self.layout_cultures_ok = QVBoxLayout(self.box_cultures_ok)
        self.droite_sol_layout.addWidget(self.box_cultures_ok)

        self.box_cultures_eviter = QGroupBox("⚠️ Cultures à éviter ou à surveiller")
        self.layout_cultures_eviter = QVBoxLayout(self.box_cultures_eviter)
        self.droite_sol_layout.addWidget(self.box_cultures_eviter)

        self.box_actions_sol = QGroupBox("🛠️ Actions recommandées pour améliorer le sol")
        self.layout_actions_sol = QVBoxLayout(self.box_actions_sol)
        self.droite_sol_layout.addWidget(self.box_actions_sol)

        self.droite_sol_layout.addStretch(1)
        layout.addWidget(scroll_droite, 1)

        self._analyser_sol()

    def _creer_carte_sol(self, titre, sous_texte, couleur, emoji=""):
        """Petite carte visuelle (QFrame avec liseré coloré) utilisée pour
        afficher une culture ou une action recommandée dans l'onglet sol."""
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
        """QDoubleSpinBox pour une valeur de laboratoire facultative : -1
        (valeur spéciale affichée "Non renseigné") sert de sentinelle pour
        "champ vide", puisque 0 est une valeur de mesure valide (0 % argile,
        0 mg/kg...)."""
        spin = QDoubleSpinBox()
        spin.setRange(-1.0, maximum)
        spin.setDecimals(decimales)
        spin.setSingleStep(1.0 if decimales == 0 else 0.1)
        spin.setSpecialValueText(qs.NON_RENSEIGNE)
        spin.setSuffix(suffixe)
        spin.setValue(-1.0)
        return spin

    def _lire_spin_labo(self, spin):
        v = spin.value()
        return None if v < 0 else round(v, spin.decimals())

    def _lire_profil_sol(self):
        ph = self.spin_sol_ph.value()
        brut = {
            "ph": None if ph <= 0.0 else round(ph, 1),
            "texture": self.cb_sol_texture.currentText(),
            "humidite": self.cb_sol_humidite.currentText(),
            "drainage": self.cb_sol_drainage.currentText(),
            "calcaire": self.cb_sol_calcaire.currentText(),
            "salinite": self.cb_sol_salinite.currentText(),
            "mo_pourcent": self._lire_spin_labo(self.spin_sol_mo),
            "argile": self._lire_spin_labo(self.spin_sol_argile),
            "limons_fins": self._lire_spin_labo(self.spin_sol_limons_fins),
            "limons_grossiers": self._lire_spin_labo(self.spin_sol_limons_grossiers),
            "cec": self._lire_spin_labo(self.spin_sol_cec),
            "c_n": self._lire_spin_labo(self.spin_sol_cn),
            "p2o5": self._lire_spin_labo(self.spin_sol_p2o5),
            "k2o": self._lire_spin_labo(self.spin_sol_k2o),
        }
        return qs.construire_profil_analyse(brut)

    def _reinitialiser_sol(self):
        self.spin_sol_ph.setValue(0.0)
        for combo in (self.cb_sol_texture, self.cb_sol_humidite,
                      self.cb_sol_drainage, self.cb_sol_calcaire, self.cb_sol_salinite):
            combo.setCurrentIndex(0)
        for spin in (self.spin_sol_mo, self.spin_sol_argile, self.spin_sol_limons_fins,
                     self.spin_sol_limons_grossiers, self.spin_sol_cec, self.spin_sol_cn,
                     self.spin_sol_p2o5, self.spin_sol_k2o):
            spin.setValue(-1.0)
        self._analyser_sol()

    def _analyser_sol(self):
        profil = self._lire_profil_sol()

        # -- Score global (jauge) --
        score = qs.score_global_sol(profil)
        if score is None:
            self.lbl_score_sol.setText("Renseignez au moins un critère pour lancer l'analyse.")
            self.barre_score_sol.setValue(0)
            self.barre_score_sol.setStyleSheet("")
        else:
            if score >= 70:
                appreciation, couleur = "Bon", COULEUR_OK
            elif score >= 45:
                appreciation, couleur = "Moyen", "#e58900"
            else:
                appreciation, couleur = "Faible", COULEUR_ALERTE
            self.lbl_score_sol.setText(f"{score} / 100 — {appreciation}")
            self.lbl_score_sol.setStyleSheet(f"font-weight: bold; font-size: 13pt; color: {couleur};")
            self.barre_score_sol.setValue(score)
            self.barre_score_sol.setStyleSheet(
                f"QProgressBar::chunk {{ background-color: {couleur}; }}"
            )

        # -- Cultures bien adaptées / à éviter --
        self._vider_layout(self.layout_cultures_ok)
        self._vider_layout(self.layout_cultures_eviter)

        if qs.profil_est_vide(profil):
            msg = QLabel("Renseignez au moins un critère (pH, texture, humidité...) pour "
                          "obtenir des suggestions de cultures adaptées.")
            msg.setWordWrap(True)
            msg.setStyleSheet(f"color: {COULEUR_INFO}; font-style: italic;")
            self.layout_cultures_ok.addWidget(msg)

            msg2 = QLabel("—")
            msg2.setStyleSheet(f"color: {COULEUR_INFO};")
            self.layout_cultures_eviter.addWidget(msg2)
        else:
            adaptees, a_eviter = qs.classer_cultures(fb.FICHES, profil)

            if not adaptees:
                self.layout_cultures_ok.addWidget(QLabel("Aucune culture ne correspond fortement à ce profil."))
            for e in adaptees:
                emoji = self._emoji_pour_culture(e["culture"])
                sous_texte = ", ".join(e["raisons"]) if e["raisons"] else f"Compatibilité : {e['score']}%"
                carte = self._creer_carte_sol(f"{e['culture']} ({e['score']}%)", sous_texte, COULEUR_OK, emoji)
                self.layout_cultures_ok.addWidget(carte)

            if not a_eviter:
                self.layout_cultures_eviter.addWidget(QLabel("Aucune culture particulièrement déconseillée détectée."))
            for e in a_eviter:
                emoji = self._emoji_pour_culture(e["culture"])
                sous_texte = ", ".join(e["raisons_negatives"]) if e["raisons_negatives"] else f"Compatibilité : {e['score']}%"
                carte = self._creer_carte_sol(f"{e['culture']} ({e['score']}%)", sous_texte, COULEUR_ALERTE, emoji)
                self.layout_cultures_eviter.addWidget(carte)

        # -- Actions recommandées --
        self._vider_layout(self.layout_actions_sol)
        for action in qs.generer_actions(profil):
            couleur = qs.URGENCE_COULEUR[action["urgence"]]
            emoji = qs.URGENCE_EMOJI[action["urgence"]]
            carte = self._creer_carte_sol(action["titre"], action["detail"], couleur, emoji)
            self.layout_actions_sol.addWidget(carte)


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


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Planning cultural maraîcher bio")
    fenetre = PlanningApp()
    fenetre.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
