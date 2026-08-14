# GENERATED — do not edit by hand. This file is produced by KlikBack's
# sync tooling; changes belong in the source it is generated from.
#
# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""Work out which objects a frame's events talk about, and under which ids.

An editor project lists a frame's event objects explicitly; a compiled game
does not. What survives is the events themselves, and every condition and
action in them carries the type and the reference of the object it acts on.
The registry is rebuilt from that: read every reference, keep the ones that
name a real object rather than a system facility, and the frame's event
object list falls out.

Two ids are involved and they are deliberately kept apart. An object's place
in the frame and its place in the event registry are different namespaces —
Backdrops, for instance, occupy the first and not the second — and merging
them produces events pointing at the wrong objects.

Where the events reference something no surviving object explains, a
placeholder is created and labelled rather than dropped, so the event is
readable in the editor instead of silently disappearing.
"""

from __future__ import annotations
import struct
from typing import Container, Iterator
from klikback.core.common.reconstruct_event_test import condition_parameter_sizes

QUALIFIER_FLAG = 0x8000

ABSOLUTE_OBJECT_SENTINELS = {0xFFFE, 0xFFFF}

CREATE_PLACEHOLDER = 1

SHOOT_PLACEHOLDER = 2

PLACEHOLDER_INSTANCE_FLAG = 8

UNRESOLVED_SHOOT_PARENT = 0xFFFF

NO_PLACEHOLDER_PARENT = -1

NON_EVENT_OBJECT_TYPES = {0, 1}

OBJECT_PARAMETER = 1

OBJECT_TYPE_TOKEN_BASE = 0x3000

CREATE_PARAMETER = 9

POSITION_PARAMETER = 16

SHOOT_PARAMETER = 18

ASK_POSITION_PARAMETER = 21

EXPRESSION_PARAMETERS = {15, 22, 23, 45, 52, 53}

OBJECT_POSITION_PARAMETER_SIZES = {
    CREATE_PARAMETER: 0x22,
    POSITION_PARAMETER: 0x1A,
    SHOOT_PARAMETER: 0x24,
    ASK_POSITION_PARAMETER: 0x22,
}

TARGET_PARAMETERS = {CREATE_PARAMETER, SHOOT_PARAMETER}

QUALIFIER_NAMES = {
    0: b"Group.Player",
    1: b"Group.Good",
    2: b"Group.Neutral",
    3: b"Group.Bad",
    4: b"Group.Enemies",
    5: b"Group.Friends",
    6: b"Group.Bullets",
    7: b"Group.Arms",
    8: b"Group.Bonus",
    9: b"Group.Collectables",
    10: b"Group.Traps",
    11: b"Group.Doors",
    12: b"Group.Keys",
    13: b"Group.Texts",
}

def qualifier_display_name(qualifier_id: int) -> bytes:
    """The name the editor shows for a qualifier group."""
    if qualifier_id in QUALIFIER_NAMES:
        return QUALIFIER_NAMES[qualifier_id]
    if 14 <= qualifier_id <= 23:
        return b"Group.%d" % (qualifier_id - 14)
    if 24 <= qualifier_id <= 99:
        return b"Group.%d" % qualifier_id
    raise ValueError(f"qualifier id {qualifier_id} is out of the proven range")

def parse_compiled_placements_with_links(
    data: bytes,
) -> list[tuple[int, int, int, int, int]]:
    """Read a frame's placements, keeping the links between them."""
    if len(data) < 4:
        raise ValueError("truncated compiled placement list")
    count = struct.unpack_from("<I", data, 0)[0]
    if len(data) != 4 + count * 12:
        raise ValueError(
            f"unexpected placement list size {len(data)} for {count} records"
        )
    placements = []
    for index in range(count):
        pos = 4 + index * 12
        instance_id, object_id, x, y, runtime_link = struct.unpack_from(
            "<HHhhI", data, pos
        )
        placements.append((instance_id, x, y, object_id, runtime_link))
    return placements

