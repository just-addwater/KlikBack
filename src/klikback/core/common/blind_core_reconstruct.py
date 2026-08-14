# GENERATED — do not edit by hand. This file is produced by KlikBack's
# sync tooling; changes belong in the source it is generated from.
#
# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""Write the per-object records a rebuilt 1.0 project is made of.

Where the pipeline's core decides *what* a frame contains, this builds the
records that say so: an Active with its movements, animations, qualifiers and
transitions; a Backdrop with its image and how it collides; a String with its
paragraphs and font. Each is written into the neutral template for its type
by setting named properties, so a record is edited semantically rather than
patched at an offset.

The values come from the compiled game's own runtime data — an object's
display settings, its scroll and memory flags, its transitions — translated
into the properties the editor stores. Where the runtime keeps something the
editor does not, or the other way round, the difference is handled here
rather than papered over upstream.
"""

from __future__ import annotations
import struct
from typing import Container
from klikback.core.mmf1.alterable_value_reconstruct import alterable_values_property, runtime_alterable_values
from klikback.core.common.comment_rows import remarks_block
from klikback.core.common.event_object_registry import NON_EVENT_OBJECT_TYPES, placeholder_editor_fields, qualifier_event_object_record
from klikback.core.common.exe_to_cca import icon_and_image_bank_offsets
from klikback.core.mmf1.movement_reconstruct import GENERAL_DESCRIPTOR, STATIC_DESCRIPTOR, replace_static_movement, runtime_movement
from klikback.core.common.multi_animation_reconstruct import animation_names_from_events, editor_animation_set, parse_runtime_animation_set
from klikback.core.common.object_reconstruct import INSTANCE_LIST, OBJECT_LIST, add_default_behavior, event_object_record, nested_payload, patch_active_record
from klikback.core.mmf1.probe import agmi_size
from klikback.core.common.qualifier_reconstruct import QUALIFIER_TAG, qualifier_indices, qualifier_property
from klikback.core.mmf1.string_reconstruct import string_editor_record

EVENT_OBJECT_LIST = b"class COIList"

def replace_icon_bank(cca: bytes, records: list[bytes]) -> bytes:

    """Swap in the generated object icons, wholesale."""
    bank_pos = icon_and_image_bank_offsets(cca)[0]
    old_size, _count = agmi_size(cca, bank_pos)
    header = bytearray(cca[bank_pos:bank_pos + 0x410])
    struct.pack_into("<I", header, 0x40C, len(records))
    bank = bytes(header) + b"".join(records)
    measured_size, measured_count = agmi_size(bank, 0)
    if measured_size != len(bank) or measured_count != len(records):
        raise ValueError("rebuilt icon bank is inconsistent")
    return cca[:bank_pos] + bank + cca[bank_pos + old_size:]

def editor_animations(
    definition: bytes,
    editor_events: list[bytes],
    name_cache: dict | None = None,
) -> list[dict]:
    """The animation set an object carries, in the editor's own arrangement."""
    animation_offset = struct.unpack_from("<H", definition, 6)[0]
    if not 8 <= animation_offset < len(definition):
        raise ValueError("Active animation offset is invalid")
    animations = parse_runtime_animation_set(b"\x00" * 60 + definition[animation_offset:])

    if name_cache is None:
        recovered_names = animation_names_from_events(editor_events)
    else:
        if "names" not in name_cache:
            name_cache["names"] = animation_names_from_events(editor_events)
        recovered_names = name_cache["names"]
    for animation in animations:
        animation_id = animation["animation_id"]
        if animation_id >= 12 and animation_id in recovered_names:
            animation["name"] = recovered_names[animation_id]
    return animations

EXTENSION_OBJECT_TYPE_BASE = 32

EVENT_OBJECT_TYPE_STRINGS = {
    2: b"Sprite",
    3: b"Text",
    4: b"Question",
    5: b"Score",
    6: b"Lives",
    7: b"Counter",
    8: b"",
    9: b"",
}

