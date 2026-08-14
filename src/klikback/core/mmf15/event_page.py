# GENERATED — do not edit by hand. This file is produced by KlikBack's
# sync tooling; changes belong in the source it is generated from.
#
# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""The editor's event page, rebuilt from a compiled game's event programs.

The compiled events are only half of an event sheet. The other half is the
page the editor draws them on: which objects have columns, in what order, and
how the rows are tiled across them. A compiled game keeps the events and
discards the page, so the page is rebuilt from what the events themselves
reference.
"""

from __future__ import annotations
import struct
from klikback.core.common.event_object_registry import qualifier_display_name

EVENT_PAGE = b"evpg"

EVENT_PAGE_HEADER_PREFIX = bytes.fromhex("00 03")

EVENTS = b"Evts"

REMARKS = b"Rems"

EVENT_OBJECT_LIST = b"EvOb"

EVENT_OBJECT = b"EvOi"

EVENT_EDITOR = b"EvEd"

EVENT_TEMPLATES = b"EvTe"

EVENT_SETTINGS = b"EvCs"

HANDLE_ALLOCATOR = b"!DNE"

COI_LIST_CLASS = b"class COIList"

REMARK_LIST_CLASS = b"class CEvtRemarkList"

OBJECT_ENTRY = 1

QUALIFIER_ENTRY = 3

QUALIFIER_TYPE = 2

QUALIFIER_FLAG = 0x8000

EVENT_OBJECT_TYPE_STRINGS = {
    2: b"Sprite",
    3: b"Text",
    4: b"Question",
    5: b"Score",
    6: b"Lives",
    7: b"Counter",

    8: b"",

    9: b"",
}

EXTENSION_OBJECT_TYPE_BASE = 32

HEADER_TAG = b"ER>>"

HEADER_FIXED_SIZE = 0x2E

HEADER_TAIL_COUNT = 0x2C

HEADER_TAIL_ENTRY = 4

COMPILED_EVENTS = b"ERes"

COMPILED_PROGRAM = b"ERev"

class EventPageProblem(Exception):
    """Raised when a page cannot be read as a page."""

class OutOfScope(Exception):
    """Raised for a page shape this does not claim to handle."""

def compiled_programs(block: bytes) -> list[bytes]:
    """The event programs a compiled frame carries."""
    if block[:4] != HEADER_TAG:
        raise EventPageProblem(f"event block starts {block[:4]!r}, not {HEADER_TAG!r}")
    (tail,) = struct.unpack_from("<H", block, HEADER_TAIL_COUNT)
    pos = HEADER_FIXED_SIZE + HEADER_TAIL_ENTRY * tail
    if block[pos:pos + 4] != COMPILED_EVENTS:
        raise EventPageProblem(
            f"expected {COMPILED_EVENTS!r} at 0x{pos:X} for tail count {tail}, "
            f"found {block[pos:pos + 4]!r}"
        )
    (total,) = struct.unpack_from("<I", block, pos + 4)
    pos += 8
    programs = []
    consumed = 0
    while consumed < total:
        if block[pos:pos + 4] != COMPILED_PROGRAM:
            raise EventPageProblem(
                f"expected {COMPILED_PROGRAM!r} at 0x{pos:X}, "
                f"found {block[pos:pos + 4]!r}"
            )
        (size,) = struct.unpack_from("<I", block, pos + 4)
        pos += 8
        programs.append(block[pos:pos + size])
        pos += size
        consumed += size
    if consumed != total:
        raise EventPageProblem(
            f"{COMPILED_PROGRAM!r} sizes total {consumed}, {COMPILED_EVENTS!r} "
            f"declares {total}"
        )
    return programs

def tile_events(program: bytes) -> list[bytes]:
    """Lay the events out across the page's columns."""
    records = []
    pos = 0
    while pos < len(program):
        (signed,) = struct.unpack_from("<h", program, pos)
        size = -signed
        if signed >= 0 or size < 0x0E or pos + size > len(program):
            raise EventPageProblem(
                f"event record size {signed} at 0x{pos:X} does not tile"
            )
        records.append(program[pos:pos + size])
        pos += size
    return records

