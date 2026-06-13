# ai_governance

Universal baseline for AI-assisted development workflows across projects.

This repository is designed to be connected as a submodule.

Task file location in parent project:
- `_dev/TASKS.md` in the parent project (created during deployment; not stored in this repository)

Primary use:
- assist implementation and maintenance workflows,
- keep repeatable mechanics deterministic,
- separate orchestration (skills) from executable helpers (tools),
- keep a single actionable backlog and compact decision memory,
- define a shared operating model for agents and contributor workflows.

## Repository structure

```text
BOOTSTRAP_PIPELINE.md
memory/
skills/
tools/
README.md
```

## Parent project structure (created during deployment)

```text
AGENTS.md
agents/
skills/
tools/
memory/
_dev/
  TASKS.md
  skills/
  tools/
  memory/
  ai_governance/   # this repository as submodule and requirements source
```

## Components

- `BOOTSTRAP_PIPELINE.md`:
  - bootstrap pipeline for initial rollout,
  - run once when integrating this setup.
- `skills/`:
  - universal inter-project playbooks for recurring tasks,
  - each skill should include goal, preconditions, steps, and verification checklist,
  - orchestration and judgement live here.
- `tools/`:
  - universal deterministic helper code for repeated operations,
  - keep utilities small, focused, and reusable,
  - document run commands close to code.
- `memory/`:
  - universal memory for cross-project requirements and patterns,
  - collect raw insights that may later become shared skills or tools,
  - store agent operating approaches, constraints, and inter-project standards for transfer into parent-project root AGENTS.md,
  - one file per stable fact,
  - concise, operational wording.

## Two-axis model

- Axis 1 (scope):
  - This repository (`skills/`, `tools/`, `memory/`) stores universal cross-project assets.
  - Parent project stores project-specific assets.
- Axis 2 (layer in parent project):
  - Layer 1: Governance layer (`AGENTS.md` in root + `_dev/TASKS.md`) for project rules, ownership, planning, and explicit separation of two branches: runtime usage (Layer 3) and development workflow (Layer 2).
  - Layer 2: Development layer (`_dev/skills`, `_dev/tools`, `_dev/memory`) for project development workflow, experiments, and build tasks.
  - Layer 3: Usage/operate layer in root (`skills/`, `tools/`, `memory/`, `agents/`) for project usage in runtime/delivery contexts (for example, libraries and integration usage), not for development.
- Requirements for Layer 2 (development) are sourced from `_dev/ai_governance`.
- Layer 3 (operate) is project-owned and adapted to local delivery/runtime needs.
- Project-specific assets from either layer can be promoted into this repository when they become reusable across projects.

## Working rules

1. Keep process docs short and actionable.
2. Put repeatable mechanics into `tools/`, not ad-hoc scripts.
3. Keep task orchestration in `skills/`, not in tool code.
4. Keep one ongoing backlog in parent project `_dev/TASKS.md`.
5. Keep project-local decisions split by layer: root `memory/` for operate context and `_dev/memory/` for development context.

## Next steps

- Add project-specific skills in `skills/`.
- Add at least one deterministic helper in `tools/`.
- Add minimal lint/test checklist and CI hooks.

## Deployment prompt

Use this prompt for first deployment in a parent project:

```text
Deploy ai_governance as a git submodule at _dev/ai_governance.
After adding the submodule, execute the rollout instructions from this module:
- README.md
- BOOTSTRAP_PIPELINE.md

Create and update parent-project files in project root:
- AGENTS.md
- agents/

If these files/folders already exist, keep them and update only where needed.

Create and update parent-project operate layer in root:
- skills/
- tools/
- memory/

If these folders already exist, do not recreate or reset them; apply only required changes.

Create and update parent-project development layer under _dev/:
- TASKS.md
- skills/
- tools/
- memory/

If these files/folders already exist, update incrementally based on current project state.

Use _dev/ai_governance as the requirements source for the _dev development layer.
Keep root operate-layer files project-owned and tailored to project runtime/delivery needs.

Treat instructions in ai_governance as the source for initial setup.
```
