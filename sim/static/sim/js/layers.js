// World assembly: builds every 3D layer for a site from loaded data.
// All positioning in LOCAL METERS (x east, z north-up-negative? z = north).
import * as THREE from "three";
import * as S from "./state.js";
import {
  makeTerrainMaterial, makeWaterMaterial, makeBuildingsMaterial,
  makeLineMaterial, makeMarkerMaterial,
} from "./shaders.js";

const STRIDE = { nairobi: 2, tana: 3 };
const FOGC = "#232a26";
const FOGD = 0.000045;

function decU8(v) { return v > 127 ? v - 256 : v; }
function max0(v) { return Math.max(0, v); }

export class World {
  constructor(scene, data) {
    this.data = data;
    this.man = data.manifest;
    const T = data.terrain;
    this.stride = STRIDE[this.man.site] || 2;

    this.root = new THREE.Group();               // everything inside
    this.root.scale.y = this.man.site === "tana" ? 4.2 : 2.0;
    scene.add(this.root);

    this._buildGridGeometries(T);
    this._buildTerrain();
    this._buildWater();
    this._buildBuildings();
    this._buildLines();
    this._buildMarkers();
    this._buildPlinth();

    // settlement flood-fraction bookkeeping for response UI
    this._settleRegions = this._buildSettleRegions();
  }

