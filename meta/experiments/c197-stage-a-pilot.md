# C197 — Stage-A pilot: what the probe costs, and what the seven served ids did on the seed set

Results document for the stage-A pilot of the per-harness model measurement (task C197). The method and the design are not in this tree; the design is named where it is cited.

## Question

What does one full pass of the probe runner cost end to end, what did the seven served ids actually do on the seed item set, and which parts of the suite did the run expose as unfinished? The stage-B cost, extrapolated from the stage-A probe and then measured on the same runner, is the cost half of the question.

## Method

The probe runner (its code is not part of this record) ran over the seed item set `a93-seed-1` (two hand-written cases, three (case, family) pairs) against all seven served ids: 21 endpoint calls and 14 sandboxed hidden-test runs, sequential, under one pinned envelope (temperature 0, a 4096-token output cap, a 180 s timeout, streamed). The gold-sanity gate ran first and passed both cases. Before it, a cost probe of 21 calls (three per id) measured wall-clock and answer length on the same ids, and the cost envelope below reads that probe. The ledger shape (case-set hash, envelope hash, failed gates, stability) comes from an owner measurement of per-stage evals of served models. That harness is not carried here.

## Result

- One pass: 21 calls, 5 min 44 s sequential (model time 329.2 s); 18 scored and 3 deferred, every deferral a cut-off answer at the 4096-token cap.
- Recorded tokens: 8,792 prompt + 14,315 completion. The deferrals' output tokens are missing from that count: the three cut-off calls spent at least 12,288 more completion tokens than the ledger reports (see the graded-run detail, §3.4).
- Fix items: 13 of 14 fix attempts passed the hidden test with no other file changed. The fourteenth, `ornith-1.5-9b` on `fix-symptom`, was deferred at the cap. See the discrepancy note below.
- Hunt item: five of seven ids failed it. Three named the decoy file and decoy function (`pricing.py:discount`), `qwen3.8-flash-next` named the right file and the wrong function, and `minimax-m3.1-flash` answered in prose instead of the required one-line form. `qwen3.8-27b-max` and `qwen3.8-flash-next-max` never finished their answer.
- Every cell fails the `items_scored` gate (it needs 30 scored items; a seed cell holds one).

## Verdict

The stage-A run measured cost and plumbing, not the signal. The seed set is a smoke test, not evidence: its fix items are saturated, and its hunt item is one bit. The probe's cost is now measured end to end rather than extrapolated: the stage-B shape (1,300 calls, sequential) is at least about 3.8–5.7 h, and about 1.4M tokens, before stage-B-shaped prompts are measured. Three runner defects surfaced. Two are fixed in the same stretch (the answer text is now kept; a deferral's usage is now recorded). The third, separating a malformed hunt verdict from a wrong location, is open and is the owner's call, because it changes what a score says.

## What this cannot show

- **No ranking.** Each (model, family) cell holds one scored item, so each cell is n = 1, and the seed set has two cases. The suite cannot separate or rank the served ids, and the claim that the bug families separate the models from the generic controls is untested.
- **No quality claim about any id.** The fix items are saturated, and the hunt item is one bit.
- **No stable latency.** One host, one day, one run; the spread inside one id (for example `qwen3.8-flash-next-max`, 5.6–62.5 s in the cost envelope) is wider than the gaps between the id means.
- **No price.** The token counts are measured; what a token costs is not.
- **No concurrency.** Every call was sequential, so the parallel figures are arithmetic.
- **No Claude reference.** It was not part of this run; the owner's subscription login is not used in an automated job.

## Cost

21 calls; 5 min 44 s sequential; 8,792 prompt + 14,315 completion tokens recorded, plus the deferrals' missing output. Stage-B projection (1,300 calls, 10 models, 130 prompts each): at the measured per-call means, about 3.8–5.7 h sequential, about 544k input and 886k output tokens; both are lower bounds, because stage-B prompts carry the full item context.

## Discrepancy in the source record

The source text states that every id repaired both fix items, and that all fourteen fix attempts that produced an answer passed. The ledger and the per-cell detail show otherwise: `ornith-1.5-9b`'s `fix-symptom` attempt was a deferral, cut off at the 4096-token cap, and it produced no answer. So 13 of 14 fix attempts passed, and 13, not 14, produced an answer. This note uses the ledger's count everywhere.

## Raw materials

