# GENERATED — do not edit by hand. This file is produced by KlikBack's
# sync tooling; changes belong in the source it is generated from.
#
# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""Read and re-write the records an MMF 1.5 project is built from.

Below the container's regions are *class blocks*: one per object, per frame,
per application, each holding a list of properties. This reads them into
named fields and writes them back out again, byte-for-byte, which is what
lets the pipeline edit a property by name instead of poking bytes at an
offset.

The 1.5 and 1.0 record layouts differ in small, specific ways — the block
signature, the shape of a property's header, the sentinel meaning "inherited"
— and handling those differences honestly is this module's whole reason to
exist. A field that is read, changed and written back must come out identical
to what went in whenever nothing was changed; that property is the thing
everything above it relies on.
"""

from __future__ import annotations
import struct
from dataclasses import dataclass, field

MAGIC = b"CnC2"

PRODUCT_MMF15 = ord("U")

CLASS_SIGNATURE = b"v1.5"

INHERITED = 0xFFFFFFFF

TYPE_STRING = 0x03

TYPE_VOID = 0x04

TAG_CHARS = frozenset(
    b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
)

@dataclass(frozen=True)
class Header:
    """What the header says about the file."""

    product: int
    major: int
    stamp: int
    build: int
    build_slot: int

    @property
    def is_mmf15(self) -> bool:
        """Whether the file was written by Multimedia Fusion 1.5 rather than a sibling.
        """
        return self.product == PRODUCT_MMF15

    @property
    def is_classic_stamp(self) -> bool:
        """Whether the header's version word is the older, readable form."""
        return self.stamp >> 16 == 1

    @property
    def minor(self) -> int | None:
        """The minor version, where the header states it in a form that can be read.
        """
        return self.stamp & 0xFFFF if self.is_classic_stamp else None

    def __str__(self) -> str:
        """The header in one line, for a report a person reads."""
        version = f"v{self.major}.{self.minor}" if self.minor is not None else (
            f"v{self.major}.x stamp {self.stamp:#010x}"
        )
        return (
            f"{MAGIC.decode()}{chr(self.product)} {version} "
            f"build {self.build} (at +{self.build_slot:#04x})"
        )

@dataclass
class Entry:
    """One entry of a property list."""

    type_id: int
    index: int
    a: int
    b: int
    size: int
    word: int | None = None
    payload: bytes = b""

    @property
    def inherited(self) -> bool:
        """Whether this entry takes the default rather than storing a value.

        An MMF project stores "unset" as its own state, distinct from storing a zero,
        and the editor shows the two differently. Reading and writing that difference
        faithfully is why a rebuilt project's dialogs look like a hand-made one's.
        """
        return self.size == INHERITED

    @property
    def value(self) -> int | bytes | None:
        """What the entry holds — a number, some bytes, or nothing at all."""
        if self.inherited or self.type_id == TYPE_VOID:
            return None
        if self.type_id == TYPE_STRING:
            return self.payload
        return self.word if self.size == 0 else self.payload

    def pack(self) -> bytes:
        """Write the entry back exactly as it was read."""
        head = struct.pack(
            "<BBBBI", self.type_id, self.index, self.a, self.b, self.size
        )
        if self.inherited or self.type_id == TYPE_VOID:
            return head
        if self.type_id == TYPE_STRING:
            return head + self.payload
        return head + struct.pack("<I", self.word or 0) + self.payload

@dataclass
class Property:
    """One property of one record."""
    tag: str
    unknown: int
    entries: list[Entry] = field(default_factory=list)

    def pack(self) -> bytes:
        """Write the property and all its entries back exactly as they were read.
        """
        out = struct.pack("<H", len(self.tag)) + self.tag.encode("ascii")
        out += struct.pack("<II", self.unknown, len(self.entries))
        for entry in self.entries:
            out += entry.pack()
        return out

    def scalar(self) -> int | None:
        """The single number a property holds, if that is all it holds."""
        if len(self.entries) != 1:
            return None
        entry = self.entries[0]
        return None if entry.inherited or entry.size else entry.word

