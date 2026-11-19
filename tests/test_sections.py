"""The Task parameters tab in sections (the console settings design's §7; the PI, 2026-11-16: "The
task file names it", "As you last left them"): `Param.section` names the section, `/` making a
subsection; a setting naming none goes to Timing where its unit is seconds, else Other; each
header counts its settings and how many differ from the task's start. The sections are the
summary's (the summary and editor design of 2026-11-19), which no longer fold; the browser's
half is in `test_page_browser.py`. Engine test material, run only in the
simulator: no number here is a timing claim about the rig.
"""

from __future__ import annotations

import re

import pytest

import _sessions
from _frames import frame, view
from _rig import DIRECT
from wl_xcon.actor import Box
from wl_xcon.dio import Simulated as Card
from wl_xcon.link import ParamRow, SetForm, SetParameter, Simulated, Telemetry, decode, encode
from wl_xcon.photometry import SRGB
from wl_xcon.task import (
    CEILINGS, OTHER, SECTION_LIMIT, TIMING, TRAINING_SECTION, Param, section_of,
)
from wl_xcon.taskd import Session, SessionSpec
from wl_xcon.web import fragments
from wl_xcon.welfare import Deployment, Simulated as Pump

WALL_NOW = 1_700_000_000.0
JAKE = Box("jake")


def test_a_settings_section_falls_back_to_timing_by_unit_then_other():
    """The task file's own name wins, whatever the unit; none named, seconds are Timing and every
    other unit Other. `Training` is the name the Training tab gathers."""
    assert section_of(Param("fix_hold", unit="s")) == TIMING == "Timing"
    assert section_of(Param("fix_window", unit="deg")) == OTHER == "Other"
    assert section_of(Param("x", unit="s", section="Gaze windows")) == "Gaze windows"
    assert section_of(Param("x", unit="deg", section="Stimuli/fixation point")) == (
        "Stimuli/fixation point")
    assert section_of(Param("x", unit="", section="")) == OTHER
    assert TRAINING_SECTION == "Training" and CEILINGS != TIMING


@pytest.mark.parametrize("section", [
    "Timing", "Gaze windows", "Stimuli/fixation point", "é°", "a" * SECTION_LIMIT, ""])
def test_a_section_one_printable_line_of_two_levels_is_taken(section):
    assert Param("x", unit="s", section=section).section == section


@pytest.mark.parametrize("section", [
    "a" * (SECTION_LIMIT + 1), "A/B/C", "Stimuli/", "/fixation", "A\nB", "A\tB", "A//B", " / ", 3,
    None])
def test_param_section_is_one_printable_line_of_two_levels_at_most(section):
    """Refused as the setting is built, saying what is allowed and what was given."""
    with pytest.raises(ValueError, match=r"section is one printable line of 60 characters"):
        Param("x", unit="s", section=section)


def _row(name, section, changed=False, unit="s"):
    return ParamRow.of(name, unit, 0.0, 10.0, 1.0, False, section=section, changed=changed)


def _summary_only(html: str) -> str:
    """The pane's summary, before its legend and the editor (the summary and editor design of
    2026-11-19): the sections are its."""
    return html.partition('<div class="legend">')[0]


def _groups(html: str) -> list[tuple[str, list]]:
    """Each summary section's header whole -- its `title`, `N settings · M changed` -- and the
    settings of the lines directly under it, in page order: the text from its header to the next
    section's start, nested or not. Rewritten for the summary and editor design, from each
    section's `<details>` and the boxes under it."""
    found = []
    for piece in re.split(r'(?=<div class="ssec")', _summary_only(html))[1:]:
        title = re.search(r'<h4 title="([^"]*)">', piece).group(1)
        body = piece.split("</h4>", 1)[1]
        found.append((title, re.findall(r'<button type="button" class="line[^"]*" '
                                        r'data-open="(.*?)"', body)))
    return found


def test_cards_are_grouped_in_declared_order_each_header_counting():
    """Sections in the order their first setting is declared; a setting of a section declared
    again later joins it; a subsection is nested in its parent, whose count takes it in; a row
    made by hand naming none is under Other; each header says `N settings · M changed`."""
    rows = (
        _row("fix_hold", "Timing"),
        _row("fix_window", "Gaze windows", unit="deg"),
        _row("fix_size", "Stimuli/fixation point", unit="deg"),
        _row("fix_color", "Stimuli/fixation point", unit="deg"),
        _row("array_size", "Stimuli/array", unit="deg"),
        _row("response_deadline", "Timing"),
        _row("loose", ""),
        _row("target_hold", "Timing"),
    )
    html = fragments(frame(params=rows), view())["params"]

    assert [(h.split(" · ")[0]) for h, _ in _groups(html)] == [
        "Timing", "Gaze windows", "Stimuli", "fixation point", "array", "Other"]
    by = dict(_groups(html))
    assert by["Timing · 3 settings · 0 changed"] == ["fix_hold", "response_deadline", "target_hold"]
    assert by["Gaze windows · 1 setting · 0 changed"] == ["fix_window"]
    assert by["Stimuli · 3 settings · 0 changed"] == []
    assert by["fixation point · 2 settings · 0 changed"] == ["fix_size", "fix_color"]
    assert by["array · 1 setting · 0 changed"] == ["array_size"]
    assert by["Other · 1 setting · 0 changed"] == ["loose"]
    # The subsections are inside their parent, which holds its own settings first.
    stimuli = html[html.index('data-section="Stimuli"'):html.index('data-section="Other"')]
    assert stimuli.index('data-section="Stimuli/fixation point"') < stimuli.index(
        'data-section="Stimuli/array"')
    assert f'data-task="{frame().task}"' in html
    summary = _summary_only(html)
    assert summary.count('<div class="ssec"') == 6 and "<details" not in summary


