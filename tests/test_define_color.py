"""A new color saved as its set's proposed file, by the service in any phase (`link.DefineColor`,
`service.Service._define_color`; the console settings design's §6; its plan's Task 8; the PI,
2026-11-16: "Saved into a color set file", and for this plan "Proposed file first"); the preview
`wlx serve` gives the page (`serve.color_preview`); and the set's design in the record and on its
card.

Every test writes into its own temporary `--tasks` folder with a `stimuli` folder beside it, as
wl-xtasks has, never into the linked wl-xtasks checkout. The set is wl-xcon's copy of isohue with
its design frame added (`tests/fixtures/isohue_design.json`). Engine test material, run only in the
simulator: no number here is a timing claim about the rig.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

import test_color_card as card
from _calibrations import measured
from _frames import frame
from test_service import _folders, _made, _open, _step
from wl_xcon import colordef, link, photometry, serve
from wl_xcon.actor import Box
from wl_xcon.link import CommandRefused, DefineColor, ParamRow, _command_from, decode, encode
from wl_xcon.photometry import ColorSet

FIXTURES = Path(__file__).parent / "fixtures"
DESIGNED = FIXTURES / "isohue_design.json"
ISOHUE = ColorSet.load(DESIGNED)
BY = Box("jake")


def _define(name="violet", *, colorset="isohue", new_set=False, method="hue_angle", numbers=None):
    """A new color by its hue angle, 290° (between isohue's blue and purple, which the sRGB
    standard shows with the set) unless other numbers are given."""
    return DefineColor(colorset=colorset, new_set=new_set, name=name, method=method,
                       numbers={"hue_deg": 290.0} if numbers is None else numbers, by=BY)


def _layout(tmp_path, *, stimuli=True):
    """A service's folders, `--tasks` with `stimuli/isohue.json` beside it (the design copy)."""
    folders = _folders(tmp_path)
    if stimuli:
        (folders[1].parent / "stimuli").mkdir()
        shutil.copy(DESIGNED, folders[1].parent / "stimuli" / "isohue.json")
    return folders


def _said(published) -> list[tuple[str, str]]:
    return [(row.kind, row.said) for row in published.controls]


def _card(colorset: ColorSet) -> dict:
    """A color card's `sets` entry for `colorset`, as the rig makes one (`Session._color_card`)."""
    return {"sets": {colorset.name: {
        "apex": list(colorset.apex), "luminance_cd_m2": colorset.luminance_cd_m2,
        "design": None if colorset.design is None else dict(colorset.design),
        "hues": {hue: {"xy": list(xy), "srgb": None} for hue, xy in colorset.colors.items()}}},
        "set": colorset.name, "hue": next(iter(colorset.colors)), "approximate": True,
        "saturation": {"setting": None, "value": 1.0, "cd_m2": 15.0},
        "luminance": {"setting": None, "value": 15.0, "cd_m2": 15.0, "set_wide": False}}


def _frame_of(colorset: ColorSet):
    rows = (ParamRow.of("distractor_appearance", "appearance", None, None, None, False,
                        source="run", color=_card(colorset)),)
    return decode(encode(frame(params=rows)))


# --- The wire ---------------------------------------------------------------------------------

def test_define_color_crosses_the_wire_and_a_page_body_and_a_malformed_one_is_refused():
    """`DefineColor` over the wire and back, `KIND` `"define_color"`, and from a page's body
    (`serve.parse_command`); a method that is none of the three, a `new_set` that is no flag and a
    word among its numbers are refused where it is decoded."""
    sent = _define()
    assert DefineColor.KIND == "define_color"
    assert link._decode_command(link._encode_command(sent)) == sent
    body = {"kind": "define_color", "colorset": "isohue", "new_set": False, "name": "cyan",
            "method": "hue_angle", "numbers": {"hue_deg": 200}}
    parsed = serve.parse_command({**body, "by": "jake"})
    assert (type(parsed), parsed.colorset, parsed.new_set, parsed.name, parsed.method,
            parsed.numbers) == (DefineColor, "isohue", False, "cyan", "hue_angle",
                                {"hue_deg": 200.0})
    wire = {**body, "by": {"kind": "box", "name": "jake"}}
    for field, bad, said in (("method", "lab", "is none of them"), ("new_set", "no", "true or false"),
                             ("numbers", {"hue_deg": "two hundred"}, "never a word"),
                             ("colorset", "", "colorset is text")):
        with pytest.raises(CommandRefused, match=said):
            _command_from({**wire, field: bad})


