# GENERATED — do not edit by hand. This file is produced by KlikBack's
# sync tooling; changes belong in the source it is generated from.
#
# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""Emit the empty MMF 1.0 project every rebuild starts from, field by field.

A rebuild needs somewhere to put what it recovers: a valid, empty project of
the right shape. The obvious way to get one is to keep a project somebody
made and patch it — and that is exactly what this module exists to avoid.
Every span of that starting file is emitted here from named fields, through
the same container grammar that reassembles authored projects byte-for-byte.

What follows matters more than the code does: a base project that is
*described* rather than copied is made of spans somebody has read — the test
for "may this be emitted?" is "can we say what it is?", which is the same
test as understanding the format.

That is about a starting point, and it is worth not overstating it into a
claim about the format. The vocabulary a valid file must speak is the
vendor's and does travel: things like the runtime's own class names, the
object type labels and the standard animation slot names. A description of
the format is made of the format's terms, so the constants the editor is
going to look for cannot be avoided.

The starting project stores a neutral location rather than any real one. A
written project records its own path, as the editor expects, which is where
a real path is meant to appear.
"""

from __future__ import annotations
import struct
from klikback.core.mmf1.container import ClassBlock98, Entry98, INHERITED, Property98, TYPE_STRING, TYPE_VOID

WIN32_HALFTONE_PALETTE = bytes.fromhex(
    "00000000800000000080000080800000000080008000800000808000c0c0c000"
    "c0dcc000a6caf00004040400080808000c0c0c0011111100161616001c1c1c00"
    "2222220029292900555555004d4d4d004242420039393900ff7c8000ff505000"
    "d6009300ccecff00efd6c600e7e7d600ada99000330000006600000099000000"
    "cc00000000330000333300006633000099330000cc330000ff33000000660000"
    "336600006666000099660000cc660000ff660000009900003399000066990000"
    "99990000cc990000ff99000000cc000033cc000066cc000099cc0000cccc0000"
    "ffcc000066ff000099ff0000ccff000000003300330033006600330099003300"
    "cc003300ff00330000333300333333006633330099333300cc333300ff333300"
    "00663300336633006666330099663300cc663300ff6633000099330033993300"
    "6699330099993300cc993300ff99330000cc330033cc330066cc330099cc3300"
    "cccc3300ffcc330033ff330066ff330099ff3300ccff3300ffff330000006600"
    "330066006600660099006600cc006600ff006600003366003333660066336600"
    "99336600cc336600ff33660000666600336666006666660099666600cc666600"
    "00996600339966006699660099996600cc996600ff99660000cc660033cc6600"
    "99cc6600cccc6600ffcc660000ff660033ff660099ff6600ccff6600ff00cc00"
    "cc00ff00009999009933990099009900cc009900000099003333990066009900"
    "cc339900ff00990000669900336699006633990099669900cc669900ff339900"
    "339999006699990099999900cc999900ff99990000cc990033cc990066cc6600"
    "99cc9900cccc9900ffcc990000ff990033ff990066cc990099ff9900ccff9900"
    "ffff99000000cc00330099006600cc009900cc00cc00cc00003399003333cc00"
    "6633cc009933cc00cc33cc00ff33cc000066cc003366cc00666699009966cc00"
    "cc66cc00ff6699000099cc003399cc006699cc009999cc00cc99cc00ff99cc00"
    "00cccc0033cccc0066cccc0099cccc00cccccc00ffcccc0000ffcc0033ffcc00"
    "66ff990099ffcc00ccffcc00ffffcc003300cc006600ff009900ff000033cc00"
    "3333ff006633ff009933ff00cc33ff00ff33ff000066ff003366ff006666cc00"
    "9966ff00cc66ff00ff66cc000099ff003399ff006699ff009999ff00cc99ff00"
    "ff99ff0000ccff0033ccff0066ccff0099ccff00ccccff00ffccff0033ffff00"
    "66ffcc0099ffff00ccffff00ff66660066ff6600ffff66006666ff00ff66ff00"
    "66ffff00a50021005f5f5f00777777008686860096969600cbcbcb00b2b2b200"
    "d7d7d700dddddd00e3e3e300eaeaea00f1f1f100f8f8f800fffbf000a0a0a400"
    "80808000ff00000000ff0000ffff00000000ff00ff00ff0000ffff00ffffff00"
)

DEFAULT_PROJECT_PALETTE = bytes.fromhex(
    "00000000800000000080000080800000000080008000800000808000c0c0c000"
    "c0dcc000a6caf000b3f7cf009febc7008be3bf007bd7bb006bcfbb005bc7bb00"
    "feffff00ebebeb00dbdbdb00cbcbcb00bbbbbb00a7a7a7009797970087878700"
    "77777700636363005353530043434300333333001f1f1f000f0f0f0008000000"
    "e3f3fb00cfebfb00bbe3fb00a7dffb0093d7fb006fc3ef0053afe3004b9fcf00"
    "438bb7003b7ba300336b8b002b57770023475f001b374b00132733000b171f00"
    "dbe7fb00c3d7f700abc7f30097b7ef007fa7ef006b97eb005787e7004377e700"
    "3b6bcb00335fb3002b53970023437f001b376700132b4b000b1b3300070f1b00"
    "dbdbef00c3c3e300afafd7009b9bcb008787c3007373b7006363ab0053539f00"
    "474793003b3b8b00333373002b2b5f0023234b00171737000f0f230007070f00"
    "fbdbff00ebbfef00dba7e300cf8fd300bf7bc700b367b700a357ab0097479b00"
    "8b378f00bf00bf006f1f730063176300570b570047074b003b003b002f002f00"
    "ffe7e700ffbfbf00ff979700ff737300ff4b4b00ff232300fe000000e7000000"
    "cb000000b30000009b000000bf0000006b000000530000003b00000023000000"
    "ffdbbb00ffc39300ffaf6f00ff974700ff7f2300fb670000eb630000d75b0000"
    "c3570000af4f00009b3b0000872f0000731f00005f1700004b0b00003b070000"
    "ffffcb00ffff8700ffff4300fff30000efe30000dfcb0000cfb30700c39b0700"
    "b3870700bfbf000093630700875307007747070067370700572b07004b230700"
    "e3ffdb00cbefbf00b3dfa7009fcf8f008bc3770077b3670067a3530057934300"
    "478733003b7727002f671b00235b13001b4b0b00133b07000b2b0000071f0000"
    "cff3cb00abe3a7008bd383006bc7670053b74b0037ab3300239b1f000f8b0b00"
    "00bf0000006f0000005f000000530000004300000037000000270000001b0000"
    "dbff7b00c7ef6300b3df4b00a3d337008fc327007fb717006fa70b005f9b0000"
    "23eb1f0023d71f0027c7230027b7230027a323002793230023831f001f731f00"
    "00e3e30000cbcb0000b3b300009b9b0000bfbf00006b6b0000535300003f3f00"
    "ffefcb00ffe7bf00ffe3b300ffdba700ffd79f00ffcf9300ffc78700ffbf7f00"
    "ffb37300efa36700df8f5b00d3835300c3734b00b7674300a7573b00974b3300"
    "8b3f2b007b3323006f2b1f005f1f17004f17130043130f00330b0b0027070700"
    "e7f7cf00dff7cf00cff7cf00cff7db00cbf3e300c7f3ef00c7ebf300c7dfef00"
    "c7d7eb00c7cfe700fbef9700f7e78700f7df7b00f7d76b00f7cf5f00f7c34f00"
    "f7bb4300f3af3300f39f2700f3931700f3870b00f3770000fffbf000a0a0a400"
    "80808000ff00000000ff0000ffff00000000ff00ff00ff0000ffff00ffffff00"
)

PALETTE_FLAG = 0x04

PALETTE_FLAGGED_RANGE = range(10, 246)

def flagged_project_palette() -> bytes:
    """The project's default colour palette, as a described table rather than a copy.
    """
    table = bytearray(DEFAULT_PROJECT_PALETTE)
    for entry in PALETTE_FLAGGED_RANGE:
        table[entry * 4 + 3] = PALETTE_FLAG
    return bytes(table)

PRODUCT = ord("T")

MAJOR = 1

STAMP = 0x00010000

BUILD = 87

def container_header() -> bytes:
    """The file's own header: what it is, which build wrote it, how long it runs.
    """
    return b"CnC2" + bytes((PRODUCT, MAJOR)) + struct.pack("<IHH", STAMP, BUILD, 0)

def empty_simple_bank(tag: bytes) -> bytes:
    """A bank with nothing in it yet — the shape, waiting for its contents."""
    return tag + struct.pack("<I", 0)

AGMI_MODE_24BIT = 4

AGMI_HEADER_WORDS = (768, 256)

def agmi_bank(palette: bytes, records: tuple[bytes, ...] = ()) -> bytes:
    """An image bank, empty and ready for the recovered artwork to replace it.
    """
    if len(palette) != 1024:
        raise ValueError("an AGMI palette is 256 four-byte entries")
    return (
        b"AGMI"
        + struct.pack("<IHH", AGMI_MODE_24BIT, *AGMI_HEADER_WORDS)
        + palette
        + struct.pack("<I", len(records))
        + b"".join(records)
    )

POST_BANKS_PAD = bytes(8)

ICON_MODE_BYTES = bytes((0x03, 0x01))

APP_ICON_CONTENT_WORDS = {(32, 32): 0x18496, (16, 16): 0x170ED}

def app_icon_template_head(width: int, height: int) -> bytes:
    """The header of an application icon record, for one of the two icon sizes.
    """
    return (
        struct.pack("<II", 0, APP_ICON_CONTENT_WORDS[(width, height)])
        + struct.pack("<HI", 0, 0)
        + struct.pack("<HH", width, height)
        + ICON_MODE_BYTES
        + bytes(8)
    )

CLASS_SCRATCH = 0x0A8C

PROP_INDEX_SCRATCH = 1

def inherited(type_id: int, index: int = 0) -> Entry98:
    """An entry that takes the default rather than storing a value of its own.

    An MMF project stores "unset" as its own state, distinct from storing a zero,
    and the editor shows the two differently. Keeping the distinction is why a
    rebuilt project's dialogs look like a hand-made one's.
    """
    return Entry98(type_id, index, INHERITED, 1, 1)

def scalar(type_id: int, word: int, index: int = 0) -> Entry98:
    """An entry holding a single number."""
    return Entry98(type_id, index, 0, 1, 1, word)

def blob(type_id: int, payload: bytes, index: int = 0) -> Entry98:
    """An entry holding a block of bytes, with its own length."""
    return Entry98(type_id, index, len(payload), 1, 1, len(payload), payload)

def string(payload: bytes, index: int = 0) -> Entry98:
    """An entry holding text."""
    return Entry98(TYPE_STRING, index, len(payload), 1, 1, None, payload)

DEFAULT_PLAYER_KEYS = (0x26, 0x28, 0x25, 0x27, 0x10, 0x11)

def default_players_payload() -> bytes:
    """The default control settings for the four players."""
    return struct.pack("<4H", 3, 3, 3, 3) + struct.pack(
        "<6H", *DEFAULT_PLAYER_KEYS
    ) * 4

def application_block(title: bytes = b"Application1\x00") -> bytes:
    """The application's own record: its properties, defaults and window settings.
    """
    properties = [
        Property98("WinS", 1, [inherited(0x0F)]),
        Property98("WinO", 1, [inherited(0x19)]),
        Property98("Colo", 1, [inherited(0x0D)]),
        Property98("GEvt", 1, [inherited(0x0A)]),
        Property98("GloV", 1, [inherited(0x0A)]),
        Property98("Menu", 1, [inherited(0x0A)]),
        Property98("Scor", 1, [inherited(TYPE_VOID), inherited(0x1E, 1)]),
        Property98("Live", 1, [inherited(TYPE_VOID), inherited(0x1E, 1)]),
        Property98("Plas", 1, [blob(0x0A, default_players_payload())]),
        Property98("RunO", 1, [inherited(0x19)]),
        Property98(
            "AppI",
            1,
            [
                inherited(TYPE_VOID),
                inherited(0x0B, 1),
                inherited(TYPE_VOID, 2),
                inherited(0x1C, 3),
            ],
        ),
        Property98(
            "Abou",
            1,
            [
                inherited(TYPE_VOID),
                string(title, 1),
                inherited(TYPE_VOID, 2),
                Entry98(TYPE_STRING, 3, INHERITED, 1, 1),
            ],
        ),
        Property98("Hlpf", 1, [inherited(0x0A)]),
        Property98("AppM", 1, [scalar(0x1A, AGMI_MODE_24BIT)]),
        Property98("LibT", 0, [inherited(0x1A)]),
        Property98("Keyw", 0, [inherited(TYPE_VOID), string(b"\x00", 1)]),
    ]
    return ClassBlock98("LApplication", CLASS_SCRATCH, properties).pack()

def frame_block(title: bytes = b"First Frame\x00") -> bytes:
    """One empty frame, with the geometry and palette records a frame carries.
    """
    pale = bytes((0x00, 0x03, 0x00, 0x01)) + flagged_project_palette()
    properties = [
        Property98("Tit", 1, [inherited(TYPE_VOID), string(title, 1)]),
        Property98(
            "Pass",
            1,
            [inherited(TYPE_VOID), Entry98(TYPE_STRING, 1, INHERITED, 1, 1)],
        ),
        Property98("PfSz", 1, [inherited(0x0F)]),
        Property98("Colo", 1, [inherited(0x0D)]),
        Property98("PfOp", 1, [inherited(0x19)]),
        Property98("Pale", 1, [blob(0x0A, pale)]),
        Property98("Evt", 1, [inherited(0x1B)]),
        Property98("FadI", 1, [inherited(0x0A)]),
        Property98("FadO", 1, [inherited(0x0A)]),
        Property98("NbO", 1, [inherited(TYPE_VOID), inherited(0x1E, 1)]),
        Property98("Keyw", 0, [inherited(TYPE_VOID), string(b"\x00", 1)]),
    ]
    return ClassBlock98("LFrame", CLASS_SCRATCH, properties).pack()

def active_item_block(name: bytes = b"Active\x00") -> bytes:
    """The properties an Active carries, each named and given its starting value.

    Every property the editor's Active dialogs can show is listed here — ink
    effect, scrolling, display and background behaviour, colour, qualifiers,
    movement. That list is the point: a rebuild sets these from the game, and a
    property nobody had described could not be set at all.
    """
    properties = [
        Property98("FadI", 1, [scalar(0x0A, 0)]),
        Property98("FadO", 1, [scalar(0x0A, 0)]),
        Property98("AltV", 1, [scalar(0x0A, 0)]),
        Property98("Keyw", 0, [inherited(TYPE_VOID), string(b"\x00", 1)]),
        Property98("ItNa", 1, [inherited(TYPE_VOID), string(name, 1)]),
        Property98("ItIc", 1, [scalar(0x0B, 0x03F9)]),
        Property98(
            "InkF",
            1,
            [scalar(0x01, 2), scalar(0x06, 0, 1), scalar(0x08, 0, 2)],
        ),
        Property98("AntA", 1, [scalar(0x01, 1)]),
        Property98("MFla", 1, [scalar(0x19, 0)]),
        Property98("MNew", 1, [scalar(0x0A, 0)]),
        Property98("Qual", 1, [scalar(0x0A, 0)]),
        Property98(
            "SFlg",
            1,
            [scalar(0x01, 2), scalar(0x01, 2, 1), scalar(0x05, 3, 2)],
        ),
        Property98("CFlg", 1, [scalar(0x19, 1)]),
        Property98("DFlg", 0, [scalar(0x19, 1)]),
        Property98("BFlg", 1, [scalar(0x01, 2), scalar(0x01, 1, 1)]),
        Property98("Colo", 1, [scalar(0x0D, 0x00FFFFFF)]),
        Property98("Visi", 1, [scalar(0x01, 2)]),
    ]
    return ClassBlock98("LActiveItem", CLASS_SCRATCH, properties).pack()

APPLICATION_PROP_PAIRS = (
    (b"WinS", b"NIWP"),
    (b"GEvt", b"TVEa"),
    (b"GloV", b"LAVa"),
    (b"Menu", b"UNMP"),
    (b"Scor", b"RCSP"),
    (b"Live", b"VILP"),
    (b"Plas", b"YLPa"),
    (b"RunO", b"TPOP"),
    (b"AppI", b"TBAP"),
    (b"Hlpf", b"PLHa"),
    (b"AppM", b"EDMa"),
    (b"LibT", b"pBIL"),
    (b"Keyw", b"\xd4BIL"),
)

FRAME_PROP_PAIRS = (
    (b"Tit", b"TITf"),
    (b"Pass", b"DWPf"),
    (b"PfSz", b"FLPf"),
    (b"Pale", b"LAPf"),
    (b"Evt", b"EVEf"),
    (b"FadI", b"NIFf"),
    (b"FadO", b"UOFf"),
    (b"NbO", b"BOBn"),
    (b"Keyw", b"\xd4BIL"),
)

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

def prop_index(
    pairs: tuple[tuple[bytes, bytes], ...],
    scratch: int = PROP_INDEX_SCRATCH,
    names: dict[bytes, bytes] | None = None,
) -> bytes:
    """The descriptor table that says which properties a record carries."""
    out = struct.pack("<IH", scratch, len(pairs))
    out += b"\x01\x00\x50\x00\x00PROP"
    for tag, data_tag in pairs:
        if len(data_tag) != 4:
            raise ValueError(f"PROP data tag for {tag!r} must be 4 bytes")
        name = (names or {}).get(tag, b"")
        out += struct.pack("<HH", 0, len(tag)) + tag
        out += struct.pack("<H", len(name)) + name
        out += data_tag
    return out

OBJECT_LIST_CLASS = b"class cHandleItemList<class LFrameItem>"

INSTANCE_LIST_CLASS = b"class cHandleItemList<class LFrameItemInstance>"

COILIST_CLASS = b"class COIList"

def counted(text: bytes) -> bytes:
    """Prefix a payload with its own length, the way the format stores text."""
    return struct.pack("<I", len(text)) + text

def extension_list(color_depth: int = AGMI_MODE_24BIT) -> bytes:
    """The project's extension table, empty, with the colour depth it works in.
    """
    return struct.pack("<II", color_depth, 0)

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
        + prop_index(ACTIVE_PROP_PAIRS)
        + struct.pack("<I", 0)
        + b"icnI" + struct.pack("<I", 4)
        + editor_animation_set(animations)
    )

def instance_record(
    x: int = 92, y: int = 88, item_id: int = 0, parent: int = 0xFFFFFFFF
) -> bytes:
    """One placement of one object in one frame."""
    return b"Inst" + struct.pack(
        "<IIIIIII", x, y, 0, 0, 0, item_id, parent
    )

def frame_body() -> bytes:
    """A frame's contents — its object list, placements and event region."""
    from klikback.core.common.object_reconstruct import event_object_record

    return (
        instance_record()
        + b"evpg" + bytes((0x00, 0x03, 0x01, 0x00))
        + b"EvOb" + counted(COILIST_CLASS) + struct.pack("<I", 1)
        + event_object_record(0, b"Active\x00")
        + b"EvEd" + struct.pack("<H", 0)
        + b"EvTe" + struct.pack("<H", 0)
        + b"!DNE" + struct.pack("<II", 2, 2)
        + counted(b"nil") + counted(b"nil")
        + struct.pack("<I", 0)
    )

