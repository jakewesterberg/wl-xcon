"""The trial scheduler: which condition next, when a block ends, what is still owed.

Between-trial code (ADR-0006), so it may hold state and do arbitrary arithmetic --
it runs in the inter-trial interval where an error is observable and recoverable
rather than a dropped frame.

**Block plans and conditions come from the task programs (wl-xtasks) or are chosen at
the rig** (XC-207). S3 §7 had them planned in wl.works before a session, with
`wl-preproc` quarantining a block wl.works did not plan; the PI retired that on
2026-10-01, through wl-works, which sends the rig no day's plan, and wl-preproc withdrew
the quarantine. This schedules *within* the blocks a run is given and never invents
one; until a task program or the rig gives them, a run is one block (`taskd._plan`).
Changing condition weights or geometry is free; changing task is a new run.
"""

from __future__ import annotations

import random
from collections import deque
from dataclasses import dataclass, field

from wl_xcon.task import (
    ANSWERS, COUNTED, OWED, REPEATED, RIGHT, SPENT, UNPAID, Counting, Family, Outcome,
)

# --- What pays a condition's debt (engine spec §16.1-16.2; engine build C2a) -------------------
#
# **Each trial structure declares its counting table** (`task.Counting`), which the scheduler is
# given (`Scheduler.counting`): "run until ten correct" and "show the array a hundred times
# regardless of accuracy" are both ordinary requirements, and a scheduler that picked one would
# silently impose an experimental design on every task in the lab. **A block may count by a table
# of its own instead** (TSK-26; `Block.counting`), and these are the named ones. **A structure
# whose table withholds** (`Counting.withholding`: detection, go/no-go) makes no response an answer
# -- a miss, the withholding design's wrong answer -- and a block's table here classes it as it
# classes a false alarm (`Scheduler._class`).

#: "Run until ten correct": only a right answer pays (`task.RIGHT`), and every other answer pays
#: nothing and is not shown again -- the block's order draws its condition as it would -- as the
#: PI ruled on 2026-08-31 ("wrong choice not" re-queued; §16.2: "Not repeated: wrong targets").
#: A withholding structure's miss is such a wrong answer: unpaid, not shown again; otherwise
#: no response is owed.
CORRECT_ONLY = Counting(
    after_stimulus=OWED,
    outcomes={outcome.value: UNPAID for outcome in ANSWERS - RIGHT},
)

#: "Show the array a hundred times regardless of accuracy": every trial whose stimulus appeared
#: pays -- an answer counted, a break or no response spent (a withholding structure's miss is an
#: answer, counted) -- and one that ended before it is owed, since nothing was presented.
PRESENTED = Counting(after_stimulus=SPENT)

#: Every trial pays: the flat run's "run N trials" (`taskd.Session._plan`). An answer is counted and
#: everything else spent, a trial that reached the longest trial too; a withholding structure's no
#: response is a miss, an answer, counted (the PI's decision 6).
EVERY_TRIAL = Counting(
    after_stimulus=SPENT,
    outcomes={outcome.value: SPENT for outcome in Outcome if outcome not in ANSWERS},
)


@dataclass(frozen=True, slots=True)
class Order:
    """How the next condition is chosen. **Declared per block** (PI, 2026-08-31)."""


@dataclass(frozen=True, slots=True)
class Shuffled(Order):
    """Every still-owed condition once per pass, in random order.

    Balance as the block progresses, and a bound on how long an animal waits for any
    condition. Partly predictable near the end of a pass, when few remain.
    """


@dataclass(frozen=True, slots=True)
class WithReplacement(Order):
    """Each trial drawn independently, optionally weighted.

    No sequential predictability, and it supports conditions wanted rarely -- catch
    trials, probes. Balance only in expectation, so the counters matter more.
    """

    weights: dict = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Constrained(Order):
    """Drawn with replacement, refusing runs longer than `max_run`.

    What most search and attention designs actually use, because an animal exploits
    runs: three of the same target position in a row and it stops searching and
    starts predicting.
    """

    max_run: int = 2
    weights: dict = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Condition:
    name: str
    values: dict
    target: int


