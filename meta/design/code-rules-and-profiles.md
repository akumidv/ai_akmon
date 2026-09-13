# Code rules — common principles, checked rules, language and environment profiles

Task **C89** (the size ratchet: **C91**). Status: **decided (§9)** — [ADR 0014](../decisions/0014-code-rules-catalog-and-language-profiles.md),
D2-48 Pending; the slices of §11 land in order. The
rule source is the [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html);
section numbers below (`§2.12`) are that guide's.

## 1. Essence

Adopt the Google Python Style Guide as akmon's code standard, and put each rule where it can be
enforced rather than where it is easiest to write down:

- a **principle that holds in any language** goes into the common guardrail;
- a **rule a program can check** goes into a rule catalog, checked by ruff on akmon and by
  akmon's own check on a consumer — and is never restated as prose, because a check beats prose;
- what is **specific to a language or to the environment the code runs in**, and no checker can
  see, goes into that language's or environment's **profile**.

A consumer gets the key rules by default and may switch any of them off or change its parameter
in `<AITNA_ROOT>/.akmon.toml`. Nothing shipped requires the consumer's linter, formatter or
package manager: ruff and uv are akmon's development dependencies only.

## 2. As-is

- [`_common.md`](../../guardrails/_common.md) holds the process floor (language, secrets,
  commits, analysis before mutation, delegation) and three code rules — reuse, API shape, don't
  duplicate what the code states. It has no design principles.
- `guardrails/python.md` (52 lines, removed by slice 1) names uv, ruff and pytest as the
  baseline toolchain and lists five generic code rules. It tells a consumer which tools to use,
  which is exactly what akmon must not do.
- [`profiles/`](../../profiles/) holds one domain profile, `quant`. "Language profile" is
  already a phrase in `ARCHETYPES.md` and `python.md`, but no file is one.
- akmon's own ruff selects `F E W I UP B`. On a consumer, nothing akmon ships checks code.

**Good:** small; no enforcement cost; nothing to configure. **Bad:** the code rules are prose
that loads into every session and is enforced by nothing; the Python guardrail prescribes tools
to consumers; akmon's own code is not held to the standard it ships.

## 3. The placement rule

Applied to each rule, in order:

1. **Can a program decide it from the source alone, with few false positives?** → **checked**:
   an entry in the catalog. Prose may name the rule's id; it does not restate the rule.
2. **Does it hold in any language?** → a **principle** in `_common.md` § Code design.
3. Otherwise → the **profile** of the language or environment it belongs to.

A rule may have both halves: the principle "failure is raised, never returned" is common prose;
its mechanical part, `no-bare-except`, is checked.

**Layout is the formatter's.** Line length, whitespace, blank lines, import order and one
statement per line (§3.1–3.6, §3.13, §3.14) are what a formatter owns. The catalog records them
so akmon's own ruff applies them, but akmon's consumer check never re-implements a formatter: a
consumer's layout belongs to whatever formatter it runs, and a second opinion on it would make
two owners of one fact.

## 4. Profiles — languages, environments, domains

| kind | attached | examples | reaches the agent as |
|---|---|---|---|
| **language** | automatically, by the language the project is written in | `python` | `@`-import (always on) |
| **environment** | automatically, by where some of the code runs — declared per path | `python-stdlib` (a bare interpreter, before any venv); `python-service` (an async server) when one is needed | `@`-import (always on) |
| **domain** | opt in, by need | `quant`, `crypto` | a link |

An environment profile layers on its language profile: prose for what the environment demands,
plus catalog rules switched on for the paths that run there — `python-stdlib`'s rule is
`stdlib-only`, which akmon's own `hooks/`, `bin/` and `common/` would carry. The guardrails
directory then means one thing: the floor that binds every project whatever its language.

**Layout after the change:**

```
guardrails/_common.md          the floor + a new § Code design (language-agnostic principles)
profiles/python.md             language profile — Python prose no checker sees
profiles/python.rules.toml     the Python rule catalog — the one owner of every checked rule
profiles/python-stdlib.md      environment profile — code that runs on a bare interpreter
profiles/quant.md              domain profile, unchanged
```

