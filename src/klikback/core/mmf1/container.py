# GENERATED — do not edit by hand. This file is produced by KlikBack's
# sync tooling; changes belong in the source it is generated from.
#
# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""Read and re-write the records an MMF 1.0 project is built from.

The 1.0 twin of the 1.5 record reader: class blocks and their properties,
read into named fields and written back byte-for-byte. Everything that edits a
1.0 project semantically -- rather than by poking bytes at an offset -- stands
on this.
"""

from __future__ import annotations
import struct
from dataclasses import dataclass, field

CLASS_SIGNATURE = b"Ver 1.1\x00"

INHERITED = 0xFFFF

TYPE_STRING = 0x03

TYPE_VOID = 0x04

@dataclass
class Entry98:
    """One entry of a property list."""

    type_id: int
    index: int
    size: int
    a: int
    b: int
    word: int | None = None
    payload: bytes = b""

    @property
    def inherited(self) -> bool:
        """Whether this entry takes the default rather than storing a value.

        The format keeps "unset" apart from "set to zero", and the editor shows the
        two differently, so the difference is read and written rather than flattened.
        """
        return self.size == INHERITED

    def pack(self) -> bytes:
        """Write the entry back exactly as it was read."""
        head = struct.pack(
            "<BBHII", self.type_id, self.index, self.size, self.a, self.b
        )
        if self.inherited or self.type_id == TYPE_VOID:
            return head
        if self.type_id == TYPE_STRING:
            return head + self.payload
        return head + struct.pack("<I", self.word or 0) + self.payload

@dataclass
class Property98:
    """One property of one record."""
    tag: str
    unknown: int
    entries: list[Entry98] = field(default_factory=list)

    def pack(self) -> bytes:
        """Write the property and all its entries back exactly as they were read.
        """
        out = struct.pack("<H", len(self.tag)) + self.tag.encode("ascii")
        out += struct.pack("<II", self.unknown, len(self.entries))
        for entry in self.entries:
            out += entry.pack()
        return out

@dataclass
class ClassBlock98:
    """One record: its class, its properties, and how to write it back exactly.
    """
    name: str
    scratch: int
    properties: list[Property98] = field(default_factory=list)

    def pack(self) -> bytes:
        """Write the whole record back exactly as it was read.

        This is the guarantee the rebuild rests on: a record can be read into named
        properties, one of them changed, and written back, with every byte that was
        not the change coming out the same.
        """
        out = CLASS_SIGNATURE
        out += struct.pack(
            "<III", len(self.properties), self.scratch, len(self.name)
        )
        out += self.name.encode("ascii")
        for prop in self.properties:
            out += prop.pack()
        return out
