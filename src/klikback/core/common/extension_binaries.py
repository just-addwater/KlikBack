# GENERATED — do not edit by hand. This file is produced by KlikBack's
# sync tooling; changes belong in the source it is generated from.
#
# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""Find the extension modules a compiled game carries inside itself.

A game embeds the modules it uses, one executable image after another inside
its own file. Locating them is what makes the modules recoverable on a machine
that has never had them installed.
"""

from __future__ import annotations
import struct
from dataclasses import dataclass
from pathlib import Path
from klikback.core.common.compression_probe import application_bytes, overlay_offset

EMBEDDED_MODULE_CHUNK = 0x222C

TERMINATOR = 0x7F7F

@dataclass(frozen=True)
class EmbeddedModule:
    """One embedded module: what it is called and where its bytes are."""
    filename: str
    image: bytes
    offset: int

def _walks_to_terminator(data: bytes, start: int, terminator: int) -> bool:
    pos = start
    while pos < terminator:
        chunk_id, _flags, size = struct.unpack_from("<HHI", data, pos)
        if chunk_id != EMBEDDED_MODULE_CHUNK or size <= 0:
            return False
        pos += 8 + size
    return pos == terminator

def find_module_stream(data: bytes) -> int:
    """Locate one module image inside the game."""
    overlay = overlay_offset(data)
    if overlay < 0:
        raise ValueError("no MMF PAME overlay")

    terminator = overlay - 8
    if terminator < 0:
        return -1
    chunk_id, _flags, size = struct.unpack_from("<HHI", data, terminator)
    if chunk_id != TERMINATOR or size != 0:
        return -1

    marker = struct.pack("<HH", EMBEDDED_MODULE_CHUNK, 0)
    position = data.find(marker, 0x1000)
    while 0 <= position < terminator:
        if _walks_to_terminator(data, position, terminator):
            return position
        position = data.find(marker, position + 1)
    return -1

def embedded_modules(path: Path) -> list[EmbeddedModule]:

    """Every module image the game carries."""
    data = application_bytes(path.read_bytes())
    start = find_module_stream(data)
    if start < 0:
        return []
    overlay = overlay_offset(data)
    modules: list[EmbeddedModule] = []
    pos = start
    while pos < overlay:
        chunk_id, _flags, size = struct.unpack_from("<HHI", data, pos)
        if chunk_id == TERMINATOR:
            if pos + 8 != overlay:
                raise ValueError("module stream terminator is misplaced")
            break
        if chunk_id != EMBEDDED_MODULE_CHUNK:
            raise ValueError(f"unexpected chunk 0x{chunk_id:04X} in module stream")
        body = data[pos + 8 : pos + 8 + size]
        filename, _, image = body.partition(b"\0")
        modules.append(
            EmbeddedModule(filename.decode("latin-1"), image, pos + 8 + len(filename) + 1)
        )
        pos += 8 + size
    return modules
