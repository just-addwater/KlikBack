# GENERATED — do not edit by hand. This file is produced by KlikBack's
# sync tooling; changes belong in the source it is generated from.
#
# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""Say which build of MMF produced a standalone game.

A standalone is MMF's own runtime with the application appended, so the
runtime's Win32 version resource dates the build that made it. The resource
is found by its fixed signature rather than by walking the executable's
resource directory, because the signature is unambiguous and survives
whatever a packer did to the section layout.

**Two version numbers live in these files and they disagree**, so they are
both reported rather than blended: the product label and the file-version
resource can name different builds for the same release. Compare like with
like, and treat a mismatch as a fact about the file rather than an error.

Games override these fields freely — an author can stamp their own version
number over the runtime's — so this contributes a build number when its shape
matches and stays quiet when it does not. What the file actually *is* comes
from its own overlay, not from this stamp.
"""

from __future__ import annotations
import argparse
import hashlib
import struct
from dataclasses import dataclass
from pathlib import Path

FIXED_FILE_INFO_SIGNATURE = b"\xbd\x04\xef\xfe"

@dataclass(frozen=True)
class BuildStamp:
    """The version fields read out of a standalone, kept separate rather than merged.
    """
    file_version: tuple[int, int, int, int]
    product_version: tuple[int, int, int, int]
    strings: dict[str, str]
    code_sha: str | None = None

    @property
    def file_version_text(self) -> str:
        """The file version as the four numbers Windows shows."""
        return ".".join(str(part) for part in self.file_version)

    @property
    def product_version_text(self) -> str:
        """The product version as the four numbers Windows shows."""
        return ".".join(str(part) for part in self.product_version)

def _version_tuple(most: int, least: int) -> tuple[int, int, int, int]:
    return (most >> 16, most & 0xFFFF, least >> 16, least & 0xFFFF)

def version_strings(data: bytes, start: int, limit: int) -> dict[str, str]:
    """The human-readable version text an executable carries, if any."""
    wanted = (
        "CompanyName",
        "ProductName",
        "ProductVersion",
        "FileVersion",
        "FileDescription",
        "InternalName",
        "OriginalFilename",
    )
    found: dict[str, str] = {}
    window = data[start:limit]
    for key in wanted:
        needle = key.encode("utf-16-le")
        at = window.find(needle)
        if at < 0:
            continue
        tail = window[at + len(needle) : at + len(needle) + 256]
        text = tail.decode("utf-16-le", errors="replace")
        value = text.strip("\x00").split("\x00")[0].strip()
        if value:
            found[key] = value
    return found

def code_fingerprint(data: bytes) -> str | None:
    """A stable digest of the runtime's own code, for telling builds apart when the
    version fields are missing or have been overwritten.
    """
    try:
        lfanew = struct.unpack_from("<I", data, 0x3C)[0]
        if data[lfanew : lfanew + 4] != b"PE\0\0":
            return None
        sections = struct.unpack_from("<H", data, lfanew + 6)[0]
        optional_size = struct.unpack_from("<H", data, lfanew + 20)[0]
        table = lfanew + 24 + optional_size
        for index in range(sections):
            entry = table + index * 40
            name = data[entry : entry + 8].rstrip(b"\0")
            if name != b".text":
                continue
            raw_size, raw_pointer = struct.unpack_from("<II", data, entry + 16)
            body = data[raw_pointer : raw_pointer + raw_size]
            if body:
                return hashlib.sha256(body).hexdigest()
    except (struct.error, IndexError):
        return None
    return None

def build_stamp(path: Path) -> BuildStamp | None:
    """The build this executable was produced by, as far as its resources admit.
    """
    data = path.read_bytes()
    at = data.find(FIXED_FILE_INFO_SIGNATURE)
    code = code_fingerprint(data)
    if at < 0:
        if code is None:
            return None
        return BuildStamp((0, 0, 0, 0), (0, 0, 0, 0), {}, code)
    file_ms, file_ls, prod_ms, prod_ls = struct.unpack_from("<4I", data, at + 8)
    return BuildStamp(
        file_version=_version_tuple(file_ms, file_ls),
        product_version=_version_tuple(prod_ms, prod_ls),
        strings=version_strings(data, at, at + 0x1000),
        code_sha=code,
    )

def main() -> None:
    """Print the build identification from a command line."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument(
        "--group", action="store_true", help="summarise by distinct version"
    )
    args = parser.parse_args()

    files = [p for p in args.paths if p.is_file()]
    results: list[tuple[Path, BuildStamp | None]] = []
    for path in files:
        try:
            results.append((path, build_stamp(path)))
        except Exception as error:
            print(f"{path.name}: FAILED {type(error).__name__}: {error}")

    if args.group:
        groups: dict[tuple[str, str], list[str]] = {}
        for path, stamp in results:
            key = (
                (stamp.file_version_text, (stamp.code_sha or "")[:16])
                if stamp
                else ("<no version resource>", "")
            )
            groups.setdefault(key, []).append(path.name)
        for (file_version, product), names in sorted(
            groups.items(), key=lambda item: -len(item[1])
        ):
            print(f"file={file_version} code={product}: {len(names)} file(s)")
            for name in sorted(names)[:6]:
                print(f"    {name}")
            if len(names) > 6:
                print(f"    ... and {len(names)-6} more")
        return

    for path, stamp in results:
        if stamp is None:
            print(f"{path.name}: no version resource")
            continue
        description = stamp.strings.get("FileDescription", "")
        print(
            f"{path.name}: file={stamp.file_version_text} "
            f"product={stamp.product_version_text} "
            f"code={(stamp.code_sha or '-')[:16]}  {description}"
        )
