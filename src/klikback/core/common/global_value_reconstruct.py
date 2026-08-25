# GENERATED — do not edit by hand. This file is produced by KlikBack's
# sync tooling; changes belong in the source it is generated from.
#
# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""Recover an application's global values -- the ones every frame can see."""

from __future__ import annotations
import struct
from pathlib import Path
from klikback.core.common.compare import find_chunk
from klikback.core.common.compression_probe import load_exe_frame
from klikback.core.common.exe_to_cca import decompress_chunk, extract_events
from klikback.core.common.reconstruct_event_test import compiled_event_to_editor_event

GLOBAL_VALUE_TAG = b"\x04\x00GloV"

NEXT_PROPERTY_TAG = b"\x04\x00Menu"

def runtime_global_values(exe_path: Path) -> tuple[list[int], list[bytes]]:
    """The global values a compiled game carries, with their initial contents.
    """

    outer, frame = load_exe_frame(exe_path)
    payload = decompress_chunk(find_chunk(outer, 0x2232))
    if len(payload) < 2:
        raise ValueError("truncated runtime Global Values chunk")
    count = struct.unpack_from("<H", payload, 0)[0]

    if len(payload) != 2 + count * 5:
        raise ValueError(
            f"unexpected Global Values size {len(payload)} for {count} values"
        )
    values = list(struct.unpack_from(f"<{count}i", payload, 2))
    flags_pos = 2 + count * 4
    for index, flag in enumerate(payload[flags_pos:]):
        if flag != 0:
            raise ValueError(
                f"unsupported Global Value flag {flag} at index {index}"
            )

    compiled = extract_events(decompress_chunk(find_chunk(frame, 0x333D)))
    events = [
        compiled_event_to_editor_event(event, object_id_map={0: 0})
        for event in compiled
    ]
    return values, events

def global_value_record(
    index: int, name: bytes, value: int, name_marker: int = 0
) -> bytes:
    """One global value in the form a project stores."""

    if b"\x00" in name:
        raise ValueError("Global Value names cannot contain NUL bytes")
    name_and_flag = name + b"\x00" + struct.pack("<I", name_marker)
    if len(name_and_flag) > 34:
        raise ValueError("Global Value name is too long for the Build 98 record")
    output = bytearray(44)

    struct.pack_into("<HHH", output, 0, 0, len(output), index)
    output[6 : 6 + len(name_and_flag)] = name_and_flag

    struct.pack_into("<i", output, 40, value)
    return bytes(output)

def global_values_property(names: list[bytes], values: list[int]) -> bytes:
    """The application property holding them all."""
    if len(names) != len(values):
        raise ValueError("Global Value name/value counts differ")
    records = b"".join(
        global_value_record(
            index,
            name,
            value,
            name_marker=1 if len(values) == 1 else 0,
        )
        for index, (name, value) in enumerate(zip(names, values))
    )
    payload = struct.pack("<I", len(values)) + records
    return (
        GLOBAL_VALUE_TAG
        + struct.pack("<II", 1, 1)
        + struct.pack("<HH", 10, len(payload))
        + struct.pack("<II", 1, 1)
        + struct.pack("<I", len(payload))
        + payload
    )

def replace_global_values_property(cca: bytes, property_data: bytes) -> bytes:
    """Write the recovered values into the rebuilt application."""
    start = cca.index(GLOBAL_VALUE_TAG)
    end = cca.index(NEXT_PROPERTY_TAG, start)
    return cca[:start] + property_data + cca[end:]
