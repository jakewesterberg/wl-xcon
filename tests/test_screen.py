"""The screen description (engine spec §3.3; build A1)."""

import math
from dataclasses import replace

import pytest

from _rig import DIRECT, RIG, STEREOSCOPE
from wl_xcon import exact, look, screen, viewport
from wl_xcon.photometry import D65, DKL, RMS, SRGB, ConeContrast, Gray, Michelson, Weber, cone_xyz, to_xyz, xyY
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


def _drift(direction, orientation, tf=2.0):
    looks = look.Look(shape=look.Circle(size=6.0),
                      fill=look.SineGrating(sf=1.0, tf=tf, direction=direction,
                                            contrast=Michelson(0.5)),
                      orientation=orientation)
    return _one(Stimulus("g", at=(0.0, 0.0), looks=looks)).items[0].fill.tf


@pytest.mark.parametrize("direction, orientation, signed", [
    (90.0, 0.0, 2.0), (270.0, 0.0, -2.0), (None, 0.0, 2.0), (120.0, 30.0, 2.0), (300.0, 30.0, -2.0),
])
def test_a_drift_direction_is_its_own_angle_and_the_drawer_reads_a_signed_speed(
        direction, orientation, signed):
    assert _drift(direction, orientation) == signed


def test_a_direction_not_across_the_bars_or_a_negative_speed_is_refused():
    with pytest.raises(ValueError, match="across the bars"):
        _drift(0.0, 0.0)
    with pytest.raises(ValueError, match="a speed"):
        _drift(None, 0.0, tf=-1.0)


def test_the_drawer_s_refusal_of_a_drift_names_every_direction_from_0_to_360():
    """The PI, 2026-10-30, "0 to 360 everywhere": at orientation 135 the drifts across the bars
    are 225 and 45, never 405, and a drift written -45 is named 315."""
    with pytest.raises(ValueError) as refused:
        _drift(-45.0, 135.0)
    assert str(refused.value) == ("a grating's drift direction 315 degrees is not across the bars: "
                                  "with orientation 135 it is 225 or 45")
    # Review 1's M1: one that prints as 360 at six significant figures reads 0.
    with pytest.raises(ValueError) as refused:
        _drift(0.0, 89.9999999)
    assert str(refused.value).endswith("it is 180 or 0")


def _seen(image, vp, x_deg):
    """The luminance of the pixel at (x°, 0°) in a direct-view image."""
    col = vp.width_px / 2 + (vp.distance_cm * math.tan(math.radians(x_deg)) + vp.ahead_cm[0]) / vp.pitch_cm[0]
    row = vp.height_px / 2 - vp.ahead_cm[1] / vp.pitch_cm[1]
    return image[int(row), int(col)][1]


@pytest.mark.parametrize("combine, inside, outside", [("window", 40.0, 0.0), ("scotoma", 0.0, 40.0)])
def test_a_window_or_a_scotoma_with_no_light_shows_or_hides_what_is_below(combine, inside, outside):
    """It draws none of its own light (call 3, XC-257): it resolves with none, and the drawer
    shows what is below only inside a window, and hides it inside a scotoma."""
    below = Stimulus("big", at=(0.0, 0.0), looks=Disc(size=6.0, color=Gray(40.0)))
    hole = Stimulus("h", at=(0.0, 0.0), looks=Disc(size=1.0), combine=combine, layer=1)
    s = screen.resolve({"big": below, "h": hole}, {}, TRIAL, DIRECT, frame_period=1 / 240)
    assert s.items[1].fill == screen.ResolvedFlat(xyz=None, weber=None)
    vp = viewport.viewports(RIG, DIRECT, pixels=(384, 216))[0]
    image = exact.draw(s, vp)
    assert (_seen(image, vp, 0.0), _seen(image, vp, 2.0)) == pytest.approx((inside, outside))


@pytest.mark.parametrize("combine", ["cover", "add", "multiply"])
def test_a_flat_fill_with_no_light_is_refused_unless_it_is_a_window_or_a_scotoma(combine):
    with pytest.raises(ValueError, match="no light"):
        _one(Stimulus("f", at=(0.0, 0.0), looks=Disc(size=1.0), combine=combine))


