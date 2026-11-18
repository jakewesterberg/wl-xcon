"""The card's histogram and hazard for a drawn setting (the console settings design's §3; the PI,
2026-11-16): the declared distribution's density as bars, and its hazard against flat. Arithmetic of
the declared distribution, never a measurement of the rig, so every number here is derived from the
distribution or from the report's own figures (`.superpowers/side-2026-11-17/nonaging-decay-report.md`).
"""

from __future__ import annotations

import math

import pytest

import test_forms as forms
from wl_xcon import variation
from wl_xcon.task import FRESH, Listed, NonAging, Param, TruncatedNormal, Uniform, Weighted


def _bin_holding(profile, share: float) -> int:
    """The bin of a continuous profile holding `share` of the way through its range."""
    low, high = profile.edges[0], profile.edges[-1]
    at = low + share * (high - low)
    for place in range(len(profile.density)):
        if profile.edges[place] <= at < profile.edges[place + 1]:
            return place
    return len(profile.density) - 1


def test_the_pis_foreperiods_profile_has_the_reports_figures():
    """The decay report's table for 750 to 1250 ms, decay a third of the range: the hazard in the
    bins holding 1/4, 1/2, 2/3 and 9/10 of the range, as a multiple of the first bin's, is 1.06,
    1.22, 1.50 and 3.67 -- and the density, a share of draws each, sums to 1."""
    shape = variation.profile(NonAging.between(0.75, 1.25))

    assert len(shape.density) == variation.PROFILE_BINS == 20
    assert len(shape.edges) == 21 and shape.edges[0] == 0.75 and shape.edges[-1] == 1.25
    assert sum(shape.density) == pytest.approx(1.0, abs=1e-12)
    assert shape.hazard[0] == 1.0
    for share, figure in ((1 / 4, 1.06), (1 / 2, 1.22), (2 / 3, 1.50), (9 / 10, 3.67)):
        assert shape.hazard[_bin_holding(shape, share)] == pytest.approx(figure, abs=0.05), share
    # More draws land early than late: a wait that ends at a constant rate, cut at the longest.
    assert shape.density[0] > shape.density[-1] > 0


def test_a_uniforms_hazard_rises_to_its_end():
    """A uniform's chance of ending in a bin, given it has not, rises to 1 in the last: 20 times
    the first bin's, over 5."""
    shape = variation.profile(Uniform(0.2, 0.6))

    assert shape.density == pytest.approx((0.05,) * 20)
    assert all(later > earlier for earlier, later in zip(shape.hazard, shape.hazard[1:]))
    assert shape.hazard[-1] > 5
    assert shape.hazard[-1] == pytest.approx(20.0)


def test_a_cut_normal_is_cut_as_bounds_of_cuts_it():
    """A normal's bins span its cut (its own, else its setting's declared range); its density sums
    to 1 and peaks at the mean."""
    normal = TruncatedNormal(0.5, 0.1, low=0.3)
    declared = Param("wait", "s", 0.0, 0.9, 0.5, True)

    shape = variation.profile(normal, declared)

    assert (shape.edges[0], shape.edges[-1]) == variation.bounds_of(normal, declared) == (0.3, 0.9)
    assert sum(shape.density) == pytest.approx(1.0)
    top = shape.density.index(max(shape.density))
    assert shape.edges[top] <= 0.5 < shape.edges[top + 1], "the peak is the bin holding the mean"
    assert shape.density[0] > shape.density[-1] > 0, "its cut is 2 spreads below the mean, 4 above"


def test_a_lists_profile_is_one_bar_a_value():
    """A list or a weighted set has a bar for each value, in order; its hazard is discrete,
    P(v) / P(>= v), against the first value's."""
    listed = variation.profile(Listed((0.9, 0.3, 0.5, 0.3)))
    assert listed.edges == (0.3, 0.5, 0.9)
    assert listed.density == pytest.approx((0.5, 0.25, 0.25))
    first = 0.5 / 1.0
    assert listed.hazard == pytest.approx((1.0, (0.25 / 0.5) / first, (0.25 / 0.25) / first))

    weighted = variation.profile(Weighted((1.0, 2.0, 3.0), (3.0, 1.0, 0.0)))
    assert weighted.edges == (1.0, 2.0), "a weight of 0 is never drawn"
    assert weighted.density == pytest.approx((0.75, 0.25))
    assert weighted.hazard == pytest.approx((1.0, 1.0 / 0.75))
    assert len(variation.profile(Listed((0.4,))).density) == 1


