# GENERATED — do not edit by hand. This file is produced by KlikBack's
# sync tooling; changes belong in the source it is generated from.
#
# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""Rebuild a whole MMF 1.0 project — every frame, every object type — from a game.

This is the 1.0 pipeline's core. "Blind" is the useful word: it works from
the compiled game alone, with no access to the project the author saved and
no editor installed. Frames, their objects, their placements and their events
are recovered from the game's own data and written into a project file.

**The base project is generated, not copied.** It is emitted from the
format's own grammar, so nothing MMF authored ships inside KlikBack and no
donor file is read while a game is being rebuilt.

Every common object type is handled: Actives with all six movement kinds,
Backdrops and Quick Backdrops, Strings, Counters, Lives, Scores, Formatted
Text and Question & Answer. Frames carry their own geometry and palettes,
including the per-frame palette variation older runtimes kept.

Object icons are **generated from each object's own recovered artwork**;
the few object families that have no art of their own carry this project's
own drawings.
"""

from __future__ import annotations
import json
import struct
from collections import Counter
from collections.abc import Callable
from pathlib import Path, PureWindowsPath
from klikback.core.common.blind_core_reconstruct import ACTIVE_OBJECT_TYPE, SCROLL_FLAGS_OFFSET, active_record, backdrop_record, parse_transition, runtime_display_values, runtime_object_transitions, runtime_qualifiers, runtime_scroll_values, set_fine_collisions, set_memory_flags, PROPERTY_HEADER_SIZE, PROPERTY_MARKER, set_obstacle, set_property_entry, set_qualifiers, set_u32_property, set_background_flags, set_blob_property, set_scroll_flags, set_transition, insert_event_data, replace_icon_bank, replace_instances, replace_objects, string_paragraphs, strip_nonmovement_default_behavior, text_record
from klikback.core.mmf1.counter_reconstruct import apply_editor_palette, counter_editor_record
from klikback.core.common.multiframe_reconstruct import decompress_chunk, find_chunk, frame_records, replace_frame_title, runtime_application
from klikback.core.common.global_event_reconstruct import build_global_event_property, global_events
from klikback.core.mmf1.active_multiframe_blind_reconstruct import frame_title
from klikback.core.common.object_reconstruct import INSTANCE_LIST, OBJECT_LIST, replace_image_bank, set_name_flag
from klikback.core.mmf1.extension_reconstruct import extension_editdata, extension_module, extension_record, is_extension_type, recovered_library_titles, set_library_table
from klikback.core.common.animation_reconstruct import IMAGE_MODE_TO_COLOR_DEPTH, rle_encode_pixels
from klikback.core.mmf1.extension_module_table import parse_module_table
from klikback.core.common.extension_inventory import PACKAGE_VERSION_MMF15, chunk_payload, frames_from, load_outer, package_version
from klikback.core.common.exe_to_cca import empty_bank_offset, extract_event_programs, icon_and_image_bank_offsets
from klikback.core.mmf1.probe import agmi_size
from klikback.core.common.pe_icon_probe import icon_dib_indices, pe_resources
from klikback.core.common.compression_probe import decompress_clickteam_stream_with_consumed, load_exe_frame
from klikback.core.common.music_reconstruct import replace_empty_music_bank, runtime_music_bank
from klikback.core.common.global_value_reconstruct import global_values_property, replace_global_values_property, runtime_global_values
from klikback.core.common.sound_reconstruct import replace_empty_sample_bank, runtime_sample_bank
from klikback.core.common.solo_object_reconstruct import counter_family_payload, counter_family_record, ftext_payload, ftext_record, patch_frame_object_id, qanda_payload, qanda_record, quick_backdrop_fill_block, quick_backdrop_payload, quick_backdrop_record
from klikback.core.common.subapplication_reconstruct import SUBAPPLICATION_TYPE, runtime_subapplication, subapplication_record
from klikback.core.common.scaffold_synthesis import WIN32_HALFTONE_PALETTE, app_icon_template_head, synthesise_scaffold
from klikback.core.mmf1.template_synthesis import synthesised_templates
from klikback.core.common.icon_generate import ACTIVE_ICON_CONTENT, BACKDROP_ICON_CONTENT, OTHER_ICON_ART, artwork_icon_record, backdrop_stub_icon, icon_from_image, imageless_icon_art, quick_backdrop_icon
from klikback.core.common.multi_animation_reconstruct import parse_runtime_animation_set

def strip_default_behavior(record: bytes) -> bytes:
    """Remove the placeholder behaviour a starting record carries.

    The base project's object arrives with an empty behaviour attached. The
    game's own behaviours are recovered separately, so the placeholder is taken
    out rather than left to appear in the editor as an event page nobody wrote.
    """
    if b"Behavior #1" not in record:
        return record
    data = bytearray(strip_nonmovement_default_behavior(record))
    count = struct.unpack_from("<I", data, 0x14)[0]
    struct.pack_into("<I", data, 0x14, count - 1)
    return bytes(data)

def counter_record(obj: dict, icon_id: int) -> bytes:
    """Build the editor record for one Counter object.

    A Counter can display as a number, as a bar or as a row of pictures, and the
    bar can fill in either direction; all of that is recovered, including the
    pictures it fills with. A Counter that displays nothing at all is a legal
    Counter and is written as one.
    """
    definition = obj["definition"]

    initial, minimum, maximum = struct.unpack_from("<iii", definition, 0x3E)

    if struct.unpack_from("<I", definition, 0x0C)[0]:
        payload = counter_family_payload(definition)
        width, height = payload["width"], payload["height"]
        image_ids = payload["image_ids"]
        display = payload["display"]
        bar_fill = payload["bar_fill"]
        if bar_fill is not None:
            if payload["bar_reverse"] not in (0, 0x0100):
                raise ValueError(
                    f"unsupported Counter bar direction {payload['bar_reverse']:#x}"
                )

            width = width if payload["bar_reverse"] else -width
    else:
        width, height, image_ids = 0, 0, []
        display = COUNTER_DISPLAY_HIDDEN
        bar_fill = None
    record = bytearray(
        counter_editor_record(
            {
                "name": obj["name"],
                "initial": initial,
                "minimum": minimum,
                "maximum": maximum,
                "width": width,
                "height": height,
                "image_ids": image_ids,
                "fill": (
                    quick_backdrop_fill_block(bar_fill)
                    if bar_fill is not None
                    else None
                ),
            }
        )
    )
    patch_frame_object_id(record, obj["object_id"])
    icon_pos = record.index(b"icnI")
    struct.pack_into("<I", record, icon_pos + 4, icon_id)
    set_counter_display(record, icon_pos, display)
    return strip_default_behavior(bytes(record))

COUNTER_DISPLAY_HIDDEN = 0

COUNTER_DISPLAY_MODES = frozenset(range(5))

def set_counter_display(record: bytearray, icon_pos: int, display: int) -> None:
    """Set how a Counter shows itself — digits, bar, pictures or nothing."""
    if display not in COUNTER_DISPLAY_MODES:
        raise ValueError(f"unsupported counter display mode {display}")
    struct.pack_into("<I", record, icon_pos + 8, display)

NEUTRAL_OBJECT_NAMES = {
    1: b"Backdrop",
    0: b"Quick Backdrop",
}

def frame_object_names(objects: list[dict]) -> list[bytes | None]:
    """Give the unnamed objects in a frame distinct names to show in the editor.

    Backdrops and Quick Backdrops are usually left unnamed by their author and
    the compiled game keeps no name for them, so numbered type names stand in and
    the editor's object list stays usable. Anything the author did name keeps its
    own name, and a stand-in never collides with one.
    """
    taken = {
        obj["name"].split(b"\x00", 1)[0]
        for obj in objects
        if obj["object_type"] not in NEUTRAL_OBJECT_NAMES
    }
    out: list[bytes | None] = []
    for obj in objects:
        base = NEUTRAL_OBJECT_NAMES.get(obj["object_type"])
        if base is None:
            out.append(None)
            continue
        name, ordinal = base, 1
        while name in taken:
            ordinal += 1
            name = base + b" " + str(ordinal).encode("ascii")
        taken.add(name)
        out.append(name + b"\x00")
    return out

def frame_item_record(
    obj: dict,
    icon_id: int,
    editor_events: list[bytes],
    templates: dict[str, bytes],
    name_cache: dict | None = None,
    synthesised_name: bytes | None = None,
) -> bytes:
    """Build the editor record for one object, whatever type it turns out to be.

    The properties an object's dialogs show — movement and ink effect, scrolling,
    display and background behaviour, colour, qualifiers, transitions — are set
    from the compiled object rather than left at the base project's defaults. Each
    is written only where the record has somewhere to put it, so an object type
    that never had a given property does not grow one.
    """
    record = _typed_frame_item_record(
        obj, icon_id, editor_events, templates, name_cache, synthesised_name
    )

    record = set_name_flag(record)
    if b"\x04\x00MFla" in record:
        record = set_memory_flags(record, obj["memory_flags"])
    scroll = runtime_scroll_values(obj["definition"])
    if scroll is not None and b"\x04\x00SFlg" in record:
        record = set_scroll_flags(record, *scroll)
    display = runtime_display_values(obj["definition"])
    if display is not None:
        if b"\x04\x00BFlg" in record:
            record = set_background_flags(
                record, display["save_background"], display["wipe_with_colour"]
            )

        if obj["object_type"] == ACTIVE_OBJECT_TYPE and b"\x04\x00CFlg" in record:
            record = set_fine_collisions(record, display["fine_collisions"])
        if b"\x04\x00Visi" in record:
            record = set_u32_property(record, b"Visi", display["visible"])
        if display["colour"] is not None and b"\x04\x00Colo" in record:
            record = set_u32_property(record, b"Colo", display["colour"])

    if b"\x04\x00Qual" in record:
        qualifiers = runtime_qualifiers(obj["definition"])
        if qualifiers:
            record = set_qualifiers(record, qualifiers)

    for tag, transition in runtime_object_transitions(obj["definition"]).items():
        if b"\x04\x00" + tag in record:
            record = set_transition(record, tag, transition)

    if (
        len(obj["definition"]) > SCROLL_FLAGS_OFFSET
        and b"\x04\x00DFlg" in record
    ):
        display_flag = bool(obj["definition"][SCROLL_FLAGS_OFFSET] & DISPLAY_PROPERTY_BIT)
        if display_flag:
            record = set_u32_property(record, b"DFlg", 1)
        elif obj["object_type"] != ACTIVE_OBJECT_TYPE:
            record = set_u32_property(record, b"DFlg", 0)

    if len(obj["header"]) >= 16:
        flags = struct.unpack_from("<H", obj["header"], INK_FLAGS_OFFSET)[0]
        if b"\x04\x00InkF" in record:
            effect = struct.unpack_from("<H", obj["header"], INK_EFFECT_OFFSET)[0]
            amount = struct.unpack_from("<I", obj["header"], INK_AMOUNT_OFFSET)[0]
            record = set_property_entry(record, b"InkF", INK_EFFECT_ENTRY, effect)
            record = set_property_entry(record, b"InkF", INK_AMOUNT_ENTRY, amount)

            if obj["object_type"] != QANDA_OBJECT_TYPE:
                record = set_property_entry(
                    record,
                    b"InkF",
                    INK_TRANSPARENT_ENTRY,
                    CHECKBOX_ON if flags & INK_TRANSPARENT_BIT else CHECKBOX_OFF,
                )
        if b"\x04\x00AntA" in record:
            record = set_u32_property(
                record,
                b"AntA",
                CHECKBOX_ON if flags & INK_ANTIALIAS_BIT else CHECKBOX_OFF,
            )
    return record

DISPLAY_PROPERTY_BIT = 0x10

INK_EFFECT_OFFSET = 8

INK_FLAGS_OFFSET = 10

INK_AMOUNT_OFFSET = 12

INK_EFFECT_ENTRY = 0x0106

INK_TRANSPARENT_ENTRY = 0x0001

INK_AMOUNT_ENTRY = 0x0208

INK_TRANSPARENT_BIT = 0x1000

INK_ANTIALIAS_BIT = 0x2000

CHECKBOX_ON = 2

CHECKBOX_OFF = 1

QANDA_OBJECT_TYPE = 4

def _typed_frame_item_record(
    obj: dict,
    icon_id: int,
    editor_events: list[bytes],
    templates: dict[str, bytes],
    name_cache: dict | None = None,
    synthesised_name: bytes | None = None,
) -> bytes:
    object_type = obj["object_type"]
    if is_extension_type(object_type):

        if "xtnd" not in templates:
            raise ValueError(
                "this application uses extension objects and the supplied "
                "templates carry no neutral Xtnd record; "
                "mmf1_template_synthesis.synthesised_templates always does"
            )
        return extension_record(
            templates["xtnd"],
            name=obj["name"],
            object_id=obj["object_id"],
            icon=icon_id,
            module=obj["module"],
            editdata=extension_editdata(obj["definition"]),
        )
    if object_type == 2:
        movement_offset = struct.unpack_from("<H", obj["definition"], 4)[0]
        template = templates["active_movement" if movement_offset else "active"]
        return active_record(template, obj, icon_id, editor_events, name_cache)
    if object_type == 1:
        return backdrop_record(
            templates["backdrop"], obj, icon_id, name=synthesised_name
        )
    if object_type == 0:

        return set_obstacle(
            quick_backdrop_record(
                templates["quickb"],
                object_id=obj["object_id"],
                icon=icon_id,
                payload=quick_backdrop_payload(obj["definition"]),
                name=synthesised_name,
            ),
            obj["definition"][4],
        )
    if object_type == 3:
        return text_record(obj, icon_id)
    if object_type in (5, 6):
        payload = counter_family_payload(obj["definition"])
        return counter_family_record(
            templates["lives" if object_type == 6 else "score"],
            name=obj["name"],
            object_id=obj["object_id"],
            icon=icon_id,
            image_ids=payload["image_ids"],
            dims=(payload["width"], payload["height"])
            if object_type == 6
            else None,
            player=payload["player"],
        )
    if object_type == 7:
        return counter_record(obj, icon_id)
    if object_type == 8:
        payload = ftext_payload(obj["definition"])
        return ftext_record(
            templates["ftext"],
            name=obj["name"],
            object_id=obj["object_id"],
            icon=icon_id,
            dims=(payload["width"], payload["height"]),
            text=payload["text"],
        )
    if object_type == 4:
        payload = qanda_payload(obj["definition"])
        return qanda_record(
            templates["qanda"],
            name=obj["name"],
            object_id=obj["object_id"],
            icon=icon_id,
            dims=(payload["width"], payload["height"]),
            question=payload["strings"][0],
            answers=payload["strings"][1:],
        )
    if object_type == SUBAPPLICATION_TYPE:
        if "subapp" not in templates:
            raise ValueError(
                "this application uses Sub-Application objects and the "
                "supplied templates carry no neutral CCAx record; "
                "mmf1_template_synthesis.synthesised_templates always does"
            )
        return subapplication_record(
            templates["subapp"],
            name=obj["name"],
            object_id=obj["object_id"],
            icon=icon_id,
            runtime=runtime_subapplication(obj["definition"]),
            editor_path=obj.get("subapplication_editor_path"),
        )
    raise ValueError(f"unsupported object type {object_type}")

def set_frame_title(frame: bytes, old_title: bytes, new_name: bytes) -> bytes:

    """Write the name the editor shows on a frame's tab."""
    return replace_frame_title(frame, old_title, new_name or b"\x00")