def strip_nonmovement_default_behavior(record: bytes) -> bytes:
    """Remove the placeholder behaviour the starting record carries.

    The base project's object arrives with an empty behaviour attached. The
    game's own behaviours are recovered separately, so the placeholder is taken
    out rather than left to show up in the editor as an event page nobody wrote.
    """
    data = bytearray(record)
    named = b"\x04\x00LEvt\x0B\x00Behavior #1TVEd"
    named_pos = data.index(named)
    property_pos = data.index(b"\x04\x00LEvt", 0x200, named_pos)
    del data[property_pos:property_pos + 26]
    named_pos = data.index(named)
    data[named_pos:named_pos + len(named)] = b"\x04\x00LEvt\x00\x00TVEd"
    return bytes(data)

PROPERTY_HEADER_SIZE = 26

PROPERTY_DEFAULT_LENGTH = 0xFFFF

PROPERTY_MARKER = b"\x04\x00"

PROPERTY_MARKERS = (b"\x04\x00", b"\x03\x00")

def property_span(record: bytes, tag: bytes, start: int = 0) -> tuple[int, int]:
    """Where one property sits inside a record."""
    position = record.index(PROPERTY_MARKER + tag, start)
    length = struct.unpack_from("<H", record, position + 16)[0]
    size = PROPERTY_HEADER_SIZE
    if length != PROPERTY_DEFAULT_LENGTH:
        size += 4 + length
    end = position + size

    if (
        record[end : end + 2] not in PROPERTY_MARKERS
        and b"PROP" not in record[end : end + 16]
    ):
        raise ValueError(
            f"property {tag!r} does not end on a property marker or the list end"
        )
    return position, end

def set_qualifiers(record: bytes, payload: bytes) -> bytes:
    """Give an object its qualifier group memberships."""
    if payload and not qualifier_indices(payload):
        payload = b""
    start, end = property_span(record, QUALIFIER_TAG[2:])
    return record[:start] + qualifier_property(payload) + record[end:]

def set_u32_property(record: bytes, tag: bytes, value: int) -> bytes:
    """Write a numeric property, replacing whatever the template held."""
    start, end = property_span(record, tag)
    return (
        record[:start]
        + record[start : start + 16]
        + struct.pack("<H", 0)
        + record[start + 18 : start + 26]
        + struct.pack("<I", value)
        + record[end:]
    )

def set_blob_property(record: bytes, tag: bytes, payload: bytes) -> bytes:
    """Write a property whose value is a block of bytes."""
    start, end = property_span(record, tag)
    return (
        record[:start]
        + record[start : start + 16]
        + struct.pack("<H", len(payload))
        + record[start + 18 : start + 26]
        + struct.pack("<I", len(payload))
        + payload
        + record[end:]
    )

def set_property_entry(record: bytes, tag: bytes, entry_id: int, value: int) -> bytes:
    """Write one numbered slot of a property that holds several.

    Several editor controls store as one property with numbered entries — an ink
    effect and its parameters, a trio of checkboxes — so the entry is which
    control, not which object. A slot the record does not have is an error rather
    than a silent no-op, because the property would then keep the template's
    value and the rebuilt object would show a setting its author never chose.
    """
    position = record.index(PROPERTY_MARKER + tag)
    count = struct.unpack_from("<I", record, position + 10)[0]
    data = bytearray(record)
    for index in range(count):
        entry = position + 14 + index * 16
        stored_id = struct.unpack_from("<H", data, entry)[0]
        if stored_id != entry_id:
            continue
        struct.pack_into("<H", data, entry + 2, 0)
        struct.pack_into("<I", data, entry + 12, value)
        return bytes(data)
    raise ValueError(f"property {tag!r} has no entry 0x{entry_id:04x}")

def set_memory_flags(record: bytes, memory_flags: int) -> bytes:
    """Write the memory-handling flags the object was compiled with."""
    return set_u32_property(record, b"MFla", memory_flags)

SCROLL_ENTRY_IDS = (0x0001, 0x0101, 0x0205)

