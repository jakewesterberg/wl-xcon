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

from dataclasses import dataclass

#: What a session is for (engine spec §19.1; the PI, 2026-10-07: "Sessions say what they are
#: for"), chosen when it opens. In this order wherever a list of them is written.
SESSION_KINDS = ("training", "piloting", "recording")

#: A warning acceptable everywhere but in a recording (spec §7.2: the default calibration
#: "refused in recording" for a task that names a color or makes contrast a factor).
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