`guardrails/python.md` goes. **What that touches:** `bin/sync.py::imported_guardrails` and
package-mode materialization learn `profiles/` (an imported profile is materialized at
`<AITNA_ROOT>/.akmon/profiles/`, as a guardrail is); `common/materialization.py::stale_guardrails`
covers both directories; the `init` AGENTS.md block's example import line; `ARCHETYPES.md`'s map
("Language → profiles, automatic"); `MODEL.md` §5, `meta/CONCEPT.md` §5, `README.md`, the role
docs' "language guardrails" wording; `meta/tests/test_package_mode.py`'s fixtures.

**Migration.** A consumer that imports `guardrails/python.md` gets a plan error from `sync`
naming the replacement line (`@<AITNA_ROOT>/.akmon/profiles/python.md`); the edit is the
consumer's, one line, listed in the bump procedures (`BOOTSTRAP.md` §E, §F) and the changelog. One
consumer is attached today.

**Alternative A — keep `guardrails/python.md` as the language file**, and use `profiles/` for
environments and domains only. *Solves:* no consumer import changes. *Costs:* "guardrails"
keeps meaning two things (the universal floor and a language's rules), and an environment
profile then layers on a guardrail — two directories for one kind of thing.
**Alternative B — a one-release alias:** `sync` materializes the profile under the old name and
warns. *Solves:* a bump never stops on the import. *Costs:* two paths for one file, and a
removal to schedule. **Recommended: the move, with the plan error** — pre-1.0, one consumer,
and the error names the fix.

## 5. The rule catalog

`profiles/python.rules.toml` — data, one table per rule:

```toml
[rule.no-mutable-default]
source = "google:2.12"
text = "A default argument value is never a mutable object."
ruff = ["B006"]        # the codes akmon's own ruff must select for this rule
check = "ast"          # ast: akmon's check implements it · formatter: layout, the formatter owns it
                       # ruff: akmon-only, no consumer implementation
default = "error"      # the consumer's severity: error | warn | off
tests = "on"           # whether it applies to test modules by default
params = {}

[rule.function-length]
source = "google:3.18"
text = "A function longer than max_lines is reconsidered: split it or say why not."
ruff = []
check = "ast"
default = "warn"
tests = "off"
params = { max_lines = 40 }
```

**One owner, four readers.** The catalog is the only place a checked rule's text, codes,
default and parameters live. It is read by:

1. **akmon's consumer check** (§7), which implements every `check = "ast"` rule. A carrier fails
   when an `ast` rule has no implementation or an implementation has no catalog entry.
2. **akmon's own `pyproject.toml`** (§8). A carrier fails when a catalog code is not selected, or
   is ignored outside a declared per-file exception, or when a parameter differs without an
   override recorded in the catalog (akmon's line length, §8).
3. **The profile prose**, which cites rule ids. A carrier fails on an id the catalog lacks.
4. *Optional* — **a ruff fragment** printed from the catalog plus the project's `.akmon.toml`
   overrides (`akmon check --print-ruff`), for a consumer that runs ruff and wants both tools to
   agree. Printed, never written into the consumer's config.

## 6. Classification — every rule, its layer, its default

Layers: **C** common principle · **K** checked (catalog) · **P** profile prose · **F** formatter.
The two count columns are the [C89 baseline](../reviews/c89-python-rule-baseline-20260913.md):
the attached consumer (key rules), akmon (strict set). `–` = not measured; `†` = an upper-bound
heuristic.

| § | rule | layer | catalog id | ruff | consumer default | consumer | akmon |
|---|---|---|---|---|---|---|---|
| 2.1 | a suppression names its rule | K | `specific-suppression` | PGH003, PGH004 | error | 0 (PGH003) | 0 |
| 2.2 | import the module, not the symbol (`typing`, `collections.abc` exempt) | P + K | `import-modules` | — | **off** | 774† | 117† |
| 2.2 | no wildcard import | K | `no-wildcard-import` | F403 | error | 0 | 0 |
| 2.3 | absolute imports by full package path | K | `absolute-imports` | TID252 | error | 0 | 0 |
| 2.4 | failure is raised, never returned; catch only where you can act; keep the protected region small | C | — | — | — | – | – |
| 2.4 | no bare `except:` | K | `no-bare-except` | E722 | error | 0 | 0 |
| 2.4 | no `except Exception` that does not re-raise | K | `no-broad-except` | BLE001 | warn | 14 | – |
| 2.4 | no `except: pass` | K | `no-silent-except` | S110 | error | 0 | 0 |
| 2.4 | `assert` is not validation (outside tests) | K | `no-assert-validation` | S101 | error | 0 | 0 |
| 2.4 | re-raise with the cause (`raise … from`) | K | `raise-from` | B904 | warn | 0 | 0 |
| 3.16 | an exception's name ends in `Error` | K | `exception-suffix` | N818 | warn | 3 | 1 |
| 2.5 | no mutable global state | C + K | `no-global-statement` | PLW0603 | warn | 2 | 0 |
| 2.6 | nest a function only to close over locals; hide with `_`, not by nesting | P | — | — | — | – | – |
| 2.7 | a comprehension has one `for` and at most one `if` | K | `simple-comprehension` | — | warn | 1 | 12 |
| 2.8 | default iterators (`for k in d`, not `d.keys()`) | K | `default-iterator` | SIM118 | error | 0 | 0 |
| 2.9 | a generator documents `Yields:` | K | param of `docstrings` | — | warn | – | – |
| 2.10 | no lambda assignment; no `map`/`filter` with a lambda | K | `lambda-use` | E731, C417 | error | 0 | 0 |
| 2.11 | a conditional expression only when each part fits one line | P | — | — | — | – | – |
| 2.12 | no mutable default argument | K | `no-mutable-default` | B006 | error | 0 | 0 |
| 2.13, 3.15 | `@property` only for a cheap derived value; no trivial getter/setter | P | — | — | — | – | – |
| 2.14 | `is None`, never `== None`; no comparison to `True`/`False` | K | `none-and-bool-compare` | E711, E712 | error | 0 | 0 |
| 2.14 | implicit false: `if seq:`, not `if len(seq):` | K | `implicit-false` | PLC1802 | warn | – | – |
| 2.17 | no `@staticmethod` — a module function; `@classmethod` only as a named constructor | K + P | `no-staticmethod` | — | warn | 22 | 2 |
| 2.18 | concurrency at the edges; never rely on a built-in being atomic; hand data over through a queue | C + P | — | — | — | – | – |
| 2.19 | no power features: metaclass, `__del__`, 3-argument `type()`, `__import__`, `exec`/`eval`, dynamic `getattr` | C + K | `no-power-features` | S102, S307 (part) | warn | 7 | 0 |
| 2.20 | `from __future__ import annotations` for forward references | P | — | — | — | – | – |
| 2.21, 3.19.1 | the public API is annotated | K | `annotate-public` | ANN001, ANN201 | warn | 91 | 12 |
| 3.19 | signatures take abstract parametrized types; builtin generics | P | — | — | — | – | – |
| 3.19.5 | `X \| None` explicitly, never an implicit Optional | K | `explicit-optional` | RUF013 | error | 0 | 0 |
| 3.1–3.6, 3.13, 3.14 | layout: line length, whitespace, blank lines, import order, one statement per line | F | `layout` | E501, E70x, E401, I, W | formatter | 2 632 over 80 | 5 849 over 80 |
| 3.7 | a shebang only on an executable | P | — | — | — | – | – |
| 3.8 | public API documented; comments say why, not what | C + K | `docstrings` | D100–D107, D417, google convention | warn | 38 | 162 |
| 3.10 | no string accumulated with `+=` in a loop | K | `no-string-concat-loop` | — | warn | 1 | 0 |
| 3.10.1 | a logging call takes a pattern and arguments, never an f-string | K | `logging-format` | G001–G004 | error | 0 | 0 |
| 3.10.2 | an error message states the actual condition and names the value | C | — | — | — | – | – |
| 3.11 | a resource is released by a scope (`with`) | C + K | `open-with-context` | SIM115 | error | 0 | 0 |
| 3.12 | a TODO carries a link: `TODO: <link> - <text>` | C + K | `todo-format` | TD (part) | warn | 11 | 0 |
| 3.16 | names say what, without abbreviation or type | C | — | — | — | – | – |
| 3.16 | PEP 8 casing; no dashes in module names | K | `naming` | N801–N803, N806, N816, N999 | error | 0 | 1 |
| 3.16.1 | no single-character names beyond `i j k v e f _` | K | `short-names` | — | **off** | – | – |
| 3.17 | an executable keeps its logic in `main()` behind the `__main__` guard | P | — | — | — | – | – |
| 3.18 | small, focused functions (reconsider beyond ~40 lines) | C + K | `function-length` | — | warn | 23 | 63 |
| — | cyclomatic complexity ≤ 10 | K | `complexity` | C901 | **off** (akmon only) | – | 16 |
| — | blocking I/O inside `async` is offloaded | P + K | `no-blocking-in-async` | ASYNC | warn | 0† | 0 |
| — | code on a bare interpreter imports the standard library only | K (env) | `stdlib-only` | — | on for `python-stdlib` paths | – | – |
| 4 | be consistent with the surrounding code | C (exists) | — | — | — | – | – |

Four design principles have no Google number and go to **C**: data or behaviour, never half of
each; a contract carries a typed object, not a stringly map; return a value or mutate state, and
say which in the name; configuration is read at the entry point and passed down. Their Python
realization — a frozen `dataclass`, `NamedTuple` or `TypedDict` inside, validation models on the
boundaries — is **P**.

**What the defaults cost.** Measured with ruff's codes, every rule proposed as `error` is at zero
on the attached consumer; measured with `akmon check` itself, it has 5 `error` findings, all
`lambda-use` on `filter(lambda …)` — which §2.10 rules out and ruff's C417, covering `map` only,
does not check. The rest of the consumer's debt is in `warn` rules (189 findings): annotations,
docstrings, `@staticmethod` 22, function length 21, broad `except` 14, TODO format 11, dynamic
`getattr` 7 ([baseline, addendum](../reviews/c89-python-rule-baseline-20260913.md)). `import-modules` and `short-names` are `off`: the first would
flag several hundred imports for the least bug-preventing rule in the guide.

## 7. akmon's check for consumers

**Command.** `akmon check` (mounted mode: `python3 <AITNA_ROOT>/akmon/bin/check.py`). stdlib
only — `ast` for the code, `tokenize` for comments (TODO format, suppressions).

**Files.** Tracked `*.py` (`git ls-files`), minus `<AITNA_ROOT>/` and `[python].exclude`.
`--changed` checks the files changed against `HEAD` (the pre-commit use); `--all` the whole tree.

**Configuration** — `<AITNA_ROOT>/.akmon.toml`:

```toml
[python]
exclude = ["demo/**"]
environments = { stdlib = ["tools/bootstrap/**"] }

[python.rules]
no-staticmethod = "off"                                  # a severity alone
function-length = { severity = "warn", max_lines = 60 }  # or a severity and parameters
docstrings = { args = false }

[python.per-path]
"src/legacy/**" = { annotate-public = "off" }
```

- **Read through `common/record.py`**, the one reader (C83). The check needs a strict parse:
  a misspelled rule id that silently leaves a rule on — or off — is the failure this schema must
  make loud. `record.py` gains a strict entry point rather than the check growing a second
  reader; the floor is 3.11, so `tomllib` is always there.
- **Validated strictly:** an unknown rule id, an unknown parameter or a wrong type is an error
  finding naming the key.
- Test modules follow each rule's `tests` default; `per-path` overrides it.

**Suppressing one line.** `# akmon: ignore[rule-id] <reason>`. A `# noqa: <code>` naming a code
the rule maps to counts too, so a consumer that also runs ruff suppresses once. A bare `# noqa`
does not count, and a suppression that names no rule or gives no reason is itself a
`specific-suppression` finding.

**Output and exit.** One line per finding — `path:line:col rule-id severity message` — then a
summary. Exit 1 when an `error` finding exists (any finding under `--strict`), else 0.

**Syntax newer than the interpreter.** The check parses with the running interpreter's `ast`.
In package mode that is the consumer's own venv; in mounted mode `python3` may be older than the
project. A file that does not parse is a `parse-error` finding naming the interpreter version and
the fix — run the check under the project's interpreter — never a crash.

**Where it runs.** The pre-commit pipeline's lint step names `akmon check --changed`. `verify`
validates only the `[python]` table (unknown ids, malformed values) — integration health, not
code quality — so a bump never turns CI red on code the bump did not touch. A consumer that
wants a gate in CI adds `akmon check --all` itself.

## 8. akmon's own configuration

- **ruff, strict:** the groups measured in the [baseline](../reviews/c89-python-rule-baseline-20260913.md)
  plus `BLE`, `D` with `convention = "google"`, and every catalog code. `line-length` stays 120 —
  a recorded override of Google's 80 (5 849 of akmon's lines are over 80, 709 over 100).
- **akmon's own check on itself**, as a `self_ci` leg: the rules ruff has no code for —
  `simple-comprehension` (12), `no-staticmethod` (2), `function-length` (63), `todo-format`, and
  `stdlib-only` on `hooks/`, `bin/`, `common/`.
- **Rollout.** 361 findings under the strict set (199 + 162 docstrings). The size family —
  C901 16, PLR0912 8, PLR0913 6, PLR0911 4, PLR0915 4, and 63 functions over 40 lines — are
  refactors of load-bearing code (`sync`, `verify`), not lint fixes. Decided: everything else
  now; the size family is **C91**, with a per-file exception list that only shrinks.

## 9. Owner decisions

Decided by the owner (this session); recorded in
[ADR 0014](../decisions/0014-code-rules-catalog-and-language-profiles.md) and D2-48.

1. **Profiles layout** — language and environment rules move to `profiles/` (§4); `guardrails/`
   keeps the universal floor.
2. **The consumer check** — a separate `akmon check`, a severity per rule, the pre-commit step on
   changed files, `verify` validating the `[python]` table only (§7).
3. **akmon's rollout** — everything but the size family now; the size family is **C91**, a
   ratchet (§8).
4. **Line length** — akmon keeps 120; a consumer's layout is its formatter's.

Proposed defaults that stand unless the owner amends them:

5. **The key list** — the defaults in §6's table.
6. **Environments** — `python-stdlib` now; `python-service` when a service consumer exists.
7. **The ruff fragment** — printed on request (`akmon check --print-ruff`), never written.

Rejected with the decisions: keeping `guardrails/python.md` (alternative A) and the one-release
alias (alternative B); the check inside `verify --strict`, which turns the consumer's CI red on
its first bump, on findings in code the bump did not touch; an advisory-only check, under which
an `error` rule could never hold; the size family in the same change, which would put refactors
of load-bearing code inside a lint change; Google's 80 (5 849 lines) or 100 (709) for akmon.

## 10. Not carried

- uv, or any package manager, as a requirement on a consumer.
- A ruff baseline a consumer must `extend`: the rule set reaches a consumer through akmon's check
  and its `.akmon.toml`, never through its linter's configuration.
- A whole-tree lint sweep as a precondition of adopting the rules: `--changed` is the default
  on a consumer, and `--all` is its own decision.

## 11. Slices

1. **Placement.** `_common.md` § Code design; `profiles/python.md`, `profiles/python-stdlib.md`
   and the catalog; `guardrails/python.md` removed; `sync`, materialization, `verify`, `init` and
   the docs of §4 follow. Carriers: an imported profile is materialized and kept fresh; the old
   import is a plan error naming the fix; every rule id the prose cites exists.
2. **The check.** `bin/check.py` + `akmon check`, the rules of §6 with `check = "ast"`,
   `record.py`'s strict entry point, `verify` validating `[python]`, the pre-commit step.
   Carriers: each rule has a failing and a passing fixture; catalog ↔ implementation parity;
   config validation; both suppression forms; `parse-error`.
3. **akmon strict.** The ruff select, the fixes outside the size family, the
   `pyproject.toml` ↔ catalog carrier, the `self_ci` leg.
4. **The size ratchet** — **C91**.
