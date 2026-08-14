# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""KlikBack's command line: identify or decompile, one file or a folder.

    klikback-cli game.exe                 decompile next to the input
    klikback-cli "C:/old games"           walk a folder, decompile everything
    klikback-cli identify game.exe        say what a file is, touch nothing
    klikback-cli identify games/ --json   the same, machine-readable
    klikback-cli game.exe --worker        the GUI's mode: NDJSON events

Exit codes: 0 everything succeeded (or there was nothing to do), 2 nothing
recognisable was found, 3 at least one game was refused or invalid, 1 an
unexpected error or a KlikBack folder that needs fixing. A refusal is the
engine declining to write a wrong project -- the report names the feature
that stopped it.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from klikback import PRODUCT, __version__, api, resources


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="klikback-cli",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version",
                        version=f"{PRODUCT} {__version__}")
    parser.add_argument("targets", nargs="+", type=Path,
                        help="game files (.exe/.gam/.cca/.ccn) or folders")
    parser.add_argument("--identify", action="store_true",
                        help="report what each file is; decompile nothing")
    parser.add_argument("--json", action="store_true",
                        help="machine-readable output, one JSON object per file")
    parser.add_argument("--worker", action="store_true",
                        help="machine mode for the KlikBack GUI: emit one JSON "
                             "event per line on stdout while decompiling")
    parser.add_argument("--out", type=Path, default=None,
                        help="output folder (default: beside each input)")
    parser.add_argument("--per-game-folders", action="store_true",
                        help="write each game's output into its own "
                             "subfolder, named after the game")
    parser.add_argument("--force", action="store_true",
                        help="overwrite existing output files")
    parser.add_argument("--suffix", default=".decompiled",
                        help="output name suffix (default: .decompiled)")
    parser.add_argument("--no-extensions", action="store_true",
                        help="do not extract embedded extension modules into "
                             "a subfolder beside the output")
    parser.add_argument("--extensions-dir", action="append", type=Path,
                        default=[], metavar="DIR",
                        help="an installed editor's extension folder, for "
                             "module titles (repeatable)")
    parser.add_argument("--recover-comments", action="store_true",
                        help="recover comment-row POSITIONS with substituted "
                             "text (off by default and not recommended: the "
                             "text is invented, and on a program whose event "
                             "groups KlikBack had to close it stops a "
                             "decompile that works without it)")
    parser.add_argument("--no-application-icons", action="store_true",
                        help="MMF 1.5: leave default application icons")
    parser.add_argument("--no-ownerless-recovery", action="store_true",
                        help="MMF 1.5: refuse games with ownerless event "
                             "programs instead of recovering them")
    parser.add_argument("--no-subapps", action="store_true",
                        help="MMF 1.5: do not rebuild external "
                             "Sub-Application children")
    parser.add_argument("--no-substitute-artwork", action="store_true",
                        help="TGF/CnC: leave stripped thumbnails/icons out "
                             "instead of writing neutral ones")
    parser.add_argument("--repair-bank", action="store_true",
                        help="TGF/CnC: re-encode bank images MMF 1.5 refuses "
                             "(off by default; 1996 editors open them as-is)")
    parser.add_argument("--drop-missing-assets", action="store_true",
                        help="TGF/CnC: open an incomplete copy -- one whose "
                             "file ends partway through a sound or image "
                             "bank -- by dropping the assets whose bytes "
                             "are not there. Nothing is invented and "
                             "nothing else moves (off by default; without "
                             "it an incomplete copy is refused and said so)")
    parser.add_argument("--repack-placement", nargs="?", const="all",
                        default=None, metavar="LEVELS",
                        help="TGF/CnC: reorder a level's object-placement "
                             "pointers into ascending order, which is what "
                             "MMF 1.5 can refuse a project over while the "
                             "1996 editors open it. Bare means every level, "
                             "or name them: 51, or 3,7-9. The entries "
                             "themselves do not move, so drawing order "
                             "survives (off by default)")
    return parser


def options_from(args: argparse.Namespace) -> api.Options:
    return api.Options(
        out_dir=args.out,
        per_game_folders=args.per_game_folders,
        force=args.force,
        extract_extensions=not args.no_extensions,
        recover_comments=args.recover_comments,
        application_icons=not args.no_application_icons,
        ownerless_recovery=not args.no_ownerless_recovery,
        subapplications=not args.no_subapps,
        extension_dirs=args.extensions_dir,
        substitute_artwork=not args.no_substitute_artwork,
        repair_bank=args.repair_bank,
        repack_placement=args.repack_placement,
        drop_missing_assets=args.drop_missing_assets,
        suffix=args.suffix,
    )


def show_inspection(inspection: api.Inspection) -> None:
    line = f"{inspection.path.name}: {inspection.product}"
    if inspection.build:
        line += f", build {inspection.build}"
    if inspection.protected is not None:
        line += ", protected" if inspection.protected else ", not protected"
    if inspection.name:
        line += f" -- {inspection.name!r}"
    print(line)
    for extra in (*inspection.notes, *inspection.companions):
        print(f"    {extra}")


