"""Session-level fuzz of the engine, as engine build C3 left it (the engine C3 plan's Task 20,
`docs/superpowers/plans/2026-10-30-engine-c3.md`).

Written for engine build C2b and extended for C3 as a git-ignored script; tracked here since
2026-11-07 (the PI: "turn the welfare check and the fuzzer into tests in the repository"), and a
small part of it, a few sessions and controls, runs in the suite (`tests/test_fuzz_sessions.py`).
Random tasks run through `taskd.Session.run` with the simulated animal under a short
out-of-cage limit. Each task draws: every distribution (`Uniform`, `Weighted`, `TruncatedNormal`,
`Listed`, `NonAging`), from the task's draws, a block's own and a condition's own range, each
setting `same` or `fresh` on a repeat. Its plans make conditions from factors (`Factorial`) and
play designed orders (`SequenceBalanced`, `Priming`) beside C2b's. A person at random sets values
(some no animal could answer with, some a reward size), hands settings back, changes drawn ranges,
reverts, switches drumming and the training aids, clears trials, moves blocks, pauses (acting
while paused too) and stops. Each
session's record and its strobed stream, decoded and assembled by wl-preproc's own code, are
checked against C2b's invariants (I2-I22, kept) and the C3 spec §12's list (C1-C13). It tests
the tree it is in, and runs from that tree's root (the session's allocation is named relative to
it), refusing to run from anywhere else; wl-preproc is looked for beside the tree, then inside
it, as `tests/conftest.py` looks:

    cd <tree> && PYTHONHASHSEED=0 $PY tools/fuzz_sessions.py N [control] [start] [tmpdir]
    cd <tree> && PYTHONHASHSEED=0 $PY tools/fuzz_sessions.py replay N [control] [start] [tmpdir]

**The C3 spec §12's list, as checked here**:
- C1 (replay mode): one seed gives the same draws, order and repeats in two processes. Two child
  processes run each seed with one fixed `PYTHONHASHSEED` against a world scripted by trial
  number (the C3 plan's call 40), with the person's random acts, and must agree line for line.
- C2 (replay mode): adding a draw moves no condition or repeat. Each seed runs again in this
  process with the fixation point's luminance drawn as well, a setting no state reads, the person
  silent, against the same scripted world; its conditions, repeats and outcomes must not move.
- C3: every drawn value inside the range its line names: the task's draw, the block's own, the
  condition's own range, or the live range (change id) in force; a drawn direction from 0 to 360.
- C4: every non-aging wait between its shortest and longest.
- C5: a `same` setting on a repeat, drummed, again at once or ordinary, equals the original
  trial's value and names its source.
- C6: a sequence-balanced block's plan holds each pair (or triple) once in each cycle, each cycle
  the linear de Bruijn sequence of n**depth + depth - 1 places (the PI, 2026-10-31), cycled as
  declared, and every trial line's planned place names the condition it played and says whether
  it is its cycle's lead-in (its first depth - 1); places are played in order, a drum's try and a
  trial again at once keeping theirs.
- C7: a priming block's runs in range, every switch a change of value; each line's run, switch
  and value agree with the block's plan.
- C8: after a hand-back, no trial `live` or `overridden` for that setting: each trial's `live` is
  exactly the names a person holds by the change log, each at its held value, `overridden` among
  them.
- C9: after a range change, every fresh draw from that draw names it (its change id) until another
  change replaces it; with none in force, the declaration.
- C10: a revert restores the chosen moment's values (the latest moment at or before the change it
  names): what a person holds, at what values, and the ranges in force; never a bounded setting:
  no revert row names one, and every trial runs at the reward size the `set` rows give.
- C11: a trial kept out of moving up (`eased`) is never in its block's rule window and always in
  its fall-back window (its first answer); its line's `eased` agrees with what the scheduler was
  told.
- C12: no trial runs with a combination no animal can get right (`check.impossible` on the trial's
  own values), whatever the random changes. This task family can make the first of the three
  (a target hold at least the response deadline, the `verify` state's timeout reading the
  deadline); the other two, about an array's looks, are Tasks 5 and 11's tests'.
- C13: every strobed change row has `sequence`, 1, 2, ... in order, and no other row (a clear's, a
  drum or training switch's) has one; its
  code is `PARAM_CHANGED`, strobed once per row; wl-preproc reads the log with no problem and its
  join times the n-th such row at the n-th code, in the gap before its first trial; since
  wl-preproc's main 295f9c9 (2026-11-07) a row that strobed nothing is timed through its fit of
  the rig's clock (each run's rows and the coded rows against a recording that runs with the
  session's wall, `Recording`), in the same gap to within the fit's own limit; the session
  is resumable (`resume.read`, numbering on from the log) and `stranded.find` lists it resumable.

`control` is a negative control, each of which must report findings in the invariant named:
- `pid` (C1, replay): a draw's unit mixes in the process id.
- `shared` (C2, replay): the added draw also draws from the scheduler's own generator.
- `range` (C3): a uniform draw of the fixation hold or the deadline lands past its highest.
- `wait` (C4): a non-aging wait lands past its longest.
- `same` (C5): a `same` setting's repeat draws afresh.
- `debruijn` (C6): a sequence-balanced plan is its conditions in sorted order, no de Bruijn cycle.
- `planned` (C6): a sequence-balanced trial's planned place is written one ahead.
- `leadin` (C6): no sequence-balanced trial's place is marked its cycle's lead-in.
- `priming` (C7): a priming block's switch keeps the last run's value.
- `handback` (C8): a person's hand-back leaves the setting held.
- `rangesrc` (C9): a draw from a live range names its declaration.
- `revert` (C10): a revert's hand-backs are dropped.
- `bounded` (C10): a revert also sets the reward size.
- `eased` (C11): the scheduler is never told a trial was eased.
- `impossible` (C12): the live refusal of a combination no animal can get right is switched off.
- `sequence` (C13): a hand-back strobes no code.
- `resume` (C13): resume refuses a hand-back's row.
And C2b's, kept: `drum`, `stall`, `time`, `limit`, `opened`, `b2b`, `firstans`, `rundrum`,
`movecode`, `insession`, `polar`.

About a fifth of the tasks place the target by a setting of `Polar` choices that their conditions
set or a weighted set draws (`_sessions.polar_task`, C2b's I22), and about a fifth by an
eccentricity and a direction setting, the direction drawn in the task's own terms and written from
0 to 360 (the C3 plan's call 11).
"""

from __future__ import annotations

import dataclasses
import json
import os
import random
import subprocess
import sys
import tempfile
import time
import traceback
from collections import Counter, deque
from pathlib import Path

HERE = Path(__file__).resolve()
#: The tree this file is in, which is the tree it tests.
TREE = HERE.parents[1]
if Path.cwd().resolve() != TREE:
    raise SystemExit(f"run from the root of the tree this tests: cd {TREE}")
sys.path.insert(0, str(TREE))
sys.path.insert(0, str(TREE / "tests"))
#: Beside the tree (a laptop with both checkouts), then inside it (CI), as `tests/conftest.py`.
for _preproc in (TREE.parent / "wl-preproc", TREE / "wl-preproc"):
    if _preproc.is_dir():
        sys.path.insert(0, str(_preproc))
        break

import _sessions  # noqa: E402
from _rig import DIRECT  # noqa: E402
from wl_preproc.contracts.events import decode_stream  # noqa: E402
from wl_preproc.events.assemble import assemble  # noqa: E402
from wl_preproc.events.rigrecords import CHANGES_NAME, read_rig_records  # noqa: E402
from wl_preproc.events.rigruns import read_rig_runs  # noqa: E402
from wl_preproc.events.rigtiming import (  # noqa: E402
    RIG_CLOCK_LIMIT_S, code_times, run_instants, time_records,
)
from wl_xcon import record as Rec  # noqa: E402
from wl_xcon import resume as Resume_  # noqa: E402
from wl_xcon import scheduler as S  # noqa: E402
from wl_xcon import stranded  # noqa: E402
from wl_xcon import task as K  # noqa: E402
from wl_xcon import taskd as T  # noqa: E402
from wl_xcon import variation as V  # noqa: E402
from wl_xcon.actor import Box  # noqa: E402
from wl_xcon.bounds import Bounds, Ceiling, Floor  # noqa: E402
from wl_xcon.check import check_task, impossible  # noqa: E402
from wl_xcon.declarations import BOUNDED  # noqa: E402
from wl_xcon.dio import Simulated as Card  # noqa: E402
from wl_xcon.geometry import shown_direction  # noqa: E402
from wl_xcon.link import (  # noqa: E402
    BackBlock, ClearOwed, Drum, HandBack, NextBlock, Pause, Resume, Revert, SetParameter, SetRange,
    Simulated, Stop, Training,
)
from wl_xcon.photometry import SRGB  # noqa: E402
from wl_xcon.run import LONGEST_TRIAL_S, Scripted  # noqa: E402
from wl_xcon.task import (  # noqa: E402
    RIGHT, SAME, Balanced, Block, ByCriterion, Condition, Cyclic, Priming, Random, SaccadeTo,
    SequenceBalanced,
)
from wl_xcon.taskd import PAUSE_HOUSEKEEPING_S, Session, SessionSpec  # noqa: E402
from wl_xcon.welfare import Deployment, Simulated as Pump  # noqa: E402

WALL_NOW = 1_700_000_000.0
VALUES = {
    "fix_acquisition": 4.0, "fix_hold": 0.3, "response_deadline": 0.6, "target_hold": 0.2,
    "fix_window": 2.0, "target_window": 3.0, "target_x": 10.0, "target_y": 0.0,
    "target_appearance": None, "fix_luminance": 40.0, "target_luminance": 40.0,
}
PASS_BUDGET = 20_000
WHO = Box("fuzz")
STRUCTURES = ('{"detection": detection, "spent": _dataclasses.replace(detection, counting='
              '_dataclasses.replace(detection.counting, after_stimulus=SPENT, cap=2))}')
ENDED = ("rule", "time", "fall_back", "next", "back", "run_time", "run")
#: `PARAM_CHANGED`'s code in the reference allocation.
PARAM_CHANGED = 4130
#: The reward size a session starts with (`bounds` below).
REWARD = 0.15
APPEARANCES = ('(Disc(size=1.0, color=Gray(P("target_luminance"))), '
               'Square(size=1.0, color=Gray(P("target_luminance"))))')