def counted(text: bytes) -> bytes:
    """Prefix a payload with its own length, the way the format stores text."""
    return struct.pack("<I", len(text)) + text

def read_counted(data: bytes, pos: int) -> tuple[bytes, int]:
    """Read a length-prefixed payload, and say where the next one starts."""
    (length,) = struct.unpack_from("<I", data, pos)
    return data[pos + 4:pos + 4 + length], pos + 4 + length

def read_event_page(body: bytes) -> dict:
    """Read an editor event page back into its parts.

    A frame's event page is a run of blocks: the events themselves, the author's
    remarks, the list of objects the events talk about, the editor's own column
    layout, then a tail of settings and templates the rebuild copies through
    untouched. This walks it and hands each part back separately, along with where
    the copied-through tail begins.

    **It walks rather than searches, and that is the whole design.** Finding a
    block by looking for its tag proves nothing about where the block before it
    ended — a tag that turns up in the right place can just as easily mean the
    grammar is wrong and the bytes happened to line up. So every block's end is
    computed from its own declared length, each expected tag is checked at the
    position the walk arrives at, and anything that is not where it should be
    stops the read by name and offset. Both of the corrections this format has
    needed were cases where a search landed on the right answer for the wrong
    reason.

    Three blocks are optional and simply absent in some frames, which the walk
    allows for by testing rather than requiring. The object list is decoded
    properly rather than kept as bytes, because its entries come in two shapes —
    a single object, or a qualifier standing for a group of them — that store
    different fields and have to be told apart to be read at all.
    """
    pos = body.find(EVENT_PAGE)
    if pos < 0:
        raise EventPageProblem("frame body has no event page")
    page_start = pos
    header = body[pos + 4:pos + 8]
    if header[:2] != EVENT_PAGE_HEADER_PREFIX:
        raise EventPageProblem(
            f"event page header {header.hex(' ')}, expected "
            f"{EVENT_PAGE_HEADER_PREFIX.hex(' ')} and a second word"
        )
    pos += 8
    page: dict = {
        "start": page_start,
        "header": header,
        "events": None,
        "remarks": None,
        "registry": None,
        "objects": [],
        "editor": None,
        "instances": body[:page_start],
    }

    if body[pos:pos + 4] == EVENTS:
        (length,) = struct.unpack_from("<I", body, pos + 4)
        page["events"] = body[pos + 8:pos + 8 + length]
        pos += 8 + length

    if body[pos:pos + 4] == REMARKS:
        start = pos
        name, pos = read_counted(body, pos + 4)
        if name != REMARK_LIST_CLASS:
            raise EventPageProblem(f"remark list class is {name!r}")
        (count,) = struct.unpack_from("<I", body, pos)
        pos += 4
        for _ in range(count):
            if body[pos:pos + 4] != b"EvRk":
                raise EventPageProblem(f"expected 'EvRk' at 0x{pos:X}")
            pos += 8
            _text, pos = read_counted(body, pos)
        page["remarks"] = body[start:pos]

    if body[pos:pos + 4] == EVENT_OBJECT_LIST:
        start = pos
        name, pos = read_counted(body, pos + 4)
        if name != COI_LIST_CLASS:
            raise EventPageProblem(f"object list class is {name!r}")
        (count,) = struct.unpack_from("<I", body, pos)
        pos += 4
        for _ in range(count):
            if body[pos:pos + 4] != EVENT_OBJECT:
                raise EventPageProblem(f"expected {EVENT_OBJECT!r} at 0x{pos:X}")
            index, kind, object_type = struct.unpack_from("<IHH", body, pos + 4)
            pos += 12
            entry_name, pos = read_counted(body, pos)
            type_string, pos = read_counted(body, pos)
            if kind == QUALIFIER_ENTRY:
                _pad, qualifier = struct.unpack_from("<HH", body, pos)
                pos += 4
                object_id, link = QUALIFIER_FLAG | qualifier, None
            elif kind == OBJECT_ENTRY:
                _pad, object_id, link = struct.unpack_from("<HIi", body, pos)
                pos += 10
            else:
                raise EventPageProblem(f"{EVENT_OBJECT!r} kind {kind} is not 1 or 3")
            page["objects"].append(
                {
                    "index": index,
                    "kind": kind,
                    "object_type": object_type,
                    "name": entry_name,
                    "type_string": type_string,
                    "object_id": object_id,
                    "link": link,
                }
            )
        page["registry"] = body[start:pos]

    if body[pos:pos + 4] != EVENT_EDITOR:
        raise EventPageProblem(
            f"expected {EVENT_EDITOR!r} at 0x{pos:X}, found {body[pos:pos + 4]!r}"
        )
    start = pos
    (columns,) = struct.unpack_from("<H", body, pos + 4)
    pos += 6 + 6 * columns
    page["editor"] = body[start:pos]
    page["columns"] = columns

    page["tail_start"] = pos

    if body[pos:pos + 4] != EVENT_TEMPLATES:
        raise EventPageProblem(
            f"expected {EVENT_TEMPLATES!r} at 0x{pos:X}, found {body[pos:pos + 4]!r}"
        )
    (templates,) = struct.unpack_from("<H", body, pos + 4)
    pos += 6 + 6 * templates
    page["templates"] = templates

    if body[pos:pos + 4] != EVENT_SETTINGS:
        raise EventPageProblem(
            f"expected {EVENT_SETTINGS!r} at 0x{pos:X}, found {body[pos:pos + 4]!r}"
        )
    (length,) = struct.unpack_from("<I", body, pos + 4)
    page["settings"] = body[pos + 8:pos + 8 + length]
    pos += 8 + length

    if body[pos:pos + 4] != HANDLE_ALLOCATOR:
        raise EventPageProblem(
            f"expected {HANDLE_ALLOCATOR!r} at 0x{pos:X}, found {body[pos:pos + 4]!r}"
        )
    page["allocator_start"] = pos
    return page

