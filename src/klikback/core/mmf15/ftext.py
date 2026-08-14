# GENERATED — do not edit by hand. This file is produced by KlikBack's
# sync tooling; changes belong in the source it is generated from.
#
# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""The Formatted Text object, rebuilt from the compiled game."""

from __future__ import annotations
import struct
from klikback.core.mmf15.object_record import ObjectRecordProblem

FORMATTED_TEXT = 8

FORMATTED_TEXT_KIND = b"RTF "

FORMATTED_TEXT_INSTANCE_TAG = b"IPIn"

CTE_NAME = b"class CTE"

def ftext_payload(definition: bytes) -> dict:
    """The text and its formatting, as the compiled game stored them."""
    if len(definition) < 16:
        raise ValueError("runtime Formatted Text definition is truncated")
    declared = struct.unpack_from("<I", definition, 0)[0]
    if declared != len(definition):
        raise ValueError(
            f"runtime Formatted Text definition declares {declared} bytes, "
            f"stores {len(definition)}"
        )
    candidates = []
    for position in range(8, len(definition) - 3):
        length = struct.unpack_from("<I", definition, position)[0]
        if position + 4 + length != len(definition):
            continue
        if definition[position - 4 : position] != b"\x00\x00\x00\x00":
            continue
        candidates.append((position, length))
    if len(candidates) != 1:
        raise ValueError(
            "runtime Formatted Text definition has "
            f"{len(candidates)} terminal RTF candidates"
        )
    position, length = candidates[0]
    width, height = struct.unpack_from("<HH", definition, position - 8)
    return {
        "width": width,
        "height": height,
        "text": definition[position + 4 : position + 4 + length],
    }

def runtime_tail(obj: dict) -> bytes:
    """The object's trailing settings in the compiled game."""
    payload = ftext_payload(obj["definition"])
    return (
        struct.pack("<III", payload["width"], payload["height"], len(CTE_NAME))
        + CTE_NAME
        + struct.pack("<II", 0, len(payload["text"]))
        + payload["text"]
    )

def build_ftext_tail(item_id: int, icon: int, obj: dict) -> bytes:
    """Write those settings into the project's own record shape."""
    return struct.pack("<I4sI", item_id, b"icnI", icon) + runtime_tail(obj)

def split_ftext_tail(tail: bytes) -> dict:
    """Read them back out of a project record."""
    if len(tail) < 41 or tail[4:8] != b"icnI":
        raise ObjectRecordProblem(
            f"Formatted Text tail is {len(tail)} bytes and opens "
            f"{tail[:12].hex(' ')}"
        )
    item_id, icon, _width, _height, name_length = struct.unpack_from(
        "<I4xIIII", tail, 0
    )
    pos = 24
    if name_length != len(CTE_NAME) or tail[pos:pos + name_length] != CTE_NAME:
        raise ObjectRecordProblem(
            f"Formatted Text names a {name_length}-byte class other than CTE"
        )
    pos += name_length
    if pos + 8 > len(tail):
        raise ObjectRecordProblem("Formatted Text CTE framing is truncated")
    zero, length = struct.unpack_from("<II", tail, pos)
    pos += 8
    if zero != 0:
        raise ObjectRecordProblem(f"Formatted Text CTE prefix is {zero}, expected 0")
    if pos + length != len(tail):
        raise ObjectRecordProblem(
            f"Formatted Text declares {length} RTF bytes but stores "
            f"{len(tail) - pos}"
        )
    return {
        "item_id": item_id,
        "icon": icon,
        "runtime_tail": tail[12:],
        "rtf": tail[pos:],
    }
