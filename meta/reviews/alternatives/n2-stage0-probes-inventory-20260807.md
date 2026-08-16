# N2 — stage 0: vendor delivery probes & inventory (2026-08-09)

> **Point-in-time findings report** (review role, no code changes). Covers plan items
> **P0.1** (live delivery probes, Claude arm incl. the D4 built-in comparison), **P0.3**
> (guardrail↔hook invariant inventory) and the **as-is halves of P0.2/P0.4** — measurement
> only. Every *decision* built on this (support-matrix dimensions, OS contract, the
> source/generated boundary declaration, numeric caps) belongs to **A12**, per the role
> seam in [ADR 0010](../../decisions/0010-alternatives-adoption-a11-verdicts.md)
> § Amendments. Probe facts age with the harness — re-run per the **N1** rule (every
> release touching `hooks/` or `bin/sync.py`).

**Probe environment.** Attached pilot consumer `alphavar` (mount mode `package`,
akmon `0.4.0.dev0`), **not** the akmon source repo — akmon itself carries no `_aitna/`,
no generated `k-*` agent files and no wired `.claude/settings.json`, so a probe run there
would measure nothing about delivery. Harness: **Claude Code 2.1.221**, headless
(`claude -p --output-format json`). Total probe cost **$0.688** across three sessions
(`ee0ebee1`, `fed796e3`, probe C).

**Codex arm** ran later, on **codex-cli 0.146.0**, and is reported in **§1A** — added in
place rather than as a separate report so the two vendors' delivery findings sit side by
side. Two probe runs were **void** (wrong workspace root, see §1A) and are excluded; the
findings that stand are read out of codex's rollout files, not out of agent self-reports.

---

## 1. P0.1 — what a subagent actually receives (Claude arm)

Method: three dispatch types given one identical context self-report questionnaire
(answer from context only, no tools). Two independent sessions with **different session
models** (opus, then haiku) to separate a model *pin* from *session inheritance*; a third
session made the tool set a direct call attempt rather than a self-report.

### 1.1 Guardrail delivery — reproduced, and it is **type-dependent**

| Dispatch type | English-artifacts rule | commit rule | D2 / owner-verify | AGENTS.md / CLAUDE.md text |
|---|---|---|---|---|
| `k-explorer` (generated) | ✅ quoted verbatim | ✅ quoted | ✅ quoted | ✅ sees both |
| `Explore` (built-in) | **ABSENT** | **ABSENT** | **ABSENT** | **ABSENT** |
| `general-purpose` (built-in) | ✅ quoted verbatim | ✅ quoted (+ D5 from AGENTS.md) | ✅ quoted | ✅ sees both |

**W4 is reproduced — but not in the shape the plan assumed.** The assumption was "a
non-`k-*` subagent receives nothing akmon-specific". Reality splits by type: `Explore`
runs with **zero** akmon context, while `general-purpose` receives the *full* project
context (CLAUDE.md → `@AGENTS.md` → `@guardrails/*`) — the same text a main-chain session
gets. So the built-in tier is not uniformly guardrail-free: one type is a viable policy
carrier, the other is a blind spot.

Second-order note: `k-explorer` answered questions 1–3 from the **project** context
(CLAUDE.md/AGENTS.md), not only from its own generated body. Its body embeds none of
those three rules (see §1.4) — so generated agents inherit the project context too, and
"delivery by construction" understates what arrives.

### 1.2 Model binding — the pin holds for `k-*`, and does not exist for built-ins

| Session model | `k-explorer` | `Explore` | `general-purpose` |
|---|---|---|---|
| opus (probe A) | **haiku** | opus | opus |
| haiku (probe B) | haiku | haiku | haiku |

The `k-explorer` pin held against an opus session — the frontmatter `model:` binding is
real, not decorative. Built-ins carry **no pin**: they follow the session model in both
directions. Confirmed independently of self-report by the session's own `modelUsage`
accounting (probe A billed `claude-haiku-4-5` for 618 output tokens — the `k-explorer`
leg alone — and `claude-opus-5` for everything else).

