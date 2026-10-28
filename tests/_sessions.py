"""A real `taskd.Session` on the simulators, for the tests of the code that works around
one -- `marks`, `preflight`, `stranded` -- without running a trial. Never collected: its
name does not start with `test_`."""

from __future__ import annotations

import time
from datetime import date, datetime
from pathlib import Path

from _rig import DIRECT
from wl_xcon import warnlist
from wl_xcon.bounds import Bounds, Ceiling, Floor
from wl_xcon.dio import Simulated as Card
from wl_xcon.photometry import SRGB
from wl_xcon.taskd import Session, SessionSpec
from wl_xcon.welfare import Deployment, Simulated as Pump

#: The wall these sessions read: this host's clock when the module loaded, so a time
#: typed from it (`typed`) names the same instant on this host's calendar.
WALL = time.time()

#: What an open accepts in these tests unless one says otherwise: every warning `wlx taskd`
#: lists at an open on the stand-in rig, which names no calibration -- the default's, and a
#: chaired session's free head -- each as its code and its sentence (the engine B plan, call
#: 25). Accepting the chaired one for a head-fixed session is harmless: only what is offered
#: is asked for.
OPEN_ACCEPTED = tuple(
    entry.key
    for entry in warnlist.of_calibration(SRGB, date(2027, 1, 14))
    + warnlist.of_deployment(Deployment.RIG_CHAIRED)
)


def bounds(subject: str = "A", out_of_cage: float = 28_800.0) -> Bounds:
    """A bounded config: a reward entry, the out-of-cage ceiling, the daily floor."""
    return Bounds(
        subject=subject,
        ceilings={
            "reward_correct": Ceiling(value=0.15, maximum=0.40, unit="mL"),
            "out_of_cage": Ceiling(value=out_of_cage, maximum=100_000.0, unit="s"),
        },
        minima={"daily_fluid": Floor(value=250.0, unit="mL")},
    )


def session(
    tmp_path, *, deployment: Deployment = Deployment.RIG_CHAIRED, out_of_cage: float = 28_800.0
) -> Session:
    """Built and not opened: nothing is on disk until a mark or `open()` writes it.
    Rig-chaired by default, so no head-fixation stands between a test and a return."""
    made = Session(
        SessionSpec(
            task="tasks/fixation_detection.py",
            allocation="tasks/allocation.py",
            root=tmp_path,
            session_id="2027-01-14_01",
            subject="A",
            trials=3,
            frame_period=1 / 240,
            seed=1,
            values={},
            bounds=bounds(out_of_cage=out_of_cage),
            already_delivered_today=0.0,
            deployment=deployment,
            geometry=DIRECT,
            session_kind="training",
            calibration=SRGB,
        ),
        card=Card(),
        pump=Pump(),
    )
    made.wall_clock = lambda: WALL
    return made


def typed(seconds_before: float) -> str:
    """A time as a person types it, with its date and zone: `seconds_before` `WALL`
    (negative is after it)."""
    return datetime.fromtimestamp(WALL - seconds_before).astimezone().isoformat(
        timespec="seconds"
    )


def whole_point_task(folder: Path) -> Path:
    """A task `check()` itself raises on, written into `folder` as `whole_point.py`: the
    reference task with its target window placed at a whole-point parameter (a legal
    form) and a fixation break its target could overlap. `check`'s overlap test
    unpacks the window's place as a pair and raises `TypeError` (XC-156, filed on main,
    not fixed here): what a pre-flight must turn into a fail rather than pass on."""
    text = Path("tasks/fixation_detection.py").read_text()
    for old, new in (
        ('            "target",\n            at=(P("target_x"), P("target_y")),',
         '            "target",\n            at=P("target_point"),'),
        ('        Param("target_x", unit="deg", low=-16.0, high=16.0, start=10.0),',
         '        Param("target_x", unit="deg", low=-16.0, high=16.0, start=10.0),\n'
         '        Param("target_point", unit="deg", choices=((10.0, 0.0), (-10.0, 0.0))),'),
        ('                On(SaccadeTo("target"), "verify", do=[Mark(4098)]),',
         '                On(SaccadeTo("target"), "verify", do=[Mark(4098)]),\n'
         '                On(Exited("fix"), Outcome.FIXATION_BREAK),'),
    ):
        assert text.count(old) == 1, old
        text = text.replace(old, new)
    path = Path(folder) / "whole_point.py"
    path.write_text(text)
    return path


