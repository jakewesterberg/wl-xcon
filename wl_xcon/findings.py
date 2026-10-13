"""What a refusal looks like, wherever one is raised.

Lifted out of `check.py` when gaze calibration needed the same vocabulary. Both
answer the same question in the same words -- *this is why I will not proceed, and
here is the name of the reason* -- and the CLI renders either without caring which
produced it.

It lives in its own module rather than in `check.py` because the dependency has to
run the other way: a load-time check that compares a task's declared eccentricity
range against the calibrated extent will import `calibration`, and `calibration`
already needs to report findings. One of the two had to move, and a four-line
dataclass is the cheaper thing to relocate.

Since engine build B a finding also says which session kinds it is acceptable in: a
warning (spec §19.2).
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: What a session is for (engine spec §19.1; the PI, 2026-10-07: "Sessions say what they are
#: for"), chosen when it opens. In this order wherever a list of them is written.
SESSION_KINDS = ("training", "piloting", "recording")

#: A warning acceptable everywhere but in a recording. **No finding gives it since the PI's
#: rulings of 2026-10-11** (XC-352's A21: the default calibration's colors are "a warning in
#: recording too", COL-02, revised); kept as the vocabulary a warning's kinds are written in.
NOT_RECORDING = ("training", "piloting")


def kind_named(kind: object) -> str:
    """`kind`, when it is one of `SESSION_KINDS`; otherwise a `ValueError` naming the three."""
    if not isinstance(kind, str) or kind not in SESSION_KINDS:
        raise ValueError(
            f"a session is for training, piloting or recording, and {kind!r} is none of them"
        )
    return kind


@dataclass(frozen=True, slots=True)
class Finding:
    code: str
    detail: str
    #: Whether this refuses the load in every session kind. A non-blocking finding still
    #: surfaces -- a `Custom` component is legitimate and still belongs on the review list.
    blocking: bool = True
    #: **The session kinds this finding is acceptable in, when it is a warning** (engine
    #: spec §19.2: "Each states the session kinds it is acceptable in; outside them it
    #: refuses"). Empty for a refusal and for a review note, which no session accepts or
    #: refuses: it asks for a person's review of the task, not of the session.
    accepted_in: tuple[str, ...] = ()
    #: **What it is about**, where that must be told apart from its sentence, which carries
    #: numbers: for a task's one `unrealizable-color` warning, each thing asking for a light the
    #: panel cannot make with the color as the task wrote it, such as "Disc asking for
    #: Gray(cd_m2=P(name='disc'))" (`check._clips`; two things asking for one written color
    #: clip alike and are one subject, two written colors of one type two -- Task 10's review,
    #: I1); for `overlapping-windows`, the state and the pair of windows; for `crowded-array`,
    #: the array; each named by its structure in a task of several (`check.check_task`). For a
    #: value outside its declared range, it says whether a finding of `check.BREAKS_A_RUN` is
    #: about something the declared ranges already give (`check.beyond_range`). No part of its
    #: equality, nor of what a session accepts; compared where it must be (`check._among`).
    subjects: tuple[str, ...] = field(default=(), compare=False)

    def __post_init__(self) -> None:
        if not isinstance(self.accepted_in, tuple):
            raise TypeError(
                f"a finding's accepted_in is a tuple of session kinds, not "
                f"{type(self.accepted_in).__name__}"
            )
        for kind in self.accepted_in:
            kind_named(kind)
            if self.accepted_in.count(kind) > 1:
                raise ValueError(f"a finding's accepted_in names {kind!r} twice")
        if self.blocking and self.accepted_in:
            raise ValueError(
                "a finding that refuses in every kind is accepted in none; give accepted_in "
                "only to a warning (blocking=False)"
            )

    @property
    def is_warning(self) -> bool:
        """Whether this belongs on a session's warnings list: acceptable in some kinds."""
        return not self.blocking and bool(self.accepted_in)

    def refuses(self, kind: str | None) -> bool:
        """Whether this refuses a session of `kind`. `None` asks without a session -- `wlx
        check` with no `--kind` -- where only a blocking finding refuses."""
        if kind is None:
            return self.blocking
        kind_named(kind)
        return self.blocking or (self.is_warning and kind not in self.accepted_in)
