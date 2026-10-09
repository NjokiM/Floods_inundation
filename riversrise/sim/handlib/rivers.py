"""River centerlines — HydroRIVERS when available, config fallback otherwise.

HydroRIVERS (HydroSHEDS.org, CC BY 4.0, non-OSM) Africa shapefile is read with
pyshp; features intersecting the site bbox (and near the configured corridors)
are converted to local-meter polylines, inheriting name/order from the site
config when a matching corridor is found.

If the download or parse fails, the config's hand-drawn centerlines are used
and the manifest records them as documented approximations.
"""
import math
from pathlib import Path

import requests
from shapely.geometry import LineString
from shapely.ops import unary_union

AF_URL = "https://data.hydrosheds.org/file/hydroRIVERS/hyrorivers_v10africa_shp.zip"
ATTRIBUTION = "Rivers © HydroSHEDS/HydroRIVERS (WWF & partners), CC BY 4.0"


def fetch_hydrorivers_af(cache_dir: Path, session=None, verbose=True):
    import zipfile
    cache_dir.mkdir(parents=True, exist_ok=True)
    marker = cache_dir / "hyrorivers_af_extracted"
    if marker.exists() and any(marker.glob("**/*.shp")):
        return sorted(marker.glob("**/*.shp"))
    sess = session or requests.Session()
    try:
        r = sess.get(AF_URL, timeout=300, stream=True)
    except requests.RequestException as ex:
        print(f"  HydroRIVERS: download failed ({ex.__class__.__name__})")
        return []
    if r.status_code != 200:
        print(f"  HydroRIVERS: HTTP {r.status_code} — falling back to config lines")
        return []
    zpath = cache_dir / "hyrorivers_af.zip"
    tmp = zpath.with_suffix(".part")
    with open(tmp, "wb") as f:
        for chunk in r.iter_content(1 << 20):
            f.write(chunk)
    tmp.rename(zpath)
    print(f"  HydroRIVERS archive: {zpath.stat().st_size / 1e6:.0f} MB")
    with zipfile.ZipFile(zpath) as z:
        z.extractall(marker)
    return sorted(marker.glob("**/*.shp"))


def site_rivers(bbox, lat_c, config_rivers, cache_dir, session=None,
                near_m=4000.0, verbose=True):
    """→ list of {"name", "order", "pts": [(x,z)...], "src": "hyd"|"approx"}"""
    from .geo import lonlat_to_local

    w, s, e, t = bbox

    def to_local(pts_lonlat):
        return [lonlat_to_local(x, y, bbox, 0, 0, lat_c) for x, y in pts_lonlat]

    corridor = unary_union(
        [LineString(r["pts"]).buffer(near_m / 111_320.0) for r in config_rivers]
    )

    shps = fetch_hydrorivers_af(cache_dir, session, verbose=verbose)
    if not shps:
        if verbose:
            print("  rivers: using config (documented approximation) centerlines")
        return [{"name": r["name"], "order": r["order"],
                 "pts": to_local(r["pts"]), "src": "approx"} for r in config_rivers]

    import shapefile
    feats = []
    for shp in shps:
        try:
            sf = shapefile.Reader(str(shp))
        except Exception as ex:
            print(f"  HydroRIVERS: cannot read {shp} ({ex})")
            continue
        fields = [f[0] for f in sf.fields[1:]]
        i_name = "riv_name" if "riv_name" in fields else None
        i_ord = "riv_ord" if "riv_ord" in fields else None
        kept = 0
        for sr in sf.iterShapeRecords():
            shx = sr.shape
            bx = shx.bbox
            if bx[2] < w or bx[0] > e or bx[3] < s or bx[1] > t:
                continue
            rec = sr.record.as_dict()
            line = LineString(shx.points)
            if not corridor.intersects(line):
                continue
            mid = line.interpolate(0.5, normalized=True)
            best, best_d = None, 1e12
            for r in config_rivers:
                d = mid.distance(LineString(r["pts"]))
                if d < best_d:
                    best, best_d = r, d
            near_cfg = best is not None and best_d * 111_320.0 < 6_000.0
            name = best["name"] if near_cfg else (rec.get(i_name) if i_name else "")
            order = best["order"] if near_cfg else (rec.get(i_ord) if i_ord else 0)
            tol_deg = 100.0 / (111_320.0 * max(0.4, math.cos(math.radians((s + t) / 2))))
            line = line.simplify(tol_deg, preserve_topology=True)
            feats.append({
                "name": name or "unnamed reach",
                "order": int(order or (best["order"] if best else 4)),
                "pts": to_local(list(line.coords)),
                "src": "hyd",
            })
            kept += 1
        if kept and verbose:
            print(f"  HydroRIVERS: {kept} reaches kept from {shp.name}")

    # make sure every configured corridor exists at least once
    have = {f["name"] for f in feats}
    for cfg in config_rivers:
        if cfg["name"] not in have:
            feats.append({"name": cfg["name"], "order": cfg["order"],
                          "pts": to_local(cfg["pts"]), "src": "approx"})
    return feats
