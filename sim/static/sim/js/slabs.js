// Exploded-view slab stack: terrain → drainage → susceptibility (HAND) →
// flood stage → buildings → response. Shares baked attributes; each slab is
// a flat plane whose shader colorizes per mode.
import * as THREE from "three";
import { makeSlabMaterial, makeLineMaterial, makeMarkerMaterial } from "./shaders.js";

const SNAMES = ["TERRAIN", "DRAINAGE", "SUSCEPTIBILITY (HAND)", "FLOOD STAGE",
  "BUILDINGS", "RESPONSE"];

export class Slabs {
  constructor(world) {
    this.man = world.man;
    this.group = new THREE.Group();
    world.root.add(this.group);
    this.group.visible = false;
    this.mats = [];
    this.lineMats = [];

    const kSep = this.man.site === "tana" ? 640 : 520;

    for (let k = 0; k < 6; k++) {
      const mat = makeSlabMaterial();
      mat.uniforms.uMode.value = k;
      const mesh = new THREE.Mesh(world.gridGeo, mat);
      mesh.position.y = -k * kSep;
      this.group.add(mesh);
      const title = makeTitle(SNAMES[k]);
      title.position.set(-this.man.wid_m / 2 - 320, -k * kSep + 40, 0);
      this.group.add(title);
      this.mats.push(mat);
    }

    // drainage slab: river lines
    for (const ln of world.data.rivers.lines) {
      const sh = flatLines(ln, -1 * kSep);
      this.group.add(sh.mesh);
      this.lineMats.push(sh.mat);
    }
    // flood slab: depth ramp handled by slab shader (uMode 3)

    // buildings slab: flat dots
    const b = world.data.buildings;
    const n = Math.min(b.n, 150000);
    const pg = new THREE.BufferGeometry();
    const pp = new Float32Array(n * 3);
    const pm = new Float32Array(n * 4);
    for (let i = 0; i < n; i++) {
      const r = i * 11;
      pp[i * 3] = b.a[r]; pp[i * 3 + 1] = -4 * kSep + 24; pp[i * 3 + 2] = b.a[r + 1];
      pm[i * 4] = b.a[r + 6] / 100;    // thresh (m)
      pm[i * 4 + 1] = 3;               // kind 3 = building dot
      pm[i * 4 + 2] = 42;              // world diameter
      pm[i * 4 + 3] = 1;
    }
    pg.setAttribute("position", new THREE.BufferAttribute(pp, 3));
    pg.setAttribute("aM", new THREE.BufferAttribute(pm, 4));
    const bmat = makeMarkerMaterial({ tint: "#caa269" });
    const bdots = new THREE.Points(pg, bmat);
    bdots.frustumCulled = false;
    this.group.add(bdots);
    this.mats.push(bmat);

    // response slab: major roads + shelters
    for (const ln of world.data.roads.lines) {
      if (ln.class > 1) continue;
      const sh = flatLines(ln, -5 * kSep);
      this.group.add(sh.mesh);
      this.lineMats.push(sh.mat);
    }
    const sp = world.man.shelters || [];
    if (sp.length) {
      const ng = new THREE.BufferGeometry();
      const np = new Float32Array(sp.length * 3);
      const nm = new Float32Array(sp.length * 4);
      sp.forEach((s, i) => {
        np[i * 3] = s.x; np[i * 3 + 1] = -5 * kSep + 90; np[i * 3 + 2] = s.z;
        nm[i * 4] = s.thresh / 100; nm[i * 4 + 1] = 1; nm[i * 4 + 2] = 420; nm[i * 4 + 3] = 1;
      });
      ng.setAttribute("position", new THREE.BufferAttribute(np, 3));
      ng.setAttribute("aM", new THREE.BufferAttribute(nm, 4));
      const smat = makeMarkerMaterial({ tint: "#3fae88" });
      const dots = new THREE.Points(ng, smat);
      dots.frustumCulled = false;
      this.group.add(dots);
      this.mats.push(smat);
    }
    this.kSep = kSep;
  }

  setStage(stage, blockage) {
    for (const m of this.mats) {
      if (m.uniforms.uStage) m.uniforms.uStage.value = stage;
      if (m.uniforms.uBlock) m.uniforms.uBlock.value = blockage;
      if (m.uniforms.uTime) m.uniforms.uTime.value = performance.now() / 1000;
    }
    for (const m of this.lineMats) {
      if (m.uniforms.uStage) m.uniforms.uStage.value = stage;
    }
  }

  setVisible(v) { this.group.visible = v; }

  // fade the stack in/out from below
  setSpread(spread) {
    this.group.position.y = (1 - spread) * -1400 + spread * 120;
  }
}

function makeTitle(text) {
  const c = document.createElement("canvas");
  c.width = 512; c.height = 96;
  const g = c.getContext("2d");
  g.fillStyle = "rgba(16,20,17,0.9)";
  g.beginPath();
  g.roundRect(0, 12, 512, 72, 16);
  g.fill();
  g.fillStyle = "#e8ecdf";
  g.font = "650 32px system-ui, sans-serif";
  g.fillText(text, 26, 58);
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, depthTest: false }));
  sp.scale.set(520, 98, 1);
  return sp;
}

function flatLines(ln, y) {
  const { f, m } = ln;
  const rows = m - 1;
  const pos = new Float32Array(rows * 2 * 3);
  const ay = new Float32Array(rows * 2);
  const af = new Float32Array(rows * 2 * 3);
  for (let s = 0; s < rows; s++) {
    for (let e2 = 0; e2 < 2; e2++) {
      const vi = s + e2;
      const r = vi * 6;
      pos[(s * 2 + e2) * 3] = f[r];
      pos[(s * 2 + e2) * 3 + 1] = 0;
      pos[(s * 2 + e2) * 3 + 2] = f[r + 1];
      ay[s * 2 + e2] = y + 22;
      af[(s * 2 + e2) * 3] = f[r + 2] / 100;
      af[(s * 2 + e2) * 3 + 1] = f[r + 3] / 100;
      af[(s * 2 + e2) * 3 + 2] = f[r + 5];
    }
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  geo.setAttribute("aY", new THREE.BufferAttribute(ay, 1));
  geo.setAttribute("aF", new THREE.BufferAttribute(af, 3));
  const mat = makeLineMaterial({ col: "#4fd4a9", wet: "#e2573f", opacity: 0.95 });
  mat.uniforms.uFogCol.value = new THREE.Color("#20241f");
  mat.uniforms.uFogD.value = 0.00002;
  const mesh = new THREE.LineSegments(geo, mat);
  return { mesh, mat };
}
