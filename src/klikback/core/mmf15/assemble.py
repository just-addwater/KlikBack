# GENERATED — do not edit by hand. This file is produced by KlikBack's
# sync tooling; changes belong in the source it is generated from.
#
# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""Assemble an editable MMF 1.5 project from what was recovered out of a game.

This is the half of the 1.5 pipeline that *writes*. Reading the game produces
frames, objects, events and banks; this turns them into the file an editor
opens, by starting from a base project and replacing named spans in it.

**The base project is generated rather than copied.** It is emitted from the
format's own grammar, so a rebuild needs nothing else on the machine to
start from.
Two properties make patching safe rather than hopeful: the container
decomposes into named regions that reassemble byte-identically, so a change
is a span replacement rather than an offset into a byte string; and records
re-serialise exactly, so a property is edited by name and written back rather
than poked.

**It refuses by name rather than half-building.** Where the recovered game
uses something this cannot reconstruct correctly, it raises `Unsupported`
naming the feature. That is the design: a project that opens and is quietly
wrong costs more than a refusal that says which object or feature stopped it.

Object icons and frame previews are **generated from the game's own artwork**
— each object's icon from the picture that object actually uses, each frame's
preview from that frame's own background. Where a game's extension module is
named by nothing that survived, the module's filename stands in and the
substitution is reported as a loss; the module itself is always carried
intact.
"""

from __future__ import annotations
import hashlib
import os
import struct
from collections.abc import Callable
from pathlib import Path
from klikback.core.mmf15.asset_bank import BankProblem, bank_contents, image_records_with_salvage
from klikback.core.mmf15.image_salvage import describe as describe_salvage
from klikback.core.mmf15.application_icons import EXPECTED_ICONS, icon_resources
from klikback.core.mmf15.backdrop import BACKDROP, BACKDROP_KIND, CHECKBOX_OFF, CHECKBOX_ON, split_backdrop_tail
from klikback.core.mmf15.cca import INHERITED, read_class_block, read_header
from klikback.core.common.container import EXTENSION_SIGNATURE, ContainerProblem, object_record_head, prop_index_end, spans
from klikback.core.mmf15.cross_build_report import editor_extensions, runtime_extensions as runtime_extension_table
from klikback.core.mmf15.counter_lives_object import COUNTER, COUNTER_KIND, LIVES, LIVES_KIND, SCORE, SCORE_KIND, build_counter_tail, build_lives_tail, build_score_tail, counter_payload, lives_payload, score_payload, split_counter_tail, split_lives_tail, split_score_tail
from klikback.core.mmf15.event_page import EVENT_OBJECT_TYPE_STRINGS, EventPageProblem, build_registry, compiled_programs, dense_item_ids, event_object_type_string, read_event_page, tile_events
from klikback.core.mmf15.frame_options import pfop_from_frame_flags
from klikback.core.mmf15.ftext import FORMATTED_TEXT, FORMATTED_TEXT_INSTANCE_TAG, FORMATTED_TEXT_KIND, build_ftext_tail, split_ftext_tail
from klikback.core.common.subapplication_reconstruct import SUBAPPLICATION_IDENTIFIER, SUBAPPLICATION_TYPE
from klikback.core.mmf15.image_bank import BANK_HEADER, build_bank, editor_bank
from klikback.core.common.cox_titles import CoxProblem, installed_titles, resource_entries, title_from_bytes
from klikback.core.mmf15.movement import runtime_extension_movement, set_movement_property
from klikback.core.mmf15.transition import checked_runtime_transition, transition_modules, transition_payload
from klikback.core.mmf15.object_record import ACTIVE, ACTIVE_KIND, OBJECT_SPAN, ObjectRecordProblem, runtime_animations, runtime_objects, split_active_tail
from klikback.core.mmf15.qanda import QANDA, QANDA_KIND, build_qanda_tail, split_qanda_tail
from klikback.core.mmf15.quick_backdrop import QUICK_BACKDROP, QUICK_BACKDROP_KIND, build_quick_backdrop_tail, split_quick_backdrop_tail
from klikback.core.mmf15.string import DISPLAY_FLAGS_OFFSET, DISPLAY_PROPERTY, NO_DESTROY_IF_FAR, NO_FOLLOW_FRAME, NO_INACTIVATE_IF_FAR, OBJECT_COLOUR_OFFSET, SAVE_BACKGROUND, STRING, STRING_KIND, VISIBLE_AT_START, WIPE_WITH_COLOUR, build_string_tail, split_string_tail
from klikback.core.common.animation_reconstruct import IMAGE_MODE_BYTES_PER_PIXEL, IMAGE_MODE_TO_COLOR_DEPTH, rle_encode_pixels, runtime_image_to_editor
from klikback.core.common.compare import Chunk, find_chunk, read_chunks
from klikback.core.common.icon_generate import OTHER_ICON_ART
from klikback.core.common.pe_icon_probe import decode_editor_icon
from klikback.core.common.solo_object_reconstruct import counter_family_payload, quick_backdrop_payload
from klikback.core.mmf15.icon_generate import ACTIVE_ICON_CONTENT_15, BACKDROP_ICON_CONTENT_15, OTHER_ICON_CONTENT_15, RENDER_ICON_CONTENT_15, artwork_icon_record_15, frame_preview_record, icon_from_image_15, imageless_icon_art, quick_backdrop_icon_15
from klikback.core.common.exe_to_cca import decompress_chunk
from klikback.core.common.extension_inventory import PACKAGE_VERSION_MMF10, chunk_payload, load_outer, package_version
from klikback.core.common.event_object_registry import CREATE_PLACEHOLDER, QUALIFIER_FLAG, UNRESOLVED_SHOOT_PARENT, event_object_slots, frame_registry, placeholder_editor_fields
from klikback.core.common.qualifier_reconstruct import qualifier_indices
from klikback.core.common.global_event_reconstruct import GROUP_OPEN as GROUP_OPEN_MARKER, build_global_event_property, classify_global_program
from klikback.core.common.blind_core_reconstruct import runtime_qualifiers
from klikback.core.common.extension_record import build_extension_tail, parse_extension_tail
from klikback.core.mmf15.run_options import run_options_15
from klikback.core.mmf15.window_options import window_options_15
from klikback.core.common.reconstruct_event_test import compiled_events_to_editor_events, drop_stray_group_closes, repair_missing_flat_group_close, stray_group_closes, unclosed_groups
from klikback.core.common.comment_rows import comment_row_template, restore_stripped_comments
from klikback.core.common.multi_animation_reconstruct import editor_animation_set
from klikback.core.common.mixed_multiframe_blind_reconstruct import build_atnf_bank, recover_frame_item_ids, runtime_font_bank
from klikback.core.common.music_reconstruct import runtime_music_bank
from klikback.core.common.global_value_reconstruct import global_value_record
from klikback.core.common.sound_reconstruct import runtime_sample_bank

APP_HEADER_CHUNK = 0x2223

APP_NAME_CHUNK = 0x2224

APP_AUTHOR_CHUNK = 0x2225

APP_MENU_CHUNK = 0x2226

APP_HELP_CHUNK = 0x2230

TRANSITION_MODULE_CHUNK = 0x2231

OBJECT_BANK_CHUNK = 0x2229

FRAME_CHUNK = 0x3333

FRAME_HEADER_CHUNK = 0x3334

FRAME_NAME_CHUNK = 0x3335

FRAME_PASSWORD_CHUNK = 0x3336

FRAME_PALETTE_CHUNK = 0x3337

FRAME_PLACEMENT_CHUNK = 0x3338

FRAME_EVENT_CHUNK = 0x333D

FRAME_FADE_IN_CHUNK = 0x333B

FRAME_FADE_OUT_CHUNK = 0x333C

DEFAULT_RUNTIME_OBJECT_COUNT = 300

FONT_BANK_CHUNKS = {0x5556, 0x6667}

IMAGE_BANK_CHUNKS = {0x5555, 0x6666}

EXTENSION_OBJECT_TYPE_BASE = 32

EXTENSION_KIND = b"Xtnd"

INSTANCE_TAG = b"Inst"

STRING_INSTANCE_TAG = b"IPIn"

PLACEMENT_RECORD = 12

class Unsupported(Exception):
    """Raised when the game uses something that cannot be rebuilt correctly.

    The message names the feature, because "which one?" is the only question
    worth answering at that point. Not an error in the run: an honest limit.
    """

def runtime_frame_containers(exe: Path) -> list[bytes]:
    """Every frame of the compiled game, still packed, in the order it was built.
    """
    return [
        chunk_payload(chunk)
        for chunk in load_outer(exe)
        if chunk.chunk_id == FRAME_CHUNK
    ]

def runtime_frame_chunks(exe: Path) -> list[list]:
    """The same frames, opened one level: each as its list of tagged pieces."""
    return [
        read_chunks(payload, 0, len(payload))
        for payload in runtime_frame_containers(exe)
    ]

def frame_password(payload: bytes) -> bytes | None:
    """The password protecting one frame, or nothing if it was never set.

    A frame password survives compilation intact, so it can be put back rather
    than reconstructed. Two of them in one frame is a contradiction the reader
    refuses instead of picking a winner.
    """
    found = None
    pos = 0
    while pos + 8 <= len(payload):
        chunk_id, flags, size = struct.unpack_from("<HHI", payload, pos)
        end = pos + 8 + size
        if end > len(payload):
            raise Unsupported(
                f"frame chunk 0x{chunk_id:04X} extends beyond its container"
            )
        if chunk_id == FRAME_PASSWORD_CHUNK:
            if found is not None:
                raise Unsupported("frame has more than one 0x3336 password chunk")
            found = chunk_payload(Chunk(chunk_id, flags, payload[pos + 8 : end]))
        pos = end
    return found

def runtime_frames(exe: Path) -> list[dict]:
    """Read each frame's own settings: size, background, palette, transitions, name.

    These are the properties the frame editor shows in its own dialogs, and every
    one of them is read from the game rather than defaulted. A frame that carries
    no event header at all is refused, because its object count — which the
    editor needs — would otherwise be a guess.
    """
    frames = []
    for payload in runtime_frame_containers(exe):
        chunks = read_chunks(payload, 0, len(payload))
        frame: dict = {
            "name": None,
            "palette": None,
            "transitions": {},
            "runtime_object_count": None,

            "password": frame_password(payload),
        }
        for inner in chunks:
            body = chunk_payload(inner)
            if inner.chunk_id == FRAME_HEADER_CHUNK:
                if len(body) != 10:
                    raise Unsupported(f"frame header is {len(body)} bytes, not 10")
                width, height = struct.unpack_from("<HH", body, 0)
                frame["width"] = width
                frame["height"] = height

                frame["background"] = body[4] | body[5] << 8 | body[6] << 16
                frame["flags"] = struct.unpack_from("<H", body, 8)[0]
            elif inner.chunk_id == FRAME_NAME_CHUNK:
                frame["name"] = body.split(b"\x00", 1)[0]
            elif inner.chunk_id == FRAME_PALETTE_CHUNK:
                frame["palette"] = body
            elif inner.chunk_id == FRAME_EVENT_CHUNK:
                if len(body) < 6 or not body.startswith(b"ER>>"):
                    raise Unsupported("frame event block has no complete ER>> header")
                frame["runtime_object_count"] = struct.unpack_from("<H", body, 4)[0]
            elif inner.chunk_id in (FRAME_FADE_IN_CHUNK, FRAME_FADE_OUT_CHUNK):
                tag = "FadI" if inner.chunk_id == FRAME_FADE_IN_CHUNK else "FadO"
                if tag in frame["transitions"]:
                    raise Unsupported(
                        f"frame has more than one runtime {tag} transition"
                    )
                try:
                    frame["transitions"][tag] = checked_runtime_transition(body)
                except Exception as problem:
                    raise Unsupported(f"frame {tag}: {problem}") from None
        if frame["runtime_object_count"] is None:
            raise Unsupported("frame has no runtime object-count event header")
        frames.append(frame)
    return frames

def placements_from_chunks(chunks: list) -> list[dict]:
    """Where every object sits in a frame, and which instance it belongs to."""
    placement = next(
        (chunk for chunk in chunks if chunk.chunk_id == FRAME_PLACEMENT_CHUNK),
        None,
    )
    if placement is None:
        return []
    payload = decompress_chunk(placement)
    (count,) = struct.unpack_from("<I", payload, 0)
    if len(payload) != 4 + count * PLACEMENT_RECORD:
        raise Unsupported(
            f"placement chunk is {len(payload)} bytes for {count} placements"
        )
    found = []
    for index in range(count):
        handle, object_id, x, y, link = struct.unpack_from(
            "<HHhhI", payload, 4 + index * PLACEMENT_RECORD
        )
        found.append(
            {
                "handle": handle,
                "object_id": object_id,
                "x": x,
                "y": y,
                "link": link,
            }
        )
    return found

CREATE_PLACEHOLDER_LINK = 0x00000001

def create_placeholders_for_unplaced(
    membership: list[int],
    placements: list[dict],
    frame_index: int,
    losses: list[str],
) -> list[dict]:
    """Give an instance to an object the events use but the frame never places.

    Events can name an object that is only ever created while the game runs, so
    the compiled frame holds no position for it. The object is real and must
    appear in the editor's object list, so it is placed at the top-left corner
    and the substitution is reported: the position the author chose is a compile
    loss, the object itself is not.
    """
    placed = {placement["object_id"] for placement in placements}
    unplaced = [object_id for object_id in membership if object_id not in placed]
    if not unplaced:
        return []
    next_handle = max((p["handle"] for p in placements), default=-1) + 1
    made = []
    for object_id in unplaced:
        made.append(
            {
                "handle": next_handle,
                "object_id": object_id,
                "x": 0,
                "y": 0,
                "link": CREATE_PLACEHOLDER_LINK,
            }
        )
        next_handle += 1
    losses.append(
        f"frame {frame_index}: {len(made)} event-referenced object"
        f"{'s' if len(made) != 1 else ''} "
        f"({', '.join(str(object_id) for object_id in unplaced)}) "
        f"{'carry' if len(made) != 1 else 'carries'} no runtime placement, so "
        "each is given a Create placeholder instance at (0, 0); the authored "
        "editor position is a compile loss"
    )
    return made

def programs_from_chunks(chunks: list) -> list[list[bytes]]:
    """The event programs a frame carries, one list of rows per program."""
    if not any(chunk.chunk_id == FRAME_EVENT_CHUNK for chunk in chunks):
        return []
    block = decompress_chunk(find_chunk(chunks, FRAME_EVENT_CHUNK))
    try:
        return [tile_events(program) for program in compiled_programs(block)]
    except EventPageProblem as problem:
        raise Unsupported(str(problem)) from None

def split_frame_programs(
    frame_programs: list[list[list[bytes]]],
    ownerless_behaviours_per_frame: list[int] | str | None = None,
) -> tuple[list[list[bytes]], list[bytes] | None, list[list[list[bytes]]]]:
    """Separate a frame's event pages from the programs that trail behind them.

    A frame's trailing programs are an object's behaviour or a global page whose
    owner reference did not survive compilation. Splitting them out is what
    allows them to be recovered and labelled honestly instead of silently merged
    into the frame's own events.
    """
    automatic_recovery = ownerless_behaviours_per_frame == "auto"
    if (
        ownerless_behaviours_per_frame is not None
        and not automatic_recovery
        and len(ownerless_behaviours_per_frame) != len(frame_programs)
    ):
        raise Unsupported(
            "--recover-ownerless-behaviours supplies "
            f"{len(ownerless_behaviours_per_frame)} frame counts for "
            f"{len(frame_programs)} frames"
        )
    global_index = classify_global_program(frame_programs)
    own: list[list[bytes]] = []
    global_sheet: list[bytes] | None = None
    ownerless: list[list[list[bytes]]] = []
    for index, programs in enumerate(frame_programs):
        skip = global_index[index] if global_index else None
        requested = (
            None
            if ownerless_behaviours_per_frame is None or automatic_recovery
            else ownerless_behaviours_per_frame[index]
        )
        if requested is not None and (requested < 0 or requested > len(programs)):
            raise Unsupported(
                f"frame {index} requests {requested} ownerless Behaviour "
                f"programs but contains {len(programs)} total programs"
            )
        if skip is None:
            if requested is None:

                sheet, behaviours = (
                    (programs[0], programs[1:]) if programs else ([], [])
                )
            else:
                own_count = len(programs) - requested
                if own_count not in (0, 1):
                    raise Unsupported(
                        f"frame {index} would leave {own_count} programs before "
                        "the requested Behaviour suffix, not zero or one frame sheet"
                    )
                sheet = programs[0] if own_count else []
                behaviours = programs[own_count:]
        else:
            if global_sheet is None:
                global_sheet = programs[skip]

            sheet = programs[0] if skip else []
            behaviours = programs[skip + 1:]
            if requested is not None and requested != len(behaviours):
                raise Unsupported(
                    f"frame {index} requests {requested} ownerless Behaviour "
                    f"programs, but the proven global-sheet boundary leaves "
                    f"{len(behaviours)}"
                )
        if behaviours and ownerless_behaviours_per_frame is None:
            raise Unsupported(
                f"frame {index} holds {len(behaviours)} object Behaviour "
                "program(s); they cannot be re-attached because compilation "
                "discards the owner; pass --recover-ownerless-behaviours to "
                "preserve them after labelled frame-event comments"
            )
        own.append(sheet)
        ownerless.append(behaviours)
    return own, global_sheet, ownerless

FALLBACK_COMMENT_LABEL = (
    "RECOVERED GLOBAL EVENT OR BEHAVIOUR {index} - OWNER UNKNOWN"
    " -- the {rows} row(s) below this line {explanation}"
)

FALLBACK_COMMENT_EXPLANATION = (
    "belong in this frame and run as they always did; "
    "the EXE does not say whether they were global events "
    "or an object's behaviour"
)

_FALLBACK_COMMENT_EVENT = comment_row_template(
    row_number=0, row_index=0, comment_id=0, background=0x00FFFFFF
)

COMMENT_MARKER = b"\xff\xf7"

COMMENT_MARKER_OFFSET = 0x10

COMMENT_FLAGS_OFFSET = 0x04

COMMENT_FLAG = 0x0080

IN_GROUP_FLAG = 0x2000

COMMENT_ID_OFFSET = 0x5C

COMMENT_BACKGROUND_OFFSET = 0x56

COMMENT_BACKGROUND_RECOVERED = 0x0000FFFF

def fallback_comment_row(comment_id: int, inside_group: bool = False) -> bytes:
    """Build the comment row that introduces a recovered, unattributed program.
    """
    if not 0 <= comment_id <= 0xFFFF:
        raise Unsupported(f"comment id {comment_id} does not fit a u16")
    row = bytearray(_FALLBACK_COMMENT_EVENT)
    struct.pack_into("<H", row, COMMENT_ID_OFFSET, comment_id)
    struct.pack_into(
        "<I", row, COMMENT_BACKGROUND_OFFSET, COMMENT_BACKGROUND_RECOVERED
    )
    flags = COMMENT_FLAG | (IN_GROUP_FLAG if inside_group else 0)
    struct.pack_into("<H", row, COMMENT_FLAGS_OFFSET, flags)
    return bytes(row)

def is_comment_row(event: bytes) -> bool:
    """Whether an event row is a comment rather than a condition-and-action pair.
    """
    return (
        len(event) >= COMMENT_MARKER_OFFSET + 2
        and event[COMMENT_MARKER_OFFSET:COMMENT_MARKER_OFFSET + 2] == COMMENT_MARKER
    )

def comment_row_id(event: bytes) -> int:
    """Which stored remark an event comment row displays.

    The text of a comment lives apart from the row that shows it; this is the
    link between the two.
    """
    if not is_comment_row(event):
        raise Unsupported("this row is not a comment row; +0x5C is not an id")
    return struct.unpack_from("<H", event, COMMENT_ID_OFFSET)[0]

def append_ownerless_behaviour_comments(
    frame_sheet: list[bytes],
    behaviours: list[list[bytes]],
    first_index: int = 1,
    recover_comments: bool = False,
    first_comment_index: int = 1,
) -> tuple[list[bytes], list[bytes]]:
    """Label recovered programs whose owner the compiled game no longer names.

    The events are real and are written back; what is missing is only the note
    saying whose they were, so they are marked as such rather than attributed to
    an object that may not be the right one.
    """
    combined: list[bytes] = []
    comments: list[bytes] = []
    recovered = 0
    for offset, program in enumerate([frame_sheet, *behaviours]):
        seam = bool(offset)
        restored: list[bytes] = []
        if recover_comments:
            program, restored = restore_stripped_comments(
                program,
                first_id=len(comments) + (1 if seam else 0),
                first_index=first_comment_index + recovered,
                row_factory=fallback_comment_row,
            )
            recovered += len(restored)
        if seam:
            combined.append(fallback_comment_row(len(comments)))
            comments.append(
                FALLBACK_COMMENT_LABEL.format(
                    index=first_index + offset - 1,
                    rows=len(program),
                    explanation=FALLBACK_COMMENT_EXPLANATION,
                ).encode("ascii")
            )
        comments.extend(restored)
        combined.extend(program)
    return combined, comments

def runtime_images(
    exe: Path, salvage_notes: list[str] | None = None
) -> list[tuple[int, bytes]]:
    """Every picture in the game, converted to the form the editor stores.

    If the image bank cannot be read as a whole, each picture is recovered on its
    own and whatever decodes is kept. A picture rebuilt that way is reported as a
    partial recovery with neutral filler where the data stopped — a damaged
    image the author can see and replace is worth more than a refused project,
    but it is never presented as the original artwork.
    """
    try:
        contents, _ambiguous, _families, _skipped = bank_contents(exe, 0)
        images = contents.get("image") or {}
    except BankProblem:
        if salvage_notes is None:
            raise
        images, salvaged = image_records_with_salvage(exe)
        for stats in salvaged:
            salvage_notes.append(
                f"image handle {stats['handle']}: the compressed stream stops "
                f"part way and the remainder cannot be decoded, so the record "
                f"is rebuilt from what did decode -- {describe_salvage(stats)}. "
                "The missing pixels are filled with a neutral colour; this is a "
                "partially recovered picture, not the artwork"
            )

    return [
        (handle, runtime_image_to_editor(record))
        for handle, record in images.items()
    ]

UNRESOLVED_IMAGE_HANDLE = 0xFFFF

def blank_image_record(mode: int) -> bytes:
    """A one-pixel stand-in, for the rare object whose picture cannot be resolved.
    """
    bytes_per_pixel = IMAGE_MODE_BYTES_PER_PIXEL.get(mode)
    if bytes_per_pixel is None:
        raise Unsupported(f"no pixel width for image mode {mode}")
    header = bytearray(24)
    struct.pack_into("<I", header, 6, bytes_per_pixel)
    struct.pack_into("<HH", header, 10, 1, 1)
    header[14] = mode

    header[15] = 0
    return runtime_image_to_editor(bytes(header) + bytes(bytes_per_pixel))

def runtime_application_properties(outer: list) -> dict:
    """The application's own settings: name, author, window, colours, menu, help.

    The project-level settings, gathered in a single pass over the compiled
    package's chunks: the name and author, the menu and help file if the
    application has them, the window size and its options, the background colour,
    the starting score and lives, and the run options.

    Most of it comes out of one header chunk, and that chunk is required — a
    package without it is refused rather than given defaults, because these are
    the settings that decide what the project *is* and inventing them would be
    inventing the application. Its length is checked before anything is read out
    of it, so a shorter header says so instead of returning whatever followed.

    The menu and the help file are allowed to be absent but not to be duplicated:
    more than one of either means the package is not the shape this reads, and
    picking one would be a guess.

    One value has no second source. The application's graphic mode is stated only
    here — each image also carries a mode byte, but that is per image and says
    nothing about what the project as a whole is set to.
    """
    name = b""
    author = b""
    menu = None
    help_file = None
    app_flags = 0
    window_size = None
    graphic_mode = None
    app_colour = None
    starting_score = None
    starting_lives = None
    for chunk in outer:
        if chunk.chunk_id == APP_NAME_CHUNK:
            name = chunk_payload(chunk).split(b"\x00", 1)[0]
        elif chunk.chunk_id == APP_AUTHOR_CHUNK:
            author = chunk_payload(chunk).split(b"\x00", 1)[0]
        elif chunk.chunk_id == APP_MENU_CHUNK:
            if menu is not None:
                raise Unsupported("the package has more than one application menu")
            menu = chunk_payload(chunk)
        elif chunk.chunk_id == APP_HELP_CHUNK:
            if help_file is not None:
                raise Unsupported("the package has more than one application help file")
            help_file = chunk_payload(chunk)
        elif chunk.chunk_id == APP_HEADER_CHUNK:
            payload = chunk_payload(chunk)
            if len(payload) < 0x50:
                raise Unsupported(
                    f"the runtime application header is {len(payload)} bytes, "
                    "shorter than the application colour at +0x4C"
                )
            app_flags = struct.unpack_from("<I", payload, 0)[0]

            (graphic_mode,) = struct.unpack_from("<H", payload, 4)
            width, height = struct.unpack_from("<HH", payload, 8)
            window_size = width | (height << 16)
            starting_score, starting_lives = struct.unpack_from("<II", payload, 0x0C)
            (app_colour,) = struct.unpack_from("<I", payload, 0x4C)

    if window_size is None:
        raise Unsupported("the package has no runtime application header")
    return {
        "name": name,
        "author": author,
        "menu": menu,
        "help_file": help_file,
        "app_colour": app_colour,
        "starting_score": starting_score,
        "starting_lives": starting_lives,
        "run_options": run_options_15(app_flags),
        "window_options": window_options_15(app_flags),
        "window_size": window_size,
        "graphic_mode": graphic_mode,
    }

EDITDATA_SIZE_FIELD = 2

def definition_is_headerless(definition: bytes) -> bool:
    if len(definition) < 4:
        return False
    (declared,) = struct.unpack_from("<I", definition, 0)
    return declared == len(definition)

def same_module_editdata(
    objects: list[dict], module_by_slot: dict[int, str]
) -> dict[str, tuple[int, bytes]]:
    best: dict[str, tuple[int, bytes]] = {}
    for obj in objects:
        if obj["object_type"] < EXTENSION_OBJECT_TYPE_BASE:
            continue
        module = module_by_slot.get(
            obj["object_type"] - EXTENSION_OBJECT_TYPE_BASE
        )
        definition = obj["definition"]
        if module is None or len(definition) < 0x28:
            continue
        (offset,) = struct.unpack_from("<I", definition, 0x24)
        if not 0x28 <= offset < len(definition):
            continue
        editdata = definition[offset:]
        if len(editdata) < EDITDATA_SIZE_FIELD:
            continue
        (declared,) = struct.unpack_from("<H", editdata, 0)
        if declared != len(editdata):
            continue
        current = best.get(module)
        if current is None or len(editdata) < len(current[1]):
            best[module] = (obj["object_id"], editdata)
    return best

def runtime_application(
    exe: Path,
    ownerless_behaviours_per_frame: list[int] | str | None = None,
    recover_comments: bool = False,
) -> dict:
    """Read a whole compiled game into the description everything else assembles from.

    The long one, and the one that decides what is recoverable. It walks the
    package once and produces a single summary — application settings, frames,
    objects, images, events, extension modules — with each unreconstructable
    feature either refused by name or recorded as a loss. Nothing below this
    point reads the game again; they all work from what this returned.
    """
    outer = load_outer(exe)
    present = {chunk.chunk_id for chunk in outer}
    application = runtime_application_properties(outer)

    module_chunks = [
        transition_modules(chunk_payload(chunk))
        for chunk in outer
        if chunk.chunk_id == TRANSITION_MODULE_CHUNK
    ]
    if len(module_chunks) > 1:
        raise Unsupported(
            f"the package has {len(module_chunks)} transition-module chunks"
        )
    transition_module_names = set(module_chunks[0]) if module_chunks else set()

    frames = runtime_frames(exe)
    frame_chunks = runtime_frame_chunks(exe)
    if not frames:
        raise Unsupported("the package has no frames")
    objects = runtime_objects(exe) if OBJECT_BANK_CHUNK in present else []
    for obj in objects:
        transitions = {}
        definition = obj["definition"]
        if len(definition) >= 0x3C:
            for tag, field in (("FadI", 0x34), ("FadO", 0x38)):
                (offset,) = struct.unpack_from("<I", definition, field)
                if not offset:
                    continue
                try:
                    transitions[tag] = checked_runtime_transition(definition, offset)
                except Exception as problem:
                    raise Unsupported(
                        f"object {obj['object_id']} {tag}: {problem}"
                    ) from None
        obj["transitions"] = transitions
    for obj in objects:
        if obj["object_type"] not in (
            ACTIVE,
            BACKDROP,
            QUICK_BACKDROP,
            STRING,
            COUNTER,
            LIVES,
            SCORE,
            QANDA,
            FORMATTED_TEXT,
            SUBAPPLICATION_TYPE,
        ) and obj["object_type"] < EXTENSION_OBJECT_TYPE_BASE:
            raise Unsupported(
                f"object {obj['object_id']} is runtime type "
                f"{obj['object_type']}; only the Active, regular Backdrop "
                f"Quick Backdrop, String, Counter, Lives, Score and "
                f"Question & Answer, Formatted Text and measured extension "
                f"objects are built yet"
            )
    runtime_modules = runtime_extension_table(exe)
    module_by_slot = {}
    if runtime_modules is not None:
        _count, _high_water, keys, _metadata = runtime_modules
        module_by_slot = {slot: filename for _kind, slot, filename, _subtype in keys}

    losses: list[str] = []
    editdata_donors = same_module_editdata(objects, module_by_slot)
    for obj in objects:
        if obj["object_type"] < EXTENSION_OBJECT_TYPE_BASE:
            continue
        slot = obj["object_type"] - EXTENSION_OBJECT_TYPE_BASE
        if slot not in module_by_slot:

            if package_version(Path(exe)) == PACKAGE_VERSION_MMF10:
                raise Unsupported(
                    f"this is an MMF 1.0 package (PAME version 0x0300), not a "
                    f"1.5 one -- its extension table is at 0x2228, so slot "
                    f"{slot} of extension object {obj['object_id']} cannot be "
                    f"resolved here. Use the 1.0 pipeline: "
                    f"py -3 tools/mmf1_decompile.py \"{exe}\""
                )
            raise Unsupported(
                f"extension object {obj['object_id']} uses module slot {slot}, "
                "which is absent from runtime chunk 0x2234"
            )
        definition = obj["definition"]
        if len(definition) < 0x28:
            raise Unsupported(
                f"extension object {obj['object_id']} definition is truncated"
            )
        module = module_by_slot[slot]
        (editdata_offset,) = struct.unpack_from("<I", definition, 0x24)
        if editdata_offset == 0 and definition_is_headerless(definition):

            recovered = editdata_donors.get(module)
            if recovered is None:
                raise Unsupported(
                    f"extension object {obj['object_id']} carries no EDITDATA "
                    f"(offset 0, definition ends at its header) and no other "
                    f"{module} object in this package has any to recover the "
                    "module's unconfigured form from"
                )
            donor_id, donor = recovered
            neutral = donor[:EDITDATA_SIZE_FIELD] + bytes(
                len(donor) - EDITDATA_SIZE_FIELD
            )
            zeroed = sum(
                1
                for a, b in zip(donor[EDITDATA_SIZE_FIELD:],
                                neutral[EDITDATA_SIZE_FIELD:])
                if a != b
            )
            losses.append(
                f"extension object {obj['object_id']} "
                f"{obj['name'].decode('latin-1')!r} ({module}) carries no "
                "EDITDATA -- the compiled definition ends at its header and "
                "stores offset 0, so the object's private settings are a "
                f"compile-time loss. It is given the {len(neutral)}-byte "
                f"unconfigured form of the module, taken from object "
                f"{donor_id} in this same package with {zeroed} configured "
                "byte(s) zeroed beyond the leading size word; the object "
                "survives, its settings do not"
            )
            obj["extension_module"] = module
            obj["editdata"] = neutral
            continue
        if not 0x28 <= editdata_offset < len(definition):
            raise Unsupported(
                f"extension object {obj['object_id']} EDITDATA offset "
                f"{editdata_offset} is out of range"
            )
        obj["extension_module"] = module
        obj["editdata"] = definition[editdata_offset:]

    for label, transitions in [
        *(
            (f"frame {index}", frame["transitions"])
            for index, frame in enumerate(frames)
        ),
        *(
            (f"object {obj['object_id']}", obj["transitions"])
            for obj in objects
        ),
    ]:
        for tag, transition in transitions.items():
            module = transition["module"]
            if module not in transition_module_names:
                raise Unsupported(
                    f"{label} {tag} names {module!r}, absent from runtime "
                    "transition-module chunk 0x2231"
                )
    objects_by_id = {obj["object_id"]: obj for obj in objects}
    try:
        frame_item_ids = recover_frame_item_ids(outer, len(frames))
    except ValueError as problem:
        raise Unsupported(f"frame item ids are ambiguous: {problem}") from None

    own_sheets, global_sheet, ownerless_behaviours = split_frame_programs(
        [programs_from_chunks(chunks) for chunks in frame_chunks],
        ownerless_behaviours_per_frame=ownerless_behaviours_per_frame,
    )

    global_event_registry = global_event_registry_15(global_sheet, objects_by_id)
    global_events = (
        None
        if global_event_registry
        else global_event_payload_15(global_sheet, [])
    )

    frame_summaries = []
    assigned: set[int] = set()

    placeholder_only_anywhere: set[int] = set()

    recovered_so_far = 0
    recovered_comments = 0

    repairs: list[str] = []

    bank_object_types = {
        object_id: obj["object_type"] for object_id, obj in objects_by_id.items()
    }
    for index, (metadata, chunks) in enumerate(zip(frames, frame_chunks)):

        strays = stray_group_closes(own_sheets[index])
        sheet = drop_stray_group_closes(own_sheets[index])
        if strays:
            losses.append(
                f"frame {index}: dropped {len(strays)} event-group close"
                f"{'s' if len(strays) != 1 else ''} the compiler emitted with "
                f"no matching open (rows {', '.join(str(s) for s in strays)}); "
                "MMF itself never writes an unmatched close or an unclosed "
                "open, so the row cannot be represented -- everything else in "
                "the program is kept"
            )
        orphans = unclosed_groups(sheet)
        compiled = repair_missing_flat_group_close(sheet)
        if orphans:
            losses.append(
                f"frame {index}: closed {len(orphans)} event group"
                f"{'s' if len(orphans) != 1 else ''} the compiler left open at "
                f"the end of the program (rows {', '.join(str(o) for o in orphans)}); "
                "each close is placed before the next group, making the "
                "remainder a sibling rather than nested -- the compiled bytes "
                "do not say which, so check those groups in the event editor"
            )
        compiled, fallback_comments = append_ownerless_behaviour_comments(
            compiled,
            ownerless_behaviours[index],
            first_index=recovered_so_far + 1,
            recover_comments=recover_comments,
            first_comment_index=recovered_comments + 1,
        )
        recovered_so_far += len(ownerless_behaviours[index])
        restored_here = len(fallback_comments) - len(ownerless_behaviours[index])
        recovered_comments += restored_here
        if restored_here:
            losses.append(
                f"frame {index}: restored {restored_here} stripped comment "
                f"row{'s' if restored_here != 1 else ''} at the position the "
                "compiler's row numbering names; the TEXT is substituted, "
                "because compilation keeps a comment's position and discards "
                "its words"
            )
        if ownerless_behaviours[index]:
            count = len(ownerless_behaviours[index])
            losses.append(
                f"frame {index}: recovered {count} ownerless Behaviour "
                f"program{'s' if count != 1 else ''} after labelled frame-event "
                f"comment{'s' if count != 1 else ''}; compilation discarded "
                "the original object owner and authored Behaviour name"
            )
        placements = placements_from_chunks(chunks) if objects else []
        unresolved: list[int] = []

        type_repairs: list[dict] = []
        try:
            registry = frame_registry(
                [
                    (p["handle"], p["x"], p["y"], p["object_id"], p["link"])
                    for p in placements
                ],
                compiled,
                objects_by_id,
                unresolved_shoot_parents=unresolved,
                type_repairs=type_repairs,
            )
        except ValueError as problem:
            raise Unsupported(
                f"frame {index}'s event references do not resolve: {problem}"
            ) from None
        for object_id in registry["event_object_ids"]:
            obj = objects_by_id[object_id]
            if (
                obj["object_type"] not in EVENT_OBJECT_TYPE_STRINGS
                and obj["object_type"] < EXTENSION_OBJECT_TYPE_BASE
            ):
                raise Unsupported(
                    f"object {obj['object_id']} has no COIList type string for "
                    f"runtime type {obj['object_type']}"
                )
        if type_repairs:

            by_object: dict[tuple, int] = {}
            for entry in type_repairs:
                key = (
                    entry["object_id"],
                    entry["name"],
                    entry["stored_type"],
                    entry["bank_type"],
                )
                by_object[key] = by_object.get(key, 0) + 1

            in_registry = set(registry["event_object_ids"])
            for (object_id, name, stored, bank), count in sorted(
                by_object.items()
            ):
                label = name.decode("latin-1") if isinstance(name, bytes) else name
                repairs.append(
                    f"frame {index}: rewrote the stored runtime type of {count} "
                    f"event reference{'s' if count != 1 else ''} to object "
                    f"{object_id} {label!r} from {stored} to the object bank's "
                    f"{bank}; "
                    + (
                        "the reference resolves to that object in this frame's "
                        "registry, so the row now names what it acts on"
                        if object_id in in_registry
                        else "THE OBJECT IS NOT IN THIS FRAME'S EVENT REGISTRY "
                        "AND THE REPAIRED ROW STILL RESOLVES TO NOTHING"
                    )
                )
        for parent in registry["dangling_shoot_parents"]:

            losses.append(
                f"frame {index} has a Shoot placeholder naming parent object "
                f"{parent} ({objects_by_id[parent]['name'].decode('latin-1')!r}) "
                "which has no other evidence in this frame; the parent word is "
                "stale, so it is written with no parent"
            )
        for handle, parent in unresolved:

            wrote = (
                "the documented 0xFFFF marker"
                if parent == UNRESOLVED_SHOOT_PARENT
                else f"scratch value {parent} (0x{parent:04X})"
            )
            losses.append(
                f"frame {index} instance {handle} is a Shoot placeholder whose "
                f"parent was already unresolved when the target was compiled "
                f"({wrote}); it is written with no parent"
            )

        registry = merge_owned_qualifiers(
            registry,
            [obj["object_id"] for obj in objects]
            if len(frames) == 1
            else registry["frame_item_object_ids"],
            objects_by_id,
        )
        event_item_ids = dense_item_ids(registry)
        if len(frames) == 1:

            for obj in objects:
                event_item_ids.setdefault(obj["object_id"], len(event_item_ids))
            item_ids = event_item_ids
            frame_objects = objects
        else:

            membership = registry["frame_item_object_ids"]
            frame_objects = [objects_by_id[object_id] for object_id in membership]
            item_ids = registry["local_item_for"]
            assigned.update(membership)

            orphans = set(registry["placeholder_only_orphans"])
            if orphans:
                placeholder_only_anywhere |= orphans
                for object_id in sorted(orphans):
                    dropped = [
                        placement
                        for placement in placements
                        if placement["object_id"] == object_id
                    ]
                    kinds = ", ".join(sorted({
                        "Create"
                        if placement["link"] & 0xFFFF == CREATE_PLACEHOLDER
                        else "Shoot"
                        for placement in dropped
                    }))
                    name = objects_by_id[object_id]["name"]
                    label = (
                        name.decode("latin-1")
                        if isinstance(name, bytes)
                        else name
                    )
                    losses.append(
                        f"frame {index}: runtime object {object_id} {label!r} "
                        f"is placed only as a {kinds} placeholder "
                        f"({len(dropped)} placement"
                        f"{'s' if len(dropped) != 1 else ''}) and no event row "
                        "names it; MMF writes no object record, no instance and "
                        "no registry entry for such an object, so it is not a "
                        "member of this frame and its placeholder placement"
                        f"{'s are' if len(dropped) != 1 else ' is'} dropped "
                        "with it"
                    )
                placements = [
                    placement
                    for placement in placements
                    if placement["object_id"] not in orphans
                ]
            placements += create_placeholders_for_unplaced(
                membership, placements, index, losses
            )
        frame_summaries.append(
            metadata
            | {
                "frame_item_id": frame_item_ids[index],
                "objects": frame_objects,
                "placements": placements,
                "events": b"".join(
                    compiled_events_to_editor_events(
                        compiled,
                        object_id_map=event_item_ids,
                        object_types=bank_object_types,
                    )
                ),
                "remarks": fallback_comments,
                "event_count": len(compiled),
                "ownerless_behaviour_programs": len(ownerless_behaviours[index]),
                "item_ids": item_ids,
                "event_item_ids": event_item_ids,
                "registry": build_registry(
                    registry["event_object_ids"] + registry["qualifier_words"],
                    registry,
                    objects_by_id,
                    event_item_ids,
                    item_ids,
                ),
            }
        )
    if len(frames) > 1 and assigned != set(objects_by_id):

        missing = sorted(set(objects_by_id) - assigned)
        for object_id in missing:
            obj = objects_by_id[object_id]
            name = obj["name"]
            label = name.decode("latin-1") if isinstance(name, bytes) else name

            why = (
                "its every placement anywhere is a Create or Shoot placeholder "
                "that no event row names, so no frame holds it as a member "
                "(see the frame losses above)"
                if object_id in placeholder_only_anywhere
                else "no placement, no event reference and no Shoot parent "
                "word anywhere in the package"
            )
            losses.append(
                f"runtime object {object_id} {label!r} (type "
                f"{obj['object_type']}) is claimed by no frame -- {why}; the "
                "editor object list of a frame is exactly the objects placed "
                "in it, so this object was in none of them and it is dropped"
            )
        objects = [obj for obj in objects if obj["object_id"] in assigned]
        objects_by_id = {obj["object_id"]: obj for obj in objects}
    has_image_bank = bool(present & IMAGE_BANK_CHUNKS)
    images = runtime_images(exe, losses) if has_image_bank else []
    if has_image_bank and not images:

        raise Unsupported(
            "the package carries an image bank "
            f"({sorted(hex(c) for c in present & IMAGE_BANK_CHUNKS)}) and it "
            "decoded to 0 records"
        )

    unresolved_image = None
    sentinel_backdrops = [
        obj["object_id"]
        for obj in objects
        if obj["object_type"] == BACKDROP
        and len(obj["definition"]) == 10
        and struct.unpack_from("<H", obj["definition"], 8)[0]
        == UNRESOLVED_IMAGE_HANDLE
    ]
    if sentinel_backdrops:
        unresolved_image = max((handle for handle, _ in images), default=-1) + 1
        images = images + [
            (
                unresolved_image,
                blank_image_record(
                    target_image_mode(application["graphic_mode"])
                ),
            )
        ]
        many = len(sentinel_backdrops) != 1
        losses.append(
            f"{len(sentinel_backdrops)} Backdrop{'s' if many else ''} "
            f"(runtime object{'s' if many else ''} "
            f"{', '.join(str(o) for o in sentinel_backdrops)}) "
            f"{'store' if many else 'stores'} image "
            f"handle {UNRESOLVED_IMAGE_HANDLE}, the compiler's marker for a "
            "reference that resolved to nothing; the runtime package holds no "
            f"artwork for it, so each is pointed at a new blank 1x1 image "
            f"(handle {unresolved_image}) -- the object survives, its picture "
            "does not"
        )
    return application | {
        "global_values": runtime_global_values_15(outer),
        "global_events": global_events,
        "global_event_sheet": global_sheet,
        "global_event_registry": global_event_registry,
        "frames": frame_summaries,
        "objects": objects,
        "placements": [
            placement
            for frame in frame_summaries
            for placement in frame["placements"]
        ],
        "fonts": runtime_font_bank(exe) if present & FONT_BANK_CHUNKS else [],
        "sample_bank": (
            runtime_sample_bank(exe)[0]
            if 0x6668 in present
            else b"APMS\x00\x00\x00\x00"
        ),
        "music_bank": (
            runtime_music_bank(exe)[0]
            if 0x6669 in present
            else b"ASUM\x00\x00\x00\x00"
        ),
        "images": images,
        "unresolved_image": unresolved_image,
        "event_count": sum(frame["event_count"] for frame in frame_summaries),
        "extension_modules": module_by_slot,

        "frame_passwords": [
            (index, frame["password"].partition(b"\x00")[0].decode("latin-1"))
            for index, frame in enumerate(frame_summaries)
            if frame["password"]
        ],

        "recovered_comments": recovered_comments,

        "losses": losses,

        "repairs": repairs,
    }

def set_scalar(block, tag: str, value: int) -> None:
    """Write a plain numeric property by name."""
    set_indexed_scalar(block, tag, 0, value)

GLOBAL_VALUE_CHUNK = 0x2232

GLOBAL_EVENT_PLAIN_STATE = 0x00

GLOBAL_EVENT_GROUPED_FIRST_HANDLE = 2

GLOBAL_EVENT_REGISTRY_STATE = 0x10

def global_event_object_map(sheet: list[bytes] | None) -> dict[int, int]:
    """Which objects the global event sheet refers to, in first-seen order."""
    if not sheet:
        return {}
    seen: dict[int, int] = {}
    for event in sheet:
        for _source, _expected, word in event_object_slots(event):
            if word not in seen:
                seen[word] = len(seen)
    return seen

def global_event_registry_15(
    sheet: list[bytes] | None,
    objects_by_id: dict[int, dict],
) -> list[dict]:
    """The object list a global event sheet carries alongside its rows.

    Global events live outside any one frame, so they cannot name objects the way
    a frame's events do: the sheet ships its own small directory of what it talks
    about, and this rebuilds it from the rows themselves.
    """
    object_map = global_event_object_map(sheet)
    if not object_map:
        return []
    references = set(object_map)
    qualifiers = sorted(word for word in references if word & QUALIFIER_FLAG)
    if qualifiers:
        raise Unsupported(
            f"the global event sheet references qualifiers {qualifiers}; a "
            "qualifier entry has never been observed in this registry, so "
            "there is no known correct way to write one"
        )
    missing = sorted(word for word in references if word not in objects_by_id)
    if missing:
        raise Unsupported(
            f"the global event sheet references objects {missing}, which are "
            "not in the runtime object table"
        )
    entries = []
    for compiled_id, event_id in sorted(object_map.items()):
        obj = objects_by_id[compiled_id]
        entries.append(
            {
                "event_id": event_id,

                "object_id": compiled_id,
                "object_type": obj["object_type"],
                "name": obj["name"],
                "type_name": event_object_type_string(obj),
            }
        )
    return entries

def global_event_payload_15(
    sheet: list[bytes] | None,
    registry: list[dict],
) -> bytes | None:
    """The finished global event sheet, ready to be stored on the application.
    """
    if not sheet:
        return None
    if registry and any("icon" not in entry for entry in registry):
        raise Unsupported(
            "the global event sheet's SJBO registry has no editor icon; the "
            "payload cannot be built before the icon bank is cloned"
        )
    grouped = any(
        len(event) >= 18 and event[16:18] == GROUP_OPEN_MARKER for event in sheet
    )
    editor = compiled_events_to_editor_events(
        sheet,
        object_id_map=global_event_object_map(sheet) or None,
        first_handle=GLOBAL_EVENT_GROUPED_FIRST_HANDLE if grouped else 1,

        object_types={
            entry["object_id"]: entry["object_type"]
            for entry in (registry or ())
            if "object_id" in entry
        }
        or None,
    )
    return build_global_event_property(
        editor,
        registry=registry or None,
        plain_state=(
            GLOBAL_EVENT_REGISTRY_STATE if registry else GLOBAL_EVENT_PLAIN_STATE
        ),
    )

def runtime_global_values_15(outer: list) -> list[int]:
    """The application's Global Values, with their starting numbers."""
    chunk = next((c for c in outer if c.chunk_id == GLOBAL_VALUE_CHUNK), None)
    if chunk is None:
        return []
    payload = decompress_chunk(chunk)
    if len(payload) < 2:
        raise Unsupported("the runtime Global Values chunk is truncated")
    (count,) = struct.unpack_from("<H", payload, 0)
    if len(payload) != 2 + count * 5:
        raise Unsupported(
            f"unexpected Global Values size {len(payload)} for {count} values"
        )
    values = list(struct.unpack_from(f"<{count}i", payload, 2))
    for index, flag in enumerate(payload[2 + count * 4 :]):
        if flag != 0:
            raise Unsupported(
                f"unsupported Global Value flag {flag} at index {index}"
            )
    return values

