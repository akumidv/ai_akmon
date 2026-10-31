# 0025 — Actors and the action repertoire

- **Status:** Accepted for **D01–D06**. The owner decided each point in session: that who drives a run
  is an axis of its own and cannot change during the run (**D01**); that a permission is a
  repertoire of allowed actions plus a short list of unconditional prohibitions, with result quality
  weighed above bypass risk and the bypass contained outside the hooks (**D02**); that a run's
  instructions and skills are prepared for it and never committed (**D03**); and that a project's own
  grants are trusted by an owner-accepted digest as a trial, measured before it is kept (**D04**).
  How the trial is built — content-keyed digests in a user-level store with the accepted copies, and
  a provisional place for the grant files — the owner decided when C172 started (**D05**). That a
  hook's `ask` becomes a deny only in a run nobody attends the owner decided on the N14 probes
  (**D06**).
  What carries the actor, the composition of actor and repertoire, and how the repertoire is made
  the recommended path stay open in the design; the names are decided in
  [0027](0027-names-of-agents-actors-roles-and-delegates.md). C172 implements D04 and D05; C178
  implements D06.
- **Owner:** akuminov@gmail.com
- **References:** [design: actors, agents and the action repertoire](../design/actors-agents-repertoire.md) ·
  [0026](0026-agents-of-the-delivery-chain.md) (the agents that hold a repertoire) ·
  [0006](0006-orchestrator-detection-corridor-context-pressure.md) D02 (ask→deny outside default) ·
  [0013](0013-hook-survivability-and-crash-posture.md) (crash posture) ·
  [0022](0022-local-layer-index-and-plans.md) (the local layer) ·
  tasks [A71](../../meta/TASKS.md), [A72](../../meta/TASKS.md), [A73](../../meta/TASKS.md),
  [C174](../../meta/TASKS.md), [C172](../../meta/TASKS.md), [C173](../../meta/TASKS.md).

## Context

akmon's runtime checks assume one kind of driver, a developer at the keyboard. The only signal a hook
reads is the harness permission mode, and every `ask` turns into a `deny` outside the interactive
`default` mode. An agent running alone in an isolated environment therefore cannot push its branch or
open a pull request at all, while a non-developer gets questions phrased for a developer.

The owner widens akmon to three drivers — a developer, an autonomous agent, a non-developer — and to
several agents with different responsibilities ([0026](0026-agents-of-the-delivery-chain.md)). Two
facts shape the decisions. A list of forbidden actions can never be complete, and each entry added
to it narrows what an agent can do for its result. And real containment of an autonomous run already
exists outside akmon: the isolated environment, the branch it commits to, and the forge's limits on
the system user it runs as.

## Decision

1. Who drives a run — the actor — is an axis of its own, set when the run is launched and fixed for
   the whole run (**D01**).
2. A permission is a closed repertoire of allowed actions plus a short list of unconditional
   prohibitions; result quality is weighed above bypass risk, and the bypass is contained outside the
   hooks (**D02**).
3. A run starts from a prepared environment whose run-specific instructions and skills are generated
   for it and never committed (**D03**).
4. A project's own grants are trusted once the owner accepted their digest; this is a trial,
   implemented first and measured before it is kept (**D04**).
5. The trial keys a digest on content, keeps accepted copies in a user-level store and asks at an
   interactive terminal; grant files sit provisionally under `<AITNA_ROOT>/grants/` (**D05**).
6. A hook's `ask` stays a question when someone attends the run and becomes a deny only when nobody
   does (**D06**).

## Alternatives considered

- **Keep keying everything on the harness permission mode.** The mode says how the harness asks, not
  who drives or what the run is for; a developer in `acceptEdits` and an isolated agent in
  `bypassPermissions` need different answers to the same push.
- **A deny-list of harmful actions.** Never complete, and every entry narrows the agent; the owner
  rejected it in favour of a repertoire.
- **The actor as a value in a tracked project file.** The run could edit the file and widen its own
  rights; the actor is set by the launcher instead (the carrier is open).
- **Editing the tracked `AGENTS.md` for a run.** An ignore rule does not hide a change to a tracked
  file, so the edit would surface in every commit of the run.
- **Accepting every grant without a digest.** A project's tracked pipeline file is writable by the
  run it grants rights to.

## Consequences

- **Open, in the design:** what carries the actor; the composition of actor ceiling and agent
  repertoire; the action vocabulary; how a hook learns the agent and the pipeline; how the
  repertoire becomes the recommended path and how an exit is discouraged (A73); the names (A72).
- **Amends nothing yet.** 0006/D02 stays the developer's behaviour; whether a gate fails closed for
  an autonomous run (0013) is decided with A73. New policy ids join the 0012 table when C173 ships.
