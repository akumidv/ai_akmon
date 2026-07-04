# Design — D2 ledger: mechanical tracking of owner-verification points

> **Status: living design concept — direction owner-approved (recording confirmed);
> details open (§4).** Task: [TASKS.md](../TASKS.md) C11. Companion to
> [model-routing](model-routing.md) — same rule-plus-hook pattern; the ledger entry
> becomes the unit its verify gates and second-opinion digests attach to.

## 1. Problem

D2 points (changes to math, DataFrame/data shape, architecture — the owner-verify
guardrail) are born mid-dialogue: the agent says "D2 pending" in chat and the remark
drowns in the flow. By commit time neither the owner nor the agent holds a list of *what
exactly awaits verification*. The owner catches Verify manually — the stated pain this
design removes. Session mining for model routing surfaced the same need (a `k-verifier`
agent candidate) — rejected as an agent, because owner dialogue and D2 are never
delegated; the mechanism is **data + hooks**.

## 2. Shape — ledger data, one rule, three code touchpoints

1. **Ledger (data)** — `_forge/D2_LEDGER.md`: one entry = one verify point:
   *what* changed (file/function/formula, with a `file:line` anchor), *kind*
   (math / data-shape / architecture), *status* `pending → verified` (verified entries
   carry the commit that landed the change; no dates — git history is the timeline).
   This file is the page where Verify is caught — not the dialogue's memory.
2. **Fill rule** — the agent adds an entry the moment it makes a D2-sensitive change
   (the rule); a **PreToolUse hook** on edits to D2-sensitive paths reminds when an edit
   arrives without a ledger entry this session (the enforcement — same
   rule-plus-hook split as commit-guard and analysis-guard).
3. **Session status** — the SessionStart hook adds a counter to the same status line as
   model routing: `D2: 3 pending`. One command (`python …/d2_ledger.py list`) prints the
   open entries.
4. **Pre-commit gate** — the diff touches D2-sensitive paths while the ledger has
   pending (or missing) entries → warn (strictness open, §4). Verify stops being
   skippable by momentum.
5. **Routing integration** — a ledger entry is the *unit of the verify gate*: the
   reasoner's draft explanation and the second-opinion digest attach to the entry, so
   the owner opens one item and sees what changed, the drafted rationale, and where the
   independent review disagrees — then verifies.

## 3. Layer

The floor rule this mechanizes is keystone's (guardrails/_common.md "Owner-verify any
change to math, data shape, or architecture"), so the mechanism belongs in `ai_keystone`
(tool + hooks, wired by `sync.py`) with the **sensitive-path config supplied by the
project** (for alphavar: `src/**/lib/**`, `src/**/schemas/**`, `entities/`, pricing
code). Same SHARED-mechanism / LOCAL-config split as model routing.

## 4. Open points

| # | Question | Leaning |
|---|---|---|
| 1 | ledger format | **Markdown table/list** (owner-readable page first), parseable by the tool; JSON sidecar only if parsing md proves brittle |
| 2 | entry id | `D2-<n>`, monotonically increasing; referenced from chat and commits |
| 3 | D2-sensitive paths | project config (see §3); start narrow (lib/schemas/entities), widen on misses |
| 4 | pre-commit strictness | **warn first**, promote to red once the ledger habit holds |
| 5 | verified-entry retention | keep in the ledger under a `verified` section, archive by sweep when long |
