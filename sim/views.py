from pathlib import Path

from django.shortcuts import render

# Every site the UI can offer. A site is only *selectable* once its container
# data has actually been baked (`python manage.py bake_<site>`). Advertising a
# site with nothing on disk made the frontend fetch a 404, and because
# switchSite() tore down the working scene first, clicking it blanked the app.
DATA_SITES = ["nairobi", "tana"]

SITE_LABELS = {"nairobi": "Nairobi", "tana": "Tana River"}

_DATA_DIR = Path(__file__).resolve().parent / "static" / "data"


def site_ready(site: str) -> bool:
    """True once <site>/manifest.json has been baked into static/data/."""
    return (_DATA_DIR / site / "manifest.json").is_file()


def index(request):
    sites = [
        {
            "id": s,
            "label": SITE_LABELS.get(s, s.title()),
            "ready": site_ready(s),
        }
        for s in DATA_SITES
    ]
    return render(request, "sim/index.html", {"sites": sites})