def set_frame_palette(frame: bytes, runtime_palette: bytes) -> bytes:
    """Give a frame its own 256 colours.

    Older runtimes let each frame carry a palette of its own, so this is per
    frame rather than per project — a rebuilt game that shared one palette across
    frames would render several of them wrong.
    """
    if len(runtime_palette) != 0x400:
        raise ValueError("runtime frame palette must be 256 4-byte entries")
    data = bytearray(frame)
    pltt = frame.index(b"Pltt")
    count = struct.unpack_from("<I", frame, pltt + 4)[0]
    if count != 256:
        raise ValueError(f"unexpected Pltt colour count {count}")
    data[pltt + 8 : pltt + 8 + 0x400] = runtime_palette
    return bytes(data)

FRAME_FLAG_BITS_TO_PFOP = {
    0x0001: 0x08,
    0x0002: 0x01,
    0x0004: 0x02,
    0x0020: 0x04,
    0x0100: 0x10,
}

KNOWN_FRAME_FLAG_MASK = 0x0167

def frame_flags_to_pfop(frame_flags: int) -> int:
    """Translate a frame's runtime options into the form the editor stores.

    A flag this does not recognise stops the rebuild rather than being dropped:
    an unmapped option is a frame setting that would silently come back wrong.
    """
    unknown = frame_flags & ~KNOWN_FRAME_FLAG_MASK
    if unknown:
        raise ValueError(
            f"unmapped runtime frame flags 0x{unknown:04x} "
            f"(full word 0x{frame_flags:04x})"
        )
    pfop = 0
    for bit, value in FRAME_FLAG_BITS_TO_PFOP.items():
        if frame_flags & bit:
            pfop |= value
    return pfop

