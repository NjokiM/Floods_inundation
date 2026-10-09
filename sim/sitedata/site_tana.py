"""Site configuration: TANA RIVER — Hola to Garsen corridor.

Coordinates EPSG:4326, elevations m.a.s.l. The lower Tana is a broad, shallow
clay floodplain: prolonged, widespread riverine flooding with dyked villages.
Labels marked "approx" are documented approximations of real geography anchored
to widely reported flood events (Oct–Nov 2023 El Niño; Apr–May 2024 long rains;
regular seasonal floods). Stage semantics: metres at the Hola gauge.
"""

NAME = "Tana River · Hola–Garsen"
SLUG = "tana"
SCORE_KICKER = "Riverine flood · lower Tana, Kenya"
KICKER = "Riverine flood · Lower Tana"
LEDE = (
    "Raise the Tana and the shallow clay floodplain answers slowly and "
    "everywhere — a wide sheet of standing water that turns villages into "
    "islands for weeks. At every level: who is wet, who is cut off, and what "
    "must move first?"
)
RIVER_LABEL = "Gauge level at Hola"

STAGE_NOTE = "Gauge level in metres above the normal dry-season river at Hola (upstream boundary condition)."

BBOX = (39.60, -2.32, 40.28, -1.12)
CENTER = (40.02, -1.72)
CELL_M = 50
Z_TILE = 12

CAMERAS = [
    {"id": "wide", "name": "Wide (Hola→Garsen)", "lat": -1.72, "lon": 40.02, "alt": 26500, "pitch": 52},
    {"id": "hola", "name": "Hola", "lat": -1.5015, "lon": 40.0310, "alt": 4200, "pitch": 57},
    {"id": "wenje", "name": "Wenje", "lat": -1.4850, "lon": 39.9640, "alt": 4000, "pitch": 57},
    {"id": "kotile", "name": "Kotile", "lat": -1.7750, "lon": 40.0830, "alt": 4300, "pitch": 57},
    {"id": "garsen", "name": "Garsen", "lat": -2.0310, "lon": 40.1050, "alt": 4100, "pitch": 57},
]

RIVERS = [
    {
        "name": "Tana River (main)",
        "order": 9,
        "pts": [
            (39.845, -1.1725), (39.8835, -1.2485), (39.9205, -1.3135), (39.9560, -1.3725),
            (39.9820, -1.4230), (39.9950, -1.4620), (40.0055, -1.4900), (40.0235, -1.4995),
            (40.0445, -1.5125), (40.0600, -1.5365), (40.0695, -1.5690), (40.0790, -1.6165),
            (40.0850, -1.6740), (40.0865, -1.7280), (40.0895, -1.7875), (40.0955, -1.8395),
            (40.1005, -1.8900), (40.1045, -1.9440), (40.1080, -1.9945), (40.1095, -2.0310),
            (40.1185, -2.0885), (40.1340, -2.1410), (40.1545, -2.1985), (40.1725, -2.2540),
        ],
    },
    {
        "name": "Tana distributary (Laini channel)",
        "order": 7,
        "pts": [
            (40.0620, -1.5440), (40.0875, -1.5820), (40.1050, -1.6270), (40.1150, -1.6795),
            (40.1200, -1.7385), (40.1220, -1.8000), (40.1270, -1.8610), (40.1340, -1.9185),
        ],
    },
    {
        "name": "Tana distributary (Njoro channel)",
        "order": 6,
        "pts": [
            (40.0710, -1.6210), (40.0530, -1.6720), (40.0455, -1.7290), (40.0450, -1.7880),
            (40.0525, -1.8420), (40.0660, -1.8930), (40.0815, -1.9445),
        ],
    },
]

