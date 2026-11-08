# C197 ranking method: how to rank served models cheaply and automatically

> Point-in-time survey carried for task C197; the method lives in the design.

**Answers:** what measurement method a per-harness model profile can use — which probe families,
how they are graded, how many items and repeats a ranking needs, what a long-context probe must
look like, and what the method must not do.

**Task:** C197 (per-harness model profiles). The ranking produced here feeds akmon's model
routing: which concrete model each delegate role (worker / mid / reasoner / auditor /
orchestrator) runs on.

**Status of the sources:** the four load-bearing papers below (IFEval, RULER, Miller's *Adding
Error Bars to Evals*, Sclar's format-sensitivity study) were **fetched and read in this session**;
the rest are cited from the research pass and are marked *(not re-verified here)*. Numbers taken
from a paper's body rather than its abstract are marked *(body)*.

---

## 1. The constraints that shape the method

The endpoint serves **seven ids** across three families ([c197-qwen-model-surface](../experiments/c197-qwen-model-surface.md)
(d)): four `qwen3.8-*` ids, `ornith-1.5-9b` and `minimax-m3.1-flash`. The measurement must:

1. run **without a human in the loop** — the daily check is unattended;
2. be **cheap enough to run daily** over seven models;
3. produce a **ranking**, not an absolute quality number — no human labels, no reference model;
4. be **comparable across days** — a number that moves with the weather is worse than no number;
5. work **across model families** whose chat templates and reasoning switches differ.

Point 4 is the one that decides the rest. A daily number is an *estimate of a ranking*, so the
artifact to keep is the **rank plus its error bar**, and only a change larger than the bar is
acted on.

## 2. What the research says

### 2.1 Graded beats judged

- **IFEval** (Google, arXiv:2311.07911 — *fetched and read*): 25 types of **verifiable
  instructions**, ~500 prompts, each checked by deterministic code; the paper's stated motivation
  is that human evaluation is "expensive, slow, and not objectively reproducible" and
  LLM-judged evaluation "is potentially biased or limited by the ability of the evaluator LLM".
  → A daily probe that grades itself with code has no judge in it at all.
- **GSM8K** (arXiv:2110.14168, *not re-verified here*): 8.5K grade-school word problems with an
  exact final number after `####` — exact match, no reference model at eval time. → The cheapest
  capability probe with a checkable answer.
- **Judges are the weak link.** MT-Bench (arXiv:2306.05685, *not re-verified here*) documents
  position, verbosity and self-enhancement biases; the position-bias study (arXiv:2305.17926,
  *not re-verified here*) reports answer-order swaps flipping a large share of verdicts; a
  panel of small judges (PoLL, arXiv:2404.18796) beats one large judge at a fraction of the cost;
  length-controlled win rates (arXiv/2404.04475) raise the correlation with human preference from
  0.94 to 0.98. → A judge may *audit* a graded score; it must not *be* the score.

### 2.2 Prompt format is a first-order effect

**Sclar et al., ICLR 2024** (arXiv:2310.11324 — *fetched and read*): "performance differences of up
to **76 accuracy points** when evaluated using LLaMA-2-13B" across meaning-preserving format
changes; sensitivity persists with model size, more few-shot examples and instruction tuning; and
format performance correlates only weakly **between** models — so a format that flatters one model
flatters a different one. → The comparison must pin **one request envelope** for every model, and
a change to that envelope starts a new measurement series rather than continuing the old one.

On this endpoint the envelope has an extra axis: the reasoning switch. `qwen3.8-27b` and
`qwen3.8-27b-nothink` are **different served ids** with different output ceilings (16384 vs 8192)
([c197-qwen-model-surface](../experiments/c197-qwen-model-surface.md) (d)) — a mode is a different candidate, not a
flag of one, and the mode must be recorded with every score.

### 2.3 Long context needs a profile, not a number

**RULER, COLM 2024** (arXiv:2404.06654, GitHub NVIDIA/RULER — *fetched and read*): vanilla
needle-in-a-haystack "is indicative of only a **superficial form** of long-context understanding";
RULER expands it with "diverse types and quantities of needles" and adds two task categories —
**multi-hop tracing** and **aggregation** — that test behaviour beyond searching. Across **17**
long-context models and **13** tasks, despite all claiming **32K+**, "only half of them can
maintain satisfactory performance at the length of 32K". The paper's effective-context-length
notebook (in the body, not the abstract) keeps the length at which a model still retains 85% of
its peak vanilla-NIAH score — the gap between *claimed* and *effective* window. → A long-context
probe must report **accuracy per depth and per length**, never one average, because the U-shape
(the "lost in the middle" effect, arXiv:2307.03172, *not re-verified here*) is exactly what an
average hides.

### 2.4 How many items, and how many repeats

**Miller, *Adding Error Bars to Evals* (Anthropic)** (arXiv:2411.00640 — *fetched and
read*; the numbers quoted below are from the paper body, not the abstract): treat eval questions as
draws from an unseen super-population; report error bars; size the experiment for the difference
you want to detect. The practical consequences for a daily run:

- a suite of a few hundred items resolves **differences of roughly 5 points**, not 1–3 points —
  so the daily artifact is a **rank with a confidence band**, and re-bindings are made only when
  the band moves;
- **repeats (K) reduce the variance of the mean** (mean of K samples has variance σ²/K); the
  paper's guidance is that K should be substantially larger than 2 for the reduction to matter;
- **clustering matters**: items that share a template or a haystack are correlated, so the
  standard error must be computed **per cluster (template), not per item** — otherwise the error
  bar is understated by a factor of two to three;
- **paired comparison**: two models scored on the *same* items correlate, and the paired difference
  has materially smaller variance than the two independent scores;
- **temperature 0 does not buy stability** — greedy decoding still varies run to run (vLLM's own
  docs state that reproducibility is not guaranteed by default). Lowering the temperature can even
  *raise* variance; fix the seed, keep the model's default sampling, average over K.

→ Consequences for the profile: keep the **per-item raw scores**, not only the aggregate, so a
later run can be compared **paired** against the stored baseline; compute the standard error **per
template cluster**; and treat sub-5-point differences as noise.

### 2.5 What the research says not to do

| Do not | Why |
|---|---|
| use an LLM judge as the primary score | position/verbosity/self-preference biases (MT-Bench, arXiv:2306.05685); a judge must itself be validated |
| run public benchmark items as-is | contamination survives paraphrase and translation (LiveBench, arXiv:2406.19314, exists for this reason) — **self-authored synthetic items** are cheaper and clean |
| run SWE-bench Verified daily | ≈$0.75/task × 500 per model per run, plus hours of wall clock; keep a terminal-style subset instead |
| use MMLU at full size | 14K items, a documented error rate, and weak ranking signal for a daily loop; a small self-authored 4-choice set is enough |
| compare models under different chat templates or envelopes | up to 76 accuracy points of pure format effect (Sclar) |
| mix reasoning and non-reasoning modes in one comparison | the mode is a different model on this endpoint |
| treat one daily number as the artifact | it is an estimate; the artifact is the rank and its band |

## 3. The chosen method (superseded)

The generic-families design (the original §3.1–§3.3, not carried) was rejected for measuring general model skills rather than the delegates' work.

## 4. What this means for the daily check

The daily check must **not** re-run the suite: 7 models × 540 items × K is a refresh, not a check.
The daily step compares the **served set** (one `GET /v1/models` — [c197-qwen-model-surface](../experiments/c197-qwen-model-surface.md)
(d)) against the set the stored measurement covers, and the **age** of the measurement:

- served set unchanged and measurement fresh → nothing to say;
- a model added, removed, or re-ceilinged → offer a refresh (the ladder's membership or a model's
  context ceiling may have changed);
- measurement older than the owner's interval → offer a refresh.

A refresh re-runs the suite, writes the new measured result **beside** the old one (never over),
and the owner approves before anything is re-bound.

## 5. Open questions

- **Self-authored items are the honest choice but need a generator.** akmon would need a seeded
  generator per family, and a regeneration cadence so the suite does not leak into the models it
  measures. Not yet designed.
- **The judge question is deferred, not answered.** If a role's quality cannot be captured by a
  graded probe (helpfulness of a long answer), the panel-and-rubric route is the documented
  fallback — but it is a separate, more expensive step and is out of the daily path.
- **What a role means in numbers.** The mapping from probe families to akmon's roles (worker /
  mid / reasoner / auditor / orchestrator) is a design decision the owner has not made; the superseded
  §3 states a proposal, not a fact.
- **Cost per refresh on the served models** is GPU-time and was not measured.
