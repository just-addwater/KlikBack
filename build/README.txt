KlikBack 1.1.2
==============

KlikBack turns a compiled Clickteam game back into an editable project.
It reads Multimedia Fusion 1.0, 1.5 and 2.0 standalones (.exe, .ccn) and
The Games Factory / Click & Create / Multimedia Fusion Express games,
including protected .gam/.cca data files.

Clickteam Fusion 2.5 and later pack their games a different way (the
Unicode runtime) and KlikBack does not read them. It does recognise
them: point it at one and it says so by name, with the build number,
rather than failing part way in.

By Justaddwater -- https://github.com/just-addwater/KlikBack


Quick start
-----------

KlikBack.exe        the app: drop a game (or a whole folder) on the
                    window, check the options, press Decompile.
klikback-cli.exe    the same engine from a console:

    klikback-cli "C:\old games\MyGame.exe"
    klikback-cli --identify "C:\old games"
    klikback-cli --help

The rebuilt project (.cca, .gam or .mfa) is written next to the game,
with a <name>.decompiled.log saying what was recovered and which options
were in force. KlikBack never overwrites the game itself or an existing
project file.

--identify is an option, not a sub-command. Exit codes, for scripting:

    0   everything you named was understood, nothing needs attention
    1   KlikBack itself went wrong, or its folder or flags need fixing
    2   something you named could not be read or recognised
    3   a game was read and could not be rebuilt
    4   a Clickteam product KlikBack does not support (Fusion 2.5+)

A 3 may change with a different setting or a newer KlikBack; a 4 will
not. --identify reports the same code a real run would.


"Windows protected your PC" (SmartScreen)
-----------------------------------------

Windows shows this for any downloaded program it has not seen before,
because KlikBack is not code-signed. Click "More info", then "Run
anyway". Some antivirus products are similarly suspicious of
PyInstaller-built programs; the source is public at the link above if
you would rather audit or build it yourself.


If the window does not open
---------------------------

KlikBack shows the actual error it met. Two things to check, in order:

  * Whether Windows has marked the files as downloaded. A zip fetched
    with a browser carries that mark, Explorer copies it onto every
    file it extracts, and the window cannot load one of its own
    components while it is set -- the command line is unaffected.
    KlikBack asks, once, whether to clear that mark from its own
    files, and does nothing unless you say yes. It is the same thing
    as right-clicking the folder, Properties, Unblock. You can also
    unblock the ZIP before extracting it, which avoids the whole
    thing.

  * The Microsoft Edge WebView2 runtime, which the window needs and
    which is part of every up-to-date Windows 10 and 11. If the error
    names it, install it from:

        https://developer.microsoft.com/microsoft-edge/webview2/

klikback-cli.exe works without the window either way.


Portable
--------

KlikBack is a plain folder: no installer, no registry, nothing outside
it. Settings live in klikback.json beside the exe. It never touches the
network. To uninstall, delete the folder.


Mixed batches: which options apply to which game
------------------------------------------------

You can drop games of every family KlikBack reads into one list. Every
option applies to the whole run, each game is handled by the pipeline
its own family needs, and an option that family does not have is
ignored for that game -- so a batch is predictable. In the window, each
block of recovery options is headed by the family it applies to and
appears once a game of that family is listed, and each game's report
lists the options that were in force for it. The one choice made per
game rather than per run is which extension modules to remove from an
MMF 2.0 game; see below.


The "MMF 1.5 Extensions folder" option
--------------------------------------

Multimedia Fusion 1.0 and 1.5 games carry their extension objects (.cox
files), but often not the display names the editor shows for them. If
you have Multimedia Fusion 1.5 installed, you can point this option at
its Extensions folder (for example C:\Multimedia Fusion\Extensions) and
KlikBack will read the display names from your installed copies. It
also warns when an installed extension is older than the one the game
was built with, since an older extension can display the rebuilt
project's events incorrectly.

KlikBack only ever READS that folder. Leave the option blank (the
default) to skip the scan: games still decompile, with names recovered
from the game itself where possible and the extension's filename
standing in otherwise.


The "MMF 2.0 Extensions folder" option
--------------------------------------

A different install for a different job. Point this option at your
Multimedia Fusion 2 Extensions folder -- the folder itself, the one
holding the .mfx files, for example
    C:\Multimedia Fusion 2\Extensions
-- and two things happen:

  * an extension object gets its module's own icon, as the editor
    draws it, instead of a stand-in from the artwork folder;

  * a 2.0 game's card lists the modules it needs and says which your
    editor has, by name and version. One the folder lacks is named:
    the editor will ask for it. One present but with no version could
    not be read properly, and may be refused too.

KlikBack only ever READS that folder, and never goes looking for one:
the folder you give is the only one it opens.

A 2.0 game carries the RUNTIME build of each module, which plays the
game but the editor cannot load; those are carved out beside the
project (<name>.extracted\Extensions) when extraction is on.


