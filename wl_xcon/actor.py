"""Who sent a command: a name typed at the rig PC, or a wl.works member (P4d-2b b2b).

Spec: `docs/superpowers/specs/2026-10-02-p4d2b-b2b-remote-signin-design.md` §6, and S9a
§6, which designed the split.

**Two types, not one with a flag** (S9a §6), for the reason `bounds.Floor` and
`bounds.Ceiling` are two: so no call site can treat a name somebody typed as an account
wl.works vouched for, and so "we do not know who" can never print as a name.

- `Box` is a name typed at the rig PC: its page, `wlx console --as`, or a terminal's
  `--as`. Unverified, and it says so whenever it is printed.
- `Member` is a person wl.works signed in. **`wlx serve` makes one** from a wl.works
  token it has checked offline (b2b slice 2, built 2026-10-05), and only it does so on
  purpose; `from_map` still makes one from any member map that reaches `taskd` (XC-218).

**No dependencies**, so `bounds` stays pure and `welfare` imports no transport.

Both print as a person reads them, so a sentence written `f"stopped by {by}"` keeps
saying the right thing. The wire and the record carry `to_map`'s form, never the printed
one, and `to_map` refuses a string, so a call site that missed the change fails a test
instead of writing a name with nothing to say what kind it is.
"""

from __future__ import annotations

from dataclasses import dataclass

#: The longest name or field an actor may carry: the wire's `link.TEXT_LIMIT`, restated
#: here so this module imports nothing. `tests/test_actor.py` pins that the two agree.
TEXT_LIMIT = 200


@dataclass(frozen=True, slots=True)
class Box:
    """A name typed at the rig PC. Empty only where a terminal's rules allow it (a
    confirmation given without `--as`); the wire refuses an empty one."""

    name: str

    def __str__(self) -> str:
        return f"{self.name} (box, unverified)" if self.name else ""


@dataclass(frozen=True, slots=True)
class Member:
    """A person wl.works signed in at this rig's page: their name as wl.works shows it
    (the token's `name`), their wl.works account (`sub`), who vouched (`iss`), and the
    token's id (`jti`), which ties a record row to a token without being one."""

    name: str
    account: str
    issuer: str
    token_id: str

    def __str__(self) -> str:
        return f"{self.name} (wl.works)"


Actor = Box | Member

_MEMBER_FIELDS = ("name", "account", "issuer", "token_id")


class NotAnActor(ValueError):
    """A `by` that is not a box name or a member, as a map. The message is a sentence."""


def to_map(by: Actor) -> dict:
    """The wire's and the record's form. Anything but an actor is a `TypeError`: a
    string here is a call site the actor types never reached."""
    if isinstance(by, Box):
        return {"kind": "box", "name": by.name}
    if isinstance(by, Member):
        return {"kind": "member", **{field: getattr(by, field) for field in _MEMBER_FIELDS}}
    raise TypeError(f"an actor is a Box or a Member, not {type(by).__name__}")


def to_map_or_none(by: Actor | None) -> dict | None:
    """`to_map`, with `None` for nobody (a mark's stamp, an unreadable packet)."""
    return None if by is None else to_map(by)


def _text(value: object, what: str, *, empty: bool = False) -> str:
    if (
        not isinstance(value, str)
        or len(value) > TEXT_LIMIT
        or (not empty and not value.strip())
    ):
        raise NotAnActor(f"{what} is text of 1 to {TEXT_LIMIT} characters")
    return value


def from_map(data: object) -> Actor:
    """`to_map`'s form back to an actor, every field checked. Raises `NotAnActor`.

    A box's name may be empty here, because a record can hold one; whether the wire
    accepts an empty name is the wire's rule (`link._actor`)."""
    if not isinstance(data, dict):
        raise NotAnActor("who sent it is a box name or a wl.works member, given as a map")
    kind = data.get("kind")
    if kind == "box":
        if set(data) != {"kind", "name"}:
            raise NotAnActor("a box actor is its kind and its name, and nothing else")
        return Box(_text(data["name"], "a box name", empty=True))
    if kind == "member":
        if set(data) != {"kind", *_MEMBER_FIELDS}:
            raise NotAnActor(
                "a member is its kind, name, account, issuer and token_id, and nothing else"
            )
        return Member(**{field: _text(data[field], f"a member's {field}") for field in _MEMBER_FIELDS})
    raise NotAnActor("an actor's kind is box or member")


def read(value: object) -> Actor | str | None:
    """A `by` as a record holds it. A map is an actor; **a string is a name recorded
    before b2b (2026-10-02)**, returned as it was written; null is nobody. A record is
    never rewritten, so a reader of an older session must take all three."""
    if value is None or isinstance(value, str):
        return value
    return from_map(value)


def shown(by: Actor | str | None) -> str:
    """Who, as a sentence names them: an actor printed, a legacy string as written,
    nobody as nothing."""
    return "" if by is None else str(by)
