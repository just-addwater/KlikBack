/* KlikBack's page logic. One bridge abstraction covers both homes:
 * inside the pywebview shell (window.pywebview.api, events pushed via
 * kb.onEvent) and inside the dev harness (fetch /api/<name>, events
 * polled from /api/events). Everything below the bridge is identical in
 * both, which is what makes the harness a real test of the product UI. */

"use strict";

/* ---------------------------------------------------------- the bridge */

const bridge = {
  mode: null, // "pywebview" | "http"

  async call(name, ...args) {
    if (this.mode === "pywebview") {
      return window.pywebview.api[name](...args);
    }
    const response = await fetch("/api/" + name, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(args),
    });
    if (!response.ok) throw new Error(name + ": " + response.status);
    return response.json();
  },

  async detect() {
    if (window.pywebview && window.pywebview.api) {
      this.mode = "pywebview";
      return;
    }
    /* Deterministic, not timed: only the dev harness answers
     * /api/events. The native bridge can take seconds to appear on a
     * cold machine (.NET spin-up), so racing it against a fixed
     * timeout misclassifies the shell as the harness. */
    let harness = false;
    try {
      harness = (await fetch("/api/events")).ok;
    } catch (ignored) { /* file:// origin or no server: the shell */ }
    if (!harness) {
      await new Promise((resolve) => {
        if (window.pywebview && window.pywebview.api) { resolve(); return; }
        window.addEventListener("pywebviewready", resolve, { once: true });
      });
      this.mode = "pywebview";
      return;
    }
    this.mode = "http";
    setInterval(async () => {
      try {
        const events = await (await fetch("/api/events")).json();
        events.forEach((event) => kb.onEvent(event));
      } catch (ignored) { /* harness gone; nothing to poll */ }
    }, 150);
  },
};

/* ------------------------------------------------------------ the state */

const state = {
  files: [],            // {path, name, inspection, status, result, losses}
  selected: null,       // a path
  running: false,
  cancelling: false,
  harness: false,
  doneCount: 0,
  sawResult: false,
  blocked: null,        // a setup problem that stopped the run before it began
  progressNow: 0,       // the monotonic floor within the current file
  overallNow: 0,        // the monotonic floor of the bar, across the run
  totalFiles: 0,        // how many files this run will report on
  settings: {},
  runStartedAt: 0,      // when the whole run started, for the final tally
  statusBase: "",       // the status line without its animated ellipsis
  tick: 0,              // heartbeat counter, drives the ellipsis
  ticker: null,         // the heartbeat interval, only while a run is going
  fileStartedAt: 0,     // when the current file started, for the clock
  filePosition: "",     // "file 2 of 5", only when a batch is running
  batchName: "",        // the game being worked on, named only in a batch
};

const el = (id) => document.getElementById(id);

const STAGE_TEXT = {
  events: "Reading events…",
  banks: "Rebuilding banks…",
  frames: "Rebuilding frames…",
  validate: "Validating the output…",
  write: "Writing…",
  levels: "Restoring levels…",
  layout: "Laying out the file…",
};

const LOOP_NOUN = { frames: "Frame", levels: "Level" };

/* Each stage owns a band of the bar, so the fill climbs once per file
 * instead of sprinting to 100% for every stage. The weights are rough
 * shares of real decompile time; exactness matters less than motion in
 * one direction. */
const STAGE_BANDS = {
  events: [0.02, 0.15],
  banks: [0.15, 0.35],
  frames: [0.35, 0.90],
  validate: [0.90, 0.97],
  write: [0.97, 1],
  levels: [0.02, 0.85],
  layout: [0.85, 0.97],
};

const BANNER_ICON = {
  "kb-good": "✓",
  "kb-expected": "⚠",
  "kb-bad": "✖",
  "kb-neutral": "ℹ",
};

const CHIP_CLASS = {
  built: "kb-chip-good",
  refused: "kb-chip-warn",
  invalid: "kb-chip-bad",
  failed: "kb-chip-bad",
  error: "kb-chip-bad",
  "working…": "kb-chip-run",
};

/* Some losses are simply what compiling a game does: the compiler throws
 * the editor pictures, the comment text and the page ownership away, so
 * EVERY compiled game is missing them and no tool can bring them back.
 * Those are presented as expected, in their own quiet box, and are not
 * counted against the game. The engine's wording is never altered --
 * this is presentation-side triage only. */
const EXPECTED_LOSS_KINDS = [
  {
    pattern: /preview thumbnail|icon artwork|object icon|icon's own pixels|application icons cannot be recovered|editor icon/i,
    label: "Icons and preview pictures",
    why: "editor-only artwork the compiler never stored",
  },
  {
    pattern: /comment row|comment position/i,
    label: "Comment text",
    why: "the compiler kept the row numbers but threw the words away",
  },
  {
    pattern: /global event|ownerless|OWNER UNKNOWN|flattened into the frame|behaviour/i,
    label: "Global events and behaviours",
    why: "all recovered and working — every event is present and runs " +
      "exactly as before; only the name of the page it was filed under " +
      "is gone, so each one sits in its frame behind a clear label",
  },
  {
    pattern: /extension module title/i,
    label: "Extension display names",
    why: "games store which extension files they use but often not the " +
      "names shown in the editor; KlikBack recovers a name where it can " +
      "and otherwise uses the filename — the extension itself works " +
      "either way",
  },
];

function classifyLosses(losses) {
  const expected = new Map();
  const notable = [];
  for (const line of losses) {
    const kind = EXPECTED_LOSS_KINDS.find((k) => k.pattern.test(line));
    if (kind) {
      if (!expected.has(kind)) expected.set(kind, []);
      expected.get(kind).push(line);
    } else {
      notable.push(line);
    }
  }
  return { expected, notable };
}

// A refused incomplete copy has no losses to list -- nothing ran -- so the
// Details block was hidden in exactly the case somebody opens it wondering
// what to do. This is the advice line's suggestion said where it was looked
// for, and it names where the control lives. Keyed the same way the facade
// keys that advice, so the two cannot drift apart.
function detailsNote(result) {
  if (result.kind === "tgf-damaged" && result.outcome === "refused") {
    return "Nothing was rebuilt, so there is nothing to list here yet. " +
      "To open this copy anyway, tick “TGF/CnC: open an incomplete copy” " +
      "under Recovery options and decompile again. It drops the assets " +
      "whose bytes are not in the file and leaves everything else alone.";
  }
  return "";
}

