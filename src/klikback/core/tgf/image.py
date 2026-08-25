# GENERATED — do not edit by hand. This file is produced by KlikBack's
# sync tooling; changes belong in the source it is generated from.
#
# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""Read and write the images a 1996 game stores.

Pictures in these files are kept run-length encoded against the game's own
palette. Everything that displays or rebuilds artwork — object icons, frame
previews, the image bank itself — goes through here.

Decoding is strict about its own bounds: a run that would read past the end
of a record raises rather than returning whatever happens to follow it.
Silently accepting a malformed image is how corrupt artwork ends up looking
like a decoder bug two steps later.
"""

from __future__ import annotations
import struct
from dataclasses import dataclass

class ImageProblem(ValueError):
    """Raised when a stored image does not decode within its own bounds."""

BYTES_PER_PIXEL = {3: 1, 4: 3, 5: 1, 6: 2, 7: 2}

RECORD_HEAD = 24

FLAG_RLE = 0x0F

FLAG_TGF_COMPRESSION = 0x40

@dataclass
class ImageRecord:
    """One image, in the form the rest of the pipeline works with."""
    checksum: int
    references: int
    width: int
    height: int
    mode: int
    flags: int
    hot_spot: tuple[int, int]
    action_point: tuple[int, int]
    payload: bytes

def parse_record(data: bytes) -> ImageRecord:
    """Read one stored image: its size, its palette and its pixels."""
    if len(data) < RECORD_HEAD:
        raise ImageProblem(f"a {len(data)}-byte record has no 24-byte head")
    checksum, references = struct.unpack_from("<HI", data, 0)
    datalen, width, height = struct.unpack_from("<IHH", data, 6)
    mode, flags = data[0x0E], data[0x0F]
    hx, hy, ax, ay = struct.unpack_from("<4H", data, 0x10)
    if RECORD_HEAD + datalen != len(data):
        raise ImageProblem(
            f"declared {datalen} data bytes, the record holds "
            f"{len(data) - RECORD_HEAD}")
    return ImageRecord(checksum, references, width, height, mode, flags,
                       (hx, hy), (ax, ay), data[RECORD_HEAD:])

def rle_decode(data: bytes, bpp: int) -> tuple[bytes, int]:
    """Unpack the run-length form images are stored in."""
    out = bytearray()
    pos = 0
    while pos < len(data):
        count = data[pos]
        pos += 1
        if count == 0:
            break
        n = count & 0x7F
        if count & 0x80:
            end = pos + n * bpp
            if end > len(data):
                raise ImageProblem(
                    f"a literal run of {n} at {pos - 1} overruns the stream")
            out += data[pos:end]
            pos = end
        else:
            end = pos + bpp
            if end > len(data):
                raise ImageProblem(
                    f"a repeat run at {pos - 1} has no colour to repeat")
            out += data[pos:end] * n
            pos = end
    return bytes(out), pos

def _walk_tgf(record: ImageRecord) -> tuple[
        list[list[tuple[int, int]]], bytes, int]:
    bpp = BYTES_PER_PIXEL[record.mode]
    h, payload = record.height, record.payload
    if len(payload) < 4 + 8 * h:
        raise ImageProblem("the payload cannot hold its own pointer list")
    (bufsize,) = struct.unpack_from("<I", payload, 0)
    ptrs = [struct.unpack_from("<II", payload, 4 + 8 * i) for i in range(h)]
    opq_start = 8 * h
    if ptrs[0][0] != opq_start:
        raise ImageProblem(
            f"line 0 opaqueness at {ptrs[0][0]}, the pointer list ends at "
            f"{opq_start}")
    colour_decomp_base = ptrs[0][1]
    opq_total = colour_decomp_base - opq_start
    colour_total = bufsize - 4 - 8 * h - opq_total
    colour_file_start = 4 + opq_start + opq_total
    if opq_total < 0 or colour_total < 0 or colour_file_start > len(payload):
        raise ImageProblem(
            f"buffer size {bufsize} and pointer list disagree about the "
            f"payload's own layout")
    line_pairs: list[list[tuple[int, int]]] = []
    for line in range(h):
        start = ptrs[line][0]
        end = ptrs[line + 1][0] if line + 1 < h else opq_start + opq_total
        if end < start or (end - start) % 2:
            raise ImageProblem(
                f"line {line} declares a {end - start}-byte pair span")
        span = payload[4 + start:4 + end]
        pairs = [(span[j], span[j + 1]) for j in range(0, len(span), 2)]
        cstart = ptrs[line][1] - colour_decomp_base
        cend = (ptrs[line + 1][1] - colour_decomp_base
                if line + 1 < h else colour_total)
        opaque = sum(o for _, o in pairs)
        if cend - cstart != opaque * bpp:
            raise ImageProblem(
                f"line {line} pairs hold {opaque} opaque pixels, the colour "
                f"pointers allot {cend - cstart} bytes at {bpp} per pixel")
        line_pairs.append(pairs)
    if record.flags & FLAG_RLE:
        colours, used = rle_decode(payload[colour_file_start:], bpp)
        if colour_file_start + used != len(payload):
            raise ImageProblem(
                f"colour list consumed {used} of "
                f"{len(payload) - colour_file_start}")
    else:
        colours = payload[colour_file_start:]
    if len(colours) < colour_total:
        raise ImageProblem(
            f"{len(colours)} colour bytes cannot fill the {colour_total} "
            f"the pointers allot")
    return line_pairs, colours, colour_total

def decode_rows(record: ImageRecord) -> list[list[int | None]]:
    """Turn a stored image into rows of pixels."""
    bpp = BYTES_PER_PIXEL.get(record.mode)
    if bpp is None:
        raise ImageProblem(f"graphic mode {record.mode} has no known pixel size")
    w, h, payload = record.width, record.height, record.payload
    if record.flags & FLAG_TGF_COMPRESSION:
        line_pairs, colours, _ = _walk_tgf(record)
        rows: list[list[int | None]] = []
        cpos = 0
        for line in range(h):
            row: list[int | None] = []
            for t, o in line_pairs[line]:
                row += [None] * t
                for _ in range(o):
                    row.append(int.from_bytes(colours[cpos:cpos + bpp],
                                              "little"))
                    cpos += bpp
            if len(row) > w:
                raise ImageProblem(
                    f"line {line} encodes {len(row)} pixels on a {w}-wide "
                    f"image")

            row += [None] * (w - len(row))
            rows.append(row)
        return rows

    if record.flags & FLAG_RLE:
        pixels, used = rle_decode(payload, bpp)
        if used != len(payload):
            raise ImageProblem(
                f"flat stream consumed {used} of {len(payload)}")
    else:
        pixels = payload
    if len(pixels) < w * h * bpp:
        raise ImageProblem(
            f"{len(pixels)} pixel bytes cannot fill {w}x{h} at {bpp}")
    return [
        [int.from_bytes(pixels[(line * w + x) * bpp:(line * w + x + 1) * bpp],
                        "little")
         for x in range(w)]
        for line in range(h)
    ]

def rle_encode(pixels: bytes, bpp: int) -> bytes:
    """Pack pixels back into that form."""
    out = bytearray()
    n = len(pixels) // bpp
    pos = 0
    while pos < n:
        run = 1
        first = pixels[pos * bpp:(pos + 1) * bpp]
        while (pos + run < n and run < 0x7F
               and pixels[(pos + run) * bpp:(pos + run + 1) * bpp] == first):
            run += 1
        if run >= 3 or (run > 1 and bpp > 1):
            out += bytes((run,)) + first
            pos += run
            continue
        start = pos
        while pos < n and pos - start < 0x7F:
            if (pos + 2 < n
                    and pixels[pos * bpp:(pos + 1) * bpp]
                    == pixels[(pos + 1) * bpp:(pos + 2) * bpp]
                    == pixels[(pos + 2) * bpp:(pos + 3) * bpp]):
                break
            pos += 1
        span = pos - start
        if span == 1:
            out += bytes((1,)) + pixels[start * bpp:(start + 1) * bpp]
        else:
            out += bytes((0x80 | span,)) + pixels[start * bpp:pos * bpp]
    out.append(0)
    return bytes(out)

def encode_tgf_image(rows: list[list[int | None]], mode: int,
                     flags: int) -> bytes:
    """Write an image out in the shape the format expects."""
    bpp = BYTES_PER_PIXEL[mode]
    h = len(rows)
    w = len(rows[0]) if rows else 0
    line_spans: list[bytes] = []
    colour_bytes = bytearray()
    colour_offsets: list[int] = []
    for row in rows:
        assert len(row) == w
        colour_offsets.append(len(colour_bytes))
        pairs = bytearray()
        x = 0
        while x < w:
            t = 0
            while x < w and row[x] is None and t < 255:
                t += 1
                x += 1
            o = 0
            o_start = x
            while x < w and row[x] is not None and o < 255:
                o += 1
                x += 1
            pairs += bytes((t, o))
            for value in row[o_start:o_start + o]:
                colour_bytes += int(value).to_bytes(bpp, "little")
        line_spans.append(bytes(pairs))
    opq_total = sum(len(s) for s in line_spans)
    colour_base = 8 * h + opq_total
    payload = bytearray()
    bufsize = 4 + 8 * h + opq_total + len(colour_bytes)
    payload += struct.pack("<I", bufsize)
    opq_at = 8 * h
    for span, coff in zip(line_spans, colour_offsets):
        payload += struct.pack("<II", opq_at, colour_base + coff)
        opq_at += len(span)
    for span in line_spans:
        payload += span
    if flags & FLAG_RLE:
        payload += rle_encode(bytes(colour_bytes), bpp)
    else:
        payload += colour_bytes
    return bytes(payload)
