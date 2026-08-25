# GENERATED — do not edit by hand. This file is produced by KlikBack's
# sync tooling; changes belong in the source it is generated from.
#
# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
from __future__ import annotations
import struct
from klikback.core.common.compression_probe import decompress_clickteam_stream_with_consumed

TRAILER_CLASS = b"CCompFileInfo"

class NotPacked(Exception):
    pass

def pe_image_end(data: bytes) -> int:
    if not data.startswith(b"MZ"):
        raise NotPacked("not a PE image")
    if len(data) < 0x40:
        raise NotPacked("truncated DOS header")
    (pe,) = struct.unpack_from("<I", data, 0x3C)
    if pe + 24 > len(data) or data[pe : pe + 4] != b"PE\0\0":
        raise NotPacked("no PE signature")
    (sections,) = struct.unpack_from("<H", data, pe + 6)
    (optional,) = struct.unpack_from("<H", data, pe + 20)
    table = pe + 24 + optional
    if table + sections * 40 > len(data):
        raise NotPacked("section table runs past the file")
    end = 0
    for index in range(sections):
        entry = table + index * 40
        raw_size, raw_pointer = struct.unpack_from("<II", data, entry + 16)
        if raw_pointer:
            end = max(end, raw_pointer + raw_size)
    if not end:
        raise NotPacked("no section carries file bytes")
    return end

def _read_cstring(data: bytes, offset: int) -> tuple[str, int]:
    if offset >= len(data):
        raise NotPacked("string runs past the trailer")
    length = data[offset]
    if length >= 0xFF:
        raise NotPacked("long-form CString in the trailer")
    end = offset + 1 + length
    if end > len(data):
        raise NotPacked("string runs past the trailer")
    return data[offset + 1 : end].decode("latin-1"), end

def trailer_names(data: bytes, trailer: int) -> list[dict]:
    if data.find(TRAILER_CLASS, trailer) < 0:
        return []
    try:
        offset = trailer + 4
        (count,) = struct.unpack_from("<H", data, offset)
        offset += 2
        if not 0 < count <= 64:
            return []
        members: list[dict] = []
        for index in range(count):
            (tag,) = struct.unpack_from("<H", data, offset)
            offset += 2
            if tag == 0xFFFF:
                offset += 2
                (name_length,) = struct.unpack_from("<H", data, offset)
                offset += 2 + name_length
            elif not tag & 0x8000:
                return []
            offset += 8
            offset += 1
            name, offset = _read_cstring(data, offset)
            offset += 8
            start, end = struct.unpack_from("<II", data, offset)
            offset += 8
            members.append({"name": name, "start": start, "end": end})
        return members
    except (struct.error, IndexError, UnicodeDecodeError):
        return []

def pack_members(data: bytes) -> list[dict]:
    image_end = pe_image_end(data)
    if image_end + 4 > len(data):
        raise NotPacked("no room for a pack block")
    (declared,) = struct.unpack_from("<I", data, image_end)
    block_end = image_end + 4 + declared
    if declared < 4 or block_end > len(data):
        raise NotPacked(f"pack length {declared} does not fit the file")
    if data.find(TRAILER_CLASS, block_end) < 0:
        raise NotPacked("no CCompFileInfo trailer past the pack block")

    named = trailer_names(data, block_end)
    by_start = {entry["start"]: entry for entry in named}

    members: list[dict] = []
    offset = 4
    while offset < declared + 4:
        absolute = image_end + offset
        payload, consumed = decompress_clickteam_stream_with_consumed(
            data[absolute:block_end]
        )
        entry = by_start.get(offset)
        members.append(
            {
                "name": entry["name"] if entry else None,
                "start": offset,
                "end": offset + consumed,
                "length": consumed,
                "bytes": payload,
            }
        )
        offset += consumed
    if offset != declared + 4:
        raise NotPacked(
            f"member walk ended at {offset}, block ends at {declared + 4}"
        )

    for entry in named:
        if entry["start"] == entry["end"]:
            members.append(
                {
                    "name": entry["name"],
                    "start": entry["start"],
                    "end": entry["end"],
                    "length": 0,
                    "bytes": b"",
                }
            )
    return members

def packed_application(data: bytes) -> bytes | None:
    try:
        members = pack_members(data)
    except NotPacked:
        return None
    except ValueError:

        return None
    for member in members:
        payload = member["bytes"]
        if not payload.startswith(b"MZ"):
            continue
        try:
            floor = pe_image_end(payload)
        except NotPacked:
            continue
        if payload.find(b"PAME", floor) >= 0:
            return payload
    return None
