"""Fail the build when the version is not the same in all four places.

The version is hand-kept in three files and read by two different consumers:
`build.bat` takes `klikback.__version__` for the zip's filename, while
PyInstaller takes `version_info.txt` for the exe's Windows version resource.
A partial bump therefore does not fail -- it ships, as a `KlikBack-0.9.2.zip`
whose Properties dialog says 0.9.1, which is worse than either number being
wrong on its own because each artifact looks internally consistent.

Run before freezing, so a mismatch costs a second rather than a build.

Every field is looked up **by name and asserted to have been found**. A guard
that silently checks nothing when a field is renamed is the failure this file
exists to prevent, one level up: it would keep printing a pass while covering
one carrier fewer. `missing` is therefore an error, not a skip.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

BUILD = Path(__file__).resolve().parent
PUBLIC = BUILD.parent

INIT = PUBLIC / "src" / "klikback" / "__init__.py"
VERSION_INFO = BUILD / "version_info.txt"
README = BUILD / "README.txt"

# label -> (file, pattern). Each pattern must capture the version, and each
# must match at least once.
FIELDS = (
    ("__version__", INIT, r'^__version__ = "([0-9]+\.[0-9]+\.[0-9]+)"'),
    ("filevers", VERSION_INFO, r"filevers=\((\d+, \d+, \d+), 0\)"),
    ("prodvers", VERSION_INFO, r"prodvers=\((\d+, \d+, \d+), 0\)"),
    ("FileVersion", VERSION_INFO, r"StringStruct\('FileVersion', '([^']+)'\)"),
    ("ProductVersion", VERSION_INFO, r"StringStruct\('ProductVersion', '([^']+)'\)"),
    # Deliberately "title line": the shorter word for it is rejected by the
    # release checks that run before this file is packaged, so do not tidy it.
    ("README.txt title line", README, r"^KlikBack ([0-9]+\.[0-9]+\.[0-9]+)\s*$"),
)


def normalise(raw: str) -> str:
    """`0, 9, 2` and `0.9.2` are the same version written two ways."""
    return raw.replace(", ", ".").strip()


def main() -> int:
    found: dict[str, str] = {}
    missing: list[str] = []
    for label, path, pattern in FIELDS:
        if not path.exists():
            missing.append(f"{label}: {path} does not exist")
            continue
        matches = re.findall(
            pattern, path.read_text(encoding="utf-8"), re.MULTILINE
        )
        if not matches:
            missing.append(f"{label}: no match for {pattern!r} in {path.name}")
            continue
        distinct = {normalise(match) for match in matches}
        if len(distinct) != 1:
            missing.append(f"{label}: disagrees with itself -- {sorted(distinct)}")
            continue
        found[label] = distinct.pop()

    if missing:
        print("version guard: a carrier could not be read --", file=sys.stderr)
        for line in missing:
            print(f"  {line}", file=sys.stderr)
        print(
            "  a field that cannot be found is not a field that agrees; fix "
            "the pattern or the file before building",
            file=sys.stderr,
        )
        return 1

    versions = set(found.values())
    if len(versions) != 1:
        print("version guard: the version is not the same everywhere --", file=sys.stderr)
        for label, version in found.items():
            print(f"  {version:<10} {label}", file=sys.stderr)
        print(
            "  build.bat names the zip from __version__ and PyInstaller stamps "
            "the exe from version_info.txt, so this would ship as a zip and an "
            "exe claiming different versions",
            file=sys.stderr,
        )
        return 1

    version = versions.pop()
    print(f"version guard: {version} in all {len(found)} places "
          f"({', '.join(found)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
