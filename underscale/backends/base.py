"""The interface every compositor backend implements."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable


class BackendError(Exception):
    """A request the compositor refused or could not carry out."""


@dataclass
class Display:
    connector: str  # e.g. "HDMI-1"
    vendor: str
    product: str
    serial: str
    name: str  # human readable, e.g. "Sony SONY TV"
    builtin: bool
    active: bool  # part of the desktop right now
    width: int = 0  # current mode, in pixels
    height: int = 0
    scale: float = 1.0
    supported_scales: list[float] = field(default_factory=list)
    # None when the compositor cannot underscan this display.
    underscan: float | None = None

    @property
    def key(self) -> str:
        """Identity of the physical display, stable across ports and reboots."""
        return f"{self.vendor}:{self.product}:{self.serial}"

    @property
    def supports_underscan(self) -> bool:
        return self.underscan is not None

    def looks_like(self, scale: float | None = None) -> tuple[int, int]:
        """The desktop size, in points, that a scale gives on the current mode."""
        scale = scale or self.scale
        return round(self.width / scale), round(self.height / scale)


class Backend(ABC):
    #: Largest underscan amount the backend accepts (fraction of the picture).
    max_underscan: float = 0.25
    #: True when the desktop stores and restores underscan itself, so the
    #: daemon must leave it alone.
    persists_settings: bool = False
    #: What the user needs when a display cannot be underscanned.
    unavailable_hint: str = "This display cannot be underscanned."

    @abstractmethod
    def list_displays(self) -> list[Display]: ...

    @abstractmethod
    def set_underscan(self, display: Display, amount: float) -> None:
        """Shrink the picture by `amount` (0.0 = off). Applies immediately."""

    @abstractmethod
    def set_scale(self, display: Display, scale: float) -> None:
        """Change the display's UI scale and keep it across logins."""

    @abstractmethod
    def on_displays_changed(self, callback: Callable[[], None]) -> None:
        """Call `callback` when displays are added, removed or reconfigured.

        Needs a running GLib main loop.
        """

    def find_display(self, query: str) -> Display:
        """Find a display by connector ("HDMI-1") or by part of its name."""
        displays = self.list_displays()
        for display in displays:
            if display.connector.lower() == query.lower():
                return display
        matches = [d for d in displays if query.lower() in d.name.lower()]
        if len(matches) == 1:
            return matches[0]
        if matches:
            names = ", ".join(d.connector for d in matches)
            raise BackendError(f"'{query}' matches several displays: {names}")
        raise BackendError(f"No display matches '{query}'")
