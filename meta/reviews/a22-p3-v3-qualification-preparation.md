# A22 P3 V3 qualification preparation review

**Reviewer:** Codex GPT-6 (current session); two independent read-only inventories
were delegated to GPT-6 Luna. **Verdict:** the qualification design can move to
runner implementation, but it is not ready for provider dispatch.

The original P3 seal still binds eight cards, the A arm, the scoring prompt and
the legacy qualification map. That map has a complete 32-cell A grid, but its
run IDs belong to the older packet. Reusing them would violate V3's fresh-ID
condition. The new [candidate schedule](../experiments/a22-p3/runs/v3-qualification-schedule-v1.json)
allocates one fresh run, subject attempt and two subject call IDs for each
card × tier × repeat. It fixes one opaque scorer packet ID shared by Codex and
Qwen per output, two scorer call IDs, a randomized subject order and alternating
scorer order. The verifier rechecks the packet seal and rejects missing or
duplicate cells, IDs and changed second-turn material.

The [candidate packet renderer](../experiments/a22-p3/v3_qualification_packet.py)
reads only the frozen case, prompt and renderer; it checks a two-turn exchange
against the actual first prompt and the case's fixed response to a `CHECK` or
no-item reply. It passes only the exchange and scoring criteria to the scorer.
The subject runner must pass only `case["subject"]["turn1"]` and the resolved
second-turn reply: `scoring` and `leakage` coexist in evaluator JSON and must
never be supplied as a subject attachment. Both scorer routes would receive
identical packet/request bytes for a cell. The renderer adds no run, attempt,
arm, tier or model label.
Card content can still reveal its topic; blinding does not conceal that.

The qualifying predicate means both scorers fail the same *run/repeat* at the
run level (any applicable E failure). It does not require agreement on the
same E element. At least four distinct card × tier strata and one from each
of four pairs are required. This floor can select uneven coverage; the B/C
comparison must use two repeats under each arm within every selected stratum
and report coverage. The existing `grid.py` expresses the run-level rule, but
its hardcoded legacy map/output paths cannot be the V3 importer as-is.
The [candidate reducer](../experiments/a22-p3/v3_qualification_reduce.py)
requires both complete 32-cell datasets, retains E-level disagreements, and
implements that same-repeat floor without issuing a comparison permit.

The schedule, renderer and reducer started no model processes. Fifteen focused offline
tests pass; Ruff check and format are the targeted validation. No new M row is
needed because this is construction, not a provider or harness measurement.
The prior route approval authorized only `codex_scorer_route_check`. There is
still no V3 qualification ledger, provider runner, accounting and quota gate,
operational seal, static preflight or owner approval. The proposed phase must
bind the 214,673-token V3 opening, all prior evidence and the default-deny
status before any of its 32 subject or 64 scorer calls can start. No result in
this review is a qualification or scored reading.