def global_values_payload(values: list[int]) -> bytes:
    """Write the Global Values back in the form the editor reads.

    **The names are regenerated, not recovered.** Compilation keeps each value's
    number and drops the label the author typed, so the values are re-labelled in
    order — the data is exact, the naming is ours.
    """
    names = [
        f"Global Value {chr(ord('A') + index)}".encode("latin-1")
        if index < 26
        else f"Global Value {index + 1}".encode("latin-1")
        for index in range(len(values))
    ]
    records = b"".join(
        global_value_record(
            index, name, value, name_marker=1 if len(values) == 1 else 0
        )
        for index, (name, value) in enumerate(zip(names, values))
    )
    return struct.pack("<I", len(values)) + records

def set_blob(block, tag: str, payload: bytes) -> None:
    """Replace a property's payload with a block of bytes."""
    prop = block.by_tag(tag)
    if prop is None:
        raise Unsupported(f"the scaffold's {block.name} has no {tag} property")
    entry = next((entry for entry in prop.entries if entry.index == 0), None)
    if entry is None:
        raise Unsupported(f"the scaffold's {block.name}.{tag} has no entry 0")
    entry.type_id = 0x0A
    entry.a = 1
    entry.b = 1
    entry.size = len(payload)
    entry.word = len(payload)
    entry.payload = payload

