"""The trial scheduler: which condition next, when a block ends, what is still owed.

Between-trial code (ADR-0006), so it may hold state and do arbitrary arithmetic --
it runs in the inter-trial interval where an error is observable and recoverable
rather than a dropped frame.

**Block plans and conditions come from the task programs (wl-xtasks) or are chosen at
the rig** (XC-207). S3 §7 had them planned in wl.works before a session, with
`wl-preproc` quarantining a block wl.works did not plan; the PI retired that on
2026-10-01, through wl-works, which sends the rig no day's plan, and wl-preproc withdrew
the quarantine. **Since engine build C2b a task declares its plans** (`task.Plan`,
`task.Task.plans`) and the operator chooses one as a run starts; this plays the chosen
plan's blocks in its order (`task.BlockOrder`) and never invents one, and a run with no
plan chosen is one block (`taskd.Session._plan`). Changing condition weights or geometry
is free; changing task is a new run.

**Since engine build C3 a block may play a designed order** (`task.SequenceBalanced`,
`task.Priming`; the PI, 2026-10-30, Q5a, Q5b and Q6): its trials come from a plan drawn as the
block opens, from a generator of its own keyed by the run's seed and the block's occurrence, never
the one ordinary draws and repeats share, so a designed block moves no other block's draws.
"""

from __future__ import annotations

import random
from collections import deque
from dataclasses import dataclass, field, replace

from wl_xcon.declarations import canonical

# The block vocabulary is the task's (engine build C2b): a plan's blocks are declared in its task
# object, and imported here, where they are played, under the names they always had here.
from wl_xcon.task import (
    ANSWERS, COUNTED, HANG_COUNTS_AS, NO_LIMIT, OWED, REPEATED, RIGHT, SPENT, UNPAID, Balanced,
    Block, BlockOrder, ByCriterion, Condition, Constrained, Counting, Cyclic, Family, Fixed, Order,
    Listed, Outcome, Priming, Random, SequenceBalanced, Shuffled, WithReplacement,
    staircase_verdict,
)
from wl_xcon.variation import balanced_sequence, run_length

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


#: Why a condition's debt was forgiven (`Shortfall.because`): its repeat limit was reached
#: (`task.Counting.cap`) by the animal's own failures, or with tries the rig lost among them -- a
#: lost tracker or a fault (`task.Family.RIG`) -- or a person cleared trials of it.
CAP = "cap"
RIG = "rig"
CLEARED = "cleared"
#: ... or its block's time ran out with it still owed (engine build C2b; the PI, 2026-10-19,
#: "Finish trial, then end": "Trials it still owed are recorded as not run, 'time ran out'"),
#: forgiving nothing: the run's end row reads it beside the condition's counts.
TIME = "time"
#: ... or the run's own time limit ran out with its block open (`task.Plan.time_limit_s`; the engine
#: C2b plan's science review, I3), recorded apart from a block's own, so the record and the console
#: say whose time it was; forgiving nothing too.
RUN_TIME = "run_time"
#: ... or it was a sequence-balanced block's trial that broke and is not shown again (engine build
#: C3; the PI, 2026-10-30, Q5b: no repeat by default, TSK-31): one trial, its place lost, never
#: flagged as possible avoidance, and the sequence goes on. A priming block writes none: a break
#: before its stimulus loses no place, and one after it is a shown trial of its run.
DESIGNED = "designed"

#: Why a block ended (`BlockEnd.ended`; engine build C2b): its own end rule was met (`RULE`: every
#: target used up, and its criterion and number of trials where it declares them), its time ran
#: out (`TIME`), its plan's fall-back rule was met (`FALL_BACK`), a person moved the run on to the
#: next block or back one (`NEXT`, `BACK`), the run's own time limit ended the run with it open
#: (`RUN_TIME`), or the run ended with it open otherwise (`RUN`: a stop, a limit, a fault, or the
#: plan unable to go on).
RULE = "rule"
FALL_BACK = "fall_back"
NEXT = "next"
BACK = "back"
RUN = "run"

#: **What the rig suggests** under a confirmed progression (`ByCriterion.confirm`; the pop-out
#: search build, 2026-11-07; the PI, "Rig suggests, trainer confirms"): moving up a stage
#: (`MOVE_UP`) or back one (`MOVE_BACK`), or widening the task's pool of pairings (`MOVE_WIDEN`;
#: `task.Pool`; "Same rule: rig suggests"), the words a `suggested` change row's `move` writes, as
#: wl-preproc accepted them (`docs/pending-wl-preproc-amendments.md`).
MOVE_UP = "up"
MOVE_BACK = "back"
MOVE_WIDEN = "widen"

#: What a trainer may switch drumming to (`Scheduler.drum`): on for the rest of the block, on for
#: the rest of the run, or off for the rest of the block.
DRUM_SCOPES = ("block", "run", "off")

#: How many failed tries in a row of one drummed trial put a warning on the console (the PI,
#: 2026-10-12, "After 10 in a row": "A warning on the console after 10 failed tries in a row");
#: drumming goes on (`Scheduler.drum_tries`).
DRUM_WARNING = 10

#: What a trainer switches on and off from the console (`Scheduler.train`; the PI, 2026-10-18):
#: **the training aid *clear***, whether a person may clear a trial from a condition's count, and
#: **the training setting "first answers only"**, how drummed answers count toward a percentage
#: rule. Drumming, the other training aid, has its own switch (`DRUM_SCOPES`).
TRAINING = ("clear", "first_answers")


@dataclass(frozen=True, slots=True)
class Draw:
    """What `Scheduler.next_trial` drew, for the trial's row: the realized sequence (engine spec
    §16.3-16.4; engine build C2a). `number` is the trial's place in the run, from 0 -- `taskd`'s
    `index`; `repeat_of`, the number of the trial it shows again, or `None`; `at_once`, whether it
    came straight after that trial, which §16.3 has recorded; `previous`, the condition of the
    trial before it in its block, an aborted one included, or `None` for a block's first.
    `drummed`, whether it is a drum's repeat, and `drumming`, whether drumming was on as it was
    drawn -- `"block"` or `"run"` -- or `None` (`Scheduler.drumming`); `aids`, the training aids on
    as it was drawn (`Scheduler.aids`). **`planned`, in a designed block, the trial's planned
    place** (engine build C3): `{"cycle": c, "position": p, "lead_in": l}` in a sequence-balanced
    block, each from 0, `lead_in` true on the first `depth - 1` places of each cycle, which only
    precede what follows (the PI, 2026-10-31), or `{"run": r, "switch": s, "value": v}` in a
    priming block -- its run from 0, `switch` true for each try at the run's first place until one
    shows its stimulus, and the feature's value planned, as the block's conditions give
    it; a drum's try and a trial shown again at once carry the place of the trial they show again.
    `None` in any other block."""

    condition: Condition
    number: int
    repeat_of: int | None = None
    at_once: bool = False
    previous: str | None = None
    drummed: bool = False
    drumming: str | None = None
    aids: tuple = ()
    planned: dict | None = None


@dataclass(frozen=True, slots=True)
class BlockEnd:
    """How one block of the run ended, for the run's end row (engine build C2b): its `block` type's
    name, why it `ended` (`RULE`, `TIME`, `FALL_BACK`, `NEXT`, `BACK`, `RUN_TIME` or `RUN`), `by`
    whom when a person moved it, and `after_trial`, the number of the last trial drawn before it
    ended, or `None` when the run drew none. **And where it stands** (the engine C2b plan's
    engineering review, I4): `position`, its place in the run's sequence of blocks, from 0 -- a
    training progression's stage -- and `block_in_session`, its number in the session's stream,
    the one its `BLOCK_START` carried, or `None` for a block that ran no trial, which the stream
    neither opens nor closes. **And `passed_at`**, at a training progression's top stage, the
    trial after which its rule was first met, its animal working on past it, or `None` (the
    science review, I1). **And `planned`, a designed block's plan** (engine build C3): a
    sequence-balanced block's condition names in the order planned, played or not, so a place no
    trial's `Draw.planned` names was never played; a priming block's runs as far as it played,
    `(value, length)` each, a run's length drawn from its `runs`, or under a `chance` the trials of
    it whose stimulus appeared; `None` for any other block."""

    block: str
    ended: str
    by: object = None
    after_trial: int | None = None
    position: int = 0
    block_in_session: int | None = None
    passed_at: int | None = None
    planned: tuple | None = None


@dataclass(frozen=True, slots=True)
class Suggestion:
    """**What the rig suggests at this boundary** under a confirmed progression
    (`ByCriterion.confirm`; `Scheduler.suggestion`): to `move` (`MOVE_UP` or `MOVE_BACK`) from the
    open stage, `block`, to the stage `to`, because `correct` of the last `of` answers its bar
    judges were right, and whether every one of them was at the stage's hardest step
    (`at_hardest`; always true of a move up, whose bar counts only those). **Or to widen the pool**
    in the open stage (`MOVE_WIDEN`; `Scheduler.widening`), by the bar to move up, `to` `None`."""

    move: str
    block: str
    to: str | None
    correct: int
    of: int
    at_hardest: bool


@dataclass(frozen=True, slots=True)
class Answers:
    """**The open stage's last answers, and the bars of what the rig suggests**
    (`Scheduler.answers`; the pop-out search build's Task 7, for the trainer's panel; its design
    §3.4, "the last 50", and §3.5), read between trials. **The last answers shown** (`_shown`),
    each trial's first answer, as many as the bar to move back reads, **in a window only a stage
    change starts afresh** (the build's final fixes, on Task 7's report): `correct` of the last
    `of` right, in a window `window` long; the wrong ones among them by outcome (`wrong`, each its
    wire string); and the trials left out of them, which moved no staircase, by outcome, a hang as
    `"hang"` (`left_out`), since the answer before the first of them or since the stage opened.
    **Toward moving up** (`_up`), the bar's own window of the answers at the stage's hardest step:
    `up_correct` of `up_of`, in a window `up_window` long. And the proportion each bar is met at,
    the stage's criterion's (`up_at`) and the fall-back's (`back_at`), each `None` where there is
    none. Its fields are `link.Bars`', in order."""

    correct: int
    of: int
    window: int
    wrong: dict
    left_out: dict
    up_correct: int
    up_of: int
    up_window: int
    up_at: float | None
    back_at: float | None

    def __iter__(self):
        return iter((self.correct, self.of, self.window, self.wrong, self.left_out,
                     self.up_correct, self.up_of, self.up_window, self.up_at, self.back_at))


