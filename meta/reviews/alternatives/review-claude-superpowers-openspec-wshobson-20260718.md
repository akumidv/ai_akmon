# Review — Superpowers, OpenSpec, wshobson/agents: ideas for akmon (2026-07-18)

> **Point-in-time review** (review role, findings snapshot). Deep pass over the
> top three of the six candidates ranked in
> [review-alternatives-20260718.md](review-alternatives-20260718.md). Clones in
> `.review/`: superpowers @ `d884ae0` (2026-07-02), OpenSpec @ `0a99f41`
> (2026-07-11), wshobson/agents @ `b6af371` (2026-07-14).
>
> Weakness IDs (W1–W16) reference
> [plan-akmon-from-alternatives-20260718.md](plan-akmon-from-alternatives-20260718.md).
> Candidate **new** weaknesses found here are numbered W17+ in §4.2 but are
> **not merged into the plan** — that waits for the owner walkthrough.

---

## 1. Superpowers (obra / Prime Radiant)

### 1.1. What it is

A complete development methodology as ~14 composable skills plus a session-start
bootstrap that forces skill invocation: brainstorm → design approval → worktree →
bite-sized plan → subagent-driven execution with per-task review → final
whole-branch review → finish. Delivered to ~10 harnesses, mostly via native
plugin marketplaces. This is the closest thing to akmon's *execution* discipline
in the wild — but it is a methodology-as-product, not a versioned per-project
standard: no layer ownership, no owner boundary, no decision records, no model
routing registry, no learn loop.

### 1.2. High-value ideas

1. **Two-verdict task review: spec compliance + code quality, separately.**
   (`skills/subagent-driven-development/SKILL.md`.) Every task is reviewed twice
   in one dispatch — "did it build what the spec says, nothing more" and "is it
   well built" — and *both* verdicts are required; a fix loop re-reviews until
   clean; a final whole-branch review runs once at the end on the most capable
   model. akmon's review role produces one blended verdict. Splitting spec
   compliance from quality catches over-building (extra `--json` flag) and
   under-building (missing progress reporting) that a single quality pass
   blurs. *(extends W12; role gap, not a new role)*

2. **Cost-aware model routing heuristics, stated as policy.** The "Model
   Selection" section is the best articulation of akmon's own goal function seen
   in any alternative: use the least powerful model per role; **"turn count
   beats token price"** — the cheapest models routinely take 2–3× the turns on
   multi-step work and cost *more* overall, so mid-tier is the floor for
   reviewers and prose-driven implementers, cheapest tier only for
   transcription-grade tasks; and **an omitted model silently inherits the
   expensive session model**, so dispatches must always name the model. akmon's
   `tools/model_routing/registry.json` maps roles to models but carries no such
   cost heuristics and no "explicit model required in every dispatch" rule.
   *(new — see W18)*

3. **File handoffs as a context-hygiene contract.** Everything pasted into a
   dispatch prompt or printed back by a subagent stays resident in the
   orchestrator's context and is re-read every turn. Superpowers moves all bulk
   artifacts as files: `task-brief` extracts one task from the plan to a file;
   the implementer writes a full report to a file and returns only status +
   commits + one-line summary; the reviewer gets three file paths, not pasted
   text; a real session's 42k-char dispatch (99% pasted history) is cited as
   the anti-pattern. Direct hit on akmon's token half of the goal function —
   akmon's delegation contract does not regulate this at all. *(new — W19)*

4. **A durable execution ledger that survives compaction.**
   Controllers that lost their place after compaction re-dispatched entire
   completed task sequences — named "the single most expensive failure
   observed". The rule: append one line per completed task to a scratch ledger
   file; after compaction trust the ledger and `git log` over recollection.
   akmon's D2 ledger tracks deferred *verification*; nothing tracks
   *execution progress* of an orchestrated session. `_aitna/` is the natural
   home. *(new — W20)*

