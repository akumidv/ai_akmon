# Design: Codex runtime contract and package-mode hardening

> Implementation task: [C39](../TASKS.md). This design is pending owner verification in
> [D2-13](../D2_LEDGER.md).

## Frame

akmon `v0.3.0` states that delegation is the default and that always-on guardrails reach every
vendor through `AGENTS.md`. The alphavar package-mode pilot disproved two assumptions:

- Codex loads the literal `AGENTS.md` text but does not expand the nested `@.../_common.md`
  line into model-visible instructions, so the delegation rule never reaches the orchestrator;
- materialized hooks still discover a project through `<AITNA_ROOT>/akmon`, which does not
  exist in package mode, so SessionStart becomes silent from a nested working directory.

Good means that a fresh Codex session receives the operative delegation rule without an owner
prompt, materialized hooks work from any directory below the project root, and documentation
claims no enforcement or model-routing capability that has not been proven against the live
Codex harness.

## Decisions

### Direct operative anchor, verify-only ownership

The root `AGENTS.md` remains hand-reviewed. The akmon block must state the delegation-default
rule directly and link `_common.md` as its normative owner. `verify --strict` rejects a consumer
whose block only contains an `@` line. `BOOTSTRAP.md` supplies the exact concise clause.

This selects **verify-only** over:

- a marker-managed generated region, rejected because it weakens the existing hand-owned
  `AGENTS.md` invariant and makes `sync` mutate the project's primary instruction source;
- a separate generated include, rejected because the live failure is precisely that Codex does
  not expand the include into model-visible context.

The SessionStart hook repeats a capability-neutral reminder as defense in depth. It names task
kinds, not Claude-specific `k-*` files: a harness may provide generic subagents without named
agent definitions or child-model selection.

### Package runtime is self-contained

Project-root discovery accepts `AGENTS.md` plus either a mounted `<AITNA_ROOT>/akmon` tree or the
package integration record `<AITNA_ROOT>/.akmon.toml`. Runtime paths resolve to the mount in
mounted modes and `<AITNA_ROOT>/.akmon` in package mode.

Every dependency of a wired materialized hook must also be materialized. Package mode therefore
copies the stdlib-only model-routing and D2-ledger tool modules used by hooks and their emitted
commands. Hooks never import the consumer virtualenv.

### Capability-aware Codex support

The vendor-neutral policy remains mandatory; enforcement depth is vendor-specific. For Codex:

- `AGENTS.md` and SessionStart carry role, memory, and delegation policy;
- edit reminders remain wired;
- D5, delegation log/nudge, model binding, named subagents, and child-model selection are not
  marked supported until live payload and enforcement probes prove their exact contracts;
- generic subagent capability may satisfy delegation even when `k-*` names/model pins are not
  available.

The compatibility matrix distinguishes policy delivery, advisory hooks, hard enforcement,
subagent launch, and model selection instead of collapsing them into one checkmark.

### Release class

This changes an operative role/delegation contract and is therefore a breaking `v0.x` release:
development moves to `0.4.0.dev0`; the owner later cuts `v0.4.0`. The existing `v0.3.0` tag is
immutable. Commit, tag, push, publish, and consumer pin updates remain owner-run.

## Acceptance

- meta tests cover mounted and package root discovery, including nested cwd and custom
  `AITNA_ROOT`;
- a real stdin-to-JSON Codex SessionStart test contains the direct delegation instruction;
- verifier rejects an `AGENTS.md` block with only the guardrail import and accepts the explicit
  anchor;
- package sync materializes every runtime dependency and `sync --check` detects drift;
- self-CI includes an installed-wheel package-mode smoke from a nested cwd;
- README, BOOTSTRAP, hooks docs, capability matrix, task state, and changelog agree with code;
- tests, ruff, self-CI (including strict consumer-fixture verify), and build pass.

## Open Verification

The following require a live Codex protocol spike and stay explicitly unsupported until proven:

- exact PreToolUse names/payloads for shell, read/search, and subagent calls;
- whether subagent calls are observable by project hooks and expose parent/child identity;
- attended and non-interactive `ask`/`deny` behavior;
- user-visible hook output and child model selection.
