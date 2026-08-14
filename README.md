
<img width="836" height="464" alt="KBlogo" src="https://github.com/user-attachments/assets/66062c45-83cf-421b-bbc8-de65c25a6b37" />

# KlikBack: a decompiler for MMF,TGF,CnC Clickteam games

**Turn a compiled Multimedia Fusion 1.0/1.5, The Games Factory, MultiMedia Fusion Express or Click & Create
game back into an editable project.**

If you have an old Clickteam-era game and no longer have the source that
built it, KlikBack rebuilds it and recovers the source. Point it at the game's `.exe`, `.gam`,
`.cca` or `.ccn` and it writes a project file the original editor opens,
carrying the frames, objects, events, artwork, sounds and extension modules
that were inside the game.

> [!CAUTION]
> **KlikBack is a preservation tool. Use it on games you made, own the
> copyright to, or have the rights holder's permission to work on.
> Decompiling gives you no rights in a game, its assets, or the extension
> modules it carries.**

It runs offline on Windows, needs no copy of Multimedia Fusion installed,
and never modifies the game you point it at. There is a window and a
command line, and the packaged app is a plain folder with no installer.


## What it reads

|  | Input | Versions | What you get |
|:--:|---|---|---|
| ✅ | Multimedia Fusion **1.0 / 1.1 / 1.2** standalone (`.exe`) | Builds 87 to 98 | an editable `.cca`, written as build 98 |
| ✅ | Multimedia Fusion **1.5** standalone (`.exe`) or package (`.ccn`) | Builds 105 to 119 | an editable `.cca`, written as build 119 |
| ✅ | **The Games Factory** standalone | 1.00 to 1.06 | an editable `.gam`, unprotected |
| ✅ | **Click & Create** or **MMF Express** standalone | CnC 1.0 to 1.03, Express 1.04 to 1.06 | an editable `.cca`, unprotected |
| ✅ | A **Vitalize** `.ccn` | Fusion 1.0 or 1.5 | an editable `.cca` |
| ✅ | A **protected** `.gam` / `.cca` | TGF, CnC, Express | the same file with the protection undone |
| ✅ | An **incomplete** copy, a download that stopped early | TGF, CnC, Express | option for an attempted rebuilt without the assets whose bytes are missing |
| ❌ | Multimedia Fusion **2** and Clickteam Fusion **2.5** or later | | **not** supported |

*MMF Express is a rebranded Click & Create.*

Files are identified by **content, never by extension**: the signatures in
the file decide what it is, so a renamed or mislabelled game still reads
correctly, and something that only looks like a game is told apart from one
that is. The generation comes from the game's own package header, not from
the version stamp an author can overwrite.

Multimedia Fusion 2 and later pack a game a different way so KlikBack cannot read it. If you need to decompile them, try https://github.com/AITYunivers/NebulaFD. 

Extension modules (`.cox` / `.gox`) are carved out of the game itself, so a
game that needs an extension your machine has never had still comes back
with that extension beside it.

## Running it

Most people want the packaged app, a plain folder with no installer:
download the zip, unzip, run `KlikBack.exe`. Its own `README.txt` covers
the app, the SmartScreen warning, and the options.

From source, you need Python 3.13 or newer:

```bash
set PYTHONPATH=src
py -3 -m klikback.cli "C:\old games\MyGame.exe"
py -3 -m klikback.cli --identify "C:\old games"
py -3 -m klikback.cli --help
```

The command line is pure standard library, with no dependencies at all. The
window (`py -3 -m klikback.gui`) additionally needs `pywebview`, and on
Windows the Edge WebView2 runtime that ships with every up-to-date
Windows 10 and 11.

To build the packaged zip:

```bash
build\build.bat
```

Pinned build requirements are in `build/requirements-build.txt`; the output
lands in `build/dist/`.

## What a decompile actually gives you

**What comes back.** Every frame and its layout, every object and its
properties, the whole event sheet, the image and sound banks, the
application icons, and the extension modules the game was carrying. Object
icons are redrawn from each object's own artwork, which is how the editor
produced them in the first place.

**What compilation destroyed.** These are gone from the game file itself,
so nothing can return them:

