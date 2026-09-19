# A22 — additional decision-review session cycles

## Purpose and limits

This evidence note extends the sample in the
[decision-workflow design](decision-workflow-and-d2-register.md). The owner requested
other Codex sessions reviewing D2-related changes and other Claude sessions, with
extraction delegated to simple subagents and no external application launches.
The main agent retained synthesis and checked the separate Git example directly.

Two delegates were requested with `gpt-5.6-luna`, medium effort. This identifies the
requested routing, not an independently probed model-delivery or comparative-quality
claim. A Claude extraction turn hit a usage limit and later resumed. No session tools
were launched through external Codex or Claude, and no raw transcripts were edited.

The sample supports **repeated review, correction and acceptance work on the same
subjects in both tools**. A literal Claude-to-Codex handoff for the paired episodes
below was not established. Shared task IDs and compatible findings support a relation,
but do not prove who supplied a particular patch or how each report was transferred.
Do not convert these cases into a count of two or three cross-model cycles per D2.
Timestamps are provenance, not measurements of active human attention.

## Other Codex episodes

### X3 — C50 / D2-16: a contract defect survives a review round

At **X3:46–47**, a review reported that falsey malformed `briefs` values were coerced
to an empty map, contradicting the fail-visible contract. Warning repetition also
contradicted the stated suppression behavior, and migration lacked an end-to-end check.
At **X3:65–66**, those issues were still reported alongside a newly identified path
normalization problem. At **X3:90–91**, the later report described closure of the
shape handling, warning behavior and migration coverage, with owner D2 review still
separate from implementation readiness.

These are successive substantive findings, not just repeated demands for an approval
word. The case suggests that a resumption packet should identify which earlier
findings remain, which were fixed, and which are new; it does not justify skipping
the second review because the first one already occurred.

### X3 — C49 / D2-19: implementation corrections plus stale task wording

At **X3:113–114**, review reported false shell-write warnings from quoted text,
non-atomic marker creation, and a shared missing-session identity. At **X3:139–140**,
the report described those implementation issues as closed but retained a task-text
inconsistency: C36 still described the earlier marker/TOCTOU behavior. The work remained
unstaged and the report requested correction before landing.

This separates implementation findings from stale explanatory state. Both matter,
but neither should force the owner to reconstruct the entire design merely to learn
which part remains unresolved.

### X4 — producer/consumer mismatch in the D2 ledger itself

At **X4:3092**, parent commentary announced an already identified defect: the parser
handled escaped pipes while `add` did not escape semantic input fields. At **X4:3099**,
a subagent final delivered the corresponding finding. At **X4:3161**, the parent
reported the fix and a full add/approve/verify regression, together with broader
checks and no staging/commit. These reports are not new test runs for this research.

The order is commentary followed by a delegate report of the same finding, not a
repair proposed before the defect was discovered. A manually pre-escaped fixture
had missed the producer-path problem. That is a counterexample to treating all
rechecking as waste or test counts as evidence of semantic completeness.

**Attribution correction:** X4:3 contains a Claude scratchpad handoff for an earlier
probe. It does not establish Claude authorship or transfer of the later ledger
change thousands of lines afterwards. An initial extraction overstated this relation;
the corrected classification is a Codex review/repair episode with unproven origin.

## Other Claude episodes and the limits of pairing

### C6 — C50 / D2-16

**C6:4475** reports green checks and a missing changelog item. **C6:4487** describes
the more consequential problem: renamed agent keys could silently lose four
consumer-specific briefs. **C6:4545** reports corrections. The later decision pass
at **C6:4896** explains normalization, rejecting unmatched/colliding/malformed maps,
and a visible refusal to rebind; **C6:4933** reports an additional whitespace-boundary
clarification and a regression, then uses historical owner-verification wording while
the landing SHA remained pending.

The subject and changed contract align with X3's C50 review. However, the intervening
owner message **C6:4478** only requests a short, task-numbered account of problems for
rechecking, without recording files. It neither names Codex nor contains the unique
Codex finding phrases. This is evidence of owner-requested reconstruction and repeated
checking, **not a proven literal transfer of X3's report**.

