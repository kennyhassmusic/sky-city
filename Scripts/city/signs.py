"""Original storefront signs. Generic words, no brand names.

The bitmaps are drawn with a tiny built-in alphabet so the script does not need a
system font. Blender puts one image on each sign board.

Run: python3 -I Scripts/city/signs.py
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pngutil  # noqa: E402

# A pedestrian block of words. None of these is a real business.
WORDS = ("CAFE", "BOOKS", "MARKET", "HOTEL", "TAILOR", "DINER")

# 5 wide, 7 tall, top row first. 1 is ink.
FONT = {
    "A": ("01110", "10001", "10001", "11111", "10001", "10001", "10001"),
    "B": ("11110", "10001", "10001", "11110", "10001", "10001", "11110"),
    "C": ("01111", "10000", "10000", "10000", "10000", "10000", "01111"),
    "D": ("11110", "10001", "10001", "10001", "10001", "10001", "11110"),
    "E": ("11111", "10000", "10000", "11110", "10000", "10000", "11111"),
    "F": ("11111", "10000", "10000", "11110", "10000", "10000", "10000"),
    "H": ("10001", "10001", "10001", "11111", "10001", "10001", "10001"),
    "I": ("11111", "00100", "00100", "00100", "00100", "00100", "11111"),
    "K": ("10001", "10010", "10100", "11000", "10100", "10010", "10001"),
    "L": ("10000", "10000", "10000", "10000", "10000", "10000", "11111"),
    "M": ("10001", "11011", "10101", "10101", "10001", "10001", "10001"),
    "N": ("10001", "11001", "10101", "10011", "10001", "10001", "10001"),
    "O": ("01110", "10001", "10001", "10001", "10001", "10001", "01110"),
    "R": ("11110", "10001", "10001", "11110", "10100", "10010", "10001"),
    "S": ("01111", "10000", "10000", "01110", "00001", "00001", "11110"),
    "T": ("11111", "00100", "00100", "00100", "00100", "00100", "00100"),
}

# Panel colours. Ink stays cream so the word reads on the street.
PANELS = {
    "CAFE": (92, 42, 36),
    "BOOKS": (36, 58, 72),
    "MARKET": (48, 72, 44),
    "HOTEL": (72, 56, 32),
    "TAILOR": (48, 40, 64),
    "DINER": (86, 48, 28),
}
INK = (236, 224, 196)


def write(folder):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    paths = []
    for word in WORDS:
        path = folder / ("T_CG_Sign_%s.png" % word)
        pngutil.write_rgb(str(path), 256, 64, _panel(word))
        paths.append(path)
    return paths


def _panel(word):
    w, h = 256, 64
    bg = PANELS[word]
    buf = bytearray(bg * (w * h))
    scale = 5
    glyph_w = 5 * scale
    gap = 4
    text_w = len(word) * glyph_w + (len(word) - 1) * gap
    x0 = (w - text_w) // 2
    y0 = (h - 7 * scale) // 2
    for i, ch in enumerate(word):
        glyph = FONT[ch]
        ox = x0 + i * (glyph_w + gap)
        for row, bits in enumerate(glyph):
            for col, bit in enumerate(bits):
                if bit != "1":
                    continue
                for dy in range(scale):
                    for dx in range(scale):
                        x = ox + col * scale + dx
                        y = y0 + row * scale + dy
                        if 0 <= x < w and 0 <= y < h:
                            i3 = (y * w + x) * 3
                            buf[i3:i3 + 3] = bytes(INK)
    return bytes(buf)


def main():
    root = os.environ.get("SKYCITY_ROOT") or str(Path(__file__).resolve().parents[2])
    folder = Path(root) / "SourceArt" / "CityGen" / "signs"
    paths = write(folder)
    print("signs", len(paths), "->", folder)


if __name__ == "__main__":
    main()
