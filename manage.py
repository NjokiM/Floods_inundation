#!/usr/bin/env python
"""Django's command-line utility for the standalone 'When the Rivers Rise' sim."""
import os
import sys


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "riversrise.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Activate venv_floods and install "
            "riversrise/requirements-riversrise.txt first."
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
