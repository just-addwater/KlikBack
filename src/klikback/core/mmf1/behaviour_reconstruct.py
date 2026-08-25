# GENERATED — do not edit by hand. This file is produced by KlikBack's
# sync tooling; changes belong in the source it is generated from.
#
# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""Recover the behaviours attached to objects -- their own private event sheets.
"""

from __future__ import annotations
from klikback.core.common.multiframe_reconstruct import frame_records

def editor_frames(cca: bytes) -> list[bytes]:
    """The frames a behaviour's events are stored in."""
    _list, _tail, spans = frame_records(cca)
    return [cca[start:end] for start, end in spans]
