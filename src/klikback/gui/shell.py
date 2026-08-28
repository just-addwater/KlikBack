# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""KlikBack's window: a pywebview shell over `web/`.

The shell owns four things and no more: the native window, the native file
dialogs, the settings file, and the worker process. Everything the user
sees is `web/index.html` + `app.js`; everything that decompiles is the CLI
worker. pywebview is imported inside `main()` so that importing this
module never requires it (the dev harness and the tests do not).

Startup degrades politely: a missing pywebview, or a window that will not
start, shows a plain message box with the actual error and what to do about
it, instead of a traceback -- and never blames a component the error did
not name.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import subprocess
import sys
from pathlib import Path

from klikback import AUTHOR, PRODUCT, PROJECT_LINK, __version__, api
from klikback.gui import worker as worker_mod

WEB_DIR = Path(__file__).resolve().parent / "web"

WEBVIEW2_LINK = "https://developer.microsoft.com/microsoft-edge/webview2/"

FILE_TYPES = (
    "Clickteam games (*.exe;*.gam;*.cca;*.ccn)",
    "All files (*.*)",
)

DEFAULT_SIZE = (780, 680)
MIN_SIZE = (640, 540)


def app_folder() -> Path:
    """Where KlikBack itself lives: the exe's folder when frozen, the
    `public/` root in development."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[3]


def settings_path() -> Path:
    """`klikback.json` beside the exe -- the portable-zip rule: no
    registry, no AppData. In development it sits at the `public/` root."""
    return app_folder() / "klikback.json"


#: The .NET assembly the window's toolkit loads, relative to the app
#: folder. Windows marking THIS ONE file is enough to stop the window; see
#: `blocked_by_windows`.
RUNTIME_ASSEMBLY = Path("_internal") / "pythonnet" / "runtime" / "Python.Runtime.dll"


def carries_web_mark(path: Path) -> bool:
    """Whether Windows has marked this file as downloaded.

    The mark is an alternate data stream named `Zone.Identifier`, which
    opens like a file whose name is `<path>:Zone.Identifier` and is simply
    absent otherwise. Anything that is not a plain readable NTFS file
    answers False: a mark that cannot be read is not a mark this can
    report on."""
    try:
        with open(f"{path}:Zone.Identifier", "rb"):
            return True
    except OSError:
        return False


def unblock_own_files(folder: Path) -> tuple[int, int]:
    """Clear the downloaded-from-the-internet mark from KlikBack's own
    files. Returns `(cleared, could not clear)`.

    **Why a program is entitled to do this to itself.** The mark exists so
    that a person decides, knowingly, whether to run something that came
    off the internet. That decision has already been made and acted on by
    the time this runs: Windows put SmartScreen in front of `KlikBack.exe`
    and somebody chose Run anyway. What is cleared here is the payload of
    the very program now executing, inside its own folder -- nothing the
    user has not already consented to run, and nothing outside it. Without
    this, the ordinary way to get KlikBack (download the zip, extract it
    with Explorer) produces an app whose window cannot open at all.

    **It is never done without being asked.** The caller puts a yes/no
    box up first, once per folder, defaulting to No -- because removing
    this mark is also what malware does to hide where it came from
    (ATT&CK T1553.005), and an unsigned program that strips it unasked has
    earned any suspicion it attracts. Asked and answered, it is the same
    operation as the Unblock tickbox in the folder's own Properties.

    Deliberately narrow: only files under `folder`, only the
    `Zone.Identifier` stream, and only ever removing it -- no attributes,
    no permissions, no content. Anything that will not clear is counted
    and left, and `blocked_by_windows` then reports it in full.
    """
    cleared = stuck = 0
    for path in folder.rglob("*"):
        if not path.is_file() or not carries_web_mark(path):
            continue
        try:
            os.remove(f"{path}:Zone.Identifier")
            cleared += 1
        except OSError:
            stuck += 1
    return cleared, stuck


def blocked_by_windows(folder: Path) -> str | None:
    """A plain account of the download mark that stops KlikBack's window,
    or None when nothing is marked.

    **This replaces the parenthesis notice, and it is the same defect.**
    Release 1.0.0 would not open its window from `KlikBack-1.0.0 (1)`,
    while the command line in the same folder worked, and the folder name
    was blamed for two releases. It was never the name. `(1)` is what a
    browser calls a SECOND DOWNLOAD, a browser download is what carries
    the Mark of the Web, and Explorer stamps that mark onto every file it
    extracts from such a zip -- so the parenthesis was a fingerprint of
    where the folder came from, not a cause. That is why the same build
    opened from four parenthesised folders when it was tested with a zip
    that had never been through a browser.

    Measured 2026-08-25, single variable, on one machine, both ways: the
    mark on `Python.Runtime.dll` ALONE is enough to produce
    `RuntimeError: Failed to resolve Python.Runtime.Loader.Initialize`,
    and removing it is enough to fix it. The command line is untouched
    either way, because it is pure standard library and never loads that
    assembly.

    Reached when the mark is still there after the offer to clear it: the
    user said no, or clearing failed on a read-only folder or a network
    share. Either way the window is about to fail, so this names the file
    and the fix by hand.
    """
    assembly = folder / RUNTIME_ASSEMBLY
    if not carries_web_mark(assembly):
        return None
    marked = sum(1 for path in folder.rglob("*")
                 if path.is_file() and carries_web_mark(path))
    return (
        "Windows has marked KlikBack's files as downloaded from the "
        f"internet ({marked} of them), which stops the window from "
        "opening:\n"
        f"    {assembly}\n\n"
        "That happens when a zip is downloaded with a browser and then "
        "extracted, because the mark travels to every file inside. The "
        "window needs to load that file and Windows will not let it.\n\n"
        "To fix it, in either order:\n"
        "  * right-click the folder, choose Properties, and tick Unblock "
        "if it is offered; or\n"
        "  * right-click the ZIP first, Properties, Unblock, then extract "
        "it again into a new folder.\n\n"
        "klikback-cli.exe in the same folder is not affected and works "
        "now."
    )


def startup_failure_text(problem: BaseException) -> str:
    """What to tell someone whose window did not start: the error itself,
    first and verbatim, then only the advice that error supports.

    The shipped message used to assert that the WebView2 runtime was
    missing whatever had actually failed, with the real error as an
    afterthought in parentheses -- so a .NET loader fault sent people off
    to install a browser component and nothing changed. WebView2 is named
    as the cause only when the error names it; otherwise it is one thing
    to check, after the error and after the folder name."""
    detail = f"{type(problem).__name__}: {problem}"
    text = f"KlikBack could not start its window.\n\nThe error was:\n    {detail}"
    blocked = blocked_by_windows(app_folder())
    if blocked is not None:
        # Named right under the error, and before WebView2 is mentioned at
        # all: when the files are marked, this IS the explanation, and the
        # measured fix is two clicks away.
        text += "\n\n" + blocked
    mentions_webview = any(
        word in str(problem).lower()
        for word in ("webview2", "webview", "microsoft edge", "edge runtime"))
    if mentions_webview:
        text += (
            "\n\nThis names the Microsoft Edge WebView2 runtime, which "
            "KlikBack's window needs and which ships with up-to-date "
            f"Windows 10 and 11. Install it from:\n    {WEBVIEW2_LINK}"
        )
    else:
        text += (
            "\n\nIf that does not explain it: KlikBack's window needs the "
            "Microsoft Edge WebView2 runtime (part of every up-to-date "
            f"Windows 10 and 11), available from\n    {WEBVIEW2_LINK}\n"
            "and the command line, klikback-cli.exe in the same folder, "
            "works without the window. Otherwise this is worth reporting, "
            f"with the error above, at:\n    {PROJECT_LINK}"
        )
    return text


def reveal(path: str) -> None:
    """Show an output in Explorer -- a file selected inside its folder, a
    folder simply opened. Shared with the dev harness so both homes behave
    the same.

    Explorer is asked directly rather than through `os.startfile`, because
    ShellExecute puts an extension-less path through its program search
    first: a folder named `Game` sitting beside `Game.exe` -- exactly what
    `--per-game-folders` writes next to the input -- launches the game
    instead of opening the folder. The command line is one string, not an
    argument list, because Popen's quoting wraps the whole `/select,...`
    switch and Explorer then reads it as a single unknown path: any output
    whose name contains a space silently opens nothing at all.
    """
    where = Path(path)
    if where.is_file():
        folder, argument = where.parent, f'/select,"{where}"'
    else:
        folder = where if where.is_dir() else where.parent
        argument = f'"{folder}"'
    if not folder.is_dir():
        return  # the output was moved or deleted since the run
    explorer = Path(os.environ.get("WINDIR") or r"C:\Windows") / "explorer.exe"
    try:
        subprocess.Popen(f'"{explorer}" {argument}')  # noqa: S603 -- fixed path
    except OSError:
        try:
            # No Explorer where it should be. The trailing separator is what
            # keeps ShellExecute's program search off the folder path.
            os.startfile(f"{folder}{os.sep}")  # noqa: S606
        except OSError:
            pass  # showing the output is a convenience; never fail over it


def measure_output(result: dict) -> dict:
    """How much a finished file actually put on disk, as bytes and a count.

    Three shapes are counted and no others: the rebuilt project itself, the
    extension modules carved into `<stem>_cox` / `<stem>_gox` (or, for a
    2.0 game, `<stem>.extracted`) beside it, and the session log. Never the whole output folder -- the default output
    folder is the game's own, and weighing that would report the user's
    game collection back at them as if KlikBack had written it. The cost of
    being that careful is that a 1.5 game with external sub-applications
    undercounts by its children, which is the safer way round.

    Shared with the dev harness so both homes report the same number.
    """
    target = result.get("target")
    if not target:
        return {"bytes": 0, "files": 0}
    target = Path(target)
    stem = target.stem
    # A stripped 2.0 recovery carries a second marker after the suffix,
    # so it comes off first.
    if stem.endswith(".stripped"):
        stem = stem[: -len(".stripped")]
    suffix = api.Options().suffix  # ".decompiled", one source of truth
    if stem.endswith(suffix):
        stem = stem[: -len(suffix)]
    wanted = [target]
    for carved in (f"{stem}_cox", f"{stem}_gox", f"{stem}.extracted"):
        folder = target.parent / carved
        if folder.is_dir():
            wanted += [found for found in folder.rglob("*") if found.is_file()]
    if result.get("session_log"):
        wanted.append(Path(result["session_log"]))
    total = 0
    counted = 0
    for path in wanted:
        try:
            total += path.stat().st_size
        except OSError:
            continue  # moved or deleted since the run; do not claim it
        counted += 1
    return {"bytes": total, "files": counted}


# -- remembering where the window was ----------------------------------------


class _WindowBox:
    """The window's last ordinary size and position.

    pywebview reports both in logical pixels, the same units
    `create_window` takes, so what is recorded here goes straight back in
    next launch with no conversion. A maximised or minimised window is
    skipped rather than recorded: storing the screen's own size as though
    the user had dragged the window that big would make the next launch
    open a full-screen KlikBack nobody asked for.
    """

    def __init__(self) -> None:
        self.box: dict[str, int] = {}
        self.previous: dict[str, int] = {}
        self.ordinary = True

    def attach(self, window) -> None:
        try:
            window.events.resized += self._resized
            window.events.moved += self._moved
            window.events.maximized += self._unusual
            window.events.minimized += self._unusual
            window.events.restored += self._ordinary
        except Exception:
            pass  # an older pywebview without these events just forgets

    def _resized(self, width, height) -> None:
        if self.ordinary:
            self.box["width"], self.box["height"] = int(width), int(height)

    def _moved(self, x, y) -> None:
        if not self.ordinary:
            return
        self.previous = dict(self.box)
        self.box["x"], self.box["y"] = int(x), int(y)

    def _unusual(self) -> None:
        # Maximising moves the window to the screen corner and only then
        # reports its new state, so the position just recorded is that
        # corner rather than where the user had it. Step back one.
        if self.ordinary and self.previous:
            self.box = self.previous
        self.ordinary = False

    def _ordinary(self) -> None:
        self.ordinary = True


def _screen_bounds() -> tuple[int, int, int, int] | None:
    """The whole virtual desktop, in the logical pixels pywebview places
    windows with. The metrics come back in physical pixels because the
    process is DPI-aware, so they are divided by the system scale.
    Approximate by design: this only has to answer "is that box still
    somewhere a mouse can reach", not lay anything out."""
    try:
        metric = ctypes.windll.user32.GetSystemMetrics
        scale = (ctypes.windll.user32.GetDpiForSystem() or 96) / 96.0
        left, top = metric(76), metric(77)   # SM_X/YVIRTUALSCREEN
        span_x, span_y = metric(78), metric(79)  # SM_CX/CYVIRTUALSCREEN
        if span_x <= 0 or span_y <= 0:
            return None
        return (int(left / scale), int(top / scale),
                int(span_x / scale), int(span_y / scale))
    except Exception:
        return None


