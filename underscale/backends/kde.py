"""KDE Plasma backend: drives KWin through `kscreen-doctor`.

Plasma already has an "overscan" setting per output and remembers it itself.
Stock KWin only offers it where the graphics driver has a property for it
(mostly AMD). The kwin-underscale package makes it work on other drivers by
scaling the planes, after which this backend, kscreen-doctor and Plasma's own
Display settings all control the same value.

Plasma stores overscan as a whole percentage, so amounts are rounded to 1%.

UNTESTED: written against the libkscreen 6.8 sources, never run on Plasma.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from typing import Callable

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio  # noqa: E402

from .base import Backend, BackendError, Display  # noqa: E402

# KScreen::Output::Type value for a laptop's own panel.
OUTPUT_TYPE_PANEL = 7

SCALES = [1.0, 1.25, 1.5, 1.75, 2.0]


class KdeBackend(Backend):
    persists_settings = True
    unavailable_hint = (
        "KWin cannot adjust overscan with this graphics driver. "
        "Install the kwin-underscale package, then log out and back in."
    )

    def __init__(self) -> None:
        if not shutil.which("kscreen-doctor"):
            raise BackendError(
                "kscreen-doctor was not found. Install the 'kscreen' or "
                "'libkscreen' package of your distribution."
            )
        self._callbacks: list[Callable[[], None]] = []
        self._subscription = None

    def _doctor(self, *args: str) -> str:
        try:
            result = subprocess.run(
                ["kscreen-doctor", *args],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise BackendError(f"kscreen-doctor failed: {error}") from error
        if result.returncode != 0:
            message = (result.stderr or result.stdout).strip().splitlines()
            raise BackendError(message[-1] if message else "kscreen-doctor failed")
        return result.stdout

    def list_displays(self) -> list[Display]:
        try:
            config = json.loads(self._doctor("-j"))
        except json.JSONDecodeError as error:
            raise BackendError("Could not read kscreen-doctor's output") from error

        displays = []
        for output in config.get("outputs", []):
            if not output.get("connected", True):
                continue
            name = output.get("name", "")
            width = height = 0
            for mode in output.get("modes", []):
                if mode.get("id") == output.get("currentModeId"):
                    size = mode.get("size", {})
                    width, height = size.get("width", 0), size.get("height", 0)
            # "overscan" is only present when KWin can do it for this output.
            overscan = output.get("overscan")
            displays.append(
                Display(
                    connector=name,
                    vendor="kde",
                    product=name,
                    serial="",
                    name=name,
                    builtin=output.get("type") == OUTPUT_TYPE_PANEL,
                    active=bool(output.get("enabled", False)),
                    width=width,
                    height=height,
                    scale=float(output.get("scale", 1.0)),
                    supported_scales=list(SCALES),
                    underscan=None if overscan is None else overscan / 100.0,
                )
            )
        return displays

    def set_underscan(self, display: Display, amount: float) -> None:
        if not display.supports_underscan:
            raise BackendError(
                f"KWin cannot adjust overscan on {display.name}. On graphics "
                "drivers without an overscan property this needs the "
                "kwin-underscale package."
            )
        percent = round(max(0.0, min(float(amount), self.max_underscan)) * 100)
        self._doctor(f"output.{display.connector}.overscan.{percent}")

    def set_scale(self, display: Display, scale: float) -> None:
        self._doctor(f"output.{display.connector}.scale.{scale:g}")

    def on_displays_changed(self, callback: Callable[[], None]) -> None:
        self._callbacks.append(callback)
        if self._subscription is not None:
            return
        try:
            bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        except Exception:  # no session bus: changes are just not reported
            return
        self._subscription = bus.signal_subscribe(
            None,
            "org.kde.kscreen.Backend",
            "configChanged",
            None,
            None,
            Gio.DBusSignalFlags.NONE,
            lambda *_args: [cb() for cb in self._callbacks],
        )
