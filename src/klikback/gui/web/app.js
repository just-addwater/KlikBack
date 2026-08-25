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
  extensions: "Carving extension modules…",
  convert: "Rebuilding the project…",
};

const LOOP_NOUN = { frames: "Frame", levels: "Level" };

/* Which option family a kind belongs to -- the same table the facade keeps
 * (`api.FAMILY_OF_KIND`). It decides which option blocks are on screen:
 * every option is global to the run and each game takes the ones its own
 * family has, so a block is shown only while a game of its family is in
 * the list. That is the whole of the mixed-batch rule, made visible. */
const FAMILY_OF_KIND = {
  mmf1: "mmf1", "mmf1-ccn": "mmf1",
  mmf15: "mmf15", "mmf15-ccn": "mmf15",
  "tgf-exe": "tgf", "tgf-data": "tgf", "tgf-damaged": "tgf",
  mmf2: "mmf2", "mmf2-ccn": "mmf2",
};

function familyOf(file) {
  return FAMILY_OF_KIND[file.inspection.kind] || null;
}

/* The queue's own spelling of what a file is. The full label ("Multimedia
 * Fusion 2.0 compiled application (.ccn)") is written for the card and
 * elides uselessly in a 215px column, so the column shows a short form and
 * carries the full label in its tooltip. */
const SHORT_LABELS = {
  mmf1: "MMF 1.0", "mmf1-ccn": "MMF 1.0 .ccn",
  mmf15: "MMF 1.5", "mmf15-ccn": "MMF 1.5 .ccn",
  mmf2: "MMF 2.0", "mmf2-ccn": "MMF 2.0 .ccn",
  "mmf-unknown": "MMF, unknown build",
  fusion2: "Fusion 2.5 or newer",
  "tgf-exe": "TGF/CnC", "tgf-data": "TGF/CnC data",
  "tgf-damaged": "TGF/CnC, incomplete",
  "mmf-editable": "editable project",
  "not-clickteam": "not a Clickteam game",
  unreadable: "unreadable",
};

function shortLabel(inspection) {
  return SHORT_LABELS[inspection.kind] || inspection.product;
}

/* What an idle row's chip says about a file that will not be decompiled.
 * A bare dash answered "what will happen to this?" with punctuation. */
function idleStatus(inspection) {
  if (inspection.decompilable) return "ready";
  if (inspection.kind === "fusion2") return "not supported";
  if (inspection.kind === "mmf-editable") return "already a project";
  return "skipped";
}

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
  extensions: [0.02, 0.10],
  convert: [0.10, 0.97],
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
  // Neither is a fault of the run: one is a product KlikBack does not
  // read, the other a file it could not identify or open. They used to
  // arrive as "nothing-to-do" and wear no chip class at all.
  unsupported: "kb-chip-warn",
  unrecognised: "kb-chip-warn",
  "working…": "kb-chip-run",
};

/* Some losses are simply what compiling a game does: the compiler throws
 * the editor pictures, the comment text and the page ownership away, so
 * EVERY compiled game is missing them and no tool can bring them back.
 * Those are presented as expected, in their own quiet box, and are not
 * counted against the game. The engine's wording is never altered --
 * this is presentation-side triage only. */
const EXPECTED_LOSS_KINDS = [
  // The 2.0 engine's own account of the merge comes first, because its
  // wording ("comment row(s) added to mark where each inlined section
  // begins") would otherwise land in the comment-text group below.
  {
    pattern: /inlined section|INLINED into the event list|inlined global-events|inlined from .*global-events|SHAPE: this project's global events|event group\(s\) came from an inlined|comment row\(s\) added to mark/i,
    label: "Global events and behaviours, merged into their frames",
    why: "all recovered and working - the compiler merged them into each " +
      "frame that used them and dropped the page names, so each section " +
      "sits in its frame behind a yellow label row saying where it came " +
      "from",
  },
  {
    pattern: /preview thumbnail|icon artwork|object icon|icon's own pixels|application icons cannot be recovered|editor icon|carry no picture of their own|take the icon of the module installed|icon slots are left transparent|recovered blank|application icon's 16x16 entry/i,
    label: "Icons and preview pictures",
    why: "editor-only artwork the compiler never stored; KlikBack draws " +
      "each icon from the object's own picture, from your installed " +
      "module, or from the artwork folder",
  },
  {
    pattern: /comment row|comment position/i,
    label: "Comment text",
    why: "the compiler kept the row numbers but threw the words away",
  },
  {
    pattern: /global event|ownerless|OWNER UNKNOWN|flattened into the frame|behaviour/i,
    label: "Global events and behaviours",
    why: "all recovered and working - every event is present and runs " +
      "exactly as before; only the name of the page it was filed under " +
      "is gone, so each one sits in its frame behind a clear label",
  },
  {
    pattern: /extension module title|display name unknown, substituted|name lost at compile, substituted|had no name to recover/i,
    label: "Extension and object display names",
    why: "games store which extension files they use but often not the " +
      "names shown in the editor; KlikBack recovers a name where it can " +
      "and otherwise uses the filename - the extension itself works " +
      "either way",
  },
  {
    // `private block ... carried verbatim` was the whole wording until the
    // engine started zeroing the four compile-baked bytes at +12, and this
    // pattern was not moved with it. Every extension object in every game
    // then arrived as something to review. BOTH wordings are matched now,
    // and the shared `private block (N bytes) carried` prefix is what is
    // keyed on, so the tail can change again without this going stale.
    pattern: /is referenced by no object; carried into the bank unchanged|private block \(\d+ bytes\) carried/i,
    label: "Carried through unchanged",
    why: "pictures no object uses, and each extension object's private " +
      "settings, are copied into the project exactly as the game holds " +
      "them",
  },
  {
    // Hardware-accelerated builds record runtime state the editor does not
    // keep, and the install's own state rather than the project's. None of
    // it is the game, none of it is recoverable, and none of it is a loss
    // worth a reader's attention -- but every object and frame carries some,
    // so unclassified it was the loudest thing in the report.
    pattern: /unused ink parameter|frame-effects chunk at its default|carries bits 0x[0-9A-Fa-f]+, which record the state of the Multimedia Fusion installation|no project field is known to be bound to it/i,
    label: "Runtime and installation state, not part of the project",
    why: "values the compiler wrote for its own use - an unused effect " +
      "slot, an empty effects chunk, a note of which installation built " +
      "the game - which the editor does not store in a project either way",
  },
];

