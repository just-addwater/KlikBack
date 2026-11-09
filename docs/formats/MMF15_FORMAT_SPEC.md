# Multimedia Fusion 1.5 — File Format Specification
justaddwater 
https://github.com/just-addwater/KlikBack

A reference for the binary formats written by Clickteam's **Multimedia Fusion
1.5** (runtime builds 105–119, 2001–2005). MMF 1.5 is an incremental revision
of the MMF 1.0 format: the container, compression, chunk framing, compiled
events, media banks and transitions are carried over unchanged, so this
document is a companion to MMF1_FORMAT_SPEC.md, it
describes what 1.5 changed and added, and restates shared structure only
where the two versions must be told apart. 

All integers are little-endian; `u8`/`u16`/`u32` unsigned, `i8`/`i16`/`i32` signed;
strings are NUL-terminated ANSI unless noted.

---

## 1. Version identification

Three independent signals separate MMF 1.5 output from 1.0 and from
Fusion 2.x:

1. **The `PAME` product byte.** The `u16` after the `PAME` signature is
   `0x0300` for MMF 1.0/1.2 and **`0x0301`** for MMF 1.5 (read as bytes:
   product 1, major 3). Fusion 2.x writes product 2 and adds `PAMU` for its
   Unicode runtime. This is the authoritative family test — PE version
   resources can be overwritten by the game's author.
2. **The PE version resource** of a standalone: the 1.5 runtime stamps
   `2.5.<build>.0` *or* `2.5.0.<build>` — both spellings occur in real
   builds.
3. **The `ER>>` event-header constants** (§6.1), which discriminate not just
   1.0 from 1.5 but build ranges inside the 1.5 line.

A `.ccn` is a bare package (`PAME` at offset 0) in both versions, and an
external Sub-Application child ships as one.

---

## 2. Unchanged from MMF 1.0

Proven unchanged by cross-version comparison (the same authored projects
compiled by both versions), not assumed:

- Chunk framing (`u16 id, u16 flags, u32 size`) and the Clickteam
  compression codec (block types 5/6/7, nonstandard code-length order).
- The 10-byte decompressed frame header (`0x3334`), including flag bit
  positions.
- **The entire compiled-event format** — the `ER>>`/`ERes`/`ERev` container,
  outer event records, condition/action records and parameters are
  byte-identical for the same authored events, apart from a handful of
  per-version header constants (§6.1). Condition/action object-type and
  opcode fields are still signed *bytes*; the widening to 16 bits happens at
  Fusion 2, not here.
- The four media banks (`0x6666`–`0x6669`), their common record layout, and
  the `0x5555`–`0x5558` handle-indexed offset tables. Whether an image is
  stored raw or RLE-compressed is a per-image compiler choice in both
  versions, not a version difference.
- Frame and object transitions, including the record layout and internal-id
  naming scheme.
- Frame passwords: flag `0x0040` in the frame header, plaintext chunk
  `0x3336` (which may sit *after* a `0x7F7F` terminator inside the frame
  container — resume walking past terminators).
- Frame item ids and the `0x222B` resolution table.
- The extension EDITDATA principle: private data survives compilation
  verbatim, prefixed by the SDK `extHeader`.

One addition to the codec's known surface: a **block type 4** exists in the
wild (one record in one known game). Its encoding is undecoded; a robust
reader should treat it as an explicit per-record failure, not a stream
desynchronisation.

---

## 3. Runtime chunk changes

| Chunk | MMF 1.0 | MMF 1.5 | Meaning |
|---:|---|---|---|
| `0x2228` | present | **removed** | 1.0 extension module table |
| `0x2232` | present | **removed** | 1.0 global values chunk |
| `0x2233` | present | **removed** | 1.0 raw 32×32×16 window icon |
| `0x2234` | — | **new** | Extension module list (§4) |
| `0x2235` | — | **new** | 16×16×256 window icon as a plain DIB (§5) |
| `0x2237` | — | **new, builds 115+** | Serial number, `u32` |