# --- The file ---------------------------------------------------------------------------------

def test_define_color_writes_under_proposed_and_never_the_sets_own_file(tmp_path):
    """With no session open: the set's file with the color added is written to
    `stimuli/proposed/isohue.json`, which loads, its old colors as they were; the set's own file is
    unchanged to the byte; the idle feed says where it went; a second color extends the proposal;
    and a new set's first color by hue angle makes `stimuli/proposed/warm.json`, its design the
    numbers given."""
    folders = _layout(tmp_path)
    service = _made(folders)
    stimuli = folders[1].parent / "stimuli"
    own = (stimuli / "isohue.json").read_bytes()

    published = _step(service, _define())

    proposed = ColorSet.load(stimuli / "proposed" / "isohue.json")
    xy = colordef.written(colordef.chromaticity(ISOHUE, "hue_angle", {"hue_deg": 290.0}))
    assert list(proposed.colors) == [*ISOHUE.colors, "violet"]
    assert proposed.colors["violet"] == xy
    assert all(proposed.colors[name] == ISOHUE.colors[name] for name in ISOHUE.colors)
    assert proposed.design == ISOHUE.design
    assert (stimuli / "isohue.json").read_bytes() == own
    assert [kind for kind, _ in _said(published)] == ["define_color"]
    assert _said(published)[0][1].endswith(
        "saved to " + folders[1].parent.name + "/stimuli/proposed/isohue.json for the PI to "
        "review and commit; a rig uses it once committed and pulled")
    assert [name for name in (stimuli / "proposed").iterdir()] == [stimuli / "proposed" /
                                                                    "isohue.json"]

    _step(service, _define("teal", method="xy", numbers={"x": 0.24, "y": 0.33}))
    assert list(ColorSet.load(stimuli / "proposed" / "isohue.json").colors) == [
        *ISOHUE.colors, "violet", "teal"]
    assert (stimuli / "isohue.json").read_bytes() == own

    numbers = {"hue_deg": 60.0, "gray_lightness": 62.0, "chroma": 20.0}
    _step(service, _define("amber", colorset="warm", new_set=True, numbers=numbers))
    warm = ColorSet.load(stimuli / "proposed" / "warm.json")
    assert (list(warm.colors), warm.apex, warm.luminance_cd_m2, warm.design) == (
        ["amber"], colordef.NEW_APEX, 15.0,
        {"space": "CAM16-UCS", "gray_lightness": 62.0, "chroma": 20.0})
    assert not (stimuli / "warm.json").exists()


def test_define_color_refuses_a_name_in_the_set_and_a_tasks_folder_without_stimuli(tmp_path):
    """Refused, writing nothing, each with its sentence: a `--tasks` with no `stimuli` folder
    beside it; a name the set has; a set that is missing, unless new; one that exists, if new; a
    set's name no file can have; and a hue angle into a set with no design."""
    bare = _made(_folders(tmp_path / "bare"))
    published = _step(bare, _define())
    assert "has no stimuli folder beside it, as wl-xtasks has" in published.refusals[-1].why

    folders = _layout(tmp_path / "laid")
    service = _made(folders)
    stimuli = folders[1].parent / "stimuli"
    shutil.copy(FIXTURES / "isohue.json", stimuli / "plain.json")
    for command, said in (
        (_define("green"), "already has a color 'green'"),
        (_define(colorset="nosuch"), "there is no color set 'nosuch'"),
        (_define(colorset="isohue", new_set=True,
                 numbers={"hue_deg": 1.0, "gray_lightness": 60.0, "chroma": 9.0}),
         "exists already"),
        (_define(colorset="../isohue"), "is named by 1 to 40 letters"),
        (_define(colorset="plain"), "has no design"),
        (_define("x" * 41), "printable text of 1 to 40 characters"),
    ):
        published = _step(service, command)
        assert said in published.refusals[-1].why, (said, published.refusals[-1].why)
    assert not (stimuli / "proposed").exists()
    assert _said(published) == []


