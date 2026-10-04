# A22 P3 scorer plan V2 — proposal only, NOT AUTHORIZED

**Status: draft for owner decision. This document does not authorize scorer or subject calls.**
It is a proposed amendment to scorer mechanics and resource accounting after the failed synthetic
CLI canaries and the later real-packet mechanics attempts. It does not alter `RUN_PLAN.md`, the
current seal, the case packets, the arms, the rubric, or the P3 hypothesis. It must be reviewed,
accepted, and sealed as a new plan before use.

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
request, including harness overhead, against the input cap. The real-packet Qwen calls verified
that the configured 1,000-token output cap is active: both the default-thinking call and the
separate thinking-disabled call used exactly 1,000 output tokens. The default-thinking call spent
that output on a thinking block and returned no final answer. The thinking-disabled call returned
text, but it did not contain the required TSV header and ended in an incomplete fragment. Thus the
1,000-token limit is active, but these attempts do not show that it is sufficient for a valid
Qwen score. The thinking-disabled route changes the scorer condition and is not evidence for the
approved default-thinking route; the recorded overlay also does not prove the gateway honored the
setting. Any future Qwen scorer must use the owner-approved condition and pass a fresh route check.

Codex has no CLI output-limit flag in the inventoried help, so its output cap is post-hoc: inspect
actual usage after each response and fail closed above 1,000. The Codex input cap is also post-hoc
because the CLI does not expose a hard input limit. The Qwen input cap is post-hoc as well. Pre-count
packet material where possible, but do not treat that count as the full CLI request size.

### Observed real-packet mechanics attempts

These attempts used the same production-shaped blinded P3 packet source and fresh opaque packet
IDs. All were explicitly recorded as mechanics-only, with `scored_p3=false` and
`qualification_data=false`; none is a P3 reading or qualification result.

- **Codex default route:** `gpt-6-astra`, one provider invocation, 12,932 input / 153 output
  tokens (27 reasoning-output tokens), zero retries, and no observed tool markers. It returned the
  exact four-column scorer header and all four element rows, so TSV shape validation passed. Its
  outcome was `OBSERVED_MECHANICS_PASS_UNSCORED`; this does not establish a hard input or output
  cap for Codex.
- **Qwen default-thinking route:** `qwen3.8-27b`, one provider request, 12,676 input / 1,000
  output tokens, zero retries, and zero tool calls. Its only assistant content was a thinking
  block; the final result was empty and the attempt failed closed with no TSV.
- **Qwen with thinking disabled:** `qwen3.8-27b`, one provider request, 12,676 input / 1,000
  output tokens, zero retries, and zero tool calls. The private invocation overlay recorded
  `extra_body.enable_thinking=false`; the response was 402 characters across four nonempty lines.
  Its first row failed all four required header fields and the final three-character fragment was
  not a complete TSV row. The attempt failed closed with no TSV. Output usage hit the cap exactly
  and the CLI reported no stop reason, so truncation at the cap is plausible but unconfirmed. No
  outbound request body or gateway acknowledgement was captured, so whether the gateway honored
  `enable_thinking=false` remains unknown.

All three one-shot locks were consumed by their calls. The Qwen routes recorded no tool calls and
no retries; Codex had no observed tool markers and no retries. These provider calls still consumed
resources even though they produced no scoring data. The separate thinking-disabled call must
remain excluded from the default-thinking condition.

This allows **at most 240 planned scorer passes**, including route canaries, all qualification and
comparison readings, and every failed or retried attempt. The **5,040,000-token figure is an
accepted-pass accounting envelope**, calculated as 240 × (20,000 input + 1,000 output); it is not
a guaranteed maximum on actual provider usage. The input cap is post-hoc on both routes and the
Codex output cap is post-hoc. A single request can exceed a post-hoc cap before the stop rule can
act, so one overrun can exceed the aggregate envelope even if dispatch stops immediately afterward.
Failed calls and route-verification probes also consume resources and must be entered at their
actual usage; missing usage must fail closed and must not be treated as zero. Before authorization,
the owner must decide whether this envelope covers only the proposed V2 passes or the whole P3
effort, including the three completed real-packet calls.

