"""The artifact must show the display, because the display is what goes wrong."""

from wl_xcon.review import render
from wl_xcon.task import (
    After, Disc, Entered, Hide, Hold, Mark, On, Outcome, REMEMBERED, Show, State,
    Stimulus, Trial, Update, Window,
)

FIX = Stimulus("fix", at=(0.0, 0.0), looks=Disc(size=0.3))
TARGET = Stimulus("target", at=(8.0, 0.0), looks=Disc(size=1.0))

TRIAL = Trial(
    start="await_fix",
    windows=[
        Window("fix", at=(0.0, 0.0), radius=2.0, on="fix"),
        Window("target", at=(8.0, 0.0), radius=2.0, on="target"),
    ],
    states=[
        State("await_fix", enter=[Show(FIX), Mark(4096)],
              go=[On(Entered("fix"), "hold_fix"),
                  On(After(2.0), Outcome.NO_FIXATION, do=[Mark(4100)])]),
        State("hold_fix",
              go=[On(Hold("fix", 0.3), "stim_on"),
                  On(After(2.0), Outcome.NO_FIXATION)]),
        State("stim_on", enter=[Show(TARGET), Hide("fix"), Mark(4097)],
              go=[On(Hold("target", 0.2), Outcome.CORRECT, do=[Mark(4099)]),
                  On(After(1.0), Outcome.NO_RESPONSE)]),
    ],
)


def test_the_artifact_shows_when_each_stimulus_is_on_screen():
    """Position and disparity are not enough.

    Every defect the reviews found was about *when* something was on the display,
    not where -- so an artifact showing only position is a picture a reviewer trusts
    of the half of the task that was never the problem.
    """
    artifact = render(TRIAL)

    assert "## Display timeline" in artifact
    # Shown in one state, taken down in another: the reviewer can see the span.
    assert "`fix`" in artifact
    assert "shown in `await_fix`" in artifact
    assert "hidden in `stim_on`" in artifact
    # A stimulus never taken down says so, rather than leaving a blank cell that
    # reads as missing information.
    assert "until the trial ends" in artifact


def test_the_code_table_names_the_transition_not_only_the_state():
    """A state emitting several codes on different edges is ambiguous otherwise.

    `stim_on` strobes one code on entry and another on the edge to CORRECT, and an
    artifact attributing both to `stim_on` cannot be checked against a recording.
    """
    artifact = render(TRIAL)

    assert "on entry" in artifact
    assert "on → CORRECT" in artifact


def test_an_update_appears_in_the_timeline():
    trial = Trial(
        start="on",
        windows=[Window("w", at=(0.0, 0.0), radius=2.0, on="fix")],
        states=[
            State("on", enter=[Show(FIX)], go=[On(After(0.5), "changed")]),
            State("changed", enter=[Update("fix", looks=Disc(size=1.5))],
                  go=[On(After(0.5), Outcome.CORRECT)]),
        ],
    )
    assert "changed in `changed`" in render(trial)


def test_an_array_task_renders():
    """Review-by-artifact fails closed only if the artifact renders.

    `ItemWindows` was added to the vocabulary and nothing rendered one, so the
    review artifact -- the thing ADR-0006 says a task is approved from -- raised
    `AttributeError` on every search task. No test caught it because no test
    rendered a task with an array.
    """
    from wl_xcon.task import Array, ItemWindows, P, Param, SaccadeTo

    trial = Trial(
        start="search",
        params=[Param("set_size", unit="items", low=2, high=6)],
        windows=[ItemWindows(of="search", radius=2.0)],
        states=[
            State(
                "search",
                enter=[
                    Show(
                        Stimulus(
                            "search",
                            at=(0.0, 0.0),
                            looks=Array(n=P("set_size"), radius=8.0, target=0),
                        )
                    )
                ],
                go=[
                    On(SaccadeTo("search.target"), Outcome.CORRECT),
                    On(After(1.0), Outcome.NO_RESPONSE),
                ],
            ),
        ],
    )
    artifact = render(trial)

    # The family is described as a family, since how many there are is a parameter.
    assert "search.*" in artifact
    assert "set_size items" in artifact


def _window_row(artifact: str, name: str) -> str:
    """The window table's row for `name`, as a reviewer reads it."""
    for line in artifact.splitlines():
        if line.startswith(f"| `{name}` |"):
            return line
    raise AssertionError(f"no window row for {name!r} in the artifact")


def test_the_artifact_names_the_stimulus_each_window_scores():
    """Trap 11: the artifact *is* the review, so what it omits is unreviewed. Window
    coupling is the specific thing that check `nothing-to-look-at` exists to enforce,
    and a reviewer can only confirm it if the artifact says it."""
    artifact = render(TRIAL)
    assert "`fix`" in _window_row(artifact, "fix")
    assert "`target`" in _window_row(artifact, "target")


