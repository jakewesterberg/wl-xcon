# ADR-0011: Display color calibration records are JSON files, one per calibration, never executed

- Status: Accepted 2026-10-08, by the PI in his answer to the engine B plan's Q4
- Date: 2026-10-08
- Deciders: PI

## Context

Engine build B (plan `docs/superpowers/plans/2026-10-08-engine-b.md`) makes every session check its
colors against a display calibration: the one the rig names, or the default, the sRGB standard, when
it names none (engine spec §7.1). The spec fixes what a calibration holds and where it lives, not the
file it is written in: **the transfer is a measured table per channel** and there is **one calibration
for the whole panel** (§7.6); **a calibration never expires** but carries its age, and past 30 days it
is a warning (§7.10); the instrument is a spectroradiometer, driven from the console in build J (§12.1);
and **records are committed per rig under `docs/measurements/<rig>/`, each with an id** (§12.6), in the
`<rig>/<YYYY-MM-DD>/` folders `docs/measurements/README.md` already asks for. Build J's tool will write
these records; a session reads the one its rig names, and a session on the default reads none.
CLAUDE.md sends file-format decisions through an ADR.

Before build B a `photometry.Calibration` existed only as Python built in tests, with a `gamma`
exponent nothing read. The rig's other settings are Python files executed at load: `tasks/rig.py`, the
animal's `bounds.py` and `settings.py`.

**The question put to the PI** (the plan's Q4, 2026-10-08, through the question box; the record is in
the plan's "Questions for the PI" and the engine brainstorm notes' "The morning after"):

- **A (recommended): one JSON file per calibration**, under `docs/measurements/<rig>/<YYYY-MM-DD>/`,
  read with the standard library and never executed. Unknown fields are refused, so the field list
  grows with builds A2 and J.
- **B: a Python file like `tasks/rig.py`.** As readable, but loading it runs it.
- **C: YAML, as wl-preproc's eye calibration is.** As asked: "Adds a dependency to this repository
  (PyYAML is wl-preproc's, not ours)." *Corrected here, not in the question as it was put:* PyYAML is
  already in this repository's optional `contract` extra, there so the contract tests can import
  wl-preproc's own YAML reader (`pyproject.toml`); C would make it a dependency of a running session.

**His answer:** "JSON data file (Recommended)": A, one JSON file per calibration, never executed. In
answering he accepted the choice, so this ADR is written as Accepted. B and C were declined.

## Decision

**A measured display color calibration is one JSON file, one object, read by
`wl_xcon.photometry.read_calibration` with the standard library's `json` and never executed.** The rig
file names it: `Rig.calibration` (`wl_xcon/geometry.py`) is the record's path, relative to the rig
file's folder unless absolute, or `None` for the default (`photometry.SRGB`, which is code, not a
record). `tasks/rig.py` names none until build J measures the panel.

**The record's fields** (`photometry.RECORD_FIELDS`, each required, plus one optional):

| Field | Holds |
|---|---|
| `id` | Text: not empty, at most `photometry.ID_LIMIT` (64) characters, every character printable, no whitespace at either end. `config.json`, each run's start row and telemetry name it, and the age warning quotes it in a sentence the page's open sends back (the plan's call 25). |
| `measured_on` | The day it was measured, `YYYY-MM-DD`, a real calendar day; its age is counted from it on the rig's local calendar. |
| `observer` | Text naming whose luminous efficiency the luminances were measured against. |
| `primaries` | `red`, `green` and `blue`, each once, each `[x, y, Y]`: a light a display makes (x at least 0, y above 0, x + y at most 1 within `photometry.TOLERANCE`, Y above 0), the three not on one line in xy. |
| `background` | `[x, y, Y]`, the reference background it was measured at; Y may be 0 (black, spec §7.5). |
| `transfer` | `red`, `green` and `blue`, each once, each a list of at least two `[level, fraction]` pairs: levels from 0 to 1 rising strictly, fractions never falling, from 0 or above to 1 at full drive. Stored and checked; evaluated from build A2. |
| `max_cone_contrast` | **Optional.** A positive number (or `null`), the panel's measured cone-contrast reach. Absent or `null`, the record states no DKL limit, and its DKL colors are refused until build A2 converts DKL through cone fundamentals (the plan's call 17). |

Every number is a finite JSON number, never `true` or `false`. **Nothing is filled in.** A record is
refused, with a sentence naming why, when a field is missing, when it has any other field, when a name
appears twice at any level, when a value is not what its field holds, when it is not JSON or not one
object, when it is nested too deep to parse, and when the file is larger than
`photometry.RECORD_LIMIT` (1 MiB). **A record the rig names and that will not load is never replaced
by the default**: `wlx check` and `wlx run` refuse outright, and `wlx taskd` keeps the sentence, never
stops on it, takes opens, ends and returns as before, and fails every run's pre-flight on it (the
plan's calls 19-20).

## Alternatives considered

- **A Python file like `tasks/rig.py`** (Q4-B): lost because loading it runs it. A calibration record
  is data a program writes, from a measurement, and reading it should be able to run no code; the rig
  file and the animal's files stay Python because a person writes them and reviews them.
- **YAML, as wl-preproc's eye calibration is** (Q4-C): lost because it would make PyYAML a dependency
  of a running session for no gain over JSON, which the standard library reads.

## Consequences

- **The field list is provisional.** Builds A2 and J add measured spectra and cone fundamentals, and
  because a record carrying a field it does not know is refused, **each of them amends this ADR's
  list** in the build that adds the field (the plan's "What the PI should know", item 5). A2 also
  replaces `max_cone_contrast` with its full conversion (spec §7.4).
- A record cannot carry a field `read_calibration` ignores, so two programs cannot disagree about one
  silently; the cost is that an older reader refuses a newer record outright.
- Each record holds its own transfer tables: the sRGB curve at all 1024 levels on each channel is
  132,160 bytes (computed 2026-10-08, `photometry.RECORD_LIMIT`'s comment), well under the 1 MiB limit.
- The color calibration's id is not wl-preproc's `SessionManifest.stimulus_calibration_id`, which S4 §9
  reserves for a stimulus calibration covering geometry, care features and ABL coupling, waiting on V1
  and V9 (the plan's call 15; S4 §9's dated note).
- Follow-up: build J writes records in this form; until then no record exists, and every session runs
  on the default with its warning.
