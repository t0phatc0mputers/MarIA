import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re
import time
from pathlib import Path

INPUT_FILE = "departement_tous_urls.txt"
OUTPUT_FILE = "meteociel_previsions_urls.txt"
ERROR_FILE = "departement_tous_errors.txt"

BASE_URL = "https://www.meteociel.fr"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/139.0 Safari/537.36"
    )
}

# Exactement :
# /previsions/<ID>/<slug>.htm
CITY_PATTERN = re.compile(
    r"^/previsions/[0-9]+/[^/]+\.htm$"
)

session = requests.Session()
session.headers.update(HEADERS)


def scrape_department(url):
    """Scrape une seule page departement_tous."""

    print(f"  GET {url}")

    response = session.get(
        url,
        timeout=30
    )

    response.raise_for_status()

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    city_urls = set()

    for a in soup.find_all("a", href=True):

        href = a["href"].strip()

        # URL relative
        if CITY_PATTERN.fullmatch(href):

            city_urls.add(
                urljoin(url, href)
            )

        # URL absolue
        elif re.fullmatch(
            r"https://www\.meteociel\.fr/previsions/"
            r"[0-9]+/[^/]+\.htm",
            href
        ):
            city_urls.add(href)

    return city_urls


# ---------------------------------------------------------
# Lecture des URLs departement_tous
# ---------------------------------------------------------

with open(
    INPUT_FILE,
    "r",
    encoding="utf-8"
) as f:

    department_urls = [
        line.strip()
        for line in f
        if line.strip()
    ]


# Supprimer les doublons tout en conservant l'ordre
department_urls = list(
    dict.fromkeys(department_urls)
)

print(
    f"{len(department_urls)} pages à scraper."
)

# ---------------------------------------------------------
# Scraping
# ---------------------------------------------------------

all_city_urls = set()
errors = []

for index, department_url in enumerate(
    department_urls,
    start=1
):

    print(
        f"\n[{index}/{len(department_urls)}]"
    )

    try:

        city_urls = scrape_department(
            department_url
        )

        print(
            f"  → {len(city_urls)} URLs trouvées"
        )

        all_city_urls.update(
            city_urls
        )

    except Exception as error:

        print(
            f"  ERREUR : {error}"
        )

        errors.append(
            f"{department_url}\t{error}"
        )

    # Pause entre deux pages
    time.sleep(1)


# ---------------------------------------------------------
# Sauvegarde des résultats
# ---------------------------------------------------------

with open(
    OUTPUT_FILE,
    "w",
    encoding="utf-8"
) as f:

    for url in sorted(all_city_urls):
        f.write(url + "\n")


# ---------------------------------------------------------
# Sauvegarde des erreurs
# ---------------------------------------------------------

with open(
    ERROR_FILE,
    "w",
    encoding="utf-8"
) as f:

    for error in errors:
        f.write(error + "\n")


# ---------------------------------------------------------
# Résumé
# ---------------------------------------------------------

print("\n" + "=" * 60)

print(
    f"Départements traités : "
    f"{len(department_urls) - len(errors)}/{len(department_urls)}"
)

print(
    f"URLs de communes : {len(all_city_urls)}"
)

print(
    f"Erreurs : {len(errors)}"
)

print(
    f"Résultat : {OUTPUT_FILE}"
)

if errors:
    print(
        f"Erreurs : {ERROR_FILE}"
    )
