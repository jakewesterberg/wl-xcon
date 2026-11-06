"""**The arithmetic of variation** (engine build C3; its spec §2-§7 and §10): what a trial draws and
from where, the conditions a block makes from factors, a designed block's sequence, and how a draw
is written in the record, said on the console and changed live. Pure: no state, no clock, nothing
read from a session, so every consumer -- the checks at load, the scheduler, the trial loop, the
pre-flight, the review report and the record's writers -- passes what it holds and gets one
answer. **Nothing here runs in a frame**: every draw and every sequence is taken between trials.
Nothing here judges whether a distribution can be drawn: `check.undrawable` does, at load and
before a live range applies, so a distribution reaching `draw` is one it accepted.

**A draw is a keyed hash, not a seeded stream** [@salmon2011parallel]: the value a setting gets
on a trial is a function of the run's seed, the trial's number in the run (`scheduler.Draw.number`,
from 0), the setting and a counter (`unit`). It holds no generator state, comes out the same in
every process and Python version, and never touches the scheduler's generators, so adding a draw
moves no condition or repeat (the spec's §2: "apart from the scheduler's"). Each distribution draws
in closed form from one unit through its inverse distribution function, with no loop: a truncated
normal between its cut's probabilities; **the non-aging wait** as the truncated exponential, which
is exactly what drawing a wait past the longest again gives (the PI, 2026-10-30, Q2, "Draw
again": "every wait falls between the shortest and the longest"). A prepared list plays in
shuffled passes, each pass's order keyed by its draw's key, so two draws of one setting keep their
own passes.

**A designed block's sequence** is a de Bruijn cycle of its conditions [@aguirre2011de]: a random
Euler circuit through their de Bruijn graph [@brooks2012counterbalancing], built as a random tree
of last exits into a random start (Wilson's loop-erased walks), then each node's exits in a random
order with its tree exit last, which walks every edge once (the BEST theorem's construction;
engineering, no paper in the library). Its generator is the caller's, drawn from the run's seed.
Each cycle is played as the linear sequence, its first conditions again at its end, so every run
of them follows once within it, the first a lead-in (the PI, 2026-10-31).

**Directions** (the PI, 2026-10-30: "0 to 360 in both repos"): a drawn direction is drawn in the
task's own terms and written and said from 0 to 360 (`geometry.shown_direction`), end by end, so a
range of directions may read 315 to 45, crossing rightward.
"""

from __future__ import annotations

import bisect
import dataclasses
import hashlib
import itertools
import math
import random
from statistics import NormalDist

from wl_xcon.declarations import canonical
from wl_xcon.geometry import shown_direction
from wl_xcon.task import (
    EASIER, NOT_DIFFICULTY, Background, Block, Condition, Distribution, Factorial, Listed, Meaning,
    NonAging, P, Param, Polar, Task, TruncatedNormal, Uniform, Weighted, is_point,
)

#: 2**53: a unit is the first 53 bits of a hash, as a fraction of this.
_UNITS = 2.0 ** 53
#: The open interval a truncated normal's probability is held in, since `NormalDist.inv_cdf`
#: refuses 0 and 1 (`StatisticsError`).
_ABOVE_0 = math.nextafter(0.0, 1.0)
_BELOW_1 = math.nextafter(1.0, 0.0)

#: **The numbers a person may change live, by kind** (the PI, 2026-10-30, Q7b, "Yes, range changes
#: live"; the spec's §6, "a uniform's ends; a wait's shortest, average and longest"): a uniform's
#: ends, a normal's numbers and cut, a wait's shortest, mean and longest. The kind never changes
#: live (a task edit); a weighted set's weights and a list's items are not changed live in engine
#: build C3.
LIVE_NUMBERS: dict[type, tuple[str, ...]] = {
    Uniform: ("low", "high"),
    TruncatedNormal: ("mean", "sd", "low", "high"),
    NonAging: ("minimum", "mean", "maximum"),
}

#: The fields of each distribution that are places on its setting's axis: a direction's are
#: written and said from 0 to 360. A normal's spread is no place.
_PLACES: dict[type, tuple[str, ...]] = {
    Uniform: ("low", "high"),
    TruncatedNormal: ("mean", "low", "high"),
    NonAging: ("minimum", "mean", "maximum"),
}


