# GENERATED — do not edit by hand. This file is produced by KlikBack's
# sync tooling; changes belong in the source it is generated from.
#
# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""Build a String object's editor record."""

from __future__ import annotations
import struct
from klikback.core.mmf1.template_synthesis import string_solo_template

STRING_TEMPLATE = string_solo_template()

def string_editor_record(string: dict) -> bytes:
    """A String object in the form a project stores."""
    record = bytearray(STRING_TEMPLATE)
    name_tag = record.index(b"ItNa")
    name_pos = name_tag + 0x24
    icon_property = record.index(b"\x04\x00ItIc", name_pos)
    struct.pack_into("<H", record, name_tag + 0x1A, len(string["name"]))
    record[name_pos:icon_property] = string["name"]

    icon_tag = record.index(b"icnI")
    tail_pos = icon_tag + 8
    fixed_tail = bytes(record[tail_pos : tail_pos + 24])
    record[tail_pos:] = (
        struct.pack("<II", string["width"], string["height"])
        + fixed_tail[8:]
        + struct.pack("<I", 1)
        + struct.pack("<I", len(string["text"]))
        + string["text"]
        + b"\x00" * 4
    )
    return bytes(record)
