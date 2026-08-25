# GENERATED — do not edit by hand. This file is produced by KlikBack's
# sync tooling; changes belong in the source it is generated from.
#
# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""Emit the empty MMF 1.5 project every rebuild starts from, field by field.

The 1.5 half of the same idea as the 1.0 scaffold: a rebuild needs a valid
empty project to fill in, and this emits one from named fields through the
container grammar instead of keeping a copy of an existing project.

So the starting point is generated at the moment it is wanted, rather than
found. The placeholder artwork the empty project carries is described here
too.

The starting project stores a neutral location; only a project actually
written to disk records a real path, which is its own.
"""

from __future__ import annotations
import struct
from klikback.core.mmf15.cca import ClassBlock, Entry, INHERITED, Property, TYPE_STRING, TYPE_VOID
from klikback.core.common.scaffold_synthesis import ACTIVE_PROP_PAIRS as ACTIVE_PROP_PAIRS_98, AGMI_MODE_24BIT, APPLICATION_PROP_PAIRS as APPLICATION_PROP_PAIRS_98, DEFAULT_PROJECT_PALETTE, FRAME_PROP_PAIRS as FRAME_PROP_PAIRS_98, NEUTRAL_PROJECT_PATH, PATH_TO_LAYOUT_FILLER, POST_BANKS_PAD, WIN32_HALFTONE_PALETTE, agmi_bank, counted, default_players_payload, empty_simple_bank, extension_list, flagged_project_palette, instance_record, prop_index, window_record

PRODUCT = ord("U")

MAJOR = 1

STAMP = 0x0065CAD1

BUILD = 119

def container_header() -> bytes:
    """The file's own header: what it is, which build wrote it, how long it runs.
    """
    return b"CnC2" + bytes((PRODUCT, MAJOR)) + struct.pack("<IHH", STAMP, 0, BUILD)

PROP_INDEX_OPENER = 1

def inherited(type_id: int, index: int = 0) -> Entry:
    """An entry that takes the default rather than storing a value of its own.

    An MMF project stores "unset" as its own state, distinct from storing a zero,
    and the editor shows the two differently. Keeping the distinction is why a
    rebuilt project's dialogs look like a hand-made one's.
    """
    return Entry(type_id, index, 1, 1, INHERITED)

def scalar(type_id: int, word: int, index: int = 0) -> Entry:
    """An entry holding a single number."""
    return Entry(type_id, index, 1, 1, 0, word)

def blob(type_id: int, payload: bytes, index: int = 0) -> Entry:
    """An entry holding a block of bytes, with its own length."""
    return Entry(type_id, index, 1, 1, len(payload), len(payload), payload)

def string(payload: bytes, index: int = 0) -> Entry:
    """An entry holding text."""
    return Entry(TYPE_STRING, index, 1, 1, len(payload), None, payload)

def inherited_string(index: int) -> Entry:
    """A text entry left unset, rather than set to an empty string."""
    return Entry(TYPE_STRING, index, 1, 1, INHERITED)

def application_block(title: bytes = b"Application1\x00") -> bytes:
    """The application's own record: properties, defaults and window settings.

    The project-level record, written out with every property at the editor's own
    default: window size and options, colours, the scores and lives settings, the
    players list, the About text, the help file, the image mode, the version
    information.

    Most of those are carried as **present but inherited** — the property is
    there, and its value says "use the default" rather than stating one. That
    distinction is the whole reason this is written out explicitly instead of
    being trimmed to the properties something actually sets. Six of them —
    global values, the menu, global events, the help file, scores and lives — are
    properties whose *absence* makes the editor open the project blank. Not
    refuse it, not complain: open it with nothing in it. A project is not
    entitled to omit a property just because it has nothing to say about it.

    Only two things are stated rather than inherited: the run options, which
    Build 98's equivalent leaves inherited and this does not, and the image mode.
    Everything else that a real project needs is patched in afterwards from the
    game being rebuilt.
    """
    properties = [
        Property("WinS", 1, [inherited(0x0F)]),
        Property("WinO", 1, [inherited(0x19)]),
        Property("Colo", 1, [inherited(0x0D)]),
        Property("GEvt", 1, [inherited(0x0A)]),
        Property("GloV", 1, [inherited(0x0A)]),
        Property("Menu", 1, [inherited(0x0A)]),
        Property("Scor", 1, [inherited(TYPE_VOID), inherited(0x1E, 1)]),
        Property("Live", 1, [inherited(TYPE_VOID), inherited(0x1E, 1)]),
        Property("Plas", 1, [blob(0x0A, default_players_payload())]),

        Property("RunO", 1, [scalar(0x19, 0x24)]),
        Property(
            "AppI",
            1,
            [
                inherited(TYPE_VOID),
                inherited(0x0B, 1),
                inherited(TYPE_VOID, 2),
                inherited(0x1C, 3),
            ],
        ),
        Property(
            "Abou",
            1,
            [
                inherited(TYPE_VOID),
                string(title, 1),
                inherited(TYPE_VOID, 2),
                inherited_string(3),
            ],
        ),
        Property("Hlpf", 1, [inherited(0x0A)]),
        Property("AppM", 1, [scalar(0x1A, AGMI_MODE_24BIT)]),
        Property("LibT", 0, [inherited(0x1A)]),
        Property("Keyw", 0, [inherited(TYPE_VOID), string(b"\x00", 1)]),

        Property(
            "VIfo",
            0,
            [
                entry
                for index in range(0, 8, 2)
                for entry in (
                    inherited(TYPE_VOID, index),
                    inherited_string(index + 1),
                )
            ],
        ),
    ]
    return ClassBlock("LApplication", properties).pack()

def frame_block() -> bytes:
    """One empty frame, with the records a frame carries."""
    pale = bytes((0x00, 0x03, 0x00, 0x01)) + flagged_project_palette()
    properties = [
        Property("Tit", 1, [inherited(TYPE_VOID), inherited_string(1)]),
        Property("Pass", 1, [inherited(TYPE_VOID), inherited_string(1)]),
        Property("PfSz", 1, [inherited(0x0F)]),
        Property("Colo", 1, [inherited(0x0D)]),
        Property("PfOp", 1, [inherited(0x19)]),
        Property("Pale", 1, [blob(0x0A, pale)]),
        Property("Evt", 1, [inherited(0x1B)]),
        Property("FadI", 1, [inherited(0x0A)]),
        Property("FadO", 1, [inherited(0x0A)]),
        Property("NbO", 1, [inherited(TYPE_VOID), inherited(0x1E, 1)]),
        Property("Keyw", 0, [inherited(TYPE_VOID), string(b"\x00", 1)]),
    ]
    return ClassBlock("LFrame", properties).pack()

def active_item_block(name: bytes = b"Active\x00") -> bytes:
    """The properties an Active carries, each named and given its starting value.

    Every property the editor's Active dialogs can show is listed here — ink
    effect, scrolling, display and background behaviour, colour, qualifiers,
    movement. That list is the point: a rebuild sets these from the game, and a
    property nobody had described could not be set at all.
    """
    properties = [
        Property("FadI", 1, [scalar(0x0A, 0)]),
        Property("FadO", 1, [scalar(0x0A, 0)]),
        Property("AltV", 1, [scalar(0x0A, 0)]),
        Property("Keyw", 0, [inherited(TYPE_VOID), string(b"\x00", 1)]),
        Property("ItNa", 1, [inherited(TYPE_VOID), string(name, 1)]),
        Property("ItIc", 1, [scalar(0x0B, 0x03F9)]),
        Property(
            "InkF",
            1,
            [scalar(0x01, 2), scalar(0x06, 0, 1), scalar(0x08, 0, 2)],
        ),
        Property("AntA", 1, [scalar(0x01, 1)]),
        Property("MFla", 1, [scalar(0x19, 0)]),
        Property("MNew", 1, [scalar(0x0A, 0)]),
        Property("Qual", 1, [scalar(0x0A, 0)]),
        Property(
            "SFlg",
            1,
            [scalar(0x01, 2), scalar(0x01, 2, 1), scalar(0x05, 3, 2)],
        ),
        Property("CFlg", 1, [scalar(0x19, 1)]),
        Property("DFlg", 0, [scalar(0x19, 1)]),
        Property("BFlg", 1, [scalar(0x01, 2), scalar(0x01, 1, 1)]),
        Property("Colo", 1, [scalar(0x0D, 0x00FFFFFF)]),
        Property("Visi", 1, [scalar(0x01, 2)]),
        Property("SFFg", 0, [inherited(0x19)]),
    ]
    return ClassBlock("LActiveItem", properties).pack()

APPLICATION_PROP_PAIRS = APPLICATION_PROP_PAIRS_98 + ((b"VIfo", b"OFVa"),)

FRAME_PROP_PAIRS = FRAME_PROP_PAIRS_98

ACTIVE_PROP_PAIRS = ACTIVE_PROP_PAIRS_98 + ((b"SFFg", b"LFFs"),)

OBJECT_LIST_CLASS = b"class cHandleItemList<class LFrameItem>"

INSTANCE_LIST_CLASS = b"class cHandleItemList<class LFrameItemInstance>"

COILIST_CLASS = b"class COIList"

ACTIVE_EDITOR_ICON_HANDLE = 4

DEFAULT_ICON_QUEUE = (0, 1, 0, 1)

def active_object_record() -> bytes:
    """An empty Active object's record, ready to be filled from the game."""
    from klikback.core.common.multi_animation_reconstruct import editor_animation_set

    animations = [
        {
            "animation_id": 0,
            "name": b"Stopped",
            "directions": [
                {
                    "direction_id": 0,
                    "minimum_speed": 50,
                    "maximum_speed": 50,
                    "repeat": 1,
                    "repeat_frame": 0,
                    "image_ids": [1],
                }
            ],
        }
    ]
    return (
        b"Actv" + struct.pack("<II", 0, 0)
        + active_item_block()
        + prop_index(ACTIVE_PROP_PAIRS, PROP_INDEX_OPENER)
        + struct.pack("<I", 0)
        + b"icnI" + struct.pack("<I", ACTIVE_EDITOR_ICON_HANDLE)
        + editor_animation_set(animations)
    )

