# A22 P3 scorer plan V2 — proposal only, NOT AUTHORIZED

**Status: owner-accepted protocol direction; technical readiness and dispatch remain gated. This
document does not authorize scorer or subject calls.** The owner confirmed the subject-run accounting
rule and directed launch on 2026-10-11; see [ADR 0019 D02](../../decisions/0019-collaboration-guidance-from-a22.md#d02--p3-resource-and-attempt-accounting).
This remains a proposed amendment to scorer mechanics and resource accounting after the failed synthetic
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

The scored subject grid is unchanged: eight cards across two tiers and two repeats under qualification
arm `A` (32 runs); a card × tier stratum qualifies only when both scorers fail the same `A` repeat.
Seal the qualification map before `B`/`C`; continue only with at least four qualifying strata and
at least one from every pair. Score both `B` and `C` twice in each qualified stratum, for up to
64 comparison runs and 96 planned subject runs total. Preserve the absolute 120 two-turn subject
run ceiling and all current stop rules. The 120 total subject-run slots consist of **96 scored runs**
and at most **24 technical or defect attempts**. Every attempt has exactly one class from
`scored`, `technical`, or `defect`. A defect attempt must carry an immutable origin attempt ID;
origin is required at creation and cannot be edited later. Technical and defect attempts do not
become scored observations. Their actual provider usage still counts toward the Codex aggregate.

## Proposed CLI scorer amendment

Keep the two independent blind scorer routes and their existing pins: Codex CLI 0.156.1 with
`gpt-6-astra`, and Qwen CLI 0.24.7 with `qwen3.8-27b`. Each scorer sees one packet at a time with
the frozen prompt, without arm, tier, subject-model, or qualification labels. Keep the two raw
readings independent; do not adjudicate.

Use the same frozen blind packet, prompt, rubric, scorer pass schedule, model pin, no-tools setting,
and no-retry rule for both routes. Keep the pins at Codex CLI 0.156.1 / `gpt-6-astra` and Qwen CLI
0.24.7 / `qwen3.8-27b`. Accept at most **20,000 observed input tokens per scorer call** on either
route, counting the whole CLI-reported request including harness overhead. For Codex, also accept
at most **1,000 observed output tokens per call**, checked after the response. These per-call
observed-usage bounds are validity/mechanics checks, not aggregate economic caps. Qwen has no
aggregate token ceiling. For Qwen, use its default-thinking condition and a
**2,000-token maximum-output setting**; this candidate is based on
the 2026-10-07 unscored canary, whose output was 1,363 tokens and whose response had the exact TSV
shape. That response stayed below 2,000, so provider enforcement of the setting remains untested;
the setting is not a hard cap. The earlier valid 1,758-token Qwen response used
`enable_thinking=false`, an altered condition, and its `command.json` incorrectly describes a
1,000-token setting. Resolve the stale metadata before a route claim. The first default-thinking
2,000-setting attempt failed DNS resolution before provider contact; a fresh one-shot succeeded.
Both attempts remain exploratory and unscored. The successful default-thinking canary recorded a
thinking block, but did not capture gateway acknowledgement of the setting. No scored V2 condition,
new seal, or qualification dispatch is authorized here; any route check must use the accepted
condition and a fresh one-shot packet.

Codex exposes no CLI output-limit flag in inventoried help, and neither route exposes a hard input
limit; check the observed usage after every call and fail closed on an overrun. Pre-count packet
material where possible, but do not treat that count as the full CLI request size. These checks
cannot prevent a single call from overshooting its allowance.

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

The scorer schedule is **exactly 120 accepted readings per model** (120 Codex and 120 Qwen), with
no uncontrolled extra scoring. Preserve all preregistered qualification, comparison, and stop
rules; failed attempts remain recorded and do not become readings or justify retries. Codex's
observed aggregate accounting ceiling for the full P3 quality evaluation is **5,000,000 tokens**.
Known prior Codex P3 usage is 153,614 tokens (126,014 subject-control tokens plus 27,600 scorer
exploratory tokens), leaving **4,846,386 tokens**. This prior debit is a reconstructed aggregate from
existing subject-control and scorer-exploration records; an authenticated event-by-event ledger
covering those historical calls is not available, so the breakdown is provenance-limited and must
not be represented as newly validated per-call accounting. Include every subsequent Codex P3
provider call exactly once, across subject turns, scorer readings, route checks, technical attempts,
and failed/defect calls, in the same observed-usage ledger. Missing usage fails closed and is never
zero. This is an accounting ceiling, not a hard provider cap: input and output checks happen
after a call, so one call can overshoot 5,000,000 before dispatch stops. Qwen has no aggregate token
ceiling; retain usage and session records for every attempt. The offline V2 approval validator,
unified append-only usage ledger, subject driver, and scorer route-check runner are implemented with
regression tests. The ledger binds reservations and usage records to the proposal, packet seal,
approval bytes, and route; accounts for scorer readings, route checks, and subject calls in one
Codex aggregate; keeps Qwen uncapped in aggregate; separates route checks from scored readings; and
fails closed on missing usage, duplicate debits, cap breaches, or a denied approval. Subject attempts
record exactly one of `scored`, `technical`, or `defect`; defect attempts carry an immutable origin
attempt ID. The driver reserves usage before each provider call and closes the reservation from
persisted rollout evidence. These are offline implementation and test results, not evidence that an
owner-accepted V2 seal or operator exists, that any route has passed a live check, or that P3 has
produced a score.

The route-check runner is a real dispatch path in code, but it remains default-denied by the current
approval. The proposed owner-selectable `OBSERVED_NO_RETRY` policy means one CLI process, one
correlated session/turn and usage record, and no CLI-visible retry/error markers. For Qwen it also
requires the generated provider overlay to set `maxRetries=0` and the correlated usage row to report
one request. It records `retry_count: null`: these observations cannot prove that a provider or
transport made no hidden retry. Literal provider-level zero retries is unavailable as a verifiable
policy with the current Codex CLI telemetry and is therefore not a selectable criterion. The
approval field defaults to `UNSELECTED`; this candidate awaits explicit owner acceptance and does not
change the dispatch gate until selected. The accepted subject-run ceiling remains 120, partitioned
into 96 scored and at most 24 technical/defect attempts.

Stop a route immediately if model identity, tool behavior, usage provenance, or an observed
per-call allowance fails. A breach is an execution defect and remains recorded; do not retry or
substitute a call. Stop further Codex dispatch when its observed aggregate reaches 5,000,000; the
ceiling cannot prevent a single-call overrun. Qwen has no aggregate token stop, but still follows
the same fixed reading schedule and preregistered stop rules.

Before qualification scoring, require a real-packet route check under the exact owner-approved
scorer condition. The completed Codex mechanics attempt passed TSV shape checks but was recorded
unscored; the Qwen default-thinking attempt failed to return a final response. The thinking-disabled
Qwen attempt used a different condition and also failed TSV validation, so it cannot clear or
replace the default-thinking route check. Do not count any of these existing mechanics attempts as
ordinary P3 scorer readings. Any new route check must use a fresh packet ID and one-shot lock, match
the pinned model, return the complete required TSV, report correlated usage, stay within the
accepted per-pass limits, preserve blinding, and record zero observed tool calls plus the selected
retry evidence policy. Under `OBSERVED_NO_RETRY`, any observed CLI retry/error marker or failed
route-specific control fails the route; a pass is mechanics-only and makes no provider-level retry
claim. Any mismatch fails the route; no substitution or retry may hide the failed attempt. Include
every such provider call and its actual usage in the owner-approved resource ledger before dispatch.

Continue to fail closed on tool events, identity mismatch, missing usage, malformed/incomplete
TSV, cap breach, uncorrelated request provenance, or any observed retry/error marker. The existing M91 limitation remains:
absence of recorded tool events does not prove hidden tool definitions were unavailable. Record
both route versions, exact model identity, settings, per-pass input/output use, event/tool audit,
attempt outcome, and the ledger before advancing to the next packet.

## Remaining prerequisites before a new seal

The owner has accepted the protocol direction: Codex's 5,000,000-token aggregate accounting ceiling
covers the full P3 effort, including known prior usage and all future Codex provider calls; Qwen uses
the same fixed experimental matrix but has no aggregate token ceiling. The owner also accepted 96
scored subject runs plus a maximum of 24 technical/defect attempts (120 total), exact class values,
and immutable required defect origin. This acceptance does not establish technical readiness, create
a new seal, or authorize dispatch. Keep the exact 120/120 accepted scorer-reading schedule and
preserve usage/session records for both routes. Before
qualification scoring, verify each route on a fresh one-shot under the exact accepted scorer
condition, with model identity, complete TSV, correlated usage, no observed tool calls, and the
owner-selected retry evidence policy. `UNSELECTED` denies route dispatch; selecting
`OBSERVED_NO_RETRY` accepts only CLI/session-observable evidence and cannot establish absence of
hidden transport retries. The
default-thinking Qwen canary on 2026-10-07 returned valid TSV after an initial DNS failure, but
stayed below the configured 2,000 output setting; enforcement remains untested. The older
thinking-disabled 2,000-setting canary does not establish the default-thinking route.

The unified accounting and attempt-class implementation is present and covered by offline tests;
live route validation and scored/qualification results remain absent. Preserve M91/M99 limitations,
current run history, the 96 scored plus 24 technical/defect subject-run partition, actual
provider-call/token records, and all preregistered P3 stop conditions. The approval record remains
default-deny (`owner_accepted=false`, no selected resource option, `dispatch_allowed=false`); it has
no owner-accepted V2 seal, completed preflight, or named human stop operator. The retry criterion
decision above is also outstanding. Keep this proposal marked **NOT AUTHORIZED** until these gates
are resolved, the plan is reviewed and accepted, a new seal is created, and dispatch is separately
authorized. No scorer or subject dispatch is authorized by this document or by the mechanics results
above.
