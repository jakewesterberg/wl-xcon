"""What wl-preproc's reader of the rig's record still says about this build's records, and nothing
else is allowed to say."""

from __future__ import annotations

import re

#: The change kinds the pop-out search build writes that wl-preproc's reader does not list yet
#: (`wl_preproc/events/rigrecords.py::KINDS`, read at its main `bc5df71` on 2026-11-08). wl-preproc
#: accepted both on 2026-11-07. Until its reader lists them (**XC-461**), it publishes each row as
#: written, counts it as no person's act on a setting, and says so once per kind, which is what
#: `problems_beyond_xc461` lets pass. Delete this module once XC-461 closes.
NOT_YET_LISTED = ("suggested", "declined")

_NOTE = re.compile(r"\d+ change rows?: `kind` is '([a-z_]+)', which no build of wl-xcon this reader knows writes")


def problems_beyond_xc461(problems) -> list[str]:
    """`problems`, less wl-preproc's note on a kind in `NOT_YET_LISTED` (XC-461): every other
    problem still fails the test that reads it."""
    kept = []
    for problem in problems:
        found = _NOTE.match(problem)
        if found is None or found.group(1) not in NOT_YET_LISTED:
            kept.append(problem)
    return kept
