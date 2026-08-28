# -*- coding: utf-8 -*-
"""
fiches_botaniques.py
---------------------
Base de données agronomiques pour l'onglet "Fiches de référence" du
planning cultural maraîcher bio.

Chaque entrée du dictionnaire FICHES est indexée par le nom EXACT de
"culture" tel qu'il apparaît dans planning_cultural.csv, et fournit les
informations nécessaires à une conduite de culture correcte :
temps de croissance, exigences de sol, hygrométrie, exposition,
espacements, fertilisation, rotation, maladies/ravageurs courants et
conseils pratiques.

Les valeurs sont des repères usuels de maraîchage biologique en climat
tempéré (type Île-de-France) ; à ajuster selon le terroir et le
microclimat réels de l'exploitation.
"""

# ------------------------------------------------------------------
# Blocs de texte partagés par famille botanique (pour éviter les
# répétitions tout en gardant une information fiable par famille)
# ------------------------------------------------------------------

MAL_ALLIUM = ("Mildiou (Peronospora), mouche mineuse de l'oignon, thrips, "
              "rouille ; éviter d'arroser le feuillage et bien aérer les rangs.")
MAL_BRASSICA = ("Hernie du chou, altises, piéride et noctuelle (chenilles), "
                "pucerons cendrés, mouche du chou ; voile anti-insectes fortement conseillé.")
MAL_CUCURBIT = ("Oïdium, mildiou, pucerons, altises sur jeunes plants, mouche blanche sous abri ; "
                "arroser au pied plutôt qu'au feuillage.")
MAL_SOLANACEE = ("Mildiou, oïdium, pucerons, aleurodes, doryphore (pomme de terre/aubergine) ; "
                 "rotation stricte de 3-4 ans indispensable.")
MAL_RACINE = ("Mouche de la carotte/du navet, nématodes, altises, rouille blanche ; "
              "sol finement ameubli pour éviter le fourchage des racines.")
MAL_LEGUMINEUSE = ("Puceron noir, bruche, anthracnose, botrytis en conditions humides ; "
                    "éviter l'excès d'azote qui favorise le feuillage au détriment des gousses.")
MAL_CHICO_SALADE = ("Limaces et escargots, pucerons, mildiou (bremia), pourriture grise (botrytis) ; "
                     "bon drainage et aération indispensables.")
MAL_AROMATIQUE = "Peu de maladies graves ; surveiller pucerons et fonte des semis en sol trop humide."

FERT_STD = ("Compost mûr ou fumier bien décomposé avant plantation (2-3 kg/m²), "
            "complément d'engrais organique azoté en cours de culture si besoin.")
FERT_LEGUMINEUSE = ("Peu ou pas d'azote (les légumineuses le fixent elles-mêmes) ; "
                     "compost mûr en fond de planche, apport possible de potasse et phosphore.")
FERT_RACINE = ("Éviter tout apport de matière organique fraîche (fourchage des racines) ; "
               "compost bien décomposé apporté à l'automne précédent, potasse modérée.")
FERT_GOURMAND = ("Culture gourmande : fumier ou compost riche à la plantation (3-4 kg/m²) "
                  "puis apports réguliers d'engrais organique azoté et potassique en cours de culture.")

ROT_3 = "Retour sur la même parcelle après 3 ans minimum."
ROT_4 = "Retour sur la même parcelle après 4 ans minimum, jamais après une culture de la même famille."


def _f(nom_latin, famille, cycle, tgerm, tcroiss, gel, expo, sol, ph, eau, hygro,
       espacement, profondeur, fertilisation, rotation, maladies, conseil, variante=""):
    """Fabrique une fiche technique complète (dictionnaire)."""
    return {
        "nom_latin": nom_latin,
        "famille": famille,
        "cycle": cycle,
        "temp_germination": tgerm,
        "temp_croissance": tcroiss,
        "gel": gel,
        "exposition": expo,
        "sol": sol,
        "ph": ph,
        "eau": eau,
        "hygrometrie": hygro,
        "espacement": espacement,
        "profondeur_semis": profondeur,
        "fertilisation": fertilisation,
        "rotation": rotation,
        "maladies": maladies,
        "conseil": conseil,
        "variante": variante,
    }


# ------------------------------------------------------------------
# FICHES : une entrée par "culture" du CSV (64 entrées)
# ------------------------------------------------------------------
FICHES = {}

# --- Ail (Allium sativum) — Amaryllidacées ---------------------------------
_ail_commun = dict(
    nom_latin="Allium sativum", famille="Amaryllidacées (ex-Alliacées)",
    tgerm="5-15 °C (vernalisation au froid nécessaire pour l'ail d'automne)",
    tcroiss="12-24 °C", gel="Résistant au gel une fois installé (jusqu'à -10 °C)",
    expo="Plein soleil", sol="Léger, drainant, meuble, sans excès de matière organique fraîche",
    ph="6,5-7,5", eau="Faible à modéré ; arrêt des arrosages 3-4 semaines avant récolte",
    hygro="Air sec de préférence en fin de cycle (favorise la conservation)",
    espacement="25 cm entre rangs", profondeur="3-5 cm, pointe vers le haut",
    fertilisation="Compost mûr à l'automne précédent, éviter le fumier frais (favorise les maladies)",
    rotation=ROT_4, maladies=MAL_ALLIUM + " Sensible en particulier à la rouille et au nématode de la tige.",
)
FICHES["Ail d'automne sec"] = _f(
    **_ail_commun, cycle="Plantation en octobre-novembre, récolte en juin-juillet (~8-9 mois)",
    conseil="Variété de garde : bulbes ressuyés puis conservés au sec, à l'abri de la lumière.",
    variante="Conduite d'automne, récolté sec pour la conservation longue durée.")
FICHES["Ail d'automne vert"] = _f(
    **_ail_commun, cycle="Plantation en octobre-novembre, récolte en avril-mai en vert (~6 mois)",
    conseil="Récolté avant maturité complète, se consomme frais rapidement, ne se conserve pas.",
    variante="Conduite d'automne, récolté en vert (bulbe non formé), pas de conservation.")
FICHES["Ail de printemps sec"] = _f(
    **_ail_commun, cycle="Plantation en février-mars, récolte en août (~5-6 mois)",
    conseil="Utile pour étaler la récolte ; nécessite un sol ressuyé dès la sortie d'hiver.",
    variante="Conduite de printemps, récolté sec pour la conservation.")
FICHES["Ail de printemps vert"] = _f(
    **_ail_commun, cycle="Plantation en février-mars, récolte en juin en vert (~4 mois)",
    conseil="Cycle court, idéal pour combler un vide de planning avant les cultures d'été.",
    variante="Conduite de printemps, récolté en vert.")

