# Design — model routing: task-kind matrix, capability ladder, session-init binding

> **Status: locked — owner verified (D2), decisions recorded in
> [ADR 0004](../decisions/0004-model-routing-capability-tiers.md).
> Built — all three phases (§8) are code-complete**: registry + init tool
> (`akmon/tools/model_routing/`), the SessionStart status-line hook
> (`hooks/model-routing.py`) and the delegation-log hook (`hooks/delegation-log.py`)
> wired by `sync.py`, the §6 doc edits landed, and alphavar consumed (init run —
> generated `k-*` agents supersede the hand-written set; project overlay
> `_aitna/model-routing.json` carries the alphavar brief extras; local config/log
> gitignored). **Implementation owner-verified (D2) — C10 closed.** Remaining follow-ups
> live as their own tasks in akmon's backlog: statistics digest (C13) —
> [TASKS.md](../TASKS.md). Codex hook payload compatibility was closed in C12; the
> in-the-moment delegation nudge in C14.
>
> **Target layer: akmon (SHARED).** This is a mechanism of the standard itself, so all
> artifacts land in the `ai_akmon` submodule (`_aitna/akmon/`); alphavar is the first
> consumer. Work therefore produces **two commits in two repos** — the akmon change,
> then the submodule-pin bump here (see memory `akmon-edits-go-to-submodule`).

## 1. Problem and requirements

Every session currently runs on one model that does everything — decomposition, deep
reasoning, and mechanical edits alike. That burns the top-tier model on boilerplate and
re-consumes the orchestrator's context on work a cheap delegate could isolate. D4 already
names token economy a first-class concern; this design gives it a routing mechanism.

Owner requirements:

1. **The already-running agent solves the task** — the main session (whatever model the
   user picked) is the orchestrator; no separate "manager" process.
2. **At session start the agent can see which models are available** in its harness.
3. **Models are bound by hierarchy** — from recorded knowledge of model boundaries and
   capabilities, not ad-hoc judgment per session.
4. **Task kinds are bound to models as subagents** — delegation is by kind of work, and
   the binding is explicit data, not the orchestrator's in-the-moment judgment.
5. **Initialization is maximally code** — deterministic scripts and hooks, not prose the
   agent re-derives each session (D4).
6. **Cross-vendor review is good practice** — reviewing architecture decisions and code
   with an independent model (e.g. Codex) is offered to the user at session
   initialization, opt-in.
7. **Binding is automatic and relative to the orchestrating model** — models change;
   the routing table is *computed* from the model the session runs on, so a model
   release costs at most a one-line data edit (usually none, thanks to aliases).
8. **Model/subagent switches are visible at code cost, not token cost** — delegation is
   logged by hooks, not narrated by the model.
9. **The orchestrating model is displayed, with a corridor warning** — the session runs
   on whatever the user launched; the status line names it, and the hook warns when it
   leaves the healthy corridor (§3): below the orchestration floor (too weak — degrades
   everything downstream) or on the auditor's reserved top rung (wasteful).
10. **Subagent models follow the live orchestrator** — detected from the transcript at
    session start and after a mid-session `/model` switch; the orchestrator itself is
    never overridden, only detected (§3).
11. **Owner-facing warnings reach the owner.** `additionalContext` reaches only the
    model; the owner never sees it in the host UI. Anything addressed to the owner — the
    init instruction, corridor and context-pressure warnings, the rebind notice — must
    also go out as `systemMessage` (UI-visible). A warning only the model sees fails
    this requirement.
12. **Context pressure is detected** (§12) — the hook warns when the session's
    context-window fill crosses recorded thresholds, before quality degrades or a forced
    compaction lands mid-task.

## 2. Vocabulary — tiers, and the task-kind matrix that feeds them

Keystone is LLM-agnostic, so the routing vocabulary is abstract **capability tiers**;
concrete model names live only in local discovery/config, not in the committed standard.

| Tier | Operation | Who runs it |
|---|---|---|
| **orchestrator** | decompose, route, integrate results, dialogue with the owner | the main session — whatever model the user runs |
| **reasoner** | load-bearing synthesis: architecture forks, contested decisions, complex debugging, quant math derivation | top rung of the ladder (§3), as a subagent |
| **worker** | delegable realization: exploration, summaries, mechanical edits, tests-under-spec, doc-sync | cheapest adequate rung, as a subagent |
| **auditor** | independent review of architecture decisions and code | a *different vendor's* model (e.g. Codex), opt-in |

Tiers are only the vocabulary. The **binding surface is the task-kind matrix** — a finite,
named list of operations, each mapped to a tier. It lives in the registry as data
(requirement 4); this table is its normative content:

| Task kind | Tier | Notes |
|---|---|---|
| `explore-search` | worker | find where X lives in code/docs; fan-out reads |
| `summarize` | worker | condense files/docs/logs to a brief |
| `mech-edit` | worker | renames, sweeps, formatting, behaviour-preserving moves |
| `test-scaffold` | worker | test skeletons and fixtures from a stated spec |
| `doc-sync` | worker | propagate an already-decided fact across docs |
| `validate-loop` | worker | run project gates (tests/lint/verify/sync), parse output, apply *minimal mechanical* fixes, re-run to green; escalate non-mechanical diagnosis |
| `implement-under-spec` | worker (mid rung) | code against a decided contract; no open design |
| `debug-deep` | reasoner | multi-cause, cross-boundary failure analysis |
| `design-fork` | reasoner | drafting options for a load-bearing decision |
| `quant-derivation` | reasoner | pricing/math derivations (quant profile work) |
| `independent-review` | second-opinion | advisory cross-vendor review at verify gates |
| `audit` | auditor | clean-context audit of a whole gate's material |
| decompose / route / synthesize / owner dialogue | orchestrator | **never delegated** |

Two policies make the matrix bite:

- **Delegation is the default.** Every kind in the matrix has a named delegate; the
  orchestrator keeps only its own row. The question is not "is this worth delegating?"
  but "which row is this?" — mid-band work no longer falls to the orchestrator by inertia.
- **Escalation ladder — start cheap, escalate on signal.** A delegable sub-task starts at
  the cheapest adequate rung; it moves up the ladder only on failure signals: tests red
  twice, the worker flags uncertainty, a contested fork emerges mid-task. Escalation is
  rare for true mechanics, so the cheap tier's ceiling rarely binds.

Delegation has two independent benefits — cheaper tokens for mechanics, and **context
isolation**: a worker's exploration does not enter the orchestrator's window and is not
re-read on every subsequent turn. The second benefit applies even when tiers share a model.

Floor rule (guardrail line, §6): **do not burn the orchestrator or reasoner tier on
mechanical work; route by task kind, not by the whole task's prestige.**

## 3. Binding — semantic policy + local discovery

Requirement 7 rules out static per-model tables. The committed registry records a
**semantic selection policy** per vendor, not a current model list: local discovery supplies
the concrete aliases in weakest→strongest order, and the policy selects lowest/mid/highest
rungs from that local list. Model churn therefore updates only gitignored local config, not
the shared standard.

The tier→model binding is a **pure function of (semantic policy, local available list,
orchestrator model)**:

- **reasoner** = the top rung *available in the harness*. If the orchestrator *is* the
  top rung, reasoner work still runs as a subagent of the same model — the
  context-isolation benefit persists.