def frame_body() -> bytes:
    """A frame's contents — object list, placements and event region."""
    from klikback.core.common.object_reconstruct import event_object_record

    return (
        instance_record()
        + b"evpg" + bytes((0x00, 0x03, 0x01, 0x00))
        + b"EvOb" + counted(COILIST_CLASS) + struct.pack("<I", 1)
        + event_object_record(0, b"Active\x00")
        + b"EvEd" + struct.pack("<H", 0)
        + b"EvTe" + struct.pack("<H", 0)
        + b"EvCs" + struct.pack("<I", 16) + bytes(16)
        + b"!DNE" + struct.pack("<II", 2, 2)
        + counted(b"nil") + counted(b"nil")
        + struct.pack("<I", 0)
        + b"icnQ" + struct.pack("<I", len(DEFAULT_ICON_QUEUE))
        + b"".join(
            b"Imag" + struct.pack("<I", handle) for handle in DEFAULT_ICON_QUEUE
        )
    )

def frame_span(item_id: int = 0) -> bytes:
    """Where one frame begins and ends inside the container."""
    return (
        b"Fram" + struct.pack("<II", 0, 0)
        + frame_block()
        + prop_index(FRAME_PROP_PAIRS, PROP_INDEX_OPENER)
        + struct.pack("<I", item_id)
        + b"Pltt" + bytes((0x00, 0x01, 0x00, 0x00)) + flagged_project_palette()
        + counted(OBJECT_LIST_CLASS) + struct.pack("<I", 1)
        + active_object_record()
        + counted(INSTANCE_LIST_CLASS) + struct.pack("<I", 1)
        + frame_body()
    )

