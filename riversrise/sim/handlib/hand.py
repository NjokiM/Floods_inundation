"""HAND (Height Above Nearest Drainage) via priority-flood.

Model semantics baked per cell:
  - `thresh_cm`  : the stage s (cm above the stream level) at which this cell
                   becomes reachable by water — spill level minus the elevation
                   of the stream outlet cell it drains to.
  - `out_cm`     : elevation (cm) of that outlet stream cell. Once flooding
                   starts, the water surface sits at out_cm + s.

Algorithm (bucket priority-flood from stream seeds):
  seeds: rasterized stream cells, spill = own elevation.
  pop lowest-spill cell u; for each unvisited 8-neighbor v:
      spill_v = max(spill_u, E[v])    (water must clear the whole path)
      first visit wins (lowest-barrier path) → spill[v], outE[v] = outE[u].
  thresh[v] = spill[v] − outE[v] ≥ 0.
  Flat floodplains thus bake in their bank-vs-plain offset; land behind a levee
  inherits the barrier height as its threshold — topographically honest.

Grid rows run north→south (row 0 = NORTH), matching dem.py/geo.py. All values
integer centimetres relative to the site elevation origin (computed by caller).
The hot loop runs on nested Python lists (≈5–10× faster than numpy element
access); numpy only at the edges.
"""
import numpy as np

_NEIGHBORS = ((-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1),
              (1, -1), (1, 0), (1, 1))


def rasterize_streams(cell_xz_lists, nx, nz, width_cells=2):
    """Draw river centerlines (FRATIONAL CELL coordinates) into a bool mask.

    cell_xz_lists: iterable of polylines of (col, row) float cell coords, where
    col i ↔ x = i (east→), row j ↔ z (row 0 = north edge).
    """
    H, W = nz, nx
    mask = np.zeros((H, W), dtype=bool)
    r = max(1, int(width_cells))
    for pts in cell_xz_lists:
        for (gx0, gz0), (gx1, gz1) in zip(pts[:-1], pts[1:]):
            n = int(max(abs(gx1 - gx0), abs(gz1 - gz0)) * 2) + 1
            for t in range(n + 1):
                f = t / n
                xi = int(round(gx0 + (gx1 - gx0) * f))
                zi = int(round(gz0 + (gz1 - gz0) * f))
                if 0 <= xi < W and 0 <= zi < H:
                    mask[max(0, zi - r):min(H, zi + r + 1),
                         max(0, xi - r):min(W, xi + r + 1)] = True
    return mask


def priority_flood(elev_cm, seed_mask, progress=None):
    """spill/outE int32 grids [nz, nx], cm relative to caller's datum."""
    nz, nx = elev_cm.shape
    E = elev_cm.tolist()                      # nested python ints (fast)
    visited = np.zeros((nz, nx), dtype=bool)

    sy, sx = np.nonzero(seed_mask)
    if sy.size == 0:
        raise ValueError("priority_flood: empty seed mask")

    spill = elev_cm.astype(np.int32).copy()
    outE = elev_cm.astype(np.int32).copy()
    S = spill.tolist()
    O = outE.tolist()

    lo = int(min(min(e) for e in E))          # bucket keys relative to min
    hi = int(max(max(e) for e in E))
    nbuckets = hi - lo + 1
    buckets = [None] * (nbuckets + 2)

    def queue(idx, key_rel):
        b = buckets[key_rel]
        if b is None:
            buckets[key_rel] = [idx]
        else:
            b.append(idx)

    min_seed = 10 ** 9
    sy_l, sx_l = sy.tolist(), sx.tolist()
    for y, x in zip(sy_l, sx_l):
        idx = y * nx + x
        visited[y, x] = True
        eb = E[y][x]
        if eb < min_seed:
            min_seed = eb
        queue(idx, eb - lo)

    ptr = min_seed - lo
    done = 0
    total = nz * nx
    visited_list = visited  # numpy row lookup is fine (fast ndarray indexing)
    nb = _NEIGHBORS
    while ptr <= nbuckets:
        drawer = buckets[ptr]
        buckets[ptr] = None
        if not drawer:
            ptr += 1
            continue
        i = 0
        while i < len(drawer):
            idx = drawer[i]
            i += 1
            y, x = divmod(idx, nx)
            s_u = S[y][x]
            o_u = O[y][x]
            for dy, dx in nb:
                vy = y + dy
                vx = x + dx
                if vy < 0 or vy >= nz or vx < 0 or vx >= nx:
                    continue
                if visited_list[vy, vx]:
                    continue
                visited_list[vy, vx] = True
                ev = E[vy][vx]
                s_v = (s_u if s_u > ev else ev)
                S[vy][vx] = s_v
                O[vy][vx] = o_u
                key = s_v - lo
                if key <= ptr:                 # same-level wave: consume in this scan
                    drawer.append(vy * nx + vx)
                else:
                    b = buckets[key]
                    if b is None:
                        buckets[key] = [vy * nx + vx]
                    else:
                        b.append(vy * nx + vx)
            done += 1
            if progress and (done & 0x3FFFF) == 0:
                progress(done / total)
        ptr += 1

    spill = np.asarray(S, dtype=np.int32)
    outE = np.asarray(O, dtype=np.int32)
    never = ~visited
    spill[never] = 1_000_000
    return spill, outE


def derived_arrays(elev_cm, spill, outE):
    """(thresh_cm uint32, out_cm int32) — packer downstream handles scaling."""
    thresh = spill.astype(np.int64) - outE.astype(np.int64)
    thresh = np.clip(thresh, 0, 2_000_000).astype(np.uint32)
    return thresh, outE.astype(np.int32)
