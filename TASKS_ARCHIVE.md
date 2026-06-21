# Archived tasks — keystone

Completed keystone work, one terse line each. Format: [`pipelines/tasks.md`](pipelines/tasks.md).
Active backlog: [`TASKS.md`](TASKS.md).

## Done

- T0 · tooling test coverage · done · engineer · `tests/` for `hook_core`/`sync`/`verify`; +sync drops stale hook entries on rename; +session-start logs swallowed errors to stderr
- T1 · cross-agent contract · done · architect · AGENTS.md remains hand-reviewed source; verify checks vendor pointers/imports and source skill-root linkage
- T2 · skill contract (minimal) · done · architect · `name/description/when_to_use/owner` frontmatter + verify check
- T5 · audit attached project (alphavar) for drift · done · architect · `sync --check` + `verify --strict` pass
- T7 · prune orphaned generated files · done · engineer · sync deletes stale banner-marked stubs; verify flags them
- T8 · keystone self-CI · done · engineer · own `tests/` + fixture `verify --strict` run in CI
- T3 · release/versioning standard · done · architect · design consolidated + locked in ADR 0001; resolves ROADMAP O2; impl phased T10–T15
- T10 · extract `learn` role · done · architect · roles/learn.md + README row; learning/memory-distill pipelines wired to the role
- T11 · `release` role + pipeline · done · architect · roles/release.md + pipelines/release.md (lightweight cut vs cadence, subject gate, anti-super-role routing)
- T12 · versioning + CHANGELOG · done · architect · v0.x.y convention + CHANGELOG.md (Unreleased); BOOTSTRAP pull-bump references release notes + downstream record
- T13 · verify CHANGELOG Unreleased warn · done · engineer · verify.check_changelog warns when CHANGELOG lacks `Unreleased`; +3 tests
- T15 · subject-relativity in layer model · done · architect · README §2: DEVELOP/USAGE/OPERATE relative to a subject; USAGE-vs-OPERATE by consequence
- T14 · release skill/tool (propose/prepare) · done · engineer · skills/release/SKILL.md + tools/release/release_check.py (--state/--check/--plan, --subject keystone|package, runner-resilient, never executes); +verify check_keystone_gitignore; pin-bump split to T18
