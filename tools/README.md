# `tools/` — keystone SHARED executable tools

Cross-project executable tools that ship *with* the standard (the SHARED dev layer, see
[README §6](../README.md)). A **skill calls a tool** ([README §7](../README.md)): the tool
is the executable; the skill is the know-how that drives it.

> **`tools/` vs `bin/`.** [`bin/`](../bin/) holds the stdlib **CLIs the contract depends on**
> and CI runs every push (`sync.py`, `verify.py`, `self_ci.py`). `tools/` holds executables a
> **role/skill drives on demand** — not CI gates. A release is owner-driven, so the release
> tool lives here, not in `bin/`, and is not wired into CI.

> **Propose / prepare, never execute (D5).** A keystone tool defaults to read-only and
> dry-run. It may print commands, validate state, or draft files; owner-owned landing actions
> (commit / tag / push / publish / pin-bump) are run by the owner.

## Tools

| Tool | Driven by | Does |
|---|---|---|
| [`release/release_check.py`](release/release_check.py) | the [`release`](../skills/release/SKILL.md) skill / role | `--state` (collect), `--check` (run the release suite, runner-resilient), `--plan vX.Y.Z` (owner-run command set). Never commits/tags/pushes. |

Run a tool with `python3 _forge/keystone/tools/<path>` (stdlib-only; no install step).
