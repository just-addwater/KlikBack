# GENERATED — do not edit by hand. This file is produced by KlikBack's
# sync tooling; changes belong in the source it is generated from.
#
# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""Unpack the compressed chunks a compiled MMF game stores its data in.

A game's frames, events and banks are stored compressed, in Clickteam's own
variant of a Huffman-coded stream. Everything the pipeline reads passes
through here first, so this is the floor the rest of the recovery stands on.

**A damaged stream is salvaged as far as it goes, not abandoned.** Real games
are decades old and have been copied, patched and archived by hand; a chunk
that stops decoding partway through still has everything before the fault in
it. Recovering that much and reporting the shortfall is worth more than
discarding a frame because its last few bytes are gone — which is why a
frame that would not decompress is reported as a named loss rather than
silently missing.
"""

from __future__ import annotations
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path
from klikback.core.common.compare import Chunk, find_chunk, read_chunks

class BitReader:
    """Read a stream a bit at a time, which is how these codes are stored."""
    def __init__(self, data: bytes, bit_pos: int = 0) -> None:
        """Start reading at a bit position, not a byte one."""
        self.data = data
        self.bit_pos = bit_pos

    def read(self, count: int) -> int:
        """Take the next few bits, whether or not they sit inside one byte."""
        value = 0
        for index in range(count):
            if self.bit_pos >= len(self.data) * 8:
                raise ValueError("truncated compressed bitstream")
            value |= (
                (self.data[self.bit_pos // 8] >> (self.bit_pos % 8)) & 1
            ) << index
            self.bit_pos += 1
        return value

def canonical_codes(lengths: list[int]) -> dict[int, tuple[int, int]]:
    """Build the code table the stream's header describes."""
    counts = [0] * (max(lengths, default=0) + 1)
    for length in lengths:
        if length:
            counts[length] += 1
    next_code = [0] * len(counts)
    code = 0
    for bits in range(1, len(counts)):
        code = (code + counts[bits - 1]) << 1
        next_code[bits] = code
    result: dict[int, tuple[int, int]] = {}
    for symbol, length in enumerate(lengths):
        if length:
            result[symbol] = (next_code[length], length)
            next_code[length] += 1
    return result

@lru_cache(maxsize=256)
def decode_table(lengths: tuple[int, ...]) -> tuple[dict[tuple[int, int], int], int]:
    """The lookup that turns codes back into symbols."""
    return (
        {
            (length, code): symbol
            for symbol, (code, length) in canonical_codes(list(lengths)).items()
        },
        max(lengths, default=0),
    )

def decode_symbol_with(
    reader: BitReader, by_code: dict[tuple[int, int], int], longest: int
) -> int:
    """Read one symbol using a given table."""
    code = 0
    for length in range(1, longest + 1):
        code = (code << 1) | reader.read(1)
        symbol = by_code.get((length, code))
        if symbol is not None:
            return symbol
    raise ValueError("invalid Huffman code")

_CLICKTEAM_ORDER = (18, 17, 16, *range(16))