#: Why a condition's debt was forgiven (`Shortfall.because`): its repeat limit was reached
#: (`task.Counting.cap`) by the animal's own failures, or with tries the rig lost among them -- a
#: lost tracker or a fault (`task.Family.RIG`) -- or a person cleared trials of it.
CAP = "cap"
RIG = "rig"
CLEARED = "cleared"

#: What a trainer may switch drumming to (`Scheduler.drum`): on for the rest of the block, on for
#: the rest of the run, or off for the rest of the block.
DRUM_SCOPES = ("block", "run", "off")

#: How many failed tries in a row of one drummed trial put a warning on the console (the PI,
#: 2026-10-12, "After 10 in a row": "A warning on the console after 10 failed tries in a row");
#: drumming goes on (`Scheduler.drum_tries`).
DRUM_WARNING = 10


@dataclass(frozen=True, slots=True)
class Draw:
    """What `Scheduler.next_trial` drew, for the trial's row: the realized sequence (engine spec
    §16.3-16.4; engine build C2a). `number` is the trial's place in the run, from 0 -- `taskd`'s
    `index`; `repeat_of`, the number of the trial it shows again, or `None`; `at_once`, whether it
    came straight after that trial, which §16.3 has recorded; `previous`, the condition of the
    trial before it in its block, an aborted one included, or `None` for a block's first.
    `drummed`, whether it is a drum's repeat, and `drumming`, whether drumming was on as it was
    drawn -- `"block"` or `"run"` -- or `None` (`Scheduler.drumming`)."""

    condition: Condition
    number: int
    repeat_of: int | None = None
    at_once: bool = False
    previous: str | None = None
    drummed: bool = False
    drumming: str | None = None


@dataclass(frozen=True, slots=True)
class Block:
    name: str
    conditions: list[Condition]
    #: `(proportion, window)` -- "80% correct over the last 20 judged trials".
    #: When absent, the block ends once every condition is owed nothing.
    criterion: tuple[float, int] | None = None
    #: The table this block counts by, **replacing its structure's** (TSK-26: what counts is
    #: declared per block): `CORRECT_ONLY`, `PRESENTED`, `EVERY_TRIAL` or any `task.Counting` --
    #: a block training an animal to hold fixation may count a fixation break as an error that
    #: pays its debt, while a block measuring a psychometric function must not. `None`, the
    #: structure's own (`Scheduler.counting`).
    counting: Counting | None = None
    #: Which outcomes are judged for the criterion. **Separate from the counting on
    #: purpose**: a block may count every presentation toward its quota while judging
    #: performance only on completed choices, and conflating the two makes a
    #: criterion track engagement rather than what the animal can do. `None`, the
    #: outcomes its table counts as answers.
    criterion_over: frozenset | None = None
    order: Order = field(default_factory=Shuffled)
    #: **Drumming** (the PI, 2026-10-11: "a training tool ... where a trial is repeated until
    #: correct"): every trial of this block that is not right comes back at once, paying nothing,
    #: until it is. A trainer switches it on or off for a block or a run from the console as well
    #: (`Scheduler.drum`).
    drum: bool = False


@dataclass
class Counts:
    """One condition's counters in its block (TSK-28): trials drawn; answers counted (`completed`),
    the correct among them; trials spent, used up without an answer (engine spec §16.2); times it
    was repeated (`repeats`; a drum's are not); its failed repeats in a row since it last paid
    (`in_a_row`, which the repeat limit counts: §16.6 as the PI read it on 2026-10-12) and how
    many of those failed tries the rig lost (`rig`); and trials of its debt forgiven, by the limit
    or by a person (`forgiven`)."""

    attempted: int = 0
    completed: int = 0
    correct: int = 0
    spent: int = 0
    repeats: int = 0
    in_a_row: int = 0
    rig: int = 0
    forgiven: int = 0


@dataclass(frozen=True, slots=True)
class Shortfall:
    """Trials of a condition's debt forgiven in a block, recorded and shown (engine spec §16.6):
    `because` its repeat limit was reached by the animal's own failures (`CAP`), which is **flagged
    as possible avoidance**; or reached with tries the rig lost among them (`RIG`), named so and
    never flagged; or a person cleared them from the console (`CLEARED`, by `by`). `after_trial`,
    the number of the trial it happened after."""

    block: str
    condition: str
    trials: int
    because: str
    after_trial: int
    by: object = None

    @property
    def possible_avoidance(self) -> bool:
        """§16.6: a condition the animal itself failed past its limit is flagged as possible
        avoidance; one the rig failed on is not (the engine C2a plan's engineering review, M4)."""
        return self.because == CAP


