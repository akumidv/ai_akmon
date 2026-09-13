# 0014 — Code rules: principles, one checked catalog, language and environment profiles

- **Status:** Proposed — owner decisions taken (this session); **D2-48** Pending.
- **Owner:** akuminov@gmail.com
- **References:** [design `code-rules-and-profiles`](../design/code-rules-and-profiles.md) (the
  full classification, schema and slices) ·
  [C89 baseline](../reviews/c89-python-rule-baseline-20260913.md) ·
  [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html) ·
  [ADR 0009](0009-packaging-package-carrier-and-mount-modes.md) (package mode, the materialized
  guardrails) · tasks [C89, C91](../TASKS.md), C83 (the one integration-record reader) · ledger
  row D2-48.

## Context

akmon ships its code rules as prose: a common guardrail with no design principles and a Python
guardrail that names uv, ruff and pytest as the consumer's toolchain. Nothing enforces the prose
on a consumer, and akmon's own ruff selects six groups. The owner's direction: adopt the Google
Python Style Guide; akmon itself runs ruff strictly; a consumer gets the key rules, may switch
any off or change a parameter in `.akmon.toml`, and is checked by akmon's own check — never by a
linter akmon imposes, since ruff and uv are akmon's development dependencies only. Each rule goes
where it can be enforced: a principle to the common guardrail, a checkable rule to a checker,
the rest to a profile of a language or an environment.

## Decision

1. **The placement rule.** A rule a program can decide from the source alone, with few false
   positives, is **checked** and never restated as prose; a principle that holds in any language
   goes to `guardrails/_common.md` § Code design; anything else goes to the profile of its
   language or environment. Layout — line length, whitespace, import order — is the
   formatter's: recorded for akmon's own ruff, never re-implemented by the consumer check.
2. **Profiles of three kinds.** *Language* (`python`) and *environment* (`python-stdlib`, code
   that runs on a bare interpreter) profiles attach automatically and reach the agent as
   `@`-imports; *domain* profiles (`quant`) stay opt-in links. `guardrails/python.md` moves to
   `profiles/python.md`; `guardrails/` keeps the universal floor. Package mode materializes an
   imported profile as it does a guardrail. A consumer still importing the old path gets a `sync`
   plan error naming the replacement line.
3. **One catalog.** `profiles/python.rules.toml` is the one owner of every checked rule's text,
   Google section, ruff codes, consumer default severity (`error` · `warn` · `off`), test-module
   default and parameters. Its readers: akmon's consumer check; akmon's own `pyproject.toml`,
   held to it by a carrier; the profile prose, which cites rule ids; and, on request, a printed
   ruff fragment for a consumer that also runs ruff — printed, never written.
4. **`akmon check`, a separate command.** stdlib only (`ast`, `tokenize`); tracked `*.py` minus
   `<AITNA_ROOT>/` and `[python].exclude`; `--changed` for the pre-commit step, `--all` for the
   tree. Configuration is `[python]` in `<AITNA_ROOT>/.akmon.toml`, read through
   `common/record.py` with a new strict entry point and validated strictly — an unknown rule id,
   parameter or type is an error. A line is suppressed by `# akmon: ignore[rule-id] <reason>` or
   by a `# noqa` naming a mapped code. Exit 1 on an `error` finding (any finding under
   `--strict`). `verify` validates only the `[python]` table, so a bump never fails CI on code
   it did not touch.
5. **akmon's own configuration.** The strict ruff set with `D` (`convention = "google"`), `BLE`
   and every catalog code, at line length 120 — a recorded override of Google's 80 — plus
   `akmon check` on itself as a `self_ci` leg for the rules ruff has no code for. The size family
   — complexity, branches, arguments, returns, statements, function length — is **C91**, a
   ratchet whose per-file exception list only shrinks.

## Consequences

- A consumer edits one import line on its next bump; the plan error names it.
- akmon maintains its own implementation of rules ruff also implements; the two can disagree on
  an edge. Fixtures per rule and the `pyproject.toml` ↔ catalog carrier bound that, not remove it.
- The check parses with the interpreter that runs it: a file whose syntax is newer is reported as
  `parse-error`, not checked.
- The key-list defaults rest on one consumer, where every `error` rule measured zero; a consumer
  that never ran a linter may meet many more findings, all switchable in `.akmon.toml`.
- **Rejected:** keeping `guardrails/python.md` as the language file (two meanings for one
  directory); a one-release alias for the old path; the check inside `verify --strict`; an
  advisory-only check; a ruff baseline a consumer must `extend`; uv or any package manager as a
  consumer requirement; the size family in the same change; Google's 80 or 100 for akmon.
