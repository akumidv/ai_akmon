# Pipeline: pre-commit

The mandatory cycle before any commit. Referenced by [code-flow](code-flow.md) and bound
on every project regardless of role.

> This is a **gate**, not advice. If a step fails, the commit does not happen — fix first.

## Steps (in order)

1. **Tests** — run the project's test suite. **No commit on red.** A behaviour change
   must come with a test that covers it.
2. **Lint / format** — run the project's linter and formatter (see the language
   [guardrails/](../guardrails/) for the stack's tools).
3. **Types** — run the type checker if the language has one.
4. **Docs in sync** — if code or behaviour changed, update the doc that **owns** the
   affected fact (API, env vars, package layout, requirements). Never leave docs stale
   after a code change.
5. **D2 ledger** *(advisory — warn-first, not a blocking gate)* — when the project tracks
   owner-verification points, run
   `python3 _aitna/akmon/tools/d2_ledger/d2_ledger.py check --ledger _aitna/D2_LEDGER.md --changed $(git diff --cached --name-only)`.
   It **warns** (never blocks) when the staged diff touches a D2-sensitive path
   (`[d2_ledger] sensitive_paths` in `_aitna/.akmon.toml`) while the ledger still holds
   `pending` entries — a prompt to log or close the verify point before the owner commits, so
   Verify stops being skippable by momentum. Advisory until the fill-habit holds, then promoted
   to red with `--strict`. A *forgotten* entry (sensitive edit never logged) is
   caught earlier, per-edit, by the reminder hook — this step covers open `pending` points.
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

The concrete commands (test runner, linter, type checker) come from the language
[guardrails/](../guardrails/) and, where a project differs, from its `AGENTS.md`. This
pipeline defines the **gate**; the project supplies the **commands**.

## Done

All steps pass; docs that own changed facts are updated; generated pointers have no drift;
akmon verify is clean; no secrets are in the diff. Only then is the change ready for
the owner to commit.
