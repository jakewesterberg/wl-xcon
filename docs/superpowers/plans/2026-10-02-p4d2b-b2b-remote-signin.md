# P4d-2b b2b Remote Sign-in Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** a lab member signed in to wl.works can use every control on a rig's https page, and the session records them as a wl.works member. The rig PC's page keeps every control it has today, and names typed there stay marked unverified.

**Architecture:** two slices, each with its own review and its own fast-forward to `main` (spec §13).
- **Slice 1, the actor types (Tasks 1-4).** A new dependency-free module, `wl_xcon/actor.py`, holds `Box` and `Member`. `by` becomes one of them everywhere it travels: on the wire, in `taskd` and the service, in the welfare modules and in the record, and in telemetry (schema 14). The page and `wlx console` show the two kinds apart. Slice 1 adds no behavior: every actor is still a `Box` when it ends.
- **Slice 2, signing in (Tasks 5-13).** A new module, `wl_xcon/signin.py`, checks a wl.works access token offline. `wlx serve` gains an https listener that accepts commands carrying a valid token and turns them into `Member` commands, plus `/whoami` and `/signout`. The page's script signs a member in with PKCE, renews, and signs out. Playwright drives the page in a real browser.

**Tech Stack:** Python 3.11+, pytest, stdlib `http.server` and `ssl`, msgpack and pyzmq (the `console` extra), PyJWT with `cryptography` (a new `signin` extra), and Playwright with headless Chromium (a new `browser` extra, tests only).

**Spec:** `docs/superpowers/specs/2026-10-02-p4d2b-b2b-remote-signin-design.md`, approved by the PI 2026-10-02. The spec is the authority; where this plan and the spec differ, the spec wins and the difference is a defect in this plan, to be reported.

## Global Constraints

- US English. No timing claim without a measurement. Every new constant in seconds or bytes is called housekeeping in its comment, never a measurement.
- Sim first. **Hot path:** nothing in this plan runs in a frame. Commands are still drained at trial boundaries.
- **Welfare-critical code** is the whole of `welfare.py`, `bounds.py`, `marks.py` and `stranded.py`, plus the named functions in `taskd.py`, `service.py`, `cli.py`, `preflight.py` and `link.py` (`docs/design/architecture.md`, from "**In code, that is**"). Slice 1 changes `by`'s type there and no rule. Each such line goes in the PI's review summary (spec §10 item 5). **The list is not widened by this plan.**
- **The token is never written anywhere**: not in a record, a log line, a response body, an exception message or a test failure message. Only its `jti` is kept, as `Member.token_id`.
- **PyJWT floor `pyjwt[crypto]>=2.10.1`** (spec §9: 2.10.0 checked a string issuer as a substring). Imported only by `wl_xcon/signin.py`. `signin.py` is imported only by `wlx serve` when `--https` is given.
- Wire `by` is a map: `{"kind": "box", "name": …}` or `{"kind": "member", "name": …, "account": …, "issuer": …, "token_id": …}`. A bare string `by` is refused. Telemetry schema 13 → 14.
- Run the suite with `WLX_REQUIRE_PREPROC=1`. A worktree's `wl-preproc` link points at a `git archive` export of wl-preproc's `origin/main` (CHECKPOINT, 2026-10-02, "wl-preproc for a worktree's suite").
- Install for this plan: `pip install -e ".[dev,contract,console,signin,browser]"` and `python3 -m playwright install chromium` (slice 2). Run the browser tests with `WLX_REQUIRE_BROWSER=1`.
- **Prove each new test can fail, by hand**: break the code it covers, see the test fail by name, restore the file, check it with `cmp`, then delete `wl_xcon/__pycache__` (stale bytecode has fooled this check before).
- **Never run the suite, edit a test or `git add` while a mutation sweep is in flight** (CLAUDE.md).
- **Backlog:** closing an item removes its line in the commit that does the work, and the commit message names the ID. Run `tests/test_backlog.py` alone before committing a backlog change.

## Rulings in this plan

1. **The actor types live in `wl_xcon/actor.py`, not in `link.py`.** `bounds` is pure and `welfare` must not import the transport's module; a dependency-free module keeps both true. `link` imports it.
2. **`Box` and `Member` print as a person reads them** (`str()`): `jake (box, unverified)` and `Jake Westerberg (wl.works)`. So a sentence written `f"stopped by {by}"` keeps saying the right thing. This matches today's text for the box page, whose names already carry the suffix (`serve._person`). A terminal's `--as jake` gains the suffix too: a name typed at the rig PC's terminal is just as unverified.
   - `Box("")` prints as an empty string, as today's empty `by` does. It exists only where a terminal's rules already allow an empty name (a confirmation given without `--as`), and never on the wire.
3. **Every record writer converts with `actor.to_map`, explicitly, and `to_map` raises `TypeError` on a string.** A writer that relied on `json.dumps` would silently write a string handed to it by a missed call site; this way a missed site fails a test.
4. **"Nobody" is `None`, not a placeholder actor.**
   - `Refused.by` is `None` where `"<unknown>"` stands today: a packet that named no readable sender, a malformed mark signal, a mark with no session.
   - `Control.by` is `None` where `""` stands today: a mark's stamp, whose sender arrives with its note.
   - `CommandRefused.by` is `Actor | None`. Every other `by` is an `Actor`.
5. **Telemetry carries the actor's whole map**, the member's account and token id included. Neither is a secret: the token id names a token without being one, and the page shows only the name.
6. **The browser test's dependency is its own extra, `browser`, not `dev`** (a deviation from spec §9's wording, same intent). The three CI jobs install `dev`, and only the pytest job needs Playwright, so the mutation jobs neither download nor run it. It is dev-only all the same: never installed on a rig.
7. **The page's sign-in state is the script's, and the greying stays Python's.** Python renders a control that only needs a sign-in as `disabled data-signin`. The script sets `disabled` on every `[data-signin]` element from whether it holds a sign-in, after every fragment swap. A control greyed for its own reason (paused-only reward, no mark endpoint) never carries `data-signin`. `web._gate` replaces `web._off` for this.
8. **A 401 from the rig carries a `reason` word** beside its sentence (`no_token`, `signed_out`, `expired`, `other_rig`, `clock`, `not_accepted`, `no_keys`), so the script can tell *renew* from *sign in again* from *wait* without parsing a sentence.
9. **The https listener does its TLS handshake on the connection's thread** (spec §3): a `ThreadingHTTPServer` subclass wraps each accepted socket in its own `finish_request`.
10. **The request log never carries a query string.** The handler's `log_request` writes the path alone, on both listeners. Without it, the stdlib's default would print wl.works' authorization code to stderr on every return to the page.
11. **Slice 1 ends with its own PI review (spec §10 item 5), a push, CI read and a fast-forward to `main`**, as b3a-1 did. Slice 2 starts on a fresh branch from that `main`.

## Review Focus

