# GENERATED — do not edit by hand. This file is produced by KlikBack's
# sync tooling; changes belong in the source it is generated from.
#
# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""Build a Counter's editor record, including how its digits are drawn."""

from __future__ import annotations
import struct
from klikback.core.common.exe_to_cca import icon_and_image_bank_offsets
from klikback.core.mmf1.template_synthesis import counter_solo_template

COUNTER_TEMPLATE = counter_solo_template()

def counter_editor_record(counter: dict) -> bytes:
    """A Counter in the form a project stores."""
    record = bytearray(COUNTER_TEMPLATE)
    value_tag = record.index(b"Valu")
    struct.pack_into("<i", record, value_tag + 0x24, counter["initial"])
    struct.pack_into("<i", record, value_tag + 0x40, counter["minimum"])
    struct.pack_into("<i", record, value_tag + 0x5C, counter["maximum"])

    name_tag = record.index(b"ItNa")
    name_pos = name_tag + 0x24
    icon_property = record.index(b"\x04\x00ItIc", name_pos)
    struct.pack_into("<H", record, name_tag + 0x1A, len(counter["name"]))
    record[name_pos:icon_property] = counter["name"]

    image_tag = record.index(b"ImSt")
    image_end = len(record) - 8
    image_records = b"".join(
        b"Imag" + struct.pack("<I", image_id)
        for image_id in counter["image_ids"]
    )
    record[image_tag:image_end] = (
        b"ImSt" + struct.pack("<I", len(counter["image_ids"])) + image_records
    )

    struct.pack_into("<iI", record, len(record) - 8, counter["width"], counter["height"])

    fill = counter.get("fill")
    if fill is not None:
        icn = record.index(b"icnI")
        fill_start = icn + 4 + 5 * 4
        record[fill_start : record.index(b"ImSt")] = fill
    return bytes(record)

def apply_editor_palette(cca: bytes, runtime_palette: bytes) -> bytes:
    """Fit a Counter's colours to the palette the project uses."""
    if len(runtime_palette) != 0x400:
        raise ValueError("runtime palette must contain 256 four-byte entries")
    data = bytearray(cca)

    bank_pos = icon_and_image_bank_offsets(cca)[1]
    palette_pos = bank_pos + 0x0C
    for color_index in range(256):
        runtime_pos = color_index * 4
        editor_pos = palette_pos + runtime_pos
        data[editor_pos : editor_pos + 3] = runtime_palette[
            runtime_pos : runtime_pos + 3
        ]
        data[editor_pos + 3] = 0
    return bytes(data)
