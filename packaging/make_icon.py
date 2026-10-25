"""Draw packaging/matnyab.ico: a white Persian letter on an accent rounded square.

Usage: python packaging/make_icon.py [OUT.ico]
Needs Pillow and the bundled Vazirmatn font. The generated .ico is committed;
rerun this script only when the design changes.
"""

from __future__ import annotations

import os
import sys

from PIL import Image, ImageDraw, ImageFont

ACCENT = "#2F6FED"
LETTER = "م"  # Meem, first letter of the Persian name
SIZES = [16, 24, 32, 48, 64, 128, 256]
MASTER = 1024

HERE = os.path.dirname(os.path.abspath(__file__))
FONT = os.path.join(HERE, "..", "assets", "fonts", "Vazirmatn-Bold.ttf")


def draw_master() -> Image.Image:
    img = Image.new("RGBA", (MASTER, MASTER), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((32, 32, MASTER - 33, MASTER - 33), radius=220, fill=ACCENT)
    font = ImageFont.truetype(FONT, 760)
    # Anchor "mm" centres the glyph box; nudge up a little for optical balance.
    draw.text((MASTER / 2, MASTER / 2 - 30), LETTER, font=font, fill="white", anchor="mm")
    return img


def main(out: str) -> None:
    master = draw_master()
    master.resize((256, 256), Image.LANCZOS).save(
        out, format="ICO", sizes=[(s, s) for s in SIZES]
    )


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "matnyab.ico"))
