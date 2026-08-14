# GENERATED — do not edit by hand. This file is produced by KlikBack's
# sync tooling; changes belong in the source it is generated from.
#
# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""Recover a 1.0 object's movement."""

from __future__ import annotations
import struct

STATIC_DESCRIPTOR = b"\x04\x00MSta\x00\x00ATSd\x00\x00"

GENERAL_DESCRIPTOR = b"\x04\x00MGen\x00\x00NEGd\x00\x00"

def runtime_movement(definition: bytes) -> tuple[int, bytes]:
    """An object's movement, as the compiled game stored it."""
    if len(definition) < 8:
        raise ValueError("runtime Active definition is truncated")
    movement_offset, animation_offset = struct.unpack_from("<HH", definition, 4)
    if not 8 <= movement_offset < animation_offset <= len(definition):
        raise ValueError("runtime movement/animation offsets are invalid")
    movement = definition[movement_offset:animation_offset]
    if len(movement) < 4:
        raise ValueError("runtime movement record is truncated")
    movement_type = struct.unpack_from("<H", movement, 2)[0]
    return movement_type, movement

def movement_wrapper(tag: bytes, movement: bytes, template: bytes) -> bytes:
    """The record a movement is stored inside."""
    if len(tag) != 4 or len(template) < 30:
        raise ValueError("invalid editor movement wrapper template")
    wrapper = bytearray(template[:30])
    wrapper[2:6] = tag
    struct.pack_into("<H", wrapper, 16, len(movement))
    struct.pack_into("<I", wrapper, 26, len(movement))
    return bytes(wrapper) + movement + struct.pack("<I", 1)

def replace_static_movement(
    record: bytes,
    movement: bytes,
    *,
    editor_tag: bytes,
    remove_descriptors: tuple[bytes, ...],
) -> bytes:
    """Give an object that does not move the record the editor expects."""
    data = bytearray(record)
    movement_start = data.index(b"\x04\x00MSta", 0x200)
    property_tag = data.index(b"P\x00\x00PROP", movement_start)
    movement_end = property_tag - 4
    old_wrapper = bytes(data[movement_start:movement_end])
    data[movement_start:movement_end] = movement_wrapper(
        editor_tag, movement, old_wrapper
    )

    for descriptor in remove_descriptors:
        descriptor_pos = data.find(descriptor, movement_start)
        if descriptor_pos < 0:
            raise ValueError(
                f"editor movement descriptor is absent: {descriptor.hex(' ')}"
            )
        del data[descriptor_pos : descriptor_pos + len(descriptor)]

    property_tag = data.index(b"P\x00\x00PROP", movement_start)
    property_count = struct.unpack_from("<H", data, property_tag - 4)[0]
    if property_count == 0:
        raise ValueError("editor property count cannot be decremented")
    if property_count < len(remove_descriptors):
        raise ValueError("editor property count cannot be decremented")
    struct.pack_into(
        "<H", data, property_tag - 4, property_count - len(remove_descriptors)
    )
    return bytes(data)