/* The 2.0 engine also reports things that are not losses at all -- what
 * it recovered and from where, which format build it wrote. Those are
 * shown, because the report is the whole story, but they are information,
 * not something to review. */
const INFO_NOTE_PATTERN =
  /recovered from the compiled file|names the project it was built from|is format build \d+; the \.mfa is written|default menu \(\d+ bytes\) is substituted|'include external files' is set|substituted the editor's \d+x\d+ default/i;

/* What was cut out on purpose. Always shown first and never folded into
 * "expected": it is the one line in the report that describes a choice
 * rather than a limit, and the person reading it later may not be the
 * person who made the choice. */
const STRIPPED_PATTERN = /^STRIPPED/;

/* A loss or note ENTRY is {text, more}: the worker condenses lines that
 * repeat with only their numbers changed, and `more` is how many further
 * lines matched the shown one's shape. One real game reported 46,000
 * lines; the full report and the session log keep them all, while the
 * card works with a few dozen entries. */

function tally(entries) {
  return entries.reduce((n, entry) => n + 1 + (entry.more || 0), 0);
}

function fmt(n) {
  return n.toLocaleString();
}

function lineText(entry) {
  return entry.text + (entry.more
    ? " (and " + fmt(entry.more) + " more like this)"
    : "");
}

function classifyLosses(losses, notes) {
  const expected = new Map();
  const notable = [];
  const info = [];
  const stripped = [];
  for (const entry of losses || []) {
    const kind = EXPECTED_LOSS_KINDS.find((k) => k.pattern.test(entry.text));
    if (kind) {
      if (!expected.has(kind)) expected.set(kind, []);
      expected.get(kind).push(entry);
    } else {
      notable.push(entry);
    }
  }
  for (const entry of notes || []) {
    if (STRIPPED_PATTERN.test(entry.text)) {
      stripped.push(entry);
      continue;
    }
    const kind = EXPECTED_LOSS_KINDS.find((k) => k.pattern.test(entry.text));
    if (kind) {
      if (!expected.has(kind)) expected.set(kind, []);
      expected.get(kind).push(entry);
    } else if (INFO_NOTE_PATTERN.test(entry.text)) {
      info.push(entry);
    } else {
      notable.push(entry);
    }
  }
  return { expected, notable, info, stripped };
}

/* The classification, computed once per state of the file's report: the
 * queue re-renders on every worker event, and running the pattern table
 * over a big report each time is work with one answer. */
