# C89 — the Python rule baseline measured on akmon and on the attached consumer (2026-09-13)

> **Question.** What would the proposed rules cost where they would apply: akmon's own tree
> under a strict ruff set with the Google docstring convention, and the one attached consumer
> under the key Google rules a consumer check would enforce by default?
>
> **Answer.** akmon: 361 findings under the strict set, of which 162 are docstring rules and 199
> everything else; 63 functions longer than 40 lines; 5 849 lines longer than 80. The consumer:
> 148 findings on the key rules that have a ruff code, every one of them in annotations (91),
> docstrings (38), broad `except` (14), exception names (3) or `global` (2) — **zero** on every
> rule the design proposes as an error. Of the rules ruff has no code for, the consumer's
> largest counts are symbol imports (774 by an upper-bound heuristic), function length (23) and
> `@staticmethod` (22).

## Corpus

- **akmon** — the working tree at `ca042e4` plus the uncommitted changes of this session: 65
  tracked `*.py` files (40 source, 25 test modules).
- **The attached consumer** (the alphavar pilot) — its tree at `d2932ce`, read only: 235
  tracked `*.py` files outside `_aitna/`, all parsed without a syntax error.
- ruff 0.15.21 from akmon's dev venv; Python 3.14 from the same venv for the `ast` pass.
  ruff ran with `--no-cache --no-fix` on an explicit file list from `git ls-files`, so nothing
  was written into either tree.

## Method

**Strict set on akmon.** `--config` with `line-length = 120`, `target-version = "py311"`, the
groups `F E W I UP B N ANN S ASYNC G LOG TID C4 FLY PERF SIM RET RSE PIE TRY DTZ PTH FBT ARG
ERA TD PGH A PL C90 RUF D`, ignoring `TRY003 ISC001 ANN401 TRY004 TRY301 S603 S607`,
`max-complexity = 10`, `[lint.pydocstyle] convention = "google"`; test modules and `conftest.py`
additionally ignore `S101 S105–S108 PLR2004 ANN ARG PLC0415 D`.

**Key rules on the consumer.** `--config` with `target-version = "py314"` and only the codes a
key rule maps to: `B006 B008 E722 BLE001 S110 B904 S101 E711 E712 SIM115 G001–G004 S102 S307
F403 TID252 PLW0603 RUF013 N801 N802 N803 N806 N816 N818 N999 ANN001 ANN201 D100–D103 D417
SIM118 E731 C417 PGH003 E701–E703 E401`, Google docstring convention; tests ignore `S101 ANN D`.

**Line length.** `ruff check --isolated --select E501 --line-length N` for N = 80 and 100.

**Rules without a ruff code** — an `ast` pass, heuristics stated so the numbers can be read:
function length is `end_lineno − lineno + 1` of the `def`, decorators excluded; a comprehension
is multi-clause when it has more than one `for` or a `for` with more than one `if`;
`@staticmethod` is the bare decorator name; a symbol import is `from x import Name` where
`Name` starts with a capital letter and `x` is not `typing`, `collections.abc`, `__future__`,
`typing_extensions`, `dataclasses`, `enum` or `abc` — an **upper bound** for "import the module,
not the symbol", since a capitalized module name would count too; a dynamic `getattr` is one
whose name argument is not a literal; a string accumulation is `+=` of a string literal or
f-string inside a `for`/`while`; a TODO is in Google format when it reads
`# TODO: <link> - <text>`.

## Results — akmon, strict set

361 findings: 199 outside the docstring group, 162 in it.

| group | findings |
|---|---|
| docstrings — undocumented public function / method / class / `__init__` / magic (D103, D102, D101, D107, D105) | 57 · 24 · 14 · 3 · 1 |
| docstrings — format (D205 blank line after summary, D209 closing quotes, D301) | 37 · 25 · 1 |
| import outside top level (PLC0415) | 24 |
| unused `noqa` (RUF100) | 21 |
| `subprocess.run` without `check` (PLW1510) · suppressible exception (SIM105) | 17 · 17 |
| complexity > 10 (C901) | 16 |
| manual list comprehension (PERF401) | 15 |
| missing argument annotation (ANN001) · private return annotation (ANN202) | 12 · 3 |
| magic value comparison (PLR2004) | 11 |
| too many branches / arguments / returns / statements (PLR0912, 0913, 0911, 0915) | 8 · 6 · 4 · 4 |
| ambiguous Unicode in string / comment / docstring (RUF001, 003, 002) | 8 · 4 · 1 |
| boolean positional parameter (FBT001, 002, 003) | 5 · 1 · 1 |
| everything else (21 codes, 1–3 each) | 27 |

