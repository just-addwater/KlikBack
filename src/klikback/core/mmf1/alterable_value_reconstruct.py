# GENERATED — do not edit by hand. This file is produced by KlikBack's
# sync tooling; changes belong in the source it is generated from.
#
# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""Recover an object's alterable values -- its own per-object variables."""

from __future__ import annotations
import struct

ALTERABLE_VALUE_TAG = b"\x04\x00AltV"

NEUTRAL_ALTERABLE_VALUE_METADATA = b"\x00" * 27

RUNTIME_ALTERABLE_VALUES_OFFSET = 0x26

def runtime_alterable_values(definition: bytes) -> list[int]:
    """The values an object carries, as the compiled game stored them."""
    if len(definition) < RUNTIME_ALTERABLE_VALUES_OFFSET + 2:
        return []
    offset = struct.unpack_from("<H", definition, RUNTIME_ALTERABLE_VALUES_OFFSET)[0]
    if offset == 0:
        return []
    if offset + 2 > len(definition):
        raise ValueError("Active alterable-value table points outside definition")
    count = struct.unpack_from("<H", definition, offset)[0]
    if count not in (1, 2, 3):
        raise ValueError(
            f"only one-to-three-value runtime tables are observed, found {count}"
        )
    end = offset + 2 + 4 * count
    if end != len(definition):
        raise ValueError("Active alterable-value table does not end at definition end")
    return list(struct.unpack_from(f"<{count}i", definition, offset + 2))

def alterable_value_record(
    index: int,
    name: bytes,
    value: int,
    metadata: bytes = NEUTRAL_ALTERABLE_VALUE_METADATA,
) -> bytes:

    """One value in the form a project stores."""
    if len(name) != 6 or b"\x00" in name:
        raise ValueError("controlled alterable-value name must be six bytes")
    if len(metadata) != 27:
        raise ValueError("alterable-value editor metadata must be 27 bytes")
    record = (
        struct.pack("<HHH", 0, 44, index)
        + name
        + b"\x00"
        + metadata
        + struct.pack("<i", value)
    )
    if len(record) != 44:
        raise ValueError("alterable-value record is not 44 bytes")
    return record

def alterable_values_property(
    names: list[bytes],
    values: list[int],
    metadata_records: list[bytes] | None = None,
) -> bytes:
    """The property holding them all."""
    if len(names) != len(values):
        raise ValueError("alterable-value name/value counts differ")
    if metadata_records is None:
        metadata_records = [NEUTRAL_ALTERABLE_VALUE_METADATA] * len(values)
    if len(metadata_records) != len(values):
        raise ValueError("alterable-value metadata count differs")
    records = b"".join(
        alterable_value_record(index, name, value, metadata)
        for index, (name, value, metadata) in enumerate(
            zip(names, values, metadata_records)
        )
    )
    payload = struct.pack("<I", len(values)) + records
    return (
        ALTERABLE_VALUE_TAG
        + struct.pack("<II", 1, 1)
        + struct.pack("<HH", 10, len(payload))
        + struct.pack("<II", 1, 1)
        + struct.pack("<I", len(payload))
        + payload
    )
