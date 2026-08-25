# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""Spawn `klikback-cli --worker` and stream its NDJSON events to a callback.

The GUI never decompiles in-process: a worker is a child process, cancel is
`kill()`, and that is always safe because the pipelines never half-write an
output (a candidate that fails validation is preserved as `.failed.cca`).
This module is deliberately free of pywebview so the dev harness and tests
can drive it headlessly.
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path


def worker_command(paths: list[str], flags: list[str]) -> list[str]:
    """The command line for one worker batch.

    Frozen (PyInstaller): the console exe sitting beside this one, which is
    the shipped worker-process model. Development: this same interpreter
    running the CLI module (`spawn` puts the package root on PYTHONPATH).
    """
    if getattr(sys, "frozen", False):
        head = [str(Path(sys.executable).with_name("klikback-cli.exe"))]
    else:
        head = [sys.executable, "-m", "klikback.cli"]
    return head + list(paths) + ["--worker"] + flags


def option_flags(options: dict) -> list[str]:
    """GUI option dict -> CLI flags. Keys mirror `api.Options`; a missing
    key means the shipped default, so an empty dict is a default run."""
    flags: list[str] = []
    if options.get("out"):
        flags += ["--out", str(options["out"])]
    if options.get("per_game_folders"):
        flags.append("--per-game-folders")
    if options.get("force"):
        flags.append("--force")
    if not options.get("extract_extensions", True):
        flags.append("--no-extensions")
    if options.get("recover_comments"):
        flags.append("--recover-comments")
    if not options.get("application_icons", True):
        flags.append("--no-application-icons")
    if not options.get("ownerless_recovery", True):
        flags.append("--no-ownerless-recovery")
    if not options.get("subapplications", True):
        flags.append("--no-subapps")
    if not options.get("substitute_artwork", True):
        flags.append("--no-substitute-artwork")
    if options.get("repair_bank"):
        flags.append("--repair-bank")
    if options.get("repair_object_data"):
        flags.append("--repair-object-data")
    if options.get("drop_missing_assets"):
        flags.append("--drop-missing-assets")
    repack = options.get("repack_placement")
    if repack:
        # The checkbox means every level; the CLI's own optional level list
        # rides through for a caller that names them.
        flags.append("--repack-placement")
        if repack is not True and str(repack) != "all":
            flags.append(str(repack))
    for directory in options.get("extension_dirs") or []:
        flags += ["--extensions-dir", str(directory)]
    # MMF 2.0. Each family's folder goes only to its own flag: the 1.5
    # folder holds .cox files and the 2.0 folder .mfx files, and a folder
    # handed to the wrong engine is a scan that can only report "not
    # installed" for everything.
    if options.get("mmf2_extension_dir"):
        flags += ["--mmf2-extensions-dir", str(options["mmf2_extension_dir"])]
    if not options.get("section_labels", True):
        flags.append("--no-section-labels")
    for module in options.get("strip_extensions") or []:
        flags += ["--strip-extension", str(module)]
    # Per file, never per run: the window chooses which modules to remove
    # on each game's own card, and a batch of games shares nothing.
    for path, modules in (options.get("strip_for") or {}).items():
        for module in modules:
            flags += ["--strip-for", str(path), str(module)]
    return flags


def write_session_log(result: dict, options: dict) -> Path | None:
    """Write `<stem>.decompiled.log` beside the output -- GUI users have no
    console scrollback. A refusal has no output file, so its log lands in
    the same folder the output would have used. Logs are always replaced;
    the never-overwrite rule protects inputs and projects, not logs.

    Returns None when the user has turned logs off, which is the whole of
    that option: the decision lives here rather than at the two call sites
    so both homes cannot drift apart on it. The report is still on screen
    and still copyable either way -- what the option controls is whether a
    file is left behind."""
    if not options.get("session_log", True):
        return None
    source = Path(result["path"])
    if result.get("target"):
        # Beside whatever was actually written -- exact under every
        # output-folder option, because the engine resolved the path.
        out_dir = Path(result["target"]).parent
    else:
        out_dir = Path(options["out"]) if options.get("out") else source.parent
        if options.get("per_game_folders"):
            out_dir = out_dir / source.stem
    target = out_dir / f"{source.stem}.decompiled.log"
    lines = [
        f"KlikBack session log -- {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"input:   {source}",
        f"kind:    {result.get('kind')}",
        f"outcome: {result.get('outcome')}",
    ]
    if result.get("target"):
        lines.append(f"output:  {result['target']}")
    # The options that applied to THIS file -- its family's, not the whole
    # window's -- so a log read months later says what shaped it.
    if result.get("applied"):
        lines.append("")
        lines.append("options in force for this file:")
        lines += [f"  {line}" for line in result["applied"]]
    lines += ["", result.get("log", "").rstrip()]
    if result.get("advice"):
        lines += ["", f"note: {result['advice']}"]
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target


class WorkerProcess:
    """One decompile batch: the child process plus its reader threads.

    `on_event(dict)` receives each NDJSON object as it arrives;
    `on_end(returncode, stderr_text)` fires once, after the stream closes.
    Both are called from reader threads -- the caller marshals to its own
    UI thread (pywebview's `evaluate_js` already does).
    """

    def __init__(
        self,
        paths: list[str],
        options: dict,
        on_event: Callable[[dict], None],
        on_end: Callable[[int, str], None] | None = None,
    ) -> None:
        self.paths = [str(path) for path in paths]
        self.options = dict(options)
        self.on_event = on_event
        self.on_end = on_end
        self.process: subprocess.Popen | None = None
        self._stderr: list[str] = []

    def spawn(self) -> None:
        command = worker_command(self.paths, option_flags(self.options))
        environment = None
        if not getattr(sys, "frozen", False):
            import os

            environment = dict(os.environ)
            package_root = str(Path(__file__).resolve().parents[2])
            existing = environment.get("PYTHONPATH", "")
            environment["PYTHONPATH"] = (
                package_root + (os.pathsep + existing if existing else "")
            )
        creationflags = 0
        if sys.platform == "win32":
            # Never flash a console window under the windowed exe.
            creationflags = subprocess.CREATE_NO_WINDOW
        self.process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=environment,
            creationflags=creationflags,
        )
        threading.Thread(target=self._read_stdout, daemon=True).start()
        threading.Thread(target=self._read_stderr, daemon=True).start()

    def cancel(self) -> None:
        if self.process is not None and self.process.poll() is None:
            self.process.kill()

    @property
    def running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def _read_stdout(self) -> None:
        assert self.process is not None and self.process.stdout is not None
        for line in self.process.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except ValueError:
                # Never let one garbled line kill the stream; surface it.
                event = {"event": "noise", "text": line}
            self.on_event(event)
        returncode = self.process.wait()
        if self.on_end is not None:
            self.on_end(returncode, "".join(self._stderr))

    def _read_stderr(self) -> None:
        assert self.process is not None and self.process.stderr is not None
        for line in self.process.stderr:
            self._stderr.append(line)
