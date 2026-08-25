# GENERATED — do not edit by hand. This file is produced by KlikBack's
# sync tooling; changes belong in the source it is generated from.
#
# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""Rebuild a game's music bank."""

from __future__ import annotations
import struct
from pathlib import Path
from klikback.core.common.compare import find_chunk
from klikback.core.common.compression_probe import decompress_clickteam_record_salvaged, decompress_clickteam_stream_with_consumed, load_exe_frame
from klikback.core.common.exe_to_cca import decompress_chunk, empty_bank_offset, extract_events
from klikback.core.common.reconstruct_event_test import compiled_event_to_editor_event

MUSIC_BANK_TAG = b"ASUM"

def midi_running_status(record: bytes, upto: int) -> int:
    """Expand the shorthand a MIDI stream uses for repeated commands."""

    def variable_length(pos: int) -> tuple[int, int]:
        value = 0
        for _ in range(4):
            byte = record[pos]
            pos += 1
            value = (value << 7) | (byte & 0x7F)
            if not byte & 0x80:
                return value, pos
        raise ValueError("over-long variable-length quantity")

    try:
        pos = record.index(b"MTrk", 0, upto) + 8
    except ValueError:
        return 0
    status = 0
    try:
        while pos < upto:
            _delta, pos = variable_length(pos)
            byte = record[pos]
            if byte == 0xFF:
                pos += 2
                length, pos = variable_length(pos)
                pos += length
                continue
            if byte in (0xF0, 0xF7):
                pos += 1
                length, pos = variable_length(pos)
                pos += length
                continue
            if byte & 0x80:
                status = byte
                pos += 1
            elif not status:
                return 0
            pos += 1 if status & 0xF0 in (0xC0, 0xD0) else 2
    except (ValueError, IndexError):
        return 0
    return status

def midi_substitute(prefix: bytes, length: int) -> bytes:
    """Stand in for a track that cannot be recovered, so the bank stays whole.
    """
    status = midi_running_status(prefix, len(prefix))
    if not status or length < 1:
        return b"\x00" * length
    return b"\x00" * (length - 1) + bytes([status])

def runtime_music_bank(
    exe_path: Path,
    salvage: bool = False,
    salvaged: list | None = None,
) -> tuple[bytes, list[bytes]]:
    """The music a compiled game carries."""
    outer, frame = load_exe_frame(exe_path)
    runtime_bank = decompress_chunk(find_chunk(outer, 0x6669))
    if len(runtime_bank) < 4:
        raise ValueError("truncated runtime music bank")
    count = struct.unpack_from("<I", runtime_bank, 0)[0]
    pos = 4
    records: list[tuple[int, bytes]] = []
    for music_index in range(count):
        if pos + 8 > len(runtime_bank):
            raise ValueError(f"truncated music header at index {music_index}")
        handle, expected_size = struct.unpack_from("<II", runtime_bank, pos)
        if salvage:
            music_record, stored_size, faults = (
                decompress_clickteam_record_salvaged(
                    runtime_bank[pos + 8 :], expected_size, midi_substitute
                )
            )
            for fault in faults:
                fault.update({"index": music_index, "handle": handle})
                if salvaged is not None:
                    salvaged.append(fault)
        else:
            music_record, stored_size = decompress_clickteam_stream_with_consumed(
                runtime_bank[pos + 8 :]
            )
        if len(music_record) != expected_size:
            raise ValueError(
                f"music {music_index} decoded {len(music_record)} bytes, "
                f"expected {expected_size}"
            )
        records.append((handle, music_record))
        pos += 8 + stored_size
    if pos != len(runtime_bank):
        raise ValueError(f"runtime music bank has {len(runtime_bank)-pos} trailing bytes")
    editor_bank = MUSIC_BANK_TAG + struct.pack("<I", count) + b"".join(
        struct.pack("<I", handle) + music_record
        for handle, music_record in records
    )

    compiled = extract_events(
        decompress_chunk(find_chunk(frame, 0x333D))
    )
    events = [compiled_event_to_editor_event(event) for event in compiled]
    return editor_bank, events

def replace_empty_music_bank(cca: bytes, music_bank: bytes) -> bytes:
    """Put the recovered music into the project's empty bank."""
    bank_pos = empty_bank_offset(cca, MUSIC_BANK_TAG)
    return cca[:bank_pos] + music_bank + cca[bank_pos + 8 :]
