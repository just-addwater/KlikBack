# GENERATED — do not edit by hand. This file is produced by KlikBack's
# sync tooling; changes belong in the source it is generated from.
#
# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""Read a built Multimedia Fusion 2 game.

Everything a recovery can know about a project comes from here: the
application's settings, its image, sound and font banks, the extension modules
it needs, and then each frame with the objects it defines, where they are
placed, and the events that drive them.

A built game is not a project.  The compiler keeps what the runtime needs and
drops the rest — the author's names for backdrops and behaviours, which sheet
each event line came from, whatever the editor remembered about window
positions and folder trees.  None of that is in the file to find, so this
reader's job is to find everything that *is*, and to be clear about the
boundary rather than quietly filling it in.

Where the format leaves a choice open, this reads it in the direction that
fails loudly.  A block whose declared size does not match what walking it
consumes is reported with both numbers; an array is walked to its terminator
rather than to a count that might be stale; a field with no known meaning is
carried, not guessed at.
"""

from __future__ import annotations
import struct
import zlib
from pathlib import Path
from klikback.core.mmf2.chunk_census import HEADER_SIZE, read_header, walk_chunks

def cstr(buf):
    """A NUL-terminated string, as the format stores names and filenames."""
    end = buf.find(b"\x00")
    return buf[: end if end >= 0 else len(buf)].decode("cp1252", "replace")

MOVEMENT_TYPES = {
    0: "static", 1: "mouse", 2: "race car", 3: "eight directions",
    4: "bouncing ball", 5: "path", 9: "platform",
}

MOVEMENT_RECORD = 16

EXT_RECORD_HEAD = 16

def extension_list(p):
    """The table of extension modules the game carries, which an object's type number
    indexes into.

    An object beyond the built-in types names its module by position here, so this
    is what turns a bare type number into "this project needs this extension".
    """
    if p is None:
        return None, "no 0x2234"
    if len(p) < 4:
        return None, "0x2234 is %d bytes, too short for a count" % len(p)
    count, second = struct.unpack_from("<2H", p, 0)
    pos, out = 4, []
    for i in range(count):
        if pos + EXT_RECORD_HEAD > len(p):
            return out, "0x2234 truncated at record %d of %d" % (i, count)
        size, handle = struct.unpack_from("<2H", p, pos)
        const, version, trailer = struct.unpack_from("<3I", p, pos + 4)
        if size < EXT_RECORD_HEAD or pos + size > len(p):
            return out, "0x2234 record %d claims %d bytes" % (i, size)
        body = p[pos + EXT_RECORD_HEAD : pos + size]
        module = cstr(body)
        subtype = cstr(body[len(module) + 1 :]) if len(body) > len(module) else ""
        out.append(dict(handle=handle, module=module, subtype=subtype,
                        constant=const, version=version, trailer=trailer,
                        position=i))
        pos += size
    left = len(p) - pos
    return out, ("0x2234, count=%d/%d, consumed %d/%d bytes"
                 % (count, second, pos, len(p))
                 + ("" if left == 0 else "  ** %d BYTES LEFT OVER **" % left))

def active_movements(body):
    """Every movement defined on an object.

    Belongs to every placeable type and not only the Active — a backdrop can be
    given a movement, and reading this for Actives alone loses it.
    """
    if body is None or len(body) < 8:
        return []
    (start,) = struct.unpack_from("<H", body, 4)
    end = len(body)
    if not (0 < start < end):
        return []
    sect = body[start:end]
    if len(sect) < 20:
        return []
    (count,) = struct.unpack_from("<I", sect, 0)
    out = []
    for i in range(count):
        off = 4 + i * MOVEMENT_RECORD
        if off + MOVEMENT_RECORD > len(sect):
            break
        (nameoff,) = struct.unpack_from("<I", sect, off)
        raw = sect[off + 4 : off + 8]
        dataoff, datasize = struct.unpack_from("<2I", sect, off + 8)

        params = (sect[dataoff : dataoff + datasize]
                  if dataoff + datasize <= len(sect) else None)
        if nameoff and nameoff < len(sect):
            out.append(dict(kind="extension", code=raw.decode("ascii", "replace"),
                            codeRaw=bytes(raw), module=cstr(sect[nameoff:]),
                            data=(dataoff, datasize), params=params))
        else:
            (num,) = struct.unpack_from("<I", raw, 0)
            entry = dict(kind="builtin", type=num,
                         name=MOVEMENT_TYPES.get(num, "movement %d?" % num),
                         data=(dataoff, datasize), params=params)
            if params is not None and len(params) >= 12:
                (entry["player"], entry["paramType"], entry["movingAtStart"]) = (
                    struct.unpack_from("<3H", params, 0)
                )
                (entry["directionMask"],) = struct.unpack_from("<I", params, 8)
            out.append(entry)
    return out

OBJECT_TYPE_CODES = {
    2: b"SPRI", 3: b"TEXT", 4: b"QSTN", 5: b"SCRE",
    6: b"LIVE", 7: b"CNTR", 8: b"RTF ", 9: b"CCA ",
}

def object_type_code(body, otype):
    """The four-character code that says what kind of object this is, where there is
    one.

    Returns whether the answer is trustworthy alongside the answer itself: the two
    backdrop types carry no code at all, and an extension's code belongs to its
    module rather than to the format.
    """
    if body is None or len(body) < 0x32:
        return None, None
    code = bytes(body[0x2E:0x32])
    want = OBJECT_TYPE_CODES.get(otype)
    return code, (None if want is None else code == want)

QUALIFIER_ID_MAX = 99

NO_QUALIFIER_TYPES = (0, 1)

def object_qualifiers(body, otype=None):
    """The groups an object belongs to.

    Terminated rather than counted: the array has a fixed number of slots and the
    list inside it ends at a marker, so reading all the slots picks up whatever
    was left in the ones past the end.
    """
    if body is None or len(body) < 0x24:
        return []
    if otype in NO_QUALIFIER_TYPES:
        return []
    out = []
    for q in struct.unpack_from("<8H", body, 0x14):
        if q == 0xFFFF:
            break
        out.append(q)
    return out

def extension_private(body):
    """The block an extension object keeps its own settings in.

    The format does not describe its contents — that is the module's business —
    so it is located, measured, and carried across unread.
    """
    if body is None or len(body) < 0x26:
        return None
    (off,) = struct.unpack_from("<H", body, 0x24)
    if not (0 < off <= len(body) - 4):
        return dict(offset=off, size=None, note="offset out of range")
    (size,) = struct.unpack_from("<I", body, off)
    return dict(offset=off, size=size, data=body[off:off + size],
                note="" if size == len(body) - off
                     else "declared %d, %d bytes remain" % (size, len(body) - off))

def transition(buf, off, where=""):
    """One fade record, in the single shape both of its carriers use."""
    if buf is None or off + 32 > len(buf):
        return dict(error="%stransition at %d runs past its %d-byte carrier"
                          % (where, off, 0 if buf is None else len(buf)))
    tid = bytes(buf[off:off + 4])
    trid = bytes(buf[off + 4:off + 8])
    duration, flags, colour, moff, poff, plen = struct.unpack_from("<6I", buf, off + 8)
    end = buf.find(bytes(1), off + 32)
    if moff != 32 or end < 0:
        return dict(error="%stransition at %d: moduleOffset %d%s"
                          % (where, off, moff,
                             "" if end >= 0 else ", module string unterminated"))
    module = buf[off + 32:end]
    if poff != moff + len(module) + 1:
        return dict(error="%stransition at %d: paramOffset %d, but the module "
                          "name is %d bytes" % (where, off, poff, len(module)))
    if off + poff + plen > len(buf):
        return dict(error="%stransition at %d: the %d-byte parameter runs past "
                          "the carrier" % (where, off, plen))
    return dict(id=tid, transitionId=trid, duration=duration, flags=flags,
                colour=colour, module=module.decode("cp1252", "replace"),
                param=bytes(buf[off + poff:off + poff + plen]),
                size=poff + plen, error=None)

def object_transitions(body):
    """An object's own fade in and fade out."""
    if body is None or len(body) < 0x3E:
        return None, None
    (fin,) = struct.unpack_from("<H", body, 0x36)
    (fout,) = struct.unpack_from("<H", body, 0x3A)
    return (transition(body, fin, "fadeIn: ") if fin else None,
            transition(body, fout, "fadeOut: ") if fout else None)

