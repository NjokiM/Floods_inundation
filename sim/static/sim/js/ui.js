// All DOM wiring: slider, segments, stats, phases, why, legend, dialogs,
// camera presets, share links. Returns hooks to main.
import { state, set, siteData } from "./state.js";

const $ = (id) => document.getElementById(id);
const PH_COLORS = ["#7fbf95", "#e0c25e", "#e59944", "#e2573f", "#9d8bf0"];

let refs = null;        // { world, slabs, viewer, flyTo, presetPose }
let ticksFor = null;    // site the slider ticks were last built for
let uiBound = false;    // window/persistent listeners attached only once

// ------------------------------------------------------------------ helpers
function phaseIdx(man) {
  let idx = 0;
  (man.phases || []).forEach((p, i) => { if (state.stage >= p.stage) idx = i; });
  return idx;
}

function fmt(v) {
  return Math.round(v).toLocaleString("en-GB");
}
function fmtK(v) {
  return v >= 9999 ? `${(v / 1000).toFixed(0)}k` : fmt(v);
}

function bindSeg(id, pick) {
  const el = $(id);
  if (!el) return;
  el.addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (!b || !el.contains(b)) return;
    el.querySelectorAll("button").forEach((x) => x.classList.toggle("on", x === b));
    pick(b);
  });
}

// ------------------------------------------------------------------ slider
function drawSlider(man) {
  const slide = $("slide");
  const p0 = state.stage / man.stage_max;
  slide.querySelector(".fl").style.width = `${p0 * 100}%`;
  slide.querySelector(".kn").style.left = `${p0 * 100}%`;
  const pi = phaseIdx(man);
  const pth = (man.phases[pi].stage / man.stage_max) * 100;
  const band = slide.querySelector(".band");
  band.style.left = "0";
  band.style.width = `${pth}%`;
  band.style.background = `linear-gradient(90deg, #ffffff00, ${PH_COLORS[pi]}55)`;
  document.documentElement.style.setProperty("--ph", PH_COLORS[pi]);
  $("mV").innerHTML = `${state.stage.toFixed(1)}<b style="color:var(--ph)"> m</b>` +
    `<small style="color:#8b948c"> / ${man.stage_max}</small>`;
  slide.setAttribute("aria-valuemin", "0");
  slide.setAttribute("aria-valuemax", String(man.stage_max));
  slide.setAttribute("aria-valuenow", state.stage.toFixed(1));
  // ticks: phase thresholds (never overlaps) + historical marks
  let ticks = slide.querySelector(".ticks");
  if (!ticks) {
    ticks = document.createElement("div");
    ticks.className = "ticks";
    ticks.style.cssText = "position:absolute;inset:0;pointer-events:none;";
    slide.appendChild(ticks);
  }
  // Ticks depend only on the manifest, but drawSlider ran on every refreshUI —
  // i.e. ~60 full DOM rebuilds per second during scenario playback. Build them
  // once per site; the per-frame path above only moves the fill and the knob.
  if (ticksFor === man.site) return;
  ticksFor = man.site;
  ticks.innerHTML = "";
  (man.phases || []).forEach((p, i) => {
    if (i === 0) return;
    const t = document.createElement("span");
    t.className = "tk";
    t.style.left = `${(p.stage / man.stage_max) * 100}%`;
    t.style.background = PH_COLORS[i];
    t.innerHTML = `<b>${p.label.toLowerCase()}</b>`;
    ticks.appendChild(t);
  });
  (man.hist_marks || []).forEach(([ho, v]) => {
    const t = document.createElement("span");
    t.className = "tk";
    t.style.left = `${(v / man.stage_max) * 100}%`;
    t.style.background = "#f2ecdf";
    t.style.opacity = "0.5";
    t.innerHTML = `<b>${ho}</b>`;
    t.style.color = "#cfd5cf";
    ticks.appendChild(t);
  });
}

// ------------------------------------------------------------------ segments
function renderScenarioSeg(man) {
  const el = $("segScen");
  if (!el) return;
  el.innerHTML = "";
  (man.scenarios || []).forEach((sc) => {
    const b = document.createElement("button");
    b.textContent = sc.label;
    b.dataset.sc = sc.id;
    if (sc.id === state.scenario) b.classList.add("on");
    el.appendChild(b);
  });
}

// Bound ONCE, and reads the manifest at click time so a site switch can never
// leave this holding a stale scenario list.
let scenarioBound = false;
function bindScenario() {
  if (scenarioBound) return;
  const el = $("segScen");
  if (!el) return;
  scenarioBound = true;
  el.addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (!b || !el.contains(b)) return;
    const man = siteData()?.manifest;
    const sc = (man?.scenarios || []).find((x) => x.id === b.dataset.sc);
    if (!sc) return;
    set({ scenario: sc.id, scenarioBlockage: sc.blockage ?? 1.0 });
    state.playT = 0;
    refreshUI();
  });
}

// Cheap per-frame sync: toggles the "on" class only, never rebuilds the DOM.
function syncScenarioOn() {
  const el = $("segScen");
  if (!el) return;
  el.querySelectorAll("button").forEach((b) =>
    b.classList.toggle("on", b.dataset.sc === state.scenario));
}

