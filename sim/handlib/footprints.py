"""Microsoft Global ML Building Footprints (MIT, non-OSM) — best-effort fetch.

The public distribution moves targets over time; we probe in order:
  1. README (raw.githubusercontent.com) → extract any blob URLs
  2. Azure blob container listing on minedbuildings (read-only if left open)
  3. Kenya/continent part-name grep of the above

If nothing resolves, we return [] — bake then synthesizes settlement clusters
procedurally from documented population figures (the central, always-on path).
Whatever succeeds is logged; the manifest records the effective building source.
"""
from pathlib import Path

import requests
from shapely.geometry import shape as shapely_shape

BLOB = "https://minedbuildings.blob.core.windows.net/globalmlbuildingfootprints"
README_RAW = "https://raw.githubusercontent.com/microsoft/GlobalMLBuildingFootprints/main/README.md"
ATTRIBUTION = "Buildings © Microsoft Global ML Building Footprints (MIT)"


def _readme_urls(cache_dir: Path, session):
    cache_dir.mkdir(parents=True, exist_ok=True)
    p = cache_dir / "msb_readme.md"
    if not p.exists():
        try:
            r = session.get(README_RAW, timeout=60)
            if r.status_code == 200:
                p.write_text(r.text)
        except requests.RequestException:
            return []
    if not p.exists():
        return []
    text = p.read_text()
    urls = []
    for token in text.replace(">", " ").replace(")", " ").split():
        t = token.strip("\"'“”")
        if t.startswith("https://") and ("minedbuildings" in t or "footprint" in t):
            if t not in urls:
                urls.append(t)
    return urls


def _list_container_prefix(prefix: str, session, maxresults=500):
    """Container listing (only works if the container allows read-list)."""
    params = {"restype": "container", "comp": "list", "prefix": prefix,
              "maxresults": str(maxresults)}
    try:
        r = session.get(BLOB, params=params, timeout=60)
    except requests.RequestException:
        return []
    if r.status_code != 200:
        return []
    import re
    names = re.findall(r"<Name>([^<]+)</Name>", r.text)
    urls = re.findall(r"<Url>([^<]+)</Url>", r.text)
    return names or urls


def kenya_parts(cache_dir: Path, session=None, verbose=True):
    """→ list of part-file URLs (geojsonl/zip) that plausibly cover Kenya."""
    sess = session or requests.Session()
    readme_urls = _readme_urls(cache_dir, sess)
    if verbose:
        print(f"  MS footprints: {len(readme_urls)} URLs found in README")
    # README usually lists continent zips; pick ones plausibly covering Kenya
    picks = []
    for u in readme_urls:
        low = u.lower()
        if any(k in low for k in ("africa", "af-", "-af", "soute", "south-africa",
                                  "east-africa", "africa.zip", "africa.csv")):
            picks.append(u)
    # also try direct prefix listing for kenya/af
    listing = _list_container_prefix("", sess)
    kenyaish = [f"{BLOB}/{n}" for n in listing if "kenya" in n.lower()]
    kenyaish += _list_container_prefix("kenya", sess, maxresults=50)
    kenyaish += [f"{BLOB}/geojson_parts/{n}" for n in _list_container_prefix("geojson_parts/", sess) if "kenya" in n.lower()]
    # README table sometimes has per-country .csv; grep it as a last resort
    for u in kenyaish if kenyaish else []:
        picks.append(u)
    # de-dupe
    seen, out = set(), []
    for u in picks:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def fetch_features(bbox, cache_dir: Path, session=None, verbose=True, max_features=400_000):
    """→ {records: [...], source: str|None}. Records in local meters added later."""
    from shapely.geometry import box

    sess = session or requests.Session()
    parts = kenya_parts(cache_dir, sess, verbose=verbose)
    if not parts:
        if verbose:
            print("  MS footprints: no part links resolved — procedural clusters only")
        return [], None
    import io
    import zipfile
    import json
    feats = []
    src = None
    for url in parts[:6]:
        try:
            r = sess.get(url, timeout=300, stream=False)
        except requests.RequestException:
            continue
        if r.status_code != 200:
            continue
        blob = r.content
        if not blob:
            continue
        try:
            if url.endswith(".zip"):
                zf = zipfile.ZipFile(io.BytesIO(blob))
                name = [n for n in zf.namelist() if n.endswith((".geojsonl", ".geojson", ".json"))][0]
                text = zf.read(name).decode("utf-8", "ignore")
            else:
                text = blob.decode("utf-8", "ignore")
        except Exception:
            continue
        feats += _parse_geojsonl(text, bbox, max_features=max_features - len(feats))
        src = url.rsplit("/", 1)[-1]
        if verbose:
            print(f"  MS footprints: {len(feats)} features so far (part {src})")
        if len(feats) >= max_features:
            break
    return feats, src


def _parse_geojsonl(text, bbox, max_features):
    w, s, e, t = bbox
    clip_box = box(w, s, e, t)
    out = []
    for line in text.splitlines():
        if not line or len(out) >= max_features:
            break
        ch = line[0]
        if ch not in "{\"":
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        geomraw = obj.get("geometry") or obj.get("geom")
        props = obj.get("properties") or {}
        if geomraw is None:
            continue
        try:
            geom = shapely_shape(geomraw)
        except Exception:
            continue
        if not geom.is_valid:
            try:
                geom = geom.buffer(0)
            except Exception:
                continue
        if not geom.intersects(clip_box):
            continue
        # chop to bbox (avoid huge slivers)
        g = geom.intersection(clip_box)
        if g.is_empty or g.is_valid is False:
            continue
        out.append({"geom": g,
                    "attrs": {"area": (props or {}).get("size_get_area") or None,
                              "conf": (props or {}).get("confidence")}})
        if len(out) >= max_features:
            break
    return out
