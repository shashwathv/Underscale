#!/usr/bin/env bash
# Rebuild Fedora's own KWin package with plane-scaled overscan added.
#
#   packaging/fedora/build-kwin.sh [output-dir]
#
# Takes the source package of the KWin version your Fedora release ships,
# applies kwin-underscale/port.py to it, and builds RPMs into output-dir
# (default: ./build/fedora-kwin). Nothing is installed except build tools.
#
# UNTESTED on real hardware: the result builds, but has not been run.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUT="$(mkdir -p "${1:-$ROOT/build/fedora-kwin}" && cd "${1:-$ROOT/build/fedora-kwin}" && pwd)"
JOBS="${UNDERSCALE_JOBS:-$(nproc)}"

SUDO=""
[ "$(id -u)" -eq 0 ] || SUDO="sudo"

echo "==> Installing build tools"
$SUDO dnf install -y rpm-build dnf-plugins-core python3

TOP="$OUT/rpmbuild"
rm -rf "$TOP"
mkdir -p "$TOP"/{SOURCES,SPECS,SRPMS}

echo "==> Fetching Fedora's KWin source package"
( cd "$TOP/SRPMS" && dnf download --source kwin )
rpm --define "_topdir $TOP" -i "$TOP"/SRPMS/kwin-*.src.rpm

SPEC="$TOP/SPECS/kwin.spec"
cp "$ROOT/kwin-underscale/port.py" "$TOP/SOURCES/underscale-port.py"

# Add the porting script as a source and run it at the end of %prep, and mark
# the release so the result is recognisable and newer than the stock build.
python3 - "$SPEC" <<'EOF'
import re
import sys

path = sys.argv[1]
lines = open(path, encoding="utf-8").read().split("\n")

out, source_added, prep_added, release_marked = [], False, False, False
in_prep = False
for line in lines:
    if not release_marked and re.match(r"^Release:\s*\S", line):
        line = line.rstrip() + ".underscale"
        release_marked = True
    # A new section ends %prep: run the port just before it.
    if in_prep and re.match(r"^%(build|generate_buildrequires|conf|install|check)\b", line):
        out.append("python3 %{SOURCE9999} .")
        out.append("")
        in_prep, prep_added = False, True
    out.append(line)
    if not source_added and re.match(r"^Source0?:", line):
        out.append("Source9999: underscale-port.py")
        source_added = True
    if line.strip() == "%prep":
        in_prep = True

if not (source_added and prep_added and release_marked):
    sys.exit(f"could not adapt the spec file (source={source_added}, prep={prep_added}, release={release_marked})")
open(path, "w", encoding="utf-8").write("\n".join(out))
EOF

echo "==> Installing KWin's build dependencies"
$SUDO dnf builddep -y "$SPEC"

echo "==> Building (this takes a while)"
rpmbuild --define "_topdir $TOP" \
         --define "debug_package %{nil}" \
         --define "_smp_build_ncpus $JOBS" \
         -bb "$SPEC"

echo
echo "==> Built packages:"
find "$TOP/RPMS" -name '*.rpm' | sort
