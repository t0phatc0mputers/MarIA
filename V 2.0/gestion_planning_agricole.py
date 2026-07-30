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
    QFormLayout, QLabel, QLineEdit, QComboBox, QSpinBox, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QPlainTextEdit, QGroupBox, QSplitter, QMessageBox, QFileDialog, QStatusBar,
    QListWidget, QListWidgetItem, QDateEdit, QCompleter, QAction,
)

import meteo_decision as md

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

        self.tabs.addTab(onglet_planning, "📋 Planning cultural")
        self.tabs.addTab(onglet_decision, "🌦 Aide à la décision")
        self.tabs.addTab(onglet_graphiques, "📈 Graphiques météo")
        self.tabs.addTab(onglet_historique, "🕘 Historique météo")
        self.tabs.addTab(onglet_fiches, "🌱 Fiches de référence")

        self._build_onglet_planning(onglet_planning)
        self._build_onglet_decision(onglet_decision)
        self._build_onglet_graphiques(onglet_graphiques)
        self._build_onglet_historique(onglet_historique)
        self._build_onglet_fiches(onglet_fiches)

    # ============================================================
    # Onglet "Planning cultural"
    # ============================================================
    def _build_onglet_planning(self, parent):
        layout = QVBoxLayout(parent)

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

        droite_box = QGroupBox()
        droite_layout = QVBoxLayout(droite_box)

        self.lbl_fiche_titre = QLabel("Sélectionnez une culture")
        font_titre = QFont()
        font_titre.setPointSize(16)
        font_titre.setBold(True)
        self.lbl_fiche_titre.setFont(font_titre)
        droite_layout.addWidget(self.lbl_fiche_titre)

        self.lbl_fiche_sous_titre = QLabel("")
        self.lbl_fiche_sous_titre.setStyleSheet(f"color: {COULEUR_INFO};")
        droite_layout.addWidget(self.lbl_fiche_sous_titre)

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
        droite_layout.addWidget(self.table_fiche, 1)

        layout.addWidget(droite_box, 1)

        self._maj_liste_fiches()

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


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Planning cultural maraîcher bio")
    fenetre = PlanningApp()
    fenetre.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
