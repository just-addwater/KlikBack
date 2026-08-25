# GENERATED — do not edit by hand. This file is produced by KlikBack's
# sync tooling; changes belong in the source it is generated from.
#
# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""The Question & Answer object, rebuilt from the compiled game."""

from __future__ import annotations
import struct
from klikback.core.mmf15.object_record import ObjectRecordProblem
from klikback.core.common.solo_object_reconstruct import qanda_block_header, qanda_payload

QANDA = 4

QANDA_KIND = b"Qstn"

def _build_block(strings: list[dict]) -> bytes:
    if not strings:
        raise ObjectRecordProblem("Question & Answer block is empty")
    colors = {string["color"] for string in strings}
    fonts = {string["font"] for string in strings}
    if len(colors) != 1:
        raise ObjectRecordProblem("Question & Answer block has mixed colours")
    if len(fonts) != 1:
        raise ObjectRecordProblem("Question & Answer block has mixed fonts")
    body = qanda_block_header(colors.pop(), fonts.pop())
    body += struct.pack("<I", len(strings))
    for string in strings:
        body += (
            struct.pack("<I", len(string["text"]))
            + string["text"]
            + struct.pack("<I", string["flag"])
        )
    return body

def runtime_tail(obj: dict) -> bytes:
    """The object's settings, as the compiled game stored them."""
    payload = qanda_payload(obj["definition"])
    strings = payload["strings"]
    if len(strings) < 2:
        raise ObjectRecordProblem(
            f"Question & Answer has {len(strings)} strings, expected question+answer"
        )
    return (
        struct.pack("<II", payload["width"], payload["height"])
        + _build_block([strings[0]])
        + _build_block(strings[1:])
    )

def build_qanda_tail(item_id: int, icon: int, obj: dict) -> bytes:
    """Write those settings into the project's own record shape."""
    return struct.pack("<I4sI", item_id, b"icnI", icon) + runtime_tail(obj)

def _split_block(tail: bytes, pos: int) -> tuple[int, int, int]:
    if pos + 20 > len(tail):
        raise ObjectRecordProblem("Question & Answer block header is truncated")
    font, _colour, format_word, zero, count = struct.unpack_from(
        "<iIIII", tail, pos
    )
    if format_word != 0x25 or zero != 0:
        raise ObjectRecordProblem(
            f"Question & Answer block framing is {format_word:#x}/{zero}"
        )
    pos += 20
    for _ in range(count):
        if pos + 8 > len(tail):
            raise ObjectRecordProblem("Question & Answer string is truncated")
        (length,) = struct.unpack_from("<I", tail, pos)
        pos += 4
        if pos + length + 4 > len(tail):
            raise ObjectRecordProblem("Question & Answer text overruns its block")
        pos += length + 4
    return pos, font, count

def split_qanda_tail(tail: bytes) -> dict:
    """Read them back out of a project record."""
    if len(tail) < 60 or tail[4:8] != b"icnI":
        raise ObjectRecordProblem(
            f"Question & Answer tail is {len(tail)} bytes and opens "
            f"{tail[:12].hex(' ')}"
        )
    item_id, icon = struct.unpack_from("<I4xI", tail, 0)
    pos, question_font, question_count = _split_block(tail, 20)
    pos, answer_font, answer_count = _split_block(tail, pos)
    if question_count != 1:
        raise ObjectRecordProblem(
            f"Question block holds {question_count} strings, expected 1"
        )
    if answer_count < 1:
        raise ObjectRecordProblem("answer block is empty")
    if pos != len(tail):
        raise ObjectRecordProblem(
            f"Question & Answer tail walk ends at {pos}, record ends at {len(tail)}"
        )
    fonts = {
        font for font in (question_font, answer_font) if font != -1
    }
    return {
        "item_id": item_id,
        "icon": icon,
        "runtime_tail": tail[12:],
        "fonts": fonts,
    }
