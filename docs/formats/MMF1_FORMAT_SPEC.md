# Multimedia Fusion 1.0 — File Format Specification
justaddwater 
https://github.com/just-addwater/KlikBack

A reference for the binary formats written by Clickteam's **Multimedia Fusion
1.0 / 1.2** (runtime builds 87–98, 1998–2001). It covers the compiled runtime
package found inside standalone `.exe` games and `.ccn` sub-application files,
with a shorter section on the editor's `.cca` project format.


All integers are **little-endian**. `u8`/`u16`/`u32` are unsigned,
`i16`/`i32` signed. Strings are NUL-terminated ANSI (Windows codepage) unless
noted.

---

## 1. The runtime package

A compiled MMF application is a chunk stream called a **PAME package**:

```text
"PAME"          char[4]  signature
u8  product     0 = MMF 1.0/1.2, 1 = MMF 1.5, 2 = Fusion 2.x
u8  major       3 for the whole MMF generation (2 = the 1996 Klik line)
u8  [10]        remaining header bytes
                chunks begin at offset +0x10
```

The package appears in three places:

| File | Layout |
|---|---|
| `.ccn` | Bare package; `PAME` at offset 0 |
| Standalone `.exe` | Runtime stub (a PE executable), then an optional extension-binary chunk stream, then the package as overlay |
| `.exe` + companion `.ccn` | A Sub-Application in external-file mode ships a second, separate `.ccn` beside the parent — never a second `PAME` inside the same file |

**Locating the package in an executable:** the four signature bytes also occur
by chance inside the runtime stub's code, so do not accept the first match.
A candidate header is valid only when chunk id `0x2223` sits at `header+16`.
Match the id as a `u16` — the adjacent flags word differs between `.exe`
(flags 1) and `.ccn` (flags 0) packages.

### 1.1 Chunk framing

```text
u16 chunk_id
u16 flags          0 = stored, 1 = Clickteam-compressed
u32 payload_size
u8  payload[payload_size]
```

A compressed payload may contain **several concatenated compression blocks**;
decompression must loop until the payload is consumed, not translate a single
block.

### 1.2 Clickteam compression

A DEFLATE-like bitstream with nonstandard framing:

- a 3-bit block type is followed by a 1-bit final flag;
- block type **5** = fixed Huffman, **6** = dynamic Huffman, **7** = stored;
- the dynamic code-length symbol order is `18, 17, 16, 0..15` — not the
  standard DEFLATE order.

It is not a zlib stream and has no standard wrapper.

---

## 2. Application-level chunks

| ID | Meaning |
|---:|---|
| `0x2223` | Application header (always first) |
| `0x2224` | Application name, NUL-terminated |
| `0x2225` | Author, NUL-terminated |
| `0x2226` | Custom application menu (verbatim editor menu payload); absent when the default menu is inherited |
| `0x2228` | Extension module table (§7) |
| `0x2229` | Object bank (§4) |
| `0x222B` | Frame item-id table (§3.2) |
| `0x222C` | Embedded extension binaries — a separate stream *before* the package in a standalone (§7.3) |
| `0x222E` | Absolute path of the source `.cca` on the build machine |
| `0x222F` | Absolute path of the build target `.exe` |
| `0x2230` | Help file path; absent when none is set |
| `0x2231` | Transition module list: `u16 count`, then NUL-terminated DLL names |
| `0x2232` | Global values (§2.2) |
| `0x2233` | Application window icon: 640 bytes of raw 32×32×16 bitmap (512-byte XOR plane + 128-byte AND mask, no header or palette) |
| `0x3333` | Frame container, repeated once per frame (§3) |
| `0x5555`–`0x5558` | Handle-indexed offset tables for the four media banks (§6.4) |
| `0x6666` | Image bank (§6.1) |
| `0x6667` | Font bank (§6.2) |
| `0x6668` | Sample bank; may be absent when empty (§6.3) |
| `0x6669` | Music bank (§6.3) |
| `0x7F7F` | Terminator |

`0x222E` and `0x222F` are build-machine metadata, not project content — they
are why two otherwise-identical builds differ in size, and they should be
excluded from structural comparisons.

### 2.1 Application header (`0x2223`)

Known fields:

| Offset | Field |
|---|---|
| `+0x00` | `u32` display/run flags word (see below) |
| `+0x04` | `u16` pixel mode: 3 = 256 colours, 4 = 16 million (the editor also has a 32,000-colour mode) |
| `+0x0C` | `u32` starting score |
| `+0x10` | `u32` starting lives |
| `+0x14` | 56 bytes of player controls: four `u16` per-player controller selectors (3 = keyboard, 1/2 = joystick), then four blocks of six `u16` key codes (up, down, left, right, fire 1, fire 2) as Windows virtual-key codes |