def malformed_task(folder: Path) -> Path:
    """A task whose declaration `values` could not compare against, written into `folder`
    as `malformed.py`: the reference task with `fix_hold`'s lower bound typed as text.
    `Param` does not check its fields and `check()` never compares a bound, so it loads
    and passes its checks -- and a starting value held against that bound raised
    `TypeError` out of the pre-flight (the b3a-1 final review, Important 1)."""
    text = Path("tasks/fixation_detection.py").read_text()
    old = 'Param("fix_hold", unit="s", low=0.05, high=2.0, start=0.3),'
    assert text.count(old) == 1, old
    path = Path(folder) / "malformed.py"
    path.write_text(text.replace(old, 'Param("fix_hold", unit="s", low="0.05", high=2.0, start=0.3),'))
    return path


def head_free_task(folder: Path) -> Path:
    """The reference detection task without its need for a fixed head, written into `folder` as
    `head_free.py`. Every reference task needs the head fixed since 2026-10-11 (the PI: "kiosk will
    be head free, in the rig will be head fixed. we do not have head tracking in the rig"; the
    engine C1 plan's Appendix B, item 31), and warns in a chaired or cage-side session
    (`head-not-fixed`, a warning since the PI's ruling of 2026-10-11); a test whose subject is one
    of those deployments, or a run of a session that keeps no head fixed between its runs, runs
    this copy instead, meeting no such warning; it differs from the reference task in that alone."""
    text = Path("tasks/fixation_detection.py").read_text()
    old = "    needs_fixed_head=True,\n"
    assert text.count(old) == 1, old
    path = Path(folder) / "head_free.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.replace(old, ""))
    return path


