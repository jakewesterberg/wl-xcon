"""The screen description (engine spec §3.3; build A1)."""

import pytest

from _rig import DIRECT, STEREOSCOPE
from wl_xcon import look, screen
from wl_xcon.photometry import RMS, Gray, Michelson, Weber, to_xyz
from wl_xcon.task import Array, Bar, Blank, Disc, Gabor, Noise, P, Square, Stimulus, Trial

TRIAL = Trial(start="s", states=[])
V = STEREOSCOPE.vergence_half_deg


def _one(stimulus, trial=TRIAL, geometry=STEREOSCOPE, values=None):
    return screen.resolve({stimulus.name: stimulus}, values or {}, trial, geometry,
                          frame_period=1 / 240)


def test_a_disc_is_a_circle_with_a_flat_light_its_parameters_bound():
    item = _one(Stimulus("fix", at=(0.0, 0.0), looks=Disc(size=0.3, color=Gray(P("lum")))),
                values={"lum": 40.0}).items[0]
    assert isinstance(item.shape, look.Circle) and item.shape.size == 0.3
    assert item.fill == screen.ResolvedFlat(xyz=to_xyz(Gray(40.0)), weber=None)
    assert item.edge == look.Hard(applies="opacity")


def test_a_bar_is_a_rectangle_long_along_its_orientation():
    item = _one(Stimulus("b", at=(0.0, 0.0),
                         looks=Bar(length=4.0, width=0.5, orientation=30.0, color=Gray(40.0)))).items[0]
    assert (item.shape.width, item.shape.height, item.orientation) == (4.0, 0.5, 30.0)


def test_a_gabor_is_a_grating_in_a_gaussian_envelope_cut_at_four_sigma():
    item = _one(Stimulus("g", at=(5.0, 0.0),
                         looks=Gabor(sf=2.0, sigma=0.5, contrast=Michelson(0.8)))).items[0]
    assert isinstance(item.fill, screen.ResolvedGrating) and item.fill.michelson == 0.8
    assert item.edge == look.GaussianEdge(sigma=0.5, applies="contrast")
    assert item.shape.size == 2 * look.GABOR_CUTOFF_SIGMAS * 0.5


def test_each_eye_s_direction_is_disparity_then_the_vergence_offset():
    item = _one(Stimulus("d", at=(1.0, 2.0), looks=Disc(color=Gray(40.0)), disparity=-0.2)).items[0]
    assert item.at_left == pytest.approx((1.0 + 0.1 + V, 2.0))
    assert item.at_right == pytest.approx((1.0 - 0.1 - V, 2.0))


def test_direct_view_has_one_direction_for_both_eyes():
    item = _one(Stimulus("d", at=(1.0, 2.0), looks=Disc(color=Gray(40.0))), geometry=DIRECT).items[0]
    assert item.at_left == item.at_right == (1.0, 2.0)


def test_per_eye_positions_are_taken_as_given():
    item = _one(Stimulus("r", at=(0.0, 0.0), looks=Disc(color=Gray(40.0)),
                         at_left=(2.0, 0.0), at_right=(-2.0, 1.0))).items[0]
    assert (item.at_left, item.at_right) == ((2.0, 0.0), (-2.0, 1.0))


def test_an_array_is_its_items_named_like_their_windows():
    array = Array(n=4, radius=8.0, target=1, looks=Disc(color=Gray(40.0)),
                  among=Square(color=Gray(40.0)))
    items = _one(Stimulus("search", at=(0.0, 0.0), looks=array), geometry=DIRECT).items
    assert [i.name for i in items] == ["search.0", "search.1", "search.2", "search.3"]
    assert isinstance(items[1].shape, look.Circle) and isinstance(items[0].shape, look.Rect)
    assert items[0].at_left == pytest.approx((8.0, 0.0)) and items[1].at_left == pytest.approx((0.0, 8.0))


def test_items_sort_by_layer_then_by_the_order_shown():
    visible = {"a": Stimulus("a", at=(0.0, 0.0), looks=Disc(color=Gray(1.0)), layer=1),
               "b": Stimulus("b", at=(0.0, 0.0), looks=Disc(color=Gray(2.0))),
               "c": Stimulus("c", at=(0.0, 0.0), looks=Disc(color=Gray(3.0)))}
    s = screen.resolve(visible, {}, TRIAL, STEREOSCOPE, frame_period=1 / 240)
    assert [i.name for i in s.items] == ["b", "c", "a"]


def test_the_background_is_black_unless_declared_and_may_differ_per_eye():
    assert _one(Stimulus("x", at=(0.0, 0.0), looks=Disc(color=Gray(1.0)))).background_left == (0.0, 0.0, 0.0)
    t = Trial(start="s", states=[], background=Gray(20.0), background_right=Gray(10.0))
    s = _one(Stimulus("x", at=(0.0, 0.0), looks=Disc(contrast=Weber(0.5))), trial=t)
    assert (s.background_left, s.background_right) == (to_xyz(Gray(20.0)), to_xyz(Gray(10.0)))
    assert s.items[0].fill == screen.ResolvedFlat(xyz=None, weber=0.5)


def test_an_unbound_parameter_is_an_error_that_names_it():
    with pytest.raises(KeyError, match="lum"):
        _one(Stimulus("fix", at=(0.0, 0.0), looks=Disc(color=Gray(P("lum")))))


