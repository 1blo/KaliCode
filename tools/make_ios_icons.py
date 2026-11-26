"""Generate the iOS app icon from the Kali Code SVG mark.

Produces the asset catalog Xcode expects:

    ios/Resources/Assets.xcassets/AppIcon.appiconset/
        Contents.json
        icon-1024.png          (the marketing icon)
        icon-20.png  icon-40.png  icon-60.png
        icon-76.png  icon-83.5.png

The mark is drawn with Pillow (no SVG rasterizer needed), the same way the
Android launcher icons are.

Run:  python tools/make_ios_icons.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw
except ImportError:
    print("Pillow is required:  python -m pip install pillow")
    raise SystemExit(1)

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "ios" / "Resources" / "Assets.xcassets"
APPSET = CATALOG / "AppIcon.appiconset"

PURPLE_TOP = (177, 74, 255)
PURPLE_BOTTOM = (106, 43, 217)


def _gradient(size: int) -> Image.Image:
    """The diagonal purple gradient from the SVG mark."""
    img = Image.new("RGB", (size, size), PURPLE_BOTTOM)
    px = img.load()
    for y in range(size):
        for x in range(size):
            t = (x + y) / (2 * (size - 1) or 1)
            px[x, y] = (
                int(PURPLE_TOP[0] + (PURPLE_BOTTOM[0] - PURPLE_TOP[0]) * t),
                int(PURPLE_TOP[1] + (PURPLE_BOTTOM[1] - PURPLE_TOP[1]) * t),
                int(PURPLE_TOP[2] + (PURPLE_BOTTOM[2] - PURPLE_TOP[2]) * t),
            )
    return img


def draw_mark(size: int, round_icon: bool = False) -> Image.Image:
    """Draw the Kali Code mark (the two angle brackets and the slash)."""
    ss = 4                      # supersample for smooth edges
    big = size * ss
    img = _gradient(big).convert("RGBA")

    mask = Image.new("L", (big, big), 0)
    d = ImageDraw.Draw(mask)
    radius = int(big * (0.5 if round_icon else 0.22))
    if round_icon:
        d.ellipse((0, 0, big - 1, big - 1), fill=255)
    else:
        d.rounded_rectangle((0, 0, big - 1, big - 1), radius=radius, fill=255)
    img.putalpha(mask)

    pen = ImageDraw.Draw(img)
    white = (255, 255, 255, 255)
    s = big / 512.0              # the SVG viewBox is 512 wide

    def pt(x: float, y: float) -> tuple[int, int]:
        return (int(x * s), int(y * s))

    # Left chevron:  M 168 118 L 118 256 L 168 394
    pen.line([pt(168, 118), pt(118, 256), pt(168, 394)],
             fill=white, width=int(42 * s), joint="curve")
    # Right chevron: M 344 118 L 394 256 L 344 394
    pen.line([pt(344, 118), pt(394, 256), pt(344, 394)],
             fill=white, width=int(42 * s), joint="curve")
    # Slash: M 292 100 L 232 412
    pen.line([pt(292, 100), pt(232, 412)],
             fill=white, width=int(34 * s))

    return img.resize((size, size), Image.LANCZOS)


def main() -> int:
    APPSET.mkdir(parents=True, exist_ok=True)

    # The sizes Xcode asks for in the asset catalog.
    sizes = [20, 40, 60, 76, 83.5, 1024]
    images = []
    for size in sizes:
        name = f"icon-{size:g}.png"
        # iOS icons must not have an alpha channel.
        img = draw_mark(int(size), round_icon=False).convert("RGB")
        img.save(APPSET / name)
        images.append({"filename": name, "idiom": "universal",
                       "platform": "ios", "size": f"{size:g}x{size:g}"})
        print(f"  wrote {name} ({size:g}x{size:g})")

    # The modern single-size entry is what Xcode 14+ prefers.
    contents = {
        "images": [
            {"filename": "icon-1024.png", "idiom": "universal",
             "platform": "ios", "size": "1024x1024"},
        ],
        "info": {"author": "xcode", "version": 1},
    }
    (APPSET / "Contents.json").write_text(
        json.dumps(contents, indent=2) + "\n", encoding="utf-8")
    print(f"  wrote {APPSET / 'Contents.json'}")

    # The catalog itself.
    (CATALOG / "Contents.json").write_text(
        json.dumps({"info": {"author": "xcode", "version": 1}}, indent=2)
        + "\n", encoding="utf-8")

    # A launch-screen colour asset, referenced by Info.plist.
    launch = CATALOG / "LaunchBackground.colorset"
    launch.mkdir(parents=True, exist_ok=True)
    (launch / "Contents.json").write_text(json.dumps({
        "colors": [
            {
                "color": {
                    "color-space": "srgb",
                    "components": {
                        "alpha": "1.000",
                        "blue": "0x12",
                        "green": "0x0D",
                        "red": "0x0D",
                    },
                },
                "idiom": "universal",
            }
        ],
        "info": {"author": "xcode", "version": 1},
    }, indent=2) + "\n", encoding="utf-8")
    print(f"  wrote {launch}")

    # A preview for the repository.
    preview = ROOT / "ios" / "icon-preview.png"
    draw_mark(256, round_icon=False).convert("RGB").save(preview)
    print(f"  wrote {preview}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
