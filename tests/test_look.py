"""The building blocks of what can be shown (engine spec §4.1-4.2; build A1)."""

import dataclasses

from wl_xcon import look, task
from wl_xcon.photometry import Gray, Michelson
from wl_xcon.task import COMBINE, PERIPHERY, Appearance, Stimulus, Trial, Update


def test_a_look_is_an_appearance_a_stimulus_can_carry():
    gabor = look.Look(
        shape=look.Circle(size=4.0),
        fill=look.SineGrating(sf=2.0, contrast=Michelson(0.8)),
        edge=look.GaussianEdge(sigma=0.5),
        orientation=30.0,
    )
    assert isinstance(gabor, Appearance)
    assert Stimulus("g", at=(5.0, 0.0), looks=gabor).looks.orientation == 30.0


def test_an_edge_applies_by_default_as_its_fill_needs():
    # None: a contrast envelope on a pattern, an opacity ramp on a flat light (spec §4.2).
    assert (look.Hard().applies, look.RaisedCosine().applies, look.GaussianEdge().applies) == (
        None, None, None)
    assert look.EDGE_APPLIES == ("opacity", "contrast")


def test_the_new_placement_fields_default_to_an_ordinary_stimulus():
    s = Stimulus("fix", at=(0.0, 0.0))
    assert (s.layer, s.combine, s.opacity, s.at_left, s.at_right) == (0, "cover", 1.0, None, None)
    assert COMBINE == ("cover", "add", "window", "scotoma", "multiply")
    assert PERIPHERY == ("true_angle", "center_scale")


def test_an_update_lists_the_new_fields_it_sets_and_nothing_else():
    assert Update("fix", opacity=0.5, layer=2).changes() == {"opacity": 0.5, "layer": 2}
    assert Update("fix", at_left=(1.0, 0.0), at_right=(-1.0, 0.0)).changes() == {
        "at_left": (1.0, 0.0), "at_right": (-1.0, 0.0)}


def test_a_trial_defaults_to_black_and_true_angle():
    t = Trial(start="s", states=[])
    assert (t.background, t.background_left, t.background_right, t.periphery) == (
        None, None, None, "true_angle")
    assert Trial(start="s", states=[], background=Gray(20.0)).background == Gray(20.0)


def test_no_appearance_implies_a_contrast_any_more():
    for name in ("Disc", "Square", "Bar", "Gabor", "Annulus", "Cross", "Polygon", "Grating",
                 "Plaid", "Checkerboard", "Noise", "RDS"):
        fields = {f.name: f for f in dataclasses.fields(getattr(task, name))}
        assert fields["contrast"].default is None, name


def test_a_grating_drifts_toward_its_orientation_plus_90_unless_a_direction_says_otherwise():
    assert look.SineGrating().direction is None  # spec §5.1; PI, 2026-10-07: "Its own angle"
