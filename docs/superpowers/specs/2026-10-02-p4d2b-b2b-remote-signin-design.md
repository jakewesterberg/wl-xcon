# P4d-2b b2b — Controls for People Signed In to wl.works

- **Status:** designed in conversation on 2026-10-02. The PI answered each question in the UI
  (quoted in §2) and approved the design in three parts ("Looks right" to each: serving and
  signing in, checking and recording, failures and testing and review), then the written spec
  ("Approve, write the plan"), all 2026-10-02.
- **Date:** 2026-10-02
- **Closes:** XC-015 (b2b) and XC-186 (a browser-driven test for the page's script).
- **Parents:**
  - the P4d-2b spec (`2026-09-26-P4d2b-browser-console-design.md`): §2's write rules, §5.0's
    rulings of 2026-09-27, and §5.7, which said b2b would be "designed in full as its own section
    when b2a has shipped". This is that design, in its own file; §5.7 points here.
  - S9a §6 (`2026-08-31-S9a-console-design.md`): `Verified` and `Local` as two types, the
    degradation made loud, and a token expiring mid-session interrupting nothing.
  - wl-works' rig sign-in spec (`wl-works/docs/superpowers/specs/2026-09-29-rig-sign-in-design.md`),
    §1-§3, §8 and §10, as **built and deployed to wl.works on 2026-10-02** (`4eb2c568`). Its
    source was read for this design, not its summary: `src/lib/rigs.ts`, `src/lib/rig-sign-in.ts`,
    `src/lib/rig-cors.ts`, `src/lib/rig-refusal.ts` and the access token's construction in
    `@better-auth/oauth-provider` 1.7.1 (`createJwtAccessToken`).
  - `docs/pending-wl-works-amendments.md`, "Signing in from a rig's page: what b2b needs".

## 1. Why

b2a gave the console page its controls, but only at the rig PC: `POST /commands` is accepted
from a loopback peer on the box's own page, and records the sender as a name typed into that
page, `NAME (box, unverified)`. Every other browser sees the controls greyed with *controls work
only at the rig PC until remote sign-in arrives*.

The PI ruled on 2026-09-27 that people signed in to wl.works get every control from the rig's
page, attributed to their account, with the browser holding the wl.works token and the rig
checking it. wl.works has now built its half: one public OAuth client per rig, a token whose
audience is that rig alone, and a token endpoint a rig's page may call. What is left is ours:
the page signs a member in, `wlx serve` checks the token, and the session records who acted as a
wl.works member rather than as a typed name.

## 2. Decided

- **Signed-in members get everything, sessions included** (the PI, 2026-10-02: "Everything").
  The 2026-09-27 ruling predates b3a's session controls. Asked again, the PI extended it: opening
  a session (its departure time), starting runs, ending a session (its return time) and resuming
  a stranded one, besides b2's run controls (settings with reward size, pause, stop, marks,
  scheduled stops, the manual reward while paused). The cost, put to him in the question: someone
  away from the rig could record that an animal left or returned. Each such entry is recorded
  under their wl.works account.
- **Sign-in goes straight through** (the PI, 2026-10-02: "Straight through"). A browser already
  signed in to wl.works comes back from wl.works without a password. The page always shows whose
  name its controls act under, with *Not you? Sign out*. The alternative, wl.works' `prompt=login`
  on every rig sign-in, was declined. On a shared iPad that means whoever is signed in to
  wl.works there; wl.works' own *Done* and its idle sign-out bound how long.
