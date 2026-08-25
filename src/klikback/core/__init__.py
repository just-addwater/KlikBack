# GENERATED — do not edit by hand. This file is produced by KlikBack's
# sync tooling; changes belong in the source it is generated from.
#
# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""The decompilation engine: four product families over shared parts.

`mmf1` and `mmf15` rebuild editable projects from Multimedia Fusion
1.0 and 1.5 games; `mmf2` does the same for Multimedia Fusion 2,
whose project file is a different format again; `tgf` reads and
unprotects the 1996-era formats (The Games Factory, Click & Create,
MMF Express); `common` is what more than one of them needs.  Nothing
here knows about the user interface — `klikback.api` is the surface
everything else calls.
"""