**Consequence for D4:** routing read-only reconnaissance to the built-in `Explore` runs it
at the *orchestrator's* rung. akmon's leverage principle (MODEL.md § Capability tiers,
`guardrails/_common.md` § Route by task kind) is **unenforceable** on built-in types —
the tier floor has nothing to bind to. Cost illustration from probe A, same questionnaire:
the pinned `k-explorer` leg cost $0.019; the opus total for the session (orchestrator plus
the two built-in legs) was $0.512. Not a clean per-agent comparison — the orchestrator's
own turns are inside the opus figure — but directionally decisive.

### 1.3 Hook observation — the log sees built-ins, the model column does not

All six dispatches across both sessions were recorded by `delegation-log.py` in
`alphavar/.claude/model-routing.log`, built-ins included:

```
2026-08-09T05:25:11+0000  ee0ebee1…  k-explorer       haiku  -  Context self-report probe
2026-08-09T05:25:25+0000  ee0ebee1…  Explore          -      -  Context self-report probe
2026-08-09T05:25:33+0000  ee0ebee1…  general-purpose  -      -  Context self-report probe
```

So the delegation log is **not** blind to non-`k-*` dispatch — a pre-existing line from
2026-07-05 (`claude-code-guide`) already showed this, and the probes confirm it
deliberately. But the model column is empty for every built-in: `bound_model_for` resolves
a model only through `name → tier → binding` in the registry, and a built-in has no
registry row. Downstream, `coverage_map.py` and the stats digest therefore **undercount
built-in dispatch** — the dispatch is visible, its cost is not.

### 1.4 SessionStart roster does not reach any subagent

The k-* delegate roster injected by `session-start-agent.py` was **ABSENT** in all three
subagent types — including `k-explorer` itself. SessionStart context is main-chain only.
This matters because `general-purpose` **has the `Agent` tool**: it can re-delegate, but
it cannot name a `k-*` delegate it was never told exists.

### 1.5 Declared tool sets are stale against the live harness — **new finding**

`routing.py` `AGENT_SPECS` declares `tools="Read, Grep, Glob, Bash"` for three agents
(`routing.py:363`, `:469`, `:502`), and the generated frontmatter carries it verbatim.
Probe C dispatched `k-explorer` and made it *attempt* the calls:

```
GREP: UNAVAILABLE
GLOB: UNAVAILABLE
Available tools: Read, Bash
```

Claude Code 2.1.221 has **no `Grep`, `Glob` or `MultiEdit` tool at all** — not as a direct
tool, not as a deferred one (verified against the harness tool inventory, and consistent
with the tool lists `Explore` and `general-purpose` self-reported). The consequence is
concrete: **`k-explorer`, akmon's read-only *sweep* delegate, runs without its sweep
tools** — `Read` and `Bash` only. The declaration fails silently; nothing warns.

The same staleness is wired in two more places:

- `bin/sync.py:262` matcher `Edit|Write|MultiEdit` and `:278` matcher
  `Bash|Edit|Write|MultiEdit|Task|Agent|Read|Grep|Glob` — the `MultiEdit`, `Grep`, `Glob`
  alternatives can never match, so the delegation nudge's read/sweep axis (D2-8) now sees
  only `Read`.
- `hooks/claude_adapter.py:12,14` — `EDIT_TOOLS` includes `MultiEdit`, `READ_TOOLS`
  includes `Grep`/`Glob`; dead entries.

This is the first time the "probes are point-in-time; a harness update invalidates them"
risk named in the theme-2 walkthrough has actually bitten — evidence *for* the N1 re-probe
rule rather than against it.

---

## 1A. P0.1 — Codex arm (measured 2026-08-08 … 2026-08-09)

Added after the report's first date; numbering of §2–§6 is left untouched so existing
references stay valid. Harness **codex-cli 0.146.0**, same pilot consumer `alphavar`, same
questionnaire method. Probes F2/F3/F4 plus two instrumented fixture repositories. Two
differences in method are worth stating before the findings, because both bounded what the
run can claim:

