# GENERATED — do not edit by hand. This file is produced by KlikBack's
# sync tooling; changes belong in the source it is generated from.
#
# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""Reader for the 1996 Clickteam game file: TGF `.gam` and CnC/MMF-Express `.cca`.

This reads the *container* of a Klik & Play-descended game file as written by
The Games Factory 1.x, Click & Create 1.x and Multimedia Fusion Express 1.x.
It is deliberately independent of the MMF 1.0 and 1.5 readers: that family
handles the later chunked format, which shares almost nothing with this one
but a vendor.

The file is a table of segments, each holding one kind of thing — the level
list, the object definitions, the event program, the banks of images and
sounds. Everything here is read from the file's own tables; a length that
disagrees with the data is reported rather than worked around, because a
container that does not decompose cleanly is exactly the case where guessing
produces a project that opens and is wrong.
"""

from __future__ import annotations
import struct
from dataclasses import dataclass, field
from pathlib import Path

UNPROTECTED_SIGNATURES = (b"GAME", b"GAPP")

PROTECTED_SIGNATURES = (b"PAME", b"PAPP")

FAMILY = {b"GAME": "cnc", b"PAME": "cnc", b"GAPP": "tgf", b"PAPP": "tgf"}

OFF_VERSION = 0x04

FORMAT_VERSION = 0x0207

OFF_NAME = 0x06

OFF_AUTHOR = 0x56

OFF_COLOR_MODE = 0xF6

OFF_FIRST_NON_GAME_SEGMENT = 0x158

OFF_LEVEL_COUNT = 0x15C

OFF_TOC_LENGTH = 0x162

OFF_LEVEL_TABLE = 0x166

SEGMENT_NAMES = {
    0x00: "level-address-table",
    0x01: "game-icon",
    0x02: "preview-bitmap",
    0x03: "global-events",
    0x04: "extension-list",
    0x05: "game-palette",
    0x06: "global-objects",
    0x07: "level-numbers",
    0x08: "level-data",
    0x09: "file-menu",
    0x0A: "image-bank",
    0x0B: "font-bank",
    0x0C: "music-bank",
    0x0D: "sound-bank",
}

SEGMENT_LAST = 0x8000

class NotAGameFile(ValueError):
    """Raised when the bytes are not a 1996 Clickteam game file at all."""

class ContainerProblem(ValueError):
    """Raised when the container's own tables contradict its contents.

    Reported rather than repaired: a file whose lengths do not add up cannot be
    read confidently, and reading it anyway produces a project that looks fine
    and is not.
    """

class TruncatedFile(ContainerProblem):

    def __init__(self, message: str, *, ident: int, offset: int,
                 declared: int, present: int) -> None:
        super().__init__(message)
        self.ident = ident
        self.offset = offset
        self.declared = declared
        self.present = present

class BankProblem(ValueError):
    """Raised when a bank of images or sounds does not walk cleanly to its end.
    """

BANK_SEGMENTS = {0x0A: "image", 0x0B: "font", 0x0C: "music", 0x0D: "sound"}

def walk_bank(data: bytes) -> list[tuple[int, int, int]]:
    """Step through one bank's entries — the images or sounds it holds."""
    if len(data) < 4:
        raise BankProblem(f"a {len(data)}-byte bank has no count")
    (count,) = struct.unpack_from("<I", data, 0)
    table_end = 4 + 8 * count
    if table_end > len(data):
        raise BankProblem(
            f"a table of {count} needs {table_end} bytes, the bank has "
            f"{len(data)}")
    out: list[tuple[int, int, int]] = []
    for slot in range(count):
        offset, size = struct.unpack_from("<II", data, 4 + 8 * slot)
        if not offset:
            continue
        if offset < table_end:
            raise BankProblem(
                f"asset {slot} at {offset} is inside the {table_end}-byte table")
        if offset + size > len(data):
            raise BankProblem(
                f"asset {slot} at {offset} + {size} runs "
                f"{offset + size - len(data)} bytes past the {len(data)}-byte "
                f"bank -- the bank is TRUNCATED, and the segment chain around "
                f"it tiles perfectly")
        out.append((slot, offset, size))
    return out

@dataclass
class Segment:
    """One top-level segment: which kind it is, where it starts, how long it runs.
    """
    offset: int
    ident: int
    last: bool
    data: bytes

    missing: int = 0

    @property
    def name(self) -> str:
        """What kind of segment this is, in words rather than a number."""
        return SEGMENT_NAMES.get(self.ident, f"unknown-{self.ident:04X}")