The flags word packs the editor's window/run-options checkboxes. Direct
mappings: bit 9 = maximized on boot, bit 4 = resize display to fill window,
bit 11 = change resolution mode, bit 12 = allow full-screen switching,
bit 0 = heading when maximized, bit 3 = machine-independent speed,
bit 10 = multi-sample, bit 16 = play samples over frames, bit 19 = don't stop
samples on focus loss. Builds 92+ add bits 20–23: no minimize box, no maximize
box, no thick frame, don't centre the frame area.

Three checkboxes (heading, menu bar, menu displayed on boot) are stored only as
XOR combinations in bits 1, 7 and 8: a setting and its exact complement compile
identically. Assuming the heading is on resolves the other two and matches
every real-world application tested.

### 2.2 Global values (`0x2232`)

```text
u16 count
i32 initial_values[count]
u8  flags[count]
```

Names of global values do not survive compilation; only indices and numeric
initial values do.

---

## 3. Frames (`0x3333`)

Each frame is itself a chunk stream:

| ID | Meaning |
|---:|---|
| `0x3334` | Frame header (see below) |
| `0x3335` | Frame name; absent for an empty/default title |
| `0x3336` | Frame password, verbatim bytes (usually plaintext); present iff frame flag `0x0040` is set |
| `0x3337` | Palette; four bytes precede the palette data |
| `0x3338` | Placements (§3.1); absent when the frame has none |
| `0x333B` | Fade-in transition (§5) |
| `0x333C` | Fade-out transition (§5) |
| `0x333D` | Compiled events (§8) |

The decompressed frame header (`0x3334`) is exactly 10 bytes:

```text
+0x00  u16   width
+0x02  u16   height
+0x04  u8[4] background colour, B G R 0
+0x08  u16   frame flags
```

Frame flags: `0x0001` = show frame title in caption, `0x0002` = grab desktop
at start, `0x0004` = keep display from previous frame, `0x0020` = handle
background collisions outside the window, `0x0040` = frame has a password,
`0x0100` = resize display to fit. The `u16` at `0x333D+4` is the frame's
"number of objects at runtime" setting (default 300). The u16 at ER>> payload offset +0x04 within the decompressed 0x333D event chunk is the frame’s “number of objects at runtime” setting.

MMF 1.0 uses **one application-wide palette**; every frame's `0x3337` is a
copy. Per-frame palette variation is possible.

### 3.1 Placements (`0x3338`)

A `u32` count, then records of:

```text
u16 instance_id
u16 object_id       application object id
i16 x
i16 y
u32 runtime_link
```

`runtime_link` = 0 for an ordinary placement. Nonzero marks a **create/shoot
placeholder** compiled at x=0, y=0: the low word is 1 for a Create Object
target or 2 for a Shoot target, and the high word is the shooting object's
application object id (0 for create). Placeholders exist so the runtime has an
object record to clone; the Create/Shoot action carries its real position.

### 3.2 Frame item ids (`0x222B`)

Frames carry permanent **item ids** that are independent of frame order —
inserting, deleting or reordering frames in the editor never renumbers them.
`0x222B` is a `u16` array indexed by item id whose value is the frame ordinal.

This matters because a **frame-jump event targets an item id, not an
ordinal** (§8.4). Deleted frames leave zeroed slots; since 0 is also a valid
ordinal, the entry for ordinal 0 can be ambiguous in projects that deleted
frames — every other ordinal is uniquely determined.

---

## 4. The object bank (`0x2229`)

Each object is a nested chunk group:

| ID | Meaning |
|---:|---|
| `0x4444` | Object header |
| `0x4445` | Object name; **omitted for Backdrop and Quick Backdrop** (their names are a compile-time loss) |
| `0x4446` | Type-specific definition |
| `0x7F7F` | Object terminator |

### 4.1 Object types

| Type | Object |
|---:|---|
| 0 | Quick Backdrop |
| 1 | Backdrop |
| 2 | Active |
| 3 | String |
| 4 | Question & Answer |
| 5 | Score |
| 6 | Lives |
| 7 | Counter |
| 8 | Formatted Text |
| 9 | Sub-Application |
| 32 + *n* | Extension in module-table slot *n* (§7) — per-application, never universal |

### 4.2 Object header (`0x4444`)

Begins with the object id and type. Other proven fields:

| Offset | Field |
|---|---|
| `+0x04` | `u16` memory-option flags: `0x01` load on call, `0x02` discardable, `0x04` global |
| `+0x08` | `u16` ink-effect index (none, transparent, anti-aliasing, semi-transparent, inverted, XOR, AND, OR) |
| `+0x0A` | `u16` bitfield: `0x1000` transparent, `0x2000` anti-aliasing |
| `+0x0C` | `u32` ink-effect amount (0–100 for semi-transparent) |

