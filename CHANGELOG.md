# Changelog — keystone

Consumer-facing release notes for the **keystone standard** (repo `ai_keystone`, mounted as
`_forge/keystone/`). It tells a consuming project *what changed and whether it breaks them* before
they bump the pin. Convention ([ADR 0001](meta/decisions/0001-release-and-roles-model.md)):

- **Versioning `v0.x.y`** while pre-1.0 — bump `x` for a **breaking** change to layout, required
  files, or a role/pipeline contract; bump `y` for minor/patch.
- Entries are grouped **Added / Changed / Fixed / Breaking**; every `consumer-visible`,
  `migration`, or `breaking` change gets a line. `internal` changes need no entry.
- A `Breaking`/`migration` line is a consumer's **re-attach checklist item** (the bump procedure
  in [BOOTSTRAP.md](BOOTSTRAP.md) diffs the version window and walks them), so write each as
  something a consumer can *verify and act on* — name the file/path/contract that moved — not just
  *read*. The procedure lives in BOOTSTRAP; this changelog stays the record of *what changed*.
- **No dates** — the git tag is the timeline ([tasks](pipelines/tasks.md) §No dates).

## Unreleased

## v0.2.1

### Added
- **Integration record `<FORGE_ROOT>/.keystone.toml`** ([BOOTSTRAP.md](BOOTSTRAP.md) §C) — a
  machine-readable (TOML) record of the keystone version a project sits on, plus its pinned test
  env. The agent writes it on attach/realign (step 6); `verify.py` validates it; the bump procedure
  diffs it against this CHANGELOG to compute which `Breaking`/`migration` entries still need
  verifying. Read via `tomllib`, with a stdlib line-parser fallback for host Python < 3.11.
- **Version-windowed delta-check** in the bump procedure ([BOOTSTRAP.md](BOOTSTRAP.md) "Pull the
  latest shared layer") — `from` = recorded version, `to` = target; walk only the `Breaking`/
  `migration` lines in `(from, to]` as a checklist.
- **Optional `[test].runner`** in `.keystone.toml` ([BOOTSTRAP.md](BOOTSTRAP.md) §A5/§C) —
  attach pins the project's existing test env (its own manager, or a `_forge/.venv` only when the
  project has no Python env) and `release_check` runs it verbatim instead of guessing. Absent →
  discovery fallback, so projects without the field are unaffected.

### Changed
- **`verify.py` validates `<FORGE_ROOT>/.keystone.toml`** on a consumer (where keystone is a
  mounted submodule); skipped when run against the keystone repo itself. A *missing* record is a
  non-gating note (does not fail `--strict`); only a *present but malformed* record (missing
  required keys) is an error. Adopting the record is optional — a realign writes it.

### Fixed
- `verify.py` now checks `roles/review.md` exists (it was added as a role but left out of the
  required-files list).
- `tools/release/release_check.py` test-runner resolution: it now prefers the dev-layer venv
  (`_forge/.venv`), invoked as `<venv>/bin/python -m pytest` (not the `bin/pytest` console script,
  whose baked-in shebang breaks on a relocated venv); and when it falls back to `uv` it installs
  pytest on the fly (`uv run --with pytest`) — a bare `uv run pytest` ran in an ephemeral env
  without pytest and failed the release check on hosts with `uv` but no pytest on PATH.

## v0.2.0

### Added
- **`release` skill** ([`skills/release/SKILL.md`](skills/release/SKILL.md)) — the first keystone
  skill; the agent-facing how-to for the release role (frame → collect → classify → gate → verify →
  handoff), with the D5 stop boundary.
- **`tools/release/release_check.py`** — the first keystone `tools/` entry; a propose/prepare release
  tool (`--state` / `--check` / `--plan`), subject-parameterized `--subject {keystone,package}`
  (pin-bump deferred, T18). Runner-resilient verify (`uv` → `.venv` → system `pytest`); never
  commits/tags/pushes. Driven by the `release` skill (T14).
- **`tools/README.md`** — the keystone SHARED `tools/` index, with the `tools/` vs `bin/` boundary.
- **`meta/bin/validate.py`** — the dev-layer validator (counterpart to `bin/verify.py`): checks
  keystone's own tree, runs the synthetic-fixture self-CI, and runs the unit tests. A consumer
  never runs it; keystone runs it in-tree. (C7)
- **BOOTSTRAP dev-layer venv** — attach (§A step 5) now provisions a `_forge/.venv` and installs
  the agent-tooling deps (pytest) **when the project language is not python/mixed**, so the
  keystone-dev validator and any future deps-bearing tool can run on a non-Python project. The
  venv lives outside the submodule, is gitignored (§D), and is never needed for the stdlib-only
  consumer CI checks. (C8)

