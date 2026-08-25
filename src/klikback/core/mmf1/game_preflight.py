# GENERATED — do not edit by hand. This file is produced by KlikBack's
# sync tooling; changes belong in the source it is generated from.
#
# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""Look a game over cheaply, before committing to rebuilding it.

Decompressing every bank and serialising a whole project is expensive, and
finding out afterwards that the game uses something unsupported is worse. This
reads only what is cheap to read -- the runtime build, the object and module
tables, the frame and event boundaries -- and reports what a rebuild would
meet.

That is what the inspect card is built on: enough to say what a file is and
what is inside it, fast enough to run the moment a file is dropped on the
window.
"""

from __future__ import annotations
import argparse
import json
import struct
import time
from collections import Counter
from pathlib import Path, PureWindowsPath
from klikback.core.mmf1.build_version import build_stamp
from klikback.core.common.event_object_registry import parse_compiled_placements_with_links
from klikback.core.common.exe_to_cca import extract_event_programs
from klikback.core.common.extension_binaries import embedded_modules
from klikback.core.common.extension_inventory import chunk_payload, frames_from, load_outer, objects_from
from klikback.core.mmf1.extension_module_table import parse_module_table
from klikback.core.common.subapplication_reconstruct import SUBAPPLICATION_TYPE, runtime_subapplication

BANK_NAMES = {
    0x6666: "images",
    0x6667: "fonts",
    0x6668: "samples",
    0x6669: "midi",
}

def _chunk(chunks, chunk_id: int):
    return next((chunk for chunk in chunks if chunk.chunk_id == chunk_id), None)

def _text(payload: bytes) -> str:
    return payload.split(b"\0", 1)[0].decode("latin-1", errors="replace")

def _frame_inventory(index: int, chunks: list, issues: list[str]) -> dict:
    header_chunk = _chunk(chunks, 0x3334)
    if header_chunk is None:
        raise ValueError(f"frame {index} has no 0x3334 header")
    header = chunk_payload(header_chunk)
    if len(header) < 10:
        raise ValueError(f"frame {index} header is only {len(header)} bytes")
    width, height = struct.unpack_from("<HH", header, 0)

    name_chunk = _chunk(chunks, 0x3335)
    name = _text(chunk_payload(name_chunk)) if name_chunk else ""

    placement_chunk = _chunk(chunks, 0x3338)
    placements = 0
    if placement_chunk is not None:
        try:
            placements = len(
                parse_compiled_placements_with_links(chunk_payload(placement_chunk))
            )
        except Exception as error:
            issues.append(
                f"frame {index} placements: {type(error).__name__}: {error}"
            )

    event_chunk = _chunk(chunks, 0x333D)
    events = 0
    event_program_sizes: list[int] = []
    event_program_events: list[int] = []
    if event_chunk is not None:
        try:
            programs = extract_event_programs(chunk_payload(event_chunk))
            event_program_sizes = [sum(map(len, program)) for program in programs]
            event_program_events = [len(program) for program in programs]
            events = sum(event_program_events)
        except Exception as error:
            issues.append(f"frame {index} events: {type(error).__name__}: {error}")

    return {
        "index": index,
        "name": name,
        "width": width,
        "height": height,
        "placements": placements,
        "events": events,
        "event_program_count": len(event_program_sizes),
        "event_program_sizes": event_program_sizes,
        "event_program_events": event_program_events,
    }

def preflight(path: Path) -> dict:
    """Inventory one game without decoding its banks.

    Everything worth knowing about a game before committing to the expensive part.
    Images and sounds are the bulk of a decompile's time, so this deliberately
    does not touch them: it reads the structure, counts what is there, and lists
    what would go wrong.

    The counting half is the easy half — frames with their sizes, objects by type,
    placements, events, which banks are present and how many stored bytes each
    holds, the build stamp, the application's own name.

    The checking half is the reason it exists. Object types the rebuild does not
    support are named. An extension object whose module is not listed in the
    game's module table is named, and so is a module listed there but missing from
    the embedded modules the game carries. A Sub-Application — a project embedded
    inside another — is resolved to the companion file it expects to find beside
    the game, and reported when that file is not there, because a game that
    depends on a missing companion will disappoint later rather than at once.

    All of it comes back as findings rather than as a refusal. Something on the
    list may not matter for the game in hand, and the point of looking early is to
    know before spending the time, not to be stopped.
    """
    start = time.monotonic()
    outer = load_outer(path)
    stamp = build_stamp(path)
    issues: list[str] = []

    app_name_chunk = _chunk(outer, 0x2224)
    app_name = _text(chunk_payload(app_name_chunk)) if app_name_chunk else ""

    objects = objects_from(outer)
    type_counts = Counter(entry["type"] for entry in objects)
    unsupported = sorted(object_type for object_type in type_counts if 10 <= object_type < 32)
    if unsupported:
        issues.append(f"unsupported runtime object types {unsupported}")

    module_chunk = _chunk(outer, 0x2228)
    modules = []
    module_slots = 0
    if module_chunk is not None:
        modules, module_slots = parse_module_table(chunk_payload(module_chunk))
    slots = {module.index for module in modules}
    missing_slots = sorted(
        object_type - 32
        for object_type in type_counts
        if object_type >= 32 and object_type - 32 not in slots
    )
    if missing_slots:
        issues.append(f"extension object module slots missing from 0x2228: {missing_slots}")

    subapplications = []
    for entry in objects:
        if entry["type"] != SUBAPPLICATION_TYPE:
            continue
        runtime = runtime_subapplication(entry["definition"])
        child = runtime.path.decode("latin-1", errors="replace")
        child_name = PureWindowsPath(child).name if child else ""
        companion = path.parent / child_name if child_name else None
        exists = bool(companion and companion.is_file())
        subapplications.append(
            {
                "object_id": entry["id"],
                "path": child,
                "companion": str(companion) if companion else None,
                "companion_exists": exists,
            }
        )
        if not child:
            issues.append(
                f"Sub-Application object {entry['id']} uses unsupported same-application mode"
            )
        elif not exists:
            issues.append(
                f"Sub-Application object {entry['id']} is missing companion {child_name!r}"
            )

    frames = [
        _frame_inventory(index, chunks, issues)
        for index, chunks in enumerate(frames_from(outer))
    ]
    embedded = embedded_modules(path)
    embedded_names = {module.filename.casefold() for module in embedded}
    missing_embedded = [
        module.filename
        for module in modules
        if module.filename.casefold() not in embedded_names
    ]
    if missing_embedded:
        issues.append(f"extension modules missing from embedded stream: {missing_embedded}")
    bank_chunks = {
        name: {
            "present": bool(matches := [c for c in outer if c.chunk_id == chunk_id]),
            "stored_bytes": sum(len(c.payload) for c in matches),
        }
        for chunk_id, name in BANK_NAMES.items()
    }

    return {
        "source": str(path),
        "file_bytes": path.stat().st_size,
        "application_name": app_name,
        "file_version": stamp.file_version_text if stamp else None,
        "product_version": stamp.product_version_text if stamp else None,
        "code_sha256": stamp.code_sha if stamp else None,
        "frames": frames,
        "frame_count": len(frames),
        "object_count": len(objects),
        "object_types": {str(key): type_counts[key] for key in sorted(type_counts)},
        "placement_count": sum(frame["placements"] for frame in frames),
        "event_count": sum(frame["events"] for frame in frames),
        "banks": bank_chunks,
        "module_slots": module_slots,
        "modules": [
            {"index": module.index, "filename": module.filename}
            for module in modules
        ],
        "embedded_modules": [module.filename for module in embedded],
        "subapplications": subapplications,
        "issues": issues,
        "elapsed_seconds": round(time.monotonic() - start, 3),
    }

def print_report(result: dict, verbose: bool = False) -> None:
    """Print that inventory in readable form."""
    build = result["file_version"] or "unknown"
    types = ",".join(
        f"{object_type}:{count}"
        for object_type, count in result["object_types"].items()
    )
    banks = ",".join(
        name for name, info in result["banks"].items() if info["present"]
    ) or "none"
    status = "OK" if not result["issues"] else "CHECK"
    print(
        f"{result['source']}: {status} build={build} frames={result['frame_count']} "
        f"objects={result['object_count']} placements={result['placement_count']} "
        f"events={result['event_count']} types={{{types}}} banks={banks} "
        f"modules={len(result['modules'])} embedded={len(result['embedded_modules'])} "
        f"({result['elapsed_seconds']:.3f}s)"
    )
    for issue in result["issues"]:
        print(f"  issue: {issue}")
    if verbose:
        for frame in result["frames"]:
            print(
                f"  frame {frame['index']}: {frame['width']}x{frame['height']} "
                f"placements={frame['placements']} events={frame['events']} "
                f"programs={frame['event_program_count']} "
                f"name={frame['name']!r}"
            )
        for module in result["modules"]:
            print(f"  module slot {module['index']}: {module['filename']}")
        for name in result["embedded_modules"]:
            print(f"  embedded: {name}")

def expand_inputs(paths: list[Path]) -> list[Path]:
    """Turn a path into the files to look at, recursing into folders."""
    exes: list[Path] = []
    for path in paths:
        if path.is_file():
            exes.append(path)
        elif path.is_dir():
            exes.extend(
                candidate
                for candidate in sorted(path.rglob("*"))
                if candidate.is_file() and candidate.suffix.casefold() == ".exe"
            )
        else:
            raise ValueError(f"input does not exist: {path}")
    return exes

def main() -> None:
    """Run the preflight from a command line."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--json", type=Path, help="write the complete result list")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    try:
        paths = expand_inputs(args.paths)
    except ValueError as error:
        parser.error(str(error))
    results = []
    failures = 0
    for path in paths:
        try:
            result = preflight(path)
        except Exception as error:
            failures += 1
            result = {
                "source": str(path),
                "fatal_error": f"{type(error).__name__}: {error}",
            }
            print(f"{path}: FAILED {result['fatal_error']}")
        else:
            print_report(result, args.verbose)
            failures += bool(result["issues"])
        results.append(result)

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(args.json)
    raise SystemExit(1 if failures else 0)
