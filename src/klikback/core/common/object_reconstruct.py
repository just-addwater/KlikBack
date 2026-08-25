# GENERATED — do not edit by hand. This file is produced by KlikBack's
# sync tooling; changes belong in the source it is generated from.
#
# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""Shared record surgery for rebuilding a 1.0 project's objects."""

from __future__ import annotations
import re
import struct
from klikback.core.common.exe_to_cca import decompress_chunk, icon_and_image_bank_offsets
from klikback.core.mmf1.probe import agmi_size

OBJECT_LIST = b"class cHandleItemList<class LFrameItem>"

INSTANCE_LIST = b"class cHandleItemList<class LFrameItemInstance>"

ACTIVE_RECORD = b"Actv" + b"\x00" * 8 + b"Ver 1.1\x00"

def nested_payload(chunks, chunk_id: int) -> bytes:
    """Read a payload stored inside another record."""
    matches = [chunk for chunk in chunks if chunk.chunk_id == chunk_id]
    if len(matches) != 1:
        raise ValueError(
            f"expected one nested chunk 0x{chunk_id:04X}, found {len(matches)}"
        )
    return decompress_chunk(matches[0])

def replace_image_bank(cca: bytes, images: list[tuple[int, bytes]]) -> bytes:

    """Swap the project's images for the ones recovered from the game."""
    bank_pos = icon_and_image_bank_offsets(cca)[1]
    old_size, _old_count = agmi_size(cca, bank_pos)
    header = bytearray(cca[bank_pos : bank_pos + 0x410])
    struct.pack_into("<I", header, 0x40C, len(images))
    records = b"".join(
        struct.pack("<I", image_id) + decoded
        for image_id, decoded in images
    )
    bank = bytes(header) + records
    measured_size, measured_count = agmi_size(bank, 0)
    if measured_size != len(bank) or measured_count != len(images):
        raise ValueError("reconstructed image bank is not self-consistent")
    return cca[:bank_pos] + bank + cca[bank_pos + old_size :]

PROP_TABLE_HEADER = re.compile(
    rb"\x01\x00\x00\x00(?P<pairs>..)\x01\x00\x50\x00\x00PROP", re.S
)

def add_default_behavior(
    record: bytearray, link_marker: bytes = b"\x01OB~"
) -> None:
    """Give an object the behaviour record the editor expects it to carry."""
    if b"\x04\x00LEvt\x0B\x00Behavior #1TVEd" in record:
        return
    matches = list(PROP_TABLE_HEADER.finditer(bytes(record)))
    if len(matches) != 1:

        raise ValueError(
            f"expected one PROP descriptor table in the record, found "
            f"{len(matches)}"
        )
    tail_pos = matches[0].start()
    record[tail_pos:tail_pos] = b"\x04\x00LEvt"
    if len(link_marker) != 4:
        raise ValueError("behavior link marker must contain four bytes")
    record[tail_pos + 10 : tail_pos + 10] = (
        b"\x01\x00\x00\x00\x0A\x00\xFF\xFF"
        b"\x01\x00\x00\x00\x01\x00\x00\x00" + link_marker
    )
    behavior_name = b"\x04\x00LEvt\x00\x00TVEd"
    behavior_pos = record.index(behavior_name)
    record[behavior_pos : behavior_pos + len(behavior_name)] = (
        b"\x04\x00LEvt\x0B\x00Behavior #1TVEd"
    )

NAME_FLAG_DEFAULT = 0xFFFF

NAME_FLAG_OFFSET = 0x0E

def set_name_flag(record: bytes) -> bytes:
    """Mark whether an object's name was set by the author."""
    data = bytearray(record)
    name_tag = data.index(b"ItNa")
    struct.pack_into("<H", data, name_tag + NAME_FLAG_OFFSET, NAME_FLAG_DEFAULT)
    return bytes(data)

def patch_active_record(
    template: bytes,
    *,
    item_id: int,
    object_id: int,
    name: bytes,
    image_id: int,
    icon_id: int,
    include_default_behavior: bool = True,
    behavior_link_marker: bytes = b"\x01OB~",
) -> bytes:
    """Write recovered values into an Active object's record."""
    if not template.startswith(ACTIVE_RECORD):
        raise ValueError("Active template has an unexpected header")
    if not name.endswith(b"\x00"):
        raise ValueError("editor object name must be NUL-terminated")

    record = bytearray(template)
    struct.pack_into("<I", record, 0x14, item_id)

    name_tag = record.index(b"ItNa")
    struct.pack_into("<H", record, name_tag + 0x1A, len(name))
    name_pos = name_tag + 0x24
    icon_tag = record.index(b"\x04\x00ItIc", name_pos)
    record[name_pos:icon_tag] = name

    palette_tag = record.index(b"PSDd")
    struct.pack_into("<I", record, palette_tag + 4, object_id)
    icon_tag = record.index(b"icnI")
    struct.pack_into("<I", record, icon_tag + 4, icon_id)

    animation_tag = record.index(b"AnSt")
    image_tag = record.index(b"Imag", animation_tag)
    struct.pack_into("<I", record, image_tag + 4, image_id)

    if include_default_behavior:

        add_default_behavior(record, behavior_link_marker)
    return set_name_flag(bytes(record))

def event_object_record(
    object_id: int,
    name: bytes,
    *,
    frame_item_id: int | None = None,
    object_type_id: int = 2,
    object_type: bytes = b"Sprite",
    instance_link: int = 0xFFFFFFFF,
) -> bytes:
    """The registry entry that lets events refer to an object."""
    if frame_item_id is None:
        frame_item_id = object_id
    clean_name = name[:-1]
    return (
        b"EvOi"
        + struct.pack("<I", object_id)
        + struct.pack("<HH", 1, object_type_id)
        + struct.pack("<I", len(clean_name))
        + clean_name
        + struct.pack("<I", len(object_type))
        + object_type
        + b"\x00\x00"
        + struct.pack("<I", frame_item_id)
        + struct.pack("<I", instance_link)
    )