#: What a task may draw, by setting, each distribution's source without its `repeat`.
DRAWABLE = {
    "fix_hold": ["Uniform(0.2, 0.4", "NonAging(0.2, 0.3, 0.5",
                 "TruncatedNormal(0.3, 0.05, low=0.2, high=0.45"],
    "response_deadline": ["Uniform(0.5, 1.0", "NonAging(0.5, 0.7, 1.2"],
    "target_y": ["TruncatedNormal(0.0, 4.0", "Uniform(-3.0, 3.0"],
    "fix_luminance": ["Uniform(20.0, 60.0", "Weighted((20.0, 40.0, 60.0), (1, 2, 1)"],
    "target_luminance": ["Uniform(20.0, 60.0", "Listed((25.0, 35.0, 45.0)"],
    "fix_window": ["Weighted((1.5, 2.0, 2.5), (1, 2, 1)"],
    "target_appearance": ["Listed(" + APPEARANCES],
}
PLAIN_DRAWS = {"target_x": ["Uniform(-12.0, 12.0", "Weighted((-10.0, 10.0), (1, 1)",
                            "Listed((-10.0, 0.0, 10.0)"]}
DIRECTED_DRAWS = {"target_dir": ["Uniform(-45.0, 45.0", "Uniform(0.0, 360.0",
                                 "Weighted((-90.0, 0.0, 90.0), (1, 1, 1)"],
                  "target_ecc": ["Uniform(4.0, 10.0"]}
POLAR_DRAWS = {"target_pos": ["Weighted((Polar(8.0, 0.0), Polar(8.0, 45.0)), (1, 1)"]}
#: What a person types live, by setting: some outside the declared range, some no animal could
#: answer with (a target hold at least the deadline).
LIVE = {
    "fix_hold": (0.1, 0.25, 0.3, 0.5, 0.8),
    "target_hold": (0.1, 0.2, 0.4, 0.7, 0.9),
    "response_deadline": (0.3, 0.6, 0.9, 1.5),
    "fix_window": (1.0, 2.0, 3.5),
    "target_window": (2.0, 3.0, 4.5),
    "target_y": (-4.0, 0.0, 4.0),
    "fix_luminance": (20.0, 50.0),
    "target_luminance": (25.0, 55.0),
}
LIVE_FAMILY = {"plain": {"target_x": (-10.0, 5.0, 12.0)},
               "directed": {"target_dir": (-30.0, 45.0, 270.0), "target_ecc": (6.0, 9.0)},
               "polar": {}}
#: The setting C2 adds a draw of, which no state reads, so the generator leaves it alone in
#: replay mode.
SPARE = "fix_luminance"
DEADLINE = ("                On(After(3.0), Outcome.NO_RESPONSE),",
            '                On(After(P("response_deadline")), Outcome.NO_RESPONSE),')


class Wall:
    def __init__(self):
        self.extra = 0.0
        self.follow = lambda: 0.0

    def __call__(self):
        return WALL_NOW + self.follow() + self.extra


#: How far after the code before it a code sent at the same instant is placed in the recording.
WORD_S = 1e-6


@dataclasses.dataclass
class Recording(Card):
    """The simulated card, each code timed as it is sent, on the session's wall less `WALL_NOW`:
    the recording C13 reads. A real rig's acquisition records on a clock that runs with the rig's,
    and since wl-preproc's main 295f9c9 (2026-11-07) a change row that strobed nothing is timed
    through a fit of the rig's instants to the recording; so the simulated recording runs with the
    simulated wall, which follows the session's frames and a pause's waits. A code sent at the
    same instant as the one before is placed `WORD_S` after it, so the recording reads in order."""

    wall: object = None
    times: list = dataclasses.field(default_factory=list)

    def emit(self, code):
        super().emit(code)
        at = self.wall() - WALL_NOW
        if self.times and at <= self.times[-1]:
            at = self.times[-1] + WORD_S
        self.times.append(at)


class Link(Simulated):
    """Random person commands at boundaries; pauses move the wall. A live act -- a value, a
    hand-back, a range, a revert, a reward size, a drum switch, a training switch, a clear -- with
    `p_live`, and while paused."""

    def __init__(self, rng, wall, p_move, p_pause, p_stop, p_live, family):
        super().__init__()
        self.rng, self.wall = rng, wall
        self.p_move, self.p_pause, self.p_stop, self.p_live = p_move, p_pause, p_stop, p_live
        self.values = {**LIVE, **LIVE_FAMILY[family]}
        self.session = None
        self.drains = 0
        self.waits = 0
        self.paused = False
        self.sent = Counter()

    def live(self):
        """One live act, built from what the session holds now, or `None`."""
        s, rng = self.session, self.rng
        try:
            task, block = s._task, s._scheduler.block
        except AttributeError:
            return None
        if task is None:
            return None
        r = rng.random()
        if r < 0.36:
            name = rng.choice(sorted(self.values))
            return SetParameter(name=name, value=rng.choice(self.values[name]), by=WHO)
        if r < 0.50:
            held = sorted(s._edited)
            name = (rng.choice(held) if held and rng.random() < 0.85
                    else rng.choice(sorted(self.values)))
            return HandBack(name=name, by=WHO)
        if r < 0.68:
            force = V.in_force(task, block)
            if not force:
                return None
            name = rng.choice(sorted(force))
            drawn, key = force[name]
            current = s._ranges.get(key, (drawn,))[0]
            numbers = V.numbers(current)
            if numbers is None:
                return SetRange(name=name, numbers={"low": 0.0}, by=WHO)
            return SetRange(name=name, numbers=jittered(rng, numbers), by=WHO)
        if r < 0.84:
            return Revert(change=rng.randint(0, s._change + 1), by=WHO)
        if r < 0.90:
            return SetParameter(name="reward_correct", value=rng.choice((0.1, 0.2, 0.3)), by=WHO)
        if r < 0.94:
            return Drum(scope=rng.choice(("block", "run", "off")), by=WHO)
        if s._scheduler.clearing and rng.random() < 0.7:
            # A clear, once the training aid allows one (some refused, owing nothing).
            names = [condition.name for condition in block.conditions]
            return ClearOwed(condition=rng.choice(names), by=WHO, rest=rng.random() < 0.3)
        return Training(setting=rng.choice(("clear", "clear", "first_answers")),
                        on=rng.random() < 0.7, by=WHO)

    def act(self, where):
        command = self.live()
        if command is not None:
            self.queue(command)
            self.sent[type(command).__name__ + where] += 1

    def drain(self):
        self.drains += 1
        if self.drains > PASS_BUDGET:
            raise RuntimeError(f"SPIN: drained {PASS_BUDGET} times")
        r = self.rng.random()
        if not self.paused:
            if r < self.p_move:
                cmd = (NextBlock if self.rng.random() < 0.6 else BackBlock)(by=WHO)
                self.queue(cmd)
                self.sent[type(cmd).__name__] += 1
            elif r < self.p_move + self.p_pause:
                self.queue(Pause(by=WHO))
                self.paused = True
                self.sent["Pause"] += 1
            elif r < self.p_move + self.p_pause + self.p_stop:
                self.queue(Stop(by=WHO))
                self.sent["Stop"] += 1
            if self.rng.random() < self.p_live:
                self.act("")
                if self.rng.random() < 0.3:
                    self.act("")
        return super().drain()

    def idle(self, timeout):
        self.waits += 1
        if self.waits > PASS_BUDGET:
            raise RuntimeError("SPIN: paused forever")
        self.wall.extra += self.rng.choice([1.0, 5.0, 30.0])
        r = self.rng.random()
        if r < 0.15:
            cmd = (NextBlock if self.rng.random() < 0.6 else BackBlock)(by=WHO)
            self.queue(cmd)
            self.sent[type(cmd).__name__ + "@paused"] += 1
        elif r < 0.6:
            self.queue(Resume(by=WHO))
            self.paused = False
        if self.p_live and self.rng.random() < 0.3:
            self.act("@paused")
        return super().idle(timeout)


def jittered(rng, numbers):
    """A person's numbers for a live range near `numbers`: each moved by up to half the span, now
    and then two swapped, which cannot be drawn and is refused."""
    span = max(numbers.values()) - min(numbers.values()) or 1.0
    out = {name: round(value + span * rng.uniform(-0.5, 0.5), 3) for name, value in numbers.items()}
    if "sd" in out:
        out["sd"] = round(abs(numbers["sd"]) * rng.uniform(0.5, 1.5), 3)
    if rng.random() < 0.1 and len(out) >= 2:
        first, second = rng.sample(sorted(out), 2)
        out[first], out[second] = out[second], out[first]
    return out


def rule(rng):
    return f"({rng.choice([0.5, 0.8, 1.0])}, {rng.randint(1, 6)})"


def repeat(rng):
    return rng.choice(["SAME", "FRESH"])


def placed(rng, family, setting=None):
    """A condition's value of `setting` (by default the target's place), and the setting."""
    setting = setting or {"polar": "target_pos", "directed": "target_dir",
                          "plain": "target_x"}[family]
    return setting, {
        "target_pos": lambda: f'Polar(8.0, {rng.choice(["0.0", "45.0"])})',
        "target_dir": lambda: rng.choice(["0.0", "90.0", "180.0", "270.0", "-90.0"]),
        "target_ecc": lambda: rng.choice(["6.0", "8.0", "10.0"]),
        "target_luminance": lambda: rng.choice(["30.0", "45.0", "60.0"]),
        "target_x": lambda: str(rng.choice([5.0, 12.0, 8.0, -10.0])),
    }[setting]()


def given_setting(rng, family, drawn):
    """What a block's conditions give: the target's place, or, now and then, so that the place is
    drawn there, its eccentricity or its luminance (where a draw gives a polar task's place)."""
    if family == "directed":
        return rng.choice(["target_dir", "target_ecc", "target_luminance"])
    if family == "polar":
        return ("target_luminance" if "target_pos" in drawn and rng.random() < 0.5
                else "target_pos")
    return rng.choice(["target_x", "target_x", "target_luminance"])


def own_range(rng, family):
    """A condition's own range, and the setting it draws."""
    if family == "directed" and rng.random() < 0.5:
        return "target_dir", f"Uniform(-30.0, 30.0, repeat={repeat(rng)})"
    return "target_y", f"Uniform(-2.0, 2.0, repeat={repeat(rng)})"


def gen_conditions(rng, n, family, drawn):
    """`n` ordinary conditions (C2b's, with a condition's own range now and then): their sources
    and the settings they give."""
    conds, given = [], set()
    setting = given_setting(rng, family, drawn)
    for j in range(n):
        name, value = placed(rng, family, setting)
        values = {name: value}
        if rng.random() < 0.2:
            ranged, drawn = own_range(rng, family)
            values = {ranged: drawn} if ranged == name else {**values, ranged: drawn}
        given |= set(values)
        st = ', structure="spent"' if rng.random() < 0.25 else ""
        body = ", ".join(f'"{k}": {v}' for k, v in values.items())
        conds.append(f'Condition("c{j}", {{{body}}}, target={rng.randint(0, 4)}{st})')
    return conds, given


