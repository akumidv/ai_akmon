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

Replace the failed 3,000-input per-pass proposal with route-specific candidate acceptance limits:
**20,000 observed input / 1,000 output tokens for Codex** and **20,000 observed input / 2,000
output tokens for Qwen**. Count the whole CLI-reported request, including harness overhead, against
the input cap. The new Qwen real-packet canary returned a valid TSV at 1,758 output tokens under a
locally configured 2,000-token setting, but it did not reach that limit; it therefore does not show
that a 2,000-token cap is enforced. Its saved `command.json` still describes a 1,000-token
enforcement setting, while its provider overlay and runner setting are 2,000; treat that metadata
field as stale and resolve the discrepancy before a route claim. The previous 1,000-output Qwen
canaries each reported exactly 1,000 output, but the default-thinking call had no final response and
the thinking-disabled call failed TSV validation. Their usage alone does not prove a hard route cap.
The valid 2,000-setting response used `enable_thinking=false`, which changes the scorer condition;
the gateway's honoring of that switch remains unverified. A user authorization for this single
technical canary covers only that exploratory mechanics call. It does not approve a scored V2
condition, a new seal, or qualification dispatch. Any scored Qwen route must use the separately
owner-approved condition and pass a fresh route check under it.

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
- **Qwen thinking-disabled, local output setting 2,000:** a fresh packet ID `g9521230`, one
  correlated provider request, 12,676 input / 1,758 output tokens, zero retries, and zero tool
  calls. The final response passed the TSV parser's exact-header, four-element, verdict, and reason
  checks; it had one leading blank line ignored by the parser and a complete final row. The
  one-shot lock is consumed. The local provider overlay has `max_tokens=2000`, `maxRetries=0`, and
  `enable_thinking=false`; the runner sets the output-token environment value to 2,000. Output did
  not reach 2,000, so cap enforcement is untested. The saved `command.json` enforcement description
  incorrectly says 1,000. Gateway handling of the thinking switch and hard output cap remains
  unknown. This is an altered-condition mechanics pass only, not a P3 score or qualification result.

All four one-shot locks were consumed by their calls. The Qwen routes recorded no tool calls and
no retries; Codex had no observed tool markers and no retries. These provider calls still consumed
resources even though they produced no scoring data. Both thinking-disabled calls must remain
excluded from the default-thinking condition. The user's authorization of `g9521230` is limited to
that one technical canary and does not accept a scored V2 condition.

This allows **at most 240 planned scorer passes**, including route canaries, all qualification and
comparison readings, and every failed or retried attempt. Under the proposed route-specific limits,
let `C` be Codex passes and `Q` be Qwen passes, with `C + Q = 240`; the accepted-pass accounting
envelope is `21,000 × C + 22,000 × Q` tokens. A fixed 120/120 route split yields **5,160,000
tokens**. If the route mix is not fixed, a conservative all-Qwen envelope is **5,280,000 tokens**;
all-Codex would be 5,040,000. These are proposed accounting envelopes, not accepted limits or
guaranteed maxima on actual provider usage. Input limits are post-hoc on both routes, Codex's output
limit is post-hoc, and the Qwen 2,000 setting has not been shown to stop generation at that limit.
A single request can exceed a post-hoc or unverified cap before the stop rule can act, so one overrun
can exceed any aggregate envelope even if dispatch stops immediately afterward. Failed calls and
route-verification probes also consume resources and must be entered at actual usage; missing usage
must fail closed and must not be treated as zero. Before authorization, the owner must select the
route allocation (or accept the conservative envelope) and decide whether its accounting includes
the whole P3 effort, including the four completed real-packet mechanics calls.
The current offline approval validator and usage ledger still hard-code 5,040,000 tokens; they
cannot record either higher route-specific candidate envelope yet. Keep this proposal unselected
and align those tools only through a separately reviewed, versioned update after the owner chooses.

Stop a route immediately if model identity, tool behavior, usage provenance, or either observed
per-pass cap fails. A cap overrun is an execution defect and remains recorded; do not retry or
substitute a call. Neither the 5.16M fixed-mix proposal nor the 5.28M conservative proposal is a
provider-enforced hard billing or token limit. Do not dispatch if the owner requires a hard
aggregate cap that these routes cannot enforce.

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
owner must choose and explicitly accept one resource-control option, decide whether the
route-specific envelope (5.16M at a fixed 120/120 split, or 5.28M if the route mix is unconstrained)
covers only future V2 passes or the whole P3 effort. The four completed real-packet calls used
54,871 actual input-plus-output tokens in total; if the 240-pass ceiling is future-only, record that
usage separately, while if the ceiling covers the whole P3 effort, count those four attempts within
it. The owner must approve the exact default-thinking scorer condition before either scorer runs
and accept that the current CLI routes cannot guarantee a hard aggregate cap because per-pass input limits and the
Codex output limit are post-hoc. Independently, Qwen's approved default-thinking route has not
passed route verification and must pass a new one-shot check before qualification scoring:

- The Qwen default-thinking attempt used the pinned model and remained within the observed token
  thresholds but returned no final answer at the output cap.
- The later `enable_thinking=false` attempt is an altered scorer condition, returned an invalid
  TSV at the same cap, and does not verify gateway support for that setting.
- The later Qwen call configured a 2,000 output setting and returned valid TSV at 1,758 output, but
  did not test whether 2,000 is enforced; it also used `enable_thinking=false`, and its saved
  command metadata incorrectly describes a 1,000 setting.
- The Codex mechanics route passed TSV shape validation, but its caps remain post-hoc and its
  result was explicitly unscored.

Owner approval of cost accounting alone does not clear a failed route. Any route-control change
requires a separate fresh canary and a versioned approval before scoring.

1. **Keep the USD 25 ceiling.** Provide the actual gateway/account rates that apply to the Qwen
   route (including any markup, cache pricing, or fixed fee), provide the Codex route's applicable
   cost basis, calculate the cost of the selected route-specific envelope (up to 5.28M tokens if
   route allocation is unconstrained), and name the person who will
   monitor spend and stop both routes at USD 25. State that a one-call overrun can exceed this
   estimate because the relevant limits are post-hoc. If the estimate exceeds USD 25 or the stop
   method is unavailable, do not dispatch.
2. **Replace the money ceiling with a token-only limit.** Explicitly approve a route mix and its
   accounting envelope (5.16M at a fixed 120/120 split or up to 5.28M if unconstrained), state
   whether completed exploratory calls count against it, and name a human operator to track actual
   usage and stop before another pass would exceed the planned amount. This option makes no USD cost
   claim and does not guarantee actual usage will stay within the selected route-specific envelope
   when per-pass limits are post-hoc; it also does not bound monetary spend while the gateway rate
   is unknown.

Neither option is selected by this proposal. After the owner chooses, update a versioned approval
record and seal the accepted plan; keep this proposal marked NOT AUTHORIZED until then. Preserve
the existing M91/M99 limitations, current subject-run history, 240-pass planned count, actual
provider-call/token ledger, and all P3 stop conditions in that new record. No scorer dispatch is
authorized by this proposal or by the mechanics results above.
