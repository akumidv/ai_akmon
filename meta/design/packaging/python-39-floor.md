# Design note: the declared Python 3.9 floor, and what makes it real

> **Deferred — backlog [C68](../../TASKS.md).** Provenance: C37 side finding, measured on this
> tree. This is independent of C37 and does not block its implementation or local git-pin
> adoption. It gates the separate V4 first-publish task unless the owner instead re-locks the
> declared floor to a version the shipped surface actually supports.
> Not a decision record: the floor itself is already locked by
> [ADR 0009 §1](../../decisions/0009-packaging-package-carrier-and-mount-modes.md). This note
> records *why the floor is currently a claim rather than a fact*, and the one open question
> the fix has to answer.

## The claim

`pyproject.toml` declares `requires-python >=3.9`, and CI runs a 3.9 matrix leg. The floor
exists because the hooks must run **venv-free** on whatever `python3` a consumer host has:
`hooks/` is stdlib-only by contract precisely so an old host is still governed.

## What is measured

`uv run --python 3.9 pytest meta/tests` is **24 failures on a clean tree**. The leg has been
red for as long as it has existed, and nothing reads it. Two independent causes:

1. **A shipped hook is dead on a 3.9 host.** `hooks/codex-hook.py` evaluates
   `Advisory = Callable[[str, str, str, Path], HookResult | None]` at **import** time, and
   PEP 604 in a runtime expression needs 3.10. `python3 <tree>/hooks/codex-hook.py
   session-start` exits 1 with `TypeError: unsupported operand type(s) for |` before any
   advisory runs — so **all four wired Codex entries** (`session-start`, `role-on-code`,
   `analysis-guard`, `d2-ledger-reminder`, i.e. every command `sync.py::_codex_hooks` writes)
   are silent no-ops on exactly the Python the standard promises to run on. 18 of the 24
   failures are this one line, through `meta/tests/test_adapters.py`.

   An import probe of every shipped `hooks/`, `bin/` and `tools/` module under 3.9 finds this
   file and **only** this file, so the code fix is one alias — `Optional[HookResult]`, the
   spelling the rest of the file already uses under `from __future__ import annotations`.

2. **Six `meta/tests/test_validate.py` cases assert 3.11+ behaviour without a version guard.**
   `meta/bin/validate.py` deliberately answers "its pyproject.toml cannot be read here
   (tomllib needs 3.11+)" below 3.11 (C62), and those tests expect the resolved runner
   unconditionally. A dev-side expectation bug, fixed with the same self-skip the
   tomllib-dependent d2 tests already carry.

## The known baseline (so a new failure is visible)

Re-measured on the current tree with the C37 work in place: **`617 passed, 24 failed, 7 skipped`**.
The 24 are exactly the two causes above — 18 in `meta/tests/test_adapters.py`, 6 in
`meta/tests/test_validate.py` — and the whole C37 surface (`test_init.py`, `test_cli.py`,
`test_sync.py`: 143 tests) passes under 3.9. That is what makes this note independent of C37
rather than a claim about it.

While this note is open the 3.9 leg cannot be green, so that triple is the fingerprint to compare
against: a 3.9 run that differs from it has a **new** failure, and "C37 is green" means the
current-interpreter legs *plus* this exact 3.9 shape. Re-measure the fingerprint whenever the test
count changes for other reasons; a stale baseline hides the thing it exists to reveal.

## The open question

Not *what to fix* — the code fix is two small edits — but **what makes the floor stay real**.
The tests did catch cause (1); the gap is that a red floor leg costs nobody anything today.
Whatever lands has to change that: a green 3.9 leg that gates, or an import probe of the
shipped surface that runs where it is read.

## Do not lose in the fix

- The floor is fixed by fixing the code, not by raising `requires-python`: the 3.9 leg exists
  because a consumer host may be old and the hooks must run there with no venv.
- Stdlib-only with zero runtime dependencies stays the contract (ADR 0009 §1).
- The two causes are independent. Fixing the noisy one (2) alone leaves a green CI over a
  dead hook.
