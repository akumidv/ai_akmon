# 0028 — Park and resume: the kit, the dotted layer and the active kit

- **Status:** Accepted for **D01–D12**. The owner decided each choice in session and reviewed the
  [design](../design/park-and-resume.md) and its plan before implementation: the dotted local layer
  (**D01**); one folder per piece of work, named *ergon* (**D02**); the word *park*, the state `parked`
  and `PARK.md` as the result of a parking (**D03**); one string for the folder and the branch, in a
  namespace of the agent's own (**D04**); the plan inside its kit (**D05**); the session's active kit
  and the switch to another task (**D06**); scratch in three tiers, with the answers of other readers
  kept in the kit (**D07**). After a review of the design the owner decided four more: task, plan, job
  and step (**D08**, superseding the levels of D05); the holder lease and the state derived from it
  (**D09**, superseding the header `state` of D03); the active unit read from the file system — a
  job's worktree, or the pick (**D10**, superseding the first paragraph of D06 for a session in a
  worktree); worktrees for parallel jobs, where the agent works and commits on its own and a result
  is carried into the current branch only when the owner starts it (**D11**, amending D04); the local index retired, the kit being its own record (**D12**, superseding 0022/D03
  and the index clauses of D01 and D02).
- **Owner:** akuminov@gmail.com
- **Supersedes, in part:** [0022/D01](0022-local-layer-index-and-plans.md#d01--the-local-layer-and-the-raw-material-home)
  for the path of the local layer and for the three places under it (`handoff/`, `plans/`);
  [0022/D03](0022-local-layer-index-and-plans.md#d03--the-local-index-and-keys) for the path of the
  local index and for the status token `handoff`, and then, by **D12**, for the local index itself;
  [0022/D04](0022-local-layer-index-and-plans.md#d04--the-plan-nature-and-lifecycle) for where a plan
  lives and, by **D12**, for the roadmap reading the local index; [0021/D01](0021-athlos-deferred-work-packages-and-handoff.md#d01--the-work-package-and-when-it-is-written)
  for the name and path of the package record. Their other content stands.
- **Amends:** [0021/D03](0021-athlos-deferred-work-packages-and-handoff.md#d03--the-pressure-notice-names-the-package-before-compact)
  in the advice text only (*park the work → `/compact`*); [0008 §4](0008-mythological-naming-aitna-akmon-kyklopes.md)
  by an amendment that adds `ergon` to the reservoir; [0022/D08](0022-local-layer-index-and-plans.md#d08--the-id-a-material-carries-is-its-owner-id)
  in the place of the kit only — material still carries the id of the row it serves.
- **References:** [design: park and resume](../design/park-and-resume.md) · [0020](0020-node-consumers-js-implementation.md)
  (Python and JavaScript move together) · [0022/D02](0022-local-layer-index-and-plans.md#d02--local-and-project-material-the-direction-of-references)
  (a tracked file never names local material) · [MEASUREMENTS.md](../../meta/MEASUREMENTS.md) M2, M52,
  M53, M66, M88 · live tasks [A59](../../meta/TASKS.md) (this work), [C181](../../meta/TASKS.md)–[C186](../../meta/TASKS.md)
  (its trunk), [A77](../../meta/TASKS.md) (exchange between projects), [A78](../../meta/TASKS.md) (the job graph),
  [A79](../../meta/TASKS.md) (harness writes), [A50](../../meta/TASKS.md) (wider parallelization) and the
  tasks A59 closes: [A67](../../meta/TASKS.md), [A21](../../meta/TASKS.md), [A66](../../meta/TASKS.md),
  [C146](../../meta/TASKS.md), [C150](../../meta/TASKS.md).

## Context

A session's work died with its context. The record that would carry it (0021/D01, C150) was never
built, the pressure notice named a package nothing wrote, and the neighbouring tasks (A67 park before
the context runs out, A21 a fresh session for a new task, A66 one hand-over record, C146 context after
compaction) described one problem four ways. The local layer 0022 made for it left three places
(`handoff/`, `plans/`, `tasks/`), so one piece of work was split between a plan file and a package
folder, and its reviews and second opinions landed in a folder per harness. A similar project keeps
a checkpoint per task; akmon reimplements the idea on its own model and does not port it, and does
not use the word *checkpoint*, which the harness already uses for rewinding (M53).

## Decision

1. The local layer is `<DEV>/.local/` and the home of work is `<DEV>/.ergon/`, both dotted so a reader
   sees at once that neither reaches the repository (**D01**).
2. One folder, a **kit** `<DEV>/.ergon/<id>-<name>/`, holds a piece of work whole — live or parked —
   and a transfer is copying it (**D02**).
3. The act is *park*, the state is `parked`, the record is `PARK.md`, the result of a parking (**D03**).
4. The folder and the branch carry one string: `.ergon/<id>-<name>/` and `_aitna/<id>-<name>` (**D04**).
5. The plan is `PLAN.md` inside its kit; the levels are plan → task → step, and a step has no index
   row; the plan's status is read by code (**D05**).
6. A session has one active kit; a switch to another task is confirmed and moves the files with it
   (**D06**).
7. Scratch has three tiers and stays inside the project; the answers of other readers live in the kit,
   in rounds (**D07**).
8. A task is a backlog row outside any plan; a plan names its tasks and is made of jobs, each run in
   isolation by one holder toward its own result, through steps (**D08**).
9. A plan or a job has at most one holder, held by a lease file; its state is read from the lease and
   the park note, never typed (**D09**).
10. A session's active unit is read from the file system: the job of the worktree it runs in, or what
    it picked (**D10**).
11. A job run in parallel gets a local worktree on a local branch of its own; the agent works and
    commits there with no confirmation, and a finished result is carried into the current branch only
    when the owner starts it, by the agent or by commands the agent prints (**D11**).
12. The local index retires; a kit is its own record and `park list` is the index (**D12**).

## Alternatives considered

- **`.parked/` as the home** (the first proposal). The folder then holds live work under a state name
  and `PARK.md` has no meaning of its own; `ergon` names the work and leaves *park* to the act.
- **The plan apart, in `.plans/<id>-<name>.md`.** Plan and kit are then two things and a transfer takes
  both. Chosen against: the plan lives in the kit.
- **A per-task description file in the kit.** A task is a change carried by a plan whose items are
  steps; a step that needs a description gets one file (`steps/<n>-<name>.md`), so there is no
  second kind of file.
- **`checkpoint` as the word.** Taken by the harness for rewinding (M53); *park* has no collision in
  `skills/`, `agents/`, `hooks/`, `src/`, `common/`, `tools/` or `js/`.
- **The status `handoff` kept.** `parked` replaces it: the same meaning, the word the owner speaks.
  `deferred` stays distinct — a project fact, a deliberate not-now.
- **A branch namespace left to the agent.** One string for folder and branch lets either be found from
  the other with no table.
- **A silent switch on a changed subject.** A model's reading of a prompt is not a fact to act on
  alone; a switch is proposed and confirmed.
- **The harness's own resume, git-carried state, a tracker, a database or a freehand note** as the
  record (D08–D11 review). A harness resume is one harness and one machine; git-carried state (the kit
  on a branch, notes, a ref namespace) publishes what the layer keeps local; a tracker is the place of
  project tasks and of the exchange between projects, not of a session's working state; a database or
  a server adds a process to run for files that already serve; a freehand note drifts from its fields.
  The kit stays: local files, typed fields, a helper.
- **The plan's unit called a task, with a row of its own** (the first proposal of D08). Every parallel
  part would then be a backlog row, and the backlog would grow with working detail. Chosen against: a
  task stays the backlog's word, the plan's unit is a *job* and never leaves the plan.
- **The active kit kept only under the session marker** (D06 as first written). Two sessions in one
  checkout would then write one working tree under two kits. Chosen against: a parallel job takes a
  worktree, and the worktree names its job.
- **The active unit read from the git branch** (D10 as first written). It worked, but it made a git
  name the record of a local fact and tied an active kit to an agent branch. Chosen against: the file
  system already says it — the worktree's folder and the lease — and the branch is only what git needs
  to commit in a worktree.
- **The local index kept beside the kits** (D12). Its rows restated the kits' headers — title, plan,
  state — and it was the one file parallel sessions shared; a transfer had to carry an excerpt of it.
- **A lock tied to a process id, or no lock.** A process id means nothing on another machine and dies
  with a crash; no lock lets two holders write one kit. A lease file with its holder and last write,
  judged stale on read and taken over only on the owner's word, survives both.

## Consequences

- **Carriers.** Code: the dev-root accessor returns both folders (C182); the `tools/park/` helper
  writes and lists (C183); the lease, the jobs, the active unit from the file system, the kit as its own record and the worktree's way
  to the main checkout's kits (C186); SessionStart returns the digest of the active kit after a
  compaction (C184); the `park` skill and the notice (C185); Python and JavaScript move together
  (0020).
  Documents: `pipelines/tasks.md`, `pipelines/design-flow.md` § Plans, `MODEL.md`, `BOOTSTRAP.md` §D
  and the 0021 and 0022 supersession notes move with C182 and C185.
- **Migration.** The legacy `<DEV>/local/` is never moved silently: `verify` warns on it and names
  the move. The plan A71 moves into its kit in C182. No legacy line is written by `init`.
- **Measured before relied on.** Claude's SessionStart `source` values, whether `/park` is a reserved
  command, what each harness's prompt hook receives and which writes make each harness ask are
  `MEASUREMENTS.md` rows (C181); a claim of parity waits for its live probe and a regression test.
- **Not machine-checked yet.** That a tracked file names no path under `.local/` or `.ergon/` is
  C156's check on the new paths (branch B5); until then a rule.
- **Untouched.** 0021/D04–D07, the athlos vocabulary, the typed id scheme of the project backlog, the
  index format and D02 of 0022, and the rule that akmon transmits nothing between machines.

## Addressable accepted decision blocks

### D01 — The dotted local layer

`Decision-ID: ADR-0028/D01`

*Superseded in part by **D12**: `<DEV>/.local/` no longer holds a local index.*

The local layer of [0022/D01](0022-local-layer-index-and-plans.md#d01--the-local-layer-and-the-raw-material-home)
gains a leading dot: `<DEV>/.local/` (akmon: `meta/.local/`; consumer: `_aitna/.local/`). It holds
what only this machine needs — the local index `TASKS.md` and `TASKS_ARCHIVE.md` (0022/D03), machine
state and model overlays. It and `<DEV>/.ergon/` (**D02**) are gitignored by one rule each, written by
`init`, together with `.tmp/` at the project root. A single accessor returns both folders in Python
and JavaScript, so no tool, hook or document restates the literal. `local/handoff/` and `local/plans/`
retire; `local/tasks/` of 0022/D03 is left as it is.

### D02 — The kit: one folder per piece of work

`Decision-ID: ADR-0028/D02`

*Amended by **D08** (`jobs/<n>-<name>/` takes the place of `steps/<n>-<name>.md`) and **D09** (the
lease file `HOLDER`); superseded in part by **D12**: a kit has no row in a local index, and `verify`
warns on a kit with no `PLAN.md` header instead.*

A **kit** is the one folder of a piece of work, a plan or a task: `<DEV>/.ergon/<id>-<name>/`, where
`<id>` is the id of the row it serves (0022/D08) and `<name>` a short kebab name of its subject. It
holds, as it needs them: `PLAN.md`; `steps/<n>-<name>.md`; `PARK.md`; `RESUME.md`, the generated,
harness-neutral resume prompt written with `PARK.md`; `briefs/<purpose>/<n>/` (**D07**); `material/`,
raw material a successor needs. It holds facts and material, never a transcript, a log, a secret or a
customer payload. A kit has exactly one row in the local index; `verify` warns on a kit with none. The
folder's name says nothing of state; the listing does. A transfer is copying the folder or pointing at
it; a bundle file is a convenience of the helper, and akmon transmits nothing.

### D03 — Park: the word, the state and the note

`Decision-ID: ADR-0028/D03`

*Superseded in part by **D09**: the header field `state` is dropped, and the state is read from the
lease and the note; and by **D12**: the index status `parked` retires with the local index. The rest
stands.*

The act is **park**, its state **parked**, its index status `parked`, and `PARK.md` is the **result of a
parking** — a kit without it is work never parked. The header of the note is machine-readable and has
one source, the typed fields the helper takes: state (`parked` until the work is unparked, `resumed`
after), plan, row, branch, revisions, owned uncommitted paths, next action, sessions (references,
never requirements), peers and origin. Its body carries the fields of 0021/D01 and what that record
lacked: owner answers received, active agents and background processes, handoff readiness. The record
belongs to the work, not to the session that wrote it: it stands without the session, and resuming
never needs one. `parked` replaces `handoff` in the local index and means work set aside on the
owner's word; `deferred` keeps its meaning of a deliberate not-now.

### D04 — One string for the folder and the branch

`Decision-ID: ADR-0028/D04`

*Amended by **D11**: a job run in parallel has the branch `_aitna/<id>-<name>.<n>`.*

The agent's own git branches live in the namespace `_aitna/`, and the branch of a piece of work is
`_aitna/<id>-<name>` — the same string as its kit's folder name. The commit guard still passes any
non-default branch; the namespace is a convention that the guard's message and the note repeat.

### D05 — The plan inside its kit; plan, task, step

`Decision-ID: ADR-0028/D05`

*Superseded in part by **D08**: the levels plan → task → step are replaced by task, plan, job and
step. The place of the plan stands.*

A plan is `PLAN.md` in the kit of the work it carries; `<DEV>/local/plans/` retires (supersedes
0022/D04 for the place only; its definition, target, criteria and lifecycle stand). The levels are
**plan** (a goal with a graph of work, with an index row), **task** (a change to the project, with a
row) and **step** (a part of one task, an item of its `PLAN.md`, id `<task-id>.<n>`, **no row, no status
token, no owner id of its own**). A task is usually carried by one plan whose items are steps; a larger
piece of work is a plan whose items are tasks, each possibly with its own kit. A plan's status is
never typed into it: it is read by code from the member rows, the members' park notes, the open
review rounds and the done marks of the steps. The graph of steps of one task is the separate roadmap
task A78.

### D06 — The session's active kit and the switch of task

`Decision-ID: ADR-0028/D06`

*Superseded in part by **D10**: a session in a job's worktree is in that job, and the record under
the session marker serves a session in the main checkout. The switch and its recommendation stand.*

A session has one **active kit**, recorded under its hashed session marker; the session's notes,
briefs, answers, kept material and `PARK.md` are written to it, and SessionStart returns its capped
digest after a compaction. A session that has picked nothing writes to no kit; a task with no kit gets
one on its first write.

A switch to another piece of work is **confirmed, never silent**. An explicit word or `park pick <id>`
applies it and states it in one line; one noticed from a prompt that names another row id is
proposed and waits for a yes; a change of subject with no id is the agent's judgement and stays
advice. A confirmed switch does four things in order: it writes the leaving kit's note when the work is
unfinished and edits are newer than the note, state `parked`; it picks the target kit or creates it
with its row; it records the pick and returns the target's digest; it names the active kit to the
owner. It recommends — never applies — what to do with the work left, from facts: all steps done and
no uncommitted owned paths → close the row and archive the kit; open owner decisions or review rounds
→ park and name them; a member of a multi-task plan → name the plan's next member; uncommitted owned
paths → name them.

The switch isolates files, not the model's context; it therefore carries the fresh-session advice
whatever the fill (A21, axis 1). The trunk carries the explicit switch; the notice of a pick by id on
the prompt hook is a branch of the plan.

### D07 — Scratch in three tiers; the answers of other readers live in the kit

`Decision-ID: ADR-0028/D07`

Scratch stays inside the project, so no harness asks for a permission outside it. Throwaway raw
material read once lives in `<project>/.tmp/` (0022/D01); material a successor needs lives in
`<kit>/material/`; the answers of other readers — a review, an audit, a second opinion — live in
`<kit>/briefs/<purpose>/<n>/answers/`, in **rounds**: `BRIEF.md` by the producer, one answer file per
reader (one writer per file), and `DISPOSITION.md` by the producer, naming for each finding the
decision and the step or revision that fixed it. Round `n+1` cites the disposition of round `n` and
lists only what changed. A hand-over of work to another reader is preceded by a park of the work, so
the reader gets the brief and not the conversation. The folders per harness for second-opinion
reports retire. Which paths make each harness ask is measured, not assumed, and the rule stands until
a measurement says it is not enough.

### D08 — Task, plan, job and step

`Decision-ID: ADR-0028/D08`

Four words, one thing each:

- A **task** is a row of a backlog kept outside any plan: the project's `TASKS.md`, where a tracker
  issue is the row's provenance (`C2[#134]`), or the tracker itself. Work with no backlog task has a
  local id `_T<n>` on its kit (D12).
- A **plan** is `PLAN.md` in a kit (D05). It names the tasks it carries, one of them its **primary
  task**, whose id names the kit (`<id>-<name>`, D02). The link runs one way: the plan names its
  tasks, and a task row never names its plan or its kit (0022/D02). Whether a task is already carried
  by a plan is read by code from the kits on this machine; a pick of such a task asks the owner whether
  to take it into that kit or leave it there. A task carried by plans on two machines is a duplicate
  this decision does not resolve; a tracker with statuses does.
- A **job** is a unit of a plan, run in isolation by one holder (D09) toward a measurable result of its
  own. It serves one or more of the plan's tasks, and one task may be served by several jobs. Jobs may
  run in parallel; a job may wait on another job of the plan or on a task carried elsewhere, read from
  that task's status. A job never leaves its plan or its kit and has no row. Its id is `<kit-id>.<n>`;
  its folder `jobs/<n>-<name>/` is made when it is first held.
- A **step** is a part of one job, done in order by its holder, id `<kit-id>.<n>.<m>`, done or not. A
  holder's parallel fan-out of a step to subagents is a **zone** ([MODEL.md](../../MODEL.md)), recorded
  no further than its brief.

The criterion: what runs in parallel in sessions of its own is a job; what one holder does in order is
a step; what one holder fans out to subagents is a zone.

**What the work discovers.** A plan is refined while it is carried out, by details nobody knew when it
was drawn. What falls within the plan's target and its tasks stays in the plan: a finer or a new step
is added by the job's holder to its `JOB.md`; a new job, or a refinement branch beside the trunk, is
added by the plan's holder to `PLAN.md` — a job's holder that sees one proposes it in its own note. What
lies beyond the target and the plan's tasks becomes a task in the backlog on the owner's word. A change
of the target or the criteria is the owner's.

`PLAN.md` holds structure, never state: a header with the kit's id, name, title and tasks (primary
first); the target and the criteria; one line per job in the row style — id, label, the tasks it
serves, `after` (job or task ids), the paths it is expected to touch, a harness hint, and its result.
A job's progress — its steps with their done marks, and `done` once its result is met — is written by
its holder in `jobs/<n>-<name>/JOB.md`, one writer per file. The plan's status is read by code from the
jobs' files, leases and notes and from the rows of its tasks; a job with no folder has not started.

### D09 — The holder lease and the derived state

`Decision-ID: ADR-0028/D09`

A plan and each of its jobs have at most one **holder**, a session. The hold is a lease file `HOLDER`
in the unit's folder — the kit for the plan, `jobs/<n>-<name>/` for a job — created only when absent,
naming the holder (harness, session reference, machine label, worktree) and the time of its last
write, which every write of the helper renews. Unpark, a pick and the first write acquire it; park and
closing release it. A second session is refused with the holder named. A lease is judged stale when
read, from its last write; a stale lease is offered to the owner for takeover, never taken silently,
and the holder it replaces is kept in the note's sessions.

The state is derived, never typed: a held unit is **active**; a free one with `PARK.md` is **parked**;
a free one without it has **not started**; a job whose `JOB.md` says `done` is **done**. The header
field `state` of D03 is dropped. The helper reads the note's branch and revisions from git when it
writes, rather than taking them from the caller, and the note records when it was written. A holder
writes only inside its unit's folder, and only the plan's holder writes `PLAN.md`, so no file is
written by two sessions.

### D10 — The active unit is read from the file system

`Decision-ID: ADR-0028/D10`

Which unit a session is in is a local fact and is read from local files, never kept in git. A session
in a job's worktree is in that job: the worktree's folder, `<id>-<name>.<n>`, names it, and the job's
lease says whether this session may write it. A session in the main checkout has no active unit until
`park pick <id>`, recorded under its hashed session marker as D06 wrote. One worktree holds one job, so
two sessions never share a working tree. A pick of another kit from a job's worktree is proposed as
another worktree with a session of its own, never applied as a checkout over uncommitted paths.

### D11 — Worktrees for parallel jobs: free inside, carried on the owner's word

`Decision-ID: ADR-0028/D11`

A job run in parallel with others gets a local git worktree, which the agent may create, inside the
project under an ignored folder that `init` writes. Git needs a branch to commit on in a worktree; it is
`_aitna/<id>-<name>.<n>`, started from the project branch, local only: the agent never pushes it, it
carries code commits and no file of the kit, and it is deleted once its result is carried (git refuses
`_aitna/<id>-<name>/<n>` beside `_aitna/<id>-<name>`, hence the dot). Inside the worktree the agent
works on its own: it edits, runs the gates and commits on that branch with no confirmation asked; it
never pushes or tags. Carrying a finished result — a job, or a step worth carrying alone — into the
current branch is the owner's call: the agent says the result is ready and stops; the owner starts the
carry and picks the way — the agent carries it on that word, by a merge or a squash into one commit,
or prints the commands and the owner runs them. The agent never starts a carry. A worktree is removed on the owner's
word or after its result is carried, never while it has uncommitted paths (A63). Its sessions read and
write the kits of the main checkout: `.ergon/` is ignored and does not follow a worktree, so the
accessor resolves it through the repository's common directory. Nothing of a kit — plan, jobs, notes,
leases — is ever committed. Which writes into the main checkout make each harness ask is measured
(A79) before a parallel run relies on it. The shipped guardrail's § Commits & ownership and akmon's own
commit clause state the commit on a job branch and the carry on the owner's word; they otherwise
stand.

### D12 — The local index retires; a kit is its own record

`Decision-ID: ADR-0028/D12`

The local index of 0022/D03 — `<DEV>/.local/TASKS.md`, its archive, and `<DEV>/.local/tasks/` —
retires. A kit is the local record of a piece of work: its `PLAN.md` header carries id, name, title
and tasks; a parked hand-over is a kit with `PARK.md`; a local thing to do that outgrows a line is a
kit with only a target. `park list` is the local index, read from the kits, and the roadmap reads the
kits where 0022/D04 had it read local rows. Work with no backlog task takes a local id `_T<n>`, counted
over the kits, live and closed, and never reused. A closed kit moves to `<DEV>/.ergon/.closed/<id>-<name>/`
on the owner's word, through the archive tool, and the owner prunes it. The status `parked` retires
with the rows that carried it. `<DEV>/.local/` keeps what only this machine needs: learning state and
model overlays. The existing local rows move into their kits (B16); until then the old index is read
as legacy input and written by nothing.
