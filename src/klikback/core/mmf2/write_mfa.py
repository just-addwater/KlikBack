# GENERATED — do not edit by hand. This file is produced by KlikBack's
# sync tooling; changes belong in the source it is generated from.
#
# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""Turn a built Multimedia Fusion 2 game back into a project the editor opens.

The product.  Everything else in this family exists so that this can read a
game and write a `.mfa` that the editor loads, runs, edits, saves and reopens.

**It refuses rather than approximates.**  A game holding something this writer
cannot express in a project file stops with the reason named, and produces no
file.  Emitting a project that opens and is quietly wrong about the game is
worse than emitting nothing: the author has no way to tell, and the mistake
gets saved over the only copy of the evidence.

Some of what the game once was is simply not in it.  The compiler drops
authors' names for backdrops and behaviours, forgets which sheet each event
line came from, and keeps only what the runtime reads.  Where that happens the
writer substitutes something workable and *says so* — every recovered project
comes with a report of what was reconstructed, what was named for the author,
and what was merged.  Read that report before reading the project.

The output is checked before it is offered: the writer reads its own file back
through the project reader, which walks to the last byte or refuses, so a file
that does not close never reaches the editor.
"""

from __future__ import annotations
import collections
import re
import struct
import zlib
from pathlib import Path
from klikback.core.mmf2.read_app import App, QUALIFIER_ID_MAX
import klikback.core.mmf2.comment_rows as comment_rows
import klikback.core.mmf2.extensions as extensions
import klikback.core.mmf2.image_codec as image_codec
from klikback.core.common.icon_generate import ARTWORK_DIR, imageless_icon_art, marker_green, read_png_rgba
import klikback.core.mmf2.scaffold_synthesis as scaffold_synthesis

FLAGS_TO_DISPLAY = {9: 0, 4: 1, 11: 2, 12: 3, 8: 6, 0: 5}

FLAGS_INVERTED = {1: 4, 7: 7}

NEWFLAGS_TO_DISPLAY = {4: 8, 5: 9, 6: 10, 7: 11, 9: 12, 10: 13, 14: 14}

FLAGS_TO_GRAPHIC = {10: 0, 3: 1}

NEWFLAGS_TO_GRAPHIC = {0: 2, 3: 3, 8: 4, 11: 7, 12: 8, 13: 9, 15: 10}

OTHERFLAGS_TO_GRAPHIC = {0: 11, 1: 5, 2: 6, 3: 13, 14: 14, 15: 15}

SHOW_DEBUGGER_BIT = 7

GRAPHIC_SHOW_DEBUGGER_OFF_BIT = 12

GRAPHIC_FLAGS_BASE = 0x00010000

FLAGS_CONST_SET = 0xA000

NEWFLAGS_REFUSE = 0x0006

OTHERFLAGS_CONST_SET = 0x0080

OTHERFLAGS_IGNORED = 0x1000

OTHERFLAGS_TO_BUILD_OPTIONS = {6: 2}

APP_BUILD_OPTIONS_CHUNK = 0x30

APP_BUILD_OPTIONS_EXE_MASK = 0x0004

APP_BUILD_OPTIONS_IMAGE_LIST = 0x0008

APP_BUILD_OPTIONS_SOUND_LIST = 0x0010

APP_BUILD_OPTIONS_FILTER_BITS = (APP_BUILD_OPTIONS_IMAGE_LIST
                                 | APP_BUILD_OPTIONS_SOUND_LIST)

APP_VISTA_CHUNK = 0x40

VISTA_LEVELS = {b"asinvoker": 1, b"requireadministrator": 2}

_VISTA_RE = re.compile(rb'requestedExecutionLevel\s+level="([A-Za-z]+)"')

def vista_privilege(exe_bytes):
    """The privilege setting the game's own Windows manifest implies.

    A built executable records this in the manifest rather than in its game data,
    so it is read from where it actually is.  A game shipped without the wrapper —
    data only — has no manifest and therefore no answer, which is a fact about the
    container and not a default to invent.
    """
    got = _VISTA_RE.search(exe_bytes)
    if got is None:
        return 0
    return VISTA_LEVELS.get(got.group(1).lower(), None)

FRAME_TO_MFA = {1: 0, 2: 1, 5: 2, 0: 3, 8: 4, 10: 5, 11: 6, 15: 8}

FRAME_ACCEPTED = 0x0040 | 0x1000

OBJECT_FLAGS_MEASURED = 0x0027

LAYER_TO_MFA = {17: 3, 2: 4, 5: 5, 6: 6}

LAYER_ACCEPTED = 0x0000_0013

MFA_LAYER_BASE = 0x1

LAYER_UNNAMED = 0x0000_0080

NEW_OBJECT_FLAGS_COMPILED_BIT = 0x4

SCORE_DIGITS_DEFAULT = {5: 9, 6: 2}

COUNTER_SIG_DEFAULT, COUNTER_DEC_DEFAULT = 16, 2

COUNTER_HIDDEN_SIZE = (96, 32)

QB_COLOR1_DEFAULT, QB_COLOR2_DEFAULT = 0x808080, 0xFFFFFF

QA_CONST = 37

EVOB_TYPE_NAMES = {2: "Sprite", 3: "Text", 4: "Question", 5: "Score",
                   6: "Lives", 7: "Counter", 8: "", 9: ""}

EVCS = bytes([0x10] + [0] * 19)

EVTS = bytes(20)

EVLS = bytes(16)

EVCS_EVENTS = bytes([0x10, 0, 0, 0, 0x2C, 0x01, 0x14, 0] + [0] * 12)

EVTS_EVENTS = bytes(8) + struct.pack("<2I", 5, 5) + bytes(4)

EVED_SYSTEM = [0xFFFF, 0xFFFE, 0xFFFD, 0xFFFC, 0xFFFB, 0xFFFA, 0xFFF9]

DEFAULT_STATIC_MOVEMENT = bytes(4) + b"\x01" + bytes(21)

MOVEMENT_HEAD = 26

EXT_DISPLAY_NAMES = {
    "alphachannel.mfx": "Alpha Channel object", "capture.mfx": "Screen Capture object",
    "easing.mfx": "Easing Object", "foreach.mfx": "ForEach",
    "joystick2.mfx": "Joystick 2 object", "kcarray.mfx": "Array",
    "kcboxa.mfx": "Active System Box", "kcboxb.mfx": "Background System Box",
    "layer.mfx": "Layer object", "mtrandom.mfx": "MT Random object",
    "moveit.mfx": "MoveIt", "parallaxer.mfx": "Parallaxer",
    "particlespray.mfx": "Particle Spray object", "perspective.mfx": "Perspective",
    "platform.mfx": "Platform Movement object", "savegame.mfx": "Save Game Object",
    "statictext.mfx": "Static Text", "surface.mfx": "Surface",
    "valueadd.mfx": "Value-Add Object", "zipobject.mfx": "Zip Object",
    "bigbox.mfx": "The Big Box", "ctrlx.mfx": "Control X",
    "dungeon.mfx": "Dungeon Object", "fcbutton.mfx": "Bouton CS",
    "fcfolder.mfx": "File-Folder object", "fcmmf2params.mfx": "MMF2 Params object",
    "fcmsgbox.mfx": "MessageBox object", "gstorex.mfx": "Global Store X",
    "imageconv.mfx": "Image Manipulator", "joystick.mfx": "Joypad object",
    "kcanim.mfx": "Animation", "kccda.mfx": "CD-Audio",
    "kcclock.mfx": "Date & Time", "kccombo.mfx": "Combo Box",
    "kcdirect.mfx": "Direction Calculator", "kcfile.mfx": "File",
    "kcini.mfx": "Ini", "kclist.mfx": "List",
    "kcpica.mfx": "Active Picture", "kctime.mfx": "Timer object",
    "kcwctrl.mfx": "Window Control", "nvar.mfx": "Named variable object",
    "parser.mfx": "String Parser", "txtblt.mfx": "Text Blitter",

    "advdir.mfx": "Advanced Direction Object",
    "advgameboard.mfx": "Advanced Game Board",
    "animpicture.mfx": "Animated Picture", "assarray.mfx": "AssArray Object",
    "b2d.mfx": "Phizix - Box2D", "binaryarray.mfx": "Binary array",
    "colorselector.mfx": "Color Selector",
    "directorypacker.mfx": "Directory packer", "download.mfx": "Download object",
    "funcloop.mfx": "Func Loop", "iif.mfx": "Immediate If Object",
    "ini++.mfx": "Ini++", "kcbutton.mfx": "Button",
    "kcdraw.mfx": "Draw object",

    "kcedit.mfx": "Edit Box",
    "kcmouse.mfx": "Mouse object", "kcpict.mfx": "Picture",
    "kcplugin.mfx": "Vitalize! Plug-in", "kcpop.mfx": "Popup Message object 2",
    "kcvfw.mfx": "AVI", "livereceiver.mfx": "Live receiver",
    "luammf2.mfx": "Lua object", "movesafely2.mfx": "Move Safely 2 Object",
    "overlay.mfx": "Overlay Redux", "stringreplace.mfx": "Substring Replace",
    "stringtokenizer.mfx": "String tokenizer",
}

import klikback.core.mmf2.divergence as divergence

class Refuse(Exception):
    """Raised when the game holds a state this writer will not express.

    The message names the state.  A refusal a user can read is a bug report they
    can send and a limitation they can work around; a silent approximation is
    neither.
    """

def map_app_words(flags, newflags, otherflags, ext_word, notes):
    """Translate the game's application flag words into the project file's.

    Refuses on a bit outside the mapped set, by name.  The two formats spell the
    same settings differently and an unmapped bit means this writer has met an
    option it has not learned — worth stopping for, and not worth passing through
    as a number.
    """
    for word, value, mapped, const_set, refuse_mask in (
            ("flags", flags,
             set(FLAGS_TO_DISPLAY) | set(FLAGS_INVERTED) | set(FLAGS_TO_GRAPHIC),
             FLAGS_CONST_SET, 0),
            ("newFlags", newflags,
             set(NEWFLAGS_TO_DISPLAY) | set(NEWFLAGS_TO_GRAPHIC),
             0, NEWFLAGS_REFUSE),
            ("otherFlags", otherflags,
             set(OTHERFLAGS_TO_GRAPHIC),
             OTHERFLAGS_CONST_SET, 0)):
        accept = const_set
        for b in mapped:
            accept |= 1 << b
        if word == "otherFlags":
            accept |= OTHERFLAGS_IGNORED
            for b in OTHERFLAGS_TO_BUILD_OPTIONS:
                accept |= 1 << b
        resid = (value & ~accept) | (value & refuse_mask)
        if resid:
            raise Refuse("%s 0x%04X carries unmapped bits 0x%04X"
                         % (word, value, resid))
        if const_set and (value & const_set) != const_set:
            cleared = const_set & ~value

            if word == "otherFlags" and cleared == 0x0080:

                notes.append("otherFlags bit 7 is CLEAR (0x%04X); no project "
                             "field is known to be bound to it, so the "
                             "recovered project does not carry this "
                             "application option" % value)
            else:

                raise Refuse("%s 0x%04X clears bits 0x%04X that no game "
                             "KlikBack has seen clears -- the option behind "
                             "them is not known" % (word, value, cleared))

    display = 0
    for eb, mb in FLAGS_TO_DISPLAY.items():
        if flags & (1 << eb):
            display |= 1 << mb
    for eb, mb in FLAGS_INVERTED.items():
        if not flags & (1 << eb):
            display |= 1 << mb
    for eb, mb in NEWFLAGS_TO_DISPLAY.items():
        if newflags & (1 << eb):
            display |= 1 << mb
    if ext_word is not None:

        if ext_word & ~0x0017:
            raise Refuse("0x2245 word 0x%X carries unmapped bits 0x%X"
                         % (ext_word, ext_word & ~0x0017))
        if ext_word & 0x0006:
            notes.append("0x2245 word 0x%X carries bits 0x%X, which record "
                         "the state of the Multimedia Fusion installation "
                         "that built this game rather than anything in the "
                         "project itself; not carried into the recovery"
                         % (ext_word, ext_word & 0x0006))
        if ext_word & 0x0001:
            display |= 1 << 15
    if newflags & (1 << 14):

        forced = display & ((1 << 4) | (1 << 5) | (1 << 11))
        if forced:
            display &= ~forced
            notes.append("MDI application: compile-forced display bits "
                         "0x%X dropped, per the editor's own save" % forced)

    graphic = GRAPHIC_FLAGS_BASE
    for eb, mb in FLAGS_TO_GRAPHIC.items():
        if flags & (1 << eb):
            graphic |= 1 << mb
    for eb, mb in NEWFLAGS_TO_GRAPHIC.items():
        if newflags & (1 << eb):
            graphic |= 1 << mb
    for eb, mb in OTHERFLAGS_TO_GRAPHIC.items():
        if otherflags & (1 << eb):
            graphic |= 1 << mb

    if not (otherflags & (1 << SHOW_DEBUGGER_BIT)):
        graphic |= 1 << GRAPHIC_SHOW_DEBUGGER_OFF_BIT
    return display, graphic

def map_frame_flags(eflags, index, share_bit_ok):
    """Translate a frame's flag word, refusing an unmapped bit."""
    accept = FRAME_ACCEPTED
    for b in FRAME_TO_MFA:
        accept |= 1 << b
    resid = eflags & ~accept
    if resid:
        raise Refuse("frame %d flags 0x%08X carry unmapped bits 0x%08X"
                     % (index, eflags, resid))
    if eflags & 0x1000 and not share_bit_ok:

        raise Refuse("frame %d sets flag bit 12 without the application's "
                     "otherFlags bit 3; the two are otherwise always set "
                     "together, so this state is not understood" % index)
    out = 0
    for eb, mb in FRAME_TO_MFA.items():
        if eflags & (1 << eb):
            out |= 1 << mb
    return out

