
<img width="557" height="310" alt="KBlogo" src="https://github.com/user-attachments/assets/66062c45-83cf-421b-bbc8-de65c25a6b37" />

# KlikBack: a decompiler for MMF, TGF, CnC Clickteam games

**Turn a compiled Multimedia Fusion 1.0/1.5/2.0, The Games Factory, Multimedia Fusion Express or Click & Create
game back into an editable project.**

If you have an old Clickteam made game and no longer have the source that built it, KlikBack rebuilds it and recovers the source. Point it at the game's `.exe`, `.gam`, `.cca` or `.ccn` and it writes a project file the original editor opens, carrying the frames, objects, events, artwork, sounds and extension modules that were inside the game.

### [Download the latest release](https://github.com/just-addwater/KlikBack/releases/latest)

> [!CAUTION]
> **KlikBack is a preservation tool. Use it on games you made, own the
> copyright to, or have the rights holder's permission to work on.
> Decompiling gives you no rights in a game, its assets, or the extension
> modules it carries.**

It runs offline on Windows, needs no copy of Multimedia Fusion installed, and never modifies the game you point it at. There is a window GUI and a command line, and the packaged app is a plain folder with no installer.


## What it reads

|  | Input | Versions | What you get |
|:--:|---|---|---|
| ✅ | Multimedia Fusion **1.0 / 1.1 / 1.2** standalone (`.exe`) | Builds 87 to 98 | an editable `.cca`, written as build 98 |
| ✅ | Multimedia Fusion **1.5** standalone (`.exe`) or (`.ccn`) | Builds 105 to 119 | an editable `.cca`, written as build 119 |
| ✅ | Multimedia Fusion **2.0** standalone (`.exe`)  | Builds 239 to 257 | an editable `.mfa`, written as build 250. HWA builds supported |
| ✅ | **The Games Factory** standalone | 1.00 to 1.06 | an editable `.gam`, unprotected |
| ✅ | **Click & Create** or **MMF Express** standalone | CnC 1.0 to 1.03, Express 1.04 to 1.06 | an editable `.cca`, unprotected |
| ✅ | A **Vitalize** `.ccn` | Fusion 1.0/1.5/2.0 | an editable `.cca` or `.mfa`|
| ✅ | A **protected** `.gam` / `.cca` | TGF, CnC, Express | the same file with the protection undone |
| ✅ | An **incomplete** copy, a download that stopped early | TGF, CnC, Express | option for an attempted rebuilt without the assets whose bytes are missing |
| ❌ | Clickteam Fusion **2.5** or later | | **not** supported |

**Newer Clickteam software is backward-compatible with projects created in earlier Clickteam products. A game created in The Games Factory can be opened in later versions of Clickteam software like MMF 1, 2 or later.**


Fusion 2.5 and later pack a game a different way so KlikBack cannot read it. If you need to decompile them, try https://github.com/AITYunivers/NebulaFD. 

Extension modules (`.cox` / `.gox` / `.mfx`) can be carved out of the game itself. Note that these extensions might be runtime versions, not editor ones. For any missing editor versions check: 

