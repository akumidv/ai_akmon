# Pipeline: pre-commit

The mandatory cycle before any commit. Referenced by [code-flow](code-flow.md) and bound
on every project regardless of role.

> This is a **gate**, not advice. If a step fails, the commit does not happen — fix first.

## Steps (in order)

1. **Tests** — run the project's test suite. **No commit on red.** A behaviour change
   must come with a test that covers it.
2. **Lint / format** — `akmon check --changed` (mounted:
   `python3 _aitna/akmon/bin/check.py --changed`) runs the checks the project declares under
   `[check]` in `.akmon.toml` — its own linter and type checker, or ruff with akmon's rules
   ([profiles/](../profiles/)) — on the changed files. A failing check stops the commit; a
   project that declares none runs its linter and formatter directly.
3. **Types** — run the type checker if the language has one.
4. **Docs in sync** — if code or behaviour changed, update the doc that **owns** the
   affected fact (API, env vars, package layout, requirements). Never leave docs stale
   after a code change.
5. **Decision and evidence continuity** — significant choices in the diff have an accepted
   thematic ADR block; the task links its implementation evidence and any remaining work.
   An unaccepted material delta returns to design-flow before implementation proceeds.
   A correction within an accepted contract needs no new ADR. Do not ask the owner to
   accept unchanged intent again or create a post-commit SHA/approval bookkeeping step.
   This is a semantic review of the changed scope, not a replacement ledger command.
6. **Generated pointers in sync** — run `python3 _aitna/akmon/bin/sync.py --check`
   when the project uses akmon. If it reports drift, run `python3 _aitna/akmon/bin/sync.py`,
   review the generated files, and include the deterministic pointers in the owner's commit.
7. **Keystone verify** — run `python3 _aitna/akmon/bin/verify.py --strict` to validate
   AGENTS anchors, generated pointers, hooks, skills, memory, secrets ignore rules, and
   CI/preflight wiring.
8. **Secrets check** — no real key/token/credential in the diff (code, config, fixtures,
   markdown). Config comes from `.env` only; `*.env.example` carries empty placeholders.
9. **Scope check** — the diff contains only what the task needs; no stray files, no
   generated artifacts that should be gitignored.

## Hard rules

- **Tests are mandatory and must pass.** This is the non-negotiable gate.
- **Never `git add` / `commit` on the owner's behalf** unless explicitly told — the owner
  stages and commits.
- **Owner-verify** math / DataFrame / architecture changes (per the role's Verify step) —
  this gate is in addition to that, not a replacement.

## Per-project specifics

The concrete commands (test runner, linter, type checker) come from the project's `AGENTS.md`
and its language profile in [profiles/](../profiles/). This pipeline defines the **gate**;
the project supplies the **commands**.

## Done

All steps pass; docs that own changed facts are updated; generated pointers have no drift;
akmon verify is clean; no secrets are in the diff. Only then is the change ready for
the owner to commit.
