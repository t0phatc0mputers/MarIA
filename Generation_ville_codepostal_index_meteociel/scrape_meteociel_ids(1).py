#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scrape_meteociel_ids.py (v2)
--------------------------------------------------
Construit un fichier JSON associant chaque commune française (nom + code
postal, tirés de index_villes.json) à son identifiant de PRÉVISIONS
Météociel (celui de l'URL https://www.meteociel.fr/previsions/ID/nom.htm,
différent du city_id des stations d'observation).

Stratégie : une requête par CODE POSTAL (pas par commune) sur le moteur de
recherche officiel prevville.php, qui renvoie toutes les communes de ce code
postal en une seule page -> ~4000 requêtes au lieu de ~12000.

Par rapport à la v1, ce script :
  - envoie un jeu d'en-têtes de navigateur complet (Accept, Accept-Language,
    Referer) en plus du User-Agent : un site qui sert une page de
    "stub" de consentement (bannière cookies, sans contenu réel) à un
    client dépourvu de ces en-têtes le fait généralement passer sur la
    page complète dès qu'ils sont présents ;
  - gère le cas où Météociel redirige DIRECTEMENT vers la page de
    prévisions (une seule commune trouvée pour ce code postal) au lieu
    d'afficher une liste : dans ce cas le nom n'est pas dans la réponse
    de recherche, on va donc le chercher sur la page de destination ;
  - reprend la regex de liste `<li><a href="/previsions/ID/slug.htm">Nom
    ( CP )</a></li>` en restant tolérant aux variantes d'espacement ;
  - affiche un diagnostic clair si la page renvoyée ressemble à un mur de
    consentement (script CMP/IAB) sans contenu exploitable, pour repérer
    tout de suite si un blocage anti-bot persiste malgré les en-têtes.

Utilisation :
    pip install requests
    python scrape_meteociel_ids.py --index-villes index_villes.json
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
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
    "Referer": "https://www.meteociel.fr/prevville.php",
}

# Liste de résultats : <li><a href="/previsions/27295/aix_les_bains.htm">Aix-les-Bains ( 73100 )</a></li>
LIST_RE = re.compile(
    r'<a href="/(?:[a-z0-9_-]+)/(\d+)/[^"]+\.htm">\s*([^<(]+?)\s*\(\s*\xa0?\s*(\d{4,5})\s*\xa0?\s*\)\s*</a>',
    re.IGNORECASE,
)

# Redirection directe (un seul résultat) : <script lang=javascript>location.href='/previsions/27295/aix_les_bains.htm'</script>
DIRECT_RE = re.compile(r"location\.href='/([a-z0-9_-]+)/(\d+)/([^']+)'", re.IGNORECASE)

# Sur la page de destination elle-même, le titre contient "... pour Nom ( CP )"
TITLE_RE = re.compile(r"pour\s+([^<(]+?)\s*\(\s*\xa0?\s*(\d{4,5})\s*\xa0?\s*\)", re.IGNORECASE)

CONSENT_MARKERS = ("__tcfapiLocator", "AppConsent", "IAB STUB")


def normalize(text: str) -> str:
    text = text.replace("\xa0", " ")
    text = unicodedata.normalize("NFC", text)
    return " ".join(text.split())


def looks_like_consent_wall(html: str) -> bool:
    return any(marker in html for marker in CONSENT_MARKERS) and "previsions/" not in html


def request_with_retries(session: requests.Session, url: str, params: dict = None,
                          retries: int = 3):
    for attempt in range(1, retries + 1):
        try:
            resp = session.get(url, params=params, headers=HEADERS, timeout=15)
            resp.encoding = "ISO-8859-1"
            return resp
        except requests.RequestException as exc:
            wait = 2 * attempt
            print(f"  [!] Erreur réseau ({exc}) - retry dans {wait}s")
            time.sleep(wait)
    return None


