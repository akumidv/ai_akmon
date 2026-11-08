# C197 probe relevance and paper recency

> Point-in-time survey carried for task C197; the method lives in the design.

**Answers:** the owner's three questions — how much a full run costs in time and
resources; how the proposed probes correlate with the score and which of them to drop; and the
observation that the papers behind the first suite are old arguments about current
models.

**Method:** a delegated research pass with web access over the primary literature (arXiv records
fetched through the arXiv API, the benchmark sites' own leaderboard data), followed by a
verification of the six load-bearing records in this repository's own session — the arXiv API
returned the quoted abstracts verbatim for
[2603.23749](https://arxiv.org/abs/2603.23749),
[2606.16062](https://arxiv.org/abs/2606.16062),
[2602.07150](https://arxiv.org/abs/2602.07150),
[2610.24206](https://arxiv.org/abs/2610.24206),
[2611.08417](https://arxiv.org/abs/2611.08417) and
[2609.24928](https://arxiv.org/abs/2609.24928). Every claim below carries its source; the ones the
pass could not verify are in §6.

**What it changes:** [c197-comparison-practice](c197-comparison-practice.md) §6 is revised by this
record — the suite's **item selection rule**, its **oracle rule**, its **repeat policy**, its
**time-limit policy** and its **citations** all change. The suite's shape (bug hunting, fixing
with a traceback, fixing from the symptom) is **not** changed by this pass; that came from the
[Claude audit](c197-role-probe-design-audit.md).

---

## 1. Item selection: by pass-rate band, not by family

The owner's question — how the probes correlate with the score, and which to drop — has a
published answer, and it is not "by family".

> we propose a simple optimization-free protocol: evaluate new agents only on tasks with
> intermediate historical pass rates (30-70%). This mid-range difficulty filter, motivated by Item
> Response Theory, reduces the number of evaluation tasks by **44-70%** while maintaining high rank
> fidelity under scaffold and temporal shifts. It provides more reliable rankings than random
> sampling, which exhibits high variance across seeds.
>
> — *Efficient Benchmarking of AI Agents*, [arXiv:2603.23749](https://arxiv.org/abs/2603.23749)
> (eight benchmarks, 33 agent scaffolds, 70+ model configurations)

**So the item's family is not the selection criterion; its pass rate is.** An item every candidate
passes and an item every candidate fails carry no rank information — and the early suite's
arithmetic and formatting families are exactly the former for a current-generation model.

Two supporting results make the pruning legitimate rather than a shortcut:

- **A small discriminating subset is established practice at agentic scale**: *Harbor Adapters and
  Harbor-Index*, [arXiv:2609.04298](https://arxiv.org/abs/2609.04298) — "Harbor-Index,
  a curated set of **82** difficult, diverse, and high-quality tasks spanning **29** benchmarks …
  no evaluated model-harness configuration exceeds 30% pass rate, and the strongest reaches 28.0%".
  SWE-bench **Lite** is the same move at 300 of 2,294 tasks, "selected to preserve the distribution
  and difficulty spectrum" (https://www.swebench.com/lite.html).
- **The pruning method matters**: *Trajectory-Aware Benchmark Subset Selection*,
  [arXiv:2609.24928](https://arxiv.org/abs/2609.24928) — "a 10%
  trajectory-aware subset keeps the median estimation error below 5% while cutting token cost by
  roughly **90%**", while "random sampling or stratified random sampling based on past pass/fail
  outcomes … risk producing high variance and unrepresentative subsets". A subset must also
  **preserve the pass/fail mix** — which is why the no-bug items stay.

**What this changes in the suite.** The keep/drop rule becomes: compute each item's pass rate
across the candidate pool (the 7 served models + haiku/sonnet/opus) and **drop the items where
every model passes or every model fails**; keep the rest. The 40 generic control items
(20 formatting + 20 arithmetic) are **not rank-carrying** for a current-generation model — they leave the
ranking and stay as integrity checks. The 8 clean (no-bug) items **stay**: false positives are a
distinct failure mode, and nothing else in the suite covers them.

## 2. What a run costs, and what a single run is worth

- **Cost of the heavyweight alternative**: the SWE-bench Verified leaderboard's own bash-only runs
  show a **median $0.334 per instance** and a **median 38 API calls per instance**
  (range 13.2–89.2); Claude 4.5 Opus (high) $0.754, MiniMax M2.5 (high) $0.073
  (https://www.swebench.com/).
- **Cost of a cheap probe item**: an LLM false-alarm triage in industrial static analysis runs at
  "$0.0011–$0.12 per alarm, 2.1–109.5 seconds" — *Reducing False Positives in Static Bug Detection
  with LLMs*, [arXiv:2601.18844](https://arxiv.org/abs/2601.18844). A single-file
  bug-hunt item is therefore **30–300× cheaper** than a Verified instance.
- **Cheapness does not buy separation**: an item in the wrong pass-rate band has *zero*
  separation power, so the band rule (§1) comes **before** the cost argument, not after it.
- **One run is not enough**:

  > single-run pass@1 estimates vary by **2.2 to 6.0 percentage points** depending on which run is
  > selected, with standard deviations exceeding 1.5 percentage points even at temperature 0 …
  > reported improvements of 2–3 percentage points may reflect evaluation noise.
  >
  > — *On Randomness in Agentic Evals*, [arXiv:2602.07150](https://arxiv.org/abs/2602.07150)
  > (latest version 60,000 trajectories on SWE-bench Verified)

  Corroborated: "temperature-0 API inference flips **~9% of per-instance outcomes** between
  byte-identical runs" ([arXiv:2607.09691](https://arxiv.org/abs/2607.09691)).

  **Derived here (our arithmetic, not a source):** a 30-item binary family at p ≈ 0.5 has
  1σ ≈ 9 pp; three repeats of the same 30 items give 1σ ≈ 5.2 pp. Since an item is cheap,
  **repeats buy more resolution than more items** — which is the opposite of the first suite's
  plan (540 items × K) and the reason that plan was expensive.

## 3. Recency: the early papers are history, and the newer set is available

**SWE-bench Verified no longer ranks models** (three independent reasons):

- **Contamination — it measures memory**: with only the issue text, models are "3 times better on
  SWE-Bench-Verified" than on a fresh benchmark, and "6 times better at finding edited files" —
  *Does SWE-Bench-Verified Test Agent Ability or Model Memory?*,
  [arXiv:2512.10218](https://arxiv.org/abs/2512.10218).
- **Convergence and scaffold variance**: "the leading two entries each resolve 396 of 500
  instances … within-model scaffold ranges reach **29.8 percentage points**, compared with the
  **8.8-point** spread of the top thirty. Exact paired McNemar tests separate none of the 29
  adjacent Verified top-thirty pairs" — *Coding Agents Have Converged*,
  [arXiv:2609.17394](https://arxiv.org/abs/2609.17394).
- **Its own task set is broken**: "applying BenchChecker to SWE-bench Verified and Multi-SWE-bench
  reveals that filtering contaminated samples reduces the reported resolution rates of most LLMs by
  **more than 20% relative**" — *BenchChecker*, [arXiv:2610.19447](https://arxiv.org/abs/2610.19447)
 .

**The newer set that replaces it:**

| Source | What it gives |
|---|---|
| *SWE-rebench V2*, [arXiv:2602.23866](https://arxiv.org/abs/2602.23866) | 32,079 tasks, 20 languages, 3,617 repositories; fresh task supply, so contamination is bounded by construction |
| *SWE-Bench Pro V2*, [arXiv:2610.24206](https://arxiv.org/abs/2610.24206) | "repaired or retired **480 of the 731** tasks"; "a hardened protocol restricts network access to the model endpoint and re-grades every patch in a clean container"; the 51-task **Hard** split spreads systems from 52.9% to 98.0% |
| *SWE-Bench Pro Verified*, [arXiv:2609.08149](https://arxiv.org/abs/2609.08149) | the reward-hacking audit: "leakage of gold solutions or hidden evaluation information"; "some models perform substantially worse than previously evaluated" |
| *Terminal-Bench* (site: **4.0**, https://www.tbench.ai/) and its paper [arXiv:2611.08417](https://arxiv.org/abs/2611.08417) | "issues in roughly 30% of the benchmark"; repairs moved accuracy by **+10 pp** and ranks by up to three; and "extending the time limit closes a **20pp** harness gap on GPT 5.4 and shrinks a **30 pp** gap on GPT 5.4 mini to 5 pp" |
| *Harbor-Index*, [arXiv:2609.04298](https://arxiv.org/abs/2609.04298) | 82 hard tasks across 29 benchmarks; the best configuration reaches 28.0% — a difficulty target for our own items |
| *SWE-smith*, [arXiv:2504.21798](https://arxiv.org/abs/2504.21798) · *SYNGEN / R2E-Gym*, [arXiv:2504.07164](https://arxiv.org/abs/2504.07164) | mutation-generated and synthetic tasks — the shape our own suite uses, and the defence against contamination |
| *LiveCodeBench*, [arXiv:2403.07974](https://arxiv.org/abs/2403.07974) · *τ-bench*, [arXiv:2406.12045](https://arxiv.org/abs/2406.12045) · *CodeClash* (https://codeclash.ai/) | the live, the tool-agent and the arena axes; the last still separates small models widely |

**GSM8K and IFEval stay as controls only** — they are not coding-capability evidence for current models, and they are exactly the items the audit rejected.

## 4. Scaffold, effort and the time limit

> Fixed model-scaffold systems are ranked reliably (0.935-0.994), while underlying-model
> reliability is substantially lower (0.148-0.841) … Even infinitely many similarly constructed
> tasks improve model-ranking reliability of a benchmark by at most 0.097 when uncertainty is
> dominated by limited scaffold coverage.
>
> — *Agent Evaluation Reliability*, [arXiv:2610.00651](https://arxiv.org/abs/2610.00651)

Three consequences for our binding:

1. **The key names the scaffold, not only the model.** A role bound to "a model" is really bound
   to "a model **under a harness**". The score set's key therefore carries the harness and the
   time limit beside the model id and the envelope hash — which is also the owner's measured ledger shape
   (its case-set and envelope hashes; see [c197-stage-a-pilot](../experiments/c197-stage-a-pilot.md)).
2. **The time limit is part of the measurement, and it must be fixed and published.** A wall-clock
   difference reads as a 20–30 pp skill gap (Terminal-Bench, above). A cheap model that is slow
   must not be scored as a weak one: the per-item time limit is generous, fixed, and **time is
   reported as a metric beside the score**.
3. **The reasoning-effort axis is an escalation policy, not a model identity.** "Effort … does not
   consistently preserve tasks that lower effort solves … the highest effort level costing up to
   **42×** as much as the lowest … starting at the lowest effort and escalating only after a
   verified failure, matches or improves on fixed top effort across all models and benchmarks at
   lower cost" — *What Effort Level Should I Choose?*,
   [arXiv:2610.34491](https://arxiv.org/abs/2610.34491). On current coding data the
   effort gap is small — Claude 4.5 Opus (high) 76.8 vs (medium) 74.4, **+2.4 pp** — which is
   **inside** the 2.2–6.0 pp single-run noise band of §2. So `qwen3.8-27b-max` is not "a stronger
   model" in the ranking; it is the **same model at a higher effort**, and the profile treats it as
   an escalation tier. (The switch itself is documented in the *Qwen3 Technical Report*,
   [arXiv:2505.09388](https://arxiv.org/abs/2505.09388) — thinking / non-thinking modes with a
   thinking budget.)

## 5. Gaming: the oracle is the weak point, and it is measurable

This is the finding with the sharpest consequence for our grading.

> On a 49-task sample of SWE-bench Verified, **28.5% of tasks have test suites weak enough that a
> Docker-verified incorrect patch passes them** … within the same human-rated difficulty stratum,
> model Pass@1 is **+14.14 percentage points higher** on flagged-hackable tasks than on robust ones
> (95% CI [+11.80, +16.48]) … the gate flags **65 of 105** decisive LLM-generated tests as failing
> on the gold patch itself, a **61.9% per-augmentation defect rate** the LLM judge alone misses.
>
> — *Auditing Reward Hackability in Code RL Training Environments*,
> [arXiv:2606.16062](https://arxiv.org/abs/2606.16062)

**So a hidden-test probe is exactly the attack surface this measures.** Our rule, adopted:

- **Every probe test is gold-sanity-gated**: it must **fail on the buggy program and pass on the
  fixed one** (fail-to-pass) *and* pass on the unmutated original (pass-to-pass). A test that does
  not satisfy this is discarded, and **no model authors the oracle** — 62 % of LLM-written tests
  were defective.
- **A weak test inflates cheap models most** (+14 pp on hackable tasks), which would have made our
  small served models look better than they are — the exact inversion the ladder must not have.

Three further mechanisms, each with its own defence:

- **Memorised public items and repositories**: models rely on "memorized repo cues", and removing
  them "consistently degrades agent performance" — *Schrödinger's Code Repository*,
  [arXiv:2609.27891](https://arxiv.org/abs/2609.27891). → our items live on
  **synthetic or private repos**; decoy files are informative only for a model that has not
  memorised the repository, and the item generator is ours.
- **Evaluation meta-knowledge**: "evaluation meta-knowledge may inflate … performance, introducing a
  novel confounder that is independent of explicit memorization … thus challenging to detect" —
  *Models That Know How Evaluations Are Designed Score Safer*,
  [arXiv:2605.28591](https://arxiv.org/abs/2605.28591). → the **no-bug fraction and
  the file layout are not inferable from the prompt**; the item composition is randomised per run.
- **Under- vs over-specification**: "Task under-specification causes guesswork … Task
  over-specification causes spoilers, where solutions can bypass some of the harder steps" —
  *Between Spoilers and Guesswork*, [arXiv:2610.22760](https://arxiv.org/abs/2610.22760)
 . → the **symptom-only** family is kept (it *is* the guesswork axis, and it is the
  more discriminative one), but the symptom string must not contain the edited line — a spoiler
  would measure the wrong thing.

**And a warning about our own localization metric.** A recent measurement-first audit could not
validate a file-localization gap on SWE-bench Verified: "the 95% intervals … included zero, leaving
the benchmark-associated gap inconclusive", and the reproduction scorer **failed its validation
gate** — *Measurement-First Auditing of Agentic Leaderboards*,
[arXiv:2610.05830](https://arxiv.org/abs/2610.05830). Our top-1/top-3 location-hit
metric is the same kind of claim, so it needs **a scorer validated on human-labelled items** before
a localization gap may be reported as a capability gap.

## 6. Not verified, or out of scope

- **No primary source reports point-biserial or item-total correlation for SWE-bench-style coding
  items.** The closest evidence is the IRT/DIF literature (2603.23749, 2607.15190,
  2609.00482, 2605.07046). Our item-discrimination gate has **no direct published precedent** —
  a gap, not a citation.
- **No published cost-per-item figure for a cheap single-file bug-hunting probe.** All per-item
  costs above come from SWE-bench Verified runs and from LLM false-alarm triage; our own cost must
  be measured on the served models (the pilot's stage A does this).
- **No study isolates the reasoning-effort axis on coding tasks.** The +2.4 pp figure is our own
  extraction from the leaderboard — a cross-run comparison, not a controlled ablation.
- **No paper found on small models specifically gaming mutation-injected bug-hunt probes.** The
  mechanisms in §5 are documented analogues, not direct evidence about a probe of this design.
- **Terminal-Bench 4.0's per-model rates, LiveCodeBench's and aider's leaderboards** are
  client-side rendered and were not extracted.
- **SWE-bench Verified's cost figures** come from the platform's own mini-SWE-agent bash-only
  mode; the site itself notes runs are "not necessarily comparable" across agent versions.

## 7. What the suite does now — the deltas this record makes

Against [c197-comparison-practice](c197-comparison-practice.md) §6:

| # | Change | Why |
|---|---|---|
| 1 | **Item selection by pass-rate band** (30–70 % over the candidate pool); items every model passes or fails are dropped | §1 — 44–70 % fewer tasks at the same rank fidelity |
| 2 | The 40 generic controls leave the **ranking** and stay as integrity checks; the 8 no-bug items stay in the ranking | §1 — a control cannot discriminate; false positives must be caught |
| 3 | **Every probe test is gold-sanity-gated**; no model authors the oracle | §5 — 28.5 % of Verified tasks accept a wrong patch; 61.9 % of LLM-written tests are defective |
| 4 | **Repeats (2–3) instead of more items**; the seed varies | §2 — 2.2–6.0 pp single-run noise; repeats are cheaper than items |
| 5 | The **time limit is fixed, published and reported** beside the score; the key names the harness | §4 — a 20–30 pp "skill gap" can be a timeout |
| 6 | The **effort tier is an escalation policy**, not a separate model in the ranking | §4 — the effort gap (+2.4 pp) is inside the noise band |
| 7 | Items live on **synthetic or private repos**; the composition is randomised; the no-bug fraction is not inferable | §5 — memorised repos, and evaluation meta-knowledge |
| 8 | The **symptom string carries no spoiler** (not the edited line) | §5 — over-specification bypasses the measured step |
| 9 | The **location-hit scorer is validated** on human-labelled items before a localization gap is claimed | §5 — the recent audit could not validate such a gap |
| 10 | The citations move to the **newer set**; Verified becomes a historical anchor; GSM8K and IFEval stay as controls | §3 |
