# GENERATED — do not edit by hand. This file is produced by KlikBack's
# sync tooling; changes belong in the source it is generated from.
#
# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""Records for the object types that stand alone rather than move and animate.

Counters, Formatted Text, Question & Answer and Quick Backdrops have no
movement or animation to rebuild; what they have is a payload of display
settings. Each is written into its neutral template by setting named fields.
"""

from __future__ import annotations
import struct
from klikback.core.common.blind_core_reconstruct import set_record_name, set_u32_property

def counter_family_payload(definition: bytes) -> dict:
    """That object's display settings, as the compiled game stored them."""
    payload_offset = struct.unpack_from("<I", definition, 0x0C)[0]
    width, height, mode_a, mode_b, reserved, count = struct.unpack_from(
        "<6H", definition, payload_offset + 4
    )
    image_ids = list(
        struct.unpack_from(f"<{count}H", definition, payload_offset + 16)
    )

    bar_fill = None
    if count == 0 and mode_b in (COUNTER_VERTICAL_BAR, COUNTER_HORIZONTAL_BAR):
        bar_fill = quick_backdrop_fill_payload(definition, payload_offset + 16)
    return {
        "width": width,
        "height": height,
        "mode": (mode_a, mode_b),

        "player": mode_a,

        "display": mode_b,
        "image_ids": image_ids,
        "bar_reverse": reserved,
        "bar_fill": bar_fill,
    }

def ftext_payload(definition: bytes) -> dict:
    """Its text and formatting, as the compiled game stored them."""
    payload = struct.unpack_from("<I", definition, 0x0C)[0]
    width, height = struct.unpack_from("<HH", definition, payload + 0x10)
    length = struct.unpack_from("<I", definition, payload + 0x18)[0]
    text = definition[payload + 0x1C : payload + 0x1C + length]
    if len(text) != length:
        raise ValueError(
            f"runtime RTF text is truncated: payload offset {payload} declares "
            f"{length} bytes and the definition holds {len(text)}"
        )
    return {"width": width, "height": height, "text": text}

QUICK_BACKDROP_FILL_TAGS = {0: "none", 1: "solid", 2: "gradient", 3: "motif"}

COUNTER_VERTICAL_BAR = 2

COUNTER_HORIZONTAL_BAR = 3

def quick_backdrop_fill_payload(data: bytes, offset: int) -> dict:
    """The fill a Quick Backdrop is drawn with."""
    extra = struct.unpack_from("<I", data, offset)[0]
    kind, fill_b = struct.unpack_from("<2H", data, offset + 4)
    fill = QUICK_BACKDROP_FILL_TAGS.get(fill_b)
    if fill is None:
        raise ValueError(f"unsupported fill selector {fill_b}")
    payload = {"extra": extra, "kind": kind, "fill_b": fill_b, "fill": fill}
    if fill == "solid":
        payload["colors"] = (struct.unpack_from("<I", data, offset + 8)[0],)
    elif fill == "gradient":
        color1, color2, direction = struct.unpack_from("<III", data, offset + 8)
        payload["colors"] = (color1, color2)
        payload["direction"] = direction
    elif fill == "motif":
        payload["motif_image"] = struct.unpack_from("<I", data, offset + 8)[0]
    return payload

def quick_backdrop_payload(definition: bytes) -> dict:

    """Its shape, colours and borders."""
    width, height, extra = struct.unpack_from("<3H", definition, 0x08)
    obstacle = struct.unpack_from("<I", definition, 0x0E)[0]
    kind, fill_b = struct.unpack_from("<2H", definition, 0x12)
    fill = QUICK_BACKDROP_FILL_TAGS.get(fill_b)
    if fill is None:
        raise ValueError(f"unsupported quick backdrop fill selector {fill_b}")
    payload = {
        "width": width,
        "height": height,
        "extra": extra,
        "obstacle": obstacle,
        "kind": kind,
        "fill_b": fill_b,
        "fill": fill,
    }
    if fill == "solid":
        payload["colors"] = (struct.unpack_from("<I", definition, 0x16)[0],)
    elif fill == "gradient":
        color1, color2, direction = struct.unpack_from("<III", definition, 0x16)
        payload["colors"] = (color1, color2)
        payload["direction"] = direction
    elif fill == "motif":
        payload["motif_image"] = struct.unpack_from("<I", definition, 0x16)[0]
    return payload

PROP_MARKER = b"\x01\x00\x50\x00\x00PROP"

def zero_prop_scratch(record: bytearray) -> None:
    """Clear the per-save scratch a property carries, so a rebuild is reproducible.
    """
    marker = record.index(PROP_MARKER)
    record[marker - 5 : marker - 2] = b"\x00\x00\x00"

def qanda_block_header(color: int, font: int = 0xFFFF) -> bytes:
    """The head of a Question & Answer record."""
    return (
        struct.pack("<i", -1 if font == 0xFFFF else font)
        + struct.pack("<I", color)
        + b"\x25\x00\x00\x00\x00\x00\x00\x00"
    )

