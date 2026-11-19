"""Colour pop-out search, for training on the default calibration (engine build B).

**The search task with ordinary colors.** `visual_search` shows the PI's 2023 red and green,
isoluminant in the lab's observer on a 16 cd/m² gray, and is meant for a measured calibration
that carries its primaries' spectra (engine spec §7.3; engine build A2), running on the default
with warnings that its colors are only nominally isoluminant (XC-352's A19 and A20); this
variant shows the sRGB red and green primaries' colors instead, each at its own luminance,
live-editable (the PI, N§4 batch 2: "a training variant uses ordinary red and green (no
isoluminance claim)"; Question 3). It loads on the default calibration in every session kind,
recording too, with the warning that its colors are nominal (the PI, 2026-10-11, XC-352's A21;
a recording session refused it until then, spec §7.2). Both start at 15 cd/m², equal by the sRGB
standard's numbers and measured by nobody: not isoluminant for any observer, and nothing here
claims they are.

Everything else -- states, windows, every other parameter, and the gray it is shown on (the
engine A2 plan's Q1) -- is `visual_search`'s, and
`tests/test_reference_tasks.py` holds the two to that. Its starting values are as unset as
that task's (XC-183).
"""

from wl_xcon.photometry import Gray, xyY
from wl_xcon.task import (
    After,
    Array,
    Bounded,
    Disc,
    Entered,
    Exited,
    Hold,
    Mark,
    ObjectWindows,
    On,
    Outcome,
    P,
    Param,
    Reward,
    SaccadeTo,
    Show,
    Square,
    State,
    Stimulus,
    EASIER,
    EXPECTED,
    STIMULUS,
    Choice,
    Meaning,
    OWED,
    Counting,
    ReactionTime,
    Task,
    Trial,
    Window,
)

#: Why a hold keeps a highest: the state it is held in ends at a fixed 10 s (3 s for the target's),
#: so a longer hold cannot finish (the engine C2a plan's O2; `hold-cut-short`).
HOLD_WHY_10 = "the state ends at 10 s, so a longer hold cannot finish"
HOLD_WHY_3 = "the state ends at 3 s, so a longer hold cannot finish"

FIX = Stimulus("fix", at=(0.0, 0.0), looks=Disc(size=0.3, color=Gray(P("fix_luminance"))))

#: The sRGB red and green primaries' chromaticities (W3C sRGB v1.10), each at its own luminance:
#: ordinary colors, with no claim about their luminance for any observer.
RED = xyY(0.64, 0.33, P("red_luminance"))
GREEN = xyY(0.30, 0.60, P("green_luminance"))

#: Why a set size keeps a highest (`unbounded-set-size`): a run builds every object and its window
#: before a trial's first frame, so an unbounded one could stall it; 12 is TSK-39's, no guess added.
SET_SIZE_WHY = "a run builds every object before the first frame, so a set size needs a highest"

ARRAY = Stimulus(
    "search",
    at=(0.0, 0.0),
    looks=Array(
        n=P("set_size"),
        radius=P("array_eccentricity"),
        target=P("target_index"),
        looks=P("target_appearance"),
        among=P("distractor_appearance"),
        phase=P("array_rotation"),
    ),
)

