# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""KlikBack's command line: identify or decompile, one file or a folder.

    klikback-cli game.exe                   decompile next to the input
    klikback-cli "C:/old games"             walk a folder, decompile everything
    klikback-cli --identify game.exe        say what a file is, touch nothing
    klikback-cli --identify games/ --json   the same, machine-readable
    klikback-cli game.exe --worker          the GUI's mode: NDJSON events

There is no `identify` sub-command; `--identify` is an option like any
other. Until 2026-08-24 the three lines above said otherwise, and typing
what they said dropped the word without a murmur and DECOMPILED the file
that was meant to be identified.

Exit codes. 0 means everything you named was understood and nothing needs
your attention:

    0  all good -- built, skipped, already a project, nothing to do
    1  KlikBack itself went wrong, or its folder or flags need fixing
    2  something you named could not be read or recognised
    3  a game was read and could not be rebuilt (refused, invalid)
    4  a Clickteam product KlikBack does not support (Fusion 2.5 and later)

A refusal is the engine declining to write a wrong project -- the report
names the feature that stopped it, and a different setting or a newer
KlikBack may open it. A 4 will not change: that product's file format is
not one KlikBack reads. `--identify` reports the same code for the same
file as a decompile run would, so a script can trust either.
"""

from __future__ import annotations

import argparse
import json
import re
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
                        help="MMF 1.0/1.5: an installed Multimedia Fusion "
                             "1.5 Extensions folder (.cox files), read for "
                             "the display names a compiled game dropped "
                             "(repeatable)")
    parser.add_argument("--mmf2-extensions-dir", type=Path, default=None,
                        metavar="DIR",
                        help="MMF 2.0: your Multimedia Fusion 2 Extensions "
                             "folder (the folder itself). Read only, never "
                             "written: extension objects then get their "
                             "module's own editor icon, and --identify says "
                             "which modules the editor here can load")
    parser.add_argument("--no-section-labels", action="store_true",
                        help="MMF 2.0: do not add the yellow comment rows "
                             "that mark where the compiler merged global "
                             "events and behaviours into each frame (they "
                             "are KlikBack's rows, not the author's)")
    parser.add_argument("--strip-extension", action="append", default=[],
                        metavar="MODULE.mfx",
                        help="MMF 2.0: REMOVE this extension from the "
                             "recovered project -- every object of the "
                             "module, every event line and action naming "
                             "them, and the declaration -- so the editor "
                             "stops demanding a module you cannot get. "
                             "Destructive: the author's content is gone "
                             "from the output (written as "
                             "<name>.decompiled.stripped.mfa so the "
                             "faithful recovery is never overwritten). "
                             "Repeatable. Applies to every 2.0 file in the "
                             "run and refuses a name a game does not use, "
                             "so in practice it is a single-game flag")
    parser.add_argument("--strip-for", action="append", nargs=2, default=[],
                        metavar=("PATH", "MODULE.mfx"),
                        help="MMF 2.0: the same removal for one file only "
                             "(what the window sends for a batch; "
                             "repeatable)")
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
                        help="TGF/CnC and MMF 2.0: write no stand-in icon "
                             "where the game has none of its own -- a TGF/CnC "
                             "game then keeps its stripped thumbnails/icons "
                             "blank, and a 2.0 object with no picture (a "
                             "String, a Counter, an extension object) gets "
                             "a blank icon instead of a drawing from the "
                             "artwork folder")
    parser.add_argument("--repair-bank", action="store_true",
                        help="TGF/CnC: re-encode bank images MMF 1.5 refuses "
                             "(off by default; the TGF/CnC editors open them as-is)")
    parser.add_argument("--repair-object-data", action="store_true",
                        help="TGF/CnC: restore an object data-block head "
                             "MMF 1.5 refuses a whole game over, while the "
                             "TGF/CnC editors open it. Rederived from the "
                             "object's own structure, never substituted "
                             "(off by default; object data is otherwise "
                             "copied verbatim)")
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
                             "TGF/CnC editors open it. Bare means every level, "
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
        repair_object_data=args.repair_object_data,
        repack_placement=args.repack_placement,
        drop_missing_assets=args.drop_missing_assets,
        mmf2_extension_dir=args.mmf2_extensions_dir,
        section_labels=not args.no_section_labels,
        strip_extensions=list(args.strip_extension),
        strip_for=strip_for_from(args.strip_for),
        suffix=args.suffix,
    )


def strip_for_from(pairs: list[list[str]]) -> dict[str, list[str]]:
    """`--strip-for PATH MODULE` pairs as the facade's per-file map."""
    chosen: dict[str, list[str]] = {}
    for path, module in pairs:
        chosen.setdefault(path, []).append(module)
    return chosen


