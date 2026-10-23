"""Write a small RGB PNG without Pillow.

The far-LOD facade images are original (a window grid drawn from the grammar, not a
downloaded photo) and they have to be real PNGs so Git LFS and Blender both accept them.
"""
import struct
import zlib


def write_rgb(path, width, height, rgb):
    """rgb is width*height*3 bytes, row-major, top row first."""
    if len(rgb) != width * height * 3:
        raise ValueError("rgb buffer is %d bytes, expected %d" % (len(rgb), width * height * 3))
    raw = bytearray()
    stride = width * 3
    for y in range(height):
        raw.append(0)
        raw.extend(rgb[y * stride:(y + 1) * stride])

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xffffffff)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(png)