- **Runs are headless** (`codex exec --sandbox read-only -C /home/ai/workspace/alphavar`),
  not the interactive TUI. The three injection channels observed here — `world_state`,
  hook-emitted developer messages, and turn forking — are the same ones a TUI session uses,
  but the equivalence is argued, not measured.
- **Agent self-reports were not trusted.** Every claim below is read out of codex's own
  rollout under `~/.codex/sessions/`. This was forced: probes F and F3 reported a workspace
  root of `alphavar` from `git rev-parse` while codex's `session_meta cwd` was
  `/home/ai/workspace/akmon`, and both runs were void as a result. The child's model
  self-report ("GPT-5") was likewise wrong. A probe that asks an agent about its own harness
  answers about the harness the agent *believes* it is in.

### 1A.1 `@`-imports are not expanded — the always-on guardrails never load

Codex delivers `AGENTS.md` verbatim in `world_state.agents_md` and does **not** resolve the
`@path` import lines inside it. Measured on the F4 parent's rollout:

```
world_state.agents_md.directory = /home/ai/workspace/alphavar
world_state.agents_md.text      = 12 505 chars
  contains "@_aitna/.akmon/guardrails/_common.md"  → True   (as literal text)
  contains "Persistent artifacts"                   → False
  contains "Privilege escalation"                   → False
```

alphavar's `AGENTS.md:41,43` import `_common.md` and `python.md` precisely so the always-on
rules load at session start; on Claude that works. On Codex both files are inert — the
common guardrail's English-artifacts rule, the commit-ownership rule and the
privilege-escalation section are simply absent from every Codex session, parent and child
alike. Corroborated independently by the earlier probe D self-report (Q2, Q3 → `ABSENT`).

This confirms the C39 / D2-13 claim, until now assumed rather than measured, and it fixes
the shape of the gap: **not** "guardrails arrive weakened", but "the import mechanism akmon
relies on is Claude-only". Whatever a consumer's `AGENTS.md` states inline does arrive; only
what it delegates to an import does not.

### 1A.2 A subagent gets the workspace file, not the injected context

`fork_turns` decides what a child inherits, and it decides it for the *whole* channel, so
the two runs must be read together:

| | parent | child, `fork_turns="none"` | child, `fork_turns="all"` |
|---|---|---|---|
| `AGENTS.md` | yes | **yes** (own `world_state`) | yes |
| `@`-imported guardrails | no | no | no |
| `[akmon]` SessionStart text | **yes** | **ABSENT** | yes |
| own identity | `/root` | `/root/k_explorer` | `/root/k_explorer` |

The `fork_turns="all"` column is not evidence of delivery: the child's rollout opens with
the parent's own message ids (`msg_019fee9a-e6fe-…`), i.e. it is a copy of the parent's
turns. With the fork removed, the child still receives `AGENTS.md` through its own
`world_state` — codex re-derives it from the workspace — but receives nothing the akmon
SessionStart hook injected.

So the Codex gap is narrower than the Claude one (§1.4, where the roster reached no subagent
at all) and differently placed: what fails to propagate is exactly akmon's **dynamic**
channel. The active-agent declaration, the D2 pending counter and the delegation-default
reminder are parent-only. A Codex delegate is therefore governed by whatever the consumer
wrote inline in `AGENTS.md`, and by nothing akmon computes at session start.

### 1A.3 Agent identity is real, and the model pin holds

`collaboration.spawn_agent` takes `agent_name`, `task_name`, `model` and `fork_turns` as
separate parameters. The spawn under akmon's own delegate name was **rejected** —
`agent_name must use only lowercase letters, digits, and underscores` — which is the finding
that forced [ADR 0011](../../decisions/0011-agent-name-notation-k-underscore.md); under
`k_explorer` it succeeds, and the name is a real addressable identity, not a label: codex
records the dispatch as `author: "/root"` → `recipient: "/root/k_explorer"`.

The **model pin is honoured**, which answers for Codex the question §1.2 answered for
Claude. Requesting `gpt-5.6-terra` for the child produced `thread_settings_applied
{"model": "gpt-5.6-terra", …}` and a child `turn_context` carrying the same model — while
the child's own answer to "which model are you?" was `GPT-5`. The pin is enforced by the
harness and is *not* observable to the agent, so the leverage principle's enforcement point
exists on Codex too.

