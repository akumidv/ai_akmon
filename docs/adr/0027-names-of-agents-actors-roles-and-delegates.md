# 0027 — Names of agents, actors, roles and delegates

- **Status:** Accepted for **D01–D06**. The owner chose each name in session when A72 started: one
  word per meaning (**D01**), the actor's values (**D02**), the role declaration (**D03**), the
  charter and its layout (**D04**), the delegate and the host subagent (**D05**), and "actor" kept to
  one meaning (**D06**). Implementation is task A72.
- **Owner:** akuminov@gmail.com
- **References:** [design: actors, agents and the action repertoire](../design/actors-agents-repertoire.md) ·
  [0025](0025-actors-and-action-repertoire.md) (the actor) ·
  [0026](0026-agents-of-the-delivery-chain.md) (the agents) ·
  [0008](0008-mythological-naming-aitna-akmon-kyklopes.md) (the myth cluster) ·
  [0011](0011-agent-name-notation-k-underscore.md) (`k_*` notation; a rename changes the present, not
  the past) · [design: standing agents](../design/standing-agents.md) (A69) ·
  task [A72](../../meta/TASKS.md).

## Context

"Agent" carried six meanings in the tree: a role's definition, a project's development charter, a
`k_*` delegate, a standing agent, a project's own subagent and the host's subagent tool.
[0026](0026-agents-of-the-delivery-chain.md) made the agent the unit of responsibility and the role a
mode of it, so the declaration `🧭 agent: <role>` and the layout of one charter directory per role now
say the opposite of the model. Vendor words — `AGENTS.md`, `.claude/agents/`, `subagent_type`,
`spawn_agent` — cannot be renamed and stay what they are.

## Decision

1. **Agent** names the unit of responsibility and nothing else (**D01**).
2. The actor's values are `developer`, `autonomous` and `guided` (**D02**).
3. The declaration names the role: `🧭 role: <name> — <focus>` (**D03**).
4. A **charter** defines an agent, one directory per agent (**D04**).
5. A `k_*` is a **delegate**; bare "subagent" is the host's mechanism (**D05**).
6. "Actor" means only who drives a run (**D06**).

## Alternatives considered

- **A myth name for the responsibility unit.** The cluster names the workspace, the standard and the
  doer; a new user reads "agent" without a gloss, and 0021 already declined to bind the reservoir early.
- **`worker` for the delegates.** It is a tier; reasoner and auditor delegates are not workers.
- **`domain-expert` for the third actor.** Says who the person is, but not every non-developer is one.
- **Keeping `🧭 agent:`.** It would keep a second meaning of "agent" in the most frequent line akmon
  asks for.
- **The word now, the layout later.** The owner chose both at once, before C174 and C173 name files.

## Consequences

- `meta/CONCEPT.md`, `roles/README.md`, `MODEL.md`, README and the two designs are restated in these
  words; ADRs, reviews and `CHANGELOG.md` keep their text ([0011](0011-agent-name-notation-k-underscore.md)).
- `k_*` files and vendor identifiers keep their names; internal `agent_specs` names may follow later.
- Two consumer-visible changes carry a one-release tolerance: `🧭 agent:` is still accepted, and a
  role-named charter directory still verifies, with a warning.

## Addressable accepted decision blocks

### D01 — One word per meaning; "agent" is the responsibility

`Decision-ID: ADR-0027/D01`

**Agent** names a unit of responsibility with a repertoire, state and skills: the development,
learning, integration, release and publish agents, and a project's own agents. It gets no myth name.
A **project agent** is a project's own agent; **standing** is a lifetime attribute of an agent (a long
session that owns its state), not a noun of its own. A project's narrow executor that holds neither
state nor a repertoire is a **project delegate**.

### D02 — The actor's values

`Decision-ID: ADR-0027/D02`

The actor ([0025](0025-actors-and-action-repertoire.md)/D01) takes the values `developer`,
`autonomous` and `guided`; `guided` is a person who does not know software development, whose key
actions are explained and confirmed.

### D03 — The declaration names the role

`Decision-ID: ADR-0027/D03`

The declaration is `🧭 role: <name> — <focus>`, stated before project work and restated on every
switch. `🧭 agent: <name> — <focus>` is accepted as an alias for one release.

### D04 — The charter of an agent and its layout

`Decision-ID: ADR-0027/D04`

A **charter** is the file that defines an agent: `agents/<agent>/README.md` under the dev-layer
root, one directory per agent (`agents/development/`), the specifics of its roles as sections. A
role-named directory (`agents/architect/`) still verifies, with a warning, for one release.

### D05 — Delegate and host subagent

`Decision-ID: ADR-0027/D05`

A `k_*` is a **delegate**: stateless, chosen by task kind, never wider than its caller. "Kyklops"
survives as the myth gloss of the delegates only; "smith" and "subagent" no longer name them. Bare
**subagent** names the host's mechanism (Claude's Agent tool, Codex `spawn_agent`); every delegate and
project delegate runs as a host subagent.

### D06 — "Actor" has one meaning

`Decision-ID: ADR-0027/D06`

"Actor" means only who drives a run. The OPERATE layer's "runtime actor" becomes "runtime agent".