def test_a_window_s_or_a_scotoma_s_declared_light_is_not_read():
    """The checker holds it to no light rule, so `resolve` reads none it could refuse: a flat
    fill resolves to no light, a grating to its bars alone, and its edge to what shows through
    it, since there is no contrast for it to shape (call 5)."""
    for looks in (Disc(size=1.0, contrast=Michelson(0.5)), Disc(size=1.0, color=Gray(40.0))):
        item = _one(Stimulus("w", at=(0.0, 0.0), looks=looks, combine="window")).items[0]
        assert item.fill == screen.ResolvedFlat(xyz=None, weber=None)
    for looks in (Gabor(sigma=0.5), Gabor(sigma=0.5, contrast=Michelson(0.5))):
        item = _one(Stimulus("s", at=(0.0, 0.0), looks=looks, combine="scotoma")).items[0]
        assert item.fill == screen.ResolvedGrating(sf=2.0, phase=0.0, tf=0.0, michelson=None,
                                                   mean_xyz=None)
        assert item.edge == look.GaussianEdge(sigma=0.5, applies="opacity")


@pytest.mark.parametrize("fill, combine", [
    (look.Flat(color=Gray(40.0)), "cover"),
    (look.SineGrating(contrast=Michelson(0.5)), "window"),
    (look.SineGrating(contrast=Michelson(0.5)), "scotoma"),
    (look.Flat(), "window"),
])
def test_an_edge_that_applies_to_a_contrast_there_is_none_of_is_refused(fill, combine):
    """The checker refuses it at load (calls 2 and 5); `resolve` refuses it too rather than
    give it a meaning, as `_drift` holds the drift rule."""
    looks = look.Look(shape=look.Circle(size=2.0), fill=fill,
                      edge=look.GaussianEdge(sigma=0.5, applies="contrast"))
    with pytest.raises(ValueError, match="has no contrast of its own"):
        _one(Stimulus("e", at=(0.0, 0.0), looks=looks, combine=combine))
    covering = look.Look(shape=look.Circle(size=2.0), fill=look.SineGrating(contrast=Michelson(0.5)),
                         edge=look.GaussianEdge(sigma=0.5, applies="contrast"))
    assert _one(Stimulus("g", at=(0.0, 0.0), looks=covering)).items[0].edge.applies == "contrast"


# --- Cone colors, converted against the background (engine build A2) -------------------------

GRAY_TRIAL = replace(TRIAL, background=Gray(P("bg")))


def test_a_cone_color_resolves_to_its_light_against_the_background_through_the_calibration():
    stimulus = Stimulus("k", at=(0.0, 0.0), looks=Disc(color=DKL(l_m=P("c"))))

    item = screen.resolve({"k": stimulus}, {"bg": 40.0, "c": 0.08}, GRAY_TRIAL, DIRECT,
                          frame_period=1 / 240, calibration=SRGB).items[0]

    assert item.fill.xyz == cone_xyz(DKL(l_m=0.08), SRGB, xyY(*D65, 40.0))
    assert item.fill.xyz == pytest.approx((44.04969059, 40.0, 43.56231003), rel=1e-8)


def test_a_cone_colored_outline_and_a_grating_mean_resolve_the_same_way():
    looks = look.Look(fill=look.SineGrating(contrast=Michelson(0.3), mean=ConeContrast(S=0.5)),
                      outline=look.Outline(width=0.1, color=DKL(lum=0.2)))

    item = screen.resolve({"g": Stimulus("g", at=(0.0, 0.0), looks=looks)}, {"bg": 40.0},
                          GRAY_TRIAL, DIRECT, frame_period=1 / 240, calibration=SRGB).items[0]

    assert item.fill.mean_xyz == cone_xyz(ConeContrast(S=0.5), SRGB, xyY(*D65, 40.0))
    assert item.outline.xyz == pytest.approx(to_xyz(Gray(48.0)), rel=1e-12)


