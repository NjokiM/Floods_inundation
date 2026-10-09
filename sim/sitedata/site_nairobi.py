"""Site configuration: NAIROBI urban corridor.

All coordinates are EPSG:4326. Elevations in metres above sea level. This file is
the single source of truth for the Nairobi bake (rivers, settlements, facilities,
phases, scenarios, narrative). Geometry relies on Copernicus GLO-30 and Esri
imagery; vector layers come from Microsoft footprints / Esri transport / fallbacks
defined in handlib.

Historical anchors (2026 Feb–Mar flash floods, as recorded in this repo's docs):
160 mm in 3–5 h at Wilson Airport on 6 Mar 2026; Nairobi River burst its banks;
Mombasa Road & Uhuru Highway flooded; ~3,500 Nairobi households affected; 71
vehicles swept on day one; highest risk wards Mathare, Mukuru kwa Njenga, Kibra.
"""

NAME = "Nairobi River corridor"
SLUG = "nairobi"
KICKER = "Urban flash flood · Nairobi, Kenya"
LEDE = (
    "Raise the Nairobi, Mathare and Ngong rivers and the water finds the ravines "
    "first — Mathare, Kiambiu, Dandora and Mukuru sit in them. Every level answers "
    "the same question: what is under water, and what should the response do?"
)
RIVER_LABEL = "River stage above bank"
STAGE_NOTE = "Stage = metres above the normal channel waterline of the Nairobi / Mathare / Ngong river system."

W = 36.70
S = -1.40  # covers Kibera ~ -1.31 south
E = 36.99
T = -1.10  # mathare top ~ -1.19; use full city breathing room
BBOX = (W, S, E, T)
CENTER = (36.845, -1.25)
CELL_M = 30           # DEM sampling pitch
Z_TILE = 13           # Esri imagery zoom

CAMERAS = [
    {"id": "wide", "name": "Wide", "lat": -1.245, "lon": 36.838, "alt": 14800, "pitch": 55},
    {"id": "mathare", "name": "Mathare", "lat": -1.2515, "lon": 36.8715, "alt": 3900, "pitch": 57},
    {"id": "mukuru", "name": "Mukuru kwa Njenga", "lat": -1.3105, "lon": 36.892, "alt": 4200, "pitch": 57},
    {"id": "kibera", "name": "Kibera", "lat": -1.3135, "lon": 36.789, "alt": 4400, "pitch": 57},
    {"id": "dandora", "name": "Dandora", "lat": -1.2620, "lon": 36.9160, "alt": 4500, "pitch": 57},
    {"id": "high", "name": "High ground (Upper Hill)", "lat": -1.2995, "lon": 36.8030, "alt": 3300, "pitch": 55},
]

# Rivers: [ (lon, lat), ... ] approximate centerlines (Nairobi system flows east).
RIVERS = [
    {
        "name": "Nairobi River",
        "order": 5,
        "pts": [
            (36.755, -1.2225), (36.772, -1.2335), (36.792, -1.2442), (36.807, -1.255),
            (36.823, -1.2605), (36.840, -1.2634), (36.857, -1.2648), (36.872, -1.2644),
            (36.888, -1.2626), (36.903, -1.2585), (36.918, -1.2540), (36.935, -1.2450),
            (36.956, -1.2305), (36.968, -1.2205),
        ],
    },
    {
        "name": "Mathare River",
        "order": 4,
        "pts": [
            (36.852, -1.2000), (36.858, -1.2168), (36.864, -1.2342), (36.871, -1.2485),
            (36.877, -1.2575), (36.8855, -1.2623), (36.8965, -1.2595),
        ],
    },
    {
        "name": "Gitathuru (Thom's) River",
        "order": 4,
        "pts": [
            (36.834, -1.2050), (36.8425, -1.2200), (36.8495, -1.2355), (36.8535, -1.2480),
            (36.8575, -1.2565), (36.8655, -1.2620),
        ],
    },
    {
        "name": "Ngong (Motoine) River",
        "order": 5,
        "pts": [
            (36.720, -1.3280), (36.739, -1.3145), (36.7595, -1.3018), (36.7765, -1.2940),
            (36.7910, -1.2908), (36.8055, -1.2918), (36.8200, -1.2952), (36.8380, -1.2992),
            (36.8560, -1.3040), (36.8740, -1.3100), (36.8960, -1.3172), (36.9220, -1.3270),
            (36.9500, -1.3372), (36.9680, -1.3440),
        ],
    },
    {
        "name": "Mbagathi River",
        "order": 4,
        "pts": [
            (36.730, -1.3450), (36.752, -1.3345), (36.772, -1.3252), (36.790, -1.3140),
            (36.806, -1.3035), (36.823, -1.2952), (36.843, -1.2922), (36.862, -1.2918),
            (36.880, -1.2890), (36.900, -1.2872), (36.924, -1.2858),
        ],
    },
]

