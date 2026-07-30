# MarIA
Projet d'aide à la décision pour le maraîchage destiné aux apprentis et au delà ! //

Il y a des modifications à réaliser dans le code même de l'API : //
- Dans forecasts.py éliminer l'usage du backslash dans un des f-strings près du commentaire (# If the city hasn't been found).
- Dans cities.py remplacer (station_type = "inactive" if (code1, code2) == (1, 1) else known_station_types[code1]) par
            (station_type = "inactive" if (code1, code2) == (0, 0) else known_station_types[code1-1])