def set_indexed_scalar(block, tag: str, index: int, value: int) -> None:
    """Write one numbered slot of a multi-part numeric property.

    Several editor controls store as one property with numbered entries — a
    checkbox trio, an ink effect and its parameters — so the index is which
    control, not which object.
    """
    prop = block.by_tag(tag)
    if prop is None:
        raise Unsupported(f"the scaffold's {block.name} has no {tag} property")
    entry = next((entry for entry in prop.entries if entry.index == index), None)
    if entry is None:
        raise Unsupported(
            f"the scaffold's {block.name}.{tag} has no entry {index}"
        )
    if entry.type_id in (0x03, 0x04):
        raise Unsupported(
            f"{tag} entry {index} is type 0x{entry.type_id:02X}, not a scalar"
        )
    entry.size = 0
    entry.payload = b""
    entry.word = value

def set_frame_runtime_object_count(block, value: int) -> None:
    """Set how many objects a frame may hold at once, or leave it at the default.
    """
    prop = block.by_tag("NbO")
    if prop is None:
        raise Unsupported(f"the scaffold's {block.name} has no NbO property")
    marker = next((entry for entry in prop.entries if entry.index == 0), None)
    count = next((entry for entry in prop.entries if entry.index == 1), None)
    if marker is None or marker.type_id != 0x04:
        raise Unsupported(f"the scaffold's {block.name}.NbO marker is malformed")
    if count is None or count.type_id != 0x1E:
        raise Unsupported(f"the scaffold's {block.name}.NbO value is malformed")
    if value in (0, DEFAULT_RUNTIME_OBJECT_COUNT):
        for entry in (marker, count):
            entry.size = INHERITED
            entry.word = None
            entry.payload = b""
        return
    marker.size = 0
    marker.word = None
    marker.payload = b""
    count.size = 0
    count.word = value
    count.payload = b""

def set_blob(block, tag: str, payload: bytes, index: int = 0) -> None:
    """Replace a property's payload with a block of bytes."""
    prop = block.by_tag(tag)
    if prop is None:
        raise Unsupported(f"the scaffold's {block.name} has no {tag} property")
    entry = next((entry for entry in prop.entries if entry.index == index), None)
    if entry is None or entry.type_id != 0x0A:
        found = None if entry is None else f"0x{entry.type_id:02X}"
        raise Unsupported(
            f"the scaffold's {block.name}.{tag} entry {index} is {found}, "
            "not a type-0x0A blob"
        )
    entry.size = len(payload)
    entry.word = len(payload)
    entry.payload = payload

def write_transition_properties(block, transitions: dict[str, dict]) -> None:
    """Write a frame's fade-in and fade-out, or clear them if it has none."""
    for tag in ("FadI", "FadO"):
        prop = block.by_tag(tag)
        transition = transitions.get(tag)
        if prop is None:
            if transition is not None:
                raise Unsupported(
                    f"the scaffold's {block.name} has no {tag} property for "
                    f"runtime transition {transition['identifier']!r}"
                )
            continue
        if transition is None:
            set_scalar(block, tag, 0)
        else:
            set_blob(block, tag, transition_payload(transition))

def set_inherited(block, tag: str, index: int = 0) -> None:
    """Mark a property as taking the default rather than storing a value.

    An MMF project stores "unset" as its own state, distinct from storing a zero.
    Writing a value where the base project inherited one would change what the
    editor shows, so the distinction is preserved rather than flattened.
    """
    prop = block.by_tag(tag)
    if prop is None:
        raise Unsupported(f"the scaffold's {block.name} has no {tag} property")
    entry = next((entry for entry in prop.entries if entry.index == index), None)
    if entry is None:
        raise Unsupported(f"the scaffold's {block.name}.{tag} has no entry {index}")
    entry.size = INHERITED
    entry.word = None
    entry.payload = b""

def set_optional_blob(block, tag: str, payload: bytes | None) -> None:
    """Store a payload, or mark the property inherited when there is none."""
    if payload is None:
        set_inherited(block, tag)
    else:
        set_blob(block, tag, payload)

def set_application_about(block, name: bytes, author: bytes) -> None:
    """Write the application's name and author."""
    prop = block.by_tag("Abou")
    if prop is None:
        raise Unsupported(f"the scaffold's {block.name} has no Abou property")
    entries = {entry.index: entry for entry in prop.entries}
    if set(entries) != {0, 1, 2, 3}:
        raise Unsupported(
            f"the scaffold's {block.name}.Abou entries are {sorted(entries)}, "
            "not 0,1,2,3"
        )
    if entries[0].type_id != 0x04 or entries[1].type_id != 0x03:
        raise Unsupported(f"the scaffold's {block.name}.Abou name pair is malformed")
    if entries[2].type_id != 0x04 or entries[3].type_id != 0x03:
        raise Unsupported(f"the scaffold's {block.name}.Abou author pair is malformed")

    entries[0].size = 0
    entries[1].payload = name + b"\x00"
    entries[1].size = len(entries[1].payload)
    if author:
        entries[2].size = 0
        entries[3].payload = author + b"\x00"
        entries[3].size = len(entries[3].payload)
    else:
        for index in (2, 3):
            entries[index].size = INHERITED
            entries[index].word = None
            entries[index].payload = b""

def set_player_start(block, tag: str, value: int) -> None:
    """Write a starting score or starting lives."""
    prop = block.by_tag(tag)
    if prop is None:
        raise Unsupported(f"the scaffold's {block.name} has no {tag} property")
    marker = next((entry for entry in prop.entries if entry.index == 0), None)
    value_entry = next((entry for entry in prop.entries if entry.index == 1), None)
    if marker is None or marker.type_id != 0x04:
        raise Unsupported(f"the scaffold's {block.name}.{tag} marker is malformed")
    if value_entry is None or value_entry.type_id != 0x1E:
        raise Unsupported(f"the scaffold's {block.name}.{tag} value is malformed")
    marker.size = INHERITED
    marker.word = None
    marker.payload = b""
    value_entry.size = 0
    value_entry.word = value
    value_entry.payload = b""