def read_clickteam_dynamic_lengths(
    reader: BitReader,
) -> tuple[int, int, list[int]]:
    """Read the per-stream code lengths that precede the data.

    A compressed block starts by describing its own alphabets: how many literal
    codes it uses, how many distance codes, and then the length of every code —
    themselves written compactly, with their own symbols for runs of zeros and
    for repeating the previous length. This reads that description and returns
    the two counts and the flat list of lengths.

    The one place this departs from ordinary deflate is the order the first small
    table's lengths are stored in, which Clickteam's compressor writes its own
    way. Everything after that is standard.

    Two things here are contracts rather than implementation details. The
    reader's bit position is left exactly at the end of the header — on success
    and on every kind of failure alike — because callers start it partway
    through a stream and read the position back afterwards to find where the
    payload begins. And a list of lengths that runs past the count the header
    declared raises rather than being trimmed to fit: an overrun means the data
    is damaged, and a trimmed list builds a tree that decodes to plausible bytes
    that are wrong, which is worse than stopping.

    There are two routes through the same work: a table-driven one for the
    ordinary case, and a bit-at-a-time walk for a table that is malformed. The
    slower walk is kept because for damaged data its behaviour *is* the
    specification — what matters is not that it is fast but that it fails in
    exactly the place and the way it always has.
    """
    data = reader.data
    dlen = len(data)
    total_bits = dlen * 8
    masks = _MASKS

    bit_pos = reader.bit_pos
    byte_pos = bit_pos >> 3
    buffer = 0
    bit_count = 0
    if bit_pos & 7 and byte_pos < dlen:
        buffer = data[byte_pos] >> (bit_pos & 7)
        bit_count = 8 - (bit_pos & 7)
        byte_pos += 1

    if bit_count < 14:
        while byte_pos < dlen and bit_count < 14:
            buffer |= data[byte_pos] << bit_count
            byte_pos += 1
            bit_count += 8
        if bit_count < 14:
            reader.bit_pos = total_bits
            raise ValueError("truncated compressed bitstream")
    literal_count = (buffer & 31) + 257
    distance_count = ((buffer >> 5) & 31) + 1
    code_length_count = ((buffer >> 10) & 15) + 4
    buffer >>= 14
    bit_count -= 14

    code_length_lengths = [0] * 19
    for index in range(code_length_count):
        if bit_count < 3:
            while byte_pos < dlen and bit_count < 3:
                buffer |= data[byte_pos] << bit_count
                byte_pos += 1
                bit_count += 8
            if bit_count < 3:
                reader.bit_pos = total_bits
                raise ValueError("truncated compressed bitstream")
        code_length_lengths[_CLICKTEAM_ORDER[index]] = buffer & 7
        buffer >>= 3
        bit_count -= 3

    table_key = tuple(code_length_lengths)
    by_code, longest = decode_table(table_key)
    fast = _fast_table(table_key)
    lengths: list[int] = []
    wanted = literal_count + distance_count

    if fast is None:

        reader.bit_pos = byte_pos * 8 - bit_count
        while len(lengths) < wanted:
            symbol = decode_symbol_with(reader, by_code, longest)
            if symbol <= 15:
                lengths.append(symbol)
            elif symbol == 16:
                if not lengths:
                    raise ValueError(
                        "repeat code 16 has no previous code length"
                    )
                lengths.extend([lengths[-1]] * (reader.read(2) + 3))
            elif symbol == 17:
                lengths.extend([0] * (reader.read(3) + 3))
            elif symbol == 18:
                lengths.extend([0] * (reader.read(7) + 11))
        if len(lengths) != wanted:
            raise ValueError(
                f"dynamic code lengths overrun their declared count "
                f"({len(lengths)} for {wanted})"
            )
        return literal_count, distance_count, lengths

    root, mask, root_bits, long_codes, table_longest = fast
    while len(lengths) < wanted:
        if bit_count < 7:
            while byte_pos < dlen and bit_count < 7:
                buffer |= data[byte_pos] << bit_count
                byte_pos += 1
                bit_count += 8
        if bit_count < table_longest:
            reader.bit_pos = byte_pos * 8 - bit_count
            symbol = decode_symbol_with(reader, by_code, longest)
            bit_pos = reader.bit_pos
            byte_pos = bit_pos >> 3
            buffer = 0
            bit_count = 0
            if bit_pos & 7:
                buffer = data[byte_pos] >> (bit_pos & 7)
                bit_count = 8 - (bit_pos & 7)
                byte_pos += 1
        else:
            entry = root[buffer & mask]
            if entry:
                code_length = entry & 15
                buffer >>= code_length
                bit_count -= code_length
                symbol = entry >> 4
            else:
                symbol = -1
                for code_length in range(root_bits + 1, table_longest + 1):
                    found = long_codes.get(
                        (code_length, buffer & masks[code_length])
                    )
                    if found is not None:
                        buffer >>= code_length
                        bit_count -= code_length
                        symbol = found
                        break
                if symbol < 0:
                    buffer >>= table_longest
                    bit_count -= table_longest
                    reader.bit_pos = byte_pos * 8 - bit_count
                    raise ValueError("invalid Huffman code")
        if symbol <= 15:
            lengths.append(symbol)
        elif symbol == 16:
            if not lengths:
                reader.bit_pos = byte_pos * 8 - bit_count
                raise ValueError("repeat code 16 has no previous code length")
            if bit_count < 2:
                while byte_pos < dlen and bit_count < 2:
                    buffer |= data[byte_pos] << bit_count
                    byte_pos += 1
                    bit_count += 8
                if bit_count < 2:
                    reader.bit_pos = total_bits
                    raise ValueError("truncated compressed bitstream")
            lengths.extend([lengths[-1]] * ((buffer & 3) + 3))
            buffer >>= 2
            bit_count -= 2
        elif symbol == 17:
            if bit_count < 3:
                while byte_pos < dlen and bit_count < 3:
                    buffer |= data[byte_pos] << bit_count
                    byte_pos += 1
                    bit_count += 8
                if bit_count < 3:
                    reader.bit_pos = total_bits
                    raise ValueError("truncated compressed bitstream")
            lengths.extend([0] * ((buffer & 7) + 3))
            buffer >>= 3
            bit_count -= 3
        elif symbol == 18:
            if bit_count < 7:
                while byte_pos < dlen and bit_count < 7:
                    buffer |= data[byte_pos] << bit_count
                    byte_pos += 1
                    bit_count += 8
                if bit_count < 7:
                    reader.bit_pos = total_bits
                    raise ValueError("truncated compressed bitstream")
            lengths.extend([0] * ((buffer & 127) + 11))
            buffer >>= 7
            bit_count -= 7

    reader.bit_pos = byte_pos * 8 - bit_count
    if len(lengths) != wanted:

        raise ValueError(
            f"dynamic code lengths overrun their declared count "
            f"({len(lengths)} for {wanted})"
        )
    return literal_count, distance_count, lengths