- CnC/TGF [Encyclofusion](https://encyclofusion.github.io/GET/) 
- MMF 1.0/1.5 [MMF Extension Archive](https://just-addwater.github.io/MMF-Extension-Archive/)
- MMF 2.0 [Darkwire](https://dark-wire.com/storage/extlist.php)

## Running it

Most people want the packaged app, a plain folder with no installer: [download the zip](https://github.com/just-addwater/KlikBack/releases/latest), unzip, run `KlikBack.exe`. Its own `README.txt` covers the app and the options.

| Version | SHA-256 |
|---|---|
| 1.1.2 .exe | f23fa8b4836a9483b296b25e97e1b23d284e26296c237a08f608c7e2c2cc1c47 |

From source, you need Python 3.13 or newer:

```bash
set PYTHONPATH=src
py -3 -m klikback.cli "C:\old games\MyGame.exe"
py -3 -m klikback.cli --identify "C:\old games"
py -3 -m klikback.cli --help
```

The command line is pure standard library, with no dependencies at all. The window (`py -3 -m klikback.gui`) additionally needs `pywebview`, and on Windows the Edge WebView2 runtime that ships with every up-to-date Windows 10 and 11.

To build the packaged zip:

```bash
build\build.bat
```

Pinned build requirements are in `build/requirements-build.txt`; the output
lands in `build/dist/`.

## What a decompile actually gives you

**What comes back.** Every frame and its layout, every object and its properties, the whole event sheet, the image and sound banks, the application icons, and the extension modules the game was carrying. Object icons are redrawn from each object's own artwork, which is how the editor produced them in the first place.

**What compilation destroyed.** These are gone from the game file itself, so nothing can return them:

| What | Why |
|---|---|
| Comment text | the compiler keeps the comment rows and their positions, and throws the words away |
| Editor-only pictures | object icons and frame preview thumbnails are not stored in a compiled game |
| Global event/Behaviour page names | the events all survive and run as before; only the name of the page they were filed under is gone, so each one lands in its frame behind a clear label |
| Global value names | the runtime keeps the values and never the names, so they come back as `Global Value A`, `B`, `C` |

*TGF/CnC V 1.00 exports seems to keep comment text*

## Layout

```
src/klikback/
  api.py          the programmatic surface: inspect, decompile, options, results
  cli.py          the command line, and the GUI's worker process
  gui/            the window (pywebview shell) and the page it hosts
  resources.py    checks the bundled resources and explains what is missing
  core/           the decompilation engine
    mmf1/  mmf15/  tgf/  mmf2/ common/
    artwork/      the drawings used where a game has no icon of its own
build/            PyInstaller spec, build script, packaged README
branding/         icon
```

### pywebview

Used because I wanted a Windows 98 style UI. Not entirely happy with it.

### About `core/`

core/ is generated and re-generated in place, so hand edits are overwritten.

### Artwork

Some object types ship with no icon of their own. KlikBack draws every icon it can from the game's own art, and falls back to the drawings in `core/artwork/`, which are this project's own work. In the packaged app that folder is visible beside the exe: replace a PNG and the substitutes change.

### Research Credits

| Name | Link |
|---|---|
| Valley Bell | [Link](https://forums.sonicretro.org/members/valleybell.10380/) |
| CTFAK2.0 | [Github](https://github.com/CTFAK/CTFAK2.0) |
| Anaconda | [Github](https://github.com/fnmwolf/Anaconda) |
| SourceExplorer | [Github](https://github.com/LAK132/SourceExplorer) |

## Licence, and what it does not cover

KlikBack is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 3 of the Licence, or (at your option) any later version.

KlikBack is distributed in the hope that it will be useful, but **without any warranty**, without even the implied warranty of merchantability or fitness for a particular purpose. See the GNU General Public License for more details. The full text is in [LICENSE](LICENSE). 

Prebuilt Windows packages include third-party runtime components. Their copyright notices and license terms are provided in THIRD-PARTY-NOTICES.txt and the accompanying licenses/ directory. These components remain the property of their respective authors and are distributed under their own licenses.

**KlikBack claims no rights in its output. The GPL applies only to
KlikBack.** Decompilation does not grant rights in the original game, its assets, or extracted extension modules; use and redistribute them only when authorised.


- KlikBack is intended for lawful preservation, interoperability, repair, and migration of software that you own or are otherwise authorized to examine.
- Some supported legacy formats describe projects as “protected.” KlikBack can convert these files into editable project formats. In this documentation, protected describes a technical state in the file format; it is not a legal conclusion about whether conversion is permitted in any particular country or situation.
- Not affiliated with or endorsed by Clickteam.
- Clickteam and product names are trademarks of their respective owners.
- Extracted modules remain subject to their original licences.
