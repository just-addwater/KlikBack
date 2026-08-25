# GENERATED — do not edit by hand. This file is produced by KlikBack's
# sync tooling; changes belong in the source it is generated from.
#
# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""The comment row a recovered MMF 2.0 project uses to label what the compiler
merged.

A frame's events, an object's behaviours and the application's global events
are three separate sheets in the editor, and a built game runs them as one
flat list with nothing recording which sheet each line came from.  The runtime
never needed to know, so the compiler did not write it down, and no reading of
the game can put it back.

What a recovery *can* do is say where the seams were.  Each merged sheet gets a
comment row in front of it, on yellow, in the recovered project's own words —
so the event editor shows one honest list with the joins marked, rather than a
silent concatenation that reads as if the author wrote it that way.

The same label, in the same words and the same colour, marks the same loss in
KlikBack's Multimedia Fusion 1.0 and 1.5 output.  Someone who has read one
does not have to learn the other.

A comment is stored as two things and a writer that emits one of them is not a
writer: a 152-byte event record carrying the font, the two colours and a
handle, and the text itself in the frame's parallel comment list under that
handle.
"""

from __future__ import annotations
import struct

COMMENT_ROW_SIZE = 152

COMMENT_MARKER = -9

COMMENT_FLAG = 0x0080

IN_GROUP_FLAG = 0x2000

GROUP_START_NUM = -10

GROUP_END_NUM = -11

COMMENT_KIND = 0x10

CONDITION_HEAD = 16

ACTION_HEAD = 14

BACKGROUND_RECOVERED = 0x0000FFFF

TEXT_COLOUR_DEFAULT = 0x00000000

def comment_row_template(
    rems_handle: int,
    background: int,
    row_number: int = 1,
    row_index: int = 0,
    inside_group: bool = False,
    kind: int = COMMENT_KIND,
    text_colour: int = TEXT_COLOUR_DEFAULT,
) -> bytes:
    """Build one comment row: its font, its two colours, and the handle its text is
    filed under.
    """
    flags = COMMENT_FLAG | (IN_GROUP_FLAG if inside_group else 0)
    head = struct.pack(
        "<hBBHHHHH",
        -COMMENT_ROW_SIZE, 1, 1, flags, kind, 0, row_number, row_index,
    )

    logfont = struct.pack("<5h", -13, 0, 0, 0, 400) + bytes(
        (0, 0, 0, 0, 3, 2, 1, 0x22)
    )
    body = (
        logfont
        + b"Arial\x00".ljust(32, b"\x00")
        + struct.pack("<II", text_colour, background)
        + struct.pack("<HH", rems_handle, rems_handle)
        + bytes(42)
    )
    parameter = struct.pack("<HH", 4 + len(body), 37) + body
    condition = (
        struct.pack("<HhhHHHBBH", CONDITION_HEAD + len(parameter), -1,
                    COMMENT_MARKER, 0, 0, 0, 1, 0, 0)
        + parameter
    )
    action = struct.pack("<HhhHHHBB", ACTION_HEAD, -1, 0, 0, 0, 0, 0, 0)

    row = head + condition + action
    if len(row) != COMMENT_ROW_SIZE:
        raise AssertionError(
            "comment row is %d bytes, not %d" % (len(row), COMMENT_ROW_SIZE)
        )
    return row

def group_depth_change(event: bytes) -> int:
    """Whether this event record opens a group, closes one, or neither.

    Labels have to be placed at the outer level.  A seam label dropped inside an
    open group would be indented under a condition that has nothing to do with it,
    and would move with that group if the author later collapsed or deleted it.
    """
    if len(event) < 20 or not event[2]:
        return 0
    objtype, num = struct.unpack_from("<2h", event, 16)
    if objtype != -1:
        return 0
    if num == GROUP_START_NUM:
        return 1
    if num == GROUP_END_NUM:
        return -1
    return 0

def rows_in(records: list[bytes]) -> int:
    """How many comment rows an event list already holds."""
    return sum(1 for r in records if group_depth_change(bytes(r)) != -1)

SECTION_LABEL = (
    "RECOVERED EVENT PROGRAM {index} - OWNER UNKNOWN - "
    "the {rows} row(s) below this line are a separate compiled program that "
    "ran in this frame, in this order, and still do; the EXE does not record "
    "whether they were a global event sheet or an object's behaviour"
)

def rems_block(texts: list[bytes]) -> bytes:
    """The frame's parallel list of comment texts, keyed by handle."""
    out = struct.pack("<I", len(texts))
    for handle, text in enumerate(texts):
        out += struct.pack("<II", handle, len(text)) + text
    return out

def label_sections(
    sections: list[list[bytes]], first_index: int = 1
) -> tuple[list[bytes], list[bytes]]:
    """Join a frame's compiled event sheets into one list, with a labelled seam
    between each.

    Returns the joined records and the texts to file alongside them.  The first
    sheet is the frame's own and is not labelled — there is no seam before it.
    """
    combined: list[bytes] = []
    texts: list[bytes] = []
    depth = 0
    for offset, section in enumerate(sections):
        if offset:
            if depth != 0:
                raise ValueError(
                    "the seam before section %d sits at event-group depth %d, "
                    "not 0; a section that does not close its own groups "
                    "cannot be labelled without guessing whether the label "
                    "belongs inside them" % (offset, depth)
                )
            combined.append(
                comment_row_template(
                    rems_handle=len(texts),
                    background=BACKGROUND_RECOVERED,
                    row_number=len(combined) + 1,
                    row_index=len(combined),
                )
            )
            texts.append(
                SECTION_LABEL.format(
                    index=first_index + offset - 1, rows=rows_in(section)
                ).encode("ascii")
            )
        for record in section:
            depth += group_depth_change(bytes(record))
            combined.append(record)
    return combined, texts
