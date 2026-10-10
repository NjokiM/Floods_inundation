"""Daily flood-data ingest for the Rivers Rise sites.

Pulls from sources that need NO registration and NO API key (all verified
reachable 2026-10-09):

  * Open-Meteo Flood API  -> GloFAS river discharge (m3/s), past + forecast
  * Open-Meteo Forecast   -> daily precipitation (mm)
  * NASA POWER            -> observed daily precipitation (authoritative, ~2d lag)
  * GDACS                 -> active flood alerts, filtered to East Africa

Writes JSON under sim/static/data/observations/<site>/ so Django's static
handler serves it at /static/data/observations/<site>/latest.json with no
extra view and no DB migration.

Deliberate limits, do not "fix" without thinking:
  * Discharge (m3/s) is NOT river stage (m). Converting needs a rating curve
    the project does not have, so this command never invents a stage value.
  * Every source is isolated: one failure degrades the payload, it never
    aborts the run or wipes previously collected data.
  * Requests are identified. Open-Meteo and Met Norway ask for a real
    User-Agent; anonymous clients get throttled or 403'd.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
import time
from pathlib import Path

import requests
from django.core.management.base import BaseCommand

UA = "riversrise-flood-monitor/1.0 (+https://github.com/NjokiM/Floods_inundation)"
TIMEOUT = 25  # seconds; every request is bounded so a hung source cannot stall cron

OUT_ROOT = Path(__file__).resolve().parents[2] / "static" / "data" / "observations"

# Sampling points, taken from sim/sitedata/site_*.py settlement/river geometry.
# These are the places the 3D model actually claims impact for, so the ingest
# and the visualisation stay talking about the same ground.
POINTS = {
    "nairobi": [
        ("nairobi_cbd", "Nairobi CBD / Nairobi River", -1.2850, 36.8225),
        ("mathare", "Mathare", -1.2520, 36.8680),
        ("mukuru", "Mukuru kwa Njenga", -1.3110, 36.8900),
        ("kibera", "Kibera", -1.3120, 36.7890),
    ],
    "tana": [
        ("hola", "Hola (Idsowe)", -1.5015, 40.0310),
        ("garsen", "Garsen", -2.0310, 40.1050),
        ("wenje", "Wenje", -1.4850, 39.9640),
        ("bura", "Bura East", -1.2425, 39.6455),
    ],
}

# GDACS returns global flood centroids; keep only the East Africa neighbourhood.
# North edge at 8N so southern Ethiopia / Somalia show up: those are the regional
# context for an OND flood season, and at 5N they were silently excluded.
EA_BBOX = (33.0, -5.0, 42.0, 8.0)  # west, south, east, north

# Open-Meteo caps the free forecast API harder than the flood API. Sending
# forecast_days=30 to /v1/forecast is a hard 400, not a truncation.
OM_FORECAST_MAX_DAYS = 16
OM_PAST_MAX_DAYS = 92

ATTRIBUTION = {
    "open_meteo_flood": "Open-Meteo Flood API (GloFAS/SEAS5), CC BY 4.0",
    "open_meteo_forecast": "Open-Meteo Forecast API, CC BY 4.0",
    "nasa_power": "NASA POWER (GEOSIT), https://power.larc.nasa.gov",
    "gdacs": "GDACS (EC/JRC + UN), https://www.gdacs.org",
}


class SourceError(Exception):
    """A single source failed; the run continues with the others."""


def _get_json(url: str, params: dict | None = None, tries: int = 3) -> dict:
    """GET with bounded retries. A single read timeout (seen live on
    flood-api.open-meteo.com) must not cost a whole site's data for the day."""
    last: Exception | None = None
    for attempt in range(1, tries + 1):
        try:
            r = requests.get(url, params=params,
                             headers={"User-Agent": UA}, timeout=TIMEOUT)
            r.raise_for_status()
            return r.json()
        except Exception as exc:  # noqa: BLE001 - re-raised after final attempt
            last = exc
            if attempt < tries:
                time.sleep(1.5 * attempt)  # 1.5s, 3s
    raise SourceError(f"{type(last).__name__}: {last}")