def fetch_postal_code(session: requests.Session, code_postal: str, debug: bool = False):
    """Retourne la liste de (id, nom, cp) trouvés pour ce code postal."""
    resp = request_with_retries(
        session, BASE_URL,
        params={"action": "getville", "villeid": "", "ville": code_postal, "envoyer": "OK"},
    )
    if resp is None:
        print(f"  [x] Abandon pour {code_postal} (réseau)")
        return []

    html = resp.text

    if debug:
        wall = looks_like_consent_wall(html)
        print(f"    [debug] status={resp.status_code} len={len(html)} "
              f"mur_de_consentement_suspecte={wall}")

    # Cas 1 : liste de résultats
    matches = LIST_RE.findall(html)
    if matches:
        return [(int(i), normalize(nom), cp) for i, nom, cp in matches]

    # Cas 2 : redirection directe (une seule commune pour ce code postal)
    m = DIRECT_RE.search(html)
    if m:
        _mode, city_id, _slug = m.groups()
        dest_url = f"https://www.meteociel.fr/{_mode}/{city_id}/{_slug}"
        dest_resp = request_with_retries(session, dest_url)
        nom = None
        if dest_resp is not None:
            mt = TITLE_RE.search(dest_resp.text)
            if mt:
                nom = normalize(mt.group(1))
        if nom is None:
            # repli : nom déduit du slug (moins fiable pour les accents)
            nom = normalize(_slug.rsplit(".", 1)[0].replace("_", " ")).title()
        return [(int(city_id), nom, code_postal)]

    # Cas 3 : rien trouvé
    if debug and not matches and looks_like_consent_wall(html):
        debug_path = Path(f"debug_{code_postal}.html")
        debug_path.write_text(html, encoding="utf-8")
        print(f"    [debug] Page ressemblant à un mur de consentement sans "
              f"contenu -> sauvegardée dans {debug_path}")
        print(f"    [debug] extrait : {html[:800]!r}")

    return []


def load_unique_postal_codes(index_villes_path: Path):
    with open(index_villes_path, encoding="utf-8") as f:
        data = json.load(f)
    return sorted({d["code_postal"] for d in data if d.get("code_postal")})


def load_checkpoint(checkpoint_path: Path):
    if checkpoint_path.exists():
        with open(checkpoint_path, encoding="utf-8") as f:
            return json.load(f)
    return {"done_codes": [], "result": {}}


def save_checkpoint(checkpoint_path: Path, state: dict):
    tmp = checkpoint_path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)
    tmp.replace(checkpoint_path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index-villes", default="index_villes.json")
    parser.add_argument("--output", default="meteociel_index.json")
    parser.add_argument("--checkpoint", default="meteociel_scrape_checkpoint.json")
    parser.add_argument("--delay", type=float, default=0.6)
    parser.add_argument("--debug-first", type=int, default=5,
                         help="Diagnostic détaillé pour les N premières requêtes")
    args = parser.parse_args()

    codes = load_unique_postal_codes(Path(args.index_villes))
    print(f"{len(codes)} codes postaux uniques à interroger.")

    checkpoint_path = Path(args.checkpoint)
    state = load_checkpoint(checkpoint_path)
    done = set(state["done_codes"])
    result = state["result"]

    remaining = [c for c in codes if c not in done]
    print(f"{len(remaining)} restants (reprise sur {len(done)} déjà faits).")

    session = requests.Session()
    # Warmup : une première visite pose les cookies (session / consentement)
    warm = request_with_retries(session, "https://www.meteociel.fr/prevville.php")
    if warm is not None:
        print(f"[warmup] status={warm.status_code} cookies={dict(session.cookies)}")

    for i, cp in enumerate(remaining, 1):
        debug = i <= args.debug_first
        entries = fetch_postal_code(session, cp, debug=debug)

        for city_id, nom, cp_found in entries:
            result[f"{nom} ({cp_found})"] = city_id

        done.add(cp)
        state["done_codes"] = list(done)
        state["result"] = result

        if i % 20 == 0 or i == len(remaining):
            save_checkpoint(checkpoint_path, state)
            print(f"[{i}/{len(remaining)}] {cp} -> {len(entries)} commune(s) "
                  f"| total collecté : {len(result)}")

        if i == 30 and len(result) == 0:
            print("\n⚠ 30 codes postaux traités, toujours 0 résultat au total.")
            print("   Le blocage semble systématique malgré les en-têtes "
                  "navigateur complets.")
            print("   Regardez les fichiers debug_*.html générés : si le "
                  "vrai contenu (liens /previsions/…) y est absent, le site "
                  "impose probablement une vérification JavaScript "
                  "(consentement ou anti-bot) qu'un simple client `requests` "
                  "ne peut pas satisfaire — il faudrait alors passer par un "
                  "navigateur automatisé (Playwright/Selenium). Dites-le moi, "
                  "je vous écris cette variante.")

        time.sleep(args.delay)

    save_checkpoint(checkpoint_path, state)

    sorted_result = dict(sorted(result.items(), key=lambda kv: kv[0]))
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(sorted_result, f, ensure_ascii=False, indent=2)

    print(f"\nTerminé : {len(sorted_result)} entrées écrites dans {args.output}")


if __name__ == "__main__":
    main()
