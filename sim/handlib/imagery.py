"""Esri World Imagery mosaic → single draped JPEG for the terrain shader.

Tiles from the classic anonymous endpoint:
  https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}
Attribution rendered in-app: "© Esri, Maxar, Earthstar Geographics".

The whole mosaic is baked at prep time; the client never streams tiles (offline
demo). If the endpoint refuses, bake still succeeds by signalling "no texture"
and the terrain shader falls back to a shaded-relief color ramp.
"""
import math
import io

import numpy as np
import requests

TILE_URL = ("https://server.arcgisonline.com/ArcGIS/rest/services/"
            "World_Imagery/MapServer/tile/{z}/{y}/{x}")
ATTRIBUTION = "© Esri, Maxar, Earthstar Geographics"


def _tile_range(bbox, zoom):
    w, s, e, t = bbox
    from .geo import mercator_xy
    xa, ya = mercator_xy(w, t, zoom)      # north-west
    xb, yb = mercator_xy(e, s, zoom)      # south-east
    return int(math.floor(xa)), int(math.floor(ya)), int(math.floor(xb)), int(math.floor(yb))


def fetch_mosaic(bbox, zoom: int, max_px=2600, session=None, verbose=True):
    """Return (PIL.Image, coverage_fraction). Top-left = NW corner of bbox."""
    sessions = session or requests.Session()
    z = zoom
    tx0, ty0, tx1, ty1 = _tile_range(bbox, z)
    ntiles = (tx1 - tx0 + 1) * (ty1 - ty0 + 1)
    if ntiles > 600:
        # guard against runaway zoom (shouldn't happen with our choices)
        while (tx1 - tx0 + 1) * (ty1 - ty0 + 1) > 600:
            z -= 1
            tx0, ty0, tx1, ty1 = _tile_range(bbox, z)
            ntiles = (tx1 - tx0 + 1) * (ty1 - ty0 + 1)
    tile_px = 256
    canvas_w = (tx1 - tx0 + 1) * tile_px
    canvas_h = (ty1 - ty0 + 1) * tile_px
    from PIL import Image
    ok = 0
    grid = Image.new("RGB", (canvas_w, canvas_h), (20, 22, 20))
    for ty in range(ty0, ty1 + 1):
        for tx in range(tx0, tx1 + 1):
            url = TILE_URL.format(z=z, y=ty, x=tx)
            try:
                r = sessions.get(url, timeout=45)
            except requests.RequestException:
                continue
            if r.status_code == 200 and r.headers.get("content-type", "").startswith("image"):
                im = Image.open(io.BytesIO(r.content)).convert("RGB")
                grid.paste(im, ((tx - tx0) * tile_px, (ty - ty0) * tile_px))
                ok += 1
    cov = ok / max(1, ntiles)
    if verbose:
        print(f"  imagery: {ok}/{ntiles} tiles at z{z}, coverage {cov:.0%}")
    # crop to the exact bbox rect (fractional tiles trimmed)
    w, s, e, t = bbox
    from .geo import mercator_xy
    xa, ya = mercator_xy(w, t, z)
    xb, yb = mercator_xy(e, s, z)
    cx0 = int(round((xa - tx0) * tile_px))
    cy0 = int(round((ya - ty0) * tile_px))
    cx1 = int(round((xb - tx0) * tile_px))
    cy1 = int(round((yb - ty0) * tile_px))
    cx0 = max(0, min(canvas_w - 1, cx0))
    cy0 = max(0, min(canvas_h - 1, cy0))
    cx1 = max(cx0 + 8, min(canvas_w, cx1))
    cy1 = max(cy0 + 8, min(canvas_h, cy1))
    crop = grid.crop((cx0, cy0, cx1, cy1))
    # cap the larger side at max_px (cheap JPEG scale-invariant detail)
    cw, ch = crop.size
    scale = min(1.0, max_px / max(cw, ch))
    if scale < 1.0:
        crop = crop.resize((max(64, int(cw * scale)), max(64, int(ch * scale))),
                           Image.LANCZOS)
    return crop, cov
