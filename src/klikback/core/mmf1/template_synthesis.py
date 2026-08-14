# GENERATED — do not edit by hand. This file is produced by KlikBack's
# sync tooling; changes belong in the source it is generated from.
#
# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""Emit the per-object-type record templates a 1.0 rebuild patches, field by field.

Each object type an editor knows — Active, Backdrop, Quick Backdrop, String,
Counter, Lives, Score, Formatted Text, Question & Answer, Sub-Application —
has a record shape of its own. A rebuild needs a neutral one of each to fill
in from the game.

Like the base project, these are **emitted from named fields**, through the
container's proven record grammar. The test is the same either way: a
template can only be emitted if every field in it can be named.
"""

from __future__ import annotations
import struct
from klikback.core.mmf1.container import ClassBlock98, Entry98, Property98, TYPE_VOID
from klikback.core.common.scaffold_synthesis import blob, counted, inherited, prop_index, scalar, string

MODULE_SIGNATURE = 0x59082516

NEUTRAL_SUBAPPLICATION_PATH = b"C:\\subapplication.cca"

def record(
    kind: bytes,
    block: bytes,
    pairs,
    tail: bytes,
    scratch: int = 1,
    pair_names: dict[bytes, bytes] | None = None,
) -> bytes:
    """Build one record from named fields, in the container's own grammar."""
    return (
        kind
        + struct.pack("<II", 0, 0)
        + block
        + prop_index(pairs, scratch, pair_names)
        + tail
    )

BEHAVIOUR_PAIR_NAME = {b"LEvt": b"Behavior #1"}

def animation_tail(
    item_id: int, icon: int, image_id: int, name: bytes
) -> bytes:
    """The animation records that close an object able to animate."""
    return (
        struct.pack("<I", item_id)
        + b"icnI" + struct.pack("<I", icon)
        + b"AnSt" + struct.pack("<I", 1)
        + b"Anix" + struct.pack("<I", 1)
        + b"Dirx" + struct.pack("<I", 1)
        + b"Imag" + struct.pack("<I", image_id)
        + struct.pack("<IIIIII", 0, 50, 50, 1, 0, 0)
        + struct.pack("<I", 0)
        + counted(name)
    )

def counter_tail(
    item_id: int, icon: int, image_ids: tuple[int, ...], trailer: bytes
) -> bytes:
    """The records that close a Counter: its icon and the pictures it displays with.
    """
    out = (
        struct.pack("<I", item_id)
        + b"icnI" + struct.pack("<I", icon)
        + b"ImSt" + struct.pack("<I", len(image_ids))
    )
    for image_id in image_ids:
        out += b"Imag" + struct.pack("<I", image_id)
    return out + trailer

DEFAULT_RTF_DOCUMENT = (
    b"{\\rtf1\\ansi\\deff0{\\fonttbl{\\f0\\froman Times New Roman;}\r\n}\r\n"
    b"{\\colortbl;"
    b"\\red0\\green0\\blue255;\\red0\\green255\\blue255;"
    b"\\red0\\green255\\blue0;\\red255\\green0\\blue255;"
    b"\\red255\\green0\\blue0;\\red255\\green255\\blue0;"
    b"\\red255\\green255\\blue255;\\red0\\green0\\blue128;"
    b"\\red0\\green128\\blue128;\\red0\\green128\\blue0;"
    b"\\red128\\green0\\blue128;\\red128\\green0\\blue0;"
    b"\\red128\\green128\\blue0;\\red128\\green128\\blue128;"
    b"\\red192\\green192\\blue192;}\r\n"
    b"\\pard\\plain\\f0\\fs20 \\par\r\n}\r\n"
)

