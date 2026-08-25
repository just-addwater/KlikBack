# GENERATED — do not edit by hand. This file is produced by KlikBack's
# sync tooling; changes belong in the source it is generated from.
#
# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""Emit the per-object-type record heads a 1.5 rebuild patches, field by field.

The 1.5 half of the template story. Each object type carries a record head of
its own — its properties and their descriptors — and a rebuild needs a
neutral one of each to fill in from the recovered game.

These are **emitted from named fields** rather than extracted from saved
projects found on the machine. Beyond anything else, that removes a real
hazard: a selection that reads whatever projects happen to be lying in a
folder will silently pick a different donor when the folder's contents
change, and the resulting difference is invisible until something opens
wrong.
"""

from __future__ import annotations
from pathlib import Path
from klikback.core.mmf15.cca import ClassBlock, Property, TYPE_VOID
from klikback.core.mmf15.scaffold_synthesis import PROP_INDEX_OPENER, inherited, scalar, string
from klikback.core.common.scaffold_synthesis import prop_index
import struct

REPO = Path(__file__).resolve().parents[1]

DONOR_ROOT = Path("donors")

TEMPLATE_BUILD = 119

BACKDROP_KIND = b"BkDr"

QUICK_BACKDROP_KIND = b"DrBa"

COUNTER_KIND = b"Cntr"

LIVES_KIND = b"Lves"

SCORE_KIND = b"Scrs"

QANDA_KIND = b"Qstn"

STRING_KIND = b"Strg"

FORMATTED_TEXT_KIND = b"RTF "

SUBAPPLICATION_KIND = b"CCAx"

EXTENSION_KIND = b"Xtnd"

NEUTRAL_OBJECT_NAME = b"Template object\x00"

TITLE_DONOR_FILES = ()

def keyword_property() -> Property:
    """The property holding an object's search keywords."""
    return Property("Keyw", 0, [inherited(TYPE_VOID), string(b"\x00", 1)])

def name_property(name: bytes) -> Property:
    """The property holding an object's name."""
    return Property("ItNa", 1, [inherited(TYPE_VOID), string(name, 1)])

def icon_property() -> Property:
    """The property holding an object's editor icon."""
    return Property("ItIc", 1, [scalar(0x0B, 0x03F9)])

def ink_property(unknown: int = 1) -> Property:
    """The property holding how an object is drawn over what is behind it."""
    return Property(
        "InkF",
        unknown,
        [scalar(0x01, 2), scalar(0x06, 0, 1), scalar(0x08, 0, 2)],
    )

def antialias_property(unknown: int = 1) -> Property:
    """The property holding whether an object's edges are smoothed."""
    return Property("AntA", unknown, [scalar(0x01, 1)])

def movement_flags_property(unknown: int = 1) -> Property:
    """The property holding an object's movement flags."""
    return Property("MFla", unknown, [scalar(0x19, 0)])

def obstacle_property() -> Property:
    """The property holding what an object collides with."""
    return Property(
        "Obst",
        1,
        [inherited(TYPE_VOID), scalar(0x06, 0, 1), scalar(0x01, 1, 2)],
    )

def movement_family(
    *,
    mnew_unknown: int = 1,
    sflg_unknown: int = 1,
    dflg_word: int,
    dflg_unknown: int = 1,
    bflg_unknown: int = 1,
    colo_unknown: int = 1,
    visi_unknown: int = 1,
    sffg_unknown: int = 0,
) -> list[Property]:
    """Which movement group an object's type belongs to."""
    return [
        Property("MNew", mnew_unknown, [scalar(0x0A, 0)]),
        Property("Qual", 1, [scalar(0x0A, 0)]),
        Property(
            "SFlg",
            sflg_unknown,
            [scalar(0x01, 2), scalar(0x01, 2, 1), scalar(0x05, 3, 2)],
        ),
        Property("CFlg", 0, [scalar(0x19, 1)]),
        Property("DFlg", dflg_unknown, [scalar(0x19, dflg_word)]),
        Property("BFlg", bflg_unknown, [scalar(0x01, 2), scalar(0x01, 1, 1)]),
        Property("Colo", colo_unknown, [scalar(0x0D, 0x00FFFFFF)]),
        Property("Visi", visi_unknown, [scalar(0x01, 2)]),
        Property("SFFg", sffg_unknown, [scalar(0x19, 0)]),
    ]