SCROLL_SELECTED = 2

SCROLL_DESELECTED = 1

SCROLL_FLAGS_OFFSET = 0x13

SCROLL_NO_FOLLOW_FRAME = 0x08

SCROLL_NO_DESTROY_IF_FAR = 0x20

SCROLL_NO_INACTIVATE_IF_FAR = 0x40

def runtime_scroll_values(definition: bytes) -> tuple[int, int, int | None] | None:
    """The scrolling settings an object carries at runtime."""
    if len(definition) <= SCROLL_FLAGS_OFFSET:
        return None
    flags = definition[SCROLL_FLAGS_OFFSET]
    return (
        SCROLL_DESELECTED if flags & SCROLL_NO_FOLLOW_FRAME else SCROLL_SELECTED,
        SCROLL_DESELECTED if flags & SCROLL_NO_DESTROY_IF_FAR else SCROLL_SELECTED,
        SCROLL_DESELECTED if flags & SCROLL_NO_INACTIVATE_IF_FAR else None,
    )

def set_scroll_flags(
    record: bytes,
    follow_frame: int,
    destroy_if_far: int,
    inactivate_if_far: int | None = None,
) -> bytes:
    """Write the three scrolling choices: follow the frame, destroy or sleep when far.
    """
    position = record.index(b"\x04\x00SFlg")
    if struct.unpack_from("<I", record, position + 10)[0] != len(SCROLL_ENTRY_IDS):
        raise ValueError("scrolling property does not hold three entries")
    data = bytearray(record)
    for index, (entry_id, value) in enumerate(
        zip(SCROLL_ENTRY_IDS, (follow_frame, destroy_if_far, inactivate_if_far))
    ):
        entry = position + 14 + index * 16
        stored_id, flag = struct.unpack_from("<HH", data, entry)
        if stored_id != entry_id or flag != 0:
            raise ValueError(
                f"scrolling entry {index} is not an explicit id 0x{entry_id:04x}"
            )
        if value is not None:
            struct.pack_into("<I", data, entry + 12, value)
    return bytes(data)

DISPLAY_FLAGS_OFFSET = 0x28

DISPLAY_SAVE_BACKGROUND = 0x01

DISPLAY_WIPE_WITH_COLOUR = 0x02

DISPLAY_NO_FINE_COLLISIONS = 0x04

DISPLAY_VISIBLE = 0x08

VISIBLE_AT_START = 2

NOT_VISIBLE_AT_START = 1

OBJECT_COLOUR_OFFSET = 0x30

BACKGROUND_ENTRY_IDS = (0x0001, 0x0101)

SAVE_BACKGROUND_ON = 1

SAVE_BACKGROUND_OFF = 2

WIPE_WITH_COLOUR_ON = 2

WIPE_WITH_COLOUR_OFF = 1

FINE_COLLISIONS_ON = 1

FINE_COLLISIONS_OFF = 0

ACTIVE_OBJECT_TYPE = 2

def runtime_display_values(definition: bytes) -> dict | None:
    """The display settings an object carries at runtime."""
    if len(definition) <= DISPLAY_FLAGS_OFFSET:
        return None
    flags = definition[DISPLAY_FLAGS_OFFSET]
    return {
        "save_background": (
            SAVE_BACKGROUND_ON
            if flags & DISPLAY_SAVE_BACKGROUND
            else SAVE_BACKGROUND_OFF
        ),
        "wipe_with_colour": (
            WIPE_WITH_COLOUR_ON
            if flags & DISPLAY_WIPE_WITH_COLOUR
            else WIPE_WITH_COLOUR_OFF
        ),
        "fine_collisions": (
            FINE_COLLISIONS_OFF
            if flags & DISPLAY_NO_FINE_COLLISIONS
            else FINE_COLLISIONS_ON
        ),
        "visible": (
            VISIBLE_AT_START if flags & DISPLAY_VISIBLE else NOT_VISIBLE_AT_START
        ),
        "colour": (
            struct.unpack_from("<I", definition, OBJECT_COLOUR_OFFSET)[0]
            if len(definition) >= OBJECT_COLOUR_OFFSET + 4
            else None
        ),
    }