def _openmeteo_flood(lat: float, lon: float, past: int, forecast: int) -> dict:
    """GloFAS river discharge. The only source here that is genuinely
    hydrological (volume rate), rather than meteorological (rain)."""
    d = _get_json(
        "https://flood-api.open-meteo.com/v1/flood",
        {"latitude": lat, "longitude": lon, "daily": "river_discharge",
         "past_days": past, "forecast_days": forecast},
    )
    daily = d.get("daily") or {}
    times = daily.get("time") or []
    vals = daily.get("river_discharge") or []
    if not times or len(times) != len(vals):
        raise SourceError("open-meteo flood: empty or ragged series")
    return {"time": times, "river_discharge": vals,
            "units": (d.get("daily_units") or {}).get("river_discharge", "m³/s"),
            "resolved": {"lat": d.get("latitude"), "lon": d.get("longitude"),
                         "elevation_m": d.get("elevation")}}


def _openmeteo_precip(lat: float, lon: float, past: int, forecast: int) -> dict:
    # Clamp to this endpoint's real limits: forecast_days>16 is a 400, and
    # past_days>92 likewise. The flood API tolerates more; this one does not.
    d = _get_json(
        "https://api.open-meteo.com/v1/forecast",
        {"latitude": lat, "longitude": lon, "daily": "precipitation_sum",
         "past_days": min(past, OM_PAST_MAX_DAYS),
         "forecast_days": min(forecast, OM_FORECAST_MAX_DAYS),
         "timezone": "Africa/Nairobi"},
    )
    daily = d.get("daily") or {}
    return {"time": daily.get("time") or [],
            "precipitation_sum": daily.get("precipitation_sum") or [],
            "units": (daily.get("units") or d.get("daily_units") or {}).get(
                "precipitation_sum", "mm")}


def _nasa_power(lat: float, lon: float, days: int) -> dict:
    """Observed precipitation. ~2 day latency: the most recent days come back
    as the -999.0 fill value and must be dropped, not plotted as zero."""
    end = dt.date.today() - dt.timedelta(days=2)
    start = end - dt.timedelta(days=days - 1)
    d = _get_json(
        "https://power.larc.nasa.gov/api/temporal/daily/point",
        {"parameters": "PRECTOTCORR", "community": "RE", "longitude": lon,
         "latitude": lat, "format": "JSON",
         "start": start.strftime("%Y%m%d"), "end": end.strftime("%Y%m%d")},
    )
    raw = ((d.get("properties") or {}).get("parameter") or {}).get("PRECTOTCORR") or {}
    filled = d.get("header", {}).get("fill_value", -999.0)
    series = {k: v for k, v in raw.items() if v != filled}
    if not series:
        raise SourceError("nasa power: no unfilled values in window")
    return {"dates": sorted(series), "precipitation_mm": [series[k] for k in sorted(series)],
            "units": "mm/day", "latency_note": "~2 days; fill values dropped"}


def _gdacs_alerts() -> list[dict]:
    """Active Orange/Red flood events inside the East Africa bbox."""
    d = _get_json("https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH",
                  {"eventlist": "FL", "alertlevel": "Orange;Red"})
    w, s, e, n = EA_BBOX
    out = []
    for f in d.get("features") or []:
        p = f.get("properties") or {}
        lon, lat = (f.get("geometry") or {}).get("coordinates") or (None, None)
        if lon is None or not (w <= lon <= e and s <= lat <= n):
            continue
        out.append({
            "eventid": p.get("eventid"), "glide": p.get("glide"),
            "name": p.get("name"), "country": p.get("country"),
            "alertlevel": p.get("alertlevel"), "episodealertlevel": p.get("episodealertlevel"),
            "fromdate": p.get("fromdate"), "todate": p.get("todate"),
            "iscurrent": p.get("iscurrent"), "lat": lat, "lon": lon,
            "report": (p.get("url") or {}).get("report"),
        })
    return out