SETTLEMENTS = [
    {"name": "Bura East", "lon": 39.6455, "lat": -1.2425, "pop": 12_000, "informal": False,
     "radius_m": 800, "aspect": 1.5, "deg": 20},
    {"name": "Mororo", "lon": 39.7845, "lat": -1.7110, "pop": 3_500, "informal": True,
     "radius_m": 480, "aspect": 1.4, "deg": 15},
    {"name": "Wenje", "lon": 39.9640, "lat": -1.4850, "pop": 9_500, "informal": True,
     "radius_m": 620, "aspect": 1.5, "deg": 5},
    {"name": "Hola (Idsowe)", "lon": 40.0310, "lat": -1.5015, "pop": 32_000, "informal": False,
     "radius_m": 900, "aspect": 1.4, "deg": 35},
    {"name": "Kotile", "lon": 40.0830, "lat": -1.7750, "pop": 6_000, "informal": True,
     "radius_m": 560, "aspect": 1.5, "deg": 10},
    {"name": "Sera", "lon": 40.1130, "lat": -1.8950, "pop": 4_500, "informal": True,
     "radius_m": 500, "aspect": 1.4, "deg": 0},
    {"name": "Garsen", "lon": 40.1050, "lat": -2.0310, "pop": 14_000, "informal": False,
     "radius_m": 800, "aspect": 1.3, "deg": 20},
    {"name": "Chanekani", "lon": 40.1490, "lat": -2.1860, "pop": 5_000, "informal": True,
     "radius_m": 520, "aspect": 1.6, "deg": 40},
    {"name": "Kipini edge", "lon": 40.2450, "lat": -2.2680, "pop": 3_000, "informal": False,
     "radius_m": 460, "aspect": 1.2, "deg": 10},
    {"name": "Bura riverine farms", "lon": 39.6680, "lat": -1.3210, "pop": 6_000, "informal": True,
     "radius_m": 900, "aspect": 2.2, "deg": 30},
    {"name": "Kone", "lon": 40.0240, "lat": -1.5680, "pop": 7_000, "informal": True,
     "radius_m": 600, "aspect": 1.7, "deg": -10},
]

FACILITIES = [
    {"name": "Hola County Referral Hospital", "k": "hospital", "lon": 40.0295, "lat": -1.5045},
    {"name": "Garsen Sub-County Hospital", "k": "hospital", "lon": 40.1030, "lat": -2.0285},
    {"name": "Wenje Health Centre", "k": "clinic", "lon": 39.9635, "lat": -1.4835},
    {"name": "Bura Health Centre", "k": "clinic", "lon": 39.6440, "lat": -1.2460},
    {"name": "Hola Township Primary School", "k": "school", "lon": 40.0360, "lat": -1.5010},
    {"name": "Wenje Secondary School", "k": "school", "lon": 39.9620, "lat": -1.4872},
    {"name": "Garsen Boys Primary School", "k": "school", "lon": 40.1010, "lat": -2.0252},
    {"name": "Kotile Primary School", "k": "school", "lon": 40.0810, "lat": -1.7725},
    {"name": "Hola Market", "k": "market", "lon": 40.0325, "lat": -1.5008},
    {"name": "Garsen Market", "k": "market", "lon": 40.1060, "lat": -2.0325},
    {"name": "Hola water intake", "k": "water", "lon": 40.0195, "lat": -1.4952},
]

# Fallback road corridors (Esri transportation query is first choice).
ROADS = [
    {"name": "Garissa–Hola road", "class": 1, "pts": [
        (39.6445, -1.2430), (39.7000, -1.2900), (39.7900, -1.3560), (39.8800, -1.4210),
        (39.9600, -1.4740), (40.0270, -1.5025), (40.0340, -1.5020)]},
    {"name": "Hola–Garsen road", "class": 1, "pts": [
        (40.0430, -1.5130), (40.0630, -1.5640), (40.0770, -1.6250), (40.0855, -1.6945),
        (40.0925, -1.7690), (40.1010, -1.8460), (40.1065, -1.9230), (40.1090, -1.9960),
        (40.1105, -2.0300), (40.1310, -2.1060), (40.1510, -2.1870)]},
    {"name": "Bura–Mororo track", "class": 2, "pts": [
        (39.6480, -1.2520), (39.6900, -1.3900), (39.7600, -1.5600), (39.7855, -1.7000)]},
    {"name": "Garsen–Kipini track", "class": 3, "pts": [
        (40.1180, -2.0480), (40.1750, -2.1400), (40.2420, -2.2360)]},
]

