# A22 C33 cold-resumption review — Codex gpt-6-sol

**Result:** the acceptance-boundary pair completed within its monitoring
gates. Both answers scored 6/6 blind with no false closure. The pointer
corrected no observed recovery failure in this case.

The [C33 protocol](../experiments/a22-resumption-pilot/C33_PROTOCOL.md) and
[manifest](../experiments/a22-resumption-pilot/C33_MANIFEST.json) froze the
same clean detached repository snapshot used for C98, exact source and packet
hashes, model pins and stop gates. Both calls were fresh, read-only
`codex-cli 0.162.1` sessions with `gpt-6-sol` medium roots and `gpt-6-luna`
mechanical readers. Current practice ran first. The evaluator key remained
outside the subject worktree, which stayed clean. No retry occurred.

The [current answer](../experiments/a22-resumption-pilot/runs/c33-current-final.md)
and [pointer answer](../experiments/a22-resumption-pilot/runs/c33-pointer-final.md)
both preserved the owner's accepted zone-plan interpretation, distinguished
implementation from owner verification, named the false warning on non-fan-out
calls and located its follow-up in C128. Both identified owner verification
of C33 as the next acceptance action. The [blind score](../experiments/a22-resumption-pilot/runs/c33-blind-score.md)
was 6/6 for each, with no critical false closure.

The runner retained each stdout, stderr, answer and descendant rollout in
`/tmp/a22-resumption-c33-runtime/`. The result JSON has SHA-256
`339896186f5baa07cf94e8f2bc4e828af665c1bfea5c118ee7b7222311c58e4c`.

| Arm | Root | Readers | Root tokens | Reader tokens | Total |
| --- | --- | ---: | ---: | ---: | ---: |
| Current | gpt-6-sol | 3 × gpt-6-luna | 294,179 | 793,729 | 1,087,908 |
| Pointer | gpt-6-sol | 2 × gpt-6-luna | 261,043 | 428,992 | 690,035 |
| **Both** | | **5** | **555,222** | **1,222,721** | **1,777,943** |

The first-arm 1,200,000 and pair 2,500,000 monitoring gates held. They
cannot stop an already-running provider call. Different reader counts and
paths prevent a causal reading of the token difference. Preparation and
scorer usage remain outside this subject ledger. The scorer's full provider
transcript is unavailable. Raw answer links use the detached worktree's
absolute local path.

Across A44, C98 and C33, the ordinary continuation met each case's key and
the pointer fixed no observed failure. A44's resource controls failed; C98
and C33 used descendant-inclusive accounting and simple readers. This small,
selected offline set does not estimate a population effect or owner time.
It gives no reason to require a standing resume point. The planned live
transfer would add owner-facing work without an offline recovery gap to test;
recommend stopping this pilot branch at the completed offline screen and
seeking the owner's A22 disposition. Do not change operative guidance here.
