# Guardrails: common (all languages)

Hard rules that bind **every** agent on **every** project, regardless of language or role.
Applied automatically (not opt-in). Language-specific rules layer on top — see
[python.md](python.md) etc.

> Guardrails are **constraints**, not guidance: they say what must always / never happen.
> Pipelines say *how* to work; profiles add *domain* rules; guardrails are the floor.

## Secrets

- **Config via environment only.** Never hardcode a secret, key, token, or credential.
- **Never in the repo.** No real secret in code, config, fixtures, docs, or a commit.
  Secrets come from `.env` (gitignored); `*.env.example` carries empty placeholders.
- A secret in a diff fails [pre-commit](../pipelines/pre-commit.md).

## Commits & ownership

- **Never `git add` / `commit` / `push` on the owner's behalf** unless explicitly told.
  The owner stages and commits.
- **Tests pass before a commit is offered.** No commit on red (see
  [pre-commit](../pipelines/pre-commit.md)).
- Branch for non-trivial work; do not commit straight to the default branch unless asked.

## Verify against reality, not memory

- Confirm names, signatures, enums, env-var names, and file paths **in the code/docs**
  before relying on or documenting them — they drift.
- **Owner-verify** any change to math, data shape, or architecture. Passing tests and
  plausibility are necessary, not sufficient.

## Documentation hygiene

- **One owner per fact.** Before adding a table / flow / list, check whether another doc
  owns it; if so, link instead of duplicating. Update the owner when the fact changes.
- **No advisory / dev-history files in the live tree.** Point-in-time reviews are archived
  with a banner; decisions become ADRs; git history is the changelog.
- **Keep the entry point single.** `AGENTS.md` is the source of truth; vendor files
  (`CLAUDE.md`, `.github/copilot-instructions.md`, …) stay thin pointers.

## Reuse over re-implementation

- Use existing project code, keystone `tools/`, and shared skills before writing new code.
- Put repeatable mechanics into a **tool**, not an ad-hoc script.
- Match the surrounding code's conventions (naming, idiom, comment density).

## Scope discipline

- Change only what the task needs; no stray edits, no unrelated refactors riding along.
- A material design gap goes back to the [architect](../roles/architect.md) role — do not
  improvise load-bearing architecture inside a code task.