def test_a_color_desaturating_the_set_on_this_panel_is_warned(tmp_path):
    """A color the panel cannot show at the set's luminance with the others is saved, and a
    `warning` on the feed says by how much the set then desaturates on which calibration: on the
    rig's with no session open, the session's with one. One the panel shows adds no warning."""
    folders = _layout(tmp_path)
    service = _made(folders)

    published = _step(service, _define("lime", method="xy", numbers={"x": 0.27, "y": 0.62}))
    kinds = [kind for kind, _ in _said(published)]
    assert kinds == ["define_color", "warning"]
    share = photometry.realize(ColorSet.load(
        folders[1].parent / "stimuli" / "proposed" / "isohue.json"), photometry.SRGB).desaturation
    assert share > 0.0
    assert _said(published)[1][1].startswith(
        f"adding lime desaturates isohue by {100 * share:.1f}% on calibration srgb-standard")

    published = _step(service, _define("dusk", method="xy", numbers={"x": 0.29, "y": 0.30}))
    assert [kind for kind, _ in _said(published)][-1] == "define_color"

    opened = _made(_layout(tmp_path / "open"))
    _step(opened, _open())
    assert opened.session is not None
    opened.calibration = measured(green=photometry.xyY(0.30, 0.45, 140.0))
    published = _step(opened, _define("lime", method="xy", numbers={"x": 0.27, "y": 0.62}))
    warned = [control.said for control in published.controls if control.kind == "warning"]
    assert len(warned) == 1 and warned[0].startswith("adding lime desaturates isohue by") and \
        "on calibration srgb-standard" in warned[0], warned


def test_a_new_color_in_a_run_is_the_services_and_never_reaches_the_run(tmp_path):
    """At a run's boundary the service takes a `DefineColor` out of what the run drains
    (`_Routed.drain`) and saves it there, as it does between runs."""
    from wl_xcon.service import _Routed

    taken = []

    class _Service:
        def _define_color(self, command):
            taken.append(command)

    wire = link.Simulated()
    wire.queue(_define())
    wire.queue(link.Pause(by=BY))
    kept = _Routed(wire, _Service()).drain()
    assert [type(command) for command in kept] == [link.Pause]
    assert taken == [_define()]


# --- The preview ------------------------------------------------------------------------------

@pytest.mark.parametrize("method, numbers", [
    ("hue_angle", {"hue_deg": 200.0}),
    ("dkl", {"azimuth_deg": 90.0, "elevation_deg": 0.0, "contrast": 0.3}),
    ("dkl", {"azimuth_deg": 90.0, "elevation_deg": 0.0}),
    ("xy", {"x": 0.24, "y": 0.33}),
])
def test_the_preview_is_what_the_rig_would_save(tmp_path, method, numbers):
    """`GET /color-preview` on the frame's set (`serve.color_preview`) gives the x and y the rig
    then saves for the same numbers in the same set, its swatch on the sRGB standard and whether
    the standard shows it; it writes nothing."""
    query = {"set": ["isohue"], "method": [method],
             **{key: [repr(value)] for key, value in numbers.items()}}
    code, answer = serve.color_preview(_frame_of(ISOHUE), query)
    assert code == 200, answer
    assert set(answer) == {"x", "y", "srgb", "in_srgb", "said"}
    service = _made(_layout(tmp_path))
    _step(service, _define("new", method=method, numbers=numbers))
    saved = ColorSet.load(service.tasks.parent / "stimuli" / "proposed" / "isohue.json")
    assert (answer["x"], answer["y"]) == saved.colors["new"]
    assert (answer["srgb"], answer["in_srgb"]) == colordef.swatch(colordef.frame(ISOHUE),
                                                                  saved.colors["new"])
    assert answer["said"].startswith(f"{colordef.SAID[method]} (")


