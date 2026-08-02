# akmon development plan from alternatives (accepted — ADR 0010)

> **Status: accepted as direction.** The A11 owner walkthrough closed all 7
> themes of §6.0 and decisions D1–D4; the verdict set is folded into
> [ADR 0010](../../decisions/0010-alternatives-adoption-a11-verdicts.md), with
> per-theme rationale, amendments and pilot criteria in the
> [walkthrough record](walkthrough-a11-20260717.md). Accepted items carry
> canonical IDs in `meta/TASKS.md`, the living execution carrier — this file
> records *why* each item exists and where it came from, not its execution
> state. Do not re-open the accepted direction here; changes go through the
> named revisit-if conditions or a new ADR.
>
> **Framing.** akmon's goal function is *quality per unit of tokens + owner
> attention*, delivered through layers, roles, and subagents. This plan maps each
> borrowed idea to a concrete akmon weakness it closes or a concept gap it fills.
> The file is extensible: reviewing another alternative appends to the register
> (§1), adds/strengthens rows in §2–§3, and may reprioritize §6 — it never
> rewrites the source reviews, which stay point-in-time.
>
> Wave 2 (Superpowers / OpenSpec / wshobson-agents, both claude and codex
> reviews) is merged: weaknesses W17–W23, concepts 9–14, items P0.4, P1.5–P1.7,
> P2.4–P2.7 and the priority view in §6.0.
>
> Wave 3 (owner addition, 2026-07-16 — host-native mechanisms, not a reviewed
> alternative): bind the A-stage design step to the host's plan surface —
> Claude Code plan mode's durable plan file and the agent-team ("tech lead")
> plan-approval gate — and consider each vendor's *built-in* subagent types in
> place of generated `k-*` where measurably at least as effective. Merged as
> W24, concept 15, item P2.8, decision D4; mechanisms verified against the
> installed Claude Code 2.1.211, not vendor docs.
>
> **Carried into [`meta/TASKS.md`](../../TASKS.md)** as the "Alternatives
> adoption" block: A11 (walkthrough, done → ADR 0010) → N2 (stage 0 probes &
> inventory) → A12/C40 (stage 1) → A13/C41 (stage 2) → A14/C42 (stage 3) →
> A15/C43 (stage 4); P3.4's matrix-as-data contract split out as A16/C44, the
> matrix's Gemini/Copilot cells as demand-driven N3. Every stage is
> design-first: the A-task locks the contract, only then the C-task implements.
> Execution state lives in TASKS.md; this file remains the why-record.

### Reconciliation inputs (resolved)

The first backlog projection exposed two dependency contradictions and one stale
current-state claim. All three are **resolved**: R1 and R2 are expressed in the task gates
in `meta/TASKS.md` (A12 waits for N2; A15 gates on C42 + N2 + the N1 Claude/Codex rerun),
R3 is folded into A12's scope (the malformed-input no-op contract). Kept as the record of
what was reconciled:

- **R1 — A12 starts too early in the execution carrier.** `meta/TASKS.md` currently
  marks A12 runnable after A11, but A12 includes P1.2 and P1.7, which consume N2's
  P0.3 invariant inventory and P0.4 source/generated-boundary declarations. Under
  the dependency spine below, A12 must wait for N2 before it can lock those contracts.
- **R2 — A15 omits the matrix-rerun gate.** `meta/TASKS.md` currently gates A15 on
  C42 and N2, while this plan requires P3.2/P3.3 → P3.4 → Phase 4 and assigns the
  P3.4 live matrix rerun to N1. Phase 4 must therefore wait for N1/P3.4 as well as
  C42 and N2.
- **R3 — W8 overstates the malformed-input gap.** Both current adapters already
  catch malformed JSON rather than crashing. Claude returns an empty payload; Codex
  retains the raw input, and ordinary malformed input produces no action. The missing
  survivability work is bounded stdin handling and BOM normalization; design should
  define and preserve a malformed-input no-op contract with regression coverage, not
  treat JSON-error catching as absent.

These reconciliation constraints were considered in the A11 walkthrough and are now
expressed in the canonical execution carrier, `meta/TASKS.md` (see ADR 0010 §Amendments
for the follow-up re-scoping accepted from the backlog review).

Review files cited throughout (English versions are the only ones kept):

[pny/claude]: review-claude-ponytail-20260718.md
[pny/codex]: review-codex-ponytail-20260718.md
[top3/claude]: review-claude-superpowers-openspec-wshobson-20260718.md
[top3/codex]: review-codex-akmon-top-3-20260718.md