LENGTH_BASES = [
    3, 4, 5, 6, 7, 8, 9, 10,
    11, 13, 15, 17,
    19, 23, 27, 31,
    35, 43, 51, 59,
    67, 83, 99, 115,
    131, 163, 195, 227,
    258,
]

LENGTH_EXTRA_BITS = [
    0, 0, 0, 0, 0, 0, 0, 0,
    1, 1, 1, 1,
    2, 2, 2, 2,
    3, 3, 3, 3,
    4, 4, 4, 4,
    5, 5, 5, 5,
    0,
]

DISTANCE_BASES = [
    1, 2, 3, 4,
    5, 7,
    9, 13,
    17, 25,
    33, 49,
    65, 97,
    129, 193,
    257, 385,
    513, 769,
    1025, 1537,
    2049, 3073,
    4097, 6145,
    8193, 12289,
    16385, 24577,
]

DISTANCE_EXTRA_BITS = [
    0, 0, 0, 0,
    1, 1,
    2, 2,
    3, 3,
    4, 4,
    5, 5,
    6, 6,
    7, 7,
    8, 8,
    9, 9,
    10, 10,
    11, 11,
    12, 12,
    13, 13,
]

_MASKS = tuple((1 << count) - 1 for count in range(17))

_STATIC_LITERAL_LENGTHS = (8,) * 144 + (9,) * 112 + (7,) * 24 + (8,) * 8

_STATIC_DISTANCE_LENGTHS = (5,) * 32

@lru_cache(maxsize=256)
def _fast_table(
    lengths: tuple[int, ...],
) -> tuple[list[int], int, int, dict[tuple[int, int], int], int] | None:
    longest = max(lengths, default=0)
    if sum(1 << (longest - length) for length in lengths if length) > 1 << longest:
        return None
    root_bits = longest if longest < 10 else 10
    size = 1 << root_bits
    root = [0] * size
    long_codes: dict[tuple[int, int], int] = {}
    for symbol, (code, length) in canonical_codes(list(lengths)).items():
        reversed_code = 0
        remaining = code
        for _ in range(length):
            reversed_code = (reversed_code << 1) | (remaining & 1)
            remaining >>= 1
        if length <= root_bits:
            entry = (symbol << 4) | length
            step = 1 << length
            for cell in range(reversed_code, size, step):
                root[cell] = entry
        else:
            long_codes[(length, reversed_code)] = symbol
    return root, size - 1, root_bits, long_codes, longest

