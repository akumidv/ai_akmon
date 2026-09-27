# AGENTS.md

## Dev layer — akmon

The standard ships in the installed `akmon` package: `akmon path` prints its root.
Archetype: `ARCHETYPES.md`. Read `_aitna/memory` at session start.

The owner verifies consequential decisions recorded in ADRs. D5 is always-on. Secrets come from `.env`.
Skills live in root `skills/`; generated vendor skill stubs are pointers only.

**Delegation is the default.** For every non-trivial task, delegate independent mechanical
substeps without waiting for an owner prompt; the orchestrator keeps decomposition, routing,
synthesis, and owner dialogue.

@_aitna/.akmon/guardrails/_common.md