def qanda_payload(definition: bytes) -> dict:
    """Its questions, answers and settings."""
    payload = struct.unpack_from("<I", definition, 0x0C)[0]
    width, height, count = struct.unpack_from("<3H", definition, payload + 4)
    offsets = struct.unpack_from(f"<{count}H", definition, payload + 10)
    strings = []
    for offset in offsets:
        pos = payload + offset
        size, font, color, kind, flag = struct.unpack_from(
            "<HHIBB", definition, pos
        )

        if kind != 5:
            raise ValueError(f"unexpected Q&A string kind {kind}")
        text = definition[pos + 10 : pos + size]
        if not text.endswith(b"\x00"):
            raise ValueError("Q&A string is not NUL-terminated")
        strings.append(
            {"text": text[:-1], "flag": flag, "color": color, "font": font}
        )
    return {"width": width, "height": height, "strings": strings}

def qanda_record(
    template: bytes,
    *,
    name: bytes,
    object_id: int,
    icon: int,
    dims: tuple[int, int],
    question: dict,
    answers: list[dict],
) -> bytes:
    """Build a Question & Answer object's record."""
    record = patch_name(bytearray(template), name)
    zero_prop_scratch(record)
    patch_frame_object_id(record, object_id)
    icn = record.index(b"icnI")

    def block(strings: list[dict]) -> bytes:
        colors = {string["color"] for string in strings}
        if len(colors) != 1:
            raise ValueError("Q&A block strings carry differing colors")
        fonts = {string.get("font", 0xFFFF) for string in strings}
        if len(fonts) != 1:
            raise ValueError("Q&A block strings carry differing fonts")
        body = qanda_block_header(colors.pop(), fonts.pop()) + struct.pack(
            "<I", len(strings)
        )
        for string in strings:
            body += (
                struct.pack("<I", len(string["text"]))
                + string["text"]
                + struct.pack("<I", string["flag"])
            )
        return body

    tail = (
        b"icnI"
        + struct.pack("<III", icon, dims[0], dims[1])
        + block([question])
        + block(answers)
    )
    return bytes(record[:icn]) + tail

def patch_name(record: bytearray, name: bytes) -> bytearray:
    """Set a record's name."""
    if not name.endswith(b"\x00"):
        raise ValueError("object name must be NUL-terminated")
    name_tag = record.index(b"ItNa")
    name_pos = name_tag + 0x24
    next_property = record.index(b"\x04\x00ItIc", name_pos)
    struct.pack_into("<H", record, name_tag + 0x1A, len(name))
    return record[:name_pos] + bytearray(name) + record[next_property:]

def patch_frame_object_id(record: bytearray, object_id: int) -> None:
    """Set which object in the frame a record is."""
    icn = record.index(b"icnI")
    if icn < 4:
        raise ValueError("icnI has no room for a frame item id before it")
    struct.pack_into("<I", record, icn - 4, object_id)

def counter_family_record(
    template: bytes,
    *,
    name: bytes,
    object_id: int,
    icon: int,
    image_ids: list[int],
    dims: tuple[int, int] | None,
    player: int | None = None,
) -> bytes:
    """Build a Counter-family object's record."""
    record = patch_name(bytearray(template), name)
    zero_prop_scratch(record)
    patch_frame_object_id(record, object_id)
    icn = record.index(b"icnI")
    struct.pack_into("<I", record, icn + 4, icon)
    image_records = b"".join(
        b"Imag" + struct.pack("<I", image_id) for image_id in image_ids
    )
    tail = b"ImSt" + struct.pack("<I", len(image_ids)) + image_records
    if dims is not None:
        tail += struct.pack("<II", *dims)
    built = bytes(record[: record.index(b"ImSt")]) + tail
    if player is not None:
        if not 1 <= player <= 4:
            raise ValueError(f"unsupported player number {player}")
        built = set_u32_property(built, b"Play", player - 1)
    return built

def ftext_record(
    template: bytes,
    *,
    name: bytes,
    object_id: int,
    icon: int,
    dims: tuple[int, int],
    text: bytes,
) -> bytes:
    """Build a Formatted Text object's record."""
    record = patch_name(bytearray(template), name)
    zero_prop_scratch(record)
    patch_frame_object_id(record, object_id)
    icn = record.index(b"icnI")
    struct.pack_into("<III", record, icn + 4, icon, dims[0], dims[1])
    length_pos = record.index(b"class CTE") + len(b"class CTE") + 4
    return (
        bytes(record[:length_pos]) + struct.pack("<I", len(text)) + text
    )

def quick_backdrop_record(
    template: bytes,
    *,
    object_id: int,
    icon: int,
    payload: dict,
    name: bytes | None = None,
) -> bytes:

    """Build a Quick Backdrop's record."""
    if name is not None:
        template = set_record_name(template, name)
    record = bytearray(template)
    zero_prop_scratch(record)
    patch_frame_object_id(record, object_id)
    icn = record.index(b"icnI")
    tail = (
        b"icnI"
        + struct.pack("<II", icon, payload["kind"])
        + struct.pack("<I", payload["extra"])
        + struct.pack("<I", payload["obstacle"])
        + quick_backdrop_fill_block(payload)
        + struct.pack("<II", payload["width"], payload["height"])
    )
    return bytes(record[:icn]) + tail

def quick_backdrop_fill_block(payload: dict) -> bytes:
    """The record holding that fill."""
    fill = payload["fill"]
    if fill == "none":
        return b"Zfll"
    if fill == "solid":
        return b"Sfll" + struct.pack("<I", payload["colors"][0])
    if fill == "gradient":
        return b"Gfll" + struct.pack(
            "<III", *payload["colors"], payload["direction"]
        )
    return b"Mfll" + struct.pack("<I", payload["motif_image"])