# --- Solanacées fruit -------------------------------------------------------
FICHES["Aubergine"] = _f(
    nom_latin="Solanum melongena", famille="Solanacées",
    cycle="Semis 8-10 semaines avant plantation, récolte 90-120 jours après semis",
    tgerm="20-28 °C (germination lente et irrégulière en dessous de 20 °C)",
    tcroiss="20-28 °C, arrêt de croissance en dessous de 15 °C", gel="Très sensible, aucune tolérance",
    expo="Plein soleil, culture sous abri conseillée sous climat tempéré",
    sol="Riche, profond, bien drainé, réchauffé", ph="6,0-6,8",
    eau="Élevé et régulier, sensible au stress hydrique (chute des fleurs)",
    hygro="60-70 % sous abri ; éviter l'air stagnant trop humide (favorise botrytis)",
    espacement="60-70 cm entre rangs, 50 cm sur le rang", profondeur="0,5-1 cm (semis en godet)",
    fertilisation=FERT_GOURMAND, rotation=ROT_4, maladies=MAL_SOLANACEE + " Araignées rouges sous abri.",
    conseil="Tuteurer et éventuellement tailler à 1-2 tiges pour favoriser la mise à fruit.")

FICHES["Tomate"] = _f(
    nom_latin="Solanum lycopersicum", famille="Solanacées",
    cycle="Semis 6-8 semaines avant plantation, récolte à partir de 60-90 jours après plantation",
    tgerm="20-25 °C", tcroiss="18-26 °C, nouaison compromise au-delà de 32 °C ou en dessous de 12 °C",
    gel="Très sensible, aucune tolérance", expo="Plein soleil, abri conseillé (limite le mildiou)",
    sol="Riche, profond, drainé, réchauffé", ph="6,0-6,8",
    eau="Régulier et modéré, arrosage au pied, éviter les à-coups (fentes des fruits, cul noir)",
    hygro="60-70 % sous abri ; bien aérer pour limiter le mildiou et l'oïdium",
    espacement="70-90 cm entre rangs, 40-50 cm sur le rang (variétés à tuteurer)",
    profondeur="0,5-1 cm (semis en godet)", fertilisation=FERT_GOURMAND, rotation=ROT_4,
    maladies=MAL_SOLANACEE + " Mildiou (Phytophthora infestans) en tête de liste en climat humide.",
    conseil="Effeuillage et taille des gourmands pour les variétés indéterminées ; pailler pour réguler l'humidité du sol.")
FICHES["Tomate déterminée"] = _f(
    nom_latin="Solanum lycopersicum (type déterminé)", famille="Solanacées",
    cycle="Semis 6-8 semaines avant plantation, récolte groupée 60-80 jours après plantation",
    tgerm="20-25 °C", tcroiss="18-26 °C", gel="Très sensible, aucune tolérance",
    expo="Plein soleil, plein champ possible", sol="Riche, profond, drainé, réchauffé", ph="6,0-6,8",
    eau="Régulier et modéré, arrosage au pied",
    hygro="Aération importante pour limiter le mildiou en plein champ",
    espacement="60-80 cm entre rangs, 40-50 cm sur le rang", profondeur="0,5-1 cm (semis en godet)",
    fertilisation=FERT_GOURMAND, rotation=ROT_4, maladies=MAL_SOLANACEE,
    conseil="Port buissonnant, ne nécessite pas de taille des gourmands ni de tuteurage systématique ; "
            "récolte plus concentrée dans le temps, adaptée à la transformation/conserve.",
    variante="Croissance limitée (non indéterminée), pratique en plein champ sans tuteurage lourd.")

FICHES["Poivron"] = _f(
    nom_latin="Capsicum annuum", famille="Solanacées",
    cycle="Semis 8-10 semaines avant plantation, récolte 90-120 jours après semis",
    tgerm="22-28 °C", tcroiss="20-28 °C, arrêt en dessous de 15 °C", gel="Très sensible, aucune tolérance",
    expo="Plein soleil, sous abri conseillé sous climat tempéré", sol="Riche, profond, drainé, réchauffé",
    ph="6,0-6,8", eau="Régulier, sensible au stress hydrique",
    hygro="60-70 % sous abri", espacement="60 cm entre rangs, 40-50 cm sur le rang",
    profondeur="0,5-1 cm (semis en godet)", fertilisation=FERT_GOURMAND, rotation=ROT_4,
    maladies=MAL_SOLANACEE + " Pucerons et thrips fréquents sous abri.",
    conseil="Tuteurer les variétés hautes ; un léger stress hydrique en fin de cycle accentue la coloration.")

# --- Cucurbitacées -----------------------------------------------------------
FICHES["Concombre"] = _f(
    nom_latin="Cucumis sativus", famille="Cucurbitacées",
    cycle="Semis, récolte à partir de 50-65 jours après semis",
    tgerm="22-28 °C", tcroiss="20-28 °C", gel="Très sensible, aucune tolérance",
    expo="Plein soleil, sous abri pour production précoce", sol="Riche, humifère, drainé, réchauffé",
    ph="6,0-6,8", eau="Élevé et régulier (95 % d'eau dans le fruit)",
    hygro="70-80 % sous abri, bonne aération pour limiter l'oïdium",
    espacement="1 m entre rangs, 40-50 cm sur le rang (ou palissage vertical)",
    profondeur="2 cm", fertilisation=FERT_GOURMAND, rotation=ROT_3, maladies=MAL_CUCURBIT,
    conseil="Palisser sur ficelle pour gagner en aération et faciliter la récolte.")

FICHES["Courgette"] = _f(
    nom_latin="Cucurbita pepo", famille="Cucurbitacées",
    cycle="Récolte à partir de 50-60 jours après semis, production étalée 2-3 mois",
    tgerm="20-30 °C (germination rapide)", tcroiss="18-28 °C", gel="Très sensible, aucune tolérance",
    expo="Plein soleil", sol="Riche, profond, bien drainé", ph="6,0-6,8",
    eau="Élevé et régulier, surtout en période de production",
    hygro="Modérée, bonne aération pour limiter l'oïdium (très sensible)",
    espacement="1-1,2 m entre plants en tous sens", profondeur="2-3 cm",
    fertilisation=FERT_GOURMAND, rotation=ROT_3, maladies=MAL_CUCURBIT + " Très sensible à l'oïdium en fin d'été.",
    conseil="Récolter régulièrement (tous les 2 jours) pour prolonger la production.")

