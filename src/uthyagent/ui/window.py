"""GTK4 desktop window for UthyAgent.

The UI is deliberately an adapter around callbacks.  It does not start an
automation backend or make assumptions about a particular provider.  PyGObject
is loaded when :class:`UthyWindow` is instantiated, allowing the rest of the
package to be imported on headless machines and in CI.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

CSS = """
window { background: #0d1512; color: #e7f0eb; }
.surface { background-color: alpha(#19372b, .84); border: 1px solid alpha(#8ee0b2, .16); border-radius: 14px; }
.sidebar { background-color: alpha(#10251d, .94); border-right: 1px solid alpha(#8ee0b2, .14); }
.brand { color: #b6f3cb; font-size: 18px; font-weight: 700; }
.muted { color: #a6b8af; }
.status { color: #b6f3cb; font-weight: 600; }
.nav button { padding: 10px 12px; border-radius: 9px; color: #c6d8ce; }
.nav button:hover, .nav button:checked { background-color: alpha(#65ca91, .18); color: #edfff3; }
button.suggested-action { background: #62c98c; color: #092014; font-weight: 700; }
button.destructive-action { color: #ffd0c7; }
.entry, textview { background-color: alpha(#07100c, .48); color: #effaf3; border: 1px solid alpha(#8ee0b2, .23); border-radius: 10px; }
.timeline-row { border-bottom: 1px solid alpha(#8ee0b2, .10); padding: 7px 0; }
.badge { background-color: alpha(#65ca91, .16); color: #b6f3cb; border-radius: 999px; padding: 4px 9px; }
"""

CSS_LIGHT = """
window { background: #f2f6f4; color: #15221d; }
.surface { background-color: alpha(#ffffff, .82); border: 1px solid alpha(#244b37, .15); border-radius: 14px; }
.sidebar { background-color: alpha(#e4eee8, .94); border-right: 1px solid alpha(#244b37, .14); }
.brand { color: #246e49; font-size: 18px; font-weight: 700; }
.muted { color: #53665b; }
.status { color: #246e49; font-weight: 600; }
.nav button { padding: 10px 12px; border-radius: 9px; color: #31483b; }
.nav button:hover, .nav button:checked { background-color: alpha(#65ca91, .24); color: #15221d; }
button.suggested-action { background: #77d6a1; color: #10251a; font-weight: 700; }
button.destructive-action { color: #9b2f26; }
.entry, textview { background-color: alpha(#ffffff, .86); color: #15221d; border: 1px solid alpha(#244b37, .23); border-radius: 10px; }
.timeline-row { border-bottom: 1px solid alpha(#244b37, .10); padding: 7px 0; }
.badge { background-color: alpha(#65ca91, .22); color: #246e49; border-radius: 999px; padding: 4px 9px; }
"""


class UthyWindow:
    """Build and own the UthyAgent GTK4 window.

    ``on_submit`` receives ``(request, mode)``; the other callbacks are
    optional and intentionally have no default side effects.  ``window`` is
    the underlying ``Gtk.ApplicationWindow`` for integrations that need it.
    """

    def __init__(
        self,
        application: Any = None,
        *,
        on_submit: Callable[[str, str], None] | None = None,
        on_stop: Callable[[], None] | None = None,
        on_refresh: Callable[[], None] | None = None,
        on_approve: Callable[[], None] | None = None,
    ) -> None:
        Gtk, Gdk = self._load_gtk()
        self.Gtk, self.Gdk = Gtk, Gdk
        self.on_submit = on_submit or (lambda request, mode: None)
        self.on_stop = on_stop or (lambda: None)
        self.on_refresh = on_refresh or (lambda: None)
        self.on_approve = on_approve or (lambda: None)
        self._timeline: list[Any] = []
        self.window = Gtk.ApplicationWindow(application=application)
        self.window.set_title("UthyAgent")
        self.window.set_default_size(1260, 760)
        self.window.set_size_request(900, 560)
        self._install_css(Gtk, Gdk)
        self._build()

    @staticmethod
    def _load_gtk() -> tuple[Any, Any]:
        try:
            import gi  # type: ignore

            gi.require_version("Gtk", "4.0")
            from gi.repository import Gdk, Gtk  # type: ignore

            return Gtk, Gdk
        except (ImportError, ValueError) as exc:
            raise RuntimeError(
                "GTK4/PyGObject is required to create UthyWindow; install "
                "python3-gi and gir1.2-gtk-4.0 on Linux."
            ) from exc

    def _install_css(self, Gtk: Any, Gdk: Any) -> None:
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS, -1)
        self._css_provider = provider
        display = Gdk.Display.get_default()
        if display is not None:
            Gtk.StyleContext.add_provider_for_display(
                display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )

    def _label(self, text: str, style: str | None = None) -> Any:
        label = self.Gtk.Label(label=text, xalign=0)
        if style:
            label.add_css_class(style)
        return label

    def _build(self) -> None:
        Gtk = self.Gtk
        root = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        self.window.set_child(root)

        sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        sidebar.set_size_request(205, -1)
        sidebar.add_css_class("sidebar")
        sidebar.set_margin_top(22)
        sidebar.set_margin_bottom(18)
        sidebar.set_margin_start(16)
        sidebar.set_margin_end(12)
        root.append(sidebar)
        brand_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=9)
        logo_path = Path(__file__).resolve().parent.parent / "resources" / "app-logo.png"
        if logo_path.is_file():
            logo = Gtk.Image.new_from_file(str(logo_path))
            logo.set_pixel_size(48)
            logo.set_tooltip_text("UthyAgent app logo")
            brand_row.append(logo)
        brand_row.append(self._label("UthyAgent", "brand"))
        sidebar.append(brand_row)
        sidebar.append(self._label("Desktop agent workspace", "muted"))
        nav = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        nav.add_css_class("nav")
        sidebar.append(nav)
        self.nav_buttons: list[Any] = []
        for index, name in enumerate(("Home", "Task History", "Settings")):
            button = Gtk.CheckButton(label=name)
            button.set_halign(Gtk.Align.FILL)
            button.set_tooltip_text(
                f"Open {name}" if index == 0 else f"{name} view is not included in this alpha"
            )
            button.set_active(index == 0)
            if index != 0:
                button.set_sensitive(False)
            button.connect("toggled", self._on_nav_toggled, index)
            nav.append(button)
            self.nav_buttons.append(button)
        self.theme_button = Gtk.ToggleButton(label="Use light theme")
        self.theme_button.set_tooltip_text("Switch between dark and light themes")
        self.theme_button.set_active(False)
        self.theme_button.connect("toggled", self._toggle_theme)
        sidebar.append(self.theme_button)
        spacer = Gtk.Box()
        spacer.set_vexpand(True)
        sidebar.append(spacer)
        sidebar.append(self._label("Linux-first controls", "muted"))

        main = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        main.set_margin_top(22)
        main.set_margin_bottom(22)
        main.set_margin_start(10)
        main.set_margin_end(10)
        main.set_hexpand(True)
        main.set_vexpand(True)
        root.append(main)
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        main.append(header)
        title_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        title_box.set_hexpand(True)
        header.append(title_box)
        title_box.append(self._label("What should I do on your desktop?"))
        title_box.append(
            self._label("Describe a task, review the plan, then run it safely.", "muted")
        )
        self.status_label = self._label("Ready", "status")
        self.provider_label = self._label("No model configured · no remote inference", "badge")
        self.provider_label.set_wrap(True)
        header.append(self.provider_label)
        header.append(self.status_label)

        composer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        composer.add_css_class("surface")
        composer.set_margin_top(2)
        composer.set_margin_start(2)
        composer.set_margin_end(2)
        composer.set_margin_top(2)
        composer.set_margin_bottom(2)
        composer.set_margin_start(14)
        composer.set_margin_end(14)
        composer.set_margin_top(14)
        composer.set_margin_bottom(14)
        main.append(composer)
        self.request_view = Gtk.TextView()
        self.request_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.request_view.set_accepts_tab(False)
        self.request_view.set_size_request(-1, 112)
        self.request_view.set_tooltip_text("Task request")
        self.request_view.get_accessible().update_property(
            Gtk.AccessibleProperty.LABEL, "Task request"
        )
        composer.append(self.request_view)
        controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        composer.append(controls)
        controls.append(self._label("Run mode:"))
        self.mode = Gtk.DropDown.new_from_strings(
            ["Observe", "Assisted", "Autonomous", "Restricted"]
        )
        self.mode.set_selected(1)
        self.mode.set_tooltip_text("Choose how much autonomy to allow")
        controls.append(self.mode)
        filler = Gtk.Box()
        filler.set_hexpand(True)
        controls.append(filler)
        self.run_button = Gtk.Button(label="Run task")
        self.run_button.add_css_class("suggested-action")
        self.run_button.set_tooltip_text("Submit the task request")
        self.run_button.connect("clicked", self._submit)
        controls.append(self.run_button)
        self.stop_button = Gtk.Button(label="Stop")
        self.stop_button.add_css_class("destructive-action")
        self.stop_button.set_tooltip_text("Stop the current task")
        self.stop_button.connect("clicked", lambda *_: self.on_stop())
        controls.append(self.stop_button)

        timeline_surface = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        timeline_surface.add_css_class("surface")
        timeline_surface.set_vexpand(True)
        timeline_surface.set_margin_start(2)
        timeline_surface.set_margin_end(2)
        timeline_surface.set_margin_start(14)
        timeline_surface.set_margin_end(14)
        timeline_surface.set_margin_top(14)
        timeline_surface.set_margin_bottom(14)
        main.append(timeline_surface)
        timeline_surface.append(self._label("Execution timeline"))
        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        timeline_surface.append(scroll)
        self.timeline_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        scroll.set_child(self.timeline_box)
        self.add_timeline("Waiting for a task request")

        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        right.set_size_request(275, -1)
        right.set_margin_top(22)
        right.set_margin_bottom(22)
        right.set_margin_end(16)
        root.append(right)
        pane = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        pane.add_css_class("surface")
        pane.set_vexpand(True)
        pane.set_margin_top(2)
        pane.set_margin_bottom(2)
        pane.set_margin_start(2)
        pane.set_margin_end(2)
        pane.set_margin_top(14)
        pane.set_margin_bottom(14)
        pane.set_margin_start(14)
        pane.set_margin_end(14)
        right.append(pane)
        pane.append(self._label("Live desktop status"))
        self.desktop_status = self._label("No desktop observation yet", "muted")
        self.desktop_status.set_wrap(True)
        pane.append(self.desktop_status)
        pane.append(self._label("Session", "muted"))
        pane.append(self._label("Ready for an observation", "badge"))
        pane.append(self._label("Inference route", "muted"))
        self.inference_status = self._label("No provider configured", "status")
        pane.append(self.inference_status)
        pane.append(self._label("Safety", "muted"))
        pane.append(self._label("Approval gates enabled", "status"))
        refresh = Gtk.Button(label="Refresh status")
        refresh.set_tooltip_text("Refresh desktop status")
        refresh.connect("clicked", lambda *_: self.on_refresh())
        pane.append(refresh)
        approval = Gtk.Button(label="Approve pending action")
        approval.set_tooltip_text("Approve the pending action")
        approval.connect("clicked", lambda *_: self.on_approve())
        approval.set_sensitive(False)
        pane.append(approval)
        self.approval_button = approval

    def _toggle_theme(self, button: Any) -> None:
        light = button.get_active()
        button.set_label("Use dark theme" if light else "Use light theme")
        self._css_provider.load_from_data(CSS_LIGHT if light else CSS, -1)

    def set_provider_status(self, text: str) -> None:
        self.provider_label.set_text(text)
        self.inference_status.set_text(text)

    def set_desktop_status(self, text: str) -> None:
        self.desktop_status.set_text(text)

    def set_approval_pending(self, pending: bool) -> None:
        self.approval_button.set_sensitive(bool(pending))

    def _on_nav_toggled(self, button: Any, index: int) -> None:
        if button.get_active():
            for position, other in enumerate(self.nav_buttons):
                if position != index:
                    other.set_active(False)

    def _submit(self, *_args: Any) -> None:
        buffer = self.request_view.get_buffer()
        request = buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), False).strip()
        modes = ("observe", "assisted", "autonomous", "restricted")
        self.on_submit(request, modes[self.mode.get_selected()])

    def set_status(self, text: str) -> None:
        self.status_label.set_text(text)

    def add_timeline(self, text: str) -> None:
        row = self.Gtk.Box(orientation=self.Gtk.Orientation.HORIZONTAL, spacing=8)
        row.add_css_class("timeline-row")
        row.append(self._label(text, "muted"))
        self.timeline_box.append(row)
        self._timeline.append(row)

    def present(self) -> None:
        self.window.present()

    def close(self) -> None:
        self.window.close()


__all__ = ["UthyWindow"]
