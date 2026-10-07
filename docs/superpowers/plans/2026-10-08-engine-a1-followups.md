# Engine A1 follow-ups: the defects A1's reviews filed — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the engineering defects engine build A1's reviews filed in `docs/backlog.md` (XC-245, XC-247 to XC-250, XC-252 to XC-257, XC-259 to XC-261, XC-263 to XC-268), so that what the load-time checker accepts is what `screen.resolve` and `exact.draw` honor, nothing is ignored without a word, and the drawer's last untested corners are pinned.

**Architecture:** No new module. `wl_xcon/check.py` gains refusals and loses two over-refusals; `wl_xcon/screen.py` lets a window or a scotoma carry no light; `wl_xcon/exact.py` gets the cross's exact distance and one modulation helper; `wl_xcon/review.py`'s stimuli table shows what a stimulus is drawn with. Each item closes its backlog line in the commit that does it ("closes XC-nnn").

**Tech Stack:** Python 3.11-3.13, numpy, pytest. No new dependency.

**Spec:** `docs/superpowers/specs/2026-10-07-engine-design.md` (approved 2026-10-07); A1's plan `docs/superpowers/plans/2026-10-07-engine-a1.md` (its Global Constraints and Review Focus 5: "degenerate values are refused at load, never met first by the drawer").

**Authority:** the PI asked on 2026-10-07 for work to continue overnight; these are defects in A1's own code, each already filed, none science-facing. Left out on purpose: XC-243, XC-244, XC-251 (wait on builds), XC-246 (needs path analysis; a conservative refusal, not a wrong drawing), XC-258 (how a trial changes its background is a design question for A3/C), XC-262 (a question for the PI).

### Calls taken in this plan (each cheap to undo)

1. **A multiplying grating's declared mean is refused at load** (XC-253): under multiply only its modulation counts, and an ignored value is a silent lie. Cost if wrong: a warning instead.
2. **A flat light whose edge says `applies="contrast"` is refused at load** (XC-249) rather than given a meaning: for one light, fading its contrast and fading its opacity are the same over the background and different over another stimulus, and nothing asks for the second. Cost if wrong: one definition in `exact.py`.
3. **A window or a scotoma needs no light** (XC-257): they show or hide what is below and never draw their fill, so the checker stops asking for one and `resolve` accepts a light-less flat fill on them.
4. **The cross's distance is the exact one** (XC-248), the standard closed form for a plus shape (two bars of half-length `size/2` and half-thickness `thickness/2`), so ramps and outlines are the same width at its re-entrant corners as on its arms; decided now, before the GPU drawer is matched against it (spec §10.1).

## Global Constraints

