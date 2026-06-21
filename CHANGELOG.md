# Changelog — keystone

Consumer-facing release notes for the **keystone standard** (repo `ai_keystone`, mounted as
`_forge/keystone/`). It tells a consuming project *what changed and whether it breaks them* before
they bump the pin. Convention ([ADR 0001](decisions/0001-release-and-roles-model.md)):

- **Versioning `v0.x.y`** while pre-1.0 — bump `x` for a **breaking** change to layout, required
  files, or a role/pipeline contract; bump `y` for minor/patch.
- Entries are grouped **Added / Changed / Fixed / Breaking**; every `consumer-visible`,
  `migration`, or `breaking` change gets a line. `internal` changes need no entry.
- **No dates** — the git tag is the timeline ([tasks](pipelines/tasks.md) §No dates).

## Unreleased

### Added
- **`release` skill** ([`skills/release/SKILL.md`](skills/release/SKILL.md)) — the first keystone
  skill; the agent-facing how-to for the release role (frame → collect → classify → gate → verify →
  handoff), with the D5 stop boundary.
- **`tools/release/release_check.py`** — the first keystone `tools/` entry; a propose/prepare release
  tool (`--state` / `--check` / `--plan`), subject-parameterized `--subject {keystone,package}`
  (pin-bump deferred, T18). Runner-resilient verify (`uv` → `.venv` → system `pytest`); never
  commits/tags/pushes. Driven by the `release` skill (T14).
- **`tools/README.md`** — the keystone SHARED `tools/` index, with the `tools/` vs `bin/` boundary.

### Changed
- `verify.py` gains `check_keystone_gitignore` — warns when the keystone submodule has no
  `.gitignore` ignoring `__pycache__/` (so a release commit cut from the submodule stays clean).

## v0.1.0

First tagged release of the keystone standard — the initial reviewed baseline consuming projects
pin to. Everything below is the contract a new consumer adopts on first mount; there is no prior
version to migrate from, so the `Breaking` note applies only to projects that mounted a pre-tag
keystone and still carry old-style skill frontmatter.

### Added
- **`release` role** + [release pipeline](pipelines/release.md): a subject-parameterized DEVELOP
  role (package / keystone tag / pin bump) with a two-mode cycle (lightweight cut · periodic
  cadence). Locked in [ADR 0001](decisions/0001-release-and-roles-model.md).
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