Removing an extension from an MMF 2.0 game
------------------------------------------

Some games need an extension nobody can get any more, and the editor
then refuses to open the rebuilt project at all. For that case there is
an option under Recovery options, off by default: "Allow removing
extension modules from a game". With it on, a 2.0 game's card gains a
"Remove" column; tick one and the project is written WITHOUT that
module -- every object of it, every event line and action that used
those objects, and the module's declaration. The editor then opens it.
Turning the option off again clears every tick.

Know what that costs before ticking it:

  * the removed content is the author's, and nothing can put it back
    from the file KlikBack wrote;
  * the game itself is untouched, and a complete recovery is one run
    away: install the module and decompile again with nothing ticked;
  * it is written as <name>.decompiled.stripped.mfa, so it never
    overwrites a complete recovery beside it;
  * the report says in its first lines exactly what was removed.

Nothing is ever ticked for you, and the choice belongs to one game, so
it is made on that game's card. On the command line,
--strip-extension MODULE.mfx does the same; a name the game does not
use is refused, with the list of what it does use.


If the copy you have is incomplete
----------------------------------

Plenty of TGF/CnC games were downloaded over connections that gave up
partway. The file looks complete -- it opens, it has a name, every
level is in it -- but its last sound or image bank runs off the end.
KlikBack says so instead of guessing:

    TGF/CnC game data, an incomplete copy
    TRUNCATED FILE: the final segment 000D (sound-bank) ... 92.1 %

By default it stops there, because what is missing is the game's own
content and throwing it away should be your decision. Tick "TGF/CnC:
open an incomplete copy" and it rebuilds the project without the assets
whose bytes are not in the file. Nothing is invented, nothing else
moves, and the report names every slot dropped and every one kept.

A complete copy of the same game, if you can find one, loses nothing.


The artwork folder
------------------

In the editor, every object shows a small icon, and KlikBack draws it
from the object's own picture wherever the game has one. Some object
types have no picture (a Counter, a String), so for those it
substitutes a drawing from the artwork\ folder beside KlikBack.exe. The
same drawings serve MMF 2.0 games, except that an extension object
takes its module's own icon when the MMF 2.0 Extensions folder is set.

That folder is yours to change: replace a PNG with your own and the
icons change. There is nothing else to run.

What is in it
.............

    string.png    String and Text objects
    counter.png   Counters
    lives.png     Lives displays
    score.png     Score displays
    other.png     everything else with no picture of its own

Four of the types that fall back to other.png can have an icon of their
own instead. Add a file with the matching name, and KlikBack picks it
up:

    qanda.png     ftext.png    subapp.png    extension.png

extension.png covers every object provided by an extension module. A
name that does not apply to the game you are decompiling is simply
unused, so it is safe to add all of them.

The format
..........

    Size          32 x 32 pixels. Multimedia Fusion games refuse any
                  other size and name the file; TGF/CnC games scale
                  whatever they are given into a slightly smaller box.
    Type          PNG, 8 bits per channel: full colour, full colour
                  with an alpha channel, or a 256-colour palette. Not
                  interlaced, and not greyscale.
    Transparency  an alpha channel (under half opaque reads as
                  transparent), or bright green, matched by dominance
                  rather than one exact value so anti-aliased edges
                  stay clean.
    Colour        snapped to the editor's own fixed palette, so flat
                  strong colours survive best and subtle gradients may
                  shift noticeably.

The whole 32 x 32 is used, so draw to the edges rather than leaving a
margin.

If a file is missing, or wrong
..............................

other.png is the one file KlikBack will not run without, since it is
what everything falls back to; re-extract the zip to restore it. Every
other name is optional, and deleting one just returns those objects to
other.png.

A drawing that does not fit the format above stops the run before any
game is read, naming the file and what to change. Nothing is written
and the game is untouched. Every name is checked, whether or not the
game uses it.

A second copy of these drawings lives in _internal\ and is the one the
engine reads. KlikBack refreshes it from the visible folder at every
start, so editing artwork\ is enough (on a read-only install that copy
is skipped and the built-in drawings are used). It only goes one way,
so removing a drawing entirely takes both folders -- KlikBack says so
and names them.


Licence, and what it does not cover
----------------------------------

KlikBack is free software under the GNU General Public License, version
3 or later. It comes with NO WARRANTY. The source and the full licence
text are at the link above; if you distribute a modified KlikBack you
must publish your changes under the same licence.

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

The format knowledge behind KlikBack was worked out here, and its output
is generated rather than taken from an existing project.

The vocabulary of the format itself is another matter, and does travel.
Any file the editor will open has to carry things like the runtime's
class names, the object type labels and the standard animation slot
names, and a file without them is not one the editor can open.
Reproducing them is what reading and writing the format means.
