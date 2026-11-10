"""underscalectl: command-line control of display underscan and scale."""

from __future__ import annotations

import argparse
import sys

from .backends import BackendError, get_backend
from .store import Store


def parse_amount(text: str) -> float:
    """Accept "5%", "5" (percent) or "0.05" (fraction); "off" is 0."""
    text = text.strip().lower()
    if text == "off":
        return 0.0
    try:
        if text.endswith("%"):
            return float(text[:-1]) / 100.0
        value = float(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not an amount: '{text}'") from None
    if value < 0:
        raise argparse.ArgumentTypeError("amount cannot be negative")
    return value / 100.0 if value >= 1.0 else value


def cmd_list(backend, _store, _args) -> int:
    for display in backend.list_displays():
        kind = "built-in" if display.builtin else "external"
        print(f"{display.connector}  {display.name}  ({kind})")
        if not display.active:
            print("    not in use")
            continue
        looks_w, looks_h = display.looks_like()
        print(f"    resolution  {display.width}x{display.height}")
        print(f"    scale       {display.scale:g}  (looks like {looks_w}x{looks_h})")
        if display.supports_underscan:
            print(f"    underscan   {display.underscan * 100:.1f}%")
        elif not display.builtin:
            print("    underscan   unavailable (needs mutter-underscale)")
    return 0


def cmd_get(backend, _store, args) -> int:
    display = backend.find_display(args.display)
    if not display.supports_underscan:
        raise BackendError(f"{display.name} cannot be underscanned")
    print(f"{display.underscan * 100:.1f}%")
    return 0


def cmd_set(backend, store, args) -> int:
    display = backend.find_display(args.display)
    amount = min(args.amount, backend.max_underscan)
    backend.set_underscan(display, amount)
    if not args.no_save:
        store.set_underscan(display, amount)
    print(f"{display.name}: underscan {amount * 100:.1f}%")
    return 0


def cmd_scale(backend, _store, args) -> int:
    display = backend.find_display(args.display)
    if args.value is None:
        for scale in display.supported_scales:
            looks_w, looks_h = display.looks_like(scale)
            mark = "*" if abs(scale - display.scale) < 0.01 else " "
            print(f"{mark} {scale:<6g} looks like {looks_w}x{looks_h}")
        return 0
    closest = min(display.supported_scales, key=lambda s: abs(s - args.value))
    if abs(closest - args.value) > 0.01:
        choices = ", ".join(f"{s:g}" for s in display.supported_scales)
        raise BackendError(f"Scale {args.value:g} is not available. Choices: {choices}")
    backend.set_scale(display, closest)
    looks_w, looks_h = display.looks_like(closest)
    print(f"{display.name}: scale {closest:g} (looks like {looks_w}x{looks_h})")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="underscalectl",
        description="Adjust the picture size (underscan) and UI scale of displays.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="show displays and their settings").set_defaults(func=cmd_list)

    get = sub.add_parser("get", help="print a display's underscan")
    get.add_argument("display", help='connector or name, e.g. "HDMI-1" or "sony"')
    get.set_defaults(func=cmd_get)

    set_ = sub.add_parser("set", help="set a display's underscan")
    set_.add_argument("display")
    set_.add_argument("amount", type=parse_amount, help='e.g. "5%%", "0.05" or "off"')
    set_.add_argument("--no-save", action="store_true", help="apply now but do not remember")
    set_.set_defaults(func=cmd_set)

    scale = sub.add_parser("scale", help="show or set a display's UI scale")
    scale.add_argument("display")
    scale.add_argument("value", type=float, nargs="?", help="omit to list the choices")
    scale.set_defaults(func=cmd_scale)

    args = parser.parse_args(argv)
    try:
        return args.func(get_backend(), Store(), args)
    except BackendError as error:
        print(f"underscalectl: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
