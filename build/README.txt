KlikBack 1.0.0
==============

KlikBack turns a compiled Clickteam game back into an editable
project. It reads Multimedia Fusion 1.0 and 1.5 standalones (.exe, .ccn)
and The Games Factory / Click & Create / Multimedia Fusion Express
games, including protected .gam/.cca data files.

Multimedia Fusion 2 and later Clickteam products pack their games a
different way, and KlikBack does not read them. It does recognise them:
point it at one and it says so by name rather than failing part way in.

By Justaddwater -- https://github.com/just-addwater/KlikBack


Quick start
-----------

KlikBack.exe        the app: drop a game (or a whole folder) on the
                    window, check the options, press Decompile.
klikback-cli.exe    the same engine from a console:

    klikback-cli "C:\old games\MyGame.exe"
    klikback-cli --identify "C:\old games"
    klikback-cli --help

The rebuilt project (.cca or .gam) is written next to the game, along
with a <name>.decompiled.log describing exactly what was recovered.
KlikBack never overwrites the game itself or an existing project file.


"Windows protected your PC" (SmartScreen)
-----------------------------------------

Windows shows this for any downloaded program it has not seen before,
because KlikBack is not code-signed (signing certificates cost money).
Click "More info", then "Run anyway". Some antivirus products are
similarly suspicious of PyInstaller-built programs; the source is public
at the link above if you would rather audit or build it yourself.


If the window does not open
---------------------------

KlikBack's interface needs the Microsoft Edge WebView2 runtime, which is
part of every up-to-date Windows 10 or 11. If KlikBack reports it is
missing, install it from:

    https://developer.microsoft.com/microsoft-edge/webview2/


Portable
--------

KlikBack is a plain folder: no installer, no registry, nothing outside
it. Settings live in klikback.json beside the exe. It never touches the
network. To uninstall, delete the folder.


The "Installed Extensions folder" option
----------------------------------------

Games built with extension objects (.cox files) carry the extensions
themselves, but often not the display names the editor shows for them.
If you have Multimedia Fusion installed, you can point this option at
its Extensions folder (for example C:\Multimedia Fusion\Extensions) and
KlikBack will read the display names from your installed copies. It
also compares versions and warns you when an installed extension is
older than the one the game was built with, since an older extension
can display the rebuilt project's events incorrectly.

KlikBack only ever READS that folder. Nothing in it is copied,
modified, or written to your output.

Leave the option blank (the default) to skip the scan entirely. Games
still decompile: names are recovered from the game itself where
possible, and the extension's filename stands in otherwise.


If the copy you have is incomplete
----------------------------------

Plenty of 1996-era games were downloaded over connections that gave up
partway. The file that results looks complete -- it opens, it has a
name, every level is in it -- but its last sound or image bank runs off
the end of the file. KlikBack says so instead of guessing:

    1996-era game data, an incomplete copy
    TRUNCATED FILE: the final segment 000D (sound-bank) ... 92.1 %

By default it stops there, because what is missing is the game's own
content and throwing it away should be your decision rather than
KlikBack's. Tick "TGF/CnC: open an incomplete copy" and it rebuilds the
project without the assets whose bytes are not in the file. Nothing is
invented, nothing else in the file moves, and the report names every
slot dropped and every one kept.

A complete copy of the same game, if you can find one, loses nothing --
so it is worth looking before settling for this.


The artwork folder
------------------

In the editor, every object shows a small icon. KlikBack draws that icon
from the object's own picture wherever the game has one -- an Active
from its first animation frame, a Backdrop from its image. Some object
types have no picture of their own (a Counter, a String), so for those
KlikBack substitutes a drawing from the artwork\ folder beside
KlikBack.exe.

That folder is yours to change. Replace a PNG with your own and the
icons change; there is nothing else to run.

What is in it
.............

    string.png    String and Text objects
    counter.png   Counters
    lives.png     Lives displays
    score.png     Score displays
    other.png     everything else with no picture of its own

other.png is the fallback: it is what a Question & Answer, Formatted
Text, Sub-Application or extension object gets by default.

You can give any of those its own icon by adding a file with the right
name. KlikBack looks for these too, and falls back to other.png for any
it does not find:

    qanda.png     ftext.png    subapp.png    extension.png

extension.png covers every object provided by an extension module. A
name that does not apply to the game you are decompiling is simply
unused, so it is safe to add all of them.

The format
..........

    Size          32 x 32 pixels. Multimedia Fusion games refuse any
                  other size and name the file; 1996-era games instead
                  scale whatever they are given down into a slightly
                  smaller box. 32 x 32 is the size that works
                  everywhere.
    Type          PNG, 8 bits per channel: full colour, full colour with
                  an alpha channel, or a 256-colour palette. Not
                  interlaced, and not greyscale.
    Transparency  either an alpha channel (anything under half opaque
                  reads as transparent) or bright green, which the two
                  supplied drawings use. Green is matched by dominance
                  rather than one exact value, so anti-aliased edges
                  stay clean.
    Colour        colours are snapped to the editor's own fixed palette.
                  Flat, strong colours survive that best; subtle
                  gradients and near-greys may shift noticeably.

The whole 32 x 32 is used as the icon, so draw to the edges rather than
leaving a margin.

If a file is missing, or wrong
..............................

other.png is the one file KlikBack will not run without, because it is
what everything falls back to: if it is gone you get a message naming
it, not a broken project. Re-extract the zip to restore it.

Every other name is optional. Delete string.png and String objects
quietly fall back to other.png; that is the same mechanism that lets you
add qanda.png later.

A drawing that is there but does not fit the format above -- the wrong
size, not really a PNG, saved as greyscale or interlaced -- stops the
run at the very start, before any game is read, with a message naming
the file, its size and what to change. Nothing is written and the game
is untouched: fix the file and start again. Every name in the list is
checked, whether or not the game you are about to decompile uses it.

There is a second copy of these drawings inside _internal\, which is the
one the engine actually reads. You do not need to touch it: at every
start KlikBack copies anything in the visible artwork\ folder over its
internal twin when the two differ, so editing the visible folder is
always enough. On a read-only install that copy is skipped and the
built-in drawings are used.

That copy only goes one way. Deleting a drawing from the visible folder
therefore leaves the last copy of it inside _internal\, still in use --
so if you want a name gone rather than corrected, KlikBack will say so
and name both folders.


Licence, and what it does not cover
----------------------------------

KlikBack is free software under the GNU General Public License, version 3
or later. It comes with NO WARRANTY. The source and the full licence text
are at the link above; if you distribute a modified KlikBack you must
publish your changes under the same licence.

KlikBack claims no rights in its output. The GPL applies only to
KlikBack. Decompilation does not grant rights in the original game, its
assets, or extracted extension modules; use and redistribute them only
when authorised.

This folder also bundles a Python interpreter, pywebview, OpenSSL and
several Microsoft components, each under its own licence.
THIRD-PARTY-NOTICES.txt lists them and licenses\ holds their texts.

  * Use only with games you own or are authorised to analyse.
  * Intended for lawful interoperability, recovery, research and
    preservation.
  * Not affiliated with or endorsed by Clickteam.
  * Clickteam and product names are trademarks of their respective
    owners.
  * Extracted modules remain subject to their original licences.


Where the format knowledge comes from
-------------------------------------

What KlikBack writes is built from scratch rather than copied from an
existing project, and the understanding of the format behind it is this
project's own work.

The vocabulary of the format itself is another matter, and does travel.
Any file the editor will open has to carry things like the runtime's
class names, the object type labels and the standard animation slot
names, and a file without them is not one the editor can open.
Reproducing them is what reading and writing the format means.