LAYOUT_LEAD_WORDS = (864, 2)

LAYOUT_TRAILING_WORDS = (1, 0x1F80, 32, 126, 289, 630)

FILLER_AFTER_CLASS_68 = (101, 3)

FILLER_BEFORE_CLASS_84 = (88,)

def window_layout(frame_editor_item_id: int = 0) -> bytes:
    """The editor's saved window arrangement, which a project carries and restores.
    """
    return (
        struct.pack(f"<{len(LAYOUT_LEAD_WORDS)}I", *LAYOUT_LEAD_WORDS)
        + window_record(68, -1, 1, (0, 26, 1292, 488))
        + struct.pack("<2I", *FILLER_AFTER_CLASS_68)
        + window_record(60, frame_editor_item_id, 3, (52, 52, 1083, 497))
        + struct.pack("<I", *FILLER_BEFORE_CLASS_84)
        + window_record(84, -1, 0, (1536, 841, 1716, 1191))
        + struct.pack(f"<{len(LAYOUT_TRAILING_WORDS)}I", *LAYOUT_TRAILING_WORDS)
    )

def editor_tail(project_path: str = NEUTRAL_PROJECT_PATH) -> bytes:
    """The editor-only records that close a project file."""
    encoded = project_path.encode("latin-1")
    return (
        counted(encoded)
        + bytes(1)
        + PATH_TO_LAYOUT_FILLER
        + window_layout()
    )

