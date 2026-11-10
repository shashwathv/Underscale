"""The Underscale settings window."""

from __future__ import annotations

import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk  # noqa: E402

from .backends import BackendError, get_backend  # noqa: E402
from .backends.base import Display  # noqa: E402
from .store import Store  # noqa: E402

APP_ID = "io.github.underscale.Underscale"

# The slider covers the range a TV's overscan realistically needs. The
# backend accepts more through underscalectl.
SLIDER_MAX = 0.15


class Window(Adw.ApplicationWindow):
    def __init__(self, app: Adw.Application, backend, store: Store) -> None:
        super().__init__(application=app, title="Displays", default_width=560, default_height=560)
        self.backend = backend
        self.store = store
        self.displays: list[Display] = []
        self.display: Display | None = None
        self._loading = False
        self._save_source = 0
        self._reload_source = 0

        self.toasts = Adw.ToastOverlay()
        view = Adw.ToolbarView()
        view.add_top_bar(Adw.HeaderBar())
        view.set_content(self.toasts)
        self.set_content(view)

        self.stack = Gtk.Stack()
        self.toasts.set_child(self.stack)

        self.empty = Adw.StatusPage(
            icon_name="video-display-symbolic",
            title="No External Display",
            description="Connect a TV or monitor to adjust its picture.",
        )
        self.stack.add_named(self.empty, "empty")

        page = Adw.PreferencesPage()
        self.stack.add_named(page, "settings")

        # Which display
        group = Adw.PreferencesGroup()
        page.add(group)
        self.picker = Adw.ComboRow(title="Display")
        self.picker.connect("notify::selected", self._on_picked)
        group.add(self.picker)

        # Underscan
        self.underscan_group = Adw.PreferencesGroup(
            title="Underscan",
            description="Shrink the picture if the edges of the desktop are cut off by the TV.",
        )
        page.add(self.underscan_group)

        self.slider = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0.0, SLIDER_MAX, 0.0025)
        self.slider.set_draw_value(False)
        self.slider.set_hexpand(True)
        self.slider.add_mark(0.0, Gtk.PositionType.BOTTOM, "Off")
        self.slider.add_mark(SLIDER_MAX, Gtk.PositionType.BOTTOM, "More")
        self.slider.connect("value-changed", self._on_slider)
        self.slider.update_property([Gtk.AccessibleProperty.LABEL], ["Underscan"])

        self.percent = Gtk.Label(width_chars=5, xalign=1.0)
        self.percent.add_css_class("numeric")
        self.percent.add_css_class("dim-label")

        box = Gtk.Box(spacing=12, margin_top=12, margin_bottom=6, margin_start=12, margin_end=12)
        box.append(self.slider)
        box.append(self.percent)
        row = Adw.PreferencesRow(activatable=False)
        row.set_child(box)
        self.underscan_group.add(row)

        self.underscan_unavailable = Adw.ActionRow(
            title="Not available",
            subtitle=backend.unavailable_hint,
        )
        self.underscan_group.add(self.underscan_unavailable)
        self.underscan_row = row

        # Scaled resolution
        self.scale_group = Adw.PreferencesGroup(
            title="Size",
            description="Make text and windows larger, or fit more on the screen.",
        )
        page.add(self.scale_group)
        self.scale_rows: list[Adw.ActionRow] = []

        backend.on_displays_changed(self._queue_reload)
        self.reload()

    # -- loading ----------------------------------------------------------

    def _queue_reload(self) -> None:
        if self._reload_source:
            GLib.source_remove(self._reload_source)
        self._reload_source = GLib.timeout_add(300, self._reload_idle)

    def _reload_idle(self) -> bool:
        self._reload_source = 0
        self.reload()
        return GLib.SOURCE_REMOVE

    def reload(self) -> None:
        try:
            displays = self.backend.list_displays()
        except BackendError as error:
            self._toast(str(error))
            return

        self.displays = [d for d in displays if d.active and not d.builtin]
        if not self.displays:
            self.display = None
            self.stack.set_visible_child_name("empty")
            return
        self.stack.set_visible_child_name("settings")

        previous = self.display.connector if self.display else None
        index = next((i for i, d in enumerate(self.displays) if d.connector == previous), 0)

        self._loading = True
        self.picker.set_model(Gtk.StringList.new([d.name for d in self.displays]))
        self.picker.set_selected(index)
        self.picker.set_sensitive(len(self.displays) > 1)
        self._loading = False
        self._show(self.displays[index])

    def _on_picked(self, _row, _pspec) -> None:
        if self._loading:
            return
        index = self.picker.get_selected()
        if 0 <= index < len(self.displays):
            self._show(self.displays[index])

    def _show(self, display: Display) -> None:
        self.display = display
        self._loading = True

        supported = display.supports_underscan
        self.underscan_row.set_visible(supported)
        self.underscan_unavailable.set_visible(not supported)
        if supported:
            self.slider.set_value(min(display.underscan, SLIDER_MAX))
            self._show_percent(display.underscan)

        for row in self.scale_rows:
            self.scale_group.remove(row)
        self.scale_rows = []

        group_leader = None
        scales = display.supported_scales
        for scale in sorted(scales, reverse=True):
            looks_w, looks_h = display.looks_like(scale)
            title = f"Looks like {looks_w} × {looks_h}"
            if scale == max(scales) and len(scales) > 1:
                subtitle = "Larger Text"
            elif scale == min(scales) and len(scales) > 1:
                subtitle = "More Space"
            else:
                subtitle = ""
            row = Adw.ActionRow(title=title, subtitle=subtitle)
            check = Gtk.CheckButton(valign=Gtk.Align.CENTER)
            if group_leader is None:
                group_leader = check
            else:
                check.set_group(group_leader)
            check.set_active(abs(scale - display.scale) < 0.01)
            check.connect("toggled", self._on_scale, scale)
            row.add_prefix(check)
            row.set_activatable_widget(check)
            self.scale_group.add(row)
            self.scale_rows.append(row)
        self.scale_group.set_visible(len(scales) > 1)

        self._loading = False

    # -- underscan --------------------------------------------------------

    def _show_percent(self, amount: float) -> None:
        self.percent.set_label("Off" if amount <= 0 else f"{amount * 100:.1f}%")

    def _on_slider(self, slider: Gtk.Scale) -> None:
        if self._loading or self.display is None:
            return
        amount = slider.get_value()
        if amount < 0.00125:
            amount = 0.0
        display = self.display
        try:
            self.backend.set_underscan(display, amount)
        except BackendError as error:
            self._toast(str(error))
            return
        display.underscan = amount
        self._show_percent(amount)

        # Apply on every movement, write to disk once the slider rests.
        if self._save_source:
            GLib.source_remove(self._save_source)
        self._save_source = GLib.timeout_add(500, self._save, display, amount)

    def _save(self, display: Display, amount: float) -> bool:
        self._save_source = 0
        if not self.backend.persists_settings:
            self.store.set_underscan(display, amount)
        return GLib.SOURCE_REMOVE

    # -- scale ------------------------------------------------------------

    def _on_scale(self, check: Gtk.CheckButton, scale: float) -> None:
        if self._loading or self.display is None or not check.get_active():
            return
        try:
            self.backend.set_scale(self.display, scale)
        except BackendError as error:
            self._toast(str(error))
            self._queue_reload()

    def _toast(self, message: str) -> None:
        self.toasts.add_toast(Adw.Toast(title=message))


class App(Adw.Application):
    def __init__(self) -> None:
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)

    def do_activate(self) -> None:
        window = self.props.active_window
        if window is None:
            try:
                backend = get_backend()
            except BackendError as error:
                print(f"underscale: {error}", file=sys.stderr)
                self.quit()
                return
            window = Window(self, backend, Store())
        window.present()


def main() -> int:
    return App().run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
