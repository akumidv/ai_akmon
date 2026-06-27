# Review — keystone dev layer (role activation + token efficiency)

A `review`-role report ([review-flow](../../pipelines/review-flow.md)). Analysis only — it
states findings and the criteria a fix must meet; the constructed fixes are `architect`
(develop ADR 0003) and `engineer` tasks (`meta/TASKS.md`).

- **Subject:** keystone's dev layer as wired into a consuming project — how a role is
  determined and kept active, and the token cost of the standard.
- **Yardstick:** (1) a role is accurately chosen and reliably re-declared on every task
  switch, including in automated / sub-agent runs; (2) the always-on token cost is minimal.

## Findings

### F1 — The standard restated shared rules instead of linking (severity: high)
*Evidence:* "Analysis before mutation", "never commit on the owner's behalf", "verify against
code", and "owner-verify math/data/architecture" each appeared verbatim in `guardrails/_common.md`
**and** restated in role files **and** re-emitted by a hook — violating keystone's own
"one owner per fact". *Criterion for a fix:* each rule has one owner; role/pipeline docs link
it. *Status:* **partially addressed** — ADR 0003's full decouple removed the develop-citation
coupling and trimmed the USE surface; a focused dedup of the remaining restated guardrail
prose remains open.

### F2 — Role determination had no heuristic at the decision point (severity: high)
*Evidence:* the SessionStart injection listed the agent roster but gave no routing rule; the
routing table lived in `roles/README.md`, rarely read. A pure review task had no role and was
routed to `architect` by default. *Criterion:* a one-line routing rule available where the
role is chosen. *Status:* **addressed in the model** — the analysis/synthesis/realization
triad + the **discriminator** now exist (ADR 0003); injecting the discriminator into the
SessionStart hint is task **A10**.

### F3 — Role activation is unguarded on the reverse switch and in automation (severity: medium)
*Evidence:* `role-on-code` nudges toward `engineer` on the first code edit only; there is no
nudge toward `review`/`architect`, no per-switch re-fire (one marker silences the whole
session), and the per-session markers key on `session_id` so spawned sub-agents may be missed.
*Criterion:* each role switch is prompted once per direction, and the prompt reaches sub-agent
/ automated runs. *Status:* **open** — triad-aware hooks + per-switch markers + the hardcoded
`OPERATE` desk label are task **C5**; a `UserPromptSubmit` confirm for sub-agent coverage is
task **C6** (verify Claude Code hook behaviour first).

### F4 — keystone's own dev artifacts shipped into every consumer (severity: high)
*Evidence:* the submodule mixed the USE surface with keystone's vision (`README.md`), ADRs,
ROADMAP, design, and backlog; operative docs cited those dev artifacts. *Criterion:* the USE
surface is self-contained; keystone's DEVELOP artifacts are cordoned and not loaded by a
consumer. *Status:* **addressed** — ADR 0003 + the `meta/` cordon, the `README→CONCEPT` +
thin `MODEL.md` split, and `verify.py`'s develop-boundary check.

## Routing

Construction handed to `architect` (ADR 0003, done) and `engineer` (`meta/TASKS.md`): the
open items are **A10** (routing hint), **C5** (triad-aware hooks + per-switch markers + OPERATE
label), and **C6** (sub-agent confirm). No finding revealed a wrong yardstick.
