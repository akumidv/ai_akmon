# 0007 — D2 ledger: mechanical tracking of owner-verification points

- **Status:** Accepted (mechanizes the guardrails/_common.md owner-verify rule; implementation
  C11; details + rationale in the design source, which stays the detail owner).
- **Owner:** akuminov@gmail.com
- **References:** design source [`meta/design/d2-ledger.md`](../design/d2-ledger.md) (§4 locked
  decisions, §5 mechanism, §6 build phases) · backlog [C11](../TASKS.md) · guardrail
  [`guardrails/_common.md`](../../guardrails/_common.md) "Verify against reality" (owner-verify).

## Context

D2 — the owner-verify prime directive (changes to math, DataFrame/data shape, architecture) —
is enforced only by memory today. A verify point is born mid-dialogue ("D2 pending" in chat) and
drowns in the flow; by commit time neither owner nor agent holds a list of *what exactly awaits
verification*, so the owner catches Verify by hand. Model-routing session mining surfaced the same
need (a `k-verifier` agent candidate) — rejected as an agent, because owner dialogue and D2 are
never delegated. The mechanism is **data + hooks**, the same rule-plus-hook pattern as
commit-guard and analysis-guard.

## Decision

Mechanize D2 with a ledger, one fill rule, and code touchpoints. The locked specifics live in the
design (§4/§5); the load-bearing choices:

1. **Ledger data** — `_aitna/D2_LEDGER.md`, a markdown table (owner-read first, tool-parsed
   second): one entry per verify point — *what* changed (`file:line` anchor), *kind*
   (math / data-shape / architecture), *status* `pending → verified`; ids `D2-<n>`, monotonic, so
   chat and commits can cite one point. No dates — the landing commit is the timeline. The tool is
   stdlib-only and **never runs git**: the caller supplies the landing sha (D5 — the owner owns
   commits), so the ledger stays a pure data file the tool only reads and rewrites.
2. **Fill rule + reminder** — the agent adds an entry when it makes a D2-sensitive change; a
   PreToolUse hook on **project-configured** sensitive paths (`.akmon.toml` `[d2_ledger]`;
   SHARED mechanism / LOCAL config, as model routing) reminds once/session when an edit lands with
   no matching pending entry — and stays **silent when the project has configured no sensitive
   paths** (nothing to scope the reminder to; a project opts in before the per-edit nudge starts).
3. **Session status** — the SessionStart hook appends `D2: N pending` to the model-routing status
   line, owner-addressed (dual-channel `systemMessage`, per [0006](0006-orchestrator-detection-corridor-context-pressure.md)) when `N > 0`.
4. **Warn-first gate** — a **separate** `d2_ledger.py check` (not folded into commit-guard, which
   stays single-purpose for the D5 veto) warns when the ledger holds **pending** entries and the
   staged diff touches a sensitive path (project configured none → any pending warns; the owner
   decides). It exits 0 and warns to stderr; `--strict` promotes to red once the fill habit holds.
   A *missing* (never-logged) entry is **not** `check`'s job — it can only see the ledger's pending
   rows, so the per-edit reminder (decision 2) catches the forgotten entry while `check` covers open
   pending at commit time.
5. **Verified transition + routing attachment** — an entry becomes `verified` only by a deliberate
   `d2_ledger.py verify D2-<n> --commit <sha>`, never a bare file edit (matching D2 = *owner*
   verifies); the entry carries optional `draft:` / `second_opinion:` fields so a reasoner
   rationale and independent review attach to the same unit (feeds C16's gate-pack).

## Consequences

- Verify stops being skippable by momentum: the open list is always one command away and shown at
  session start; the owner opens one item and sees change + drafted rationale + independent review.
- New always-on surface (a hook + a status counter). Kept advisory (warn-first) until the habit
  forms, so it does not become friction agents route around.
- The ledger entry is the unit other mechanisms attach to (routing verify gate, second-opinion
  digest, owner-attention metrics C19) — one durable anchor rather than scattered chat remarks.
- Build is phased (design §6): tool → reminder hook → session counter → warn-first check — all four
  landed, and this ADR's wording was reconciled to what shipped: the reminder/`check` division of
  labour (forgotten vs. open-pending), the unconfigured behaviour (reminder silent, `check` warns),
  and the stdlib-only / never-git constraint. The design doc remains the living detail owner.