for _nom, _cycle in [
    ("Courge 90-100 jours", "Type précoce (butternut petit calibre, pâtisson…) : 90-100 jours semis-récolte"),
    ("Courge 100-110 jours", "Type mi-saison (butternut, potimarron…) : 100-110 jours semis-récolte"),
    ("Courge 120-140 jours", "Type tardif de garde (potiron, musquée de Provence…) : 120-140 jours semis-récolte"),
]:
    FICHES[_nom] = _f(
        nom_latin="Cucurbita spp.", famille="Cucurbitacées", cycle=_cycle,
        tgerm="22-28 °C", tcroiss="18-28 °C", gel="Très sensible, récolter avant les premières gelées",
        expo="Plein soleil", sol="Riche, profond, bien drainé, forte demande en matière organique",
        ph="6,0-6,8", eau="Élevé en début de cycle, réduit en fin de cycle pour favoriser la conservation",
        hygro="Modérée ; bonne aération du feuillage", espacement="1,5-2 m entre plants (variétés coureuses)",
        profondeur="2-3 cm", fertilisation=FERT_GOURMAND, rotation=ROT_3, maladies=MAL_CUCURBIT,
        conseil="Laisser durcir et suberiser le pédoncule avant récolte pour les types de longue conservation ; "
                "ressuyer 1-2 semaines au soleil avant stockage.",
        variante="Regroupement par durée de cycle plutôt que par variété nommée.")

FICHES["Melon"] = _f(
    nom_latin="Cucumis melo", famille="Cucurbitacées",
    cycle="90-110 jours semis-récolte selon variété et climat",
    tgerm="25-30 °C", tcroiss="22-28 °C, très exigeant en chaleur", gel="Très sensible, aucune tolérance",
    expo="Plein soleil, sous abri ou paillage plastique conseillés sous climat tempéré",
    sol="Léger, drainant, réchauffé, riche en matière organique", ph="6,5-7,5",
    eau="Modéré à élevé en croissance, réduit fortement 1-2 semaines avant récolte (taux de sucre)",
    hygro="Air plutôt sec en fin de cycle pour limiter l'oïdium et favoriser le sucre",
    espacement="1,2-1,5 m entre plants", profondeur="2 cm", fertilisation=FERT_GOURMAND, rotation=ROT_4,
    maladies=MAL_CUCURBIT + " Fusariose du melon en sol contaminé.",
    conseil="Pincer au-dessus de la 2e-3e feuille pour favoriser les ramifications fructifères.")

FICHES["Pastèque"] = _f(
    nom_latin="Citrullus lanatus", famille="Cucurbitacées",
    cycle="90-120 jours semis-récolte, très exigeant en chaleur cumulée",
    tgerm="25-30 °C", tcroiss="22-30 °C", gel="Très sensible, aucune tolérance",
    expo="Plein soleil impératif, paillage plastique noir recommandé sous climat tempéré",
    sol="Léger, sableux à limoneux, très bien drainé, réchauffé", ph="6,0-7,0",
    eau="Élevé en croissance végétative, réduit en maturation des fruits",
    hygro="Air sec de préférence, très sensible à l'oïdium en atmosphère humide",
    espacement="1,5-2 m entre plants", profondeur="2-3 cm", fertilisation=FERT_GOURMAND, rotation=ROT_4,
    maladies=MAL_CUCURBIT, conseil="Choisir des variétés adaptées aux climats frais (cycle court) hors régions méridionales.")

# --- Racines --------------------------------------------------------------
for _nom, _cycle, _conseil in [
    ("Carotte botte", "70-90 jours, récolte jeune en botte", "Récolter jeune pour la fraîcheur et la tendreté ; éclaircir tôt."),
    ("Carotte de conservation", "110-130 jours, récolte à maturité complète", "Buttage léger contre le verdissement des collets ; conserver en silo ou en cave humide."),
]:
    FICHES[_nom] = _f(
        nom_latin="Daucus carota", famille="Apiacées (Ombellifères)", cycle=_cycle,
        tgerm="8-25 °C (optimal 20 °C)", tcroiss="16-21 °C", gel="Assez résistant en végétation, sensible en gelées fortes",
        expo="Plein soleil à mi-ombre", sol="Profond, meuble, sans cailloux, sans fumure fraîche",
        ph="6,0-6,8", eau="Régulier et modéré, surtout à la levée", hygro="Modérée, sol frais mais non détrempé",
        espacement="20-25 cm entre rangs, éclaircir à 3-5 cm sur le rang", profondeur="1 cm",
        fertilisation=FERT_RACINE, rotation=ROT_3, maladies=MAL_RACINE, conseil=_conseil)

for _nom, _cycle, _conseil in [
    ("Navet botte", "45-60 jours, récolte jeune", "Croissance rapide ; récolter tôt pour éviter le boisage de la chair."),
    ("Navet conservation", "70-90 jours, récolte à maturité", "Peut se conserver en silo/cave après arrachage à l'automne."),
]:
    FICHES[_nom] = _f(
        nom_latin="Brassica rapa var. rapa", famille="Brassicacées", cycle=_cycle,
        tgerm="8-30 °C (optimal 20 °C)", tcroiss="15-20 °C", gel="Résiste à de légères gelées",
        expo="Plein soleil à mi-ombre", sol="Léger, frais, riche en humus", ph="6,0-7,0",
        eau="Régulier, un manque d'eau accentue le goût piquant/boisé",
        hygro="Modérée, sol constamment frais", espacement="25-30 cm entre rangs, 10 cm sur le rang",
        profondeur="1 cm", fertilisation=FERT_RACINE, rotation=ROT_4, maladies=MAL_BRASSICA, conseil=_conseil)

for _nom, _conseil in [("Radis botte", "Semis échelonnés tous les 10-15 jours pour une production continue."),
                        ("Radis rave", "Variétés à racine plus grosse, cycle légèrement plus long, récolte différée.")]:
    FICHES[_nom] = _f(
        nom_latin="Raphanus sativus", famille="Brassicacées",
        cycle="20-30 jours pour les radis botte, 30-45 jours pour les radis rave",
        tgerm="8-30 °C (optimal 18-22 °C, germination très rapide)", tcroiss="10-18 °C",
        gel="Sensible aux fortes gelées, tolère les gelées légères",
        expo="Plein soleil à mi-ombre l'été (montaison rapide en cas de forte chaleur/sécheresse)",
        sol="Léger, meuble, frais, sans cailloux", ph="6,0-7,0",
        eau="Régulier et constant, un manque d'eau provoque piquant et fentes",
        hygro="Sol frais en permanence", espacement="15-20 cm entre rangs, 3-5 cm sur le rang",
        profondeur="1 cm", fertilisation=FERT_RACINE, rotation=ROT_4, maladies=MAL_RACINE + " Altises particulièrement voraces sur les jeunes plants.",
        conseil=_conseil)