def block_draws(rng, given, drawn, spare):
    """A block's own draws: `BY_CONDITIONS` for each setting its conditions give that the task
    draws, and now and then a draw of its own of one they do not give."""
    entries = {name: "BY_CONDITIONS" for name in sorted(given & drawn)}
    if rng.random() < 0.25:
        options = [name for name in ("fix_hold", "target_luminance", "response_deadline")
                   if name not in given and name != spare]
        if options:
            name = rng.choice(options)
            source = {"fix_hold": "Uniform(0.3, 0.5", "target_luminance": "Uniform(30.0, 50.0",
                      "response_deadline": "NonAging(0.6, 0.8, 1.1"}[name]
            entries[name] = f"{source}, repeat={repeat(rng)})"
    if not entries:
        return ""
    return ", draws={" + ", ".join(f'"{k}": {v}' for k, v in entries.items()) + "}"


def gen_block(rng, i, family, drawn, spare, top):
    kind = rng.random()
    if kind < 0.12 and not top:
        return gen_balanced(rng, i, family, drawn, spare)
    if kind < 0.22:
        return gen_priming(rng, i, family, drawn, spare)
    if kind < 0.34:
        return gen_factorial(rng, i, family, drawn, spare)
    conds, given = gen_conditions(rng, rng.randint(1, 3), family, drawn)
    kw = []
    if rng.random() < 0.35:
        kw.append(f"criterion={rule(rng)}")
    if rng.random() < 0.25:
        kw.append(f"trials={rng.randint(1, 8)}")
    if rng.random() < 0.3:
        kw.append(f"time_limit_s={rng.choice([5.0, 15.0, 40.0])}")
    if rng.random() < 0.3:
        kw.append("drum=True")
    if rng.random() < 0.15:
        weights = '{"c0": 0.0}' if rng.random() < 0.3 else "{}"
        kw.append(f"order=WithReplacement(weights={weights})")
    elif rng.random() < 0.15:
        kw.append("order=Constrained(max_run=1)")
    r = rng.random()
    if r < 0.12:
        kw.append(f"counting=_dataclasses.replace(detection.counting, appears=None, "
                  f"withholding=False, cap={rng.choice(['NO_LIMIT', '1', '3'])})")
    elif r < 0.24:
        # A hold-training block: its own table scores a broken hold, judged both ways.
        kw.append('counting=_dataclasses.replace(detection.counting, appears=None, '
                  'withholding=False, outcomes={"fixation_break": "counted"})')
    draws = block_draws(rng, given, drawn, spare)
    return f'Block("b{i}", [{", ".join(conds)}]{"".join(", " + k for k in kw)}{draws})'


def gen_balanced(rng, i, family, drawn, spare):
    """A sequence-balanced block: 2 or 3 conditions apart in their place, depth 2 (3 for two),
    each owing exactly what its cycles play; now and then cut by a number of trials or a time."""
    # A polar task's place offers two positions only.
    n = 2 if family == "polar" else rng.choice([2, 2, 3])
    depth = 3 if n == 2 and rng.random() < 0.3 else 2
    cycles = rng.choice([1, 1, 2])
    setting, places = {"polar": ("target_pos", ["Polar(8.0, 0.0)", "Polar(8.0, 45.0)",
                                               "Polar(8.0, 90.0)"]),
                       "directed": ("target_dir", ["0.0", "90.0", "180.0"]),
                       "plain": ("target_x", ["-10.0", "5.0", "12.0"])}[family]
    target = cycles * n ** (depth - 1)
    conds = [f'Condition("s{j}", {{"{setting}": {places[j]}}}, target={target})' for j in range(n)]
    kw = [f"order=SequenceBalanced(depth={depth}, cycles={cycles}, "
          f"again_at_once={rng.random() < 0.4})"]
    if rng.random() < 0.2:
        kw.append(f"trials={rng.randint(2, (n ** depth + depth - 1) * cycles)}")
    if rng.random() < 0.2:
        kw.append(f"time_limit_s={rng.choice([5.0, 15.0])}")
    if rng.random() < 0.25:
        kw.append("drum=True")
    draws = block_draws(rng, {setting}, drawn, spare)
    return f'Block("b{i}", [{", ".join(conds)}], {", ".join(kw)}{draws})'


def gen_priming(rng, i, family, drawn, spare):
    """A priming block on the target's luminance or place: 2 to 4 conditions, at least two values,
    targets 0, a number of trials or a time limit; by chance or by runs."""
    if rng.random() < 0.5:
        setting, values = "target_luminance", ["30.0", "60.0", "45.0"]
    else:
        setting, values = {"polar": ("target_pos", ["Polar(8.0, 0.0)", "Polar(8.0, 45.0)"]),
                           "directed": ("target_dir", ["0.0", "180.0"]),
                           "plain": ("target_x", ["-10.0", "10.0"])}[family]
    n = rng.randint(2, 4)
    # A polar task's target has no place unless its conditions or a draw give one.
    also = (', "target_pos": Polar(8.0, 0.0)' if family == "polar" and setting != "target_pos"
            else "")
    conds = [f'Condition("p{j}", {{"{setting}": {values[j % len(values)]}{also}}}, target=0)'
             for j in range(n)]
    how = (f"chance={rng.choice([0.0, 0.5, 0.8, 1.0])}" if rng.random() < 0.5
           else f"runs={rng.choice(['(1, 3)', '(2, 4)', '(3, 3)'])}")
    kw = [f'order=Priming("{setting}", {how}, again_at_once={rng.random() < 0.4})']
    if rng.random() < 0.7:
        kw.append(f"trials={rng.randint(4, 14)}")
    else:
        kw.append(f"time_limit_s={rng.choice([5.0, 15.0])}")
    if rng.random() < 0.2:
        kw.append("drum=True")
    given = {setting} | ({"target_pos"} if also else set())
    draws = block_draws(rng, given, drawn, spare)
    return f'Block("b{i}", [{", ".join(conds)}], {", ".join(kw)}{draws})'


def gen_factorial(rng, i, family, drawn, spare):
    """A factorial block: two factors, one now and then levelled by ranges of its own, an exclusion
    now and then, a hand-listed condition now and then."""
    place, places = {"polar": ("target_pos", "(Polar(8.0, 0.0), Polar(8.0, 45.0))"),
                     "directed": ("target_dir", "(0.0, 180.0)"),
                     "plain": ("target_x", "(-10.0, 10.0)")}[family]
    factors = {place: places}
    if rng.random() < 0.5:
        factors["target_luminance"] = "(30.0, 60.0)"
    else:
        factors["target_y"] = (f"(Uniform(-2.0, 0.0, repeat={repeat(rng)}), "
                               f"Uniform(0.0, 2.0, repeat={repeat(rng)}))")
    source = ", ".join(f'"{k}": {v}' for k, v in factors.items())
    extra = ""
    if rng.random() < 0.3 and "target_luminance" in factors:
        first = places.strip("()").split(", ")[0]
        if family == "polar":
            first = "Polar(8.0, 0.0)"
        extra = f', exclude=({{"{place}": {first}, "target_luminance": 30.0}},)'
    target = rng.randint(1, 2)
    listed = ""
    given = set(factors)
    if rng.random() < 0.25:
        name, value = placed(rng, family)
        listed = f'Condition("hand", {{"{name}": {value}}}, target=1)'
        given.add(name)
    kw = []
    if rng.random() < 0.3:
        kw.append(f"criterion={rule(rng)}")
    if rng.random() < 0.25:
        kw.append("drum=True")
    draws = block_draws(rng, given, drawn, spare)
    return (f'Block("b{i}", [{listed}], factorial=Factorial({{{source}}}{extra}, '
            f'target={target}){"".join(", " + k for k in kw)}{draws})')


def gen_draws(rng, family, spare):
    """The task's draws: each drawable setting with a chance, its distribution and repeat."""
    placing = {"plain": PLAIN_DRAWS, "directed": DIRECTED_DRAWS, "polar": POLAR_DRAWS}[family]
    pool = {**DRAWABLE, **placing}
    draws = {}
    for name in sorted(pool):
        if name != spare and rng.random() < (0.6 if name in placing else 0.3):
            draws[name] = f"{rng.choice(pool[name])}, repeat={repeat(rng)})"
    return draws


def gen_plan(rng, family, drawn, spare):
    n = rng.randint(1, 4)
    kind = rng.choice(["Fixed", "Cyclic", "Balanced", "Random", "ByCriterion"])
    blocks = [gen_block(rng, i, family, drawn, spare, top=kind == "ByCriterion" and i == n - 1)
              for i in range(n)]
    if rng.random() < 0.06:
        blocks = [f'Block("b{i}", [Condition("c0", {{}}, target=0)])' for i in range(n)]
        kind = rng.choice(["Cyclic", "Balanced", "Random"])
        return kind, f'{{"p": Plan([{", ".join(blocks)}], order={kind}(None), time_limit_s=None)}}'
    if kind == "Fixed":
        order = "Fixed()"
    elif kind == "Cyclic":
        order = f"Cyclic({rng.choice(['None', '1', '2', '3'])})"
    elif kind in ("Balanced", "Random"):
        order = f"{kind}({rng.choice(['None', str(n), str(2 * n + 1), '5'])})"
    else:
        order = f"ByCriterion({rng.choice(['None', rule(rng), rule(rng)])})"
    limit = rng.choice(["None", "None", "60.0", "200.0"])
    return kind, f'{{"p": Plan([{", ".join(blocks)}], order={order}, time_limit_s={limit})}}'


def directed(path):
    """The task at `path` with its target placed by eccentricity and direction, `target_ecc`
    (8°) and `target_dir`, declared from -180 to 180 and starting at 0 (as Task 7's
    `tests/test_draws_in_runs._directed`)."""
    text = path.read_text()
    for old, new in (
        ('"target", at=(P("target_x"), P("target_y")), looks=P("target_appearance")',
         '"target", at=Polar(P("target_ecc"), P("target_dir")), looks=P("target_appearance")'),
        ('            at=(P("target_x"), P("target_y")),\n            radius=P("target_window"),',
         '            at=Polar(P("target_ecc"), P("target_dir")),\n'
         '            radius=P("target_window"),'),
        ('        Param("target_x", unit="deg", low=-16.0, high=16.0, start=10.0),',
         '        Param("target_ecc", unit="deg", low=0.0, high=16.0, start=8.0),\n'
         '        Param("target_dir", unit="deg", low=-180.0, high=180.0, start=0.0),\n'
         '        Param("target_x", unit="deg", low=-16.0, high=16.0, start=10.0),'),
    ):
        assert text.count(old) == 1, old
        text = text.replace(old, new)
    text = text.replace("from wl_xcon.task import (", "from wl_xcon.task import (\n    Polar,", 1)
    text += (
        "from wl_xcon.task import NOT_DIFFICULTY, STIMULUS, Meaning\n"
        "TASK = _dataclasses.replace(TASK, meanings={\n"
        "    **TASK.meanings,\n"
        "    'target_ecc': Meaning(NOT_DIFFICULTY, STIMULUS, note='how far out the target is'),\n"
        "    'target_dir': Meaning(NOT_DIFFICULTY, STIMULUS, note='which way the target is'),\n"
        "})\n"
    )
    path.write_text(text)