def set_application_icon_customized(block) -> None:
    """Tell the project its application icons are the author's, not the defaults.
    """
    prop = block.by_tag("AppI")
    if prop is None:
        raise Unsupported(f"the scaffold's {block.name} has no AppI property")
    entries = {entry.index: entry for entry in prop.entries}
    if set(entries) != {0, 1, 2, 3}:
        raise Unsupported(
            f"the scaffold's {block.name}.AppI entries are {sorted(entries)}, "
            "not 0,1,2,3"
        )
    for index in (0, 2):
        entries[index].size = 0
        entries[index].word = None
        entries[index].payload = b""
    for index in (1, 3):
        entries[index].size = INHERITED
        entries[index].word = None
        entries[index].payload = b""

def write_application_properties(block, summary: dict, bank_mode: int) -> None:
    """Write every application-wide setting into the project at once.

    The one place the application's own dialogs are filled in, so what the editor
    shows under Application Properties is exactly what the game carried. A global
    event sheet that has lost its object directory stops here rather than being
    written with the base project's — an inherited sheet would be a different
    program.
    """
    set_application_about(block, summary["name"], summary["author"])
    set_scalar(block, "RunO", summary["run_options"])
    set_scalar(block, "WinO", summary["window_options"])
    set_scalar(block, "WinS", summary["window_size"])
    set_scalar(block, "AppM", IMAGE_MODE_TO_COLOR_DEPTH[bank_mode])
    set_scalar(block, "Colo", summary["app_colour"])
    set_optional_blob(block, "Menu", summary["menu"])
    set_optional_blob(block, "Hlpf", summary["help_file"])
    set_player_start(block, "Scor", summary["starting_score"])
    set_player_start(block, "Live", summary["starting_lives"])
    if summary.get("application_icons_customized"):
        set_application_icon_customized(block)
    if summary["global_values"]:
        set_blob(block, "GloV", global_values_payload(summary["global_values"]))
    else:
        set_inherited(block, "GloV")
    if summary["global_events"]:
        set_blob(block, "GEvt", summary["global_events"])
    elif summary.get("global_event_registry"):

        raise Unsupported(
            "the global event sheet needs an SJBO registry that was never "
            "built; its payload would be inherited from the scaffold"
        )
    else:
        set_inherited(block, "GEvt")

def runtime_alterable_values_15(definition: bytes) -> list[int]:
    """An Active object's alterable values, as the game left them."""
    if len(definition) < 0x28:
        return []
    offset = struct.unpack_from("<H", definition, 0x26)[0]
    if offset == 0:
        return []
    if offset + 2 > len(definition):
        raise Unsupported("alterable-value table points outside object definition")
    count = struct.unpack_from("<H", definition, offset)[0]
    if count > 26:
        raise Unsupported(f"alterable-value table has {count} entries; maximum is 26")
    end = offset + 2 + 4 * count
    if end > len(definition):
        raise Unsupported("alterable-value table is truncated")
    return list(struct.unpack_from(f"<{count}i", definition, offset + 2))

def merge_owned_qualifiers(
    registry: dict, member_object_ids: list[int], objects_by_id: dict[int, dict]
) -> dict:
    """Add the qualifiers an object actually carries to a page's object directory.

    A qualifier is a group an object belongs to, and events can address the group
    instead of the object. The compiled page names only the groups its rows used,
    so the groups its objects declare are folded back in — otherwise the editor
    would show a page addressing a qualifier it does not list.
    """
    owned: set[int] = set()
    for object_id in member_object_ids:
        payload = runtime_qualifiers(objects_by_id[object_id]["definition"])
        if not payload:
            continue
        owned.update(QUALIFIER_FLAG | index for index in qualifier_indices(payload))
    words = sorted(set(registry["qualifier_words"]) | owned)
    if words == registry["qualifier_words"]:
        return registry
    object_id_map = {
        key: value
        for key, value in registry["object_id_map"].items()
        if not key & QUALIFIER_FLAG
    }
    for word in words:
        object_id_map[word] = len(object_id_map)
    return registry | {"qualifier_words": words, "object_id_map": object_id_map}

def runtime_qualifiers_15(definition: bytes) -> bytes:
    """The qualifier groups one object belongs to."""
    payload = runtime_qualifiers(definition)
    if not payload:
        return b""
    words = struct.unpack("<9H", payload)
    if 0xFFFF in words[:-1] and words[-1] == 0:
        return payload[:16]
    return payload

def editor_alterable_values(values: list[int]) -> bytes:
    """Write an object's alterable values in the form the editor reads.

    As with Global Values, the numbers are exact and the labels are regenerated:
    compilation does not keep the names the author typed.
    """
    records = []
    for index, value in enumerate(values):
        name = f"Value{chr(ord('A') + index)}".encode("ascii")
        name_field = name + b"\x00" * (34 - len(name))
        records.append(struct.pack("<HHH", 0, 44, index) + name_field + struct.pack("<i", value))
    return struct.pack("<I", len(records)) + b"".join(records)

def set_string(block, tag: str, text: bytes) -> None:
    """Write a text property, terminated the way the format expects."""
    set_string_payload(block, tag, text + b"\x00")

def set_string_payload(block, tag: str, payload: bytes) -> None:
    """Write text into a property that stores it as a marker and a buffer."""
    prop = block.by_tag(tag)
    if prop is None:
        raise Unsupported(f"the scaffold's {block.name} has no {tag} property")
    wrote = False
    for entry in prop.entries:
        if entry.type_id == 0x04 and not wrote:
            entry.size = 0
        elif entry.type_id == 0x03 and not wrote:
            entry.payload = payload
            entry.size = len(entry.payload)
            wrote = True
    if not wrote:
        raise Unsupported(f"{block.name}.{tag} has no type-0x03 string entry")

def set_frame_password(block, password: bytes | None) -> None:
    """Put a frame's password back, or leave the frame unprotected."""
    prop = block.by_tag("Pass")
    if prop is None:
        raise Unsupported(f"the scaffold's {block.name} has no Pass property")
    if not password:
        for entry in prop.entries:
            if entry.type_id in (0x03, 0x04):
                entry.size = INHERITED
                entry.payload = b""
        return
    if password.count(b"\x00") != 1 or not password.endswith(b"\x00"):
        raise Unsupported(
            f"frame password {password!r} is not one NUL-terminated buffer"
        )
    set_string_payload(block, "Pass", password)

def frame_password_of(block) -> bytes | None:
    """Read back the password a rebuilt frame stores — used to check the rebuild.
    """
    prop = block.by_tag("Pass")
    if prop is None:
        return None
    text = next((e for e in prop.entries if e.type_id == 0x03), None)
    if text is None or text.inherited:
        return None
    return text.payload

def set_object_name(block, text: bytes) -> None:
    """Write the name the editor shows for an object."""
    prop = block.by_tag("ItNa")
    if prop is None:
        raise Unsupported(f"the scaffold's {block.name} has no ItNa property")
    entry = next((entry for entry in prop.entries if entry.type_id == 0x03), None)
    if entry is None:
        raise Unsupported(f"{block.name}.ItNa has no type-0x03 string entry")
    entry.payload = text + b"\x00"
    entry.size = len(entry.payload)

def palette_span_payload(data: bytes, span, runtime_palette: bytes) -> bytes:
    """Put the game's own 256 colours into the project's palette region.

    The region's short header belongs to the project and is kept; only the
    colours themselves come from the game.
    """
    header, entries = 4, 1024
    if len(runtime_palette) != header + entries:
        raise Unsupported(
            f"runtime palette is {len(runtime_palette)} bytes, expected "
            f"{header + entries}"
        )

    if len(span) != 4 + header + entries:
        raise Unsupported(f"scaffold palette span is {len(span)} bytes")
    keep = data[span.start:span.start + 4 + header]
    return keep + runtime_palette[header:]

def rebuild(
    data: bytes, replacements: dict[str, bytes], parts: list | None = None
) -> bytes:
    """Reassemble the container from its spans after they have been patched."""
    if parts is None:
        parts = sorted(spans(data), key=lambda span: (span.start, span.end))
    elif os.environ.get("MMF15_SPANS_CROSSCHECK"):
        fresh = sorted(spans(data), key=lambda span: (span.start, span.end))
        if fresh != sorted(parts, key=lambda span: (span.start, span.end)):
            raise ContainerProblem(
                "span maintenance drift: the reused span list does not match "
                "a fresh walk of the file being rebuilt"
            )
    unknown = set(replacements) - {span.name for span in parts}
    if unknown:
        raise Unsupported(f"no such span in the scaffold: {sorted(unknown)}")
    out = bytearray()
    cursor = 0
    for span in parts:
        if span.start < cursor:
            continue
        if span.start != cursor:
            raise ContainerProblem(
                f"gap of {span.start - cursor} bytes before {span.name}"
            )
        out += replacements.get(span.name, data[span.start:span.end])
        cursor = span.end
    if cursor != len(data):
        raise ContainerProblem(f"{len(data) - cursor} bytes past the last span")
    return bytes(out)

class SpanLedger:
    """Tracks which regions of the container have been replaced, and with what.

    Building a project replaces around thirty named regions, one after another.
    Walking the whole file again after each replacement is the obviously correct
    way to keep track of where everything now is, and on a large game that walk
    costs more than all the work it is bookkeeping for. So the file is walked
    once, and each replacement updates the table by arithmetic instead: the
    region that changed takes its new length, and everything after it shifts by
    the difference.

    That shortcut is sound because of what each replacement actually is — one
    named region swapped for a well-formed region of the same name — and because
    none of the readers in the walk look backwards across a region boundary.
    Together those two facts make the shifted table the same table a fresh walk
    would produce, rather than merely a table that has worked so far.

    Sound is not the same as proven, so the ledger can be asked to prove it: with
    the cross-check turned on, every change is followed by a complete fresh walk
    and the *whole* table compared, not just the entries anyone thought to
    suspect. The project's own test runs turn it on. Regardless of the setting,
    the finished file is walked again from scratch before anything is written.

    Two checks are always on, because they catch a drifted table rather than
    merely disagreeing with one. A block that no longer ends where the table says
    it does refuses by name. So does a rebuild whose regions overlap or leave a
    gap between them. A table that has drifted from the file does not fail
    loudly on its own — it writes correct bytes into the wrong place.
    """

    __slots__ = ("ordered", "parts")

    def __init__(self, data: bytes):
        self.ordered = sorted(spans(data), key=lambda span: (span.start, span.end))
        self.parts = {span.name: span for span in self.ordered}

    def crosscheck(self, data: bytes) -> None:
        """Confirm the tracked regions still match a fresh reading of the file.

        A safety net, off unless asked for: it catches a region table that has drifted
        out of step with the bytes it describes, which would otherwise show up much
        later as a corrupt project.
        """
        if not os.environ.get("MMF15_SPANS_CROSSCHECK"):
            return
        fresh = sorted(spans(data), key=lambda span: (span.start, span.end))
        if fresh != self.ordered:
            held = {span.name: span for span in self.ordered}
            fresh_by_name = {span.name: span for span in fresh}
            for name in sorted(set(held) | set(fresh_by_name)):
                if held.get(name) != fresh_by_name.get(name):
                    raise ContainerProblem(
                        f"span maintenance drift at {name}: kept "
                        f"{held.get(name)}, a fresh walk says "
                        f"{fresh_by_name.get(name)}"
                    )
            raise ContainerProblem(
                "span maintenance drift: same entries, different order"
            )

    def _shift(self, span, delta: int) -> None:
        if not delta:
            return
        boundary = span.end
        span.end += delta
        for other in self.ordered:
            if other is not span and other.start >= boundary:
                other.start += delta
                other.end += delta

    def splice(self, data: bytes, name: str, payload: bytes) -> bytes:
        """Replace one named region and move everything after it by the size difference.
        """
        span = self.parts[name]
        out = data[:span.start] + payload + data[span.end:]
        self._shift(span, len(payload) - len(span))
        self.crosscheck(out)
        return out

    def pack_block(self, data: bytes, name: str, patch) -> bytes:
        """Re-serialise one record after a change, checking it ends where it should.
        """
        span = self.parts[name]
        block, end = read_class_block(data, span.start)
        if end != span.end:
            raise ContainerProblem(
                f"span table drift at {name}: the class block ends at "
                f"0x{end:X}, the table says 0x{span.end:X}"
            )
        patch(block)
        return block.pack()

    def patch_block(self, data: bytes, name: str, patch) -> bytes:
        """Change a record in place: read it, edit it, write it back."""
        return self.splice(data, name, self.pack_block(data, name, patch))

    def rebuild(self, data: bytes, replacements: dict[str, bytes]) -> bytes:
        """Write several regions at once and update where every region now lives.

        Nothing may overlap and nothing may be left out — a gap or an overlap means
        the map of the file no longer describes the file, and that is refused rather
        than written.
        """
        unknown = set(replacements) - set(self.parts)
        if unknown:
            raise Unsupported(f"no such span in the scaffold: {sorted(unknown)}")
        out = bytearray()
        cursor = 0
        delta = 0
        moves = []
        for span in self.ordered:
            if span.start < cursor:

                raise ContainerProblem(
                    f"span {span.name} overlaps the span before it; the "
                    f"ledger cannot maintain an overlapped table"
                )
            if span.start != cursor:
                raise ContainerProblem(
                    f"gap of {span.start - cursor} bytes before {span.name}"
                )
            payload = replacements.get(span.name)
            new_start = span.start + delta
            if payload is None:
                out += data[span.start:span.end]
                new_end = span.end + delta
            else:
                out += payload
                new_end = new_start + len(payload)
                delta += len(payload) - len(span)
            moves.append((span, new_start, new_end))
            cursor = span.end
        if cursor != len(data):
            raise ContainerProblem(
                f"{len(data) - cursor} bytes past the last span"
            )
        for span, new_start, new_end in moves:
            span.start = new_start
            span.end = new_end
        result = bytes(out)
        self.crosscheck(result)
        return result

def generated_object_icon_15(
    obj: dict,
    images_by_id: dict[int, bytes],
    palette: bytes,
    unresolved_image: int | None,
    fallbacks: list,
) -> bytes:
    """Draw one object's editor icon from the picture that object itself uses.

    An Active takes the first frame of its own animation, a Backdrop its own
    image, a Counter its own digits or bar. Nothing is copied from MMF: where an
    object has no picture to draw from — a timer, a sound, an extension — the
    icon comes from this project's own artwork folder, and where an object's
    picture cannot be read the same neutral drawing stands in and the reason is
    recorded.
    """
    object_type = obj["object_type"]
    try:
        if object_type == ACTIVE:
            image_id = None
            for animation in runtime_animations(obj["definition"]):
                for direction in animation["directions"]:
                    if direction["image_ids"]:
                        image_id = direction["image_ids"][0]
                        break
                if image_id is not None:
                    break
            if image_id is None or image_id not in images_by_id:
                raise ValueError("no animation image to derive the icon from")
            return icon_from_image_15(
                images_by_id[image_id], palette, 0, ACTIVE_ICON_CONTENT_15
            )[4:]
        if object_type == BACKDROP:
            image = struct.unpack_from("<H", obj["definition"], 8)[0]
            if image == UNRESOLVED_IMAGE_HANDLE and unresolved_image is not None:
                image = unresolved_image
            if image not in images_by_id:
                raise ValueError(f"Backdrop image {image} is not in the bank")
            return icon_from_image_15(
                images_by_id[image], palette, 0, BACKDROP_ICON_CONTENT_15
            )[4:]
        if object_type == QUICK_BACKDROP:
            payload = quick_backdrop_payload(obj["definition"])
            return quick_backdrop_icon_15(payload, palette, 0, images_by_id)[4:]
        if object_type in (COUNTER, LIVES, SCORE):

            if (
                len(obj["definition"]) >= 0x10
                and struct.unpack_from("<I", obj["definition"], 0x0C)[0]
            ):
                payload = counter_family_payload(obj["definition"])
                image_ids = [
                    image_id
                    for image_id in payload["image_ids"]
                    if image_id in images_by_id
                ]
                if image_ids:
                    return icon_from_image_15(
                        images_by_id[image_ids[0]], palette, 0,
                        OTHER_ICON_CONTENT_15,
                    )[4:]
                if payload.get("bar_fill") is not None:
                    return quick_backdrop_icon_15(
                        payload["bar_fill"], palette, 0, images_by_id,
                        payload["width"], payload["height"],
                        RENDER_ICON_CONTENT_15,
                    )[4:]
    except (ValueError, KeyError, struct.error) as problem:
        fallbacks.append(
            {
                "object_id": obj.get("object_id"),
                "object_type": object_type,
                "reason": str(problem),
            }
        )
        return artwork_icon_record_15(OTHER_ICON_ART, 0)[4:]
    return artwork_icon_record_15(imageless_icon_art(object_type), 0)[4:]

def generate_object_icons(
    data: bytes, summary: dict, alias: bool = False,
    ledger: SpanLedger | None = None,
) -> tuple[bytes, list[int], dict[int, int]]:
    """Draw each object's editor icon from that object's own artwork.

    The small picture the editor shows beside an object in its lists. Every one is
    **drawn from that object's own recovered art** — no icon pixels come from
    anywhere else, which is the point as much as the result. An object whose art
    could not be recovered gets a described stand-in, and that is recorded as a
    fallback so the run can say which objects it happened to rather than leaving
    the reader to spot the difference by eye.

    The icons are added to the project's image bank under fresh handles, in the
    same frame-by-frame order the record builders consume them, so an object and
    its icon cannot drift apart.

    Aliasing is optional and worth explaining. Many objects produce byte-identical
    icons, and the editor's own files store one copy and point several objects at
    it. Turning aliasing on reproduces that, which makes the rebuilt file closer
    to what the editor would have written; leaving it off gives every object its
    own record. Both are correct, and the difference is only in how the file is
    laid out.
    """
    header, records, order = editor_bank(
        data, 1, ledger.parts if ledger is not None else None
    )
    images_by_id = dict(summary["images"])
    frame_palette = (
        summary["frames"][0]["palette"] if summary["frames"] else None
    )
    palette = (
        bank_palette(frame_palette[4:])
        if frame_palette is not None
        else bytes(header[12:12 + 1024])
    )
    fallbacks = summary.setdefault("generated_icon_fallbacks", [])
    next_handle = max(order) + 1 if order else 0
    extra: list[tuple[int, bytes]] = []
    icons: list[int] = []
    handle_by_object: dict[int, int] = {}
    dedupe: dict[bytes, int] = {}
    for frame in summary["frames"]:
        for obj in frame["objects"]:
            record = generated_object_icon_15(
                obj, images_by_id, palette,
                summary.get("unresolved_image"), fallbacks,
            )
            if alias:
                known = dedupe.get(record)
                if known is not None:
                    icons.append(known)
                    handle_by_object.setdefault(obj["object_id"], known)
                    continue
                dedupe[record] = next_handle
            extra.append((next_handle, record))
            icons.append(next_handle)
            handle_by_object.setdefault(obj["object_id"], next_handle)
            next_handle += 1
    bank = build_bank(
        header, [(handle, records[handle]) for handle in order] + extra
    )
    if ledger is not None:
        return ledger.rebuild(data, {"AGMI-1": bank}), icons, handle_by_object
    return rebuild(data, {"AGMI-1": bank}), icons, handle_by_object

