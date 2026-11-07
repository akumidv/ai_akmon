# 0029 — Ergon, athlos, step: one method of work

- **Status:** Accepted for **D01–D12**. The owner answered each code of the
  [merge record](../design/ergon-athlos-merge.md) in session: the levels and promotion (**D01**,
  D-A59-DEPTH); the words — *ergon* for the piece of work, *athlos* for the unit, no *argos* (**D02**,
  D-A59-PIECE, D-A59-ATHLOS, D-A59-ARGOS); the key (**D03**, D-A59-KEY); who holds what (**D04**,
  D-A59-HOLD); the record and the transport (**D05**, D-A59-RECORD); worktrees following the harness
  (**D06**, D-A59-WORKTREE — the principle; its design stays in the record's §11.10 until reviewed);
  the explicit export (**D07**, D-A59-CARRY). The owner then reviewed the text and accepted it,
  confirming D02's reading, and stated the rule that **D08** records (decisions carried by code)
  and the commit scope that **D09** records (D-COMMIT-SCOPE, record §11.12). After C194's measurement
the owner accepted the gloss in the entry file with the words a user may say instead (**D10**,
D-C194-GLOSS), names on the ergon's folder only (**D11**, D-C189-NAMES) and the translation of the
old layout on read (**D12**, D-C189-COMPAT).
- **Owner:** akuminov@gmail.com
- **Supersedes, in part:** [0028/D02](0028-park-and-resume-the-kit-and-the-dotted-layer.md#d02--the-kit-one-folder-per-piece-of-work)
  for the word *kit*; [0028/D08](0028-park-and-resume-the-kit-and-the-dotted-layer.md#d08--task-plan-job-and-step)
  for the word *job*; [0028/D10](0028-park-and-resume-the-kit-and-the-dotted-layer.md#d10--the-active-unit-is-read-from-the-file-system)
  for a worktree the harness made; [0021/D04](0021-athlos-deferred-work-packages-and-handoff.md#d04--an-athlos-is-the-labor-not-its-frame-and-not-its-doer)
  for the key of an athlos. Their other content stands.
- **Amends:** [0028/D11](0028-park-and-resume-the-kit-and-the-dotted-layer.md#d11--worktrees-for-parallel-jobs-free-inside-carried-on-the-owners-word)
  — akmon's own `.worktrees/` is the fallback where the harness has no worktrees; the "Untouched" line
  of 0028's Consequences, for 0021/D04 and the athlos vocabulary; [0008 §4](0008-mythological-naming-aitna-akmon-kyklopes.md)'s
  *ergon* amendment, read as naming the work; the common guardrail's § Commits & ownership
  job-branch carve-out and `AGENTS.md` § Commits, by D09.
- **References:** [the merge record](../design/ergon-athlos-merge.md) (the options, prices and the
  method's draft) · [design: park and resume](../design/park-and-resume.md) (the model) ·
  [0020](0020-node-consumers-js-implementation.md) (Python and JavaScript move together) ·
  [MEASUREMENTS.md](../../meta/MEASUREMENTS.md) M36, M37, M41, M82, M90, M189, M190, M210–M220 · tasks
  [C188](../../meta/TASKS.md) (this record), [A59](../../meta/TASKS.md), [A80](../../meta/TASKS.md)
  (when an athlos goes to a subagent), [C189](../../meta/TASKS.md)–[C193](../../meta/TASKS.md) (the
  work this record opens).

## Context

ADR 0021 named the bounded labour of a plan the *athlos* and gave it no carrier; ADR 0028 built the
carrier — the kit, its plan, its *jobs* with a lease, a note and a worktree — and left 0021's athlos
"untouched". Two words then named one rung, and the word ADR 0008 had given to *the work* named only
the folder the kits live in, while the kit took the work's place. The owner asked for one entity with
one name, worked out from the meaning of the words, and for the method around it — how work is cut,
handed to another session, a delegate or another environment, and how the parties exchange what they
know — to lie on the harnesses' own mechanisms rather than across them.

## Decision

1. Work has three fixed levels — **ergon**, **athlos**, **step** — each with a result of its own; an
   athlos that needs a plan of its own is promoted to an ergon, never nested (**D01**).
2. *Ergon* names the piece of work and *kit* retires; *athlos* names the unit and *job* retires;
   *argos* is not adopted; the layer's path `<DEV>/.ergon/` stays (**D02**).
3. An athlos is keyed by its id `<ergon-id>.<n>`; its line carries the `zone:` it lands in (**D03**).
4. Only a session holds a lease; one session commonly holds an ergon and, in turn, one athlos after
   another; a subagent executes under its launcher's lease (**D04**).
5. The record is in the ergon's folder; the harness is the transport (**D05**).
6. Worktrees follow the harness: the binding of an athlos to its worktree is recorded, not encoded
   in a path (**D06**).
7. Only an explicit export moves an ergon off its machine, and it carries the work's changes with
   the record; park stays local (**D07**).
8. The method is carried by the helper's code, its tests and scenarios; prose states what and why
   and names the command (**D08**).
9. An agent commits only inside a worktree; the main checkout's history is the owner's (**D09**).

## Alternatives considered

- **The unit keeps *job*, the athlos retires** (record §6.1 A). No rename; the word for a bounded,
  judged labour leaves the vocabulary. Chosen against: the owner took the Greek word for the rung.
- ***Kit* stays and *ergon* keeps the layer** (record §6.2 A). Free, but the ADRs' own word for the
  piece of work would name a second thing. Chosen against: *ergon* is read as the work.
- **The unit named *argos*** (record §6.4, Idea 4). Collides with the reserved *Arges* and with Argo
  Workflows, whose model 0028/D08 borrowed; the slot it would fill is the machinery, already named by
  file names.
- **A recursive athlos** nested to any depth (record §11.7 Alt-2). One word for two levels in every
  sentence — the inverse of the complaint.
- **A subagent holding a lease itself** (D-A59-HOLD B). A Claude subagent shares its parent's session
  id (M36, M189) and starts without akmon's session context (M37, M41); a lease keyed by session could
  not tell them apart.
- **akmon's own worktree beside the harness's.** Two places for one thing, and an athlos run in a
  harness-made worktree would be invisible to akmon.
- **The ergon tracked in git, or carried by park itself** (record §11.7 Alt-4; D-A59-CARRY B). The
  layer is local on purpose (0028/D01); a transfer is a deliberate act.

## Consequences

- **One migration release** renames *kit* → *ergon* and *job* → *athlos* across the helper and its
  JavaScript twin together (0020), their tests, the plan's line format, the park scenarios and the
  shipped prose, with a compatibility read for kits and `jobs/` folders written before it (C189).
- The plan's athlos line gains `zone:` (C189). The note gains no field for worktrees: the binding
  is read from git and from the lease and note akmon already writes (C190).
- The active-unit lookup reads the lease's worktree, then the note's branch; the folder-name rule
  of 0028/D10 retires (C190).
- `park export` grows into the export of D07, with an import beside it and a portability check
  (C191, absorbing 0028's branch B10).
- The commit guard learns the worktree: a commit inside a worktree on its branch passes, and every
  history-writing git command in the main checkout or outside a worktree is the owner's; the shipped
  carve-out is reworded to match (C190).
- `PLAN.md` is changed through a helper command under the ergon's lease (C192); closing an ergon
  checks that its athlos units cover the plan's criteria (C193).
- When an athlos is handed to a subagent rather than done in the session is open (A80); 0021/D06's
  "the head launches every worker" stands as a rule, though a subagent can now launch one (M212).
- **Untouched.** The `zone` (0021/D04, frozen), the lease and its file `HOLDER`, *step*, *plan*,
  *task*, the branch namespace of 0028/D04, and 0021/D05–D07.

## Addressable accepted decision blocks

### D01 — Three fixed levels, each with a result of its own

`Decision-ID: ADR-0029/D01`

Work is cut into three levels. An **ergon** is a piece of work, realized through a **plan**; its
result is the plan's criteria — the results of its athlos units together with the integration condition
none of them owns. An **athlos** is a unit of that plan, realized through **steps**; its result is
its own acceptance condition. A **step** is a part done in order, its result a checkable done mark.
The zone is not a level: it is the frame of one step's fan-out to delegates.

The composite the owner described — the ergon level and, inside it, a unit, both realized through a
plan and steps — is this self-similarity, not one word over two levels. An athlos whose steps need a
plan of their own is **promoted** to an ergon of its own, linked from its parent's plan line; the
parent keeps the integration step. The depth stays three.

### D02 — The words: ergon, athlos; no kit, no job, no argos

`Decision-ID: ADR-0029/D02`

*Ergon* (ἔργον, the work and what it has made) names the **piece of work** — the folder
`<DEV>/.ergon/<id>-<name>/` and what it holds — and the word *kit* retires. *Athlos* (ἆθλον:
a bounded trial with a verdict) names the **unit** of an ergon's plan — the rung 0021/D04
described as the labour and 0028/D08 as the job — and the word *job* retires. *Argos* is not adopted.
The layer's path `<DEV>/.ergon/` does not move: it is the home of ergons. ADR 0008's *ergon*
amendment is read as naming the work.

### D03 — The key: the id, and the zone on the line

`Decision-ID: ADR-0029/D03`

An athlos is keyed by its place in the plan, the id `<ergon-id>.<n>`, which the plan's lines, the
athlos's folder, its worktree binding, its lease and the plan's `after` edges already read. Its line
in `PLAN.md` carries `tasks:` and a `zone:` field: 0021's pair (task id, zone) is the athlos's
**content**, so one athlos per (task, zone) keeps its own acceptance condition. The zone's spelling
and its parsing stay as 0021/D04 froze them.

### D04 — Who holds what

`Decision-ID: ADR-0029/D04`

Only a **session** holds a lease. The session that holds an ergon is its **head**: the only writer of
`PLAN.md`, the one that merges the results of its athlos units into the plan's criteria and speaks to the owner.
The common case is sequential: one session is the head of an ergon and, in turn, the holder of one
athlos after another — it holds two levels at once, and moving to the next athlos is a pick. A
holder fans a step out to `k_*` delegates; a delegate holds nothing, and its return is real only once
the holder has written it into the athlos's record. A subagent may execute a whole athlos under its
launcher's lease; when that is worth doing is A80's. A holder that wrote its note retires — its
session is not woken — and the athlos resumes under a new holder by takeover, the former holder kept
in the note's sessions.

### D05 — The record is in the folder; the harness is the transport

`Decision-ID: ADR-0029/D05`

What a later reader of any harness, on any machine, needs in order to continue lives in the ergon's
folder, in files with one writer each. A harness's own channels — its resume, todo list, plan file,
memory, a subagent's return in context, a message to a running agent — carry facts faster and are
used where they exist, but none is the only copy: their output is written into the ergon's files
before the work is parked. akmon names where a mechanism's output lands; it does not rebuild the
mechanism.

### D06 — Worktrees follow the harness

`Decision-ID: ADR-0029/D06`

Where the harness makes worktrees, an athlos runs in the harness's worktree, and akmon neither moves
nor renames it nor deletes it. akmon reads every worktree through git, never through a harness's
path layout, and adds the least on top: the binding of an athlos to its worktree is read from what
akmon already writes — the lease names the worktree, the note the branch — rather than encoded in
the worktree's path or kept in a new field. akmon's own `.worktrees/<ergon-id>-<name>.<n>/`, made
the way a harness makes one, stays for a harness with no worktree feature. Because a harness may
start a worktree from a revision other than the head's, the base is checked against git when the
athlos is taken, not assumed and not stored. The design is the merge record's §11.10.

### D07 — Only an explicit export moves an ergon

`Decision-ID: ADR-0029/D07`

*Park* writes the note and stays on its machine; it never transfers. An ergon goes to another
machine, environment or harness only by an explicit **export**, and the export carries the work as
well as the record: the ergon's folder without leases and scratch, each athlos's commits that are on
no remote, its uncommitted changes, and a manifest the import checks reachability against. The
export refuses an ergon that is not portable — an absolute path of the machine it was written on, a
reference into `.local/`, a secret — in one line. The import makes the worktree through the receiving
harness where it has one, and the leases start absent.

### D08 — The method is carried by code, not by prose

`Decision-ID: ADR-0029/D08`

What the method does — the lookup of the active athlos, the base check, the export and the import,
the portability check — is the helper's code, in Python and its JavaScript twin (0020), with its
tests and its park scenarios as the contract. An ADR block states what is decided and why; a design
section holds a mechanism only until it is built, then points at the code; the shipped skills and
guides name the command and never restate its steps. A rule a program can check is checked by it
(the common guardrail's code-design principle), so a step that exists only as a sentence is a gap
to close, not a rule to follow.

### D09 — An agent commits only inside a worktree

`Decision-ID: ADR-0029/D09`

The main checkout is the owner's: an agent changes no history there, on any branch, and writes no
git object or ref outside a worktree — no plumbing write, no scratch repository. Inside a worktree —
one it made (D06's fallback) or one the harness made for its athlos — the agent commits on that
worktree's branch, and may bring other branches or worktrees into it; it never carries the
worktree's branch out. It may propose carrying the worktree into the branch the owner is on; the
owner does it, or asks for it. Pushing, tagging and publishing stay the owner's everywhere. This
replaces `AGENTS.md`'s "an agent may commit on a local non-default branch" and widens 0028/D11's
job-branch carve-out from akmon's own `.worktrees/` path to any worktree an athlos is bound to. The
guard enforces it by the repository a command acts on, not by the session's directory (C190).

### D10 — The words are glossed in the entry file, with the words a user may say

`Decision-ID: ADR-0029/D10`

The block akmon ships into a project's `AGENTS.md`, and akmon's own, carries one gloss of the
method's words beside its pointer to the method:

> Work is tracked in `<DEV>/.ergon/`: an *ergon* is a piece of work (what a user may call an epic, a
> kit or a work package); an *athlos* is a bounded unit of it (a job); a *step* is one line of an
> athlos, checked off when done; to *park* an athlos is to stop it for another session (a handoff, a
> checkpoint). A *task* is a backlog row an ergon serves; a user who says "task" may mean an ergon or
> an athlos, so read which from the id.

The design's words stay (D02); the other words are kept as readings of them, because users and
harnesses say them and an agent has to map them, not refuse them. *Task* is named as ambiguous
because it is the backlog's word. Why (M221–M223): a definition one hop from the entry file is what
saves an agent work, in any vocabulary; a one-sentence gloss was the cheapest carrier that got every
task right; the standard *task* for a unit collided with the backlog's in 10 of 18 runs. The gloss
carries meaning only: the format of a note or a plan line and its place stay with the code (D08).

### D11 — Only the ergon's folder carries a name; what is inside it is coded

`Decision-ID: ADR-0029/D11`

A folder name is information about its entity, and only the ergon needs it: `<DEV>/.ergon/<id>-<name>/`.
What lives inside an ergon is already placed by it and is named by its code alone — an athlos's
folder is the `<n>` of its id `<ergon-id>.<n>`, with no label and no folder for the plural:
`<DEV>/.ergon/<id>-<name>/<n>/ATHLOS.md`. No name, command or field uses a plural form of a word of
the method, so *aethla* and *athla* are not adopted. The label of an athlos stays on its plan line.

### D12 — The old layout is translated on read

`Decision-ID: ADR-0029/D12`

Until C189 is built, and for the records written before it, the helper reads the old forms — the kit
and job words, `jobs/<n>-<label>/JOB.md`, the retired local index — and translates them on read into
the method's words and shapes; it never writes an old form. Once C189 is implemented, the existing
records are rewritten once to the new layout. The readings of D10 stay after that, because they are
the words people use.