The run's own record is copied unchanged into `meta/.ergon/C197-model-measurement/materials/stage-a/`: `ledger.jsonl` (21 rows, one per cell) and `detail/*.jsonl` (21 files, one per cell). The copies keep their bytes and names, because they are sealed run inputs; the endpoint address they record is therefore not scrubbed. The ergon is local and gitignored, and this note and the M-rows stand without it.

## Detail: the stage-A cost envelope

### Environment

| | |
|---|---|
| Host | Linux 6.18.33.2-microsoft-standard-WSL2 (WSL2), 16 cores |
| Endpoint | an OpenAI-compatible endpoint |
| Credential | the endpoint's bearer token is a personal credential; it is not reproduced here and never appears in the probe record |

### 1. The raw numbers

Every row is one call, verbatim from the probe's raw per-call record (not carried into this tree). `seconds` is
wall-clock per call; `chars` is the length of the returned answer text.

| model | case | family | status | seconds | chars | prompt_tok | completion_tok | total_tok |
|---|---|---|---|---|---|---|---|---|
| `minimax-m3.1-flash` | invoice-coupon | fix-traceback | ok | 4.6 | 1024 | 0 | 0 | 0 |
| `minimax-m3.1-flash` | invoice-coupon | fix-symptom | ok | 3.9 | 797 | 0 | 0 | 0 |
| `minimax-m3.1-flash` | inventory-available | hunt | ok | 5.1 | 1323 | 0 | 0 | 0 |
| `ornith-1.5-9b` | invoice-coupon | fix-traceback | ok | 5.2 | 238 | 0 | 0 | 0 |
| `ornith-1.5-9b` | invoice-coupon | fix-symptom | **deferred** | 31.8 | 0 | 503 | 2048 | 2551 |
| `ornith-1.5-9b` | inventory-available | hunt | ok | 23.0 | 19 | 0 | 0 | 0 |
| `qwen3.8-27b` | invoice-coupon | fix-traceback | ok | 6.5 | 543 | 0 | 0 | 0 |
| `qwen3.8-27b` | invoice-coupon | fix-symptom | ok | 16.5 | 530 | 0 | 0 | 0 |
| `qwen3.8-27b` | inventory-available | hunt | ok | 18.9 | 25 | 0 | 0 | 0 |
| `qwen3.8-27b-max` | invoice-coupon | fix-traceback | ok | 10.4 | 530 | 0 | 0 | 0 |
| `qwen3.8-27b-max` | invoice-coupon | fix-symptom | ok | 10.8 | 532 | 0 | 0 | 0 |
| `qwen3.8-27b-max` | inventory-available | hunt | ok | 14.0 | 19 | 0 | 0 | 0 |
| `qwen3.8-27b-nothink` | invoice-coupon | fix-traceback | ok | 2.2 | 543 | 0 | 0 | 0 |
| `qwen3.8-27b-nothink` | invoice-coupon | fix-symptom | ok | 2.3 | 530 | 0 | 0 | 0 |
| `qwen3.8-27b-nothink` | inventory-available | hunt | ok | 0.6 | 19 | 0 | 0 | 0 |
| `qwen3.8-flash-next` | invoice-coupon | fix-traceback | ok | 5.6 | 543 | 0 | 0 | 0 |
| `qwen3.8-flash-next` | invoice-coupon | fix-symptom | ok | 10.0 | 543 | 0 | 0 | 0 |
| `qwen3.8-flash-next` | inventory-available | hunt | ok | 8.9 | 25 | 0 | 0 | 0 |
| `qwen3.8-flash-next-max` | invoice-coupon | fix-traceback | ok | 6.6 | 532 | 0 | 0 | 0 |
| `qwen3.8-flash-next-max` | invoice-coupon | fix-symptom | ok | 24.1 | 530 | 0 | 0 | 0 |
| `qwen3.8-flash-next-max` | inventory-available | hunt | ok | 62.5 | 25 | 0 | 0 | 0 |

Per model, over its three calls (means are arithmetic on the rows above):