def replace_frame_previews(
    data: bytes, summary: dict, ledger: SpanLedger | None = None
) -> bytes:
    """Render each frame's thumbnail from that frame's own background."""
    header, records, order = editor_bank(
        data, 1, ledger.parts if ledger is not None else None
    )
    previews = [
        handle
        for handle in order
        if len(records[handle]) >= 14
        and struct.unpack_from("<HH", records[handle], 10) == (64, 48)
    ]
    frames = summary["frames"]
    replaced = dict(records)
    for index, handle in enumerate(previews):
        background = (
            frames[index]["background"]
            if index < len(frames) and frames[index].get("background") is not None
            else 0x00FFFFFF
        )
        replaced[handle] = frame_preview_record(handle, background)[4:]
    bank = build_bank(header, [(handle, replaced[handle]) for handle in order])
    if ledger is not None:
        return ledger.rebuild(data, {"AGMI-1": bank})
    return rebuild(data, {"AGMI-1": bank})

APPLICATION_ICON_BANK_ORDER = (3, 4, 2, 1)

APPLICATION_ICON_QUEUE_ORDER = (3, 4, 1, 2)

APPLICATION_ICON_SIZES = {(32, 32), (16, 16)}

DEFAULT_APPLICATION_ICON_SHA256 = {
    1: "06fcf5ef7744e8ac911b5f4f709183c273c2cff3830127ea8a40fe951049cdde",
    2: "b3dab150b6eb71e803799bd413bfd9fccfbf9be0053ab5f65fbeb7cc3585dc0f",
    3: "2e2cc6e390a7d3f6109c4d1cf805694b08fa768343a9c0b2cfc71fcdb31097f6",
    4: "b289ea5bf4691d66ddde0b85a660cc934bc8daab42414e89a246567b61e7a643",
}

