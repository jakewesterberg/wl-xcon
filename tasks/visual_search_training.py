"""Colour pop-out search, for training on the default calibration (engine build B).

**The search task with ordinary colors.** `visual_search` shows the PI's 2023 red and green,
isoluminant in the lab's observer on a 16 cd/m² gray, and runs only on a measured calibration
that carries its primaries' spectra (engine spec §7.3; engine build A2); this variant shows the
sRGB red and green primaries' colors instead, each at its own luminance, live-editable (the PI,
N§4 batch 2: "a training variant uses ordinary red and green (no isoluminance claim)"; Question
3). It loads on the default calibration in training and piloting, with the warning, and **a
recording session refuses it** while the default is in use (spec §7.2). Both start at 15 cd/m²,
equal by the sRGB standard's numbers and measured by nobody: not isoluminant for any observer,
and nothing here claims they are.

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
    ItemWindows,
    Mark,
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
    Trial,
    Window,
)

FIX = Stimulus("fix", at=(0.0, 0.0), looks=Disc(size=0.3, color=Gray(P("fix_luminance"))))

#: The sRGB red and green primaries' chromaticities (W3C sRGB v1.10), each at its own luminance:
#: ordinary colors, with no claim about their luminance for any observer.
RED = xyY(0.64, 0.33, P("red_luminance"))
GREEN = xyY(0.30, 0.60, P("green_luminance"))

ARRAY = Stimulus(
    "search",
    at=(0.0, 0.0),
    looks=Array(
        n=P("set_size"),
        radius=P("eccentricity"),
        target=P("target_index"),
        looks=P("target_looks"),
        among=P("distractors"),
        phase=P("array_phase"),
    ),
)

search = Trial(
    start="await_fix",
    # Direct view, with the detection tasks: the lab's programme runs there.
    view="direct",
    background=Gray(16.0),  # visual_search.BACKGROUND (the engine A2 plan's Q1)
    windows=[
        Window("fix", at=(0.0, 0.0), radius=P("fix_window"), on="fix"),
        # One declaration, `set_size` windows. The author cannot write them out,
        # because how many there are is not known until a trial runs.
        ItemWindows(of="search", radius=P("item_window")),
    ],
    params=[
        Param("fix_timeout", unit="s", low=0.5, high=10.0),
        Param("fix_hold", unit="s", low=0.05, high=2.0),
        Param("response_window", unit="s", low=0.1, high=3.0),
        Param("target_hold", unit="s", low=0.05, high=1.0),
        Param("fix_window", unit="deg", low=0.5, high=5.0),
        # Bounded so that twelve items on the smallest legal ring still cannot
        # crowd: adjacent centres are 2 R sin(pi/n) = 2.59° apart at n=12, R=5, and
        # two 1° windows sum to 2°. The first version of this task allowed 4°
        # windows on a 3° ring, where adjacent windows overlapped by more than their
        # own width -- so a saccade to one distractor would have been scored against
        # another. It passed every check that existed at the time.
        Param("item_window", unit="deg", low=0.5, high=1.0),
        # Back to 14, what it was before the interim bound of 12 at the stereoscope's
        # mask (2026-09-28), and checked against direct view: the ring reaches ±14°
        # vertically as well, inside direct view's ±18.4°.
        Param("eccentricity", unit="deg", low=5.0, high=14.0),
        # The manipulation. A value, not a structure -- which is the entire point.
        Param("set_size", unit="items", low=2, high=12),
        # `high` is one below `set_size`'s *lowest* legal value, because the checker
        # reasons over ranges: a target index of 6 is illegal the moment set size
        # can be 2, whatever it happens to be set to right now.
        Param("target_index", unit="index", low=0, high=1),
        #: Randomised between trials so the animal cannot learn positions.
        Param("array_phase", unit="deg", low=0.0, high=360.0),
        # Feature as a value. Red-among-green and square-among-discs are the same
        # task with a different setting.
        Param(
            "target_looks",
            unit="appearance",
            choices=(
                Disc(size=1.0, color=RED),
                Disc(size=1.0, color=GREEN),
                Square(size=1.0, color=GREEN),
            ),
        ),
        Param(
            "distractors",
            unit="appearance",
            choices=(Disc(size=1.0, color=GREEN), Disc(size=1.0, color=RED)),
        ),
        # Absolute luminance, D65 white (the PI, 2026-10-07: "Absolute cd/m²", starting
        # at "40 cd/m²"). Bounded at 80, the default calibration's white (the sRGB
        # standard's), until a measured calibration and V9's brightness cap say otherwise
        # (engine spec §7.1, §7.7).
        Param("fix_luminance", unit="cd/m2", low=0.0, high=80.0, start=40.0),
        # Each color's luminance, its own (Question 3), equal to start by the standard's numbers.
        # Bounded at its primary's full drive on the default calibration, floored: 17.0 and
        # 57.2 cd/m² at its 80 cd/m² white.
        Param("red_luminance", unit="cd/m2", low=0.0, high=17.0, start=15.0),
        Param("green_luminance", unit="cd/m2", low=0.0, high=57.0, start=15.0),
    ],
    states=[
        State(
            "await_fix",
            enter=[Show(FIX), Mark(4096)],
            go=[
                On(Entered("fix"), "hold_fix"),
                On(After(P("fix_timeout")), Outcome.NO_FIXATION, do=[Mark(4100)]),
            ],
        ),
        State(
            "hold_fix",
            go=[
                On(Hold("fix", P("fix_hold")), "array_on"),
                On(Exited("fix"), Outcome.FIXATION_BREAK, do=[Mark(4101)]),
                On(After(P("fix_timeout")), Outcome.NO_FIXATION),
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
                On(After(P("response_window")), Outcome.NO_RESPONSE, do=[Mark(4117)]),
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
                On(After(P("response_window")), Outcome.NO_RESPONSE, do=[Mark(4117)]),
            ],
        ),
    ],
)
