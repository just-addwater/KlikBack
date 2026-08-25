# GENERATED — do not edit by hand. This file is produced by KlikBack's
# sync tooling; changes belong in the source it is generated from.
#
# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""Say what a 1996-era Clickteam file actually is: product, build, protection.

The file's own bytes are the only authority. The extension is a convention
and the filename is a claim by whoever archived it, so every field reported
here is read out of the file: `GAPP`/`PAPP` data files belong to The Games
Factory, `GAME`/`PAME` to Click & Create / Multimedia Fusion Express, and a
`P` signature means the protected form. A standalone executable is never
trusted about the format — runtimes share code across products — but it is
a good build fingerprint: the position of the runtime's checksum marker is
stable per build.
"""

from __future__ import annotations
import argparse
import collections
import struct
import sys
from pathlib import Path
import klikback.core.tgf.format as tgf

GAME_MARKER = b"wwx" + bytes((0x89,)) + b"EV"

PRODUCT_STRINGS = [
    b"The Games Factory", b"Click & Create", b"Multimedia Fusion Express",
    b"Corel Click", b"Klik & Play",
]

COLOUR_MODES = {3: "8-bit", 4: "24-bit", 5: "4-bit", 6: "15-bit", 7: "16-bit"}

PRODUCT = {b"GAPP": "TGF", b"PAPP": "TGF", b"GAME": "CnC/MMFx", b"PAME": "CnC/MMFx"}

def pe_timestamp(blob: bytes) -> str:
    """The PE header's build date, `YYYY-MM-DD`, or `-` when the blob is not a
    readable PE image. Useful for dating a standalone; never used to decide
    what the file is.
    """
    try:
        if blob[:2] != b"MZ":
            return "-"
        pe = struct.unpack_from("<I", blob, 0x3C)[0]
        if blob[pe:pe + 4] != b"PE\0\0":
            return "-"
        import datetime
        stamp = struct.unpack_from("<I", blob, pe + 8)[0]
        return datetime.datetime.fromtimestamp(stamp, datetime.timezone.utc).strftime("%Y-%m-%d")
    except Exception:
        return "-"

def describe_data(path: Path) -> dict | None:
    """Say what a data file is, or nothing if it is not one of these at all."""
    try:
        game = tgf.read(path)
    except (tgf.NotAGameFile, tgf.ContainerProblem) as problem:
        return {"path": path, "error": str(problem)}
    mode = struct.unpack_from("<H", game.raw, tgf.OFF_COLOR_MODE)[0]

    starts = set()
    for level in game.levels():
        try:
            starts.add(tgf.level_blocks(level.data)[0])
        except tgf.ContainerProblem:
            starts.add(-1)
    return {
        "path": path,
        "family": PRODUCT[game.signature],
        "signature": game.signature.decode(),
        "protected": game.protected,
        "version": game.version,
        "levels": game.level_count,
        "colour": COLOUR_MODES.get(mode, f"mode {mode}"),
        "name": game.name,
        "segments": sorted({s.ident for s in game.segments}),
        "block_start": sorted(starts),
        "size": len(game.raw),
    }

def describe_exe(path: Path) -> dict:
    """Say what a standalone executable is, and which build made it."""
    blob = path.read_bytes()
    at = blob.find(GAME_MARKER)
    found = sorted({s.decode("latin-1") for s in PRODUCT_STRINGS if s in blob})
    return {
        "path": path,
        "marker": at,
        "standalone": at >= 0,
        "strings": found,
        "built": pe_timestamp(blob),
        "size": len(blob),
    }

def main() -> int:
    """Print the description from a command line."""
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("roots", nargs="+", type=Path)
    parser.add_argument("--summary", action="store_true",
                        help="print only the tallies, not a line per file")
    args = parser.parse_args()

    builds: collections.Counter = collections.Counter()
    families: collections.Counter = collections.Counter()
    colours: collections.Counter = collections.Counter()
    unreadable = []

    for root in args.roots:
        for path in sorted(root.rglob("*")):
            if path.suffix.lower() in (".gam", ".cca"):
                info = describe_data(path)
                if "error" in info:
                    unreadable.append((path, info["error"]))
                    if not args.summary:
                        print(f"DATA {path.name[:38]:40} UNREADABLE: {info['error']}")
                    continue
                key = (info["family"], "protected" if info["protected"] else "plain")
                families[key] += 1
                colours[info["colour"]] += 1
                if not args.summary:
                    starts = "/".join(f"0x{s:02X}" for s in info["block_start"])
                    print(
                        f"DATA {path.name[:38]:40} {info['signature']} "
                        f"{info['family']:9} "
                        f"{'PROTECTED' if info['protected'] else 'plain    '} "
                        f"v{info['version']:04X} {info['levels']:4} levels "
                        f"{info['colour']:7} blocks@{starts:9} "
                        f"{info['size']:>11,}B  {info['name'][:24]!r}"
                    )
            elif path.suffix.lower() == ".exe":
                info = describe_exe(path)
                builds[info["marker"]] += 1
                if not args.summary:
                    where = f"0x{info['marker']:X}" if info["standalone"] else "not-a-standalone"
                    print(
                        f"EXE  {path.name[:38]:40} {where:16} built {info['built']} "
                        f"{info['size']:>11,}B  {info['strings']}"
                    )

    print("\ndata files by family and state:")
    for (family, state), count in sorted(families.items()):
        print(f"  {count:4} {family} {state}")
    print("colour modes:")
    for colour, count in colours.most_common():
        print(f"  {count:4} {colour}")
    print("executables by runtime build (marker offset):")
    for marker, count in sorted(builds.items()):
        label = f"0x{marker:X}" if marker >= 0 else "no marker -- not a stand-alone"
        print(f"  {count:4} {label}")
    if unreadable:
        print(f"\n{len(unreadable)} unreadable data file(s):")
        for path, why in unreadable[:20]:
            print(f"  {path.name}: {why}")
    return 0