MOVEMENT_PROP_PAIRS = (
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
    (b"SFFg", b"LFFs"),
)

BACKDROP_PROP_PAIRS = (
    (b"Keyw", b"\xd4BIL"),
    (b"ItNa", b"TITi"),
    (b"ItIc", b"NCIi"),
    (b"InkF", b"XFIi"),
    (b"MFla", b"MEMi"),
    (b"Obst", b"SBOs"),
)

COUNTER_PROP_PAIRS = ((b"Valu", b"LAVc"),) + MOVEMENT_PROP_PAIRS

PLAYER_PROP_PAIRS = MOVEMENT_PROP_PAIRS + ((b"Play", b"YLPc"),)

FTEXT_PROP_PAIRS = ((b"RCol", b"PSDr"),) + MOVEMENT_PROP_PAIRS

COUNTER_MINIMUM = 0xC4653601

COUNTER_MAXIMUM = 0x3B9AC9FF

def backdrop_block() -> bytes:
    """A neutral Backdrop — a picture placed in the frame."""
    return ClassBlock(
        "LBackdropItem",
        [
            keyword_property(),
            name_property(b"Backdrop\x00"),
            icon_property(),
            ink_property(),
            antialias_property(),
            movement_flags_property(),
            obstacle_property(),
        ],
    ).pack()

def quick_backdrop_block() -> bytes:
    """A neutral Quick Backdrop — a shape or fill rather than a stored image.
    """
    return ClassBlock(
        "LDrawBackItem",
        [
            keyword_property(),
            name_property(b"Quick Backdrop\x00"),
            icon_property(),
            ink_property(),
            antialias_property(),
            movement_flags_property(),
            obstacle_property(),
        ],
    ).pack()

def counter_block() -> bytes:
    """A neutral Counter."""
    return ClassBlock(
        "LCounterItem",
        [
            Property(
                "Valu",
                1,
                [
                    inherited(TYPE_VOID),
                    scalar(0x1E, 0, 1),
                    inherited(TYPE_VOID, 2),
                    scalar(0x1E, COUNTER_MINIMUM, 3),
                    inherited(TYPE_VOID, 4),
                    scalar(0x1E, COUNTER_MAXIMUM, 5),
                ],
            ),
            keyword_property(),
            name_property(b"Counter\x00"),
            icon_property(),
            ink_property(),
            antialias_property(),
            movement_flags_property(),
            *movement_family(dflg_word=0),
        ],
    ).pack()

def lives_block() -> bytes:
    """A neutral Lives display."""
    return ClassBlock(
        "LLivesItem",
        [
            keyword_property(),
            name_property(b"Lives\x00"),
            icon_property(),
            ink_property(),
            antialias_property(),
            movement_flags_property(),
            *movement_family(dflg_word=0),
            Property("Play", 1, [scalar(0x06, 0, 1)]),
        ],
    ).pack()

def score_block() -> bytes:
    """A neutral Score display."""
    return ClassBlock(
        "LScoreItem",
        [
            keyword_property(),
            name_property(b"Score\x00"),
            icon_property(),
            ink_property(),
            antialias_property(),
            movement_flags_property(),
            *movement_family(dflg_word=0),
            Property("Play", 1, [scalar(0x06, 0, 1)]),
        ],
    ).pack()

def qanda_block() -> bytes:
    """A neutral Question & Answer object."""
    return ClassBlock(
        "LQuestionItem",
        [
            keyword_property(),
            name_property(b"Question & Answer\x00"),
            icon_property(),
            ink_property(0),
            antialias_property(0),
            movement_flags_property(0),
            *movement_family(
                mnew_unknown=0, sflg_unknown=0, dflg_word=1, dflg_unknown=0,
                bflg_unknown=0, colo_unknown=0,
            ),
        ],
    ).pack()

def string_block() -> bytes:
    """A neutral String object."""
    return ClassBlock(
        "LStringItem",
        [
            keyword_property(),
            name_property(b"String\x00"),
            icon_property(),
            ink_property(),
            antialias_property(),
            movement_flags_property(),
            *movement_family(dflg_word=1),
        ],
    ).pack()