| model | seconds per call | spread | answer length (chars) |
|---|---|---|---|
| `qwen3.8-27b-nothink` | 1.7 | 0.6 – 2.3 | 19 – 543 |
| `minimax-m3.1-flash` | 4.5 | 3.9 – 5.1 | 797 – 1323 |
| `qwen3.8-flash-next` | 8.2 | 5.6 – 10.0 | 25 – 543 |
| `qwen3.8-27b-max` | 11.7 | 10.4 – 14.0 | 19 – 532 |
| `qwen3.8-27b` | 14.0 | 6.5 – 18.9 | 25 – 543 |
| `ornith-1.5-9b` | 20.0 | 5.2 – 31.8 | 19 – 238 |
| `qwen3.8-flash-next-max` | 31.1 | 6.6 – 62.5 | 25 – 532 |

Over the whole probe: 273.5 s of wall-clock across 21 calls — a mean of **13.0 s per call**, or
12.1 s over the 20 successful calls alone. Answer lengths run from **19 to 1323 characters**.

### 2. Findings

**The latency spread is an order of magnitude, and it is a property of the id, not of the case.**
The three cases cost the same model very different amounts: `qwen3.8-flash-next-max` spends 6.6 s
on `invoice-coupon / fix-traceback` and 62.5 s on `inventory-available / hunt` — a factor of 9.5 on
the same probe run. The cheapest id (`qwen3.8-27b-nothink`, mean 1.7 s) is 18× faster than the
dearest (`qwen3.8-flash-next-max`, mean 31.1 s). Any wall-clock budget for stage B therefore has
to be a per-model budget, not a single number.

**The zeros are a property of the client, not evidence of free calls.** Every one of the 20
successful calls reports `prompt_tokens` / `completion_tokens` / `total_tokens` = 0. The cause is
in the client, and it was read in this repository:

- the source project's one-call helper `ask` sends `"stream_options": {"include_usage": True}` and reads the
  usage chunk into a local `usage` variable inside its stream loop, but its return type is `str` —
  the answer text. On success the usage block is dropped; it reaches the caller only on the failure
  paths, where it is interpolated into the `GatewayError` message (`finish_reason: {…}, usage:
  {usage}`). So a successful call through this helper **cannot** report its token cost.
- the source project's `GatewayClient` sends the same `stream_options`, keeps the usage
  chunk (`_stream` → `_usage_of`), and returns it inside `Answer(text, usage, latency_s, variant)`;
  the source project's runner writes `answer.usage.prompt_tokens` and
  `answer.usage.completion_tokens` into the ledger row. That client **can** report the cost.

**Consequence: the token cost of a successful stage-A call is still unmeasured.** The zeros are a
property of the helper the probe used, not proof that the calls cost nothing. The only non-zero
figures in the probe are on the one call that failed — and they are non-zero precisely because the
failure path is the one that reports usage.

**The single deferral is the id with no declared output ceiling.** The deferred call is
`ornith-1.5-9b` on `invoice-coupon / fix-symptom`: 31.8 s, no answer, and the only token counts in
the whole probe — 503 prompt + 2048 completion = 2551 total. The cut at 2048 output tokens matches
an id the endpoint reports **no** `max_output_tokens` for: in
[c197-qwen-model-surface](c197-qwen-model-surface.md) §(d), the `GET /v1/models` listing of
gives `ornith-1.5-9b` "(none reported)" for both `max_input_tokens` and `max_output_tokens`, while
the other six ids report a ceiling (8192 – 65536). the source project's one-call helper `ask` sends **no**
`max_tokens` of its own, so on that id the endpoint's own default decides where the answer stops —
and a reasoning model that does not fit in 2048 output tokens is deferred rather than answered.

### 3. What the stage-B set costs — an extrapolation, labelled as one

**Assumptions, stated in full.** Sequential execution, no parallelism; the per-call latency is the
**measured** stage-A mean of **13.0 s** over the 21 calls (12.1 s over the 20 successful ones); the
prompt set is the stage-B shape (130 prompts per role-model pair, 10 models).

| set | calls | at 13.0 s per call, sequential |
|---|---|---|
| one role-model pair | 130 | 1690 s ≈ **28 min** |
| all 10 models | 1300 | 16 900 s ≈ **4.7 h** |

**The figure is a lower bound for stage B.** The probe's prompts are the stage-A ones; the stage-B
prompts carry the full item context and are therefore larger, and a larger prompt costs more. The
envelope above is what this probe measured, not what stage B will cost — the stage-B figure has to
be measured on stage-B-shaped prompts (see §5).

**Under a stated parallel width.** Dividing the sequential figure by a constant number of in-flight
calls (arithmetic only — no concurrency headroom, rate limit or queueing behaviour was measured):

