"""The warnings list (engine spec §19.2): every imperfection a session runs with, each stating
the session kinds it is acceptable in; outside them it refuses. **Pure**: it reads what it is
given and decides nothing about a session. `taskd.Session.accept` records what a person
accepted (`warnings.jsonl`), `service.Service._open` asks for the rig's warnings at the open
and `_start` for a run's in its pre-flight (spec §19.3: "Accepted once per session, at open,
recorded"; "a warning appearing later asks again").

**What this build lists:** the default calibration and a calibration past 30 days (spec §7.1,
§7.10); a calibration that will not load or is dated after today, which no kind accepts (the
engine B plan, call 19: every run's pre-flight fails on it, and nothing else reads it); a
chaired session's free head (§5.9); a task's warnings, its load-time findings that
are warnings (`luminance-step`, `color-on-default`, `contrast-on-default`); and today's
pre-flight unknowns, the pump calibration and the eye tracker (S9a §10). **What later builds
add**, each waiting on the build named: dithering and a timing record older than a graphics
change (E, V1); a pattern near the pixel limit, and a screen, mode or care-feature mismatch
(E); frame-clock faults (E, F); a lossy image (A4).

**Not built: a warning appearing during a run** (spec §19.3's pause at the next trial). Nothing
in this build can appear mid-run outside its kinds: the calibration is loaded once, as `wlx
taskd` starts; a calibration's age is accepted in every kind; and the rest are fixed when a run
starts. XC-276 waits on build E, the first that can.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable
from dataclasses import dataclass
from datetime import date

from wl_xcon.findings import SESSION_KINDS, kind_named
from wl_xcon.photometry import SRGB_WHITE_CD_M2, Calibration
from wl_xcon.welfare import Deployment

#: The codes this module gives, as a person accepts them.
DEFAULT_CALIBRATION = "default calibration"
CALIBRATION_AGE = "calibration age"
CALIBRATION_RECORD = "calibration record"
HEAD_FREE = "head free"
#: The code of a row saying the warnings could not be listed at all (`service.Service`'s idle
#: frame and its run's pre-flight; the engine B plan, calls 27 and 31): not a warning, so no
#: console says it as one every run refuses.
UNLISTED = "warnings"

#: Past this many days a calibration is listed; it never expires (spec §7.10; the PI, N§4
#: batch 3: "never expires, but there is an age ... A warning pops after 30 days").
CALIBRATION_WARN_AFTER_DAYS = 30


@dataclass(frozen=True, slots=True)
class Entry:
    """One warning: its code, its sentence (`detail`, as a `Finding`'s is), and the session
    kinds it is acceptable in -- none, for one no session accepts."""

    code: str
    detail: str
    accepted_in: tuple[str, ...]

    def __post_init__(self) -> None:
        for kind in self.accepted_in:
            kind_named(kind)

    @property
    def key(self) -> tuple[str, str]:
        """What identifies it once accepted: its code and its sentence (call 7), so the same
        code with a new sentence is asked again."""
        return (self.code, self.detail)


def of_findings(findings: Iterable) -> list[Entry]:
    """A task's warnings: its load-time findings that are warnings, each under its code."""
    return [Entry(f.code, f.detail, f.accepted_in) for f in findings if f.is_warning]


def of_calibration(calibration: Calibration, today: date) -> list[Entry]:
    """The calibration's: the default's, or a measured one's age past 30 days -- or, dated
    after `today`, one no session kind accepts, since its date or this host's clock is wrong
    (the engine B plan, call 19)."""
    if calibration.standard:
        return [Entry(DEFAULT_CALIBRATION, (
            f"the rig names no measured calibration, so colors and luminances are the sRGB "
            f"standard's (its primaries, D65 white at {SRGB_WHITE_CD_M2:g} cd/m², its transfer "
            f"curve) and no luminance here was measured; how closely the panel's sRGB mode "
            f"follows the standard is UNVERIFIED (engine spec §7.1)"), SESSION_KINDS)]
    age = calibration.age_days(today)
    if age < 0:
        return [Entry(CALIBRATION_AGE, (
            f"calibration {calibration.id} is dated {calibration.measured_on}, after today "
            f"({today.isoformat()}): its date or this host's clock is wrong, and no session kind "
            f"accepts it, so every run's pre-flight fails on it until one is corrected"), ())]
    if age > CALIBRATION_WARN_AFTER_DAYS:
        return [Entry(CALIBRATION_AGE, (
            f"calibration {calibration.id} was measured on {calibration.measured_on}, {age} days "
            f"ago; past {CALIBRATION_WARN_AFTER_DAYS} days a calibration is listed, never refused "
            f"(engine spec §7.10)"), SESSION_KINDS)]
    return []


def of_unloaded(refusal: str) -> list[Entry]:
    """A calibration record the rig names and that will not load, as `cli._load_calibration`
    refused it (the review's C1): one entry no session kind accepts, so every run's pre-flight
    fails on it, with the refusal's own sentence, while `wlx taskd` goes on taking opens, ends
    and returns."""
    return [Entry(CALIBRATION_RECORD, (
        f"{refusal}; no session kind accepts a calibration that will not load, so every run's "
        f"pre-flight fails on it until the record is repaired and wlx taskd started again"), ())]


def of_deployment(deployment: Deployment) -> list[Entry]:
    """A chaired session's: the head is free, so positions assume a nominal head (spec §5.9)."""
    if deployment is Deployment.RIG_CHAIRED:
        return [Entry(HEAD_FREE, (
            "a chaired session's head is free, so every stimulus position assumes a nominal head "
            "position (engine spec §5.9)"), SESSION_KINDS)]
    return []


def of_unknowns(items: Iterable) -> list[Entry]:
    """Today's pre-flight unknowns (S9a §10), each under its item's name and sentence: the
    2026-09-19 rule, a recorded acknowledgement, in every kind."""
    return [Entry(item.name, item.said, SESSION_KINDS) for item in items if item.result == "unknown"]


def refused(entries: Iterable[Entry], kind: str) -> list[Entry]:
    """The entries a session of `kind` does not accept."""
    kind_named(kind)
    return [entry for entry in entries if kind not in entry.accepted_in]


def owed(entries: Iterable[Entry], accepted: Collection[tuple[str, str]]) -> list[Entry]:
    """The entries not yet accepted, by `Entry.key`."""
    return [entry for entry in entries if entry.key not in accepted]


def sentence(entries: Iterable[Entry]) -> str:
    """The entries as a refusal or a pre-flight item says them."""
    return "; ".join(f"{entry.code}: {entry.detail}" for entry in entries)
