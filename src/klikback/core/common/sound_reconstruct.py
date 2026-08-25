# GENERATED — do not edit by hand. This file is produced by KlikBack's
# sync tooling; changes belong in the source it is generated from.
#
# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""Rebuild a game's sound bank from the samples it carries.

Sounds are stored as the runtime wants them, which is not always the form the
editor expects; where a sample is in a compressed form, it is decoded to plain
audio so the rebuilt project holds something an editor can play and export.
"""

from __future__ import annotations
import struct
from pathlib import Path
from klikback.core.common.compare import find_chunk
from klikback.core.common.compression_probe import decompress_clickteam_stream_with_consumed, load_exe_frame
from klikback.core.common.exe_to_cca import decompress_chunk, empty_bank_offset, extract_events
from klikback.core.common.reconstruct_event_test import compiled_event_to_editor_event

SAMPLE_BANK_TAG = b"APMS"

PCM_FORMAT = 1

MS_ADPCM_FORMAT = 2

MS_ADPCM_ADAPTATION = (
    230,
    230,
    230,
    230,
    307,
    409,
    512,
    614,
    768,
    614,
    512,
    409,
    307,
    230,
    230,
    230,
)

def _clamp_i16(value: int) -> int:
    return max(-32768, min(32767, value))

def _decode_ms_adpcm_nibble(
    nibble: int,
    state: list[int],
    coefficients: list[tuple[int, int]],
) -> int:
    predictor, delta, sample1, sample2 = state
    if predictor >= len(coefficients):
        raise ValueError(f"invalid Microsoft ADPCM predictor {predictor}")
    coef1, coef2 = coefficients[predictor]
    signed = nibble - 16 if nibble & 8 else nibble
    sample = _clamp_i16(
        (sample1 * coef1 + sample2 * coef2) // 256 + signed * delta
    )
    state[3] = sample1
    state[2] = sample
    state[1] = max(16, MS_ADPCM_ADAPTATION[nibble] * delta // 256)
    return sample

def ms_adpcm_to_pcm_sample(sample_record: bytes) -> bytes:
    """Decode one compressed audio sample to plain audio."""
    if len(sample_record) < 22:
        raise ValueError("truncated MMF sample record")
    name_size = struct.unpack_from("<I", sample_record, 18)[0]
    format_pos = 22 + name_size
    if format_pos + 18 > len(sample_record):
        raise ValueError("truncated MMF sample format")
    (
        format_tag,
        channels,
        sample_rate,
        _average_bytes,
        block_align,
        bits_per_sample,
        extra_size,
    ) = struct.unpack_from("<HHIIHHH", sample_record, format_pos)
    if format_tag != MS_ADPCM_FORMAT:
        raise ValueError(f"sample format is {format_tag}, not Microsoft ADPCM")
    if channels not in (1, 2) or bits_per_sample != 4:
        raise ValueError(
            f"unsupported Microsoft ADPCM shape: channels={channels}, "
            f"bits={bits_per_sample}"
        )
    if extra_size < 4 or format_pos + 18 + extra_size + 4 > len(sample_record):
        raise ValueError("truncated Microsoft ADPCM format extension")
    samples_per_block, coefficient_count = struct.unpack_from(
        "<HH", sample_record, format_pos + 18
    )
    if extra_size != 4 + coefficient_count * 4:
        raise ValueError(
            f"Microsoft ADPCM extra size {extra_size} does not match "
            f"{coefficient_count} coefficients"
        )
    coefficients = [
        struct.unpack_from("<hh", sample_record, format_pos + 22 + index * 4)
        for index in range(coefficient_count)
    ]
    data_size_pos = format_pos + 18 + extra_size
    data_size = struct.unpack_from("<I", sample_record, data_size_pos)[0]
    data_pos = data_size_pos + 4
    data_end = data_pos + data_size
    if data_end > len(sample_record):
        raise ValueError("truncated Microsoft ADPCM sample payload")
    if block_align < channels * 7 or samples_per_block < 2:
        raise ValueError("invalid Microsoft ADPCM block geometry")

    pcm = bytearray()
    data = sample_record[data_pos:data_end]
    for block_start in range(0, len(data), block_align):
        block = data[block_start : block_start + block_align]
        header_size = channels * 7
        if len(block) < header_size:
            raise ValueError("truncated Microsoft ADPCM block header")
        predictors = list(block[:channels])
        pos = channels
        deltas = list(struct.unpack_from(f"<{channels}h", block, pos))
        pos += channels * 2
        sample1 = list(struct.unpack_from(f"<{channels}h", block, pos))
        pos += channels * 2
        sample2 = list(struct.unpack_from(f"<{channels}h", block, pos))
        pos += channels * 2
        states = [
            [predictors[index], deltas[index], sample1[index], sample2[index]]
            for index in range(channels)
        ]
        for frame in (sample2, sample1):
            pcm.extend(struct.pack(f"<{channels}h", *frame))
        emitted = 2
        for value in block[pos:]:
            if emitted >= samples_per_block:
                break
            if channels == 2:
                frame = (
                    _decode_ms_adpcm_nibble(value >> 4, states[0], coefficients),
                    _decode_ms_adpcm_nibble(value & 0x0F, states[1], coefficients),
                )
                pcm.extend(struct.pack("<2h", *frame))
                emitted += 1
            else:
                for nibble in (value >> 4, value & 0x0F):
                    if emitted >= samples_per_block:
                        break
                    pcm.extend(
                        struct.pack(
                            "<h",
                            _decode_ms_adpcm_nibble(
                                nibble, states[0], coefficients
                            ),
                        )
                    )
                    emitted += 1

    converted = bytearray(sample_record[:format_pos])
    converted.extend(
        struct.pack(
            "<HHIIHHH",
            PCM_FORMAT,
            channels,
            sample_rate,
            sample_rate * channels * 2,
            channels * 2,
            16,
            0,
        )
    )
    converted.extend(struct.pack("<I", len(pcm)))
    converted.extend(pcm)

    converted.extend(b"\0\0")
    struct.pack_into("<I", converted, 6, len(converted) - 22)
    return bytes(converted)

def editor_sample_record(sample_record: bytes) -> bytes:
    """One sample in the form a project stores."""
    if len(sample_record) < 22:
        raise ValueError("truncated MMF sample record")
    name_size = struct.unpack_from("<I", sample_record, 18)[0]
    format_pos = 22 + name_size
    if format_pos + 2 > len(sample_record):
        raise ValueError("truncated MMF sample format")
    format_tag = struct.unpack_from("<H", sample_record, format_pos)[0]
    if format_tag == PCM_FORMAT:
        return sample_record
    if format_tag == MS_ADPCM_FORMAT:
        return ms_adpcm_to_pcm_sample(sample_record)
    raise ValueError(f"unsupported MMF sample WAVE format {format_tag}")

def runtime_sample_bank(exe_path: Path) -> tuple[bytes, list[bytes]]:
    """The samples a compiled game carries."""
    outer, frame = load_exe_frame(exe_path)
    runtime_bank = decompress_chunk(find_chunk(outer, 0x6668))
    if len(runtime_bank) < 4:
        raise ValueError("truncated runtime sample bank")
    count = struct.unpack_from("<I", runtime_bank, 0)[0]
    pos = 4
    records: list[tuple[int, bytes]] = []
    for sample_index in range(count):
        if pos + 8 > len(runtime_bank):
            raise ValueError(f"truncated sample header at index {sample_index}")
        handle, expected_size = struct.unpack_from("<II", runtime_bank, pos)
        sample_record, stored_size = decompress_clickteam_stream_with_consumed(
            runtime_bank[pos + 8 :]
        )
        if len(sample_record) != expected_size:

            self_described = (
                expected_size >= 22
                and len(sample_record) > expected_size
                and struct.unpack_from("<I", sample_record, 6)[0] + 22
                == expected_size
            )
            if not self_described:
                raise ValueError(
                    f"sample {sample_index} decoded {len(sample_record)} "
                    f"bytes, expected {expected_size}"
                )
            sample_record = sample_record[:expected_size]
        records.append((handle, editor_sample_record(sample_record)))
        pos += 8 + stored_size
    if pos != len(runtime_bank):
        raise ValueError(f"runtime sample bank has {len(runtime_bank)-pos} trailing bytes")
    editor_bank = SAMPLE_BANK_TAG + struct.pack("<I", count) + b"".join(
        struct.pack("<I", handle) + sample_record
        for handle, sample_record in records
    )

    compiled = extract_events(
        decompress_chunk(find_chunk(frame, 0x333D))
    )
    events = [compiled_event_to_editor_event(event) for event in compiled]
    return editor_bank, events

def replace_empty_sample_bank(cca: bytes, sample_bank: bytes) -> bytes:
    """Put the recovered samples into the project's empty bank."""
    bank_pos = empty_bank_offset(cca, SAMPLE_BANK_TAG)
    return cca[:bank_pos] + sample_bank + cca[bank_pos + 8 :]