def run_worker(targets: list[Path], options: api.Options) -> int:
    """The GUI's machine mode: one JSON object per line on stdout.

    Events, in the order a consumer sees them per file:

        {"event": "file", "path": ..., "kind": ...}      work starts
        {"event": "stage", "name": ...}                  a stage boundary
        {"event": "progress", "stage": ..., "n": 3, "of": 12}
        {"event": "loss", "text": ...}                   one recorded loss
        {"event": "result", ...Result fields...}         the file is done

    When a startup check fails the whole stream is a single
    `{"event": "blocked", "reason": ..., "text": ...}` line, emitted by
    `main` before any of the above, so a consumer can tell "KlikBack's own
    folder needs fixing" apart from a process that died.

    The engine's own printed report is captured into the result's log, so
    nothing but JSON reaches stdout -- but that capture also means the
    callback must write to the stream object saved BEFORE decompiling
    starts, not to whatever `sys.stdout` names mid-run. Every line is
    flushed as it is written so a pipe reader sees events live. Cancel is
    process kill: the pipelines never half-write an output (a candidate
    that fails validation is preserved as `.failed.cca` instead).
    """
    out = sys.stdout

    def emit(event: dict) -> None:
        out.write(json.dumps(event) + "\n")
        out.flush()

    def progress(stage: str, n: int | None = None, of: int | None = None) -> None:
        if n is None:
            emit({"event": "stage", "name": stage})
        else:
            emit({"event": "progress", "stage": stage, "n": n, "of": of})

    seen = 0
    worst = 0
    for target in targets:
        inspection = api.inspect(target)
        if len(targets) > 1 and not inspection.decompilable:
            # The same rule as the human mode: a folder walk skips
            # strangers quietly, a file named explicitly gets a result.
            continue
        seen += 1
        emit({"event": "file", "path": str(target), "kind": inspection.kind})
        result = api.decompile(target, options, inspection, progress=progress)
        for line in result.log.splitlines():
            text = line.strip()
            if text.startswith("loss: "):
                emit({"event": "loss", "text": text[len("loss: "):]})
        emit({"event": "result", **result.as_dict()})
        if result.outcome in ("refused", "invalid"):
            worst = max(worst, 3)
        elif result.outcome in ("failed", "error"):
            worst = max(worst, 1)
    return worst if seen else 2


def stop_before_starting(
    args: argparse.Namespace, reason: str, text: str, code: int
) -> int:
    """Report a problem found before any game is read, in whichever
    language the caller speaks.

    The worker's consumer reads NDJSON and nothing else, so a bare line on
    stdout reaches the window as a process that died with no output -- the
    opposite of what these are. Every one of them is a fixable thing about
    KlikBack's own folder or the flags it was given, found before a byte of
    anybody's game was touched."""
    if args.worker:
        sys.stdout.write(json.dumps(
            {"event": "blocked", "reason": reason, "text": text}) + "\n")
        sys.stdout.flush()
    else:
        print(text)
    return code


def main(argv: list[str] | None = None) -> int:
    # 1996 game names arrive in whatever codepage their era used; never let
    # a console that cannot print one kill a batch.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    args = build_parser().parse_args(argv)
    try:
        resources.verify_artwork()
    except resources.ResourceProblem as problem:
        return stop_before_starting(args, "artwork", str(problem), 1)

    if args.repack_placement is not None and not api.level_spec_is_valid(
            args.repack_placement):
        return stop_before_starting(
            args, "options",
            f"--repack-placement does not understand "
            f"{args.repack_placement!r}. Name levels as numbers and ranges "
            f"-- 51, or 3,7-9 -- or pass the flag on its own for every "
            f"level.", 2)

    targets = api.collect_targets(args.targets)
    if not targets:
        print("nothing to look at: no .exe/.gam/.cca/.ccn found")
        return 2

    if args.identify:
        recognised = 0
        for target in targets:
            inspection = api.inspect(target)
            recognised += inspection.decompilable
            if args.json:
                print(json.dumps(inspection.as_dict()))
            else:
                show_inspection(inspection)
        return 0 if recognised else 2

    options = options_from(args)
    if args.worker:
        return run_worker(targets, options)
    tally: dict[str, int] = {}
    worst = 0
    for target in targets:
        inspection = api.inspect(target)
        if len(targets) > 1 and not inspection.decompilable:
            # A folder walk skips strangers quietly; a file named
            # explicitly always gets a full explanation.
            continue
        if not args.json:
            print(f"\n=== {target.name}")
        result = api.decompile(target, options, inspection)
        tally[result.outcome] = tally.get(result.outcome, 0) + 1
        if args.json:
            print(json.dumps(result.as_dict()))
        else:
            print("  " + result.log.replace("\n", "\n  "))
            if result.advice and not result.ok:
                print(f"  note: {result.advice}")
        if result.outcome in ("refused", "invalid"):
            worst = max(worst, 3)
        elif result.outcome in ("failed", "error"):
            worst = max(worst, 1)

    if not tally:
        print("no Clickteam games found in what was given")
        return 2
    if not args.json:
        summary = ", ".join(f"{n} {k}" for k, n in sorted(tally.items()))
        print(f"\n{sum(tally.values())} file(s): {summary}")
        print("A 'loss:' line is content the writer knew it dropped -- read them.")
    return worst


if __name__ == "__main__":
    sys.exit(main())