def ftext_block() -> bytes:
    """A neutral Formatted Text object."""
    return ClassBlock(
        "LRTFItem",
        [
            Property("RCol", 1, [scalar(0x0D, 0x00FFFFFF)]),
            Property("ROpt", 1, [scalar(0x19, 1)]),
            keyword_property(),
            name_property(b"Formatted Text\x00"),
            icon_property(),
            ink_property(),
            antialias_property(),
            movement_flags_property(0),
            *movement_family(dflg_word=1, sffg_unknown=1),
        ],
    ).pack()

def subapplication_block() -> bytes:
    """A neutral Sub-Application — a project embedded inside another."""
    return ClassBlock(
        "LCCAItem",
        [
            keyword_property(),
            name_property(b"Sub-Application\x00"),
            icon_property(),
            ink_property(0),
            antialias_property(0),
            movement_flags_property(0),
            *movement_family(
                sflg_unknown=0, dflg_word=1, dflg_unknown=0, bflg_unknown=0,
                sffg_unknown=1,
            ),
        ],
    ).pack()

def extension_block() -> bytes:
    """A neutral extension object, for the modules a game brings its own code for.

    The stored name is a placeholder rather than a type label like the other
    heads carry. This one head was proven against a saved project whose extension
    object is named after a third party's product, and a template holds a neutral
    value anywhere a real project would hold something particular to its author.
    The field is inert either way: every record built writes the target object's
    own name over it.
    """
    return ClassBlock(
        "LExtendItem",
        [
            keyword_property(),
            name_property(NEUTRAL_OBJECT_NAME),
            icon_property(),
            ink_property(0),
            antialias_property(0),
            movement_flags_property(0),
            *movement_family(
                mnew_unknown=0, sflg_unknown=0, dflg_word=1, dflg_unknown=0,
                bflg_unknown=0, colo_unknown=0, visi_unknown=0, sffg_unknown=1,
            ),
        ],
    ).pack()

TEMPLATE_SPECS: dict[bytes, tuple] = {
    BACKDROP_KIND: (backdrop_block, BACKDROP_PROP_PAIRS, 2),
    QUICK_BACKDROP_KIND: (quick_backdrop_block, BACKDROP_PROP_PAIRS, 4),
    COUNTER_KIND: (counter_block, COUNTER_PROP_PAIRS, 4),
    LIVES_KIND: (lives_block, PLAYER_PROP_PAIRS, 2),
    SCORE_KIND: (score_block, PLAYER_PROP_PAIRS, 2),
    QANDA_KIND: (qanda_block, MOVEMENT_PROP_PAIRS, 2),
    STRING_KIND: (string_block, MOVEMENT_PROP_PAIRS, 2),
    FORMATTED_TEXT_KIND: (ftext_block, FTEXT_PROP_PAIRS, 2),
    SUBAPPLICATION_KIND: (subapplication_block, MOVEMENT_PROP_PAIRS, 2),
    EXTENSION_KIND: (extension_block, MOVEMENT_PROP_PAIRS, 2),
}

TEMPLATE_DONORS: dict[bytes, str] = {}

def synthesised_template(kind: bytes) -> tuple[bytes, int]:
    """The neutral record head for one object type."""
    builder, pairs, icon = TEMPLATE_SPECS[kind]
    head = (
        kind
        + struct.pack("<II", 0, 0)
        + builder()
        + prop_index(pairs, PROP_INDEX_OPENER)
    )
    return head, icon

def donor_bytes(kind: bytes) -> bytes:
    """Read the one record part the emitted templates do not describe.

    Everything else about a template is written out field by field. A single
    piece — an object type's editor icon record — is not yet described well
    enough to emit, so it is read from a reference project if one has been
    supplied. Nothing on KlikBack's own path asks for it, and where no reference
    exists this says so plainly rather than substituting something else.
    """
    _builder, _pairs, _icon = TEMPLATE_SPECS[kind]

    filename = TEMPLATE_DONORS.get(kind)
    if filename is None:
        raise FileNotFoundError(
            f"no class-head donor is named for {kind!r} -- its editor icon "
            f"record is the one part of the template the synthesis does not "
            f"describe, so there is nothing to read it from"
        )
    path = DONOR_ROOT / filename
    if not path.exists():
        raise FileNotFoundError(
            f"the class-head donor {path} is missing -- its editor icon "
            f"record is the one part of the {kind!r} template the synthesis "
            f"does not describe"
        )
    return path.read_bytes()
