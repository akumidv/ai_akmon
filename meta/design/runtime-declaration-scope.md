# What the runtime declaration is a declaration *of*

**Status:** open fork — A20. Nothing here is decided.

C57 shipped `bin/runtime.py`: the binaries akmon requires, each with a population and a modality,
joined against what the tree actually invokes. The join is closed by construction and the real
tree passes it. This note records the question that closure does not answer.

## The gap

F16's two joins read exactly two sources: the command strings `sync` emits, and the
harness-command map. Everything akmon invokes outside those two sources is invisible to the
checker — correctly so, since a whole-source binary inventory would report dev tooling as a
consumer requirement. But the *declaration* inherits that scope, and a consumer reads the
declaration as the OS contract.

## What is actually true about each binary

The first draft of this note called the missing dependencies "hard-required", which is wrong in
four different ways. The uses do not share a modality, and that is the substance of the fork
rather than a detail of it:

| use | binary | what absence actually costs |
|---|---|---|
| generated Codex wiring — `$(git rev-parse --show-toplevel)` | `git` | the hook cannot resolve the root; declared today as `required-on:codex` |
| `akmon init --mode submodule` / `--mode subtree` | `git` | attach cannot proceed: `submodule add`, `ls-remote` reachability, tag discovery for the pin, checkout |
| `akmon init --mode vendored` / `--mode package` | `git` | **nothing** — neither mode touches a git command on the attach path |
| commit guard, branch lookup (`hook_core.current_git_branch`) | `git` | **nothing is weakened**: the call returns `""`, and an empty branch takes the same `ask` branch as `main`, so absence makes the guard *stricter*. It is also Claude-only wiring — `sync` does not emit the commit guard on the Codex route at all |
| `meta/bin/validate.py` | `pytest` | nothing for a consumer, and not a binary dependency for a contributor either: `_pytest_command` prefers an **importable** pytest and only reaches for `uv` when that fails |
| `meta/bin/validate.py` | `uv` | a *fallback* resolver, reached only when pytest is not importable; absent, the leg skips with a stated reason rather than failing |
| `meta/self_ci.py` | `uv` | **unconditional** — `uv build`, `uv venv` and `uv pip install` have no alternative path, so the wheel-smoke leg cannot run without it. The one contributor-side hard requirement, and it does not share a modality with the line above |

So `git` alone appears in four different modalities — and the contributor tools split too: `uv`
is a hard requirement for `self_ci` and a fallback for `validate`, while `pytest` is not a binary
dependency in either. The rows do not divide into "generated wiring" and "contributor tooling":
only the last three are contributor-only. Attach (`akmon init`) and the commit guard are both
**consumer-facing** and both invisible to the join, which is what makes the gap consequential —
if the missing uses were merely developer conveniences the declaration could keep its present
scope and say so in a sentence.

## The fork

**First:** how many populations does the declaration carry? Today there are two.

- **(a) keep two, scoped to generated wiring** — today's shape made explicit. The declaration
  stays fully derived from what `sync` emits and therefore self-checking. Attach-time
  requirements move to a statement `BOOTSTRAP.md` owns. Costs: a consumer reads two documents to
  learn what the host needs, and the more consequential requirement — attach — lives in the
  document with no checker behind it.
- **(b) four populations, each with its own modality vocabulary** — `generated-wiring`
  (unchanged), `attach-carrier` (per mount mode: `required-on:submodule`, `required-on:subtree`,
  absent for `vendored`/`package`), `optional-enhancement` (present-improves, absent-degrades-
  safely, which is what the branch lookup actually is), and `contributor-tooling` (never a
  consumer requirement, declared so it stops being invisible — and needing at least two
  modalities of its own, since `self_ci` cannot run without `uv` while `validate` merely prefers
  it). Costs: three of the four have no
  closed join behind them, so they are hand-maintained assertions — the exact thing F16 removed
  from the one population that *can* be derived. Each would need its own carrier or an explicit
  "unchecked by construction" marker, or the declaration becomes decoration again.
- **(c) two populations, but modality carries a condition** — keep `generated-wiring` and
  `akmon-own-tooling`, and let a modality say `required-on:mode=submodule` alongside
  `required-on:codex`. Cheaper than (b), but it puts mount modes and vendor routes in one
  vocabulary, and only one of the two is derivable.

**Then, and only then:** does `optional-enhancement` need a *fail-safe direction* field? The
branch lookup degrades toward stricter, and a reader cannot tell that from `optional` alone. A
declaration that cannot distinguish "absent means less safe" from "absent means more strict" is
not saying much about a runtime.

A checker change follows the decision; it is not the decision.

## Rejected pre-emptively

Widening C57's scan to a whole-source binary inventory. It would report `uv` and `pytest` as
consumer requirements they are not, and would replace a closed join with a heuristic.

## Provenance

Found while implementing C57's F16 join; the route-scoped `git` modality comes from the Codex
`base` command string in `bin/sync.py`. Filed as C71, refiled as **A20** — the work is a scope
decision, and the typed-id contract derives the architect role from the `A` letter
([pipelines/tasks.md](../../pipelines/tasks.md)). The dependency table above replaces the first
draft's claim that these uses were uniformly hard-required (N-review finding 7), and separates
`self_ci`'s unconditional `uv` from `validate`'s fallback use of it (N-review finding 6).