### 4.3 Common object definition (`0x4446`)

The definition shares one common layout across all types, including
extensions:

| Offset | Field |
|---|---|
| `+0x04` | `u16` movement-block offset; 0 = static/default |
| `+0x06` | `u16` animation-table offset |
| `+0x0C` | `u32` offset of the type-specific payload (Counter family, String, Sub-App, …) |
| `+0x12` | `u16` OEFLAGS (extensions) |
| `+0x13` | `u8` flags: `0x08` deselects "follow the frame" (HUD pinning), `0x20` deselects "destroy if too far from frame", `0x40` deselects "inactivate if too far", `0x10` object-display flag |
| `+0x14`–`+0x25` | Qualifier list: nine `u16` slots, terminated by the first `0xFFFF` (bytes after the terminator are uninitialised, not padding). The runtime can fill all nine; the editor accepts at most eight |
| `+0x24` | `u32` EDITDATA offset (extensions only — overlays the qualifier area's tail; read it, don't assume 60) |
| `+0x26` | `u16` offset of the alterable-value initial table (builds 94+): `u16 count`, `i32 values[count]`. Build 87 discards initial values and stores 0 here |
| `+0x28` | `u8` flags: `0x01` save background, `0x02` wipe with colour, `0x04` deselects fine collisions (Actives only), `0x08` visible at start |
| `+0x2C` | `char[4]` type tag: `SPRI`, `CNTR`, `TEXT`, `LIVE`, `SCRE`, `RTF `, `QSTN`, `CCA `, or an extension's own identifier |
| `+0x30` | `u32` object colour (used by "wipe with colour") |
| `+0x34` | `u32` fade-in transition offset, 0 = none |
| `+0x38` | `u32` fade-out transition offset |

Qualifier ids follow the editor dialog order: 0 Player, 1 Good, 2 Neutral,
3 Bad, 4 Enemies, 5 Friends, 6 Bullets, 7 Arms, 8 Bonus, 9 Collectables,
10 Traps, 11 Doors, 12 Keys, 13 Texts; numeric qualifiers "0"–"9" are 14–23,
unnamed slots continue to 99.

### 4.4 Movement block

Located by the offset at `+0x04`:

```text
u16 player        1-based controlling player; 0 = computer-controlled
u16 movement_type
... type-specific data
```

| ID | Movement |
|---:|---|
| 1 | Mouse |
| 2 | Race (car) |
| 3 | Eight directions |
| 4 | Ball |
| 5 | Path |
| 9 | Platform |

### 4.5 Animations

The animation table holds standard animation slots 0–11 (Stopped, Walking,
Running, Appearing, Disappearing, Bouncing, Shooting, Jumping, Falling,
Climbing, Crouch down, Stand up) plus user animations. Direction records carry
their direction id internally; physical record order is not significant.
Custom animation names survive compilation only when referenced by an event
parameter.

### 4.6 Type-specific payloads

Reached through the `u32` offset at definition `+0x0C` unless noted.

**Counter** (at fixed definition offsets): `i32` initial/minimum/maximum at
`+0x3E`, dimensions at `+0x4E`, image count at `+0x58`, then `u16` image
handles. Display modes: 0 hidden (payload omitted), 1 numbers, 2 vertical bar,
3 horizontal bar, 4 animation. Bar counters store fill data and a reverse
flag (`0x0100`) controlling count/growth direction.

**String**: paragraph-table offset is a `u32` at `+0x0C`; the table is
`u32 size`, `u16` width/height/count, `u16` offsets, then per paragraph
`u16 size, u16 font (0xFFFF = default), u32 colour (RGB0), u16 0`,
NUL-terminated text.

**Lives / Score** (payload): `u16` width/height at `+4`/`+6`, **1-based player
at `+8`**, display selector at `+10` (1 = numbers, 4 = picture), image count
at `+14`, `u16` handles from `+16`. Numbers mode uses 14 image frames: digits
0–9 then `-`, `+`, `.`, `e`.

**Formatted Text** (payload): `u16` width/height at `+0x10`, `u32` RTF length
at `+0x18`, RTF text at `+0x1C`. Offsets are payload-relative — the payload is
*usually* at definition offset 60, but not always.

**Quick Backdrop**: obstacle type at `+0x04`, `u16` width/height at `+0x08`,
fill kind at `+0x12`, fill selector at `+0x14` (0 none, 1 solid colour,
2 gradient, 3 motif image), values from `+0x16`.