`0x222E` (source `.cca` path) and `0x222F` (target `.exe` path) exist in
both versions. Together with `0x2237` they are build-machine metadata:
exclude them from structural comparisons, and treat the serial as
install-identifying data that should never be copied into new output. The
serial never round-trips through the editor — no `.cca` carries it.

---

## 4. Extension module list (`0x2234`)

```text
u16 moduleCount
u16 slotHighWater      maximum stored slot + 1; 0 for an empty table
per module:
    u16     type       the object type this module's objects use
    u16     slot       not necessarily dense
    u32     0x59082516 signature, constant
    byte[8] patch/install metadata — varies by build, keep opaque
    char[]  filename   NUL-terminated, e.g. "kcflx.cox"
    char[]  subtype    NUL-terminated; empty except for ActiveX (below)
```

**The runtime object type is stored explicitly and is *not* derivable from
position or slot.** This breaks MMF 1.0's `32 + slot` rule: real 1.5 files
exist where the module at index 0 has type 34 and the module at index 1 has
type 27. Always read the type from this chunk.

The trailing `subtype` string is empty for every ordinary extension — its
lone terminator is easy to misread as a pad byte. For `KcActiveX.cox`
entries it holds the CLSID of the hosted OLE control (e.g. Shockwave Flash);
the same CLSID also appears inside the hosting object's own EDITDATA.

A module-free application writes a four-byte all-zero payload. Deleting an
extension in the editor frees its slot without renumbering, so slots may
skip values and `slotHighWater` must be carried through, not recomputed.

Embedded extension binaries still travel in a `0x222C` stream before the
package, as in 1.0. A `.cox`'s display title lives in its string resource 2;
runtime-embedded copies usually retain it.

Two further extension facts worth an implementer's attention:

- **EDITDATA is a schema owned by the extension build that wrote it.** The
  same extension can use different EDITDATA sizes across builds, and later
  editors accept older schemas — so a tool should preserve EDITDATA
  byte-for-byte as an opaque blob, never translate it to a newer layout.
  The leading SDK `extHeader` (`i16 extSize, extMaxSize, extOldFlags,
  extVersion`) makes each blob self-describing. An extension definition can
  also carry a movement block, bounded by the EDITDATA offset.
- **Editor vs runtime builds of a `.cox` are told apart by `RT_MENU`
  resources**, not by title or exports: the editor fills its
  condition/action/expression pick lists from three menu resources, so a
  module with none is a runtime-only build (the converse is weaker — many
  single-binary modules serve both roles). Every `.cox` exports the full
  SDK surface either way. RT_MENU resources indicate that a module contains editor ACE-menu data.
Their absence means the editor cannot obtain those menus from that binary,
but does not by itself prove that the module is unloadable or exclusively a
runtime build.

---

## 5. Application icons

MMF 1.5 raised the icon set from two PE resources to four:

| `RT_ICON` id | Icon |
|---:|---|
| 1 | 32×32×16 |
| 2 | 16×16×16 |
| 3 | 32×32×256 — new in 1.5 |
| 4 | 16×16×256 — new in 1.5 |

The overlay's own copy for the application window changed accordingly:
`0x2233` (raw 16-colour bitmap) is gone, and `0x2235` carries the 16×16×256
icon as a DIB that is byte-identical to PE resource 4 except for two header
fields that differ only by icon-resource convention (`biHeight` doubled,
`biSizeImage` including the AND mask in the resource).

In the editor file, the four icons map to images in the first `AGMI` bank,
and the application-terminal `icnQ` list assigns bank handles to icon slots
in the fixed order resource 3, 4, 1, 2. Physical bank order is edit history,
not slot identity. The `AppI` property is a single "icon was customised"
boolean; it does not record which variant changed.

---

## 6. Events

### 6.1 `ER>>` header constants by build

The `ER>>` header is 46 bytes plus a variable tail: the `u16` at `+0x2C` is
a tail count (usually 0) and `ERes` begins at `0x2E + 4 × count`. The `u16`
at `+0x04` is the frame's "number of objects at runtime" (default 300), not
a version stamp. The constants at fixed offsets discriminate versions and
builds with no known exception:

