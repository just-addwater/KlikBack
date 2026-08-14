# GENERATED — do not edit by hand. This file is produced by KlikBack's
# sync tooling; changes belong in the source it is generated from.
#
# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""The Active object's record in a 1.5 project, rebuilt from the compiled game.

The Active carries movement, animation and most of what makes a game a game,
and its record is correspondingly the largest. It is modelled properly rather
than treated as an opaque run of bytes: the animations, the movement block and
the trailing properties are each read out and written back by name.
"""

from __future__ import annotations
import re
import struct
from pathlib import Path
from klikback.core.common.blind_core_reconstruct import nested_payload
from klikback.core.common.compare import find_chunk
from klikback.core.common.compression_probe import load_exe_frame
from klikback.core.common.exe_to_cca import decompress_chunk
from klikback.core.common.multi_animation_reconstruct import parse_runtime_animation_set
from klikback.core.common.object_analysis import split_object_chunks

OBJECT_BANK_CHUNK = 0x2229

OBJECT_HEADER_CHUNK = 0x4444

OBJECT_NAME_CHUNK = 0x4445

OBJECT_DEFINITION_CHUNK = 0x4446

ACTIVE = 2

ACTIVE_KIND = b"Actv"

OBJECT_SPAN = re.compile(r"frame\d+-object\d+")

ANIMATION_OFFSET_FIELD = 6

class ObjectRecordProblem(Exception):
    """Raised when an object record matches no shape this models."""

def runtime_objects(exe: Path) -> list[dict]:
    """Every object the compiled game defines, with its type and settings."""
    outer, _frame = load_exe_frame(exe)
    found = []
    bank = decompress_chunk(find_chunk(outer, OBJECT_BANK_CHUNK))
    for index, chunks in enumerate(split_object_chunks(bank)):
        header = nested_payload(chunks, OBJECT_HEADER_CHUNK)
        object_id, object_type = struct.unpack_from("<HH", header, 0)
        named = any(chunk.chunk_id == OBJECT_NAME_CHUNK for chunk in chunks)
        found.append(
            {
                "index": index,
                "object_id": object_id,
                "object_type": object_type,

                "header": header,
                "name": (
                    nested_payload(chunks, OBJECT_NAME_CHUNK).split(b"\x00", 1)[0]
                    if named
                    else b""
                ),
                "definition": nested_payload(chunks, OBJECT_DEFINITION_CHUNK),
            }
        )
    return found

def runtime_animations(definition: bytes) -> list[dict]:
    """An object's animation set, as the compiled game stored it."""
    (offset,) = struct.unpack_from("<H", definition, ANIMATION_OFFSET_FIELD)
    if not 8 <= offset < len(definition):
        raise ObjectRecordProblem(f"animation offset {offset} is out of range")
    return parse_runtime_animation_set(bytes(60) + definition[offset:])

def split_active_tail(tail: bytes) -> tuple[int, int, bytes]:
    """Separate the parts of an Active's record so each can be rebuilt."""
    if len(tail) < 12 or tail[4:8] != b"icnI":
        raise ObjectRecordProblem(
            f"Active tail opens {tail[:12].hex(' ')}, expected a u32 then 'icnI'"
        )
    (item_id,) = struct.unpack_from("<I", tail, 0)
    (icon,) = struct.unpack_from("<I", tail, 8)
    if tail[12:16] != b"AnSt":
        raise ObjectRecordProblem(f"expected 'AnSt' at +0x0C, found {tail[12:16]!r}")
    return item_id, icon, tail[12:]