def active_alterables(body):
    """An object's alterable values and strings.

    Either list may be absent, which means the author never gave the object any —
    not that this reader could not find them.
    """
    if body is None or len(body) < 0x2A:
        return None, None, ""
    tail = struct.unpack_from("<H", body, 6)[0]
    voff, soff = struct.unpack_from("<2H", body, 4 + 0x22)
    values = strings = None
    problems = []
    if voff:
        (n,) = struct.unpack_from("<H", body, voff)
        end = voff + 2 + 4 * (n + 1)
        if end <= len(body):
            words = struct.unpack_from("<%dI" % (n + 1), body, voff + 2)
            values = list(words[:-1])
            if words[-1] != 0:
                problems.append("value trailer %d, not 0" % words[-1])
            if end != (soff or tail):
                problems.append("values end at %d, next block at %d" % (end, soff or tail))
        else:
            problems.append("value block overruns")
    if soff:
        (n,) = struct.unpack_from("<H", body, soff)
        pos, out = soff + 2, []
        for _ in range(n):
            e = body.find(b"\x00", pos)
            if e < 0:
                break
            out.append(body[pos:e].decode("cp1252", "replace"))
            pos = e + 1
        strings = out
        if len(out) != n or pos != tail:
            problems.append("strings end at %d for %d of %d, trailing block at %d"
                            % (pos, len(out), n, tail))
    return values, strings, "; ".join(problems)

