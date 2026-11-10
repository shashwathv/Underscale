#!/usr/bin/env bash
# Install the Underscale app, underscalectl and the daemon without a package
# manager, under /usr/local. Used on Fedora and Debian; Arch uses the PKGBUILD.
#
#   packaging/install-app.sh              install
#   packaging/install-app.sh --uninstall  remove
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PREFIX=/usr/local
LIBDIR="$PREFIX/lib/underscale-app"

SUDO=""
[ "$(id -u)" -eq 0 ] || SUDO="sudo"

FILES=(
  "$PREFIX/bin/underscale"
  "$PREFIX/bin/underscalectl"
  "$PREFIX/bin/underscale-daemon"
  "$PREFIX/lib/systemd/user/underscale-daemon.service"
  "$PREFIX/share/applications/io.github.underscale.Underscale.desktop"
)

if [ "${1:-}" = "--uninstall" ]; then
  $SUDO rm -rf "$LIBDIR"
  $SUDO rm -f "${FILES[@]}"
  echo "Underscale app removed."
  exit 0
fi

$SUDO rm -rf "$LIBDIR"
$SUDO install -d "$LIBDIR/underscale/backends"
$SUDO install -m644 "$ROOT"/underscale/*.py "$LIBDIR/underscale/"
$SUDO install -m644 "$ROOT"/underscale/backends/*.py "$LIBDIR/underscale/backends/"

# Launchers that find the package in its private directory.
launcher() { # name module
  local tmp
  tmp="$(mktemp)"
  cat > "$tmp" <<EOF
#!/usr/bin/python3
import sys

sys.path.insert(0, "$LIBDIR")
from underscale.$2 import main

sys.exit(main())
EOF
  $SUDO install -Dm755 "$tmp" "$PREFIX/bin/$1"
  rm -f "$tmp"
}
launcher underscale app
launcher underscalectl cli
launcher underscale-daemon daemon

tmp="$(mktemp)"
sed "s|^ExecStart=.*|ExecStart=$PREFIX/bin/underscale-daemon|" "$ROOT/data/underscale-daemon.service" > "$tmp"
$SUDO install -Dm644 "$tmp" "$PREFIX/lib/systemd/user/underscale-daemon.service"
rm -f "$tmp"

$SUDO install -Dm644 "$ROOT/data/io.github.underscale.Underscale.desktop" \
  "$PREFIX/share/applications/io.github.underscale.Underscale.desktop"

echo "Underscale app installed under $PREFIX."
