# GENERATED — do not edit by hand. This file is produced by KlikBack's
# sync tooling; changes belong in the source it is generated from.
#
# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""The Counter, Lives and Score objects, rebuilt from the compiled game.

All three display a number and all three store it the same way: a common
record head, then a tail holding the display settings -- digits or bar,
colours, minimum and maximum, and the images a digit display uses.
"""

from __future__ import annotations
import struct
from klikback.core.mmf15.object_record import ObjectRecordProblem
from klikback.core.common.solo_object_reconstruct import counter_family_payload, quick_backdrop_fill_block

COUNTER = 7

COUNTER_KIND = b"Cntr"

LIVES = 6

LIVES_KIND = b"Lves"

SCORE = 5

SCORE_KIND = b"Scrs"

DISPLAY_HIDDEN = 0

DISPLAY_NUMBERS = 1

DISPLAY_VERTICAL_BAR = 2

DISPLAY_HORIZONTAL_BAR = 3

DISPLAY_ANIMATION = 4

DISPLAY_MODES = frozenset(range(5))

LIVES_DISPLAYS = frozenset((DISPLAY_NUMBERS, DISPLAY_ANIMATION))

SCORE_DISPLAYS = frozenset((DISPLAY_NUMBERS,))

NEUTRAL_HIDDEN_DIMS = (96, 32)

DEFAULT_FILL = b"Sfll" + struct.pack("<I", 0x00808080)

FILL_SIZES = {b"Zfll": 4, b"Sfll": 8, b"Gfll": 16, b"Mfll": 8}

def counter_payload(obj: dict) -> dict:
    """A Counter's settings, as the compiled game stored them."""
    definition = obj["definition"]
    initial, minimum, maximum = struct.unpack_from("<iii", definition, 0x3E)
    if struct.unpack_from("<I", definition, 0x0C)[0] == 0:
        return {
            "initial": initial,
            "minimum": minimum,
            "maximum": maximum,
            "display": DISPLAY_HIDDEN,
            "image_ids": [],
            "width": None,
            "height": None,
            "fill": DEFAULT_FILL,
        }
    payload = counter_family_payload(definition)
    display = payload["display"]
    if display not in DISPLAY_MODES or payload["player"] != 0:
        raise ObjectRecordProblem(
            f"Counter display/player is {display}/{payload['player']}"
        )
    width = payload["width"]
    fill = DEFAULT_FILL
    if display in (DISPLAY_VERTICAL_BAR, DISPLAY_HORIZONTAL_BAR):
        if payload["bar_reverse"] not in (0, 0x0100):
            raise ObjectRecordProblem(
                f"Counter bar direction is {payload['bar_reverse']:#x}"
            )
        if payload["bar_fill"] is None:
            raise ObjectRecordProblem("bar Counter has no fill")
        if payload["bar_fill"].get("extra") != 8:
            raise ObjectRecordProblem("bar Counter fill prefix is not 8")
        width = width if payload["bar_reverse"] else -width
        fill = quick_backdrop_fill_block(payload["bar_fill"])
    return {
        "initial": initial,
        "minimum": minimum,
        "maximum": maximum,
        "display": display,
        "image_ids": payload["image_ids"],
        "width": width,
        "height": payload["height"],
        "fill": fill,
    }

def build_counter_tail(
    item_id: int,
    icon: int,
    obj: dict,
    hidden_dims: tuple[int, int] = NEUTRAL_HIDDEN_DIMS,
) -> bytes:
    """Write a Counter's settings into the project's own record shape."""
    payload = counter_payload(obj)
    width = hidden_dims[0] if payload["width"] is None else payload["width"]
    height = hidden_dims[1] if payload["height"] is None else payload["height"]
    images = b"".join(
        b"Imag" + struct.pack("<I", handle) for handle in payload["image_ids"]
    )
    return (
        struct.pack(
            "<I4sIIIII",
            item_id,
            b"icnI",
            icon,
            payload["display"],
            2,
            0,
            8,
        )
        + payload["fill"]
        + b"ImSt"
        + struct.pack("<I", len(payload["image_ids"]))
        + images
        + struct.pack("<iI", width, height)
    )

