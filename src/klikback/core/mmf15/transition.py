# GENERATED — do not edit by hand. This file is produced by KlikBack's
# sync tooling; changes belong in the source it is generated from.
#
# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""The transitions a game plays between frames and between objects.

A transition is provided by a module and referred to by identity rather than by
name, so showing it correctly in the editor means resolving that identity back
to a module and a display name.
"""

from __future__ import annotations
import struct
from klikback.core.common.blind_core_reconstruct import TRANSITION_NAMES, parse_transition

def _by_identifier(pairs: dict[tuple[bytes, bytes], bytes]) -> dict[bytes, bytes]:
    owners: dict[bytes, set[bytes]] = {}
    for module, identifier in pairs:
        owners.setdefault(identifier, set()).add(module)
    return {
        identifier: name
        for (_module, identifier), name in pairs.items()
        if len(owners[identifier]) == 1
    }

MMF15_TRANSITION_NAMES = _by_identifier(TRANSITION_NAMES) | {
    b"MAH1ARO2": b"Ovine Rubber (loose)",
    b"SFTRDROP": b"Tile Drop",
    b"SFTRFOLD": b"Folder",
    b"SFTRPIXX": b"Pixelate (*beta*)",
    b"SS00SE00": b"Advanced Scrolling",
    b"SS00SE01": b"Square",
    b"SS00SE02": b"Turn 2",
    b"SS00SE03": b"Line",
    b"SS00SE04": b"ZigZag",
    b"SS00SE05": b"Open",
    b"SS00SE06": b"Push",
    b"SS00SE07": b"Stretch",
    b"SS00SE08": b"Turn",
    b"SS00SE09": b"Stretch 2",
    b"SS00SE10": b"Back",
    b"SS00SE11": b"Zoom",
    b"SS00SE12": b"Cell",
    b"SS00SE13": b"Trame",

    b"FAD1ROTA": b"Rotate",
    b"FAD1SLID": b"Slider",
    b"MAH1ARO1": b"Ovine Rubber (tight)",
}

MMF15_TRANSITION_NAMES_BY_MODULE = {
    (b"rubberovine.dll", b"MAH1ARO2"): b"Ovine Rubber (loose)",
    (b"rollovine.dll", b"MAH1ARO2"): b"Ovine Roll",
}

def transition_display_name(identifier: bytes, module: bytes) -> bytes | None:
    """The name the editor shows for a transition."""
    key = (module.rstrip(b"\x00").lower(), identifier)
    if key in MMF15_TRANSITION_NAMES_BY_MODULE:
        return MMF15_TRANSITION_NAMES_BY_MODULE[key]
    if any(ident == identifier for _module, ident in MMF15_TRANSITION_NAMES_BY_MODULE):

        return None
    return MMF15_TRANSITION_NAMES.get(identifier)

class TransitionProblem(Exception):
    """Raised when a transition resolves to no module this knows."""

def transition_modules(payload: bytes) -> list[bytes]:
    """The modules that provide transitions."""
    if len(payload) < 2:
        raise TransitionProblem("0x2231 is shorter than its u16 count")
    (count,) = struct.unpack_from("<H", payload)
    cursor = 2
    modules = []
    for _ in range(count):
        try:
            end = payload.index(b"\x00", cursor) + 1
        except ValueError as problem:
            raise TransitionProblem("0x2231 has an unterminated module name") from problem
        modules.append(payload[cursor:end])
        cursor = end
    if cursor != len(payload):
        raise TransitionProblem(
            f"0x2231 leaves {len(payload) - cursor} byte(s) after {count} modules"
        )
    return modules

def checked_runtime_transition(data: bytes, offset: int = 0) -> dict:
    """A transition read from the compiled game, resolved to a module this knows.
    """
    if offset < 0 or offset + 0x20 > len(data):
        raise TransitionProblem(f"transition offset {offset:#x} is out of range")
    identifier = data[offset : offset + 8]
    module_offset, parameter_offset, parameter_length = struct.unpack_from(
        "<III", data, offset + 0x14
    )
    module_start = offset + module_offset
    parameter_start = offset + parameter_offset
    parameter_end = parameter_start + parameter_length
    if module_start < offset + 0x20 or module_start >= len(data):
        raise TransitionProblem(
            f"transition {identifier!r} module offset {module_offset:#x} is invalid"
        )
    try:
        data.index(b"\x00", module_start)
    except ValueError as problem:
        raise TransitionProblem(
            f"transition {identifier!r} module name is unterminated"
        ) from problem
    if parameter_start < offset + 0x20 or parameter_end > len(data):
        raise TransitionProblem(
            f"transition {identifier!r} parameter span is out of range"
        )
    parsed = parse_transition(data, offset)
    parsed["identifier"] = identifier
    display = transition_display_name(identifier, parsed["module"])
    if display is None:
        module = parsed["module"].rstrip(b"\x00")
        raise TransitionProblem(
            f"transition {identifier!r} in module {module!r} has no verified "
            "display name"
        )
    parsed["name"] = display + b"\x00"
    return parsed

def transition_payload(transition: dict) -> bytes:
    """The transition's own settings."""

    def sub(flag: int, record_id: int, payload: bytes) -> bytes:
        return struct.pack("<HHI", flag, record_id, len(payload)) + payload

    parameters = transition["parameters"]
    value = (
        sub(0, 0x333, transition["header"])
        + sub(0, 0x334, transition["module"])
    )
    if parameters:
        return (
            value
            + sub(0, 0x335, transition["name"])
            + sub(0x8000, 0x336, parameters)
        )
    return value + sub(0x8000, 0x335, transition["name"])