def frame_span(item_id: int = 0) -> bytes:
    """One whole frame: its record, its palette, its objects and its contents.
    """
    return (
        b"Fram" + struct.pack("<II", 0, 0)
        + frame_block()
        + prop_index(FRAME_PROP_PAIRS)
        + struct.pack("<I", item_id)
        + b"Pltt" + bytes((0x00, 0x01, 0x00, 0x00)) + flagged_project_palette()
        + counted(OBJECT_LIST_CLASS) + struct.pack("<I", 1)
        + active_object_record()
        + counted(INSTANCE_LIST_CLASS) + struct.pack("<I", 1)
        + frame_body()
    )

NEUTRAL_PROJECT_PATH = "C:\\reconstruction.cca"

PATH_TO_LAYOUT_FILLER = bytes((0x06, 0x00, 0x00))

LAYOUT_LEAD_WORDS = (864, 2)

LAYOUT_TRAILING_WORDS = (1, 0x1F80, 32, 126, 289, 800)

FILLER_AFTER_CLASS_68 = (101, 3)

FILLER_BEFORE_CLASS_84 = (88,)

def window_record(
    window_class: int,
    identity: int,
    state: int,
    rect: tuple[int, int, int, int],
    show_cmd: int = 1,
) -> bytes:
    """One saved editor window: which kind, where it sat, and how it was shown.
    """
    placement = struct.pack(
        "<IIIiiiiiiii", 44, 0, show_cmd, -1, -1, -1, -1, *rect
    )
    return struct.pack("<IiiII", window_class, identity, -1, state, 0) + placement

