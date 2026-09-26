# T2 — qualification of the hardened cases

> **Verdict:** under arm `A` — no akmon guidance at all — six of ten case × tier pairs fail at least
> once in two repeats and enter the grid; four pass twice and measure nothing there. P2-3, the
> changed-premise case, is passed by both tiers without guidance and leaves the grid. Scoring was
> done by a separate agent that never saw the clause, the arm, the tier or the run records; a second
> scorer on a 25 % sample agreed on 22 of 23 elements and on every case verdict. Owned by A22 and
> [trial T2](../design/attention-frame-comparison.md#trial-t2--delivery-and-clause-comparison);
> row M82 in [MEASUREMENTS](../MEASUREMENTS.md).

## What ran

| Held | Value |
| --- | --- |
| Arm | `A` — the role sentence and the one-check protocol |
| Cases | P2-1 … P2-5, as fixed in [packet P2](../design/attention-frame-comparison.md#delivery-and-clause-packet-p2) |
| Tiers | the registry's strongest rung and its `mid` rung, Anthropic route |
| Repeats | two per case × tier — 20 runs |
| Harness | Claude Code 2.1.278; every run verified from its transcript (system prompt byte-equal to the arm, no tools, no instruction files, cwd outside any repository, user messages as sent) |

## Result

A pair qualifies when `A` fails the case in at least one repeat; a run fails the case when any
element fails.

| Case | Strongest | Mid |
| --- | --- | --- |
| P2-1 — configured is not active | qualifies (1 of 2 failed) | out (passed twice) |
| P2-2 — partial versus completed checks | qualifies (2 of 2) | qualifies (2 of 2) |
| P2-3 — changed premise | out | out |
| P2-4 — another agent's report | qualifies (1 of 2) | qualifies (2 of 2) |
| P2-5 — generator output as runtime behaviour | out | qualifies (2 of 2) |

What the failures were, from the element scores:

- **P2-2, all four runs:** no subject named `meta/self_ci.py` or treated the verification set as
  more than the CI output shown; three of four gave a go or a conditional go. Without the
  project's definition of "the verification", the subjects verified the change instead.
- **P2-4 and P2-5 at `mid`:** the one check requested could not test the claim (`codex --help`,
  a filesystem-wide `find`), though the final answers did not endorse the claim.
- **P2-1 and P2-4 at strongest:** one run each answered without checking, or checked something that
  could not show whether the hooks run.

P2-3 is the informative negative: with M28's supersession marker removed and M29/M62 present,
every run of both tiers compared the rows by date and method and refused the stale premise
unaided. The T1 defect was real, and the capability it hid does not need guidance at these tiers.

## Execution defects, discarded and rerun

Five cells were discarded before scoring and rerun once each, under stopping condition 3. The
menu matcher sent `codex --version` / `codex --help` requests to the "real codex turn" output
(q836, q849) or to nothing (q803), and a direct run of the SessionStart hook to the session
observation (q569, q719). The menus were repaired — a help/version item carrying real
`codex-cli 0.154.0` output, and a direct-hook item carrying the real hook stdout from the
[Step 0 transcript](t2-session-delivery-20260922.md) — and every other recorded request was
re-matched against the repaired menus to confirm its routing did not change.

One protocol limit stays: a reply that ends with a `CHECK:` line after prose is treated as the
final answer, as the protocol states. q719r did this; it scored as a pass on its own content.

## Cost

$1.38 recorded across the 20 scored runs, the five discarded cells and one mechanics run; a first
mechanics run aborted on the per-turn cap before its record was written, so its cost is not in
that figure.

## What this does not establish

That the qualified cases discriminate between the *guidance* arms — only that the floor fails
them. Two repeats per pair; one harness, one vendor; the scorers are models, and agreement was
measured on a sample.