### C6 — C49 / D2-19

**C6:3855,3949** cover initial shell-route work and a completion report. **C6:4045**
reports removal of a weak shell-write heuristic and atomic marker handling;
**C6:4126** describes another command-position fix. **C6:4487,4639** cover a further
heredoc-spacing classification issue and its correction. The D2 walkthrough at
**C6:5188,5350,5359** refines the measured route account, fallback reporting and
throttling scope, with later tests reported.

This is compatible with the contract evolution seen in X3. The nearest owner request
before the first correction, **C6:3974**, asks to check C49 review refinements but
does not identify Codex or quote its finding. The earlier heuristic appears in a
tool-use payload at **C6:3856**; it must not be presented as the final accepted design
when later messages explicitly remove it. A topic match is not proof of handoff.

### C7 — D2-1/2/3: decision acceptance is not implementation verification

**C7:3163** begins the D2-1 walkthrough; **C7:3276,3286,3326,3354** contain follow-up
changes/reports. **C7:3429** records D2-1 approval and begins D2-2; **C7:3811** records
D2-2 approval. These support iterative examination before acceptance, not a claim
that every intermediate pass was clerical.

**C7:4615** is a direct assistant report of three mechanical D2-3 implementation
defects, followed by wording corrections at **C7:4695** and an Approved report at
**C7:4736**. **C7:4810** explicitly restores the boundary: the architecture is accepted
but C17 implementation verification remains blocked on C76. This is an **open**
implementation-verification outcome, not a closed fix/verify cycle. It shows why
removing ledger state transitions must not erase truthful unresolved-work reporting.

## What changes in the design hypotheses

- Repetition has multiple causes: real defects not yet fixed, new policy boundaries,
  stale task wording, restored explanations, and acceptance/landing bookkeeping.
  A cycle should be classified by the changed claim or evidence, not just counted.
- Record the accepted decision once, but preserve its scope. Task work must still
  expose implementation defects after architecture acceptance, as in D2-3.
- Show which finding changed the decision versus which only corrected the code or
  description. Reuse unchanged rationale, without narrowing a requested full review.
- The extraction itself needs enough context: source, message kind, physical line,
  owning section/decision and what is inferred. An agent summary without those
  boundaries can turn historical or unrelated material into a current assertion.

One separate Git extraction error illustrates the last point. A delegate detached
D2-44's row from its containing section and incorrectly called it Pending. The main
agent checked the actual snapshots: it was Approved when first committed and later
Verified. The corrected example lives in the
[Git/provenance section](decision-workflow-and-d2-register.md#verification-and-sha).
This is a correction to research handling, not an additional historical user error
or evidence that one model class is generally inferior.

## Trace index and next evidence boundary

References above use physical JSONL lines, not extracted-message ordinals.

- **X3:** `/home/ai/.codex/sessions/2026/08/17/rollout-2026-08-17T08-18-14-01a00ecc-be7a-74e0-a28f-51147d2fc7ad.jsonl`.
- **X4:** `/home/ai/.codex/sessions/2026/08/07/rollout-2026-08-07T04-57-52-019fda95-b764-7092-bfa8-477d9b0e1cdc.jsonl`.
- **C6:** `/home/ai/.claude/projects/-home-ai-workspace-akmon/f2d0115c-bcc3-4fd6-b844-24f170d34b5e.jsonl`.
- **C7:** `/home/ai/.claude/projects/-home-ai-workspace-akmon/c8d142c8-d5ea-409c-b62e-57c247ec8405.jsonl`.

Explicit end-to-end cross-model transfer attribution remains unproven in this bounded
extension. The Codex thread `01a041de-da04-7643-87ad-080598291ec6` was also considered
but is not counted as an established Claude handoff. Do not restart a global transcript
census to fill that gap by volume. A later targeted check can use an identifiable
handoff or matching revision if causal attribution becomes necessary to the choice.
The current examples are enough to challenge a blanket “all repeat review is waste”
claim, not to estimate time savings or compare model quality.