const BANNERS = {
  built: ["kb-good", (r) => "Decompiled — " + basename(r.target)],
  // A refusal usually means the engine met something it will not
  // reconstruct wrongly. An incomplete copy is refused for the opposite
  // reason -- nothing about the game is the problem, the file is short of
  // bytes -- so it says so rather than blaming a feature.
  refused: ["kb-expected", (r) => r.kind === "tgf-damaged"
    ? "This copy of the game is incomplete."
    : "This game uses a feature that cannot be reconstructed correctly."],
  invalid: ["kb-bad", () =>
    "The reconstruction failed its own validation."],
  failed: ["kb-bad", () => "Something unexpected went wrong."],
  error: ["kb-bad", () => "Something unexpected went wrong."],
  skipped: ["kb-neutral", () =>
    "The output already exists — nothing was overwritten."],
  "nothing-to-do": ["kb-neutral", () => "Nothing to decompile."],
};

function basename(path) {
  return path ? String(path).split(/[\\/]/).pop() : "";
}

function fileByPath(path) {
  return state.files.find((file) => file.path === path);
}

/* ------------------------------------------------------- queue and card */

async function addPaths(paths) {
  let expanded = [];
  try {
    expanded = await bridge.call("expand", paths);
  } catch (problem) {
    setStatus("Could not read that: " + problem.message);
    return;
  }
  for (const path of expanded) {
    if (fileByPath(path)) continue;
    const inspection = await bridge.call("inspect", path);
    state.files.push({
      path,
      name: basename(path),
      inspection,
      status: inspection.decompilable ? "ready" : "—",
      result: null,
      losses: [],
    });
    state.selected = path;
  }
  renderQueue();
  renderSelected();
  updateButtons();
  saveRecents(expanded);
}

function renderQueue() {
  const wrap = el("queue-wrap");
  wrap.classList.toggle("kb-hidden", state.files.length === 0);
  // The well is an invitation, and it has been accepted: with files in the
  // list it collapses to its buttons and gives the height back.
  el("drop-well").classList.toggle("kb-compact", state.files.length > 0);
  // Only a list you can click between needs the card to hold still.
  el("inspect-card").classList.toggle("kb-steady", state.files.length > 1);
  const body = el("queue-body");
  body.textContent = "";
  for (const file of state.files) {
    const row = document.createElement("tr");
    row.classList.toggle("kb-selected", file.path === state.selected);
    // The cells are one line each and elide, so the full path lives here
    // -- along with the two things the row can do, which used to be a
    // tooltip on the panel that no longer has one.
    row.dataset.tip = file.path +
      "\nDouble-click a finished file to open its output folder; " +
      "Delete takes the selected one off the list.";
    [file.name, file.inspection.product].forEach((text) => {
      const cell = document.createElement("td");
      cell.textContent = text;
      row.appendChild(cell);
    });
    const statusCell = document.createElement("td");
    statusCell.className = "kb-status-cell";
    const chip = document.createElement("span");
    chip.className = "kb-chip " + (CHIP_CLASS[file.status] || "kb-chip-neutral");
    let statusText = file.status;
    if (file.result) {
      const { notable } = classifyLosses(file.losses);
      if (notable.length) {
        statusText += " · " + notable.length + " to review";
      }
    }
    chip.textContent = statusText;
    statusCell.appendChild(chip);
    row.appendChild(statusCell);

    // One row at a time, so the list is no longer all-or-nothing with
    // Clear. Disabled during a run: the worker was handed a fixed list of
    // paths and cannot be told to forget one.
    const removeCell = document.createElement("td");
    removeCell.className = "kb-remove-cell";
    if (!state.running) {
      const cross = document.createElement("span");
      cross.className = "kb-remove";
      cross.textContent = "×";
      cross.dataset.tip = "Take " + file.name + " off the list. " +
        "The file on disk is not touched.";
      cross.addEventListener("click", (event) => {
        event.stopPropagation();  // removing is not also selecting
        removeFile(file.path);
      });
      removeCell.appendChild(cross);
    }
    row.appendChild(removeCell);

    row.addEventListener("click", () => {
      state.selected = file.path;
      renderQueue();
      renderSelected();
    });
    row.addEventListener("dblclick", () => {
      const where = file.result &&
        (file.result.target || file.result.session_log);
      if (where) bridge.call("open_folder", where);
    });
    body.appendChild(row);
  }
  const any1996 = state.files.some(
    (file) => file.inspection.kind.startsWith("tgf"));
  el("options-1996").classList.toggle("kb-hidden", !any1996);
}

/* Take one file off the list -- the row's × and the Delete key share this.
 * The selection moves to whatever takes the removed row's place, so holding
 * Delete walks down the list instead of stopping dead after one press. */
function removeFile(path) {
  if (state.running) return;
  const at = state.files.findIndex((file) => file.path === path);
  if (at < 0) return;
  const [gone] = state.files.splice(at, 1);
  if (state.selected === path) {
    const next = state.files[Math.min(at, state.files.length - 1)];
    state.selected = next ? next.path : null;
  }
  renderQueue();
  renderSelected();
  updateButtons();
  if (state.files.length) {
    setStatus("Removed " + gone.name + " — " + state.files.length +
      " file" + (state.files.length === 1 ? "" : "s") + " left.");
  } else {
    setProgress(null);
    setStatus("Ready");
  }
}

