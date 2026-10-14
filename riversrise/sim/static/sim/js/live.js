// Live river watch panel: renders the daily ingest output
// (/static/data/observations/<site>/latest.json) into #live in the sidebar.
//
// Honesty rules — these mirror sim/management/commands/fetch_flood_data.py:
//   - discharge is MODELLED GloFAS m³/s, never stage in metres; the footer
//     says so and nothing here may imply a link to the scenario slider.
//   - degraded signals (unreliable_baseline / off_glofas_network /
//     insufficient_data) render as muted chips WITH their reason, never as
//     numbers dressed up as confident.
//   - data older than STALE_AFTER_H gets a stale warning (the ingest cron may
//     have missed a run — e.g. laptop lid closed at 06:00).
// Never throws into the caller: fetch/parse/render failures collapse the panel
// to a one-line "unavailable" state and leave the 3D scene untouched.
import { siteData } from "./state.js";

const STALE_AFTER_H = 26;   // matches backend fetch_flood_data.STALE_AFTER_HOURS
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

// Full status vocabulary of _discharge_signal() — keep in sync with the
// management command; an unknown status degrades to the "no data" chip.
const STATUS = {
  rising:              { cls: "s-rise",    word: (s) => `RISING ×${fmtX(s.peak_over_baseline)}` },
  elevated:            { cls: "s-elev",    word: (s) => `ELEVATED ×${fmtX(s.peak_over_baseline)}` },
  steady:              { cls: "s-steady",  word: () => "STEADY" },
  unreliable_baseline: { cls: "s-unrated", word: () => "unrated" },
  off_glofas_network:  { cls: "s-offnet",  word: () => "off-network" },
  insufficient_data:   { cls: "s-nodata",  word: () => "no data" },
};

const LIVE = {};            // site -> Promise<data>, fetched once per page load
let hooks = null;           // { flyTo, presetPose, y0 }
let bound = false;          // head/rows listeners attached once
let userToggled = false;    // manual collapse wins over the mobile default

// ------------------------------------------------------------------ helpers
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

function safeUrl(u) { return /^https?:\/\//i.test(u || "") ? u : "#"; }

function fmtX(r) {                       // ratio -> "25" / "7.8"
  if (r == null || !isFinite(r)) return "?";
  return r >= 10 ? String(Math.round(r)) : r.toFixed(1);
}

function fmtFlow(v) {                    // m³/s, honest precision
  if (v == null || !isFinite(v)) return "—";
  if (v >= 100) return String(Math.round(v));
  if (v >= 10) return v.toFixed(1);
  return String(parseFloat(v.toFixed(2)));
}

function fmtDate(iso) {                  // "2026-10-16" -> "Oct 16"
  if (!iso) return "";
  const [y, m, d] = String(iso).slice(0, 10).split("-").map(Number);
  if (!m || !d) return String(iso);
  return `${MONTHS[m - 1]} ${d}`;
}

function addDays(iso, n) {               // date-only arithmetic, TZ-safe
  const [y, m, d] = String(iso).split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d + n)).toISOString().slice(0, 10);
}

// ------------------------------------------------------------------ content
function ageInfo(genIso) {
  const gen = new Date(genIso);
  if (isNaN(gen)) return { text: "unknown age", stale: true };
  const hhmm = String(genIso).slice(11, 16);
  const genDay = String(genIso).slice(0, 10);
  const now = new Date();
  const ageH = (now - gen) / 3.6e6;
  const today = now.toISOString().slice(0, 10);
  const when = genDay === today ? `updated ${hhmm} UTC`
                                : `updated ${fmtDate(genDay)} · ${hhmm} UTC`;
  return { text: when, stale: ageH > STALE_AFTER_H };
}

function subText(sig) {
  switch (sig.status) {
    case "rising":
    case "elevated":
    case "steady":
      return `peak ${fmtFlow(sig.forecast_peak_m3s)} m³/s ${fmtDate(sig.peak_date)}` +
             ` · base ${fmtFlow(sig.baseline_m3s)}`;
    case "unreliable_baseline":
      return `baseline ${fmtFlow(sig.baseline_m3s)} m³/s — below GloFAS resolution`;
    case "off_glofas_network":
      return `not on a GloFAS-modelled channel`;
    default:
      return `no usable discharge window`;
  }
}