### 1A.4 The advisory hook surface is inert — and it is two defects, not one

Hooks execute (`hook: PreToolUse` ×3 + `Completed` ×3 on a write), and Codex does deliver
PreToolUse `additionalContext` to the model — a fixture hook returning a marker string had
it quoted back. Yet no akmon advisory hook has ever produced output on Codex. Two
independent causes, both now backlog items:

- **[C48](../../TASKS.md)** — `codex_adapter.file_paths` looks for the patch body under
  `patch`/`raw`, but codex 0.146.0 puts it under `tool_input["command"]`. All three wired
  PreToolUse hooks return `None`.
- **[C47](../../TASKS.md)** — patch bodies carry repo-relative paths (`*** Add File: …`),
  and `is_planning_doc` only matches absolute ones. So repairing C48 alone still leaves
  `analysis-guard` — the hook guarding the owner's standing analysis-before-mutation rule —
  mute. Hence C48 is ordered behind C47.

### 1A.5 `deny` **is** enforced — and the model routed around it in one turn

The one enforcement result that is not a defect in akmon's code, and the most consequential
finding of the Codex arm. A fixture hook returning
`{"permissionDecision": "deny"}` on matcher `Edit|Write|apply_patch|shell` was given a
plain "create probe.txt" task:

```
call 1  tools.apply_patch(…)        → Script error: Command blocked by PreToolUse hook: N2 probe …
call 2  tools.exec_command({cmd: "apply_patch <<'PATCH' … PATCH"})  → exit 0
        file created, task reported DONE
```

The hard deny works: codex refuses the tool call and surfaces the reason. But the model, on
its own initiative and without being asked to circumvent anything, re-issued the identical
`apply_patch` through the shell — and no hook saw it, because none of the four matcher
alternatives in that fixture covers the shell route.

**Which matcher does cover it — measured, after an earlier reading of this run named the
wrong one.** A fixture with one hook per matcher, a plain `echo` task, and a plain patch
task, on codex 0.146.0:

| matcher | shell call | `apply_patch` call | `tool_name` codex reports |
|---|---|---|---|
| `Bash` | **fires** | — | `Bash`, `tool_input.command` = the command string |
| `exec_command` | no | — | — |
| `shell` | no | — | — |
| `apply_patch` | — | **fires** | `apply_patch`, `tool_input.command` = the patch body |
| `Edit` | — | **fires** | `apply_patch` |
| `Write` | — | **fires** | `apply_patch` |

So codex **normalizes to Claude's matcher vocabulary**: its unified shell tool matches as
`Bash`, and its patch tool matches as `apply_patch`, `Edit` **or** `Write` — all three are
live aliases for the same call, and `tool_name` in the payload is `apply_patch` whichever
alternative matched. `exec_command` and `shell`, the names that appear in the model-facing
tool surface and in the fixture above, match nothing.

Two things follow, and they should not be merged:

1. **Enforcement on Codex is real but matcher-scoped**, and akmon's shipped matcher misses
   the shell route entirely. `bin/sync.py:212` emits `Edit|Write|apply_patch` — three
   working aliases for exactly one route. Every mutation reachable through the shell
   (`apply_patch` heredoc, `python3 -c`, `sed -i`, `tee`, `git checkout`) is unobserved
   today, and will remain unobserved after C47 and C48 are fixed, because the only matcher
   that would see it — `Bash` — is not emitted. New entry **[C49](../../TASKS.md)**.
2. **This is *not* another instance of C46.** The first reading of this probe assumed
   `Edit`/`Write` were dead Claude names on Codex; the table above disproves it. Codex went
   to the trouble of accepting Claude's matcher vocabulary, so the cross-vendor naming
   contract holds here — the defect is a **missing alternative**, not a wrong one. Worth
   recording precisely, because the two diagnoses imply opposite fixes: a name map (C46) vs.
   an inventory of the routes a vendor exposes.