@dataclass
class GameFile:
    """One parsed 1996 game: what it is, what it contains, and where each part sits.

    A whole game file held open for reading: its signature and version, its
    levels, and every numbered segment the file is made of, each remembering
    where it sits in the original bytes. The raw bytes are kept alongside, because
    rebuilding is a matter of replacing named regions and copying the rest through
    untouched — a reader that only returned parsed values could not do that.

    The signature is what says whether the file is protected and which member of
    the 1996 family it belongs to, so both are read from it rather than tracked
    separately. Everything else is a small accessor over the same data: fetch a
    segment by its id, list the levels, read one of the fixed text fields such as
    the game's name or its author.
    """
    path: Path | None
    raw: bytes
    signature: bytes
    version: int
    level_count: int
    level_addresses: list[int]
    segments: list[Segment] = field(default_factory=list)

    @property
    def protected(self) -> bool:
        """Whether the file is the protected form, which cannot be opened by the editor.
        """
        return self.signature in PROTECTED_SIGNATURES

    @property
    def family(self) -> str:
        """Which product made this file: The Games Factory, or Click & Create.
        """
        return FAMILY[self.signature]

    def segment(self, ident: int) -> Segment | None:
        """The one segment of a given kind, if the file has it."""
        for seg in self.segments:
            if seg.ident == ident:
                return seg
        return None

    def levels(self) -> list[Segment]:
        """Every level in the game, in the order the file stores them."""
        return [s for s in self.segments if s.ident == 0x08]

    def text(self, offset: int, length: int = 0x4E) -> str:
        """Read one of the file's fixed-position text fields."""
        return self.raw[offset:offset + length].split(b"\0")[0].decode("latin-1")

    @property
    def name(self) -> str:
        """The name the game gives itself."""
        return self.text(OFF_NAME)

    @property
    def author(self) -> str:
        """The author the game names."""
        return self.text(OFF_AUTHOR)

def read(data: bytes | Path, *, path: Path | None = None,
         clip_truncated: bool = False) -> GameFile:
    """Parse a game file into its segments, levels and objects."""
    if isinstance(data, Path):
        path, data = data, data.read_bytes()
    signature = data[:4]
    if signature not in UNPROTECTED_SIGNATURES + PROTECTED_SIGNATURES:
        raise NotAGameFile(
            f"expected one of GAME/PAME/GAPP/PAPP, found {signature!r}"
        )
    if len(data) < OFF_LEVEL_TABLE:
        raise ContainerProblem(f"{len(data)} bytes is shorter than the header")

    version = struct.unpack_from("<H", data, OFF_VERSION)[0]
    if version != FORMAT_VERSION:

        raise ContainerProblem(
            f"version 0x{version:04X} is not the 0x{FORMAT_VERSION:04X} this "
            f"reader parses (0x0126 is Klik & Play, an earlier product)"
        )
    level_count = struct.unpack_from("<H", data, OFF_LEVEL_COUNT)[0]
    table_end = OFF_LEVEL_TABLE + 4 * level_count
    if table_end > len(data):
        raise ContainerProblem(
            f"level address table for {level_count} levels overruns the file"
        )
    addresses = list(
        struct.unpack_from(f"<{level_count}I", data, OFF_LEVEL_TABLE)
    ) if level_count else []

    game = GameFile(path, data, signature, version, level_count, addresses)
    game.segments = walk_segments(data, table_end,
                                  clip_truncated=clip_truncated)
    return game

def walk_segments(data: bytes, start: int, *,
                  clip_truncated: bool = False) -> list[Segment]:
    """Step through the file's top-level segments in order."""
    segments: list[Segment] = []
    offset = start
    while True:
        if offset + 6 > len(data):
            raise ContainerProblem(
                f"segment header at {offset} runs past the end of {len(data)} bytes"
            )
        ident, length = struct.unpack_from("<HI", data, offset)
        last = bool(ident & SEGMENT_LAST)
        ident &= ~SEGMENT_LAST
        end = offset + 6 + length
        if end > len(data):

            short = len(data) - offset - 6
            if last:
                if clip_truncated:
                    segments.append(Segment(offset, ident, True,
                                            data[offset + 6:],
                                            missing=length - short))
                    return segments
                raise TruncatedFile(
                    f"TRUNCATED FILE: the final segment {ident:04X} "
                    f"({SEGMENT_NAMES.get(ident, 'unknown')}) at {offset} "
                    f"declares {length} bytes and only {short} are present "
                    f"({100 * short / length:.1f} %). Every earlier segment "
                    f"tiled exactly, so the container is well-formed and the "
                    f"file is incomplete -- this is a damaged copy, not a "
                    f"format this reader cannot parse",
                    ident=ident, offset=offset, declared=length, present=short,
                )
            raise ContainerProblem(
                f"segment {ident:04X} at {offset} declares {length} bytes, "
                f"which overruns the file by {end - len(data)}"
            )
        segments.append(Segment(offset, ident, last, data[offset + 6:end]))
        offset = end
        if last:
            break
    if offset != len(data):
        raise ContainerProblem(
            f"segment walk ended at {offset} with {len(data) - offset} bytes left over"
        )
    return segments

