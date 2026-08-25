# GENERATED — do not edit by hand. This file is produced by KlikBack's
# sync tooling; changes belong in the source it is generated from.
#
# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""Draw an object's editor icon from that object's own recovered artwork.

The little picture beside an object in the editor is stored in the project,
and a compiled game does not keep it. It can be *derived*, though, because
the editor derives it the same way: from the object's own art. An Active's
icon comes from the first frame of its first animation, a Backdrop's from its
image, a Quick Backdrop's from its fill.

The rule is the editor's own, measured rather than guessed: the art is
scaled into a 30-pixel box — untouched if it already fits, otherwise the
longest side scaled to 30 and the other floored — sampled, and quantised to
the nearest colour in the editor's palette.

The few object families with no art of their own carry drawings that belong
to this project, read from the `artwork/` folder beside the application.
Those files are part of the product: if one is missing the pipeline says so
rather than quietly
drawing nothing, and dropping a replacement PNG into that folder is a
supported way to change what the icons look like.
"""

from __future__ import annotations
import struct
import zlib
from pathlib import Path
from klikback.core.common.animation_reconstruct import IMAGE_MODE_BYTES_PER_PIXEL, rle_encode_pixels
from klikback.core.common.scaffold_synthesis import WIN32_HALFTONE_PALETTE

ICON_BOX = 30

ICON_MODE_BYTES = bytes((0x03, 0x01))

ACTIVE_ICON_CONTENT = 0x19652

BACKDROP_ICON_CONTENT = 0x21320

OTHER_ICON_CONTENT = 0x1DAB2

ARTWORK_DIR = Path(__file__).resolve().parent.parent / "artwork"

OTHER_ICON_ART = ARTWORK_DIR / "other.png"

ARTWORK_BY_TYPE = {
    3: "string.png",
    4: "qanda.png",
    5: "score.png",
    6: "lives.png",
    7: "counter.png",
    8: "ftext.png",
    9: "subapp.png",
}

EXTENSION_ARTWORK = "extension.png"

_ARTWORK_PRESENT: dict[str, bool] = {}

def imageless_icon_art(object_type: int) -> Path:
    """Which of this project's own drawings stands in for an object family."""
    name = ARTWORK_BY_TYPE.get(object_type)
    if name is None and object_type >= 32:
        name = EXTENSION_ARTWORK
    if name is not None:
        present = _ARTWORK_PRESENT.get(name)
        if present is None:
            present = (ARTWORK_DIR / name).is_file()
            _ARTWORK_PRESENT[name] = present
        if present:
            return ARTWORK_DIR / name
    return OTHER_ICON_ART

STUB_PIXEL_INDEX = 10

HALFTONE_COLORS = [
    tuple(WIN32_HALFTONE_PALETTE[pos : pos + 3]) for pos in range(0, 0x400, 4)
]

_QUANTISE_CACHE: dict[tuple[int, int, int], int] = {}

def halftone_quantise(rgb: tuple[int, int, int]) -> int:
    """Snap a colour to the nearest one the editor's palette can store."""
    got = _QUANTISE_CACHE.get(rgb)
    if got is None:
        red, green, blue = rgb
        got = min(
            range(1, 256),
            key=lambda index: (HALFTONE_COLORS[index][0] - red) ** 2
            + (HALFTONE_COLORS[index][1] - green) ** 2
            + (HALFTONE_COLORS[index][2] - blue) ** 2,
        )
        _QUANTISE_CACHE[rgb] = got
    return got

def rle_decode(data: bytes, bytes_per_pixel: int) -> bytes:
    """Unpack the run-length form the editor stores icons in."""
    out = bytearray()
    pos = 0
    while pos < len(data):
        count = data[pos]
        pos += 1
        if count == 0:
            break
        if count & 0x80:
            span = (count & 0x7F) * bytes_per_pixel
            out += data[pos : pos + span]
            pos += span
        else:
            out += data[pos : pos + bytes_per_pixel] * count
            pos += bytes_per_pixel
    return bytes(out)

def editor_image_pixels(record: bytes) -> tuple[int, int, int, list[bytes]]:
    """Decode a stored image into pixels that can be sampled."""
    width, height = struct.unpack_from("<HH", record, 10)
    mode = record[14]
    bytes_per_pixel = IMAGE_MODE_BYTES_PER_PIXEL.get(mode)
    if bytes_per_pixel is None:
        raise ValueError(f"unsupported image mode {mode}")
    raw = rle_decode(record[24:], bytes_per_pixel)
    if height == 0 or len(raw) % height:
        raise ValueError(f"cannot tile {len(raw)} pixel bytes into {height} rows")
    stride = len(raw) // height
    row_bytes = width * bytes_per_pixel
    if stride < row_bytes:
        raise ValueError(f"row stride {stride} is under {row_bytes} pixel bytes")
    return (
        width,
        height,
        mode,
        [raw[row * stride : row * stride + row_bytes] for row in range(height)],
    )