# Settlement cells: name, center, population (documented), informal flag.
# radius_m/aspect/deg shape the procedural cluster (documented approximation).
SETTLEMENTS = [
    {"name": "Mathare", "lon": 36.8680, "lat": -1.2520, "pop": 190_000, "informal": True,
     "radius_m": 1500, "aspect": 1.85, "deg": 38},
    {"name": "Kiambiu", "lon": 36.8585, "lat": -1.2720, "pop": 35_000, "informal": True,
     "radius_m": 420, "aspect": 1.3, "deg": 10},
    {"name": "Eastleigh", "lon": 36.8495, "lat": -1.2780, "pop": 60_000, "informal": False,
     "radius_m": 700, "aspect": 1.2, "deg": 15},
    {"name": "Dandora", "lon": 36.9160, "lat": -1.2620, "pop": 80_000, "informal": False,
     "radius_m": 900, "aspect": 1.35, "deg": 40},
    {"name": "Mukuru kwa Njenga", "lon": 36.8900, "lat": -1.3110, "pop": 210_000, "informal": True,
     "radius_m": 1600, "aspect": 2.0, "deg": 55},
    {"name": "Mukuru kwa Reuben", "lon": 36.9010, "lat": -1.3000, "pop": 70_000, "informal": True,
     "radius_m": 900, "aspect": 1.6, "deg": 40},
    {"name": "Kibera", "lon": 36.7890, "lat": -1.3120, "pop": 170_000, "informal": True,
     "radius_m": 1300, "aspect": 1.9, "deg": 30},
    {"name": "Gikomba", "lon": 36.8450, "lat": -1.2870, "pop": 8_000, "informal": True,
     "radius_m": 320, "aspect": 1.2, "deg": 80},
    {"name": "Upper Hill", "lon": 36.8030, "lat": -1.2995, "pop": 4_000, "informal": False, "high": True,
     "radius_m": 450, "aspect": 1.2, "deg": 10},
    {"name": "Nairobi CBD", "lon": 36.8225, "lat": -1.2850, "pop": 12_000, "informal": False,
     "radius_m": 600, "aspect": 1.35, "deg": 25},
    {"name": "Kilimani", "lon": 36.7780, "lat": -1.2890, "pop": 30_000, "informal": False, "high": True,
     "radius_m": 800, "aspect": 1.3, "deg": 5},
    {"name": "Karen", "lon": 36.7280, "lat": -1.3250, "pop": 12_000, "informal": False, "high": True,
     "radius_m": 1100, "aspect": 1.6, "deg": 30},
]

# Fallback road corridors used only if the Esri transportation query fails
# (approximate polylines — geometry precision is decorative; totals are manifest).
ROADS = [
    {"name": "Mombasa Road (A8)", "class": 0, "pts": [
        (36.715, -1.3315), (36.755, -1.3170), (36.795, -1.3040), (36.830, -1.2995),
        (36.866, -1.2950), (36.902, -1.3000), (36.945, -1.3150), (36.985, -1.3300)]},
    {"name": "Uhuru Highway", "class": 1, "pts": [
        (36.8170, -1.3050), (36.8200, -1.2940), (36.8250, -1.2830), (36.8272, -1.2700),
        (36.8280, -1.2570)]},
    {"name": "Thika Superhighway (A2)", "class": 0, "pts": [
        (36.8385, -1.2730), (36.8620, -1.2505), (36.8870, -1.2280), (36.9160, -1.2080),
        (36.9450, -1.1880)]},
    {"name": "Juja Road", "class": 1, "pts": [
        (36.8580, -1.2735), (36.8770, -1.2590), (36.8995, -1.2370)]},
    {"name": "Outer Ring Road", "class": 1, "pts": [
        (36.8900, -1.2780), (36.8860, -1.2980), (36.8815, -1.3230)]},
    {"name": "Ngong Road", "class": 1, "pts": [
        (36.7180, -1.3270), (36.7500, -1.3115), (36.7860, -1.2990), (36.8010, -1.2955)]},
    {"name": "Mbagathi Way", "class": 2, "pts": [
        (36.7755, -1.3055), (36.8030, -1.3025), (36.8200, -1.2998)]},
    {"name": "Landhies Road", "class": 2, "pts": [
        (36.8270, -1.2870), (36.8420, -1.2810), (36.8590, -1.2740), (36.8740, -1.2705)]},
]

