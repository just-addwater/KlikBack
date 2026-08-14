# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""Collect the licence notices the binary release has to carry.

KlikBack's own LICENSE covers KlikBack. The zip also bundles a Python
interpreter, pywebview and the .NET bridge it needs, OpenSSL, and several
Microsoft components -- and every one of those licences requires its notice
to travel with the binaries. Before this existed the release shipped two
licence files, one of which was an accident: a copy setuptools had vendored
into itself.

Two rules shape how it works.

**Nothing is written from memory.** Every licence text is copied verbatim
from a file already on disk -- the wheel's own licence, the interpreter's own
LICENSE.txt, a canonical Apache-2.0 text. A notices file containing a licence
somebody retyped is worse than no notices file, because it looks authoritative
and is not.

**An absence fails the build.** Each expected component names where its text
comes from; if a version bump moves or drops that file, this stops rather than
quietly shipping a release with a notice missing. The one component that ships
no licence text of its own is named explicitly, so "no file" can never be
mistaken for "not checked".
"""

from __future__ import annotations

import argparse
import importlib.metadata as metadata
import pathlib
import shutil
import sys
import sysconfig
import textwrap

#: Distributions whose code is inside the release. `pyinstaller` is here not
#: because the package ships, but because its bootloader is compiled into
#: both exes.
BUNDLED_WHEELS = [
    "pywebview",
    "pythonnet",
    "clr_loader",
    "setuptools",
    "cffi",
    "pyinstaller",
]

#: Bundled, and ships no licence file in its wheel. Its declared licence goes
#: in the index instead of a text -- named rather than silently absent.
WHEELS_WITHOUT_A_TEXT = {
    "proxy_tools": "MIT (declared in the package metadata; the wheel carries "
                   "no licence file)",
}

#: Where a bare licence name would mislead. PyInstaller is the one that
#: matters: its classifier says GPLv2, which next to Apache-2.0 OpenSSL reads
#: like a conflict, and the exception in its own COPYING.txt is what says
#: otherwise.
COMPONENT_NOTES = {
    "pyinstaller": "with the bootloader exception in its COPYING.txt, which "
                   "permits bundling with an application under any licence",
}

#: Components with no Python packaging at all. Each says where its text is
#: read from, so nothing here is transcribed.
#: (component, what it covers, licence, how to find the text)
NATIVE_COMPONENTS = [
    (
        "CPython",
        "python313.dll, the standard library, and the Windows build's own "
        "inclusions (libffi, and the C runtime stubs beside it)",
        "Python Software Foundation License Version 2",
        "interpreter",
    ),
    (
        "OpenSSL",
        "libcrypto-3.dll and libssl-3.dll, reached through _ssl.pyd",
        "Apache License 2.0",
        "apache",
    ),
]

#: Microsoft's components are redistributed under their own terms rather than
#: an open-source licence, so the index names them and points at the terms. A
#: URL in a text file is a reference, not a network call: KlikBack itself
#: still never touches the network.
MICROSOFT_COMPONENTS = [
    ("Microsoft Edge WebView2 components",
     "Microsoft.Web.WebView2.Core.dll, Microsoft.Web.WebView2.WinForms.dll "
     "and WebView2Loader.dll, vendored by pywebview",
     "https://developer.microsoft.com/microsoft-edge/webview2/"),
    (".NET runtime assemblies",
     "Python.Runtime.dll and the System.* assemblies, vendored by pythonnet",
     "https://dotnet.microsoft.com/"),
    ("Microsoft Visual C++ runtime",
     "VCRUNTIME140.dll, VCRUNTIME140_1.dll and the api-ms-win-* UCRT stubs, "
     "as redistributed with CPython",
     "https://learn.microsoft.com/cpp/windows/redistributing-visual-cpp-files"),
]

HEADER = """\
THIRD-PARTY NOTICES FOR KLIKBACK {version}
{rule}

KlikBack itself is under the GNU General Public License version 3 or later;
its text is in LICENSE, beside this file. KlikBack claims no rights in its
output -- see README.txt.

This release also bundles the components below. Each is used under its own
licence, and each licence text is in the licenses\\ folder next to this file,
copied verbatim from the component's own distribution.

"""


class NoticeMissing(Exception):
    """A licence text that was expected and is not there."""


def wrap(text: str) -> str:
    """One indented paragraph, hard-wrapped like the README beside it."""
    return textwrap.fill(text, width=72, initial_indent="    ",
                         subsequent_indent="    ")


def licence_files(name: str) -> list[pathlib.Path]:
    """Every licence-looking file a distribution ships, as real paths.

    Wheels put these in `<name>.dist-info/licenses/` these days and directly
    in `.dist-info/` before that, so both are matched; `COPYING` catches the
    GNU spelling that PyInstaller uses. Only the distribution's own files are
    considered -- a licence a package vendored from somebody else is that
    package's business, and one of those is how the release ended up carrying
    an `importlib_metadata` notice and nothing else.
    """
    dist = metadata.distribution(name)
    root = f"{dist.metadata['Name'].replace('-', '_').lower()}-{dist.version}"
    found = []
    for entry in dist.files or []:
        parts = [part.lower() for part in entry.parts]
        if not parts[0].startswith(root.split("-")[0]):
            continue
        if "dist-info" not in parts[0]:
            continue
        stem = parts[-1]
        if stem.startswith(("license", "licence", "copying", "notice")):
            found.append(pathlib.Path(dist.locate_file(entry)).resolve())
    return found


def canonical_apache_text() -> pathlib.Path:
    """A verbatim, unmodified Apache-2.0 text from the local environment.

    OpenSSL 3 is Apache-2.0 licensed but arrives as two bare DLLs with no
    text beside them. Rather than transcribe the licence, this takes a copy
    already on disk and checks it is the canonical one: the appendix
    boilerplate still says `[yyyy] [name of copyright owner]`, which a text
    somebody had adapted for their own project would not.
    """
    site = pathlib.Path(sysconfig.get_paths()["purelib"])
    for candidate in sorted(site.rglob("LICENSE*")):
        try:
            text = candidate.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        stripped = text.lstrip()
        if (stripped.startswith("Apache License")
                and "Version 2.0, January 2004" in stripped[:200]
                and "[yyyy] [name of copyright owner]" in text
                and "END OF TERMS AND CONDITIONS" in text):
            return candidate
    raise NoticeMissing(
        "no unmodified Apache-2.0 text found in this environment; OpenSSL's "
        "notice cannot be assembled without one"
    )


def interpreter_licence() -> pathlib.Path:
    """CPython's own LICENSE.txt, from the interpreter that built the zip."""
    path = pathlib.Path(sys.base_prefix) / "LICENSE.txt"
    if not path.is_file():
        raise NoticeMissing(f"the interpreter has no LICENSE.txt at {path}")
    return path


