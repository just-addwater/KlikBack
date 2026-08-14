# GENERATED — do not edit by hand. This file is produced by KlikBack's
# sync tooling; changes belong in the source it is generated from.
#
# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""An application's window options -- how its window looks and behaves."""

from __future__ import annotations
from klikback.core.common.mixed_multiframe_blind_reconstruct import runtime_window_options

WINDOW_OPTION_RUNTIME_BITS_15 = {
    0x1000: 25,
    0x2000: 26,
}

def window_options_15(flags: int) -> int:
    """The window settings a compiled game was built with."""
    options = runtime_window_options(flags)
    for option, bit in WINDOW_OPTION_RUNTIME_BITS_15.items():
        if flags >> bit & 1:
            options |= option
    return options
