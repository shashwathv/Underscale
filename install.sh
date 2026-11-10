#!/usr/bin/env bash
# Underscale installer.
#
#   ./install.sh              build and install everything for this system
#   ./install.sh --uninstall  go back to the stock compositor and remove Underscale
#
# Supported:   Arch Linux    GNOME, KDE Plasma
#              Fedora        KDE Plasma
#              Debian        KDE Plasma
#
# Only GNOME on Arch has been tested on real hardware. The KDE Plasma builds
# compile but have not been run yet.
#
# Run as your normal user. It asks for your password when it needs root.
set -euo pipefail

MUTTER_VERSION="51.1"   # the Mutter version the GNOME patch is written for
KWIN_VERSION="6.8.2"    # the KWin version the Arch package is pinned to
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

say()  { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
fail() { printf '\n\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" -ne 0 ] || fail "Run this as your normal user, not as root or with sudo."

# --- what are we running on -------------------------------------------------

DISTRO="${UNDERSCALE_DISTRO:-}"
if [ -z "$DISTRO" ] && [ -r /etc/os-release ]; then
  # shellcheck disable=SC1091
  DISTRO="$(. /etc/os-release && echo "${ID:-}")"
fi
case "$DISTRO" in
  arch|fedora|debian) ;;
  *) fail "Unsupported distribution '${DISTRO:-unknown}'. Underscale supports Arch Linux, Fedora and Debian." ;;
esac

DESKTOP="${UNDERSCALE_DESKTOP:-}"
if [ -z "$DESKTOP" ]; then
  case ":$(echo "${XDG_CURRENT_DESKTOP:-}" | tr '[:upper:]' '[:lower:]'):" in
    *:gnome:*) DESKTOP=gnome ;;
    *:kde:*)   DESKTOP=kde ;;
  esac
fi
case "$DESKTOP" in
  gnome|kde) ;;
  *) fail "Could not tell which desktop you use (XDG_CURRENT_DESKTOP='${XDG_CURRENT_DESKTOP:-}').
       Underscale supports GNOME and KDE Plasma. Run this from inside your desktop session,
       or set UNDERSCALE_DESKTOP=gnome or UNDERSCALE_DESKTOP=kde." ;;
esac

if [ "$DESKTOP" = gnome ] && [ "$DISTRO" != arch ]; then
  fail "GNOME is only supported on Arch Linux so far. On $DISTRO, KDE Plasma is supported."
fi

ACTION=install
case "${1:-}" in
  "") ;;
  --uninstall) ACTION=uninstall ;;
  *) fail "Unknown option '$1'. Use no option to install, or --uninstall." ;;
esac

if [ "${XDG_SESSION_TYPE:-wayland}" != "wayland" ] && [ "$ACTION" = install ]; then
  printf '\nNote: this does not look like a Wayland session. Underscale only works on Wayland.\n'
fi

untested_notice() {
  cat <<'EOF'

  NOTE: Underscale on KDE Plasma is UNTESTED. The patched KWin compiles, but
  nobody has run it on real hardware yet. If the desktop does not start
  afterwards, switch to a text console with Ctrl+Alt+F3, log in, and run:
      ./install.sh --uninstall

EOF
  read -r -p "Continue? [y/N] " answer
  case "$answer" in y|Y|yes|YES) ;; *) echo "Nothing was changed."; exit 0 ;; esac
}

enable_daemon() {
  say "Enabling the daemon that restores your settings"
  systemctl --user daemon-reload
  systemctl --user enable --now underscale-daemon.service \
    || echo "Could not start the daemon now; it will start at your next login."
}

finish() { # $1 = "relogin" when the compositor was replaced
  if [ "${1:-}" = relogin ]; then
    say "Installed. Log out and back in, then open 'Underscale' from the app menu."
  else
    say "Installed. Open 'Underscale' from the app menu."
  fi
  if [ "$DESKTOP" = kde ]; then
    echo "On Plasma the same setting is also in System Settings > Display & Monitor (Overscan)."
  fi
  echo "To undo everything later:  ./install.sh --uninstall"
}

# --- Arch -------------------------------------------------------------------

# Print the path of the package a PKGBUILD in the current directory produces.
built_package() {
  makepkg --packagelist | grep -v -- '-debug-' | head -n 1
}

arch_build_tools() {
  local missing=() pkg
  for pkg in base-devel git; do
    pacman -Qq "$pkg" >/dev/null 2>&1 || missing+=("$pkg")
  done
  if [ "${#missing[@]}" -gt 0 ]; then
    say "Installing build tools: ${missing[*]}"
    sudo pacman -S --needed "${missing[@]}"
  fi
}

# arch_install <stock package> <patched package> <pinned version> <build dir>
arch_install() {
  local stock="$1" patched="$2" version="$3" dir="$4"
  local installed compositor_pkg="" app_pkg

  installed="$(pacman -Q "$stock" 2>/dev/null | awk '{print $2}' || true)"
  [ -n "$installed" ] || fail "$stock is not installed."
  case "$installed" in
    "$version"-*) ;;
    *) fail "This release patches $stock $version, but you have $installed.
       Installing it would break your desktop. Check the repository for a newer release." ;;
  esac

  arch_build_tools

  if pacman -Qq "$patched" >/dev/null 2>&1 && [ -z "${UNDERSCALE_REBUILD:-}" ]; then
    say "$patched is already installed; skipping its build"
  else
    say "Building $patched (this takes a while)"
    cd "$dir"
    makepkg -sf
    compositor_pkg="$(built_package)"
    [ -f "$compositor_pkg" ] || fail "The $patched package was not produced."
  fi

  say "Building the Underscale app"
  cd "$ROOT"
  makepkg -sf
  app_pkg="$(built_package)"
  [ -f "$app_pkg" ] || fail "The Underscale package was not produced."

  say "Installing"
  if [ -n "$compositor_pkg" ]; then
    echo "pacman will ask to remove '$stock', because the patched package replaces it. Answer 'y'."
    sudo pacman -U "$compositor_pkg" "$app_pkg"
  else
    sudo pacman -U "$app_pkg"
  fi

  [ "$DESKTOP" = kde ] || enable_daemon
  if [ -n "$compositor_pkg" ]; then finish relogin; else finish; fi
}

