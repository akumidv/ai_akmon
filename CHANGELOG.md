# Changelog — akmon

Consumer-facing release notes for the **akmon standard** (repo `ai_akmon`, mounted as
`_aitna/akmon/`). It tells a consuming project *what changed and whether it breaks them* before
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

### Added
- **Model routing — capability tiers** ([MODEL.md](MODEL.md) §10, ADR 0004): task-kind →
  tier matrix and per-vendor semantic selection policy as data in
  [`tools/model_routing/registry.json`](tools/model_routing/registry.json) (project overlay:
  `<aitna-root>/model-routing.json`, deep-merged; may add per-agent `briefs`); the
  idempotent [`tools/model_routing/init.py`](tools/model_routing/init.py) computes the
  tier→model binding relative to the orchestrating model and generates the `k-*` subagent
  definitions (`.claude/agents/`, committed) plus `.claude/model-routing.local.json`
  (per-user — consumers gitignore it, with `.claude/model-routing.log`).
- **Two routing hooks**, wired by `sync.py` for Claude Code:
  [`hooks/model-routing.py`](hooks/model-routing.py) (SessionStart — binding status line /
  init instruction, weak-orchestrator warning) and
  [`hooks/delegation-log.py`](hooks/delegation-log.py) (PreToolUse `Task|Agent` — one TSV
  log line per delegation, zero token cost).
- **Tier floor guardrail** ([guardrails/_common.md](guardrails/_common.md) § Route by task
  kind) and one-line tier annotations in the triad roles and the review/code/design flows.
- **Delegation-nudge hook**: [`hooks/delegation-nudge.py`](hooks/delegation-nudge.py)
  (PreToolUse, combined matcher `Bash|Edit|Write|MultiEdit|Task|Agent`) counts consecutive
  orchestrator edit/shell calls since session start or the last subagent delegation and,
  past a threshold (default 10, env `KEYSTONE_DELEGATION_NUDGE_THRESHOLD`), injects an
  advisory reminder to route by task kind to the `k-*` delegates — once per drift episode;
  a subagent delegation resets the counter and re-arms the reminder. Never blocks. Wired by
  `sync.py`.
- **Statistics digest** (`stats-digest` skill + tool, the on-demand counterpart to the
  zero-token delegation log): [`tools/model_routing/stats.py`](tools/model_routing/stats.py)
  parses the delegation log and the current session transcript (orchestrator + per-subagent
  token usage), queries the Claude OAuth usage API for remaining session/week budget
  (degrades to `unavailable` offline), writes the full report to `.claude/stats/` and prints
  a compact digest; [`skills/stats-digest/SKILL.md`](skills/stats-digest/SKILL.md) drives it
  on the owner's chat trigger and gates learn-loop recommendations on owner confirmation.
  Known limit: the delegation log is append-only across sessions, so delegation counts span
  the log, while token stats are per-session.
- **Cross-vendor second-opinion runner**:
  [`tools/model_routing/second_opinion.py`](tools/model_routing/second_opinion.py) runs an
  advisory review at a verify/align gate through the registry-selected CLI. Claude-led sessions
  default to Codex (`codex exec`); Codex-led sessions default to Claude
  (`claude -p --output-format text`). The runner writes the full report under the configured
  per-vendor report directory and prints a digest; it is not a blocking hook.

### Migration
- Re-run `bin/sync.py` (wires the two new hooks into `.claude/settings.json`), run
  `tools/model_routing/init.py`, and add `.claude/model-routing.local.json` +
  `.claude/model-routing.log` to the project `.gitignore`.
- To use Codex-led routing or Claude second-opinion review, keep the OpenAI and Anthropic
  selection-policy/second-opinion entries in `tools/model_routing/registry.json` or override
  them in the project overlay (`<aitna-root>/model-routing.json`). Concrete model aliases come
  from local discovery / `--available`, not from committed registry data.

### Fixed
- **Codex hook output contract**: `hooks/codex-hook.py` now reads the Codex SessionStart `cwd`
  payload and `hooks/codex_adapter.py` serializes hook results as `hookSpecificOutput` JSON, so
  Codex CLI 0.142 accepts the generated SessionStart hook instead of reporting hook failure.