function renderSelected() {
  const file = fileByPath(state.selected);
  const card = el("inspect-card");
  if (!file) {
    card.classList.add("kb-hidden");
    el("result-pane").classList.add("kb-hidden");
    return;
  }
  card.classList.remove("kb-hidden");
  el("inspect-title").textContent = file.name;
  const iconBox = el("inspect-icon");
  iconBox.textContent = "";
  if (file.inspection.icon) {
    const img = document.createElement("img");
    img.src = file.inspection.icon;
    img.alt = "";
    img.addEventListener("load", () => sizeIcon(img));
    iconBox.appendChild(img);
  } else {
    iconBox.textContent = "🕹️";
  }
  const inspection = file.inspection;
  const box = el("inspect-lines");
  box.textContent = "";

  const line = (cls, text) => {
    const div = document.createElement("div");
    div.className = cls;
    if (text !== undefined) div.textContent = text;
    box.appendChild(div);
    return div;
  };

  line("kb-inspect-head", inspection.product);
  if (inspection.name) {
    const title = line("kb-inspect-title");
    const label = document.createElement("span");
    label.className = "kb-label";
    label.textContent = "Title ";
    title.appendChild(label);
    title.appendChild(document.createTextNode(inspection.name));
  }
  // Which folder it came from, shortened the same way the Recent menu
  // shortens: two games in a batch can share a name, and this is the only
  // thing on screen that tells them apart.
  const where = line("kb-inspect-where", shortenPath(file.path));
  where.dataset.tip = file.path;

  /* Build, size and protection used to be a comma-list read as a
   * sentence; they are three separate answers, so they get three tags a
   * reader can land on one at a time. Protection is the one that changes
   * what happens next, so it is the one that is coloured. */
  const facts = line("kb-facts");
  const fact = (text, cls, tip) => {
    const tag = document.createElement("span");
    tag.className = "kb-fact" + (cls ? " " + cls : "");
    tag.textContent = text;
    if (tip) tag.dataset.tip = tip;
    facts.appendChild(tag);
  };
  if (inspection.build) fact("build " + inspection.build);
  fact(sizeText(inspection.size));
  // Only the 1996 families report protection at all, so the tooltip can
  // say what it means for them without hedging. It is worth saying: the
  // word looks like a warning, and here it is the ordinary case.
  if (inspection.protected !== null && inspection.protected !== undefined) {
    fact(inspection.protected ? "protected" : "not protected",
      inspection.protected ? "kb-fact-warn" : "",
      inspection.protected
        ? "The game's data is scrambled so the editor cannot open it. " +
          "That is normal for a game published in this era, and KlikBack " +
          "unscrambles it — nothing extra is needed from you."
        : "The game's data is stored plainly, so there is nothing to " +
          "unscramble. It still needs rebuilding into a project.");
  }

  // An incomplete copy gets a tag rather than the "no" colour: it is a game
  // KlikBack reads, held up by a decision about the assets that are missing
  // rather than by anything it cannot do.
  if (inspection.kind === "tgf-damaged") {
    fact("incomplete copy", "kb-fact-warn",
      "The file stops partway through its last sound or image bank — " +
      "what an interrupted download leaves behind. Everything before that " +
      "point is intact, so ticking “TGF/CnC: open an incomplete copy” " +
      "rebuilds it without the assets whose bytes are missing.");
  }

  // A Clickteam game from a generation this cannot read carries its own
  // verdict in its first note, so that note gets the "no" colour and the
  // stranger line below is left off: two sentences saying the same thing
  // read as though the second one added something.
  inspection.notes.forEach((note, index) => {
    const verdict = inspection.kind === "fusion2" && index === 0;
    line("kb-inspect-note" + (verdict ? " kb-inspect-nope" : ""), note);
  });
  inspection.companions.forEach((companion) => {
    const found = line("kb-inspect-note");
    const tick = document.createElement("span");
    tick.className = "kb-tick";
    // A search that found nothing says so in its own sentence; a tick in
    // front of it would be claiming the opposite.
    tick.textContent = /^(No|\d)/.test(companion) ? "·" : "✓";
    if (tick.textContent === "·") tick.classList.add("kb-tick-none");
    found.appendChild(tick);
    found.appendChild(document.createTextNode(companion));
  });
  // "Not a Clickteam game" is the wrong sentence for a Clickteam game that
  // is merely too new, and pointing its owner at the signature list would
  // send them after a file that is perfectly fine.
  if (!inspection.decompilable && inspection.kind !== "fusion2") {
    line("kb-inspect-note kb-inspect-nope",
      "This doesn’t look like a decompilable Clickteam game — " +
      "the signatures checked are listed above.");
  }
  renderResult(file);
}

/* How big to draw a game's own icon in a 64px frame.
 *
 * Pixel art only survives being enlarged by whole numbers -- at 1.5x some
 * pixels become two and their neighbours stay one, which is exactly the
 * mush the icon was drawn to avoid. Nearly every game of this era carries
 * a 32, so doubling it fills the frame and shows the author's own pixels
 * unchanged. Anything already bigger than the frame is shrunk instead,
 * and shrinking is the one direction that wants smoothing. */
function sizeIcon(img) {
  const natural = img.naturalWidth || 32;
  const drawn = natural * 2 <= 64 ? natural * 2 : Math.min(natural, 64);
  img.style.width = drawn + "px";
  img.style.height = drawn + "px";
  img.style.imageRendering = natural <= 64 ? "pixelated" : "auto";
}

function sizeText(bytes) {
  if (!bytes) return "empty file";
  if (bytes < 1024 * 1024) return Math.round(bytes / 1024) + " KB";
  return (bytes / (1024 * 1024)).toFixed(1) + " MB";
}

/* How much was written, not just where.
 *
 * The banner names the rebuilt file and Open folder shows it, but neither
 * says whether anything of substance came out -- and the weight is the one
 * number a user cannot get without going and looking. The page cannot read
 * a filesystem, so the shell measures; the answer is cached on the file so
 * clicking between queue rows does not re-walk the carved folder. */
async function measureOutput(file) {
  if (!file.result || !file.result.target) return;
  try {
    file.written = await bridge.call("written", file.result);
  } catch (ignored) {
    return;  // the output moved under us; the line simply stays away
  }
  if (state.selected === file.path) renderResult(file);
}

function writtenText(written) {
  if (!written || !written.files) return "";
  return "Wrote " + sizeText(written.bytes) + " across " + written.files +
    " file" + (written.files === 1 ? "" : "s") + ".";
}

/* ----------------------------------------------------------- the result */

