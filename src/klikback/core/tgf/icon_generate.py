# GENERATED — do not edit by hand. This file is produced by KlikBack's
# sync tooling; changes belong in the source it is generated from.
#
# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""Draw a 1996 object's editor icon from that object's own artwork.

Protecting a 1996 game emptied every object's stored editor icon, so
unprotecting one has to put something back. The honest something is the
object's own art: a backdrop or quick backdrop uses the picture it displays,
an active the first frame of its first animation direction, and a score,
lives or counter the first frame of its display art.

The rule is the editor's own: the art is scaled into a 30-pixel box —
untouched if it already fits, otherwise the longest side scaled to 30 and the
other floored — sampled, and quantised to the nearest colour available.

This is a **substitution and is reported as one**. The author's original icon
is gone from the file and nothing recovers it; what this produces is a
recognisable stand-in so the project is navigable, not a claim that the
original came back. Objects with no art at all fall back to this project's
own drawings, never to anybody else's.
"""

from __future__ import annotations
import struct
import zlib
from functools import lru_cache
from pathlib import Path
import klikback.core.tgf.image as img
from klikback.core.tgf.icon_census import source_handle

ICON_BOX = 30

ARTWORK_DIR = Path(__file__).resolve().parent.parent / "artwork"

ARTWORK_BY_TYPE = {
    0x03: "string.png",
    0x04: "qanda.png",
    0x05: "score.png",
    0x06: "lives.png",
    0x07: "counter.png",
}

EXTENSION_ARTWORK = "extension.png"

OTHER_ARTWORK = "other.png"

def icon_dimensions(width: int, height: int) -> tuple[int, int]:
    """The size the art becomes once scaled into the editor's icon box."""
    longest = max(width, height)
    if longest <= ICON_BOX:
        return width, height
    return max(width * ICON_BOX // longest, 1), max(height * ICON_BOX // longest, 1)

def sample(index: int, source_extent: int, dest_extent: int) -> int:
    """Pick the source pixel that stands for one icon pixel."""
    return ((index + 1) * source_extent - 1) // dest_extent

def read_palette(raw: bytes) -> list[tuple[int, int, int]]:
    """The colours the game's own artwork is stored against."""
    body = raw[4:4 + 1024]
    return [(body[i * 4], body[i * 4 + 1], body[i * 4 + 2])
            for i in range(256)]

def art_pixel_rgb(value: int, mode: int) -> tuple[int, int, int]:
    """The colour of one pixel of the source art."""
    if mode == 6:
        r = (value >> 10) & 0x1F
        g = (value >> 5) & 0x1F
        b = value & 0x1F
        return (r << 3 | r >> 2, g << 3 | g >> 2, b << 3 | b >> 2)
    if mode == 4:
        return ((value >> 16) & 0xFF, (value >> 8) & 0xFF, value & 0xFF)
    raise img.ImageProblem(f"no RGB reading for graphic mode {mode}")

class _Quantiser:
    """Map a colour to the nearest entry in the game's own palette."""

    def __init__(self, palette: list[tuple[int, int, int]]):
        """Take the palette every drawn icon will be matched against."""
        self.palette = palette
        self.cache: dict[tuple[int, int, int], int] = {}

    def __call__(self, rgb: tuple[int, int, int]) -> int:
        """The palette entry closest to one colour."""
        got = self.cache.get(rgb)
        if got is None:
            red, green, blue = rgb
            best = 1 << 30
            got = 1
            for i in range(1, 256):
                r, g, b = self.palette[i]
                d = (r - red) ** 2 + (g - green) ** 2 + (b - blue) ** 2
                if d < best:
                    best, got = d, i
            self.cache[rgb] = got
        return got

def rle_encode(indices: bytes) -> bytes:
    """Pack pixels into the run-length form the editor stores icons in."""
    out = bytearray()
    pos = 0
    n = len(indices)
    while pos < n:
        run = 1
        while (pos + run < n and run < 0x7F
               and indices[pos + run] == indices[pos]):
            run += 1
        if run >= 3:
            out += bytes((run, indices[pos]))
            pos += run
            continue

        start = pos
        while pos < n and pos - start < 0x7F:
            if (pos + 2 < n and indices[pos] == indices[pos + 1]
                    == indices[pos + 2]):
                break
            pos += 1
        span = pos - start
        if span == 1:
            out += bytes((1, indices[start]))
        else:
            out += bytes((0x80 | span,)) + indices[start:pos]
    out.append(0)
    return bytes(out)

def build_icon_record(width: int, height: int, indices: bytes) -> bytes:
    """Assemble the stored icon record — its header, size and encoded pixels.
    """
    runs = rle_encode(indices)
    return struct.pack(
        "<HIIHHBBHHHH",
        0,
        3,
        len(runs),
        width, height,
        3, 1,
        0, 0, 0, 0,
    ) + runs

def icon_from_art(art: img.ImageRecord,
                  quantise: _Quantiser | None) -> bytes:
    """Build an object's icon from the picture that object actually uses."""
    rows = img.decode_rows(art)
    iw, ih = icon_dimensions(art.width, art.height)
    out = bytearray()
    for y in range(ih):
        sy = sample(y, art.height, ih) if ih != art.height else y
        for x in range(iw):
            sx = sample(x, art.width, iw) if iw != art.width else x
            value = rows[sy][sx]
            if value is None:
                out.append(0)
            elif art.mode == 3:
                out.append(value & 0xFF)
            else:
                if quantise is None:
                    raise img.ImageProblem(
                        f"mode {art.mode} art needs a palette")
                out.append(quantise(art_pixel_rgb(value, art.mode)))
    return build_icon_record(iw, ih, bytes(out))

def colorref_rgb(colorref: int) -> tuple[int, int, int]:
    """Split a Windows colour value into its red, green and blue parts."""
    return (colorref & 0xFF, (colorref >> 8) & 0xFF, (colorref >> 16) & 0xFF)

QBD_TYPE_MOSAIC = 1

def quick_backdrop_icon(head: bytes, quantise: _Quantiser) -> bytes:
    """Draw the icon for an object that is a shape or fill, not a stored picture.
    """
    c1 = struct.unpack_from("<I", head, 0x18)[0]
    c2 = struct.unpack_from("<I", head, 0x1C)[0]
    qtype = head[0x20]
    r1, g1, b1 = colorref_rgb(c1)
    r2, g2, b2 = colorref_rgb(c2)
    gradient = (qtype & 0x0F) == 2
    horizontal = bool(qtype & 0x10)
    out = bytearray()
    for y in range(ICON_BOX):
        for x in range(ICON_BOX):
            if gradient:
                t = (x if horizontal else y) / (ICON_BOX - 1)
                rgb = (round(r1 + (r2 - r1) * t),
                       round(g1 + (g2 - g1) * t),
                       round(b1 + (b2 - b1) * t))
            else:
                rgb = (r1, g1, b1)
            out.append(quantise(rgb))
    return build_icon_record(ICON_BOX, ICON_BOX, bytes(out))

def read_png_rgba(path: Path) -> tuple[int, int, bytes]:
    """Read a PNG into pixels — enough of the format for the artwork folder."""
    blob = path.read_bytes()
    if blob[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"{path} is not a PNG")
    pos = 8
    width = height = 0
    colour_type = 0
    idat = bytearray()
    palette = b""
    while pos + 8 <= len(blob):
        (length,) = struct.unpack_from(">I", blob, pos)
        kind = blob[pos + 4:pos + 8]
        data = blob[pos + 8:pos + 8 + length]
        pos += 12 + length
        if kind == b"IHDR":
            width, height, depth, colour_type = struct.unpack_from(
                ">IIBB", data, 0)
            if depth != 8 or colour_type not in (2, 3, 6):
                raise ValueError(f"{path}: unsupported PNG shape")
        elif kind == b"PLTE":
            palette = data
        elif kind == b"IDAT":
            idat += data
        elif kind == b"IEND":
            break
    raw = zlib.decompress(bytes(idat))
    channels = {2: 3, 3: 1, 6: 4}[colour_type]
    stride = width * channels
    rows = []
    previous = bytearray(stride)
    at = 0
    for _ in range(height):
        filt = raw[at]
        line = bytearray(raw[at + 1:at + 1 + stride])
        at += 1 + stride
        for i in range(stride):
            a = line[i - channels] if i >= channels else 0
            b = previous[i]
            c = previous[i - channels] if i >= channels else 0
            if filt == 1:
                line[i] = (line[i] + a) & 0xFF
            elif filt == 2:
                line[i] = (line[i] + b) & 0xFF
            elif filt == 3:
                line[i] = (line[i] + (a + b) // 2) & 0xFF
            elif filt == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pr = a if pa <= pb and pa <= pc else (b if pb <= pc else c)
                line[i] = (line[i] + pr) & 0xFF
        rows.append(bytes(line))
        previous = line
    rgba = bytearray()
    for line in rows:
        for x in range(width):
            if colour_type == 6:
                r, g, b, a = line[x * 4:x * 4 + 4]
            elif colour_type == 2:
                r, g, b = line[x * 3:x * 3 + 3]
                a = 255
            else:
                idx = line[x]
                r, g, b = palette[idx * 3:idx * 3 + 3]
                a = 255
            rgba += bytes((r, g, b, a))
    return width, height, bytes(rgba)

def marker_green(red: int, green: int, blue: int) -> bool:
    """The colour the artwork uses to mean "transparent here"."""
    return green >= 0x80 and green >= red * 2 and green >= blue * 2

def artwork_for_type(object_type: int) -> Path:
    """Which of this project's own drawings stands in for an object type."""
    name = ARTWORK_BY_TYPE.get(object_type)
    if name is None and object_type >= 0x20:
        name = EXTENSION_ARTWORK
    if name is not None and (ARTWORK_DIR / name).is_file():
        return ARTWORK_DIR / name
    return ARTWORK_DIR / OTHER_ARTWORK

@lru_cache(maxsize=None)
def _artwork_rgba(path: Path) -> tuple[int, int, bytes]:
    return read_png_rgba(path)

def artwork_icon(object_type: int, quantise: _Quantiser) -> bytes | None:
    """Build an icon record from one of this project's own PNG drawings."""
    path = artwork_for_type(object_type)
    if not path.is_file():
        return None
    width, height, rgba = _artwork_rgba(path)
    iw, ih = icon_dimensions(width, height)
    out = bytearray()
    for y in range(ih):
        sy = sample(y, height, ih) if ih != height else y
        for x in range(iw):
            sx = sample(x, width, iw) if iw != width else x
            r, g, b, a = rgba[(sy * width + sx) * 4:(sy * width + sx) * 4 + 4]
            if a < 0x80 or marker_green(r, g, b):
                out.append(0)
            else:
                out.append(quantise((r, g, b)))
    return build_icon_record(iw, ih, bytes(out))
