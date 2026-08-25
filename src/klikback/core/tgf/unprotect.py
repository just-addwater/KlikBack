# GENERATED — do not edit by hand. This file is produced by KlikBack's
# sync tooling; changes belong in the source it is generated from.
#
# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""Turn a protected 1996-era Clickteam file back into one an editor will open.

Protection here is not encryption and not compression: it is *subtractive*.
The exporter wrote the same file with named spans deleted and a handful of
pointers rewritten. Undoing it is therefore mostly bookkeeping — put the
signature back, restore the shapes the editor itself writes, and repoint the
tables — and the honest part of the job is saying what cannot come back.

What is genuinely gone is **artwork**: the two preview thumbnails, one icon
per object, and one per global object. Nothing in the file still holds those
pixels, so no amount of decoding recovers them. The gaps are filled with
replacements that keep the project openable, and every one of them is
reported as a loss rather than passed off as the original.

Everything else is restored to a shape the editor accepts, which is why a
successfully unprotected file opens and edits normally even though it is not
byte-for-byte the author's own.
"""

from __future__ import annotations
import argparse
import struct
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
import klikback.core.tgf.bank_repair as tgf_bank_repair
import klikback.core.tgf.block3 as tgf_block3
import klikback.core.tgf.extract_extensions as extensions
import klikback.core.tgf.format as tgf
import klikback.core.tgf.icon_generate as icon_gen
import klikback.core.tgf.image as tgf_img

UNPROTECT_SIGNATURE = {b"PAME": b"GAME", b"PAPP": b"GAPP"}

GAME_PREVIEW_SIZE = (128, 96)

LEVEL_PREVIEW_SIZE = (64, 48)

OBJECT_ICON_SIZE = (30, 30)

EVENT_HEADER_VERSION = 0x0217

GAME_ICON_LENGTH = 800

EMPTY_EVENT_BLOCK_3 = b"\0" * 10

class CannotUnprotect(ValueError):
    """Raised when the file is not protected, or is protected in a way not measured.

    Refusing is the correct outcome here. A file whose protection does not match
    what this understands would be guessed at rather than restored, and a guess
    that opens is worse than a refusal that explains itself.
    """

@dataclass
class Report:
    """What was restored, what was replaced, and what was lost outright."""
    path: Path
    family: str
    recovered: list[str] = field(default_factory=list)
    substituted: list[str] = field(default_factory=list)
    losses: list[str] = field(default_factory=list)

    def line(self, bucket: list[str], text: str) -> None:
        """Add one line to the recovered, substituted or lost list."""
        bucket.append(text)

    def render(self) -> str:
        """The report as text, grouped so a reader can see what each line is claiming.

        Three kinds of line, kept apart on purpose: what came back, what was replaced
        by something of ours, and what is simply gone. Collapsing them would let a
        substitution read as a recovery.
        """
        out = [f"{self.path.name}: {self.family} protected game file"]
        for label, rows in (
            ("recovered", self.recovered),
            ("substituted", self.substituted),
            ("loss", self.losses),
        ):
            for row in rows:
                out.append(f"  {label}: {row}")
        return "\n".join(out)

def blank_dib(width: int, height: int, colour_depth: int) -> bytes:
    """An empty image of the shape the preview segments carry.

    Used where a thumbnail was removed and nothing in the file can stand in for
    it. The editor wants an image of that shape; this is an honest empty one.
    """
    bits = 8 if colour_depth in (3, 5) else 24
    stride = ((width * bits + 31) // 32) * 4
    pixels = stride * height
    header = struct.pack(
        "<IiiHHIIiiII", 40, width, height, 1, bits, 0, pixels, 0, 0, 0, 0
    )
    palette = b""
    if bits == 8:

        palette = b"".join(
            struct.pack("<BBBB", i, i, i, 0) for i in range(256)
        )
    return header + palette + b"\xff" * pixels

def blank_object_icon(colour_depth: int) -> bytes:
    """A single flat-coloured object icon, for an object with no art to draw from.
    """
    width, height = OBJECT_ICON_SIZE
    colour = 0xFF
    remaining = width * height
    runs = bytearray()
    while remaining:
        take = min(remaining, 0x7F)
        runs += bytes((take, colour))
        remaining -= take
    runs += b"\0"
    header = struct.pack(
        "<HHHIHHBBHHHH",
        0,
        3, 0,
        len(runs),
        width, height,
        colour_depth, 1,
        0, 0, 0, 0,
    )
    return header + bytes(runs)

class IconGenerator:
    """Derive replacement object icons from the game's own image bank.

    The original icons are gone, but the objects' own artwork is not, so a
    stand-in is drawn from the picture the object actually uses. It is a
    substitution and it is reported as one — the point is a project you can
    navigate, not a claim that the author's icons came back.
    """

    def __init__(self, game: tgf.GameFile, colour_depth: int):
        """Gather what the icons can be drawn from: the game's pictures and its palette.
        """
        self.colour_depth = colour_depth
        self.bank: dict[int, bytes] = {}
        seg = game.segment(0x0A)
        if seg is not None:
            try:
                for slot, off, size in tgf.walk_bank(seg.data):
                    self.bank[slot] = seg.data[off:off + size]
            except tgf.BankProblem:
                pass
        pal = game.segment(0x05)
        self.quantise = (icon_gen._Quantiser(icon_gen.read_palette(pal.data))
                         if pal is not None and len(pal.data) >= 1028 else None)
        self.generated = 0
        self.artwork = 0
        self.blank = 0

    def icon_for(self, obj: tgf.ObjectDefinition, head: bytes) -> bytes:
        """Draw one object's icon, from its own picture where there is one.

        The chain is deliberate. An object's own artwork first; a Quick Backdrop's own
        fill pattern next; then this project's own drawing for the object's type; and
        a blank square only when even the palette is missing. Every step after the
        first is a substitution and is counted as one.
        """
        try:
            handle = icon_gen.source_handle(obj, head)
            raw = self.bank.get(handle) if handle is not None else None
            if raw is not None:
                art = tgf_img.parse_record(raw)
                made = icon_gen.icon_from_art(art, self.quantise)
                self.generated += 1
                return made
            if (obj.object_type == 0x00 and self.quantise is not None
                    and len(head) >= 0x21
                    and head[0x20] & 0x0F != icon_gen.QBD_TYPE_MOSAIC):

                made = icon_gen.quick_backdrop_icon(head, self.quantise)
                self.generated += 1
                return made
        except (tgf_img.ImageProblem, ValueError, struct.error):
            pass
        if self.quantise is not None:
            try:
                made = icon_gen.artwork_icon(obj.object_type, self.quantise)
            except (ValueError, OSError):
                made = None
            if made is not None:
                self.artwork += 1
                return made
        self.blank += 1
        return blank_object_icon(self.colour_depth)

    def report_into(self, report: Report) -> None:
        """Say how many icons were drawn, and from what."""
        if self.generated:
            report.line(
                report.substituted,
                f"{self.generated} object icon(s) regenerated from the "
                f"object's own art, as the editor itself does on resave",
            )
        if self.artwork:
            report.line(
                report.substituted,
                f"{self.artwork} object icon(s) drawn from artwork/ -- the "
                f"object has no derivable image",
            )
        if self.blank:
            report.line(
                report.substituted,
                f"{self.blank} object icon(s) replaced with a blank "
                f"{OBJECT_ICON_SIZE[0]}x{OBJECT_ICON_SIZE[1]} square",
            )

def pack_block(ident: int, data: bytes, last: bool = False) -> bytes:
    """Wrap a block in the header the format frames it with."""
    return struct.pack("<HI", ident | (0x8000 if last else 0), len(data)) + data

EVENT_GROUP_FLAGS = 4

EVENT_ROW_IN_GROUP = 0x2000

EVENT_ROW_DRAWN = 0x0200

def unfilter_block1(block1: bytes) -> tuple[bytes, int, int]:
    """Mark every drawable row as drawn, which is the editor's *no filter* view.
    """
    out = bytearray(block1)
    seen = changed = 0
    for offset, size in tgf.event_groups(block1):
        if size < EVENT_GROUP_FLAGS + 2:
            continue
        seen += 1
        (flags,) = struct.unpack_from("<H", out, offset + EVENT_GROUP_FLAGS)
        if flags & EVENT_ROW_IN_GROUP or flags & EVENT_ROW_DRAWN:
            continue
        struct.pack_into("<H", out, offset + EVENT_GROUP_FLAGS,
                         flags | EVENT_ROW_DRAWN)
        changed += 1
    return bytes(out), seen, changed

def restore_events(block: bytes, report: Report,
                   donor_block3: bytes | None = None,
                   unfilter: bool = True,
                   generated_block3: bytes | None = None,
                   level_index: int = 0,
                   comment_placeholder: bool = False,
                   drop_comment_rows: bool = False) -> bytes:
    """Put the event header back and give the emptied block an authored empty shape.

    A level's event section is three blocks. Protection removes the section's
    header outright and empties the third block, which is where the event
    editor keeps its column layout and its comment lines. The header goes back
    first; then what survives is walked, so the third block is *replaced* rather
    than appended to. A declared length that overruns the data stops the rebuild
    instead of being stepped over — past that point nothing else read would mean
    anything.

    The third block can be filled three ways, and the report says plainly which
    one happened rather than blurring them together:

    - **derived** from this level's own objects and events — the normal path, and
      nothing is copied from anywhere;
    - **the authored empty form**, which is honest and loses the column list;
    - **taken from another file**, which is a diagnostic build only. It cannot be
      reached without asking for it, and its own report line says outright that
      the result is not decompiler output. The distinction between a value this
      tool derived and a value it lifted out of a sibling file is the whole
      difference between a decompiler and a copier.

    Comment rows are the awkward case, because the rows survive and the words do
    not. They can be deleted — every damaged row, not a visible subset, since a
    sheet with some of them missing is one nobody can reason about — and that is
    reported as a loss naming what went with them: the row, its position and its
    colour. Rows that stay can be given a single space each, which is reported as
    invented content and never as a recovery: the only reason for it is that the
    editor crashes on a comment record of zero length.
    """
    if tgf.event_header(block):
        report.line(report.recovered, "events block already carries its header")
        return block
    head = tgf.EVENT_HEADER_SIGNATURE + struct.pack("<H", EVENT_HEADER_VERSION)
    report.line(
        report.recovered,
        f"events header {head[:4]!r}+v{EVENT_HEADER_VERSION:04X}",
    )

    if len(block) < 6:
        raise CannotUnprotect(f"events block is {len(block)} bytes, too short to walk")
    block1_length = struct.unpack_from("<I", block, 0)[0]
    cursor = 4 + block1_length
    if cursor + 2 > len(block):
        raise CannotUnprotect(
            f"events block 1 declares {block1_length} bytes, which overruns"
        )
    block2_length = struct.unpack_from("<H", block, cursor)[0]
    cursor += 2 + block2_length
    if cursor > len(block):
        raise CannotUnprotect(
            f"events block 2 declares {block2_length} bytes, which overruns"
        )
    trailing = len(block) - cursor
    if drop_comment_rows:

        trimmed, dropped = tgf_block3.without_comment_rows(
            block[4:4 + block1_length])
        if dropped:
            block = (struct.pack("<I", len(trimmed)) + trimmed
                     + block[4 + block1_length:])
            block1_length = len(trimmed)
            cursor = 4 + block1_length + 2 + block2_length
            trailing = len(block) - cursor
            report.line(
                report.losses,
                f"level {level_index}: {dropped} blank comment row(s) DELETED "
                f"from the event list -- their text was destroyed by protection "
                f"and this discards the row, its position and its colour too",
            )
    if unfilter:
        rebuilt, seen, changed = unfilter_block1(block[4:4 + block1_length])
        if changed:
            block = (block[:4] + rebuilt + block[4 + block1_length:])
            report.line(
                report.recovered,
                f"events block 1: {changed} of {seen} row(s) marked drawn, so "
                f"the sheet's view state matches the unfiltered block 3",
            )
    if donor_block3 is not None:
        report.line(
            report.substituted,
            f"events block 3 taken from a DONOR ({len(donor_block3)} bytes) -- "
            f"DIAGNOSTIC BUILD, not decompiler output",
        )
        return head + block[:cursor] + donor_block3
    if generated_block3 is not None:
        report.line(
            report.recovered,
            f"level {level_index}: events block 3 REGENERATED from this level's "
            f"own objects and events ({trailing} bytes found, "
            f"{len(generated_block3)} written) -- the event editor's column "
            f"list, derived; the comment lines remain a loss",
        )
        if comment_placeholder:

            slots = tgf_block3.walk(generated_block3).comments
            report.line(
                report.substituted,
                f"level {level_index}: {slots.used if slots else 0} comment "
                f"record(s) written as a single space instead of empty -- "
                f"INVENTED CONTENT, and the only reason for it is that The "
                f"Games Factory crashes on a zero-length comment record",
            )
        return head + block[:cursor] + generated_block3
    report.line(
        report.substituted,
        f"events block 3 rebuilt as the authored empty form "
        f"({trailing} bytes found, {len(EMPTY_EVENT_BLOCK_3)} written); "
        f"the event editor's object columns and its comment lines are a "
        f"genuine loss",
    )
    return head + block[:cursor] + EMPTY_EVENT_BLOCK_3

def restore_objects(block: bytes, colour_depth: int, substitute: bool,
                    report: Report, *, globals_have_blocks: bool = False,
                    what: str = "object",
                    icons: IconGenerator | None = None) -> bytes:
    """Refill every object-icon block the exporter emptied in place."""
    objects = tgf.object_definitions(block, globals_have_blocks=globals_have_blocks)
    if not objects:
        return block
    blank = blank_object_icon(colour_depth) if substitute else b""
    out = bytearray(block[:4])
    cursor = 4
    refilled = 0
    for obj in objects:
        head_end = cursor + tgf.OBJECT_RECORD_HEAD
        head = block[cursor:head_end]
        out += head
        cursor = head_end
        for data_block in obj.blocks:
            payload = data_block.data
            if data_block.ident == 0x02 and not payload:
                if not substitute:
                    payload = b""
                elif icons is not None:
                    payload = icons.icon_for(obj, head)
                else:
                    payload = blank
                refilled += 1
            out += pack_block(data_block.ident, payload, data_block.last)
            cursor = data_block.offset + 6 + len(data_block.data)
    out += block[cursor:]
    if refilled:
        if not substitute:
            report.line(report.losses, f"{refilled} {what} icon(s) left empty")
        elif icons is None:
            report.line(
                report.substituted,
                f"{refilled} {what} icon(s) replaced with a blank "
                f"{OBJECT_ICON_SIZE[0]}x{OBJECT_ICON_SIZE[1]} square",
            )
        report.line(report.losses, f"{refilled} {what} icon(s): the authored icon's own pixels are not in the file")
    return bytes(out)

PLACEMENT_UNUSED = 0xFFFFFFFF

def repack_placement_block(data: bytes) -> tuple[bytes, int]:
    if len(data) < 2:
        return data, 0
    (count,) = struct.unpack_from("<H", data, 0)
    if 2 + 4 * count > len(data):
        raise CannotUnprotect(
            f"placement declares {count} slots, the block is {len(data)} bytes")
    pointers = list(struct.unpack_from(f"<{count}I", data, 2))
    live = [i for i, p in enumerate(pointers) if p != PLACEMENT_UNUSED]
    ordered = sorted(pointers[i] for i in live)
    out = bytearray(data)
    moved = 0
    for slot, value in zip(live, ordered):
        if pointers[slot] != value:
            moved += 1
        struct.pack_into("<I", out, 2 + 4 * slot, value)
    if len(out) != len(data):
        raise AssertionError("the repack changed the placement block's length")
    return bytes(out), moved

def restore_level(level: bytes, index: int, colour_depth: int,
                  substitute: bool, report: Report,
                  donor_block3: bytes | None = None,
                  unfilter: bool = True,
                  regenerate_block3: bool = True,
                  comment_placeholder: bool = False,
                  drop_comment_rows: bool = True,
                  icons: IconGenerator | None = None,
                  repack_placement: bool = False) -> bytes:
    """Rebuild one level's removed spans and repoint its tables.

    One level's worth of the work: its objects, its events, its palette, its
    preview picture and its transition names. Protection removes some of these
    outright, so a rebuild has to decide *where* a replacement goes as well as
    what it holds.

    The preview is the one that needs a rule. It sits immediately after the
    palette in every level that has a palette, so that is where a substituted one
    goes. But a level with no palette at all is a real shape rather than a fault
    — a chapter divider that carries almost nothing still carries a preview —
    and keying the insertion on the palette alone dropped the preview from
    exactly those levels, because the block it was waiting to follow never
    arrived. A level with neither gets its preview first instead.

    The transition names are written empty and reported as substituted:
    protection deletes them and nothing left in the file implies what they said.
    The preview's artwork is reported as a loss whether or not a blank stand-in
    is written for it, because a blank rectangle is not the picture that was
    there.
    """
    start, blocks = tgf.level_blocks(level)
    generated_block3 = None
    if regenerate_block3 and donor_block3 is None:

        generated_block3 = tgf_block3.for_level(
            level,
            comment_text=(tgf_block3.COMMENT_PLACEHOLDER if comment_placeholder
                          else b""),
            drop_comment_rows=drop_comment_rows)
    head = level[:start]
    if start == tgf.LEVEL_BLOCKS_AT_STRIPPED:
        head = head + b"\0" * tgf.LEVEL_TRANSITION_NAMES_LENGTH
        report.line(
            report.substituted,
            f"level {index}: {tgf.LEVEL_TRANSITION_NAMES_LENGTH}-byte transition "
            f"name pair, written empty -- the names are deleted by protection "
            f"and are not derivable from anything left in the file",
        )

    rebuilt: list[tuple[int, bytes]] = []
    have_preview = any(b.ident == 0x01 for b in blocks)
    have_palette = any(b.ident == 0x00 for b in blocks)

    def put_preview() -> None:
        if substitute:
            rebuilt.append((0x01, blank_dib(*LEVEL_PREVIEW_SIZE, colour_depth)))
            report.line(
                report.substituted,
                f"level {index}: blank "
                f"{LEVEL_PREVIEW_SIZE[0]}x{LEVEL_PREVIEW_SIZE[1]} preview thumbnail",
            )
        report.line(report.losses, f"level {index}: preview thumbnail artwork")

    if not have_preview and not have_palette:
        put_preview()

    for block in blocks:
        data = block.data
        if block.ident == 0x02:
            data = restore_objects(data, colour_depth, substitute, report,
                                   icons=icons)
        elif block.ident == 0x03 and repack_placement:
            data, moved = repack_placement_block(data)
            if moved:
                report.line(
                    report.substituted,
                    f"level {index}: placement pointers reordered, {moved} of "
                    f"{len(data) // 4} word(s) moved -- the entries and their "
                    f"drawing order are untouched",
                )
        elif block.ident == 0x04:
            data = restore_events(data, report, donor_block3, unfilter,
                                  generated_block3, index, comment_placeholder,
                                  drop_comment_rows)
        rebuilt.append((block.ident, data))
        if block.ident == 0x00 and not have_preview:
            put_preview()

    out = bytearray(head)
    for i, (ident, data) in enumerate(rebuilt):
        out += pack_block(ident, data, last=(i == len(rebuilt) - 1))
    return bytes(out)

def unprotect(game: tgf.GameFile, *, substitute: bool = True,
              donor_block3: Callable[[int], bytes] | None = None,
              unfilter: bool = True,
              regenerate_block3: bool = True,
              comment_placeholder: bool = False,
              drop_comment_rows: bool = True,
              generate_icons: bool = True,
              repair_bank: bool = False,

              repair_object_data: bool = False,

              repack_placement: set[int] | None = None,

              progress: Callable[..., None] | None = None,
              ) -> tuple[bytes, Report]:
    """Undo the protection transform and return the rebuilt bytes with a report.

    The report is the point as much as the bytes are: it names every span that
    was restored and every one that was replaced, so what you have is clear
    before you open it. The optional progress callback is a pure observer,
    called per level and again at layout.
    """
    if not game.protected:
        raise CannotUnprotect(
            f"{game.signature.decode()} is already an unprotected signature"
        )
    report = Report(game.path or Path("<bytes>"), game.family)
    signature = UNPROTECT_SIGNATURE[game.signature]
    report.line(report.recovered, f"signature {game.signature.decode()} -> {signature.decode()}")

    colour_depth = struct.unpack_from("<H", game.raw, tgf.OFF_COLOR_MODE)[0]
    header = bytearray(game.raw[:tgf.OFF_LEVEL_TABLE])
    header[0:4] = signature

    icons = (IconGenerator(game, colour_depth)
             if substitute and generate_icons else None)

    segments: list[tuple[int, bytes]] = []
    present = {s.ident for s in game.segments}
    level_index = 0

    def reinsert_stripped() -> None:
        if 0x01 not in present:

            if substitute:
                segments.append((0x01, bytes(GAME_ICON_LENGTH)))
                report.line(
                    report.substituted,
                    f"blank {GAME_ICON_LENGTH}-byte game icon "
                    f"(CnC 1.00 strips the segment)",
                )
            report.line(report.losses, "game icon artwork")
        if 0x02 not in present:
            if substitute:
                segments.append((0x02, blank_dib(*GAME_PREVIEW_SIZE, colour_depth)))
                report.line(
                    report.substituted,
                    f"blank {GAME_PREVIEW_SIZE[0]}x{GAME_PREVIEW_SIZE[1]} "
                    f"game preview thumbnail",
                )
            report.line(report.losses, "game preview thumbnail artwork")

    anchor = 0x01 if 0x01 in present else (0x07 if 0x07 in present else None)
    if anchor is None:
        reinsert_stripped()
    for segment in game.segments:
        data = segment.data
        if segment.ident == 0x08:
            if progress is not None:
                progress("levels", level_index + 1, game.level_count)
            data = restore_level(data, level_index, colour_depth,
                                 substitute, report,
                                 donor_block3(level_index) if donor_block3 else None,
                                 unfilter, regenerate_block3,
                                 comment_placeholder, drop_comment_rows,
                                 icons=icons,
                                 repack_placement=(
                                     repack_placement is not None
                                     and level_index in repack_placement))
            level_index += 1
        elif segment.ident == 0x0A and data and repair_bank:

            try:
                data, repair_lines = tgf_bank_repair.repair_bank(data)
            except (tgf.BankProblem, tgf_img.ImageProblem) as err:
                report.line(report.losses,
                            f"bank repair refused: {err}")
                repair_lines = []
            for line in repair_lines:
                report.line(report.substituted, line)
        elif segment.ident == 0x06 and data:

            data = restore_objects(data, colour_depth, substitute, report,
                                   globals_have_blocks=True,
                                   what="global object", icons=icons)
        segments.append((segment.ident, data))
        if segment.ident == anchor:
            reinsert_stripped()
            anchor = None
    if icons is not None:
        icons.report_into(report)

    if progress is not None:
        progress("layout")

    level_table_end = tgf.OFF_LEVEL_TABLE + 4 * game.level_count
    body = bytearray()
    level_addresses: list[int] = []
    first_bank = 0
    globals_at = 0
    object_pointer_fixes = 0
    for i, (ident, data) in enumerate(segments):
        position = level_table_end + len(body)
        if ident == 0x06 and data:
            globals_at = position + 6

        if ident == 0x08:
            level_addresses.append(position + 6)
        if ident in (0x0A, 0x0B, 0x0C, 0x0D) and not first_bank:
            first_bank = position
        body += pack_block(ident, data, last=(i == len(segments) - 1))

    if len(level_addresses) != game.level_count:
        raise CannotUnprotect(
            f"header says {game.level_count} levels, the segment chain holds "
            f"{len(level_addresses)}"
        )
    struct.pack_into("<I", header, tgf.OFF_FIRST_NON_GAME_SEGMENT, first_bank)
    report.line(report.recovered, f"level address table ({game.level_count} entr(y|ies))")
    report.line(report.recovered, f"first-non-game-segment pointer 0x{first_bank:X}")

    out = bytearray(header)
    out += struct.pack(f"<{game.level_count}I", *level_addresses) if game.level_count else b""
    out += body

    object_pointer_fixes = _fix_object_pointers(out, level_addresses, globals_at)
    if object_pointer_fixes:
        report.line(
            report.recovered,
            f"{object_pointer_fixes} object first-data-block pointer(s), which a "
            f"protected file leaves naming the unprotected layout",
        )
    if repair_object_data:
        _repair_active_heads(out, level_addresses, report)
    return bytes(out), report

ACTIVE_VALUE_NAMES_AT = 0x24

ACTIVE_HEAD_CONSTANT_AT = 0x28

ACTIVE_HEAD_CONSTANT = 0x00FB

def _active_animation_end(data: bytes) -> int | None:
    if len(data) < 0x30 or data[0x2A:0x2E] != b"SPRI":
        return None
    sprite = 0x2E
    (sprite_len,) = struct.unpack_from("<H", data, sprite)
    ani = sprite + sprite_len
    if ani + 0x24 > len(data):
        return None
    end = ani + 4 + 32
    for slot in range(16):
        (aptr,) = struct.unpack_from("<H", data, ani + 4 + 2 * slot)
        if aptr >= 0x8000:
            continue
        adata = ani + aptr
        if adata + 0x40 > len(data):
            return None
        end = max(end, adata + 0x40)
        for direction in range(32):
            (dptr,) = struct.unpack_from("<H", data, adata + 2 * direction)
            if dptr >= 0x8000:
                continue
            ddata = adata + dptr
            if ddata + 0x0A > len(data):
                return None
            (frames,) = struct.unpack_from("<H", data, ddata + 6)
            end = max(end, ddata + 8 + 2 * frames)
    return end

def _repair_active_heads(out: bytearray, level_addresses: list[int],
                         report: Report) -> int:
    repaired = 0
    for level_index, level_data in enumerate(level_addresses):
        level_start = level_data - 6
        length = struct.unpack_from("<I", out, level_start + 2)[0]
        level = bytes(out[level_data:level_data + length])
        _, blocks = tgf.level_blocks(level)
        for block in blocks:
            if block.ident != 0x02:
                continue
            block_base = level_data + block.offset + 6
            for obj in tgf.object_definitions(block.data):
                if obj.object_type != 0x02:
                    continue
                for db in obj.blocks:
                    if db.ident != 0x00 or len(db.data) < 0x2E:
                        continue
                    data = db.data
                    (pos,) = struct.unpack_from(
                        "<I", data, ACTIVE_VALUE_NAMES_AT)
                    (constant,) = struct.unpack_from(
                        "<H", data, ACTIVE_HEAD_CONSTANT_AT)
                    if (not any(data[0x21:0x24])
                            and constant == ACTIVE_HEAD_CONSTANT
                            and 0 < pos <= len(data)):
                        continue
                    end = _active_animation_end(data)
                    if end is None or not 0 < end + 2 <= len(data):
                        report.line(
                            report.losses,
                            f"level {level_index}: active {obj.index} "
                            f"({obj.name!r}) violates the data-head "
                            f"invariants and its animation region does not "
                            f"walk, so it was left as shipped")
                        continue
                    at = block_base + db.offset + 6
                    out[at + 0x21:at + 0x24] = b"\0\0\0"
                    struct.pack_into("<I", out, at + ACTIVE_VALUE_NAMES_AT,
                                     end + 2)
                    struct.pack_into("<H", out, at + ACTIVE_HEAD_CONSTANT_AT,
                                     ACTIVE_HEAD_CONSTANT)
                    repaired += 1
                    report.line(
                        report.substituted,
                        f"level {level_index}: active {obj.index} "
                        f"({obj.name!r}) data-head repaired -- value-names "
                        f"position rederived as {end + 2}, the 0x00FB "
                        f"constant restored, +0x21..+0x23 zeroed")
    return repaired

def _repoint(out: bytearray, block_base: int, block: bytes,
             globals_have_blocks: bool = False) -> int:
    fixed = 0
    for obj in tgf.object_definitions(block, globals_have_blocks=globals_have_blocks):

        where = obj.blocks[0].offset if obj.blocks else obj.offset
        struct.pack_into(
            "<I", out,
            block_base + where - tgf.OBJECT_RECORD_HEAD + tgf.OFF_OBJECT_FIRST_BLOCK,
            block_base + where,
        )
        fixed += 1
    return fixed

def _fix_object_pointers(out: bytearray, level_addresses: list[int],
                         globals_at: int = 0) -> int:
    fixed = 0
    for level_data in level_addresses:
        level_start = level_data - 6
        length = struct.unpack_from("<I", out, level_start + 2)[0]
        level = bytes(out[level_data:level_data + length])
        start, blocks = tgf.level_blocks(level)
        for block in blocks:
            if block.ident != 0x02:
                continue
            fixed += _repoint(out, level_data + block.offset + 6, block.data)
    if globals_at:
        length = struct.unpack_from("<I", out, globals_at - 4)[0]
        fixed += _repoint(out, globals_at, bytes(out[globals_at:globals_at + length]),
                          globals_have_blocks=True)
    return fixed

DATA_SUFFIXES = (".gam", ".cca")

DEFAULT_SUFFIX = ".decompiled"

def _readable(path: Path) -> bool:

    try:
        tgf.read(path, clip_truncated=True)
    except Exception:
        return False
    return True

def find_data_file(exe: Path) -> tuple[Path | None, str]:
    """The 1996 data file sitting beside an executable, and how it was chosen.

    Chosen by content, never by name: the matching stem is tried first, and an
    ambiguous folder is reported as ambiguous rather than guessed at.
    """
    siblings = [p for p in sorted(exe.parent.iterdir())
                if p.suffix.lower() in DATA_SUFFIXES and _readable(p)]
    if not siblings:
        return None, f"no readable .gam/.cca beside {exe.name}"
    exact = [p for p in siblings if p.stem.lower() == exe.stem.lower()]
    if exact:
        return exact[0], f"stem matches {exe.name}"
    if len(siblings) == 1:
        return siblings[0], f"the only data file beside {exe.name}"
    names = ", ".join(p.name for p in siblings)
    return None, (f"{len(siblings)} data files beside {exe.name} and none has "
                  f"its stem -- name the one you mean: {names}")

def find_executable(data: Path) -> tuple[Path | None, str]:
    """The standalone beside a data file — which is where the extension modules live.
    """
    siblings = [p for p in sorted(data.parent.iterdir())
                if p.suffix.lower() == ".exe"]
    if not siblings:
        return None, "no .exe beside it, so no extensions to carve"
    exact = [p for p in siblings if p.stem.lower() == data.stem.lower()]
    if exact:
        return exact[0], f"stem matches {data.name}"
    if len(siblings) == 1:
        return siblings[0], f"the only .exe beside {data.name}"
    names = ", ".join(p.name for p in siblings)
    return None, (f"{len(siblings)} executables beside {data.name} and none has "
                  f"its stem, so none is carved: {names}")

def resolve(target: Path) -> tuple[Path | None, Path | None, list[str]]:
    """Work out the data-file-and-executable pair from whichever half was named.
    """
    notes: list[str] = []
    if target.suffix.lower() == ".exe":
        data, why = find_data_file(target)
        notes.append(f"data file: {data.name if data else 'NOT FOUND'} -- {why}")
        return data, target, notes
    exe, why = find_executable(target)
    notes.append(f"executable: {exe.name if exe else 'none'} -- {why}")
    return target, exe, notes

def main() -> int:
    """Run the unprotect from a command line."""
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("game", type=Path,
                        help="the .gam/.cca, or the stand-alone .exe beside it "
                             "-- either half finds the other")
    parser.add_argument("-o", "--output", type=Path)
    parser.add_argument(
        "--no-substitute-artwork",
        action="store_true",
        help="leave the stripped thumbnails and icons out rather than writing "
             "blank ones; the file is then structurally complete but the "
             "editor has no picture to show",
    )
    parser.add_argument(
        "--repair-bank",
        action="store_true",
        help="re-encode the bank images a sum-driven reader cannot decode. "
             "MMF 1.5 refuses a whole game over one such image while every "
             "1996 editor opens it; the repair rewrites only "
             "those images -- exact where the record is internally "
             "consistent, best-effort with transparent fill where the "
             "content is already missing from the file. OFF by default: "
             "everywhere else the bank is copied byte-for-byte, and this is "
             "the one flag that changes that",
    )
    parser.add_argument(
        "--repair-object-data",
        action="store_true",
        help="restore an active object's data-block head where the file as "
             "shipped violates the three invariants every authored active "
             "satisfies (58,597 of 58,597 measured): value-names position "
             "in range and equal to the animation region's end + 2, the "
             "0x00FB constant at +0x28, zeros at +0x21..+0x23. MMF 1.5 "
             "refuses a whole game over one such head while the 1996 "
             "editors open it. The position is REDERIVED from the block's "
             "own animation structure, not substituted. OFF by default: "
             "this program otherwise copies object data verbatim, and a "
             "healthy file comes back byte for byte")
    parser.add_argument(
        "--repack-placement", nargs="?", const="all", metavar="LEVELS",
        help="reorder a level's object-placement pointers so they address "
             "entries in ascending order. Bare = every level; or name them, "
             "e.g. --repack-placement 51. MMF 1.5 can refuse a project over "
             "ONE level's pointer order while all three 1996 editors open it, "
             "and this is what makes MMF accept it -- 72 bytes on the game it "
             "was measured on. The entries themselves do not move, so drawing "
             "order survives; only the order objects were placed in changes. "
             "OFF by default: this program otherwise copies the placement "
             "block verbatim, and a level already in ascending order is "
             "unaffected either way")
    parser.add_argument(
        "--no-generate-icons",
        action="store_true",
        help="substitute every emptied object icon with the blank square "
             "instead of deriving it from the object's own art. The default "
             "derives each icon from the image bank exactly as the editors "
             "themselves do on resave (identity below the 30-box, else "
             "longest side scaled to 30, last-pixel-of-cell sampling, "
             "transparent to index 0); the bank survives protection "
             "byte-identically, so the derivation uses nothing but the file. "
             "Use this flag to reproduce an older run",
    )
    parser.add_argument(
        "--keep-filter",
        action="store_true",
        help="leave block 1's row-drawn bits exactly as the protected file "
             "has them. The default marks every drawable row drawn, which "
             "is the *no filter* view state and matches the unfiltered "
             "block 3 this program writes. It does NOT fix the event-editor "
             "crash -- that needs block 3 regenerating",
    )
    parser.add_argument(
        "--no-regenerate-block3",
        action="store_true",
        help="write the empty 10-byte block 3 instead of deriving one. This is "
             "what the program used to do by default, and it is now the "
             "fallback rather than the behaviour: the empty form makes The "
             "Games Factory crash its event editor and silently discard the "
             "comment rows on save. Use it to reproduce an older run",
    )
    parser.add_argument(
        "--keep-comment-rows",
        action="store_true",
        help="keep the blank comment rows as empty records instead of deleting "
             "them. Their text is gone either way; what a blank record still "
             "carries is the row's POSITION in the event list and its "
             "background colour, both of which survive protection. Keeping "
             "them preserves that evidence at the cost of a sheet full of "
             "blank coloured bands",
    )
    parser.add_argument(
        "--regenerate-block3",
        action="store_true",
        help="derive the event editor's column list, comment records and M list "
             "for each level from that level's own content, instead of writing "
             "the empty form. The empty form makes The Games Factory CRASH when "
             "the event editor is opened, and makes it SILENTLY DISCARD the "
             "comment rows on save -- hundreds of event groups on a large game. "
             "The derived one fixes both: measured over thirteen controlled "
             "level pairs, the event editor opens unfiltered on every one while "
             "the empty build crashes on every one, and a re-save keeps all the "
             "groups the empty build loses. NOW THE DEFAULT -- this flag is "
             "accepted and redundant; --no-regenerate-block3 restores the old "
             "behaviour",
    )
    parser.add_argument(
        "--comment-placeholder",
        action="store_true",
        help="write each regenerated comment record as a single SPACE instead "
             "of empty. INVENTED CONTENT: the author's words are deleted by "
             "protection and this does not restore them, it gives the record a "
             "length. It was added because empty-text records once appeared to "
             "crash TGF's event editor where one-space records did not -- and "
             "none of those crashes reproduced when the comparison was re-run "
             "properly against a control. There is currently no measurement in "
             "which this flag helps. Off by default; it implies "
             "--keep-comment-rows, since a record cannot be both filled and "
             "deleted",
    )
    parser.add_argument(
        "--drop-comment-rows",
        action="store_true",
        help="DELETE the blank comment rows from the event list. NOW THE "
             "DEFAULT -- this flag is accepted and redundant; "
             "--keep-comment-rows restores them as empty records. It removes "
             "only rows that reference the deleted text: the sheet's FOLDER "
             "TITLES also carry the comment bit and their text is in block 1 "
             "and survives, so those are kept. Where protection kept the text "
             "-- version 1.00 of either product -- nothing is dropped, "
             "automatically, because those levels are passed through untouched",
    )
    parser.add_argument(
        "--suffix", default=DEFAULT_SUFFIX,
        help=f"what to call the recovery, as the MMF 1.0/1.5 driver names its "
             f"own output (default: {DEFAULT_SUFFIX})",
    )
    parser.add_argument(
        "--no-cox", action="store_true",
        help="do not carve the stand-alone's embedded extensions into "
             "<stem>_cox/ beside the recovery. Extraction is ON by default: a "
             "1996 game declares its extensions in segment 0x04 and carries "
             "the modules inside its own .exe, so a recovery without them is "
             "one the editor cannot fully open",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="overwrite extension files already in the output directory",
    )
    parser.add_argument("--report", action="store_true", help="print only, write nothing")
    args = parser.parse_args()

    regenerate = not args.no_regenerate_block3

    keep_rows = args.keep_comment_rows or args.comment_placeholder
    drop_rows = regenerate and not keep_rows

    if args.no_regenerate_block3 and (args.regenerate_block3
                                      or args.drop_comment_rows):
        parser.error("--no-regenerate-block3 contradicts --regenerate-block3 / "
                     "--drop-comment-rows; the empty form carries neither a "
                     "column list nor comment records")
    if args.no_regenerate_block3 and args.comment_placeholder:
        parser.error("--comment-placeholder only affects comment records that "
                     "regeneration writes, and --no-regenerate-block3 writes "
                     "none; on its own it would change nothing and report that "
                     "it had")
    if args.keep_comment_rows and args.drop_comment_rows:
        parser.error("--keep-comment-rows and --drop-comment-rows are opposites")
    if args.comment_placeholder and args.drop_comment_rows:
        parser.error("--comment-placeholder fills comment records and "
                     "--drop-comment-rows deletes them; pick one")

    source, exe, notes = resolve(args.game)
    for note in notes:
        print(f"  {note}")
    if source is None:
        parser.error(f"{args.game} names no data file this reader can pair")

    game = tgf.read(source)
    repack: set[int] | None = None
    if args.repack_placement == "all":
        repack = set(range(game.level_count))
    elif args.repack_placement:
        repack = set()
        for part in args.repack_placement.split(","):
            part = part.strip()
            if "-" in part[1:]:
                lo, hi = part.split("-", 1)
                repack.update(range(int(lo), int(hi) + 1))
            elif part:
                repack.add(int(part))
    data, report = unprotect(game, substitute=not args.no_substitute_artwork,
                             unfilter=not args.keep_filter,
                             regenerate_block3=regenerate,
                             comment_placeholder=args.comment_placeholder,
                             drop_comment_rows=drop_rows,
                             generate_icons=not args.no_generate_icons,
                             repair_bank=args.repair_bank,
                             repair_object_data=args.repair_object_data,
                             repack_placement=repack)
    print(report.render())
    print(f"  {len(game.raw):,} bytes in, {len(data):,} bytes out")

    if not args.report:
        out = args.output or source.with_name(
            f"{source.stem}{args.suffix}{source.suffix}")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data)
        print(f"  wrote {out}")
        if not args.no_cox:

            kind = "gox" if game.family == "tgf" else "cox"
            if exe is None:
                print(f"  extensions: no executable to carve")
            else:
                print("  " + extensions.extract_to(
                    exe, out.parent / f"{source.stem}_{kind}", args.force))
    return 0
