# Underscale

Apple's external-display sizing controls, for GNOME on Arch Linux.

- **Underscan slider.** Shrinks the whole picture inside the video signal so a
  TV that crops the edges (overscan) shows the entire desktop. The resolution
  does not change; the display hardware does the scaling.
- **Scaled sizes.** "Looks like 1536 × 864"-style choices from Larger Text to
  More Space.

## Parts

| Part | What it is |
| --- | --- |
| `mutter-underscale/` | Arch package: Mutter 51.1 plus one patch that adds adjustable underscan. Replaces the stock `mutter` package. |
| `underscale/` | Python package: settings window, `underscalectl`, and a daemon that re-applies saved values. |
| `scripts/phase0-scaler-test.sh` | Console test that the GPU accepts a scaled primary plane. |

Underscan needs the patched Mutter because the Intel driver has no underscan
property on HDMI. Scaled sizes work on stock Mutter.

## Install

```sh
# 1. Patched Mutter
cd mutter-underscale
makepkg -s
sudo pacman -U mutter-underscale-51.1-1-x86_64.pkg.tar.zst
# log out and back in

# 2. App, CLI and daemon
cd ..
makepkg -si
systemctl --user enable --now underscale-daemon.service
```

## Use

Open **Underscale** from the app grid, or:

```sh
underscalectl list
underscalectl set HDMI-1 5%      # shrink the picture by 5%
underscalectl set HDMI-1 off
underscalectl scale HDMI-1       # list the size choices
underscalectl scale HDMI-1 1.25
```

Settings are stored per physical display in `~/.config/underscale/displays.json`.

## Revert to stock Mutter

From a text console (Ctrl+Alt+F3):

```sh
sudo pacman -U /var/cache/pacman/pkg/mutter-51.1-1-x86_64.pkg.tar.zst
```

Then log in again. Your monitor layout is unaffected: the patch does not change
`monitors.xml`.

## Updates

`mutter-underscale` is tied to Mutter 51.1 and pacman will not update it on its
own. Point releases of stock `mutter` are skipped silently, so rebuild this
package to pick up their fixes. A GNOME major update will stop with a dependency
conflict on `gnome-shell`: either rebuild this package against the new Mutter
first, or let pacman replace it with stock `mutter` and lose underscan until
the patch is ported.

## Known gaps

- The GDM login screen is not underscanned; the amount is applied after login.
- The pointer image is not shrunk with the picture, only positioned correctly.
- "More Space" sizes beyond the display's native resolution need a second
  Mutter patch that is not written yet.
- GNOME only for now. The backend interface in `underscale/backends/base.py` is
  where other compositors plug in.
