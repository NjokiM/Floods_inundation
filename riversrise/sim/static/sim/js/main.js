// Boot + frame loop + lifecycle. No framework — plain ES modules.
import * as THREE from "three";
import { Viewer } from "./scene.js";
import { World } from "./layers.js";
import { Slabs } from "./slabs.js";
import { state, set, on, cacheSiteData, siteData } from "./state.js";
import { loadSite } from "./loader.js";
import { initUI, refreshUI, setHint } from "./ui.js";
import { loadLive } from "./live.js";

const host = document.getElementById("world");
const loading = document.getElementById("loading");

const FOG_LAB = "#232a26";
const FOG_STUDIO = "#d9dfdd";

let viewer = null;
let world = null;
let slabs = null;
let uiHooks = null;       // { stats(stats, stage) }
let lastStage = -1;
let spread = 0;

let flyAnim = null;
function flyTo(pose, secs = 1.4) {
  if (!viewer) return;
  flyAnim = {
    p0: viewer.camera.position.clone(), p1: pose.pos.clone(),
    t0: viewer.controls.target.clone(), t1: pose.target.clone(),
    start: performance.now(), secs: secs * 1000,
  };
}
function tickFly() {
  if (!flyAnim) return;
  let k = (performance.now() - flyAnim.start) / flyAnim.secs;
  if (k >= 1) k = 1;
  const e = 1 - Math.pow(1 - k, 3);
  viewer.camera.position.lerpVectors(flyAnim.p0, flyAnim.p1, e);
  viewer.controls.target.lerpVectors(flyAnim.t0, flyAnim.t1, e);
  if (k === 1) flyAnim = null;
}

// ---------------------------------------------------------- camera presets
function presetPose(man, cam, y0 = 0) {
  const x = (cam.lon - (man.bbox[0] + man.bbox[2]) / 2) *
    (111320 * Math.cos(man.lat_c * Math.PI / 180));
  const z = (cam.lat - (man.bbox[1] + man.bbox[3]) / 2) * 110574;
  const pitch = (cam.pitch ?? 55) * Math.PI / 180;
  const dist = (cam.alt ?? 8000) * 2.5;
  const az = (cam.az ?? -215) * Math.PI / 180;
  const dxz = Math.cos(pitch) * dist;
  return {
    target: new THREE.Vector3(x, y0, z),
    pos: new THREE.Vector3(
      x - dxz * Math.sin(az),
      (man.site === "tana" ? 4.2 : 2.0) * Math.sin(pitch) * dist,
      z + dxz * Math.cos(az)),
  };
}
function stackPose() {
  const man = siteData()?.manifest;
  if (!man) return null;                          // was an unguarded man.site deref
  const vv = man.site === "tana" ? 4.2 : 2.0;     // vertical exaggeration (was dead)
  return {
    target: new THREE.Vector3(0, -3 * 520 * 0.5, 0),
    pos: new THREE.Vector3(man.wid_m * 0.62, vv * 13500, -man.hei_m * 0.42 - 3000),
  };
}

// ---------------------------------------------------------- scenario play
const PLAY_SECS = { nairobi: 15, tana: 26 };

function sampleCurve(curve, t) {
  if (t <= curve[0][0]) return curve[0][1];
  for (let i = 1; i < curve.length; i++) {
    if (t <= curve[i][0]) {
      const [ta, va] = curve[i - 1], [tb, vb] = curve[i];
      const f = (t - ta) / Math.max(1e-6, tb - ta);
      return va + (vb - va) * f;
    }
  }
  return curve[curve.length - 1][1];
}

function scenarioOf(man) {
  return (man.scenarios || []).find((s) => s.id === state.scenario) ||
    (man.scenarios || [])[0] || { curve: [[0, 0], [1, 0]], blockage: 1 };
}

let lastStats = null;
function advancePlay(dtMs) {
  const man = siteData()?.manifest;
  if (!man || !state.playing) return;
  const scen = scenarioOf(man);
  const dur = (PLAY_SECS[state.site] || 16) * 1000;
  state.playT = Math.min(1.0001, state.playT + dtMs / dur);
  const f = sampleCurve(scen.curve, Math.min(1, state.playT));
  set({ stage: +(f * man.stage_max).toFixed(2) });
  if (state.playT >= 1) {
    set({ playing: false });
    if (uiHooks) setPlayBtn(false);
  }
  refreshUI();
}

function setPlayBtn(playing) {
  const p = document.getElementById("play");
  if (!p) return;
  p.setAttribute("aria-pressed", String(playing));
  document.getElementById("playPath").setAttribute("d", playing
    ? "M7 5.5h4v13H7zM13 5.5h4v13h-4z"
    : "M8 5.5v13l10.5-6.5z");
}

