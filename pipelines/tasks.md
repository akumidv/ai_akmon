# Pipeline — task backlog convention

How every project (and akmon itself) keeps its backlog. The goal is a backlog any cold
agent can load cheaply and act on: **`TASKS.md` is an index, not a document.**

Why it matters: agents re-read the backlog at session start (code-flow step 1). A paragraph
per task costs ~150–300 tokens; a one-line entry costs ~20–30. The detail belongs in design
docs / accepted ADR blocks / task evidence — link it, don't restate it.

## The entry format

One task = **one line**:

```
- <id> · <title> · <status> · <goal ≤12 words> · [detail](link)
```

- **id** — a **typed** identifier: one uppercase type letter + a number, no separator (`A1`,
  `C2`, `L1`, `V3`). Stable, **never reused** (the counter runs per type). The type letter
  encodes the kind of work; the owning **role is derived** from it (table below), so the role is
  not a separate field.

  | Letter | Type | Role (derived) | Pipeline |
  |---|---|---|---|
  | **N** | aNalysis — review of state/quality/conformance; findings report | review | review-flow |
  | **A** | Architecture & design — contracts, requirements (R#), ADRs, design concepts | architect | design-flow |
  | **C** | Code — production code, tests, refactor, dev tooling | engineer | code-flow |
  | **L** | Learning — memory distill / promotion | learn | learning + memory-distill |
  | **V** | Release — version cut / changelog / pin bump | release | release |

  Letters deliberately avoid `D`/`R`/`O`/`T` — taken by `D#` (dev requirements), `R#`
  (architecture requirements), `O#` (roadmap gaps), and legacy `T#` tasks. Add a new type letter
  only when a genuinely new role/pipeline appears (then via an ADR), not per project — as `N`
  was added for the `review` role.
- **GitHub link (optional)** — when a task has a tracker issue, append it to the id in brackets:
  `C2[#134]` for an issue in **this** repo (GitHub autolinks `#134`), or `C2[owner/repo#134]`
  across repos (e.g. a project task referencing an akmon issue). The local id stays canonical;
  `[#…]` is provenance, not the id. Distinct from the trailing `[detail](link)`.
- **status** — exactly one of `active | blocked | deferred | done`. `blocked` = waiting on an
  external dependency; `deferred` = a deliberate not-now (still a real intent, just parked).
- **a status must be checkable.** "complete in the tree", "done locally" and their variants are not
  statuses: they describe an uncommitted working copy nobody else can verify, and they outlive the
  code they claim — a task can end up asserting finished work that no commit ever carried and whose
  subject has since been deleted. A task is either **landed**, meaning the carriers it names resolve
  in committed history; **conclusively superseded or withdrawn**, meaning no implementation remains
  intended and the archive says explicitly whether any carrier landed; or **open**, with the
  remaining work stated. A commit may be named as implementation evidence; the history is the
  timeline, but a hash is not a status. A `done` row prepared in the same change as its carriers is
  proposed closure until that change lands; it must not describe the uncommitted tree as historical
  fact.
- **goal** — ≤12 words, the outcome. Not the plan.
- **detail link** — design doc, accepted ADR block, or task/evidence record. Required once
  detail exists; omit only for a one-line task that needs none.

A short multi-line note under an entry is allowed **only** for a genuine loose end that has no
other home yet — and that is a signal to write the design doc, not to grow the entry.

Legacy `T<n>` ids already in `TASKS_ARCHIVE.md` are **grandfathered** (frozen as-is); the typed
scheme applies to the live backlog and every new task. Don't renumber history.

## Files & lifecycle

- **`TASKS.md`** — `active` + `blocked` + `deferred` only. Capped; see thresholds.
- **`TASKS_ARCHIVE.md`** — terminal `done` entries: landed work and explicitly superseded or
  withdrawn work, with the terminal reason stated. Move an entry here **in the same change as its
  carriers land** — done work never accumulates in the live file. The move is mechanized by
  `tools/tasks/archive.py` (`--tasks <path>`; `--done <id>…` closes named entries then sweeps,
  `--apply` to write) — it works on **any** `TASKS.md` in this format, akmon's or a consuming
  project's `_aitna/TASKS.md`.
- **Detail** — lives in `design/` docs, thematic `decisions/` ADR blocks, or task/evidence
  records. `TASKS.md` links; it does not duplicate.
- An optional **Status** block at the top of `TASKS.md` is fine: ≤5 lines, current focus only.

## When to write

`TASKS.md` is the single destination for accepted work — **not** a license to write during an
analysis-only turn. Add or update task entries only after the owner agrees to record them. The
always-on rule and its trigger list live in [_common](../guardrails/_common.md) § Analysis
before mutation; this convention only says *where* accepted work lands.

## Where do implementation-born tasks go?

Tasks discovered **during coding** (a follow-up, a bug, a cleanup) usually have no design doc
and need none. They land in the **same `TASKS.md`** as a **`C`** task (engineer, derived), status
`active`/`blocked` — origin (design vs process) does not change the destination, only whether a
detail link exists:

- small & self-contained → one line, **no link** (the goal is the whole spec);
- needs a sentence of context → the 1–3 line loose-end note (a hint to write an artifact if it
  grows);
- turns out to be a significant *decision*, not a fix → pause the affected implementation,
  frame it in design/task detail, obtain owner acceptance, then record the accepted ADR
  block and link it. Implementation may **discover** a design fork; it does not authorize
  coding an unaccepted choice first. Routine corrections need no new decision block.

Reusable *knowledge* found mid-task goes to `_aitna/memory/` via the learn loop, **not** here.

## Detail by reference (where things go)

| Kind of detail | Lives in | TASKS.md does |
| --- | --- | --- |
| Open design question and alternatives | `design/` doc or task detail | link it |
| Accepted architecture / math / data commitment and rationale | the owning thematic ADR block | link its stable ID/anchor |
| Implementation conformance / missing measurements / residuals | the implementing or investigating task's evidence | link the evidence and remaining work |
| Step-by-step plan | the design doc's touch-list | link it |
| Acceptance / done-criteria | the linked doc | one-line goal only |

Accepting a design does not complete its implementation task. Removing legacy approval
bookkeeping does not complete an outstanding measurement or review. Keep the actual
dependency and remaining work visible without a parallel decision-status ledger.

## No dates

Do **not** write dates in `TASKS.md`, `TASKS_ARCHIVE.md`, design docs, or ADRs. The commit
history is the authoritative timeline — a date in the prose is redundant, goes stale, and burns
tokens. Need "when did X land"? `git log`. (This rule is akmon-wide, not task-only; design
docs and `decisions/` ADRs follow it too — order ADRs by their number, not a date.)

## Thresholds (enforced by `verify.py`)

- `TASKS.md` exists; `TASKS_ARCHIVE.md` exists once anything is done.
- Every `TASKS.md` entry carries a status token.
- **Warn** if `TASKS.md` exceeds ~200 lines, contains `done` entries (they belong in the
  archive), or contains dates (`YYYY-MM-DD`).

## Anti-patterns

- A task entry that restates a design already written elsewhere.
- `done` entries lingering in `TASKS.md`.
- Per-agent backlog files — keep one backlog, filter by the type letter (role is derived).
- Heavyweight schemas (weights, estimates, dependency graphs) — re-bloat by another name.