def set_background_flags(record: bytes, save: int, wipe: int) -> bytes:
    """Write how an object treats the background behind it."""
    position = record.index(b"\x04\x00BFlg")
    if struct.unpack_from("<I", record, position + 10)[0] != len(
        BACKGROUND_ENTRY_IDS
    ):
        raise ValueError("background property does not hold two entries")
    data = bytearray(record)
    for index, (entry_id, value) in enumerate(
        zip(BACKGROUND_ENTRY_IDS, (save, wipe))
    ):
        entry = position + 14 + index * 16
        stored_id, flag = struct.unpack_from("<HH", data, entry)
        if stored_id != entry_id or flag != 0:
            raise ValueError(
                f"background entry {index} is not an explicit id 0x{entry_id:04x}"
            )
        struct.pack_into("<I", data, entry + 12, value)
    return bytes(data)

def set_fine_collisions(record: bytes, value: int) -> bytes:
    """Set whether an Active collides by its shape or by its box."""
    start, _end = property_span(record, b"CFlg")
    data = bytearray(record)
    struct.pack_into("<I", data, start + 26, value)
    return bytes(data)

TRANSITION_HEADER_SIZE = 0x14

TRANSITION_MODULE_OFFSET = 0x14

TRANSITION_NAMES = {

    (b"cctrans.dll", b"STDTBAND"): b"Bands",
    (b"cctrans.dll", b"STDTDOOR"): b"Door",

    (b"cctrans.dll", b"STDTFADE"): b"Fade",
    (b"cctrans.dll", b"STDTMOSA"): b"Mosaic",
    (b"cctrans.dll", b"STDTSCRL"): b"Scrolling",
    (b"cctrans.dll", b"STDTZIGZ"): b"Zigzag",
    (b"cctrans.dll", b"STDTZOOM"): b"Zoom",

    (b"sftrans.dll", b"SFTRATS "): b"Advanced Transition Studio :)",
    (b"sftrans.dll", b"SFTRAZOM"): b"Alpha Zoom",
    (b"sftrans.dll", b"SFTRCFAD"): b"Color Fade",
    (b"sftrans.dll", b"SFTRCIRC"): b"Circle",
    (b"sftrans.dll", b"SFTRCRAP"): b"Crappy Transition",
    (b"sftrans.dll", b"SFTRFAN "): b"Fan",

    (b"sftrans.dll", b"SFTRFOLD"): b"Folder",
    (b"sftrans.dll", b"SFTRPIXX"): b"Pixelate (*beta*)",
    (b"sftrans.dll", b"SFTRSTRE"): b"Stretch",
    (b"sftrans.dll", b"SFTRTZOM"): b"Tile Zoom",

    (b"fctrans.dll", b"FAD1ROTA"): b"Rotate",
    (b"fctrans.dll", b"FAD1SLID"): b"Slider",

    (b"rollovine.dll", b"MAH1ARO2"): b"Ovine Roll",
    (b"rubberovine.dll", b"MAH1ARO1"): b"Ovine Rubber (tight)",
    (b"rubberovine.dll", b"MAH1ARO2"): b"Ovine Rubber (loose)",
    (b"strans.dll", b"SS00SE00"): b"Advanced Scrolling",
    (b"strans.dll", b"SS00SE04"): b"ZigZag",
    (b"strans.dll", b"SS00SE10"): b"Back",
    (b"strans.dll", b"SS00SE12"): b"Cell",
    (b"strans.dll", b"SS00SE13"): b"Trame",
}

FADE_IN_OFFSET = 0x34

FADE_OUT_OFFSET = 0x38

