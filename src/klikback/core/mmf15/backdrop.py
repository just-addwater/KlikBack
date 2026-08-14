# GENERATED — do not edit by hand. This file is produced by KlikBack's
# sync tooling; changes belong in the source it is generated from.
#
# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""The Backdrop object's record in a 1.5 project."""

from __future__ import annotations
import struct
from klikback.core.mmf15.object_record import ObjectRecordProblem

BACKDROP = 1

BACKDROP_KIND = b"BkDr"

CHECKBOX_ON = 2

CHECKBOX_OFF = 1

def split_backdrop_tail(tail: bytes) -> tuple[int, int, int]:
    """Separate a Backdrop's trailing settings so they can be rebuilt."""
    if len(tail) != 16 or tail[4:8] != b"icnI":
        raise ObjectRecordProblem(
            f"Backdrop tail is {len(tail)} bytes and opens "
            f"{tail[:12].hex(' ')}, expected u32 then 'icnI'"
        )
    item_id = struct.unpack_from("<I", tail, 0)[0]
    icon = struct.unpack_from("<I", tail, 8)[0]
    image = struct.unpack_from("<I", tail, 12)[0]
    return item_id, icon, image