def task_file(tmp, rng, family, draws, plans):
    """The fuzzed task, written into `tmp`: `varied_task` (or `polar_task` with the C3 vocabulary)
    with `draws` and `plans`, its `verify` state's timeout reading the response deadline, so a
    target hold at least the deadline leaves no time to answer (XC-343's first combination)."""
    source = "{" + ", ".join(f'"{k}": {v}' for k, v in draws.items()) + "}"
    if family == "polar":
        path = _sessions.polar_task(tmp, name="fuzzed")
        path.write_text(path.read_text() + (
            "\nfrom wl_xcon.task import (\n"
            "    BY_CONDITIONS, FRESH, NO_LIMIT, SAME, SPENT, Balanced, Block, ByCriterion,\n"
            "    Condition, Constrained, Cyclic, Factorial, Fixed, Listed, NonAging, Plan,\n"
            "    Priming, Random, SequenceBalanced, TruncatedNormal, Uniform, Weighted,\n"
            "    WithReplacement,\n"
            ")\n"
            "_dataclasses = _polar_dataclasses\n"
            f"TASK = _dataclasses.replace(TASK, structures={STRUCTURES}, plans={plans}, "
            f"draws={source})\n"))
    else:
        path = _sessions.varied_task(tmp, draws=source, plans=plans, name="fuzzed",
                                     structures=STRUCTURES)
        if family == "directed":
            directed(path)
    text = path.read_text()
    assert text.count(DEADLINE[0]) == 1
    path.write_text(text.replace(*DEADLINE))
    return path


CURRENT = {}
#: How often each C3 invariant was met with something to judge, across the sessions run.
EXERCISED = Counter()
CLOSES = []
DRAWS = []
FALL_BACK_BAD = []
EASED = {}
EASED_BAD = []
RAN = []
_orig_close = S.Scheduler.close
_orig_next = S.Scheduler.next_trial
_orig_record = S.Scheduler.record
_orig_advance = S.Scheduler.advance
_orig_run_trial = T.run_trial


def _close(self, reason, by=None):
    if not self.closed and "s" in CURRENT:
        sess = CURRENT["s"]
        CLOSES.append((self.block.name, reason, self.block.time_limit_s,
                       sess._elapsed - sess._block_from, self._drum is not None))
        if reason == "fall_back":
            # The shadow window: each trial's first judged answer in this block, kept apart from
            # the scheduler's own `_back`, which a fall-back must agree with.
            proportion, window = self.order.fall_back
            last = list(getattr(self, "_shadow", ()))[-window:]
            if len(last) < window or sum(last) / len(last) >= proportion:
                FALL_BACK_BAD.append((self.block.name, last, (proportion, window)))
    return _orig_close(self, reason, by)


def _next(self):
    if "s" in CURRENT:
        sess = CURRENT["s"]
        DRAWS.append((sess._elapsed - sess._run_from, sess._elapsed - sess._block_from,
                      self.block.time_limit_s, self._drum is not None))
    return _orig_next(self)


def _record(self, condition, outcome, shown=True, eased=False, hardest=True):
    first_try = self.drawn is None or not self.drawn.drummed
    judged = self._answer(outcome, condition) or self._scored(outcome)
    if not hasattr(self, "_shadow"):
        self._shadow, self._shadow_answered = deque(), False
    if first_try:
        self._shadow_answered = False
    first = judged and not self._shadow_answered
    if first:
        self._shadow.append(1 if outcome in RIGHT else 0)
    self._shadow_answered = self._shadow_answered or judged
    # C11: what the rule window and the fall-back window held before this trial.
    window, back = list(self._window), list(self._back)
    told = False if CONTROL == "eased" else eased
    kind = _orig_record(self, condition, outcome, shown, told, hardest)
    if self.drawn is not None:
        EASED[self.drawn.number] = bool(eased)
    if eased and judged:
        EXERCISED["C11 eased trials judged"] += 1
        if list(self._window) != window:
            EASED_BAD.append(f"C11 eased trial {self.drawn.number} entered block "
                             f"{self.block.name}'s rule window")
        if first:
            expected = deque(back, maxlen=self._back.maxlen)
            expected.append(1 if outcome in RIGHT else 0)
            if list(self._back) != list(expected):
                EASED_BAD.append(f"C11 eased trial {self.drawn.number} missing from block "
                                 f"{self.block.name}'s fall-back window")
    if CONTROL == "firstans" and judged and not first:
        self._back.append(1 if outcome in RIGHT else 0)
    return kind


def _advance(self, reason="rule", by=None):
    kept = set(self._opened)
    out = _orig_advance(self, reason, by)
    self._shadow, self._shadow_answered = deque(), False
    if CONTROL == "opened" and reason in ("next", "back"):
        self._opened |= kept
    return out


def _run_trial(trial, world, frame_period, *, values, **kwargs):
    if "s" in CURRENT:
        RAN.append((dict(values), CURRENT["s"].spec.bounds.ceilings["reward_correct"].value))
    return _orig_run_trial(trial, world, frame_period, values=values, **kwargs)


S.Scheduler.close = _close
S.Scheduler.next_trial = _next
S.Scheduler.record = _record
S.Scheduler.advance = _advance
T.run_trial = _run_trial
CONTROL = None


def rows(path):
    return [json.loads(x) for x in path.read_text().splitlines()] if path.exists() else []


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def written(value):
    """`value` as a trial line writes it, read back from JSON."""
    if not isinstance(value, (int, float, str, bool, type(None))):
        value = Rec._written(value)
    return json.loads(json.dumps(value))


def rebuilt(recorded):
    """A distribution from its recorded form (`variation.recorded`), a live range's."""
    fields = {k: tuple(v) if isinstance(v, list) else v for k, v in recorded["fields"].items()}
    return getattr(K, recorded["class"])(**fields)


def inside(dist, value, declared, direction):
    """Whether `value`, as a trial line writes it, is one `dist` can give."""
    if isinstance(dist, (K.Weighted, K.Listed)):
        can = [written(item) for item in V.values_of(dist)]
        if direction:
            can = [shown_direction(item) if number(item) else item for item in can]
        return value in can
    ends = V.bounds_of(dist, declared)
    if ends is None or not number(value):
        return False
    low, high = ends
    if direction:
        return 0 <= value < 360 and any(low - 1e-9 <= value + 360 * k <= high + 1e-9
                                        for k in (-2, -1, 0, 1))
    return low - 1e-12 <= value <= high + 1e-12


def keyed(row):
    return ("task", row["name"]) if row["from"] == "task" else ("block", row["block"], row["name"])


class Ledger:
    """What the change log says a person holds and what ranges are in force, act by act, with the
    moments a revert goes back to (C8-C10)."""

    def __init__(self, bounded):
        self.bounded = bounded
        self.held, self.ranges, self.dists = {}, {}, {}
        self.reward = REWARD
        self.moments = [(0, {}, {})]
        #: Settings handed back, by a button or a revert, and not held since (C8).
        self.handed = set()

    def state(self):
        return dict(self.held), {key: dist for key, (dist, _) in self.ranges.items()}

    def apply(self, act, findings):
        kind, change = act[0]["kind"], act[0]["change"]
        if kind in ("clear", "drum", "training"):
            return
        if kind == "set":
            (row,) = act
            if row["name"] in self.bounded:
                self.reward = row["now"]
                EXERCISED["C10 reward sizes set"] += 1
                return
            self.held[row["name"]] = row["now"]
        elif kind == "hand_back":
            self.held.pop(act[0]["name"], None)
            self.handed.add(act[0]["name"])
        elif kind == "range":
            key = keyed(act[0])
            self.ranges[key] = (act[0]["now"], change)
            self.dists[(change, key)] = act[0]["now"]
        elif kind == "revert":
            moment = act[0]["moment"]
            then = next(m for m in reversed(self.moments) if m[0] <= moment)
            EXERCISED["C10 reverts checked against their moment"] += 1
            for row in act:
                if row["name"] in self.bounded:
                    findings.append(f"C10 revert {change} names the bounded {row['name']}")
                    continue
                if "from" in row:
                    key = keyed(row)
                    if key in then[2]:
                        self.ranges[key] = (row["now"], change)
                        self.dists[(change, key)] = row["now"]
                    else:
                        self.ranges.pop(key, None)
                elif row["now"] is None:
                    self.held.pop(row["name"], None)
                    self.handed.add(row["name"])
                else:
                    self.held[row["name"]] = row["now"]
            held, ranges = self.state()
            if (held, ranges) != (then[1], then[2]):
                findings.append(f"C10 revert {change} to {moment} holds {held} {ranges}, "
                                f"moment {then[0]} held {then[1]} {then[2]}")
        else:
            findings.append(f"C13 unknown kind {kind!r}")
            return
        self.moments.append((change, *self.state()))


def acts(changes):
    """The change log's rows, one list per act (rows of one change id, in order)."""
    out = []
    for row in changes:
        if out and out[-1][0]["change"] == row["change"]:
            out[-1].append(row)
        else:
            out.append([row])
    return out