function handleLayer(b) {
  const l = b.dataset.l;
  if (!l) return;
  state.layers.city = l === "city";
  state.layers.hand = l === "hand";
  state.layers.response = l === "response";
  refs?.world?.setLayers?.(state.layers);
  refreshUI();
}

function handleView(b) {
  const v = b.dataset.v;
  if (!v) return;
  set({ view: v });
  document.getElementById("app").classList.toggle("studio", v === "studio");
  refs?.viewer?.setMode?.(v);
  cameraPreset(v === "exploded" ? "stack" : "wide");
  refreshUI();
}

function handleSite(b) {
  if (!b.dataset.site) return;
  set({ playing: false, playT: 0 });
  set({ site: b.dataset.site });
}

// ------------------------------------------------------------------ stats
function renderStats(man, stats, stage) {
  if (!stats) return;
  // The headline river-stage readout was never written here — it updated
  // structures, facilities, roads and people but left #s-stage on the template's
  // hardcoded "0.0m" forever, so the app's primary number never moved.
  $("s-stage").innerHTML = `${(stage ?? 0).toFixed(1)}<small>m</small>`;
  $("s-struct").innerHTML = fmtK(stats.wetB);
  $("s-facil").textContent = String(stats.facil);
  $("s-roads").innerHTML = `${stats.cutKm.toFixed(1)}<small>km</small>`;
  const rate = Math.min(1, 0.12 + 0.42 * (stage / Math.max(1, man.stage_max)));
  const disp = Math.round(stats.people * rate);
  $("s-people").innerHTML = `${fmt(stats.people)}<small>≈ ${fmt(disp)} displaced</small>`;
}

// ------------------------------------------------------------------ phases/why/legend
function renderPhases(man) {
  const bar = $("phasebar");
  bar.innerHTML = "";
  const idx = phaseIdx(man);
  (man.phases || []).forEach((p, i) => {
    const el = document.createElement("i");
    el.textContent = p.label;
    el.style.setProperty("--c", PH_COLORS[i]);
    if (i === idx) el.classList.add("on");
    else if (i < idx) el.classList.add("past");
    bar.appendChild(el);
  });
}

function renderWhy(man) {
  const idx = phaseIdx(man);
  const p = man.phases[idx];
  $("why").innerHTML = `<b class="p">${p.label}</b> — ${p.why}`;
  $("slLab").textContent = man.river_label || "River";
}

function renderLegend(man) {
  const lg = $("legend");
  const on = state.layers.response || state.layers.hand;
  lg.hidden = !on;
  if (!on) return;
  const items = [`<em>${state.layers.hand ? "HAND risk" : "Response"}</em>`];
  if (state.layers.hand) {
    items.push(`<span><s style="background:#c8452a"></s>floods early (low HAND)</span>`);
    items.push(`<span><s style="background:#8fa39a"></s>calm ground (high HAND)</span>`);
  }
  if (state.layers.response) {
    items.push(`<span><s style="background:#4fd4a9"></s>shelter / high ground</span>`);
    items.push(`<span><s style="background:#e8f4ec"></s>open route</span>`);
    items.push(`<span><s style="background:#e2573f"></s>NO-GO — water</span>`);
    items.push(`<span><s style="background:#caa269"></s>${fmtK(refs.world.data.buildings.n)} structures · ${fmt(refs.world.man.facilities.length)} critical sites</span>`);
  }
  lg.innerHTML = items.join("");
}

// ------------------------------------------------------------------ cameras
function cameraPreset(id) {
  const man = siteData()?.manifest;
  if (!man || !refs?.flyTo) return;
  if (id === "stack") {
    const pose = refs.stackPose?.();
    if (pose) refs.flyTo(pose, 2.2);   // stackPose() returns null before load
    return;
  }
  const cam = (man.cameras || []).find((c) => c.id === id);
  if (cam) refs.flyTo(refs.presetPose(man, cam, refs.y0), 1.5);
}

// ------------------------------------------------------------------ dialogs
function bindDialogs() {
  document.querySelectorAll("dialog .x").forEach((x) => {
    x.addEventListener("click", () => x.parentElement.close());
  });
  $("infoBtn").onclick = () => {
    const man = siteData()?.manifest;
    if (man) {
      $("infoBody").innerHTML = `
        <h2>When the Rivers Rise — Nairobi &amp; Tana</h2>
        <h3>How the model works</h3>${man.info?.methodology || ""}
        <h3>Data &amp; attribution</h3>${man.info?.sources || ""}
        <h3>What these numbers are</h3>${man.info?.disclaimer || ""}
        <h3>Glossary</h3>
        <p><b>Stage</b> — how far the river is above its normal channel line.
        <b>HAND</b> — a point's height above its nearest drainage: the first
        thing that decides whether it floods. <b>Phase</b> — the response level
        implied by the current stage.</p>`;
    }
    $("info").showModal();
  };
  $("camBtn").onclick = () => {
    const man = siteData()?.manifest;
    const list = $("camList");
    list.innerHTML = "";
    (man?.cameras || []).forEach((c) => {
      const b = document.createElement("button");
      b.textContent = c.name;
      b.onclick = () => { cameraPreset(c.id); $("cams").close(); };
      list.appendChild(b);
    });
    $("cams").showModal();
  };
  $("shareBtn").onclick = async () => {
    const h = `#s=${state.site}|${state.scenario}|${state.stage.toFixed(2)}|${state.view}|` +
      ["city", "hand", "response"].filter((k) => state.layers[k]).join(",");
    history.replaceState(null, "", h);
    try { await navigator.clipboard.writeText(location.href); setHint("link copied", 2600); }
    catch { setHint("link updated in the address bar", 2600); }
  };
}