def _number(value: object) -> bool:
    """Whether `value` is a number: an `int` or a `float`, never a `bool`."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _finite(value: object) -> bool:
    """Whether `value` is a finite number."""
    return _number(value) and math.isfinite(value)


def _items(value: object) -> tuple:
    """A distribution's `values` or `weights` as a tuple: () for anything that is not a tuple or
    a list, which the load refuses, so nothing reading it raises first."""
    return tuple(value) if isinstance(value, (tuple, list)) else ()


def unit(*key: int | str) -> float:
    """**A number in [0, 1) that `key` alone decides** (engine build C3's call 4): the first 53
    bits of the SHA-256 of the key's parts, each written as text and joined by the unit separator
    `"\\x1f"`, as a fraction of 2**53. One key gives one number in every process and Python
    version, and holds no state. A draw's key is `(seed, trial, setting, counter)`; a prepared
    list's pass order `(seed, "pass", *key, pass, item)`."""
    text = "\x1f".join(str(part) for part in key)
    head = int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:8], "big") >> 11
    return head / _UNITS


def _cut(normal: TruncatedNormal, declared: Param | None) -> tuple:
    """A truncated normal's cut, `(low, high)`: each end its own, else its setting's declared
    end where that is a finite number (TSK-24: "a normal, truncated to the declared range"),
    else `None`."""
    low, high = normal.low, normal.high
    if declared is not None:
        if low is None and _finite(declared.low):
            low = declared.low
        if high is None and _finite(declared.high):
            high = declared.high
    return low, high


def bounds_of(distribution: object, declared: Param | None = None) -> tuple[float, float] | None:
    """**The least and the most a draw can give**: a uniform's ends; a truncated normal's cut,
    each end its own or its setting's declared one (`declared`), an end neither gives infinite;
    a wait's shortest and longest. `None` for a finite set (`Weighted`, `Listed`), whose values
    `values_of` gives, and for anything else."""
    if isinstance(distribution, Uniform):
        return (distribution.low, distribution.high)
    if isinstance(distribution, TruncatedNormal):
        low, high = _cut(distribution, declared)
        return (-math.inf if low is None else low, math.inf if high is None else high)
    if isinstance(distribution, NonAging):
        return (distribution.minimum, distribution.maximum)
    return None


def values_of(distribution: object) -> tuple:
    """**The values a finite set can give**: a `Weighted`'s or a `Listed`'s `values`, a weight of
    0 included; `()` for anything else."""
    if isinstance(distribution, (Weighted, Listed)):
        return _items(distribution.values)
    return ()


def extremes(distribution: object, declared: Param | None = None, *,
             direction: bool = False) -> tuple:
    """**The least and the most a draw can give, where each is a finite number**, each once
    (engine build C3's spec §11): a uniform's, a normal's or a wait's ends (`bounds_of`, a normal
    cut to its setting's declared range, `declared`, where it gives no end of its own), or a
    finite set's least and greatest number (`values_of`), a value of weight 0 left out, since it
    is never drawn; `()` for a set of no numbers. What a draw is checked again with, widened, one
    extreme at a time with its condition's values, at a run's start (`preflight.beyond`) and live,
    with a person's value outside its range (`taskd.Session._outside_sets`, `_beyond_range`): a
    check widened to an extreme reasons over every value between it and the declared range, so the
    two ends are all it needs. For a distribution the load accepts (`check.undrawable`).

    **A direction** (`direction=True`, for a setting `directions` names) is judged on the circle it
    is shown on, 0 to 360 (`geometry.shown_direction`; the controller's ruling on the review of
    Task 11): `Uniform(-45, 45)` gives 315 and 45, inside a setting declared [0, 360]."""
    ends = bounds_of(distribution, declared)
    if ends is None:
        values = values_of(distribution)
        weights = (_items(distribution.weights) if isinstance(distribution, Weighted)
                   else (1,) * len(values))
        numbers = [value for value, weight in zip(values, weights)
                   if weight > 0 and isinstance(value, (int, float))
                   and not isinstance(value, bool)]
        ends = (min(numbers), max(numbers)) if numbers else ()
    if direction:
        ends = tuple(shown_direction(end) for end in ends if math.isfinite(end))
    return tuple(dict.fromkeys(end for end in ends if math.isfinite(end)))


#: **The numbers that place a draw's values on its setting's axis**, by kind (the PI, 2026-10-31,
#: on the engine C3 plan's Appendix B, item 18): each is read as a value of the setting is
#: (`easier_range`). A normal's spread is not one: changing it moves its values both ways at once.
_PLACED = {Uniform: ("low", "high"), TruncatedNormal: ("mean", "low", "high"),
           NonAging: ("minimum", "mean", "maximum")}


