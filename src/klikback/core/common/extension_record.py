# GENERATED — do not edit by hand. This file is produced by KlikBack's
# sync tooling; changes belong in the source it is generated from.
#
# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""The record an extension object stores, around the module's own settings.

An extension object's settings belong to its module and are carried through
untouched; what this handles is the record the project wraps around them.
"""

from __future__ import annotations
import struct
from dataclasses import dataclass

SUBTYPE_SENTINEL = b"nil"

MODULE_STAMP = 0x59082516

@dataclass(frozen=True)
class ExtensionRecord:
    """One extension object's record."""
    start: int
    icon_start: int
    icon_handle: int
    subtype: bytes
    module: str
    stamp: int
    editdata: bytes
    end: int

def parse_extension_tail(cca: bytes, icon_start: int) -> ExtensionRecord:
    """Read the record's trailing part."""
    pos = icon_start + 4
    icon_handle = struct.unpack_from("<I", cca, pos)[0]
    pos += 4
    subtype_length = struct.unpack_from("<I", cca, pos)[0]
    subtype = cca[pos + 4 : pos + 4 + subtype_length]
    pos += 4 + subtype_length
    sentinel = struct.unpack_from("<I", cca, pos)[0]
    if sentinel != 0xFFFFFFFF:
        raise ValueError(f"expected 0xFFFFFFFF after subtype, found {sentinel:#x}")
    pos += 4
    name_length = struct.unpack_from("<I", cca, pos)[0]
    module = cca[pos + 4 : pos + 4 + name_length].decode("latin-1")
    pos += 4 + name_length
    stamp, zero = struct.unpack_from("<II", cca, pos)
    if zero != 0:
        raise ValueError(f"expected zero after the stamp, found {zero:#x}")
    pos += 8
    size = struct.unpack_from("<H", cca, pos)[0]
    editdata = cca[pos + 2 : pos + 2 + size]
    if len(editdata) != size:
        raise ValueError("editdata runs past the end of the file")
    declared = struct.unpack_from("<h", editdata, 0)[0]
    if declared != size:
        raise ValueError(f"editdata size {size} != its own extSize {declared}")
    return ExtensionRecord(
        start=0,
        icon_start=icon_start,
        icon_handle=icon_handle,
        subtype=subtype,
        module=module,
        stamp=stamp,
        editdata=editdata,
        end=pos + 2 + size,
    )

def build_extension_tail(
    icon_handle: int,
    module: str,
    editdata: bytes,
    subtype: bytes = SUBTYPE_SENTINEL,
    stamp: int = MODULE_STAMP,
) -> bytes:
    """Write it back."""
    encoded = module.encode("latin-1")
    return (
        b"icnI"
        + struct.pack("<I", icon_handle)
        + struct.pack("<I", len(subtype))
        + subtype
        + b"\xff\xff\xff\xff"
        + struct.pack("<I", len(encoded))
        + encoded
        + struct.pack("<II", stamp, 0)
        + struct.pack("<H", len(editdata))
        + editdata
    )