def restore_geometry(saved: dict) -> dict:
    """A remembered window box as `create_window` keyword arguments.

    Anything that no longer makes sense is dropped rather than corrected.
    The position in particular is only honoured while enough of the title
    bar still lands on a monitor that exists: a window restored onto a
    second screen that has since been unplugged is a window nobody can
    reach, and letting Windows place it is the recoverable answer.
    """
    geometry: dict = {}
    try:
        width, height = int(saved.get("width", 0)), int(saved.get("height", 0))
    except (TypeError, ValueError):
        return {}
    if width >= MIN_SIZE[0] and height >= MIN_SIZE[1]:
        geometry["width"], geometry["height"] = width, height
    try:
        x, y = int(saved["x"]), int(saved["y"])
    except (KeyError, TypeError, ValueError):
        return geometry
    bounds = _screen_bounds()
    if bounds is None:
        return geometry  # cannot check, so do not gamble with the position
    left, top, span_x, span_y = bounds
    if (left - 16 <= x <= left + span_x - 120
            and top - 16 <= y <= top + span_y - 40):
        geometry["x"], geometry["y"] = x, y
    return geometry


def _brand_title_bar(window) -> None:
    """Paint the native title bar KlikBack navy where the OS allows it.
    `DWMWA_CAPTION_COLOR` exists on Windows 11 only; on Windows 10 the
    call fails and the window simply keeps the stock caption."""
    if sys.platform != "win32":
        return
    try:
        hwnd = int(window.native.Handle.__int__())
        dwm = ctypes.windll.dwmapi
        for attribute, colour in (
            (35, 0x00600000),  # DWMWA_CAPTION_COLOR, BGR: navy
            (36, 0x00FFFFFF),  # DWMWA_TEXT_COLOR, BGR: white
        ):
            dwm.DwmSetWindowAttribute(
                hwnd, attribute,
                ctypes.byref(ctypes.c_uint32(colour)), 4,
            )
    except Exception:
        pass  # cosmetics only; never let them near startup


