"""Roads — Esri World Transportation query first, config fallback corridors after.

ArcGIS REST query (anonymous, low-volume public demo usage; attribution Esri):
  https://server.arcgisonline.com/ArcGIS/rest/services/Specialty/World_Transportation/MapServer/0/query
Returns esri JSON (polyline features, WGS84 with outSR=4326). We try a bbox
query and map classes ("Codetags"/"RoutePreType"… degrade to class buckets).

Fallback: hand-drawn corridors from the site config (documented approximations).
"""
import math
import urllib.parse
import requests
from shapely.geometry import LineString

SVC = ("https://server.arcgisonline.com/ArcGIS/rest/services/Specialty/"
       "World_Transportation/MapServer")
LAYER = 0
ATTRIBUTION = "Roads © Esri World Transportation (where queried)"

_CLASSES = {"Freeway": 0, "Highway": 0, "Expressway": 0, "Motorway": 0,
            "Primary": 1, "Trunk": 0, "Major": 1, "Secondary": 2, "Road": 2,
            "Street": 3, "Track": 3, "Ramp": 3}


def query_esri(bbox, session=None, verbose=True, limit=4000):
    w, s, e, t = bbox
    env = {"xmin": w, "ymin": s, "xmax": e, "ymax": t,
           "spatialReference": {"wkid": 4326}}
    params = {
        "f": "json",
        "where": "1=1",
        "geometry": urllib.parse.quote(str(env).replace("'", '"')),
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "*",
        "outSR": "4326",
        "returnGeometry": "true",
        "resultOffset": "0",
        "resultRecordCount": str(limit),
    }
    url = f"{SVC}/{LAYER}/query"
    sess = session or requests.Session()
    try:
        r = sess.get(url, params=params, timeout=90)
    except requests.RequestException as ex:
        print(f"  Esri roads: request failed ({ex.__class__.__name__})")
        return []
    if r.status_code != 200:
        print(f"  Esri roads: HTTP {r.status_code}")
        return []
    js = r.json()
    if js.get("error"):
        print(f"  Esri roads: service error {js['error'].get('message')}")
        return []
    feats = js.get("features") or []
    if verbose:
        print(f"  Esri roads: {len(feats)} features returned")
    out = []
    for f_ in feats:
        geom = (f_.get("geometry") or {})
        paths = geom.get("paths")
        if not paths:
            continue
        attrs = f_.get("attributes") or {}
        label = str(attrs.get("FullName") or attrs.get("RoutePreType") or
                    attrs.get("RouteType") or "")
        cls = None
        for k, v in _CLASSES.items():
            if k.lower() in label.lower():
                cls = v
                break
        out.append({"name": label, "class": 1 if cls is None else cls,
                    "lines": paths})
    return out


def site_roads(bbox, lat_c, config_roads, session=None, verbose=True):
    """→ [{"class", "name", "pts":[(x,z)...]}] in local meters."""
    from .geo import lonlat_to_local

    def to_local(pts_lonlat):
        return [lonlat_to_local(x, y, bbox, 0, 0, lat_c) for x, y in pts_lonlat]

    feats = query_esri(bbox, session, verbose=verbose)
    if feats:
        out = []
        for f_ in feats:
            for path in f_["lines"]:
                pts = [(p[0], p[1]) for p in path]
                line = LineString(pts)
                if line.length * 111_320 < 500:
                    continue
                line = line.simplify(60.0 / 111_320.0, preserve_topology=True)
                out.append({"name": f_["name"], "class": f_["class"],
                            "pts": to_local(list(line.coords))})
        # dedupe same-name overlaps
        return out

    out = []
    for r in config_roads:
        out.append({"name": r["name"], "class": r.get("class", 2),
                    "pts": to_local(r["pts"])})
    return out
