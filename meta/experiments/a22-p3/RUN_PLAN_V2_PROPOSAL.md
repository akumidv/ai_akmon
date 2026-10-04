# A22 P3 scorer plan V2 — proposal only, NOT AUTHORIZED

**Status: draft for owner decision. This document does not authorize scorer or subject calls.**
It is a proposed amendment to scorer mechanics and resource accounting after the failed CLI
canaries. It does not alter `RUN_PLAN.md`, the current seal, the case packets, the arms, the
rubric, or the P3 hypothesis. It must be reviewed, accepted, and sealed as a new plan before use.

## Unchanged question and experiment

P3 continues to test whether adding the frozen decision-ground routing clause (`C`) to the
current relevant baseline (`B`) improves the subject's decision-ground behavior. The hypothesis,
observable criteria, four matched case pairs, and practical-benefit rule remain exactly as in the
sealed packet: at least three fewer failed `C` runs than `B` under both fixed scorers, with no pair
showing at least two more `C` failures under both scorers. Anything else is inconclusive or worse,
never equivalence. P3 still makes no claim about native consumer delivery, project match, examples,
or the later fresh-task/cold-resumption pilot.

The subject grid is unchanged: eight cards across two tiers and two repeats under qualification
arm `A` (32 runs); a card × tier stratum qualifies only when both scorers fail the same `A` repeat.
Seal the qualification map before `B`/`C`; continue only with at least four qualifying strata and
at least one from every pair. Score both `B` and `C` twice in each qualified stratum, for up to
64 comparison runs and 96 planned subject runs total. Preserve the absolute 120 two-turn subject
run ceiling and all current stop rules.

## Proposed CLI scorer amendment

Keep the two independent blind scorer routes and their existing pins: Codex CLI 0.156.1 with
`gpt-6-astra`, and Qwen CLI 0.24.7 with `qwen3.8-27b`. Each scorer sees one packet at a time with
the frozen prompt, without arm, tier, subject-model, or qualification labels. Keep the two raw
readings independent; do not adjudicate.

Replace the failed 3,000-input/1,000-output per-pass proposal with a target acceptance cap of
**20,000 observed input tokens and 1,000 output tokens per pass**. Count the whole CLI-reported
request, including harness overhead, against the input cap. Qwen's 1,000-token output limit must
be fixed on the installed route using the documented settings/environment mechanism and retained
in the attempt record; the exploratory canary reached exactly 1,000 output tokens. Codex has no
CLI output-limit flag in the inventoried help, so its output cap is post-hoc: inspect actual usage
after each response and fail closed above 1,000. The Codex input cap is also post-hoc because the
CLI does not expose a hard input limit. Pre-count packet material where possible, but do not treat
that count as the full CLI request size.

This allows **at most 240 scorer passes**, including one preliminary real-packet canary per route,
all qualification and comparison readings, and any failed or retried attempts. The planned
accounting envelope is 240 × (20,000 input + 1,000 output) = **5,040,000 aggregate scorer tokens**.
Stop a route immediately if model identity, tool behavior, usage provenance, or either observed
per-pass cap fails. A cap overrun is an execution defect and remains recorded; because the Codex
input/output caps are observable only after a response, the 5.04M envelope is a planned ceiling
for accepted passes, not a provider-enforced hard billing limit. Do not dispatch if the owner
requires a hard aggregate cap that the CLI routes cannot enforce.

Before qualification scoring, send one actual blinded P3 response packet through each route as
the preliminary real-packet canary. Keep those attempts inside the 240-pass total. Require each
to match its pinned model, return the complete required TSV, report actual token usage, stay
within the stated cap, preserve blinding, and record zero tool calls/retries. Any mismatch fails
the route and stops scorer dispatch; no substitution or retry may hide the failed attempt. If both
pass, retain their readings as the first ordinary scorer readings for those packets and continue
the fixed grid. These canaries are scoring attempts and count toward the token/cost budget.

Continue to fail closed on tool events, identity mismatch, missing usage, malformed/incomplete
TSV, cap breach, uncorrelated request provenance, or any retry. The existing M91 limitation remains:
absence of recorded tool events does not prove hidden tool definitions were unavailable. Record
both route versions, exact model identity, settings, per-pass input/output use, event/tool audit,
attempt outcome, and the ledger before advancing to the next packet.

## Owner choice required before a new seal

The present approval records unknown Qwen gateway pricing and no named cost-stop operator. The
owner must choose and explicitly accept one resource-control option before either scorer runs:

1. **Keep the USD 25 ceiling.** Provide the actual gateway/account rates that apply to the Qwen
   route (including any markup, cache pricing, or fixed fee), provide the Codex route's applicable
   cost basis, calculate the 5.04M-token worst-case estimate, and name the person who will monitor
   spend and stop both routes at USD 25. If the estimate can exceed USD 25 or the stop method is
   unavailable, do not dispatch.
2. **Replace the money ceiling with a token-only limit.** Explicitly approve the 5.04M planned
   scorer-token ceiling and name a human operator to track the running token ledger and stop before
   another pass would exceed it. This option makes no USD cost claim and does not bound monetary
   spend while the gateway rate is unknown.

Neither option is selected by this proposal. After the owner chooses, update a versioned approval
record and seal the accepted plan; keep this proposal marked NOT AUTHORIZED until then. Preserve
the existing M91/M99 limitations, current subject-run history, 240-pass total, and all P3 stop
conditions in that new record.
