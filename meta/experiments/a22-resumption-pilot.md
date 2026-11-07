# A22 cold-resumption pilot — does a record-derived pointer beat ordinary discovery?

Task: A22 (the branch is closed by [ADR 0019](../../docs/adr/0019-collaboration-guidance-from-a22.md)
D08, without a new rule).

## Question

Does a compact pointer to existing records improve truthful recovery of a paused task over ordinary
repository discovery in a fresh session? The pilot was framed as a mechanics and usability screen,
not an effect estimate.

## Method

- **Pairs.** Three offline cases, each a pair of fresh read-only `codex exec` sessions at medium
  reasoning on `gpt-6-sol` (codex-cli 0.162.1): the current practice (ordinary repository discovery)
  and a pointer to the records. The first pair was an A44 case; the second and third were C98 and
  C33.
- **Frozen input.** Each case ran on a clean detached snapshot at a recorded HEAD. Source, prompt and
  key hashes were recorded before dispatch and rechecked after each call. The evaluator key was kept
  outside the subject snapshot.
- **Scoring.** A separate `gpt-6-luna` reader saw only two final answers, labelled X (pointer) and
  Y (current), and scored six binary items: goal, accepted rationale, truthful state, material
  limit, next action, and no unnecessary owner intake. A critical false closure was scored
  separately. The assignment was revealed after the item ratings were fixed.
- **Monitoring.** Token totals counted the root session and every observed descendant rollout,
  including cached input. A44 had a 200,000-token pair ceiling. C98 and C33 had a 1,200,000-token
  first-arm gate and a 2,500,000-token pair gate.

## Verdict

**No gain.** Both arms recovered the task in every case, and no pointer corrected an observed
recovery failure.

- A44: 6/6 for both arms (M177).
- C98: 6/6 for both arms after one rubric clarification (M178).
- C33: 6/6 for both arms (M179).
- No false closure in any pair.

Negative and operational findings:

- **A44 breached its ceiling.** The current-practice call used 216,859 input and 1,922 output tokens
  (218,781 in all), above the 200,000 ceiling. The continuation was written to run only the pointer
  arm, under a cumulative 500,000-token ceiling.
- **A44 breached both monitors overall.** The seven sessions totalled 1,567,032 tokens including
  cached input (M177). The first ledger had omitted descendants, so the 200,000 and 500,000 monitors
  were breached. Five file-reading children ran on `gpt-6-sol` against the owner's model preference.
- **The token totals are not comparable.** C98 used 716,059 tokens for the current arm and 1,461,326
  for the pointer arm. C33 used 1,087,908 for the current arm and 690,035 for the pointer arm. The
  two cases point in opposite directions, and the totals do not isolate a token-cost effect.
- **The scoring evidence is thin.** `runs/blind-score.md` is a copy of the evaluator's reply, not a
  raw transcript. The pilot kept no retained scorer transcript.

## Limits

- One case per pair. A pair cannot establish transfer, owner attention saved, or a population effect.
- The arm order was fixed, current practice first, so order is confounded with the condition.
- Each pair had one blinded reader, from the same vendor family as the subject.
- The pilot did not run a live owner-facing transfer and did not change operative guidance.

## Recorded in

- Rows [M177–M179](../MEASUREMENTS.md) in [MEASUREMENTS](../MEASUREMENTS.md).
- [ADR 0019 D08](../../docs/adr/0019-collaboration-guidance-from-a22.md#d08--close-the-cold-resumption-pilot-without-a-new-rule).
- Design [A22 fresh-task resumption pilot](../../docs/design/a22-fresh-task-resumption-pilot.md).
- Reviews [A44 pilot](../reviews/a22-cold-resumption-codex-gpt-6-sol-pilot.md),
  [C98 pair](../reviews/a22-c98-cold-resumption-codex-gpt-6-sol-pilot.md) and
  [C33 pair](../reviews/a22-c33-cold-resumption-codex-gpt-6-sol-pilot.md).

## Materials

The protocols, manifests, prompts and keys, the pair runners, the raw per-call JSONL, the final
answers, stderr and the blinded answer and score copies are the ergon's local materials at
`meta/.ergon/A22-resumption-pilot/materials/`. This document stands without them.
