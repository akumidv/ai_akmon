# Review — ideas and approaches from ponytail for akmon (2026-07-18)

> **Point-in-time review** (review role, findings snapshot). Examined a clone of
> [DietrichGebert/ponytail](https://github.com/DietrichGebert/ponytail) at
> `.review/ponytail`, commit `14a0d79` (2026-07-10), package version 4.8.4.
> akmon state: working copy of `main` after PR #1 (package mode).

**Owner request.** Look at what could be borrowed from the ideas and approaches
of similar projects, using ponytail as the example.

---

## 1. What ponytail is, and how it differs in class

ponytail is **one behavioral skill** (the "lazy senior dev": a 7-rung YAGNI
ladder before writing any code) plus a very mature **distribution shell**:
6 skills, intensity levels (`lite|full|ultra|off`), lifecycle hooks, a
statusline, an MCP server, and adapters for ~20 hosts
(Claude Code, Codex, Gemini CLI, Copilot, Cursor, OpenCode, pi, Hermes, Qoder…).

Class comparison — akmon and ponytail solve **different problems**:

| | akmon | ponytail |
|---|---|---|
| Subject | the whole AI-development discipline: layers, roles, model routing, gate audit, learn loop | one rule ("the minimal solution") + its delivery |
| Policy | Markdown/JSON, vendor-neutral core | one rule text (`AGENTS.md` ≈ `SKILL.md`) |
| Enforcement | forcing-function hooks (commit guard, delegation nudge) | ruleset injection every turn + modes |
| Proof of value | no measurements | reproducible benchmarks, behavior gates |
| Distribution | mount/submodule + Python package, manual bootstrap | plugin marketplaces, 1–2-command install |

Conclusion: what is worth borrowing is not the *content* (ponytail's rules only
overlap akmon's goals at the edge — reuse/YAGNI), but the **engineering of
delivery, measurement, and robustness**: there ponytail is clearly ahead.

---

## 2. High-value ideas (backlog candidates)

### 2.1. Behavioral benchmarks: prove the standard works

ponytail's strongest suit. Three levels (`benchmarks/`):

1. **Single-shot eval** (promptfoo): 3 arms (no skill / control / skill),
   3 models, 10 runs, median. LOC is a measurement; correctness is a **gate**
   (the generated code is executed: email/debounce/CSV checks really run).
2. **Agentic benchmark**: a headless Claude Code session on a real public repo
   (FastAPI+React), scored on the `git diff` it leaves, 12 tasks × n=4, same
   arms. This was the answer to honest criticism (#126): single-shot overstated
   the effect because of prose in the baseline — and they **published the
   correction** right in the README.
3. **Behavior gates** (`behavior.yaml` + `behavior.js`): what is checked is not
   the rule *text* but the **behavior it produces** (was a calibration knob
   left, was a runnable check left), and **the grader itself is unit-tested**
   (`tests/behavior.test.js`) — the grader is proven without an API key, so the
   eval can be trusted.

**For akmon.** akmon's goal function — "quality per unit of tokens + owner
attention" — is measured nowhere; the vendor-support table is full of ❓, and
the 2026-07-05 review recorded "verification lags construction". Proposal:

- `meta/benchmarks/` with an A/B: a session with akmon hooks vs without, on a
  fixed consumer; metrics — share of delegated tool calls (already written by
  the delegation log at zero cost), orchestrator vs smith tokens, gate verdicts.
- Behavior gates for the key guardrails: "the commit guard actually stops a
  commit to main", "the nudge actually returns the orchestrator to delegating"
  — with a control arm (without the hook the gate must fail — that delta is the
  proof).
- Port the "unit-test the grader separately from the eval" pattern as is.

This also closes N1 (fill the vendor table from experiment, not from docs) —
for ponytail, the experiment *is* the source of its table.

### 2.2. Injecting rules into subagents (SubagentStart)

Via a `SubagentStart` hook, ponytail injects the ruleset into **every**
subagent, with an optional regex scope on the agent type
(`PONYTAIL_SUBAGENT_MATCHER`, unanchored, case-insensitive; an invalid regex →
fail-open, inject).

**For akmon.** Today guardrails reach the `k-*` smiths through their generated
agent files, but akmon has no SubagentStart surface: an arbitrary subagent
(e.g. a spontaneous `general-purpose`) leaves **without** guardrails. Add
`hooks/subagent-guardrails.py` (core + claude_adapter, like the rest) with a
matcher policy of "`k-*` are already equipped — inject only into strangers" —
cheap, and closes a real enforcement gap.

### 2.3. Hook survivability contract: "never block the session"

For ponytail this is an explicit, tested discipline
(`hooks/ponytail-mode-tracker.js`):

- stdin may never deliver EOF (a Windows/PowerShell wrapper swallowed the pipe
  and froze the session — their issue #443) → a 1s timeout fallback with
  `unref()`, a `stdin.error` handler, "process what arrived and exit";
- UTF-8 BOM stripped before `JSON.parse`;
- node missing from PATH → the hook stays quiet instead of erroring on every
  prompt;
- `timeout: 5` on every hook in the wiring;
- a dedicated test file for Windows behavior (`tests/hooks-windows.test.js`);
- a **fallback text embedded in the code**: if `SKILL.md` cannot be read, a
  hardcoded copy of the rules is injected — degradation, not silence.

**For akmon.** akmon's hooks are Python over stdin-JSON — the same risk class.
Worth doing: (a) fix the contract "a hook never blocks and never crashes the
session" in `hooks/README.md` as the norm, (b) add a shared safe entry to
`hook_core` (stdin read timeout, BOM, broken JSON → no-op), (c) emit `timeout`
in the wiring generated by `sync.py`, (d) a degradation test.

### 2.4. Intensity levels + observable state

ponytail: `lite|full|ultra|off` — state in a flag file, default from
env/`config.json`, `/ponytail` with no argument **reports the current level**,
the statusline shows the mode permanently, a level switch is confirmed in
context. Technically elegant: all levels live in **one** `SKILL.md`, and
`ponytail-instructions.js` filters the mode-specific lines at injection time —
one owning artifact, variants derived (exactly akmon's principle).

**For akmon.** Enforcement is currently binary; the delegation nudge already
has two steps (nudge → hard-ask), but the owner cannot officially soften it or
see it. Proposal: an enforcement level (`advise|nudge|enforce|off`) as data
(a flag file in `_aitna/`, default in `.akmon.toml`), plus an `akmon status`
command/skill showing the version pin, active level, role, and hook wiring.
This hits "owner attention" directly: visible state is cheaper than finding
out.

### 2.5. An invariant canary against rule-copy drift

`scripts/check-rule-copies.js`: (1) every instruction copy is byte-compared
against the canonical `AGENTS.md`; (2) for files that cannot be byte-compared
(`SKILL.md` is longer) — an **INVARIANTS** list: load-bearing phrasings
("input validation at trust boundaries", "ONE runnable check"…), each required
to be present in every source; rewording a rule fails CI and reminds you to
propagate it. Honestly marked `ponytail: canary, not full equality`, with an
upgrade path (generate the copies).

**For akmon.** `sync.py --check` catches pointer drift, but nothing catches the
**semantic** drift between `guardrails/*.md` (the prose) and `hook_core.py`
(the code of the same rule). A cheap step in `meta/self_ci.py`: a list of
load-bearing guardrail phrases/constants required to be present both in the
prose and in the hook code (e.g. the commit guard's list of guarded commands).
This is an executable form of the "exactly one owning artifact" principle.

---

## 3. Medium-value ideas

### 3.1. Explicit vendor-support tiers instead of ❓

ponytail does not pretend all 20 hosts are equal: in
`docs/agent-portability.md` each host is tagged with a tier — **plugin-tier**
(hooks + modes + commands) or **instruction-tier** (only the always-on text) —
with the exact list of adapter files and the rule "Keep adapters thin: the host
supports skills/hooks → point at the existing files; it supports only
instructions → keep the copy in sync". Degradation is a supported mode, not a
gap.

**For akmon.** The vendor-support table in the README is already honest, but it
has no degradation model: what is *guaranteed* on an instruction-tier vendor
(Gemini, Copilot) when there are no hooks? Worth defining a minimal
instruction-tier contract (pointer + guardrails text + role rule) and tagging
each table row with a tier. Then ❓ becomes "tier defined, depth unverified" —
and N1 narrows.

### 3.2. A deliberate-simplification marker in code + harvest into a ledger

The convention `ponytail: <ceiling>, <upgrade path>` in a code comment — every
cut corner must name its ceiling and its revisit trigger; the `/ponytail-debt`
skill greps the markers into a ledger and tags `no-trigger` the ones without a
trigger ("those are the ones that silently rot").

**For akmon.** The D2 ledger tracks deferred **feature verification**; there is
no analogous mechanism for deferred **simplifications in code**. A cheap
convention in `guardrails/_common.md` (a marker like
`akmon-defer: <ceiling>, <trigger>`) + a grep harvest in `tools/` (or a D2
extension). The key detail worth copying exactly: **the revisit trigger is
mandatory**, otherwise the marker is just a legitimized TODO.

### 3.3. A plugin carrier for Claude Code

Installing ponytail: `/plugin marketplace add …` + `/plugin install …` — versus
akmon's multi-step manual BOOTSTRAP. akmon's mount/package carriers solve
"a versioned standard inside the repo", but the entry bar is high. A third
carrier — a **Claude Code plugin** (`.claude-plugin/plugin.json` +
marketplace.json: hooks, skills, and commands are picked up automatically) —
would remove the manual hook wiring for the deepest-supported vendor. ponytail
also ships `scripts/uninstall.js` with a correct cleanup of state **outside**
the plugin folder and the warning "run it before removing the plugin — the
script is itself a plugin file"; akmon's detach path in BOOTSTRAP is worth
checking for the same trap.

### 3.4. MCP as a policy delivery channel

`ponytail-mcp`: a tiny MCP server serving the same ruleset as a prompt and as a
read-only tool (with `structuredContent`), with the honest caveat "this is not
a replacement for always-on injection — it is the option for hosts that have no
other surface". Mode resolution reuses the shared config module — every channel
emits identical text.

**For akmon.** The `mcp` archetype already exists in ARCHETYPES; this is
different — MCP as a **transport for the standard itself**, for vendors with no
hooks and no pointers. Inexpensive (a thin wrapper over already-existing
artifacts), closes the tail of the vendor table. Medium priority: tiers (3.1)
come first.

### 3.5. Version-consistency self-check

`scripts/check-versions.js` keeps the version in sync across all manifests
(package.json, plugin.json, marketplace…). akmon's version lives in
`pyproject.toml`/`CHANGELOG`/the consumer's pin; if a plugin carrier (3.3)
appears, such a check in `meta/self_ci.py` becomes mandatory. Useful already
today: `release_check` can cross-check the pyproject version against the latest
CHANGELOG entry.

---

## 4. Low-value but cheap ideas

- **Worked before/after examples** (`examples/` — "survivors": a 404-line date
  picker → 23 lines). akmon has the deep `gate-anatomy.md`; what is missing is
  **short** contrast examples of the effect ("session without the nudge / with
  the nudge", a delegation-log fragment). One screen, before/after, a number.
- **An independent-corroboration section** in the README (other people's
  benchmarks with the caveat "the numbers are theirs, not ours") — a model of
  honest marketing; useful once akmon has its own numbers (2.1).
- **`after-install.md`** — a short post-install cheat sheet; the analog for
  BOOTSTRAP: "what you should see in the first session after attach" (the
  SessionStart hook partly does this, but a checklist for the owner helps).
- **A statusline with the active mode** — together with 2.4: show
  `akmon v0.2.1 · engineer · enforce` in the status line.
- **A FAQ with personality** in the README — ponytail's tone ("Why 'ponytail'?
  You know exactly why") sells well; akmon already has the Etna myth, a FAQ
  could play it out.

---

## 5. What NOT to borrow

- **The fan of ~20 adapters.** ponytail has one rule text — copies are cheap;
  akmon's surface (hooks, routing, roles) is an order of magnitude larger, and
  every adapter is a liability. akmon's current position (deep on
  Claude/Codex, everything else instruction-tier per 3.1) is the right one.
- **Injecting the full ruleset every turn** (ponytail's Qoder path). For akmon,
  with its volume of policy, this is a direct token tax — against the goal
  function; SessionStart + targeted PreToolUse reminders are already more
  economical.
- **A single monolithic rule text.** akmon's layers/roles/profiles are a
  deliberate structure; flattening it into one AGENTS text for portability is
  not needed (what is needed is an instruction-tier digest, not a replacement).

---

## 6. Priority summary

| # | Idea | What it gives | Where it lands | Effort |
|---|---|---|---|---|
| 2.1 | Behavioral/agentic benchmarks + gates with a control arm | proof of the goal function; closes N1 and "verification lags" | `meta/benchmarks/`, delegation log | medium/high |
| 2.2 | SubagentStart guardrail injection with a matcher | closes the enforcement gap for non-`k-*` subagents | `hooks/` | low |
| 2.3 | "Hook never blocks" contract + safe entry in `hook_core` | survivability in real sessions, Windows | `hooks/`, tests | low |
| 2.4 | Enforcement levels + `akmon status` + visible state | less owner attention spent finding out | hooks + `.akmon.toml` | medium |
| 2.5 | Guardrail↔hook invariant canary in self_ci | catches semantic drift between prose and code | `meta/self_ci.py` | low |
| 3.1 | plugin-/instruction-tier tags in the vendor table | turns ❓ into a degradation contract | README, docs | low |
| 3.2 | `akmon-defer:` marker with a mandatory trigger + harvest | simplification debt does not rot silently | guardrails, `tools/` | low |
| 3.3 | Claude Code plugin as a third carrier (+uninstall) | 2-command install | new carrier, ADR | medium |
| 3.4 | MCP server as a transport for the standard | hosts with no hooks/pointers | `tools/` | medium |
| 3.5 | Version-consistency check | mandatory with carrier 3.3 | `self_ci`/`release_check` | low |

Recommended first wave: **2.2 → 2.3 → 2.5 → 3.1** (all low effort, pure
strengthening of what exists), then **2.1** as a separate task — it is the
strategic one: akmon currently has not a single number proving its own goal
function, and ponytail shows such numbers can be obtained reproducibly and
honestly.

---

## 7. Cross-review comparison (added 2026-07-18)

> Added after comparing this report with the independent Codex review of the same
> clone ([review-codex-ponytail-20260718.md](review-codex-ponytail-20260718.md)).
> Sections 1–6 above are left untouched; this section records what the comparison
> adds, where the two reviews disagree, and what each covers uniquely. The two
> load-bearing Codex citations were re-verified against the ponytail sources.

### 7.1. Where the reviews converge (double-confirmed core)

Both independent reviews name the same #1 lever and the same supporting set:
behavioral/agentic A/B benchmarks as the largest gap (this report 2.1 = Codex F1);
policy delivery to subagents (2.2 = F4); OS/shell hook survivability (2.3 = F5);
deliberate-shortcut markers with a mandatory revisit trigger (3.2 = F6); honest
vendor-support tiers (3.1 = part of F5); and the same do-not-copy list (adapter
sprawl, duplicated rule text, shortest-diff as an absolute). Convergence from two
different reviewers is itself evidence the core is right.

### 7.2. Additions from the Codex review (absent above)

1. **The contamination-bug lesson** — the strongest single find. Ponytail nearly
   published a false ~4% result: the plugin's SessionStart hook fired in **every**
   arm, so the baseline was secretly running ponytail. Verified in
   `benchmarks/results/2026-06-18-agentic.md`. The fix is a ready-made isolation
   checklist for any future akmon benchmark (2.1): `--setting-sources project,local`
   to exclude global plugins, exactly one plugin per arm via `--plugin-dir`, a fresh
   repo copy and fresh agent context per cell, workspaces retained for offline
   rescoring. Without this discipline a benchmark lies confidently.
2. **A solution ladder in code-flow** (Codex F2). Section 1 above dismissed
   ponytail's *content* as marginal; that was too quick. The ordered decision
   procedure (need at all → project reuse → stdlib → native platform → installed
   dependency → minimal expression → only then new code) plus the root-cause clause
   ("fix the shared source, not the named symptom") does not exist in
   `pipelines/code-flow.md` as a *procedure* — the individual reuse rules are there,
   the ordering is not. Subordinate to the accepted task and locked design; never
   overrides security/accessibility/trust-boundary/explicit requirements.
3. **A simplicity lens for review** (Codex F3). The `delete / stdlib / native /
   yagni / shrink` tag vocabulary from `ponytail-review` as a named yardstick
   **inside** the existing `review` role — no new role; `net lines removable` as
   supplementary evidence, never as severity.
4. **Evidence classes for learn-loop promotion** (Codex F7). Verified in
   `benchmarks/results/2026-06-22-issue-245-217-comprehension.md`: a logically sound
   new rung (#217) shipped, its behavioral benefit did not reproduce — labeled
   **unproven**, not success. For akmon's PROMOTE step: grade promotion evidence as
   contract/unit-verified · behaviorally demonstrated · no-regression-only ·
   unproven hypothesis · model/harness-specific ceiling. Failure to reproduce never
   becomes positive evidence.
5. **Probe-first discipline for subagent delivery** (Codex F4) — see 7.3.
6. **A support contract as a dimension**: `vendor × carrier × OS/shell × capability`
   (Codex F5). Section 2.3 above covers the *execution* contract (never block);
   Codex adds the *declaration* contract: either officially POSIX-only, or Windows
   generation + CI — but never silently assumed.
7. **Backlog anchoring and role routing.** Codex ties each finding to an existing
   carrier (O5 for evals, N1/A9 for the capability matrix, A3/C6 for subagent
   probes) and names the role that takes it next (`review` probes → `architect`
   lock → `engineer`). The recommendations in sections 2–6 above should land the
   same way instead of floating free.

### 7.3. Recorded divergences (owner decides)

- **Enforcement levels.** This report (2.4) proposes `advise|nudge|enforce|off`;
  Codex (4.1) argues mutable intensity state creates ambiguity about which contract
  is active. Non-contradictory middle: the *observability* half (an `akmon status`
  command, statusline, visible version/role/wiring) is uncontroversial and worth
  keeping; the *mutable strength* half is the contested part and needs an
  architect-level decision before any implementation.
- **SubagentStart injection.** This report (2.2) proposes adding the hook now;
  Codex (F4) proposes live probes first — prove the drift (does a non-`k-*`
  subagent actually miss guardrails on each harness?), then build, and honestly
  distinguish documented / delivered / advisory / enforced in the capability
  matrix, since a fail-open hook is availability, not enforcement. The probe-first
  order is more in akmon's own spirit (verification before mechanism) and is
  adopted in the plan below.

### 7.4. Unique coverage of this report (not in the Codex review)

Kept as-is in sections 2–4; listed so a merge never drops them: MCP as a transport
for the standard itself (3.4); the Claude Code plugin carrier including the
uninstall-script trap (3.3); the version-consistency check (3.5); the
guardrail↔hook invariant canary in `self_ci` (2.5 — Codex only nods at canaries in
its 4.4); the never-block *implementation* specifics (stdin timeout fallback, BOM
strip, embedded fallback ruleset — 2.3); deriving mode variants from a single
`SKILL.md` at injection time (2.4); and the low-cost polish items (after-install
checklist, before/after examples, statusline) in section 4.

---

## 8. Phased implementation plan

Moved to the standalone, alternative-agnostic plan:
[plan-akmon-from-alternatives-20260718.md](plan-akmon-from-alternatives-20260718.md)
(draft — NOT accepted; pending owner walkthrough). That file reframes the
findings of this review and the Codex review as akmon weaknesses (W1–W16),
adopted concepts, explicit non-goals, open owner decisions (enforcement levels;
SubagentStart timing), and phases P0–P5 with the dependency spine. This review
stays a point-in-time snapshot; future alternatives extend the plan file, not
this one.