def test_a_changed_setting_counts_in_its_sections_header():
    """Through the web pane: a row `changed` counts in its header, and in its parent's."""
    rows = (_row("fix_hold", "Timing", changed=True), _row("response_deadline", "Timing"),
            _row("fix_size", "Stimuli/fixation point", changed=True, unit="deg"),
            _row("fix_color", "Stimuli/fixation point", unit="deg"))
    html = fragments(frame(params=rows), view())["params"]

    assert "Timing · 2 settings · 1 changed" in html
    assert "Stimuli · 2 settings · 1 changed" in html
    assert "fixation point · 2 settings · 1 changed" in html


def test_a_card_escapes_its_sections_name():
    html = fragments(frame(params=(_row("x", 'A"><script>alert(1)</script>'),)), view())["params"]
    assert "<script>" not in html and "&lt;script&gt;" in html


class _Drained(Simulated):
    """A link that queues `script[n]` as the `n`th drain begins, keeping each drain's rows."""

    BUDGET = 40

    def __init__(self, script):
        super().__init__()
        self.script, self.drains, self.seen, self.session = dict(script), 0, {}, None

    def drain(self) -> list:
        self.drains += 1
        assert self.drains <= self.BUDGET, f"the session drained {self.drains} times"
        if self.session is not None and self.session.phase == "running":
            self.seen[self.drains] = {row[0]: row for row in self.session.parameters}
        for command in self.script.get(self.drains, ()):
            self.queue(command)
        return super().drain()


def _run(tmp_path, link, values=None) -> Session:
    spec = SessionSpec(
        task="tasks/fixation_detection.py", allocation="tasks/allocation.py", root=tmp_path,
        session_id="2027-01-14_01", subject="A", trials=4, frame_period=1 / 240, seed=7,
        values=values or {}, bounds=_sessions.bounds(), already_delivered_today=0.0,
        deployment=Deployment.RIG_FIXED, geometry=DIRECT, session_kind="training",
        calibration=SRGB)
    session = Session(spec, card=Card(), pump=Pump(), link=link)
    session.wall_clock = lambda: WALL_NOW + session.now()
    session.left_cage(at=WALL_NOW)
    session.head_fixed(at=session.wall_now())
    link.session = session
    session.run()
    return session


def _changed(row) -> bool:
    return row[18]


def test_a_setting_a_person_holds_or_the_run_was_given_is_changed_and_the_tasks_start_is_not(
        tmp_path):
    """From `Session.parameters` (the row's 18th and 19th items): a value a person holds, a form a
    person gave and a value the run was given are `changed`; the task's start, and a welfare
    ceiling, are not. Each row carries its section, a ceiling's `CEILINGS`. Between runs none are
    changed. Through the wire the row keeps both."""
    link = _Drained({
        2: [SetParameter(name="fix_hold", value=0.4, by=JAKE),
            SetForm(name="response_deadline", shape="non_aging",
                    numbers={"shortest": 0.5, "longest": 1.0}, by=JAKE)]})
    session = _run(tmp_path, link, values={"target_hold": 0.25})

    first = link.seen[min(link.seen)]
    last = link.seen[max(link.seen)]
    assert not any(_changed(row) for name, row in first.items() if name != "target_hold")
    assert _changed(first["target_hold"]) and first["target_hold"][17] == TIMING
    assert _changed(last["fix_hold"]), "a value a person holds"
    assert _changed(last["response_deadline"]), "a form a person gave"
    assert not _changed(last["fix_acquisition"])
    assert last["fix_window"][17] == OTHER
    ceilings = [row for row in session.parameters if row[5]]
    assert ceilings and all(row[17] == CEILINGS and not _changed(row) for row in ceilings)

    sent = [decode(encode(f)) for f in link.published if isinstance(f, Telemetry)][-1]
    by = {row.name: row for row in sent.params}
    assert (by["fix_hold"].section, by["fix_window"].section) == (TIMING, OTHER)
    assert by["target_hold"].changed and not by["fix_acquisition"].changed
