# -*- mode: python ; coding: utf-8 -*-
"""KlikBack PyInstaller spec: two exes over one shared _internal/.

KlikBack.exe is the windowed GUI, klikback-cli.exe the console CLI (and
the GUI's worker process). Both are thin entries over the same package,
frozen one-folder -- no unpack-to-temp cold start, fewer AV false
positives than one-file. The engine's package-relative artwork lookup and
the GUI's web/ assets ship as data at the paths the code already resolves,
so nothing is patched for freezing.

Build with build.bat (which runs the sync gate first on a research
checkout) or directly:

    py -3 -m PyInstaller --noconfirm klikback.spec
"""

import os

SRC = os.path.join(SPECPATH, "..", "src")
ICON = os.path.join(SPECPATH, "..", "branding", "KlikBack.ico")
VERSION_FILE = os.path.join(SPECPATH, "version_info.txt")
RUNTIME_HOOKS = [os.path.join(SPECPATH, "hook_artwork.py")]

# Where the frozen modules' own Path(__file__) formulas resolve.
ARTWORK_DATA = [(os.path.join(SRC, "klikback", "core", "artwork"),
                 "klikback/core/artwork")]
WEB_DATA = [(os.path.join(SRC, "klikback", "gui", "web"),
             "klikback/gui/web")]

# pywebview's Windows backend is loaded dynamically, so name it here.
GUI_HIDDEN = [
    "webview",
    "webview.platforms.edgechromium",
    "webview.platforms.winforms",
    "clr_loader",
    "pythonnet",
]

# Weight that arrives through the module graph and is never used. KlikBack
# imports none of these itself; they come in behind pywebview, whose default
# HTTP server is a vendored bottle that names gevent inside server adapters
# we never reach. Each was removed on its own and the frozen window relaunched
# before the next was tried, because an exclusion pywebview needs while it
# picks a backend fails at startup rather than at build time.
#
# `ssl` is deliberately NOT here, and neither is the 6.2 MB OpenSSL pair
# behind it: `webview/__init__.py` does `import webview.http`, which imports
# `ssl` at module level, so a build without it cannot open a window at all.
# That is the whole of the "can the OpenSSL pair go" question, answered by
# reading rather than by a failed build.
EXCLUDES = [
    "tkinter",      # ~7.8 MB of Tcl/Tk data and DLLs; nothing imports it
    "_tkinter",
    "gevent",       # ~2.2 MB; only ever named by bottle's GeventServer
    "greenlet",
    "_testcapi",    # CPython's own test modules
    "_testinternalcapi",
]

# Payload pywebview brings that a 64-bit Windows build cannot reach. Worth
# more than its 14 KB: every binary in the zip is a component whose licence
# has to be accounted for in THIRD-PARTY-NOTICES.txt.
#
# The arm64 and x86 `runtimes/*/native/WebView2Loader.dll` were tried here
# too, and MUST NOT BE. Measured, twice each way: with both present the
# frozen window starts (exit 0), with either one missing it fails before it
# opens (exit 1) -- on x64, which uses neither. The loader is resolved
# through the whole RID tree, so an incomplete `runtimes/` folder breaks the
# resolution rather than falling back to the architecture actually running.
# Restoring one of the two is not enough; it takes both. That is 269 KB
# bought back for a startup that works, and it is exactly the failure the
# excludes list warns about: it happens at launch, never at build time.
UNREACHABLE = (
    "webview/lib/pywebview-android.jar",
)

def without_unreachable(entries):
    """Drop the UNREACHABLE payload from a TOC, whichever way it is spelled."""
    return [
        entry for entry in entries
        if not any(entry[0].replace("\\", "/").endswith(name)
                   for name in UNREACHABLE)
    ]

a_gui = Analysis(
    [os.path.join(SPECPATH, "entry_gui.py")],
    pathex=[SRC],
    datas=ARTWORK_DATA + WEB_DATA,
    hiddenimports=GUI_HIDDEN,
    runtime_hooks=RUNTIME_HOOKS,
    excludes=EXCLUDES,
    noarchive=False,
)

a_cli = Analysis(
    [os.path.join(SPECPATH, "entry_cli.py")],
    pathex=[SRC],
    datas=ARTWORK_DATA,
    hiddenimports=[],
    runtime_hooks=RUNTIME_HOOKS,
    excludes=EXCLUDES,
    noarchive=False,
)

pyz_gui = PYZ(a_gui.pure)
pyz_cli = PYZ(a_cli.pure)

exe_gui = EXE(
    pyz_gui,
    a_gui.scripts,
    [],
    exclude_binaries=True,
    name="KlikBack",
    console=False,
    icon=ICON,
    version=VERSION_FILE,
    upx=False,
)

exe_cli = EXE(
    pyz_cli,
    a_cli.scripts,
    [],
    exclude_binaries=True,
    name="klikback-cli",
    console=True,
    icon=ICON,
    version=VERSION_FILE,
    upx=False,
)

coll = COLLECT(
    exe_gui,
    without_unreachable(a_gui.binaries),
    without_unreachable(a_gui.datas),
    exe_cli,
    without_unreachable(a_cli.binaries),
    without_unreachable(a_cli.datas),
    name="KlikBack",
    upx=False,
)
