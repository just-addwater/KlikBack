# GENERATED — do not edit by hand. This file is produced by KlikBack's
# sync tooling; changes belong in the source it is generated from.
#
# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""Pull a compiled game's event programs out of its executable."""

from __future__ import annotations
import struct
from klikback.core.common.compare import Chunk
from klikback.core.common.compression_probe import decompress_clickteam_stream
from klikback.core.common.container import FONT_BANK, MUSIC_BANK, SAMPLE_BANK, agmi_end, simple_bank_end

def decompress_chunk(chunk: Chunk) -> bytes:
    """Unpack one stored chunk."""
    if chunk.flags == 0:
        return chunk.payload
    if chunk.flags != 1 or len(chunk.payload) < 4:
        raise ValueError(
            f"unsupported flags 0x{chunk.flags:X} on chunk 0x{chunk.chunk_id:04X}"
        )
    expected_size = struct.unpack_from("<I", chunk.payload, 0)[0]

    output = decompress_clickteam_stream(chunk.payload[4:])
    if len(output) != expected_size:
        raise ValueError(
            f"chunk 0x{chunk.chunk_id:04X}: decoded {len(output)} bytes, "
            f"expected {expected_size}"
        )
    return output

def event_is_well_formed(event: bytes) -> bool:
    """Whether an event reads as a whole event rather than as damage."""
    pos = 0x0E
    for header_size, count in ((0x0E, event[2]), (0x0C, event[3])):
        for _ in range(count):
            if pos + header_size > len(event):
                return False
            size = struct.unpack_from("<H", event, pos)[0]
            if size < header_size or pos + size > len(event):
                return False
            pos += size
    return pos == len(event)

def extract_events(event_chunk: bytes) -> list[bytes]:
    """Every event program the game carries."""
    candidates: list[tuple[int, bytes]] = []
    for pos in range(len(event_chunk) - 1):
        signed_size = struct.unpack_from("<h", event_chunk, pos)[0]
        if signed_size >= 0:
            continue
        size = -signed_size
        end = pos + size
        if size >= 0x0E and end <= len(event_chunk):
            condition_count = event_chunk[pos + 2]
            action_count = event_chunk[pos + 3]

            if (
                condition_count
                and action_count
                and event_is_well_formed(event_chunk[pos:end])
            ):
                candidates.append((pos, event_chunk[pos:end]))

    events: list[bytes] = []
    previous_end = -1
    for pos, candidate in candidates:
        if pos < previous_end:
            continue
        events.append(candidate)
        previous_end = pos + len(candidate)
    return events

def extract_event_programs(event_chunk: bytes) -> list[list[bytes]]:
    """The programs belonging to one frame."""
    first_revision = event_chunk.find(b"ERev")
    resources = event_chunk.rfind(b"ERes", 0, first_revision)
    if first_revision < 0 or resources < 0:
        return [extract_events(event_chunk)]
    if resources + 8 != first_revision:
        raise ValueError("runtime event resources do not lead into ERev data")

    declared_payload_size = struct.unpack_from("<I", event_chunk, resources + 4)[0]
    programs: list[list[bytes]] = []
    measured_payload_size = 0
    pos = first_revision
    while event_chunk.startswith(b"ERev", pos):
        if pos + 8 > len(event_chunk):
            raise ValueError("truncated ERev header")
        size = struct.unpack_from("<I", event_chunk, pos + 4)[0]
        start = pos + 8
        end = start + size
        if end > len(event_chunk):
            raise ValueError("ERev payload extends beyond the event chunk")
        program = event_chunk[start:end]
        events = extract_events(program)
        if sum(map(len, events)) != len(program):
            raise ValueError("ERev payload contains bytes outside event records")
        programs.append(events)
        measured_payload_size += size
        pos = end

    if measured_payload_size != declared_payload_size:
        raise ValueError(
            f"ERes declares {declared_payload_size} event bytes, "
            f"but ERev records contain {measured_payload_size}"
        )
    if event_chunk[pos:] != b"<<ER":
        raise ValueError("runtime event program list has an unexpected trailer")
    return programs

BANK_CHAIN_START = 14

BANK_CHAIN = (b"ATNF", b"APMS", b"ASUM", b"AGMI")

def empty_bank_offset(cca: bytes, tag: bytes) -> int:
    """Where an empty bank sits, which is where recovered content is written.
    """
    if tag not in BANK_CHAIN:
        raise ValueError(f"{tag!r} is not an asset bank in the chain")
    pos = BANK_CHAIN_START
    for entry in BANK_CHAIN:
        if cca[pos : pos + 4] != entry:
            raise ValueError(
                f"asset bank chain: expected {entry!r} at offset {pos}, found "
                f"{cca[pos : pos + 4]!r} -- an earlier bank is already "
                f"populated, so the banks are being replaced out of order"
            )
        if entry == tag:
            if cca[pos + 4 : pos + 8] != b"\x00\x00\x00\x00":
                raise ValueError(
                    f"the {tag.decode()} bank at offset {pos} is not empty"
                )
            return pos
        pos += 8
    raise ValueError(f"{tag!r} was not reached in the asset bank chain")

def icon_and_image_bank_offsets(cca: bytes) -> tuple[int, int]:
    pos = BANK_CHAIN_START
    for tag in (FONT_BANK, SAMPLE_BANK, MUSIC_BANK):
        pos = simple_bank_end(cca, pos, tag)
    icon_bank = pos
    return icon_bank, agmi_end(cca, icon_bank)