FICHES["Panais"] = _f(
    nom_latin="Pastinaca sativa", famille="Apiacées (Ombellifères)",
    cycle="120-150 jours, culture longue", tgerm="10-20 °C (levée lente et irrégulière, 2-3 semaines)",
    tcroiss="15-20 °C", gel="Très résistant, la gelée améliore la saveur (sucre)",
    expo="Plein soleil à mi-ombre", sol="Profond, meuble, sans cailloux ni fumure fraîche", ph="6,0-7,0",
    eau="Régulier et modéré", hygro="Modérée, sol frais", espacement="30 cm entre rangs, 10-15 cm sur le rang",
    profondeur="1-1,5 cm", fertilisation=FERT_RACINE, rotation=ROT_3, maladies=MAL_RACINE,
    conseil="Peut rester en terre tout l'hiver et être récolté au fur et à mesure des besoins.")

FICHES["Rutabaga"] = _f(
    nom_latin="Brassica napus var. napobrassica", famille="Brassicacées",
    cycle="90-120 jours", tgerm="8-25 °C", tcroiss="13-18 °C", gel="Très résistant, culture d'hiver classique",
    expo="Plein soleil à mi-ombre", sol="Profond, frais, riche en humus", ph="6,0-7,0",
    eau="Régulier", hygro="Modérée, sol frais", espacement="40 cm entre rangs, 25-30 cm sur le rang",
    profondeur="1-1,5 cm", fertilisation=FERT_RACINE, rotation=ROT_4, maladies=MAL_BRASSICA,
    conseil="Se conserve très bien en cave ou en silo tout l'hiver.")

for _nom, _cycle, _conseil in [
    ("Betterave botte", "60-70 jours, récolte jeune en botte", "Récolter jeune (taille d'une balle de golf à tennis) pour la tendreté."),
    ("Betterave de conservation", "90-120 jours, récolte à maturité", "Arracher avant les fortes gelées, conserver en silo avec le collet non coupé ras."),
]:
    FICHES[_nom] = _f(
        nom_latin="Beta vulgaris", famille="Amaranthacées (ex-Chénopodiacées)", cycle=_cycle,
        tgerm="8-30 °C (optimal 20-25 °C)", tcroiss="16-22 °C", gel="Sensible aux fortes gelées",
        expo="Plein soleil", sol="Profond, meuble, riche en humus, tolère bien les sols moyens",
        ph="6,5-7,5 (sensible à l'acidité)", eau="Régulier, un stress hydrique durcit la racine",
        hygro="Modérée, sol frais", espacement="30 cm entre rangs, éclaircir à 10 cm sur le rang",
        profondeur="1,5-2 cm (semences agglomérées = plusieurs graines par glomérule)",
        fertilisation=FERT_STD, rotation=ROT_3, maladies=MAL_RACINE + " Cercosporiose sur le feuillage en été humide.",
        conseil=_conseil)

# --- Alliacées bulbes --------------------------------------------------------
for _nom, _cycle, _conseil, _variante in [
    ("Oignon botte", "60-90 jours, récolte jeune en botte, non bulbé à maturité", "Semis dense, récolte précoce avant formation complète du bulbe.", "Récolte en frais, pas de conservation longue."),
    ("Oignon botte - bulbille", "60-80 jours à partir de bulbilles (plus rapide que le semis)", "Plantation de bulbilles au lieu du semis : levée plus fiable, cycle raccourci.", "Multiplication par bulbilles, récolte en frais."),
    ("Oignon conservation", "150-180 jours depuis semis, récolte à bulbe formé et fanes couchées", "Ne récolter qu'après le couchage naturel des fanes ; bien ressuyer avant stockage.", "Variétés de garde, séchage indispensable avant conservation."),
    ("Oignon conservation - bulbille", "100-120 jours depuis la plantation de bulbilles", "Plantation de bulbilles : culture plus simple et plus précoce que le semis, bonne aptitude à la garde.", "Multiplication par bulbilles, variétés de conservation."),
]:
    FICHES[_nom] = _f(
        nom_latin="Allium cepa", famille="Amaryllidacées (ex-Alliacées)", cycle=_cycle,
        tgerm="10-25 °C", tcroiss="13-24 °C", gel="Assez résistant en végétation (variétés d'automne)",
        expo="Plein soleil", sol="Léger, drainant, riche en humus", ph="6,5-7,5",
        eau="Modéré et régulier, arrêt des arrosages avant récolte (variétés de conservation)",
        hygro="Air sec en fin de cycle pour favoriser le séchage et la conservation",
        espacement="25-30 cm entre rangs, 10 cm sur le rang (semis) ou 10-15 cm (bulbilles)",
        profondeur="1 cm (semis) ou pointe affleurante (bulbilles)",
        fertilisation=FERT_STD, rotation=ROT_4, maladies=MAL_ALLIUM, conseil=_conseil, variante=_variante)

FICHES["Echalote"] = _f(
    nom_latin="Allium cepa var. aggregatum", famille="Amaryllidacées (ex-Alliacées)",
    cycle="Plantation en février-mars, récolte en juillet (~5 mois)",
    tgerm="—", tcroiss="12-24 °C", gel="Résistant en végétation, planter hors période de gel fort",
    expo="Plein soleil", sol="Léger, drainant, meuble", ph="6,5-7,5",
    eau="Faible à modéré, arrêt avant récolte", hygro="Air sec en fin de cycle",
    espacement="25-30 cm entre rangs, 15-20 cm sur le rang", profondeur="Pointe affleurante (plantation de bulbilles)",
    fertilisation=FERT_STD, rotation=ROT_4, maladies=MAL_ALLIUM,
    conseil="Chaque bulbille plantée se multiplie en une touffe de plusieurs bulbes ; récolter et faire sécher au soleil quelques jours.")

FICHES["Poireau"] = _f(
    nom_latin="Allium porrum", famille="Amaryllidacées (ex-Alliacées)",
    cycle="Semis puis repiquage, récolte 5-7 mois après semis selon variété (précoce à tardive)",
    tgerm="10-25 °C", tcroiss="13-23 °C", gel="Très résistant (variétés d'hiver, jusqu'à -15 °C)",
    expo="Plein soleil à mi-ombre", sol="Profond, riche, frais, bien ameubli", ph="6,5-7,5",
    eau="Régulier et soutenu tout au long du cycle", hygro="Sol frais en permanence, air ambiant classique",
    espacement="30-40 cm entre rangs, 10-15 cm sur le rang", profondeur="Repiquage à 5-10 cm de profondeur (butée progressive)",
    fertilisation=FERT_STD, rotation=ROT_4, maladies=MAL_ALLIUM + " Teigne du poireau et thrips en été.",
    conseil="Butter progressivement pour allonger le fût blanc ; habiller les racines et le feuillage avant repiquage.")