function classifyFile(file) {
  const stamp = (file.losses || []).length + ":" + (file.notes || []).length;
  if (file._classifiedAs !== stamp) {
    file._classified = classifyLosses(file.losses, file.notes);
    file._classifiedAs = stamp;
  }
  return file._classified;
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
  built: ["kb-good", (r) => "Decompiled - " + basename(r.target)],
  // A refusal usually means the engine met something it will not
  // reconstruct wrongly. An incomplete copy is refused for the opposite
  // reason -- nothing about the game is the problem, the file is short of
  // bytes -- so it says so rather than blaming a feature.
  // A TGF/CnC standalone keeps its game in a .gam or .cca beside it, and
  // the only way this pipeline refuses one is that none of them could be
  // used. Keyed on kind and outcome, the way the facade keys its advice.
  refused: ["kb-expected", (r) => r.kind === "tgf-damaged"
    ? "This copy of the game is incomplete."
    : r.kind === "tgf-exe"
      ? "This game's data file could not be used."
      : "This game uses a feature that cannot be reconstructed correctly."],
  invalid: ["kb-bad", () =>
    "The reconstruction failed its own validation."],
  failed: ["kb-bad", () => "Something unexpected went wrong."],
  error: ["kb-bad", () => "Something unexpected went wrong."],
  skipped: ["kb-neutral", () =>
    "The output already exists - nothing was overwritten."],
  "nothing-to-do": ["kb-neutral", () => "Nothing to decompile."],
  // Both were "Nothing to decompile." until 2026-08-24, which is true of
  // a project that is already a project and false of these two.
  unsupported: ["kb-expected", () =>
    "KlikBack does not read this Clickteam product."],
  unrecognised: ["kb-expected", () =>
    "KlikBack could not read or recognise this file."],
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
    const inspection = await bridge.call("inspect", path, mmf2Folder());
    state.files.push({
      path,
      name: basename(path),
      inspection,
      status: idleStatus(inspection),
      result: null,
      losses: [],
      notes: [],
      // MMF 2.0 only: the modules chosen for removal from THIS game. Per
      // file by design -- a strip list names modules of one project, and
      // a batch of games shares nothing. Nothing is ever pre-ticked.
      strip: new Set(),
    });
    state.selected = path;
  }
  renderQueue();
  renderSelected();
  updateButtons();
  saveRecents(expanded);
}

function mmf2Folder() {
  return el("mmf2-ext-dir").value.trim() || null;
}

/* Whether the cards may offer to remove a module at all: a Recovery
 * option, off by default, so the ordinary card is a plain list of what the
 * game needs and the destructive choice is only seen by somebody who
 * turned it on. */
function allowStrip() {
  return el("opt-allowstrip").checked;
}

/* Turning the option off takes every ticked removal with it, so nothing
 * armed on a card can outlive the control that showed it. */
function onAllowStripChange() {
  if (!allowStrip()) {
    state.files.forEach((file) => { if (file.strip) file.strip.clear(); });
  }
  renderQueue();
  renderSelected();
}

/* The MMF 2.0 folder changed: the cards' "installed" column answers from
 * it, so every 2.0 game in the list is looked at again. The verdicts do
 * not move -- only the extension rows read the folder -- and a removal
 * already ticked stays ticked. */
async function reinspectMmf2() {
  if (state.running) return;
  const folder = mmf2Folder();
  let checked = 0;
  for (const file of state.files) {
    if (familyOf(file) !== "mmf2") continue;
    try {
      file.inspection = await bridge.call("inspect", file.path, folder);
    } catch (ignored) {
      continue;  // the file went away; its old card stands
    }
    checked += 1;
    const known = new Set(file.inspection.extensions.map((r) => r.module));
    file.strip = new Set([...file.strip].filter((m) => known.has(m)));
  }
  renderQueue();
  renderSelected();
  // Say what just happened: the installed column changing by itself reads
  // as a glitch, not as an answer.
  if (checked) {
    setStatus(folder
      ? "Checked " + checked + " MMF 2.0 game" + (checked === 1 ? "" : "s") +
        " against the Extensions folder."
      : "MMF 2.0 folder cleared - module install checks are off.");
  }
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
    const nameCell = document.createElement("td");
    nameCell.textContent = file.name;
    row.appendChild(nameCell);
    const whatCell = document.createElement("td");
    whatCell.textContent = shortLabel(file.inspection);
    // The full label, written for the card, rides in the cell's own tip so
    // the short form costs nothing.
    whatCell.dataset.tip = file.inspection.product;
    row.appendChild(whatCell);
    const statusCell = document.createElement("td");
    statusCell.className = "kb-status-cell";
    const chip = document.createElement("span");
    chip.className = "kb-chip " + (CHIP_CLASS[file.status] || "kb-chip-neutral");
    let statusText = file.status;
    if (file.result) {
      const { notable, stripped } = classifyFile(file);
      if (stripped.length) {
        statusText += " · modules removed";
      }
      if (notable.length) {
        statusText += " · " + fmt(tally(notable)) + " to review";
      }
    } else if (file.strip && file.strip.size) {
      // A removal is the one per-game choice; the row says it is armed,
      // so a batch can be checked at a glance before Decompile.
      statusText += " · removes " + file.strip.size;
    }
    chip.textContent = statusText;
    statusCell.appendChild(chip);
    row.appendChild(statusCell);

    // One row at a time, so the list is no longer all-or-nothing with
    // Clear. Disabled during a run: the worker was handed a fixed list of
    // paths and cannot be told to forget one.
    const removeCell = document.createElement("td");
    removeCell.className = "kb-remove-cell";
    // A finished row can open its output without the double-click secret:
    // the same folder the result pane's button shows, from the row itself.
    const where = file.result &&
      (file.result.target || file.result.session_log);
    if (where) {
      const opener = document.createElement("span");
      opener.className = "kb-open-row";
      opener.textContent = "📁";
      opener.dataset.tip = "Show what was written for " + file.name +
        " in Explorer.";
      opener.addEventListener("click", (event) => {
        event.stopPropagation();  // opening is not also selecting
        bridge.call("open_folder", where);
      });
      removeCell.appendChild(opener);
    }
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
  renderFamilyBlocks();
}

