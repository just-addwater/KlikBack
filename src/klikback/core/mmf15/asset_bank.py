# GENERATED — do not edit by hand. This file is produced by KlikBack's
# sync tooling; changes belong in the source it is generated from.
#
# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""The banks a compiled 1.5 game keeps its images, sounds, music and fonts in.

Each bank is a run of records with an offset table in front of it, and between
them they are most of a game's bytes. Reading them is where a rebuild gets the
artwork and audio it puts back into the project.

Records are found through the bank's own offset table rather than by walking
one record into the next, so a single unreadable record costs that record
rather than everything after it.
"""

from __future__ import annotations
import struct
from functools import lru_cache
from pathlib import Path
from klikback.core.common.compression_probe import decompress_clickteam_stream_with_consumed
from klikback.core.common.extension_inventory import chunk_payload, load_outer
from klikback.core.mmf15.image_salvage import SalvageProblem, salvage_image_record

BANKS = (
    (0x5555, 0x6666, "image"),
    (0x5556, 0x6667, "font"),
    (0x5557, 0x6668, "sample"),
    (0x5558, 0x6669, "music"),
)

OFFSET_BIAS = 4

class BankProblem(Exception):
    """Raised when a bank does not walk cleanly to its end."""

def bank_chunks(exe: Path) -> dict[int, bytes]:
    """The banks a compiled game carries."""
    wanted = {table for table, _bank, _name in BANKS}
    wanted |= {bank for _table, bank, _name in BANKS}
    found: dict[int, bytes] = {}
    for chunk in load_outer(exe):
        if chunk.chunk_id in wanted:
            if chunk.chunk_id in found:
                raise BankProblem(f"chunk 0x{chunk.chunk_id:04X} appears twice")
            found[chunk.chunk_id] = chunk_payload(chunk)
    return found

def read_offsets(table: bytes) -> list[int]:
    """The bank's own table of where each record starts."""
    if len(table) % 4:
        raise BankProblem(f"offset table is {len(table)} bytes, not a multiple of 4")
    return list(struct.unpack_from(f"<{len(table) // 4}I", table, 0))

def records_via_offsets(
    bank: bytes, offsets: list[int], decode: bool = True
) -> tuple[dict[int, bytes], int]:
    """Walk a bank by its table, so one bad record does not lose the rest.

    The bank carries a table saying where each record starts, and reading by that
    table is worth more than convenience: it removes an ambiguity that reading the
    records in sequence cannot. A compressed stream does not always state where it
    stops, so a sequential reader has to decide the boundary itself — the table
    just says.

    Three properties are asserted, and asserting them is the job as much as
    returning the records. The number of live slots must match the count the bank
    declares. Each slot must point at a record whose stored handle is that slot's
    own index. And the records must **partition** the payload: no two slots
    pointing at the same place, the first starting where the bank's data starts,
    and each record reaching exactly as far as the next one begins.

    That last one is checked from both ends. A record that decodes past its
    neighbour's start is a hard failure; one that stops short is counted as a
    boundary a sequential reader would have had to guess at, which is the measure
    of how much the table is buying.

    Every failure raises rather than being reported, and that is deliberate: a
    table that does not describe its bank is a discovery about the format, not a
    difference in content, and a reader that recovered from it would hide the very
    thing worth knowing. Bounding each record by the next start also keeps the
    walk linear — handing the decompressor the whole remaining bank each time
    makes it quadratic, which on a large game is the difference between seconds
    and over a minute.

    Decoding can be skipped, and then every check that reads only headers still
    runs. The compression here is pure Python, so on a large collection that is
    the difference between seconds and a coffee break.
    """
    if len(bank) < 4:
        raise BankProblem(f"bank payload is {len(bank)} bytes")
    count = struct.unpack_from("<I", bank, 0)[0]

    live = [(index, value) for index, value in enumerate(offsets) if value]
    if len(live) != count:
        raise BankProblem(
            f"offset table has {len(live)} non-zero slots, bank declares {count}"
        )

    by_start = {value - OFFSET_BIAS: index for index, value in live}
    if len(by_start) != len(live):
        raise BankProblem("two offset slots point at the same record")
    starts = sorted(by_start)
    if starts[0] != 4:
        raise BankProblem(f"first record starts at {starts[0]}, not 4")
    bounds = dict(zip(starts, starts[1:] + [len(bank)]))

    records: dict[int, bytes] = {}
    ambiguous = 0
    for pos in starts:
        index = by_start[pos]
        limit = bounds[pos]
        if pos + 8 > limit:
            raise BankProblem(f"slot {index} leaves no room for a record header")
        handle, size = struct.unpack_from("<II", bank, pos)
        if handle != index:
            raise BankProblem(f"slot {index} points at a record with handle {handle}")
        if not decode:
            continue
        try:
            decoded, consumed = decompress_clickteam_stream_with_consumed(
                bank[pos + 8:limit]
            )
        except ValueError as problem:
            raise BankProblem(f"handle {index}: {problem}") from problem
        if len(decoded) != size:
            raise BankProblem(
                f"handle {index} decodes to {len(decoded)} bytes, header says {size}"
            )
        records[index] = bytes(decoded)

        if pos + 8 + consumed > limit:
            raise BankProblem(f"handle {index} runs past the next record")
        if pos + 8 + consumed != limit:
            ambiguous += 1
    return records, ambiguous