- **`wlx serve` checks the token and passes a typed actor to the rig** (the PI, 2026-10-02,
  approach 1 of three). Declined: keeping `by` a string such as `"Jake Westerberg (wl.works)"`
  (the record could not prove which account, and a name typed at the box could mimic one); and
  a web server such as Caddy in front of `wlx serve` for https (every network request would reach
  `wlx serve` from loopback, which is exactly what b2a's box check rests on).
- **Held from 2026-09-27 and 2026-09-29, not asked again:** the browser holds the token and
  presents it with each command; the rig verifies offline; a deactivated account's token works
  until its hour ends; https only; a sign-out on the page; the rig PC keeps every control.

**Engineering calls made in this design, stated so they can be overruled:** the rig PC's own
page stays plain http on loopback (§3), so an expired certificate can never lock out the person
at the rig; tokens live in the tab's `sessionStorage` (§4); a signed-out token is refused at this
rig for the rest of its hour, remembered in memory only (§5, §7); the rig compares `iss` itself
as well as through the library (§5); a command refused for its token is never re-sent by the page
(§4).

## 3. Serving: a second listener

`wlx serve` keeps today's listener exactly as it is: plain http at `--http HOST:PORT`, the rig
PC's own page with b2a's four box checks for writes, and reads open to the lab network.

**New, and all-or-none:**

```
--https HOST:PORT          the lab network's listener, TLS
--tls-cert FILE            the rig page's certificate chain (PEM)
--tls-key FILE             its private key (PEM)
--rig-page NAME=URL        this rig's entry in wl.works' RIG_PAGES, verbatim
--wl-works-issuer URL      https://wl.works/api/auth for the lab
--wl-works-cache FILE      where the discovery document and keys are kept
```

Any of them without the rest is refused at start, naming what is missing. Without any of them,
`wlx serve` is exactly what it is today, and remote sign-in is off.

- **`--rig-page` is copied from wl.works' configuration, not re-typed.** wl.works keys a rig on a
  short name and its page's address (`RIG_PAGES="rig-3=https://rig-3.wl.works/"`), derives the
  client id as `wl-works-rig-` + name (`RIG_CLIENT_PREFIX`, `src/lib/rigs.ts`), the token's
  audience as the address's origin, and the only return address as the address **compared as a
  string**. The flag takes the same entry and is parsed by `parseRigPages`' rules, mirrored: a
  name of lower-case letters and digits joined by single hyphens, at most 32 long; an absolute
  `https` address with no user name, password, fragment or comma. So `wl-works-rig-rig-3`,
  `https://rig-3.wl.works` and `https://rig-3.wl.works/` are this rig's client id, audience and
  return address, and a typo here fails the sign-in at wl.works rather than passing it somewhere
  else.
- **TLS** is the standard library's `ssl`, server side, TLS 1.2 at least. The certificate and
  key are read at start; a renewed certificate is taken up by restarting `wlx serve`, which, as
  b1 already says, changes nothing in `taskd`. **The handshake runs on the connection's own
  thread**, never on the thread that accepts connections, so one slow or stalled client cannot
  stop others connecting. The key's path is never logged and its contents never leave the file.
- **`Host`** on the https listener must name the page's host (with its port when the page's
  address carries one). Anything else is the JSON 421 b2a already answers.
- **Routes.** The http listener's, plus `POST /whoami` and `POST /signout` (§4). `GET /` with a
  query string serves the page, because wl.works returns the browser to the page's address with
  `?code=…&state=…` or `?error=…`. The server never reads, logs or echoes that query; the page's
  script consumes it. Every response on both listeners gains `Referrer-Policy: no-referrer`.
- **A write on the https listener** is accepted when all of these hold: `Origin` is exactly the
  page's origin; `Content-Type: application/json`; `Authorization: Bearer <token>` passes §5. The
  peer's address is not checked: the token is the authority there. **The body carries no `by`**;
  the actor is the token's (§6), and a body with a `by` is refused as a field the command does not
  take, the way b2a refuses any extra field.
- **The http listener refuses a command that carries an `Authorization` header**, with *sign-in
  works only on the rig's https page*. A box write is a box write; a token is never taken over
  plain http.
