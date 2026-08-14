# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""Runtime hook: let the visible artwork/ folder override the bundled one.

Drop-in PNG customisation is an engine feature ("a PNG in this folder is
enough"), so the zip ships a user-editable artwork/ folder beside the exes.
The engine itself resolves artwork relative to its own package, which in a
frozen build lands inside _internal/. This hook bridges the two at startup:
any file in the exe-adjacent artwork/ is copied over its _internal twin
when the bytes differ. Every failure is swallowed -- a read-only install
simply runs with the bundled artwork.
"""

import os
import sys

def _seed_artwork():
    visible = os.path.join(os.path.dirname(sys.executable), "artwork")
    internal = os.path.join(sys._MEIPASS, "klikback", "core", "artwork")
    if not os.path.isdir(visible) or not os.path.isdir(internal):
        return
    for name in os.listdir(visible):
        source = os.path.join(visible, name)
        target = os.path.join(internal, name)
        if not os.path.isfile(source):
            continue
        try:
            with open(source, "rb") as handle:
                data = handle.read()
            try:
                with open(target, "rb") as handle:
                    if handle.read() == data:
                        continue
            except OSError:
                pass
            with open(target, "wb") as handle:
                handle.write(data)
        except OSError:
            continue

_seed_artwork()
del _seed_artwork
