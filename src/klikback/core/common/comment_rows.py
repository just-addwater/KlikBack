# GENERATED — do not edit by hand. This file is produced by KlikBack's
# sync tooling; changes belong in the source it is generated from.
#
# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""The comment rows in a frame's event sheet, and the text they point at.

A comment in the event editor is stored as **two** things: a row in the event
sheet carrying the font, the colour and an id, and the text itself in a
parallel list keyed by that id. A writer that emits one of them is not a
writer — the row without its text is a blank line, and text without a row is
invisible.

**What compilation keeps, and what it does not.** The rows survive: their
positions, their formatting and their ids are all in the compiled game. The
*text* is not — it is authoring information the runtime never needs, so the
compiler drops it. That asymmetry is why comment recovery is an option
rather than a default: putting the rows back means writing text nobody wrote,
and text the author did not write should never appear in their project
unasked.

So the rows are honest by construction — a recovered comment says what it is,
and the option that produces them is off unless it is turned on.
"""

from __future__ import annotations
import struct

COMMENT_ROW_SIZE = 146

COMMENT_MARKER = 0xF7FF

COMMENT_FLAG = 0x0080

IN_GROUP_FLAG = 0x2000

FLAGS_OFFSET = 0x04

ROW_NUMBER_OFFSET = 0x0A

MARKER_OFFSET = 0x10

COMMENT_ID_OFFSET = 0x5C

GROUP_OPEN_MARKER = b"\xFF\xF6"

GROUP_CLOSE_MARKER = b"\xFF\xF5"

def comment_row_template(
    row_number: int, row_index: int, comment_id: int, background: int
) -> bytes:
    """The neutral row every comment is built from, emitted from named fields.
    """
    logfont = struct.pack("<5h", -13, 0, 0, 0, 400) + bytes(
        (0, 0, 0, 0, 3, 2, 1, 0x22)
    )
    parameter = (
        struct.pack("<HH", 106, 37)
        + logfont
        + b"Arial\x00".ljust(32, b"\x00")
        + struct.pack("<II", 0x000000, background)
        + struct.pack("<HH", 0, comment_id)
        + bytes(40)
    )
    condition = (
        struct.pack("<HH", 120, COMMENT_MARKER)
        + bytes(6)
        + struct.pack("<I", 1)
        + parameter
    )
    action = struct.pack("<HBB", 12, 0xFF, 0) + bytes(8)
    header = struct.pack(
        "<hBBHHHHH",
        -COMMENT_ROW_SIZE, 1, 1, COMMENT_FLAG, 16, 0, row_number, row_index,
    )
    row = header + condition + action
    if len(row) != COMMENT_ROW_SIZE:
        raise ValueError(f"comment row template is {len(row)} bytes, not 146")
    return row

COMMENT_ROW = comment_row_template(
    row_number=4, row_index=3, comment_id=2, background=0x0000FFFF
)

REMARK_LIST_TAG = b"Rems"

REMARK_LIST_CLASS = b"class CEvtRemarkList"

REMARK_TAG = b"EvRk"

def comment_row(comment_id: int, inside_group: bool = False) -> bytes:
    """Build one comment row, with its formatting and its id."""
    if not 0 <= comment_id <= 0xFFFF:
        raise ValueError(f"comment id {comment_id} does not fit a u16")
    row = bytearray(COMMENT_ROW)
    flags = COMMENT_FLAG | (IN_GROUP_FLAG if inside_group else 0)
    struct.pack_into("<H", row, FLAGS_OFFSET, flags)
    struct.pack_into("<H", row, COMMENT_ID_OFFSET, comment_id)
    return bytes(row)

def is_comment_row(event: bytes) -> bool:
    """Whether an event row is a comment rather than a real event."""
    return (
        len(event) >= MARKER_OFFSET + 2
        and struct.unpack_from("<H", event, MARKER_OFFSET)[0] == COMMENT_MARKER
    )

def comment_id(event: bytes) -> int:
    """The id binding a row to its text."""
    if not is_comment_row(event):
        raise ValueError("this row is not a comment row; +0x5C is not an id")
    return struct.unpack_from("<H", event, COMMENT_ID_OFFSET)[0]

def row_number(event: bytes) -> int:
    """Where a row sits in the sheet."""
    return struct.unpack_from("<H", event, ROW_NUMBER_OFFSET)[0]

MAXIMUM_STRIPPED_ROWS = 20000

def stripped_row_numbers(program: list[bytes]) -> list[int]:
    """The positions the compiler kept for comments whose text it discarded.

    Every compiled event still carries the row number the author's editor gave it,
    and compiling does not renumber the rows that survive. So the numbers missing
    from the sequence are exactly the rows that were dropped. That is how the
    *positions* of deleted comment rows are known when their text is gone
    completely.

    It must be asked of **one program**, never of a frame's combined sheet.
    Numbering restarts at 1 for each program, so a combined sheet reads as a page
    that jumps backwards at every join, and every join turns into a gap that was
    never there.

    The leading block is the part worth not missing. Rows are numbered from one, so
    a program whose lowest surviving row is 12 proves rows 1 to 11 existed and were
    removed, exactly as a hole at 19 proves row 19 was. Reading only the holes in
    the middle silently loses a large share of what is recoverable.

    Two things raise rather than being worked around: a sequence that does not
    strictly ascend, and a count of implied missing rows far beyond anything a real
    page holds. Both mean the row number is being read out of phase — an absurd
    derived value is evidence about the reader, not about the file.
    """
    numbers = [row_number(event) for event in program]
    if not numbers:
        return []
    for earlier, later in zip(numbers, numbers[1:]):
        if later <= earlier:
            raise ValueError(
                f"compiled row numbers are not strictly ascending "
                f"({earlier} then {later}); +0x0A is being read out of phase, "
                "so which rows were stripped cannot be derived"
            )
    if numbers[0] < 1:
        raise ValueError(f"compiled row number {numbers[0]} is below the 1-based floor")
    missing = sorted(set(range(1, numbers[-1] + 1)) - set(numbers))
    if len(missing) > MAXIMUM_STRIPPED_ROWS:
        raise ValueError(
            f"this program's row numbers imply {len(missing)} stripped rows, "
            f"above the guard of {MAXIMUM_STRIPPED_ROWS}; the largest ever "
            "measured is 111, so this is a misread rather than a page"
        )
    return missing

RECOVERED_COMMENT_TEXT = (
    "RECOVERED COMMENT {index} - TEXT LOST AT COMPILE TIME - the author "
    "wrote a comment on this row; compilation kept its position and "
    "discarded its words"
)

def restore_stripped_comments(
    program: list[bytes],
    first_id: int = 0,
    first_index: int = 1,
    row_factory=None,
) -> tuple[list[bytes], list[bytes]]:
    """Put the comment rows back where the compiled game says they were.

    What the opt-in comment recovery actually does. The rows survive compilation as
    numbered gaps; the words do not survive at all. So every restored row carries
    stand-in text, and that is the whole reason the option is off by default —
    turning it on adds writing to the project that the author never wrote.

    **The position is the recovered fact, not the number.** Nothing here writes a
    row number: the converter renumbers every row it emits, and the editor
    regenerates the field on every save regardless. The row is placed at the right
    index and the numbering follows from that.

    The group flag is computed rather than carried over. A comment written *inside*
    an event group records that it is, so the group depth is tracked across the rows
    already placed and the flag set from it. Getting this wrong corrupts nothing —
    it moves the comment out of the group it was written in, which is precisely the
    part of the position being claimed as recovered.

    A program that ends at an unbalanced group depth raises instead: a comment's
    group membership cannot be derived from a page that does not close what it
    opens.
    """
    build_row = comment_row if row_factory is None else row_factory
    missing = stripped_row_numbers(program)
    if not missing:
        return list(program), []

    by_number = {row_number(event): event for event in program}
    wanted = set(missing)
    combined: list[bytes] = []
    texts: list[bytes] = []
    depth = 0
    for number in range(1, max(by_number) + 1):
        if number in wanted:
            combined.append(
                build_row(first_id + len(texts), inside_group=depth > 0)
            )
            texts.append(
                RECOVERED_COMMENT_TEXT.format(
                    index=first_index + len(texts)
                ).encode("ascii")
            )
            continue
        event = by_number[number]
        combined.append(event)
        depth += group_depth_change(event)
    if depth != 0:
        raise ValueError(
            f"this program ends at event-group depth {depth}; a comment's "
            "group membership cannot be derived from an unbalanced page"
        )
    return combined, texts

def group_depth_change(event: bytes) -> int:
    """How a row changes the nesting of event groups around it."""
    marker = event[MARKER_OFFSET : MARKER_OFFSET + 2]
    if marker == GROUP_OPEN_MARKER:
        return 1
    if marker == GROUP_CLOSE_MARKER:
        return -1
    return 0

def remarks_block(texts: list[bytes]) -> bytes:
    """The parallel list holding the comment text."""
    if not texts:
        return b""
    records = b"".join(
        REMARK_TAG + struct.pack("<II", index, len(text)) + text
        for index, text in enumerate(texts)
    )
    return (
        REMARK_LIST_TAG
        + struct.pack("<I", len(REMARK_LIST_CLASS))
        + REMARK_LIST_CLASS
        + struct.pack("<I", len(texts))
        + records
    )

FLATTENED_PROGRAM_LABEL = (
    "RECOVERED EVENT PROGRAM {index} - OWNER UNKNOWN - "
    "the {rows} row(s) below this line are a separate compiled program that "
    "ran in this frame, in this order, and still do; the EXE does not record "
    "whether they were a global event sheet or an object's behaviour"
)

def label_flattened_programs(
    programs: list[list[bytes]],
    first_index: int = 1,
    recover_comments: bool = False,
    first_comment_index: int = 1,
) -> tuple[list[bytes], list[bytes]]:
    """Mark programs the compiler merged, so the editor shows what happened.

    A frame's own event sheet, the global sheet and each object's behaviours all
    compile into the same frame. Putting them back means running them together into
    one sheet, and a comment row is written at each join to say that a separate
    recovered program starts here.

    Each label states **how many rows that program contributes**, which is not
    decoration. A join can land anywhere in a page, so "the rows below this" has no
    stated end otherwise — a reader would have to count down to the next join, and
    the last program has no next join at all. The count includes any recovered
    comment rows, because those are rows that appear in the editor and a reader
    counting down the page will count them.

    **The first program is not labelled, and that is a limit rather than a claim.**
    The programs come in a fixed order, but an empty sheet emits no program at all,
    so in a frame whose own sheet is empty the first program already belongs to
    something else. Every join marks a real boundary; what a join cannot say is
    which side of the first one the frame's own rows are on. Labelling the first
    program too would assert the opposite guess with exactly the same confidence.

    Comment recovery, when it is on, runs **per program** and before the label is
    written. Per program because row numbering restarts with each one. Before,
    because the label counts the rows and a recovered comment is one of them. The
    two features share a single id space allocated in append order — a comment row
    whose id names no stored text is exactly the dangling reference worth never
    creating.

    The join is *checked* to sit outside any group rather than assumed to. A label
    written inside the previous program's last group reads as a comment about those
    rows instead of about the ones below it.
    """
    combined: list[bytes] = []
    texts: list[bytes] = []
    seams = 0
    recovered = 0
    for offset, program in enumerate(programs):
        seam = bool(offset)
        if seam:
            depth = sum(group_depth_change(event) for event in combined)
            if depth != 0:
                raise ValueError(
                    f"the seam before program {offset} sits at event-group "
                    f"depth {depth}, not 0; a program that does not close its "
                    "own groups cannot be labelled without guessing whether "
                    "the label belongs inside them"
                )

        restored: list[bytes] = []
        if recover_comments:
            program, restored = restore_stripped_comments(
                program,
                first_id=len(texts) + (1 if seam else 0),
                first_index=first_comment_index + recovered,
            )
            recovered += len(restored)
        if seam:
            combined.append(comment_row(len(texts)))
            texts.append(
                FLATTENED_PROGRAM_LABEL.format(
                    index=first_index + seams, rows=len(program)
                ).encode("ascii")
            )
            seams += 1
        texts.extend(restored)
        combined.extend(program)
    return combined, texts