function tipText(sig) {
  switch (sig.status) {
    case "rising":
    case "elevated":
    case "steady":
      return `Modelled GloFAS/SEAS5 discharge: median of the observed window ` +
             `${fmtFlow(sig.baseline_m3s)} m³/s, forecast peak ` +
             `${fmtFlow(sig.forecast_peak_m3s)} m³/s on ${fmtDate(sig.peak_date)}. ` +
             `Model output, not a gauge reading.`;
    case "unreliable_baseline":
      return `Median observed baseline ${fmtFlow(sig.baseline_m3s)} m³/s is below what ` +
             `GloFAS resolves on small streams, so a peak/baseline ratio would be ` +
             `arithmetic noise, not hydrology. Forecast peak for what it's worth: ` +
             `${fmtFlow(sig.forecast_peak_m3s)} m³/s on ${fmtDate(sig.peak_date)}.`;
    case "off_glofas_network":
      return sig.note || "Discharge is zero across the whole window: this point is " +
             "not on a GloFAS-modelled channel and carries no flood signal.";
    default:
      return "Not enough discharge data in the window to say anything honest.";
  }
}

function pointRow(p) {
  const sig = p.signal || { status: "insufficient_data" };
  const st = STATUS[sig.status] || STATUS.insufficient_data;
  return `<button type="button" class="live-row" data-lat="${esc(p.lat)}" ` +
         `data-lon="${esc(p.lon)}" title="${esc(tipText(sig))}">` +
         `<span class="lr-top"><span class="lr-name">${esc(p.label)}</span>` +
         `<span class="lr-chip ${st.cls}">${st.word(sig)}</span></span>` +
         `<span class="lr-sub">${esc(subText(sig))}</span></button>`;
}

function rainSummary(points, genDate) {
  // Past 7d: NASA POWER observed (last 7 daily values — POWER lags ~2 days, so
  // the window ends before today; the label carries that end date).
  // Next 7d: Open-Meteo precipitation forecast from the generation date.
  const g7 = addDays(genDate, 7);
  const next = [], past = [];
  let obsEnd = null;
  for (const p of points) {
    const omp = p.openmeteo_precip;
    if (Array.isArray(omp?.time) && Array.isArray(omp?.precipitation_sum)) {
      let s = 0;
      omp.time.forEach((t, i) => {
        if (t >= genDate && t < g7) s += omp.precipitation_sum[i] || 0;
      });
      next.push(s);
    }
    const np = p.nasa_power;
    if (Array.isArray(np?.dates) && np.dates.length >= 7 &&
        Array.isArray(np.precipitation_mm)) {
      past.push(np.precipitation_mm.slice(-7).reduce((a, b) => a + (b || 0), 0));
      const d = String(np.dates[np.dates.length - 1]);
      const iso = `${d.slice(0, 4)}-${d.slice(4, 6)}-${d.slice(6, 8)}`;
      if (!obsEnd || iso > obsEnd) obsEnd = iso;
    }
  }
  const avg = (a) => (a.length ? a.reduce((x, y) => x + y, 0) / a.length : null);
  return { next: avg(next), past: avg(past), obsEnd };
}

function gdacsLine(alerts) {
  const cur = (Array.isArray(alerts) ? alerts : [])
    .filter((a) => String(a?.iscurrent).toLowerCase() === "true");
  if (!cur.length) return `GDACS · no active East Africa flood alerts`;
  return cur.slice(0, 2).map((a) =>
    `GDACS · <a href="${safeUrl(a.report)}" target="_blank" rel="noopener">` +
    `${esc(a.name)}</a> — ${esc(a.alertlevel)}`).join("<br>");
}

