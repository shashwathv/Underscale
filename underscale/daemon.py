"""underscale-daemon: re-applies each display's saved underscan.

The compositor does not store the amount, so it has to be applied again at
login and whenever a display is plugged in or the layout changes.
"""

from __future__ import annotations

import sys

import gi

gi.require_version("GLib", "2.0")
from gi.repository import GLib  # noqa: E402

from .backends import BackendError, get_backend  # noqa: E402
from .store import Store  # noqa: E402


def apply_saved(backend, store) -> None:
    try:
        displays = backend.list_displays()
    except BackendError as error:
        print(f"underscale-daemon: {error}", file=sys.stderr)
        return

    for display in displays:
        if not display.active or not display.supports_underscan:
            continue
        wanted = store.get_underscan(display)
        if abs(wanted - display.underscan) < 0.0005:
            continue
        try:
            backend.set_underscan(display, wanted)
            print(f"underscale-daemon: {display.name}: underscan {wanted * 100:.1f}%")
        except BackendError as error:
            print(f"underscale-daemon: {display.name}: {error}", file=sys.stderr)


def main() -> int:
    try:
        backend = get_backend()
    except BackendError as error:
        print(f"underscale-daemon: {error}", file=sys.stderr)
        return 1
    store = Store()

    pending = {"id": 0}

    def run() -> bool:
        pending["id"] = 0
        apply_saved(backend, store)
        return GLib.SOURCE_REMOVE

    def schedule() -> None:
        # Hotplug produces a burst of change signals; act once it settles.
        if pending["id"]:
            GLib.source_remove(pending["id"])
        pending["id"] = GLib.timeout_add(400, run)

    backend.on_displays_changed(schedule)
    apply_saved(backend, store)

    GLib.MainLoop().run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