function renderResult(file) {
  const pane = el("result-pane");
  if (!file || !file.result) {
    pane.classList.add("kb-hidden");
    return;
  }
  pane.classList.remove("kb-hidden");
  const result = file.result;
  const [cls, text] = BANNERS[result.outcome] ||
    ["kb-neutral", () => result.outcome];
  el("result-banner").className = "kb-banner " + cls;
  el("result-banner-icon").textContent = BANNER_ICON[cls] || "";
  el("result-banner-text").textContent =
    BANNERS[result.outcome] ? text(result) : String(result.outcome);

  // What happened and how much are one statement, so the size line is the
  // banner's second line rather than a separate note further down.
  const writtenNote = el("result-written");
  const writtenLine = writtenText(file.written);
  writtenNote.textContent = writtenLine;
  writtenNote.classList.toggle("kb-hidden", !writtenLine);

  const advice = el("result-advice");
  advice.textContent = result.advice || "";
  advice.classList.toggle("kb-hidden", !result.advice);

  const openButton = el("open-folder-button");
  const where = result.target || result.session_log;
  openButton.classList.toggle("kb-hidden", !where);
  openButton.onclick = () => bridge.call("open_folder", where);

  el("session-log-note").textContent = result.session_log
    ? "Log saved beside the output: " + basename(result.session_log)
    : (result.session_log_error
      ? "Session log could not be written: " + result.session_log_error : "");

  const lossDetails = el("loss-details");
  const noteText = detailsNote(result);
  const note = el("loss-note");
  note.textContent = noteText;
  note.classList.toggle("kb-hidden", !noteText);
  lossDetails.classList.toggle("kb-hidden",
    file.losses.length === 0 && !noteText);
  const { expected, notable } = classifyLosses(file.losses);
  const expectedCount =
    [...expected.values()].reduce((n, lines) => n + lines.length, 0);
  // The summary is generated from counts, so the note-only case needs a
  // line of its own rather than a count of nothing.
  el("loss-summary").textContent = notable.length
    ? "Details — " + notable.length + " thing" +
      (notable.length === 1 ? "" : "s") + " worth reading" +
      (expectedCount ? " (and " + expectedCount + " expected)" : "")
    : expectedCount
      ? "Details — " + expectedCount + " expected compile loss" +
        (expectedCount === 1 ? "" : "es") + " (normal)"
      : "Details — what to try next";
  const list = el("loss-list");
  list.textContent = "";
  for (const loss of notable) {
    const item = document.createElement("li");
    item.textContent = loss;
    list.appendChild(item);
  }
  const expectedBox = el("expected-losses");
  expectedBox.textContent = "";
  expectedBox.classList.toggle("kb-hidden", expectedCount === 0);
  if (expectedCount) {
    const note = document.createElement("div");
    note.className = "kb-expected-note";
    note.textContent =
      "These are normal. Compiling a game throws this content away for " +
      "good, so every compiled game is missing it whatever decompiles " +
      "it; KlikBack writes safe stand-ins where it can.";
    expectedBox.appendChild(note);
    for (const [kind, lines] of expected) {
      const group = document.createElement("details");
      const summary = document.createElement("summary");
      summary.textContent =
        kind.label + " — " + kind.why + " (" + lines.length + ")";
      group.appendChild(summary);
      const items = document.createElement("ul");
      for (const line of lines) {
        const item = document.createElement("li");
        item.textContent = line;
        items.appendChild(item);
      }
      group.appendChild(items);
      expectedBox.appendChild(group);
    }
  }
  el("log-text").textContent = result.log || "";

  el("save-log-button").onclick = async () => {
    const saved = await bridge.call(
      "save_log", logFileText(file), file.name + ".log");
    if (saved) setStatus("Saved " + shortenFile(saved));
  };
  el("save-log-button").disabled = state.harness;

  el("copy-log-button").onclick = async () => {
    setStatus(await copyText(logFileText(file))
      ? "Report copied to the clipboard."
      : "The clipboard refused the report — use Save log instead.");
  };
}

/* Save log needs a native dialog and so is dead in the dev preview; Copy
 * log works in both homes, which makes it the quicker path to a report
 * somebody can paste into an issue. Both origins KlikBack runs from
 * (file:// in the shell, 127.0.0.1 in the harness) count as secure, so the
 * async clipboard is available; the execCommand path is there for the
 * WebView2 that disagrees. */
async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch (ignored) { /* no permission, or no clipboard API at all */ }
  const scratch = document.createElement("textarea");
  scratch.value = text;
  scratch.setAttribute("readonly", "");
  scratch.style.position = "fixed";
  scratch.style.opacity = "0";
  document.body.appendChild(scratch);
  scratch.select();
  let copied = false;
  try {
    copied = document.execCommand("copy");
  } catch (ignored) { /* older engines throw rather than return false */ }
  scratch.remove();
  return copied;
}

function logFileText(file) {
  const result = file.result;
  return [
    "KlikBack report for " + file.path,
    "outcome: " + result.outcome,
    result.target ? "output:  " + result.target : "",
    "",
    result.log || "",
    result.advice ? "\nnote: " + result.advice : "",
  ].filter((line) => line !== "").join("\n") + "\n";
}

/* ------------------------------------------------------------ the run */

function collectOptions() {
  const out = el("out-dir").value.trim();
  return {
    out: out || null,
    per_game_folders: el("opt-pergame").checked,
    force: el("opt-force").checked,
    session_log: el("opt-log").checked,
    extract_extensions: el("opt-extensions").checked,
    recover_comments: el("opt-comments").checked,
    application_icons: el("opt-appicons").checked,
    ownerless_recovery: el("opt-ownerless").checked,
    substitute_artwork: el("opt-artwork").checked,
    repair_bank: el("opt-repairbank").checked,
    repack_placement: el("opt-repackplacement").checked,
    drop_missing_assets: el("opt-dropmissing").checked,
    extension_dirs: el("ext-dir").value.trim()
      ? [el("ext-dir").value.trim()] : [],
  };
}

async function go() {
  if (state.running || state.files.length === 0) return;
  const paths = state.files.map((file) => file.path);
  state.running = true;
  state.cancelling = false;
  state.sawResult = false;
  state.blocked = null;
  state.doneCount = 0;
  state.files.forEach((file) => {
    if (file.inspection.decompilable) file.status = "queued";
    file.result = null;
    file.losses = [];
    file.written = null;
  });
  renderQueue();
  renderResult(fileByPath(state.selected));
  updateButtons();
  state.fileStartedAt = 0;
  state.runStartedAt = Date.now();
  state.filePosition = "";
  state.batchName = "";
  // The denominator the bar divides by has to be the number of files the
  // worker will actually report on: a batch skips undecompilable strangers
  // silently, but a single named file always gets its result.
  state.totalFiles = state.files.length > 1
    ? Math.max(state.files.filter((f) => f.inspection.decompilable).length, 1)
    : 1;
  resetProgress();
  el("status-right").textContent = "";
  setWindowTitle("starting");
  setStatus("Starting…");
  setProgress(null, "marquee");
  el("progress").classList.add("working");
  startHeartbeat();
  const options = collectOptions();
  saveSettings(options);
  const accepted = await bridge.call("start", paths, options);
  if (!accepted) {
    state.running = false;
    stopHeartbeat();
    el("progress").classList.remove("working");
    setProgress(null);
    updateButtons();
    setStatus("A run is already in progress.");
  }
}