| Producer | `+0x0A +0x0C +0x0E +0x10 +0x12 +0x14 +0x16 +0x2A` |
|---|---|
| MMF 1.0, builds 87–99 | `7, 10, 23, 6, 5, 6, 15, 51` |
| MMF 1.5, builds 105–112 | `7, 10, 23, 6, 7, 6, 17, 52` |
| MMF 1.5, builds 115–119 | `7, 11, 23, 6, 7, 6, 18, 52` |

### 6.2 New actions, conditions and expressions

All flow-control additions live in the **special** family (`0xFF`), which
1.0 already used. Event group markers are unchanged: special condition −10
opens a group, −11 closes one.

**Fast loops** (new feature):

| Kind | Number | Meaning |
|---|---:|---|
| action | 14 | Start Loop (name, count) |
| action | 15 | Stop Loop (name) |
| action | 16 | Set Loop Index (name, index) |
| condition | −16 | On Loop (name) |
| expression | special 46 | `LoopIndex(name)` |

Special action 17 and condition −15 are also new in 1.5 (exact semantics
unconfirmed). Special conditions −17 (menu option checked) and the
menu-option actions 8–13 relate to the menu-control ACEs; a new
pick-all-objects-in-zone condition (create family `0xFB`, number −18)
carries a type-19 zone-rectangle parameter (`u16` left, top, right,
bottom).

**Menu-control ACEs** (special family, type-48 menu-id parameter unless
noted): actions 8/9 enable/disable menu option, 10/11 check/uncheck menu
option, 12/13 show/hide menu bar (no parameter); condition −14 menu option
selected, condition −17 menu option checked.

**New system expressions** form one nearly contiguous block, special
expressions 28–47:

```text
28 Int(    29 Abs(    30 Ceil(   31 Floor(  32 ACos(   33 ASin(
34 unknown   35 NOT(    36 NDropped  37 unknown   38 CommandLine$
39 CommandItem$(  40 Min(  41 Max(  42 GetRGB(  43 GetRed(
44 GetGreen(  45 GetBlue(  46 LoopIndex(  47 unknown 
```

plus `Appname$` (9) and `Exp(` (18) extending existing blocks, storyboard
expression 9 (collision-mask value) and counter expressions 49/50.
Expression numbers 0–27 are inherited from 1.0 (0 = integer literal,
3 = string literal, 4 = number-to-string wrapper, 253 = argument separator,
254 = argument-list close). Extension ACE numbering still starts at 48.

### 6.3 New object-family ACEs

All proven by single-event isolation files. Object-specific ACE numbering
starts at 48 in both versions, so these extend existing tables.

**Counter** (type 7): actions 51 set minimum / 52 set maximum; expressions
49 get minimum / 50 get maximum (a bare 4-byte object reference, no
argument list).

**Sound** (family `0xFE`): action 6, stop a *specific* sample — the one 1.5
sound addition (stop-any-sample 1 and stop-any-music 3 are inherited).
Its type-35 parameter shares parameter type 6's layout: `s16 handle`,
`u16 flags` (bit 0 = uninterruptible), then the 64-byte sample name.

**Storyboard** (family `0xFD`): actions 12 clear screen (type-24 colour),
13 clear zone (type-19 zone + colour), 14 full-screen mode, 15 windowed
mode; conditions −5 is-obstacle-at(x, y) and −6 is-ladder-at(x, y);
expression 9 = collision-mask value at (x, y).

**Active** (type 2): actions 39 set semi-transparency, 40 force animation
frame, 41 restore animation frame (parameterless), 42 set acceleration,
43 set deceleration, 51 add backdrop, 52 replace colour (two type-24
colours). Action 48 (paste into background) is inherited from 1.0.

Two shared parameter types pinned by these specimens:

- **Type 19** — zone rectangle: four `u16`, left, top, right, bottom.
- **Type 43** — collision-mode enum: 0 not an obstacle, 1 obstacle,
  2 platform, 3 ladder, 4 no effect on collisions. The enum predates 1.5
  (action 48 uses it), so it applies to 1.0 as well.