def active_block(scratch: int, static_movement: bool) -> bytes:
    """A neutral Active object, the type that carries movement and animation.
    """
    properties = [
        Property98("FadI", 1, [scalar(0x0A, 0)]),
        Property98("FadO", 1, [scalar(0x0A, 0)]),
        Property98("AltV", 1, [scalar(0x0A, 0)]),
        Property98("Keyw", 0, [inherited(TYPE_VOID), string(b"\x00", 1)]),
        Property98("ItNa", 1, [inherited(TYPE_VOID), string(b"Active\x00", 1)]),
        Property98("ItIc", 1, [scalar(0x0B, 0x3F9)]),
        Property98(
            "InkF", 1, [scalar(0x01, 2), scalar(0x06, 0, 1), scalar(0x08, 0, 2)]
        ),
        Property98("AntA", 1, [scalar(0x01, 1)]),
        Property98("MFla", 1, [scalar(0x19, 0)]),
        Property98("MNew", 1, [scalar(0x0A, 0)]),
        Property98("Qual", 1, [scalar(0x0A, 0)]),
        Property98(
            "SFlg", 1, [scalar(0x01, 2), scalar(0x01, 2, 1), scalar(0x05, 3, 2)]
        ),
        Property98("CFlg", 1, [scalar(0x19, 1)]),
        Property98("DFlg", 0, [scalar(0x19, 1)]),
        Property98("BFlg", 1, [scalar(0x01, 2), scalar(0x01, 1, 1)]),
        Property98("Colo", 1, [scalar(0x0D, 0x00FFFFFF)]),
        Property98("Visi", 1, [scalar(0x01, 2)]),
    ]
    if static_movement:

        properties.append(
            Property98(
                "MSta",
                1,
                [
                    blob(
                        0x0A,
                        b"\x00\x00\x00\x00\x01\x00\x00\x00\xff\xff\xff\xff"
                        + bytes(14),
                    )
                ],
            )
        )
    return ClassBlock98("LActiveItem", scratch, properties).pack()

ACTIVE_PROP_PAIRS = (
    (b"FadI", b"NIFf"),
    (b"FadO", b"UOFf"),
    (b"AltV", b"LAVd"),
    (b"Keyw", b"\xd4BIL"),
    (b"ItNa", b"TITi"),
    (b"ItIc", b"NCIi"),
    (b"InkF", b"XFIi"),
    (b"MFla", b"MEMi"),
    (b"MNew", b"WNMd"),
    (b"MSta", b"ATSd"),
    (b"MBal", b"LABd"),
    (b"MPla", b"ALPd"),
    (b"MMou", b"UOMd"),
    (b"MPat", b"TAPd"),
    (b"MGen", b"NEGd"),
    (b"MRac", b"CARd"),
    (b"LEvt", b"TVEd"),
    (b"Qual", b"AUQd"),
    (b"SFlg", b"RCSd"),
    (b"CFlg", b"LOCd"),
    (b"DFlg", b"PSDd"),
)

COMMON_PROP_PAIRS = ACTIVE_PROP_PAIRS[3:]

COUNTER_PROP_PAIRS = COMMON_PROP_PAIRS + ((b"Play", b"YLPc"),)

PAINT_PROP_PAIRS = (
    (b"Keyw", b"\xd4BIL"),
    (b"ItNa", b"TITi"),
    (b"ItIc", b"NCIi"),
    (b"InkF", b"XFIi"),
    (b"MFla", b"MEMi"),
    (b"Obst", b"SBOs"),
)

FTEXT_PROP_PAIRS = ((b"RCol", b"PSDr"),) + COMMON_PROP_PAIRS

def common_head(name: bytes, *, keyw_unknown: int = 0) -> list[Property98]:
    """The head every object record shares — id, name, type and flags."""
    return [
        Property98("Keyw", keyw_unknown, [inherited(TYPE_VOID), string(b"\x00", 1)]),
        Property98("ItNa", 1, [inherited(TYPE_VOID), string(name, 1)]),
        Property98("ItIc", 1, [scalar(0x0B, 0x3F9)]),
    ]

def backdrop_block() -> bytes:
    """A neutral Backdrop — a picture placed in the frame."""
    properties = common_head(b"Backdrop\x00") + [
        Property98(
            "InkF", 1, [scalar(0x01, 2), scalar(0x06, 0, 1), scalar(0x08, 0, 2)]
        ),
        Property98("AntA", 1, [scalar(0x01, 1)]),
        Property98("MFla", 1, [scalar(0x19, 0)]),

        Property98(
            "Obst",
            1,
            [Entry98(TYPE_VOID, 0, 0, 1, 1), scalar(0x06, 1, 1), scalar(0x01, 1, 2)],
        ),
    ]
    return ClassBlock98("LBackdropItem", 0x6C0, properties).pack()