def test_a_profile_is_computed_once_a_distribution(monkeypatch):
    """`parameters` runs between frames and asks every drawn card each time: equal distributions
    share one computation, a different one makes its own."""
    calls = []
    real = variation._build
    monkeypatch.setattr(variation, "_build", lambda *key: calls.append(key) or real(*key))
    first = NonAging.between(0.7111, 1.3111, repeat=FRESH)

    one = variation.profile(first)
    again = variation.profile(NonAging.between(0.7111, 1.3111, repeat=FRESH))
    variation.profile(Uniform(0.7111, 1.3111))
    variation.profile(Uniform(0.7111, 1.3111))
    variation.profile(Listed((0.7111, 0.8111)))
    variation.profile(Listed([0.7111, 0.8111]))

    assert again is one
    assert len(calls) == 3, f"{len(calls)} computations for 3 distributions"


def test_a_degenerate_distribution_is_one_bar_and_never_raises():
    """A range of no width gives one bar of all the draws; a distribution the load would refuse
    never raises between trials."""
    for shape in (variation.profile(Uniform(0.5, 0.5)), variation.profile(Listed(())),
                  variation.profile(Weighted((1.0,), (0.0,)))):
        assert len(shape.density) == len(shape.hazard) and sum(shape.density) in (0, 1.0)
    for broken in (TruncatedNormal(0.5, 0.0), NonAging(0.5, 0.5, 1.0), Uniform(math.nan, 1.0)):
        assert variation.profile(broken).density in ((), (1.0,)), broken
    one = variation.profile(Uniform(0.5, 0.5))
    assert (one.edges, one.density, one.hazard) == ((0.5,), (1.0,), (1.0,))


def test_a_session_gives_a_drawn_card_its_profile_computed_once(tmp_path, monkeypatch):
    """Through `Session.parameters`: a person's draw's card carries the profile of that draw, a
    fixed card none, and the cards computed again each drain ask the cache."""
    calls = []
    real = variation._build
    monkeypatch.setattr(variation, "_build", lambda *key: calls.append(key) or real(*key))
    link = forms._Drained({2: [forms._form(numbers={"shortest": 0.7123, "longest": 1.3123})]})
    session = forms._session(forms._plain(tmp_path, trials=8), link)

    session.run()

    cards = [rows["fix_hold"] for rows, _, _ in link.seen.values()]
    drawn = [row for row in cards if row[11] == "drawn" and row[12] is not None]
    assert drawn, "no card was drawn"
    expected = variation.profile(NonAging.between(0.7123, 1.3123, repeat=FRESH)).as_dict()
    assert all(row[13] == expected for row in drawn)
    assert all(row[13] is None for row in cards if row[12] is None)
    assert len(calls) == 1, f"{len(calls)} computations across {len(drawn)} drawn cards"


def test_a_persons_draw_is_profiled_over_the_blocks_and_the_blocks_again_once_handed_back(tmp_path):
    """A block that draws `fix_hold` from a uniform shows that draw's profile; a person's non-aging
    draw over it shows the person's, never the block's; handed back, the block's again."""
    path = forms._sessions.varied_task(
        tmp_path, plans='{"p": Plan([Block("b", [Condition("c", {}, target=8)], '
                        'draws={"fix_hold": Uniform(0.2, 0.4, repeat=FRESH)})])}', name="profiled")
    link = forms._Drained({2: [forms._form()], 5: [forms.HandBack(name="fix_hold", by=forms.JAKE)]})
    session = forms._session(forms._spec(tmp_path, path, plan="p", trials=8), link)

    session.run()

    block = variation.profile(Uniform(0.2, 0.4, repeat=FRESH)).as_dict()
    person = variation.profile(forms.WAIT).as_dict()
    seen = {drain: rows["fix_hold"] for drain, (rows, _, _) in link.seen.items()}
    assert seen[1][13] == block and seen[1][12]["by"] == "block"
    assert seen[4][13] == person and seen[4][12]["by"] == "person"
    assert seen[7][13] == block