# Critical facilities (documented approximate real points where known).
FACILITIES = [
    {"name": "Kenyatta National Hospital", "k": "hospital", "lon": 36.8058, "lat": -1.3003},
    {"name": "Mama Lucy Kibaki Hospital", "k": "hospital", "lon": 36.8928, "lat": -1.3120},
    {"name": "Mbagathi County Hospital", "k": "hospital", "lon": 36.7744, "lat": -1.3058},
    {"name": "Pumwani Maternity", "k": "hospital", "lon": 36.8482, "lat": -1.2858},
    {"name": "Mathare North Health Centre", "k": "clinic", "lon": 36.8654, "lat": -1.2447},
    {"name": "Gikomba Market", "k": "market", "lon": 36.8443, "lat": -1.2875},
    {"name": "Dandora Primary School", "k": "school", "lon": 36.9310, "lat": -1.2685},
    {"name": "Toi Primary School, Kibera", "k": "school", "lon": 36.7822, "lat": -1.3065},
    {"name": "Nairobi Water Works — Kikuyu", "k": "water", "lon": 36.7240, "lat": -1.2580},
    {"name": "Moi Forces Academy", "k": "school", "lon": 36.8680, "lat": -1.2680},
]

# Response phases: label, threshold on stage (m), copy per phase. Colors from CSS.
PHASES = [
    {"label": "Normal",  "stage": 0.0,
     "why": "Rivers inside their banks. Seasonal showers keep the city wet but the <b>ravine neighbourhoods</b> stay dry: Mathare, Mukuru and Kibera sit metres above their channels."},
    {"label": "Watch",   "stage": 1.2,
     "why": "<b>Ravines wet first.</b> <span class='t'>Mathare and Mukuru's streamside lanes</span> flood: informal homes sit <b>directly at the water's edge</b>, where the nearest drain is the river itself."},
    {"label": "Mobilize", "stage": 2.0,
     "why": "<b>Drains are the bottleneck.</b> Storm drains clog with silt and garbage, so <span class='a'>streets flood at half the depth</span> as they would if they were clear. Crews stage on the arterials."},
    {"label": "Evacuate", "stage": 2.8,
     "why": "<b>Move people, not things.</b> <span class='r'>Order evacuation out of riparian strips first</span> (Mathare Valley, Mukuru B, Kibera sidestreets): they are the first to lose escape routes."},
    {"label": "Extreme", "stage": 3.6,
     "why": "<b>Lifelines failure.</b> Mombasa Road / Uhuru Highway sections shut, power substations isolate, and relief becomes <span class='r'>boat-and-air</span>. This is the <b class='w'>6 Mar 2026</b> profile."},
]

SCENARIOS = [
    {"id": "seasonal", "label": "Seasonal heavy rains",
     "blockage": 0.88,
     "curve": [[0.0, 0.05], [0.07, 0.25], [0.20, 0.65], [0.42, 1.0], [0.72, 0.85], [1.0, 0.35]]},
    {"id": "elnino", "label": "El Niño extreme",
     "blockage": 0.62,
     "curve": [[0.0, 0.55], [0.07, 0.95], [0.12, 1.0], [0.55, 0.95], [1.0, 0.25]]},
]

STAGE_MAX = 4.5
HIST_MARKS = [["6 Mar 2026", 3.3], ["OND 2023 El Niño", 2.1]]

INFO = {
    "methodology": """<p><b>Model = Height Above Nearest Drainage (HAND)</b>. Every terrain cell's
flood threshold is its vertical distance above the nearest stream, computed from Copernicus
GLO-30 with a priority-flood. Move the stage slider s metres above the river and every cell
whose HAND &lt; s can hold standing water (depth ≈ s − HAND). Blocked drains in informal
settlements effectively drop that threshold — why ravine neighbourhoods flood first.</p>
<p><b>Stats</b> recount baked footprint/road/facility objects against live depth fields each
slider step. Displacement uses a depth-tiered rate. All figures are <b>planning
approximations</b>, not official impact bulletins.</p>""",
    "sources": """<p><b>Terrain</b> © Copernicus GLO-30 (DLR/Airbus), via Copernicus / ESA ·
<b>Imagery</b> © Esri, Maxar, Earthstar Geographics · <b>Buildings</b> © Microsoft Global ML
Building Footprints (MIT) · <b>Rivers</b> © HydroSHEDS/HydroRIVERS (World Wildlife Fund &amp;
partners, CC-BY) · <b>Roads</b> © Esri World Transportation where queried; fallback corridors
hand-drawn · <b>Populations</b> KNBS 2019 census orders + widely-reported flood-response
figures.</p>
<p>Built with vanilla Three.js and Django. Original design and code — no reference-site
content reproduction.</p>""",
    "disclaimer": """<p><b>This is a teaching model.</b> Thresholds, settlement extents and
impact figures are calibrated approximations anchored to the well-documented 6 Mar 2026
Nairobi flood and to reported Tana River floods of 2023/2024. For operational decisions,
use Kenya's official agencies (Kenya Meteorological Department, NDMA, WRA, county
governments).</p>""",
}