### Changed
- **Sharper SessionStart role hint** — the active-agent reminder now carries the DEVELOP routing
  discriminator (decompose → review · construct → architect · realize → engineer) up front, when
  the project has dev agents, instead of a vague "pick the one the task calls for". The agent gets
  the picking rule at session start, not only after a code/planning edit. OPERATE-only projects
  keep the generic line. (A10)
- **Configurable dev-layer root** — `_forge/` is now the *default*, not a hard-coded literal. A
  project may relocate the dev layer by declaring **`FORGE_ROOT`** (a project-root-relative path,
  e.g. `tools/ai`); keystone then mounts at `<FORGE_ROOT>/keystone` and `sync.py` / `verify.py` /
  the hooks derive every path (generated pointers, hook commands, the do-not-edit banner) from it.
  Unset → `_forge`, byte-identical to before. Documented in MODEL.md §2 + BOOTSTRAP §A. (A4)
- `verify.py` gains `check_keystone_gitignore` — warns when the keystone submodule has no
  `.gitignore` ignoring `__pycache__/` (so a release commit cut from the submodule stays clean).
- **USE/dev verify split** — `bin/verify.py` is now the **USE-contract verifier only**: it
  dropped the keystone-self layout/CI requirements and no longer references the dev layer at all.
  keystone-self checks moved to the new `meta/bin/validate.py`. Consumer CI is unchanged
  (`sync.py --check` + `verify.py --strict`). (C7)
- **Stricter USE-surface isolation** — the develop-boundary check became
  `check_use_surface_isolation`: it now scans the *whole* USE surface (incl. `skills/`, `tools/`)
  and fails on **any mention** of the dev layer — numbered `ADR ####` / `ROADMAP O#` citations and
  dev-tree paths in links *or* inline code — not just markdown links. Generic vocabulary ("file an
  ADR") stays legal. (C7)
- **Terminology** — the third axis is now consistently called **Archetype** (was "Project type")
  across `MODEL.md`, `ARCHETYPES.md`, `BOOTSTRAP.md`, `README.md`.

### Breaking
- **Dev layer renamed `develop/` → `meta/`.** keystone's own development artifacts (CONCEPT,
  decisions/ADRs, ROADMAP, design, reviews, tests, self_ci) now live under
  `_forge/keystone/meta/`. The rename avoids colliding with the **DEVELOP** role/mode of the
  model. *Migration:* a consumer that hardcoded any `_forge/keystone/develop/...` path (CI, docs,
  scripts) must repoint it to `meta/...`. CI that ran `develop/self_ci.py` / `pytest develop/tests`
  should drop them (those are keystone-self checks, run via `meta/bin/validate.py`, not a consumer
  concern). (C7)

## v0.1.0

First tagged release of the keystone standard — the initial reviewed baseline consuming projects
pin to. Everything below is the contract a new consumer adopts on first mount; there is no prior
version to migrate from, so the `Breaking` note applies only to projects that mounted a pre-tag
keystone and still carry old-style skill frontmatter.

### Added
- **`release` role** + [release pipeline](pipelines/release.md): a subject-parameterized DEVELOP
  role (package / keystone tag / pin bump) with a two-mode cycle (lightweight cut · periodic
  cadence). Locked in [ADR 0001](meta/decisions/0001-release-and-roles-model.md).
- **`learn` role** ([learn](roles/learn.md)): the learn loop now has an owning role wrapping the
  `memory-distill` + `learning` pipelines.
- **`decisions/`** — keystone now keeps its own ADRs (this is where standard-level decisions land,
  parallel to a project's `docs/dev/decisions/`).
- **`CHANGELOG.md`** (this file) and the `v0.x.y` versioning convention.
- **Skill contract** — `SKILL.md` frontmatter now requires `name` / `description` / `when_to_use`
  / `owner`, checked by `verify.py`.

### Changed
- `verify.py` is stricter: validates the cross-agent pointer contract (vendor pointers import
  `AGENTS.md`; AGENTS.md stays hand-reviewed, not generated) and the skill contract above.
- `sync.py` now prunes orphaned banner-marked generated skill stubs; `verify.py` flags them.
- CI runs the keystone self-CI fixture (`bin/self_ci.py`) alongside sync/verify/pytest.

### Breaking
- **Skill frontmatter** — consuming projects with existing `skills/*/SKILL.md` must add the
  `when_to_use` and `owner` fields (and ensure `name` matches the skill directory), or
  `verify.py --strict` will fail. Migration: add the two fields to each skill's frontmatter.