def c3_checks(task, session, trials, changes, card, d, root):
    """The C3 spec §12's invariants C3-C13 over one session's record."""
    findings = []
    bounded = set(BOUNDED) | set(session.spec.bounds.ceilings)
    declared = {param.name: param for param in task.params}
    turned = V.directions(task)
    blocks = {block.name: V.expanded(block) for block in task.plans["p"].blocks}
    by_index = {line["index"]: line for line in trials}
    ledger = Ledger(bounded)
    grouped, at = acts(changes), 0
    if len(RAN) != len(trials):
        findings.append(f"C10 {len(RAN)} trials ran, {len(trials)} lines")
    for line, (values, reward) in zip(trials, RAN):
        while at < len(grouped) and grouped[at][0]["trial_number"] <= line["trial_number"]:
            ledger.apply(grouped[at], findings)
            at += 1
        n = line["trial_number"]
        ledger.handed -= set(ledger.held)
        EXERCISED["C8 trials after a hand-back"] += bool(ledger.handed)
        EXERCISED["C12 trials judged"] += 1
        # C8: live is exactly who holds what, by the change log.
        if line["live"] != sorted(ledger.held):
            findings.append(f"C8 trial {n} live {line['live']} but held {sorted(ledger.held)}")
        for name, value in ledger.held.items():
            if line["params"].get(name) != value:
                findings.append(f"C8 trial {n} {name} {line['params'].get(name)!r} held {value!r}")
        if not set(line["overridden"]) <= set(line["live"]):
            findings.append(f"C8 trial {n} overridden {line['overridden']} not live")
        # C10: the reward size the set rows give.
        if reward != ledger.reward:
            findings.append(f"C10 trial {n} ran at reward {reward}, the log gives {ledger.reward}")
        # C12: no trial no animal can get right.
        if impossible_ran(task, values):
            findings.append(f"C12 trial {n} ran with target_hold {values.get('target_hold')} "
                            f"and response_deadline {values.get('response_deadline')}")
        block = blocks[line["block"]]
        condition = next(c for c in block.conditions if c.name == line["condition"])
        draws = {**V.in_force(task, block), **V.own_ranges(condition)}
        original = by_index.get(line["repeat_of"]) if line["repeat_of"] is not None else None
        for name, source in line["drawn"].items():
            if name not in draws:
                findings.append(f"C3 trial {n} drew {name}, which no draw in force gives")
                continue
            declaration, key = draws[name]
            value = line["params"][name]
            kept = (original is not None and declaration.repeat == SAME
                    and name in original["drawn"])
            EXERCISED["C3 drawn values"] += 1
            EXERCISED["C3 drawn directions"] += name in turned
            if kept:
                EXERCISED["C5 same values on repeats"] += 1
                EXERCISED["C5 ... on a drum's try"] += bool(line["drummed"])
                # C5: the original's value and source.
                if value != original["params"][name] or source != original["drawn"][name]:
                    findings.append(f"C5 trial {n} {name} {value!r} from {source!r}; its original "
                                    f"{original['trial_number']} {original['params'][name]!r} from "
                                    f"{original['drawn'][name]!r}")
            else:
                # C9: the live range in force names it, else the declaration.
                want = ledger.ranges[key][1] if key in ledger.ranges else key[0]
                if source != want:
                    findings.append(f"C9 trial {n} {name} drawn from {source!r}, in force {want!r}")
            if isinstance(source, int):
                recorded = ledger.dists.get((source, key))
                if recorded is None:
                    findings.append(f"C9 trial {n} {name} names change {source}, no range of it")
                    continue
                dist = rebuilt(recorded)
                EXERCISED["C9 values drawn from a live range"] += 1
            else:
                dist = declaration
            EXERCISED["C4 waits"] += isinstance(dist, K.NonAging)
            if not inside(dist, value, declared.get(name), name in turned):
                code = "C4" if isinstance(dist, K.NonAging) else "C3"
                findings.append(f"{code} trial {n} {name} {value!r} outside {dist!r}")
    findings += designed_checks(task, trials, blocks)
    findings += EASED_BAD
    for line in trials:
        if EASED.get(line["index"]) != bool(line["eased"]):
            findings.append(f"C11 trial {line['trial_number']} line eased {line['eased']} told "
                            f"{EASED.get(line['index'])}")
    findings += log_checks(session, changes, card, d, root)
    return findings


IMPOSSIBLE_SEEN = {}


def impossible_ran(task, values):
    """Whether a trial's own values make it one no animal can get right (`check.impossible`, the
    task's draws and plans set aside so every value is the trial's)."""
    key = tuple(sorted((name, repr(value)) for name, value in values.items()))
    if key not in IMPOSSIBLE_SEEN:
        bare = dataclasses.replace(task, draws={}, plans={})
        IMPOSSIBLE_SEEN[key] = bool(impossible(
            bare, [Block("trial", [Condition("trial", {}, target=1)])], values))
    return IMPOSSIBLE_SEEN[key]


def designed_checks(task, trials, blocks):
    """C6 and C7: each designed block's plan, and its lines against it."""
    findings = []
    end = CURRENT["end"]
    for entry in end.get("block_ends", []):
        block = blocks[entry["block"]]
        order = block.order
        lines = [line for line in trials if entry.get("block_in_session") is not None
                 and line.get("block_in_session") == entry["block_in_session"]]
        planned = entry.get("planned")
        if isinstance(order, SequenceBalanced):
            names = [c.name for c in block.conditions]
            tuples_in = len(names) ** order.depth
            size = tuples_in + order.depth - 1
            if not isinstance(planned, list) or len(planned) != size * order.cycles:
                findings.append(f"C6 block {entry['block']} planned {planned!r}")
                continue
            chunk = planned[:size]
            if planned != chunk * order.cycles:
                findings.append(f"C6 block {entry['block']} cycles differ")
            tuples = Counter(tuple(chunk[i + j] for j in range(order.depth))
                             for i in range(tuples_in))
            if len(tuples) != tuples_in or set(tuples.values()) != {1}:
                findings.append(f"C6 block {entry['block']} plan {chunk} is no linear de Bruijn "
                                f"sequence")
            EXERCISED["C6 sequence-balanced plans"] += 1
            places = []
            for line in lines:
                EXERCISED["C6 sequence-balanced trials"] += 1
                spot = line.get("planned")
                if not isinstance(spot, dict) or set(spot) != {"cycle", "position", "lead_in"}:
                    findings.append(f"C6 trial {line['trial_number']} planned {spot!r}")
                    break
                if spot["lead_in"] is not (spot["position"] < order.depth - 1):
                    findings.append(f"C6 trial {line['trial_number']} lead-in {spot!r}")
                if spot["lead_in"]:
                    EXERCISED["C6 lead-in trials"] += 1
                place = spot["cycle"] * size + spot["position"]
                if place >= len(planned) or planned[place] != line["condition"]:
                    findings.append(f"C6 trial {line['trial_number']} played {line['condition']} "
                                    f"at planned place {place}")
                if not places or places[-1] != place:
                    places.append(place)
            if places != list(range(len(places))):
                findings.append(f"C6 block {entry['block']} places played {places[:20]}")
        elif isinstance(order, Priming):
            if not isinstance(planned, list):
                findings.append(f"C7 block {entry['block']} planned {planned!r}")
                continue
            if any(a["value"] == b["value"] for a, b in zip(planned, planned[1:])):
                findings.append(f"C7 block {entry['block']} a switch kept its value: {planned}")
            if order.runs is not None and any(not order.runs[0] <= run["length"] <= order.runs[1]
                                              for run in planned):
                findings.append(f"C7 block {entry['block']} run lengths {planned} past "
                                f"{order.runs}")
            if order.runs is None and any(run["length"] < 1 for run in planned[:-1]):
                findings.append(f"C7 block {entry['block']} an empty run {planned}")
            EXERCISED["C7 priming plans"] += 1
            EXERCISED["C7 switches"] += max(len(planned) - 1, 0)
            shown = set()
            for line in lines:
                EXERCISED["C7 priming trials"] += 1
                spot = line.get("planned")
                if not isinstance(spot, dict) or set(spot) != {"run", "switch", "value"} or not (
                        0 <= spot["run"] < len(planned)):
                    findings.append(f"C7 trial {line['trial_number']} planned {spot!r}")
                    break
                condition = next(c for c in block.conditions if c.name == line["condition"])
                if (spot["value"] != planned[spot["run"]]["value"]
                        or written(condition.values[order.feature]) != spot["value"]):
                    findings.append(f"C7 trial {line['trial_number']} {line['condition']} under "
                                    f"run {spot}")
                fresh = not line["drummed"] and not (line["at_once"] and order.again_at_once)
                if fresh and spot["switch"] != (spot["run"] not in shown):
                    findings.append(f"C7 trial {line['trial_number']} switch {spot['switch']}")
                if line["shown"]:
                    shown.add(spot["run"])
        elif planned is not None:
            findings.append(f"C6 block {entry['block']} plays no designed order, planned "
                            f"{planned!r}")
    return findings


def log_checks(session, changes, card, d, root):
    """C13: sequence, strobes, wl-preproc's join, resume and `stranded.find`."""
    findings = []
    strobed = [row for row in changes if row["kind"] in Rec.STROBED]
    EXERCISED["C13 strobed rows timed"] += len(strobed)
    EXERCISED["C13 sessions read by resume and stranded.find"] += 1
    EXERCISED["C12 live refusals of trials no animal can get right"] += sum(
        "impossible-trial" in why for _, _, why in session.refusals)
    if [row.get("sequence") for row in strobed] != list(range(1, len(strobed) + 1)):
        findings.append(f"C13 sequences {[row.get('sequence') for row in strobed][:12]}")
    if any("sequence" in row for row in changes if row["kind"] not in Rec.STROBED):
        findings.append("C13 an unstrobed row has a sequence")
    if any(row.get("event_code") != PARAM_CHANGED for row in strobed):
        findings.append("C13 a strobed row names another code")
    if card.codes.count(PARAM_CHANGED) != len(strobed):
        findings.append(f"C13 {card.codes.count(PARAM_CHANGED)} PARAM_CHANGED for "
                        f"{len(strobed)} strobed rows")
    records = read_rig_records(d.parent)
    if records.problems:
        findings.append(f"C13 wl-preproc read problems {records.problems[:2]}")
    if len(card.times) != len(card.codes):
        findings.append(f"C13 {len(card.codes)} codes sent, {len(card.times)} timed")
    events = decode_stream(list(zip(card.times, card.codes)))
    # The rig's clock is fitted as wl-preproc's pipeline fits it (`schema/events.py`): each run's
    # start and end rows against its measured start and its `RUN_END`, with the coded rows.
    rig_runs = read_rig_runs(d.parent, session.spec.subject)
    measured = {}
    for run in assemble(events).runs:
        measured.setdefault(run.run_number, (run.start_s, run.end_s))
    timing = time_records(records, code_times(events),
                          run_instants(rig_runs.runs if rig_runs is not None else (), measured))
    problems = [p for p in timing.problems if p.startswith(CHANGES_NAME)]
    if problems:
        findings.append(f"C13 wl-preproc timing problems {problems[:2]}")
    starts = {t.trial_id: t for t in assemble(events).trials}
    for row, at in zip(changes, timing.changes):
        before, after = starts.get(row["trial_number"] - 1), starts.get(row["trial_number"])
        if row["kind"] not in Rec.STROBED:
            EXERCISED["C13 rows that strobed nothing, timed by the rig's clock"] += at is not None
            # Since wl-preproc's 295f9c9 a row that strobed nothing (a clear, a drum or training
            # switch) is timed through its fit of the rig's clock: in the gap before its trial,
            # to within the fit's own limit.
            if at is None or (before is not None and at < before.end_s - RIG_CLOCK_LIMIT_S) or (
                    after is not None and not at < after.start_s + RIG_CLOCK_LIMIT_S):
                findings.append(f"C13 unstrobed change {row['change']} ({row['kind']}) timed {at} "
                                f"outside the gap before trial {row['trial_number']}")
            continue
        if at is None or (before is not None and not before.end_s < at) or (
                after is not None and not at < after.start_s):
            findings.append(f"C13 change {row['change']} ({row['kind']}) timed {at} outside the "
                            f"gap before trial {row['trial_number']}")
    try:
        restoration = Resume_.read(d, session.welfare.left_cage_wall_at)
        if (restoration.sequence, restoration.change) != (
                max([row["sequence"] for row in strobed], default=0),
                max([row["change"] for row in changes], default=0)):
            findings.append(f"C13 resume numbers on from {restoration.sequence}, "
                            f"{restoration.change}")
    except Resume_.Unresumable as refused:
        findings.append(f"C13 not resumable: {refused}")
    found = stranded.find(root)
    if [(f.resumable, f.why) for f in found] != [(True, "")]:
        findings.append(f"C13 stranded.find {[(f.resumable, f.why[:80]) for f in found]}")
    return findings


