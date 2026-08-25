# GENERATED — do not edit by hand. This file is produced by KlikBack's
# sync tooling; changes belong in the source it is generated from.
#
# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""Rebuild an editable project from a Multimedia Fusion 1.0 game.

Given a compiled 1.0 executable this writes the `.cca` an editor opens, a
`.summary.json` inventory of what was recovered, and every extension module
the executable carried. KlikBack's own command line and window call it
through `klikback.api`; nothing here needs a running editor, an installed
copy of MMF, or a network.

Two habits of this pipeline are worth knowing because they shape what you
get back.

**It validates the project before writing it.** A rebuild that fails its own
structural check is written as `<name>.decompiled.failed.cca` and reported as
invalid, so a bad candidate is kept for inspection rather than deleted — but
it is never handed over as a normal result.

**Its losses are itemised, not summarised.** Frames whose events would not
decompress, frame passwords, qualifier memberships past the editor's limit of
eight, unresolved frame item ids, and global event sheets flattened into the
frames that used them are each reported on their own line, naming the frame.
A loss is a statement about the compiled game, not a failure of the run: the
compiler discarded something the format cannot express, and the report says
which something.

The source file is never overwritten. An output that already exists is left
alone unless overwriting is asked for explicitly.
"""

from __future__ import annotations
import argparse
import traceback
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from klikback.core.common.compression_probe import application_bytes, overlay_offset
from klikback.core.common.extension_binaries import embedded_modules
from klikback.core.mmf1.editor_state import retarget_frame_editor_windows
from klikback.core.common.mixed_multiframe_blind_reconstruct import failed_output_path, reconstruct, reconstruction_report, set_project_path, summary_output_path, validate, write_report

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
    """Whether these bytes are a 1.0 standalone game, judged by content alone.

    The extension is a convention and the filename is a claim; the overlay the
    runtime appends is the evidence.
    """
    try:
        data = application_bytes(exe.read_bytes())
    except OSError:
        return False
    return overlay_offset(data) >= 0

def extract_cox(exe: Path, out_dir: Path, force: bool) -> str:
    """Carve the extension modules the game carried into a folder of `.cox` files.

    A compiled game embeds the modules it uses, so they can be recovered whole
    even when the machine has never had them installed. They are written out
    byte-for-byte; nothing is generated to fill a gap.
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

def losses(summary: dict, report: dict) -> list[str]:
    """Everything the compiled game could not give back, one entry per fact.

    Each entry names what was lost and where, in the terms a user of the editor
    would recognise — a frame number, an object name, an event row — because the
    answer to "is this project usable?" depends on which of these applies, not on
    how many there are.
    """
    lines: list[str] = []
    for index, reason in summary.get("unreadable_event_frames", ()):
        lines.append(f"frame {index} events LOST -- would not decompress: {reason}")
    for entry in report.get("lossy_qualifier_memberships", ()):
        lines.append(
            f"object {entry['name']!r} lost qualifier {entry['dropped_qualifier']} "
            f"-- {entry['reason']}"
        )
    if report.get("unresolved_frame_item_ids"):
        lines.append(
            f"{len(report['unresolved_frame_item_ids'])} unresolved frame item id(s)"
        )
    for entry in report.get("unresolved_global_events", ()):
        lines.append(f"global events left flattened into the frame sheet: {entry}")
    for entry in report.get("salvaged_music_records", ()):
        lines.append(
            f"music record {entry['index']} (handle {entry['handle']}) holds a "
            f"damaged back-reference at byte {entry['offset']} -- distance "
            f"{entry['distance']} reaches before the record; "
            f"{entry['emitted_length']} byte(s) SUBSTITUTED, the rest of the "
            f"track recovered against its declared length"
        )
    unplaced = report.get("unplaced_placeholders") or []
    if unplaced:
        lines.append(
            f"{len(unplaced)} frame member(s) the runtime never placed, each "
            f"given a Create placeholder instance at (0, 0); the object, its "
            f"record and its reference are recovered, the authored editor "
            f"position is not"
        )
    dangling = report.get("dangling_shoot_parents") or []
    if dangling:
        objects = sorted({entry["object_id"] for entry in dangling})
        lines.append(
            f"{len(dangling)} Shoot placeholder parent(s) naming object(s) "
            f"{objects} with no other evidence in their frame; the parent word "
            f"is stale, so each placeholder is written with no parent, which "
            f"is what the editor itself writes in the same situation"
        )
    recovered = report.get("recovered_comments") or []
    if recovered:
        total = sum(count for _frame, count in recovered)
        lines.append(
            f"{total} comment row(s) recovered across {len(recovered)} "
            f"frame(s) from the compiler's own row numbering; each row's "
            f"POSITION is recovered and its TEXT is SUBSTITUTED, because "
            f"compilation discards the words and keeps the number"
        )
    synthesised = report.get("synthesised_library_titles") or []
    if synthesised:
        lines.append(
            f"no source names the editor library title of "
            f"{', '.join(synthesised)}; the module basename was written "
            f"instead, which is not a title MMF itself ever stores"
        )
    return lines

