# GENERATED — do not edit by hand. This file is produced by KlikBack's
# sync tooling; changes belong in the source it is generated from.
#
# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""The MMF 1.5 project file as a sequence of named regions.

One level up from reading individual records: this decomposes a whole project
into the spans it is made of — banks, frame bodies, object lists, the editor's
own tail — and puts them back together again.

That decomposition is what makes assembling a project safe. Adding an object
means growing a list, and growing a list means knowing where the list starts,
where it ends and what its count says. With the file described this way a
change is a *span replacement*; without it, a change is an offset into a byte
string and a hope. Regions reassemble byte-for-byte, so anything left
untouched is provably untouched.

A length that disagrees with the data raises rather than being worked around.
A container that does not decompose cleanly is exactly the case where
carrying on produces a project that opens and is wrong.
"""

from __future__ import annotations
import struct
from dataclasses import dataclass
from klikback.core.mmf15.cca import CLASS_SIGNATURE, read_class_block, read_header

HEADER_SIZE = 14

FONT_BANK = b"ATNF"

SAMPLE_BANK = b"APMS"

MUSIC_BANK = b"ASUM"

IMAGE_BANK = b"AGMI"

FRAME_LIST = b"FrmL"

FRAME = b"Fram"

PALETTE = b"Pltt"

PROP = b"PROP"

OBJECT_LIST = b"class cHandleItemList<class LFrameItem>"

INSTANCE_LIST = b"class cHandleItemList<class LFrameItemInstance>"

FONT_DESCRIPTOR_SIZE = 104

AUDIO_RECORD_OVERHEAD = 22

EXTENSION_SIGNATURE = 0x59082516

EXTENSION_LIST_COLOR_DEPTHS = frozenset({3, 4, 6})

class ContainerProblem(Exception):
    """Raised when the file's own tables contradict its contents."""

@dataclass
class Span:
    """One named region: what it is, where it starts, how far it runs."""

    name: str
    start: int
    end: int

    def __len__(self) -> int:
        """How many bytes the region covers."""
        return self.end - self.start

def counted_string(data: bytes, pos: int, expected: bytes) -> int:
    """Read a length-prefixed string, checking it is the string expected."""
    (length,) = struct.unpack_from("<I", data, pos)
    if length != len(expected):
        raise ContainerProblem(
            f"expected a {len(expected)}-byte marker at 0x{pos:X}, found {length}"
        )
    found = data[pos + 4:pos + 4 + length]
    if found != expected:
        raise ContainerProblem(f"expected {expected!r} at 0x{pos:X}, found {found!r}")
    return pos + 4 + length

def agmi_end(data: bytes, pos: int) -> int:
    """Where an image bank ends."""
    if data[pos:pos + 4] != IMAGE_BANK:
        raise ContainerProblem(f"expected {IMAGE_BANK!r} at 0x{pos:X}")
    cursor = pos + 4 + 4 + 2 + 2 + 256 * 4
    (count,) = struct.unpack_from("<I", data, cursor)
    cursor += 4
    for index in range(count):
        cursor += 4
        if cursor + 24 > len(data):
            raise ContainerProblem(f"image {index} header runs past the file")
        (rle_length,) = struct.unpack_from("<I", data, cursor + 6)
        cursor += 24 + rle_length
    return cursor

def simple_bank_end(data: bytes, pos: int, tag: bytes) -> int:
    """Where a bank of the simpler kind — sounds, music, fonts — ends."""
    if data[pos:pos + 4] != tag:
        raise ContainerProblem(f"expected {tag!r} at 0x{pos:X}")
    (count,) = struct.unpack_from("<I", data, pos + 4)
    cursor = pos + 8
    if not count:
        return cursor
    if tag == FONT_BANK:
        return cursor + count * (4 + FONT_DESCRIPTOR_SIZE)
    for record in range(count):
        cursor += 4
        (payload,) = struct.unpack_from("<I", data, cursor + 6)
        cursor += AUDIO_RECORD_OVERHEAD + payload
        if cursor > len(data):
            raise ContainerProblem(
                f"{tag.decode()} record {record} runs past the file"
            )
    return cursor

def extension_list_end(data: bytes, pos: int) -> int:
    """Where the list of extension modules ends."""
    (depth, count) = struct.unpack_from("<II", data, pos)
    if depth not in EXTENSION_LIST_COLOR_DEPTHS:
        raise ContainerProblem(
            f"extension list at 0x{pos:X} opens with colour depth {depth}, "
            f"not one of {sorted(EXTENSION_LIST_COLOR_DEPTHS)}"
        )
    cursor = pos + 8
    for module in range(count):
        cursor += 4
        for _field in range(2):
            (length,) = struct.unpack_from("<I", data, cursor)
            cursor += 4 + length
        (signature,) = struct.unpack_from("<I", data, cursor)
        if signature != EXTENSION_SIGNATURE:
            raise ContainerProblem(
                f"module {module} signature is 0x{signature:08X}, "
                f"not 0x{EXTENSION_SIGNATURE:08X}"
            )
        cursor += 8
        if cursor > len(data):
            raise ContainerProblem(f"extension module {module} runs past the file")
    return cursor