| What | Why |
|---|---|
| Comment text | the compiler keeps the comment rows and their positions, and throws the words away |
| Editor-only pictures | object icons and frame preview thumbnails are not stored in a compiled game. Klikback attempts to recreate from ingame artwork |
| Global event page names | the events all survive and run as before; only the name of the page they were filed under is gone, so each one lands in its frame behind a clear label |
| Global value names | the runtime keeps the values and never the names, so they come back as `Global Value A`, `B`, `C` |

That list is the same for every compiled game, whatever reads it. What
KlikBack adds is telling you which of it applied to yours:

- **Losses are itemised, not summarised.** Every line beginning `loss:` in
  the session log is content the writer knew it dropped, named with the
  frame, object or row it belongs to. A game with losses is normal; the
  list tells you which ones matter for what you want to do.
- **A refusal is an honest outcome, not a crash.** Where a game uses
  something that cannot be reconstructed correctly, KlikBack names the
  feature and stops, instead of writing a project that opens and is quietly
  wrong.
- **Nothing is overwritten.** Neither the game nor an existing project file
  is ever written over unless you ask for it explicitly.


## Layout

```
src/klikback/
  api.py          the programmatic surface: inspect, decompile, options, results
  cli.py          the command line, and the GUI's worker process
  gui/            the window (pywebview shell) and the page it hosts
  resources.py    checks the bundled resources and explains what is missing
  core/           the decompilation engine
    mmf1/  mmf15/  tgf/  common/
    artwork/      the drawings used where a game has no icon of its own
build/            PyInstaller spec, build script, packaged README
branding/         logo and icon
```

### pywebview

Used because <img width="1672" height="929" alt="KBlogo" src="https://github.com/user-attachments/assets/242f7853-bac1-46c0-8812-810f175b4c89" />
I wanted a Windows 98 style UI. Not entirely happy with it.

### About `core/`

These modules carry a **GENERATED** header, and they are. They come from a
separate codebase, not part of this distribution. The generator strips its comments and writes these files with
documentation of their own, and an equivalence check proves the two sides
are the same program, differing only in prose.

So read `core/` as it stands, but do not hand-edit it: the next generation
overwrites whatever you change.

### Artwork

Some object types ship with no icon of their own. KlikBack draws every icon
it can from the game's own art, and falls back to the drawings in
`core/artwork/`, which are this project's own work. In the packaged app
that folder is visible beside the exe: replace a PNG and the substitutes
change.

Five of the nine names ship (`other.png`, `string.png`, `counter.png`,
`lives.png`, `score.png`); the other four are empty drop-in slots, filled
only by somebody who wants them. Each drawing is a 32x32 PNG, 8 bits per
channel, full colour or
256-colour palette, not interlaced, with transparency as an alpha channel or
bright green. `resources.py` holds every name either icon family knows to
that contract at startup, before a game is opened, because the alternative
is a decompile stopping partway through over a file the person editing it
never saw named.

## Provenance

What KlikBack writes is built from scratch rather than copied from an
existing project, and the format knowledge behind it was worked out here.

The vocabulary of the format itself is another matter, and does travel: any
file the editor will open has to carry things like the runtime's class
names, the object type labels and the standard animation slot names. They
are there because a file without them is not one the editor can read.

## Licence, and what it does not cover

KlikBack is free software: you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free
Software Foundation, either version 3 of the Licence, or (at your option)
any later version.

KlikBack is distributed in the hope that it will be useful, but **without
any warranty**, without even the implied warranty of merchantability or
fitness for a particular purpose. See the GNU General Public License for
more details. The full text is in [LICENSE](LICENSE).

In practice: use it for anything, including commercially, but if you
distribute a modified KlikBack you have to publish your changes under the
same licence.

**KlikBack claims no rights in its output. The GPL applies only to
KlikBack.** Decompilation does not grant rights in the original game, its
assets, or extracted extension modules; use and redistribute them only when
authorised.

- Use only with games you own or are authorised to analyse.
- Intended for lawful interoperability, recovery, research and preservation.
- Not affiliated with or endorsed by Clickteam.
- Clickteam and product names are trademarks of their respective owners.
- Extracted modules remain subject to their original licences.