def expression_object_slots(
    event: bytes, parameter_pos: int, parameter_end: int
) -> Iterator[tuple[str, int, int]]:
    """The references carried by expressions inside actions."""
    token_pos = parameter_pos + 6
    while token_pos < parameter_end:
        if token_pos + 2 > parameter_end:
            raise ValueError("truncated compiled expression token")
        token_code = struct.unpack_from("<H", event, token_pos)[0]
        if token_code == 0:
            return
        if token_pos + 4 > parameter_end:
            raise ValueError("truncated compiled expression token header")
        token_size = struct.unpack_from("<H", event, token_pos + 2)[0]
        token_end = token_pos + token_size
        if token_size < 4 or token_end > parameter_end:
            raise ValueError("invalid compiled expression token")
        token_type = token_code & 0xFF
        if 0 < token_type < 0x80:
            if token_size < 8:
                raise ValueError("truncated object expression token")
            word = struct.unpack_from("<H", event, token_pos + 4)[0]

            expected = token_type if token_code >= OBJECT_TYPE_TOKEN_BASE else None
            yield ("expression token", expected, word)
        token_pos = token_end
    raise ValueError("compiled expression lacks a terminator")

def event_object_slots(event: bytes) -> Iterator[tuple[str, int | None, int]]:
    """The references carried by conditions and actions.

    Every place one compiled event names an object, in the order they appear:
    the condition and action headers themselves, object parameters, the "which
    object" word inside a position parameter, the creation target of an action
    that makes something, and every reference inside an expression.

    Each slot also reports the object *type* the record implies, and only where
    that type can be trusted. A header byte and an expression token say what kind
    of object they expect and are worth checking against the object bank. The
    word trailing an object parameter looks like the same information and is not
    — it is cached by the editor rather than maintained, and games exist whose
    cached word disagrees with the object's real type. Reporting it as
    authoritative would make those games fail a check they should pass, so it is
    read for its id and left alone otherwise.

    The record sizes are checked as the walk goes, and a size that does not
    account for exactly the bytes present raises. An event whose parameters do
    not add up is one where a silent recovery would put a reference in the wrong
    slot.
    """
    signed_size = struct.unpack_from("<h", event, 0)[0]
    if signed_size >= 0 or -signed_size != len(event):
        raise ValueError("invalid compiled event record size")
    condition_count = event[2]
    action_count = event[3]
    pos = 0x0E
    for kind, count, fixed_size in (
        ("condition", condition_count, 14),
        ("action", action_count, 12),
    ):
        for _ in range(count):
            record_size = struct.unpack_from("<H", event, pos)[0]
            record_end = pos + record_size
            if record_size < fixed_size or record_end > len(event):
                raise ValueError(f"invalid compiled {kind} record")
            type_byte = event[pos + 2]
            if type_byte < 0x80:
                yield (
                    f"{kind} header",
                    type_byte,
                    struct.unpack_from("<H", event, pos + 4)[0],
                )
            parameter_pos = pos + fixed_size

            condition_sizes = (
                condition_parameter_sizes(event, parameter_pos, record_end)[0]
                if kind == "condition"
                else None
            )
            size_index = 0
            while parameter_pos < record_end:
                if parameter_pos + 4 > record_end:
                    raise ValueError(f"truncated compiled {kind} parameter")
                parameter_size, parameter_type = struct.unpack_from(
                    "<HH", event, parameter_pos
                )
                if condition_sizes is not None:
                    parameter_size = condition_sizes[size_index]
                    size_index += 1
                parameter_end = parameter_pos + parameter_size
                if parameter_size < 4 or parameter_end > record_end:
                    raise ValueError(f"invalid compiled {kind} parameter")
                if parameter_type == OBJECT_PARAMETER:
                    if parameter_size < 10:
                        raise ValueError("truncated compiled object parameter")

                    yield (
                        "object parameter",
                        None,
                        struct.unpack_from("<H", event, parameter_pos + 6)[0],
                    )
                elif parameter_type in OBJECT_POSITION_PARAMETER_SIZES:
                    minimum = OBJECT_POSITION_PARAMETER_SIZES[parameter_type]
                    if parameter_size < minimum:
                        raise ValueError(
                            f"truncated compiled type-{parameter_type} parameter"
                        )
                    reference = struct.unpack_from(
                        "<H", event, parameter_pos + 4
                    )[0]
                    if reference not in ABSOLUTE_OBJECT_SENTINELS:
                        yield ("position reference", None, reference)
                    if parameter_type in TARGET_PARAMETERS:
                        yield (
                            "creation target",
                            None,
                            struct.unpack_from(
                                "<H", event, parameter_pos + 0x1C
                            )[0],
                        )
                elif parameter_type in EXPRESSION_PARAMETERS:
                    yield from expression_object_slots(
                        event, parameter_pos, parameter_end
                    )
                parameter_pos = parameter_end
            pos = record_end
    if pos != len(event):
        raise ValueError("event record contains unparsed trailing data")