## v0.2.1

### Added
- **Integration record `<AITNA_ROOT>/.akmon.toml`** ([BOOTSTRAP.md](BOOTSTRAP.md) §C) — a
  machine-readable (TOML) record of the akmon version a project sits on, plus its pinned test
  env. The agent writes it on attach/realign (step 6); `verify.py` validates it; the bump procedure
  diffs it against this CHANGELOG to compute which `Breaking`/`migration` entries still need
  verifying. Read via `tomllib`, with a stdlib line-parser fallback for host Python < 3.11.
- **Version-windowed delta-check** in the bump procedure ([BOOTSTRAP.md](BOOTSTRAP.md) "Pull the
  latest shared layer") — `from` = recorded version, `to` = target; walk only the `Breaking`/
  `migration` lines in `(from, to]` as a checklist.
- **Optional `[test].runner`** in `.akmon.toml` ([BOOTSTRAP.md](BOOTSTRAP.md) §A5/§C) —
  attach pins the project's existing test env (its own manager, or a `_aitna/.venv` only when the
  project has no Python env) and `release_check` runs it verbatim instead of guessing. Absent →
  discovery fallback, so projects without the field are unaffected.

### Changed
- **`verify.py` validates `<AITNA_ROOT>/.akmon.toml`** on a consumer (where akmon is a
  mounted submodule); skipped when run against the akmon repo itself. A *missing* record is a
  non-gating note (does not fail `--strict`); only a *present but malformed* record (missing
  required keys) is an error. Adopting the record is optional — a realign writes it.

### Fixed
- `verify.py` now checks `roles/review.md` exists (it was added as a role but left out of the
  required-files list).
- `tools/release/release_check.py` test-runner resolution: it now prefers the dev-layer venv
  (`_aitna/.venv`), invoked as `<venv>/bin/python -m pytest` (not the `bin/pytest` console script,
  whose baked-in shebang breaks on a relocated venv); and when it falls back to `uv` it installs
  pytest on the fly (`uv run --with pytest`) — a bare `uv run pytest` ran in an ephemeral env
  without pytest and failed the release check on hosts with `uv` but no pytest on PATH.

## v0.2.0

### Added
- **`release` skill** ([`skills/release/SKILL.md`](skills/release/SKILL.md)) — the first akmon
  skill; the agent-facing how-to for the release role (frame → collect → classify → gate → verify →
  handoff), with the D5 stop boundary.
- **`tools/release/release_check.py`** — the first akmon `tools/` entry; a propose/prepare release
  tool (`--state` / `--check` / `--plan`), subject-parameterized `--subject {akmon,package}`
  (pin-bump deferred, T18). Runner-resilient verify (`uv` → `.venv` → system `pytest`); never
  commits/tags/pushes. Driven by the `release` skill (T14).
- **`tools/README.md`** — the akmon SHARED `tools/` index, with the `tools/` vs `bin/` boundary.
- **`meta/bin/validate.py`** — the dev-layer validator (counterpart to `bin/verify.py`): checks
  akmon's own tree, runs the synthetic-fixture self-CI, and runs the unit tests. A consumer
  never runs it; akmon runs it in-tree. (C7)
- **BOOTSTRAP dev-layer venv** — attach (§A step 5) now provisions a `_aitna/.venv` and installs
  the agent-tooling deps (pytest) **when the project language is not python/mixed**, so the
  akmon-dev validator and any future deps-bearing tool can run on a non-Python project. The
  venv lives outside the submodule, is gitignored (§D), and is never needed for the stdlib-only
  consumer CI checks. (C8)

### Changed
- **Sharper SessionStart role hint** — the active-agent reminder now carries the DEVELOP routing
  discriminator (decompose → review · construct → architect · realize → engineer) up front, when
  the project has dev agents, instead of a vague "pick the one the task calls for". The agent gets
  the picking rule at session start, not only after a code/planning edit. OPERATE-only projects
  keep the generic line. (A10)
