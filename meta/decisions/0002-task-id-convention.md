# 0002 — Typed task-id convention

- **Status:** Accepted (owner-scoped).
- **Amended by:** [ADR 0003](0003-role-triad-and-develop-use-separation.md) — adds letter **N**
  (analysis/review) for the `review` role (the four-letter table below predates the triad).
- **Owner:** akuminov@gmail.com
- **References:** [pipelines/tasks.md](../../pipelines/tasks.md) (the normative format this locks) ·
  [roles/README.md](../../roles/README.md) (the roles a type derives) · supersedes the `T<n>`
  id rule.

## Context

Task ids were `T<n>` — a single generic kind. The owner wants the **type** of work
(architecture, design, development, …) visible in the stable id via a letter prefix, while ids
stay numeric. Two facts shaped the design:

1. **The single-letter namespace is already taken.** `D#` (DEVELOPMENT_REQUIREMENTS), `R#`
   (ARCHITECTURE_REQUIREMENTS), `O#` (ROADMAP gaps), and legacy `T#` tasks all exist. A typed
   prefix that reused `D`/`R`/`O`/`T` would be ambiguous (is `D5` a rule or a task?). This pushes
   toward a small set of letters that dodge those.
2. **A "type" overlaps the existing `role` field.** Since `type → pipeline → role` is
   deterministic, carrying both is redundant; deriving the role from the type shortens every
   entry.

A separate need surfaced: linking a task to a **GitHub issue** without making the issue number
the id (not every task has one; issues live per-repo).

## Decision

1. **Id = one uppercase type letter + a number, no separator** (`A1`, `C2`, `L1`, `V3`). Stable,
   **never reused**; the counter runs **per type**.

2. **Four type letters**, each deriving its owning role:

   | Letter | Type | Role |
   |---|---|---|
   | **A** | Architecture & design (contracts, requirements, ADRs, design concepts) | architect |
   | **C** | Code (production code, tests, refactor, dev tooling) | engineer |
   | **L** | Learning (memory distill / promotion) | learn |
   | **V** | Release (version cut / changelog / pin bump) | release |

   Architecture and design share **A** (both are architect/design-flow; a task often starts as a
   concept and yields an ADR, and the id must not change). Tooling folds into **C** (same
   engineer/code-flow). Letters avoid `D`/`R`/`O`/`T` by construction. A new letter is added only
   when a genuinely new role/pipeline appears, via a follow-up ADR.

3. **Role is derived, not stored.** The entry drops the `role` field:
   `- <id> · <title> · <status> · <goal> · [detail](link)`.

4. **GitHub issues attach to the id, optionally:** `C2[#134]` (issue in the same repo as the
   backlog file) or `C2[owner/repo#134]` (cross-repo). The local id is canonical; `[#…]` is
   provenance and is distinct from the trailing `[detail](link)`.

5. **Grandfather history.** Legacy `T<n>` ids in `TASKS_ARCHIVE.md` are frozen as-is; the typed
   scheme applies to the **live backlog** and all new tasks. History is not renumbered (so
   commit/ADR references to old `T#` stay valid).

## Consequences

- `pipelines/tasks.md` carries the normative format + the type→role table; every consuming
  project inherits it on the next pin bump.
- The live `TASKS.md` migrates its open entries to typed ids (e.g. `T17 → A1`, `T9 → C1`);
  `TASKS_ARCHIVE.md` keeps `T#`.
- `verify.py` needs no change for the id format — its task check validates status tokens and
  separators, not the id shape. (A future check could assert the typed shape if drift appears.)
- Cross-project comparability improves: the same letter means the same kind of work everywhere.

## Rollout

Applied in the same change that locks this ADR: `pipelines/tasks.md` updated, `TASKS.md`
migrated, `TASKS_ARCHIVE.md` grandfathered. No code change required.
