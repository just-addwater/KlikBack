# GENERATED — do not edit by hand. This file is produced by KlikBack's
# sync tooling; changes belong in the source it is generated from.
#
# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""The table of extension modules a compiled game declares."""

from __future__ import annotations
import struct
from dataclasses import dataclass

@dataclass(frozen=True)
class ExtensionModule:
    """One declared module: what it is called and which slot it occupies."""
    index: int
    stamp: int
    filename: str

def module_by_index(modules: list[ExtensionModule], index: int) -> ExtensionModule:
    """The module an object refers to by position."""
    for module in modules:
        if module.index == index:
            return module
    available = sorted(m.index for m in modules)
    raise ValueError(f"no extension module in slot {index}; slots are {available}")

def parse_module_table(payload: bytes) -> tuple[list[ExtensionModule], int]:
    """Read the table of modules a game declares."""
    count, repeated = struct.unpack_from("<HH", payload, 0)
    modules: list[ExtensionModule] = []
    pos = 4
    for _ in range(count):
        entry_size, index = struct.unpack_from("<HH", payload, pos)
        end = pos + entry_size
        if entry_size < 9 or end > len(payload):
            raise ValueError(f"entry at {pos} claims {entry_size} bytes")
        stamp = struct.unpack_from("<I", payload, pos + 4)[0]
        name = payload[pos + 8 : end].split(b"\0")[0].decode("latin-1")
        modules.append(ExtensionModule(index, stamp, name))
        pos = end
    if pos != len(payload):
        raise ValueError(f"module table left {len(payload)-pos} trailing bytes")
    return modules, repeated
