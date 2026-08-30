#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generer_index_previsions.py
------------------------------
Construit un fichier JSON associant, pour chaque commune française connue de
Météociel côté STATIONS (voir index_villes.json, 12 800 entrées issues de
cities_database.json), la clé "Nom (code_postal)" (ou juste "Nom" quand le
code postal n'est pas connu) à son IDENTIFIANT DE PRÉVISIONS Météociel -
c'est-à-dire l'identifiant numérique qu'on trouve dans une URL du type
https://www.meteociel.fr/previsions/29154/buc.htm, DIFFÉRENT du city_id des
stations (voir meteo_decision.py, commentaire au-dessus de
_resoudre_et_appeler_previsions, pour le détail de cette distinction).

Une fois ce fichier construit, l'application peut retrouver instantanément
l'identifiant de prévisions de n'importe quelle ville de la liste sans
JAMAIS avoir à interroger la page de recherche par nom de Météociel (donc
plus aucun risque de "TooManyCitiesError" en cours d'utilisation, même pour
des homonymes comme Buc) : cache_ids_previsions.json n'est alors plus
alimenté au fil de l'eau (une ville à la fois, à la première utilisation)
mais pré-rempli intégralement, une bonne fois pour toutes.

Pourquoi un script séparé, à exécuter à la main (une seule fois, en tâche de
fond) :
    - ~12 800 communes à interroger, une requête HTTP chacune -> plusieurs
      heures avec un délai raisonnable entre deux requêtes (voir --delai) ;
    - reprise automatique en cas d'interruption (Ctrl+C, coupure réseau...) :
      le fichier de sortie est sauvegardé régulièrement en cours de route, et
      relancer le script saute directement les communes déjà résolues.

Utilisation :
    pip install meteociel-api requests
    python generer_index_previsions.py

    (options : --delai 1.5   pour espacer davantage les requêtes
               --limite 500  pour ne traiter que les 500 premières
                             communes restantes (utile pour tester)
               --sortie chemin.json / --erreurs chemin.json
                             pour changer les fichiers de sortie)

Le script doit être exécuté dans le dossier de l'application (à côté de
index_villes.json, cities_database.json et meteo_decision.py), car il
réutilise directement la logique de résolution de meteo_decision.py
(_resoudre_id_previsions / _choisir_parmi_candidats) - exactement la même
que celle utilisée en direct par l'application, garantissant un résultat
cohérent avec ce qu'elle produirait ville par ville.
"""

import argparse
import json
import os
import sys
import time

_ICI = os.path.dirname(os.path.abspath(__file__))
CHEMIN_INDEX_VILLES = os.path.join(_ICI, "index_villes.json")
CHEMIN_SORTIE_DEFAUT = os.path.join(_ICI, "identifiants_previsions.json")
CHEMIN_ERREURS_DEFAUT = os.path.join(_ICI, "identifiants_previsions_erreurs.json")

try:
    import meteo_decision as md
except ImportError as exc:
    print(
        f"Impossible d'importer meteo_decision.py ({exc}).\n"
        "Lancez ce script depuis le dossier de l'application (celui qui "
        "contient meteo_decision.py, index_villes.json, cities_database.json)."
    )
    sys.exit(1)

if not md.METEOCIEL_AVAILABLE:
    print(
        "Le paquet 'meteociel-api' n'est pas installé.\n"
        "Installez-le avec : pip install meteociel-api"
    )
    sys.exit(1)

from meteociel.forecasts import TooManyCitiesError


def cle_commune(nom, code_postal):
    """Clé utilisée dans le fichier de sortie : "Nom (code_postal)", ou
    juste "Nom" si le code postal n'est pas connu (rare - voir
    index_villes.json, ~1100 communes sur 12800 sans code postal dérivé)."""
    return f"{nom} ({code_postal})" if code_postal else nom


def communes_uniques():
    """Charge index_villes.json et renvoie la liste dédoublonnée des
    couples (nom, code_postal) à résoudre : plusieurs entrées de
    index_villes.json (une par STATION) peuvent correspondre à la même
    commune (ex. deux stations "secondaire"/"amateur" pour Arbent), pour
    laquelle l'identifiant de prévisions est le même - inutile de
    l'interroger deux fois."""
    with open(CHEMIN_INDEX_VILLES, encoding="utf-8") as f:
        entrees = json.load(f)

    vues = set()
    communes = []
    for e in entrees:
        paire = (e["nom"], e.get("code_postal"))
        if paire in vues:
            continue
        vues.add(paire)
        communes.append(paire)
    return communes


