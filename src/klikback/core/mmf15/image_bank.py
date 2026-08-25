# GENERATED — do not edit by hand. This file is produced by KlikBack's
# sync tooling; changes belong in the source it is generated from.
#
# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""The image bank a 1.5 project stores its pictures in."""

from __future__ import annotations
import struct
from klikback.core.common.container import spans

BANK_HEADER = 4 + 4 + 2 + 2 + 256 * 4

IMAGE_RECORD_HEADER = 24

RLE_LENGTH_OFFSET = 6

class ImageBankProblem(Exception):
    """Raised when a bank cannot be read as a bank."""

def editor_bank(
    data: bytes, which: int, parts: dict | None = None
) -> tuple[bytes, dict[int, bytes], list[int]]:
    """The bank in the form a project holds it."""
    if parts is None:
        parts = {span.name: span for span in spans(data)}
    span = parts[f"AGMI-{which}"]
    blob = data[span.start:span.end]
    (count,) = struct.unpack_from("<I", blob, BANK_HEADER)
    cursor = BANK_HEADER + 4
    records: dict[int, bytes] = {}
    order: list[int] = []
    for index in range(count):
        (handle,) = struct.unpack_from("<I", blob, cursor)
        cursor += 4
        (rle,) = struct.unpack_from("<I", blob, cursor + RLE_LENGTH_OFFSET)
        record = blob[cursor:cursor + IMAGE_RECORD_HEADER + rle]
        if len(record) != IMAGE_RECORD_HEADER + rle:
            raise ImageBankProblem(f"image {index} runs past bank {which}")
        if handle in records:
            raise ImageBankProblem(f"handle {handle} appears twice in bank {which}")
        records[handle] = record
        order.append(handle)
        cursor += len(record)
    if cursor != len(blob):
        raise ImageBankProblem(
            f"bank {which} has {len(blob) - cursor} bytes past its last image"
        )
    return blob[:BANK_HEADER], records, order

def build_bank(header: bytes, images: list[tuple[int, bytes]]) -> bytes:
    """Assemble a bank from recovered images."""
    return (
        header
        + struct.pack("<I", len(images))
        + b"".join(
            struct.pack("<I", handle) + record for handle, record in images
        )
    )