def quickb_block() -> bytes:
    """A neutral Quick Backdrop — a shape or fill rather than a stored image.
    """
    properties = common_head(b"Quick Backdrop\x00") + [
        Property98(
            "InkF", 1, [scalar(0x01, 2), scalar(0x06, 0, 1), scalar(0x08, 0, 2)]
        ),
        Property98("AntA", 1, [scalar(0x01, 1)]),
        Property98("MFla", 1, [scalar(0x19, 0)]),
        Property98(
            "Obst",
            1,
            [inherited(TYPE_VOID), scalar(0x06, 0, 1), scalar(0x01, 1, 2)],
        ),
    ]
    return ClassBlock98("LDrawBackItem", 0x938, properties).pack()

def movement_capable_body(
    unknowns: dict[str, int], dflg_word: int
) -> list[Property98]:
    """The movement fields an object able to move carries."""
    def unknown(tag: str, default: int = 1) -> int:
        return unknowns.get(tag, default)

    return [
        Property98(
            "InkF",
            unknown("InkF"),
            [scalar(0x01, 2), scalar(0x06, 0, 1), scalar(0x08, 0, 2)],
        ),
        Property98("AntA", unknown("AntA"), [scalar(0x01, 1)]),
        Property98("MFla", unknown("MFla"), [scalar(0x19, 0)]),
        Property98("MNew", unknown("MNew"), [scalar(0x0A, 0)]),
        Property98("Qual", 1, [scalar(0x0A, 0)]),
        Property98(
            "SFlg",
            unknown("SFlg"),
            [scalar(0x01, 2), scalar(0x01, 2, 1), scalar(0x05, 3, 2)],
        ),
        Property98("CFlg", 0, [scalar(0x19, 1)]),
        Property98("DFlg", unknown("DFlg"), [scalar(0x19, dflg_word)]),
        Property98(
            "BFlg", unknown("BFlg"), [scalar(0x01, 2), scalar(0x01, 1, 1)]
        ),
        Property98("Colo", unknown("Colo"), [scalar(0x0D, 0x00FFFFFF)]),
        Property98("Visi", unknown("Visi"), [scalar(0x01, 2)]),
    ]

def lives_block() -> bytes:
    """A neutral Lives display."""
    properties = (
        common_head(b"Lives\x00")
        + movement_capable_body({"DFlg": 1}, 0)
        + [Property98("Play", 1, [scalar(0x06, 0, 1)])]
    )
    return ClassBlock98("LLivesItem", 0xEC0, properties).pack()

def score_block() -> bytes:
    """A neutral Score display."""
    properties = (
        common_head(b"Score\x00")
        + movement_capable_body({"DFlg": 1}, 0)
        + [Property98("Play", 1, [scalar(0x06, 0, 1)])]
    )
    return ClassBlock98("LScoreItem", 0xB54, properties).pack()

def ftext_block() -> bytes:
    """A neutral Formatted Text object."""
    properties = [
        Property98("RCol", 1, [scalar(0x0D, 0x00FFFFFF)]),
        Property98("ROpt", 1, [scalar(0x19, 1)]),
    ] + common_head(b"Formatted Text\x00") + movement_capable_body(
        {"MFla": 0, "CFlg": 0, "DFlg": 1}, 1
    )
    return ClassBlock98("LRTFItem", 0xA68, properties).pack()

def qanda_block() -> bytes:
    """A neutral Question & Answer object."""
    properties = common_head(b"Question & Answer\x00") + movement_capable_body(
        {"InkF": 0, "AntA": 0, "MFla": 0, "MNew": 0, "SFlg": 0, "DFlg": 0,
         "BFlg": 0, "Colo": 0}, 1
    )
    return ClassBlock98("LQuestionItem", 0x4AC, properties).pack()