- **Containment is named, not supplied.** akmon documents the isolation, the commit target and the
  forge limits an autonomous run needs; it does not provide them.
- **Python and JavaScript move together** ([0020](0020-node-consumers-js-implementation.md)).

## Addressable accepted decision blocks

### D01 — The actor: who drives a run, fixed for the run

`Decision-ID: ADR-0025/D01`

Every run has an actor: who drives it. Three exist — a developer, an autonomous agent running alone
in an isolated environment, and a non-developer (working names `developer`, `autonomous`, `guided`,
final names by A72). The actor is set when the run is launched, outside what the run can write, and
it cannot be changed while the run works. A run with no actor set behaves as a developer's run,
which is akmon's behaviour before this record.

The actor is distinct from a role (what operation the agent performs), from an agent (which
responsibility runs, [0026](0026-agents-of-the-delivery-chain.md)) and from the harness permission
mode (how the harness asks).

### D02 — Permissions are a repertoire of allowed actions plus unconditional prohibitions

`Decision-ID: ADR-0025/D02`

What a run may do is expressed as a **repertoire**: a closed vocabulary of allowed actions, held by
the agent and bounded by the actor. Next to it stands a short list of **prohibitions** that hold for
every actor and every agent (privilege escalation is the first). akmon does not try to enumerate
harmful actions.

The loss of result quality weighs more than the risk of a bypass. An action outside the repertoire is
not denied by that fact alone; how it is discouraged is open. The bypass is contained outside the
hooks: by isolating the agent, by isolating where it commits, and by the forge's own limits on the
system user the run works as.

### D03 — The run environment: run-local instructions, never committed

`Decision-ID: ADR-0025/D03`

A run starts from a prepared environment: the product cloned, its dependencies and akmon installed.
The instructions and skills for the run's agent and actor are then generated into it and may be
regenerated for every run. They are run-local: ignored by git and never committed. They live in files
of their own that the harness loads beside the project's tracked `AGENTS.md`, which stays the
project's and is not edited for a run. Which carrier each harness loads is a measurement of the
implementing task.

### D04 — Trust in a project's own grants by an owner-accepted digest, as a trial

`Decision-ID: ADR-0025/D04`

Grants shipped in akmon's installed tree are trusted. Grants a project declares in its own tracked
files take effect only once the owner accepted their digest, recorded where the run cannot write; a
changed digest is untrusted until accepted again.

This is a trial. Its named risk is a loop of re-approvals that is slow and buys little, as the
approval rounds of A22 were. It is implemented first and measured over the period the rest of the
plan takes — re-acceptances, owner time, changes it caught — then kept, simplified or dropped by a
new block.

### D05 — How the digest trial is built

`Decision-ID: ADR-0025/D05`

An accepted digest is the SHA-256 of a grant file's content and is not bound to a project or a path:
the same text carries the same grants in any clone, so a fresh isolated checkout needs no new
acceptance and only a real change asks the owner again. The store is a user-level directory —
`$AKMON_TRUST_DIR`, else `$XDG_STATE_HOME/akmon/trust`, else `~/.local/state/akmon/trust` — outside
every checkout; a launcher gives an autonomous run that directory read-only, which akmon documents
and does not supply. The store keeps a copy of every accepted file, so a re-acceptance shows the owner
the change since the last accepted version of the same path rather than the whole file. An
acceptance is confirmed at an interactive terminal; there is no non-interactive acceptance.

A project's grant files live, provisionally, under `<AITNA_ROOT>/grants/`; the name may change with
the taxonomy (A72) and the repertoire artifact (C173), and the trust mechanism does not depend on it.

### D06 — An ask becomes a deny only when nobody attends

`Decision-ID: ADR-0025/D06`

A hook that forms an `ask` lets it through as a question when the run is attended and turns it into
a deny when it is not. Attendance is read from what the host states: Claude Code sets
`CLAUDE_CODE_SESSION_ATTENDED` in the hook process, `1` in an interactive session and `0` under
`-p`, on the main chain and in a subagent alike (M199, M200). Where the host states nothing (Codex,
an older Claude Code), the earlier rule stands: only the interactive `default` permission mode
attends. A mode that skips every question (`bypassPermissions`, `dontAsk`) is never attended, since
the question would not be asked (M193). The permission mode alone no longer decides: an attended
session in `auto` shows a hook's question (M197), and an unattended `-p` run reports `default`
(M199). This narrows [0006](0006-orchestrator-detection-corridor-context-pressure.md)/D02's
"outside interactive default mode becomes a deny" to the unattended run.
