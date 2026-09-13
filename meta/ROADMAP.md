# Roadmap — akmon

The forward-looking plan. [MODEL.md](../MODEL.md) owns the mission and operating model;
[CONCEPT.md](CONCEPT.md) explains the background. This file records development
priorities and **what is deliberately not yet formulated**; [TASKS.md](TASKS.md) owns
current execution state and dependencies.

Each open item states: **the gap** (what is missing), **why it matters**, and a
**direction** (how it will likely be resolved). Directions are intent, not commitments.

## Product priorities

1. **Human attention and joint decision quality.** Improve the whole collaboration:
   goals and future-use knowledge, plans, truthful proportional reporting, useful
   disagreement, and resumption without repeated context reconstruction. D2 is a pilot
   case, not the boundary. Start with the [research and AP0–AP5 plan](design/attention-and-human-agent-collaboration.md#refinement-and-implementation-plan)
   and its design/implementation tasks A22/C86.
2. **Token efficiency for quality.** Develop the existing roles, subagent delegation,
   model selection, skills, and hook controls against the cost of errors and rework.
   Check achieved quality and actual routing/delivery evidence, not agent counts or
   nominal model settings. Reuse [model-routing](design/model-routing.md); do not create
   a competing routing policy under the attention initiative.

These are connected priorities under the [mission](../MODEL.md#mission-and-priorities),
not two unrelated products. Track quality, human effort, and token cost separately;
neither fast approval nor low token use establishes effectiveness. Audit the premises
of a decision separately from checking that its implementation conforms to it.

Evaluate resource allocation over the relevant lifecycle: design, implementation,
verification, use, and rework. A larger up-front investment in design or model reasoning
can be efficient; retain it for its expected and then observed contribution, not because
the individual step was cheap or the chosen model was the strongest.

Reliable delivery, compatibility, and the learn loop support both priorities. A new
carrier, feature, role, or automation earns scope through demonstrated need; it does
not outrank outcome quality merely because it is implementable. Existing safety,
correctness, and explicitly locked task dependencies remain in force.

---

## Done (formulated in the model)

- **Three axes** — Layer (SHARED/LOCAL/USAGE), Role (architect/engineer/…), Archetype
  (package/service/…). Layer as a decision tree, not a grid (no false "shared usage").
- **Role vs agent** — role = definition (in akmon); agent = incarnation (in a
  project). Axis values are roles; an agent is a point where axes meet.
- **Learn loop** ([MODEL §6](../MODEL.md#6-the-learn-loop-how-the-standard-evolves)) — CAPTURE → DISTILL → PROMOTE → PROPAGATE; two memories
  (shared `_aitna/memory/` vs provider-private) kept distinct; promotion test
  (general + proven).
- **Develop roles** — review, architect, engineer, with cross-cutting learn and release;
  role and model tier remain separate ([MODEL §3](../MODEL.md#3-role-vs-agent--the-develop-triad)).
- **Distribution** — supported carriers are described in the [README](../README.md);
  possible further carriers remain subordinate to the product priorities.

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
  referenced from akmon, not inside it.

### O2. Release, versioning & compatibility of the standard — RESOLVED

- **Gap.** akmon is one submodule consumed by N projects. There is no notion of a
  akmon **release**, **version**, **changelog**, or **breaking-change signal**. A project
  that bumps the pin can silently inherit a changed role or guardrail.
- **Why it matters.** A standard that retunes itself (the learn loop) must let consumers
  know *what changed and whether it breaks them* — otherwise promotion is unsafe at scale.
- **Resolution.** Locked in [ADR 0001](decisions/0001-release-and-roles-model.md): a
  subject-parameterized `release` DEVELOP role + two-mode pipeline, `learn` extracted as a
  sibling role, `v0.x.y` versioning, one-job-per-artifact (archive vs release notes vs tag vs
  downstream bump record), and a `CHANGELOG.md` with an `Unreleased` section. Implementation is
  phased via backlog T10–T15 (design: [release-versioning.md](design/release-versioning.md)).

### O3. Cross-agent contract (Claude / Codex / Gemini) — PARTIALLY DONE

- **Status.** The base contract is closed (T1): `verify.py` checks vendor pointers/imports
  and source skill-root linkage, AGENTS.md stays hand-reviewed. **Remaining (v2):** how
  `AGENTS.md` ↔ skills/roles relate *beyond thin pointers* — e.g. a generated AGENTS skill
  block from one source without clobbering project text. Framed as a parked design skeleton
  ([design/cross-agent-contract-v2.md](design/cross-agent-contract-v2.md), backlog T16).
- **Gap.** README §7 declares "source of truth = markdown + code; vendors get generated
  pointers via `sync.py`" — an initial stdlib-only `bin/sync.py` now writes the basic
  pointer set and Claude hook wiring; `bin/verify.py` validates the project contract;
  BOOTSTRAP specifies which generated pointers are committed; and CI/preflight guidance
  runs both tools. The remaining contract gap is how `AGENTS.md` ↔ `CLAUDE.md` ↔
  roles/skills relate beyond the current thin pointers.
- **Why it matters.** "LLM-agnostic" is the project's headline claim; right now it has
  a minimal mechanism, but skills and role pointers can still drift from `AGENTS.md` unless
  the source-to-pointer relationship is fully specified.
- **Direction.** Extend `bin/sync.py` to write the AGENTS.md skill block from one source
  if that can be done without overwriting project-specific text; document re-run triggers
  after submodule updates and new local skills.

### O4. Orchestration & separation of duties

- **Status.** DEVELOP routing is defined in [MODEL §10](../MODEL.md#10-capability-tiers--model-routing):
  the session orchestrator owns decomposition, routing, integration, and owner dialogue;
  the task-kind matrix routes bounded work to model tiers. This is distinct from adding
  another DEVELOP role. The current roles are owned by MODEL §3.
- **Gap.** OPERATE's hard runtime propose/execute separation remains undesigned (O1).
  For DEVELOP, any claimed enforcement must be checked against the actual harness
  capability, not inferred from the existence of a routing policy.
- **Why it matters.** Explicit routing helps allocate work, but neither routing nor a
  second agent by itself proves an authority boundary is enforced.
- **Direction.** Evaluate friction and delivered controls through the existing routing
  work. A separate orchestrator role/skill is not a prerequisite for the mission;
  revisit it only for a demonstrated gap, and design OPERATE separately if brought into scope.

### O5. Skill contract — PARTIALLY DONE

- **Status.** The minimal contract is closed (T2, reshaped by C79 to the Agent Skills format):
  required `name` / `description` / `metadata.owner` frontmatter within the standard's limits,
  checked by `verify.py`. **Remaining:** a richer schema
  (inputs / outputs / constraints / safety / eval) and **eval gates** in CI before a
  shared-layer change merges.
- **Gap.** "skill = SKILL.md" is stated, but there is no schema. Skills will not be
  comparable across projects (no agreed purpose / inputs / outputs / constraints /
  safety / eval / owner fields).
- **Why it matters.** Comparable, evaluable skills are the prerequisite for eval gates and
  for promoting skills between projects with confidence.
- **Direction.** A minimal `SKILL.md` frontmatter schema + a validator (a akmon tool);
  later, eval gates in CI before a shared-layer change merges.

---

## Distribution — current carriers and conditional directions

akmon is built to survive a change of carrier; carrier expansion serves the mission:

- **Current.** The [README](../README.md) owns supported mount modes and installation
  status; the [packaging design](design/packaging/README.md) owns their rationale.
  Do not treat the package carrier as merely a future design or confuse an implemented
  CLI with public package publication.
- **Possible hybrid.** Governance/docs retain their versioned source while executable
  tools and validators could be exposed through an MCP server. Revisit only when a
  demonstrated tooling bottleneck justifies another delivery and maintenance surface.
- **Possible standalone offering.** Consider it at cross-project volume that justifies
  the infrastructure. It is not a required stage on the path to better collaboration.

---

## Build vs buy (optional accelerators, not prerequisites)

Keep core governance in-repo (submodule + markdown). Integrate external products
selectively, observability/eval first — never as a dependency the model needs to function.

- Observability / eval: Promptfoo, Braintrust, Arize Phoenix, LangSmith.
- Safety guardrails: content-safety / prompt-firewall services.
- Gateway / policy: an LLM gateway for routing + policy + cost.

---

## Suggested order to close the gaps

1. **Make the mission testable.** Refine the interaction cases and premises, then verify
   a small first slice before adding a universal skill or new infrastructure (A22/C86).
2. **Improve quality per agent-work cost in parallel.** Continue the existing routing,
   delegation, skills, and measured enforcement work against real failure modes; use
   TASKS for its current ordering and dependencies.
3. **Validate and propagate useful mechanisms.** Evaluate behavior, owner understanding,
   limitations, and maintenance cost as well as code correctness; release and realign
   consumers only through the existing owner-controlled process.
4. **Expand only for demonstrated need.** Richer skill/eval infrastructure, further carrier
   changes, and OPERATE remain conditional directions, not prerequisites for the mission.