def extension_line(row: dict) -> str:
    """One 2.0 extension module for the identify card, in words: where the
    game gets it from, and whether the editor here can load it."""
    facts = []
    facts.append("inside the game (runtime build)" if row["embedded"]
                 else "not inside the game")
    if row["shipped"]:
        facts.append("a copy beside the game")
    if row["installed"] is None:
        facts.append("editor folder not checked (--mmf2-extensions-dir)")
    elif row.get("unversioned"):
        # Present, but nothing readable inside it -- see the `unversioned`
        # note in `api._mmf2_extension_rows`. Saying a flat "installed"
        # here turns a check that cannot see inside the module into a
        # promise that the editor will load it.
        facts.append("PRESENT but no version could be read from it -- the "
                     "editor may still refuse it")
    elif row["installed"]:
        facts.append("installed" + (f" {row['version']}" if row["version"]
                                    else ""))
    else:
        facts.append("NOT in your Extensions folder -- the editor will ask "
                     "for it")
        for name, title in row["near_misses"][:3]:
            facts.append(f"installed under another name? {name} "
                         f"({title or 'no title'}) -- a different release, "
                         f"not a substitute")
    title = f" ({row['title']})" if row["title"] else ""
    return f"{row['module']}{title}: " + "; ".join(facts)


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
    if inspection.extensions:
        count = len(inspection.extensions)
        print(f"    {count} extension module{'s' if count != 1 else ''} "
              f"the game asks for:")
        for row in inspection.extensions:
            print(f"      {extension_line(row)}")


#: The most distinct report lines one file's event stream will carry per
#: category. Far above anything a game should reach once repeats are
#: condensed -- a shape is a MESSAGE, not an item -- so hitting it means
#: something is reporting pathologically, and the tail is summarised
#: rather than streamed.
CONDENSED_LIMIT = 500


def condensed(lines: list[str]) -> list[tuple[str, int]]:
    """`(first line, how many more like it)` per distinct line shape.

    Two lines share a shape when they are identical after every run of
    digits is masked out -- which is exactly how the engines' per-item
    reports repeat ("image 481 is referenced by no object", 3,000 times).
    First-seen order, so the stream reads as the log does. Past
    `CONDENSED_LIMIT` distinct shapes, the rest are one summary line."""
    groups: dict[str, list] = {}
    order: list[list] = []
    for text in lines:
        shape = re.sub(r"\d+", "#", text)
        found = groups.get(shape)
        if found is None:
            groups[shape] = found = [text, 0]
            order.append(found)
        else:
            found[1] += 1
    if len(order) > CONDENSED_LIMIT:
        tail = order[CONDENSED_LIMIT:]
        left = sum(1 + extra for _text, extra in tail)
        order = order[:CONDENSED_LIMIT]
        order.append([f"({left} further lines are not shown here; the "
                      f"full report and the session log have every one)", 0])
    return [(text, extra) for text, extra in order]