def parse_transition(data: bytes, offset: int) -> dict:
    """Read a transition out of the compiled game's own form."""
    identifier = data[offset : offset + 8]
    module_offset, param_offset, param_length = struct.unpack_from(
        "<III", data, offset + TRANSITION_MODULE_OFFSET
    )
    module_end = data.index(b"\x00", offset + module_offset) + 1
    module = data[offset + module_offset : module_end]
    return {
        "header": data[offset : offset + TRANSITION_HEADER_SIZE],
        "module": module,

        "name": TRANSITION_NAMES.get(
            (module.rstrip(b"\x00").lower(), identifier), b"Transition"
        )
        + b"\x00",
        "parameters": data[
            offset + param_offset : offset + param_offset + param_length
        ],
    }

def transition_property(tag: bytes, transition: dict) -> bytes:
    """Store one transition in the form the editor reads."""

    def sub(flag: int, record_id: int, payload: bytes) -> bytes:
        return struct.pack("<HHI", flag, record_id, len(payload)) + payload

    value = (
        sub(0x0000, 0x0333, transition["header"])
        + sub(0x0000, 0x0334, transition["module"])
        + sub(0x0000, 0x0335, transition["name"])
        + sub(0x8000, 0x0336, transition["parameters"])
    )
    return (
        b"\x04\x00"
        + tag
        + struct.pack("<II", 1, 1)
        + struct.pack("<HH", 10, len(value))
        + struct.pack("<II", 1, 1)
        + struct.pack("<I", len(value))
        + value
    )

def set_transition(record: bytes, tag: bytes, transition: dict | None) -> bytes:
    """Give an object its transition, as the editor stores it."""
    start, end = property_span(record, tag)
    if transition is None:
        return record
    return record[:start] + transition_property(tag, transition) + record[end:]

def runtime_object_transitions(definition: bytes) -> dict:
    """Every object's transition, as the game stored it."""
    transitions = {}
    if len(definition) < FADE_OUT_OFFSET + 4:
        return transitions
    for tag, offset in ((b"FadI", FADE_IN_OFFSET), (b"FadO", FADE_OUT_OFFSET)):
        block = struct.unpack_from("<I", definition, offset)[0]
        if block:
            transitions[tag] = parse_transition(definition, block)
    return transitions

def runtime_qualifiers(definition: bytes) -> bytes:
    """The qualifier groups the compiled game says an object belongs to."""
    if len(definition) < 38:
        return b""
    payload = definition[20:38]
    indices = qualifier_indices(payload)
    if not indices:
        return b""
    if 0xFFFF not in struct.unpack("<9H", payload):
        return payload[:16] + b"\xff\xff"
    return payload