def _message_box(title: str, text: str) -> None:
    if sys.platform == "win32":
        ctypes.windll.user32.MessageBoxW(None, text, title, 0x10)
    else:
        print(f"{title}: {text}", file=sys.stderr)


def _ask_yes_no(title: str, text: str) -> bool:
    """A yes/no box, defaulting to NO. False anywhere there is no desktop
    to ask on, because the answer to "may I change something on your
    disk?" when nobody can be asked is no."""
    if sys.platform != "win32":
        return False
    # MB_YESNO | MB_ICONQUESTION | MB_DEFBUTTON2 -- No is the default
    # button, so a reflexive Enter declines rather than consents.
    answer = ctypes.windll.user32.MessageBoxW(None, text, title, 0x4 | 0x20 | 0x100)
    return answer == 6  # IDYES


class Api:
    """The JS bridge: every method here is callable as
    `window.pywebview.api.<name>(...)` from `app.js`."""

    def __init__(self, autorun: list[str], autostart: bool) -> None:
        self._window = None
        self._worker: worker_mod.WorkerProcess | None = None
        self._autorun = autorun
        self._autostart = autostart
        self._box = _WindowBox()

    def attach(self, window) -> None:
        self._window = window
        self._box.attach(window)

    def on_drop(self, event: dict) -> None:
        """Files dropped on the window. Registered through pywebview's DOM
        API because that is the only path where dropped files carry their
        real full paths (`pywebviewFullPath`); a plain JS listener never
        sees them."""
        files = (event.get("dataTransfer") or {}).get("files") or []
        paths = [f.get("pywebviewFullPath") for f in files]
        paths = [p for p in paths if p]
        if paths:
            self._push({"event": "dropped", "paths": paths})

    # -- lifecycle ---------------------------------------------------------

    def boot(self) -> dict:
        """Everything the page needs to draw itself, in one call."""
        return {
            "product": PRODUCT,
            "version": __version__,
            "author": AUTHOR,
            "link": PROJECT_LINK,
            "settings": self.load_settings(),
            "autorun": self._autorun,
            "autostart": self._autostart,
        }

    def quit(self) -> None:
        if self._window is not None:
            self._window.destroy()

    def open_link(self, url: str) -> None:
        """Open a page in the user's own browser -- only ever web links."""
        if url.startswith(("https://", "http://")):
            import webbrowser

            webbrowser.open(url)

    def set_title(self, title: str) -> None:
        """Track the run in the window title, so a KlikBack left minimised
        through a long decompile still reports from the taskbar. Cosmetic:
        a shell that will not retitle is not worth an error."""
        try:
            if self._window is not None:
                self._window.set_title(title)
        except Exception:
            pass

    # -- inspection and dialogs -------------------------------------------

    def inspect(self, path: str, mmf2_extensions_dir: str | None = None) -> dict:
        folder = Path(mmf2_extensions_dir) if mmf2_extensions_dir else None
        return api.inspect(Path(path), folder).as_dict()

    def expand(self, paths: list[str]) -> list[str]:
        """Folders become their candidate files, exactly as the CLI walks
        them, so the queue shows what a batch will actually touch."""
        return [str(p) for p in api.collect_targets([Path(p) for p in paths])]

    def browse_files(self) -> list[str]:
        import webview

        chosen = self._window.create_file_dialog(
            webview.OPEN_DIALOG, allow_multiple=True, file_types=FILE_TYPES
        )
        return [str(path) for path in (chosen or [])]

    def browse_folder(self) -> str | None:
        import webview

        chosen = self._window.create_file_dialog(webview.FOLDER_DIALOG)
        return str(chosen[0]) if chosen else None

    def open_folder(self, path: str) -> None:
        reveal(path)

    def written(self, result: dict) -> dict:
        return measure_output(result)

    def save_log(self, text: str, suggested: str) -> str | None:
        import webview

        chosen = self._window.create_file_dialog(
            webview.SAVE_DIALOG, save_filename=suggested
        )
        if not chosen:
            return None
        target = Path(chosen if isinstance(chosen, str) else chosen[0])
        target.write_text(text, encoding="utf-8")
        return str(target)

    # -- settings ----------------------------------------------------------

    def load_settings(self) -> dict:
        try:
            loaded = json.loads(settings_path().read_text(encoding="utf-8"))
            return loaded if isinstance(loaded, dict) else {}
        except (OSError, ValueError):
            return {}

    def save_settings(self, settings: dict) -> None:
        try:
            settings_path().write_text(
                json.dumps(settings, indent=2), encoding="utf-8"
            )
        except OSError:
            pass  # a read-only folder must never break the app over cosmetics

    def remember_window(self) -> None:
        """Store where the window ended up, on the way out. The settings
        are re-read rather than reused so the page's own last save -- the
        options, the output folder, the recent list -- is not overwritten
        with whatever this process happened to load at startup."""
        if not self._box.box:
            return  # never moved or resized: nothing to say
        try:
            settings = self.load_settings()
            settings["window"] = dict(self._box.box)
            self.save_settings(settings)
        except Exception:
            pass  # closing time; nothing here is worth delaying it

    # -- the worker --------------------------------------------------------

    def start(self, paths: list[str], options: dict) -> bool:
        if self._worker is not None and self._worker.running:
            return False
        self._options = dict(options)
        self._worker = worker_mod.WorkerProcess(
            paths, options, self._dispatch, self._ended
        )
        self._worker.spawn()
        return True

    def cancel(self) -> None:
        if self._worker is not None:
            self._worker.cancel()

    def _dispatch(self, event: dict) -> None:
        if event.get("event") == "result":
            try:
                log_path = worker_mod.write_session_log(event, self._options)
                if log_path is not None:
                    event = {**event, "session_log": str(log_path)}
            except OSError as problem:
                event = {**event, "session_log_error": str(problem)}
        self._push(event)

    def _ended(self, returncode: int, stderr_text: str) -> None:
        self._push({
            "event": "end",
            "returncode": returncode,
            "stderr": stderr_text[-4000:],
        })

    def _push(self, event: dict) -> None:
        if self._window is not None:
            self._window.evaluate_js(f"kb.onEvent({json.dumps(event)})")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="KlikBack")
    parser.add_argument("paths", nargs="*",
                        help="game files to load into the queue on startup")
    parser.add_argument("--autorun", action="store_true",
                        help="start decompiling the given paths immediately "
                             "(used by the automated smoke test)")
    parser.add_argument("--debug", action="store_true",
                        help="open the WebView devtools")
    args = parser.parse_args(argv)

    try:
        import webview
    except ImportError:
        if getattr(sys, "frozen", False):
            _message_box(
                PRODUCT,
                "This KlikBack build is incomplete: its window library "
                "(pywebview) was not bundled. Please re-download KlikBack, "
                f"or report this at:\n    {PROJECT_LINK}",
            )
        else:
            _message_box(
                PRODUCT,
                "This development checkout is missing the pywebview package "
                "(the shipped app bundles it).\n\nInstall it with:\n"
                "    py -3 -m pip install pywebview",
            )
        return 1

    bridge = Api([str(Path(p).resolve()) for p in args.paths], args.autorun)
    settings = bridge.load_settings()

    # The download mark stops the .NET loader, so it has to go before the
    # loader runs -- but removing it is a change to files on the user's
    # disk, and stripping the mark is also a thing malware does to hide
    # where it came from. So KlikBack ASKS, once per folder, and does
    # nothing at all unless the answer is yes (user's call, 2026-08-25).
    # Declining is remembered so it is asked once and not on every launch;
    # the window then fails, and its message names the manual fix.
    folder = app_folder()
    if blocked_by_windows(folder) is not None:
        if settings.get("unblock_declined") == str(folder):
            pass
        elif _ask_yes_no(PRODUCT, (
            "Windows has marked KlikBack's own files as downloaded from "
            "the internet, and that stops its window from opening. It "
            "happens when a zip is downloaded with a browser and then "
            "extracted with Explorer.\n\n"
            "Clear that mark from KlikBack's own files?\n"
            f"    {folder}\n\n"
            "This is the same thing as right-clicking that folder, "
            "choosing Properties and ticking Unblock. Nothing outside "
            "the folder is touched, and no file's contents change.\n\n"
            "If you choose No, the window will not open, but "
            "klikback-cli.exe still works."
        )):
            unblock_own_files(folder)
        else:
            settings["unblock_declined"] = str(folder)
            bridge.save_settings(settings)

    # Whatever would not clear -- a read-only folder, a network share, or
    # a person who said no -- is still worth naming, because the window is
    # about to fail.
    blocked = blocked_by_windows(folder)
    if blocked is not None and settings.get("blocked_notice") != str(folder):
        _message_box(PRODUCT, blocked + "\n\nKlikBack will now try to "
                     "open its window anyway.")
        settings["blocked_notice"] = str(folder)
        bridge.save_settings(settings)

    geometry = restore_geometry(settings.get("window") or {})
    try:
        window = webview.create_window(
            f"{PRODUCT} {__version__}",
            str(WEB_DIR / "index.html"),
            js_api=bridge,
            width=geometry.get("width", DEFAULT_SIZE[0]),
            height=geometry.get("height", DEFAULT_SIZE[1]),
            # Absent means "put it where you like" -- which is what a first
            # run, or a saved position that no longer lands on a screen,
            # both want.
            x=geometry.get("x"),
            y=geometry.get("y"),
            min_size=MIN_SIZE,
        )
        bridge.attach(window)

        def shown() -> None:
            _brand_title_bar(window)

        def loaded() -> None:
            try:
                window.dom.document.events.drop += bridge.on_drop
            except Exception as problem:
                print(f"drop registration failed: {problem}", file=sys.stderr)

        def closing() -> None:
            bridge.remember_window()

        window.events.shown += shown
        window.events.loaded += loaded
        window.events.closing += closing
        webview.start(debug=args.debug)
    except Exception as problem:
        _message_box(PRODUCT, startup_failure_text(problem))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