def _set_default_frame_prop(frame: bytes, tag: bytes, value: bytes) -> bytes:
    prefix = b"\x04\x00" + tag + b"\x01\x00\x00\x00\x01\x00\x00\x00"
    idx = frame.index(prefix)
    id_off = idx + len(prefix)
    flag_off = id_off + 2
    if frame[flag_off : flag_off + 2] != b"\xff\xff":
        raise ValueError(f"frame property {tag!r} is not in scaffold default form")
    tail = flag_off + 2 + 8
    explicit = (
        prefix
        + frame[id_off : id_off + 2]
        + b"\x00\x00"
        + b"\x01\x00\x00\x00\x01\x00\x00\x00"
        + value
    )
    return frame[:idx] + explicit + frame[tail:]

DEFAULT_RUNTIME_OBJECT_COUNT = 300

def set_frame_object_count(frame: bytes, count: int) -> bytes:
    """Set how many objects a frame may hold at once."""
    marker = b"\x03\x00NbO"
    start = frame.index(marker)
    prefix_len = 13
    first_flag = start + prefix_len + 2
    second_flag = first_flag + 2 + 8 + 2
    end = second_flag + 2 + 8
    if (
        frame[first_flag : first_flag + 2] != b"\xff\xff"
        or frame[second_flag : second_flag + 2] != b"\xff\xff"
    ):
        raise ValueError("frame NbO is not in scaffold default (inheriting) form")
    data = bytearray(frame[:end])
    data[first_flag : first_flag + 2] = b"\x00\x00"
    data[second_flag : second_flag + 2] = b"\x00\x00"
    return bytes(data) + struct.pack("<I", count) + frame[end:]

PASSWORD_PROPERTY = b"\x04\x00Pass"

PASSWORD_MARKER_ENTRY_ID = 0x0004

PASSWORD_TEXT_ENTRY_ID = 0x0103

PROPERTY_ENTRY_SIZE = 12

PROPERTY_ENTRY_INHERITED = 0xFFFF

def set_frame_password(frame: bytes, password: bytes) -> bytes:
    """Put a frame's password back.

    A frame password survives compilation intact, so it is restored rather than
    reconstructed, and a password that is not one clean string is refused rather
    than written half-formed.
    """
    if not password:
        return frame
    if password.count(b"\x00") != 1 or not password.endswith(b"\x00"):
        raise ValueError(f"frame password {password!r} is not one NUL-terminated string")
    start = frame.index(PASSWORD_PROPERTY)
    count = struct.unpack_from("<I", frame, start + 10)[0]
    if count != 2:
        raise ValueError(f"frame Pass property has {count} entries, expected 2")
    marker = start + 14
    text = marker + PROPERTY_ENTRY_SIZE
    marker_id, marker_length = struct.unpack_from("<HH", frame, marker)
    text_id, text_length = struct.unpack_from("<HH", frame, text)
    if (marker_id, text_id) != (PASSWORD_MARKER_ENTRY_ID, PASSWORD_TEXT_ENTRY_ID):
        raise ValueError(
            f"frame Pass entries are 0x{marker_id:04X}/0x{text_id:04X}, "
            f"expected 0x0004/0x0103"
        )
    if (marker_length, text_length) != (
        PROPERTY_ENTRY_INHERITED,
        PROPERTY_ENTRY_INHERITED,
    ):
        raise ValueError("frame Pass is not in scaffold default (inheriting) form")
    end = text + PROPERTY_ENTRY_SIZE
    return (
        frame[:text]
        + struct.pack("<HH", text_id, len(password))
        + frame[text + 4 : end]
        + password
        + frame[end:]
    )

def set_frame_geometry(
    frame: bytes, width: int, height: int, bg_color: int, frame_flags: int
) -> bytes:
    """Write a frame's size, background colour and its own options."""
    pfop = frame_flags_to_pfop(frame_flags)
    frame = _set_default_frame_prop(frame, b"PfSz", struct.pack("<HH", width, height))
    frame = _set_default_frame_prop(frame, b"Colo", struct.pack("<I", bg_color))
    frame = _set_default_frame_prop(frame, b"PfOp", struct.pack("<I", pfop))
    return frame

def set_app_window_size(cca: bytes, width: int, height: int) -> bytes:
    """Write the application's window size."""
    return _set_default_frame_prop(cca, b"WinS", struct.pack("<HH", width, height))

APP_COLOR_MODE_FROM_RUNTIME = IMAGE_MODE_TO_COLOR_DEPTH

PLAYER_SETTINGS_OFFSET = 0x14

PLAYER_SETTINGS_SIZE = 0x38

def set_app_players(cca: bytes, header: bytes) -> bytes:
    """Restore the player and control settings the game was built with."""
    if len(header) < PLAYER_SETTINGS_OFFSET + PLAYER_SETTINGS_SIZE:
        return cca
    payload = header[
        PLAYER_SETTINGS_OFFSET : PLAYER_SETTINGS_OFFSET + PLAYER_SETTINGS_SIZE
    ]
    position = cca.index(PROPERTY_MARKER + b"Plas")
    length = struct.unpack_from("<H", cca, position + 16)[0]
    if length != PLAYER_SETTINGS_SIZE:
        raise ValueError(
            f"Plas property holds {length} bytes, expected {PLAYER_SETTINGS_SIZE}"
        )
    start = position + PROPERTY_HEADER_SIZE + 4
    return cca[:start] + payload + cca[start + PLAYER_SETTINGS_SIZE :]

def set_app_color_mode(cca: bytes, runtime_mode: int) -> bytes:
    """Write the colour depth the project works in, taken from the game's own.
    """
    color_mode = APP_COLOR_MODE_FROM_RUNTIME.get(runtime_mode)
    if color_mode is None:
        raise ValueError(f"unsupported runtime graphic mode {runtime_mode}")
    return set_u32_property(cca, b"AppM", color_mode)