def active_record(
    template: bytes,
    obj: dict,
    icon_id: int,
    editor_events: list[bytes],
    name_cache: dict | None = None,
) -> bytes:
    """Build an Active object's record: movement, animation, qualifiers and flags.

    The Active is the richest object type there is, and its record is assembled
    from four independent recoveries rather than copied from anywhere.

    **Animations** are rebuilt into the editor's own set structure, and the images
    come back as the ids the rebuilt image bank uses. Only the animations the
    object really has are written — an empty slot the object never used is not a
    harmless extra, because the editor will happily give an enemy a movement with
    no directions and no pictures in it, and that is what the game then renders.

    **Movement** is read from the compiled object and written back under the tag
    the editor expects for that kind — static, mouse, race car, general, ball,
    path or platform. Each kind brings its own descriptor, and the template's
    placeholder descriptors are removed or kept to match: which ones is a property
    of the movement type, not a guess.

    **Qualifiers** — the groups an object can be selected through — carry across
    from the compiled definition unchanged.

    **Alterable values** are the one place with an honest substitution. The
    compiled game keeps the values but not the names the author gave them, so
    neutral names stand in and the loss is limited to a label: the numbers, and
    how many there are, are the object's own.
    """
    animations = editor_animations(obj["definition"], editor_events, name_cache)
    movement_offset = struct.unpack_from("<H", obj["definition"], 4)[0]
    movement_type = None
    movement = b""
    if movement_offset:
        movement_type, movement = runtime_movement(obj["definition"])

    first_image = next(
        image_id
        for animation in animations
        for direction in animation["directions"]
        for image_id in direction["image_ids"]
    )
    record = patch_active_record(
        template,
        item_id=struct.unpack_from("<I", template, 0x14)[0],
        object_id=obj["object_id"],
        name=obj["name"],
        image_id=first_image,
        icon_id=icon_id,
        include_default_behavior=False,
    )
    record = set_qualifiers(record, runtime_qualifiers(obj["definition"]))
    animation_pos = record.index(b"AnSt")
    record = record[:animation_pos] + editor_animation_set(animations)

    if movement_offset:
        movement_tags = {
            0: b"MSta",
            1: b"MMou",
            2: b"MRac",
            3: b"MGen",
            4: b"MBal",
            5: b"MPat",
            9: b"MPla",
        }
        if movement_type not in movement_tags:
            raise ValueError(f"unsupported built-in movement type {movement_type}")
        if movement_type in (0, 4):

            remove = ()
        elif movement_type == 9:
            remove = (STATIC_DESCRIPTOR, GENERAL_DESCRIPTOR)
        else:
            remove = (STATIC_DESCRIPTOR,)
        record = replace_static_movement(
            record,
            movement,
            editor_tag=movement_tags[movement_type],
            remove_descriptors=remove,
        )
    initial_values = runtime_alterable_values(obj["definition"])
    if initial_values:

        start = record.index(b"\x04\x00AltV")
        end = record.index(b"\x04\x00Keyw", start)
        names = [
            f"Value{chr(ord('A') + index)}".encode("ascii")
            for index in range(len(initial_values))
        ]
        record = (
            record[:start]
            + alterable_values_property(names, initial_values)
            + record[end:]
        )
        data = bytearray(record)
        had_behavior = b"\x04\x00LEvt\x0B\x00Behavior #1TVEd" in data
        add_default_behavior(data, b"\x01\x00\x00\x00")
        if not had_behavior:
            property_count = struct.unpack_from("<I", data, 0x14)[0]
            struct.pack_into("<I", data, 0x14, property_count + 1)
        record = bytes(data)
    return record

OBST_PROPERTY_PREFIX = b"\x04\x00Obst\x01\x00\x00\x00\x03\x00\x00\x00\x04\x00"

OBST_VALUE_OFFSET = 38

def set_obstacle(record: bytes, obstacle: int) -> bytes:
    """Set what an object collides with."""
    if obstacle not in (0, 1, 2, 3):
        raise ValueError(f"unsupported obstacle type {obstacle}")
    data = bytearray(record)
    pos = data.index(OBST_PROPERTY_PREFIX)
    data[pos + OBST_VALUE_OFFSET] = obstacle
    return bytes(data)

def set_record_name(record: bytes, name: bytes) -> bytes:
    """Name a record, the way the editor shows it."""
    if not name.endswith(b"\x00"):
        raise ValueError("editor object name must be NUL-terminated")
    data = bytearray(record)
    name_tag = data.index(b"ItNa")
    struct.pack_into("<H", data, name_tag + 0x1A, len(name))
    name_pos = name_tag + 0x24
    icon_tag = data.index(b"\x04\x00ItIc", name_pos)
    data[name_pos:icon_tag] = name
    return bytes(data)

def backdrop_record(
    template: bytes, obj: dict, icon_id: int, name: bytes | None = None
) -> bytes:

    """Build a Backdrop's record, with its image and collision settings."""
    if name is not None:
        template = set_record_name(template, name)
    record = bytearray(template)
    object_id_pos = record.index(b"SBOs")
    struct.pack_into("<I", record, object_id_pos + 4, obj["object_id"])
    icon_pos = record.index(b"icnI")
    struct.pack_into("<II", record, icon_pos + 4, icon_id, obj["image_id"])

    return set_obstacle(bytes(record), obj["definition"][4])