def _decode_block_symbols_compat(
    reader: BitReader,
    output: bytearray,
    literal_by_code: dict[tuple[int, int], int],
    literal_longest: int,
    distance_by_code: dict[tuple[int, int], int],
    distance_longest: int,
) -> None:
    while True:
        symbol = decode_symbol_with(reader, literal_by_code, literal_longest)
        if symbol < 256:
            output.append(symbol)
            continue
        if symbol == 256:
            return
        if symbol < 257 or symbol > 285:
            raise ValueError(f"invalid length symbol {symbol}")
        length_index = symbol - 257
        length = LENGTH_BASES[length_index] + reader.read(
            LENGTH_EXTRA_BITS[length_index]
        )
        distance_symbol = decode_symbol_with(
            reader, distance_by_code, distance_longest
        )
        if distance_symbol >= len(DISTANCE_BASES):
            raise ValueError(f"invalid distance symbol {distance_symbol}")
        distance = DISTANCE_BASES[distance_symbol] + reader.read(
            DISTANCE_EXTRA_BITS[distance_symbol]
        )
        if distance <= 0 or distance > len(output):
            raise ValueError(
                f"invalid back-reference distance {distance} at "
                f"output offset {len(output)}"
            )
        if distance >= length:
            start = len(output) - distance
            output.extend(output[start : start + length])
        else:
            for _ in range(length):
                output.append(output[-distance])

def decompress_clickteam_stream_with_consumed(
    data: bytes, partial: bool = False
) -> tuple[bytes, int]:
    """Unpack a stream and say how many input bytes it used.

    Needed where chunks are packed end to end and the next one starts wherever
    the last stopped.
    """

    reader = BitReader(data)
    output = bytearray()
    try:
        return _decode_blocks(data, reader, output, partial)
    except (ValueError, IndexError):

        if partial:
            return bytes(output), (reader.bit_pos + 7) // 8
        raise