Stop a route immediately if model identity, tool behavior, usage provenance, or either observed
per-pass cap fails. A cap overrun is an execution defect and remains recorded; do not retry or
substitute a call. The 5.04M figure is not a provider-enforced hard billing or token limit. Do not
dispatch if the owner requires a hard aggregate cap that these routes cannot enforce.

Before qualification scoring, require a real-packet route check under the exact owner-approved
scorer condition. The completed Codex mechanics attempt passed TSV shape checks but was recorded
unscored; the Qwen default-thinking attempt failed to return a final response. The thinking-disabled
Qwen attempt used a different condition and also failed TSV validation, so it cannot clear or
replace the default-thinking route check. Do not count any of these existing mechanics attempts as
ordinary P3 scorer readings. Any new route check must use a fresh packet ID and one-shot lock, match
the pinned model, return the complete required TSV, report correlated usage, stay within the
accepted per-pass limits, preserve blinding, and record zero tool calls/retries. Any mismatch fails
the route; no substitution or retry may hide the failed attempt. Include every such provider call
and its actual usage in the owner-approved resource ledger before dispatch.

Continue to fail closed on tool events, identity mismatch, missing usage, malformed/incomplete
TSV, cap breach, uncorrelated request provenance, or any retry. The existing M91 limitation remains:
absence of recorded tool events does not prove hidden tool definitions were unavailable. Record
both route versions, exact model identity, settings, per-pass input/output use, event/tool audit,
attempt outcome, and the ledger before advancing to the next packet.

## Owner choice required before a new seal

The present approval records unknown Qwen gateway pricing and no named cost-stop operator. The
owner must choose and explicitly accept one resource-control option, decide whether the 5.04M
accepted-pass envelope includes the three completed real-packet calls, and approve the exact
default-thinking scorer condition before either scorer runs. The owner must also accept that the
current CLI routes cannot guarantee a hard aggregate cap because per-pass input limits and the
Codex output limit are post-hoc. Independently, Qwen's approved default-thinking route has not
passed route verification and must pass a new one-shot check before qualification scoring:

- The Qwen default-thinking attempt used the pinned model and remained within the observed token
  thresholds but returned no final answer at the output cap.
- The later `enable_thinking=false` attempt is an altered scorer condition, returned an invalid
  TSV at the same cap, and does not verify gateway support for that setting.
- The Codex mechanics route passed TSV shape validation, but its caps remain post-hoc and its
  result was explicitly unscored.

Owner approval of cost accounting alone does not clear a failed route. Any route-control change
requires a separate fresh canary and a versioned approval before scoring.

1. **Keep the USD 25 ceiling.** Provide the actual gateway/account rates that apply to the Qwen
   route (including any markup, cache pricing, or fixed fee), provide the Codex route's applicable
   cost basis, calculate the cost of the 5.04M accepted-pass envelope, and name the person who will
   monitor spend and stop both routes at USD 25. State that a one-call overrun can exceed this
   estimate because the relevant limits are post-hoc. If the estimate exceeds USD 25 or the stop
   method is unavailable, do not dispatch.
2. **Replace the money ceiling with a token-only limit.** Explicitly approve the 5.04M accepted-pass
   accounting envelope, state whether completed exploratory calls count against it, and name a
   human operator to track actual usage and stop before another pass would exceed the planned
   amount. This option makes no USD cost claim and does not guarantee actual usage will stay within
   5.04M when per-pass limits are post-hoc; it also does not bound monetary spend while the gateway
   rate is unknown.

Neither option is selected by this proposal. After the owner chooses, update a versioned approval
record and seal the accepted plan; keep this proposal marked NOT AUTHORIZED until then. Preserve
the existing M91/M99 limitations, current subject-run history, 240-pass planned count, actual
provider-call/token ledger, and all P3 stop conditions in that new record. No scorer dispatch is
authorized by this proposal or by the mechanics results above.
