"""Compositor backends. Everything outside this package talks to `Backend` only."""

from .base import Backend, BackendError, Display


def get_backend() -> Backend:
    """Return the backend for the running desktop.

    Only GNOME (Mutter) exists today. Other compositors plug in here.
    """
    from .mutter import MutterBackend

    return MutterBackend()


__all__ = ["Backend", "BackendError", "Display", "get_backend"]
