# GENERATED — do not edit by hand. This file is produced by KlikBack's
# sync tooling; changes belong in the source it is generated from.
#
# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""Which extension modules an MMF 2.0 project needs, and getting them out of the
game that carries them.

Fusion 2 games are built out of objects the editor does not itself provide —
INI files, arrays, movement controllers, third-party effects — and a project
that names one will not open in an editor that does not have it installed.  So
the first useful thing to say about a recovered project is what it will ask
for.

A packed standalone has three regions: the small executable stub that starts
it, a block holding every module the game runs, and the game's own data.  The
modules really are in there, compressed — the runtime engine, the extension
modules, the movement controllers, the image and sound filters, and any music
or video the author added as an external file.  They can be listed and they
can be written back out.

Being able to name what is missing matters more than being able to supply it.
An extension is somebody else's software, often still available from its
author, and telling a user *which* modules to install is an answer they can
act on.
"""

from __future__ import annotations
import hashlib
import shutil
import struct
import zlib
from pathlib import Path, PurePath
from klikback.core.mmf2.read_app import App, _pe_resources, extension_list, read_header
from klikback.core.common.cox_titles import CoxProblem, resource_entries, title_from_bytes

EDITOR_SUBDIR = "Extensions"

RUNTIME_SUBDIR = Path("Data") / "Runtime"

RT_VERSION = 16

VS_FFI_SIGNATURE = b"\xbd\x04\xef\xfe"

def file_version(data: bytes):
    """The version numbers a module's own resources carry, if it has any.

    Two builds of an extension can have the same filename and different
    capabilities, so a recovered project is worth comparing against the copy
    actually installed.
    """
    try:
        entries = resource_entries(data)
    except CoxProblem:
        return None
    for path, off, size in entries:
        if not path or path[0] != RT_VERSION or off is None:
            continue
        blob = data[off:off + size]
        at = blob.find(VS_FFI_SIGNATURE)
        if at < 0 or at + 16 > len(blob):
            continue
        ms, ls = struct.unpack_from("<II", blob, at + 8)
        return (ms >> 16, ms & 0xFFFF, ls >> 16, ls & 0xFFFF)
    return None

def _digest(path: Path) -> str:
    return hashlib.sha1(path.read_bytes()).hexdigest()

class Install:
    """One Fusion 2 installation, as a lookup from module name to the file on disk.
    """

    def __init__(self, root: Path):
        self.root = Path(root)
        self.editor = self.root / EDITOR_SUBDIR
        self.runtime = self.root / RUNTIME_SUBDIR

    def exists(self) -> bool:
        """Whether this installation has a module by that name at all."""
        return self.editor.is_dir()

    def editor_copy(self, module: str):
        """The installed module the editor loads — the half that has to be present for a
        project to open.
        """
        p = self.editor / module
        return p if p.is_file() else None

    def runtime_copy(self, module: str):
        """The installed module the runtime loads — the half a rebuilt game needs.
        """
        p = self.runtime / module
        return p if p.is_file() else None

PACK_MAGIC = 0x77777777

PACK_HEADER = 32

class PackProblem(Exception):
    """Raised when a file has no readable block of embedded modules."""

def _sections_end(data: bytes) -> int:
    if data[:2] != b"MZ":
        raise PackProblem("not a PE image")
    (lfanew,) = struct.unpack_from("<I", data, 0x3C)
    if data[lfanew:lfanew + 4] != b"PE" + bytes(2):
        raise PackProblem("no PE header")
    nsec, = struct.unpack_from("<H", data, lfanew + 6)
    optsz, = struct.unpack_from("<H", data, lfanew + 20)
    first = lfanew + 24 + optsz
    end = 0
    for i in range(nsec):
        _vsz, _va, rsz, ptr = struct.unpack_from("<4I", data, first + i * 40 + 8)
        end = max(end, ptr + rsz)
    return end

def _layout(hashed, wide):
    return "%s %s" % ("hashed" if hashed else "bare",
                      "utf-16" if wide else "cp1252")

def _walk_pack(data, start, count, hashed, wide=False):
    q, out = start + PACK_HEADER, []
    for i in range(count):
        if q + 2 > len(data):
            raise PackProblem("entry %d overruns the file" % i)
        (nl,) = struct.unpack_from("<H", data, q)
        nb = nl * (2 if wide else 1)
        head = 2 + nb + (8 if hashed else 4)
        if nl == 0 or nl > 260 or q + head > len(data):
            raise PackProblem("entry %d has a %d-char name" % (i, nl))
        name = data[q + 2:q + 2 + nb].decode("utf-16-le" if wide else "latin-1",
                                             "replace")
        if hashed:
            h, csize = struct.unpack_from("<2I", data, q + 2 + nb)
        else:
            h = 0
            (csize,) = struct.unpack_from("<I", data, q + 2 + nb)
        body = q + head
        if csize > len(data) or body + csize > len(data):
            raise PackProblem("entry %d (%s) claims %d bytes" % (i, name, csize))
        out.append(dict(name=name, hash=h, compressed=csize,
                        offset=body, raw=data[body:body + csize]))
        q = body + csize
    return q, out

def pack_entries(exe: Path):
    """Every embedded module in one game: where the block starts, what is in it, and
    anything odd about how it was read.
    """
    data = Path(exe).read_bytes()
    start = _sections_end(data)
    if start + PACK_HEADER > len(data):
        raise PackProblem("file ends before a pack block could start")
    magic, _w1, first, blocksize, _w4, _z1, _z2, count = struct.unpack_from(
        "<8I", data, start)
    if magic != PACK_MAGIC:
        raise PackProblem("no 0x%08X magic at 0x%X (found 0x%08X)"
                          % (PACK_MAGIC, start, magic))
    if first != PACK_HEADER:
        raise PackProblem("first entry at %d, expected %d" % (first, PACK_HEADER))
    if count > 4096:
        raise PackProblem("pack claims %d entries" % count)

    where, how, _fields = read_header(data, Path(exe))
    attempts, failures = [], []
    for hashed in (True, False):
        for wide in (False, True):
            try:
                q, out = _walk_pack(data, start, count, hashed, wide)
            except PackProblem as e:
                failures.append("%s layout: %s" % (_layout(hashed, wide), e))
                continue
            attempts.append((hashed, wide, q, out))
    if not attempts:
        raise PackProblem("; ".join(failures))

    chosen = None
    for hashed, wide, q, out in attempts:
        if where is not None and q == where:
            chosen = (hashed, wide, q, out)
            break
    if chosen is None:

        for hashed, wide, q, out in attempts:
            if q - start == blocksize:
                chosen = (hashed, wide, q, out)
                break
    if chosen is None:
        raise PackProblem(
            "no entry layout closes: %s"
            % ", ".join("%s ends at 0x%X" % (_layout(h, w), q)
                        for h, w, q, _o in attempts)
            + (" (game header at 0x%X)" % where if where is not None else ""))

    hashed, wide, q, out = chosen
    for e in out:
        try:
            e["data"] = zlib.decompress(e["raw"])
            e["stored"] = "zlib"
        except zlib.error:
            e["data"] = e["raw"]
            e["stored"] = "raw"
        del e["raw"]
    note = ("chain closes exactly on the game header at 0x%X (%s, %s layout)"
            % (q, how, _layout(hashed, wide))) if q == where else (
            "chain consumed the declared %d-byte block (%s layout)"
            % (blocksize, _layout(hashed, wide)))
    return start, out, note

RUNTIME_SHELL = "stdrt.exe"

RUNTIME_FILES = frozenset((
    RUNTIME_SHELL,
    "mmfs2.dll",
    "mmf2d3d8.dll",
    "mmf2d3d9.dll",
))

FOLDER_SUFFIX = ".extracted"

EFFECTS_DIR = "Effects"

EXTENSIONS_DIR = "Extensions"

TRANSITIONS_DIR = "Transitions"

FILTERS_DIR = "Filters"

def safe_name(name):
    base = PurePath(str(name).replace("\\", "/")).name
    base = base.strip().strip(".")
    if not base or base in (".", ".."):
        return None
    return base

def transition_modules(app):
    found = set()
    try:
        frames = app.frames()
    except Exception:
        return found
    for f in frames:
        for which in ("fadeIn", "fadeOut"):
            tr = f.get(which)
            if tr and tr.get("module"):
                found.add(tr["module"].lower())
        for it in f.get("items", []) or []:
            for which in ("fadeIn", "fadeOut"):
                tr = it.get(which)
                if tr and tr.get("module"):
                    found.add(tr["module"].lower())
    return found

def extract(exe: Path, outdir: Path, with_runtime: bool = False,
            effects: bool = True) -> int:
    """Write every embedded module out to its own directory beside the game.

    Deliberately not written where installed copies are looked for: a carved copy
    sitting there would answer the next version comparison with itself.
    """
    exe = Path(exe)
    builds = []
    try:
        start, entries, note = pack_entries(exe)
    except PackProblem as e:
        print("== %s: no embedded modules: %s" % (exe.name, e))
        return 0
    keep = [e for e in entries
            if with_runtime or e["name"].lower() not in RUNTIME_FILES]
    skipped = len(entries) - len(keep)
    dest = Path(outdir) / (exe.stem + FOLDER_SUFFIX)
    dest.mkdir(parents=True, exist_ok=True)
    print("== %s  pack block at 0x%X, %d entr(ies)" % (exe.name, start, len(entries)))
    try:
        app = App(exe)
    except BaseException:
        app = None
    tmods = transition_modules(app) if app is not None else set()
    written = 0
    for e in keep:
        base = safe_name(e["name"])
        if base is None:
            print("   %-24s SKIPPED -- unusable name" % e["name"][:24])
            continue
        low = base.lower()
        if low.endswith((".mfx", ".mvx")):
            sub_dir = EXTENSIONS_DIR
        elif low in tmods:
            sub_dir = TRANSITIONS_DIR
        elif low.endswith((".ift", ".sft")):
            sub_dir = FILTERS_DIR
        else:
            sub_dir = None
        target_dir = dest / sub_dir if sub_dir else dest
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / base).write_bytes(e["data"])
        written += 1
        if sub_dir == EXTENSIONS_DIR:
            builds.append((base,) + mfx_build(e["data"]))
        title = None
        if e["data"][:2] == b"MZ":
            try:
                title = title_from_bytes(e["data"])
            except CoxProblem:
                title = None
        print("   %-24s %8d -> %8d  %s%s"
              % (base, e["compressed"], len(e["data"]),
                 ("%s/  " % sub_dir) if sub_dir else "",
                 ("%r" % title) if title else ""))
    if skipped:

        print("   (%d runtime file(s) not written -- the shell and its DLLs "
              "are not project parts and do nothing without the game data "
              "that was appended to them)"
              % skipped)

    shaders_written = 0
    if effects and app is not None:
        try:
            found = app.shaders()
        except BaseException:
            found = []
        for name, src, _params in found:
            base = safe_name(name)
            if base is None or not src:
                continue
            (dest / EFFECTS_DIR).mkdir(parents=True, exist_ok=True)
            (dest / EFFECTS_DIR / base).write_bytes(src)
            shaders_written += 1
            print("   %-24s %8s -> %8d  %s/" % (base, "-", len(src), EFFECTS_DIR))

    if builds:
        rt = [n for n, k, _w in builds if k == "runtime"]
        lines = ["Build type of each carved .mfx, as classified by",
                 "mfx_build().", "",
                 "A game bundles the RUNTIME build of an extension. The editor",
                 "needs the EDITOR build, which carries the property pages, the",
                 "ACE menus and the object icon and is NOT present in the game.",
                 "Copying a runtime build into the editor's Extensions folder",
                 "does not make the project openable, and at least one module in",
                 "the wild breaks the editor at startup when installed.", ""]
        for n, kind, why in sorted(builds):
            lines.append("%-34s %-8s  %s" % (n, kind, why))
        lines += ["", "%d of %d carved module(s) are runtime builds."
                  % (len(rt), len(builds))]
        (dest / EXTENSIONS_DIR).mkdir(parents=True, exist_ok=True)
        (dest / EXTENSIONS_DIR / "BUILD TYPES.txt").write_text(
            chr(10).join(lines) + chr(10), encoding="utf-8")
        print("   %d of %d module(s) are RUNTIME builds -- the editor cannot "
              "use those (see %s/BUILD TYPES.txt)"
              % (len(rt), len(builds), EXTENSIONS_DIR))
    print("   %s" % note)
    print("   wrote %d file(s) to %s" % (written + shaders_written, dest))
    return written + shaders_written

MENU_APIS = frozenset([
    "user32.dll!appendmenua", "user32.dll!getsubmenu",
    "user32.dll!getmenuitemid", "user32.dll!createpopupmenu",
    "user32.dll!getmenuitemcount", "user32.dll!getmenustate",
    "user32.dll!getmenustringa", "user32.dll!destroymenu",
])

MENU_APIS_NEEDED = 6

ICON_BITMAP_ID = 400

def icon_bitmap(data: bytes):
    """The picture a module carries as its own object icon, read out of the
    module's resources.
    """
    for path, off, size in _pe_resources(data):
        if len(path) >= 2 and path[0] == 2 and path[1] == ICON_BITMAP_ID:
            break
    else:
        return None
    blob = data[off:off + size]
    if len(blob) < 40:
        return None
    hs, w, h, _planes, bpp, comp = struct.unpack_from("<IiiHHI", blob, 0)
    if comp != 0 or h <= 0 or w <= 0 or bpp not in (4, 8, 24, 32):
        return None
    ncol = struct.unpack_from("<I", blob, 32)[0] or (1 << bpp if bpp <= 8 else 0)
    pal = blob[hs:hs + ncol * 4]
    px = hs + ncol * 4
    row = ((w * bpp + 31) // 32) * 4
    if px + row * h > len(blob) or (bpp <= 8 and len(pal) < ncol * 4):
        return None
    out = []
    for y in range(h):
        b = px + row * (h - 1 - y)
        for x in range(w):
            if bpp == 24:
                bl, g, r = blob[b + 3 * x:b + 3 * x + 3]
            elif bpp == 32:
                bl, g, r = blob[b + 4 * x:b + 4 * x + 3]
            elif bpp == 8:
                i = blob[b + x]
                bl, g, r = pal[4 * i:4 * i + 3]
            else:
                i = (blob[b + x // 2] >> (4 if x % 2 == 0 else 0)) & 0xF
                bl, g, r = pal[4 * i:4 * i + 3]
            out.append((r, g, bl))
    return w, h, bpp, out

def _icon_word(r, g, b, bpp):
    w = ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)
    if w == 0:
        if r | g | b:
            return 1
        if bpp == 8:
            return 0x0800
    return w

def editor_icon_picture(data: bytes):
    """That picture as the editor stores it beside an object: a palette-depth
    bitmap whole, any other with the colour of its top-left pixel made
    transparent, and two small colour adjustments the editor makes that were
    learned from its own saves.

    An icon taken this way is the module's *current* icon. The editor keeps the
    icon an object was created with and never refreshes it, so a project made
    with an older module may show different art; that is the author's file
    being faithful to its own history, not a fault in the module.
    """
    bm = icon_bitmap(data)
    if bm is None:
        return None
    w, h, bpp, px = bm
    key = None if bpp == 8 else px[0]
    flat = tuple(None if p == key else _icon_word(p[0], p[1], p[2], bpp)
                 for p in px)
    return w, h, flat

def _pe_import_funcs(data: bytes) -> set:
    if data[:2] != b"MZ" or len(data) < 0x40:
        return set()
    e_lfanew, = struct.unpack_from("<I", data, 0x3C)
    if data[e_lfanew:e_lfanew + 4] != b"PE" + bytes(2):
        return set()
    coff = e_lfanew + 4
    nsec, = struct.unpack_from("<H", data, coff + 2)
    optsz, = struct.unpack_from("<H", data, coff + 16)
    opt = coff + 20
    magic, = struct.unpack_from("<H", data, opt)
    dirs = opt + (96 if magic == 0x10B else 112)
    if optsz < 16 or dirs + 16 > len(data):
        return set()
    secs = []
    sect = opt + optsz
    for i in range(nsec):
        o = sect + i * 40
        if o + 40 > len(data):
            break
        va, = struct.unpack_from("<I", data, o + 12)
        vsz, = struct.unpack_from("<I", data, o + 8)
        raw, = struct.unpack_from("<I", data, o + 20)
        rsz, = struct.unpack_from("<I", data, o + 16)
        secs.append((va, max(vsz, rsz), raw))

    def off(va):
        for sva, sz, raw in secs:
            if sva <= va < sva + sz:
                return raw + (va - sva)
        return None

    iva, _isz = struct.unpack_from("<II", data, dirs + 8)
    if not iva:
        return set()
    p = off(iva)
    if p is None:
        return set()
    ptr = 8 if magic == 0x20B else 4
    hi = (1 << 63) if magic == 0x20B else (1 << 31)
    out = set()

    for k in range(256):
        o = p + k * 20
        if o + 20 > len(data):
            break
        oft, = struct.unpack_from("<I", data, o)
        nva, = struct.unpack_from("<I", data, o + 12)
        fta, = struct.unpack_from("<I", data, o + 16)
        if nva == 0:
            break
        no = off(nva)
        dll = ""
        if no is not None:
            end = data.find(bytes(1), no)
            if 0 <= end and end - no <= 128:
                dll = data[no:end].decode("ascii", "replace").lower()
        t = off(oft or fta)
        if t is None:
            continue
        for j in range(4096):
            q = t + j * ptr
            if q + ptr > len(data):
                break
            v, = struct.unpack_from("<Q" if ptr == 8 else "<I", data, q)
            if v == 0:
                break
            if v & hi:
                continue
            h = off(v & 0x7FFFFFFF)
            if h is None or h + 2 > len(data):
                continue
            end = data.find(bytes(1), h + 2)
            if end < 0 or end - h - 2 > 128:
                continue
            out.add(dll + "!" + data[h + 2:end].decode("ascii", "replace").lower())
    return out

def mfx_build(data: bytes):
    if data[:2] != b"MZ":
        return "unknown", "not a PE"
    menus = len(MENU_APIS & _pe_import_funcs(data))
    try:
        icon = any(path[0] == 2 and path[1] == ICON_BITMAP_ID
                   for path, _o, _s in _pe_resources(data) if len(path) >= 2)
    except BaseException:
        icon = False
    why = "%d/%d menu API(s), icon %s" % (menus, len(MENU_APIS),
                                          "present" if icon else "absent")
    if menus >= MENU_APIS_NEEDED and icon:
        return "editor", why
    return "runtime", why

def needed_modules(exe: Path):
    """The modules the project's own object list names, with their handles.

    This is what the project asks for, as against what the file happens to carry —
    the two can differ, and the difference is the interesting part.
    """
    app = App(exe)
    records, note = extension_list(app.payload(0x2234))
    if records is None:
        return [], note
    return [(r["handle"], r["module"], r["subtype"]) for r in records], note

def classify(module: str, exe_dir: Path, installs: list[Install]):
    """Everything known about one module a project needs: whether it is embedded in
    the game, whether it is installed here, and how the two versions compare.
    """
    out = {
        "module": module,
        "shipped": None,
        "installed": None,
        "runtime_only": False,
        "title": None,
        "version": None,
        "shipped_version": None,
        "where": None,
        "near_misses": [],
    }

    for cand in sorted(exe_dir.rglob(module)):
        if cand.is_file():
            out["shipped"] = cand
            break

    for inst in installs:
        found = inst.editor_copy(module)
        if found is not None:
            out["installed"] = found
            out["where"] = inst.root
            break

    if out["installed"] is None and out["shipped"] is None:
        stem = Path(module).stem.lower()
        for inst in installs:
            if not inst.exists():
                continue
            for cand in sorted(inst.editor.glob("*.mfx")):
                cs = cand.stem.lower()
                if cs != stem and cs.startswith(stem):
                    try:
                        title = title_from_bytes(cand.read_bytes())
                    except CoxProblem:
                        title = None
                    out["near_misses"].append((cand.name, title))

    source = out["installed"] or out["shipped"]
    if source is not None:
        data = source.read_bytes()
        try:
            out["title"] = title_from_bytes(data)
        except CoxProblem:
            out["title"] = None
        out["version"] = file_version(data)

    if out["shipped"] is not None:
        out["shipped_version"] = file_version(out["shipped"].read_bytes())

        shipped_digest = _digest(out["shipped"])
        for inst in installs:
            rt, ed = inst.runtime_copy(module), inst.editor_copy(module)
            if rt is None:
                continue
            if _digest(rt) == shipped_digest and (
                ed is None or _digest(ed) != shipped_digest
            ):
                out["runtime_only"] = True
                break
    return out

def report(exe: Path, installs: list[Install], collect: Path | None):
    """Say what a project needs and what this machine can supply."""
    modules, note = needed_modules(exe)
    print("== %s" % exe.name)
    if not modules:
        print("   no extension list: %s" % (note or "none"))
        return 0
    exe_dir = exe.parent
    missing = 0
    rows = [classify(m, exe_dir, installs) for _h, m, _s in modules]
    width = max(len(r["module"]) for r in rows)
    for r in rows:
        flags = []
        if r["installed"] is None and r["shipped"] is None:
            flags.append("MISSING -- install it or place it beside the game")
            missing += 1
            if r["near_misses"]:
                flags.append("installed under another name? %s -- a different "
                             "release, NOT a substitute (the project names the "
                             "module by filename)"
                             % ", ".join("%s (%s)" % (n, ti or "no title")
                                         for n, ti in r["near_misses"][:3]))
        elif r["installed"] is None:
            flags.append("not installed; a copy ships with the game")
        if r["runtime_only"]:
            flags.append("the shipped copy is a RUNTIME build -- the editor "
                         "cannot use it")
        if (r["shipped_version"] and r["version"]
                and r["shipped_version"] != r["version"]):
            flags.append("version differs: shipped %s, installed %s"
                         % (".".join(map(str, r["shipped_version"])),
                            ".".join(map(str, r["version"]))))
        ver = ".".join(map(str, r["version"])) if r["version"] else "-"
        print("   %-*s  %-28s %-12s %s"
              % (width, r["module"], (r["title"] or "-")[:28], ver,
                 "; ".join(flags)))
    print("   %d module(s), %d missing" % (len(rows), missing))

    if collect is not None:
        dest = Path(collect) / "Extensions"
        dest.mkdir(parents=True, exist_ok=True)
        copied = 0
        for r in rows:

            src = r["installed"] or (None if r["runtime_only"] else r["shipped"])
            if src is None:
                continue
            shutil.copy2(src, dest / r["module"])
            copied += 1
        print("   collected %d of %d module(s) into %s"
              % (copied, len(rows), dest))
        print("   NOTE: collected from the install and from beside the game. "
              "Nothing was extracted from the EXE -- a 2.0 standalone embeds "
              "no .mfx.")
    return missing
