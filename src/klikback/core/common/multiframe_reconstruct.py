# GENERATED — do not edit by hand. This file is produced by KlikBack's
# sync tooling; changes belong in the source it is generated from.
#
# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""Assemble a whole multi-frame application from its recovered frames.

A game is more than a list of frames: the application itself has properties,
a global event sheet and a frame order, and each frame has a title and a
place in that order. This puts those together once the frames themselves are
rebuilt.
"""

from __future__ import annotations
import re
import struct
from pathlib import Path
from klikback.core.common.animation_reconstruct import runtime_image_to_editor
from klikback.core.common.compare import find_chunk, read_chunks
from klikback.core.common.compression_probe import load_exe_frame
from klikback.core.common.event_object_registry import collect_event_references, create_placeholders_for_unplaced, frame_registry, parse_compiled_placements_with_links
from klikback.core.common.blind_core_reconstruct import EVENT_OBJECT_TYPE_STRINGS, EXTENSION_OBJECT_TYPE_BASE
from klikback.core.common.global_event_reconstruct import classify_global_program
from klikback.core.common.exe_to_cca import decompress_chunk, extract_event_programs
from klikback.core.common.object_analysis import parse_image_streams, split_object_chunks
from klikback.core.common.object_reconstruct import nested_payload
from klikback.core.common.reconstruct_event_test import compiled_event_programs_to_editor_events, group_close_template, unclosed_groups

FRAME_RECORD = b"Fram" + b"\x00" * 8 + b"Ver 1.1\x00"

def all_exe_frames(outer_chunks) -> list[list]:
    """Every frame in a compiled game."""
    return [
        read_chunks(chunk.payload, 0, len(chunk.payload))
        for chunk in outer_chunks
        if chunk.chunk_id == 0x3333
    ]

def runtime_frame(frame_chunks: list, unreadable_events: list | None = None) -> dict:
    """One frame as the compiled game stored it.

    Size, background colour, flags, name, palette, placements, events, password
    and transitions, read out of the chunks a compiled frame is made of. Several
    of those chunks are genuinely optional — a frame saved with no title may carry
    no title chunk at all, and a frame with nothing placed in it carries no
    placements — so their absence is a shape rather than a fault.

    One chunk carries two unrelated things: the compiled event programs *and* the
    frame's "how many objects at runtime" setting. That coupling matters because
    it means one unreadable chunk costs both.

    Which brings up the only real choice here. A frame whose event chunk will not
    decompress can either stop the whole rebuild or be decoded with no events at
    all, and the default is to stop. A frame that silently comes back without its
    events is a far worse outcome than a refusal: the project opens, looks
    complete, and does nothing. Tolerating it has to be asked for, and the reason
    is recorded when it is. Even then nothing is invented — the object count falls
    back to the value that means "inherit the default" rather than to a number.
    """
    header = decompress_chunk(find_chunk(frame_chunks, 0x3334))

    try:
        events = decompress_chunk(find_chunk(frame_chunks, 0x333D))
        event_block_or_none = (
            events,
            struct.unpack_from("<H", events, 4)[0],
            extract_event_programs(events),
        )
    except Exception as error:
        if unreadable_events is None:
            raise
        unreadable_events.append(str(error))

        event_block_or_none = (None, 0, [])

    name_chunks = [chunk for chunk in frame_chunks if chunk.chunk_id == 0x3335]
    name = decompress_chunk(name_chunks[0]) if name_chunks else b""
    placement_chunks = [chunk for chunk in frame_chunks if chunk.chunk_id == 0x3338]
    if len(placement_chunks) > 1:
        raise ValueError("runtime frame has multiple placement chunks")
    placements_with_links = (
        parse_compiled_placements_with_links(
            decompress_chunk(placement_chunks[0])
        )
        if placement_chunks
        else []
    )

    return {
        "width": struct.unpack_from("<H", header, 0)[0],
        "height": struct.unpack_from("<H", header, 2)[0],
        "bg_color": struct.unpack_from("<I", header, 4)[0],
        "frame_flags": struct.unpack_from("<H", header, 8)[0],
        "name": name,
        "placements": [
            (instance_id, x, y, object_id)
            for instance_id, x, y, object_id, _link in placements_with_links
        ],
        "placements_with_links": placements_with_links,
        "palette": decompress_chunk(find_chunk(frame_chunks, 0x3337))[4:],

        "password": next(
            (
                decompress_chunk(chunk)
                for chunk in frame_chunks
                if chunk.chunk_id == 0x3336
            ),
            None,
        ),

        "runtime_object_count": event_block_or_none[1],
        "compiled_event_programs": event_block_or_none[2],

        "transitions": {
            tag: decompress_chunk(matches[0])
            for tag, chunk_id in ((b"FadI", 0x333B), (b"FadO", 0x333C))
            for matches in [
                [chunk for chunk in frame_chunks if chunk.chunk_id == chunk_id]
            ]
            if matches
        },
    }

def recover_global_events(
    frames: list[dict],
    objects_by_id: dict[int, dict],
    notes: list,
) -> dict | None:
    """Lift the global sheet back out of the frames the compiler copied it into.

    A global event is written once and runs in every frame. Compiling does not
    keep it anywhere separate — it copies the whole sheet into every frame's own
    events — so reading each frame at face value produces a project carrying the
    same sheet as many times as the game has frames, which is both wrong and
    tedious to look at.

    This finds the one program every frame has in common, lifts it out, and takes
    it back out of each frame. The list of objects it refers to is rebuilt in its
    own numbering, because the sheet is not a frame and does not share a frame's
    ids.

    It refuses rather than guessing in two cases, and says which in both: when no
    single program is common to every frame, and when the sheet selects through a
    qualifier group, whose registry entry is a different shape from any the
    recovery has been proven against. An unresolved sheet stays flattened into
    the frames — wrong, but visible and reported. A guessed one would be wrong and
    invisible.
    """
    programs = [
        [p for p in frame["compiled_event_programs"] if p] for frame in frames
    ]
    for frame, kept in zip(frames, programs):
        frame["compiled_event_programs"] = kept
    indexes = classify_global_program(programs)
    if indexes is None:
        if any(len(kept) > 1 for kept in programs):
            notes.append("unresolved: no single program is common to every frame")
        return None
    compiled = programs[0][indexes[0]]
    object_ids, qualifier_words = collect_event_references(
        compiled, objects_by_id, type_repairs=[]
    )
    if qualifier_words:

        notes.append("unresolved: sheet references a qualifier")
        return None
    registry = []
    for event_id, object_id in enumerate(sorted(object_ids)):
        obj = objects_by_id[object_id]
        object_type = obj["object_type"]
        if object_type in EVENT_OBJECT_TYPE_STRINGS:
            type_name = EVENT_OBJECT_TYPE_STRINGS[object_type]
        elif object_type >= EXTENSION_OBJECT_TYPE_BASE:

            type_name = obj["definition"][0x2C:0x30]
        else:
            notes.append(f"unresolved: sheet references object type {object_type}")
            return None
        registry.append(
            {
                "event_id": event_id,
                "object_id": object_id,
                "object_type": object_type,
                "name": obj["name"].split(b"\x00")[0],
                "type_name": type_name,
            }
        )
    for frame, index in zip(frames, indexes):
        frame["compiled_event_programs"].pop(index)
    object_id_map = {entry["object_id"]: entry["event_id"] for entry in registry}
    return {
        "events": compiled_event_programs_to_editor_events(
            [compiled], object_id_map=object_id_map
        ),
        "registry": registry,
    }

def runtime_application(
    exe_path: Path,
    type_repairs: list | None = None,
    frame_target_map: dict[int, int] | None = None,
    global_events: list | None = None,
    unreadable_events: list | None = None,
    size_repairs: list | None = None,
    unplaced_placeholders: list | None = None,
    dangling_shoot_parents: list | None = None,
    label_flattened_seams: bool = False,
    recover_comments: bool = False,
    recovered_comments: list | None = None,
    group_close_repairs: list | None = None,
) -> tuple[list[dict], list[dict], list[tuple[int, bytes]]]:
    """Every frame's objects, placements and events, read out of the compiled game.

    The top of the 1.0 reading path, and the place the pieces meet. It loads the
    executable, reads each frame, reads the object bank once for the whole
    application, decodes the images, and then converts each frame's events into
    editor form under that frame's own numbering.

    Several recoveries and repairs happen here, and they share a deliberate shape:
    **passing a list turns on both the repair and its reporting together**, so a
    caller that cannot report a repair does not silently get one. A row this
    pipeline invents belongs on a repair line whether or not the placement is
    obvious.

    The ones worth knowing about:

    - **The global event sheet.** An event written once to run everywhere is
      compiled into *every* frame, so a reader taking each frame at face value
      duplicates it across all of them. It is lifted out once and removed from
      the frames it came from.
    - **Objects the events name but the runtime never placed.** These would reach
      the editor with no instance at all — a state the editor never writes and
      destroys on save — so each gets the same stand-in placement the editor's own
      files use. This one is unconditional, because the alternative is writing a
      file the editor quietly corrupts.
    - **Event groups the compiler left open**, closed with a close record taken
      from elsewhere in the same game rather than invented.
    - **Shoot placeholders naming a parent that is not there**, reported and *not*
      repaired: nothing left in the game says what the parent was.
    - **Comment rows**, restorable at the positions the surviving row numbers
      name, with substituted text. Off by default and reported as the loss it is.

    One numbering detail is load-bearing. Labels are numbered across the whole
    project rather than per frame, because otherwise nine recovered programs all
    show "1" in nine different frames and no two can be told apart in
    conversation.

    A game whose objects carry no graphics at all — only text and counters — has
    no image bank in the file. That is an empty bank, not a malformed one.
    """
    if recover_comments and not label_flattened_seams:
        raise ValueError(
            "recover_comments needs label_flattened_seams: both write comment "
            "rows into one Rems block and one id space"
        )
    outer, _first_frame = load_exe_frame(exe_path)
    frames = []
    for index, chunks in enumerate(all_exe_frames(outer)):
        per_frame: list | None = [] if unreadable_events is not None else None
        frames.append(runtime_frame(chunks, unreadable_events=per_frame))
        for reason in per_frame or []:
            unreadable_events.append((index, reason))

    objects = []
    object_chunks = split_object_chunks(
        decompress_chunk(find_chunk(outer, 0x2229))
    )
    for object_id, chunks in enumerate(object_chunks):
        header = nested_payload(chunks, 0x4444)
        object_type = struct.unpack_from("<H", header, 2)[0]
        definition = nested_payload(chunks, 0x4446)
        name_chunks = [chunk for chunk in chunks if chunk.chunk_id == 0x4445]
        name = (
            decompress_chunk(name_chunks[0])
            if name_chunks
            else b"Backdrop\x00"
        )
        image_id = struct.unpack_from("<H", definition, len(definition) - 2)[0]
        objects.append(
            {
                "object_id": object_id,
                "object_type": object_type,
                "name": name,
                "definition": definition,
                "header": header,
                "image_id": image_id,

                "memory_flags": struct.unpack_from("<H", header, 4)[0],
            }
        )

    image_chunks = [chunk for chunk in outer if chunk.chunk_id == 0x6666]
    images = [
        (image_id, runtime_image_to_editor(decoded))
        for chunk in image_chunks
        for image_id, decoded, _stored_size in parse_image_streams(
            decompress_chunk(chunk)
        )
    ]
    objects_by_id = {obj["object_id"]: obj for obj in objects}

    if global_events is not None:
        notes: list = []
        sheet = recover_global_events(frames, objects_by_id, notes)
        global_events.append({"sheet": sheet, "notes": notes})
    labelled_so_far = 0
    comments_so_far = 0

    close_template = group_close_template(
        [
            program
            for frame in frames
            for program in frame["compiled_event_programs"]
        ]
    )
    for index, frame in enumerate(frames):
        compiled_programs = frame.pop("compiled_event_programs")
        compiled_events = [
            event
            for program in compiled_programs
            for event in program
        ]

        registry = frame_registry(
            frame["placements_with_links"],
            compiled_events,
            objects_by_id,
            type_repairs,
        )
        frame["registry"] = registry

        for parent in registry["dangling_shoot_parents"]:
            if dangling_shoot_parents is None:
                continue
            name = objects_by_id[parent]["name"].split(b"\x00", 1)[0]
            dangling_shoot_parents.append(
                {
                    "frame": index,
                    "object_id": parent,
                    "name": name.decode("latin-1", "replace"),
                }
            )

        frame["placements_with_links"] = frame["placements_with_links"] + (
            create_placeholders_for_unplaced(
                registry,
                frame["placements_with_links"],
                index,
                objects_by_id,
                unplaced_placeholders,
            )
        )
        frame["placements"] = [
            (instance_id, x, y, object_id)
            for instance_id, x, y, object_id, _link in frame["placements_with_links"]
        ]

        frame["remarks"] = [] if label_flattened_seams else None

        if group_close_repairs is not None:
            orphans = sum(
                len(unclosed_groups(program))
                for program in compiled_programs
                if program
            )
            if orphans:
                group_close_repairs.append((index, orphans))
        frame["events"] = compiled_event_programs_to_editor_events(
            compiled_programs,
            object_id_map=registry["object_id_map"],
            frame_target_map=frame_target_map,
            remarks=frame["remarks"],
            first_remark_index=labelled_so_far + 1,
            recover_comments=recover_comments,
            first_comment_index=comments_so_far + 1,
            close_template=close_template,

            object_types=(
                {
                    object_id: obj["object_type"]
                    for object_id, obj in objects_by_id.items()
                }
                if type_repairs is not None
                else None
            ),
            size_repairs=size_repairs,
        )

        if frame["remarks"] is not None:
            seams = max(sum(1 for program in compiled_programs if program) - 1, 0)
            total = len(frame["remarks"])
            if total < seams:
                raise ValueError(
                    f"frame {index}: {total} remark(s) for {seams} seam(s); "
                    "the remark split cannot be derived"
                )
            labelled_so_far += seams
            if recover_comments:
                restored = total - seams
                comments_so_far += restored
                if restored and recovered_comments is not None:
                    recovered_comments.append((index, restored))
    return frames, objects, images

def frame_records(cca: bytes) -> tuple[int, int, list[tuple[int, int]]]:
    """The records a rebuilt frame is made of."""
    list_pos = cca.index(b"FrmL")
    count = struct.unpack_from("<I", cca, list_pos + 4)[0]
    starts = [
        match.start()
        for match in re.finditer(re.escape(FRAME_RECORD), cca)
    ]
    if len(starts) != count:
        raise ValueError(f"FrmL says {count} frames but found {len(starts)} records")
    tail_pos = cca.index(b"icnD", starts[-1])
    records = []
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else tail_pos
        records.append((start, end))
    return list_pos, tail_pos, records

def replace_frame_title(frame: bytes, old_name: bytes, new_name: bytes) -> bytes:
    """Set a frame's title in the rebuilt project."""
    if not old_name.endswith(b"\x00") or not new_name.endswith(b"\x00"):
        raise ValueError("frame names must be NUL-terminated")
    name_pos = frame.index(old_name)
    data = bytearray(frame)
    struct.pack_into("<H", data, name_pos - 10, len(new_name))
    data[name_pos : name_pos + len(old_name)] = new_name
    return bytes(data)