- **Content-Security-Policy** on the https page adds exactly the token endpoint's origin to
  `connect-src` (`https://wl.works`, from the discovery document, §5). Everything else is
  unchanged: one script by nonce, the bundled fonts, nothing else fetched. The sign-in itself is a
  top-level navigation to wl.works, which `connect-src` does not govern.
- **`web.CONTROLS_AT_THE_BOX`** (*"…until remote sign-in arrives"*) is a "not yet" whose wait
  ends here. On the http listener, a LAN viewer's greyed controls say *controls work at the rig
  PC, or signed in on this rig's https page* when `--https` is configured, and *controls work
  only at the rig PC* when it is not.

## 4. Signing in, on the page

The page's script does the OAuth exchange; Python renders everything a person reads, as b1
requires. The values the script needs are rendered into the page from §5's discovery: the
authorization and token endpoints, the client id, the return address and the resource.

**Three modes, rendered by Python and stated in the header** (S9a §6: the degradation is loud):

| Where | Header | Controls |
|---|---|---|
| The rig PC, `http://localhost` | *At the rig PC · names typed here are unverified* | b2a's, with the name prompt |
| The https page, signed in | *Controls act as NAME (wl.works) · Not you? Sign out* | live |
| The https page, signed out; any http page off the box | *Read-only · Sign in with wl.works* (https), or §3's sentence (http) | greyed |

The script switches between the second and third by one attribute on the page; the markup and
the greying are Python's and CSS's. NAME is the name `POST /whoami` returned, never a claim the
script read out of the token itself.

