# Design — actors, agents and the action repertoire

> **Status: proposed — the base design of task A71.** The parts the owner decided are the
> addressable blocks of [ADR 0025](../adr/0025-actors-and-action-repertoire.md) (actor, repertoire,
> run environment, trust in a project's grants) and
> [ADR 0026](../adr/0026-agents-of-the-delivery-chain.md) (which agents exist and what each owns).
> Everything else here is a proposal or an open question, settled while the plan's tasks are
> implemented, not before them. Names are working names until [A72](../../meta/TASKS.md) fixes them.

## Why this changes

akmon was built to standardize how **a developer** works with an agent: the developer is the owner,
the hooks hold commits and other key actions for them ([ADR 0001](../adr/0001-release-and-roles-model.md)
D5, `commits.owner-owned`), and every rule assumes a person at the keyboard who understands a diff.

akmon now standardizes work for three kinds of driver and for several agents:

- **who drives a run** — a developer; an agent running alone in an isolated environment to solve a
  task end to end; a specialist who does not know software development;
- **which agent runs** — a development agent, an integration agent that decides a merge, a release
  agent, a publish agent, a learning agent, and the agents a consuming project builds for itself.

One rule set no longer fits. What protects a developer's commits stops an isolated agent from
delivering anything; an `ask` a developer reads in a second is a question a non-developer cannot
judge; and a release that "prepares and stops" (D5) is the opposite of a release agent that opens
its pull request and posts its review without prompting anyone.

## What exists, verified in the tree

| Fact | Where |
|---|---|
| The only run signal a hook reads is the harness `permission_mode`; who drives is not known | `hooks/git-commit-guard.py`, `hooks/delegation-nudge.py`; M33, M35 |
| Every `ask` becomes a `deny` outside `default` mode, so an unattended run has no allow path for a push or a pull request | `_escalate_unattended_ask` in `hooks/hook_core.py`; [0006](../adr/0006-orchestrator-detection-corridor-context-pressure.md) D02 |
| The commit guard asks on every `push` regardless of branch and does not see `gh pr create`, `glab mr create`, `--force` or `HEAD:main` | `git_commit_guard_result` in `hooks/hook_core.py`; [C1](../../meta/TASKS.md) |
| No commit guard is wired on Codex | `bin/sync.json` `codex_hooks`; `CAPABILITIES.md` |
| A crashed hook lets the action through | [0013](../adr/0013-hook-survivability-and-crash-posture.md) |
| `.akmon.toml` has no table for checks, actors or agents | `common/record.py` |
| A hook-forced `ask` is not enforced in a background or child session | M34 (version not recorded) |
| "Agent" means six things: a role's definition, a project's dev charter, a `k_*` delegate, a standing agent, a project's narrow subagent, the host's own subagent tool | `roles/`, `<DEV>/agents/`, `.claude/agents/`, [standing agents](standing-agents.md) |
| The concept has three axes — Layer, Role, Archetype — and no driver axis | `meta/CONCEPT.md` |
| Roles were split because one bar cannot optimize analysis, synthesis and implementation at once | `roles/README.md`; [0003](../adr/0003-role-triad-and-develop-use-separation.md) |

## The model in one picture

```
 Actor (who drives; set at launch, fixed for the run)        ADR 0025/D01
   │ launches
   ▼
 Run environment (clone + dependencies + akmon + run-local   ADR 0025/D03
   instructions and skills, ignored, never committed)
   │ hosts
   ▼
 Agent (a responsibility: repertoire, state, skills)          ADR 0026
   ├── works in ──▶ Role (a mode: architect · engineer · review)
   │                  └── follows ──▶ Pipeline ──declares──▶ actions it needs
   ├── acts through ──▶ Repertoire verb (a skill or an `akmon` command)
   ├── delegates to ──▶ Delegate (`k_*`, stateless, by task kind; never wider than its caller)
   └── hands off to ──▶ the next agent of the chain

 Effective permission  =  Repertoire(agent, pipeline)  bounded by  Ceiling(actor)
                          minus  Prohibitions (unconditional)       ADR 0025/D02

 Delivery chain:  development ─PR─▶ integration ─merged─▶ release ─PR─▶ publish
                  learning reads the records of every run
 A consuming project's own agents join the same contract (A69 standard).
```

## Concepts

Working names; the taxonomy and the final names are task A72, which also joins the standing-agent
standard of [A69](standing-agents.md) and the OPERATE rename of C168.

| Concept | What it is | Who sets it | Lifetime | Carries permissions |
|---|---|---|---|---|
| **Actor** | who drives a run: `developer`, `autonomous`, `guided` (a non-developer) | whoever launches the run | one run, never changed inside it | yes — the ceiling |
| **Run environment** | the prepared checkout an agent works in | the launcher | one run | indirectly — what is installed and reachable |
| **Agent** | a responsibility with its repertoire, its state and its skills | the project (akmon ships the delivery chain) | as long as the project keeps it | yes — the repertoire |
| **Role** | a mode an agent works in, with its own quality bar | the agent, by operation | a stretch of a run | no — it selects the pipeline |
| **Pipeline** | the procedure a role follows | akmon or the project | — | declares the actions it needs |
| **Repertoire** | the closed vocabulary of actions an agent is expected to use | agent metadata | — | it is the permission |
| **Prohibition** | an action denied to every actor and every agent | akmon | — | unconditional `deny` |
| **Verb** | the one-call implementation of a repertoire action | a skill or an `akmon` command | — | inherits the agent's |
| **Delegate** | a stateless worker by task kind (`k_*`) | the orchestrating agent | one call | never wider than the caller |
| **Project agent** | an agent a consuming project builds: a standing session, a narrow executor | the project | the project's | the same contract |

**Naming.** The market word for the thing that carries a responsibility and a repertoire is
*agent*, and a user will look for it. The collisions are on the other five meanings. A72 weighs two
directions: keep *agent* for the responsibility and give every other meaning its own word (the
delegates are already *delegates* in MODEL.md; the charter becomes the agent's card), or choose a
distinct, readable word for akmon's agents in the myth cluster of [0008](../adr/0008-mythological-naming-aitna-akmon-kyklopes.md).
Either way the role is a mode of an agent and never an agent itself.

## The agents akmon ships

The decomposition is [ADR 0026](../adr/0026-agents-of-the-delivery-chain.md); the repertoires below
are proposals.

| Agent | Responsibility | Roles | Typical repertoire | Hands off |
|---|---|---|---|---|
| Development | turn a task into a reviewed change | architect, engineer, review | branch, commit on its branch, run checks, run a review through a delegate, fix, open a pull request | the pull request, with open decision codes in its body |
| Integration | decide whether a task's change goes in | review (of the delivered change) | read task, review and fixes; review on its own; classify each finding as a blocker or a new task; merge, return the task, or open new tasks | the merged change, or the task back |
| Release | cut a release | release | release branch from the integration branch, version and changelog commit, pull request, post its review | the release pull request |
| Publish | publish a release | — | tag, publish | the published artifact |
| Learning | turn run records into lasting knowledge | learn | read run records and memory, propose promotions | a promotion proposal |

## Permissions: a repertoire, not a deny-list

Accepted in [0025/D02](../adr/0025-actors-and-action-repertoire.md#d02--permissions-are-a-repertoire-of-allowed-actions-plus-unconditional-prohibitions):
the permission is the set of allowed actions, plus a short list of unconditional prohibitions. A
deny-list of everything harmful can never be complete, and the attempt hollows the agent out. The
loss of result quality weighs more than the risk of a bypass; the bypass is contained outside the
hooks — by isolating the agent, by isolating where it commits, and by the forge's own limits on the
system user it runs as (branch protection, token scope).

**Composition — proposal.** For each action an actor has a default decision and a ceiling; the
agent's repertoire, derived from the metadata of the pipelines it follows, raises the default up to
that ceiling and never past it; a prohibition is never lifted.

```
decision = min(ceiling(actor), max(default(actor), repertoire(agent, pipeline)))
```

There is no person behind an `autonomous` run, so its decisions are `allow`, `note` (context only)
and `deny`; an `ask` there is a `deny` by construction. A `guided` run's confirmation explains the
consequence in plain words before it asks.

**Action vocabulary — proposal.** Dotted ids with a target class:
`git.branch.create`, `git.commit`, `git.push`, `git.push.force`, `git.tag`, `git.merge`,
`forge.pr.create`, `forge.pr.review.post`, `forge.pr.merge`, `pkg.publish`, `worktree.discard`,
`deps.install`, `net.outbound`; targets `default-branch`, `protected-branch`, `own-branch`
(a run prefix), and a pattern (`release/*`).

**Illustration of actor defaults — draft, not a decision.**

| Action | developer | autonomous | guided |
|---|---|---|---|
| privilege escalation | prohibited | prohibited | prohibited |
| branch create or switch | allow | allow | allow |
| commit on own branch | allow | allow | allow, reported |
| commit on the default branch | ask | deny | deny — move the work to a branch |
| push own branch | ask | allow | confirm |
| push default, force, `HEAD:main` | ask | deny | deny |
| open a pull request | ask | allow | confirm |
| merge into the default branch | ask | repertoire only | confirm or deny |
| tag, publish | ask | repertoire only | deny |
| discard the working copy | ask | allow | confirm |

## Steering toward the repertoire — open (A73)

The owner's question is how allowed actions become the recommended and used ones, and how an action
outside the repertoire is discouraged without being blocked. Four layers were drafted:

- **A — the easy path.** Every repertoire action has one verb (a skill or an `akmon` command) that
  does the mechanics right — branch name, pull-request body, pre-checks — and writes an event.
  SessionStart injects the agent's repertoire. This is the only layer that raises quality rather than
  only steering it.
- **B — a nudge on exit.** PreToolUse classifies a call as in, out or unknown; out returns context
  naming the repertoire verb for the same intent ("use `Y`; if it cannot do this, say why in the
  pull request"), first use per session and action class, re-armed by episode like the delegation
  nudge; never an `ask`. Every event is logged and summarized at the gate and in the pull request.
- **C — a gate.** Only for prohibitions and a few actions the forge does not contain, by exact parse
  of mutating forms.
- **D — prose only.** No evidence either way; the delegation-drift data is why the nudge hook exists.

Recommended: A as the main investment, B with its log from the start, C only after C1. A nudge
tolerates a coarse classifier (an unparseable call is logged as unknown, never nudged); a gate needs
C1's exact parser, and an unparseable call must not pass a gate silently. On Codex, a PreToolUse
context channel and an enforced output contract have no measurement yet.

## Who tells a hook which agent and pipeline run — open

A hybrid, by actor; to be designed with the implementation:

- `autonomous`: the launcher names the agent and the pipeline next to the actor; the run cannot
  change them.
- interactive actors: entering a pipeline asks once and lists what will then run without asking
  (in plain words for `guided`); the grant lasts until the pipeline ends or times out.
- the subagent type in a hook payload is a third carrier, pending a measurement, and its definition
  file is editable by the agent.

## Trusting a project's own grants — accepted as a trial

[0025/D04](../adr/0025-actors-and-action-repertoire.md#d04--trust-in-a-projects-own-grants-by-an-owner-accepted-digest-as-a-trial):
grants shipped in akmon's installed tree are trusted; grants a project declares in its tracked files
take effect once the owner accepted their digest, recorded where the run cannot write. **Risk named:**
this can become a loop of re-approvals that is slow and buys little — the experience of A22. So it is
implemented first and measured over the period the rest of the plan takes (re-acceptances, owner time,
changes it caught), then kept, simplified or dropped.

## The run environment

[0025/D03](../adr/0025-actors-and-action-repertoire.md#d03--the-run-environment-run-local-instructions-never-committed):
a run starts from a prepared environment — the product cloned, its dependencies and akmon installed —
and the instructions and skills for the run's agent and actor are generated into it. They are run-local:
ignored by git and never committed.

The tracked `AGENTS.md` belongs to the project, and an ignore rule does not hide a change to a tracked
file. The run's instructions therefore live in files of their own that the harness loads beside it
(the harness-local instruction file, a run-local skill directory, the SessionStart injection), not in
an edited `AGENTS.md`. Which carrier each harness loads is a measurement. This also answers akmon's
own case: its `AGENTS.md` keeps the developer's narrower rule (an agent never pushes, merges or tags),
and an agent run on akmon receives its repertoire from the run-local layer.

## What this amends

| Record | Change | By |
|---|---|---|
| [0001](../adr/0001-release-and-roles-model.md) D5 | the release agent commits and opens its pull request; tag and publish move to the publish agent | 0026/D04, D05 |
| [0006](../adr/0006-orchestrator-detection-corridor-context-pressure.md) D02 | stays as the `developer` default; `autonomous` has no `ask` by construction | A71 implementation |
| [0012](../adr/0012-stage1-contracts-and-vocabulary.md) | new policy ids for repertoire, prohibition and actor checks | C173 |
| [0013](../adr/0013-hook-survivability-and-crash-posture.md) | whether a gate fails closed for `autonomous` — open | A73 |
| [0015](../adr/0015-mission-and-resource-allocation.md), MODEL.md mission | the integration agent's merge decision is the separately accepted acceptance authority the mission requires | 0026/D03 |
| `meta/CONCEPT.md`, `roles/README.md`, README | a fourth axis (actor) and the agent ↔ role relation | A72 |

## Open questions for the start

Each is decided while its task is implemented, not before it.

- **D-ACTOR-CARRIER** — what carries the actor: an environment value from the launcher, a user-level
  file, both; may a tracked file narrow it.
- **D-AGENT-TERM** — the word for akmon's agents and for each colliding meaning (A72).
- **D-PIPELINE-SIGNAL** — how a hook learns the agent and pipeline per actor (above).
- **D-REPERTOIRE-ARTIFACT** — one data file per agent, or the repertoire in pipeline metadata, as the
  single owner the SessionStart block, the nudge and the log all read.
- **D-REPERTOIRE-NUDGE** — how loud an exit is; can it become an `ask` for a developer.
- **D-AUTONOMOUS-FORGE** — GitHub and GitLab; draft or ready pull request; rewriting its own branch.
- **D-AUTONOMOUS-FORK** — at a design fork with no owner: take the conservative option and list the
  question in the pull request, or stop.
- **D-GUIDED-PROFILE** — what a non-developer does unasked, which actions need an explanation, which
  surface they use (an `ask` reaches only an interactive `default` session), how much of the process
  (roles, ADR, decision codes) applies.
- **D-COAUTHOR** — the AI trailer in an autonomous run's commits: forbid, allow or require.
- **D-MERGE-CONDITIONS** — what the integration agent requires before a merge, and into which branch.
- **D-ACTOR-PARITY** — Claude first, Codex after its probes.

## Plan theses

The working plan is local ([0022](../adr/0022-local-layer-index-and-plans.md) D04); these theses are
enough to rebuild it.

- **Target.** One `autonomous` development-agent run in a prepared environment takes a task to a
  pull request — branch, commit, review, fix, commit, pull request — with its repertoire injected and
  every action logged; a push to the default branch, a merge, a tag and a prohibited action do not
  happen. The developer's behaviour is unchanged.
- **First, by the owner's order:** digest trust for a project's grants (C172), so its cost is
  observed through the rest of the plan.
- **Trunk:** names fixed (A72) before any file is named after them → run environment (C171) →
  actor carrier, repertoire data, SessionStart injection, event log for the development agent (C173)
  → the target run.
- **Branches back to the trunk:** steering layers B and C (A73, after C1); the integration, release
  and publish agents' cards (A74); `guided` confirmations in plain words; Codex after its probes (N20).
- **Measured, not assumed:** an `ask` in print mode and in a child session (N14), the subagent type
  in a hook payload and Codex's PreToolUse context (N20), out-of-repertoire events per run, the digest
  trial's cost.