def map_layer_flags(lflags, index, which, notes=None):
    """Translate a layer's flag word, refusing an unmapped bit.

    One bit is the exception. It appears on a handful of layers built by later
    releases than this writer was measured against, and no option in the layer's
    own property page accounts for it -- nor does any state the editor stores in
    a project file, so there is nowhere faithful to put it. Refusing it would
    cost the whole game to keep one checkbox nobody can name, so the layer is
    written without it and the report says which frame and layer lost it.
    """
    accept = LAYER_ACCEPTED | LAYER_UNNAMED
    for b in LAYER_TO_MFA:
        accept |= 1 << b
    resid = lflags & ~accept
    if resid:
        raise Refuse("frame %d layer %d flags 0x%08X carry unmapped bits "
                     "0x%08X" % (index, which, lflags, resid))
    if lflags & LAYER_UNNAMED and notes is not None:
        notes.append("frame %d layer %d: layer flag bit 7 (0x%08X) is set "
                     "and has no known editor state, so the layer is "
                     "written without it" % (index, which, LAYER_UNNAMED))
    out = MFA_LAYER_BASE
    for eb, mb in LAYER_TO_MFA.items():
        if lflags & (1 << eb):
            out |= 1 << mb
    return out

class W:
    """The output buffer: the project file's primitives, written in order."""
    def __init__(self):
        self.parts = []
        self.size = 0
        self.lossy_strings = []

    def _put(self, b):
        self.parts.append(b)
        self.size += len(b)

    def raw(self, b):
        self._put(bytes(b))

    def u8(self, v):
        self._put(struct.pack("<B", v))

    def u16(self, v):
        self._put(struct.pack("<H", v & 0xFFFF))

    def i16(self, v):

        self._put(struct.pack("<H", v & 0xFFFF))

    def u32(self, v):
        self._put(struct.pack("<I", v & 0xFFFFFFFF))

    def i32(self, v):
        self._put(struct.pack("<I", v & 0xFFFFFFFF))

    def f32(self, v):
        self._put(struct.pack("<f", v))

    def s(self, text):
        if isinstance(text, str):
            try:
                b = text.encode("cp1252")
            except UnicodeEncodeError:
                b = text.encode("cp1252", "replace")
                self.lossy_strings.append(text)
        else:
            b = bytes(text)
        self.u32(len(b))
        self.raw(b)

    def blob(self, b):
        self.u32(len(b))
        self.raw(b)

    def tell(self):
        return self.size

    def bytes(self):
        return b"".join(self.parts)

TRANSITION_NAMES = {
    ("cctrans.dll", b"BAND"): "Bands",
    ("cctrans.dll", b"DOOR"): "Door",
    ("cctrans.dll", b"FADE"): "Fade",
    ("cctrans.dll", b"MOSA"): "Mosaic",
    ("cctrans.dll", b"SCRL"): "Scrolling",
    ("cctrans.dll", b"SE00"): "Advanced Scrolling",
    ("cctrans.dll", b"SE01"): "Square",
    ("cctrans.dll", b"SE02"): "Turn 2",
    ("cctrans.dll", b"SE03"): "Line",
    ("cctrans.dll", b"SE04"): "ZigZag 2",
    ("cctrans.dll", b"SE05"): "Open",
    ("cctrans.dll", b"SE06"): "Push",
    ("cctrans.dll", b"SE07"): "Stretch",
    ("cctrans.dll", b"SE08"): "Turn",
    ("cctrans.dll", b"SE09"): "Stretch 2",
    ("cctrans.dll", b"SE10"): "Back",
    ("cctrans.dll", b"SE11"): "Zoom 2",
    ("cctrans.dll", b"SE12"): "Cell",
    ("cctrans.dll", b"SE13"): "Trame",
    ("cctrans.dll", b"ZOOM"): "Zoom",
    ("sftrans.dll", b"AZOM"): "Alpha Zoom",
    ("sftrans.dll", b"CIRC"): "Circle",
    ("sftrans.dll", b"STRE"): "Stretch",
}

def _write_transition(w, tr, where, notes):
    if tr.get("error"):
        raise Refuse("%s: %s" % (where, tr["error"]))
    module = tr["module"]
    name = TRANSITION_NAMES.get((module.lower(), tr["transitionId"]))
    if name is None:
        code = tr["transitionId"].decode("cp1252", "replace")
        name = code
        notes.append("%s: transition %s in %s has no display name KlikBack "
                     "knows; "
                     "substituted its own code %r" % (where, code, module, name))
    w.s(module)
    w.s(name)
    w.raw(tr["id"])
    w.raw(tr["transitionId"])
    w.u32(tr["duration"])
    w.u32(tr["flags"])
    w.u32(tr["colour"])
    w.blob(tr["param"])
    notes.append("%s: transition %s from %s; the editor needs that module "
                 "installed" % (where, name, module))

def _write_fades(w, holder, where, notes):
    for which in ("fadeIn", "fadeOut"):
        tr = holder.get(which)
        if tr is None:
            w.u8(0)
        else:
            w.u8(1)
            _write_transition(w, tr, "%s %s" % (where, which), notes)

def load_template(edition="software"):
    """The project skeleton a recovered file is built on.

    Some of the project format is editor furniture with nothing in the game to
    derive it from — a default menu, the colour tables, the settings a fresh
    project carries.  Those are generated field by field, for the edition asked
    for, rather than copied from a file.
    """
    return scaffold_synthesis.scaffold(edition)

def exe_image_palette(app):
    """The colour table a built game's indexed pictures refer to.

    A built game's picture bank carries no table of its own; each level carries
    one, and it is the table the project's picture bank had.  Levels can in
    principle disagree and the first is taken, because the bank being rebuilt is
    one bank with one table.

    Returns nothing when the game carries no table at all, and an indexed picture
    then stays unreadable — which means it is carried through untouched, not that
    anything has gone wrong.
    """
    from klikback.core.mmf2.read_app import walk_chunks
    for chunk in app.by_id.get(0x3333) or []:
        kids, _stop, _ = walk_chunks(chunk.payload, 0, len(chunk.payload),
                                     keep_payload=True)
        pal = {c.id: c.payload for c in kids}.get(0x3337)
        if pal is not None and len(pal) >= 4 + image_codec.PALETTE_BYTES:
            return bytes(pal[4:4 + image_codec.PALETTE_BYTES])
    return None

def inflated_images(app):
    """Every image in the game, decompressed, by handle."""
    p = app.payload(0x6666)
    out = {}
    if p is None:
        return out
    (count,) = struct.unpack_from("<I", p, 0)
    pos = 4
    for _ in range(count):
        handle, dsize, csize = struct.unpack_from("<3I", p, pos)
        raw = zlib.decompress(p[pos + 12 : pos + 12 + csize])
        if len(raw) != dsize:
            raise Refuse("image %d inflates to %d, header says %d"
                         % (handle, len(raw), dsize))
        out[handle] = raw
        pos += 12 + csize
    return out

APP_FILTER_CHUNK = 0x34

def filter_chunk(exe_path, notes):
    """The project's image and sound filter selection, rebuilt from the modules the
    game carries.

    Off by default.  A game records which filters it *packed*, and two projects
    that pack the same filters can have recorded the selection two different ways,
    so writing one of them back is a choice rather than a recovery.
    """
    try:
        _start, entries, _note = extensions.pack_entries(Path(exe_path))
    except Exception as e:
        notes.append("filters: no pack block to read the filter list from "
                     "(%s); chunk 0x%02X is not written"
                     % (e, APP_FILTER_CHUNK))
        return None
    images, sounds = [], []
    for e in entries:
        name = e["name"]
        low = name.lower()
        bucket = images if low.endswith(".ift") else (
            sounds if low.endswith(".sft") else None)
        if bucket is not None and not any(x.lower() == low for x in bucket):
            bucket.append(name)
    if not images and not sounds:

        notes.append("filters: the pack block names no image or sound "
                     "filter; chunk 0x%02X is not written rather than "
                     "written empty" % APP_FILTER_CHUNK)
        return None
    body = bytearray()
    for group in (images, sounds):
        body += struct.pack("<I", len(group))
        for name in group:
            raw = name.encode("cp1252", "replace")
            body += struct.pack("<I", len(raw)) + raw
    notes.append("filters: chunk 0x%02X written from the pack block -- "
                 "%d image (%s), %d sound (%s). This is OPT-IN recovered "
                 "content: the EXE proves which filters the project used, "
                 "but not whether the editor stored the list."
                 % (APP_FILTER_CHUNK, len(images), ", ".join(images) or "-",
                    len(sounds), ", ".join(sounds) or "-"))
    return bytes(body)

