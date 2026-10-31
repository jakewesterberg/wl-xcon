# Amendments to wl-works

Delivered 2026-10-11 as a dated section of wl-works' `HANDOVER-wl-expcontroller.md` (`2bf5aca0`); answers are read there.

**Updated 2026-10-31: `prepare-session` is withdrawn.** Later on 2026-10-11, answering the asks delivered that
day, wl.works withdrew `prepare-session` as a published action, superseding its yes of 2026-08-31. A rig's own
page, signed in through wl.works, reads at a session's open what `prepare-session` was to carry, and the people
list with it, from a new read-only resource of wl.works', the rig read (its stage 10c-1, designed, not built);
wl.works sends a rig no action and no data. Read 2026-10-31 at wl.works `main` `b3c1b933`, read only: its
`HANDOVER-wl-expcontroller.md` (answer 2's correction, lines 68-70; "The second brainstorm's answers", lines
619-640) and its spec `docs/superpowers/specs/2026-10-11-what-wl-works-gives-a-lab-host-and-a-workstation-design.md`
(ruling 2, lines 79-82; §1.3, lines 156-160; §2, lines 164-243). Each section below that asked for
`prepare-session` carries a dated note saying so; what it asked is kept as written. Backlog XC-100, XC-105 and
XC-320 say what each now waits on.

