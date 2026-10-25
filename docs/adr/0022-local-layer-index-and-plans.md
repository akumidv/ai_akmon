# 0022 — The local layer, its index, and the plan

- **Status:** Accepted for **D01–D06**. The owner decided each choice in session: the local root,
  akmon's symmetric dev root, the raw-material home, the direction of references between local and
  project material, the nature and lifecycle of a plan, the split between a pipeline and two skills,
  the home of development skills, and that a project's dev root is resolved by code. The form of
  that code is not part of this record (**D06**, task **C157**). Implementation has not started.
- **Confirmed by the owner afterwards:** the three provisions the architect derived — the id
  exemption of local rows and the narrowing of 0002 (D03), a companion row carrying no copy of its
  project status (D03), and resume prompts naming paths from the project root only (D01); a token of
  its own, `handoff`, for work set aside in the local index (D03); and that the roadmap tool reads the
  project index plus the local index (D04).
- **Decided by the owner afterwards:** material under `<DEV>/local/` is grouped by purpose in three
  places, `handoff/`, `plans/` and `tasks/` (**D01**); a plan is one document and a handoff is a
  self-sufficient kit that holds the material a task or a plan needs beyond its own file (**D01**); a
  task whose description does not fit a paragraph is one file, `<DEV>/tasks/<id>-<name>.md` in the
  project and `<DEV>/local/tasks/<id>-<name>.md` locally (**D03**); and a local-only row's id is
  `_T<n>`, a prefix that marks it local and keeps its number apart from the project backlog's (**D03**).
- **Not part of this record:** where project documents live against the dev layer is
  [0023](0023-project-documents-layout.md).
