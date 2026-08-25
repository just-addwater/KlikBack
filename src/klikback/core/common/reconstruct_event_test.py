# GENERATED — do not edit by hand. This file is produced by KlikBack's
# sync tooling; changes belong in the source it is generated from.
#
# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""Turn a compiled game's events back into the events an editor shows.

A compiled event and an editor event are not the same thing. The runtime form
is packed for execution: object references are positions, parameters are
sized to what the runtime needs, and the grouping the author saw is implied
rather than stored. This converts one into the other, event by event.

**Group nesting is where honesty matters.** A compiler can leave groups open
at the end of a program, and the compiled bytes do not say whether what
follows was meant to be nested inside them or to sit alongside. Each close is
placed before the next group -- making the remainder a sibling -- and the
choice is reported as a loss naming the rows involved, because it is a guess
and the author is the one who can check it.
"""

from __future__ import annotations
import struct
from klikback.core.common.comment_rows import label_flattened_programs

EXPRESSION_PARAMETER_TYPES = {15, 22, 23, 45, 52, 53}

OBJECT_POSITION_PARAMETER_SIZES = {9: 0x22, 16: 0x1A, 18: 0x24, 21: 0x22}

TARGET_PARAMETER_TYPES = {9, 18}

ABSOLUTE_OBJECT_SENTINELS = {0xFFFE, 0xFFFF}

def remap_object_position_parameter(
    output: bytearray,
    parameter_pos: int,
    parameter_size: int,
    parameter_type: int,
    object_id_map: dict[int, int] | None,
) -> None:
    """Point a position parameter at the rebuilt object it refers to."""
    if parameter_size < OBJECT_POSITION_PARAMETER_SIZES[parameter_type]:
        raise ValueError(
            f"truncated compiled type-{parameter_type} parameter"
        )
    output[parameter_pos + 0x14 : parameter_pos + 0x16] = b"\x00\x00"
    if object_id_map is None:
        return
    reference = struct.unpack_from("<H", output, parameter_pos + 4)[0]
    if reference not in ABSOLUTE_OBJECT_SENTINELS and reference in object_id_map:
        struct.pack_into(
            "<H", output, parameter_pos + 4, object_id_map[reference]
        )
    if parameter_type in TARGET_PARAMETER_TYPES:
        target = struct.unpack_from("<H", output, parameter_pos + 0x1C)[0]
        if target in object_id_map:
            struct.pack_into(
                "<H", output, parameter_pos + 0x1C, object_id_map[target]
            )

def remap_expression_object_ids(
    output: bytearray,
    parameter_pos: int,
    parameter_end: int,
    object_id_map: dict[int, int],
) -> None:
    """Point an expression's object references at the rebuilt objects."""
    if parameter_end - parameter_pos < 8:
        raise ValueError("truncated compiled expression parameter")
    token_pos = parameter_pos + 6
    while token_pos < parameter_end:
        if token_pos + 2 > parameter_end:
            raise ValueError("truncated compiled expression token")
        token_code = struct.unpack_from("<H", output, token_pos)[0]
        if token_code == 0:

            return
        if token_pos + 4 > parameter_end:
            raise ValueError("truncated compiled expression token header")
        token_size = struct.unpack_from("<H", output, token_pos + 2)[0]
        token_end = token_pos + token_size
        if token_size < 4 or token_end > parameter_end:
            raise ValueError("invalid compiled expression token")

        token_type = token_code & 0xFF
        if 0 < token_type < 0x80:
            if token_size < 8:
                raise ValueError("truncated object expression token")
            object_id = struct.unpack_from("<H", output, token_pos + 4)[0]
            if object_id in object_id_map:
                struct.pack_into(
                    "<H", output, token_pos + 4, object_id_map[object_id]
                )
        token_pos = token_end
    raise ValueError("compiled expression lacks a terminator")

