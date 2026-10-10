"""App config for `sim`.

It exists for one reason: the daily flood-data ingest is scheduled by cron on a
developer laptop, and a lid closed at 06:00 leaves a silent hole in the series
that nothing would ever notice. So on dev-server start we ask the ingest command
to catch up -- but only for sites whose data is actually stale, and only in a
background thread, so startup is never blocked by a slow or dead upstream.

Guards matter here. `ready()` fires for EVERY process: migrate, collectstatic,
shell, each management command, and twice under runserver's autoreloader. Without
them this would either spam the network on every command or recurse into itself
(the ingest is itself a management command, so it triggers `ready()` too).
"""

import os
import sys
import threading

from django.apps import AppConfig


def _should_catch_up() -> bool:
    if "runserver" not in sys.argv:
        return False
    # Never recurse: the ingest command loads the app registry like any other.
    if "fetch_flood_data" in sys.argv:
        return False
    # runserver forks an autoreload child; RUN_MAIN is only set in the child, so
    # the fetch happens once per server start rather than twice.
    return os.environ.get("RUN_MAIN") == "true"


class SimConfig(AppConfig):
    name = "sim"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        if not _should_catch_up():
            return

        def _run():
            # Imported lazily: touching the command module at app-load time pulls
            # in `requests` before the registry is ready.
            from django.core.management import call_command

            try:
                call_command("fetch_flood_data", if_stale=True, quiet=True)
            except SystemExit:
                pass  # the command exits 1 on partial source failure; not fatal here
            except Exception as exc:  # noqa: BLE001 - startup must never die on this
                print(f"[sim] flood-data catch-up failed: {exc}", file=sys.stderr)

        threading.Thread(target=_run, name="flood-ingest-catchup", daemon=True).start()