/* Show each family's option block only while a game of that family is in
 * the list. One rule for every block, read from the markup, so adding a
 * family is a `data-families` attribute rather than a new special case. */
function renderFamilyBlocks() {
  const present = new Set(state.files.map(familyOf).filter(Boolean));
  document.querySelectorAll(".kb-family[data-families]").forEach((block) => {
    const wanted = block.dataset.families.split(/\s+/);
    block.classList.toggle("kb-hidden",
      !wanted.some((family) => present.has(family)));
  });
  // The disclosure stays collapsed (user's call), so its summary carries a
  // live count of what is inside it for the games listed: a closed line
  // that says "(5 for the games listed)" is an invitation, a bare one is
  // furniture.
  const visible = document.querySelectorAll(
    "#recovery-options .kb-family:not(.kb-hidden) .field-row").length;
  el("recovery-summary").textContent = visible
    ? "Recovery options (" + visible + " for the games listed)"
    : "Recovery options";
  // One line either way: what the hint needs to say depends on whether
  // there is anything to explain yet.
  el("family-hint").textContent = visible
    ? "Each block applies to the game family it names; games of other " +
      "families ignore it, and every game's report lists what was in " +
      "force for it."
    : "Options for each game family appear here once a game of that " +
      "family is in the list.";
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
    setStatus("Removed " + gone.name + " - " + state.files.length +
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
  // Only the TGF/CnC families report protection at all, so the tooltip can
  // say what it means for them without hedging. It is worth saying: the
  // word looks like a warning, and here it is the ordinary case.
  if (inspection.protected !== null && inspection.protected !== undefined) {
    fact(inspection.protected ? "protected" : "not protected",
      inspection.protected ? "kb-fact-warn" : "",
      inspection.protected
        ? "The game's data is scrambled so the editor cannot open it. " +
          "That is normal for a game published in this era, and KlikBack " +
          "unscrambles it - nothing extra is needed from you."
        : "The game's data is stored plainly, so there is nothing to " +
          "unscramble. It still needs rebuilding into a project.");
  }

  // An incomplete copy gets a tag rather than the "no" colour: it is a game
  // KlikBack reads, held up by a decision about the assets that are missing
  // rather than by anything it cannot do.
  if (inspection.kind === "tgf-damaged") {
    fact("incomplete copy", "kb-fact-warn",
      "The file stops partway through its last sound or image bank - " +
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
      "This doesn’t look like a decompilable Clickteam game - " +
      "the signatures checked are listed above.");
  }
  renderExtensions(file);
  renderResult(file);
}

/* The extension modules a 2.0 game asks for, and the one choice made per
 * game: which of them to remove from the recovered project.
 *
 * Why the control lives here and not in Options: a removal names modules
 * of ONE project, so a batch of games shares nothing -- the list is built
 * from this game's own inspection, which is also what makes the engine's
 * unknown-name refusal unreachable from the window. Nothing is ever
 * pre-ticked: a module the editor here lacks is marked, and that mark is
 * a suggestion, not a decision. */
const REMOVE_TIP =
  "Leave this module out of the recovered project - its objects and the " +
  "event lines that used them - so the editor stops asking for a file " +
  "you do not have. That content is gone from the output (written as a " +
  "separate .stripped.mfa); the game file itself is untouched, and " +
  "installing the module instead keeps everything.";

function renderExtensions(file) {
  const box = el("inspect-extensions");
  box.textContent = "";
  const rows = (file.inspection.extensions || []);
  const isMmf2 = familyOf(file) === "mmf2";
  box.classList.toggle("kb-hidden", !isMmf2 || rows.length === 0);
  if (!isMmf2 || rows.length === 0) return;

  // Collapsed by default (user's call): the plain card stays plain, and
  // the folded line still answers the first question -- how many modules,
  // whether any is missing here, whether a removal is armed. Armed
  // removals force it open, so nothing destructive ever hides.
  const missing = rows.filter((row) => row.installed === false).length;
  const doubtful = rows.filter((row) => row.installed && row.unversioned)
    .length;
  const group = document.createElement("details");
  group.className = "kb-ext-details";
  group.open = !!file.extOpen || file.strip.size > 0;
  group.addEventListener("toggle", () => { file.extOpen = group.open; });
  const summary = document.createElement("summary");
  summary.appendChild(document.createTextNode(
    "Extension modules this game needs (" + rows.length + ")"));
  if (missing) {
    const flag = document.createElement("span");
    flag.className = "kb-ext-missing";
    flag.textContent = missing + " not installed";
    summary.appendChild(document.createTextNode(" "));
    summary.appendChild(flag);
  }
  if (doubtful) {
    // Worth the fold line for the same reason "not installed" is: it is a
    // module the editor may ask for, and the summary is where somebody
    // decides whether to open the list at all.
    const shaky = document.createElement("span");
    shaky.className = "kb-ext-caution";
    shaky.textContent = doubtful + " with no version";
    summary.appendChild(document.createTextNode(" "));
    summary.appendChild(shaky);
  }
  if (file.strip.size) {
    const armed = document.createElement("span");
    armed.className = "kb-ext-missing";
    armed.textContent = "removes " + file.strip.size;
    summary.appendChild(document.createTextNode(" "));
    summary.appendChild(armed);
  }
  group.appendChild(summary);
  box.appendChild(group);

  const table = document.createElement("table");
  table.className = "kb-ext-table";
  const thead = document.createElement("thead");
  const hr = document.createElement("tr");
  [["Module", ""],
   ["In the game", "A 2.0 game carries the RUNTIME build of each module, " +
     "which plays the game but cannot be loaded by the editor. It is " +
     "carved out beside the project when extraction is on."],
   ["In your MMF 2.0 folder", "Whether the EDITOR build is in the " +
     "Extensions folder set below. The editor needs that one to open the " +
     "project."],
   // The Remove column exists only while the Recovery option allows it
   // (user's call, 2026-08-23): the plain card is a list of what the game
   // needs, and a destructive choice is not offered to someone who did
   // not ask to see it.
   ...(allowStrip() ? [["Remove", REMOVE_TIP]] : []),
  ].forEach(([text, tip]) => {
    const th = document.createElement("th");
    th.textContent = text;
    if (tip) th.dataset.tip = tip;
    hr.appendChild(th);
  });
  thead.appendChild(hr);
  table.appendChild(thead);

  const tbody = document.createElement("tbody");
  const folderSet = !!mmf2Folder();
  for (const row of rows) {
    const tr = document.createElement("tr");
    const name = document.createElement("td");
    name.textContent = row.module;
    if (row.title) {
      const title = document.createElement("span");
      title.className = "kb-ext-title";
      title.textContent = " " + row.title;
      name.appendChild(title);
    }
    tr.appendChild(name);

    const inside = document.createElement("td");
    // "Runtime copy only" (the user's wording): the copy in the game
    // plays it but is not the build the editor loads -- the column
    // header's tip says why.
    inside.textContent = row.embedded
      ? "Runtime copy only"
      : (row.shipped ? "beside it" : "no");
    if (row.shipped) inside.dataset.tip = row.shipped;
    tr.appendChild(inside);

    const installed = document.createElement("td");
    const mark = document.createElement("span");
    if (row.installed === null || row.installed === undefined) {
      mark.className = "kb-ext-unknown";
      mark.textContent = folderSet ? "not checked" : "set the folder below";
      mark.dataset.tip = "Point the MMF 2.0 Extensions folder option at " +
        "your editor's Extensions folder and this column says whether " +
        "the editor here has each module." +
        (folderSet ? "" : " Click to go to that option.");
      if (!folderSet) {
        // The field this points at is two collapsed disclosures away;
        // a pointer that opens them beats directions to them.
        mark.classList.add("kb-linkish");
        mark.addEventListener("click", revealMmf2FolderOption);
      }
    } else if (row.installed && row.unversioned) {
      // Present, but nothing readable inside it. A weaker answer than
      // "installed", and it is the honest one: this check reads the
      // module's version resource, and a module that has none has
      // something wrong that the editor may well object to.
      mark.className = "kb-ext-caution";
      mark.textContent = "present, no version";
      mark.dataset.tip =
        "The file is in your Extensions folder, but no version could be " +
        "read out of it, which usually means something inside it is " +
        "damaged. The editor may still ask for this module when it opens " +
        "the project. Replacing it with a good copy is the fix." +
        (row.installed_path ? " " + row.installed_path : "");
    } else if (row.installed) {
      mark.className = "kb-ext-ok";
      mark.textContent = "installed" + (row.version ? " " + row.version : "");
      if (row.installed_path) mark.dataset.tip = row.installed_path;
    } else {
      mark.className = "kb-ext-missing";
      mark.textContent = "not installed";
      const misses = (row.near_misses || []);
      mark.dataset.tip =
        "The editor will ask for this module when it opens the project. " +
        "Install it in your Extensions folder" +
        (allowStrip()
          ? ", or tick Remove to leave its objects and events out."
          : ". If nobody can supply it, the Recovery option 'Allow " +
            "removing extension modules from a game' lets you leave its " +
            "objects and events out instead.") +
        (misses.length
          ? " Installed under another name? " +
            misses.map(([n, t]) => n + " (" + (t || "no title") + ")").join(", ") +
            " - a different release, not a substitute: the project names " +
            "the module by filename."
          : "");
    }
    installed.appendChild(mark);
    tr.appendChild(installed);

    if (allowStrip()) {
      const remove = document.createElement("td");
      remove.className = "kb-ext-remove";
      const tick = document.createElement("input");
      tick.type = "checkbox";
      tick.checked = file.strip.has(row.module);
      tick.disabled = state.running;
      tick.dataset.tip = REMOVE_TIP;
      tick.setAttribute("aria-label",
        "Remove " + row.module + " from the project");
      tick.addEventListener("change", () => {
        if (tick.checked) file.strip.add(row.module);
        else file.strip.delete(row.module);
        renderQueue();
        renderExtensions(file);
      });
      remove.appendChild(tick);
      tr.appendChild(remove);
    }
    tbody.appendChild(tr);
  }
  table.appendChild(tbody);
  group.appendChild(table);

  // Said in full the moment anything is ticked, where the tick is.
  if (file.strip.size) {
    const warn = document.createElement("div");
    warn.className = "kb-ext-warning";
    const chosen = [...file.strip].join(", ");
    warn.textContent =
      "Removing " + chosen + " from this project: every object of " +
      (file.strip.size === 1 ? "this module" : "these modules") +
      " and every event line and action that used them will be left " +
      "out, and cannot be put back from the output. The game file is " +
      "untouched; the project is written as " +
      file.name.replace(/\.[^.]+$/, "") + ".decompiled.stripped.mfa, " +
      "beside any complete recovery. Installing the module instead " +
      "keeps everything.";
    group.appendChild(warn);
  }
}

/* Open the collapsed disclosures between a card's "set the folder below"
 * and the field it means, then hand the keyboard to the field. */
function revealMmf2FolderOption() {
  const details = el("mmf2-extensions-option");
  details.open = true;
  details.scrollIntoView({ behavior: "smooth", block: "nearest" });
  el("mmf2-ext-dir").focus();
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
  const applied = result.applied || [];
  const { expected, notable, info, stripped } = classifyFile(file);
  // Counts include what the condensed entries stand for, so the summary
  // still says 46,000 where the list shows a dozen lines.
  const notableCount = tally(notable);
  const expectedCount =
    [...expected.values()].reduce((n, entries) => n + tally(entries), 0);
  const infoCount = tally(info);
  // Options-in-force lives on its own line now, so Details is hidden the
  // moment there is nothing to actually review -- a clean game no longer
  // claims it has something worth opening.
  lossDetails.classList.toggle("kb-hidden",
    !notable.length && !expectedCount && !info.length && !stripped.length &&
    !noteText);

  // The summary is generated from counts. Removals come first because they
  // are the one line that describes a choice rather than a limit.
  const parts = [];
  if (stripped.length) parts.push("modules removed, as asked");
  if (notableCount) {
    parts.push(fmt(notableCount) + " thing" +
      (notableCount === 1 ? "" : "s") + " worth reading");
  }
  if (expectedCount) {
    parts.push(fmt(expectedCount) + " expected compile loss" +
      (expectedCount === 1 ? "" : "es") + " (normal)");
  }
  el("loss-summary").textContent = parts.length
    ? "Details - " + parts.join(", ")
    : (infoCount
      ? "Details - " + fmt(infoCount) + " note" +
        (infoCount === 1 ? "" : "s") + " about the recovery"
      : "Details - what to try next");

  const strippedBox = el("stripped-box");
  strippedBox.textContent = "";
  strippedBox.classList.toggle("kb-hidden", stripped.length === 0);
  if (stripped.length) {
    const head = document.createElement("div");
    head.className = "kb-stripped-head";
    head.textContent = "Removed from this project, at your request";
    strippedBox.appendChild(head);
    const items = document.createElement("ul");
    for (const entry of stripped) {
      const item = document.createElement("li");
      item.textContent = lineText(entry);
      items.appendChild(item);
    }
    strippedBox.appendChild(items);
    const why = document.createElement("div");
    why.className = "kb-stripped-note";
    why.textContent =
      "This content is not in the output and cannot be put back from it. " +
      "The game file is untouched, and a complete recovery is one run " +
      "away: install the module in your MMF 2.0 Extensions folder and " +
      "decompile again with nothing ticked for removal.";
    strippedBox.appendChild(why);
  }

  const list = el("loss-list");
  list.textContent = "";
  for (const entry of notable) {
    const item = document.createElement("li");
    item.textContent = lineText(entry);
    list.appendChild(item);
  }
  const expectedBox = el("expected-losses");
  expectedBox.textContent = "";
  expectedBox.classList.toggle("kb-hidden", expectedCount === 0 && !info.length);
  if (expectedCount) {
    const note = document.createElement("div");
    note.className = "kb-expected-note";
    note.textContent =
      "These are normal. Compiling a game throws this content away for " +
      "good, so every compiled game is missing it whatever decompiles " +
      "it; KlikBack writes safe stand-ins where it can.";
    expectedBox.appendChild(note);
    for (const [kind, entries] of expected) {
      expectedBox.appendChild(foldedList(
        kind.label + " - " + kind.why + " (" + fmt(tally(entries)) + ")",
        entries));
    }
  }
  if (info.length) {
    expectedBox.appendChild(foldedList(
      "What was recovered, and from where (" + fmt(infoCount) + ")", info));
  }

  // Which options shaped THIS file -- its family's, not the whole
  // window's. In a mixed batch that is the only honest answer to "what
  // did my settings do to this game".
  const appliedBox = el("applied-box");
  appliedBox.textContent = "";
  appliedBox.classList.toggle("kb-hidden", applied.length === 0);
  if (applied.length) {
    appliedBox.appendChild(foldedList(
      "Options in force for this file (" + (applied.length - 1) + ")",
      applied));
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
      : "The clipboard refused the report - use Save log instead.");
  };
}