ANIMATION_SLOTS = {
    0: "Stopped", 1: "Walking", 2: "Running", 3: "Appearing", 4: "Disappearing",
    5: "Bouncing", 6: "Shooting", 7: "Jumping", 8: "Falling", 9: "Climbing",
    10: "Crouch down", 11: "Stand up",
}

def active_animations(body):
    """An object's animation table: its directions, their speeds, and the images each
    frame uses.
    """
    if body is None or len(body) < 8:
        return None, "no body"
    tail = struct.unpack_from("<H", body, 6)[0]
    blk = body[tail:]
    if len(blk) < 4:
        return None, "block is %d bytes" % len(blk)
    size, count = struct.unpack_from("<2H", blk, 0)
    if size != len(blk):
        return None, "leading size %d != block length %d" % (size, len(blk))
    if 4 + 2 * count > len(blk):
        return None, "count %d overruns the block" % count
    out = []
    for slot, off in enumerate(struct.unpack_from("<%dH" % count, blk, 4)):
        if not off:
            continue
        if off + 64 > len(blk):
            return None, "animation %d overruns" % slot
        dirs = []
        for d, doff in enumerate(struct.unpack_from("<32H", blk, off)):
            if not doff:
                continue
            at = off + doff
            if at + 8 > len(blk):
                return None, "direction %d of animation %d overruns" % (d, slot)
            minspeed, maxspeed = blk[at], blk[at + 1]
            repeat, backto, frames = struct.unpack_from("<3h", blk, at + 2)
            if frames < 0 or at + 8 + 2 * frames > len(blk):
                return None, "frameCount %d in direction %d of animation %d" % (frames, d, slot)
            dirs.append(dict(direction=d, minSpeed=minspeed, maxSpeed=maxspeed,
                             repeat=repeat, backTo=backto,
                             frames=list(struct.unpack_from("<%dH" % frames, blk, at + 8))))
        out.append(dict(slot=slot, name=ANIMATION_SLOTS.get(slot, "user %d" % (slot - 12))
                        if slot >= 12 or slot in ANIMATION_SLOTS else "animation %d" % slot,
                        directions=dirs))
    return out, "size=%d slots=%d used=%d" % (size, count, len(out))

def _pe_resources(data):
    if data[:2] != b"MZ" or len(data) < 0x40:
        return []
    e_lfanew = struct.unpack_from("<I", data, 0x3C)[0]
    if data[e_lfanew:e_lfanew + 4] != b"PE" + bytes(2):
        return []
    coff = e_lfanew + 4
    nsec, = struct.unpack_from("<H", data, coff + 2)
    optsz, = struct.unpack_from("<H", data, coff + 16)
    sect = coff + 20 + optsz
    base = va = None
    for i in range(nsec):
        o = sect + i * 40
        if data[o:o + 8].rstrip(bytes(1)) == b".rsrc":
            va, = struct.unpack_from("<I", data, o + 12)
            base, = struct.unpack_from("<I", data, o + 20)
            break
    if base is None:
        return []

    found = []

    def walk(off, path, depth):

        if depth > 3:
            return
        n_named, n_id = struct.unpack_from("<HH", data, base + off + 12)
        for i in range(n_named + n_id):
            e = base + off + 16 + i * 8
            nid, entry = struct.unpack_from("<II", data, e)
            if entry & 0x80000000:
                walk(entry & 0x7FFFFFFF, path + (nid,), depth + 1)
            else:
                dva, dsz = struct.unpack_from("<II", data, base + (entry & 0x7FFFFFFF))
                found.append((path + (nid,), dva, dsz))

    walk(0, (), 1)
    return [(path, base + (dva - va), dsz) for path, dva, dsz in found]