def easier_range(meaning: Meaning, drawn: object, written: object,
                 declared: Param | None = None, reference: object = None) -> bool | None:
    """**Whether a range changed live counts as easier than the range the task writes**, judged as
    a whole (the PI, 2026-10-31, on the engine C3 plan's Appendix B, item 18, "Judge the range as a
    whole (Recommended)": "if it reaches any value easier than the written range allows (for a
    uniform, either end moved the easier way; anything that cannot be read, or mixed, counts as
    easier, as doubt does under item 2)"). Each number placing its values (`_PLACED`: a uniform's
    two ends, a normal's mean and cut, its cut filled from `declared` as `bounds_of` fills it, a
    wait's shortest, average and longest) is read as a value of the setting is (`easier`, with
    `reference` for a meaning relative to another setting): `True` where one moved the easier way,
    a mixed change among them, or where a normal's spread changed, its values moving both ways;
    `None` where none moved the easier way and which way one moved cannot be read; `False` where
    none moved, or each that moved moved the harder way, and for a setting that is no difficulty
    setting. Read the other way round, `easier_range(meaning, written, drawn)` true says it moved
    the harder way somewhere. Two draws of other kinds, or of two kinds, cannot be read."""
    if meaning.kind == NOT_DIFFICULTY:
        return False
    fields = _PLACED.get(type(written))
    if fields is None or type(drawn) is not type(written):
        return None
    doubt = False
    for field in fields:
        now, was = _placed(drawn, field, declared), _placed(written, field, declared)
        if now == was:
            continue
        way = easier(meaning, now, was, reference)
        if way is None:
            doubt = True
        elif way:
            return True
    if isinstance(written, TruncatedNormal) and drawn.sd != written.sd:
        return True
    return None if doubt else False


def _placed(distribution: Distribution, field: str, declared: Param | None) -> object:
    """One of the numbers placing a draw's values (`_PLACED`): a normal's cut end filled from
    `declared` as `bounds_of` fills it, so a cut written and one its setting gives read alike."""
    if isinstance(distribution, TruncatedNormal) and field in ("low", "high"):
        return bounds_of(distribution, declared)[0 if field == "low" else 1]
    return getattr(distribution, field)


def draw(
    distribution: Distribution,
    seed: int,
    trial: int,
    key: tuple,
    *,
    declared: Param | None = None,
    ordinal: int = 0,
) -> object:
    """**The value `distribution` gives a setting on one trial** (engine build C3's calls 4, 5
    and 7), in the task's own terms: `trial` is the trial's number in the run (`Draw.number`),
    `key` the draw's key (`("task", name)`, `("block", block, name)` or `("condition", condition,
    name)`), its last part the setting. Every kind but a list draws from one unit, `unit(seed,
    trial, setting, 0)`, the counter 0 since each needs one; so a setting's unit on a trial is the
    same whichever draw is in force, and a draw from another range on the same trial is the same
    quantile of it.

    - **`Uniform`**: `low` plus the unit's share of the span.
    - **`Weighted`**: each value in proportion to its weight; a weight of 0 is never drawn.
    - **`TruncatedNormal`**: by the inverse of the normal's distribution function, between the
      probabilities of its cut (`bounds_of`, with `declared` for an end it does not give). The
      probability is held inside (0, 1) and the value inside the cut, so a cut far in a tail,
      where floating point holds almost none of the normal, gives its nearer end and never raises
      (the load refuses such a cut; review I-2).
    - **`Listed`**: the item at place `ordinal` of the run's fresh draws from this key (`Session.
      _listed`): pass `ordinal // n` is the items sorted by `unit(seed, "pass", *key, pass, item)`,
      so each item is played once a pass, in a new order each pass; with `in_order`, as listed,
      over and over. The trial does not choose it.
    - **`NonAging`**: `minimum` plus the exponential wait of mean `mean - minimum`, cut at
      `maximum` by its inverse distribution function -- the distribution drawing a wait past the
      longest again gives, without a loop.

    Anything else, which the load refuses, draws `None`."""
    if isinstance(distribution, Listed):
        values = _items(distribution.values)
        place = ordinal % len(values)
        if distribution.in_order:
            return values[place]
        turn = ordinal // len(values)
        order = sorted(range(len(values)),
                       key=lambda item: unit(seed, "pass", *key, turn, item))
        return values[order[place]]
    return quantile(distribution, unit(seed, trial, key[-1], 0), declared)


