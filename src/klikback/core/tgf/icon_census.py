# GENERATED — do not edit by hand. This file is produced by KlikBack's
# sync tooling; changes belong in the source it is generated from.
#
# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""Which piece of a 1996 object's artwork its editor icon is drawn from.

Different object types keep their art in different places, so generating a
replacement icon starts with knowing where to look: an active's first
animation frame, a display object's first frame, a backdrop's own image.
"""

from __future__ import annotations
import struct
import klikback.core.tgf.format as tgf

OFF_MOSAIC_IMAGE = 0x36

def sprite_first_frame(data: bytes) -> int | None:
    """The first frame of an animated object's art."""
    if len(data) < 0x30 or data[0x2A:0x2E] != b"SPRI":
        return None
    sprite = 0x2E
    if sprite + 2 > len(data):
        return None
    (sprite_len,) = struct.unpack_from("<H", data, sprite)
    ani = sprite + sprite_len
    if ani + 0x24 > len(data):
        return None
    for slot in range(16):
        (aptr,) = struct.unpack_from("<H", data, ani + 4 + 2 * slot)
        if aptr >= 0x8000:
            continue
        adata = ani + aptr
        if adata + 0x40 > len(data):
            return None
        for direction in range(32):
            (dptr,) = struct.unpack_from("<H", data, adata + 2 * direction)
            if dptr >= 0x8000:
                continue
            ddata = adata + dptr
            if ddata + 0x0A > len(data):
                return None
            (frames,) = struct.unpack_from("<H", data, ddata + 6)
            if frames < 1:
                return None
            (image_id,) = struct.unpack_from("<H", data, ddata + 8)
            return image_id
        return None
    return None

def display_first_frame(data: bytes, object_type: int) -> int | None:
    """The first frame of a display object's art."""
    signatures = {0x05: b"SCRE", 0x06: b"LIVE", 0x07: b"CNTR"}
    sig = signatures.get(object_type)
    if sig is None or len(data) < 0x30 or data[0x2A:0x2E] != sig:
        return None
    pos = 0x2E
    if object_type == 0x07:

        if pos + 2 > len(data):
            return None
        (attr_len,) = struct.unpack_from("<H", data, pos)
        pos += attr_len
    if pos + 10 > len(data):
        return None
    length, display_type = struct.unpack_from("<HH", data, pos)
    if object_type == 0x07 and display_type not in (1, 4):
        return None
    (image_id,) = struct.unpack_from("<H", data, pos + 8)
    return image_id

def source_handle(obj: tgf.ObjectDefinition, head: bytes) -> int | None:
    """Which stored image an object's icon should be drawn from."""
    data_block = next(
        (db.data for db in obj.blocks if db.ident == 0x00 and db.data), None)
    if obj.object_type in (0x00, 0x01):
        return struct.unpack_from("<H", head, OFF_MOSAIC_IMAGE)[0]
    if obj.object_type == 0x02 and data_block:
        return sprite_first_frame(data_block)
    if obj.object_type in (0x05, 0x06, 0x07) and data_block:
        return display_first_frame(data_block, obj.object_type)
    return None