The behavioural half deserves stating plainly for A12: a guardrail expressed as a deny on a
tool name is a guardrail against one *route*, not against an *effect*, and the model treats
a blocked route as an obstacle to solve. Enumerating `Bash` closes today's gap; it does not
make a deny unbypassable, since a denied effect stays reachable by any route not enumerated.
Any enforcement claim akmon makes must name the route it covers.

### 1A.6 A native identity carrier exists — and the obvious context carrier does not

Two mechanisms that bear directly on how akmon should give a Codex delegate a role, both
measured on 0.146.0 with fixture repositories.

**Project agent roles work.** `<repo>/.codex/agents/<name>.toml` defines a spawnable role:
a TOML table with `name`, `description`, `developer_instructions` (validated non-blank;
`nickname_candidates`, model/reasoning and sandbox overrides also parsed). A fixture role
whose `developer_instructions` demanded the token `FIXTURE_ROLE_ACTIVE` produced exactly
that token in the child's answer — so this is a real delivery path for role identity, and
the first one Codex offers that akmon can *ship as a file*, the way it ships
`.claude/agents/k_*.md`. Two conditions, both easy to miss:

- **The project must be trusted.** The same file in an untrusted repo yields
  `unknown agent_type 'probe_role'`; `$CODEX_HOME/agents/*.toml` is read regardless.
  Discovery is trust-gated exactly like hooks.
- **`agent_type` is not in the model-facing tool schema.** The spawn tool as shown to the
  model exposes `task_name`, `fork_turns`, `model` and `message`; asked directly, the model
  reported no `agent_type` parameter at all. The router validates and honours it anyway. So
  shipping role files alone is **inert** — a parent that is not explicitly told to pass
  `agent_type` will never select a role.

**`SubagentStart` does not fire.** The event name exists in the shipped protocol enum
(`PreToolUse · PermissionRequest · PostToolUse · PreCompact · PostCompact · SessionStart ·
SessionEnd · SubagentStart · SubagentStop`) with `agent_type` / `agent_transcript_path`
fields, which makes it the obvious fix for the parent-only gap of §1A.2. It is not usable
in this build: a fixture `SubagentStart` hook — tried both with `matcher: ".*"` and with no
matcher, in the same `hooks.json` shape that fires `SessionStart` in the same repo — never
executed, wrote no payload, and the child reported `ABSENT` for its marker. Recorded as
measured-absent rather than unsupported: an enum entry with no dispatch is exactly what a
feature looks like the release before it ships, so this is an N1 re-probe item.

Net for the design question: **role identity has a native carrier today
(`.codex/agents/*.toml` + an explicit `agent_type`), dynamic per-session context does not.**
Anything akmon computes at session start — D2 counters, routing status, the active-agent
declaration — reaches a Codex child only if the parent puts it in the task message.

---

## 2. P0.3 — guardrail ↔ hook invariant inventory (as-is, no checker)

Pairs found between `guardrails/_common.md` rule sections and `hooks/hook_core.py`
enforcement. Three classes:

**A. Declared pairs — the prose names its enforcer (3).**

| Guardrail § | Enforcer | Decision |
|---|---|---|
| Privilege escalation | `privilege_escalation_guard_result` (`_SUDO_RE = \bsudo\b`) | `deny` |
| Commits & ownership | `git_commit_guard_result` (+ Co-Authored-By) | `ask`/`deny` |
| Analysis before mutation | `analysis_write_result` / `analysis-guard.py` | advisory |

**B. Undeclared pairs — a hook enforces the rule, the prose never says so (2).**

| Guardrail § | Enforcer | Constants |
|---|---|---|
| Route by task kind — the tier floor | `delegation_nudge_result` | thresholds 10 (advisory) / 20 (ask) |
| Verify against reality → Owner-verify | `d2_ledger_reminder_result` + `d2_sensitive_paths` | per-project globs |

**C. Orphan enforcer — a hook with no rule section owning it (1):**
`role_on_code_result` / `role-on-code.py`. No `guardrails/*` section states the rule it
enforces.

**Prose-only rules (no deterministic enforcer):** artifacts-English / chat-language,
Secrets, Documentation hygiene, Reuse over re-implementation, Scope discipline,
API shape (subject first), "don't duplicate what the code already states".

