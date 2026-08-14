# GENERATED — do not edit by hand. This file is produced by KlikBack's
# sync tooling; changes belong in the source it is generated from.
#
# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""Rebuild the event editor's column set for a 1996 level.

Protection deletes this block outright on the later 1996 builds, and an empty
stand-in is not free: the event editor will not open on one, and an editor
made to save anyway discards the event groups it cannot place — thousands of
rows on a large game. Rebuilding the block with the right columns fixes both.

The columns are derivable because they are a *view* of things that survived:
which objects a level's events actually reference, which qualifiers they use,
and where the comment rows sit. Nothing here invents an author's layout; it
reconstructs the set of columns the events require in order to be shown.

This runs behind an option that is **off by default**, in keeping with the
rule that anything adding content the author did not write is opt-in.
"""

from __future__ import annotations
import struct
import klikback.core.tgf.format as tgf

SYSTEM_IDS = (-1, -2, -3, -5, -6, -7)

GLOBAL_REFERENCE = 0x8000

EVENT_GROUP_HEAD = 14

RECORD_OBJECT_REFERENCE = 4

def referenced_objects(events_block1: bytes) -> list[int]:
    """Every object a level's events actually mention."""
    seen: list[int] = []
    for offset, size in tgf.event_groups(events_block1):
        conditions, actions = events_block1[offset + 2], events_block1[offset + 3]
        cursor = offset + EVENT_GROUP_HEAD
        for _ in range(conditions + actions):
            if cursor + 2 > offset + size:
                break
            (length,) = struct.unpack_from("<H", events_block1, cursor)
            if length < 4 or cursor + length > offset + size:
                break
            if length > RECORD_OBJECT_REFERENCE + 2:
                (reference,) = struct.unpack_from(
                    "<h", events_block1, cursor + RECORD_OBJECT_REFERENCE)
                if reference not in seen:
                    seen.append(reference)
            cursor += length
    return seen

def comment_slots(events_block1: bytes) -> list[int]:
    """Where the comment rows sit among the events."""
    slots: list[int] = []
    for offset, size in tgf.event_groups(events_block1):
        conditions, actions = events_block1[offset + 2], events_block1[offset + 3]
        cursor = offset + EVENT_GROUP_HEAD
        for _ in range(conditions + actions):
            if cursor + 4 > offset + size:
                break
            (length,) = struct.unpack_from("<H", events_block1, cursor)
            if length < 4 or cursor + length > offset + size:
                break
            kind, code = struct.unpack_from("<bb", events_block1, cursor + 2)
            if (kind == COMMENT_CONDITION_TYPE and code == COMMENT_CONDITION_CODE
                    and length >= COMMENT_INDEX_AT + 2):
                (number,) = struct.unpack_from("<H", events_block1,
                                               cursor + COMMENT_INDEX_AT)
                if number and number - 1 not in slots:
                    slots.append(number - 1)
            cursor += length
    return sorted(slots)

def comment_row_offsets(events_block1: bytes) -> list[tuple[int, int]]:
    """The positions of comment rows within the event program."""
    out: list[tuple[int, int]] = []
    for offset, size in tgf.event_groups(events_block1):
        conditions, actions = events_block1[offset + 2], events_block1[offset + 3]
        cursor = offset + EVENT_GROUP_HEAD
        for _ in range(conditions + actions):
            if cursor + 4 > offset + size:
                break
            (length,) = struct.unpack_from("<H", events_block1, cursor)
            if length < 4 or cursor + length > offset + size:
                break
            kind, code = struct.unpack_from("<bb", events_block1, cursor + 2)
            if (kind == COMMENT_CONDITION_TYPE and code == COMMENT_CONDITION_CODE
                    and length >= COMMENT_INDEX_AT + 2):
                (number,) = struct.unpack_from("<H", events_block1,
                                               cursor + COMMENT_INDEX_AT)
                if number:
                    out.append((offset, size))
                    break
            cursor += length
    return out

