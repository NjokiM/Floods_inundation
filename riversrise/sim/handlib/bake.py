"""The site bake pipeline: DEM → HAND → streams → buildings → roads → assets.

Pipeline per site (commands bake_nairobi / bake_tana / bake_all):
  1. Copernicus GLO-30 window → site elevation grid (local meters, dx/dz pitch).
  2. Rivers (HydroRIVERS ∪ config fallback) → rasterized stream seeds.
  3. bucket priority-flood → per-cell thresh_cm (spill − outlet) + out_cm.
  4. Buildings: real footprints (best-effort MS) + procedural settlement
     clusters anchored to documented populations (deterministic).
  5. Roads: Esri World Transportation query, else config-fallback corridors.
  6. Settlement masks + shelters + imagery mosaic + manifest (narrative, cams,
     phases, scenarios). Written into sim/static/data/<slug>/.
"""
import json
import math
import random
import struct
import zlib
from pathlib import Path

import numpy as np
import requests

import sim.handlib.geo as geo
from sim.handlib import dem as demlib
from sim.handlib import hand as handlib
from sim.handlib import imagery as imagerylib
from sim.handlib import rivers as riverslib
from sim.handlib import roads as roadslib
from sim.handlib import footprints as fplib

CACHE_ROOT = Path(__file__).resolve().parents[2] / ".cache"
OUT_ROOT = Path(__file__).resolve().parents[2] / "sim" / "static" / "data"

SETTLE_R_INFORMAL_M = 1150.0
SETTLE_R_FORMAL_M = 620.0
HH_INFORMAL = 5.5
HH_FORMAL = 4.0