def application_icon_pixels(resource: bytes, editor_palette: bytes) -> tuple[int, int, bytes]:
    """Convert one Windows icon into the editor's own palette and layout.

    The icon's transparent pixels become the editor's transparent index, and a
    pixel that was genuinely black is moved to the nearest opaque black so it
    does not disappear into transparency.
    """
    if len(resource) < 40 or len(editor_palette) != 1024:
        raise Unsupported("application icon DIB or editor palette is truncated")
    header_size, width, doubled_height, planes, bits = struct.unpack_from(
        "<IiiHH", resource, 0
    )
    compression = struct.unpack_from("<I", resource, 16)[0]
    if (
        header_size != 40
        or width <= 0
        or doubled_height <= 0
        or doubled_height % 2
        or planes != 1
        or bits not in (4, 8)
        or compression != 0
    ):
        raise Unsupported(
            "application icon is not a bottom-up 4/8-bit BITMAPINFOHEADER DIB"
        )
    height = doubled_height // 2
    palette_entries = 1 << bits
    colour_stride = ((width * bits + 31) // 32) * 4
    mask_stride = ((width + 31) // 32) * 4
    colour_start = 40 + palette_entries * 4
    mask_start = colour_start + colour_stride * height
    if mask_start + mask_stride * height != len(resource):
        raise Unsupported(
            f"application icon {width}x{height}x{bits} has unexpected "
            f"length {len(resource)}"
        )

    palette_colours = [
        editor_palette[pos:pos + 3] for pos in range(0, len(editor_palette), 4)
    ]
    opaque_black = min(
        range(1, len(palette_colours)),
        key=lambda index: sum(palette_colours[index]),
    )
    pixels = bytearray()
    for row in range(height - 1, -1, -1):
        packed = resource[
            colour_start + row * colour_stride:
            colour_start + (row + 1) * colour_stride
        ]
        if bits == 8:
            indices = list(packed[:width])
        else:
            indices = []
            for value in packed:
                indices.extend((value >> 4, value & 0x0F))
            indices = indices[:width]
        mask = resource[
            mask_start + row * mask_stride:mask_start + (row + 1) * mask_stride
        ]
        for column, index in enumerate(indices):
            transparent = (mask[column // 8] >> (7 - column % 8)) & 1
            editor_index = index if bits == 8 or index < 8 else index + 240
            if transparent:
                editor_index = 0
            elif editor_index == 0:
                editor_index = opaque_black
            pixels.append(editor_index)
    return width, height, bytes(pixels)

def application_icon_record(resource: bytes, template: bytes, palette: bytes) -> bytes:
    """Store a converted Windows icon as an editor image record."""
    width, height, pixels = application_icon_pixels(resource, palette)
    if len(template) < 24 or struct.unpack_from("<HH", template, 10) != (width, height):
        raise Unsupported(
            f"no {width}x{height} editor application-icon template is available"
        )
    encoded = rle_encode_pixels([bytes((pixel,)) for pixel in pixels])
    record = bytearray(template[:24])
    struct.pack_into("<I", record, 6, len(encoded))
    struct.pack_into("<HH", record, 10, width, height)
    record[14] = 3
    record[15] = 1
    record.extend(encoded)
    return bytes(record)

def application_icons_match_existing(
    data: bytes, resources: dict[int, bytes],
    ledger: SpanLedger | None = None,
) -> bool:
    """Whether the project already shows the icons this game carries.

    Asked first so that a game using the standard Windows icons is left alone
    rather than rewritten to say the same thing.
    """
    if set(resources) != set(EXPECTED_ICONS):
        return False
    header, records, _order = editor_bank(
        data, 1, ledger.parts if ledger is not None else None
    )
    queue = data.rfind(b"icnQ")
    if queue < 0 or queue + 8 > len(data):
        return False
    (count,) = struct.unpack_from("<I", data, queue + 4)
    if count != len(APPLICATION_ICON_QUEUE_ORDER):
        return False
    handles = []
    for index in range(count):
        entry = queue + 8 + index * 8
        if data[entry:entry + 4] != b"Imag":
            return False
        handles.append(struct.unpack_from("<I", data, entry + 4)[0])
    palette = header[12:12 + 1024]
    matches = []
    for handle, resource_id in zip(handles, APPLICATION_ICON_QUEUE_ORDER):
        record = records.get(handle)
        if record is None:
            return False
        _width, _height, pixels = application_icon_pixels(
            resources[resource_id], palette
        )
        matches.append(
            decode_editor_icon(struct.pack("<I", handle) + record) == pixels
        )
    if all(matches):
        return True

    default_resources = all(
        hashlib.sha256(resources[resource_id]).hexdigest()
        == DEFAULT_APPLICATION_ICON_SHA256[resource_id]
        for resource_id in EXPECTED_ICONS
    )
    default_aliases = handles[0] == handles[2] and handles[1] == handles[3]
    return default_resources and default_aliases and matches[:2] == [True, True]

def application_icons_are_default(resources: dict[int, bytes]) -> bool:
    """Whether these are the unmodified icons the runtime ships with."""
    return set(resources) == set(EXPECTED_ICONS) and all(
        hashlib.sha256(resources[resource_id]).hexdigest()
        == DEFAULT_APPLICATION_ICON_SHA256[resource_id]
        for resource_id in EXPECTED_ICONS
    )

def write_default_application_icons(
    data: bytes, resources: dict[int, bytes],
    ledger: SpanLedger | None = None,
) -> bytes:
    """Write the standard icon pair into a project that expects them.

    The state a project is in when nobody has changed its application icon: two
    stored records, with the four icon slots pointing at them in pairs rather than
    each having a copy of its own.

    That aliasing is preserved deliberately, and it is not tidiness. Giving all
    four slots their own copy of the same pixels is a valid-looking file that can
    make the editor exit outright on a large project. So the shape stays as the
    editor writes it, and only the pixels change — taken from the game's own
    executable, which is what lets the base project ship with placeholder records
    instead of somebody's real icons.

    Like the custom path, this repoints the queue at the end of the file as well
    as replacing the pixels, and refuses a queue that is not the length or the
    shape it expects rather than writing into it blind.
    """
    header, records, order = editor_bank(
        data, 1, ledger.parts if ledger is not None else None
    )
    prefix = []
    for handle in order:
        record = records[handle]
        if len(record) < 14 or struct.unpack_from(
            "<HH", record, 10
        ) not in APPLICATION_ICON_SIZES:
            break
        prefix.append(handle)
    if len(prefix) < 2 or [
        struct.unpack_from("<HH", records[handle], 10) for handle in prefix[:2]
    ] != [(32, 32), (16, 16)]:
        raise Unsupported(
            "scaffold lacks the canonical leading 32x32/16x16 app icons"
        )
    palette = header[12:12 + 1024]
    replaced = dict(records)
    replaced[prefix[0]] = application_icon_record(
        resources[3], records[prefix[0]], palette
    )
    replaced[prefix[1]] = application_icon_record(
        resources[4], records[prefix[1]], palette
    )
    bank = build_bank(header, [(handle, replaced[handle]) for handle in order])
    if ledger is not None:
        rebuilt = ledger.rebuild(data, {"AGMI-1": bank})
    else:
        rebuilt = rebuild(data, {"AGMI-1": bank})
    queue = rebuilt.rfind(b"icnQ")
    if queue < 0 or queue + 8 > len(rebuilt):
        raise Unsupported("scaffold has no terminal application-icon queue")
    (count,) = struct.unpack_from("<I", rebuilt, queue + 4)
    if count != len(APPLICATION_ICON_QUEUE_ORDER):
        raise Unsupported(
            f"application-icon queue has {count} entries, expected "
            f"{len(APPLICATION_ICON_QUEUE_ORDER)}"
        )
    aliased = (prefix[0], prefix[1], prefix[0], prefix[1])
    output = bytearray(rebuilt)
    for index, handle in enumerate(aliased):
        entry = queue + 8 + index * 8
        if output[entry:entry + 4] != b"Imag":
            raise Unsupported("application-icon queue contains a non-Imag entry")
        struct.pack_into("<I", output, entry + 4, handle)
    result = bytes(output)
    if ledger is not None:

        ledger.crosscheck(result)
    return result

def replace_application_icons(
    data: bytes, resources: dict[int, bytes],
    ledger: SpanLedger | None = None,
) -> bytes:
    """Put the game's own Windows icons back into the project.

    A project keeps its application icons at the very front of the image bank, in
    a run of the two sizes Windows uses. That run is found by reading forwards
    until a record turns up that is not one of those sizes — a frame preview or an
    object's icon — rather than by assuming a count, since how many are there
    depends on what the project was last saved with.

    The four icons the game carries are then written over that run, reusing the
    handles already there and allocating fresh ones where the project has fewer
    records than it needs. Handles are the editor's own allocator numbers, so a
    new one only has to avoid colliding with an existing one.

    The other half of the job is the queue at the end of the file, which is what
    actually says *which* stored record serves as *which* icon. Writing the pixels
    without repointing the queue leaves a project whose icons look untouched. The
    queue's entries are checked before being written, and a queue of the wrong
    length or holding an unexpected kind of entry refuses rather than being
    patched blind.
    """
    if set(resources) != set(EXPECTED_ICONS):
        raise Unsupported(
            f"application PE icon ids are {sorted(resources)}, expected "
            f"{sorted(EXPECTED_ICONS)}"
        )
    header, records, order = editor_bank(
        data, 1, ledger.parts if ledger is not None else None
    )
    prefix = []
    for handle in order:
        record = records[handle]
        if len(record) < 14 or struct.unpack_from("<HH", record, 10) not in APPLICATION_ICON_SIZES:
            break
        prefix.append(handle)
    if len(prefix) < 2 or [struct.unpack_from("<HH", records[h], 10) for h in prefix[:2]] != [
        (32, 32),
        (16, 16),
    ]:
        raise Unsupported("scaffold lacks the canonical leading 32x32/16x16 app icons")
    templates = {
        struct.unpack_from("<HH", records[handle], 10): records[handle]
        for handle in prefix
    }
    next_handle = max(order) + 1 if order else 0
    handles = list(prefix[:4])
    while len(handles) < 4:
        handles.append(next_handle)
        next_handle += 1
    palette = header[12:12 + 1024]
    application_records = []
    handle_by_resource = {}
    for handle, resource_id in zip(handles, APPLICATION_ICON_BANK_ORDER):
        width, height, _depth = EXPECTED_ICONS[resource_id][1:]
        template = templates[(width, height)]
        handle_by_resource[resource_id] = handle
        application_records.append(
            (handle, application_icon_record(resources[resource_id], template, palette))
        )
    remaining = [(handle, records[handle]) for handle in order[len(prefix):]]
    bank = build_bank(header, application_records + remaining)
    if ledger is not None:
        rebuilt = ledger.rebuild(data, {"AGMI-1": bank})
    else:
        rebuilt = rebuild(data, {"AGMI-1": bank})
    queue = rebuilt.rfind(b"icnQ")
    if queue < 0 or queue + 8 > len(rebuilt):
        raise Unsupported("scaffold has no terminal application-icon queue")
    (count,) = struct.unpack_from("<I", rebuilt, queue + 4)
    if count != len(APPLICATION_ICON_QUEUE_ORDER):
        raise Unsupported(
            f"application-icon queue has {count} entries, expected "
            f"{len(APPLICATION_ICON_QUEUE_ORDER)}"
        )
    output = bytearray(rebuilt)
    for index, resource_id in enumerate(APPLICATION_ICON_QUEUE_ORDER):
        entry = queue + 8 + index * 8
        if output[entry:entry + 4] != b"Imag":
            raise Unsupported("application-icon queue contains a non-Imag entry")
        struct.pack_into("<I", output, entry + 4, handle_by_resource[resource_id])
    result = bytes(output)
    if ledger is not None:

        ledger.crosscheck(result)
    return result

def insert_frames(data: bytes, frame_count: int) -> bytes:
    """Grow the base project to the frame count the game actually has.

    The base project has one frame; the game may have fifty. A frame is a complete
    envelope in the file rather than an entry in a list, so the extra ones are made
    by cloning the base's own neutral frame. Nothing of the target is in them yet —
    every frame-specific field is patched in afterwards.

    Two things travel with a frame and both are handled here. Each frame owns a
    small preview thumbnail in the image bank, so one clone of the base project's
    own neutral thumbnail is added per new frame under a fresh handle; the preview
    is editor-only, so cloning a neutral one is the whole of what is needed.

    The second is a trap worth naming. The icon queue at the very end of the file
    sits *inside* the last frame's body when the file is parsed, but it belongs to
    the application, not to that frame. Real multi-frame projects carry it exactly
    once, at the end. Copying it into every cloned frame produces a file that is
    structurally plausible and that the editor rejects. So the clones are built
    from the body with that queue cut off, and only the final frame keeps it.

    It refuses rather than guessing: a base project that already has more than one
    frame, or one that does not carry exactly one preview of the expected size, is
    not something to grow.
    """
    parts = {span.name: span for span in spans(data)}
    existing = sum(1 for name in parts if name.endswith("-Fram"))
    if existing == frame_count:
        return data
    if existing != 1 or frame_count < 1:
        raise Unsupported(
            f"frame insertion grows a one-frame scaffold only; target has "
            f"{existing} frames and the package needs {frame_count}"
        )

    header, records, order = editor_bank(data, 1)
    thumbnails = [
        handle
        for handle in order
        if len(records[handle]) >= 14
        and struct.unpack_from("<HH", records[handle], 10) == (64, 48)
    ]
    if len(thumbnails) != 1:
        raise Unsupported(
            "one-frame scaffold must carry exactly one 64x48 frame preview; "
            f"found {len(thumbnails)}"
        )
    next_handle = max(order) + 1 if order else 0
    added = [
        (next_handle + index, records[thumbnails[0]])
        for index in range(frame_count - 1)
    ]
    bank = build_bank(
        header,
        [(handle, records[handle]) for handle in order] + added,
    )

    frame_start = parts["frame0-Fram"].start
    body = parts["frame0-body"]
    neutral_prefix = data[frame_start:body.start]
    neutral_body = data[body.start:body.end]
    page = read_event_page(neutral_body)
    pos = page["allocator_start"]
    if neutral_body[pos:pos + 4] != b"!DNE":
        raise Unsupported("neutral frame has no !DNE allocator")
    pos += 12
    for _ in range(2):
        (length,) = struct.unpack_from("<I", neutral_body, pos)
        pos += 4 + length
    pos += 4
    if neutral_body[pos:pos + 4] != b"icnQ":
        raise Unsupported("one-frame scaffold has no terminal icnQ queue")
    (icon_count,) = struct.unpack_from("<I", neutral_body, pos + 4)
    if pos + 8 + icon_count * 8 != len(neutral_body):
        raise Unsupported("terminal icnQ queue has an invalid length")
    body_without_terminal_queue = neutral_body[:pos]
    intermediate = neutral_prefix + body_without_terminal_queue
    final = neutral_prefix + neutral_body
    return rebuild(
        data,
        {
            "AGMI-1": bank,
            "FrmL": b"FrmL" + struct.pack("<I", frame_count),

            "frame0-body": body_without_terminal_queue
            + intermediate * (frame_count - 2)
            + final,
        },
    )

def encode_ansi_path(text: str) -> bytes:
    """Encode an output path the way MMF stores it, or explain why it cannot be.

    MMF keeps the project's own location as plain bytes in a Windows codepage,
    so a folder name outside every codepage on this machine has no representation
    in the file. That is refused with the fix stated — write somewhere the name
    can be spelled — rather than silently mangled.
    """
    for codec in ("latin-1", "mbcs"):
        try:
            return text.encode(codec)
        except (UnicodeEncodeError, LookupError):
            continue
    raise Unsupported(
        f"the output path {text!r} holds characters no ANSI codepage on this "
        f"machine can encode, and MMF stores the path as ANSI bytes; write the "
        f"reconstruction to a directory whose name is representable"
    )

def set_source_path(
    data: bytes, output: Path, ledger: SpanLedger | None = None
) -> bytes:
    """Record where the project is being written, as the editor expects."""
    parts = (
        ledger.parts
        if ledger is not None
        else {span.name: span for span in spans(data)}
    )
    state = parts["editor-state"]
    (length,) = struct.unpack_from("<I", data, state.start)
    path = encode_ansi_path(str(output.resolve()))
    payload = (
        struct.pack("<I", len(path))
        + path
        + data[state.start + 4 + length:state.end]
    )
    if ledger is not None:
        return ledger.splice(data, "editor-state", payload)
    return rebuild(data, {"editor-state": payload})

FRAME_EDITOR_WINDOW_CLASS = 60

def retarget_editor_state_frames(
    data: bytes, frame_item_ids: list[int],
    ledger: SpanLedger | None = None,
) -> tuple[bytes, list[str]]:
    """Point the project's saved editor windows at frames that exist.

    A project remembers which frames were open when it was last saved. A window
    left pointing at a frame this project does not have is moved to the first
    frame, and the change is reported: harmless, but not invisible.
    """
    parts = (
        ledger.parts
        if ledger is not None
        else {span.name: span for span in spans(data)}
    )
    state = parts["editor-state"]
    (length,) = struct.unpack_from("<I", data, state.start)
    tail_start = state.start + 4 + length
    count = (state.end - tail_start) // 4
    if count < 2 or not frame_item_ids:
        return data, []
    words = list(struct.unpack_from(f"<{count}i", data, tail_start))
    present = set(frame_item_ids)
    first = frame_item_ids[0]
    repairs: list[str] = []
    for index in range(count - 1):
        if words[index] != FRAME_EDITOR_WINDOW_CLASS:
            continue
        stored = words[index + 1]
        if stored in present:
            continue
        words[index + 1] = first
        repairs.append(
            f"the scaffold's saved editor layout reopens a Frame Editor on "
            f"frame item id {stored}, which this project has no frame for; "
            f"retargeted to frame 0's item id {first} so the window can be "
            "reopened"
        )
    if not repairs:
        return data, []
    payload = (
        data[state.start:tail_start]
        + struct.pack(f"<{count}i", *words)
        + data[tail_start + 4 * count:state.end]
    )
    if ledger is not None:
        return ledger.splice(data, "editor-state", payload), repairs
    return rebuild(data, {"editor-state": payload}), repairs

def neutral_object_head(data: bytes, start: int, tail_start: int) -> bytes:
    """Take one object record and blank it back to a reusable starting point.
    """
    return (
        data[start:start + 8]
        + struct.pack("<I", 0)
        + data[object_record_head(data, start):tail_start]
    )

def active_template(
    data: bytes, parts: list | None = None
) -> tuple[bytes, int]:
    """Find an Active in the base project to start every rebuilt Active from.

    Rebuilding an object means starting from a real record of that type and
    setting its properties, rather than assembling bytes that only look like one.
    Where the base project has no record of the type the game needs, that is
    refused by name.
    """
    for span in (parts if parts is not None else spans(data)):
        if not OBJECT_SPAN.fullmatch(span.name):
            continue
        if data[span.start:span.start + 4] != ACTIVE_KIND:
            continue
        _block, end = read_class_block(data, object_record_head(data, span.start))
        tail_start = prop_index_end(data, end)
        _item, icon, _animations = split_active_tail(data[tail_start:span.end])
        return neutral_object_head(data, span.start, tail_start), icon
    raise Unsupported("the scaffold holds no Active object to use as a template")

def backdrop_template(
    data: bytes, parts: list | None = None
) -> tuple[bytes, int]:
    """Find a Backdrop in the base project to start rebuilt Backdrops from."""
    for span in (parts if parts is not None else spans(data)):
        if not OBJECT_SPAN.fullmatch(span.name):
            continue
        if data[span.start:span.start + 4] != BACKDROP_KIND:
            continue
        _block, end = read_class_block(data, object_record_head(data, span.start))
        tail_start = prop_index_end(data, end)
        _item, icon, _image = split_backdrop_tail(data[tail_start:span.end])
        return neutral_object_head(data, span.start, tail_start), icon
    raise Unsupported(
        "the target needs a regular Backdrop but the scaffold holds no "
        "Backdrop template"
    )

def quick_backdrop_template(
    data: bytes, parts: list | None = None
) -> tuple[bytes, int]:
    """Find a Quick Backdrop in the base project to start rebuilt ones from."""
    for span in (parts if parts is not None else spans(data)):
        if not OBJECT_SPAN.fullmatch(span.name):
            continue
        if data[span.start:span.start + 4] != QUICK_BACKDROP_KIND:
            continue
        _block, end = read_class_block(data, object_record_head(data, span.start))
        tail_start = prop_index_end(data, end)
        _item, icon, _runtime_tail, _motif = split_quick_backdrop_tail(
            data[tail_start:span.end]
        )
        return neutral_object_head(data, span.start, tail_start), icon
    raise Unsupported(
        "the target needs a Quick Backdrop but the scaffold holds no "
        "Quick Backdrop template"
    )

def string_template(
    data: bytes, parts: list | None = None
) -> tuple[bytes, int]:
    """Find a String object in the base project to start rebuilt Strings from.
    """
    for span in (parts if parts is not None else spans(data)):
        if not OBJECT_SPAN.fullmatch(span.name):
            continue
        if data[span.start:span.start + 4] != STRING_KIND:
            continue
        _block, end = read_class_block(data, object_record_head(data, span.start))
        tail_start = prop_index_end(data, end)
        _item, icon, _runtime_tail = split_string_tail(
            data[tail_start:span.end]
        )
        return neutral_object_head(data, span.start, tail_start), icon
    raise Unsupported(
        "the target needs a String but the scaffold holds no String template"
    )

def counter_family_template(
    data: bytes, kind: bytes, label: str, parts: list | None = None
) -> tuple[bytes, int]:
    """Find a starting record for one of the types that share a tail layout.

    Counter, Lives, Score, Question & Answer, Formatted Text, Sub-Application and
    extension objects all store their own data after a common head, so they are
    found the same way and differ only in which type is being asked for.
    """
    for span in (parts if parts is not None else spans(data)):
        if not OBJECT_SPAN.fullmatch(span.name):
            continue
        if data[span.start:span.start + 4] != kind:
            continue
        _block, end = read_class_block(data, object_record_head(data, span.start))
        tail_start = prop_index_end(data, end)
        tail = data[tail_start:span.end]
        if len(tail) < 12 or tail[4:8] != b"icnI":
            raise Unsupported(f"the scaffold's {label} tail has no icnI")
        (icon,) = struct.unpack_from("<I", tail, 8)
        return neutral_object_head(data, span.start, tail_start), icon
    raise Unsupported(
        f"the target needs a {label} but the scaffold holds no {label} template"
    )

def counter_template(data: bytes, parts: list | None = None) -> tuple[bytes, int]:
    return counter_family_template(data, COUNTER_KIND, "Counter", parts)

def lives_template(data: bytes, parts: list | None = None) -> tuple[bytes, int]:
    return counter_family_template(data, LIVES_KIND, "Lives", parts)

def score_template(data: bytes, parts: list | None = None) -> tuple[bytes, int]:
    return counter_family_template(data, SCORE_KIND, "Score", parts)

def qanda_template(data: bytes, parts: list | None = None) -> tuple[bytes, int]:
    return counter_family_template(data, QANDA_KIND, "Question & Answer", parts)

def ftext_template(data: bytes, parts: list | None = None) -> tuple[bytes, int]:
    return counter_family_template(
        data, FORMATTED_TEXT_KIND, "Formatted Text", parts
    )

SUBAPPLICATION_KIND = b"CCAx"

SUBAPPLICATION_INTERNAL = 1 << 14

def subapplication_template(
    data: bytes, parts: list | None = None
) -> tuple[bytes, int]:
    return counter_family_template(
        data, SUBAPPLICATION_KIND, "Sub-Application", parts
    )

def extension_template(
    data: bytes, parts: list | None = None
) -> tuple[bytes, int]:
    return counter_family_template(
        data, EXTENSION_KIND, "extension object", parts
    )

def donor_module_titles(sources: list[Path]) -> dict[str, str]:
    """Read extension display titles out of projects supplied as references.

    Two references that disagree about one module's title stop the run: a title
    belongs to the module, so a disagreement means one of them is describing a
    different release, and quietly picking one would mislabel the objects.
    """
    titles: dict[str, str] = {}
    for source in sources:
        _depth, entries = editor_extensions(source)
        for _slot, filename, title in entries:
            key = filename.lower()
            if titles.setdefault(key, title) != title:
                raise Unsupported(
                    f"the supplied CCAs disagree on {filename}'s title: "
                    f"{titles[key]!r} and {title!r}"
                )
    return titles

def merge_installed_titles(
    titles: dict[str, str], extension_dirs: Path | list[Path] | None
) -> dict[str, str]:
    """Take module display titles from the extensions installed on this machine.

    Only consulted when an extensions folder has been named. A disagreement
    between what is installed and what the game expects is treated as fatal
    rather than smoothed over, because silently preferring one would produce a
    project whose objects are labelled for a different release.
    """
    if extension_dirs is None:
        return titles, []
    if isinstance(extension_dirs, Path):
        extension_dirs = [extension_dirs]
    merged = dict(titles)
    from_cca = set(titles)
    drift: list[str] = []
    for directory in extension_dirs:
        if not directory.is_dir():
            raise Unsupported(f"extension directory {directory} does not exist")
        for module, title in installed_titles(directory).items():
            if module not in merged:
                merged[module] = title
                continue
            if merged[module] == title:
                continue
            if module in from_cca:
                raise Unsupported(
                    f"{module}: a supplied Build-119 CCA titles it "
                    f"{merged[module]!r} but {directory} declares {title!r}; a "
                    "module title is supposed to be a property of the .cox"
                )
            drift.append(
                f"{module}: {directory} declares {title!r}; keeping "
                f"{merged[module]!r} from an earlier source"
            )
    return merged, drift

def packed_note(image: bytes) -> str:
    """Explain that a module's title is unreadable because the file is compressed.

    Some extension modules ship compressed, which puts their text out of reach
    without unpacking them. Worth saying plainly: this is a property of the
    module, not a fault in the reader, and nothing here can undo it.
    """
    try:
        names = {
            image[off:off + 8].rstrip(b"\0")
            for off in _section_name_offsets(image)
        }
    except Exception:
        return ""
    for marker, packer in ((b"UPX0", "UPX"), (b".aspack", "ASPack"),
                           (b".petite", "Petite"), (b"MEW", "MEW")):
        if any(name.startswith(marker) for name in names):
            return (
                f" -- the image is {packer}-packed, so its string table is "
                "inside the compressed payload; this is not a reader fault and "
                "not fixable without unpacking"
            )
    return ""

def no_strings_note(image: bytes) -> str:
    """Explain that a module carries no title text at all to recover."""
    try:
        kinds = {tag[0] for tag, _off, _size in resource_entries(image)}
    except Exception:
        return ""
    if 6 not in kinds:
        return (
            " -- it carries no RT_STRING resource at all, so the title was "
            "stripped from this build; nothing can recover it"
        )
    return ""

def _section_name_offsets(image: bytes):
    pe = struct.unpack_from("<I", image, 0x3C)[0]
    count = struct.unpack_from("<H", image, pe + 6)[0]
    optional_size = struct.unpack_from("<H", image, pe + 20)[0]
    table = pe + 24 + optional_size
    return [table + index * 40 for index in range(count)]

def merge_embedded_titles(
    titles: dict[str, str], exe: Path, wanted: set[str]
) -> tuple[dict[str, str], list[str]]:
    """Recover module display titles from the game's own embedded copies.

    The usual source, and the reason a game titles its extensions correctly on a
    machine that has never had them installed.
    """
    from klikback.core.common.extension_binaries import embedded_modules

    outstanding = {name for name in wanted if name not in titles}
    if not outstanding:
        return titles, []
    merged = dict(titles)
    notes: list[str] = []
    try:
        embedded = embedded_modules(exe)
    except Exception as exc:
        return merged, [f"embedded module stream unreadable: {exc}"]
    for module in embedded:
        name = module.filename.lower()
        if name not in outstanding:
            continue
        try:
            title = title_from_bytes(module.image)
        except CoxProblem as exc:
            notes.append(
                f"{module.filename}: embedded image carries no readable title "
                f"({exc}){packed_note(module.image)}"
            )
            continue
        if not title:
            notes.append(
                f"{module.filename}: embedded image declares no title"
                f"{no_strings_note(module.image)}"
            )
            continue
        merged[name] = title
        notes.append(
            f"{module.filename}: title {title!r} recovered from the target's "
            "own embedded module, because no supplied CCA and no installed "
            ".cox names it"
        )
    return merged, notes

def build_module_entries(
    modules: dict[int, str], titles: dict[str, str]
) -> bytes:
    """The extension modules the project declares, with their display titles.
    """
    out = bytearray()
    for slot in sorted(modules):
        filename = modules[slot]
        out += struct.pack("<I", slot)
        out += counted(filename.encode("ascii"))
        out += counted(titles[filename.lower()].encode("ascii"))
        out += struct.pack("<II", EXTENSION_SIGNATURE, 0)
    return bytes(out)

def template_from_sources(
    builder,
    sources: list[bytes],
    kind: bytes | None = None,
    build: int | None = None,
    need_icon: bool = True,
    source_spans: list | None = None,
) -> tuple[bytes, int, bytes | None]:
    """Find a starting record for one object type, or emit one from the grammar.

    Reference projects are tried in order and the first that has the type wins;
    when none does, the record is synthesised from the format's own description
    of it. That fallback is what lets KlikBack rebuild an object type without
    carrying an MMF-authored project to copy it out of.
    """
    last_problem = None
    for index, source in enumerate(sources):
        parts = source_spans[index] if source_spans is not None else None
        try:
            head, icon = builder(source, parts)
            return head, icon, None if index == 0 else source
        except Unsupported as problem:
            last_problem = problem
    if kind is not None:
        from klikback.core.mmf15.template_synthesis import TEMPLATE_BUILD, TEMPLATE_SPECS, donor_bytes, synthesised_template

        if build == TEMPLATE_BUILD and kind in TEMPLATE_SPECS:
            head, icon = synthesised_template(kind)

            return head, icon, donor_bytes(kind) if need_icon else None
    if last_problem is not None:
        raise last_problem
    raise Unsupported("no template sources were supplied")

def active_record(head: bytes, icon: int, item_id: int, obj: dict) -> bytes:
    """Build the editor record for one Active object.

    Everything the Active's property dialogs show comes from the compiled object:
    its movement, ink effect, scrolling and display flags, colour, qualifiers,
    alterable values and animations. An attached behaviour left over from the
    starting record is cleared, because the game's own behaviours are recovered
    separately and an inherited one would be somebody else's events.
    """
    block, end = read_class_block(head, 12)
    set_string(block, "ItNa", obj["name"])

    behaviour_property = block.by_tag("LEvt")
    if behaviour_property is not None and any(
        not entry.inherited and entry.size for entry in behaviour_property.entries
    ):
        set_blob(block, "LEvt", b"")
    header = obj["header"]
    definition = obj["definition"]
    if len(header) < 16 or len(definition) < OBJECT_COLOUR_OFFSET + 4:
        raise Unsupported(
            f"Active {obj['object_id']} has {len(header)} header and "
            f"{len(definition)} definition bytes"
        )
    ink_flags = struct.unpack_from("<H", header, 0x0A)[0]
    scroll_flags = definition[0x13]
    display_flags = definition[DISPLAY_FLAGS_OFFSET]
    set_scalar(block, "MFla", struct.unpack_from("<H", header, 4)[0])
    set_indexed_scalar(block, "InkF", 0, 2 if ink_flags & 0x1000 else 1)
    set_indexed_scalar(block, "InkF", 1, struct.unpack_from("<H", header, 8)[0])
    set_indexed_scalar(block, "InkF", 2, struct.unpack_from("<I", header, 12)[0])
    set_scalar(block, "AntA", 2 if ink_flags & 0x2000 else 1)
    set_indexed_scalar(block, "SFlg", 0, 1 if scroll_flags & NO_FOLLOW_FRAME else 2)
    set_indexed_scalar(
        block, "SFlg", 1, 1 if scroll_flags & NO_DESTROY_IF_FAR else 2
    )
    set_indexed_scalar(
        block, "SFlg", 2, 1 if scroll_flags & NO_INACTIVATE_IF_FAR else 3
    )

    if scroll_flags & DISPLAY_PROPERTY:
        set_scalar(block, "DFlg", 1)
    set_indexed_scalar(
        block, "BFlg", 0, 1 if display_flags & SAVE_BACKGROUND else 2
    )
    set_indexed_scalar(
        block, "BFlg", 1, 2 if display_flags & WIPE_WITH_COLOUR else 1
    )
    set_scalar(block, "CFlg", 0 if display_flags & 0x04 else 1)
    set_scalar(block, "Visi", 2 if display_flags & VISIBLE_AT_START else 1)
    set_scalar(
        block,
        "Colo",
        struct.unpack_from("<I", definition, OBJECT_COLOUR_OFFSET)[0],
    )
    qualifiers = runtime_qualifiers_15(definition)
    if qualifiers:
        set_blob(block, "Qual", qualifiers)
    alterable_values = runtime_alterable_values_15(definition)
    if alterable_values:
        set_blob(block, "AltV", editor_alterable_values(alterable_values))
    write_transition_properties(block, obj.get("transitions", {}))
    try:
        set_movement_property(block, obj)
    except ObjectRecordProblem as problem:
        raise Unsupported(str(problem)) from None
    patched = head[:12] + block.pack() + head[end:]
    return (
        patched
        + struct.pack("<I", item_id)
        + b"icnI"
        + struct.pack("<I", icon)
        + editor_animation_set(runtime_animations(obj["definition"]))
    )

def without_attached_behaviour(record: bytes) -> bytes:
    """Strip a behaviour the starting record brought with it."""
    block, end = read_class_block(record, 12)
    prop = block.by_tag("LEvt")
    if prop is None or not any(
        not entry.inherited and entry.size for entry in prop.entries
    ):
        return record
    set_blob(block, "LEvt", b"")
    return record[:12] + block.pack() + record[end:]

def backdrop_record(
    head: bytes,
    icon: int,
    item_id: int,
    obj: dict,
    name: bytes | None = None,
    unresolved_image: int | None = None,
) -> bytes:
    """Build the editor record for one Backdrop object.

    A Backdrop whose image never resolved is given the substitute image allocated
    for that purpose; with no substitute available the object is refused rather
    than written pointing at nothing.
    """
    header = obj["header"]
    definition = obj["definition"]
    if len(header) < 16 or len(definition) != 10:
        raise Unsupported(
            f"Backdrop {obj['object_id']} has {len(header)} header and "
            f"{len(definition)} definition bytes"
        )
    flags = struct.unpack_from("<H", header, 0x0A)[0]
    block, end = read_class_block(head, 12)
    set_object_name(block, name or obj["name"] or b"Backdrop")
    set_scalar(block, "MFla", struct.unpack_from("<H", header, 4)[0])
    set_indexed_scalar(block, "InkF", 0, 2 if flags & 0x1000 else 1)
    set_indexed_scalar(block, "InkF", 1, struct.unpack_from("<H", header, 8)[0])
    set_indexed_scalar(block, "InkF", 2, struct.unpack_from("<I", header, 12)[0])
    set_scalar(block, "AntA", 2 if flags & 0x2000 else 1)
    set_indexed_scalar(block, "Obst", 1, definition[4])
    set_indexed_scalar(
        block,
        "Obst",
        2,
        CHECKBOX_ON if struct.unpack_from("<H", definition, 6)[0] else CHECKBOX_OFF,
    )
    write_transition_properties(block, obj.get("transitions", {}))
    image = struct.unpack_from("<H", definition, 8)[0]
    if image == UNRESOLVED_IMAGE_HANDLE:

        if unresolved_image is None:
            raise Unsupported(
                f"Backdrop {obj['object_id']} names the unresolved-image "
                f"marker {UNRESOLVED_IMAGE_HANDLE} and no substitute image "
                "was allocated"
            )
        image = unresolved_image
    patched = head[:12] + block.pack() + head[end:]
    return patched + struct.pack("<I4sII", item_id, b"icnI", icon, image)

def quick_backdrop_record(
    head: bytes, icon: int, item_id: int, obj: dict, name: bytes | None = None
) -> bytes:
    """Build the editor record for one Quick Backdrop object."""
    header = obj["header"]
    definition = obj["definition"]
    if len(header) < 16 or len(definition) < 22:
        raise Unsupported(
            f"Quick Backdrop {obj['object_id']} has {len(header)} header and "
            f"{len(definition)} definition bytes"
        )
    flags = struct.unpack_from("<H", header, 0x0A)[0]
    block, end = read_class_block(head, 12)

    set_object_name(block, name or obj["name"] or b"Quick Backdrop")
    set_scalar(block, "MFla", struct.unpack_from("<H", header, 4)[0])
    set_indexed_scalar(block, "InkF", 0, 2 if flags & 0x1000 else 1)
    set_indexed_scalar(block, "InkF", 1, struct.unpack_from("<H", header, 8)[0])
    set_indexed_scalar(block, "InkF", 2, struct.unpack_from("<I", header, 12)[0])
    set_scalar(block, "AntA", 2 if flags & 0x2000 else 1)

    set_indexed_scalar(block, "Obst", 1, definition[4])
    write_transition_properties(block, obj.get("transitions", {}))
    patched = head[:12] + block.pack() + head[end:]
    return patched + build_quick_backdrop_tail(item_id, icon, obj)

def string_record(
    head: bytes, icon: int, item_id: int, obj: dict, name: bytes | None = None
) -> bytes:
    """Build the editor record for one String object."""
    header = obj["header"]
    definition = obj["definition"]
    if len(header) < 16 or len(definition) < OBJECT_COLOUR_OFFSET + 4:
        raise Unsupported(
            f"String {obj['object_id']} has {len(header)} header and "
            f"{len(definition)} definition bytes"
        )
    ink_flags = struct.unpack_from("<H", header, 0x0A)[0]
    scroll_flags = definition[0x13]
    display_flags = definition[DISPLAY_FLAGS_OFFSET]
    block, end = read_class_block(head, 12)
    set_object_name(block, name or obj["name"] or b"String")
    set_scalar(block, "MFla", struct.unpack_from("<H", header, 4)[0])
    set_indexed_scalar(block, "InkF", 0, 2 if ink_flags & 0x1000 else 1)
    set_indexed_scalar(block, "InkF", 1, struct.unpack_from("<H", header, 8)[0])
    set_indexed_scalar(block, "InkF", 2, struct.unpack_from("<I", header, 12)[0])
    set_scalar(block, "AntA", 2 if ink_flags & 0x2000 else 1)
    set_indexed_scalar(block, "SFlg", 0, 1 if scroll_flags & NO_FOLLOW_FRAME else 2)
    set_indexed_scalar(
        block, "SFlg", 1, 1 if scroll_flags & NO_DESTROY_IF_FAR else 2
    )
    set_indexed_scalar(
        block, "SFlg", 2, 1 if scroll_flags & NO_INACTIVATE_IF_FAR else 3
    )
    set_scalar(block, "DFlg", 1 if scroll_flags & DISPLAY_PROPERTY else 0)
    set_indexed_scalar(
        block, "BFlg", 0, 1 if display_flags & SAVE_BACKGROUND else 2
    )
    set_indexed_scalar(
        block, "BFlg", 1, 2 if display_flags & WIPE_WITH_COLOUR else 1
    )

    set_scalar(block, "CFlg", 1)
    set_scalar(block, "Visi", 2 if display_flags & VISIBLE_AT_START else 1)
    set_scalar(
        block,
        "Colo",
        struct.unpack_from("<I", definition, OBJECT_COLOUR_OFFSET)[0],
    )
    write_transition_properties(block, obj.get("transitions", {}))
    patched = head[:12] + block.pack() + head[end:]
    return patched + build_string_tail(item_id, icon, obj)

def set_common_nonactive_properties(
    block,
    obj: dict,
    *,
    preserve_ink_page: bool = False,
    preserve_display: bool = False,
) -> None:
    """Write the properties every non-Active object type shares.

    Name, movement flags, ink effect, scrolling and display behaviour, colour and
    qualifiers are stored the same way whatever the object is, so they are
    written once here and each type adds only what is its own. Two of them are
    held back for the types that store them differently.
    """
    header = obj["header"]
    definition = obj["definition"]
    if len(header) < 16 or len(definition) < OBJECT_COLOUR_OFFSET + 4:
        raise Unsupported(
            f"object {obj['object_id']} has {len(header)} header and "
            f"{len(definition)} definition bytes"
        )
    ink_flags = struct.unpack_from("<H", header, 0x0A)[0]
    scroll_flags = definition[0x13]
    display_flags = definition[DISPLAY_FLAGS_OFFSET]
    set_object_name(block, obj["name"])
    set_scalar(block, "MFla", struct.unpack_from("<H", header, 4)[0])
    if not preserve_ink_page:
        set_indexed_scalar(block, "InkF", 0, 2 if ink_flags & 0x1000 else 1)
        set_indexed_scalar(
            block, "InkF", 1, struct.unpack_from("<H", header, 8)[0]
        )
        set_indexed_scalar(
            block, "InkF", 2, struct.unpack_from("<I", header, 12)[0]
        )
    set_scalar(block, "AntA", 2 if ink_flags & 0x2000 else 1)
    set_indexed_scalar(block, "SFlg", 0, 1 if scroll_flags & NO_FOLLOW_FRAME else 2)
    set_indexed_scalar(
        block, "SFlg", 1, 1 if scroll_flags & NO_DESTROY_IF_FAR else 2
    )
    set_indexed_scalar(
        block, "SFlg", 2, 1 if scroll_flags & NO_INACTIVATE_IF_FAR else 3
    )
    if not preserve_display:
        set_scalar(block, "DFlg", 1 if scroll_flags & DISPLAY_PROPERTY else 0)
    set_indexed_scalar(
        block, "BFlg", 0, 1 if display_flags & SAVE_BACKGROUND else 2
    )
    set_indexed_scalar(
        block, "BFlg", 1, 2 if display_flags & WIPE_WITH_COLOUR else 1
    )
    set_scalar(block, "CFlg", 1)
    set_scalar(block, "Visi", 2 if display_flags & VISIBLE_AT_START else 1)
    set_scalar(
        block,
        "Colo",
        struct.unpack_from("<I", definition, OBJECT_COLOUR_OFFSET)[0],
    )
    qualifiers = runtime_qualifiers_15(definition)
    if qualifiers and block.by_tag("Qual") is not None:
        set_blob(block, "Qual", qualifiers)
    write_transition_properties(block, obj.get("transitions", {}))

def counter_record(head: bytes, icon: int, item_id: int, obj: dict) -> bytes:
    """Build the editor record for one Counter object."""
    payload = counter_payload(obj)
    block, end = read_class_block(head, 12)
    set_common_nonactive_properties(block, obj)
    set_indexed_scalar(block, "Valu", 1, payload["initial"] & 0xFFFFFFFF)
    set_indexed_scalar(block, "Valu", 3, payload["minimum"] & 0xFFFFFFFF)
    set_indexed_scalar(block, "Valu", 5, payload["maximum"] & 0xFFFFFFFF)
    patched = head[:12] + block.pack() + head[end:]
    return patched + build_counter_tail(item_id, icon, obj)

def lives_record(head: bytes, icon: int, item_id: int, obj: dict) -> bytes:
    """Build the editor record for one Lives object."""
    payload = lives_payload(obj)
    block, end = read_class_block(head, 12)
    set_common_nonactive_properties(block, obj)
    set_indexed_scalar(block, "Play", 1, payload["player"] - 1)
    patched = head[:12] + block.pack() + head[end:]
    return patched + build_lives_tail(item_id, icon, obj)

def score_record(head: bytes, icon: int, item_id: int, obj: dict) -> bytes:
    """Build the editor record for one Score object."""
    payload = score_payload(obj)
    block, end = read_class_block(head, 12)
    set_common_nonactive_properties(block, obj)
    set_indexed_scalar(block, "Play", 1, payload["player"] - 1)
    patched = head[:12] + block.pack() + head[end:]
    return patched + build_score_tail(item_id, icon, obj)

def qanda_record(head: bytes, icon: int, item_id: int, obj: dict) -> bytes:
    """Build the editor record for one Question & Answer object."""
    block, end = read_class_block(head, 12)
    set_common_nonactive_properties(
        block,
        obj,
        preserve_ink_page=True,
        preserve_display=True,
    )
    patched = head[:12] + block.pack() + head[end:]
    return patched + build_qanda_tail(item_id, icon, obj)

def ftext_record(head: bytes, icon: int, item_id: int, obj: dict) -> bytes:
    """Build the editor record for one Formatted Text object."""
    block, end = read_class_block(head, 12)
    set_common_nonactive_properties(block, obj)

    patched = head[:12] + block.pack() + head[end:]
    return patched + build_ftext_tail(item_id, icon, obj)

def subapplication_payload(obj: dict) -> dict:
    """Read a Sub-Application's size, options and the file it points at."""
    definition = obj["definition"]
    if len(definition) < 0x30 or definition[0x2C:0x30] != SUBAPPLICATION_IDENTIFIER:
        raise Unsupported(f"object {obj['object_id']} is not a Sub-Application definition")
    (offset,) = struct.unpack_from("<I", definition, 0x0C)
    if offset + 17 > len(definition):
        raise Unsupported("Sub-Application data block is truncated")
    leading, width, height, version, start_frame, options = struct.unpack_from(
        "<IHHHHI", definition, offset
    )
    path = definition[offset + 16 :].split(b"\x00", 1)[0]
    if leading or version:
        raise Unsupported(
            f"Sub-Application has unsupported leading/version fields "
            f"{leading}/{version}"
        )
    internal = bool(options & SUBAPPLICATION_INTERNAL)

    if internal and path:
        raise Unsupported(
            "Sub-Application sets Internal and still names a child path "
            f"({path!r}); an internal child is stored in the project itself, "
            "so the two together have no consistent meaning"
        )
    if not internal and path:
        if not path.lower().endswith(b".ccn"):
            raise Unsupported(
                "external Sub-Application runtime path does not end in .ccn"
            )

        path = path[:-4] + b".cca"
    return {
        "width": width,
        "height": height,
        "start_frame": start_frame,
        "options": options,
        "path": path,
        "internal": internal,
    }

def retarget_subapplication_path(
    path: bytes, directory: Path | None, repairs: list[str] | None
) -> bytes:
    """Point a Sub-Application at a file beside the rebuilt project.

    A Sub-Application stores the path of its child as it was on the machine that
    compiled the game — an absolute path into somebody else's folders, which
    means nothing here. Rewriting it to the folder being written to is reported
    as a repair, so the change is visible rather than assumed.
    """
    if directory is None or not path:
        return path
    replacement = str(Path(directory) / Path(path.decode("latin-1")).name)
    encoded = replacement.encode("latin-1", errors="replace")
    if encoded != path and repairs is not None:
        repairs.append(
            f"Sub-Application path retargeted to {replacement!r} "
            f"(the target stored {path.decode('latin-1')!r}, which is the "
            f"path on the machine that compiled it)"
        )
    return encoded

def subapplication_record(
    head: bytes,
    icon: int,
    item_id: int,
    obj: dict,
    retarget_directory: Path | None = None,
    repairs: list[str] | None = None,
) -> bytes:
    """Build the editor record for one Sub-Application object."""
    payload = subapplication_payload(obj)
    payload["path"] = retarget_subapplication_path(
        payload["path"], retarget_directory, repairs
    )
    block, end = read_class_block(head, 12)
    set_common_nonactive_properties(block, obj)
    patched = head[:12] + block.pack() + head[end:]
    tail = (
        struct.pack("<I4sII", item_id, b"icnI", icon, len(payload["path"]))
        + payload["path"]
        + struct.pack(
            "<III", payload["width"], payload["height"], payload["options"]
        )
    )
    if payload["internal"]:
        tail += struct.pack("<I", payload["start_frame"])
    return patched + tail

NEUTRAL_OBJECT_NAMES = {
    BACKDROP: b"Backdrop",
    QUICK_BACKDROP: b"Quick Backdrop",
    STRING: b"String",
}

def frame_object_names(objects: list[dict]) -> list[bytes | None]:
    """Give the unnamed objects in a frame distinct names to show in the editor.

    Backdrops, Quick Backdrops and Strings are commonly left unnamed by their
    author, and the compiled game keeps no name for them. Numbered type names
    stand in so the editor's object list is usable; anything the author did name
    keeps its own name.
    """
    taken = {obj["name"] for obj in objects if obj["name"]}
    out: list[bytes | None] = []
    for obj in objects:
        base = NEUTRAL_OBJECT_NAMES.get(obj["object_type"])
        if obj["name"] or base is None:
            out.append(None)
            continue
        name, ordinal = base, 1
        while name in taken:
            ordinal += 1
            name = base + b" " + str(ordinal).encode("ascii")
        taken.add(name)
        out.append(name)
    return out

def extension_record(head: bytes, icon: int, item_id: int, obj: dict) -> bytes:
    """Build the editor record for one extension object.

    The module's own settings are carried across untouched — they are the
    extension's private data and nothing here claims to understand them.
    """
    block, end = read_class_block(head, 12)
    set_common_nonactive_properties(
        block, obj, preserve_ink_page=True, preserve_display=True
    )

    try:
        set_movement_property(block, obj, reader=runtime_extension_movement)
    except ObjectRecordProblem:
        pass
    patched = head[:12] + block.pack() + head[end:]
    return (
        patched
        + struct.pack("<I", item_id)
        + build_extension_tail(icon, obj["extension_module"], obj["editdata"])
    )

def instance_records(
    placements: list[dict],
    objects_by_id: dict[int, dict],
    item_ids: dict[int, int],
) -> bytes:
    """Every placement of every object in a frame — what sits where."""
    out = bytearray()
    for placement in placements:
        obj = objects_by_id[placement["object_id"]]
        if obj["object_type"] == STRING:
            out += STRING_INSTANCE_TAG
        elif obj["object_type"] == FORMATTED_TEXT:
            out += FORMATTED_TEXT_INSTANCE_TAG
        else:
            out += INSTANCE_TAG
        if placement["link"]:
            editor_a, editor_b, editor_end = placeholder_editor_fields(
                placement["link"], item_ids, allow_dangling_parent=True
            )
        else:
            editor_a, editor_b, editor_end = 0, 0, -1
        out += struct.pack(
            "<iiiiiii",
            placement["x"],
            placement["y"],
            placement["handle"],
            editor_a,
            editor_b,
            item_ids[placement["object_id"]],
            editor_end,
        )
    return bytes(out)

EVENT_PAGE = b"evpg"

EVENTS = b"Evts"

EVENT_EDITOR = b"EvEd"

def counted(text: bytes) -> bytes:
    """Prefix a payload with its own length, the way the format stores text."""
    return struct.pack("<I", len(text)) + text

EMPTY_EVENT_EDITOR = EVENT_EDITOR + struct.pack("<H", 0)

def frame_body(
    scaffold_body: bytes,
    placements: list[dict],
    objects_by_id: dict[int, dict],
    item_ids: dict[int, int],
    events: bytes,
    remarks: list[bytes],
    registry_block: bytes,
) -> bytes:
    """Build one frame: its geometry, palette, objects and their placements."""
    page = read_event_page(scaffold_body)
    return (
        instance_records(placements, objects_by_id, item_ids)
        + EVENT_PAGE
        + scaffold_body[page["start"] + 4:page["start"] + 8]
        + (EVENTS + counted_block(events) if events else b"")
        + event_remarks_block(remarks)
        + registry_block
        + EMPTY_EVENT_EDITOR
        + scaffold_body[page["tail_start"]:]
    )

def event_remarks_block(remarks: list[bytes]) -> bytes:
    """Store the text of a frame's comments, which its comment rows point at.
    """
    if not remarks:
        return b""
    class_name = b"class CEvtRemarkList"
    records = b"".join(
        b"EvRk" + struct.pack("<I", index) + counted(text)
        for index, text in enumerate(remarks)
    )
    return b"Rems" + counted(class_name) + struct.pack("<I", len(remarks)) + records

def counted_block(payload: bytes) -> bytes:
    return struct.pack("<I", len(payload)) + payload

def bank_palette(runtime_palette: bytes) -> bytes:
    """The image bank's copy of the palette, in the form the bank stores it."""
    out = bytearray(runtime_palette)
    for pos in range(3, len(out), 4):
        out[pos] = 0
    return bytes(out)

def target_image_mode(graphic_mode: int) -> int:
    """The colour depth the rebuilt project uses — the game's own, or a refusal.
    """
    if graphic_mode not in IMAGE_MODE_TO_COLOR_DEPTH:
        raise Unsupported(
            f"the runtime application graphic mode is {graphic_mode}, not one "
            f"of {sorted(IMAGE_MODE_TO_COLOR_DEPTH)}"
        )
    return graphic_mode

def replace_image_bank(
    data: bytes,
    images: list[tuple[int, bytes]],
    palette: bytes | None,
    graphic_mode: int,
    ledger: SpanLedger | None = None,
) -> bytes:
    """Swap in the images recovered from the game, wholesale."""
    parts = (
        ledger.parts
        if ledger is not None
        else {span.name: span for span in spans(data)}
    )
    header = bytearray(data[parts["AGMI-2"].start:parts["AGMI-2"].start + BANK_HEADER])
    mode = target_image_mode(graphic_mode)
    struct.pack_into("<I", header, 4, mode)
    if palette is not None:
        header[12:12 + 1024] = bank_palette(palette)

    icons = bytearray(data[parts["AGMI-1"].start:parts["AGMI-1"].end])
    struct.pack_into("<I", icons, 4, mode)
    replacements = {
        "AGMI-1": bytes(icons), "AGMI-2": build_bank(bytes(header), images)
    }
    if ledger is not None:
        return ledger.rebuild(data, replacements)
    return rebuild(data, replacements)

def assemble(
    exe: Path,
    scaffold: Path | None,
    output: Path | None = None,
    template_scaffolds: list[Path] | None = None,
    extension_dir: Path | list[Path] | None = None,
    ownerless_behaviours_per_frame: list[int] | str | None = None,

    recover_comments: bool = False,
    reconstruct_application_icons: bool = False,

    alias_object_icons: bool = True,

    subapplication_directory: Path | None = None,

    progress: Callable[..., None] | None = None,
) -> tuple[bytes, dict]:
    """Build the whole project and return its bytes.

    The one entry point worth calling: everything else here is a step inside it.
    The optional progress callback is a pure observer — a stage name at each
    boundary, `(stage, n, of)` inside the per-frame loop — and cannot change what
    is assembled.
    """
    if progress is not None:
        progress("events")
    summary = runtime_application(
        exe,
        ownerless_behaviours_per_frame=ownerless_behaviours_per_frame,
        recover_comments=recover_comments,
    )
    summary["application_icons"] = None
    if reconstruct_application_icons:
        try:
            summary["application_icons"] = icon_resources(exe)
        except ValueError as problem:

            if "not a PE executable" not in str(problem):
                raise
            summary.setdefault("losses", []).append(
                f"{Path(exe).name} is a bare runtime package with no PE "
                "resources, so its application icons cannot be recovered; "
                "the scaffold's are used"
            )
    if scaffold is None:
        from klikback.core.mmf15.scaffold_synthesis import product_scaffold_bytes

        data = product_scaffold_bytes()
    else:
        data = scaffold.read_bytes()
    data = insert_frames(data, len(summary["frames"]))
    target_header = read_header(data)
    template_sources = [data]
    for donor in template_scaffolds or []:
        donor_data = donor.read_bytes()
        donor_header = read_header(donor_data)
        if donor_header.build != target_header.build:
            raise Unsupported(
                f"template donor {donor.name} is build {donor_header.build}, "
                f"not target build {target_header.build}"
            )
        template_sources.append(donor_data)

    ledger = SpanLedger(data)
    parts = ledger.parts
    scaffold_frames = sum(1 for name in parts if name.endswith("-Fram"))
    if scaffold_frames != len(summary["frames"]):
        raise Unsupported(
            f"scaffold has {scaffold_frames} frames, the package has "
            f"{len(summary['frames'])}; only one-frame scaffold growth is built"
        )
    module_entries = b""
    if summary["extension_modules"]:
        if target_header.build != 119:
            raise Unsupported(
                "extension output requires a Build-119 target scaffold; "
                f"this scaffold is build {target_header.build}"
            )
        title_sources = ([scaffold] if scaffold is not None else []) + list(
            template_scaffolds or []
        )
        if not template_scaffolds:

            from klikback.core.mmf15.template_synthesis import TITLE_DONOR_FILES

            title_sources += [path for path in TITLE_DONOR_FILES if path.exists()]
        titles = donor_module_titles(title_sources)
        titles, title_drift = merge_installed_titles(titles, extension_dir)
        used = {name.lower() for name in summary["extension_modules"].values()}
        for note in title_drift:

            if note.split(":", 1)[0] in used:
                summary.setdefault("losses", []).append(
                    f"extension module title drift ignored -- {note}"
                )

        titles, embedded_notes = merge_embedded_titles(titles, exe, used)
        for note in embedded_notes:
            summary.setdefault("losses", []).append(
                f"extension module title -- {note}"
            )
        missing = {
            slot: filename
            for slot, filename in summary["extension_modules"].items()
            if filename.lower() not in titles
        }
        for slot, filename in sorted(missing.items()):

            stem = filename.rsplit(".", 1)[0]
            titles[filename.lower()] = stem
            summary.setdefault("losses", []).append(
                f"extension module title substituted -- slot {slot} "
                f"{filename}: no installed .cox or embedded module image "
                f"names it, so its filename stands in as {stem!r}; the "
                "module itself is carried intact"
            )
        module_entries = build_module_entries(
            summary["extension_modules"], titles
        )

    scaffold_objects = [
        struct.unpack_from("<I", data, parts[f"frame{index}-objects"].end - 4)[0]
        for index in range(scaffold_frames)
    ]

    frame_records = [b"" for _frame in summary["frames"]]
    if summary["objects"]:

        def head_only(builder, kind=None):
            head, _icon, _donor = template_from_sources(
                builder, template_sources, kind, target_header.build,
                need_icon=False,

                source_spans=[ledger.ordered]
                + [None] * (len(template_sources) - 1),
            )
            return head

        types = {obj["object_type"] for obj in summary["objects"]}
        active_head = head_only(active_template) if ACTIVE in types else None
        backdrop_head = (
            head_only(backdrop_template, BACKDROP_KIND)
            if BACKDROP in types else None
        )
        quick_backdrop_head = (
            head_only(quick_backdrop_template, QUICK_BACKDROP_KIND)
            if QUICK_BACKDROP in types else None
        )
        string_head = (
            head_only(string_template, STRING_KIND) if STRING in types else None
        )
        counter_head = (
            head_only(counter_template, COUNTER_KIND)
            if COUNTER in types else None
        )
        lives_head = (
            head_only(lives_template, LIVES_KIND) if LIVES in types else None
        )
        score_head = (
            head_only(score_template, SCORE_KIND) if SCORE in types else None
        )
        qanda_head = (
            head_only(qanda_template, QANDA_KIND) if QANDA in types else None
        )
        ftext_head = (
            head_only(ftext_template, FORMATTED_TEXT_KIND)
            if FORMATTED_TEXT in types else None
        )
        subapplication_head = (
            head_only(subapplication_template, SUBAPPLICATION_KIND)
            if SUBAPPLICATION_TYPE in types else None
        )
        extension_head = (
            head_only(extension_template, EXTENSION_KIND)
            if any(kind >= EXTENSION_OBJECT_TYPE_BASE for kind in types)
            else None
        )
        data, icons, handle_by_object = generate_object_icons(
            data, summary, alias=alias_object_icons, ledger=ledger
        )

        if summary.get("global_event_registry"):

            _bank_header, bank_records, _bank_order = editor_bank(
                data, 1, ledger.parts
            )
            for entry in summary["global_event_registry"]:
                entry["icon"] = bank_records[
                    handle_by_object.get(entry["object_id"], icons[0])
                ]
            summary["global_events"] = global_event_payload_15(
                summary["global_event_sheet"], summary["global_event_registry"]
            )

        def build_record(
            obj: dict, icon: int, item_id: int, name: bytes | None = None
        ) -> bytes:
            if obj["object_type"] == ACTIVE:
                return active_record(active_head, icon, item_id, obj)
            if obj["object_type"] == BACKDROP:
                return backdrop_record(
                    backdrop_head,
                    icon,
                    item_id,
                    obj,
                    name,
                    summary.get("unresolved_image"),
                )
            if obj["object_type"] == QUICK_BACKDROP:
                return quick_backdrop_record(
                    quick_backdrop_head, icon, item_id, obj, name
                )
            if obj["object_type"] == STRING:
                return string_record(string_head, icon, item_id, obj, name)
            if obj["object_type"] == COUNTER:
                return counter_record(counter_head, icon, item_id, obj)
            if obj["object_type"] == LIVES:
                return lives_record(lives_head, icon, item_id, obj)
            if obj["object_type"] == SCORE:
                return score_record(score_head, icon, item_id, obj)
            if obj["object_type"] == QANDA:
                return qanda_record(qanda_head, icon, item_id, obj)
            if obj["object_type"] == FORMATTED_TEXT:
                return ftext_record(ftext_head, icon, item_id, obj)
            if obj["object_type"] == SUBAPPLICATION_TYPE:
                return subapplication_record(
                    subapplication_head,
                    icon,
                    item_id,
                    obj,
                    subapplication_directory,
                    summary.setdefault("repairs", []),
                )
            if obj["object_type"] >= EXTENSION_OBJECT_TYPE_BASE:
                return extension_record(extension_head, icon, item_id, obj)
            raise Unsupported(
                f"no record builder for runtime type {obj['object_type']}"
            )

        icon_index = 0
        for frame_index, frame in enumerate(summary["frames"]):
            records = []
            names = frame_object_names(frame["objects"])
            for obj, name in zip(frame["objects"], names):
                records.append(
                    without_attached_behaviour(
                        build_record(
                            obj,
                            icons[icon_index],
                            frame["item_ids"][obj["object_id"]],
                            name,
                        )
                    )
                )
                icon_index += 1
            frame_records[frame_index] = b"".join(records)

    replacements = {
        "ATNF": build_atnf_bank(summary["fonts"]),
        "APMS": summary["sample_bank"],
        "ASUM": summary["music_bank"],
    }
    objects_by_id = {obj["object_id"]: obj for obj in summary["objects"]}
    for frame_index, frame in enumerate(summary["frames"]):
        if progress is not None:
            progress("frames", frame_index + 1, len(summary["frames"]))
        object_list = parts[f"frame{frame_index}-objects"]
        instance_list = parts[f"frame{frame_index}-instances"]
        body = parts[f"frame{frame_index}-body"]
        replacements[f"frame{frame_index}-objects"] = (
            data[object_list.start:object_list.end - 4]
            + struct.pack("<I", len(frame["objects"]))
        )
        replacements[f"frame{frame_index}-instances"] = (
            data[instance_list.start:instance_list.end - 4]
            + struct.pack("<I", len(frame["placements"]))
        )
        replacements[f"frame{frame_index}-body"] = frame_body(
            data[body.start:body.end],
            frame["placements"],
            objects_by_id,
            frame["item_ids"],
            frame["events"],
            frame["remarks"],
            frame["registry"],
        )
        replacements[f"frame{frame_index}-handle"] = struct.pack(
            "<I", frame["frame_item_id"]
        )

        if scaffold_objects[frame_index]:
            for object_index in range(scaffold_objects[frame_index]):
                replacements[f"frame{frame_index}-object{object_index}"] = (
                    frame_records[frame_index] if object_index == 0 else b""
                )
        else:
            replacements[f"frame{frame_index}-objects"] += frame_records[frame_index]

    data = rebuild(data, replacements, parts=ledger.ordered)
    ledger = SpanLedger(data)
    if progress is not None:
        progress("banks")

    data = replace_image_bank(
        data,
        summary["images"],
        summary["frames"][0]["palette"][4:]
        if summary["frames"][0]["palette"] is not None
        else None,
        summary["graphic_mode"],
        ledger=ledger,
    )
    summary["application_icons_customized"] = False
    if summary["application_icons"] is not None:
        if not application_icons_match_existing(
            data, summary["application_icons"], ledger=ledger
        ):
            if application_icons_are_default(summary["application_icons"]):

                data = write_default_application_icons(
                    data, summary["application_icons"], ledger=ledger
                )
            else:
                data = replace_application_icons(
                    data, summary["application_icons"], ledger=ledger
                )
                summary["application_icons_customized"] = True

    data = replace_frame_previews(data, summary, ledger=ledger)
    parts = ledger.parts

    frame_replacements: dict[str, bytes] = {}
    for frame_index in reversed(range(len(summary["frames"]))):
        frame = summary["frames"][frame_index]
        if frame["palette"] is not None:
            frame_replacements[f"frame{frame_index}-Pltt"] = (
                palette_span_payload(
                    data, parts[f"frame{frame_index}-Pltt"], frame["palette"]
                )
            )

        def frame_properties(block, frame=frame) -> None:
            set_string(block, "Tit", frame["name"] or b"")
            set_frame_password(block, frame["password"])
            set_scalar(block, "PfSz", frame["width"] | frame["height"] << 16)
            set_scalar(block, "Colo", frame["background"])
            set_scalar(block, "PfOp", pfop_from_frame_flags(frame["flags"]))
            set_frame_runtime_object_count(block, frame["runtime_object_count"])
            write_transition_properties(block, frame["transitions"])

        frame_replacements[f"frame{frame_index}-LFrame"] = ledger.pack_block(
            data, f"frame{frame_index}-LFrame", frame_properties
        )
    if frame_replacements:
        data = ledger.rebuild(data, frame_replacements)

    (bank_mode,) = struct.unpack_from("<I", data, parts["AGMI-2"].start + 4)

    extensions = bytearray(data[parts["extensions"].start:parts["extensions"].end])
    if summary["extension_modules"]:
        extensions = bytearray(
            struct.pack("<II", bank_mode, len(summary["extension_modules"]))
            + module_entries
        )
    else:
        struct.pack_into("<I", extensions, 0, bank_mode)
    data = ledger.splice(data, "extensions", bytes(extensions))

    data = ledger.patch_block(
        data,
        "LApplication",
        lambda block: write_application_properties(block, summary, bank_mode),
    )

    data, layout_repairs = retarget_editor_state_frames(
        data, [frame["frame_item_id"] for frame in summary["frames"]],
        ledger=ledger,
    )
    summary.setdefault("repairs", []).extend(layout_repairs)

    if output is not None:
        data = set_source_path(data, output, ledger=ledger)

    if progress is not None:
        progress("validate")
    check_output(data, summary)
    return data, summary

EDITOR_PALETTE_HEADER = bytes.fromhex("00 01 00 00")

def check_output(data: bytes, summary: dict) -> None:
    """Prove the assembled project is structurally sound before it is offered.

    A project that fails this is kept for inspection rather than presented as a
    result — the failure is worth more than a file that looks finished.
    """
    parts = spans(data)
    named = {span.name: span for span in parts}

    for frame_index, frame in enumerate(summary["frames"]):
        objects = sum(
            1
            for span in parts
            if OBJECT_SPAN.fullmatch(span.name)
            and span.name.startswith(f"frame{frame_index}-")
        )
        declared = struct.unpack_from(
            "<I", data, named[f"frame{frame_index}-objects"].end - 4
        )[0]
        if objects != declared or objects != len(frame["objects"]):
            raise Unsupported(
                f"frame {frame_index} object list declares {declared}, holds "
                f"{objects} records, package needs {len(frame['objects'])}"
            )
        instances = struct.unpack_from(
            "<I", data, named[f"frame{frame_index}-instances"].end - 4
        )[0]
        if instances != len(frame["placements"]):
            raise Unsupported(
                f"frame {frame_index} instance list declares {instances}, "
                f"package places {len(frame['placements'])}"
            )
        handle = struct.unpack_from(
            "<I", data, named[f"frame{frame_index}-handle"].start
        )[0]
        if handle != frame["frame_item_id"]:
            raise Unsupported(
                f"frame {frame_index} item id is {handle}, expected "
                f"{frame['frame_item_id']}"
            )

        block, _end = read_class_block(data, named[f"frame{frame_index}-LFrame"].start)
        stored = frame_password_of(block)
        wanted = frame["password"] or None
        if stored != wanted:
            raise Unsupported(
                f"frame {frame_index} Pass holds {stored!r}, the runtime "
                f"package holds {wanted!r}"
            )

        ids = [
            comment_row_id(row)
            for row in tile_events(frame["events"])
            if is_comment_row(row)
        ]
        if len(set(ids)) != len(ids):
            raise Unsupported(
                f"frame {frame_index} has {len(ids)} comment rows naming "
                f"{len(set(ids))} distinct Rems ids: {ids}"
            )
        if any(not 0 <= comment < len(frame["remarks"]) for comment in ids):
            raise Unsupported(
                f"frame {frame_index} comment rows name Rems ids {ids}, but "
                f"the page holds {len(frame['remarks'])} remark record(s)"
            )

    images = set(editor_bank(data, 2, named)[1])
    icons = set(editor_bank(data, 1, named)[1])
    font_bank = named["ATNF"]
    font_count = struct.unpack_from("<I", data, font_bank.start + 4)[0]
    fonts = {
        struct.unpack_from("<I", data, font_bank.start + 8 + index * 108)[0]
        for index in range(font_count)
    }
    for span in parts:
        if not OBJECT_SPAN.fullmatch(span.name):
            continue
        kind = data[span.start:span.start + 4]
        _block, end = read_class_block(data, object_record_head(data, span.start))
        tail = data[prop_index_end(data, end):span.end]
        if kind == ACTIVE_KIND:
            _item, icon, animations = split_active_tail(tail)
            image_handles = []
            for pos in range(len(animations) - 8):
                if animations[pos:pos + 4] == b"Imag":
                    image_handles.append(
                        struct.unpack_from("<I", animations, pos + 4)[0]
                    )
        elif kind == BACKDROP_KIND:
            _item, icon, image_handle = split_backdrop_tail(tail)
            image_handles = [image_handle]
        elif kind == QUICK_BACKDROP_KIND:
            _item, icon, _runtime_tail, motif = split_quick_backdrop_tail(tail)
            image_handles = [] if motif is None else [motif]
        elif kind == STRING_KIND:
            _item, icon, _runtime_tail = split_string_tail(tail)
            image_handles = []
            (font,) = struct.unpack_from("<I", _runtime_tail, 8)
            if font != 0xFFFFFFFF and font not in fonts:
                raise Unsupported(
                    f"{span.name} names font {font}, not in the ATNF bank"
                )
        elif kind == COUNTER_KIND:
            parsed = split_counter_tail(tail)
            icon = parsed["icon"]
            image_handles = parsed["images"]
        elif kind == LIVES_KIND:
            parsed = split_lives_tail(tail)
            icon = parsed["icon"]
            image_handles = parsed["images"]
        elif kind == SCORE_KIND:
            parsed = split_score_tail(tail)
            icon = parsed["icon"]
            image_handles = parsed["images"]
        elif kind == QANDA_KIND:
            parsed = split_qanda_tail(tail)
            icon = parsed["icon"]
            image_handles = []
            for font in parsed["fonts"]:
                if font not in fonts:
                    raise Unsupported(
                        f"{span.name} names font {font}, not in the ATNF bank"
                    )
        elif kind == FORMATTED_TEXT_KIND:
            parsed = split_ftext_tail(tail)
            icon = parsed["icon"]
            image_handles = []
        elif kind == SUBAPPLICATION_KIND:
            if len(tail) < 16 or tail[4:8] != b"icnI":
                raise Unsupported(f"{span.name} has a malformed Sub-Application tail")
            (icon,) = struct.unpack_from("<I", tail, 8)
            image_handles = []
        elif kind == EXTENSION_KIND:
            parsed = parse_extension_tail(tail, 4)
            icon = parsed.icon_handle
            image_handles = []
        else:
            raise Unsupported(f"{span.name} has unsupported kind {kind!r}")
        if icon not in icons:
            raise Unsupported(f"{span.name} names icon {icon}, not in AGMI bank 1")
        for handle in image_handles:
            if handle not in images:
                raise Unsupported(
                    f"{span.name} names image {handle}, not in AGMI bank 2"
                )

    for span in parts:
        if not span.name.endswith("-Pltt"):
            continue
        header = data[span.start + 4:span.start + 8]
        if header != EDITOR_PALETTE_HEADER:
            raise Unsupported(
                f"{span.name} carries {header.hex(' ')}, not the editor "
                f"header {EDITOR_PALETTE_HEADER.hex(' ')} -- a runtime "
                f"palette was copied in without conversion"
            )