def repairs(report: dict) -> list[str]:
    """The repairs made along the way, in the words the report prints.

    A repair is neither a clean recovery nor a loss: something in the game was
    inconsistent and was mended so the project would open. Each one says what was
    wrong and what was done, because a silent repair is indistinguishable from a
    misreading.
    """
    lines: list[str] = []
    repaired = report.get("repaired_event_reference_types") or []
    if repaired:
        ids = sorted({entry["object_id"] for entry in repaired})
        lines.append(
            f"{len(repaired)} event reference(s) whose stored runtime type "
            f"disagreed with the object bank; rewritten to the bank's type, "
            f"object ids {ids}"
        )
    groups = report.get("group_close_repairs") or []
    if groups:
        total = sum(count for _frame, count in groups)
        lines.append(
            f"{total} event group(s) across {len(groups)} frame(s) left open "
            f"by the compiler; each closed with a close record copied from "
            f"this package, placed before the next group starts. The group's "
            f"rows are recovered; the close row is added"
        )
    sizes = report.get("repaired_parameter_sizes") or []
    if sizes:
        stored = sorted({entry["stored"] for entry in sizes})
        types = sorted({entry["parameter_type"] for entry in sizes})
        lines.append(
            f"{len(sizes)} condition parameter size word(s) carrying a stray "
            f"high byte (stored {stored}, parameter type(s) {types}); the low "
            f"byte is the size, which is the only reading that tiles the "
            f"record and the size those types carry in every measured project"
        )
    return lines

def summarise(report: dict, summary: dict) -> str:
    """The per-frame inventory that becomes the `.summary.json` beside the project.

    Counts, names and the loss list in machine-readable form, for anyone who
    wants to diff two runs or check a rebuild without opening an editor.
    """
    types = ", ".join(
        f"type {key}x{count}" for key, count in report["object_types"].items()
    )
    lines = [
        f"{report['frame_count']} frames, {report['object_count']} objects, "
        f"{report['placement_count']} instances, {report['image_count']} images, "
        f"{report['event_count']} events",
        f"object types: {types}",
    ]
    if report.get("global_event_rows"):
        lines.append(f"recovered {report['global_event_rows']} global event row(s)")
    passwords = summary.get("frame_passwords") or ()
    if passwords:

        named = ", ".join(f"frame {index} {text!r}" for index, text in passwords[:6])
        if len(passwords) > 6:
            named += f", and {len(passwords) - 6} more"
        lines.append(f"recovered {len(passwords)} frame password(s): {named}")
    found = losses(summary, report)
    lines.extend(f"loss: {line}" for line in found)
    if not found:
        lines.append("no recorded losses")
    lines.extend(f"repair: {line}" for line in repairs(report))
    return "\n".join("      " + line for line in lines)