def synthesise_scaffold(
    *,
    project_path: str = NEUTRAL_PROJECT_PATH,
    icon_records: tuple[bytes, ...] = (),
    image_records: tuple[bytes, ...] = (),
) -> bytes:
    """Build the empty starting project and return its bytes."""
    return (
        container_header()
        + empty_simple_bank(b"ATNF")
        + empty_simple_bank(b"APMS")
        + empty_simple_bank(b"ASUM")
        + agmi_bank(WIN32_HALFTONE_PALETTE, tuple(icon_records))
        + agmi_bank(DEFAULT_PROJECT_PALETTE, tuple(image_records))
        + POST_BANKS_PAD
        + application_block()
        + prop_index(APPLICATION_PROP_PAIRS, PROP_INDEX_OPENER)
        + extension_list()
        + b"FrmL" + struct.pack("<I", 1)
        + frame_span()
        + editor_tail(project_path)
    )

def blank_image_record(handle: int, width: int, height: int) -> bytes:
    """An empty image entry, of the shape the banks expect."""
    from klikback.core.common.animation_reconstruct import rle_encode_pixels

    encoded = rle_encode_pixels([b"\x00\x00\x00"] * (width * height))
    return (
        struct.pack("<IIHI", handle, 0, 0, len(encoded))
        + struct.pack("<HH", width, height)
        + bytes((0x04, 0x01))
        + bytes(8)
        + encoded
    )

def placeholder_artwork() -> tuple[tuple[bytes, ...], tuple[bytes, ...]]:
    """The stand-in images an empty project carries until real artwork replaces them.
    """
    from klikback.core.common.icon_generate import OTHER_ICON_ART, build_icon_record
    from klikback.core.mmf15.icon_generate import artwork_icon_record_15, frame_preview_record

    icon_records = (
        build_icon_record(0, 0, 32, 32, [0] * 1024),
        build_icon_record(1, 0, 16, 16, [0] * 256),
        frame_preview_record(2, 0x00FFFFFF),
        artwork_icon_record_15(OTHER_ICON_ART, ACTIVE_EDITOR_ICON_HANDLE),
    )
    image_records = (blank_image_record(1, 32, 32),)
    return icon_records, image_records

def product_scaffold_bytes(project_path: str = NEUTRAL_PROJECT_PATH) -> bytes:
    """The starting project as the pipeline uses it, artwork placeholders included.
    """
    icon_records, image_records = placeholder_artwork()
    return synthesise_scaffold(
        project_path=project_path,
        icon_records=icon_records,
        image_records=image_records,
    )