def quantile(distribution: Distribution, share: float, declared: Param | None = None) -> object:
    """**What `distribution` gives at `share`**, a fraction in [0, 1): `draw`'s value from one unit
    for every kind but a list, which plays its items in passes, each kind as `draw` says, and a
    priming run's length before it is rounded down (`run_length`). **A weighted set's place is held
    to its last value of weight above 0**, so weights whose sum overflows a float, or a weight too
    small to add to the rest, give one of its values and never raise between trials (the C3 plan's
    engineering review, M-2; the load refuses both, `check.undrawable`). `None` for a list and for
    anything else."""
    if isinstance(distribution, Uniform):
        low, high = distribution.low, distribution.high
        return min(max(low + share * (high - low), low), high)
    if isinstance(distribution, Weighted):
        weights = _items(distribution.weights)
        running = list(itertools.accumulate(weights))
        last = max(at for at, weight in enumerate(weights) if weight > 0)
        return _items(distribution.values)[
            min(bisect.bisect_right(running, share * running[-1]), last)]
    if isinstance(distribution, TruncatedNormal):
        low, high = bounds_of(distribution, declared)
        normal = NormalDist(distribution.mean, distribution.sd)
        below, above = normal.cdf(low), normal.cdf(high)
        chance = min(max(below + share * (above - below), _ABOVE_0), _BELOW_1)
        return min(max(normal.inv_cdf(chance), low), high)
    if isinstance(distribution, NonAging):
        scale = distribution.mean - distribution.minimum
        span = distribution.maximum - distribution.minimum
        waited = -scale * math.log1p(share * math.expm1(-span / scale))
        return min(max(distribution.minimum + waited, distribution.minimum), distribution.maximum)
    return None


def realized_mean(wait: NonAging) -> float:
    """**What the non-aging wait averages once its tail is drawn again** (engine build C3's call
    6): `minimum + τ - L / (e^(L/τ) - 1)`, the mean of the exponential of mean `τ = mean -
    minimum` cut at `L = maximum - minimum`, below the declared `mean`, which is the uncut wait's.
    750 to 1250 ms with a mean of 1000 realizes 922 ms (the spec's §3). Arithmetic of the declared
    distribution, not a measurement of the rig."""
    scale = wait.mean - wait.minimum
    span = wait.maximum - wait.minimum
    # `span / expm1(span / scale)` written so that a longest far past the mean, e to more than
    # about 709, gives its limit, 0, rather than raising `OverflowError`.
    return wait.minimum + scale - span * math.exp(-span / scale) / -math.expm1(-span / scale)


def hazard_ratio(wait: NonAging, at: float) -> float:
    """**How much more likely the wait is to end at `at` than the flat rate** (the spec's §3:
    "the review report shows how much the target's chance rises near the longest"): the hazard
    of the cut exponential over the uncut one's, `1 / (1 - e^(-(maximum - at) / τ))`. 1.16, 1.58,
    3.03 and 10.51 at 750, 1000, 1150 and 1225 ms of a 750-1000-1250 ms wait. 0 before the
    shortest, where the wait cannot end; infinite at the longest, where it must."""
    if at < wait.minimum:
        return 0.0
    if at >= wait.maximum:
        return math.inf
    return 1.0 / -math.expm1(-(wait.maximum - at) / (wait.mean - wait.minimum))


def run_length(runs: Distribution, share: float) -> int:
    """**A priming run's length drawn from a distribution** (engine build C3's call 16; the C3
    plan's science review, I-8): its value at `share` (`quantile`), rounded down, at least 1. Runs
    of `(low, high)`, and a prepared list's lengths, which play in passes, the scheduler draws
    itself."""
    return max(1, math.floor(quantile(runs, share)))


def switch_chances(runs: object) -> tuple[tuple[int, float], ...]:
    """**The chance a priming run switches after each of its trials**, given it lasted that long
    (the C3 plan's science review, I-8): `(k, chance)` for each length k from 1 to the longest, a
    run that has shown k trials ending there -- the chance of a length of k over that of k or more.
    Runs of `(low, high)` are each length as likely; a distribution's length is its value rounded
    down, at least 1 (`run_length`); a weighted set's in proportion to its weights, a list's each
    item alike. Lengths drawn evenly make a switch ever more expected along a run, certain at its
    longest; non-aging lengths keep the chance nearly the same until the cut. Arithmetic of the
    declaration, for the review report, never a measurement."""
    lengths = _lengths(runs)
    longest = max(lengths)
    left, chances = 1.0, []
    for length in range(1, longest + 1):
        share = lengths.get(length, 0.0)
        chances.append((length, 1.0 if length == longest else share / left if left > 0 else 1.0))
        left -= share
    return tuple(chances)


