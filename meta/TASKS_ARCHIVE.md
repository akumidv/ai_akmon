# Archived tasks — keystone

Completed keystone work, one terse line each. Format: [`pipelines/tasks.md`](../pipelines/tasks.md).
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
- A5 · review role + review-flow pipeline · done · roles/review.md + pipelines/review-flow.md; analysis (decompose→measure→report), criteria as hand-off · [ADR 0003](decisions/0003-role-triad-and-develop-use-separation.md)
- A6 · narrow architect to synthesis; engineer escalation; roles/README routing · done · triad + discriminator + "why separate mode" in role docs · [ADR 0003](decisions/0003-role-triad-and-develop-use-separation.md)
- A7 · review task-id letter `N` · done · pipelines/tasks.md table + ADR 0002 amendment + interim memory note · [ADR 0003](decisions/0003-role-triad-and-develop-use-separation.md)
- A8 · README→develop/CONCEPT + thin USE MODEL.md · done · vision out of consumer USE context; AGENTS.md retargeted; thin root README bridge · [ADR 0003](decisions/0003-role-triad-and-develop-use-separation.md)
- A9 · decouple USE docs from develop artifacts · done · 11 ADR/ROADMAP citations stripped; USE→MODEL repointed; boundary check green · [ADR 0003](decisions/0003-role-triad-and-develop-use-separation.md)
- C3 · create develop/, move dev artifacts · done · decisions/design/ROADMAP/TASKS/tests/self_ci/CONCEPT cordoned; all links fixed · [ADR 0003](decisions/0003-role-triad-and-develop-use-separation.md)
- C4 · verify.py develop-boundary check + path updates · done · forbids USE→develop links; tooling paths + fixtures updated; self_ci + 96 tests green · [ADR 0003](decisions/0003-role-triad-and-develop-use-separation.md)
- C5 · triad-aware role hooks · done · review/architect/engineer nudges in role-on-code + analysis-guard; per-direction markers; `OPERATE` label fixed · [ADR 0003](decisions/0003-role-triad-and-develop-use-separation.md)
- C7 · develop→meta rename + USE/dev verify split · done · folder `develop/`→`meta/`; `bin/verify.py` USE-only; new `meta/bin/validate.py` runs dev-layer self-checks + self_ci + tests; strict USE-surface isolation (no `meta/` path, no numbered-ADR/ROADMAP/dev-path/bare-name citations); ADR 0003 §5–§6a + CHANGELOG; 102 tests green · [ADR 0003](decisions/0003-role-triad-and-develop-use-separation.md)
- C8 · BOOTSTRAP: dev-layer venv on non-Python projects · done · attach step 5 provisions `_forge/.venv` (uv-first, caveated stdlib fallback) + installs pytest when language≠python/mixed; §D gitignores it; validate.py docstring points at it; CHANGELOG Unreleased
- A4 · `_forge/` path is configurable, not fixed · done · `FORGE_ROOT` env (default `_forge`) configures the dev-layer root; sync.py/verify.py/hook_core derive every path (pointers, hook commands, banner, classifiers) from it; MODEL.md §2 + BOOTSTRAP §A; +13 tests
- A10 · SessionStart discriminator routing-hint · done · session hint carries the DEVELOP discriminator (decompose→review · construct→architect · realize→engineer) up front when dev agents exist; OPERATE-only keeps generic line; +2 tests · [ADR 0003](decisions/0003-role-triad-and-develop-use-separation.md)