def build(seed, rng, spare=None):
    """A random task for `seed`: its family, draws and plan."""
    pick = random.Random(f"family:{seed}").random()
    family = "polar" if pick < 0.2 else "directed" if pick < 0.4 else "plain"
    draws = gen_draws(rng, family, spare)
    kind, plans = gen_plan(rng, family, set(draws), spare)
    return family, draws, kind, plans


def session_for(seed, rng, path, family, ceiling, world=None, live=True):
    bounds = Bounds(subject="A", ceilings={
        "reward_correct": Ceiling(value=REWARD, maximum=0.40, unit="mL"),
        "out_of_cage": Ceiling(value=ceiling, maximum=100_000.0, unit="s")},
        minima={"daily_fluid": Floor(value=250.0, unit="mL")})
    spec = SessionSpec(task=str(path), allocation="tasks/allocation.py", root=path.parent,
                       session_id="2027-01-14_01", subject="A", trials=400,
                       frame_period=1 / 240, seed=seed, values=dict(VALUES), bounds=bounds,
                       already_delivered_today=0.0, deployment=Deployment.RIG_FIXED,
                       geometry=DIRECT, session_kind="training", calibration=SRGB, plan="p")
    wall = Wall()
    link = Link(rng, wall, p_move=rng.choice([0.0, 0.0, 0.02, 0.08]),
                p_pause=rng.choice([0.0, 0.01, 0.03]), p_stop=rng.choice([0.0, 0.0, 0.002]),
                p_live=rng.choice([0.0, 0.1, 0.25, 0.4]) if live else 0.0, family=family)
    card = Recording(wall=wall)
    session = Session(spec, card=card, pump=Pump(), link=link, wall_clock=wall)
    link.session = session
    if world is not None:
        session.world = world
    session.left_cage(at=WALL_NOW)
    session.head_fixed(at=wall())
    wall.follow = session.now
    return session, link, card, wall


def reset():
    CLOSES.clear()
    DRAWS.clear()
    FALL_BACK_BAD.clear()
    EASED.clear()
    EASED_BAD.clear()
    RAN.clear()


def one(seed, control=None):
    rng = random.Random(seed)
    family, draws, kind, plans = build(seed, rng)
    ceiling = rng.choice([150.0, 300.0, 600.0])
    tmp = Path(tempfile.mkdtemp(prefix="c3fuzz", dir=FUZZDIR))
    path = task_file(tmp / "task", rng, family, draws, plans)
    findings = []
    from wl_xcon.cli import _load_task
    task = _load_task(path)
    checked = check_task(task)
    blocking = [f for f in checked if f.blocking and f.code != "unallocated-code"]
    if blocking:
        return {"seed": seed, "skipped": "refused at load", "codes": [f.code for f in blocking],
                "family": family}
    weightless = any(f.code == "weightless-condition" for f in checked)
    session, link, card, wall = session_for(seed, rng, path, family, ceiling)
    root = path.parent
    t0 = time.monotonic()
    CURRENT["s"] = session
    reset()
    try:
        session.run()
    except SystemExit as exc:
        if str(exc).startswith(REFUSED_AT_START):
            # A run refused as it starts under the PI's "Refuse to start" (XC-415; the ruling on
            # the C3 plan's prospect run): a refusal, as one at load is, never a finding.
            return {"seed": seed, "skipped": "refused at start", "codes": ["refused-at-start"],
                    "family": family}
        return {"seed": seed, "kind": kind, "plans": plans, "family": family, "findings": [
            f"RAISED {type(exc).__name__}: {exc}"], "tb": traceback.format_exc()[-1500:]}
    except BaseException as exc:  # noqa: BLE001
        return {"seed": seed, "kind": kind, "plans": plans, "family": family, "findings": [
            f"RAISED {type(exc).__name__}: {exc}"], "tb": traceback.format_exc()[-1500:]}
    took = time.monotonic() - t0
    d = session.directory
    runs = rows(d / "runs.jsonl")
    trials = rows(d / "trials.jsonl")
    controls = rows(d / "controls.jsonl")
    changes = rows(d / "parameter_changes.jsonl")
    plan = task.plans["p"]
    names = [b.name for b in plan.blocks]
    scheduler = session._scheduler

    # I2: start and end rows only.
    if [r["event"] for r in runs] != ["start", "end"]:
        findings.append(f"I2 runs rows {[r['event'] for r in runs]}")
    start = runs[0] if runs else {}
    end = runs[-1] if runs else {}
    CURRENT["end"] = end
    # I3/I5: stop kinds, and `limit` only for the out-of-cage welfare stop.
    out = wall() - WALL_NOW
    if session.stop_kind not in ("completed", "limit", "operator"):
        findings.append(f"I3 stop_kind {session.stop_kind}")
    if session.stop_kind == "limit" and out < ceiling - 1e-6:
        findings.append(f"I5 limit before ceiling: out {out:.1f} < {ceiling}")
    if out > ceiling + LONGEST_TRIAL_S + PAUSE_HOUSEKEEPING_S + 31.0:
        findings.append(f"W1 out-of-cage overran: {out:.1f} s against {ceiling}")
    why = session.stopped_because or ""
    if out >= ceiling and session.stop_kind not in ("limit", "operator"):
        if not any(said in why for said in ("time limit", "finished", "no further",
                                            "no condition")):
            findings.append(f"W2 past ceiling, not ended as limit: {why}")
    # I3b: a completed run says why in its end row; no other run does.
    reason = end.get("end_reason")
    if session.stop_kind == "completed" and reason not in T.END_REASONS:
        findings.append(f"I3b completed with end_reason {reason!r}")
    if session.stop_kind != "completed" and reason is not None:
        findings.append(f"I3b {session.stop_kind} with end_reason {reason!r}")
    expected = {"plan's time limit": "plan_time", "no further trial": "stalled",
                "no condition left": "cannot_draw"}
    for said, code in expected.items():
        if said in why and reason != code:
            findings.append(f"I3c '{said}' with end_reason {reason!r}")
    # I4: the plan's time limit: never early; and past it, only a drummed trial is drawn (the PI,
    # 2026-10-19, "Finish the drum first", for a run's limit too).
    worked = session._elapsed - session._run_from
    if "plan's time limit" in why:
        if session.stop_kind != "completed":
            findings.append("I4 plan time stop not completed")
        if worked < plan.time_limit_s:
            findings.append(f"I4 plan time worked {worked:.1f} < {plan.time_limit_s}")
    if plan.time_limit_s is not None:
        for run_worked, _, _, drum in DRAWS:
            if run_worked >= plan.time_limit_s and not drum:
                findings.append(f"I4b a fresh trial drawn at {run_worked:.1f} s, past the plan's "
                                f"{plan.time_limit_s}")
                break
    # I16: a block's own time limit: past it, only a drummed trial is drawn.
    for _, block_worked, limit, drum in DRAWS:
        if limit is not None and block_worked >= limit and not drum:
            findings.append(f"I16 a fresh trial drawn {block_worked:.1f} s into a {limit} s block")
            break
    # I6: block ends.
    ends = end.get("block_ends", [])
    if len(ends) != len(session.blocks_run):
        findings.append(f"I6 block_ends {len(ends)} vs blocks_run {len(session.blocks_run)}")
    if [e["block"] for e in ends] != session.blocks_run:
        findings.append("I6 block_ends names differ from blocks_run")
    for e in ends:
        if e["ended"] not in ENDED:
            findings.append(f"I6 ended {e['ended']}")
    # I10: six fields and structure, and C3's four.
    for r in trials:
        for k in ("index", "subject", "outcome", "block", "condition", "params", "structure",
                  "drawn", "live", "eased", "planned"):
            if k not in r:
                findings.append(f"I10 trial line lacks {k}")
                break
    # I7: stream framing, as wl-preproc assembles it.
    words = [(float(i), w) for i, w in enumerate(card.codes)]
    asm = assemble(decode_stream(words))
    if asm.errors:
        findings.append(f"I7 decode errors {asm.errors[:2]}")
    by_number = {r["trial_number"]: r for r in trials if "trial_number" in r}
    block_of = {}
    for t in asm.trials:
        inside_ = [b for b in asm.blocks
                   if b.start_s <= t.start_s <= (b.end_s if b.end_s is not None else b.last_s)]
        if len(inside_) != 1:
            findings.append(f"I7 trial {t.trial_id} in {len(inside_)} blocks")
            continue
        block_of[t.trial_id] = inside_[0].block_id
    per_block = {}
    for tid, bid in block_of.items():
        r = by_number.get(tid)
        if r is not None:
            per_block.setdefault(bid, set()).add(r["block"])
    for bid, types in per_block.items():
        if len(types) != 1:
            findings.append(f"I7 stream block {bid} has types {sorted(types)}")
    if len(asm.trials) != len(trials):
        findings.append(f"I7 stream trials {len(asm.trials)} vs lines {len(trials)}")
    in_session = list(dict.fromkeys(r.get("block_in_session") for r in trials))
    if len(in_session) != len(asm.blocks):
        findings.append(f"I7 {len(asm.blocks)} stream blocks vs {len(in_session)} in lines")
    # I17 (engineering review, I4): block_ends join the stream's blocks.
    numbered = [e.get("block_in_session") for e in ends if e.get("block_in_session") is not None]
    if numbered != in_session:
        findings.append(f"I17 block_ends numbers {numbered} vs lines {in_session}")
    for e in ends:
        k = e.get("block_in_session")
        if k is not None and {r["block"] for r in trials if r.get("block_in_session") == k} != {
                e["block"]}:
            findings.append(f"I17 block {k} is not all {e['block']}")
    zero_trial_blocks = sum(e.get("block_in_session") is None for e in ends)
    # I18 (engineering review, I4): each entry's place in the run's sequence is its block type.
    n = len(names)
    for e in ends:
        position = e.get("position")
        if isinstance(plan.order, Cyclic):
            want = names[position % n]
        elif isinstance(plan.order, (Balanced, Random)):
            want = names[scheduler._sequence[position]]
        else:
            want = names[position]
        if want != e["block"]:
            findings.append(f"I18 position {position} is {want}, entry says {e['block']}")
            break
    # I19 (the PI, 2026-10-19, "Never back-to-back").
    if isinstance(plan.order, Balanced) and n > 1:
        seq = scheduler._sequence
        if any(a == b for a, b in zip(seq, seq[1:])):
            findings.append(f"I19 balanced sequence back to back: {seq[:12]}")
    # I8: a drummed trial is in the same stream block as the trial before it.
    for a, b in zip(trials, trials[1:]):
        if b.get("drummed"):
            if a["block"] != b["block"] or block_of.get(a.get("trial_number")) != block_of.get(
                    b.get("trial_number")):
                findings.append(f"I8 drummed trial {b.get('trial_number')} split from its trial")
    # I9: a training progression moves one stage at a time by its rules (a person's move too).
    if kind == "ByCriterion":
        idx = [names.index(name) for name in session.blocks_run]
        for x, y in zip(idx, idx[1:]):
            if abs(x - y) != 1:
                findings.append(f"I9 stage {x} -> {y}")
                break
    # I12: time shortfalls only for blocks ended by their own time; run_time shortfalls only for
    # the block the run's time ended; designed ones only in a sequence-balanced block, one trial.
    for because, ended in (("time", "time"), ("run_time", "run_time")):
        closed = {e["block"] for e in ends if e["ended"] == ended}
        for s in end.get("shortfalls", []):
            if s["because"] == because and s["block"] not in closed:
                findings.append(f"I12 {because} shortfall for {s['block']} not ended {ended}")
    balanced = {b.name for b in plan.blocks if isinstance(b.order, SequenceBalanced)}
    for s in end.get("shortfalls", []):
        if s["because"] == "designed" and (s["block"] not in balanced or s["trials"] != 1):
            findings.append(f"I12 designed shortfall {s}")
    # I13: moves recorded with who; controls rows only for accepted moves; no event code.
    moves = [c for c in controls if c.get("kind") in ("next_block", "back_block")]
    for c in moves:
        if c.get("by") != {"kind": "box", "name": "fuzz"}:
            findings.append("I13 move without who")
        if c.get("event_code") is not None:
            findings.append(f"I13 move row names code {c.get('event_code')}")
    nmoves = sum(e["ended"] in ("next", "back") for e in ends)
    if nmoves != len(moves):
        findings.append(f"I13 {nmoves} moved block ends vs {len(moves)} control rows")
    # I8b: a block never ends on its rule, its time, a fall-back or the run's time with a drum
    # waiting.
    for (name, closed, limit, worked_in, drum) in CLOSES:
        if drum and closed in ("rule", "fall_back", "time", "run_time"):
            findings.append(f"I8b block {name} ended {closed} with a drum waiting")
    # I20 (the PI, "First answer only").
    for name, last, rule_ in FALL_BACK_BAD:
        findings.append(f"I20 block {name} fell back on first answers {last} under {rule_}")
    # I14: a stall is genuine -- every block type, opened fresh, owes nothing and has no
    # criterion or number of trials, so none can draw.
    if "no further trial" in why and any(
            b.criterion is not None or b.trials is not None
            or any(c.target > 0 for c in V.expanded(b).conditions) for b in plan.blocks):
        findings.append("I14 false stall")
    if "no condition left to draw" in why and not weightless:
        findings.append(f"I15 cannot-draw end: {why}")
    # I22 (the PI, 2026-10-20, "Both, polar first").
    if family == "polar":
        from wl_xcon.geometry import polar_deg
        for r in trials:
            value = r["params"].get("target_pos")
            if not (isinstance(value, dict)
                    and set(value) == {"eccentricity", "direction", "x", "y"}
                    and abs(value["x"] - polar_deg(value["eccentricity"],
                                                   value["direction"])[0]) < 1e-9
                    and abs(value["y"] - polar_deg(value["eccentricity"],
                                                   value["direction"])[1]) < 1e-9):
                findings.append(f"I22 trial {r.get('trial_number')} target_pos {value!r}")
                break
    # I21 (science review, I4): the start row writes the plan as declared.
    if start.get("plan") != "p" or (start.get("plan_form") or {}).get("class") != "Plan":
        findings.append(f"I21 start row plan {start.get('plan')!r} form {start.get('plan_form')!r}")
    # The C3 spec §12's (C3-C13).
    try:
        findings += c3_checks(task, session, trials, changes, card, d, root)
    except Exception as exc:  # noqa: BLE001
        findings.append(f"CHECK RAISED {type(exc).__name__}: {exc} "
                        f"{traceback.format_exc()[-600:]}")
    return {"seed": seed, "kind": kind, "family": family, "findings": findings,
            "trials": len(trials), "blocks": len(ends), "zero_trial_blocks": zero_trial_blocks,
            "stop": session.stop_kind, "why": why, "took": took, "end_reason": reason,
            "sent": dict(link.sent), "plans": plans if findings else None,
            "draws": draws if findings else None,
            "ended": Counter(e["ended"] for e in ends), "fell_back": scheduler.fell_back,
            "weightless": weightless, "refusals": len(session.refusals),
            "kinds": Counter(row["kind"] for row in changes),
            "drawn": sum(len(line["drawn"]) for line in trials),
            "eased": sum(bool(line["eased"]) for line in trials),
            "repeats": sum(line["repeat_of"] is not None for line in trials),
            "designed": Counter(type(b.order).__name__ for b in plan.blocks
                                if isinstance(b.order, (SequenceBalanced, Priming))),
            "factorial": sum(b.factorial is not None for b in plan.blocks)}


