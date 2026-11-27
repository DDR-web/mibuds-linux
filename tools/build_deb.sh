#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PKG_NAME="mibuds-linux"
DESKTOP_ID="io.github.mibuds_linux"
VERSION="0.1.0~beta1"
RELEASE_LABEL="0.1.0-beta.1"
ARCH="all"
DIST_DIR="$ROOT_DIR/dist"
STAGE_DIR="$DIST_DIR/${PKG_NAME}_${RELEASE_LABEL}_${ARCH}"

rm -rf "$STAGE_DIR"
mkdir -p \
  "$STAGE_DIR/DEBIAN" \
  "$STAGE_DIR/opt/$PKG_NAME/tools" \
  "$STAGE_DIR/opt/$PKG_NAME/assets/locales" \
  "$STAGE_DIR/usr/bin" \
  "$STAGE_DIR/usr/share/applications" \
  "$STAGE_DIR/usr/share/pixmaps"

cp -r "$ROOT_DIR/controllers" "$STAGE_DIR/opt/$PKG_NAME/"
cp -r "$ROOT_DIR/utils" "$STAGE_DIR/opt/$PKG_NAME/"
cp -r "$ROOT_DIR/web_ui" "$STAGE_DIR/opt/$PKG_NAME/"
cp "$ROOT_DIR/tools/install_desktop_entry.py" "$STAGE_DIR/opt/$PKG_NAME/tools/"
cp "$ROOT_DIR/assets/icon.png" "$STAGE_DIR/opt/$PKG_NAME/assets/"
cp "$ROOT_DIR/assets/device_catalog.json" "$STAGE_DIR/opt/$PKG_NAME/assets/"
cp "$ROOT_DIR/assets/locales/en.json" "$STAGE_DIR/opt/$PKG_NAME/assets/locales/"
cp -r "$ROOT_DIR/assets/xiaomi_8_pro" "$STAGE_DIR/opt/$PKG_NAME/assets/"
cp "$ROOT_DIR/mibuds_server.py" "$STAGE_DIR/opt/$PKG_NAME/"
cp "$ROOT_DIR/mibuds_app.py" "$STAGE_DIR/opt/$PKG_NAME/"
cp "$ROOT_DIR/LICENSE" "$STAGE_DIR/opt/$PKG_NAME/"

# Strip compiled Python caches from package payload
find "$STAGE_DIR/opt/$PKG_NAME" -type d -name "__pycache__" -exec rm -rf {} +
find "$STAGE_DIR/opt/$PKG_NAME" -type f -name "*.pyc" -delete

# Install icons under both package name and reverse-DNS app_id for Wayland/X11 taskbars
cp "$ROOT_DIR/assets/icon.png" "$STAGE_DIR/usr/share/pixmaps/$PKG_NAME.png"
cp "$ROOT_DIR/assets/icon.png" "$STAGE_DIR/usr/share/pixmaps/$DESKTOP_ID.png"
for size in 48x48 64x64 128x128 256x256; do
  ICON_DIR="$STAGE_DIR/usr/share/icons/hicolor/$size/apps"
  mkdir -p "$ICON_DIR"
  cp "$ROOT_DIR/assets/icon.png" "$ICON_DIR/$PKG_NAME.png"
  cp "$ROOT_DIR/assets/icon.png" "$ICON_DIR/$DESKTOP_ID.png"
done

cat > "$STAGE_DIR/usr/bin/$PKG_NAME" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
cd /opt/mibuds-linux
exec python3 /opt/mibuds-linux/mibuds_app.py "$@"
EOF
chmod 0755 "$STAGE_DIR/usr/bin/$PKG_NAME"

cat > "$STAGE_DIR/usr/share/applications/$DESKTOP_ID.desktop" <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=MiBuds Linux
GenericName=Xiaomi & Redmi Earbuds Manager
GenericName[it]=Gestione Auricolari Xiaomi e Redmi
Comment=Unofficial Linux desktop companion for Xiaomi & Redmi earbuds (ANC, Transparency, Gestures, EQ, Battery)
Comment[it]=App desktop Linux non ufficiale per auricolari Xiaomi e Redmi (ANC, Trasparenza, Gestures, EQ, Batteria)
Exec=/usr/bin/$PKG_NAME
Icon=$PKG_NAME
Terminal=false
Categories=AudioVideo;Audio;Settings;HardwareSettings;Utility;
Keywords=mibuds;xiaomi;redmi;buds;earbuds;headphones;bluetooth;anc;dolby;auricolari;cuffie;
StartupWMClass=$DESKTOP_ID
StartupNotify=true
EOF

cat > "$STAGE_DIR/DEBIAN/postinst" <<'EOF'
#!/usr/bin/env bash
set -e
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database /usr/share/applications || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
  gtk-update-icon-cache -f -t /usr/share/icons/hicolor || true
fi
EOF
chmod 0755 "$STAGE_DIR/DEBIAN/postinst"

cat > "$STAGE_DIR/DEBIAN/postrm" <<'EOF'
#!/usr/bin/env bash
set -e
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database /usr/share/applications || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
  gtk-update-icon-cache -f -t /usr/share/icons/hicolor || true
fi
EOF
chmod 0755 "$STAGE_DIR/DEBIAN/postrm"

cat > "$STAGE_DIR/DEBIAN/control" <<EOF
Package: $PKG_NAME
Version: $VERSION
Section: sound
Priority: optional
Architecture: $ARCH
Depends: python3 (>= 3.10), python3-gi, gir1.2-gtk-3.0, gir1.2-webkit2-4.1, bluez
Recommends: gir1.2-gstreamer-1.0, gstreamer1.0-plugins-base, gstreamer1.0-plugins-good, alsa-utils
Maintainer: MiBuds Linux Contributors
Description: Unofficial Linux desktop companion for Xiaomi and Redmi earbuds
 Controls Xiaomi and Redmi earbuds (hardware-tested on REDMI Buds 8 Pro) over
 BlueZ RFCOMM with SAFER+ authentication. Features Dark OLED, Light, and
 Custom themes, Noise Cancellation, Transparency, Immersive Commute ambient
 soundscapes, Gestures, Spatial Audio, EQ presets, Battery telemetry, and
 Find Your Earphones.
EOF

mkdir -p "$DIST_DIR"
DEB_PATH="$DIST_DIR/${PKG_NAME}_${RELEASE_LABEL}_${ARCH}.deb"
dpkg-deb --root-owner-group --build "$STAGE_DIR" "$DEB_PATH"
echo "Built Debian package: $DEB_PATH"