arch_uninstall() {
  local stock="$1" patched="$2"
  systemctl --user disable --now underscale-daemon.service 2>/dev/null || true
  if pacman -Qq underscale >/dev/null 2>&1; then
    say "Removing the Underscale app"
    sudo pacman -R underscale
  fi
  if pacman -Qq "$patched" >/dev/null 2>&1; then
    say "Restoring stock $stock (answer 'y' when pacman asks to remove $patched)"
    sudo pacman -S "$stock"
    say "Done. Log out and back in to finish."
  else
    say "Done. Stock $stock was already installed."
  fi
}

# --- Fedora (KDE Plasma) ----------------------------------------------------

fedora_install() {
  local out="$ROOT/build/fedora-kwin" rpm name install=()
  say "Building Fedora's KWin with overscan support (this takes a while)"
  "$ROOT/packaging/fedora/build-kwin.sh" "$out"

  # Replace only the KWin packages that are already installed.
  while IFS= read -r rpm; do
    name="$(rpm -qp --qf '%{NAME}' "$rpm" 2>/dev/null)"
    if rpm -q "$name" >/dev/null 2>&1; then install+=("$rpm"); fi
  done < <(find "$out/rpmbuild/RPMS" -name '*.rpm' | sort)
  [ "${#install[@]}" -gt 0 ] || fail "None of the built packages match an installed KWin package."

  say "Installing the patched KWin"
  sudo dnf install -y "${install[@]}"

  say "Installing the Underscale app"
  sudo dnf install -y python3-gobject gtk4 libadwaita
  "$ROOT/packaging/install-app.sh"
  finish relogin
}

fedora_uninstall() {
  "$ROOT/packaging/install-app.sh" --uninstall
  local pkgs
  pkgs="$(rpm -qa --qf '%{NAME} %{RELEASE}\n' | awk '$2 ~ /underscale/ {print $1}' | sort -u)"
  if [ -n "$pkgs" ]; then
    say "Restoring Fedora's stock KWin"
    # shellcheck disable=SC2086
    sudo dnf distro-sync -y $pkgs
    say "Done. Log out and back in to finish."
  else
    say "Done. Stock KWin was already installed."
  fi
}

# --- Debian (KDE Plasma) ----------------------------------------------------

debian_install() {
  local out="$ROOT/build/debian-kwin" deb name install=()
  say "Building Debian's KWin with overscan support (this takes a while)"
  "$ROOT/packaging/debian/build-kwin.sh" "$out"

  # Replace only the KWin packages that are already installed.
  while IFS= read -r deb; do
    name="$(dpkg-deb -f "$deb" Package)"
    if dpkg-query -W -f='${Status}' "$name" 2>/dev/null | grep -q 'install ok installed'; then
      install+=("$deb")
    fi
  done < <(find "$out/src" -maxdepth 1 -name '*.deb' | sort)
  [ "${#install[@]}" -gt 0 ] || fail "None of the built packages match an installed KWin package."

  say "Installing the patched KWin"
  sudo apt-get install -y "${install[@]}"

  say "Installing the Underscale app"
  sudo apt-get install -y python3-gi gir1.2-gtk-4.0 gir1.2-adw-1
  "$ROOT/packaging/install-app.sh"
  finish relogin
}

debian_uninstall() {
  "$ROOT/packaging/install-app.sh" --uninstall
  local pkg stock args=()
  while IFS= read -r pkg; do
    # The newest version of this package that is not ours.
    stock="$(apt-cache madison "$pkg" | awk '{print $3}' | grep -v underscale | head -n 1)"
    [ -n "$stock" ] && args+=("$pkg=$stock")
  done < <(dpkg-query -W -f='${Package} ${Version}\n' | awk '$2 ~ /underscale/ {print $1}')
  if [ "${#args[@]}" -gt 0 ]; then
    say "Restoring Debian's stock KWin"
    sudo apt-get install -y --allow-downgrades "${args[@]}"
    say "Done. Log out and back in to finish."
  else
    say "Done. Stock KWin was already installed."
  fi
}

# --- go ---------------------------------------------------------------------

case "$DISTRO:$DESKTOP:$ACTION" in
  arch:gnome:install)    arch_install mutter mutter-underscale "$MUTTER_VERSION" "$ROOT/mutter-underscale" ;;
  arch:gnome:uninstall)  arch_uninstall mutter mutter-underscale ;;
  arch:kde:install)      untested_notice
                         arch_install kwin kwin-underscale "$KWIN_VERSION" "$ROOT/kwin-underscale" ;;
  arch:kde:uninstall)    arch_uninstall kwin kwin-underscale ;;
  fedora:kde:install)    untested_notice; fedora_install ;;
  fedora:kde:uninstall)  fedora_uninstall ;;
  debian:kde:install)    untested_notice; debian_install ;;
  debian:kde:uninstall)  debian_uninstall ;;
esac