def run_worker(targets: list[tuple[Path, bool]], options: api.Options) -> int:
    """The GUI's machine mode: one JSON object per line on stdout.

    Events, in the order a consumer sees them per file:

        {"event": "file", "path": ..., "kind": ...}      work starts
        {"event": "stage", "name": ...}                  a stage boundary
        {"event": "progress", "stage": ..., "n": 3, "of": 12}
        {"event": "loss", "text": ..., "more": 0}        one recorded loss
        {"event": "note", "text": ..., "more": 0}        one 2.0 report note
        {"event": "result", ...Result fields...}         the file is done

    A `loss` is what the 1.x and 1996 engines print as `loss:` -- content
    the writer knew it dropped. A `note` is what the 2.0 engine prints as
    `report:` -- its whole account of what changed: substitutions, what was
    inlined, what was stripped. Both reach the window's Details block; the
    distinction is kept because the window sorts them differently.

    The engines report per item, and a big game reports per item tens of
    thousands of times -- one real game produced 46,000 lines, which is
    both unreadable and a stall (each event is marshalled into the window
    on its own). So lines that repeat with only their numbers changed are
    CONDENSED before emission: a single event carries the first such line
    and `more`, how many further lines matched its shape. Nothing is dropped
    from the record -- the result's `log`, the CLI's own output and the
    session log all keep every line; only the event stream is condensed,
    because its job is a readable card, not an archive.

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
    codes: list[int] = []
    for target, _named in targets:
        inspection = api.inspect(target)
        if len(targets) > 1 and not inspection.decompilable:
            # Deliberately NOT the human mode's rule, which turns on who
            # named the file. In worker mode the caller is the window, and
            # it has already expanded every folder itself, inspected every
            # file and put a card on screen for the ones it cannot use --
            # so every path arriving here is "named" and the distinction
            # says nothing. What it still needs is the batch rule: report
            # on the games, and on a lone file whatever it turns out to
            # be.
            continue
        seen += 1
        emit({"event": "file", "path": str(target), "kind": inspection.kind})
        result = api.decompile(target, options, inspection, progress=progress)
        losses: list[str] = []
        notes: list[str] = []
        for line in result.log.splitlines():
            text = line.strip()
            if text.startswith("loss: "):
                losses.append(text[len("loss: "):])
            elif text.startswith("report: "):
                notes.append(text[len("report: "):])
        for name, lines in (("loss", losses), ("note", notes)):
            for text, extra in condensed(lines):
                emit({"event": name, "text": text, "more": extra})
        emit({"event": "result", **result.as_dict()})
        codes.append(result.exit_code)
    return api.worst_exit(codes) if seen else api.EXIT_UNRECOGNISED


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


def mistyped_option(parser: argparse.ArgumentParser,
                    targets: list[Path]) -> str | None:
    """A named target that is really an option somebody typed bare.

    `klikback-cli identify game.exe` is the case this exists for: it is
    what KlikBack's own `--help` printed until 2026-08-24, and argparse
    takes `identify` as a file name. The word then does not exist, so it
    used to be dropped in silence -- and the file after it was DECOMPILED,
    the opposite of what was asked, with a success code.

    The test is deliberately narrow: a target with no directory part, no
    suffix, that does not exist, and whose name with dashes in front IS
    one of this parser's own options. Anything else is just a path that is
    not there, and gets reported as one rather than second-guessed."""
    options = {string for action in parser._actions
               for string in action.option_strings}
    for target in targets:
        text = str(target)
        if (target.suffix or target.parent != Path(".")
                or target.exists() or f"--{text}" not in options):
            continue
        rest = " ".join(f'"{p}"' for p in targets if str(p) != text)
        return (
            f"klikback-cli has no {text!r} command -- it is an option, "
            f"spelled --{text}. Nothing was done, on purpose: ignoring the "
            f"word would have DECOMPILED the file(s) named after it "
            f"instead. What was probably meant:\n\n"
            f"    klikback-cli --{text} {rest}".rstrip()
        )
    return None


def main(argv: list[str] | None = None) -> int:
    # 1996 game names arrive in whatever codepage their era used; never let
    # a console that cannot print one kill a batch.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        resources.verify_artwork()
    except resources.ResourceProblem as problem:
        return stop_before_starting(args, "artwork", str(problem),
                                    api.EXIT_ERROR)

    mistyped = mistyped_option(parser, args.targets)
    if mistyped is not None:
        return stop_before_starting(args, "options", mistyped,
                                    api.EXIT_UNRECOGNISED)

    if args.repack_placement is not None and not api.level_spec_is_valid(
            args.repack_placement):
        return stop_before_starting(
            args, "options",
            f"--repack-placement does not understand "
            f"{args.repack_placement!r}. Name levels as numbers and ranges "
            f"-- 51, or 3,7-9 -- or pass the flag on its own for every "
            f"level.", api.EXIT_UNRECOGNISED)

    targets = api.collect_targets_with_origin(args.targets)
    if not targets:
        print("nothing to look at: no .exe/.gam/.cca/.ccn/.mfa found")
        return api.EXIT_UNRECOGNISED

    if args.identify:
        # The same table the decompile path uses, and the same rule about
        # who a verdict belongs to. A file a PERSON named always counts:
        # if it is missing, or is a product KlikBack cannot read, the run
        # says so in its exit code. Files a folder WALK turned up are
        # reported in full but do not drag the code down -- a folder of
        # fifty games and two text files is not a failed request -- except
        # that a walk which found nothing usable at all is still a 2.
        codes = []
        walked = recognised = 0
        for target, named in targets:
            inspection = api.inspect(target, args.mmf2_extensions_dir)
            if args.json:
                print(json.dumps(inspection.as_dict()))
            else:
                show_inspection(inspection)
            if named:
                codes.append(inspection.exit_code)
            else:
                walked += 1
                recognised += inspection.decompilable
        if walked and not recognised:
            codes.append(api.EXIT_UNRECOGNISED)
        return api.worst_exit(codes)

    options = options_from(args)
    if args.worker:
        return run_worker(targets, options)
    tally: dict[str, int] = {}
    codes: list[int] = []
    losses = 0
    for target, named in targets:
        inspection = api.inspect(target)
        if not named and not inspection.decompilable:
            # A folder walk skips strangers quietly; a file named
            # explicitly always gets a full explanation. The test used to
            # be "more than one target", which meant a missing path named
            # alongside a real game was dropped without a word.
            continue
        if not args.json:
            print(f"\n=== {target.name}")
        result = api.decompile(target, options, inspection)
        tally[result.outcome] = tally.get(result.outcome, 0) + 1
        losses += sum(1 for line in result.log.splitlines()
                      if line.strip().startswith("loss: "))
        if args.json:
            print(json.dumps(result.as_dict()))
        else:
            print("  " + result.log.replace("\n", "\n  "))
            if result.applied:
                # Which options shaped THIS file. In a mixed batch every
                # flag is global and each file takes the ones its family
                # has, so the line is per file rather than per run.
                print("  options in force: " + "; ".join(result.applied))
            # Advice rides on a refusal or a failure -- and on one success:
            # a project with modules removed says so, whether or not the
            # person reading it later was the one who asked.
            if result.advice and (not result.ok or
                                  result.advice == api.ADVICE["mmf2-stripped"]):
                print(f"  note: {result.advice}")
        codes.append(result.exit_code)

    if not tally:
        print("no Clickteam games found in what was given")
        return api.EXIT_UNRECOGNISED
    if not args.json:
        summary = ", ".join(f"{n} {k}" for k, n in sorted(tally.items()))
        print(f"\n{sum(tally.values())} file(s): {summary}")
        if losses:
            # Only when there are some. This printed on every run, including
            # ones with no losses and no games, which taught readers to skip
            # the line that matters most on the runs where it does.
            print(f"{losses:,} 'loss:' line(s) above are content the writer "
                  f"knew it dropped -- read them.")
    return api.worst_exit(codes)


if __name__ == "__main__":
    sys.exit(main())
