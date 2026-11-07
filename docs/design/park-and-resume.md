# Park and resume — one plan for A59, A67, A21, A66, C150 and C146

Living design for [A59](../../meta/TASKS.md). It replaces the sessions-branch stub in
[roadmap-view](roadmap-view.md#sessions-a-third-branch) and carries the plan that closes the folded
tasks. What the owner stated or decided in session is recorded as such (§ Decisions); what is
proposed becomes a stable block in a thematic ADR only after the owner confirms the open codes
(§ Open).

## Problem

A session's work has to survive three things: the context running out (compaction, a fresh session),
a pause for an owner answer or a long wait, and a change of holder. Today akmon covers this with six
tasks that describe one mechanism from six sides:

| Task | Side of the one problem | What only it adds |
|---|---|---|
| A59 | the record and a code-made table of sessions | the table the owner reads |
| A67 | when to set work aside before context runs out | the trigger: pressure, or before a long wait |
| A21 | when a *new task* should start a fresh session | two axes: explicit task pick (reliable), passive change (advisory) |
| C150 | the helper that writes the record and the resume prompt | the field set (ADR 0021 D01), the `handoff` index line, D05 retirement text |
| C146 | what a compacted session gets back | language and role lines, fill-reading reset, session-id accessor |
| A66 | one hand-over record for resume, review, audit and second opinion | the purpose block of a record (§ Briefs) |

They fold into A59 and close with it. Nothing is lost: each side is a step or a branch below.

## Reference: what the similar project does (reimplemented, not ported)

The similar project already runs a version of this. Its facts, read from its working tree, are input
only; akmon builds its own.

- A gitignored per-task Markdown record with a fixed template (task, plan links, result and next
  action, owned uncommitted paths, checks, owner answers, active agents, handoff readiness, fresh
  session prompt). The agent writes it by instruction; hooks only read it.
- A SessionStart hook hands the goal, next action and owner answers back after a compaction.
- A Stop hook holds once at a pause when project edits are newer than the newest record.
- Every third compaction advises recording the state and opening a fresh session; a role switch
  offers a fresh session.
- Task close deletes the record. A local `_agent/<KEY>_<slug>` branch is where the agent commits.

What akmon does differently, on purpose:

1. **The record is written by a helper from typed fields**, not freehand. The agent supplies facts;
   code renders the template and the resume prompt, so they cannot drift.
2. **The stop hold compares against this task's own record**, not the newest record of any task
   (the similar project lets one task's record clear every other task's hold).
3. **One name for one thing.** The similar project calls both a file and a git branch "checkpoint";
   akmon names neither so, and `/checkpoint` is a Claude Code alias of `/rewind` (M53).
4. **One owner per fact.** The record links its index row and its plan and never copies status; the
   path of the layer comes from one accessor, not literals (ADR 0022 D02, D03, D06).
5. **Cleanup rides the existing archive path**, not a second deleter.
6. **One folder holds everything about a piece of work** — plan, steps, record, hand-over briefs and
   their answers, kept material — where the similar project scatters them across `sessions/`,
   `plans/` and `streams/`.

## Decisions

**Stated or decided by the owner** (to be recorded in the ADR that C181 writes):

- The local layer gains a leading dot: `<DEV>/.local/` (akmon: `meta/.local/`, consumer:
  `_aitna/.local/`), so a reader sees at once that it never goes to the repository.
- **D-PARK-HOME — decided: `<DEV>/.ergon/`** (akmon: `meta/.ergon/`, consumer: `_aitna/.ergon/`),
  dotted, the one home of every piece of work, live or parked. It takes the place of
  `local/handoff/` and of `local/plans/` (ADR 0022 D01, D04). *Ergon* (ἔργον) is the work and what
  it has made so far; it joins the naming reservoir of
  [ADR 0008 §4](../adr/0008-mythological-naming-aitna-akmon-kyklopes.md) by amendment.
- **D-PARK-WORD — decided: *park*.** The act is park, the state is parked, the index status is
  `parked`, and the record is the park note `PARK.md` — **the result of a parking**, not the name
  of a folder.
- **D-PARK-BRANCH — decided: yes.** The agent's own git branches live under the AITNA namespace.
- **D-PARK-KEYFORM — decided: one string for the folder and the branch:** `<id>-<name>`, so the
  work `A59-park-and-resume` has the folder `.ergon/A59-park-and-resume/` and the branch
  `_aitna/A59-park-and-resume`.
- **D-PARK-PLANHOME — decided:** the plan lives in its kit, as `PLAN.md`; `local/plans/` retires.
- **D-PARK-SCRATCH — decided:** the three tiers of § Scratch; the answers of other readers (a second
  opinion, an audit, a review) live **in the kit**, with the work, not in a temporary folder and not
  in a folder per harness.
- **D-PARK-A66 — decided: fold.** A66 is designed here (§ Briefs) and closes with A59.
- **D-STEP-WORD — decided: *step*,** and refined by D-A59-UNIT below.
- **D-A59-UNIT — decided: task, plan, job, step** (§ Tasks, plans, jobs and steps; ADR 0028 D08). A
  task is what a backlog records, outside any plan; a plan names its tasks, one of them primary; a job
  is a plan's unit run in isolation by one holder toward a result of its own, possibly in parallel
  with others, and never leaves the plan; a step is a part of a job done in order. What the work
  discovers within the plan's target and tasks refines the plan — new steps, new jobs, refinement
  branches; what lies beyond them becomes a task in the backlog (§ Tasks, plans, jobs and steps).
- **D-A59-TRANSFER-ID — answered:** the kit is named for its primary task; the plan names its tasks and
  no task names its plan. On one machine code reads which kit carries a task and asks the owner what to
  do; a task carried on two machines is the tracker's to resolve, not this design's (§ Portability).
- **D-A59-HOLDER — decided: a lease file `HOLDER`** per held unit (§ Holders, worktrees and the active
  kit; ADR 0028 D09).
- **D-A59-ACTIVE — decided, then revised: the active unit is read from the file system** — a session in
  a job's worktree is in that job, a session in the main checkout is in what it picked; nothing of it
  is kept in git (ADR 0028 D10). The first form read it from the branch name; the owner asked why a
  local fact should live in git, and it does not need to.
- **D-A59-STATE — decided: derived** from the lease and the note; the header `state` is dropped, and
  the status `parked` retires with the local index (ADR 0028 D09, D12).
- **D-A59-PLANFORMAT — decided: machine-readable job lines** — id, label, tasks, `after`, paths,
  harness hint, result — with the progress in each job's own file (ADR 0028 D08).
- **D-A59-WORKTREE — decided:** the agent creates local worktrees for parallel jobs and works and
  commits there on its own, never pushing; a finished result enters the current branch only when the
  owner starts the carry, done by the agent on that word or by commands the agent prints (ADR 0028
  D11).
- **D-A59-TRUNKRUN — decided:** the trunk is accepted on a real task run by two sessions on two
  harnesses; more platforms and the wider parallelization belong to A50, linked from here.
- **D-PARK-PEER — decided, then narrowed:** A77 is the exchange between projects and the project task
  queue, through a tracker — GitHub issues, or a project's `TASKS.md`, which is a tracker kept in the
  repository — and is outside this design; the coordination of sessions inside one
  project — the lease and the worktrees — is in the trunk (§ Peers).
- **B8 after A79 — decided:** the briefs branch starts once the research of harness writes has its
  matrix.
- **D-PARK-LOCALTASKS — answered, then refined by D-A59-UNIT:** a plan's work is jobs and steps, so
  there are **no per-task description files in a kit**; a job's description is its `JOB.md`.
- **D-A59-LOCALINDEX — decided: b, the local index retires;** a kit is its own record and `park list`
  is the index (§ The kit is its own record; ADR 0028 D12).
- **D-C186-PATH — answered: the design's path sentence carries the exception.** A path inside the
  project is named from the project root; a path outside it — a kit in the main checkout read from a
  linked worktree — is named by its absolute path (§ Portability). The files that already carried the
  exception keep it.
- **D-C186-DATES — confirmed: the corpus's lease fixtures keep their own days.** A stale lease and a
  fresh one are stamped with fixed days of their own, and under the corpus's normalization rule 5 a
  day that is not the run's own day is fixture data, compared literally, so both scenarios are stable
  on any run day. The convention and its stamps are owned by the corpus's fixture model
  ([the conformance README](../../meta/conformance/README.md)).
- The folded tasks close with A59; the plan carries the trunk and everything the similar project
  has.
- A parked task must move: to another session, **another harness** and **another machine**; it must
  stand without its session (a session reference is kept to gather material on the same machine;
  resuming never needs it). The parked tasks can be **listed**.
- A record is **linked to its plan**; a plan's status is read from the records and never typed into
  the plan.
- **Everything of a piece of work lives in one folder**, so a transfer is copying that folder or
  pointing at it. **Reviews come in rounds**, kept together with the fixes they led to (§ Briefs).
- **Scratch files stay inside the project**, so no harness asks for an extra permission (§ Scratch).
- A second roadmap strand follows: the graph of a plan's jobs (A78).
- **A switch to another piece of work inside one session is noticed and moves the work with it**
  (§ Switching work inside a session): the session's active kit changes, every file the session writes
  goes to the new kit, and the old one is parked or closed on a recommendation the owner confirms.
- The owner reviews the design and the plan **before** any implementation starts.

**Synonym triggers.** *Handoff* (the old word of this layer, and one a model already reads as "set this
work aside for another session") is a trigger of the `park` skill beside *park*: «запаркуй», «передай
дальше», "hand this off", "handoff" all start a parking. It is a trigger word only — the state, the
note and the folder keep the names *parked*, `PARK.md` and `.ergon` (C185 writes the skill's
`description` with these words).

The word *park* in speech: «запаркуй задачу» or "park this session" writes the note; «распаркуй
`<id>`» / "unpark `<id>`" hands back the prompt and the capped digest. `parked` stays distinct from
`deferred` — a project fact, a deliberate not-now — as `handoff` was
([ADR 0022 D03](../adr/0022-local-layer-index-and-plans.md#d03--the-local-index-and-keys)). The
terms `park`, `parked`, `unpark` and `.ergon` collide with nothing in `skills/`, `agents/`,
`hooks/`, `src/`, `common/`, `tools/` or `js/` (a `grep` for `ergon` must use `\.ergon\b`: the
substring sits in "ergonomics"). `/park` and `/unpark` are not commands of Claude Code 2.1.318 ([M206](../../meta/MEASUREMENTS.md)), so the skill's names are free there.

## The kit — one folder per piece of work

A **kit** is the one folder of a piece of work, a plan or a task: `<DEV>/.ergon/<id>-<name>/`.
`<id>` is the id of the row the kit serves (ADR 0022 D08) and `<name>` a short kebab name of its
subject; the git branch of the work is `_aitna/<id>-<name>`, the same string.

```
<DEV>/.local/                          # gitignored: what only this machine needs
  learning.json  model-*.json          #   machine state and overlays
<DEV>/.ergon/<id>-<name>/              # gitignored: ONE FOLDER per piece of work, named for its primary task
  PLAN.md        # the plan: header, target, criteria, one line per job — structure, never state
  HOLDER         # the lease of the plan's holder, while one holds it (§ Holders)
  PARK.md        # the plan holder's park note: typed header + the facts; exists after the first parking
  RESUME.md      # the generated, harness-neutral resume prompt; written with PARK.md
  jobs/<n>-<name>/                     # one folder per job, made when the job is first held
    JOB.md       #   the job's steps with their done marks, and `done` once its result is met
    HOLDER  PARK.md  RESUME.md         #   the job's own lease, note and prompt
    briefs/  material/                 #   the job's own hand-overs and material
  briefs/<purpose>/<n>/                # hand-over rounds of the plan to other readers (§ Briefs)
  material/      # raw material the work needs to be resumed; kept
<DEV>/.ergon/.closed/<id>-<name>/      # a closed kit, moved here on the owner's word; pruned by the owner
.worktrees/<id>-<name>.<n>/            # project root, gitignored: a parallel job's worktree (§ Holders)
.tmp/                                  # project root, gitignored: throwaway scratch (§ Scratch)
```

- **A kit is created when a piece of work outgrows a paragraph** — by the `plan` skill (A61), by the
  first park, or by the first brief. Each unit in it — the plan, each job — is written by its one
  holder (§ Holders); a job's holder writes only inside its job's folder.
- **`PARK.md` is the result of parking.** A unit without it was never parked. Its state is not written
  in it: held is active, free with a note is parked, free without one has not started (ADR 0028 D09).
  The next parking rewrites the note.
- **Transfer is one folder.** Copy the kit, or point at it. Another machine gets an export, a directory that carries the work too (§ Portability; [ADR 0029/D07](../adr/0029-ergon-athlos-step-one-method-of-work.md#d07--only-an-explicit-export-moves-an-ergon)).
- **A kit holds facts and material, never transcript, logs, secrets or customer payloads.** Tracked
  files never name a path under it (ADR 0022 D02).
- A kit is its own record: its `PLAN.md` header is what a local index row used to say; `verify` warns
  on a kit with no header (§ The kit is its own record).
- The folder's name says nothing of state: `ls` cannot tell live from parked work; `park list` does.
- The trunk's `steps/<n>-<name>.md` of the first layout retires: a step is a line of its job's
  `JOB.md`, and a job that needs a description has it there.

### Where the plan lives — the alternatives, and what was chosen

| | Plan lives in | One folder per work | Cost |
|---|---|---|---|
| A1 | `<DEV>/.plans/<id>-<name>.md` | no — plan and kit are two things, a transfer takes both | the plan exists before any park, ADR 0022 D04 unchanged; but a piece of work is split |
| A2 | `<DEV>/.parked/<id>-<name>/PLAN.md` | yes | the folder holds live work under a state name |
| **A3 — chosen** | `<DEV>/.ergon/<id>-<name>/PLAN.md` | **yes** | the folder is named for the work, `PARK.md` is only the parking's result; `ls` shows no state; the roadmap scans kits; the existing plan A71 moves in (one migration step); `.local/plans/` retires |

## Tasks, plans, jobs and steps

**Four words, one thing each** (decided, ADR 0028 D08). The model is the one of a CI workflow — a
workflow of jobs, each job a sequence of steps — with the backlog's task kept outside it:

| Word | What it is | Row | Who writes it | Id | Where it lives |
|---|---|---|---|---|---|
| **task** | a change the backlog records, outside any plan | yes: the project's `TASKS.md` (a tracker issue as provenance) or the tracker | the owner's agreement | `C184`, `C2[#134]` | `TASKS.md`, the tracker |
| **plan** | a target over one or more tasks, one of them primary | its primary task's row, or none for local work (`_T<n>` on the kit); it names its other tasks | the plan's holder | the primary task's id | `PLAN.md` of the kit |
| **job** | a unit run in isolation by one holder toward a measurable result | **no** | its holder | `<kit-id>.<n>` (`A59.6`) | a line of `PLAN.md`; `jobs/<n>-<name>/` once held |
| **step** | a part of one job, done in order by its holder | **no** | its holder | `<kit-id>.<n>.<m>` (`A59.6.2`) | a line of the job's `JOB.md` |

- **The criterion.** What runs in parallel in sessions of its own is a job; what one holder does in
  order is a step; what one holder fans out to subagents inside a step is a **zone**
  ([MODEL.md](../../MODEL.md)), short-lived and recorded no further than its brief. The id says the
  level: a row id is a task, one dotted number a job, two a step.
- **A job is not a task.** It serves one or more of the plan's tasks, and a task may be served by
  several jobs; jobs and tasks are not one to one. A job may run beside others, wait on another job
  (`after A59.4`) or wait on a task carried in another plan (`after C152`), read from that task's
  status; a job that serves one task whose row is closed reads as done, which is how the jobs carried
  before this format existed are read. A job never leaves its plan and kit, so the backlog does not
  grow with working detail.
- **What the work discovers.** A plan is refined while it is carried out, by details nobody knew when
  it was drawn. What falls within the plan's target and its tasks stays in the plan: a finer or a new
  step goes into the job's `JOB.md` by its holder; a new job, or a refinement branch beside the trunk,
  goes into `PLAN.md` by the plan's holder — a job's holder that sees one proposes it in its own note,
  so `PLAN.md` keeps one writer. What lies beyond the target and the plan's tasks — a bug elsewhere, a
  follow-up for another area — becomes a task in the backlog on the owner's word. A change of the
  target or the criteria is the owner's.
- **The link runs one way.** The plan names its tasks; a task row never names its plan or its kit
  (ADR 0022 D02 already forbids a tracked file to name a path under `.ergon/`). `park list --task <id>`
  reads which kits on this machine carry a task, and a pick of a task that another kit carries asks
  the owner: take it into that kit, or leave it there.
- **Speech.** The owner may say *job* or «наряд»/«работа»; the files keep `job`. *Step* is «шаг».

### The format of `PLAN.md`

`PLAN.md` holds structure and never state. A header the helper reads, the target and criteria in
prose, and one line per job in the row style of [tasks](../../pipelines/tasks.md):

```
---
id: A59
name: park-and-resume
title: park and resume
tasks: A59, C181, C182, C183, C184, C185, C186
---
## Jobs

- A59.5 · holder lease, jobs, worktrees, the kit as its own record · tasks C186 · after A59.4 · paths common/project_root.*, tools/park/, js/tools/park/ · harness any · result: a second session on a held job is refused with the holder named
- A59.6 · return after compaction · tasks C184 · after A59.5 · paths hooks/ · harness claude, codex · result: after /compact the digest of the active unit is returned
```

- The **fields** after the label are `tasks`, `after`, `paths`, `harness` and `result`, in that order,
  each optional but `tasks` and `result`. `after` names job ids of the plan or task ids; `paths` names
  the paths the job is expected to touch, as globs; `harness` is a hint, not a constraint.
- **Progress lives with the job.** The job's holder writes `jobs/<n>-<name>/JOB.md`: a line per step
  with its done mark, and `done` once the result is met. One writer per file, so parallel holders
  never write one file; the plan's holder edits `PLAN.md` only to change the structure.
- **Status is read by code.** A plan's state is joined from its jobs (folder, lease, note, `JOB.md`),
  the rows of its tasks and the open review rounds: `park list --plan <id>` prints it in the trunk,
  and the roadmap tool joins it with the backlog (B12, [A50](../../meta/TASKS.md), C152).
- **Two jobs that may run at once and share a path** are named by the helper when it reads the plan:
  `paths` is a forecast, so the warning is advice, and the owned uncommitted paths of each note are
  the fact (the destructive-operation rule of [A63](../../meta/TASKS.md) applies between them).
- **The graph of a plan's jobs** is drawn from `after` by the separate roadmap task A78. The field is
  decided here for plans; D-EDGE-FIELD in [roadmap-view](roadmap-view.md) stays the question of edges
  between backlog rows.

The labels P0–P4, P2b and B1–B17 below are this design's working labels; in the kit's `PLAN.md` they
are jobs `A59.<n>`.

## The athlos and the job — one rung, two sides

ADR 0021 (the *athlos*) and ADR 0028 (the *job*) describe the same rung of the same ladder from two
sides. This section states that rung and the rules that follow from the union; the word that names
it, and what a rename would cost, are the owner's decision and live in
[the merge record](ergon-athlos-merge.md).

**The overlap.** An athlos is "the bounded labour of an approved plan, keyed by (task id, zone)",
carried by a session, executed by `k_*` delegates, outliving both (ADR 0021 D04). A job is "a unit
of a plan, run in isolation by one holder toward a measurable result of its own", with its own
lease, its own folder and its own worktree when it runs beside another (ADR 0028 D08–D11). Both
are: one bounded piece of an approved plan's work, with an acceptance condition of its own, held by
one session, done by delegates.

**What differs is the carrier and the key, not the thing.** The athlos was defined before the
ergon's machinery existed; its record was a work package (ADR 0021 D01) — a kit with a `HANDOFF.md`
note, which the legacy-kit branch gives a `PARK.md` header. The kit is that carrier, built: the
lease that names the holder, the note that carries the facts, the folder that travels, the worktree
that isolates a parallel run. The keys differ as well: the athlos is named by the pair (task id,
zone), the job by its id `<kit-id>.<n>` and the tasks it serves. A union keeps both — the id as the
unit's place in the plan, the pair as its content ([the merge record](ergon-athlos-merge.md) §6.3).

**The ladder, one owner per rung.**

| Rung | Word | Owner | What it is | Its carrier |
|---|---|---|---|---|
| a unit of a plan's work | **athlos** ([ADR 0029/D02](../adr/0029-ergon-athlos-step-one-method-of-work.md#d02--the-words-ergon-athlos-no-kit-no-job-no-argos)) | the merge of ADR 0021 D04 and ADR 0028 D08 | a bounded unit with an acceptance condition of its own, serving one or more tasks, run in isolation by one holder, placed by its id and named by its (task, zone) | the kit: folder, lease, note, worktree |
| a part of a unit, done in order | **step** | ADR 0028 D08 | one part of a unit, done in order by its holder | the unit's own file |
| a frame of a fan-out | **zone** | ADR 0021 D04, ADR 0028 D08 | where the work lands; the delegation ledger's label | the ledger and the coverage map |
| the doer | **Kyklops** (`k_*`) | ADR 0008 | the delegate that does part of a zone | the session's tool call |

**The rules that follow.**

- **One unit, one acceptance condition.** The condition is the unit's own, not the plan's; the plan
  is met when its units are met.
- **A unit runs in parallel in two ways.** Inside one unit, the zones of its steps run at once in one
  session (ADR 0021 D06). Beside other work, a unit that must be isolated, paused, resumed or
  carried to another machine is leased, gets its own folder and its own worktree — that is what makes
  it possible. *This is the merge's payoff: the athlos's clauses (its own acceptance condition, the
  zone where its work lands) and the ergon's machinery (lease, note, worktree) end up on one rung.*
- **The zone is one mechanism, not two.** Both records use the same frame word: the zone is where
  the work lands, recorded as the delegation ledger's label and read by the coverage map. Its
  spelling is a data format, not a word to be swept (ADR 0021 D04, "Why the frame word stays").
- **The merge is decided.** [ADR 0029](../adr/0029-ergon-athlos-step-one-method-of-work.md) accepts it and names what it amends; ADR 0021 D04–D07 and ADR 0028 D01–D12 otherwise stand as written ([the merge record](ergon-athlos-merge.md) keeps the options).

**The alternatives.** The shapes this section weighs — one word for the merged unit, and what each of them costs — live in [the merge record](ergon-athlos-merge.md); [ADR 0029](../adr/0029-ergon-athlos-step-one-method-of-work.md) owns the decision, and this section owns the model.

## The park note — fields

ADR 0021 D01's fixed fields, plus what the similar project's template carries that akmon lacked:
goal and acceptance (at the coarsest scale that is already an acceptance, per A52); approved scope
and open questions; branch, revisions and **owned uncommitted paths**; checks run and their outcome;
what remains unverified; **owner answers received**; **active agents and background processes**; next
action; **handoff readiness**; the resume prompt; and the links that make the record portable and
connected: **plan** (its id), **job** (when the note is a job's), **row** (its primary task's row, when it has one),
**sessions** (optional references: harness, session id, machine label, transcript hint) and
**origin** (where and by which harness it was written). A reader that still has to open the old
conversation to find the next action falsifies the field set (D01's reconsider clause).

`PARK.md` is plain Markdown with a small machine-readable header (ids, links, branch, revisions, next
action, the time it was written) and a free body for the facts. The header has one source — the typed
fields the helper takes, and what the helper reads itself — so no parallel declaration drifts from it.

**Revised by the review** (ADR 0028 D09; carried by P2b): the header has **no `state`** — it is read
from the lease and the note; **branch and revisions are read from git** by the helper when it writes,
never passed by the caller, so they cannot be wrong at the moment of writing; the note records **when
it was written**, which the digest compares with the last edit (§ The return after compaction); and
**`peers` is dropped** with the narrowing of A77 (§ Peers).

## Portability and detachment

The record belongs to the **work**, not to the session that wrote it.

- **Any holder.** `RESUME.md` is harness-neutral: it names a path from the project root when the
  file lies inside it, and by its absolute path when it lies outside it (a kit in the main
  checkout, read from a linked worktree), together with the commands to run, never a slash
  command of one harness. A harness adapter adds only the re-injection (Claude and Codex
  SessionStart; for a harness with no hook, the owner pastes the prompt). The adapters are
  branches; the record is the same for all.
- **Sessions are references, never requirements.** `sessions` lists where the work was done. On the
  same machine a resumer may open the old transcript to gather material; elsewhere the field is
  only provenance.
- **Another machine.** `park export <id> --out <dir>` writes a directory: the ergon's folder without leases and scratch, a git bundle of each athlos's commits that no remote has, a patch of its uncommitted changes, and a manifest the import checks ([ADR 0029/D07](../adr/0029-ergon-athlos-step-one-method-of-work.md#d07--only-an-explicit-export-moves-an-ergon)); the owner moves it — ADR 0022 D01 keeps delivery between machines with the owner, and akmon transmits nothing. `park import <dir>` places the ergon under `.ergon/`; until C191 lands, `park export` still writes one bundle file of the kit, leases left out. with no local index there is no row to carry. The note states, from `git`, whether its branch and revisions are reachable from a remote; if
  not, the readiness line says the owner must push — akmon never pushes.
- **The kit's id on another machine** (D-A59-TRANSFER-ID). A kit is named for its primary task. A
  project task's id is the same everywhere, so the kit, its jobs and their branches keep their names.
  A kit whose primary is a local `_T<n>` may meet a different `_T<n>` on the other machine: the import
  refuses the clash and asks the owner for the id to take (`park import --as <id>-<name>`), and the
  old one is kept as `origin`. That a task is carried by plans on two machines at once is a duplicate
  the tracker resolves with its statuses; this design does not.
- **The list.** `park list` prints each kit and, under it, each job: id, title, state (not started,
  active with its holder, parked, done), next action, open owner decisions (the `D-…` codes), open
  review rounds, branch, harness and age; filters by plan, task and state; `--closed` adds the closed
  kits. It reads `.ergon/` and writes nothing.

## Switching work inside a session

**Owner requirement:** when a session turns to another task, that is detected, a new kit is opened (or
the existing one picked), and everything the session keeps from then on is switched to it. The aim is
**isolation of the files**: each piece of work keeps its own plan, steps, briefs, material and note, so
nothing of one lands in another and either can be parked or handed on whole. The switch also gives the
moment to recommend what to do with the work being left.

- **The active kit.** A session has one *active kit*, and in it one active unit — the plan, or one
  job. In a job's worktree the worktree names it (§ Holders, worktrees and the active kit); in the main
  checkout the pick recorded under the session's hashed session marker (P3) does. It is where the session's notes,
  briefs and answers, kept material and `PARK.md` are written, and which SessionStart returns after a
  compaction. A session that has picked nothing writes to no kit; a task with no kit gets one on its
  first write (§ The kit).
- **Two ways a switch is noticed.**
  1. **By a word or an id — code.** The owner names another row (`switch to C183`, «переходим на C183»,
     `/park pick C183`), or a prompt names a row id other than the active kit's as its subject. A hook
     on the prompt can read this, so it is checked and tested; it needs a probe of what each harness
     passes to the prompt hook (P0). A bare mention of an id in passing is not a switch: the hook
     proposes, it never applies on a mention alone.
  2. **By subject — the agent's judgement.** The prompt changes subject with no id. No code decides
     that; the agent's instruction says to ask once, and the owner's answer settles it. This stays
     advisory (A21 axis 2).
- **A switch is confirmed, never silent.** An owner's explicit word applies it and states it in one
  line; a noticed one is proposed with the recommendation below and waits for a yes. Declining keeps
  the active kit.
- **What a confirmed switch does,** in order: (1) the leaving kit's note is written if the work is
  not finished and edits are newer than its note — the same write as an owner's park (P2), state
  `parked`; (2) the target kit is picked, or created with its `PLAN.md` header; (3) the
  pick is recorded and the target's capped digest is handed back, as after a compaction; (4) the
  owner is told the active kit by name, so a wrong pick shows at once.
- **Recommendation on the work left behind.** Read from facts, not typed: a row whose steps are all
  done and whose branch has no uncommitted owned paths → *close the row and archive the kit* (B4); a
  kit with open owner decisions or open review rounds → *park it, and name them*; a kit that is one
  member of a multi-task plan → *the plan's next member is <id>*, from the plan; owned uncommitted
  paths → *name them, commit or leave them with the note*. It is advice: nothing closes or archives
  without the owner's word, and the plan is never edited to say so.
- **What it does not isolate.** The files, not the session's context: what the model has already read
  of the old task is still in its window. So the switch also carries the fresh-session advice (A21
  axis 1): *whatever the fill, a different task is better started in a new session*, and the more so
  when the old task was large. The owner may still keep the session; the kit boundary holds either
  way.
- **Trunk and branch.** The trunk carries the explicit switch only — `park pick <id>` through the
  `park` skill (P4): step (1)–(4) above and the recommendation read by code. The detection by id on
  the prompt hook and the proposal flow are branch B15; the by-subject detection stays advice in the
  agent instructions.
- **In a job's worktree a switch is another worktree.** The worktree holds its job, so a pick of
  another kit is proposed as a worktree for it, with a session of its own; it is never applied as a
  checkout over uncommitted paths (ADR 0028 D10).

## Holders, worktrees and the active kit

The coordination of sessions inside one project. It answers three questions the first layout left
open: who may write a unit now, which unit a session is in, and how two sessions work one plan at
once without sharing a working tree.

### The holder and its lease

- **One holder per unit.** The plan and each job have at most one holder, a session. The hold is the
  file `HOLDER` in the unit's folder — the kit for the plan, `jobs/<n>-<name>/` for a job.
- **Acquire.** Unpark, a pick and the first write create the lease only when it is absent (an
  exclusive create, so two sessions racing for it cannot both win). It names the holder — harness,
  session reference, machine label, worktree — and the time of its last write.
- **Renew and release.** Every write of the helper renews the time. Park and closing release the lease
  by removing it; the note stays.
- **Refuse.** A second session that tries to hold a held unit is refused with the holder named, and is
  told what it may do instead: read the note, hold another job, or ask the owner.
- **Stale.** A lease is judged stale when it is read, from its last write against a threshold; a
  lease written on another machine, which came with a copied kit, is stale at once, and `park export`
  leaves leases out. A stale lease is offered to the
  owner for takeover, never taken silently; a takeover keeps the replaced holder in the note's
  `sessions`, and the replaced holder's uncommitted paths are named before anything else is done. A write never
  takes a stale lease; it is refused and points at `hold --takeover`. Where the unit has no note yet,
  the replaced holder waits in a `SESSIONS` file beside the lease until the next write merges it into
  the note; where the replaced holder's worktree cannot be read, the takeover says so in one line.
- **The state is derived** (ADR 0028 D09): held → **active**; free with `PARK.md` → **parked**; free
  without → **not started**; `JOB.md` says `done` → **done**. A plan's state is joined from its jobs:
  active if the plan or any job is held, else done if every job is done, else parked if the plan or any
  job is parked, else not started. `park list` shows a kit it cannot read as `unreadable` with the
  reason, in its place, and goes on listing the others.
- **No shared file.** A holder writes only inside its unit's folder, and only the plan's holder writes
  `PLAN.md`; with the local index retired (§ The kit is its own record) no file is written by two
  sessions, so there is no lost update to guard against.

### The active unit is read from the file system

Which unit a session is in is a local fact, so it is read from local files and nothing of it is kept
in git (ADR 0028 D10).

- **In a job's worktree** the session is in that job: the worktree's folder
  `.worktrees/<id>-<name>.<n>/` names it, and SessionStart reads it from the path. *Current code, superseded by [ADR 0029/D06](../adr/0029-ergon-athlos-step-one-method-of-work.md#d06--worktrees-follow-the-harness): the active unit is read from the git top level (C190).* The job's lease
  says whether this session may write it — a new session after the old one ended takes the lease over
  on the owner's word, as above.
- **In the main checkout** no kit is active until `park pick <id>`, recorded under the hashed session
  marker (C184). Sequential work — one session at a time on a plan — needs nothing more than that.
- One worktree holds one job, so two sessions never share a working tree: a second session on the same
  plan takes a job of its own and a worktree for it.

### Worktrees for parallel jobs

- **Where.** `<project>/.worktrees/<id>-<name>.<n>/`, inside the project so no harness has to reach
  outside it, ignored by the line `init` writes with `.local/`, `.ergon/` and `.tmp/`. Dotted, so
  pytest, the linters and a search that honours the ignore list skip it; that each harness does is
  measured in A79.
- **Branch.** Git needs a branch to commit on in a worktree; it is `_aitna/<id>-<name>.<n>`, started
  from the project branch. It is **local**: the agent never pushes it, it carries the job's code
  commits and no file of the kit, and it is deleted once its result is carried. It is not where the
  work is recorded — the kit is. The dot, not a slash: git refuses `_aitna/<id>-<name>/<n>` beside an
  existing `_aitna/<id>-<name>`.
- **Nothing of a kit is committed.** `.ergon/` and `.worktrees/` are ignored; the plan, the jobs'
  files, the notes and the leases stay on this machine, so the repository receives only the code the
  owner carries into the project branch.
- **Inside the worktree the agent works on its own.** It creates the worktree, edits, runs the gates
  and commits on the job's branch as it goes, with no confirmation asked; it never pushes or tags. The
  shipped guardrail's § Commits & ownership states this permission, and the harness's approval settings for the worktree are what A79 measures so that nothing there asks either. *Current code, superseded by [ADR 0029/D06](../adr/0029-ergon-athlos-step-one-method-of-work.md#d06--worktrees-follow-the-harness) (the harness makes the worktree where it has one) and [D09](../adr/0029-ergon-athlos-step-one-method-of-work.md#d09--an-agent-commits-only-inside-a-worktree) (the agent commits only inside one); the guard follows in C190.*
- **Carrying a result is the owner's call.** When a job — or a step worth carrying on its own — is
  finished, the agent says so and stops there. Its result enters the current branch only when the
  owner starts the carry, in the way the owner picks: the agent carries it on that word, by a merge
  or a squash into one commit, or the agent prints the commands and the owner runs them. The carry
  is never started by the agent and never folded into other work.
- **Removal.** On the owner's word, or after the result is carried; never while the worktree has
  uncommitted paths ([A63](../../meta/TASKS.md)).
- **The kits stay in the main checkout.** `.ergon/` is ignored and does not follow a worktree, so the
  accessor resolves it through the repository's common directory (`git rev-parse --git-common-dir`),
  and every session of the project sees one set of kits. A session in a worktree writes only its own
  job's folder there. Whether that write makes a harness ask is an A79 measurement; the fallback is
  the harness's flag for an added directory, passed by whoever starts the session.
- **Paths.** Each job line names the paths it expects to touch; two jobs that may run at once and
  share one are named when the plan is read, as advice. The owned uncommitted paths in each note are
  the fact.

### Alternatives weighed

| | How | Why not |
|---|---|---|
| no lock | the agent's discipline | two holders write one kit; nothing shows it |
| a lock by process id | a pid file | means nothing on another machine and dies with a crash |
| the active kit under the session marker only | the D06 first form | two sessions in one checkout write one tree under two kits |
| the active unit from the branch name | the D10 first form | a local fact kept in git; the worktree's folder and the lease already say it |
| a confirmation for each commit in the worktree | the guardrail's default | the owner answers prompts for work nobody else sees; the one moment that needs the owner is the carry |
| a job branch `_aitna/<kit>/<n>` | a slash | git refuses it beside `_aitna/<kit>` |
| worktrees beside the project | `../<project>.<n>/` | outside the project: every harness asks, and the scratch rule is broken |
| the kit carried into the worktree | a copy per worktree | two copies of one plan; the job's folder dies with the worktree |

## The return after compaction

What SessionStart hands back on `compact` (P3, C184), and why the note alone is not enough: the note
is written when the agent parks, and a compaction can come before any park. So the digest has two
parts, both capped together in characters and cut at a whole line with the overflow named (A39):

- **Computed now,** by code, whatever the note says: the active unit and its holder; the branch and
  the last commits since its base (subjects, at most a few); the uncommitted paths, capped; the time
  of the last edit among them.
- **Recorded,** from the unit's `PARK.md`: goal, next action, owner answers received, open owner
  decisions, open review rounds.
- **The comparison.** When the last edit is newer than the note, the digest says so in its first line
  — *the note is older than the last edit; the computed part is newer* — so a stale note cannot pass
  for the state.
- With no note yet, the computed part is the whole digest, and the language and role lines come first
  as C146 asked.

## Briefs — hand-overs to other readers, in rounds (A66, folded)

A **brief** is a hand-over of a piece of work to a reader other than the next resumer: a reviewer,
an auditor, a second opinion, the session that realizes a plan, the session that evaluates it. It
lives in the kit, next to the work it concerns, so the material, the answers and the fixes stay
together.

### Layout — a series per purpose, a round per hand-over

```
<kit>/briefs/<purpose>/<n>/
  BRIEF.md           # producer: the question, what not to take on trust, the shape of the answer,
                     #   where it returns, reader_sees, the material (paths and revisions), follows: <n-1>
  answers/<reader>.md  # one file per reader, written by that reader: verdict + findings F1, F2, …
  DISPOSITION.md     # producer: for each finding — accepted | rejected | deferred, the reason,
                     #   and the step or revision that fixed it
```

- `<purpose>` is a **series**: `review`, `audit`, `second-opinion`, `plan-to-realize`, `evaluate`.
  `<n>` is the **round**, counted from 1 within the series and never reused.
- **A review rarely ends in one round.** Round 1 finds problems; the producer fixes them and records
  in `DISPOSITION.md` which finding led to which step or revision; round 2's brief cites that
  disposition and lists only what changed since, so the reader checks the fixes and looks for new
  problems instead of re-reading everything. The series is **open** until a round has every finding
  disposed and its reader accepts, or the owner closes it.
- **Several readers in one round** — two reviewers, or an auditor and a second opinion — each write
  their own `answers/<reader>.md`: one writer per file. How divergent verdicts are combined is the
  question of A68, not decided here.
- Findings carry ids `F<k>` within a round so a disposition and a later round can name them exactly.

### The record

- **One core, a purpose block.** The core is the park note's fields, so the same record serves
  resume and every other reader. A brief adds what a purpose needs (A66's list): the **question put
  to the reader**; **what the reader must not take on trust**; the **shape of the answer**; **where
  the answer returns**; and whether the reader sees **facts only or facts plus the producer's
  conclusions** (`reader_sees`). Material is listed as paths from the project root.
- **Park before a second opinion.** Before the head calls a second opinion, an auditor or a
  reviewer, it parks the work (the state is fixed in `PARK.md`) and the helper writes the round's
  `BRIEF.md`. The reader gets the brief, not the conversation. A call with no piece of work behind
  it first gets a local row and a kit — cheap, and it keeps the answer somewhere findable.
- **The existing producers feed the helper.** The gate-pack of `gate_pack.py` (C96) and the evidence
  pack of A38 become **kinds** of brief written through the same function; they are not rewritten
  in this task. The order against C150 is settled: the helper is built once, in P2, with the purpose
  block empty, and the kinds land in B8.
- **Completeness per purpose is checked by code:** the helper refuses a brief that lacks a field its
  purpose requires.
- **The answer's place changes.** Second-opinion reports go today to a different folder per harness
  (`.claude/`, `.codex/`, `.qwen/`, `.opencode/`, `.pi/` `second-opinion/`, set by `report_dir` in
  `tools/model_routing/registry.json`). They return to `briefs/second-opinion/<n>/answers/`; the five
  harness folders retire.
- **Constraint:** ADR 0019 D08 closed the cold-resumption pilot with no standing resume-point rule,
  so the brief is justified as one system of fixing, not by a claimed gain in resumption. Kits stay
  local; tracked documents cite the rule, never a kit (ADR 0022 D02).

## Scratch and temporary files

The owner's requirement: scratch stays **inside the project** so no harness asks for an extra
permission — Qwen was named as the frequent case. The rule has three tiers (decided):

| Tier | Where | Lives | Holds |
|---|---|---|---|
| throwaway | `<project>/.tmp/` (ADR 0022 D01), gitignored | until the owner clears it | raw material read once: another model's review, an export, a scratch file |
| kept for the work | `<kit>/material/` | with the kit | material a successor needs to resume |
| answers of other readers | `<kit>/briefs/<purpose>/<n>/answers/` | with the kit | second-opinion, audit and review output |

- Agents are told to write scratch to `.tmp/`, never to `/tmp` or another path outside the project.
  `init` writes the ignore lines for `.tmp/`, `.local/` and `.ergon/` together (C155, on the new
  paths).
- **What is not yet known.** A non-interactive probe ([M207](../../meta/MEASUREMENTS.md)) did not
  separate inside from outside the project: Claude and Codex refused every write, Qwen's default mode
  had no write tool and its `auto-edit` mode wrote everywhere without asking. Which paths make each
  harness ask in an **interactive** session stays unmeasured — the other Qwen rows are the
  second-opinion argv (M180), where write tools are excluded. A probe
  per harness (Qwen first) writes a file inside and outside the project in each approval mode and
  records the prompt behaviour as a `MEASUREMENTS.md` row; the rule above is the design, the row
  decides whether it is enough.
- Hook markers (`delegation-nudge`, the context-pressure marker) are written by the hook process to
  the operating system's temp directory, not by an agent tool call. That they cause no prompt is
  likewise unmeasured and goes into the same probe; moving them into the project is an option only
  if the probe shows a prompt.

## Peers

**Outside this design.** This design collects the material of one piece of work and lets it be
continued elsewhere. The exchange between sessions of *different* projects, and the queue of project
tasks, are another scenario, run through a task tracker — GitHub issues, or a project's `TASKS.md`,
which is a tracker kept in the repository: that is
[A77](../../meta/TASKS.md). The variants first recorded for it — a kit read from a sibling checkout, a
shared folder, bundles, an exchange branch — are its input, not this plan's.

**Inside one project** the coordination of sessions is this design's own and is in the trunk: the
lease, the active unit read from the file system and the worktrees (§ Holders, worktrees and the active kit).
So the park header carries no `peers` field.

## Plan

Shape ([guardrail § Plan shape](../../guardrails/_common.md#plan-shape--reach-a-result-then-refine-it)):
**trunk B** is the smallest result that meets the acceptance condition; every step of the fuller
set (**A**) is a branch that returns to the trunk with the condition still met. Python and the
JavaScript twin move together per [ADR 0020](../adr/0020-node-consumers-js-implementation.md); each
behaviour step ships conformance scenarios, and a new `.py` gets its `js/` pair.

**Acceptance of the trunk:** a piece of work can be parked on the owner's word; after `/compact` or
in a new session the SessionStart hands back a capped digest of that kit's note and its resume
prompt; the kit and the layer sit under dotted folders that `init` ignores; verified live on Claude
Code and with a parity test for Codex per M66. **The trunk run** (D-A59-TRUNKRUN): a real task whose
plan has two jobs, held at once by two sessions on two harnesses (Claude Code and Codex), each in its
own worktree; the second session's attempt on the first one's job is refused with the holder named;
one job is parked and resumed after `/compact`; inside the worktrees nothing asks the owner; both
results are carried into the project branch only when the owner starts it, once by the agent and once
by the commands it prints; a k_auditor audit of the run closes it. More harnesses and platforms are A50's.

### Trunk (B)

| Step | Does | Folds |
|---|---|---|
| **P0** Decision and probes | ADR for the names, the dotted folders, the kit, the branch namespace and the plan's home, amending 0021 D01/D02, 0022 D01/D03/D04 and 0008 §4 (status `parked`; `local/handoff/` and `local/plans/` → `.ergon/`; `ergon` into the reservoir); `MEASUREMENTS.md` rows for Claude SessionStart `source` values, whether `/park` is reserved, and what each harness's prompt hook receives (B15) | — |
| **P1** The dotted layer | one accessor returns `<DEV>/.local/` and `<DEV>/.ergon/`; replace the literals (`common/learning.json` `state_rel`, `tools/model_routing/agents.json` overlay paths, `src/akmon/init.json` ignore lines and their JS twins); move plan A71 into its kit; sweep docs, tests, conformance scenarios; a legacy `local/` makes `verify` warn, never a silent move | A60, C155 paths |
| **P2** The park helper | `tools/park/` (Python and JS): `park write` creates or updates the kit's `PARK.md` (typed header with `plan`, `row`, `sessions`; atomic) and `RESUME.md` (harness-neutral; D05's retirement text included, forced termination stays N15), appends the `parked` index line; `park unpark`; `park list` with filters; the helper API has an empty purpose block for B8 | C150, A66 core |
| **P2b** Holders, jobs and worktrees | the lease `HOLDER` per unit; `jobs/<n>-<name>/` with `JOB.md` and the job lines of `PLAN.md`, the shared-path warning; the park header without `state` and `peers`, branch and revisions read from git, the time of writing; the derived state per kit and per job in `park list`, `--task`, read from the kits with no index line written (D12); the active unit from the worktree's folder; `ergon_root` through the repository's common directory in a worktree; `init` ignores `.worktrees/`; the guardrail's job-branch commit line (C186; carries the former B9) | the review's W2–W4, W7, W9 |
| **P3** Return after compaction | SessionStart on `compact` re-injects the language and role lines and clears the fill reading (C146), plus the two-part digest of the active unit — computed now and recorded in the note, compared (§ The return after compaction) — capped in characters, cut at a whole line, overflow named (A39); in the main checkout the pick is recorded under the hashed session marker | C146, A39, the review's W1 |
| **P4** The `park` skill and the notice | a user skill: park, unpark, pick a task; the context-pressure notice names *park the work → `/compact`* (ADR 0021 D03, new word); `park pick <id>` switches the session's active kit — writes the leaving note, picks or creates the target kit, hands back its digest, and recommends closing, parking or continuing the work left (§ Switching work inside a session); an explicit pick also recommends a fresh session whatever the fill (A21 axis 1) | A67, A21, C150 |

### Branches (A), each returning to the trunk

| Branch | Does | Returns when |
|---|---|---|
| **B1** Stop hold | holds once at a pause or hand-back when project edits are newer than *this kit's* note; unattended runs deny, per the `gate-audit` precedent; Claude only until a Codex main-agent stop exists (M88) | the hold reads the note P2 writes |
| **B2** Pressure and wait triggers | a pressure notice at `warn`, advice before a long wait on an audit (the A67 case), an advisory every Nth compaction with N chosen from M2 and M52 data | the notice names the P4 skill |
| **B3** Role switch | a fresh-session offer on architect→engineer for a large task, with the note written first | the offer calls P2 |
| **B4** Cleanup | closing or archiving a task prunes its kit through `tools/tasks/archive.py` | the kit has a `PLAN.md` header; a closed kit moves to `.ergon/.closed/` (D12) |
| **B5** Guards | `verify` errors when `.local/`, `.ergon/` or `.tmp/` is not ignored or a tracked file names a path under them; warns on a kit with no `PLAN.md` header and on a legacy local index (C155 and C156 on the new paths) | `init` writes the ignore lines |
| **B6** Branch namespace | the commit guard's reason text and the note use `_aitna/<id>-<name>` and a job's `_aitna/<id>-<name>.<n>`; the guard still passes any non-default branch (current code; C190 changes the guard to [ADR 0029/D09](../adr/0029-ergon-athlos-step-one-method-of-work.md#d09--an-agent-commits-only-inside-a-worktree)), so this is a convention plus a message, with its JS twin and scenarios | the note records the branch |
| **B7** Sessions table | a code-made table of kits and live sessions for the owner, on C152's renderer (plain `park list` is already in the trunk) | C152 exists |
| **B8** Briefs | the purpose block, the series and rounds (`BRIEF.md`, `answers/`, `DISPOSITION.md`), the kinds (`second-opinion`, `audit`, `review`, `plan-to-realize`, `evaluate`), the completeness check, `gate_pack.py` and A38's pack feeding the helper, the second-opinion answer returning to the round, the harness `report_dir`s retiring; **starts after A79** (decided) | one review runs two rounds from briefs end to end |
| **B9** Worktrees | **moved into the trunk as P2b** | — |
| **B10** Another machine and harness | `park export` (leases left out) / `park import`, the reachability line for the branch, the refusal of a clashing `_T<n>` with `--as`; a paste-mode `RESUME.md` for a harness with no hook; adapters per harness only after a live probe | a bundle round-trips between two checkouts in a test |
| **B11** Peers | the exchange between projects through the tracker | **leaves this plan: A77** (§ Peers) |
| **B12** Plan status | the join of `park list --plan` (trunk, P2b) with the roadmap digest (C152) | the digest answers "where are we on plan X" |
| **B13** Job graph | the roadmap strand: the jobs of one plan drawn as a graph from their `after` | **leaves this plan: A78** |
| **B14** Scratch and writes per harness | the `.tmp/` rule in the agent instructions, `init`'s ignore line and a decision on the hook markers; the **research of how each harness writes** — Codex, Qwen and Claude by mode, target and model, deciding whether agents on different harnesses and models run side by side with no owner prompts — is the separate task **A79**, and B14 takes its result | A79's matrix exists and the rule matches it |
| **B15** Task switch in a session | the prompt hook reads a row id other than the active kit's and proposes the switch with the recommendation on the work left; a probe of the prompt hook's payload per harness first; a by-subject change stays advice (A21 axis 2); its scenarios and JS twin | `park pick` exists (P4) |
| **B16** Legacy kits | the kits written before this design (`HANDOFF.md`, `RESUME.md`, `PLAN-rev1.md`, loose reports) are given a `PARK.md` header and a `PLAN.md` header from what they hold, by the helper and with the owner's check, so each can be listed and resumed; the rows of the retired local index move into their kits' headers, and `.local/tasks/` files into kits (D12) | `park list` shows every legacy kit with a state |
| **B17** The athlos and the job | the merge of ADR 0021's *athlos* with ADR 0028's *job* into one rung (§ The athlos and the job — one rung, two sides): the relation recorded in a new thematic ADR that owns it, and the vocabulary moved as [ADR 0029](../adr/0029-ergon-athlos-step-one-method-of-work.md) decides ([the merge record](ergon-athlos-merge.md)); under a rename the sweep is mechanical — the helper and its twin, their tests, the plan's line format, the park scenarios, the shipped prose — and the migration is one release with a compatibility read for kits written before it | done: the codes are answered in ADR 0029 (C188); the rename is C189 |

### Parity and honesty

No claim of Codex or Qwen parity without a live probe and a regression test for the exact payload
([AGENTS.md § Verification](../../AGENTS.md)). Measured today: Codex SessionStart reports `compact`
(M66); Claude's `compact_boundary` is recorded (M2); Claude's SessionStart `source` takes `startup`, `resume`, `clear` and `compact` ([M204](../../meta/MEASUREMENTS.md)) and its prompt hook receives the prompt text ([M205](../../meta/MEASUREMENTS.md)); PreCompact/PostCompact have **no row**; Codex has no main-agent stop event (M88). P0 closed the
SessionStart gap; B1 stays Claude-only until M88 changes.

## The kit is its own record — the local index retires

Decided (D-A59-LOCALINDEX b; ADR 0028 D12). The local index (`<DEV>/.local/TASKS.md`, its archive and
`<DEV>/.local/tasks/`, ADR 0022 D03) was made for the work of a plan on one machine. With jobs that
work lives in the plan, and the kit names its tasks and its title in `PLAN.md`; read on akmon's own
index, every row was a plan's row, a parked hand-over or a local task with a description file — each a
kit, or a kit to be.

- **A kit is the local record.** Its `PLAN.md` header carries id, name, title and tasks; a parked
  hand-over is a kit with `PARK.md`; a local thing to do that outgrows a line is a kit with only a
  target. `park list` is the local index, read from the kits.
- **Local ids.** Work with no backlog task takes `_T<n>` on its kit, counted over the kits, live and
  closed, and never reused.
- **Closing.** A closed kit moves to `<DEV>/.ergon/.closed/<id>-<name>/` on the owner's word, through
  the archive tool (B4); the listing skips it unless asked, and the owner prunes it.
- **What `.local/` keeps.** Only what this machine needs: learning state and model overlays.
- **The status `parked` retires** with the rows that carried it; the state is read from the lease and
  the note only.
- **Carriers.** P2b writes no index line and reads the kits; [tasks](../../pipelines/tasks.md) § The
  local layer is rewritten; C152's input moves from local rows to kits; `verify` warns on a kit with
  no header (B5); the existing rows move into their kits (B16), and until then the old index is read
  as legacy input and written by nothing.

| | Alternative | Why not |
|---|---|---|
| a | keep the index beside the kits | two owners of one fact; the one file parallel sessions shared; a transfer had to carry an excerpt of a row |
| c | keep it, generated from the kits | a cache to keep fresh for what `park list` already prints |

## Open

- **The merge's codes** — D-A59-ATHLOS, D-A59-PIECE, D-A59-KEY and D-A59-ARGOS — are answered in [ADR 0029](../adr/0029-ergon-athlos-step-one-method-of-work.md) D02 and D03; the merge record §8 keeps the answers and the options behind them.

The probes P0 and B14 name are measurements rather than choices.