| in-flight calls | 1300-call set |
|---|---|
| 1 (sequential) | ≈4.7 h |
| 4 | ≈1.2 h |
| 8 | ≈0.6 h |

### 4. What this record establishes, and what it does not

**It establishes**

- the per-call wall-clock cost of akmon's own probe item shape on 7 served ids, measured on one
  host on one day (§1);
- that the per-id latency spread (1.7 s to 31.1 s mean) makes any single wall-clock budget
  meaningless (§2);
- that the token cost of a successful call through the source project's one-call helper `ask` is **not
  measurable**, because that helper discards the usage chunk it asks the endpoint for (§2, verified in
  the code);
- that `ornith-1.5-9b` is the one served id with no declared output ceiling, and that a call on it
  is cut at 2048 output tokens and deferred (§2, with the endpoint's listing from
  [c197-qwen-model-surface](c197-qwen-model-surface.md));
- the order of magnitude of the stage-B run at the measured stage-A mean: ≈28 min per role-model
  pair, ≈4.7 h for the 10-model set, sequential — a lower bound, since the stage-B prompts are
  larger (§3, extrapolation).

**It does not establish**

- **a price.** No token cost of a successful call is measured — only the helper's discard of it
  (§2). The probe yields a time envelope, not a cost envelope in money.
- **a quality ranking.** The probe records latency and answer length only; no answer was scored,
  and no model is shown to be better than another.
- **a stable latency.** 21 calls, 3 per model, one host, one day. The spread inside a single
  model (5.6 s to 62.5 s on `qwen3.8-flash-next-max`) is wider than the difference between several
  models' means, so the per-model means above are not a ranking either.
- **anything about stage-B prompts.** Their size, and therefore their latency, is not measured.
- **the endpoint's behaviour under concurrency.** No parallel call was made, so §3's parallel figures
  are arithmetic.

### 5. Open questions

- **Should the per-call latency for stage B be measured on stage-B-shaped prompts** (full item
  context) rather than carried from a stage-A probe whose prompts were smaller?
- **What is the token cost of a successful call?** The measured way is a client that keeps the
  usage chunk — the source project's `GatewayClient` already does; the stage-A probe's
  client does not. Until a run uses the former, no cost-per-item figure exists.
- **Can the 2048-token cut on `ornith-1.5-9b` be raised** — by the client sending `max_tokens`, or
  only by the endpoint declaring a ceiling for that id? The item format's own output size is not
  measured either.
- **Does the endpoint accept concurrent calls, and at what width?** Nothing here measured a
  concurrency ceiling, so the parallel figures in §3 are unverified arithmetic.
- **The probe file records one deferred call** (`ornith-1.5-9b`, 31.8 s). If a second deferral on
  that id was observed, it is not in the recorded file, and the envelope should not count it.

## Detail: the graded run

### Environment

| | |
|---|---|
| Host | Linux 6.18.33.2-microsoft-standard-WSL2 (WSL2) |
| Endpoint | an OpenAI-compatible endpoint |
| Item set | `a93-seed-1`, `cases_sha 4dd0c1b96c01`, `envelope_sha 98ae4bc6ae3a` |
| Scaffold | `qwen-code` — the harness is part of the score's key (c197-probe-relevance §4) |
| Sandbox | `python:3.13-slim`, model-written code never runs on the host |

### 1. The run