- **worker** = the lowest available rung; the `mid` rung serves `implement-under-spec`.
- **escalation path** = the rungs between worker and reasoner, in ladder order.
- **second-opinion** = a different vendor's entry, independent of the local model list.
- **orchestrator** = whatever the user launched — the binding never overrides it, but
  (requirement 9) the hook warns when it leaves the **healthy corridor**
  `floor ≤ orchestrator < top`:
  - **below the floor** (`orchestrator_floor`, a *named* alias — anthropic: `opus`):
    too weak — orchestration is decomposition and synthesis, the one place a weak model
    degrades everything downstream; suggest `/model` up. Advisory: the auditor's
    level verdict (§9.2) stays the authoritative, evidence-based check.
  - **on the top rung while the floor sits lower**: wasteful — the top rung is the
    auditor's reserved tier (§9.3); orchestration doesn't need it; suggest `/model`
    down to the floor.
  - **degenerate collapse, no warning:** when the ladder tops out at the floor (e.g. no
    `fable` locally — `available` ends at `opus`), `floor == top`, both conditions go
    silent, and orchestrator = reasoner = auditor = the floor. That is the accepted
    degraded mode, not an anomaly.
  - a floor alias absent from the local ladder disables the corridor (nothing to rank
    against — only the existing unknown-orchestrator warning remains); a vendor may keep
    the relative `"highest"` floor (openai does), which reproduces the pre-corridor
    below-top warning and never fires the wasteful arm.

If discovery is unavailable, the binding uses semantic fallback labels (`worker`, `mid`,
`strongest`) and warns. File-backed generated agents omit concrete `model:` frontmatter in
that mode instead of pretending semantic labels are valid vendor model ids.

**Orchestrator detection is transcript-driven** (the model the main chain actually ran on,
read as code — no owner action per session after the one-time setup):

1. the hook reads the session transcript (`transcript_path` in its payload), which records
   `message.model` per turn; it takes the **last main-chain** assistant message (sidechain =
   subagent turns are skipped so a delegate's model never masquerades as the orchestrator's)
   and maps the concrete id to an alias — pure code;
2. when the detected alias differs from the recorded orchestrator — a session launched on a
   different model, or a mid-session `/model` switch — the hook recomputes the binding and
   **regenerates the `k-*` defs** so subagents follow the live model. SessionStart carries it
   plus the status line; **UserPromptSubmit** re-runs the same check each turn (silent unless a
   switch just landed), which is what makes a mid-session `/model` propagate to delegates;