function onEvent(event) {
  switch (event.event) {
    case "dropped":
      // Files dropped on the app window, delivered by the shell with
      // their real paths.
      if (event.paths && event.paths.length) addPaths(event.paths);
      break;
    case "file": {
      const file = fileByPath(event.path) || fileByPath(
        // The CLI may report a resolved spelling of the same path.
        (state.files.find((f) => basename(f.path) === basename(event.path))
          || {}).path);
      if (file) {
        file.status = "working…";
        state.selected = file.path;
        state.currentPath = file.path;
        renderQueue();
        renderSelected();
      }
      state.progressNow = 0;
      setProgress(0);
      state.fileStartedAt = Date.now();
      const queued = state.files.filter((f) => f.inspection.decompilable);
      state.filePosition = queued.length > 1
        ? "file " + Math.min(state.doneCount + 1, queued.length) +
          " of " + queued.length
        : "";
      renderElapsed();
      // Only in a batch: one file has its name on the card above, and
      // repeating it in front of every stage would just cost width.
      state.batchName = queued.length > 1 ? basename(event.path) : "";
      // Named outright here rather than through the prefix, so a single
      // file still opens with "Working on <game>…" the way it always has.
      setStatus("Working on " + basename(event.path) + "…");
      break;
    }
    case "stage": {
      const band = STAGE_BANDS[event.name];
      if (band) setProgress(band[0]);
      setRunStatus(STAGE_TEXT[event.name] || event.name);
      break;
    }
    case "progress": {
      const noun = LOOP_NOUN[event.stage] || "Step";
      const band = STAGE_BANDS[event.stage] || [0, 1];
      setProgress(band[0] + (event.n / event.of) * (band[1] - band[0]));
      setRunStatus(noun + " " + event.n + " of " + event.of + " — " +
        (STAGE_TEXT[event.stage] || event.stage).toLowerCase(), false);
      break;
    }
    case "loss": {
      const file = fileByPath(state.currentPath);
      if (file) file.losses.push(event.text);
      break;
    }
    case "result": {
      state.sawResult = true;
      state.doneCount += 1;
      // The file's share of the bar passes from `progressNow` to
      // `doneCount` here, which is why zeroing the one does not drop the
      // other: (done-1 + share)/total becomes (done + 0)/total.
      setProgress(0);
      const file = fileByPath(event.path) || fileByPath(state.currentPath);
      if (file) {
        file.result = event;
        file.status = event.outcome;
        renderQueue();
        if (state.selected === file.path) renderResult(file);
        measureOutput(file);
      }
      break;
    }
    case "blocked":
      // The worker stopped before reading anything, because something in
      // KlikBack's own folder needs fixing. Held until "end" so the pane
      // is written once, after the run has finished unwinding.
      state.blocked = event;
      break;
    case "end": {
      state.running = false;
      stopHeartbeat();
      setWindowTitle("");
      el("progress").classList.remove("working");
      state.filePosition = "";
      state.batchName = "";
      // The right-hand field carries the live position and clock, which
      // only exist while a run does. At the end it goes quiet rather than
      // repeating a tally the left field already gives in full.
      el("status-right").textContent = "";
      // The bar's floor is deliberately sticky, so the two ends of a run
      // are set rather than nudged: empty when it was stopped, full when
      // it finished. A run blocked before it began is the empty case --
      // no file was read, so a full bar would be a lie.
      if (state.cancelling || state.blocked) {
        resetProgress();
        drawProgress(0);
      } else {
        state.overallNow = 1;
        drawProgress(1);
      }
      state.files.forEach((file) => {
        if (file.status === "working…" || file.status === "queued") {
          file.status = state.cancelling ? "cancelled" : "—";
        }
      });
      renderQueue();
      if (state.cancelling) {
        setStatus("Cancelled");
      } else if (state.blocked) {
        setStatus("Nothing was decompiled — see below.");
        showBlocked(state.blocked);
      } else if (!state.sawResult && event.returncode !== 0) {
        setStatus("The worker crashed — details below.");
        showCrash(event);
      } else {
        setStatus(tallyText());
        el("result-pane").scrollIntoView(
          { behavior: "smooth", block: "nearest" });
      }
      updateButtons();
      break;
    }
    case "noise":
      break; // an unparseable worker line; already kept out of the stream
    default:
      break;
  }
}

function showBlocked(event) {
  // Deliberately the "expected outcome" colour the refusal card uses, not
  // the crash red: the run stopped because a file in KlikBack's own folder
  // needs fixing, which is a thing to go and do rather than a fault to
  // report. The worker's message is the whole explanation, so it is shown
  // as it was written -- naming the file, the fix and the contract.
  const pane = el("result-pane");
  pane.classList.remove("kb-hidden");
  el("result-banner").className = "kb-banner kb-expected";
  el("result-banner-icon").textContent = BANNER_ICON["kb-expected"];
  el("result-banner-text").textContent =
    event.reason === "artwork"
      ? "A drawing in the artwork folder needs fixing."
      : "KlikBack could not start the run.";
  el("result-written").classList.add("kb-hidden");
  const advice = el("result-advice");
  advice.classList.remove("kb-hidden");
  advice.textContent =
    "Nothing was read and nothing was written. The game you queued is " +
    "untouched — fix the file below and run it again.";
  el("open-folder-button").classList.add("kb-hidden");
  el("loss-details").classList.add("kb-hidden");
  el("log-text").textContent = event.text || "";
}

function showCrash(event) {
  const pane = el("result-pane");
  pane.classList.remove("kb-hidden");
  el("result-banner").className = "kb-banner kb-bad";
  el("result-banner-icon").textContent = BANNER_ICON["kb-bad"];
  el("result-banner-text").textContent = "The worker process crashed.";
  el("result-written").classList.add("kb-hidden");
  const advice = el("result-advice");
  advice.classList.remove("kb-hidden");
  advice.textContent =
    "This is not a refusal — it is a fault worth reporting. " +
    "The output below is the crash log.";
  el("open-folder-button").classList.add("kb-hidden");
  el("loss-details").classList.add("kb-hidden");
  el("log-text").textContent =
    (event.stderr || "(no crash output)") +
    "\n(exit code " + event.returncode + ")";
}