- US English; match the surrounding code's comment density and idiom; a "not yet" comment names what it waits for (CLAUDE.md).
- No welfare-critical code is touched (architecture.md's list); `run.py` is untouched.
- Every new refusal is proven able to fail, and every behavior change has a test that fails without it (break, see it fail as an assertion, restore with `cmp`, clear `__pycache__`).
- The suite: `WLX_REQUIRE_PREPROC=1 WLX_REQUIRE_BROWSER=1 PYTHONDONTWRITEBYTECODE=1 .superpowers/venv/bin/python -m pytest -q -p no:cacheprovider -W error::RuntimeWarning` — green before each commit.
- Each commit that fixes a backlog item removes that item's line from `docs/backlog.md` and says "closes XC-nnn" in its message (CLAUDE.md: closing one removes its line in the commit that does the work).
- No change to an existing finding's code name; new refusals reuse `bad-block` (a value no block can hold), `bad-placement` (how a stimulus is placed or combined) or `per-eye-misused`.

---

### Task 1: Values of the wrong kind, and parameters that refer to themselves

**Files:** `wl_xcon/check.py`, `wl_xcon/photometry.py`; tests in `tests/test_display_checks.py`, `tests/test_color.py`.

**Behavior:**
1. **XC-245.** In any block or named kind, a field that holds a number (`size`, `width`, `height`, `length`, `thickness`, `inner`, `outer`, `sigma`, `aperture`, `sides`, `sf`, `phase`, `tf`, `direction`, `orientation`, a contrast's `value`, a `Gray`'s `cd_m2`, a stimulus's `opacity`) and holds neither a number nor a parameter is refused: `bad-block` "… is <repr>, not a number" (`bad-placement` for opacity). A `bool` is not a number here.
2. **XC-264.** A color field (`color`, a grating's `mean`, an outline's `color`, the trial's backgrounds) that holds neither a `Color`, `None` nor a parameter — or a parameter whose choices include something that is not a `Color` or `None` — is refused: `bad-block` "… is <repr>, not a color".
3. **XC-265.** A `Show` (or `Update`) whose `looks` is a parameter with no choices is refused: `bad-block` "its appearance is parameter <name>, which offers no appearances as choices".
4. **XC-267.** A literal `Vertices` whose points enclose no area (shoelace area below 1e-12 square degrees, e.g. collinear) is refused: `bad-block` "encloses no area".
5. **XC-263.** A parameter whose choices contain itself, directly or through other parameters, is refused instead of recursing: `_parts`, `_modulates`, `_black` (and any other walk that follows a parameter's choices) carry the names they are inside and refuse a revisit as `bad-block` "parameter <name> refers to itself". `check()` must return findings, never raise RecursionError.
6. **XC-255.** `photometry.to_xyz` given a `Gray` whose `cd_m2` is a parameter raises `TypeError` saying the parameter must be bound first (`screen.resolve` binds it), instead of `float()`'s message.

**Tests** (each asserts the code is in the blocking findings, or the exception type and message): `Circle(size="big")` in a `Look`; `Gabor(sf="2")`; `Disc(color=10.0)` and `Disc(color=P("c"))` with choices `(10.0, 20.0)`; `Show(Stimulus("s", at=…, looks=P("l")))` with `Param("l", unit="appearance", low=0, high=1)`; `Vertices(points=((0,0),(1,1),(2,2)))`; a parameter `P("a")` whose choices are `(Disc(color=Gray(P("a"))),)` — check returns a `bad-block` naming it and does not raise; `to_xyz(Gray(P("x")))` raises `TypeError` matching "bind". A legitimate `Gray(P("lum"))` with a range and a `Disc(color=P("c"))` whose choices are colors still load (regression guard).

**Closes:** XC-245, XC-255, XC-263, XC-264, XC-265, XC-267.

---

### Task 2: Colors with parameters inside, under a calibration

**Files:** `wl_xcon/check.py`; tests in `tests/test_color.py`, `tests/test_display_checks.py`.

**Behavior:**
1. **XC-261.** With a calibration, an `xyY` some of whose `x`, `y`, `Y` are parameters — written directly, or as a choice of a color parameter — is checked for realizability at every combination of the values its parameters can take (each choice, or both ends of a range: `_reach`), like a literal; a component parameter that offers neither is refused (`bad-block` "cannot be bounded"). Without a calibration it stays `uncalibrated-color`, as a literal `xyY` does. `check()` never raises TypeError here.
2. **XC-266.** An `xyY` background (trial, left or right) whose `Y` is a parameter that can reach 0 counts as black, as a `Gray` parameter does (for `weber-on-black` and a grating's `unlit`).

**Tests:** with the tests' `PANEL` calibration: `Disc(color=xyY(0.64, 0.33, P("Y")))` with `Param("Y", low=0, high=10)` loads (no `unrealizable-color`), with `high=900` is refused `unrealizable-color`, and with no range is refused `bad-block`; the same through `Disc(color=P("c"))` whose choice is that `xyY`; `check()` does not raise for any of them. A Weber disc on `background=xyY(0.3127, 0.329, P("bg"))` with `Param("bg", low=0, high=40)` is refused `weber-on-black`, and with `low=5` is not.

**Closes:** XC-261, XC-266.

---

### Task 3: What each way of combining needs from a stimulus's light

**Files:** `wl_xcon/check.py`, `wl_xcon/screen.py`; tests in `tests/test_display_checks.py`, `tests/test_screen.py`, `tests/test_engine_path.py`.

**Behavior:**
1. **XC-257 (call 3).** An appearance shown only by stimuli whose `combine` is `"window"` or `"scotoma"` is not held to the light rules (`unlit`, `weber-on-black`, `contrast-convention`, `overspecified-color`); the degenerate-value rules still apply (its shape must still be a shape). `screen.resolve` accepts a flat fill with neither color nor contrast on a window or scotoma item (a `ResolvedFlat(xyz=None, weber=None)`), and still raises for one on any other combination. Updates that change `looks` on such a stimulus are held to the same rule. `exact.draw` already never reads a window's or scotoma's fill — keep it so.
2. **XC-256 (the multiply part) and XC-253 (call 1).** A grating shown only with `combine="multiply"` is not refused `unlit` for having no declared mean on a black background (its mean is never used); a multiplying grating that declares a `mean` is refused: `bad-placement` "… multiplies the contrast below by its modulation, so its declared mean would be ignored; remove it". (The rest of XC-256, a pattern over a lit stimulus, needs path analysis and stays filed; reword its backlog line to say only that part remains.)
3. **XC-249 (call 2).** A flat fill whose edge says `applies="contrast"` is refused: `bad-block` "a flat light's edge fades its light, so `applies` is \"opacity\" (or left unset); \"contrast\" applies to a pattern".
4. **XC-268.** The background advice (`_background_fix`) names every background parameter whose values can reach black — by its range's low end or by a choice of 0 or a black color — and, when an eye's background is black because it is unset or literally black, says to declare that eye's background (naming which eye on the stereoscope).

**Tests:** a window `Stimulus` whose looks is `Disc(size=1.0)` (no light) over a lit disc loads with no blocking finding, and `resolve` plus a preview `draw` give what is below inside it; the same `Disc(size=1.0)` with `combine="cover"` is still refused `unlit`, and `resolve` still raises for it; a multiplying `Gabor` with no mean on the black default loads; a multiplying `look.Look` grating with `mean=Gray(20.0)` is refused `bad-placement`; a flat `look.Look` with `edge=look.RaisedCosine(width=0.1, applies="contrast")` is refused `bad-block`; `_background_fix`'s text for (a) two background parameters both reaching 0 names both, (b) a parameter whose choices include `Gray(0.0)` names it, (c) a stereoscope trial with only `background_left` declared names the right eye. Add the window case and the multiplying-Gabor case to `tests/test_engine_path.py`'s accepted table.

**Closes:** XC-249, XC-253, XC-257, XC-268; narrows XC-256.

---

### Task 4: Per-eye positions in updates, and what the review report shows

**Files:** `wl_xcon/check.py`, `wl_xcon/review.py`; tests in `tests/test_display_checks.py` and the test file that covers `review.render` (find it with `grep -l "review" tests/`).

**Behavior:**
1. **XC-259 (first half).** An `Update` that sets `at` on a stimulus every `Show` of which carries per-eye positions is refused: `per-eye-misused` "… has per-eye positions, so `at` is not used; update `at_left` and `at_right`". (An `Update` that sets `at` together with both per-eye positions, on such a stimulus, is refused the same way.)
2. **XC-260.** An `Update` that sets only one of `at_left`, `at_right` is accepted when every `Show` of that stimulus carries both (the other eye keeps its position); it is still refused when some `Show` of it has none. Check 8 (`_as_updated`) must then measure that eye's new position with the other eye's old one — confirm it does (it varies each property independently) and add a test that an `Update(at_left=(12.5, 0.0))` on a per-eye stimulus through the stereoscope is refused `stimulus-off-screen`.
3. **XC-259 (second half).** `review.render`'s "Stimuli" table shows, per `Show`: the state, the stimulus's name, its position (`at`, or `L (x, y) / R (x, y)` when it has per-eye positions), disparity, eye, layer, combination and opacity; and the report states the trial's background (each eye's on the stereoscope, "black (default)" when unset) once, above the table. Values that are parameters print as their names, as the rest of the report does.

**Tests:** the two `Update` cases of item 1 refused; item 2's accepted case, its refused case, and its check-8 case; a `review.render` of a stereoscope trial with a per-eye stimulus, a layered `add` stimulus at opacity 0.5 and `background=Gray(20.0)` contains the new columns' values and the background line (assert on substrings of the markdown).

**Closes:** XC-259, XC-260.

---

### Task 5: The drawer's cross, its one modulation, and its untested corners

**Files:** `wl_xcon/exact.py`; tests in `tests/test_exact.py`, `tests/test_viewport.py`.

**Behavior:**
1. **XC-248 (call 4).** `signed_distance` for `look.Cross` is the exact signed distance to a plus shape of arm half-length `a = size/2` and half-thickness `b = thickness/2`: with `p = (|u|, |w|)` ordered so that `p.x ≥ p.y` (swap where `w > u`), `q = p − (a, b)`, `k = max(q.x, q.y)`, `v = q` where `k > 0` else `(b − p.x, −k)`, `d = sign(k) · |max(v, 0)|`. Vectorized over arrays. Its docstring states it is exact (and the module docstring's step 2 still holds).
2. **XC-254.** The grating's modulation `1 + m · sin(_phase(…)) · envelope` is written once (a helper both `_light` and `_gain` call).
3. **XC-252, XC-250, XC-247:** tests only.

**Tests:**
- Cross: for `look.Cross(size=2.0, thickness=0.2)`, `signed_distance` at `(0.09, 0.09)` is `−hypot(0.01, 0.01)` ≈ −0.014142 (the re-entrant corner (0.1, 0.1) is the nearest boundary point), at `(0.15, 0.15)` it is `+hypot(0.05, 0.05)` ≈ 0.070711, at `(0.5, 0.0)` it is −0.1, at `(1.2, 0.0)` it is +0.2, and at `(0.0, 0.5)` −0.1 (symmetry); the existing inside/outside test still passes. Prove: the old min-of-rectangles fails the `(0.09, 0.09)` case.
- XC-252: on gray 20, a lit `Disc(size=4, color=Gray(30))` and over it a `Disc(size=4, contrast=Weber(0.25))` with `combine="add"`: the center is 30 + 20·0.25 = 35. Prove: swapping `_light`'s mean and background arguments in the `add` branch fails it.
- XC-250: a soft edge drawn — a flat `look.Look(shape=Circle(size=4), fill=Flat(color=Gray(40)), edge=RaisedCosine(width=1.0))` on black: the pixel at radius 1.75° (half way into the 1° ramp from the 2° boundary) is ≈ 20 (rel 0.05) and at the center 40; an outline's opacity — the outline of a stimulus at `opacity=0.5` over black draws its band at half its color; `exact.draw` of a `Screen` holding an `Item` whose shape is a `Shape` subclass the drawer does not know raises `NotYetDrawable` naming a build.
- XC-247: a `Viewport` with `ahead_cm=(1.0, 0.5)` puts the sample nearest the viewport's center at x ≈ −1.0 cm, y ≈ −0.5 cm (the straight-ahead point moved right and up); `sample_cm(vp, 2)`'s first row's y is exactly `(height/2 − 0.25) · pitch_y`; for `c = viewport.center(30.0, 10.0)`, `local_true_angle` of `c` itself is (0, 0), of a direction 1° away in any of several directions has `hypot(u, w)` equal to `acos(v·c)` in degrees (1e-9), and of `viewport.center(30.0, 11.0)` has `w > 0`.

**Closes:** XC-247, XC-248, XC-250, XC-252, XC-254.

---

## Self-review

- Every backlog item in scope maps to a task and is closed in it; the out-of-scope ones are named with why in **Authority**.
- No new finding code; messages say what to write instead.
- The four calls are the only new decisions; each is cheap to undo, and none is science-facing.
