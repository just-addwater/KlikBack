# GENERATED — do not edit by hand. This file is produced by KlikBack's
# sync tooling; changes belong in the source it is generated from.
#
# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""The chunk grammar an MMF 2.0 game is written in.

Everything in a Fusion 2 game after its 16-byte header is a flat list of
records — a two-byte identifier, a two-byte storage flag, a four-byte size,
then that many bytes — and every larger structure in the format is one of
those payloads holding another such list.  This module is the walk, and
almost nothing else in the engine reads a raw offset.

**The walk steps; it never searches.**  It starts at a computed position and
moves record by record to a terminator.  A tag that is *found* proves nothing
about where the record before it ended, and a game's own sound samples spell
four-letter tags often enough that searching for one is a way of landing in
the middle of the data.  A walk that does not reach its terminator says so and
returns what it has, because a short walk is a fact about the reader at least
as often as about the file.

A payload is stored raw, deflated, or encrypted, and the flag says which.  The
encrypted forms belong to a later Clickteam generation: they are recognised
and counted, not opened.
"""

from __future__ import annotations
import struct
import zlib
from klikback.core.mmf2.build_census import game_header_offset, overlay_offset

HEADER_SIZE = 16

CHUNK_HEADER_SIZE = 8

TERMINATOR = 0x7F7F

class Chunk:
    """One record of a chunk list: where it starts, what it is, how it is stored, and
    what came out of it.
    """
    __slots__ = ("offset", "id", "flags", "size", "status", "payload_len", "payload")

    def __init__(self, offset, cid, flags, size):
        """Note a record's framing.  What it holds is filled in afterwards, if it is
        looked at at all.
        """
        self.offset = offset
        self.id = cid
        self.flags = flags
        self.size = size
        self.status = "?"
        self.payload_len = None
        self.payload = None

def decode_chunk(data, chunk, keep_payload):
    """Unpack one record's payload according to its storage flag.

    Never raises.  Damage is recorded on the record — truncated, a deflate stream
    that will not open, a size that disagrees with its own header, a storage flag
    this format does not define — so that one bad record in a large game is a line
    in a report rather than the end of the read.
    """
    start = chunk.offset + CHUNK_HEADER_SIZE
    raw = data[start : start + chunk.size]
    if len(raw) < chunk.size:
        chunk.status = "truncated"
        return
    if chunk.flags == 0:
        chunk.status = "raw"
        chunk.payload_len = chunk.size
        if keep_payload:
            chunk.payload = raw
        return
    if chunk.flags == 1:
        if chunk.size < 8:
            chunk.status = "zlib-header-short"
            return
        dsize, csize = struct.unpack_from("<II", raw, 0)
        try:
            out = zlib.decompress(raw[8 : 8 + csize])
        except zlib.error as exc:
            chunk.status = "zlib-error:%s" % str(exc).split(" ")[0]
            return
        chunk.payload_len = len(out)
        chunk.status = "zlib" if len(out) == dsize else "zlib-size-mismatch"
        if keep_payload:
            chunk.payload = out
        return
    if chunk.flags in (2, 3):
        chunk.status = "encrypted"
        return
    chunk.status = "unknown-flag"

def walk_chunks(data, pos, end, limit=100000, keep_payload=False, decode=True):
    """Step a chunk list from a position to its terminator.

    Returns the records, the reason it stopped, and where it stopped.  The stop
    reason is part of the answer: reaching a terminator, running out of bytes, and
    finding a record that claims more space than its container has are three
    different outcomes and callers treat them differently.
    """
    chunks = []
    while True:
        if len(chunks) >= limit:
            return chunks, "chunk-limit", pos
        if pos + CHUNK_HEADER_SIZE > end:
            return chunks, "ran-out-of-bytes", pos
        cid, flags = struct.unpack_from("<HH", data, pos)
        (size,) = struct.unpack_from("<I", data, pos + 4)
        chunk = Chunk(pos, cid, flags, size)
        if pos + CHUNK_HEADER_SIZE + size > end:
            chunk.status = "overruns-container"
            chunks.append(chunk)
            return chunks, "overrun", pos
        if decode:
            decode_chunk(data, chunk, keep_payload)
        chunks.append(chunk)
        pos += CHUNK_HEADER_SIZE + size
        if cid == TERMINATOR:
            return chunks, "terminator", pos

def read_header(data, path):
    """Read the game header, and say how it was found.

    Tries the appended-data position first and the start of the file second, so
    one function answers for a standalone and for a bare game-data file.  When
    neither yields a header it returns the reason instead, which is how the rest
    of the engine learns that a file is not a Fusion 2 game at all.
    """
    start = overlay_offset(data)
    off = how = None
    if start is not None:
        off, how = game_header_offset(data, start)
    if off is None:
        off, how = game_header_offset(data, 0)
        how = how and ("wholefile-" + how)
    if off is None:
        return None, "no PAME/PAMU header", None
    magic = data[off : off + 4].decode("ascii", "replace")
    rv, rsub = struct.unpack_from("<HH", data, off + 4)
    pver, pbuild = struct.unpack_from("<II", data, off + 8)
    return off, how, (magic, rv, rsub, pver, pbuild)
