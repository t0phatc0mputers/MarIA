import requests
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
import re
import threading

INPUT_FILE = "meteociel_previsions_urls.txt"
OUTPUT_FILE = "meteociel_previsions_urls_codes_postaux.txt"
ERROR_FILE = "meteociel_previsions_errors.txt"

MAX_WORKERS = 10

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/139.0 Safari/537.36"
    )
}

# Une Session par thread
thread_local = threading.local()


def get_session():
    if not hasattr(thread_local, "session"):
        thread_local.session = requests.Session()
        thread_local.session.headers.update(HEADERS)

    return thread_local.session


def extract_postal_code(soup):
    """
    Recherche un code postal dans la page.
    """

    text = soup.get_text(" ", strip=True)

    matches = re.findall(
        r"\b(?:0[1-9]|[1-8][0-9]|9[0-5]|97|98)[0-9]{3}\b",
        text
    )

    matches = list(dict.fromkeys(matches))

    if not matches:
        return None

    return matches[0]


def scrape_url(url):
    """
    Scrape une page Météociel.
    Retourne (url, code_postal, erreur).
    """

    try:

        session = get_session()

        response = session.get(
            url,
            timeout=30
        )

        response.raise_for_status()

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        postal_code = extract_postal_code(soup)

        if postal_code is None:
            return (
                url,
                None,
                "CODE_POSTAL_INTROUVABLE"
            )

        return (
            url,
            postal_code,
            None
        )

    except Exception as e:

        return (
            url,
            None,
            str(e)
        )


# ---------------------------------------------------------
# Lecture des URLs
# ---------------------------------------------------------

with open(
    INPUT_FILE,
    "r",
    encoding="utf-8"
) as f:

    urls = [
        line.strip()
        for line in f
        if line.strip()
    ]


print(f"{len(urls)} URLs à scraper.")
print(f"{MAX_WORKERS} threads utilisés.\n")


results = []
errors = []


# ---------------------------------------------------------
# Multithreading
# ---------------------------------------------------------

with ThreadPoolExecutor(
    max_workers=MAX_WORKERS
) as executor:

    futures = {
        executor.submit(scrape_url, url): url
        for url in urls
    }

    for i, future in enumerate(
        as_completed(futures),
        1
    ):

        url, postal_code, error = future.result()

        if error is None:

            result = f"{url};{postal_code}"

            results.append(result)

            print(
                f"[{i}/{len(urls)}] "
                f"{postal_code} ← {url}"
            )

        else:

            errors.append(
                f"{url};{error}"
            )

            print(
                f"[{i}/{len(urls)}] "
                f"ERREUR ← {url}"
            )


# ---------------------------------------------------------
# Sauvegarde
# ---------------------------------------------------------

# Tri pour conserver un fichier déterministe
results.sort()

with open(
    OUTPUT_FILE,
    "w",
    encoding="utf-8"
) as f:

    for line in results:
        f.write(line + "\n")


errors.sort()

with open(
    ERROR_FILE,
    "w",
    encoding="utf-8"
) as f:

    for line in errors:
        f.write(line + "\n")


# ---------------------------------------------------------
# Résumé
# ---------------------------------------------------------

print()
print("=" * 60)
print(f"URLs totales       : {len(urls)}")
print(f"Succès             : {len(results)}")
print(f"Erreurs            : {len(errors)}")
print(f"Threads            : {MAX_WORKERS}")
print()
print(f"Résultat : {OUTPUT_FILE}")
print(f"Erreurs  : {ERROR_FILE}")