def condition_parameter_sizes(
    record: bytes, start: int, end: int
) -> tuple[list[int], list[int]]:
    """How wide each parameter of a condition is."""

    def tile(mask: int) -> list[int] | None:
        sizes: list[int] = []
        pos = start
        while pos < end:
            if pos + 4 > end:
                return None
            size = struct.unpack_from("<H", record, pos)[0] & mask
            if size < 4 or pos + size > end:
                return None
            sizes.append(size)
            pos += size
        return sizes if pos == end else None

    wide = tile(0xFFFF)
    if wide is not None:
        return wide, []
    narrow = tile(0x00FF)
    if narrow is None:
        raise ValueError("invalid compiled condition parameter")
    repaired = []
    pos = start
    for size in narrow:
        if struct.unpack_from("<H", record, pos)[0] > 0xFF:
            repaired.append(pos)
        pos += size
    return narrow, repaired

def repair_header_object_type(
    output: bytearray,
    pos: int,
    object_types: dict[int, int] | None,
) -> None:
    """Correct an event header whose object type does not match its use."""
    if object_types is None:
        return
    stored = output[pos + 2]
    object_id = struct.unpack_from("<H", output, pos + 4)[0]
    if object_id & 0x8000:
        return
    bank = object_types.get(object_id)
    if bank is None or bank == stored or not 0 < bank < 0x80:
        return
    output[pos + 2] = bank

