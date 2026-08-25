# GENERATED — do not edit by hand. This file is produced by KlikBack's
# sync tooling; changes belong in the source it is generated from.
#
# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""Carve the extension modules a 1996 standalone embeds in its own executable.

**The extensions are not in the `.gam`/`.cca`.** The data file only *names*
what it depends on — one fixed-size record per extension, carrying the
module's filename and nothing of its code. So a data file alone cannot tell
you whether the game will open on this machine; it can only tell you what it
will ask for.

The **standalone executable** is where the code is. A game that needs an
extension this machine has never had is carrying its own copy, and that copy
can be lifted out whole. This is what makes an unprotected 1996 game usable
rather than merely readable: the modules travel with it.

Names come from the data file's own dependency records, so what is written
out is what the game asked for, spelled the way the game spelled it.
"""

from __future__ import annotations
import re
import struct
import sys
from pathlib import Path

NAME_RE = re.compile(rb"[A-Za-z0-9_\-]{2,30}\.(?:COX|GOX|CCX|GFX)", re.I)

def pe_extent(data: bytes, start: int) -> int | None:
    """How far one embedded module reaches, so the next one can be found."""
    try:
        if data[start:start + 2] != b"MZ":
            return None
        pe = struct.unpack_from("<I", data, start + 0x3C)[0]
        if data[start + pe:start + pe + 4] != b"PE\0\0":
            return None
        sections = struct.unpack_from("<H", data, start + pe + 6)[0]
        opt_size = struct.unpack_from("<H", data, start + pe + 20)[0]
        table = start + pe + 24 + opt_size
        end = 0
        for i in range(sections):
            entry = table + i * 40
            raw_size, raw_ptr = struct.unpack_from("<II", data, entry + 16)
            if raw_ptr:
                end = max(end, raw_ptr + raw_size)
        return end or None
    except (struct.error, IndexError):
        return None

def is_dll(blob: bytes) -> bool:
    """Whether a carved image is a library rather than the host program."""
    try:
        pe = struct.unpack_from("<I", blob, 0x3C)[0]
        return bool(struct.unpack_from("<H", blob, pe + 22)[0] & 0x2000)
    except (struct.error, IndexError):
        return False

def _rva_to_offset(blob: bytes, rva: int) -> int | None:
    try:
        pe = struct.unpack_from("<I", blob, 0x3C)[0]
        sections = struct.unpack_from("<H", blob, pe + 6)[0]
        opt_size = struct.unpack_from("<H", blob, pe + 20)[0]
        table = pe + 24 + opt_size
        for i in range(sections):
            e = table + i * 40
            virt_size, virt_addr = struct.unpack_from("<II", blob, e + 8)
            raw_size, raw_ptr = struct.unpack_from("<II", blob, e + 16)
            if virt_addr <= rva < virt_addr + max(virt_size, raw_size):
                return raw_ptr + (rva - virt_addr)
    except (struct.error, IndexError):
        return None
    return None

def internal_name(blob: bytes) -> str | None:
    """The name a carved module gives for itself, read from its own resources.
    """
    try:
        pe = struct.unpack_from("<I", blob, 0x3C)[0]
        opt = pe + 24
        magic = struct.unpack_from("<H", blob, opt)[0]

        dirs = opt + (0x60 if magic == 0x10B else 0x70)
        export_rva = struct.unpack_from("<I", blob, dirs)[0]
        if not export_rva:
            return None
        off = _rva_to_offset(blob, export_rva)
        if off is None:
            return None
        name_rva = struct.unpack_from("<I", blob, off + 12)[0]
        name_off = _rva_to_offset(blob, name_rva)
        if name_off is None:
            return None
        end = blob.index(b"\0", name_off)
        name = blob[name_off:end].decode("latin-1")
        return name or None
    except (struct.error, IndexError, ValueError):
        return None

def carve(exe: Path):
    """Cut one module's bytes out of the executable that carries it."""
    data = exe.read_bytes()
    out = []
    for hit in re.finditer(b"MZ", data):
        start = hit.start()
        if start == 0:
            continue
        end = pe_extent(data, start)
        if not end or start + end > len(data):
            continue
        blob = data[start:start + end]
        if len(blob) < 4096 or not is_dll(blob):
            continue
        out.append((start, blob))
    return out

def segment_names(exe: Path) -> list[str]:
    """The extension filenames the data file lists as its dependencies."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import klikback.core.tgf.format as fmt
    for data in sorted(exe.parent.glob("*")):
        if data.suffix.lower() not in (".gam", ".cca"):
            continue
        try:
            game = fmt.read(data)
        except Exception:
            continue
        seg = game.segment(0x04)
        if seg is None:
            continue
        names = [m.group(0).decode("latin-1")
                 for m in NAME_RE.finditer(seg.data)]
        if names:
            return names
    return []

def extract_to(exe: Path, out_dir: Path, force: bool = False) -> str:
    """Write every embedded module into a folder, one file each."""
    try:
        pieces = carve(exe)
    except OSError as problem:
        return f"extensions: cannot read {exe.name} ({problem})"
    if not pieces:
        return "extensions: none embedded"
    declared = segment_names(exe)
    by_order = bool(declared) and len(declared) == len(pieces)
    written = skipped = 0
    for i, (offset, blob) in enumerate(pieces):
        name = (declared[i] if by_order
                else internal_name(blob) or f"unnamed_{offset:08X}.bin")

        name = Path(name).name
        if not name or name in (".", ".."):
            continue
        out_dir.mkdir(parents=True, exist_ok=True)
        target = out_dir / name
        if target.exists() and not force:
            skipped += 1
            continue
        target.write_bytes(blob)
        written += 1
    how = ("named from segment 0x04" if by_order
           else "named from the export directory, WHICH CAN BE STALE")
    note = f"extensions: {written} written to {out_dir.name}/ ({how})"
    if skipped:
        note += f", {skipped} already there (--force to replace)"
    if declared and not by_order:
        note += (f" -- {len(pieces)} embedded against {len(declared)} declared, "
                 f"so the order could not be trusted")
    return note
