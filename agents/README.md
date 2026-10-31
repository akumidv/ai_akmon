# agents — the cross-project agent definitions

An **agent** is a unit of responsibility with a repertoire and state; a **role** is a mode it works
in, selected by operation; a **charter** is a project's file that defines one of its agents
(ADR 0026/D06, ADR 0027). akmon ships the definition of each of its agents here, apart from the
[roles](../roles/README.md): the agent's responsibility, the roles it works in, its pipeline and its
hand-offs.

| Concept | Where it lives | What it is |
|---|---|---|
| **Agent definition** | `agents/<agent>.md` here, in akmon | the shared definition: responsibility, roles, pipeline, hand-offs |
| **Role** | `roles/<role>.md` in akmon — or, for `learn` and `release`, inside the agent definition | one mode of an agent, with its own bar |
| **Charter** | `<aitna>/agents/<agent>/README.md` in a project | the project's specifics for one agent, linking the definition |

| Agent | Roles it works in | Definition | Charter directory |
|---|---|---|---|
| development | `review`, `architect`, `engineer` | [development.md](development.md) | `agents/development/` |
| learning | `learn` | [learning.md](learning.md) | `agents/learning/` |
| release | `release` | [release.md](release.md) | `agents/release/` |

[`agents.json`](agents.json) is the one owner of the agent → roles table: `akmon init` writes each
charter's sections from it and the session-start hook names each agent's roles from it. The file's
key order is the order of the delivery chain (ADR 0026/D08) — development, learning, integration,
release, publish, of which the first, second and fourth exist — and wherever akmon lists its agents they
follow it, a project's own agents after them by name. The role
names `learn` and `release` stay valid in the role declaration (`🧭 role: <name> — <focus>`).

The integration and publish agents (ADR 0026/D03, D05) are decided but have no definition yet; each
agent's repertoire arrives with task C173.

## A charter links its definition

A project's charter (`_aitna/agents/<agent>/README.md`) links the agent's definition here, and the
role file for each role it works in under `roles/`, and adds only project specifics — the same
inheritance contract as [roles/README.md](../roles/README.md). A charter directory named for a role
(`architect/`, `engineer/`, `review/`, `learn/`) is the pre-0027 layout and verifies with a warning;
`release/` is the current layout for the release agent.
