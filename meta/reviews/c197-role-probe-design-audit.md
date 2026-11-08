# C197 audit of the role-linked probe design, by Claude

> Point-in-time review carried for task C197; the design it audits is not carried here.

- **Task:** C197 (per-harness model profiles) — the probe suite proposed in
  [c197-ranking-method](c197-ranking-method.md) §3 (superseded) and
  [c197-comparison-practice](c197-comparison-practice.md) §6.
- **Class:** state — an external assessment of a proposed design, before it is measured.
- **Reviewer:** Claude (`opus`), run through the Claude Code CLI on with the owner's
  directive: «let's also audit the proposed model grades for roles through Claude … first do the review, then make the revisions based on the review, then measure with Claude».
- **Material:** the owner's requirement, c197-ranking-method §3, c197-comparison-practice §6, the design
  §10 stages 0–3, and
  `tools/model_routing/routing.py` (`compute_binding`).
- **Limits of this record:** the reviewer ran with web fetch and search **refused**, so every paper
  it cites is **not verified here** — the citations are its own, not checked against the source.
  Its own file write was **refused** by the harness, so the reply below was transcribed by the
  orchestrator from the CLI's stdout; the wording is the reviewer's, the file layout is not.
- **Owner decisions this audit feeds:** the revision of the suite (design stage 0), then the
  measurement (stage 3).

## The reply

**Verdict.** The probes in c197-ranking-method §3 (superseded) test general model skills, not what akmon's delegates do. None
of them counts bugs found or fixed.

- **Arithmetic (GSM8K-style) and multiple choice** are useless for these roles. The arithmetic
  family also takes 32 % of all calls.
- **Formatting compliance (IFEval-style)** checks prose formatting, not staying in scope while
  editing.
- **Code synthesis and tool-call checks** are relevant but in the wrong shape, and mapped to the
  wrong roles.
- **Long context** runs on essays rather than code, has 40 items for a 44-cell grid, and costs
  about 10× its token budget.
- **c197-ranking-method's numbers don't add up.** Its "3.8K calls" ignores repeats (the real figure is 13,020),
  and a fixed seed makes its repeats nearly identical.

**The deeper problem: nothing would use the per-role grades.** `compute_binding`
(`tools/model_routing/routing.py:293`; the reviewer cited lines 364–383 of the source tree) builds one ordered ladder: worker is the lowest model, mid the next,
auditor the highest, and reasoner is whatever the orchestrator runs. A measured "reasoner grade" or
"auditor grade" has nowhere to go.

**The Claude calibration is sound, with four conditions:**

- grade by a paired test ("at most δ points worse than the anchor"), not by matching point
  estimates;
- call Claude through the same bare API request as the served models, not inside Claude Code;
- freeze the reference per suite version and per concrete model id, not per alias;
- use it first to check the probes are valid (if opus doesn't beat haiku on a probe family, that
  family is broken).

The risk that served models are tuned clones of Claude doesn't bias a test-graded score. It does
bias item generation and selection if Claude does either, so both must be programmatic.

**Top five changes:**

1. **Your decision:** decide whether a measured grade orders one ladder or binds each role
   separately. The second option changes the routing code and the model-routing ADR (not carried here; its number differs in this tree).
2. Replace c197-ranking-method §3 (superseded) with probes mapped to the actual delegates. These are bugs injected by code
   mutation, with clean decoy files, and graded by hidden tests and line matching. The key pair is
   the same bug fixed with the traceback given vs from the symptom only; the auditor probe accepts
   or rejects candidate patches.
3. **Your decisions:** add a Claude-reference section to c197-ranking-method. You need to set the margin δ, choose
   whether the reasoner bar is opus or sonnet, and approve the API spend (about 1,440 calls per
   suite version).
4. Fix c197-ranking-method's arithmetic and statistics. Each role score will resolve only about 12–20 points
   within a few hundred items, which is enough for three bands (below haiku, haiku–sonnet, sonnet
   and up).
5. Add a safety envelope to the refresh runner: output-token caps, timeouts, a token budget, and a
   sandbox for running model-written code.

**Pilot (one session).**

- 40 small programs carrying 130 prompts:
  - 30 find-the-bug items, including 8 clean decoys;
  - 30 fix-with-traceback items;
  - 30 fix-from-symptom items on the same bugs;
  - 20 formatting and 20 arithmetic items for comparison.
- Run on all 10 models with no repeats, about 1,300 calls.
- It decides two things. Do the bug probes separate opus from haiku while the generic ones don't?
  If not, the bug-probe design is falsified. Are the served models in the same order across
  roles? If yes, one ladder is enough.
- It also measures the real token cost and checks for small models gaming the probes.
- At this size it only detects gaps of 20–25 points or more.