def _decode_blocks(
    data: bytes, reader: BitReader, output: bytearray, partial: bool
) -> tuple[bytes, int]:
    dlen = len(data)
    total_bits = dlen * 8
    masks = _MASKS
    length_bases = LENGTH_BASES
    length_extras = LENGTH_EXTRA_BITS
    distance_bases = DISTANCE_BASES
    distance_extras = DISTANCE_EXTRA_BITS
    distance_symbol_limit = len(DISTANCE_BASES)

    bit_pos = reader.bit_pos
    byte_pos = bit_pos >> 3
    buffer = 0
    bit_count = 0
    if bit_pos & 7:
        buffer = data[byte_pos] >> (bit_pos & 7)
        bit_count = 8 - (bit_pos & 7)
        byte_pos += 1

    while True:
        logical = byte_pos * 8 - bit_count
        if partial and logical + 4 > total_bits:
            reader.bit_pos = logical
            return bytes(output), (logical + 7) // 8
        if bit_count < 4:
            while byte_pos < dlen and bit_count < 4:
                buffer |= data[byte_pos] << bit_count
                byte_pos += 1
                bit_count += 8
            if bit_count < 4:
                reader.bit_pos = total_bits
                raise ValueError("truncated compressed bitstream")
        block_type = buffer & 7
        final = (buffer >> 3) & 1
        buffer >>= 4
        bit_count -= 4
        if partial and block_type not in (5, 6, 7):
            logical = byte_pos * 8 - bit_count
            reader.bit_pos = logical
            return bytes(output), (logical + 7) // 8
        if block_type == 7:
            drop = bit_count & 7
            buffer >>= drop
            bit_count -= drop
            if bit_count < 16:
                while byte_pos < dlen and bit_count < 16:
                    buffer |= data[byte_pos] << bit_count
                    byte_pos += 1
                    bit_count += 8
                if bit_count < 16:
                    reader.bit_pos = total_bits
                    raise ValueError("truncated compressed bitstream")
            length = buffer & 0xFFFF
            buffer >>= 16
            bit_count -= 16

            start_byte = byte_pos - (bit_count >> 3)
            end_byte = start_byte + length
            if end_byte > dlen:

                output.extend(data[start_byte:dlen])
                reader.bit_pos = total_bits
                raise ValueError("truncated compressed bitstream")
            output.extend(data[start_byte:end_byte])
            byte_pos = end_byte
            buffer = 0
            bit_count = 0
        elif block_type == 5 or block_type == 6:
            if block_type == 5:
                literal_tuple = _STATIC_LITERAL_LENGTHS
                distance_tuple = _STATIC_DISTANCE_LENGTHS
            else:
                reader.bit_pos = byte_pos * 8 - bit_count
                literal_count, distance_count, lengths = (
                    read_clickteam_dynamic_lengths(reader)
                )
                bit_pos = reader.bit_pos
                byte_pos = bit_pos >> 3
                buffer = 0
                bit_count = 0
                if bit_pos & 7:
                    buffer = data[byte_pos] >> (bit_pos & 7)
                    bit_count = 8 - (bit_pos & 7)
                    byte_pos += 1
                literal_tuple = tuple(lengths[:literal_count])
                distance_tuple = tuple(
                    lengths[literal_count : literal_count + distance_count]
                )

            literal_by_code, literal_longest = decode_table(literal_tuple)
            distance_by_code, distance_longest = decode_table(distance_tuple)
            literal_fast = _fast_table(literal_tuple)
            distance_fast = _fast_table(distance_tuple)
            if literal_fast is None or distance_fast is None:
                reader.bit_pos = byte_pos * 8 - bit_count
                _decode_block_symbols_compat(
                    reader,
                    output,
                    literal_by_code,
                    literal_longest,
                    distance_by_code,
                    distance_longest,
                )
                bit_pos = reader.bit_pos
                byte_pos = bit_pos >> 3
                buffer = 0
                bit_count = 0
                if bit_pos & 7:
                    buffer = data[byte_pos] >> (bit_pos & 7)
                    bit_count = 8 - (bit_pos & 7)
                    byte_pos += 1
            else:
                lit_root, lit_mask, lit_bits, lit_long, lit_longest = literal_fast
                dist_root, dist_mask, dist_bits, dist_long, dist_longest = (
                    distance_fast
                )
                append = output.append
                extend = output.extend
                while True:
                    if bit_count < 15:
                        while byte_pos < dlen and bit_count < 15:
                            buffer |= data[byte_pos] << bit_count
                            byte_pos += 1
                            bit_count += 8
                    if bit_count < lit_longest:
                        reader.bit_pos = byte_pos * 8 - bit_count
                        symbol = decode_symbol_with(
                            reader, literal_by_code, literal_longest
                        )
                        bit_pos = reader.bit_pos
                        byte_pos = bit_pos >> 3
                        buffer = 0
                        bit_count = 0
                        if bit_pos & 7:
                            buffer = data[byte_pos] >> (bit_pos & 7)
                            bit_count = 8 - (bit_pos & 7)
                            byte_pos += 1
                    else:
                        entry = lit_root[buffer & lit_mask]
                        if entry:
                            code_length = entry & 15
                            buffer >>= code_length
                            bit_count -= code_length
                            symbol = entry >> 4
                        else:
                            symbol = -1
                            for code_length in range(
                                lit_bits + 1, lit_longest + 1
                            ):
                                found = lit_long.get(
                                    (code_length, buffer & masks[code_length])
                                )
                                if found is not None:
                                    buffer >>= code_length
                                    bit_count -= code_length
                                    symbol = found
                                    break
                            if symbol < 0:
                                buffer >>= lit_longest
                                bit_count -= lit_longest
                                reader.bit_pos = byte_pos * 8 - bit_count
                                raise ValueError("invalid Huffman code")
                    if symbol < 256:
                        append(symbol)
                        continue
                    if symbol == 256:
                        break
                    if symbol < 257 or symbol > 285:
                        reader.bit_pos = byte_pos * 8 - bit_count
                        raise ValueError(f"invalid length symbol {symbol}")
                    length_index = symbol - 257
                    extra = length_extras[length_index]
                    if extra:
                        if bit_count < extra:
                            while byte_pos < dlen and bit_count < extra:
                                buffer |= data[byte_pos] << bit_count
                                byte_pos += 1
                                bit_count += 8
                            if bit_count < extra:
                                reader.bit_pos = total_bits
                                raise ValueError("truncated compressed bitstream")
                        length = length_bases[length_index] + (
                            buffer & masks[extra]
                        )
                        buffer >>= extra
                        bit_count -= extra
                    else:
                        length = length_bases[length_index]
                    if bit_count < 15:
                        while byte_pos < dlen and bit_count < 15:
                            buffer |= data[byte_pos] << bit_count
                            byte_pos += 1
                            bit_count += 8
                    if bit_count < dist_longest:
                        reader.bit_pos = byte_pos * 8 - bit_count
                        distance_symbol = decode_symbol_with(
                            reader, distance_by_code, distance_longest
                        )
                        bit_pos = reader.bit_pos
                        byte_pos = bit_pos >> 3
                        buffer = 0
                        bit_count = 0
                        if bit_pos & 7:
                            buffer = data[byte_pos] >> (bit_pos & 7)
                            bit_count = 8 - (bit_pos & 7)
                            byte_pos += 1
                    else:
                        entry = dist_root[buffer & dist_mask]
                        if entry:
                            code_length = entry & 15
                            buffer >>= code_length
                            bit_count -= code_length
                            distance_symbol = entry >> 4
                        else:
                            distance_symbol = -1
                            for code_length in range(
                                dist_bits + 1, dist_longest + 1
                            ):
                                found = dist_long.get(
                                    (code_length, buffer & masks[code_length])
                                )
                                if found is not None:
                                    buffer >>= code_length
                                    bit_count -= code_length
                                    distance_symbol = found
                                    break
                            if distance_symbol < 0:
                                buffer >>= dist_longest
                                bit_count -= dist_longest
                                reader.bit_pos = byte_pos * 8 - bit_count
                                raise ValueError("invalid Huffman code")
                    if distance_symbol >= distance_symbol_limit:
                        reader.bit_pos = byte_pos * 8 - bit_count
                        raise ValueError(
                            f"invalid distance symbol {distance_symbol}"
                        )
                    extra = distance_extras[distance_symbol]
                    if extra:
                        if bit_count < extra:
                            while byte_pos < dlen and bit_count < extra:
                                buffer |= data[byte_pos] << bit_count
                                byte_pos += 1
                                bit_count += 8
                            if bit_count < extra:
                                reader.bit_pos = total_bits
                                raise ValueError("truncated compressed bitstream")
                        distance = distance_bases[distance_symbol] + (
                            buffer & masks[extra]
                        )
                        buffer >>= extra
                        bit_count -= extra
                    else:
                        distance = distance_bases[distance_symbol]
                    out_len = len(output)
                    if distance <= 0 or distance > out_len:
                        reader.bit_pos = byte_pos * 8 - bit_count
                        raise ValueError(
                            f"invalid back-reference distance {distance} at "
                            f"output offset {out_len}"
                        )

                    if distance >= length:
                        start = out_len - distance
                        extend(output[start : start + length])
                    else:
                        segment = bytes(output[out_len - distance :])
                        repeat, remainder = divmod(length, distance)
                        extend(segment * repeat + segment[:remainder])
        else:
            reader.bit_pos = byte_pos * 8 - bit_count
            raise ValueError(f"unsupported Clickteam block type {block_type}")

        if final:
            logical = byte_pos * 8 - bit_count
            reader.bit_pos = logical
            return bytes(output), (logical + 7) // 8

