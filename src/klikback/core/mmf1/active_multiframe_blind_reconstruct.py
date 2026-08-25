# GENERATED — do not edit by hand. This file is produced by KlikBack's
# sync tooling; changes belong in the source it is generated from.
#
# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""A helper kept from the earlier Active-only rebuild path."""

from __future__ import annotations
import struct

def frame_title(frame: bytes) -> bytes:
    """A frame's title, as the compiled game stored it."""
    pass_pos = frame.index(b"\x04\x00Pass")

    empty_match = None
    for length_pos in reversed(range(max(0, pass_pos - 260), pass_pos - 9)):
        length = struct.unpack_from("<H", frame, length_pos)[0]
        name_pos = length_pos + 10
        if length == 0xFFFF and name_pos == pass_pos:
            return b""
        if name_pos + length == pass_pos and (
            length == 0 or frame[pass_pos - 1] == 0
        ):
            title = frame[name_pos:pass_pos]

            if title and title != b"\x00":
                return title
            if empty_match is None:
                empty_match = title
    if empty_match is not None:
        return empty_match
    raise ValueError("could not locate the neutral frame title")