def compiled_event_to_editor_event(
    compiled: bytes,
    object_id_map: dict[int, int] | None = None,
    frame_target_map: dict[int, int] | None = None,
    object_types: dict[int, int] | None = None,
    size_repairs: list | None = None,
) -> bytes:
    """Convert one compiled event.

    The heart of getting a game's logic back. A compiled event row and an editor
    one are close relatives rather than different things, so this rewrites a
    compiled row in place rather than translating it — every field it does not
    understand survives verbatim, which is why unusual events come through at all.

    Three kinds of change happen, and the distinction is worth holding onto.

    **Renumbering.** Object references are stored under the application's own
    numbering and the editor wants the frame's, so every place a row names an
    object is rewritten: the condition and action headers, object parameters, the
    "other object" in a collision, position references, and every reference nested
    inside an expression. Frame jump targets get the same treatment — the stored
    value identifies a frame rather than counting to it, which is what lets a jump
    to a since-deleted frame be repaired instead of silently pointing somewhere.

    **Clearing what only the runtime uses.** A sound parameter keeps its name in
    both forms but also carries the runtime's handle into the sound bank, which
    the editor resolves by name instead; music is the same with a different empty
    value. An event-group action compiles its target into a runtime address, and
    the editor works that out from the event list. Each of these is set to the
    value the editor writes, not to zero on principle.

    **Repairs, each optional and each recorded.** A header whose stored object
    type disagrees with the object bank can be corrected. A parameter whose size
    word carries a stray high byte is fixed in the row itself and not merely
    skipped over while reading — dropping a bad value from the reader and leaving
    it in the output is exactly the mistake worth not making twice.

    Everything else is checked rather than assumed: a record whose size does not
    account for its own contents, or an event with bytes left over at the end,
    raises instead of producing a row that opens and means something else.
    """

    output = bytearray(compiled)
    signed_size = struct.unpack_from("<h", output, 0)[0]
    if signed_size >= 0 or -signed_size != len(output):
        raise ValueError("invalid compiled event record size")

    condition_count = output[2]
    action_count = output[3]
    if not condition_count or not action_count:
        raise ValueError("this experiment expects conditions and actions")

    pos = 0x0E
    for _ in range(condition_count):
        record_size = struct.unpack_from("<H", output, pos)[0]
        record_end = pos + record_size
        if record_size < 0x0E or record_end > len(output):
            raise ValueError("invalid compiled condition record")

        output[pos + 12 : pos + 14] = b"\x00\x00"
        object_type = output[pos + 2]
        if object_type < 0x80:

            repair_header_object_type(output, pos, object_types)
        if object_id_map is not None and object_type < 0x80:
            object_id = struct.unpack_from("<H", output, pos + 4)[0]
            if object_id in object_id_map:
                struct.pack_into("<H", output, pos + 4, object_id_map[object_id])

        parameter_sizes, stray_high_bytes = condition_parameter_sizes(
            output, pos + 14, record_end
        )

        for offset in stray_high_bytes:
            if size_repairs is not None:
                size_repairs.append(
                    {
                        "record_offset": pos,
                        "parameter_offset": offset,
                        "stored": struct.unpack_from("<H", output, offset)[0],
                        "used": struct.unpack_from("<H", output, offset)[0] & 0xFF,
                        "parameter_type": struct.unpack_from(
                            "<H", output, offset + 2
                        )[0],
                    }
                )
            output[offset + 1] = 0
        parameter_pos = pos + 14
        for parameter_size in parameter_sizes:
            parameter_type = struct.unpack_from(
                "<H", output, parameter_pos + 2
            )[0]
            parameter_end = parameter_pos + parameter_size
            if parameter_type == 1 and object_id_map is not None:

                if parameter_size < 10:
                    raise ValueError("truncated compiled object parameter")
                object_id = struct.unpack_from("<H", output, parameter_pos + 6)[0]
                if object_id in object_id_map:
                    struct.pack_into(
                        "<H", output, parameter_pos + 6, object_id_map[object_id]
                    )
            elif parameter_type in OBJECT_POSITION_PARAMETER_SIZES:
                remap_object_position_parameter(
                    output,
                    parameter_pos,
                    parameter_size,
                    parameter_type,
                    object_id_map,
                )
            elif (
                parameter_type in EXPRESSION_PARAMETER_TYPES
                and object_id_map is not None
            ):
                remap_expression_object_ids(
                    output, parameter_pos, parameter_end, object_id_map
                )
            parameter_pos = parameter_end
        pos = record_end

    for _ in range(action_count):
        record_size = struct.unpack_from("<H", output, pos)[0]
        record_end = pos + record_size
        if record_size < 0x0C or record_end > len(output):
            raise ValueError("invalid compiled action record")
        object_type = output[pos + 2]
        if object_type < 0x80:
            repair_header_object_type(output, pos, object_types)
        if object_id_map is not None and object_type < 0x80:
            object_id = struct.unpack_from("<H", output, pos + 4)[0]
            if object_id in object_id_map:
                struct.pack_into("<H", output, pos + 4, object_id_map[object_id])

        parameter_count = output[pos + 10]
        parameter_pos = pos + 12
        for _parameter_index in range(parameter_count):
            if parameter_pos + 4 > record_end:
                raise ValueError("truncated compiled action parameter")
            parameter_size, parameter_type = struct.unpack_from(
                "<HH", output, parameter_pos
            )
            parameter_end = parameter_pos + parameter_size
            if parameter_size < 4 or parameter_end > record_end:
                raise ValueError("invalid compiled action parameter")
            if parameter_type == 6:

                if parameter_size < 6:
                    raise ValueError("truncated compiled sample parameter")
                output[parameter_pos + 4 : parameter_pos + 6] = b"\x00\x00"
            elif parameter_type == 7:

                if parameter_size < 6:
                    raise ValueError("truncated compiled music parameter")
                output[parameter_pos + 4 : parameter_pos + 6] = b"\xFF\xFF"
            elif parameter_type == 26 and frame_target_map is not None:

                if parameter_size >= 6:
                    target = struct.unpack_from("<H", output, parameter_pos + 4)[0]
                    if target in frame_target_map:
                        struct.pack_into(
                            "<H",
                            output,
                            parameter_pos + 4,
                            frame_target_map[target],
                        )
            elif parameter_type == 39:

                if parameter_size < 8:
                    raise ValueError("truncated compiled event-group parameter")
                output[parameter_pos + 4 : parameter_pos + 8] = b"\x00" * 4
            elif parameter_type == 1 and object_id_map is not None:
                if parameter_size < 10:
                    raise ValueError("truncated compiled object parameter")
                object_id = struct.unpack_from("<H", output, parameter_pos + 6)[0]
                if object_id in object_id_map:
                    struct.pack_into(
                        "<H", output, parameter_pos + 6, object_id_map[object_id]
                    )
            elif parameter_type in OBJECT_POSITION_PARAMETER_SIZES:
                remap_object_position_parameter(
                    output,
                    parameter_pos,
                    parameter_size,
                    parameter_type,
                    object_id_map,
                )
            elif (
                parameter_type in EXPRESSION_PARAMETER_TYPES
                and object_id_map is not None
            ):
                remap_expression_object_ids(
                    output, parameter_pos, parameter_end, object_id_map
                )
            parameter_pos = parameter_end
        if parameter_pos != record_end:
            raise ValueError("action contains unparsed trailing parameter data")
        pos = record_end

    if pos != len(output):
        raise ValueError("event record contains unparsed trailing data")
    return bytes(output)

