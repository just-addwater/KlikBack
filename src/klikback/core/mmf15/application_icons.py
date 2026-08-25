# GENERATED — do not edit by hand. This file is produced by KlikBack's
# sync tooling; changes belong in the source it is generated from.
#
# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""The application icons a 1.5 project carries -- the game's own Windows icons.
"""

from __future__ import annotations
from pathlib import Path
from klikback.core.common.pe_icon_probe import pe_resources

RT_ICON = 3

EXPECTED_ICONS = {
    1: (744, 32, 32, 4),
    2: (296, 16, 16, 4),
    3: (2216, 32, 32, 8),
    4: (1384, 16, 16, 8),
}

def icon_resources(exe: Path) -> dict[int, bytes]:
    """The icon images an executable carries, ready to become the project's."""
    return {
        res.name_id: res.data
        for res in pe_resources(exe)
        if res.type_id == RT_ICON
    }
