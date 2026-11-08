# C197 comparison practice: how the field compares models on coding work

> Point-in-time survey carried for task C197; the method lives in the design.

**Answers:** the owner's question — «Have you looked at how the industry compares models for development work? Some short synthetic tests, for example for finding bugs and the number of fixed ones?»
and what that means for akmon's role probes.

**Status of the sources:** this record is the synthesis of a research pass; every claim below carries
its URL, and the items the pass could **not** verify are listed in §7. The numbers here are the
research's, not akmon's own measurements — the pilot that would turn them into akmon facts is
§6.

---

## 1. What the industry actually uses

> **Read with [c197-probe-relevance](c197-probe-relevance.md) §3.** SWE-bench Verified is
> now a **historical anchor**: it is contaminated (models are "3 times better" on it than on a
> fresh benchmark at finding edited files), it has **converged** (the top two entries resolve 396
> of 500 instances; McNemar separates none of the 29 adjacent pairs among the top thirty), and
> filtering contaminated samples lowers reported rates by >20 % relative. The newer set that
> replaces it is SWE-rebench V2, SWE-Bench Pro V2 (Hard split), Terminal-Bench 4.0, Harbor-Index,
> SWE-smith/SYNGEN, LiveCodeBench, τ-bench and CodeClash. What follows is the **shape** of the
> field's practice, which holds; the specific benchmark's currency is c197-probe-relevance's subject.

The field's unit of measurement is a **task with hidden tests**, not a score:

