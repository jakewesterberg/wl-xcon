"""What a call on the trial loop's path builds, read from the instructions it runs (XC-413, XC-414).

Never collected, since its name does not start with `test_`. Shared by `tests/test_gaze.py`, where
judging a window and a whole frame of a running trial are measured, and `tests/test_saccade.py`,
where one sample of the saccade detector is.
"""

from __future__ import annotations

import dis
import gc
import sys

#: The instructions that build an object, by what they build, the first prefix an instruction's name
#: has deciding: a container and what fills one, a string, a slice, a function or its cell, a
#: generator, an iterator, a call's packed arguments, and anything else built. Named by what is
#: built, not by instruction, so Python 3.11 to 3.13 read alike: one string is `FORMAT_VALUE` in
#: 3.12 and `FORMAT_SIMPLE` in 3.13. **A float is not counted**: CPython boxes every float an
#: arithmetic step makes, and no pure-Python path avoids it.
BUILDING = (
    ("BUILD_TUPLE", "tuple"), ("LIST_TO_TUPLE", "tuple"),
    ("BUILD_LIST", "list"), ("LIST_", "list"),
    ("BUILD_MAP", "dict"), ("BUILD_CONST_KEY_MAP", "dict"), ("DICT_", "dict"), ("MAP_ADD", "dict"),
    ("BUILD_SET", "set"), ("SET_ADD", "set"), ("SET_UPDATE", "set"),
    ("BUILD_STRING", "string"), ("FORMAT_", "string"), ("CONVERT_VALUE", "string"),
    ("BUILD_SLICE", "slice"), ("BINARY_SLICE", "slice"),
    ("MAKE_", "function"), ("SET_FUNCTION_ATTRIBUTE", "function"),
    ("RETURN_GENERATOR", "generator"), ("GET_ITER", "iterator"),
    ("CALL_FUNCTION_EX", "arguments"), ("CALL_INTRINSIC", "object"), ("BUILD_", "object"),
)


def what_builds(opname: str) -> "str | None":
    return next((what for prefix, what in BUILDING if opname.startswith(prefix)), None)


def builds_of(function) -> "list[tuple[str, str]]":
    """What `function`'s own code can build, read whole (`BUILDING`), by its qualified name: for a
    function a measure does not enter on each frame but runs every frame of, as `run.run_trial`
    runs `_Loop.frame` (XC-414)."""
    code = function.__code__
    return sorted({(code.co_qualname, what) for instruction in dis.get_instructions(code)
                   if (what := what_builds(instruction.opname)) is not None})


def built_on(call, *args, named: "dict | None" = None) -> "list[tuple[str, str]]":
    """What each Python function `call(*args)` runs can build, by the function's qualified name,
    `call` itself included (`BUILDING`). **The functions are found by running it**
    (`sys.setprofile`), so the measure follows whatever the path calls, which a list of functions
    written into a test does not; **each is read whole** (`dis`), so a branch this call did not take
    is read too. The collector is off meanwhile, so no finalizer runs inside.

    **`named` names code otherwise than by its qualified name**, code object to name: a
    `collections.namedtuple`'s generated `__new__` is compiled from a string as a `<lambda>`, so
    without it every record's tuple and any other lambda's read alike (XC-414's review, M2).

    **It cannot see a call that allocates.** It reads instructions, and a call is one instruction
    whatever it does: `str(frame)`, `list(x)` or `dict(x)` in `in_window` would pass it (the
    gaze-followups review's K3), as would anything a function written in C allocates inside. Such
    calls are kept off the path by reading it, not by this."""
    codes = set()

    def entered(frame, event, arg):
        if event == "call":
            codes.add(frame.f_code)

    collecting = gc.isenabled()
    gc.disable()
    sys.setprofile(entered)
    try:
        call(*args)
    finally:
        sys.setprofile(None)
        if collecting:
            gc.enable()
    named = named or {}
    return sorted({(named.get(code, code.co_qualname), what)
                   for code in codes for instruction in dis.get_instructions(code)
                   if (what := what_builds(instruction.opname)) is not None})