def prop_index_end(data: bytes, pos: int) -> int:
    """Where a property descriptor table ends."""
    (one,) = struct.unpack_from("<I", data, pos)
    if one != 1:
        raise ContainerProblem(f"PROP index at 0x{pos:X} opens with {one}, not 1")
    (count,) = struct.unpack_from("<H", data, pos + 4)
    cursor = pos + 6
    if data[cursor:cursor + 5] != b"\x01\x00\x50\x00\x00":
        raise ContainerProblem(f"PROP marker prefix is wrong at 0x{cursor:X}")
    cursor += 5
    if data[cursor:cursor + 4] != PROP:
        raise ContainerProblem(f"expected {PROP!r} at 0x{cursor:X}")
    cursor += 4
    for entry in range(count):
        (zero, tag_length) = struct.unpack_from("<HH", data, cursor)
        if zero:
            raise ContainerProblem(f"PROP entry {entry} opens with {zero}, not 0")
        cursor += 4 + tag_length
        (name_length,) = struct.unpack_from("<H", data, cursor)
        cursor += 2 + name_length + 4
        if cursor > len(data):
            raise ContainerProblem(f"PROP entry {entry} runs past the file")
    return cursor

def class_block_end(data: bytes, pos: int) -> int:
    """Where one class block ends, by reading its own length rather than scanning.
    """
    block, end = read_class_block(data, pos)
    packed = block.pack()
    if packed != data[pos:end]:
        raise ContainerProblem(
            f"class block {block.name} at 0x{pos:X} does not repack "
            f"byte-identically ({len(packed)} vs {end - pos} bytes)"
        )
    return end

def spans(data: bytes) -> list[Span]:
    """Decompose a project file into its named regions, in order.

    The regions come out in the order the file stores them: a fixed header, then
    the font, sound and music banks, then two image banks, then the application's
    own class block and the table describing its properties, then the list of
    extension modules the project uses. After that comes the frame list, and each
    frame contributes a run of its own regions — its header, its class block and
    property table, its handle, its palette, and then the lists of objects,
    placements and events inside it.

    The walk is a reader and a check at the same time. Every region's end is
    found by reading the file's own lengths and markers rather than by scanning
    for something that looks right, and a length that disagrees with what
    follows stops the walk instead of being stepped over. A project that does not
    decompose cleanly is exactly the case where carrying on would produce a file
    that opens and is quietly wrong.

    The last region is the editor's own saved state — the path the project was
    saved from and the window layout it was last showing. It looks like a region
    worth ignoring and is not: the layout names the frame the editor had open, by
    that frame's identity in the file. Carrying one project's tail into another
    is how a rebuild ends up asking the editor to reopen a frame that is not
    there.
    """
    read_header(data)
    out = [Span("header", 0, HEADER_SIZE)]
    pos = HEADER_SIZE

    for tag in (FONT_BANK, SAMPLE_BANK, MUSIC_BANK):
        end = simple_bank_end(data, pos, tag)
        out.append(Span(tag.decode(), pos, end))
        pos = end
    for bank in (1, 2):
        end = agmi_end(data, pos)
        out.append(Span(f"AGMI-{bank}", pos, end))
        pos = end

    if data[pos:pos + 8] != bytes(8):
        raise ContainerProblem(
            f"expected 8 zero bytes after the image banks at 0x{pos:X}, "
            f"found {data[pos:pos + 8].hex(' ')}"
        )
    out.append(Span("post-banks", pos, pos + 8))
    pos += 8

    end = class_block_end(data, pos)
    out.append(Span("LApplication", pos, end))
    pos = end
    end = prop_index_end(data, pos)
    out.append(Span("LApplication-PROP", pos, end))
    pos = end
    end = extension_list_end(data, pos)
    out.append(Span("extensions", pos, end))
    pos = end

    if data[pos:pos + 4] != FRAME_LIST:
        raise ContainerProblem(f"expected {FRAME_LIST!r} at 0x{pos:X}")
    (frame_count,) = struct.unpack_from("<I", data, pos + 4)
    out.append(Span("FrmL", pos, pos + 8))
    pos += 8

    for frame in range(frame_count):
        if data[pos:pos + 4] != FRAME:
            raise ContainerProblem(f"expected {FRAME!r} for frame {frame} at 0x{pos:X}")
        out.append(Span(f"frame{frame}-Fram", pos, pos + 12))
        pos += 12
        end = class_block_end(data, pos)
        out.append(Span(f"frame{frame}-LFrame", pos, end))
        pos = end
        end = prop_index_end(data, pos)
        out.append(Span(f"frame{frame}-PROP", pos, end))
        pos = end

        out.append(Span(f"frame{frame}-handle", pos, pos + 4))
        pos += 4
        if data[pos:pos + 4] != PALETTE:
            raise ContainerProblem(f"expected {PALETTE!r} at 0x{pos:X}")
        out.append(Span(f"frame{frame}-Pltt", pos, pos + 4 + 1028))
        pos += 4 + 1028
        pos = frame_lists(data, pos, frame, out)

    out.append(Span("editor-state", pos, len(data)))
    return out

