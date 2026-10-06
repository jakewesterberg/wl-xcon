# P4d-2b b2b-ready: the rig's https page, ready to switch on

**Status:** designed 2026-10-06, both halves approved by the PI in conversation ("Looks right");
built on branch `b2b-ready`, 2026-10-06;
this written spec is for the PI's review. It builds on
[the b2b spec](2026-10-02-p4d2b-b2b-remote-signin-design.md) (slices 1 and 2, on `main` since
2026-10-06) and amends it where §6 below says.

## 1. Why

b2b slice 2 built the rig's https page and shipped it switched off. Its final review left eight
items in the backlog. The PI ruled one of them, **XC-226**, must be fixed before any rig switches
its https page on, and chose on 2026-10-06 to fix all eight together, before the page is used:

| Item | Today |
|---|---|
| XC-226 | A bad https setup at a restart refuses all of `wlx serve`, the rig PC's page included. Start also waits on wl.works (two fetches, each up to `signin.FETCH_TIMEOUT_S`) before anything is served. |
| XC-227 | A page served before the rig has wl.works' keys offers no sign-in until it is reloaded. |
| XC-228 | The key set is never fetched again unless a token names an unknown key, so a key wl.works withdraws stays trusted until a restart. |
| XC-232 | When wl.works answers as another issuer, the page and every refusal say "the rig has not reached wl.works", which is untrue. |
| XC-229 | A renewal that hangs keeps the page reading signed in past its token's lapse, and a press waits on it. |
| XC-230 | Any renewal answer without a token, a server error included, signs the page out at once with most of the hour left. |
| XC-231 | Two sentences mislead: a renewal the rig could not confirm leaves the page reading signed in forever with a generic sentence on every press; and the rig's `expired` with wl.works out of reach makes the page say it renewed. |
| XC-224 | A duplicated tab copies `sessionStorage`, so two tabs hold one renewal token, and the second to renew ends the member's sign-in in both. |

In none of these is anything wrong sent to the rig. What is at stake is the rig PC's page staying
up, and a member's page telling the truth.

## 2. Decided

- **The rig PC's page always starts** (the PI, 2026-10-06, of three: "Always start the rig PC
  page"). Nothing about the https page can stop `wlx serve`; the https page is off, with its
  reason in the terminal and on the rig PC's page. Declined: refusing a typo in the https flags
  at start as today (a typo made while editing a start-up command would still take the rig PC's
  page down); and serving the https page from a program of its own (two programs to start and
  watch on every rig).
- **The server half and the page half** (§3, §4) as presented, each approved ("Looks right").

**Engineering calls, stated so they can be overruled:** the key set is fetched again every 15
minutes (`signin.KEY_REFRESH_S`, housekeeping, not a measurement); a page with no sign-in
available asks again every 60 s, the keys thread's own interval; a tab waits up to 1 s for its
sign-in's lock before calling itself a duplicate (§4.5); the rig's word on a token's expiry wins
over the page's clock (§4.4).

## 3. The server half (`wlx serve`, `signin`)

### 3.1 The rig PC's page always starts (XC-226)

`run()` keeps one rule for the rig PC page's own setup: `--http`, `--link`, the health token and
`--stale-after` are refused before anything binds, as today. **The six https flags are never a
refusal.** Their checks run in this order, and the first that fails turns the https page off
with its sentence:

1. all six given together (naming what is missing);
2. the `signin` extra installed;
3. `--rig-page` and `--wl-works-issuer` parse (`signin.parse_rig_page`, `signin.parse_issuer`);
4. the certificate and key load (`tls_context`);
5. the https port binds.

The sentences are today's refusals, unchanged in substance. **Off** means: `wlx serve` serves the
rig PC's page exactly as without the six flags, and says so:

- **in the terminal**, at start: `wlx serve: the rig's https page is off: <reason>`, beside the
  startup line, which then says controls work only from the rig PC's own browser;
- **on the rig PC's own page** (the box's browser), a static line rendered by Python: *the rig's
  https page is off: <reason>*;
- **to a viewer on the lab network** over http, `web.CONTROLS_AT_THE_BOX` (*controls work only at
  the rig PC*), not `CONTROLS_ELSEWHERE`, since no https page is serving.

`WITHOUT_HTTPS` and `_https_refused` go: no refusal needs them. A busy https port is not retried;
it is off until the next restart, like every other reason.

*(Amended 2026-10-06, the final review: check 2 has a second sentence, for an extra that is
installed and will not load, which slice 2 let stop `wlx serve` rather than call it not
installed: "the signin extra is installed but could not be loaded (`<error type>` from
`<module>`)".)*

