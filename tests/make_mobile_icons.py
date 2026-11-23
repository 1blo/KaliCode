"""Generate the PWA PNG icons from the SVG source (uses Pillow if available).

Run:  python tests/make_mobile_icons.py
Skips silently if Pillow is not installed; the PWA still works with the SVG icon.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MOBILE = os.path.join(ROOT, "kali", "mobile")

SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#b14aff"/>
      <stop offset="100%" stop-color="#6a2bd9"/>
    </linearGradient>
  </defs>
  <rect width="512" height="512" rx="112" fill="url(#g)"/>
  <path d="M 168 118 L 118 256 L 168 394" fill="none" stroke="#fff" stroke-width="42"
        stroke-linecap="round" stroke-linejoin="round"/>
  <path d="M 344 118 L 394 256 L 344 394" fill="none" stroke="#fff" stroke-width="42"
        stroke-linecap="round" stroke-linejoin="round"/>
  <path d="M 292 100 L 232 412" fill="none" stroke="#fff" stroke-width="34"
        stroke-linecap="round" opacity=".85"/>
</svg>
"""


def draw(size: int) -> "Image.Image":
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = size / 512.0

    # Rounded-rect gradient background.
    bg = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    bd = ImageDraw.Draw(bg)
    for i in range(int(size)):
        t = i / max(size - 1, 1)
        c = (int(0xB1 * (1 - t) + 0x6A * t),
             int(0x4A * (1 - t) + 0x2B * t),
             int(0xFF * (1 - t) + 0xD9 * t), 255)
        bd.line([(i, 0), (i, size)], fill=c)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size - 1, size - 1],
                                           radius=int(112 * s), fill=255)
    img.paste(bg, (0, 0), mask)

    # The "K" mark.
    def pt(x, y):
        return (x * s, y * s)

    d.line([pt(168, 118), pt(118, 256), pt(168, 394)], fill=(255, 255, 255, 255),
           width=int(42 * s), joint="curve")
    d.line([pt(344, 118), pt(394, 256), pt(344, 394)], fill=(255, 255, 255, 255),
           width=int(42 * s), joint="curve")
    d.line([pt(292, 100), pt(232, 412)], fill=(255, 255, 255, 220),
           width=int(34 * s))
    return img


def main() -> int:
    try:
        from PIL import Image  # noqa: F401
    except ImportError:
        print("Pillow not installed - skipping PNG icon generation.")
        print("Install with: pip install pillow")
        return 0

    for size in (192, 512):
        out = os.path.join(MOBILE, f"icon-{size}.png")
        img = draw(size)
        img.save(out, "PNG")
        print(f"wrote {os.path.relpath(out, ROOT)} ({size}x{size})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
