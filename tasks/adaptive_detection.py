"""Detection with contrast on a staircase, and mini-blocks of held eccentricity.

The task S1's bake-off expected to be the hard case, and it was not: **the trial is
`fixation_detection`'s trial unchanged.** A staircase was never a within-trial
concern. Everything adaptive here lives in `next_params`, which is ordinary Python
called at a trial boundary, outside the frame budget (ADR-0006).

That is the whole argument for the split, demonstrated rather than asserted: the
strongest case for imperative trials evaporates once condition generation lives
between trials, where it always belonged.
"""

from dataclasses import dataclass, field

from wl_xcon.photometry import Gray
from wl_xcon.task import (
    After,
    Bounded,
    Mark,
    Disc,
    Entered,
    Hold,
    Exited,
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
    CLEAR_CUT,
    EASIER,
    NOT_DIFFICULTY,
    NO_CHOICE,
    STIMULUS,
    Meaning,
    ReactionTime,
    Task,
    Trial,
    Window,
)

FIX = Stimulus("fix", at=(0.0, 0.0), looks=Disc(size=0.3, color=Gray(P("fix_luminance"))))

adaptive_detection = Trial(
    start="await_fix",
    # Direct view, as `fixation_detection`: its ±16° is wider than the stereoscope's mask.
    view="direct",
    windows=[
        Window("fix", at=(0.0, 0.0), radius=P("fix_window"), on="fix"),
        Window(
            "target",
            at=(P("target_position"), 0.0),
            radius=P("target_window"),
            on="target",
        ),
    ],
    params=[
        Param("fix_timeout", unit="s", low=0.5, high=10.0),
        Param("fix_hold", unit="s", low=0.05, high=2.0),
        Param("response_window", unit="s", low=0.1, high=3.0),
        Param("target_hold", unit="s", low=0.05, high=1.0),
        Param("fix_window", unit="deg", low=0.5, high=5.0),
        Param("target_window", unit="deg", low=0.5, high=6.0),
        # ±16° again (direct-view spec §8), checked against direct view's ±30.5° field.
        # ±12 was the interim, at the stereoscope's mask, before direct view had a
        # `Geometry` (2026-09-28).
        Param("target_position", unit="deg", low=-16.0, high=16.0),
        # Appearance is a parameter, so switching circles among squares for
        # penguins among elephants is a value applied in an ITI -- not a new
        # task and not a new block.
        Param(
            "target_looks",
            unit="appearance",
            choices=(
                Disc(size=1.0, color=Gray(P("target_luminance"))),
                Square(size=1.0, color=Gray(P("target_luminance"))),
            ),
        ),
        Param("contrast", unit="fraction", low=0.02, high=1.0),
        # Held eccentricity is |target_position|, so the same bound.
        Param("eccentricity", unit="deg", low=2.0, high=16.0),
        # Absolute luminance, D65 white (the PI, 2026-10-07: "Absolute cd/m²", starting
        # at "40 cd/m²"). Bounded at 80, the default calibration's white (the sRGB
        # standard's), until a measured calibration and V9's brightness cap say otherwise
        # (engine spec §7.1, §7.7).
        Param("fix_luminance", unit="cd/m2", low=0.0, high=80.0, start=40.0),
        Param("target_luminance", unit="cd/m2", low=0.0, high=80.0, start=40.0),
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
                On(Hold("fix", P("fix_hold")), "stim_on"),
                On(Exited("fix"), Outcome.FIXATION_BREAK, do=[Mark(4101)]),
                On(After(P("fix_timeout")), Outcome.NO_FIXATION, do=[Mark(4100)]),
            ],
        ),
        State(
            # The target's position and contrast are parameters, so a mini-block
            # that moves the array from 0 to 10 degrees is a value change applied
            # in an ITI -- not a new task, and not a new block (S3 §7).
            "stim_on",
            enter=[
                Show(
                    Stimulus(
                        "target",
                        at=(P("target_position"), 0.0),
                        looks=P("target_looks"),
                    )
                ),
                Mark(4097),
            ],
            go=[
                On(SaccadeTo("target"), "verify", do=[Mark(4098)]),
                On(After(P("response_window")), Outcome.NO_RESPONSE),
            ],
        ),
        State(
            "verify",
            go=[
                On(
                    Hold("target", P("target_hold")),
                    Outcome.CORRECT,
                    do=[Mark(4099), Mark(4102), Reward("reward_correct")],
                ),
                On(Exited("target"), Outcome.WRONG_TARGET),
                On(After(P("response_window")), Outcome.NO_RESPONSE),
            ],
        ),
    ],
)


@dataclass
class Staircase:
    """One-up two-down on contrast, converging near 71% correct.

    Between-trial Python. It holds state across trials, does arbitrary arithmetic,
    and none of that costs anything -- it runs in the inter-trial interval where
    an error is observable and recoverable rather than inside a frame budget.
    """

    value: float
    step: float = 0.8
    floor: float = 0.02
    ceiling: float = 1.0
    _consecutive_correct: int = field(default=0, repr=False)

    def update(self, correct: bool) -> None:
        if not correct:
            self._consecutive_correct = 0
            self.value = min(self.ceiling, self.value / self.step)
            return
        self._consecutive_correct += 1
        if self._consecutive_correct >= 2:
            self._consecutive_correct = 0
            self.value = max(self.floor, self.value * self.step)


def next_params(
    staircase: Staircase, eccentricity: float, last: Outcome | None
) -> dict[str, float]:
    """The next trial's values. Called at a trial boundary, never inside one.

    Only completed trials move the staircase: an abort says nothing about
    difficulty, and letting one move the estimate makes contrast track engagement
    rather than perception.
    """
    if last in (Outcome.CORRECT, Outcome.WRONG_TARGET):
        staircase.update(last is Outcome.CORRECT)
    return {
        "fix_timeout": 4.0,
        "fix_hold": 0.3,
        "response_window": 0.6,
        "target_hold": 0.2,
        "contrast": staircase.value,
        "eccentricity": eccentricity,
    }


#: The task object (engine spec §3.5; engine build C1): the detection trial, timed as
#: `fixation_detection`'s is, and the two settings it declares as no other task does (the engine
#: C1 plan's Appendix B, items 20 and 21; decisions.md TRN-10). No stimulus reads either and
#: nothing moves them until a between-trial procedure is called (XC-242): `contrast` keeps the
#: direction `Staircase` above assumes, raising it after an error, and `eccentricity` is no
#: difficulty setting while nothing reads it; each note says so, so the record never teaches an
#: agent that either has no effect.
TASK = Task(
    structures={"detection": adaptive_detection},
    default="detection",
    reaction_time=ReactionTime(
        state="stim_on",
        to=("verify",),
        note=(
            "from entering stim_on, the frame the target is commanded, to a saccade landing in "
            "its window"
        ),
    ),
    choice=NO_CHOICE,
    meanings={
        "contrast": Meaning(CLEAR_CUT, STIMULUS, raising=EASIER, note=(
            "nothing reads it yet: no stimulus draws with it, and nothing moves it until a "
            "between-trial procedure is called (XC-242)")),
        "eccentricity": Meaning(NOT_DIFFICULTY, STIMULUS, note=(
            "nothing reads it yet: the target's distance is target_position's, and this "
            "setting moves nothing on screen until a between-trial procedure is called "
            "(XC-242)")),
    },
)
