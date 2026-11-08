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
  Work set aside on the owner's word is parked in its ergon; its state is read from the ergon, never
  a status.
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
- **A paragraph is the size criterion for a task** in `TASKS.md`. A task whose
  description does not fit one — how to reproduce it, data, a longer statement — is one file,
  `<DEV>/tasks/<id>-<name>.md`, linked as its detail. It holds the task's own description, not a
  decision (an ADR block) or an open design question (a design doc). Local work that outgrows a
  paragraph is an ergon (§ The local layer).

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
- **Detail** — lives in `docs/design/` docs, thematic `docs/adr/` ADR blocks, or task/evidence
  records. `TASKS.md` links; it does not duplicate.
- **`<DEV>/.local/`** — the ignored local layer: what only this machine needs (learning state,
  model overlays). Local work lives in ergons under `<DEV>/.ergon/`, owned by
  [The local layer](#the-local-layer) below. An ergon is input, not a record: what local work
  concludes still becomes a design doc, an ADR block or a `TASKS.md` row.
- An optional **Status** block at the top of `TASKS.md` is fine: ≤5 lines, current focus only.

## The local layer

`<DEV>` is the dev-layer root, `<dev root>` (default `_aitna`).
Everything a session resumes from lives under `<DEV>/.ergon/`, with `<DEV>/.local/` for machine
state; both are **gitignored**. Raw
material read once (another model's review, an export, a work area) lives in `.tmp/` at the
project root, also ignored and inside the project so no outside permission is needed; nothing a
task or a plan needs is kept there.

```
<DEV>/TASKS.md  TASKS_ARCHIVE.md        tracked project index
<DEV>/tasks/<id>-<name>.md              a project task's description, when it does not fit a paragraph
<DEV>/.local/                           machine state and overlays (learning state, model overlays)
<DEV>/.ergon/<id>-<name>/PLAN.md        a plan: one working document, inside its ergon, made of athlos
<DEV>/.ergon/<id>-<name>/               an ergon: one folder per piece of work, named for its primary
                                        task — PLAN, HOLDER, PARK, RESUME, and one folder per athlos
                                        named by its number alone, `<n>/ATHLOS.md`
<DEV>/.ergon/.closed/<id>-<name>/       a closed ergon, moved there on the owner's word
.worktrees/<id>-<name>.<n>/             at the project root: the worktree of a parallel athlos (ignored)
<DEV>/skills/                           development skills, apart from the shipped root `skills/`
```

- **Id.** There are no local rows. An ergon is named `<id>-<name>` for its plan's primary task; work
  with no backlog task takes `_T<n>`: `_T` marks it local, and `<n>` is counted over the ergons, live
  and closed, and never reused; `akmon tool park/park local-id` prints the next free one. A slug is
  not an id; `<name>` is a short kebab name of its subject.
  The ergon's `PLAN.md` header (id, name, title, tasks) is its local record, and `park list` is the
  local index. The plan names its tasks; a task row never names its plan. A transfer to another
  machine is an explicit export: a directory with the ergon's folder, the git bundles of its unpushed
  commits, a patch of its uncommitted changes and a manifest.
- **Direction.** A local record may reference project material. A tracked file never references a
  path under `.local/` or `.ergon/`: a tracked reference is dead on every other machine. Promoting a local record
  is refused while a local reference remains in it. Once `verify` carries the check, a tracked file that
  links or names a path under `.local/` or `.ergon/` is an error; a local slug written in prose cannot be
  checked and is a rule only.
- **No per-task folder in the project tree.** A task's requirements are its row, a paragraph, or
  one description file linked from the row; its working materials are local. A closed ergon moves to
  `<DEV>/.ergon/.closed/` on the owner's word and stays until the owner prunes it.
- **Parked.** Work set aside on the owner's word is parked in its ergon: its state is read from the
  ergon's lease and park note, never typed, and no row changes.
- **A task is not an athlos.** A task is what a backlog records; a plan names its tasks, and its own
  units — athlos, and the steps inside them — never become rows. What a plan's work discovers is
  refined in the plan when it falls within the plan's target and its tasks: a finer or new step goes
  into its athlos's `ATHLOS.md`, a new athlos or a refinement branch into `PLAN.md`. What lies beyond
  the target and the plan's tasks becomes a task here, on the owner's word.
- **Resume prompts** name a path from the project root when the file lies inside it, and by its
  absolute path when it lies outside it (an ergon in the main checkout, read from a linked worktree).
- **A plan** is a local working document, not a record: [design-flow § Plans](design-flow.md#plans).

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
| Open design question and alternatives | `docs/design/` doc or task detail | link it |
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
docs and `docs/adr/` ADRs follow it too — order ADRs by their number, not a date.)

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