**Signing in.**
1. *Sign in with wl.works* makes a PKCE code verifier (32 random bytes, base64url) and its S256
   challenge (`crypto.subtle`, which needs the https page), and a random `state`; it keeps both in
   `sessionStorage` and navigates to the authorization endpoint with `response_type=code`,
   `client_id`, `redirect_uri` (the page), `scope=offline_access`, `resource` (the page's origin),
   `code_challenge`, `code_challenge_method=S256` and `state`. **No `prompt`** (§2).
2. wl.works signs the member in, or is already signed in, and refuses a member without
   `control-rigs`, an impersonated session and a shared device's own account on its own page
   (wl-works' rig sign-in spec §2 and ruling 7).
3. Back at the page with `?code&state`: a `state` that is not the one kept is refused (*this
   sign-in was not started from this page*) and nothing is exchanged. Otherwise the script posts
   the code, the verifier, the client id and the return address to the token endpoint as a
   form-encoded `fetch` with `credentials: "omit"` (the endpoint answers rig origins across
   origins and sends no credentials header: `src/lib/rig-cors.ts`), then removes the query with
   `history.replaceState`, and drops the verifier and `state`.
4. The access token, the renewal token and the access token's expiry (from `expires_in`) are
   kept in `sessionStorage`: they survive a reload of that tab, die with the tab, and are never
   shared with another tab.
5. `POST /whoami` with the token: the rig checks it (§5) and answers the name it will record, or
   the refusal's sentence. Only a token the rig accepts turns the controls on.

`?error=…&error_description=…` from wl.works shows its description and stays signed out.

**Renewing.** About five minutes before the access token's expiry (a housekeeping margin, not a
measurement), the script posts `grant_type=refresh_token`, the renewal token and the client id to
the token endpoint and keeps the new pair (wl.works rotates the renewal token). Before sending
any command it renews first if the token has less than a minute left, and on waking a tab whose
token has lapsed. **A refused renewal** — the sign-in at the rig is 24 hours old, the wl.works
sign-in ended, the permission was removed — shows wl.works' own `error_description` when the
response is readable, and the page returns to signed out.

**A command refused for its token is never re-sent.** The rig refuses it before queueing it, so
nothing happened; the page renews if it can and says so, and the person presses again. This keeps
b2a's rule that nothing on the command path re-sends any command, which a manual reward depends
on.

**Signing out.** `POST /signout` with the token: the rig refuses that token (`jti`) for the rest
of its hour (§5). The script then clears its `sessionStorage` whatever the answer, and the page is
signed out. **The renewal token is not revoked at wl.works**: its revocation endpoint answers no
rig origin across origins (`rig-cors.ts`: only `/oauth2/token` does), so the page could not know
whether a revocation worked, and the renewal token is gone with the storage that held it.

## 5. Checking a token, in `wlx serve`

A new module, `wl_xcon/signin.py`, used only by `wlx serve` and only when `--https` is given.

**Discovery and keys.** At start it reads `<issuer>/.well-known/openid-configuration` and
requires its `issuer` to equal `--wl-works-issuer` exactly (OpenID Connect Discovery 1.0 §4.3).
It takes `authorization_endpoint`, `token_endpoint` and `jwks_uri`, each of which must be https,
and reads the keys. Both documents are written to `--wl-works-cache` (whole-file replace, so a
crash mid-write leaves the old cache). Read live on 2026-10-02: issuer
`https://wl.works/api/auth`, endpoints `…/oauth2/authorize` and `…/oauth2/token`, `jwks_uri`
`…/jwks` holding four RSA keys with `alg` RS256, and `code_challenge_methods_supported`
`["S256"]`.

- **wl.works unreachable at start:** the cache is used, and its `issuer` must equal the flag's.
- **No cache either:** every command from the network is refused with *the rig has not reached
  wl.works to check sign-ins; use the rig PC*, and a background thread retries every 60 s
  (housekeeping) until the keys arrive. The rig PC's page is unaffected.
- **Keys used:** RSA keys whose `use` is absent or `sig` and whose `alg` is absent or `RS256`.
  Anything else in the set is ignored.
- **Outbound requests** go only to the discovery document and the key set, over https with the
  system's certificate checks and a 5 s timeout (housekeeping). The rig needs a route to
  wl.works' public address, which wl-works expects the university network to allow
  (`pending-wl-works-amendments.md`, "Correction").

**A token** (`Authorization: Bearer`, at most 8 KiB) is accepted when every check passes, in
this order:

1. Its header: `alg` is `RS256` (never `none`, never an HMAC algorithm keyed on a public key);
   `typ` is `at+jwt` (wl.works' `JWT_ACCESS_TOKEN_TYPE`, RFC 9068 §2.1; `application/at+jwt`
   also accepted); `kid` names a key held. **An unknown `kid`** fetches the key set again, at
   most once a minute, and is refused if still unknown, so a key wl.works rotated in is picked
   up and a stream of junk ids cannot make the rig fetch on every request.
2. Its signature, with PyJWT: `algorithms=["RS256"]`, `audience` the page's origin with
   `strict_aud` (a single string, equal; wl.works sends one audience as a string,
   `toAudienceClaim`, and its own test pins `aud` to the origin), `issuer` the discovered one,
   `exp`, `iat`, `sub`, `aud`, `iss` and `jti` required, and 60 s of leeway on the times
   (housekeeping; the rig keeps time from wl-works' NTP server, ADR-0009).
3. **`iss` compared again by `signin.py`, exactly.** PyJWT 2.10.0 compared a string issuer as a
   substring (`payload["iss"] not in issuer`, its `_validate_iss`, read from the 2.10.0 wheel on
   2026-10-02), so `https://wl.works` would have passed for `https://wl.works/api/auth`. 2.10.1
   compares it exactly; the floor is 2.10.1 (§9), and the second comparison costs nothing.
4. `azp` is this rig's client id, and `client_id`, when present, is too. A rig token carries both
   (`createJwtAccessToken`). Only the rig's own client can get the rig's audience, so this is
   belt and braces; it also turns a misconfigured `--rig-page` name into a refusal that says so.
5. `name` is a non-empty printable string within `link.TEXT_LIMIT`, and `sub` is non-empty.
6. `jti` has not been signed out at this page.

A pass yields `link.Member(name, account=sub, issuer=iss, token_id=jti)` and the token's
expiry. A failure is a 401 with `{"status": "refused", "said": …}` and one plain sentence:
*sign in with wl.works to use the controls* (no token), *this sign-in was signed out here*,
*your sign-in has expired; sign in again* (also renewing first, §4), *this sign-in is for
another rig*, *the rig's clock and this sign-in disagree; check the rig's time* (`iat` in the
future), *this is not a wl.works sign-in the rig accepts* (signature, issuer, algorithm, type,
unknown key), or the keys-unavailable sentence above. Nothing from the token is echoed.

**Signed out.** `POST /signout` checks the token as above and, if it passes, adds its `jti` with
its expiry to a set held under a lock; entries are dropped once expired. A token that does not
pass needs no signing out, and the answer is the same either way. **The set is memory only**: a
restart of `wlx serve` forgets it, and the browser that signed out has already discarded the token.

## 6. Who: two actor types, through the wire, the record and the page

**Two types in `link`** (*amended 2026-10-04: built in `wl_xcon/actor.py`, which `link` imports; plan Ruling 1, so `bounds` stays pure*), as S9a §6 designed them, frozen:

- `Box(name)` — a name typed at the rig PC's page, `wlx console --as`, or a `wlx run`/`wlx
  taskd` terminal's `--as`. Its empty name stays allowed exactly where the terminal's rules allow
  it today (a confirmation given without `--as`).
- `Member(name, account, issuer, token_id)` — made only by `wlx serve`, after §5.

`Actor = Box | Member`. **Every command's `by` is one or the other.** On the wire it is a tagged
map: `{"kind": "box", "name": "jake"}` or `{"kind": "member", "name": "Jake Westerberg",
"account": "<wl.works user id>", "issuer": "https://wl.works/api/auth", "token_id": "<jti>"}`. A
bare string `by` is refused, as `link._actor` refuses a missing one today.

- **`taskd` and the service pass the actor through unchanged.** Every record row that has a `by`
  writes the actor's map. **The token itself is never written anywhere**; its `jti` is the token
  id, which ties a row to a token without being one.
- **Readers of a record accept a string `by`** as written before this change, shown as it was
  (`resume.py`'s *session ended by …* sentence today). A record is never rewritten.
- **Shown as** *NAME (wl.works)* for a member and *NAME (box, unverified)* for a box, by one
  function used by the page, `wlx console` and every sentence that names an actor, and **marked
  differently on the page** (the box form set apart), so a box name typed to look like a member's
  still reads as a box name.
- **Telemetry schema 13 → 14.** `Refused.by`, `Staged.by`, `ScheduledStop.by` and the control
  events' `by` carry the actor's map. A schema-13 reader refuses schema 14, as §3 of the P4d-2b
  spec already rules.
- **The trust boundary does not move.** `taskd`'s command socket stays loopback-bound, so a
  process on the rig PC could still send a `Member` it made up, as it can send any `Box` today.
  The rig PC is trusted; what b2b adds is that nothing off the rig PC can act without wl.works
  vouching for it.
- **Welfare-critical code carries the actor.** `welfare`, `bounds`, `marks` and `stranded`, and
  the listed functions in `taskd`, `service` and `cli`, take `by` and write it into their rows.
  Only its type and its written form change, never a rule; those lines come to the PI with §10's
  summary. The welfare-critical list is unchanged.

## 7. When things fail

| What | What happens |
|---|---|
| wl.works down, keys cached | Signed-in pages keep working until their hour ends (the check is offline). Renewal fails and the page signs out with the reason. The rig PC is unaffected. |
| wl.works never reached, no cache | Network commands refused with the keys-unavailable sentence; retried every 60 s. The rig PC is unaffected. |
| wl.works rotates its keys | An unknown `kid` fetches the key set once (at most once a minute). |
| A token expires during an action | Refused before queueing; nothing on the rig changes; the session never notices (S9a §6). The page renews and the person presses again. |
| A member is deactivated or loses `control-rigs` | wl.works refuses their next renewal; their current token works at the rig until its hour ends (accepted 2026-09-27). |
| The rig's clock is off by more than the leeway | Tokens refused as expired, or with the clock sentence; ADR-0009's NTP keeps it right. |
| `wlx serve` restarts | Signed-out tokens forgotten (§5); pages reconnect their event streams as today and keep their tokens; `taskd` unaffected. |
| The certificate expires | Browsers refuse the https page; the rig PC's http page is unaffected. Renewing it is XC-151's. |

## 8. Testing (sim first, no network)

- **A fake wl.works in the tests**: an RSA key generated at test time, a discovery document and
  key set shaped like the live ones read on 2026-10-02, and tokens the tests mint. `signin.py`
  takes its fetch as a seam, so unit tests need no server; one test runs the real fetch against
  a loopback https server with a test certificate authority, so the path the rig uses is
  exercised too.
- **A self-signed certificate** for the https listener, generated at test time with
  `cryptography`.
- **`signin.py`:** each check in §5 refusing on its own (no token, expired, `iat` in the future,
  another rig's `aud`, a list `aud`, wrong issuer and a substring of it, wrong `azp`, `alg`
  `none`, HS256 signed with the public key's bytes, wrong `typ`, unknown `kid` with the refetch
  and its rate limit, a key of the wrong type, missing `name`/`sub`/`jti`, oversized token, signed
  out); discovery's issuer mismatch; the cache written, read back and refused when it names
  another issuer; the keys-unavailable state and its retry.
- **`serve`:** the https listener's `Host`, `Origin`, `Content-Type` and `Authorization` rules; a
  `by` in a member's body refused; the http listener refusing a token; `/whoami` and `/signout`;
  `GET /?code=…` serving the page without echoing the query; `Referrer-Policy`; the
  `connect-src` origin; the flags' all-or-none refusal and `--rig-page`'s parse refusals.
- **End to end:** a real session and a real `wlx serve --https`, driven with a member's token: a
  setting (reward size included), a pause, a manual reward while paused, a mark, a scheduled
  stop, and from `wlx taskd` an open with its departure, an end with its return and a resume.
  Each is recorded under the member's map, shown *(wl.works)* in the feed, and the token appears
  in no file the session wrote.
- **In a real browser (closes XC-186):** Playwright with headless Chromium drives the https page
  against a fake authorization endpoint (which redirects back with a code) and token endpoint:
  sign in, the header naming the member from `/whoami`, a command, a renewal (with a short-lived
  token), a refused renewal showing its sentence, a `state` mismatch refused, and sign-out after
  which the rig refuses the old token. The harness is then there for XC-191's script defects.
- **The no-leak test** gains `jwt` and `cryptography`: blocked in a subprocess, `link`, `taskd`,
  `cli` and `serve` without `--https` still import and run.
- **The mutation gate** over every changed module, read line by line (trap 7), and
  `tools/mutate.py --all signin` before its tests are trusted.
- **On the hardware list**, because it needs XC-151's certificate and a rig in wl.works'
  `RIG_PAGES`: one live sign-in at a real rig page, with a token wl.works issued.

## 9. Dependencies (ADR-0004 entries, with the build)

- **`signin` extra: `pyjwt[crypto]>=2.10.1`** — PyJWT (MIT) verifies the RS256 access token; its
  `crypto` extra brings `cryptography` (Apache-2.0 OR BSD-3-Clause). Licenses read from PyPI's
  JSON (`info.license_expression`) on 2026-10-02: PyJWT 2.15.1 `MIT`, cryptography 50.0.2
  `Apache-2.0 OR BSD-3-Clause`. **2.10.1, not 2.8**: `strict_aud` is present from 2.8.0 at least
  (its `jwt/api_jwt.py`, read 2026-10-02), but 2.10.0's issuer check is the substring one in §5.
  An extra, imported only by `serve --https`, so a rig that takes no remote control installs
  neither, as `console` keeps transport off a terminal-only rig.
- **~~`dev` gains~~ A `browser` extra holds `playwright`** (Apache-2.0; PyPI, 1.63.0, read
  2026-10-02) for §8's browser test, and CI's pytest job installs headless Chromium for it.
  Never installed on a rig. *(Amended 2026-10-02 by the plan, its Ruling 6: all three CI jobs
  install `dev`, and only the pytest job needs a browser, so its own extra keeps the mutation
  jobs from downloading it.)*
- TLS is the standard library's `ssl`; the OAuth exchange runs in the browser. Nothing else.

## 10. Human review before merge

Welfare-critical by CLAUDE.md (who can command reward and the out-of-cage marks, and the type of
`by` in listed code), given to the PI as numbered items in plain terms:

1. Members with wl.works' `control-rigs` permission can use every control from any browser:
   sessions (with departure and return times), runs, settings including reward size (still
   capped by its approved ceiling), and the manual reward. Each is recorded under their wl.works
   account.
2. A command from the network is accepted only with a valid wl.works token for this rig;
   anything else changes nothing.
3. Sign-out on the page stops that token at this rig at once. Otherwise a token works until its
   hour ends, even after its member signs out of wl.works or is deactivated (accepted
   2026-09-27).
4. No token problem and no wl.works outage can stop or pause a session, and the rig PC keeps
   every control.
5. In the welfare-critical modules and functions, `by` changes from a name to one of the two
   actor types and is written as its map; no rule changes. The lines are listed for him.

> **Slice 1 answered 2026-10-05.** Item 5 went to the PI as seven plain items: the two kinds of
> actor, and that nothing signs a member in before slice 2; no welfare rule changes (26 lines,
> type, written form and one default only); a blank name still refused for an amendment, in
> the same words; the process's own rows record nobody; a bare-text `by` refused, changing
> nothing; records from before b2b read back, resume and end with their names as written; a
> typed name never shown as a member. He approved all seven ("Approve all seven"). He was first
> asked on 2026-10-04 by a question that pointed at a list it never showed. His answer then was
> the same, but it is not the record. Items 1-4 are slice 2's, asked at its review. The
> welfare list is unchanged.

## 11. Outside this repository

- **wl-works**, when b2b is built: that the rig side exists, and that its page asks for
  `offline_access` alone with no `prompt`, as its §10 ruling 5 expects. The list of rigs
  (XC-152) waits on their names and addresses (XC-151).
- **wl-preproc**: nothing. It reads no `by` from our record (its `origin/main`, searched
  2026-10-02).

## 12. Out of scope

- **Certificates and names for the rig pages** (XC-151), and **the list sent to wl-works**
  (XC-152). b2b is built and tested with a test certificate and ships switched off until both
  exist.
- **A session summary that says its welfare actions were unattributed** (S9a §6's last
  sentence on loud degradation): b2b records each action's actor type; the summary line is
  XC-216.
- **A Stop jumping the command queue** (XC-121). The P4d-2b spec §5.2 had placed it with b2b;
  b2b changes nothing on the command path past the token check, and it stays its own item.
- **Revoking the renewal token at wl.works on sign-out** (§4: no answer the page could read).
- **Remembering signed-out tokens across a restart** (§5).

## 13. Build order

Two slices, so the change to welfare-critical code is reviewed apart from the new code that uses
it:

1. **The actor types** (§6): `Box` and `Member` on the wire, through `taskd`, the service and the
   record, telemetry schema 14, the two forms on the page and in `wlx console`. No new behavior:
   every actor is still a `Box` when this slice ends, and the suite proves the record and the
   feed unchanged in meaning. §10 item 5 is reviewed here.
2. **Signing in** (§3-§5, §7, §8): `signin.py`, the https listener, the page's sign-in, the
   browser harness, the `signin` and `dev` extras. §10 items 1-4 are reviewed here.