def image_records_with_salvage(
    exe: Path,
) -> tuple[dict[int, bytes], list[dict[str, int]]]:
    """The image records, with partly-damaged ones recovered as far as they go.

    The reconstruction path's image reader. It is deliberately a *separate*
    function from the plain one, which raises on any record it cannot decode and
    must keep doing so: a reader that quietly substitutes content would turn a real
    format discovery into a silent pass, and the plain reader is what everything
    that checks the format uses. Here the standing rule is the other one — a field
    that cannot be recovered is a loss to substitute and report, not a reason to
    refuse a whole game.

    The structural checks are identical in both, and that is the point rather than
    duplication. The number of live slots must match the count the bank declares,
    each slot must point at a record carrying that slot's own handle, and the
    records must partition the bank with no overlap and no gap. Those are what make
    a record's boundary trustworthy in the first place, and salvaging up to a wrong
    boundary is inventing rather than recovering.

    Only after all that does a record that will not decode get taken apart: the
    prefix that did decode is the picture as far as it goes, and rebuilding it is
    what produces a usable image with an honest hole. The per-record numbers come
    back alongside so the loss can be reported by name and size.
    """
    chunks = bank_chunks(exe)
    table_id, bank_id, _name = BANKS[0]
    table = chunks.get(table_id)
    bank = chunks.get(bank_id)
    if table is None or bank is None:
        raise BankProblem("image bank is missing its bank or its offset table")

    offsets = read_offsets(table)
    count = struct.unpack_from("<I", bank, 0)[0]
    live = [(index, value) for index, value in enumerate(offsets) if value]
    if len(live) != count:
        raise BankProblem(
            f"offset table has {len(live)} non-zero slots, bank declares {count}"
        )
    by_start = {value - OFFSET_BIAS: index for index, value in live}
    if len(by_start) != len(live):
        raise BankProblem("two offset slots point at the same record")
    starts = sorted(by_start)
    if starts[0] != 4:
        raise BankProblem(f"first record starts at {starts[0]}, not 4")
    bounds = dict(zip(starts, starts[1:] + [len(bank)]))

    records: dict[int, bytes] = {}
    salvaged: list[dict[str, int]] = []
    for pos in starts:
        index = by_start[pos]
        limit = bounds[pos]
        if pos + 8 > limit:
            raise BankProblem(f"slot {index} leaves no room for a record header")
        handle, size = struct.unpack_from("<II", bank, pos)
        if handle != index:
            raise BankProblem(f"slot {index} points at a record with handle {handle}")
        stream = bank[pos + 8 : limit]
        try:
            decoded, _consumed = decompress_clickteam_stream_with_consumed(stream)
        except ValueError:
            decoded = None
        if decoded is not None and len(decoded) == size:
            records[index] = bytes(decoded)
            continue

        prefix, _consumed = decompress_clickteam_stream_with_consumed(
            stream, partial=True
        )
        try:
            record, stats = salvage_image_record(bytes(prefix), size)
        except SalvageProblem as problem:
            raise BankProblem(f"handle {index}: {problem}") from problem
        stats["handle"] = index
        records[index] = record
        salvaged.append(stats)
    return records, salvaged

@lru_cache(maxsize=None)
def bank_contents(
    exe: Path, budget: int = 0
) -> tuple[dict[str, dict[int, bytes]], dict[str, int], int, int]:
    """Everything one bank holds, in order."""
    chunks = bank_chunks(exe)
    contents: dict[str, dict[int, bytes]] = {}
    ambiguous: dict[str, int] = {}
    families = skipped = 0
    for table_id, bank_id, name in BANKS:
        table = chunks.get(table_id)
        bank = chunks.get(bank_id)
        if table is None and bank is None:
            continue
        if table is None or bank is None:
            missing = f"0x{table_id:04X}" if table is None else f"0x{bank_id:04X}"
            raise BankProblem(f"{name} bank is missing its {missing}")
        decode = not budget or len(bank) <= budget
        skipped += not decode
        offsets = read_offsets(table)
        found, ambiguous[name] = records_via_offsets(bank, offsets, decode)

        contents[name] = found if decode else None
        families += 1
    return contents, ambiguous, families, skipped