def test_what_a_later_build_draws_says_which_build():
    with pytest.raises(screen.NotYetDrawable, match="A3"):
        _one(Stimulus("n", at=(0.0, 0.0), looks=Noise()))


def test_a_blank_draws_nothing_and_the_description_carries_its_frame():
    s = screen.resolve({"x": Stimulus("x", at=(0.0, 0.0), looks=Blank())}, {}, TRIAL, STEREOSCOPE,
                       frame_period=1 / 240, frame=7, onsets={"x": 3})
    assert (s.items, s.frame, s.frame_period, s.setup, s.schema) == ((), 7, 1 / 240, "stereoscope", 1)


def test_an_onset_frame_is_the_stimulus_s_first_frame_and_zero_without_one():
    x = Stimulus("x", at=(0.0, 0.0), looks=Disc(color=Gray(40.0)))
    with_onset = screen.resolve({"x": x}, {}, TRIAL, STEREOSCOPE, frame_period=1 / 240,
                                onsets={"x": 3})
    assert with_onset.items[0].onset_frame == 3
    assert _one(x).items[0].onset_frame == 0


def test_an_outline_is_resolved_to_a_width_and_a_light():
    looks = look.Look(outline=look.Outline(width=P("w"), color=Gray(40.0)),
                      fill=look.Flat(color=Gray(40.0)))
    item = _one(Stimulus("o", at=(0.0, 0.0), looks=looks), values={"w": 0.2}).items[0]
    assert item.outline == screen.ResolvedOutline(width=0.2, xyz=to_xyz(Gray(40.0)))


def test_a_grating_look_resolves_every_field_and_its_orientation():
    looks = look.Look(fill=look.SineGrating(sf=P("sf"), phase=90.0, tf=2.0,
                                            contrast=Michelson(0.5), mean=Gray(10.0)),
                      orientation=P("o"))
    item = _one(Stimulus("g", at=(0.0, 0.0), looks=looks), values={"sf": 3.0, "o": 45.0}).items[0]
    assert item.fill == screen.ResolvedGrating(sf=3.0, phase=90.0, tf=2.0, michelson=0.5,
                                               mean_xyz=to_xyz(Gray(10.0)))
    assert item.orientation == 45.0


def test_a_fill_that_cannot_be_drawn_is_refused():
    with pytest.raises(ValueError, match="no light"):
        _one(Stimulus("f", at=(0.0, 0.0), looks=look.Look(fill=look.Flat())))
    with pytest.raises(ValueError, match="no contrast"):
        _one(Stimulus("g", at=(0.0, 0.0), looks=look.Look(fill=look.SineGrating())))


def test_a_flat_light_in_a_pattern_s_convention_is_refused_as_never_drawable():
    # A flat light takes a color or a Weber contrast, in every build.
    with pytest.raises(ValueError, match="color or a Weber") as refused:
        _one(Stimulus("m", at=(0.0, 0.0), looks=Disc(contrast=Michelson(0.5))))
    assert not isinstance(refused.value, screen.NotYetDrawable)


def test_a_grating_s_rms_contrast_names_the_build_that_draws_it():
    with pytest.raises(screen.NotYetDrawable, match="A3"):
        _one(Stimulus("g", at=(0.0, 0.0), looks=Gabor(contrast=RMS(0.2))))


def test_an_outline_that_resolves_to_no_light_is_refused():
    looks = look.Look(fill=look.Flat(color=Gray(40.0)), outline=look.Outline(width=0.2, color=P("oc")))
    with pytest.raises(ValueError, match="outline"):
        _one(Stimulus("o", at=(0.0, 0.0), looks=looks), values={"oc": None})


def test_direct_view_refuses_what_only_the_stereoscope_shows():
    with pytest.raises(ValueError, match="disparity"):
        _one(Stimulus("d", at=(0.0, 0.0), looks=Disc(color=Gray(40.0)), disparity=0.2),
             geometry=DIRECT)
    with pytest.raises(ValueError, match="per-eye"):
        _one(Stimulus("r", at=(0.0, 0.0), looks=Disc(color=Gray(40.0)),
                      at_left=(2.0, 0.0), at_right=(-2.0, 0.0)), geometry=DIRECT)
    with pytest.raises(ValueError, match="left eye"):
        _one(Stimulus("l", at=(0.0, 0.0), looks=Disc(color=Gray(40.0)), eye="left"), geometry=DIRECT)


def test_an_array_whose_appearance_is_a_parameter_is_bound_before_it_is_drawn():
    array = Array(n=2, radius=8.0, target=0, looks=P("target"), among=Square(color=Gray(40.0)))
    items = _one(Stimulus("s", at=(0.0, 0.0), looks=array), geometry=DIRECT,
                 values={"target": Disc(size=0.7, color=Gray(40.0))}).items
    assert isinstance(items[0].shape, look.Circle) and items[0].shape.size == 0.7
    assert isinstance(items[1].shape, look.Rect)


def test_a_left_eye_background_overrides_the_shared_one_for_that_eye_only():
    t = Trial(start="s", states=[], background=Gray(20.0), background_left=Gray(5.0))
    s = _one(Stimulus("x", at=(0.0, 0.0), looks=Disc(color=Gray(1.0))), trial=t)
    assert (s.background_left, s.background_right) == (to_xyz(Gray(5.0)), to_xyz(Gray(20.0)))
