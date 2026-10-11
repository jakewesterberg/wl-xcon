"""Colour pop-out search. The paradigm the vocabulary could not express.

Until 2026-08-31 this task was **unwritable**, twice over. There was no colour, so a
red target among green distractors could not be stated at all; and an array was N
separate `Show` actions, so set size was a change to the *shape* of the task rather
than a value -- a different file for four items and eight, invisible to live editing.
Both are the commonest manipulations in visual search, which is the lab's programme.

What makes this the pop-out paradigm rather than a collection of shapes: the target
and the distractors differ in **exactly one** feature, and which feature is a
parameter. Swapping `target_looks` from a red disc to a square turns a colour
pop-out into a shape pop-out between one trial and the next, with the same task
running and the same structure recorded.

`target_looks` and `distractors` are isoluminant by construction -- `DKL(lum=0)` -- which is a
claim about photometry, so this task **runs only on a measured display calibration that carries
its primaries' spectra** (engine spec §7.3; engine build A2): on the default it is refused in
every kind of session. Its red and green are the PI's 2023 pop-out items' (Westerberg et al.
2023, Methods, "Task design: Pop-out search"), made isoluminant in the lab's observer, as
contrasts about `BACKGROUND`, the gray the array is shown on (spec §7.5; the engine A2 plan's
Q1). No calibration for our panels exists yet.
"""

from wl_xcon.photometry import DKL, Gray
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
    EXPECTED,
    HARDER,
    STIMULUS,
    Choice,
    Meaning,
    ReactionTime,
    Task,
    Trial,
    Window,
)

FIX = Stimulus("fix", at=(0.0, 0.0), looks=Disc(size=0.3, color=Gray(P("fix_luminance"))))

#: A red and a green of equal luminance, as cone contrasts from the background. Equal *by
#: construction* rather than by arithmetic somebody did once: the whole reason DKL is the space
#: this is written in. The PI's 2023 items, carried over by his published numbers (the engine A2
#: plan's Q1): their cone contrasts (red L +0.27, M -0.54, S -0.94; green L -0.06, M +0.13,
#: S -0.87), computed in another cone set by Cole and Hine's (1992) method, taken as contrasts in
#: the lab's observer about a D65 gray, and L and M moved to the nearest point isoluminant under
#: V_F,10 (by at most 0.022), S kept (computed 2026-10-10). His published lights (their xy)
#: converted against a D65 gray instead would give l_m +0.643 and -0.118.
RED = DKL(lum=0.0, l_m=0.603, s_lm=-0.94)
GREEN = DKL(lum=0.0, l_m=-0.143, s_lm=-0.87)

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

#: The gray the array is shown on, D65 at 16 cd/m². RED and GREEN are contrasts about it, and on
#: black they would name no light (engine spec §7.5). The PI's answer to the engine A2 plan's Q1
#: (2026-10-10): the gray at the items' own luminance, one level for all rigs, the brightest each
#: rig's measured screen makes with a small margin. On sRGB-like primaries at an 80 cd/m² white,
#: RED, made mostly by the red primary with a little green beside it, needs that primary at full
#: drive on a 17.7 cd/m² gray, so 16 leaves 9.4% (computed 2026-10-10); re-set when the panels
#: are measured (XC-310). The fixation point's starting 40 cd/m² stays
#: brighter (Weber +1.5).
BACKGROUND = Gray(16.0)

search = Trial(
    start="await_fix",
    # Direct view, with the detection tasks: the lab's programme runs there.
    view="direct",
    background=BACKGROUND,
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


#: The target's look, in search: the feature it pops out on, overriding the shared list's meaning
#: for a lone target's look (the engine C1 plan's Appendix B, item 28; decisions.md TRN-10).
TARGET_LOOKS = Meaning(
    EXPECTED,
    STIMULUS,
    raising=HARDER,
    note=(
        "read with the distractors: the target's look is the feature it pops out on, and a swap "
        "of its color slows the next few trials (priming of pop-out); a change can leave it "
        "looking like the distractors, with no answer, and a shape difference guides search "
        "less surely than a color one"
    ),
    overrides=(
        "in search the target's look is the feature that pops out, not a lone target's shape"
    ),
)

#: The ring's radius (`Array.radius`), declared here and not shared: in `adaptive_detection` the
#: same name moves nothing on screen (the engine C1 plan's Appendix B, item 19).
RING = Meaning(
    EXPECTED,
    STIMULUS,
    raising=HARDER,
    note=(
        "a wider ring makes the array sparser, which weakens pop-out; red-green sensitivity "
        "falls farther from fixation; and saccades scatter more while the item windows stay "
        "as they are"
    ),
)

#: The task object (engine spec §3.5; engine build C1): a saccade landing on any item of the
#: array is the choice, the target or a distractor, and its reaction time runs from the array's
#: command to it (XC-288 §4.3).
TASK = Task(
    structures={"search": search},
    default="search",
    reaction_time=ReactionTime(
        state="array_on",
        to=("verify", Outcome.WRONG_TARGET),
        note=(
            "from entering array_on, the frame the array is commanded, to a saccade landing on "
            "an item, the target or a distractor"
        ),
    ),
    choice=Choice(items=("search.target", "search.distractor"), by="saccade"),
    meanings={"target_looks": TARGET_LOOKS, "eccentricity": RING},
)