Rules without a ruff code: 63 functions over 40 lines (4 in tests), 27 over 60; 12 multi-clause
comprehensions (9 in tests); 2 `@staticmethod`; 117 symbol imports by the upper-bound heuristic
(51 in tests); no TODO comment, no power feature, no string accumulation in a loop.

Line length: 5 849 lines over 80, 709 over 100, none over 120 (the configured limit).

## Results — the consumer, key rules

148 findings with a ruff code:

| rule | code | findings |
|---|---|---|
| annotate the public API | ANN001 · ANN201 | 66 · 25 |
| document the public API | D102 · D103 · D100 · D101 · D417 | 32 · 3 · 1 · 1 · 1 |
| no broad `except` | BLE001 | 14 |
| exception names end in `Error` | N818 | 3 |
| no `global` statement | PLW0603 | 2 |
| every other code listed in Method | — | 0 |

Rules without a ruff code: 774 symbol imports by the upper-bound heuristic (254 in tests); 23
functions over 40 lines (2 in tests), 6 over 60; 22 `@staticmethod`; 7 dynamic `getattr` (a
registry that dispatches by name); 11 TODO comments, none in Google format; 1 multi-clause
comprehension; 1 string accumulation in a loop; no metaclass, `__del__`, 3-argument `type()` or
`__import__`.

Line length: 2 632 lines over 80, 605 over 100. The consumer's own ruff config sets 120.

## Addendum — `akmon check` on the same trees

The check C89 ships (`bin/check.py`, catalog defaults, no `[python]` configuration), run on the
same two trees after its first two corrections — `no-silent-except` narrowed to a catch-all
handler, as ruff's S110 reads it, and `naming` no longer descending into a class body inside a
function or flagging a name declared `global`, both false positives this run surfaced on the
consumer's tests. Read only: the consumer's `git status` was the same 22 lines before and after.

| tree | files | `error` | `warn` |
|---|---|---|---|
| the consumer | 235 | 5 — `lambda-use` ×5 | 189 — `annotate-public` 69 (per function), `docstrings` 35, `no-staticmethod` 22, `function-length` 21, `no-broad-except` 14, `todo-format` 11, `no-power-features` 7, `implicit-false` 3, `exception-suffix` 3, `no-global-statement` 2, `simple-comprehension` 1, `no-string-concat-loop` 1 |
| akmon | 70 | 1 — `naming` (the same local name ruff's N806 reports) | 213 — `docstrings` 126, `function-length` 59, `simple-comprehension` 14, `no-broad-except` 6, `annotate-public` 5, `no-staticmethod` 2, `exception-suffix` 1 |

The consumer's five errors are `filter(lambda …)` calls: Google §2.10 rules out `map` and
`filter` over a lambda, while ruff's C417 covers `map` only — the one place the catalog's
Google rule is wider than the ruff code it maps to, and the reason the ruff-coded run above
counted zero errors. A third correction came from the same run: a module under a `_`-prefixed
path is private, as pydocstyle reads it, which took the consumer's `docstrings` count from 57 to
35 (the ruff run counted 38; ruff's `D` also counts a missing blank line or a `D417` the check's
presence rule does not) and akmon's from 127 to 126. The table is after all three.

## Limits

- One consumer. Its zero on the error-class rules says the defaults cost it nothing today; it
  says nothing about a consumer that has never run a linter.
- The consumer already runs ruff `F E W I UP B`, which is why the bug-class rules are at zero.
- The symbol-import count is an upper bound; the true count of "imports a symbol, not a module"
  needs the import resolved, which the design's check does and this pass does not.
