# 0004 — Model routing: capability tiers, task-kind matrix, ladder binding

- **Status:** Accepted (owner-scoped; implementation phased).
- **Owner:** akuminov@gmail.com
- **References:** [MODEL.md](../../MODEL.md) (the operation axis the tiers bind to) ·
  [guardrails/_common.md](../../guardrails/_common.md) (gains the floor rule) ·
  [pipelines/{review,code,design}-flow](../../pipelines/) (gain step tier annotations) ·
  [hooks/](../../hooks/) (`session-start-agent.py` wiring contract, `claude_adapter` /
  `codex_adapter`) · design concept in [`meta/design/model-routing.md`](../design/model-routing.md)
  (options, rejected branches, examples) · keystone backlog task [C10](../TASKS.md).

## Context

A session runs on one model that does everything — decomposition, deep reasoning, and
mechanical edits alike. That burns the strongest model on boilerplate and re-consumes the
orchestrator's context on work a cheap delegate could isolate. Harnesses expose multiple
models and subagents, but keystone had no standard for *which work goes to which model*:
routing was per-session judgment, model names threatened to leak into process docs, and
model releases would rot any hardcoded mapping. The owner's requirements: the running
session orchestrates; bindings come from recorded knowledge, computed automatically
relative to the orchestrating model; delegation is by kind of work; initialization and
observability are code, not prose; cross-vendor review is offered opt-in.

## Decision

1. **Vocabulary — four capability tiers** (vendor-neutral): `orchestrator` (the main
   session: decompose, route, synthesize, owner dialogue — never delegated), `reasoner`
   (load-bearing synthesis: design forks, deep debugging, quant derivation), `worker`
   (delegable realization: exploration, summaries, mechanical edits, tests-under-spec),
   `second-opinion` (independent cross-vendor review, opt-in).
2. **The binding surface is a task-kind matrix, kept as data.** A finite named list of
   operations (`explore-search`, `summarize`, `mech-edit`, `test-scaffold`, `doc-sync`,
   `validate-loop`, `implement-under-spec`, `debug-deep`, `design-fork`,
   `quant-derivation`, `independent-review`), each mapped to a tier in the registry. **Delegation is the
   default** — every matrix row has a named delegate; the orchestrator keeps only its own
   row. Escalation is a ladder policy: start at the cheapest adequate rung, move up only
   on failure signals (tests red twice, delegate flags uncertainty, contested fork).
3. **Model selection is semantic policy plus local discovery, not committed model names.**
   The registry records how to choose from a vendor's locally discovered weakest→strongest
   list (worker = lowest, reasoner = highest, orchestrator floor = highest). Concrete
   aliases live in gitignored local config or generated harness files, never as current
   truth in the shared registry. The tier→model binding is a **pure function of
   (semantic policy, local available list, orchestrator model)**: reasoner = top available
   rung (a same-model subagent when the orchestrator already is the top — context
   isolation persists); worker = lowest available rung; `mid` rung serves
   `implement-under-spec`.
4. **The orchestrator is whatever the user launched, and is always displayed.** The
   session-start status line names it; if it ranks below the local highest rung, the hook
   adds a warning and suggests switching up. Advice only —
   the user's choice stands.
5. **Mechanism is three code components** in keystone: `tools/model_routing/`
   (`registry.json` + idempotent init tool that computes the binding and generates the
   per-vendor subagent definitions and a gitignored local config), a **SessionStart
   hook** (fresh config → one status line; missing/stale → init instruction + two owner
   questions: confirm binding, enable second-opinion), and a **PreToolUse delegation-log
   hook** on the subagent tool (one log line per delegation — model switches are visible
   at zero token cost; the model never narrates routing). Wired per vendor by `sync.py`
   through the existing adapter contract. Generated subagent files are committed; the
   local config is not.
6. **Pipelines anchor the routing:** review/code/design-flow steps carry one-line tier
   annotations (evidence fan-out → worker; verify/align gates → reasoner +
   second-opinion advisory), so delegation triggers because a step arrived, not because
   the orchestrator remembered.
7. **Second-opinion never replaces owner verification** — it is advisory input at the
   existing verify gates, called via the registry-recorded invocation (the vendor CLI in
   non-interactive mode, e.g. `codex exec`; a plugin command is registry data if adopted
   later). Its output **always surfaces in chat** — full report to a file, a digest
   (verdict + disagreements) to the owner — unlike routing switches, which are a silent
   log. Tiers change who *drafts*, never who *decides*.

Locked points: worker floor = cheapest locally discovered adequate rung; ask-on-stale only (status line
otherwise); generated agents grouped by brief and **namespaced `k-`** (`k-explorer`,
`k-mechanic`, `k-validator`, `k-implementer`, `k-reasoner`) — lowercase-kebab,
keystone-managed, collision-free against harness built-ins; second-opinion opt-in per
project with per-session override.

## Consequences

- `MODEL.md` gains a capability-tier section; each triad role file gets a default-tier
  line; `guardrails/_common.md` gains the floor rule (*do not burn the orchestrator or
  reasoner tier on mechanical work; route by task kind, not by the whole task's
  prestige*); the three flow pipelines gain step annotations.
- Model releases cost at most one registry line (aliases absorb point releases); process
  docs never change for a model change.
- Phasing: (1) bootstrap — hand-written grouped subagents in the first consumer validate
  the matrix rows; (2) registry + tool + hooks built here and wired by `sync.py`;
  (3) consumers bump the pin and run init (generated agents supersede hand-written ones).
- Rejected branches (polar two-tier routing, per-model binding tables, complexity
  scoring, prose-only skill, chat-narrated switches) stay on record in the design
  concept with revisit-if conditions.