function tallyText() {
  const counts = {};
  state.files.forEach((file) => {
    if (file.result) {
      counts[file.result.outcome] = (counts[file.result.outcome] || 0) + 1;
    }
  });
  const parts = Object.keys(counts).sort()
    .map((key) => counts[key] + " " + key);
  const summary = parts.length ? "Done: " + parts.join(", ") : "Done";
  // How long it took is worth knowing after a big game, and it is the one
  // number nobody can reconstruct afterwards.
  const seconds = state.runStartedAt
    ? Math.round((Date.now() - state.runStartedAt) / 1000) : 0;
  return seconds < 3 ? summary : summary + " in " + clockText(seconds);
}

function clockText(seconds) {
  return Math.floor(seconds / 60) + ":" + String(seconds % 60).padStart(2, "0");
}

/* The window's own title tracks the run, so a KlikBack left minimised
 * during a long decompile still says where it is from the taskbar. */
function setWindowTitle(text) {
  const title = text ? PRODUCT_TITLE + " — " + text : PRODUCT_TITLE;
  if (document.title !== title) {
    document.title = title;
    bridge.call("set_title", title).catch(() => {});
  }
}

/* The bar belongs to the run, the status line to the file.
 *
 * A per-file bar restarted at 0 ten times in a ten-file batch, which reads
 * as going backwards however honest each individual sweep was. The bar now
 * shows (finished + how far into the current one) / total, so it only ever
 * climbs; which file, which stage and how long it has been are all still in
 * the status line, where the detail belongs.
 *
 * Two floors, not one. `progressNow` is the old within-file floor and still
 * resets to 0 for each new file -- it is what stops a late event from a
 * cheap stage pulling that file's share backwards. `overallNow` is the
 * bar's own floor and never resets inside a run, so the reset of the first
 * cannot move the second. They stay in step because the file's share is
 * surrendered to `doneCount` at the same moment `progressNow` is zeroed. */
function overallFraction() {
  const total = state.totalFiles || 1;
  const done = Math.min(state.doneCount, total);
  return Math.min(1, (done + state.progressNow) / total);
}

function resetProgress() {
  state.progressNow = 0;
  state.overallNow = 0;
}

function setProgress(fraction, mode) {
  if (mode === "marquee") {
    drawProgress(null, "marquee");
    return;
  }
  if (fraction === null) {
    resetProgress();
    drawProgress(null);
    return;
  }
  // Monotonic within a file: a late event from a cheaper stage must not
  // pull the bar backwards. Zero (a new file) resets the floor.
  if (fraction <= 0) {
    state.progressNow = 0;
  } else {
    state.progressNow = Math.max(fraction, state.progressNow || 0);
  }
  state.overallNow = Math.max(state.overallNow, overallFraction());
  drawProgress(state.overallNow);
}

/* The only place the bar is written to. The percentage is read out beside
 * the bar rather than printed across it, so there is one copy of the label
 * and no clipping arithmetic; a blank label at 0 is now a choice rather
 * than a workaround, because an empty bar says "idle" better than "0%"
 * does -- and drawProgress(0) is what a cancelled run ends on. */
function drawProgress(fraction, mode) {
  const indicator = el("progress");
  indicator.classList.toggle("marquee", mode === "marquee");
  const percent =
    fraction === null ? null : Math.round(fraction * 100);
  // The indeterminate slider belongs to the track, so the fill sits at
  // zero all through it and has nothing to unwind when the first real
  // event arrives.
  el("progress-bar").style.width = percent === null ? "0" : percent + "%";
  el("progress-text").textContent =
    percent === null || percent === 0 ? "" : percent + "%";
  // A progressbar with no aria-valuenow is the standard way to say
  // indeterminate, which is exactly what the marquee means. An idle bar
  // is not indeterminate -- it is at zero, and says so.
  if (mode === "marquee") {
    indicator.removeAttribute("aria-valuenow");
  } else {
    indicator.setAttribute("aria-valuenow",
      String(percent === null ? 0 : percent));
  }
}

/* The heartbeat.
 *
 * A big game sits inside one stage for minutes at a time with nothing to
 * report -- a 60 MB target spends a long while reading events before the
 * first frame arrives -- and a status line that has not moved for two
 * minutes reads as a hung program. The dots and the clock say "still
 * going" without claiming progress the engine has not reported: the bar's
 * fill is still driven only by real events.
 *
 * The dots are padded with non-breaking spaces so the line does not
 * shuffle sideways four times a second. */
const ELLIPSIS = ["   ", ".  ", ".. ", "..."];

//: The window title's stable half, filled in at boot.
let PRODUCT_TITLE = "KlikBack";

/* The status line's own house style, so twenty messages written months
 * apart read as one voice. The line says one of two things:
 *
 *   a STATE, which takes no full stop -- "Ready", "Cancelled",
 *   "Done: 1 built in 0:07";
 *   a SENTENCE about what happened, which takes one -- "The recent list is
 *   empty.", "Nothing was decompiled -- see below."
 *
 * with one exception in either case: a message ending in a filename or a
 * path takes no stop, because a stop after `game.decompiled.log` reads as
 * part of the name. A message the run is still animating ends in an
 * ellipsis and has its trailing punctuation replaced anyway.
 *
 * `announce` is false only for the per-frame progress line, which changes
 * several times a second: a live region reading out every frame number
 * would be unusable, while the stage boundaries around it are exactly what
 * somebody wants to hear. */
function setStatus(text, announce = true) {
  state.statusBase = text;
  renderStatus();
  if (announce) {
    const node = el("status-announce");
    // Writing the same string twice does not re-announce in some readers,
    // so an unchanged message is left alone rather than blanked and reset.
    if (node && node.textContent !== text) node.textContent = text;
  }
}

/* The status line during a run, with the game named while a batch is going.
 *
 * The name matters most exactly when it is hardest to know: one file has
 * its name on the card above, but in a batch the only other clue is "file 2
 * of 5", which does not say which. It used to be set once, by the `file`
 * event, and then overwritten by the first stage a moment later -- so the
 * name was on screen for a fraction of a second per file. */
function setRunStatus(text, announce = true) {
  const named = state.batchName ? state.batchName + " — " + text : text;
  setStatus(named, announce);
}

function renderStatus() {
  const base = state.statusBase || "";
  const field = el("status-main");
  field.textContent = state.running
    ? base.replace(/[.…]+$/, "") + ELLIPSIS[state.tick % ELLIPSIS.length]
    : base;
  // The field cannot wrap, so a long message — a saved path, a 1996 game
  // with a sentence for a filename — is cut with an ellipsis. Then it must
  // still be readable, and only then: a tooltip on every status line would
  // be noise. The tip carries the settled text, not the animated one, so
  // it does not flicker under the cursor.
  if (field.scrollWidth > field.clientWidth) {
    field.setAttribute("data-tip", base);
  } else {
    field.removeAttribute("data-tip");
  }
}