### 3.2 wl.works is asked after binding (XC-226)

`_https_setup` no longer calls `Checker.load()`. The https page binds and serves at once, and
**the keys thread** (`wlx-serve-keys`) does the first load as soon as `wlx serve` starts, then
keeps going:

- **Without keys**, it loads again every `RETRY_EVERY_S` (60 s), from wl.works or else the
  cache, as today.
- **With keys**, it fetches the key set again every `KEY_REFRESH_S` (§3.3).
- It prints the first outcome to the terminal (`wlx serve: sign-in keys from …`, or the
  keys-unavailable sentence), and again whenever the rig goes from no keys to keys or back.
  Each retry that changes nothing prints nothing.

Until the first load returns, the https page is served in its keys-unavailable mode, and
commands from the network are refused with that sentence (b2b spec §5, unchanged).

### 3.3 The key set is refreshed (XC-228)

Once the rig holds keys, the keys thread fetches `jwks_uri` again every `KEY_REFRESH_S` = 900 s.
A set holding at least one usable key **replaces** the held set and is cached beside the held
discovery document, so a key wl.works withdraws is refused within 15 minutes. A fetch that
fails, or a set with no usable key, **keeps** the held keys (an outage behaves as b2b spec §7
says). The discovery document is not fetched again; the endpoints rendered into open pages stay
valid until `wlx serve` restarts. The unknown-`kid` refetch (b2b spec §5, at most once a minute)
is unchanged.

### 3.4 Why the rig cannot check sign-ins (XC-232)

`Checker` keeps the reason it holds no keys: **not reached** (`NO_KEYS`, as today) or **another
issuer**: wl.works answered, and its discovery document names an issuer other than
`--wl-works-issuer`. The second has its own sentence, `OTHER_ISSUER`:

> this rig's wl.works setting does not match wl.works; use the rig PC

Both are refused with the reason word `no_keys`, so the page treats them alike (b2b plan, Ruling
8). Only the sentence differs. The https page's keys-unavailable mode and every network refusal
give the sentence that is true now. The terminal keeps its longer sentence naming both issuers.

### 3.5 The unavailable answer comes first

`Checker.check` answers *cannot check sign-ins* (`no_keys`, §3.4) before looking at the token at
all. Today a request without a token is told *sign in with wl.works to use the controls* even
when the rig could not check one if it came. The order of b2b spec §5's numbered checks is
otherwise unchanged. §4.6 relies on this order.

## 4. The page half (the https page's script)

The script stays what b1 made it: it renders nothing a person reads; every sentence is
Python's or one of the script's named constants. b2b's rules all stand:
- one renewal at a time;
- `generation` makes a sign-out stand against a renewal in flight;
- a renewed pair is stored at once;
- a command refused for its token is never re-sent;
- the lapse sign-out of slice 2's final review (I1).

### 4.1 Every stuck state ends at the lapse (XC-229, XC-231)

**A sign-in the page holds ends when the access token it holds lapses, unless a renewal has
replaced that token by then**, whatever is in flight: a renewal still hanging, a confirmation the rig never gave. The page signs
itself out at the lapse, on its own, with the reason that applies:
- wl.works was not reached (`UNREACHED`, as today);
- or the rig did not confirm the renewed sign-in.

*(Amended 2026-10-06 by the plan's Ruling 2: a renewal begun at or after the lapse is given
`RETRY_MS`, and a lapse with no renewal in flight renews once more first, unless the rig never
confirmed the sign-in.)*

A press waiting on a renewal gets its answer at the lapse at the latest. The renewal's late
answer, if one comes, is dropped (`generation`). **The renewal token is not presented again**
after a hang, so a lapse never risks the reuse XC-225 describes.

### 4.2 Only wl.works' own refusal is a refusal (XC-230)