class SiteBaker:
    def __init__(self, site, verbose=True):
        self.site = site
        self.verbose = verbose
        self.bbox = site.BBOX
        self.w, self.s, self.e, self.t = self.bbox
        self.lat_c = (self.s + self.t) / 2
        self.cell_m = site.CELL_M
        self.slug = site.SLUG
        self.root = OUT_ROOT / self.slug
        self.cache_dem = CACHE_ROOT / "dem"
        self.cache_bld = CACHE_ROOT / "buildings"
        self.sess = requests.Session()
        self.sess.headers["User-Agent"] = "riversrise-bake/1.0 (teaching sim)"
        self.imagery_cov = 0.0

    # ---------------- stage 1: terrain ------------------
    def bake_terrain(self):
        nx, nz, wid_m, hei_m = geo.grid_shape(self.bbox, self.cell_m)
        self.nx, self.nz = nx, nz
        self.wid_m, self.hei_m = wid_m, hei_m
        self.dx = wid_m / nx
        self.dz = hei_m / nz
        print(f"  grid {nx}×{nz} = {nx * nz / 1e6:.2f}M cells ({self.cell_m} m)")
        self.elev = demlib.fetch_grid(self.bbox, nx, nz, self.cache_dem, self.sess)
        print(f"  DEM range {np.nanmin(self.elev):.1f} … {np.nanmax(self.elev):.1f} m")
        self.bake_slope()

    def bake_slope(self):
        gx_, gy_ = np.gradient(self.elev.astype("float64"), self.dz, self.dx)
        # surface normal = normalize(−∂E/∂x, 1, +∂E/∂z): rows go south (z = hei/2 − j·dz)
        # so ∂E/∂z = −∂E/∂j⇒ with gy_ = ∂E/∂j, −∂E/∂z = gy_. Hence n = (−gx, 1, gy)/L.
        L = np.hypot(1.0, np.hypot(gx_, gy_))
        nxv = np.clip(np.rint(-gx_ / L * 100.0), -100, 100).astype("int8")
        nzv = np.clip(np.rint(gy_ / L * 100.0), -100, 100).astype("int8")
        self.slope_x = nxv
        self.slope_z = nzv

    # ---------------- stage 2: rivers -------------------
    def bake_rivers(self):
        rivers = riverslib.site_rivers(self.bbox, self.lat_c, self.site.RIVERS,
                                       self.cache_dem, self.sess)
        self.rivers_out = rivers
        cell_lists = []
        for r in rivers:
            cell_lists.append([
                ((x + self.wid_m / 2) / self.dx, (self.hei_m / 2 - z) / self.dz)
                for x, z in r["pts"]
            ])
        seeds = handlib.rasterize_streams(cell_lists, self.nx, self.nz, 2)
        self.seeds = seeds
        print(f"  rivers: {len(rivers)} lines ({sum(1 for r in rivers if r['src']=='approx')} approx), "
              f"{int(seeds.sum())} seed cells")

    # ---------------- stage 3: HAND ---------------------
    def bake_hand(self):
        elev_cm = np.rint(self.elev.astype("float64") * 100.0)
        self.origin_cm = int(np.floor(elev_cm.min())) - 4000  # pad 40 m bed
        self.elev_rel = (elev_cm - self.origin_cm).astype("int32")
        spill, outE = handlib.priority_flood(
            self.elev_rel, self.seeds,
            progress=(lambda f: print(f"    flood sweep {f:.0%}", flush=True)
                      if self.verbose else None),
        )
        self.thresh, self.outE = handlib.derived_arrays(self.elev_rel, spill, outE)
        g = self.thresh.astype("float32") / 100.0
        print(f"  HAND: min {g.min():.2f} m · median {np.median(g):.2f} m · "
              f"<2 m: {(g < 2).mean():.0%} of cells · "
              f">8 m: {(g > 8).mean():.0%}")

    # ---------------- stage 4: buildings ----------------
    def bake_buildings(self):
        records = []
        self.settle_mask = np.zeros((self.nz, self.nx), dtype=np.uint8)
        self.settle_scene = []
        for idx, sdef in enumerate(self.site.SETTLEMENTS):
            cx, cz = self.cell_of_lonlat(sdef["lon"], sdef["lat"])
            r_m = sdef.get("radius_m", SETTLE_R_INFORMAL_M if sdef.get("informal")
                           else SETTLE_R_FORMAL_M)
            cls = 0 if sdef.get("informal") else 1
            hh = HH_INFORMAL if cls == 0 else HH_FORMAL
            pop = sdef.get("pop") or 5_000
            need = max(1, int(round(pop / hh)))
            recs = self._synth_cluster(cx, cz, r_m, need, cls,
                                       1000003 * (idx + 1) + hash(sdef["name"]) % 9973,
                                       aspect=sdef.get("aspect", 1.0),
                                       deg=sdef.get("deg", 0.0))
            records.extend(recs)
            paint = self._paint_mask(cx, cz, r_m, cls, aspect=sdef.get("aspect", 1.0),
                                     deg=sdef.get("deg", 0.0))
            gi_c, gj_c = self.cell_index(cx, cz)
            self.settle_scene.append({
                "name": sdef["name"], "pop": pop,
                "informal": bool(sdef.get("informal")),
                "x": cx, "z": cz, "r_m": r_m,
                "aspect": sdef.get("aspect", 1.0), "deg": sdef.get("deg", 0.0),
                "mask_n": paint.get("n", 0),
                "thresh_med": paint.get("med", 0.0) / 100.0,   # stage metres
                "thresh_p10": paint.get("p10", 0.0) / 100.0,
                "elev": float(self.elev_rel[gj_c, gi_c]),
            })
            print(f"    cluster {sdef['name']}: {len(recs)}/{need} huts "
                  f"(pop≈{pop}) at r={r_m:.0f} m")
        # real footprints (best-effort), classified by nearest settlement
        real, src = fplib.fetch_features(self.bbox, self.cache_bld, self.sess,
                                         max_features=120_000)
        names = [s["name"] for s in self.site.SETTLEMENTS]
        cpts = np.array([
            self.cell_of_lonlat(s["lon"], s["lat"]) for s in self.site.SETTLEMENTS
        ], dtype="float64")
        informal_set = {n for n, s in zip(names, self.site.SETTLEMENTS)
                        if s.get("informal")}
        for geom in real:
            cx, cz = self.centroid_local(geom)
            if not (math.isfinite(cx) and math.isfinite(cz)):
                continue
            d = np.hypot(cx - cpts[:, 0], cz - cpts[:, 1])
            j = int(np.argmin(d))
            nm = names[j]
            if nm in informal_set:
                w_m, l_m, h_cm, hh = 5.6, 5.2, 300, HH_INFORMAL
                cls = 0
            else:
                w_m = l_m = math.sqrt(max(20.0, min(9_000.0, geom.area)))
                h_cm = 520
                hh = HH_FORMAL
                cls = 1
            records.append({"x": cx, "z": cz, "w": w_m, "l": l_m, "rot": 0.0,
                            "h_cm": h_cm, "class": cls, "hh": hh})
        # pack to instance arrays
        n = len(records)
        arr = np.zeros((n, 11), dtype="float32")
        for k, r in enumerate(records):
            gi, gj = self.cell_index(r["x"], r["z"])
            arr[k, 0] = r["x"]; arr[k, 1] = r["z"]
            arr[k, 2] = r["w"]; arr[k, 3] = r["l"]
            arr[k, 4] = r["rot"]; arr[k, 5] = r["h_cm"]
            arr[k, 6] = float(self.thresh[gj, gi])
            arr[k, 7] = float(self.outE[gj, gi])
            arr[k, 8] = float(self.elev_rel[gj, gi])
            arr[k, 9] = r["class"]
            arr[k, 10] = r["hh"]
        arr = arr[arr[:, 6] < 100_000]  # drop rows outside any drainage reach
        self.buildings = arr
        self.bldg_source = src or "procedural (pop-anchored clusters)"
        n_informal = int((arr[:, 9] == 0).sum())
        people = float((arr[:, 10]).sum())
        print(f"  buildings: {len(arr)} ({n_informal} informal), "
              f"est. pop {people / 1000:.0f} k, src={self.bldg_source[:40]}")

    def centroid_local(self, geom):
        """shapely polygon → local (x, z) meters."""
        if geom is None or geom.is_empty:
            return float("nan"), float("nan")
        p = geom.representative_point()
        return self.cell_of_lonlat(p.x, p.y)

    def _ellipse_u(self, dx, dz, deg):
        """Map local (dx, dz) into cluster-ellipse frame → (u, v) meters."""
        a = -math.radians(deg)
        co, si = math.cos(a), math.sin(a)
        ru = co * dx + si * dz
        rv = -si * dx + co * dz
        # ellipse semi-axes: keep area ≈ π r_m; long axis along u
        # aspect A: u-axis = r*sqrt(A), v-axis = r/sqrt(A)
        A = self._cur_aspect
        rx = math.sqrt(max(0.2, A)) * self._cur_radius
        ry = self._cur_radius / math.sqrt(max(0.2, A))
        return ru / rx, rv / ry, (ru, rv, rx, ry)

    def _synth_cluster(self, cx, cz, r_m, n_hh, cls, seed, aspect=1.0, deg=0.0):
        self._cur_radius = r_m
        self._cur_aspect = aspect
        rng = random.Random(seed)
        step = 21.0 if cls == 0 else 56.0
        span = int(r_m * max(1.0, math.sqrt(aspect)) / step) * 2 + 1
        recs = []
        for j in range(-span, span + 1):
            if len(recs) >= n_hh:
                break
            for i in range(-span, span + 1):
                if len(recs) >= n_hh:
                    break
                x = cx + (i + rng.uniform(-0.31, 0.31)) * step
                z = cz + (j + rng.uniform(-0.31, 0.31)) * step
                u, v, _ = self._ellipse_u(x - cx, z - cz, deg)
                if u * u + v * v > 1.0 or rng.random() > 0.86:
                    continue
                gi, gj = self.cell_index(x, z)
                s_ = abs(int(self.slope_x[gj, gi])) + abs(int(self.slope_z[gj, gi]))
                if s_ > 92:   # too steep for a hut
                    continue
                recs.append(self._box(rng, cls, x, z))
        # top-up inside radius if sparse
        while len(recs) < n_hh:
            ang = rng.uniform(0, 2 * math.pi)
            rr = math.sqrt(rng.random())
            u = math.cos(ang) * rr
            v = math.sin(ang) * rr
            A = max(0.2, aspect)
            rx = math.sqrt(A) * r_m
            ry = r_m / math.sqrt(A)
            a = -math.radians(deg)  # ellipse→world rotation
            dx = math.cos(a) * (u * rx) + math.sin(a) * (v * ry)
            dz = -math.sin(a) * (u * rx) + math.cos(a) * (v * ry)
            x, z = cx + dx, cz + dz
            recs.append(self._box(rng, cls, x, z))
        return recs[:n_hh]

    def _box(self, rng, cls, x, z):
        if cls == 0:
            return {"x": x, "z": z, "w": rng.uniform(3.4, 6.6),
                    "l": rng.uniform(3.2, 6.0), "rot": rng.uniform(0, math.pi),
                    "h_cm": int(rng.uniform(240, 400)), "class": 0,
                    "hh": HH_INFORMAL}
        return {"x": x, "z": z, "w": rng.uniform(7.0, 12.5),
                "l": rng.uniform(7.0, 12.0), "rot": rng.uniform(-0.08, 0.08),
                "h_cm": int(rng.uniform(300, 860)), "class": 1, "hh": HH_FORMAL}

    def _paint_mask(self, cx, cz, r_m, cls, aspect=1.0, deg=0.0):
        # fuzzy settlement ring for the blockage factor; skip stream cells
        ci = (cx + self.wid_m / 2) / self.dx
        cj = (self.hei_m / 2 - cz) / self.dz
        rx = r_m * math.sqrt(max(0.2, aspect)) / self.dx
        ry = r_m / math.sqrt(max(0.2, aspect)) / self.dz
        a = -math.radians(deg)
        co, si = math.cos(a), math.sin(a)
        i0, i1 = max(0, int(ci - rx * 1.1)), min(self.nx, int(ci + rx * 1.1) + 1)
        j0, j1 = max(0, int(cj - ry * 1.1)), min(self.nz, int(cj + ry * 1.1) + 1)
        if i1 - i0 < 2 or j1 - j0 < 2:
            return
        jj, ii = np.mgrid[j0:j1, i0:i1]
        xg = ii * self.dx - self.wid_m / 2
        zg = self.hei_m / 2 - jj * self.dz
        dxl = xg - cx
        dzl = zg - cz
        u = co * dxl + si * dzl
        v = -si * dxl + co * dzl
        dist2 = (u / (rx * self.dx)) ** 2 + (v / (ry * self.dz)) ** 2
        rng = np.random.default_rng((abs(int(ci * 73 + cz * 131)) % (2 ** 31)))
        noise = rng.random(dist2.shape)
        inside = dist2 + (noise - 0.5) * 0.5
        take = (inside < 1.0) & (noise > 0.10)
        take &= dist2 > 0.02          # leave the bank strip visually soft
        take &= self.thresh[j0:j1, i0:i1] > 6   # not on the stream cells
        vals = self.thresh[j0:j1, i0:i1][take]
        reg = self.settle_mask[j0:j1, i0:i1]
        val = 1 if cls == 0 else 2
        self.settle_mask[j0:j1, i0:i1] = np.where(take & (reg == 0), val, reg)
        if vals.size == 0:
            return {"n": 0}
        return {"n": int(vals.size),
                "min": float(vals.min()),
                "med": float(np.median(vals)),
                "p10": float(np.percentile(vals, 10))}

    def cell_index(self, x, z):
        gi = int(min(self.nx - 1, max(0, round((x + self.wid_m / 2) / self.dx))))
        gj = int(min(self.nz - 1, max(0, round((self.hei_m / 2 - z) / self.dz))))
        return gi, gj

    def cell_of_lonlat(self, lon, lat):
        x, z = geo.lonlat_to_local(lon, lat, self.bbox, self.wid_m, self.hei_m,
                                   self.lat_c)
        return x, z

    # ---------------- stage 5: roads --------------------
    def bake_roads(self):
        rs = roadslib.site_roads(self.bbox, self.lat_c,
                                 getattr(self.site, "ROADS", []), self.sess)
        self.roads = []
        for r in rs:
            m = len(r["pts"])
            fl = np.zeros((m, 6), dtype="float32")
            for k, (x, z) in enumerate(r["pts"]):
                gi, gj = self.cell_index(x, z)
                fl[k, 0] = x; fl[k, 1] = z
                fl[k, 2] = float(self.thresh[gj, gi])
                fl[k, 3] = float(self.outE[gj, gi])
                fl[k, 4] = float(self.elev_rel[gj, gi])
                fl[k, 5] = float(r["class"])
            length = float(np.hypot(np.diff(fl[:, 0]), np.diff(fl[:, 1])).sum())
            if length < 300:
                continue
            self.roads.append({"name": r["name"], "class": int(r["class"]),
                               "lines": fl, "len_m": length})
        km = sum(x["len_m"] for x in self.roads) / 1000.0
        print(f"  roads: {len(self.roads)} polylines · {km:.1f} km")

    # ---------------- stage 6: points -------------------
    def bake_points(self):
        self.facilities = []
        for f_ in self.site.FACILITIES:
            x, z = self.cell_of_lonlat(f_["lon"], f_["lat"])
            gi, gj = self.cell_index(x, z)
            self.facilities.append({
                "name": f_["name"], "k": f_["k"], "x": x, "z": z,
                "thresh": int(self.thresh[gj, gi]),
                "out": int(self.outE[gj, gi]),
                "elev": int(self.elev_rel[gj, gi]),
            })
        self.shelters = []
        for sdef in self.site.SETTLEMENTS:
            cx, cz = self.cell_of_lonlat(sdef["lon"], sdef["lat"])
            ci, cj = self.cell_index(cx, cz)
            rcell = int(min(40, (650 + 0.28 * math.sqrt(sdef.get("pop", 5000)))
                            / self.dx))
            best = None
            lo_i, hi_i = max(0, ci - rcell), min(self.nx, ci + rcell + 1)
            lo_j, hi_j = max(0, cj - rcell), min(self.nz, cj + rcell + 1)
            th_h = self.thresh[lo_j:hi_j, lo_i:hi_i]
            gy, gx = np.unravel_index(int(np.argmax(th_h)), th_h.shape)
            val = int(th_h[gy, gx])
            gi2, gj2 = lo_i + gx, lo_j + gy
            sx = gi2 * self.dx - self.wid_m / 2
            sz = self.hei_m / 2 - gj2 * self.dz
            lon, lat = geo.local_to_lonlat(sx, sz, self.bbox, self.lat_c)
            self.shelters.append({
                "name": f"High ground near {sdef['name']}",
                "x": sx, "z": sz, "lon": lon, "lat": lat,
                "thresh": val, "out": int(self.outE[gj2, gi2]),
                "elev": int(self.elev_rel[gj2, gi2]),
            })

    # ---------------- stage 7: imagery ------------------
    def bake_imagery(self):
        im, cov = imagerylib.fetch_mosaic(self.bbox, self.site.Z_TILE,
                                          session=self.sess)
        self.imagery_cov = cov
        self.root.mkdir(parents=True, exist_ok=True)
        p = self.root / "imagery.jpg"
        im.save(p, "JPEG", quality=74, optimize=True)
        print(f"  imagery: {im.size[0]}×{im.size[1]} px, coverage {cov:.0%}")

    # ---------------- stage 8: pack ---------------------
    def pack_all(self):
        self.root.mkdir(parents=True, exist_ok=True)
        selev = self._u16scale(self.elev_rel)
        sthresh = self._u16scale(self.thresh)
        sout = self._u16scale(self.outE)
        terrain_h = {
            "nx": self.nx, "nz": self.nz,
            "origin_cm": self.origin_cm,
            "scales": {"elev": selev[1], "thresh": sthresh[1], "out": sout[1]},
        }
        sections = {
            "elev": selev[0],
            "thresh": sthresh[0],
            "out": sout[0],
            "settle": self.settle_mask.tobytes(),
            "slope": np.concatenate([self.slope_x.astype("uint8").ravel(),
                                     self.slope_z.astype("uint8").ravel()]).tobytes(),
        }
        self._write_blob("terrain.bin", terrain_h, sections)

        bh = {"n": int(self.buildings.shape[0]), "layout": [
            "x", "z", "w", "l", "rot", "h_cm", "thresh", "out", "elev",
            "class", "hh"]}
        self._write_blob("buildings.bin", bh,
                         {"f": self.buildings.astype("float32").tobytes()})

        road_lines = {}
        payload = b""
        for k, r in enumerate(self.roads):
            road_lines[str(k)] = {"n": int(r["lines"].shape[0]),
                                  "name": r["name"], "class": r["class"]}
            payload += r["lines"].astype("float32").tobytes()
        self._write_blob("roads.bin",
                         {"n": len(self.roads), "lines": road_lines},
                         {"bin": payload})

        riv_lines = {}
        payload = b""
        for k, r in enumerate(self.rivers_out):
            fl = np.zeros((len(r["pts"]), 6), dtype="float32")
            for i_, (x, z) in enumerate(r["pts"]):
                gi, gj = self.cell_index(x, z)
                fl[i_, 0] = x; fl[i_, 1] = z
                fl[i_, 2] = float(self.thresh[gj, gi])
                fl[i_, 3] = float(self.outE[gj, gi])
                fl[i_, 4] = float(self.elev_rel[gj, gi])
                fl[i_, 5] = float(r.get("order", 4))
            riv_lines[str(k)] = {"n": int(fl.shape[0]), "name": r["name"],
                                 "order": int(r.get("order", 4))}
            payload += fl.tobytes()
        self._write_blob("rivers.bin", {"n": len(self.rivers_out),
                                        "lines": riv_lines}, {"bin": payload})

        manifest = {
            "site": self.slug,
            "name": self.site.NAME,
            "kicker": getattr(self.site, "KICKER", self.slug),
            "lede": self.site.LEDE,
            "river_label": self.site.RIVER_LABEL,
            "stage_note": self.site.STAGE_NOTE,
            "bbox": [float(v) for v in self.bbox],
            "nx": self.nx, "nz": self.nz,
            "dx": self.dx, "dz": self.dz,
            "wid_m": self.wid_m, "hei_m": self.hei_m,
            "origin_cm": self.origin_cm,
            "lat_c": self.lat_c,
            "stage_max": self.site.STAGE_MAX,
            "hist_marks": self.site.HIST_MARKS,
            "phases": self.site.PHASES,
            "scenarios": self.site.SCENARIOS,
            "cameras": self.site.CAMERAS,
            "settlements": [dict(s) for s in self.settle_scene],
            "facilities": self.facilities,
            "shelters": self.shelters,
            "road_manifest": [{"name": r["name"], "class": r["class"],
                               "len_m": round(r["len_m"], 1)}
                              for r in self.roads],
            "bldg_source": self.bldg_source,
            "imagery": ("esri" if self.imagery_cov > 0.9 else
                        "esri-partial" if self.imagery_cov > 0.2 else "none"),
            "attributions": {
                "imagery": imagerylib.ATTRIBUTION,
                "rivers": riverslib.ATTRIBUTION,
                "buildings": fplib.ATTRIBUTION,
                "roads": roadslib.ATTRIBUTION,
                "terrain": "Terrain © Copernicus GLO-30 (DLR/Airbus), Copernicus/ESA",
            },
            "info": self.site.INFO,
        }
        (self.root / "manifest.json").write_text(
            json.dumps(manifest, indent=1, ensure_ascii=False))
        total = sum(f_.stat().st_size for f_ in self.root.iterdir())
        for f_ in sorted(self.root.iterdir()):
            print(f"  out {f_.name}: {f_.stat().st_size / 1e6:.2f} MB")
        print(f"  ✓ {self.slug} baked — {total / 1e6:.1f} MB total")

    # -------- helpers --------
    def _u16scale(self, a):
        hi = float(np.max(a)) if np.size(a) else 0.0
        sc = 1
        for s in (1, 2, 4, 8, 16):
            if hi < 65535.0 * s:
                sc = s
                break
        return (np.clip(a / sc, 0, 65535).astype("uint16").tobytes(), sc)

    def _write_blob(self, name, header, sections):
        jbits = json.dumps({"h": header,
                            "s": {k: len(v) for k, v in sections.items()}},
                           separators=(",", ":")).encode("utf-8")
        payload = zlib.compress(b"".join(v for v in sections.values()), 6)
        # simple container: magic | u32 jsonLen | json | u32 binLen | zlib bin
        out = (b"WRRZ" + struct.pack("<I", len(jbits)) + jbits +
               struct.pack("<I", len(payload)) + payload)
        (self.root / name).write_bytes(out)

    def run(self):
        print(f"== baking {self.slug} ==")
        self.bake_terrain()
        self.bake_rivers()
        self.bake_hand()
        self.bake_buildings()
        self.bake_roads()
        self.bake_points()
        self.bake_imagery()
        self.pack_all()