**Input for A12/P1.2:** the invariant canary must cover **5 pairs, not 3** — classes A+B —
and class C needs a disposition (give the hook a rule owner, or reclassify it). Note the
canary's cheapest form is available for class A only, where the prose already carries the
enforcer's name as a checkable anchor.

---

## 3. P0.2 as-is — delivery channels and OS surface (measurement, no declaration)

- **Shell dependence is real and undeclared.** Claude wiring emits
  `python3 "$CLAUDE_PROJECT_DIR/<hooks>/<script>"` (`sync.py:252`); Codex wiring emits
  `python3 "$(git rev-parse --show-toplevel)/<hooks>/codex-hook.py"` (`sync.py:203`) — a
  command substitution, i.e. a POSIX shell is required, and `python3` must be on PATH
  (Windows ships `python`). akmon is **de facto POSIX-only**; nothing states it. This is
  W9 with a concrete mechanism attached.
- **No `timeout` field** in either generated hook wiring — W8 confirmed from the wiring
  side, complementing the unbounded `json.load(sys.stdin)` already recorded.
- **README matrix volume:** 8 capabilities × 4 vendors = 32 cells; 16 are ❓
  (Gemini/Copilot columns nearly whole), 3 are ❌ (all Codex). One Codex cell
  ("Generic subagent launch") cites live verification on 0.144.1.

## 4. P0.4 as-is — the de-facto source/generated boundary and always-loaded volume

**Generated (owned by `sync.py`, `GENERATED_MARKER = "Generated by "`):** `CLAUDE.md`,
`.github/copilot-instructions.md`, `GEMINI.md`, `.codex/README.md`, `.codex/hooks.json`,
`.claude/settings.json`, `.claude/skills/*/SKILL.md`; in `package` mode additionally the
materialization under `<aitna>/.akmon/` (hooks `*.py`, `guardrails/*`,
`tools/model_routing/*`, `d2_ledger.py`) plus the generated keys of `.akmon.toml`.

**Hand-owned:** `AGENTS.md` — which is the entry point every vendor pointer redirects to.
The boundary exists only as a per-file banner; there is no list, and nothing states which
hand-owned files are load-bearing.

**Always-loaded volume, measured on alphavar (package mode):**

| File | Lines | Bytes |
|---|---:|---:|
| `CLAUDE.md` (generated pointer) | 12 | 476 |
| `AGENTS.md` (hand-owned, `@`-imported) | 232 | 12 651 |
| `_aitna/.akmon/guardrails/_common.md` | 135 | 7 769 |
| `_aitna/.akmon/guardrails/python.md` | 54 | 2 717 |
| **total in every session's context** | **433** | **23 613** |

For reference, the borrowed cap wshobson uses is ≤150 context lines: the measured chain is
**2.9×** that, and `AGENTS.md` alone is 1.5×. The materialized surface under
`_aitna/.akmon/` (26 files, 360 KB) is **not** context-loaded — it is runtime code — and
must not be counted against a context cap. A12 picks akmon's own numbers; this is the
baseline they are picked against.

---

## 5. What this changes downstream

