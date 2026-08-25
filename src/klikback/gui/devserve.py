# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""Preview the KlikBack GUI in an ordinary browser -- no pywebview needed.

    py -3 -m klikback.gui.devserve [--port 8123] [--autorun] [paths...]

A stdlib HTTP bridge that serves `web/` and stands in for the pywebview JS
API: `app.js` detects the missing `window.pywebview` and talks to
`POST /api/<name>` instead, polling `GET /api/events` for worker events.
The worker process, the engine, the session log and the option flags are
all the real thing -- only the native window and its file dialogs are not,
so `browse` returns nothing here and paths arrive on the command line or
typed into the path box.

This is a development harness, not the product. The shipped GUI is the
pywebview shell in `shell.py`; keep the two behind the same `app.js`
bridge so what is proven here is what ships there.
"""

from __future__ import annotations

import argparse
import json
import queue
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from klikback import AUTHOR, PRODUCT, PROJECT_LINK, __version__, api
from klikback.gui import worker as worker_mod
from klikback.gui.shell import (
    WEB_DIR,
    measure_output,
    reveal,
    settings_path,
)

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".ico": "image/x-icon",
    ".woff2": "font/woff2",
    ".woff": "font/woff",
}


class Bridge:
    """The same surface `shell.Api` offers, minus native dialogs, with
    events queued for the page to poll instead of pushed by evaluate_js."""

    def __init__(self, autorun: list[str], autostart: bool) -> None:
        self.events: queue.Queue[dict] = queue.Queue()
        self.worker: worker_mod.WorkerProcess | None = None
        self.autorun = autorun
        self.autostart = autostart
        self._options: dict = {}

    def boot(self) -> dict:
        return {
            "product": PRODUCT,
            "version": __version__,
            "author": AUTHOR,
            "link": PROJECT_LINK,
            "settings": self.load_settings(),
            "autorun": self.autorun,
            "autostart": self.autostart,
            "harness": True,
        }

    def quit(self) -> None:
        pass  # the dev preview page has no window of its own to close

    def open_link(self, url: str) -> None:
        if url.startswith(("https://", "http://")):
            import webbrowser

            webbrowser.open(url)

    def set_title(self, title: str) -> None:
        pass  # the browser tab titles itself from document.title

    def inspect(self, path: str, mmf2_extensions_dir: str | None = None) -> dict:
        folder = Path(mmf2_extensions_dir) if mmf2_extensions_dir else None
        return api.inspect(Path(path), folder).as_dict()

    def expand(self, paths: list[str]) -> list[str]:
        return [str(p) for p in api.collect_targets([Path(p) for p in paths])]

    def open_folder(self, path: str) -> None:
        reveal(path)

    def written(self, result: dict) -> dict:
        return measure_output(result)

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
            pass

    def start(self, paths: list[str], options: dict) -> bool:
        if self.worker is not None and self.worker.running:
            return False
        self._options = dict(options)
        self.worker = worker_mod.WorkerProcess(
            paths, options, self._on_event, self._on_end
        )
        self.worker.spawn()
        return True

    def cancel(self) -> None:
        if self.worker is not None:
            self.worker.cancel()

    def drain(self) -> list[dict]:
        drained: list[dict] = []
        try:
            while True:
                drained.append(self.events.get_nowait())
        except queue.Empty:
            return drained

    def _on_event(self, event: dict) -> None:
        if event.get("event") == "result":
            try:
                log_path = worker_mod.write_session_log(event, self._options)
                if log_path is not None:
                    event = {**event, "session_log": str(log_path)}
            except OSError as problem:
                event = {**event, "session_log_error": str(problem)}
        self.events.put(event)

    def _on_end(self, returncode: int, stderr_text: str) -> None:
        self.events.put({
            "event": "end",
            "returncode": returncode,
            "stderr": stderr_text[-4000:],
        })


def make_handler(bridge: Bridge):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *ignored) -> None:
            pass  # keep the harness console quiet; events are the output

        def _json(self, payload, status=HTTPStatus.OK) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            if self.path == "/api/events":
                self._json(bridge.drain())
                return
            name = self.path.split("?", 1)[0].lstrip("/") or "index.html"
            target = (WEB_DIR / name).resolve()
            if not target.is_file() or WEB_DIR.resolve() not in target.parents:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            body = target.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header(
                "Content-Type",
                CONTENT_TYPES.get(target.suffix.lower(),
                                  "application/octet-stream"),
            )
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            try:
                arguments = json.loads(self.rfile.read(length) or b"[]")
            except ValueError:
                self._json({"error": "bad JSON"}, HTTPStatus.BAD_REQUEST)
                return
            if not self.path.startswith("/api/"):
                self._json({"error": "no such call"}, HTTPStatus.NOT_FOUND)
                return
            name = self.path[len("/api/"):]
            method = getattr(bridge, name, None)
            if method is None or name.startswith("_"):
                self._json({"error": "no such call"}, HTTPStatus.NOT_FOUND)
                return
            self._json(method(*arguments))

    return Handler


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*")
    parser.add_argument("--port", type=int, default=8123)
    parser.add_argument("--autorun", action="store_true",
                        help="load the given paths and start immediately")
    args = parser.parse_args(argv)

    bridge = Bridge(
        [str(Path(p).resolve()) for p in args.paths], args.autorun
    )
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(bridge))
    print(f"KlikBack dev preview: http://127.0.0.1:{args.port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
