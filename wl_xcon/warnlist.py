"""The warnings list (engine spec §19.2): every imperfection a session runs with, each stating
the session kinds it is acceptable in; outside them it refuses. **Pure**: it reads what it is
given and decides nothing about a session. `taskd.Session.accept` records what a person
accepted (`warnings.jsonl`), `service.Service._open` asks for the rig's warnings at the open
and `_start` for a run's in its pre-flight (spec §19.3: "Accepted once per session, at open,
recorded"; "a warning appearing later asks again").

**What this build lists:** the default calibration and a calibration past 30 days (spec §7.1,
§7.10); a calibration that will not load -- a record, or a rig field that is no record's path
-- in whose place the default runs, and one dated after today (accepted in every kind since the
PI's rulings on XC-352, 2026-10-11, E1 and E2: no kind accepted them, and every run's pre-flight
failed on them, until then); a resumed session's calibration, when it is not the one the
session opened on (the warnings-over-refusals review's I2), and its half-IPD, when it is not
the one it opened on (Task 7's review, I1); a chaired session's free head (§5.9); a
stereoscope's setup -- the nominal half-IPD, another animal's settings, a half-IPD outside the
drawn optics -- and settings direct view ignores (the PI's rulings on XC-352, 2026-10-11, C6,
C7, C8 and H4); a pause the allocation cannot mark (D5), accepted as it is taken; a task's
warnings, its load-time findings that are warnings (`luminance-step`, `color-on-default`,
`contrast-on-default`, and, since the PI's rulings of 2026-10-11, `head-not-fixed`,
`overlapping-windows`, `crowded-array`, `wrong-eye-criterion`, `monocular-stereogram`,
`wrong-setup`, `isoluminance-on-default`, `unrealizable-color`, `cone-colors-without-spectra`,
`hold-cut-short` (engine build C2a), `windows-left-behind` (2026-10-27, an array's object
window scored after a `Show` or an `Update` that can draw it as no array), `cyclopean-windows`
(2026-10-28, an array's object window scored where the array can be drawn with a position per eye
or a disparity, its windows staying about its cyclopean position), `direction-outside-0-360` and
`negative-eccentricity` (2026-10-30, the PI's "Warn at load" twice: a setting used as a direction,
a position's or a grating's drift, that can be outside 0 to 360, and a position at an eccentricity
below 0, each written two ways, a plan condition's value included)
and, for a value outside its declared range at a run's start or live, `outside-range` and, for a
wait longer than any the task declares, `longer-than-declared`, by his answer of 2026-10-12);
and today's pre-flight unknowns, the pump calibration and the eye tracker (S9a §10). **What
later builds add**, each waiting on the build named: dithering and a timing record older than a
graphics change (E, V1); a pattern near the pixel limit, and a screen, mode or care-feature
mismatch (E); frame-clock faults (E, F); a lossy image (A4).

**Not built: a warning appearing during a run outside its kinds** (spec §19.3's pause at the
next trial). Nothing in this build can: the calibration is loaded once, as `wlx taskd` starts;
a calibration's age is accepted in every kind; the rest are fixed when a run starts; and those
that can appear during a run since the PI's rulings on XC-352 (2026-10-11) are accepted as they
happen, in every kind, by whoever set the value or paused: a pause the allocation cannot mark
(D5), and a live value outside its declared range (D2) -- `outside-range`, `longer-than-declared`
for a wait longer than any the task declares, and each warning the task's checks give widened
to it and not as declared (`overlapping-windows`, `crowded-array`, `unrealizable-color`,
`wrong-setup` and the rest, each prefixed "with 'x' at v, outside its declared range"); one its
session's kind does not accept refuses the value instead (`taskd.Session._beyond_range`).
XC-276 waits on build E, the first that can.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Collection, Iterable
from dataclasses import dataclass
from datetime import date

from wl_xcon import link as _link
from wl_xcon.findings import SESSION_KINDS, kind_named
from wl_xcon.geometry import Rig, SubjectSettings
from wl_xcon.photometry import SRGB_WHITE_CD_M2, Calibration
from wl_xcon.welfare import Deployment

#: The codes this module gives, as a person accepts them.
DEFAULT_CALIBRATION = "default calibration"
CALIBRATION_AGE = "calibration age"
CALIBRATION_RECORD = "calibration record"
CALIBRATION_CHANGED = "calibration changed"
SETUP_CHANGED = "setup changed"
HEAD_FREE = "head free"
NOMINAL_HALF_IPD = "nominal half-IPD"
OTHER_ANIMALS_SETTINGS = "another animal's settings"
HALF_IPD_OUTSIDE = "half-IPD outside the optics"
SETTINGS_NOT_READ = "settings not read"
#: A pause the allocation cannot mark (`taskd.Session._pause`; the PI, 2026-10-11, XC-352's D5).
PAUSE_UNMARKED = "pause unmarked"
#: The code of a row saying the warnings could not be listed at all (`service.Service`'s idle
#: frame and its run's pre-flight; the engine B plan, calls 27 and 31): not a warning, so no
#: console says it as one every run refuses.
UNLISTED = "warnings"

#: Past this many days a calibration is listed; it never expires (spec §7.10; the PI, N§4
#: batch 3: "never expires, but there is an age ... A warning pops after 30 days").
CALIBRATION_WARN_AFTER_DAYS = 30

#: What no warning's code holds: a run's pre-flight names the codes it asks to accept as a list
#: in parentheses, a repeated one with its count ("luminance-step ×30"; `preflight.warnings`),
#: and its rule that a cut never drops a name relies on never meeting one of these in a code.
CODE_REFUSES = (",", "(", ")", "×")


@dataclass(frozen=True, slots=True)
class Entry:
    """One warning: its code, its sentence (`detail`, as a `Finding`'s is), and the session
    kinds it is acceptable in -- none, for one no session accepts.

    **It refuses what its consumers cannot carry** (the engine B final review): an empty code,
    a code holding one of `CODE_REFUSES`, and kinds that are not a tuple of the three, each
    named once. A record read back from disk is held to this before a resume
    (`resume._accepted`), so a damaged row is left out of the resume and its warning asked again
    (XC-352's C11), never an exception."""

    code: str
    detail: str
    accepted_in: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.code, str) or not self.code.strip():
            raise ValueError("a warning's code is text, and this one is empty")
        for held in CODE_REFUSES:
            if held in self.code:
                raise ValueError(
                    f"a warning's code never holds {held!r}, which a run's pre-flight uses to "
                    f"list the codes it asks to accept"
                )
        if not isinstance(self.accepted_in, tuple):
            raise TypeError(
                f"a warning's accepted_in is a tuple of session kinds, not "
                f"{type(self.accepted_in).__name__}"
            )
        for kind in self.accepted_in:
            kind_named(kind)
            if self.accepted_in.count(kind) > 1:
                raise ValueError(f"a warning's accepted_in names {kind!r} twice")

    @property
    def key(self) -> tuple[str, str]:
        """What identifies it once accepted: its code and its sentence (call 7), so the same
        code with a new sentence is asked again."""
        return (self.code, self.detail)


def of_findings(findings: Iterable) -> list[Entry]:
    """A task's warnings: its load-time findings that are warnings, each under its code."""
    return [Entry(f.code, f.detail, f.accepted_in) for f in findings if f.is_warning]


def of_calibration(calibration: Calibration, today: date, unloaded: bool = False) -> list[Entry]:
    """The calibration's: the default's, or a measured one's age past 30 days -- or, dated
    after `today`, a warning in every kind that its date or this host's clock is wrong (the PI,
    2026-10-11, XC-352's E2; no kind accepted it until then, the engine B plan's call 19). Every
    sentence an open can be asked to accept fits `link.NOTE_LIMIT`, which the open's form sends
    back (a calibration's id is at most `photometry.ID_LIMIT` characters). **`unloaded`**: the
    default stands in for a record the rig names that would not load (`of_unloaded`, listed
    first; XC-352's E1), and its sentence says so, not that the rig names none (the
    warnings-over-refusals review's M4) -- a record, or a field that is no record's path."""
    if calibration.standard:
        why = ("the calibration the rig names would not load" if unloaded
               else "the rig names no measured calibration")
        return [Entry(DEFAULT_CALIBRATION, (
            f"{why}, so colors and luminances are the sRGB "
            f"standard's (its primaries, D65 white at {SRGB_WHITE_CD_M2:g} cd/m², its transfer "
            f"curve) and no luminance here was measured; how closely the panel's sRGB mode "
            f"follows the standard is UNVERIFIED (engine spec §7.1)"), SESSION_KINDS)]
    age = calibration.age_days(today)
    if age < 0:
        return [Entry(CALIBRATION_AGE, (
            f"calibration {calibration.id} is dated {calibration.measured_on}, after today "
            f"({today.isoformat()}): its date or this host's clock is wrong; check this host's "
            f"clock, which every welfare time is anchored to, and the record's date (wlx taskd "
            f"reads both as it starts)"), SESSION_KINDS)]
    if age > CALIBRATION_WARN_AFTER_DAYS:
        return [Entry(CALIBRATION_AGE, (
            f"calibration {calibration.id} was measured on {calibration.measured_on}, {age} days "
            f"ago; past {CALIBRATION_WARN_AFTER_DAYS} days a calibration is listed, never refused "
            f"(engine spec §7.10)"), SESSION_KINDS)]
    return []


def of_unloaded(refusal: str) -> list[Entry]:
    """A calibration the rig names and that will not load -- a record, or a field that is no
    record's path -- as `cli._load_calibration` refused it: **a warning in every kind that the
    default runs in its place** (the PI, 2026-10-11, XC-352's E1: "fall back to the default with a
    warning"; no kind accepted it, and every run's pre-flight failed on it, until then), in
    `wlx taskd`, `wlx run` and `wlx check` alike. The refusal is quoted cut in its middle, so
    the whole sentence stays within `link.NOTE_LIMIT`, which the open's form sends back, and keeps
    why it would not load; `wlx taskd` prints it whole as it starts. **Each control character in
    it is U+FFFD** (Task 6's review, minor): the page sends the sentence back exactly as its HTML
    attribute gives it, and an attribute turns a carriage return into a line feed and a NUL into
    U+FFFD, so a record whose bad key held either could never be accepted."""
    tail = (
        "; this session runs on the default calibration, the sRGB standard, in its place, until "
        "the rig's calibration is repaired and read again (wlx taskd reads it as it starts; engine "
        "spec §7.1)"
    )
    refusal = "".join("\ufffd" if unicodedata.category(ch) == "Cc" else ch for ch in refusal)
    room = _link.NOTE_LIMIT - len(tail)
    if len(refusal) > room:
        # Its middle cut: a record's refusal names its path first and why it would not load last.
        head = room // 3
        refusal = refusal[:head] + "…" + refusal[-(room - head - 1):]
    return [Entry(CALIBRATION_RECORD, refusal + tail, SESSION_KINDS)]


def of_changed_calibration(opened_on: str | None, now: Calibration) -> list[Entry]:
    """A stranded session resumed by a service that runs `now`, not the calibration it opened on,
    whose id its `config.json` names (`opened_on`, `None` for none): **a warning in every kind,
    never a refusal** (the warnings-over-refusals review's I2; the PI's rule of 2026-10-11), asked
    with the resumed session's first run, naming both. The record stays interpretable: each run's
    start row names the calibration it ran against."""
    was = "no calibration" if opened_on is None else f"calibration {opened_on}"
    standard = ", the sRGB standard, measured by nobody," if now.standard else ""
    return [Entry(CALIBRATION_CHANGED, (
        f"this session opened on {was}, which its config.json names, and is resumed on calibration "
        f"{now.id}{standard} which this wlx taskd runs on: its runs from here are checked and "
        f"drawn against {now.id}, and each run's start row in runs.jsonl names the calibration it "
        f"ran against"), SESSION_KINDS)]


def of_changed_setup(
    opened_on_cm: float, opened_nominal: bool, now_cm: float, now_nominal: bool
) -> list[Entry]:
    """A stranded stereoscope session resumed on another half-IPD than its `config.json` names
    (Task 7's review, I1; modeled on `of_changed_calibration`): the animal's settings file was
    removed, added or changed since it opened. **A warning in every kind, never a refusal** (the PI's
    rule of 2026-10-11), asked with the resumed session's first run, naming both. `config.json`
    keeps what it opened on; the `session resumed` row in welfare_notes.jsonl names what it now
    runs on."""
    opened = "nominal" if opened_nominal else "from the animal's settings"
    # No file is read when it is nominal, so the sentence never says one was.
    now = "nominal" if now_nominal else "from the settings file now read"
    return [Entry(SETUP_CHANGED, (
        f"this session opened on a half-IPD of {opened_on_cm:g} cm ({opened}), which its "
        f"config.json names, and is resumed on {now_cm:g} cm ({now}): its runs from here are "
        f"drawn at {now_cm:g} cm, and the session resumed row in welfare_notes.jsonl names it"),
        SESSION_KINDS)]


def of_deployment(deployment: Deployment) -> list[Entry]:
    """A chaired session's: the head is free, so positions assume a nominal head (spec §5.9)."""
    if deployment is Deployment.RIG_CHAIRED:
        return [Entry(HEAD_FREE, (
            "a chaired session's head is free, so every stimulus position assumes a nominal head "
            "position (engine spec §5.9)"), SESSION_KINDS)]
    return []


def of_setup(
    rig: Rig, subject: str, half_ipd_cm: float, settings: SubjectSettings | None, path
) -> list[Entry]:
    """A stereoscope's setup for `subject`, built for `half_ipd_cm` from `settings` (read from
    `path`), or for the nominal half-IPD when there are none (the PI, 2026-10-11, XC-352's C6, C7
    and C8; each refused until then), **each a warning in every kind**: no settings file, so the
    nominal half-IPD, recorded as nominal (`config.json`'s `setup.half_ipd_nominal`); another
    animal's settings, whose half-IPD the session uses; and a half-IPD outside the optics
    drawing's table, its field extrapolated."""
    entries = []
    if settings is None:
        entries.append(Entry(NOMINAL_HALF_IPD, (
            f"{subject!r} has no settings file, so the stereoscope is built for the optics "
            f"drawing's nominal half-IPD, {half_ipd_cm:g} cm, which is not a measurement (STE-20): "
            f"disparities and the vergence offset assume it, and the session records it as "
            f"nominal"), SESSION_KINDS))
    elif settings.subject != subject:
        entries.append(Entry(OTHER_ANIMALS_SETTINGS, (
            f"{path} holds {settings.subject!r}'s settings, and this session is {subject!r}'s: "
            f"these are {settings.subject!r}'s settings, so the stereoscope is built for "
            f"{settings.subject!r}'s half-IPD of {half_ipd_cm:g} cm"), SESSION_KINDS))
    low, high = rig.half_ipd_range_cm
    if not low <= half_ipd_cm <= high:
        entries.append(Entry(HALF_IPD_OUTSIDE, (
            f"a half-IPD of {half_ipd_cm:g} cm is outside the {low:g}-{high:g} cm this "
            f"stereoscope is drawn for (IPD {20 * low:g}-{20 * high:g} mm, the optics drawing's "
            f"table): its mirrors and its field are extrapolated there, not drawn, so positions "
            f"and the off-screen check rest on an unmodeled field"), SESSION_KINDS))
    return entries


def of_ignored_settings(path) -> list[Entry]:
    """`--subject-settings` given with direct view, which reads nothing from it: a warning that
    the session ignores it (the PI, 2026-10-11, XC-352's H4; refused until then)."""
    return [Entry(SETTINGS_NOT_READ, (
        f"--subject-settings {path} holds the stereoscope's half-IPD, and direct view reads "
        f"nothing from it, so this session ignores it"), SESSION_KINDS)]


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