# --- Brassicacées feuilles/pommes -------------------------------------------
_choux_communs = dict(famille="Brassicacées", tgerm="8-30 °C (optimal 20 °C)",
                       expo="Plein soleil à mi-ombre", ph="6,5-7,5",
                       sol="Riche, profond, frais, forte demande en azote",
                       fertilisation=FERT_STD, rotation=ROT_4, maladies=MAL_BRASSICA)

FICHES["Chou brocoli"] = _f(
    nom_latin="Brassica oleracea var. italica", **_choux_communs,
    cycle="80-100 jours semis-récolte", tcroiss="15-20 °C, monte en graine si chaleur excessive",
    gel="Résiste à de légères gelées", eau="Régulier et soutenu (feuillage abondant)",
    hygro="Sol frais, atmosphère non desséchante", espacement="50 cm entre rangs, 40-50 cm sur le rang",
    profondeur="1 cm (semis en pépinière)",
    conseil="Récolter l'inflorescence terminale puis laisser les pousses secondaires se développer pour une deuxième récolte.")
FICHES["Chou-fleur"] = _f(
    nom_latin="Brassica oleracea var. botrytis", **_choux_communs,
    cycle="90-120 jours semis-récolte, culture exigeante et régulière", tcroiss="15-20 °C, très sensible aux à-coups",
    gel="Résiste à de légères gelées (variétés d'automne/hiver)", eau="Élevé et très régulier (pomme déformée en cas de stress)",
    hygro="Sol constamment frais", espacement="60 cm entre rangs, 50-60 cm sur le rang",
    profondeur="1 cm (semis en pépinière)",
    conseil="Casser une feuille sur la pomme pour la protéger du soleil et garder une pomme bien blanche.")
FICHES["Chou cabus"] = _f(
    nom_latin="Brassica oleracea var. capitata", **_choux_communs,
    cycle="90-120 jours semis-récolte selon variété", tcroiss="15-20 °C",
    gel="Résistant, variétés d'hiver très rustiques", eau="Régulier et soutenu",
    hygro="Sol frais", espacement="50-60 cm entre rangs, 40-50 cm sur le rang", profondeur="1 cm (semis en pépinière)",
    conseil="Pommes fermes, bonne aptitude à la conservation en cave pour les variétés d'hiver.")
FICHES["Chou de milan"] = _f(
    nom_latin="Brassica oleracea var. sabauda", **_choux_communs,
    cycle="90-120 jours semis-récolte", tcroiss="13-18 °C, apprécie la fraîcheur",
    gel="Très résistant, saveur améliorée par le froid", eau="Régulier",
    hygro="Sol frais", espacement="50-60 cm entre rangs, 40-50 cm sur le rang", profondeur="1 cm (semis en pépinière)",
    conseil="Chou d'automne-hiver par excellence (feuilles cloquées) ; le gel adoucit son goût.")
FICHES["Chou de Bruxelles"] = _f(
    nom_latin="Brassica oleracea var. gemmifera", **_choux_communs,
    cycle="150-180 jours, culture longue jusqu'à l'hiver", tcroiss="15-18 °C, formation des pommes favorisée par le froid",
    gel="Très résistant, la gelée sucre les pommes", eau="Régulier et soutenu",
    hygro="Sol frais", espacement="60-70 cm entre rangs, 60 cm sur le rang", profondeur="1 cm (semis en pépinière)",
    conseil="Étêter la plante fin de saison pour concentrer la formation des petites pommes le long de la tige.")
FICHES["Chou kale"] = _f(
    nom_latin="Brassica oleracea var. sabellica", **_choux_communs,
    cycle="60-80 jours pour les premières feuilles, récolte échelonnée ensuite tout l'hiver",
    tcroiss="10-20 °C, très rustique", gel="Extrêmement résistant, saveur améliorée par le gel",
    eau="Modéré à régulier", hygro="Peu exigeant", espacement="50 cm entre rangs, 40-50 cm sur le rang",
    profondeur="1 cm (semis en pépinière ou en place)",
    conseil="Récolte en cueillette continue des feuilles basses, la plante repousse tout l'hiver.")
FICHES["Chou rave"] = _f(
    nom_latin="Brassica oleracea var. gongylodes", **_choux_communs,
    cycle="55-70 jours semis-récolte (cycle court)", tcroiss="15-20 °C",
    gel="Résiste à de légères gelées", eau="Régulier, un manque d'eau fait fibrer la chair",
    hygro="Sol frais", espacement="30-40 cm entre rangs, 20-25 cm sur le rang", profondeur="1 cm",
    conseil="Récolter tant que le renflement reste tendre (taille d'une balle de tennis maximum).")
FICHES["Chou chinois pak choi"] = _f(
    nom_latin="Brassica rapa subsp. chinensis", **_choux_communs,
    cycle="40-55 jours, cycle très court", tcroiss="15-20 °C, monte vite en graine si chaleur/jours longs",
    gel="Sensible aux fortes gelées", eau="Régulier et soutenu (feuilles charnues, forte transpiration)",
    hygro="Sol constamment frais", espacement="25-30 cm entre rangs, 20 cm sur le rang", profondeur="0,5-1 cm",
    conseil="Semer plutôt en fin d'été (jours raccourcissants) pour limiter la montaison précoce.")
FICHES["Chou chinois pe tsai"] = _f(
    nom_latin="Brassica rapa subsp. pekinensis", **_choux_communs,
    cycle="60-80 jours, cycle court", tcroiss="12-20 °C, sensible à la montaison en jours longs et chaleur",
    gel="Sensible aux fortes gelées", eau="Régulier et soutenu", hygro="Sol constamment frais",
    espacement="35-40 cm entre rangs, 30-35 cm sur le rang", profondeur="0,5-1 cm",
    conseil="Semis de préférence en été pour récolte d'automne, sensible à la montaison au printemps.")

# --- Chicorées / salades ------------------------------------------------------
for _nom, _cycle, _conseil in [
    ("Chicorée chioggia", "70-90 jours, pomme rouge type radicchio", "Blanchir/couvrir légèrement pour intensifier la couleur et adoucir l'amertume."),
    ("Chicorée pain de sucre", "90-110 jours, grosse pomme allongée", "Culture d'automne classique, bonne tenue au froid et à la conservation courte en cave."),
    ("Chicorée scarole & frisée", "70-90 jours", "Lier les feuilles extérieures 2-3 semaines avant récolte pour blanchir le cœur."),
    ("Chicorée trévise", "80-100 jours, forçage possible pour les variétés tardives", "Le froid intensifie la coloration rouge caractéristique ; possibilité de forçage à l'obscurité en hiver."),
]:
    FICHES[_nom] = _f(
        nom_latin="Cichorium intybus / endivia", famille="Astéracées (Composées)", cycle=_cycle,
        tgerm="15-25 °C", tcroiss="15-20 °C", gel="Assez résistant, tolère de légères gelées",
        expo="Plein soleil à mi-ombre l'été", sol="Riche, frais, humifère, bien drainé",
        ph="6,5-7,5", eau="Régulier, sol jamais desséché (sinon amertume excessive)",
        hygro="Sol frais, bonne aération du feuillage", espacement="30-35 cm entre rangs, 30 cm sur le rang",
        profondeur="0,5-1 cm", fertilisation=FERT_STD, rotation=ROT_3, maladies=MAL_CHICO_SALADE, conseil=_conseil)

