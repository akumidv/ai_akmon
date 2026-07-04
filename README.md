# akmon

The cross-project standard for **how an AI assistant helps develop, and helps use,** each
project — mounted into every project as a git submodule at `_aitna/akmon/`. It is
LLM-agnostic plain Markdown/JSON; the single entry point in a consuming project is its root
`AGENTS.md`.

## Name & metaphor — the forge under Aitna

*The name states the purpose.* In the myth, the **Kyklōpes** (Cyclopes — Brontes, Steropes, Arges)
work the **akmon** (anvil) in the aitna beneath **Aitna** (Mount Etna), hammering out the thunderbolts
of Zeus. This is that forge for software: the shared **anvil** every project is hammered into shape on,
worked by the assistant's smiths, inside each project's own forge-workspace. The vocabulary maps
one-to-one onto the system:

| myth (Greek) | in the system | name |
|--------------|---------------|------|
| **AItna** (Αἴτνη) — the volcano the forge sits under | each project's **dev-layer workspace** — the fire where the project is built; begins with **ai** | `_aitna/` |
| **akmon** (ἄκμων) — the AnvIl in the forge | this **shared standard/engine**, mounted inside the workspace | `akmon` / repo `ai_akmon`, at `_aitna/akmon/` |
| **Kyklōpes** (Κύκλωπες) — Zeus's smiths | the **subagents** — the `k-` prefix (`k-explorer`, `k-implementer`, …) | `k-*` (prefix kept) |

Containment is literal: the anvil sits **inside** the volcano-forge, exactly as `akmon/` sits inside
`_aitna/` — the same nesting as `_aitna/akmon/`. The `k-` prefix needs **no migration**: it
simply re-reads as *Kyklōpes*. The cluster is a reservoir for future entities —
**keraunos** (thunderbolt) a shipped deliverable, **Hephaistos** the orchestrator, **Brontes/Steropes/
Arges** smith tiers, **sphyra** (hammer) / **physa** (bellows) tools.

> **The smiths are used, not just named.** Delegation to the `k-*` smiths is **enforced**, not
> merely documented — because restating "delegate by task kind" in prose did not stop the
> orchestrator from doing everything itself. A PreToolUse forcing-function counts the
> orchestrator's own consecutive delegable calls (read/sweep, edit, shell) with no delegation and,
> past a threshold, nudges — then hard-asks — to hand the work to a smith. The smiths themselves are
> exempt (a `k-*` delegate has no delegation tool of its own). Mechanism + motivation:
> [model-routing §13](meta/design/model-routing.md).

> The names are **locked** ([ADR 0008](meta/decisions/0008-mythological-naming-aitna-akmon-kyklopes.md)),
> and the on-disk rename is tracked as one migration release ([V1](meta/TASKS.md)).

## What a consuming project follows (the USE surface)

- **[MODEL.md](MODEL.md)** — the operative model: layers (SHARED/LOCAL/USAGE), roles & agents,
  the DEVELOP triad (`review` → `architect` → `engineer`) + the routing discriminator,
  archetypes, guardrails/profiles, the learn loop, secrets, and the sync/verify tooling.
- **[BOOTSTRAP.md](BOOTSTRAP.md)** — attach akmon to a project, or realign one.
- **[ARCHETYPES.md](ARCHETYPES.md)** — archetypes + per-archetype USAGE/requirement checklists.
- **`roles/` · `pipelines/` · `guardrails/` · `profiles/`** — the role definitions, dev
  cycles, and rules an agent applies.

## akmon's own development

akmon's vision/constitution, decisions (ADRs), roadmap, backlog, design concepts, reviews,
and tests live under **[develop/](develop/)** — akmon's own DEVELOP layer. A consuming
project does **not** load it; the operative standard above is self-contained
([develop/CONCEPT.md](develop/CONCEPT.md) holds the full rationale). Separation locked in
develop ADR 0003.