def event_object_type_string(obj: dict) -> bytes:
    """The name the editor shows for an object type."""
    object_type = obj["object_type"]
    if object_type in EVENT_OBJECT_TYPE_STRINGS:
        return EVENT_OBJECT_TYPE_STRINGS[object_type]
    if object_type >= EXTENSION_OBJECT_TYPE_BASE:
        return obj["definition"][0x2C:0x30]
    raise OutOfScope(f"no COIList type string for runtime object type {object_type}")

def dense_item_ids(registry: dict) -> dict[int, int]:
    """Renumber object ids into the contiguous range a page expects."""
    return dict(registry["object_id_map"])

def build_registry(
    order: list[int],
    registry: dict,
    objects_by_id: dict[int, dict],
    event_item_ids: dict[int, int],
    frame_item_ids: dict[int, int] | None = None,
) -> bytes:
    """The object list a page needs in order to show its events."""
    if frame_item_ids is None:
        frame_item_ids = event_item_ids
    records = []
    for key in order:
        if key & QUALIFIER_FLAG and key not in objects_by_id:
            qualifier = key & ~QUALIFIER_FLAG
            records.append(
                EVENT_OBJECT
                + struct.pack("<IHH", event_item_ids[key], QUALIFIER_ENTRY,
                              QUALIFIER_TYPE)
                + counted(qualifier_display_name(qualifier))
                + counted(EVENT_OBJECT_TYPE_STRINGS[QUALIFIER_TYPE])
                + struct.pack("<HH", 0, qualifier)
            )
            continue
        obj = objects_by_id[key]
        link = registry["placeholder_instance_for"].get(key, 0xFFFFFFFF)
        records.append(
            EVENT_OBJECT
            + struct.pack("<IHH", event_item_ids[key], OBJECT_ENTRY,
                          obj["object_type"])
            + counted(obj["name"])
            + counted(event_object_type_string(obj))
            + struct.pack("<HII", 0, frame_item_ids[key], link)
        )
    if not records:
        return b""
    return (
        EVENT_OBJECT_LIST
        + counted(COI_LIST_CLASS)
        + struct.pack("<I", len(records))
        + b"".join(records)
    )