PLAYER_VALUE_INNER_ID = 0x011E

PLAYER_VALUE_HEADER = 26

def set_player_value(cca: bytes, tag: bytes, value: int) -> bytes:
    """Write a starting score or starting lives."""
    start = cca.index(b"\x04\x00" + tag)
    inner = start + PLAYER_VALUE_HEADER
    inner_id, inner_flag = struct.unpack_from("<HH", cca, inner)
    if inner_id != PLAYER_VALUE_INNER_ID:
        raise ValueError(f"{tag!r} does not nest the player-value block")
    end = inner + 12 + (0 if inner_flag == 0xFFFF else 4)
    return (
        cca[:inner]
        + struct.pack("<HH", inner_id, 0)
        + cca[inner + 4 : inner + 12]
        + struct.pack("<I", value)
        + cca[end:]
    )

WINDOW_OPTION_RUNTIME_BITS = {
    0x01: 9,
    0x02: 4,
    0x04: 11,
    0x08: 12,
    0x100: 20,
    0x200: 21,
    0x400: 22,
    0x800: 23,
}

HEADING = 0x10

MENU_BAR = 0x40

MENU_ON_BOOT = 0x80

WINDOW_MENU_BITS = (1, 7, 8)

def runtime_window_options(app_flags: int) -> int:
    """Translate the game's window flags into the editor's window options.

    The menu-related flags do not map one-for-one, and where the compiled
    combination is not one the editor can express, the safest reading is taken
    rather than a partial one invented.
    """
    options = 0
    for option, bit in WINDOW_OPTION_RUNTIME_BITS.items():
        if app_flags >> bit & 1:
            options |= option

    bit1, bit7, bit8 = (app_flags >> bit & 1 for bit in WINDOW_MENU_BITS)
    if bit1 ^ bit7 ^ bit8 != 1:

        return options | HEADING | MENU_BAR | MENU_ON_BOOT

    options |= HEADING
    if not bit7:
        options |= MENU_BAR
    if bit8:
        options |= MENU_ON_BOOT
    return options

RUN_OPTION_RUNTIME_BITS = {
    0x01: 10,
    0x02: 3,
    0x04: 16,
    0x08: 19,
}

def runtime_run_options(app_flags: int) -> int:
    """Translate the game's run flags into the editor's run options."""
    return sum(
        option
        for option, bit in RUN_OPTION_RUNTIME_BITS.items()
        if app_flags >> bit & 1
    )

def set_frame_item_id(frame: bytes, item_id: int) -> bytes:
    """Give a frame the id the rest of the project refers to it by."""
    data = bytearray(frame)
    struct.pack_into("<I", data, frame.index(b"Pltt") - 4, item_id)
    return bytes(data)

def frame_jump_targets(outer) -> set[int]:
    """Every frame an event anywhere in the game can jump to.

    Read before the frames are numbered, because a jump names its destination by
    an id the rebuilt project has to reproduce: get those wrong and the game
    still runs, but goes to the wrong place.
    """
    targets: set[int] = set()
    for frame in frames_from(outer):
        chunk = find_chunk(frame, 0x333D)
        if chunk is None:
            continue
        try:
            programs = extract_event_programs(chunk_payload(chunk))
        except Exception:
            continue
        for program in programs:
            for event in program:
                targets.update(_jump_targets_in_event(event))
    return targets

def _jump_targets_in_event(event: bytes) -> list[int]:
    found: list[int] = []
    if len(event) < 0x0E:
        return found
    pos = 0x0E
    for _ in range(event[2]):
        if pos + 2 > len(event):
            return found
        size = struct.unpack_from("<H", event, pos)[0]
        if size < 0x0E or pos + size > len(event):
            return found
        pos += size
    for _ in range(event[3]):
        if pos + 12 > len(event):
            return found
        size = struct.unpack_from("<H", event, pos)[0]
        end = pos + size
        if size < 0x0C or end > len(event):
            return found
        object_type = event[pos + 2]
        parameter_pos = pos + 12
        for _ in range(event[pos + 10]):
            if parameter_pos + 4 > end:
                break
            p_size, p_type = struct.unpack_from("<HH", event, parameter_pos)
            p_end = parameter_pos + p_size
            if p_size < 4 or p_end > end:
                break
            if object_type == 0xFD and p_type == 26 and p_size >= 6:
                found.append(
                    struct.unpack_from("<H", event, parameter_pos + 4)[0]
                )
            parameter_pos = p_end
        pos = end
    return found

