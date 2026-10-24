# A22 P3 V3 scorer identity after the terminal qualification attempt

**Status:** option 2 accepted for prospective implementation in
[ADR 0019 D03](../../decisions/0019-collaboration-guidance-from-a22.md#d03--prospective-p3-scorer-packet-identity-binding).
This document does not amend any sealed input, accept a scorer result,
authorize a provider call, or restart qualification. The prior
qualification successor remains terminal; its seven complete cells and eighth
partial cell do not become cells in a fresh dataset.

## Problem and invariant

In the failed Qwen reply, all four TSV rows used `gf04a4422bf50dd1` while the
packet and frozen schedule used `gf04a4422bf50dd1f` (M155). The strict parser
correctly rejected the reply. The cause of the omitted final character is not
observable from this single call. The scoring criteria, two independent blind
readings, exact E1–E4 coverage, same-repeat qualification rule, and no-retry
evidence policy must remain fixed.

The runner dispatches exactly one sealed packet per scorer call and already
binds the call to its packet, request, model, usage and raw reply in the ledger.
Packet identity must be unambiguous and independently auditable; a model's
imperfect copy of an opaque identifier must not be silently corrected.

## Options

1. **Keep the four-column TSV and strengthen exact-copy instructions.** Tell
   both scorers to reproduce the packet ID character for character and add an
   offline length check plus unscored route checks for both routes. This changes
   the prompt only and retains the current parser and downstream files. It is
   smaller, but a passing sample cannot establish reliable copying across the
   full qualification grid; one prior format route passed before call 31 failed.
2. **Remove the model-authored packet ID from the reply (accepted).** Ask
   each scorer for exactly `element`, `verdict`, and `reason` TSV columns. Accept
   only one header and one nonempty row for each expected E element, with no
   extra rows, text, tools or observable retry. The runner takes the packet ID
   solely from its sealed one-packet call record and materializes a separate
   canonical four-column TSV. Retain the raw three-column reply, its hash, the
   canonical four-column bytes and hash, and their binding to the same request,
   call, usage and ledger completion. Downstream qualification reads only the
   canonical file after verifying that binding. This removes ID copying as a
   failure mode while keeping the existing E1–E4 judgments and two-scorer rule.
   It changes the scorer response contract and evidence shape. D03 accepts
   implementation, while any provider dispatch still requires a fresh seal and
   separate phase acceptance.
3. **Normalize a near-match ID.** Rejected: inserting a missing character or
   stripping quotes would accept a model-authored identifier that differs from
   the sealed packet. A near-match rule could misbind another packet, and it
   would be especially unsafe to apply retrospectively to the terminal call.

## Prospective verification and dispatch gates

- Keep prior seals, approval, raw reply, and failure record byte-for-byte.
  Correct only the unsealed report, task and M155 account of what was observed.
- If option 2 is accepted, implement a pure raw-to-canonical parser with tests
  for exact E coverage, duplicates, extra text, malformed columns, blank
  reasons, invalid verdicts, packet/call mismatch, and tampered raw/canonical
  hashes. The parser must not infer an E verdict or modify a reason.
- Render identical blind request bytes for both scorers under the new prompt.
  Keep Qwen default thinking and the accepted resource/stop conditions. Check
  remaining subject-attempt and scorer-pass ceilings before a new schedule.
- Freeze new run, packet, subject and scorer IDs; a complete fresh 32-cell A
  schedule, exact code, prompt, tests, model/CLI settings, predecessor evidence,
  private runtime and offline preflight. Route checks on both scorer paths are
  unscored mechanics evidence only. A separate owner acceptance of the exact
  new seal and phase is required before dispatch. Any malformed reply or missing
  correlated usage remains terminal for that seal under `OBSERVED_NO_RETRY`.
- No B/C comparison is authorized by this proposal. Qualification requires a
  complete fresh 32-cell dataset and the unchanged two-scorer floor.

**Accepted scope:** option 2's prospective scorer response/evidence contract.
This decision does not change the verdict on the failed call.
