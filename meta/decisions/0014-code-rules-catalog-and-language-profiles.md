# 0014 — Code rules: principles, a standard ruff configuration, language and environment profiles

- **Status:** Proposed — owner decisions taken (this session, two rounds); **D2-48** Pending.
- **Owner:** akuminov@gmail.com
- **References:** [design `code-rules-and-profiles`](../design/code-rules-and-profiles.md) (the
  full classification and slices) ·
  [C89 baseline](../reviews/c89-python-rule-baseline-20260913.md) ·
  [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html) ·
  [ADR 0009](0009-packaging-package-carrier-and-mount-modes.md) (package mode, the materialized
  guardrails) · tasks [C89, C91](../TASKS.md), C83 (the one integration-record reader) · ledger
  row D2-48.

## Context

akmon shipped its code rules as prose: a common guardrail with no design principles and a Python
guardrail that named uv, ruff and pytest as the consumer's toolchain. Nothing enforced the prose,
and akmon's own ruff selected six groups. The owner's direction: adopt the Google Python Style
Guide; akmon itself runs ruff strictly; each rule goes where it can be enforced — a principle to
the common guardrail, a checkable rule to a checker, the rest to a profile of a language or an
environment. And, in a second round, after a first design had akmon check consumer code with an
AST checker of its own configured in `.akmon.toml`: **no reinvented linter.** A project's rules
and style are its own; akmon runs the project's linter with the project's settings, or — when the
project has none — offers ruff with akmon's rules, set up the standard way; akmon's rules live in
a standard ruff configuration that runs without akmon too.

## Decision

1. **The placement rule.** A rule a standard linter can check lives in that linter's
   configuration and is never restated as prose; a principle that holds in any language goes to
   `guardrails/_common.md` § Code design; anything else goes to the profile of its language or
   environment. A Google rule no linter covers is profile prose and a review point.
2. **Profiles of three kinds.** *Language* (`python`) and *environment* (`python-stdlib`, code
   that runs on a bare interpreter) profiles attach automatically and reach the agent as
   `@`-imports; *domain* profiles (`quant`) stay opt-in links. `guardrails/python.md` moves to
   `profiles/python.md`; `guardrails/` keeps the universal floor. A consumer still importing the
   old path gets a `sync` plan error naming the replacement line, in every mount mode.
3. **akmon's Python rules are a standard ruff configuration** — `profiles/ruff.toml`, each group
   annotated with its Google section, with no `target-version` so ruff takes the project's
   `requires-python`. It runs as `ruff check --config <file>` or through `extend` from a
   project's own ruff configuration; a project adjusts it there (`extend-ignore`,
   `per-file-ignores`), never in akmon's file. In package mode `sync` materializes an extended
   rules file at `<AITNA_ROOT>/.akmon/profiles/ruff.toml`, as it does an imported profile.
4. **`akmon check` runs the checks a project declares** — named commands under `[check]` in
   `<AITNA_ROOT>/.akmon.toml`, read through `common/record.py`'s strict entry point. `{files}`
   becomes the files a run covers: the project, or under `--changed` the changed files matching
   the check's patterns. Each command's output passes through untouched and its result is one
   finding; exit 1 when one fails or cannot run. akmon checks no code itself. `verify` validates
   only the table, so a bump never fails CI on code it did not touch; the pre-commit step runs
   `akmon check --changed`.
5. **`init` decides once what `akmon check` runs.** It detects the project's ruff, flake8, pylint
   and mypy configuration and records those commands through the project's environment manager
   (the default when any is found); when none is, it offers ruff with akmon's rules — a standard
   `extend` added to the project's `pyproject.toml` or `ruff.toml` (the default then); or nothing.
   It asks when it can, `--checks own|akmon|none` decides without asking, and a realign never
   changes a recorded `[check]`.
6. **akmon's own configuration** extends the same `profiles/ruff.toml`, at line length 120 — a
   recorded override of Google's 80. The size family — complexity, branches, arguments, returns,
   statements — is **C91**, a ratchet whose per-file exception list only shrinks.

## Consequences

- A consumer edits one import line on its next bump; the plan error names it.
- On the `akmon` choice `init` writes one `extend` into the project's ruff configuration — never
  over an `extend` the project chose — and the project must install ruff; `init` names the
  command. Nothing is written on the `own` or `none` choice.
- The Google rules no ruff code covers — one `for` per comprehension, no `@staticmethod`,
  function length in lines, the TODO link form, standard-library-only code — are review points,
  not checks.
- An external command's output is not in the findings envelope; only its result is.
- **Rejected:** an AST checker of akmon's own with per-rule configuration in `.akmon.toml` (built
  and measured in the first round, then withdrawn: a second implementation of rules ruff already
  has, which disagreed with ruff on its first real run); printing a ruff fragment instead of
  shipping a configuration; keeping `guardrails/python.md` as the language file; a one-release
  alias for the old path; the check inside `verify --strict`; parsing each linter's output into
  findings; uv or any package manager as a consumer requirement; the size family in the same
  change; Google's 80 or 100 for akmon.
