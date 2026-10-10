"""A stranded session's folder read back for a resume (XC-026 spec §3, §4, §8a).

**Pure.** It reads files and returns a `Restoration`, or raises `Unresumable` saying why.
It decides nothing about welfare: `Session.resume` and `Welfare` apply what it read, and
`Service._resume` decides whether to. The departure comes in from `stranded.find`, the
one reader of `welfare_notes.jsonl`.

**Every number comes from `trial_starts.jsonl`** (§8a item 1). A trial that died mid-trial
started, and strobed its number, with no `trials.jsonl` line, so no number it took is
issued again. **The fluid comes from the lines and the hand rewards** (§4). A trial that
died has no line, so its reward, if any, is not counted, and the supplement errs larger.
A record that cannot give the fluid so far cannot be resumed: it is never taken as zero.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

from wl_xcon import actor as actors
from wl_xcon import link as _link
from wl_xcon.findings import SESSION_KINDS
from wl_xcon.levels import Levels, task_name
from wl_xcon.record import ACCEPTED_WARNINGS, CONTROLS, RUNS, TRIAL_STARTS
from wl_xcon.simulate import Tally
from wl_xcon.task import Outcome
from wl_xcon.warnlist import Entry
from wl_xcon.welfare import OUT_OF_CAGE

#: The numbers a run's start row records (`Session.run`), which a resume continues from.
RUN_NUMBERS = ("run_in_session", "run_in_task", "task_in_session")

#: Why a record written before XC-026 cannot be resumed, said once, for the page.
PREDATES = (
    "its record was written before the rig recorded each trial's fluid (XC-026), so its "
    "fluid so far cannot be known; end it with its return instead"
)

#: Why a record written before engine build B cannot be resumed, said once, for the page.
PREDATES_KINDS = (
    "its record was written before sessions said what they are for (engine build B), so what "
    "it is for is unknown; end it with its return instead"
)


class Unresumable(Exception):
    """A folder that cannot be resumed; its message says why, for the page."""


def _cut(error: Exception) -> str:
    """What a reader said of a record it could not read, cut to `link.TEXT_LIMIT` characters
    and "…" as the file's quoted values are (`link._quoted`), shown as it is: why a session
    cannot be resumed is `Stranded.why`, on every idle frame and the page's banner, and a
    parser's message can quote what it could not read -- `float()`'s quotes all of it, and
    an `OSError`'s the whole path (XC-299)."""
    return _link.cut(str(error), _link.TEXT_LIMIT)


@dataclass(frozen=True)
class Restoration:
    session_id: str
    subject: str
    deployment: str
    view: str
    session_kind: str
    subject_settings: str
    bounds_at_open: dict
    already_today: float | None
    departure: float
    commanded: float
    last_reward_at: float | None
    levels: Levels
    run_index: int | None
    sequence: int
    bounded: dict
    last_written_at: float
    #: Whether its runs were ended (End session's `end` row) before its process stopped.
    ended: bool
    #: How its last run ended, as `Session.stopped_because` and `stop_kind` say it.
    stopped_because: str
    stop_kind: str | None
    #: Each warning the session accepted, as `Session.warnings` gives it.
    accepted: tuple


def _rows(directory: Path, name: str) -> list[dict]:
    path = directory / name
    if not path.exists():
        return []
    try:
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip()]
    except (OSError, ValueError) as error:
        raise Unresumable(f"its {name} cannot be read ({_cut(error)}); end it instead") from error