def collect(dist_root: pathlib.Path, version: str) -> list[str]:
    """Write licenses\\ and return the index's component lines."""
    out = dist_root / "licenses"
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    lines = []

    for name, covers, licence, source in NATIVE_COMPONENTS:
        origin = (interpreter_licence() if source == "interpreter"
                  else canonical_apache_text())
        target = out / f"{name}.txt"
        shutil.copyfile(origin, target)
        lines.append(f"{name}\n{wrap(covers)}\n{wrap(licence)}\n"
                     f"    licenses\\{target.name}")

    for name in BUNDLED_WHEELS:
        try:
            dist = metadata.distribution(name)
        except metadata.PackageNotFoundError as problem:
            raise NoticeMissing(f"{name} is not installed") from problem
        files = licence_files(name)
        if not files:
            raise NoticeMissing(
                f"{name} {dist.version} ships no licence file; if that is "
                f"correct for this version, move it to WHEELS_WITHOUT_A_TEXT "
                f"with its declared licence"
            )
        written = []
        for origin in files:
            suffix = "" if len(files) == 1 else f"-{origin.stem.lower()}"
            target = out / f"{name}-{dist.version}{suffix}.txt"
            shutil.copyfile(origin, target)
            written.append(f"licenses\\{target.name}")
        licence = declared(dist, files[0])
        if name in COMPONENT_NOTES:
            licence += ", " + COMPONENT_NOTES[name]
        lines.append(f"{name} {dist.version}\n{wrap(licence)}\n"
                     + "\n".join(f"    {w}" for w in written))

    for name, declaration in WHEELS_WITHOUT_A_TEXT.items():
        dist = metadata.distribution(name)
        lines.append(f"{name} {dist.version}\n{wrap(declaration)}")

    return lines


def declared(dist: metadata.Distribution, text: pathlib.Path | None) -> str:
    """What a distribution says its licence is, in its own words.

    Metadata first, and the licence file's own opening line as the last
    resort -- `clr_loader` declares nothing anywhere in its metadata, and
    reading the first line of the text it ships is still reading rather than
    assuming.
    """
    meta = dist.metadata
    expression = meta.get("License-Expression")
    if expression:
        return expression
    classifiers = [
        value.split("::")[-1].strip()
        for value in (meta.get_all("Classifier") or [])
        if value.startswith("License ::")
    ]
    if classifiers:
        return "; ".join(classifiers)
    inline = (meta.get("License") or "").strip()
    # Some wheels paste their whole licence into the field; the file beside
    # it is the copy that matters, so only a short value is worth quoting.
    if 0 < len(inline) <= 60:
        return inline
    if text is not None:
        for line in text.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.strip():
                return line.strip() + " (from the text it ships)"
    return "declared nowhere; see the text"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("dist_root", type=pathlib.Path,
                        help="the collected KlikBack folder to write into")
    parser.add_argument("--version", required=True)
    args = parser.parse_args(argv)

    if not args.dist_root.is_dir():
        print(f"no such folder: {args.dist_root}", file=sys.stderr)
        return 1
    try:
        components = collect(args.dist_root, args.version)
    except NoticeMissing as problem:
        print(f"third-party notices: {problem}", file=sys.stderr)
        return 1

    rule = "=" * (len(f"THIRD-PARTY NOTICES FOR KLIKBACK {args.version}"))
    body = [HEADER.format(version=args.version, rule=rule)]
    body += [line + "\n" for line in components]
    body.append(
        "\nThe components below are Microsoft's, redistributed under their own\n"
        "terms rather than an open-source licence. Their texts are not\n"
        "reproduced here; the references are where the terms are published.\n"
    )
    for name, covers, url in MICROSOFT_COMPONENTS:
        body.append(f"\n{name}\n{wrap(covers)}\n    {url}\n")

    index = args.dist_root / "THIRD-PARTY-NOTICES.txt"
    index.write_text("\n".join(body).replace("\n\n\n", "\n\n"),
                     encoding="utf-8", newline="\r\n")
    written = len(list((args.dist_root / "licenses").iterdir()))
    print(f"third-party notices: {written} licence texts, "
          f"{len(components) + len(MICROSOFT_COMPONENTS)} components")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
