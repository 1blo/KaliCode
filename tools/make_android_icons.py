"""Generate the Android launcher icons from the Kali Code SVG mark.

Produces:
    android/app/src/main/res/mipmap-mdpi/ic_launcher.png      48x48
    android/app/src/main/res/mipmap-hdpi/ic_launcher.png      72x72
    android/app/src/main/res/mipmap-xhdpi/ic_launcher.png     96x96
    android/app/src/main/res/mipmap-xxhdpi/ic_launcher.png   144x144
    android/app/src/main/res/mipmap-xxxhdpi/ic_launcher.png  192x192
    ... plus the round variants.

The mark is drawn with Pillow (no SVG rasterizer needed).

Run:  python tools/make_android_icons.py
"""
from __future__ import annotations

import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw
except ImportError:
    print("Pillow is required:  python -m pip install pillow")
    raise SystemExit(1)

ROOT = Path(__file__).resolve().parent.parent
RES = ROOT / "android" / "app" / "src" / "main" / "res"

DENSITIES = {
    "mdpi": 48,
    "hdpi": 72,
    "xhdpi": 96,
    "xxhdpi": 144,
    "xxxhdpi": 192,
}

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


def draw_mark(size: int, round_icon: bool) -> Image.Image:
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
    for density, size in DENSITIES.items():
        out_dir = RES / f"mipmap-{density}"
        out_dir.mkdir(parents=True, exist_ok=True)
        draw_mark(size, round_icon=False).save(out_dir / "ic_launcher.png")
        draw_mark(size, round_icon=True).save(out_dir / "ic_launcher_round.png")
        print(f"  wrote {out_dir.name} ({size}x{size})")

    # A small preview for the repo.
    preview = ROOT / "android" / "icon-preview.png"
    draw_mark(256, round_icon=False).save(preview)
    print(f"  wrote {preview}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
