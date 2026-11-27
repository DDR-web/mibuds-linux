#!/usr/bin/env python3
"""MiBuds Linux Desktop Application (GTK3 Application + Themed HeaderBar + WebKit2)."""

from __future__ import annotations

import argparse
from pathlib import Path
import signal
import sys
from typing import Any

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("WebKit2", "4.1")
from gi.repository import Gtk, Gdk, Gio, GLib, WebKit2  # noqa: E402

from controllers.bluetooth.redmi_buds_8_pro import RedmiBuds8ProService  # noqa: E402
from tools.install_desktop_entry import DESKTOP_ID, ICON_NAME, ensure_desktop_entry  # noqa: E402
from mibuds_server import start_background_server  # noqa: E402

ROOT_DIR = Path(__file__).resolve().parent


def _hex_to_rgba(hex_color: str) -> Gdk.RGBA:
    rgba = Gdk.RGBA(0.0, 0.0, 0.0, 1.0)
    rgba.parse(hex_color)
    return rgba


def _build_gtk_theme_css(theme: dict[str, Any]) -> tuple[bytes, str]:
    mode = theme.get("mode", "dark")
    if mode == "light":
        bg = "#F5F6F8"
        fg = "#141418"
        border = "#E5E7EB"
        title_fg = "#686870"
        btn_bg = "#E8EAEF"
        btn_fg = "#3A3A40"
        btn_hover = "#D8DCE4"
    elif mode == "custom":
        bg = theme.get("bg", "#0A0E17")
        is_light = theme.get("custom_base") == "light"
        fg = "#141418" if is_light else "#F5F5F7"
        border = "rgba(0, 0, 0, 0.09)" if is_light else "rgba(255, 255, 255, 0.09)"
        title_fg = "#55555E" if is_light else "#9E9EA8"
        btn_bg = "rgba(0, 0, 0, 0.08)" if is_light else "rgba(255, 255, 255, 0.10)"
        btn_fg = "#26262C" if is_light else "#D4D4DC"
        btn_hover = "rgba(0, 0, 0, 0.15)" if is_light else "rgba(255, 255, 255, 0.18)"
    else:
        bg = "#000000"
        fg = "#F5F5F7"
        border = "#161618"
        title_fg = "#8E8E93"
        btn_bg = "#18181C"
        btn_fg = "#C4C4CA"
        btn_hover = "#2A2A30"

    css = f"""
        window, window.csd, window.background {{
            background-color: {bg};
            color: {fg};
            border-radius: 16px;
        }}
        window.maximized, window.maximized.csd {{
            border-radius: 0px;
        }}
        headerbar.xiaomi-headerbar {{
            background-color: {bg};
            background-image: none;
            border-bottom: 1px solid {border};
            box-shadow: none;
            min-height: 36px;
            padding: 0 12px;
            border-top-left-radius: 16px;
            border-top-right-radius: 16px;
        }}
        window.maximized headerbar.xiaomi-headerbar {{
            border-radius: 0px;
        }}
        headerbar.xiaomi-headerbar label.title {{
            color: {title_fg};
            font-size: 12.5px;
            font-weight: 500;
        }}
        headerbar.xiaomi-headerbar button.titlebutton {{
            background-color: {btn_bg};
            background-image: none;
            color: {btn_fg};
            border: none;
            box-shadow: none;
            border-radius: 999px;
            min-width: 24px;
            min-height: 24px;
            padding: 2px;
            margin: 0 2px;
        }}
        headerbar.xiaomi-headerbar button.titlebutton:hover {{
            background-color: {btn_hover};
            color: {fg};
        }}
        headerbar.xiaomi-headerbar button.titlebutton.close:hover {{
            background-color: #E5484D;
            color: #FFFFFF;
        }}
    """
    return css.encode("utf-8"), bg


