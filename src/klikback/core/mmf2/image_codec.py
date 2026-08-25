# GENERATED — do not edit by hand. This file is produced by KlikBack's
# sync tooling; changes belong in the source it is generated from.
#
# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""Read the pictures out of a Multimedia Fusion 2 project or game.

Every picture a project holds — an object's animation frames, a backdrop, the
little thumbnail the editor shows beside an object in its list — is stored the
same way: a short fixed header saying how big the picture is and how its
pixels are packed, then the pixels.

The header is the same everywhere.  The pixels are not.  A pixel may be one,
two or three bytes; a two-byte pixel divides those bytes between the three
colours in either of two ways; a picture may store which pixels are
see-through in a plane of its own, or it may nominate one colour as the
see-through one; and it may be stored plainly or run-length compressed.  The
combination is announced in the header, and this module turns whatever it
finds into one plain answer: how wide, how tall, and what colour each pixel
is, with see-through pixels reported as nothing at all.

Two of those choices are easy to get wrong in a way that produces no error at
all.  A row is sometimes longer than the picture is wide, so the last pixel
of each row is padding that must not be read; and which flag means
"compressed" is not the same bit for every pixel size.  Miss either and the
picture still decodes — into something sheared or scrambled — so both are
settled here from the stored lengths rather than assumed.

That last part is the point of reading a picture rather than comparing the
stored bytes.  The same picture written twice can be two entirely different
sequences of bytes — compressed one time and plain the next, see-through by a
nominated colour one time and by a separate plane the next — and none of that
difference is a difference in the picture.  Anything that wants to know
whether two pictures are the same has to ask about the pixels.

Four pixel formats appear and all four are read: three bytes per pixel stored
blue first; two two-byte formats that divide their sixteen bits between the
colours differently, one giving five bits to each and leaving a bit spare and
the other giving the spare bit to green; and a one-byte format whose pixel is
an INDEX into a colour table.

That last one needs the table, and the table is not in the picture — it
belongs to the bank the picture came from, and the two banks a project holds
carry different tables.  So a picture in that format has to be read together
with its own bank's table; read with the other one it still decodes, into a
complete set of plausible and wrong colours.  Supply the table and it reads;
withhold it and the picture reports its size and its stored bytes but refuses
to give colours, which is the honest answer rather than a guess.