def _accepted(row: dict, number: int, session_kind: str) -> tuple:
    """Row `number` of `ACCEPTED_WARNINGS`, as `SessionRecord.warning` writes it, read back as
    `Session.warnings` gives it -- or `Unresumable`, naming the field that is not what that
    method writes (the engine B plan, call 12). **Nothing is coerced**, as `Service._resume`
    says of the rest of the record: a damaged row is not what anyone accepted, so
    `stranded.find` marks the session not resumable rather than restoring a guess. A field
    the row lacks is a `KeyError`, which `read` names."""

    def damaged(what: str) -> Unresumable:
        return Unresumable(
            f"its {ACCEPTED_WARNINGS} row {number} {what}, so what the session accepted "
            f"cannot be known; end it instead"
        )

    code, detail, kinds, by, at = (
        row[name] for name in ("code", "detail", "accepted_in", "by", "at")
    )
    if not isinstance(code, str):
        raise damaged("has a code that is not text")
    if not isinstance(detail, str):
        raise damaged("has a detail that is not text")
    if not isinstance(kinds, list) or not all(kind in SESSION_KINDS for kind in kinds):
        raise damaged("has an accepted_in that is not a list of training, piloting or recording")
    # **Held to what `Entry` refuses** (the engine B final review): `Session.resume` builds one
    # from each row, after it restores the departure, so a row it would refuse is refused here,
    # as a reason the session cannot be resumed, never as an exception out of a resume.
    try:
        Entry(code, detail, tuple(kinds))
    except (TypeError, ValueError) as error:
        raise damaged(f"is not a warning as the rig lists one ({_cut(error)})") from error
    if row["session_kind"] != session_kind:
        # Quoted cut (the engine B final review): this sentence is shown on every idle frame.
        raise damaged(
            f"has a session_kind of {_link._quoted(row['session_kind'])}, and its config.json "
            f"says the session is for {session_kind!r}"
        )
    if isinstance(at, bool) or not isinstance(at, (int, float)) or not math.isfinite(at):
        raise damaged("has an at that is not a finite number")
    try:
        accepted_by = None if by is None else actors.from_map(by)
    except actors.NotAnActor as error:
        raise damaged(f"has a by that is not an actor's map or null ({_cut(error)})") from error
    return (code, detail, tuple(kinds), accepted_by, float(at))


def read(directory: Path, departure: float) -> Restoration:
    """The session at `directory` (its `xcon` folder), left at `departure`, read back.
    **Fails closed**: whatever its record makes raise is `Unresumable`, naming it, so a
    record nobody can read is never resumed and never stops `wlx taskd`, whose start
    reads every stranded folder through here (`stranded.find`)."""
    directory = Path(directory)
    try:
        return _read(directory, departure)
    except Unresumable:
        raise
    except Exception as error:  # noqa: BLE001 -- fail closed: an unreadable record is not resumed
        raise Unresumable(
            f"its record cannot be read ({type(error).__name__}: {_cut(error)}); end it instead"
        ) from error


