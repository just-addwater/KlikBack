# GENERATED — do not edit by hand. This file is produced by KlikBack's
# sync tooling; changes belong in the source it is generated from.
#
# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""An application's run options -- how it behaves when it is played."""

from __future__ import annotations
import struct
from pathlib import Path
from klikback.core.common.compare import find_chunk
from klikback.core.common.extension_inventory import chunk_payload, load_outer

APP_HEADER_CHUNK = 0x2223

RUN_OPTION_RUNTIME_BITS_15 = {
    0x01: 10,
    0x02: 3,
    0x04: 16,
    0x08: 19,
    0x10: 24,
    0x80: 27,
}

def run_options_15(app_flags: int) -> int:
    """The options a compiled game was built with."""
    return sum(
        option
        for option, bit in RUN_OPTION_RUNTIME_BITS_15.items()
        if app_flags >> bit & 1
    )

def app_flags(exe: Path) -> int:
    """The individual settings those options are made of."""
    header = chunk_payload(find_chunk(load_outer(exe), APP_HEADER_CHUNK))
    return struct.unpack_from("<I", header, 0)[0]
