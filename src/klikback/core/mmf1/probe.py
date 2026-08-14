# GENERATED — do not edit by hand. This file is produced by KlikBack's
# sync tooling; changes belong in the source it is generated from.
#
# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""Locate the parts of a compiled 1.0 game inside its executable.

The first thing anything else needs: where the game's own data begins, and how
large its banks are.
"""

from __future__ import annotations
import struct

def agmi_size(data: bytes, start: int) -> tuple[int, int]:
    """How large an image bank is."""
    if data[start : start + 4] != b"AGMI":
        raise ValueError("not an AGMI segment")
    count = struct.unpack_from("<I", data, start + 0x40C)[0]
    pos = start + 0x410
    for _ in range(count):
        image_size = struct.unpack_from("<I", data, pos + 0x0A)[0]
        pos += 0x1C + image_size
    return pos - start, count
