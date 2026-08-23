#!/usr/bin/env python3
"""
Récupère, pour chaque code postal présent dans index_villes.json, la liste des
communes et de leur véritable identifiant de PRÉVISION Météociel (celui utilisé
dans les URL https://www.meteociel.fr/previsions/ID/nom_commune.htm), en
interrogeant le moteur de recherche officiel du site :

    https://www.meteociel.fr/prevville.php?action=getville&envoyer=OK&ville=<code_postal>

Une seule requête par CODE POSTAL suffit : la page retourne déjà toutes les
communes qui partagent ce code postal, avec leur identifiant de prévision.

⚠️ À EXÉCUTER SUR VOTRE MACHINE (pas dans le sandbox Claude) :
   le domaine meteociel.fr n'est pas autorisé par le pare-feu du bac à sable.

Installation :
    pip install requests

Usage :
    python scrape_meteociel_ids.py \
        --index-villes index_villes.json \
        --output meteociel_index.json

Le script sauvegarde un fichier de reprise (checkpoint) au fur et à mesure,
afin de pouvoir être interrompu et relancé sans perdre la progression.
"""

import argparse
import json
import re
import time
import unicodedata
from pathlib import Path

import requests

BASE_URL = "https://www.meteociel.fr/prevville.php"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}

# Capture chaque lien de résultat : /previsions/<id>/<slug>.htm">Nom ( CP )
RESULT_RE = re.compile(
    r'/previsions/(\d+)/[^"\'>]+\.htm["\']?[^>]*>\s*([^<(\n]+?)\s*\(\s*(\d{5})\s*\)',
    re.IGNORECASE,
)


def normalize(text: str) -> str:
    """Nettoie les espaces/insécables restants dans le texte extrait."""
    text = text.replace("\xa0", " ")
    text = unicodedata.normalize("NFC", text)
    return " ".join(text.split())


def fetch_postal_code(session: requests.Session, code_postal: str, retries: int = 3):
    """Interroge prevville.php pour un code postal et retourne les triples
    (id, nom, code_postal) trouvés sur la page."""
    params = {"action": "getville", "envoyer": "OK", "ville": code_postal}
    for attempt in range(1, retries + 1):
        try:
            resp = session.get(BASE_URL, params=params, headers=HEADERS, timeout=15)
            resp.encoding = "ISO-8859-1"  # charset déclaré par le site
            html = resp.text
            matches = RESULT_RE.findall(html)
            return [
                (int(city_id), normalize(nom), cp)
                for city_id, nom, cp in matches
            ]
        except requests.RequestException as exc:
            wait = 2 * attempt
            print(f"  [!] Erreur sur {code_postal} ({exc}) - retry dans {wait}s")
            time.sleep(wait)
    print(f"  [x] Abandon pour le code postal {code_postal} après {retries} tentatives")
    return []


def load_unique_postal_codes(index_villes_path: Path):
    with open(index_villes_path, encoding="utf-8") as f:
        data = json.load(f)
    codes = sorted({d["code_postal"] for d in data if d.get("code_postal")})
    return codes


def load_checkpoint(checkpoint_path: Path):
    if checkpoint_path.exists():
        with open(checkpoint_path, encoding="utf-8") as f:
            return json.load(f)
    return {"done_codes": [], "result": {}}


def save_checkpoint(checkpoint_path: Path, state: dict):
    with open(checkpoint_path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index-villes", default="index_villes.json",
                         help="Chemin vers index_villes.json")
    parser.add_argument("--output", default="meteociel_index.json",
                         help="Fichier JSON final (nom (cp) -> id)")
    parser.add_argument("--checkpoint", default="meteociel_scrape_checkpoint.json",
                         help="Fichier de reprise en cas d'interruption")
    parser.add_argument("--delay", type=float, default=0.6,
                         help="Pause en secondes entre deux requêtes (soyez respectueux du site)")
    args = parser.parse_args()

    index_villes_path = Path(args.index_villes)
    output_path = Path(args.output)
    checkpoint_path = Path(args.checkpoint)

    codes = load_unique_postal_codes(index_villes_path)
    print(f"{len(codes)} codes postaux uniques à interroger.")

    state = load_checkpoint(checkpoint_path)
    done = set(state["done_codes"])
    result = state["result"]

    remaining = [c for c in codes if c not in done]
    print(f"{len(remaining)} restants (reprise sur {len(done)} déjà faits).")

    session = requests.Session()

    for i, cp in enumerate(remaining, 1):
        entries = fetch_postal_code(session, cp)
        for city_id, nom, cp_found in entries:
            key = f"{nom} ({cp_found})"
            result[key] = city_id

        done.add(cp)
        state["done_codes"] = list(done)
        state["result"] = result

        if i % 20 == 0 or i == len(remaining):
            save_checkpoint(checkpoint_path, state)
            print(f"[{i}/{len(remaining)}] {cp} -> {len(entries)} commune(s) "
                  f"| total collecté : {len(result)}")

        time.sleep(args.delay)

    save_checkpoint(checkpoint_path, state)

    sorted_result = dict(sorted(result.items(), key=lambda kv: kv[0]))
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(sorted_result, f, ensure_ascii=False, indent=2)

    print(f"\nTerminé : {len(sorted_result)} entrées écrites dans {output_path}")


if __name__ == "__main__":
    main()
