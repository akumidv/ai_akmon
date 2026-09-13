# Capability matrix

What akmon **ships** on each vendor harness, recorded as six independent answers per claim
instead of one glyph. A `✅` cannot say whether a capability is documented, whether the wiring
akmon generates actually reaches the harness, what it does at the tool boundary, or what happens
when it crashes — so this file asks each question separately and requires a citation for every
answer that came from a measurement.

**The six axes.**

| axis | what it answers | values |
|---|---|---|
| `documented` | do akmon's shipped docs state this capability? | `yes` · `no` |
| `delivered` | does the wiring akmon generates actually reach the harness? | `yes` · `no` · `unmeasured` |
| `route` | exactly where it is wired: `vendor` · `version` · `event` · `matcher` | a value per coordinate, `n/a` when not hook-routed, `unmeasured` when unprobed |
| `effect` | what it does at the tool boundary on the normal path | `none` · `advisory` · `ask` · `deny` |
| `crash-posture` | what happens to the action when the mechanism fails | `fail-open` · `fail-closed` · `unmeasured` |
| `evidence` | the probe or report behind the measured answers | a citation, or empty when nothing is measured |

**Two rules bind them.** An `ask` or `deny` effect requires every route coordinate and the crash
posture to be measured — an enforcement claim over an unmeasured route is not a guarantee. And a
claim that measures anything must cite; a claim that measures nothing must cite nothing. No claim
is exempt from either rule.

One row is one **claim**: one capability on one harness. A vendor with no measured or shipped
claim has no row — absence here means akmon asserts nothing, not that the capability is missing.
Gemini CLI and Copilot are in that position for everything except the generated pointer.

<!-- akmon:capability-matrix:begin -->

### `AGENTS.md` entry point via generated pointer — Claude Code

- documented: yes
- delivered: yes
- route: vendor=claude-code; version=2.1.221; event=n/a; matcher=n/a
- effect: none
- crash-posture: unmeasured
- evidence: `bin/verify.py` pointers.generated-freshness + `meta/self_ci.py` fixture leg

### `AGENTS.md` entry point via generated pointer — Codex CLI

- documented: yes
- delivered: yes
- route: vendor=codex-cli; version=0.146.0; event=n/a; matcher=n/a
- effect: none
- crash-posture: unmeasured
- evidence: N2 probe inventory (`meta/reviews/alternatives/n2-stage0-probes-inventory-20260807.md`)

### `AGENTS.md` entry point via generated pointer — Gemini CLI

- documented: yes
- delivered: unmeasured
- route: vendor=gemini-cli; version=unmeasured; event=n/a; matcher=n/a
- effect: none
- crash-posture: unmeasured
- evidence:

### Always-on guardrails via `@`-import from `AGENTS.md` — Claude Code

- documented: yes
- delivered: yes
- route: vendor=claude-code; version=2.1.221; event=n/a; matcher=n/a
- effect: none
- crash-posture: unmeasured
- evidence: N2 probe inventory — imports expanded

### Always-on guardrails via `@`-import from `AGENTS.md` — Codex CLI

- documented: yes
- delivered: no
- route: vendor=codex-cli; version=0.146.0; event=n/a; matcher=n/a
- effect: none
- crash-posture: unmeasured
- evidence: N2 probe inventory — `@` lines arrive as literal text, so the guardrails never load

### Session-start context (agent roster, memory, delegation) — Claude Code

- documented: yes
- delivered: yes
- route: vendor=claude-code; version=2.1.221; event=SessionStart; matcher=n/a
- effect: none
- crash-posture: unmeasured
- evidence: N2 probe inventory + `meta/tests/test_adapters.py` payload contract

### Session-start context (agent roster, memory, delegation) — Codex CLI

- documented: yes
- delivered: yes
- route: vendor=codex-cli; version=0.146.0; event=SessionStart; matcher=startup|resume|clear|compact
- effect: none
- crash-posture: fail-open
- evidence: N2 (parent-only `hookSpecificOutput`; akmon wires no `SubagentStart`, which dispatches on 0.153.4 — M62) + N1/F4 run D — a killed hook is discarded and the action proceeds; delivery is additionally host-gated, see N7; on 0.153.4 nothing produces `clear` — `/new` arrives as `startup` (M66); a hook that exits 1 is fail-open too, and Codex shows it `Failed` (M71)

### Commit guard — owner-owned commits at the tool boundary — Claude Code

- documented: yes
- delivered: yes
- route: vendor=claude-code; version=2.1.221; event=PreToolUse; matcher=Bash
- effect: deny
- crash-posture: fail-open
- evidence: `meta/tests/test_hook_core.py` deny contract + D2-11 e2e wrapper runs; a crash is fail-open on 2.1.270 — the C87 guard answers it with exit 0 and an owner notice and the command runs (M69), and a hook that dies with exit 1 lets it run too (M70)

### Commit guard — owner-owned commits at the tool boundary — Codex CLI

- documented: yes
- delivered: no
- route: vendor=codex-cli; version=0.146.0; event=n/a; matcher=n/a
- effect: none
- crash-posture: unmeasured
- evidence: akmon wires no D5 entry in `.codex/hooks.json`; the raw-harness deny N2 measured, and M59 again on the Bash route on 0.153.4, is not shipped support

### Delegation policy reaches the orchestrator — Claude Code

