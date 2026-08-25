# GENERATED — do not edit by hand. This file is produced by KlikBack's
# sync tooling; changes belong in the source it is generated from.
#
# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""Compare the extension modules a game was built with against the installed ones.

A compiled game carries the exact module binaries it was built against. The
editor does not use those: it loads whatever is installed in its own
extensions folder, and renders each extension's conditions, actions and
expressions **by position** in that module's tables.

So a rebuild can be perfect and the event editor still show the wrong
expression — or nothing at all where a position no longer exists — simply
because the installed module is a different release from the one the game was
built with. That failure looks like a decompiler bug and is not one, which is
the whole reason this report exists.

It only runs when an extensions folder has been named. With nothing to
compare against, every module reads as "not installed" and the report is
noise rather than information.
"""

from __future__ import annotations
import hashlib
from pathlib import Path
from klikback.core.common.extension_binaries import embedded_modules
from klikback.core.common.cox_titles import CoxProblem, RT_MENU, resource_entries

def digest(data: bytes) -> str:
    """A stable identity for a module, for telling two builds of it apart."""
    return hashlib.sha256(data).hexdigest()

def installed_module(name: str, directories: list[Path]) -> Path | None:
    """The installed copy of one module, if this machine has it."""
    wanted = name.casefold()
    for directory in directories:
        if not directory.is_dir():
            continue
        for candidate in sorted(directory.iterdir()):
            if candidate.is_file() and candidate.name.casefold() == wanted:
                return candidate
    return None

def ace_menus(image: bytes) -> dict[int, int] | None:
    """The conditions, actions and expressions a module offers, in order."""
    try:
        return {
            tag[1]: size
            for tag, _offset, size in resource_entries(image)
            if tag[0] == RT_MENU
        }
    except CoxProblem:
        return None

def menu_comparison(embedded: bytes, installed: bytes) -> dict:
    """Where two versions of a module's tables agree and where they diverge.

    A module's actions, conditions and expressions are numbered, and a project
    refers to them by number. So the comparison that matters runs in one direction
    only: an installed module with **more** entries than the build the game was
    compiled against is harmless, and one with **fewer** is not, because a number
    the game uses may be past the end of the table the editor is reading.

    That is the one finding worth acting on, and it is reported per menu with both
    sizes so it can be judged rather than merely believed. Identical tables and a
    larger installed set are stated too, but as reassurance.

    A module carrying no menus at all is reported as saying nothing rather than as
    agreeing — the runtime build of a module has none, and treating an empty table
    as a match would call every such comparison a pass.
    """
    theirs, ours = ace_menus(embedded), ace_menus(installed)
    if theirs is None or ours is None:
        return {
            "menu_state": "unreadable",
            "unreadable_side": "embedded" if theirs is None else "installed",
        }
    if not theirs:

        return {"menu_state": "embedded has no menus"}
    undersized = {
        str(menu): [ours.get(menu, 0), size]
        for menu, size in theirs.items()
        if ours.get(menu, 0) < size
    }
    return {
        "menu_state": "undersized" if undersized else (
            "identical" if ours == theirs else "installed is a superset"
        ),
        "embedded_menus": {str(k): v for k, v in sorted(theirs.items())},
        "installed_menus": {str(k): v for k, v in sorted(ours.items())},
        "undersized": undersized,
    }

def compare(exe: Path, directories: list[Path]) -> dict:
    """Compare a game's modules against the installed ones, module by module.

    For every extension the game carries: is the copy installed on this machine the
    same file, a different one, or not there at all. Decided by hashing the
    contents, not by trusting a name or a date.

    This is what separates a rebuild that is byte-correct from one that *displays*
    correctly. The editor does not store the name of an action or an expression in
    the project — it stores a number, and renders it by looking that number up in
    the module it has installed. So a different installed build can show the wrong
    expression for a rebuild in which nothing at all is wrong. The file is right;
    the thing reading it disagrees.

    Which is why the menus are compared as well as the bytes. Differing bytes are
    common and usually harmless — a newer build of a module with the same tables
    reads a project identically. The difference that actually breaks is a menu that
    has got *smaller*.

    Nothing installed is opened for any purpose but reading it to hash, and nothing
    is written back. The report is a report.
    """
    modules = []
    for module in embedded_modules(exe):
        name = Path(module.filename).name
        installed = installed_module(name, directories)
        record = {
            "module": name,
            "embedded_size": len(module.image),
            "embedded_sha256": digest(module.image),
            "installed_path": str(installed) if installed else None,
        }
        if installed is None:
            record["state"] = "not installed"
            record["menu_state"] = "not installed"
        else:
            image = installed.read_bytes()
            record["installed_size"] = len(image)
            record["installed_sha256"] = digest(image)
            record["state"] = (
                "same" if image == module.image else "differs"
            )
            record.update(menu_comparison(module.image, image))
        modules.append(record)
    return {
        "exe": str(exe),
        "extension_directories": [str(one) for one in directories],
        "modules": modules,
        "same": sum(1 for one in modules if one["state"] == "same"),
        "differs": sum(1 for one in modules if one["state"] == "differs"),
        "missing": sum(1 for one in modules if one["state"] == "not installed"),
        "undersized": sum(
            1 for one in modules if one.get("menu_state") == "undersized"
        ),
    }

def menu_report_line(result: dict) -> str | None:
    """The detail line naming what moved between two versions of a module."""
    undersized = [
        one for one in result["modules"] if one.get("menu_state") == "undersized"
    ]
    unreadable = [
        one["module"] for one in result["modules"]
        if one.get("menu_state") == "unreadable"
    ]
    parts = []
    if undersized:
        detail = "; ".join(
            f"{one['module']} menu {menu} is {have} bytes against the game's "
            f"{want}"
            for one in undersized
            for menu, (have, want) in sorted(one["undersized"].items())
        )
        parts.append(
            f"ACE MENUS UNDERSIZED in {len(undersized)} installed module(s) -- "
            f"the editor may crash rendering these rows, and installing the "
            f"game's own editor build of each is the fix: {detail}"
        )
    if unreadable:
        parts.append(
            f"ACE menus could not be compared for {', '.join(sorted(unreadable))} "
            "(packed or unreadable resources) -- absence of a finding here is "
            "not evidence"
        )
    return "  ".join(parts) if parts else None

def report_line(result: dict) -> str:
    """One module's result, in the words the report prints."""
    total = len(result["modules"])
    if not total:
        return "modules: none embedded"
    drifted = [
        one["module"] for one in result["modules"] if one["state"] != "same"
    ]
    if not drifted:
        return f"modules: all {total} match the installed .cox"
    return (
        f"modules: {len(drifted)} of {total} differ from the installed .cox "
        f"({', '.join(sorted(drifted))}) -- a digest difference alone is weak "
        f"evidence (a PE timestamp counts); the ACE-menu check below is the one "
        f"with a direction"
    )