| | |
|---|---|
| Calls | 21 (3 (case, family) pairs × 7 models) |
| Sandboxed hidden-test runs | 14 (the two fix families × 7 models) |
| Wall-clock | **5 min 44 s** sequential (the runner's own plan estimated ~13 min) |
| Scored / deferred | 18 scored, **3 deferred** — every deferral a cut-off answer |
| Tokens (recorded) | 8,792 prompt + 14,315 completion — the deferrals' output tokens are missing (§3.4) |
| Model time | 329.2 s of the 344 s — the run is almost entirely model time |

Per model: three calls each.

| model | prompt tok | completion tok | model time | fix-traceback | fix-symptom | hunt |
|---|---|---|---|---|---|---|
| `qwen3.8-27b-nothink` | 1,338 | 313 | 3.7 s | pass | pass | fail |
| `minimax-m3.1-flash` | 1,779 | 1,018 | 15.2 s | pass | pass | fail |
| `qwen3.8-flash-next` | 1,332 | 1,818 | 16.8 s | pass | pass | fail (right file, wrong function) |
| `ornith-1.5-9b` | 829 | 965 | 72.1 s | pass | **deferred** | fail |
| `qwen3.8-27b` | 1,332 | 3,616 | 57.5 s | pass | pass | fail |
| `qwen3.8-flash-next-max` | 1,091 | 2,975 | 75.4 s | pass | pass | **deferred** |
| `qwen3.8-27b-max` | 1,091 | 3,610 | 88.4 s | pass | pass | **deferred** |

The three deferred calls are all the same failure: *"the answer was cut off by the 4096-token cap"*.

### 2. What the answers said

**Every id repaired both fix items.** All fourteen fix attempts that produced an answer passed the
hidden test with no other file changed. On two items of this shape the suite is saturated: the
repair is easy, and nothing separates the ids.

**The hunt item is the one that discriminates, and the decoy works.** The defect is in
`inventory.py:available`; `pricing.py` and `shipping.py` are the decoys. Three ids
(`ornith-1.5-9b`, `qwen3.8-27b`, `qwen3.8-27b-nothink`) answered `pricing.py:discount` — the
decoy file and the decoy function. `qwen3.8-flash-next` answered `inventory.py:reserved_for` —
**the right file, the wrong function**, which the scorer keeps apart from a wrong file as a
localization gap. Only `minimax-m3.1-flash` answered in prose instead of the required one-line
form, and `qwen3.8-27b-max` and `qwen3.8-flash-next-max` never finished their answer.

**So the seed set's order is: everyone ties on repair, the hunt item separates by whether the
model is lured by the decoy.** That is the mechanism the suite is supposed to have, seen once.

### 3. Findings

#### 3.1 The seed set cannot separate the models — and that is by construction

Every one of the 21 cells fails the `items_scored` gate, because the gate needs 30 scored items
and a seed cell holds 1. A stage-A run therefore measures **cost and plumbing**, never the signal.
What it does show is that the two-item suite has no headroom: the fix items are saturated and the
hunt item is one bit.

#### 3.2 The reasoning ids are cut off by the cap, and the cap does its job

`qwen3.8-27b` spent **2,673 completion tokens** on a one-line answer and `qwen3.8-flash-next-max`
and `qwen3.8-27b-max` exceeded the 4096-token cap and were deferred. The deferral rule held: a
cut-off answer is a **deferral**, counted on its own line, never a miss. But the answer the item
asked for is one line of text, so a verbosity that costs 2,700 tokens on it is the model's habit,
not the item's difficulty — and it is a **scaffold** effect (c197-comparison-practice §6 measures a 29.8 pp scaffold
gap), not a capability gap. The suite has to constrain the answer length explicitly, or the hunt
family will measure verbosity.

#### 3.3 A format failure is recorded as a capability failure

`minimax-m3.1-flash` answered the hunt item in prose; the scorer calls that *"the answer is not
one line of the form file.py:function_name"* and the cell's `location_hit` and
`file_localization` both read 0. The item asks for the exact form, so this is a real
format-compliance failure — but it is reported as *"the model cannot name the file and the
function that hold the defect"*, which is a different claim. c197-probe-relevance §5 requires the location scorer
to be validated on human-labelled items before a localization gap is reported as a capability gap;
this run is the first evidence that the **scorer** needs a third verdict (malformed) beside the
two location verdicts, so that a format failure is not silently merged into a wrong location.

#### 3.4 The record could not be re-derived, and the deferrals' cost was lost

