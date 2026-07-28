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
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

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
        # --- Zone de filtre / recherche ---
        top = ttk.Frame(self, padding=8)
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
        mid = ttk.Frame(self, padding=(8, 0))
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
        form = ttk.LabelFrame(self, text="Détail de l'entrée", padding=10)
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


if __name__ == "__main__":
    app = PlanningApp()
    app.mainloop()
