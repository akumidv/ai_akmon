# 0008 — Mythological naming: `_aitna` (forge-workspace), `akmon` (the standard), Kyklōpes (`k-`)

- **Status:** Accepted (naming locked; on-disk migration is [V1](../TASKS.md), owner-timed). Supersedes
  V1's earlier English `anvil` choice.
- **Owner:** akuminov@gmail.com
- **References:** backlog [V1](../TASKS.md) (execution scope, both keystone and the alphavar consumer) ·
  README [naming section](../../README.md) (the operative explanation a consuming project reads) ·
  V1's predecessor framing (`ai_keystone`→`ai_anvil`) which this replaces.

## Context

The names were a **mixed metaphor**. `keystone` is masonry (an arch's central stone); `_forge` is a
smithy; the `k-` subagent prefix (`k-explorer`, `k-implementer`, …) was merely "keystone-derived". Three
unrelated images for one system. V1 already recognised this and proposed collapsing to a single smithing
metaphor by renaming `keystone` → `anvil`, but plain English `anvil`/`forge` left the `k-` prefix
unexplained and carried no other hook.

The owner chose to seat the whole system in **one myth cluster**: Hephaestus's forge beneath **Mount
Etna**, where the **Cyclopes** work the **anvil** to hammer out the thunderbolts of Zeus. It is coherent
(one scene, not three metaphors), it retro-fits the `k-` prefix for free, it opens a reservoir of names
for future entities, and the workspace name gains an **ai** hook.

## Decision

Adopt a three-name mapping drawn from the cluster. The vocabulary *is* the purpose statement: the shared
standard is the **anvil** every project is hammered into shape on, worked by the assistant's smiths,
inside each project's own forge-workspace.

| myth (Greek) | role in the system | current name | new name |
|--------------|--------------------|--------------|----------|
| **Aitna** (Αἴτνη) — the volcano the forge sits under | each project's **dev-layer workspace** (the fire where the project is built); begins with **ai** | `_forge/` | `_aitna/` |
| **akmon** (ἄκμων) — the anvil in the forge | the **shared standard** mounted inside the workspace | `keystone` (repo `ai_keystone`) | `akmon` (repo `ai_akmon`), mounted at `_aitna/akmon/` |
| **Kyklōpes** (Κύκλωπες) — Zeus's smiths (Brontes, Steropes, Arges) | the **subagents** — the `k-` prefix | `k-*` | `k-*` (prefix kept, re-read as *Kyklōpes*) |

Load-bearing points:

1. **Containment is literal.** The anvil sits *inside* the volcano-forge, exactly as `akmon/` sits inside
   `_aitna/` — the same nesting as today's `_forge/keystone/`. This is what fixes the assignment:
   keystone (the contained standard) = anvil; `_forge` (the container workspace) = the volcano-forge.
   The reverse mapping would put a volcano inside an anvil.
2. **The `k-` prefix does not migrate.** It stops meaning "keystone" and starts meaning "Kyklōpes" — a
   pure re-reading, zero code/doc churn on the prefix. Orthogonal to [V2](../TASKS.md)'s `k-synthesizer`
   → `k-auditor` rename, which changes the *suffix* only.
3. **The `ai` hook lands on the visible touchpoint.** `_aitna/` is the folder every consuming repo shows;
   it advertises "this repo is worked by the AI apparatus" at the point of contact, while the engine
   inside carries the terse product name `akmon`.
4. **Reservoir for future entities** (name once, from the same scene): **keraunos** (κεραυνός,
   thunderbolt) — a shipped deliverable/release; **Hephaistos** — the orchestrator; **Brontes / Steropes
   / Arges** — smith tiers; **sphyra** (hammer) / **physa** (bellows) — tools.

Execution (repo rename, folder/mount move, `.keystone.toml` → `.akmon.toml`, `_forge`→`_aitna` in the
alphavar consumer incl. the `_forge.*` import path, doc sweep with older ADRs grandfathered) is one
migration release, scoped in [V1](../TASKS.md). Cheapest now — alphavar is the sole consumer.

## Consequences

- One coherent metaphor replaces three; the previously-unexplained `k-` prefix becomes the best-motivated
  name in the set, at no migration cost.
- Discoverability caveat: `aitna` reads as "Etna" only to those who know the myth — hence the etymology
  lives in the README naming section, not just here. Two Greek A-words (`aitna` / `akmon`) sit adjacent;
  they are conceptually nested (folder ⊃ engine), which is the mnemonic, but a beginner may briefly
  confuse them.
- Older ADRs and design docs keep the `keystone`/`_forge` names (grandfathered per V1); this ADR + the
  README naming section are the canonical vocabulary going forward.
- The reservoir means future entities are named by lookup, not invention — reducing future naming forks.