def _discharge_signal(series: list, times: list) -> dict:
    """Cheap, honest interpretation: forecast peak vs the observed baseline.

    No rating curve exists, so this deliberately reports RELATIVE change and
    never claims a stage in metres.
    """
    vals = [v for v in series if isinstance(v, (int, float))]
    if len(vals) < 4:
        return {"status": "insufficient_data"}
    today = dt.date.today().isoformat()
    obs = [v for t, v in zip(times, series)
           if t <= today and isinstance(v, (int, float))]
    # keep (date, value) pairs so the peak's date comes from the FORECAST window;
    # matching on value alone returned the first occurrence anywhere in the series.
    fct = [(t, v) for t, v in zip(times, series)
           if t > today and isinstance(v, (int, float))]
    # An all-zero series means GloFAS has no channel at this grid cell (true of
    # Bura East), NOT a dry river. Say so rather than emitting 0.0 m³/s as if it
    # were a measurement someone could read as "no flood risk here".
    if vals and max(vals) <= 0.0:
        return {"status": "off_glofas_network",
                "note": "discharge is 0 across the whole window: this point is not on a "
                        "GloFAS-modelled channel, so it carries no flood signal at all."}
    base = sorted(obs)[len(obs) // 2] if obs else None  # median of observed window
    peak_pair = max(fct, key=lambda tv: tv[1]) if fct else None
    # fct rows are (date, value), so the value comes SECOND. Getting this the
    # other way round assigns the date string to `peak` and dies on peak / base.
    peak_day, peak = peak_pair if peak_pair else (None, None)
    # `base == 0.0` is falsy but a perfectly valid median, so test against None.
    if base is not None and peak is not None:
        if base < MIN_BASELINE_M3S:
            # Live example: Mukuru 0.03 -> 1.52 m3/s computes as "x50 rising", but
            # both numbers sit below what GloFAS can resolve on a small urban
            # stream. Ranking that above a genuine x8 on the Tana is nonsense, so
            # report it as low-confidence instead of as the loudest alarm we have.
            ratio, status = None, "unreliable_baseline"
        else:
            ratio = peak / base
            status = ("rising" if ratio >= 3 else
                      "elevated" if ratio >= 1.5 else "steady")
    else:
        ratio, status = None, "insufficient_data"
    return {"baseline_m3s": base, "forecast_peak_m3s": peak, "peak_date": peak_day,
            "peak_over_baseline": round(ratio, 2) if ratio else None, "status": status}


# --- staleness ---------------------------------------------------------------
# The cron job runs on a laptop: a lid closed at 06:00 leaves a silent hole in
# the series that nothing would ever notice. These helpers let the app see the
# gap and catch up by itself on server start.

STALE_AFTER_HOURS = 26  # just over a day, so a single missed cron run trips it

# Below this, a peak/baseline RATIO is arithmetic noise rather than hydrology:
# GloFAS cannot resolve flow on small urban streams, so 0.03 -> 1.52 m3/s would
# otherwise outrank a real x8 rise on the Tana.
MIN_BASELINE_M3S = 1.0


def latest_age_hours(site: str) -> float | None:
    """Age of <site>/latest.json in hours, or None if missing/unreadable."""
    p = OUT_ROOT / site / "latest.json"
    if not p.exists():
        return None
    try:
        gen = dt.datetime.fromisoformat(json.loads(p.read_text())["generated_utc"])
    except Exception:  # noqa: BLE001 - unreadable counts as missing
        return None
    if gen.tzinfo is None:
        gen = gen.replace(tzinfo=dt.timezone.utc)
    return (dt.datetime.now(dt.timezone.utc) - gen).total_seconds() / 3600.0


def stale_sites(hours: float = STALE_AFTER_HOURS) -> list[str]:
    return [s for s in POINTS
            if (a := latest_age_hours(s)) is None or a > hours]


class Command(BaseCommand):
    help = "Fetch daily flood data (GloFAS discharge, rainfall, GDACS alerts) for the sites."

    def add_arguments(self, parser):
        parser.add_argument("--site", default="all",
                            help="nairobi | tana | all (default: all)")
        parser.add_argument("--if-stale", action="store_true",
                            help=f"fetch only sites older than {STALE_AFTER_HOURS}h and "
                                 "exit quietly when none are; used by the start-up catch-up")
        parser.add_argument("--past", type=int, default=30,
                            help="days of history to pull (default 30)")
        parser.add_argument("--forecast", type=int, default=30,
                            help="forecast days to pull (default 30)")
        parser.add_argument("--quiet", action="store_true")

    def handle(self, *args, **opts):
        sites = list(POINTS) if opts["site"] == "all" else [opts["site"]]
        unknown = [s for s in sites if s not in POINTS]
        if unknown:
            self.stderr.write(f"unknown site(s): {', '.join(unknown)}")
            sys.exit(2)

        log = (lambda *a: None) if opts["quiet"] else (lambda *a: self.stdout.write(" ".join(str(x) for x in a)))

        if opts["if_stale"]:
            stale = [s for s in sites if s in stale_sites()]
            if not stale:
                log(f"fresh: every site updated within {STALE_AFTER_HOURS}h, nothing to fetch")
                return
            sites = stale
            log(f"catching up stale site(s): {', '.join(sites)}")
        now = dt.datetime.now(dt.timezone.utc)
        failures: list[str] = []

        try:
            alerts = _gdacs_alerts()
            log(f"GDACS: {len(alerts)} active East Africa flood event(s)")
        except Exception as exc:  # noqa: BLE001 - one dead source must not kill the run
            alerts, err = [], f"gdacs: {exc}"
            failures.append(err)
            log("!", err)

        for site in sites:
            points = {}
            for pid, label, lat, lon in POINTS[site]:
                rec: dict = {"label": label, "lat": lat, "lon": lon}
                for key, fn, kw in (
                    ("openmeteo_flood", _openmeteo_flood, {"past": opts["past"], "forecast": opts["forecast"]}),
                    ("openmeteo_precip", _openmeteo_precip, {"past": opts["past"], "forecast": opts["forecast"]}),
                    ("nasa_power", _nasa_power, {"days": opts["past"]}),
                ):
                    try:
                        rec[key] = fn(lat, lon, **kw)
                    except Exception as exc:  # noqa: BLE001
                        rec[key] = {"error": str(exc)}
                        failures.append(f"{site}/{pid}/{key}: {exc}")
                        log(f"  ! {site}/{pid}/{key}: {exc}")
                q = rec.get("openmeteo_flood") or {}
                if q.get("time"):
                    rec["signal"] = _discharge_signal(q["river_discharge"], q["time"])
                points[pid] = rec
                sig = rec.get("signal") or {}
                log(f"  {site}/{pid}: discharge peak {sig.get('forecast_peak_m3s')} m³/s "
                    f"({sig.get('status')}) · POWER days {len((rec.get('nasa_power') or {}).get('dates') or [])}")

            payload = {
                "generated_utc": now.isoformat(timespec="seconds"),
                "site": site,
                "window": {"past_days": opts["past"], "forecast_days": opts["forecast"]},
                "attribution": ATTRIBUTION,
                "east_africa_gdacs_alerts": alerts,
                "points": points,
                "note": ("river_discharge is m³/s (GloFAS), NOT river stage in metres. "
                         "No rating curve is applied, so nothing here should be read as "
                         "the model's stage slider value."),
            }

            d = OUT_ROOT / site
            d.mkdir(parents=True, exist_ok=True)
            # atomic-ish: write temp then replace, so a mid-write crash cannot
            # leave a truncated latest.json that the frontend would choke on.
            tmp = d / f".latest.{now.strftime('%Y%m%d%H%M%S')}.tmp"
            tmp.write_text(json.dumps(payload, indent=1, ensure_ascii=False))
            tmp.replace(d / "latest.json")
            (d / f"{now:%Y-%m-%d}.json").write_text(
                json.dumps(payload, indent=1, ensure_ascii=False))

            # Rolling series: one compact row per run, so the time series grows
            # without re-downloading history. Keeps latest.json small.
            sfile = d / "series.json"
            series = json.loads(sfile.read_text()) if sfile.exists() else []
            series.append({
                "generated_utc": payload["generated_utc"],
                "points": {pid: {
                    "discharge_peak_m3s": (r.get("signal") or {}).get("forecast_peak_m3s"),
                    "discharge_baseline_m3s": (r.get("signal") or {}).get("baseline_m3s"),
                    "status": (r.get("signal") or {}).get("status"),
                    "power_mm_last": ((r.get("nasa_power") or {}).get("precipitation_mm") or [None])[-1],
                } for pid, r in points.items()},
                "gdacs_alerts": len(alerts),
            })
            # One row per DAY, not per run: a manual re-run after the 06:00 cron
            # job must replace that day's row. Dedupe across the WHOLE list rather
            # than just today, so rows duplicated before this guard existed get
            # cleaned up too. Later row wins; sorted so the file stays chronological.
            by_day = {str(r.get("generated_utc", ""))[:10]: r for r in series}
            series = [by_day[k] for k in sorted(by_day)][-730:]  # ~2 years of days
            sfile.write_text(json.dumps(series, indent=1, ensure_ascii=False))
            log(f"-> {d/'latest.json'}")

        if failures:
            self.stderr.write(f"completed with {len(failures)} source failure(s)")
            # non-zero so a cron wrapper can alert, but the good data is on disk
            sys.exit(1 if len(failures) >= len(sites) * 3 else 0)
        log("all sources OK")
