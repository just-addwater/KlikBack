# GENERATED — do not edit by hand. This file is produced by KlikBack's
# sync tooling; changes belong in the source it is generated from.
#
# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""Recover the qualifier groups objects belong to.

A qualifier lets events act on every object of a kind at once. The membership
survives compilation; the editor's way of storing it does not, so it is
rebuilt.
"""

from __future__ import annotations
import struct

QUALIFIER_TAG = b"\x04\x00Qual"

def qualifier_property(payload: bytes) -> bytes:
    """The property holding an object's qualifier memberships."""
    if payload and len(payload) != 18:
        raise ValueError(f"qualifier payload should be empty or 18 bytes, found {len(payload)}")
    if payload:
        qualifier_indices(payload)
    return (
        QUALIFIER_TAG
        + struct.pack("<II", 1, 1)
        + struct.pack("<HH", 10, len(payload))
        + struct.pack("<II", 1, 1)
        + struct.pack("<I", len(payload))
        + payload
    )

def qualifier_indices(payload: bytes) -> list[int]:
    """Which qualifier groups an object belongs to."""
    if len(payload) != 18:
        raise ValueError(f"qualifier list should contain nine words, found {len(payload)} bytes")
    words = list(struct.unpack("<9H", payload))
    if 0xFFFF in words:
        indices = words[: words.index(0xFFFF)]
    elif all(index <= 99 for index in words):
        indices = words
    else:
        raise ValueError("unterminated qualifier list contains an invalid id")
    if any(index > 99 for index in indices):
        raise ValueError(f"qualifier list contains an invalid id: {indices}")
    return indices