Some packings are not read.  Where a picture is stored in a form this module
has not been shown to understand, it says so and stops, rather than returning
pixels it is guessing at.  A caller that can carry the stored bytes through
untouched should do that; a caller that needs the pixels has to treat the
refusal as an answer.
"""

from __future__ import annotations
import struct

HEADER = 32

FLAG_RLE = 0x02

FLAG_ALPHA = 0x10

MODE_PALETTE8 = 3

MODE_BGR888 = 4

MODE_RGB555 = 6

MODE_RGB565 = 7

PIXEL_BYTES = {MODE_PALETTE8: 1, MODE_BGR888: 3,
               MODE_RGB555: 2, MODE_RGB565: 2}

RLE_FLAG = {1: 0x01, 2: FLAG_RLE, 3: 0x04}

MODES = (MODE_PALETTE8, MODE_BGR888, MODE_RGB555, MODE_RGB565)

PALETTE_ENTRIES = 256

PALETTE_BYTES = PALETTE_ENTRIES * 4

def palette_rgb(palette, index):
    """One entry of a bank's colour table, as a plain colour.

    Entries are stored red first, which is the opposite order to the Windows
    structure of the same shape and size — reading it the familiar way swaps red
    and blue on every pixel of every indexed picture.
    """
    if palette is None or len(palette) < PALETTE_BYTES:
        raise Unsupported("a graphicMode 3 record needs its bank's %d-byte "
                          "palette; %s was supplied"
                          % (PALETTE_BYTES,
                             "none" if palette is None
                             else "%d bytes" % len(palette)))
    at = (index & 0xFF) * 4
    return (palette[at] << 16) | (palette[at + 1] << 8) | palette[at + 2]

ICON_BOX = 32

class Unsupported(Exception):
    """Raised when a picture is stored in a form this module will not guess at.
    """

def unpack(raw, palette=None):
    """Split a stored picture into its header fields and its pixel body.

    Reports how big the picture is, how its pixels are packed, where its hot spot
    and action point sit, and which colour — if any — stands for see-through.
    """
    if len(raw) < HEADER:
        raise Unsupported("an image record is %d bytes, shorter than its "
                          "32-byte header" % len(raw))
    checksum, unnamed, data_size = struct.unpack_from("<3I", raw, 0)
    width, height = struct.unpack_from("<2H", raw, 12)
    hot_x, hot_y, act_x, act_y = struct.unpack_from("<4h", raw, 20)
    (transparent,) = struct.unpack_from("<I", raw, 28)
    return dict(checksum=checksum, unnamed=unnamed, dataSize=data_size,
                width=width, height=height,
                graphicMode=raw[16], flags=raw[17],
                hotSpotX=hot_x, hotSpotY=hot_y,
                actionX=act_x, actionY=act_y,
                transparent=transparent, palette=palette,
                body=raw[HEADER:])

def transparent_word(transparent, mode=MODE_RGB565):
    """The nominated see-through colour, in the packing this picture uses.

    The two 16-bit packings divide the two bytes up differently, so the same
    colour is a different pair of bytes in each.  Reading a picture with the wrong
    one does not merely shift its colours — it changes which pixels are treated as
    see-through, which is a far louder kind of wrong.
    """
    red = transparent & 0xFF
    green = (transparent >> 8) & 0xFF
    blue = (transparent >> 16) & 0xFF
    if mode == MODE_RGB555:
        return ((red >> 3) << 10) | ((green >> 3) << 5) | (blue >> 3)
    if mode == MODE_RGB565:
        return ((red >> 3) << 11) | ((green >> 2) << 5) | (blue >> 3)
    if mode in (MODE_BGR888, MODE_PALETTE8):

        return (red << 16) | (green << 8) | blue
    raise Unsupported("graphicMode %d has no known word packing" % mode)

def to_rgb565(value, mode):
    """Re-express a decoded pixel as a 16-bit colour.

    The editor keeps the small thumbnail beside an object in 16 bits whatever the
    artwork is, so a 24-bit picture has to be converted before it can be compared
    with one — or written as one.  The 24-bit conversion is the editor's own,
    established by reproducing thumbnails it had already stored.  The conversion
    from the other 16-bit format is not: it widens a colour channel by shifting,
    and if the editor rounds instead, the result will differ in the lowest bit.
    """
    if mode == MODE_RGB565:
        return value
    if mode in (MODE_BGR888, MODE_PALETTE8):

        red = (value >> 16) & 0xFF
        green = (value >> 8) & 0xFF
        blue = value & 0xFF
        return ((red >> 3) << 11) | ((green >> 2) << 5) | (blue >> 3)
    if mode == MODE_RGB555:
        red = (value >> 10) & 0x1F
        green = (value >> 5) & 0x1F
        blue = value & 0x1F

        return (red << 11) | ((green << 1) << 5) | blue
    raise Unsupported("graphicMode %d has no known conversion to RGB565"
                      % mode)

def decode_runs(data, count, unit=2):
    """Undo the run-length compression, which counts in pixels rather than bytes.
    """
    out = bytearray()
    pos = got = 0
    while got < count:
        if pos >= len(data):
            raise Unsupported("the run stream ran out after %d of %d pixels"
                              % (got, count))
        control = data[pos]
        pos += 1
        if control & 0x80:
            n = control & 0x7F
            end = pos + unit * n
            if end > len(data):
                raise Unsupported("a literal run of %d pixels overruns the "
                                  "record" % n)
            out += data[pos:end]
            pos = end
        else:
            if pos + unit > len(data):
                raise Unsupported("a repeat run has no pixel after it")
            out += data[pos:pos + unit] * control
            pos += unit
            n = control
        if not n:
            raise Unsupported("a zero-length run at pixel %d would not "
                              "terminate" % got)
        got += n
    if got != count:
        raise Unsupported("the run stream decoded %d pixels, not %d"
                          % (got, count))
    return bytes(out), pos

def encode_runs(plane, unit=2):
    """Compress a run of pixels back.

    This is a valid encoding, not the editor's own.  Where a run of identical
    pixels can be written more than one way, this makes its own choice, so the
    bytes will not generally match what the editor would have written for the same
    picture.  It exists so a picture can be written back out in the compressed
    form, not so bytes can be compared.
    """
    out = bytearray()
    words = [plane[i:i + unit] for i in range(0, len(plane), unit)]
    i = 0
    while i < len(words):
        run = 1
        while (i + run < len(words) and run < 0x7F
               and words[i + run] == words[i]):
            run += 1
        if run > 1:
            out.append(run)
            out += words[i]
            i += run
            continue
        run = 1
        while (i + run < len(words) and run < 0x7F
               and (i + run + 1 >= len(words)
                    or words[i + run + 1] != words[i + run])):
            run += 1
        out.append(0x80 | run)
        for word in words[i:i + run]:
            out += word
        i += run
    out.append(0)
    return bytes(out)

def row_pixels(width, mode):
    """How many pixels one stored row holds, which is not always the width.

    Some pixel sizes pad each row out to an even number of pixels and others do
    not.  The extra pixel is not part of the picture and reading it shifts every
    row after the first.
    """
    if mode in (MODE_PALETTE8, MODE_BGR888):
        return width + (width & 1)
    return width

def colour_row_bytes(width, mode=MODE_RGB565):
    """How many bytes one row of colour takes."""
    return row_pixels(width, mode) * PIXEL_BYTES[mode]

def alpha_row_bytes(width):
    """How many bytes one row of the see-through plane takes.

    This is not the same as the colour row length.  The see-through plane pads
    every row out to a four-byte boundary whatever the pixel format is, where a
    colour row pads to a whole number of pixels for some formats and not at all
    for others.
    """
    return (width + 3) & ~3

def planes(rec):
    """The colour bytes and, where there is one, the see-through plane.

    Undoes the compression if the picture is compressed, and checks the result is
    the size the header said it would be.  Each plane has its own row length and
    they are not the same, so index the see-through plane with `alpha_row_bytes`
    rather than assuming it matches the colour rows.
    """
    mode = rec["graphicMode"]
    if mode not in MODES:
        raise Unsupported("graphicMode %d is not decoded by this module"
                          % mode)
    width, height = rec["width"], rec["height"]
    unit = PIXEL_BYTES[mode]
    if rec["flags"] & RLE_FLAG[unit]:
        colour, used = decode_runs(rec["body"],
                                   row_pixels(width, mode) * height, unit)
        left = rec["body"][used:]
        if left not in (b"", b"\x00"):
            raise Unsupported("a compressed record left %d bytes over, not "
                              "the single terminator" % len(left))
        return colour, None
    clen = colour_row_bytes(width, mode) * height
    colour = rec["body"][:clen]
    if len(colour) != clen:
        raise Unsupported("an uncompressed record holds %d bytes, short of "
                          "the %d its colour plane needs"
                          % (len(rec["body"]), clen))
    if not rec["flags"] & FLAG_ALPHA:

        return colour, None
    alen = alpha_row_bytes(width) * height
    alpha = rec["body"][clen:clen + alen]
    if len(alpha) != alen:
        raise Unsupported("an alpha record holds %d bytes after its colour "
                          "plane, short of %d"
                          % (len(rec["body"]) - clen, alen))
    return colour, alpha

def pixels(rec):
    """Every pixel, row by row, as a colour and whether it can be seen."""
    colour, alpha = planes(rec)
    mode = rec["graphicMode"]
    width, height = rec["width"], rec["height"]
    unit = PIXEL_BYTES[mode]
    per = row_pixels(width, mode)
    key = transparent_word(rec["transparent"], mode)
    stride = alpha_row_bytes(width)
    grid = []
    for y in range(height):
        row = []
        for x in range(width):
            at = (y * per + x) * unit
            if mode == MODE_PALETTE8:

                value = palette_rgb(rec["palette"], colour[at])
            elif unit == 3:

                value = ((colour[at + 2] << 16) | (colour[at + 1] << 8)
                         | colour[at])
            else:
                value = colour[at] | (colour[at + 1] << 8)
            if alpha is None:
                row.append((value, value != key))
            else:
                row.append((value, alpha[y * stride + x] != 0))
        grid.append(row)
    return grid

def picture(rec):
    """A picture as width, height, and one colour per pixel, with see-through pixels
    reported as nothing.

    This is the form to compare two pictures in.  How a picture was stored — the
    compression, which colour was nominated see-through, whether there was a
    separate plane — is dropped, because none of it is part of the picture.
    """
    grid = pixels(rec)
    flat = tuple(word if visible else None
                 for row in grid for word, visible in row)
    return rec["width"], rec["height"], flat

def trim(pic):
    """The same picture with its see-through border cut away.

    Returns nothing at all when every pixel is see-through: there is no picture
    left to speak of, and a caller should treat that as an absence rather than as
    an empty picture.
    """
    width, height, flat = pic
    grid = [[flat[y * width + x] for x in range(width)] for y in range(height)]
    box = visible_box([[(v or 0, v is not None) for v in row] for row in grid])
    if box is None:
        return None
    x0, y0, x1, y1 = box
    return (x1 - x0, y1 - y0,
            tuple(grid[y][x] for y in range(y0, y1) for x in range(x0, x1)))

def visible_box(grid):
    """The rectangle holding every pixel that can be seen."""
    xs, ys = [], []
    for y, row in enumerate(grid):
        for x, (_, visible) in enumerate(row):
            if visible:
                xs.append(x)
                ys.append(y)
    if not xs:
        return None
    return min(xs), min(ys), max(xs) + 1, max(ys) + 1

def fit_box(width, height, box=ICON_BOX):
    """The size a picture is shown at inside a square box, keeping its shape.

    A picture that already fits keeps its own size; a larger one is reduced by
    whichever side is longer.
    """
    if width <= box and height <= box:
        return width, height
    scale = float(box) / max(width, height)
    return max(1, int(width * scale)), max(1, int(height * scale))

RENDER_UNDECODED = "undecoded"

RENDER_SCALED = "scaled"

RENDER_EMPTY = "empty"

def icon_render(rec):
    """The small picture the editor keeps beside an object in its lists.

    That picture is not the object's own artwork stored a second time.  It is
    made from it: fitted inside a small square box, then cut down to the pixels
    that can actually be seen.

    Only part of that is reproduced here, and the rest is declined by name rather
    than approximated.  When the artwork already fits the box, no reduction is
    involved and the result is exact.  When it is larger, a reduction is needed
    and the way the editor reduces a picture is not known, so the caller is told
    `RENDER_SCALED` and should carry the original through instead.  A picture
    whose packing cannot be read is declined as `RENDER_UNDECODED`, and one that
    is see-through all the way across is declined as `RENDER_EMPTY` — there is
    nothing to show.

    The three refusals mean three different things and a caller that treats them
    alike will get two of them wrong.  A picture that cannot be read still has a
    thumbnail; a picture that is entirely see-through does not.

    This lives here, rather than in whichever part of KlikBack happens to need
    it, so that everything asking what the editor's thumbnail looks like asks the
    same question and gets the same answer.
    """
    if rec["graphicMode"] not in MODES:
        return None, RENDER_UNDECODED
    width, height = rec["width"], rec["height"]
    if fit_box(width, height) != (width, height):
        return None, RENDER_SCALED
    try:
        pic = picture(rec)
    except Unsupported:
        return None, RENDER_UNDECODED
    cut = trim(pic)
    if cut is None:
        return None, RENDER_EMPTY
    return cut, None

def control():

    """Check this module against pictures whose correct reading is known."""
    raw = (struct.pack("<3I", 0x1234, 1, 6)
           + struct.pack("<2H", 2, 1)
           + struct.pack("<BBH", MODE_RGB565, FLAG_ALPHA, 0)
           + struct.pack("<4h", 1, 2, 3, 4)
           + struct.pack("<I", 0x00385C00)
           + bytes([0x00, 0x00, 0xFF, 0xFF, 0x01, 0x00, 0x00, 0x00]))
    rec = unpack(raw)
    if (rec["width"], rec["height"]) != (2, 1):
        raise AssertionError("the header's size is not at +0x0C")
    if rec["graphicMode"] != MODE_RGB565 or rec["flags"] != FLAG_ALPHA:
        raise AssertionError("graphicMode and flags are not at +0x10/+0x11")
    if (rec["hotSpotX"], rec["actionY"]) != (1, 4):
        raise AssertionError("the hot spot / action point are not at +0x14")
    print("unpack: 32-byte header, size at +0x0C, mode and flags at +0x10")

    if transparent_word(0x00385C00) != 0x02E7:
        raise AssertionError(
            "COLORREF 0x00385C00 must read RGB565 0x02E7 -- red 0x00, green "
            "0x5C, blue 0x38 -- and reads 0x%04X"
            % transparent_word(0x00385C00))
    if transparent_word(0) != 0:
        raise AssertionError("black is not 0")
    if transparent_word(0x00FFFFFF) != 0xFFFF:
        raise AssertionError("white is not 0xFFFF")
    print("transparent_word: COLORREF red-first, 0x00385C00 -> 0x02E7")

    if transparent_word(0x00385C00, MODE_RGB555) != 0x0167:
        raise AssertionError(
            "COLORREF 0x00385C00 must read RGB555 0x0167 and reads 0x%04X"
            % transparent_word(0x00385C00, MODE_RGB555))
    if transparent_word(0x00FFFFFF, MODE_RGB555) != 0x7FFF:
        raise AssertionError(
            "white in RGB555 is 0x7FFF -- five bits per channel with bit 15 "
            "left clear -- and reads 0x%04X"
            % transparent_word(0x00FFFFFF, MODE_RGB555))
    if transparent_word(0x00FFFFFF, MODE_RGB555) & 0x8000:
        raise AssertionError("mode 6 must never set bit 15")
    try:
        transparent_word(0, 5)
    except Unsupported:
        pass
    else:
        raise AssertionError("a mode with no known packing must be refused "
                             "rather than silently read as 565")
    print("transparent_word: mode 6 is 5-5-5 with bit 15 clear, "
          "0x00385C00 -> 0x0167 against mode 7's 0x02E7")

    if colour_row_bytes(11) != 22 or alpha_row_bytes(11) != 12:
        raise AssertionError("11 wide is 22 colour bytes and 12 alpha bytes")
    if colour_row_bytes(11) * 20 + alpha_row_bytes(11) * 20 != 680:
        raise AssertionError("an 11x20 alpha record is 680 bytes")
    print("row rules: colour width*2 unpadded, alpha DWORD-aligned")

    wide = (struct.pack("<3I", 0, 0, 0) + struct.pack("<2H", 3, 2)
            + struct.pack("<BBH", MODE_RGB565, FLAG_ALPHA, 0)
            + struct.pack("<4h", 0, 0, 0, 0) + struct.pack("<I", 0)
            + bytes([1, 0, 2, 0, 3, 0, 4, 0, 5, 0, 6, 0])
            + bytes([0xFF, 0, 0xFF, 0]) + bytes([0, 0xFF, 0, 0]))
    grid = pixels(unpack(wide))
    if [[v for v, _ in row] for row in grid] != [[1, 2, 3], [4, 5, 6]]:
        raise AssertionError("the colour plane is not row-packed at width*2")
    if [[s for _, s in row] for row in grid] != [[True, False, True],
                                                 [False, True, False]]:
        raise AssertionError(
            "the alpha plane must be indexed at its own DWORD stride; read "
            "at the colour stride a 3-wide record gives %r"
            % [[s for _, s in row] for row in grid])
    print("pixels: alpha at its own stride, 3-wide proves the padding byte")

    plain = bytes([0xAA, 0xBB]) * 5 + bytes([1, 2, 3, 4])
    runs = encode_runs(plain)
    back, used = decode_runs(runs, len(plain) // 2)
    if back != plain or used != len(runs) - 1:
        raise AssertionError("encode/decode does not round-trip")
    if runs[0] != 5 or runs[1:3] != bytes([0xAA, 0xBB]):
        raise AssertionError("a 5-word repeat is not `05` then the word")
    if runs[-1] != 0:
        raise AssertionError("the stream does not end with the 0 terminator")
    literal, used = decode_runs(bytes([0x82, 1, 0, 2, 0]), 2)
    if literal != bytes([1, 0, 2, 0]) or used != 5:
        raise AssertionError("0x82 is not a two-word literal run")
    print("runs: bit 7 literal, otherwise repeat, 0 terminates")

    body = encode_runs(bytes([0xE7, 0x02, 0x22, 0x5B]))
    comp = (struct.pack("<3I", 0, 0, len(body)) + struct.pack("<2H", 2, 1)
            + struct.pack("<BBH", MODE_RGB565, FLAG_RLE, 0)
            + struct.pack("<4h", 0, 0, 0, 0)
            + struct.pack("<I", 0x00385C00) + body)
    grid = pixels(unpack(comp))
    if grid != [[(0x02E7, False), (0x5B22, True)]]:
        raise AssertionError("a compressed record must key its transparency "
                             "off the header colour, and reads %r" % grid)
    print("compressed: no alpha plane, invisible == the transparent colour")

    keyed = picture(unpack(comp))
    if keyed != (2, 1, (None, 0x5B22)):
        raise AssertionError("picture() must drop the invisible pixel's "
                             "colour, and gives %r" % (keyed,))
    other_key = (struct.pack("<3I", 0, 0, 0) + struct.pack("<2H", 2, 1)
                 + struct.pack("<BBH", MODE_RGB565, FLAG_RLE, 0)
                 + struct.pack("<4h", 0, 0, 0, 0)
                 + struct.pack("<I", 0x00FFFFFF)
                 + encode_runs(bytes([0xFF, 0xFF, 0x22, 0x5B])))
    if picture(unpack(other_key)) != keyed:
        raise AssertionError(
            "two records of one picture with different transparent colours "
            "must compare EQUAL; they read %r and %r"
            % (picture(unpack(other_key)), keyed))
    plane = bytes([0, 0, 0, 0, 0, 0]) + bytes([9, 0, 0, 0, 8, 0])
    boxed = (struct.pack("<3I", 0, 0, 0) + struct.pack("<2H", 3, 2)
             + struct.pack("<BBH", MODE_RGB565, FLAG_RLE, 0)
             + struct.pack("<4h", 0, 0, 0, 0) + struct.pack("<I", 0)
             + encode_runs(plane))
    if trim(picture(unpack(boxed))) != (3, 1, (9, None, 8)):
        raise AssertionError("trim does not cut to the visible box: %r"
                             % (trim(picture(unpack(boxed))),))
    if trim((1, 1, (None,))) is not None:
        raise AssertionError("an invisible picture has no trim")
    print("picture / trim: encoding dropped, transparent key dropped, "
          "cropped to the visible box")

    def one_word(mode, word, key):
        return unpack(struct.pack("<3I", 0, 0, 0) + struct.pack("<2H", 1, 1)
                      + struct.pack("<BBH", mode, FLAG_RLE, 0)
                      + struct.pack("<4h", 0, 0, 0, 0)
                      + struct.pack("<I", key)
                      + encode_runs(struct.pack("<H", word)))

    same_colour_555 = picture(one_word(MODE_RGB555, 0x0167, 0))
    same_colour_565 = picture(one_word(MODE_RGB565, 0x02E7, 0))
    if same_colour_555 == same_colour_565:
        raise AssertionError(
            "a mode 6 and a mode 7 record holding the same colour must not "
            "compare EQUAL -- the words are 0x0167 and 0x02E7 -- or the two "
            "packings have been merged; both read %r" % (same_colour_555,))

    as_six = picture(one_word(MODE_RGB555, 0x0167, 0x00385C00))
    as_seven = picture(one_word(MODE_RGB565, 0x0167, 0x00385C00))
    if as_six != (1, 1, (None,)):
        raise AssertionError(
            "mode 6 must key its transparency off the 555 word, so 0x0167 "
            "under transparent 0x00385C00 is INVISIBLE; it reads %r"
            % (as_six,))
    if as_seven != (1, 1, (0x0167,)):
        raise AssertionError(
            "mode 7 must key off the 565 word 0x02E7, so 0x0167 stays "
            "visible; it reads %r" % (as_seven,))
    if as_six == as_seven:
        raise AssertionError("identical bytes read identically under both "
                             "modes -- graphicMode is being ignored")
    print("mode 6 vs 7: same colour -> different pictures; same bytes -> "
          "different visibility")

    six_alpha = (struct.pack("<3I", 0, 0, 0) + struct.pack("<2H", 3, 2)
                 + struct.pack("<BBH", MODE_RGB555, FLAG_ALPHA, 0)
                 + struct.pack("<4h", 0, 0, 0, 0) + struct.pack("<I", 0)
                 + bytes([1, 0, 2, 0, 3, 0, 4, 0, 5, 0, 6, 0])
                 + bytes([0xFF, 0, 0xFF, 0]) + bytes([0, 0xFF, 0, 0]))
    six_grid = pixels(unpack(six_alpha))
    if [[v for v, _ in row] for row in six_grid] != [[1, 2, 3], [4, 5, 6]]:
        raise AssertionError("mode 6's colour plane is not row-packed at "
                             "width*2: %r" % ([[v for v, _ in row]
                                               for row in six_grid],))
    if [[v for _, v in row] for row in six_grid] != [[True, False, True],
                                                     [False, True, False]]:
        raise AssertionError("mode 6's alpha plane is not read at its own "
                             "DWORD stride: %r" % ([[v for _, v in row]
                                                    for row in six_grid],))
    print("mode 6: same 32-byte header, same width*2 colour row, same "
          "DWORD alpha stride, same 2-byte run unit")

    if visible_box(grid) != (1, 0, 2, 1):
        raise AssertionError("visible_box does not skip the keyed pixel")
    if visible_box([[(0, False)]]) is not None:
        raise AssertionError("an all-transparent picture has no box")
    for src, want in (((32, 32), (32, 32)), ((16, 24), (16, 24)),
                      ((64, 64), (32, 32)), ((166, 165), (32, 31)),
                      ((320, 240), (32, 24)), ((16, 128), (4, 32)),
                      ((384, 135), (32, 11))):
        if fit_box(*src) != want:
            raise AssertionError("fit_box%s is %s, not %s"
                                 % (src, fit_box(*src), want))
    print("fit_box: 7 measured sizes, truncating on the longer side")

    small = (struct.pack("<3I", 0, 0, 0) + struct.pack("<2H", 3, 2)
             + struct.pack("<BBH", MODE_RGB565, FLAG_RLE, 0)
             + struct.pack("<4h", 0, 0, 0, 0) + struct.pack("<I", 0)
             + encode_runs(bytes([0, 0, 9, 0, 0, 0]) + bytes(6)))
    got, why = icon_render(unpack(small))
    if why is not None or got != (1, 1, (9,)):
        raise AssertionError("a 3x2 picture with one visible pixel must "
                             "render to that pixel; got %r / %r" % (got, why))
    big = (struct.pack("<3I", 0, 0, 0) + struct.pack("<2H", 64, 1)
           + struct.pack("<BBH", MODE_RGB565, FLAG_RLE, 0)
           + struct.pack("<4h", 0, 0, 0, 0) + struct.pack("<I", 0)
           + encode_runs(bytes([9, 0]) * 64))
    if icon_render(unpack(big)) != (None, RENDER_SCALED):
        raise AssertionError("a 64-wide picture needs a downscale and must "
                             "be declined as %s" % RENDER_SCALED)
    empty = (struct.pack("<3I", 0, 0, 0) + struct.pack("<2H", 2, 1)
             + struct.pack("<BBH", MODE_RGB565, FLAG_RLE, 0)
             + struct.pack("<4h", 0, 0, 0, 0) + struct.pack("<I", 0)
             + encode_runs(bytes(4)))
    if icon_render(unpack(empty)) != (None, RENDER_EMPTY):
        raise AssertionError("a wholly transparent picture must be declined "
                             "as %s, not rendered blank" % RENDER_EMPTY)
    undec = (struct.pack("<3I", 0, 0, 0) + struct.pack("<2H", 2, 1)
             + struct.pack("<BBH", 4, 0, 0)
             + struct.pack("<4h", 0, 0, 0, 0) + struct.pack("<I", 0))
    if icon_render(unpack(undec)) != (None, RENDER_UNDECODED):
        raise AssertionError("graphicMode 4 must be declined as %s"
                             % RENDER_UNDECODED)
    if len({RENDER_UNDECODED, RENDER_SCALED, RENDER_EMPTY}) != 3:
        raise AssertionError("the three reasons must be distinguishable")

    pal3 = bytes([0, 0, 0, 0, 0x80, 0, 0, 0]) + bytes(PALETTE_BYTES - 8)
    for mode, pixel in ((MODE_RGB555, bytes([9, 0])),
                        (MODE_BGR888, bytes([9, 0, 0])),
                        (MODE_PALETTE8, bytes([1]))):
        unit = PIXEL_BYTES[mode]

        body = pixel * row_pixels(1, mode)
        one = (struct.pack("<3I", 0, 0, 0) + struct.pack("<2H", 1, 1)
               + struct.pack("<BBH", mode, RLE_FLAG[unit], 0)
               + struct.pack("<4h", 0, 0, 0, 0) + struct.pack("<I", 0)
               + encode_runs(body, unit))

        got, why = icon_render(unpack(
            one, pal3 if mode == MODE_PALETTE8 else None))
        if why is not None or got[:2] != (1, 1):
            raise AssertionError(
                "icon_render must reach graphicMode %d; it said %r"
                % (mode, why))

    exact = (struct.pack("<3I", 0, 0, 0)
             + struct.pack("<2H", ICON_BOX, 1)
             + struct.pack("<BBH", MODE_RGB565, FLAG_RLE, 0)
             + struct.pack("<4h", 0, 0, 0, 0) + struct.pack("<I", 0)
             + encode_runs(bytes([9, 0]) * ICON_BOX))
    got, why = icon_render(unpack(exact))
    if why is not None or got[0] != ICON_BOX:
        raise AssertionError("a picture exactly %d wide fits and must not be "
                             "declined; got %r" % (ICON_BOX, why))
    print("icon_render: fits -> cut down; larger, undecodable and empty each "
          "declined by NAME")

    if PIXEL_BYTES[MODE_BGR888] != 3 or PIXEL_BYTES[MODE_RGB555] != 2:
        raise AssertionError("the pixel sizes are wrong")
    if sorted(RLE_FLAG.values()) != [0x01, 0x02, 0x04]:
        raise AssertionError("the three run-length flag bits must differ; "
                             "they are %r" % (RLE_FLAG,))

    for args, want in (((33, MODE_BGR888), 34), ((32, MODE_BGR888), 32),
                       ((1, MODE_BGR888), 2), ((11, MODE_PALETTE8), 12),
                       ((11, MODE_RGB565), 11), ((11, MODE_RGB555), 11)):
        if row_pixels(*args) != want:
            raise AssertionError("row_pixels%s is %d, not %d"
                                 % (args, row_pixels(*args), want))
    if colour_row_bytes(33, MODE_BGR888) != 102:
        raise AssertionError("a 33-wide 24-bit row is 34 pixels = 102 bytes")
    if colour_row_bytes(11, MODE_RGB565) != 22:
        raise AssertionError("an 11-wide 16-bit row is 22 bytes, unpadded -- "
                             "the even-pixel rule must NOT reach mode 7")

    odd = (struct.pack("<3I", 0, 0, 0) + struct.pack("<2H", 1, 2)
           + struct.pack("<BBH", MODE_BGR888, 0, 0)
           + struct.pack("<4h", 0, 0, 0, 0) + struct.pack("<I", 0)
           + bytes([0x00, 0x80, 0xFF]) + bytes([0xAA, 0xAA, 0xAA])
           + bytes([0x11, 0x22, 0x33]) + bytes([0xBB, 0xBB, 0xBB]))
    grid = pixels(unpack(odd))
    if [[v for v, _ in row] for row in grid] != [[0xFF8000], [0x332211]]:
        raise AssertionError(
            "a 24-bit pixel is stored BLUE, GREEN, RED, and a 1-wide record "
            "stores a PAD pixel that must not be read; got %r"
            % ([[v for v, _ in row] for row in grid],))
    if transparent_word(0x00385C00, MODE_BGR888) != 0x005C38:
        raise AssertionError("mode 4's key is the colour itself, read out "
                             "RGB; it is 0x%06X"
                             % transparent_word(0x00385C00, MODE_BGR888))

    body = encode_runs(bytes([0x00, 0x80, 0xFF]) * 4, 3)
    comp4 = (struct.pack("<3I", 0, 0, len(body)) + struct.pack("<2H", 2, 2)
             + struct.pack("<BBH", MODE_BGR888, RLE_FLAG[3], 0)
             + struct.pack("<4h", 0, 0, 0, 0) + struct.pack("<I", 0) + body)
    if [[v for v, _ in row] for row in pixels(unpack(comp4))] != [
            [0xFF8000, 0xFF8000], [0xFF8000, 0xFF8000]]:
        raise AssertionError("a mode 4 record does not decode at a 3-byte "
                             "run unit")

    wrong_bit = comp4[:17] + bytes([FLAG_RLE]) + comp4[18:]
    try:
        planes(unpack(wrong_bit))
    except Unsupported:
        pass
    else:
        raise AssertionError(
            "flags 0x02 on a mode 4 record is NOT its run-length bit; "
            "reading it as compressed decodes 24-bit pictures at a 16-bit "
            "stride")

    if to_rgb565(0xFF8000, MODE_BGR888) != 0xFC00:
        raise AssertionError("24-bit 0xFF8000 is RGB565 0xFC00, not 0x%04X"
                             % to_rgb565(0xFF8000, MODE_BGR888))
    if to_rgb565(0x1234, MODE_RGB565) != 0x1234:
        raise AssertionError("a 565 value converts to itself")
    try:
        to_rgb565(0, 5)
    except Unsupported:
        pass
    else:
        raise AssertionError("an unknown mode has no conversion to 565")
    print("graphicMode 4: 3-byte pixel, BLUE first, even-pixel rows, "
          "its own run-length bit, and the editor's 565 conversion")

    pal = bytearray(PALETTE_BYTES)
    for i, (r, g, b) in enumerate([(0x00, 0x00, 0x00), (0x80, 0x00, 0x00),
                                   (0x00, 0x80, 0x00), (0x80, 0x80, 0x00)]):
        pal[i * 4:i * 4 + 3] = bytes([r, g, b])
    pal = bytes(pal)
    if palette_rgb(pal, 1) != 0x800000:
        raise AssertionError(
            "a palette entry is RED, GREEN, BLUE -- entry 1 of the Windows "
            "system colours is dark red 0x800000 and reads 0x%06X"
            % palette_rgb(pal, 1))
    if palette_rgb(pal, 2) != 0x008000 or palette_rgb(pal, 3) != 0x808000:
        raise AssertionError("the palette is not R-first")
    for bad in (None, bytes(16)):
        try:
            palette_rgb(bad, 0)
        except Unsupported:
            pass
        else:
            raise AssertionError("a missing or short palette must be refused")

    def paletted(indices, w, h, flags, transparent, palette):
        body = (encode_runs(indices, 1) if flags & RLE_FLAG[1] else indices)
        return unpack(
            struct.pack("<3I", 0, 0, len(body)) + struct.pack("<2H", w, h)
            + struct.pack("<BBH", MODE_PALETTE8, flags, 0)
            + struct.pack("<4h", 0, 0, 0, 0)
            + struct.pack("<I", transparent) + body, palette)

    rec3 = paletted(bytes([1, 0xFF, 2, 0xFF]), 1, 2, 0, 0x00FFFFFF, pal)
    grid = pixels(rec3)
    if [[v for v, _ in row] for row in grid] != [[0x800000], [0x008000]]:
        raise AssertionError(
            "a mode 3 row stores an even number of indices and the pad must "
            "not be read; got %r" % ([[v for v, _ in row] for row in grid],))

    rec3 = paletted(bytes([1, 0, 2, 0]), 2, 2, 0, 0x00000080, pal)
    if [[v for _v, v in row] for row in pixels(rec3)] != [[False, True],
                                                          [True, True]]:
        raise AssertionError(
            "COLORREF 0x00000080 is dark red, which is palette entry 1, so "
            "only the index-1 pixel is invisible; got %r"
            % ([[v for _v, v in row] for row in pixels(rec3)],))

    rec3 = paletted(bytes([1, 0, 2, 0]), 2, 2, 0, 0x00123456, pal)
    if any(not v for row in pixels(rec3) for _c, v in row):
        raise AssertionError("a transparent colour absent from the palette "
                             "must hide nothing")

    rec3 = paletted(bytes([2, 2, 2, 2]), 2, 2, RLE_FLAG[1], 0, pal)
    if [[v for v, _ in row] for row in pixels(rec3)] != [[0x008000] * 2] * 2:
        raise AssertionError("a mode 3 record does not decode at a 1-byte "
                             "run unit")
    wrong = paletted(bytes([2, 2, 2, 2]), 2, 2, RLE_FLAG[1], 0, pal)
    wrong["flags"] = RLE_FLAG[3]
    try:
        planes(wrong)
    except Unsupported:
        pass
    else:
        raise AssertionError("flags 0x04 is NOT mode 3's run-length bit")

    bare = paletted(bytes([1, 0, 2, 0]), 2, 2, 0, 0, None)
    if planes(bare)[0] != bytes([1, 0, 2, 0]):
        raise AssertionError("a mode 3 record's PLANES need no palette")
    try:
        pixels(bare)
    except Unsupported as exc:
        if "palette" not in str(exc):
            raise AssertionError("the refusal must name the palette")
    else:
        raise AssertionError("mode 3 without a palette must refuse to give "
                             "COLOURS rather than invent them")

    other = bytearray(pal)
    other[4:7] = bytes([0x11, 0x22, 0x33])
    a = picture(paletted(bytes([1, 0, 1, 0]), 2, 2, 0, 0, pal))
    b = picture(paletted(bytes([1, 0, 1, 0]), 2, 2, 0, 0, bytes(other)))
    if a == b:
        raise AssertionError(
            "two mode 3 records with the same indices and different palettes "
            "must NOT compare equal, or the palette is being ignored")
    print("graphicMode 3: 8-bit indices, R-first palette, its own "
          "run-length bit, and no colours without a palette")

    for mode in (5, 9):
        bad = (struct.pack("<3I", 0, 0, 0) + struct.pack("<2H", 1, 1)
               + struct.pack("<BBH", mode, 0, 0)
               + struct.pack("<4h", 0, 0, 0, 0) + struct.pack("<I", 0))
        try:
            planes(unpack(bad))
        except Unsupported:
            pass
        else:
            raise AssertionError("graphicMode %d must be refused" % mode)

    ok_six = (struct.pack("<3I", 0, 0, 0) + struct.pack("<2H", 1, 1)
              + struct.pack("<BBH", MODE_RGB555, 0, 0)
              + struct.pack("<4h", 0, 0, 0, 0) + struct.pack("<I", 0)
              + struct.pack("<H", 0x1234))
    if planes(unpack(ok_six)) != (struct.pack("<H", 0x1234), None):
        raise AssertionError("graphicMode 6 must decode")
    ok_four = (struct.pack("<3I", 0, 0, 0) + struct.pack("<2H", 2, 1)
               + struct.pack("<BBH", MODE_BGR888, 0, 0)
               + struct.pack("<4h", 0, 0, 0, 0) + struct.pack("<I", 0)
               + bytes([1, 2, 3, 4, 5, 6]))
    if planes(unpack(ok_four))[0] != bytes([1, 2, 3, 4, 5, 6]):
        raise AssertionError("graphicMode 4 must decode")
    try:
        decode_runs(bytes([0x84, 1, 0]), 4)
    except Unsupported:
        pass
    else:
        raise AssertionError("a literal run past the end must be refused")
    try:
        decode_runs(bytes([0x00, 1, 0]), 4)
    except Unsupported:
        pass
    else:
        raise AssertionError("a zero-length run must be refused")
    print("refusals: unknown modes -- 3, 4, 6 and 7 decode -- an "
          "overrunning run, a zero run")
    print("all checks passed")
