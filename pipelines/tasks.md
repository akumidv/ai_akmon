# Pipeline — task backlog convention

How every project (and keystone itself) keeps its backlog. The goal is a backlog any cold
agent can load cheaply and act on: **`TASKS.md` is an index, not a document.**

Why it matters: agents re-read the backlog at session start (code-flow step 1). A paragraph
per task costs ~150–300 tokens; a one-line entry costs ~20–30. The detail belongs in design
docs / ADRs / ledgers — link it, don't restate it.

## The entry format

One task = **one line**:

```
- <id> · <title> · <status> · <role> · <goal ≤12 words> · [detail](link)
```

- **id** — `T<n>`, stable, never reused.
- **status** — exactly one of `active | blocked | deferred | done`. `blocked` = waiting on an
  external dependency; `deferred` = a deliberate not-now (still a real intent, just parked).
- **role** — the keystone role that owns it (`architect` / `engineer` / …).
- **goal** — ≤12 words, the outcome. Not the plan.
- **detail link** — design doc, ADR, or ledger row. Required once detail exists; omit only for
  a one-line task that needs none.

A short multi-line note under an entry is allowed **only** for a genuine loose end that has no
other home yet — and that is a signal to write the design doc, not to grow the entry.

## Files & lifecycle

- **`TASKS.md`** — `active` + `blocked` + `deferred` only. Capped; see thresholds.
- **`TASKS_ARCHIVE.md`** — `done`, one terse line each. Move an entry here **in the same
  session it lands** — done work never accumulates in the live file.
- **Detail** — lives in `design/` docs, `decisions/` ADRs, or a verification ledger. `TASKS.md`
  links; it does not duplicate.
- An optional **Status** block at the top of `TASKS.md` is fine: ≤5 lines, current focus only.

## When to write

`TASKS.md` is the single destination for accepted work — **not** a license to write during an
analysis-only turn. Add or update task entries only after the owner agrees to record them. The
always-on rule and its trigger list live in [_common](../guardrails/_common.md) § Analysis
before mutation; this convention only says *where* accepted work lands.

## Where do implementation-born tasks go?

Tasks discovered **during coding** (a follow-up, a bug, a cleanup) usually have no design doc
and need none. They land in the **same `TASKS.md`**, `role: engineer`, status `active`/
`blocked` — origin (design vs process) does not change the destination, only whether a detail
link exists:

- small & self-contained → one line, **no link** (the goal is the whole spec);
- needs a sentence of context → the 1–3 line loose-end note (a hint to write an artifact if it
  grows);
- turns out to be a *decision*, not a fix → write an ADR / short design note now and link it —
  implementation may **originate** a design artifact, design need not precede code.

Reusable *knowledge* found mid-task goes to `_forge/memory/` via the learn loop, **not** here.

## Detail by reference (where things go)

| Kind of detail | Lives in | TASKS.md does |
| --- | --- | --- |
| What/why of a design | `design/` doc or ADR | link it |
| Math / DataFrame / verification | the project's D2-style ledger | link the row |
| Step-by-step plan | the design doc's touch-list | link it |
| Acceptance / done-criteria | the linked doc | one-line goal only |

## No dates

Do **not** write dates in `TASKS.md`, `TASKS_ARCHIVE.md`, design docs, or ADRs. The commit
history is the authoritative timeline — a date in the prose is redundant, goes stale, and burns
tokens. Need "when did X land"? `git log`. (This rule is keystone-wide, not task-only; design
docs and `decisions/` ADRs follow it too — order ADRs by their number, not a date.)

## Thresholds (enforced by `verify.py`)

- `TASKS.md` exists; `TASKS_ARCHIVE.md` exists once anything is done.
- Every `TASKS.md` entry carries a status token.
- **Warn** if `TASKS.md` exceeds ~200 lines, contains `done` entries (they belong in the
  archive), or contains dates (`YYYY-MM-DD`).

## Anti-patterns

- A task entry that restates a design already written elsewhere.
- `done` entries lingering in `TASKS.md`.
- Per-agent backlog files — keep one backlog, filter by the `role` field.
- Heavyweight schemas (weights, estimates, dependency graphs) — re-bloat by another name.
