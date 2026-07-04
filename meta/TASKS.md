# TASKS — keystone development backlog

The single backlog for developing the keystone standard itself. Format:
[`pipelines/tasks.md`](../pipelines/tasks.md). Directions / model gaps: [`ROADMAP.md`](ROADMAP.md).

> This is keystone's *own* backlog (evolving the standard), distinct from a consuming
> project's `_forge/TASKS.md`.

## Status

Tooling spine (`bin/sync.py`, `bin/verify.py`, vendor-neutral `hooks/hook_core.py`) exists and
is **tested** (`tests/`). Remaining work is contract specification + scale hardening, not new
mechanism.

## Active / blocked / deferred

Model routing ([ADR 0004](decisions/0004-model-routing-capability-tiers.md); design in
[`meta/design/model-routing.md`](design/model-routing.md)):

- C11 · D2 ledger · active · architect/engineer · mechanical verify-tracking: ledger data + reminder/status hooks + pre-commit gate (keystone mechanism, project path-config); ledger entry = unit of verify gate for reasoner/second-opinion attachments (+ synthesizer gate report, per A5) · [design](design/d2-ledger.md)
Synthesizer / gate-pack extension (design in [`model-routing.md` §9–11](design/model-routing.md)) —
**architecture** (lock, then ADR):

- A5 · synthesizer + roles design: owner lock · done · architect · §9.7 + §10.4 locked by owner → [ADR 0005](decisions/0005-synthesizer-gate-audit-and-role-routing.md) (extends 0004); unblocks C15–C20 · [design §9.7+§10.4](design/model-routing.md)
- A6 · roles & pipelines under the subagent model · done in design · architect · recorded as §10 (role = orchestration contract; role→task-kinds matrix; zone plan from Decompose/Survey; loop-back edges; learn/release tiers); lock items folded into A5 (done) · [design §10](design/model-routing.md)

**implementation** (A5 locked → ADR 0005; sequence C15 → C16/C17 → C18):

- C15 · registry/binding: synthesizer tier · active · engineer · pinned-max `synthesizer` policy + `synthesis-verify` and `plan-draft` task-kind rows + dynamic reasoner policy (orchestrator rung + per-kind floors) + second-opinion model-diversity ladder + `role_task_kinds`; compute_binding, init, generated `k-synthesizer` · [design §9.3+§10.2](design/model-routing.md)
- C16 · gate-pack builder · queued (after C15) · engineer · one structured package (artifacts + yardstick + coverage map) consumed by synthesizer subagent and second-opinion CLI, plus the minimal plan-check pack (yardstick + zone plan, pre-fan-out); replaces free-form `--prompt-file` in second_opinion.py; runnable as one deterministic script per §11 · [design §9.4+§9.3.5](design/model-routing.md)
- C17 · coverage map from delegation log · queued (after C15) · engineer · zone label on fan-out delegations (from the §10.3 zone plan) + assembler tool — map at code cost, not tokens · [design §9.4+§10.3](design/model-routing.md)
- C18 · docs: leverage principle + role/pipeline deltas · queued (after C15) · engineer · name the leverage principle in MODEL.md; tier table + matrix rows update; review/design-flow synthesizer anchors (post-fan-out + the pre-fan-out plan check) + loop-back edges; roles/*.md one-paragraph deltas linking §10 incl. the drafts-vs-decides invariant reading; demote static floor warning to weak prior · [design §9.1–9.5+§10](design/model-routing.md)
- C19 · owner-attention metrics in stats digest · deferred · extends C13: D2 pending/verified, decisions per session, next to token spend · [design §9.6](design/model-routing.md)
- C20 · role-matrix advisory check in delegation hook · queued (after C15) · engineer · warn when a routed task kind falls outside the active role's `role_task_kinds` row; ships the session-state active-role marker (A5 lock: doc rule first, marker with this task) · [design §10.2+§10.4](design/model-routing.md)
- C21 · delegation indication in the host UI · active · engineer · the delegation-log hook additionally returns a one-line `systemMessage` per subagent call (`→ <agent> (<model>): <description>`) so delegations are visible in IDE/CLI surfaces at zero token cost — code, not agent narration; keep the TSV log as the record · owner request 2026-07

Keystone identity (rename):

- V1 · rename `ai_keystone` → `ai_anvil` (anvil metaphor) · pending (owner-timed) · release+architect · the shared standard is the *anvil* every project's `_forge` (forge) hammers on — fixes the mixed smithy/masonry metaphor; scope: GitHub repo rename, submodule URL+mount (`<FORGE_ROOT>/keystone` → `<FORGE_ROOT>/anvil`), `.keystone.toml`, hooks/tools path derivation, doc sweep (MODEL/BOOTSTRAP/README/ADRs grandfathered), consumer pin bump; one migration release; cheapest now while alphavar is the only consumer; sequence after the C15–C18 wave to avoid mid-implementation churn

Role-triad + develop/use split ([ADR 0003](decisions/0003-role-triad-and-develop-use-separation.md)):

- C6 · UserPromptSubmit role-confirm for sub-agents · deferred · verify Claude Code hook behaviour first · [ADR 0003](decisions/0003-role-triad-and-develop-use-separation.md)
- C9 · release_check.py keystone-subject scoping · active · `--check --subject keystone` from a non-Python consumer: (a) ✅ pytest-runner resolution fixed in v0.2.1 (dev-venv `python -m pytest`, pinned `[test].runner` from `.keystone.toml`, `uv run --with pytest` fallback); (b) ⬜ `verify --strict` still runs against the consumer root, so the consumer's own TASKS/CI warnings block a keystone release — scope keystone-subject verify to the submodule tree (or reuse `meta/bin/validate.py`). Surfaced cutting v0.2.0; (a) closed cutting v0.2.1
- C2 · release tool: pin-bump subject · deferred · the 3rd release subject (keystone pin bump recorded in a consuming project); only after keystone+package subjects settle · [design](design/release-versioning.md)
- A3 · cross-agent contract v2 · deferred · skill/role inventory beyond thin pointers · [design](design/cross-agent-contract-v2.md)
- C1 · harden git-commit-guard parsing · deferred · close regex bypasses only if a real one bites
- A1 · orchestration / role handoffs · deferred · until role routing causes real friction (4 roles now; release routes) · [ROADMAP O4](ROADMAP.md)
- A2 · OPERATE mode · deferred · keep as design note until a runtime actor exists · [ROADMAP O1](ROADMAP.md)

Ids use the typed scheme ([ADR 0002](decisions/0002-task-id-convention.md)): **A** architecture/
design · **C** code · **L** learning · **V** release · **N** analysis/review; the role is derived. Archived `T#` are
grandfathered (frozen), so the historical references below keep their `T#`.

Trim rationale (A1/A2/C1/A3/C2 "deferred") is recorded in ROADMAP O# / the release design; do not
re-expand without a reason. The T3 release design (ADR 0001) is implemented (T10–T15); C2 is the
deferred pin-bump follow-up, A3 the deferred O3 v2 design, A4 surfaced while building the release
tool.

## Done

See [`TASKS_ARCHIVE.md`](TASKS_ARCHIVE.md).