// ---------------------------------------------------------- frame loop
function onFrame(hi) {
  requestAnimationFrame(() => onFrame());
  if (!viewer || !world) return;
  const dt = viewer.clock.getDelta() * 1000;
  advancePlay(dt);
  tickFly();

  const want = state.view === "exploded" ? 1 : 0;
  spread += (want - spread) * Math.min(1, dt / 380);
  if (Math.abs(want - spread) < 0.005) spread = want;
  if (slabs) {
    const on = spread > 0.008 || state.view === "exploded";
    slabs.setVisible(on);
    slabs.setSpread(spread);
  }
  world.root.visible = !(state.view === "exploded" && spread > 0.92);
  world.update(state.stage);

  // setStage also refreshes the slabs' uTime, so it has to run every frame. It
  // used to sit inside the stage-change guard, which froze the slab pulses
  // whenever the stage was static (e.g. parked in exploded view).
  slabs?.setStage(state.stage, state.scenarioBlockage ?? 1.0);
  if (state.stage !== lastStage) {
    const stats = world.stats(state.stage);
    uiHooks?.stats?.(siteData()?.manifest, stats, state.stage);
    lastStage = state.stage;
  }
  viewer.render();
}

// ---------------------------------------------------------- lifecycle
function showFatal(err) {
  loading.classList.remove("off");
  loading.innerHTML =
    `<b style="color:#e2573f">This scene failed to load.</b><br>` +
    `<span style="opacity:.72;font-size:.85rem">${String(err?.message || err)}</span>`;
}

async function boot() {
  // Without this catch, ANY failure (unbaked site, shader compile error, stack
  // overflow in World) rejected boot() silently: onFrame() never ran, render()
  // was never called, and the overlay sat on "Filling the valley…" forever with
  // a blank screen and nothing to explain it.
  try {
    viewer = new Viewer(host);
    await switchSite(state.site, true);
  } catch (err) {
    console.error("[riversrise] boot failed:", err);
    showFatal(err);
    return;
  }
  loading.classList.add("off");
  onFrame();

  // keyboard: handled in ui.js; play button icon synced when scenario ends
  on("playing", (v) => setPlayBtn(v));
}

async function switchSite(site, first = false) {
  loading.classList.remove("off");

  // Load BEFORE tearing anything down. The old order disposed the working world
  // first, so a failed fetch (e.g. a site with no baked data) left a blank screen
  // with no way back short of a full reload.
  const keepSite = world?.man?.site ?? null;
  let data;
  try {
    data = siteData(site) || await loadSite(site);
  } catch (err) {
    console.error(`[riversrise] could not load site "${site}":`, err);
    // direct write, not set(): set() would re-fire on("site") and recurse
    if (keepSite) state.site = keepSite;
    setHint(`could not load ${site} — is its data baked?`, 4200);
    loading.classList.add("off");
    throw err;
  }
  cacheSiteData(site, data);

  if (world) {
    world.root.traverse((o) => {
      if (o.geometry) o.geometry.dispose();
      if (o.material) (Array.isArray(o.material) ? o.material : [o.material])
        .forEach((m) => { m?.map?.dispose?.(); m?.dispose?.(); });
    });
    viewer.scene.remove(world.root);
    viewer.markerMats = [];
    world = null; slabs = null;
  }

  world = new World(viewer.scene, data);
  slabs = new Slabs(world);
  viewer.registerMarkers([world.shelterPts?.mat, world.facilPts?.mat, world.splatPts?.mat]
    .filter(Boolean));
  viewer.scene.fog.color.set(state.view === "studio" ? FOG_STUDIO : FOG_LAB);

  const man = data.manifest;
  set({ scenario: man.scenarios?.[0]?.id ?? null });
  set({ scenarioBlockage: man.scenarios?.[0]?.blockage ?? 1.0 });
  set({ stage: Math.min(state.stage, man.stage_max) });
  state.playT = 0;
  state.stageMax = man.stage_max;

  // median terrain height as default camera target level
  const T = data.terrain;
  const y0 = medianAt(T.elevM, T.nx, T.nz);

  world.setLayers?.(state.layers);

  const cam0 = man.cameras?.[0];
  if (cam0) {
    const pose = presetPose(man, cam0, y0);
    if (first) {
      viewer.camera.position.copy(pose.pos);
      viewer.controls.target.copy(pose.target);
      viewer.controls.update();
    } else {
      flyTo(pose, 1.7);
    }
  }

  uiHooks = initUI({
    data, world, slabs, viewer, flyTo, presetPose, stackPose, y0,
  });
  // Live river watch panel: independent async fetch that never throws into
  // this path — a failed ingest degrades the panel, never the scene. Not
  // awaited on purpose: the 3D view must not wait on the observation JSON.
  loadLive(site, { flyTo, presetPose, y0 })
    .catch((e) => console.warn("[riversrise] live panel:", e));
  set({ ready: true });
  lastStage = -1;
  refreshUI();
  loading.classList.add("off");
}

function medianAt(elevM, nx, nz) {
  let sum = 0, n = 0;
  for (let j = 0; j < nz; j += 8) {
    for (let i = 0; i < nx; i += 8) {
      sum += elevM[j * nx + i]; n++;
    }
  }
  return n ? sum / n : 0;
}

// switchSite rethrows a failed load on purpose; swallow it here so a bad site
// click logs instead of surfacing as an unhandled promise rejection.
on("site", (s) => { switchSite(s).catch((e) => console.error("[riversrise] site switch:", e)); });

boot();