@dataclass
class Counts:
    """One condition's counters in its block (TSK-28): trials drawn; answers counted (`completed`),
    the correct among them; trials spent, used up without an answer (engine spec §16.2); times it
    was repeated (`repeats`; a drum's are not); the failed tries in a row of its trial being shown
    again, its first try's included, each of which placed a repeat (`in_a_row`, which the repeat
    limit counts: §16.6 as the PI read it on 2026-10-12, and on 2026-10-18 "1: an answer ends the
    trial"), and how many of those the rig lost (`rig`); trials of its debt forgiven, by the limit
    or by a person (`forgiven`), and whether its limit flagged it as possible avoidance
    (`flagged`). **And for the console and the run's end row** (the PI, 2026-10-18): its `trials`,
    a trial and its drummed repeats one, and the tries recorded, every presentation (`presented`;
    `attempted` counts every draw, a trial that faulted included); every answer, any try's, `right`
    or `wrong`; and the trials whose first try was right (`right_first`). **And in a training
    progression, the trials a live change eased**, on their first try or on the try that paid
    them (`eased`; engine build C3, the PI, 2026-10-30, Q8, "Merge; fix eased trials in C3"; the
    controller's ruling on the engine C3 plan's Task 15), **and the eased tries that paid**
    (`eased_paid`, answers counted and trials spent): its stage's number of trials and its targets
    leave them out
    (`block_trials`, `owed`; the engine C3 plan's review, I-7), and every other count keeps them."""

    attempted: int = 0
    completed: int = 0
    correct: int = 0
    spent: int = 0
    repeats: int = 0
    in_a_row: int = 0
    rig: int = 0
    forgiven: int = 0
    flagged: bool = False
    trials: int = 0
    presented: int = 0
    right: int = 0
    wrong: int = 0
    right_first: int = 0
    eased: int = 0
    eased_paid: int = 0


@dataclass(frozen=True, slots=True)
class ConditionReport:
    """One condition's counts in one block of the run, for the console and the run's end row (the
    PI, 2026-10-18, decisions 15 and 16): its `trials`, a trial and its drummed repeats one, and its
    `presentations`, every try; its answers `right` and `wrong`, every try's, and `right_first`,
    the trials whose first try was right; what it still `owed`, the ordinary `repeats` placed, the
    trials `moved_past` -- forgiven by its repeat limit or a person's clear -- and whether its limit
    flagged it as `possible_avoidance`; its `drummed` tries, and `failing`, the failed tries in a
    row of its trial being drummed now (one still in flight counts). **A run that ends in a fault
    can leave these counts one try ahead of the lines written**: a try is counted by
    `Scheduler.record` before its line is written, so a fault between the two leaves it counted
    and without a line."""

    block: str
    condition: str
    trials: int
    presentations: int
    right: int
    wrong: int
    right_first: int
    owed: int
    repeats: int
    moved_past: int
    possible_avoidance: bool
    drummed: int
    failing: int