def test_a_cone_color_without_a_calibration_or_on_black_is_not_resolved():
    stimulus = Stimulus("k", at=(0.0, 0.0), looks=Disc(color=DKL(l_m=0.08)))

    with pytest.raises(ValueError, match="none was given"):
        screen.resolve({"k": stimulus}, {"bg": 40.0}, GRAY_TRIAL, DIRECT, frame_period=1 / 240)
    with pytest.raises(ValueError, match="background is black"):
        screen.resolve({"k": stimulus}, {}, TRIAL, DIRECT, frame_period=1 / 240, calibration=SRGB)


def test_a_cone_color_between_two_eyes_backgrounds_is_not_resolved():
    """`check` refuses it at load (`cone-color-two-backgrounds`); this is the backstop."""
    trial = replace(TRIAL, background_left=Gray(20.0), background_right=Gray(30.0))
    stimulus = Stimulus("k", at=(0.0, 0.0), looks=Disc(color=DKL(l_m=0.08)))

    with pytest.raises(ValueError, match="the two eyes' backgrounds differ"):
        screen.resolve({"k": stimulus}, {}, trial, STEREOSCOPE, frame_period=1 / 240,
                       calibration=SRGB)
    lit = Stimulus("g", at=(0.0, 0.0), looks=Disc(color=Gray(40.0)))
    s = screen.resolve({"g": lit}, {}, trial, STEREOSCOPE, frame_period=1 / 240)
    assert (s.background_left[1], s.background_right[1]) == (20.0, 30.0)


def test_two_equal_explicit_eye_backgrounds_are_one_background_for_a_cone_color():
    stimulus = Stimulus("k", at=(0.0, 0.0), looks=Disc(color=DKL(l_m=0.08)))
    split = replace(TRIAL, background_left=Gray(30.0), background_right=Gray(30.0))
    shared = replace(TRIAL, background=Gray(30.0))

    def fill(trial):
        return screen.resolve({"k": stimulus}, {}, trial, STEREOSCOPE, frame_period=1 / 240,
                              calibration=SRGB).items[0].fill.xyz

    assert fill(split) == fill(shared)


def test_a_named_grating_s_color_waits_for_the_pattern_fills():
    stimulus = Stimulus("g", at=(0.0, 0.0), looks=Gabor(contrast=Michelson(0.5), color=Gray(20.0)))

    with pytest.raises(screen.NotYetDrawable, match="engine build A3"):
        _one(stimulus)


# --- The wire (demo mode design §3.9) ---------------------------------------------------------

#: **A screen of every kind the drawer draws** (`exact.signed_distance`, `edge_profile`, `_light`):
#: each shape, a flat light absolute and as a contrast, a grating about a mean and about what is
#: behind it, each edge, an outline and none, a window, one eye's stimulus and a disparity, through
#: the stereoscope so each eye's direction differs.
_SHAPES = (
    look.Circle(size=1.0), look.Ellipse(width=2.0, height=1.0), look.Rect(width=1.0, height=2.0),
    look.Cross(size=0.5, thickness=0.1), look.RegularPolygon(sides=5, size=1.0),
    look.Vertices(points=((0.0, 0.0), (1.0, 0.0), (0.0, 1.0))), look.Ring(inner=1.0, outer=2.0),
    look.Path(points=((0.0, 0.0), (1.0, 1.0), (2.0, 0.0)), width=0.1), look.WholeScreen(),
)
_FILLS = (
    look.Flat(color=Gray(40.0)), look.Flat(contrast=Weber(0.5)),
    look.SineGrating(sf=2.0, phase=30.0, tf=1.0, contrast=Michelson(0.5), mean=Gray(20.0)),
    look.SineGrating(sf=3.0, contrast=Michelson(0.25)),
)
_EDGES = (look.Hard(), look.RaisedCosine(width=0.1), look.GaussianEdge(sigma=0.5))


