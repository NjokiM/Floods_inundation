"""WSGI entrypoint — the sim is effectively a static site."""
import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "riversrise.settings")
application = get_wsgi_application()