def convert(exe_path, out_path, section_labels=True, filters=False,
            report=None, strip_extensions=(), generate_icons=True,
            extensions_dir=None):
    """Read a game and write the project, or refuse.

    Given an editor's extension folder, an extension object with no picture of
    its own takes the icon its module carries there -- what the editor would
    show for that object inserted today -- and a module the folder lacks falls
    back to the stock drawing.  Without a folder, every such object gets the
    drawing.
    """
    app = App(Path(exe_path))
    hdr = app.app_header()
    if hdr is None:
        raise Refuse("no readable AppHeader")
    p2223 = app.payload(0x2223)
    flags, newflags, mode, otherflags = struct.unpack_from("<4H", p2223, 4)
    control_types = struct.unpack_from("<4H", p2223, 0x18)
    control_keys = struct.unpack_from("<32H", p2223, 0x20)
    window_menu_index = p2223[0x6C]

    template = load_template()
    menu = app.payload(0x2226)
    menu_substituted = menu is None
    if menu_substituted:

        menu = template.menu
    images = inflated_images(app)
    palette = exe_image_palette(app)
    objects, note = app.objects()
    if objects is None:
        raise Refuse(note)
    frames = app.frames()
    name = app.name() or "Recovered application"

    gvalues, gstrings = app.globals()
    if gvalues and gvalues.get("error"):
        raise Refuse("globals: %s" % gvalues["error"])

    ext_records, _ext_note = app.extensions()
    ext_records = ext_records or []

    notes = []

    strip_oi = frozenset()
    strip_tally = collections.Counter()
    if strip_extensions:
        want = {m.lower() for m in strip_extensions}
        by_name = {er["module"].lower(): er for er in ext_records}
        unknown = sorted(want - set(by_name))
        if unknown:
            raise Refuse("--strip-extension names %s, which this game does "
                         "not use. It uses: %s"
                         % (", ".join(unknown),
                            ", ".join(sorted(er["module"] for er in ext_records))
                            or "no extensions at all"))
        strip_types = {by_name[m]["handle"] + 32 for m in want}
        strip_oi = frozenset(i for i, o in enumerate(objects)
                             if o.get("type") in strip_types)
        strip_tally["objects"] = len(strip_oi)
        notes.append("STRIPPED extension(s) %s: %d object(s) removed"
                     % (", ".join(sorted(by_name[m]["module"] for m in want)),
                        len(strip_oi)))

        ext_records = [er for er in ext_records
                       if er["module"].lower() not in want]
    if menu_substituted:

        notes.append("the application carries no menu chunk; the editor's "
                     "default menu (550 bytes) is substituted -- it is what "
                     "the editor's own save of a game in this state holds")

    if app.app_icon() is not None and app.app_icon_set():
        notes.append("the application's own icon is recovered from the "
                     "compiled file -- all nine bank entries, 48x48, 32x32 "
                     "and 16x16 at three depths")
    elif app.app_icon() is None:
        notes.append("the compiled file carries no application icon at all")

    _orig = app.editor_path()
    if _orig:
        notes.append("the compiled file names the project it was built "
                     "from: %s" % _orig)

    p2245 = app.payload(0x2245)
    ext_word = (struct.unpack_from("<I", p2245, 0)[0]
                if p2245 is not None and len(p2245) >= 4 else None)
    display_flags, graphic_flags = map_app_words(flags, newflags, otherflags,
                                                 ext_word, notes)

    _ver = app.version_info() or {}

    try:
        _bins = app.binary_files()
    except ValueError as exc:
        raise Refuse("binary files: %s" % exc)

    w = W()
    w.raw(b"MMF2")
    w.u32(4)
    w.u32(app.pver)

    if app.pbuild != template.build:
        notes.append("the source EXE is format build %d; the .mfa is written "
                     "in this writer's target format, build %d"
                     % (app.pbuild, template.build))
    w.u32(template.build)
    w.s(name)
    w.s(_ver.get("description") or "")
    w.s(str(Path(out_path).resolve()))
    w.u32(0)

    w.raw(b"ATNF")
    _write_fonts(w, app)
    w.raw(b"APMS")
    _write_sounds(w, app)
    w.raw(b"ASUM")
    _write_musics(w, app)

    recovered_icons = _app_icon_records(app, template, notes)
    if recovered_icons is not None:

        icon_records = list(enumerate(recovered_icons))
    else:

        icon_records = list(enumerate(_blank_app_icon_records()))
        notes.append("this container carries no application icon; the nine "
                     "icon slots are left transparent")
    next_icon = max(h for h, _ in icon_records) + 1
    object_icons = {}
    blank = None
    emptied = 0
    artwork_handles = {}
    drawn = {}
    rendered_memo = {}
    installed = _InstalledIcons(extensions_dir, ext_records)
    for obj in objects:
        img = _first_image(obj, images, palette, rendered_memo)

        icon = (None if img is None
                else _object_icon_record(img, palette, rendered_memo))
        if icon is None:

            if img is not None:
                emptied += 1
            elif generate_icons and installed.record(obj) is not None:

                object_icons[obj["handle"]] = installed.handle(obj, icon_records, next_icon)
                next_icon = installed.next_icon
                continue
            elif generate_icons and _wants_artwork(obj.get("type")):
                art = imageless_icon_art(obj.get("type"))
                handle = artwork_handles.get(art)
                if handle is None:
                    handle = artwork_handles[art] = next_icon
                    icon_records.append((next_icon, _artwork_icon_record(art)))
                    next_icon += 1
                    drawn[art.name] = 0
                drawn[art.name] += 1
                object_icons[obj["handle"]] = handle
                continue
            if blank is None:
                blank = next_icon
                icon_records.append((next_icon, _blank_icon_record()))
                next_icon += 1
                notes.append("some objects carry no picture of their own -- a "
                             "String, a Sub-Application, a Counter shown as "
                             "digits -- and the editor draws those icons from "
                             "its own artwork, which the compiled file does "
                             "not carry; they are recovered blank")
            object_icons[obj["handle"]] = blank
            continue
        object_icons[obj["handle"]] = next_icon
        icon_records.append((next_icon, icon))
        next_icon += 1
    if emptied:
        notes.append("%d object(s) have a picture that is wholly transparent, "
                     "so the editor's trim leaves no icon to write; they are "
                     "recovered blank" % emptied)
    installed.report(notes)
    if drawn:

        notes.append("%d object(s) carry no picture of their own, so the "
                     "editor draws their icons from artwork the compiled "
                     "file does not contain; this recovery substitutes its "
                     "OWN drawings from %s (%s)"
                     % (sum(drawn.values()), ARTWORK_DIR.name,
                        ", ".join("%s x%d" % (n, c)
                                  for n, c in sorted(drawn.items()))))
    w.raw(b"AGMI")
    _write_image_bank(w, template.icons, icon_records, mode)

    referenced = set()
    for obj in objects:

        for aname, dirs in _animations(obj):
            for d in dirs:
                referenced.update(d["frames"])
        if obj.get("type") == 1 and len(obj.get("properties") or b"") >= 18:
            referenced.add(struct.unpack_from("<H", obj["properties"], 0x10)[0])
    for h in sorted(set(images) - referenced):
        notes.append("image %d is referenced by no object; carried into the "
                     "bank unchanged" % h)
    w.raw(b"AGMI")

    _write_image_bank(w, template.images,
                      [(h, images[h]) for h in sorted(images)], mode)

    w.s(name)

    w.s(app.author() or "")
    w.s(_ver.get("description") or "")
    w.s(app.copyright() or "")
    w.s(_ver.get("company") or "")
    w.s(_ver.get("version") or "")

    w.u32(hdr["width"])
    w.u32(hdr["height"])
    w.u32(hdr["borderColor"])
    w.u32(display_flags)
    w.u32(graphic_flags)
    w.s(app.help_file() or "")
    w.s("")
    w.u32(hdr["initialScore"])
    w.u32(hdr["initialLives"])
    w.u32(hdr["frameRate"])

    p2245 = app.payload(0x2245)
    if p2245 is not None and len(p2245) >= 8:
        build_type = struct.unpack_from("<I", p2245, 4)[0]
    else:
        build_type = 2 if app.how == "wholefile-direct" else 0
    w.u32(build_type)
    w.s("")
    w.u32(0)
    w.s("")
    w.s(app.about_box() or "")
    w.u32(0)

    w.u32(len(_bins))
    for _name, _data in _bins:
        w.u32(len(_name))
        w.raw(_name)
        notes.append("the project embeds a binary file (%d bytes in the "
                     "compiled application); the editor stores its NAME, "
                     "which is what is recovered here"
                     % len(_data))

    w.u32(4)
    for i in range(4):
        w.u32(control_types[i])
        w.u32(16)
        for k in control_keys[i * 8 : i * 8 + 8]:
            w.u32(k)
        for _ in range(8):
            w.u32(0)

    w.blob(menu)
    w.u32(window_menu_index)

    w.u32(0)

    _write_value_list(w, [(0, v) for v in (gvalues or {}).get("values", [])])
    _write_value_list(w, [(2, s) for s in (gstrings or {}).get("strings", [])])
    w.u32(0)
    w.u32(mode)
    w.u32(9)
    for i in range(9):
        w.u32(i)
    w.u32(0)

    w.u32(len(ext_records))
    for er in ext_records:
        display = EXT_DISPLAY_NAMES.get(er["module"].lower())
        if display is None:
            display = Path(er["module"]).stem
            notes.append("extension %s: display name unknown, substituted %r"
                         % (er["module"], display))
        w.u32(er["handle"])
        w.s(er["module"])
        w.s(display)
        w.u32(er["constant"])
        w.s(er["subtype"])

    w.u32(len(frames))
    offset_pos = w.tell()
    for _ in range(len(frames)):
        w.u32(0)
    post_pos_slot = w.tell()
    w.u32(0)

    ext_by_handle = {er["handle"]: er for er in ext_records}
    for oi, obj in enumerate(objects):

        if oi in strip_oi:
            continue
        t = obj.get("type")
        if t is not None and t >= 32:
            er = ext_by_handle.get(t - 32)
            if er is None:
                raise Refuse("object %r: extension handle %d is not in the "
                             "0x2234 table" % (obj.get("name"), t - 32))
            obj["extension"] = er

    counters = {0: 0, 1: 0}

    substituted_names = []
    for obj in objects:
        t = obj.get("type")
        if t in (0, 1) and not obj.get("name"):
            counters[t] += 1
            stem = "Backdrop" if t == 1 else "Quick Backdrop"
            obj["name"] = (stem if counters[t] == 1
                           else "%s %d" % (stem, counters[t]))
            substituted_names.append(obj["name"])

    for _t, _stem in ((1, "Backdrop"), (0, "Quick Backdrop")):
        if counters[_t]:
            notes.append("%d %s object(s) had no name to recover -- the "
                         "compiler drops these from every game -- so they "
                         "are named %s, %s 2, ... %s %d, the way the editor "
                         "names new ones"
                         % (counters[_t], _stem, _stem, _stem, _stem,
                            counters[_t]))

    frame_offsets = []
    share_bit_ok = bool(otherflags & 0x0008)
    _fhandles = app.frame_handles()
    if _fhandles is not None and _fhandles != list(range(len(frames))):
        notes.append("the project's frames were rearranged in the editor; "
                     "their original handles are recovered from the "
                     "compiled file rather than renumbered by position")
    _inline_mark = len(notes)
    for i, frame in enumerate(frames):
        frame_offsets.append(w.tell())
        _write_frame(w, app, frame, i, objects, images, object_icons, notes,
                     share_bit_ok, section_labels,
                     None if _fhandles is None else _fhandles[i],
                     strip_oi, strip_tally)
    if strip_extensions:
        notes.append("STRIPPED: %d instance(s), %d event line(s) and %d lone "
                     "action(s) removed with them"
                     % (strip_tally["instances"], strip_tally["records"],
                        strip_tally["actions"]))
    post_frames = w.tell()

    _inlined = [n for n in notes[_inline_mark:] if "inlined from" in n]
    if _inlined:
        notes.append(
            "SHAPE: this game's global events and object behaviours have "
            "been INLINED into the event list of each frame that used them "
            "(%d frame(s) affected). The recovered game behaves as the "
            "original does; what is lost is the SPLIT -- the compiled file "
            "does not record which records came from the global sheet, which "
            "from a behaviour, or which object owned it, so there is no way "
            "to put them back. Comment rows mark where each inlined section "
            "begins." % len(_inlined))

    ext_numeric = (struct.unpack_from("<I", p2245, 0x0C)[0]
                   if p2245 is not None and len(p2245) >= 16 else None)

    filter_body = filter_chunk(exe_path, notes) if filters else None
    for cid, payload in template.chunks:
        if cid == 0x38:
            continue
        if cid == 0x6C and ext_numeric is not None:
            payload = struct.pack("<I", ext_numeric)
        if cid == APP_BUILD_OPTIONS_CHUNK and len(payload) >= 4:

            opts = struct.unpack_from("<I", payload, 0)[0]
            opts &= ~APP_BUILD_OPTIONS_EXE_MASK
            for eb, mb in OTHERFLAGS_TO_BUILD_OPTIONS.items():
                if otherflags & (1 << eb):
                    opts |= 1 << mb
            if filter_body is not None:

                opts |= APP_BUILD_OPTIONS_FILTER_BITS
                notes.append(
                    "filters: build-options bits 3 and 4 set (chunk 0x%02X "
                    "-> 0x%X) -- these mark that a filter list is stored and "
                    "the editor refuses one without them. They move no "
                    "checkbox on the Build Options page: its four settings "
                    "are bits 0, 1, 2 and 5, and none of them changes here."
                    % (APP_BUILD_OPTIONS_CHUNK, opts))
            if otherflags & 0x0040:

                _bin_note = ("; this file also embeds %d binary file(s), "
                             "whose names are recovered" % len(_bins)
                             if _bins else "")
                notes.append(
                    "application: 'include external files' is set, and the "
                    "option is carried. No external file was found in this "
                    "EXE to go with it: its pack block holds runtime modules "
                    "only%s. If the project referenced files that are not "
                    "embedded, they are still wherever the author kept them "
                    "-- the recovered project points at the same paths."
                    % _bin_note)
            payload = struct.pack("<I", opts) + payload[4:]
        if cid == APP_VISTA_CHUNK and len(payload) >= 4:
            level = vista_privilege(app.path.read_bytes())
            if level is None:
                raise Refuse("the PE manifest requests an execution level "
                             "this writer has no .mfa value for")
            payload = struct.pack("<I", level) + payload[4:]
        w.u8(cid)
        w.blob(payload)
        if cid == 0x30 and filter_body is not None:
            w.u8(APP_FILTER_CHUNK)
            w.blob(filter_body)
    w.u8(0)

    out = bytearray(w.bytes())
    for i, off in enumerate(frame_offsets):
        struct.pack_into("<I", out, offset_pos + 4 * i, off)
    struct.pack_into("<I", out, post_pos_slot, post_frames)
    Path(out_path).write_bytes(bytes(out))
    if w.lossy_strings:
        notes.append("%d string(s) hold characters cp1252 cannot represent "
                     "and were substituted: %s"
                     % (len(w.lossy_strings),
                        ", ".join(repr(t) for t in w.lossy_strings[:3])))
    if report is not None:
        report["stripped"] = dict(strip_tally)
        report["substituted_names"] = list(substituted_names)
        report["notes"] = list(notes)

        report["app"] = app
    for n in notes:
        print("report: %s" % n)
    return out_path