def frame_lists(data: bytes, pos: int, frame: int, out: list[Span]) -> int:
    """The lists inside one frame — its objects, placements and events."""
    start = pos
    pos = counted_string(data, pos, OBJECT_LIST)
    (object_count,) = struct.unpack_from("<I", data, pos)
    pos += 4
    for index in range(object_count):
        record_start = pos
        pos = object_record_head(data, pos)
        pos = class_block_end(data, pos)
        pos = object_record_tail(data, pos, index == object_count - 1)
        out.append(Span(f"frame{frame}-object{index}", record_start, pos))
    out.insert(
        len(out) - object_count,
        Span(f"frame{frame}-objects", start, start + 4 + len(OBJECT_LIST) + 4),
    )

    start = pos
    pos = counted_string(data, pos, INSTANCE_LIST)
    (instance_count,) = struct.unpack_from("<I", data, pos)
    pos += 4
    out.append(Span(f"frame{frame}-instances", start, pos))

    end = next_frame_start(data, pos)
    out.append(Span(f"frame{frame}-body", pos, end))
    return end

OBJECT_RECORD_NAME_MAX = 256

def plausible_object_record_name(data: bytes, pos: int) -> bool:
    """Whether the bytes at this position really look like an object record.

    The walk over a project's regions has to know where one object record ends
    and the next begins, and the only marker is a name length followed by the
    name. Checking that the name is a sane length and readable text is what stops
    a misread from being followed off the end of the file into nonsense.
    """
    (length,) = struct.unpack_from("<I", data, pos + 8)
    if length == 0:
        return True
    if length > OBJECT_RECORD_NAME_MAX:
        return False
    name = data[pos + 12:pos + 12 + length]
    return len(name) == length and all(0x20 <= byte < 0x7F for byte in name)

def object_record_head(data: bytes, pos: int) -> int:
    """Where one object's record begins, and what its head says."""
    (name_length,) = struct.unpack_from("<I", data, pos + 8)
    if name_length > OBJECT_RECORD_NAME_MAX:
        raise ContainerProblem(
            f"implausible object record name length {name_length} at "
            f"0x{pos + 8:X}"
        )
    return pos + 12 + name_length

def object_record_tail(data: bytes, pos: int, last: bool) -> int:
    """Where one object's record ends."""
    pos = prop_index_end(data, pos)
    if last:
        return find_marker(data, pos, INSTANCE_LIST)
    cursor = pos
    zero4 = bytes(4)

    while cursor + 16 <= len(data):
        if (
            data[cursor + 4:cursor + 8] == zero4
            and plausible_object_record_name(data, cursor)
        ):
            head = object_record_head(data, cursor)
            if data[head:head + 4] != CLASS_SIGNATURE:
                cursor += 1
                continue
            try:
                read_class_block(data, head)
            except (
                ValueError,
                ContainerProblem,
                struct.error,
                UnicodeDecodeError,
            ):
                cursor += 1
                continue
            return cursor
        cursor += 1
    raise ContainerProblem(f"no object record follows 0x{pos:X}")

def find_marker(data: bytes, pos: int, marker: bytes) -> int:
    """Locate the next occurrence of a known marker from a position."""
    found = data.find(marker, pos)
    while found >= 4:
        if struct.unpack_from("<I", data, found - 4)[0] == len(marker):
            return found - 4
        found = data.find(marker, found + 1)
    raise ContainerProblem(f"no {marker[:24]!r}... marker after 0x{pos:X}")

def next_frame_start(data: bytes, pos: int) -> int:
    """Where the following frame begins."""
    cursor = pos
    while True:
        cursor = data.find(FRAME, cursor)
        if cursor < 0:
            break
        try:
            read_class_block(data, cursor + 12)
        except (ValueError, struct.error, UnicodeDecodeError):
            cursor += 4
            continue
        return cursor
    return editor_state_start(data, pos)

def editor_state_start(data: bytes, pos: int) -> int:
    """Where the editor-only records at the end of a project begin."""
    cursor = pos
    while cursor + 8 <= len(data):
        (length,) = struct.unpack_from("<I", data, cursor)
        if 4 <= length <= 512 and cursor + 4 + length <= len(data):
            text = data[cursor + 4:cursor + 4 + length]
            if text[1:3] == b":\\" and text[:1].isalpha():
                return cursor
        cursor += 1
    raise ContainerProblem("no editor source path found after the last frame")