def _lengths(runs: object) -> dict[int, float]:
    """A priming run's lengths, whole numbers from 1, each with its probability
    (`switch_chances`)."""
    if isinstance(runs, tuple):
        low, high = runs
        return {length: 1 / (high - low + 1) for length in range(low, high + 1)}
    lengths: dict[int, float] = {}
    if isinstance(runs, (Weighted, Listed)):
        values = _items(runs.values)
        weights = _items(runs.weights) if isinstance(runs, Weighted) else (1,) * len(values)
        total = math.fsum(weights)
        for value, weight in zip(values, weights):
            if weight > 0:
                at = max(1, math.floor(value))
                lengths[at] = lengths.get(at, 0.0) + weight / total
        return lengths
    low, high = bounds_of(runs)
    if high <= low:
        return {max(1, math.floor(low)): 1.0}
    if isinstance(runs, Uniform):
        def below(at: float) -> float:
            return (at - low) / (high - low)
    elif isinstance(runs, TruncatedNormal):
        normal = NormalDist(runs.mean, runs.sd)
        under, held = normal.cdf(low), normal.cdf(high) - normal.cdf(low)

        def below(at: float) -> float:
            return (normal.cdf(at) - under) / held
    else:
        scale = runs.mean - runs.minimum

        def below(at: float) -> float:
            return math.expm1(-(at - low) / scale) / math.expm1(-(high - low) / scale)
    for at in range(math.floor(low), math.floor(high) + 1):
        share = below(min(at + 1, high)) - below(max(at, low))
        if share > 0:
            lengths[max(1, at)] = lengths.get(max(1, at), 0.0) + share
    return lengths


def in_force(task: Task, block: Block) -> dict[str, tuple[Distribution, tuple]]:
    """**The draws in force in `block`**, by setting, each with its key (engine build C3's call 7;
    the PI, 2026-10-30, Q1a, "Task default, block may replace"): the block's own (`Block.draws`),
    keyed `("block", block, name)`, and the task's (`Task.draws`), keyed `("task", name)`, for
    each setting the block's own draws do not name. A setting the block names `BY_CONDITIONS` is
    its conditions', so neither draw is in force there. A condition's own range is
    `own_ranges`'."""
    own = block.draws if isinstance(block.draws, dict) else {}
    found = {
        name: (drawn, ("block", block.name, name))
        for name, drawn in own.items() if isinstance(drawn, Distribution)
    }
    for name, drawn in task.draws.items():
        if name not in own:
            found[name] = (drawn, ("task", name))
    return found


def own_ranges(condition: Condition) -> dict[str, tuple[Distribution, tuple]]:
    """**A condition's own ranges** (the PI, 2026-10-30, Q1b: "a condition may draw its own
    setting from its own range"): each value it sets that is a `Distribution`, by setting, keyed
    `("condition", condition, name)`."""
    values = condition.values if isinstance(condition.values, dict) else {}
    return {
        name: (value, ("condition", condition.name, name))
        for name, value in values.items() if isinstance(value, Distribution)
    }


def level_name(level: object) -> str:
    """**A factor's level as a generated condition's name writes it** (engine build C3's call
    14): text as written; a number by `repr`, its shortest exact form; a position of numbers
    eccentricity first, `"8° at 270°"`, its direction from 0 to 360 and none at eccentricity 0
    (the PI, 2026-10-30, "Empty at center"), or an (x, y) pair as `"(1.5, -2)"`; a range of its
    own in the rig's words (`words`, with no unit); anything else by its `repr`, which the load
    refuses where that holds an address (`" at 0x"`)."""
    if isinstance(level, str):
        return level
    if isinstance(level, Distribution):
        return words(level, "")
    if _number(level):
        return repr(level)
    if isinstance(level, Polar) and is_point(level):
        if level.eccentricity == 0:
            return f"{level.eccentricity!r}°"
        return f"{level.eccentricity!r}° at {shown_direction(level.direction)!r}°"
    if is_point(level):
        return f"({level[0]!r}, {level[1]!r})"
    return repr(level)