def decompress_clickteam_stream(data: bytes) -> bytes:
    """Unpack one compressed stream."""

    output, _stored_size = decompress_clickteam_stream_with_consumed(data)
    return output

def _decode_tolerating_out_of_window(
    data: bytes, emit: Callable[[bytes, int], bytes]
) -> tuple[bytes, int, list[dict]]:
    reader = BitReader(data)
    output = bytearray()
    faults: list[dict] = []
    while True:
        block_type = reader.read(3)
        final = reader.read(1)
        if block_type == 7:
            reader.bit_pos = (reader.bit_pos + 7) & ~7
            for _ in range(reader.read(16)):
                output.append(reader.read(8))
        elif block_type in (5, 6):
            if block_type == 5:
                literal_lengths = [8] * 144 + [9] * 112 + [7] * 24 + [8] * 8
                distance_lengths = [5] * 32
            else:
                literal_count, distance_count, lengths = (
                    read_clickteam_dynamic_lengths(reader)
                )
                literal_lengths = lengths[:literal_count]
                distance_lengths = lengths[
                    literal_count : literal_count + distance_count
                ]
            literal_by_code, literal_longest = decode_table(tuple(literal_lengths))
            distance_by_code, distance_longest = decode_table(tuple(distance_lengths))
            while True:
                symbol = decode_symbol_with(reader, literal_by_code, literal_longest)
                if symbol < 256:
                    output.append(symbol)
                    continue
                if symbol == 256:
                    break
                if symbol < 257 or symbol > 285:
                    raise ValueError(f"invalid length symbol {symbol}")
                length_index = symbol - 257
                length = LENGTH_BASES[length_index] + reader.read(
                    LENGTH_EXTRA_BITS[length_index]
                )
                distance_symbol = decode_symbol_with(
                    reader, distance_by_code, distance_longest
                )
                if distance_symbol >= len(DISTANCE_BASES):
                    raise ValueError(f"invalid distance symbol {distance_symbol}")
                distance = DISTANCE_BASES[distance_symbol] + reader.read(
                    DISTANCE_EXTRA_BITS[distance_symbol]
                )
                if distance <= 0:
                    raise ValueError("zero back-reference distance")
                if distance > len(output):
                    substitute = emit(bytes(output), length)
                    faults.append(
                        {
                            "offset": len(output),
                            "distance": distance,
                            "stored_length": length,
                            "emitted_length": len(substitute),
                        }
                    )
                    output.extend(substitute)
                    continue
                if distance >= length:
                    start = len(output) - distance
                    output.extend(output[start : start + length])
                else:
                    for _ in range(length):
                        output.append(output[-distance])
        else:
            raise ValueError(f"unsupported Clickteam block type {block_type}")
        if final:
            return bytes(output), (reader.bit_pos + 7) // 8, faults