- documented: yes
- delivered: yes
- route: vendor=claude-code; version=2.1.221; event=SessionStart; matcher=n/a
- effect: none
- crash-posture: unmeasured
- evidence: N2 probe inventory + the direct `AGENTS.md` anchor `bin/verify.py` agents.block-anchors requires

### Delegation policy reaches the orchestrator — Codex CLI

- documented: yes
- delivered: yes
- route: vendor=codex-cli; version=0.146.0; event=SessionStart; matcher=startup|resume|clear|compact
- effect: none
- crash-posture: fail-open
- evidence: N2 + `meta/self_ci.py` installed-wheel smoke asserts the phrase in the real hook payload; host-gated delivery per N7; on 0.153.4 nothing produces `clear` (M66); exit 1 is fail-open, shown `Failed` (M71)

### Delegation log and drift nudge — Claude Code

- documented: yes
- delivered: yes
- route: vendor=claude-code; version=2.1.221; event=PreToolUse; matcher=Bash|Edit|Write|MultiEdit|Task|Agent|Read|Grep|Glob
- effect: ask
- crash-posture: fail-open
- evidence: D2-8 live run (advisory and ask both dispatched) + D2-11 escalation tests; a crash is fail-open on 2.1.270 on every tool the matcher names that exists — `Bash` (M69, M70), `Read`, `Edit`, `Write`, `Agent` (M77): the C87 guard's exit 0 with an owner notice and a bare exit 1 both let the call run

### Delegation log and drift nudge — Codex CLI

- documented: yes
- delivered: no
- route: vendor=codex-cli; version=0.146.0; event=n/a; matcher=n/a
- effect: none
- crash-posture: unmeasured
- evidence: akmon wires no delegation entry for Codex; the vendor route is measured on 0.153.4 (M62 — `collaborationspawn_agent`, `SubagentStart`/`SubagentStop`), but no payload contract is chosen

### Generic subagent launch — Claude Code

- documented: yes
- delivered: yes
- route: vendor=claude-code; version=2.1.221; event=n/a; matcher=n/a
- effect: none
- crash-posture: unmeasured
- evidence: N2 probe inventory

### Generic subagent launch — Codex CLI

- documented: yes
- delivered: yes
- route: vendor=codex-cli; version=0.153.4; event=n/a; matcher=n/a
- effect: none
- crash-posture: unmeasured
- evidence: N2 probe inventory — live launch on 0.144.1; again on 0.153.4, with the `SubagentStart`/`SubagentStop` lifecycle (M62)

### Named `k_*` agents and child-model routing — Claude Code

- documented: yes
- delivered: yes
- route: vendor=claude-code; version=2.1.221; event=n/a; matcher=n/a
- effect: none
- crash-posture: unmeasured
- evidence: generated agent files under `.claude/agents/`, pinned by `meta/tests/test_model_routing.py`

### Named `k_*` agents and child-model routing — Codex CLI

- documented: yes
- delivered: no
- route: vendor=codex-cli; version=0.146.0; event=n/a; matcher=n/a
- effect: none
- crash-posture: unmeasured
- evidence: model pin and named identity proven live on 0.146.0, but akmon emits no `.codex/agents/*.toml`, so the capability is not shipped

### Second opinion (cross-vendor review) — Claude Code

- documented: yes
- delivered: unmeasured
- route: vendor=claude-code; version=2.1.221; event=n/a; matcher=n/a
- effect: none
- crash-posture: unmeasured
- evidence:

### Second opinion (cross-vendor review) — Codex CLI

- documented: yes
- delivered: unmeasured
- route: vendor=codex-cli; version=0.146.0; event=n/a; matcher=n/a
- effect: none
- crash-posture: unmeasured
- evidence:

<!-- akmon:capability-matrix:end -->

## Delivery is not capability, on Codex

A correct `.codex/hooks.json` is not sufficient on the ordinary persisted, non-bypass path
measured on codex-cli 0.149.1 ([N7](meta/reviews/n7-codex-hook-delivery-20260825.md)):
project-local hooks are discovered only when `~/.codex/config.toml` carries a
`[projects."<abs root>"]` entry for **that** root — trust does not inherit from an ancestor — and
each entry runs only while its `trusted_hash` is current. A `sync` that changes approved wiring
invalidates the affected approvals: the hash covers an entry within its group, so a matcher-only
change flips every entry in that group, and those entries then stay reported `enabled: true`
while running nothing, with no warning and no diagnostic. Re-approval is `/hooks`; the step is in
the attach and bump procedures ([BOOTSTRAP](BOOTSTRAP.md) §A8, §E, §F). `akmon verify` does not
inspect that host state — that gap is tracked as **C70**.

## What `delivered: unmeasured` is waiting on

The second-opinion rows on both harnesses stand at `delivered: unmeasured`. `sync` writes the
route and `tools/model_routing/second_opinion.py` builds the argv — both pinned by
`meta/tests/test_second_opinion_cli.py` — but that suite runs only `--dry-run` and the skip
branch, so no test has ever watched the argv reach a harness. A dry-run establishes what akmon
emits, never what the harness accepts, and the same distinction across two vendors is the parity
claim `AGENTS.md` requires a live probe for. The probe and the carrier that follows it are tracked as
**N8** (the per-harness probe) and **C72** (the regression carriers and the matrix update that follow from its evidence); until they land, the axis stays unmeasured and cites nothing.