def window_layout(frame_editor_item_id: int = 0) -> bytes:
    """The editor's saved window arrangement, which a project carries and restores.
    """
    words = struct.pack(f"<{len(LAYOUT_LEAD_WORDS)}I", *LAYOUT_LEAD_WORDS)
    out = (
        words
        + window_record(68, -1, 0x80000001, (26, 26, 1318, 488))
        + struct.pack("<2I", *FILLER_AFTER_CLASS_68)
        + window_record(60, frame_editor_item_id, 3, (52, 52, 1083, 497))
        + struct.pack("<I", *FILLER_BEFORE_CLASS_84)
        + window_record(84, -1, 0, (1536, 841, 1766, 1191))
        + struct.pack(f"<{len(LAYOUT_TRAILING_WORDS)}I", *LAYOUT_TRAILING_WORDS)
    )
    return out

def editor_tail(project_path: str = NEUTRAL_PROJECT_PATH) -> bytes:
    """The editor-only records that close a project file."""
    encoded = project_path.encode("latin-1")
    return (
        b"icnD"
        + struct.pack("<III", 0, 1, len(encoded))
        + encoded
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
        + prop_index(APPLICATION_PROP_PAIRS)
        + extension_list()
        + b"FrmL" + struct.pack("<I", 1)
        + frame_span()
        + editor_tail(project_path)
    )