def string_paragraphs(
    definition: bytes,
) -> tuple[int, int, list[bytes], int, int, int]:
    """The lines of a String object, split as the editor stores them."""
    text_offset = struct.unpack_from("<I", definition, 0x0C)[0]
    width, height, count = struct.unpack_from(
        "<3H", definition, text_offset + 4
    )
    offsets = struct.unpack_from(f"<{count}H", definition, text_offset + 10)
    texts = []
    styles = set()
    for paragraph_offset in offsets:
        pos = text_offset + paragraph_offset
        size, font, color, reserved = struct.unpack_from(
            "<HHIH", definition, pos
        )
        styles.add((font, color, reserved))
        text = definition[pos + 10 : pos + size]
        if not text.endswith(b"\x00"):
            raise ValueError("String paragraph is not NUL-terminated")
        texts.append(text[:-1])
    if len(styles) != 1:
        raise ValueError(f"String paragraphs carry mixed styles {styles}")
    font, color, reserved = styles.pop()
    return width, height, texts, font, color, reserved

def text_record(obj: dict, icon_id: int) -> bytes:
    """Build a String object's record, with its paragraphs and formatting."""
    width, height, texts, font, color, reserved = string_paragraphs(
        obj["definition"]
    )
    record = bytearray(
        string_editor_record(
            {
                "name": obj["name"],
                "width": width,
                "height": height,
                "text": texts[0],
            }
        )
    )

    attr_pos = record.index(b"icnI") + 16
    editor_font = font if font != 0xFFFF else 0xFFFFFFFF
    struct.pack_into("<IIII", record, attr_pos, editor_font, color, reserved, 0)
    if len(texts) > 1:

        paragraph_pos = record.index(b"icnI") + 8 + 24
        record[paragraph_pos:] = struct.pack("<I", len(texts)) + b"".join(
            struct.pack("<I", len(text)) + text + b"\x00" * 4
            for text in texts
        )
    struct.pack_into("<I", record, 0x14, 14)
    name_pos = record.index(b"ItNa")
    struct.pack_into("<H", record, name_pos + 0x0E, 0xFFFF)
    palette_pos = record.index(b"PSDd")
    struct.pack_into("<I", record, palette_pos + 4, obj["object_id"])
    icon_pos = record.index(b"icnI")
    struct.pack_into("<I", record, icon_pos + 4, icon_id)
    result = bytes(record)
    if b"Behavior #1" in result:
        result = strip_nonmovement_default_behavior(result)
    return result

def replace_objects(cca: bytes, records: list[bytes]) -> bytes:
    """Put the rebuilt object records into the project."""
    count_pos = cca.index(OBJECT_LIST) + len(OBJECT_LIST)
    instance_pos = cca.index(INSTANCE_LIST, count_pos)
    records_end = instance_pos - 4
    if cca[records_end:instance_pos] != struct.pack("<I", 0x2F):
        raise ValueError("blind scaffold object-list terminator is missing")
    cca = (
        cca[:count_pos]
        + struct.pack("<I", len(records))
        + b"".join(records)
        + cca[records_end:]
    )
    end_tag = cca.index(b"!DNE", count_pos)
    data = bytearray(cca)
    struct.pack_into("<I", data, end_tag + 8, len(records) + 1)
    return bytes(data)

def replace_instances(
    cca: bytes,
    placements: list[tuple[int, int, int, int, int]],
    types: dict[int, int],
    app_to_local_item: dict[int, int] | None = None,
    dangling_shoot_parents: Container[int] = (),
) -> bytes:
    """Put the placements — which object sits where in each frame — into the project.
    """
    count_pos = cca.index(INSTANCE_LIST) + len(INSTANCE_LIST)
    old_count = struct.unpack_from("<I", cca, count_pos)[0]
    old_end = count_pos + 4 + old_count * 32
    records = bytearray()
    for instance_id, x, y, object_id, runtime_link in placements:
        if runtime_link:
            editor_a, editor_b, editor_end = placeholder_editor_fields(
                runtime_link,
                app_to_local_item
                if app_to_local_item is not None
                else {local_id: local_id for local_id in types},
                allow_dangling_parent=dangling_shoot_parents,
            )
        else:
            editor_a = 0
            editor_b = 0
            editor_end = -1

        records.extend(b"IPIn" if types[object_id] in (3, 8) else b"Inst")
        records.extend(
            struct.pack(
                "<iiiiiii",
                x,
                y,
                instance_id,
                editor_a,
                editor_b,
                object_id,
                editor_end,
            )
        )
    return cca[:count_pos] + struct.pack("<I", len(placements)) + bytes(records) + cca[old_end:]

