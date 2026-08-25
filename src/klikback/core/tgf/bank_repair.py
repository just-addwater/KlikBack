# GENERATED — do not edit by hand. This file is produced by KlikBack's
# sync tooling; changes belong in the source it is generated from.
#
# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""Repair 1996 bank images that a stricter reader will not accept.

The 1996 editors read a bank by following its pointer list, and tolerate a
record that does not quite add up. Later Clickteam software re-decodes the same
bank strictly -- each line's runs must reach the width exactly -- and refuses
the whole file over a handful of images the original editors open without
complaint.

So a game can be entirely sound by the standard of the tool that made it and
still be rejected by a newer one. This rewrites just those records into a form
both readers accept, and leaves everything else alone.
"""

from __future__ import annotations
import struct
import klikback.core.tgf.format as tgf
import klikback.core.tgf.image as img

def sum_driven_ok(rec: img.ImageRecord) -> tuple[bool, str]:
    """Whether a record already satisfies the stricter reading."""
    if not rec.flags & img.FLAG_TGF_COMPRESSION:
        return True, ""
    bpp = img.BYTES_PER_PIXEL.get(rec.mode)
    if bpp is None:
        return True, ""
    p, w, h = rec.payload, rec.width, rec.height
    if len(p) < 4 + 8 * h:
        return False, "payload cannot hold its pointer list"
    pos = 4 + 8 * h
    opaque_total = 0
    for line in range(h):
        total = 0
        while total < w:
            if pos + 2 > len(p):
                return False, f"line {line}: payload exhausted"
            t, o = p[pos], p[pos + 1]
            pos += 2
            total += t + o
            opaque_total += o
        if total != w:
            return False, f"line {line}: sums to {total} of {w}"
    if rec.flags & img.FLAG_RLE:
        try:
            colours, _ = img.rle_decode(p[pos:], bpp)
        except img.ImageProblem as e:
            return False, f"colour stream: {e}"
    else:
        colours = p[pos:]
    if len(colours) < opaque_total * bpp:
        return False, f"colours {len(colours)} short of {opaque_total * bpp}"
    return True, ""

RLE_OVERRUN_TOLERANCE = 3

def rle_overrun(rec: img.ImageRecord) -> int:
    if not rec.flags & img.FLAG_TGF_COMPRESSION or not rec.flags & img.FLAG_RLE:
        return 0
    bpp = img.BYTES_PER_PIXEL.get(rec.mode)
    if bpp is None:
        return 0
    p, h = rec.payload, rec.height
    if len(p) < 4 + 8 * h or h == 0:
        return 0
    (declared,) = struct.unpack_from("<I", p, 0)
    pointers = [struct.unpack_from("<II", p, 4 + 8 * i) for i in range(h)]
    colour_base = min(c for _o, c in pointers)
    expected = declared - 4 - 8 * h - (colour_base - 8 * h)
    if expected < 0:
        return 0
    try:
        decoded, _ = img.rle_decode(p[4 + colour_base:], bpp)
    except img.ImageProblem:
        return 0
    return max(0, len(decoded) - expected)

def decode_lenient(rec: img.ImageRecord) -> list[list[int | None]]:
    """Decode a record the tolerant way the 1996 editors do."""
    bpp = img.BYTES_PER_PIXEL[rec.mode]
    p, w, h = rec.payload, rec.width, rec.height
    pos = 4 + 8 * h
    pair_runs: list[list[tuple[int, int]]] = []
    for line in range(h):
        total = 0
        pairs: list[tuple[int, int]] = []
        while total < w and pos + 2 <= len(p):
            t, o = p[pos], p[pos + 1]
            pos += 2
            if total + t + o > w:
                t = min(t, w - total)
                o = min(o, w - total - t)
            total += t + o
            pairs.append((t, o))
        pair_runs.append(pairs)
    if rec.flags & img.FLAG_RLE:
        try:
            colours, _ = img.rle_decode(p[pos:], bpp)
        except img.ImageProblem:
            colours = b""
    else:
        colours = p[pos:]
    rows: list[list[int | None]] = []
    cpos = 0
    for pairs in pair_runs:
        row: list[int | None] = []
        for t, o in pairs:
            row += [None] * t
            for _ in range(o):
                px = colours[cpos:cpos + bpp]
                cpos += bpp
                row.append(int.from_bytes(px, "little") if len(px) == bpp
                           else None)
        row += [None] * (len(row) < rec.width and rec.width - len(row) or 0)
        rows.append(row[:rec.width])
    return rows

def repair_record(raw: bytes) -> tuple[bytes, str]:
    """Rewrite one image into a form both readers accept."""
    rec = img.parse_record(raw)
    try:
        rows = img.decode_rows(rec)
        how = "exact (re-encoded from its own pixels, none changed)"
    except img.ImageProblem:
        rows = decode_lenient(rec)
        how = "best-effort (structure contradicts itself; missing pixels transparent)"
    payload = img.encode_tgf_image(rows, rec.mode,
                                   rec.flags if rec.flags & img.FLAG_RLE
                                   else rec.flags | img.FLAG_RLE)
    head = bytearray(raw[:img.RECORD_HEAD])
    struct.pack_into("<I", head, 6, len(payload))
    out = bytes(head) + payload

    made = img.parse_record(out)
    img.decode_rows(made)
    ok, why = sum_driven_ok(made)
    if not ok:
        raise img.ImageProblem(f"repair failed its own gate: {why}")
    if rle_overrun(made):
        raise img.ImageProblem(
            "repair failed its own gate: the re-encoded stream still "
            "overruns its declared buffer")
    return out, how

def repair_bank(segment_data: bytes) -> tuple[bytes, list[str]]:
    """Repair only the records a strict reader would reject."""
    slots = tgf.walk_bank(segment_data)
    (count,) = struct.unpack_from("<I", segment_data, 0)
    filled = {s: (o, z) for s, o, z in slots}
    repairs: dict[int, tuple[bytes, str]] = {}
    for slot, off, size in slots:
        try:
            rec = img.parse_record(segment_data[off:off + size])
        except img.ImageProblem:
            continue
        ok, why = sum_driven_ok(rec)
        overrun = rle_overrun(rec)
        if ok and overrun <= RLE_OVERRUN_TOLERANCE:
            continue
        repaired, how = repair_record(segment_data[off:off + size])
        if ok:
            how += (f"; the colour stream decoded {overrun} bytes past its "
                    f"declared buffer, against a measured ceiling of "
                    f"{RLE_OVERRUN_TOLERANCE}")
        repairs[slot] = (repaired, how)
    if not repairs:
        return segment_data, []
    report = []
    table = bytearray(struct.pack("<I", count))
    body = bytearray()
    base = 4 + 8 * count
    for slot in range(count):
        if slot not in filled:
            table += struct.pack("<II", 0, 0)
            continue
        off, size = filled[slot]
        data = (repairs[slot][0] if slot in repairs
                else segment_data[off:off + size])
        table += struct.pack("<II", base + len(body), len(data))
        body += data
        if slot in repairs:
            rec = img.parse_record(data)
            report.append(
                f"bank image {slot} ({rec.width}x{rec.height}) re-encoded "
                f"sum-exact: {repairs[slot][1]}")
    return bytes(table + body), report