def build_cca(
    exe: Path, target: Path, args,

    progress: Callable[..., None] | None = None,
) -> tuple[str, str]:
    """Rebuild one game into one project file, and return what happened.

    This is the whole pipeline for a single target: read the executable, recover
    the frames, events, objects and banks, assemble the project, check it, and
    write it beside its inputs. The optional progress callback is a pure
    observer — it is called with a stage name at each boundary and with
    `(stage, n, of)` inside the per-frame loops, and it can never change what is
    built.
    """
    if target.exists() and not args.force:
        return "skipped", f"cca: {target.name} already exists (--force to replace)"
    try:
        output, summary = reconstruct(
            exe,
            allow_unreadable_events=args.allow_unreadable_events,
            extension_dirs=args.extensions,
            recover_comments=args.recover_comments,
            progress=progress,
        )
    except Exception as problem:
        if args.traceback:
            traceback.print_exc()
        return "failed", f"cca: FAILED -- {type(problem).__name__}: {problem}"

    target.parent.mkdir(parents=True, exist_ok=True)
    if progress is not None:
        progress("validate")
    try:
        validate(output, summary)
    except Exception as error:

        failed = failed_output_path(target)
        failed.write_bytes(set_project_path(output, failed))
        report = reconstruction_report(
            exe, failed, summary, status="validation_failed",
            error=f"{type(error).__name__}: {error}",
        )
        if not args.no_summary:
            write_report(summary_output_path(target), report)
        return "invalid", (
            f"cca: INVALID -- output failed its own validation: "
            f"{type(error).__name__}: {error}\n"
            f"      candidate kept as {failed.name} for diagnosis"
        )

    output_report = reconstruction_report(exe, target, summary, status="success")
    try:

        stamped = set_project_path(output, target)

        stamped, layout_repairs = retarget_frame_editor_windows(stamped)
    except Exception as problem:
        if args.traceback:
            traceback.print_exc()
        return "failed", (
            f"cca: FAILED at the last step, after a complete reconstruction -- "
            f"{type(problem).__name__}: {problem}"
        )
    if progress is not None:
        progress("write")
    target.write_bytes(stamped)
    output_report["retargeted_frame_editor_windows"] = layout_repairs
    text = f"cca: {target.name} ({len(output):,} bytes)\n" + summarise(
        output_report, summary
    )
    for line in layout_repairs:
        text += f"\n      repair: {line}"
    if not args.no_summary:
        write_report(summary_output_path(target), output_report)
        text += f"\n      summary: {summary_output_path(target).name}"
    return "built", text

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
    parser.add_argument("--allow-unreadable-events", action="store_true",
                        help="reconstruct a frame with no events when its event "
                             "chunk will not decompress. The frame's events are "
                             "LOST, not recovered -- for a damaged EXE only")
    parser.add_argument("--recover-comments", action="store_true",
                        help="restore the author's comment rows at the "
                             "positions the compiler's row numbering names. "
                             "The POSITION is recovered exactly; the TEXT is "
                             "SUBSTITUTED, so this adds a lot of writing the "
                             "author did not do -- tens of thousands of rows "
                             "on a large game. Off by default for that reason, "
                             "not for doubt about the reading")
    parser.add_argument("--extensions", type=Path, action="append", default=None,
                        help="an installed Extensions directory, repeatable, "
                             "highest precedence first. Used only for the "
                             "editor library title of a module the EXE does "
                             "not embed a titled image of; defaults to the "
                             "Build 98 editor's own")
    parser.add_argument("--no-summary", action="store_true",
                        help="do not write the .summary.json")
    parser.add_argument("--no-cca", action="store_true")
    parser.add_argument("--no-cox", action="store_true")
    parser.add_argument("--traceback", action="store_true",
                        help="print the full traceback on an unexpected failure")
    return parser

def driver_defaults(**overrides) -> argparse.Namespace:
    """The options a caller that is not a command line starts from."""
    args = build_parser().parse_args(["."])
    for name, value in overrides.items():
        setattr(args, name, value)
    return args

def main() -> None:
    """Run the decompile from a command line."""
    parser = build_parser()
    args = parser.parse_args()
    if args.extensions is None:
        args.extensions = DEFAULT_EXTENSIONS

    targets = executables(args.targets)
    if not targets:

        raise SystemExit(f"no {'/'.join(BUILD_SUFFIXES)} files found")

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
        if not args.no_cca:
            target = out_dir / f"{label}{args.suffix}.cca"
            outcome, report = build_cca(exe, target, args)
            outcomes[outcome] += 1
            print("  " + report)

    if not args.no_cca:
        tally = ", ".join(f"{n} {k}" for k, n in sorted(outcomes.items()))
        print(f"\n{len(targets)} builds seen: {tally}")
        print("A 'loss:' line is content the writer knew it dropped -- read them.")
        print("Opening in MMF proves it loads; run/edit/save/close/reopen is the real test.")