@dataclass
class ClassBlock:
    """One record: its class, its properties, and how to write it back exactly.
    """
    name: str
    properties: list[Property] = field(default_factory=list)

    def pack(self) -> bytes:
        """Write the whole record back exactly as it was read.

        This is the guarantee the rebuild rests on: a record can be read into named
        properties, one of them changed, and written back, with every byte that was
        not the change coming out the same. Patching a project is safe because of it.
        """
        out = CLASS_SIGNATURE
        out += struct.pack("<II", len(self.properties), len(self.name))
        out += self.name.encode("ascii")
        for prop in self.properties:
            out += prop.pack()
        return out

    def by_tag(self, tag: str) -> Property | None:
        """Find one property by name."""
        return next((p for p in self.properties if p.tag == tag), None)

def read_header(data: bytes) -> Header:
    """The file's own header: what it is, and which build wrote it."""
    if data[:4] != MAGIC:
        raise ValueError("not a CnC2 container")
    product, major = data[4], data[5]
    stamp = struct.unpack_from("<I", data, 0x06)[0]
    early, late = struct.unpack_from("<HH", data, 0x0A)

    if early and late:
        raise ValueError(
            f"both build slots set: +0x0A={early}, +0x0C={late}"
        )
    build, slot = (early, 0x0A) if early else (late, 0x0C)
    return Header(product, major, stamp, build, slot)

def read_entry(data: bytes, pos: int) -> tuple[Entry, int]:
    """Read one entry of a property list."""
    type_id, index, a, b, size = struct.unpack_from("<BBBBI", data, pos)
    pos += 8
    if size == INHERITED or type_id == TYPE_VOID:
        if size not in (INHERITED, 0):
            raise ValueError(f"type 0x{type_id:02X} with size {size} at 0x{pos:X}")
        return Entry(type_id, index, a, b, size), pos
    if type_id == TYPE_STRING:
        payload = data[pos : pos + size]
        if len(payload) != size:
            raise ValueError(f"string payload truncated at 0x{pos:X}")
        return Entry(type_id, index, a, b, size, None, payload), pos + size
    word = struct.unpack_from("<I", data, pos)[0]
    pos += 4
    payload = data[pos : pos + size]
    if len(payload) != size:
        raise ValueError(f"payload truncated at 0x{pos:X}")
    return Entry(type_id, index, a, b, size, word, payload), pos + size

def read_property(data: bytes, pos: int) -> tuple[Property, int]:
    """Read one property — its type, its index, and its payload."""
    tag_length = struct.unpack_from("<H", data, pos)[0]
    if not 2 <= tag_length <= 8:
        raise ValueError(f"implausible tag length {tag_length} at 0x{pos:X}")
    raw = data[pos + 2 : pos + 2 + tag_length]
    if len(raw) != tag_length or not TAG_CHARS.issuperset(raw):
        raise ValueError(f"implausible tag {raw!r} at 0x{pos:X}")
    pos += 2 + tag_length
    unknown, count = struct.unpack_from("<II", data, pos)
    if count > 64:
        raise ValueError(f"implausible entry count {count} at 0x{pos:X}")
    pos += 8
    entries = []
    for _ in range(count):
        entry, pos = read_entry(data, pos)
        entries.append(entry)
    return Property(raw.decode("ascii"), unknown, entries), pos

def read_class_block(data: bytes, pos: int) -> tuple[ClassBlock, int]:
    """Read one record and its properties into named fields."""
    if data[pos : pos + 4] != CLASS_SIGNATURE:
        raise ValueError(f"expected {CLASS_SIGNATURE!r} at 0x{pos:X}")
    count, name_length = struct.unpack_from("<II", data, pos + 4)
    if count > 4096 or name_length > 256:
        raise ValueError(f"implausible class header at 0x{pos:X}")
    pos += 12
    raw = data[pos : pos + name_length]
    if len(raw) != name_length or not TAG_CHARS.issuperset(raw):
        raise ValueError(f"implausible class name {raw!r} at 0x{pos:X}")
    pos += name_length
    properties = []
    for _ in range(count):
        prop, pos = read_property(data, pos)
        properties.append(prop)
    return ClassBlock(raw.decode("ascii"), properties), pos
