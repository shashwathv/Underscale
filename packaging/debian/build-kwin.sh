#!/usr/bin/env bash
# Rebuild Debian's own KWin package with plane-scaled overscan added.
#
#   packaging/debian/build-kwin.sh [output-dir]
#
# Takes the source package of the KWin version your Debian release ships,
# applies kwin-underscale/port.py to it, and builds .deb files into output-dir
# (default: ./build/debian-kwin). Nothing is installed except build tools.
#
# UNTESTED on real hardware: the result builds, but has not been run.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUT="$(mkdir -p "${1:-$ROOT/build/debian-kwin}" && cd "${1:-$ROOT/build/debian-kwin}" && pwd)"
JOBS="${UNDERSCALE_JOBS:-$(nproc)}"

SUDO=""
[ "$(id -u)" -eq 0 ] || SUDO="sudo"
export DEBIAN_FRONTEND=noninteractive

# Source packages need "deb-src" entries. Add a temporary one that mirrors the
# enabled binary entries, and take it away again when done.
SRC_LIST=/etc/apt/sources.list.d/underscale-src.sources
cleanup() { $SUDO rm -f "$SRC_LIST"; }
trap cleanup EXIT

echo "==> Enabling source packages (temporary)"
if [ -f /etc/apt/sources.list.d/debian.sources ]; then
  sed 's/^Types:.*/Types: deb-src/' /etc/apt/sources.list.d/debian.sources | $SUDO tee "$SRC_LIST" >/dev/null
elif [ -f /etc/apt/sources.list ] && grep -q '^deb ' /etc/apt/sources.list; then
  # Old one-line format: write the equivalent deb-src lines.
  SRC_LIST=/etc/apt/sources.list.d/underscale-src.list
  grep '^deb ' /etc/apt/sources.list | sed 's/^deb /deb-src /' | $SUDO tee "$SRC_LIST" >/dev/null
else
  echo "Could not find your APT sources to enable source packages." >&2
  exit 1
fi

$SUDO apt-get update
echo "==> Installing build tools"
$SUDO apt-get install -y --no-install-recommends build-essential devscripts dpkg-dev fakeroot python3

cd "$OUT"
rm -rf src && mkdir src && cd src

echo "==> Fetching Debian's KWin source package"
apt-get source kwin
SRC_DIR="$(find . -maxdepth 1 -mindepth 1 -type d -name 'kwin-*' | head -n 1)"
[ -n "$SRC_DIR" ] || { echo "KWin source directory not found." >&2; exit 1; }

echo "==> Installing KWin's build dependencies"
$SUDO apt-get build-dep -y kwin

cd "$SRC_DIR"
python3 "$ROOT/kwin-underscale/port.py" .

# Mark the version so the result is recognisable and newer than the stock build.
DEBFULLNAME="${DEBFULLNAME:-Underscale}" DEBEMAIL="${DEBEMAIL:-underscale@localhost}" \
  dch --local +underscale "Overscan compensation by plane scaling on drivers without an overscan property."

echo "==> Building (this takes a while)"
DEB_BUILD_OPTIONS="nocheck parallel=$JOBS" dpkg-buildpackage -b -uc -us

echo
echo "==> Built packages:"
find "$OUT/src" -maxdepth 1 -name '*.deb' | sort