# Same 5-phase ladder; thresholds are gauge metres (documented approximations).
PHASES = [
    {"label": "Normal",  "stage": 0.0,
     "why": "Dry-season flow in the channel. The dyked levees and the <b>higher terraces</b> (Hola township, Garsen ridge) keep everything else dry."},
    {"label": "Watch",   "stage": 3.0,
     "why": "<b>Backswamps fill first.</b> Old oxbows and the low <span class='t'>farms behind the levees</span> (Wenje, Kotile, Mororo) take water weeks before the towns do."},
    {"label": "Mobilize", "stage": 4.5,
     "why": "<b>Islands form.</b> The dyked compounds work — until one breaks. A single breach floods the whole protected area within a night. Crews stock sandbags at the schools; ferry crossings start."},
    {"label": "Evacuate", "stage": 6.0,
     "why": "<b>Move out of the sheet.</b> Order evacuation of the floodplain villages while the road spine still reads: <span class='r'>Hola–Garsen road closes section by section.</span> Relief prepositions at Hola."},
    {"label": "Extreme", "stage": 7.2,
     "why": "<b>Fields become lakes.</b> This profile (2023/2024 style) stands for <b>weeks</b>: cholera risk, crop loss, schools closed into shelters. Response shifts fully to boats and air-drops."},
]

SCENARIOS = [
    {"id": "seasonal", "label": "Seasonal rains",
     "blockage": 1.0,
     "curve": [[0.0, 0.1], [0.35, 0.55], [0.75, 1.0], [1.0, 0.6]]},
    {"id": "elnino", "label": "El Niño extreme",
     "blockage": 0.95,
     "curve": [[0.0, 0.3], [0.55, 1.0], [1.0, 0.8]]},
    {"id": "dam", "label": "Dam release / surge",
     "blockage": 1.0,
     "curve": [[0.0, 0.75], [0.10, 1.0], [0.6, 0.8], [1.0, 0.15]]},
]

STAGE_MAX = 8.0
HIST_MARKS = [["Nov 2023 El Niño", 6.1], ["Apr 2024 long rains", 6.9]]

INFO = {
    "methodology": """<p><b>Model = Height Above Nearest Drainage (HAND)</b>, computed from
Copernicus GLO-30 at ~50 m. The slider is the river <b>gauge level at Hola</b>; every floodplain
cell holds standing water once the gauge rises past its threshold (cell HAND plus its local
spill relation). Dyke compounds result as natural "spills": water enters them only when the
river tops the levee line.</p>
<p><b>Stats</b> re-baked per slider step over footprint/road/facility layers; displacement uses
a depth-tiered rate. Figures are planning approximations for teaching use, not official
counts.</p>""",
    "sources": """<p><b>Terrain</b> © Copernicus GLO-30 (DLR/Airbus), via Copernicus / ESA ·
<b>Imagery</b> © Esri, Maxar, Earthstar Geographics · <b>Buildings</b> © Microsoft Global ML
Building Footprints (MIT) · <b>Rivers</b> © HydroSHEDS/HydroRIVERS (WWF &amp; partners, CC-BY)
· <b>Roads</b> © Esri World Transportation where queried; fallback corridors hand-drawn ·
<b>Populations</b> KNBS 2019 counts by ward + widely-reported response figures.</p>""",
    "disclaimer": """<p><b>This is a teaching model.</b> Gauge thresholds, settlement extents and
impact figures are calibrated approximations anchored to the reported Tana floods of
2023/2024 and typical seasonal peaks. For operational decisions use Kenya's official
agencies (NDMA, Kenya Meteorological Department, WRA, Tana River county).</p>""",
}
