# Code rules — common principles, a standard ruff configuration, language and environment profiles

Task **C89** (the size ratchet: **C91**). Status: **decided (§9, two rounds)** —
[ADR 0014](../decisions/0014-code-rules-catalog-and-language-profiles.md), D2-48 Pending; slices 1–2
of §11 are in the tree. The rule source is the
[Google Python Style Guide](https://google.github.io/styleguide/pyguide.html); section numbers
below (`§2.12`) are that guide's.

## 1. Essence

Adopt the Google Python Style Guide as akmon's code standard, and put each rule where it can be
enforced rather than where it is easiest to write down:

- a **principle that holds in any language** goes into the common guardrail;
- a **rule a standard linter can check** goes into that linter's configuration — akmon's own is
  `profiles/ruff.toml` — and is never restated as prose, because a check beats prose;
- what is **specific to a language or to the environment the code runs in**, and no linter can
  see, goes into that language's or environment's **profile**.

akmon ships **no linter of its own**. A project's rules and style are its own: `akmon check` runs
the checks the project declares — its linter with its settings — and a project that has none is
offered ruff with akmon's rules, set up the standard way (`extend`). ruff and uv stay akmon's
development dependencies; a consumer takes ruff only by choosing akmon's rules.

## 2. As-is

- [`_common.md`](../../guardrails/_common.md) held the process floor (language, secrets, commits,
  analysis before mutation, delegation) and three code rules — reuse, API shape, don't duplicate
  what the code states — with no design principles.
- `guardrails/python.md` (52 lines, removed by slice 1) named uv, ruff and pytest as the baseline
  toolchain and listed five generic code rules — telling a consumer which tools to use.
- [`profiles/`](../../profiles/) held one domain profile, `quant`.
- akmon's own ruff selects `F E W I UP B`. On a consumer, nothing akmon shipped ran any check.

**Good:** small; nothing to configure. **Bad:** the code rules were prose loaded into every
session and enforced by nothing; the Python guardrail prescribed tools to consumers; akmon's own
code was not held to the standard it ships.

## 3. The placement rule

Applied to each rule, in order:

1. **Can a standard linter decide it from the source, with few false positives?** → **checked**:
   in the linter's configuration. Prose may cite the linter's code; it does not restate the rule.
2. **Does it hold in any language?** → a **principle** in `_common.md` § Code design.
3. Otherwise → the **profile** of the language or environment it belongs to — including every
   Google rule no linter covers, which is then a review point.

A rule may have both halves: the principle "failure is raised, never returned" is common prose;
its mechanical part, ruff's `E722` and `BLE001`, is checked.

**Layout is the formatter's** — line length, whitespace, blank lines, import order, one statement
per line (§3.1–3.6, §3.13, §3.14). akmon's `ruff.toml` carries akmon's choices for them; a project
with its own formatter keeps its own.

## 4. Profiles — languages, environments, domains

| kind | attached | examples | reaches the agent as |
|---|---|---|---|
| **language** | automatically, by the language the project is written in | `python` | `@`-import (always on) |
| **environment** | automatically, by where some of the code runs — paths named beside the import | `python-stdlib` (a bare interpreter, before any venv); `python-service` (an async server) when one is needed | `@`-import (always on) |
| **domain** | opt in, by need | `quant`, `crypto` | a link |

An environment profile layers on its language profile with what that environment demands; for
`python-stdlib` that is standard-library-only code, a review point since no linter checks it.
The guardrails directory now means one thing: the floor that binds every project whatever its
language.

**Layout:**

```
guardrails/_common.md          the floor + § Code design (language-agnostic principles)
profiles/python.md             language profile — Python prose no linter sees
profiles/ruff.toml             akmon's Python rules — a standard ruff configuration
profiles/python-stdlib.md      environment profile — code that runs on a bare interpreter
profiles/quant.md              domain profile, unchanged
```

`guardrails/python.md` went. `bin/sync.py::imported_standard_files` and package-mode
materialization cover `profiles/` (an imported profile is materialized at
`<AITNA_ROOT>/.akmon/profiles/`, as a guardrail is); `common/materialization.py::stale_materialized`
covers both directories and TOML; the `init` block's example import, `ARCHETYPES.md`'s map,
`MODEL.md` §5, `meta/CONCEPT.md` §5, `README.md` and the role docs follow.

**Migration.** A consumer that imports `guardrails/python.md` gets a plan error from `sync`
naming the replacement line, in every mount mode — the check now reads a mounted consumer's
`@`-imports too, where an unresolvable one was silent before. The edit is the consumer's, one
line, listed in the bump procedures (`BOOTSTRAP.md` §E, §F) and the changelog.

**Rejected:** keeping `guardrails/python.md` as the language file (two meanings for one
directory) and a one-release alias for the old path (two paths for one file).

## 5. akmon's rules — `profiles/ruff.toml`

A plain ruff configuration: the strict group set measured in the
[baseline](../reviews/c89-python-rule-baseline-20260913.md), plus `BLE` and `D` with
`convention = "google"`, each group annotated with the Google sections it carries; `TD002` and
`TD003` ignored because Google's TODO carries a link, not an author; relative imports banned
outright; test ignores as `**/`-globs; `line-length = 120`; and no `target-version`, so ruff
takes it from the project's `requires-python`.

It runs with or without akmon, the two standard ways:

- `ruff check --config <path to profiles/ruff.toml> .`
- `[tool.ruff] extend = "<path>"` in the project's own configuration, which then adjusts it the
  standard way — `extend-select`, `extend-ignore`, `per-file-ignores` — never in akmon's file.

**Measured on ruff 0.15.21** before building on it: a project whose `pyproject.toml` extends a
configuration in a subdirectory keeps that file's `**/test_*.py` and `conftest.py` ignores for
its own tests, and its `requires-python` still sets the target version.
`meta/tests/test_ruff_profile.py` carries both.

In package mode the path `extend` names must live in the repository — the same reason the
guardrails are materialized — so `sync` reads the project's ruff configuration
(`bin/sync.py::ruff_extends`) and materializes an extended `profiles/ruff.toml` at
`<AITNA_ROOT>/.akmon/profiles/ruff.toml`, banner as a TOML comment, kept fresh like a profile.
An `extend` of a file the standard does not ship is a plan error; an `extend` of the project's
own file is none of akmon's business.

## 6. Classification — every rule and its layer

Layers: **C** common principle · **K** checked by ruff, in `profiles/ruff.toml` · **P** profile
prose (a review point) · **F** formatter. The two count columns are the
[C89 baseline](../reviews/c89-python-rule-baseline-20260913.md): the attached consumer (key rules),
akmon (strict set). `–` = not measured; `†` = an upper-bound heuristic.

| § | rule | layer | ruff | consumer | akmon |
|---|---|---|---|---|---|
| 2.1 | a suppression names its rule | K | PGH003, PGH004 | 0 (PGH003) | 0 |
| 2.2 | import the module, not the symbol (`typing`, `collections.abc` exempt) | P | — | 774† | 117† |
| 2.2 | no wildcard import | K | F403 | 0 | 0 |
| 2.3 | absolute imports by full package path | K | TID252, every relative import | 0 | 0 |
| 2.4 | failure is raised, never returned; catch only where you can act; keep the protected region small | C | — | – | – |
| 2.4 | no bare `except:` | K | E722 | 0 | 0 |
| 2.4 | no `except Exception` that does not re-raise | K | BLE001 | 14 | – |
| 2.4 | no catch-all `except` that only passes | K | S110 | 0 | 0 |
| 2.4 | `assert` is not validation (outside tests) | K | S101 | 0 | 0 |
| 2.4 | re-raise with the cause (`raise … from`) | K | B904 | 0 | 0 |
| 3.16 | an exception's name ends in `Error` | K | N818 | 3 | 1 |
| 2.5 | no mutable global state | C + K | PLW0603 | 2 | 0 |
| 2.6 | nest a function only to close over locals; hide with `_`, not by nesting | P | — | – | – |
| 2.7 | a comprehension has one `for` and at most one `if` | P | — | 1 | 12 |
| 2.8 | default iterators (`for k in d`, not `d.keys()`) | K | SIM118 | 0 | 0 |
| 2.9 | a generator documents `Yields:` | P | — | – | – |
| 2.10 | no lambda bound to a name; no `map` over a lambda (`filter` too — P) | K | E731, C417 | 0 | 0 |
| 2.11 | a conditional expression only when each part fits one line | P | — | – | – |
| 2.12 | no mutable default argument | K | B006 | 0 | 0 |
| 2.13, 3.15 | `@property` only for a cheap derived value; no trivial getter/setter | P | — | – | – |
| 2.14 | `is None`, never `== None`; no comparison to `True`/`False` | K | E711, E712 | 0 | 0 |
| 2.14 | implicit false: `if seq:`, not `if len(seq):` | K | PLC1802 | – | – |
| 2.17 | no `@staticmethod` — a module function; `@classmethod` only as a named constructor | P | — | 22 | 2 |
| 2.18 | concurrency at the edges; never rely on a built-in being atomic; hand data over through a queue | C + P | — | – | – |
| 2.19 | no power features (`exec`/`eval` checked; metaclass, `__del__`, dynamic dispatch — P) | C + K | S102, S307 | 7 | 0 |
| 2.20 | `from __future__ import annotations` for forward references | P | — | – | – |
| 2.21, 3.19.1 | the public API is annotated | K | ANN | 91 | 12 |
| 3.19 | signatures take abstract parametrized types; builtin generics | P | — | – | – |
| 3.19.5 | `X \| None` explicitly, never an implicit Optional | K | RUF013 | 0 | 0 |
| 3.1–3.6, 3.13, 3.14 | layout: line length, whitespace, blank lines, import order, one statement per line | F | E501, E7, I, W | 2 632 over 80 | 5 849 over 80 |
| 3.7 | a shebang only on an executable | P | — | – | – |
| 3.8 | public API documented; comments say why, not what | C + K | D, google convention | 38 | 162 |
| 3.10 | no string accumulated with `+=` in a loop | P | — | 1 | 0 |
| 3.10.1 | a logging call takes a pattern and arguments, never an f-string | K | G, LOG | 0 | 0 |
| 3.10.2 | an error message states the actual condition and names the value | C | — | – | – |
| 3.11 | a resource is released by a scope (`with`) | C + K | SIM115 | 0 | 0 |
| 3.12 | a TODO carries a link: `TODO: <link> - <text>` (the form checked, the link P) | C + K | TD | 11 | 0 |
| 3.16 | names say what, without abbreviation or type | C | — | – | – |
| 3.16 | PEP 8 casing; no dashes in module names | K | N | 0 | 1 |
| 3.16.1 | no single-character names beyond `i j k v e f _` | P | — | – | – |
| 3.17 | an executable keeps its logic in `main()` behind the `__main__` guard | P | — | – | – |
| 3.18 | small, focused functions (Google's ~40 lines — P) | C + K | C901 ≤ 10, PLR09xx | 23 | 63 |
| — | blocking I/O inside `async` is offloaded | K | ASYNC | 0† | 0 |
| — | code on a bare interpreter imports the standard library only | P (env) | — | – | – |
| 4 | be consistent with the surrounding code | C (exists) | — | – | – |

Four design principles have no Google number and go to **C**: data or behaviour, never half of
each; a contract carries a typed object, not a stringly map; return a value or mutate state, and
say which in the name; configuration is read at the entry point and passed down. Their Python
realization — a frozen `dataclass`, `NamedTuple` or `TypedDict` inside, validation models on the
boundaries — is **P**.

## 7. `akmon check` and the project's choice

**`akmon check` runs what the project declares** (`bin/check.py`, `common/check_runner.py`;
mounted: `python3 <AITNA_ROOT>/akmon/bin/check.py`):

```toml
[check]
ruff = "uv run ruff check {files}"
types = { command = "uv run mypy {files}", files = ["*.py"] }
```

- `{files}` becomes the files a run covers: `.` for the project, or under `--changed` the files
  that differ from `HEAD` (plus new, unignored ones, never `<AITNA_ROOT>/`) matching the check's
  `files` patterns — `*.py` when none are named. A check with no matching change is skipped; a
  command without the placeholder runs unchanged.
- Each command runs in the project root without a shell; its output passes through untouched,
  and its result is one finding (`check.run`): `ok`, or `error` with the exit code. A command
  that is not installed is an `error` naming it. Exit 1 when any check fails or cannot run.
- `[check]` is read through `common/record.py::read_akmon_toml_strict`, strictly: a malformed
  entry is an error and is not run. No table at all is a `warn` — nothing ran.
- `verify` validates the table (`check.config`) and runs nothing, so a bump never fails CI on
  code it did not touch. The pre-commit pipeline's lint step is `akmon check --changed`.

**`init` decides once what it runs** (`src/akmon/_init.py::_setup_checks`):

| the project has | default | recorded |
|---|---|---|
| a ruff, flake8, pylint or mypy configuration (`ruff.toml`, `[tool.ruff]`, `.flake8`, `[flake8]` in `setup.cfg`/`tox.ini`, `.pylintrc`, `[tool.pylint]`, `mypy.ini`, `[tool.mypy]`, `[mypy]`) | `own` | one check per tool found, through the project's manager (`uv run` with `uv.lock`, `poetry run` with `poetry.lock`) |
| none | `akmon` | `ruff = "<manager> ruff check {files}"`, and a standard `extend` of akmon's rules added to `[tool.ruff]` in `pyproject.toml` — or to `ruff.toml`, written when neither exists |

It asks when it can (an interactive terminal, no `--yes`), `--checks own|akmon|none` decides
without asking, and a non-interactive run takes the defaults. A record that already has `[check]`
is left alone — a realign never changes the choice. On `akmon`, an `extend` the project already
has is never replaced (ruff takes one; `init` names the line to change), and when ruff is not
declared `init` names the command that adds it (`uv add --dev ruff`, `poetry add --group dev
ruff`). Nothing is written on `own` or `none`.

## 8. akmon's own configuration

- akmon's `pyproject.toml` extends `profiles/ruff.toml` (slice 3), so akmon runs exactly the
  rules it offers; `line-length = 120` is a recorded override of Google's 80 (5 849 of akmon's
  lines are over 80, 709 over 100). Beside the `extend` it sets only `allowed-confusables` (`ℹ`,
  the notice glyph akmon's hooks print) — no rule, ignore or per-file exception of its own; a
  carrier holds it to that.
- **Deliberate exceptions** are inline — `# noqa: CODE — reason` on the line, never a per-file
  ignore that would also hide the next, accidental one: a function-level import kept off the
  per-tool-call hook path or keyed by the one-reader carrier (`tomllib`, C83), and a broad
  `except` at a crash-open hook entry or a seam that never raises. Never for the size family: a
  size limit is met, not waived, and its carrier runs with `--ignore-noqa`.
- **Rollout.** 361 findings under the strict set at the design measurement, 386 under the
  profile as shipped. The size family — C901 16, PLR0912 8, PLR0913 6, PLR0911 4, PLR0915 4 —
  are refactors of load-bearing code (`sync`, `verify`), not lint fixes: everything else lands
  with slice 3, the size family is **C91**. C91 first listed the 22 remaining file-and-rule
  pairs in `[tool.ruff.lint.extend-per-file-ignores]` — `extend-`, since a plain
  `per-file-ignores` replaces the profile's test-file ignores — then brought each one under its
  limit; the table is gone.

## 9. Owner decisions

Decided by the owner (this session); recorded in
[ADR 0014](../decisions/0014-code-rules-catalog-and-language-profiles.md) and D2-48.

**First round.**

1. **Profiles layout** — language and environment rules move to `profiles/`; `guardrails/`
   keeps the universal floor (§4).
2. **akmon's rollout** — everything but the size family now; the size family is **C91** (§8).
3. **Line length** — akmon keeps 120.
4. A separate check with per-rule severities in `.akmon.toml` — **superseded** by the second
   round.

**Second round** — "no reinvented wheel; the standard approach is best":

5. **No linter of akmon's own.** The first round's AST checker was built, run on both trees
   ([baseline addendum](../reviews/c89-python-rule-baseline-20260913.md)) and withdrawn.
6. **akmon's rules are a standard ruff configuration** that also runs without akmon (§5).
7. **`akmon check` is a wrapper** over the project's own checks; their output as is, plus one
   finding per command (§7).
8. **`init` offers the choice** — the project's own linter by default when it has one; ruff with
   akmon's rules, set up the standard way, when it has none (§7).

## 10. Not carried

- uv, or any package manager, as a requirement on a consumer.
- A rule configuration of akmon's own beside the linter's: a project tunes akmon's rules in its
  own ruff configuration.
- Parsing each linter's output into findings.
- A whole-tree lint sweep as a precondition of adopting the rules: `--changed` is the pre-commit
  scope.

## 11. Slices

1. **Placement** — in the tree. `_common.md` § Code design; `profiles/python.md`,
   `profiles/python-stdlib.md`; `guardrails/python.md` removed; `sync`, materialization, `verify`,
   `init` and the docs follow. Carriers: an imported profile is materialized and kept fresh; the
   old import is a plan error naming the fix, in package and mounted mode.
2. **Rules and the wrapper** — in the tree. `profiles/ruff.toml`; `akmon check` over `[check]`;
   `init --checks`; `sync` materializing an extended rules file; `verify` validating `[check]`;
   the pre-commit step. Carriers: D2-48.
3. **akmon's own ruff** — `pyproject.toml` extends `profiles/ruff.toml`, the fixes outside the
   size family, and the per-file exceptions C91 then shrinks. After the owner's commit of 1–2.
4. **The size ratchet** — **C91**.