# --- Replay mode: C1 and C2 --------------------------------------------------------------------

BREAK = Scripted({}, inside={frame: "fix" for frame in range(1, 6)})


def scripted(trial, values, index):
    """A world fixed per trial number: every fourth trial from the second broken, the rest right
    whatever the holds (the C3 plan's call 40)."""
    if index % 4 == 1:
        return BREAK
    held = round(values["fix_hold"] * 240) + 20
    return Scripted({SaccadeTo("target"): held + 10},
                    inside={frame: "fix" if frame <= held else "target"
                            for frame in range(1, held + 400)})


#: How `Session.run` begins the sentence of a run it refuses before it starts (`check.unplaced`, the
#: PI's "Refuse to start", XC-415): counted as refused at its start, never as a finding.
REFUSED_AT_START = "task refused, run not started: "


def replayed(seed, spare_draw=None, live=True):
    """`seed`'s task run against the scripted world: what each line says it was and drew, and
    each change row; `None` where the task is refused at load or the run raised."""
    rng = random.Random(seed)
    family, draws, kind, plans = build(seed, rng, spare=SPARE)
    if spare_draw is not None:
        draws = {**draws, SPARE: spare_draw}
    ceiling = rng.choice([150.0, 300.0, 600.0])
    tmp = Path(tempfile.mkdtemp(prefix="c3replay", dir=FUZZDIR))
    path = task_file(tmp / "task", rng, family, draws, plans)
    from wl_xcon.cli import _load_task
    task = _load_task(path)
    if any(f.blocking and f.code != "unallocated-code" for f in check_task(task)):
        return None
    session, link, card, wall = session_for(seed, rng, path, family, ceiling, world=scripted,
                                            live=live)
    CURRENT["s"] = session
    reset()
    try:
        session.run()
    except SystemExit as exc:
        if str(exc).startswith(REFUSED_AT_START):
            return {"refused_at_start": str(exc)}
        return {"raised": f"{type(exc).__name__}: {exc}"}
    except BaseException as exc:  # noqa: BLE001
        return {"raised": f"{type(exc).__name__}: {exc}"}
    d = session.directory
    return {
        "lines": [[line["index"], line["block"], line["condition"], line["repeat_of"],
                   line["at_once"], line["drummed"], line["outcome"], line["drawn"],
                   {name: line["params"][name] for name in line["drawn"]}, line["live"],
                   line["eased"], line["planned"]] for line in rows(d / "trials.jsonl")],
        "changes": [[row["change"], row["kind"], row["name"], row["was"], row["now"]]
                    for row in rows(d / "parameter_changes.jsonl")],
        "refusals": len(session.refusals),
    }


def replay_child(n, start):
    out = {seed: replayed(seed) for seed in range(start, start + n)}
    print(json.dumps(out))


def elsewhere(n, control, start, folder):
    done = subprocess.run(
        [sys.executable, str(HERE), "replay-child", str(n), control or "none", str(start),
         str(folder)],
        cwd=TREE, env={**os.environ, "PYTHONHASHSEED": "0"}, capture_output=True, text=True,
        timeout=3600)
    if done.returncode != 0:
        raise SystemExit(done.stderr[-3000:])
    return json.loads(done.stdout.splitlines()[-1])


def replay(n, control, start):
    t0 = time.monotonic()
    first = elsewhere(n, control, start, FUZZDIR / "first")
    second = elsewhere(n, control, start, FUZZDIR / "second")
    ran = [seed for seed, got in first.items() if got is not None and "lines" in got]
    at_start = sum(got is not None and "refused_at_start" in got for got in first.values())
    c1 = [seed for seed in first if first[seed] != second[seed]]
    trials = sum(len(first[seed]["lines"]) for seed in ran)
    repeats = sum(line[3] is not None for seed in ran for line in first[seed]["lines"])
    drawn = sum(len(line[7]) for seed in ran for line in first[seed]["lines"])
    acts_ = sum(len(first[seed]["changes"]) for seed in ran)
    raised = [seed for seed, got in first.items() if got is not None and "raised" in got]
    print(f"C1 control={control} seeds={n} ran={len(ran)} refused_at_load="
          f"{sum(got is None for got in first.values())}"
          + (f" refused_at_start={at_start}" if at_start else "")
          + f" raised={len(raised)} trials={trials} "
          f"repeats={repeats} drawn_values={drawn} change_rows={acts_} differing={len(c1)} "
          f"wall={time.monotonic() - t0:.0f}s")
    for seed in c1[:3]:
        a, b = first[seed], second[seed]
        at = next((i for i, (x, y) in enumerate(zip(a["lines"], b["lines"])) if x != y), None)
        print("--- C1", seed, "first differing line", at,
              a["lines"][at] if at is not None else "", b["lines"][at] if at is not None else "")
    # C2: a draw added of a setting no state reads, in this process, the person silent.
    apply_control(control)
    t0 = time.monotonic()
    moved, compared = [], 0
    for seed in range(start, start + n):
        without = replayed(seed, live=False)
        with_ = replayed(seed, spare_draw="Uniform(20.0, 60.0, repeat=FRESH)", live=False)
        if without is None or with_ is None or "lines" not in without or "lines" not in with_:
            continue
        compared += 1
        if [line[:7] for line in without["lines"]] != [line[:7] for line in with_["lines"]]:
            moved.append(seed)
        elif not all(SPARE in line[7] for line in with_["lines"]):
            moved.append(seed)
    print(f"C2 control={control} compared={compared} moved={len(moved)} "
          f"wall={time.monotonic() - t0:.0f}s {moved[:6]}")


