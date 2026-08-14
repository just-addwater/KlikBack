# GENERATED — do not edit by hand. This file is produced by KlikBack's
# sync tooling; changes belong in the source it is generated from.
#
# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""Rebuild a Sub-Application object -- a project embedded inside another.

A Sub-Application either carries its child project inside itself or points at
one beside it on disk. Both forms are rebuilt, and a stored path is rewritten
to where the child was actually written rather than left pointing at wherever
it lived on the machine that compiled it.
"""

from __future__ import annotations
import struct
from dataclasses import dataclass

SUBAPPLICATION_TYPE = 9

SUBAPPLICATION_IDENTIFIER = b"CCA "

@dataclass(frozen=True)
class RuntimeSubApplication:
    """What that object holds: its child, its window, and how it is displayed.
    """
    data_offset: int
    leading_value: int
    width: int
    height: int
    reserved: int
    options: int
    path: bytes

def runtime_subapplication(definition: bytes) -> RuntimeSubApplication:
    """A Sub-Application as the compiled game stored it."""
    if len(definition) < 0x30 or definition[0x2C:0x30] != SUBAPPLICATION_IDENTIFIER:
        raise ValueError("runtime object is not a Sub-Application definition")
    data_offset = struct.unpack_from("<I", definition, 0x0C)[0]
    if data_offset + 17 > len(definition):
        raise ValueError("Sub-Application data offset is outside the definition")
    leading, width, height, reserved, options = struct.unpack_from(
        "<IHHII", definition, data_offset
    )
    path_start = data_offset + 16
    path_end = definition.find(b"\0", path_start)
    if path_end < 0:
        raise ValueError("Sub-Application runtime path is not NUL-terminated")
    if path_end + 1 != len(definition):
        raise ValueError("Sub-Application definition has unparsed trailing bytes")
    return RuntimeSubApplication(
        data_offset=data_offset,
        leading_value=leading,
        width=width,
        height=height,
        reserved=reserved,
        options=options,
        path=definition[path_start:path_end],
    )

def build_subapplication_tail(
    icon: int, path: bytes, width: int, height: int, options: int
) -> bytes:
    """Write those settings into the project's own record shape."""
    if b"\0" in path:
        raise ValueError("editor Sub-Application path must not contain NUL")
    if not 0 <= width <= 0xFFFFFFFF or not 0 <= height <= 0xFFFFFFFF:
        raise ValueError("Sub-Application dimensions do not fit editor u32 fields")
    return (
        b"icnI"
        + struct.pack("<II", icon, len(path))
        + path
        + struct.pack("<III", width, height, options)
    )

def subapplication_record(
    template: bytes,
    *,
    name: bytes,
    object_id: int,
    icon: int,
    runtime: RuntimeSubApplication,
    editor_path: bytes | None = None,
) -> bytes:
    """Build the whole record."""
    if not runtime.path:
        raise ValueError(
            "same-application Sub-Application mode is not yet supported"
        )
    if runtime.leading_value != 0 or runtime.reserved != 0:
        raise ValueError(
            "external Sub-Application has unexpected nonzero mode fields"
        )

    from klikback.core.common.solo_object_reconstruct import patch_frame_object_id, patch_name, zero_prop_scratch

    record = patch_name(bytearray(template), name)
    zero_prop_scratch(record)
    patch_frame_object_id(record, object_id)
    icon_start = record.index(b"icnI")
    tail = build_subapplication_tail(
        icon,
        runtime.path if editor_path is None else editor_path,
        runtime.width,
        runtime.height,
        runtime.options,
    )
    return bytes(record[:icon_start]) + tail
