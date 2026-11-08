# 0031 — Work styles: delegating and controlling, apart from the actor and its access matrix

- **Status:** Accepted for **D01–D08**. The owner answered each code in session: the two styles as
  fixed bundles, with the reading of delegation in the controlling style the owner stated
  (**D01**, **D02**, D-STYLE-AXES); where a style is set and switched (**D03**, D-STYLE-CARRIER);
  the block commit printed by the agent and run by the owner (**D04**, D-STYLE-COMMIT (a)); the
  hand-off prompt in chat in the developer's language, recorded in the common guardrail (**D05**,
  D-STYLE-LANG (a)); the style-aware delegation rule (**D06**, D-STYLE-DELEG); the access matrix by
  actor, its carrier and the AI trailer (**D07**, D-ACCESS-MATRIX); what no style changes (**D08**).
- **Owner:** akuminov@gmail.com
- **Extends:** [0025](0025-actors-and-action-repertoire.md) — the access matrix is the actor's
  repertoire made data; D07 decides the design's D-ACTOR-CARRIER and D-COAUTHOR ·
  [0029](0029-ergon-athlos-step-one-method-of-work.md) — a style chooses how the method's sessions are
  started, not what the method is.
- **Amends, for the `autonomous` actor only:** [0029/D09](0029-ergon-athlos-step-one-method-of-work.md#d09--an-agent-commits-only-inside-a-worktree)
  ("pushing, tagging and publishing stay the owner's everywhere") and the common guardrail's
  job-branch carve-out ("never pushes or tags") — an autonomous run pushes its own branch and opens a
  pull request (D07). For a `developer` run both stand as written, and so does
  [0025/D06](0025-actors-and-action-repertoire.md#d06--an-ask-becomes-a-deny-only-when-nobody-attends).
- **References:** [design: actors, agents and the repertoire](../design/actors-agents-repertoire.md)
  (the draft matrix this record settles) · [design: park and resume](../design/park-and-resume.md) ·
  [CAPABILITIES.md](../../CAPABILITIES.md) (the harness matrix) · [agents/](../../agents/README.md)
  (the agent matrix) · tasks [C203](../../meta/TASKS.md) (this record's implementation),
  [C173](../../meta/TASKS.md) (the actor carrier and the repertoire data), [A71](../../meta/TASKS.md),
  [A59](../../meta/TASKS.md), [A80](../../meta/TASKS.md).

## Context

akmon's development agent has one way of splitting work with the developer: delegation is the
default, the orchestrating session cuts the work, hands sub-steps and whole athla to subagents and
worktrees, and the developer sees the result at the gates. Some developers want the opposite split
for some work: to see every transition between stages, to launch each stage session themselves, to
read the prompt that starts it before it runs, and to keep the work in the main checkout with one
commit per block. Neither split is wrong; they are two styles of the same method of work.

Next to this, the commit guard treats every run alike. A developer's run must keep the agent away
from the owner's history, while a run with no developer — an autonomous agent working on its own
branch — must be able to finish its task and commit its result. ADR 0025 named the axis that decides
this, the actor, and left its carrier and its data open. The two questions meet in one place, the
guard's decision, so they are decided together: the style must never be the thing that opens a
permission.

## Decision

In a `developer` run the developer is the owner of the run; this record says *developer* for the
person in the run and *owner* where a rule says only that person may act.

1. A work style is how a `developer` run splits the work with the developer; it is a separate axis
   from the actor and never widens a permission (**D01**).
2. Two styles, each a fixed bundle: **delegating** (the default) and **controlling** (**D02**).
3. The style is set by an in-session command, the developer's local setting, or the project's
   setting, in that order, and switched only by the owner at a park boundary (**D03**).
4. In the controlling style the agent prints the block's commit and the owner runs it (**D04**).
5. A prompt carried between sessions by the developer is chat, in the developer's language;
   the records it points to stay English (**D05**).
6. The delegation rule reads the style: mechanical delegation stays the default in both; in the
   controlling style stages are the developer's and a higher-tier delegate is recommended, not
   called (**D06**).
7. Access is a matrix of actor × action × place; the actor is carried by the launcher's environment
   value; an autonomous actor commits and pushes its own branch (**D07**).
8. Guardrails, the actor's ceiling and the learning and release agents do not depend on the style
   (**D08**).

## Alternatives considered

- **A style as a bundle with per-axis overrides** (D-STYLE-AXES (b)). Every override multiplies the
  combinations nobody tested; an axis that proves to need its own setting can get one later.
- **A style that widens permissions** — the controlling style letting the agent commit in the main
  checkout. A switch the session can reach would then open history writes; ADR 0025 refused a tracked
  file as the actor's carrier for the same reason.
- **The agent commits the block on an `ask`** (D-STYLE-COMMIT (b)). Needs an amendment of 0029/D09 and
  holds only where the guard runs; on Codex it is prose.
- **A hidden worktree per block** (D-STYLE-COMMIT (c)). Contradicts the style's point — the work is
  in the main checkout, where the developer sees it.
- **`RESUME.md` in the developer's language** (D-STYLE-LANG (b)). The record is read by every future
  agent; it stays canonical.
- **No subagents at all in the controlling style** (the first reading of D-STYLE-DELEG). The owner
  rejected it: the stage session would do mechanical work on the orchestrator tier, slowly and at the
  highest price.
- **The access matrix keyed by style.** The style is chosen inside a developer's run and can change;
  the actor is fixed for the run (0025/D01). Permissions follow the fixed axis.

## Consequences

- A developer can work in either style on the same project; the project sets the team's default and
  each developer overrides it locally.
- The commit guard stops being a hard-coded list: it reads the matrix from data by actor, place and
  attendance, and the autonomous run gets its commit without a style or a carve-out.
- `CAPABILITIES.md` gains rows per style and per actor. On Codex the commit guard and the delegation
  nudge are not delivered, so there both styles and the matrix are prose until its probes land
  (D-ACTOR-PARITY); the rows say so.
- The common guardrail's § Language gains a third surface (D05).
- `AGENTS.md` § Delegation and the shipped delegation block become style-aware (D06).
- The common guardrail's § Commits (the carve-out and its runtime-check line), `AGENTS.md` § Commits
  and 0029/D09 gain the autonomous actor's exception (D07).

## Decision details

### D01 — A work style is a developer's split of the work, apart from the actor

`Decision-ID: ADR-0031/D01`

A work style says how a run whose actor is `developer` (0025/D01) divides the work between the
developer and the agent: who starts sessions, how large a stage is, how often the developer is asked,
in which language the prompts the developer carries are written, and where the work is committed. It
applies only to the `developer` actor; an `autonomous` or `guided` run has no style. A style never
widens a permission: what an agent may do is decided by the actor, the place (the main checkout, a
worktree, its own branch) and attendance (D07), and by nothing a style sets. A style may make the
agent ask more or do less; it never makes a denied action pass.

### D02 — Two styles, each a fixed bundle

`Decision-ID: ADR-0031/D02`

| Axis | Delegating (default) | Controlling |
|---|---|---|
| Delegation | the orchestrator delegates sub-steps and whole athla by task kind (MODEL.md § Capability tiers) | the session delegates mechanical sub-steps to the worker tier as usual; stages are not delegated — the developer moves them to sessions; a higher-tier delegate is recommended, not called (D06) |
| Who starts sessions | the orchestrator: subagents, parallel athla in worktrees | the developer: each stage of the ergon runs in a session the developer starts, and its result is carried back by the developer |
| Stage size | an athlos, to its result | a block of steps the developer can check, ending in a park (`PARK.md` and `RESUME.md`) |
| Questions | at gates, one `Needed from you` block at the end | at every stage boundary, plus the developer's reading of the prompt before it runs |
| Prompts | internal briefs to delegates, in English | a prompt addressed to the receiving session, written in the developer's language (D05) |
| Place and commit | worktrees; the agent commits on its branch and prints the squash (0029/D09) | the main checkout, sessions in sequence; one commit per block, printed by the agent and run by the owner (D04) |

In the controlling style the orchestrating session holds the ergon; a stage is cut out of it by the
developer into a separate session, and the stage's result comes back into the orchestrating session
the same way — through the developer, who therefore sees every transition between athla. Inside its
own task each session works as usual. A style is a named bundle; no axis is set alone.

### D03 — Where the style is set and when it switches

`Decision-ID: ADR-0031/D03`

The first of these that is present decides:

1. **The session:** the developer types `/style delegating` or `/style controlling`; the
   `UserPromptSubmit` hook reads the owner's typed prompt and records the style for that
   `session_id` in `<DEV>/.local/`. The agent cannot produce a user prompt, so only the owner can
   switch — which is safe because a style opens nothing (D01).
2. **The developer:** `<DEV>/.local/work.json`, untracked, the same layer as the model-routing file.
3. **The project:** `[work] style` in `<DEV>/.akmon.toml`, read through the project record reader.
4. **akmon's default:** `delegating`.

A switch in the middle of an athlos takes effect at a park boundary: the athlos is parked, then the
new style applies. The SessionStart context states the style in force and where it came from. Codex's
`UserPromptSubmit` carries the typed `prompt` (M65), so the same capture serves both harnesses; until
the capture is wired and tested there, a harness reads the style from the files only.

### D04 — The controlling style's block commit is printed and run by the owner

`Decision-ID: ADR-0031/D04`

At the end of a block in the main checkout the agent parks and prints the commit as commands — the
paths to stage and one `git commit -m "<message>"` with the message it proposes — and the owner runs
them, or asks the agent to. This is 0029/D09 unchanged: the main checkout's history stays the owner's,
and the commit guard needs no new case.

### D05 — A prompt the developer carries is chat, in the developer's language

`Decision-ID: ADR-0031/D05`

A prompt one session hands to another through the developer — the start of a stage session, or the
result a stage session returns to the orchestrating one — is printed in chat, addressed to the
session that receives it and written in the developer's language, because the developer reads it,
checks it and pastes it. It points to the records by path; `PARK.md`, `RESUME.md`, the plan and every
other record stay English. The common guardrail's § Language records this as its third surface: a
prompt carried by the owner between sessions is chat.

### D06 — The delegation rule reads the style

`Decision-ID: ADR-0031/D06`

Delegating mechanical sub-steps (exploration, mechanical edits, validation loops) to the worker tier
stays the default in both styles: otherwise the session does mechanical work on the orchestrator's
model, slowly and at its price. What the controlling style takes from the agent is the delegation of
stages: the agent does not hand a whole athlos to a subagent or start parallel athla in worktrees, and
where the delegating style's orchestrator would call a higher-tier delegate (the reasoner, the
auditor, the implementer of a whole athlos), it recommends that call to the developer instead — which
delegate, for what, and why — and the developer decides; a review, for one, runs on the developer's
call. `AGENTS.md` § Delegation and the shipped delegation block say "delegation is the default" for
mechanical sub-steps in both styles and name the stage delegation as the delegating style's. The delegation nudge keeps counting undelegated mechanical
volume in both styles; the gate audit, in the controlling style, is recommended at the gate and runs
when the developer calls it.

### D07 — Access is a matrix of actor, action and place

`Decision-ID: ADR-0031/D07`

Whether an action passes, asks or is denied is read from the actor (0025/D01), the action and the
place; attendance turns an `ask` into a `deny` when nobody attends (0025/D06). The style is not a key.

| Action | developer (either style) | autonomous |
|---|---|---|
| commit in the main checkout or on the default branch | ask; the agent prints the commands (D04) | deny on the default branch and on `develop`; allow on its own run branch, in its own clone or worktree |
| commit in its own linked worktree, on that worktree's branch | allow (the job-branch carve-out) | allow |
| commit on any other branch | ask | allow on its own run branch, deny elsewhere |
| push its own branch | ask | allow |
| open a pull request or merge request from its own branch into the default branch (new: the guard has no case for it today) | ask | allow; into any other base, deny |
| merge into the default branch, tag, publish | ask | only as its agent's repertoire grants |
| push the default branch or `develop`, forced or not | ask | deny |
| `sudo`; an AI `Co-Authored-By` trailer | prohibited | prohibited |

An autonomous run is held by its isolation and by the forge's protection of the default branch
(0025/D02), so it finishes its task, commits and pushes its result on its own run branch, and opens a
pull request (merge request) from that branch into the default branch; it never commits or pushes to
the default branch or to `develop` (D-C203-AUTONOMOUS-CLONE: the owner's reading of the first row,
and `develop` named as protected). The `guided` actor's row is
A76's. Rewriting an autonomous run's own branch stays open with D-AUTONOMOUS-FORGE. **Its own run branch** is the branch the launcher names in `AKMON_RUN_BRANCH`; with no value, a branch under `agent/` whose name starts with a task id (`agent/C203-…`); release branches (`release/…`) are protected like `develop` (D-C203-RUN-BRANCH). A branch name starts with its task id after any prefix, except the default and release branches — a rule for every actor, checked by the guard only for the `autonomous` run. When the guard cannot read the matrix it denies an `autonomous` run and lets a `developer` run through, the crash posture of [0013](0013-hook-survivability-and-crash-posture.md) (D-C203-GUARD-CRASH; A73 for the other gates). The agent never writes the actor's carrier: a harness settings file's `env` block reaches the hook process (M239), so the guard denies an agent's write to the `env` of harness settings, for every actor (D-C203-ACTOR-WRITE). The actor is
carried by an environment value the launcher sets, `AKMON_ACTOR` (`developer` or `autonomous`), read
at the hook's entry point the way attendance is (decides D-ACTOR-CARRIER); a run with no value, or with
a value the guard does not know, is a `developer` run (D-C203-ACTOR-ENV). The AI trailer is
prohibited for every actor (decides D-COAUTHOR). The matrix leaves the commit guard's hard-coded lists
and becomes data keyed by actor, read by the Python and JavaScript guards alike
([0020](0020-node-consumers-js-implementation.md)), in its own file, `common/access_matrix.json`, which
C173's repertoire reads too (D-C203-MATRIX-FILE (b)); whether one repertoire file per agent joins it
stays C173's D-REPERTOIRE-ARTIFACT. For a `developer` run the matrix keeps the
guard's `git` outcomes — push and tag ask everywhere, history writes pass only in a linked worktree on
its own branch — and adds the forge's pull-request, merge and release commands as asks.

### D08 — What no style changes

`Decision-ID: ADR-0031/D08`

The guardrails stand whole in both styles: secrets, no privilege escalation, the owner's commits and
the job-branch carve-out ([0001](0001-release-and-roles-model.md) D5,
[0028/D11](0028-park-and-resume-the-kit-and-the-dotted-layer.md#d11--worktrees-for-parallel-jobs-free-inside-carried-on-the-owners-word)),
read for a `developer` run (D07 widens push for the `autonomous` actor only), analysis before mutation, the
role declaration, decision codes, English artifacts. So do the actor, its ceiling and its unconditional
prohibitions (0025/D01, D02, D06). The learning and release agents follow their own fixed procedures;
a style applies to the development agent only.
