"""
Standalone settings for the 'When the Rivers Rise — Nairobi & Tana' flood sim.

No database, no admin, no auth. The server only renders one template and serves
static assets; all computation lives in data-prep management commands and the
browser-side Three.js client.
"""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = "wrr-local-demo-key-not-for-production"
DEBUG = True
ALLOWED_HOSTS = ["127.0.0.1", "localhost"]

INSTALLED_APPS = [
    "sim",
    "django.contrib.staticfiles",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "riversrise.urls"
WSGI_APPLICATION = "riversrise.wsgi.application"

DATABASES = {}

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": []},
    },
]

# Tanium: static under each app via AppDirectoriesFinder.
STATIC_URL = "static/"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

USE_TZ = False