def collect_event_references(
    events: list[bytes],
    objects_by_id: dict[int, dict],
    type_repairs: list | None = None,
) -> tuple[set[int], set[int]]:
    """Every object reference the events make."""
    object_ids: set[int] = set()
    qualifier_words: set[int] = set()
    for event in events:
        for source, expected_type, word in event_object_slots(event):
            if word & QUALIFIER_FLAG:
                qualifier_words.add(word)
                continue
            if word not in objects_by_id:
                raise ValueError(
                    f"{source} references unknown runtime object {word}"
                )
            actual_type = objects_by_id[word]["object_type"]
            if expected_type is not None and expected_type != actual_type:
                if type_repairs is None:
                    raise ValueError(
                        f"{source} claims object {word} has type "
                        f"{expected_type}, but the object bank says "
                        f"{actual_type}"
                    )
                type_repairs.append(
                    {
                        "object_id": word,
                        "name": _readable_name(objects_by_id[word]),
                        "stored_type": expected_type,
                        "bank_type": actual_type,
                        "slot": source,
                        "reason": "stored type disagrees with the object "
                        "bank; the reference is kept and the row's type is "
                        "rewritten to the bank type",
                    }
                )
            object_ids.add(word)
    return object_ids, qualifier_words

def _readable_name(obj: dict) -> str:
    name = obj.get("name") or b""
    if isinstance(name, bytes):
        return name.split(b"\x00", 1)[0].decode("latin-1", "replace")
    return str(name)

RUNTIME_QUALIFIER_OFFSET = 20

QUALIFIER_TERMINATOR = 0xFFFF

MAX_QUALIFIER_ID = 99

EDITOR_QUALIFIER_CAPACITY = 8

def object_qualifiers(obj: dict) -> list[int]:
    """The qualifier groups an object belongs to."""
    if "definition" not in obj:
        raise ValueError(
            f"object {obj.get('object_id')} carries no definition, so its "
            "qualifier membership cannot be read"
        )
    definition = obj["definition"] or b""
    if len(definition) < RUNTIME_QUALIFIER_OFFSET + 18:
        return []
    words = list(struct.unpack_from("<9H", definition, RUNTIME_QUALIFIER_OFFSET))
    indices = (
        words[: words.index(QUALIFIER_TERMINATOR)]
        if QUALIFIER_TERMINATOR in words
        else words
    )
    if any(index > MAX_QUALIFIER_ID for index in indices):

        return []
    return indices[:EDITOR_QUALIFIER_CAPACITY]

