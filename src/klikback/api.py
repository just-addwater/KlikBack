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
import re
import struct
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path

from klikback.core.common.pe_icon_probe import pe_resources
from klikback.core.mmf1 import decompile as mmf1_driver
from klikback.core.common.compression_probe import application_bytes
from klikback.core.mmf1.build_version import build_stamp, build_stamp_in
from klikback.core.mmf15 import decompile as mmf15_driver
from klikback.core.mmf2 import extensions as mmf2_extensions
from klikback.core.mmf2 import write_mfa as mmf2_writer
from klikback.core.mmf2.read_app import App as Mmf2App
from klikback.core.tgf import bank_audit
from klikback.core.tgf import extract_extensions as tgf_extensions
from klikback.core.tgf import format as tgf_format
from klikback.core.tgf import identify as tgf_identify
from klikback.core.tgf import unprotect as tgf_unprotect

#: Suffixes worth even looking at when a folder is walked. Content decides
#: after that; a renamed file named explicitly is still inspected.
#:
#: `.scr` was missing until 2026-08-22, which meant a folder walk never offered
#: a screensaver to anything even though `inspect()` identifies one correctly
#: the moment it is named. That is the discovery-step gap the research driver
#: had at the same time and for the same reason: every function downstream
#: takes a path and opens it, so nothing below this line can notice.
#:
#: `.mfa` joined on 2026-08-24. It is not a game and never will be -- it is
#: the Multimedia Fusion 2 editor's own project file, the thing KlikBack
#: WRITES -- but an editable project is an input KlikBack accepts and answers
#: ("this is already a project"), which is exactly what `.cca` gets. Leaving
#: it out meant the native format of the 2.0 family was the one editable
#: project a folder walk stayed silent about.
CANDIDATE_SUFFIXES = {".exe", ".gam", ".cca", ".ccn", ".scr", ".mfa"}

