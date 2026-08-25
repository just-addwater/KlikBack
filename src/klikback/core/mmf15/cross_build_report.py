# GENERATED — do not edit by hand. This file is produced by KlikBack's
# sync tooling; changes belong in the source it is generated from.
#
# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""Compare what a game was built with against what an editor has installed."""

from __future__ import annotations
import hashlib
import struct
from pathlib import Path
from klikback.core.common.extension_inventory import chunk_payload, load_outer
from klikback.core.common.container import EXTENSION_SIGNATURE, spans

EXTENSION_CHUNK = 0x2234

def digest(data: bytes) -> str:
    """A stable identity for a module, for telling two builds of it apart."""
    return hashlib.sha256(data).hexdigest()

def runtime_extensions(exe: Path) -> tuple | None:
    """The extension modules a compiled game carries."""
    chunks = [chunk for chunk in load_outer(exe) if chunk.chunk_id == EXTENSION_CHUNK]
    if not chunks:
        return None
    if len(chunks) != 1:
        raise ValueError(f"runtime extension table occurs {len(chunks)} times")
    data = chunk_payload(chunks[0])
    if len(data) < 4:
        raise ValueError("runtime extension table is truncated")
    count, high_water = struct.unpack_from("<HH", data, 0)
    cursor = 4
    keys = []
    metadata = []
    for index in range(count):
        if cursor + 16 > len(data):
            raise ValueError(f"runtime extension entry {index} is truncated")
        kind, slot, signature = struct.unpack_from("<HHI", data, cursor)
        private = data[cursor + 8:cursor + 16]
        cursor += 16
        if signature != EXTENSION_SIGNATURE:
            raise ValueError(f"runtime extension entry {index} has a bad signature")
        end = data.find(b"\0", cursor)
        if end < 0:
            raise ValueError(f"runtime extension entry {index} has no filename")
        filename = data[cursor:end].decode("ascii")
        subtype_end = data.find(b"\0", end + 1)
        if subtype_end < 0:
            raise ValueError(
                f"runtime extension entry {index} subtype is unterminated"
            )
        subtype = data[end + 1:subtype_end].decode("ascii")
        cursor = subtype_end + 1

        keys.append((kind, slot, filename, subtype))
        metadata.append(digest(private))
    if cursor != len(data):
        raise ValueError(f"{len(data) - cursor} bytes remain after runtime extension table")
    return count, high_water, tuple(keys), tuple(metadata)

def editor_extensions(cca: Path | bytes) -> tuple:
    """The modules installed for an editor to use."""
    data = cca if isinstance(cca, bytes) else cca.read_bytes()
    region = next(span for span in spans(data) if span.name == "extensions")
    payload = data[region.start:region.end]
    depth, count = struct.unpack_from("<II", payload, 0)
    cursor = 8
    entries = []
    for index in range(count):
        slot = struct.unpack_from("<I", payload, cursor)[0]
        cursor += 4
        fields = []
        for _ in range(2):
            length = struct.unpack_from("<I", payload, cursor)[0]
            cursor += 4
            fields.append(payload[cursor:cursor + length].decode("ascii"))
            cursor += length
        signature, tail = struct.unpack_from("<II", payload, cursor)
        cursor += 8
        if signature != EXTENSION_SIGNATURE or tail != 0:
            raise ValueError(f"editor extension entry {index} has a bad trailer")
        entries.append((slot, *fields))
    if cursor != len(payload):
        raise ValueError(f"{len(payload) - cursor} bytes remain after editor extension table")
    return depth, tuple(entries)