- **pny/claude** — [review-claude-ponytail-20260718.md](review-claude-ponytail-20260718.md)
- **pny/codex** — [review-codex-ponytail-20260718.md](review-codex-ponytail-20260718.md)
- **top3/claude** — [review-claude-superpowers-openspec-wshobson-20260718.md](review-claude-superpowers-openspec-wshobson-20260718.md) (§5 is the cross-review against top3/codex)
- **top3/codex** — [review-codex-akmon-top-3-20260718.md](review-codex-akmon-top-3-20260718.md)

---

## 1. Alternatives register

| Alternative | Class | Reviewed | Sources |
|---|---|---|---|
| [ponytail](https://github.com/DietrichGebert/ponytail) (commit `14a0d79`, v4.8.4) | one behavioral skill ("lazy senior dev" YAGNI ladder) + a mature distribution/measurement shell | 2026-07-15/18 | [pny/claude] · [pny/codex] |
| [Superpowers](https://github.com/obra/superpowers) (commit `d884ae0`) | full execution methodology as composable skills + bootstrap; ~10 harnesses | 2026-07-18 | [top3/claude] §1 · [top3/codex] §1 |
| [OpenSpec](https://github.com/Fission-AI/OpenSpec) (commit `0a99f41`) | spec-driven change lifecycle (delta specs, archive-merge) + machine-readable CLI contract | 2026-07-18 | [top3/claude] §2 · [top3/codex] §2 |
| [wshobson/agents](https://github.com/wshobson/agents) (commit `b6af371`) | multi-harness plugin marketplace; source/generated invariants, capability matrix as code, layered evals | 2026-07-18 | [top3/claude] §3 · [top3/codex] §3 |

*(next alternatives are appended here with their own review files; remaining
candidates from the landscape ranking: Spec Kit, Agent OS, GSD Core)*

---

## 2. Weak points of akmon these findings close

Grouped by the kind of gap. `Source` cites the review section that carries the
evidence and detail; `Carrier` is the existing backlog anchor.

### 2.1. Proof and measurement (the largest gap)

Confirmed across all four sources: every mature alternative built eval
infrastructure, and the three observed architectures are complementary layers —
cheap deterministic gates (ponytail) → session compliance (Superpowers) →
statistical certification (wshobson), each cost-tagged
([top3/claude] §4.1).

| ID | Weakness | Evidence | Closed by | Source | Carrier |
|---|---|---|---|---|---|
| W1 | The goal function is measured nowhere; not a single first-party number proves akmon helps | 2026-07-05 review: "verification lags construction" | behavioral/agentic A/B benchmarks with a control arm; behavior gates for the forcing hooks; grader unit-tested separately from any API-dependent eval; layered depth with cost tags (static → LLM judge → statistical) | [pny/claude] §2.1 / [pny/codex] F1 / [top3/claude] §1.2-5, §3.2-4 / [top3/codex] gap 1 | O5 |
| W2 | Vendor-support table is full of ❓ filled from docs, not experiment | README matrix | re-run the matrix from experiment; record documented / delivered / advisory / enforced per cell; capability matrix kept as code with the human table generated; one canonical acceptance probe per vendor as the definition of "delivered"; round-trip real-CLI smoke tests where cheap | [pny/claude] §3.1 / [pny/codex] F5 / [top3/claude] §1.2-8, §3.2-2/-6 / [top3/codex] gap 5 | N1, A9 |
| W3 | No isolation discipline defined for any future benchmark — a contaminated benchmark lies confidently | ponytail's near-published false ~4% (SessionStart hook fired in the baseline arm) | adopt the isolation checklist: one plugin per arm, excluded global settings, fresh repo copy + fresh context per cell, workspaces retained for rescoring | [pny/codex] F1 (verified against `benchmarks/results/2026-06-18-agentic.md`) | O5 |

### 2.2. Drift control

| ID | Weakness | Evidence | Closed by | Source | Carrier |
|---|---|---|---|---|---|
| W4 | Subagent delivery drift: a non-`k-*` subagent may leave without guardrails; never verified live on any harness | no SubagentStart surface; matrix rows unproven | probe first (record from the payload what actually arrives), then — only if drift reproduces — a scoped SubagentStart injection hook | [pny/claude] §2.2 / [pny/codex] F4 | A3, C6 |
| W5 | Semantic drift between guardrail prose and hook code: `sync.py --check` catches pointer drift, nothing catches a rule reworded in `guardrails/*.md` but stale in `hook_core.py` | same rule lives in two forms with no cross-check | invariant canary in `meta/self_ci.py`: load-bearing phrases/constants required present in both prose and code; extend the same sweep to documentation drift (dead links, staleness, size caps), every finding shipping a concrete fix string | [pny/claude] §2.5 / [top3/claude] §3.2-3 | — |
| W6 | Deferred *simplifications in code* rot silently: D2 tracks deferred feature verification only | no marker convention | `akmon-defer: <ceiling>, <trigger>` marker — trigger mandatory, points to a canonical `TASKS.md` ID, no parallel ledger; grep harvest flags `no-trigger` rot | [pny/claude] §3.2 / [pny/codex] F6 | D2-adjacent |
| W7 | Version drift across manifests once more than one carrier exists | pyproject / CHANGELOG / consumer pin unlinked | version cross-check in `release_check`; mandatory if a plugin carrier lands | [pny/claude] §3.5 | — |
| W21 | Change state has no lifecycle: design docs are whole-document snapshots (no delta records, no archive-merge step reconciling finished work), and a non-trivial change fragments across `meta/TASKS.md`, design, ADR, D2, code, and tests with no projection or invalidation | backlog entries sitting `code-complete & D2-pending`; design docs drift silently | delta semantics (`ADDED/MODIFIED/REMOVED`) + an archive-merge closing step folded into akmon's existing carriers (no new tree); a compact change manifest *linking* the canonical owners, never duplicating them; dependency invalidation — a changed upstream design/spec marks dependent task briefs and audit packs stale | [top3/claude] §2.2-1/-2, §5.2-1/-2 / [top3/codex] gap 4 | — |
| W23 | Source/generated boundary not declared or checked (what `sync.py` generates vs what may be hand-edited), and no numeric progressive-disclosure caps despite preaching token economy | wshobson states it as invariant #1 with concrete caps (context ≤150 lines/~500 tokens; 8 KB vendor skill cap) | declare the boundary as an invariant; one self_ci check for it; adopt numeric caps for always-loaded artifacts with a deterministic check | [top3/claude] §3.2-1/-5 / [top3/codex] §3 | — |

### 2.3. Robustness of the enforcement surface

| ID | Weakness | Evidence | Closed by | Source | Carrier |
|---|---|---|---|---|---|
| W8 | Hooks can still block or crash a session: Python reads stdin with no bounded timeout, BOM input is not normalized, and generated wiring has no `timeout`; malformed JSON is already caught by both adapters but the intended no-op behavior lacks regression coverage | same risk class as ponytail's frozen-session issue #443; current `claude_adapter.load_payload()` and `codex_adapter.load_payload()` catch JSON decode errors | "hook never blocks" contract: bounded stdin handling, BOM normalization, `timeout` in `sync.py` wiring, regression tests for malformed-input no-op behavior, and degradation tests for the missing paths | [pny/claude] §2.3 / [pny/codex] F5 | — |
| W9 | OS/shell support silently assumed rather than declared | no statement anywhere | declare the support contract as a dimension: `vendor × carrier × OS/shell × capability`; POSIX-only is acceptable if stated | [pny/codex] F5 | N1 |
| W10 | Instruction-tier vendors (no hooks) have no defined degradation contract — ❓ instead of "what is guaranteed" | README matrix | plugin-tier / instruction-tier tags per vendor row; a minimal instruction-tier contract (pointer + guardrails text + role rule) | [pny/claude] §3.1 | N1 |
| W20 | No execution-progress ledger surviving compaction: an orchestrator that loses its place may re-dispatch entire completed task sequences | named "the single most expensive failure observed" in Superpowers | append-only ledger convention in `_aitna/` (one line per completed dispatch); after compaction trust the ledger and `git log` over recollection | [top3/claude] §1.2-4 | — |

### 2.4. Gaps inside existing roles and pipelines

No new roles are needed — every gap found lands *inside* an existing role, in
all four reviews independently ([top3/codex]: "a handoff protocol, not a
role"). That is itself a finding: the role set (review/architect/engineer +
learn/release) held up against external comparison; what is missing is
procedure, not structure.

| ID | Weakness | Role/pipeline | Closed by | Source |
|---|---|---|---|---|
| W11 | `code-flow` has the individual reuse rules but no *ordered decision procedure* before writing new code, and no root-cause clause for bug fixes | engineer / code-flow | solution ladder (need at all → project reuse → stdlib → native → installed dep → minimal expression → new code) + "fix the shared source, not the named symptom"; subordinate to accepted task and locked design; never overrides security/accessibility/trust-boundary/data-loss/explicit requirements | [pny/claude] §7.2-2 / [pny/codex] F2 |
| W12 | Review verdicts are single-blended and under-specified: no named yardstick for over-engineering, no split between spec compliance and implementation quality, and engineer verification is signal-triggered rather than a consistent task-level contract (worker success reports carry too much trust) | review / review-flow, engineer gate | simplicity lens: `delete / stdlib / native / yagni / shrink` tag vocabulary, read-only, severity by boundary/risk, never LOC; **two-verdict task review** — spec compliance and implementation quality separately, material findings force fix + re-review; reviewer-independence clauses ported verbatim (never tell a reviewer what not to flag, never pre-rate severity, plan contradictions go to the owner) | [pny/claude] §7.2-3 / [pny/codex] F3 / [top3/claude] §1.2-1/-7 / [top3/codex] gap 3 |
| W13 | The learn-loop PROMOTE step grades no evidence: a plausible rule and a proven rule promote identically | learn | evidence classes: contract/unit-verified · behaviorally demonstrated · no-regression-only · unproven hypothesis · model/harness-specific ceiling; negative results retained and labeled | [pny/claude] §7.2-4 / [pny/codex] F7 (verified: ponytail's #217 rung labeled *unproven* when the benefit did not reproduce) |
| W24 | design-flow's living design concept is not wired to the host's native plan surface: Claude Code plan mode already produces a durable, owner-approved, resumable plan file (default `~/.claude/plans/`, directory configurable to a project path; `ExitPlanMode` refuses without it), and agent teams give the lead an approve/reject gate over every teammate's plan — yet akmon's design-first rule relies on session discipline where the harness offers an enforcement point, and the approved plan evaporates in a vendor-private directory instead of becoming the design concept | architect / design-flow (+ delegation) | run the A-stage design session in plan mode and promote the approved plan file into `meta/design/` (as, or folded into, the living design concept) with a back-pointer; in team ("tech lead") execution the lead's teammate-plan approval is the same gate at dispatch granularity; vendor mechanisms stay in the adapter layer — instruction-tier fallback: the design concept file itself is the plan | owner request 2026-07-16; verified against Claude Code 2.1.211 *(wave 3 — host-native, not from the reviewed alternatives)* |

### 2.5. Delegation contract and token economics *(new group — wave 2)*

The delegation surface (orchestrator ↔ subagents) has routing but no complete
task protocol; this is the wave-2 counterpart of §2.4 — again contracts, not
roles.

| ID | Weakness | Evidence | Closed by | Source |
|---|---|---|---|---|
| W17 | No subagent report contract: no bounded status vocabulary and no defined controller reactions — every orchestrator improvises failure handling | Superpowers defines `DONE / DONE_WITH_CONCERNS / NEEDS_CONTEXT / BLOCKED`, each with a prescribed response, plus "never force the same model to retry without changes" | a normative dispatch packet (task goal, accepted design/task excerpt, relevant constraints, allowed scope/tools, verification commands, owner boundary, expected report paths) + the status vocabulary with controller reactions | [top3/claude] §1.2-6 / [top3/codex] gap 2 |
| W18 | Model routing has no cost heuristics and no "explicit model per dispatch" rule; `tools/model_routing/registry.json` encodes a floor, not outcome economics | "turn count beats token price" — cheapest models take 2–3× the turns and cost *more*; an omitted model silently inherits the expensive session model | cost heuristics stated as policy (mid-tier floor for reviewers and prose-driven implementers; cheapest tier only for transcription-grade tasks); explicit model in every dispatch; calibrate by outcome portfolio per task kind × tier (turns, tokens, retries, review defects, owner interventions), not token price | [top3/claude] §1.2-2, §3.2-7 / [top3/codex] gap 6 |
| W19 | No context-hygiene contract for delegation: bulk artifacts pasted into dispatches and reports stay resident in the orchestrator's context and are re-read every turn | a real 42k-char dispatch (99% pasted history) cited as the anti-pattern | file handoffs: task briefs, reports, and review packages move as files; a subagent returns status + one-line summary + paths only | [top3/claude] §1.2-3 / [top3/codex] gap 2 |
| W22 | akmon tooling (`sync --check`, `verify.py`, `self_ci.py`) emits prose only: no shared diagnostic envelope, no machine-readable fix strings — costly for both agents and the owner to act on | OpenSpec's agent contract: one JSON per invocation, `severity/code/message/target/fix` envelope, `snake_case` code catalog, exit-code table | one shared diagnostic envelope across akmon tooling with a mandatory one-sentence `fix` per finding | [top3/claude] §2.2-3 / — |

### 2.6. Owner attention and adoption

| ID | Weakness | Evidence | Closed by | Source |
|---|---|---|---|---|
| W14 | Active state is invisible: the owner cannot cheaply see version pin, active role, hook wiring, carrier | finding out costs attention | `akmon status` (observability only; mutable enforcement levels are a separate contested decision — §5 D1) | [pny/claude] §2.4 / [pny/codex] 4.1 |
| W15 | Install friction: multi-step manual BOOTSTRAP vs ponytail's 2-command plugin install | BOOTSTRAP.md | Claude Code plugin as a third carrier (ADR required; includes the uninstall-state-outside-plugin trap) | [pny/claude] §3.3 |
| W16 | No delivery channel at all for vendors with neither hooks nor pointer support | matrix tail | MCP as a transport for the standard itself (thin wrapper over existing artifacts) | [pny/claude] §3.4 |

---

## 3. New concepts adopted into the akmon approach

Concepts that generalize beyond any single alternative — these change *how akmon
develops itself*, not just what lands in the backlog:

1. **Probe-first: verification before mechanism.** Prove a gap exists (live
   probe, reproduced drift) before building the mechanism that closes it. A
   fail-open hook is availability, not enforcement. Governs W4 and gates P4.1.
2. **Behavior gates with a control arm — and a baseline that must fail.** Check
   the *behavior* a rule produces, not the rule text; the delta against the
   without-arm is the proof; the grader itself is unit-tested without an API
   key. Wave 2 adds the RED-GREEN-REFACTOR discipline for guardrail authoring:
   if you didn't watch an agent fail without the rule, you don't know the rule
   teaches the right thing ([top3/claude] §1.2-5). Governs W1.
3. **Benchmark isolation discipline.** The contamination checklist (W3) as a
   standing part of any eval contract — adopted once, applies to every future
   measurement.
4. **Degradation as a supported contract, not a gap.** Tiers per vendor with a
   stated minimum (W9, W10); "documented / delivered / advisory / enforced" as
   the honest vocabulary for capability cells (W2).
5. **Never-block execution contract for hooks.** The enforcement surface must
   never cost a session (W8).
6. **Evidence-graded promotion.** No rule is promoted on plausibility; failure
   to reproduce never becomes positive evidence (W13).
7. **Mandatory revisit trigger on any deferred cut.** A ceiling without a
   trigger is a legitimized TODO (W6).
8. **Executable canaries for single-ownership.** "Exactly one owning artifact"
   is enforced by CI, not by discipline (W5, W7, W23).
9. **Turn-count economics.** Total task cost = turns × context, not token
   price; routing decisions and their calibration must count turns, retries,
   review loops, and owner interventions (W18). *(wave 2)*
10. **Context hygiene: bulk moves as files.** Anything pasted into a dispatch
    or report is a permanent context tax on the orchestrator; briefs, reports,
    and review packages travel as file paths (W19). *(wave 2)*
11. **Durable progress over recollection.** Execution state that must survive
    compaction lives in append-only artifacts, never in conversation memory
    (W20). *(wave 2)*
12. **Change as a delta folded back into truth.** A change describes its diff
    against current truth, a closing step reconciles finished work with the
    canonical docs, and a changed upstream artifact invalidates downstream work
    explicitly (W21). Complements — never substitutes — the learn loop.
    *(wave 2)*
13. **Machine-readable diagnostics with a fix per finding.** Every akmon check
    speaks one envelope; every finding ships one actionable sentence (W22).
    *(wave 2)*
14. **A pilot acceptance criterion per accepted item.** Anything the
    walkthrough accepts gets a measurable pilot criterion before engineer work,
    and rejected mechanisms are recorded with revisit conditions
    ([top3/codex] consolidated table). *(wave 2 — meta-discipline for this
    plan itself)*
15. **Design in the host's plan surface; approval as a harness gate.** Where
    the vendor offers a first-class planning mode (read-only research →
    explicit owner approval → durable, resumable plan file), the design step
    runs in it, and the approved plan is promoted into the design concept
    rather than left in a vendor-private directory; where a team mode exists,
    the lead's plan-approval gate over teammates turns "design-first" from
    discipline into mechanism (W24). The portable contract is
    mode + gate + artifact; the concrete carriers are vendor-adapter concerns.
    *(wave 3 — owner addition)*

## 4. Explicit non-goals (examined and rejected)

- **Adapter sprawl** (~20 hosts): every adapter is a liability at akmon's
  surface size; deep on Claude/Codex + instruction-tier for the rest.
- **Full ruleset injection every turn**: a direct token tax against the goal
  function; SessionStart + targeted PreToolUse reminders stay.
- **One monolithic rule text**: layers/roles/profiles are deliberate structure;
  an instruction-tier *digest* is the portable form, not a replacement.
- **Shortest-diff as an absolute / one-runnable-check as the full test
  contract**: rejected in both ponytail reviews' do-not-copy lists.
- **A parallel spec tree** (`openspec/`-style) beside `meta/TASKS.md` +
  `meta/design/` + D2: adopt the lifecycle semantics (W21), never the folders —
  no second source of truth, no second task list. *(wave 2)*
- **Bootstrap absolutism** ("1% chance → MUST invoke") and universal mandatory
  TDD/worktrees: reliability bought with a permanent token/attention tax; akmon
  scopes discipline by archetype and risk. *(wave 2)*
- **Catalog scale as a goal** (94 plugins / 203 agents; persona proliferation):
  domain personas stay LOCAL specializations or skills, never SHARED roles.
  *(wave 2)*
- **New top-level roles**: all four reviews converge — the gaps are handoff and
  change-state contracts around the existing roles. *(wave 2)*

## 5. Open owner decisions

- **D1 — mutable enforcement levels** (`advise|nudge|enforce|off`):
  [pny/claude] §2.4 proposes them; [pny/codex] 4.1 argues mutable intensity
  makes the active contract ambiguous. The observability half is uncontested
  (W14 / P1.4); the mutable half is parked as P4.4 pending this decision.
  **Resolved (A11 theme 7, 2026-07-17): mutability rejected** — P4.4 closed
  with the [pny/codex] 4.1 rationale; the "soften a hook" need is served by
  the declared path (C42 data → fix or unwire via sync, visible in
  `akmon status`). Revisit-if: real consumer demand for per-project
  softening that unwiring cannot express —
  [walkthrough record](walkthrough-a11-20260717.md).
- **D2 — SubagentStart timing**: probe-first order adopted in this plan
  (P0.1 gates P4.1); the owner may override and build the hook immediately.
  **Resolved (A11 theme 2, 2026-07-17): probe-first confirmed** —
  [walkthrough record](walkthrough-a11-20260717.md).
- **D3 — fresh vs forked subagent context**: Superpowers mandates absolute
  fresh-context isolation per task; [top3/codex] recommends A/B-testing it
  against a cheaper bounded inherited-context arm before adopting it as
  doctrine. Measured inside P3.2's harness; until then the delegation contract
  (P2.4) stays silent on isolation.
  **Parked (A11 theme 3, 2026-07-17): confirmed** — resolved by measurement in
  C42; P2.4 stays silent on isolation until then
  ([walkthrough record](walkthrough-a11-20260717.md)).
- **D4 — built-in vs generated subagents, per vendor** *(wave 3)*: Claude Code
  ships built-in agent types (Explore, Plan, general-purpose, fork) that
  overlap akmon's generated `k-*` roles (k-explorer, k-reasoner); other
  vendors' harnesses carry their own native subagent mechanisms. Mapping akmon
  roles onto the host's built-ins would drop generated-agent maintenance and
  inherit vendor tuning — but it is unverified what a built-in actually
  receives (guardrail delivery, model pinning via `model` override, tool
  limits, context shape) and whether the delegation log / routing hooks still
  see it. Decision rule: prefer the vendor's native subagents *where they are
  measurably at least as effective* (delivery proven + outcome economics per
  W18), else keep `k-*`; decided per vendor row, not globally. The P0.1
  delivery probes extend to the built-in types as a comparison arm (Claude
  Code first); until then `k-*` stays the contract.
  **Resolved (A11 theme 2, 2026-07-17): the decision rule is confirmed** —
  decided per vendor from the N2/P0.1 comparison-arm data; `k-*` stays the
  contract until the data lands ([walkthrough record](walkthrough-a11-20260717.md)).

---

## 6. Phased plan

Ordering rationale: verification before mechanism, cheap hardening before new
surface, measurement before expansion. **Priority ≠ execution order**: phases
encode dependencies and effort; the priority view below says what matters most
if capacity is scarce.

### 6.0. Priority view

Priorities follow the cross-review convergence: both wave-2 reviews
independently rank proof of behavior and proof of delivery first
([top3/claude] §4.1, [top3/codex] consolidated table). Acceptance signals
implement concept 14.

| Priority | Theme | Items | W | Acceptance signal for the pilot |
|---:|---|---|---|---|
| 1 | Prove that policy changes behavior | P3.1 → P3.2 (+P3.3) | W1, W3, W13 | a repeated baseline/treatment fixture catches ≥1 known policy failure and reports variance and cost |
| 1 | Prove vendor delivery on live paths | P0.1, P0.2 → P3.4 | W2, W4, W9, W10 | a real CLI transcript proves the exact payload on one vendor × carrier × subagent path |
| 2 | Delegation contracts | P2.4, P2.5, P2.6, P2.8 | W17, W18, W19, W24 | two representative tasks run on the packet; scope escapes, missing-context retries, and dispatch tokens measured; one A-stage design produced via plan mode and promoted into `meta/design/` |
| 2 | Change-state lifecycle | P2.7 | W21 | one change manifest links the existing owners, detects a stale base, adds no second source of truth |
| 2 | Review/handoff discipline | P2.1, P2.2 | W11, W12 | escaped findings at final audit and review-loop count drop on two pilot reviews |
| 3 | Cheap deterministic hardening | P1.1–P1.7, P0.3, P0.4, P2.3 | W5–W8, W20, W22, W23 | checks land in `self_ci`/`release_check` and fail on seeded violations |
| 4 | Owner attention & new carriers | P1.4; Phase 4 | W14–W16 | gated on Phase 3 measurement; D1 for P4.4 |

### Phase 0 — Probes and declarations (review role, no code)

- **P0.1** Live subagent-delivery probes on Claude Code and Codex → reproduced-drift
  record (or its absence) attached to N1/A3/C6. Includes the D4 comparison arm:
  probe the host's *built-in* agent types (Claude Code: Explore / Plan /
  general-purpose / fork) alongside generated `k-*` — what guardrails, model
  binding, and tools each actually receives, and whether the delegation
  log/routing hooks observe them. *(W4, feeds D4)*
- **P0.2** Declare support-matrix dimensions: plugin-/instruction-tier per vendor
  row; OS support stated (POSIX-only or Windows planned). *(W9, W10)*
- **P0.3** Inventory guardrail↔hook rule pairs → the INVARIANTS list, no checker
  yet. *(W5)*
- **P0.4** Declare the source/generated boundary (what `sync.py` owns, what may
  never be hand-edited) and pick the numeric caps for always-loaded artifacts —
  declaration only, checker in P1.7. *(W23)*

### Phase 1 — Cheap hardening of what exists (engineer, low effort)

- **P1.1** Hook survivability contract: bounded stdin handling, BOM normalization,
  `timeout` in generated wiring, contract in `hooks/README.md`, degradation tests
  for the missing paths, and regression tests that lock the intended malformed-input
  no-op behavior. *(W8)*
- **P1.2** Invariant canary in `meta/self_ci.py`, consuming the P0.3 list. *(W5)*
- **P1.3** Version cross-check in `release_check`: pyproject ↔ latest CHANGELOG
  entry. *(W7)*
- **P1.4** `akmon status` — observability only; mutable levels parked (D1). *(W14)*
- **P1.5** Execution-ledger convention in `_aitna/`: one appended line per
  completed dispatch; "after compaction trust the ledger and `git log`" clause
  in the orchestration guardrail. *(W20)*
- **P1.6** Shared diagnostic envelope (`severity/code/message/target/fix`, exit
  codes) as one module; adopt in `sync --check`, `verify.py`, `self_ci.py`;
  every finding carries a one-sentence fix. *(W22)*
- **P1.7** Boundary + caps checks in `self_ci`, consuming P0.4: generated files
  not hand-edited, always-loaded artifacts within the declared caps; extend to
  doc gardening (dead links, staleness) as the same sweep. *(W23, extends W5)*

### Phase 2 — Pipeline contracts (architect lock, then small text changes)

- **P2.1** Solution ladder + root-cause clause in `code-flow`, with the
  non-negotiables carved out. *(W11)*
- **P2.2** Review contract in `review-flow`: simplicity lens (five-tag
  vocabulary, read-only, severity by boundary/risk) **plus** the wave-2
  additions — two-verdict review (spec compliance ∥ implementation quality,
  material findings force fix + re-review) and reviewer-independence clauses
  ported verbatim. *(W12)*
- **P2.3** `akmon-defer:` semantics: ceiling **and** trigger required, canonical
  `TASKS.md` ID, grep harvest flags `no-trigger`. *(W6)*
- **P2.4** Delegation dispatch packet + report contract: packet fields, bounded
  status vocabulary (`DONE/DONE_WITH_CONCERNS/NEEDS_CONTEXT/BLOCKED`) with
  prescribed controller reactions; isolation question parked under D3. *(W17)*
- **P2.5** Context-hygiene contract for delegation: briefs/reports/review
  packages move as files, subagents return status + summary + paths; payload
  sizes measurable. *(W19)*
- **P2.6** Cost heuristics into routing policy: mid-tier floor for reviewers and
  prose-driven implementers, explicit model required in every dispatch, tier
  mapping stays generation-time data; outcome calibration deferred to the P3
  harness. *(W18)*
- **P2.7** Change-state lifecycle (architect pass first): delta semantics and an
  archive-merge closing step inside existing carriers; a compact change manifest
  linking task/design/ADR/D2/code owners; dependency invalidation marking
  downstream briefs stale. No new tree (§4). *(W21)*
- **P2.8** Design-session carrier *(wave 3)*: bind design-flow's
  concept-drafting step to the host's plan mode where available — the session
  drafts read-only, and the owner-approved plan file (Claude Code:
  `~/.claude/plans/` by default; the plans directory is configurable to a
  project path, which may point it straight at the repo) is promoted into
  `meta/design/` with a back-pointer instead of evaporating vendor-side. In
  agent-team ("tech lead") execution, the lead's approval of each teammate's
  plan is the same design-first gate at dispatch granularity, mapped onto the
  P2.4 packet. Instruction-tier fallback: the design concept file itself is
  the plan. Native-subagent reuse rides D4, not this item. *(W24)*

### Phase 3 — The strategic lever: behavioral evaluation (O5)

- **P3.1** Architect pass on the evaluation contract: arms, isolation checklist,
  pinned fixture consumer, metric axes (role/boundary compliance, delegation &
  routing, gate activation, correctness/safety, owner attention/tokens/time; LOC
  diagnostic only), repetitions, workspace retention. Wave-2 absorptions: the
  layered cost-tagged depth model (static always-on → bounded LLM judge on risk
  → statistical runs for promotions only), baseline-must-fail for guardrail
  authoring, the completeness/correctness/coherence/drift audit axes, and the
  per-vendor acceptance probe as the definition of a "delivered" matrix cell.
  *(W1, W3)*
- **P3.2** Harness in `meta/benchmarks/` + behavior gates with a control arm for
  the two cheapest claims first: commit guard stops a default-branch commit;
  delegation nudge changes delegation share (measurable from the existing
  delegation log). Grader unit-tested separately. Includes the D3 arm
  (fresh vs bounded inherited context) and first outcome data for W18
  calibration (turns/tokens/retries per tier). *(W1; feeds D3, W18)*
- **P3.3** Evidence classes wired into learn-loop PROMOTE — same architect pass
  as P3.1. *(W13)*
- **P3.4** Re-run the vendor capability matrix from experiment (closes N1):
  documented/delivered/advisory/enforced per cell; matrix kept as data consumed
  by `sync.py` with the README table generated from it; round-trip real-CLI
  smoke checks automated where a harness is cheaply installable. *(W2, W10)*

### Phase 4 — New surface, only after measurement exists (gated on Phase 3)

- **P4.1** SubagentStart guardrail injection — **only if** P0.1 reproduced the
  drift; scoped by matcher ("`k-*` already equipped"); effect verified by the P3
  harness. *(W4)*
- **P4.2** Claude Code plugin carrier: ADR, uninstall path, P1.3 check becomes
  mandatory. *(W15)*
- **P4.3** MCP transport for the standard; instruction-tier semantics from P0.2
  apply. *(W16)*
- **P4.4** Mutable enforcement levels — only if D1 is decided in favor; otherwise
  closed as rejected with the [pny/codex] 4.1 rationale. *(W14, D1)*

### Phase 5 — Polish (opportunistic, no gate)

Before/after examples of hook effect; after-install checklist for BOOTSTRAP;
statusline integration (extends P1.4); "enablers, not gates" framing sentence in
pipeline docs ([top3/claude] §2.2-4); rationalization tables as a guardrail
authoring idiom ([top3/claude] §1.2-9); independent-corroboration README
section — meaningful only once Phase 3 produces first-party numbers.

**Dependency spine:** P0.1 → P4.1 and → D4; P0.3 → P1.2; P0.4 → P1.7; P3.1 →
P3.2/P3.3 → P3.4 → Phase 4; P1.3 → P4.2; P2.4/P2.5/P2.6/P2.8 share one
architect pass (delegation/handoff contract); P2.7 has its own architect pass;
D3 resolves inside P3.2; D4 resolves per vendor from the P0.1 comparison arm
plus W18 outcome data. Phases 1–2 depend on Phase 0 only where noted and can
run in parallel with it.
