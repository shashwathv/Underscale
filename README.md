# Underscale

**An adjustable underscan slider for external displays on GNOME, like the one in macOS.**

If you plug a laptop into a TV and the edges of the desktop are cut off (the top
bar is half missing, window corners fall off the screen), the TV is
*overscanning*: it enlarges the picture and crops the border. macOS has an
"Underscan" slider that fixes this by shrinking the picture until it fits.
GNOME on Wayland has no such control on most hardware. Underscale adds it.

- **Underscan slider.** Shrinks the whole picture inside the video signal, live,
  as you drag. The resolution does not change and the display hardware does the
  scaling, so it costs nothing at runtime.
- **Scaled sizes.** "Looks like 1536 × 864"-style choices, from Larger Text to
  More Space, for each external display.
- **Remembers each display.** Settings are stored per physical TV or monitor and
  restored at login and when you plug it back in.

> **Status:** early, and tested on one machine so far: a Dell laptop with Intel
> Iris Xe graphics (`i915`), a Sony TV over HDMI, GNOME 51.1 on Wayland, Arch
> Linux. It should work on other GPUs whose display planes can scale, but that
> is unverified. Reports are welcome.

## Why this needs a patched Mutter

GNOME's built-in "Adjust for TV" switch depends on an `underscan` property that
only some graphics drivers provide. Intel's driver does not provide it on HDMI,
so on Intel laptops the switch never appears. Where it does appear it is on/off
with a fixed 5% border.

Underscale takes a different route that does not depend on that property. It
asks the display hardware to scale the desktop's primary plane into a smaller,
centred rectangle of the screen:

```
 1920 x 1080 video signal                 what the TV shows
┌──────────────────────────┐             ┌──────────────────────────┐
│  black border            │             │┌────────────────────────┐│
│  ┌────────────────────┐  │   TV crops  ││                        ││
│  │                    │  │   the edge  ││   the whole desktop,   ││
│  │  desktop, still    │  │  ────────►  ││   nothing cut off      ││
│  │  1920 x 1080,      │  │             ││                        ││
│  │  scaled to fit     │  │             │└────────────────────────┘│
│  └────────────────────┘  │             └──────────────────────────┘
└──────────────────────────┘
```

