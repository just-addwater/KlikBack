# GENERATED — do not edit by hand. This file is produced by KlikBack's
# sync tooling; changes belong in the source it is generated from.
#
# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""The Quick Backdrop, rebuilt from the compiled game.

A Quick Backdrop is a shape or a fill rather than a stored picture, so what has
to survive is how it is drawn: its pattern, its colours and its borders.
"""

from __future__ import annotations
import struct
from klikback.core.mmf15.object_record import ObjectRecordProblem
from klikback.core.common.solo_object_reconstruct import quick_backdrop_fill_block, quick_backdrop_payload

QUICK_BACKDROP = 0

QUICK_BACKDROP_KIND = b"DrBa"

def runtime_tail(obj: dict) -> bytes:
    """The object's fill and border settings, as the compiled game stored them.
    """
    payload = quick_backdrop_payload(obj["definition"])
    return (
        struct.pack("<III", payload["kind"], payload["extra"], payload["obstacle"])
        + quick_backdrop_fill_block(payload)
        + struct.pack("<II", payload["width"], payload["height"])
    )

def build_quick_backdrop_tail(item_id: int, icon: int, obj: dict) -> bytes:
    """Write those into the project's own record shape."""
    return struct.pack("<I4sI", item_id, b"icnI", icon) + runtime_tail(obj)

def split_quick_backdrop_tail(tail: bytes) -> tuple[int, int, bytes, int | None]:
    """Read them back out of a project record."""
    if len(tail) < 32 or tail[4:8] != b"icnI":
        raise ObjectRecordProblem(
            f"Quick Backdrop tail is {len(tail)} bytes and opens "
            f"{tail[:12].hex(' ')}, expected u32 then 'icnI'"
        )
    (item_id,) = struct.unpack_from("<I", tail, 0)
    (icon,) = struct.unpack_from("<I", tail, 8)
    tag = tail[24:28]
    fill_sizes = {b"Zfll": 4, b"Sfll": 8, b"Gfll": 16, b"Mfll": 8}
    if tag not in fill_sizes:
        raise ObjectRecordProblem(f"unknown Quick Backdrop fill tag {tag!r}")
    expected = 24 + fill_sizes[tag] + 8
    if len(tail) != expected:
        raise ObjectRecordProblem(
            f"{tag.decode('ascii')} tail is {len(tail)} bytes, expected {expected}"
        )
    motif = struct.unpack_from("<I", tail, 28)[0] if tag == b"Mfll" else None
    return item_id, icon, tail[12:], motif