def _pe_icons(data):
    out = []
    for path, off, sz in _pe_resources(data):
        if not path or path[0] != 3:
            continue
        blob = data[off:off + sz]
        if len(blob) < 40:
            continue
        w, h, planes, bpp = struct.unpack_from("<iiHH", blob, 4)

        out.append((path[1], w, h // 2, bpp, blob))
    out.sort()
    return out

RUNTIME_FILE_DESCRIPTION = "Multimedia Fusion Application Runtime"

VERSION_KEYS = ("CompanyName", "FileDescription", "FileVersion",
                "InternalName", "LegalCopyright", "LegalTrademarks",
                "OriginalFilename", "ProductName", "ProductVersion",
                "Comments")

def _pe_version_strings(data):
    nul = chr(0)
    for path, off, sz in _pe_resources(data):
        if not path or path[0] != 16:
            continue
        txt = data[off:off + sz].decode("utf-16-le", "ignore")
        out = {}
        for key in VERSION_KEYS:
            i = txt.find(key)
            if i < 0:
                continue
            j = i + len(key)
            while j < len(txt) and txt[j] == nul:
                j += 1
            k = txt.find(nul, j)
            out[key] = txt[j:k if k >= 0 else len(txt)]
        return out
    return {}

def _icon_planes(w, h, bpp, blob):
    hdr_size, = struct.unpack_from("<I", blob, 0)
    ncolours, = struct.unpack_from("<I", blob, 32)
    if bpp <= 8 and not ncolours:
        ncolours = 1 << bpp
    pal_off = hdr_size
    pal = blob[pal_off:pal_off + ncolours * 4]
    px_off = pal_off + ncolours * 4
    row = ((w * bpp + 31) // 32) * 4
    mask_row = ((w + 31) // 32) * 4
    mask_off = px_off + row * h
    colour = bytearray(w * h * 2)
    alpha = bytearray(w * h)
    for y in range(h):
        sy = h - 1 - y
        base_c = px_off + row * sy
        base_m = mask_off + mask_row * sy
        for x in range(w):
            if bpp == 32:
                b, g, r, a = blob[base_c + x * 4: base_c + x * 4 + 4]
            elif bpp == 24:
                b, g, r = blob[base_c + x * 3: base_c + x * 3 + 3]
                a = 255
            else:
                if bpp == 8:
                    idx = blob[base_c + x]
                elif bpp == 4:
                    byte = blob[base_c + (x >> 1)]
                    idx = (byte >> 4) if not x & 1 else (byte & 0xF)
                else:
                    byte = blob[base_c + (x >> 3)]
                    idx = (byte >> (7 - (x & 7))) & 1
                b, g, r = pal[idx * 4], pal[idx * 4 + 1], pal[idx * 4 + 2]
                a = 255
            if a == 255 or bpp != 32:

                bit = (blob[base_m + (x >> 3)] >> (7 - (x & 7))) & 1
                a = 0 if bit else 255
            i = y * w + x
            struct.pack_into("<H", colour, i * 2,
                             ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3))
            alpha[i] = a
    return dict(rgb565=bytes(colour), alpha=bytes(alpha))

class App:
    """One built game, walked on construction."""
    def __init__(self, path):
        self.path = Path(path)
        data = self.data = self.path.read_bytes()
        off, how, fields = read_header(data, self.path)
        if off is None:
            raise SystemExit("no game header in %s (%s)" % (path, how))
        self.how = how
        self.magic, self.rtver, self.rtsub, self.pver, self.pbuild = fields
        self.chunks, self.stop, _ = walk_chunks(
            data, off + HEADER_SIZE, len(data), keep_payload=True
        )
        self.by_id = {}
        for chunk in self.chunks:
            self.by_id.setdefault(chunk.id, []).append(chunk)

    def payload(self, cid):
        """The contents of one of the game's top-level chunks, decompressed."""
        got = self.by_id.get(cid)
        return got[0].payload if got else None

    def app_header(self):
        """The application's own settings: window size, initial score and lives, frame
        rate, and the flag words behind the editor's checkboxes.
        """
        p = self.payload(0x2223)
        if p is None or len(p) < 112:
            return None
        flags, newflags, mode, otherflags, w, h = struct.unpack_from("<6H", p, 4)
        score, lives = struct.unpack_from("<2I", p, 0x10)
        border, nframes, rate = struct.unpack_from("<3I", p, 0x60)
        return dict(
            leading_word=struct.unpack_from("<I", p, 0)[0],
            flags=flags, newFlags=newflags, mode=mode, otherFlags=otherflags,
            width=w, height=h,
            initialScore=score ^ 0xFFFFFFFF, initialLives=lives ^ 0xFFFFFFFF,
            borderColor=border, numberOfFrames=nframes, frameRate=rate,
            includeExternalFiles=bool(otherflags & 0x0040),
        )

    def name(self):
        """The application's name."""
        p = self.payload(0x2224)
        return cstr(p) if p is not None else None

    def author(self):
        p = self.payload(0x2225)
        return cstr(p) if p is not None else None

    def copyright(self):
        p = self.payload(0x223B)
        return cstr(p) if p is not None else None

    def about_box(self):
        p = self.payload(0x223A)
        return cstr(p) if p is not None else None

    def help_file(self):
        p = self.payload(0x2230)
        return cstr(p) if p is not None else None

    def frame_handles(self):
        p = self.payload(0x222B)
        n = (self.app_header() or {}).get("numberOfFrames")
        if p is None or n is None or len(p) % 2:
            return None
        table = struct.unpack_from("<%dH" % (len(p) // 2), bytes(p), 0)
        out = [None] * n
        for handle, pos in enumerate(table):
            if pos < n and out[pos] is None:
                out[pos] = handle
        if any(v is None for v in out) or len(set(out)) != n:
            return None
        if len(table) != n:
            return None
        return out

    def binary_files(self):
        p = self.payload(0x2238)
        if p is None or len(p) < 4:
            return []
        p = bytes(p)
        (count,) = struct.unpack_from("<I", p, 0)
        out, pos = [], 4
        for _ in range(count):
            (nlen,) = struct.unpack_from("<H", p, pos)
            name = p[pos + 2 : pos + 2 + nlen]
            pos += 2 + nlen
            (dlen,) = struct.unpack_from("<I", p, pos)
            out.append((name, p[pos + 4 : pos + 4 + dlen]))
            pos += 4 + dlen
        if pos != len(p):
            raise ValueError("0x2238 left %d bytes over" % (len(p) - pos))
        return out

    def app_icon(self):
        return self.payload(0x2235)

    def version_info(self):
        vs = _pe_version_strings(self.data)
        if not vs:
            return None
        if (vs.get("FileDescription") or "").rstrip() == RUNTIME_FILE_DESCRIPTION:
            return dict(company="", description="", version="")
        return dict(company=(vs.get("CompanyName") or "").rstrip(),
                    description=(vs.get("FileDescription") or "").rstrip(),
                    version=(vs.get("FileVersion") or "").rstrip())

    def app_icon_small(self):
        p = self.payload(0x2235)
        if p is None or len(p) < 1352:
            return None
        hdr, = struct.unpack_from("<I", p, 0)
        w, h, _planes, bpp = struct.unpack_from("<iiHH", p, 4)
        if (w, h, bpp) != (16, 16, 8) or hdr != 40:
            return None
        pal = p[40:40 + 1024]
        px_off, mask_off = 40 + 1024, 40 + 1024 + 256
        colour, alpha = bytearray(16 * 16 * 2), bytearray(16 * 16)
        for y in range(16):
            sy = 15 - y
            for x in range(16):
                idx = p[px_off + sy * 16 + x]
                b, g, r = pal[idx * 4], pal[idx * 4 + 1], pal[idx * 4 + 2]

                bit = (p[mask_off + y * 2 + (x >> 3)] >> (7 - (x & 7))) & 1
                i = y * 16 + x
                struct.pack_into("<H", colour, i * 2,
                                 ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3))
                alpha[i] = 0 if bit else 255
        return bytes(colour), bytes(alpha)

    def app_icon_set(self):

        cached = getattr(self, "_app_icon_set_cache", None)
        if cached is not None:
            return cached
        try:
            out = [dict(width=w, height=h, bpp=bpp, **_icon_planes(w, h, bpp, blob))
                   for _rid, w, h, bpp, blob in _pe_icons(self.data)]
        except (struct.error, ValueError, IndexError):
            out = []
        self._app_icon_set_cache = out
        return out

    def editor_path(self):
        p = self.payload(0x222E)
        return cstr(p) if p is not None else None

    def build_target_path(self):
        p = self.payload(0x222F)
        return cstr(p) if p is not None else None

    def shaders(self):
        p = self.payload(0x2243)
        if not p or len(p) < 8:
            return []
        try:
            (count,) = struct.unpack_from("<I", p, 0)
        except struct.error:
            return []
        out = []
        for i in range(count):
            try:
                (base,) = struct.unpack_from("<I", p, 4 + 4 * i)
                noff, soff, poff = struct.unpack_from("<3I", p, base)
                name = cstr(p[base + noff:])
                src = p[base + soff:].split(bytes(1))[0]
                params = []
                if poff:

                    try:
                        q = base + poff
                        pc, toff, noff2 = struct.unpack_from("<3I", p, q)
                        types = p[q + toff: q + toff + pc]
                        names = p[q + noff2:].split(bytes(1))
                        if len(types) == pc and len(names) >= pc:
                            params = [(names[j].decode("latin-1"), types[j])
                                      for j in range(pc)]
                    except (struct.error, IndexError):
                        params = []
                if name:
                    out.append((name, src, params))
            except (struct.error, IndexError):
                continue
        return out

    def extensions(self):
        return extension_list(self.payload(0x2234))

    def images(self, inflate=True):
        """The image bank, and the index that maps a handle to a position in it.
        """
        p = self.payload(0x6666)
        if p is None:
            return None, "no 0x6666"
        if len(p) < 4:
            return None, "0x6666 is %d bytes" % len(p)
        (count,) = struct.unpack_from("<I", p, 0)
        pos, out = 4, []
        for i in range(count):
            if pos + 12 > len(p):
                return out, "0x6666 truncated at image %d of %d" % (i, count)
            handle, dsize, csize = struct.unpack_from("<3I", p, pos)
            if pos + 12 + csize > len(p):
                return out, "0x6666 image %d claims %d compressed bytes" % (i, csize)
            entry = dict(handle=handle, at=pos + 4, decompressed=dsize, compressed=csize)
            if inflate:
                try:
                    raw = zlib.decompress(p[pos + 12 : pos + 12 + csize])
                except zlib.error as exc:
                    entry["error"] = "inflate failed: %s" % exc
                    raw = b""
                if raw:
                    entry["inflated"] = len(raw)
                    if len(raw) != dsize:
                        entry["error"] = "inflated to %d, header says %d" % (len(raw), dsize)
                    if len(raw) >= 32:
                        (entry["checksum"], entry["unnamed"],
                         entry["dataSize"]) = struct.unpack_from("<3I", raw, 0)
                        entry["width"], entry["height"] = struct.unpack_from("<2H", raw, 12)
                        entry["graphicMode"], entry["flags"] = raw[16], raw[17]
                        (entry["hotSpotX"], entry["hotSpotY"],
                         entry["actionX"], entry["actionY"]) = struct.unpack_from("<4h", raw, 20)
                        (entry["transparent"],) = struct.unpack_from("<I", raw, 28)
            out.append(entry)
            pos += 12 + csize
        left = len(p) - pos
        note = "0x6666, %d images, consumed %d/%d bytes" % (count, pos, len(p))
        if left:
            note += "  ** %d BYTES LEFT OVER **" % left

        q = self.payload(0x5555)
        if q is None:
            note += "; no 0x5555 index"
        elif len(q) % 4:
            note += "; 0x5555 is %d bytes, not a u32 array" % len(q)
        else:
            idx = struct.unpack_from("<%dI" % (len(q) // 4), q, 0)
            wrong = [e["handle"] for e in out
                     if e["handle"] >= len(idx) or idx[e["handle"]] != e["at"]]
            holes = sum(1 for h in range(len(idx))
                        if idx[h] and h not in {e["handle"] for e in out})
            if wrong or holes:
                note += "; ** 0x5555 disagrees on %d handles, %d filled holes **" % (
                    len(wrong), holes)
            else:
                note += "; 0x5555 indexes all %d by handle (%d unused slots)" % (
                    len(out), len(idx) - len(out))
        return out, note

    def fonts(self):
        """The font bank, which is the image bank's exact shape with Windows font
        descriptions in place of pictures.
        """
        p = self.payload(0x6667)
        if p is None:
            return None, "no 0x6667 font bank"
        (count,) = struct.unpack_from("<I", p, 0)
        pos, out, problems = 4, [], []
        for _ in range(count):
            if pos + 12 > len(p):
                problems.append("record head overruns")
                break
            handle, dsize, csize = struct.unpack_from("<3I", p, pos)
            entry = dict(handle=handle)
            try:
                raw = zlib.decompress(p[pos + 12 : pos + 12 + csize])
            except zlib.error as exc:
                problems.append("handle %d will not inflate (%s)" % (handle, exc))
                raw = b""
            if len(raw) != dsize:
                problems.append("handle %d inflated to %d, stored %d"
                                % (handle, len(raw), dsize))
            if len(raw) >= 72:
                b = 12
                (entry["height"], entry["width"], entry["escapement"],
                 entry["orientation"], entry["weight"]) = struct.unpack_from(
                    "<5i", raw, b)
                entry["italic"], entry["underline"] = raw[b + 20], raw[b + 21]
                entry["strikeout"], entry["charset"] = raw[b + 22], raw[b + 23]
                entry["face"] = cstr(raw[b + 28 : b + 60])
            out.append(entry)
            pos += 12 + csize
        if pos != len(p) and not problems:
            problems.append("bank left %d bytes over" % (len(p) - pos))
        return out, "; ".join(problems)

    def globals(self):
        """The application's global values and global strings."""
        values, strings = None, None
        p = self.payload(0x2232)
        if p is not None and len(p) >= 2:
            (n,) = struct.unpack_from("<H", p, 0)
            if 2 + 5 * n == len(p):
                values = dict(
                    count=n,
                    values=list(struct.unpack_from("<%dI" % n, p, 2)) if n else [],
                    types=list(p[2 + 4 * n : 2 + 5 * n]),
                )
            else:
                values = dict(count=n, error="2 + 5*%d != %d" % (n, len(p)))
        q = self.payload(0x2233)
        if q is not None and len(q) >= 4:
            (n,) = struct.unpack_from("<I", q, 0)
            out, pos = [], 4
            for _ in range(n):
                end = q.find(b"\x00", pos)
                if end < 0:
                    break
                out.append(q[pos:end].decode("cp1252", "replace"))
                pos = end + 1
            strings = dict(count=n, strings=out,
                           error=None if pos == len(q) and len(out) == n
                           else "walk consumed %d/%d for %d strings" % (pos, len(q), n))
        return values, strings

    def objects(self):
        """The object bank: every object the game defines, each as its own chunk list.
        """
        which = 0x2229 if self.payload(0x2229) is not None else 0x223F
        p = self.payload(which)
        if p is None:
            return None, "no object bank: neither 0x2229 nor 0x223F"
        self.bank_id = which
        (count,) = struct.unpack_from("<I", p, 0)
        pos = 4
        out = []
        for _ in range(count):
            chunks, stop, pos = walk_chunks(p, pos, len(p), keep_payload=True)
            rec = {c.id: c.payload for c in chunks}
            head = rec.get(0x4444)
            entry = dict(stop=stop, ids=[c.id for c in chunks])
            if head is not None and len(head) >= 4:
                entry["handle"], entry["type"] = struct.unpack_from("<2H", head, 0)
            if head is not None and len(head) >= 16:

                (entry["flags"],) = struct.unpack_from("<H", head, 4)
                entry["inkEffect"], entry["inkEffectParameter"] = (
                    struct.unpack_from("<2I", head, 8)
                )
            entry["name"] = cstr(rec[0x4445]) if rec.get(0x4445) else None
            entry["properties_len"] = len(rec[0x4446]) if rec.get(0x4446) else 0
            entry["properties"] = rec.get(0x4446)

            entry["shader"] = rec.get(0x4448)
            entry["code"], entry["code_ok"] = object_type_code(
                rec.get(0x4446), entry.get("type")
            )
            entry["qualifiers"] = object_qualifiers(rec.get(0x4446),
                                        entry.get("type"))
            entry["fadeIn"], entry["fadeOut"] = object_transitions(rec.get(0x4446))
            if (entry.get("type") or 0) >= 32:
                entry["private"] = extension_private(rec.get(0x4446))
            body = rec.get(0x4446)

            entry["movements"] = (
                [] if entry.get("type") in (0, 1) else active_movements(body)
            )
            if entry.get("type") == 2:
                entry["values"], entry["strings"], entry["alterable_note"] = (
                    active_alterables(body)
                )
                entry["animations"], entry["animation_note"] = active_animations(body)
            elif (entry.get("type") or 0) >= 32:

                entry["values"], entry["strings"], entry["alterable_note"] = (
                    active_alterables(body)
                )
            out.append(entry)
        leftover = len(p) - pos
        return out, ("0x%04X, consumed %d/%d bytes" % (which, pos, len(p))) + (
            "" if leftover == 0 else "  ** %d BYTES LEFT OVER **" % leftover
        )

    def frames(self):
        """Every frame, with its settings, layers, objects, instances and events.
        """
        out = []
        for chunk in self.by_id.get(0x3333, []):
            kids, stop, _ = walk_chunks(
                chunk.payload, 0, len(chunk.payload), keep_payload=True
            )
            rec = {c.id: c.payload for c in kids}
            frame = dict(stop=stop, ids=[c.id for c in kids])
            frame["name"] = cstr(rec[0x3335]) if rec.get(0x3335) else None

            head = rec.get(0x3334)
            frame["flags"] = (
                struct.unpack_from("<I", head, 0x0C)[0]
                if head is not None and len(head) >= 16 else None
            )

            pw = rec.get(0x3336)
            frame["password"] = cstr(pw) if pw is not None else None

            frame["fadeIn"] = (transition(rec[0x333B], 0, "frame fadeIn: ")
                               if rec.get(0x333B) is not None else None)
            frame["fadeOut"] = (transition(rec[0x333C], 0, "frame fadeOut: ")
                                if rec.get(0x333C) is not None else None)
            frame["instances"], frame["instances_left"] = self._instances(
                rec.get(0x3338)
            )
            frame["events"] = self._events(rec.get(0x333D))
            out.append(frame)
        return out

    @staticmethod
    def _instances(p):
        if p is None:
            return [], 0
        (count,) = struct.unpack_from("<I", p, 0)
        out = []
        for i in range(count):
            off = 4 + i * 20
            if off + 20 > len(p):
                out.append(dict(truncated=True))
                return out, 0
            handle, objinfo = struct.unpack_from("<2H", p, off)
            x, y = struct.unpack_from("<2i", p, off + 4)

            ptype, pinfo = struct.unpack_from("<2H", p, off + 12)
            (layer,) = struct.unpack_from("<I", p, off + 16)
            out.append(dict(handle=handle, objectInfo=objinfo, x=x, y=y,
                            layer=layer,
                            parentType=ptype, parentObjectInfo=pinfo,
                            tail=p[off + 12 : off + 20].hex(" ")))
        return out, len(p) - (4 + count * 20)

    @staticmethod
    def _events(p):
        if p is None:
            return None
        info = dict(chunk_len=len(p), framed=p[:4] == b"ER>>" and p[-4:] == b"<<ER")
        info["objects_word"] = p[6] if len(p) > 6 else None
        idx = p.find(b"ERes")
        if idx >= 0 and idx + 8 <= len(p):
            (info["eres_len"],) = struct.unpack_from("<I", p, idx + 4)
            info["erev_sections"] = App._erev_sections(p, idx + 8, info["eres_len"])
            info["groups"] = App._groups(p, idx + 8, info["eres_len"])
            info["parameters"], info["parameter_note"] = App._parameters(
                p, idx + 8, info["eres_len"]
            )
            info["object_refs"] = App._object_refs(p, idx + 8, info["eres_len"])
            info["group_starts"] = App._group_starts(p, idx + 8, info["eres_len"])
        return info

    @staticmethod
    def _group_starts(p, base, total):
        pos, seen, out = base, 0, set()
        while seen < total:
            if pos + 8 > len(p) or p[pos : pos + 4] != b"ERev":
                return out
            (size,) = struct.unpack_from("<I", p, pos + 4)
            q, end = pos + 8, pos + 8 + size
            if end > len(p):
                return out
            while q < end:
                (neg,) = struct.unpack_from("<h", p, q)
                n = -neg
                if n <= 0 or q + n > end:
                    return out
                if p[q + 2] and q + 20 <= end:
                    ot, num = struct.unpack_from("<2h", p, q + 16)
                    if ot == -1 and num == -10:
                        out.add(q)
                q += n
            pos, seen = end, seen + size
        return out

    @staticmethod
    def _parameters(p, base, total):
        pos, seen, out, problems = base, 0, [], []
        while seen < total:
            if pos + 8 > len(p) or p[pos : pos + 4] != b"ERev":
                return out, "section chain broke"
            (size,) = struct.unpack_from("<I", p, pos + 4)
            q, end = pos + 8, pos + 8 + size
            if end > len(p):
                return out, "section overruns the chunk"
            while q < end:
                (neg,) = struct.unpack_from("<h", p, q)
                n = -neg
                if n <= 0 or q + n > end or q + 20 > end:
                    return out, "event record walk broke"
                nc, na = p[q + 2], p[q + 3]
                r = q + 14
                for kind, cnt in (("condition", nc), ("action", na)):
                    for _ in range(cnt):
                        if r + 2 > end:
                            return out, "ran off the section"
                        params, note = App._ace_parameters(p, r, kind)
                        out.extend(params)
                        if note:
                            problems.append("%s: %s" % (kind, note))
                        r += struct.unpack_from("<H", p, r)[0]
                q += n
            pos, seen = end, seen + size
        return out, "; ".join(problems[:3])

    @staticmethod
    def _ace_parameters(p, q, kind):
        (size,) = struct.unpack_from("<H", p, q)
        if size < 14:
            return [], "record is %d bytes, below the 14-byte head" % size
        count = p[q + 0x0C]
        r, out = q + (0x10 if kind == "condition" else 0x0E), []
        while r < q + size:
            if r + 4 > q + size:
                return out, "parameter head overruns the record"
            psize, ptype = struct.unpack_from("<2H", p, r)
            if psize < 4:
                return out, "parameter size %d below 4" % psize

            out.append(dict(type=ptype, size=psize, at=r,
                            data=p[r + 4 : r + psize]))
            r += psize
        if r != q + size:
            return out, "chain ends at %d, record ends at %d" % (r - q, size)
        if len(out) != count:
            return out, "chain holds %d, paramCount says %d" % (len(out), count)
        return out, ""

    @staticmethod
    def _object_refs(p, base, total):
        pos, seen, out = base, 0, []
        while seen < total:
            if pos + 8 > len(p) or p[pos : pos + 4] != b"ERev":
                return out
            (size,) = struct.unpack_from("<I", p, pos + 4)
            q, end = pos + 8, pos + 8 + size
            if end > len(p):
                return out
            while q < end:
                (neg,) = struct.unpack_from("<h", p, q)
                n = -neg
                if n <= 0 or q + n > end or q + 20 > end:
                    return out
                nc, na = p[q + 2], p[q + 3]
                r = q + 14
                for kind, cnt in (("condition", nc), ("action", na)):
                    for _ in range(cnt):
                        if r + 14 > end:
                            return out
                        (rs,) = struct.unpack_from("<H", p, r)
                        if rs < 14:
                            return out
                        objtype = struct.unpack_from("<h", p, r + 2)[0]
                        if objtype >= 0:
                            out.append(struct.unpack_from("<H", p, r + 6)[0])
                        r += rs
                q += n
            pos, seen = end, seen + size
        return out

    @staticmethod
    def _groups(p, base, total):
        pos, seen = base, 0
        starts = ends = depth = maxdepth = 0
        while seen < total:
            if pos + 8 > len(p) or p[pos : pos + 4] != b"ERev":
                return None
            (size,) = struct.unpack_from("<I", p, pos + 4)
            q, end = pos + 8, pos + 8 + size
            if end > len(p):
                return None
            while q < end:
                (neg,) = struct.unpack_from("<h", p, q)
                n = -neg
                if n <= 0 or q + n > end or q + 20 > end:
                    return None
                objtype, num = struct.unpack_from("<2h", p, q + 16)
                if objtype == -1 and num == -10:
                    starts += 1
                    depth += 1
                    maxdepth = max(maxdepth, depth)
                elif objtype == -1 and num == -11:
                    ends += 1
                    depth -= 1
                q += n
            pos, seen = end, seen + size
        return dict(starts=starts, ends=ends, maxDepth=maxdepth, finalDepth=depth)

    @staticmethod
    def _erev_sections(p, base, total):
        pos, seen, n = base, 0, 0
        while seen < total:
            if pos + 8 > len(p) or p[pos : pos + 4] != b"ERev":
                return None
            (size,) = struct.unpack_from("<I", p, pos + 4)
            pos += 8 + size
            seen += size
            n += 1
        return n if seen == total and pos <= len(p) else None
