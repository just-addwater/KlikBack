# GENERATED — do not edit by hand. This file is produced by KlikBack's
# sync tooling; changes belong in the source it is generated from.
#
# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""Recover an application's Global Events sheet.

A global event is authored once, at application level, and runs on every
frame. Compilation does not keep it as an application-level thing at all: it
copies the program into each frame, as an ordinary frame program. Recovering
the sheet therefore means recognising the same program appearing across
frames and lifting it back out to where it was authored.

That inference is what allows a rebuilt project to show the global sheet in
the editor rather than the same events repeated in every frame — which is
what the compiled game literally contains, and what a naive rebuild would
produce.

Where a program's owner cannot be established, it is recovered and labelled
as such rather than dropped or attributed to a guess. The events are real,
and losing them to preserve tidiness would be the wrong trade.
"""

from __future__ import annotations
import struct
from klikback.core.mmf1.event_analysis import split_event_records

CONTAINER_HEADER = b"KLBEDAEH"

CONTAINER_TRAILER = b"!DNE"

EVENT_TAG = b"STVE"

GROUP_TAG = b"SPRG"

GROUP_CLASS = b"class CGroupInfoList"

REGISTRY_TAG = b"SJBO"

REGISTRY_CLASS = b"class COIList"

CONTAINER_VERSION = 0x0300

CONTAINER_COUNT = 1

CONTAINER_STATE = 0x10

CONTAINER_STATE_HAS_GROUPS = 0x01

GROUP_OPEN = b"\xFF\xF6"

GROUP_NAME_SIZE = 80

GROUP_NAME_PARAMETER = 38

REGISTRY_REFERENCE_MARKER = b"OICO"

REGISTRY_ICON_TAG = b"GMIC"

def global_events(payload: bytes) -> tuple[list[bytes], bytes]:
    """The application's global sheet, lifted back out of the frames."""
    if not payload.startswith(CONTAINER_HEADER):
        raise ValueError("GEvt payload lacks the KLBEDAEH header")
    if not payload.endswith(CONTAINER_TRAILER):
        raise ValueError("GEvt payload lacks the !DNE trailer")
    tag = payload.index(EVENT_TAG)
    size = struct.unpack_from("<I", payload, tag + 4)[0]
    return split_event_records(payload[tag + 8 : tag + 8 + size])

def group_records(events: list[bytes]) -> list[tuple[bytes, int]]:
    """The event groups making up a sheet."""
    records = []
    for event in events:
        if len(event) < 18 or event[16:18] != GROUP_OPEN:
            continue
        size = struct.unpack_from("<H", event, 0x0E)[0]
        position = 0x0E + 14
        while position + 4 <= 0x0E + size:
            parameter_size, parameter_type = struct.unpack_from("<HH", event, position)
            if parameter_size < 4:
                break
            if parameter_type == GROUP_NAME_PARAMETER:
                flags = struct.unpack_from("<H", event, position + 6)[0]
                start = position + 8
                name = event[start : start + GROUP_NAME_SIZE].split(b"\x00")[0]
                records.append((name, flags))
                break
            position += parameter_size
    return records

def sub_block(tag: bytes, class_name: bytes, records: list[bytes]) -> bytes:
    """One named, counted list of records — the shape these blocks nest in."""
    return (
        tag
        + struct.pack("<I", len(class_name))
        + class_name
        + struct.pack("<I", len(records))
        + b"".join(records)
    )

def group_info_block(groups: list[tuple[bytes, int]]) -> bytes:
    """The header describing one group of events."""
    records = []
    for name, flags in groups:
        padded = name[:GROUP_NAME_SIZE].ljust(GROUP_NAME_SIZE, b"\x00")
        records.append(b"EvGI" + struct.pack("<IH", flags, flags) + padded)
    return sub_block(GROUP_TAG, GROUP_CLASS, records)