def subapp_block() -> bytes:
    """A neutral Sub-Application — a project embedded inside another."""
    properties = common_head(b"Sub-Application\x00") + movement_capable_body(
        {"InkF": 0, "AntA": 0, "MFla": 0, "SFlg": 0, "DFlg": 0, "BFlg": 0}, 1
    )
    return ClassBlock98("LCCAItem", 0x530, properties).pack()

def xtnd_block() -> bytes:
    """A neutral extension object, for the modules a game brings its own code for.
    """
    properties = common_head(b"Template object\x00") + movement_capable_body(
        {"InkF": 0, "AntA": 0, "MFla": 0, "MNew": 0, "SFlg": 0, "DFlg": 0,
         "BFlg": 0, "Colo": 0, "Visi": 0}, 1
    )
    return ClassBlock98("LExtendItem", 0xA60, properties).pack()

def qanda_button(text: bytes) -> bytes:
    """One of a Question & Answer object's buttons, with its caption."""
    return (
        struct.pack("<iIIII", -1, 0, 0x25, 0, 1) + counted(text)
        + struct.pack("<I", 0)
    )

def solo_head(name: bytes) -> list[Property98]:
    """The three properties every standalone object record opens with."""
    return [
        Property98("Keyw", 0, [inherited(TYPE_VOID), string(b"\x00", 1)]),
        Property98("ItNa", 1, [Entry98(TYPE_VOID, 0, 0, 1, 1), string(name, 1)]),
        Property98("ItIc", 1, [scalar(0x0B, 0x3F9)]),
    ]

def counter_solo_block() -> bytes:
    """A neutral Counter, in the standalone form."""
    properties = (
        [
            Property98(
                "Valu",
                1,
                [
                    Entry98(TYPE_VOID, 0, 0, 1, 1), scalar(0x1E, 37, 1),
                    Entry98(TYPE_VOID, 2, 0, 1, 1), scalar(0x1E, 0, 3),
                    Entry98(TYPE_VOID, 4, 0, 1, 1), scalar(0x1E, 125, 5),
                ],
            )
        ]
        + solo_head(b"Health\x00")
        + movement_capable_body({"DFlg": 1}, 0)
        + [Property98("LEvt", 1, [inherited(0x0A)])]
    )
    return ClassBlock98("LCounterItem", 0x8A0, properties).pack()

def string_solo_block() -> bytes:
    """A neutral String object, in the standalone form."""
    properties = (
        solo_head(b"Message\x00")
        + movement_capable_body({"MFla": 0, "DFlg": 1}, 1)
        + [Property98("LEvt", 1, [inherited(0x0A)])]
    )
    return ClassBlock98("LStringItem", 0x88C, properties).pack()

def counter_solo_template() -> bytes:
    """A neutral Counter in the standalone form, ready to be filled from a game.
    """
    image_list = b"".join(
        b"Imag" + struct.pack("<I", image_id) for image_id in range(14)
    )
    return record(
        b"Cntr",
        counter_solo_block(),
        ((b"Valu", b"LAVc"),) + COMMON_PROP_PAIRS,
        struct.pack("<I", 0)
        + b"icnI" + struct.pack("<I", 4)
        + struct.pack("<III", 1, 2, 0)
        + counted(b"Sfll" + bytes((0x80, 0x80, 0x80, 0x00)))
        + b"ImSt" + struct.pack("<I", 14) + image_list
        + struct.pack("<II", 0x60, 0x20),
        pair_names=BEHAVIOUR_PAIR_NAME,
    )

def string_solo_template() -> bytes:
    """A neutral String in the standalone form, ready to be filled from a game.
    """
    return record(
        b"Strg",
        string_solo_block(),
        COMMON_PROP_PAIRS,
        struct.pack("<I", 0)
        + b"icnI" + struct.pack("<I", 2)
        + struct.pack("<IIi", 150, 20, -1)
        + bytes(12)
        + struct.pack("<I", 1)
        + counted(b"READY - 98")
        + struct.pack("<I", 0),
        pair_names=BEHAVIOUR_PAIR_NAME,
    )