**Question & Answer** (payload): `u16` width/height/count at `+4`, `u16`
string offsets at `+10`; each string is `u16 size, u16 font, u32 colour,
u8 5, u8 correct_flag`, NUL-terminated text; the first string is the
question.

**Sub-Application** (type 9, payload; external-file mode):

```text
u32 leading_value    0 in external-file mode
u16 width
u16 height
u32 reserved         0 in external-file mode
u32 options          bit 3 (0x08) default; sharing/resize bits above
char child_path[]    NUL-terminated; the compiler rewrites .cca → .ccn
```

The stored child path is absolute at build time; resolve the basename beside
the parent executable.

---

## 5. Transitions

A frame's transitions are chunks `0x333B`/`0x333C`; an object's are appended
after its animation table at the offsets in definition `+0x34`/`+0x38`. Both
use one record:

```text
+0x00 char[8] internal id      +0x08 u32 duration (ms)
+0x0C u32 flag                 +0x10 u32 colour
+0x14 u32 module name offset   +0x18 u32 parameter offset
+0x1C u32 parameter length     then module name, then parameters
```

The internal id's first four characters name the module and the last four the
transition. Known ids: `CCTrans.dll` — `STDTBAND` Bands, `STDTDOOR` Door,
`STDTFADE` Fade, `STDTMOSA` Mosaic, `STDTSCRL` Scrolling, `STDTZIGZ` Zigzag,
`STDTZOOM` Zoom; `SFTrans.dll` (third-party) — Alpha Zoom, Color Fade, Circle,
Fan, Stretch, Tile Zoom and others. The human-readable display name is not
stored in the runtime; a transition module carries its names as UTF-16
resource strings.

---

## 6. Media banks

All four banks (`0x6666` images, `0x6667` fonts, `0x6668` samples, `0x6669`
music) share one record layout:

```text
u32 count
per record:
    u32 handle
    u32 decoded_size
    <Clickteam-compressed stream>
```

### 6.1 Images (`0x6666`)

Images are individually Clickteam-compressed and keyed by handle. Handles
need not be monotonic in stream order and must be preserved. The image record
header (after decompression) carries `u16 width`, `u16 height` at
`+0x0A`/`+0x0C`, a colour-mode byte at `+0x0E` and a flags byte at `+0x0F`
whose low nibble, when nonzero, means the pixel data is stored in the
editor's RLE form; whether an image is stored raw or RLE is a per-image
compiler choice.

The application's icons are **not** in the image bank of a standalone: they
live in ordinary PE resources (`RT_ICON` id 1 = 32×32, id 2 = 16×16) as 4-bit
DIBs with XOR and AND planes. Chunk `0x2233` duplicates the 32×32 icon.

### 6.2 Fonts (`0x6667`)

`u32 count`, then per font: `u32 handle`, `u32 size` (always 104), and a
Clickteam-compressed 104-byte LOGFONT-style descriptor carrying the typeface
name and weight. Because the records are compressed, face names never appear
in a raw scan of the file.

### 6.3 Samples (`0x6668`) and music (`0x6669`)

Sample records embed WAVE data — format tag 1 (PCM) or 2 (Microsoft ADPCM,
with block geometry and coefficient table embedded). Music records hold MIDI.
An application with no samples may omit `0x6668` entirely.

### 6.4 Offset tables (`0x5555`–`0x5558`)

Each bank has a companion chunk — `0x5555` indexes `0x6666`, `0x5556`
indexes `0x6667`, `0x5557` indexes `0x6668`, `0x5558` indexes `0x6669` —
that is stored uncompressed and carries no count:

```text
u32 offsets[table_length / 4]    one slot per handle
```

A zero slot means the handle has no asset; otherwise the record header sits
at `offset − 4` in the bank payload (the −4 being the bank's own leading
count). The slot index *is* the handle, the non-zero slot count equals the
bank's record count, and the sorted offsets partition the bank payload
exactly — the tables are purely derived data and can be regenerated from the
bank.

---

## 7. Extension objects (`.cox`)

Extensions are DLLs (`.cox`) providing new object types. Their private data
(**EDITDATA**) survives compilation untouched, which is what makes
extension-using games fully recoverable.

### 7.1 Module table (`0x2228`)

```text
u16 count           number of entries
u16 slots           allocator high-water mark — NOT a copy of count
per entry:
    u16 entry_size  includes this field
    u16 index       the module's slot; values may be skipped
    u32 stamp       0x59082516 in every sample
    char[] module filename, NUL-terminated
    u8  pad
```

Deleting an extension in the editor frees its slot without renumbering, so
`index` is a slot, not a list position. **An extension object's runtime type
is `32 + slot`** — resolve modules by slot, never by list position, and never
assume a type number is the same in another application. A core-only
application still carries the chunk with `count = 0`.

