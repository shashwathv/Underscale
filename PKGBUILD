# Underscale: settings window, underscalectl and daemon.
# Underscan needs the mutter-underscale package (see mutter-underscale/).
#
# Build and install:  makepkg -si
# Then:               systemctl --user enable --now underscale-daemon.service

pkgname=underscale
pkgver=0.1.0
pkgrel=1
pkgdesc="Apple-style underscan and scaled resolutions for external displays"
arch=(any)
license=(GPL-2.0-or-later)
depends=(gtk4 libadwaita python python-gobject)
optdepends=('mutter-underscale: underscan on GNOME')

package() {
  local site
  site=$(python -c 'import sysconfig; print(sysconfig.get_path("purelib"))')

  cd "$startdir"
  install -d "$pkgdir$site/underscale/backends"
  install -m644 underscale/*.py "$pkgdir$site/underscale/"
  install -m644 underscale/backends/*.py "$pkgdir$site/underscale/backends/"
  python -m compileall -q -d "$site" "$pkgdir$site/underscale"

  install -Dm755 -t "$pkgdir/usr/bin" bin/underscale bin/underscalectl bin/underscale-daemon
  install -Dm644 -t "$pkgdir/usr/lib/systemd/user" data/underscale-daemon.service
  install -Dm644 -t "$pkgdir/usr/share/applications" data/io.github.underscale.Underscale.desktop
}
