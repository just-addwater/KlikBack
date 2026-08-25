# GENERATED — do not edit by hand. This file is produced by KlikBack's
# sync tooling; changes belong in the source it is generated from.
#
# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""Find where an MMF 2.0 game's data begins inside the file that carries it.

A Fusion 2 standalone is the runtime executable with the game appended, and
between the two there is usually a pack block holding the modules the game
needs.  Nothing here searches for a signature: the position is computed from
the executable's own section table and then stepped forward past whatever the
packer put in the way, so a file that does not have a game in it comes back
with no answer instead of with a plausible wrong one.

A `.ccn` — the same game data without the runtime wrapped round it — starts at
the beginning of the file, so both callers ask the same question and one of
them gets a trivial answer.
"""

from __future__ import annotations
import struct

PACK_HEADER = bytes([0x77, 0x77, 0x77, 0x77, 0x49, 0x87, 0x47, 0x12])

PRODUCTS = {0x0300: "MMF1", 0x0301: "MMF1.5", 0x0302: "MMF2-family"}

def overlay_offset(data):
    """Where the executable's own contents stop and the appended data starts.

    Computed from the PE section table — the end of the last section's raw data —
    because that is the file's own account of its size.  Reading a length from a
    header the game itself wrote would trust the thing being examined.
    """
    if data[:2] != b"MZ":
        return None
    (e_lfanew,) = struct.unpack_from("<I", data, 0x3C)
    if data[e_lfanew : e_lfanew + 4] != b"PE\x00\x00":
        return None
    (num_sections,) = struct.unpack_from("<H", data, e_lfanew + 6)
    (opt_size,) = struct.unpack_from("<H", data, e_lfanew + 20)
    sect = e_lfanew + 24 + opt_size
    end = 0
    for i in range(num_sections):
        raw_size, raw_ptr = struct.unpack_from("<II", data, sect + i * 40 + 16)
        end = max(end, raw_ptr + raw_size)
    return end if end and end < len(data) else None

def game_header_offset(data, start):
    """Where the game's own header sits, stepping past a pack block if one is there.

    The pack block is optional and self-describing, so this walks it rather than
    assuming a size.  It returns nothing when what it finds does not look like a
    game header, which is what makes "this is not a Fusion 2 file" an answer this
    module can give.
    """
    if data[start : start + 8] == PACK_HEADER:
        (data_size,) = struct.unpack_from("<I", data, start + 12)
        cand = start + data_size - 32
        if data[cand : cand + 4] in (b"PAME", b"PAMU"):
            return cand, "pack"

    if data[start : start + 4] in (b"PAME", b"PAMU"):
        return start, "direct"
    for magic in (b"PAME", b"PAMU"):
        idx = data.find(magic, start)
        while idx != -1:
            (rv,) = struct.unpack_from("<H", data, idx + 4)
            if rv in PRODUCTS or rv == 0x0207:
                return idx, "scan"
            idx = data.find(magic, idx + 1)
    return None, None