- **Configurable dev-layer root** — `_aitna/` is now the *default*, not a hard-coded literal. A
  project may relocate the dev layer by declaring **`AITNA_ROOT`** (a project-root-relative path,
  e.g. `tools/ai`); akmon then mounts at `<AITNA_ROOT>/akmon` and `sync.py` / `verify.py` /
  the hooks derive every path (generated pointers, hook commands, the do-not-edit banner) from it.
  Unset → `_aitna`, byte-identical to before. Documented in MODEL.md §2 + BOOTSTRAP §A. (A4)
- `verify.py` gains `check_akmon_gitignore` — warns when the akmon submodule has no
  `.gitignore` ignoring `__pycache__/` (so a release commit cut from the submodule stays clean).
- **USE/dev verify split** — `bin/verify.py` is now the **USE-contract verifier only**: it
  dropped the akmon-self layout/CI requirements and no longer references the dev layer at all.
  akmon-self checks moved to the new `meta/bin/validate.py`. Consumer CI is unchanged
  (`sync.py --check` + `verify.py --strict`). (C7)
- **Stricter USE-surface isolation** — the develop-boundary check became
  `check_use_surface_isolation`: it now scans the *whole* USE surface (incl. `skills/`, `tools/`)
  and fails on **any mention** of the dev layer — numbered `ADR ####` / `ROADMAP O#` citations and
  dev-tree paths in links *or* inline code — not just markdown links. Generic vocabulary ("file an
  ADR") stays legal. (C7)
- **Terminology** — the third axis is now consistently called **Archetype** (was "Project type")
  across `MODEL.md`, `ARCHETYPES.md`, `BOOTSTRAP.md`, `README.md`.

### Breaking
- **Dev layer renamed `develop/` → `meta/`.** akmon's own development artifacts (CONCEPT,
  decisions/ADRs, ROADMAP, design, reviews, tests, self_ci) now live under
  `_aitna/akmon/meta/`. The rename avoids colliding with the **DEVELOP** role/mode of the
  model. *Migration:* a consumer that hardcoded any `_aitna/akmon/develop/...` path (CI, docs,
  scripts) must repoint it to `meta/...`. CI that ran `develop/self_ci.py` / `pytest develop/tests`
  should drop them (those are akmon-self checks, run via `meta/bin/validate.py`, not a consumer
  concern). (C7)

## v0.1.0

First tagged release of the akmon standard — the initial reviewed baseline consuming projects
pin to. Everything below is the contract a new consumer adopts on first mount; there is no prior
version to migrate from, so the `Breaking` note applies only to projects that mounted a pre-tag
akmon and still carry old-style skill frontmatter.

### Added
- **`release` role** + [release pipeline](pipelines/release.md): a subject-parameterized DEVELOP
  role (package / akmon tag / pin bump) with a two-mode cycle (lightweight cut · periodic
  cadence). Locked in [ADR 0001](meta/decisions/0001-release-and-roles-model.md).
- **`learn` role** ([learn](roles/learn.md)): the learn loop now has an owning role wrapping the
  `memory-distill` + `learning` pipelines.
- **`decisions/`** — akmon now keeps its own ADRs (this is where standard-level decisions land,
  parallel to a project's `docs/dev/decisions/`).
- **`CHANGELOG.md`** (this file) and the `v0.x.y` versioning convention.
- **Skill contract** — `SKILL.md` frontmatter now requires `name` / `description` / `when_to_use`
  / `owner`, checked by `verify.py`.

### Changed
- `verify.py` is stricter: validates the cross-agent pointer contract (vendor pointers import
  `AGENTS.md`; AGENTS.md stays hand-reviewed, not generated) and the skill contract above.
- `sync.py` now prunes orphaned banner-marked generated skill stubs; `verify.py` flags them.
- CI runs the akmon self-CI fixture (`bin/self_ci.py`) alongside sync/verify/pytest.

### Breaking
- **Skill frontmatter** — consuming projects with existing `skills/*/SKILL.md` must add the
  `when_to_use` and `owner` fields (and ensure `name` matches the skill directory), or
  `verify.py --strict` will fail. Migration: add the two fields to each skill's frontmatter.