@dataclass(frozen=True, slots=True)
class Shortfall:
    """Trials of a condition's debt forgiven in a block, recorded and shown (engine spec §16.6):
    `because` its repeat limit was reached by the animal's own failures (`CAP`), which is **flagged
    as possible avoidance**; or reached with tries the rig lost among them (`RIG`), named so and
    never flagged; or a person cleared them from the console (`CLEARED`, by `by`). `after_trial`,
    the number of the trial it happened after, or `None` for a clear before the run's first."""

    block: str
    condition: str
    trials: int
    because: str
    after_trial: int | None
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
    #: The default structure's counting table (`task.Trial.counting`), which a block's own replaces
    #: (`Block.counting`). `None` answers only what every structure shares -- an answer counted,
    #: the four of `task.REPEATED` owed -- and raises on what each declares (`_class`).
    counting: Counting | None = None
    #: **The training setting "first answers only"** (the PI, 2026-10-18): under drumming, a
    #: percentage rule judges only each trial's first answer, where by default it judges every
    #: answer in order ("Every answer"); a streak judges every answer either way. Off by default;
    #: a trainer switches it from the console (`train`).
    first_answers: bool = False
    #: **The training aid *clear*** (the PI, 2026-10-18, "Drumming and 'clear'"): whether a
    #: person may clear a trial from a condition's count (`clear`). Off by default -- until
    #: per-animal training profiles exist (XC-379), every run starts with it off -- and a trainer
    #: switches it from the console (`train`).
    clearing: bool = False
    #: **Each structure's counting table, by the structure's name** (engine build C2b): a condition
    #: naming a structure (`task.Condition.structure`) counts by that one's, unless its block
    #: counts by a table of its own; a condition naming none, or one missing here, by `counting`'s
    #: (the PI, 2026-10-07: "each condition names its own" structure).
    countings: dict = field(default_factory=dict)
    #: **How the blocks follow one another** (`task.BlockOrder`; engine spec §13.5; engine build
    #: C2b): `Fixed`, each once in order, by default. A random order draws from a generator of its
    #: own, seeded from `seed`, so it replays and leaves every condition's draw as it was.
    order: BlockOrder = field(default_factory=Fixed)
    #: **The place in the run's sequence of blocks it starts at**, from 0 (the pop-out search
    #: build's Task 6; its design §3.6, "the trainer picks" the stage): a later block of a plan
    #: whose order plays its blocks by their places -- in order, over and over, or stage by stage
    #: (`start_at`) -- the blocks before it still there to move or fall back to.
    start: int = 0
    _rng: random.Random = field(init=False, repr=False)
    _order_rng: random.Random = field(init=False, repr=False)
    #: The open block's place in the run's sequence of blocks, from 0, and the block types that
    #: sequence has drawn so far, by index into `blocks`, for a random order.
    _position: int = field(init=False, default=0, repr=False)
    _sequence: list = field(init=False, default_factory=list, repr=False)
    #: Whether the open block's time has run out (`expire`).
    _expired: bool = field(init=False, default=False, repr=False)
    #: The open block's last answers judged, 1 right and 0 wrong, as long as a `ByCriterion`
    #: order's fall-back rule's window: what that rule reads.
    _back: deque = field(init=False, default_factory=deque, repr=False)
    #: **Under a confirmed progression** (`ByCriterion.confirm`; the pop-out search build,
    #: 2026-11-07), the open stage's last answers as its suggestion's bars judge them (`_bar`),
    #: each `(right, at its hardest step)`: toward moving up, as long as its criterion's window
    #: (`_up`), and toward moving back, as long as the fall-back's (`_down`); and whether the trial
    #: being drummed has had such an answer yet (`_bar_answered`). Empty otherwise. **For the
    #: trainer's panel** (`answers`; the pop-out search build's Task 7), the stage's last answers
    #: shown (`_shown`), each trial's first, as long as `_down`, each with its outcome's wire string
    #: and the trials left out of the bars just before it, by outcome (`(right, outcome, aside)`),
    #: and `_aside` counting those left out since the last such answer, by outcome: **both start
    #: afresh only as a stage opens** (the build's final fixes, on Task 7's report), never as a
    #: person holds a move or changes the pool, which start the bars' own windows afresh.
    _up: deque = field(init=False, default_factory=deque, repr=False)
    _down: deque = field(init=False, default_factory=deque, repr=False)
    _bar_answered: bool = field(init=False, default=False, repr=False)
    _shown: deque = field(init=False, default_factory=deque, repr=False)
    _aside: dict = field(init=False, default_factory=dict, repr=False)
    #: How each block left behind ended, in order, and whether the open one's end is recorded
    #: (`close`): the run's end row's.
    ended: list = field(init=False, default_factory=list)
    closed: bool = field(init=False, default=False)
    #: The block types opened since the last trial was drawn or a person's move (the progress
    #: check, `stalled`).
    _opened: set = field(init=False, default_factory=set, repr=False)
    #: **The open block's number in the session's stream** (`levels.Position.block_in_session`),
    #: which the loop gives as the block's first trial opens it with `BLOCK_START` (`taskd`), or
    #: `None` while it has run no trial: what its `BlockEnd` records.
    in_session: int | None = field(init=False, default=None)
    #: At a training progression's top stage, the trial after which its rule was first met
    #: (`ends`), or `None`: what its `BlockEnd` records and the console shows.
    passed_at: int | None = field(init=False, default=None)
    #: How many times the run's plan fell back a stage (`FALL_BACK`), for the console's plan row.
    fell_back: int = field(init=False, default=0)
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
    #: Whether this drum chain (a trial's first try and its drummed repeats) has had a judged
    #: trial: an answer, or what the block's own table scores (`_scored`).
    _answered: bool = field(init=False, default=False, repr=False)
    #: Whether this drum chain's trial is counted eased toward its stage's number of trials
    #: (`Counts.eased`, a training progression's only): its first try was eased, or the try that
    #: paid it (the controller's ruling on the engine C3 plan's Task 15).
    _eased_chain: bool = field(init=False, default=False, repr=False)
    #: The blocks left behind's `ConditionReport`s, in order (`report`).
    _reports: list = field(init=False, default_factory=list, repr=False)
    #: The run's trials so far, a trial and its drummed repeats one (the PI, 2026-10-18: "200
    #: trials; drummed repeats inside them"): each try recorded that is no drum's repeat. What the
    #: console and the run's end row count as trials (the controller's rulings I1 and M5).
    trials: int = field(init=False, default=0)
    #: **The open block's designed order** (engine build C3), when it plays one: its own generator,
    #: `random.Random(f"design:{seed}:{occurrence}")`, the occurrence the number of blocks the run
    #: has ended as it opens, so each opening -- a person's *back one* included -- plays a plan of
    #: its own, replayed by the seed (the engine C3 plan's Appendix B item 7), and no draw of it
    #: moves `_rng`'s.
    _design: random.Random | None = field(init=False, default=None, repr=False)
    #: A sequence-balanced block's plan, its condition names in the order planned; the next place
    #: to play in it; and the places in one cycle.
    _plan: tuple = field(init=False, default=(), repr=False)
    _place: int = field(init=False, default=0, repr=False)
    _cycle: int = field(init=False, default=1, repr=False)
    #: A priming block's values of its feature, `(form, value, names)` each, grouped by
    #: `declarations.canonical`; each value's pass of its conditions, shuffled; its runs so far,
    #: `[value's index, length]` each; the next run, decided as the last one ended and taken with
    #: its first trial; the shown trials of the run playing now; and whether a try at its place
    #: has been shown.
    _groups: list = field(init=False, default_factory=list, repr=False)
    _passes: dict = field(init=False, default_factory=dict, repr=False)
    _runs: list = field(init=False, default_factory=list, repr=False)
    #: A priming block's run lengths still to come from a prepared list's pass (`_run_length`).
    _lengths: deque = field(init=False, default_factory=deque, repr=False)
    _coming: tuple | None = field(init=False, default=None, repr=False)
    _at: int = field(init=False, default=0, repr=False)
    _seen: bool = field(init=False, default=False, repr=False)
    #: A designed block's trial to show again at once (`again_at_once`): `(condition, repeat_of,
    #: planned)`, or `None`.
    _again: tuple | None = field(init=False, default=None, repr=False)

    def __post_init__(self) -> None:
        self._rng = random.Random(self.seed)
        self._order_rng = random.Random(f"blocks:{self.seed}")
        first = self._type_at(self.start)
        if first is None:
            raise IndexError("a plan with no block to start has nothing to run")
        self._position = self.start
        self._index = first
        self._opened = {first}
        self._back = self._fall_back_window()
        self._up, self._down = self._bar_windows()
        self._shown = deque(maxlen=self._down.maxlen)
        self._counts = {c.name: Counts() for c in self.block.conditions}
        self._begin()
        self._refill()

    def _begin(self) -> None:
        """**Set out the open block's designed order as it opens** (engine build C3), or clear the
        last block's: a sequence-balanced block's plan (`variation.balanced_sequence`; the PI,
        2026-10-30, Q5a), or a priming block's values and its first run (Q6), each drawn from the
        block's own generator (`_design`)."""
        order = self.block.order
        self._again, self._plan, self._place = None, (), 0
        self._groups, self._passes, self._runs = [], {}, []
        self._lengths.clear()
        self._coming, self._at, self._seen = None, 0, False
        if not isinstance(order, (SequenceBalanced, Priming)):
            self._design = None
            return
        self._design = random.Random(f"design:{self.seed}:{len(self.ended)}")
        names = [condition.name for condition in self.block.conditions]
        if isinstance(order, SequenceBalanced):
            self._plan = balanced_sequence(names, order.depth, order.cycles, self._design)
            # Each cycle the linear sequence, its first `depth - 1` places a lead-in (the PI,
            # 2026-10-31, on the engine C3 plan's Appendix B, item 1).
            self._cycle = len(names) ** order.depth + order.depth - 1
            return
        for condition in self.block.conditions:
            value = condition.values.get(order.feature)
            form = canonical(value)
            group = next((group for group in self._groups if group[0] == form), None)
            if group is None:
                self._groups.append((form, value, [condition.name]))
            else:
                group[2].append(condition.name)
        if self._groups:
            self._coming = self._new_run(None)
        for index in range(len(self._groups)):
            self._passes[index] = deque()
            self._refill_pass(index)

    def _refill_pass(self, group: int) -> None:
        """A priming value's conditions in a new shuffled pass. Drawn as the block opens and as a
        pass is used up (`_take`), never as the next trial is looked at, so reading `drawable`
        moves nothing in the seeded plan."""
        shuffled = list(self._groups[group][2])
        self._design.shuffle(shuffled)
        self._passes[group].extend(shuffled)

    @property
    def _designed(self) -> bool:
        """Whether the open block plays a designed order (engine build C3): its plan, not its
        targets, gives its trials, and a break is not shown again unless it comes back at once."""
        return isinstance(self.block.order, (SequenceBalanced, Priming))

    @property
    def planned(self) -> tuple | None:
        """**The open block's plan** (engine build C3): a sequence-balanced block's condition names
        in the order planned, played or not; a priming block's runs as far as it has played,
        `(value, length)` each; `None` for any other block. What its `BlockEnd` records."""
        order = self.block.order
        if isinstance(order, SequenceBalanced):
            return self._plan
        if isinstance(order, Priming):
            return tuple((self._groups[group][1], length) for group, length in self._runs)
        return None

    @property
    def waiting(self) -> frozenset[int]:
        """**The trials that will be shown again**, by number (engine build C3): a repeat waiting
        for its slot, a drum's trial, a designed block's trial again at once. What the trial loop
        keeps a trial's drawn values for, so a repeat that keeps them finds them."""
        return frozenset(self.waiting_conditions)

    @property
    def waiting_conditions(self) -> dict[int, str]:
        """**Each trial that will be shown again, by number, with its condition's name** (engine
        build C3): `waiting`'s trials, each of the open block. What the live check of trials no
        animal can get right judges with the `same` values each keeps (`taskd.Session.
        _kept_trials`; the controller's ruling of 2026-10-30 on the engine C3 plan's fuzz)."""
        named = {number: condition for _, number, condition in self._due}
        if self._drum is not None:
            named[self._drum[1]] = self._drum[0]
        if self._again is not None:
            named[self._again[1]] = self._again[0]
        return named

    @property
    def block(self) -> Block:
        return self.blocks[self._index]

    def _type_at(self, position: int) -> int | None:
        """The block type the run's `position`th block is, by index into `blocks`, or `None` past
        the plan's end (engine spec §13.5): **in order once** (`Fixed`); **over and over**
        (`Cyclic`), its `cycles` passes; **in shuffled rounds** (`Balanced`: each round every type
        once, the last round partial where the count is not whole rounds); **each drawn at
        random** (`Random`); **stage by stage** (`ByCriterion`, which moves up and back by its
        rules, `_next_position`). A random sequence is drawn as far as it is read, from
        `_order_rng`, and kept, so the same position is always the same type; a balanced round
        never starts with the type the round before it ended with."""
        n = len(self.blocks)
        order = self.order
        if n == 0:
            raise IndexError("a plan with no block to start has nothing to run")
        if position < 0:
            return None
        if isinstance(order, Cyclic):
            if order.cycles is not None and position >= order.cycles * n:
                return None
            return position % n
        if isinstance(order, (Balanced, Random)):
            if order.blocks is not None and position >= order.blocks:
                return None
            while len(self._sequence) <= position:
                if isinstance(order, Balanced):
                    round_ = list(range(n))
                    self._order_rng.shuffle(round_)
                    if self._sequence and round_[0] == self._sequence[-1] and n > 1:
                        # **Never back-to-back** (the PI, 2026-10-19: "Each new round starts with
                        # a different type than the last one played, so every block boundary is a
                        # real switch; still balanced in counts"): the round turned by one, still
                        # a round, drawing nothing more from the seed.
                        round_ = round_[1:] + round_[:1]
                    self._sequence.extend(round_)
                else:
                    self._sequence.append(self._order_rng.randrange(n))
            return self._sequence[position]
        return position if position < n else None

    def _next_position(self, reason: str) -> int | None:
        """Where the run's sequence goes as the open block ends for `reason`: back one for a
        fall-back or a person's *back one*, else on one. `None` before the first."""
        if reason in (FALL_BACK, BACK):
            return self._position - 1 if self._position > 0 else None
        return self._position + 1

    def _fall_back_window(self) -> deque:
        rule = self.order.fall_back if isinstance(self.order, ByCriterion) else None
        return deque(maxlen=rule[1] if rule is not None and rule[1] >= 1 else 0)

    @property
    def _confirming(self) -> bool:
        """Whether the plan is a confirmed progression (`ByCriterion.confirm`; the PI, 2026-11-07,
        "Rig suggests, trainer confirms"): no stage moves up or back on its rules, which the rig
        suggests instead (`suggestion`), a person confirming each move (`move`)."""
        return isinstance(self.order, ByCriterion) and self.order.confirm

    @property
    def confirming(self) -> bool:
        """Whether the plan is a confirmed progression (`_confirming`), for the session's changes
        feed (the pop-out search build)."""
        return self._confirming

    def _bar_windows(self) -> tuple[deque, deque]:
        """The open stage's two windows for its suggestion's bars, empty: as long as its criterion's
        window toward moving up, and as long as the fall-back's toward moving back -- each of no
        length where there is no such rule, or the plan is no confirmed progression."""

        def window(rule) -> deque:
            return deque(maxlen=rule[1] if self._confirming and rule is not None
                         and rule[1] >= 1 else 0)

        return window(self.block.criterion), window(getattr(self.order, "fall_back", None))

    def _answers_for(self, move: str) -> deque:
        """The window `move`'s bar reads: the one toward moving up for a move up and for widening
        the pool (`MOVE_WIDEN`; "Same rule: rig suggests"), the one toward moving back for a move
        back."""
        return self._down if move == MOVE_BACK else self._up

    def bar(self, move: str) -> tuple[int, int, bool]:
        """**The numbers a suggestion's bar reads now** (`suggestion`): how many of the last
        answers in its window were right, how many answers are in it, and whether every one was at
        the stage's hardest step -- toward moving up (`MOVE_UP`) or widening the pool
        (`MOVE_WIDEN`), one window, or back (`MOVE_BACK`)."""
        answers = self._answers_for(move)
        return (sum(answer[0] for answer in answers), len(answers),
                all(answer[1] for answer in answers))

    @property
    def answers(self) -> Answers | None:
        """**The open stage's last answers, and its bar to move up, for the trainer's panel**
        (`Answers`; the pop-out search build's Task 7; its design §3.5: "the last 50 trials'
        percent correct and errors by kind", the trials left out "shown beside it", §3.4), under a
        confirmed progression, else `None`: the last answers shown (`_shown`), which no hold and
        no change of the pool clears (the build's final fixes), and the bar to move up's own
        window. Read between trials, never in a frame: at most the two windows' answers, counted."""
        if not self._confirming:
            return None
        wrong: dict = {}
        left: dict = {}
        for right, outcome, aside in self._shown:
            if not right:
                wrong[outcome] = wrong.get(outcome, 0) + 1
            for said, count in aside:
                left[said] = left.get(said, 0) + count
        for said, count in self._aside.items():
            left[said] = left.get(said, 0) + count
        correct = sum(answer[0] for answer in self._shown)
        up_correct, up_of, _ = self.bar(MOVE_UP)
        criterion, fall_back = self.block.criterion, self.order.fall_back
        return Answers(correct, len(self._shown), self._shown.maxlen, wrong, left, up_correct,
                       up_of,
                       self._up.maxlen, None if criterion is None else criterion[0],
                       None if fall_back is None else fall_back[0])

    def _met_up(self) -> tuple[int, int, bool] | None:
        """The bar to move up's numbers (`bar`) where it is met -- its window full and at least
        the stage's criterion's proportion right -- else `None`, as under no confirmed
        progression, or in a stage with no criterion."""
        criterion = self.block.criterion
        if not self._confirming or criterion is None or not self._up.maxlen:
            return None
        right, of, hardest = self.bar(MOVE_UP)
        met = of >= self._up.maxlen and right / of >= criterion[0]
        return (right, of, hardest) if met else None

    @property
    def suggestion(self) -> Suggestion | None:
        """**What the rig suggests at this boundary**, under a confirmed progression
        (`ByCriterion.confirm`; the pop-out search build's design §3.4; the PI, 2026-11-07), or
        `None`, read between trials, never in a frame:

        - **up** to the next stage where the open stage's criterion is met ("80% correct, last 50
          trials") **at its hardest step** ("Hardest step reached, 80% there"): at least its
          proportion right of **the last window's answers given at the stage's hardest step** --
          its staircase at its last level, or any for a stage with none (`record`'s `hardest`) --
          the window full. An answer at an easier level is left out, neither counting nor
          breaking the window: a failure at the top steps a one-up staircase down, so a window
          that every answer had to share would ask for an unbroken run of right answers there,
          not 80%;
        - **back** to the stage below where fewer than the fall-back's proportion of its last
          window's first answers are right ("Below 50% of the last 50"), judged once that many
          are in, at any stage but the first, which has none below it.

        **Answers only**, as the stage's staircase classes them (`task.staircase_verdict`;
        TSK-33; the design's §3.4): a trial that moves no staircase -- no fixation, an early
        saccade, any whose stimulus never appeared -- is in neither window, and a look to empty
        space or leaving the target before its hold is a failure in both. A trial a person's
        change eased is in the window to move back, never in the one to move up (engine build C3;
        the PI, Q8). A met bar to move up counts before one to move back, as `ends` counts a met
        rule before a fall-back. Live: a suggestion whose bar stops being met is gone at the next
        boundary (the plan's Review Focus 2), and a person's move or hold starts its window
        afresh (`advance`, `decline`)."""
        if not self._confirming:
            return None
        above = self._type_at(self._position + 1)
        met = self._met_up()
        if above is not None and met is not None:
            return Suggestion(MOVE_UP, self.block.name, self.blocks[above].name, *met)
        below = self._type_at(self._position - 1)
        if below is not None and self._down.maxlen:
            right, of, hardest = self.bar(MOVE_BACK)
            if of >= self._down.maxlen and right / of < self.order.fall_back[0]:
                return Suggestion(MOVE_BACK, self.block.name, self.blocks[below].name, right, of,
                                  hardest)
        return None

    @property
    def widening(self) -> Suggestion | None:
        """**Whether the bar to widen the pool is met**, under a confirmed progression (`task.Pool`;
        the pop-out search build's design §3.2 and §3.4; the PI, 2026-11-07, "Same rule: rig
        suggests"): **the bar to move up, on its own window** -- the stage's criterion met on its
        last answers at its hardest step -- **judged over every pairing pooled**, at any stage,
        the top one included, which has none above it. A `Suggestion` to widen (`MOVE_WIDEN`), `to`
        `None`, or `None`; whether the pool has a pairing left to add is the session's to say
        (`taskd.Session._suggest`). One window meeting both bars, the move up and the widening are
        one prompt, the stage's first (the design's §3.4). Read between trials, never in a
        frame."""
        met = self._met_up()
        return None if met is None else Suggestion(MOVE_WIDEN, self.block.name, None, *met)

    def judged(self, outcome: Outcome | None, shown: bool, first_try: bool, eased: bool,
               hardest: bool) -> None:
        """**One trial of a run that stopped with its process, toward the open stage's bars**
        (the pop-out search build's Task 6; the plan's Review Focus 4): a resumed session's run
        going on from it gives each of that stage's trials here, between runs, in order, as its
        line and the run's record read (`taskd.went_on`), so its suggestion's windows are what
        they were -- judged by `_bar`, as `record` judges a trial now, and nothing else about the
        block counted."""
        if self._confirming:
            self._bar(outcome, shown, first_try, eased, hardest)

    def decline(self, move: str) -> None:
        """**A person holds instead of moving** (`link.Decline`; the PI, 2026-11-07, "Rig suggests,
        trainer confirms"): the window of the declined move starts afresh, so the rig suggests
        that move again only once a fresh window of answers meets its bar, never on the answers a
        person has already held on ("After 50 new tries", the PI, the same day). The other window
        goes on. A widening shares the window to move up (`_answers_for`), so a hold of either
        starts both afresh. **The last answers shown stay**, and the trials left out beside them
        (`_shown`; the build's final fixes, on Task 7's report, whose panel read "no answers yet"
        after a hold)."""
        self._answers_for(move).clear()

    def afresh(self) -> None:
        """**The open stage's bars start afresh** (the pop-out search build, 2026-11-07): its pool
        of pairings changed (`task.Pool`), and the bars judge the pairings pooled now (the
        design's §3.4: "the bar is judged over all the current pairings pooled"), so neither
        window keeps the answers given on the pool before. The staircase stays where it is
        ("a widening leaves the staircase where it is"), and so do the last answers shown
        (`_shown`), which are the stage's."""
        self._up.clear()
        self._down.clear()

    @property
    def _top(self) -> bool:
        """Whether the open block is a training progression's top stage (`ByCriterion`), where the
        animal keeps working once its rule is met (the PI, 2026-10-19, "Same, but top keeps
        going")."""
        return isinstance(self.order, ByCriterion) and self._position == len(self.blocks) - 1

    @property
    def moves_up(self) -> bool:
        """Whether the open block has a rule that moves the animal on, which a trial a live change
        eased is kept out of (`record`): its criterion, or a training progression's stage
        (`ByCriterion`), whose number of trials and targets leave eased trials out. Where the
        changes feed says a trial is kept out (`taskd._kept_out`; the engine C3 plan's engineering
        review, I-2)."""
        return self.block.criterion is not None or isinstance(self.order, ByCriterion)

    @property
    def plays_out(self) -> bool:
        """Whether the open block is a sequence-balanced one, which ends on its plan, never a
        criterion, so where `moves_up` is true it is a training progression's stage below the
        top (the load refuses one at the top), which moves up when its sequence is played out,
        eased trials or not (the PI, 2026-10-31, on the engine C3 plan's Appendix B, item 10,
        "Only warn at load"; `check`'s `sequence-stage-moves-up`): the changes feed says that of
        it, not that its trials are kept out (`taskd._kept_out`)."""
        return isinstance(self.block.order, SequenceBalanced)

    @property
    def _falls_back(self) -> bool:
        """Whether a training progression's fall-back rule is met (`ByCriterion.fall_back`): fewer
        than its proportion of the last window's answers right, judged once that many answers are
        in (the PI, 2026-10-19: "under 50% over the last 20", answers only) -- **each trial's first
        answer only** ("First answer only"; `record`) -- at any stage but the first, which has none
        below it. **Never under a confirmed progression**, whose fall-back the rig suggests
        instead (`suggestion`)."""
        if (not isinstance(self.order, ByCriterion) or self.order.fall_back is None
                or self._confirming):
            return False
        proportion, window = self.order.fall_back
        return (self._position > 0 and window >= 1 and len(self._back) >= window
                and sum(self._back) / len(self._back) < proportion)

    @property
    def ends(self) -> str | None:
        """**Why the open block ends at this boundary**, or `None` while it goes on (engine spec
        §13.5; engine build C2b): `RULE` once its own end rule is met (`finished`) -- **but at a
        training progression's top stage the animal keeps working**, its conditions drawn again
        (`past_targets`); `FALL_BACK` once its plan's fall-back rule is met; `TIME` once its time
        has run out (`expire`). **Never while a drummed trial waits** (the PI, 2026-10-18 and
        2026-10-19: "Finish the drum first"): that trial comes back until it is right, then the
        block ends. A met rule counts before a fall-back -- at the top stage too, which works on
        while its rule holds -- and either before the time. **The top stage's rule met the first
        time is noted** (`passed_at`; the engine C2b plan's science review, I1): the record and
        the console say when it passed. **Under a confirmed progression** (`ByCriterion.confirm`)
        neither its rule nor its fall-back ends a stage: the rig suggests the move
        (`suggestion`) and a person makes it (`move`); a stage's time running out still moves it
        up, a time limit being the task author's declaration and no judgment of the animal."""
        if self._drum is not None:
            return None
        if self.finished and not self._top and not self._confirming:
            return RULE
        self._note_passed()
        if self._falls_back and not self.finished:
            return FALL_BACK
        if self._expired:
            return TIME
        return None

    def _note_passed(self) -> None:
        """Note the trial after which a training progression's top stage first met its rule
        (`passed_at`; the engine C2b plan's science review, I1), asked at every boundary (`ends`)
        and before every draw (`next_trial`), so it names the trial that met it whoever asks.
        `None` while it has not, or when it was met before the run's first trial."""
        if self.passed_at is None and self._top and self.finished:
            self.passed_at = self._number - 1 if self._number else None

    @property
    def following(self) -> Block | None:
        """The block the open one is followed by if it ends now (`ends`), or `None` while it goes on
        and when the plan is done then."""
        reason = self.ends
        if reason is None:
            return None
        position = self._next_position(reason)
        index = None if position is None else self._type_at(position)
        return None if index is None else self.blocks[index]

    def following_if_expired(self, expired: bool) -> Block | None:
        """`following`, asked as if the open block's time had run out (`expire`) where `expired` is
        true, **without setting it**: the end is still decided where the loop decides it. What
        `taskd.Session._playing` asks at a boundary, so a value applied as a block ends by its
        time is judged by the block that follows, with no side effect on the boundary (a drum
        switch, `owed`)."""
        held = self._expired
        self._expired = held or expired
        try:
            return self.following
        finally:
            self._expired = held

    @property
    def next_block(self) -> Block | None:
        """The block the plan goes on to when the open one ends on its own rule or its time -- the
        next stage up in a training progression -- or `None` where the plan ends there: what the
        console shows as next (engine build C2b)."""
        index = self._type_at(self._position + 1)
        return None if index is None else self.blocks[index]

    def expire(self) -> None:
        """The open block's time has run out (`Block.time_limit_s`; the PI, 2026-10-19), read by the
        loop between trials on the time trials ran, pauses not counting: it ends at this boundary,
        or once a drummed trial waiting is right (`ends`)."""
        self._expired = True

    @property
    def expired(self) -> bool:
        return self._expired

    @property
    def drum_waiting(self) -> str | None:
        """The condition whose drummed trial waits to come back until it is right, or `None`: what
        holds a block's end (`ends`) and, in the loop, the run's time limit (the PI, 2026-10-19,
        "Finish the drum first", for both), and what a person's move drops."""
        return None if self._drum is None else self._drum[0]

    def because(self, reason: str) -> str:
        """Why the open block ends for `reason`, in words and with its numbers, for the console's
        changes feed (the engine C2b plan's science review, I2: "S2 -> S1: 8 of last 20 right"):
        its rule and what met it, the fall-back and the first answers that met it, or whose time
        ran out. **A designed block's rule is its plan** (engine build C3): a sequence-balanced
        block's played out or cut by its number of trials, a priming block's number of trials."""
        if reason == RULE and self._designed:
            if isinstance(self.block.order, SequenceBalanced) and self._place >= len(self._plan):
                return "its rule met: its planned sequence played out"
            return f"its rule met: {self.block_trials} trials run"
        if reason == RULE:
            met = []
            if self.block.criterion is not None:
                right = sum(self._window)
                met.append(f"{right} right in a row" if self.streak
                           else f"{right} of its last {len(self._window)} answers right")
            if self.block.trials is not None:
                met.append(f"{self.block_trials} trials run")
            return "its rule met: " + ", ".join(met + ["every target used up"])
        if reason == FALL_BACK:
            proportion = self.order.fall_back[0]
            return (f"fell back: {sum(self._back)} of its last {len(self._back)} first answers "
                    f"right, under {proportion:.0%}")
        if reason == TIME:
            return "its time ran out" + ("" if self.finished else ", its rule not met")
        if reason == RUN_TIME:
            return "the run's time ran out"
        return {NEXT: "moved on by hand", BACK: "moved back by hand"}.get(reason, "the run ended")

    @property
    def block_trials(self) -> int:
        """The open block's trials so far, a trial and its drummed repeats one: what its number of
        trials counts (`Block.trials`). **In a training progression a trial a live change eased is
        left out** (engine build C3; the PI, 2026-10-30, Q8, "Merge; fix eased trials in C3": eased
        trials do not count toward moving up; the engine C3 plan's review, I-7): a stage ending on
        its number of trials is not passed on eased trials (`Counts.eased`), a drummed trial whose
        paying try was eased among them (the controller's ruling on the engine C3 plan's Task
        15)."""
        return sum(counts.trials - counts.eased for counts in self._counts.values())

    @property
    def stalled(self) -> bool:
        """**The per-advance progress check** (engine spec §13.5: "`taskd`'s guard against a
        spinning plan becomes a per-advance progress check"; engine build C2b): since the last
        trial drawn, or a person's last move, the plan has opened every one of its block types and
        each ended before it drew a trial, so no block it can open will draw one and moving on again
        would spin. The run then ends, saying why (the PI, 2026-10-19, "End run with a
        sentence")."""
        return self._opened >= set(range(len(self.blocks)))

    @property
    def drawable(self) -> bool:
        """Whether the open block can draw a trial now: a drummed trial waits, a repeat waits, or a
        condition can be drawn by its order (`_peek`). A block that cannot, and does not end, has
        nothing to show (the PI, 2026-10-19: the run ends, saying why). **A designed block's trial
        again at once waits too** (engine build C3), and its next is its plan's (`_peek`)."""
        return (self._drum is not None or self._again is not None or bool(self._due)
                or self._peek() is not None)

    def _refill(self) -> None:
        """Queue the next draw, however this block declares its order.

        Always from the seeded generator, so a session's condition order is
        reconstructable -- a randomisation nobody can reproduce is one nobody can
        rule out as an explanation. **A designed block queues none** (engine build C3):
        its plan gives its trials (`_planned_next`), from a generator of its own.
        """
        if self._designed:
            return
        pending = [c.name for c in self.block.conditions if self._drawable(c.name)]
        if not pending:
            return
        order = self.block.order
        if isinstance(order, Shuffled):
            self._rng.shuffle(pending)
            self._queue.extend(pending)
            return

        # **A condition of weight 0 is never drawn** (the engine C2b plan's engineering review,
        # I2), so it is left out: a block whose every condition still drawable weighs 0 has nothing
        # to draw (`drawable`), and the loop ends the run with its sentence where
        # `random.choices` raised. The rest draw as the seed gave them: a weight of 0 was never
        # chosen.
        pending = [name for name in pending if order.weights.get(name, 1.0) > 0]
        if not pending:
            return
        if isinstance(order, Constrained):
            allowed = [name for name in pending if not self._runs_long(name)]
            if allowed:
                pending = allowed
        weights = [order.weights.get(name, 1.0) for name in pending]
        self._queue.append(self._rng.choices(pending, weights=weights, k=1)[0])

    def _drawable(self, condition: str) -> bool:
        """Whether an ordinary draw may give `condition`: it still owes, or the block is past its
        targets (`past_targets`), and no repeat of it is waiting for its slot -- the repeat is its
        next trial (engine spec §16.3)."""
        return ((self.owed(condition) > 0 or self.past_targets)
                and all(name != condition for _, _, name in self._due))

    @property
    def past_targets(self) -> bool:
        """Whether the open block ends on a criterion or a number of trials, or is a training
        progression's top stage, and every target is used up: **then every condition of the block
        is drawn again, by its order, until the criterion is met** (the PI, 2026-10-18: "conditions
        keep coming until both hold"), the number of trials is run (engine build C2b), or -- at the
        top stage -- until a time limit, a stop or the session's end (the PI, 2026-10-19, "Same, but
        top keeps going"). Nothing is owed then, so a break is not shown again and nothing is
        forgiven, but a drummed trial still comes back until it is right (`record`). **Never in
        a designed block** (engine build C3): its plan gives its trials, and nothing is drawn past
        it. **Every stage of a confirmed progression** (`ByCriterion.confirm`) works on as a top
        stage does, until a person moves the run, since none moves of itself."""
        if self._designed:
            return False
        if (self.block.criterion is None and self.block.trials is None and not self._top
                and not self._confirming):
            return False
        # The terms of `owed`, read from the counts: `owed` finds its condition by name.
        counts = self._counts
        return all(
            c.target <= counts[c.name].completed + counts[c.name].spent + counts[c.name].forgiven
            - counts[c.name].eased_paid
            for c in self.block.conditions)

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
        still queued), and the queue refilled once when empty; `None` when nothing is drawable.
        **A designed block's is its plan's** (`_planned_next`; engine build C3)."""
        if self._designed:
            return self._planned_next()
        for _ in range(2):
            while self._queue and not self._drawable(self._queue[0]):
                self._queue.popleft()
            if self._queue:
                return self._queue[0]
            self._refill()
        return None

    def _planned_next(self) -> str | None:
        """A designed block's next trial's condition, its place left unplayed (engine build C3): a
        sequence-balanced block's next place, `None` once its plan is played out; a priming
        block's next condition of the value its place plans, from that value's shuffled pass (the
        PI, 2026-10-30, Q6). **A priming block's place moves on first past a trial whose stimulus
        appeared** (`_move_on`); a trial that ended before it leaves its place to the next, so a
        break before the stimulus loses no place."""
        if isinstance(self.block.order, SequenceBalanced):
            return self._plan[self._place] if self._place < len(self._plan) else None
        if self._seen:
            self._move_on()
        run = self._coming if self._coming is not None else (self._runs[-1] if self._runs else None)
        if run is None:
            return None
        return self._passes[run[0]][0]

    def _move_on(self) -> None:
        """**A priming block's place moves on** past a trial whose stimulus appeared, its last try
        over (engine build C3; the PI, 2026-10-30, Q6, "Both of the last two"): under a `chance`,
        the next trial repeats this run's value with that chance, else a switch; under `runs`, the
        run goes on until it has shown its drawn length, then a switch. "Last" is the last trial
        whose stimulus appeared, and a run counts only those (the engine C3 plan's Appendix B,
        item 6)."""
        order = self.block.order
        self._seen = False
        self._at += 1
        if order.runs is None:
            if self._design.random() < order.chance:
                return
        elif self._at < self._runs[-1][1]:
            return
        self._coming = self._new_run(self._runs[-1][0])
        self._at = 0

    def _new_run(self, previous: int | None) -> tuple[int, int]:
        """A priming block's next run, `(value's index, length)`: **a switch picks another value at
        random** (engine build C3, the spec's §5), any value for the block's first; its length is
        drawn from `runs` -- `(low, high)`, whole numbers from the lowest to the highest, or a
        distribution (`_run_length`) -- or under a `chance` counts its shown trials from 0."""
        order = self.block.order
        others = [group for group in range(len(self._groups)) if group != previous] or [previous]
        group = others[self._design.randrange(len(others))]
        if order.runs is None:
            return group, 0
        if isinstance(order.runs, tuple):
            return group, self._design.randint(*order.runs)
        return group, self._run_length(order.runs)

    def _run_length(self, runs) -> int:
        """**A priming run's length drawn from a distribution** (the C3 plan's science review, I-8:
        lengths drawn evenly make a switch ever more expected along a run; a non-aging draw keeps
        it nearly as likely after every trial): a prepared list's items in passes, each once a
        pass, shuffled by the block's design generator unless it plays in order; any other kind's
        value at a unit that generator draws, rounded down, at least 1
        (`variation.run_length`)."""
        if isinstance(runs, Listed):
            if not self._lengths:
                items = list(runs.values)
                if not runs.in_order:
                    self._design.shuffle(items)
                self._lengths.extend(items)
            return max(1, int(self._lengths.popleft() // 1))
        return run_length(runs, self._design.random())

    def _take(self) -> dict:
        """Play a designed block's next place (engine build C3), its condition `_planned_next`
        gave, and return the place for its `Draw.planned`: a sequence-balanced block's cycle and
        position, each from 0, and whether the place is its cycle's lead-in, one of its first
        `depth - 1`, which only precede what follows (the PI, 2026-10-31); a priming block's run
        from 0, `switch` true for each try at the run's first place until one has shown its
        stimulus, and the value it plans."""
        if isinstance(self.block.order, SequenceBalanced):
            place = self._place
            self._place += 1
            position = place % self._cycle
            return {"cycle": place // self._cycle, "position": position,
                    "lead_in": position < self.block.order.depth - 1}
        if self._coming is not None:
            self._runs.append(list(self._coming))
            self._coming = None
        group = self._runs[-1][0]
        self._passes[group].popleft()
        if not self._passes[group]:
            self._refill_pass(group)
        return {"run": len(self._runs) - 1, "switch": self._at == 0,
                "value": self._groups[group][1]}

    def _report(self, condition: str) -> ConditionReport:
        counts = self._counts[condition]
        waiting = self._drum is not None and self._drum[0] == condition
        # **A drummed try still in flight counts too**: `next_trial` cleared `_drum` at its draw, so
        # a run that faults or is stopped mid-try would otherwise read 0 failed tries in a row.
        flying = (self.drawn is not None and self.drawn.drummed
                  and self.drawn.condition.name == condition
                  and counts.attempted > counts.presented)
        return ConditionReport(
            self.block.name, condition, counts.trials, counts.presented, counts.right,
            counts.wrong, counts.right_first, self.owed(condition), counts.repeats,
            counts.forgiven, counts.flagged, counts.presented - counts.trials,
            self._tries if waiting or flying else 0,
        )

    @property
    def block_report(self) -> tuple:
        """The open block's `ConditionReport`s, one per condition in its order: the console's."""
        return tuple(self._report(c.name) for c in self.block.conditions)

    @property
    def report(self) -> tuple:
        """Every block's `ConditionReport`s so far, in order, the open one's last: what the run's
        end row records (the PI, 2026-10-18: "written into the run's end record as well")."""
        return tuple(self._reports) + self.block_report

    def counts(self, condition: str) -> Counts:
        return self._counts[condition]

    def owed(self, condition: str) -> int:
        """Target minus what paid -- the answers counted and the trials spent -- and what was
        forgiven (§16.6), **never minus attempted**: an owed trial produced no datum, so it left
        the condition owing exactly what it owed before. **In a training progression an eased
        trial pays nothing toward its stage's targets** (`Counts.eased_paid`; engine build C3, the
        engine C3 plan's review, I-7), so its condition is drawn on. **A sequence-balanced block
        owes its plan's places** of the condition not yet played, and one shown again at once,
        until it is cut by its number of trials or a time limit, then **nothing** (the plan's
        review, I-3), its places unplayed in its `planned` and in no shortfall."""
        if isinstance(self.block.order, SequenceBalanced):
            if self._expired or (self.closed and self.ended[-1].ended in (TIME, RUN_TIME)):
                return 0
            again = int(self._again is not None and self._again[0] == condition)
            if self.block.trials is not None and self.block_trials >= self.block.trials:
                return again
            return self._plan[self._place:].count(condition) + again
        target = next(c.target for c in self.block.conditions if c.name == condition)
        counts = self._counts[condition]
        return max(0, target - counts.completed - counts.spent - counts.forgiven
                   + counts.eased_paid)

    def _structure(self, condition: str) -> Counting | None:
        """The counting table of the structure `condition` plays (engine build C2b): the one it
        names (`task.Condition.structure`, read in `countings`), else the default's (`counting`).
        What counts as an answer, and the repeat limit where its block sets none, are its."""
        named = next(c for c in self.block.conditions if c.name == condition).structure
        if named is None:
            return self.counting
        return self.countings.get(named, self.counting)

    def _table(self, condition: str) -> Counting | None:
        """The table `condition`'s trials count by: its block's own, else its structure's.
        (`_class` still asks the structure's whether no response is an answer: what counts as one
        is the structure's.)"""
        own = self.block.counting
        return own if own is not None else self._structure(condition)

    def _cap(self, condition: str) -> int | None:
        """`condition`'s repeat limit in the open block: its block's own table's, **else its
        structure's** -- a block that counts by a table of its own keeps the task's limit unless its
        table sets one (the PI, 2026-10-18: "No: the task's limit applies unless the block sets its
        own") -- a number, or `task.NO_LIMIT`, which removes it (XC-380). `None`, no limit."""
        own = self.block.counting
        if own is not None and own.cap is not None:
            return None if own.cap == NO_LIMIT else own.cap
        structure = self._structure(condition)
        if structure is None or structure.cap == NO_LIMIT:
            return None
        return structure.cap

    def _answer(self, outcome: Outcome | None, condition: str) -> bool:
        """Whether `outcome` is an answer, right or wrong (the PI, 2026-10-18): one of
        `task.ANSWERS` -- a correct answer, a correct rejection, a wrong target, a false alarm, an
        early or a late response or error -- or no response where `condition`'s structure makes
        withholding an answer, a miss (`Counting.withholding`, the structure's, as `_class` reads
        it). A trial with no answer -- a break, no fixation, a lost tracker, a fault, a hang -- is
        none."""
        if outcome in ANSWERS:
            return True
        structure = self._structure(condition)
        return (outcome is Outcome.NO_RESPONSE and structure is not None
                and structure.withholding)

    def _scored(self, outcome: Outcome | None) -> bool:
        """Whether the open block's own table scores `outcome` though it is no answer, so its rule
        judges it wrong, never right. Two outcomes only, and only where the block's table gives
        them `COUNTED`: a broken hold (`Family.BREAKS`), for a block training a hold (the PI,
        2026-10-18, decision 17: "Only where a block itself declares a broken hold as a scored trial
        (a hold-training block) does it count as a miss toward the percentage. Everywhere else,
        breaks stay out."), and a failure to acquire fixation (`Outcome.NO_FIXATION`), for a block
        training looking at the fixation point (decision 19: "Yes, where the block says so", "Same
        rule as broken holds ... Lost tracking and rig faults never count against the animal"). A
        hang, a trial that reached the longest trial (`None`), counts as `HANG_COUNTS_AS`, no
        fixation, and is judged as that is. Never a rig outcome (`Family.RIG`), never no response,
        never anything else, whatever the table pays it."""
        own = self.block.counting
        if own is None:
            return False
        if outcome is None:
            outcome = HANG_COUNTS_AS
        if outcome.family is not Family.BREAKS and outcome is not Outcome.NO_FIXATION:
            return False
        return own.outcomes.get(outcome.value) == COUNTED

    @property
    def _first_answers(self) -> bool:
        """Whether a rule judges only each trial's first answer: the training setting
        `first_answers` is on and the block's rule is a percentage. **A rule of proportion 1.0 is a
        streak**, "N correct in a row", which judges every answer in order whatever the setting
        (the PI, 2026-10-18: "Every answer counts in order")."""
        criterion = self.block.criterion
        return self.first_answers and criterion is not None and not self.streak

    @property
    def streak(self) -> bool:
        """Whether the open block's rule is a streak, "N correct in a row": a criterion of
        proportion 1.0, which the training setting `first_answers` leaves judging every answer."""
        criterion = self.block.criterion
        return criterion is not None and criterion[0] >= 1.0

    def _class(self, outcome: Outcome | None, shown: bool, condition: str) -> str:
        """What `outcome` does to `condition`'s count, by the block's table or its structure's
        (`task.Counting.of`). **With neither**, what every structure shares still answers -- an
        answer counted, shown or not; the four of `task.REPEATED`, a hang and a break before the
        stimulus owed -- and an outcome each structure declares for raises: no default stands in
        for a declaration (the PI, 2026-10-11), and `check.check_task` refuses a run's structure
        without one. **Where the structure's table makes no response an answer** (`withholding`), a
        block's own table classes `NO_RESPONSE` as it classes `FALSE_ALARM`, the withholding
        design's other wrong answer, whatever it declares for no response: what counts as an
        answer is the structure's, as `appears` is (the PI's decision 6, 2026-10-11,
        "'No response' ... is a miss (counts, used up)"; the review of build C2a's Task 3).
        **Where the structure does not withhold**, a block's table's own `withholding` is not read
        either: no response is no answer under any block (the controller's ruling M8 on the
        plan's revision review)."""
        table = self._table(condition)
        structure = self._structure(condition)
        if outcome is Outcome.NO_RESPONSE and self.block.counting is not None:
            if structure is not None and structure.withholding:
                return self.block.counting.of(Outcome.FALSE_ALARM, shown)
            table = replace(self.block.counting, withholding=False)
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
        """The open block ends now and the plan has no block after it: the *run* is out of plan.

        Separate from `finished`, which has always been about the current block
        alone. Nothing advanced past a block until 2026-09-06, so a two-block
        scheduler ran its first block forever -- and nothing noticed, because
        `taskd` never imported this module. **Since engine build C2b** the block after
        it is its plan's order's (`ends`, `following`): a training progression's top
        stage is never done by its rule, only by its time.
        """
        return self.ends is not None and self.following is None

    def advance(self, reason: str = RULE, by: object = None) -> Block:
        """Move to the block the plan's order gives as the open one ends for `reason` (`ends`, or a
        person's `NEXT` or `BACK`), and start it empty; the open block's end is recorded (`close`).

        **Counters and the criterion window are reset**, because they are properties
        of a block and not of a session: a criterion carried across would be met
        before its own block had run a trial, on evidence from a different task
        configuration entirely. `requeued` is not reset -- it is the session's log of
        what had to be run again, and that reads across blocks. **A block falling back
        or stepped back to starts fresh too** (the PI, 2026-10-19: "Move back one stage,
        starting it fresh").
        """
        position = self._next_position(reason)
        index = None if position is None else self._type_at(position)
        if index is None:
            raise IndexError(
                f"block {self.block.name!r} is the last block; a session that ran "
                f"off the end of its plan would draw from a block that does not exist"
                if reason not in (FALL_BACK, BACK)
                else f"block {self.block.name!r} is the plan's first; there is no block before it"
            )
        self._reports.extend(self.block_report)
        self.close(reason, by)
        self.fell_back += reason == FALL_BACK
        self._position, self._index = position, index
        self.closed = False
        if reason in (NEXT, BACK):
            # **A person's move is not the plan spinning** (the engine C2b plan's engineering
            # review, I1): the progress check counts afresh from it, so a block moved to that owes
            # nothing cannot make a plan whose other blocks draw look stalled.
            self._opened = {index}
        else:
            self._opened.add(index)
        self.in_session = None
        self.passed_at = None
        self._counts = {c.name: Counts() for c in self.block.conditions}
        self._queue.clear()
        self._window.clear()
        self._back = self._fall_back_window()
        self._up, self._down = self._bar_windows()
        self._shown = deque(maxlen=self._down.maxlen)
        self._aside = {}
        self._drawn.clear()
        self._due.clear()
        self._drum = None
        self._expired = False
        if self._switched != "run" and not self._carried:
            self._switched = None
        self._carried = False
        self._begin()
        self._refill()
        return self.block

    def close(self, reason: str, by: object = None) -> None:
        """Record how the open block ended (`BlockEnd`), once: by `advance`, or by the run as it
        ends with the block open. **A block its time ended writes what it still owed as not run**
        (the PI, 2026-10-19: "Trials it still owed are recorded as not run, 'time ran out'"): a
        `Shortfall` per condition owing, `because` `TIME` -- or `RUN_TIME`, the run's time --
        forgiving nothing. **A sequence-balanced block a time limit cuts owes nothing** (engine
        build C3; the engine C3 plan's review, I-3): the places it did not play are in its plan
        (`planned`, which the end records), never a shortfall."""
        if self.closed:
            return
        after = self._number - 1 if self._number else None
        if reason in (TIME, RUN_TIME) and not isinstance(self.block.order, SequenceBalanced):
            for c in self.block.conditions:
                owed = self.owed(c.name)
                if owed:
                    self.shortfalls.append(Shortfall(self.block.name, c.name, owed, reason, after))
        self.ended.append(BlockEnd(self.block.name, reason, by, after, self._position,
                                   self.in_session, self.passed_at, self.planned))
        self.closed = True

    def move(self, step: str, by: object = None) -> str | None:
        """**A person moves the run on to the next block, or back one** (the PI, 2026-10-19,
        "'Next' and 'back one'": "Both directions by hand, each recorded with who"): `NEXT` to the
        block the plan's order gives next, the next stage up in a training progression; `BACK` to
        the block before the open one in the run's sequence, the stage below, started fresh. At
        once, a drummed trial waiting dropped. Returns why nothing moved -- there is no such block
        -- or `None`."""
        if step not in (NEXT, BACK):
            raise ValueError(f"a block is moved {NEXT} or {BACK}, not {step!r}")
        position = self._next_position(step)
        if position is None or self._type_at(position) is None:
            return (
                f"block {self.block.name!r} is the last its plan gives, so there is no next block; "
                f"stop ends the run"
                if step == NEXT
                else f"block {self.block.name!r} is the first of the run's blocks, so there is no "
                f"block before it"
            )
        self.advance(step, by)
        return None

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
    def drumming_switched(self) -> str | None:
        """What `drumming` reads for the block a switch made now is for, had this switch not been
        made: the next block's when the switch would be carried to it (`drum`; `advance` keeps a
        run's switch and resets the rest, leaving the next block's own `drum`, and keeps a switch
        already carried), else this one's."""
        following = self.following
        if following is not None:
            if self._carried:
                # A switch already carried to the next block in this drain: it is what that
                # block reads (`advance` keeps it), not that block's own declaration.
                return self._switched if self._switched in ("run", "block") else None
            if self._switched == "run":
                return "run"
            return "block" if following.drum else None
        return self.drumming

    @property
    def drum_tries(self) -> int:
        """Failed tries in a row of the trial being drummed, its first try included, or 0 when no
        drum's trial waits: at `DRUM_WARNING` the console warns, and drumming goes on (the PI,
        2026-10-12)."""
        return self._tries if self._drum is not None else 0

    @property
    def aids(self) -> tuple:
        """The training aids on now (the PI, 2026-10-18, "Drumming and 'clear'"): `"drumming"`
        while trials are drummed, by a block's declaration or a trainer's switch, and `"clear"`
        while a person may clear a trial from the count. Each trial's row marks them (`Draw.aids`),
        and the console shows a standing warning while any is on."""
        return tuple(name for name, on in (("drumming", self.drumming is not None),
                                           ("clear", self.clearing)) if on)

    def train(self, setting: str, on: bool) -> None:
        """Switch a training setting on or off for the rest of the run, as a trainer does from the
        console (the PI, 2026-10-18; `TRAINING`): `"clear"`, the training aid that lets a person
        clear a trial from the count, or `"first_answers"`, which judges only each drummed trial's
        first answer for a percentage rule. Both are off as a run starts."""
        if setting not in TRAINING:
            raise ValueError(f"a training setting is {' or '.join(TRAINING)}, not {setting!r}")
        if setting == "clear":
            self.clearing = on
        else:
            self.first_answers = on

    @property
    def clearable(self) -> bool:
        """Whether a trial of the open block can be owed, so a person may clear one from the
        console (the engine C2a plan's engineering review, Minor 3): trials are drummed, or the
        block's table -- or a structure's its conditions play -- owes some outcome, before its
        stimulus or after. The flat run's every-trial table owes none, so a plain "run N trials"
        offers no *clear*, where one would only shorten the run."""
        if self.drumming:
            return True
        tables = {id(table): table for table in
                  (self._table(c.name) for c in self.block.conditions)}.values()
        return any(
            table is None
            or OWED in {table.of(o, shown) for o in (*Outcome, None) for shown in (True, False)}
            for table in tables
        )

    def clear(self, condition: str, by: object = None, rest: bool = False) -> str | None:
        """Forgive one trial of `condition`'s debt in this block, or with `rest` all it still owes,
        as a person does from the console (the PI, 2026-10-11: "manually advance beyond or clear a
        specific trial in the count"; *the rest*, the engine C2a plan's science review, D5): a
        repeat of it waiting, or a drum's trial, is dropped, its failed tries in a row start over
        (the PI, 2026-10-18), and the clearing is a `Shortfall` naming `by`. Returns why nothing was
        cleared -- *clear* is off (`clearing`: a control not switched on, never a refusal of a
        task), the block has no such condition, or it owes nothing -- or `None`. **In a designed
        block only a trial waiting to come back is cleared** (engine build C3), a drum's or one
        again at once, one trial: its plan gives its trials, so there is no other debt to clear."""
        if not self.clearing:
            return (
                "clear is a training aid, and it is off in this run; a trainer switches it on to "
                "clear a trial from the count"
            )
        if condition not in self._counts:
            return (
                f"block {self.block.name!r} has no condition {condition!r}, so nothing is cleared"
            )
        if self._designed:
            if not ((self._drum is not None and self._drum[0] == condition)
                    or (self._again is not None and self._again[0] == condition)):
                return (
                    f"block {self.block.name!r} plays a designed order, so only a trial waiting "
                    f"to come back is cleared, and no trial of {condition!r} waits"
                )
            self._forgive(condition, 1, CLEARED, by)
        else:
            owed = self.owed(condition)
            if owed == 0:
                return (
                    f"{condition!r} owes nothing in block {self.block.name!r}, so nothing is "
                    f"cleared"
                )
            self._forgive(condition, owed if rest else 1, CLEARED, by)
        # **The trial moved past is over, so its count starts over** (the PI, 2026-10-18, "End that
        # waiting trial; count starts over"), as an answer ends a trial.
        counts = self._counts[condition]
        counts.in_a_row = counts.rig = 0
        # **A person's clear is not the plan spinning** (the engine C2b plan's Task 5 review): the
        # progress check counts afresh from it, as an answer ends a trial: the open block is not
        # one "opened since the last trial", so a block cleared to nothing owed cannot make a
        # plan that can still draw look stalled (Task 7's review, Important 1).
        self._opened = set()
        return None

    def drum(self, scope: str) -> str:
        """Switch drumming, as a trainer does from the console (the PI, 2026-10-11): `"block"` on
        until this block ends, `"run"` on until the run ends, `"off"` off until this block ends.
        Off drops a drum's trial waiting to come back; its condition stays owed and is drawn as
        any other (past a criterion block's targets it owes nothing, and every condition is
        drawn: `past_targets`). **Returns the name of the block it is for**: this one, or the next
        when this block's end rule is already met -- the loop drains commands before it advances,
        so a switch made then is the next block's (the engineering review's Minor 10)."""
        if scope not in DRUM_SCOPES:
            raise ValueError(f"drumming is switched {', '.join(DRUM_SCOPES)}, not {scope!r}")
        # Asked before *off* drops a drum that holds a met block open, which would meet its end
        # rule: stopping such a drum is this block's switch (the PI, 2026-10-18: "Finish the drum
        # first").
        following = self.following
        self._carried = following is not None
        self._switched = scope
        if scope == "off":
            self._drum = None
        return following.name if following is not None else self.block.name

    @property
    def finished(self) -> bool:
        """Whether the open block's end rule is met: every condition owes nothing, and where the
        block ends on a criterion or a number of trials, those are met too -- **its targets are a
        minimum** (the PI, 2026-10-18, "Both: criterion and every target": "The block ends only
        once the criterion is met and every target is used up; conditions keep coming until both
        hold") -- **and no drum waits** ("Finish the drum first": "The block ends only after the
        drummed trial is answered right. If the extra tries drop the percentage below the bar, the
        block carries on. Training ends on a success."). **A designed block's rule is its plan**
        (engine build C3): a sequence-balanced block is finished at whichever comes first, its
        plan played out or its number of trials run (the engine C3 plan's review, I-3), a priming
        block once its number of trials is run -- and neither while a trial waits to come back at
        once."""
        if self._drum is not None:
            return False
        if self._designed:
            if self._again is not None:
                return False
            if self.block.trials is not None and self.block_trials >= self.block.trials:
                return True
            return isinstance(self.block.order, SequenceBalanced) and self._place >= len(self._plan)
        if self.block.criterion is not None:
            proportion, window = self.block.criterion
            if len(self._window) < window or sum(self._window) / len(self._window) < proportion:
                return False
        if self.block.trials is not None and self.block_trials < self.block.trials:
            # **A number of trials** (engine spec §13.5; engine build C2b): run that many, and
            # every target used up too -- its targets are a minimum, as under a criterion.
            return False
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
        them**, at once. **In a designed block** (engine build C3) a trial again at once comes
        next, and otherwise the plan's next place (`_take`); a drum's try and a trial again at
        once carry the place of the trial they show again, so neither moves the plan."""
        self._note_passed()
        number = self._number
        waiting = sorted(self._due)
        drummed = self._drum is not None
        planned = None
        if drummed:
            name, repeat_of = self._drum
            self._drum = None
            planned = None if self.drawn is None else self.drawn.planned
        elif self._again is not None:
            name, repeat_of, planned = self._again
            self._again = None
        else:
            name, repeat_of = self._peek(), None
            if waiting and (waiting[0][0] <= number or name is None or self._runs_long(name)):
                due = waiting[0]
                if due[1] == number - 1 and len(waiting) > 1:
                    due = waiting[1]
                self._due.remove(due)
                _, repeat_of, name = due
            elif name is None:
                raise IndexError(
                    f"block {self.block.name!r} has no condition left to draw and its end rule is "
                    f"not met"
                )
            elif self._designed:
                planned = self._take()
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
            aids=self.aids,
            planned=planned,
        )
        self._drawn.append(name)
        self._counts[name].attempted += 1
        self._number += 1
        self._opened = set()
        return condition

    def record(self, condition: str, outcome: Outcome | None, shown: bool = True,
               eased: bool = False, hardest: bool = True) -> str:
        """Count one trial of `condition` by its table (engine spec §16.1-16.2), and return what it
        did to the count: `COUNTED`, `SPENT`, `OWED` or `UNPAID`. `outcome` `None` is a trial that
        reached the longest trial (`task.HANG_COUNTS_AS`); `shown`, whether its stimulus had
        appeared (`task.Counting.of`). A right answer (`task.RIGHT`: correct, or a correct
        rejection) is right for a rule and the correct count. **Every answer is judged** (`_answer`;
        the PI, 2026-10-18), whatever the table says about paying, **and nothing else but what the
        block's own table scores**: a broken hold or a failure to acquire fixation (`_scored`).
        While drumming, a trial that is not right is `OWED` and comes back at once, whatever its
        table says; a streak judges each of its answers, and so does a percentage unless
        `first_answers` is on. An owed trial of a condition whose trial has failed as many tries in
        a row as its limit allows (`task.Counting.cap`: the block's table's, else the structure's)
        is not repeated again: its remaining debt is forgiven, a `Shortfall` (§16.6). **A designed
        block's break** is not shown again unless it comes back at once (`_break`; engine build
        C3).

        **`eased`, a trial a live change made easier** (engine build C3; the PI, 2026-10-30, Q8,
        "Merge; fix eased trials in C3": eased trials do not count toward moving up, and do count
        toward moving back): it is left out of the window the block's criterion and a stage's
        rule read, and still judged toward the fall-back and counted toward its condition. **In a
        training progression** (`ByCriterion`) it counts toward neither its stage's number of
        trials nor its targets either (`Counts.eased`; the engine C3 plan's review, I-7), so an
        animal is never moved up on eased trials. **A trial whose paying try was eased is eased**
        toward its stage's number of trials, whatever its first try was (the controller's ruling on
        the engine C3 plan's Task 15): a drum's try that pays it answered an easier task.

        **`hardest`, whether the trial was at its stage's hardest step** (the pop-out search build,
        2026-11-07; the PI, "Hardest step reached, 80% there"): its block's staircase at its last
        level, true for a block with none. Read only under a confirmed progression, by the bars
        of what the rig suggests (`_bar`, `suggestion`)."""
        counts = self._counts[condition]
        kind = self._class(outcome, shown, condition)
        first_try = self.drawn is None or not self.drawn.drummed
        judged = self._answer(outcome, condition) or self._scored(outcome)
        kept = eased and isinstance(self.order, ByCriterion)
        # A try recorded: a presentation, and a trial unless a drum brought it back (the PI,
        # 2026-10-18, "200 trials; drummed repeats inside them"); an ordinary repeat, shown again a
        # few trials later, is a trial of its own. Counted as each try ends, so a trial that
        # faulted, which has no line, is in neither (the controller's ruling M5).
        counts.presented += 1
        counts.trials += first_try
        if first_try:
            self._eased_chain = kept
        counts.eased += kept and first_try
        self.trials += first_try
        if isinstance(self.block.order, Priming) and shown and self._runs and not self._seen:
            # **A priming run counts only trials whose stimulus appeared** (engine build C3; the
            # engine C3 plan's Appendix B, item 6): this place is shown, and moves on once its
            # last try is over (`_move_on`); under a `chance` its run is one trial longer.
            self._seen = True
            if self.block.order.runs is None:
                self._runs[-1][1] += 1
        if judged:
            # Every answer, any try's, right or wrong -- and a break the block's own table scores,
            # wrong -- for the console and the end row.
            counts.right += outcome in RIGHT
            counts.wrong += outcome not in RIGHT
        counts.right_first += first_try and outcome in RIGHT
        if first_try:
            self._answered = False
        if judged and not eased and not (self._answered and self._first_answers):
            # **Every answer is judged** (the PI, 2026-10-18: a rule judges answers,
            # "whatever the counting says about paying", "until N correct" included): a trial with
            # no answer -- a break, no fixation, a lost tracker, a hang -- neither adds to nor
            # breaks a streak or a percentage -- **but where the block's own table scores it**, a
            # broken hold or a failure to acquire fixation, which is judged a miss (`_scored`;
            # "Yes, where the block says so"). **Under drumming** a streak judges every answer in
            # order, drummed tries included ("Every answer counts in order"), and so does a
            # percentage by default ("Every answer"); with the training setting `first_answers`,
            # a percentage judges only each trial's first answer -- after a try that ended before
            # any answer, the first try that answers (2026-10-12, "Leave drummed repeats out";
            # 2026-10-18, "Judge its first answer"). **An eased trial never** (engine build C3).
            self._window.append(1 if outcome in RIGHT else 0)
            if self.block.criterion is not None:
                while len(self._window) > self.block.criterion[1]:
                    self._window.popleft()
        if judged and not self._answered:
            # **The fall-back rule judges each trial's first answer only** (the PI, 2026-10-19,
            # "First answer only": "so one stubborn trial can't demote a stage the animal is
            # otherwise doing well in"), whatever the stage's own rule is and however it counts
            # drummed tries -- after a try that ended before any answer, the first try that
            # answers -- and a broken hold the block's own table scores is judged here as it is
            # toward moving up ("Yes, the same").
            self._back.append(1 if outcome in RIGHT else 0)
        self._answered = self._answered or judged
        if self._confirming:
            self._bar(outcome, shown, first_try, eased, hardest)
        if kind != OWED:
            # **The trial is over, so its failed tries in a row start again** (the PI, 2026-10-18,
            # "1: an answer ends the trial": the limit counts failed tries of one trial, and any
            # answer, right or wrong, starts it over), as they do when it is used up, which is not
            # shown again either. A drummed answer ends the trial's count as well, so this comes
            # before the drum branch, which returns (the controller's ruling I3).
            counts.in_a_row = counts.rig = 0
        if (self.drumming and outcome not in RIGHT
                and (self._designed or self.owed(condition) > 0 or self.past_targets)):
            # **Drumming** (`Block.drum`): repeated until right -- a correct answer or a correct
            # rejection (`task.RIGHT`) -- at once, paying nothing, its failed tries in a row
            # counted for the console's warning (`drum_tries`); past a criterion block's targets
            # too, where its conditions keep coming (`past_targets`); and in a designed block,
            # whose plan waits for it, the drum's tries keeping the place they show again (engine
            # build C3; the engine C3 plan's call 17).
            self.requeued.append(condition)
            self._drum = (condition, self._number - 1)
            self._tries = 1 if first_try else self._tries + 1
            return OWED
        if kind == COUNTED:
            counts.completed += 1
            counts.correct += outcome in RIGHT
        elif kind == SPENT:
            counts.spent += 1
        counts.eased_paid += kept and kind in (COUNTED, SPENT)
        if kept and kind in (COUNTED, SPENT) and not self._eased_chain:
            # **A trial whose paying try was eased is eased** toward its stage's number of trials
            # (the controller's ruling on the engine C3 plan's Task 15): its first try was not, and
            # the drum's try that pays it answered an easier task. Counted once a trial.
            self._eased_chain = True
            counts.eased += 1
        if self._designed:
            if kind == OWED:
                self._break(condition, outcome)
            return kind
        if kind == OWED and self.owed(condition) > 0:
            counts.rig += outcome is not None and outcome.family is Family.RIG
            cap = self._cap(condition)
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

    def _bar(self, outcome: Outcome | None, shown: bool, first_try: bool, eased: bool,
             hardest: bool) -> None:
        """**One trial toward the bars of what the rig suggests** (`suggestion`; the pop-out search
        build's design §3.4), under a confirmed progression, between trials: **answers only**, as
        a staircase classes them (`task.staircase_verdict`; TSK-33) -- a right answer right, any
        failure wrong, a trial that moves no staircase in neither window -- each kept with whether
        it was at its stage's hardest step. **Toward moving up** every answer given at the stage's
        hardest step ("Hardest step reached, 80% there"), as the stage's own rule judges them, each
        trial's first only under the training setting "first answers" (`_first_answers`),
        **never one a person's change eased** (engine build C3; the PI, Q8);
        **toward moving back each trial's first answer only** (the PI, 2026-10-19, "First answer
        only"), an eased one included, as `_back` judges them. **A trial that is no answer** is
        counted beside them by its outcome (`_aside`), and the next first answer, among the last
        answers shown (`_shown`), takes those counted before it (`answers`; the pop-out search
        build's Task 7)."""
        if first_try:
            self._bar_answered = False
        verdict = staircase_verdict(outcome, shown)
        said = "hang" if outcome is None else outcome.value
        if verdict is None:
            self._aside[said] = self._aside.get(said, 0) + 1
            return
        if hardest and not eased and not (self._bar_answered and self._first_answers):
            self._up.append((verdict, hardest))
        if not self._bar_answered:
            self._down.append((verdict, hardest))
            self._shown.append((verdict, said, tuple(self._aside.items())))
            self._aside = {}
        self._bar_answered = True

    def _break(self, condition: str, outcome: Outcome | None) -> None:
        """**A break in a designed block** (engine build C3; the PI, 2026-10-30, Q5b, "'Again at
        once' as an option"): by default the trial is not shown again and the sequence goes on, a
        sequence-balanced block's lost place a shortfall, `DESIGNED`, one trial, never flagged; a
        priming block's place is not lost, so it writes none (the engine C3 plan's review, M-9).
        **With `again_at_once`** the trial comes straight back with its place, a repeat counted as
        any is, **under the repeat limit** (review I-4; §16.6, the PI, 2026-10-12: "moved past
        after 3 failed repeats in a row"): past its failed tries in a row it is moved past, `CAP`
        or `RIG`, flagged as possible avoidance as any is, and the sequence goes on."""
        counts = self._counts[condition]
        if self.block.order.again_at_once:
            counts.rig += outcome is not None and outcome.family is Family.RIG
            cap = self._cap(condition)
            if cap is None or counts.in_a_row < cap:
                counts.repeats += 1
                counts.in_a_row += 1
                self.requeued.append(condition)
                planned = None if self.drawn is None else self.drawn.planned
                self._again = (condition, self._number - 1, planned)
                return
            self._forgive(condition, 1, RIG if counts.rig else CAP)
            # The trial moved past is over, so its count starts over: the plan shows its
            # condition again.
            counts.in_a_row = counts.rig = 0
        elif isinstance(self.block.order, SequenceBalanced):
            self._forgive(condition, 1, DESIGNED)

    def _forgive(self, condition: str, trials: int, because: str, by: object = None) -> None:
        """Forgive `trials` of `condition`'s debt in this block (§16.6): no repeat of it waits any
        longer, nor a drum's trial, nor one again at once, and the shortfall is the run's
        record."""
        self._counts[condition].forgiven += trials
        self._counts[condition].flagged |= because == CAP
        self._due = [due for due in self._due if due[2] != condition]
        if self._drum is not None and self._drum[0] == condition:
            self._drum = None
        if self._again is not None and self._again[0] == condition:
            self._again = None
        # A person's clear can come before the run's first trial, after none.
        after = self._number - 1 if self._number else None
        self.shortfalls.append(Shortfall(self.block.name, condition, trials, because, after, by))

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
