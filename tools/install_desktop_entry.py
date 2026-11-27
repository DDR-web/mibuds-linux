#!/usr/bin/env python3
"""Register MiBuds Linux in the user's Linux application launcher & Wayland taskbar."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
ICON_NAME = "mibuds-linux"
DESKTOP_ID = "io.github.mibuds_linux"
SYSTEM_DESKTOP_PATH = Path(f"/usr/share/applications/{DESKTOP_ID}.desktop")


def ensure_desktop_entry(quiet: bool = False) -> Path:
    """Install/update user .desktop launcher and hicolor icons when running from source."""
    if str(ROOT_DIR).startswith("/opt/") and SYSTEM_DESKTOP_PATH.is_file():
        return SYSTEM_DESKTOP_PATH

    data_home = Path(os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share"))
    apps_dir = data_home / "applications"
    pixmaps_dir = data_home / "pixmaps"
    hicolor_root = data_home / "icons" / "hicolor"

    apps_dir.mkdir(parents=True, exist_ok=True)
    pixmaps_dir.mkdir(parents=True, exist_ok=True)

    # Remove legacy launchers from earlier builds
    for legacy_name in ("xiaomi-earbuds-linux.desktop", "io.github.xiaomi_earbuds_linux.desktop"):
        legacy_desktop = apps_dir / legacy_name
        if legacy_desktop.exists():
            legacy_desktop.unlink()

    src_icon = ROOT_DIR / "assets" / "icon.png"
    icon_targets = [
        pixmaps_dir / f"{ICON_NAME}.png",
        pixmaps_dir / f"{DESKTOP_ID}.png",
    ]
    for size in ("256x256", "128x128", "64x64", "48x48"):
        size_dir = hicolor_root / size / "apps"
        size_dir.mkdir(parents=True, exist_ok=True)
        icon_targets.append(size_dir / f"{ICON_NAME}.png")
        icon_targets.append(size_dir / f"{DESKTOP_ID}.png")

    if src_icon.is_file():
        data = src_icon.read_bytes()
        for target in icon_targets:
            if not target.exists() or target.read_bytes() != data:
                target.write_bytes(data)

    launcher_script = ROOT_DIR / "run_mibuds.sh"
    if launcher_script.is_file():
        exec_cmd = f'"{launcher_script}"'
    else:
        exec_cmd = f'"{sys.executable}" "{ROOT_DIR / "mibuds_app.py"}"'

    desktop_path = apps_dir / f"{DESKTOP_ID}.desktop"
    desktop_content = "\n".join([
        "[Desktop Entry]",
        "Type=Application",
        "Version=1.0",
        "Name=MiBuds Linux",
        "GenericName=Xiaomi & Redmi Earbuds Manager",
        "GenericName[it]=Gestione Auricolari Xiaomi e Redmi",
        "Comment=Unofficial Linux desktop companion for Xiaomi & Redmi earbuds (ANC, Transparency, Gestures, EQ, Battery)",
        "Comment[it]=App desktop Linux non ufficiale per auricolari Xiaomi e Redmi (ANC, Trasparenza, Gestures, EQ, Batteria)",
        f"Exec={exec_cmd}",
        f"Path={ROOT_DIR}",
        f"Icon={ICON_NAME}",
        "Terminal=false",
        "Categories=AudioVideo;Audio;Settings;HardwareSettings;Utility;",
        "Keywords=mibuds;xiaomi;redmi;buds;earbuds;headphones;bluetooth;anc;dolby;auricolari;cuffie;",
        f"StartupWMClass={DESKTOP_ID}",
        "StartupNotify=true",
        "",
    ])

    if not desktop_path.exists() or desktop_path.read_text(encoding="utf-8") != desktop_content:
        desktop_path.write_text(desktop_content, encoding="utf-8")
        desktop_path.chmod(0o755)

    for cmd in (
        ["update-desktop-database", str(apps_dir)],
        ["gtk-update-icon-cache", "-f", "-t", str(hicolor_root)],
    ):
        if shutil.which(cmd[0]):
            try:
                subprocess.run(cmd, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except OSError:
                pass

    if not quiet:
        print(f"Installed desktop launcher: {desktop_path}")
        print(f"Installed themed icons: {ICON_NAME}, {DESKTOP_ID}")
    return desktop_path


if __name__ == "__main__":
    ensure_desktop_entry(quiet=False)