def compiled_events_to_editor_events(
    compiled_events: list[bytes],
    object_id_map: dict[int, int] | None = None,
    frame_target_map: dict[int, int] | None = None,
    first_handle: int = 1,
    object_types: dict[int, int] | None = None,
    size_repairs: list | None = None,
) -> list[bytes]:
    """Convert a whole program of compiled events into editor events.

    Each row is converted on its own, and then one thing is done that only makes
    sense across the whole list: the editor's group handles are handed back out.

    An event sheet can nest groups inside groups, and the editor identifies every
    row — and both ends of every group — by a handle. Those handles are allocated
    in a particular order, so they are reissued by walking the list the same way:
    a group's opening row takes the next handle, its closing row the one after,
    and then the rows *inside* it are numbered, before the walk carries on past
    the close. Nesting is handled by recursion into each group's span, which is
    why an inner group's rows land where the editor expects rather than after
    everything else.

    The scan for a group's matching close counts depth rather than stopping at the
    first close it meets, and a group that never closes raises with its position
    instead of silently swallowing the rest of the sheet.

    Where the numbering starts is a parameter rather than a constant, and the
    reason is a genuine irregularity: every frame's sheet starts at one, and so
    does an ungrouped global sheet, but a *grouped* 1.5 global sheet starts at two.
    Since one version needs the offset and the other does not, the caller says
    which rather than the code deciding from the version.
    """

    events = [
        bytearray(
            compiled_event_to_editor_event(
                event,
                object_id_map=object_id_map,
                frame_target_map=frame_target_map,
                object_types=object_types,
                size_repairs=size_repairs,
            )
        )
        for event in compiled_events
    ]

    def is_group_open(event: bytearray) -> bool:
        return len(event) >= 18 and event[16:18] == b"\xFF\xF6"

    def is_group_close(event: bytearray) -> bool:
        return len(event) >= 18 and event[16:18] == b"\xFF\xF5"

    def matching_close(open_index: int, stop: int) -> int:
        depth = 1
        for index in range(open_index + 1, stop):
            if is_group_open(events[index]):
                depth += 1
            elif is_group_close(events[index]):
                depth -= 1
                if depth == 0:
                    return index
        raise ValueError(f"event group at index {open_index} has no closing marker")

    next_handle = first_handle

    def assign_range(start: int, stop: int) -> None:
        nonlocal next_handle
        index = start
        while index < stop:
            event = events[index]
            if is_group_close(event):
                raise ValueError(f"unexpected event-group close at index {index}")
            if is_group_open(event):
                close_index = matching_close(index, stop)
                struct.pack_into("<H", event, 10, next_handle)
                next_handle += 1
                struct.pack_into("<H", events[close_index], 10, next_handle)
                next_handle += 1
                assign_range(index + 1, close_index)
                index = close_index + 1
                continue
            struct.pack_into("<H", event, 10, next_handle)
            next_handle += 1
            index += 1

    assign_range(0, len(events))
    return [bytes(event) for event in events]

def group_marker(event: bytes) -> int:
    """The row that opens or closes a group."""
    if len(event) >= 18 and event[16:18] == b"\xFF\xF6":
        return 1
    if len(event) >= 18 and event[16:18] == b"\xFF\xF5":
        return -1
    return 0

