#!/usr/bin/env bash
# Phase 0: check that the Intel display scaler accepts a shrunk primary plane
# on the HDMI output. This is the mechanism the Mutter patch relies on.
#
# Run from a TEXT CONSOLE, not from inside GNOME:
#   1. Press Ctrl+Alt+F3 and log in.
#   2. Run:  ~/Projects/underscale/scripts/phase0-scaler-test.sh
#   3. Look at the TV, press Enter to end the test.
#   4. Press Ctrl+Alt+F2 (or F1) to return to GNOME.
#
# Expected on the TV: a colour test pattern, centred, slightly smaller than the
# screen, with a black border on all four sides.
set -u

DRIVER=i915
SCALE="${1:-0.95}"

if [ -n "${WAYLAND_DISPLAY:-}" ] || [ -n "${DISPLAY:-}" ]; then
  echo "This must run from a text console (Ctrl+Alt+F3), not inside GNOME." >&2
  exit 1
fi

# Find the connected HDMI connector and the CRTC that can drive it.
conn_line=$(modetest -M "$DRIVER" -c 2>/dev/null | grep -E '^[0-9]+\s+[0-9]+\s+connected\s+HDMI' | head -1)
if [ -z "$conn_line" ]; then
  echo "No connected HDMI display found." >&2
  exit 1
fi
CONN=$(awk '{print $1}' <<<"$conn_line")

# Use the second CRTC (pipe B) and its first plane; pipe A drives the laptop panel.
CRTC=$(modetest -M "$DRIVER" -p 2>/dev/null | awk '/^CRTCs:/{f=1;next} /^Planes:/{f=0} f && /^[0-9]+\s/{print $1}' | sed -n 2p)
PLANE=$(modetest -M "$DRIVER" -p 2>/dev/null | awk '/^Planes:/{f=1;next} f && /^[0-9]+\s/ && $NF=="0x00000002"{print $1; exit}')

W=1920; H=1080
X=$(awk -v w=$W -v s="$SCALE" 'BEGIN{printf "%d", (w - w*s)/2}')
Y=$(awk -v h=$H -v s="$SCALE" 'BEGIN{printf "%d", (h - h*s)/2}')

echo "connector=$CONN crtc=$CRTC plane=$PLANE scale=$SCALE offset=+$X+$Y"
echo "Starting test. Look at the TV, then press Enter here to stop."
echo

modetest -M "$DRIVER" -a \
  -s "${CONN}@${CRTC}:${W}x${H}-60" \
  -P "${PLANE}@${CRTC}:${W}x${H}+${X}+${Y}*${SCALE}" \
  2>&1 | tee /tmp/underscale-phase0.log
status=${PIPESTATUS[0]}

echo
if [ "$status" -eq 0 ] && ! grep -qiE 'failed|invalid|error' /tmp/underscale-phase0.log; then
  echo "RESULT: the kernel ACCEPTED the scaled plane."
  echo "If the TV showed a centred, shrunk pattern with black borders, phase 0 passed."
else
  echo "RESULT: the kernel REJECTED the scaled plane (exit $status)."
  echo "Log saved to /tmp/underscale-phase0.log"
fi
