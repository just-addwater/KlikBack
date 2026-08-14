# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""Where KlikBack's bundled resources live, and friendly failure when lost.

The engine's icon generators resolve their replacement artwork relative to
their own package (`core/artwork/`), so a source checkout and a frozen
build both work with no configuration. This module exists so the rest of
KlikBack has one place to ask, and one place that turns a missing folder
into an actionable message instead of a traceback.

The artwork folder is also the app's one advertised customisation surface:
the packaged app puts a copy beside the exe and the README invites people
to drop replacement PNGs into it. That makes it user input, with a contract
the user cannot see -- so everything the engine might read is checked here,
once, before a run starts. Reaching a wrong-sized PNG eight minutes into a
game is a raw ValueError naming a path inside `_internal/` that nobody
edited, which reads as a KlikBack bug and is not one.
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

from klikback.core.common import icon_generate as mmf_icons
from klikback.core.tgf import icon_generate as tgf_icons

ARTWORK_DIR = Path(__file__).resolve().parent / "core" / "artwork"

#: The one file the engine refuses to run without — every imageless object
#: family falls back to it.
REQUIRED_ARTWORK = ("other.png",)

#: The editor's object icons are a fixed size; the MMF families reject any
#: other and name the file, the 1996 family scales into a slightly smaller
#: box. 32x32 is the size that works for both.
ICON_SIDE = 32

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

#: Colour types both engine readers accept: RGB, 256-colour palette, RGBA.
#: The MMF reader also takes greyscale and the 1996 reader does not, so a
#: greyscale drawing would decompile one family and stop the other -- the
#: same split this check exists to catch, one step subtler.
_COLOUR_TYPES = (2, 3, 6)


def _artwork_names() -> tuple[str, ...]:
    """Every filename either icon family will pick up if it is there.

    Read out of the engines' own tables rather than copied, so an object
    type added on the engine side is checked here for free. A hand-kept
    copy would silently stop covering the new name."""
    names = set(REQUIRED_ARTWORK)
    for module in (mmf_icons, tgf_icons):
        names.update(module.ARTWORK_BY_TYPE.values())
        names.add(module.EXTENSION_ARTWORK)
    return tuple(sorted(names))


ARTWORK_NAMES = _artwork_names()

CONTRACT = (
    "Every drawing in that folder is a 32 x 32 PNG, 8 bits per channel, "
    "RGB / RGBA / 256-colour palette, not interlaced. Transparency is "
    "either an alpha channel or bright green. The artwork section of "
    "README.txt has the rest."
)


class ResourceProblem(RuntimeError):
    """A file KlikBack itself needs is missing or unusable.

    Always about KlikBack's own folder, never about the game being
    decompiled — which is why it is reported before any work starts, as
    something to fix rather than something that went wrong."""


class MissingResource(ResourceProblem):
    """A bundled file is gone — almost always a mangled unzip or a deleted
    folder, never a property of the game being decompiled."""


class UnusableArtwork(ResourceProblem):
    """A drop-in artwork PNG is there but does not meet the contract, so
    the object family that would use it cannot be drawn."""


def visible_artwork_dir() -> Path:
    """The artwork folder a person edits.

    In the packaged app that is the visible one beside the exe: a startup
    hook copies it over the `_internal/` twin the engine actually reads, so
    the internal copy is where a fault is *found* and the visible one is
    where it must be *fixed*. Naming the internal path is what made this
    class of problem look like a KlikBack bug. Running from source there is
    only one folder and it is the one below."""
    if getattr(sys, "frozen", False):
        beside = Path(sys.executable).resolve().parent / "artwork"
        if beside.is_dir():
            return beside
    return ARTWORK_DIR


def _blame(name: str) -> tuple[Path, str | None]:
    """Which copy of one artwork file to put in front of a person, and a
    note when the two copies have come apart.

    The startup copy is one-way. Deleting a bad drawing from the visible
    folder therefore does not undo it — the copy made at the last start is
    still inside `_internal/` and is still the one being read — so that
    state gets said out loud instead of leaving someone fixing a file that
    is no longer the problem."""
    visible = visible_artwork_dir()
    if visible == ARTWORK_DIR or (visible / name).is_file():
        return visible / name, None
    return ARTWORK_DIR / name, (
        f"There is no {name} in {visible} any more, but an earlier start "
        f"copied one into the folder above and that is the copy KlikBack "
        f"reads. Delete it, or put a good {name} back in the visible "
        f"folder and start again."
    )