def split_counter_tail(tail: bytes) -> dict:
    """Read a Counter's settings back out of a project record."""
    if len(tail) < 52 or tail[4:8] != b"icnI":
        raise ObjectRecordProblem("Counter tail is truncated or lacks icnI")
    item_id, icon, display, a, b, extra = struct.unpack_from("<I4xIIIII", tail, 0)
    if display not in DISPLAY_MODES or (a, b, extra) != (2, 0, 8):
        raise ObjectRecordProblem(
            f"Counter display/framing is {display}/{a}/{b}/{extra}"
        )
    fill_tag = tail[28:32]
    if fill_tag not in FILL_SIZES:
        raise ObjectRecordProblem(f"Counter fill tag is {fill_tag!r}")
    pos = 28 + FILL_SIZES[fill_tag]
    if tail[pos:pos + 4] != b"ImSt":
        raise ObjectRecordProblem("Counter fill is not followed by ImSt")
    (count,) = struct.unpack_from("<I", tail, pos + 4)
    pos += 8
    images = []
    for _ in range(count):
        if tail[pos:pos + 4] != b"Imag":
            raise ObjectRecordProblem("Counter image list has a non-Imag entry")
        images.append(struct.unpack_from("<I", tail, pos + 4)[0])
        pos += 8
    if pos + 8 != len(tail):
        raise ObjectRecordProblem("Counter tail does not end after its dimensions")
    width, height = struct.unpack_from("<iI", tail, pos)
    return {
        "item_id": item_id,
        "icon": icon,
        "display": display,
        "images": images,
        "width": width,
        "height": height,
    }

def lives_payload(obj: dict) -> dict:
    """A Lives display's settings, as the compiled game stored them."""
    payload = counter_family_payload(obj["definition"])
    if payload["display"] not in LIVES_DISPLAYS:
        raise ObjectRecordProblem(f"Lives display is {payload['display']}")
    if not 1 <= payload["player"] <= 4:
        raise ObjectRecordProblem(f"Lives player is {payload['player']}")
    return payload

def build_lives_tail(item_id: int, icon: int, obj: dict) -> bytes:
    """Write a Lives display's settings into the project."""
    payload = lives_payload(obj)
    images = b"".join(
        b"Imag" + struct.pack("<I", handle) for handle in payload["image_ids"]
    )
    return (
        struct.pack("<I4sI4sI", item_id, b"icnI", icon, b"ImSt", len(payload["image_ids"]))
        + images
        + struct.pack("<II", payload["width"], payload["height"])
    )

def split_lives_tail(tail: bytes) -> dict:
    """Read a Lives display's settings back out."""
    if len(tail) < 28 or tail[4:8] != b"icnI" or tail[12:16] != b"ImSt":
        raise ObjectRecordProblem("Lives tail is truncated or has wrong tags")
    item_id, icon, count = struct.unpack_from("<I4xI4xI", tail, 0)
    pos = 20
    images = []
    for _ in range(count):
        if tail[pos:pos + 4] != b"Imag":
            raise ObjectRecordProblem("Lives image list has a non-Imag entry")
        images.append(struct.unpack_from("<I", tail, pos + 4)[0])
        pos += 8
    if pos + 8 != len(tail):
        raise ObjectRecordProblem("Lives tail does not end after its dimensions")
    width, height = struct.unpack_from("<II", tail, pos)
    return {
        "item_id": item_id,
        "icon": icon,
        "images": images,
        "width": width,
        "height": height,
    }

def score_payload(obj: dict) -> dict:
    """A Score display's settings, as the compiled game stored them."""
    payload = counter_family_payload(obj["definition"])
    if payload["display"] not in SCORE_DISPLAYS:
        raise ObjectRecordProblem(f"Score display is {payload['display']}")
    if not 1 <= payload["player"] <= 4:
        raise ObjectRecordProblem(f"Score player is {payload['player']}")
    if (payload["width"], payload["height"]) != (0, 0):
        raise ObjectRecordProblem(
            f"Score runtime dimensions are {payload['width']}x{payload['height']}"
        )
    if len(payload["image_ids"]) != 14:
        raise ObjectRecordProblem(
            f"Score numbers display has {len(payload['image_ids'])} images, not 14"
        )
    return payload

def build_score_tail(item_id: int, icon: int, obj: dict) -> bytes:
    """Write a Score display's settings into the project."""
    payload = score_payload(obj)
    images = b"".join(
        b"Imag" + struct.pack("<I", handle) for handle in payload["image_ids"]
    )
    return (
        struct.pack("<I4sI4sI", item_id, b"icnI", icon, b"ImSt", len(payload["image_ids"]))
        + images
    )

def split_score_tail(tail: bytes) -> dict:
    """Read a Score display's settings back out."""
    if len(tail) < 20 or tail[4:8] != b"icnI" or tail[12:16] != b"ImSt":
        raise ObjectRecordProblem("Score tail is truncated or has wrong tags")
    item_id, icon, count = struct.unpack_from("<I4xI4xI", tail, 0)
    pos = 20
    images = []
    for _ in range(count):
        if tail[pos:pos + 4] != b"Imag":
            raise ObjectRecordProblem("Score image list has a non-Imag entry")
        images.append(struct.unpack_from("<I", tail, pos + 4)[0])
        pos += 8
    if pos != len(tail):
        raise ObjectRecordProblem("Score tail does not end after its image list")
    return {"item_id": item_id, "icon": icon, "images": images}
