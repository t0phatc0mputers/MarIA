# -*- coding: utf-8 -*-
"""
carte_localisation.py
------------------------
Génère une carte de France interactive (Leaflet, via folium) cliquable pour
choisir un point GPS - utilisée par la pop-up "Choisir une localisation"
(voir dialogue_localisation.py) afin de retrouver la station Météociel la
plus proche d'un simple clic, sans avoir à en connaître le nom exact.

Le clic sur la carte est transmis du JavaScript (Leaflet) vers Python via
QWebChannel (pont Qt <-> page web injecté dans le HTML généré) : voir la
classe Pont dans dialogue_localisation.py, qui reçoit les coordonnées et les
retransmet en signal Qt.

Nécessite le paquet 'folium' (pip install folium) ; l'affichage dans
l'application nécessite en plus PyQtWebEngine (pip install PyQtWebEngine) -
géré séparément par dialogue_localisation.py, qui propose une saisie de
coordonnées GPS classique en repli si ces paquets sont absents.
"""

import os
import re

try:
    import folium
    FOLIUM_DISPONIBLE = True
    FOLIUM_IMPORT_ERROR = None
except ImportError as exc:  # pragma: no cover
    FOLIUM_DISPONIBLE = False
    FOLIUM_IMPORT_ERROR = exc

_ICI = os.path.dirname(os.path.abspath(__file__))

# Fond de carte optionnel : contours réels des régions (générés pour
# l'onglet "Carte régionale" - voir carte_france.py). S'il est présent, on
# l'affiche en simple contour (sans remplissage) pour donner des repères
# géographiques ; sinon la carte reste un fond de plan classique, sans que
# cela empêche la sélection d'un point.
CHEMIN_CONTOURS_REGIONS = os.path.join(_ICI, "regions_france.geojson")

# Script injecté juste avant </html> (après les scripts d'initialisation
# propres à folium, que la bibliothèque place elle-même après </body> - il
# faut donc passer après eux pour que la variable JS de la carte existe déjà)
# : relie la carte Leaflet générée par folium (variable JS "{nom_carte}",
# retrouvée par expression régulière après l'enregistrement du HTML) au
# pont Qt/Python via QWebChannel, et pose un marqueur au point cliqué.
_SCRIPT_PONT = """
<script src="qrc:///qtwebchannel/qwebchannel.js"></script>
<script>
window.__pont = null;
new QWebChannel(qt.webChannelTransport, function(channel) {{
    window.__pont = channel.objects.pont;
}});
var __carteFerme = {nom_carte};
var __marqueurChoisi = null;
__carteFerme.on('click', function(e) {{
    var lat = e.latlng.lat, lon = e.latlng.lng;
    if (__marqueurChoisi) {{ __carteFerme.removeLayer(__marqueurChoisi); }}
    __marqueurChoisi = L.marker([lat, lon]).addTo(__carteFerme);
    if (window.__pont) {{ window.__pont.point_choisi(lat, lon); }}
}});
</script>
"""


def construire_carte_html(chemin_sortie, lat=46.6, lon=2.5, zoom=6):
    """Construit la carte de France cliquable et l'enregistre en HTML à
    l'emplacement ``chemin_sortie``. Renvoie ``chemin_sortie``.

    Lève RuntimeError si 'folium' n'est pas installé, ou si la variable
    JavaScript de la carte n'a pas pu être repérée dans le HTML généré
    (ce qui indiquerait un changement de format interne de folium)."""
    if not FOLIUM_DISPONIBLE:
        raise RuntimeError(
            "Le paquet 'folium' n'est pas installé.\nInstallez-le avec : pip install folium\n"
            f"(Erreur d'import d'origine : {FOLIUM_IMPORT_ERROR})"
        )

    carte = folium.Map(location=[lat, lon], zoom_start=zoom, tiles="CartoDB positron")

    if os.path.exists(CHEMIN_CONTOURS_REGIONS):
        folium.GeoJson(
            CHEMIN_CONTOURS_REGIONS,
            name="Régions",
            style_function=lambda _f: {"fillOpacity": 0, "color": "#3a3a3a", "weight": 1.2},
            tooltip=folium.GeoJsonTooltip(fields=["nom"], aliases=["Région :"]),
        ).add_to(carte)

    carte.save(chemin_sortie)

    with open(chemin_sortie, encoding="utf-8") as f:
        html = f.read()

    m = re.search(r"var\s+(map_[0-9a-f]+)\s*=\s*L\.map", html)
    if not m:
        raise RuntimeError(
            "Impossible de repérer la variable JavaScript de la carte Folium "
            "dans le HTML généré (version de folium incompatible ?)."
        )
    nom_carte = m.group(1)

    html = html.replace("</html>", _SCRIPT_PONT.format(nom_carte=nom_carte) + "</html>")

    with open(chemin_sortie, "w", encoding="utf-8") as f:
        f.write(html)

    return chemin_sortie
