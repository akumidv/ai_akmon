# Review — Ponytail ideas for evolving akmon (2026-07-18)

> **Point-in-time review** (archived findings produced in the `review` role). It covers
> the current uncommitted akmon working tree and the local Ponytail 4.8.4 clone under
> `.review/ponytail/` as of 2026-07-15. Facts in this document will become stale; if
> the owner accepts any recommendations, design/ADR artifacts and `meta/TASKS.md`
> entries become their living carriers. This English translation was added at the
> owner's request; the original Russian report remains preserved separately.

**Owner request.** Identify ideas and approaches from similar projects, starting with
[Ponytail](../../.review/ponytail/README.md), that could strengthen akmon; distinguish
transferable mechanisms from attractive but incompatible solutions.

**Scope.** Ponytail's process and runtime mechanisms compared with akmon's operating model,
roles, pipelines, hooks, routing, verification, learning, and distribution.

**Evaluation criteria.** An idea is useful for akmon if it:

1. closes a confirmed gap rather than duplicating an existing owner artifact;
2. can become a verifiable contract rather than merely additional prose;
3. preserves the `review → architect → engineer` separation and owner-owned decisions;
4. has a regression/evaluation path;
5. does not weaken correctness, safety, D2/D5, or explicit-scope gates;
6. justifies its maintenance cost across multiple vendor/carrier/OS surfaces.

**Method.** Two areas were inspected independently: (P) Ponytail's structure, skills,
hooks, adapters, tests, and benchmark methodology; and (A) akmon's current contracts,
backlog, and test coverage. The results were then compared and ranked. No source code,
backlog, or design artifacts were changed during the review.

---

## 1. Executive summary

Ponytail does not offer a stronger overall orchestration model: akmon goes deeper in role
separation, owner boundaries, data-driven model routing, gate-pack/auditor behavior,
learning, and release governance. Ponytail's main value lies elsewhere:

1. **the standard's behavior is treated as an experimentally verifiable product;**
2. **solution minimality is expressed as an explicit decision ladder and a dedicated
   review lens;**
3. **host/OS compatibility is tested through concrete regression cases;**
4. **deliberate shortcuts receive a ceiling and a revisit trigger;**
5. **failed or negative benchmark results are retained as knowledge, while claims are
   narrowed to the range actually demonstrated.**

These contracts should be considered for adoption, but not Ponytail's persona model,
global intensity modes, `shortest diff wins` as an absolute criterion, duplicated rule
copies, or weak minimum testing standard.

---

## 2. Comparison map

### 2.1 What is already stronger or more complete in akmon