LEVEL_BLOCK_NAMES = {
    0x00: "level-palette",
    0x01: "level-preview",
    0x02: "object-definitions",
    0x03: "object-placement",
    0x04: "level-events",
    0x05: "music-playlist",
    0x06: "file-path",
    0x07: "embedded-picani",
}

LEVEL_BLOCK_LAST = 0x8000

LEVEL_BLOCKS_AT = 0xB8

LEVEL_BLOCKS_AT_STRIPPED = 0x78

LEVEL_TRANSITION_NAMES_LENGTH = LEVEL_BLOCKS_AT - LEVEL_BLOCKS_AT_STRIPPED

@dataclass
class LevelBlock:
    """One block inside a level, identified by kind."""
    offset: int
    ident: int
    last: bool
    data: bytes

    @property
    def name(self) -> str:
        """What kind of block this is, in words rather than a number."""
        return LEVEL_BLOCK_NAMES.get(self.ident, f"unknown-{self.ident:04X}")

def _try_blocks(level: bytes, start: int) -> list[LevelBlock] | None:
    blocks: list[LevelBlock] = []
    offset = start
    while offset + 6 <= len(level):
        ident, length = struct.unpack_from("<HI", level, offset)
        last = bool(ident & LEVEL_BLOCK_LAST)
        ident &= ~LEVEL_BLOCK_LAST
        end = offset + 6 + length
        if ident not in LEVEL_BLOCK_NAMES or end > len(level):
            return None
        blocks.append(LevelBlock(offset, ident, last, level[offset + 6:end]))
        offset = end
        if last:
            return blocks if offset == len(level) else None
    return None

def level_blocks(level: bytes) -> tuple[int, list[LevelBlock]]:
    """The blocks that make up one level, by kind."""
    for start in (LEVEL_BLOCKS_AT, LEVEL_BLOCKS_AT_STRIPPED):
        blocks = _try_blocks(level, start)
        if blocks is not None:
            return start, blocks
    raise ContainerProblem(
        f"no block walk tiles this {len(level)}-byte level from "
        f"0x{LEVEL_BLOCKS_AT:02X} or 0x{LEVEL_BLOCKS_AT_STRIPPED:02X}"
    )

OBJECT_RECORD_HEAD = 0x44

OFF_OBJECT_NAME = 0x00

OFF_OBJECT_TYPE = 0x2A

OFF_OBJECT_FLAGS = 0x26

OFF_OBJECT_FIRST_BLOCK = 0x40

OBJECT_GLOBAL = 0x80

OBJECT_DELETED = 0xFF

OBJECT_TYPE_NAMES = {
    0x00: "quick-backdrop",
    0x01: "backdrop",
    0x02: "active",
    0x03: "text",
    0x04: "question",
    0x05: "score",
    0x06: "lives",
    0x07: "counter",
    0xFF: "deleted",
}

OBJECT_DATA_BLOCK_LAST = 0x8000

OBJECT_DATA_BLOCK_NAMES = {0x00: "object-data", 0x02: "object-icon"}

@dataclass
class ObjectDataBlock:
    """One block inside an object definition, identified by kind."""
    offset: int
    ident: int
    last: bool
    data: bytes

    @property
    def name(self) -> str:
        """What kind of block this is, in words rather than a number."""
        return OBJECT_DATA_BLOCK_NAMES.get(self.ident, f"unknown-{self.ident:04X}")

@dataclass
class ObjectDefinition:
    """One object's definition: what type it is, what it is called, how it is used.
    """
    index: int

    offset: int

    name: str
    object_type: int
    first_block_pointer: int
    blocks: list[ObjectDataBlock]
    flags: int = 0

    base: int = 0

    @property
    def type_name(self) -> str:
        """The object's type in words — or, for anything outside the built-in set, the
        number, because a 1996 extension object is only identified by it.
        """
        return OBJECT_TYPE_NAMES.get(self.object_type, f"extension-{self.object_type:02X}")

    @property
    def is_global(self) -> bool:
        """Whether the object is shared across levels rather than owned by one.
        """
        return bool(self.flags & OBJECT_GLOBAL)

    @property
    def deleted(self) -> bool:
        """Whether the slot holds an object the author deleted.

        A deleted object leaves its slot behind, because everything after it is
        addressed by position. The slot is carried across as the empty thing it is.
        """
        return self.object_type == OBJECT_DELETED