### 6.4 Expression token header

Shared with 1.0, stated here in full:

```text
i8  object_type      -1 special, -7 player, positive = object family
i8  expression_number
u16 token_size       includes this 4-byte header
u16 object_id        present for object families and player only
i16 object_info_list same condition
... payload
```

Player tokens carry a *player* reference, not an object reference — do not
remap them through an object table. Active expression 16 (alterable value)
carries one extra `u16` index.

---

## 7. Application and frame options

### 7.1 Run options (`RunO`)

The Run Options dialog grew from four checkboxes (1.0) to nine (build 119).
Bits map to the application header flags word (`0x2223 +0x00`):

| `RunO` | Checkbox | Runtime bit |
|---:|---|---|
| `0x01` | Multi-samples | 10 |
| `0x02` | Machine-independent speed | 3 |
| `0x04` | Play sounds over frames | 16 |
| `0x08` | Do not stop samples on focus loss | 19 |
| `0x10` | Do not stop screensaver | 24 — new in 1.5 |
| `0x20` | Use DirectX | **none — compile-time loss** |
| `0x40` | VRAM only | **none — compile-time loss** |
| `0x80` | Enable visual (XP) themes | 27 — added after build 105 |
| `0x100` | V-sync | **none — compile-time loss** |

DirectX, VRAM-only and V-sync leave no trace in any chunk of the compiled
output.

### 7.2 Window options (`WinO`) and size (`WinS`)

MMF 1.0's `WinO` mapping applies through `0x800`; build 119 adds
`0x1000` = disable close (runtime bit 25) and `0x2000` = hidden at start
(bit 26). The heading/menu-bar/menu-on-boot ambiguity (three checkboxes
compiled into two independent bits) persists. The window size is
`u16 width, u16 height` at application header `+0x08`; other application
content (author `0x2225`, menu `0x2226`, help path `0x2230`, border colour
at header `+0x4C`, starting score/lives at `+0x0C`/`+0x10`) is 1.0's mapping
unchanged.

### 7.3 Frame options (`PfOp` ↔ frame flags)

| `PfOp` bit | Runtime flag | Checkbox |
|---:|---:|---|
| `0x01` | `0x0002` | Grab desktop at start |
| `0x02` | `0x0004` | Keep display from previous frame |
| `0x04` | `0x0020` | Handle background collisions out of window |
| `0x08` | `0x0001` | Display frame title in caption |
| `0x10` | `0x0100` | Resize display to fit |
| `0x20` | `0x0400` | **Force Load On Call — new in 1.5** |

Flag `0x0040` remains the frame-password flag and is not a run option.

---

## 8. Objects

### 8.1 Alterable values A–Z

1.5 raised alterable values from three (A–C) to twenty-six (A–Z). **The
structures are unchanged from 1.0; only the limits widened.**

Runtime (definition `+0x26` → `u16 count`, `i32 values[count]`): the table
is **dense** — `count` is the highest authored index + 1, untouched slots
are 0. Editor (`AltV` property, 44-byte records with `u16 index` at `+4`, a
34-byte name buffer at `+6` and the `i32` value at `+40`): the list is
**sparse and ordered by index**, holding only authored values. Names remain
editor-only in both versions.

### 8.2 Sub-Application

The runtime type-specific block gained two fields inside 1.0's layout:

```text
+0x00 u32 leading_value     0 in all known samples
+0x04 u16 width
+0x06 u16 height
+0x08 u16 version           0 in every measured specimen
+0x0A u16 start_frame       zero-based frame ORDINAL (not an item id)
+0x0C u32 options
+0x10 char child_path[]     NUL-terminated; empty in internal mode
```

Known option bits: `0x0001` share global values, `0x0002` share lives,
`0x0004` share scores, `0x0008` share window attributes (the default),
`0x0020` popup, `0x0100` border, `0x4000` **internal source** ("frame from
this application" — implies an empty child path; the full window-style group
occupies the remaining low bits), `0x8000` hide on close, `0x10000`
custom size, with a stretch bit alongside. Internal mode appends one extra
`u32` start-frame field to the *editor* record tail; external mode ends at
the options word.

