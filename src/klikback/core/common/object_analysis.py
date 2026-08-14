# GENERATED — do not edit by hand. This file is produced by KlikBack's
# sync tooling; changes belong in the source it is generated from.
#
# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""Split a compiled game's object data into the pieces each object owns."""

from __future__ import annotations
import struct
from klikback.core.common.compare import Chunk
from klikback.core.common.compression_probe import decompress_clickteam_stream_with_consumed

def parse_image_streams(data: bytes) -> list[tuple[int, bytes, int]]:
    """Split the game's image bank into the individual compressed streams inside it.

    The bank is a count followed by one compressed stream per image, and — this is
    the whole difficulty — no stream states its own stored length. Where one ends
    and the next begins has to be worked out, and it is genuinely ambiguous: the
    compressor is inconsistent about leaving a single zero byte after a stream
    that is already complete. So every image offers two possible lengths, and
    picking the wrong one does not fail here. It fails later, at whichever image
    the wrong offset lands in the middle of.

    That makes this a backtracking search rather than a walk. Take the first
    candidate length, carry on, and when something further along will not decode,
    step back to the most recent image that still has an alternative and try that
    instead. It only accepts a split where **every** image decoded to the size its
    header declared *and* the last stream ends exactly at the end of the bank.
    Either test on its own would accept a wrong answer.

    The search keeps its own explicit stack instead of recursing, and that is not
    a matter of taste: one interpreter frame per image overflows the stack on
    image-heavy games, and games with more than a thousand images exist.
    """
    count = struct.unpack_from("<I", data, 0)[0]

    def decode(header_pos: int):
        if header_pos + 8 > len(data):
            return None
        image_id, expected_size = struct.unpack_from("<II", data, header_pos)
        stream_pos = header_pos + 8
        try:
            output, minimum_size = decompress_clickteam_stream_with_consumed(
                data[stream_pos:]
            )
        except ValueError:
            return None
        if len(output) != expected_size:
            return None
        stored_sizes = [minimum_size]
        minimum_end = stream_pos + minimum_size
        if minimum_end < len(data) and data[minimum_end] == 0:
            stored_sizes.append(minimum_size + 1)
        return image_id, output, stream_pos, stored_sizes

    stack: list[list] = []
    header_pos = 4
    extending = True
    while True:
        if extending:
            if len(stack) == count:
                if header_pos == len(data):
                    return [
                        (image_id, output, stored_sizes[choice])
                        for image_id, output, _pos, stored_sizes, choice in stack
                    ]

                extending = False
            else:
                decoded = decode(header_pos)
                if decoded is None:
                    extending = False
                else:
                    image_id, output, stream_pos, stored_sizes = decoded
                    stack.append([image_id, output, stream_pos, stored_sizes, 0])
                    header_pos = stream_pos + stored_sizes[0]
        if not extending:
            while stack:
                entry = stack[-1]
                entry[4] += 1
                if entry[4] < len(entry[3]):
                    header_pos = entry[2] + entry[3][entry[4]]
                    extending = True
                    break
                stack.pop()
            if not extending:
                raise ValueError(
                    f"could not parse all {count} runtime image streams"
                )

def split_object_chunks(data: bytes) -> list[list[Chunk]]:
    """Separate the per-object records from one run of object data."""
    count = struct.unpack_from("<I", data, 0)[0]
    pos = 4
    objects: list[list[Chunk]] = []
    for _ in range(count):
        chunks: list[Chunk] = []
        while pos + 8 <= len(data):
            chunk_id, flags, size = struct.unpack_from("<HHI", data, pos)
            end = pos + 8 + size
            if end > len(data):
                raise ValueError("nested object chunk extends beyond its container")
            chunks.append(Chunk(chunk_id, flags, data[pos + 8 : end]))
            pos = end
            if chunk_id == 0x7F7F:
                break
        objects.append(chunks)
    if pos != len(data):
        raise ValueError(f"object chunk parser left {len(data)-pos} trailing bytes")
    return objects