def test_a_preview_names_why_it_defines_no_color():
    """A preview that defines none is a 400 with the sentence, its numbers null: a word for a
    number, a field given twice, a hue angle in a set with no design, and a new set by hue angle
    without its frame."""
    plain = ColorSet.load(FIXTURES / "isohue.json")
    for frame_, query, said in (
        (_frame_of(ISOHUE), {"set": ["isohue"], "method": ["xy"], "x": ["a"], "y": ["0.3"]},
         "not a number"),
        (_frame_of(ISOHUE), {"set": ["isohue"], "method": ["xy"], "x": ["0.2", "0.3"],
                             "y": ["0.3"]}, "given once"),
        (_frame_of(plain), {"set": ["isohue"], "method": ["hue_angle"], "hue_deg": ["10"]},
         "has no design"),
        (None, {"set": ["warm"], "method": ["hue_angle"], "hue_deg": ["10"]},
         "gray_lightness and chroma"),
    ):
        code, answer = serve.color_preview(frame_, query)
        assert code == 400 and answer["x"] is None and said in answer["said"], answer


def test_a_served_preview_answers_on_the_latest_frame_and_bounds_its_fields():
    """**`GET /color-preview` is served** (`serve.make_handler`'s `_color_preview`) on a real
    loopback socket with no ZMQ, no sign-in and no token, as any viewer asks: on the latest frame
    the hub holds, its answer is `color_preview`'s on that frame and the query's fields, as JSON,
    200 for a color it defines and 400 with the sentence for one it does not; a query of more than
    16 fields is refused before it is read (TSK-75), its numbers null."""
    import http.client
    import threading
    from http.server import ThreadingHTTPServer

    from _frames import ENDPOINT

    hub = serve.Hub(steady=lambda: 0.0, endpoint=ENDPOINT)
    hub.offer(_frame_of(ISOHUE))
    server = ThreadingHTTPServer(("127.0.0.1", 0),
                                 serve.make_handler(hub, token="t0ken", stale_after_s=30.0))
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05},
                              daemon=True)
    thread.start()

    def asked(path: str) -> tuple[int, str, dict]:
        connection = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
        try:
            connection.request("GET", path)
            response = connection.getresponse()
            return response.status, response.getheader("Content-Type"), json.loads(response.read())
        finally:
            connection.close()

    try:
        latest = hub.snapshot(on_box=True, stale_after_s=30.0)[0]
        defined = asked("/color-preview?set=isohue&method=hue_angle&hue_deg=290")
        assert defined == (200, "application/json", serve.color_preview(
            latest, {"set": ["isohue"], "method": ["hue_angle"], "hue_deg": ["290"]})[1])
        assert defined[2]["x"] is not None and defined[2]["said"].startswith(
            f"{colordef.SAID['hue_angle']} (")
        refused = asked("/color-preview?set=isohue&method=xy&x=a&y=0.3")
        assert refused[:2] == (400, "application/json")
        assert refused[2]["x"] is None and "not a number" in refused[2]["said"]
        many = "&".join(f"f{n}=1" for n in range(17))
        assert asked(f"/color-preview?{many}") == (400, "application/json", {
            "x": None, "y": None, "srgb": None, "in_srgb": None,
            "said": "a color preview takes at most 16 fields"})
    finally:
        hub.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


# --- The record and the card ------------------------------------------------------------------

def test_a_sets_design_is_in_the_record_and_on_its_card(tmp_path, monkeypatch):
    """A set whose file has a design carries it: the run's start row writes it in `color_sets`, and
    its color card's `sets` give it, as the preview reads it."""
    written = card._hue_task

    def designed(folder, name="hues"):
        path = written(folder, name)
        path.write_text(path.read_text().replace(str(card.FIXTURE), str(DESIGNED)))
        return path

    monkeypatch.setattr(card, "_hue_task", designed)
    drained = card._Drained({})
    session = card._session(tmp_path, drained, trials=2)

    session.run()

    (start,) = [row for row in card._rows(session, "runs.jsonl") if row["event"] == "start"]
    assert start["color_sets"]["isohue"]["design"] == ISOHUE.design
    assert drained.cards[2]["distractor_appearance"][16]["sets"]["isohue"]["design"] == \
        ISOHUE.design