### 8.3 Editor schema note

Build 115 added an `SFFg` property to most object classes' schemas. No
non-default value has ever been observed; it is a schema default, not a
recoverable runtime field.

---

## 9. The editor format (`.cca`)

### 9.1 Container header

```text
+0x00  char[4]  "CnC2"
+0x04  u8       product letter: 'T' = MMF 1.0/1.2, 'U' = MMF 1.5
+0x05  u8       version major (1)
+0x06  u8       version minor: 5   (see caveats below)
+0x08  u16      1
+0x0A  u32      build number      (builds ≤ 108)
+0x0C  u32      build number      (builds ≥ 110; the unused slot is zero)
+0x0E           first editor bank tag (ATNF, APMS, ASUM, AGMI, …)
```

Two fields moved or changed meaning inside the 1.5 line:

- **The build slot moved** from `+0x0A` to `+0x0C` between builds 108
  and 110. Read whichever is nonzero; no known file sets both or neither.
- **`+0x06` stops being a version at build 113.** Through build 112 the
  `u32` at `+0x06` is `u16 minor, u16 1`; from 113 it carries an opaque,
  install-scoped stamp (plausibly a registration serial). Test
  `stamp >> 16 == 1` before interpreting the minor; from 113 on, copy the
  field through unchanged and never propagate it into new output.

### 9.2 Class blocks and property records

MMF 1.5 slimmed the record framing:

```text
Class block:      char[4] "v1.5"     (1.0: 8-byte "Ver 1.1\0")
                  u32 propertyCount  (1.0 adds a per-save stamp u32 here)
                  u32 nameLength, class name
                  ... property records

Property record:  u16 tagLength, char tag[]   ← a LENGTH, not a separator
                  u32 unknown (usually 1)
                  u32 entryCount, entries

Property entry:   u8 type, u8 index, u8 a, u8 b
                  u32 size            0xFFFFFFFF = inherited, nothing follows
                  payload
```

Two traps:

- **The `04 00` before each tag is a tag length.** 1.0 uses only
  four-character tags, so it reads like a constant separator there; 1.5 has
  genuine three-character tags (`Tit`, `Evt`) and a reader assuming `04 00`
  desynchronises immediately.
- The property entry was reshaped: 1.0's `u8 type, u8 index, u16 size,
  u32 a, u32 b` became `u8 type, u8 index, u8 a, u8 b, u32 size`, and the
  inherited sentinel widened from `0xFFFF` to `0xFFFFFFFF`. An inherited
  entry is 8 bytes in 1.5, 16 in 1.0.

Entry payloads by type: `0x03` = `size` bytes holding a NUL-terminated
string (the buffer may carry uninitialised heap after the NUL — read to the
first NUL, don't trust `size` as string length); `0x04` = a zero-size
"field is set" marker, normally paired with an adjacent `0x03`; every other
type carries a `u32` word (the value, for scalars) optionally followed by
`size` bytes (`0x0A` sized blobs: palettes, key tables, `AltV`, …).

### 9.3 Frame and object structure

- The `PROP` property-index block that follows each class block (see the
  1.0 spec, §9.2) is unchanged, except that in 1.5 it starts a fixed 4 bytes
  past the class block where 1.0 leaks scratch bytes into the gap.
- Each object record in a frame's object list begins
  `char kind[4]` (`"Actv"`, `"BkDr"`, `"CCAx"`, `"Xtnd"`, …), `u32 0`, then a
  counted name that is empty in virtually every record (a whole-frame
  Sub-Application source stores `FRAME-BKGND-ITEM` there) — then the `v1.5`
  class block.
- The frame palette (`Pltt`) and the runtime palette (`0x3337`) are both a
  4-byte header plus 1024 bytes of entries. **The entries are identical; the
  headers are two different constants** (`00 01 00 00` editor,
  `00 03 00 01` runtime). Writing the runtime header into an editor file
  makes MMF reject it silently.
- Behaviour display names live in the object's `PROP` index block, exactly
  as in 1.0, and do not survive compilation. An object can have at most
  **one** behaviour — the editor does not allow a second. Behaviour *group*
  names do survive (in the group-open row's type-38 parameter), so a group
  name is recoverable from an `.exe` while a behaviour name is not.
- Two `AGMI` image banks, in order: bank 1 is editor-only artwork (object
  icons, frame thumbnails, application icons), bank 2 is the runtime image
  bank. Same arrangement as 1.0.

### 9.4 The frame body

After a frame's object list, measured on 1.5 (the individual structures are
1.0's; the layout is the part first mapped here):

```text
per instance:  "Inst" i32 x, i32 y, i32 instanceHandle,
               i32 editorA, i32 editorB, i32 objectId, i32 -1
               (String and Formatted Text instances use tag "IPIn")