def without_comment_rows(events_block1: bytes) -> tuple[bytes, int]:
    """The same events with the comment rows removed."""
    remove = {offset for offset, _size in comment_row_offsets(events_block1)}
    if not remove:
        return events_block1, 0
    kept = bytearray()
    for offset, size in tgf.event_groups(events_block1):
        if offset not in remove:
            kept += events_block1[offset:offset + size]
    kept += b"\0\0"
    return bytes(kept), len(remove)

GLOBAL_COLUMN_ID = 2

SHORTCUT_REFERENCE = 0x4000

SHORTCUT_REFERENCE_AT = (0x04, 0x10)

def shortcut_references(events_block1: bytes) -> dict[int, tuple[int, int]]:
    """The references the editor keeps as shortcuts."""
    found: dict[int, list[int]] = {}
    for offset, size in tgf.event_groups(events_block1):
        conditions, actions = events_block1[offset + 2], events_block1[offset + 3]
        cursor = offset + EVENT_GROUP_HEAD
        for _ in range(conditions + actions):
            if cursor + 4 > offset + size:
                break
            (length,) = struct.unpack_from("<H", events_block1, cursor)
            if length < 4 or cursor + length > offset + size:
                break
            (kind,) = struct.unpack_from("<b", events_block1, cursor + 2)

            if kind <= 0:
                cursor += length
                continue
            for at in SHORTCUT_REFERENCE_AT:
                if at + 2 > length:
                    continue
                (value,) = struct.unpack_from("<H", events_block1, cursor + at)
                if SHORTCUT_REFERENCE < value < SHORTCUT_REFERENCE + 0x100:
                    row = found.setdefault(value, [kind, 0])
                    row[1] += 1
            cursor += length
    return {ref: (kind, uses) for ref, (kind, uses) in found.items()}

def global_references(events_block1: bytes) -> list[int]:
    """The references that reach outside the level."""
    return [ref for ref in referenced_objects(events_block1) if ref < 0
            and (ref & GLOBAL_REFERENCE)]

UNCOLUMNED_TYPES = frozenset({0x00, 0x01, 0x05, 0x06, 0xFF})

def columns_from_objects(objects: list[tgf.ObjectDefinition],
                         events_block1: bytes) -> list[tuple[int, int]]:
    """The columns implied by the objects a level uses."""

    columned = [obj for obj in objects
                if obj.object_type not in UNCOLUMNED_TYPES]
    type_order: list[int] = []
    for obj in columned:
        if obj.object_type not in type_order:
            type_order.append(obj.object_type)
    body: list[tuple[int, int]] = []
    for object_type in type_order:
        body += [(object_type, obj.index) for obj in columned
                 if obj.object_type == object_type]
    body += [(GLOBAL_COLUMN_ID, reference)
             for reference in global_references(events_block1)]

    body += [(kind, reference) for reference, (kind, _uses)
             in shortcut_references(events_block1).items()]
    if not body and not referenced_objects(events_block1):
        return []
    return [(ident, 0) for ident in SYSTEM_IDS] + body

def columns_from_events(objects: list[tgf.ObjectDefinition],
                        events_block1: bytes) -> list[tuple[int, int]]:
    """The columns implied by the events themselves."""
    by_index = {obj.index: obj for obj in objects}
    shortcuts = shortcut_references(events_block1)
    columns = [(ident, 0) for ident in SYSTEM_IDS]
    for reference in referenced_objects(events_block1):
        if reference < 0 and (reference & GLOBAL_REFERENCE):
            columns.append((GLOBAL_COLUMN_ID, reference))
        elif reference in shortcuts:
            columns.append((shortcuts[reference][0], reference))
            continue
        obj = by_index.get(reference)
        if obj is None or obj.type_name == "deleted":
            continue
        columns.append((obj.object_type, reference))

    have = {reference for _ident, reference in columns}
    columns += [(kind, reference) for reference, (kind, _uses)
                in shortcuts.items() if reference not in have]
    return columns

SECOND_LIST_HEAD = ((0, -2), (0, -5), (0, -3))

SECOND_LIST_TYPE = 2