1. **A pre-b2b record read back.** `controls.jsonl`, `welfare_notes.jsonl` and `runs.jsonl` written before this change hold string `by`s. A resume and a stranded end of such a session must still work, and must show the old name as written. Test: Task 2 (`resume`'s sentence from a string `by`), Task 3 (`actor.read` of a string).
2. **A box name typed to look like a member's.** A name such as `Jake Westerberg (wl.works)` typed at the box must still read as a box name in the feed, the strip, the refusals and `wlx console`. Test: Task 3.
3. **A token arriving where it must not.** A token sent to the plain-http listener is refused there, a body `by` beside a token is refused, and a box command with no token on https is refused. Test: Task 9.
4. **The authorization code and the token stay out of every file and log.** After an end-to-end signed-in session, no file in the session folder, nothing on `wlx serve`'s stderr and no response body contains the access token, the renewal token or the code. Test: Task 9 (record and stderr), Task 11 (the browser path).
5. **A tab left open past its hour.** The next command renews first. A refused renewal drops the page to signed out with wl.works' sentence. A reward is never sent twice by the page, whatever the token's state. Test: Task 11.

---

# Slice 1 — the actor types

### Task 1: `wl_xcon/actor.py`

**Files:**
- Create: `wl_xcon/actor.py`
- Modify: `tools/mutation_gate.py` (add `"actor": "None"` to `RETURNS`)
- Test: `tests/test_actor.py`

**Interfaces:**
- Produces:
  - `actor.Box(name: str)` and `actor.Member(name: str, account: str, issuer: str, token_id: str)`, frozen, slotted, each with `__str__`;
  - `actor.Actor = Box | Member`;
  - `actor.TEXT_LIMIT = 200`;
  - `actor.to_map(by: Actor) -> dict` (raises `TypeError` for anything else);
  - `actor.to_map_or_none(by: Actor | None) -> dict | None`;
  - `actor.NotAnActor(ValueError)`;
  - `actor.from_map(data: object) -> Actor` (raises `NotAnActor`);
  - `actor.read(value: object) -> Actor | str | None` (a record's `by`: map, legacy string or null);
  - `actor.shown(by: Actor | str | None) -> str`.

- [ ] **Step 1: Write the failing tests** in `tests/test_actor.py`:

```python
"""`wl_xcon/actor.py`: who sent a command (b2b spec §6)."""

from __future__ import annotations

import pytest

from wl_xcon import actor
from wl_xcon import link
from wl_xcon.actor import Box, Member

MEMBER = Member(
    name="Jake Westerberg",
    account="user-1",
    issuer="https://wl.works/api/auth",
    token_id="jti-1",
)


def test_each_kind_prints_as_a_person_reads_it():
    assert str(Box("jake")) == "jake (box, unverified)"
    assert str(MEMBER) == "Jake Westerberg (wl.works)"
    assert str(Box("")) == ""


def test_a_box_name_dressed_as_a_member_still_prints_as_a_box():
    assert str(Box("Jake Westerberg (wl.works)")) == (
        "Jake Westerberg (wl.works) (box, unverified)"
    )


def test_to_map_and_from_map_round_trip_both_kinds():
    assert actor.to_map(Box("jake")) == {"kind": "box", "name": "jake"}
    assert actor.to_map(MEMBER) == {
        "kind": "member",
        "name": "Jake Westerberg",
        "account": "user-1",
        "issuer": "https://wl.works/api/auth",
        "token_id": "jti-1",
    }
    assert actor.from_map(actor.to_map(Box("jake"))) == Box("jake")
    assert actor.from_map(actor.to_map(MEMBER)) == MEMBER


@pytest.mark.parametrize("not_one", ["jake", None, 3, ("box", "jake")])
def test_to_map_refuses_anything_but_an_actor(not_one):
    with pytest.raises(TypeError):
        actor.to_map(not_one)


def test_to_map_or_none_passes_nobody_through():
    assert actor.to_map_or_none(None) is None
    assert actor.to_map_or_none(Box("jake")) == {"kind": "box", "name": "jake"}


@pytest.mark.parametrize(
    "data",
    [
        "jake",
        None,
        {"kind": "box"},
        {"kind": "box", "name": 3},
        {"kind": "box", "name": "jake", "extra": 1},
        {"kind": "member", "name": "J", "account": "a", "issuer": "i"},
        {"kind": "member", "name": "", "account": "a", "issuer": "i", "token_id": "t"},
        {"kind": "member", "name": "J", "account": "a", "issuer": "i", "token_id": 5},
        {"kind": "admin", "name": "jake"},
        {"kind": "box", "name": "x" * 201},
    ],
)
def test_from_map_refuses_what_is_not_an_actor(data):
    with pytest.raises(actor.NotAnActor):
        actor.from_map(data)


def test_from_map_keeps_an_empty_box_name_for_a_record_that_has_one():
    """A terminal confirmation given without --as is recorded with an empty name;
    reading it back must work. The wire refuses an empty name separately."""
    assert actor.from_map({"kind": "box", "name": ""}) == Box("")


def test_read_takes_a_map_a_legacy_string_and_null():
    """Review Focus 1: a record written before b2b holds a string `by`."""
    assert actor.read({"kind": "box", "name": "jake"}) == Box("jake")
    assert actor.read("jake (box, unverified)") == "jake (box, unverified)"
    assert actor.read(None) is None


def test_shown_takes_an_actor_a_legacy_string_and_nobody():
    assert actor.shown(MEMBER) == "Jake Westerberg (wl.works)"
    assert actor.shown("jake (box, unverified)") == "jake (box, unverified)"
    assert actor.shown(None) == ""


def test_the_limit_is_the_wires():
    assert actor.TEXT_LIMIT == link.TEXT_LIMIT
```

- [ ] **Step 2: Run them to see them fail.** `python3 -m pytest -q -p no:cacheprovider tests/test_actor.py`. Expected: collection error, `No module named 'wl_xcon.actor'`.

- [ ] **Step 3: Write `wl_xcon/actor.py`:**

```python
"""Who sent a command: a name typed at the rig PC, or a wl.works member (P4d-2b b2b).

Spec: `docs/superpowers/specs/2026-10-02-p4d2b-b2b-remote-signin-design.md` §6, and S9a
§6, which designed the split.

**Two types, not one with a flag** (S9a §6), for the reason `bounds.Floor` and
`bounds.Ceiling` are two: so no call site can treat a name somebody typed as an account
wl.works vouched for, and so "we do not know who" can never print as a name.

- `Box` is a name typed at the rig PC: its page, `wlx console --as`, or a terminal's
  `--as`. Unverified, and it says so whenever it is printed.
- `Member` is a person wl.works signed in. **Only `wlx serve` makes one**, after
  `signin.Checker` has checked their token (b2b's second slice).

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
```

Add `"actor": "None",` to `RETURNS` in `tools/mutation_gate.py`, beside `"resume": "None",`.

- [ ] **Step 4: Run the tests to see them pass.** Same command. Expected: all pass.
- [ ] **Step 5: Prove the new tests can fail.** Change `Box.__str__` to return `self.name`, run, and see `test_each_kind_prints_as_a_person_reads_it` fail by name. Make `to_map` return `{"kind": "box", "name": str(by)}` for anything, run, and see `test_to_map_refuses_anything_but_an_actor` fail. Restore the file each time, check it with `cmp` against a copy, and delete `wl_xcon/__pycache__`.
- [ ] **Step 6: Commit.** `git add wl_xcon/actor.py tests/test_actor.py tools/mutation_gate.py` then commit: "Add the actor types: a box name and a wl.works member (b2b spec §6)".

---

### Task 2: `by` is an actor on the wire, through the session, and in the record

One atomic change, because a `by` cannot be an actor in one module and a string in the next without the suite going red between them. The steps go module by module in the order a command travels. Each step has its rule, the lines it touches, and code for the parts that are not mechanical.

**Files:**
- Modify: `wl_xcon/link.py`, `wl_xcon/taskd.py`, `wl_xcon/service.py`, `wl_xcon/record.py`, `wl_xcon/welfare.py`, `wl_xcon/bounds.py`, `wl_xcon/marks.py`, `wl_xcon/stranded.py`, `wl_xcon/preflight.py`, `wl_xcon/resume.py`, `wl_xcon/cli.py`, `wl_xcon/serve.py`, `wl_xcon/web.py`.
- Test: every test file that builds a `by` (`grep -c 'by=' tests/*.py` lists them; `test_taskd.py`, `test_link.py`, `test_service.py`, `test_serve.py`, `test_marks.py`, `test_cli.py`, `test_welfare.py`, `test_record.py`, `test_stranded.py`, `test_bounds.py`, `test_preflight.py`, `test_resume.py`, `test_web.py`), and `tests/_frames.py` if it builds a `Staged`, `Refused`, `ScheduledStop` or `Control`.

**Interfaces:**
- Consumes: Task 1's `actor` module.
- Produces:
  - every `link` command's `by: Actor`;
  - `link.Staged.by: Actor`, `link.ScheduledStop.by: Actor`, `link.Refused.by: Actor | None`, `link.Control.by: Actor | None`;
  - `link.CommandRefused(name: str, by: Actor | None, why: str)`;
  - `link.SCHEMA = 14`;
  - `serve._person(by: object) -> actor.Box`; `serve.MarkSignal.by` and `serve.MarkNote.by` are `Actor`;
  - every record row's `by` (and `runs.jsonl`'s preflight rows' `acknowledged_by`) is `actor.to_map`'s map or null.

**The rules, which every step applies:**
- **R1.** A parameter, field or tuple slot that holds who sent something is annotated `Actor` (from `wl_xcon.actor`), or `Actor | None` where Ruling 4 says nobody is possible.
- **R2.** Wherever a `by` is put into a dict that becomes JSON or msgpack, write `actor.to_map(by)` (or `to_map_or_none`).
- **R3.** Wherever a `by` is formatted into a sentence by an f-string, leave it: `str()` prints it correctly (Ruling 2). Wherever it is passed to a function that expects text (`_printable`, `_e`, `.strip()`), pass `actor.shown(by)` or read `by.name`.
- **R4.** Import as `from wl_xcon import actor as actors` in a module that already has a local named `actor` or `_actor`, otherwise `from wl_xcon.actor import Actor, Box`.

- [ ] **Step 1: The wire, `wl_xcon/link.py`.**
  - Annotate every command dataclass's `by` as `Actor` (R1). Annotate `Staged.by` and `ScheduledStop.by` as `Actor`, and `Refused.by` and `Control.by` as `Actor | None`. Update `Control`'s docstring: "`by` is who sent it, `None` for a mark's stamp, whose sender arrives with its note".
  - `CommandRefused.__init__(self, name: str, by: Actor | None, why: str)`.
  - Replace `_actor`:

```python
def _actor(by: object, name: str) -> Actor:
    """`by`, when it is an actor's map with a name (b2b spec §6): a box name of 1 to
    `TEXT_LIMIT` characters, or a wl.works member.

    S9a §6: every welfare-affecting write records its actor, and a write from nobody
    is refused rather than recorded as written by nobody. **A bare string is refused
    too**: since b2b a name with nothing to say what kind it is is not an actor. `name`
    is what the refusal is filed under -- the parameter for a setting, the command's
    kind otherwise."""
    try:
        who = actors.from_map(by)
    except actors.NotAnActor:
        who = None
    if who is None or not who.name.strip():
        raise CommandRefused(
            name,
            None,
            f"a {name!r} command must say who sent it (`by`: a box name or a wl.works "
            f"member; S9a §6), and this one did not, so it is refused",
        )
    return who
```

  - In `_command_from`'s `set` branch, where the sender of a nameless setting is read, use `_sender(data.get("by"))` in place of the inline string test:

```python
def _sender(by: object) -> Actor | None:
    """Who a malformed command said it was from, when it said so readably, for its
    refusal's row; `None` otherwise."""
    try:
        return actors.from_map(by)
    except actors.NotAnActor:
        return None
```

  - `_encode_command`: every `"by": command.by` becomes `"by": actors.to_map(command.by)` (R2).
  - The telemetry encoders: `_refusals_out` writes `actors.to_map_or_none(r.by)`. The `staged` list writes `actors.to_map(s.by)`, `scheduled_stop` writes `actors.to_map(...)`, and `controls` writes `actors.to_map_or_none(c.by)`.
  - The telemetry decoders, in `_telemetry_from` and `_idle_from`:

```python
        staged=tuple(Staged(**{**s, "by": actors.from_map(s["by"])}) for s in data["staged"]),
        refusals=tuple(_refused_in(r) for r in data["refusals"]),
        ...
        scheduled_stop=(
            None
            if data["scheduled_stop"] is None
            else ScheduledStop(
                **{**data["scheduled_stop"], "by": actors.from_map(data["scheduled_stop"]["by"])}
            )
        ),
        controls=tuple(
            Control(**{**c, "by": None if c["by"] is None else actors.from_map(c["by"])})
            for c in data["controls"]
        ),
```

    with

```python
def _refused_in(r: dict) -> Refused:
    return Refused(name=r["name"], by=None if r["by"] is None else actors.from_map(r["by"]), why=r["why"])
```

    and use `_refused_in` in `_idle_from` too.
  - In `decode`, the `except (KeyError, TypeError)` that turns a bad frame into `FrameError` becomes `except (KeyError, TypeError, actors.NotAnActor)`.
  - `ZmqLink.drain`: both `by="<unknown>"` become `by=None`. Rewrite the docstring sentence that says `name` and `by` are placeholders: "`name` is a placeholder (`"<transport>"`) and `by` is `None`".
  - `SCHEMA = 14`, with this entry under 13's:

```python
#: 14 (2026-10-02, P4d-2b b2b spec §6): every `by` is an actor's map, a box name or a
#: wl.works member (`actor.to_map`), where it was a string; a refusal's and a control's
#: is null for nobody, where it was `"<unknown>"` or empty. A reader of 13 refuses 14 and
#: 14 refuses 13, by name.
```

  - Update the P4d-3 docstring in `ZmqLink.__init__` (`grep -n 'P4d-3' wl_xcon/link.py`). Its sentence "rather than the bare `by: str` this link carries today. Until that lands, `by` is whatever the sender typed" becomes: "The actor types exist since b2b (`actor.py`), and a `Member` is made only by `wlx serve` after a wl.works token checks out; on this socket, a `by` is still whatever the local sender wrote, so the loopback-only bind remains what makes that acceptable."

- [ ] **Step 2: The session, `wl_xcon/taskd.py`.**
  - R1 on every `by` parameter and on the tuple slots documented beside `refusals`, `_controls`, `_staged` and `scheduled_stop`.
  - A mark's stamp feeds its control with `by=None` where it passes `""` today (`grep -n '"mark"' wl_xcon/taskd.py` and read `stamp`).
  - In `Session.resume`, `self.spec.bounds.set(name, value, by=f"{by}, restored on resume")` becomes `self.spec.bounds.set(name, value, by=by)`. `bounds.set` records nothing (its docstring: "`by` is the actor the caller records"); the resume's own `session resumed` row already says how.
  - Every other `by` in `taskd.py` is passed through, or formatted by an f-string (R3, unchanged).

- [ ] **Step 3: The service, `wl_xcon/service.py`.** R1 throughout. `_mark`'s `self._refuse("mark", "<unknown>", …)` becomes `self._refuse("mark", None, …)`, and `_refuse`'s `by` is `Actor | None`.

- [ ] **Step 4: The welfare modules** (welfare-critical; the type and the written form change, never a rule).
  - `bounds.py`: `Bounds.set(self, name: str, value: float, by: Actor)`, importing `from wl_xcon.actor import Actor`.
  - `welfare.py`: `confirm_already_today(..., by: Actor)`; `amend_mark(..., by: Actor)`, whose blank check becomes `if not by.name.strip():` with its sentence unchanged.
  - `marks.py`: `Confirm.by`, `Amend.by`, `Departure.by`, and every `by` parameter, are `Actor`. The `note` dict keeps the actor itself under `"by"`: `record.welfare_note` converts it (Step 5).
  - `stranded.py`: `by: Actor` in `restore`'s inner `returned_to_cage` (its default `""` becomes `Box("")`).

- [ ] **Step 5: The record, `wl_xcon/record.py`.** R2 in each writer: `welfare_note`, `parameter_change`, `control` (`to_map_or_none`, since a stamp's is `None`) and `refusal` (`to_map_or_none`). In `SessionRecord.run`, which takes `**fields`, write a `by` among them as `actors.to_map(fields["by"])` before the row is dumped. Annotate each `by` parameter (R1).

- [ ] **Step 6: The pre-flight rows, `wl_xcon/preflight.py` `rows`** (not on the welfare list; `out_of_cage` and `gate` are, and are not touched):

```python
def rows(preflight: Preflight, by: Actor | None, acknowledged: Collection[str]) -> list[dict]:
    ...
    if signed and not (isinstance(by, (Box, Member)) and by.name.strip()):
        raise ValueError(...)  # the sentence unchanged
    return [
        {
            ...
            "acknowledged_by": actors.to_map(by) if item in signed else None,
        }
        ...
    ]
```

  Read the function first. If `wlx run` calls it with no actor today (`by=""`), it passes `None` now.

- [ ] **Step 7: Reading a record back, `wl_xcon/resume.py`.** Line 199's `f"session ended by {ends[0]['by']}, before any run"` becomes `f"session ended by {actors.shown(actors.read(ends[0]['by']))}, before any run"`. A record written before b2b holds a string there (Review Focus 1).

- [ ] **Step 8: The terminal, `wl_xcon/cli.py`.**
  - Every `by=args.actor` becomes `by=Box(args.actor or "")`. Read each site: a site that refuses a missing `--as` first keeps that refusal.
  - `_settle_return(session, actor: Actor, …)`; `main` passes `Box(args.actor or "")`.
  - `given = {"by": args.actor, …}` (line ~335) becomes `{"by": Box(args.actor or ""), …}`.
  - `wlx console`'s commands become `_link.SetParameter(name=name, value=value, by=Box(args.actor))` and `_link.Stop(by=Box(args.actor))`.
  - `render`: every `_printable(x.by)` becomes `_printable(actors.shown(x.by))`, which covers the refusal, staged, scheduled-stop and control lines.

- [ ] **Step 9: The box page's sender, `wl_xcon/serve.py`.**
  - `_person` returns `Box(by.strip())` (the suffix now comes from `str()`), with its refusal unchanged.
  - `MarkSignal.by` and `MarkNote.by` are `Actor`.
  - In `parse_command`, the service kinds go to `link._command_from({**data, "by": actors.to_map(by)})`, since `_command_from` now reads a map.
  - The POST body's `by` stays a typed name: the box page sends `"by": "jake"`, and `_person` makes the `Box`.

- [ ] **Step 10: The page, `wl_xcon/web.py`.** `_e(x.by)` already prints correctly through `str()` (R3), so it stays as is until Task 3. Fix only what breaks: a `by` tested for truthiness where `""` meant nobody is now `None`, which is also falsy, so read each site and keep it.

- [ ] **Step 11: The tests.**
  - In every test file listed under **Files**, import `from wl_xcon.actor import Box`.
  - Every Python-side construction `by="X"` becomes `by=Box("X")`: link commands, `Session` calls, `marks`, `welfare`, `stranded`, `preflight.rows` and `Refused`/`Staged`/`Control`/`ScheduledStop` rows.
  - **Leave alone:** JSON bodies posted to `/commands` (`"by": "jake"` there is the typed name the box page sends).
  - A hand-built msgpack packet's `"by": "jake"` becomes `"by": {"kind": "box", "name": "jake"}`.
  - Assertions on record rows compare maps: `row["by"] == {"kind": "box", "name": "jake"}`, where they compared `"jake (box, unverified)"`.
  - Assertions on sentences keep their text where the box page sent the command. Where a terminal's `--as jake` did, the text gains ` (box, unverified)`.
  - Where a test asserted `by == "<unknown>"` or `by == ""` for nobody, it asserts `is None`.
  - Add to `tests/test_link.py`:

```python
def test_a_string_by_on_the_wire_is_refused_naming_the_rule():
    """b2b spec §6: a name with nothing to say what kind it is is not an actor."""
    import msgpack
    from wl_xcon.link import CommandRefused, _decode_command

    with pytest.raises(CommandRefused) as refused:
        _decode_command(msgpack.packb({"kind": "stop", "by": "jake"}, use_bin_type=True))
    assert refused.value.by is None
    assert "a box name or a wl.works member" in refused.value.why


def test_a_member_survives_the_wire_and_a_frame():
    from wl_xcon.actor import Member
    from wl_xcon.link import Pause, _decode_command, _encode_command

    member = Member(name="Jake Westerberg", account="u-1", issuer="https://wl.works/api/auth", token_id="j-1")
    assert _decode_command(_encode_command(Pause(by=member))) == Pause(by=member)
```

    Then, in the file's existing telemetry round-trip test (`grep -n 'def test_.*round' tests/test_link.py`), add a `Control` with `by=None` and a `Staged` with a `Member`, and assert both come back equal. Also add a frame whose control's `by` is `{"kind": "admin"}` and assert `decode` raises `FrameError`.
  - Add to `tests/test_record.py`: a `control` row written with `by=None` reads back `null`, and one written with a string raises `TypeError`.
  - Add to `tests/test_resume.py` (**Review Focus 1**): a session folder whose `controls.jsonl` `end` row carries `"by": "jake (box, unverified)"` (a pre-b2b string) gives the sentence `session ended by jake (box, unverified), before any run`. Build it the way the file's existing end-before-any-run test builds its folder, then rewrite that row's `by` to the string.

- [ ] **Step 12: Run the whole suite.** `WLX_REQUIRE_PREPROC=1 python3 -m pytest -q -p no:cacheprovider`. Every failure is a site this task missed: fix it in its own module, under the rules above. Expected: green, with the count equal to the start count plus the new tests.

- [ ] **Step 13: Find what the suite cannot see.**
  - `grep -n 'by: str' wl_xcon/*.py`. Every remaining hit must be a reason or a sentence, never who sent something.
  - `grep -n '"<unknown>"' wl_xcon/*.py` must be empty.
  - `grep -n '"by": by\b\|"by": command.by\|"by": s.by\|"by": c.by\|"by": r.by' wl_xcon/*.py` must be empty, except in `marks.py`'s `note`, which `record.welfare_note` converts.

- [ ] **Step 14: Prove the new tests can fail.**
  - Make `_actor` accept a string again (`if isinstance(by, str): return actors.Box(by)` first) and see `test_a_string_by_on_the_wire_is_refused_naming_the_rule` fail.
  - Make `_refused_in` return `by=r["by"]` and see the round-trip test fail.
  - Restore each file, check it with `cmp`, and delete `wl_xcon/__pycache__`.

- [ ] **Step 15: Commit.** "Carry who sent a command as a box name or a wl.works member, on the wire and in the record (b2b spec §6)". Body: schema 14; nobody is `None`; record rows hold `actor.to_map`'s form; a pre-b2b string still reads.

---

### Task 3: The two kinds shown apart, and the path proved

**Files:**
- Modify: `wl_xcon/web.py` (`_who`, its CSS, and every `by` it renders)
- Modify: the docs, as listed in Step 5
- Test: `tests/test_web.py`, `tests/test_cli.py`, `tests/test_serve.py`

**Interfaces:**
- Consumes: Task 2's typed `by` in telemetry.
- Produces: `web._who(by: Actor | None) -> str`, the one way the page shows who.

- [ ] **Step 1: Write the failing tests.** In `tests/test_web.py`, using the file's frame builder (`tests/_frames.py`; read it first and use its own names):

```python
def test_a_member_and_a_box_name_render_apart():
    from wl_xcon.actor import Box, Member
    from wl_xcon.web import _who

    member = Member(name="Jake Westerberg", account="u", issuer="https://wl.works/api/auth", token_id="j")
    assert 'class="who-m"' in _who(member) and "(wl.works)" in _who(member)
    assert 'class="who-b"' in _who(Box("jake")) and "(box, unverified)" in _who(Box("jake"))
    assert _who(None) == ""


def test_a_box_name_typed_to_look_like_a_member_still_renders_as_a_box():
    """Review Focus 2."""
    from wl_xcon.actor import Box
    from wl_xcon.web import _who

    shown = _who(Box("Jake Westerberg (wl.works)"))
    assert 'class="who-b"' in shown and 'class="who-m"' not in shown
    assert shown.endswith('<span class="nm">(box, unverified)</span></span>')
```

  Then, for each pane that names who: the changes feed (a `Control`, a `Staged`, a `Refused`) and the scheduled-stop cell. Build a frame holding one member and one box actor and assert each pane's HTML holds `who-m` for the first and `who-b` for the second.

  In `tests/test_cli.py`, for `render` (**Review Focus 2**): a frame whose control's `by` is `Box("Jake Westerberg (wl.works)")` renders `by Jake Westerberg (wl.works) (box, unverified)`.

- [ ] **Step 2: Run them to see them fail.** `python3 -m pytest -q -p no:cacheprovider tests/test_web.py tests/test_cli.py -k "who or render or member"`.

- [ ] **Step 3: Implement.** In `wl_xcon/web.py`:

```python
def _who(by: Actor | None) -> str:
    """Who sent a control, as the page shows it (b2b spec §6): a member as *NAME
    (wl.works)*, a box name set apart as *NAME (box, unverified)*, so a typed name
    dressed as a member's still reads as typed; nothing for nobody."""
    if by is None:
        return ""
    if isinstance(by, Member):
        return f'<span class="who-m">{_e(by.name)} <span class="nm">(wl.works)</span></span>'
    return f'<span class="who-b">{_e(by.name)} <span class="nm">(box, unverified)</span></span>'
```

  Replace each `_e(x.by)` with `_who(x.by)`: the feed's staged, control and refusal lines, the parameter card's staged line, the idle refusals and the scheduled cell. Add to `_CSS`: `.who-b{font-style:italic}`. In `_changes`, `who = f" · {_e(control.by)}" if control.by else ""` becomes `who = f" · {_who(control.by)}" if control.by is not None else ""`.

- [ ] **Step 4: The path, end to end.** In `tests/test_serve.py`, add a test with the file's `_Taskd` (a real `wlx taskd` and `wlx serve`).
  - Open a session from the page with the box's name. Run a short run with a pause, a setting change, a hand reward and a mark with a note. End with a return.
  - Then read every `*.jsonl` file in the session folder and assert that every `by` and `acknowledged_by` value is a dict or `None`, never a string.

    ```python
        for path in sorted(folder.glob("*.jsonl")):
            for line in path.read_text().splitlines():
                row = json.loads(line)
                for key in ("by", "acknowledged_by"):
                    assert not isinstance(row.get(key), str), (path.name, key, row.get(key))
                for item in row.get("preflight") or ():
                    assert not isinstance(item.get("acknowledged_by"), str), (path.name, item)
    ```

    Read `_Taskd` and the file's existing open/run/end tests (`grep -n '_open_body\|_start_body\|_end_body' tests/test_serve.py`) and drive it the same way.

- [ ] **Step 5: The docs.**
  - `docs/design/architecture.md`: where the record's files are described, say each row's `by` is an actor's map since b2b (`actor.to_map`), and a string in an older record. In the welfare-critical paragraph, nothing changes.
  - `docs/superpowers/specs/2026-08-31-S9a-console-design.md` §6: a dated note under "`Actor` is two types": "Built 2026-10-02 (b2b slice 1) as `actor.Box` and `actor.Member`; `Local(box credential)` became `Box(name)`, a name typed at the rig PC, since the box has no credential of its own beyond being the rig PC."

- [ ] **Step 6: Run the whole suite**, then prove each new test can fail. Make `_who` render both kinds with one class, and see both web tests fail. Make `render` print `by.name` without `shown`, and see the cli test fail. Restore each file and check it with `cmp`.

- [ ] **Step 7: Commit.** "Show a wl.works member and a box name apart, and prove the record holds no string actor".

---

### Task 4: Slice 1's proof and review

- [ ] **Step 1:** Run the full suite three times in a row with `WLX_REQUIRE_PREPROC=1`, and record each count.
- [ ] **Step 2: Sweep every new and changed function.** Use `git archive` copies, one lane per module, each with its `wl-preproc` link pointing at the export:

      python3 tools/mutate.py --all --only <names> --returns <RETURNS value> wl_xcon/<module>.py

  - `actor`: all of it.
  - `link`: `_actor`, `_sender`, `_refused_in`, `_encode_command`, `_command_from`, `_mark`, `_refusals_out`, `_telemetry_out`, `_telemetry_from`, `_idle_from`, `decode`, `drain`.
  - `record`: `welfare_note`, `parameter_change`, `control`, `refusal`, `run`.
  - `welfare`: `amend_mark`, `confirm_already_today`.
  - `preflight`: `rows`.
  - `resume`: the function holding line 199.
  - `cli`: `render` and every function Step 8 changed.
  - `serve`: `_person`, `parse_command`.
  - `web`: `_who`, `_changes`, `_scheduled`, `_idle_refusals`, `_params`.
  - `taskd`, `service`, `marks`, `stranded`, `bounds`: each function whose body changed (`git diff -U0 main -- wl_xcon/<module>.py` names them).

  Read every line. `N failed` is a catch. A timeout gets an unbounded rerun (`mutate._neuter_source` in a `git archive` copy, then pytest there). A survivor gets a test.
- [ ] **Step 3: The PI's review (spec §10 item 5), in the UI** (`AskUserQuestion`), as numbered items in plain terms. Give the welfare-critical lines this slice changed, one line each, from `git diff main -- wl_xcon/welfare.py wl_xcon/bounds.py wl_xcon/marks.py wl_xcon/stranded.py` and the listed functions in `taskd.py`, `service.py`, `cli.py` and `link.py`. Each changes `by`'s type or its written form, and none changes a rule. Record the answer in the spec's §10.
- [ ] **Step 4: Push the branch, read its CI run job by job** (pytest on 3.11-3.13, the mutation gate's lines), and fast-forward `main` once it is green and approved. Write the CHECKPOINT entry for slice 1. Slice 2 starts from that `main` on branch `b2b-signin`.

---

# Slice 2 — signing in

### Task 5: The dependencies, and keeping them out of everything else

**Files:**
- Modify: `pyproject.toml`, `docs/design/decisions/ADR-0004-license.md`, `.github/workflows/ci.yml`
- Modify: `tests/_transport_import_blocker.py`, `tests/test_no_transport_leak.py`

**Interfaces:**
- Produces: the `signin` and `browser` extras, and a CI pytest job that installs Chromium and sets `WLX_REQUIRE_BROWSER=1`.

- [ ] **Step 1: Extend the blocker test first.** In `tests/_transport_import_blocker.py`, block `jwt` and `cryptography` beside `zmq` and `msgpack`, printing `BLOCKED: import jwt raised` and `BLOCKED: import cryptography raised` as it does for the other two. In `tests/test_no_transport_leak.py`, assert those two lines, and rename the test to `test_link_taskd_cli_health_serve_and_web_import_with_transport_and_signin_unavailable`. `serve` must import with `jwt` blocked, which proves it imports `signin` only when `--https` is given.
- [ ] **Step 2: Run it.** `python3 -m pytest -q -p no:cacheprovider tests/test_no_transport_leak.py`. Expected: PASS, since nothing imports `jwt` yet. Prove it can fail: add `import jwt` at the top of `wl_xcon/serve.py`, see the test fail naming `serve`, and restore the file.
- [ ] **Step 3: `pyproject.toml`.** Add, with comments in the file's style:

```toml
# What `wlx serve --https` needs to check a wl.works sign-in (P4d-2b b2b spec §5, §9):
# PyJWT verifies the RS256 access token, and its `crypto` extra brings `cryptography`.
# **2.10.1, not 2.8**: 2.10.0 compared a string issuer as a substring
# (`payload["iss"] not in issuer`, its `jwt/api_jwt.py`, read 2026-10-02). An extra, and
# imported only by `signin.py`, which `serve` imports only when `--https` is given, so a
# rig that takes no remote control installs neither (`tests/test_no_transport_leak.py`).
signin = ["pyjwt[crypto]>=2.10.1"]
# The page's script driven in a real browser (b2b spec §8; closes XC-186). Tests only:
# never installed on a rig. Its own extra so the mutation jobs, which install `dev`,
# neither download it nor a browser. After installing: `python -m playwright install chromium`.
browser = ["playwright>=1.63"]
```

- [ ] **Step 4: ADR-0004's inventory**, three rows in its table's format:

```markdown
| `pyjwt[crypto]` >= 2.10.1 (signin extra) | MIT (pypi.org/pypi/pyjwt/json `.info.license_expression`, 2.15.1, verified 2026-10-02) | Verifies a wl.works access token offline on the rig: RS256 against wl.works' published keys, audience, issuer and expiry (P4d-2b b2b spec §5). 2.10.1 is the floor because 2.10.0 compared a string issuer as a substring (read from its wheel, 2026-10-02) |
| `cryptography` (via `pyjwt[crypto]`) | Apache-2.0 OR BSD-3-Clause (pypi.org/pypi/cryptography/json `.info.license_expression`, 50.0.2, verified 2026-10-02) | PyJWT's RSA backend; also generates the tests' throwaway keys and certificates |
| `playwright` >= 1.63 (browser extra, tests only) | Apache-2.0 (pypi.org/pypi/playwright/json `.info.license_expression`, 1.63.0, verified 2026-10-02) | Drives the console page's script in headless Chromium (b2b spec §8, XC-186). Never installed on a rig |
```

- [ ] **Step 5: `.github/workflows/ci.yml`.**
  - The pytest job installs `.[dev,contract,console,signin,browser]`, then runs `python -m playwright install --with-deps chromium`, and sets `WLX_REQUIRE_BROWSER: "1"` beside `WLX_REQUIRE_PREPROC`.
  - Both mutation jobs install `.[dev,contract,console,signin]`.
  - Read the file before editing; the three `pip install` lines are at ~77, ~140 and ~198.
- [ ] **Step 6: Run the suite** (`pip install -e ".[dev,contract,console,signin,browser]"` first) and commit: "Add the signin and browser extras, and keep jwt out of everything but signin".

---

### Task 6: `signin.py`, part 1 — the rig page, discovery, keys and the cache

**Files:**
- Create: `wl_xcon/signin.py`
- Create: `tests/_issuer.py` (a fake wl.works: a key, its documents, minted tokens)
- Modify: `tools/mutation_gate.py` (`"signin": "None"`)
- Test: `tests/test_signin.py`

**Interfaces:**
- Produces:
  - `signin.RigPage(name, page, origin, client_id, host)` and `signin.parse_rig_page(text: str) -> RigPage` (raises `ValueError` with a sentence);
  - `signin.Discovery(issuer, authorization_endpoint, token_endpoint, jwks_uri)`, with the property `token_origin`;
  - `signin.fetch_json(url: str, *, context: ssl.SSLContext | None = None) -> dict`;
  - `signin.Checker(*, page: RigPage, issuer: str, cache: Path, fetch=fetch_json)`, with `.load() -> str` (a sentence for the terminal), `.ready -> bool`, `.discovery -> Discovery | None` and `.retry_until_ready(stop: threading.Event) -> None`;
  - `tests/_issuer.Issuer(issuer: str = "https://wl.works/api/auth")`, with `.discovery() -> dict`, `.jwks() -> dict`, `.fetch(url) -> dict` (a `fetch` seam that records `.fetched`) and `.mint(**claims) -> str`.

- [ ] **Step 1: Write `tests/_issuer.py`.** The tests mint tokens the way wl.works does (`createJwtAccessToken`, read 2026-10-02): header `alg` RS256, `typ` `at+jwt` and `kid`; claims `sub`, `aud` (one string), `client_id`, `azp`, `scope`, `iss`, `iat`, `exp`, `jti` and `name`.

```python
"""A fake wl.works for the sign-in tests (b2b spec §8): an RSA key generated at test
time, a discovery document and key set shaped like the live ones read 2026-10-02, and
access tokens minted the way wl.works mints a rig's (`createJwtAccessToken` in
`@better-auth/oauth-provider` 1.7.1: header alg RS256, typ at+jwt, kid; claims sub, aud,
client_id, azp, scope, iss, iat, exp, jti, plus wl.works' `name`). Never on the network."""

from __future__ import annotations

import base64
import secrets
import time

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

ISSUER = "https://wl.works/api/auth"
PAGE = "https://rig-3.wl.works/"
ORIGIN = "https://rig-3.wl.works"
CLIENT = "wl-works-rig-rig-3"


def _b64(number: int) -> str:
    raw = number.to_bytes((number.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


class Issuer:
    def __init__(self, issuer: str = ISSUER, kid: str = "test-key-1") -> None:
        self.issuer = issuer
        self.kid = kid
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.fetched: list[str] = []
        #: Set by a test to make `fetch` raise, as an unreachable wl.works would.
        self.down = False

    def pem(self) -> bytes:
        return self.key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )

    def discovery(self) -> dict:
        return {
            "issuer": self.issuer,
            "authorization_endpoint": f"{self.issuer}/oauth2/authorize",
            "token_endpoint": f"{self.issuer}/oauth2/token",
            "jwks_uri": f"{self.issuer}/jwks",
            "code_challenge_methods_supported": ["S256"],
        }

    def jwks(self, *extra: dict) -> dict:
        numbers = self.key.public_key().public_numbers()
        mine = {"kty": "RSA", "alg": "RS256", "kid": self.kid, "n": _b64(numbers.n), "e": _b64(numbers.e)}
        return {"keys": [mine, *extra]}

    def fetch(self, url: str) -> dict:
        self.fetched.append(url)
        if self.down:
            raise OSError("wl.works is unreachable (test)")
        if url == f"{self.issuer}/.well-known/openid-configuration":
            return self.discovery()
        if url == f"{self.issuer}/jwks":
            return self.jwks()
        raise OSError(f"no such document: {url}")

    def mint(
        self,
        *,
        aud: object = ORIGIN,
        azp: str = CLIENT,
        name: object = "Jake Westerberg",
        sub: object = "user-1",
        jti: object | None = None,
        exp_in: float = 3600,
        iat_in: float = 0,
        iss: str | None = None,
        typ: str = "at+jwt",
        kid: str | None = None,
        drop: tuple = (),
        key=None,
        algorithm: str = "RS256",
    ) -> str:
        now = time.time()
        claims = {
            "sub": sub, "aud": aud, "client_id": azp, "azp": azp, "scope": "offline_access",
            "iss": self.issuer if iss is None else iss, "iat": int(now + iat_in),
            "exp": int(now + exp_in), "jti": jti or secrets.token_hex(16), "name": name,
        }
        for claim in drop:
            claims.pop(claim)
        headers = {"typ": typ, "kid": self.kid if kid is None else kid}
        return jwt.encode(claims, self.pem() if key is None else key, algorithm=algorithm, headers=headers)
```

- [ ] **Step 2: Write the failing tests** in `tests/test_signin.py`:

```python
"""`wl_xcon/signin.py`: checking a wl.works sign-in at a rig's page (b2b spec §3, §5)."""

from __future__ import annotations

import json

import pytest

pytest.importorskip("jwt")

from _issuer import CLIENT, ISSUER, ORIGIN, PAGE, Issuer
from wl_xcon import signin


def test_a_rig_page_entry_is_read_as_wl_works_reads_it():
    page = signin.parse_rig_page("rig-3=https://rig-3.wl.works/")
    assert (page.name, page.page, page.origin, page.client_id, page.host) == (
        "rig-3", "https://rig-3.wl.works/", "https://rig-3.wl.works", CLIENT, "rig-3.wl.works",
    )


def test_a_page_with_a_port_keeps_it_in_the_origin_and_the_host_and_443_does_not():
    assert signin.parse_rig_page("rig-3=https://127.0.0.1:8443/").origin == "https://127.0.0.1:8443"
    assert signin.parse_rig_page("rig-3=https://127.0.0.1:8443/").host == "127.0.0.1:8443"
    assert signin.parse_rig_page("rig-3=https://Rig-3.WL.works:443/").origin == "https://rig-3.wl.works"


@pytest.mark.parametrize(
    "text, says",
    [
        ("https://rig-3.wl.works/", '"="'),
        ("Rig3=https://rig-3.wl.works/", "lower-case"),
        ("rig--3=https://rig-3.wl.works/", "lower-case"),
        ("r" * 33 + "=https://rig-3.wl.works/", "lower-case"),
        ("rig-3=http://rig-3.wl.works/", "https"),
        ("rig-3=https://u:p@rig-3.wl.works/", "user name"),
        ("rig-3=https://rig-3.wl.works/#x", "fragment"),
        ("rig-3=https://rig-3.wl.works/a,b", "comma"),
        ("rig-3=not a url", "https"),
    ],
)
def test_a_rig_page_wl_works_would_refuse_is_refused_here(text, says):
    with pytest.raises(ValueError) as refused:
        signin.parse_rig_page(text)
    assert says in str(refused.value)


def _checker(tmp_path, issuer: Issuer) -> signin.Checker:
    return signin.Checker(
        page=signin.parse_rig_page(f"rig-3={PAGE}"),
        issuer=ISSUER,
        cache=tmp_path / "wl-works.json",
        fetch=issuer.fetch,
    )


def test_load_reads_discovery_and_keys_from_wl_works_and_caches_both(tmp_path):
    issuer = Issuer()
    checker = _checker(tmp_path, issuer)
    said = checker.load()
    assert checker.ready and "from wl.works" in said
    assert checker.discovery.token_endpoint == f"{ISSUER}/oauth2/token"
    assert checker.discovery.token_origin == "https://wl.works"
    cached = json.loads((tmp_path / "wl-works.json").read_text())
    assert cached["discovery"]["issuer"] == ISSUER and cached["jwks"]["keys"]


def test_load_falls_back_to_the_cache_when_wl_works_is_unreachable(tmp_path):
    issuer = Issuer()
    _checker(tmp_path, issuer).load()
    issuer.down = True
    checker = _checker(tmp_path, issuer)
    said = checker.load()
    assert checker.ready and "cache" in said


def test_with_no_wl_works_and_no_cache_the_rig_holds_no_keys(tmp_path):
    issuer = Issuer()
    issuer.down = True
    checker = _checker(tmp_path, issuer)
    said = checker.load()
    assert not checker.ready and checker.discovery is None
    assert signin.NO_KEYS in said


def test_a_discovery_naming_another_issuer_is_refused_and_not_cached(tmp_path):
    issuer = Issuer(issuer="https://wl.works")  # a different issuer string
    checker = signin.Checker(
        page=signin.parse_rig_page(f"rig-3={PAGE}"),
        issuer=ISSUER,
        cache=tmp_path / "wl-works.json",
        fetch=lambda url: issuer.discovery() if "openid" in url else issuer.jwks(),
    )
    said = checker.load()
    assert not checker.ready and signin.NO_KEYS in said
    assert not (tmp_path / "wl-works.json").exists()


def test_a_cache_naming_another_issuer_is_not_used(tmp_path):
    (tmp_path / "wl-works.json").write_text(
        json.dumps({"discovery": {**Issuer().discovery(), "issuer": "https://elsewhere"}, "jwks": Issuer().jwks()})
    )
    issuer = Issuer()
    issuer.down = True
    checker = _checker(tmp_path, issuer)
    checker.load()
    assert not checker.ready


def test_only_rsa_signing_keys_are_kept(tmp_path):
    issuer = Issuer()
    extra = (
        {"kty": "EC", "kid": "ec", "crv": "P-256", "x": "AA", "y": "AA"},
        {**issuer.jwks()["keys"][0], "kid": "enc", "use": "enc"},
        {**issuer.jwks()["keys"][0], "kid": "hs", "alg": "HS256"},
    )
    checker = signin.Checker(
        page=signin.parse_rig_page(f"rig-3={PAGE}"), issuer=ISSUER, cache=tmp_path / "c.json",
        fetch=lambda url: issuer.discovery() if "openid" in url else issuer.jwks(*extra),
    )
    checker.load()
    assert checker.key_ids() == {issuer.kid}


def test_fetch_json_refuses_plain_http():
    with pytest.raises(ValueError):
        signin.fetch_json("http://wl.works/api/auth/jwks")
```

  Add a test that `retry_until_ready` loads once wl.works answers: build a checker on a down issuer, start `retry_until_ready(stop)` on a thread with `signin.RETRY_EVERY_S` monkeypatched to `0.05`, set `issuer.down = False`, and wait up to 5 s for `checker.ready`. Then set `stop` and join.

  Add one test that runs `fetch_json` against a real loopback https server, with a test certificate authority passed as `context`. Generate the CA and the leaf with `cryptography` in a helper `tests/_tls.py`; Task 8 needs it too.

```python
"""Throwaway TLS material for tests (b2b spec §8): a CA, and a leaf for 127.0.0.1
signed by it, written as PEM files. Never committed, never reused across runs."""

from __future__ import annotations

import datetime
import ipaddress
import ssl
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


def _name(text: str) -> x509.Name:
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, text)])


def material(directory: Path) -> dict[str, Path]:
    """`ca`, `cert` and `key` PEM paths under `directory`."""
    now = datetime.datetime.now(datetime.timezone.utc)
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ca = (
        x509.CertificateBuilder()
        .subject_name(_name("wl-xcon test CA")).issuer_name(_name("wl-xcon test CA"))
        .public_key(ca_key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5)).not_valid_after(now + datetime.timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(ca_key, hashes.SHA256())
    )
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    leaf = (
        x509.CertificateBuilder()
        .subject_name(_name("127.0.0.1")).issuer_name(ca.subject)
        .public_key(key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5)).not_valid_after(now + datetime.timedelta(days=1))
        .add_extension(
            x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address("127.0.0.1")), x509.DNSName("localhost")]),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256())
    )
    paths = {"ca": directory / "ca.pem", "cert": directory / "cert.pem", "key": directory / "key.pem"}
    paths["ca"].write_bytes(ca.public_bytes(serialization.Encoding.PEM))
    paths["cert"].write_bytes(leaf.public_bytes(serialization.Encoding.PEM))
    paths["key"].write_bytes(
        key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    )
    return paths


def client_context(ca: Path) -> ssl.SSLContext:
    return ssl.create_default_context(cafile=str(ca))
```

- [ ] **Step 3: Run them to see them fail** (no `wl_xcon.signin`).

- [ ] **Step 4: Write `wl_xcon/signin.py`, part 1.**

```python
"""Checking a wl.works sign-in at a rig's page (P4d-2b b2b).

Spec: `docs/superpowers/specs/2026-10-02-p4d2b-b2b-remote-signin-design.md` §3-§5,
against wl-works' rig sign-in as built and deployed on 2026-10-02 (`4eb2c568`; its
`src/lib/rigs.ts`, `src/lib/rig-sign-in.ts` and `src/lib/rig-cors.ts`, and
`createJwtAccessToken` in `@better-auth/oauth-provider` 1.7.1, read that day).

**Used only by `wlx serve`, and only when `--https` is given**, which is the only time
`jwt` and `cryptography` (the `signin` extra) are imported
(`tests/test_no_transport_leak.py` proves `serve` imports without them).

**Offline by design** (the PI, 2026-09-27): a token is checked against wl.works'
published keys, cached here, never by asking wl.works about it. So a token already
issued keeps working through a wl.works outage, and through a sign-out at wl.works,
until its hour ends; a sign-out at this page is refused here at once (`sign_out`).
"""

from __future__ import annotations

import http.client
import json
import os
import re
import ssl
import tempfile
import threading
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

import jwt

from wl_xcon import actor as actors

#: wl.works' client id for a rig is this and the rig's name (`RIG_CLIENT_PREFIX`,
#: wl-works `src/lib/rigs.ts`, read 2026-10-02).
CLIENT_PREFIX = "wl-works-rig-"
#: A rig's name, as wl.works' `parseRigPages` allows it.
_NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
NAME_MAX = 32
#: Housekeeping, not measurements (spec §5): the outbound fetch's timeout, the largest
#: document read, and how often an unknown key id may fetch the key set again, and a
#: rig with no keys retries.
FETCH_TIMEOUT_S = 5.0
FETCH_LIMIT = 65536
REFETCH_EVERY_S = 60.0
RETRY_EVERY_S = 60.0
#: The refusal a rig with no keys gives a command from the network (spec §5).
NO_KEYS = "the rig has not reached wl.works to check sign-ins; use the rig PC"


@dataclass(frozen=True, slots=True)
class RigPage:
    """This rig's entry in wl.works' `RIG_PAGES`: its name, its page's address exactly
    as configured (the one return address wl.works compares as a string), the page's
    origin (the token's audience), wl.works' client id for it, and the `Host` a
    browser sends for it."""

    name: str
    page: str
    origin: str
    client_id: str
    host: str


def parse_rig_page(text: str) -> RigPage:
    """`--rig-page NAME=URL`, by wl.works' own `parseRigPages` rules, so a page wl.works
    would refuse to configure is refused here too. Raises `ValueError` with a sentence."""
    name, eq, page = text.partition("=")
    shape = f'--rig-page takes NAME=URL, as wl.works\' RIG_PAGES does, such as "rig-3=https://rig-3.wl.works/"'
    if not eq:
        raise ValueError(f'{shape}; {text!r} has no "="')
    if not _NAME.fullmatch(name) or len(name) > NAME_MAX:
        raise ValueError(
            f"{shape}; its name is lower-case letters and digits, joined by single hyphens, "
            f"at most {NAME_MAX} long"
        )
    if "," in page:
        raise ValueError(f"{shape}; its address has a comma, which wl.works refuses")
    parts = urlsplit(page)
    if parts.scheme != "https" or not parts.hostname:
        raise ValueError(f"{shape}; its address must be an absolute https address")
    if parts.username is not None or parts.password is not None:
        raise ValueError(f"{shape}; its address carries a user name or password")
    if parts.fragment or "#" in page:
        raise ValueError(f"{shape}; its address has a fragment (#)")
    host = parts.hostname.lower()
    if ":" in host:
        host = f"[{host}]"
    port = parts.port
    netloc = host if port in (None, 443) else f"{host}:{port}"
    return RigPage(name, page, f"https://{netloc}", CLIENT_PREFIX + name, netloc)


@dataclass(frozen=True, slots=True)
class Discovery:
    """What this rig reads from wl.works' discovery document (spec §5)."""

    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    jwks_uri: str

    @property
    def token_origin(self) -> str:
        """The token endpoint's origin: the one outside address the page may `fetch`."""
        parts = urlsplit(self.token_endpoint)
        return f"{parts.scheme}://{parts.netloc}"


def _discovery(data: object, issuer: str) -> Discovery:
    """The document's four fields, checked. **Its issuer must be the configured one,
    exactly** (OpenID Connect Discovery 1.0 §4.3). Raises `ValueError`."""
    if not isinstance(data, dict) or data.get("issuer") != issuer:
        raise ValueError(f"wl.works' discovery document does not name the issuer {issuer!r}")
    fields = ("authorization_endpoint", "token_endpoint", "jwks_uri")
    for field in fields:
        value = data.get(field)
        if not isinstance(value, str) or urlsplit(value).scheme != "https":
            raise ValueError(f"wl.works' discovery document's {field} is not an https address")
    return Discovery(issuer, *(data[field] for field in fields))


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A discovery document or key set that redirects is refused, never followed: a
    redirect could leave https."""

    def redirect_request(self, *args, **kwargs):
        return None


def fetch_json(url: str, *, context: ssl.SSLContext | None = None) -> dict:
    """GET one JSON object over https, with the system's certificate checks (or
    `context`'s, in a test), no redirects, `FETCH_TIMEOUT_S` and at most `FETCH_LIMIT`
    bytes. Raises `ValueError`, `OSError` or `http.client.HTTPException`."""
    if urlsplit(url).scheme != "https":
        raise ValueError(f"{url!r} is not an https address")
    opener = urllib.request.build_opener(
        _NoRedirect, urllib.request.HTTPSHandler(context=context or ssl.create_default_context())
    )
    with opener.open(urllib.request.Request(url, headers={"Accept": "application/json"}), timeout=FETCH_TIMEOUT_S) as response:
        if response.status != 200:
            raise ValueError(f"{url!r} answered {response.status}")
        body = response.read(FETCH_LIMIT + 1)
    if len(body) > FETCH_LIMIT:
        raise ValueError(f"{url!r} answered more than {FETCH_LIMIT} bytes")
    data = json.loads(body)
    if not isinstance(data, dict):
        raise ValueError(f"{url!r} did not answer a JSON object")
    return data


def _keys(jwks: object) -> dict:
    """Key id → RSA public key, for every key a rig token can be signed with: RSA, its
    `use` absent or `sig`, its `alg` absent or RS256. Anything else is ignored."""
    if not isinstance(jwks, dict) or not isinstance(jwks.get("keys"), list):
        raise ValueError("wl.works' key set holds no list of keys")
    keys = {}
    for jwk in jwks["keys"]:
        if not isinstance(jwk, dict) or jwk.get("kty") != "RSA":
            continue
        if jwk.get("use") not in (None, "sig") or jwk.get("alg") not in (None, "RS256"):
            continue
        kid = jwk.get("kid")
        if not isinstance(kid, str) or not kid:
            continue
        try:
            keys[kid] = jwt.PyJWK(jwk, algorithm="RS256").key
        except (jwt.exceptions.PyJWTError, ValueError, TypeError):
            continue
    return keys


def _save(path: Path, discovery: dict, jwks: dict) -> None:
    """Both documents to `path`, replaced whole, so a crash mid-write leaves the old one."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as out:
            json.dump({"discovery": discovery, "jwks": jwks}, out)
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


class Checker:
    """This rig's view of wl.works: its discovery, its keys, and the tokens signed out
    here (spec §5). Thread-safe: every HTTP thread of `wlx serve` checks through one."""

    def __init__(self, *, page: RigPage, issuer: str, cache: Path, fetch=fetch_json) -> None:
        self.page = page
        self.issuer = issuer
        self.cache = cache
        self._fetch = fetch
        self._lock = threading.Lock()
        self._discovery: Discovery | None = None
        self._keys: dict = {}
        self._last_refetch = float("-inf")
        #: Signed-out token ids and when each token expires (spec §5). Memory only.
        self._signed_out: dict[str, float] = {}

    @property
    def discovery(self) -> Discovery | None:
        with self._lock:
            return self._discovery

    @property
    def ready(self) -> bool:
        with self._lock:
            return self._discovery is not None and bool(self._keys)

    def key_ids(self) -> set[str]:
        with self._lock:
            return set(self._keys)

    def load(self) -> str:
        """Discovery and keys from wl.works, else from the cache; a sentence saying which,
        for `wlx serve`'s terminal."""
        try:
            document = self._fetch(self.issuer.rstrip("/") + "/.well-known/openid-configuration")
            discovery = _discovery(document, self.issuer)
            jwks = self._fetch(discovery.jwks_uri)
            keys = _keys(jwks)
            if not keys:
                raise ValueError("wl.works' key set holds no RS256 signing key")
        except (OSError, ValueError, http.client.HTTPException) as live:
            return self._from_cache(f"{type(live).__name__}: {live}")
        _save(self.cache, document, jwks)
        with self._lock:
            self._discovery, self._keys = discovery, keys
        return f"sign-in keys from wl.works ({len(keys)})"

    def _from_cache(self, why: str) -> str:
        try:
            cached = json.loads(self.cache.read_text(encoding="utf-8"))
            discovery = _discovery(cached["discovery"], self.issuer)
            keys = _keys(cached["jwks"])
        except (OSError, ValueError, KeyError, TypeError):
            return f"{NO_KEYS} (wl.works: {why}; no usable cache at {self.cache})"
        if not keys:
            return f"{NO_KEYS} (wl.works: {why}; the cache holds no key)"
        with self._lock:
            self._discovery, self._keys = discovery, keys
        return f"sign-in keys from the cache, {len(keys)} (wl.works: {why})"

    def retry_until_ready(self, stop: threading.Event) -> None:
        """Every `RETRY_EVERY_S`, load again, until there are keys or `stop` is set."""
        while not self.ready and not stop.wait(RETRY_EVERY_S):
            self.load()
```

  Add `"signin": "None",` to `RETURNS` in `tools/mutation_gate.py`.

- [ ] **Step 5: Run the tests to see them pass.** `python3 -m pytest -q -p no:cacheprovider tests/test_signin.py`.
- [ ] **Step 6: Prove the new tests can fail.**
  - Make `_discovery` skip its issuer check, and see the two issuer tests fail.
  - Make `_keys` keep every key, and see `test_only_rsa_signing_keys_are_kept` fail.
  - Make `parse_rig_page` keep the port when it is 443, and see the origin test fail.
  - Restore each, check with `cmp`, and delete `wl_xcon/__pycache__`.
- [ ] **Step 7: Commit.** "Read this rig's page entry, wl.works' discovery and its keys, cached (b2b spec §5)".

---

### Task 7: `signin.py`, part 2 — checking a token, and signing one out

**Files:**
- Modify: `wl_xcon/signin.py`
- Test: `tests/test_signin.py`

**Interfaces:**
- Consumes: Task 6's `Checker`, `tests/_issuer.Issuer.mint`.
- Produces:
  - `signin.Refused(Exception)`, with `.said: str` and `.reason: str`;
  - `signin.Accepted(member: actor.Member, expires_at: float)`;
  - `Checker.check(authorization: str | None) -> Accepted` (raises `Refused`);
  - `Checker.sign_out(authorization: str | None) -> None`;
  - the sentence constants `NO_TOKEN`, `SIGNED_OUT`, `EXPIRED`, `OTHER_RIG`, `CLOCK`, `NOT_ACCEPTED`, with `NO_KEYS` from Task 6;
  - `LEEWAY_S = 60`, `TOKEN_LIMIT = 8192`, `ACCESS_TOKEN_TYPES`.

- [ ] **Step 1: Write the failing tests**, appended to `tests/test_signin.py`:

```python
from wl_xcon.actor import Member


def _ready(tmp_path, issuer=None):
    issuer = issuer or Issuer()
    checker = _checker(tmp_path, issuer)
    checker.load()
    return checker, issuer


def _bearer(token: str) -> str:
    return f"Bearer {token}"


def test_a_good_token_names_its_member(tmp_path):
    checker, issuer = _ready(tmp_path)
    accepted = checker.check(_bearer(issuer.mint(jti="j-1")))
    assert accepted.member == Member(name="Jake Westerberg", account="user-1", issuer=ISSUER, token_id="j-1")
    assert accepted.expires_at > 0


def _refused(checker, header) -> signin.Refused:
    with pytest.raises(signin.Refused) as refused:
        checker.check(header)
    return refused.value


@pytest.mark.parametrize("header", [None, "", "Basic abc", "Bearer", "Bearer " + "x" * 9000])
def test_no_token_is_refused_asking_for_a_sign_in(tmp_path, header):
    checker, _ = _ready(tmp_path)
    refused = _refused(checker, header)
    assert (refused.reason, refused.said) == ("no_token", signin.NO_TOKEN)


@pytest.mark.parametrize(
    "mint, reason",
    [
        (dict(exp_in=-120), "expired"),
        (dict(iat_in=600), "clock"),
        (dict(aud="https://rig-4.wl.works"), "other_rig"),
        (dict(aud=[ORIGIN, "https://wl.works/api/auth/oauth2/userinfo"]), "other_rig"),
        (dict(azp="wl-works-rig-rig-4"), "other_rig"),
        (dict(iss="https://wl.works"), "not_accepted"),
        (dict(iss="https://wl.works/api/auth/"), "not_accepted"),
        (dict(typ="JWT"), "not_accepted"),
        (dict(kid="nobody"), "not_accepted"),
        (dict(drop=("jti",)), "not_accepted"),
        (dict(drop=("sub",)), "not_accepted"),
        (dict(name=""), "not_accepted"),
        (dict(name=None), "not_accepted"),
        (dict(name="x" * 201), "not_accepted"),
    ],
)
def test_each_check_refuses_on_its_own(tmp_path, mint, reason):
    checker, issuer = _ready(tmp_path)
    assert _refused(checker, _bearer(issuer.mint(**mint))).reason == reason


def test_a_token_signed_by_another_key_is_refused(tmp_path):
    checker, issuer = _ready(tmp_path)
    forger = Issuer()
    assert _refused(checker, _bearer(forger.mint(kid=issuer.kid))).reason == "not_accepted"


def _hs256(claims: dict, secret: bytes, kid: str) -> str:
    """An HS256 token built by hand: PyJWT itself refuses to use a PEM public key as an
    HMAC secret, so the attack has to be assembled the way an attacker would."""
    import base64
    import hashlib
    import hmac

    def b64(raw: bytes) -> bytes:
        return base64.urlsafe_b64encode(raw).rstrip(b"=")

    head = b64(json.dumps({"alg": "HS256", "typ": "at+jwt", "kid": kid}).encode())
    body = b64(json.dumps(claims).encode())
    signature = b64(hmac.new(secret, head + b"." + body, hashlib.sha256).digest())
    return (head + b"." + body + b"." + signature).decode("ascii")


def test_alg_none_and_hs256_keyed_on_the_public_key_are_refused(tmp_path):
    """The algorithm-confusion attacks: an unsigned token, and an HMAC whose secret is
    the published public key."""
    from cryptography.hazmat.primitives import serialization

    checker, issuer = _ready(tmp_path)
    public = issuer.key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    claims = jwt.decode(issuer.mint(), options={"verify_signature": False})
    unsigned = jwt.encode(claims, None, algorithm="none", headers={"typ": "at+jwt", "kid": issuer.kid})
    assert _refused(checker, _bearer(unsigned)).reason == "not_accepted"
    assert _refused(checker, _bearer(_hs256(claims, public, issuer.kid))).reason == "not_accepted"


def test_an_unknown_key_id_fetches_the_key_set_again_at_most_once_a_minute(tmp_path, monkeypatch):
    checker, issuer = _ready(tmp_path)
    fetched = len(issuer.fetched)
    _refused(checker, _bearer(issuer.mint(kid="new")))
    _refused(checker, _bearer(issuer.mint(kid="newer")))
    assert len(issuer.fetched) == fetched + 1


def test_a_key_wl_works_rotated_in_is_picked_up(tmp_path):
    checker, issuer = _ready(tmp_path)
    issuer.kid = "rotated"
    assert checker.check(_bearer(issuer.mint())).member.name == "Jake Westerberg"


def test_a_signed_out_token_is_refused_here_and_another_is_not(tmp_path):
    checker, issuer = _ready(tmp_path)
    first, second = issuer.mint(jti="j-1"), issuer.mint(jti="j-2")
    checker.sign_out(_bearer(first))
    assert _refused(checker, _bearer(first)).reason == "signed_out"
    assert checker.check(_bearer(second)).member.token_id == "j-2"


def test_signing_out_a_token_that_does_not_check_out_does_nothing(tmp_path):
    checker, issuer = _ready(tmp_path)
    checker.sign_out("Bearer junk")
    checker.sign_out(None)
    assert checker.check(_bearer(issuer.mint())).member.name == "Jake Westerberg"


def test_with_no_keys_every_token_is_refused_saying_so(tmp_path):
    issuer = Issuer()
    issuer.down = True
    checker = _checker(tmp_path, issuer)
    checker.load()
    refused = _refused(checker, _bearer(issuer.mint()))
    assert (refused.reason, refused.said) == ("no_keys", signin.NO_KEYS)


def test_no_refusal_echoes_the_token(tmp_path):
    checker, issuer = _ready(tmp_path)
    token = issuer.mint(exp_in=-120)
    refused = _refused(checker, _bearer(token))
    assert token not in refused.said and token not in str(refused)
```

  `import jwt` at the top of the file, after the `importorskip`. The rotated-key test needs the issuer's `fetch` to serve its current `kid`; `Issuer.jwks` already reads `self.kid`.

- [ ] **Step 2: Run them to see them fail.**

- [ ] **Step 3: Implement**, appended to `wl_xcon/signin.py`:

```python
#: Seconds of clock leeway on `exp` and `iat`. Housekeeping (spec §5), not a
#: measurement: the rig keeps time from wl-works' NTP server (ADR-0009).
LEEWAY_S = 60
#: The longest `Authorization` value read, in bytes. A bound on one header's reach,
#: not a rule about wl.works: its tokens are about a kilobyte.
TOKEN_LIMIT = 8192
#: wl.works' access-token type (`JWT_ACCESS_TOKEN_TYPE`), and RFC 9068 §2.1's long form.
ACCESS_TOKEN_TYPES = frozenset({"at+jwt", "application/at+jwt"})

#: The refusals (spec §5): each a sentence for the page, and a word for its script.
NO_TOKEN = "sign in with wl.works to use the controls"
SIGNED_OUT = "this sign-in was signed out here; sign in again"
EXPIRED = "your sign-in has expired; sign in again"
OTHER_RIG = "this sign-in is for another rig"
CLOCK = "the rig's clock and this sign-in disagree; check the rig's time"
NOT_ACCEPTED = "this is not a wl.works sign-in the rig accepts"


class Refused(Exception):
    """A token this rig does not accept: `said` for a person, `reason` for the page's
    script (the plan's Ruling 8). Never carries the token."""

    def __init__(self, reason: str, said: str) -> None:
        super().__init__(said)
        self.reason = reason
        self.said = said


@dataclass(frozen=True, slots=True)
class Accepted:
    """A token that checked out: who it names, and when it expires (POSIX seconds)."""

    member: actors.Member
    expires_at: float


def _bearer(authorization: str | None) -> str:
    if not authorization or len(authorization) > TOKEN_LIMIT:
        raise Refused("no_token", NO_TOKEN)
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise Refused("no_token", NO_TOKEN)
    return token.strip()


def _claim(claims: dict, name: str) -> str:
    value = claims.get(name)
    if not isinstance(value, str) or not value.strip() or len(value) > actors.TEXT_LIMIT or not value.isprintable():
        raise Refused("not_accepted", NOT_ACCEPTED)
    return value
```

  And these methods on `Checker`:

```python
    def check(self, authorization: str | None) -> Accepted:
        """Spec §5's checks, in its order. Raises `Refused`."""
        token = _bearer(authorization)
        with self._lock:
            discovery = self._discovery
            ready = discovery is not None and bool(self._keys)
        if not ready:
            raise Refused("no_keys", NO_KEYS)
        try:
            head = jwt.get_unverified_header(token)
        except jwt.exceptions.PyJWTError:
            raise Refused("not_accepted", NOT_ACCEPTED) from None
        typ = head.get("typ")
        if head.get("alg") != "RS256" or not isinstance(typ, str) or typ.lower() not in ACCESS_TOKEN_TYPES:
            raise Refused("not_accepted", NOT_ACCEPTED)
        key = self._key(head.get("kid"))
        try:
            claims = jwt.decode(
                token,
                key,
                algorithms=["RS256"],
                audience=self.page.origin,
                issuer=discovery.issuer,
                leeway=LEEWAY_S,
                options={"require": ["exp", "iat", "sub", "aud", "iss", "jti"], "strict_aud": True},
            )
        except jwt.exceptions.ExpiredSignatureError:
            raise Refused("expired", EXPIRED) from None
        except jwt.exceptions.ImmatureSignatureError:
            raise Refused("clock", CLOCK) from None
        except jwt.exceptions.InvalidAudienceError:
            raise Refused("other_rig", OTHER_RIG) from None
        except jwt.exceptions.PyJWTError:
            raise Refused("not_accepted", NOT_ACCEPTED) from None
        # Again, exactly: PyJWT 2.10.0 compared a string issuer as a substring (spec §5).
        if claims.get("iss") != discovery.issuer:
            raise Refused("not_accepted", NOT_ACCEPTED)
        if claims.get("azp") != self.page.client_id or claims.get("client_id", self.page.client_id) != self.page.client_id:
            raise Refused("other_rig", OTHER_RIG)
        member = actors.Member(
            name=_claim(claims, "name"),
            account=_claim(claims, "sub"),
            issuer=claims["iss"],
            token_id=_claim(claims, "jti"),
        )
        now = time.time()
        with self._lock:
            self._signed_out = {jti: until for jti, until in self._signed_out.items() if until + LEEWAY_S > now}
            if member.token_id in self._signed_out:
                raise Refused("signed_out", SIGNED_OUT)
        return Accepted(member, float(claims["exp"]))

    def _key(self, kid: object):
        """The key `kid` names; an unknown one fetches the key set again, at most once
        every `REFETCH_EVERY_S`, so a key wl.works rotated in is found and junk ids cannot
        make the rig fetch on every request."""
        if not isinstance(kid, str):
            raise Refused("not_accepted", NOT_ACCEPTED)
        with self._lock:
            key = self._keys.get(kid)
            due = time.monotonic() - self._last_refetch >= REFETCH_EVERY_S
            if key is None and due:
                self._last_refetch = time.monotonic()
            discovery = self._discovery
        if key is None and due and discovery is not None:
            try:
                jwks = self._fetch(discovery.jwks_uri)
                keys = _keys(jwks)
            except (OSError, ValueError, http.client.HTTPException):
                keys = {}
            if keys:
                with self._lock:
                    self._keys = keys
                key = keys.get(kid)
        if key is None:
            raise Refused("not_accepted", NOT_ACCEPTED)
        return key

    def sign_out(self, authorization: str | None) -> None:
        """Refuse this token here for the rest of its hour (spec §4, §5). A token that
        does not check out needs no signing out."""
        try:
            accepted = self.check(authorization)
        except Refused:
            return
        with self._lock:
            self._signed_out[accepted.member.token_id] = accepted.expires_at
```

  The rotated-key refetch should also save the new key set to the cache: after a successful refetch, call `_save(self.cache, <the discovery document>, jwks)`. To do that, keep the last discovery document in `self._document` from `load()`, and write both.

- [ ] **Step 4: Run the tests to see them pass.**
- [ ] **Step 5: Prove they can fail, one per check.**
  - Remove the second `iss` comparison, then run with PyJWT 2.10.0 installed in a throwaway venv (`pip install pyjwt[crypto]==2.10.0`), and see the `https://wl.works` case fail. Note in the report that this is the only case that needs 2.10.0.
  - Remove `strict_aud`, and see the list-`aud` case fail.
  - Remove the `azp` check, and see its case fail.
  - Remove the signed-out lookup, and see its test fail.
  - Remove the refetch rate limit, and see the once-a-minute test fail.
  - Restore after each.
- [ ] **Step 6: Commit.** "Check a wl.works access token offline, and refuse one signed out here (b2b spec §5)".

---

### Task 8: The https listener

**Files:**
- Modify: `wl_xcon/serve.py`, `wl_xcon/cli.py` (the `serve` parser)
- Test: `tests/test_serve.py`

**Interfaces:**
- Consumes: `signin.RigPage`, `signin.Checker`, and `tests/_tls.material`.
- Produces:
  - `serve.Remote(page, checker)`, a frozen dataclass;
  - `serve.tls_context(cert: Path, key: Path) -> ssl.SSLContext`;
  - `serve._PageServer(address, handler, context)`;
  - `make_handler(..., remote: Remote | None = None)`;
  - `Server(..., https: tuple[str, int] | None = None, tls: ssl.SSLContext | None = None, remote: Remote | None = None)`, with `page_address`;
  - `serve.TOKEN_OVER_HTTP`;
  - the CLI flags `--https`, `--tls-cert`, `--tls-key`, `--rig-page`, `--wl-works-issuer` and `--wl-works-cache`.

- [ ] **Step 1: Write the failing tests**, in a new section of `tests/test_serve.py` with a helper beside `_served`:

```python
# --- b2b: the https listener --------------------------------------------------------

def _page_served(tmp_path, hub, *, dispatch=None, issuer=None):
    """`make_handler` with a `Remote`, on a real loopback TLS socket: the rig's https
    page as a browser reaches it, with a fake wl.works behind its checker."""
    pytest.importorskip("jwt")
    from _issuer import ISSUER, Issuer
    from _tls import client_context, material
    from wl_xcon import signin
    from wl_xcon.serve import Remote, _PageServer, tls_context

    tls = material(tmp_path)
    port = int(free_endpoints(1)[0].rsplit(":", 1)[1])
    page = signin.parse_rig_page(f"rig-3=https://127.0.0.1:{port}/")
    issuer = issuer or Issuer()
    checker = signin.Checker(page=page, issuer=ISSUER, cache=tmp_path / "wl-works.json", fetch=issuer.fetch)
    checker.load()
    server = _PageServer(
        ("127.0.0.1", port),
        make_handler(hub, token=TOKEN, stale_after_s=30.0, dispatch=dispatch, remote=Remote(page, checker)),
        tls_context(tls["cert"], tls["key"]),
    )
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    return server, thread, port, page, issuer, client_context(tls["ca"])


def _https(port, context, method, path, headers=None, body=b""):
    connection = http.client.HTTPSConnection("127.0.0.1", port, timeout=5, context=context)
    try:
        connection.putrequest(method, path, skip_host=True)
        for name, value in {"Host": f"127.0.0.1:{port}", **(headers or {})}.items():
            connection.putheader(name, value)
        connection.putheader("Content-Length", str(len(body)))
        connection.endheaders(body)
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        connection.close()
```

  Tests, each starting `_page_served` and shutting the server down in `finally`:
  - `GET /` over TLS answers 200 with the page.
  - `GET /?code=SECRETCODE&state=S` answers the page, and its body does not contain `SECRETCODE`.
  - Every response, on both listeners, carries `Referrer-Policy: no-referrer`.
  - The https page's `Content-Security-Policy` has `connect-src 'self' https://wl.works`.
  - A `Host` other than `127.0.0.1:{port}` (say `rig-4.wl.works`) answers 421.
  - **The request log** (`capsys`, or the handler's `log_message` patched to collect): after `GET /?code=SECRETCODE`, the logged line holds `GET /` and not `SECRETCODE` (Ruling 10).
  - **A slow handshake does not stop others.** Open a raw TCP connection to the port and send nothing. Then, within 5 s, a second client's `GET /` answers 200.
  - **On the http listener** (the file's `_served`), a `POST /commands` with an `Authorization` header answers 403 with `TOKEN_OVER_HTTP`, and the dispatch saw nothing (**Review Focus 3**).
  - `/whoami` and `/signout` on the http listener answer 404.
  - **The flags** (through `cli.main` or `serve.run`, as the file's `_serve_args` tests do):
    - `--https` without `--tls-cert` is refused naming the missing flag; each of the six alone, likewise;
    - `--rig-page rig3=http://x/` is refused with `parse_rig_page`'s sentence;
    - a `--tls-key` file that is not a key is refused with a sentence that holds neither the file's contents nor its path.

- [ ] **Step 2: Run them to see them fail.**

- [ ] **Step 3: Implement in `wl_xcon/serve.py`.**

```python
import ssl
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # `signin` imports `jwt`; `serve` must import without it.
    from wl_xcon import signin as _signin

#: What a command carrying a token to the plain-http listener is told (b2b spec §3).
TOKEN_OVER_HTTP = "sign-in works only on the rig's https page"


@dataclass(frozen=True)
class Remote:
    """The https page's sign-in (b2b spec §3-§5): this rig's page entry, and the checker
    every command from the network goes through."""

    page: "_signin.RigPage"
    checker: "_signin.Checker"


def tls_context(cert: Path, key: Path) -> ssl.SSLContext:
    """The https listener's TLS, server side, TLS 1.2 at least (spec §3). Raises
    `SystemExit` with a sentence that names the flags and never the key's contents or path."""
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    try:
        context.load_cert_chain(certfile=cert, keyfile=key)
    except (OSError, ssl.SSLError) as exc:
        raise SystemExit(
            f"refused: --tls-cert and --tls-key could not be loaded as a certificate chain "
            f"and its private key ({type(exc).__name__})"
        ) from None
    return context


class _PageServer(ThreadingHTTPServer):
    """The https listener (spec §3). **The TLS handshake runs on the connection's own
    thread** (`finish_request`), never on the thread that accepts, so one slow or stalled
    client cannot stop others connecting."""

    def __init__(self, address, handler, context: ssl.SSLContext) -> None:
        self._context = context
        super().__init__(address, handler)

    def finish_request(self, request, client_address) -> None:
        request.settimeout(REQUEST_TIMEOUT_S)
        try:
            tls = self._context.wrap_socket(request, server_side=True)
        except (ssl.SSLError, OSError):
            return  # a failed handshake asked nothing, so there is nothing to answer
        try:
            self.RequestHandlerClass(tls, client_address, self)
        finally:
            tls.close()
```

  In `make_handler`, add the `remote: Remote | None = None` parameter, `_remote = remote` on the class, and these changes:
  - `_host_ok`: with a remote, `(self.headers.get("Host") or "").strip().lower() == self._remote.page.host`; otherwise as today.
  - `may_write`: `False` with a remote, since the box checks never apply on the https page.
  - `_path()` returns `self.path.partition("?")[0]`. `do_GET` routes on it, so `GET /?code=…` serves the page; every other path with a query is 404 as before.
  - `_ROUTES` gains `/whoami` and `/signout`. A handler with no remote answers 404 for both.
  - `_security_headers` adds `Referrer-Policy: no-referrer`.
  - `log_request` writes the path alone (Ruling 10):

```python
        def log_request(self, code="-", size="-") -> None:
            """The stdlib's request line without its query string (the plan's Ruling 10):
            the page's return from wl.works carries an authorization code there."""
            self.log_message('"%s %s" %s', self.command, self._path(), str(code))
```

  - `_page`: with a remote, the CSP's `connect-src` adds the token endpoint's origin (`_csp(nonce, connect=…)`, where `connect` is `remote.checker.discovery.token_origin` when the checker has a discovery, and nothing otherwise).
  - `_command`, on the http listener: a request carrying an `Authorization` header is answered `403 {"status": "refused", "said": TOKEN_OVER_HTTP}` before anything else.
  - On the https listener, `POST /commands` is Task 9's. Until Task 9, it answers `403` with `NO_TOKEN`'s sentence.

  In `Server.__init__`, take `https`, `tls` and `remote`, all `None` by default:

```python
        self._page_http = (
            None
            if https is None
            else _PageServer(
                https,
                make_handler(
                    self.hub, token=token, stale_after_s=stale_after_s, keepalive_s=keepalive_s,
                    dispatch=self.dispatch, remote=remote,
                ),
                tls,
            )
        )
        self._page_web = None if self._page_http is None else threading.Thread(
            target=self._page_http.serve_forever, name="wlx-serve-https", daemon=True
        )
        self._keys = None if remote is None or remote.checker.ready else threading.Thread(
            target=remote.checker.retry_until_ready, args=(self._stop,), name="wlx-serve-keys", daemon=True
        )
```

  `start` starts `_page_web` and `_keys` when present. `close` shuts down and joins `_page_http` exactly as it does `_http`, guarded by `ident` (read its docstring's fix rounds first). `page_address` returns `_page_http.server_address[:2]`.

  In `run`, after the existing checks: if any of the six flags is given, all six must be, or the refusal names the missing ones. Then:
  - `from wl_xcon import signin` here, inside the branch, and nowhere at module level;
  - `page = signin.parse_rig_page(args.rig_page)`, turning `ValueError` into `SystemExit(f"refused: {exc}")`;
  - `parse_http(args.https)` for the address;
  - `tls_context(...)`;
  - a `signin.Checker(page=page, issuer=args.wl_works_issuer, cache=args.wl_works_cache)`, `load()`ed, with its sentence printed;
  - then `Server(..., https=…, tls=…, remote=Remote(page, checker))`;
  - and the start line gains: `the rig's https page is at {page.page}, where people signed in to wl.works may use the controls`.

  In `cli.py`'s `serve` parser, add the six flags with help in the file's style:
  - `--https HOST:PORT`;
  - `--tls-cert PATH` and `--tls-key PATH` (both `type=Path`);
  - `--rig-page NAME=URL` ("this rig's entry in wl.works' RIG_PAGES, copied verbatim");
  - `--wl-works-issuer URL` ("https://wl.works/api/auth for the lab");
  - `--wl-works-cache PATH` (`type=Path`).

- [ ] **Step 4: Run the tests to see them pass**, then the whole suite.
- [ ] **Step 5: Prove they can fail.**
  - Move the handshake into `get_request` (wrap there), and see the slow-handshake test fail.
  - Remove `log_request`, and see the log test fail.
  - Remove the http listener's token refusal, and see its test fail.
  - Restore each.
- [ ] **Step 6: Commit.** "Serve the rig's page over https beside the box's own, its handshake per connection (b2b spec §3)".

---

### Task 9: Commands, `/whoami` and `/signout` from a signed-in page

**Files:**
- Modify: `wl_xcon/serve.py`
- Test: `tests/test_serve.py`

**Interfaces:**
- Consumes: `Checker.check`, `Checker.sign_out`, `Remote`, and Task 2's `parse_command`.
- Produces:
  - `serve.parse_command(data: object, actor: Member | None = None)`;
  - `POST /whoami`, answering `200 {"status": "signed_in", "name": str, "shown": str, "expires_at": float}`;
  - `POST /signout`, answering `200 {"status": "signed_out", "said": "signed out at this rig"}`;
  - a refusal's body: `401 {"status": "refused", "reason": str, "said": str}`.

- [ ] **Step 1: Write the failing tests**, with `_page_served` and the file's `_Dispatch`. Each POST goes through `_https(..., "POST", path, headers, body)` with `Origin: https://127.0.0.1:{port}`, `Content-Type: application/json` and `Authorization: Bearer <token>` unless the test says otherwise:
  - A pause with a good token reaches the dispatch as `Pause(by=Member(...))`, the member named from the token.
  - Each refused case answers 401, carries `reason` and `said`, and the dispatch sees nothing: no token, an expired token, another rig's audience, and a token signed out through `/signout`.
  - A body carrying `"by": "jake"` beside a good token answers 400, `not sent: a command from a signed-in page takes no by; who sent it is the sign-in's` (**Review Focus 3**).
  - A wrong `Origin`, or no `Content-Type`, answers 403, and the dispatch sees nothing.
  - `/whoami` with a good token answers the member's `name` and `shown`; with an expired one, 401 with reason `expired`.
  - `/signout` answers 200 whatever the token. After it, `/whoami` with that token answers 401 with reason `signed_out`.
  - **No token in any answer**: for each of the above, assert `token.encode()` is not in the response body.

  **End to end, with a real session** (**Review Focus 4**):
  - Use the file's `_Taskd`. Beside its http `Server`, start a second `Server` on the same `sub`, `req` and `mark`, with its own `http=("127.0.0.1", 0)` (the parameter is required), plus `https` and a `Remote` built as `_page_served` builds one. A second console on one session is ordinary: the REP socket answers each REQ peer in turn.
  - Through the https page and a member's token: open a session (the departure typed now), start a short run, pause, change `reward_correct`, give a hand reward, mark with a note, schedule a stop after 2 trials, resume, end with the return.
  - Then assert:
    - every `by` and `acknowledged_by` in the session folder's `*.jsonl` files whose command came from the page is the member's map, `{"kind": "member", "name": "Jake Westerberg", "account": "user-1", "issuer": …, "token_id": <jti>}`;
    - the departure row in `welfare_notes.jsonl` is the member's;
    - **no file in the folder contains the token**: `assert token not in path.read_text()` for every file;
    - **and `wlx serve`'s log holds neither the token nor a code**: run this test under `capfd` and read stderr.
  - **A resume from the page** (spec §8): a second `_Taskd` test, built on the file's crash-and-resume test (`grep -n 'crash = True' tests/test_serve.py`). Leave a session stranded, then resume it through the https page with a member's token. Assert that the `session resumed` row in `welfare_notes.jsonl` carries the member's map.

- [ ] **Step 2: Run them to see them fail.**

- [ ] **Step 3: Implement.** `parse_command`:

```python
def parse_command(data: object, actor: Member | None = None):
    """... (existing docstring) ...

    **From a signed-in page (b2b spec §3)** `actor` is the member `signin` named, and the
    body carries no `by`: who sent it is the sign-in's, never what a page wrote."""
    if not isinstance(data, dict):
        raise BadCommand("a command is one JSON object")
    kind = data.get("kind")
    if not isinstance(kind, str) or kind not in _SHAPES:
        raise BadCommand(f"{kind!r} is not a command this console sends")
    if actor is None:
        by = _person(data.get("by"))
        allowed = {"kind", "by"}
    else:
        if "by" in data:
            raise BadCommand("a command from a signed-in page takes no by; who sent it is the sign-in's")
        by = actor
        allowed = {"kind"}
    extra = set(data) - allowed - _SHAPES[kind]
    ...  # the rest unchanged
```

  In the handler, on the https listener:

```python
        def _from_the_page(self) -> bool:
            """The https page's write checks before the token's (spec §3): `Origin` is
            exactly the page's origin, and `Content-Type: application/json`."""
            origin = (self.headers.get("Origin") or "").lower()
            content = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            return origin == self._remote.page.origin and content == "application/json"

        def _signed_in(self):
            """The member this request's token names, or `None` after answering its 401."""
            from wl_xcon import signin  # imported only on the https listener's path

            try:
                return self._remote.checker.check(self.headers.get("Authorization"))
            except signin.Refused as refused:
                self._send_json(401, {"status": "refused", "reason": refused.reason, "said": refused.said})
                return None
```

  - `_command` on the https listener:
    1. `_from_the_page()`, else 403 with `{"status": "refused", "said": "a command must come from this rig's page"}`;
    2. then `_signed_in()`, which returns `None` after answering;
    3. then the existing length, body and parse path, with `parse_command(data, actor=accepted.member)`.
  - `do_POST` routes `/whoami` and `/signout` on the https listener, each after `_from_the_page()`.
  - `/whoami`: `accepted = self._signed_in()`; then `200 {"status": "signed_in", "name": accepted.member.name, "shown": str(accepted.member), "expires_at": accepted.expires_at}`.
  - `/signout`: `self._remote.checker.sign_out(self.headers.get("Authorization"))`, then 200 with `"signed out at this rig"`.
  - **Both read and discard their bodies** (at most `BODY_LIMIT`, as `_command` does), so a keep-alive connection stays in step.

- [ ] **Step 4: Run them to see them pass, then the whole suite.**
- [ ] **Step 5: Prove they can fail.**
  - Let a body's `by` override `actor`, and see Review Focus 3's test fail.
  - Skip `_from_the_page`, and see the Origin test fail.
  - Restore each.
- [ ] **Step 6: Commit.** "Accept commands from a signed-in page as its member's, with /whoami and /signout (b2b spec §3-§5)".

---

### Task 10: The page — modes, gating and the sign-in script

**Files:**
- Modify: `wl_xcon/web.py`, `wl_xcon/serve.py` (pass the sign-in to the page)
- Test: `tests/test_web.py`

**Interfaces:**
- Consumes: `signin.Discovery`, `signin.RigPage`, and Task 9's routes and answers.
- Produces:
  - `web.SignIn(authorize: str | None, token_endpoint: str | None, client_id: str, page: str, resource: str, unavailable: str | None = None)`. `unavailable` is the sentence the page shows when the rig has no keys yet. `serve` passes `signin.NO_KEYS`, because `web` must not import `signin`, which imports `jwt`;
  - `View.signin: bool = False` and `View.https_page: bool = False`;
  - `web._gate(view: View, other: str = "") -> str`;
  - `web.page(..., signin: SignIn | None = None, https_page: bool = False)`;
  - the constants `SIGN_IN_FIRST`, `CONTROLS_AT_THE_BOX` ("controls work only at the rig PC") and `CONTROLS_ELSEWHERE` ("controls work at the rig PC, or signed in on this rig's https page").

- [ ] **Step 1: Write the failing tests** in `tests/test_web.py`, with the file's own frame and view builders:
  - **`_gate`:**
    - a writable view returns its `other` unchanged;
    - a sign-in view returns `other` when given, and ` disabled data-signin title="sign in with wl.works to use the controls"` when not;
    - a LAN view returns `disabled` with `CONTROLS_AT_THE_BOX`, or with `CONTROLS_ELSEWHERE` when `https_page` is set.
  - **On a sign-in view:**
    - *give reward*, while a run's trials run, carries `REWARD_ONLY_PAUSED` and no `data-signin` (Ruling 7);
    - *pause* carries `data-signin`.
  - **`page(..., signin=SignIn(...))`:**
    - sets `data-signin="1"`, `data-authorize`, `data-token-endpoint`, `data-client`, `data-page` and `data-resource` on `<body>`, all escaped;
    - renders `#signin` and `#signout` and no `#rename`;
    - its static controls carry `data-signin`.
  - **`page(..., signin=SignIn(authorize=None, token_endpoint=None, ..., unavailable="the rig has not reached wl.works to check sign-ins; use the rig PC"))`** (no keys yet) renders that sentence and no `#signin` button.
  - **The box page** (`can_write=True`) is unchanged: `#who`, `#rename`, no `data-signin` anywhere.
  - **The script's text** carries, as the file's other script tests read it:
    - `"offline_access"`, `"S256"`, `credentials: "omit"` and `sessionStorage`;
    - no `localStorage` use for the sign-in (the box's name keeps its `localStorage`);
    - and `Authorization`.

- [ ] **Step 2: Run them to see them fail.**

- [ ] **Step 3: Implement the renderer.** Replace `_off` with `_gate`, and every `off = _off(view) or (X)` with `off = _gate(view, X)` (`grep -n '_off(' wl_xcon/web.py`; there are about fourteen):

```python
#: What a control says on the https page to a browser not signed in (b2b spec §4).
SIGN_IN_FIRST = "sign in with wl.works to use the controls"
#: What a LAN viewer's greyed controls say on the plain-http page (b2b spec §3): the
#: first without an https page configured, the second with one.
CONTROLS_AT_THE_BOX = "controls work only at the rig PC"
CONTROLS_ELSEWHERE = "controls work at the rig PC, or signed in on this rig's https page"


def _gate(view: View, other: str = "") -> str:
    """A control's attributes (the plan's Ruling 7). `other` is its own reason to be
    greyed, or nothing. On the box's page, `other`. On the https page, `other`, or, when
    it has none, greyed until the script holds a sign-in (`data-signin`). Everywhere else,
    greyed saying where controls work."""
    if view.can_write:
        return other
    if view.signin:
        return other or f' disabled data-signin title="{_e(SIGN_IN_FIRST)}"'
    why = CONTROLS_ELSEWHERE if view.https_page else CONTROLS_AT_THE_BOX
    return f' disabled title="{_e(why)}"'
```

  `serve` sets `signin=True` on the https listener's views, and `https_page=True` on the http listener's when a remote is configured. Thread this through `Hub.snapshot` as `can_write` is threaded today.

  In `page`:
  - The static `off` is `""` when writable, ` disabled data-signin title="…"` on the sign-in page, and the LAN sentence otherwise.
  - The `who` span becomes one of three:
    - the box's: today's markup;
    - the https page's:

      ```html
      <span class="who" id="mode"><span class="so">read-only · <button class="btn small primary" id="signin" type="button">sign in with wl.works</button></span><span class="si">controls act as <b id="member"></b> · <button class="btn small" id="signout" type="button">not you? sign out</button></span></span>
      ```

      or, with `signin.token_endpoint is None`, `read-only · <span class="nm">` plus `signin.unavailable` (escaped) plus `</span>`;
    - a LAN viewer's: `read-only` and the greyed sentence.
  - Add the `<body>` attributes from `SignIn`, each `_e`-escaped.
  - Add to `_CSS`: `body:not([data-signed-in="1"]) .si{display:none} body[data-signed-in="1"] .so{display:none}`.

  In `serve`'s `_page` on the https listener, build `SignIn`:
  - `authorize` and `token_endpoint` from `checker.discovery`, or `None` without one, and then `unavailable=signin.NO_KEYS`;
  - `client_id` from `page.client_id`, `page` from `page.page`, and `resource` from `page.origin`.

- [ ] **Step 4: Implement the script.** Add this block to `_SCRIPT`, after the `NAME_KEY` declarations:

```js
  // P4d-2b b2b (spec §4): signing a member in on the rig's https page. The tokens live
  // in this tab's sessionStorage only; Python renders every word a person reads.
  var signinPage = body.getAttribute("data-signin") === "1";
  var SIGNIN_KEY = "wlx-signin";
  var PKCE_KEY = "wlx-signin-pkce";
  // Housekeeping, not measurements (spec §4): renew this long before the hour is up,
  // and renew first before a command when less than this is left.
  var RENEW_BEFORE_MS = 5 * 60 * 1000;
  var FRESH_FOR_MS = 60 * 1000;
  var renewTimer = null;
  function readStore(key) {
    try { return JSON.parse(window.sessionStorage.getItem(key) || "null"); } catch (e) { return null; }
  }
  function writeStore(key, value) {
    try {
      if (value === null) { window.sessionStorage.removeItem(key); }
      else { window.sessionStorage.setItem(key, JSON.stringify(value)); }
    } catch (e) { /* this tab's memory only, then */ }
  }
  var signin = signinPage ? readStore(SIGNIN_KEY) : null;
  function signedIn() { return !!(signin && signin.name); }
  function b64url(bytes) {
    var text = "";
    for (var i = 0; i < bytes.length; i++) { text += String.fromCharCode(bytes[i]); }
    return btoa(text).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  }
  function random(n) { var bytes = new Uint8Array(n); crypto.getRandomValues(bytes); return b64url(bytes); }
  function applySignIn() {
    if (!signinPage) { return; }
    body.setAttribute("data-signed-in", signedIn() ? "1" : "0");
    var member = el("member");
    if (member) { member.textContent = signedIn() ? signin.shown : ""; }
    Array.prototype.forEach.call(document.querySelectorAll("[data-signin]"), function (node) {
      node.disabled = !signedIn();
    });
  }
  function startSignIn() {
    var verifier = random(32);
    var state = random(16);
    crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier)).then(function (digest) {
      writeStore(PKCE_KEY, { verifier: verifier, state: state });
      var query = new URLSearchParams({
        response_type: "code",
        client_id: body.getAttribute("data-client"),
        redirect_uri: body.getAttribute("data-page"),
        scope: "offline_access",
        resource: body.getAttribute("data-resource"),
        code_challenge: b64url(new Uint8Array(digest)),
        code_challenge_method: "S256",
        state: state
      });
      window.location.assign(body.getAttribute("data-authorize") + "?" + query.toString());
    });
  }
  function tokenRequest(fields) {
    return fetch(body.getAttribute("data-token-endpoint"), {
      method: "POST",
      credentials: "omit",
      cache: "no-store",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams(fields).toString()
    }).then(function (response) {
      return response.json().then(
        function (answer) { return { ok: response.ok, answer: answer }; },
        function () { return { ok: false, answer: {} }; }
      );
    });
  }
  function keep(answer) {
    signin = {
      access: answer.access_token,
      refresh: answer.refresh_token || (signin && signin.refresh) || null,
      expires: Date.now() + Number(answer.expires_in) * 1000,
      name: null,
      shown: null
    };
  }
  function forget() {
    signin = null;
    writeStore(SIGNIN_KEY, null);
    clearTimeout(renewTimer);
    applySignIn();
  }
  function whoami() {
    return fetch("/whoami", {
      method: "POST",
      cache: "no-store",
      headers: { "Content-Type": "application/json", "Authorization": "Bearer " + signin.access },
      body: "{}"
    }).then(function (response) { return response.json(); }).then(function (answer) {
      if (answer.status === "signed_in") {
        signin.name = answer.name;
        signin.shown = answer.shown;
        writeStore(SIGNIN_KEY, signin);
        scheduleRenew();
        applySignIn();
      } else {
        forget();
        tell("not signed in: " + answer.said, "crit");
      }
    });
  }
  function finishSignIn() {
    var params = new URLSearchParams(window.location.search);
    if (!params.has("code") && !params.has("error")) { return Promise.resolve(); }
    window.history.replaceState(null, "", window.location.pathname);
    var kept = readStore(PKCE_KEY);
    writeStore(PKCE_KEY, null);
    if (params.has("error")) {
      tell("not signed in: " + (params.get("error_description") || params.get("error")), "crit");
      return Promise.resolve();
    }
    if (!kept || kept.state !== params.get("state")) {
      tell("not signed in: this sign-in was not started from this page", "crit");
      return Promise.resolve();
    }
    return tokenRequest({
      grant_type: "authorization_code",
      code: params.get("code"),
      redirect_uri: body.getAttribute("data-page"),
      client_id: body.getAttribute("data-client"),
      code_verifier: kept.verifier
    }).then(function (result) {
      if (!result.ok || !result.answer.access_token) {
        tell("not signed in: " + (result.answer.error_description || "wl.works did not sign you in"), "crit");
        return;
      }
      keep(result.answer);
      return whoami();
    });
  }
  function renew() {
    if (!signin || !signin.refresh) { forget(); return Promise.resolve(false); }
    return tokenRequest({
      grant_type: "refresh_token",
      refresh_token: signin.refresh,
      client_id: body.getAttribute("data-client")
    }).then(function (result) {
      if (!result.ok || !result.answer.access_token) {
        forget();
        tell("signed out: " + (result.answer.error_description || "wl.works did not renew this sign-in"), "crit");
        return false;
      }
      keep(result.answer);
      return whoami().then(function () { return signedIn(); });
    }, function () {
      tell("could not reach wl.works to renew this sign-in", "crit");
      return signedIn() && signin.expires > Date.now();
    });
  }
  function scheduleRenew() {
    clearTimeout(renewTimer);
    if (!signin) { return; }
    var left = signin.expires - Date.now();
    renewTimer = setTimeout(renew, Math.max(left / 2, left - RENEW_BEFORE_MS));
  }
  function fresh() {
    if (!signedIn()) { return Promise.resolve(false); }
    if (signin.expires - Date.now() > FRESH_FOR_MS) { return Promise.resolve(true); }
    return renew();
  }
  function signOut() {
    var held = signin;
    forget();
    tell("signed out at this rig", "ok");
    if (!held) { return; }
    fetch("/signout", {
      method: "POST",
      cache: "no-store",
      headers: { "Content-Type": "application/json", "Authorization": "Bearer " + held.access },
      body: "{}"
    }).catch(function () { /* the tab has forgotten it either way */ });
  }
```

  Restructure `post` into `post` and `deliver`. The rest of `post`'s body moves into `deliver` unchanged, including the `REWARD_LOST` path:

```js
  function post(command, then, after) {
    var done = after || function () {};
    if (signinPage) {
      fresh().then(function (ok) {
        if (!ok) { tell("not sent: sign in with wl.works to use the controls", "crit"); done(); return; }
        deliver(command, { "Authorization": "Bearer " + signin.access }, then, done);
      });
      return;
    }
    if (!canWrite) { done(); return; }
    var by = name || askName();
    if (!by) {
      tell("not sent: give your name first -- every command records who sent it", "crit");
      done();
      return;
    }
    command.by = by;
    deliver(command, {}, then, done);
  }
  function deliver(command, extra, then, done) {
    tell("sending…", "");
    var headers = { "Content-Type": "application/json" };
    Object.keys(extra).forEach(function (key) { headers[key] = extra[key]; });
    fetch("/commands", {
      method: "POST",
      headers: headers,
      body: JSON.stringify(command),
      cache: "no-store"
    }).then(function (response) {
      return response.json();
    }).then(function (answer) {
      tell(answer.said, answer.status === "sent" || answer.status === "signaled" ? "ok" : "crit");
      // A refusal for the token (the plan's Ruling 8): never re-sent; renew, or sign out.
      if (answer.reason === "expired") { renew(); }
      else if (answer.reason === "signed_out" || answer.reason === "other_rig" ||
               answer.reason === "not_accepted" || answer.reason === "no_token") { forget(); }
      if (then) { then(answer); }
    }).catch(function () {
      tell(command.kind === "reward" ? REWARD_LOST : "not delivered: this page could not reach wlx serve", "crit");
    }).then(done);
  }
```

  Wire it up:
  - In `swap`, at its end: `applySignIn();`.
  - In `showName`, return first when `el("who")` is null.
  - Guard `el("rename").addEventListener` with `if (el("rename"))`.
  - At the end, before `showName(); open();`:

```js
  if (signinPage) {
    if (el("signin")) { el("signin").addEventListener("click", startSignIn); }
    if (el("signout")) { el("signout").addEventListener("click", signOut); }
    document.addEventListener("visibilitychange", function () {
      if (!document.hidden && signin && signin.expires - Date.now() < RENEW_BEFORE_MS) { renew(); }
    });
    applySignIn();
    finishSignIn().then(function () {
      if (signin && signin.access && !signin.name) { return whoami(); }
      if (signedIn()) { return whoami(); }
    }).then(applySignIn);
  }
```

- [ ] **Step 5: Run the tests, then the whole suite.**
- [ ] **Step 6: Prove the renderer tests can fail.** Make `_gate` put `data-signin` on a control with its own reason, and see the paused-reward test fail. Restore it. The script's behavior is proved in a browser in Task 11.
- [ ] **Step 7: Commit.** "Sign a member in on the rig's https page, renew, and sign out (b2b spec §4)".

---

### Task 11: The page in a real browser (closes XC-186)

**Files:**
- Create: `tests/_browser.py` (the browser fixture and a fake wl.works served over https)
- Create: `tests/test_page_browser.py`

**Interfaces:**
- Consumes:
  - Task 8's `_PageServer`, `Remote` and `tls_context`;
  - `tests/_tls.material`, `tests/_issuer.Issuer`, and `tests/_frames.py`'s frame;
  - Task 9's routes and Task 10's page.
- Produces: `tests/_browser.chromium()`, a context manager that yields a Playwright `Browser`. It skips when Playwright or Chromium is missing, and fails instead when `WLX_REQUIRE_BROWSER=1`.

- [ ] **Step 1: Write `tests/_browser.py`.**
  - `chromium()`: `pytest.importorskip("playwright.sync_api")` (or, under `WLX_REQUIRE_BROWSER=1`, a plain import that fails). Then `sync_playwright().start()` and `chromium.launch()`. A launch error is a skip, or under the variable a failure, naming `python -m playwright install chromium`.
  - `FakeWlWorks(issuer: Issuer, page: str, origin: str, tls: dict)`: an `https` `ThreadingHTTPServer` (a `_PageServer`, with `tls_context(tls["cert"], tls["key"])`) whose handler serves two endpoints.
    - **`GET /api/auth/oauth2/authorize`** checks:
      - `client_id == "wl-works-rig-rig-3"`, `redirect_uri == page`, `scope == "offline_access"`;
      - `resource == origin`, `code_challenge_method == "S256"`;
      - and the absence of `prompt` (the PI's ruling).
      - It records the challenge under a fresh code and answers `302` to `page + "?" + urlencode({"code": code, "state": state})`. A failed check answers `400` and records why in `self.refused`.
    - **`POST /api/auth/oauth2/token`**, form-encoded:
      - `authorization_code` checks the code, the verifier against its S256 challenge, `client_id` and `redirect_uri`. It answers `{"access_token": issuer.mint(aud=origin, exp_in=self.expires_in), "refresh_token": "r-<n>", "expires_in": self.expires_in, "token_type": "Bearer"}`.
      - `refresh_token` does the same, or, when `self.refuse_renewal` is set, answers `400 {"error": "invalid_grant", "error_description": "This sign-in at the rig is 24 hours old. Sign in again at the rig."}` (wl-works `rig-sign-in.ts`'s words).
      - Every answer on this path carries `Access-Control-Allow-Origin: <origin>` and `Vary: Origin`, as `rig-cors.ts`'s `withRigCors` does. `OPTIONS` answers as its `rigPreflight` does.
    - Counters: `self.renewals` and `self.exchanges`.
  - The issuer the rig's checker uses is `https://127.0.0.1:<fake port>/api/auth`, so its discovery's endpoints point at the fake. Give `Issuer` that string, and give the checker `fetch=issuer.fetch` (no network), with its discovery's `authorization_endpoint` and `token_endpoint` on the fake's address.

- [ ] **Step 2: Write the browser tests** in `tests/test_page_browser.py`, around one fixture, `rig`, defined in that file. It yields an object with:
  - `browser_page()`, a Playwright page already at the rig's https page;
  - `dispatch`, the `_Dispatch` (copy that small class from `tests/test_serve.py`; test files here do not import each other);
  - `checker`, the rig's `signin.Checker`;
  - `fake`, the `FakeWlWorks`;
  - `hub`, so a test can `offer` a paused frame;
  - `wait_for(predicate, seconds=10.0)`, polling every 0.05 s and failing the test on timeout.

  It shuts everything down in its teardown. Each test:
  - starts the fake wl.works and the rig's https page, the latter served by `_PageServer` with `make_handler(hub, …, remote=Remote(page, checker), dispatch=_Dispatch())`, `hub.offer(<the frame from tests/_frames.py>)`, and CSP `connect-src` naming the fake's origin;
  - opens a Playwright context with `ignore_https_errors=True`;
  - and goes to the page.

  If `page.evaluate("window.isSecureContext")` is false under `ignore_https_errors`, launch Chromium instead with `--ignore-certificate-errors-spki-list=<base64 of the SHA-256 of the leaf's SubjectPublicKeyInfo>`. That makes the test certificate trusted rather than bypassed, and `crypto.subtle` needs a secure context. Record which one worked in the report.

  ```python
  def test_a_member_signs_in_and_a_pause_reaches_the_rig_as_theirs(rig):
      page = rig.browser_page()
      page.click("#signin")
      page.wait_for_selector("#member:has-text('Jake Westerberg (wl.works)')", timeout=10_000)
      assert "code=" not in page.url
      page.click('[data-cmd="pause"]')
      rig.wait_for(lambda: rig.dispatch.seen)
      assert isinstance(rig.dispatch.seen[-1], Pause)
      assert rig.dispatch.seen[-1].by.name == "Jake Westerberg"
  ```

  Then these, each with its own assertions:
  - **`test_a_state_that_was_not_started_here_is_refused`**: navigate straight to `page + "?code=X&state=forged"`. `#sent` shows `this sign-in was not started from this page`, the fake saw no token exchange, and `#member` is empty.
  - **`test_a_short_token_is_renewed_before_a_command`**: set the fake's `expires_in = 4` before signing in. After sign-in, wait 3 s, click pause, and assert `fake.renewals >= 1` and that the dispatch saw the pause.
  - **`test_a_refused_renewal_signs_the_page_out_with_wl_works_sentence`**: set `refuse_renewal`, use a short token, wait for the renewal, and assert `#sent` holds `24 hours old` and the controls are `disabled` again.
  - **`test_sign_out_makes_the_rig_refuse_the_old_token`**: after sign-in, read the token from `sessionStorage` (`page.evaluate`), click `#signout`, then POST `/whoami` with that token from Python (`_https`) and assert 401 with reason `signed_out`.
  - **`test_a_reward_refused_for_its_token_is_not_sent_again`** (**Review Focus 5**): after sign-in, call `rig.checker.sign_out` with the page's token. Click *give reward* once, wait 2 s, and assert the dispatch saw no `ManualReward` and `#sent` names the refusal. (The reward button is live only while paused, so first give the hub a paused frame: `_frames.py`'s builder with `paused_at` set.)
  - **`test_neither_the_code_nor_the_token_reaches_the_page_server_log`** (**Review Focus 4**): run the sign-in under `capfd`, and assert stderr holds neither the code (recorded by the fake) nor the token.

- [ ] **Step 3: Run them.** `WLX_REQUIRE_BROWSER=1 python3 -m pytest -q -p no:cacheprovider tests/test_page_browser.py`. A failure here is a defect in Tasks 8-10: fix it in the owning file, in this task's commit, and name it in the report.
- [ ] **Step 4: Prove the browser tests can fail.**
  - Remove the `state` comparison in `finishSignIn`, and see the forged-state test fail.
  - Make `deliver` re-send on a 401 (`if (answer.reason) { deliver(command, extra, then, done); }`), and see the reward test fail.
  - Restore each, and check the file with `cmp`.
- [ ] **Step 5: Commit.** "Drive the rig's page in a real browser: sign in, renew, refuse, sign out (closes XC-186)". In the same commit, remove XC-186's line from `docs/backlog.md`, and in XC-191's line change `waits on: XC-186` to `waits on: nothing`.

---

### Task 12: The docs, and the backlog

**Files:**
- Modify: `docs/design/architecture.md`, `docs/superpowers/specs/2026-09-26-P4d2b-browser-console-design.md`, `docs/superpowers/specs/2026-08-31-S9a-console-design.md`, `docs/pending-wl-works-amendments.md`, `docs/backlog.md`, `docs/design/decisions/ADR-0008-console-surface.md` (only if it states that writes come from the box alone: `grep -n 'box' docs/design/decisions/ADR-0008-console-surface.md`).

- [ ] **Step 1: `architecture.md`.** In the console's section, describe the second listener:
  - the https page and the flags;
  - that a command from it is a `Member`'s, checked offline against wl.works' keys;
  - and that the rig PC's http page is unchanged.

  The welfare-critical paragraph does not change: the list is not widened.
- [ ] **Step 2: The P4d-2b spec §2**, the bullet "**Reads are open to the LAN; writes from the box in b2a, and from people signed in to wl-works in b2b**": add "(built 2026-10-02; see the b2b spec)".
- [ ] **Step 3: S9a §6:** "Built 2026-10-02 (b2b): the box is not an OAuth client holding a session; the browser holds the member's token and `wlx serve` checks it offline, as the P4d-2b spec §5.7 recorded the PI choosing on 2026-09-27."
- [ ] **Step 4: `pending-wl-works-amendments.md`**, the "Signing in" section: add a dated line saying the rig side is built. Its page asks for `offline_access` alone, with no `prompt`. Nothing is configured in `RIG_PAGES` until XC-151 and XC-152.
- [ ] **Step 5: The backlog.** Remove XC-015's line ("closes XC-015"). Add one line in "Needs the rig":
  - `- **XC-NNN** A live sign-in at a real rig's https page with a token wl.works issued: the one check b2b's tests cannot make (spec §8). — 2026-10-02, [b2b spec §8](superpowers/specs/2026-10-02-p4d2b-b2b-remote-signin-design.md#8-testing-sim-first-no-network) — waits on: XC-151, XC-152`
  - Take the next free ID and raise "Next free ID" by one. Run `tests/test_backlog.py` alone.
- [ ] **Step 6: Commit.** "Say where b2b's sign-in lives in the docs (closes XC-015)".

---

### Task 13: Slice 2's proof and review

- [ ] **Step 1:** Run the full suite three times in a row with `WLX_REQUIRE_PREPROC=1 WLX_REQUIRE_BROWSER=1`, and record each count.
- [ ] **Step 2: Sweep every new and changed function** in `git archive` copies, one lane per module:
  - `signin`: all of it;
  - `serve`: `tls_context`, `_PageServer.finish_request`, `make_handler`'s changed and new methods (`_host_ok`, `may_write`, `_path`, `log_request`, `_security_headers`, `_page`, `_command`, `_from_the_page`, `_signed_in`, `do_GET`, `do_POST`), `parse_command`, `Server.__init__`, `start`, `close`, `page_address` and `run`;
  - `web`: `_gate`, `page`, and every function whose `_off` became `_gate`;
  - `cli`: the `serve` parser's function.

  Read every line. `N failed` is a catch. A timeout gets an unbounded rerun. A survivor gets a test. `web._SCRIPT` is a string the harness cannot reach; Task 11's browser tests are its proof.
- [ ] **Step 3: The PI's welfare review, spec §10 items 1-4, in the UI** (`AskUserQuestion`), as numbered items in plain terms. Record the answer in the spec's §10.
- [ ] **Step 4: Push, read CI job by job** (pytest with the browser, on 3.11-3.13; the mutation gate's lines), and fast-forward `main` once it is green and approved. Write the CHECKPOINT entry: what moved, what is next (XC-151 and XC-152 before any rig uses it), and what was learned.
- [ ] **Step 5: Tell wl-works** (spec §11) that the rig side is built: its page asks for `offline_access` alone with no `prompt`, and the rig list follows XC-151. Find a running wl-works session with `ListAgents` and send it with `SendMessage`, as their rig sign-in answer reached this repository. If none is running, tell the PI that the message is waiting, and record it in `docs/pending-wl-works-amendments.md`'s "Signing in" section.