def test_a_window_scoring_a_remembered_location_says_so():
    """`REMEMBERED` is a claim someone made -- that nothing is displayed there on
    purpose -- and it has to be legible as one. Rendered identically to an ordinary
    stimulus it would read as a coupling the task does not have."""
    trial = Trial(
        start="hold",
        windows=[Window("recalled", at=(6.0, 0.0), radius=2.0, on=REMEMBERED)],
        states=[
            State("hold", enter=[Show(FIX)],
                  go=[On(Hold("recalled", 0.2), Outcome.CORRECT),
                      On(After(1.0), Outcome.NO_RESPONSE)]),
        ],
    )
    row = _window_row(render(trial), "recalled")
    assert "remembered" in row.lower()
    assert "`" + "REMEMBERED" + "`" not in row, "it is a claim, not a stimulus name"


def test_a_window_coupled_to_nothing_is_called_out_rather_than_left_blank():
    """An empty cell reads as missing information. `on` unset is refused at load, so
    the only way a reviewer sees this is a task that skipped the checker -- which is
    exactly when the artifact has to be loudest."""
    trial = Trial(
        start="hold",
        windows=[Window("orphan", at=(6.0, 0.0), radius=2.0)],
        states=[
            State("hold", enter=[Show(FIX)],
                  go=[On(Hold("orphan", 0.2), Outcome.CORRECT),
                      On(After(1.0), Outcome.NO_RESPONSE)]),
        ],
    )
    row = _window_row(render(trial), "orphan")
    assert "nothing declared" in row


def test_the_stimuli_table_shows_how_each_stimulus_is_placed_and_combined():
    """XC-259: per-eye positions, layer, combination, opacity and the background are what
    the drawer draws from, so a table of `at` and disparity alone left half of it unreviewed."""
    from wl_xcon.photometry import Gray
    from wl_xcon.task import P, Param

    pair = Stimulus("pair", at=(0.0, 0.0), looks=Disc(size=1.0, color=Gray(40.0)),
                    at_left=(2.0, 0.0), at_right=(-2.0, 0.5))
    glow = Stimulus("glow", at=(P("ecc"), 1.0), looks=Disc(size=1.0, color=Gray(10.0)),
                    layer=2, combine="add", opacity=0.5)
    trial = Trial(
        start="on", view="stereoscope", background=Gray(20.0),
        params=[Param("ecc", unit="deg", low=-4.0, high=4.0)],
        states=[State("on", enter=[Show(pair), Show(glow)], go=[On(After(1.0), Outcome.ABORT)])],
    )
    artifact = render(trial)

    assert "| State | Stimulus | Position° | Disparity° | Eye | Layer | Combination | Opacity |" \
        in artifact
    assert "| `on` | `pair` | L (2, 0) / R (-2, 0.5) | 0 | both | 0 | cover | 1 |" in artifact
    # A parameter by its name, as everywhere else in the report.
    assert "| `on` | `glow` | (ecc, 1) | 0 | both | 2 | add | 0.5 |" in artifact
    # Once, above the table, each eye's on the stereoscope.
    assert artifact.count("Background:") == 1
    assert "Background: left eye Gray(20); right eye Gray(20)" in artifact
    assert artifact.index("Background:") < artifact.index("| State | Stimulus |")


def test_an_unset_background_is_said_to_be_black():
    assert "Background: black (default)" in render(TRIAL)


def test_each_eye_s_own_background_is_shown_where_one_is_declared():
    from wl_xcon.photometry import Gray

    own = Trial(start="on", view="stereoscope", background=Gray(20.0), background_right=Gray(30.0),
                states=[State("on", enter=[Show(FIX)], go=[On(After(1.0), Outcome.ABORT)])])
    assert "Background: left eye Gray(20); right eye Gray(30)" in render(own)
    # Off the stereoscope too, where the checker refuses it: the artifact shows what is declared.
    direct = Trial(start="on", view="direct", background_left=Gray(5.0),
                   states=[State("on", enter=[Show(FIX)], go=[On(After(1.0), Outcome.ABORT)])])
    assert "Background: left eye Gray(5); right eye black (default)" in render(direct)


def test_a_background_s_parameters_print_as_their_names_and_a_non_color_still_renders():
    from wl_xcon.photometry import Gray
    from wl_xcon.task import P

    def shown(**background) -> str:
        return render(Trial(start="on", **background, states=[
            State("on", enter=[Show(FIX)], go=[On(After(1.0), Outcome.ABORT)])]))

    assert "Background: Gray(bg_lum)" in shown(background=Gray(P("bg_lum")))
    assert "Background: bg" in shown(background=P("bg"))
    # The checker refuses it, but `wlx review` checks nothing first, and an artifact that
    # raises shows nothing at all.
    assert "Background: 20" in shown(background=20.0)
