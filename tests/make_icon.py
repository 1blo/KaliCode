"""Generate a multi-resolution Windows .ico from the Kali Code logo."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "kali", "assets", "app_icon.png")
OUT = os.path.join(ROOT, "kali", "assets", "app_icon.ico")

SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]


def main() -> int:
    if not os.path.exists(SRC):
        print("source logo missing:", SRC)
        return 1
    im = Image.open(SRC).convert("RGBA")
    # Square, centered on a transparent canvas (ICO handles transparency).
    w, h = im.size
    side = max(w, h)
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(im, ((side - w) // 2, (side - h) // 2), im)
    canvas.save(OUT, format="ICO", sizes=SIZES)
    print("wrote", OUT, os.path.getsize(OUT), "bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