function renderElapsed() {
  if (!state.running) return;
  const seconds = state.fileStartedAt
    ? Math.floor((Date.now() - state.fileStartedAt) / 1000) : 0;
  // Under a few seconds a clock is just flicker; a long file is where it
  // earns its place.
  const clock = seconds < 3 ? "" : clockText(seconds);
  el("status-right").textContent =
    [state.filePosition, clock].filter(Boolean).join("  ·  ");
}

function startHeartbeat() {
  stopHeartbeat();
  state.tick = 0;
  state.ticker = window.setInterval(() => {
    state.tick += 1;
    renderStatus();
    renderElapsed();
    const percent = Math.round((state.overallNow || 0) * 100);
    setWindowTitle([
      percent ? percent + "%" : "",
      state.currentPath ? basename(state.currentPath) : "",
    ].filter(Boolean).join(" — "));
  }, 400);
}

function stopHeartbeat() {
  if (state.ticker !== null) window.clearInterval(state.ticker);
  state.ticker = null;
}

function updateButtons() {
  el("go-button").disabled = state.running || state.files.length === 0;
  el("cancel-button").disabled = !state.running;
  el("clear-button").disabled = state.running;
}

/* ---------------------------------------------------------- settings */

function applySettings(settings) {
  state.settings = settings || {};
  const options = state.settings.options || {};
  const set = (id, key, fallback) => {
    el(id).checked = options[key] === undefined ? fallback : !!options[key];
  };
  set("opt-extensions", "extract_extensions", true);
  set("opt-pergame", "per_game_folders", false);
  set("opt-appicons", "application_icons", true);
  set("opt-ownerless", "ownerless_recovery", true);
  set("opt-comments", "recover_comments", false);
  set("opt-force", "force", false);
  set("opt-log", "session_log", true);
  set("opt-artwork", "substitute_artwork", true);
  set("opt-repairbank", "repair_bank", false);
  set("opt-repackplacement", "repack_placement", false);
  set("opt-dropmissing", "drop_missing_assets", false);
  el("out-dir").value = state.settings.out || "";
  el("ext-dir").value = (options.extension_dirs || [])[0] || "";
}

function saveSettings(options) {
  state.settings.options = options;
  state.settings.out = options.out || "";
  bridge.call("save_settings", state.settings).catch(() => {});
}

function saveRecents(paths) {
  const recent = state.settings.recent || [];
  paths.forEach((path) => {
    const at = recent.indexOf(path);
    if (at >= 0) recent.splice(at, 1);
    recent.unshift(path);
  });
  state.settings.recent = recent.slice(0, 10);
  bridge.call("save_settings", state.settings).catch(() => {});
  renderRecent();
}

/* ------------------------------------------------------------- recents */

/* The settings file has remembered the last ten games since phase 4 and
 * nothing ever showed them. They hang off their own button beside Browse…
 * rather than a File menu: the menu bar was taken out on purpose, and this
 * is where a user already looks for "open something". */

/* A path short enough for the status line, keeping the part worth reading.
 * The field elides at its END, so a long path loses its filename -- the one
 * word the message is actually about. This shortens the folder the way the
 * Recent menu does and keeps the name whole. */
function shortenFile(path) {
  const folder = shortenPath(path);
  return folder ? folder + "\\" + basename(path) : basename(path);
}

function shortenPath(path) {
  const parts = String(path).split(/[\\/]/);
  parts.pop();  // the file's own name is already the item's first line
  const tail = parts.slice(-2).join("\\");
  return parts.length > 2 ? "…\\" + tail : tail;
}

function renderRecent() {
  const recent = (state.settings.recent || []).filter(Boolean);
  el("recent-button").disabled = recent.length === 0;
  const menu = el("recent-menu");
  menu.textContent = "";
  for (const path of recent) {
    const item = document.createElement("div");
    item.className = "kb-menu-item";
    item.dataset.tip = path;  // the whole path, in the classic yellow box
    const name = document.createElement("span");
    name.className = "kb-menu-name";
    name.textContent = basename(path);
    const where = document.createElement("span");
    where.className = "kb-menu-where";
    where.textContent = shortenPath(path);
    item.appendChild(name);
    item.appendChild(where);
    item.addEventListener("click", () => {
      closeRecent();
      addPaths([path]);
    });
    menu.appendChild(item);
  }
  if (!recent.length) return;
  const rule = document.createElement("div");
  rule.className = "kb-menu-rule";
  menu.appendChild(rule);
  const forget = document.createElement("div");
  forget.className = "kb-menu-item";
  forget.dataset.tip =
    "Empty this list. It only forgets the paths — no file is touched.";
  forget.textContent = "Forget these";
  forget.addEventListener("click", () => {
    closeRecent();
    state.settings.recent = [];
    bridge.call("save_settings", state.settings).catch(() => {});
    renderRecent();
    setStatus("The recent list is empty.");
  });
  menu.appendChild(forget);
}

function recentIsOpen() {
  return !el("recent-menu").classList.contains("kb-hidden");
}

function closeRecent() {
  el("recent-menu").classList.add("kb-hidden");
}

/* ------------------------------------------------------------ tooltips */

/* One floating pale-yellow tooltip for every [data-tip] element, shown
 * after a short hover the way the real Windows ones were. Kept as plain
 * mouseover/mouseout so it works identically in the shell and the
 * harness; `title=` is not used because WebView2 renders it in the
 * browser style, not ours. */
function tooltips() {
  const tip = document.createElement("div");
  tip.id = "kb-tooltip";
  tip.className = "kb-hidden";
  document.body.appendChild(tip);
  let timer = null;

  document.addEventListener("mouseover", (event) => {
    const target = event.target.closest("[data-tip]");
    if (!target) return;
    clearTimeout(timer);
    timer = setTimeout(() => {
      tip.textContent = target.dataset.tip;
      tip.style.left = "0px";
      tip.style.top = "0px";
      tip.classList.remove("kb-hidden");
      const rect = target.getBoundingClientRect();
      let x = rect.left + 14;
      let y = rect.bottom + 6;
      if (x + tip.offsetWidth > window.innerWidth - 8) {
        x = window.innerWidth - tip.offsetWidth - 8;
      }
      if (y + tip.offsetHeight > window.innerHeight - 8) {
        y = rect.top - tip.offsetHeight - 6;
      }
      tip.style.left = Math.max(4, x) + "px";
      tip.style.top = Math.max(4, y) + "px";
    }, 400);
  });

  document.addEventListener("mouseout", (event) => {
    if (event.target.closest && event.target.closest("[data-tip]")) {
      clearTimeout(timer);
      tip.classList.add("kb-hidden");
    }
  });
}