  // ------------------------------------------------------------------ grids
  _buildGridGeometries(T) {
    const st = this.stride;
    const nx = this.man.nx, nz = this.man.nz;
    const nFull = nx * nz;
    const nx2 = Math.floor((nx - 1) / st) + 1;
    const nz2 = Math.floor((nz - 1) / st) + 1;
    this.nx2 = nx2; this.nz2 = nz2;

    const count = nx2 * nz2;
    const pos = new Float32Array(count * 3);
    const elev = new Float32Array(count);
    const thresh = new Float32Array(count);
    const out = new Float32Array(count);
    const settle = new Float32Array(count);
    const slopeXY = new Float32Array(count * 2);
    const cellUv = new Float32Array(count * 2);
    const dx = this.man.dx, dz = this.man.dz;
    let k = 0;
    for (let j = 0; j < nz2; j++) {
      const jj = j * st;
      const z = this.man.hei_m / 2 - jj * dz;
      const v = 1 - (jj / (nz - 1));
      for (let i = 0; i < nx2; i++) {
        const ii = i * st;
        const idx = jj * nx + ii;
        const x = ii * dx - this.man.wid_m / 2;
        const u = ii / (nx - 1);
        pos[k * 3] = x; pos[k * 3 + 1] = 0; pos[k * 3 + 2] = z;
        elev[k] = T.elevM[idx];
        thresh[k] = T.threshM[idx];
        out[k] = T.outM[idx];
        settle[k] = T.settleU8[idx];
        const sx = decU8(T.slopeU8[idx]);
        const sz = decU8(T.slopeU8[nFull + idx]);
        slopeXY[k * 2] = sx; slopeXY[k * 2 + 1] = sz;
        cellUv[k * 2] = u; cellUv[k * 2 + 1] = v;
        k++;
      }
    }
    // indices (two triangles per quad)
    const q = (nx2 - 1) * (nz2 - 1);
    const inds = new Uint32Array(q * 6);
    let p = 0;
    for (let j = 0; j < nz2 - 1; j++) {
      for (let i = 0; i < nx2 - 1; i++) {
        const a = j * nx2 + i, b = a + 1, c = a + nx2, d = c + 1;
        inds[p++] = a; inds[p++] = c; inds[p++] = b;
        inds[p++] = b; inds[p++] = c; inds[p++] = d;
      }
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    geo.setIndex(new THREE.BufferAttribute(inds, 1));
    geo.setAttribute("aElev", new THREE.BufferAttribute(elev, 1));
    geo.setAttribute("aThresh", new THREE.BufferAttribute(thresh, 1));
    geo.setAttribute("aOut", new THREE.BufferAttribute(out, 1));
    geo.setAttribute("aSettle", new THREE.BufferAttribute(settle, 1));
    geo.setAttribute("aSlope", new THREE.BufferAttribute(slopeXY, 2));
    geo.setAttribute("aCellUv", new THREE.BufferAttribute(cellUv, 2));
    this.gridGeo = geo;

    // water mesh uses the SAME per-vertex data but drawn only where wet
    const wgeo = new THREE.BufferGeometry();
    wgeo.setAttribute("position", new THREE.BufferAttribute(pos.slice(), 3));
    wgeo.setIndex(geo.index);
    wgeo.setAttribute("aElev", geo.attributes.aElev);
    wgeo.setAttribute("aThresh", geo.attributes.aThresh);
    wgeo.setAttribute("aOut", geo.attributes.aOut);
    wgeo.setAttribute("aSettle", geo.attributes.aSettle);
    wgeo.setAttribute("aCellUv", geo.attributes.aCellUv);
    this.waterGeo = wgeo;
  }

  _buildTerrain() {
    const loader = new THREE.TextureLoader();
    const tex = this.data.imageryUrl
      ? loader.load(this.data.imageryUrl, (tl) => { tl.colorSpace = THREE.SRGBColorSpace; })
      : null;
    this.terrainMat = makeTerrainMaterial(tex);
    const mesh = new THREE.Mesh(this.gridGeo, this.terrainMat);
    this.root.add(mesh);
    this.terrainMat.uniforms.uFogCol.value = new THREE.Color(FOGC);
    this.terrainMat.uniforms.uFogD.value = FOGD;
    this.terrainMesh = mesh;
  }

  _buildWater() {
    this.waterMat = makeWaterMaterial();
    this.waterMat.uniforms.uFogCol.value = new THREE.Color(FOGC);
    this.waterMat.uniforms.uFogD.value = FOGD;
    this.waterMesh = new THREE.Mesh(this.waterGeo, this.waterMat);
    this.waterMesh.frustumCulled = false;
    this.root.add(this.waterMesh);
  }

  _buildBuildings() {
    const b = this.data.buildings;
    const n = b.n;
    if (!n) { this.bldgMesh = null; return; }
    const box = new THREE.BoxGeometry(1, 1, 1);
    const geo = new THREE.InstancedBufferGeometry();
    geo.index = box.index;
    geo.attributes.position = box.attributes.position;
    geo.attributes.normal = box.attributes.normal;
    const iPos = new Float32Array(n * 3);
    const iDim = new Float32Array(n * 4);
    const iHand = new Float32Array(n * 3);
    for (let i = 0; i < n; i++) {
      const r = i * 11;
      iPos[i * 3] = b.a[r + 0];
      iPos[i * 3 + 1] = b.a[r + 1];
      iPos[i * 3 + 2] = b.a[r + 4];
      iDim[i * 4] = b.a[r + 2];
      iDim[i * 4 + 1] = b.a[r + 3];
      iDim[i * 4 + 2] = b.a[r + 5] / 100;      // cm→m
      iDim[i * 4 + 3] = b.a[r + 9];
      iHand[i * 3] = b.a[r + 6] / 100;
      iHand[i * 3 + 1] = b.a[r + 7] / 100;
      iHand[i * 3 + 2] = b.a[r + 8] / 100;
    }
    geo.setAttribute("iPos", new THREE.InstancedBufferAttribute(iPos, 3));
    geo.setAttribute("iDim", new THREE.InstancedBufferAttribute(iDim, 4));
    geo.setAttribute("iHand", new THREE.InstancedBufferAttribute(iHand, 3));
    geo.instanceCount = n;
    this.bldgMat = makeBuildingsMaterial();
    this.bldgMat.uniforms.uFogCol.value = new THREE.Color(FOGC);
    this.bldgMat.uniforms.uFogD.value = FOGD;
    this.bldgMesh = new THREE.Mesh(geo, this.bldgMat);
    this.bldgMesh.frustumCulled = false;
    this.root.add(this.bldgMesh);
  }

  _buildLines() {
    this.roadGroup = new THREE.Group();
    this.root.add(this.roadGroup);
    this.roadMats = [];
    this.roadSegs = [];
    for (const ln of this.data.roads.lines) {
      this._addPolyline(ln, this.roadGroup, {
        col: clsColor(ln.class),
        wet: "#d94330",
        opacity: ln.class >= 2 ? 0.8 : 1.0,
      });
    }
    this.riverMats = [];
    this.riverGroup = new THREE.Group();
    this.root.add(this.riverGroup);
    for (const ln of this.data.rivers.lines) {
      this._addPolyline(ln, this.riverGroup, {
        col: "#3f8f9e", wet: "#57b3c8", opacity: Math.min(0.85, 0.45 + ln.order * 0.05),
      });
    }
  }

  _addPolyline(ln, group, style) {
    const { f, m } = ln;
    const rows = m - 1;                       // segments
    const pos = new Float32Array(rows * 2 * 3);
    const ay = new Float32Array(rows * 2);
    const af = new Float32Array(rows * 2 * 3);
    for (let s = 0; s < rows; s++) {
      for (let e2 = 0; e2 < 2; e2++) {
        const vi = s + e2;
        const r = vi * 6;
        const y = f[r + 4] + 0.35;
        pos[(s * 2 + e2) * 3] = f[r];
        pos[(s * 2 + e2) * 3 + 1] = 0;
        pos[(s * 2 + e2) * 3 + 2] = f[r + 1];
        ay[s * 2 + e2] = y;
        af[(s * 2 + e2) * 3] = f[r + 2];
        af[(s * 2 + e2) * 3 + 1] = f[r + 3];
        af[(s * 2 + e2) * 3 + 2] = f[r + 5];
      }
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    geo.setAttribute("aY", new THREE.BufferAttribute(ay, 1));
    geo.setAttribute("aF", new THREE.BufferAttribute(af, 3));
    const mat = makeLineMaterial(style);
    mat.uniforms.uFogCol.value = new THREE.Color(FOGC);
    mat.uniforms.uFogD.value = FOGD;
    const seg = new THREE.LineSegments(geo, mat);
    group.add(seg);
    if (group === this.roadGroup) {
      this.roadMats.push(mat);
      this.roadSegs.push(geo);
    } else {
      this.riverMats.push(mat);
    }
  }

  // ------------------------------------------------------------------ points
  _buildMarkers() {
    // shelters: green pulse; facilities: tints by kind; no-go splats: red halo
    this.shelterPts = this._makePoints(this.man.shelters, "#e8f4ec", 4, 1);
    this.facilPts = this._makePoints(this.man.facilities, "#f2ecdf", 3.4, 0);
    this.splatPts = this._makeSplats();
  }

  _makePoints(list, tint, worldD, kind) {
    const n = list?.length || 0;
    if (!n) return null;
    const pos = new Float32Array(n * 3);
    const aM = new Float32Array(n * 4);
    for (let i = 0; i < n; i++) {
      const r = list[i];
      pos[i * 3] = r.x;
      pos[i * 3 + 1] = (r.elev ?? 0) / 100 + (kind === 1 ? 2.4 : 1.6);  // cm→m + lift
      pos[i * 3 + 2] = r.z;
      aM[i * 4] = (r.thresh ?? 0) / 100;     // cm → stage metres
      aM[i * 4 + 1] = kind;
      aM[i * 4 + 2] = worldD;                // world diameter (m)
      aM[i * 4 + 3] = 1.0;                   // seen (phase gate at runtime)
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    geo.setAttribute("aM", new THREE.BufferAttribute(aM, 4));
    const mat = makeMarkerMaterial({ tint });
    const pts = new THREE.Points(geo, mat);
    pts.frustumCulled = false;
    this.root.add(pts);
    return { pts, mat, list, aM };
  }

  _makeSplats() {
    // one soft red halo per settlement; brightness ~ flooded mask share
    const list = this.man.settlements || [];
    const n = list.length;
    const pos = new Float32Array(n * 3);
    const aM = new Float32Array(n * 4);
    for (let i = 0; i < n; i++) {
      const s = list[i];
      pos[i * 3] = s.x;
      pos[i * 3 + 1] = (s.elev ?? 0) / 100 + 3.5;    // cm→m + lift above ground
      pos[i * 3 + 2] = s.z;
      aM[i * 4] = (s.thresh_p10 ?? s.thresh_med ?? 0) * 100 / 100;  // stage metres
      aM[i * 4 + 1] = 2;                              // kind 2 = splat
      aM[i * 4 + 2] = 2.5 * (s.r_m ?? 900);           // world diameter ≈ ellipse span
      aM[i * 4 + 3] = 1.0;
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    geo.setAttribute("aM", new THREE.BufferAttribute(aM, 4));
    const mat = makeMarkerMaterial({ tint: "#d8552e" });
    const pts = new THREE.Points(geo, mat);
    pts.frustumCulled = false;
    this.root.add(pts);
    return { pts, mat, list, aM };
  }

  _buildSettleRegions() {
    // Per settlement: full-res mask cell indices (for flooded-fraction stats).
    const T = this.data.terrain;
    const nx = this.man.nx, nz = this.man.nz;
    const regions = (this.man.settlements || []).map((s) => {
      const cells = [];
      const rx = Math.max(3, Math.round((s.r_m * Math.sqrt(Math.max(0.2, s.aspect || 1))) / this.man.dx));
      const ry = Math.max(3, Math.round((s.r_m / Math.sqrt(Math.max(0.2, s.aspect || 1))) / this.man.dz));
      const gi0 = Math.round((s.x + this.man.wid_m / 2) / this.man.dx);
      const gj0 = Math.round((this.man.hei_m / 2 - s.z) / this.man.dz);
      const a = -(s.deg || 0) * Math.PI / 180;
      const co = Math.cos(a), si = Math.sin(a);
      for (let jj = max0(gj0 - ry); jj < Math.min(nz, gj0 + ry + 1); jj++) {
        for (let ii = max0(gi0 - rx); ii < Math.min(nx, gi0 + rx + 1); ii++) {
          const x = ii * this.man.dx - this.man.wid_m / 2 - s.x;
          const z = this.man.hei_m / 2 - jj * this.man.dz - s.z;
          const du = co * x + si * z;
          const dv = -si * x + co * z;
          const ud = du / (rx * this.man.dx);
          const vd = dv / (ry * this.man.dz);
          if (ud > 1.2 || vd > 1.2) continue;
          const idx = jj * nx + ii;
          if (T.settleU8[idx]) cells.push(idx);
        }
      }
      return { name: s.name, cells: new Uint32Array(cells) };
    });
    return regions;
  }

  _buildPlinth() {
    // dark slab under the diorama edges
    const minE = Math.min(...this.data.terrain.elevM) ?? 0;
    const H = 420;
    const top = Math.min(minE - 6, -2);
    const W = this.man.wid_m * 1.03, D = this.man.hei_m * 1.03;
    const geo = new THREE.BoxGeometry(W, H, D);
    const mat = new THREE.MeshBasicMaterial({ color: 0x161a17 });
    const box = new THREE.Mesh(geo, mat);
    box.position.y = top - H / 2;
    box.renderOrder = -1;
    this.root.add(box);
  }

  // ------------------------------------------------------------------ update
  setLayers(l) {
    this.layers = { ...l };
    if (this.bldgMesh) this.bldgMesh.visible = l.city || l.response || l.hand;
    this.terrainMat.uniforms.uHeatA.value = l.hand ? 0.92 : 0.0;
    if (this.facilPts) this.facilPts.pts.visible = l.city || l.response;
    if (this.shelterPts) this.shelterPts.pts.visible = l.response;
    if (this.splatPts) this.splatPts.pts.visible = l.response;
  }

  update(stage) {
    const st = S.state;
    const blockage = st.scenarioBlockage ?? 1;
    for (const mat of [
      this.terrainMat, this.waterMat, ...(this.bldgMat ? [this.bldgMat] : []),
      ...this.roadMats, ...this.riverMats, ...(this.facilPts ? [this.facilPts.mat] : []),
      ...(this.shelterPts ? [this.shelterPts.mat] : []),
      ...(this.splatPts ? [this.splatPts.mat] : []),
    ]) {
      if (mat.uniforms.uStage) mat.uniforms.uStage.value = stage;
      if (mat.uniforms.uBlock) mat.uniforms.uBlock.value = blockage;
      if (mat.uniforms.uTime) mat.uniforms.uTime.value = performance.now() / 1000;
    }
    // marker "seen" gates by phase
    const phase = phaseIndex(stage, this.man.phases);
    if (this.shelterPts) {
      const active = phase >= 2 ? 1 : 0;          // Mobilize → shelters show
      const aM = this.shelterPts.aM;
      for (let i = 0; i < this.man.shelters.length; i++) aM[i * 4 + 3] = active;
      this.shelterPts.pts.geometry.attributes.aM.needsUpdate = true;
      this.shelterPts.pts.visible = st.layers.response && !!active;
    }
  }

  stats(stage) {
    const b = this.data.buildings;
    const n = b.n;
    let wetB = 0, people = 0;
    const a = b.a;
    for (let i = 0; i < n; i++) {
      const r = i * 11;
      const classIn = a[r + 9];
      const block = classIn < 0.5 ? (S.state.scenarioBlockage ?? 1) : 1;
      const thresh = a[r + 6] / 100 * block;       // baked cm → stage metres
      if (thresh < stage) { wetB++; people += a[r + 10]; }
    }
    // roads (segments cut): both endpoints under stage
    let cutM = 0;
    for (const ln of this.data.roads.lines) {
      const f = ln.f, m = ln.m;
      for (let s = 0; s < m - 1; s++) {
        const i1 = s * 6, i2 = (s + 1) * 6;
        if (f[i1 + 2] / 100 < stage && f[i2 + 2] / 100 < stage) {
          cutM += Math.hypot(f[i2] - f[i1], f[i2 + 1] - f[i1 + 1]);
        }
      }
    }
    let facil = 0;
    for (const fa of this.man.facilities) if (fa.thresh / 100 < stage) facil++;
    return { wetB, people, cutKm: cutM / 1000.0, facil };
  }
}

function clsColor(cls) {
  return ["#efe6d8", "#cfd6cd", "#a8b3ac", "#8f9a94"][cls] ?? "#9aa6a0";
}

function phaseIndex(stage, phases) {
  let idx = 0;
  (phases || []).forEach((p, i) => { if (stage >= p.stage) idx = i; });
  return idx;
}