/* A collapsed heading with a list under it -- the shape every group in the
 * Details block takes. Takes plain strings (the options list) and
 * condensed {text, more} entries alike. */
function foldedList(heading, lines) {
  const group = document.createElement("details");
  const summary = document.createElement("summary");
  summary.textContent = heading;
  group.appendChild(summary);
  const items = document.createElement("ul");
  for (const line of lines) {
    const item = document.createElement("li");
    item.textContent = typeof line === "string" ? line : lineText(line);
    items.appendChild(item);
  }
  group.appendChild(items);
  return group;
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
    repair_object_data: el("opt-repairobjectdata").checked,
    repack_placement: el("opt-repackplacement").checked,
    drop_missing_assets: el("opt-dropmissing").checked,
    extension_dirs: el("ext-dir").value.trim()
      ? [el("ext-dir").value.trim()] : [],
    // MMF 2.0. Two folders for two installs: the 1.5 one above holds .cox
    // files and serves 1.0/1.5 names; this one holds .mfx files and
    // serves 2.0 icons and the card's installed column. The worker hands
    // each to its own family only.
    mmf2_extension_dir: mmf2Folder(),
    section_labels: el("opt-sectionlabels").checked,
    // A window-side gate only: it decides whether the cards show a Remove
    // column, and the worker never sees it. The removals themselves go
    // through `collectStrips`.
    allow_strip: allowStrip(),
  };
}