def _problem_text(name: str, fault: str, fix: str) -> str:
    """One artwork complaint, in the shape a person can act on: what is
    wrong, which file, what to do, and what the contract is."""
    path, note = _blame(name)
    lines = [fault, "", f"  file: {path}", f"  fix:  {fix}", ""]
    if note:
        lines += [note, ""]
    lines.append(CONTRACT)
    lines.append(
        "Nothing was decompiled and nothing was written -- fix the file "
        "and run it again."
    )
    return "\n".join(lines)


def _png_header(path: Path) -> tuple[int, int, int, int, int] | None:
    """(width, height, depth, colour type, interlace) from the IHDR chunk,
    or None when this is not a PNG at all.

    Read from the header alone, so the size of a drawing somebody saved at
    2000x2000 by mistake costs nothing to reject: the engine's own decoders
    are pure Python and would walk every pixel first."""
    with path.open("rb") as handle:
        head = handle.read(29)
    if len(head) < 29 or head[:8] != _PNG_SIGNATURE or head[12:16] != b"IHDR":
        return None
    width, height, depth, colour, _method, _filter, interlace = (
        struct.unpack_from(">IIBBBBB", head, 16)
    )
    return width, height, depth, colour, interlace


def check_artwork_file(name: str) -> None:
    """Hold one present artwork drawing to the contract, or raise
    `UnusableArtwork` naming what is wrong with it."""
    path = ARTWORK_DIR / name
    header = _png_header(path)
    if header is None:
        raise UnusableArtwork(_problem_text(
            name,
            f"{name} in KlikBack's artwork folder is not a PNG file.",
            "save it as a PNG, or delete it -- the objects that would use "
            "it fall back to other.png.",
        ))
    width, height, depth, colour, interlace = header
    if (width, height) != (ICON_SIDE, ICON_SIDE):
        raise UnusableArtwork(_problem_text(
            name,
            f"{name} in KlikBack's artwork folder is {width} x {height}, "
            f"and an object icon must be {ICON_SIDE} x {ICON_SIDE}.",
            f"save it at {ICON_SIDE} x {ICON_SIDE} pixels, or delete it -- "
            "the objects that would use it fall back to other.png.",
        ))
    if depth != 8 or interlace or colour not in _COLOUR_TYPES:
        raise UnusableArtwork(_problem_text(
            name,
            f"{name} in KlikBack's artwork folder is a kind of PNG "
            f"KlikBack cannot read (bit depth {depth}, colour type "
            f"{colour}{', interlaced' if interlace else ''}).",
            "re-save it as an 8-bit RGB or RGBA PNG without interlacing, "
            "or delete it -- the objects that would use it fall back to "
            "other.png.",
        ))
    try:
        mmf_icons.read_png_rgba(path)
    except Exception:
        # Deliberately not echoed: the reader's own message quotes the
        # internal path, which is the one thing this message must not send
        # somebody off to edit.
        raise UnusableArtwork(_problem_text(
            name,
            f"{name} in KlikBack's artwork folder could not be read -- the "
            f"file looks damaged or was not written completely.",
            "save it again, or delete it -- the objects that would use it "
            "fall back to other.png.",
        )) from None


def verify_artwork() -> Path:
    """The artwork directory, checked. Raise a `ResourceProblem` with a
    message a person can act on when it is unusable.

    Every name either icon family knows is checked, not just the required
    one: seven of the eight are drop-in slots that ship empty, so nothing
    exercises them until somebody fills one, and filling one with a file
    that does not fit the contract used to surface as a crash partway
    through a decompile."""
    for name in REQUIRED_ARTWORK:
        if not (ARTWORK_DIR / name).is_file():
            # Named against the visible folder, which is where a person can
            # put it back; `_blame` is for a file that exists in one copy
            # and not the other, which a missing required file never is.
            raise MissingResource(
                f"KlikBack's artwork folder is missing {name!r} "
                f"(looked in {visible_artwork_dir()}). Restore the folder "
                f"or re-extract KlikBack, then try again."
            )
    for name in ARTWORK_NAMES:
        if (ARTWORK_DIR / name).is_file():
            check_artwork_file(name)
    return ARTWORK_DIR