def apply_control(control):
    global CONTROL
    CONTROL = control
    if control == "drum":
        orig = S.Scheduler.ends.fget

        def ends(self):
            saved, self._drum = self._drum, None
            try:
                return orig(self)
            finally:
                self._drum = saved
        S.Scheduler.ends = property(ends)
        origf = S.Scheduler.finished.fget

        def finished(self):
            saved, self._drum = self._drum, None
            try:
                return origf(self)
            finally:
                self._drum = saved
        S.Scheduler.finished = property(finished)
    elif control == "stall":
        S.Scheduler.stalled = property(lambda self: False)
    elif control == "time":
        S.Scheduler.expire = lambda self: None
    elif control == "limit":
        orig_run = T.Session.run

        def run(self, *a, **k):
            out = orig_run(self, *a, **k)
            if "plan's time limit" in (self.stopped_because or ""):
                self.stop_kind = "limit"
            return out
        T.Session.run = run
    elif control == "b2b":
        orig_type_at = S.Scheduler._type_at

        def type_at(self, position):
            order = self.order
            if isinstance(order, Balanced) and position >= 0 and (
                    order.blocks is None or position < order.blocks):
                n = len(self.blocks)
                while len(self._sequence) <= position:
                    round_ = list(range(n))
                    self._order_rng.shuffle(round_)
                    self._sequence.extend(round_)
                return self._sequence[position]
            return orig_type_at(self, position)
        S.Scheduler._type_at = type_at
    elif control == "rundrum":
        S.Scheduler.drum_waiting = property(lambda self: None)
    elif control == "movecode":
        orig_control = T.Session._control

        def _control(self, kind, by, feed, index, at=None, event_code=None, **detail):
            if kind in ("next_block", "back_block"):
                event_code = 3
            return orig_control(self, kind, by, feed, index, at, event_code, **detail)
        T.Session._control = _control
    elif control == "insession":
        orig_close2 = S.Scheduler.close

        def close(self, reason, by=None):
            if self.in_session is not None:
                self.in_session += 1
            return orig_close2(self, reason, by)
        S.Scheduler.close = close
    elif control == "polar":
        orig_written = Rec._written

        def _written(value):
            out = orig_written(value)
            if isinstance(out, dict) and "eccentricity" in out:
                return {k: out[k] for k in ("eccentricity", "direction")}
            return out
        Rec._written = _written
    elif control == "pid":
        orig_unit = V.unit
        V.unit = lambda *key: orig_unit(*key, os.getpid())
    elif control == "shared":
        orig_draw = T.Session._draw

        def _draw(self, task, block, condition, draw):
            if SPARE in task.draws:
                self._scheduler._rng.random()
            return orig_draw(self, task, block, condition, draw)
        T.Session._draw = _draw
    elif control in ("range", "wait"):
        orig_value = V.draw

        def draw(distribution, seed, trial, key, **kw):
            value = orig_value(distribution, seed, trial, key, **kw)
            if control == "range" and isinstance(distribution, K.Uniform) and key[-1] in (
                    "fix_hold", "response_deadline"):
                return distribution.high + 0.05
            if control == "wait" and isinstance(distribution, K.NonAging):
                return distribution.maximum + 0.05
            return value
        V.draw = draw
    elif control == "same":
        orig_draw = T.Session._draw

        def _draw(self, task, block, condition, draw):
            kept = self._kept.pop(draw.repeat_of, None) if draw.repeat_of is not None else None
            try:
                return orig_draw(self, task, block, condition, draw)
            finally:
                if kept is not None:
                    self._kept[draw.repeat_of] = kept
        T.Session._draw = _draw
    elif control == "debruijn":
        orig_balanced = S.balanced_sequence
        S.balanced_sequence = lambda names, depth, cycles, rng: tuple(
            sorted(orig_balanced(names, depth, cycles, rng)))
    elif control == "planned":
        orig_take = S.Scheduler._take

        def _take(self):
            place = orig_take(self)
            if "position" in place:
                return {**place, "position": place["position"] + 1}
            return place
        S.Scheduler._take = _take
    elif control == "leadin":
        orig_take_lead = S.Scheduler._take

        def _take(self):
            place = orig_take_lead(self)
            if "lead_in" in place:
                return {**place, "lead_in": False}
            return place
        S.Scheduler._take = _take
    elif control == "priming":
        orig_new_run = S.Scheduler._new_run

        def _new_run(self, previous):
            group, length = orig_new_run(self, previous)
            return (group if previous is None else previous), length
        S.Scheduler._new_run = _new_run
    elif control == "handback":
        orig_pending = T.Session._apply_pending

        def _apply_pending(self, act, code, trial_number, index):
            applied = orig_pending(self, act, code, trial_number, index)
            if act.kind == "hand_back" and act.act is None:
                self._edited |= {act.name}
            return applied
        T.Session._apply_pending = _apply_pending
    elif control == "rangesrc":
        orig_draw = T.Session._draw

        def _draw(self, task, block, condition, draw):
            taken, sources = orig_draw(self, task, block, condition, draw)
            keys = {**V.in_force(task, block), **V.own_ranges(condition)}
            return taken, {name: keys[name][1][0] if isinstance(source, int) else source
                           for name, source in sources.items()}
        T.Session._draw = _draw
    elif control == "revert":
        orig_revert = T.Session._revert

        def _revert(self, command, index):
            before = len(self._pending)
            orig_revert(self, command, index)
            self._pending[before:] = [p for p in self._pending[before:]
                                      if not (p.kind == "hand_back" and p.act is not None)]
        T.Session._revert = _revert
    elif control == "bounded":
        orig_revert = T.Session._revert

        def _revert(self, command, index):
            acts_before = self._act
            orig_revert(self, command, index)
            if self._act != acts_before:
                self._staged.append(("reward_correct", self.spec.bounds.ceilings[
                    "reward_correct"].value, 0.11, command.by, True))
                self._acts[len(self._staged) - 1] = self._act
        T.Session._revert = _revert
    elif control == "impossible":
        T.Session._impossible = lambda self, name, value: None
        T.Session._possible = lambda self, changed=None, **kw: None
    elif control == "sequence":
        orig_pending = T.Session._apply_pending

        def _apply_pending(self, act, code, trial_number, index):
            if act.kind != "hand_back":
                return orig_pending(self, act, code, trial_number, index)
            emit = self.card.emit
            self.card.emit = lambda word: None
            try:
                return orig_pending(self, act, code, trial_number, index)
            finally:
                self.card.emit = emit
        T.Session._apply_pending = _apply_pending
    elif control == "resume":
        Resume_.KINDS = tuple(kind for kind in Resume_.KINDS if kind != "hand_back")
    elif control not in (None, "opened", "firstans", "eased"):
        raise SystemExit(f"no control {control!r}")


#: The CPU-seconds each fuzzing process may use, when set (`tests/test_fuzz_sessions.py` sets it):
#: a mutant that makes a session spin is killed rather than left running after the suite that
#: started it was killed. A process's limit is inherited by the replay children it starts.
CPU_LIMIT_ENV = "WLX_FUZZ_CPU_S"


def main(argv):
    global FUZZDIR
    if os.environ.get(CPU_LIMIT_ENV):
        import resource
        seconds = int(os.environ[CPU_LIMIT_ENV])
        _, hard = resource.getrlimit(resource.RLIMIT_CPU)
        if hard != resource.RLIM_INFINITY:
            seconds = min(seconds, hard)
        resource.setrlimit(resource.RLIMIT_CPU, (seconds, seconds))
    if argv[1] in ("replay", "replay-child"):
        mode, argv = argv[1], argv[1:]
    else:
        mode = "fuzz"
    n = int(argv[1])
    control = argv[2] if len(argv) > 2 and argv[2] != "none" else None
    start = int(argv[3]) if len(argv) > 3 else 0
    FUZZDIR = Path(argv[4]) if len(argv) > 4 else Path(tempfile.mkdtemp())
    FUZZDIR.mkdir(parents=True, exist_ok=True)
    if mode == "replay-child":
        apply_control(control)
        return replay_child(n, start)
    if mode == "replay":
        return replay(n, control, start)
    apply_control(control)
    results = []
    t0 = time.monotonic()
    for seed in range(start, start + n):
        results.append(one(seed, control))
    ran = [r for r in results if "skipped" not in r]
    bad = [r for r in ran if r["findings"]]
    at_start = sum(r.get("skipped") == "refused at start" for r in results)
    print(f"control={control} sessions={len(results)} ran={len(ran)} "
          f"refused_at_load={len(results) - len(ran) - at_start}"
          + (f" refused_at_start={at_start}" if at_start else "")
          + f" with_findings={len(bad)} "
          f"wall={time.monotonic() - t0:.0f}s")
    print("trials", sum(r.get("trials", 0) for r in ran), "blocks",
          sum(r.get("blocks", 0) for r in ran),
          "zero-trial blocks", sum(r.get("zero_trial_blocks", 0) for r in ran),
          "fell back", sum(r.get("fell_back", 0) for r in ran),
          "weightless plans", sum(bool(r.get("weightless")) for r in ran))
    print("families", dict(Counter(r.get("family") for r in ran)),
          "refused codes", dict(Counter(c for r in results if "skipped" in r for c in r["codes"])))
    print("drawn values", sum(r.get("drawn", 0) for r in ran), "repeats",
          sum(r.get("repeats", 0) for r in ran), "eased trials",
          sum(r.get("eased", 0) for r in ran), "refusals", sum(r.get("refusals", 0) for r in ran),
          "factorial blocks", sum(r.get("factorial", 0) for r in ran))
    designed = Counter()
    for r in ran:
        designed.update(r.get("designed", {}))
    print("designed blocks", dict(designed))
    print("exercised", dict(EXERCISED))
    print("stops", dict(Counter(r.get("stop") for r in ran)))
    print("end reasons", dict(Counter(r.get("end_reason") for r in ran)))
    print("orders", dict(Counter(r.get("kind") for r in ran)))
    ended = Counter()
    for r in ran:
        ended.update(r.get("ended", {}))
    print("block ends", dict(ended))
    kinds = Counter()
    for r in ran:
        kinds.update(r.get("kinds", {}))
    print("change rows", dict(kinds))
    sent = Counter()
    for r in ran:
        sent.update(r.get("sent", {}))
    print("commands", dict(sorted(sent.items())))
    found = Counter()
    for r in bad:
        for f in r["findings"]:
            found[f.split(" ")[0]] += 1
    print("finding kinds", dict(found))
    for r in bad[:6]:
        print("---", r["seed"], r.get("kind"), r.get("family"), r["findings"][:4])
        print("   plans:", (r.get("plans") or "")[:600])
        print("   draws:", r.get("draws"))
        if r.get("tb"):
            print(r["tb"])


if __name__ == "__main__":
    main(sys.argv)