FICHES["Salade"] = _f(
    nom_latin="Lactuca sativa", famille="Astéracées (Composées)",
    cycle="45-75 jours selon type (batavia, pommée, feuille à couper) et saison",
    tgerm="4-25 °C (inhibition de germination au-delà de 25-28 °C)", tcroiss="15-20 °C",
    gel="Assez résistant selon variété (variétés d'hiver rustiques)", expo="Plein soleil, mi-ombre en été",
    sol="Riche, frais, humifère, bien drainé", ph="6,0-7,0",
    eau="Régulier et constant, racines superficielles sensibles à la sécheresse",
    hygro="Sol frais en permanence, air non stagnant (limite botrytis)",
    espacement="25-30 cm entre rangs, 25-30 cm sur le rang (pommées)", profondeur="0,5 cm",
    fertilisation=FERT_STD, rotation=ROT_3, maladies=MAL_CHICO_SALADE,
    conseil="Échelonner les semis toutes les 2-3 semaines pour une récolte continue ; semer à l'ombre en été pour éviter la thermo-inhibition.")

FICHES["Mâche"] = _f(
    nom_latin="Valerianella locusta", famille="Caprifoliacées (ex-Valérianacées)",
    cycle="45-60 jours, culture d'automne-hiver", tgerm="10-20 °C, germination difficile au-delà de 20 °C",
    tcroiss="10-15 °C", gel="Très résistante, jusqu'à -15 °C sous protection", expo="Plein soleil à mi-ombre",
    sol="Léger, frais, riche en humus", ph="6,0-7,0", eau="Modéré, sol frais mais bien drainé",
    hygro="Sol frais ; éviter l'excès d'eau stagnante (pourriture)", espacement="15-20 cm entre rangs, semis dense à la volée",
    profondeur="0,5 cm", fertilisation=FERT_STD, rotation=ROT_3,
    maladies="Oïdium et pourriture en sol trop humide ou mal drainé ; limaces.",
    conseil="Culture typique d'automne-hiver ; un voile de protection améliore la propreté des feuilles en hiver.")

# --- Épinard / Blette --------------------------------------------------------
FICHES["Epinard"] = _f(
    nom_latin="Spinacia oleracea", famille="Amaranthacées (ex-Chénopodiacées)",
    cycle="45-60 jours, montaison rapide en jours longs et chaleur", tgerm="4-20 °C (germe mal au-delà de 20 °C)",
    tcroiss="15-18 °C", gel="Très résistant", expo="Plein soleil en automne/hiver, mi-ombre en été",
    sol="Riche, frais, humifère, bien drainé", ph="6,5-7,5",
    eau="Régulier et abondant (feuillage à forte teneur en eau)", hygro="Sol constamment frais",
    espacement="25-30 cm entre rangs, 8-10 cm sur le rang", profondeur="1,5-2 cm",
    fertilisation=FERT_STD, rotation=ROT_3, maladies="Mildiou de l'épinard (Peronospora), pucerons ; monte vite en graine par temps chaud/sec.",
    conseil="Privilégier les semis de fin d'été/automne et de fin d'hiver pour éviter la montaison estivale.")

FICHES["Blette"] = _f(
    nom_latin="Beta vulgaris subsp. vulgaris (var. cicla)", famille="Amaranthacées (ex-Chénopodiacées)",
    cycle="60 jours pour les premières feuilles, récolte échelonnée ensuite plusieurs mois",
    tgerm="8-30 °C (optimal 20-25 °C)", tcroiss="16-22 °C", gel="Assez résistante, tolère de légères gelées",
    expo="Plein soleil à mi-ombre", sol="Riche, profond, frais", ph="6,5-7,5",
    eau="Régulier", hygro="Sol frais", espacement="35-40 cm entre rangs, 30 cm sur le rang",
    profondeur="1,5-2 cm (semences agglomérées)", fertilisation=FERT_STD, rotation=ROT_3,
    maladies="Cercosporiose, pucerons ; assez rustique et peu sensible dans l'ensemble.",
    conseil="Récolte en cueillette des feuilles extérieures, la plante repousse pendant plusieurs mois.")

# --- Légumineuses -------------------------------------------------------------
FICHES["Fève"] = _f(
    nom_latin="Vicia faba", famille="Fabacées (Légumineuses)",
    cycle="Semis d'automne ou de fin d'hiver, récolte 90-120 jours après semis",
    tgerm="3-5 °C (levée possible en sol froid)", tcroiss="10-20 °C, craint la chaleur estivale",
    gel="Résistante à de bonnes gelées (variétés d'automne, jusqu'à -8/-10 °C)",
    expo="Plein soleil", sol="Profond, frais, tous types de sols même lourds", ph="6,0-7,0",
    eau="Modéré, surtout à la floraison et à la formation des gousses",
    hygro="Modérée, éviter l'excès d'humidité stagnante (favorise l'anthracnose)",
    espacement="40-50 cm entre rangs, 20 cm sur le rang", profondeur="4-5 cm",
    fertilisation=FERT_LEGUMINEUSE, rotation=ROT_4, maladies=MAL_LEGUMINEUSE,
    conseil="Pincer l'extrémité des tiges dès l'apparition des pucerons noirs pour limiter leur installation.")

for _nom, _cycle, _conseil in [
    ("Haricot vert nain", "60-70 jours semis-récolte, production étalée 3-4 semaines", "Semer par succession toutes les 3 semaines pour étaler la récolte."),
    ("Haricot vert à rames", "70-90 jours, production étalée sur plusieurs semaines", "Prévoir un palissage solide (rames ou filet) de 1,8-2 m ; production plus longue que le nain."),
    ("Haricot demi-sec", "90-110 jours, récolte à un stade intermédiaire (grain formé, gousse encore souple)", "Récolter quand le grain est formé mais la gousse pas totalement sèche."),
]:
    FICHES[_nom] = _f(
        nom_latin="Phaseolus vulgaris", famille="Fabacées (Légumineuses)", cycle=_cycle,
        tgerm="12-15 °C minimum (optimal 20-25 °C), sensible au froid humide (fonte de semis)",
        tcroiss="18-25 °C", gel="Très sensible, aucune tolérance", expo="Plein soleil",
        sol="Léger à moyen, bien drainé, réchauffé", ph="6,0-7,0",
        eau="Régulier, surtout à la floraison", hygro="Modérée ; éviter le feuillage mouillé (anthracnose)",
        espacement="40-50 cm entre rangs (60-80 cm pour les variétés à rames), 5-8 cm sur le rang",
        profondeur="3-4 cm", fertilisation=FERT_LEGUMINEUSE, rotation=ROT_4, maladies=MAL_LEGUMINEUSE, conseil=_conseil)

