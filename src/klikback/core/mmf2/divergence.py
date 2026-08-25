# GENERATED — do not edit by hand. This file is produced by KlikBack's
# sync tooling; changes belong in the source it is generated from.
#
# KlikBack is free software: you may redistribute and/or modify it under
# the GNU General Public License, version 3 or later, as published by the
# Free Software Foundation. There is NO WARRANTY. See the LICENSE file.
"""Find every object an event line refers to.

An event line names objects in more places than is obvious.  There is the
object the line is about, which sits in the line's own header; there are
parameters that carry an object of their own, such as the target of a "create"
or the subject of a comparison; and there are expressions, where an object can
be named inside an arithmetic term several levels down.

Anything that needs to know which objects a line depends on has to look in all
of those places.  Missing one does not produce an error — it produces an
answer that is quietly short, and a caller that removes an object on the
strength of it can leave a project referring to something that is no longer
there.  So the search lives here once, and callers use it rather than keeping
a copy of their own.
"""

from __future__ import annotations
import struct
import klikback.core.mmf2.write_mfa as writer

READ_ONLY_PARAM_SITES = {9: (0x18,)}

def ace_object_refs(rec, kind, r, size):
    """Collect every object an event line names, from all of its sites at once.

    Returns the objects the line's header names, the ones its parameters carry,
    and the ones that appear inside expression terms, as one list.  A line that
    names the same object twice will report it twice: the result says where
    references are, not how many distinct objects there are.

    Parameters whose layout is not understood are skipped rather than guessed at,
    so the answer can be incomplete for an unusual line, and a caller that must
    not act on a partial answer should treat an unreadable parameter as a reason
    to leave the line alone.
    """
    out = []
    (objtype,) = struct.unpack_from("<h", rec, r + 2)
    if objtype >= 0:
        out.append(struct.unpack_from("<H", rec, r + 6)[0])
    try:
        params = writer._ace_params(rec, kind, r, size)
    except Exception:
        return out
    for _poff, ptype, body, blen in params:
        for site in (tuple(writer.QUALIFIER_PARAM_SITES.get(ptype, ()))
                     + READ_ONLY_PARAM_SITES.get(ptype, ())):
            if site + 2 <= blen:
                out.append(struct.unpack_from("<H", rec, body + site)[0])
        if ptype in writer.EXPRESSION_PARAM_TYPES:
            toks = writer._expression_tokens(rec[body:body + blen])
            for pos, otype, _code, tsize in (toks or ()):
                if otype >= 0 and tsize >= 8:
                    out.append(
                        struct.unpack_from("<H", rec, body + pos + 6)[0])
    return out