def _render_once(raw, palette, memo):
    if memo is not None:
        hit = memo.get(raw)
        if hit is not None:
            return hit
    rec = image_codec.unpack(raw, palette)
    rendered, why = image_codec.icon_render(rec)
    out = (rec, rendered, why)
    if memo is not None:
        memo[raw] = out
    return out

def _pick_image(handles, images, palette=None, memo=None):
    first = None
    for h in handles:
        raw = images.get(h)
        if raw is None:
            continue
        if first is None:
            first = raw
        try:
            _rec, _pic, why = _render_once(raw, palette, memo)
        except image_codec.Unsupported:
            return raw
        if why != image_codec.RENDER_EMPTY:
            return raw
    return first

def _first_image(obj, images, palette=None, memo=None):
    t = obj.get("type")
    props = obj.get("properties") or b""
    if t == 0:

        if len(props) == 38:
            (fill,) = struct.unpack_from("<H", props, 0x18)
            if fill == 3:
                (h,) = struct.unpack_from("<I", props, 0x1A)
                return _pick_image([h], images, palette, memo)
        return None
    if t == 1:

        if len(props) >= 18:
            (h,) = struct.unpack_from("<H", props, 0x10)
            return _pick_image([h], images, palette, memo)
        return None
    if t in (5, 6, 7):

        try:
            base = _section(props, obj.get("name") or "display object")
        except Refuse:
            base = None
        if base is not None:
            try:
                d = _display_section(props, base, obj.get("name") or "display")
            except Refuse:
                d = None
            return _pick_image((d or {}).get("images") or (), images,
                               palette, memo)
        return None
    frames = []
    for aname, dirs in _animations(obj):
        for d in dirs:
            frames.extend(d["frames"])
    return _pick_image(frames, images, palette, memo)

def _icon_planes(w, h, flat):
    colour = bytearray()
    for word in flat:
        colour += struct.pack("<H", 0 if word is None else word)
    stride = image_codec.alpha_row_bytes(w)
    alpha = bytearray(stride * h)
    for y in range(h):
        for x in range(w):
            if flat[y * w + x] is not None:
                alpha[y * stride + x] = 0xFF
    return bytes(colour) + bytes(alpha)

def _object_icon_record(raw, palette=None, memo=None):
    rec, rendered, why = _render_once(raw, palette, memo)
    if why in (image_codec.RENDER_UNDECODED, image_codec.RENDER_SCALED):
        return raw
    if why == image_codec.RENDER_EMPTY:
        return None
    tw, th, flat = rendered
    mode = rec["graphicMode"]
    if mode in (image_codec.MODE_BGR888, image_codec.MODE_PALETTE8):

        flat = tuple(None if v is None else image_codec.to_rgb565(v, mode)
                     for v in flat)
        mode = image_codec.MODE_RGB565
    return _icon_record(tw, th, _icon_planes(tw, th, flat), mode=mode)

def _write_fonts(w, app):
    p = app.payload(0x6667)
    if p is None or len(p) < 4:
        w.u32(0)
        return
    (count,) = struct.unpack_from("<I", p, 0)
    w.u32(count)
    pos = 4
    for _ in range(count):
        handle, dsize, csize = struct.unpack_from("<3I", p, pos)
        raw = zlib.decompress(p[pos + 12 : pos + 12 + csize])

        w.u32(handle)
        w.raw(raw[:12])
        w.raw(raw[12:72])
        pos += 12 + csize

def _write_sounds(w, app):
    p = app.payload(0x6668)
    if p is None or len(p) < 4:
        w.u32(0)
        return
    (count,) = struct.unpack_from("<I", p, 0)
    w.u32(count)
    pos = 4
    for _ in range(count):
        (handle, checksum, references, dsize, sflags, reserved,
         name_len) = struct.unpack_from("<7I", p, pos)
        if sflags & 0x20:

            raw = p[pos + 28 : pos + 28 + dsize]
            pos += 28 + dsize
        else:
            (csize,) = struct.unpack_from("<I", p, pos + 28)
            raw = zlib.decompress(p[pos + 32 : pos + 32 + csize])
            pos += 32 + csize
        w.u32(handle)
        w.u32(checksum)
        w.u32(references)
        w.u32(len(raw))
        w.u32(sflags)
        w.u32(reserved)
        w.u32(name_len)
        w.raw(raw)

def _write_musics(w, app):
    p = app.payload(0x6669)
    if p is None or len(p) < 4:
        w.u32(0)
        return
    (count,) = struct.unpack_from("<I", p, 0)
    w.u32(count)
    pos = 4
    for i in range(count):
        handle, dsize, csize = struct.unpack_from("<3I", p, pos)
        raw = zlib.decompress(p[pos + 12 : pos + 12 + csize])
        if len(raw) != dsize:
            raise Refuse("music record %d inflates to %d bytes, not the %d "
                         "the record claims" % (i, len(raw), dsize))
        (length,) = struct.unpack_from("<I", raw, 8)
        (reserved,) = struct.unpack_from("<I", raw, 16)
        if 24 + length != dsize:
            raise Refuse("music record %d: a %d-byte head plus a %d-byte "
                         "body is not the %d bytes it inflated to"
                         % (i, 24, length, dsize))
        if reserved != 0:
            raise Refuse("music record %d has a non-zero reserved word (%d)"
                         % (i, reserved))
        w.u32(handle)
        w.raw(raw)
        pos += 12 + csize
    if pos != len(p):
        raise Refuse("the music bank left %d bytes over" % (len(p) - pos))

def _icon_record(w, h, body, mode=image_codec.MODE_RGB565):
    return (struct.pack("<3I", zlib.crc32(body) & 0xFFFF, 1, len(body))
            + struct.pack("<2H", w, h)
            + struct.pack("<BBH", mode, 0x10, 0)
            + struct.pack("<4h", 0, 0, 0, 0)
            + struct.pack("<I", 8)
            + body)

BLANK_ICON_SIDE = 32

def _blank_icon_record():
    side = BLANK_ICON_SIDE
    return _icon_record(side, side, bytes(side * side * 3))

ARTWORK_TYPES = frozenset(range(3, 10))

EXTENSION_TYPE_MIN = 32

class _InstalledIcons:
    """The extension icons an editor's extension folder can supply, one record per
    module, with which modules were found and which were not.
    """

    def __init__(self, folder, ext_records):
        self.modules = {}
        self.folder = None
        if folder:
            self.folder = Path(folder)
            if not self.folder.is_dir():
                raise Refuse("extensions folder %s is not a directory" % self.folder)
            for f in self.folder.iterdir():
                if f.suffix.lower() == ".mfx" and f.is_file():
                    self.modules[f.name.lower()] = f
        self.by_handle = {er["handle"]: Path(er["module"]).name
                          for er in ext_records}
        self.records = {}
        self.handles = {}
        self.found = collections.Counter()
        self.missing = collections.Counter()
        self.next_icon = None

    def _module(self, obj):
        t = obj.get("type")
        if self.folder is None or t is None or t < EXTENSION_TYPE_MIN:
            return None
        return self.by_handle.get(t - EXTENSION_TYPE_MIN)

    def record(self, obj):
        name = self._module(obj)
        if name is None:
            return None
        if name not in self.records:
            rec = None
            f = self.modules.get(name.lower())
            if f is not None:
                pic = extensions.editor_icon_picture(f.read_bytes())
                if pic is not None:
                    w, h, flat = pic
                    rec = _icon_record(w, h, _icon_planes(w, h, flat))
            self.records[name] = rec
        rec = self.records[name]
        (self.found if rec is not None else self.missing)[name] += 1
        return rec

    def handle(self, obj, icon_records, next_icon):
        name = self._module(obj)
        self.next_icon = next_icon
        if name not in self.handles:
            self.handles[name] = next_icon
            icon_records.append((next_icon, self.records[name]))
            self.next_icon = next_icon + 1
        return self.handles[name]

    def report(self, notes):
        if self.folder is None:
            return
        if self.found:
            notes.append("%d extension object(s) take the icon of the module "
                         "installed in %s (%s)"
                         % (sum(self.found.values()), self.folder,
                            ", ".join("%s x%d" % (n, c)
                                      for n, c in sorted(self.found.items()))))
        if self.missing:
            notes.append("%d extension object(s) fall back to artwork: their "
                         "module is not in %s or carries no icon (%s)"
                         % (sum(self.missing.values()), self.folder,
                            ", ".join(sorted(self.missing))))

def _wants_artwork(object_type):
    return (object_type in ARTWORK_TYPES
            or (object_type or 0) >= EXTENSION_TYPE_MIN)

_ARTWORK_CACHE = {}

def _artwork_icon_record(path):
    got = _ARTWORK_CACHE.get(path)
    if got is not None:
        return got
    width, height, rgba = read_png_rgba(path)
    if (width, height) != (BLANK_ICON_SIDE, BLANK_ICON_SIDE):
        raise Refuse("%s is %dx%d; object artwork must be %dx%d"
                     % (path, width, height, BLANK_ICON_SIDE, BLANK_ICON_SIDE))
    cstride = image_codec.colour_row_bytes(width)
    astride = image_codec.alpha_row_bytes(width)
    colour = bytearray(cstride * height)
    alpha = bytearray(astride * height)
    for y in range(height):
        for x in range(width):
            red, green, blue, opacity = rgba[(y * width + x) * 4:][:4]
            if opacity < 128 or marker_green(red, green, blue):
                continue
            word = ((red >> 3) << 11) | ((green >> 2) << 5) | (blue >> 3)
            struct.pack_into("<H", colour, y * cstride + x * 2, word)
            alpha[y * astride + x] = 0xFF
    got = _icon_record(width, height, bytes(colour) + bytes(alpha))
    _ARTWORK_CACHE[path] = got
    return got

def _app_icon_records(app, template, notes):
    got = app.app_icon_set()
    if not got:

        small = app.app_icon_small()
        if small is None:
            return None

        planes = scaffold_synthesis.scaled_icon_set({16: small})
        notes.append("this container carries no PE resources, so only the "
                     "application icon's 16x16 entry is recoverable (chunk "
                     "0x2235); it fills the three 16x16 bank slots and is "
                     "scaled up to fill the 48x48 and 32x32 ones")
        return [_icon_record(side, side, c + a) for side, c, a in planes]
    by = {}
    for ic in got:
        by[(ic["bpp"], ic["width"], ic["height"])] = ic
    out = []
    for bpp in (32, 8, 4):
        for side in (48, 32, 16):
            ic = by.get((bpp, side, side))
            if ic is None:

                available = {}
                for d in (4, 8, 32):
                    for ic2 in got:
                        if ic2["bpp"] == d and ic2["width"] == ic2["height"]:
                            available[ic2["width"]] = (ic2["rgb565"], ic2["alpha"])
                planes = scaffold_synthesis.scaled_icon_set(available)
                notes.append("the application icon is incomplete in the "
                             "compiled file (no %dx%d at %d bpp); every slot "
                             "is filled from the sizes it does carry (%s)"
                             % (side, side, bpp,
                                ", ".join("%dx%d" % (k, k) for k in sorted(available))))
                return [_icon_record(sd, sd, c + a) for sd, c, a in planes]
            out.append(_icon_record(side, side, ic["rgb565"] + ic["alpha"]))
    return out

def _blank_app_icon_records():
    out = []
    for _bpp, side in scaffold_synthesis.ICON_SLOTS:
        out.append(_icon_record(side, side, bytes(side * side * 2) + bytes(side * side)))
    return out

def _write_image_bank(w, template_bank, records, graphic_mode=None):

    w.u32(template_bank["graphicMode"] if graphic_mode is None else graphic_mode)
    w.u16(template_bank["paletteVersion"])
    w.u16(template_bank["paletteEntries"])
    w.raw(template_bank["palette"])
    w.u32(len(records))
    for handle, raw in records:
        w.u32(handle)
        w.raw(raw)

def _write_value_list(w, items):
    w.u32(len(items))
    for vtype, value in items:
        w.s("")
        w.u32(vtype)
        if vtype == 2:
            w.s(value)
        else:
            w.i32(value)