def _every_kind() -> "screen.Screen":
    visible = {}
    for i, shape in enumerate(_SHAPES):
        fill = _FILLS[i % len(_FILLS)]
        edge = _EDGES[i % len(_EDGES)]
        if isinstance(edge, look.GaussianEdge) and isinstance(fill, look.Flat):
            edge = look.GaussianEdge(sigma=0.5, applies="opacity")
        visible[f"s{i}"] = Stimulus(
            f"s{i}", at=(float(i) - 4.0, 1.0),
            looks=look.Look(shape=shape, fill=fill, edge=edge, orientation=15.0 * i,
                            outline=look.Outline(width=0.05, color=Gray(60.0)) if i % 2 else None),
            layer=i % 3, disparity=0.1 * (i % 2), eye=("both", "left", "right")[i % 3],
            opacity=0.5 + 0.05 * i,
        )
    visible["hole"] = Stimulus("hole", at=(0.0, -3.0), looks=Disc(size=2.0), combine="window")
    trial = Trial(start="s", states=[], background=Gray(20.0))
    return screen.resolve(visible, {}, trial, STEREOSCOPE, frame_period=1 / 240, frame=9,
                          onsets={"s2": 4}, calibration=SRGB)


def _kinds(data) -> set:
    if isinstance(data, list):
        return set().union(*map(_kinds, data)) if data else set()
    if isinstance(data, dict):
        return {data[screen.KIND]}.union(*map(_kinds, data.values()))
    return set()


def test_screen_to_wire_and_back_is_equal_for_each_kind_the_drawer_draws():
    """Demo mode §3.9: a demo's `Screen` crosses a process boundary, the first to, in `Drawn`;
    `wlx serve` draws it with the exact drawer. **Whole and equal**: every block back as its own
    class, every tuple a tuple, every number the number sent, through msgpack as the link packs it;
    and the screen carries every kind the drawer draws, so none is left untested here."""
    import msgpack

    sent = _every_kind()
    wire = screen.to_wire(sent)
    back = screen.from_wire(msgpack.unpackb(msgpack.packb(wire, use_bin_type=True), raw=False))

    assert back == sent
    assert type(back.items[0].at_left) is tuple and type(back.items[0].order) is tuple
    drawn = {type(item.shape) for item in sent.items} | {type(item.fill) for item in sent.items}
    drawn |= {type(item.edge) for item in sent.items}
    drawn |= {type(item.outline) for item in sent.items if item.outline is not None}
    every = {look.Circle, look.Ellipse, look.Rect, look.Cross, look.RegularPolygon, look.Vertices,
             look.Ring, look.Path, look.WholeScreen, screen.ResolvedFlat, screen.ResolvedGrating,
             look.Hard, look.RaisedCosine, look.GaussianEdge, screen.ResolvedOutline}
    assert drawn == every
    assert _kinds(wire) == {kind.__name__ for kind in every} | {"Item", "Screen"}
    assert any(item.fill.weber is not None for item in sent.items
               if isinstance(item.fill, screen.ResolvedFlat))
    assert any(item.fill.mean_xyz is None for item in sent.items
               if isinstance(item.fill, screen.ResolvedGrating))
    assert any(item.at_left != item.at_right for item in sent.items)
    for vp in viewport.viewports(RIG, STEREOSCOPE, pixels=(64, 24)):
        assert (exact.draw(back, vp, supersample=1) == exact.draw(sent, vp, supersample=1)).all()