def frame_registry(
    placements: list[tuple[int, int, int, int, int]],
    compiled_events: list[bytes],
    objects_by_id: dict[int, dict],
    type_repairs: list | None = None,
    unresolved_shoot_parents: list | None = None,
) -> dict:
    """The event object list for one frame, rebuilt from that frame's events.

    Compiling a game throws the editor's frame item list away and keeps only what
    the runtime needs: the objects' records, where they were placed, and the
    events. This puts the list back, and the whole question is what counts as
    evidence that an object belonged to the frame.

    Two things count. An object **really placed** in the frame belongs to it, and
    so does an object **named by a condition, an action or an expression** — even
    one placed nowhere, because an event that creates an object at runtime still
    has to be able to name it in the editor.

    One thing deliberately does not count. Some placements are not placements at
    all but the compiler's own bookkeeping for a Create or Shoot action, standing
    in for an object the events will bring into being later. On its own that is
    not evidence of anything: an object whose every placement is one of these and
    which no row names is not a frame item and gets no registry entry, and its
    stand-in placement goes with it. That matches what the editor writes for the
    same games. The ids are returned by name rather than filtered away quietly,
    so the caller drops exactly those and a genuine misreading cannot hide as a
    frame that came out slightly smaller than it should.

    A Shoot stand-in also names the object doing the shooting, and that word can
    outlive what it pointed at — the compiler keeps writing it after the link has
    gone stale. A parent with no other evidence in the frame is reported as
    dangling rather than invented into the object list, and the placement is
    written with no parent, which is what the editor itself does with one.

    Two id spaces come out of this and they are not the same. The frame item
    order includes every member; the event registry excludes the types that
    cannot appear in events, so an object's position differs between the two.
    The returned maps keep them apart. Qualifiers — the groups an object can be
    selected through — get registry entries too, and on **membership** rather
    than on being mentioned: an object that belongs to a group puts its group in
    the registry whether or not any row selects through it.
    """
    by_first_instance: dict[int, int] = {}
    placeholder_instance_for: dict[int, int] = {}
    shoot_parents: set[int] = set()
    really_placed: set[int] = set()
    for instance_id, _x, _y, object_id, runtime_link in placements:
        if object_id not in objects_by_id:
            raise ValueError(f"placement references unknown object {object_id}")
        if object_id not in by_first_instance or instance_id < by_first_instance[object_id]:
            by_first_instance[object_id] = instance_id
        if not runtime_link:
            really_placed.add(object_id)
        if runtime_link:
            kind = runtime_link & 0xFFFF
            parent = runtime_link >> 16
            if kind not in {CREATE_PLACEHOLDER, SHOOT_PLACEHOLDER}:
                raise ValueError(
                    f"unsupported placement runtime link 0x{runtime_link:08X}"
                )

            if kind == SHOOT_PLACEHOLDER and (
                parent == UNRESOLVED_SHOOT_PARENT or parent not in objects_by_id
            ):

                if unresolved_shoot_parents is not None:

                    unresolved_shoot_parents.append((instance_id, parent))
            elif kind == SHOOT_PLACEHOLDER:

                shoot_parents.add(parent)
            current = placeholder_instance_for.get(object_id)
            if current is None or instance_id < current:
                placeholder_instance_for[object_id] = instance_id

    referenced, qualifier_words = collect_event_references(
        compiled_events, objects_by_id, type_repairs
    )
    placed_order = sorted(by_first_instance, key=by_first_instance.get)

    shoot_only = shoot_parents - really_placed - referenced
    dangling_shoot_parents = sorted(shoot_only)
    referenced.update(shoot_parents - shoot_only)

    placeholder_only_orphans = sorted(
        object_id
        for object_id in placed_order
        if object_id not in really_placed and object_id not in referenced
    )
    orphans = set(placeholder_only_orphans)
    placed_order = [object_id for object_id in placed_order if object_id not in orphans]
    for object_id in orphans:
        placeholder_instance_for.pop(object_id, None)
    unplaced = sorted(referenced - set(placed_order))
    frame_item_object_ids = placed_order + unplaced
    event_object_ids = [
        object_id
        for object_id in frame_item_object_ids
        if objects_by_id[object_id]["object_type"] not in NON_EVENT_OBJECT_TYPES
    ]
    object_id_map = {
        object_id: event_id
        for event_id, object_id in enumerate(event_object_ids)
    }

    qualifier_words = set(qualifier_words)
    for object_id in event_object_ids:
        for qualifier_id in object_qualifiers(objects_by_id[object_id]):
            qualifier_words.add(QUALIFIER_FLAG | qualifier_id)

    for word in sorted(qualifier_words):
        object_id_map[word] = len(object_id_map)
    return {
        "frame_item_object_ids": frame_item_object_ids,
        "event_object_ids": event_object_ids,
        "qualifier_words": sorted(qualifier_words),
        "object_id_map": object_id_map,
        "local_item_for": {
            object_id: local_id
            for local_id, object_id in enumerate(frame_item_object_ids)
        },
        "placeholder_instance_for": placeholder_instance_for,
        "unplaced_referenced": unplaced,
        "dangling_shoot_parents": dangling_shoot_parents,
        "placeholder_only_orphans": placeholder_only_orphans,
    }

