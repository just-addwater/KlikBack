# GENERATED — do not edit by hand. This file is produced by KlikBack's
# sync tooling; changes belong in the source it is generated from.
#
# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""Read a project file as a list of chunks, for comparing one against another.
"""

from __future__ import annotations
import struct
from dataclasses import dataclass

@dataclass(frozen=True)
class Chunk:
    """One chunk: what it is, where it starts, how long it runs."""
    chunk_id: int
    flags: int
    payload: bytes

def read_chunks(data: bytes, start: int, limit: int) -> list[Chunk]:
    """Every chunk in a project file, with its tag and its bytes."""
    chunks: list[Chunk] = []
    pos = start
    while pos + 8 <= limit:
        chunk_id, flags, size = struct.unpack_from("<HHI", data, pos)
        end = pos + 8 + size
        if end > limit:
            raise ValueError(f"chunk 0x{chunk_id:04X} extends beyond its container")
        chunks.append(Chunk(chunk_id, flags, data[pos + 8 : end]))
        pos = end
        if chunk_id == 0x7F7F:
            break
    return chunks

def find_chunk(chunks: list[Chunk], chunk_id: int) -> Chunk:
    """The chunk carrying a given tag."""
    return next(chunk for chunk in chunks if chunk.chunk_id == chunk_id)