search = Trial(
    start="await_fix",
    # Direct view, with the detection tasks: the lab's programme runs there.
    view="direct",
    # Its counting table (the engine C2a plan's Appendix B, item 9): a training variant, so a break
    # after the array appears (in `array_on`) is owed, shown again, and each condition is
    # practised as planned; no repeat limit (item 12, the PI, 2026-10-13).
    counting=Counting(after_stimulus=OWED, appears="array_on"),
    background=Gray(16.0),  # visual_search.BACKGROUND (the engine A2 plan's Q1)
    windows=[
        Window("fix", at=(0.0, 0.0), radius=P("fix_window"), on="fix"),
        # One declaration, `set_size` windows. The author cannot write them out,
        # because how many there are is not known until a trial runs.
        ObjectWindows(of="search", radius=P("object_window")),
    ],
    params=[
        Param("fix_acquisition", unit="s", low=0.0),
        Param("fix_hold", unit="s", low=0.0, high=10.0, why=HOLD_WHY_10),
        Param("response_deadline", unit="s", low=0.0),
        Param("target_hold", unit="s", low=0.0, high=3.0, why=HOLD_WHY_3),
        Param("fix_window", unit="deg"),
        # No range (the PI, 2026-11-16, "Hard limits only where impossible"; decisions.md
        # TSK-39): windows that crowd at the values set are warned of by the layout, so a
        # saccade to one distractor is not scored against another unseen (pitfalls P20).
        Param("object_window", unit="deg", start=1.0),
        # Its lowest is 0, a distance; the field is judged where it is set (direct view's
        # ±18.4° vertically), not by a guessed highest.
        Param("array_eccentricity", unit="deg", low=0.0, start=8.0),
        # The manipulation. A value, not a structure -- which is the entire point.
        Param("set_size", unit="objects", low=1, high=12, start=4, why=SET_SIZE_WHY, whole=True),
        # No highest: an index past the array is refused where it is set (`check.laid_out`),
        # against the set size it is set with, and the load holds it at its start, 0.
        Param("target_index", unit="index", low=0, start=0, whole=True),
        #: Randomised between trials so the animal cannot learn positions.
        Param("array_rotation", unit="deg", start=0.0),
        # Feature as a value. Red-among-green and square-among-discs are the same
        # task with a different setting.
        Param(
            "target_appearance",
            unit="appearance",
            choices=(
                Disc(size=1.0, color=RED),
                Disc(size=1.0, color=GREEN),
                Square(size=1.0, color=GREEN),
            ),
        ),
        Param(
            "distractor_appearance",
            unit="appearance",
            choices=(Disc(size=1.0, color=GREEN), Disc(size=1.0, color=RED)),
        ),
        # Absolute luminance, D65 white (the PI, 2026-10-07: "Absolute cd/m²", starting
        # at "40 cd/m²"). Bounded at 80, the default calibration's white (the sRGB
        # standard's), until a measured calibration and V9's brightness cap say otherwise
        # (engine spec §7.1, §7.7).
        Param("fix_luminance", unit="cd/m2", low=0.0, high=80.0, start=40.0,
              why="white on the default calibration, the published sRGB 80 cd/m² (COL-29)"),
        # Each color's luminance, its own (Question 3), equal to start by the standard's numbers.
        # Bounded at its primary's full drive on the default calibration, floored: 17.0 and
        # 57.2 cd/m² at its 80 cd/m² white.
        Param("red_luminance", unit="cd/m2", low=0.0, high=17.0, start=15.0,
              why="the red primary at full drive on the default calibration (80 cd/m2 white)"),
        Param("green_luminance", unit="cd/m2", low=0.0, high=57.0, start=15.0,
              why="the green primary at full drive on the default calibration (80 cd/m2 white)"),
    ],
    states=[
        State(
            "await_fix",
            enter=[Show(FIX), Mark(4096)],
            go=[
                On(Entered("fix"), "hold_fix"),
                On(After(P("fix_acquisition")), Outcome.NO_FIXATION, do=[Mark(4100)]),
            ],
        ),
        State(
            "hold_fix",
            go=[
                On(Hold("fix", P("fix_hold")), "array_on"),
                On(Exited("fix"), Outcome.FIXATION_BREAK, do=[Mark(4101)]),
                # Longer than any legal `fix_hold`, as `fixation_detection` says.
                On(After(10.0), Outcome.NO_FIXATION),
            ],
        ),
        State(
            "array_on",
            enter=[Show(ARRAY), Mark(4103)],
            go=[
                On(SaccadeTo("search.target"), "verify", do=[Mark(4098)]),
                # One transition for every distractor there will ever be. Enumerating
                # them would be the same structure-versus-value problem one level
                # down, and would make the measurement this task exists for --
                # target versus distractor -- unavailable.
                On(
                    SaccadeTo("search.distractor"),
                    Outcome.WRONG_TARGET,
                    do=[Mark(4104), Mark(4113)],
                ),
                On(After(P("response_deadline")), Outcome.NO_RESPONSE, do=[Mark(4117)]),
            ],
        ),
        State(
            "verify",
            go=[
                On(
                    Hold("search.target", P("target_hold")),
                    Outcome.CORRECT,
                    do=[Mark(4099), Mark(4110), Mark(4102), Reward("reward_correct")],
                ),
                On(Exited("search.target"), Outcome.TARGET_BREAK, do=[Mark(4120)]),
                # The hold runs its own time, as `fixation_detection` says.
                On(After(3.0), Outcome.NO_RESPONSE, do=[Mark(4117)]),
            ],
        ),
    ],
)


#: How many objects the array shows: `visual_search`'s override, written here as that file's other
#: declarations are (`tests/test_reference_tasks.py` holds the two equal).
SET_SIZE = Meaning(
    EXPECTED,
    STIMULUS,
    raising=EASIER,
    note="in a pop-out search a denser array makes the odd object stand out more",
    overrides="a pop-out search: a denser array makes the odd object stand out more",
)

#: Each color's luminance, read from the other's (the engine C1 plan's Appendix B, items 26 and
#: 27; decisions.md TRN-10): the cue it adds is the brightness gap between them.
_GAP = (
    "the cue it adds is the brightness gap between the red and the green, redundant with their "
    "color, so a larger gap is easier; near equal brightness, whose point for this animal is "
    "unknown, the direction is uncertain; narrowing the gap is the fading path toward "
    "isoluminance"
)

#: The task object (engine spec §3.5; engine build C1): `visual_search`'s, and the two luminance
#: settings only this variant has.
TASK = Task(
    structures={"search": search},
    default="search",
    reaction_time=ReactionTime(
        state="array_on",
        to=("verify", Outcome.WRONG_TARGET),
        note=(
            "from entering array_on, the frame the array is commanded, to a saccade landing on "
            "an object, the target or a distractor"
        ),
    ),
    choice=Choice(objects=("search.target", "search.distractor"), by="saccade"),
    meanings={
        "set_size": SET_SIZE,
        "red_luminance": Meaning(
            EXPECTED, STIMULUS, raising=EASIER, relative_to="green_luminance", note=_GAP),
        "green_luminance": Meaning(
            EXPECTED, STIMULUS, raising=EASIER, relative_to="red_luminance", note=_GAP),
    },
    # The rig fixes the head, which has no tracking there (the PI, 2026-10-11: "kiosk will be head
    # free, in the rig will be head fixed. we do not have head tracking in the rig"; the engine C1
    # plan's Appendix B, item 31): a warning in any session not declared head-fixed (`RIG_FIXED`).
    needs_fixed_head=True,
)