class XiaomiEarbudsApplication(Gtk.Application):
    """GTK Application with Wayland/X11 taskbar icon registration and themed window."""

    def __init__(self, width: int, height: int, no_bt_scan: bool) -> None:
        super().__init__(
            application_id=DESKTOP_ID,
            flags=Gio.ApplicationFlags.FLAGS_NONE,
        )
        self._width = width
        self._height = height
        self._no_bt_scan = no_bt_scan
        self._service: RedmiBuds8ProService | None = None
        self._httpd = None
        self._win: Gtk.ApplicationWindow | None = None
        self._webview: WebKit2.WebView | None = None
        self._css_provider: Gtk.CssProvider | None = None

    def _on_theme_changed(self, theme: dict[str, Any]) -> None:
        GLib.idle_add(self._apply_gtk_theme, theme)

    def _apply_gtk_theme(self, theme: dict[str, Any]) -> bool:
        if self._css_provider is None:
            return False
        css_bytes, bg_hex = _build_gtk_theme_css(theme)
        try:
            self._css_provider.load_from_data(css_bytes)
        except GLib.Error:
            pass
        if self._webview is not None:
            self._webview.set_background_color(_hex_to_rgba(bg_hex))
        return False

    def do_activate(self) -> None:  # noqa: N802
        if self._win is not None:
            self._win.present()
            return

        if self._service is None:
            self._service = RedmiBuds8ProService(
                enable_bluetooth_auto=not self._no_bt_scan,
                theme_callback=self._on_theme_changed,
            )
            self._httpd, _srv_thread, port = start_background_server(
                host="127.0.0.1",
                port=0,
                service=self._service,
            )
        else:
            port = self._httpd.server_address[1]

        self._css_provider = Gtk.CssProvider()
        screen = Gdk.Screen.get_default()
        if screen is not None:
            Gtk.StyleContext.add_provider_for_screen(
                screen,
                self._css_provider,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
            )

        win = Gtk.ApplicationWindow(application=self, title="MiBuds Linux")
        self._win = win
        win.set_default_size(self._width, self._height)
        win.set_size_request(400, 620)
        win.set_resizable(True)
        win.set_decorated(True)
        win.set_position(Gtk.WindowPosition.CENTER)
        win.set_wmclass(DESKTOP_ID, DESKTOP_ID)

        icon_path = ROOT_DIR / "assets" / "icon.png"
        if icon_path.is_file():
            try:
                win.set_icon_from_file(str(icon_path))
                Gtk.Window.set_default_icon_from_file(str(icon_path))
            except GLib.Error:
                pass

        header = Gtk.HeaderBar()
        header.set_title("MiBuds Linux")
        header.set_show_close_button(True)
        header.set_decoration_layout(":minimize,maximize,close")
        header.get_style_context().add_class("xiaomi-headerbar")
        win.set_titlebar(header)

        webview = WebKit2.WebView()
        self._webview = webview
        settings = webview.get_settings()
        settings.set_enable_developer_extras(False)
        settings.set_enable_smooth_scrolling(True)
        settings.set_media_playback_requires_user_gesture(False)
        settings.set_hardware_acceleration_policy(WebKit2.HardwareAccelerationPolicy.ON_DEMAND)

        self._apply_gtk_theme(self._service.get_state().get("theme", {}))
        webview.load_uri(f"http://127.0.0.1:{port}/index.html")

        win.add(webview)
        win.show_all()

    def do_shutdown(self) -> None:  # noqa: N802
        try:
            if self._service is not None:
                self._service.shutdown()
            if self._httpd is not None:
                self._httpd.shutdown()
                self._httpd.server_close()
        finally:
            Gtk.Application.do_shutdown(self)


def main() -> None:
    parser = argparse.ArgumentParser(description="MiBuds Linux Desktop")
    parser.add_argument("--no-bt-scan", action="store_true", help="Skip initial BlueZ scan")
    parser.add_argument("--width", type=int, default=1080)
    parser.add_argument("--height", type=int, default=720)
    args, remaining = parser.parse_known_args()

    try:
        ensure_desktop_entry(quiet=True)
    except Exception:
        pass

    # Match io.github.mibuds_linux.desktop on both Wayland and X11
    GLib.set_prgname(DESKTOP_ID)
    GLib.set_application_name("MiBuds Linux")
    Gtk.Window.set_default_icon_name(ICON_NAME)

    app = XiaomiEarbudsApplication(args.width, args.height, args.no_bt_scan)
    signal.signal(signal.SIGINT, lambda *_: GLib.idle_add(app.quit))
    sys.exit(app.run([sys.argv[0], *remaining]))


if __name__ == "__main__":
    main()
