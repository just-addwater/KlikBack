# GENERATED — do not edit by hand. This file is produced by KlikBack's
# sync tooling; changes belong in the source it is generated from.
#
# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""Emit the empty Multimedia Fusion 2 project every rebuild starts from, field
by field.

A rebuilt project needs a valid empty project to be filled in: the file's
header and format stamp, the default menu and its keyboard shortcuts, the
two colour tables the image banks open with, the four default player
controls, one empty frame, and the short list of application settings the
editor writes for a project nobody has touched yet. This module writes all of
that from named fields, so the starting point is generated at the moment it
is wanted rather than found in a file.

The editor comes in two editions, and their empty projects are not the same
file with a different number on the front: they stamp different format
builds, set different renderer flags, and write different sets of
application and frame records. Both are described here under one name each,
so a rebuild can ask for either.

Nothing here carries artwork. The application icon's nine slots are filled
from the game being rebuilt — its own icon resources where it has them, its
one small icon scaled up where that is all it carries — so an empty project
from this module holds no picture that was not the game's.
"""

from __future__ import annotations
import struct
from klikback.core.common.scaffold_synthesis import AGMI_HEADER_WORDS, DEFAULT_PROJECT_PALETTE, WIN32_HALFTONE_PALETTE

def u16(v):
    """Two bytes, little-endian."""
    return struct.pack("<H", v)

def u32(v):
    """Four bytes, little-endian."""
    return struct.pack("<I", v & 0xFFFFFFFF)

def s(text):
    """A length-prefixed text field."""
    b = text.encode("cp1252")
    return u32(len(b)) + b

PROJECT_PALETTE_OVERRIDES = {
    16: bytes.fromhex("fffffe00"),
    31: bytes.fromhex("00000800"),
    63: bytes.fromhex("080f1b00"),
    79: bytes.fromhex("08081000"),
    89: bytes.fromhex("7b2b7f00"),
    107: bytes.fromhex("83000000"),
    137: bytes.fromhex("a3730700"),
    168: bytes.fromhex("007f0000"),
    196: bytes.fromhex("00838300"),
}

def image_bank_palette() -> bytes:
    """The colour table the image bank opens with."""
    table = bytearray(DEFAULT_PROJECT_PALETTE)
    for entry, quad in PROJECT_PALETTE_OVERRIDES.items():
        table[entry * 4:entry * 4 + 4] = quad
    return bytes(table)

def icon_bank_palette() -> bytes:
    """The colour table the icon bank opens with."""
    return WIN32_HALFTONE_PALETTE

GRAPHIC_MODE = 4

def bank_dict(palette: bytes, items) -> dict:
    """An image bank in the shape the project writer reads it."""
    return dict(graphicMode=GRAPHIC_MODE, paletteVersion=AGMI_HEADER_WORDS[0],
                paletteEntries=AGMI_HEADER_WORDS[1], palette=palette,
                items=[dict(handle=h, raw=r) for h, r in items])

MF_POPUP, MF_END, MF_HELP = 0x10, 0x80, 0x08

DEFAULT_MENU = (
    (MF_POPUP, None, "&File"),
    (0, 1010, "&New\tF2"),
    (0, 0, ""),
    (0, 1011, "Pass&word"),
    (0, 1012, "&Pause\tCtrl+P"),
    (0, 1013, "Pla&yers\tCtrl+Y"),
    (0, 0, ""),
    (MF_END, 1009, "&Quit\tAlt+F4"),
    (MF_POPUP, None, "&Options"),
    (0, 1020, "Play &samples\tCtrl+S"),
    (0, 1021, "Play &musics\tCtrl+M"),
    (0, 0, ""),
    (0, 1022, "&Hide the menu\tF8"),
    (0, 0, ""),
    (MF_END, 1025, "&Full Screen\tAlt+Enter"),
    (MF_POPUP | MF_END, None, "&Help"),
    (0, 1023, "&Contents\tF1"),
    (0, 0, ""),
    (MF_END, 1024, "&About..."),
)

FVIRTKEY, FCONTROL, FALT, FLAST = 0x01, 0x08, 0x10, 0x80

VK_RETURN, VK_F1, VK_F2, VK_F4, VK_F8 = 0x0D, 0x70, 0x71, 0x73, 0x77

DEFAULT_ACCELERATORS = (
    (FVIRTKEY | FALT, VK_RETURN, 1025),
    (FVIRTKEY | FCONTROL, ord("P"), 1012),
    (FVIRTKEY | FCONTROL, ord("Y"), 1013),
    (FVIRTKEY | FCONTROL, ord("S"), 1020),
    (FVIRTKEY | FCONTROL, ord("M"), 1021),
    (FVIRTKEY, VK_F1, 1023),
    (FVIRTKEY, VK_F2, 1010),
    (FVIRTKEY | FALT, VK_F4, 1009),
    (FVIRTKEY | FLAST, VK_F8, 1022),
)

MENU_HEADER_SIZE = 20

def menu_template(items=DEFAULT_MENU) -> bytes:
    """The default menu as the runtime stores it: File, Options and Help."""
    out = struct.pack("<HH", 0, 0)
    for flags, ident, text in items:
        out += u16(flags)
        if not flags & MF_POPUP:
            out += u16(ident)
        out += text.encode("utf-16-le") + b"\x00\x00"
    return out

def accelerator_table(entries=DEFAULT_ACCELERATORS) -> bytes:
    """The keyboard shortcuts that go with the default menu."""
    return b"".join(struct.pack("<4H", v, k, c, 0) for v, k, c in entries)

def default_menu_blob() -> bytes:
    """The stored menu record: a small header, the menu, then the shortcuts."""
    menu = menu_template()
    accel = accelerator_table()
    head = struct.pack("<5I", MENU_HEADER_SIZE, MENU_HEADER_SIZE, len(menu),
                       MENU_HEADER_SIZE + len(menu), len(accel))
    return head + menu + accel

WINDOW_WIDTH, WINDOW_HEIGHT = 640, 480

INITIAL_SCORE, INITIAL_LIVES, FRAME_RATE = 0, 3, 50

ICON_SLOTS = tuple((bpp, side) for bpp in (32, 8, 4) for side in (48, 32, 16))

ACHK_CHUNK = 0x38

COUNTER_CHUNK = 0x3C

ZERO_SCRATCH = bytes(8)

DEFAULT_ENTRY_NAME = "#default#"

RUNTIME_IDENT = "com.clickteam.runtime"

APPLICATION_IDENT = "com.yourcompany.yourapplication"

def chunk_76() -> bytes:
    """One of the constant application records a fresh project carries."""
    return (u32(0) + s(DEFAULT_ENTRY_NAME) + b"\xff" * 8 + u32(105) + u32(7)
            + u32(0x001719CD) + u32(0x00FFFFFF))

def chunk_7e() -> bytes:
    """The record naming the runtime."""
    return u32(0x00010000) + b"\xff" * 12 + s(RUNTIME_IDENT)

def chunk_82() -> bytes:
    """The record naming the application."""
    return bytes(16) + s(APPLICATION_IDENT) + b"\xff" * 8

def app_chunks_software(achk: bytes, counter: bytes):
    """The application records the software-rendering editor writes for a fresh
    project.
    """
    return [
        (0x30, u32(0)),
        (ACHK_CHUNK, b"ACHK" + achk),
        (COUNTER_CHUNK, counter),
        (0x40, u32(1)),
        (0x44, u32(0)),
        (0x48, u32(0)),
        (0x54, bytes(8)),
        (0x60, u32(0)),
        (0x5C, u32(1) + bytes(24)),
        (0x64, bytes(8)),
        (0x6C, u32(8)),
        (0x76, chunk_76()),
        (0x74, u32(44100) + u32(0x80)),
        (0x7A, u32(0)),
        (0x7E, chunk_7e()),
        (0x82, chunk_82()),
    ]

def app_chunks_hwa(achk: bytes, counter: bytes):
    """The application records the hardware-accelerated editor writes."""
    return app_chunks_software(achk, counter)[:5]

FRAME_MAX_OBJECTS = 500

RANDOMIZE_SEED = 0xFFFFFFFF

NO_EFFECT_RECORD = u32(0) + u32(0xFFFFFFFF) + u32(0)

def frame_chunks_software():
    """The frame records the software-rendering editor writes for an empty frame.
    """
    return [
        (0x21, struct.pack("<4I", 0, 0, WINDOW_WIDTH, WINDOW_HEIGHT)),
        (0x23, u32(RANDOMIZE_SEED)),
        (0x26, struct.pack("<2I", 0, FRAME_MAX_OBJECTS)),
        (0x27, u32(FRAME_RATE)),
        (0x29, u32(1)),
    ]

def frame_chunks_hwa():
    """The frame records the hardware-accelerated editor writes."""
    return [
        (0x21, struct.pack("<4I", 0, 0, WINDOW_WIDTH, WINDOW_HEIGHT)),
        (0x23, u32(RANDOMIZE_SEED)),
        (0x25, NO_EFFECT_RECORD),
    ]

class Edition:
    """One editor edition: its format build, its flags and its record lists."""
    def __init__(self, name, build, graphic_flags, frame_flags, app_chunks,
                 frame_chunks):
        self.name = name
        self.build = build
        self.graphic_flags = graphic_flags
        self.frame_flags = frame_flags
        self.app_chunks = app_chunks
        self.frame_chunks = frame_chunks

EDITIONS = {
    "software": Edition("software", 250, 0x00010881, 0x104,
                        app_chunks_software, frame_chunks_software),
    "hwa": Edition("hwa", 249, 0x00004881, 0x004,
                   app_chunks_hwa, frame_chunks_hwa),
}

class Scaffold:
    """The empty project in the form the project writer consumes."""

    def __init__(self, edition="software"):
        ed = EDITIONS[edition]
        self.edition = ed.name
        self.build = ed.build
        self.graphicFlags = ed.graphic_flags
        self.menu = default_menu_blob()
        self.icons = bank_dict(icon_bank_palette(), [])
        self.images = bank_dict(image_bank_palette(), [])
        self.chunks = ed.app_chunks(ZERO_SCRATCH, ZERO_SCRATCH)

def scaffold(edition="software") -> Scaffold:
    """The empty project for one edition."""
    return Scaffold(edition)

def scale_nearest(colour: bytes, alpha: bytes, side: int, out_side: int):
    """Resize a picture and its transparency plane by repeating pixels."""
    if out_side == side:
        return colour, alpha
    oc = bytearray(out_side * out_side * 2)
    oa = bytearray(out_side * out_side)
    for y in range(out_side):
        sy = y * side // out_side
        for x in range(out_side):
            sx = x * side // out_side
            si = sy * side + sx
            di = y * out_side + x
            oc[di * 2:di * 2 + 2] = colour[si * 2:si * 2 + 2]
            oa[di] = alpha[si]
    return bytes(oc), bytes(oa)

def scaled_icon_set(available: dict):
    """The nine application-icon pictures, each the game's own icon at that size
    where it has one and the nearest size it does have scaled where it does not.
    """
    if not available:
        return None
    out = []
    for _bpp, side in ICON_SLOTS:
        if side in available:
            c, a = available[side]
            out.append((side, c, a))
            continue
        src = min(available, key=lambda k: (abs(k - side), -k))
        c, a = scale_nearest(*available[src], src, side)
        out.append((side, c, a))
    return out