def generated(block: Block) -> list[Condition]:
    """**The conditions `block`'s factorial makes** (TSK-22: "the framework makes the combinations
    minus declared exclusions, each named from its levels"; the PI, 2026-10-30, Q4, "Yes, each
    cell equal"): every combination of its factors' levels, the first factor slowest, but those an
    exclusion matches -- an exclusion, `{factor: level}`, matches every combination holding all the
    levels it names -- each named `"factor=level, factor=level"` in the factors' declared order
    (`level_name`), owed `target` or its own number in `targets`, playing `structure`. `[]` for a
    block without one, or one with no factors. A part that is not the shape `Factorial` declares,
    or an exclusion naming no factor, is read as giving or excluding nothing, so the load can
    refuse it with a sentence and nothing raises first."""
    factorial = block.factorial
    if not isinstance(factorial, Factorial) or not isinstance(factorial.factors, dict) or not (
            factorial.factors):
        return []
    factors = list(factorial.factors)
    levels = [_items(each) for each in factorial.factors.values()]
    exclusions = [each for each in _items(factorial.exclude) if isinstance(each, dict) and each]
    targets = factorial.targets if isinstance(factorial.targets, dict) else {}
    made: list[Condition] = []
    for combination in itertools.product(*levels):
        values = dict(zip(factors, combination))
        if any(all(factor in values and values[factor] == level
                   for factor, level in exclusion.items()) for exclusion in exclusions):
            continue
        name = ", ".join(f"{factor}={level_name(level)}" for factor, level in values.items())
        made.append(Condition(name, values, targets.get(name, factorial.target),
                              factorial.structure))
    return made


def expanded(block: Block) -> Block:
    """**`block` with its factorial expanded into ordinary conditions** (engine build C3's call
    14): its hand-listed conditions first, then `generated`'s, `factorial` `None`, every other
    field as declared; so a generated condition is counted, repeated, overridden and checked as a
    hand-listed one is. A block without a factorial, or whose conditions are not a list, is
    returned as it is."""
    if not isinstance(block.factorial, Factorial) or not isinstance(block.conditions, list):
        return block
    return dataclasses.replace(block, conditions=[*block.conditions, *generated(block)],
                               factorial=None)


def balanced_sequence(
    names: list[str], depth: int, cycles: int, rng: random.Random
) -> tuple[str, ...]:
    """**A sequence-balanced block's conditions in the order played** (TSK-23; the PI,
    2026-10-30, Q5a, "Block picks; pairs default"): one de Bruijn cycle of `names` at `depth`
    [@aguirre2011de], `n**depth` trials of `n` names in which each run of `depth` names, a name
    after itself included, follows once, counted cyclically -- drawn from `rng` as a random Euler
    circuit through their de Bruijn graph [@brooks2012counterbalancing] -- **played as the linear
    sequence**: its first `depth - 1` names again at its end, `n**depth + depth - 1` names in which
    each run of `depth` follows exactly once (the PI, 2026-10-31, on the engine C3 plan's Appendix
    B, item 1, "Add one closing trial (Recommended)": 17 for 4 at pairs, every pair shown), its
    first `depth - 1` places a lead-in that only precedes what follows. Played `cycles` times
    over, each cycle holds every run once. Outside its lead-in each name is played `n**(depth - 1)`
    times a cycle. `()` for no names, a depth under 1 or no cycles.

    The graph's nodes are the runs of `depth - 1` names, as numbers in base `n`; an edge, a name,
    leads from a run to the run it ends. A random tree of last exits into a random start is drawn
    by loop-erased random walks (Wilson's); each node's exits are shuffled, its tree exit last;
    walking from the start along each node's next unused exit then uses every edge once."""
    count = len(names)
    if not count or depth < 1 or cycles < 1:
        return ()
    nodes = count ** (depth - 1)
    start = rng.randrange(nodes)
    leave: dict[int, int] = {}
    reached = {start}
    for first in range(nodes):
        node = first
        while node not in reached:
            leave[node] = rng.randrange(count)
            node = (node * count + leave[node]) % nodes
        node = first
        while node not in reached:
            reached.add(node)
            node = (node * count + leave[node]) % nodes
    exits = []
    for node in range(nodes):
        order = list(range(count))
        rng.shuffle(order)
        if node != start:
            order.remove(leave[node])
            order.append(leave[node])
        exits.append(order)
    used = [0] * nodes
    node, played = start, []
    for _ in range(count ** depth):
        name = exits[node][used[node]]
        used[node] += 1
        played.append(names[name])
        node = (node * count + name) % nodes
    return tuple(played + (played * depth)[:depth - 1]) * cycles