def stray_group_closes(compiled_events: list[bytes]) -> list[int]:
    """Group closes with nothing open to close."""
    stack: list[int] = []
    stray: list[int] = []
    for index, event in enumerate(compiled_events):
        kind = group_marker(event)
        if kind == 1:
            stack.append(index)
        elif kind == -1:
            if stack:
                stack.pop()
            else:
                stray.append(index)
    return stray

def drop_stray_group_closes(compiled_events: list[bytes]) -> list[bytes]:
    """Remove closes that would nest the sheet wrongly."""
    stray = set(stray_group_closes(compiled_events))
    if not stray:
        return compiled_events
    return [
        event for index, event in enumerate(compiled_events) if index not in stray
    ]

def unclosed_groups(compiled_events: list[bytes]) -> list[int]:
    """The event groups a program leaves open at its end."""
    stack: list[int] = []
    for index, event in enumerate(compiled_events):
        kind = group_marker(event)
        if kind == 1:
            stack.append(index)
        elif kind == -1:
            if not stack:
                raise ValueError(f"unexpected event-group close at index {index}")
            stack.pop()
    return stack

def group_close_template(programs: list[list[bytes]]) -> bytes | None:
    """The neutral closing row, emitted from named fields."""
    for program in programs:
        for event in program:
            if group_marker(event) == -1:
                return bytes(event)
    return None

def repair_missing_flat_group_close(
    compiled_events: list[bytes], close_template: bytes | None = None
) -> list[bytes]:
    """Close a group the compiler left open, and say where."""
    if not unclosed_groups(compiled_events):
        return compiled_events

    own_close = next(
        (event for event in compiled_events if group_marker(event) == -1), None
    )

    close_template = own_close if own_close is not None else close_template
    if close_template is None:

        raise ValueError(
            "event program leaves a group open and no program in this package "
            "holds a close record to copy; refusing to invent one"
        )
    synthetic_close = bytearray(close_template)
    struct.pack_into("<H", synthetic_close, 10, 0)
    synthetic_close[12:14] = b"\x00\x00"

    events = list(compiled_events)
    for _pass in range(len(events) + 1):
        stack = unclosed_groups(events)
        if not stack:
            return events
        orphan = stack[0]

        balance = 0
        for event in events[orphan + 1:]:
            balance += group_marker(event)
            if balance < 0:
                raise ValueError(
                    f"event group at index {orphan} is not trailing; its "
                    "remainder is unbalanced, so where it closes is undecidable"
                )

        at = next(
            (index for index in range(orphan + 1, len(events))
             if group_marker(events[index]) == 1),
            len(events),
        )
        events = events[:at] + [bytes(synthetic_close)] + events[at:]
    raise ValueError("event-group repair did not converge")

def compiled_event_programs_to_editor_events(
    compiled_programs: list[list[bytes]],
    object_id_map: dict[int, int] | None = None,
    frame_target_map: dict[int, int] | None = None,
    object_types: dict[int, int] | None = None,
    size_repairs: list | None = None,
    remarks: list | None = None,
    first_remark_index: int = 1,
    recover_comments: bool = False,
    first_comment_index: int = 1,
    close_template: bytes | None = None,
) -> list[bytes]:
    """Convert every program a frame carries."""
    repaired = [
        repair_missing_flat_group_close(program, close_template=close_template)
        for program in compiled_programs

        if program
    ]
    if remarks is None:
        if recover_comments:
            raise ValueError(
                "recover_comments needs a remarks list: a recovered comment "
                "row whose id names no EvRk record is a dangling reference"
            )
        compiled_events = [event for program in repaired for event in program]
    else:
        compiled_events, texts = label_flattened_programs(
            repaired,
            first_index=first_remark_index,
            recover_comments=recover_comments,
            first_comment_index=first_comment_index,
        )
        remarks.extend(texts)
    return compiled_events_to_editor_events(
        compiled_events,
        object_id_map=object_id_map,
        frame_target_map=frame_target_map,
        object_types=object_types,
        size_repairs=size_repairs,
    )