/* The one per-file option, keyed by path: which modules each 2.0 game
 * has ticked for removal. Kept out of the saved settings on purpose -- a
 * removal belongs to a game, not to the window. */
function collectStrips() {
  const strips = {};
  if (!allowStrip()) return strips;
  for (const file of state.files) {
    if (file.strip && file.strip.size) strips[file.path] = [...file.strip];
  }
  return strips;
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
    file.notes = [];
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
  const accepted = await bridge.call(
    "start", paths, { ...options, strip_for: collectStrips() });
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
      setRunStatus(noun + " " + event.n + " of " + event.of + " - " +
        (STAGE_TEXT[event.stage] || event.stage).toLowerCase(), false);
      break;
    }
    case "loss": {
      const file = fileByPath(state.currentPath);
      if (file) file.losses.push({ text: event.text, more: event.more || 0 });
      break;
    }
    case "note": {
      // The 2.0 engine's report lines -- substitutions, what was merged,
      // what was removed. Kept apart from losses because they are sorted
      // differently: a removal is shown first, information last.
      const file = fileByPath(state.currentPath);
      if (file) file.notes.push({ text: event.text, more: event.more || 0 });
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
          file.status = state.cancelling ? "cancelled" : "not run";
        }
      });
      renderQueue();
      if (state.cancelling) {
        setStatus("Cancelled");
      } else if (state.blocked) {
        setStatus("Nothing was decompiled - see below.");
        showBlocked(state.blocked);
      } else if (!state.sawResult && event.returncode !== 0) {
        setStatus("The worker crashed - details below.");
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
    "untouched - fix the file below and run it again.";
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
    "This is not a refusal - it is a fault worth reporting. " +
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
  const title = text ? PRODUCT_TITLE + " - " + text : PRODUCT_TITLE;
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
  const named = state.batchName ? state.batchName + " - " + text : text;
  setStatus(named, announce);
}

