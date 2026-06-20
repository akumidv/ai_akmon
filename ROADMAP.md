# Roadmap — keystone

The forward-looking plan. The operating model itself is in [README.md](README.md); this
file records **what is deliberately not yet formulated** (so the gaps are explicit, not
lost) and the order in which to close them.

Each open item states: **the gap** (what is missing), **why it matters**, and a
**direction** (how it will likely be resolved). Directions are intent, not commitments.

---

## Done (formulated in the model)

- **Three axes** — Layer (SHARED/LOCAL/USAGE), Role (architect/engineer/…), Project type
  (package/service/…). Layer as a decision tree, not a grid (no false "shared usage").
- **Role vs agent** — role = definition (in keystone); agent = incarnation (in a
  project). Axis values are roles; an agent is a point where axes meet.
- **Learn loop** (README §3a) — CAPTURE → DISTILL → PROMOTE → PROPAGATE; two memories
  (shared `_forge/memory/` vs provider-private) kept distinct; promotion test
  (general + proven).
- **Two roles** — architect, engineer (with role files + project-agent charters).
- **Distribution intent** — submodule now, MCP hybrid later (see below).

---

## Open — gaps in the model (not yet formulated)

### O1. OPERATE mode (runtime actors)

- **Gap.** The decision tree spans DEVELOP and USE only. A third mode — an agent that
  *acts in the world at runtime* (places orders, moves data/money) — has no place in the
  model. It is noted as a scope boundary in README §2 but not designed.
- **Why it matters.** Its risk is categorically different (irreversible, real-money
  consequences), so it needs its own **hard runtime guardrails**, separation of
  duties (propose ≠ execute), and an orchestrator — none of which D#/USAGE rules cover.
  Folding it into USAGE (as the old `desk/` did) is a category error.
- **Direction.** When formulated, OPERATE becomes a **third branch of the tree**, not a
  layer under DEVELOP — with its own guardrail tier (call it G#) and an orchestrator that
  enforces propose/execute separation. Until then it lives in a *separate* domain/repo,
  referenced from keystone, not inside it.

### O2. Versioning & compatibility of the standard

- **Gap.** keystone is one submodule consumed by N projects. There is no notion of a
  keystone **version**, a **changelog**, or a **breaking-change signal**. A project that
  bumps the pin can silently inherit a changed role or guardrail.
- **Why it matters.** A standard that retunes itself (the learn loop) must let consumers
  know *what changed and whether it breaks them* — otherwise promotion is unsafe at scale.
- **Direction.** A `CHANGELOG.md` + semver-ish tags on keystone; compatibility labels on
  shared skills/roles; the bootstrap/`sync` step surfaces "what changed since your pin".

### O3. Cross-agent contract (Claude / Codex / Gemini)

- **Gap.** README §7 declares "source of truth = markdown + code; vendors get generated
  pointers via `sync.py`" — but the contract is not specified: which files
  (`.claude/skills/`, `.codex/`, `GEMINI.md`), what is committed vs generated, how
  `AGENTS.md` ↔ `CLAUDE.md` ↔ roles/skills relate.
- **Why it matters.** "LLM-agnostic" is the project's headline claim; right now it is a
  declaration with no mechanism. `sync.py` does not exist yet.
- **Direction.** Specify the pointer layout + commit policy; implement `bin/sync.py`
  (stdlib only) to write Claude pointers and the AGENTS.md skill block from one source;
  document re-run triggers (after submodule update / new local skill).

### O4. Orchestration & separation of duties

- **Gap.** The architect → engineer hand-off is described, but *who routes work* across
  roles, and how propose/execute separation is enforced, is undefined. Matters more as
  roles/agents multiply and once OPERATE (O1) exists.
- **Why it matters.** Without an orchestrator, role boundaries are advisory; an agent can
  quietly cross from proposing into executing.
- **Direction.** A lightweight orchestrator role/skill that selects the role for a task,
  enforces the hand-off, and (for OPERATE) guarantees propose ≠ execute.

### O5. Skill contract

- **Gap.** "skill = SKILL.md" is stated, but there is no schema. Skills will not be
  comparable across projects (no agreed purpose / inputs / outputs / constraints /
  safety / eval / owner fields).
- **Why it matters.** Comparable, evaluable skills are the prerequisite for eval gates and
  for promoting skills between projects with confidence.
- **Direction.** A minimal `SKILL.md` frontmatter schema + a validator (a keystone tool);
  later, eval gates in CI before a shared-layer change merges.

---

## Distribution — submodule → MCP → product

keystone is built to survive a change of carrier (README §9):

- **Now.** Git submodule — deterministic pinning, PR governance, works offline, no infra.
- **Next (hybrid).** Governance/docs stay in the submodule; executable `tools/` and
  validators move behind an **MCP server** the assistant mounts. Same contract, new
  carrier. Revisit when executable tooling (sync, validators, fixtures) becomes the
  bottleneck rather than the docs.
- **Later (product).** A standalone offering — the name `keystone` stands on its own. Only
  worth it at cross-project volume that justifies the infra.

---

## Build vs buy (optional accelerators, not prerequisites)

Keep core governance in-repo (submodule + markdown). Integrate external products
selectively, observability/eval first — never as a dependency the model needs to function.

- Observability / eval: Promptfoo, Braintrust, Arize Phoenix, LangSmith.
- Safety guardrails: content-safety / prompt-firewall services.
- Gateway / policy: an LLM gateway for routing + policy + cost.

---

## Suggested order to close the gaps

1. **O1 direction note + this ROADMAP** — make every gap explicit (cheap, prevents loss).
2. **Pipelines + guardrails + profiles** — make the roles and the learn loop runnable.
3. **ARCHETYPES + BOOTSTRAP** — make keystone deployable to a new project.
4. **O3 `sync.py`** — make the cross-agent claim real.
5. **O2 versioning, O5 skill contract, O4 orchestration** — harden for scale.
6. **O1 OPERATE** — formulate the runtime branch when a runtime actor is actually needed.