"evpg" u16 0x0300, u16 (normally 1)
["Evts" u32 length, editor event records]      omitted when no events
["Rems" u32 20 "class CEvtRemarkList" u32 count
    per remark: "EvRk" u32 index, u32 length, text]
["EvOb" u32 13 "class COIList" u32 count, EvOi entries]
"EvEd" u16 count, i16 columnType[count], u16 evOiIndex[count], u16 0[count]
"EvTe" u16 count, same three arrays
"EvCs" u32 16, 16 bytes                        frame event settings
"!DNE" u32 2, u32 nextHandle, u32 3 "nil", u32 3 "nil", u32 0
["icnQ" u32 count, per entry "Imag" u32 handle]
```

Traps mapped the hard way, valid for both versions:

- `Rems` (the author's event comments — a pure compile loss) sits *between*
  `Evts` and `EvOb`; a reader that assumes `EvOb` follows `Evts`
  desynchronises on any commented project. The full comment-row anatomy
  (the special-condition-−9 row, its `+0x5C` binding to `EvRk`, and the two
  `COLORREF`s at `+0x52`/`+0x56`) is in the 1.0 spec §9.6 and holds
  measured-per-format on both sides; comment *positions* survive
  compilation, text does not.
- `EvEd`'s leading `u16` is a **count**, not a length: three parallel
  arrays of that count follow (6 × count bytes). Column types −1 to −7 are
  the seven system columns; the rest are object runtime types. `EvEd` is
  editor session state (which columns were displayed), not content.
- Ordinary instance placeholders store editor fields `(8, 1, −1)` for a
  Create target and `(8, 2, parentItemId)` for a Shoot target; the parent
  is a frame-local item id on the editor side but an application-global
  object id in the compiled placement link.
- `!DNE`'s second word is a handle allocator, not a count.

---

## 10. Dating a file within the 1.5 line

| Signal | Boundary |
|---|---|
| `.cca` build slot at `+0x0A` vs `+0x0C` | moved between 108 and 110 |
| `.cca` `+0x06` classic version stamp vs opaque | changed between 112 and 113 |
| `ER>>` constants `+0x0C`/`+0x16` step 10→11 / 17→18 | between 112 and 115 |
| Serial chunk `0x2237` appears | between 112 and 115 |
| PE version resource | `2.5.<build>.0` or `2.5.0.<build>` |

These boundaries are independent — do not collapse them into one "schema
version".

---

## 11. What compilation loses (beyond the 1.0 list)

Everything in the 1.0 losses list still applies (Backdrop/Quick Backdrop
names, global-value and alterable-value names, comment rows, behaviour
ownership, …). 1.5 adds:

- the **Use DirectX**, **VRAM only** and **V-sync** run options — no chunk
  records them;
- the serial number's provenance: `0x2237` is written at compile time from
  the install's licence data and cannot be regenerated from a project;
- behaviour display names (recoverable from a `.cca`, never from an
  `.exe`), as in 1.0.


---

This is an unofficial interoperability specification. It is not affiliated
with or endorsed by Clickteam. Clickteam, Multimedia Fusion, The Games
Factory, Click & Create, and other product or extension names are used only
to identify compatible formats. All trademarks belong to their respective
owners.