### 7.2 Extension definitions

The definition is the common object definition (§4.3) with the qualifier list,
flag bytes and transition offsets keeping their usual meaning, plus:
OEFLAGS at `+0x12`, the EDITDATA offset at `+0x24`, and the extension's
four-character identifier at `+0x2C`. The EDITDATA begins with the Clickteam
SDK `extHeader` (`i16 extSize, extMaxSize, extOldFlags, extVersion`), so its
length and data version are self-describing; the definition ends exactly at
`editdata_offset + extSize`.

Extension actions are opcode `48 + index` (counting up); conditions are
`207 − index` (counting down). Built-in objects use the same opcode spaces.
Event rows with conditions but no actions are dropped at compile time.

### 7.3 Embedded binaries (`0x222C`)

A standalone embeds the `.cox` files it needs and unpacks them at startup.
They form a second chunk stream between the host executable and the `PAME`
overlay, terminated by `0x7F7F`:

```text
u16 0x222C, u16 flags, u32 size
char[] module filename, NUL-terminated
u8  image[...]      a PE32 i386 DLL
```

A Sub-Application parent embeds the de-duplicated union of parent and child
dependencies. Validate the stream start by walking chunk lengths onto the
terminator — the marker bytes also occur by chance inside the host executable.

---

## 8. Compiled events (`0x333D`)

### 8.1 Container

```text
"ER>>"  46-byte header + variable tail (below)
"ERes"  u32 total_event_payload_bytes
    "ERev" u32 program_size   event records[program_size]
    "ERev" u32 program_size   event records[program_size]
    ...
"<<ER"
```

The `ER>>` header: the `u16` at `+0x04` is the frame's "number of objects at
runtime" (0 in Build 87, default 300 later); `+0x06`/`+0x08` vary per frame;
`+0x0A` through `+0x2A` are per-version constants (every 1.0 build writes
`7, 10, 23, 6, 5, 6, 15, 51` at `+0x0A/+0x0C/+0x0E/+0x10/+0x12/+0x14/+0x16/
+0x2A` — MMF 1.5 differs, making these a reliable version discriminator);
the `u16` at `+0x2C` is a **tail count**, usually 0, and `ERes` begins at
`0x2E + 4 × count`. `ERes` equals the sum of the `ERev` payload sizes,
excluding their 8-byte headers.

A frame holds one or more **programs**, in a fixed order: the frame's own
event sheet, then the application's global-event sheet (copied into every
frame it applies to), then object behaviours in application-object order.
Empty sheets emit no program at all, and an `ERev` header carries no owner id
— so a lone program's role (frame sheet vs. behaviour vs. global sheet) is not
directly recorded. Global events and behaviours compile to byte-identical
programs; the global sheet is recognisable only as the program recurring
across every frame its objects reach.

### 8.2 Event records

```text
i16 negative_record_size    |value| = record length
u8  condition_count
u8  action_count
... fixed header through +0x0D
... condition records (14-byte fixed headers)
... action records   (12-byte fixed headers)
```

The field at `+0x0A` is the row's 1-based number in the editor event list —
effectively a **byte**: a sheet longer than 255 rows wraps and reuses every
value, so the number identifies a row only on short sheets. The byte at
`+0x0C` is an editor revision counter preserved verbatim through
compilation. Compilation drops editor-only rows (comments, condition-only
rows) **without renumbering**, so the gaps in the surviving row numbers name
the exact positions of every stripped comment row.

Condition and action records share a header:

```text
u16 record_size
u8  object_type      0x00–0x7F object type; >= 0xF0 system family
u8  opcode
u16 object_word      object/qualifier when type < 0x80
...parameters
```

System families: `0xFF` special/groups, `0xFE` sound, `0xFD` storyboard,
`0xFC` timer, `0xFB` create-new-objects, `0xFA` mouse/keyboard, `0xF9`
player. Qualifier references set bit 15 of the object word
(`0x8000 | qualifier_id`); real objects use plain application object ids.
System-family object words are family-specific values, not object references.

System-family opcode ranges observed across the Build-98 era (useful when
mapping an unknown number): special actions run 0–13 and special conditions
−1 to −14. Extension actions are `48 + index` counting up and extension
conditions `207 − index` counting down; built-in object-specific ACEs use
the same base of 48, as do object-specific expressions.

### 8.3 Parameters

Each parameter record begins with a `u16` size word (not a `u32`), followed
by `u16 type` and the type-specific payload. Proven types:

