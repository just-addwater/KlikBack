# GENERATED — do not edit by hand. This file is produced by KlikBack's
# sync tooling; changes belong in the source it is generated from.
#
# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""An object's movement, translated between the compiled game and the editor.

Movement is stored one way for the runtime, which only has to execute it, and
another for the editor, which has to show it and let you change it. This
converts between the two, including the movement kinds an extension module
provides rather than the editor itself.
"""

from __future__ import annotations
import struct
from klikback.core.mmf15.cca import ClassBlock, Entry, Property
from klikback.core.mmf15.object_record import ObjectRecordProblem

MOVEMENT_TAGS = {
    0: "MSta",
    1: "MMou",
    2: "MRac",
    3: "MGen",
    4: "MBal",
    5: "MPat",
    9: "MPla",
}

ALL_MOVEMENT_TAGS = frozenset(MOVEMENT_TAGS.values())

def runtime_movement(obj: dict) -> tuple[int, bytes]:
    """An object's movement, as the compiled game stored it."""
    definition = obj["definition"]
    if len(definition) < 8:
        raise ObjectRecordProblem("runtime Active definition is truncated")
    movement_offset, animation_offset = struct.unpack_from("<HH", definition, 4)
    if movement_offset == 0:
        if not 8 <= animation_offset <= len(definition):
            raise ObjectRecordProblem(
                f"static Active animation offset {animation_offset} is invalid"
            )
        return 0, b""
    if not 8 <= movement_offset < animation_offset <= len(definition):
        raise ObjectRecordProblem(
            f"movement/animation offsets {movement_offset}/{animation_offset} "
            "are invalid"
        )
    movement = definition[movement_offset:animation_offset]
    if len(movement) < 4:
        raise ObjectRecordProblem("runtime movement block is truncated")
    movement_type = struct.unpack_from("<H", movement, 2)[0]
    return movement_type, movement

def runtime_extension_movement(obj: dict) -> tuple[int, bytes]:
    """The same, for a movement a module provides."""
    definition = obj["definition"]
    if len(definition) < 0x28:
        raise ObjectRecordProblem("runtime extension definition is truncated")
    movement_offset, animation_offset = struct.unpack_from("<HH", definition, 4)
    editdata_offset = struct.unpack_from("<I", definition, 0x24)[0]
    if animation_offset or not editdata_offset:

        raise ObjectRecordProblem(
            f"extension definition has animation offset {animation_offset} "
            f"and EDITDATA offset {editdata_offset}"
        )
    if movement_offset == 0:
        return 0, b""
    if not 8 <= movement_offset < editdata_offset <= len(definition):
        raise ObjectRecordProblem(
            f"extension movement/EDITDATA offsets {movement_offset}/"
            f"{editdata_offset} are invalid"
        )
    movement = definition[movement_offset:editdata_offset]
    if len(movement) < 4:
        raise ObjectRecordProblem("runtime movement block is truncated")
    return struct.unpack_from("<H", movement, 2)[0], movement

def movement_property(movement_type: int, movement: bytes) -> Property:
    """The editor property holding a movement."""
    tag = MOVEMENT_TAGS.get(movement_type)
    if tag is None:
        raise ObjectRecordProblem(
            f"movement type {movement_type} has no measured MMF 1.5 property"
        )
    return Property(
        tag=tag,
        unknown=1,
        entries=[
            Entry(
                type_id=0x0A,
                index=0,
                a=1,
                b=1,
                size=len(movement),
                word=len(movement),
                payload=movement,
            )
        ],
    )

def set_movement_property(block: ClassBlock, obj: dict, reader=None) -> None:
    """Write a recovered movement into an object's record."""
    block.properties = [
        prop for prop in block.properties if prop.tag not in ALL_MOVEMENT_TAGS
    ]
    movement_type, movement = (reader or runtime_movement)(obj)

    if not movement:
        return
    prop = movement_property(movement_type, movement)

    insert_at = next(
        (index for index, existing in enumerate(block.properties)
         if existing.tag == "SFFg"),
        len(block.properties),
    )
    block.properties.insert(insert_at, prop)