def object_registry_block(entries: list[dict]) -> bytes:
    """The object list a global sheet carries alongside its events."""
    records = []
    for entry in entries:
        icon = REGISTRY_ICON_TAG + entry["icon"]
        records.append(
            b"EvOi"
            + struct.pack("<IHH", entry["event_id"], 2, entry["object_type"])
            + struct.pack("<I", len(entry["name"]))
            + entry["name"]
            + struct.pack("<I", len(entry["type_name"]))
            + entry["type_name"]
            + struct.pack("<H", 0)
            + REGISTRY_REFERENCE_MARKER
            + struct.pack("<I", len(icon))
            + icon
        )
    return sub_block(REGISTRY_TAG, REGISTRY_CLASS, records)

def build_global_event_property(
    events: list[bytes],
    registry: list[dict] | None = None,
    plain_state: int | None = None,
) -> bytes:
    """Write the recovered sheet into the application's own property.

    The container the editor keeps a project's global event sheet in: the events
    themselves, then the list of objects they refer to, then the group information
    if the sheet has groups. A sheet without groups simply omits that part, and the
    state word says which shape it is.

    No comment rows are ever written into it, and that is not an omission. Comment
    rows never reach the runtime at all — they are compiler loss in the strictest
    sense — so unlike a frame's sheet there is nothing here whose position survived
    to be restored.

    One field differs between the two versions and is therefore **passed in rather
    than derived**. A sheet *with* groups stores the same state word in both. A
    sheet without them does not: one version always sets a particular bit, and the
    other lets both bits track the group list. Taking the word from the caller
    keeps that disagreement visible where the choice is made, instead of hiding it
    inside a version check where the next reader would find a rule that looks
    arbitrary.
    """
    data = b"".join(events) + b"\x00\x00"
    groups = group_records(events)
    if plain_state is None:
        plain_state = CONTAINER_STATE
    state = (
        CONTAINER_STATE | CONTAINER_STATE_HAS_GROUPS if groups else plain_state
    )
    blocks = b""
    if registry:
        blocks += object_registry_block(registry)
    if groups:
        blocks += group_info_block(groups)
    return (
        CONTAINER_HEADER
        + struct.pack("<HHI", CONTAINER_VERSION, CONTAINER_COUNT, state)
        + EVENT_TAG
        + struct.pack("<I", len(data))
        + data
        + blocks
        + CONTAINER_TRAILER
    )

def program_signature(program: list[bytes]) -> tuple[tuple[int, int], ...]:
    """A stable identity for a program, so the same one is recognised across frames.
    """
    return tuple((len(event), event[0x0A]) for event in program)

def classify_global_program(
    frame_programs: list[list[list[bytes]]],
) -> list[int] | None:
    """Decide what a recovered program is — global sheet, behaviour, or unknown.

    The global sheet is compiled into every frame, so it has to be told apart from
    each frame's own sheet before it can be lifted out. The programs come in a
    fixed order, but an empty frame sheet emits no program at all, so the global
    sheet is not reliably at any particular position.

    What *is* reliable is that it is the same program everywhere. So it is
    identified by its signature being common to all the frames rather than by where
    it sits.

    It answers "cannot tell" in the two cases where naming it would be a guess: an
    application with a single frame, where a global event and an object's
    behaviours compile to the same thing and nothing distinguishes them; and an
    application where two different candidates are common to every frame.

    The cost of guessing wrong is the reason for that caution. Mistaking one
    frame's own sheet for the global one would make that frame's events run in
    *every* frame. So an unresolved sheet is reported and left where it is —
    duplicated into each frame, which is wrong but visible — rather than moved on a
    guess.
    """

    frame_programs = [[p for p in programs if p] for programs in frame_programs]
    if len(frame_programs) < 2 or any(not p for p in frame_programs):
        return None
    candidates = set(program_signature(p) for p in frame_programs[0][:2])
    for programs in frame_programs[1:]:
        candidates &= set(program_signature(p) for p in programs[:2])
    if len(candidates) != 1:
        return None
    wanted = next(iter(candidates))
    indexes = []
    for programs in frame_programs:
        matches = [
            index
            for index, program in enumerate(programs[:2])
            if program_signature(program) == wanted
        ]
        if len(matches) != 1:
            return None
        indexes.append(matches[0])
    return indexes