| Type | Content |
|---:|---|
| 1 | Object/qualifier reference at `+6` (the `u16` at `+8` is cached type metadata, not authoritative) |
| 6 | Play Sample: `u16` sample handle at `+4`, `u16` options at `+6` (bit 0 = uninterruptible), 64-byte sample name |
| 7 | Music handle |
| 9, 18 | Create Object / Shoot: object reference at `+4` (`0xFFFE`/`0xFFFF` = absolute position), placeholder instance id at `+0x1A`, target object at `+0x1C` |
| 10 | Animation reference |
| 15, 22, 23, 45 | Expression token stream with embedded object references |
| 16, 21 | Position: object reference at `+4` with the same sentinels |
| 24 | Colour |
| 26 | Frame jump target — a frame **item id**, not an ordinal (§3.2) |
| 38 | Group header: `u32` (low word: start-inactive bit) + 80-byte NUL-padded group name |
| 39 | Runtime event-group pointer |

An expression parameter's payload is `u16 size, u16 type, i16 comparison`,
then a token stream ending in a `u16 0` terminator. Each token is:

```text
i8  object_type      signed: -1 (0xFF) special, -7 (0xF9) player, ...
i8  expression_number
u16 token_size       includes this 4-byte header
u16 object_id        only for object families (type > 0) and player
i16 object_info_list same condition
... payload
```

Special expression 0 (`0x00FF`) is an integer literal, 3 a string literal,
4 the editor's number-to-string wrapper, 253 (`0xFDFF`) the argument
separator, and 254 (`0xFEFF`) closes one argument list (a nested call closes
once per level). Object-specific expression numbers start at 48, the same
base as object-specific actions. An object token's low byte encodes the
referenced object's runtime type only for token codes `0x3000` and above
(the retrieve-data-from-object family); lower families store a constant
`0x02` there as part of the opcode.

### 8.4 Groups

Event groups open with special condition **−10** (a group-open row carrying
the type-38 name parameter) and close with special condition **−11**; both
are conditions of object family `0xFF`, and both rows also carry a bare
parameterless special action 0 as their companion action. Each program
normally balances its own markers, though a handful of real games shipped
compiler-emitted unbalanced programs; the editor itself never saves one.

A compiled group-close row is always a **40-byte record**, constant across
whole corpora apart from its row number/index and a few known scratch
bytes — which is what makes one close usable as a template for repairing an
unclosed group.

---

## 9. The editor format (`.cca`)

The editor project is a different serialization built from tagged class
records rather than chunks. Highlights:

- The file begins with a 14-byte container header:

  ```text
  +0x00  char[4]  "CnC2"
  +0x04  u8       product letter: 'T' = MMF 1.0/1.2
  +0x05  u8       version major (1)
  +0x06  u8       version minor: 0 = MMF 1.0, 2 = MMF 1.2
  +0x08  u16      1
  +0x0A  u32      format revision (87 in Build-98 saves — not the editor build)
  +0x0E           first editor bank tag
  ```

- Class blocks are framed as a record tag, 8 zero bytes, the 8-byte signature
  `"Ver 1.1\0"`, a loader-validated property count, a per-save stamp `u32`
  (shared by every record written in the same save, arbitrary on load), and a
  length-prefixed class name (`LApplication`, `LFrame`, `LActItem`,
  `LExtendItem`, …).
- Object properties use four-character tags (`ItNa` name, `ItIc` icon, `InkF`
  ink effect, `Qual` qualifiers, `LEvt` behaviour events, `FadI`/`FadO`
  transitions, …) with a common wrapper; each property entry is
  `u8 type, u8 index, u16 size, u32, u32`, and a size word of `0xFFFF` means
  "inherit the default" and stores no value.
- Media live in editor banks: `AGMI` (images and icons), `APMS` (samples),
  `ASUM` (music), `ATNF` (fonts). There are **two `AGMI` banks, in order**:
  bank 1 holds editor-only artwork (30×30 object icons, 64×48 frame
  thumbnails, application icons), bank 2 is the runtime image bank.
- Frame event sheets reference objects through a per-frame registry
  (`COIList`) that excludes Backdrop and Quick Backdrop and assigns ids in
  frame-item order, with qualifier entries after object entries.

### 9.1 The `AGMI` image bank

```text
u32, u16, u16                 bank header
u8[1024]                      256 palette entries, B G R 0
u32 count
per image:
    u32 index                 easy to miss — omitting it desynchronises
    u32 id
    u16
    u32 rle_length
    u16 width, u16 height
    u16 flags
    i16 hot_x, i16 hot_y      hotspot
    i16 act_x, i16 act_y      action point
    u8  rle_data[rle_length]
```

Editor images use a run-length encoding of palette indices; index 0 is
transparent.

### 9.2 The `PROP` index block