function renderStatus() {
  const base = state.statusBase || "";
  const field = el("status-main");
  field.textContent = state.running
    ? base.replace(/[.…]+$/, "") + ELLIPSIS[state.tick % ELLIPSIS.length]
    : base;
  // The field cannot wrap, so a long message - a saved path, a TGF/CnC game
  // with a sentence for a filename - is cut with an ellipsis. Then it must
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
    ].filter(Boolean).join(" - "));
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
  // The button carries the count in a batch -- and when strangers will be
  // skipped, says so before the run rather than letting the tally explain
  // it afterwards. A single file keeps the plain verb: even a stranger
  // named alone gets a full answer, so there is nothing to count.
  const total = state.files.length;
  const runnable = state.files.filter(
    (file) => file.inspection.decompilable).length;
  el("go-button").textContent =
    total <= 1 ? "Decompile"
      : runnable < total ? "Decompile " + runnable + " of " + total
        : "Decompile " + total + " files";
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
  set("opt-repairobjectdata", "repair_object_data", false);
  set("opt-repackplacement", "repack_placement", false);
  set("opt-dropmissing", "drop_missing_assets", false);
  set("opt-sectionlabels", "section_labels", true);
  set("opt-allowstrip", "allow_strip", false);
  el("out-dir").value = state.settings.out || "";
  el("ext-dir").value = (options.extension_dirs || [])[0] || "";
  el("mmf2-ext-dir").value = options.mmf2_extension_dir || "";
}

