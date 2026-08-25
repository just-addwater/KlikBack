# GENERATED — do not edit by hand. This file is produced by KlikBack's
# sync tooling; changes belong in the source it is generated from.
#
# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""Convert a game's stored images into the form a project holds them in."""

from __future__ import annotations
import struct

IMAGE_MODE_TO_COLOR_DEPTH = {3: 1, 4: 4, 6: 2, 7: 2}

def literal_break_run(bytes_per_pixel: int) -> int:
    """Where a run of identical pixels has to be broken for the encoding."""
    return (1 + bytes_per_pixel) // bytes_per_pixel + 1

def rle_encode_pixels(pixels: list[bytes]) -> bytes:
    """Pack pixels into the run-length form a project stores."""
    encoded = bytearray()
    break_run = literal_break_run(len(pixels[0])) if pixels else 2
    pos = 0
    while pos < len(pixels):
        run = 1
        while (
            pos + run < len(pixels)
            and run < 0x7F
            and pixels[pos + run] == pixels[pos]
        ):
            run += 1
        if run >= 2:
            encoded.append(run)
            encoded.extend(pixels[pos])
            pos += run
            continue

        literal_start = pos
        pos += 1
        while pos - literal_start < 0x7F and pos < len(pixels):
            following_run = 1
            while (
                pos + following_run < len(pixels)
                and following_run < break_run
                and pixels[pos + following_run] == pixels[pos]
            ):
                following_run += 1
            if following_run >= break_run:
                break
            pos += 1
        literal_count = pos - literal_start
        encoded.append(0x80 | literal_count)
        encoded.extend(b"".join(pixels[literal_start:pos]))
    encoded.append(0)
    return bytes(encoded)

IMAGE_MODE_BYTES_PER_PIXEL = {3: 1, 4: 3, 6: 2, 7: 2}

def runtime_image_to_editor(decoded: bytes) -> bytes:
    """Turn one image from the game's form into the project's."""
    if len(decoded) < 24:
        raise ValueError("runtime image record is truncated")
    flags = decoded[15]
    if flags & 0x0F:
        return decoded

    width, height = struct.unpack_from("<HH", decoded, 10)
    mode = decoded[14]
    bytes_per_pixel = IMAGE_MODE_BYTES_PER_PIXEL.get(mode)
    if bytes_per_pixel is None:
        raise ValueError(f"unsupported MMF image mode {mode}")
    data_size = struct.unpack_from("<I", decoded, 6)[0]
    raw = decoded[24 : 24 + data_size]
    if len(raw) != data_size:
        raise ValueError("runtime image pixel data is truncated")
    if height == 0 or len(raw) % height:
        raise ValueError(
            f"runtime pixel data cannot be divided into {height} rows"
        )
    stride = len(raw) // height
    row_bytes = width * bytes_per_pixel
    if stride < row_bytes:
        raise ValueError(
            f"runtime row has {stride} bytes, needs at least {row_bytes}"
        )

    pixels = [
        raw[pos : pos + bytes_per_pixel]
        for pos in range(0, len(raw), bytes_per_pixel)
    ]

    compressed = rle_encode_pixels(pixels)
    header = bytearray(decoded[:24])
    struct.pack_into("<I", header, 6, len(compressed))
    editor_flag = IMAGE_MODE_TO_COLOR_DEPTH[mode]
    header[15] = (header[15] & 0xF0) | editor_flag
    return bytes(header) + compressed
