# A22 P3 — decision-ground routing packet

This is a sealed candidate packet, not authorization to run a model or change operative guidance.
It implements four P3 pairs as eight constructed neutral cards. A is the no-guidance
qualification arm; B is the current akmon architect baseline; C is B plus only the frozen
decision-ground clause. There are no examples or delivery arms.

## Build and seal

Run, without model calls:

    python3 build_cases.py
    python3 build_arms.py
    python3 qualify.py
    python3 check_bundle.py --write-seal

The bundle checker validates eight cards, exact menu ids, hidden-oracle leakage, B as a strict
prefix of C, and rendered arm hashes. It excludes Python bytecode and run-output artifacts from
the frozen-input seal. Only --write-seal writes seal.json and SHA256SUMS; its ordinary mode
verifies only and fails if accepted sealed input differs.

## Execution gate

Before any model call, the owner must record the exact CLI/harness/model/effort pins, independent
scorer model pins, scorer token and spend cap, and mechanics preflight result. The driver must use
two turns, no tools, an out-of-repository scratch directory, exact-id menu routing, and rollout
verification. Every subject gets a second turn: the selected item output for an exact menu request,
or the card's fixed unavailable-item response otherwise. The driver records a run-attempt marker
before dispatch, so a failed or interrupted attempt consumes the run budget. Tool-use checks inspect
the returned and persisted event streams after each dispatch. Do not substitute T2 delivery arms or
T3 examples arms.

Qualification is 8 cards x 2 tiers x 2 repeats under A = 32 subject runs. A card/tier qualifies
only when both blind scorers fail the same A repeat. Seal the resulting map before B/C. Continue
only with at least four qualified strata and at least one from every pair. B/C uses two repeats
per qualifying stratum and may have at most 64 runs, so scored subject runs total at most 96.
Predeclared mechanics/defect reruns may use at most 24 more; 120 two-turn subject runs is absolute.
The input cap is 40k per turn, with a predeclared C-only 50k exception if its frozen payload needs it.

Two independent blind readings are required for every output; no adjudication calls are allowed.
At most 240 scoring passes, including defects and preflight, are allowed. A practical benefit
requires at least three fewer C failures than B under both scorers, and no pair with at least two
more C failures under both scorers. Any other outcome is inconclusive or worse, never equivalence.

## Scoring and audit

Create packets with score_packets.py, give each scorer only those packets and
scoring/scorer-prompt.txt, then retain both TSV readings without adjudication. Retain failed
executions, discarded outputs, reasons, sealed maps, exchanges, records, scorer TSVs, and final
SHA256SUMS. A repair may rerun only the affected defective cell and may not change a sealed card,
rubric, arm, or map.

The driver writes `<run-id>.turn<N>.stdout.txt`, `.stderr.txt`, `.events.json`, and
`.dispatch.json` in `runs/` for each attempted turn before it accepts or rejects the dispatch.
Keep these files for failed, interrupted, and successful attempts. To qualify A cells, score all
32 packets and run `python3 grid.py <scorer-1.tsv> <scorer-2.tsv>`. The importer requires complete,
matching element rows from both scorer TSVs and verifies each TSV verdict against the sealed A map,
run record, two-turn exchange, and their recorded hashes before it writes any B/C grid.
