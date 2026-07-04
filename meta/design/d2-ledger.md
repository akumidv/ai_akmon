# Design — D2 ledger: mechanical tracking of owner-verification points

> **Status: locked — §4 decisions owner-confirmed; ready for phased build (C11).**
> Task: [TASKS.md](../TASKS.md) C11. Companion to
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

1. **Ledger (data)** — `_aitna/D2_LEDGER.md`: one entry = one verify point:
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

The floor rule this mechanizes is akmon's (guardrails/_common.md "Owner-verify any
change to math, data shape, or architecture"), so the mechanism belongs in `ai_akmon`
(tool + hooks, wired by `sync.py`) with the **sensitive-path config supplied by the
project** (for alphavar: `src/**/lib/**`, `src/**/schemas/**`, `entities/`, pricing
code). Same SHARED-mechanism / LOCAL-config split as model routing.

## 4. Decisions (locked)

| # | Question | Decision | Why |
|---|----------|----------|-----|
| 1 | ledger format | **Markdown table** in `_aitna/D2_LEDGER.md`, parsed by the tool | the page is owner-read first, tool-parsed second — JSON would kill readability; parse md, add a sidecar only if it proves brittle |
| 2 | entry id | `D2-<n>`, monotonic | so chat and commit messages can cite one verify point (`verified in D2-3`) |
| 3 | D2-sensitive paths | **project config** (§3); start narrow (`src/**/lib/**`, `src/**/schemas/**`, `entities/`, pricing), widen on misses | akmon can't know where a given project's math lives; a narrow start avoids reminder-fatigue, misses teach the widening |
| 4 | pre-commit strictness | **warn first**, promote to red once the habit holds | a red gate before the fill-habit exists gets routed around; warn builds the habit, then tighten |
| 5 | verified-entry retention | `## Verified` section in the same file; sweep to an archive when long | keeps the live page short (open items on top) without losing the audit trail — same pattern as TASKS/TASKS_ARCHIVE |

## 5. Mechanism (resolved gaps)

Four points §4 left implicit, resolved so the build has no open forks:

- **A — config home.** The sensitive-path globs live in the project's `.akmon.toml`
  (new `[d2_ledger] sensitive_paths = [...]` key), read by the tool and both hooks —
  the same file model routing already reads. No new config surface.
- **B — how an entry becomes `verified`.** The owner (or the agent on the owner's word)
  runs `python …/d2_ledger.py verify D2-3 --commit <sha>`: the tool moves `D2-3` to
  `## Verified` and stamps the landing commit. Status never flips by a bare file edit —
  the transition is a deliberate act, matching D2 ("owner verifies").
- **C — gate placement.** The pre-commit check is a **separate** `d2_ledger.py check`
  (warn-first), *not* folded into `git-commit-guard` — commit-guard owns the D5
  push/commit-ownership veto and must stay single-purpose; the D2 warn is advisory and
  independently tunable.
- **D — attachment fields.** The entry schema carries optional `draft:` and
  `second_opinion:` fields now (empty until used), so C16's gate-pack / second-opinion
  digest can attach the reasoner's rationale and the independent review to the same
  entry (§2.5) without a later schema migration.

## 6. Build phases (C11)

1. **Ledger + tool** — `tools/d2_ledger/d2_ledger.py`: `add` / `list` / `verify` / `check`
   over `_aitna/D2_LEDGER.md`; stdlib-only, never git (D5); tests mirror the archive tool.
2. **Reminder hook** — PreToolUse on edits to `.akmon.toml`-configured sensitive paths;
   reminds once/session when an edit lands with no matching pending entry (marker in tempdir,
   same throttle pattern as delegation-nudge).
3. **SessionStart counter** — `D2: N pending` appended to the model-routing status line;
   owner-addressed (dual-channel `systemMessage`, per ADR 0006) when `N > 0`.
4. **Pre-commit `check`** — warn-first gate (§4#4, §5C); wired into the pre-commit pipeline
   doc, not commit-guard.
5. **ADR** — [ADR 0007](../decisions/0007-d2-ledger.md) records the locked model (written
   upfront to survive context churn; wording refined as the build lands, this design stays
   the detail owner).