// ------------------------------------------------------------------ slider drag
function setStageFromEvent(man, clientX) {
  const slide = $("slide");
  const r = slide.getBoundingClientRect();
  const f = Math.max(0, Math.min(1, (clientX - r.left) / r.width));
  state.playT = f;   // scrubbing moves the scenario clock with you
  set({ playing: false, stage: +(f * man.stage_max).toFixed(2) });
  refreshUI();
}

// Bound once; the manifest is resolved at event time, so a site switch can never
// leave the slider dragging against the previous site's stage_max.
function bindSlider() {
  const slide = $("slide");
  let drag = false;
  const apply = (clientX) => {
    const man = siteData()?.manifest;
    if (man) setStageFromEvent(man, clientX);
  };
  slide.addEventListener("pointerdown", (e) => {
    drag = true;
    slide.setPointerCapture?.(e.pointerId);
    apply(e.clientX);
  });
  slide.addEventListener("pointermove", (e) => {
    if (drag) apply(e.clientX);
  });
  slide.addEventListener("pointerup", () => { drag = false; });
  slide.addEventListener("pointercancel", () => { drag = false; });
}

function bindKeys() {
  window.addEventListener("keydown", (e) => {
    const man = siteData()?.manifest;
    if (!man) return;
    if (e.key === " " && !e.repeat) { e.preventDefault(); togglePlay(); return; }
    if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
      const d = (e.key === "ArrowRight" ? 0.1 : -0.1);
      const ns = Math.max(0, Math.min(man.stage_max, +(state.stage + d).toFixed(2)));
      // keep the scenario clock with the slider — dragging already did this.
      // Without it, pressing play after an arrow-key nudge jumped back to the
      // stale playT and silently undid the adjustment.
      state.playT = man.stage_max ? ns / man.stage_max : 0;
      set({ playing: false, stage: ns });
      refreshUI();
    }
  });
}

function togglePlay() {
  const man = siteData()?.manifest;
  if (!man) return;
  if (state.playing) {
    set({ playing: false });
    setPlayIcon(false);
    return;
  }
  if (state.playT > 0.999) state.playT = 0;
  set({ playing: true });
  setPlayIcon(true);
}

function setPlayIcon(playing) {
  const p = $("play");
  p.setAttribute("aria-pressed", String(playing));
  $("playPath").setAttribute("d", playing
    ? "M7 5.5h4v13H7zM13 5.5h4v13h-4z"
    : "M8 5.5v13l10.5-6.5z");
}

// ------------------------------------------------------------------ boot/hooks
export function initUI(refsIn) {
  refs = refsIn;
  const man = refsIn.data.manifest;
  // initUI runs on EVERY site switch, but these listeners attach to elements (and
  // to window) that outlive the switch. Re-binding stacked duplicates: after N
  // site switches one spacebar press fired N toggles — an even N looked like the
  // key was dead — and one arrow key moved the stage N x 0.1 m. Bind once, then
  // only rebuild the per-site scenario buttons.
  if (!uiBound) {
    bindSeg("siteSeg", handleSite);
    bindSeg("segLayer", handleLayer);
    bindSeg("segView", handleView);
    bindScenario();
    bindSlider();
    $("play").onclick = togglePlay;
    bindDialogs();
    bindKeys();
    uiBound = true;
  }
  renderScenarioSeg(man);
  refreshUI();
  return { stats: renderStats };
}

export function setHint(text, ms) {
  let el = $("uiHint");
  if (!el) {
    el = document.createElement("div");
    el.id = "uiHint";
    document.getElementById("app").appendChild(el);
  }
  if (!text) { el.classList.remove("on"); return; }
  el.textContent = text;
  el.classList.add("on");
  if (ms) setTimeout(() => el.classList.remove("on"), ms);
}

export function refreshUI() {
  const man = siteData()?.manifest;
  if (!man || !refs?.world) return;
  $("kicker").textContent = man.kicker || "";
  $("mLabel").textContent = man.river_label || "River level";
  drawSlider(man);
  // Was renderScenarioSeg(man) + bindScenario(man). refreshUI runs every frame
  // during playback (via advancePlay) and on every slider move, so that rebuilt
  // the buttons ~60x/sec AND stacked a fresh click listener on #segScen each
  // time: ~900 duplicates per playthrough, every one re-firing the handler.
  // Buttons are built once per site now; here we only sync the "on" class.
  syncScenarioOn();
  renderPhases(man);
  renderWhy(man);
  renderLegend(man);
}