Two defects in what the run writes — **both fixed on, in the same stretch, with tests
that fail without the change** (the source project's test module):

- **The answer text was not persisted.** A detail row carried the verdict, the reason, the token
  counts and the latency — but not the answer. The source project's `scoring.py` opens with the
  promise that *"the grading is mechanical on purpose … so the same answer always earns the same
  verdict"*, which is only auditable if the answer is kept. As it stood, a shipped score could
  not be re-derived or checked by anyone but the runner. **Fixed**: `runner.Attempt` carries the
  answer and writes it into the detail row under `answer`.
- **A deferral's tokens were zeroed.** `runner._attempt` wrote `prompt_tokens=0,
  completion_tokens=0` for a deferral, so the three cut-off calls' 4096 output tokens each were
  missing from the cost record: the run spent at least **12,288 more completion tokens** than the
  ledger reports. **Fixed**: `Deferral` carries the usage the stream had reported, and
  the deferral path writes it.

The run's own numbers above are therefore the ones the old code produced; a re-run under the fixed
code would report the deferrals' tokens.

#### 3.5 The plan's cost estimate is about twice the measured cost

The runner's plan estimated ~13 min for the run; it took **5 min 44 s**. The estimate assumes
`ESTIMATED_CALL_SECONDS = 30` per call; the measured mean is **15.7 s** per call (10.4 s over the
scored ones). The estimate is a ceiling, not a mean, and it should be stated as one.

#### 3.6 What stage B costs, measured rather than extrapolated from stage A's probe

At the measured means — 10.4 s per scored call, 15.7 s per call including deferrals — the stage-B
shape (130 prompts per role-model pair, 10 models, 1,300 calls) costs, sequential:

| set | calls | at 10.4 s | at 15.7 s |
|---|---|---|---|
| one role-model pair | 130 | ≈23 min | ≈34 min |
| all 10 models | 1,300 | ≈3.8 h | ≈5.7 h |

The tokens of the same set, scaled from this run's per-call averages (419 input, 682 output):
**≈544k input and ≈886k output tokens**, before the deferrals' missing output. Both figures are
**lower bounds**: the stage-B prompts carry the full item context and are larger than these, and
the deferral rate rises with the answer length the reasoning ids spend.

### 4. What this record establishes, and what it does not

**It establishes**

- the end-to-end cost of one probe pass over the seven served ids: **5 min 44 s**, 21 calls,
  14 sandboxed test runs, 8,792 + 14,315 recorded tokens, 329.2 s of model time (§1);
- that the seed suite does **not** separate the ids: all seven repair both fix items, and the
  hunt item separates only between "lured by the decoy", "right file, wrong function" and "cut
  off" (§2);
- that the decoy mechanism works — three of the four in-form answers named the decoy file *and* the
  decoy function (§2);
- that a cut-off answer is correctly a deferral and not a miss, and that verbosity alone can
  cause it (§3.2);
- that a format failure and a wrong location are currently reported as the same thing (§3.3);
- that the shipped record cannot be re-derived and under-counts the deferrals' tokens (§3.4);
- the measured stage-B cost: ≈3.8–5.7 h and ≈1.4M tokens for 1,300 calls, sequential (§3.6).

**It does not establish**

- **a ranking.** One item per family cannot rank anything, and every cell fails the items gate.
- **a quality claim about any id.** The fix items are saturated; the hunt item is one bit.
- **the suite's separation.** That needs the generator's 40 programs and stage B's 130 prompts.
- **the price.** The token counts are measured; what a token costs is not.
- **anything about the Claude reference.** It was not part of this run — Anthropic's terms forbid
  a subscription login in an automated job, so that run stays manual and by the owner.

### 5. What has to be fixed before the score set ships

1. ~~**Keep the answer text** in the detail row, so a score can be re-derived and audited.~~
   **Done** — `runner.Attempt` carries the answer; the detail row writes it.
2. ~~**Record a deferral's usage** instead of zeroing it — the cost record is otherwise wrong.~~
   **Done** — `Deferral` carries the usage the stream reported.
3. **Separate the malformed verdict** from the wrong-location verdict in the hunt scorer — **open,
   the owner's call**: it changes what a score says, not only how it is stored.
4. **Constrain the answer length in the prompt** (and lower the cap for the hunt family), so the
   hunt family measures localization and not verbosity.
5. **State the plan's estimate as a ceiling**, or re-derive it from the measured mean.
6. **Keep the seed set as a smoke test**, not as evidence: the gate, the plumbing and the ledger
   are exercised by it, and its scores are not published.

### 6. Open questions

- **Does the stage-A signal separate at all?** With one item per family it cannot; the first
  honest test is stage B on the generated set.
- **Is the hunt answer's one-line form the right ask?** The form is what makes the score
  mechanical, and five of seven ids follow it — but the suite has to decide whether a prose
  answer that names the right location is a miss.
- **What output cap does the hunt family need?** 4096 tokens is generous for one line and still
  cut two reasoning ids off.
- **Does the concurrency width hold?** Everything here was sequential; no parallel call was made,
  so the parallel figures in the cost envelope §3 remain arithmetic.

