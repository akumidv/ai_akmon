# TASKS — keystone development backlog

The single backlog for developing the keystone standard itself. Format:
[`pipelines/tasks.md`](pipelines/tasks.md). Directions / model gaps: [`ROADMAP.md`](ROADMAP.md).

> This is keystone's *own* backlog (evolving the standard), distinct from a consuming
> project's `_forge/TASKS.md`.

## Status

Tooling spine (`bin/sync.py`, `bin/verify.py`, vendor-neutral `hooks/hook_core.py`) exists and
is **tested** (`tests/`). Remaining work is contract specification + scale hardening, not new
mechanism.

## Active / blocked / deferred

- T17 · `_forge/` path is configurable, not fixed · active · architect · `_forge/` is the *suggested* dev-layer path; the model/tooling must treat it as a configurable root (one declared place, e.g. AGENTS.md), not a hard-coded literal. Audit hard-coded `_forge/` in bin/sync.py, bin/verify.py, hooks, and docs
- T18 · release tool: pin-bump subject · deferred · engineer · the 3rd release subject (keystone pin bump recorded in a consuming project); only after keystone+package subjects settle · [design](design/release-versioning.md)
- T16 · cross-agent contract v2 · deferred · architect · skill/role inventory beyond thin pointers · [design](design/cross-agent-contract-v2.md)
- T9 · harden git-commit-guard parsing · deferred · engineer · close regex bypasses only if a real one bites
- T4 · orchestration / role handoffs · deferred · architect · until role routing causes real friction (4 roles now; release routes) · [ROADMAP O4](ROADMAP.md)
- T6 · OPERATE mode · deferred · architect · keep as design note until a runtime actor exists · [ROADMAP O1](ROADMAP.md)

Trim rationale (T4/T6/T9/T16/T18 "deferred") is recorded in ROADMAP O# / the release design; do
not re-expand without a reason. The T3 release design (ADR 0001) is implemented (T10–T13, T15);
T14 shipped the release skill/tool (keystone + package subjects) — T18 is the deferred pin-bump
follow-up; T16 is the deferred O3 v2 design. T17 surfaced while building T14 (paths are hard-coded).

## Done

See [`TASKS_ARCHIVE.md`](TASKS_ARCHIVE.md).
