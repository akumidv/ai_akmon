# keystone

The cross-project standard for **how an AI assistant helps develop, and helps use,** each
project — mounted into every project as a git submodule at `_forge/keystone/`. It is
LLM-agnostic plain Markdown/JSON; the single entry point in a consuming project is its root
`AGENTS.md`.

## What a consuming project follows (the USE surface)

- **[MODEL.md](MODEL.md)** — the operative model: layers (SHARED/LOCAL/USAGE), roles & agents,
  the DEVELOP triad (`review` → `architect` → `engineer`) + the routing discriminator,
  archetypes, guardrails/profiles, the learn loop, secrets, and the sync/verify tooling.
- **[BOOTSTRAP.md](BOOTSTRAP.md)** — attach keystone to a project, or realign one.
- **[ARCHETYPES.md](ARCHETYPES.md)** — archetypes + per-archetype USAGE/requirement checklists.
- **`roles/` · `pipelines/` · `guardrails/` · `profiles/`** — the role definitions, dev
  cycles, and rules an agent applies.

## keystone's own development

keystone's vision/constitution, decisions (ADRs), roadmap, backlog, design concepts, reviews,
and tests live under **[develop/](develop/)** — keystone's own DEVELOP layer. A consuming
project does **not** load it; the operative standard above is self-contained
([develop/CONCEPT.md](develop/CONCEPT.md) holds the full rationale). Separation locked in
develop ADR 0003.
