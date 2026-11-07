# A32-E2 — does an offline claim auditor reach its pre-registered gate?

Task: A32 (the auditor screen, C113).

## Question

Does any auditor configuration, at its pre-registered score cutoff, reach recall of at least 0.6 on
failed runs, recall of at least 0.6 on the P2-4 E2 failures, and a false-flag rate of at most 0.2 on
the frozen cohort of 161 exchanges?

## Method

- **Cohort.** The 161 E1 exchanges outside the pilot ids: 84 primary failures, 28 P2-4 E2 failures and
  77 passes.
- **Configurations.** Nine, giving 1,449 prompts and calls:
  - Claude Haiku, a Codex reserve model and Qwen 3.8 27B, on the exact E1 prompt, scored by verdict
    only.
  - Claude Sonnet 5 and `gpt-5.6-terra`, on the V0 and V1 prompts, with cutoffs 9 and 8.
  - `gpt-6-sol`, on V0 and V1, with cutoff 9.
- **Prompts.** V0 adds the pilot's `mismatch_score` request to the E1 prompt. V1 supplies the actual
  `trial/arm/role` instruction file delivered to that subject. V1 does not rebuild the whole harness
  context.
- **Calibration from the pilot.** `gpt-5.6-terra` at cutoff 8 gave 2 of 12 passes flagged, against 4
  of 12 at cutoff 7; 8 was the lowest tested cutoff within the 0.2 false-flag limit. Sonnet's cutoff 9
  is a prospective fallback: only 24 of 30 pilot V0 responses were valid. The pilot's V1 run
  hardcoded `B_full`, so it is not calibration for the corrected treatment.
- **Run.** A mechanics preflight, a bounded canary of one exchange per configuration, then the full
  run with a halt marker per route on quota or authentication errors. Invalid records keep their
  attempt history and are rerun; a valid record is never called again.

## Verdict

**No E2 result.** The run stopped at 1,378 of 1,449 valid records. Claude mid-V1 had 90 of 161 valid
cells, and a `g7684` `invalid_exit` latch stood open. An incomplete cohort is ineligible for the gate,
so no configuration passes or fails it.

The earlier E1 screen was negative. Recall on failed runs, recall on P2-4 E2 and false-flag rate, on
the E1 prompt:

| Configuration | Recall, failed | Recall, P2-4 E2 | False flags |
| --- | ---: | ---: | ---: |
| Claude Haiku | 0.28 | 0.37 | 0.22 |
| gpt-reserve | 0.58 | 0.50 | 0.44 |
| Qwen 3.8 27B | 0.23 | 0.32 | 0.22 |

None of the three met the recall and false-flag limits of the gate: Haiku and Qwen missed recall,
and gpt-reserve missed the false-flag limit.

Runner findings, fixed before the full run: the classifier halted valid runs on `g2167` ("quotation")
and `g2417` ("unauthorized").

## Limits

- The pilot calibration was small (for `gpt-5.6-terra`, 12 passes and 18 failures), and it does not
  establish Sonnet's cutoff.
- The cutoffs were fixed before the run and were not chosen after seeing E2 outcomes.
- Qwen ran in safe mode with plan approval, but built-in tools stayed callable: in M99, 9 of 193
  headless calls invoked one or two tools. A recorded tool call invalidates the Qwen result.
- The canary was a mechanics and provenance check: one record per configuration cannot estimate
  quality.
- The raw run directory lay outside the tree and is absent; the materials hold the runner and its
  tests only.

## Recorded in

- Rows [M98, M99 and M102](../MEASUREMENTS.md) in [MEASUREMENTS](../MEASUREMENTS.md): the E1 screen,
  Qwen tool use and the mechanics preflight.
- Design [claim-evidence checks § A32-E1 result](../../docs/design/claim-evidence-checks.md#a32-e1-result)
  and [§ A32-E2 follow-up](../../docs/design/claim-evidence-checks.md#a32-e2-follow-up).
- Reviews [A32-E2 protocol](../reviews/a32-e2-codex-protocol.md) and
  [A32-E2 run](../reviews/a32-e2-codex-run.md).

## Materials

The runner (`runner.py`), its README and its tests are the ergon's local materials at
`meta/.ergon/A32-e2-auditor/materials/`. This document stands without them.
