# GENERATED — do not edit by hand. This file is produced by KlikBack's
# sync tooling; changes belong in the source it is generated from.
#
# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""Read the package a compiled game wraps around its project.

Before any frame can be rebuilt, the outer package has to be opened: which
version it is, what chunks it holds, which objects and frames are inside.
"""

from __future__ import annotations
import struct
from pathlib import Path
from klikback.core.common.compare import Chunk, read_chunks
from klikback.core.common.compression_probe import application_bytes, overlay_offset
from klikback.core.common.exe_to_cca import decompress_chunk
from klikback.core.common.object_analysis import split_object_chunks

def load_outer(path: Path) -> list[Chunk]:
    """Open a compiled game's outer package."""
    data = application_bytes(path.read_bytes())
    overlay = overlay_offset(data)
    if overlay < 0:
        raise ValueError(f"{path}: no MMF PAME overlay")
    return read_chunks(data, overlay + 0x10, len(data))

PACKAGE_VERSION_MMF10 = 0x0300

PACKAGE_VERSION_MMF15 = 0x0301

def package_version(path: Path) -> int | None:
    """Which version of the package format this file is."""
    data = application_bytes(path.read_bytes())
    overlay = overlay_offset(data)
    if overlay < 0:
        return None
    return struct.unpack_from("<H", data, overlay + 4)[0]

def chunk_payload(chunk: Chunk) -> bytes:
    """The contents of one chunk of the package."""
    return decompress_chunk(chunk) if chunk.flags else chunk.payload

def objects_from(outer: list[Chunk]) -> list[dict]:
    """The objects the package declares."""
    bank = next(c for c in outer if c.chunk_id == 0x2229)
    entries: list[dict] = []
    for chunks in split_object_chunks(chunk_payload(bank)):
        record: dict = {"name": None, "definition": None}
        for chunk in chunks:
            payload = chunk_payload(chunk)
            if chunk.chunk_id == 0x4444:
                record["header"] = payload
                record["id"], record["type"] = struct.unpack_from("<HH", payload, 0)
            elif chunk.chunk_id == 0x4445:
                record["name"] = payload.split(b"\0")[0].decode("latin-1")
            elif chunk.chunk_id == 0x4446:
                record["definition"] = payload
        entries.append(record)
    return entries

def frames_from(outer: list[Chunk]) -> list[list[Chunk]]:
    """The frames the package declares."""
    return [
        read_chunks(c.payload, 0, len(c.payload))
        for c in outer
        if c.chunk_id == 0x3333
    ]