FICHES["Pois"] = _f(
    nom_latin="Pisum sativum", famille="Fabacées (Légumineuses)",
    cycle="60-90 jours selon variété (nain/à rames) et saison",
    tgerm="4-6 °C minimum (optimal 15-20 °C)", tcroiss="13-18 °C, craint la chaleur estivale",
    gel="Résistant à de légères gelées, semis possible dès la fin de l'hiver",
    expo="Plein soleil", sol="Frais, meuble, bien drainé, tous types de sols", ph="6,0-7,0",
    eau="Modéré, régulier surtout en floraison", hygro="Modérée, éviter l'excès d'humidité stagnante",
    espacement="40-50 cm entre rangs, 5 cm sur le rang", profondeur="3-4 cm",
    fertilisation=FERT_LEGUMINEUSE, rotation=ROT_4, maladies=MAL_LEGUMINEUSE + " Oïdium en fin de cycle par temps sec et chaud.",
    conseil="Prévoir un support (grillage, rames) même pour les variétés naines de plus de 40 cm.")

# --- Aromatiques --------------------------------------------------------------
FICHES["Basilic"] = _f(
    nom_latin="Ocimum basilicum", famille="Lamiacées",
    cycle="Semis, récolte à partir de 45-60 jours, cueillette continue ensuite",
    tgerm="20-25 °C (germination difficile en dessous de 18 °C)", tcroiss="20-28 °C", gel="Très sensible, aucune tolérance",
    expo="Plein soleil, abrité du vent", sol="Riche, frais, bien drainé", ph="6,0-7,0",
    eau="Régulier, arroser au pied sans mouiller le feuillage", hygro="Modérée ; excès d'humidité favorise la fonte des semis et le mildiou du basilic",
    espacement="30 cm entre rangs, 20-25 cm sur le rang", profondeur="0,5 cm",
    fertilisation=FERT_STD, rotation=ROT_3, maladies=MAL_AROMATIQUE + " Mildiou du basilic (Peronospora belbahrii) en conditions humides.",
    conseil="Pincer régulièrement le sommet des tiges pour retarder la montaison à graine et densifier le plant.")

FICHES["Persil"] = _f(
    nom_latin="Petroselinum crispum", famille="Apiacées (Ombellifères)",
    cycle="Levée lente (3-4 semaines), première récolte à 70-90 jours puis cueillette continue",
    tgerm="10-25 °C (levée lente et irrégulière)", tcroiss="15-20 °C", gel="Résistant, tolère l'hiver sous climat tempéré",
    expo="Plein soleil à mi-ombre", sol="Riche, frais, profond", ph="6,0-7,0",
    eau="Régulier", hygro="Sol frais en permanence", espacement="25-30 cm entre rangs, 15-20 cm sur le rang",
    profondeur="0,5-1 cm", fertilisation=FERT_STD, rotation=ROT_3, maladies=MAL_AROMATIQUE,
    conseil="Faire tremper les graines 24 h avant semis pour accélérer une levée naturellement lente.")

FICHES["Ciboulette"] = _f(
    nom_latin="Allium schoenoprasum", famille="Amaryllidacées (ex-Alliacées)",
    cycle="Semis ou division, première coupe à 70-80 jours puis vivace récoltable plusieurs années",
    tgerm="15-20 °C", tcroiss="15-20 °C", gel="Très résistante, plante vivace rustique",
    expo="Plein soleil à mi-ombre", sol="Riche, frais, bien drainé", ph="6,0-7,0",
    eau="Régulier", hygro="Sol frais", espacement="20-25 cm entre touffes", profondeur="0,5-1 cm",
    fertilisation=FERT_STD, rotation=ROT_3, maladies=MAL_AROMATIQUE,
    conseil="Diviser les touffes tous les 3-4 ans pour maintenir la vigueur ; couper court pour stimuler la repousse.")

FICHES["Coriandre"] = _f(
    nom_latin="Coriandrum sativum", famille="Apiacées (Ombellifères)",
    cycle="40-50 jours pour la récolte en feuilles, monte vite en graine en jours longs/chaleur",
    tgerm="10-20 °C", tcroiss="15-20 °C", gel="Sensible aux fortes gelées",
    expo="Plein soleil à mi-ombre l'été", sol="Léger, drainant", ph="6,0-7,0",
    eau="Modéré, sol frais", hygro="Modérée", espacement="25-30 cm entre rangs, semis dense sur le rang",
    profondeur="0,5-1 cm", fertilisation=FERT_STD, rotation=ROT_3, maladies=MAL_AROMATIQUE,
    conseil="Semer par petites succession fréquentes car la plante monte vite en graine, surtout en été.")

FICHES["Fenouil"] = _f(
    nom_latin="Foeniculum vulgare var. azoricum", famille="Apiacées (Ombellifères)",
    cycle="90-110 jours pour le fenouil bulbeux", tgerm="10-25 °C", tcroiss="15-20 °C, monte en graine si stress (froid, sécheresse)",
    gel="Assez sensible aux fortes gelées, résiste à de légères gelées", expo="Plein soleil",
    sol="Riche, frais, profond, bien drainé", ph="6,5-7,5", eau="Régulier et soutenu (sensible à la montaison en cas de stress hydrique)",
    hygro="Sol constamment frais", espacement="40 cm entre rangs, 25-30 cm sur le rang", profondeur="1 cm",
    fertilisation=FERT_STD, rotation=ROT_3, maladies=MAL_AROMATIQUE + " Pucerons occasionnels.",
    conseil="Butter légèrement le pied en formation du bulbe pour le blanchir et l'attendrir.")

