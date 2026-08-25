# GENERATED — do not edit by hand. This file is produced by KlikBack's
# sync tooling; changes belong in the source it is generated from.
#
# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""Recover an image whose compressed stream stops decoding partway through.

Some games contain a record that cannot be fully decoded -- an old file, an
unusual encoder, damage introduced decades ago. The question is what to do
about it, and the standing answer in this project is that **an unrecoverable
field is a loss, not a reason to refuse the game**.

One image in eight hundred should cost that image: the pixels that did decode
are kept, the remainder is filled, and the shortfall is reported as a named
loss. Refusing instead would cost every frame and every object in the game for
the sake of one picture.
"""

from __future__ import annotations
import struct
from klikback.core.common.animation_reconstruct import IMAGE_MODE_BYTES_PER_PIXEL, rle_encode_pixels

class SalvageProblem(Exception):
    """Raised when not even the record's own shape can be read."""

def rle_decode_pixels(data: bytes, bytes_per_pixel: int) -> tuple[list[bytes], bool]:
    """Unpack pixels, stopping cleanly where the stream stops making sense."""
    pixels: list[bytes] = []
    pos = 0
    limit = len(data)
    while pos < limit:
        control = data[pos]
        pos += 1
        if control == 0:
            return pixels, True
        if control & 0x80:
            count = control & 0x7F
            span = count * bytes_per_pixel
            if pos + span > limit:
                return pixels, False
            for step in range(count):
                start = pos + step * bytes_per_pixel
                pixels.append(data[start : start + bytes_per_pixel])
            pos += span
        else:
            if pos + bytes_per_pixel > limit:
                return pixels, False
            pixel = data[pos : pos + bytes_per_pixel]
            pos += bytes_per_pixel
            pixels.extend([pixel] * control)
    return pixels, False

def record_geometry(prefix: bytes) -> tuple[int, int, int, int, int]:
    """The size and shape the record says the image is."""
    if len(prefix) < 24:
        raise SalvageProblem(
            f"only {len(prefix)} bytes decoded, not even the 24-byte header"
        )
    data_size = struct.unpack_from("<I", prefix, 6)[0]
    width, height = struct.unpack_from("<HH", prefix, 10)
    mode = prefix[14]
    bytes_per_pixel = IMAGE_MODE_BYTES_PER_PIXEL.get(mode)
    if bytes_per_pixel is None:
        raise SalvageProblem(f"no pixel width for image mode {mode}")
    if not width or not height:
        raise SalvageProblem(f"degenerate geometry {width}x{height}")
    return width, height, mode, bytes_per_pixel, data_size

def salvage_image_record(
    prefix: bytes, declared_size: int, fill: bytes | None = None
) -> tuple[bytes, dict[str, int]]:
    """Rebuild an image record from as much of its stream as decodes.

    When a picture's compressed stream stops partway, its header still says how
    big the picture was meant to be. Rather than dropping the image or writing one
    of the wrong size, this keeps every pixel that did decode, fills the rest with
    a chosen fill colour, and re-encodes the whole thing in the form the editor
    reads. What lands in the project is a valid image of the right dimensions with
    an honest hole in it.

    It refuses everything it cannot justify: a stream that turns out to be
    complete, since then there is nothing to salvage and something else is wrong;
    a record stored in the uncompressed form, which this does not handle; more
    pixels recovered than the stated dimensions can hold; a fill colour of the
    wrong size for the image's colour mode.

    One judgement is worth stating outright. The target is width × height, not the
    row-by-row layout the runtime used. Stored images normally keep their row
    padding, and stripping it skews every padded row — but a stream that stopped
    early cannot say what its padding was, so whatever padding this record had is
    simply part of what was lost.

    The counts come back with the record — how many pixels were recovered and how
    many were filled — so the loss can be reported in real terms instead of as
    "an image was damaged".
    """
    width, height, mode, bytes_per_pixel, data_size = record_geometry(prefix)
    if 24 + data_size != declared_size:
        raise SalvageProblem(
            f"header says 24 + {data_size} = {24 + data_size}, "
            f"bank says {declared_size}"
        )
    flags = prefix[15]
    if not flags & 0x0F:
        raise SalvageProblem(
            "record is in the raw form; salvage only handles the editor RLE "
            "form, whose encoder this shares"
        )

    body = prefix[24:]
    pixels, terminated = rle_decode_pixels(body, bytes_per_pixel)
    if terminated:
        raise SalvageProblem(
            "the RLE stream is complete, so this record does not need salvaging"
        )

    wanted = width * height
    if len(pixels) > wanted:
        raise SalvageProblem(
            f"recovered {len(pixels):,} pixels for a {width}x{height} image"
        )
    if fill is None:
        fill = bytes(bytes_per_pixel)
    if len(fill) != bytes_per_pixel:
        raise SalvageProblem(
            f"fill pixel is {len(fill)} bytes, mode {mode} needs "
            f"{bytes_per_pixel}"
        )
    missing = wanted - len(pixels)
    pixels.extend([fill] * missing)

    compressed = rle_encode_pixels(pixels)
    header = bytearray(prefix[:24])
    struct.pack_into("<I", header, 6, len(compressed))
    struct.pack_into("<HH", header, 10, width, height)
    return bytes(header) + compressed, {
        "width": width,
        "height": height,
        "mode": mode,
        "pixels": wanted,
        "recovered": wanted - missing,
        "missing": missing,
        "prefix_bytes": len(prefix),
        "declared_bytes": declared_size,
    }

def describe(stats: dict[str, int]) -> str:
    """Say in plain words how much of an image was recovered."""
    share = 100.0 * stats["recovered"] / stats["pixels"] if stats["pixels"] else 0.0
    return (
        f"{stats['width']}x{stats['height']} mode {stats['mode']}: "
        f"{stats['recovered']:,} of {stats['pixels']:,} pixels recovered "
        f"({share:.1f}%), {stats['missing']:,} filled"
    )
