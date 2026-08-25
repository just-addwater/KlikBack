# GENERATED — do not edit by hand. This file is produced by KlikBack's
# sync tooling; changes belong in the source it is generated from.
#
# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""Rebuild an editable project from a Multimedia Fusion 1.5 game.

Given a compiled 1.5 executable or package this writes the `.cca` an editor
opens and carves out every extension module the game carried. KlikBack's
command line and window call it through `klikback.api`; it needs no editor,
no installed copy of MMF, and no network.

**The output is deliberately not named `<name>.cca`.** Real games ship
`thing.exe` beside `thing.cca`, and writing `<name>.cca` would silently
overwrite the very source a rebuild is meant to be compared against. The
default is `<name>.decompiled.cca`, and an existing file is never overwritten
unless overwriting is asked for explicitly.

**This refuses by name rather than half-building.** When the pipeline meets
something it cannot reconstruct correctly, it says which feature stopped it
instead of writing a project that looks fine and is wrong. A refusal is an
expected outcome on some games, not a crash.

Programs with no owner are recovered by default. A frame's trailing programs
— an object's behaviour, or a global event page that outlived the reference
naming it — are written back with honest labelling rather than dropped, so
the events are in the project to read even where the compiled bytes no longer
say whose they were.
"""

from __future__ import annotations
import argparse
from collections import Counter
from collections.abc import Callable
import traceback
from pathlib import Path
from klikback.core.common.compression_probe import application_bytes, overlay_offset
from klikback.core.common.extension_binaries import embedded_modules
from klikback.core.mmf15.assemble import ContainerProblem, SUBAPPLICATION_TYPE, Unsupported, assemble, subapplication_payload
from klikback.core.mmf15.object_record import runtime_objects
from klikback.core.mmf15.module_drift import compare as compare_modules, menu_report_line, report_line

REPO = Path(__file__).resolve().parents[1]

DEFAULT_EXTENSIONS: list[Path] = []

SKIP_PARTS: tuple[str, ...] = ()

BUILD_SUFFIXES = (".exe", ".scr", ".ccn")

def executables(roots: list[Path]) -> list[Path]:
    """Walk a path into the list of candidate files, recursing into folders."""
    found: list[Path] = []
    for root in roots:
        if root.is_file():
            found.append(root)
            continue
        if not root.exists():
            print(f"  SKIP {root}: does not exist")
            continue
        for path in sorted(root.rglob("*")):
            if path.suffix.lower() not in BUILD_SUFFIXES or not path.is_file():
                continue
            if any(part.startswith(SKIP_PARTS) for part in path.parts):
                continue
            found.append(path)
    return found

def output_label(build: Path) -> str:
    if build.suffix.lower() == ".exe":
        return build.stem
    return f"{build.stem}{build.suffix.lower().replace('.', '_')}"

def is_mmf_standalone(exe: Path) -> bool:
    """Whether these bytes are a 1.5 standalone game, judged by content alone.
    """
    try:
        data = application_bytes(exe.read_bytes())
    except OSError:
        return False
    return overlay_offset(data) >= 0

def extract_cox(exe: Path, out_dir: Path, force: bool) -> str:
    """Carve the extension modules the game carried into a folder of `.cox` files.

    A compiled game embeds the modules it uses, so they come back whole from the
    game alone, byte-for-byte, on a machine that never had them installed.
    """
    try:
        modules = embedded_modules(exe)
    except Exception as problem:
        return f"cox: cannot read module stream ({problem})"
    if not modules:
        return "cox: none embedded"
    out_dir.mkdir(parents=True, exist_ok=True)
    written = skipped = 0
    for module in modules:

        name = Path(module.filename).name
        if not name or name in (".", ".."):
            continue
        target = out_dir / name
        if target.exists() and not force:
            skipped += 1
            continue
        target.write_bytes(module.image)
        written += 1
    report = f"cox: {written} written to {out_dir.name}/"
    if skipped:
        report += f", {skipped} already present (--force to replace)"
    return report

def module_drift(exe: Path, directories: list[Path]) -> str:
    """Compare the modules a game carries against the ones installed on this machine.

    Only meaningful when an extensions folder has been named: with nothing to
    compare against, every module reads as "not installed" and the report says
    nothing worth reading. Given a folder, a difference is worth knowing — the
    game was built against a different release of that extension than the one
    installed here.
    """
    try:
        result = compare_modules(exe, list(directories))
    except Exception as problem:
        return f"modules: cannot compare ({problem})"
    lines = [report_line(result)]
    menus = menu_report_line(result)
    if menus:
        lines.append(menus)
    return "\n  ".join(lines)

def external_subapplications(exe: Path) -> list[str]:
    """The child projects a game refers to as separate files rather than embedding.
    """
    try:
        objects = runtime_objects(exe)
    except Exception:
        return []
    found: list[str] = []
    for obj in objects:
        if obj.get("object_type") != SUBAPPLICATION_TYPE:
            continue
        try:
            payload = subapplication_payload(obj)
        except Exception:
            continue
        if payload["internal"] or not payload["path"]:
            continue
        found.append(Path(payload["path"].decode("latin-1")).name)
    return found

def find_child_package(exe: Path, filename: str) -> Path | None:
    """Locate the package a sub-application reference points at, by content."""
    stem = Path(filename).stem
    for suffix in (".ccn", ".cca"):
        beside = exe.parent / f"{stem}{suffix}"
        if beside.exists():
            return beside
    for suffix in (".ccn", ".cca"):
        matches = sorted(exe.parent.rglob(f"{stem}{suffix}"))
        matches = [
            path for path in matches
            if not any(part.startswith(SKIP_PARTS) for part in path.parts)
        ]
        if matches:
            return matches[0]
    return None

def build_cca(
    exe: Path,
    target: Path,
    args,
    donors: list[Path],
    subapplication_directory: Path | None = None,

    progress: Callable[..., None] | None = None,
) -> tuple[str, str]:
    """Rebuild one game into one project file, and return what happened.

    Reads the executable or package, recovers frames, events, objects and banks,
    assembles the project and writes it beside its inputs. The optional progress
    callback is a pure observer — a stage name at each boundary, `(stage, n, of)`
    inside the per-frame loops — and cannot change what is built.
    """
    if target.exists() and not args.force:
        return "skipped", f"cca: {target.name} already exists (--force to replace)"
    try:
        data, summary = assemble(
            exe,
            args.scaffold,
            target,
            template_scaffolds=donors,
            extension_dir=[d for d in args.extensions if d.exists()] or None,
            ownerless_behaviours_per_frame=(
                None if args.no_recover_ownerless_behaviours else "auto"
            ),
            recover_comments=args.recover_comments,
            reconstruct_application_icons=not args.no_application_icons,
            alias_object_icons=not args.no_alias_object_icons,
            subapplication_directory=subapplication_directory,
            progress=progress,
        )
    except (Unsupported, ContainerProblem) as problem:
        return "refused", f"cca: REFUSED -- {problem}"
    except Exception as problem:
        if args.traceback:
            traceback.print_exc()
        return "failed", f"cca: FAILED -- {type(problem).__name__}: {problem}"
    target.parent.mkdir(parents=True, exist_ok=True)
    if progress is not None:
        progress("write")
    target.write_bytes(data)
    return "built", f"cca: {target.name} ({len(data):,} bytes)\n" + summarise(summary)

def build_subapplications(
    exe: Path, children: list[str], out_dir: Path, args, donors: list[Path]
) -> list[str]:
    """Rebuild the child projects a game embeds, alongside their parent.

    A sub-application is a whole project inside another one. Each is rebuilt as
    its own file so the set opens in the editor the way the author built it.
    """
    outcomes: list[str] = []
    for filename in children:
        source = find_child_package(exe, filename)
        if source is None:
            print(f"  subapp: {filename} NOT FOUND beside the parent -- the "
                  f"rebuilt project will point at a file that is not there")
            outcomes.append("sub-application not found")
            continue
        target = out_dir / f"{Path(filename).stem}.cca"
        if target.exists() and not args.force and target != source:
            print(f"  subapp: {target.name} already exists, left alone "
                  f"(--force to replace); the parent points at it")
            outcomes.append("sub-application skipped")
            continue
        if target == source:

            print(f"  subapp: {target.name} is the authored project itself; "
                  f"not rebuilt, and the parent points at it")
            outcomes.append("sub-application already present")
            continue
        print(f"  subapp: {source.name} -> {target.name}")
        outcome, report = build_cca(exe=source, target=target, args=args,
                                    donors=donors,
                                    subapplication_directory=out_dir)
        outcomes.append(f"sub-application {outcome}")
        print("    " + report.replace("\n", "\n  "))
    return outcomes

def summarise(summary: dict) -> str:
    """The per-frame inventory of what was recovered, in machine-readable form.
    """
    name = summary["name"].decode("latin-1")
    frame = summary["frames"][0]
    title = frame["name"].decode("latin-1") if frame["name"] else "<none>"
    lines = [
        f"{name!r}: {len(summary['frames'])} frames, "
        f"{len(summary['objects'])} objects, "
        f"{len(summary['placements'])} instances, "
        f"{len(summary['images'])} images",
        f"frame 0 {title!r} {frame['width']}x{frame['height']}",
    ]

    passwords = summary.get("frame_passwords") or ()
    if passwords:
        named = ", ".join(f"frame {index} {text!r}" for index, text in passwords[:6])
        if len(passwords) > 6:
            named += f", and {len(passwords) - 6} more"
        lines.append(f"recovered {len(passwords)} frame password(s): {named}")
    losses = list(summary.get("losses", ()))
    lines.extend(f"loss: {line}" for line in losses)
    if not losses:
        lines.append("no recorded losses")

    lines.extend(f"repair: {line}" for line in summary.get("repairs", ()))
    return "\n".join("      " + line for line in lines)

def build_parser() -> argparse.ArgumentParser:
    """The command-line options this pipeline accepts."""
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("targets", nargs="+", type=Path,
                        help="an .exe, or a folder to walk for .exe files")
    parser.add_argument("--out", type=Path, default=None,
                        help="write everything here instead of beside each EXE")
    parser.add_argument("--force", action="store_true",
                        help="replace output files that already exist")
    parser.add_argument("--suffix", default=".decompiled",
                        help="inserted before .cca; '' writes <stem>.cca and "
                             "can overwrite a real project, so it needs --force")
    parser.add_argument(
        "--scaffold", type=Path, default=None,
        help="an explicit scaffold .cca to grow instead of the synthesised "
             "Build-119 scaffold (the default since 2026-08-09)")
    parser.add_argument("--donors", type=Path, default=None,
                        help="directory of neutral class-head donor .cca files "
                             "to use instead of the synthesised class heads "
                             "(the default since 2026-08-09)")
    parser.add_argument("--extensions", type=Path, action="append", default=None,
                        help="an installed MMF 1.5 Extensions directory; "
                             "repeatable, the editor's own first")
    parser.add_argument("--no-cca", action="store_true")
    parser.add_argument("--no-cox", action="store_true")
    parser.add_argument(
        "--no-subapps",
        action="store_true",
        help="do not reconstruct external Sub-Application children, and leave "
             "the parent's stored path exactly as the target holds it. That "
             "path is the absolute path on the machine that COMPILED the "
             "game, so by default each child is found beside the parent (or "
             "under it), rebuilt into the output directory under its own "
             "name, and the parent is repointed at it",
    )
    parser.add_argument(
        "--recover-ownerless-behaviours",
        action="store_true",
        help="accepted and ignored: recovery is the default. Kept so existing "
             "scripts and the documented commands keep working",
    )
    parser.add_argument(
        "--no-recover-ownerless-behaviours",
        action="store_true",
        help="REFUSE a game whose frames carry anonymous programs instead of "
             "preserving them after labelled comments. Recovery is on by "
             "default because refusing loses the entire game rather than one "
             "page's ownership",
    )
    parser.add_argument(
        "--recover-comments",
        action="store_true",
        help="put a comment row back at every editor row the compiler stripped."
             " The POSITION is recovered -- the compiler renumbers nothing, so "
             "a program's own row numbering names every row it lost -- and the "
             "TEXT is substituted, which is why this is off by default",
    )
    parser.add_argument(
        "--no-application-icons",
        action="store_true",
        help="leave the scaffold's default application icons in place instead "
             "of recovering all four icon resources from the EXE",
    )
    parser.add_argument(
        "--alias-object-icons",
        action="store_true",
        help="accepted and ignored: aliasing is the default since 2026-08-05. "
             "Kept so existing scripts and notes keep working",
    )
    parser.add_argument(
        "--no-alias-object-icons",
        action="store_true",
        help="give every object its own copy of the substituted editor icon "
             "instead of pointing them at a shared AGMI bank-1 record. The "
             "icons are a compile loss either way -- no runtime package "
             "carries editor artwork -- so this only controls how many copies "
             "of an invented picture the file holds, which on a large game is "
             "a few hundred records against a handful. Use it if a project "
             "misbehaves in a way you suspect the shared records for",
    )
    parser.add_argument("--traceback", action="store_true",
                        help="print the full traceback on an unexpected failure")
    return parser

def driver_defaults(**overrides) -> argparse.Namespace:
    """The options a caller that is not a command line starts from."""
    args = build_parser().parse_args(["--", "placeholder.exe"])
    for name, value in overrides.items():
        if not hasattr(args, name):
            raise ValueError(f"{name} is not a mmf_decompile option")
        setattr(args, name, value)
    return args

def main() -> None:
    """Run the decompile from a command line."""
    parser = build_parser()
    args = parser.parse_args()

    if args.extensions is None:
        args.extensions = DEFAULT_EXTENSIONS
    if args.scaffold is not None and not args.scaffold.exists():
        raise SystemExit(f"scaffold not found: {args.scaffold}")
    donors = None
    if args.donors is not None:
        donors = sorted(args.donors.glob("*.cca")) if args.donors.exists() else []
        if not donors:
            print(f"  NOTE no class-head donors found in {args.donors} -- "
                  f"falling back to the synthesised class heads")
            donors = None

    targets = executables(args.targets)
    if not targets:
        raise SystemExit("no .exe files found")

    outcomes: Counter[str] = Counter()
    for exe in targets:
        out_dir = args.out or exe.parent
        print(f"\n=== {exe.name}")
        if not is_mmf_standalone(exe):
            outcomes["not an MMF standalone"] += 1
            print("  skipped: no PAME overlay -- not an MMF standalone")
            continue
        label = output_label(exe)
        if not args.no_cox:
            print("  " + extract_cox(exe, out_dir / f"{label}_cox", args.force))
            print("  " + module_drift(exe, args.extensions))
        if not args.no_cca:
            children = [] if args.no_subapps else external_subapplications(exe)
            target = out_dir / f"{label}{args.suffix}.cca"
            outcome, report = build_cca(
                exe, target, args, donors,
                subapplication_directory=out_dir if children else None,
            )
            outcomes[outcome] += 1
            print("  " + report)
            for child_outcome in build_subapplications(
                exe, children, out_dir, args, donors
            ):
                outcomes[child_outcome] += 1

    if not args.no_cca:
        tally = ", ".join(f"{n} {k}" for k, n in sorted(outcomes.items()))
        print(f"\n{len(targets)} EXEs seen: {tally}")
        print("A 'loss:' line is content the writer knew it dropped -- read them.")
        print("Opening in MMF proves it loads; run/edit/save/close/reopen is the real test.")