def frame_item_target_map(outer, frame_item_ids: list[int]) -> dict[int, int]:
    """Where each frame-change action actually leads, once ids are resolved."""
    chunk = find_chunk(outer, 0x222B)
    if chunk is None:
        return {}
    payload = decompress_chunk(chunk)
    table = list(struct.unpack_from("<" + "H" * (len(payload) // 2), payload))
    mapping: dict[int, int] = {}
    for target in frame_jump_targets(outer):
        if target >= len(table):
            continue
        ordinal = table[target]
        if 0 <= ordinal < len(frame_item_ids):
            mapping[target] = frame_item_ids[ordinal]
    return mapping

def recover_frame_item_ids(
    outer, frame_count: int, notes: list | None = None
) -> list[int]:
    """Work out which frame each object belongs to, and under which id.

    Membership is not stated outright in a compiled game; it is recovered from
    placements, event references and parent links. Ids that cannot be resolved
    are reported rather than guessed, because a wrong id silently attaches an
    object to the wrong frame.
    """
    chunk = find_chunk(outer, 0x222B)
    if chunk is None:

        return list(range(frame_count))
    payload = decompress_chunk(chunk)
    table = list(struct.unpack_from("<" + "H" * (len(payload) // 2), payload))

    targets: set[int] | None = None
    item_ids: list[int] = []
    unresolved: list[tuple[int, list[int], int]] = []
    for ordinal in range(frame_count):
        candidates = [i for i, value in enumerate(table) if value == ordinal]
        if len(candidates) == 1:
            item_ids.append(candidates[0])
            continue
        if not candidates:
            raise ValueError(
                f"frame ordinal {ordinal} has no item id in chunk 0x222B"
            )

        if targets is None:
            targets = frame_jump_targets(outer)
        referenced = [c for c in candidates if c in targets]
        if len(referenced) == 1:
            item_ids.append(referenced[0])
        elif referenced:

            item_ids.append(referenced[0])
            unresolved.append(
                {
                    "frame_ordinal": ordinal,
                    "candidates": candidates,
                    "targeted_by": referenced,
                    "chosen": referenced[0],
                    "reason": "several stale jump targets resolve to this "
                    "frame; all are remapped to the chosen id",
                }
            )
        else:

            item_ids.append(candidates[0])
            unresolved.append(
                {
                    "frame_ordinal": ordinal,
                    "candidates": candidates,
                    "chosen": candidates[0],
                    "reason": "deleted frames zeroed their slots; "
                    "no frame jump targets this frame",
                }
            )
    if unresolved and notes is not None:
        notes.extend(unresolved)
    return item_ids

def reconstruct_frame(
    neutral_frame: bytes,
    old_title: bytes,
    frame_index: int,
    runtime_frame_data: dict,
    objects_by_id: dict[int, dict],
    templates: dict[str, bytes],
    item_id: int | None = None,
) -> bytes:
    """Build one frame: geometry, palette, objects, placements and events.

    A neutral frame goes in and a filled one comes out, a field at a time. Title,
    palette, size, background colour and flags all come straight off the compiled
    frame. So does the frame password — it is genuinely *recovered* rather than
    stood in for, because both the compiled and the editor form store the same
    plain text, so a password survives compilation whole.

    Two settings are deliberately left alone when the compiled value says nothing.
    "How many objects at runtime" is only written back when the author changed it,
    since the default reads as zero rather than as a count, and writing a literal
    zero would replace an inherited default with a stated one.

    Backdrop and Quick Backdrop display names are a compile-time loss, so the
    editor's own default naming is reproduced instead — Backdrop, Backdrop 2, and
    so on — and made unique against whatever names did survive in that frame.

    The renumbering is the part worth knowing about. Object ids in a compiled game
    are global to the whole application; in the editor they are local to the
    frame. Every record and every placement is rewritten into the frame's own
    numbering as it is built.

    Placements belonging to an object that turned out not to be a frame member are
    dropped **by name**, from the list the registry returns, rather than by
    noticing they have no local id. The difference matters: the missing-id case is
    also what a genuine reader fault looks like, and it should stop the rebuild
    rather than quietly produce a frame with fewer things in it than the game had.

    A frame with no items and no events at all omits the event structures
    entirely, because that is what the editor writes for one.
    """
    frame = set_frame_title(
        neutral_frame, old_title, runtime_frame_data["name"]
    )
    frame = set_frame_item_id(
        frame, frame_index if item_id is None else item_id
    )
    frame = set_frame_palette(frame, runtime_frame_data["palette"])
    frame = set_frame_geometry(
        frame,
        runtime_frame_data["width"],
        runtime_frame_data["height"],
        runtime_frame_data["bg_color"],
        runtime_frame_data["frame_flags"],
    )

    frame = set_frame_password(frame, runtime_frame_data.get("password") or b"")

    runtime_object_count = runtime_frame_data.get("runtime_object_count", 0)
    if runtime_object_count not in (0, DEFAULT_RUNTIME_OBJECT_COUNT):
        frame = set_frame_object_count(frame, runtime_object_count)

    for tag, block in runtime_frame_data.get("transitions", {}).items():
        frame = set_transition(frame, tag, parse_transition(block, 0))
    registry = runtime_frame_data["registry"]
    local_id_for = registry["local_item_for"]
    local_objects = [
        dict(objects_by_id[runtime_id], object_id=local_id_for[runtime_id])
        for runtime_id in registry["frame_item_object_ids"]
    ]

    synthesised_names = frame_object_names(local_objects)
    records = []

    name_cache: dict = {}
    for runtime_id, local_object, synthesised_name in zip(
        registry["frame_item_object_ids"], local_objects, synthesised_names
    ):
        records.append(
            frame_item_record(
                local_object,
                icon_id=2 + runtime_id,
                editor_events=runtime_frame_data["events"],
                templates=templates,
                name_cache=name_cache,
                synthesised_name=synthesised_name,
            )
        )

    frame = replace_objects(frame, records)

    orphans = set(registry["placeholder_only_orphans"])
    local_placements = [
        (instance_id, x, y, local_id_for[object_id], runtime_link)
        for instance_id, x, y, object_id, runtime_link
        in runtime_frame_data["placements_with_links"]
        if object_id not in orphans
    ]
    frame = replace_instances(
        frame,
        local_placements,
        {obj["object_id"]: obj["object_type"] for obj in local_objects},
        app_to_local_item=local_id_for,
        dangling_shoot_parents=registry["dangling_shoot_parents"],
    )
    local_placeholders = {
        local_id_for[object_id]: instance_id
        for object_id, instance_id
        in registry["placeholder_instance_for"].items()
    }
    if not runtime_frame_data["events"] and not local_objects:

        insertion = frame.index(b"evpg") + 8
        return frame[:insertion] + frame[frame.index(b"EvEd", insertion):]
    return insert_event_data(
        frame,
        runtime_frame_data["events"],
        local_objects,
        placeholder_instance_for=local_placeholders,
        qualifier_words=registry["qualifier_words"],
        remarks=runtime_frame_data.get("remarks"),
    )

def first_animation_image_id(definition: bytes) -> int | None:
    """The first picture an Active actually shows — what its icon is drawn from.
    """
    animation_offset = struct.unpack_from("<H", definition, 6)[0]
    if not 8 <= animation_offset < len(definition):
        return None
    animations = parse_runtime_animation_set(
        b"\x00" * 60 + definition[animation_offset:]
    )
    for animation in animations:
        for direction in animation["directions"]:
            if direction["image_ids"]:
                return direction["image_ids"][0]
    return None

def generated_object_icon(
    obj: dict,
    images_by_id: dict[int, bytes],
    palette: bytes,
    handle: int,
    fallbacks: list,
) -> bytes:
    """Draw an object's editor icon from that object's own artwork."""
    object_type = obj["object_type"]
    if object_type in (0, 1, 2):
        try:
            if object_type == 2:
                record = images_by_id.get(first_animation_image_id(obj["definition"]))
                if record is None:
                    raise ValueError("no animation image to derive the icon from")
                return icon_from_image(record, palette, handle, ACTIVE_ICON_CONTENT)
            if object_type == 1:
                record = images_by_id.get(obj["image_id"])
                if record is None:
                    return backdrop_stub_icon(handle)
                return icon_from_image(record, palette, handle, BACKDROP_ICON_CONTENT)
            return quick_backdrop_icon(
                quick_backdrop_payload(obj["definition"]), palette, handle,
                images_by_id,
            )
        except (ValueError, struct.error) as problem:
            fallbacks.append(
                {
                    "object_id": obj["object_id"],
                    "object_type": object_type,
                    "reason": str(problem),
                }
            )
        return artwork_icon_record(OTHER_ICON_ART, handle)
    return artwork_icon_record(imageless_icon_art(object_type), handle)

ARIAL_LOGFONT_HEADER = (
    struct.pack("<IIHHH", 0, 0, 0, 1, 3)
    + struct.pack("<5h", -13, 0, 0, 0, 400)
    + bytes((0, 0, 0, 0, 3, 2, 1, 0x22))
)

FONT_DESCRIPTOR = (
    ARIAL_LOGFONT_HEADER
    + b"Arial\x00".ljust(32, b"\x00")
    + b"Regular\x00".ljust(32, b"\x00")
    + b"\x00\x00"
)

def runtime_font_bank(exe_path: Path) -> list[tuple[int, bytes]]:
    """The fonts the game used, rebuilt as the project's font bank."""
    outer, _first_frame = load_exe_frame(exe_path)
    chunks = [chunk for chunk in outer if chunk.chunk_id == 0x6667]
    if not chunks:
        return []
    data = decompress_chunk(chunks[0])
    count = struct.unpack_from("<I", data, 0)[0]
    fonts: list[tuple[int, bytes]] = []
    pos = 4
    for index in range(count):
        if pos + 8 > len(data):
            raise ValueError(f"truncated font header at index {index}")
        handle, size = struct.unpack_from("<II", data, pos)
        descriptor, consumed = decompress_clickteam_stream_with_consumed(
            data[pos + 8:]
        )
        if len(descriptor) != size:
            raise ValueError(
                f"font {index} decoded {len(descriptor)} bytes, expected {size}"
            )
        fonts.append((handle, bytes(descriptor)))
        pos += 8 + consumed
    if pos != len(data):
        raise ValueError(f"font bank has {len(data) - pos} trailing bytes")
    return fonts

def build_atnf_bank(fonts: list[tuple[int, bytes]]) -> bytes:
    """Pack the recovered fonts into the bank the project stores them in."""
    if not fonts:
        return b"ATNF" + struct.pack("<I", 0)
    return (
        b"ATNF"
        + struct.pack("<I", len(fonts))
        + b"".join(
            struct.pack("<I", handle) + descriptor for handle, descriptor in fonts
        )
    )

def replace_atnf_bank(cca: bytes, fonts: list[tuple[int, bytes]]) -> bytes:
    """Put the recovered font bank into the project in place of the empty one.
    """
    start = empty_bank_offset(cca, b"ATNF")
    return cca[:start] + build_atnf_bank(fonts) + cca[start + 8 :]

def referenced_font_handles(objects: list[dict]) -> list[int]:
    """Which fonts the objects in this game actually ask for.

    Only the fonts something uses are carried over, so a rebuilt project's font
    list describes the game rather than the machine it was compiled on.
    """
    handles: set[int] = set()
    for obj in objects:
        if obj["object_type"] == 3:
            _w, _h, _texts, font, _color, _reserved = string_paragraphs(
                obj["definition"]
            )
            if font != 0xFFFF:
                handles.add(font)
        elif obj["object_type"] == QANDA_OBJECT_TYPE:
            for string in qanda_payload(obj["definition"])["strings"]:
                if string["font"] != 0xFFFF:
                    handles.add(string["font"])
    return sorted(handles)

def runtime_extension_modules(exe_path: Path) -> list:
    """The extension modules the game carries, with the titles they declare."""
    chunk = next(
        (c for c in load_outer(exe_path) if c.chunk_id == 0x2228), None
    )
    if chunk is None:
        return []
    return parse_module_table(chunk_payload(chunk))[0]

def set_application_about(cca: bytes, name: bytes, author: bytes) -> bytes:
    """Write the application's name and author."""
    name = name.split(b"\x00", 1)[0] + b"\x00"
    author = author.split(b"\x00", 1)[0] + b"\x00"
    has_author = author != b"\x00"

    def entry(entry_id: int, flag: int, payload: bytes = b"") -> bytes:
        return struct.pack("<HHII", entry_id, flag, 1, 1) + payload

    about = (
        b"\x04\x00Abou"
        + struct.pack("<II", 1, 4)
        + entry(0x0004, 0 if has_author else 0xFFFF)
        + entry(0x0103, len(name), name)
        + entry(0x0204, 0 if has_author else 0xFFFF)
        + (
            entry(0x0303, len(author), author)
            if has_author
            else entry(0x0303, 0xFFFF)
        )
    )
    start = cca.index(b"\x04\x00Abou")
    end = cca.index(b"\x04\x00Hlpf", start)
    return cca[:start] + about + cca[end:]

def make_application_icon_flags_explicit(cca: bytes) -> bytes:
    """Say outright that the project's application icons are its own."""
    start = cca.index(b"\x04\x00AppI")
    end = cca.index(b"\x04\x00Abou", start)
    prop = bytearray(cca[start:end])
    if len(prop) != 14 + 4 * 12:
        raise ValueError("unexpected AppI property layout")
    for entry_index in (0, 2):
        struct.pack_into("<H", prop, 14 + entry_index * 12 + 2, 0)
    return cca[:start] + bytes(prop) + cca[end:]

def application_icon_records(exe_path: Path) -> list[bytes]:
    """The game's own Windows icons, rebuilt as the project's application icons.

    Windows icons and editor images are both indexed pictures with a palette, so
    this is a translation rather than a redraw: every colour in the icon is looked
    up in the editor's own palette and the pixels are rewritten as indices into
    that. A colour with no match stops the conversion by name rather than being
    approximated, because a silently nearest-colour icon is a wrong icon nobody
    will think to question.

    Transparency is where the two formats genuinely disagree. The editor treats
    palette index 0 as transparent; a Windows icon keeps transparency in a separate
    mask, which leaves it free to use colour 0 for *opaque black*. Taken literally,
    every black pixel in an icon would come out see-through. So the mask decides,
    and an opaque pixel that would land on index 0 is moved to the nearest very
    dark shade instead — which is what the editor's own saved files do, and it
    compiles back to black.

    A source with no Windows resources at all returns nothing rather than failing.
    A compiled package with no executable wrapper around it has no icon to recover,
    and keeping the base project's default is the right answer there.

    The record heads and the palette are written out from named values here, so the
    only thing in the result that comes from anywhere is the game's own pixels.
    """
    try:
        resources = [
            resource
            for resource in pe_resources(exe_path)
            if resource.type_id == 3
        ]
    except ValueError:
        if exe_path.read_bytes().startswith(b"PAME"):
            return []
        raise
    dibs = [icon_dib_indices(resource.data) for resource in resources]
    by_size = {
        (width, height): (indices, mask, palette)
        for width, height, indices, mask, palette in dibs
    }
    if (32, 32) not in by_size or (16, 16) not in by_size:
        raise ValueError("executable does not carry both 32x32 and 16x16 icons")

    editor_colors = [
        WIN32_HALFTONE_PALETTE[pos : pos + 3]
        for pos in range(0, len(WIN32_HALFTONE_PALETTE), 4)
    ]
    by_template_size = {
        size: app_icon_template_head(*size) for size in ((32, 32), (16, 16))
    }
    records: list[bytes] = []
    for handle, size in enumerate(((32, 32), (16, 16))):
        indices, mask, dib_palette = by_size[size]
        dib_colors = [
            dib_palette[pos : pos + 3][::-1] for pos in range(0, len(dib_palette), 4)
        ]
        color_map: list[int] = []
        for color in dib_colors:
            try:
                color_map.append(editor_colors.index(color))
            except ValueError as error:
                raise ValueError(
                    f"Windows icon colour {color.hex()} is absent from editor palette"
                ) from error

        opaque_black = min(
            range(1, len(editor_colors)), key=lambda index: sum(editor_colors[index])
        )
        width, height = size
        mask_stride = len(mask) // height
        pixels = []
        for position, dib_index in enumerate(indices):
            row, column = divmod(position, width)
            transparent = (
                mask[row * mask_stride + column // 8] >> (7 - column % 8)
            ) & 1
            editor_index = color_map[dib_index]
            if transparent:
                editor_index = 0
            elif editor_index == 0:
                editor_index = opaque_black
            pixels.append(bytes((editor_index,)))
        encoded = rle_encode_pixels(pixels)
        record = bytearray(by_template_size[size][:0x1C])
        struct.pack_into("<I", record, 0, handle)
        struct.pack_into("<I", record, 0x0A, len(encoded))
        record.extend(encoded)
        records.append(bytes(record))
    return records

def refuse_wrong_package_version(exe_path: Path) -> None:
    """Stop rather than rebuild a package this pipeline does not handle."""
    version = package_version(exe_path)
    if version == PACKAGE_VERSION_MMF15:
        raise ValueError(
            f"this is an MMF 1.5 package (PAME version 0x0301), not a 1.0 one "
            f"-- its extension table is at 0x2234 rather than 0x2228 and its "
            f"records differ throughout. Use the 1.5 pipeline: "
            f'py -3 tools/mmf_decompile.py "{exe_path}"'
        )

def reconstruct(
    exe_path: Path,
    *,
    allow_unreadable_events: bool = False,
    extension_dirs: list[Path] | None = None,
    recover_comments: bool = False,

    progress: Callable[..., None] | None = None,
) -> tuple[bytes, dict]:

    """Rebuild the project and return its bytes.

    The entry point: recover the frames, build the records, assemble the
    container. The optional progress callback is a pure observer, called per
    frame, and cannot change what is built.
    """
    repaired_event_reference_types: list = []
    repaired_parameter_sizes: list = []
    salvaged_music_records: list = []
    synthesised_library_titles: list = []
    unplaced_placeholders: list = []
    dangling_shoot_parents: list = []
    recovered_comments: list = []
    group_close_repairs: list = []
    refuse_wrong_package_version(exe_path)

    outer_for_frames = load_outer(exe_path)
    frame_count_for_ids = len(list(frames_from(outer_for_frames)))
    unresolved_item_ids: list = []
    frame_item_ids = recover_frame_item_ids(
        outer_for_frames, frame_count_for_ids, notes=unresolved_item_ids
    )
    frame_target_map = frame_item_target_map(outer_for_frames, frame_item_ids)
    recovered_global_events: list = []
    unreadable_events: list | None = [] if allow_unreadable_events else None
    if progress is not None:
        progress("events")
    frames, objects, images = runtime_application(
        exe_path,
        type_repairs=repaired_event_reference_types,
        frame_target_map=frame_target_map,
        global_events=recovered_global_events,
        unreadable_events=unreadable_events,
        size_repairs=repaired_parameter_sizes,
        unplaced_placeholders=unplaced_placeholders,
        dangling_shoot_parents=dangling_shoot_parents,

        group_close_repairs=group_close_repairs,

        label_flattened_seams=True,

        recover_comments=recover_comments,
        recovered_comments=recovered_comments,
    )
    global_event_sheet = recovered_global_events[0]
    if not frames:
        raise ValueError("runtime application has no frames")

    if any(
        not (0 < frame["width"] <= 0xFFFF and 0 < frame["height"] <= 0xFFFF)
        for frame in frames
    ):
        raise ValueError("frame dimensions must fit the u16 playfield fields")

    for obj in objects:
        if obj["object_type"] != SUBAPPLICATION_TYPE:
            continue
        payload = runtime_subapplication(obj["definition"])
        if not payload.path:
            continue
        child_name = PureWindowsPath(payload.path.decode("latin-1")).name
        companion = (exe_path.parent / child_name).resolve()
        if companion.is_file():
            obj["subapplication_editor_path"] = str(companion).encode("latin-1")

    modules = runtime_extension_modules(exe_path)
    for obj in objects:
        if is_extension_type(obj["object_type"]):
            obj["module"] = extension_module(modules, obj["object_type"])

    if progress is not None:
        progress("banks")

    cca = synthesise_scaffold()
    if modules:
        cca = set_library_table(
            cca,
            modules,
            recovered_library_titles(exe_path, extension_dirs),
            synthesised_library_titles,
        )
    cca = replace_image_bank(cca, images)
    icons = application_icon_records(exe_path)

    images_by_id = dict(images)
    project_palette = frames[0]["palette"]
    generated_icon_fallbacks: list = []
    for obj in objects:
        icons.append(
            generated_object_icon(
                obj,
                images_by_id,
                project_palette,
                2 + obj["object_id"],
                generated_icon_fallbacks,
            )
        )
    cca = replace_icon_bank(cca, icons)

    icons_by_handle = {
        struct.unpack_from("<I", record, 0)[0]: record[4:] for record in icons
    }
    cca = make_application_icon_flags_explicit(cca)

    cca = apply_editor_palette(cca, frames[0]["palette"])

    outer, _first_frame = load_exe_frame(exe_path)

    if any(chunk.chunk_id == 0x6669 for chunk in outer):

        music_bank, _music_events = runtime_music_bank(
            exe_path, salvage=True, salvaged=salvaged_music_records
        )
        cca = replace_empty_music_bank(cca, music_bank)

    if any(chunk.chunk_id == 0x6668 for chunk in outer):
        sample_bank, _sample_events = runtime_sample_bank(exe_path)
        cca = replace_empty_sample_bank(cca, sample_bank)

    fonts = runtime_font_bank(exe_path)
    carried = {handle for handle, _descriptor in fonts}
    for handle in referenced_font_handles(objects):
        if handle not in carried:
            fonts.append((handle, FONT_DESCRIPTOR))
    cca = replace_atnf_bank(cca, sorted(fonts))

    global_values = []
    if any(chunk.chunk_id == 0x2232 for chunk in outer):
        global_values, _global_events = runtime_global_values(exe_path)
    if global_values:
        if len(global_values) > 26:
            raise ValueError("more than 26 Global Values are not supported")
        global_names = [
            f"Global Value {chr(ord('A') + index)}".encode("latin-1")
            for index in range(len(global_values))
        ]
        cca = replace_global_values_property(
            cca, global_values_property(global_names, global_values)
        )

    menu_chunk = next((c for c in outer if c.chunk_id == 0x2226), None)
    if menu_chunk is not None:
        cca = set_blob_property(cca, b"Menu", decompress_chunk(menu_chunk))

    global_event_payload = None
    if global_event_sheet["sheet"] is not None:
        sheet = global_event_sheet["sheet"]
        for entry in sheet["registry"]:
            entry["icon"] = icons_by_handle[2 + entry["object_id"]]
        global_event_payload = build_global_event_property(
            sheet["events"], registry=sheet["registry"]
        )
        cca = set_blob_property(cca, b"GEvt", global_event_payload)

    name_chunk = find_chunk(outer, 0x2224)
    author_chunk = find_chunk(outer, 0x2225)
    if name_chunk is not None and author_chunk is not None:
        cca = set_application_about(
            cca, decompress_chunk(name_chunk), decompress_chunk(author_chunk)
        )

    app_header = find_chunk(outer, 0x2223)
    if app_header is not None:
        header = decompress_chunk(app_header)
        win_w, win_h = struct.unpack_from("<HH", header, 8)
        cca = set_app_window_size(cca, win_w, win_h)

        cca = set_app_color_mode(cca, struct.unpack_from("<H", header, 4)[0])

        cca = set_app_players(cca, header)

        score, lives = struct.unpack_from("<II", header, 0x0C)
        cca = set_player_value(cca, b"Scor", score)
        cca = set_player_value(cca, b"Live", lives)

        cca = set_u32_property(
            cca,
            b"WinO",
            runtime_window_options(struct.unpack_from("<I", header, 0)[0]),
        )
        cca = set_u32_property(
            cca,
            b"RunO",
            runtime_run_options(struct.unpack_from("<I", header, 0)[0]),
        )

    list_pos, tail_pos, editor_frames = frame_records(cca)
    if len(editor_frames) != 1:
        raise ValueError("neutral scaffold should contain exactly one frame")
    old_start, old_end = editor_frames[0]
    neutral_frame = cca[old_start:old_end]
    old_title = frame_title(neutral_frame)

    templates = synthesised_templates()
    objects_by_id = {obj["object_id"]: obj for obj in objects}

    if len(frame_item_ids) != len(frames):
        raise ValueError(
            f"recovered {len(frame_item_ids)} frame item ids for "
            f"{len(frames)} frames"
        )
    rebuilt_frames = []
    for frame_index, frame in enumerate(frames):
        if progress is not None:
            progress("frames", frame_index + 1, len(frames))
        rebuilt_frames.append(
            reconstruct_frame(
                neutral_frame,
                old_title,
                frame_index,
                frame,
                objects_by_id,
                templates,
                item_id=frame_item_ids[frame_index],
            )
        )
    cca = cca[:old_start] + b"".join(rebuilt_frames) + cca[tail_pos:]
    data = bytearray(cca)
    struct.pack_into("<I", data, list_pos + 4, len(rebuilt_frames))
    return bytes(data), {
        "frames": frames,
        "objects": objects,
        "images": images,
        "unresolved_frame_item_ids": unresolved_item_ids,
        "repaired_event_reference_types": repaired_event_reference_types,
        "repaired_parameter_sizes": repaired_parameter_sizes,

        "salvaged_music_records": salvaged_music_records,

        "unplaced_placeholders": unplaced_placeholders,

        "dangling_shoot_parents": dangling_shoot_parents,

        "group_close_repairs": group_close_repairs,

        "recovered_comments": recovered_comments,
        "global_event_rows": (
            0
            if global_event_payload is None
            else len(global_events(global_event_payload)[0])
        ),
        "unresolved_global_events": global_event_sheet["notes"],

        "generated_icon_fallbacks": generated_icon_fallbacks,

        "synthesised_library_titles": synthesised_library_titles,

        "unreadable_event_frames": unreadable_events or [],

        "frame_passwords": [
            (index, frame["password"].partition(bytes(1))[0].decode("latin-1"))
            for index, frame in enumerate(frames)
            if frame.get("password")
        ],
    }

def validate(output: bytes, summary: dict) -> None:
    """Check the rebuilt project before it is offered as a result.

    A project that fails is written under a `.failed` name and reported as
    invalid rather than handed over — a bad candidate is worth keeping for
    inspection, and worth never being mistaken for a good one.
    """
    _list_pos, _tail_pos, records = frame_records(output)
    if len(records) != len(summary["frames"]):
        raise ValueError("reconstructed frame count is wrong")
    for index, ((start, end), expected) in enumerate(
        zip(records, summary["frames"])
    ):
        frame = output[start:end]
        if frame_title(frame) != (expected["name"] or b"\x00"):
            raise ValueError(f"frame {index} title is wrong")
        object_count_pos = frame.index(OBJECT_LIST) + len(OBJECT_LIST)
        expected_objects = len(expected["registry"]["frame_item_object_ids"])
        if struct.unpack_from("<I", frame, object_count_pos)[0] != expected_objects:
            raise ValueError(f"frame {index} object count is wrong")
        instance_count_pos = frame.index(INSTANCE_LIST) + len(INSTANCE_LIST)

        orphans = set(expected["registry"]["placeholder_only_orphans"])
        expected_instances = sum(
            1
            for placement in expected["placements"]
            if placement[3] not in orphans
        )
        if struct.unpack_from("<I", frame, instance_count_pos)[0] != expected_instances:
            raise ValueError(f"frame {index} placement count is wrong")

    image_pos = icon_and_image_bank_offsets(output)[1]
    _image_size, image_count = agmi_size(output, image_pos)
    if image_count != len(summary["images"]):
        raise ValueError("reconstructed image count is wrong")

PROJECT_PATH_RECORD = b"icnD"

def encode_ansi_path(text: str) -> bytes:
    """Encode the project's location the way MMF stores it, or explain why it cannot be.

    MMF keeps the path as plain bytes in a Windows codepage, so a folder name
    outside every codepage on this machine has no representation in the file.
    That is refused with the fix stated rather than silently mangled.
    """
    for codec in ("latin-1", "mbcs"):
        try:
            return text.encode(codec)
        except (UnicodeEncodeError, LookupError):
            continue
    raise ValueError(
        f"the output path {text!r} holds characters no ANSI codepage on this "
        f"machine can encode, and MMF stores the project's own path as ANSI "
        f"bytes; write the reconstruction to a directory whose name is "
        f"representable"
    )

def set_project_path(data: bytes, path: Path) -> bytes:
    """Record the project's own location in the file, as the editor expects.

    A saved project stores where it lives; a rebuilt one stores where it was
    written. Nothing about the machine that built it travels any further than
    that.
    """
    at = data.find(PROJECT_PATH_RECORD)
    if at < 0:
        return data
    try:
        _a, _b, length = struct.unpack_from("<III", data, at + 4)
    except struct.error:
        return data
    end = at + 16 + length

    if end >= len(data) or data[end:end + 1] != bytes(1):
        return data
    encoded = encode_ansi_path(str(path))
    return (
        data[:at + 12]
        + struct.pack("<I", len(encoded))
        + encoded
        + bytes(1)
        + data[end + 1:]
    )

def failed_output_path(output: Path) -> Path:
    """Where a project that failed validation is kept, under its own name."""
    return output.with_name(f"{output.stem}.failed{output.suffix}")

def summary_output_path(output: Path) -> Path:
    """Where the machine-readable inventory is written."""
    return output.with_name(f"{output.stem}.summary.json")

def reconstruction_report(
    exe: Path,
    output: Path,
    summary: dict,
    *,
    status: str,
    error: str | None = None,
    timings: dict[str, float] | None = None,
) -> dict:
    """Everything recovered and everything lost, in the terms the report prints.

    The machine-readable summary written beside a rebuilt project: what the game
    turned out to contain — frames with their sizes, placement and event counts,
    objects broken down by type, images — and then every category of loss and
    repair the run recorded.

    One decision shapes the whole thing: the loss and repair keys are **always
    written, empty list included**. That way an absent key means "this version of
    the tool did not have that field yet", not "nothing was lost" — which are
    very different answers to give someone reading an old report to decide
    whether a game came back cleanly.

    It also derives one thing rather than copying it. An object can belong to more
    qualifier groups at runtime than the editor is able to show, so any
    membership past what the editor supports is listed by name with the one that
    had to be dropped and why. That is a real loss which nothing else in the run
    would otherwise mention.
    """
    type_counts = Counter(obj["object_type"] for obj in summary["objects"])
    qualifier_truncations = []
    for obj in summary["objects"]:
        definition = obj["definition"]
        if obj["object_type"] != ACTIVE_OBJECT_TYPE or len(definition) < 38:
            continue
        words = list(struct.unpack("<9H", definition[20:38]))
        if 0xFFFF not in words and all(word <= 99 for word in words):
            qualifier_truncations.append(
                {
                    "object_id": obj["object_id"],
                    "name": obj["name"].split(b"\0", 1)[0].decode(
                        "latin-1", errors="replace"
                    ),
                    "kept_qualifiers": words[:8],
                    "dropped_qualifier": words[8],
                    "reason": "editor supports at most eight memberships plus 0xFFFF",
                }
            )
    frames = [
        {
            "index": index,
            "name": frame["name"].split(b"\0", 1)[0].decode(
                "latin-1", errors="replace"
            ),
            "width": frame["width"],
            "height": frame["height"],
            "placements": len(frame["placements"]),
            "events": len(frame["events"]),
        }
        for index, frame in enumerate(summary["frames"])
    ]
    report = {
        "status": status,
        "source": str(exe),
        "output": str(output),
        "frame_count": len(frames),
        "object_count": len(summary["objects"]),
        "image_count": len(summary["images"]),
        "placement_count": sum(frame["placements"] for frame in frames),
        "event_count": sum(frame["events"] for frame in frames),
        "object_types": {str(key): type_counts[key] for key in sorted(type_counts)},
        "frames": frames,
    }
    if qualifier_truncations:
        report["lossy_qualifier_memberships"] = qualifier_truncations

    report["unresolved_frame_item_ids"] = summary.get(
        "unresolved_frame_item_ids", []
    )
    report["repaired_event_reference_types"] = summary.get(
        "repaired_event_reference_types", []
    )
    report["repaired_parameter_sizes"] = summary.get("repaired_parameter_sizes", [])
    report["salvaged_music_records"] = summary.get("salvaged_music_records", [])
    report["global_event_rows"] = summary.get("global_event_rows", 0)
    report["unresolved_global_events"] = summary.get("unresolved_global_events", [])
    report["synthesised_library_titles"] = summary.get(
        "synthesised_library_titles", []
    )
    report["unplaced_placeholders"] = summary.get("unplaced_placeholders", [])
    report["generated_icon_fallbacks"] = summary.get(
        "generated_icon_fallbacks", []
    )
    report["dangling_shoot_parents"] = summary.get("dangling_shoot_parents", [])
    report["group_close_repairs"] = summary.get("group_close_repairs", [])
    report["recovered_comments"] = summary.get("recovered_comments", [])
    if timings is not None:
        report["timings_seconds"] = {
            name: round(seconds, 3) for name, seconds in timings.items()
        }
    if error is not None:
        report["error"] = error
    return report

def write_report(path: Path, report: dict) -> None:
    """Write the inventory beside the project, for reading without an editor.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