def second_list(objects: list[tgf.ObjectDefinition]) -> list[tuple[int, int]]:
    """The object list the block carries alongside its columns."""
    entries = list(SECOND_LIST_HEAD)
    for obj in objects:
        if obj.object_type == SECOND_LIST_TYPE:
            entries.append((obj.index, obj.object_type))
    return entries

COMMENT_CONDITION_TYPE = -1

COMMENT_CONDITION_CODE = -9

COMMENT_INDEX_AT = 0x4E

SECTION_HEADER = 8

SECTION_SLOTS = 512

SECTION_DATA = SECTION_HEADER + 2 * SECTION_SLOTS

class Section:
    """One section of the block."""

    __slots__ = ("base", "end", "high_water", "used", "offsets", "raw")

    def __init__(self, base: int, end: int, high_water: int, used: int,
                 offsets: list[int], raw: bytes) -> None:
        self.base, self.end = base, end
        self.high_water, self.used = high_water, used
        self.offsets, self.raw = offsets, raw

    @property
    def slots(self) -> list[int]:
        """Which of the section's slots hold something."""
        return [index for index, value in enumerate(self.offsets) if value]

    def text(self, slot: int) -> bytes | None:
        """The text in one slot, or nothing if the slot is empty."""
        if slot >= len(self.offsets) or not self.offsets[slot]:
            return None
        start = self.offsets[slot]
        stop = self.raw.find(b"\0", start)
        return self.raw[start:stop if stop >= 0 else self.end]

def read_section(raw: bytes, base: int) -> Section:
    """Read one section from an existing block."""
    if base + SECTION_HEADER > len(raw):
        raise ValueError(f"section header at {base} runs past a {len(raw)}-byte block")
    end, reserved, high_water, used = struct.unpack_from("<HHHH", raw, base)
    if reserved:
        raise ValueError(f"section reserved word is {reserved}, not 0")
    if high_water > SECTION_SLOTS:
        raise ValueError(f"high-water {high_water} exceeds {SECTION_SLOTS} slots")
    if end < SECTION_DATA or base + end > len(raw):
        raise ValueError(f"section length {end} at {base} in a {len(raw)}-byte block")
    offsets = [struct.unpack_from("<H", raw, base + SECTION_HEADER + 2 * i)[0]
               for i in range(high_water)]
    filled = [value for value in offsets if value]
    if len(filled) != used:
        raise ValueError(f"section declares {used} slots in use, {len(filled)} are")
    if filled and (min(filled) < SECTION_DATA or max(filled) >= end):
        raise ValueError("a section offset falls outside its own data")
    return Section(base, end, high_water, used, offsets, raw[base:base + end])

def comment_section(slots: list[int], text: bytes = b"") -> bytes:
    """The section holding comment rows, built for the slots a level uses.

    The slot numbers are what the events already point at, so they are preserved
    exactly; only the text is ours, and by default it is a single space. Writing
    recovered comment *text* is a separate, opt-in choice — the rows survived
    compilation and the words did not.
    """
    if not slots:
        raise ValueError("a comment section with no slots is not a shape to write")
    if min(slots) < 0 or max(slots) >= SECTION_SLOTS:
        raise ValueError(f"comment slot outside 0..{SECTION_SLOTS - 1}: "
                         f"{min(slots)}..{max(slots)}")
    if b"\0" in text:
        raise ValueError("a comment's text cannot contain a NUL")
    stride = len(text) + 1
    stride += stride % 2
    table = [0] * SECTION_SLOTS
    for position, slot in enumerate(sorted(slots)):
        table[slot] = SECTION_DATA + stride * position
    end = SECTION_DATA + stride * len(slots)
    out = bytearray(struct.pack("<HHHH", end, 0, max(slots) + 1, len(slots)))
    for value in table:
        out += struct.pack("<H", value)
    record = text + b"\0" * (stride - len(text))
    out += record * len(slots)
    assert len(out) == end, (len(out), end)
    return bytes(out)

SHORTCUT_RECORD = 104

SHORTCUT_MIDDLE = b":fs64-@:"