A renewal answer ends the sign-in only when wl.works refuses it: **HTTP 400 or 401 with a JSON
body whose `error` is a string** (RFC 6749 §5.2's error response). Then the page signs out with
`error_description`, as today. Any other answer without a new token is treated like no answer:
- a server error;
- a body that is not JSON;
- JSON without a token or an `error`.

The sign-in stays, and the renewal is tried again until the lapse (§4.1, b2b spec §7).

*(Amended 2026-10-06, the final review: §4.1's lapse has a third reason, a renewal wl.works
answered without a token and without refusing it (`NOT_RENEWED`): "wl.works did not renew this
sign-in before it lapsed; the rig PC's page keeps every control". Until then the page keeps the
sign-in and says (`BUSY`): "wl.works could not renew this sign-in just now; trying again until it
lapses". A page served without keys (§4.6) has no token endpoint and never asks for a renewal: it
keeps a stored sign-in while its token has time left, its controls grayed, and waits for §4.6's
reload to confirm it. A token with more than a minute left is asked about once at load, and the
page then says "signed in, but not usable now: " and the rig's sentence. At the lapse it signs out
with the sentence it shows in place of the sign-in.)*

Trying again after a server error presents the same renewal token, which wl.works may already
have spent. With wl.works' reuse interval at 0 (XC-225, asked of wl-works 2026-10-06), the next
answer is then `invalid_grant` and the page signs out. That is today's outcome, reached later and
truthfully.

### 4.3 A renewal the rig has not confirmed (XC-231)

When wl.works renews but `/whoami` cannot reach the rig, the page keeps the new pair (already
stored, b2b) and the member's name in its header. It greys the controls with:

> this rig has not confirmed the sign-in; trying again

*(Amended 2026-10-06 by the plan's Ruling 1: covers every confirmation the rig cannot give, a fresh
sign-in's and a reload's too.)*

It asks the rig again every 30 s (the script's `RETRY_MS`, not `serve.RETRY_MS`, which is the
event stream's). A press in that state sends nothing and says that
sentence. Confirmation brings the controls back. The lapse (§4.1) bounds the wait.

*(Amended 2026-10-06, the final review: a confirmation the rig answers `no_keys` or `clock`, as in
a restart's window without keys (§3.2), keeps the sign-in, grays the controls with "signed in, but
not usable now: " and the rig's sentence, and is asked again every `RETRY_MS` too, on a page that
can renew. A page served without keys waits instead for §4.6's reload.)*

### 4.4 The rig's word on expiry wins (XC-231)

When the rig refuses a command as `expired` while the page still counts time left, the rig's
offline check is the authority. The page treats the token as lapsed now and renews:
- **it got a new token:** it says, as today, *this sign-in was renewed; the command was not sent:
  send it again*;
- **wl.works could not be reached:** the token has lapsed, so the page signs out with `UNREACHED`;
- **wl.works refused:** the page signs out with wl.works' sentence.

It never says *renewed* without a new token.

### 4.5 One sign-in per tab (XC-224)

Each sign-in gets a random id, kept with it in `sessionStorage`. The tab that holds the sign-in
holds a Web Lock (`navigator.locks`) named by that id for as long as it is open, and releases it
when the sign-in ends.
- **A page loaded with a stored sign-in** asks for its lock, waiting up to 1 s.
- **Granted:** a fresh tab, or a reload. Within the wait, the old document's lock has gone.
- **Not granted:** another open tab holds this sign-in, so this tab is a duplicate. It forgets
  its copy **without** `POST /signout`, which would end the original tab's sign-in too. It shows
  read-only with:

  > this sign-in is in use in another tab; use that tab, or sign in again here

Signing in again gives the duplicate a sign-in of its own (a new renewal family at wl.works).

**Probed 2026-10-06** in Playwright's Chromium 153 and WebKit 26.6, on an https page:
- `navigator.locks` is present;
- a second tab finds a held lock taken, at once and after a 1 s wait;
- ten reloads in each engine all re-acquired it, with and without the wait.

Safari's own *Duplicate Tab* (copying `sessionStorage`) is not driven by Playwright and stays a
check by hand (§7). A browser without `navigator.locks` skips the check and behaves as today.

### 4.6 A page without sign-in recovers by itself (XC-227)

An https page served in its keys-unavailable mode posts `/whoami` with no token every 60 s. The
answer is `no_keys` while the rig still cannot check sign-ins (§3.5), and `no_token` once it can.
On `no_token` the page reloads itself, and Python renders it with *sign in with wl.works*. A
stored sign-in in that tab is confirmed on the reload, as on any reload.

## 5. When things fail (amends b2b spec §7)

| What | What happens |
|---|---|
| The https setup is broken at a start or restart (any of §3.1's five) | The rig PC's page serves as without the https flags; the https page is off; the terminal and the rig PC's page say why. `taskd` unaffected. |
| wl.works unreachable at start | Both pages serve at once; network commands refused with the keys-unavailable sentence until the keys thread has keys (60 s retries, the cache first). |
| wl.works answers as another issuer | As unreachable, with `OTHER_ISSUER` on the page and in each refusal. |
| wl.works withdraws a key | Refused within `KEY_REFRESH_S` of the withdrawal. |
| A renewal hangs, or the rig never confirms one | The page signs out at the token's lapse with the reason; nothing is sent. |
| wl.works answers a renewal with a server error | As unreachable: kept, retried until the lapse. |
| A tab is duplicated | The duplicate forgets its copy and says so; the original keeps working. |

## 6. Amendments to the b2b spec (made with the build, dated)

- **§3:** "Any of them without the rest is refused at start, naming what is missing." The https
  page is off instead, naming it (§3.1 here).
- **§5:** "At start it reads `<issuer>/.well-known/openid-configuration`." The keys thread reads
  it after binding (§3.2). The key set is also fetched every `KEY_REFRESH_S` (§3.3). The
  unavailable answer comes before the token's checks (§3.5). An issuer mismatch has its own
  sentence (§3.4).
- **§4:** "never shared with another tab". It now holds, by §4.5. A refused renewal is defined
  by §4.2.
- **§7:** the rows of §5 here.
- `serve.run`'s docstring: "Every refusal is a sentence, and all of them happen before anything
  binds" holds for the rig PC page's setup only.

## 7. Testing (sim first, no network)

- **`signin`:**
  - the unavailable answer before the token (a request with no token while not ready is `no_keys`);
  - `OTHER_ISSUER` after a mismatch, and `NO_KEYS` after a failure to reach wl.works;
  - the keys thread: the first load after start, the retry, and the refresh that replaces the keys;
  - a failed refresh and an empty set keep the held keys;
  - a withdrawn `kid` is refused after a refresh;
  - the terminal lines on a change only.
- **`serve`:**
  - each of §3.1's five failures leaves the http listener serving the rig PC's page, says why in
    the terminal and on that page, and gives a LAN viewer `CONTROLS_AT_THE_BOX`;
  - the https page served before the first load, in its keys-unavailable mode;
  - no fetch to wl.works before binding;
  - the slice-2 tests that pinned `WITHOUT_HTTPS` reworked to pin this.
- **In a real browser** (`tests/test_page_browser.py`), one test each:
  - a hanging renewal signs out at the lapse, and a waiting press resolves then with nothing sent
    (§4.1);
  - a 503 and a non-JSON renewal answer keep the sign-in and retry, and a 400 `invalid_grant`
    signs out with its description (§4.2);
  - an unconfirmed renewal greys the controls with its sentence and recovers on confirmation
    (§4.3);
  - the rig's `expired` with wl.works unreachable signs out with `UNREACHED`, never "renewed"
    (§4.4);
  - a duplicate, made by copying a signed-in tab's `sessionStorage` into a second tab before its
    script runs, forgets its copy, says so and posts no `/signout`, while the first tab still
    acts; and a reload keeps its sign-in (§4.5);
  - a page served without keys reloads into *sign in with wl.works* once the fake wl.works is
    reachable (§4.6).
- **The browser engine is a setting:** `WLX_BROWSER=webkit` runs the browser tests in WebKit
  (default `chromium`). CI stays on Chromium; the WebKit run is local, once per change to the
  page script, and its result is recorded in the CHECKPOINT entry.
- **Every new or reworked test is proven able to fail** against the change it pins, and the
  mutation gate covers every changed module.
- **By hand, with XC-223's live check:** in Safari, on a signed-in rig page, *Window › Duplicate
  Tab*: the duplicate says §4.5's sentence.

## 8. Review before merge

No welfare-critical function changes: `taskd`, `welfare`, `bounds`, `link._setting` and
`web._hand_reward_now` are untouched, and the command path past the token check is b2b's. The
plan names the functions it changes. Because XC-226 is the PI's ruling, and because what members
can do stays exactly as approved on 2026-10-05, the PI gets a short plain summary before merge:
1. the rig PC's page always starts;
2. every stuck sign-in ends at its lapse, sending nothing;
3. one sign-in per tab;
4. nothing a member can do, and no limit, changes.

## 9. Out of scope

- Certificates and names for the rig pages (XC-151), the list sent to wl-works (XC-152), and the
  live sign-in (XC-223).
- wl.works' renewal-token reuse interval (XC-225): asked of wl-works on 2026-10-06.
- Retrying a busy https port; fetching the discovery document again while running (§3.3).
- Revoking the renewal token at wl.works on sign-out, and remembering signed-out tokens across a
  restart (b2b spec §12).

## 10. Build order

One slice on branch `b2b-ready`, subagent-driven as b2b was, the server half first:
1. `signin` (§3.2-§3.5);
2. `serve` (§3.1, §3.2);
3. the page's lapse, renewal and confirmation rules (§4.1-§4.4);
4. the per-tab lock and the self-recovering page (§4.5, §4.6);
5. the browser setting and the docs: b2b spec amendments, `architecture.md`, and the backlog
   closing XC-224 and XC-226 to XC-232.
