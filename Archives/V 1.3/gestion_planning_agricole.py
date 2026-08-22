#!/usr/bin/env python3
"""
Gestion du planning cultural maraîcher bio (Île-de-France)
-----------------------------------------------------------
Application Tkinter permettant de consulter, ajouter, modifier, supprimer
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

Auteur : généré avec Claude
"""

import csv
import datetime
import os
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext

import meteo_decision as md

try:
    import matplotlib
    matplotlib.use("TkAgg")
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False

CSV_PATH_DEFAULT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "planning_cultural.csv")
FIELDS = ["culture", "conduite", "variete_n", "action", "semaine_debut", "semaine_fin",
          "mois_debut", "mois_fin", "commentaire"]

ACTIONS = ["Semis direct", "Semis en pot/plant", "Plantation", "Récolte",
           "Conservation", "Forçage"]
CONDUITES = ["SA", "PC"]

MONTH_FR = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
            "septembre", "octobre", "novembre", "décembre"]


def semaine_vers_mois(semaine: int) -> str:
    """Convertit un numéro de semaine (1-52) en nom de mois approximatif."""
    semaine = max(1, min(52, int(semaine)))
    d = datetime.date(2025, 1, 1) + datetime.timedelta(days=(semaine - 1) * 7)
    return MONTH_FR[d.month - 1]


class PlanningApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Gestion du planning cultural maraîcher bio - GAB IDF")
        self.geometry("1250x700")
        self.csv_path = CSV_PATH_DEFAULT
        self.rows = []  # liste de dicts
        self.selected_index = None  # index dans self.rows correspondant à la ligne affichée sélectionnée

        self._build_menu()
        self._build_widgets()
        self._load_csv(self.csv_path, silent=True)

    # ------------------------------------------------------------------ UI
    def _build_menu(self):
        menubar = tk.Menu(self)
        filemenu = tk.Menu(menubar, tearoff=0)
        filemenu.add_command(label="Ouvrir un CSV...", command=self.ouvrir_csv)
        filemenu.add_command(label="Enregistrer", command=self.enregistrer_csv)
        filemenu.add_command(label="Enregistrer sous...", command=self.enregistrer_sous)
        filemenu.add_separator()
        filemenu.add_command(label="Quitter", command=self.quit)
        menubar.add_cascade(label="Fichier", menu=filemenu)
        self.config(menu=menubar)

    def _build_widgets(self):
        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True)

        onglet_planning = ttk.Frame(notebook)
        onglet_decision = ttk.Frame(notebook)
        onglet_graphiques = ttk.Frame(notebook)
        notebook.add(onglet_planning, text="Planning cultural")
        notebook.add(onglet_decision, text="Aide à la décision (météo)")
        notebook.add(onglet_graphiques, text="Graphiques météo")

        self._build_onglet_planning(onglet_planning)
        self._build_onglet_decision(onglet_decision)
        self._build_onglet_graphiques(onglet_graphiques)

    def _build_onglet_planning(self, parent):
        # --- Zone de filtre / recherche ---
        top = ttk.Frame(parent, padding=8)
        top.pack(side="top", fill="x")

        ttk.Label(top, text="Recherche (culture) :").pack(side="left")
        self.var_recherche = tk.StringVar()
        self.var_recherche.trace_add("write", lambda *a: self._rafraichir_tableau())
        ttk.Entry(top, textvariable=self.var_recherche, width=25).pack(side="left", padx=(4, 16))

        ttk.Label(top, text="Conduite :").pack(side="left")
        self.var_filtre_conduite = tk.StringVar(value="Toutes")
        cb = ttk.Combobox(top, textvariable=self.var_filtre_conduite, state="readonly", width=8,
                           values=["Toutes"] + CONDUITES)
        cb.pack(side="left", padx=(4, 16))
        cb.bind("<<ComboboxSelected>>", lambda e: self._rafraichir_tableau())

        ttk.Label(top, text="Action :").pack(side="left")
        self.var_filtre_action = tk.StringVar(value="Toutes")
        cb2 = ttk.Combobox(top, textvariable=self.var_filtre_action, state="readonly", width=18,
                            values=["Toutes"] + ACTIONS)
        cb2.pack(side="left", padx=(4, 16))
        cb2.bind("<<ComboboxSelected>>", lambda e: self._rafraichir_tableau())

        ttk.Label(top, text="Mois en cours :").pack(side="left")
        self.var_filtre_mois = tk.StringVar(value="Tous")
        cb3 = ttk.Combobox(top, textvariable=self.var_filtre_mois, state="readonly", width=12,
                            values=["Tous"] + MONTH_FR)
        cb3.pack(side="left", padx=(4, 16))
        cb3.bind("<<ComboboxSelected>>", lambda e: self._rafraichir_tableau())

        # --- Tableau (Treeview) ---
        mid = ttk.Frame(parent, padding=(8, 0))
        mid.pack(side="top", fill="both", expand=True)

        columns = FIELDS
        headers = ["Culture", "Conduite", "Variété n°", "Action", "Sem. début", "Sem. fin",
                   "Mois début", "Mois fin", "Commentaire"]
        self.tree = ttk.Treeview(mid, columns=columns, show="headings", selectmode="browse")
        for col, head in zip(columns, headers):
            self.tree.heading(col, text=head, command=lambda c=col: self._trier_par(c))
            width = 220 if col == "commentaire" else (110 if col == "culture" else 90)
            self.tree.column(col, width=width, anchor="w")
        self.tree.pack(side="left", fill="both", expand=True)

        scroll = ttk.Scrollbar(mid, orient="vertical", command=self.tree.yview)
        scroll.pack(side="left", fill="y")
        self.tree.configure(yscrollcommand=scroll.set)

        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        # --- Formulaire d'édition à droite ---
        form = ttk.LabelFrame(parent, text="Détail de l'entrée", padding=10)
        form.pack(side="right", fill="y", padx=8, pady=8)

        self.vars = {}
        row = 0
        ttk.Label(form, text="Culture :").grid(row=row, column=0, sticky="w", pady=3)
        self.vars["culture"] = tk.StringVar()
        ttk.Entry(form, textvariable=self.vars["culture"], width=28).grid(row=row, column=1, pady=3)
        row += 1

        ttk.Label(form, text="Conduite :").grid(row=row, column=0, sticky="w", pady=3)
        self.vars["conduite"] = tk.StringVar(value="SA")
        ttk.Combobox(form, textvariable=self.vars["conduite"], values=CONDUITES,
                     state="readonly", width=25).grid(row=row, column=1, pady=3)
        row += 1

        ttk.Label(form, text="Variété n° :").grid(row=row, column=0, sticky="w", pady=3)
        self.vars["variete_n"] = tk.StringVar(value="1")
        ttk.Entry(form, textvariable=self.vars["variete_n"], width=28).grid(row=row, column=1, pady=3)
        row += 1

        ttk.Label(form, text="Action :").grid(row=row, column=0, sticky="w", pady=3)
        self.vars["action"] = tk.StringVar(value=ACTIONS[0])
        ttk.Combobox(form, textvariable=self.vars["action"], values=ACTIONS,
                     state="readonly", width=25).grid(row=row, column=1, pady=3)
        row += 1

        ttk.Label(form, text="Semaine début (1-52) :").grid(row=row, column=0, sticky="w", pady=3)
        self.vars["semaine_debut"] = tk.StringVar(value="1")
        ttk.Spinbox(form, from_=1, to=52, textvariable=self.vars["semaine_debut"],
                    width=26).grid(row=row, column=1, pady=3)
        row += 1

        ttk.Label(form, text="Semaine fin (1-52) :").grid(row=row, column=0, sticky="w", pady=3)
        self.vars["semaine_fin"] = tk.StringVar(value="1")
        ttk.Spinbox(form, from_=1, to=52, textvariable=self.vars["semaine_fin"],
                    width=26).grid(row=row, column=1, pady=3)
        row += 1

        ttk.Label(form, text="Commentaire :").grid(row=row, column=0, sticky="nw", pady=3)
        self.txt_commentaire = tk.Text(form, width=28, height=5, wrap="word")
        self.txt_commentaire.grid(row=row, column=1, pady=3)
        row += 1

        btns = ttk.Frame(form)
        btns.grid(row=row, column=0, columnspan=2, pady=(12, 4), sticky="ew")
        ttk.Button(btns, text="Nouvelle entrée", command=self._nouvelle_entree).pack(fill="x", pady=2)
        ttk.Button(btns, text="Ajouter", command=self._ajouter).pack(fill="x", pady=2)
        ttk.Button(btns, text="Enregistrer modification", command=self._modifier).pack(fill="x", pady=2)
        ttk.Button(btns, text="Supprimer", command=self._supprimer).pack(fill="x", pady=2)

        # --- Barre de statut ---
        self.status = tk.StringVar(value="Prêt.")
        ttk.Label(self, textvariable=self.status, relief="sunken", anchor="w").pack(side="bottom", fill="x")

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
                self.status.set(f"{len(self.rows)} entrées chargées depuis {path}")
            except Exception as e:
                if not silent:
                    messagebox.showerror("Erreur", f"Impossible de lire le fichier :\n{e}")
        else:
            if not silent:
                messagebox.showinfo("Info", "Aucun fichier existant : un nouveau planning vide a été créé.")
            self.status.set("Nouveau planning (aucun fichier chargé).")
        self._rafraichir_tableau()
        if hasattr(self, "cb_dec_culture"):
            self._maj_liste_cultures()

    def ouvrir_csv(self):
        path = filedialog.askopenfilename(title="Ouvrir un planning CSV",
                                           filetypes=[("Fichiers CSV", "*.csv"), ("Tous les fichiers", "*.*")])
        if path:
            self._load_csv(path)

    def enregistrer_csv(self):
        self._ecrire_csv(self.csv_path)

    def enregistrer_sous(self):
        path = filedialog.asksaveasfilename(title="Enregistrer sous...", defaultextension=".csv",
                                             filetypes=[("Fichiers CSV", "*.csv")])
        if path:
            self.csv_path = path
            self._ecrire_csv(path)

    def _ecrire_csv(self, path):
        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=FIELDS, delimiter=";")
                writer.writeheader()
                for r in self.rows:
                    writer.writerow(r)
            self.status.set(f"Enregistré : {path} ({len(self.rows)} entrées)")
        except Exception as e:
            messagebox.showerror("Erreur", f"Impossible d'enregistrer :\n{e}")

    # ------------------------------------------------------------ Tableau
    def _lignes_filtrees(self):
        recherche = self.var_recherche.get().strip().lower()
        f_conduite = self.var_filtre_conduite.get()
        f_action = self.var_filtre_action.get()
        f_mois = self.var_filtre_mois.get()

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
        self.tree.delete(*self.tree.get_children())
        self._visible = self._lignes_filtrees()
        for idx, r in self._visible:
            values = [r.get(f, "") for f in FIELDS]
            self.tree.insert("", "end", iid=str(idx), values=values)
        self.status.set(f"{len(self._visible)} entrée(s) affichée(s) sur {len(self.rows)} au total.")

    def _trier_par(self, col):
        try:
            self.rows.sort(key=lambda r: (int(r[col]) if r[col].isdigit() else r[col]))
        except Exception:
            self.rows.sort(key=lambda r: r.get(col, ""))
        self._rafraichir_tableau()

    def _on_select(self, event):
        sel = self.tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        self.selected_index = idx
        r = self.rows[idx]
        for k in ["culture", "conduite", "variete_n", "action", "semaine_debut", "semaine_fin"]:
            self.vars[k].set(r.get(k, ""))
        self.txt_commentaire.delete("1.0", "end")
        self.txt_commentaire.insert("1.0", r.get("commentaire", ""))

    # ------------------------------------------------------------ CRUD
    def _lire_formulaire(self):
        try:
            sem_d = int(self.vars["semaine_debut"].get())
            sem_f = int(self.vars["semaine_fin"].get())
        except ValueError:
            messagebox.showwarning("Valeur invalide", "Les semaines doivent être des nombres entiers (1-52).")
            return None
        if not (1 <= sem_d <= 52) or not (1 <= sem_f <= 52):
            messagebox.showwarning("Valeur invalide", "Les semaines doivent être comprises entre 1 et 52.")
            return None
        culture = self.vars["culture"].get().strip()
        if not culture:
            messagebox.showwarning("Champ requis", "Le nom de la culture est requis.")
            return None
        return {
            "culture": culture,
            "conduite": self.vars["conduite"].get(),
            "variete_n": self.vars["variete_n"].get().strip() or "1",
            "action": self.vars["action"].get(),
            "semaine_debut": str(sem_d),
            "semaine_fin": str(sem_f),
            "mois_debut": semaine_vers_mois(sem_d),
            "mois_fin": semaine_vers_mois(sem_f),
            "commentaire": self.txt_commentaire.get("1.0", "end").strip(),
        }

    def _nouvelle_entree(self):
        self.selected_index = None
        self.tree.selection_remove(self.tree.selection())
        self.vars["culture"].set("")
        self.vars["conduite"].set("SA")
        self.vars["variete_n"].set("1")
        self.vars["action"].set(ACTIONS[0])
        self.vars["semaine_debut"].set("1")
        self.vars["semaine_fin"].set("1")
        self.txt_commentaire.delete("1.0", "end")

    def _ajouter(self):
        data = self._lire_formulaire()
        if data is None:
            return
        self.rows.append(data)
        self._rafraichir_tableau()
        if hasattr(self, "cb_dec_culture"):
            self._maj_liste_cultures()
        self.status.set(f"Entrée ajoutée : {data['culture']} ({data['conduite']})")

    def _modifier(self):
        if self.selected_index is None:
            messagebox.showinfo("Info", "Sélectionnez d'abord une entrée dans le tableau à modifier.")
            return
        data = self._lire_formulaire()
        if data is None:
            return
        self.rows[self.selected_index] = data
        self._rafraichir_tableau()
        self.status.set(f"Entrée modifiée : {data['culture']} ({data['conduite']})")

    def _supprimer(self):
        if self.selected_index is None:
            messagebox.showinfo("Info", "Sélectionnez d'abord une entrée dans le tableau à supprimer.")
            return
        if messagebox.askyesno("Confirmation", "Supprimer cette entrée du planning ?"):
            del self.rows[self.selected_index]
            self.selected_index = None
            self._rafraichir_tableau()
            self.status.set("Entrée supprimée.")

    # ============================================================
    # Onglet "Aide à la décision (météo)"
    # ============================================================
    def _build_onglet_decision(self, parent):
        info = (
            "Cet outil applique des règles agronomiques simples (gel, pluie, vent) aux "
            "prévisions Météociel pour suggérer le meilleur moment pour une action. "
            "Ce n'est pas une prédiction garantie : vérifiez toujours l'état du terrain."
        )
        ttk.Label(parent, text=info, wraplength=850, foreground="#555").pack(
            side="top", fill="x", padx=10, pady=(10, 4))

        if not md.METEOCIEL_AVAILABLE:
            ttk.Label(
                parent,
                text=("⚠ Le paquet 'meteociel-api' n'est pas installé sur cette machine. "
                      "Installez-le avec :  pip install meteociel-api"),
                foreground="red", wraplength=850,
            ).pack(side="top", fill="x", padx=10, pady=(0, 8))

        form = ttk.Frame(parent, padding=10)
        form.pack(side="top", fill="x")

        # Ligne 1 : culture / conduite / variété
        ttk.Label(form, text="Culture :").grid(row=0, column=0, sticky="w", padx=4, pady=4)
        self.var_dec_culture = tk.StringVar()
        self.cb_dec_culture = ttk.Combobox(form, textvariable=self.var_dec_culture, width=28)
        self.cb_dec_culture.grid(row=0, column=1, padx=4, pady=4)
        self.cb_dec_culture.bind("<<ComboboxSelected>>", lambda e: self._maj_variete_conduite())
        self.cb_dec_culture.bind("<KeyRelease>", lambda e: self._filtrer_autocompletion_culture())

        ttk.Label(form, text="Conduite :").grid(row=0, column=2, sticky="w", padx=4, pady=4)
        self.var_dec_conduite = tk.StringVar(value="Toutes")
        self.cb_dec_conduite = ttk.Combobox(form, textvariable=self.var_dec_conduite,
                                             values=["Toutes"] + CONDUITES, state="readonly", width=10)
        self.cb_dec_conduite.grid(row=0, column=3, padx=4, pady=4)

        ttk.Label(form, text="Variété n° :").grid(row=0, column=4, sticky="w", padx=4, pady=4)
        self.var_dec_variete = tk.StringVar(value="Toutes")
        self.cb_dec_variete = ttk.Combobox(form, textvariable=self.var_dec_variete,
                                            values=["Toutes"], state="readonly", width=8)
        self.cb_dec_variete.grid(row=0, column=5, padx=4, pady=4)

        # Ligne 2 : action / ville
        ttk.Label(form, text="Action :").grid(row=1, column=0, sticky="w", padx=4, pady=4)
        self.var_dec_action = tk.StringVar(value=ACTIONS[0])
        ttk.Combobox(form, textvariable=self.var_dec_action, values=ACTIONS,
                     state="readonly", width=28).grid(row=1, column=1, padx=4, pady=4)

        ttk.Label(form, text="Ville (Météociel) :").grid(row=1, column=2, sticky="w", padx=4, pady=4)
        self.var_dec_ville = tk.StringVar(value="Paris (75000)")
        ttk.Entry(form, textvariable=self.var_dec_ville, width=22).grid(
            row=1, column=3, columnspan=2, padx=4, pady=4, sticky="w")

        # Ligne 3 : mode / modèle
        ttk.Label(form, text="Source météo :").grid(row=2, column=0, sticky="w", padx=4, pady=4)
        self.var_dec_mode = tk.StringVar(value=list(md.MODES_DISPONIBLES.keys())[0])
        cb_mode = ttk.Combobox(form, textvariable=self.var_dec_mode,
                                values=list(md.MODES_DISPONIBLES.keys()), state="readonly", width=38)
        cb_mode.grid(row=2, column=1, columnspan=2, padx=4, pady=4, sticky="w")
        cb_mode.bind("<<ComboboxSelected>>", lambda e: self._maj_etat_modele())

        ttk.Label(form, text="Modèle :").grid(row=2, column=3, sticky="w", padx=4, pady=4)
        self.var_dec_modele = tk.StringVar(value="gfs")
        self.cb_dec_modele = ttk.Combobox(form, textvariable=self.var_dec_modele,
                                           values=md.MODELES_DISPONIBLES, state="readonly", width=10)
        self.cb_dec_modele.grid(row=2, column=4, padx=4, pady=4, sticky="w")

        self.btn_dec_analyser = ttk.Button(form, text="Analyser", command=self._lancer_analyse_decision)
        self.btn_dec_analyser.grid(row=3, column=0, columnspan=2, pady=(8, 4), sticky="ew")

        # Zone de résultats
        result_frame = ttk.LabelFrame(parent, text="Résultat de l'analyse", padding=8)
        result_frame.pack(side="top", fill="both", expand=True, padx=10, pady=(0, 10))
        self.txt_dec_resultat = scrolledtext.ScrolledText(result_frame, wrap="word", height=20)
        self.txt_dec_resultat.pack(fill="both", expand=True)
        self.txt_dec_resultat.insert("1.0", "Sélectionnez une culture et une action, puis cliquez sur "
                                             "« Analyser ».")
        self.txt_dec_resultat.configure(state="disabled")

        self._maj_liste_cultures()

    def _maj_liste_cultures(self):
        """Met à jour la liste déroulante des cultures depuis le planning chargé."""
        cultures = sorted({r["culture"] for r in self.rows if r.get("culture")})
        self.cb_dec_culture.configure(values=cultures)
        if cultures and not self.var_dec_culture.get():
            self.var_dec_culture.set(cultures[0])
        self._maj_variete_conduite()

    def _filtrer_autocompletion_culture(self):
        texte = self.var_dec_culture.get().strip().lower()
        cultures = sorted({r["culture"] for r in self.rows if r.get("culture")})
        if texte:
            cultures = [c for c in cultures if texte in c.lower()]
        self.cb_dec_culture.configure(values=cultures)

    def _maj_variete_conduite(self):
        culture = self.var_dec_culture.get().strip().lower()
        varietes = sorted({str(r.get("variete_n", "1")) for r in self.rows
                            if r.get("culture", "").strip().lower() == culture},
                           key=lambda x: (len(x), x))
        self.cb_dec_variete.configure(values=["Toutes"] + varietes)
        self.var_dec_variete.set("Toutes")

    def _maj_etat_modele(self):
        mode = md.MODES_DISPONIBLES.get(self.var_dec_mode.get(), "forecasts")
        self.cb_dec_modele.configure(state="readonly" if mode == "forecasts" else "disabled")

    def _ecrire_resultat(self, texte):
        self.txt_dec_resultat.configure(state="normal")
        self.txt_dec_resultat.delete("1.0", "end")
        self.txt_dec_resultat.insert("1.0", texte)
        self.txt_dec_resultat.configure(state="disabled")

    def _lancer_analyse_decision(self):
        culture = self.var_dec_culture.get().strip()
        conduite_sel = self.var_dec_conduite.get()
        variete = self.var_dec_variete.get()
        action = self.var_dec_action.get()
        ville = self.var_dec_ville.get().strip()
        mode = md.MODES_DISPONIBLES.get(self.var_dec_mode.get(), "forecasts")
        modele = self.var_dec_modele.get()

        if not culture:
            messagebox.showwarning("Champ requis", "Veuillez indiquer une culture.")
            return
        if not ville:
            messagebox.showwarning("Champ requis", "Veuillez indiquer une ville pour la météo.")
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

        self._ecrire_resultat(
            texte_calendrier + "\n\n⏳ Récupération des prévisions météo Météociel en cours..."
        )
        self.btn_dec_analyser.configure(state="disabled")
        self.status.set("Analyse météo en cours...")

        def tache_fond():
            try:
                _, _, texte_meteo = md.recommander(action, ville, mode=mode, modele=modele)
                erreur = None
            except Exception as e:  # réseau, ville introuvable, paquet manquant, etc.
                texte_meteo = None
                erreur = e
            self.after(0, lambda: self._analyse_terminee(texte_calendrier, texte_meteo, erreur))

        threading.Thread(target=tache_fond, daemon=True).start()

    def _analyse_terminee(self, texte_calendrier, texte_meteo, erreur):
        self.btn_dec_analyser.configure(state="normal")
        if erreur is not None:
            self._ecrire_resultat(
                texte_calendrier +
                f"\n\n❌ Impossible de récupérer les données météo Météociel :\n{erreur}"
            )
            self.status.set("Échec de la récupération météo.")
            return
        self._ecrire_resultat(texte_calendrier + "\n\n--- Analyse météo ---\n" + texte_meteo)
        self.status.set("Analyse météo terminée.")

    # ============================================================
    # Onglet "Graphiques météo"
    # ============================================================
    def _build_onglet_graphiques(self, parent):
        if not MATPLOTLIB_AVAILABLE:
            ttk.Label(
                parent,
                text=("⚠ Le paquet 'matplotlib' n'est pas installé. Installez-le avec :\n"
                      "pip install matplotlib"),
                foreground="red", wraplength=850, justify="left",
            ).pack(padx=20, pady=20, anchor="w")
            return

        form = ttk.Frame(parent, padding=10)
        form.pack(side="top", fill="x")

        ttk.Label(form, text="Ville (Météociel) :").grid(row=0, column=0, sticky="w", padx=4, pady=4)
        self.var_graph_ville = tk.StringVar(value="Paris (75000)")
        ttk.Entry(form, textvariable=self.var_graph_ville, width=24).grid(
            row=0, column=1, padx=4, pady=4, sticky="w")

        ttk.Label(form, text="Source météo :").grid(row=0, column=2, sticky="w", padx=4, pady=4)
        self.var_graph_mode = tk.StringVar(value=list(md.MODES_DISPONIBLES.keys())[0])
        cb_mode = ttk.Combobox(form, textvariable=self.var_graph_mode,
                                values=list(md.MODES_DISPONIBLES.keys()), state="readonly", width=38)
        cb_mode.grid(row=0, column=3, padx=4, pady=4, sticky="w")
        cb_mode.bind("<<ComboboxSelected>>", lambda e: self._maj_etat_modele_graph())

        ttk.Label(form, text="Modèle :").grid(row=0, column=4, sticky="w", padx=4, pady=4)
        self.var_graph_modele = tk.StringVar(value="gfs")
        self.cb_graph_modele = ttk.Combobox(form, textvariable=self.var_graph_modele,
                                             values=md.MODELES_DISPONIBLES, state="readonly", width=10)
        self.cb_graph_modele.grid(row=0, column=5, padx=4, pady=4, sticky="w")

        self.btn_graph_charger = ttk.Button(form, text="Afficher le graphique",
                                             command=self._lancer_chargement_graphique)
        self.btn_graph_charger.grid(row=0, column=6, padx=(16, 4), pady=4)

        self.lbl_graph_status = ttk.Label(parent, text="Choisissez une ville puis cliquez sur "
                                                         "« Afficher le graphique ».", foreground="#555")
        self.lbl_graph_status.pack(side="top", fill="x", padx=14)

        # Zone du graphique matplotlib
        graph_frame = ttk.Frame(parent)
        graph_frame.pack(side="top", fill="both", expand=True, padx=10, pady=10)

        self.fig_meteo = Figure(figsize=(10, 6.5), dpi=100)
        self.axes_meteo = self.fig_meteo.subplots(2, 2)
        self.fig_meteo.tight_layout(pad=3.0)

        self.canvas_meteo = FigureCanvasTkAgg(self.fig_meteo, master=graph_frame)
        self.canvas_meteo.get_tk_widget().pack(side="top", fill="both", expand=True)

        toolbar_frame = ttk.Frame(graph_frame)
        toolbar_frame.pack(side="top", fill="x")
        self.toolbar_meteo = NavigationToolbar2Tk(self.canvas_meteo, toolbar_frame)
        self.toolbar_meteo.update()

        self._dessiner_graphiques_vides()

    def _maj_etat_modele_graph(self):
        mode = md.MODES_DISPONIBLES.get(self.var_graph_mode.get(), "forecasts")
        self.cb_graph_modele.configure(state="readonly" if mode == "forecasts" else "disabled")

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
        ville = self.var_graph_ville.get().strip()
        if not ville:
            messagebox.showwarning("Champ requis", "Veuillez indiquer une ville pour la météo.")
            return
        mode = md.MODES_DISPONIBLES.get(self.var_graph_mode.get(), "forecasts")
        modele = self.var_graph_modele.get()

        self.btn_graph_charger.configure(state="disabled")
        self.lbl_graph_status.configure(text="⏳ Récupération des données Météociel en cours...")

        def tache_fond():
            try:
                ville_trouvee, df = md.recuperer_previsions(ville, mode=mode, modele=modele)
                erreur = None
            except Exception as e:
                ville_trouvee, df, erreur = None, None, e
            self.after(0, lambda: self._graphique_termine(ville_trouvee, df, erreur))

        threading.Thread(target=tache_fond, daemon=True).start()

    def _graphique_termine(self, ville_trouvee, df, erreur):
        self.btn_graph_charger.configure(state="normal")
        if erreur is not None:
            self.lbl_graph_status.configure(text=f"❌ Échec de la récupération météo : {erreur}")
            return

        if df is None or df.empty:
            self.lbl_graph_status.configure(text="Aucune donnée renvoyée par Météociel.")
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

        self.lbl_graph_status.configure(
            text=f"✅ Données chargées pour « {ville_trouvee} » ({len(df)} relevés).")


if __name__ == "__main__":
    app = PlanningApp()
    app.mainloop()
