from PyInstaller.utils.hooks import collect_data_files

datas = [
    ("cities_database.json", "."),
    ("cities_database_old.json", "."),
    ("codes_postaux_insee.json", "."),
    ("prevision_id.json", "."),
    ("regions_france.geojson", "."),
    ("stations_gps.json", "."),
    ("planning_cultural.csv", "."),
    ("planning_cultural_genere.csv", "."),
    ("planning_cultural_genere.xlsx", "."),

    ("ressources_carte", "ressources_carte"),
    ("ressources_sol", "ressources_sol"),
]

a = Analysis(
    ["gestion_planning_agricole.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "PyQt5.QtWebEngineWidgets",
        "matplotlib",
        "matplotlib.backends.backend_qt5agg",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="GestionPlanningAgricole",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
)
