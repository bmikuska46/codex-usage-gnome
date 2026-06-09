from __future__ import annotations

import json
import threading
import time

import gi

gi.require_version("GLib", "2.0")
from gi.repository import GLib  # noqa: E402

from .api import UsageData, get_usage
from .auth import login
from .config import POLL_INTERVAL_SECONDS

DBUS_NAME = "com.github.bmikuska.CodexUsage"
DBUS_PATH = "/com/github/bmikuska/CodexUsage"
DBUS_INTERFACE = "com.github.bmikuska.CodexUsage"


class UsageService:
    def __init__(self) -> None:
        self._usage: UsageData = UsageData(
            plan_type="",
            email=None,
            primary=None,
            secondary=None,
            limit_reached=False,
            error="Starting…",
        )
        self._lock = threading.Lock()
        self._login_in_progress = False

    def get_usage_json(self) -> str:
        with self._lock:
            return json.dumps(self._usage.to_variant())

    def refresh(self) -> str:
        usage = get_usage(force_refresh=False)
        with self._lock:
            self._usage = usage
        return json.dumps(usage.to_variant())

    def login(self) -> str:
        if self._login_in_progress:
            return json.dumps({"status": "in_progress"})

        def _run() -> None:
            self._login_in_progress = True
            try:
                login()
                usage = get_usage(force_refresh=True)
                with self._lock:
                    self._usage = usage
            except Exception as exc:  # noqa: BLE001
                with self._lock:
                    self._usage = UsageData(
                        plan_type="",
                        email=None,
                        primary=None,
                        secondary=None,
                        limit_reached=False,
                        error=str(exc),
                    )
            finally:
                self._login_in_progress = False

        threading.Thread(target=_run, daemon=True).start()
        return json.dumps({"status": "started"})

    def logout(self) -> str:
        from .config import AUTH_FILE, LEGACY_AUTH_FILE

        for auth_file in (AUTH_FILE, LEGACY_AUTH_FILE):
            if auth_file.exists():
                auth_file.unlink()
        with self._lock:
            self._usage = UsageData(
                plan_type="",
                email=None,
                primary=None,
                secondary=None,
                limit_reached=False,
                error="Not logged in",
            )
        return json.dumps({"status": "ok"})

    def _poll(self) -> bool:
        usage = get_usage()
        with self._lock:
            self._usage = usage
        return True

    def start_polling(self) -> None:
        GLib.timeout_add_seconds(POLL_INTERVAL_SECONDS, self._poll)
        self._poll()


def run_dbus_service() -> None:
    import dbus
    from dbus.mainloop.glib import DBusGMainLoop
    from dbus.service import BusName, Object, method

    DBusGMainLoop(set_as_default=True)
    service = UsageService()

    class CodexUsageObject(Object):
        @method(DBUS_INTERFACE, in_signature="", out_signature="s")
        def GetUsage(self) -> str:  # noqa: N802
            return service.get_usage_json()

        @method(DBUS_INTERFACE, in_signature="", out_signature="s")
        def Refresh(self) -> str:  # noqa: N802
            return service.refresh()

        @method(DBUS_INTERFACE, in_signature="", out_signature="s")
        def Login(self) -> str:  # noqa: N802
            return service.login()

        @method(DBUS_INTERFACE, in_signature="", out_signature="s")
        def Logout(self) -> str:  # noqa: N802
            return service.logout()

    bus_name = BusName(DBUS_NAME, bus=dbus.SessionBus())
    CodexUsageObject(bus_name, DBUS_PATH)
    service.start_polling()

    loop = GLib.MainLoop()
    try:
        loop.run()
    except KeyboardInterrupt:
        pass