Every class block is followed — after three uninitialised scratch bytes, a
`u16` entry count and the marker `01 00 50 00 00 "PROP"` — by a property
index:

```text
per entry:
    u16     0
    u16     tag_length, char tag[]     FadI, AltV, ItNa, LEvt, Qual, ...
    u16     name_length, char name[]   0 for every tag except LEvt,
                                       where it holds the Behaviour name
    u32     id                         the tag's mnemonic reversed + prefix
                                       (LEvt → "dEVT"); match on the tag
```

The entry count lists every property the class *can* carry (14 for
`LApplication`, 21 for an Active), not the properties actually written. The
`LEvt` name slot is where an authored Behaviour name lives — it is
recoverable from a `.cca` and never from a compiled executable.

### 9.3 Behaviour and global-event containers

Event sheets are stored per frame (`Evts`), per object (`LEvt` behaviours),
and per application (`GEvt` global events). Behaviour and global sheets use
a `KLBEDAEH` ("HEADEBLK" reversed) container:

```text
KLBEDAEH  u16 0x0300  u16 count  u32 editor_state
STVE  u32 event_bytes   editor event records   u16 0
[SMER  u32 20  "class CEvtRemarkList"  u32 count  EvRk...]   comment rows
[SPRG  u32 20  "class CGroupInfoList"  u32 count  EvGI...]   event groups
[SJBO  u32 13  "class COIList"         u32 count  EvOi...]   object registry
!DNE
```

- `editor_state` bit 0 is set exactly when an `SPRG` block follows.
- An `EvGI` group record is fixed 90 bytes: `EvGI`, `u32 flags`, `u16 flags`,
  then an 80-byte NUL-padded name. Both flag fields repeat the high word of
  the group-open condition's type-38 parameter; the name must be truncated
  at its NUL (the tail is uninitialised heap).