SHORTCUT_TYPE_NAMES = {2: b"Sprite", 3: b"Text", 7: b"Counter"}

def shortcut_name(object_type: int, display: bytes = b"") -> bytes:
    """The name a shortcut entry carries."""
    if b"\0" in display:
        raise ValueError("a shortcut's display name cannot contain a NUL")
    return display + SHORTCUT_MIDDLE + SHORTCUT_TYPE_NAMES.get(
        object_type, b"")

def shortcut_record(object_type: int, uses: int = 0, home_index: int = 0,
                    display: bytes = b"") -> bytes:
    """One shortcut entry."""
    out = bytearray(struct.pack("<HHHHI", 0xFFFF, home_index, uses,
                                object_type, 0))
    out += shortcut_name(object_type, display) + b"\0"
    if len(out) > SHORTCUT_RECORD:
        raise ValueError(f"a shortcut name of {len(display)} bytes does not fit "
                         f"in a {SHORTCUT_RECORD}-byte record")
    return bytes(out) + b"\0" * (SHORTCUT_RECORD - len(out))

def shortcut_slot(reference: int) -> int:
    """Where in the section a given event reference expects to find its entry.
    """
    return reference - SHORTCUT_REFERENCE - 1

def shortcut_section(records: dict[int, bytes]) -> bytes:
    """The section holding the shortcut entries."""
    if not records:
        raise ValueError("a second section with no records is not a shape to write")
    if min(records) < 0 or max(records) >= SECTION_SLOTS:
        raise ValueError(f"shortcut slot outside 0..{SECTION_SLOTS - 1}: "
                         f"{min(records)}..{max(records)}")
    table = [0] * SECTION_SLOTS
    body = bytearray()
    for position, slot in enumerate(sorted(records)):
        record = records[slot]
        if len(record) != SHORTCUT_RECORD:
            raise ValueError(f"shortcut record for slot {slot} is "
                             f"{len(record)} bytes, not {SHORTCUT_RECORD}")
        table[slot] = SECTION_DATA + SHORTCUT_RECORD * position
        body += record
    end = SECTION_DATA + SHORTCUT_RECORD * len(records)
    out = bytearray(struct.pack("<HHHH", end, 0, max(records) + 1, len(records)))
    for value in table:
        out += struct.pack("<H", value)
    out += body
    assert len(out) == end, (len(out), end)
    return bytes(out)

def shortcut_section_for(events_block1: bytes) -> bytes | None:
    """The shortcut section a level's events need, or nothing if they need none.
    """
    shortcuts = shortcut_references(events_block1)
    if not shortcuts:
        return None
    records = {shortcut_slot(reference): shortcut_record(kind, uses)
               for reference, (kind, uses) in shortcuts.items()}
    return shortcut_section(records)

def build(columns: list[tuple[int, int]],
          second: list[tuple[int, int]] | None = None,
          comments: list[int] | None = None,
          third: list[int] | None = None,
          extra: bytes | None = None,
          comment_text: bytes = b"") -> bytes:
    """Assemble the block from its sections."""
    second = second if second is not None else []
    count, second_count = len(columns), len(second)
    if third is not None and len(third) != count:
        raise ValueError(f"third array has {len(third)} words for {count} columns")
    out = bytearray(struct.pack("<H", count))
    for ident, _reference in columns:
        out += struct.pack("<h", ident)
    for _ident, reference in columns:
        out += struct.pack("<h", reference)
    if third is None:
        out += b"\0" * (2 * count)
    else:
        for value in third:
            out += struct.pack("<h", value)
    out += struct.pack("<H", 0)
    if comments:
        out += struct.pack("<H", 1) + comment_section(comments, comment_text)
    else:
        out += struct.pack("<H", 0)
    if extra:
        out += struct.pack("<H", 1) + extra
    else:
        out += struct.pack("<H", 0)
    out += struct.pack("<H", second_count)
    for reference, _ident in second:
        out += struct.pack("<h", reference)
    for _reference, ident in second:
        out += struct.pack("<h", ident)
    if not comments and not extra:
        assert len(out) == 6 * count + 10 + 4 * second_count, (
            len(out), count, second_count)
    return bytes(out)