def polar_task(folder: Path, *, name: str = "polar") -> Path:
    """The reference detection task with its target placed by one setting, `target_pos`, whose
    choices are polar positions -- 8° out to the right and 8° out at 45° (`task.Polar`; the PI,
    2026-10-19, "Polar first, x-y allowed") -- written into `folder` as `NAME.py`. Engine test
    material, run only in the simulator: no reference task has such a setting."""
    text = Path("tasks/fixation_detection.py").read_text()
    for old, new in (
        ('"target", at=(P("target_x"), P("target_y")), looks=P("target_appearance")',
         '"target", at=P("target_pos"), looks=P("target_appearance")'),
        ('            at=(P("target_x"), P("target_y")),\n            radius=P("target_window"),',
         '            at=P("target_pos"),\n            radius=P("target_window"),'),
        ('        Param("target_x", unit="deg", low=-16.0, high=16.0, start=10.0),',
         '        Param("target_pos", unit="deg", choices=(Polar(8.0, 0.0), Polar(8.0, 45.0))),\n'
         '        Param("target_x", unit="deg", low=-16.0, high=16.0, start=10.0),'),
        ("from wl_xcon.task import (", "from wl_xcon.task import (\n    Polar,"),
    ):
        assert text.count(old) == 1, old
        text = text.replace(old, new)
    text += (
        "\n\nimport dataclasses as _polar_dataclasses\n"
        "from wl_xcon.task import NOT_DIFFICULTY, STIMULUS, Meaning\n"
        "TASK = _polar_dataclasses.replace(TASK, meanings={\n"
        "    **TASK.meanings,\n"
        "    'target_pos': Meaning(NOT_DIFFICULTY, STIMULUS, note='the target position'),\n"
        "})\n"
    )
    path = Path(folder) / f"{name}.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def planned_task(folder: Path, plans: str = "{}", *, name: str = "planned",
                 structures: str = "TASK.structures") -> Path:
    """The reference detection task with plans (engine build C2b), written into `folder` as
    `NAME.py`: `plans` is Python source for its plans dict, and `structures` for its structures
    dict, each free to name `detection`, its one trial structure, and every word of the plan
    vocabulary. Engine test material, run only in the simulator: no reference task declares a
    plan, since real plans are set with the PI in wl-xtasks."""
    text = Path("tasks/fixation_detection.py").read_text() + (
        "\n\nimport dataclasses as _dataclasses\n"
        "from wl_xcon.task import (\n"
        "    NO_LIMIT, SPENT, Balanced, Block, ByCriterion, Condition, Constrained, Cyclic,\n"
        "    Fixed, Plan, Random, WithReplacement,\n"
        ")\n"
        f"TASK = _dataclasses.replace(TASK, structures={structures}, plans={plans})\n"
    )
    path = Path(folder) / f"{name}.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def stimuli_task(folder: Path, *, name: str = "stimuli") -> Path:
    """The reference detection task showing three more stimuli beside its fixation point in
    `await_fix` -- `corner` at (20°, 20°), `oblique` at `Polar(10, 135)` and `ring`, an array of
    four 3° about (-8°, -6°) at phase 30° -- and moving `corner` to `Polar(12, -60)` as its target
    appears, written into `folder` as `NAME.py` (XC-399: where each shown stimulus was, on its
    trial's row). Engine test material, run only in the simulator; (20°, 20°) is past direct view's
    18.4° up at 50 cm, so the tests that run it view the panel from nearer."""
    text = Path("tasks/fixation_detection.py").read_text()
    shade = "color=Gray(P(\"fix_luminance\"))"
    for old, new in (
        ("from wl_xcon.task import (", "from wl_xcon.task import (\n    Array,\n    Polar,\n    Update,"),
        ("\ndetection = Trial(\n", (
            f'\nCORNER = Stimulus("corner", at=(20.0, 20.0), looks=Disc(size=0.3, {shade}))\n'
            f'OBLIQUE = Stimulus("oblique", at=Polar(10.0, 135.0), looks=Disc(size=0.3, {shade}))\n'
            f'RING = Stimulus("ring", at=(-8.0, -6.0), looks=Array(\n'
            f'    n=4, radius=3.0, phase=30.0, looks=Disc(size=0.5, {shade}),\n'
            f'    among=Disc(size=0.5, {shade})))\n'
            "\ndetection = Trial(\n")),
        ("            enter=[Show(FIX), Mark(4096)],",
         "            enter=[Show(FIX), Show(CORNER), Show(OBLIQUE), Show(RING), Mark(4096)],"),
        ("            enter=[Show(TARGET), Mark(4097)],",
         '            enter=[Show(TARGET), Update("corner", at=Polar(12.0, -60.0)), Mark(4097)],'),
    ):
        assert text.count(old) == 1, old
        text = text.replace(old, new)
    path = Path(folder) / f"{name}.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def cue_task(folder: Path, *, name: str = "cue") -> Path:
    """The reference detection task showing a cue beside its fixation point in `await_fix`, placed
    by a setting, `cue_pos`, whose choices are two polar positions and which declares no start, so
    a run that gives none leaves it without a value; no window is on the cue (the review of XC-399,
    I1, its probe). Engine test material, run only in the simulator."""
    text = Path("tasks/fixation_detection.py").read_text()
    for old, new in (
        ("from wl_xcon.task import (", "from wl_xcon.task import (\n    Polar,"),
        ("\ndetection = Trial(\n",
         '\nCUE = Stimulus("cue", at=P("cue_pos"), looks=Disc(size=0.5, color=Gray(P("fix_luminance"))))\n'
         "\ndetection = Trial(\n"),
        ("            enter=[Show(FIX), Mark(4096)],",
         "            enter=[Show(FIX), Show(CUE), Mark(4096)],"),
        ('        Param("target_x", unit="deg", low=-16.0, high=16.0, start=10.0),',
         '        Param("cue_pos", unit="deg", choices=(Polar(8.0, 0.0), Polar(8.0, 180.0))),\n'
         '        Param("target_x", unit="deg", low=-16.0, high=16.0, start=10.0),'),
    ):
        assert text.count(old) == 1, old
        text = text.replace(old, new)
    text += (
        "\n\nimport dataclasses as _cue_dataclasses\n"
        "from wl_xcon.task import NOT_DIFFICULTY, STIMULUS, Meaning\n"
        "TASK = _cue_dataclasses.replace(TASK, meanings={\n"
        "    **TASK.meanings, 'cue_pos': Meaning(NOT_DIFFICULTY, STIMULUS, note='a cue')})\n"
    )
    path = Path(folder) / f"{name}.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path
