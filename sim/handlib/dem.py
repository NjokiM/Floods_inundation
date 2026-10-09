"""Copernicus GLO-30 DEM fetch + window resample (rewritten for clarity).

Tiles = 1°x1° COGs in the open AWS bucket (no credentials):
  https://copernicus-dem-30m.s3.amazonaws.com/<NAME>/<NAME>.tif
where NAME marks the tile's NORTH-WEST corner cell, e.g. S02/E036 covers
lat [-2,-1], lon [36,37].

download_tiles() streams tiles into a local cache dir; fetch_grid() then reads
each tile's bbox intersection with rasterio and bilinear-resamples it onto the
site grid. Overlaps (adjacent tile seams) keep the first writer's data; final
residual holes are filled from neighbors.
"""
import math
from pathlib import Path

import numpy as np
import requests

BASE = "https://copernicus-dem-30m.s3.amazonaws.com"


def _candidate_tile_names(bbox):
    w, s, e, t = bbox
    outs = set()
    for lat_corner in (math.floor(s), math.floor(t)):
        for lon_corner in (math.floor(w), math.floor(e)):
            for la in (lat_corner, lat_corner + 1):
                for lo in (lon_corner, lon_corner + 1):
                    la_q = min(79, max(-79, la))
                    lo_q = min(179, max(-179, lo))
                    ns = "N" if la_q >= 0 else "S"
                    ew = "E" if lo_q >= 0 else "W"
                    outs.add(
                        f"Copernicus_DSM_COG_10_{ns}{abs(la_q):02d}_00_"
                        f"{ew}{abs(lo_q):03d}_00_DEM"
                    )
    return sorted(outs)


def download_tiles(bbox, cache_dir: Path, session=None, verbose=True):
    sess = session or requests.Session()
    cache_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for name in _candidate_tile_names(bbox):
        url = f"{BASE}/{name}/{name}.tif"
        p = cache_dir / f"{name}.tif"
        if p.exists() and p.stat().st_size > 1_000_000:
            paths.append(p)
            continue
        try:
            r = sess.get(url, timeout=180, stream=True)
        except requests.RequestException as ex:
            if verbose:
                print(f"  DEM {name}: request failed ({ex.__class__.__name__})")
            continue
        if r.status_code != 200:
            if verbose:
                print(f"  DEM {name}: HTTP {r.status_code} — skipped")
            continue
        tmp = p.with_suffix(".part")
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
        tmp.rename(p)
        paths.append(p)
        if verbose:
            print(f"  DEM {name}: {p.stat().st_size/1e6:.1f} MB cached")
    return paths


def _window_read(local_tif: Path, bbox):
    """Intersection of bbox with a tile: native-res float32 window + geo metadata."""
    import rasterio

    w, s, e, t = bbox
    with rasterio.open(local_tif) as ds:
        tf = ds.transform
        # lon/lat → fractional pixel coords in this tile's CRS grid
        col_f = (np.array([w, e]) - tf.c) / tf.a
        row_f = (np.array([t, s]) - tf.f) / tf.e
        c0, c1 = col_f.min(), col_f.max()
        r0, r1 = row_f.min(), row_f.max()
        ic0, ic1 = max(0, int(math.floor(c0))), min(ds.width, int(math.ceil(c1)))
        ir0, ir1 = max(0, int(math.floor(r0))), min(ds.height, int(math.ceil(r1)))
        if ic1 - ic0 < 2 or ir1 - ir0 < 2:
            return None
        win = rasterio.windows.Window(ic0, ir0, ic1 - ic0, ir1 - ir0)
        arr = np.asarray(ds.read(1, window=win), dtype="float32")
        nod = ds.nodata
        bad = np.zeros(arr.shape, dtype=bool)
        if nod is not None:
            bad |= np.isclose(arr, nod)
        bad |= ~np.isfinite(arr)
        lon0 = tf.c + ic0 * tf.a
        lat0 = tf.f + ir0 * tf.e           # NORTH edge of window
        lon1 = tf.c + ic1 * tf.a
        lat1 = tf.f + ir1 * tf.e
    return {
        "arr": arr, "bad": bad,
        "lon0": lon0, "lon1": lon1, "lat0": lat0, "lat1": lat1,
    }


def fetch_grid(bbox, nx: int, nz: int, cache_dir: Path, session=None, verbose=True):
    """float32 elevation grid [nz rows, nx cols], row 0 = NORTH edge, meters."""
    from .geo import fill_nodata, resample_bilinear

    w, s, e, t = bbox
    tiles = download_tiles(bbox, cache_dir, session)
    if not tiles:
        raise RuntimeError("No Copernicus GLO-30 tiles could be fetched.")
    canvas = np.full((nz, nx), np.nan, dtype="float32")
    for pth in tiles:
        info = _window_read(pth, bbox)
        if info is None:
            continue
        lon0, lon1, lat0, lat1 = info["lon0"], info["lon1"], info["lat0"], info["lat1"]
        # canvas fractional space (rows from north edge)
        fx0 = (lon0 - w) / (e - w) * nx
        fx1 = (lon1 - w) / (e - w) * nx
        fy0 = (t - lat0) / (t - s) * nz
        fy1 = (t - lat1) / (t - s) * nz
        x0, x1 = max(0, int(round(fx0))), min(nx, int(round(fx1)))
        y0, y1 = max(0, int(round(fy0))), min(nz, int(round(fy1)))
        if x1 - x0 < 2 or y1 - y0 < 2:
            continue
        patch = resample_bilinear(info["arr"], y1 - y0, x1 - x0)
        pbm = resample_bilinear(info["bad"].astype("float32"), y1 - y0, x1 - x0) > 0.5
        region = canvas[y0:y1, x0:x1]
        # first writer wins; skip patch cells that are nodata
        canvas[y0:y1, x0:x1] = np.where(np.isnan(region) & ~pbm, patch, region)
    grid = fill_nodata(canvas, np.isnan(canvas), iterations=800)
    if np.isnan(grid.astype("float32")).any():
        grid = np.nan_to_num(grid, nan=np.nanmin(grid))
    return grid.astype("float32")
