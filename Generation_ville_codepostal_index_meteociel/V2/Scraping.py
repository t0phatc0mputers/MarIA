import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re
import time

BASE = "https://www.meteociel.fr"

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0"
})


def get_soup(url):
    r = session.get(url, timeout=30)
    r.raise_for_status()
    return BeautifulSoup(r.text, "html.parser")


# -------------------------------------------------
# 1. Récupérer les pages départementales
# -------------------------------------------------

url = f"{BASE}/previsions/departements.htm"

soup = get_soup(url)

departement_urls = set()

for a in soup.find_all("a", href=True):

    href = a["href"]

    if re.match(
        r"^/previsions/departement/[^/]+\.htm$",
        href
    ):
        departement_urls.add(
            urljoin(BASE, href)
        )


print(
    "Départements :",
    len(departement_urls)
)


# -------------------------------------------------
# 2. Pour chaque département, trouver le lien
#    departement_tous
# -------------------------------------------------

departement_tous_urls = set()

for i, department_url in enumerate(
    sorted(departement_urls),
    1
):

    print(
        f"[{i}/{len(departement_urls)}] "
        f"{department_url}"
    )

    soup = get_soup(department_url)

    for a in soup.find_all("a", href=True):

        href = a["href"]

        if "/previsions/departement_tous/" in href:

            departement_tous_urls.add(
                urljoin(department_url, href)
            )

    time.sleep(0.5)


# -------------------------------------------------
# 3. Sauvegarder les URLs
# -------------------------------------------------

with open(
    "departement_tous_urls.txt",
    "w",
    encoding="utf-8"
) as f:

    for url in sorted(departement_tous_urls):
        f.write(url + "\n")


print(
    "departement_tous trouvées :",
    len(departement_tous_urls)
)