- **SWE-bench** (2,294 instances, 12 repos; Lite = 300; Verified = 500 human-filtered) — graded by
  applying the model's patch and running the repo's tests: **FAIL_TO_PASS** must flip to pass and
  **PASS_TO_PASS** must stay passing. The median instance has 1 f2p and 51 p2p tests
  (https://arxiv.org/html/2310.06770v3, https://www.swebench.com/verified.html). The paper states
  plainly that running it "can be time-consuming and, depending on the model, require a costly
  amount of compute or API credits" — it is not a daily probe.
- **SWE-smith** (https://arxiv.org/abs/2504.21798) — 50k auto-generated instances over 128 repos,
  where an injected bug *breaks existing repo tests*: the cheap, synthetic, endlessly renewable form
  of the same idea.
- **R2E-Gym / SYNGEN** (https://arxiv.org/abs/2504.07164) — >8.7K executable tasks generated from
  commits by test generation + back-translation; less dependence on human-written issues.
- **BugsInPy** (https://arxiv.org/abs/2401.15481) — 493 real bugs in 17 real Python programs, f2p/p2p
  grading; pip-installable, so it runs without a sandbox.
- **aider polyglot** (https://aider.chat/docs/leaderboards/) — 225 Exercism exercises in 6 languages,
  graded by **test pass rate** plus a separate **% well-formed edit format** metric, with published
  per-model token and dollar cost. The cheapest thing here that measures what a **worker** actually
  does: execute a mechanical edit and report it in the harness's format.
- **RepoQA / RepoBench-R** (https://arxiv.org/abs/2406.06025, https://arxiv.org/html/2306.03091v2) —
  retrieval and comprehension *inside a repository*: the closest published proxy to an orchestrator's
  first job.
- **LiveCodeBench** (https://arxiv.org/abs/2403.07974) — 400 rolling problems with a date cutoff, so
  contamination is bounded by construction.
- **CodeXGLUE defect detection** (https://github.com/microsoft/CodeXGLUE) — 27,318 examples of
  insecure-vs-secure classification; a cheap floor for "can it spot a bad change".
- **terminal-bench** (https://www.tbench.ai/) and **τ-bench** (https://arxiv.org/abs/2406.12045) —
  agentic, but the first needs a GPU sandbox and the second grades a final database state.

**Nothing in that list is a knowledge benchmark.** Every one is a *task* whose success is decided by
a program.

## 2. The owner's intuition is the field's method — with one correction

«Bug hunting and the number of fixed bugs is the model level» is exactly how the field measures
coding ability. The correction is in **how the count is reported**, and the literature is
unusually clear on this:

- **A raw count is not a metric.** Paired statistical testing on SWE-bench Verified shows that
  **none** of the 29 adjacent pairs among the top 30 leaderboard entries separate under McNemar,
  and that **164 of 500 instances** are needed to tell the top 10 apart
  (https://arxiv.org/abs/2609.17394). Single-digit count differences between two models carry no
  information.
- **Report a rate with an interval, and compare paired.** Fixed/attempted with a Wilson (or exact
  Clopper–Pearson) interval; pairwise **exact McNemar** over the *same* items for every model;
  report the number of discordant pairs, and say "no significant difference" when there are fewer
  than ~10.
- **Repeat each item** (K trials) to separate the model from the sampling noise — the same
  conclusion as [c197-ranking-method](c197-ranking-method.md) §2.4 from the other direction.
- **Separate hunting from fixing.** Report (a) localization accuracy — did it point at the right
  place, (b) fix given localization, (c) end-to-end fix. A model can be good at one and bad at
  another, and the role ladder needs to know which.
- **Never accept a patch that breaks passing tests.** The SWE-bench taxonomy (Resolved / Breaking
  Resolved / Partially Resolved / No-Op / Regression) exists because "the tests pass" and "the
  patch is right" come apart; no-op patches are the common failure.

## 3. What the "fixed" signal actually means (the sobering part)

- On Defects4J, **47** bugs received test-suite-adequate patches, and manual review found only **9**
  truly correct — a ~19 % true-positive rate for the naive "tests pass" signal
  (https://arxiv.org/abs/1811.02429).
- **>95 %** of Defects4J versions contain **2–24 faults** (https://arxiv.org/abs/2108.04455): one
  fixed bug says nothing about the rest of the file.
- Defects4J patches are **tiny** — median 4 lines, 30 % add-only, 92 % touch one file
  (https://arxiv.org/abs/1801.06393) — so a one-line difference can flip a similarity score while
  changing the semantics.
- **Patch similarity (CodeBLEU, diff-match) correlates with programmer-assigned quality better than
  BLEU or exact accuracy** (https://arxiv.org/abs/2009.10297) but is a *differential* signal, not a
  correctness criterion: an alternative correct fix or a cosmetic refactor scores low.
- **LLM-as-judge on code is unreliable**: order-of-presentation changes substantially alter
  accuracy, and pairwise comparison beats scalar point-wise judging
  (https://arxiv.org/abs/2507.10535). → confirms [c197-ranking-method](c197-ranking-method.md) §2.1:
  the judge may audit, not score.

## 4. The confound that matters most here

- **Scaffold variance exceeds the model gaps.** Within-model scaffold ranges reach **29.8
  percentage points**, while the spread across the top thirty leaderboard entries is **8.8 points**
  (https://arxiv.org/abs/2609.17394). A model ranking measured under *our* scaffold describes
  **model × scaffold**, not the model.
- **Public benchmarks do not agree with each other.** Across 2,487 tasks from 5 benchmarks and
  14,922 runs of 6 agent configurations, *every pair* of benchmarks differs on at least two axes of
  the Spread-Novelty-Centrality profile — including benchmarks that share a task label
  (https://arxiv.org/abs/2609.01271). → a public coding benchmark is not a proxy for our harness.
- **Contamination is measurable** on agentic benchmarks: up to **76 %** accuracy predicting the
  buggy file path from the issue text alone, and up to **35 %** 5-gram reproduction of the original
  function (https://arxiv.org/abs/2506.12286); an audit found **~60 %** of unsolved SWE-bench
  Verified instances contain flawed tests (https://arxiv.org/abs/2608.09802). → self-authored items
  stay the right choice.

## 5. Routing: what the literature supports

- **RouteLLM** (https://arxiv.org/html/2406.18665v4): routers trained on arena preferences save >2×
  cost at 95 % of GPT-4 quality, but the same routers are **at or below random** on out-of-distribution
  benchmarks (GSM8K, MMLU) — the routing signal must be **domain-matched**, and a router trained on
  preferences does not transfer to "is this patch correct".
- **FrugalGPT** (https://arxiv.org/abs/2305.05176), **Hybrid LLM** (https://arxiv.org/abs/2404.14618):
  cascades and difficulty prediction pay off when the cheap model is good enough on the routed
  slice; the operational signal is the **marginal gain over the small model**, not absolute quality
  (https://arxiv.org/abs/2604.22520).
- **AWS Bedrock Intelligent Prompt Routing** (https://docs.aws.amazon.com/bedrock/latest/userguide/prompt-routing.html)
  uses a response-quality-difference threshold against one fallback model, and states its own limits
  (two models per router, no application-specific feedback).

**Inference for our case.** Our seven ids are **one vendor family** (four `qwen3.8-*` variants) plus
two others; the variants differ mostly in **reasoning effort** (`-max`, `-nothink`), not in
capability. The literature's diversity requirement is therefore not met: the highest-value routing
here is **effort-tier routing** (flash / flash-max / 27b / 27b-max), not family routing. A profile
that says "worker → flash-nothink, reasoner → 27b-max" is exactly that, and it is what the owner's
Claude-anchored calibration will decide.

## 6. What akmon would build, and the pilot that tests it

> **Revised after the [Claude audit](c197-role-probe-design-audit.md).**
> The suite below replaces [c197-ranking-method](c197-ranking-method.md) §3 (superseded) (the generic family
> list), which the audit found measures general model skills rather than the delegates' work, and
> which spent 32 % of its calls on arithmetic. The item shape, the grading, the statistics and the
> pilot now follow the audit's findings.
>
> **Revised again by [c197-probe-relevance](c197-probe-relevance.md)** — the *rules*
> below changed: the item-selection rule (pass-rate band), the oracle rule (gold-sanity gate), the
> repeat policy, the time-limit policy and the citations. The **shape** did not change.

A role-linked suite built on §1's shapes, **self-authored** (contamination-free) and small. The
items are **bugs injected by code mutation into small programs**, with **clean decoy files** beside
the faulty one, so that a model cannot win by guessing which file matters:

| Component | Role it informs | Shape | Grading | Items |
|---|---|---|---|---|
| **Bug hunt (localize)** | reasoner, auditor | a small program with one planted defect plus clean decoys; ask for the location | location hit (top-1 / top-3) **and** the decoys untouched | 30 + 8 clean decoys |
| **Bug fix — traceback given** | reasoner, mid | the same programs with the failing test's traceback shown; ask for the patch | hidden f2p passes **and** p2p intact | 30 |
| **Bug fix — symptom only** | reasoner, mid | the **same** bugs, but only the observed symptom; ask for the patch | hidden f2p passes **and** p2p intact | 30 |
| **Audit a candidate patch** | auditor | a diff with defects; accept or reject | planted-line recall minus false positives | (with the hunt family) |
| **Formatting / arithmetic control** | — | generic items, kept as **integrity checks only** — they are not rank-carrying for a current-generation model | exact match | 20 + 20 |

The **traceback / symptom pair** is the load-bearing shape the audit names: the same bug fixed with
the stack trace given versus from the symptom alone separates *localization ability* from *repair
ability*, and it is what tells a role ladder which of the two a model actually has.

**Everything is programmatically graded; there is no judge in the score.** Item **generation and
selection are programmatic too** — an item chosen by Claude would bias the comparison, because the
served models may be tuned clones of Claude. That risk does not touch a test-graded score; it
touches the suite itself.

### 6.1 The rules the suite must obey (c197-probe-relevance)

| Rule | What it forbids | Why |
|---|---|---|
| **Select items by pass-rate band.** Compute each item's pass rate over the candidate pool (7 served models + haiku/sonnet/opus) and **drop the items every model passes and the items every model fails**. The 40 generic controls leave the ranking and stay as integrity checks; the 8 no-bug items stay in the ranking — false positives are a distinct failure mode nothing else covers. | dropping items by family or by intuition | the mid-range filter cuts tasks 44–70 % at the same rank fidelity ([c197-probe-relevance](c197-probe-relevance.md) §1) |
| **Gold-sanity-gate every test.** A probe test must **fail on the buggy program and pass on the fixed one**, and pass on the unmutated original. A test that does not is discarded, and **no model authors the oracle**. | an LLM-written or hand-written "hidden test" that a wrong patch can satisfy | 28.5 % of SWE-bench Verified tasks accept a Docker-verified wrong patch; 61.9 % of LLM-generated decisive tests fail on the gold patch ([c197-probe-relevance](c197-probe-relevance.md) §5) |
| **Repeat, don't multiply.** 2–3 repeats per item with a **varying** seed, rather than more items; a fixed seed makes a repeat a near-duplicate. | one run per item | single-run pass@1 varies 2.2–6.0 pp, and ≈9 % of per-instance outcomes flip between byte-identical runs ([c197-probe-relevance](c197-probe-relevance.md) §2) |
| **Fix and publish the time limit, and report the time.** The per-item limit is generous and identical for every model; the wall-clock is recorded beside the score. | a timeout that reads as a skill difference | extending the time limit closes a 20 pp harness gap on one model and shrinks a 30 pp gap on another to 5 pp ([c197-probe-relevance](c197-probe-relevance.md) §4) |
| **Bind the scaffold, not only the model.** The score's key carries the harness and the limit beside the model id, the case-set hash and the envelope hash. | a score that silently means "this model under an unnamed scaffold" | fixed model-scaffold systems rank reliably; underlying-model reliability is 0.148–0.841 ([c197-probe-relevance](c197-probe-relevance.md) §4) |
| **Treat the effort tier as an escalation policy, not as a model.** `-max` and `-nothink` are one family at two effort levels; the profile uses the higher tier as the escalation step. | ranking `-max` as "a stronger model" | the measured effort gap (+2.4 pp) is **inside** the single-run noise band, and escalating on verified failure matches fixed top effort at up to 42× lower cost ([c197-probe-relevance](c197-probe-relevance.md) §4) |
| **Keep the items off any corpus the models saw.** Synthetic or private repositories; the composition is randomised per run and the no-bug fraction is not inferable from the prompt. | decoy files in a repository a model has memorised; a visible clean-item ratio | agents lean on memorised repo cues, and evaluation meta-knowledge inflates scores independently of memorisation ([c197-probe-relevance](c197-probe-relevance.md) §5) |
| **No spoiler in the symptom.** The symptom string must not contain the edited line. | a symptom that hands over the fix | over-specification lets a model bypass the step the item measures ([c197-probe-relevance](c197-probe-relevance.md) §5) |
| **Validate the location-hit scorer** on human-labelled items before a localization gap is reported as a capability gap. | a top-1/top-3 gap taken at face value | a recent measurement-first audit could not validate such a gap: its intervals included zero and its scorer failed its validation gate ([c197-probe-relevance](c197-probe-relevance.md) §5) |

**Statistics.** A role score over a few hundred items resolves roughly **12–20 points** — enough
for **three bands**, not for a fine order. So the binding is banded: below the haiku reference,
haiku–sonnet, sonnet and up.

**The pilot** (one session, cheap enough to be decisive), **as revised by the audit** and then by
the owner (staged, because 1440 calls is more than one subscription's limits):

- **Stage A — one prompt per role family per model**, compared with qwen. It answers what a full
  run costs in **wall-clock and tokens**, and whether the signal separates at that size.
- **Stage B — the full set** (40 small programs, 130 prompts: 30 find-the-bug items of which 8 are
  clean decoys, 30 fix-with-traceback, 30 fix-from-symptom on the same bugs, 20 formatting + 20
  arithmetic controls), on all 10 models (7 served models + haiku / sonnet / opus), with the repeats and
  the gold-sanity gate of §6.1, only if stage A says the suite separates.
- ≈ **1,300 calls** at one repeat; the repeats multiply that, which is why stage A measures the
  cost first.

The pilot answers the three questions the design cannot yet answer: (1) does the suite **separate**
the models at all — specifically, do the bug families separate opus from haiku while the generic
control families do not; if they do not, the probe design is **falsified**; (2) are the served models
models in the **same order across roles** — if yes, one ordered ladder suffices; (3) how wide the
intervals are, i.e. whether the item count must grow before any re-binding is defensible. At this
size the pilot only detects gaps of **20–25 points or more** — a limit it states, so a null result
is read as "underpowered", not as "no difference".

**The runner needs a safety envelope.** The suite executes **model-written code**, so the refresh
runner carries output-token caps, explicit timeouts, a token budget per model, and a sandbox for
running the produced patches.

## 7. Not verified, or out of scope

- **BashBench** — the research could not find such an arXiv paper; treat the name as unverified.
- **SWE-bench Verified's annotator count and removal fraction** — the commonly cited figures
  (93 annotators, ~61 %) come from a source the pass could not fetch; the official page says only
  "human annotators".
- **terminal-bench cost and per-version task counts** — not published on its site.
- **Defects4J's counts** (835 bugs / 9 projects) come from the project's pages, not a fetched paper.
- **Cost per item on our endpoint** — unmeasured; the endpoint's GPU time is the currency.
- **A formal power calculation** for the suite was not done: the research's own estimate is that
  ~20 discordant pairs resolve roughly ±15 pp, which is wider than most gaps we expect — so the
  pilot must measure the interval before any threshold is set.
- **No published work maps benchmark axes onto akmon's roles** (worker / mid / reasoner / auditor /
  orchestrator). The mapping in §6 is an inference from task-shape and scaffold-dependence
  literature, and it is the thing the Claude-anchored calibration is meant to replace with a
  measurement.
