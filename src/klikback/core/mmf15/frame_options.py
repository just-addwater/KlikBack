# GENERATED — do not edit by hand. This file is produced by KlikBack's
# sync tooling; changes belong in the source it is generated from.
#
# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""One frame's own options, translated from the compiled game's flags."""

from __future__ import annotations

PFOP_FROM_FRAME_FLAG = {
    0x0001: 0x08,
    0x0002: 0x01,
    0x0004: 0x02,
    0x0020: 0x04,
    0x0100: 0x10,
    0x0400: 0x20,
}

KNOWN_FRAME_FLAG_MASK = 0x0527

NON_OPTION_FRAME_FLAGS = 0x0040

def pfop_from_frame_flags(frame_flags: int) -> int:
    """The editor's frame options, from the flags the runtime carries."""
    unknown = frame_flags & ~(KNOWN_FRAME_FLAG_MASK | NON_OPTION_FRAME_FLAGS)
    if unknown:
        raise ValueError(
            f"unmapped runtime frame flags 0x{unknown:04X} "
            f"(full word 0x{frame_flags:04X})"
        )
    pfop = 0
    for bit, value in PFOP_FROM_FRAME_FLAG.items():
        if frame_flags & bit:
            pfop |= value
    return pfop
