# GENERATED — do not edit by hand. This file is produced by KlikBack's
# sync tooling; changes belong in the source it is generated from.
#
# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""Rebuild an object's animation set -- its directions, frames and speeds.

Animation names are not always kept by the compiler. Where a name is missing
but the events refer to it, the name is recovered from that reference rather
than left blank.
"""

from __future__ import annotations
import struct

STANDARD_ANIMATION_NAMES = {
    0: b"Stopped",
    1: b"Walking",
    2: b"Running",
    3: b"Appearing",
    4: b"Disappearing",
    5: b"Bouncing",
    6: b"Shooting",
    7: b"Jumping",
    8: b"Falling",
    9: b"Climbing",
    10: b"Crouch down",
    11: b"Stand up",
}

def parse_runtime_animation_set(definition: bytes) -> list[dict]:
    """The animations as the compiled game stored them.

    An Active's animations are three tables nested inside each other. The object
    points at a table of animation slots; each animation that exists points at a
    table of thirty-two directions; each direction that exists holds its speeds,
    its looping settings and the list of images making up its frames. Slots and
    directions the object does not use are stored as zero and skipped, which is
    why an object with one animation facing one way is small.

    Every offset is checked against the definition's real length before it is
    followed, and each level says which animation and which direction it was
    reading when something did not fit. An animation table is followed by
    offsets, and an offset that points outside the data reads whatever is there —
    so the checks are what separate "this object has unusual animations" from
    "this object is being misread".

    One thing that looks like damage and is not: the animation table does not
    always run to the end of the definition. An object with a fade-in or fade-out
    transition stores that block straight after it. So trailing bytes are
    legitimate and only an overrun is a fault.

    The standard animations are given their editor names — Stopped, Walking and
    the rest — and anything beyond them is numbered. Games exist that store the
    names and games exist that store nothing and let the editor supply the label
    from the slot; both load, and writing the names is the form proven to match
    what the editor saves.
    """
    base = 60
    if len(definition) < base + 4:
        raise ValueError("Active definition has no animation table")
    table_size, animation_slots = struct.unpack_from("<HH", definition, base)

    if base + table_size > len(definition):
        raise ValueError(
            f"animation table size {table_size} overruns the definition"
        )
    offsets_end = base + 4 + animation_slots * 2
    if offsets_end > len(definition):
        raise ValueError("animation offset table is truncated")
    animation_offsets = struct.unpack_from(
        f"<{animation_slots}H", definition, base + 4
    )

    animations = []
    for animation_id, animation_offset in enumerate(animation_offsets):
        if animation_offset == 0:
            continue
        animation_pos = base + animation_offset
        if animation_pos + 64 > len(definition):
            raise ValueError(f"animation {animation_id} direction table is truncated")
        direction_offsets = struct.unpack_from("<32H", definition, animation_pos)
        directions = []
        for direction_id, direction_offset in enumerate(direction_offsets):
            if direction_offset == 0:
                continue
            direction_pos = animation_pos + direction_offset
            if direction_pos + 8 > len(definition):
                raise ValueError(
                    f"animation {animation_id} direction {direction_id} is truncated"
                )
            minimum_speed, maximum_speed = struct.unpack_from(
                "<BB", definition, direction_pos
            )
            repeat, repeat_frame, frame_count = struct.unpack_from(
                "<HHH", definition, direction_pos + 2
            )
            frame_end = direction_pos + 8 + frame_count * 2
            if frame_end > len(definition):
                raise ValueError(
                    f"animation {animation_id} direction {direction_id} frames are truncated"
                )
            image_ids = list(
                struct.unpack_from(
                    f"<{frame_count}H", definition, direction_pos + 8
                )
            )
            directions.append(
                {
                    "direction_id": direction_id,
                    "minimum_speed": minimum_speed,
                    "maximum_speed": maximum_speed,
                    "repeat": repeat,
                    "repeat_frame": repeat_frame,
                    "image_ids": image_ids,
                }
            )

        name = STANDARD_ANIMATION_NAMES.get(
            animation_id, f"User animation {animation_id - 11}".encode("ascii")
        )
        animations.append(
            {
                "animation_id": animation_id,
                "name": name,
                "directions": directions,
            }
        )
    return animations

def animation_names_from_events(events: list[bytes]) -> dict[int, bytes]:
    """Animation names recovered from the events that use them."""
    names: dict[int, bytes] = {}
    for event in events:
        pos = 0x0E
        for _ in range(event[2]):
            size = struct.unpack_from("<H", event, pos)[0]
            pos += size
        for _ in range(event[3]):
            action_size = struct.unpack_from("<H", event, pos)[0]
            action_end = pos + action_size

            parameter_count = event[pos + 10]
            parameter_pos = pos + 12
            for _parameter_index in range(parameter_count):
                parameter_size, parameter_type = struct.unpack_from(
                    "<HH", event, parameter_pos
                )
                parameter_end = parameter_pos + parameter_size
                if parameter_end > action_end:
                    raise ValueError("animation action parameter is truncated")
                if parameter_type == 10:
                    if parameter_size < 7:
                        raise ValueError("animation-name parameter is truncated")
                    animation_id = struct.unpack_from("<H", event, parameter_pos + 4)[0]
                    name_start = parameter_pos + 6
                    name_end = event.find(b"\x00", name_start, parameter_end)
                    if name_end < 0:
                        raise ValueError("animation-name parameter is not terminated")
                    if name_end > name_start:
                        names[animation_id] = event[name_start:name_end]
                parameter_pos = parameter_end
            if parameter_pos != action_end:
                raise ValueError("animation action contains trailing parameter data")
            pos = action_end
        if pos != len(event):
            raise ValueError("animation event contains trailing data")
    return names

def editor_animation_set(animations: list[dict]) -> bytes:
    """An object's animations in the form a project stores."""
    result = bytearray(b"AnSt" + struct.pack("<I", len(animations)))
    for animation in animations:
        directions = animation["directions"]
        result.extend(b"Anix" + struct.pack("<I", len(directions)))
        for direction in directions:
            image_ids = direction["image_ids"]
            result.extend(b"Dirx" + struct.pack("<I", len(image_ids)))
            for image_id in image_ids:
                result.extend(b"Imag" + struct.pack("<I", image_id))
            result.extend(
                struct.pack(
                    "<IIIIII",
                    direction["direction_id"],
                    direction["minimum_speed"],
                    direction["maximum_speed"],
                    direction["repeat"],
                    direction["repeat_frame"],
                    direction["direction_id"],
                )
            )
        result.extend(struct.pack("<I", animation["animation_id"]))
        name = animation["name"]
        result.extend(struct.pack("<I", len(name)) + name)
    return bytes(result)