def _animations(obj):
    out = []
    for anim in obj.get("animations") or []:
        slot = anim.get("slot")
        dirs = []
        for d in anim.get("directions", []):
            dirs.append(dict(index=d.get("direction", 0),
                             minSpeed=d.get("minSpeed", 50),
                             maxSpeed=d.get("maxSpeed", 50),
                             repeat=d.get("repeat", 1),
                             backTo=d.get("backTo", 0),
                             frames=d.get("frames", [])))
        out.append((slot, dirs))
    return out

def _exe_event_sections(p):
    """A frame's compiled event sheets, each as a list of records.

    The game stores the frame's own events, each behaviour's, and the global ones
    as separate sections, and records nothing about which is which.
    """
    idx = p.find(b"ERes")
    if idx < 0 or idx + 8 > len(p):
        raise Refuse("frame events carry no ERes")
    (total,) = struct.unpack_from("<I", p, idx + 4)
    if total == 0:
        return None
    pos, seen, sections = idx + 8, 0, []
    while seen < total:
        if p[pos : pos + 4] != b"ERev":
            raise Refuse("ERev section chain broke at %d" % pos)
        (size,) = struct.unpack_from("<I", p, pos + 4)
        q, end, records = pos + 8, pos + 8 + size, []
        while q < end:
            (neg,) = struct.unpack_from("<h", p, q)
            n = -neg
            if n <= 0 or q + n > end:
                raise Refuse("event record walk broke at %d" % q)
            records.append(bytes(p[q : q + n]))
            q += n
        sections.append(records)
        pos, seen = end, seen + size
    return sections

def _aces(rec):
    out, r = [], 14
    for kind, cnt in (("condition", rec[2]), ("action", rec[3])):
        for _ in range(cnt):
            (size,) = struct.unpack_from("<H", rec, r)
            if size < 14 or r + size > len(rec):
                raise Refuse("ACE walk broke inside an event record")
            out.append((kind, r, size))
            r += size
    return out

def strip_record(rec, ghosts):
    aces = _aces(rec)
    keep, dropped = [], 0
    for kind, r, size in aces:
        named = any(oi in ghosts
                    for oi in divergence.ace_object_refs(rec, kind, r, size))
        if named and kind == "condition":
            return None, 0
        if named:
            dropped += 1
            continue
        keep.append((kind, rec[r:r + size]))
    if not dropped:
        return rec, 0
    conds = [b for k, b in keep if k == "condition"]
    acts = [b for k, b in keep if k == "action"]
    if not acts:

        return None, dropped
    body = b"".join(conds) + b"".join(acts)
    head = bytearray(rec[:14])
    head[2] = len(conds)
    head[3] = len(acts)
    out = bytearray(bytes(head) + body)

    struct.pack_into("<h", out, 0, -len(out))
    return bytes(out), dropped

RANDOMIZE_SEED = bytes.fromhex("ffffffff")

EFFECTS_DEFAULT_FRAME = bytes.fromhex("00000000ffffffffffffffff00000000")

def _frame_effects(rec, index, app, notes):
    """The effect applied to a whole frame, as the project stores it.

    The accelerated runtime writes this record for every frame whether or not an
    effect was chosen, so nearly all of them say "none". Where one is real it
    names a shader and carries the values the author typed for its parameters;
    both are recovered, with the parameter names taken from the shader the game
    carries with it.
    """
    p = rec.get(0x3349)
    if p is None:
        return None
    if len(p) < 16:
        raise Refuse("frame %d: 0x3349 is %d bytes, short of the 16-byte "
                     "record" % (index, len(p)))
    word, param, sidx, pcount = struct.unpack_from("<4I", p, 0)
    if 16 + 4 * pcount != len(p):
        raise Refuse("frame %d: 0x3349 is %d bytes; %d parameter(s) need %d"
                     % (index, len(p), pcount, 16 + 4 * pcount))
    if p == EFFECTS_DEFAULT_FRAME:
        notes.append("frame %d carries the HWA runtime's 0x3349 frame-effects "
                     "chunk at its default (no effect); it holds no project "
                     "data and is not carried" % index)
    try:
        bank = app.shaders()
    except Exception:
        bank = []
    return _effect_record(word, param, sidx, pcount, p, 16, bank,
                          "frame %d" % index, notes)

def _effect_record(word, param, sidx, pcount, buf, voff, bank, label, notes):
    """One effect record, shared by a frame and by each of its layers.

    The two differ only in where the parameter values sit, so the record itself
    is built once here rather than written out twice.
    """
    body = bytearray()
    body += struct.pack("<2I", _layer_effect_id(word), param)
    eid = word & 0xFF
    name, decls = None, []
    if sidx != 0xFFFFFFFF:
        if sidx >= len(bank):
            raise Refuse("%s names shader %d and the 0x2243 bank holds %d"
                         % (label, sidx, len(bank)))
        name, _src, decls = bank[sidx]
    if name is None:
        body += struct.pack("<I", 0)
        if eid:
            notes.append("%s: HWA effect id %d, no shader (recovered from "
                         "the compiled file)" % (label, eid))
        return bytes(body)
    if pcount != len(decls):
        raise Refuse("%s has %d parameter value(s) and %r declares %d"
                     % (label, pcount, name, len(decls)))
    if voff + 4 * pcount > len(buf):
        raise Refuse("%s: parameters run past the effects chunk" % label)
    body += struct.pack("<I", 1)

    nb = name.encode("cp1252", "replace")
    body += struct.pack("<I", len(nb)) + nb
    body += struct.pack("<I", pcount)
    for j, (pname, ptype) in enumerate(decls):
        pb = pname.encode("cp1252", "replace")
        (val,) = struct.unpack_from("<I", buf, voff + 4 * j)
        body += struct.pack("<I", len(pb)) + pb
        body += struct.pack("<2I", ptype, val)
    notes.append("%s: HWA effect %r with %d parameter(s), recovered from the "
                 "compiled file" % (label, name, pcount))
    return bytes(body)

def _layer_effect_id(word):
    """The effect number a layer's compiled record stands for.

    Almost always it is read straight off the record. The exception is semi
    transparency, which the accelerated runtime does not treat as an effect at
    all -- it just blends -- so the compiled record says "no effect" and carries
    the blend instead, and this turns that back into the option the author chose.
    A layer left fully opaque compiles to something indistinguishable from having
    no effect, and that one case cannot be recovered; it looks the same either way.
    """
    return (word & 0xFF) or (1 if word & 0x1000 else 0)

def _layer_effects(rec, index, layer_count, app, notes):
    p = rec.get(0x3345)
    if p is None:
        return None
    need = 20 * layer_count
    if len(p) < need:
        raise Refuse("frame %d: 0x3345 is %d bytes, short of the %d its %d "
                     "layers need" % (index, len(p), need, layer_count))
    heads = [struct.unpack_from("<5I", p, i * 20) for i in range(layer_count)]
    total = sum(h[3] for h in heads)
    if need + 4 * total != len(p):
        raise Refuse("frame %d: 0x3345 is %d bytes; %d layers and %d "
                     "parameter(s) need %d"
                     % (index, len(p), layer_count, total, need + 4 * total))
    try:
        bank = app.shaders()
    except Exception:
        bank = []
    out = []
    for li, (word, param, sidx, pcount, poff) in enumerate(heads):
        out.append(_effect_record(word, param, sidx, pcount, p, poff, bank,
                                  "frame %d layer %d" % (index, li), notes))
    return b"".join(out)

def _ace_params(rec, kind, r, size):
    q = r + (0x10 if kind == "condition" else 0x0E)
    end = r + size
    out = []
    while q < end:
        if q + 4 > end:
            raise Refuse("parameter head overruns its ACE record")
        psize, ptype = struct.unpack_from("<2H", rec, q)
        if psize < 4 or q + psize > end:
            raise Refuse("parameter size %d does not fit its ACE record"
                         % psize)
        out.append((q, ptype, q + 4, psize - 4))
        q += psize
    return out

def _remap_qualifiers(out, rec, kind, r, size, qhandle, where, residue):
    def rewrite(off, what, strict):
        (v,) = struct.unpack_from("<H", rec, off)
        if not v & 0x8000:
            return
        qid = v & 0x7FFF
        if qid > QUALIFIER_ID_MAX:
            if strict:
                raise Refuse("%s: %s references qualifier %d, outside the "
                             "proven 0..%d id space"
                             % (where, what[0] % what[1:], qid,
                                QUALIFIER_ID_MAX))
            return
        if qid not in qhandle:
            raise Refuse("%s: %s references qualifier %d, which has no EvOb "
                         "entry in this frame to bind it to"
                         % (where, what[0] % what[1:], qid))
        struct.pack_into("<H", out, off, qhandle[qid])

    (objtype,) = struct.unpack_from("<h", rec, r + 2)
    if objtype >= 0:
        rewrite(r + 6, ("the ACE head",), True)
    for _poff, ptype, body, blen in _ace_params(rec, kind, r, size):

        sites = QUALIFIER_PARAM_SITES.get(ptype, ())
        declared = set(sites)
        for site in sites:
            if site + 2 <= blen:
                rewrite(body + site, ("parameter type %d +0x%02X", ptype,
                                      site), False)
        if ptype in EXPRESSION_PARAM_TYPES:
            toks = _expression_tokens(rec[body:body + blen])
            if toks is None:
                raise Refuse("%s: a type-%d expression body does not close on "
                             "its terminator" % (where, ptype))
            for pos, otype, _code, tsize in toks:
                if otype < 0 or tsize < 8:
                    continue
                declared.add(pos + 6)
                rewrite(body + pos + 6,
                        ("a type-%d expression token at +0x%02X", ptype, pos),
                        False)

        nwords = blen // 2
        if nwords:
            words = struct.unpack_from("<%dH" % nwords, rec, body)
            for i, v in enumerate(words):
                if v & 0x8000 and (v & 0x7FFF) in qhandle:
                    off = i * 2
                    if off not in declared:
                        residue[(ptype, off)] += 1

GROUP_PARAM_TYPE = 38

GROUP_ID_IN_BODY = 0x02

def _group_id_site(rec):
    if not rec[2] or len(rec) < 20:
        return None
    if struct.unpack_from("<2h", rec, 16) != (-1, -10):
        return None
    kind, r, size = _aces(rec)[0]
    for _poff, ptype, body, blen in _ace_params(rec, kind, r, size):
        if ptype == GROUP_PARAM_TYPE and blen >= GROUP_ID_IN_BODY + 2:
            return body + GROUP_ID_IN_BODY
    return None

def _renumber_inlined_groups(records, index, notes):
    """Give every event group in the merged list its own number again.

    Each sheet numbered its groups from scratch, so joining them collides numbers
    that were only ever unique within one sheet.  Nothing refers to a group by
    number, so renumbering is safe — and leaving the collision in is not.
    """
    sites = []
    for rec in records:
        at = _group_id_site(rec)
        if at is not None:
            sites.append((rec, at, struct.unpack_from("<H", rec, at)[0]))
    if not sites:
        return 0
    used = {gid for _rec, _at, gid in sites}
    seen, moved, nxt = set(), 0, 0
    for rec, at, gid in sites:
        if gid not in seen:
            seen.add(gid)
            continue
        while nxt in used:
            nxt += 1
        if nxt > 0xFFFF:
            raise Refuse("frame %d: more than 65536 event groups after "
                         "inlining -- no free group id left" % index)
        struct.pack_into("<H", rec, at, nxt)
        used.add(nxt)
        seen.add(nxt)
        moved += 1
    if moved:
        notes.append(
            "frame %d: %d event group(s) came from an inlined global-events "
            "or behaviour section whose group id collided with one already "
            "in the frame's own list; they were renumbered (a group id is "
            "unique per event list and nothing references a group by it)"
            % (index, moved))
    return moved

def _normalize_record(rec, evob_handles, qhandle, where, residue):
    """Rewrite one compiled event record into the form the project file stores.
    """
    out = bytearray(rec)
    for kind, r, size in _aces(rec):
        if kind == "condition":
            struct.pack_into("<H", out, r + 0x0E, 0)
        (objtype,) = struct.unpack_from("<h", rec, r + 2)
        if objtype >= 0:
            (oi,) = struct.unpack_from("<H", rec, r + 6)
            if not oi & 0x8000 and oi not in evob_handles:
                raise Refuse("%s references object %d, which has no instance "
                             "in the frame -- no EvOb entry to bind it to"
                             % (where, oi))
        _remap_qualifiers(out, rec, kind, r, size, qhandle, where, residue)
    return bytes(out)

