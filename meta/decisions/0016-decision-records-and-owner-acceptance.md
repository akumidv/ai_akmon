# 0016 — Thematic decision records and one owner acceptance

- **Status:** Accepted
- **Owner:** akuminov@gmail.com
- **References:** [workflow design](../design/decision-workflow-and-d2-register.md) ·
  [migration design](../design/d2-legacy-migration.md) ·
  [cutover map](../design/d2-cutover-reference-map.md) · [C94](../TASKS_ARCHIVE.md)

## Context

The D2 ledger gave consequential choices visible IDs, but made one semantic decision travel
through `Pending → Approved → Verified`, required a manually copied landing SHA, and duplicated
state across the ledger, ADR, design and task. In practice many entries still needed design work;
the administrative verification step did not prove correctness and repeatedly consumed owner
attention.

## Accepted decision blocks

### D01 — Separate design, accepted decisions, work, and evidence

`Decision-ID: ADR-0016/D01`
`Legacy-ID: D2-24`

Open alternatives and unresolved premises live in a living design or task. A consequential,
settled choice is recorded once in a thematic ADR decision block. Implementation status,
conformance checks and versioned measurements live in tasks and evidence. No second decision
ledger mirrors those states.

The owner explicitly accepts a bounded semantic scope once. Landing unchanged implementation
does not ask for the same acceptance again. A material delta from that scope returns to design
and requires a new or replacing decision block; a non-material correction is recorded in the
task or history. A commit may identify implementation evidence, but its hash is not a decision
status and is never mandatory ADR metadata.

### D02 — Addressable thematic blocks

`Decision-ID: ADR-0016/D02`

Related choices remain together in a thematic ADR, but each independently replaceable choice has
a stable `ADR-NNNN/DNN` identifier. Every block states its choice and boundary; load-bearing
alternatives, costs and reconsideration triggers remain in the ADR or its linked design. One
owner acceptance may cover a clearly enumerated coherent set of blocks. Physical file count does
not determine the number of acceptance acts.

### D03 — Lossless legacy lookup without a live legacy workflow

`Decision-ID: ADR-0016/D03`

The former ledger is frozen as historical evidence. Every old D2 ID has one canonical
`Legacy-ID: D2-N` alias at its current semantic owner: an accepted ADR block, or for an unresolved
measurement, its task/evidence owner. Historical reports retain their original language. An
alias is navigation and provenance, never status. Checks enforce uniqueness and resolution but
do not recreate approval stages.

## Consequences

- ADR status is only `Accepted` or `Superseded`; unfinished reasoning is not an ADR.
- Owner reports distinguish the decision accepted, implementation conformance, evidence limits,
  and remaining work instead of compressing them into one lifecycle label.
- Sensitive changes still require owner attention under the common guardrail, but no reminder
  may demand a D2 row or a post-landing `verify --commit` transition.
- Historical references remain meaningful and grep-friendly without leaving an apparent active
  queue at `meta/D2_LEDGER.md`.

## Rejected alternatives

- **Keep D2 as an accepted-only registry.** Rejected as a second index whose status and wording
  can drift from the ADR that owns the decision.
- **One ADR per question.** Rejected because it fragments the context needed to judge coupled
  choices.
- **One project-wide decision ADR.** Rejected because it defeats thematic reading and makes every
  unrelated change touch the same document.
- **Infer acceptance from a commit.** Rejected because authorship and landing do not establish
  owner understanding or agreement.