def third_array(raw: bytes) -> list[int]:
    """Read the block's third word array, one entry per column."""
    (count,) = struct.unpack_from("<H", raw, 0)
    base = 2 + 4 * count
    return [struct.unpack_from("<h", raw, base + 2 * i)[0] for i in range(count)]

class Block3:
    """The rebuilt block: its sections and how to write them out."""

    __slots__ = ("columns", "third", "comments", "extra", "second", "length")

    def __init__(self, columns, third, comments, extra, second, length):
        """Hold the sections a block was read as, and how long it ran."""
        self.columns = columns
        self.third = third
        self.comments: Section | None = comments
        self.extra: Section | None = extra
        self.second = second
        self.length = length

def walk(raw: bytes) -> Block3:
    """Step through an existing block's sections."""
    (count,) = struct.unpack_from("<H", raw, 0)
    if 2 + 6 * count + 8 > len(raw):
        raise ValueError(f"{count} columns do not fit in {len(raw)} bytes")
    ids = [struct.unpack_from("<h", raw, 2 + 2 * i)[0] for i in range(count)]
    refs = [struct.unpack_from("<h", raw, 2 + 2 * count + 2 * i)[0]
            for i in range(count)]
    cursor = 2 + 6 * count
    (leading,) = struct.unpack_from("<H", raw, cursor)
    if leading:
        raise ValueError(f"the word after the column list is {leading}, not 0")
    cursor += 2

    sections: list[Section | None] = []
    for which in ("comment", "second"):
        (flag,) = struct.unpack_from("<H", raw, cursor)
        cursor += 2
        if flag == 0:
            sections.append(None)
            continue
        if flag != 1:
            raise ValueError(f"the {which} section's flag is {flag}, not 0 or 1")
        section = read_section(raw, cursor)
        sections.append(section)
        cursor += section.end

    (second_count,) = struct.unpack_from("<H", raw, cursor)
    base = cursor + 2
    if base + 4 * second_count > len(raw):
        raise ValueError(f"an M list of {second_count} overruns the block")
    second = [(struct.unpack_from("<h", raw, base + 2 * i)[0],
               struct.unpack_from("<h", raw, base + 2 * second_count + 2 * i)[0])
              for i in range(second_count)]
    return Block3(list(zip(ids, refs)), third_array(raw), sections[0],
                  sections[1], second, base + 4 * second_count)

def default_third_array(count: int) -> list[int]:
    """All zero — which is the event sheet unfiltered, with nothing hidden.

    This array is the event editor's filter, and a mark in it means "show only
    column n". A rebuilt block writes no mark, so the sheet opens on all the
    events and draws every row the level has, comments included. Marking a column
    would make the editor open too, by putting it in a view where most of the
    level is simply not drawn — which is a worse answer than it looks.
    """
    return [0] * count

COMMENT_PLACEHOLDER = b" "

def for_level(level: bytes, source: str = "objects",
              comment_text: bytes = b"",
              drop_comment_rows: bool = False) -> bytes | None:
    """Build the column set one level's events need."""
    _start, blocks = tgf.level_blocks(level)
    by_ident = {block.ident: block.data for block in blocks}
    if 0x04 not in by_ident or 0x02 not in by_ident:
        return None
    objects = tgf.object_definitions(by_ident[0x02])

    events = by_ident[0x04]
    header = tgf.event_header(events)
    body = events[6:] if header else events
    (length1,) = struct.unpack_from("<I", body, 0)
    block1 = body[4:4 + length1]

    if source == "events":
        columns = columns_from_events(objects, block1)
    else:
        columns = columns_from_objects(objects, block1)

    extra = shortcut_section_for(block1)
    if drop_comment_rows:
        block1, _dropped = without_comment_rows(block1)
    return build(columns, second_list(objects), comments=comment_slots(block1),
                 third=default_third_array(len(columns)),
                 extra=extra, comment_text=comment_text)