def synthesised_templates() -> dict[str, bytes]:
    """Every per-type template, ready to be filled from a recovered object.

    One neutral record per object type — Active, Backdrop, Quick Backdrop, Lives,
    Score, Formatted Text, Question & Answer, Sub-Application, extension — each
    written out **field by field from named values**, not extracted from a project
    found on the machine. Every value in them is here to read: which properties the
    type carries, what the editor's own defaults are for each, and what the type's
    tail looks like.

    Two of them exist in a pair rather than singly, because the record's shape
    genuinely differs: an Active that carries a movement and one that does not are
    not the same record with a flag flipped.

    Anywhere a real project would hold something particular to its author — a
    Sub-Application's path to its child file, an extension's module name — the
    template holds a neutral value instead. Those fields are rewritten for every
    record actually emitted, so what is here is scaffolding rather than content;
    keeping it neutral means a field nobody rewrote still says nothing in
    particular.
    """
    return {
        "active": record(
            b"Actv",
            active_block(0x9D4, static_movement=False),
            ACTIVE_PROP_PAIRS,
            animation_tail(0, icon=4, image_id=1, name=b"Stopped"),
        ),
        "active_movement": record(
            b"Actv",
            active_block(0xA04, static_movement=True),
            ACTIVE_PROP_PAIRS,
            animation_tail(0, icon=2, image_id=0, name=b""),
        ),
        "backdrop": record(
            b"BkDr",
            backdrop_block(),
            PAINT_PROP_PAIRS,

            struct.pack("<I", 1) + b"icnI" + struct.pack("<II", 5, 3),
            scratch=0x64650001,
        ),
        "quickb": record(
            b"DrBa",
            quickb_block(),
            PAINT_PROP_PAIRS,
            struct.pack("<I", 0)
            + b"icnI" + struct.pack("<I", 5)

            + struct.pack("<II", 2, 0)
            + counted(b"Sfll" + bytes((0x80, 0x80, 0x80, 0x00)))
            + struct.pack("<II", 100, 100),
        ),
        "lives": record(
            b"Lves",
            lives_block(),
            COUNTER_PROP_PAIRS,
            counter_tail(0, 5, tuple(range(1, 15)), struct.pack("<II", 0x60, 0x20)),
        ),
        "score": record(
            b"Scrs",
            score_block(),
            COUNTER_PROP_PAIRS,
            counter_tail(0, 4, tuple(range(10)) + (14, 11, 12, 13), b""),
        ),
        "ftext": record(
            b"RTF ",
            ftext_block(),
            FTEXT_PROP_PAIRS,
            struct.pack("<I", 0)
            + b"icnI" + struct.pack("<I", 2)
            + struct.pack("<II", 100, 100)
            + counted(b"class CTE")
            + struct.pack("<I", 0)
            + counted(DEFAULT_RTF_DOCUMENT),
        ),
        "qanda": record(
            b"Qstn",
            qanda_block(),
            COMMON_PROP_PAIRS,
            struct.pack("<I", 0)
            + b"icnI" + struct.pack("<I", 2)
            + struct.pack("<II", 100, 100)
            + qanda_button(b"Question")
            + qanda_button(b"Answer"),
        ),
        "subapp": record(
            b"CCAx",
            subapp_block(),
            COMMON_PROP_PAIRS,
            struct.pack("<I", 0)
            + b"icnI" + struct.pack("<I", 2)
            + counted(NEUTRAL_SUBAPPLICATION_PATH)

            + struct.pack("<III", 0x20, 0x20, 8),
        ),
        "xtnd": record(
            b"Xtnd",
            xtnd_block(),
            COMMON_PROP_PAIRS,
            struct.pack("<I", 0)
            + b"icnI" + struct.pack("<I", 2)
            + counted(b"nil")
            + struct.pack("<i", -1)
            + counted(b"Template.cox")
            + struct.pack("<II", MODULE_SIGNATURE, 0)

            + struct.pack("<HH", 0x0C, 0x0C)
            + bytes(6)
            + struct.pack("<HH", 0x20, 0x20),
        ),
    }