The `meta/reviews/README.md` index would need a row for this record. I left it alone because you
asked for one file only.

## What the audit changes, and where

Recorded here so the revision is traceable to the finding rather than asserted.

| # | Finding | Lands in |
|---|---|---|
| 1 | c197-ranking-method §3 (superseded)'s families (arithmetic, multiple choice, IFEval-style formatting, long-context retrieval on essays) test general skills, not the delegates' work; arithmetic alone takes 32 % of the calls | [c197-ranking-method](c197-ranking-method.md) §3 (superseded) — **superseded**, replaced by the role-linked suite in [c197-comparison-practice](c197-comparison-practice.md) §6 as revised below; the arithmetic/multiple-choice/formatting families leave the daily suite, and the formatting/arithmetic **comparison** items stay in the pilot only, as a control |
| 2 | the role grades have nowhere to go — `compute_binding` builds one ordered ladder | design §8 and the open call **Q-C197-LADDER-SHAPE** — an owner decision (architecture, D2); the second option changes `tools/model_routing/routing.py` and the model-routing ADR (not carried here; its number differs in this tree) |
| 3 | the calibration needs a **paired** test against the anchor, not matching point estimates; the reference must be frozen per suite version and per concrete model id; the reference must validate the probes (opus must beat haiku on a family, or that family is broken) | design §4.1 and [c197-comparison-practice](c197-comparison-practice.md) §6 — adopted; δ and the reasoner bar are owner calls (**Q-C197-REFERENCE-MARGIN**, **Q-C197-REASONER-BAR**) |
| 4 | Claude must be called through the **same bare request** as the served models, not inside Claude Code | design §4.1 — **adopted in principle, constrained in practice**: the owner's Claude access is the Claude Code subscription, not an API key; the bare-channel variant needs an API credential the owner has not provided. Recorded as an open call (**Q-C197-REFERENCE-CHANNEL**) with the default being the Claude Code CLI plus an explicit "measured under a different envelope" caveat on the reference section |
| 5 | c197-ranking-method's call arithmetic ignores repeats (13,020, not 3.8K) and a fixed seed makes repeats nearly identical | [c197-ranking-method](c197-ranking-method.md) §3 (superseded) — the arithmetic is corrected; the seed claim is carried into the revised statistics (variance reduction comes from K, and repeats at a fixed seed are near-duplicates, so repeats must vary the sampled seed) |
| 6 | the role score resolves only ~12–20 points within a few hundred items — enough for three bands, not for a fine ranking | design §4.1 and §6 — the binding becomes **banded** (below haiku / haiku–sonnet / sonnet and up), not a fine order; the pilot measures the real width before any threshold is set |
| 7 | the refresh runner needs a safety envelope: output-token caps, timeouts, a token budget, and a sandbox for running model-written code | design §6 — the runner's envelope is named as a requirement of the tool (the suite executes model-written code, so it is a sandbox boundary) |
| 8 | the pilot's shape: 40 small programs, 130 prompts, 10 models, ~1,300 calls, no repeats; detects gaps of 20–25 points | [c197-comparison-practice](c197-comparison-practice.md) §6 — **adopted in place of** the earlier ~320-items-per-model pilot; the pilot now runs once without repeats, since the point is separation, not a CI-grade interval |
| 9 | the item generator and the selection of items must be programmatic, so that a Claude-authored item cannot bias the comparison | [c197-comparison-practice](c197-comparison-practice.md) §6 — the generator's determinism is stated as a requirement, alongside the contamination argument already there |

## What this audit does not decide

- Whether the ladder is one ordered list or a per-role binding (owner call, item 2).
- δ, the reasoner bar, and the API spend (owner calls, item 3).
- Whether the Claude reference can be measured through a bare API request at all on the owner's
  account (item 4).
- Whether the pilot's 130-prompt set separates opus from haiku on the bug families — that is the
  pilot's result, and it may falsify the design.

## Sources cited by the reviewer (not verified here)

The reviewer worked without web access; these are its citations, carried unverified.

- SWE-bench (https://arxiv.org/html/2310.06770v3) — f2p/p2p grading.
- SWE-smith (https://arxiv.org/abs/2504.21798) — injected bugs that break existing tests.
- BugsInPy (https://arxiv.org/abs/2401.15481) — 493 real bugs, pip-installable.
- Defects4J (https://arxiv.org/abs/1811.02429) — 47 test-adequate patches, 9 truly correct.
- McNemar on SWE-bench Verified (https://arxiv.org/abs/2609.17394) — no adjacent top-30 pair
  separates; scaffold variance 29.8 pp against an 8.8 pp spread.
- The spread-novelty-centrality benchmark comparison (https://arxiv.org/abs/2609.01271).
- Contamination measurement (https://arxiv.org/abs/2506.12286).