def charger_json(chemin):
    if os.path.exists(chemin):
        with open(chemin, encoding="utf-8") as f:
            return json.load(f)
    return {}


def sauvegarder_json(chemin, donnees):
    # Écriture via un fichier temporaire puis remplacement atomique, pour ne
    # jamais laisser un fichier de sortie tronqué/corrompu en cas
    # d'interruption (Ctrl+C, coupure de courant...) pile pendant l'écriture.
    chemin_tmp = chemin + ".tmp"
    with open(chemin_tmp, "w", encoding="utf-8") as f:
        json.dump(donnees, f, ensure_ascii=False, indent=2, sort_keys=True)
    os.replace(chemin_tmp, chemin)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--delai", type=float, default=1.0,
                         help="Délai en secondes entre deux requêtes (défaut : 1.0)")
    parser.add_argument("--limite", type=int, default=None,
                         help="Nombre maximal de communes à traiter lors de cette exécution "
                              "(défaut : toutes les communes restantes)")
    parser.add_argument("--sortie", default=CHEMIN_SORTIE_DEFAUT,
                         help=f"Fichier de sortie (défaut : {CHEMIN_SORTIE_DEFAUT})")
    parser.add_argument("--erreurs", default=CHEMIN_ERREURS_DEFAUT,
                         help=f"Fichier des échecs/ambiguïtés non résolues (défaut : {CHEMIN_ERREURS_DEFAUT})")
    parser.add_argument("--sauvegarde-tous-les", type=int, default=20,
                         help="Sauvegarde le fichier de sortie tous les N succès (défaut : 20)")
    args = parser.parse_args()

    communes = communes_uniques()
    resultats = charger_json(args.sortie)
    erreurs = charger_json(args.erreurs)

    a_faire = [
        (nom, cp) for (nom, cp) in communes
        if cle_commune(nom, cp) not in resultats and cle_commune(nom, cp) not in erreurs
    ]

    print(f"{len(communes)} communes au total, {len(resultats)} déjà résolues, "
          f"{len(erreurs)} déjà en erreur, {len(a_faire)} restant à traiter.")

    if args.limite:
        a_faire = a_faire[: args.limite]
        print(f"(--limite {args.limite} : {len(a_faire)} communes traitées lors de cette exécution)")

    depuis_derniere_sauvegarde = 0
    traitees = 0
    try:
        for nom, code_postal in a_faire:
            cle = cle_commune(nom, code_postal)
            try:
                identifiant = md._resoudre_id_previsions(
                    nom, mode="forecasts", modele="gfs", code_postal_attendu=code_postal
                )
                resultats[cle] = identifiant
                depuis_derniere_sauvegarde += 1
            except TooManyCitiesError as e:
                erreurs[cle] = {"type": "ambigu", "detail": str(e)}
            except ValueError as e:
                erreurs[cle] = {"type": "introuvable", "detail": str(e)}
            except ConnectionError as e:
                # Problème réseau ponctuel : on ne le compte pas comme une
                # erreur définitive (il sera retenté à la prochaine
                # exécution, la clé n'étant ajoutée ni à resultats ni à
                # erreurs) - mais on interrompt la boucle plutôt que
                # d'enchaîner des échecs (connexion probablement coupée).
                print(f"\nErreur réseau sur « {cle} » : {e}\nArrêt (relancez le script pour reprendre).")
                break
            except Exception as e:  # pragma: no cover - robustesse générale
                erreurs[cle] = {"type": "autre", "detail": f"{type(e).__name__}: {e}"}

            traitees += 1
            print(f"[{traitees}/{len(a_faire)}] {cle} -> "
                  f"{resultats.get(cle, erreurs.get(cle, {}).get('type', '?'))}")

            if depuis_derniere_sauvegarde >= args.sauvegarde_tous_les:
                sauvegarder_json(args.sortie, resultats)
                sauvegarder_json(args.erreurs, erreurs)
                depuis_derniere_sauvegarde = 0

            time.sleep(args.delai)
    except KeyboardInterrupt:
        print("\nInterrompu par l'utilisateur.")
    finally:
        sauvegarder_json(args.sortie, resultats)
        sauvegarder_json(args.erreurs, erreurs)
        print(f"\nSauvegardé : {len(resultats)} résolues -> {args.sortie}")
        print(f"           {len(erreurs)} en erreur -> {args.erreurs}")
        print("Relancez simplement le script pour reprendre là où il s'est arrêté.")


if __name__ == "__main__":
    main()