def numbers(distribution: object) -> dict[str, float] | None:
    """**The numbers of a draw a person may change live** (`LIVE_NUMBERS`), each it holds: a
    normal's cut only where it declares its own. `None` for a kind whose numbers are not changed
    live: a weighted set, a list, anything else."""
    fields = LIVE_NUMBERS.get(type(distribution))
    if fields is None:
        return None
    return {name: getattr(distribution, name) for name in fields
            if getattr(distribution, name) is not None}


def with_numbers(distribution: Distribution, changed: dict[str, float]) -> Distribution:
    """**`distribution` with the numbers a person changed live** (the PI, 2026-10-30, Q7b): the
    same kind, what a repeat takes and every number not named as they were. `ValueError`, saying
    which, for a kind whose numbers are not changed live or a name that is not one of its live
    numbers. Whether the result can be drawn is `check.undrawable`'s to judge."""
    fields = LIVE_NUMBERS.get(type(distribution))
    kind = type(distribution).__name__
    if fields is None:
        raise ValueError(
            f"a {kind}'s numbers are not changed live: only a Uniform's, a TruncatedNormal's "
            f"and a NonAging's are"
        )
    for name in changed:
        if name not in fields:
            raise ValueError(
                f"{name!r} is not a number of a {kind} changed live; its live numbers are "
                f"{', '.join(fields)}"
            )
    return dataclasses.replace(distribution, **changed)


def _turned(value: object) -> object:
    """A direction's number from 0 to 360 (`geometry.shown_direction`); anything else as it is."""
    return shown_direction(value) if _number(value) else value


def _shown(distribution: Distribution, direction: bool) -> Distribution:
    """`distribution` as the rig writes and says it: for a direction setting, each place on its
    axis -- a uniform's ends, a normal's mean and cut, a wait's three, each value of a set --
    from 0 to 360 (the PI, 2026-10-30), so a range may cross rightward; otherwise as it is."""
    if not direction:
        return distribution
    if isinstance(distribution, (Weighted, Listed)):
        return dataclasses.replace(
            distribution, values=tuple(_turned(value) for value in values_of(distribution)))
    return dataclasses.replace(distribution, **{
        name: _turned(getattr(distribution, name))
        for name in _PLACES.get(type(distribution), ())
    })


def recorded(distribution: Distribution, declared: Param | None = None, *,
             direction: bool = False) -> dict:
    """**A draw as the record writes it** (engine build C3's calls 11 and 12): every field, its
    defaults included (`declarations.canonical(..., every_field=True)`, as an appearance is,
    REC-27), so the record never needs this build's defaults to be read; a truncated normal's cut
    filled from its setting's declared range (`declared`) where it gives none; a direction
    setting's places from 0 to 360 (`direction`). The task's hash keeps the hash's form."""
    if isinstance(distribution, TruncatedNormal):
        low, high = _cut(distribution, declared)
        distribution = dataclasses.replace(distribution, low=low, high=high)
    return canonical(_shown(distribution, direction), every_field=True)


def words(distribution: Distribution, unit: str, *, direction: bool = False) -> str:
    """**A draw in the rig's words** (engine build C3; the spec's §6, "a draw and its range"):
    what the console's card and a staged change say, and a range level's name. Each number by its
    `repr` and `unit` (none where `unit` is empty), a direction's places from 0 to 360:
    `"uniform from 315 deg to 45 deg"`; `"one of 0.1 s, 0.5 s, weighted 3:1"`; `"normal of mean
    1.0 s and sd 0.1 s, cut from 0.9 s to 1.1 s"` (`"cut to the setting's range"` where it
    declares no cut of its own); `"each of 2, 4, 6 once a pass, shuffled"` or `"in order: 2, 4, 6,
    over and over"`; `"non-aging from 0.75 s to 1.25 s, mean 1.0 s"`."""
    shown = _shown(distribution, direction)
    # In a direction draw, equal ends mean the whole turn (the controller's ruling on the review of
    # Task 4): a span of 360 in the task's own terms reads as both ends the same direction.
    turn = (direction and isinstance(distribution, (Uniform, TruncatedNormal))
            and _number(distribution.low) and _number(distribution.high)
            and distribution.high - distribution.low == 360)

    def amount(value: object) -> str:
        if not _number(value):
            return level_name(value)
        return f"{value!r} {unit}" if unit else repr(value)

    if turn and isinstance(shown, Uniform):
        return f"uniform over the whole turn, from {amount(shown.low)}"
    if isinstance(shown, Uniform):
        return f"uniform from {amount(shown.low)} to {amount(shown.high)}"
    if isinstance(shown, Weighted):
        weights = ":".join(repr(weight) for weight in _items(shown.weights))
        return f"one of {', '.join(amount(v) for v in values_of(shown))}, weighted {weights}"
    if isinstance(shown, TruncatedNormal):
        if turn:
            cut = f"cut to the whole turn, from {amount(shown.low)}"
        elif shown.low is None and shown.high is None:
            cut = "cut to the setting's range"
        else:
            lowest = "the setting's lowest" if shown.low is None else amount(shown.low)
            highest = "the setting's highest" if shown.high is None else amount(shown.high)
            cut = f"cut from {lowest} to {highest}"
        return f"normal of mean {amount(shown.mean)} and sd {amount(shown.sd)}, {cut}"
    if isinstance(shown, Listed):
        items = ", ".join(amount(value) for value in values_of(shown))
        if shown.in_order:
            return f"in order: {items}, over and over"
        return f"each of {items} once a pass, shuffled"
    if isinstance(shown, NonAging):
        return (f"non-aging from {amount(shown.minimum)} to {amount(shown.maximum)}, "
                f"mean {amount(shown.mean)}")
    return repr(distribution)