- **Owner:** akuminov@gmail.com
- **Supersedes, in part:** [0021/D01](0021-athlos-deferred-work-packages-and-handoff.md#d01--the-work-package-and-when-it-is-written)
  for the path of the package record, and
  [0021/D02](0021-athlos-deferred-work-packages-and-handoff.md#d02--backlog-line-and-composed-resume-prompt)
  for the home of the `deferred` line. Their other content stands.
- **Amends:** [0002](0002-task-id-convention.md) in scope only — the typed id applies to the project
  backlog; a local-only index row takes `_T<n>` (**D03**).
- **References:** [pipelines/tasks.md](../../pipelines/tasks.md) (entry format, files and lifecycle) ·
  [pipelines/design-flow.md](../../pipelines/design-flow.md) § Plans ·
  [MODEL.md](../../MODEL.md) § Layer · [BOOTSTRAP.md](../../BOOTSTRAP.md) §D (ignore lines) ·
  [design: roadmap view](../design/roadmap-view.md) (the plan graph) ·
  live tasks [A39](../../meta/TASKS.md), [C150](../../meta/TASKS.md), [A58](../../meta/TASKS.md), [C152](../../meta/TASKS.md),
  [C154](../../meta/TASKS.md) and the tasks this record opens ([A60](../../meta/TASKS.md)–[C157](../../meta/TASKS.md)).

## Context

Local working material — a plan, the handoff to the next session, session state, a local backlog —
had no single home, and the repository carried four paths for it: `<AITNA_ROOT>/plan/` (a draft of the
bootstrap text and the `init` ignore line, never released), `<AITNA_ROOT>/local/plans/`
(A39), `<AITNA_ROOT>/local/packages/<task-id>/` (0021/D01) and `<AITNA_ROOT>/local/review/` (the
review-change design). Sessions filled the gap by improvisation: handoff folders and plans under
`.tmp/`, a plan folder under a nonexistent `_aitna/` in akmon, a root-level local backlog.

Three consequences. A resume prompt was observed carrying an absolute path of another machine. An
ignored folder does not follow a task into a git worktree (how git behaves, not measured here). And 0021/D01 itself records that no
`local/` ignore rule existed, so a package written under it surfaces as untracked noise.

Two further facts shaped the choice. The tracked rule said a plan is "never committed", which
conflicts with keeping local material and indexing it. And "plan" meant two things in the text: the
steps of one task (A39) and a trunk over backlog rows with a goal (the roadmap design).

## Decision

1. Everything a session resumes from lives under one ignored folder, `<DEV>/local/`, where `<DEV>`
   is `<AITNA_ROOT>` in a consumer and `meta/` in akmon. Raw material read once lives in `.tmp/` at
   the project root (**D01**).
2. A reference may point from local to project material and never the other way; a record that
   still holds a local reference is not promoted (**D02**).
3. Local work has an index in the project row format; a local-only row's id is `_T<n>`, and a task
   has no folder in the project tree, only a row and, when a paragraph is too small, one file. A
   deferral line goes to the local index (**D03**).
4. A plan is a working document for an architectural or product change that needs several tasks and
   states its target and S.M.A.R.T. criteria. It is not a queue and it is not kept in history;
   decisions found in it become ADR or design records that it links (**D04**).
5. The plan's definition and format are owned by pipelines; the agent-facing procedure is two
   skills, `plan` and `roadmap`; development skills live in `<DEV>/skills/` (**D05**).
6. A project's dev root is resolved by one code accessor; akmon's own repository resolves `meta/`
   by it (**D06**).

## Alternatives considered

- **`plan/` as the folder name.** Written in a draft and never released, so nothing migrates; but the
  name is narrower than the content now that "plan" is an entity.
- **A tracked per-task folder in the project tree as the promoted twin of local material.** Rejected by
  the owner: materials of a task are local by nature, and the task requirements already live in the
  row and its detail link. What the project keeps for a task is at most one description file, which
  is the task's statement and not its material (**D03**).
- **A folder per task or per plan for its material.** Replaced by the owner's rule: a plan is one
  document and a task is a row or one file; what either needs beyond that goes into the handoff kit,
  so there is one kind of folder, not three.
- **A slug or a bare letter as the local id.** A slug is the shape of a question or decision code
  and says nothing of a task's age; a letter collides with the type letters of 0002. `_T<n>` marks
  the row local and counts on its own.
- **One flat `local/<key>/` folder.** Rejected by the owner: folders of unclear purpose pile up; the
  the three places say what each is for.
- **A plan as a new kind of index.** A second notation and a second parser. The members of a plan
  stay rows of the existing indexes and the graph is read from their dependencies; the plan document
  itself is not an index. The roadmap tool reads both indexes (**D04**).
- **A plan kept in history as a design record.** Accumulates working text nobody needs; what the
  plan decides is recorded as a decision, and what it changes as the changes themselves.
- **A queue of unrelated tasks as a plan.** A plain sequence has no target, no optimization and no
  parallelism; it is a handoff, not a plan.
- **Pipeline only, or skill only, for the plan.** A document does not run the conversation; a rule
  kept in a skill depends on a switch a consumer controls. Layered, as `release` already is.

## Consequences

- **Carriers.** Owner documents (A60): `pipelines/tasks.md`, `pipelines/design-flow.md` § Plans,
  `MODEL.md` layer table, `BOOTSTRAP.md` §D, the review-change design and the 0021 supersession
  notes. Code: the ignore lines in `init` (C155), the guard in `verify` (C156), the resume helper
  of C150, the dev-root accessor (C157). Skills: `plan` (A61) and the home of development skills
  (A62). Python and JavaScript move together (ADR 0020).
- **Not machine-checked yet.** Until C156 lands, "local is ignored" and "no tracked link into
  local" are rules, not guards. A local slug named in tracked prose cannot be machine-checked at all
  and stays a rule (**D02**).
- **No legacy line.** The earlier `<AITNA_ROOT>/plan/` was never released, so `init` writes only the
  new lines. A consumer attached before C155 lacks them: once C156 lands its `verify` reports the
  missing ignore rule and names the fix.
- **A39 changes meaning.** "A plan for one task" is retired; the task keeps the local layer and its
  guard, and the plan notion is **D04**.
- **Untouched.** 0021/D03–D07, the athlos vocabulary, the work-package field set, the typed id
  scheme of the project backlog.

## Addressable accepted decision blocks

### D01 — The local layer and the raw-material home

`Decision-ID: ADR-0022/D01`

`<DEV>/local/` is the one home of material a session resumes from: the local index, handoff
records, resume prompts, briefs, evidence and probes. It is gitignored by one rule. `<DEV>` is
`<AITNA_ROOT>` (default `_aitna`) in a consumer and `meta/` in akmon, so akmon's local root is
`meta/local/` and the layouts are symmetric.

Material is grouped by purpose, so a folder's use is read from its place and not guessed from its
name:

| Place | Holds |
|---|---|
| `<DEV>/local/handoff/<id>-<name>/` | a self-sufficient kit for a task or a plan: `HANDOFF.md`, `RESUME.md`, prompts, and the evidence, probes, reports, briefs and review packs the task or plan needs beyond its own file |
| `<DEV>/local/plans/<id>-<name>.md` | a plan: one working document |
| `<DEV>/local/tasks/<id>-<name>.md` | a local task's description, when it does not fit a paragraph (**D03**) |

A plan and a task each stay one file. Material beyond that is not given a folder of its own: it goes
into the handoff kit of the task or plan, which carries no copy of a local row or of the plan unless
the owner says a transfer to another machine needs it. Delivery between machines is the owner's.

`<id>` is the id of the row that owns the file or folder: a project id when the row is the local
companion of one backlog task, `_T<n>` otherwise (**D03**), never a date. `<name>` is a short kebab name of what
the file or folder is about (`_T3-athlos-0021`), so a listing reads without opening the index; the
row's id stays `<id>` alone.

Raw material read once — another model's review, an export, a history-rewrite work area — lives in
`.tmp/` at the project root, gitignored, inside the project so an agent needs no permission outside
it. Nothing that a successor needs to resume from lives there, and no record defers to it.

The package record of [0021/D01](0021-athlos-deferred-work-packages-and-handoff.md) is
`<DEV>/local/handoff/<id>-<name>/HANDOFF.md`, not `local/packages/<task-id>/`. A resume prompt names paths
from the project root only.

Known limit: an ignored folder does not follow a task into a git worktree, so a session in a worktree
resumes from the main checkout's `local/`. Settling that is A39's open question, not a reason to
move local material into the tracked tree.

### D02 — Local and project material: the direction of references

`Decision-ID: ADR-0022/D02`

Four relations:

1. A local record may reference project material: a local plan or task names project ids.
2. A project record never references local material: no row, plan or detail link of a tracked file
   names a path under `local/`.
3. Promoting a local record to the project is refused while a local reference remains in it; the
   members are promoted first or dropped.
4. Once the `verify` check exists (C156) the relations are checked by path: a tracked file that links
   or names a path under `local/` is an error. Until then, and for a slug of local material written in
   tracked prose, which cannot be machine-checked at all, they are rules only.

The reason is portability: a tracked reference into local material is dead on every other machine.

### D03 — The local index and keys

`Decision-ID: ADR-0022/D03`

`<DEV>/local/TASKS.md` and `TASKS_ARCHIVE.md` use the project row format of
[pipelines/tasks.md](../../pipelines/tasks.md). A row's id is the project id when the row is the
local companion of a project task, otherwise `_T<n>`: `_T` marks the row local and `<n>` is a number
of the local index, counted over the index and its archive and never reused. A slug is not an id; it
names a question or a decision (`D-TOPIC`), which are short-lived, while a local task can outlive
many sessions and its number must not meet a project id. A companion row carries the status of the
local work only, never a copy of the project status. The local index has one status token more than
the project index, `handoff`: work set aside for another session, to be resumed from its package.
`deferred` keeps one meaning in both indexes, a deliberate not-now. Every `handoff/` folder,
`plans/` file and `tasks/` file has a row, written by whatever creates it — the C150
helper for a package, the `plan` skill for a plan, the author by hand otherwise; C156 warns on a file
or folder without one. `_T<n>` carries no role letter, so [0002](0002-task-id-convention.md), which types the project backlog's ids, is
narrowed in scope: it does not govern local rows and no role is derived from `_T`.

A task has no folder in the project tree. Its requirements are the row, a paragraph, and its detail
link; a description that does not fit a paragraph (how to reproduce, data, a longer statement) is one
file, `<DEV>/tasks/<id>-<name>.md` in the project (tracked) and `<DEV>/local/tasks/<id>-<name>.md`
for a local row, linked as the row's detail. That file is the task's own description, not a decision
or an open design question. Materials are local, in the handoff kit. A finished local task is kept, marked done in the local archive, and pruned at
the owner's discretion.

Deferring ([0021/D02](0021-athlos-deferred-work-packages-and-handoff.md#d02--backlog-line-and-composed-resume-prompt))
appends its line to the **local** index with the status `handoff`, because its link points into the
package. A project row is not changed by it: "set this batch aside for another session" is local
state, "a deliberate not-now" (`deferred`) is a project fact.

### D04 — The plan: nature and lifecycle

`Decision-ID: ADR-0022/D04`

A **plan** is the working document for the realization of an architectural or product change that
needs work across several tasks. It states the initial problem, the target state, the S.M.A.R.T.
criteria of that state, and the graph of its member tasks, so parallel work and priorities can be
read from it. Its members are rows of the project backlog or of the local index.

A plan is not a set of unrelated tasks run in order. A sequence has no target to optimize toward
and no parallelism; kept as a handoff, it is not a plan. A set of backlog tasks becomes a plan when
the owner names a main goal among them and the tasks are formed into a graph.

A work large enough to decompose is raised as a product (project) task: its row, and the decision
and design records it needs, are project material. The plan stays a working document: it is not
kept in project history, it is not promoted, and after the work lands the result is recorded as the
changes themselves (archived rows, decision or design records). A decision a plan contains is
written as an ADR block or design record first; the plan then links it and implementation goes on.
The plan may link project material (**D02**).

The roadmap tool reads the project index and the local index and draws the graph from the
dependencies of their rows. What it writes to a tracked file is drawn from the project index only,
so a tracked output never carries a local row (**D02**).

### D05 — Pipeline, two skills, development skills

`Decision-ID: ADR-0022/D05`

The plan is both a pipeline fact and a skill, layered as `release` is. **Pipelines own the facts:**
the layout and relations in `pipelines/tasks.md`, the content of a plan in `design-flow` § Plans.
**Skills own the procedure and link the facts.** There are two: `plan`, which forms a plan with the
owner, shipped to consumers in root `skills/` and selected per A55; and `roadmap` (C154), which
reads the plan graph and chooses the next step. Their triggers differ — forming happens once with
the owner, reading every session.

Development skills — those that serve how a project is developed — live in `<DEV>/skills/` (akmon:
`meta/skills/`), apart from the shipped root `skills/`. This fixes where a process skill lives
(the location half of A58's open request); how a harness discovers them is A62.

### D06 — The dev root is resolved by code

`Decision-ID: ADR-0022/D06`

A project's dev root is resolved by one code accessor that every tool and hook calls; it is not
restated by a prose sentence, a hand-set environment variable per tool or a literal in a hook. The
accessor resolves akmon's own repository to `meta/`. The form of the declaration — how the source
repository is recognized, how a relocated root is stated, how the fallback behaves when discovery
fails — is the work of C157 and is not decided here; it records its own decision block before code.
`AGENTS.md` states the fact for readers.