**Updated 2026-10-11.** Six asks were delivered that day (XC-320; XC-099 and XC-100's build order; XC-103;
XC-104's alert half; XC-105; XC-098), listed in "Delivered 2026-10-11" below, and wl-works' own list of what is
closed is there too. Most of what was open here has since been **answered by wl.works** (the host list,
`prepare-session` and the fluid envelope on 2026-08-31; rig sign-in 2026-09-29 and 2026-10-06; the plan fields and the
calibration block withdrawn 2026-10-01), so what remains is the building, not the agreeing. Read against
wl-works `main` at `71b04613` (wl-works' own reading, 2026-10-11). Of the two asks opened
2026-08-31 while designing this controller
([`superpowers/specs/2026-08-31-controller-architecture-design.md`](superpowers/specs/2026-08-31-controller-architecture-design.md)
§12.3), neither is applied here, and neither is wl-works' to discover: that repository is
owned by another worker, including its remote, so these are written where wl-preproc
writes its own — in the requesting repository, for the other side to accept, amend or
refuse.

**And one from XC-288, opened 2026-10-10**: what the training-record file needs from wl.works,
under "XC-288's training records", before the closing list of decisions.

**And one from 2026-10-18**: the ELN's session-finish row labels the rig's fluid figure "fluid
commanded", not "fluid delivered", and an ELN water entry is only ever water received (wl-works'
answer that day, and the PI's four rulings on it, relayed to wl-works), under "The ELN's
session-finish row", before the list delivered 2026-10-11 (backlog XC-390).

**Both build on a document that is itself proposed, not agreed.**
`wl-preproc/docs/ops/lab-host-protocol.md` says so in its own opening line: it is written
by wl-preproc, describes the host half, and is *"proposed to wl.works rather than written
into that repository."* If wl-works rejects or reshapes that protocol, both amendments
below move with it, and that is the correct dependency — a second protocol invented here
would be worse than either outcome.

> **Accepted 2026-10-11 by wl.works** (noted 2026-10-31): the protocol is no longer only proposed. wl.works took it
> in two parts: a common part every lab machine speaks (the token, `/health`, the job envelope, listings by
> `?since=`, the codes, the three timings) and an appendix per kind of machine, each its writer's; its copy is its
> `docs/ops/lab-host-protocol.md`, and the rig's and the kiosk's appendices are asked of wl-xcon (backlog XC-434).
> (Its lab-host spec, `docs/superpowers/specs/2026-10-11-what-wl-works-gives-a-lab-host-and-a-workstation-design.md`,
> ruling 1 and §1.1; its handover, "The second brainstorm's answers", lines 626-629; read 2026-10-31 at its `main` `b3c1b933`.)

---

# OPEN — wl-works gains a second lab host, and it speaks the protocol it already has

## The ask

Treat the **task PC** as a lab host of the same kind as the preprocessing server: same
transport, same bearer token, same `GET /health` and `POST /jobs`, same status codes, same
three timing numbers. Different *action vocabulary*, identical wire contract.

Nothing about the protocol changes. What changes on the wl-works side is that
`lab-host-protocol.md`'s client is pointed at more than one host, and that the host list
becomes configuration rather than a constant.

## Why this and not a new protocol

Because wl-works' **18b contract tests already run against a fake wl-preproc**, and every
one of those tests is about the wire contract rather than about preprocessing. A second
host that answers the same shapes inherits them. A second protocol would need its own
client, its own tests, and its own maintenance, in exchange for nothing the first one
cannot express.

It also settles a question this controller would otherwise have to answer badly. The rig
**cannot push to the ELN** — `lab-host-protocol.md` §11.2 states the topology, *"the app
binds only to the WireGuard interface and we are on the lab LAN with no route in"*, and
wl-preproc enforces the complement with an AST walk over its whole package asserting it
never opens an outbound connection. So autopopulating the ELN from a rig is a pull, or it
is nothing.

## What the rig would answer

**`GET /health` — live session state as readings, not as a new endpoint.**

This follows `lab-host-protocol.md`'s own stated rule verbatim. Its "What this protocol
does not carry" section declines a job-status endpoint and says that when progress becomes
observable *"it will be as a **reading**, because readings are the surface this host already
publishes and wl.works already polls — not as a new endpoint."* Live session state is
exactly that shape: current, per-host, and cheap.

Proposed readings, in the existing readings format:

| Reading | Example | Why a reading and not a record |
|---|---|---|
| `session` | `wl-2027-01-14-A-001`, or absent | The session identity `wl-sync` minted, if one is running |
| `subject` | `A` | Who is working right now |
| `task` | `detection-v3`, with its version | What is running right now |
| `state` | `running` / `paused` / `idle` / `fault` | Whether a person needs to walk to the rig |
| `trials` | `340 attempted / 318 completed` | Progress, current by nature |
| `fluid` | `142 mL commanded` *(corrected 2026-10-18: this said "142 mL of a 250 mL ceiling"; there is no fluid ceiling since 2026-09-06, the PI, and the figure is the session's commanded total, not fluid received)* | Welfare-relevant, and stale-by-a-minute is fine |
| `preflight` | `pass`, with its timestamp | Whether the last start-up check was clean |

At the protocol's proposed 60 s poll cadence this gives wl-works a live rig dashboard for
the cost of a field list, and it needs no new endpoint, no callback and no push.

**The finished session summary is *not* asked for over this protocol.**

It goes where session data already goes: a file in the session directory, ingested by
wl-preproc alongside everything else, reaching the ELN through the path that already
exists. `lab-host-protocol.md` declines result upload for the same reason — *"wl.works
pulls; this host never pushes"* — and a session summary is a result. One integration, not
two, and no second copy of the session record free to drift from the ingested one.

The trade wl-works should know it is making: the ELN entry appears **after ingest, not at
session end**. If that latency turns out to matter, the fix is to make ingest prompt, not
to add an endpoint here.

**`POST /jobs` — a small action vocabulary, and one rule about what may go in it.**

Proposed initial actions: `prepare-session` (§ the second amendment below) and
`export-session` (re-emit a session's outputs if a transfer was lost). Both are idempotent
under the existing key, both return the existing activation-key shape, and both use `422`
for "this host cannot do that" exactly as documented.

> **Note, 2026-10-11:** wl.works' answers of 2026-08-31 name `prepare-session`, the host list as configuration and the fluid envelope; **`export-session` is not among them**, and wl-works' 2026-10-11 handover does not ask about it. Treat it as proposed here and unanswered, and as not needed by any build.

> **Superseded 2026-10-11 for `prepare-session`** (noted 2026-10-31): wl.works withdrew it as a published action,
> and what it was to carry is read by the rig's own page instead (the note at the head of the next section).
> wl.works' lab-host spec §1.3 (lines 156-160) says that with it gone "the rig publishes no jobs", that
> `prepare-session` "is not a lab-host action", and that the welfare exclusion below becomes plain: "wl.works sends
> a rig no action and no data. It only polls the rig's status." `export-session` is still as the note above says:
> proposed here and not answered.

> **No welfare-affecting action is ever published here.** `lab-host-protocol.md`'s most
> prominent line is that publishing an action makes it available to every member of the
> lab and that there is no permission model on the app side. On a preprocessing server the
> worst case is wasted compute. On a rig it is fluid, stimulation, or a session started on
> an animal nobody is standing next to. **Reward delivery, stimulation, session start and
> parameter changes are not actions and will not be exposed through this protocol** — they
> require a person at the console. This is a constraint this repository accepts, stated
> here so wl-works never has to wonder whether a rig action might be one of those.

---

# OPEN — the metadata bundle wl-works already assembles should reach the rig too

> **Superseded 2026-10-11 by wl.works' design** (noted 2026-10-31). wl.works withdrew `prepare-session`, so this
> section's ask, from "The finding" to "What is deliberately not asked for", is kept as history: wl.works sends a
> rig no action and no data. **What replaced it** (wl.works' ruling 2 of 2026-10-11, "The rig's page fetches it",
> superseding the 2026-08-31 ruling that wl.works sends it to the rig): the rig's own page, already signed in
> through wl.works, asks wl.works for a second token and reads a new read-only resource, the rig read, refused
> to an agent's token and answering across origins only to a configured rig page, never with cookies. At a session's open it answers, for the animal the
> person picks, named by its rig name: the animal's permanent id and rig name; its newest weight, with the date it
> was measured and who weighed it; its water state (`free`, `bottle` or `control`, with any minimum and its
> window); the day's water as the envelope (`value_ml`, `as_of`, `sources_included`, `complete`, in the field
> `water_received_today_ml` since 2026-10-19), `value_ml` every water entry of the animal's lab day, rig, kiosk and
> home cage; its open rig visit; and the people list. Nobody signed in, or wl.works or the network down: nothing
> arrives, and the console asks the person. "The other field names are the plan's, agreed with wl-xcon." It is
> wl.works' stage 10c-1, designed, not built, in its build "what lab machines read" right after its 20b-1 (its
> lab-host spec, `docs/superpowers/specs/2026-10-11-what-wl-works-gives-a-lab-host-and-a-workstation-design.md`,
> ruling 2 and §2.1 to §2.4, lines 79-82 and 164-228, and §13; its handover, "The second brainstorm's answers",
> lines 619-640). The sections from "One addition to the session planner" on are separate asks, each with its own
> dated notes. Backlog XC-100.

## The finding

wl-works already builds a metadata bundle for wl-preproc's job requests: subject, probe
serials, `insertion_number`, and — since wl-preproc's 2026-08-22 amendment, built and
frozen on their side at `contracts/protocol.py` — `trajectory_id` per insertion:

```json
{ "serial": "NP-1234", "insertion_number": 1, "trajectory_id": "T-0042" }
```

**The rig wants the same bundle, at the other end of the session.** Today, everything in it
would be typed into the rig console by hand at session start and then typed into the ELN
again afterward, with two chances to disagree and nothing to catch it. The bundle already
exists, is already authored in the ELN, and is already serialized for a lab host.

## The ask

A `prepare-session` action carrying the existing `MetadataBundle`, plus the session intent:

| Field | Source | Rig use |
|---|---|---|
| `subject` | ELN | Selects the subject's bounded config — per-delivery reward volume, the daily fluid **floor**, session duration, stim limits |
| `probes[]` with `serial`, `insertion_number`, `trajectory_id` | ELN, existing shape | Recorded in the session config snapshot so electrode -> trajectory -> coregistration closes from the behavioural record too |
| `planned_task` | ELN | Preselects the task; the operator confirms rather than chooses |
| `session_intent` | ELN | Free text into the session record and the ELN entry |

**No new fields are requested.** Three of the four already exist in the bundle wl-works
sends wl-preproc; `planned_task` and `session_intent` are the only additions, and both are
optional — a rig that receives neither behaves exactly as it does today.

> **Withdrawn 2026-10-01** (the PI, as recorded by wl-works `6a57b1cc`, its spec
> `2026-10-01-montage-plan-design.md` §1): `planned_task`, `session_intent` and the `probes[]`
> bundle are withdrawn. wl.works sends the rig nothing of a plan, and wl-xcon reads probes and
> sites from SpikeGLX on the rig. **What stands:** `prepare-session` itself, now carrying no plan
> fields, and the day's delivered fluid as an envelope (`fluid_delivered_today_ml`). Backlog
> XC-100. *(2026-10-11: `prepare-session` withdrawn too; the envelope stands, read by the rig's page.
> The note at this section's head.)*
>
> **Renamed 2026-10-19 by wl.works** (its handover's "2026-10-19: wl.works's answer on a session's water —
> four asks", asks 3 and 4): the field is `water_received_today_ml`, the day's water the animal received;
> the envelope inside is unchanged (`value_ml`, `as_of`, `sources_included`, `complete`), and `complete`
> is false while any of the animal's rig sessions that day is held for a person, which the rig reads as
> absence. Backlog XC-100.

## Why it reaches wl-works

Because the bundle is authored there and the rig has no route to fetch it (§11.2, above).
Everything the rig needs from the ELN must arrive with a request, which is the same
sentence that shaped wl-preproc's half of this problem.

*(Superseded 2026-10-11, noted 2026-10-31: in wl.works' design nothing arrives with a request; the rig's own page,
through the member signed in there, reads it from wl.works. See the note at this section's head.)*

## What is deliberately not asked for

Declined rather than skipped, so a later revision overturns a decision instead of
discovering an option:

- **No session-start action.** `prepare-session` stages metadata and returns; it does not
  begin a session. See the welfare note above. *(2026-10-11: `prepare-session` is withdrawn; the rig read that
  replaced it starts nothing either: it is read only, and "The page writes nothing to wl.works", wl.works'
  lab-host spec §2.1.)*
- **No TLS, no rate limiting, no permission model, no `Retry-After`.** Identical to
  wl-preproc's declines and for identical reasons; a rig should not be the host that
  invents a second answer.
- **No schema published from this repository yet.** The rig's `session-summary` is declared
  `planned` in `wl.yaml` and no JSON Schema is exported, because the shape should not be
  frozen before wl-works has said whether it wants this at all. When it is frozen it will
  be exported and CI-diffed, the way wl-preproc's two contracts are.

## One addition to the session planner

**Every session needs a planned calibration block.** `wl-preproc` authors block rows from
wl.works' session planner and quarantines on absence, so a calibration block run at the rig
without a matching plan degrades the session's timing tier. And a *dedicated* calibration block
is not optional in the way it might look: `wl-preproc`'s own docstring says it "reliably
supplies six well-spread targets," which is what decides whether a session reaches the
second-order calibration rung at all — an in-task epoch cannot guarantee the spread.

So the planner should emit a calibration block at the head of every session, with
`TaskTypeCode.CALIBRATION`. The in-task `CALIBRATION_START`/`CALIBRATION_END` epochs that follow
through the day need no planning and create no blocks.

> **Withdrawn 2026-10-01** (the PI, as recorded by wl-works `6a57b1cc`, its spec
> `2026-10-01-montage-plan-design.md` §1): the planner sends no runs, so whether a session opens
> with calibration is decided at the rig. wl-preproc withdrew the quarantine this rested on: a
> block wl.works did not author is "an unlinked block, reported and harmless" (its
> `docs/pending-wl-works-amendments.md`, `main` `b0f8b52`). Backlog XC-101, closed.

## An OAuth2 client per control box (new, 2026-09-19)

ADR-0008 makes the experimenter console a web application served by each control box, and
S9a §6 makes the box an **OAuth2 client of wl.works** so that an action can be attributed
to a real account and revoked by deactivating it.

**This asks for configuration, not development.** Read from source 2026-09-19:
`src/lib/auth.ts` registers better-auth's `mcp()` plugin, which in 1.7.1 *is* the OAuth
provider — its own comment: *"Because it is the OAuth provider, it cannot be combined with
a separate oauthProvider. So the `/oauth2/*` surface Zulip reads and the MCP agent surface
are served by the same plugin."* Zulip is already a live consumer, PKCE is a per-client
column defaulting true, and revocation is proven end to end: an admin deactivating a
member cut their already-open Zulip session as a direct result.

So the ask is a client registration per control box — or one for the fleet, if that is
preferred there; we have no opinion, and the choice is yours because it is your
credential lifecycle.

> **This does not make wl.works load-bearing for a session.** The box's own credential is
> the floor and never depends on the network: if wl.works is unreachable, the console is
> still reachable directly on the LAN and actions are recorded as `unattributed` rather
> than refused. A session with an animal in the chair must not stop because an intranet is
> down. Identity is an attribution mechanism here, never an authorisation one.

> **And the welfare exclusion above is unchanged and unaffected.** Reward, stimulation,
> session start and parameter changes are still not published as lab-host-protocol
> actions, for exactly the reason Plan 10 §4.1 states in its own first line. Attribution
> arriving *from* wl.works does not make wl.works an actor; the box authorises, and the
> box records who asked.

## Signing in from a rig's page: what b2b needs (new, 2026-09-29)

> **BUILT AND DEPLOYED BY wl-works ON 2026-10-02** (`4eb2c568`, merged that morning; their
> `HANDOVER-wl-expcontroller.md`, "wl.works' answer — signing in at a rig's page"). Read from
> their source the same day for b2b's design (`docs/superpowers/specs/2026-10-02-p4d2b-b2b-remote-signin-design.md`):
> `RIG_PAGES` entries `name=https://page/`, client `wl-works-rig-<name>`, **`scope=offline_access`
> alone** (their ruling 5 of 2026-10-01: with `openid` the `aud` becomes a list of two), `aud` the
> page's origin as a single string, a `name` claim, `typ: at+jwt`, RS256, one hour, renewal for 24
> hours from the sign-in at the rig. **No rig is in `RIG_PAGES` yet**: that waits on our XC-151
> (names and certificates) and XC-152 (the list). Backlog XC-102 and XC-147 to XC-149 closed.

> **RIG SIDE BUILT 2026-10-05** (b2b slice 2: `wlx serve --https`, `wl_xcon/signin.py`).
> Its page asks for `offline_access` alone, with no `prompt`. Nothing is configured in
> `RIG_PAGES` until XC-151 and XC-152.

> **TWO ASKS FROM THE RIG SIDE, 2026-10-05** (b2b slice 2's final review).
> - **A small `refreshTokenReuseInterval`** (backlog XC-225). wl.works sets none
>   (`@better-auth/oauth-provider` 1.7.1, read 2026-10-05), so a renewal whose answer is
>   lost in transit, by a network drop or a 5xx without CORS headers, is followed by the
>   page presenting the same renewal token again, which wl.works takes as a reuse and which
>   revokes that member's renewal tokens for that rig. A small reuse interval would let
>   that second presentation through. The page renews once at a time and stores each
>   new pair at once (b2b spec §4; `web._SCRIPT`'s `renew`), so only a lost answer reaches this.
> - **Refuse a rig page with a path.** `parseRigPages` (`src/lib/rigs.ts:95-104`, read
>   2026-10-05 at `e37847f4`) accepts an address with a path, such as
>   `https://rig-3.wl.works/console`. The rig refuses one in `--rig-page`, because `wlx serve`
>   serves its page at the root of the address only, so a sign-in returning to that path
>   would find no page. wl.works might refuse one too, so that the two cannot disagree.

> **DEPLOYED 2026-10-07** (wl.works production, about 09:12 CEST, wl-works commit `637007a7`, its
> stage 16a-1b; told to this repository by its session that day, not checked here): the renewal
> grace is 120 s (`refreshTokenReuseInterval: 120` on `mcp()`), and each `RIG_PAGES` entry must be
> the page's origin alone, with at most one trailing "/", a path, a query, an upper-case host or a
> spelled-out `:443` refused when wl.works starts. `RIG_PAGES` is still unset there: adding a rig is
> the step after XC-151 and XC-152. XC-225 closed; XC-241 no longer waits.

> **ANSWERED 2026-10-06: yes to both** (the PI's rulings in wl-works, its rig sign-in spec §11
> at `7ddf97be`, told to this repository by its session that day). Both are built as the first
> task of wl-works' 16a-1b, which was not yet planned or deployed that day. What follows is
> wl-works' reading of its own source, not checked here.
> - **The reuse grace.** The first ask's premise was half wrong: wl.works calls `mcp()`, and
>   `@better-auth/mcp` 1.7.1 sets `refreshTokenReuseInterval` to 30 s (its `dist/index.mjs:170`),
>   so the provider's 0 never applied. The page's retry 30 s after a failed renewal still lands
>   just past that. **Ruled: 120 s**, for every client (the option is global). Inside it, a
>   renewal token presented again gets the stored answer of the renewal already made; outside
>   it, a reuse still ends that client's renewals for the member (XC-225).
> - **The path.** `parseRigPages` refuses any address not written as its origin, optionally with
>   a final `/`, compared as written (so `/.` and `/%2e` are refused too). That is stricter than
>   `signin.parse_rig_page`, which also takes a query, an upper-case host and a spelled-out
>   `:443` (XC-240). wl.works refuses such an entry at boot. *(2026-10-07: XC-240 closed; `parse_rig_page`
>   now refuses whatever is not the origin as written, with or without a final `/`, as
>   `parseRigPages` does at wl-works' 637007a7.)*
> - **A suggestion, for us to weigh:** the page's renewal `fetch` has no timeout; an
>   `AbortController` would bound a connection dropped without an answer (XC-241).

> **ANSWERED 2026-09-29: yes to all four, with two conditions and three asks of us.** wl-works
> designed it with the PI the same day (wl-works `docs/superpowers/specs/2026-09-29-rig-sign-in-design.md`
> §8, approved in `e057946b` and the commit after; told to this repository by that
> session). **Built after wl-works' row 45a-2 and its sign-in rate-limit change**, ahead of its
> other January items; it will say when it is deployed.
> - **A client per rig**, never one for the fleet, seeded from one line of wl-works'
>   configuration per rig (a short name and the rig page's address): a public client, PKCE
>   required, consent skipped, `authorization_code` and `refresh_token`, scopes
>   `openid profile offline_access`. **Only https rig pages**; a rig taken out of the list is
>   switched off, not deleted.
> - **The return address** is exactly the configured page.
> - **Tokens for the rig:** request `resource=<the rig page's origin>` (e.g.
>   `https://rig-3.wl.works`); the access token is an RS256 JWT whose `aud` is that origin alone.
>   No other rig's client and no agent client can get it, and the agent API refuses it. **To
>   verify on the rig:** the signature against `https://wl.works/api/auth/jwks` (keys cached);
>   `iss` equals `https://wl.works/api/auth`, read from `/.well-known/openid-configuration`
>   rather than hard-coded; `aud` is the rig's own origin; `exp`. The member is `sub`; their
>   name as wl.works shows it is the `name` claim.
> - **The token endpoint** answers cross-origin for configured rig origins only, with no
>   credentials: a cookieless fetch.
> - **Condition A:** a member needs wl.works' new `control-rigs` permission, granted by an admin
>   to positions or tags (admins have it by default, nobody else does, never an agent), checked
>   at sign-in and at every renewal; without it wl.works shows a page telling them to ask an
>   admin.
> - **Condition B:** the access token lasts **1 hour**; the refresh token **24 hours**, and only
>   while the wl.works sign-in it came from is active. Signing out, "Done" on a shared iPad,
>   losing the permission or deactivation each stop renewal; a token already issued still works
>   at the rig until its hour ends, because the rig checks it offline.
> - **Asked of wl-xcon:** an **https certificate for each rig page** (one route: a name under
>   wl.works such as `rig-N.wl.works` pointing at the rig's lab address); **a sign-out on the
>   rig page**, because on a shared iPad the previous person's token otherwise lasts up to an
>   hour after "Done"; and **the list of rigs** (name and page address) for wl-works to
>   configure.
> - **Correction:** a route from the lab network to wl.works' private side is probably **not**
>   needed. The member's browser signs in at wl.works' public address as anywhere, and the rig
>   fetches keys from the public `https://wl.works/api/auth/jwks`. The proviso: the university
>   network must let `wl.works` through (KU Leuven's FortiGuard has blocked one of its domains
>   before).

**The design moved after the section above was written.** P4d-2b spec §5.0 and §5.7 (PI,
2026-09-27): people signed in to wl.works may send every control to a rig from its page,
reward size included (still capped by the rig's own approved ceiling), and **the browser
holds the wl.works access token and presents it with each command; the rig verifies it.**
The PI chose this over the rig holding its own sign-in session, knowing that a deactivated
account keeps working until its token expires. **For signed-in, attributed writes this
supersedes the line in `HANDOVER-wl-expcontroller.md` in wl-works** that reward, stimulation
and parameter changes need a person at the console. The rig PC keeps every control.

Read from wl-works' source on 2026-09-29, four things stand between a rig and that flow.
Each is yours to accept, amend or refuse:

1. **A registered client per rig, or one for the fleet** (as above, unchanged). Anonymous
   registration sits behind the loopback gate (the comment on the `mcp()` configuration in
   `src/lib/auth.ts`), so a rig cannot introduce itself; its client has to be seeded, as
   Zulip's is (`scripts/seed-zulip-client.ts`).
2. **A sign-in that returns to the rig's page.** `isAllowedAuthorizeRedirect`
   (`src/lib/loopback-redirect.ts`) delivers an authorization code only to a loopback
   address or to the one configured Zulip URL. A rig's page is reached by its registered name
   on the lab network, so each rig's callback URL would need to join the configured list.
3. **Tokens meant for a rig.** The `mcp()` plugin binds every issued token's audience to the
   MCP resource (`mcpResourceUrl()`; the plugin's own documentation, `@better-auth/mcp`'s
   `index.d.mts`: "Issued tokens are audience-bound to it"). A rig that accepted those tokens
   would accept every agent token minted for the MCP API, so it will not. It needs tokens
   whose audience is that rig (an RFC 8707 `resource` per rig), or an equivalent you prefer.
4. **The browser exchanging the code for a token.** Because the browser holds the token, the
   rig's page, on the rig's own origin, calls `/api/auth/oauth2/token` itself, as a public
   client with PKCE. **UNVERIFIED here:** whether that endpoint answers a cross-origin request
   from a rig's origin. If it does not, those origins would need allowing.

The rig verifies each token as an RS256 JWT against `/api/auth/jwks`, fetched while it can
reach wl.works and cached, so a token already issued keeps verifying through a short outage.

**And a route, which is infrastructure and the PI's:** the lab network has no route to
wl.works' WireGuard side today. The PI's permission for rigs to connect (2026-09-27) is a
permission, not a route.

**Nothing here makes wl.works load-bearing for a session.** A rig that cannot reach wl.works
still runs, and its own PC keeps every control; only remote, attributed control waits.

## wl-works runs an NTP server, and lab hosts synchronize to it (new, 2026-09-20)

**The ask: run an NTP server on wl-works at `ntp.wl.works`, reachable from the lab
network on UDP 123, and let a lab host initiate that one connection.** The hostname is
the PI's, named 2026-09-20; **the route is the part still open**, and it is the whole of
what this ask is now about. `ADR-0009` (this repository, 2026-09-20)
is the PI's decision behind it — welfare marks are now clock times (the out-of-cage
departure mark, among them) rather than intervals, and the daily fluid figure spans two
deployments, the rig and the cage-side kiosk, that cannot otherwise agree what "today" or
"09:15" means. Nothing currently guarantees they do; each host just keeps whatever clock
it booted with.

**Why this needs a routing change, and why it is narrower than it sounds.** §11.2's
topology — wl-works binds only to WireGuard, lab machines have no route in — is stated in
`docs/design/architecture.md` as an unqualified rule until this commit. NTP is
client-initiated: the lab host asks, the server answers. So a lab host reaching wl-works
for time needs a route to it that does not exist today, on UDP 123 only.

> **Updated 2026-10-11 — the hostname is not as settled as this section says.** wl-works' own sources give **three** names, and its handover asks which a lab host will be given; **wl-xcon asserts none of them.** `ntp.wl.works` is the PI's name (2026-09-20, as this section says). wl-works' `docs/ops/waiting-on.md` (lines 3552 and 3564) says `ptp.wl.works` serves NTP, and its row-60 spec (`2026-09-20-row-60-lab-time-service-design.md` §8) rules `time.wl.works`, over both `ptp.` and `ntp.`. Wherever this file or the backlog writes `ntp.wl.works` below, read it as "the PI's name, awaiting wl-works' answer". The route (a lab host initiating UDP 123, one port, one direction) is asked unchanged. XC-017, a preflight clock-skew check, waits on it.

> **Answered 2026-10-11 by wl.works** (noted 2026-10-31): **`time.wl.works`**, its owner's ruling of 2026-09-20 (its
> row 60 §8), `time.` over `ptp.` and `ntp.`; the two `ptp.` lines were stale and were struck that day. The route
> is not designed: how a lab host's UDP 123 to that name reaches the time appliance is row 60's plan's, and row 60
> is filed under its "Waiting on final hardware", since no appliance, switch, fiber or antenna exists. It calls
> this section's framing (one port, one direction, bookkeeping time, the rig's clock the floor) consistent with
> row 60. (Its handover, "XC-103 — the NTP hostname", lines 540-549; read 2026-10-31 at its `main` `b3c1b933`.) This repository's
> ADR-0009 and architecture.md still write `ntp.wl.works`, the PI's name of 2026-09-20. Backlog XC-103.

**This is not the AST guardrail changing.** `wl-preproc`'s "never initiates a connection"
check (`tests/test_cli_guardrails.py`, read from source 2026-09-20) is a static walk over
*application source*, asserting nothing in that package opens an outbound socket. A
system time daemon is a different layer — it is not application code the guardrail walks,
and this ask does not touch it. What changes is a routing/firewall rule: one UDP port,
one direction, one purpose.

**What this repository accepts, so wl-works does not have to guess.** An NTP client that
cannot reach its server keeps its own clock and drifts at ordinary rates; a multi-day
wl-works outage does not stop a rig session and does not invalidate a day's fluid
accounting. wl-works is not becoming load-bearing for a session by running this service,
on the same principle already established above for the console and its OAuth2 client:
the rig's own clock is the floor, and this only disciplines it. And this is bookkeeping
time, never the timing record — it sets which day it is and what a wall-clock mark reads,
never the alignment of neural data, which stays the sync box's hardware ticks and the
strobed event words. The welfare-action exclusion is unaffected: NTP is a clock source,
not an action, and is never published through the lab-host protocol.

~~**What we would still like verified, but are not blocked on.** `ntp.kuleuven.be`, KU
Leuven ICTS's own central NTP service, exists — verified 2026-09-20 against
`https://admin.kuleuven.be/icts/services/ntp` — but its reachability from the rig's
network segment is unverified.~~ **Closed 2026-09-20: the PI named `ntp.wl.works`, so
the ICTS service is checked and not chosen.** Its segment reachability stops being a
question because nothing is going to depend on it. The verification is kept, struck
through rather than deleted, because it is why the alternative was worth considering —
ADR-0009's *Alternatives considered* carries it. **Do not read this as the routing
question closing with it**: the lab host still needs a path to `ntp.wl.works` on UDP 123,
and that is item 5 below.

---

# OPEN — XC-288's training records: what the agent's file needs from wl-works (new, 2026-10-10)

Opened 2026-10-10 by XC-288 ([its spec](superpowers/specs/2026-10-10-xc288-training-records-design.md), approved by the PI that day), backlog XC-320. The
spec's wl-works asks are in its [§7](superpowers/specs/2026-10-10-xc288-training-records-design.md#7-which-build-carries-what); the reasons are in
[§3.8](superpowers/specs/2026-10-10-xc288-training-records-design.md#38-at-the-sessions-open), [§3.9](superpowers/specs/2026-10-10-xc288-training-records-design.md#39-experimenter-notes-and-welfare-observations) and
[§5.4](superpowers/specs/2026-10-10-xc288-training-records-design.md#54-rebuilding-and-versions). Read against wl-works at `71b04613` for the ELN's state, as the spec's
§3.9 records. Each is yours to accept, amend or refuse.

## The finding

Every session now ends with one self-describing file for an AI agent to learn from, built from the rig's own logs
([§5](superpowers/specs/2026-10-10-xc288-training-records-design.md#5-the-agents-file)). Most of it is the rig's. The part that is not is what the trainer saw and wrote
down: the animal's weight and water, the notes, the observations. Per §3.9, the ELN's per-session notes are
designed (its plan 11 and 16b, `animal_session`) and not built; nothing ties a note to a rig session; nothing
delivers notes to lab storage. Observations exist per animal, with when they happened and when they were written.

## The ask

**1. `prepare-session` (XC-100) carries more** ([§3.8](superpowers/specs/2026-10-10-xc288-training-records-design.md#38-at-the-sessions-open)). It already stages the
day's metadata and the fluid delivered so far. Added:

| Field | Why the rig wants it |
|---|---|
| The animal's **permanent id** (`animal.id`), beside the rig name | A rig name can be edited and reused in wl.works; the id never changes. Until it arrives, the record holds the rig name and the file is joined to the id at its build |
| **That day's weight with the date it was measured**, and the **water regime** | The record shows what the trainer saw. Until it arrives, the same facts are joined at the file's build |
| **Water entries** are not asked of `prepare-session`; they come by the read path in item 4. The **reward fluid** (type, dilution) is recorded by the rig itself at the open, so it is not asked of wl-works either | Named here so that nobody adds it |
| The lab's **people list with each person's account id** | Lets a change be attributed when nobody can sign in (spec §3.6): the person picks a name from the list and the row is recorded "not signed in", with why. Until it arrives the list is a file on lab storage kept by hand |

> **Superseded 2026-10-11 by wl.works' design** (noted 2026-10-31): `prepare-session` is withdrawn, and ask 1 is
> designed as part of the rig read, which the rig's own page, signed in through wl.works, calls at a session's
> open (wl.works' stage 10c-1, designed, not built; the note at the head of the metadata-bundle section above):
> the animal's permanent id and rig name; its newest weight with the date it was measured and who weighed it; its
> water state; and **the people list**: every active person (not a device, not banned, not deactivated) holding
> *Control rigs*, by an admin's role or a grant, each with account id and name, "replaced whole at every read, so
> the rig keeps the latest for the times nobody can sign in". Nobody signed in: nothing arrives, and the console
> uses the last people list it kept. A removed member's name stays in a rig's copy until its page next reads,
> wl.works' fifth `sever` exception. (wl.works' lab-host spec §2.2, §2.4 and §2.5, lines 182-198, 220-228 and
> 237-239; its handover, "The second brainstorm's answers", XC-320 (a), lines 638-640.) Until it is built and our
> page calls it, the list is the hand-kept file. Asks 2 to 5 were answered the same day in that handover's "The
> first brainstorm's answers" and "The second brainstorm's answers"; backlog XC-320 says how.

**2. The ELN's session keyed to the rig's session** (16b's `animal_session`; subject and session folder name).
Without a key, a note written after the session cannot be found from it.

**3. Each note with its own author and time**, not only whole-session revisions. The agent's file records who wrote
what and when, and says how recent its notes are ([§3.9](superpowers/specs/2026-10-10-xc288-training-records-design.md#39-experimenter-notes-and-welfare-observations)).

**4. A read path for one named lab workstation's own wl.works client** ([§5.4](superpowers/specs/2026-10-10-xc288-training-records-design.md#54-rebuilding-and-versions)).
Signed in as a member, it reads:

- a session's notes;
- an animal's observations and health over time;
- weights with their dates;
- the water regime and water entries (amounts, sources, supplements, ad-lib days);
- rig names over time, so a session is joined to the right animal by id on the day.

The file's rebuild writes a dated snapshot of what it fetched into the session's folder and builds from the folder
only, so the same folder always gives the same file. Notes are often written after the session, so a rebuild picks
them up; the read path is how.

**5. Days with no session, and why.** A record per animal per day of whether it trained, and why not ([§7](superpowers/specs/2026-10-10-xc288-training-records-design.md#7-which-build-carries-what)).
An agent that sees only sessions cannot tell a day of rest from a day of illness.

## What the PI ruled that bears on this

- **Account ids only, never names** (Q15, [§5.2](superpowers/specs/2026-10-10-xc288-training-records-design.md#52-what-it-holds)). The agent's file holds the wl.works
  account id of whoever acted, signed in or picked from the list. Names stay in wl.works and are looked up when a
  person needs them. This is why the people list carries ids.
  *Revised 2026-10-11*: the PI discussed it with wl-works ("wl-works and i discussed the id thing
  being too conservative. each person will have an id, but the name should also be present in places
  where who said or did something is useful"). Each person keeps a permanent account id, still the
  join key, and the person's name is also recorded wherever who said or did something is useful
  (changes, reasons, notes, marks), so the people list's names are recorded beside its ids, not only
  looked up ([§3.6](superpowers/specs/2026-10-10-xc288-training-records-design.md#36-who)
  and [§5.2](superpowers/specs/2026-10-10-xc288-training-records-design.md#52-what-it-holds)'s notes; decisions.md TRN-08).
- **The rig gets no new network route** ([§5.4](superpowers/specs/2026-10-10-xc288-training-records-design.md#54-rebuilding-and-versions)). The read in item 4 is not made
  by a rig and not by a wl-preproc host (which never initiates a connection). **It runs on one named lab
  workstation** with its own wl.works client and a member's sign-in. Everything the rig itself needs arrives with
  `prepare-session`, as above. *(2026-10-11: `prepare-session` is withdrawn; the rig's own page reads it from the
  rig read instead, the note under "The ask".)*
- **Changes need a wl.works sign-in** (Q7, Q8, [§3.6](superpowers/specs/2026-10-10-xc288-training-records-design.md#36-who)), which is the existing sign-in work
  (XC-151, XC-152) and not part of this ask.

## What is deliberately not asked for

- **No push to the rig, and no new route.** The rig still has no route in or out beyond what the sections above
  already settle; what it receives arrives with `prepare-session`, which wl-works sends as it does for the
  other fields. *(2026-10-11: wl.works sends a rig nothing; the rig's own page reads it, the note under "The
  ask".)*
- **Nothing welfare-affecting is published.** The standing exclusion above is unchanged: reward, stimulation,
  session start and parameter changes are not actions, and nothing here adds one. The weight, water and
  observation facts are read, not acted on, and the rig's welfare limits do not depend on them or on wl.works
  answering.
- **No names in the agent's file**, and so no request for wl-works to send them to the rig beyond the display
  name in the people list the picker needs.
- **No schema fixed here.** The rig's field names follow whatever `prepare-session` settles on. *(2026-10-11:
  they follow the rig read's; wl.works' lab-host spec §2.2: "The other field names are the plan's, agreed with
  wl-xcon.")*

**Nothing waits on an answer for a session to run.** Until each part is met the file says what it lacks (it
holds no ELN notes; it holds the rig name and not the id) and is rebuilt when it arrives.

---

## What wl-works must decide

1. Whether the client's host list becomes configuration. **Answered yes, 2026-08-31.**
2. **Answered 2026-08-31: yes to `prepare-session`, unrestricted; `export-session` was not answered (see the note in the first section).** Whether `prepare-session` and `export-session` are acceptable as published actions given
   the flat permission model, with the welfare exclusion above as a standing constraint.
   **Superseded 2026-10-11 for `prepare-session`**: wl.works withdrew it as a published action (its handover's
   answer 2, corrected that day, lines 68-70), and the rig's own page reads what it was to carry (the note at the
   head of the metadata-bundle section). `export-session` is still unanswered.
3. Whether a control box may register as an OAuth2 client of wl.works for operator
   attribution (above), and whether that is one client per box or one for the fleet.
4. Whether `planned_task` and `session_intent` are worth adding to a bundle that is already
   load-bearing on their side — their Plan 18b tests run against a fake, so the payload
   shape matters there before either machine exists. **Withdrawn 2026-10-01** (wl-works
   `6a57b1cc`, its montage-plan spec §1): both are plan fields, and nothing of a plan is sent.
   What stands of wl.works' answers of 2026-08-31: `prepare-session` (with no plan fields),
   the fluid figure as an envelope, the host list as configuration (item 1) and alerts.
   *(2026-10-11: `prepare-session` withdrawn, item 2; the envelope stands, read by the rig's page.)*
5. Whether wl-works can run an NTP server at `ntp.wl.works` reachable from the lab
   network on UDP 123, and open the one-port routing exception that requires (new,
   2026-09-20 — see above). **The hostname is the PI's; the route is not settled. As of 2026-10-11 wl-works names two other hostnames (see the update in the NTP section), and its answer is awaited on which a lab host is given.** *(Answered 2026-10-11: `time.wl.works`; the route is row 60's, waiting on its final hardware. The NTP section's note.)*
6. **Answered 2026-09-29: yes, with conditions (above).** Whether signed-in members may send controls to a rig from its page, and, if so, the four
   changes that needs: a client per rig, the rig's callback URL allowed, tokens whose
   audience is the rig, and the rig's page exchanging a code for a token (new, 2026-09-29 —
   see "Signing in from a rig's page"). **The permission for rigs to connect is the PI's and
   is given; the route is not built.**
7. **XC-288's asks (new, 2026-10-10; above).** Whether `prepare-session` may carry the animal's permanent id,
   the day's weight with its date, the water regime and the people list with account ids;
   whether the ELN's session can be keyed to the rig's and each note carry its own author and time; whether a
   read path for one lab workstation's own client is acceptable; and whether a record of days with no session
   and why is something wl-works can hold. **Answered 2026-10-11** (wl.works' handover, "The first brainstorm's
   answers" and "The second brainstorm's answers"): the first four designed, not built, the first as the rig read
   rather than `prepare-session` (the note under XC-288's ask); the last with no new record, an optional
   observation of a new kind, *Training*. Backlog XC-320.

Nothing here is blocked on an answer: the controller's v1 works with no ELN integration at
all, writing everything to the session directory as it would anyway. This buys the ELN
entry, not the recording.

---

# OPEN — The ELN's session-finish row: "fluid commanded", not "fluid delivered" (new, 2026-10-18)

Opened 2026-10-18 on the PI's decision, backlog XC-390. Raised with wl-works the same day, which answered and
queued a brainstorm on what a session's water entry records (its `ee9a58f0`); the PI's rulings on its answer were
relayed to it that day. Yours to accept, amend or refuse.

## The finding

A finished rig session reaches the ELN as a file in the session directory, ingested by `wl-preproc`
([S10 §4](superpowers/specs/2026-08-31-S10-data-and-lab-integration-design.md#4-the-lab-host-endpoint);
[controller architecture §12.3](superpowers/specs/2026-08-31-controller-architecture-design.md#123-wl-works-and-the-eln)).
Both tables labeled its fluid figure "fluid delivered". That figure is the session's commanded total: what the task
PC asked the pump for, reconciled against the sync box's delivered line. `wl-sync` stated on 2026-10-18 that the line
is the signal sent to the reward driver: "It is not a measurement of fluid. An unpowered or unplugged driver, an
empty reservoir and a blocked line all still record as delivered." The PI then ruled that it is **"A count of reward
commands"**: "Exact count of times the pump was told to run, hand rewards included. Multiplied by the pump's
calibration it gives fluid commanded, not fluid received, and the docs say so."
([S8 §5.1](superpowers/specs/2026-08-31-S8-session-management-design.md#51-fluid-is-reconciled-not-tallied)).

## The ask

**Wherever the ELN shows or stores a rig session's fluid figure from the session-finish row, label it "fluid
commanded", not "fluid delivered".** Asked whether the labels should say "fluid commanded", the PI answered on
2026-10-18 **"Say 'fluid commanded'"**: "Matches your decision that the total is fluid commanded. The ELN row's
label change is also sent to wl-works as an ask." wl-xcon's own specs carry the new label from the same day.

## Why

A label is a claim about the animal. "Delivered" reads as fluid the animal received, and this figure cannot show
that: the line sits before the pump, so a pump that did not run, an empty reservoir or a blocked line still counts
as a command. What the animal received is checked separately, by a reservoir reading at session start and end that
the session summary compares with the commanded total, warning if they disagree (the PI, 2026-10-18; XC-389, which he
requires before the first animal). That reading is not built yet and is not part of this ask.

## wl-works' answer (2026-10-18)

An ELN water entry (`animal_water_entry`) is water the animal **received**, to every reader: one figure, no status,
summed under water control against the animal's minimum, and raising or withholding the care staff's `water_short`,
`water_unrecorded` and `water_none_yet` warnings. So a commanded figure filed as water "would make a dry reservoir read
as a watered animal". It named what this touches in its own designs: its session-record spec §5.3, which files a
kiosk session's "delivered total" automatically as a *Kiosk* water entry; its handover's XC-320 (b), which asks
wl-xcon for that figure; the `fluid_delivered_today_ml` envelope, named *delivered*; and 11a-1's run water, typed by
a person, where someone copying the rig's display would file commanded as received. It recommended four rules (its brainstorm queue at `ee9a58f0`; the facts read at its
`153844d0`).

## The PI's rulings on it (2026-10-18)

He answered **"Agree"** to each of the four, and they were relayed to wl-works that day:

1. **A water entry always means water received, whoever writes it.** Commanded is the rig's own record, shown beside
   it and never summed in.
2. **Until the reservoir reading exists, nothing files water automatically.** The experimenter types what was
   received, with commanded shown beside it, labeled commanded.
3. **Once the reading exists, the reservoir drop is filed automatically as the water entry**, with commanded beside
   it. How wide differences are handled is designed in wl-works' brainstorm.
4. **Kiosks the same:** no automatic kiosk water entry from a commanded total.

**So wl-works' XC-320 (b) ask, that the kiosk publish each session's "fluid delivered", is superseded**: a kiosk's
figure is its commanded total, labeled so, and by rule 4 it is never filed as water automatically. The rig's side
of rule 3 waits on XC-389, which is also where the floor check moves to the reservoir drop once it is read (the PI,
2026-10-18, "Yes, use the drop once read").

## wl.works' answer (2026-10-19)

Its brainstorm on what a session's water records was ruled by the PI on 2026-10-19 (wl.works' spec
`docs/superpowers/specs/2026-10-19-a-sessions-water-received-and-commanded-design.md`; its handover's section
"2026-10-19: wl.works's answer on a session's water — four asks", read at its `main` `638697ab`, unpushed when read).
His four answers above stand. What he added there: **a wide difference is held for a person**: when the rig's session
summary says the reservoir drop and the commanded total disagree, by the threshold XC-389 sets (wl.works holds none of
its own), or a session arrives without that verdict, wl.works files no water and asks a person what the animal
received; **the drop files itself only when the end reading was entered by a `Member` signed in through wl.works**,
so until a rig has its https page (XC-151, XC-152) every session from it is held and its water typed by hand, as
today; water given outside the pump stays typed in wl.works beside the drop; fluid commanded is never typed there,
only shown, labeled *fluid commanded*, once read.

**Its four asks of wl-xcon**, filed: **1** a list of the rig's sessions, `GET /sessions?since=<cursor>`, with the
readings, the verdict and who entered the end reading, and whether a session can change after its end (XC-394);
**2** the kiosk's listing, the same less who entered the reading (XC-395); **3** the day's water envelope renamed
`water_received_today_ml`, and **4** its `complete` false while a session is held, read as absence (both on XC-100).
wl.works asked for no reply until this is taken up.

---

# OPEN — delivered 2026-10-11: what wl-works was asked, and what it listed as closed

On 2026-10-11 the PI decided to send every open ask to its sibling repositories ("Send all now"). The six below
are wl-works' section, in its order; each is wl-works' to accept, amend or refuse.

| Backlog | The ask | Blocks (wl-xcon) |
|---|---|---|
| XC-320 | The five parts of the XC-288 section above ((a) to (e)) | no build; the training-record file says what it lacks until each part is met |
| XC-099, XC-100 | wl-works answered yes to both on 2026-08-31 and has not built them (no code behind `manage-lab-hosts`). Asked: whether they are scheduled, so wl-xcon knows whether to code against a fake, and the envelope's field names once settled (the fluid figure as `value_ml`, `as_of`, `sources_included`, `complete`). XC-320 (a) rides on this | nothing |
| XC-103 | Which of the three NTP hostnames a lab host is given (see the NTP section's update), then the route | XC-017 |
| XC-104 | The alert half: wl-works said yes to the `state` reading and not yet to raising an alert, because its notification seam delivered nothing. Has that changed? The kiosk cannot initiate a connection, so the alert originates on wl-works' side; a local indicator at the cage is the complement and does not wait | nothing |
| XC-105 | Does the ELN record both ends of an out-of-cage interval as clock times, and when might the rig read them? The rig's own 8-hour limit stays the rig's. wl-works did not check this | nothing; the stand-in works |
| XC-098 | Does wl-works want to write `session_manifest.yaml`? The question is open with wl-preproc too (the XC-098 line in [the wl-preproc file](pending-wl-preproc-amendments.md#open--delivered-2026-10-11-engine-spec-21-and-the-older-backlog-asks)) | nothing |

> **Answered 2026-10-11** (noted 2026-10-31; wl.works' handover, "wl.works'
> answers to the open asks of 2026-10-11", lines 512-667, read at its `main` `b3c1b933`). **XC-099, XC-100**: code
> against a fake; the lab-host client is its Plan 10's stage 10a-1, in the fifth build of its order (lines
> 519-532); later that day `prepare-session` was withdrawn and the rig read designed in its place, the envelope's
> names standing (lines 630-637; the note at the head of the metadata-bundle section). **XC-105**: the ELN records
> both ends as clock times, each with who marked it (lines 597-601), and the rig's page reads the departure at the
> open and the return after (lines 641-645). **XC-320**: item 7 of "What wl-works must decide". **XC-103**:
> `time.wl.works`, the route not designed (lines 540-549; the NTP section's note). **XC-104**: yes, a kiosk
> answering `down` tells the animal's people once per episode (lines 654-657). The table above is kept as asked;
> XC-098's answer is in the same section of wl.works' handover.
>
> **Its asks of wl-xcon that day**, filed in the backlog on 2026-10-31: write the rig's and the kiosk's
> appendices of the lab-host protocol (XC-434; lines 626-629); publish `subject` and `out_since` readings when
> the console has had to ask (XC-435; lines 641-645); the kiosk answers `down` for a stop and a refusal as well
> as a fault (XC-436; lines 654-657); and the rig read's other field names agreed at 10c-1's plan (XC-437; its
> lab-host spec §2.2, line 197).

**Closed, per wl-works (not re-asked):** XC-102, XC-147 to XC-149, XC-225 and XC-240 (rig sign-in built and deployed,
`4eb2c568` and `637007a7`; only XC-151 and XC-152, wl-xcon's, stand between it and a live check); the host list,
`prepare-session` as a published action and the fluid envelope (yes, 2026-08-31; building is the XC-099/XC-100 row);
the plan fields and the calibration block (withdrawn 2026-10-01, XC-101); XC-104's reading half (yes, 2026-08-31).
XC-151 and XC-152 are stated as wl-xcon's own work and were not asked of wl.works. *(Later on 2026-10-11 wl.works
withdrew `prepare-session` as a published action; the note above.)*
