# 0026 — Agents of the delivery chain

- **Status:** Accepted for **D01–D08**. The owner decided in session that the development roles are
  roles of one agent (**D01**), that learning is an agent of its own (**D02**), that a separate
  integration agent decides a merge (**D03**), that a release agent cuts a release without prompting
  the developer (**D04**), and that tag and publish belong to a separate publish agent (**D05**). The
  names are fixed by [0027](0027-names-of-agents-actors-roles-and-delegates.md); each agent's repertoire is a
  proposal in the design. When release and learning became agents, the owner chose a folder of agent
  definitions apart from the roles (**D06**) and a learning run over the project's sessions with a
  reminder after 10 sessions or 7 days (**D07**). On that implementation the owner chose to list the
  agents in the order of the chain and to make a learning run due before a pull request (**D08**).
- **Owner:** akuminov@gmail.com
- **Supersedes, in part:** [0001](0001-release-and-roles-model.md) D5 — the owner no longer executes
  the commit of a release: the release agent commits and opens its pull request (**D04**), and tag and
  publish move to the publish agent (**D05**). D5 stands for every run whose agent holds no such grant.
- **References:** [design: actors, agents and the action repertoire](../design/actors-agents-repertoire.md) ·
  [0025](0025-actors-and-action-repertoire.md) (actor and repertoire) ·
  [0003](0003-role-triad-and-develop-use-separation.md) (the role triad) ·
  [0015](0015-mission-and-resource-allocation.md) D01 (acceptance authority needs its own decision) ·
  [design: standing agents](../design/standing-agents.md) (A69) ·
  tasks [A71](../../meta/TASKS.md), [A72](../../meta/TASKS.md), [A74](../../meta/TASKS.md).

## Context

"Agent" in akmon today is a role's charter, and every step from a finished change to a published
release is the owner's: the release role prepares commit, tag and publish commands and stops (0001
D5). The owner wants the chain itself run by agents, each with one responsibility and the repertoire
that responsibility needs ([0025](0025-actors-and-action-repertoire.md)/D02), and wants the
development roles, which share one responsibility, kept together.

## Decision

1. Architect, engineer and review are roles of one development agent (**D01**).
2. Learning is an agent of its own (**D02**).
3. An integration agent decides whether a task's change is merged (**D03**).
4. A release agent cuts a release and opens its pull request without prompting the developer
   (**D04**).
5. Tag and publish belong to a publish agent (**D05**).
6. akmon defines its agents in a folder of their own, apart from the roles (**D06**).
7. The learning agent reads the project's sessions since its last run and is recalled by a reminder
   (**D07**).
8. Agents are listed in the order of the chain, and a learning run is due before a pull request
   (**D08**).

## Alternatives considered

- **One agent per role.** The three development roles share one responsibility, one state and one
  task; splitting them into agents multiplies hand-offs without a different repertoire.
- **The development agent merges its own change.** The decision to accept a change would be taken by
  the author of the change.
- **The release agent also tags and publishes.** Publishing is irreversible in a way a pull request is
  not; it gets its own agent and its own repertoire.

## Consequences

- **Roles keep their bars.** The reason roles were split — one bar cannot optimize analysis,
  synthesis and implementation at once — still holds; what is one is the responsibility, the
  repertoire and the state. The audit stays a delegate tier the agent calls.
- **0015's condition is met here.** The mission adds no autonomous acceptance authority and requires
  one to be decided on its own; D03 is that decision, bounded to the integration agent.
- **A consuming project's agents** join the same contract through the standing-agent standard (A69);
  the taxonomy and the relationship graph are A72.
- **Open, in the design:** each agent's repertoire, the integration agent's merge conditions and
  target branch, whether the publish agent asks under each actor.

## Addressable accepted decision blocks

### D01 — The development agent and its roles

`Decision-ID: ADR-0026/D01`

Architect, engineer and review are roles of one **development agent**. The agent owns the
responsibility (turn a task into a reviewed change), the repertoire and the state; a role is a mode it
works in, selected by operation, with its own quality bar and pipeline as [0003](0003-role-triad-and-develop-use-separation.md)
defines them. The audit stays a delegate tier the agent calls, not a role.

### D02 — The learning agent

`Decision-ID: ADR-0026/D02`

Learning — turning the records of runs into lasting knowledge — is an agent of its own, not a role of
the development agent. It reads the records every run leaves and proposes promotions.

### D03 — The integration agent decides a merge

`Decision-ID: ADR-0026/D03`

An **integration agent** takes a task's delivered change: it reads the task, the review and the fixes,
reviews the change on its own, and classifies every review finding as a **blocker** or a **new task**
that does not stop the merge. It then merges the change, or returns the task for rework, and opens a
task for every finding it did not treat as a blocker. It does not release.

### D04 — The release agent

`Decision-ID: ADR-0026/D04`

A **release agent** cuts a release without prompting the developer: it creates the release branch
from the integration branch, commits the version and changelog, opens the pull request and posts its
review. It does not tag or publish.

### D05 — The publish agent

`Decision-ID: ADR-0026/D05`

Tag and publish, where a project publishes at all, belong to a **publish agent** of their own. Whether
it asks before acting is set by the actor of its run ([0025](0025-actors-and-action-repertoire.md)/D01).

### D06 — Agent definitions apart from the roles

`Decision-ID: ADR-0026/D06`

akmon ships the definition of each of its agents in a folder of agent definitions, apart from
`roles/`: the agent's responsibility, the roles it works in, its pipeline and its hand-offs.
`roles/` keeps only the modes of the development agent — review, architect, engineer. The release and
learning agents work in one mode each, `release` and `learn`, defined inside their agent definitions;
those names stay valid in the role declaration. `akmon init` scaffolds a charter for the development,
release and learning agents (`agents/development/`, `agents/release/`, `agents/learning/`); a charter
directory named `learn/` is a legacy layout and verifies with a warning for one release, as the other
role-named directories do ([0027](0027-names-of-agents-actors-roles-and-delegates.md)/D04).

### D07 — The learning agent's run and its reminder

`Decision-ID: ADR-0026/D07`

The learning agent reads the sessions of the project it serves — never other projects' — recorded
since its last run, and proposes what to keep; nothing is persisted until the owner confirms it. The
end of a run is recorded in the project's local layer. At session start a hook reminds the owner and
the model to run it once 10 sessions or 7 days have passed since that run, whichever comes first, and
only when at least one session has passed; the project may change both thresholds. In the first
version the owner starts the run through a skill; a scheduled run waits for the run environment
(C174).

### D08 — The chain's order and a learning run before a pull request

`Decision-ID: ADR-0026/D08`

Wherever akmon lists its agents, they follow the delivery chain — development, learning,
integration, release, publish — and a project's own agents follow them by name. Learning stands
before integration because a change carries the lessons of the sessions that made it: before a pull
request is opened, by the release agent or by the hand-off that leads to integration, a learning run
is due when at least one session has passed since the last one. The agent opening the request tells
the owner and offers the run; it does not start it on its own, and what the owner confirms lands in
the same pull request. This adds a third occasion to D07's reminder; its thresholds still govern the
session-start one.