Only the compositor can do that, so the feature is a small patch to Mutter
(GNOME's compositor) plus an app that controls it.

## What's in this repository

| Path | What it is |
| --- | --- |
| `mutter-underscale/` | Arch package: Mutter 51.1 plus one patch. Replaces the stock `mutter` package. |
| `underscale/` | Python package: the settings window, `underscalectl`, and the daemon. |
| `bin/`, `data/` | Launchers, the systemd user service, the desktop entry. |
| `install.sh` | One-step installer and uninstaller. |
| `PKGBUILD` | Arch package for the app, CLI and daemon. |
| `scripts/phase0-scaler-test.sh` | Console test: does your GPU accept a scaled primary plane? |

## Requirements

- Arch Linux
- GNOME 51 on Wayland, with **Mutter 51.1** (the patch is written against that version)
- An external display on a GPU that uses the kernel's atomic modesetting and
  has scaling-capable planes. Verified on Intel `i915` (Tiger Lake).

## Install

```sh
git clone https://github.com/shashwathv/Underscale.git && cd Underscale && ./install.sh
```

Then **log out and back in**, and open **Underscale** from the app grid.

The installer builds the patched Mutter (about five minutes) and the app,
installs both, and turns on the daemon. Along the way:

- It asks for your password when it installs packages.
- pacman asks to remove `mutter`, because the patched package replaces it.
  Answer **y**.
- It stops without changing anything if your Mutter is not version 51.1.

To undo everything: `./install.sh --uninstall`

### Optional: check your hardware first

This takes two minutes and tells you whether the approach works on your GPU
before you replace any system package. Switch to a text console with
**Ctrl+Alt+F3**, log in, and run:

```sh
./scripts/phase0-scaler-test.sh
```

A colour test pattern should appear on the external display, and the script
prints `RESULT: the kernel ACCEPTED the scaled plane`. Press Enter to end it and
**Ctrl+Alt+F2** to return to GNOME. The script assumes an Intel GPU with the
external display on HDMI.

### Manual install

If you would rather run the steps yourself:

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

### The window

Open **Underscale** from the app grid. Pick the display, then drag the
**Underscan** slider from *Off* towards *More* until all four edges of the
desktop are visible on the TV. The picture changes while you drag.

The **Size** list below it changes how large text and windows appear.

### The command line

```sh
underscalectl list                 # displays and their current settings
underscalectl set HDMI-1 5%        # shrink the picture by 5%
underscalectl set sony 0.05        # same, matching the display by name
underscalectl set HDMI-1 off       # back to full size
underscalectl get HDMI-1           # print the current underscan
underscalectl set HDMI-1 8% --no-save   # try a value without remembering it

underscalectl scale HDMI-1         # list the size choices
underscalectl scale HDMI-1 1.25    # looks like 1536x864 on a 1080p display
```

The slider in the window goes up to 15%. `underscalectl` accepts up to 25%.

### Where settings live

`~/.config/underscale/displays.json`, keyed by the display's own identity
(vendor, product, serial), not by the port it is plugged into:

```json
{
  "SNY:SONY TV:0x01010101": {
    "name": "Sony SONY TV",
    "underscan": 0.05
  }
}
```

The daemon reads this file at login and whenever displays change, and applies
the saved amount.

## How it works

**The Mutter patch** (`mutter-underscale/0001-underscan-amount-via-plane-scaling.patch`):

- When Mutter hands a finished frame to the kernel, it normally places the
  primary plane over the whole screen. With an underscan amount set, it places
  the plane on a smaller centred rectangle and leaves the source size alone, so
  the display hardware scales it. Fullscreen video that bypasses compositing
  takes the same path.
- The hardware pointer is a separate plane, so its position is mapped into the
  same rectangle and it lands where it should.
- Before accepting a new amount, Mutter asks the kernel to test the
  configuration. If the hardware cannot scale to that size, the request fails
  with an error and nothing changes on screen.
- The format of `monitors.xml` is untouched, so switching back to stock Mutter
  cannot disturb your saved monitor layout.

**The D-Bus interface** it adds to `org.gnome.Mutter.DisplayConfig`:

| Member | Meaning |
| --- | --- |
| Method `SetUnderscanAmount(s connector, d amount)` | Shrink the picture of `connector` by `amount`, from `0.0` (off) to `0.25`. Applies immediately, without a mode switch. Not stored by Mutter. |
| Monitor property `underscan-amount` (`d`) in `GetCurrentState` | The current amount. Present on external monitors when the feature is available. |

You can drive it without the app:

```sh
gdbus call --session --dest org.gnome.Mutter.DisplayConfig \
  --object-path /org/gnome/Mutter/DisplayConfig \
  --method org.gnome.Mutter.DisplayConfig.SetUnderscanAmount HDMI-1 0.05
```

**The app** never talks to Mutter directly outside `underscale/backends/mutter.py`.
Everything else uses the small `Backend` interface in
`underscale/backends/base.py`, which is where support for other compositors
will plug in.

## Troubleshooting

**The slider says "Not available".** The running Mutter is not the patched one.
Check with `pacman -Q mutter-underscale`, and make sure you logged out and back
in after installing it.

**The setting is gone after login or after replugging the TV.** The daemon is
not running. Check `systemctl --user status underscale-daemon.service`.

**"The display hardware rejected scaling the picture".** Your GPU or driver
cannot scale the primary plane to that size. Try a smaller amount. If no amount
works, the hardware path this project uses is not available on your machine.

**The login screen is still cut off.** Expected for now; see Limitations.

**Check the TV too.** Many TVs can turn overscan off themselves, under a picture
setting named something like *Full Pixel*, *Just Scan*, *Screen Fit* or *PC
mode*. If yours has it, that is the better fix, because the picture is then not
scaled twice.

## Going back to stock Mutter

`./install.sh --uninstall` does this for you. By hand, or if the desktop will
not start, from a text console (**Ctrl+Alt+F3**):

```sh
sudo pacman -S mutter
```

pacman offers to remove `mutter-underscale` in its place. Then log in again.
If you are offline, the previous package is usually still in the cache:

```sh
sudo pacman -U /var/cache/pacman/pkg/mutter-51.1-1-x86_64.pkg.tar.zst
```

## Updates

`mutter-underscale` is tied to Mutter 51.1 and pacman will not update it on its
own.

- **Point releases** of stock `mutter` are skipped silently. Rebuild this
  package to pick up their fixes once the patch has been checked against them.
- **A GNOME major update** stops with a dependency conflict on `gnome-shell`.
  Either wait for the patch to be ported to the new Mutter, or let pacman
  replace this package with stock `mutter` and lose underscan until then.

## Limitations

- **The GDM login screen is not underscanned.** The amount is applied by a user
  service after login.
- **The pointer image is not shrunk** with the picture, only positioned
  correctly. At typical amounts the size difference is not visible.
- **Scaling softens the picture slightly**, as it does on macOS, because 1920
  pixels are being drawn into fewer.
- **"More Space" beyond the display's native resolution** is not available.
  Mutter does not allow a scale below 1, and the patch for that is not written.
- **GNOME only**, and only the Wayland session.
- **Displays that span several connectors** (tiled monitors) are not handled.

## Roadmap

- Sizes beyond native resolution ("More Space"), with a second Mutter patch
- Underscan on the login screen
- An AUR package
- Backends for other compositors: KDE Plasma, then wlroots compositors and Hyprland

## Related work

- GNOME's **Adjust for TV** switch: fixed 5%, and only on drivers with an
  `underscan` property.
- KDE Plasma's **overscan** setting: adjustable, but also driver-dependent.
  [KDE bug 486621](https://bugs.kde.org/show_bug.cgi?id=486621) tracks doing it
  in the compositor for drivers without the property.
- [Mutter issue 1046](https://gitlab.gnome.org/GNOME/mutter/-/issues/1046) asks
  for a manually adjustable border in GNOME.

## Contributing

Bug reports are most useful with the output of `underscalectl list`, your GPU
and driver (`lspci -k | grep -A3 VGA`), your Mutter version, and what the TV
showed. If you tried the hardware test script, include its result line.

## Licence

GPL-2.0-or-later, the same licence as Mutter, which the patch modifies. See
[LICENSE](LICENSE).

Underscale is an independent project and is not affiliated with GNOME or Apple.