def _read(directory: Path, departure: float) -> Restoration:
    try:
        config = json.loads((directory / "config.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise Unresumable(
            f"its config.json cannot be read ({_cut(error)}); end it instead"
        ) from error
    # The final review's M5: a folder copied under another name is not that session.
    # Its value quoted cut (`link._quoted`; the engine B final review), as the session kind's
    # below: this sentence is `Stranded.why`, shown on every idle frame and the page's banner.
    if str(config["session_id"]) != directory.parent.name:
        raise Unresumable(
            f"its config.json names session {_link._quoted(config['session_id'])} and its folder "
            f"is {directory.parent.name!r}, so it is not the session it records; end it instead"
        )
    starts = _rows(directory, TRIAL_STARTS)
    lines = _rows(directory, "trials.jsonl")
    if (
        "already_delivered_today" not in config
        or any("fluid_ml" not in line for line in lines)
        or (lines and not starts)
    ):
        raise Unresumable(PREDATES)
    # What a resume compares the animal's bounds with (plan ruling 3), so it must be there.
    bounds = config.get("bounds")
    if not (
        isinstance(bounds, dict)
        and isinstance(bounds.get("ceilings"), dict)
        and isinstance(bounds.get("minima"), dict)
    ):
        raise Unresumable(
            "its config.json does not hold the bounds it opened with, as ceilings and "
            "minima, so whether they have changed cannot be checked; end it instead"
        )
    session_kind = config.get("session_kind")
    if session_kind is None:
        raise Unresumable(PREDATES_KINDS)
    if session_kind not in SESSION_KINDS:
        raise Unresumable(
            f"its config.json says the session is for {_link._quoted(session_kind)}, which is not "
            f"training, piloting or recording; end it instead"
        )
    runs = _rows(directory, RUNS)
    run_rows = [row for row in runs if row["event"] == "start"]
    controls = _rows(directory, CONTROLS)
    ends = [row for row in controls if row["kind"] == "end"]
    changes = _rows(directory, "parameter_changes.jsonl")

    hand = [row for row in controls if row["kind"] == "reward"]
    commanded = sum(float(line["fluid_ml"]) for line in lines)
    commanded += sum(float(row["ml"]) for row in hand)
    instants = [line["last_reward_at"] for line in lines if line["last_reward_at"] is not None]
    instants += [row["at"] for row in hand if row["at"] is not None]

    # The run and task numbers each start row recorded, the largest of each (the final
    # review's I3). Never counted from the rows: a run that raised after `start_run` and
    # before its row took numbers no row holds, and a count would issue them again. Its
    # row is written before the run's first strobe, so every run number strobed is here.
    # Trials and blocks are taken from the starts, the largest of each.
    levels = Levels()
    for row in run_rows:
        if any(key not in row for key in RUN_NUMBERS):
            raise Unresumable(
                f"its runs.jsonl start row for run {_link._quoted(row['run'])} does not record "
                f"its run and task numbers, so the next run's could repeat one in the "
                f"recording; end it instead"
            )
        name = levels.task = task_name(row["task"])
        levels.runs = max(levels.runs, int(row["run_in_session"]))
        levels.task_runs[name] = max(levels.task_runs.get(name, 0), int(row["run_in_task"]))
        levels.order[name] = max(levels.order.get(name, 0), int(row["task_in_session"]))
        levels.task_trials.setdefault(name, 0)
        levels.task_blocks.setdefault(name, 0)
        levels.task_tallies.setdefault(name, Tally())
    for row in starts:
        name = task_name(row["task"])
        levels.trials = max(levels.trials, int(row["trial_number"]))
        levels.blocks = max(levels.blocks, int(row["block_in_session"]))
        levels.task_trials[name] = max(levels.task_trials.get(name, 0), int(row["trial_in_task"]))
        levels.task_blocks[name] = max(levels.task_blocks.get(name, 0), int(row["block_in_task"]))
    tasks = {int(row["trial_number"]): task_name(row["task"]) for row in starts}
    for line in lines:
        number = int(line["trial_number"])
        if number not in tasks:
            raise Unresumable(
                f"its trials.jsonl names trial {number}, which trial_starts.jsonl does not; "
                f"end it instead"
            )
        for tally in (levels.session_tally, levels.task_tallies[tasks[number]]):
            if line["outcome"] == "hang":
                tally.hangs += 1
            else:
                tally.outcomes[Outcome(line["outcome"])] += 1

    # The values the last run started with, then the changes made during it: a change in
    # an earlier run is already in the last start row (`runs.jsonl`'s `bounded`). **The
    # out-of-cage limit is in no start row**, so its latest change, in any run, is carried
    # (the final review's I2): a limit the session lowered is never reverted to the file's.
    run_index = int(run_rows[-1]["run"]) if run_rows else None
    bounded = dict(run_rows[-1]["bounded"]) if run_rows else {}
    for change in sorted(changes, key=lambda c: int(c["sequence"])):
        if change["name"] == OUT_OF_CAGE or (
            change["run"] == run_index and change["name"] in bounded
        ):
            bounded[change["name"]] = float(change["now"])
    # How the last run ended, for the frames and the summary (the final review's M1): its
    # end row's reason, or, with none, that its process died in it. A session that ran no
    # run and was ended says so, as `Session.end_runs` words it.
    stopped_because, stop_kind = "", None
    if run_index is not None:
        end = [row for row in runs if row["event"] == "end" and row["run"] == run_index]
        if end:
            stopped_because, stop_kind = str(end[-1]["stopped_because"]), end[-1]["stop_kind"]
        else:
            stopped_because = (
                f"run {run_index + 1} stopped with its process; its record holds no end for it"
            )
            stop_kind = "fault"
    elif ends:
        # A record written before b2b (2026-10-02) holds a string here, and `actor.read`
        # returns it as written.
        stopped_because = (
            f"session ended by {actors.shown(actors.read(ends[0]['by']))}, before any run"
        )
        stop_kind = "operator"
    accepted = tuple(
        _accepted(row, number, session_kind)
        for number, row in enumerate(_rows(directory, ACCEPTED_WARNINGS), start=1)
    )
    return Restoration(
        session_id=str(config["session_id"]),
        subject=str(config["subject"]),
        deployment=str(config["deployment"]),
        view=str(config["setup"]["view"]),
        session_kind=session_kind,
        subject_settings=str(config["versions"]["subject_settings"]),
        bounds_at_open=bounds,
        already_today=config["already_delivered_today"],
        departure=departure,
        commanded=commanded,
        last_reward_at=max(instants) if instants else None,
        levels=levels,
        run_index=run_index,
        sequence=max((int(c["sequence"]) for c in changes), default=0),
        bounded=bounded,
        last_written_at=max(path.stat().st_mtime for path in directory.iterdir()),
        ended=bool(ends),
        stopped_because=stopped_because,
        stop_kind=stop_kind,
        accepted=accepted,
    )
