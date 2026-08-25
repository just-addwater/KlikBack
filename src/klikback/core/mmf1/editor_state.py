# GENERATED — do not edit by hand. This file is produced by KlikBack's
# sync tooling; changes belong in the source it is generated from.
#
# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""The editor's own saved state: which windows were open, and where.

A project remembers how it was last being worked on -- the frame editor
windows, their positions, which frames they showed. It is not part of the
game, but a project without it opens looking wrong, so a rebuild writes a
sensible one and points it at the frames that actually exist.
"""

from __future__ import annotations
import struct

PROJECT_PATH_RECORD = b"icnD"

FRAME_NAMING_WINDOW_CLASSES = (60, 74)

PATH_TO_LAYOUT_GAP = 4

WINDOW_SENTINEL_OFFSET = 8

WINDOW_SENTINEL = -1

PLACEMENT_LENGTH_OFFSET = 20

PLACEMENT_LENGTH = 44

def editor_state_span(data: bytes) -> tuple[int, int] | None:
    """Where the editor's saved state sits in the project."""
    at = data.find(PROJECT_PATH_RECORD)
    if at < 0:
        return None
    try:
        _a, _b, length = struct.unpack_from("<III", data, at + 4)
    except struct.error:
        return None
    end = at + 16 + length

    if end >= len(data) or data[end : end + 1] != bytes(1):
        return None

    start = end + PATH_TO_LAYOUT_GAP
    if start > len(data) or (len(data) - start) % 4:
        return None
    return start, len(data)

def frame_editor_records(data: bytes) -> list[int]:
    """The window records, one per frame editor."""
    span = editor_state_span(data)
    if span is None:
        return []
    start, end = span
    count = (end - start) // 4
    if count < 6:
        return []
    words = struct.unpack_from(f"<{count}i", data, start)
    found = []
    for index in range(count - 5):
        if words[index] not in FRAME_NAMING_WINDOW_CLASSES:
            continue
        if words[index + WINDOW_SENTINEL_OFFSET // 4] != WINDOW_SENTINEL:
            continue
        if words[index + PLACEMENT_LENGTH_OFFSET // 4] != PLACEMENT_LENGTH:
            continue
        found.append(start + 4 * (index + 1))
    return found

def frame_item_ids(data: bytes) -> list[int]:
    """Which frames those windows refer to."""
    from klikback.core.mmf1.behaviour_reconstruct import editor_frames

    ids = []
    for frame in editor_frames(data):
        at = frame.find(b"Pltt")
        if at >= 4:
            ids.append(struct.unpack_from("<I", frame, at - 4)[0])
    return ids

def retarget_frame_editor_windows(
    data: bytes, ids: list[int] | None = None
) -> tuple[bytes, list[str]]:
    """Point the saved windows at the rebuilt project's own frames."""
    if ids is None:
        ids = frame_item_ids(data)
    if not ids:
        return data, []
    present = set(ids)
    first = ids[0]
    output = bytearray(data)
    repairs: list[str] = []
    for at in frame_editor_records(data):
        stored = struct.unpack_from("<i", output, at)[0]
        if stored in present:
            continue
        struct.pack_into("<i", output, at, first)
        repairs.append(
            f"the scaffold's saved editor layout reopens a Frame Editor on "
            f"frame item id {stored}, which this project has no frame for; "
            f"retargeted to frame 0's item id {first} so the window can be "
            f"reopened"
        )
    if not repairs:
        return data, []
    return bytes(output), repairs
