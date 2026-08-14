# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""KlikBack's one programmatic surface: look at a file, then decompile it.

Two operations, used by the CLI and the GUI alike:

- `inspect(path)` -- fast, content-only identification. The extension is
  never trusted: every verdict comes from the file's own bytes (PE version
  stamps, overlay signatures, container signatures, the 1996 checksum
  marker), and companion files are located by the same content-verified
  rules the engine itself uses.
- `decompile(path, options)` -- run the right pipeline for what the file
  actually is, and report what happened in the engine's own words.

A refusal is an expected outcome, not an error: it is the engine declining
to write something it cannot write correctly, and the `Result` says which
feature stopped it. `loss:` lines matter more than a clean exit -- they are
content the writer knew it dropped.
"""

from __future__ import annotations

import base64
import contextlib
import io
import struct
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path

from klikback.core.common.pe_icon_probe import pe_resources
from klikback.core.mmf1 import decompile as mmf1_driver
from klikback.core.mmf1.build_version import build_stamp
from klikback.core.mmf15 import decompile as mmf15_driver
from klikback.core.tgf import bank_audit
from klikback.core.tgf import extract_extensions as tgf_extensions
from klikback.core.tgf import format as tgf_format
from klikback.core.tgf import identify as tgf_identify
from klikback.core.tgf import unprotect as tgf_unprotect

#: Suffixes worth even looking at when a folder is walked. Content decides
#: after that; a renamed file named explicitly is still inspected.
CANDIDATE_SUFFIXES = {".exe", ".gam", ".cca", ".ccn"}

KIND_LABELS = {
    "mmf1": "Multimedia Fusion 1.0 standalone",
    "mmf15": "Multimedia Fusion 1.5 standalone",
    "mmf1-ccn": "Multimedia Fusion 1.0 compiled application (.ccn)",
    "mmf15-ccn": "Multimedia Fusion 1.5 compiled application (.ccn)",
    "mmf-unknown": "Multimedia Fusion standalone of an unrecognised build",
    "fusion2": "Multimedia Fusion 2 or newer -- not supported",
    "tgf-exe": "1996-era standalone (TGF / Click & Create / MMF Express)",
    "tgf-data": "1996-era game data (TGF / Click & Create / MMF Express)",
    "tgf-damaged": "1996-era game data, an incomplete copy",
    "mmf-editable": "editable Multimedia Fusion project",
    "not-clickteam": "not a Clickteam game",
    "unreadable": "unreadable file",
}

#: The runtime package header every Multimedia Fusion generation writes:
#:
#:     "PAME" | "PAMU"   u8 product   u8 major   [12 more bytes]
#:     u16 0x2223                                the first chunk's id
#:
#: `PAMU` is the Unicode runtime, which arrived with Fusion 2 -- no MMF 1.x
#: build writes one. The product byte says which generation packed the file:
#: 0 is the MMF 1.0/1.2 line, 1 is MMF 1.5, and 2 is the Fusion 2 runtime
#: that MMF 2, MMF 2.5 and their successors all share.
#:
#: The major byte matters as much as the product byte: the 1996-era line
#: signs `PAME` too, at major 2, and its product byte is a large number that
#: means something else entirely. Reading the product without the major
#: would file those games as "too new", which is the opposite of true.
PACKAGE_SIGNATURES = (b"PAME", b"PAMU")
PACKAGE_FIRST_CHUNK = 0x2223
MMF_PACKAGE_MAJOR = 3
FUSION2_PRODUCT = 2


@dataclass
class Inspection:
    path: Path
    kind: str
    product: str
    build: str | None = None
    protected: bool | None = None
    name: str | None = None
    size: int = 0
    companions: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    #: The application's own icon as a `data:` URI, when the file is a PE
    #: executable carrying icon resources. Cosmetic and best-effort.
    icon: str | None = None

    @property
    def decompilable(self) -> bool:
        # An incomplete copy counts: it is a game this reads, and what it
        # needs is a decision about the missing assets rather than a
        # different program. Saying no here would hide the option that
        # opens it and drop it silently out of a folder walk.
        return self.kind in (
            "mmf1", "mmf15", "mmf1-ccn", "mmf15-ccn", "tgf-exe", "tgf-data",
            "tgf-damaged",
        )

    def as_dict(self) -> dict:
        return {
            "path": str(self.path),
            "kind": self.kind,
            "product": self.product,
            "build": self.build,
            "protected": self.protected,
            "name": self.name,
            "size": self.size,
            "companions": self.companions,
            "notes": self.notes,
            "decompilable": self.decompilable,
            "icon": self.icon,
        }


@dataclass
class Options:
    """Every knob the GUI will expose, with the shipping defaults.

    `recover_comments` stays off by default everywhere: the recovered
    POSITION is real but the text is substituted, and invented content is
    opt-in."""

    out_dir: Path | None = None  # None: beside the input
    force: bool = False
    extract_extensions: bool = True
    recover_comments: bool = False
    application_icons: bool = True   # MMF 1.5
    ownerless_recovery: bool = True  # MMF 1.5
    subapplications: bool = True     # MMF 1.5
    extension_dirs: list[Path] = field(default_factory=list)
    substitute_artwork: bool = True  # 1996
    repair_bank: bool = False        # 1996
    #: 1996: which levels have their object-placement pointers reordered.
    #: None is off, "all" is every level, otherwise the driver's own
    #: spelling -- "51", "3,7", "10-14". Off by default: the placement
    #: block is otherwise copied verbatim.
    repack_placement: str | None = None
    #: 1996: open a copy that is short of bytes by dropping the assets whose
    #: data is not in the file. Off by default -- what is dropped is
    #: content, and a decompiler that quietly discards a game's sounds is
    #: worse than one that stops and says so.
    drop_missing_assets: bool = False
    #: Give every game its own subfolder (named after the game) under the
    #: output root, so a batch of games never mixes its files.
    per_game_folders: bool = False
    suffix: str = ".decompiled"


@dataclass
class Result:
    path: Path
    kind: str
    outcome: str  # built | skipped | refused | invalid | failed | nothing-to-do | error
    target: Path | None
    log: str
    advice: str | None = None

    @property
    def ok(self) -> bool:
        return self.outcome in ("built", "skipped", "nothing-to-do")

    def as_dict(self) -> dict:
        return {
            "path": str(self.path),
            "kind": self.kind,
            "outcome": self.outcome,
            "target": str(self.target) if self.target else None,
            "log": self.log,
            "advice": self.advice,
        }


ADVICE = {
    "refused": (
        "The engine declined rather than write a wrong project -- the log "
        "names the feature that stopped it. This game may need a newer "
        "KlikBack, not different settings."
    ),
    "invalid": (
        "The reconstruction failed its own validation; the .failed.cca "
        "candidate was kept beside the output for diagnosis."
    ),
    "failed": (
        "Something unexpected went wrong. The log has the details; if the "
        "file plays fine as a game, this is worth reporting."
    ),
    "not-clickteam": (
        "The file has none of the signatures a Clickteam-era game carries "
        "(no MMF overlay, no 1996 runtime marker, no known container). "
        "If it arrived in an installer, install it first and point "
        "KlikBack at the installed game."
    ),
    "mmf-editable": (
        "This is already an editable project -- open it in the matching "
        "editor. There is nothing to decompile."
    ),
    "fusion2": (
        "This game was built with Multimedia Fusion 2 or a later Clickteam "
        "product. KlikBack reads the generation before it -- Multimedia "
        "Fusion 1.0 and 1.5, and the 1996-era Games Factory / Click & "
        "Create / MMF Express line. A Fusion 2 package is a different "
        "format, so no setting here will open it."
    ),
    "comment-recovery": (
        "This run had comment recovery on -- rule that out first, before "
        "reporting anything. Turn 'Recover comment positions' off (drop "
        "--recover-comments on the command line) and run it again: if it "
        "builds, that was the cause and the game is fine. It is off by "
        "default, it is the only option that writes text the author never "
        "wrote, and nothing else about the decompile depends on it. It "
        "cannot number a program where the compiler left an event group "
        "open, because the closing row is then one KlikBack put back "
        "rather than one the author wrote."
    ),
    "tgf-damaged": (
        "This copy of the game is incomplete -- it stops partway through "
        "the last of its sounds or pictures, which is what an interrupted "
        "download leaves behind. Everything before that point is intact, "
        "so KlikBack can still rebuild the project by dropping the assets "
        "whose bytes are not in the file: turn on 'open an incomplete copy' "
        "(--drop-missing-assets on the command line). Nothing is invented "
        "and nothing else moves -- what is dropped was already gone. A "
        "complete copy of the game, if you can find one, loses nothing."
    ),
    "tgf-unprotected": (
        "This data file is not protected: its editor already opens it. "
        "KlikBack can still carve the extensions out of the standalone "
        "beside it."
    ),
}


def resolved_out_dir(path: Path, options: Options) -> Path:
    """Where this input's output goes: the chosen folder (or beside the
    input), plus a per-game subfolder when the option asks for one."""
    base = options.out_dir or path.parent
    return Path(base) / path.stem if options.per_game_folders else Path(base)


def _sentence(text: str) -> str:
    """A search's own reason, promoted to a sentence of its own.

    The companion searches return a lower-case clause meant to sit after a
    colon ("no .exe beside it, so no extensions to carve"). When there is
    no file to name, that clause IS the whole answer, so it starts the
    line -- and a line shown to a person starts with a capital."""
    return text[:1].upper() + text[1:]


def _pe_icon_data_uri(path: Path) -> str | None:
    """The application's own icon, wrapped as a one-entry `.ico` data URI.

    Composed from the PE icon resources — the same resources the 1.5
    pipeline recovers as application icons. The `RT_GROUP_ICON` directory
    picks the variant to show (largest square, then deepest colour, which
    lands on the 32x32 the taskbar showed). Best-effort by design: a
    missing icon is a cosmetic absence, never an inspection failure.
    """
    try:
        resources = pe_resources(path)
        icons = {
            entry.name_id: entry.data
            for entry in resources
            if entry.type_id == 3  # RT_ICON
        }
        if not icons:
            return None
        width = bits = 0
        ident = None
        for entry in resources:
            if entry.type_id != 14 or len(entry.data) < 20:  # RT_GROUP_ICON
                continue
            count = struct.unpack_from("<H", entry.data, 4)[0]
            variants = []
            for index in range(count):
                if 6 + (index + 1) * 14 > len(entry.data):
                    break
                (side, _height, _colors, _reserved, _planes, depth,
                 _size, name) = struct.unpack_from(
                    "<BBBBHHIH", entry.data, 6 + index * 14
                )
                if name in icons:
                    variants.append((side or 256, depth, name))
            if variants:
                variants.sort()
                width, bits, ident = variants[-1]
                break
        if ident is None:
            ident = max(icons, key=lambda name: len(icons[name]))
        payload = icons[ident]
        if not width and len(payload) >= 8:
            width = struct.unpack_from("<i", payload, 4)[0] or 32
        header = struct.pack("<HHH", 0, 1, 1)
        entry = struct.pack(
            "<BBBBHHII",
            width % 256, width % 256, 0, 0, 1, bits, len(payload), 22,
        )
        encoded = base64.b64encode(header + entry + payload).decode("ascii")
        return "data:image/x-icon;base64," + encoded
    except Exception:
        return None


def _truncation(path: Path) -> str | None:
    """The reader's own account of why this 1996 file is incomplete, or None
    when it is not (including when it is not readable at all -- that is a
    different answer and the caller already has one for it)."""
    try:
        tgf_format.read(path)
    except tgf_format.TruncatedFile as damage:
        return str(damage)
    except Exception:
        return None
    return None


def _damaged_1996_inspection(path: Path, size: int) -> Inspection | None:
    """An Inspection when this file is a 1996 game the reader refuses only
    because the copy is incomplete, else None.

    Reached from the branch that used to answer "not a Clickteam game" for
    anything carrying the signature it could not then walk. A file cut off
    mid-download is not a stranger and not a format from another
    generation: everything before the cut parses, which is why it can be
    described here as fully as a healthy one -- name, protection, level
    count -- with the damage as the note. Read a second time rather than
    threaded through the identify helper, because only the rare failing
    file pays for it."""
    try:
        tgf_format.read(path)
    except tgf_format.TruncatedFile as damage:
        try:
            game = tgf_format.read(path, clip_truncated=True)
        except Exception:
            return Inspection(
                path, "tgf-damaged", KIND_LABELS["tgf-damaged"], size=size,
                notes=[str(damage)],
            )
        exe, why = tgf_unprotect.find_executable(path)
        return Inspection(
            path, "tgf-damaged", KIND_LABELS["tgf-damaged"],
            build=str(game.version), protected=game.protected,
            name=game.name or None, size=size,
            companions=[
                f"Standalone {exe.name}, {why}; its extension modules are "
                f"carved from there" if exe else _sentence(why)
            ],
            notes=[str(damage)],
        )
    except Exception:
        return None
    return None


def _package_header(data: bytes) -> tuple[bytes, int, int, int] | None:
    """(signature, product, major, offset) of the runtime package, or None.

    Located by the chunk that follows it rather than by an offset guess.
    The four signature letters also occur inside the runtimes' own code, far
    enough into the executable that searching from a fixed floor does not
    clear them, and a stray hit reads a version out of whatever bytes happen
    to sit next to it. A candidate therefore only counts when the package's
    first chunk id is where the header says it will be -- which is a
    property of the format rather than of any one build, and it is what lets
    the same reader answer for an executable with the package appended and
    for a bare package file alike.

    This does not replace the decompilers' own overlay search: it is a
    front-door check that runs before dispatch, so that a file from a
    generation this cannot read is named rather than guessed at.
    """
    for signature in PACKAGE_SIGNATURES:
        at = data.find(signature)
        while at >= 0:
            if at + 18 <= len(data):
                chunk = struct.unpack_from("<H", data, at + 16)[0]
                if chunk == PACKAGE_FIRST_CHUNK:
                    return signature, data[at + 4], data[at + 5], at
            at = data.find(signature, at + 1)
    return None


def _fusion2_inspection(
    path: Path, data: bytes, size: int
) -> Inspection | None:
    """An Inspection when this file is Fusion 2 or newer, else None.

    Two independent signals, either one enough: the Unicode `PAMU`
    signature, which only exists from Fusion 2 onward, and a package product
    byte past the two generations this reads -- the latter only under the
    major byte those generations share, so the 1996-era line, which signs
    `PAME` at a lower major, is never mistaken for something newer. Both are
    taken from the package header itself rather than from the PE version
    resource, for the same reason the 1.0-vs-1.5 split is: the resource
    belongs to whoever built the executable and authors overwrite it freely.

    Answering early matters more here than it looks. Without this, one of
    these files reads as an unrecognised build, another as not a Clickteam
    game at all, and a third is identified as MMF 1.0 with confidence and
    then fails deep inside the 1.0 reader with a block-type error that
    invites a bug report. Three different wrong answers for one cause.

    The runtime build number rides along when the PE stamp has the shape
    this runtime generation writes, and is left out when it does not, so an
    author-stamped executable reports no build rather than a wrong one.
    """
    header = _package_header(data)
    if header is None:
        return None
    signature, product, major, _at = header
    newer = (
        signature == b"PAMU"
        or major > MMF_PACKAGE_MAJOR
        or (major == MMF_PACKAGE_MAJOR and product >= FUSION2_PRODUCT)
    )
    if not newer:
        return None
    stamp = build_stamp(path) if data[:2] == b"MZ" else None
    version = stamp.file_version if stamp is not None else (0, 0, 0, 0)
    build = str(version[2]) if version[0] == 3 else None
    return Inspection(
        path, "fusion2", KIND_LABELS["fusion2"], build=build, size=size,
        notes=[
            ADVICE["fusion2"],
            f"its runtime package is {signature.decode('ascii')} product "
            f"{product}, the Fusion 2 generation",
        ],
        icon=_pe_icon_data_uri(path) if data[:2] == b"MZ" else None,
    )


def _mmf_kind(path: Path, data: bytes) -> tuple[str, str | None]:
    """(kind, build) for a PAME-overlay executable.

    The FAMILY comes from the overlay's own container version word -- the
    same `0x03xx` / low-bit rule the data-file dispatch uses -- because the
    PE version resource belongs to whoever built the EXE and authors
    overwrite it freely. Dozens of released games carry the author's own
    number there, and at least one stamps a 1.0-era version over a 1.5
    package outright. Checked across more than a thousand overlay
    executables: word `0x0300`/`0x0302` is the 1.0/1.2 line, `0x0301` is
    1.5, nothing else appeared, and in the single case where the PE stamp
    and the overlay disagreed, the overlay was the one that matched what the
    file actually decompiles as.

    The BUILD NUMBER still comes from the PE stamp, but only when its shape
    matches the family: the 1.0 line stamps 2.0/2.1/2.2.0.N for builds
    87-98, 1.5 stamps 2.5.N.0 or 2.5.0.N. An author-stamped EXE reports no
    build rather than a wrong one.
    """
    at = 0 if data.startswith(b"PAME") else data.find(b"PAME", 0x40000)
    if not (0 <= at <= len(data) - 6):
        return "mmf-unknown", None
    word = struct.unpack_from("<H", data, at + 4)[0]
    if word >> 8 != 3:
        return "mmf-unknown", None
    stamp = build_stamp(path)
    version = stamp.file_version if stamp is not None else (0, 0, 0, 0)
    if word & 1:
        build = str(version[2] or version[3]) if version[:2] == (2, 5) else None
        return "mmf15", build
    build = (
        str(version[3])
        if version[:2] in ((2, 0), (2, 1), (2, 2)) else None
    )
    return "mmf1", build


def inspect(path: Path) -> Inspection:
    path = Path(path)
    try:
        data = path.read_bytes()
    except OSError as problem:
        return Inspection(
            path, "unreadable", KIND_LABELS["unreadable"],
            notes=[str(problem)],
        )
    size = len(data)

    # Asked before anything else, because a Fusion 2 file otherwise reaches
    # three different wrong answers depending on which signature its runtime
    # happens to carry -- and the worst of them is a confident one.
    newer = _fusion2_inspection(path, data, size)
    if newer is not None:
        return newer

    if data[:2] == b"MZ":
        if mmf1_driver.is_mmf_standalone(path):
            kind, build = _mmf_kind(path, data)
            return Inspection(
                path, kind, KIND_LABELS[kind], build=build, size=size,
                icon=_pe_icon_data_uri(path),
            )
        info = tgf_identify.describe_exe(path)
        if info.get("standalone"):
            companion, why = tgf_unprotect.find_data_file(path)
            # A whole sentence either way. The search's own reason is kept
            # verbatim -- it names the file it compared against, which is
            # what makes an ambiguous folder actionable -- but the framing
            # around it is written for a reader rather than a log.
            companions = [
                f"Game data {companion.name}, {why}" if companion
                else _sentence(why)
            ]
            # The damage belongs to the pair, not to the half that was
            # named: an executable whose only data file is an incomplete
            # copy is in exactly the state the .cca reports, and calling it
            # an ordinary standalone would hide the option that opens it.
            notes = [f"runtime marker at {info['marker']:#x}"]
            kind, label = "tgf-exe", KIND_LABELS["tgf-exe"]
            if companion is not None:
                damage = _truncation(companion)
                if damage is not None:
                    # The label is written for the half that was named: the
                    # executable is whole, its game data is not, and saying
                    # "an incomplete copy" flatly about the .exe would send
                    # somebody looking for a better download of the wrong
                    # file.
                    kind = "tgf-damaged"
                    label = ("1996-era standalone -- its game data is an "
                             "incomplete copy")
                    notes.append(damage)
            return Inspection(
                path, kind, label, size=size,
                companions=companions, notes=notes,
                icon=_pe_icon_data_uri(path),
            )
        return Inspection(
            path, "not-clickteam", KIND_LABELS["not-clickteam"], size=size,
            notes=["a Windows executable with no MMF overlay and no 1996 "
                   "runtime marker"],
        )

    if data[:4] in (b"GAPP", b"PAPP", b"GAME", b"PAME") and len(data) >= 6:
        version = struct.unpack_from("<H", data, 4)[0]
        if version >> 8 == 3:
            kind = "mmf15-ccn" if version & 1 else "mmf1-ccn"
            return Inspection(path, kind, KIND_LABELS[kind], size=size)
        info = tgf_identify.describe_data(path)
        if info is not None and "error" not in info:
            protected = bool(info.get("protected"))
            companions: list[str] = []
            exe, why = tgf_unprotect.find_executable(path)
            # ASCII only: these lines are printed by the CLI as well as
            # shown in the window, and a console encoding that cannot
            # spell an em dash turns it into a replacement character.
            companions.append(
                f"Standalone {exe.name}, {why}; its extension modules are "
                f"carved from there" if exe else _sentence(why)
            )
            return Inspection(
                path, "tgf-data", KIND_LABELS["tgf-data"],
                build=str(info.get("version")), protected=protected,
                name=info.get("name") or None, size=size,
                companions=companions,
                notes=[f"{info.get('family')} {info.get('signature')}, "
                       f"{info.get('levels')} level(s), "
                       f"{info.get('colour')}"],
            )
        note = (info or {}).get("error", "container walk failed")
        damaged = _damaged_1996_inspection(path, size)
        if damaged is not None:
            return damaged
        return Inspection(
            path, "not-clickteam", KIND_LABELS["not-clickteam"], size=size,
            notes=[f"carries a 1996-style signature but is not readable "
                   f"as one: {note}"],
        )

    if data[:5] in (b"CnC2T", b"CnC2U"):
        which = "1.0" if data[:5] == b"CnC2T" else "1.5"
        return Inspection(
            path, "mmf-editable",
            f"{KIND_LABELS['mmf-editable']} (Multimedia Fusion {which})",
            size=size, notes=[ADVICE["mmf-editable"]],
        )

    return Inspection(
        path, "not-clickteam", KIND_LABELS["not-clickteam"], size=size,
    )


def _capture(runner) -> tuple[str, object]:
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        value = runner()
    return buffer.getvalue().rstrip(), value


def _decompile_mmf1(
    path: Path, options: Options,
    progress: Callable[..., None] | None = None,
) -> Result:
    out_dir = resolved_out_dir(path, options)
    args = mmf1_driver.driver_defaults(
        force=options.force,
        recover_comments=options.recover_comments,
        extensions=list(options.extension_dirs),
        # The pipeline's JSON reconstruction report is a research artifact;
        # KlikBack users get the session log instead.
        no_summary=True,
    )
    target = out_dir / f"{path.stem}{options.suffix}.cca"

    def run():
        if options.extract_extensions and path.suffix.lower() == ".exe":
            print(mmf1_driver.extract_cox(
                path, out_dir / f"{path.stem}_cox", options.force
            ))
        return mmf1_driver.build_cca(path, target, args, progress=progress)

    log, (outcome, report) = _capture(run)
    log = (log + "\n" + report).strip()
    kind = "mmf1" if path.suffix.lower() == ".exe" else "mmf1-ccn"
    return Result(path, kind, outcome, target if outcome == "built" else None,
                  log, ADVICE.get(outcome))


def _decompile_mmf15(
    path: Path, options: Options,
    progress: Callable[..., None] | None = None,
) -> Result:
    out_dir = resolved_out_dir(path, options)
    args = mmf15_driver.driver_defaults(
        force=options.force,
        recover_comments=options.recover_comments,
        extensions=list(options.extension_dirs),
        no_application_icons=not options.application_icons,
        no_recover_ownerless_behaviours=not options.ownerless_recovery,
        no_subapps=not options.subapplications,
    )
    target = out_dir / f"{path.stem}{options.suffix}.cca"

    def run():
        if options.extract_extensions and path.suffix.lower() == ".exe":
            print(mmf15_driver.extract_cox(
                path, out_dir / f"{path.stem}_cox", options.force
            ))
            # The drift report compares the game's embedded extensions
            # against an installed set. With no directory to compare
            # against, every module reads "not installed" and the report
            # is pure noise -- so it only runs when the user pointed at one.
            if args.extensions:
                print(mmf15_driver.module_drift(path, args.extensions))
        children = (
            [] if not options.subapplications
            else mmf15_driver.external_subapplications(path)
        )
        outcome, report = mmf15_driver.build_cca(
            path, target, args, None,
            subapplication_directory=out_dir if children else None,
            progress=progress,
        )
        print(report)
        for child_outcome in mmf15_driver.build_subapplications(
            path, children, out_dir, args, None
        ):
            print(f"  ({child_outcome})")
        return outcome

    log, outcome = _capture(run)
    kind = "mmf15" if path.suffix.lower() == ".exe" else "mmf15-ccn"
    return Result(path, kind, outcome, target if outcome == "built" else None,
                  log, ADVICE.get(outcome))


def level_spec_is_valid(spec: str) -> bool:
    """Whether a `--repack-placement` level list can be read at all.

    Checked where it is typed rather than where it is used, so a typo is a
    sentence about the option instead of an exception from inside the
    engine an hour later."""
    if spec == "all":
        return True
    parts = [part.strip() for part in spec.split(",")]
    if not any(parts):
        return False
    for part in parts:
        ends = part.split("-", 1) if "-" in part[1:] else [part]
        if not all(end.strip().lstrip("+-").isdigit() for end in ends if part):
            return False
    return True


def repack_levels(spec: str | None, level_count: int) -> set[int] | None:
    """The set of levels a `--repack-placement` value names, or None.

    The engine takes level indices and this is the only place that knows
    how many a game has, which is what "every level" needs. The spelling is
    the engine driver's own, so a level list means the same thing typed at
    either program."""
    if not spec:
        return None
    if spec == "all":
        return set(range(level_count))
    levels: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if "-" in part[1:]:
            low, high = part.split("-", 1)
            levels.update(range(int(low), int(high) + 1))
        elif part:
            levels.add(int(part))
    return levels


def _load_1996(source: Path, options: Options):
    """Read a 1996 game file, salvaging an incomplete copy when asked to.

    Two faults, both of them a copy short of bytes rather than a format
    problem: a bank table naming assets past the end of its own segment,
    and -- one level further out -- a final segment running past the end of
    the file. The first still parses and would be carried into the rebuilt
    project as a bank an editor cannot allocate; the second the reader
    refuses outright.

    Neither is repaired unless the caller asks. Both repairs drop content
    that is already absent, so they are the same kind of decision as any
    other loss the user opts into, and with the option off this is exactly
    the read it has always been."""
    if not options.drop_missing_assets:
        return tgf_format.read(source), []
    salvage: list[str] = []
    try:
        game = tgf_format.read(source)
    except tgf_format.TruncatedFile:
        data, salvage = bank_audit.repair_truncated(source.read_bytes())
        game = tgf_format.read(data, path=source)
    # A file with nothing to drop comes back untouched byte for byte, which
    # is the repair's own guarantee -- so this runs on every file the
    # option is on for, and only a file that needs it is re-read.
    data, dropped = bank_audit.repair(game)
    if dropped:
        salvage += dropped
        game = tgf_format.read(data, path=source)
    return game, salvage


def _decompile_tgf(
    path: Path, options: Options, inspection: Inspection,
    progress: Callable[..., None] | None = None,
) -> Result:
    def run():
        source, exe, notes = tgf_unprotect.resolve(path)
        for note in notes:
            print(f"  {note}")
        if source is None:
            return ("failed", None)
        try:
            game, salvage = _load_1996(source, options)
        except tgf_format.TruncatedFile as damage:
            # An expected outcome with an answer, not a crash: the copy is
            # incomplete and there is an option that opens it anyway.
            print(f"  {damage}")
            return ("refused", None)
        for note in salvage:
            print(f"  salvaged: {note}")
        out_dir = resolved_out_dir(source, options)
        carve_dir = out_dir

        if not game.protected:
            if salvage:
                # The salvage IS the recovery for an unprotected copy --
                # there is no protection to undo, so the repaired container
                # is the whole of what KlikBack has to give back.
                out = out_dir / f"{source.stem}{options.suffix}{source.suffix}"
                if out.exists() and not options.force:
                    return ("skipped",
                            f"{out.name} already exists (--force to replace)")
                out.parent.mkdir(parents=True, exist_ok=True)
                if progress is not None:
                    progress("write")
                out.write_bytes(game.raw)
                print(f"  wrote {out}")
                outcome = "built"
            else:
                print("  " + ADVICE["tgf-unprotected"])
                outcome, out = "nothing-to-do", None
        else:
            data, report = tgf_unprotect.unprotect(
                game,
                substitute=options.substitute_artwork,
                repair_bank=options.repair_bank,
                repack_placement=repack_levels(
                    options.repack_placement, game.level_count),
                progress=progress,
            )
            print(report.render())
            print(f"  {len(game.raw):,} bytes in, {len(data):,} bytes out")
            out = out_dir / f"{source.stem}{options.suffix}{source.suffix}"
            if out.exists() and not options.force:
                return ("skipped",
                        f"{out.name} already exists (--force to replace)")
            out.parent.mkdir(parents=True, exist_ok=True)
            if progress is not None:
                progress("write")
            out.write_bytes(data)
            print(f"  wrote {out}")
            outcome = "built"

        if options.extract_extensions:
            kind = "gox" if game.family == "tgf" else "cox"
            if exe is None:
                print("  extensions: no executable to carve")
            else:
                print("  " + tgf_extensions.extract_to(
                    exe, carve_dir / f"{source.stem}_{kind}", options.force
                ))
        return (outcome, out)

    log, value = _capture(run)
    outcome, target = value if isinstance(value, tuple) else ("failed", None)
    if isinstance(target, str):  # the skipped message
        log = (log + "\n" + target).strip()
        target = None
    advice = ADVICE.get(outcome)
    if outcome == "refused" and inspection.kind == "tgf-damaged":
        # The generic refusal advice says the game may need a newer
        # KlikBack. This one needs a decision, and the advice names it.
        advice = ADVICE["tgf-damaged"]
    return Result(path, inspection.kind, outcome, target, log, advice)


def _comment_recovery_advice(result: Result, options: Options) -> Result:
    """Point a failed run at the comment-recovery option when it was on.

    The condition is the option's own state, not the wording of the error.
    Two reasons. The pipelines catch their own exceptions and report a
    line, so by the time a Result exists there is no traceback left to
    read; and matching the engine's prose would stop recognising this the
    moment somebody improved the sentence, silently and in the direction of
    saying nothing.

    So the advice is written to be true of any failed run with the option
    on: it does not claim to know that comment recovery caused this one,
    it says to rule it out first -- which is right whatever the cause,
    since the option is off by default and nothing else depends on it."""
    if options.recover_comments and result.outcome in (
        "failed", "error", "invalid"
    ):
        return replace(result, advice=ADVICE["comment-recovery"])
    return result


def decompile(
    path: Path, options: Options | None = None,
    inspection: Inspection | None = None,
    progress: Callable[..., None] | None = None,
) -> Result:
    """Decompile one file with the pipeline its content calls for.

    `progress` is an optional pure observer for a progress display, called
    as `progress(stage)` at a stage boundary and `progress(stage, n, of)`
    inside a pipeline's frame/level loop. It never changes what is built:
    the engines consult it for nothing, so with or without one the output
    bytes and every failure point are identical. Note that the engine's own
    report is being captured while it runs, so a callback that prints must
    hold a reference to the real stream (the worker mode does)."""
    path = Path(path)
    options = options or Options()
    inspection = inspection or inspect(path)
    kind = inspection.kind
    try:
        if kind in ("mmf1", "mmf1-ccn"):
            return _comment_recovery_advice(
                _decompile_mmf1(path, options, progress), options)
        if kind in ("mmf15", "mmf15-ccn"):
            return _comment_recovery_advice(
                _decompile_mmf15(path, options, progress), options)
        if kind in ("tgf-exe", "tgf-data", "tgf-damaged"):
            return _comment_recovery_advice(
                _decompile_tgf(path, options, inspection, progress), options)
    except Exception as problem:  # a crash is an error card, never silence
        return _comment_recovery_advice(Result(
            path, kind, "error", None,
            f"{type(problem).__name__}: {problem}", ADVICE.get("failed"),
        ), options)
    advice = ADVICE.get(kind) or ADVICE.get("not-clickteam")
    return Result(path, kind, "nothing-to-do", None,
                  "\n".join(inspection.notes) or inspection.product, advice)


def collect_targets(paths: list[Path]) -> list[Path]:
    """Files worth inspecting from a mixed list of files and folders."""
    found: list[Path] = []
    for path in paths:
        path = Path(path)
        if path.is_dir():
            found.extend(
                candidate
                for candidate in sorted(path.rglob("*"))
                if candidate.suffix.lower() in CANDIDATE_SUFFIXES
                and candidate.is_file()
            )
        elif path.exists():
            found.append(path)
        else:
            found.append(path)  # let inspect() report it as unreadable
    return found