3. the orchestrator itself is **never overridden** — it is the owner's explicit choice; the
   hook only detects it. Detection lags a `/model` switch by one turn (the new model appears in
   the transcript on the next assistant message) and falls back to harness settings / the
   recorded config when the transcript names no model yet (a fresh session's first turn). The
   status line keeps a self-check as the belt-and-suspenders fallback. **Per-user by
   construction:** the `model:` frontmatter tracks the local orchestrator, so the generated
   `k-*` defs are gitignored and regenerated, not committed (they would otherwise churn across
   users/models).

> **First-run boundary.** Only the one-time setup is explicit — the owner runs `init.py` once
> to record the `available` ladder and the second-opinion opt-in (the hook needs the ladder to
> map ids → aliases). Thereafter the orchestrator is auto-detected every session; a model
> release or a `/model` switch costs zero owner action.

## 4. Mechanism — akmon components

### 4.1 Registry (data) — `_aitna/akmon/tools/model_routing/registry.json`

The single owner of model-selection policy *and* task-kind knowledge (requirements 3 + 4):

```json
{
  "anthropic": {
    "selection_policy": {
      "available_order": "weakest-to-strongest",
      "worker": "lowest",
      "mid": "next-after-worker",
      "reasoner": "highest",
      "orchestrator_floor": "highest"
    },
    "second_opinion": {"cli": "claude", "invoke": "claude -p --output-format text", "report_dir": ".codex/second-opinion/"},
    "semantic_fallback": {"worker": "worker", "mid": "mid", "reasoner": "strongest", "orchestrator": "strongest"}
  },
  "openai": {
    "selection_policy": {"available_order": "weakest-to-strongest", "worker": "lowest", "mid": "next-after-worker", "reasoner": "highest", "orchestrator_floor": "highest"},
    "second_opinion": {"cli": "codex", "invoke": "codex exec", "report_dir": ".claude/second-opinion/"},
    "semantic_fallback": {"worker": "worker", "mid": "mid", "reasoner": "strongest", "orchestrator": "strongest"}
  },
  "task_kinds": {
    "explore-search": {"tier": "worker"},
    "summarize": {"tier": "worker"},
    "mech-edit": {"tier": "worker"},
    "test-scaffold": {"tier": "worker"},
    "doc-sync": {"tier": "worker"},
    "validate-loop": {"tier": "worker"},
    "implement-under-spec": {"tier": "worker", "rung": "mid"},
    "debug-deep": {"tier": "reasoner"},
    "design-fork": {"tier": "reasoner"},
    "quant-derivation": {"tier": "reasoner"},
    "independent-review": {"tier": "second-opinion"}
  }
}
```

A project may overlay this with a local override file (same shape, deep-merged) for
project-specific kinds or a pinned dated id when behaviour must be frozen.

### 4.2 Init tool (code) — `_aitna/akmon/tools/model_routing/`

Run as `python _aitna/akmon/tools/model_routing/init.py [--orchestrator <alias>]
[--available <ids>] [--second-opinion on|off]` (stdlib-only, idempotent):

1. Resolves the orchestrator (flag from the agent — only it sees its harness — else the
   settings default) and the available models.
2. Computes the tier→model binding from the semantic policy (§3), local available list,
   and the task-kind matrix.
3. Emits generated artifacts (banner: *generated — edit registry/config, not this file*):
   - `.claude/agents/k-*.md` — subagent definitions with concrete `model:` frontmatter only
     when local discovery / `--available` provides aliases, plus a role brief carrying the
     task kinds each serves; includes `k-auditor` for the auditor tier. **Gitignored and regenerated**
     (the model is per-user; §3), by init here and by the hook each time the orchestrator
     moves;
   - `.claude/model-routing.local.json` — the resolved binding, second-opinion opt-in,
     registry hash for staleness detection (gitignored — per-user/per-machine, like `.env`).

### 4.3 SessionStart + UserPromptSubmit hook (code) — `_aitna/akmon/hooks/model-routing.py`

Wired beside the existing `session-start-agent.py`, by `bin/sync.py` through the same
adapter contract (`claude_adapter` / `codex_adapter`). One entrypoint, two events: it runs on
**SessionStart** (the status line below) and on **UserPromptSubmit** (per-turn orchestrator
re-detection + rebind, silent unless a `/model` switch just landed). Both first apply the
transcript detection of §3 — detect the live orchestrator, and rebind the `k-*` defs when it
moved — before producing their output:

- **Config present and fresh** (registry hash matches, orchestrator matches settings) →
  inject one status line: `model routing: vendor=openai · orchestrator=<local-top> ·
  reasoner=<local-top> · worker=<local-low> · auditor=<local-high> · second-opinion=claude(on)`. Zero questions,
  near-zero tokens. If the orchestrator leaves the healthy corridor (§3), the line gains
  a warning:
  `⚠ orchestrator=<below-floor> is below the orchestration floor (<floor>) — consider /model up`
  or
  `⚠ orchestrator=<top> runs on the auditor's reserved top rung — consider /model down to <floor>`
  (requirement 9; advice only, the user's choice stands).
- **Config missing or stale** → inject the init instruction: run the tool, and ask the
  owner two questions — (a) confirm the proposed binding, (b) enable second-opinion
  review (requirement 6).

**Delivery — two channels (requirement 11).** `hookSpecificOutput.additionalContext` is
injected into the *model's* context only; the host UI does not show it to the owner.
Everything owner-addressed — the init instruction, the corridor warning, the mid-session
rebind notice, the context-pressure warning (§12) — is therefore *also* returned as the
top-level `systemMessage` (UI-visible; the claude adapter already carries the field, same
idiom as C21's delegation indication). The steady-state status line stays context-only so
the UI is not noisy when nothing needs the owner's attention.

Same rule-plus-hook split akmon already uses (commit guard, role declaration).

### 4.4 Routing observability (code) — delegation log at zero token cost

Requirement 8. A **PreToolUse hook on the subagent tool** (`Agent`/`Task` matcher, wired
like the guards) appends one line per delegation to a local log
(`.claude/model-routing.log`): timestamp, task kind/tier, resolved model, description.
This is a local process in milliseconds and **consumes no model tokens** — nothing is
injected into context; the harness UI already shows subagent calls live. The model never
narrates a switch.

On demand — the owner asks in chat (e.g. "статистика работы") — a **statistics digest**
runs **in a subagent** (a `k-*` reporter, not the orchestrator, so parsing the transcript
and the log costs the orchestrator no context). It parses the session transcript (JSONL)
plus the delegation log and reports:

- **subagent / tier stats** — how many delegations, by task kind/tier and resolved model
  (from the log);
- **tokens spent per role/tier** — attributed from the transcript's per-message usage;
- **remaining budget** — session and week, **queried from the Claude API** (rate-limit /
  usage response, not memory — the exact field is verified against the API at
  implementation, per "verify against reality");
- **learn-loop recommendations** — a quick pass over the session proposing what to persist
  to `memory/` or draft as a skill/tool. This **feeds the learn loop**
  ([memory-distill](../../pipelines/memory-distill.md)) and **nothing is persisted
  without the owner's explicit confirmation**.

It stays token-efficient: a digest goes to chat, the full report to a file, entering
context only on request. The digest is the on-demand counterpart to the zero-token log
above. Scoped as its own task — see [akmon TASKS.md](../akmon/meta/TASKS.md) **C13**.

### 4.5 Pipeline tier annotations (docs — one line per step)

Routing anchors in **process steps**, not in the orchestrator's memory. Each pipeline
step that has a natural delegate gets a one-line tier annotation:

- **review-flow:** *Decompose*/*Measure* evidence fan-out → `worker`
  (`explore-search`, `summarize`); adversarial verification of ranked findings →
  `reasoner` (+ `second-opinion` when enabled).
- **code-flow:** *Implement* mechanical sub-steps → `worker` (`mech-edit`,
  `implement-under-spec`); *Test* scaffolding → `worker` (`test-scaffold`); *Verify*
  gate → `reasoner` review + `second-opinion` advisory.
- **design-flow:** *Survey* fan-out → `worker` (`explore-search`); *Design* option
  drafting on load-bearing forks → `reasoner` (`design-fork`); *Align* gate →
  `second-opinion` advisory to the owner.

### 4.6 Second-opinion protocol

When enabled in config, the orchestrator calls the external vendor at the existing
**verify gates** — design-flow *Align* for architecture decisions, code-flow step 5
*Verify* for code — via the registry-recorded invocation. The channel is the vendor's
**CLI in non-interactive mode** (`codex exec "<prompt>"` for Claude-led sessions,
`claude -p --output-format text "<prompt>"` for Codex-led sessions); a plugin command can
replace it later — it is registry data. Note: akmon's `codex_adapter.py`/`codex-hook.py`
are the *reverse* direction (akmon guardrails running inside a Codex session), not this
channel.

**Delivery — the opinion always surfaces in chat** (unlike routing switches, which are a
silent log): the full report is written to a file
(`.claude/second-opinion/<gate>-<n>.md`); the chat gets a **digest** — verdict, the
points where the second opinion *disagrees* with the orchestrator's analysis, and the
file link; the call itself is recorded by the delegation-log hook (§4.4). Token cost is
bounded: a digest per gate, opt-in only; the full report enters context only on request.

The external review is *advisory input to the owner's verification*, never a replacement
for D2: it widens what the owner sees, it does not sign off. Tiers change who *drafts*,
never who *decides*.

## 5. Session flow (end to end)

```
SessionStart hook (code)
├─ config fresh → status line injected → agent self-checks orchestrator line → work starts
└─ config missing/stale
   → agent states its model + available models (its harness knowledge)
   → agent runs init tool → binding computed from ladder + matrix
   → agent asks owner: confirm binding? enable second-opinion?
   → tool writes config + generated subagents → work starts
During work (orchestrator):
├─ sub-task matches a matrix row  → Agent(<delegate>)   [default path; hook logs it]
│    └─ failure signal            → escalate one rung up the ladder
├─ gate-pack audit + trigger fires → Agent(k-auditor, gate-pack)
├─ verify gate + opt-in on        → /codex:review (advisory → owner)
└─ decompose / synthesize / owner dialogue → stays in main session
```

## 6. Keystone doc integration (lands with the mechanism)

- **MODEL.md** — a capability-tier section: the tier vocabulary (adding `auditor` tier,
  renamed from `synthesizer` in V2) and the matrix's normative table (§2), binding to the
  existing cognitive-operation axis.
- **roles/*.md** — one default-tier line per triad role (review fans out to workers,
  architect drafts forks on reasoner, engineer routes mechanics to workers).
- **guardrails/_common.md** — the floor rule (§2).
- **pipelines/{review,code,design}-flow.md** — the step annotations (§4.5).

## 7. Alternatives considered / rejected branches

- **Model names in role docs / an akmon profile** — rejected: violates akmon's
  LLM-agnosticism; names drift with every release. *Revisit-if:* never for names.
- **Prose-only skill the agent re-reads each session** — rejected: token burn every
  session, non-deterministic application; contradicts requirement 5 and D4.
- **Two polar tiers only (reasoner/worker), routing by orchestrator judgment** —
  rejected: mid-band work (implement-under-spec, exploration, summaries) is polar to
  neither, defaults to the orchestrator, and the delegation rate stays low. Replaced by
  the task-kind matrix + delegation-as-default. *Revisit-if:* the matrix rows prove
  indistinguishable in practice.
- **Per-orchestrator-model binding tables in the registry** — rejected: N models × M
  tiers duplicates one fact many times and drifts. Semantic policy + local discovery
  states the selection rule once without committing volatile aliases (requirement 7).
- **Numeric complexity scoring (points for ambiguity/blast-radius → score bands →
  models)** — rejected: the scores are still the orchestrator's judgment, plus ceremony;
  a named task-kind list is checkable, a score is not.
- **Fully automatic init, no user questions** — rejected: owner explicitly wants the
  init-time confirmation (binding + second-opinion). Costs one exchange, only when
  config is missing/stale.
- **Ask the user every session** — softened: steady state is a status line (silence =
  keep); the question is asked at first init or on staleness. Open point §8.2.
- **Model narrates every switch in chat** — rejected for the steady state: tens of
  tokens per delegation and easy to forget; the PreToolUse log hook (§4.4) reports the
  same fact at zero token cost. *Revisit-if:* the owner wants in-chat visibility beyond
  the harness UI.
- **Hand-written `.claude/agents/` files, no tool** — rejected as the end state (drifts
  from the registry, per-vendor duplication), but **accepted as the bootstrap** (§8
  phasing) to validate matrix rows before building the generator. V2 note: once the `auditor`
  tier and `audit` task kind are stable, they become part of the code-generated set.
- **LOCAL-first phasing (build in alphavar, promote later)** — rejected by owner
  decision: this is a mechanism *of the standard*, so it is designed and built in
  `ai_akmon` directly; alphavar is the first consumer and the proving ground. The
  learn loop still applies to the *content* (matrix rows, ladder notes) via memory
  capture.
- **Subject-scoped agents (`k-framework-maint`, `k-bootstrap`)** — rejected: the matrix
  is *operation*-based; a subject area (akmon hook maintenance, config deployment)
  decomposes into existing rows plus `validate-loop`. Surfaced by session mining
  (Phase-1 CAPTURE). *Revisit-if:* a subject demands standing context no operation row
  carries.
- **Delegating the owner loop (`k-domain-resolver`, `k-verifier` as agents)** —
  rejected: owner dialogue and D2 verification are the orchestrator's matrix row,
  *never delegated*. The real need behind `k-verifier` — catching what awaits
  verification — is hooks + data, not an agent: see
  [d2-ledger design](d2-ledger.md).

## 8. Decided register (owner-locked) and phasing

All former open points are **locked** (owner verification of this design; recorded in
[ADR 0004](../akmon/meta/decisions/0004-model-routing-capability-tiers.md)):

| # | Question | Decision |
|---|---|---|
| 1 | worker floor | **lowest locally discovered adequate rung** — worker rows are mechanics; the ladder escalates on signal, so the floor's ceiling rarely binds |
| 2 | ask every session vs on-stale | **status-line + ask-on-stale**; the self-check line (§3) covers mid-session model switches |
| 3 | generated `.claude/agents/*.md` | ~~commit~~ **revised by [ADR 0006](../decisions/0006-orchestrator-detection-corridor-context-pressure.md): gitignored + regenerated** — the `model:` frontmatter follows the local orchestrator (per-user by construction, §3), so committed copies churn across users/models; the registry + overlay are the committed source, init/hook regenerate |
| 4 | second-opinion opt-in scope | **per project with per-session override** — recorded in local config; re-asked on staleness |
| 5 | granularity of generated agents | **few agents grouped by brief**; the bootstrap set is `k-explorer`, `k-mechanic`, `k-validator` (worker tier), `k-implementer` (mid rung — `implement-under-spec` needs its own model, so it splits from mechanic), `k-reasoner` (top rung); split further only if briefs diverge |
| 5a | agent naming | **`k-` prefix (akmon namespace)**, lowercase-kebab — avoids collision with harness built-ins (`Explore`, `Plan`, …) and marks provenance: `k-*` agents are akmon-managed, later owned by the generator |
| 6 | home of this design doc | **`ai_akmon` (`meta/design/`)** — revised post-lock: the mechanism is a akmon standard artifact end to end, design doc included, not just its ADR/doc edits; moved out of alphavar's LOCAL `_aitna/design/` once the model-routing and D2-ledger work settled |
| 7 | top rung / orchestrator display | **local-discovery-driven, never a hardcoded name**; status line always names the orchestrator; warn + suggest switching when below the local highest rung (§3, requirement 9) |

**Post-lock additions (owner-approved), from mining seven recent sessions** — three
worker-tier analysts classified the transcripts; findings: exploration
and summarizing dominate the orchestrator's burn (~35–40%), and all three independently
surfaced an uncovered *run gate → parse output → fix → re-run* loop (10–25% of work).
Hence: the `validate-loop` matrix row + `k-validator` bootstrap agent; read-only Bash
for `k-explorer` (git log/diff inspection was a visible share of exploration); the
subject-scoped and owner-loop agent candidates went to the rejected register (§7).
The same mining validated the worker tier itself: reliable extraction/classification,
weak arithmetic and subject-vs-operation confusion — calibration stays with the
orchestrator, exactly the escalation contract.

**Phasing:** (1) bootstrap *(done)* — hand-written grouped subagents in alphavar's
`.claude/agents/` validate the matrix rows in daily work; capture what delegates
well/badly to `_aitna/memory/`; (2) build registry + init tool + both hooks in
`ai_akmon`, wire via `sync.py`, land the §6 doc edits; (3) alphavar consumes: bump the
submodule pin, run init (generated agents supersede the hand-written set), gitignore the
local config.

## 9. Extension — auditor tier, gate-pack protocol, level-hypothesis check

> **Status: owner-locked (A5) — §9.7 + §10.4 decided; the decision record is
> [ADR 0005](../decisions/0005-synthesizer-gate-audit-and-role-routing.md).** v2 of this section: v1
> ("refine-synthesis as a reasoner task kind") is superseded — see the rejected register
> (§9.8) for what changed and why. Companion sections: §10 (roles under the subagent
> model), §11 (prior art — host-harness built-ins). Backlog: architecture A5 ·
> implementation C15–C20 ([TASKS.md](../TASKS.md)).
> Motivating evidence: alphavar's top-down architecture review, finding #1
> (`io → options` inversion) — a defect invisible to any per-file/per-module finding,
> surviving several design passes, found only when something looked at the **whole
> dependency graph at once**.

### 9.1 Principle — quality investment ∝ artifact leverage

The routing rule the whole mechanism already follows implicitly, now named. An
artifact's **leverage** has two components:

- **error cost** — how expensively an error in it is *detected and undone* (a mechanic's
  rename: gates catch it in seconds; a wrong architecture picture: inherited by every
  decision built on it before anyone notices);
- **inheritance cost** — how much future *operation and evolution* the artifact carries:
  quality built in up front is not only cheaper rework, it is cheaper running and
  extending of everything downstream of it.

Both components point the same way: **the higher the leverage, the stronger the model,
the fresher the context, and the closer to the owner the check.** The existing tier
gradient already embodies this (haiku workers hold edit rights *because* gates bound
their errors; the top-rung tier drafts but never edits *because* its errors are not
gate-detectable); this extension completes the gradient at the top, where leverage is
maximal: the orchestrator's own synthesis and the owner's decisions.

### 9.2 The session model is the owner's level hypothesis

The user's choice of session model is not a config accident — it is the **owner's
hypothesis about the task's level**. The binding respects it (never overrides), routes
*relative* to it, and — new here — **checks it empirically**: the auditor (§9.3),
which always runs on the maximal available model, sees the whole collected material at a
gate and includes a **level verdict** in its output: does the material suggest the task
exceeded the hypothesis (contested forks resolved shallowly, contradictions the
orchestrator missed, D2-dense territory)? If so, it names the *specific* piece to redo
on a higher rung, or recommends `/model` up. Advisory — the owner decides. The static
init-time floor warning (§3, requirement 9) is retained as a weak prior but demoted:
the evidence-based gate check is the authoritative signal.

### 9.3 Tier changes (registry-level)

1. **New tier `auditor` — pinned to the maximal available rung.** Runs the
   `audit` task kind at review/architect gates: audits the *whole* collected
   material for what no part-check could see (contradictions between
   independently-correct findings, uncovered seams between zones, option sets with
   incompatible assumptions), plus the level verdict (§9.2). This is the **first audit of
   the orchestrator's own work** — every other tier's output is already checked by
   something (gates, tests, a draft's reader, the owner); the orchestrator's synthesis was
   the one unaudited node, precisely where the io↔options class lives. Splitting it from
   `reasoner` is now justified because the selection policies genuinely diverge (below).
2. **`reasoner` becomes dynamic** — no longer dogmatically the top rung: the top model is
   not always available, is expensive, and the orchestrator's own rung is often adequate
   for a bounded draft. Default and floors decided (§9.7 #1): default to
   the orchestrator's rung (hypothesis-consistent, fresh context is the main benefit),
   escalate on the existing ladder signals, with per-task-kind floors as registry data
   (e.g. `quant-derivation` may pin higher). A wrong under-powered draft at a gate is
   caught by the auditor — the safety net that makes the cheaper default acceptable.
3. **`second-opinion` — always a *different model*, because it thinks differently.** The
   diversity requirement is about priors, not vendor branding: the reviewer must differ
   from the models whose work it reviews (the orchestrator as author, the auditor as
   auditor). Preference ladder (registry policy): (1) another vendor's model; (2) the same
   vendor's *different* model; never the same model. Fallback when no other vendor is
   reachable: decided (§9.7 #2) — a different model of the same vendor.

Three independence mechanisms, one axis: adversarial verification varies the **prompt**,
the auditor varies the **context** (fresh view, same or stronger model), second
opinion varies the **priors** (different model). Verification depth scales with gate
criticality: an ordinary Calibrate gets the auditor alone; a load-bearing Align gets
auditor + second opinion.

4. **Generated agent `k-auditor`** — the tier's concrete artifact, joining the
   bootstrap set (§8.5: `k-explorer`, `k-mechanic`, `k-validator`, `k-implementer`,
   `k-reasoner`, now `k-auditor`). Registry deltas: an `auditor` selection policy
   (`"auditor": "highest"` — pinned max, unlike the now-dynamic reasoner) and a
   task-kind row `"audit": {"tier": "auditor"}`. Definition contract:
   - **frontmatter:** `model:` = the maximal locally available rung; **tools read-only**
     (Read/Grep/Glob + read-only Bash) — like `k-reasoner`, it drafts and audits, never
     edits;
   - **input:** a gate-pack (§9.4), nothing else — no session history; the clean context
     *is* the mechanism;
   - **output:** contradictions between independently-correct findings/options ·
     uncovered seams derived from the coverage map · re-ranking / recommendation deltas ·
     the **level verdict** (§9.2) · an explicit "could not verify" list;
   - **delivery mirrors §4.6:** full report to a file, digest to chat (verdict +
     disagreements + level verdict), the call logged by the delegation hook; the report
     attaches to the D2 ledger entry (§9.6);
   - **escalation signal:** if the pack lacks what the audit needs (no coverage map, no
     yardstick), it returns the precise gap instead of a diluted verdict.

5. **New task kind `plan-draft` — tier `reasoner` (dynamic); owner-decided.** The plan
   was the last unaudited high-leverage artifact: the post-gate audit checks work
   against the coverage map, which derives from the plan itself, so a zone the plan
   never contained cannot surface as an uncovered seam (circular blindness). Two
   mechanisms close it, **no new standing agent**:
   - **Drafting:** for ordinary tasks the orchestrator plans itself (its own matrix
     row). On leverage signals — a cross-zone task, D2-dense territory, an expected
     gate-qualifying fan-out — the decomposition draft (the zone plan §10.3, risks,
     ordering) is delegated as `plan-draft` to the reasoner in fresh context, escalating
     up the ladder as usual. Not `design-fork`: that drafts *product* structure, this
     drafts *work* structure — a different question shape, hence its own checkable
     matrix row. Registry delta: `"plan-draft": {"tier": "reasoner"}`. *Adopting* the
     plan stays with the orchestrator — the precise invariant reading, §10.1.
   - **Plan check — the auditor's second, pre-fan-out anchor; owner-decided: always
     for gate-qualifying work.** Pre-fan-out, "gate-qualifying" is knowable only via the
     structural criterion (the zone plan names ≥2 zones — counts don't exist yet); when
     it holds, the auditor receives a **minimal pack** — yardstick + zone plan, no
     artifacts — and answers: does the plan cover the stated goal; which zones/seams are
     obviously missing? The plan is checked against the *goal*, not against its own
     coverage map. Cheap (input is tens of lines), same pinned-max model, and it runs
     *before* the fan-out spends tokens on a mis-scoped plan.
   The economics this completes: planning and auditing are **low-token, high-leverage**
   → the maximal model; fan-out execution is **high-token, low-leverage** → cheap
   models. The strongest model concentrates at exactly three points — plan draft (on
   signal), plan check (before spend), whole audit (after) — while orchestration between
   them runs on the owner's hypothesis model.

### 9.4 Gate-pack protocol — one packaging, N executors

One structured input package per gate, consumed by every executor (the auditor
subagent and the second-opinion CLI — replacing §4.6's free-form `--prompt-file`):

- **the step's artifacts** — findings with evidence (review) / options with trade-offs +
  the decisions register (architect);
- **the Frame-stage yardstick / acceptance condition** — so executors judge against the
  stated goal, not one inferred from the findings;
- **a coverage map** — which zone/module each fan-out worker actually checked, assembled
  **from the delegation log by code, not by the orchestrator** (fan-out calls carry a
  zone label in their description; a tool derives the map — requirement 8 discipline:
  visible at code cost, not token cost);
- *optional, per gate:* a real dependency-graph excerpt (grep-derived) for
  architecture-review gates — open point 3.

**Roles and tiers stay orthogonal** (MODEL.md §1): the **role** determines the pack's
contract and the question asked (review: "what contradicts, what seam is uncovered?" ·
architect: "do the locked decisions cohere, do options assume compatible things?");
the **tier** determines only the model. Engineer/code-flow keeps its existing verify
annotation — implementation errors are gate-detectable and the design leverage was
already spent at the design gate; the orchestrator may still invoke an audit pass on signal
for high-leverage code (a core abstraction, a public API) — **A7 (b) makes `audit` a
cross-cutting verification kind (§10.2), routable from any role and governed by the structural
trigger, so this engineer-side invocation needs no role-specific carve-out and the C20
advisory does not warn against it.**

### 9.5 Triggers and the loop-back edge *(carried from v1, unchanged in substance)*

- **Count floor** (registry data, code-computed): `review.min_findings` /
  `architect.min_options` — leaning 3 / 2, tuned from delegation-log evidence.
- **Structural trigger:** fan-out touched ≥2 independently-decomposed zones, each
  contributing ≥1 finding/option — fires at 1-per-zone where the count floor misses;
  exactly the io↔options shape.
- **Orchestrator override**, both directions; a skip above the floor is logged with its
  reason (delegation-log hook, §4.4), not silent.
- **Loop-back edge (new in v2):** a found seam/contradiction routes back — review: to
  Decompose/Measure; design: to Iterate — for **one bounded re-round** of fan-out, then
  re-synthesis only if the new material re-qualifies. More than one re-round → escalate
  to the owner instead of oscillating.
- **Anchors (post-fan-out):** review-flow end of Calibrate (step 4, before Hand off);
  design-flow Consolidate (step 7, before the ADR fold — previously the one flow step
  with no tier annotation).
- **Anchor (pre-fan-out, new):** the plan check (§9.3 item 5) — fires whenever the zone
  plan names ≥2 zones (the pre-fan-out form of the structural trigger; owner-decided:
  always for gate-qualifying work, not on-signal).

### 9.6 Owner integration — attention is the second budget

The owner is the apex decision node; the framework's goal is quality per unit of
**tokens + owner attention**, and only the first had a mechanism. Two integrations:

- **d2-ledger attachment:** the auditor's gate report attaches to the D2 ledger
  entry alongside the reasoner draft and second-opinion digest (d2-ledger §2.5) — the
  owner opens one entry and sees the change, the drafted rationale, the whole-picture
  audit, and where the independent review disagrees, then decides.
- **attention metrics:** the stats digest (C13) reports owner load next to token spend —
  D2 entries pending/verified, decisions taken per session — so both halves of the goal
  function are measured.

### 9.7 Decided register (A5 owner lock)

All points locked by the owner ("9.7 принято"); recorded in
[ADR 0005](../decisions/0005-synthesizer-gate-audit-and-role-routing.md).

| # | Question | Decision |
|---|---|---|
| 1 | `reasoner` dynamic default | **(a)** orchestrator's rung + per-task-kind registry floors, escalate on ladder signals — trusts the level hypothesis; the auditor catches under-powered drafts at the gate |
| 2 | second-opinion fallback when no other vendor is reachable | **(b)** a different model of the same vendor — weaker prior diversity still beats none; the ladder (other vendor → other model → never same) is registry data |
| 3 | optional dependency-graph excerpt in the review gate-pack | **yes**, opt-in per gate |
| 4 | count-floor numbers | **3 / 2**, tune from telemetry |
| 5 | skip-above-floor surfacing | **silent-but-logged** |
| 6 | orchestrator floor relaxation | **yes** — with the auditor on, review/architect-dominant sessions may orchestrate below the top rung; the init-time floor warning stands as the weak prior (§9.2), the gate-level verdict is the authoritative signal |
| 7 | `plan-draft` as its own matrix row (vs reusing `design-fork`) | **own row** — work structure vs product structure are different question shapes; the matrix stays checkable |
| 8 | plan-check trigger | **always for gate-qualifying work** — pre-fan-out that means the structural criterion (zone plan ≥2 zones); counts don't exist yet |
| 9 | who runs `plan-draft` | **dynamic reasoner** (the draft is a bounded task; the pinned-max auditor keeps the *check*) — was already the §9.3 text; confirmed, not an open fork |

### 9.8 Alternatives considered / rejected branches

- **v1: `audit` as a task kind on the `reasoner` tier, no new tier** —
  superseded: v1 assumed the selection policies coincide (both top-rung); the level-
  hypothesis model splits them — reasoner goes dynamic/relative, auditor stays
  pinned-max. The prompt-contract insight of v1 (a category difference from
  `design-fork`/`debug-deep`) carries over unchanged.
- **`reasoner` statically pinned to the top rung** *(the pre-v2 status quo, §3)* —
  superseded by open point 1: not always available, expensive, and often above the
  bounded draft's needs; the auditor safety net makes the relative default viable.
  *Revisit-if:* gate audits show under-powered drafts recurring despite the ladder.
- **Second-opinion bound to vendor diversity only** — superseded: the requirement is
  *model* diversity (different priors); vendor diversity is the preferred but not the
  only way to get it.
- **Mandatory auditor at every gate** (v1-fork B) — rejected: contradicts the
  threshold+override decision; cost on trivial gates buys nothing.
- **Fold into `design-fork`/`debug-deep` prompt contract** — rejected (carried from v1):
  a different question shape; conflation degrades both prompts.
- **Trigger by orchestrator judgment alone** — rejected (carried from v1): the inertia
  risk the matrix exists to remove.
- **Raw worker transcripts as default input** — rejected (carried from v1): process
  noise at token cost; the dependency graph opt-in is the one carve-out.
- **Other vendor as the auditor** — rejected: conflates the context-diversity and
  prior-diversity mechanisms; the auditor must share the session's conventions and
  registry contract, which a foreign CLI does not; prior diversity is second-opinion's
  job.

## 10. Roles under the subagent model

> **Status: owner-locked with §9 (A5 → [ADR 0005](../decisions/0005-synthesizer-gate-audit-and-role-routing.md)).**
> This section is the design source;
> `roles/*.md` and `pipelines/*.md` receive one-paragraph deltas that link here
> (single owner per fact — the matrix below lives in the registry, docs link to it).

### 10.1 A role is an orchestration contract

Pre-tier, a role read as "one agent walks the pipeline". Under the subagent model a role
names three things instead: **(a) the steps the orchestrator keeps** (Frame, gate
decisions, owner dialogue — its own matrix row), **(b) its routing rights** — which task
kinds it may delegate (§10.2), and **(c) the gate contract its pipeline ends with**
(which gate-pack, which executors, at what criticality). The `🧭 agent:` declaration
marks whose orchestration contract is active; subagents do not inherit the role — they
receive a task kind, and the role's constraints must already be encoded in what it is
allowed to route.

The "decompose / route / synthesize — never delegated" invariant (§2, ADR 0004) reads
precisely as: the orchestrator never delegates **adopting** a plan, a route, or a
synthesis. The **draft** is delegable like any other draft — `plan-draft` (§9.3 item 5)
for decomposition, exactly the drafts-vs-decides split the rest of the system already
runs on (reasoner drafts forks, architect + owner decide; auditor audits, owner
decides).

### 10.2 Role → allowed task kinds (registry `role_task_kinds`)

The gap this closes: nothing currently stops the analysis-only `review` role from
routing an edit — the guardrail rests on orchestrator discipline alone. As registry data:

| Role | May route | Never routes |
|---|---|---|
| review | explore-search · summarize · debug-deep · plan-draft | any edit kind — review produces words |
| architect | explore-search · summarize · design-fork · quant-derivation · plan-draft · doc-sync *(only post-Record-confirmation)* | mech-edit · implement-under-spec · test-scaffold · validate-loop |
| engineer | all worker kinds · debug-deep · quant-derivation · plan-draft | design-fork — a material design gap goes *back to architect*, not sideways to a reasoner |
| learn | explore-search · summarize · doc-sync *(post-confirmation)* | — |
| release | validate-loop · doc-sync · summarize | — |

**Cross-cutting verification kinds — `independent-review` and `audit`** — are **not role-gated** (A7 (b)): any role may route them, and
*when* they are warranted is the **structural trigger** (fan-out touched ≥2 zones) / count
floor (§9.5), not the producing role. This dissolves the A7 seam (§9.4) at its source — the
auditor is a role-agnostic *verification capability*, not an engineer-specific task kind — so
it belongs to no single row above and is exempt from the warning below. (Consequence:
learn/release may route them too — advisory-only, and verification is never role-inappropriate.)

Enforcement is advisory, same idiom as the delegation nudge: the delegation hook warns
when a routed kind falls outside the active role's row (**cross-cutting verification kinds
excepted**, per the note above — a `cross_cutting_kinds` registry list, checked in
`role_matrix_warning`). It needs a machine-readable active-role marker (the `🧭` chat
declaration is invisible to hooks) — decided §10.4: doc rule + registry data ship first; the
session-state marker lands with C20.

### 10.3 Pipeline step contracts gain data outputs

- **Decompose (review) / Survey (design) emit an explicit zone plan** — the named list
  of zones/modules the fan-out is split by. Each fan-out delegation carries its zone
  label; the coverage map (§9.4, C17) is then *assembled from the log by code*, closing
  the loop between how work was split and how its completeness is audited. Today the
  decomposition lives in prose and the map would have no source.
- **Loop-back edges become explicit steps** in review-flow (Calibrate → Decompose, one
  bounded re-round) and design-flow (Consolidate → Iterate) — §9.5's topology, written
  into the flow docs rather than implied.
- **learn/release get their tier lines:** learn's session mining routes
  `explore-search`/`summarize` fan-outs (the model-routing mining itself was the
  precedent); release routes `validate-loop`. Decisions stay with the orchestrator and
  owner in both.

### 10.4 Decided (A5 owner lock)

| # | Question | Decision |
|---|---|---|
| 1 | Active-role marker for hook enforcement | **(b) then (a)** — ship the matrix as a doc rule + registry data first; add the session-state marker when the delegation hook gains its role check (C20) |
| 2 | Does `review` routing `debug-deep` blur analysis-only? | **no** — a failure-mechanism diagnosis is analysis; the *fix* is what review must not construct |
| 3 | `engineer` vs the auditor — §9.4 permits an on-signal code audit, §10.2 omitted it (A7 seam 1) | **(b)** — make `audit` (+ `independent-review`) **cross-cutting verification kinds**: routable from *any* role and exempt from the role-matrix warning; *when* they apply is the structural trigger (§9.5), not the role. Cleaner than a per-row copy — the auditor is role-agnostic *verification*, not engineer-specific work, which dissolves the seam at source and simplifies C20. Consequence: learn/release may route them too (advisory-only, never harmful). Impl in C18: registry `cross_cutting_kinds` + `role_matrix_warning` exemption + test + ADR 0005 addendum. Follow-up weighs the sub-fork (auto-trigger `plan-draft` on un-decomposed high-leverage work — verdict contradiction 2's economics root) |

## 11. Prior art — the host harness's own subagents (Claude Code)

Checked against the built-in agent set of the harness this session runs in (`Explore`,
`Plan`, `general-purpose`, `claude`, plus the deterministic `Workflow` orchestration
tool and its quality patterns). Verified against the live tool surface, not memory.

| akmon | Closest host built-in | Note |
|---|---|---|
| `k-explorer` | **Explore** (fast read-only search, "conclusions not file dumps", breadth parameter) | same shape, independently converged — including enforcement *by tool set*, not prompt trust |
| `k-reasoner` | **Plan** ("software architect for implementation plans, trade-offs") | partial: Plan is the "tech-lead-shaped" built-in, scoped to implementation planning; k-reasoner is wider (debug-deep, quant) |
| `k-mechanic` / `k-validator` / `k-implementer` | `general-purpose` / `claude` (catch-alls) | no per-kind split in the host — akmon's task-kind granularity is finer |
| `auditor` | **Workflow "completeness critic"** pattern ("what's missing — claim unverified, modality not run?") + "adversarial verify" | the closest prior art to `audit` — but in the host it is a *workflow stage pattern*, not a standing agent with a pinned model |
| second-opinion | — | absent (single-vendor harness); akmon addition |
| level-hypothesis check, owner-attention budget (D2 ledger) | — | absent; akmon additions |
| orchestrator = main session, never delegated | same in the host | both systems keep decomposition/synthesis/user dialogue in the main loop |

Adopted into this design from the comparison:

- **Enforcement by tool set** (Explore has no write tools; `k-explorer`/`k-reasoner`/
  `k-auditor` likewise) — already aligned, keep as the rule for audit-tier agents.
- **Deterministic orchestration for the gate fan-out:** the host's `Workflow` runs
  fan-out/pipeline/verify loops as *code*, not model judgment — exactly akmon's D4
  instinct. The gate-pack assembly + fan-out + auditor call (C16/C17) should be
  runnable as one deterministic script, with the orchestrator deciding only entry and
  the verdict's consumption. *(Vehicle, not contract — per-vendor availability differs.)*
- **Perspective-diverse verification** (distinct lenses beating N identical checkers) —
  refines the §9.3 diversity axis: when a gate warrants more than one auditor-side
  check, vary the *lens* (coherence / coverage / level), not just the count.

Divergences kept deliberately: the host routes to agents by *description matching*;
akmon routes by the task-kind matrix (checkable data, not affinity). The host has no
cross-model tiering of its built-ins by task economics — akmon's core addition stands.

## 12. Runtime weakness signals — context pressure and the intelligence axis

> **Status: built ([ADR 0006](../decisions/0006-orchestrator-detection-corridor-context-pressure.md);
> C23 — awaiting owner verify, D2).** Requirement 12.

A model can be "weak" for the running session on two axes; each already has (or now gets)
a distinct detector — no overlap:

- **Intelligence** — the task exceeds the model's level. Detector: the auditor's
  **level verdict** (§9.2), evidence-based at gates. The static corridor warning (§3) is
  the weak prior at the session boundary. **No new mechanism** — this axis is closed.
- **Tokens** — the context window fills up; quality degrades before a forced compaction
  lands mid-task. Detector: **context-pressure detection**, below.

### 12.1 Signal — read from the transcript the hook already scans

The transcript's per-turn `message.usage` records the context economics of each call.
The **fill** of the window at the last main-chain assistant turn is

```
fill = input_tokens + cache_read_input_tokens + cache_creation_input_tokens
```

(the three input components partition the prompt; `output_tokens` is not context carried
forward). One transcript pass yields both the orchestrator model (§3 detection) and the
fill — the detector adds **zero extra I/O** to the per-turn hook.

### 12.2 Policy as registry data

```json
"context_pressure": {
  "window_default": 200000,
  "windows": {},
  "warn_ratios": [0.85, 0.95]
}
```

- `window_default` — the assumed context window; `windows` maps alias substrings to
  exceptions when a model's window differs. Registry data, overlayable per project.
- `warn_ratios` — ordered warning bands: **high** (plan the compaction: checkpoint
  durable state to files/TASKS, finish the unit of work) and **critical** (compact now —
  past this point quality loss and a forced mid-task compaction are imminent).

### 12.3 Mechanism — same hook, banded, throttled

Runs inside the §4.3 UserPromptSubmit pass (and at SessionStart, where a resumed session
may already be deep):

1. compute `fill / window` for the last main-chain turn;
2. find the highest crossed band (or none);
3. **throttle by band, not by turn:** a per-session temp-dir marker
   (`akmon-context-pressure-<session_id>`, the delegation-nudge idiom) records the last
   announced band; warn only when the band *rises* — 0→85 warns once, 85→95 warns once
   more, steady 87% stays silent;
4. **reset on compaction:** fill dropping below the lowest band clears the marker, so a
   later re-crossing warns again (each compaction cycle gets its own warnings);
5. delivery per requirement 11: `systemMessage` (the owner acts — `/compact`, checkpoint)
   **and** `additionalContext` (the model acts — stop opening new fronts, persist durable
   state, propose the checkpoint), e.g.
   `⚠ context pressure: ~83% of 200k — checkpoint durable state and plan compaction`.

Missing/malformed `usage` → silent (never block a turn, the hook's standing rule).

### 12.4 Rejected branches

- **The model self-reports fullness** — rejected: it cannot see its own window fill
  reliably, and narration costs the very tokens under pressure; the transcript states the
  fact for free (requirement 8 discipline: code cost, not token cost).
- **Warn every turn above a threshold** — rejected: a nag the model and owner learn to
  ignore; banded one-shot warnings with compaction reset keep the signal rare and real.
- **Auto-compact / auto-checkpoint on critical** — rejected: mutating the session is the
  owner's move (same never-override stance as the orchestrator choice); the hook informs.

## 13. Delegation drift — from prose to a forcing function

> **Status: axis-1 built (advisory + hard ask + the C28d subagent exemption landed;
> awaiting owner verify + commit, D2 — see [D2 ledger](../D2_LEDGER.md) D2-8/D2-9).
> C28a live-verified: no tool-category exemption, but a background/child-session
> enforcement gap surfaced (D2-10, C31). Axis-2 planned (C29).** Requirement: make
> delegation *actually happen*, not just be documented.

### 13.1 Problem — the standard said "delegate" seven times and the orchestrator still didn't

Every routing artifact already tells the orchestrator to delegate by task kind
(MODEL.md § Capability tiers, §9.1 leverage, the roles, the guardrails). The observed
behaviour was the opposite: **the orchestrator did everything itself** — reads, sweeps,
edits, shell — and only the owner's manual `k-*` calls produced any delegation. The
delegation log (§4.4) confirmed it: healthy-looking entries were *all* owner-initiated,
so the autonomous self-delegation the standard asks for was effectively zero.

Prose does not fix this. A rule restated an eighth time is still a rule that falls out of
context in a long session — the same reason the commit and analysis guards are **hooks**,
not paragraphs. Delegation needs a **forcing function** at tool-call time, on the same
PreToolUse surface those guards already use.

### 13.2 Axis-1 (built) — call-count drift → graduated advisory → hard ask

`hooks/hook_core.py::delegation_nudge_result` counts **consecutive orchestrator delegable
tool calls with no delegation between them**, keyed per session in the temp dir (the
§12.3 marker idiom):

- **What counts** — edit (`Write/Edit/MultiEdit`), shell (`Bash`), **and read
  (`Read/Grep/Glob`)**. Reads count because the actual drift symptom *is* the read/sweep:
  pulling a wide `git diff`, grepping the tree, reading many files inline is exactly the
  work a `k-explorer` should absorb so the dump never enters orchestrator context. An
  edit-only counter would have missed the dominant failure mode.
- **Graduation** — advisory `additionalContext` at the nudge threshold (default 10,
  `KEYSTONE_DELEGATION_NUDGE_THRESHOLD`); a hard PreToolUse **`ask`** on *sustained* drift
  at the ask threshold (default 20, `KEYSTONE_DELEGATION_ASK_THRESHOLD`, clamped ≥ advisory).
  Each fires **once per drift episode** via its own temp-dir marker.
- **Reset + re-arm** — any subagent delegation (`Task`/`Agent`) zeroes the counter and
  clears both markers: a delegation is the exact act the nudge wants, so it re-arms the
  whole ladder for the next episode.
- **Wiring** — the matcher in `bin/sync.py::_claude_hooks` is the source of truth
  (`Bash|Edit|Write|MultiEdit|Task|Agent|Read|Grep|Glob`), mirrored into
  `.claude/settings.json`.

**Vendor contract (C28a live-verified; C28b wire shape schema-verified, runtime open).**
The hook dispatches identically for read-only tools (`Read/Grep/Glob`) and for
`Bash/Edit` — confirmed live (C28a): a debug-instrumented run showed `delegation-nudge.py`
firing on a real `Read` call exactly like a real `Bash` call, same counter, same
`HookResult(permission_decision="ask")` output. No tool-category exemption exists in the
hook. The codex adapter's output **shape** is confirmed schema-valid (C28b): the installed
`codex` binary embeds its own JSON schema for hook I/O, and
`pre-tool-use.command.output.hookSpecificOutput.permissionDecision` is exactly
`allow|deny|ask`, matching what `codex_adapter.py` emits today. Codex also exposes a
separate `PermissionRequest` hook event (own `behavior: allow|deny` contract) not yet
used here. What remains open is **runtime enforcement** — whether codex actually blocks
on `ask`/`deny`, especially under non-interactive `codex exec` — untested, deferred
(owner: cost/time). See [D2 ledger](../D2_LEDGER.md) D2-10 for a related lever: both
Claude and Codex payloads carry a `permission_mode` field with the identical enum
(`default|acceptEdits|plan|dontAsk|bypassPermissions`), which a hook could read to decide
`ask` vs `deny` instead of emitting an `ask` that may be a no-op in non-default modes.

**Background/child-session gap (C31) — resolved by escalation, owner decision.** The same
live test showed the emitted `ask` was **not enforced** — for either `Read` or `Bash` — in a
Claude Code background/child session (`CLAUDE_CODE_CHILD_SESSION=1`): both tool calls
completed normally with no permission gate, even though the hook's stdout carried
`permissionDecision: "ask"` for both. Rather than spend more cycles isolating background-vs-
`acceptEdits` as the exact trigger, the owner chose the stricter posture over the diagnostic
one: **`delegation_nudge_result` and `git_commit_guard_result` now both escalate any `ask`
to a hard `deny` whenever `permission_mode` is not the interactive `default`** (including the
field being absent, the worst case) — `_escalate_unattended_ask` in `hook_core.py`. `deny` is
the one decision every vendor is confirmed (C28b) to enforce unconditionally, so a session
that cannot be trusted to answer `ask` gets a real stop instead of a silent pass-through; the
owner watches how this behaves in practice (fatigue vs. missed real confirmations) rather
than gating the fix on a foreground/background repro first. Both Claude wrappers
(`git-commit-guard.py`, `delegation-nudge.py`) read `permission_mode` straight off the
PreToolUse payload and thread it through; Codex is unaffected for now — its `.codex/hooks.json`
does not wire either of these two hooks. See [D2 ledger](../D2_LEDGER.md) D2-11.

### 13.3 The subagent exemption (C28d) — why a shared session_id is a trap

Claude Code gives a subagent's tool calls the **same `session_id`** as the main chain.
The counter is keyed by `session_id`, so without a guard a subagent's reads charged the
**orchestrator's** counter — and worse, tripped the nudge (and the hard `ask`) *inside* a
`k-*` delegate that has **no `Task` tool and cannot delegate at all*. Demonstrated live: a
read-only audit subagent tripped the nudge at its tenth read. The advisory wasted the
delegate's context; the `ask` was un-actionable and blocked its legitimate reads.

Fix: the PreToolUse payload carries `agent_id` **only inside a subagent**. The wrapper
sets `is_subagent = bool(payload.get("agent_id"))`; `delegation_nudge_result` returns
early **before touching the counter** when it is set. So subagent calls are fully
transparent to the mechanism — they neither charge the orchestrator's counter nor receive
a nudge — regardless of the shared `session_id`.

### 13.4 Axis-2 (planned, C29) — inline output-weight as the context-cost signal

Axis-1 counts *calls*; it cannot tell a one-line `git rev-parse` from a thousand-line
`git diff`. The principled second axis measures **cumulative byte/char weight of the
inline tool output the orchestrator pulled instead of delegating** (a PostToolUse
entrypoint, since the output does not exist at PreToolUse), reset on `Task`/`Agent`. Its
motivation is **context cost in two senses**, only one of which axis-1 sees:

1. **Token budget** — inline dumps fill the window and pull compaction forward (the §12
   fill signal, from the *supply* side).
2. **Reasoning quality** — beyond raw tokens, low-signal bulk dilutes attention (context
   rot / lost-in-the-middle): small load-bearing details get ignored as the window fills.
   This is *why* the axis is weighted by fill, not merely additive.

- **Coefficient** — axis-2's weight scales with context fill, reusing the §12.1 `fill`
  computation (one owner for that fact — link, don't recompute). At least **four bands**
  (e.g. ~0.5 / 0.7 / 0.85 / 0.95 → ×1 / ×2 / ×4 / ×8): the fuller the window, the more
  expensive each self-served inline answer is, on *both* grounds above.
- **Advisory-only, dual-channel** — `additionalContext` (model-addressed) **and** an
  owner-visible `systemMessage` stating a quality/token recommendation fired and that the
  owner *may* escalate it to a hard `ask`. **Not** an armed auto-ask — see rejected below.

### 13.5 Rejected branches

- **An eighth prose restatement** — rejected: the prose already existed sevenfold and did
  not change behaviour (§13.1). The demoted duplicate bullets were removed to restore
  one-owner-per-fact; the leverage principle stays in MODEL.md, the mechanism here.
- **Arming axis-2 with an auto-`ask`** — rejected (owner decision): a second hard gate on
  top of axis-1's ask risks alarm fatigue, and it collides on the same `ask` channel as
  the commit guard; it also contradicts §12.4's "the hook informs, the owner acts" stance.
  Axis-2 stays advisory; escalation to a hard ask is an explicit owner move.
- **Heuristic read-only-vs-mutating classification of the bash string** — rejected as the
  tuning axis: brittle (`git status && rm -rf` is not read-only) and on the wrong axis. The
  cost that matters is **output weight**, not mutation: a read-only `git diff` across many
  files is the *most* expensive thing to pull inline and *should* trip. Axis-2 measures the
  right thing directly; only genuinely tiny-output commands (`git status`, `rev-parse`,
  `ls`) are inline-justified, and axis-2's weight already discounts them.
- **Assuming the drift is "in remission"** — rejected: a healthy delegation log is an
  artifact of the owner's *manual* audit calls, not autonomous self-delegation. The
  mechanism must assume the drift is live, which is why axis-2 is warranted on top of
  axis-1 rather than deferred.