def test_every_block_a_screen_is_made_of_crosses_the_wire_and_nothing_else():
    """The wire's list is closed: `look`'s shapes, fills, edges and outline, the resolved fills and
    outline, `Item` and `Screen`, every one of them -- a block added to `look` without joining it
    fails here -- and nothing a peer names besides. A kind not on it, a block with a field missing
    or one too many, a `Screen` of another schema and anything that is no screen are refused."""
    def every(base) -> set:
        # The module's own classes only: `dataclass(slots=True)` makes a new class, and the one it
        # replaced may still be listed among the base's subclasses until it is collected.
        found = set()
        for kind in base.__subclasses__():
            if getattr(look, kind.__name__, None) is kind:
                found |= {kind} | every(kind)
        return found

    expected = (every(look.Shape) | every(look.Fill) | every(look.Edge)
                | {look.Outline, screen.ResolvedFlat, screen.ResolvedGrating,
                   screen.ResolvedOutline, screen.Item, screen.Screen})
    assert set(screen.WIRE_KINDS) == expected
    assert len({kind.__name__ for kind in screen.WIRE_KINDS}) == len(screen.WIRE_KINDS)

    wire = screen.to_wire(_one(Stimulus("fix", at=(0.0, 0.0), looks=Disc(color=Gray(40.0)))))

    def changed(**at_the_shape) -> dict:
        data = {**wire, "items": [{**wire["items"][0], "shape": {**wire["items"][0]["shape"]}}]}
        data["items"][0]["shape"].update(at_the_shape)
        return data

    for data, said in (
        (changed(kind="Disc"), "'Disc' is no kind a screen description is made of"),
        (changed(kind="os.system"), "'os.system' is no kind"),
        (changed(kind=None), "None is no kind"),
        (changed(radius=1.0), "a Circle carries size, and this one carries size, radius"),
        ({k: v for k, v in wire.items() if k != "frame"}, "a Screen carries"),
        ({**wire, "schema": screen.SCHEMA + 1}, "schema 2 arrived, and this build reads schema 1"),
        (wire["items"][0], "a screen description on the wire is a Screen, not Item"),
        ({**wire, "frame": {1, 2}}, "is no part of a screen description"),
    ):
        with pytest.raises(ValueError, match=said):
            screen.from_wire(data)
    unwired = _one(Stimulus("fix", at=(0.0, 0.0), looks=Disc(color=Gray(40.0))))
    item = replace(unwired.items[0], shape=Disc(size=1.0))
    with pytest.raises(ValueError, match="is no part of a screen description, so it cannot cross"):
        screen.to_wire(replace(unwired, items=(item,)))
    with pytest.raises(ValueError, match="a screen description on the wire is a Screen"):
        screen.to_wire(unwired.items[0])


def test_a_scaled_array_draws_each_object_at_its_own_eccentricity():
    """The console settings design's §5 ("Size = factor x eccentricity", the PI, 2026-11-16): a size
    a person scales is bound where a fixed size is, at each item's own cyclopean place, its true
    eccentricity from straight ahead (`task.size_at`, `geometry.polar_of_deg`), never an average:
    an array about (4°, 0°) of radius 4° puts its objects 8°, 5.65° (twice) and 0° out, so they are
    drawn 2.4°, 1.70° and 0° across, each its own, where a fixed size draws all four alike."""
    from wl_xcon.geometry import polar_of_deg
    from wl_xcon.task import Scaled

    disc = Disc(size=P("disc_size"), color=Gray(40.0))
    ring = Stimulus("search", at=(4.0, 0.0), looks=Array(n=4, radius=4.0, looks=disc, among=disc))
    scaled = _one(ring, geometry=DIRECT, values={"disc_size": Scaled(0.3)}).items
    assert len(scaled) == 4
    for item in scaled:
        assert item.at_left == item.at_right
        assert item.shape.size == pytest.approx(0.3 * polar_of_deg(*item.at_left)[0], abs=1e-12)
    assert scaled[0].shape.size == pytest.approx(2.4, abs=1e-12)
    assert len({round(item.shape.size, 9) for item in scaled}) == 3
    fixed = _one(ring, geometry=DIRECT, values={"disc_size": 1.0}).items
    assert [item.shape.size for item in fixed] == [1.0] * 4
    square = Stimulus("s", at=(6.0, 6.0), looks=Square(size=P("disc_size"), color=Gray(40.0)))
    (item,) = _one(square, geometry=DIRECT, values={"disc_size": Scaled(0.3)}).items
    assert (item.shape.width, item.shape.height) == pytest.approx(
        (0.3 * polar_of_deg(6.0, 6.0)[0],) * 2, abs=1e-12)