- In a registry entry, an owner word of 1 (a behaviour's owning object)
  writes `OIC0` and nothing else; an owner word of 0 (a referenced object)
  writes `OICO`, a `u32` size, and `GMIC` followed by the object's editor
  icon record body.
- An application with no global events stores the inherited sentinel
  `0xFFFF` in `GEvt`'s length word.

Compilation copies the global sheet into every frame's event container as an
ordinary program (dropping rows whose conditions name objects absent from
that frame), which is why its identity is not directly recorded in a
standalone (§8.1).

### 9.4 Registry records (`EvOi`)

Object and qualifier entries have different lengths — one shape for both
desynchronises on every qualifier-bearing frame:

```text
object:    "EvOi" u32 localIndex, u16 1, u16 runtimeType,
           u32 len + name, u32 len + typeString,
           u16 0, u32 frameItemId, i32 placeholderInstance
qualifier: "EvOi" u32 localIndex, u16 3, u16 qualifiedType,
           u32 len + name, u32 len + "Sprite", u16 0, u16 qualifierId
```

`placeholderInstance` is `0xFFFFFFFF` unless the object has a create/shoot
placeholder, in which case it holds that placeholder's instance id.
Qualifier display strings are `Group.<Label>` for named ids, `Group.<n−14>`
for numeric ids and `Group.<id>` for unnamed slots. Extension entries store
the runtime type and the four-character identifier from definition `+0x2C`
as the type string.

A frame's registry holds a qualifier entry **exactly when some object in
that frame is a member of that qualifier** — membership, not event
reference, is the source (most qualifier entries in real games are named by
no row at all).

### 9.5 The frame tail, and the two ids that index it

A frame record's tail is a fixed walk, never a tag search:

```text
class cHandleItemList<class LFrameItem>          u32 count, object records
class cHandleItemList<class LFrameItemInstance>  u32 count, 32-byte records
evpg <4 bytes>
  [Evts u32 size   editor event records]
  [Rems u32 20 "class CEvtRemarkList" u32 count
      per remark: EvRk u32 row, u32 length, text]
  [EvOb u32 13 "class COIList" u32 count, EvOi entries]
  EvEd ...
```

`Evts`, `Rems` and `EvOb` are each omitted when empty; when present, `Rems`
sits **between** `Evts` and `EvOb` (note this is the reverse of the `GEvt`
container's `SMER`/`SPRG`/`SJBO` order).

Two ids index this structure, and **neither is a list position**:

- The **frame item id** is the `u32` immediately before `icnI` in an object
  record (equivalently, immediately before the frame's `Pltt` block for the
  frame's own id). MMF allocates item ids from a free list, so real
  projects hold non-consecutive sets.
- The **registry id** an event row names is the `EvOi` entry's own leading
  `u32`. Deleting an object leaves a gap: the editor prunes unreferenced
  entries without renumbering the survivors.

Both wrong readings (treating either id as an index) pass every small
sequentially-built test project and fail on real games.

### 9.6 Comment rows

An event-editor comment is **two bound structures**, both editor-only:

- a 146-byte row in `Evts` whose single condition is special condition
  **−9** carrying a 102-byte type-37 parameter (a LOGFONT — face, size,
  style — describing how the row is drawn), plus the companion special
  action 0;
- an `EvRk` entry in `Rems` carrying the comment's text.

The row binds to its text through a **`u16` at row offset `+0x5C`**
matching the `EvRk` entry's id (reading a `u32` there fails — `+0x5E`
begins the font style name). The row's colours are two `COLORREF`s
(`0x00BBGGRR`): text at `+0x52`, background at `+0x56`. The compiled
output drops the whole pair, but because compilation does not renumber
(§8.2), the *positions* of stripped comments are recoverable; their text is
not.

### 9.7 The `Qual` property's four forms

The qualifier-membership property is a fixed-capacity array of `u16` words
terminated by `0xFFFF`; the capacity (8 or 9 words) is a property of the
saving project and everything past the terminator is uninitialised. Four
forms occur, and three of them mean "no memberships": the property absent
entirely (Backdrop kinds only), the inherited sentinel `0xFFFF` in the
length word, and an explicit zero-length payload. A reader that demands the
full-width list misreads the empty forms as failures.

### 9.8 Generated editor icons

The `icnI` handle on each object record names a first-`AGMI`-bank record
that MMF **generates from the object's own art** — the same scheme the
1996 products use (see the TGF/CnC spec):

- Icon records are a 28-byte head (`u32 handle, u32 scratch, u16 0,
  u32 rleLength, u16 w, u16 h`, mode bytes `03 01`, 8 zero bytes) plus
  1-byte-per-pixel editor RLE, rows padded to even length. Icon pixels are
  always indices into the Win32 halftone palette.
- Source: an Active thumbnails the first frame of its first animation
  direction; a Backdrop its own image; a Quick Backdrop's icon is a
  *render* of the object (shape, border, fill), not a scaled copy.
- Size: art with `max(w, h) ≤ 30` keeps its dimensions; larger art scales
  its longest side to 30 with the other floored proportionally.
- Sampling is per-axis last-pixel-of-cell (`src = ((i+1)·S − 1) / d`);
  colours quantise to the nearest halftone entry (indices 1–255) by squared
  RGB distance, transparency to index 0.
- A stored icon can be **stale**: the editor regenerates only on edits it
  sees, so authored games carry icons their current art no longer explains.

### 9.9 The `icnD` trailer

After the application's `!DNE` allocator record the file ends with

```text
"icnD", u32 0, u32 1, u32 length, char path[length], NUL
```

— the absolute path the project was saved to, in the machine's ANSI
codepage (`length` excludes the NUL). It is machine metadata, and worth
knowing about for privacy reasons: every `.cca` carries its author's
directory layout. Do not confuse it with paths that are content (an
external Sub-Application's `.ccn` child path, file-action parameters).

---

## 10. What compilation loses

The compiler discards editor-only data. Not recoverable from a standalone:

- comment rows and unused (unplaced) objects;
- **Backdrop and Quick Backdrop names** — the runtime omits their name chunks;
- global-value and alterable-value **names** (numeric values survive; alterable
  initial values survive only from build 94 on);
- custom animation names not referenced by an event;
- behaviour names and, in most cases, which object owned a behaviour sheet;
- transition display names (recoverable from the transition module's own
  resources);
- extension library display titles (re-read from the installed `.cox` on
  load);
- whether polarity-ambiguous window options (§2.1) were set or complemented;
- editor-only state: selection flags, allocator history, uninitialised heap
  bytes the editor leaks into name buffers and padding.

---

## 11. Identifying the producing build

Three independent signals:

1. **The `PAME` version bytes** (§1): product byte 0 = 1.0/1.2, 1 = 1.5,
   2 = Fusion 2.x; major byte 3 = MMF generation.
2. **The PE version resource** of a standalone (`VS_FIXEDFILEINFO`, signature
   `0xFEEF04BD`): the runtime family stamps `2.0.0.87`, `2.1.0.91`,
   `2.2.0.98`, where the last field is the build. Unreliable on its own —
   some games overwrite it with their own version.
3. **The `.text` section hash** of the stub, which is identical for every
   standalone of a given build regardless of the application appended.

---


This is an unofficial interoperability specification. It is not affiliated
with or endorsed by Clickteam. Clickteam, Multimedia Fusion, The Games
Factory, Click & Create, and other product or extension names are used only
to identify compatible formats. All trademarks belong to their respective
owners.