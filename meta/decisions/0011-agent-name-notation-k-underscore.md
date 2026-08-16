# 0011 — Agent name notation: `k_*`, one notation for every vendor

- **Status:** Accepted (A12 lock, scoped to the agent-name question; the rest of A12's
  deterministic-hardening shapes lock separately). Owner-verify point: D2-15.
- **Owner:** akuminov@gmail.com
- **References:** [ADR 0008](0008-mythological-naming-aitna-akmon-kyklopes.md) (the `k-`
  prefix and its *Kyklōpes* reading) · [ADR 0010](0010-alternatives-adoption-a11-verdicts.md)
  (A12 owns the decisions that ride the N2 inventory) · backlog carrier
  [C46](../TASKS.md) (the mechanism half — neutral declaration + per-vendor name map) ·
  N2 stage-0 findings [`n2-stage0-probes-inventory-20260807.md`](../reviews/alternatives/n2-stage0-probes-inventory-20260807.md)
  · ledger row D2-15.

## Context

akmon generates six delegate definitions — `k-explorer`, `k-mechanic`, `k-validator`,
`k-implementer`, `k-reasoner`, `k-auditor` — from `AGENT_SPECS`. The hyphenated form dates
from ADR 0008, which fixed the `k-` prefix without any vendor named as a constraint; Claude
Code was the only delivery path at the time.

N2 stage-0 probe F2 tried to spawn a Codex subagent under akmon's own delegate name and was
rejected outright:

```
Rejected: agent_name must use only lowercase letters, digits, and underscores
```

Read from the shipped `codex 0.146.0` binary, the full constraint set on `agent_name` is:
must not be empty · lowercase letters, digits and underscores only · must not contain `/` ·
`root` is reserved. The hyphen makes **all six** akmon delegate names illegal as Codex agent
names. Claude accepts the hyphen, which is why the split never surfaced: one vendor's
permissiveness had been silently encoded as a cross-vendor contract.

Nothing in the current shipped surface breaks — `bin/sync.py` emits only `.codex/README.md`
and `.codex/hooks.json` for Codex, so akmon ships no Codex agent definitions today. The
exposure is to the *plan*: D4 and any step that would give Codex delegates the `k-*`
identity.

**Corrected after publication, from measurement rather than inference.** This ADR first
stated that `collaboration.spawn_agent` takes `agent_name` and `task_name` as separate
parameters, and that codex has no agent-definition file convention. Both are wrong. The
spawn tool exposes `task_name`, `fork_turns`, `model` and `message`; `agent_name` is the
name under which the **task name's** path segment is validated, which is why passing
`task_name="k-explorer"` produced an `agent_name` error. And codex 0.146.0 *does* have an
agent-definition convention — `<repo>/.codex/agents/<name>.toml` (also
`$CODEX_HOME/agents/`), carrying `name`, `description`, `developer_instructions` and
model/reasoning/sandbox overrides, selected at spawn time by an `agent_type` argument. See
[N2 findings §1A.6](../reviews/alternatives/n2-stage0-probes-inventory-20260807.md).
Neither correction disturbs the decision — the constraint that forced it is a property of
the name, not of where the name is declared — but it removes the ADR's stated reason for
*not* generating Codex agent definitions, which is now an open design question rather than
an absence of mechanism.

## Decision

**Rename all six delegates to the `k_*` notation — one notation used unchanged by every
vendor.** The `k-` prefix of ADR 0008 survives as `k_`; the *Kyklōpes* reading is untouched.

Measured before deciding, not assumed: a `k_`-named agent definition placed in a wired
consumer is offered by **Claude Code 2.1.221** as a subagent type alongside the hyphenated
ones. The notation is legal on both vendors; only the hyphen was not. Confirmed from the
other side afterwards by probe F3: `k_explorer` spawns on codex 0.146.0 without complaint and
the child carries it as a real, addressable identity — codex's own rollout records the
dispatch as `author: "/root"` → `recipient: "/root/k_explorer"`, and the child reports the
same path as its name.

**Scope boundary — what is renamed and what is not.** Renamed: `AGENT_SPECS` and the
generated definitions, hook and tool prose, tests, and the currently-true documentation
(`README.md`, `BOOTSTRAP.md`, `meta/design/model-routing.md`, pipelines, roles, skills,
examples). **Not renamed:** records of what was decided or observed at a time — ADRs 0004 /
0005 / 0006 / 0008 / 0010, everything under `meta/reviews/`, `CHANGELOG.md`, the D2 ledger's
historical rows, V2's owner-locked name trio (`k-synthesizer`→`k-auditor`), and the
hyphenated names quoted inside C46 as the defect itself. Rewriting those would make the
record state something that never happened; a rename is a change of the present, not of the
past.

