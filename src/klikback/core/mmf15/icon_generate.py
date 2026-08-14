# GENERATED — do not edit by hand. This file is produced by KlikBack's
# sync tooling; changes belong in the source it is generated from.
#
# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""Draw 1.5 object icons and frame previews from the game's own artwork.

The 1.5 half of icon generation. An object's editor icon comes from the
picture that object actually uses, and a frame's thumbnail is rendered from
that frame's own background -- so both are derived from the game itself.

1.5 has its own measured rule for fitting art into the icon box, which is why
this exists separately from the 1.0 version rather than sharing it.
"""

from __future__ import annotations
import struct
from pathlib import Path
from klikback.core.common.icon_generate import build_icon_record, editor_image_pixels, halftone_quantise, imageless_icon_art, artwork_icon_indices, colorref_rgb, sample, source_rgb

ICON_BOX_15 = 32

ACTIVE_ICON_CONTENT_15 = 0x19652

BACKDROP_ICON_CONTENT_15 = 0x18319

RENDER_ICON_CONTENT_15 = 0x11320

OTHER_ICON_CONTENT_15 = 0x1DAB2

PREVIEW_CONTENT_15 = 0x15267

PREVIEW_WIDTH = 64

PREVIEW_HEIGHT = 48

PREVIEW_CONTENT_COLUMNS = 63

def icon_dimensions_15(width: int, height: int) -> tuple[int, int]:
    """The size art becomes once fitted into 1.5's icon box."""
    largest = max(width, height)
    if largest <= ICON_BOX_15:
        return width, height
    return (
        max(1, width * ICON_BOX_15 // largest),
        max(1, height * ICON_BOX_15 // largest),
    )

def icon_pixel_indices_15(record: bytes, palette: bytes, dest_width: int,
                          dest_height: int) -> list[int]:
    """The icon's pixels as palette entries, ready to store."""
    width, height, mode, rows = editor_image_pixels(record)
    indices: list[int] = []
    for y in range(dest_height):
        row = rows[sample(y, height, dest_height)]
        for x in range(dest_width):
            rgb = source_rgb(mode, row, sample(x, width, dest_width), palette)
            indices.append(0 if rgb is None else halftone_quantise(rgb))
    return indices

def icon_from_image_15(record: bytes, palette: bytes, handle: int,
                       content: int) -> bytes:
    """Build an object's icon from a picture the object uses."""
    width, height = struct.unpack_from("<HH", record, 10)
    dest_width, dest_height = icon_dimensions_15(width, height)
    return build_icon_record(
        handle, content, dest_width, dest_height,
        icon_pixel_indices_15(record, palette, dest_width, dest_height),
    )

def quick_backdrop_icon_15(
    payload: dict, palette: bytes, handle: int,
    images_by_id: dict[int, bytes] | None = None,
    width: int | None = None, height: int | None = None,
    content: int = RENDER_ICON_CONTENT_15,
) -> bytes:
    """Draw the icon for an object that is a shape or fill, not a stored picture.
    """
    if width is None:
        width = payload.get("width") or ICON_BOX_15
    if height is None:
        height = payload.get("height") or ICON_BOX_15
    dest_width, dest_height = icon_dimensions_15(width, height)
    fill = payload["fill"]
    if fill == "solid":
        index = halftone_quantise(colorref_rgb(payload["colors"][0]))
        return build_icon_record(handle, content, dest_width, dest_height,
                                 [index] * (dest_width * dest_height))
    if fill == "gradient":
        first = colorref_rgb(payload["colors"][0])
        second = colorref_rgb(payload["colors"][1])
        vertical = payload.get("direction", 1) == 1
        extent = dest_height if vertical else dest_width
        bands = [
            halftone_quantise(
                tuple(
                    first[channel]
                    + (second[channel] - first[channel]) * step // extent
                    for channel in range(3)
                )
            )
            for step in range(extent)
        ]
        if vertical:
            indices = [bands[y] for y in range(dest_height)
                       for _x in range(dest_width)]
        else:
            indices = [bands[x] for _y in range(dest_height)
                       for x in range(dest_width)]
        return build_icon_record(handle, content, dest_width, dest_height,
                                 indices)
    if fill == "motif" and images_by_id is not None:
        record = images_by_id.get(payload.get("motif_image"))
        if record is not None:
            mwidth, mheight, mode, rows = editor_image_pixels(record)
            indices = []
            for y in range(dest_height):
                source_y = sample(y, height, dest_height)
                row = rows[source_y % mheight]
                for x in range(dest_width):
                    source_x = sample(x, width, dest_width)
                    rgb = source_rgb(mode, row, source_x % mwidth, palette)
                    indices.append(0 if rgb is None else halftone_quantise(rgb))
            return build_icon_record(handle, content, dest_width, dest_height,
                                     indices)

    return build_icon_record(handle, content, dest_width, dest_height,
                             [0] * (dest_width * dest_height))

def artwork_icon_record_15(path: Path, handle: int) -> bytes:
    """Build an icon record from one of this project's own PNG drawings."""
    return build_icon_record(
        handle, OTHER_ICON_CONTENT_15, 32, 32, artwork_icon_indices(path)
    )

def frame_preview_record(handle: int, background_colorref: int) -> bytes:
    """Render a frame's thumbnail from that frame's own background."""
    index = halftone_quantise(colorref_rgb(background_colorref))
    indices = []
    for _y in range(PREVIEW_HEIGHT):
        indices.extend([index] * PREVIEW_CONTENT_COLUMNS)
        indices.extend([0] * (PREVIEW_WIDTH - PREVIEW_CONTENT_COLUMNS))
    return build_icon_record(handle, PREVIEW_CONTENT_15, PREVIEW_WIDTH,
                             PREVIEW_HEIGHT, indices)