5. **Skill TDD + session-level behavioral evals.** `writing-skills` applies
   RED-GREEN-REFACTOR to process documentation: run the pressure scenario
   *without* the skill and document the exact rationalizations (RED), write the
   skill against those specific violations (GREEN), close loopholes and
   re-verify (REFACTOR). "If you didn't watch an agent fail without the skill,
   you don't know if the skill teaches the right thing." The eval harness
   (superpowers-evals/drill) drives real tmux sessions and judges compliance
   with an LLM verifier. This is a third independent eval architecture after
   ponytail's two (behavior gates, agentic A/B) — and it adds the
   *baseline-must-fail* discipline to guardrail authoring itself. *(W1/O5)*

6. **A subagent status vocabulary with defined controller reactions.**
   `DONE / DONE_WITH_CONCERNS / NEEDS_CONTEXT / BLOCKED`, each with a
   prescribed response (add context and re-dispatch; escalate the model; split
   the task; escalate to the human) plus "never force the same model to retry
   without changes". akmon's delegation has no standard report contract, so
   every orchestrator improvises failure handling. *(new — W17)*

7. **Reviewer independence, stated negatively.** Never tell a reviewer what
   *not* to flag, never pre-rate severity in the dispatch ("treat as Minor at
   most"), never dismiss a finding because the plan mandates it — plan
   contradictions go to the human. akmon's clean-context k-auditor is the same
   instinct for gate audit; this phrasing extends it to every review dispatch
   and is worth porting verbatim into the delegation guardrails. *(extends W12)*

8. **Harness-integration acceptance test.** A new harness integration is real
   only if a clean session on the canonical prompt ("Let's make a react todo
   list") auto-triggers the bootstrap skill; manual file copies and per-session
   opt-ins are explicitly "not integrations" (`CLAUDE.md`). For akmon's vendor
   matrix this is the missing *definition of done* per cell: one canonical
   acceptance probe per vendor, transcript attached. Feeds directly into W2/P0.1
   probes. *(W2)*

9. **Rationalization tables as an enforcement idiom.** Both the bootstrap and
   `verification-before-completion` carry tables of observed evasions with
   counters ("Agent said success → verify independently"; "I'm confident →
   confidence ≠ evidence"). This is akmon's learn-loop CAPTURE step distilled
   into the artifact itself: guardrails engineered against *documented* failure
   modes, not hypothetical ones. Cheap idiom to adopt in guardrail authoring.
   *(supports W1/W13)*

### 1.3. Do not borrow

- **Universal mandatory TDD and worktrees** without risk-based scoping (already
  flagged in the landscape review) — akmon scopes discipline by archetype and
  risk, not unconditionally.
- **The "1% chance → MUST invoke" absolutism** of the bootstrap. It buys
  trigger reliability at a permanent token/attention tax and suppresses
  judgment; akmon's role pointers + forcing hooks are a more economical
  enforcement surface.
- **Methodology-as-product framing** — no versioned per-consumer contract, no
  owner boundary; the distribution model does not transfer.

---

## 2. OpenSpec (Fission-AI)

### 2.1. What it is

A lightweight spec-driven change lifecycle: `openspec/specs/` holds the current
truth as requirements + given/when/then scenarios; each unit of work is a
*change folder* (`proposal → delta specs → design → tasks`); archiving merges
the deltas back into the specs. A CLI (`openspec`) with a fully documented
machine-readable JSON contract drives 25+ tools. Philosophy: "enablers, not
gates" — the artifact chain orders context dependencies, it does not gate.

### 2.2. High-value ideas

1. **Delta specs: describe the diff, not the destination.** A change never
   rewrites a spec; it declares `ADDED / MODIFIED / REMOVED` requirements.
   This is what makes spec-driven work viable on brownfield code ("specify a
   change to a 50,000-line app without documenting the whole thing"). akmon's
   `meta/design/` docs are whole-document snapshots — nothing marks what a
   given piece of work *changes*, so design docs drift from reality silently.
   *(new — W21)*

2. **Archive-folds-into-truth lifecycle.** On completion, a change's deltas
   merge into the canonical specs and the folder moves to a dated archive —
   the loop *closes* and the specs describe the new reality. akmon has
   `meta/TASKS.md`, `meta/design/`, `meta/decisions/`, the D2 ledger — but no
   closing step that reconciles a finished task with the design docs it
   invalidated. This is the specs analog of akmon's learn loop
   (CAPTURE→…→PROPAGATE) and pairs naturally with it. *(W21)*

3. **A machine-readable diagnostic contract for tooling.**
   `docs/agent-contract.md` documents, per CLI command: one JSON document per
   invocation, a single shared diagnostic envelope
   (`severity / code / message / target / fix` — fix is *one actionable
   sentence*), a full catalog of `snake_case` diagnostic codes, and an
   exit-code table. akmon's `sync.py --check`, `verify.py`, `self_ci.py`
   speak human prose only; adopting one envelope with mandatory `fix` strings
   would make every akmon check consumable by agents and cheaper for the owner
   to act on. *(new — W22)*

4. **"Enablers, not gates" as explicit framing.** The dependency chain exists
   so the AI has the context it needs, not to force ceremony; any artifact is
   editable at any time; the honest tradeoff (discipline shifts to the human)
   is stated in the docs. akmon's pipelines are already iterative in spirit —
   borrowing the *framing sentence* for pipeline docs prevents them from
   reading as waterfall. *(cheap polish)*

5. **Stores: the planning layer as a repo of its own.** Cross-repo features
   get one change/one plan in a shared planning repo, consumed read-only by
   code repos. akmon's SHARED layer already versions the *standard*
   cross-project; stores extend the same move to *work in progress*. Not
   urgent, but the natural shape if akmon consumers ever need cross-repo
   features. *(deferred; note only)*

### 2.3. Do not borrow

- **The directory structure wholesale.** The landscape review's warning stands:
  `openspec/changes/` beside `meta/TASKS.md` + `meta/design/` + D2 would be a
  second source of truth. Adopt the *lifecycle semantics* (deltas, archive
  merge) into akmon's existing carriers, not the folders.
- **Requirements ceremony for every change.** OpenSpec itself concedes trivial
  fixes don't pay for the ceremony; akmon's risk-scoped gates already encode
  that judgment.

---

## 3. wshobson/agents

### 3.1. What it is

A multi-harness plugin marketplace: 94 plugins / 203 agents / 175 skills
authored once as Claude Code markdown under `plugins/` and delivered to five
harnesses by per-harness adapters that emit *native* artifacts (TOML for Codex,
permission blocks for OpenCode, …) — explicitly "not lowest-common-denominator
translations". The content catalog is not the interesting part for akmon; the
delivery engineering is.

### 3.2. High-value ideas

1. **The source/generated boundary as a stated invariant.** Invariant #1 of
   `ARCHITECTURE.md`: all authoring under `plugins/`; generated harness
   artifacts are gitignored; the only committed exceptions are thin registries
   that *point at* source; never hand-edit generated files. akmon's `sync.py`
   generates agent files and wiring, but the boundary (what is source, what is
   generated, what may never be hand-edited) is nowhere stated as an invariant
   or checked. Cheap to declare + one self_ci check. *(new — W23)*

2. **Capability matrix as code, docs generated from it.**
   `tools/adapters/capabilities.py` is the single source of the per-harness
   capability matrix; `docs/harnesses.md` opens with "This file mirrors the
   capability matrix in capabilities.py. Edit there; regenerate via `make
   docs`." Every adapter consumes the same matrix. This is the executable form
   of akmon's vendor-support table: data consumed by `sync.py`, README table
   generated from it — ❓ cells become impossible to leave stale. *(W2/W10)*

3. **Doc gardening as a CI gate.** Three mechanical gates — `make validate`
   (structure), `make garden` (drift: dead links, stale generated artifacts,
   oversize skills, marketplace orphans), `make test` — and the convention
   that **every finding ships a concrete fix string** (Invariant #4). akmon's
   `self_ci.py` covers structure/tests; a gardener pass (dead links across
   guardrails/pipelines/README, staleness, size caps) extends the W5 canary
   idea from rule drift to *documentation* drift. *(extends W5)*

4. **Layered eval depth: static → LLM judge → Monte Carlo.** `plugin-eval`
   scores artifacts in three layers with explicit cost tags (static: <2s,
   free; judge: ~30s, 4 calls; Monte Carlo: 50–100 runs with Wilson/bootstrap
   confidence intervals and Cohen's κ), a `--threshold` CI gate, and depth
   presets (`quick/standard/deep`). For akmon's P3/O5 this is the missing
   *cost model*: cheap deterministic checks always-on, LLM judging on demand,
   statistical runs reserved for promotions — the eval ladder priced in the
   same currency as the goal function. *(W1/O5)*

5. **Progressive-disclosure caps as concrete numbers.** Context files ≤150
   lines / ~500 tokens; skill bodies ≤8 KB (a real vendor hard cap, respected
   by the adapter with `references/` overflow); detail loaded on demand, never
   pre-injected. akmon preaches token economy but has no numeric caps and no
   check; caps are cheap to adopt in self_ci and directly serve the goal
   function. *(extends W23 / token half of goal function)*

6. **Round-trip real-CLI smoke tests in CI.** The CI workflow installs two of
   the target harnesses (OpenCode, Gemini) and exercises the generated
   artifacts against the real CLIs on every PR. For akmon's vendor matrix this
   is the automation of "delivered" cells — the same probe P0.1 does manually,
   made repeatable. *(W2, feeds P3.4)*

7. **Model tiers as adapter-mapped data.** Tier aliases in frontmatter
   (`opus/sonnet/haiku/inherit`, tier 0 for longest-horizon work), mapped to
   native model IDs per harness at generation time. Convergent with akmon's
   routing registry; the portable detail is *mapping at generation time*, so
   one routing policy survives vendor renames. *(supports W18)*

### 3.3. Do not borrow

- **Catalog scale as a goal.** 94 plugins / 203 agents is an adoption play;
  every artifact is a liability under akmon's goal function. (Same verdict as
  ponytail's 20 adapters.)
- **Five-harness adapter framework now.** The *invariants* transfer; the
  framework itself is justified only by their catalog breadth. akmon stays
  deep on Claude/Codex + instruction-tier (per P0.2).

---

## 4. Cross-alternative synthesis

### 4.1. Convergence across four sources

With ponytail, four independent mature projects now show the same picture:

- **Everyone built eval infrastructure; akmon has none.** Ponytail: behavior
  gates + agentic A/B with a control arm. Superpowers: skill-TDD
  (baseline-must-fail) + LLM-verified session evals. wshobson: layered
  static/judge/Monte-Carlo scoring with confidence intervals. Three different
  architectures, one lesson — W1 is confirmed as akmon's largest gap, and the
  three architectures are *complementary layers*, not competitors: cheap
  deterministic gates (ponytail) → session compliance (superpowers) →
  statistical certification (wshobson), each priced.
- **Delivery honesty is an executable artifact.** Ponytail's tier tags,
  wshobson's capability matrix as code + real-CLI round-trips, Superpowers'
  acceptance test per harness — together they turn akmon's ❓ cells into:
  matrix as data, one canonical probe per vendor, CI round-trip where cheap.
  *(W2/W10)*
- **Single-source + generated variants** is universal (ponytail's mode
  filtering from one SKILL.md, wshobson's adapters, OpenSpec's one contract).
  akmon's principle is validated; what's missing is stating and checking the
  boundary (W23).

### 4.2. Candidate new weaknesses (NOT merged into the plan)

For the owner walkthrough; numbering continues the plan's W-series:

| ID | Weakness | Source | Suggested phase |
|---|---|---|---|
| W17 | No subagent report contract: no status vocabulary (`DONE/DONE_WITH_CONCERNS/NEEDS_CONTEXT/BLOCKED`), no defined controller reactions | Superpowers 1.2-6 | Phase 2 (pipeline contracts) |
| W18 | Model routing has no cost heuristics ("turn count beats token price", mid-tier floor for reviewers) and no "explicit model per dispatch" rule | Superpowers 1.2-2, wshobson 3.2-7 | Phase 2 |
| W19 | No context-hygiene contract for delegation: bulk artifacts pasted into dispatches/reports instead of moved as files | Superpowers 1.2-3 | Phase 2 |
| W20 | No execution-progress ledger surviving compaction; orchestrator re-dispatch of completed work is unguarded | Superpowers 1.2-4 | Phase 1 (cheap: `_aitna/` convention) |
| W21 | Design docs have no change lifecycle: no delta records, no archive-merge step reconciling finished work with `meta/design/` | OpenSpec 2.2-1/2 | Phase 2 (architect pass first) |
| W22 | akmon tooling (`sync --check`, `verify`, `self_ci`) emits prose only: no shared diagnostic envelope, no machine-readable `fix` strings | OpenSpec 2.2-3 | Phase 1–2 |
| W23 | Source/generated boundary not declared or checked; no numeric progressive-disclosure caps | wshobson 3.2-1/5 | Phase 0 (declare) + Phase 1 (check) |

### 4.3. Suggested plan impacts (not applied)

- **P3.1 (eval contract)** should absorb three additions: the layered
  cost-tagged depth model (wshobson), baseline-must-fail for guardrail
  authoring (Superpowers), and the per-vendor acceptance probe as the
  definition of a "delivered" matrix cell (Superpowers + wshobson round-trip).
- **Phase 2** grows candidates W17–W19 (delegation/report/context contracts) —
  they are textual contracts like P2.1–P2.3, same cost class.
- **P0.2** should declare the source/generated boundary (W23) alongside tiers.
- **Two-verdict review (1.2-1) and reviewer-independence clauses (1.2-7)**
  slot into the existing P2.2 rather than new items.

Nothing above modifies the plan file; register rows for the three alternatives
were appended to its §1 as the plan itself prescribes.

---

## 5. Cross-review: comparison with the Codex review

An independent Codex review of the same trio exists:
[review-codex-akmon-top-3-20260718.md](review-codex-akmon-top-3-20260718.md).
Sections 1–4 above are unchanged; this section only compares. Codex organizes
its review around six akmon gaps and a prioritized pilot table; this review
organizes around per-project ideas and candidate W-IDs — the two structures
are complementary, and the mapping is given in §5.4.

### 5.1. Where the reviews independently converge

Strong signal — two independent passes over the same sources landed on the
same conclusions:

- **Same trio, same rationale.** Codex independently frames the selection as
  "the smallest set covering three different failure surfaces" (behavior /
  change-state drift / delivery certification) — the same division as §§1–3.
- **No new top-level roles.** Both reviews explicitly conclude the missing
  pieces are *contracts around the roles* (Codex: "a handoff protocol, not a
  role"), rejecting persona catalogs.
- **Two-verdict review** (spec compliance + implementation quality, separately,
  with mandatory re-review) — §1.2-1 ↔ Codex's dispatch/review handoff.
- **Cost heuristics over token price** ("turn count beats token price",
  explicit model per dispatch, outcome-based calibration) — §1.2-2/W18 ↔
  Codex gap 6 and its P1 pilot.
- **Dispatch packet + bounded status vocabulary** — W17/W19 ↔ Codex's
  "one normative dispatch packet, bounded status vocabulary".
- **Baseline-must-fail behavioral evals** as the top priority — §1.2-5/W1 ↔
  Codex P0 finding #1 (behavioral A/B with fresh contexts).
- **Capability matrix as machine-owned data** with generated docs, plus
  **live round-trip certification** per vendor path — §3.2-2/-6 ↔ Codex P0
  finding #2 and its vendor-capability registry
  (`native/emulated/degraded/unsupported/unverified` + evidence class).
- **Layered eval depths with risk gates** (static always-on → semantic on
  risk → statistical for release candidates) — §3.2-4 ↔ Codex's "three depths".
- **Do-not-copy overlap**: no `openspec/` tree as a second source of truth; no
  universal TDD/worktrees; catalog scale is not coverage; LLM-judge scores
  never replace deterministic invariants or owner decisions.

### 5.2. What Codex adds — fold into the owner walkthrough

1. **Dependency invalidation as an explicit contract.** A changed upstream
   design/spec should mark dependent task briefs and audit packs *stale*
   (metric: invalidated artifacts caught, escaped stale assumptions). This
   review covered delta specs and archive-merge (W21) but missed downstream
   invalidation — a genuine extension of **W21**.
2. **Change-state projection across all carriers, not just design docs.**
   Codex generalizes the drift problem with local evidence: backlog entries
   sitting `code-complete & D2-pending` prove that task, design, ADR, D2,
   code, and tests fragment change state. Its proposal — a compact *change
   manifest* that links the existing canonical owners without duplicating
   them — is a broader (and better-anchored) framing of **W21**.
3. **Verification axes: completeness / correctness / coherence / drift.**
   Borrowed from OpenSpec's verify vocabulary and missed here entirely: add
   these axes to the audit yardstick so findings classify by axis (metric:
   false-ready rate). Slots into the audit/eval work (P3.x).
4. **Engineer-verification asymmetry.** The engineer gate audit is
   signal-triggered while review/design verification is structural, so
   successful worker reports carry too much trust. Sharper diagnosis of the
   gap behind two-verdict review — extends **W12/W17**.
5. **Resolved-graph gate packs.** OpenSpec's action-scoped instruction
   generation mapped to akmon: generate the auditor's pack from the resolved
   dependency graph (links + selected facts), measuring pack tokens and audit
   precision.
6. **Pilot acceptance criteria per finding.** Codex's consolidated table
   attaches a measurable acceptance criterion to every adaptation, and its
   six-step experiment sequence ends with an architect decision recording
   *rejected* mechanisms and revisit conditions. This discipline should apply
   to every plan item the walkthrough accepts.
7. **A cheaper forked-context control arm.** Absolute fresh-context isolation
   should be A/B-tested against bounded inherited context — same control-arm
   instinct the Codex ponytail review contributed (P4.1 heritage).

### 5.3. Complements — covered here, absent in the Codex review

- **W20 execution ledger surviving compaction** (Superpowers' "single most
  expensive failure") — no Codex counterpart.
- **W22 machine-readable diagnostic envelope** for akmon tooling
  (`severity/code/message/target/fix`, exit-code table) — Codex does not
  cover OpenSpec's agent contract.
- **W23 source/generated boundary as a declared, checked invariant** and the
  concrete numeric caps (150 lines / 500 tokens / 8 KB) — Codex has the
  `garden`-style sweep but not the boundary declaration or the numbers.
- **Reviewer-independence clauses** stated negatively (§1.2-7) and
  **rationalization tables** as an enforcement idiom (§1.2-9) — portable
  verbatim; Codex has independent review but not these authoring idioms.
- **Harness acceptance test as the definition of a "delivered" matrix cell**
  (§1.2-8) — Codex requires transcript evidence but not the one-canonical-
  probe-per-vendor formulation.

One framing divergence, no conflict: §2.2-2 calls archive-merge the "specs
analog" of the learn loop that *pairs* with it; Codex warns archive history
is *not a substitute* for CAPTURE→DISTILL→PROMOTE→PROPAGATE. Both hold —
adopt the lifecycle semantics, keep the learn loop as the owner of lessons.

### 5.4. Codex gaps ↔ W-series mapping

| Codex gap (its §"weak spots") | This review | Status |
|---|---|---|
| 1. Policy behavior weakly evaluated | W1/O5 (§1.2-5, §3.2-4) | converges |
| 2. Routing but no complete task protocol | W17 + W19 (§1.2-3/-6) | converges |
| 3. Engineer verification less independent | extends W12 (§1.2-1/-7) | Codex sharper |
| 4. Change state fragmented | W21 (§2.2-1/-2) | Codex broader (manifest + invalidation) |
| 5. Vendor delivery evidence incomplete | W2/W10 (§3.2-2/-6) | converges |
| 6. Token economics not outcome-calibrated | W18 (§1.2-2, §3.2-7) | converges; Codex adds portfolio view |

Net: six of six Codex gaps land on existing W-IDs — no new W-number is
needed; the walkthrough should instead **broaden W21** (manifest +
invalidation), **sharpen W12** (engineer asymmetry), and adopt Codex's
per-pilot acceptance criteria for every accepted item. Nothing here modifies
the plan file.