/* ---------------------------------------------------------- shortcuts */

/* Enter decompiles, Esc cancels, Delete drops the selected row, Ctrl+O
 * browses. A text field keeps every key it might want: typing a path and
 * pressing Enter has to add that path rather than start the run, and
 * Delete inside a box has to delete a character. */

function typingIn(node) {
  return !!node && (node.isContentEditable ||
    ["INPUT", "TEXTAREA", "SELECT"].includes(node.tagName));
}

function onKey(event) {
  if (event.altKey || event.metaKey) return;
  // An open menu owns Escape wherever the focus is; nothing else does.
  if (event.key === "Escape" && recentIsOpen()) {
    closeRecent();
    return;
  }
  if (typingIn(event.target)) return;

  if (event.ctrlKey) {
    if (event.key === "o" || event.key === "O") {
      event.preventDefault();
      openGames();
    }
    return;
  }
  switch (event.key) {
    case "Enter":
      // A focused button, link or summary already answers Enter itself;
      // firing Decompile as well would be one press doing two things.
      if (["BUTTON", "A", "SUMMARY"].includes(event.target.tagName)) return;
      if (!el("go-button").disabled) {
        event.preventDefault();
        el("go-button").click();
      }
      break;
    case "Escape":
      if (!el("cancel-button").disabled) {
        event.preventDefault();
        el("cancel-button").click();
      }
      break;
    case "Delete":
      if (state.selected && !state.running) {
        event.preventDefault();
        removeFile(state.selected);
      }
      break;
    default:
      break;
  }
}

/* ------------------------------------------------------------- wiring */

async function openGames() {
  if (state.harness) {
    setStatus("No native dialogs in the dev preview — use the path box.");
    return;
  }
  const chosen = await bridge.call("browse_files");
  if (chosen && chosen.length) addPaths(chosen);
}

function wire() {
  tooltips();
  el("github-link").addEventListener("click", (event) => {
    // In the app window an <a> would navigate the app itself; the shell
    // opens the user's own browser instead. The dev preview is a browser.
    if (!state.harness) {
      event.preventDefault();
      bridge.call("open_link", el("github-link").href);
    }
  });
  el("browse-button").addEventListener("click", openGames);

  el("recent-button").addEventListener("click", (event) => {
    event.stopPropagation();  // the document handler below closes it again
    el("recent-menu").classList.toggle("kb-hidden", recentIsOpen());
  });
  document.addEventListener("click", (event) => {
    if (recentIsOpen() &&
        !(event.target.closest && event.target.closest(".kb-recent-wrap"))) {
      closeRecent();
    }
  });
  document.addEventListener("keydown", onKey);

  el("add-path-button").addEventListener("click", () => {
    const value = el("path-box").value.trim();
    if (value) {
      el("path-box").value = "";
      addPaths([value]);
    }
  });
  el("path-box").addEventListener("keydown", (event) => {
    if (event.key === "Enter") el("add-path-button").click();
  });

  el("out-browse").addEventListener("click", async () => {
    if (state.harness) {
      setStatus("No native dialogs in the dev preview — " +
        "type the folder.");
      return;
    }
    const chosen = await bridge.call("browse_folder");
    if (chosen) el("out-dir").value = chosen;
  });
  el("ext-browse").addEventListener("click", async () => {
    if (state.harness) {
      setStatus("No native dialogs in the dev preview — " +
        "type the folder.");
      return;
    }
    const chosen = await bridge.call("browse_folder");
    if (chosen) el("ext-dir").value = chosen;
  });

  el("go-button").addEventListener("click", go);
  el("cancel-button").addEventListener("click", () => {
    state.cancelling = true;
    bridge.call("cancel");
    setStatus("Cancelling…");
  });
  el("clear-button").addEventListener("click", () => {
    if (state.running) return;
    state.files = [];
    state.selected = null;
    renderQueue();
    renderSelected();
    updateButtons();
    setStatus("Ready");
    setProgress(null);
  });

  /* Dropping anywhere on the window works; the well is the visual anchor.
   *
   * The highlight is held by a timer rather than dropped on `dragleave`,
   * because `dragleave` bubbles: crossing from one element to the next
   * fires it even though the pointer never left the window, so the state
   * flickered off and on all the way across the page. `dragover` keeps
   * firing while a drag is anywhere over the window -- the drag model
   * repeats it about every 350ms even when the pointer is still -- so a
   * timer that outlives that gap holds steady, and lets go a moment after
   * the drag really has. */
  const well = el("drop-well");
  let dragTimer = null;
  document.addEventListener("dragover", (event) => {
    event.preventDefault();
    well.classList.add("kb-drag-over");
    window.clearTimeout(dragTimer);
    dragTimer = window.setTimeout(
      () => well.classList.remove("kb-drag-over"), 500);
  });
  document.addEventListener("drop", (event) => {
    event.preventDefault();
    window.clearTimeout(dragTimer);
    well.classList.remove("kb-drag-over");
    // In the app window the shell receives the drop natively (with real
    // paths) and pushes a "dropped" event; this handler only clears the
    // highlight there. A browser never reveals full paths at all.
    if (bridge.mode !== "pywebview" && event.dataTransfer.files.length) {
      setStatus("Dropping needs the app window — in the dev preview, " +
        "use the path box.");
    }
  });
}

/* --------------------------------------------------------------- boot */

const kb = { onEvent };
window.kb = kb;

(async function boot() {
  wire();
  await bridge.detect();
  const config = await bridge.call("boot");
  state.harness = !!config.harness;
  applySettings(config.settings);
  renderRecent();
  PRODUCT_TITLE = config.product + " " + config.version;
  document.title = PRODUCT_TITLE;
  el("topbar-version").textContent = "v" + config.version;
  setStatus("Ready — " + config.product + " " + config.version +
    (state.harness ? " (dev preview)" : ""));
  if (config.autorun && config.autorun.length) {
    await addPaths(config.autorun);
    if (config.autostart) go();
  }
  updateButtons();
})();