# --- Céleris -------------------------------------------------------------------
FICHES["Céleri branche"] = _f(
    nom_latin="Apium graveolens var. dulce", famille="Apiacées (Ombellifères)",
    cycle="Semis, repiquage, récolte 5-6 mois après semis", tgerm="15-20 °C (levée lente, 2-3 semaines)",
    tcroiss="15-20 °C, craint les fortes chaleurs et les à-coups", gel="Sensible aux fortes gelées",
    expo="Plein soleil à mi-ombre", sol="Riche, profond, très frais à humide, forte teneur en matière organique",
    ph="6,5-7,5", eau="Élevé et très régulier (plante très gourmande en eau)",
    hygro="Sol quasi constamment humide, air non desséchant", espacement="30-40 cm entre rangs, 25-30 cm sur le rang",
    profondeur="0,5 cm (semis en pépinière, en surface)", fertilisation=FERT_GOURMAND, rotation=ROT_4,
    maladies="Septoriose, mouche mineuse du céleri, limaces ; sensible aux carences en cas de sol sec.",
    conseil="Un arrosage irrégulier provoque le fendillement et la montaison précoce des côtes.")

FICHES["Céleri rave"] = _f(
    nom_latin="Apium graveolens var. rapaceum", famille="Apiacées (Ombellifères)",
    cycle="Semis, repiquage, récolte 6-7 mois après semis (culture longue)",
    tgerm="15-20 °C (levée lente)", tcroiss="15-20 °C", gel="Assez résistant en végétation, sensible aux fortes gelées prolongées",
    expo="Plein soleil à mi-ombre", sol="Riche, profond, frais, forte teneur en matière organique",
    ph="6,5-7,0", eau="Élevé et régulier tout au long du cycle",
    hygro="Sol constamment frais à humide", espacement="40 cm entre rangs, 30-35 cm sur le rang",
    profondeur="0,5 cm (semis en pépinière, en surface)", fertilisation=FERT_GOURMAND, rotation=ROT_4,
    maladies="Septoriose, mouche mineuse, limaces ; nécessite un sol jamais desséché pour un beau renflement.",
    conseil="Retirer les racines secondaires en cours de culture pour concentrer le grossissement de la boule.")

# --- Autres cultures ------------------------------------------------------------
FICHES["Mais doux"] = _f(
    nom_latin="Zea mays var. saccharata", famille="Poacées (Graminées)",
    cycle="80-100 jours semis-récolte selon variété", tgerm="10-12 °C minimum (optimal 20-25 °C)",
    tcroiss="18-27 °C, très exigeant en chaleur et en lumière", gel="Très sensible, aucune tolérance",
    expo="Plein soleil impératif", sol="Riche, profond, bien drainé, forte demande en azote",
    ph="6,0-7,0", eau="Élevé, surtout à la floraison (formation des épis)", hygro="Modérée, bonne aération des rangs",
    espacement="70-80 cm entre rangs, 25-30 cm sur le rang", profondeur="3-4 cm",
    fertilisation="Culture très gourmande en azote : compost riche puis apports fractionnés d'engrais organique azoté.",
    rotation=ROT_3, maladies="Pyrale du maïs, pucerons, charbon ; planter en blocs carrés plutôt qu'en ligne unique pour favoriser la pollinisation.",
    conseil="Planter en blocs de plusieurs rangs courts plutôt qu'en un rang long : la pollinisation par le vent est bien meilleure.")

FICHES["Patate douce"] = _f(
    nom_latin="Ipomoea batatas", famille="Convolvulacées",
    cycle="Plantation de plants (boutures) en mai-juin, récolte 4-5 mois après (fin septembre-octobre)",
    tgerm="—", tcroiss="20-30 °C, très exigeante en chaleur", gel="Très sensible, aucune tolérance",
    expo="Plein soleil impératif", sol="Léger, sableux à limoneux, très bien drainé, réchauffé (buttes/paillage plastique conseillés)",
    ph="5,5-6,5", eau="Modéré, réduit en fin de cycle pour favoriser la formation des tubercules",
    hygro="Air chaud, sol drainé (excès d'eau favorise le pourrissement des racines)",
    espacement="80-100 cm entre rangs, 30-40 cm sur le rang", profondeur="Plantation des boutures enracinées à 5-8 cm",
    fertilisation="Peu d'azote (favorise le feuillage au détriment des tubercules), privilégier potasse et phosphore.",
    rotation=ROT_3, maladies="Peu de bio-agresseurs sous climat tempéré ; surveiller les limaces sur jeunes plants et le pourridié en sol trop humide.",
    conseil="Planter sur buttes recouvertes de film plastique noir pour réchauffer le sol, indispensable sous climat tempéré.")

FICHES["Pomme de terre"] = _f(
    nom_latin="Solanum tuberosum", famille="Solanacées",
    cycle="Plantation, récolte 90-120 jours après (variétés de conservation)",
    tgerm="7-10 °C minimum pour la levée des germes", tcroiss="15-20 °C, arrêt de tubérisation au-delà de 27 °C",
    gel="Feuillage très sensible au gel, tubercules protégés en terre par le buttage", expo="Plein soleil",
    sol="Meuble, profond, drainant, non calcaire", ph="5,5-6,5 (sol trop calcaire favorise la gale commune)",
    eau="Régulier et soutenu, notamment à la tubérisation (floraison)", hygro="Modérée ; excès d'humidité favorise le mildiou",
    espacement="60-70 cm entre rangs, 30-35 cm sur le rang", profondeur="10 cm, puis buttage progressif",
    fertilisation=FERT_STD, rotation=ROT_4, maladies=MAL_SOLANACEE + " Doryphore et mildiou en tête des préoccupations.",
    conseil="Butter 2-3 fois en cours de culture pour protéger les tubercules de la lumière (verdissement) et du gel tardif.")
FICHES["Pomme de terre primeur"] = _f(
    nom_latin="Solanum tuberosum (variété précoce)", famille="Solanacées",
    cycle="Plantation, récolte 70-90 jours après (nouvelle pomme de terre, non destinée à la garde)",
    tgerm="7-10 °C minimum, germer les plants à la lumière avant plantation (chitting)",
    tcroiss="15-20 °C", gel="Feuillage sensible au gel, protéger les levées précoces",
    expo="Plein soleil", sol="Meuble, léger, réchauffé rapidement au printemps", ph="5,5-6,5",
    eau="Régulier", hygro="Modérée", espacement="55-60 cm entre rangs, 25-30 cm sur le rang",
    profondeur="8-10 cm, buttage léger", fertilisation=FERT_STD, rotation=ROT_4, maladies=MAL_SOLANACEE,
    conseil="Récolter jeune (peau non adhérente) pour une consommation rapide en \"nouvelle\" ; pas de conservation longue.")

FICHES["Ail_placeholder_removed"] = None
del FICHES["Ail_placeholder_removed"]


# ------------------------------------------------------------------
# Vérification de couverture (utilisée en développement uniquement)
# ------------------------------------------------------------------
def cultures_sans_fiche(liste_cultures):
    """Retourne la liste des cultures du CSV qui n'ont pas encore de fiche."""
    return sorted(c for c in set(liste_cultures) if c not in FICHES)
