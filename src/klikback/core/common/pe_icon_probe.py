# GENERATED — do not edit by hand. This file is produced by KlikBack's
# sync tooling; changes belong in the source it is generated from.
#
# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""Read the Windows icon resources a compiled game carries.

A standalone keeps its application icons where any Windows program does, in
the executable's own resource directory. That is where the icon on the
inspect card comes from, and it is also where a rebuild gets the application
icons to put back into the project — the game's own artwork, not a stand-in.
"""

from __future__ import annotations
import struct
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class Resource:
    """One resource entry: what it is, which id it has, and where its bytes are.
    """
    type_id: int
    name_id: int
    language_id: int
    data: bytes

def pe_resources(path: Path) -> list[Resource]:
    """Every resource in the executable, by type and id, with its bytes.

    Windows stores an executable's resources in a directory three levels deep —
    type, then id, then language — and describes where things live in memory
    rather than in the file. So the walk does two jobs: follow the three levels,
    and translate each address back into a file position through the section
    table the executable carries for that purpose. Both 32- and 64-bit
    executables are handled; they differ only in where the directory list starts.

    Entries named with a string rather than a number are skipped. Everything this
    reads for — icons, icon groups, the version stamp — is numbered, and a named
    entry is somebody else's data.

    What comes back is the raw bytes of each entry, with no attempt to say what
    they mean. Deciding that is the caller's job, and keeping the two apart is
    what lets the same reader serve the icon on the inspect card, the icons a
    rebuild puts back into the project, and the version stamp that helps identify
    which build made the game.
    """
    from klikback.core.common.compression_probe import application_bytes

    return pe_resources_in(application_bytes(path.read_bytes()), str(path))

def pe_resources_in(data: bytes, path: str = "<bytes>") -> list[Resource]:
    pe_pos = struct.unpack_from("<I", data, 0x3C)[0]
    if data[pe_pos : pe_pos + 4] != b"PE\0\0":
        raise ValueError(f"{path}: not a PE executable")
    section_count = struct.unpack_from("<H", data, pe_pos + 6)[0]
    optional_size = struct.unpack_from("<H", data, pe_pos + 20)[0]
    optional_pos = pe_pos + 24
    magic = struct.unpack_from("<H", data, optional_pos)[0]
    if magic == 0x10B:
        directory_pos = optional_pos + 96
    elif magic == 0x20B:
        directory_pos = optional_pos + 112
    else:
        raise ValueError(f"{path}: unsupported PE optional-header magic 0x{magic:X}")
    resource_rva, _resource_size = struct.unpack_from(
        "<II", data, directory_pos + 2 * 8
    )
    section_pos = optional_pos + optional_size
    sections: list[tuple[int, int, int]] = []
    for index in range(section_count):
        pos = section_pos + index * 40
        virtual_size, virtual_address, raw_size, raw_pos = struct.unpack_from(
            "<IIII", data, pos + 8
        )
        sections.append((virtual_address, max(virtual_size, raw_size), raw_pos))

    def file_offset(rva: int) -> int:
        for virtual_address, size, raw_pos in sections:
            if virtual_address <= rva < virtual_address + size:
                return raw_pos + rva - virtual_address
        raise ValueError(f"{path}: RVA 0x{rva:X} is outside the section table")

    resource_base = file_offset(resource_rva)

    def directory_entries(relative_pos: int) -> list[tuple[int, int]]:
        pos = resource_base + relative_pos
        named, numbered = struct.unpack_from("<HH", data, pos + 12)
        return [
            struct.unpack_from("<II", data, pos + 16 + index * 8)
            for index in range(named + numbered)
        ]

    resources: list[Resource] = []
    for type_name, type_offset in directory_entries(0):
        if type_name & 0x80000000:
            continue
        type_id = type_name & 0xFFFF
        for name, name_offset in directory_entries(type_offset & 0x7FFFFFFF):
            if name & 0x80000000:
                continue
            name_id = name & 0xFFFF
            for language, language_offset in directory_entries(
                name_offset & 0x7FFFFFFF
            ):
                if language & 0x80000000:
                    continue
                entry_pos = resource_base + (language_offset & 0x7FFFFFFF)
                data_rva, size = struct.unpack_from("<II", data, entry_pos)
                start = file_offset(data_rva)
                resources.append(
                    Resource(type_id, name_id, language & 0xFFFF, data[start : start + size])
                )
    return resources

def icon_dib_indices(data: bytes) -> tuple[int, int, bytes, bytes, bytes]:
    """Where the icon images sit inside the resource, ready to be read out."""
    header_size, width, doubled_height, _planes, bits = struct.unpack_from(
        "<IiiHH", data
    )
    if header_size != 40 or bits != 4 or width <= 0 or doubled_height <= 0:
        raise ValueError("only bottom-up 4-bit BITMAPINFOHEADER icons are supported")
    height = doubled_height // 2
    palette = data[40 : 40 + 16 * 4]
    color_stride = ((width * bits + 31) // 32) * 4
    mask_stride = ((width + 31) // 32) * 4
    color_pos = 40 + 16 * 4
    mask_pos = color_pos + color_stride * height
    rows: list[bytes] = []
    masks: list[bytes] = []
    for row in range(height - 1, -1, -1):
        packed = data[color_pos + row * color_stride : color_pos + (row + 1) * color_stride]
        indices = bytearray()
        for value in packed:
            indices.extend((value >> 4, value & 0x0F))
        rows.append(bytes(indices[:width]))
        masks.append(
            data[mask_pos + row * mask_stride : mask_pos + (row + 1) * mask_stride]
        )
    return width, height, b"".join(rows), b"".join(masks), palette

def decode_editor_icon(record: bytes) -> bytes:
    """Turn one stored icon image into the pixels the editor expects."""
    mode = record[0x12]
    if mode != 3:
        raise ValueError(f"unsupported editor icon mode {mode}")
    encoded = record[0x1C:]
    decoded = bytearray()
    pos = 0
    while True:
        control = encoded[pos]
        pos += 1
        if control == 0:
            break
        if control & 0x80:
            count = control & 0x7F
            decoded.extend(encoded[pos : pos + count])
            pos += count
        else:
            decoded.extend(encoded[pos : pos + 1] * control)
            pos += 1
    return bytes(decoded)