def _write_frame(w, app, frame, index, objects, images, object_icons, notes,
                 share_bit_ok, section_labels=True, frame_handle=None,
                 strip_oi=frozenset(), strip_tally=None):
    """One frame: settings, layers, transitions, its objects, their placements, and
    its events.
    """
    from klikback.core.mmf2.read_app import walk_chunks
    chunk = app.by_id[0x3333][index]
    kids, stop, _ = walk_chunks(chunk.payload, 0, len(chunk.payload), keep_payload=True)
    rec = {c.id: c.payload for c in kids}
    head = rec[0x3334]
    fwidth, fheight, background = struct.unpack_from("<3I", head, 0)
    (eflags,) = struct.unpack_from("<I", head, 0x0C)
    mfa_fflags = map_frame_flags(eflags, index, share_bit_ok)
    frame_fx = _frame_effects(rec, index, app, notes)
    sections = (_exe_event_sections(rec[0x333D])
                if rec.get(0x333D) is not None else None)
    if strip_oi and sections is not None:

        kept_sections = []
        for sec in sections:
            out = []
            for r in sec:
                new, nacts = strip_record(r, strip_oi)
                if new is None:
                    strip_tally["records"] += 1
                else:
                    out.append(new)
                strip_tally["actions"] += nacts
            kept_sections.append(out)
        sections = kept_sections
    if strip_oi:
        before = len(frame["instances"])
        frame["instances"] = [i for i in frame["instances"]
                              if i.get("objectInfo") not in strip_oi]
        strip_tally["instances"] += before - len(frame["instances"])

    layers = _parse_layers(rec.get(0x3341), index)
    layer_fx = _layer_effects(rec, index, len(layers), app, notes)

    w.u32(index if frame_handle is None else frame_handle)
    w.s(frame["name"] or "Frame %d" % (index + 1))
    w.u32(fwidth)
    w.u32(fheight)
    w.u32(background)
    w.u32(mfa_fflags)

    ep = rec.get(0x333D)
    max_objects = (struct.unpack_from("<H", ep, 4)[0]
                   if ep is not None and len(ep) >= 6 else 500)
    w.u32(max_objects)
    w.s(frame.get("password") or "")
    w.u32(0)

    w.i32(fwidth // 2)
    w.i32(fheight // 2)
    pal = rec.get(0x3337)
    w.u32(256)
    if pal is not None and len(pal) >= 4 + 1024:
        w.raw(pal[4 : 4 + 1024])
    else:
        w.raw(bytes(1024))
    w.u32(0xFFFFFFFF)
    w.u32(0)
    w.u32(len(layers))
    for li, (lname, lflags, xc, yc) in enumerate(layers):

        w.s("" if lname == "Layer %d" % (li + 1) else lname)
        w.u32(map_layer_flags(lflags, index, li, notes))
        w.f32(xc)
        w.f32(yc)

    _write_fades(w, frame, "frame %d" % index, notes)

    used = sorted({inst["objectInfo"] for inst in frame["instances"]})
    item_handle = {oi: i for i, oi in enumerate(used)}
    w.u32(len(used))
    for oi in used:
        _write_frame_item(w, objects[oi], item_handle[oi], object_icons,
                          app, notes)

    w.u32(len(used))
    for oi in used:
        w.u32(0x70000005)
        w.u32(item_handle[oi])

    _dedupe_instance_handles(frame["instances"], index, notes)
    w.u32(len(frame["instances"]))
    for inst in frame["instances"]:
        layer = inst.get("layer", 0)
        if layer >= len(layers):
            raise Refuse("frame %d: instance on layer %d, but the frame has "
                         "%d layers" % (index, layer, len(layers)))

        ptype = inst.get("parentType", 0)
        if ptype not in (0, 1, 2):
            raise Refuse("frame %d: instance parentType %d is outside the "
                         "known set {0, 1, 2}" % (index, ptype))
        if ptype == 2:
            pref = inst["parentObjectInfo"]

            if pref & 0x8000 and (pref & 0x7FFF) <= QUALIFIER_ID_MAX:
                raise Refuse("frame %d: instance parent is qualifier %d -- a "
                             "qualifier parent has no known project-file form"
                             % (index, pref & 0x7FFF))
            if pref not in item_handle:

                parent = 0xFFFFFFFF
                if pref & 0x8000:

                    notes.append("frame %d: an instance's parent field holds "
                                 "0x%04X (i16 %d), which is neither an object "
                                 "in this file nor a value in the qualifier "
                                 "id space 0..%d; read as the 'no parent' "
                                 "sentinel and stored as the editor stores a "
                                 "dangling parent -- parentType 2, "
                                 "parentHandle -1"
                                 % (index, pref, pref - 0x10000,
                                    QUALIFIER_ID_MAX))
                else:
                    notes.append("frame %d: a placeholder instance's parent "
                                 "(objectInfo %d) has no instance in this "
                                 "frame; stored as the editor stores a "
                                 "dangling parent -- parentType 2, "
                                 "parentHandle -1" % (index, pref))
            else:
                parent = item_handle[pref]
        else:
            parent = 0xFFFFFFFF

            if inst.get("parentObjectInfo"):

                notes.append("frame %d: instance %d is parentType %d with a "
                             "non-zero parent field (%d), a combination whose "
                             "meaning is not known, so it is not remapped and "
                             "the editor's parent for it is not recovered"
                             % (index, inst.get("handle", -1), ptype,
                                inst["parentObjectInfo"]))

        flags = 0x8 if ptype else 0
        w.i32(inst["x"])
        w.i32(inst["y"])
        w.u32(layer)
        w.u32(inst["handle"])
        w.u32(flags)
        w.u32(ptype)
        w.u32(item_handle[inst["objectInfo"]])
        w.u32(parent)
    _write_events(w, used, objects, item_handle, sections, index, notes,
                  section_labels)
    _write_frame_chunks(w, rec, fwidth, fheight, layer_fx, frame_fx)

def _dedupe_instance_handles(instances, index, notes):
    """Give every placed object in a frame a distinct handle.

    A large project can run the editor's handle counter past what the compiled
    field holds, and the truncation makes two objects share a number.  Uniqueness
    can be restored; the original numbers cannot, and the report says so.
    """
    used = {inst["handle"] for inst in instances}
    seen, moved, nxt = set(), 0, 0
    for inst in instances:
        h = inst["handle"]
        if h not in seen:
            seen.add(h)
            continue
        while nxt in used:
            nxt += 1
        if nxt > 0xFFFF:
            raise Refuse("frame %d: no free instance handle left" % index)
        inst["handle"] = nxt
        used.add(nxt)
        seen.add(nxt)
        moved += 1
    if moved:
        notes.append(
            "frame %d: %d instance(s) shared a handle with an earlier one -- "
            "the editor's handle allocator passed 65,536 and the compile "
            "truncated it into the EXE's u16 field, so the wrapped handles "
            "collided; the later occurrence was renumbered so every instance has its "
            "own handle. The original values are not recoverable from the "
            "EXE -- uniqueness is restored, the number is a compile loss"
            % (index, moved))
    return moved

def _parse_layers(p, index):
    if p is None:
        raise Refuse("frame %d has no 0x3341 layer chunk" % index)
    (count,) = struct.unpack_from("<I", p, 0)
    pos, out = 4, []
    for _ in range(count):
        flags, xc, yc = struct.unpack_from("<Iff", p, pos)
        pos += 20
        end = p.index(b"\0", pos)
        name = p[pos:end].decode("cp1252", "replace")
        pos = end + 1
        out.append((name, flags, xc, yc))
    if pos != len(p):
        raise Refuse("frame %d: 0x3341 leaves %d bytes over"
                     % (index, len(p) - pos))
    return out

def _write_frame_item(w, obj, per_frame_handle, object_icons, app, notes):
    """One object as the project defines it, with the body its type calls for.
    """
    t = obj.get("type")
    if t is None or not (0 <= t <= 9 or t >= 32):
        raise Refuse("object type %s has no writer yet" % t)

    oflags = obj.get("flags", 0)
    if oflags & ~OBJECT_FLAGS_MEASURED:
        raise Refuse("object %r: 0x4444 flag bits 0x%04X are unmapped"
                     % (obj.get("name"), oflags & ~OBJECT_FLAGS_MEASURED))
    ink = obj.get("inkEffect", 0x10000000)
    inkp = obj.get("inkEffectParameter", 0)
    if ink & ~0x300010FF:
        raise Refuse("object %r: inkEffect 0x%08X has unmapped bits"
                     % (obj.get("name"), ink))

    item_chunks = _item_chunks(obj, t, app, notes)
    if any(cid == 0x2D for cid, _ in item_chunks):

        inkp = 0
    elif inkp == 0xFFFFFFFF:

        inkp = 0
        notes.append("object %r: the HWA runtime's unused ink parameter "
                     "(0xFFFFFFFF) normalized to the editor's 0"
                     % obj.get("name"))
    w.i32(t)
    w.u32(per_frame_handle)
    w.s(obj.get("name") or "")
    w.u32(1 if ink & 0x10000000 else 0)
    w.u32(ink & 0xFF)
    w.u32(inkp)
    w.u32(1 if ink & 0x20000000 else 0)
    w.u32(oflags)
    w.u32(1)
    w.u32(object_icons.get(obj["handle"], 0))

    for cid, payload in item_chunks:
        w.u8(cid)
        w.blob(payload)
    w.u8(0)

    if t == 0:
        _write_quick_backdrop_body(w, obj, notes)
        return

    if t == 1:

        props = obj.get("properties") or b""
        if len(props) < 18:
            raise Refuse("Backdrop %r: 0x4446 is %d bytes, expected 18"
                         % (obj.get("name"), len(props)))
        obstacle, collision = struct.unpack_from("<2H", props, 4)
        (image_handle,) = struct.unpack_from("<H", props, 0x10)
        w.u32(obstacle)
        w.u32(collision)
        w.u32(image_handle)
        return

    if t >= 32:
        _write_extension_body(w, obj, notes)
        return

    _write_object_head(w, obj, t)
    _write_value_list(w, [(0, v) for v in (obj.get("values") or [])])
    _write_value_list(w, [(2, s) for s in (obj.get("strings") or [])])
    _write_movements(w, obj, notes)
    w.u32(0)
    _write_fades(w, obj, "object %r" % (obj.get("name"),), notes)
    if t != 2:

        _write_typed_body(w, obj, t, notes)
        return
    anims = _animations(obj)
    if not anims:
        w.u8(0)
    else:

        by_slot = {slot: dirs for slot, dirs in anims}
        w.u8(1)
        w.u32(max(by_slot) + 1)
        for slot in range(max(by_slot) + 1):
            dirs = by_slot.get(slot, [])
            w.s("")
            w.u32(len(dirs))
            for d in dirs:
                w.u32(d["index"])
                w.u32(d["minSpeed"])
                w.u32(d["maxSpeed"])
                w.u32(d["repeat"])
                w.u32(d["backTo"])
                w.u32(len(d["frames"]))
                for h in d["frames"]:
                    w.u32(h)

def _cstr(b, off):
    end = b.find(b"\0", off)
    if end < 0:
        raise Refuse("a string at 0x%X in a 0x4446 block runs past its end "
                     "with no terminator" % off)
    return b[off:end], end + 1

def _section(props, name, sized=True):
    if len(props) < 0x14:
        raise Refuse("%s: 0x4446 is %d bytes, too short for the shared head"
                     % (name, len(props)))
    (base,) = struct.unpack_from("<I", props, 0x0C)
    if base == 0:
        return None
    if base + 4 > len(props):
        raise Refuse("%s: section offset 0x%X is outside its %d-byte block"
                     % (name, base, len(props)))
    if sized:
        (size,) = struct.unpack_from("<I", props, base)
        if size < 4 or base + size > len(props):
            raise Refuse("%s: section at 0x%X claims %d bytes, block is %d"
                         % (name, base, size, len(props)))
    return base

def _paragraph_table(props, base, name):
    size, width, height, count = struct.unpack_from("<4I", props, base)
    recs = []
    for i in range(count):
        (off,) = struct.unpack_from("<I", props, base + 0x10 + 4 * i)
        r = base + off
        if r + 8 > base + size:
            raise Refuse("%s: paragraph %d starts at +%d, past the section"
                         % (name, i, off))
        font = struct.unpack_from("<h", props, r)[0]
        flags = struct.unpack_from("<H", props, r + 2)[0]
        colour = struct.unpack_from("<I", props, r + 4)[0]
        text, _end = _cstr(props, r + 8)
        recs.append(dict(font=font, flags=flags, colour=colour, text=text))
    if not recs:
        raise Refuse("%s: the paragraph table is empty" % name)
    return width, height, recs

def _display_section(props, base, name):
    size, width, height = struct.unpack_from("<3I", props, base)
    player, display, fixed, font, count = struct.unpack_from(
        "<5H", props, base + 0x0C)
    if base + 0x16 + 2 * count > base + size:
        raise Refuse("%s: %d display images run past the section" % (name, count))
    images = (list(struct.unpack_from("<%dH" % count, props, base + 0x16))
              if count else [])

    tail = base + 0x16 + 2 * count
    colour1 = colour2 = tail_flags = gradient = 0
    if tail + 0x14 <= base + size:
        (tail_flags,) = struct.unpack_from("<H", props, tail + 6)
        colour1, colour2, gradient = struct.unpack_from("<3I", props, tail + 8)
    return dict(size=size, width=width, height=height, player=player,
                displayType=display, fixed=fixed, font=font, images=images,
                colour1=colour1, colour2=colour2, tailFlags=tail_flags,
                gradient=gradient)

def _u32_of(font):
    return font & 0xFFFFFFFF

def _counter_format_chunk(word):
    fixed = word & 0x000F
    flags = ((1 if fixed else 0) | (2 if word & 0x0200 else 0)
             | (4 if word & 0x0400 else 0) | (8 if word & 0x0800 else 0))
    sig = (((word >> 4) & 0x1F) + 1 if word & 0x0200 else COUNTER_SIG_DEFAULT)
    dec = ((word >> 12) & 0x0F if word & 0x0400 else COUNTER_DEC_DEFAULT)
    return bytes([flags, fixed, sig, dec])

def _object_effect_chunk(obj, app, notes):
    """The visual effect set on one object: its blend colour, and the shader it uses
    with that shader's own parameter names, types and values.

    A game built for the hardware-accelerated runtime keeps all of this, in three
    different places -- the colour on the object, the shader's code and parameter
    list in a bank shared by the whole application, and this object's own values
    beside it. The project file wants them as one record, so this is where they
    are put back together.

    An object with no effect gets no record at all, and the rule for telling the
    two apart is the flag the runtime sets when the colour is in use rather than
    the effect number alone: an effect number by itself does not mean the object
    customised anything.
    """
    ink = obj.get("inkEffect", 0)
    blob = obj.get("shader")
    if blob is None and not (ink & 0xFF and ink & 0x1000):
        if ink & 0x1000:
            notes.append("object %r: ink bit 12 (the colour/alpha word is in "
                         "use) with effect id 0 -- no effect for a chunk 45 "
                         "to carry, so the word is not written"
                         % obj.get("name"))
        return None
    word0 = obj.get("inkEffectParameter", 0)
    body = bytearray(struct.pack("<I", word0))
    if blob is None:
        body += struct.pack("<I", 0)
        notes.append("object %r: HWA effect id %d with colour/blend 0x%08X, "
                     "recovered from the compiled file"
                     % (obj.get("name"), ink & 0xFF, word0))
        return bytes(body)
    if len(blob) < 8:
        raise Refuse("object %r: 0x4448 is %d bytes, too short for its head"
                     % (obj.get("name"), len(blob)))
    sidx, pcount = struct.unpack_from("<2I", blob, 0)
    if 8 + 4 * pcount != len(blob):
        raise Refuse("object %r: 0x4448 is %d bytes; %d parameter(s) need %d"
                     % (obj.get("name"), len(blob), pcount, 8 + 4 * pcount))
    try:
        bank = app.shaders()
    except Exception:
        bank = []
    if sidx >= len(bank):
        raise Refuse("object %r names shader %d and the 0x2243 bank holds %d"
                     % (obj.get("name"), sidx, len(bank)))
    name, _src, decls = bank[sidx]
    if pcount != len(decls):
        raise Refuse("object %r has %d parameter value(s) and %r declares %d"
                     % (obj.get("name"), pcount, name, len(decls)))

    nb = name.encode("cp1252", "replace")
    body += struct.pack("<I", 1)
    body += struct.pack("<I", len(nb)) + nb
    body += struct.pack("<I", pcount)
    for j, (pname, ptype) in enumerate(decls):
        pb = pname.encode("cp1252", "replace")
        (val,) = struct.unpack_from("<I", blob, 8 + 4 * j)
        body += struct.pack("<I", len(pb)) + pb
        body += struct.pack("<2I", ptype, val)
    notes.append("object %r: HWA effect %r with %d parameter(s), recovered "
                 "from the compiled file" % (obj.get("name"), name, pcount))
    return bytes(body)

def _item_chunks(obj, t, app, notes):
    props = obj.get("properties") or b""
    tail = []
    fx = _object_effect_chunk(obj, app, notes)
    if fx is not None:
        tail.append((0x2D, fx))
    if t in (5, 6):
        base = _section(props, obj.get("name") or "Score/Lives")
        fixed = struct.unpack_from("<H", props, base + 0x10)[0] if base else 0
        digits = fixed if fixed else SCORE_DIGITS_DEFAULT[t]
        return [(0x17, bytes([1 if fixed else 0, digits & 0xFF]))] + tail
    if t == 7:
        base = _section(props, obj.get("name") or "Counter")
        word = struct.unpack_from("<H", props, base + 0x10)[0] if base else 0
        return [(0x16, _counter_format_chunk(word))] + tail
    return tail

def _write_typed_body(w, obj, t, notes):
    """What each object type adds after the shared body — paragraphs, digit images,
    an animation table, a sub-application.
    """
    props = obj.get("properties") or b""
    name = obj.get("name") or "object"
    base = _section(props, name, sized=t != 9)

    if t == 3:
        width, height, recs = _paragraph_table(props, base, name)
        w.u32(width)
        w.u32(height)
        w.u32(_u32_of(recs[0]["font"]))
        w.u32(recs[0]["colour"])
        w.u32(recs[0]["flags"])
        w.u32(0)
        w.u32(len(recs))
        for r in recs:
            w.s(r["text"])
            w.u32(0)
        return

    if t == 4:
        width, height, recs = _paragraph_table(props, base, name)
        if len(recs) < 2:
            raise Refuse("%s: a Question & Answer with %d paragraph(s) has no "
                         "answer to write" % (name, len(recs)))
        q, answers = recs[0], recs[1:]
        w.u32(width)
        w.u32(height)
        w.u32(_u32_of(q["font"]))
        w.u32(q["colour"])
        w.u32(QA_CONST)
        w.u32(q["flags"] >> 9)
        w.u32(1)
        w.s(q["text"])
        w.u32(0)
        w.u32(_u32_of(answers[0]["font"]))
        w.u32(answers[0]["colour"])
        w.u32(QA_CONST)
        w.u32(answers[0]["flags"] >> 9)
        w.u32(len(answers))
        for a in answers:
            w.s(a["text"])
            w.u32((a["flags"] >> 8) & 1)
        return

    if t in (5, 6):
        if base is None:
            raise Refuse("%s: a Score/Lives with no display section is an "
                         "unmeasured state" % name)
        d = _display_section(props, base, name)
        text_mode = d["displayType"] == 5
        w.u32(d["player"])
        w.u32(len(d["images"]))
        for h in d["images"]:
            w.u32(h)
        w.u32(1 if text_mode else 0)
        w.u32(d["colour1"] if text_mode else 0)
        w.u32(d["font"] if text_mode else 0xFFFFFFFF)
        w.i32(d["width"])
        w.i32(d["height"])
        return

    if t == 7:

        end = base if base is not None else len(props)
        if end < 12:
            raise Refuse("%s: no room for the counter's value block" % name)
        value, minimum, maximum = struct.unpack_from("<3i", props, end - 12)
        images = []
        colour1, colour2 = 0, 255
        display_flags, gradient, count_type = 1, 0, 1
        if base is None:
            display = 0
            width, height = COUNTER_HIDDEN_SIZE
            font = 0xFFFFFFFF
            notes.append("object %r: the Counter is hidden, so the compiled "
                         "file carries no size and no number format for it; "
                         "substituted the editor's %dx%d default"
                         % (name, width, height))
        else:
            d = _display_section(props, base, name)
            display, width, height = d["displayType"], d["width"], d["height"]
            images = d["images"]
            font = d["font"] if display == 5 else 0xFFFFFFFF
            if display in (2, 3):
                colour1, colour2 = d["colour1"], d["colour2"]
                display_flags, gradient = d["tailFlags"], d["gradient"]

                count_type = 1 if d["fixed"] & 0x0100 else 0
                if not count_type:
                    width = -width
        w.i32(value)
        w.i32(minimum)
        w.i32(maximum)
        w.u32(display)
        w.u32(display_flags)
        w.u32(colour1)
        w.u32(colour2)
        w.u32(gradient)
        w.u32(count_type)
        w.i32(width)
        w.i32(height)
        w.u32(len(images))
        for h in images:
            w.u32(h)
        w.u32(font)
        return

    if t == 8:
        if base is None:
            raise Refuse("%s: a Formatted Text with no section" % name)
        rtf_flags, colour, width, height = struct.unpack_from(
            "<4I", props, base + 0x08)

        (tlen,) = struct.unpack_from("<I", props, base + 0x1C)
        if base + 0x20 + tlen > len(props):
            raise Refuse("%s: the RTF text claims %d bytes, block is %d"
                         % (name, tlen, len(props)))
        text = props[base + 0x20 : base + 0x20 + tlen]
        text = text.split(b"\0", 1)[0].decode("cp1252", "replace")
        w.i32(width)
        w.i32(height)
        w.u32(rtf_flags)
        w.u32(colour)
        w.s(text)
        return

    if t == 9:
        if base is None:
            raise Refuse("%s: a Sub-application with no section" % name)

        width, height = struct.unpack_from("<2I", props, base + 0x04)
        start_frame = struct.unpack_from("<H", props, base + 0x0E)[0]
        (options,) = struct.unpack_from("<I", props, base + 0x10)
        path, _end = _cstr(props, base + 0x1C)

        if not options & 0x4000:
            start_frame = 0xFFFFFFFF

        if options & (1 << 20):
            options &= ~((1 << 6) | (1 << 9) | (1 << 10))
        if path:

            if path.lower().endswith(b".ccn"):
                path = path[:-4] + b".mfa"
                notes.append("object %r: the sub-application's compiled "
                             "target %s is stored by the editor as the "
                             "project it was built from"
                             % (name, path.decode("cp1252", "replace")))
        w.s(path)
        w.i32(width)
        w.i32(height)
        w.u32(options)
        w.u32(start_frame)
        if start_frame != 0xFFFFFFFF:
            w.i32(-1)
        return

    raise Refuse("object type %s has no writer yet" % t)

def _write_quick_backdrop_body(w, obj, notes):
    props = obj.get("properties") or b""
    name = obj.get("name") or "Quick Backdrop"
    if len(props) != 38:

        raise Refuse("Quick Backdrop %r: its property block is %d bytes; "
                     "every one KlikBack has seen is 38"
                     % (name, len(props)))
    obstacle, collision = struct.unpack_from("<2H", props, 4)
    width, height = struct.unpack_from("<2I", props, 8)
    (border_size,) = struct.unpack_from("<H", props, 0x10)
    (border_colour,) = struct.unpack_from("<I", props, 0x12)
    shape, fill = struct.unpack_from("<2H", props, 0x16)
    a, b, shape_flags = struct.unpack_from("<3I", props, 0x1A)
    if collision != 1:

        raise Refuse("Quick Backdrop %r: collision mode %d -- the compiler "
                     "writes 1 for every one KlikBack has seen, and the "
                     "editor stores 0 beside it" % (name, collision))

    image, colour1, colour2 = 0xFFFFFFFF, QB_COLOR1_DEFAULT, QB_COLOR2_DEFAULT
    if fill == 3:
        image = a
    elif fill in (1, 2):
        colour1 = a
        if fill == 2:
            colour2 = b
    w.u32(obstacle)
    w.u32(0)
    w.u32(width)
    w.u32(height)
    w.u32(shape)
    w.u32(border_size)
    w.u32(border_colour)
    w.u32(fill)
    w.u32(colour1)
    w.u32(colour2)
    w.u32(shape_flags)
    w.u32(image)

def _write_movements(w, obj, notes):
    """The movements defined on one object."""
    movements = obj.get("movements") or []
    if not movements:

        w.u32(1)
        w.s("Movement #1")
        w.s("")
        w.u32(0)
        w.blob(DEFAULT_STATIC_MOVEMENT)
        return
    w.u32(len(movements))
    for i, m in enumerate(movements):
        if m.get("params") is None:
            raise Refuse("movement %d has no readable parameter block" % i)

        w.s("Movement #%d" % (i + 1))
        if m.get("kind") == "extension":
            module = m.get("module")
            raw = m.get("codeRaw")
            if not module or not raw or len(raw) != 4:
                raise Refuse("movement %d is an extension movement with no "
                             "readable .mvx name or type code" % i)
            w.s(module)
            w.u32(struct.unpack("<I", raw)[0])

            if len(m["params"]) < MOVEMENT_HEAD:
                raise Refuse("movement %d (%s) has a %d-byte parameter block, "
                             "shorter than the shared %d-byte head"
                             % (i + 1, module, len(m["params"]), MOVEMENT_HEAD))
            w.blob(m["params"][MOVEMENT_HEAD:])
            notes.append("object %r: movement %d is the extension movement "
                         "%s; the editor needs that module installed"
                         % (obj.get("name"), i + 1, module))
            continue
        w.s("")
        w.u32(m["type"])
        w.blob(m["params"])

def _write_object_head(w, obj, t):
    props = obj.get("properties") or b""
    if len(props) < 0x14:
        raise Refuse("object %r: 0x4446 is %d bytes, too short to carry its "
                     "objectFlags" % (obj.get("name"), len(props)))
    (object_flags,) = struct.unpack_from("<I", props, 0x10)
    w.u32(object_flags)
    if len(props) < 0x36:
        raise Refuse("object %r: 0x4446 is %d bytes, too short to carry its "
                     "newObjectFlags and backgroundColor"
                     % (obj.get("name"), len(props)))
    (new_flags,) = struct.unpack_from("<H", props, 0x2A)
    if t != 2:
        new_flags &= ~NEW_OBJECT_FLAGS_COMPILED_BIT
    w.u32(new_flags)
    (background,) = struct.unpack_from("<I", props, 0x32)
    w.u32(background)
    quals = obj.get("qualifiers") or []
    for i in range(9):
        w.i16(quals[i] if i < len(quals) else -1)

def _write_extension_body(w, obj, notes):
    priv = obj.get("private") or {}
    if priv.get("data") is None:
        raise Refuse("extension %r: no readable private block" % obj.get("name"))
    ext = obj.get("extension") or {}
    if not ext.get("module"):
        raise Refuse("extension %r: its 0x2234 record is missing" % obj.get("name"))
    module = ext["module"]
    display = EXT_DISPLAY_NAMES.get(module.lower())
    if display is None:
        display = Path(module).stem
        notes.append("extension %s: display name unknown, substituted %r"
                     % (module, display))
    _write_object_head(w, obj, obj["type"])

    _write_value_list(w, [(0, v) for v in (obj.get("values") or [])])
    _write_value_list(w, [(2, s) for s in (obj.get("strings") or [])])
    _write_movements(w, obj, notes)
    w.u32(0)
    _write_fades(w, obj, "extension %r" % (obj.get("name"),), notes)
    w.u8(0)
    w.i32(-1)
    w.s(display)
    w.s(module)
    w.u32(ext["constant"])
    w.s(ext.get("subtype") or "")

    data = priv["data"]
    if len(data) >= 16 and any(data[12:16]):
        data = data[:12] + bytes(4) + data[16:]
        notes.append("extension item %r (%s): private block (%d bytes) "
                     "carried from the compiled EXE, with the 4 bytes at +12 "
                     "zeroed as the editor writes them (the compile bakes a "
                     "pointer there)"
                     % (obj.get("name"), module, len(data)))
    else:
        notes.append("extension item %r (%s): private block (%d bytes) "
                     "carried verbatim from the compiled EXE"
                     % (obj.get("name"), module, len(data)))
    w.blob(data)

def _evob_typename(obj):
    t = obj["type"]
    if t >= 32:
        code = obj.get("code")
        if not code or len(code) != 4:
            raise Refuse("extension %r: no 4-char type code for its EvOb "
                         "entry" % obj.get("name"))

        return code.split(b"\x00", 1)[0].decode("cp1252")
    return EVOB_TYPE_NAMES.get(t, "")

QUALIFIER_PARAM_SITES = {
    1: (0x02,),
    9: (0x00,),
    16: (0x00,),
    18: (0x00, 0x18),
}

EXPRESSION_PARAM_TYPES = frozenset({15, 22, 23, 27, 45, 46})

def _expression_tokens(body):
    n = len(body)
    if n < 6 or body[n - 4:] != b"\0\0\0\0":
        return None
    pos, end, out = 2, n - 4, []
    while pos < end:
        if pos + 6 > end:
            return None
        otype, code, size = struct.unpack_from("<hHH", body, pos)
        if size < 6 or pos + size > end:
            return None
        out.append((pos, otype, code, size))
        pos += size
    return out if pos == end else None

def _frame_qualifiers(used, objects, sections, index, notes):
    itype, tname, order = {}, {}, []
    carriers = {}
    for oi in used:
        obj = objects[oi]
        for q in (obj.get("qualifiers") or []):
            carriers.setdefault(q, set()).add(obj["type"])
            if q not in itype:
                itype[q] = obj["type"]
                tname[q] = _evob_typename(obj)
                order.append(q)

    if sections is not None:
        for section in sections:
            for rec in section:
                for _kind, r, _size in _aces(rec):
                    (objtype,) = struct.unpack_from("<h", rec, r + 2)
                    if objtype < 0:
                        continue
                    (oi,) = struct.unpack_from("<H", rec, r + 6)
                    if not oi & 0x8000:
                        continue
                    q = oi & 0x7FFF
                    if q not in itype:
                        itype[q] = objtype

                        tname[q] = EVOB_TYPE_NAMES.get(objtype, "")
                        order.append(q)
                        notes.append(
                            "frame %d: an event references qualifier %d, "
                            "which no item in this frame carries; an EvOb "
                            "entry was emitted for it so the reference binds"
                            % (index, q))
    for q in order:
        if q > QUALIFIER_ID_MAX:
            raise Refuse("frame %d: qualifier id %d is outside the proven "
                         "0..%d id space" % (index, q, QUALIFIER_ID_MAX))
    for q in sorted(carriers):
        if len(carriers[q]) > 1:
            notes.append(
                "frame %d: qualifier %d is carried by items of %d different "
                "object types (%s); the .mfa gives each type its own EvOb "
                "entry and this writer emits one, typed %d"
                % (index, q, len(carriers[q]),
                   ", ".join(str(t) for t in sorted(carriers[q])), itype[q]))
    return [(q, itype[q], tname[q]) for q in order]

def _write_events(w, used, objects, item_handle, sections, index, notes, section_labels=True):
    """A frame's event sheet, with the merged sections labelled and every object
    reference remapped to the project's own numbering.
    """
    w.u16(1027)
    w.u16(0)

    evobs = [oi for oi in used if objects[oi]["type"] not in (0, 1)]
    quals = _frame_qualifiers(used, objects, sections, index, notes)

    qbase = (max(evobs) + 1) if evobs else 0
    qhandle = {qid: qbase + i for i, (qid, _t, _n) in enumerate(quals)}
    residue = collections.Counter()
    if sections is not None:
        inlined = sum(len(s) for s in sections[1:])
        if len(sections) > 1:
            notes.append(
                "frame %d: %d event sections -- the frame's own %d records "
                "plus %d inlined from %d global-events/behaviour sections "
                "(the EXE does not label which; the split and any behaviour "
                "owners are a compile-time loss)"
                % (index, len(sections), len(sections[0]), inlined,
                   len(sections) - 1))
        handles = set(evobs)
        normalized = [
            [bytearray(_normalize_record(r, handles, qhandle,
                                         "frame %d" % index, residue))
             for r in section]
            for section in sections
        ]

        comments = []
        if section_labels and len(sections) > 1:
            try:
                records, comments = comment_rows.label_sections(normalized)
            except ValueError as exc:

                records = [r for section in normalized for r in section]
                notes.append(
                    "frame %d: the inlined sections were NOT labelled -- %s"
                    % (index, exc))
            else:
                notes.append(
                    "frame %d: %d comment row(s) added to mark where each "
                    "inlined section begins; they are ours, not the "
                    "author's, and are rendered on yellow to say so"
                    % (index, len(comments)))
        else:
            records = [r for section in normalized for r in section]

        _renumber_inlined_groups(records, index, notes)
        payload = b"".join(bytes(r) for r in records)
        if residue:
            notes.append(
                "frame %d: %d qualifier-shaped value(s) sit in parameter "
                "slots KlikBack does not decode (%s) and were left "
                "verbatim rather than remapped -- the expression token chain "
                "is unread, and rewriting an undecoded word to fix a "
                "reference would corrupt real data"
                % (index, sum(residue.values()),
                   ", ".join("type %d +0x%02X x%d" % (t, o, n)
                             for (t, o), n in residue.most_common(4))))
        w.raw(b"Evts")
        w.blob(payload)
        if comments:
            w.raw(b"Rems")
            w.raw(comment_rows.rems_block(comments))
    if evobs or quals:
        w.raw(b"EvOb")
        w.u32(len(evobs) + len(quals))
        for oi in evobs:
            obj = objects[oi]
            w.u32(oi)
            w.u16(1)
            w.u16(obj["type"])
            w.s(obj.get("name") or "")
            w.s(_evob_typename(obj))
            w.u16(0)
            w.u32(item_handle[oi])
            w.u32(0xFFFFFFFF)
        for qid, qtype, qtname in quals:
            w.u32(qhandle[qid])
            w.u16(3)
            w.u16(qtype)

            w.s("Group.%d" % qid)
            w.s(qtname)

            w.u16(0)
            w.u16(qid)
        if quals:
            notes.append(
                "frame %d: %d qualifier(s) %s -- EvOb entries emitted so the "
                "events' qualifier references bind; their display names are "
                "substituted as Group.<id> (the editor's own name table is "
                "not carried in this tool)"
                % (index, len(quals), [q for q, _t, _n in quals]))
    w.raw(b"EvEd")
    if sections is None:
        w.i16(0)
    else:

        cols = ([(objects[oi]["type"], oi) for oi in evobs]
                + [(qtype, qhandle[qid]) for qid, qtype, _n in quals])
        w.i16(len(EVED_SYSTEM) + len(cols))
        for t in EVED_SYSTEM:
            w.u16(t)
        for t, _h in cols:
            w.u16(t)
        for _ in EVED_SYSTEM:
            w.u16(0)
        for _t, h in cols:
            w.u16(h)
        for _ in range(len(EVED_SYSTEM) + len(cols)):
            w.u16(0)
    w.raw(b"EvTs")
    w.u16(1)
    w.raw(EVTS if sections is None else EVTS_EVENTS)
    w.raw(b"EvLs")
    w.u16(1)
    w.raw(EVLS)
    w.raw(b"EvCs")
    w.raw(EVCS if sections is None else EVCS_EVENTS)
    w.raw(b"!DNE")

def _write_frame_chunks(w, rec, fwidth, fheight, layer_fx=None,
                        frame_fx=None):
    virtual = rec.get(0x3342)
    w.u8(0x21)
    w.blob(virtual if virtual is not None and len(virtual) == 16
           else struct.pack("<4I", 0, 0, fwidth, fheight))

    seed = rec.get(0x3344)
    w.u8(0x23)
    if seed is not None and len(seed) == 2:
        w.blob(struct.pack("<I", struct.unpack("<H", seed)[0]))
    else:
        w.blob(RANDOMIZE_SEED)
    if layer_fx is not None:

        w.u8(0x25)
        w.blob(layer_fx)
    w.u8(0x26)
    w.blob(struct.pack("<2I", 0, 500))
    timer = rec.get(0x3347)
    w.u8(0x27)
    w.blob(timer if timer is not None and len(timer) == 4
           else struct.pack("<I", 50))

    if frame_fx is not None:
        w.u8(0x28)
        w.blob(frame_fx)
    w.u8(0x29)
    w.blob(struct.pack("<I", 1))
    w.u8(0)

OUTPUT_SUFFIX = ".decompiled"

def default_output(exe_path, suffix=OUTPUT_SUFFIX):
    """Where a recovered project goes: beside the game, under its own name.

    Never the game's own stem alone — a project file already sitting there is very
    likely the author's original, and the one thing a recovery must not do is
    overwrite the evidence it was checked against.
    """
    exe = Path(exe_path)
    if not suffix:
        raise Refuse("an empty --suffix would write %s.mfa, which can "
                     "overwrite the author's own project" % exe.stem)
    return exe.with_name(exe.stem + suffix + ".mfa")
