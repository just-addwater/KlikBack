# GENERATED — do not edit by hand. This file is produced by KlikBack's
# sync tooling; changes belong in the source it is generated from.
#
# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""What a 1996 file's asset banks claim, checked against the bytes that are
actually there -- and the two repairs that follow from it.

The four asset banks (image, font, music, sound) all carry the same table: a
count, then an offset and a size for each slot. Nothing in the format makes
that table agree with the segment holding it, and two ways of disagreeing turn
up in real files. Both are a copy that is short of bytes rather than a format
this cannot read:

- a bank table naming assets that run past the end of its own segment, in a
  file whose container is otherwise perfect; and
- one level further out, a final segment that runs past the end of the file
  itself, which is what an interrupted download leaves behind.

Either one is invisible to a container check. The segments can tile exactly,
every level can walk and every object parse, and the file still be incomplete
-- so a reader that only checks the container calls it sound, and the editor
then allocates on the size the table declares and runs out of memory. A
container that tiles is not a file that is whole.

Both repairs drop and neither invents. A slot whose bytes are not in the file
names something that was already gone before this ran; the repair is to stop
the file claiming otherwise, so an editor can open everything that did
survive.
"""

from __future__ import annotations
import struct
import klikback.core.tgf.format as tgf
import klikback.core.tgf.unprotect as tgf_unprotect

def repair_bank(data: bytes) -> tuple[bytes, list[int]]:
    """A bank with every slot whose data is not in the file emptied, and the list of
    slots that were dropped so a caller can report them.

    Nothing is invented and nothing is substituted. The assets that survive are
    repacked in order and the entries naming absent bytes are removed, which is
    what makes the table and the segment agree again.
    """
    (count,) = struct.unpack_from("<I", data, 0)
    table_end = 4 + 8 * count
    if table_end > len(data):
        raise tgf.BankProblem(
            f"a table of {count} needs {table_end} bytes, the bank has "
            f"{len(data)}")
    table: list[tuple[int, int]] = []
    body = bytearray()
    dropped: list[int] = []
    for slot in range(count):
        offset, size = struct.unpack_from("<II", data, 4 + 8 * slot)
        if not offset:
            table.append((0, 0))
            continue
        if offset < table_end or offset + size > len(data):
            table.append((0, 0))
            dropped.append(slot)
            continue
        table.append((table_end + len(body), size))
        body += data[offset:offset + size]

    out = bytearray(struct.pack("<I", count))
    for offset, size in table:
        out += struct.pack("<II", offset, size)
    return bytes(out) + bytes(body), dropped

def repair_truncated(data: bytes) -> tuple[bytes, list[str]]:
    """A file whose final segment overruns the file itself, cut back to the bytes it
    actually holds.

    Because the truncation is always in the segment flagged last, and the last
    segment of a 1996 file is an asset bank, **nothing before that bank's own
    header moves**: no level, no object pointer, no level address, and neither of
    the two file pointers. That is a far stronger guarantee than a whole-file
    rebuild can offer -- and it is checked rather than assumed, because a splice
    that landed one byte out would still produce a file that reads. Three checks,
    each of which a plausible-looking wrong splice would fail: the bytes before
    the repaired segment are unchanged, the result parses without the clipping
    that made the input readable at all, and every surviving asset carries the
    same bytes it did before.

    The file stays protected if it was protected. This restores the container;
    opening it is still the unprotect step's job.
    """
    game = tgf.read(data, clip_truncated=True)
    segment = game.segments[-1]
    if not segment.missing:
        return data, []
    if segment.ident not in tgf.BANK_SEGMENTS:
        raise tgf.BankProblem(
            f"the truncated segment is {segment.ident:#06x} "
            f"({segment.name}), not an asset bank -- this repair drops whole "
            f"assets from a bank and has nothing to say about a short "
            f"{segment.name}")
    name = tgf.BANK_SEGMENTS[segment.ident]
    declared = len(segment.data) + segment.missing
    try:
        new_bank, dropped = repair_bank(segment.data)
    except tgf.BankProblem as exc:
        raise tgf.BankProblem(
            f"{name} bank ({segment.ident:#04x}): the truncation reached the "
            f"bank's own table, so which assets the file held is no longer "
            f"recoverable -- {exc}") from exc

    out = data[:segment.offset] + tgf_unprotect.pack_block(
        segment.ident, new_bank, last=True)

    if out[:segment.offset] != data[:segment.offset]:
        raise AssertionError(
            "the repair changed a byte before the truncated segment's header")
    after = tgf.read(out)
    if len(after.levels()) != len(game.levels()):
        raise AssertionError(
            f"the repair changed the level count, {len(game.levels())} -> "
            f"{len(after.levels())}")
    kept = _same_assets(segment.data, after.segments[-1].data)

    notes = [
        f"{name} bank ({segment.ident:#04x}): the file holds "
        f"{len(segment.data):,} of the {declared:,} bytes its header declares "
        f"-- {segment.missing:,} short ({100 * len(segment.data) / declared:.1f} %)",
    ]
    if dropped:
        notes.append(
            f"{name} bank ({segment.ident:#04x}): dropped slot(s) "
            f"{', '.join(str(s) for s in dropped)} -- their data is not in "
            f"the file")
    notes.append(
        f"{name} bank ({segment.ident:#04x}): {kept} asset(s) kept, byte for "
        f"byte")
    return out, notes

def _same_assets(before: bytes, after: bytes) -> int:
    """How many slots survived, having checked that every one of them carries the
    bytes it carried before.

    The table is rewritten by the repair, so a slot's offset legitimately moves;
    its contents must not. A repack that dropped the wrong slot, or that was one
    entry out, still produces a bank that walks and tiles -- so walking is not the
    check, and comparing the payloads is. The original side is read straight off
    its own table rather than walked, because a truncated bank is precisely a bank
    that does not tile.
    """
    (count,) = struct.unpack_from("<I", before, 0)
    old: dict[int, bytes] = {}
    for slot in range(count):
        offset, size = struct.unpack_from("<II", before, 4 + 8 * slot)
        if offset and offset + size <= len(before):
            old[slot] = before[offset:offset + size]
    kept = 0
    for slot, offset, size in tgf.walk_bank(after):
        if slot not in old:
            raise AssertionError(f"the repair invented bank slot {slot}")
        if after[offset:offset + size] != old[slot]:
            raise AssertionError(f"the repair changed bank slot {slot}'s bytes")
        kept += 1
    return kept

def repair(game: tgf.GameFile) -> tuple[bytes, list[str]]:
    """The game with every truncated asset dropped and every pointer recomputed.

    A file with nothing to drop comes back untouched, byte for byte, and that is a
    `return` rather than a hope: this rebuild recomputes the object pointers and
    the first-bank pointer, which a protected file legitimately carries stale, so
    re-emitting a healthy file would move bytes for no reason at all.

    When something is dropped, the result is checked against the input the way a
    repair has to be. Every segment that was not repaired must come back
    byte-identical and the level count must be unchanged; a level segment that
    moved is named rather than allowed silently, because its object pointers
    legitimately change with it.
    """
    notes: list[str] = []
    segments: list[tuple[int, bytes]] = []
    repaired: set[int] = set()
    for segment in game.segments:
        data = segment.data
        if segment.ident in tgf.BANK_SEGMENTS and data:
            data, dropped = repair_bank(data)
            if dropped:
                repaired.add(segment.ident)
                notes.append(
                    f"{tgf.BANK_SEGMENTS[segment.ident]} bank "
                    f"({segment.ident:#04x}): dropped slot(s) "
                    f"{', '.join(str(s) for s in dropped)} -- their data is "
                    f"not in the file")
        segments.append((segment.ident, data))

    if not notes:
        return game.raw, []

    count = len(game.levels())
    header = bytearray(game.raw[:tgf.OFF_LEVEL_TABLE])
    struct.pack_into("<H", header, tgf.OFF_TOC_LENGTH, 4 * count)
    level_table_end = tgf.OFF_LEVEL_TABLE + 4 * count
    body = bytearray()
    addresses: list[int] = []
    first_bank = 0
    globals_at = 0
    for i, (ident, data) in enumerate(segments):
        position = level_table_end + len(body)
        if ident == 0x06 and data:
            globals_at = position + 6
        if ident == 0x08:
            addresses.append(position + 6)
        if ident in tgf.BANK_SEGMENTS and not first_bank:
            first_bank = position
        body += tgf_unprotect.pack_block(ident, data,
                                         last=(i == len(segments) - 1))
    struct.pack_into("<I", header, tgf.OFF_FIRST_NON_GAME_SEGMENT, first_bank)
    out = bytearray(header)
    out += struct.pack(f"<{count}I", *addresses) if count else b""
    out += body
    tgf_unprotect._fix_object_pointers(out, addresses, globals_at)

    after = tgf.read(bytes(out))
    if len(after.levels()) != count:
        raise AssertionError(
            f"the repair changed the level count, {count} -> "
            f"{len(after.levels())}")
    before_list = list(game.segments)
    after_list = list(after.segments)
    if [s.ident for s in before_list] != [s.ident for s in after_list]:
        raise AssertionError("the repair changed the segment order")
    for old, new in zip(before_list, after_list):
        if old.ident in repaired or old.data == new.data:
            continue
        if old.ident == 0x08:
            notes.append(
                f"level segment at {old.offset} moved, so its object pointers "
                f"were recomputed")
            continue
        raise AssertionError(
            f"the repair changed segment {old.ident:#04x}, which it should "
            f"not have touched")
    return bytes(out), notes