**Migration is part of the decision, not a follow-up.** `tools/model_routing/routing.py`
gains `obsolete_agent_files` / `remove_obsolete_agents`: on every init and every hook rebind,
a generated agent definition on disk that the current `AGENT_SPECS` no longer plans is
deleted. Only files carrying `GENERATED_BANNER` are candidates, so a hand-written agent in
the same directory is never a deletion target. Without this the rename would not migrate
anything — it would *duplicate*: `bin/sync.py`'s obsolete-file sweep covers only
`.claude/skills/*/SKILL.md` and never looked at `.claude/agents/`, so every consumer would
carry twelve agent definitions, six of them stale, still model-pinned, still advertising the
non-existent tools of C46, with nothing warning.

## Consequences

- Consumers pick the rename up on the next `init.py` run or the next SessionStart rebind:
  six `k_*.md` written, six `k-*.md` deleted. No manual step, and the deletion is reported
  (`deleted: …`) rather than silent.
- **Delegation history does not migrate.** `agent_tier_map()` keys tiers by the live
  `AGENT_SPECS` names, so delegation-log rows and subagent transcripts written before the
  rename carry `k-*` names that no longer resolve to a tier. Per-agent stats therefore split
  across the rename boundary. Accepted (owner, D2-15 clause 3): the log is an
  append-only record of what actually ran, and rewriting it to make a chart continuous would
  be the same falsification the scope boundary above rejects. **Folding the notation in the
  stats path is rejected with it** — `resolve_briefs` folds case and `-`/`_` through
  `agent_key`, and applying that same fold in `stats.py::label_and_tier` would close the split
  without touching the log. It is rejected because the two lookups answer different questions:
  a brief key is a consumer's address for a *live* agent and must survive a rename, while a
  log label names *what ran*, under a name that no longer exists. Folding it would join
  pre- and post-rename runs into one continuous per-agent series — falsifying the chart
  instead of the file, which is the same loss one layer up. The asymmetry is therefore the
  decision, not a half-done migration, and a reader who wants the joined view states the
  mapping explicitly at read time.
- A prompt or brief that names a delegate literally must use the new form; the old name is
  no longer a valid subagent type once the stale definition is pruned.
- **Consumer overlay `briefs` keys do *not* have to be migrated.** They were matched against
  the spec name exactly, so the rename orphaned them silently — the generated definition
  shipped without the project's hand-authored instructions and the sweep above then deleted
  the `k-*.md` that still carried them. Found in review, carried as
  [C50](../TASKS.md) and fixed there: the lookup now folds case and `-`/`_`, and a brief key
  matching no agent is a hard error that stops the regeneration instead of an empty string.
  The general lesson for the scope boundary above: a rename reaches further than the files
  akmon generates, into the keys by which a consumer addresses them.
- The rename buys a shared *notation*, not a shared *mechanism*. C46 remains open and still
  owns the real fix — declare capabilities and identities neutrally, map them per vendor, and
  fail loudly on a name the target harness does not know. This ADR removes one instance of
  the problem; it does not remove the class.

## Alternatives

- **Per-vendor name map (`k-explorer` on Claude, `k_explorer` on Codex)** — rejected. It
  gives one delegate two identities, so every log line, brief, stats row and owner-facing
  message has to say which vendor's spelling it means. It also presupposes exactly the
  mapping machinery C46 has not built yet, making the fix depend on the unbuilt thing.
  Revisit-if: a future vendor's constraints are mutually exclusive with another's, at which
  point no single notation can exist and the map becomes unavoidable.
- **Keep the hyphen; give Codex delegates no akmon identity** — rejected. It is free today
  precisely because akmon delegates nothing to Codex subagents, and it forecloses D4 by
  making the Codex arm structurally unable to carry a role identity. Cheap now, and pays for
  it exactly when the Codex arm starts to matter.
- **Drop the `k` prefix entirely while renaming** — rejected as out of scope. The prefix
  carries ADR 0008's naming and is what makes a generated delegate recognizable as akmon's;
  the hyphen was the defect, not the prefix. Bundling an unforced naming change into a forced
  compatibility fix would put both beyond a single owner verification.