def directions(task: Task) -> frozenset[str]:
    """**The settings `task` places a direction by** (engine build C3's call 11): each named as a
    `Polar`'s direction anywhere in its structures -- a stimulus's position, either eye's, an
    `Update`'s, a window's center, an array's center. A drawn one is written and said from 0 to
    360; an eccentricity is no direction."""
    found: set[str] = set()

    def walk(node: object) -> None:
        if isinstance(node, Polar):
            if isinstance(node.direction, P):
                found.add(node.direction.name)
        elif dataclasses.is_dataclass(node) and not isinstance(node, type):
            for spec in dataclasses.fields(node):
                walk(getattr(node, spec.name))
        elif isinstance(node, (list, tuple)):
            for item in node:
                walk(item)
        elif isinstance(node, dict):
            for item in node.values():
                walk(item)

    walk(list(task.structures.values()))
    return frozenset(found)


def easier(meaning: Meaning, value: object, otherwise: object, reference: object = None, *,
           choices: bool = False) -> bool | None:
    """**Whether `value` makes the task easier than `otherwise` would** (engine build C3's call
    18; XC-288 §4.1, TRN-03), as `meaning` reads, a clear-cut and an expected setting alike:
    `True`, easier; `False`, not easier -- harder, the same, or a setting that is not a difficulty
    setting, which moves the task neither way; **`None` where the direction cannot be read**, and
    a caller judging a live change keeps the trial out of moving up then (the animal is never
    moved up on doubt).

    - **Numbers, `relative_to` `None`**: raising the value moves the task as `raising` says.
    - **Numbers, relative to a number or another setting** (`reference`, that setting's value):
      moving the value farther from it moves the task as `raising` says; as far, the same. A
      reference that is not a number cannot be read.
    - **Relative to the trial's background** (`BACKGROUND`): cannot be read here; the background
      is a color, not a number on the setting's scale.
    - **A choice** (`choices`, a setting whose values are its `Param.choices`, numbers or not, as
      `review._direction` reads it), **or anything but numbers -- an appearance, a position**: a
      choice has no order, so a change is read by `raising` alone (TRN-11: "a task's own meaning
      for one reads on changing it"). Read relative to anything, or against nothing (`None`), it
      cannot be read.

    A changed choice is easier where `raising` is easier, whichever way it changed; so asking the
    other way round, `easier(meaning, otherwise, value)`, does not say it was harder."""
    if meaning.kind == NOT_DIFFICULTY or value == otherwise:
        return False
    if value is None or otherwise is None:
        return None
    eases = meaning.raising == EASIER
    relative = meaning.relative_to
    if choices or not (_number(value) and _number(otherwise)):
        return eases if relative is None else None
    if not (_finite(value) and _finite(otherwise)) or isinstance(relative, Background):
        return None
    if relative is None:
        return (value > otherwise) == eases
    anchor = reference if isinstance(relative, str) else relative
    if not _finite(anchor):
        return None
    farther, nearer = abs(value - anchor), abs(otherwise - anchor)
    if farther == nearer:
        return False
    return (farther > nearer) == eases
