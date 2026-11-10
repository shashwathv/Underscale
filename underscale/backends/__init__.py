"""Compositor backends. Everything outside this package talks to `Backend` only."""

import os

from .base import Backend, BackendError, Display


def current_desktop() -> str:
    """"gnome", "kde" or "" for anything else."""
    names = os.environ.get("XDG_CURRENT_DESKTOP", "").lower().split(":")
    if "gnome" in names:
        return "gnome"
    if "kde" in names:
        return "kde"
    return ""


def get_backend() -> Backend:
    """Return the backend for the running desktop."""
    desktop = current_desktop()
    if desktop == "gnome":
        from .mutter import MutterBackend

        return MutterBackend()
    if desktop == "kde":
        from .kde import KdeBackend

        return KdeBackend()
    shown = os.environ.get("XDG_CURRENT_DESKTOP") or "unknown"
    raise BackendError(
        f"This desktop ({shown}) is not supported yet. "
        "Underscale works on GNOME and KDE Plasma."
    )


__all__ = ["Backend", "BackendError", "Display", "current_desktop", "get_backend"]
