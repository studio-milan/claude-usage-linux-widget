#!/usr/bin/env bash
# Claude Usage Indicator - installer Rev00
set -euo pipefail

REV="Rev00"
HERE="$(cd "$(dirname "$0")" && pwd)"
SRC="$HERE/claude-usage-indicator-${REV}.py"
BIN="$HOME/.local/bin/claude-usage-indicator-${REV}.py"
AUTOSTART="$HOME/.config/autostart"

echo "==> Installing dependencies (sudo password may be requested)"
sudo apt-get update -qq
sudo apt-get install -y python3-gi gir1.2-gtk-3.0 gir1.2-ayatanaappindicator3-0.1 \
    libnotify-bin gnome-shell-extension-appindicator

echo "==> Enabling Ubuntu AppIndicator extension (if not already enabled)"
gnome-extensions enable ubuntu-appindicators@ubuntu.com 2>/dev/null || true

echo "==> Installing script to $BIN"
mkdir -p "$HOME/.local/bin" "$AUTOSTART"
install -m 755 "$SRC" "$BIN"

echo "==> Registering autostart (older revisions are removed)"
rm -f "$AUTOSTART"/claude-usage-indicator*.desktop
cat > "$AUTOSTART/claude-usage-indicator-${REV}.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Claude Usage Indicator ${REV}
Comment=Claude session and weekly usage in the status bar
Exec=/usr/bin/python3 ${BIN}
X-GNOME-Autostart-enabled=true
X-GNOME-Autostart-Delay=10
EOF

echo "==> Quick check"
/usr/bin/python3 "$BIN" --once || true

echo "==> Starting indicator"
pkill -f "claude-usage-indicator-.*\.py" 2>/dev/null || true
nohup /usr/bin/python3 "$BIN" >/dev/null 2>&1 &
disown || true

echo "Done. Look for the double ring next to wifi and battery."