- Three independent Layer / Role / Archetype axes and explicit separation of DEVELOP
  operations ([MODEL.md](../../MODEL.md#1-three-orthogonal-axes-do-not-conflate)).
- Separate gated pipelines for analysis, design, and implementation:
  [review-flow](../../pipelines/review-flow.md),
  [design-flow](../../pipelines/design-flow.md), and
  [code-flow](../../pipelines/code-flow.md).
- Data-driven task-kind/model routing, inexpensive worker fan-outs, a clean-context
  auditor, and cross-vendor second opinions
  ([MODEL.md](../../MODEL.md#10-capability-tiers--model-routing)).
- Explicit owner boundaries: the agent prepares; the owner decides and performs commits,
  tags, pushes, publishing, and pin bumps.
- The `CAPTURE → DISTILL → PROMOTE → PROPAGATE` learning loop and subject-scoped release
  model.
- Generated thin pointers and read-only `verify`, rather than manual duplication of the
  complete rules text across vendor files.
- Package/mount carrier model, synthetic consumer self-CI, and hook policy tests.

### 2.2 Distinctive Ponytail mechanisms

- One compact solution ladder: YAGNI → project reuse → standard library → native platform
  → installed dependency → minimal new code
  ([AGENTS.md](../../.review/ponytail/AGENTS.md)).
- Persistent `lite/full/ultra/off` modes, runtime mode tracking, and a status line.
- Specialized skills for implementation discipline, diff review, repository auditing,
  shortcut debt, benchmark gains, and help
  ([README](../../.review/ponytail/README.md#commands)).
- Many host adapters, with instruction-only and plugin/hook surfaces separated
  ([agent portability](../../.review/ponytail/docs/agent-portability.md)).
- Explicit policy injection into subagents.
- Correctness, behavior, robustness, and agentic A/B benchmarks with retained reports.
- Release/version drift tests and Windows/shell regression tests.

---

## 3. Findings and recommendations

### F1 — The standard lacks behavioral A/B evaluations (high priority)

**Observation.** Ponytail tests whether a skill changes the behavior of a real coding
agent, not merely whether the skill text exists. Its agentic benchmark uses the same
harness and model for both arms, a real pinned codebase, a separate clean context for
every cell, multiple repetitions, `git diff` as the observable result, and executable
adversarial safety checks
([benchmark method](../../.review/ponytail/benchmarks/results/2026-06-18-agentic.md#what-changed)).

The recorded contamination failure is especially important: the global SessionStart
plugin accidentally reached the baseline, invalidating the initial result. The fix
isolated settings sources and loaded exactly one plugin arm
([contamination bug](../../.review/ponytail/benchmarks/results/2026-06-18-agentic.md#a-contamination-bug-we-found-in-our-own-numbers)).

**akmon gap.** O5 calls for a richer skill schema and evaluation gates, but no executable
contract exists yet ([ROADMAP](../ROADMAP.md#o5-skill-contract--partially-done)). Current
unit and self-CI checks verify wiring and deterministic mechanics, but not whether the
standard changes real agent behavior in the intended direction.

**What to adopt.** Adopt the general methodology, not Ponytail's specific metrics:

- baseline and akmon arms on the same harness/model/version;
- complete isolation of global/user plugins, memory, and configuration;
- a pinned fixture repository and reproducible task corpus;
- a deterministic scorer wherever the result is executable;
- multiple repetitions, retaining every workspace for offline rescoring;
- separate correctness, safety, boundary-adherence, and economics axes;
- publication of negative results and model ceilings rather than discarding them.

Akmon's primary metrics should include active-role and analysis-before-mutation compliance;
the D5/owner boundary; delegation and role-to-task-kind routing; appropriate gate-audit
activation or omission; result correctness and safety; and owner attention, tool calls,
tokens, and wall-clock time. LOC is only a secondary diagnostic: it does not measure
architecture quality, correctness, or maintenance cost.

**Decision criterion.** The evaluation contract reproduces a baseline-versus-akmon delta,
prevents cross-arm contamination, includes an executable scorer, and explicitly records
the supported model/harness range.

**Route:** `architect` to develop O5; after lock, `engineer` for the harness and tests.

### F2 — code-flow has no explicit solution ladder (high priority)

**Observation.** Ponytail requires stopping at the first sufficient level:

1. does anything need to be built at all;
2. does the project already contain the solution;
3. can the standard library solve it;
4. can the native platform solve it;
5. is an already installed dependency suitable;
6. is a minimal local expression sufficient;
7. only then, add the minimum new code.

The ladder is applied **after** reading the affected code and tracing the actual flow.
Bug fixes must find callers and address the shared root cause, not merely the nearest
named symptom ([Ponytail contract](../../.review/ponytail/AGENTS.md)).

**Current akmon state.** `code-flow` requires reuse of existing abstractions and
standard-library-only development tooling, while common guardrails prohibit unrelated
work ([code-flow](../../pipelines/code-flow.md),
[scope discipline](../../guardrails/_common.md#scope-discipline)). These constraints do
not form an ordered decision procedure.

**What to adopt.** Add a short solution ladder to engineer/code-flow, subordinate to the
accepted task and locked design. The root-cause clause should require checking affected
paths/callers and fixing the most general confirmed source, rather than literally
requiring “always grep every caller.”

**Constraints.** The ladder must never override an explicit requirement, security,
accessibility, trust-boundary validation, data-loss handling, project convention, or
complete tests.

**Decision criterion.** Before creating a new abstraction or dependency, the engineer
explicitly checks the preceding rungs; a bug fix includes evidence that it addresses the
shared source or is a justified local case.

**Route:** `architect` for the pipeline contract; then `engineer` for verifier/eval
work if a machine-checkable mechanism is selected.

### F3 — review needs a specialized simplicity lens (high priority)

**Observation.** Ponytail separates correctness/security review from over-engineering
review. The latter uses a narrow vocabulary:

- `delete` — dead or speculative functionality;
- `stdlib` — a hand-rolled standard capability;
- `native` — a dependency or custom code used instead of a platform capability;
- `yagni` — abstraction, configuration, or flexibility without a second real use case;
- `shrink` — the same logic with a smaller surface.

Each finding gives the location, what to remove, and what should replace it; the skill is
read-only and explicitly does not substitute for correctness/security review
([ponytail-review](../../.review/ponytail/skills/ponytail-review/SKILL.md#format)).

**What to adopt.** Add a named simplicity/over-engineering lens invoked through the
existing `review` role. A separate role is unnecessary: akmon already defines review as
analysis through a selected yardstick. `net lines/dependencies removable` may be
supplementary evidence, but not severity. Severity should reflect boundary count,
operational risk, and maintenance burden under akmon's rules.

**Decision criterion.** The lens produces evidence-backed findings and replacement
criteria, does not conflate complexity with correctness/security, and makes no changes
itself.

**Route:** `architect` to choose its home: pipeline lens, shared skill, or both.

### F4 — Policy propagation to subagents requires live evidence (medium priority)

**Observation.** Ponytail does not assume that a subagent receives the original ruleset:
a hook explicitly injects policy at launch and allows scoping by `agent_type`. Malformed
or missing payloads fail open to avoid blocking the host
([subagent hook](../../.review/ponytail/hooks/ponytail-subagent.js)).

**Current akmon state.** Generated `k-*` briefs require following project `AGENTS.md`,
while role constraints are encoded in allowed task kinds and tool sets
([generated agents](../../tools/model_routing/routing.py)). Actual availability of root
instructions and hook context varies by harness; Codex/Gemini/Copilot parity is only
partially verified ([vendor support](../../README.md#vendor-support)).

**What to adopt.** Do not add a hook immediately. Define test hypotheses for N1/A3/C6:

- does each subagent receive common guardrails and the task-kind-specific brief;
- does it see the owner/D5 boundary;
- can payload/output prove this rather than vendor documentation;
- what is the honest degraded mode without injection.

**Decision criterion.** Add injection only after reproduced drift; distinguish documented,
delivered, advisory, and enforced behavior in the capability matrix.

**Route:** begin with `review` live probes; if a gap is confirmed, move to `architect`.

### F5 — Hook OS/runtime portability is undefined (medium priority)

**Observation.** Ponytail includes regression tests for PowerShell environment syntax,
POSIX-only shell constructs, missing hook scripts, hangs caused by unclosed stdin, and
host manifest differences
([Windows hook tests](../../.review/ponytail/tests/hooks-windows.test.js)).

**akmon gap.** CI runs only on Ubuntu and two Python versions
([CI](../../.github/workflows/ci.yml)). Generated commands use `python3`, POSIX shell
variables, and `git rev-parse` ([sync hook command](../../bin/sync.py)). This is not a
defect if the contract is deliberately POSIX-only, but the OS dimension is absent from
the vendor capability matrix.

**What to adopt.** Define an explicit support contract:

`vendor × carrier/mount mode × OS/shell × capability`.

Either officially limit runtime support to POSIX environments, or add Windows generation,
CI, and end-to-end coverage. Portability must not be assumed silently.

**Decision criterion.** Every supported combination has an executable smoke test;
unsupported combinations are clearly identified.

**Route:** `review` to establish actual support scope, then `architect`.

### F6 — Deliberate shortcuts lack ceilings and revisit triggers (medium/low priority)

**Observation.** Ponytail requires a deliberate shortcut to record its ceiling and upgrade
path; its debt skill collects markers and separately flags entries without a trigger
([debt contract](../../.review/ponytail/skills/ponytail-debt/SKILL.md#scan)).

**Conflict.** A separate `PONYTAIL-DEBT.md` or marker ledger would violate akmon's
single-backlog invariant: accepted work must enter `TASKS.md`
([task destination](../../pipelines/tasks.md#when-to-write)).

**What to adopt.** Adopt the semantics, not a second ledger:

- a shortcut with a real ceiling receives a canonical task ID;
- the detail artifact records the ceiling, upgrade trigger, and affected boundary;
- a code marker, if needed, points to the task ID rather than creating a parallel backlog;
- deferred intent without a measurable trigger is a weak entry.

For a small self-contained follow-up, the current one-line task convention remains
sufficient; do not inflate every entry with a new schema.

**Decision criterion.** No accepted shortcut exists only in a comment; its revisit
condition is testable, while canonical ownership remains in the backlog/detail artifact.

**Route:** `architect`, but only if recurring shortcut markers appear in practice.

### F7 — Claim discipline and negative results are valuable (medium priority)

**Observation.** Ponytail publicly recorded that an early single-shot benchmark overstated
the effect because of a chatty baseline; the later agentic benchmark narrowed the claim.
The report explicitly states its limitations: one model, `n=4`, safety as a floor,
nondeterminism, and timeout cells
([limitations](../../.review/ponytail/benchmarks/results/2026-06-18-agentic.md#limitations-so-this-cant-be-the-next-thing-someone-debunks)).

In another benchmark, a new reuse rung was logically sound but its behavioral benefit did
not reproduce; the result was labeled **unproven**, not successful
([comprehension/reuse report](../../.review/ponytail/benchmarks/results/2026-06-22-issue-245-217-comprehension.md#217-rung-shipped-failure-did-not-reproduce)).

**What to adopt.** Strengthen `proven` in the learning promotion test. Promotion
evidence should distinguish contract/unit verified, behaviorally demonstrated,
no-regression only, unproven hypothesis, and model/harness-specific ceiling. This belongs
to F1/O5, not separate bureaucracy.

**Decision criterion.** A shared claim includes its evidence class and applicability
limits; failure to reproduce does not become positive evidence.

**Route:** `architect` together with O5 and the learning contract.

---

## 4. What should not be copied literally

### 4.1 Global `lite/full/ultra` modes

Mutable intensity state creates ambiguity: which contract is active, and can `ultra`
weaken the accepted scope? Akmon already has explicit roles, pipelines, profiles, task
kinds, and model tiers. The useful part is the stable solution ladder; the persona/mode
layer is unnecessary. Do not reuse `tier`: in akmon it already means a capability/model
rung, not policy strength.

### 4.2 `Shortest working diff wins` as an absolute rule

A small diff at the wrong boundary can leave a sibling path broken. LOC may be measured,
but it does not replace correctness, root-cause coverage, maintainability, or architecture
fit.

### 4.3 “One runnable check” as the complete verification contract

This is a useful lower bound for a small standalone example, but weaker than akmon's
current contract: behavior changes require tests, then lint/type/pre-commit checks, while
load-bearing changes undergo owner verification. One assertion cannot replace the full
suite.

### 4.4 Manual full rule copies for every host

Ponytail mitigates copy drift with byte comparison and invariant canaries
([copy checker](../../.review/ponytail/scripts/check-rule-copies.js)). In akmon, a canonical
source plus generated thin pointers and `sync --check`/`verify` better satisfy
one-owner-per-fact. Canary tests for load-bearing phrases may be adopted; duplicated prose
should not return.

### 4.5 Fail-open behavior without honest capability status

Fail-open behavior preserves host availability but means enforcement is absent. Akmon
should retain its rule: documented wire shape does not equal live capability; parity
claims require a real payload/enforcement probe and regression test.

### 4.6 Racing for the largest possible adapter count

Ponytail distributes a compact skill across many hosts. Akmon carries a heavier contract:
local layout, backlog, hooks, routing, carriers, and verification. Until package/init and
N1 are complete, deepening two or three verified surfaces is preferable to broad but
instruction-only support.

---

## 5. Recommended order for architectural consideration

| Order | Direction | Why now | Existing carrier |
|---|---|---|---|
| 1 | Behavioral evaluation contract | The largest new lever; tests the standard itself | O5 |
| 2 | Solution ladder + simplicity review lens | Small contract with broad effects on code volume and dependency choices | code-flow + review-flow |
| 3 | Vendor/carrier/OS capability contract | Makes portability claims verifiable and honest | N1 + A9 |
| 4 | Subagent policy-delivery probes | Tests the assumption that instructions are inherited | A3/C6/N1 |
| 5 | Evidence classes for learning promotion | Prevents `unproven` from becoming shared truth | O5 + learn |
| 6 | Ceilings/triggers for shortcuts | Useful after a recurring real signal appears | tasks/learn |

This is **not an accepted design or a backlog update**. After owner selection, the next
stage is a switch to `architect`, comparison of alternatives, and recording only the
selected directions.

---

## 6. Verification evidence

During the independent akmon check:

| Check | Result |
|---|---|
| `uv run pytest` | `421 passed` |
| `python3 meta/self_ci.py` | pass |
| `uv run ruff check .` | not run during this review |
| `uv build` | not run during this review |

The working tree had substantial pre-existing changes before the review began; the report
describes that tree, not the latest release tag. The archived report itself was the only
change made during that step.

## 7. Review limitations

- Ponytail was analyzed from the local 4.8.4 clone snapshot; remote issues and history
  were not rechecked.
- Its headline agentic evidence is limited to one model and few repetitions; it is a
  strong methodology example, not universal proof of the outcome.
- No live Windows run of Ponytail or akmon was performed; contracts and tests were
  compared.
- Ponytail's Codex/Gemini/Copilot enforcement was not used as evidence of parity for
  akmon.
- The recommendations deliberately stop before solution design, in accordance with
  review-flow.
