"""GNOME backend: talks to org.gnome.Mutter.DisplayConfig over D-Bus.

Underscan needs the mutter-underscale package, which adds the
SetUnderscanAmount method and the "underscan-amount" monitor property.
Scale works on stock Mutter.
"""

from __future__ import annotations

from typing import Callable

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib  # noqa: E402

from .base import Backend, BackendError, Display  # noqa: E402

BUS_NAME = "org.gnome.Mutter.DisplayConfig"
OBJECT_PATH = "/org/gnome/Mutter/DisplayConfig"
INTERFACE = "org.gnome.Mutter.DisplayConfig"

APPLY_PERSISTENT = 2
LAYOUT_MODE_LOGICAL = 1


def _clean_error(error: GLib.Error) -> str:
    # Remote errors arrive as "GDBus.Error:<error name>: <message>".
    message = error.message or str(error)
    if message.startswith("GDBus.Error:"):
        _prefix, _sep, rest = message[len("GDBus.Error:"):].partition(": ")
        message = rest or message
    return message


class MutterBackend(Backend):
    def __init__(self) -> None:
        try:
            self._proxy = Gio.DBusProxy.new_for_bus_sync(
                Gio.BusType.SESSION,
                Gio.DBusProxyFlags.DO_NOT_LOAD_PROPERTIES,
                None,
                BUS_NAME,
                OBJECT_PATH,
                INTERFACE,
                None,
            )
        except GLib.Error as error:
            raise BackendError(f"Cannot reach Mutter: {_clean_error(error)}") from error
        self._callbacks: list[Callable[[], None]] = []
        self._proxy.connect("g-signal", self._on_signal)
        self._proxy.connect("notify::g-name-owner", self._on_name_owner)

    # -- state ------------------------------------------------------------

    def _call(self, method: str, args: GLib.Variant | None = None):
        try:
            result = self._proxy.call_sync(
                method, args, Gio.DBusCallFlags.NONE, -1, None
            )
        except GLib.Error as error:
            raise BackendError(_clean_error(error)) from error
        return result.unpack() if result is not None else None

    def _state(self):
        return self._call("GetCurrentState")

    def list_displays(self) -> list[Display]:
        _serial, monitors, logical_monitors, _props = self._state()

        scale_of: dict[str, float] = {}
        for _x, _y, scale, _transform, _primary, specs, _lprops in logical_monitors:
            for spec in specs:
                scale_of[spec[0]] = scale

        displays = []
        for (connector, vendor, product, serial), modes, props in monitors:
            display = Display(
                connector=connector,
                vendor=vendor,
                product=product,
                serial=serial,
                name=props.get("display-name", connector),
                builtin=bool(props.get("is-builtin", False)),
                active=connector in scale_of,
                scale=scale_of.get(connector, 1.0),
                underscan=props.get("underscan-amount"),
            )
            for _id, width, height, _rate, _preferred, scales, mode_props in modes:
                if mode_props.get("is-current"):
                    display.width, display.height = width, height
                    display.supported_scales = sorted(scales)
            displays.append(display)
        return displays

    # -- underscan --------------------------------------------------------

    def set_underscan(self, display: Display, amount: float) -> None:
        if not display.supports_underscan:
            raise BackendError(
                f"{display.name} cannot be underscanned. This needs the "
                "mutter-underscale package and an external display."
            )
        amount = max(0.0, min(float(amount), self.max_underscan))
        self._call(
            "SetUnderscanAmount",
            GLib.Variant("(sd)", (display.connector, amount)),
        )

    # -- scale ------------------------------------------------------------

    def set_scale(self, display: Display, scale: float) -> None:
        serial, monitors, logical_monitors, props = self._state()

        current_mode: dict[str, tuple[str, int, int]] = {}
        monitor_props: dict[str, dict] = {}
        for (connector, *_rest), modes, mprops in monitors:
            monitor_props[connector] = mprops
            for mode_id, width, height, _rate, _pref, _scales, mode_props in modes:
                if mode_props.get("is-current"):
                    current_mode[connector] = (mode_id, width, height)

        target = None
        for logical in logical_monitors:
            if any(spec[0] == display.connector for spec in logical[5]):
                target = logical
        if target is None:
            raise BackendError(f"{display.name} is not part of the desktop")

        logical_layout = props.get("layout-mode", LAYOUT_MODE_LOGICAL) == LAYOUT_MODE_LOGICAL

        def logical_size(logical, with_scale):
            _mode, width, height = current_mode[logical[5][0][0]]
            if logical[3] in (1, 3, 5, 7):  # rotated by 90 or 270 degrees
                width, height = height, width
            if logical_layout:
                return round(width / with_scale), round(height / with_scale)
            return width, height

        old_w, old_h = logical_size(target, target[2])
        new_w, new_h = logical_size(target, scale)
        old_right, old_bottom = target[0] + old_w, target[1] + old_h

        # Monitors to the right of or below the changed one move with its
        # edge, so the layout stays gap-free.
        config = []
        for logical in logical_monitors:
            x, y, lscale, transform, primary, specs, _lprops = logical
            if logical is target:
                lscale = scale
            else:
                if x >= old_right:
                    x += new_w - old_w
                if y >= old_bottom:
                    y += new_h - old_h
            outputs = []
            for spec in specs:
                connector = spec[0]
                out_props = {}
                mprops = monitor_props.get(connector, {})
                if mprops.get("is-underscanning"):
                    out_props["underscanning"] = GLib.Variant("b", True)
                if "color-mode" in mprops:
                    out_props["color-mode"] = GLib.Variant("u", mprops["color-mode"])
                outputs.append((connector, current_mode[connector][0], out_props))
            config.append((x, y, lscale, transform, primary, outputs))

        apply_props = {}
        if props.get("supports-changing-layout-mode"):
            apply_props["layout-mode"] = GLib.Variant(
                "u", props.get("layout-mode", LAYOUT_MODE_LOGICAL)
            )

        self._call(
            "ApplyMonitorsConfig",
            GLib.Variant(
                "(uua(iiduba(ssa{sv}))a{sv})",
                (serial, APPLY_PERSISTENT, config, apply_props),
            ),
        )

    # -- change notification ---------------------------------------------

    def on_displays_changed(self, callback: Callable[[], None]) -> None:
        self._callbacks.append(callback)

    def _notify(self) -> None:
        for callback in self._callbacks:
            callback()

    def _on_signal(self, _proxy, _sender, signal_name, _params) -> None:
        if signal_name == "MonitorsChanged":
            self._notify()

    def _on_name_owner(self, proxy, _pspec) -> None:
        # Mutter (re)appeared on the bus, e.g. after a shell restart.
        if proxy.get_name_owner():
            self._notify()
