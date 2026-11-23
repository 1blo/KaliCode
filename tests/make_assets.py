"""Prepare Kali Code image assets for Discord.

- app_icon.png  : 1024x1024 square logo (Discord app icon requirement)
- presence.png  : 1024x1024 logo used as the Rich Presence large_image

Usage:
    python tests/make_assets.py [path/to/logo.png]

Defaults to the bundled `kali/assets/app_icon.png` so the script works
without any machine-specific paths.
"""
import os
import shutil
import sys

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "kali", "assets")
DEFAULT_SRC = os.path.join(OUT_DIR, "app_icon.png")
SRC = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SRC


def main() -> int:
    os.makedirs(OUT_DIR, exist_ok=True)
    im = Image.open(SRC).convert("RGB")
    side = min(im.size)
    # Centre-crop to a square, then resize to 1024x1024.
    left = (im.width - side) // 2
    top = (im.height - side) // 2
    square = im.crop((left, top, left + side, top + side)).resize((1024, 1024), Image.LANCZOS)

    icon_path = os.path.join(OUT_DIR, "app_icon.png")
    square.save(icon_path, "PNG", optimize=True)
    print("app icon   ->", icon_path, os.path.getsize(icon_path), "bytes")

    # Presence asset: Discord renders the large image in a circle-ish frame,
    # so a slightly padded version looks better.
    padded = Image.new("RGB", (1024, 1024), (10, 22, 48))
    inset = square.resize((820, 820), Image.LANCZOS)
    padded.paste(inset, (102, 102))
    presence_path = os.path.join(OUT_DIR, "presence.png")
    padded.save(presence_path, "PNG", optimize=True)
    print("presence   ->", presence_path, os.path.getsize(presence_path), "bytes")

    # Rich Presence invite cover image: Discord wants 1024x576 (16:9).
    cover = Image.new("RGB", (1024, 576), (8, 18, 42))
    # soft radial glow behind the logo
    glow = Image.new("RGB", (1024, 576), (8, 18, 42))
    from PIL import ImageDraw

    d = ImageDraw.Draw(glow)
    d.ellipse((262, -60, 762, 440), fill=(20, 60, 130))
    cover = Image.blend(cover, glow, 0.45)
    logo = square.resize((420, 420), Image.LANCZOS)
    cover.paste(logo, (302, 78))
    cover_path = os.path.join(OUT_DIR, "cover.png")
    cover.save(cover_path, "PNG", optimize=True)
    print("cover      ->", cover_path, os.path.getsize(cover_path), "bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
