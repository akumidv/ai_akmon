# 0018 — Release consistency, alignment ownership, and explicit update

- **Status:** Accepted
- **Owner:** akuminov@gmail.com
- **References:** [ADR 0009](0009-packaging-package-carrier-and-mount-modes.md) ·
  [update design](../design/packaging/update-command.md) · [A23/C92](../TASKS_ARCHIVE.md)

## Accepted decision blocks

### D01 — Version and release consistency

`Decision-ID: ADR-0018/D01`
`Legacy-ID: D2-31`

Version literals, changelog state and release tags are checked as distinct carriers. Development
versions use `Unreleased`; final versions match the newest released heading; only `vX.Y.Z` is an
admissible release-tag spelling. Shared version parsing and ordering own all consumers of these
rules. Missing or inapplicable carriers are reported explicitly rather than silently equated.

### D02 — Attach, sync, and realign ownership

`Decision-ID: ADR-0018/D02`
`Legacy-ID: D2-36`

Init attaches and records a carrier; sync regenerates only Akmon-owned artifacts and checks
hand-owned ones; realign does not silently overwrite a consumer's root `AGENTS.md` or local
choices. A release communicates required manual migrations. Mounted and package carriers share
the contract while retaining their carrier-specific mechanics.

### D03 — Explicit update and rollback

`Decision-ID: ADR-0018/D03`
`Legacy-ID: D2-51`

`akmon update [--ref]` moves a pin, then realigns and verifies. Without `--ref` it selects the
newest final release and never moves backward; an explicit older ref is an announced rollback.
Each carrier uses its native safe mechanism, unsupported package managers receive the exact
command instead of an inferred mutation, and subtree mutation is printed rather than executed.
The operation never commits. Live consumer verification remains implementation evidence, not a
condition on the accepted decision.

## Rejected alternatives

- Treat a git tag as the sole version authority; it cannot represent development-ahead state.
- Let sync rewrite hand-owned integration text; it would erase local intent.
- Hide rollback or commit an update automatically; both remove owner control at the riskiest
  boundary.
