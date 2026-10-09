"""Shared geographic helpers: local-meter mapping, resampling, quantization.

Every site is baked in LOCAL METERS:
  x = east (m), z = north (m), y = elevation (m).
Cell (col i, row j) centers at:
  x = (i + 0.5) * dx - width/2,  z = H/2 - (j + 0.5) * dz   (row 0 at NORTH edge)
Texture UVs run u = i/(nx-1), v = 1 - j/(nz-1)?? — kept: v = j/(nz-1) with
texture rows aligned north→south so v=0 is north imagery edge? For simplicity the
mosaic is written top(north)→bottom(south) row-major, matching plane UV v = 1 at
north. All conventions live here to avoid drift between bake and client.
"""
import math

import numpy as np

M_PER_DEG_LAT = 110_574.0


def meters_per_deg_lon(lat_deg: float) -> float:
    return 111_320.0 * math.cos(math.radians(lat_deg))


def grid_shape(bbox, cell_m: float):
    w, s, e, t = bbox
    lat_c = (s + t) / 2
    wid_m = (e - w) * meters_per_deg_lon(lat_c)
    hei_m = (t - s) * M_PER_DEG_LAT
    nx = max(8, int(round(wid_m / cell_m)) + 1)
    nz = max(8, int(round(hei_m / cell_m)) + 1)
    return nx, nz, wid_m, hei_m


def lonlat_to_local(lon: float, lat: float, bbox, wid_m: float, hei_m: float, lat_c: float):
    """→ (x, z) meters, z = north positive, origin at bbox center."""
    w, s, e, t = bbox
    x = (lon - (w + e) / 2) * meters_per_deg_lon(lat_c)
    z = (lat - (s + t) / 2) * M_PER_DEG_LAT
    return x, z


def local_to_lonlat(x: float, z: float, bbox, lat_c: float):
    w, s, e, t = bbox
    lon = x / meters_per_deg_lon(lat_c) + (w + e) / 2
    lat = z / M_PER_DEG_LAT + (s + t) / 2
    return lon, lat


def mercator_xy(lon: float, lat: float, zoom: int):
    """Web-mercator fractional tile coords at `zoom` (x, y both fractional)."""
    import math as m
    n = 2 ** zoom
    x = (lon + 180.0) / 360.0 * n
    latr = m.radians(max(-85.0, min(85.0, lat)))
    y = (1.0 - math.log(m.tan(latr) + 1 / m.cos(latr)) / m.pi) / 2 * n
    return x, y


def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def fill_nodata(a, invalid_mask, iterations: int = 400):
    """Simple iterative mean-of-valid-neighbors fill for DEM holes (small areas)."""
    import numpy as np
    a = a.copy()
    inv = invalid_mask
    for _ in range(iterations):
        if not inv.any():
            break
        num = np.zeros_like(a)
        den = np.zeros_like(a, dtype=int)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                sh = np.roll(np.roll(a, dy, 0), dx, 1)
                msk = np.roll(np.roll(~inv, dy, 0), dx, 1)
                # edges are valid in our slices (translated roll wraps, acceptable)
                num += sh * msk
                den += msk
        take = inv & (den > 0)
        a[take] = num[take] / den[take]
        inv = inv & (den == 0)
    return a


def resample_bilinear(a, out_h: int, out_w: int):
    """PIL-based bilinear resize for float arrays (works in 'F' mode)."""
    from PIL import Image
    im = Image.fromarray(a.astype("float32"), mode="F")
    im = im.resize((out_w, out_h), Image.BILINEAR)
    return np.asarray(im, dtype="float32")
