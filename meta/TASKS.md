# TASKS — keystone development backlog

The single backlog for developing the keystone standard itself. Format:
[`pipelines/tasks.md`](../pipelines/tasks.md). Directions / model gaps: [`ROADMAP.md`](ROADMAP.md).

> This is keystone's *own* backlog (evolving the standard), distinct from a consuming
> project's `_forge/TASKS.md`.

## Status

Tooling spine (`bin/sync.py`, `bin/verify.py`, vendor-neutral `hooks/hook_core.py`) exists and
is **tested** (`tests/`). Remaining work is contract specification + scale hardening, not new
mechanism.

## Active / blocked / deferred

Role-triad + develop/use split ([ADR 0003](decisions/0003-role-triad-and-develop-use-separation.md)):

- C6 · UserPromptSubmit role-confirm for sub-agents · deferred · verify Claude Code hook behaviour first · [ADR 0003](decisions/0003-role-triad-and-develop-use-separation.md)
- C9 · release_check.py keystone-subject scoping · active · `--check --subject keystone` from a non-Python consumer: (a) ✅ pytest-runner resolution fixed in v0.2.1 (dev-venv `python -m pytest`, pinned `[test].runner` from `.keystone.toml`, `uv run --with pytest` fallback); (b) ⬜ `verify --strict` still runs against the consumer root, so the consumer's own TASKS/CI warnings block a keystone release — scope keystone-subject verify to the submodule tree (or reuse `meta/bin/validate.py`). Surfaced cutting v0.2.0; (a) closed cutting v0.2.1
- C2 · release tool: pin-bump subject · deferred · the 3rd release subject (keystone pin bump recorded in a consuming project); only after keystone+package subjects settle · [design](design/release-versioning.md)
- A3 · cross-agent contract v2 · deferred · skill/role inventory beyond thin pointers · [design](design/cross-agent-contract-v2.md)
- C1 · harden git-commit-guard parsing · deferred · close regex bypasses only if a real one bites
- A1 · orchestration / role handoffs · deferred · until role routing causes real friction (4 roles now; release routes) · [ROADMAP O4](ROADMAP.md)
- A2 · OPERATE mode · deferred · keep as design note until a runtime actor exists · [ROADMAP O1](ROADMAP.md)

Ids use the typed scheme ([ADR 0002](decisions/0002-task-id-convention.md)): **A** architecture/
design · **C** code · **L** learning · **V** release · **N** analysis/review; the role is derived. Archived `T#` are
grandfathered (frozen), so the historical references below keep their `T#`.

Trim rationale (A1/A2/C1/A3/C2 "deferred") is recorded in ROADMAP O# / the release design; do not
re-expand without a reason. The T3 release design (ADR 0001) is implemented (T10–T15); C2 is the
deferred pin-bump follow-up, A3 the deferred O3 v2 design, A4 surfaced while building the release
tool.

## Done

See [`TASKS_ARCHIVE.md`](TASKS_ARCHIVE.md).
