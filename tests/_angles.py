"""Where a position is, in true visual angle, computed in the tests from the formulas the PI and
the record name, never from `wl_xcon.geometry`, so a test of the record cannot agree with its code
by construction (XC-399). Never collected: its name does not start with `test_`.

A per-axis position `(x, y)` names the direction `(tan x, tan y, 1)` (each axis `atan(X/D)`).
"""

from __future__ import annotations

import math


def true(x: float, y: float) -> tuple[float, float]:
    """The eccentricity and direction of `(x, y)`, in degrees: `atan(√(tan²x + tan²y))` and
    `atan2(tan y, tan x)`, the formulas the record is told to wl-preproc in."""
    tx, ty = math.tan(math.radians(x)), math.tan(math.radians(y))
    return (math.degrees(math.atan(math.sqrt(tx * tx + ty * ty))),
            math.degrees(math.atan2(ty, tx)))


def from_polar(eccentricity: float, direction: float) -> tuple[float, float]:
    """The per-axis position `eccentricity` degrees out, `direction` degrees counter-clockwise from
    rightward (engine spec §5.1): `atan(tan e·cos θ)` across and `atan(tan e·sin θ)` up."""
    reach = math.tan(math.radians(eccentricity))
    t = math.radians(direction)
    return (math.degrees(math.atan(reach * math.cos(t))),
            math.degrees(math.atan(reach * math.sin(t))))


def _unit(x: float, y: float) -> tuple[float, float, float]:
    v = (math.tan(math.radians(x)), math.tan(math.radians(y)), 1.0)
    norm = math.sqrt(sum(c * c for c in v))
    return (v[0] / norm, v[1] / norm, v[2] / norm)


def apart(a: tuple[float, float], b: tuple[float, float]) -> float:
    """The true visual angle between two per-axis positions, in degrees."""
    u, v = _unit(*a), _unit(*b)
    return math.degrees(math.acos(max(-1.0, min(1.0, sum(p * q for p, q in zip(u, v))))))


def ring(x: float, y: float, radius: float, phase: float, n: int) -> list[tuple[float, float]]:
    """An array's objects about `(x, y)` as STE-28 defines them: a true circle of `radius` degrees
    of visual angle about the center's direction, object `i` at `phase + 360 i / n` degrees
    counter-clockwise from the center's local rightward axis -- the screen's rightward axis less its
    share along the center, upward square to both."""
    c = _unit(x, y)
    right = (1.0 - c[0] * c[0], -c[0] * c[1], -c[0] * c[2])
    norm = math.sqrt(sum(r * r for r in right))
    right = tuple(r / norm for r in right)
    up = (c[1] * right[2] - c[2] * right[1], c[2] * right[0] - c[0] * right[2],
          c[0] * right[1] - c[1] * right[0])
    r = math.radians(radius)
    objects = []
    for i in range(n):
        phi = math.radians(phase + 360.0 * i / n)
        v = [math.cos(r) * c[k] + math.sin(r) * (math.cos(phi) * right[k] + math.sin(phi) * up[k])
             for k in range(3)]
        objects.append((math.degrees(math.atan(v[0] / v[2])), math.degrees(math.atan(v[1] / v[2]))))
    return objects