def source_rgb(
    mode: int, row: bytes, x: int, palette: bytes
) -> tuple[int, int, int] | None:
    """The colour of one pixel of the source art, or nothing where it is transparent.

    Each of the picture formats a game can store stores transparency its own way,
    and all three answers meet here — so an icon drawn from a game's art keeps
    the see-through parts see-through, whatever depth the art was saved at.
    """
    if mode == 3:
        index = row[x]
        if index == 0:
            return None
        return tuple(palette[index * 4 : index * 4 + 3])
    if mode == 4:
        blue, green, red = row[x * 3 : x * 3 + 3]
        if red == green == blue == 0:
            return None
        return (red, green, blue)
    value = struct.unpack_from("<H", row, x * 2)[0]
    if value == 0:
        return None
    return (
        (value >> 10 & 0x1F) * 255 // 31,
        (value >> 5 & 0x1F) * 255 // 31,
        (value & 0x1F) * 255 // 31,
    )

def icon_dimensions(width: int, height: int) -> tuple[int, int]:
    """The size the art becomes once scaled into the editor's icon box."""
    largest = max(width, height)
    if largest <= ICON_BOX:
        return width, height
    return (
        max(1, width * ICON_BOX // largest),
        max(1, height * ICON_BOX // largest),
    )

def sample(index: int, source_extent: int, dest_extent: int) -> int:
    """Pick the source pixel that stands for one icon pixel."""
    return min(source_extent - 1, ((index + 1) * source_extent - 1) // dest_extent)

def build_icon_record(handle: int, content: int, width: int, height: int,
                      indices: list[int]) -> bytes:
    """Assemble the stored icon record — its header, size and encoded pixels.
    """
    if len(indices) != width * height:
        raise ValueError(f"{len(indices)} pixels cannot fill {width}x{height}")
    if width % 2:
        padded: list[int] = []
        for row in range(height):
            padded.extend(indices[row * width : (row + 1) * width])
            padded.append(0)
        indices = padded
    encoded = rle_encode_pixels([bytes((index,)) for index in indices])
    return (
        struct.pack("<IIHI", handle, content, 0, len(encoded))
        + struct.pack("<HH", width, height)
        + ICON_MODE_BYTES
        + bytes(8)
        + encoded
    )

def icon_pixel_indices(record: bytes, palette: bytes, dest_width: int,
                       dest_height: int) -> list[int]:
    """The icon's pixels as palette entries, ready to encode."""
    width, height, mode, rows = editor_image_pixels(record)
    indices: list[int] = []
    for y in range(dest_height):
        row = rows[sample(y, height, dest_height)]
        for x in range(dest_width):
            rgb = source_rgb(mode, row, sample(x, width, dest_width), palette)
            indices.append(0 if rgb is None else halftone_quantise(rgb))
    return indices

def icon_from_image(record: bytes, palette: bytes, handle: int,
                    content: int) -> bytes:
    """Build an object's icon from a picture the object actually uses."""
    width, height = struct.unpack_from("<HH", record, 10)
    dest_width, dest_height = icon_dimensions(width, height)
    return build_icon_record(
        handle, content, dest_width, dest_height,
        icon_pixel_indices(record, palette, dest_width, dest_height),
    )

def backdrop_stub_icon(handle: int) -> bytes:
    """The minimal icon record a Backdrop with no image of its own carries."""
    return build_icon_record(
        handle, BACKDROP_ICON_CONTENT, 32, 1, [STUB_PIXEL_INDEX] * 32
    )

def colorref_rgb(colorref: int) -> tuple[int, int, int]:
    """Split a Windows colour value into its red, green and blue parts."""
    return (colorref & 0xFF, colorref >> 8 & 0xFF, colorref >> 16 & 0xFF)

def quick_backdrop_icon(
    payload: dict, palette: bytes, handle: int,
    images_by_id: dict[int, bytes] | None = None,
) -> bytes:
    """Draw the icon for an object that is a shape or fill, not a stored picture.
    """
    fill = payload["fill"]
    if fill == "solid":
        index = halftone_quantise(colorref_rgb(payload["colors"][0]))
        return build_icon_record(handle, BACKDROP_ICON_CONTENT, 32, 32,
                                 [index] * 1024)
    if fill == "gradient":
        first = colorref_rgb(payload["colors"][0])
        second = colorref_rgb(payload["colors"][1])
        vertical = payload.get("direction", 1) == 1
        bands = [
            halftone_quantise(
                tuple(
                    first[channel]
                    + (second[channel] - first[channel]) * step // 32
                    for channel in range(3)
                )
            )
            for step in range(32)
        ]
        if vertical:
            indices = [bands[y] for y in range(32) for _x in range(32)]
        else:
            indices = [bands[x] for _y in range(32) for x in range(32)]
        return build_icon_record(handle, BACKDROP_ICON_CONTENT, 32, 32, indices)
    if fill == "motif" and images_by_id is not None:
        record = images_by_id.get(payload.get("motif_image"))
        if record is not None:
            width, height, mode, rows = editor_image_pixels(record)
            indices = []
            for y in range(32):
                row = rows[y % height]
                for x in range(32):
                    rgb = source_rgb(mode, row, x % width, palette)
                    indices.append(0 if rgb is None else halftone_quantise(rgb))
            return build_icon_record(handle, BACKDROP_ICON_CONTENT, 32, 32,
                                     indices)

    return build_icon_record(handle, BACKDROP_ICON_CONTENT, 32, 32, [0] * 1024)

def read_png_rgba(path: Path) -> tuple[int, int, bytes]:
    """Read a PNG into pixels — enough of the format for the artwork folder."""
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"{path} is not a PNG file")
    width = height = None
    color_type = None
    palette = b""
    idat = bytearray()
    pos = 8
    while pos + 8 <= len(data):
        length, chunk_type = struct.unpack_from(">I4s", data, pos)
        body = data[pos + 8 : pos + 8 + length]
        if chunk_type == b"IHDR":
            width, height, depth, color_type, _comp, _filt, interlace = (
                struct.unpack_from(">IIBBBBB", body, 0)
            )
            if depth != 8 or interlace or color_type not in (0, 2, 3, 6):
                raise ValueError(
                    f"{path}: only non-interlaced 8-bit grey/RGB/palette/RGBA "
                    f"PNGs are supported (depth {depth}, colour {color_type})"
                )
        elif chunk_type == b"PLTE":
            palette = body
        elif chunk_type == b"IDAT":
            idat += body
        elif chunk_type == b"IEND":
            break
        pos += 12 + length
    if width is None:
        raise ValueError(f"{path} has no IHDR chunk")
    channels = {0: 1, 2: 3, 3: 1, 6: 4}[color_type]
    stride = width * channels
    raw = zlib.decompress(bytes(idat))
    if len(raw) != (stride + 1) * height:
        raise ValueError(f"{path}: decompressed image data has the wrong size")
    rgba = bytearray()
    previous = bytearray(stride)
    cursor = 0
    for _y in range(height):
        line_filter = raw[cursor]
        cursor += 1
        line = bytearray(raw[cursor : cursor + stride])
        cursor += stride
        if line_filter == 1:
            for i in range(channels, stride):
                line[i] = (line[i] + line[i - channels]) & 0xFF
        elif line_filter == 2:
            for i in range(stride):
                line[i] = (line[i] + previous[i]) & 0xFF
        elif line_filter == 3:
            for i in range(stride):
                left = line[i - channels] if i >= channels else 0
                line[i] = (line[i] + ((left + previous[i]) >> 1)) & 0xFF
        elif line_filter == 4:
            for i in range(stride):
                left = line[i - channels] if i >= channels else 0
                above = previous[i]
                corner = previous[i - channels] if i >= channels else 0
                estimate = left + above - corner
                distances = (
                    abs(estimate - left), abs(estimate - above),
                    abs(estimate - corner),
                )
                if distances[0] <= distances[1] and distances[0] <= distances[2]:
                    predictor = left
                elif distances[1] <= distances[2]:
                    predictor = above
                else:
                    predictor = corner
                line[i] = (line[i] + predictor) & 0xFF
        elif line_filter != 0:
            raise ValueError(f"{path}: unknown PNG filter {line_filter}")
        for x in range(width):
            if color_type == 6:
                rgba += line[x * 4 : x * 4 + 4]
            elif color_type == 2:
                rgba += line[x * 3 : x * 3 + 3] + b"\xff"
            elif color_type == 3:
                entry = line[x] * 3
                rgba += palette[entry : entry + 3] + b"\xff"
            else:
                rgba += bytes((line[x], line[x], line[x], 0xFF))
        previous = line
    return width, height, bytes(rgba)

def marker_green(red: int, green: int, blue: int) -> bool:
    """The colour the artwork uses to mean "transparent here"."""
    return green >= 128 and green > 2 * max(red, blue)

_ARTWORK_CACHE: dict[Path, list[int]] = {}

def artwork_icon_indices(path: Path) -> list[int]:
    """Read one of this project's own drawings out of its PNG.

    These are the icons for the object families that have no artwork of their own
    to be drawn from. They live in the artwork folder beside the application and
    can be replaced there — a PNG in that folder is enough.
    """
    indices = _ARTWORK_CACHE.get(path)
    if indices is None:
        width, height, rgba = read_png_rgba(path)
        if (width, height) != (32, 32):
            raise ValueError(f"{path} must be 32x32, not {width}x{height}")
        indices = []
        for position in range(0, len(rgba), 4):
            red, green, blue, alpha = rgba[position : position + 4]
            if alpha < 128 or marker_green(red, green, blue):
                indices.append(0)
            else:
                indices.append(halftone_quantise((red, green, blue)))
        _ARTWORK_CACHE[path] = indices
    return indices

def artwork_icon_record(path: Path, handle: int) -> bytes:
    """Build an icon record from one of this project's own PNG drawings."""
    return build_icon_record(
        handle, OTHER_ICON_CONTENT, 32, 32, artwork_icon_indices(path)
    )
