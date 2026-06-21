# Pipeline: memory-distill

The continuous cycle the [learn](../roles/learn.md) role follows. Steps **1–2** of the
[learn loop](../README.md#3a-the-learn-loop--how-the-keystone-evolves-through-use):
turn raw insights into shared memory, and recurring memory into reusable local assets.
This runs **continuously**, as work happens — not on a schedule (that is
[learning](learning.md)).

## When

- An agent hits an **insight**, **friction**, or a **repeated manual step** while working.
- A piece of provider-private memory is worth making team-visible.

## Steps

1. **CAPTURE** — write **one fact = one file** to `_forge/memory/`, indexed in
   `_forge/memory/MEMORY.md`. Concise, operational wording. This is shared project memory:
   in git, visible to all developers and agents.
   - Distinguish from **provider-private memory** (each assistant's own store). Private
     memory stays with the individual; distill *from* it into `_forge/memory/` — never
     treat the private store as the shared source of truth.
   - **Route by generality first.** Before filing a fact as project memory, classify it: a
     **project-specific** fact (this domain, this code, this runtime) is a first-class
     `_forge/memory/` entry. A **general methodology/process/role/convention** lesson is
     **not** project memory — check keystone (`guardrails/`, `roles/`, `pipelines/`): if it is
     already covered there, the lesson is to *follow* the existing rule (write nothing local);
     if it is missing, it is a **PROMOTE candidate** ([learning](learning.md) step 3), captured
     locally only as a brief staging note pointing at the gap. Filing a general rule as project
     memory both buries it and lets it drift from the standard.
2. **DISTILL** — when a fact recurs or proves load-bearing, turn it into something
   reusable:
   - a repeated procedure → a **LOCAL skill** (`_forge/skills/<name>/SKILL.md`),
   - a repeated mechanical operation → a **LOCAL tool** (`_forge/tools/<name>/`),
   - a way a role should work here → the project **agent charter** (`_forge/agents/`),
   - a refined requirement or decision → `docs/` via the [architect](../roles/architect.md)
     role (an ADR / requirement update).

## Boundary with promotion

memory-distill stays **LOCAL**. Lifting a local asset into keystone (cross-project) is
**PROMOTE**, step 3 — handled by [learning](learning.md). Do not promote here; a fact must
prove general *and* reused first.

## Done

The insight is one fact in `_forge/memory/` (indexed); recurring facts have become a
local skill / tool / agent-charter update / requirement. Nothing is left only in an
agent's head or in private memory.