// ------------------------------------------------------------------ render
function renderLive(panel, d) {
  const points = Object.values(d?.points || {});
  if (!points.length) { renderUnavailable(panel, "no points in today's ingest"); return; }

  const genDate = String(d.generated_utc || "").slice(0, 10);
  const age = ageInfo(d.generated_utc);
  const ageEl = panel.querySelector("#liveAge");
  ageEl.textContent = age.stale ? `⚠ stale · ${age.text}` : age.text;
  ageEl.classList.toggle("stale", age.stale);

  const rain = rainSummary(points, genDate);
  const sum = [];
  if (rain.next != null || rain.past != null) {
    const nextTxt = rain.next != null ? `next 7d ~${Math.round(rain.next)} mm (fcst)` : "";
    const pastTxt = rain.past != null
      ? `past 7d ~${Math.round(rain.past)} mm (obs to ${fmtDate(rain.obsEnd)})` : "";
    sum.push(`Rain · ${[nextTxt, pastTxt].filter(Boolean).join(" · ")}`);
  }
  sum.push(gdacsLine(d.east_africa_gdacs_alerts));

  panel.querySelector("#liveBody").innerHTML =
    points.map(pointRow).join("") +
    `<div class="live-sum">${sum.join("<br>")}</div>` +
    `<div class="live-foot">Modelled discharge (GloFAS/SEAS5 via Open-Meteo) — not ` +
    `gauges, and not this scene's stage slider.<br>Sources: Open-Meteo · NASA POWER · GDACS</div>`;

  panel.hidden = false;
  if (!bound) {
    bindHead(panel);
    bindRows(panel);
    bound = true;
  }
  // Mobile default: start collapsed so the sim keeps the screen — unless the
  // user has already made their own choice this page load.
  if (!userToggled && window.matchMedia("(max-width: 900px)").matches)
    panel.classList.add("collapsed");
  const head = panel.querySelector("#liveHead");
  head.setAttribute("aria-expanded", String(!panel.classList.contains("collapsed")));
}

function renderUnavailable(panel, why = "the daily ingest may have failed") {
  const ageEl = panel.querySelector("#liveAge");
  if (ageEl) { ageEl.textContent = "unavailable"; ageEl.classList.remove("stale"); }
  const body = panel.querySelector("#liveBody");
  if (body) body.innerHTML = `<div class="live-none">live data unavailable — ${esc(why)}</div>`;
  panel.hidden = false;
}

// ------------------------------------------------------------------ binding
function bindHead(panel) {
  panel.querySelector("#liveHead").addEventListener("click", () => {
    userToggled = true;
    panel.classList.toggle("collapsed");
    panel.querySelector("#liveHead")
      .setAttribute("aria-expanded", String(!panel.classList.contains("collapsed")));
  });
}

// Delegated once on the body container (survives innerHTML rebuilds):
// click a point row -> fly the camera to that lat/lon.
function bindRows(panel) {
  panel.querySelector("#liveBody").addEventListener("click", (e) => {
    const row = e.target.closest(".live-row");
    if (!row || !hooks?.flyTo || !hooks?.presetPose) return;
    const man = siteData()?.manifest;
    if (!man) return;
    const lat = parseFloat(row.dataset.lat);
    const lon = parseFloat(row.dataset.lon);
    if (!isFinite(lat) || !isFinite(lon)) return;
    // point-of-interest framing: tighter than the site's "wide" camera,
    // scaled to the scene so Nairobi streets and the Tana corridor both work.
    const alt = Math.min(6000, Math.max(600, (man.wid_m || 20000) * 0.06));
    hooks.flyTo(hooks.presetPose(man, { lat, lon, pitch: 58, alt, az: -215 }, hooks.y0), 1.4);
  });
}

// ------------------------------------------------------------------ public
function liveFor(site) {
  if (!LIVE[site]) {
    LIVE[site] = fetch(`/static/data/observations/${site}/latest.json`)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status} for ${site}`);
        return r.json();
      });
  }
  return LIVE[site];
}

// Called from switchSite (main.js) on boot and on every site switch.
// Resolves always; failures degrade to the unavailable state.
export function loadLive(site, refs) {
  if (refs) hooks = refs;
  const panel = document.getElementById("live");
  if (!panel || !site) return Promise.resolve();
  return liveFor(site)
    .then((d) => renderLive(panel, d))
    .catch((err) => {
      console.warn("[riversrise] live panel unavailable:", err?.message || err);
      renderUnavailable(panel);
    });
}