KIND_LABELS = {
    "mmf1": "Multimedia Fusion 1.0 standalone",
    "mmf15": "Multimedia Fusion 1.5 standalone",
    "mmf1-ccn": "Multimedia Fusion 1.0 compiled application (.ccn)",
    "mmf15-ccn": "Multimedia Fusion 1.5 compiled application (.ccn)",
    "mmf-unknown": "Multimedia Fusion standalone of an unrecognised build",
    "mmf2": "Multimedia Fusion 2.0 standalone",
    "mmf2-ccn": "Multimedia Fusion 2.0 compiled application (.ccn)",
    "fusion2": "Clickteam Fusion 2.5 or newer -- not supported",
    "tgf-exe": "TGF/CnC standalone (The Games Factory / Click & Create / MMF Express)",
    "tgf-data": "TGF/CnC game data (The Games Factory / Click & Create / MMF Express)",
    "tgf-damaged": "TGF/CnC game data, an incomplete copy",
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

#: The format builds Multimedia Fusion 2.0 wrote, as measured over every
#: 2.0 game this was developed against (all `PAME` product-2 files, 231 to
#: 257). The split between 2.0 and the generation after it is not a build
#: threshold at all: Fusion 2.5 writes the Unicode package (`PAMU`), and
#: every `PAMU` file seen is build 280 or later. A `PAME` file outside this
#: range is still read as 2.0 -- the reader accepts it and the writer says
#: so if something does not fit -- but the inspection names the build as
#: one KlikBack has not measured.
MMF2_BUILDS = (231, 257)

#: Which option family each kind belongs to, for the "options in force"
#: report. The batch rule (decided 2026-08-23): every option is global per
#: run, each file is dispatched by its kind, and an option its family does
#: not have is ignored for that file -- so a mixed batch is predictable, and
#: this table is what lets each file's report say which options applied to
#: it rather than which were ticked.
FAMILY_OF_KIND = {
    "mmf1": "mmf1", "mmf1-ccn": "mmf1",
    "mmf15": "mmf15", "mmf15-ccn": "mmf15",
    "tgf-exe": "tgf", "tgf-data": "tgf", "tgf-damaged": "tgf",
    "mmf2": "mmf2", "mmf2-ccn": "mmf2",
}

#: **What an exit code means** (settled with the user 2026-08-24, after the
#: 1.1.0 release test found the two surfaces disagreeing about the same
#: file). One table, obeyed by the decompile path and by `--identify`
#: alike, because a script that gets 0 from one and 2 from the other for a
#: path that is not there cannot trust either.
#:
#: **Exit 0 means: everything you named was understood, and nothing needs
#: your attention.** Everything else says which kind of attention.
#:
#:     0  all good -- built, skipped, already a project, nothing to do
#:     1  KlikBack itself went wrong, or its folder or flags need fixing
#:     2  something you named could not be read or recognised
#:     3  a game was read and could not be rebuilt (refused, invalid)
#:     4  a Clickteam product KlikBack does not support (Fusion 2.5+)
#:
#: 4 exists so a script can tell "no version of KlikBack will ever read
#: this, stop retrying" from "this one game hit a gap", which sharing 3
#: could not. Before this, a Fusion 2.5 file and a path that did not exist
#: both exited 0 from the decompile path -- both counted `nothing-to-do`.
EXIT_OK = 0
EXIT_ERROR = 1
EXIT_UNRECOGNISED = 2
EXIT_REFUSED = 3
EXIT_UNSUPPORTED = 4

#: Every `Result.outcome`, and the code it exits with.
#:
#: `nothing-to-do` now means only what it says: an editable project, or an
#: unprotected data file its own editor opens. Both genuinely need nothing.
#: The two verdicts that used to shelter under it have their own names --
#: `unsupported` for a product KlikBack cannot read, `unrecognised` for a
#: file it cannot identify or cannot open at all.
OUTCOME_EXIT = {
    "built": EXIT_OK,
    "skipped": EXIT_OK,
    "nothing-to-do": EXIT_OK,
    "error": EXIT_ERROR,
    "failed": EXIT_ERROR,
    "unrecognised": EXIT_UNRECOGNISED,
    "refused": EXIT_REFUSED,
    "invalid": EXIT_REFUSED,
    "unsupported": EXIT_UNSUPPORTED,
}

#: Which code a batch reports when its files disagree: the most serious
#: wins, and seriousness is NOT the numeric order. An unexpected error
#: outranks everything -- it is the one outcome that means KlikBack, rather
#: than the game, is at fault -- and a product that is simply out of scope
#: is the mildest non-zero thing that can happen.
EXIT_SEVERITY = [
    EXIT_OK, EXIT_UNSUPPORTED, EXIT_UNRECOGNISED, EXIT_REFUSED, EXIT_ERROR,
]

#: What `--identify` reports for a file it has just named correctly. It
#: refuses nothing and builds nothing, so its verdict is about the FILE:
#: can KlikBack work on this, and if not, why not. The kinds absent here
#: are the decompilable ones, which are `EXIT_OK` -- there is a pipeline
#: waiting for them.
KIND_OUTCOME = {
    "mmf-editable": "nothing-to-do",
    "fusion2": "unsupported",
    "not-clickteam": "unrecognised",
    "unreadable": "unrecognised",
    "mmf-unknown": "unrecognised",
}


def exit_code(outcome: str) -> int:
    """The exit code one file's outcome calls for."""
    return OUTCOME_EXIT.get(outcome, EXIT_ERROR)


def worst_exit(codes) -> int:
    """The code a run of several files reports: the most serious of them."""
    worst = EXIT_OK
    for code in codes:
        if EXIT_SEVERITY.index(code) > EXIT_SEVERITY.index(worst):
            worst = code
    return worst


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
    #: Why this file cannot be decompiled AS IT STANDS, when that is
    #: already known before any work starts, else None.
    #:
    #: Only for what the inspection itself establishes and no setting can
    #: get past -- today, a 1996 standalone with no usable game data
    #: beside it. An incomplete copy is deliberately NOT blocked: there is
    #: an option that opens one, so it is a decision rather than a wall.
    #:
    #: It exists so `--identify` and a real run cannot contradict each
    #: other about the same file. Identifying never claims a conversion
    #: will succeed -- a refusal the writer only meets halfway through is
    #: nobody's to predict -- but a fact the inspection has in its hand is
    #: a different thing, and reporting it as "fine" is how a file came to
    #: exit 0 from one surface and 3 from the other.
    blocked: str | None = None
    #: MMF 2.0 only: the extension modules the game asks for, one dict per
    #: module (see `_mmf2_extension_rows`). Gathered here, before any run,
    #: because this is the list the remove-extension control is built from:
    #: it offers only names the game itself uses, which is what makes the
    #: engine's unknown-name refusal unreachable from the window.
    extensions: list[dict] = field(default_factory=list)

    @property
    def decompilable(self) -> bool:
        # An incomplete copy counts: it is a game this reads, and what it
        # needs is a decision about the missing assets rather than a
        # different program. Saying no here would hide the option that
        # opens it and drop it silently out of a folder walk.
        return self.kind in (
            "mmf1", "mmf15", "mmf1-ccn", "mmf15-ccn", "tgf-exe", "tgf-data",
            "tgf-damaged", "mmf2", "mmf2-ccn",
        )

    @property
    def exit_code(self) -> int:
        """What identifying this file, on its own, is worth as an exit code.

        `--identify` builds nothing and refuses nothing, so its verdict is
        about the FILE rather than about any work: a kind with a pipeline
        waiting for it is fine, an editable project is fine, and everything
        else says why not. This is what makes the two surfaces agree -- the
        same missing path, the same Fusion 2.5 game, gets the same code
        whichever one is asked."""
        if self.blocked:
            return EXIT_REFUSED
        if self.decompilable:
            return EXIT_OK
        return exit_code(KIND_OUTCOME.get(self.kind, "unrecognised"))

    def as_dict(self) -> dict:
        return {
            "path": str(self.path),
            "kind": self.kind,
            "product": self.product,
            "exit_code": self.exit_code,
            "build": self.build,
            "protected": self.protected,
            "name": self.name,
            "size": self.size,
            "companions": self.companions,
            "notes": self.notes,
            "decompilable": self.decompilable,
            "blocked": self.blocked,
            "icon": self.icon,
            "extensions": self.extensions,
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
    recover_comments: bool = False   # MMF 1.0 / 1.5
    application_icons: bool = True   # MMF 1.5
    ownerless_recovery: bool = True  # MMF 1.5
    subapplications: bool = True     # MMF 1.5
    #: MMF 1.0 / 1.5: an installed editor's Extensions folder (.cox files),
    #: read for the display names a compiled game dropped.
    extension_dirs: list[Path] = field(default_factory=list)
    #: 1996 and MMF 2.0: a stand-in icon where the game has none of its
    #: own. For a 1996 game that is a blank icon / thumbnail; for a 2.0 game
    #: it is a drawing from the artwork folder, for an object type that has
    #: no picture (a String, a Counter, an extension object).
    substitute_artwork: bool = True
    repair_bank: bool = False        # 1996
    #: TGF/CnC: restore an active object's data-block head where the file
    #: as shipped breaks the invariants every authored active satisfies --
    #: MMF 1.5 refuses a whole game over one such head while the TGF/CnC
    #: editors open it. The head is rederived from the object's own
    #: structure, never substituted. Off by default: object data is
    #: otherwise copied verbatim, and a healthy file comes back byte for
    #: byte either way.
    repair_object_data: bool = False
    #: MMF 2.0: the user's own MMF 2 Extensions folder (the folder itself,
    #: not the install root). Read, never written: an extension object then
    #: gets its module's own editor icon, and the inspection can say which
    #: modules the editor here will be able to load. Off unless a folder is
    #: given -- it is never looked for under Program Files.
    mmf2_extension_dir: Path | None = None
    #: MMF 2.0: the yellow comment rows marking where the compiler merged
    #: the global events and behaviours into each frame. They are
    #: KlikBack's rows, not the author's, which is why they can be declined.
    section_labels: bool = True
    #: MMF 2.0: module filenames to remove from EVERY 2.0 file in the run --
    #: the command line's spelling. Every object of those modules, every
    #: event line and action naming them, and the declaration go; a name
    #: the game does not use is a refusal. A strip list names modules of
    #: one project, so in practice this is a single-game flag.
    strip_extensions: list[str] = field(default_factory=list)
    #: MMF 2.0: the same, chosen per file -- `{path: [module, ...]}`. This
    #: is the window's spelling: a batch of games shares nothing, so the
    #: choice lives on each game's own card.
    strip_for: dict[str, list[str]] = field(default_factory=dict)
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
    #: One of `OUTCOME_EXIT`'s keys: built | skipped | nothing-to-do |
    #: refused | invalid | unsupported | unrecognised | failed | error.
    outcome: str
    target: Path | None
    log: str
    advice: str | None = None
    #: The options that were in force for THIS file, as "name: value"
    #: lines -- only the ones its family has. In a mixed batch every option
    #: is global and each file takes the ones that apply to it, so this is
    #: how a file's own report says what actually shaped it.
    applied: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.outcome in ("built", "skipped", "nothing-to-do")

    @property
    def exit_code(self) -> int:
        return exit_code(self.outcome)

    def as_dict(self) -> dict:
        return {
            "path": str(self.path),
            "kind": self.kind,
            "outcome": self.outcome,
            "exit_code": self.exit_code,
            "target": str(self.target) if self.target else None,
            "log": self.log,
            "advice": self.advice,
            "applied": self.applied,
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
    "mmf-unknown": (
        "This is a Multimedia Fusion standalone, but its build is not one "
        "KlikBack recognises, so it has no pipeline to send it down. The "
        "file is not damaged as far as this went -- the overlay is there "
        "and was read; it is the build stamp that is unfamiliar. Worth "
        "reporting, with the game."
    ),
    "unreadable": (
        "KlikBack could not open that path at all -- the line above is what "
        "Windows said about it. Check the spelling, and check that the file "
        "is where you think it is. This is not a verdict about a game: "
        "nothing was read, so nothing could be identified."
    ),
    "tgf-no-data": (
        "A TGF/CnC standalone keeps its game in a separate .gam or .cca "
        "beside it, and none beside this one could be used -- the lines "
        "above name every file that was weighed and what was wrong with "
        "each. If a data file is damaged, that damage is what to re-"
        "download. If two games share a folder, give KlikBack the data "
        "file itself instead of the executable -- it decompiles either "
        "half. If the data file is somewhere else, put the two back "
        "together. Nothing was written."
    ),
    "mmf2-strip-unknown": (
        "Nothing was removed and nothing was written. This is a name "
        "KlikBack could not match, not a limit of the recovery: the list "
        "above is the modules this project actually uses, spelled the way "
        "the project spells them. Pick from that list -- the names are "
        "case-insensitive but the spelling and the .mfx are not optional -- "
        "or clear the removal entirely to get the faithful recovery."
    ),
    "not-clickteam": (
        "The file has none of the signatures a Clickteam-era game carries "
        "(no MMF overlay, no TGF/CnC runtime marker, no known container). "
        "If it arrived in an installer, install it first and point "
        "KlikBack at the installed game."
    ),
    "mmf-editable": (
        "This is already an editable project -- open it in the matching "
        "editor. There is nothing to decompile."
    ),
    "fusion2": (
        "This game was built with Clickteam Fusion 2.5 or a later product: "
        "its package is the Unicode runtime's, which arrived after "
        "Multimedia Fusion 2.0. KlikBack reads Multimedia Fusion 2.0 "
        "(builds 231 to 257), 1.0 and 1.5, and the TGF/CnC line (The Games "
        "Factory / Click & Create / MMF Express). The Fusion 2.5 package is a "
        "different layout, so no setting here will open it."
    ),
    "mmf2-build": (
        "Multimedia Fusion 2.0 was measured on builds 231 to 257; this file "
        "is read the same way, and the engine names anything that does not "
        "fit rather than guessing."
    ),
    "mmf2-stripped": (
        "Extension modules were REMOVED from this project at your request. "
        "Every object of those modules, every event line and action that "
        "used them, and the modules' declarations are gone from this "
        "output, and nothing can put them back from it -- the report lists "
        "what was removed. The original game file is untouched, and a "
        "complete recovery is one run away: install the module in your "
        "editor's Extensions folder instead, and decompile again with "
        "nothing ticked for removal."
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


def _standalone_family(companion: Path | None) -> str:
    """Which 1996 product a standalone belongs to -- from its data file.

    The executable does not carry the answer. The Games Factory and Click
    & Create ship stand-alone runtimes that share code, so an `.exe` built
    by one can hold the other's product string, and a product string in an
    executable is a hint about the BUILD and never about the format.

    The data file is authoritative, because a runtime only recognises its
    own pair: `GAPP`/`PAPP` is The Games Factory, `GAME`/`PAME` is Click &
    Create or MMF Express. A standalone always has one beside it or it has
    nothing to run. So the family is read from the companion, attributed
    to the companion, and when there is no companion the answer is that it
    cannot be told -- not a guess dressed as a verdict.

    The signature is the data file's first four bytes and the mapping is
    the engine's own table, so this costs a four-byte read and works on a
    copy too damaged to parse -- which is the case that most wants an
    answer.
    """
    if companion is None:
        return ("which 1996 product built it cannot be told from the "
                "executable -- the runtimes share code, so the data file "
                "beside it is what says, and none was found")
    try:
        with open(companion, "rb") as handle:
            signature = handle.read(4)
    except OSError:
        signature = b""
    family = tgf_identify.PRODUCT.get(signature)
    if family is None:
        return ("which 1996 product built it cannot be told from the "
                f"executable, and {companion.name} carries no signature "
                "that says either")
    return (f"{family} {signature.decode('ascii')}, from {companion.name} "
            f"-- the data file carries the product, not the executable")


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


def _version_text(version) -> str | None:
    return ".".join(str(part) for part in version) if version else None


def _mmf2_extension_rows(
    path: Path, app, extensions_dir: Path | None
) -> list[dict]:
    """One dict per extension module a 2.0 game asks for.

    The game's own list (`0x2234`) names every module its objects need; the
    pack block says which of them travel inside the executable (as RUNTIME
    builds, the half the editor cannot load); and the user's Extensions
    folder, when one was given, says which the editor here can open. All
    three are the engine's own readers -- this only lays the answers side
    by side for a card. `installed` is None when no folder was given, so a
    "not installed" is never claimed from a check that did not run.
    """
    records, _note = app.extensions()
    if not records:
        return []
    embedded: set[str] = set()
    if app.data[:2] == b"MZ":
        try:
            _start, entries, _note = mmf2_extensions.pack_entries(path)
            embedded = {entry["name"].lower() for entry in entries}
        except mmf2_extensions.PackProblem:
            pass
    installs = []
    if extensions_dir:
        folder = Path(extensions_dir)
        # The engine's Install is keyed on the INSTALL root and looks in
        # Extensions/ under it; the option names the Extensions folder
        # itself, so the root is its parent and the editor folder is the
        # one given -- whatever it happens to be called.
        install = mmf2_extensions.Install(folder.parent)
        install.editor = folder
        installs.append(install)
    rows = []
    for record in records:
        module = record["module"]
        known = mmf2_extensions.classify(module, path.parent, installs)
        version = _version_text(known["version"])
        rows.append({
            "module": module,
            "handle": record["handle"],
            "title": known["title"],
            "embedded": module.lower() in embedded,
            "shipped": str(known["shipped"]) if known["shipped"] else None,
            "installed": (
                None if not installs else known["installed"] is not None),
            "installed_path": (
                str(known["installed"]) if known["installed"] else None),
            "version": version,
            #: Present in the folder, but nothing readable inside it. A
            #: WEAKER state than `installed`, and named here so both
            #: surfaces say the same thing about it.
            #:
            #: An extension module carries a Windows version resource, and
            #: an editor that will not load one can look exactly like an
            #: editor that will: the file is there, the right size, a real
            #: executable. A module with no readable version has something
            #: wrong inside it, which is a reason to expect the editor to
            #: ask for it anyway. That is a CAUTION and not a verdict --
            #: the module may load perfectly well -- but reporting it as a
            #: flat "installed" turns a maybe into a promise.
            "unversioned": bool(
                installs and known["installed"] is not None and not version),
            "runtime_only": bool(known["runtime_only"]),
            "near_misses": [
                [name, title] for name, title in known["near_misses"]],
        })
    return rows


def _fusion2_inspection(
    path: Path, data: bytes, size: int,
    mmf2_extensions_dir: Path | None = None,
) -> Inspection | None:
    """An Inspection when this file is from the Fusion 2 era, else None:
    Multimedia Fusion 2.0, which KlikBack reads, or Fusion 2.5 and later,
    which it names and declines.

    The front door is the package header, read before anything else, for
    the reason the 1.0-vs-1.5 split is: the PE version resource belongs to
    whoever built the executable and authors overwrite it freely, while the
    header is the runtime's own. Without this early answer one of these
    files used to read as an unrecognised build, another as not a Clickteam
    game at all, and a third was identified as MMF 1.0 with confidence and
    then failed deep inside the 1.0 reader. Three wrong answers, one cause.

    Within the era, the split is the SIGNATURE, not a build threshold: 2.0
    writes `PAME`, and every Unicode `PAMU` package seen is Fusion 2.5's
    (builds 280 and up). The format build comes from the 2.0 engine's own
    reader, which is also what lists the extension modules the game asks
    for -- gathered now, so the window can show them before a run.
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
    is_exe = data[:2] == b"MZ"
    icon = _pe_icon_data_uri(path) if is_exe else None
    app = None
    why = None
    try:
        app = Mmf2App(path)
    except SystemExit as problem:  # the reader's own "no game header"
        why = str(problem)
    except Exception as problem:
        why = f"{type(problem).__name__}: {problem}"
    build = str(app.pbuild) if app is not None else None

    mmf2 = (signature == b"PAME" and major == MMF_PACKAGE_MAJOR
            and product == FUSION2_PRODUCT)
    if not mmf2:
        evidence = (
            f"its runtime package is {signature.decode('ascii')} product "
            f"{product}"
            + (" -- the Unicode runtime, which is Fusion 2.5's"
               if signature == b"PAMU" else "")
            + (f"; format build {build}" if build else "")
        )
        return Inspection(
            path, "fusion2", KIND_LABELS["fusion2"], build=build, size=size,
            notes=[ADVICE["fusion2"], evidence], icon=icon,
        )

    kind = "mmf2" if is_exe else "mmf2-ccn"
    notes: list[str] = []
    extensions: list[dict] = []
    name = None
    if app is None:
        notes.append(f"KlikBack's 2.0 reader could not open it: {why}")
    else:
        name = app.name() or None
        if not MMF2_BUILDS[0] <= app.pbuild <= MMF2_BUILDS[1]:
            notes.append(f"format build {app.pbuild} is outside the measured "
                         f"range. " + ADVICE["mmf2-build"])
        try:
            extensions = _mmf2_extension_rows(path, app, mmf2_extensions_dir)
        except Exception as problem:  # a card line, never a failed inspect
            notes.append(f"the extension list could not be read: "
                         f"{type(problem).__name__}: {problem}")
    return Inspection(
        path, kind, KIND_LABELS[kind], build=build, name=name, size=size,
        notes=notes, icon=icon, extensions=extensions,
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
    # Read through `application_bytes`, so a packed-project installer is
    # classified by the GAME it carries rather than by the setup program
    # wrapping it. `Build / Project` emits an installer whose game is a
    # Clickteam-compressed member of its payload, and there is no `PAME`
    # anywhere in the wrapper -- so the raw search below called every one of
    # them `mmf-unknown`, a confident answer about the wrong file. The build
    # stamp comes from the same unwrapped image for the same reason.
    inner = application_bytes(data)
    at = 0 if inner.startswith(b"PAME") else inner.find(b"PAME", 0x40000)
    if not (0 <= at <= len(inner) - 6):
        return "mmf-unknown", None
    word = struct.unpack_from("<H", inner, at + 4)[0]
    if word >> 8 != 3:
        return "mmf-unknown", None
    stamp = build_stamp(path) if inner is data else build_stamp_in(inner)
    version = stamp.file_version if stamp is not None else (0, 0, 0, 0)
    if word & 1:
        build = str(version[2] or version[3]) if version[:2] == (2, 5) else None
        return "mmf15", build
    build = (
        str(version[3])
        if version[:2] in ((2, 0), (2, 1), (2, 2)) else None
    )
    return "mmf1", build


def inspect(
    path: Path, mmf2_extensions_dir: Path | None = None
) -> Inspection:
    """What a file is, from its own bytes.

    `mmf2_extensions_dir` is the user's MMF 2 Extensions folder, when one
    is set: a 2.0 game's extension list then also says which modules the
    editor here has. It changes nothing about the verdict -- only the
    card's extension rows read it."""
    path = Path(path)
    try:
        data = path.read_bytes()
    except OSError as problem:
        return Inspection(
            path, "unreadable", KIND_LABELS["unreadable"],
            notes=[str(problem)],
        )
    size = len(data)

    # Asked before anything else, because a Fusion 2-era file otherwise
    # reaches three different wrong answers depending on which signature its
    # runtime happens to carry -- and the worst of them is a confident one.
    newer = _fusion2_inspection(path, data, size, mmf2_extensions_dir)
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
            notes.append(_standalone_family(companion))
            kind, label = "tgf-exe", KIND_LABELS["tgf-exe"]
            # Known here and nowhere else cheaper: this executable is a
            # game, and there is nothing beside it to decompile. No
            # setting changes that, so the inspection says so rather than
            # letting a run discover it.
            blocked = None if companion is not None else (
                "there is no game data file beside it that KlikBack can "
                "read, and a TGF/CnC standalone holds none of its own")
            if companion is not None:
                damage = _truncation(companion)
                if damage is not None:
                    # The label is written for the half that was named: the
                    # executable is whole, its game data is not, and saying
                    # "an incomplete copy" flatly about the .exe would send
                    # somebody looking for a better download of the wrong
                    # file.
                    kind = "tgf-damaged"
                    label = ("TGF/CnC standalone -- its game data is an "
                             "incomplete copy")
                    notes.append(damage)
            return Inspection(
                path, kind, label, size=size,
                companions=companions, notes=notes, blocked=blocked,
                icon=_pe_icon_data_uri(path),
            )
        return Inspection(
            path, "not-clickteam", KIND_LABELS["not-clickteam"], size=size,
            notes=["a Windows executable with no MMF overlay and no TGF/CnC "
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
            notes=[f"carries a TGF/CnC-style signature but is not readable "
                   f"as one: {note}"],
        )

    if data[:5] in (b"CnC2T", b"CnC2U"):
        which = "1.0" if data[:5] == b"CnC2T" else "1.5"
        return Inspection(
            path, "mmf-editable",
            f"{KIND_LABELS['mmf-editable']} (Multimedia Fusion {which})",
            size=size, notes=[ADVICE["mmf-editable"]],
        )

    # The Multimedia Fusion 2 editor's own project file -- the format
    # KlikBack WRITES. It landed in "not a Clickteam game" until
    # 2026-08-24, which is the sharpest wording defect the 1.1.0 release
    # test found: the native project format of the headline family was the
    # one editable project the app disowned, while both older `.cca`
    # generations got the right sentence from the branch above.
    #
    # The header is the writer's own (`mmf2_write_mfa`): "MMF2", then
    # `mfaBuild`, `product`, and the FORMAT build -- the same build number
    # `MMF2_BUILDS` measures, so a file from a later generation names
    # itself rather than being called 2.0 on the strength of its magic.
    if data[:4] == b"MMF2" and len(data) >= 16:
        _mfa_build, _product, build = struct.unpack_from("<3I", data, 4)
        measured = MMF2_BUILDS[0] <= build <= MMF2_BUILDS[1]
        product_name = "Multimedia Fusion 2" if measured else "Fusion 2 era"
        notes = [ADVICE["mmf-editable"]]
        if not measured:
            notes.append(
                f"format build {build} is outside the {MMF2_BUILDS[0]}-"
                f"{MMF2_BUILDS[1]} range KlikBack measured for Multimedia "
                f"Fusion 2.0, so which product wrote it is not claimed here")
        return Inspection(
            path, "mmf-editable",
            f"{KIND_LABELS['mmf-editable']} ({product_name})",
            build=str(build), size=size, notes=notes,
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


def _why_no_data_file(exe: Path) -> list[str]:
    """Name the `.gam`/`.cca` files that ARE beside `exe`, and why each was
    no good.

    The companion search answers `NOT FOUND -- no readable .gam/.cca beside
    <exe>`, which is true of an empty folder and equally true of a folder
    holding a 17 MB `.cca` that will not parse. The 1.1.0 release test hit
    the second and read the first: `Kenny's Rampage 3` reports NOT FOUND
    with its data file sitting right there. The reason exists -- the reader
    raises it -- and the search discards it to return a bool.

    So this asks the reader again, for the message only, using the SAME
    call the search uses (`clip_truncated=True`, so an incomplete copy
    still counts as readable and never lands here). That duplication is
    deliberate and has to stay in step: if the two ever disagree, this
    would explain a "no" the search did not give.
    """
    lines = [f"no game data file could be used for {exe.name}"]
    try:
        siblings = [p for p in sorted(exe.parent.iterdir())
                    if p.suffix.lower() in tgf_unprotect.DATA_SUFFIXES]
    except OSError as problem:
        return lines + [f"the folder itself could not be listed: {problem}"]
    if not siblings:
        return lines + [f"there is no .gam or .cca file in "
                        f"{exe.parent.name or '.'} at all"]
    detail = []
    readable = 0
    for candidate in siblings:
        size = f"{candidate.stat().st_size:,} bytes"
        try:
            tgf_format.read(candidate, clip_truncated=True)
        except Exception as problem:
            detail.append(f"  {candidate.name} ({size}): {problem}")
        else:
            readable += 1
            detail.append(f"  {candidate.name} ({size}): reads fine")
    if readable:
        # Some of them parse, so the search turned them down on the NAMING
        # rule, and its own note is the useful half -- it says which files
        # it weighed and that none carries the executable's stem, which is
        # the thing the user can act on. It refuses to guess between two
        # games on purpose.
        _found, why = tgf_unprotect.find_data_file(exe)
        lines = [f"no game data file could be used for {exe.name}: {why}"]
    lines.append(f"{len(siblings)} data file(s) sit beside it:")
    return lines + detail


def _decompile_tgf(
    path: Path, options: Options, inspection: Inspection,
    progress: Callable[..., None] | None = None,
) -> Result:
    #: Set by `run` when the refusal is "there is no data file to read",
    #: which wants its own advice -- the game and its data have to be put
    #: back together, and no KlikBack setting is involved.
    no_data: list[bool] = []

    def run():
        source, exe, notes = tgf_unprotect.resolve(path)
        if source is not None:
            for note in notes:
                print(f"  {note}")
        else:
            # The search's own note says "data file: NOT FOUND", which is
            # true of an empty folder and false of this one -- the file is
            # there and will not parse. Its verdict stands; its wording is
            # replaced by what `_why_no_data_file` can actually show.
            no_data.append(True)
            for line in _why_no_data_file(path):
                print(f"  {line}")
            # A refusal, not a failure. This was `failed` -- exit 1,
            # "Something unexpected went wrong" -- until 2026-08-24, for a
            # condition KlikBack has entirely diagnosed and can advise on.
            return ("refused", None)
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
                repair_object_data=options.repair_object_data,
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
    elif outcome == "refused" and no_data:
        # And this one needs the two halves of the game back in one folder,
        # which is not a KlikBack setting at all.
        advice = ADVICE["tgf-no-data"]
    return Result(path, inspection.kind, outcome, target, log, advice)


def _path_key(path) -> str:
    """One spelling for a path wherever it is compared: the window and the
    worker may name the same file with different separators or case."""
    try:
        return str(Path(path).resolve()).lower()
    except OSError:
        return str(path).lower()


def strip_list_for(path: Path, options: Options) -> list[str]:
    """The modules to remove from THIS 2.0 file: the run-wide list plus
    the ones chosen for the file itself, in a stable order, no repeats."""
    chosen = list(options.strip_extensions)
    wanted = _path_key(path)
    for key, modules in options.strip_for.items():
        if _path_key(key) == wanted:
            chosen += list(modules)
    seen: set[str] = set()
    unique = []
    for module in chosen:
        if module.lower() not in seen:
            seen.add(module.lower())
            unique.append(module)
    return unique


#: The engine's per-frame section-label note, as it is worded today. Only
#: the two counts are read out of it, and a gate converts a game with
#: merged sections and fails if this stops matching -- a total that
#: quietly disappears is worse than no total, because the whole point of
#: the line is that a project gained rows KlikBack wrote.
_SECTION_LABEL_NOTE = re.compile(
    r"^frame (\d+): (\d+) comment row\(s\) added\b")


def _section_label_total(notes: list[str]) -> str:
    """One line saying how many comment rows KlikBack added to this project.

    The engine reports the labels per frame, and always has. What it
    cannot report is the total, and the total is what gets lost: the
    worker condenses report lines that differ only in their numbers, which
    is exactly what a per-frame count is, so a hundred frames' worth of
    labels can reach the window as one line saying "1".

    A total is a different SHAPE, so the condenser cannot merge it away,
    and it is the number a person actually wants: how much of this project
    is ours rather than the author's. Section labels stay on by default --
    they are plainly KlikBack's own, they are labelled as ours in the
    project and rendered on yellow, and without them nothing records where
    the compiler merged the global events into a frame. That is what
    separates them from `--recover-comments`, where the invented text
    stands in for words the author really wrote, and which is therefore
    off unless it is asked for.
    """
    frames = rows = 0
    for note in notes:
        found = _SECTION_LABEL_NOTE.match(note)
        if found:
            frames += 1
            rows += int(found.group(2))
    if not rows:
        return ""
    return (
        f"report: {rows:,} comment row(s) across {frames:,} frame(s) are "
        f"KlikBack's own section labels, not the author's -- they mark "
        f"where the compiler merged global events and behaviours into a "
        f"frame, and are the only record of it. --no-section-labels leaves "
        f"them out."
    )


def _decompile_mmf2(
    path: Path, options: Options, inspection: Inspection,
    progress: Callable[..., None] | None = None,
) -> Result:
    """One 2.0 game through the engine's single call.

    The extension modules come out first, when asked and when there is a
    pack block to carve (a `.ccn` has none). Then `convert`, which writes
    the whole `.mfa` at the end or raises `Refuse` with the reason -- so
    there is never a half-written project to clean up. A stripped
    recovery takes a name of its own, `<stem>.decompiled.stripped.mfa`,
    for two reasons the engine's own command line already gives: the
    faithful recovery beside it is never overwritten by the cut-down one,
    and the filename itself says what was done to it.
    """
    out_dir = resolved_out_dir(path, options)
    strip = strip_list_for(path, options)
    target = out_dir / (
        f"{path.stem}{options.suffix}{'.stripped' if strip else ''}.mfa")
    folder = options.mmf2_extension_dir
    # Which removal names this project does not carry, decided from the
    # inspection's own module list rather than from the wording of the
    # engine's refusal. The engine checks the same thing first and refuses
    # with the project's list; this only decides WHICH advice rides on
    # that refusal, and matching prose to find out would stop working the
    # moment somebody improved the sentence -- silently, and in the
    # direction of saying nothing.
    uses = {row["module"].lower() for row in inspection.extensions}
    unknown_strip = [name for name in strip if name.lower() not in uses]

    def run():
        if target.exists() and not options.force:
            return ("skipped",
                    f"{target.name} already exists (--force to replace)", {})
        if options.extract_extensions and inspection.kind == "mmf2":
            carve = out_dir / f"{path.stem}{mmf2_extensions.FOLDER_SUFFIX}"
            if carve.exists() and not options.force:
                print(f"  extensions: {carve.name}/ already exists "
                      f"(--force to replace)")
            else:
                if progress is not None:
                    progress("extensions")
                out_dir.mkdir(parents=True, exist_ok=True)
                mmf2_extensions.extract(path, out_dir)
        if progress is not None:
            progress("convert")
        out_dir.mkdir(parents=True, exist_ok=True)
        report: dict = {}
        try:
            mmf2_writer.convert(
                path, target,
                section_labels=options.section_labels,
                report=report,
                strip_extensions=strip,
                generate_icons=options.substitute_artwork,
                extensions_dir=str(folder) if folder else None,
            )
        except mmf2_writer.Refuse as why:
            print(f"  refused: {why}")
            return ("refused", None, {})
        except SystemExit as why:  # the reader's own exit on a bad header
            print(f"  {why}")
            return ("failed", None, {})
        print(f"  wrote {target}")
        return ("built", target, report)

    log, (outcome, written, report) = _capture(run)
    if isinstance(written, str):  # the skipped message
        log = (log + "\n" + written).strip()
        written = None
    if outcome == "built":
        labels = _section_label_total(report.get("notes") or [])
        if labels:
            log = (log + "\n" + labels).strip()
    advice = ADVICE.get(outcome)
    if outcome == "built" and report.get("stripped"):
        advice = ADVICE["mmf2-stripped"]
    elif outcome == "refused" and unknown_strip:
        advice = ADVICE["mmf2-strip-unknown"]
    return Result(path, inspection.kind, outcome, written, log, advice)


def options_in_force(
    kind: str, options: Options, path: Path | None = None
) -> list[str]:
    """The options that shaped one file, as "name: value" lines.

    Only the family's own options are listed, because only those did
    anything: in a batch every option is global and each file takes the
    ones its kind has. Spelled in the window's words, so a line here can be
    found on screen. `path` is what the one per-file option (which modules
    to remove from a 2.0 game) is keyed on."""
    family = FAMILY_OF_KIND.get(kind)
    if family is None:
        return []
    on = lambda flag: "on" if flag else "off"  # noqa: E731 -- a one-word table
    # A .ccn is the bare package with no wrapper to carve modules from, so
    # for one the extraction option -- whatever it is set to -- did
    # nothing, and saying "on" would send somebody looking for a folder
    # that was never going to exist. (What a 1.x package embeds is carried
    # inside the rebuilt project itself either way.)
    extract_line = (
        "extract extensions into a subfolder: not applicable to a .ccn"
        if kind.endswith("-ccn")
        else f"extract extensions into a subfolder: "
             f"{on(options.extract_extensions)}")
    lines = [
        f"output folder: {options.out_dir or 'beside the input'}",
        f"each game into its own folder: {on(options.per_game_folders)}",
        f"overwrite existing output: {on(options.force)}",
        extract_line,
    ]
    if family in ("mmf1", "mmf15"):
        lines.append(f"recover comment positions: {on(options.recover_comments)}")
        lines.append("MMF 1.5 Extensions folder: " + (
            ", ".join(str(d) for d in options.extension_dirs) or "none"))
    if family == "mmf15":
        lines += [
            f"recover application icons: {on(options.application_icons)}",
            f"recover ownerless behaviours / globals: "
            f"{on(options.ownerless_recovery)}",
            f"rebuild external sub-applications: {on(options.subapplications)}",
        ]
    if family == "tgf":
        lines += [
            f"substitute stand-in icons / thumbnails: "
            f"{on(options.substitute_artwork)}",
            f"re-encode bank images MMF refuses: {on(options.repair_bank)}",
            f"repair object data MMF refuses: "
            f"{on(options.repair_object_data)}",
            f"reorder placement pointers: {options.repack_placement or 'off'}",
            f"open an incomplete copy: {on(options.drop_missing_assets)}",
        ]
    if family == "mmf2":
        lines += [
            f"substitute stand-in icons: {on(options.substitute_artwork)}",
            f"MMF 2.0 Extensions folder: {options.mmf2_extension_dir or 'none'}",
            f"label merged global events / behaviours: "
            f"{on(options.section_labels)}",
        ]
        removed = strip_list_for(path, options) if path is not None else []
        lines.append("remove extensions from the project: "
                     + (", ".join(removed) if removed else "none"))
    lines.append("options of other game families did not apply to this file")
    return lines


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
    applied = options_in_force(kind, options, path)

    def finished(result: Result) -> Result:
        return replace(_comment_recovery_advice(result, options),
                       applied=applied)

    try:
        if kind in ("mmf1", "mmf1-ccn"):
            return finished(_decompile_mmf1(path, options, progress))
        if kind in ("mmf15", "mmf15-ccn"):
            return finished(_decompile_mmf15(path, options, progress))
        if kind in ("tgf-exe", "tgf-data", "tgf-damaged"):
            return finished(
                _decompile_tgf(path, options, inspection, progress))
        if kind in ("mmf2", "mmf2-ccn"):
            return finished(
                _decompile_mmf2(path, options, inspection, progress))
    except Exception as problem:  # a crash is an error card, never silence
        return finished(Result(
            path, kind, "error", None,
            f"{type(problem).__name__}: {problem}", ADVICE.get("failed"),
        ))
    # Nothing above took the file, so this is a verdict about what it IS.
    # Until 2026-08-24 every one of these was `nothing-to-do` and exited 0,
    # which put a path that does not exist, a stranger, and a Fusion 2.5
    # game in the same bucket as an editable project that genuinely needs
    # nothing done to it. They are three different answers and now say so
    # -- see `OUTCOME_EXIT`.
    outcome = KIND_OUTCOME.get(kind, "unrecognised")
    advice = ADVICE.get(kind) or ADVICE.get("not-clickteam")
    # Several of these inspections carry their advice as a NOTE as well,
    # because the identify card has no separate place to put one. Here
    # there is one, and printing the same paragraph twice under two
    # headings reads as two different things that happen to agree.
    body = [note for note in inspection.notes if note != advice]
    return Result(path, kind, outcome, None,
                  "\n".join(body) or inspection.product, advice)


def collect_targets(paths: list[Path]) -> list[Path]:
    """Files worth inspecting from a mixed list of files and folders."""
    return [path for path, _named in collect_targets_with_origin(paths)]


def collect_targets_with_origin(paths) -> list[tuple[Path, bool]]:
    """The same list, each entry saying whether a PERSON named that file.

    `(path, named)` -- `named` is True for a path given on the command line
    or dropped on the window, False for one a folder walk turned up.

    The difference is the whole of the answer to two 1.1.0 defects, and it
    could not be made anywhere else: below this line every function takes a
    path and opens it, so nothing downstream can tell the two apart. A file
    a walk found and cannot use is a stranger and is skipped in silence,
    which is right -- a folder of fifty files should not report forty-eight
    holiday photos. A file a PERSON named is a request, and a request that
    cannot be met gets an answer.

    Before this, the same rule applied to both, so `klikback-cli identify
    game.exe` -- the spelling KlikBack's own `--help` printed -- dropped the
    word `identify` without a murmur, decompiled the game the user wanted
    identified, and exited 0.
    """
    found: list[tuple[Path, bool]] = []
    for path in paths:
        path = Path(path)
        if path.is_dir():
            found.extend(
                (candidate, False)
                for candidate in sorted(path.rglob("*"))
                if candidate.suffix.lower() in CANDIDATE_SUFFIXES
                and candidate.is_file()
            )
        else:
            # Including a path that is not there: `inspect()` reports it as
            # unreadable, which is an answer to a person who named it.
            found.append((path, True))
    return found