@dataclass
class Scheduler:
    blocks: list[Block]
    seed: int = 0
    #: The structure's counting table (`task.Trial.counting`), which a block's own replaces
    #: (`Block.counting`). `None` answers only what every structure shares -- an answer counted,
    #: the four of `task.REPEATED` owed -- and raises on what each declares (`_class`).
    counting: Counting | None = None
    _rng: random.Random = field(init=False, repr=False)
    _counts: dict = field(init=False, default_factory=dict, repr=False)
    _queue: deque = field(init=False, default_factory=deque, repr=False)
    requeued: list = field(init=False, default_factory=list)
    _window: deque = field(init=False, default_factory=deque, repr=False)
    _index: int = field(init=False, default=0, repr=False)
    _drawn: list = field(init=False, default_factory=list, repr=False)
    #: Repeats waiting for their slot (engine spec §16.3): `(slot, repeat_of, condition)`, the
    #: slot a trial number, at most one per condition, whose normal draws wait for it.
    _due: list = field(init=False, default_factory=list, repr=False)
    #: Trials drawn in this run: the next one's number (`Draw.number`).
    _number: int = field(init=False, default=0, repr=False)
    #: The last draw, which `taskd` writes into its trial's row.
    drawn: Draw | None = field(init=False, default=None)
    #: A drum's trial to show at once: `(condition, repeat_of)`, or `None`.
    _drum: tuple | None = field(init=False, default=None, repr=False)
    #: What a trainer switched drumming to (`DRUM_SCOPES`), or `None` for the block's own.
    _switched: str | None = field(init=False, default=None, repr=False)
    #: The run's shortfalls, every block's, in order (§16.6), which its end row records.
    shortfalls: list = field(init=False, default_factory=list)
    #: Whether that switch came once this block's end rule was met, so it is the next block's.
    _carried: bool = field(init=False, default=False, repr=False)
    #: Failed tries in a row of the trial being drummed, its first try included.
    _tries: int = field(init=False, default=0, repr=False)
    #: Whether this drum chain (a trial's first try and its drummed repeats) has had an answer
    #: judged.
    _answered: bool = field(init=False, default=False, repr=False)

    def __post_init__(self) -> None:
        self._rng = random.Random(self.seed)
        self._counts = {c.name: Counts() for c in self.block.conditions}
        self._refill()

    @property
    def block(self) -> Block:
        return self.blocks[self._index]

    def _refill(self) -> None:
        """Queue the next draw, however this block declares its order.

        Always from the seeded generator, so a session's condition order is
        reconstructable -- a randomisation nobody can reproduce is one nobody can
        rule out as an explanation.
        """
        pending = [c.name for c in self.block.conditions if self._drawable(c.name)]
        if not pending:
            return
        order = self.block.order
        if isinstance(order, Shuffled):
            self._rng.shuffle(pending)
            self._queue.extend(pending)
            return

        weights = [order.weights.get(name, 1.0) for name in pending]
        if isinstance(order, Constrained):
            allowed = [name for name in pending if not self._runs_long(name)]
            if allowed:
                pending = allowed
                weights = [order.weights.get(name, 1.0) for name in pending]
        self._queue.append(self._rng.choices(pending, weights=weights, k=1)[0])

    def _drawable(self, condition: str) -> bool:
        """Whether an ordinary draw may give `condition`: it still owes, and no repeat of it is
        waiting for its slot -- the repeat is its next trial (engine spec §16.3)."""
        return self.owed(condition) > 0 and all(name != condition for _, _, name in self._due)

    def _runs_long(self, condition: str) -> bool:
        """Whether `condition` next would make a run longer than a `Constrained` block allows."""
        order = self.block.order
        return (
            isinstance(order, Constrained)
            and len(self._drawn) >= order.max_run
            and all(previous == condition for previous in self._drawn[-order.max_run:])
        )

    def _peek(self) -> str | None:
        """The next ordinary draw, left in the queue: entries that stopped being drawable since
        they were queued are dropped (an entry goes stale when Task 8's `clear` forgives a condition
        still queued), and the queue refilled once when empty; `None` when nothing is drawable."""
        for _ in range(2):
            while self._queue and not self._drawable(self._queue[0]):
                self._queue.popleft()
            if self._queue:
                return self._queue[0]
            self._refill()
        return None

    def counts(self, condition: str) -> Counts:
        return self._counts[condition]

    def owed(self, condition: str) -> int:
        """Target minus what paid -- the answers counted and the trials spent -- and what was
        forgiven (§16.6), **never minus attempted**: an owed trial produced no datum, so it left
        the condition owing exactly what it owed before."""
        target = next(c.target for c in self.block.conditions if c.name == condition)
        counts = self._counts[condition]
        return max(0, target - counts.completed - counts.spent - counts.forgiven)

    @property
    def _table(self) -> Counting | None:
        """The open block's counting table, else the run's. (`_class` still asks the run's whether no
        response is an answer: what counts as one is the structure's.)"""
        return self.block.counting if self.block.counting is not None else self.counting

    def _class(self, outcome: Outcome | None, shown: bool) -> str:
        """What `outcome` does to its condition's count, by the block's table or the structure's
        (`task.Counting.of`). **With neither**, what every structure shares still answers -- an
        answer counted, shown or not; the four of `task.REPEATED`, a hang and a break before the
        stimulus owed -- and an outcome each structure declares for raises: no default stands in
        for a declaration (the PI, 2026-10-11), and `check.check_task` refuses a run's structure
        without one. **Where the structure's table makes no response an answer** (`withholding`), a
        block's own table classes `NO_RESPONSE` as it classes `FALSE_ALARM`, the withholding design's
        other wrong answer, whatever it declares for no response: what counts as an answer is the
        structure's, as `appears` is (the PI's decision 6, 2026-10-11, "'No response' ... is a miss
        (counts, used up)"; the review of build C2a's Task 3)."""
        table = self._table
        if (outcome is Outcome.NO_RESPONSE and self.block.counting is not None
                and self.counting is not None and self.counting.withholding):
            return self.block.counting.of(Outcome.FALSE_ALARM, shown)
        if table is not None:
            return table.of(outcome, shown)
        if outcome in ANSWERS:
            return COUNTED
        if outcome is None or outcome in REPEATED or not shown:
            return OWED
        raise ValueError(
            f"{outcome.value} ended a trial of block {self.block.name!r}, and neither the block "
            f"nor its structure has a counting table saying what it does to the count (engine "
            f"spec §16.2)"
        )

    def upcoming(self) -> list[str]:
        return list(self._queue)

    @property
    def done(self) -> bool:
        """Every block finished, which is when the *session* runs out of plan.

        Separate from `finished`, which has always been about the current block
        alone. Nothing advanced past a block until 2026-09-06, so a two-block
        scheduler ran its first block forever -- and nothing noticed, because
        `taskd` never imported this module.
        """
        return self._index >= len(self.blocks) - 1 and self.finished

    def advance(self) -> Block:
        """Move to the next block, and start it empty.

        **Counters and the criterion window are reset**, because they are properties
        of a block and not of a session: a criterion carried across would be met
        before its own block had run a trial, on evidence from a different task
        configuration entirely. `requeued` is not reset -- it is the session's log of
        what had to be run again, and that reads across blocks.
        """
        if self._index >= len(self.blocks) - 1:
            raise IndexError(
                f"block {self.block.name!r} is the last block; a session that ran "
                f"off the end of its plan would draw from a block that does not exist"
            )
        self._index += 1
        self._counts = {c.name: Counts() for c in self.block.conditions}
        self._queue.clear()
        self._window.clear()
        self._drawn.clear()
        self._due.clear()
        self._drum = None
        if self._switched != "run" and not self._carried:
            self._switched = None
        self._carried = False
        self._refill()
        return self.block

    @property
    def drumming(self) -> str | None:
        """Whether trials are drummed now (`Block.drum`): `"run"` when a trainer switched it on for
        the run, `"block"` when for this block or the block declares it, `None` when it is off --
        a trainer's *off* holds to the block's end, a declaring block's included."""
        if self._switched in ("run", "block"):
            return self._switched
        if self._switched is None and self.block.drum:
            return "block"
        return None

    @property
    def drum_tries(self) -> int:
        """Failed tries in a row of the trial being drummed, its first try included, or 0 when no
        drum's trial waits: at `DRUM_WARNING` the console warns, and drumming goes on (the PI,
        2026-10-12)."""
        return self._tries if self._drum is not None else 0

    def drum(self, scope: str) -> str:
        """Switch drumming, as a trainer does from the console (the PI, 2026-10-11): `"block"` on
        until this block ends, `"run"` on until the run ends, `"off"` off until this block ends.
        Off drops a drum's trial waiting to come back; its condition stays owed and is drawn as
        any other. **Returns the name of the block it is for**: this one, or the next when this
        block's end rule is already met -- the loop drains commands before it advances, so a
        switch made then is the next block's (the engineering review's Minor 10)."""
        if scope not in DRUM_SCOPES:
            raise ValueError(f"drumming is switched {', '.join(DRUM_SCOPES)}, not {scope!r}")
        self._switched = scope
        if scope == "off":
            self._drum = None
        self._carried = self.finished and not self.done
        return self.blocks[self._index + 1].name if self._carried else self.block.name

    @property
    def finished(self) -> bool:
        if self.block.criterion is not None:
            proportion, window = self.block.criterion
            if len(self._window) < window:
                return False
            return sum(self._window) / len(self._window) >= proportion
        return all(self.owed(c.name) == 0 for c in self.block.conditions)

    def next_trial(self) -> Condition:
        """The next trial's condition, its `Draw` left in `drawn`. **The earliest waiting repeat
        goes first** when its slot has come, when nothing else can be drawn, or when the ordinary
        draw -- which gives no condition a repeat is waiting for -- would make a run longer than a
        `Constrained` block allows (engine spec §16.3). **Except that a repeat taken early, its
        slot not yet come, which the trial just recorded placed, gives way to the next waiting
        one** when there is another: only the last condition owed repeats at once. A repeat taken
        at its slot or early can make a run of two of its condition, at once or not; a
        `Constrained` block's limit counts it as a draw. **A drum's trial goes before all of
        them**, at once."""
        number = self._number
        waiting = sorted(self._due)
        drummed = self._drum is not None
        name, repeat_of = self._drum if drummed else (self._peek(), None)
        if drummed:
            self._drum = None
        elif waiting and (waiting[0][0] <= number or name is None or self._runs_long(name)):
            due = waiting[0]
            if due[1] == number - 1 and len(waiting) > 1:
                due = waiting[1]
            self._due.remove(due)
            _, repeat_of, name = due
        elif name is None:
            raise IndexError(
                f"block {self.block.name!r} has no condition left to draw and its end rule is not "
                f"met"
            )
        else:
            self._queue.popleft()
        condition = next(c for c in self.block.conditions if c.name == name)
        self.drawn = Draw(
            condition,
            number,
            repeat_of=repeat_of,
            at_once=repeat_of is not None and repeat_of == number - 1,
            previous=self._drawn[-1] if self._drawn else None,
            drummed=drummed,
            drumming=self.drumming,
        )
        self._drawn.append(name)
        self._counts[name].attempted += 1
        self._number += 1
        return condition

    def record(self, condition: str, outcome: Outcome | None, shown: bool = True) -> str:
        """Count one trial of `condition` by its table (engine spec §16.1-16.2), and return what it
        did to the count: `COUNTED`, `SPENT`, `OWED` or `UNPAID`. `outcome` `None` is a trial that
        reached the longest trial (`task.HANG_COUNTS_AS`); `shown`, whether its stimulus had
        appeared (`task.Counting.of`). A right answer (`task.RIGHT`: correct, or a correct
        rejection) is right for the criterion and the correct count. While drumming, a trial that
        is not right is `OWED` and comes back at once, whatever its table says, and only a trial's
        first answer is judged. An owed trial of a condition that has failed as many repeats in a row
        as its table's limit allows (`task.Counting.cap`) is not repeated again: its remaining debt
        is forgiven, a `Shortfall` (§16.6)."""
        counts = self._counts[condition]
        kind = self._class(outcome, shown)
        first_try = self.drawn is None or not self.drawn.drummed
        over = self.block.criterion_over
        judged = (outcome in over) if over is not None else kind == COUNTED
        if first_try:
            self._answered = False
        if judged and not self._answered:
            # **Only a trial's first answer is judged** (the PI, 2026-10-12, "Leave drummed repeats
            # out", and 2026-10-18, "Judge its first answer"): a drum's repeat after a wrong answer
            # is recorded as what it was and never judged; after a try that ended before any answer
            # -- a break, no fixation, a hang -- it is the trial's first answer, and is judged.
            self._answered = True
            self._window.append(1 if outcome in RIGHT else 0)
            if self.block.criterion is not None:
                while len(self._window) > self.block.criterion[1]:
                    self._window.popleft()
        if self.drumming and outcome not in RIGHT and self.owed(condition) > 0:
            # **Drumming** (`Block.drum`): repeated until right -- a correct answer or a correct
            # rejection (`task.RIGHT`) -- at once, paying nothing, its failed tries in a row
            # counted for the console's warning (`drum_tries`).
            self.requeued.append(condition)
            self._drum = (condition, self._number - 1)
            self._tries = 1 if first_try else self._tries + 1
            return OWED
        if kind == COUNTED:
            counts.completed += 1
            counts.correct += outcome in RIGHT
        elif kind == SPENT:
            counts.spent += 1
        if kind in (COUNTED, SPENT):
            # The condition paid, so its failed repeats in a row start again (the PI, 2026-10-12:
            # "the count resets once it is done").
            counts.in_a_row = counts.rig = 0
        if kind == OWED and self.owed(condition) > 0:
            counts.rig += outcome is not None and outcome.family is Family.RIG
            table = self._table
            cap = None if table is None else table.cap
            if cap is not None and counts.in_a_row >= cap:
                # **Past its limit, the condition's remaining debt is forgiven** (§16.6; the PI,
                # 2026-10-12: "moved past after 3 failed repeats in a row"), its shortfall
                # recorded -- flagged as possible avoidance only when the animal failed each try.
                self._forgive(condition, self.owed(condition), RIG if counts.rig else CAP)
            else:
                counts.repeats += 1
                counts.in_a_row += 1
                self.requeued.append(condition)
                self._repeat(condition)
        return kind

    def _forgive(self, condition: str, trials: int, because: str, by: object = None) -> None:
        """Forgive `trials` of `condition`'s debt in this block (§16.6): no repeat of it waits any
        longer, nor a drum's trial, and the shortfall is the run's record."""
        self._counts[condition].forgiven += trials
        self._due = [due for due in self._due if due[2] != condition]
        if self._drum is not None and self._drum[0] == condition:
            self._drum = None
        self.shortfalls.append(
            Shortfall(self.block.name, condition, trials, because, self._number - 1, by))

    def _repeat(self, condition: str) -> None:
        """Place the repeat of the trial just recorded (engine spec §16.3; the PI, 2026-10-11, and
        2026-10-12 for every block): **a random slot within the next k trials, k the block's
        number of conditions and at least 3, never the very next** -- so an animal cannot get an
        easy condition by breaking on a hard one, nor the same display again by breaking on it, nor
        know where a repeat comes in a block of two (the PI: "At least 3") -- **unless nothing else
        can be drawn**: it is the only condition still owed, or every other is waiting too, when
        a waiting repeat comes first (`next_trial`: the earliest, but not this one while another
        waits), at once only if it is the last, which its row records (`Draw.at_once`). **The
        slot is one no other waiting repeat holds**, so two never fall due on one trial and none
        waits past its window: every waiting repeat was placed at an earlier trial m with its
        slot at most m + k, so slot number + k is always free. A drum's trials, which go before
        them all, put the waiting repeats off by as many trials as it takes tries. The slot is
        the block's seeded generator's, so a session's order stays reproducible."""
        number = self._number - 1
        k = max(3, len(self.block.conditions))
        held = {slot for slot, _, _ in self._due}
        free = [slot for slot in range(number + 2, number + k + 1) if slot not in held]
        slot = self._rng.choice(free)
        self._due.append((slot, number, condition))