def insert_event_data(
    cca: bytes,
    events: list[bytes],
    objects: list[dict],
    placeholder_instance_for: dict[int, int] | None = None,
    qualifier_words: list[int] | None = None,
    remarks: list[bytes] | None = None,
) -> bytes:
    """Write a frame's converted events into the project.

    Three things go into a frame's event page together, and their order in the
    file is fixed: the events, then the author's comment rows, then the list of
    objects the events talk about. Getting the order wrong produces a page the
    editor will not read, and it is the reverse of the order the same three take
    in the global-events container — worth knowing before assuming one implies the
    other.

    The object list is built here rather than copied. Each entry names its object,
    its type as the editor spells it, and — for an object with no real placement —
    the stand-in instance that represents it. Objects of the types that never
    appear in events are left out, which is why this list and the frame's item
    list are different lengths.

    Qualifiers get entries too, appended after the objects in the numbering the
    registry assigned. Leaving them out is the interesting failure: any event that
    selects through a group then points at an entry that is not there, and the
    editor rejects the whole frame. A game with no group-selecting events looks
    fine either way, so the omission stays invisible until it meets one that does.

    Two shapes are refused or handled rather than papered over. Comment rows with
    no events cannot be written at all, because the rows those comments are
    attached to live in the event block. And a frame with no eligible objects gets
    **no object list block at all** rather than an empty one — the editor omits it
    entirely for such a frame, and writing an empty one makes it crash on opening
    or running that frame. The switch is on the record count, not the event count:
    a frame with objects but no events still gets a list.
    """
    insertion = cca.index(b"evpg") + 8
    old_end = cca.index(b"EvEd", insertion)
    if cca[insertion:insertion + 4] not in {b"EvEd", b"EvOb"}:
        raise ValueError("blind scaffold event page has an unexpected layout")
    placeholders = placeholder_instance_for or {}
    event_objects = [
        obj for obj in objects if obj["object_type"] not in NON_EVENT_OBJECT_TYPES
    ]
    records = []
    for event_id, obj in enumerate(event_objects):
        instance_link = placeholders.get(obj["object_id"], 0xFFFFFFFF)
        object_type = obj["object_type"]
        if object_type in EVENT_OBJECT_TYPE_STRINGS:
            type_string = EVENT_OBJECT_TYPE_STRINGS[object_type]
        elif object_type >= EXTENSION_OBJECT_TYPE_BASE:

            type_string = obj["definition"][0x2C:0x30]
        else:
            raise ValueError(f"unsupported event object type {object_type}")
        records.append(
            event_object_record(
                event_id,
                obj["name"],
                frame_item_id=obj["object_id"],
                object_type_id=object_type,
                object_type=type_string,
                instance_link=instance_link,
            )
        )
    for offset, qualifier_word in enumerate(qualifier_words or []):
        records.append(
            qualifier_event_object_record(
                len(event_objects) + offset, qualifier_word
            )
        )

    registry = (
        b"Evts" + struct.pack("<I", sum(map(len, events))) + b"".join(events)
        + remarks_block(remarks or [])
    )
    if remarks and not events:
        raise ValueError(
            "a page with comment rows but no Evts block cannot be written: "
            "the rows the comments name live in that block"
        )

    if records:
        registry += (
            b"EvOb" + struct.pack("<I", len(EVENT_OBJECT_LIST)) + EVENT_OBJECT_LIST
            + struct.pack("<I", len(records)) + b"".join(records)
        )
    cca = cca[:insertion] + registry + cca[old_end:]
    return cca