def decompress_clickteam_record_salvaged(
    data: bytes,
    declared: int,
    substitute: Callable[[bytes, int], bytes] | None = None,
) -> tuple[bytes, int, list[dict]]:
    """Unpack as much of a damaged record as is actually recoverable."""
    if substitute is None:
        substitute = lambda _prefix, length: b"\x00" * length

    try:
        output, stored_size = decompress_clickteam_stream_with_consumed(data)
    except (ValueError, IndexError):
        pass
    else:
        return output, stored_size, []

    output, stored_size, faults = _decode_tolerating_out_of_window(
        data, lambda prefix, length: substitute(prefix, length)
    )
    if not faults:
        return output, stored_size, faults
    if len(faults) > 1:
        raise ValueError(
            f"{len(faults)} out-of-window back-references; the salvage "
            f"handles a single damaged reference and cannot apportion a "
            f"surplus between several"
        )
    surplus = len(output) - declared
    fault = faults[0]
    if surplus < 0 or surplus >= fault["stored_length"]:
        raise ValueError(
            f"out-of-window back-reference at output offset {fault['offset']} "
            f"distance {fault['distance']}: decoded {len(output)} bytes against "
            f"a declared {declared}, which the stored match length "
            f"{fault['stored_length']} cannot account for"
        )
    true_length = fault["stored_length"] - surplus
    output, stored_size, faults = _decode_tolerating_out_of_window(
        data, lambda prefix, _length: substitute(prefix, true_length)
    )
    if len(output) != declared:
        raise ValueError(
            f"salvaged record is {len(output)} bytes against a declared {declared}"
        )
    faults[0]["stored_length"] = fault["stored_length"]
    return output, stored_size, faults

def overlay_offset(data: bytes) -> int:
    if data.startswith(b"PAME"):
        return 0
    return data.find(b"PAME", 0x40000)

def application_bytes(data: bytes) -> bytes:
    if overlay_offset(data) >= 0:
        return data
    try:
        from klikback.core.common.project_pack import packed_application
    except ImportError:
        return data
    return packed_application(data) or data

def load_exe_frame(path: Path) -> tuple[list[Chunk], list[Chunk]]:
    """Pull one frame's compressed chunk out of a compiled game."""
    data = application_bytes(path.read_bytes())
    overlay = overlay_offset(data)
    if overlay < 0:
        raise ValueError(f"{path}: no MMF PAME overlay")
    outer = read_chunks(data, overlay + 0x10, len(data))
    frame = find_chunk(outer, 0x3333)
    if frame.flags != 0:
        raise ValueError("outer frame container is unexpectedly compressed")
    inner = read_chunks(frame.payload, 0, len(frame.payload))
    return outer, inner
