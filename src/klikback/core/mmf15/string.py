# GENERATED — do not edit by hand. This file is produced by KlikBack's
# sync tooling; changes belong in the source it is generated from.
#
# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""The String object, rebuilt from the compiled game."""

from __future__ import annotations
import struct
from klikback.core.mmf15.object_record import ObjectRecordProblem
from klikback.core.common.blind_core_reconstruct import string_paragraphs

STRING = 3

STRING_KIND = b"Strg"

NO_FOLLOW_FRAME = 0x08

DISPLAY_PROPERTY = 0x10

NO_DESTROY_IF_FAR = 0x20

NO_INACTIVATE_IF_FAR = 0x40

DISPLAY_FLAGS_OFFSET = 0x28

SAVE_BACKGROUND = 0x01

WIPE_WITH_COLOUR = 0x02

VISIBLE_AT_START = 0x08

OBJECT_COLOUR_OFFSET = 0x30

def runtime_tail(obj: dict) -> bytes:
    """The object's paragraphs and formatting, as the compiled game stored them.
    """
    width, height, texts, font, colour, reserved = string_paragraphs(
        obj["definition"]
    )
    editor_font = 0xFFFFFFFF if font == 0xFFFF else font
    return (
        struct.pack(
            "<7I",
            width,
            height,
            editor_font,
            colour,
            reserved,
            0,
            len(texts),
        )
        + b"".join(
            struct.pack("<I", len(text)) + text + struct.pack("<I", 0)
            for text in texts
        )
    )

def build_string_tail(item_id: int, icon: int, obj: dict) -> bytes:
    """Write those into the project's own record shape."""
    return struct.pack("<I4sI", item_id, b"icnI", icon) + runtime_tail(obj)

def split_string_tail(tail: bytes) -> tuple[int, int, bytes]:
    """Read them back out of a project record."""
    if len(tail) < 48 or tail[4:8] != b"icnI":
        raise ObjectRecordProblem(
            f"String tail is {len(tail)} bytes and opens "
            f"{tail[:12].hex(' ')}, expected u32 then 'icnI'"
        )
    item_id, icon = struct.unpack_from("<I4xI", tail, 0)
    _width, _height, _font, _colour, _reserved, zero, count = (
        struct.unpack_from("<7I", tail, 12)
    )
    if zero != 0:
        raise ObjectRecordProblem(f"String style trailer is {zero}, expected 0")
    cursor = 40
    for _index in range(count):
        if cursor + 8 > len(tail):
            raise ObjectRecordProblem("String paragraph header is truncated")
        (length,) = struct.unpack_from("<I", tail, cursor)
        cursor += 4 + length
        if cursor + 4 > len(tail):
            raise ObjectRecordProblem("String paragraph text is truncated")
        (paragraph_zero,) = struct.unpack_from("<I", tail, cursor)
        if paragraph_zero != 0:
            raise ObjectRecordProblem(
                f"String paragraph trailer is {paragraph_zero}, expected 0"
            )
        cursor += 4
    if cursor != len(tail):
        raise ObjectRecordProblem(
            f"String tail walk ends at {cursor}, record ends at {len(tail)}"
        )
    return item_id, icon, tail[12:]