def object_definitions(block: bytes, *,
                       globals_have_blocks: bool = False,
                       ) -> list[ObjectDefinition]:
    """Every object the game defines, with its type, name and flags.

    Each record is a fixed head — name, type, flags — optionally followed by a
    chain of data blocks holding the object's own content. The whole difficulty is
    knowing which records have a chain, because the head does not carry a length
    covering it.

    It is **read from the record**, never inferred from the bytes that follow. A
    deleted object never has a chain. An object shared between levels has exactly
    one copy of its content, stored with the global list rather than in the level,
    so it has a chain in one place and none in the other — and the caller says
    which place is being read.

    The reason for that rule is worth keeping. An earlier version decided by
    peeking at the next two bytes and asking whether they looked like a block
    header. A record head starts with the object's name, so an object with an
    empty name starts with the same two bytes a block header does, and files with
    such an object became unreadable while everything else in reach kept working.
    A test that happens to fit everything tried so far is not a rule.

    Lengths are checked as the walk goes, and a chain that overruns its block, or
    a block id that is not a block id, stops the read by name.
    """
    if len(block) < 4:
        return []
    count = struct.unpack_from("<H", block, 0)[0]
    objects: list[ObjectDefinition] = []
    offset = 4
    for index in range(count):
        if offset + OBJECT_RECORD_HEAD > len(block):
            raise ContainerProblem(
                f"object {index} of {count} needs {OBJECT_RECORD_HEAD} bytes at "
                f"{offset} but the block is {len(block)}"
            )
        base = offset
        head = block[offset:offset + OBJECT_RECORD_HEAD]
        name = head[OFF_OBJECT_NAME:OFF_OBJECT_NAME + 0x16].split(b"\0")[0].decode("latin-1")
        object_type = head[OFF_OBJECT_TYPE]
        flags = head[OFF_OBJECT_FLAGS]
        pointer = struct.unpack_from("<I", head, OFF_OBJECT_FIRST_BLOCK)[0]
        offset += OBJECT_RECORD_HEAD
        blocks: list[ObjectDataBlock] = []
        has_chain = object_type != OBJECT_DELETED and (
            globals_have_blocks or not flags & OBJECT_GLOBAL
        )
        while has_chain:
            if offset + 6 > len(block):
                raise ContainerProblem(
                    f"object {index} of {count} declares a data-block chain that "
                    f"needs 6 bytes at {offset} but the block is {len(block)}"
                )
            ident, length = struct.unpack_from("<HI", block, offset)
            last = bool(ident & OBJECT_DATA_BLOCK_LAST)
            ident &= ~OBJECT_DATA_BLOCK_LAST
            if ident not in OBJECT_DATA_BLOCK_NAMES:
                raise ContainerProblem(
                    f"object {index} of {count} should carry a data-block chain "
                    f"but {ident:04X} at {offset} is not a data-block id"
                )
            end = offset + 6 + length
            if end > len(block):
                raise ContainerProblem(
                    f"object {index} data block {ident:04X} overruns the block"
                )
            blocks.append(ObjectDataBlock(offset, ident, last, block[offset + 6:end]))
            offset = end
            if last:
                break
        objects.append(
            ObjectDefinition(index, offset, name, object_type, pointer, blocks,
                             flags, base)
        )
    return objects

EVENT_HEADER_SIGNATURE = b"Fra\0"

def event_header(block: bytes) -> tuple[bytes, int] | None:
    """The event program's header, which says how the rest is shaped."""
    if block[:4] == EVENT_HEADER_SIGNATURE:
        return EVENT_HEADER_SIGNATURE, struct.unpack_from("<H", block, 4)[0]
    return None

def event_groups(block1: bytes) -> list[tuple[int, int]]:
    """The event program, split into the groups the editor shows as pages."""
    groups: list[tuple[int, int]] = []
    offset = 0
    while offset + 2 <= len(block1):
        (size,) = struct.unpack_from("<h", block1, offset)
        if size == 0:
            return groups
        size = abs(size)
        if size < 4 or offset + size > len(block1):
            return groups
        groups.append((offset, size))
        offset += size
    return groups
