# GENERATED — do not edit by hand. This file is produced by KlikBack's
# sync tooling; changes belong in the source it is generated from.
#
# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""Split a compiled event program into its individual events."""

from __future__ import annotations
import struct

def split_event_records(data: bytes) -> tuple[list[bytes], bytes]:
    """Separate one program into the events that make it up."""
    records: list[bytes] = []
    pos = 0
    while pos + 2 <= len(data):
        signed_size = struct.unpack_from("<h", data, pos)[0]
        if signed_size >= 0:
            break
        size = -signed_size
        if size < 0x0E or pos + size > len(data):
            break
        records.append(data[pos : pos + size])
        pos += size
    return records, data[pos:]
