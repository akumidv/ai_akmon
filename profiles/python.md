# Profile: Python (language)

The **language** profile for Python — attached automatically to any project written in Python,
and `@`-imported from `AGENTS.md` so it loads at session start. It layers on the
[common guardrails](../guardrails/_common.md): their § Code design states the principles for any
language; this file says how they read in Python, and only what no checker can see.

> **Checked rules are not repeated here.** Every Python rule a program can decide lives in
> [`python.rules.toml`](python.rules.toml) — its text, its Google Python Style Guide section,
> its default severity — and `akmon check` enforces it. A document names such a rule as
> `python:<id>`. A project switches a rule off or changes a parameter in
> `<AITNA_ROOT>/.akmon.toml` under `[python]`; it never edits the catalog.

## Toolchain — the project's own

- **One declared environment manager and one lockfile;** commands run through it, and no one
  activates a virtual environment by hand. Which manager is the project's choice — akmon
  requires none.
- **The project's linter and formatter own layout** — line length, whitespace, import order.
  akmon's checked rules do not depend on them; a project that runs ruff can print a matching
  configuration fragment with `akmon check --print-ruff`.
- **Tests:** the project's runner, pinned as `[test].runner` in `<AITNA_ROOT>/.akmon.toml`.
- **Types:** a type checker where the project adopts one. The public API is annotated either
  way (`python:annotate-public`).

## Design — the common principles, read in Python

- **Data or behaviour.** Data is a `@dataclass(frozen=True)`, a `NamedTuple` or a `TypedDict`;
  behaviour is a class with methods. A validation model (pydantic or equivalent) sits on the
  **boundaries** — parsed input, settings, responses — and the frozen types carry the data
  inside.
- **A contract carries a typed object**, not `dict[str, Any]`.
- **Signatures take abstract, parametrized types** — `Sequence[int]`, `Mapping[str, Path]`,
  `Iterable[T]` — and return concrete ones. Builtin generics (`list[int]`), `X | None` spelled
  out, and `from __future__ import annotations` for a forward reference (Google §2.20, §3.19).
- **A method that never touches `self` is a module function** (`python:no-staticmethod`).
  `@classmethod` only as a named constructor. No getter or setter that only reads or writes an
  attribute — make the attribute public; `@property` only for a cheap, unsurprising derived
  value (§2.13, §2.17, §3.15).
- **A nested function only to close over local values;** hide a helper with a leading `_`, not
  by nesting it (§2.6).
- **A conditional expression only when each part fits on one line** (§2.11).
- **Power features** (`python:no-power-features`) — what the standard library builds on them,
  `dataclasses`, `enum`, `abc`, is fine to use; writing a metaclass or a name-driven dispatch of
  your own is not.
- **Import the module, not the symbol,** so a call site names where a name comes from
  (`python:import-modules`, off by default). Symbols from `typing` and `collections.abc` are
  imported directly.
- **Concurrency.** Never rely on a built-in type being atomic; hand data between threads through
  `queue.Queue`; prefer `threading.Condition` to bare locks (§2.18). Blocking I/O inside `async`
  code is offloaded to a thread, never called on the event loop (`python:no-blocking-in-async`).
- **An executable** keeps its logic in `main()`, called behind `if __name__ == "__main__":`, and
  only an executed file carries a shebang (§3.7, §3.17).
- **Validate at the boundary** and keep internal code trusting the validated types.
- **Imports are real and current.** Verify a symbol exists before importing it — modules move in
  refactors ([_common.md](../guardrails/_common.md) § Verify against reality).
- **Reuse the project's abstractions** — provider patterns, the data dictionary, shared base
  classes: extend them, don't fork them.

## Tests

- **A behaviour change ships with a test.** Tests mirror the source layout.
- **Mark slow, networked and integration tests** so the default run stays fast and hermetic;
  gate them behind an explicit marker.
- **No real network or secrets in unit tests.** Use fixtures and fakes; an integration test that
  needs credentials reads them from `.env` and is opt-in.
- **Tests pass before a commit** (the [pre-commit](../pipelines/pre-commit.md) gate).

## Data / numerics

- Numerics-heavy code (DataFrames, arrays, pricing) also follows the [quant](quant.md) domain
  profile — opt it in when the project does numerics. Any change to data shape or math is
  **owner-verified** ([_common.md](../guardrails/_common.md)).

## Packaging

- The public API is explicit (`__all__` or a documented surface) for a `package`-type project.
- Optional or heavy dependencies are **extras**, not core dependencies; document when a test or a
  command needs an extra enabled.
