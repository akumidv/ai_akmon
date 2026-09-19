# D2 ledger — retired

The D2 approval and commit-verification workflow is superseded by
[ADR 0016](decisions/0016-decision-records-and-owner-acceptance.md). This path remains as a
compatibility pointer so old links fail informatively instead of opening an apparent live queue.

- Accepted choices live as addressable blocks in thematic [ADRs](decisions/README.md).
- Open design questions live in `meta/design/`; implementation and evidence state live in
  [TASKS](TASKS.md) and reviews/measurements.
- Search for the exact marker `Legacy-ID: D2-N` to find the current semantic owner of an old ID.
- The last ledger snapshot is frozen at [archive/D2_LEDGER.md](archive/D2_LEDGER.md). It is
  historical evidence and must not receive new rows or state transitions.

There is no `approve`, `verify --commit`, Pending, Approved, or Verified transition after this
cutover. A material change to an accepted decision creates or replaces an ADR block and receives
explicit owner acceptance there.
