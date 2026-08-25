# GENERATED — do not edit by hand. This file is produced by KlikBack's
# sync tooling; changes belong in the source it is generated from.
#
# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""Rebuild the extension objects a game uses, and name them the way the editor does.

An extension object is one whose behaviour comes from a module rather than
from the editor itself. Two things have to be right for it to open properly:
the object's own stored settings, which come from the compiled game, and the
module's display title, which is what the editor shows in place of a type
name.

**Titles come from a measured chain, ending in the module's own filename.**
The extensions installed on this machine are asked first when a folder has
been named; then the copies the game carries, which declare their own titles;
and when nothing names a module, its filename stands in and the substitution
is reported as a loss. The module itself is always carried intact — a
stand-in title costs a label, not a feature.
"""

from __future__ import annotations
import struct
from klikback.core.mmf1.extension_module_table import ExtensionModule, module_by_index
from klikback.core.common.extension_record import MODULE_STAMP, build_extension_tail

EXTENSION_TYPE_BASE = 32

EDITDATA_OFFSET_FIELD = 0x24

LIBRARY_ANCHOR = b"\x04\x00Keyw\x00\x00\xd4BIL"

def is_extension_type(object_type: int) -> bool:
    """Whether an object's type means "provided by a module"."""
    return object_type >= EXTENSION_TYPE_BASE

def extension_editdata(definition: bytes) -> bytes:
    """The object's own stored settings, as the module wrote them."""
    offset = struct.unpack_from("<I", definition, EDITDATA_OFFSET_FIELD)[0]
    editdata = definition[offset:]
    declared = struct.unpack_from("<h", editdata, 0)[0]
    if declared != len(editdata):
        raise ValueError(
            f"extension data claims {declared} bytes but the definition "
            f"supplies {len(editdata)} from offset {offset}"
        )
    return editdata

def extension_module(modules: list[ExtensionModule], object_type: int) -> str:
    """Which module an extension object belongs to."""
    return module_by_index(modules, object_type - EXTENSION_TYPE_BASE).filename

def extension_library_title(filename: str) -> str:
    """The display title for one module."""
    return filename.rsplit(".", 1)[0]

def recovered_library_titles(
    exe_path, extension_dirs=None
) -> dict[str, str]:
    """Titles for every module a game uses, by the measured chain."""

    from klikback.core.common.cox_titles import title_from_bytes
    from klikback.core.common.extension_binaries import embedded_modules

    titles: dict[str, str] = {}
    for directory in reversed(list(extension_dirs or ())):
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.cox")):
            try:
                title = title_from_bytes(path.read_bytes())
            except Exception:
                continue
            if title:
                titles[path.name.casefold()] = title
    try:
        modules = embedded_modules(exe_path)
    except Exception:
        modules = []
    for module in modules:
        try:
            title = title_from_bytes(module.image)
        except Exception:
            continue
        if title:
            from pathlib import Path as _Path

            titles[_Path(module.filename).name.casefold()] = title
    return titles

def build_library_table(
    modules: list[ExtensionModule],
    titles: dict[str, str] | None = None,
    synthesised: list[str] | None = None,
) -> bytes:
    """The module list a project declares."""
    out = struct.pack("<I", len(modules))
    for module in modules:
        index = module.index
        name = module.filename.encode("latin-1")
        recovered = (titles or {}).get(module.filename.casefold())
        if recovered is None and synthesised is not None:
            synthesised.append(module.filename)
        text = recovered or extension_library_title(module.filename)
        title = text.encode("latin-1", errors="replace")
        out += (
            struct.pack("<I", index)
            + struct.pack("<I", len(name))
            + name
            + struct.pack("<I", len(title))
            + title
            + struct.pack("<II", MODULE_STAMP, 0)
        )
    return out

def set_library_table(
    cca: bytes,
    modules: list[ExtensionModule],
    titles: dict[str, str] | None = None,
    synthesised: list[str] | None = None,
) -> bytes:
    """Write that list into the project."""
    anchor = cca.index(LIBRARY_ANCHOR) + len(LIBRARY_ANCHOR)
    count_pos = anchor + 4
    existing = struct.unpack_from("<I", cca, count_pos)[0]
    if existing:
        raise ValueError("scaffold already carries a non-empty library table")
    return (
        cca[:count_pos]
        + build_library_table(modules, titles, synthesised)
        + cca[count_pos + 4 :]
    )

def extension_record(
    template: bytes,
    *,
    name: bytes,
    object_id: int,
    icon: int,
    module: str,
    editdata: bytes,
) -> bytes:
    """Rebuild one extension object's record."""

    from klikback.core.common.solo_object_reconstruct import patch_frame_object_id, patch_name, zero_prop_scratch

    record = patch_name(bytearray(template), name)
    zero_prop_scratch(record)
    patch_frame_object_id(record, object_id)
    icon_start = record.index(b"icnI")
    return bytes(record[:icon_start]) + build_extension_tail(
        icon, module, editdata
    )