def create_placeholders_for_unplaced(
    registry: dict,
    placements: list[tuple[int, int, int, int, int]],
    frame_index: int,
    objects_by_id: dict[int, dict],
    losses: list[str] | None = None,
) -> list[tuple[int, int, int, int, int]]:
    """Give an event's unexplained reference something honest to point at."""
    unplaced = registry["unplaced_referenced"]
    if not unplaced:
        return []
    next_instance = max((instance_id for instance_id, *_ in placements), default=-1) + 1
    made = []
    for object_id in unplaced:
        made.append((next_instance, 0, 0, object_id, CREATE_PLACEHOLDER))
        registry["placeholder_instance_for"][object_id] = next_instance
        next_instance += 1
    if losses is not None:
        named = ", ".join(
            f"{object_id} ({_readable_name(objects_by_id[object_id])})"
            for object_id in unplaced
        )
        plural = "s" if len(made) != 1 else ""
        losses.append(
            f"frame {frame_index}: {len(made)} event-referenced object{plural} "
            f"[{named}] carr{'y' if len(made) != 1 else 'ies'} no runtime "
            f"placement, so each is given a Create placeholder instance at "
            f"(0, 0); the authored editor position is a compile loss"
        )
    return made

def placeholder_editor_fields(
    runtime_link: int,
    app_to_local_item: dict[int, int],
    allow_dangling_parent: bool | Container[int] = False,
) -> tuple[int, int, int]:
    """The fields a placeholder carries so it reads clearly in the editor."""
    kind = runtime_link & 0xFFFF
    parent_object = runtime_link >> 16
    if kind == CREATE_PLACEHOLDER:
        parent = NO_PLACEHOLDER_PARENT
    elif kind == SHOOT_PLACEHOLDER and parent_object == UNRESOLVED_SHOOT_PARENT:
        parent = NO_PLACEHOLDER_PARENT
    elif kind == SHOOT_PLACEHOLDER:
        if parent_object not in app_to_local_item:
            allowed = allow_dangling_parent is True or (
                allow_dangling_parent is not False
                and parent_object in allow_dangling_parent
            )
            if not allowed:
                raise ValueError(
                    f"shoot placeholder parent {parent_object} is not a frame item"
                )

            parent = NO_PLACEHOLDER_PARENT
        else:
            parent = app_to_local_item[parent_object]
    else:
        raise ValueError(f"unsupported placement runtime link 0x{runtime_link:08X}")
    return PLACEHOLDER_INSTANCE_FLAG, kind, parent

def qualifier_event_object_record(
    event_id: int, qualifier_word: int, object_type_id: int = 2
) -> bytes:
    """The registry entry standing for a qualifier rather than a single object.
    """
    qualifier_id = qualifier_word & ~QUALIFIER_FLAG
    name = qualifier_display_name(qualifier_id)
    return (
        b"EvOi"
        + struct.pack("<I", event_id)
        + struct.pack("<HH", 3, object_type_id)
        + struct.pack("<I", len(name))
        + name
        + struct.pack("<I", 6)
        + b"Sprite"
        + b"\x00\x00"
        + struct.pack("<H", qualifier_id)
    )
