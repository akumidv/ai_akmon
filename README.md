# akmon

> **The anvil for AI-assisted development** — an enforced, versioned, LLM-agnostic
> standard on top of `AGENTS.md`.

The cross-project standard for **how an AI assistant helps develop, and helps use, each
project**. It is mounted into every project as a git submodule at `_aitna/akmon/` (repo
[`ai_akmon`](https://github.com/akumidv/ai_akmon)) and is **LLM-agnostic**: plain
Markdown/JSON that any assistant (Claude, Codex,
Gemini, Copilot, …) or a human can read. No vendor's tooling is privileged; the single
entry point in a consuming project is its root `AGENTS.md`. The submodule is the default
mount mode; a tree-less **`package`** mode — akmon installed as a pinned dev dependency,
only hooks/guardrails materialized into the repo — is designed and pending implementation
([ADR 0009](meta/decisions/0009-packaging-package-carrier-and-mount-modes.md),
[BOOTSTRAP.md §F](BOOTSTRAP.md)).

**New consumer? Start at [BOOTSTRAP.md](BOOTSTRAP.md)** — it attaches akmon to a project.
Already attached? **[MODEL.md](MODEL.md)** is the operative rulebook.

## The simple idea

Attach one submodule — get a working discipline for AI-assisted development:

- **One entry point.** The root `AGENTS.md` is the single source of guidance; thin
  generated pointers (`CLAUDE.md`, `GEMINI.md`, …) keep every assistant reading it.
- **Rules that bite.** The invariants ship as hooks (commit guard, delegation nudge,
  session-start reminders) — not prose that decays out of context.
- **The right model for each step.** Cheap models fan out on mechanical work; the
  strongest model concentrates on the few checks where an error would cost the most.
- **A learn loop.** A lesson paid for once, in one project, becomes a rule every
  project inherits on its next update.

That is everything needed to begin — [BOOTSTRAP.md](BOOTSTRAP.md) walks the attach.
The sections down to **[Advanced — the full model](#advanced--the-full-model)** stay at
this altitude; the machinery behind them can wait until the basics run.

## Why it exists

AI assistance fails in predictable ways: rules restated in prose fall out of context and
decay; the same fact duplicated across documents drifts into contradiction; a session does
everything itself, on one model rung, regardless of what each step actually needs; and
every project reinvents its own conventions, so nothing learned in one carries to the next.

akmon is the counter-structure: **one versioned standard shared by all projects**, built
around a single goal function — *quality per unit of tokens + owner attention* — and a
small set of named invariants
([MODEL.md §11](MODEL.md#11-principles--the-shape-in-seven-lines)). In short: a rule that
must always hold ships with a forcing function (a hook), not just prose; a binding
contract lives as machine-checked data with exactly one owning artifact; the strongest
model concentrates at the few points where an error would cost the most; and assistants
only *draft* — the owner always *decides*. Everything in this repository is those
principles taking physical shape.

## Name & metaphor — the forge under Aitna

*The name states the purpose.* In the myth, the **Kyklōpes** (Cyclopes) work the **akmon**
(anvil) in the forge beneath **Aitna** (Mount Etna). This is that forge for software: the
shared **anvil** every project is hammered into shape on, worked by the assistant's smiths,
inside each project's own forge-workspace. The vocabulary maps one-to-one onto the system:

| myth (Greek) | in the system | name |
|--------------|---------------|------|
| **AItna** (Αἴτνη) — the volcano the forge sits under | each project's **dev-layer workspace** — the fire where the project is built; begins with **ai** | `_aitna/` |
| **akmon** (ἄκμων) — the AnvIl in the forge | this **shared standard/engine**, mounted inside the workspace | `akmon` / repo `ai_akmon`, at `_aitna/akmon/` |
| **Kyklōpes** (Κύκλωπες) — Zeus's smiths | the **subagents** — the `k-` prefix (`k-explorer`, `k-implementer`, …) | `k-*` (prefix kept) |

Containment is literal: the anvil sits **inside** the volcano-forge, exactly as `akmon/`
sits inside `_aitna/`; the `k-` prefix of the subagents reads as *Kyklōpes*.

> The names are **locked** ([ADR 0008](meta/decisions/0008-mythological-naming-aitna-akmon-kyklopes.md)),
> and the on-disk rename is tracked as one migration release ([V1](meta/TASKS.md)).

## Vendor support

akmon is LLM-agnostic by design, but *enforcement depth* differs per vendor harness — a
pointer file is universal, hooks are not. The honest current state; ❓ cells are
unverified and tracked as task **N1** in [meta/TASKS.md](meta/TASKS.md) (fill from
experiment against the real harness, not from vendor docs):

| Capability | Claude Code | Codex CLI | Gemini CLI | Copilot |
|---|---|---|---|---|
| `AGENTS.md` entry point via generated pointer (`sync.py`) | ✅ `CLAUDE.md` | ✅ native `AGENTS.md` | ✅ `GEMINI.md` | ❓ |
| Session-start context (agent roster, memory rule) | ✅ SessionStart hook | ⚠️ plain-text reminders only | ❓ | ❓ |
| Commit guard — hard `ask`/`deny` at the tool boundary | ✅ PreToolUse hook | ⚠️ needs a verified output contract | ❓ | ❓ |
| Delegation log + nudge (the smiths are *used*) | ✅ PreToolUse hook | ❓ | ❓ | ❓ |
| Model routing — `k-*` generation + local discovery | ✅ | ❓ | ❓ | ❓ |
| Second opinion (cross-vendor review) | ✅ asks Codex | ✅ asks Claude | ❓ | ❓ |

## What's in this repository

| Path | What it is |
|---|---|
| [MODEL.md](MODEL.md) | the operative model — axes, roles, tiers, principles; **the rulebook a consumer applies** |
| [BOOTSTRAP.md](BOOTSTRAP.md) | attach akmon to a project, or realign one |
| [ARCHETYPES.md](ARCHETYPES.md) | the archetype taxonomy + per-archetype USAGE/requirement checklists |
| [roles/](roles/) | the role definitions: `review` · `architect` · `engineer` + `learn` · `release` |
| [pipelines/](pipelines/) | how each role works: review-flow · design-flow · code-flow · pre-commit · release · tasks · the learn loop |
| [guardrails/](guardrails/) | always-on hard rules per language (`_common`, `python`, …) |
| [profiles/](profiles/) | opt-in domain rules (`quant`, …) |
| [skills/](skills/) | shared know-how any consuming project can use |
| [tools/](tools/) | executable mechanics: model routing (registry · init · gate-pack · coverage map · second opinion), tasks, release checks, the D2 ledger |
| [hooks/](hooks/) | the forcing functions — vendor-wired session/pre-tool guards (commit guard, analysis guard, delegation log + nudge, model routing) — [hooks/README.md](hooks/README.md) |
| [bin/](bin/) | `sync.py` — generates the thin vendor pointers · `verify.py` — validates the project contract (reports, never modifies) |
| [examples/](examples/) | worked, self-contained walkthroughs (start: [gate-anatomy.md](examples/gate-anatomy.md)) |
| [CHANGELOG.md](CHANGELOG.md) | the versioned change record — what a consumer's bump delta-checks against |
| [meta/](meta/) | akmon's **own** DEVELOP layer — a consumer never loads it |

## Life with a consuming project

Three movements, each defined once here and reused by every project:

1. **Attach** ([BOOTSTRAP.md](BOOTSTRAP.md)). Add the submodule; classify the project's
   archetype and language; resolve its guardrails and profiles; create the LOCAL layout
   (`_aitna/{agents,skills,tools,memory}` + `TASKS.md`); write the akmon block into the
   project's `AGENTS.md` and the machine-readable integration record `.akmon.toml`; wire
   the hooks into vendor config; run `sync.py` (generated pointers) and
   `verify.py --strict` (contract check). The agent prepares everything — **the owner
   commits**.
2. **Stay current.** A project pins an akmon version; a bump is a **delta-check** against
   [CHANGELOG.md](CHANGELOG.md) — only `Breaking`/`migration` lines in the version window
   need action — then a realign. `sync.py --check` + `verify.py --strict` run in the
   project's CI, so pointer and contract drift fail before merge, not months later.
3. **Give back — the learn loop.** CAPTURE a session fact into `_aitna/memory/` → DISTILL
   recurring facts into a LOCAL skill/tool/requirement → PROMOTE what is general *and*
   proven into akmon via PR → PROPAGATE to every project on the next submodule update.
   Flow is one-way **up** ([MODEL.md §6](MODEL.md#6-the-learn-loop-how-the-standard-evolves)).

This is the whole point of the SHARED layer: a lesson paid for once, in one project,
becomes a rule every project inherits on its next bump.

---

## Advanced — the full model

Everything below is the complete operating model behind
[the simple idea](#the-simple-idea). Attaching akmon does not require it; return here
once the basics run and you want to see the machinery — or to change it.

### The model in three axes

Every artifact and every action classifies on **three independent axes** —
[MODEL.md](MODEL.md) owns the definitions; this is the orientation:

- **Layer** — *whom an artifact serves*: **SHARED** (this submodule — every project),
  **LOCAL** (`_aitna/{agents,skills,tools,memory}` — this project's own developer),
  **USAGE** (root `skills/` — a downstream consumer of what the project exposes).
  SHARED+LOCAL point inward (building the repo); USAGE points outward.
- **Role** — *who performs the work*: the DEVELOP triad **review** (analysis — assess
  what *is*) → **architect** (synthesis — design what *should be*) → **engineer**
  (realization — code and tests), plus cross-cutting **learn** and **release**. Each role
  is a definition here ([roles/](roles/)) with its own pipeline
  ([pipelines/](pipelines/)); a project instantiates it as an *agent* in
  `_aitna/agents/`, inheriting the definition and adding only project specifics.
- **Archetype** — *what the project exposes outward* (`package` / `service` / `mcp` /
  `frontend` / …): chosen by the contract, not the language; decides whether a USAGE
  layer exists and its shape ([ARCHETYPES.md](ARCHETYPES.md)).

On top of the axes sit the always-on **[guardrails/](guardrails/)** (hard rules per
language, applied automatically) and opt-in **[profiles/](profiles/)** (domain rules such
as `quant`, attached only where the project has that concern).

### How a session runs — the model in one picture

One session = one **orchestrator** (the main assistant, on the session's own model) plus
the `k-*` smiths it delegates to. The orchestrator keeps only what cannot be delegated —
decompose, route, synthesize, owner dialogue — and hands every named **task kind** to the
smith bound to it:

```
owner ──► orchestrator (session model)
            │   decompose · route · synthesize · owner dialogue
            │
            ├─► k-explorer / k-mechanic / k-validator   worker     cheapest adequate rung
            ├─► k-implementer                           worker     mid rung
            ├─► k-reasoner                              reasoner   the orchestrator's rung
            │         …results return; the orchestrator synthesizes…
            ├─► k-auditor  ─ clean context, gate-pack ─ auditor    maximal rung, always
            └─► second opinion                          other vendor, opt-in
            │
owner ◄── synthesis + audit verdict + the items only the owner can verify
```

- **Routing is data.** The task-kind → tier matrix and the per-vendor selection policy live
  in [`tools/model_routing/registry.json`](tools/model_routing/registry.json) — the single
  owner; `init.py` binds tiers to locally available models and generates the `k-*` agent
  definitions. Operative rules: [MODEL.md §10](MODEL.md#10-capability-tiers--model-routing).
- **Quality concentrates where leverage is highest.** Cheap models fan out to sweep and
  edit; the maximal model runs at a few low-token points — plan checks and the **gate
  audit**, where a clean-context `k-auditor` judges a whole gate's collected material
  against a yardstick. Worked, real example: [examples/gate-anatomy.md](examples/gate-anatomy.md).
- **Hooks keep it true at runtime.** SessionStart shows the binding; a PreToolUse hook logs
  every delegation at zero token cost; the delegation nudge pushes a drifting orchestrator
  back to the smiths; the commit guard enforces owner-owned commits.

> **The smiths are used, not just named.** Delegation to the `k-*` smiths is **enforced**,
> not merely documented — because restating "delegate by task kind" in prose did not stop
> the orchestrator from doing everything itself. A PreToolUse forcing-function counts the
> orchestrator's own consecutive delegable calls (read/sweep, edit, shell) with no
> delegation and, past a threshold, nudges — then hard-asks — to hand the work to a smith.
> The smiths themselves are exempt (a `k-*` delegate has no delegation tool of its own).
> Mechanism + motivation: [model-routing §13](meta/design/model-routing.md).

## akmon's own development

akmon's vision/constitution, decisions (ADRs), roadmap, backlog, design concepts, reviews,
and tests live under **[meta/](meta/)** — akmon's own DEVELOP layer. A consuming project
does **not** load it; the operative standard above is self-contained
([meta/CONCEPT.md](meta/CONCEPT.md) holds the full rationale). Separation locked in meta
ADR 0003. **Working on akmon itself? Start there** — constitution first, then the ADRs and
[meta/TASKS.md](meta/TASKS.md).

The dev bench is a **plain clone of this repo**: akmon is self-hosted, so a session opened
in the clone develops the standard under the standard. To validate a change against a real
consumer before tagging, point the consumer at the working copy — work directly in its
mounted submodule (it *is* a checkout of `ai_akmon`), or, for a `package`-mode uv consumer,
override the pin with a local editable install: `[tool.uv.sources] akmon = { path =
"../ai_akmon", editable = true }` in its `pyproject.toml` (or ephemerally
`uv pip install -e ../ai_akmon`, which lasts until the next `uv sync`); `akmon sync` then
re-materializes hooks/guardrails from the working copy. When done: commit + tag here, drop
the override, return the consumer to the tag pin. (This workflow lives here on purpose —
BOOTSTRAP is consumer-only: developing *with* akmon, never akmon itself.)
