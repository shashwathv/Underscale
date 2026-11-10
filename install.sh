#!/usr/bin/env bash
# Underscale installer for Arch Linux + GNOME.
#
#   ./install.sh              build and install everything
#   ./install.sh --uninstall  go back to stock Mutter and remove Underscale
#
# Run as your normal user. It asks for your password when it needs root.
set -euo pipefail

MUTTER_VERSION="51.1"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

say()  { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
fail() { printf '\n\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" -ne 0 ] || fail "Run this as your normal user, not as root or with sudo."
command -v pacman >/dev/null || fail "This installer is for Arch Linux (pacman not found)."

uninstall() {
  say "Stopping the Underscale daemon"
  systemctl --user disable --now underscale-daemon.service 2>/dev/null || true

  if pacman -Qq underscale >/dev/null 2>&1; then
    say "Removing the Underscale app"
    sudo pacman -R underscale
  fi

  if pacman -Qq mutter-underscale >/dev/null 2>&1; then
    say "Restoring stock Mutter (answer 'y' when pacman asks to remove mutter-underscale)"
    sudo pacman -S mutter
    say "Done. Log out and back in to finish."
  else
    say "Done. Stock Mutter was already installed."
  fi
}

if [ "${1:-}" = "--uninstall" ]; then
  uninstall
  exit 0
elif [ -n "${1:-}" ]; then
  fail "Unknown option '$1'. Use no option to install, or --uninstall."
fi

# --- checks ----------------------------------------------------------------

installed_mutter="$(pacman -Q mutter 2>/dev/null | awk '{print $2}' || true)"
[ -n "$installed_mutter" ] || fail "Mutter is not installed. Underscale needs GNOME."
case "$installed_mutter" in
  "$MUTTER_VERSION"-*) ;;
  *) fail "This release patches Mutter $MUTTER_VERSION, but you have $installed_mutter.
       Installing it would break GNOME Shell. Check the repository for a newer release." ;;
esac

if [ "${XDG_SESSION_TYPE:-}" != "wayland" ]; then
  printf '\nNote: this does not look like a Wayland session. Underscale only works on GNOME Wayland.\n'
fi

# --- build tools -----------------------------------------------------------

missing=()
for pkg in base-devel git; do
  pacman -Qq "$pkg" >/dev/null 2>&1 || missing+=("$pkg")
done
if [ "${#missing[@]}" -gt 0 ]; then
  say "Installing build tools: ${missing[*]}"
  sudo pacman -S --needed "${missing[@]}"
fi

# Print the path of the package a PKGBUILD in the current directory produces.
built_package() {
  makepkg --packagelist | grep -v -- '-debug-' | head -n 1
}

# --- patched Mutter --------------------------------------------------------

if pacman -Qq mutter-underscale >/dev/null 2>&1 \
   && [ "$(pacman -Q mutter-underscale | awk '{print $2}')" = "$MUTTER_VERSION-1" ] \
   && [ -z "${UNDERSCALE_REBUILD:-}" ]; then
  say "Patched Mutter is already installed; skipping its build"
  mutter_pkg=""
else
  say "Building the patched Mutter (about five minutes)"
  cd "$ROOT/mutter-underscale"
  makepkg -sf
  mutter_pkg="$(built_package)"
  [ -f "$mutter_pkg" ] || fail "The Mutter package was not produced."
fi

# --- app, CLI, daemon ------------------------------------------------------

say "Building the Underscale app"
cd "$ROOT"
makepkg -sf
app_pkg="$(built_package)"
[ -f "$app_pkg" ] || fail "The Underscale package was not produced."

# --- install ---------------------------------------------------------------

say "Installing"
if [ -n "$mutter_pkg" ]; then
  echo "pacman will ask to remove 'mutter', because the patched package replaces it. Answer 'y'."
  sudo pacman -U "$mutter_pkg" "$app_pkg"
else
  sudo pacman -U "$app_pkg"
fi

say "Enabling the daemon that restores your settings"
systemctl --user daemon-reload
systemctl --user enable --now underscale-daemon.service \
  || echo "Could not start the daemon now; it will start at your next login."

if [ -n "$mutter_pkg" ]; then
  say "Installed. Log out and back in, then open 'Underscale' from the app grid."
  echo "To log out now:  gnome-session-quit --logout"
else
  say "Installed. Open 'Underscale' from the app grid."
fi
echo "To undo everything later:  ./install.sh --uninstall"