- **D4 (built-ins vs `k-*`) — data now exists, and it argues for keeping `k-*` as the
  contract** while treating `general-purpose` as an acceptable *policy* carrier and
  `Explore` as a blind spot. Grounds: policy delivery is type-dependent (§1.1), and the
  model pin — the leverage principle's only enforcement point — does not exist for
  built-ins at all (§1.2). The decision rule ("prefer native only where measurably at
  least as effective") is not met on the economics half.
- **P4.1 (SubagentStart injection) — the gate opens.** Drift is reproduced for `Explore`
  (§1.1) and for the roster on every type (§1.4). The gate condition D2 named is satisfied;
  whether to build it is still A15's call.
- **New backlog entry, outside W1–W24: [C46](../../TASKS.md) — stale tool declarations.**
  §1.5 is a live defect, not a plan item: `k-explorer` is missing its sweep tools today,
  and two hook matchers plus two adapter tool sets carry dead entries. The root cause is a
  **second owner** — `hook_core.py:107–113` already models neutral tool *kinds* normalized
  per vendor adapter, and `AGENT_SPECS` bypasses that pattern to name Claude's tools
  directly. Owner-chosen fix: declare **capabilities** (`read`/`search`/`shell`) with a
  per-vendor name map, degrade a missing capability to its Bash equivalent explicitly, and
  add a deterministic check that every declared name is in a known harness inventory — the
  next harness drift then fails loudly. Shipping akmon's own tools over MCP was considered
  and rejected here: that is **P4.3**, gated behind A15/C42, and it buys a new load-bearing
  surface against ADR 0009's zero-runtime-deps constraint. Note the degradation is not
  free: Bash is strictly wider than Grep/Glob, so a read-only delegate's boundary rests on
  the prose in its body rather than on its tool set — worth stating as a contract rather
  than inheriting as an accident.
- **P1.2 scope correction:** 5 invariant pairs, not 3, plus one orphan hook needing a
  disposition (§2).
- **P0.2 → A12:** the OS contract to declare is "POSIX shell + `python3` on PATH", with
  the two concrete call sites as the evidence (§3).
- **Support matrix (A12) — the Codex cells are now fillable, and most of them are `no`.**
  From §1A: always-on guardrails **not delivered** (import mechanism is Claude-only);
  hook-injected session context **parent-only**, never reaching a delegate; advisory hooks
  **inert** pending C47+C48; hard `deny` **enforced but route-scoped**, bypassed through
  `exec_command` in the same turn; model pin and agent identity **working**. A12 should
  declare per **capability**, not per vendor name, and state the *route* each enforcement
  claim covers — a matrix cell reading "hooks: yes" would be true and useless.
- **New backlog entry: [C49](../../TASKS.md) — the Codex PreToolUse matcher misses the
  shell route.** §1A.5 is a live hole, not a plan item, and it is independent of C47/C48:
  fixing those two makes the advisory hooks speak, but they still never see a mutation made
  through the shell, because the matcher that would catch it (`Bash`) is not emitted.
- **[C50](../../TASKS.md) — consumer briefs are keyed by agent name, and the rename orphans
  them.** Found while reviewing the ADR 0011 migration, not by a probe: `routing.py:576–578`
  looks up `briefs.get(spec.name)`, and alphavar's `_aitna/model-routing.json` still keys
  four briefs by `k-mechanic`/`k-validator`/`k-implementer`/`k-reasoner`. The next init or
  rebind writes `k_*.md` without those project specifics **and** deletes the `k-*.md` files
  that carried them — silent loss of consumer-authored behaviour, caused by the very pruning
  that makes the rename a migration.

## 6. Open — not covered by this run

- **Codex arm of P0.1 — now measured (§1A)**, with two limits: runs were headless
  `codex exec` rather than TUI, and `ask` (as distinct from hard `deny`) was never
  exercised. An enforcement cell may be claimed known-good only for the `apply_patch`
  route.
- **Whether a Codex delegate can be given akmon context at all — partly answered (§1A.6).**
  Role identity has a shippable carrier (`.codex/agents/*.toml`, trust-gated, requiring an
  explicit `agent_type` the model is not told about); dynamic per-session context has none,
  because `SubagentStart` does not dispatch in 0.146.0. Whether the remaining route — the
  parent packing policy into the task message — is acceptable as a *contract* rather than a
  workaround is A12/A15's call, and it is the Codex half of the P4.1 question.
- **`.codex/agents/*.toml` beyond the smoke test.** Model/reasoning/sandbox overrides in a
  role file were parsed but not exercised; whether a role can be pinned to a tier the way
  `k_*.md` frontmatter pins one is the measurement D4's Codex arm would need.
- **`fork` and `Plan` built-in types** were not probed — `Explore` and `general-purpose`
  were chosen as the extremes of the read-only/full-capability axis.
- **Whether `general-purpose`'s full context arrives via the same path a main-chain
  session uses** (project `CLAUDE.md` import chain) or via a separate injection — not
  distinguished by these probes; matters only if A15 designs injection.