function saveSettings(options) {
  // Never the per-game removals: those are keyed by path and belong to
  // the games in the list, not to the window.
  const { strip_for: ignored, ...remembered } = options;
  state.settings.options = remembered;
  state.settings.out = options.out || "";
  bridge.call("save_settings", state.settings).catch(() => {});
}

/* Settings used to be written at exactly two moments: when a run started,
 * and when files were added. Nowhere else -- not on quit, not when an
 * option changed. So a cold launch, tick an option, close left no
 * settings file at all, which is the ordinary "it forgot everything I
 * set" complaint and was entirely real.
 *
 * Every control now writes through. It is a small JSON file beside the
 * exe and a person can only click so fast, but a text field fires on
 * every keystroke, so the write is held back until typing stops. `flush`
 * exists for the window closing, where there is no later. */
let settingsTimer = null;

function rememberSettings(delay) {
  window.clearTimeout(settingsTimer);
  settingsTimer = window.setTimeout(
    () => saveSettings(collectOptions()), delay || 0);
}

function flushSettings() {
  window.clearTimeout(settingsTimer);
  settingsTimer = null;
  saveSettings(collectOptions());
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
    "Empty this list. It only forgets the paths - no file is touched.";
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
    setStatus("No native dialogs in the dev preview - use the path box.");
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
      setStatus("No native dialogs in the dev preview - " +
        "type the folder.");
      return;
    }
    const chosen = await bridge.call("browse_folder");
    if (chosen) el("out-dir").value = chosen;
  });
  el("ext-browse").addEventListener("click", async () => {
    if (state.harness) {
      setStatus("No native dialogs in the dev preview - " +
        "type the folder.");
      return;
    }
    const chosen = await bridge.call("browse_folder");
    if (chosen) el("ext-dir").value = chosen;
  });
  el("mmf2-ext-browse").addEventListener("click", async () => {
    if (state.harness) {
      setStatus("No native dialogs in the dev preview - " +
        "type the folder.");
      return;
    }
    const chosen = await bridge.call("browse_folder");
    if (chosen) {
      el("mmf2-ext-dir").value = chosen;
      reinspectMmf2();
    }
  });
  // The card's installed column answers from this folder, so a change
  // here re-reads every 2.0 game in the list.
  el("mmf2-ext-dir").addEventListener("change", reinspectMmf2);
  el("opt-allowstrip").addEventListener("change", onAllowStripChange);

  /* Remember every option the moment it changes -- see rememberSettings.
   * Driven off the form itself rather than a list of ids, so an option
   * added later cannot be forgotten by omission: that is exactly how
   * `--no-subapps` came to have no control and no saved key. Text fields
   * wait for typing to stop; ticks are written at once. */
  document.querySelectorAll("input, select, textarea").forEach((control) => {
    const typed = control.type === "text" || control.tagName === "TEXTAREA";
    control.addEventListener("change", () => rememberSettings(0));
    if (typed) control.addEventListener("input", () => rememberSettings(700));
  });
  // And once more on the way out, for anything still inside the
  // hold-back window. Whether an embedded browser runs these on the way
  // to being destroyed is not something to rely on, which is why the
  // change handlers above are the actual fix and these are a backstop:
  // by the time either fires, everything but the last few hundred
  // milliseconds of typing is already on disk.
  window.addEventListener("beforeunload", flushSettings);
  window.addEventListener("pagehide", flushSettings);

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
      setStatus("Dropping needs the app window - in the dev preview, " +
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
  setStatus("Ready - " + config.product + " " + config.version +
    (state.harness ? " (dev preview)" : ""));
  if (config.autorun && config.autorun.length) {
    await addPaths(config.autorun);
    if (config.autostart) go();
  }
  updateButtons();
})();
