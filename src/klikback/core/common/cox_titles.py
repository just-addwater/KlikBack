# GENERATED — do not edit by hand. This file is produced by KlikBack's
# sync tooling; changes belong in the source it is generated from.
#
# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""Read an extension module's editor display title out of the module itself.

Every extension shows a name in the editor — "Array", "Window Control",
"Date & Time" — and a rebuilt project has to write those names into its own
module list. The title turns out to be **a property of the module, not of the
project**: a given module always declares the same title, everywhere it is
used.

That is what makes a game titleable on a machine that has never had its
extensions installed. A compiled game carries copies of the modules it uses,
so the titles can be read out of those copies. Where a module declares no
title at all — some builds have it stripped — the module's filename stands in
and the substitution is reported, since a wrong-looking name in the editor is
better than a refusal to rebuild the game at all.
"""

from __future__ import annotations
import struct
from pathlib import Path

TITLE_STRING_ID = 2

RT_STRING = 6

RT_MENU = 4

STRINGS_PER_BLOCK = 16

PE_MAGIC_32 = 0x10B

RESOURCE_DIRECTORY_INDEX = 2

class CoxProblem(Exception):
    """Raised when a file is not a readable extension module."""

def _sections(data: bytes) -> list[tuple[int, int, int, int]]:
    if data[:2] != b"MZ":
        raise CoxProblem("not a DOS/PE image")
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    if data[pe:pe + 4] != b"PE\0\0":
        raise CoxProblem("no PE signature")
    count = struct.unpack_from("<H", data, pe + 6)[0]
    optional_size = struct.unpack_from("<H", data, pe + 20)[0]
    table = pe + 24 + optional_size
    out = []
    for index in range(count):
        off = table + index * 40
        virtual_size, virtual_address, raw_size, raw_address = struct.unpack_from(
            "<IIII", data, off + 8
        )
        out.append((virtual_address, virtual_size, raw_address, raw_size))
    return out

def _offset(sections, rva: int) -> int | None:
    for virtual_address, virtual_size, raw_address, raw_size in sections:
        span = max(virtual_size, raw_size)
        if virtual_address <= rva < virtual_address + span:
            return raw_address + (rva - virtual_address)
    return None

def _walk(data, sections, base, off, path, out, depth=0):
    if depth > 3:
        raise CoxProblem("resource directory nests deeper than type/name/language")
    named, ids = struct.unpack_from("<HH", data, off + 12)
    for index in range(named + ids):
        entry = off + 16 + index * 8
        name, target = struct.unpack_from("<II", data, entry)
        key = name & 0x7FFFFFFF
        if target & 0x80000000:
            _walk(data, sections, base, base + (target & 0x7FFFFFFF),
                  path + [key], out, depth + 1)
        else:
            rva, size = struct.unpack_from("<II", data, base + target)
            out.append((tuple(path + [key]), _offset(sections, rva), size))

def resource_entries(data: bytes) -> list[tuple[tuple[int, ...], int | None, int]]:
    """The resources a module carries, which is where its title is stored."""
    sections = _sections(data)
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    optional = pe + 24
    magic = struct.unpack_from("<H", data, optional)[0]
    directories = optional + (96 if magic == PE_MAGIC_32 else 112)
    rva, _size = struct.unpack_from(
        "<II", data, directories + RESOURCE_DIRECTORY_INDEX * 8
    )
    if not rva:
        return []
    base = _offset(sections, rva)
    if base is None:
        raise CoxProblem("the resource directory RVA is outside every section")
    out: list[tuple[tuple[int, ...], int | None, int]] = []
    _walk(data, sections, base, base, [], out)
    return out

def _block_strings(data: bytes, off: int, size: int) -> list[str]:
    out = []
    pos, end = off, off + size
    for _index in range(STRINGS_PER_BLOCK):
        if pos + 2 > end:
            break
        (length,) = struct.unpack_from("<H", data, pos)
        pos += 2
        if pos + length * 2 > end:
            raise CoxProblem("a string overruns its RT_STRING block")
        out.append(data[pos:pos + length * 2].decode("utf-16-le"))
        pos += length * 2
    return out

def title_from_bytes(data: bytes) -> str | None:
    """The same, read from a module already in memory — as a game's embedded copy is.
    """
    block = TITLE_STRING_ID // STRINGS_PER_BLOCK + 1
    index = TITLE_STRING_ID % STRINGS_PER_BLOCK
    for key, off, size in resource_entries(data):
        if key[0] != RT_STRING or off is None or len(key) < 2 or key[1] != block:
            continue
        strings = _block_strings(data, off, size)
        if index < len(strings) and strings[index]:
            return strings[index]
    return None

def cox_title(path: Path) -> str | None:
    """The display title one extension module declares for itself."""
    return title_from_bytes(path.read_bytes())

def installed_titles(directory: Path) -> dict[str, str]:
    """The titles of the extension modules installed in a folder on this machine.

    Only consulted when a folder has been named. With nothing to compare against,
    every module reads as "not installed" and the resulting report says nothing
    worth reading.
    """
    titles: dict[str, str] = {}
    for module in sorted(directory.glob("*.cox")):
        try:
            title = cox_title(module)
        except (CoxProblem, struct.error, UnicodeDecodeError):
            continue
        if title:
            titles[module.name.lower()] = title
    return titles
