---
name: release
description: Conduct a keystone-or-project release as the release role — frame the subject, collect state, classify impact, gate with the owner, verify, and hand off owner-run commands (never execute them).
when_to_use: When the owner wants to cut a release for a subject (a project package, the keystone tag, or a keystone pin bump) or bump a keystone pin in a consuming project.
owner: keystone
---

# release

The procedural skill for the [`release`](../../roles/release.md) role. It teaches *how to
run the release conversation* and *when to stop* (the D5 boundary). The pipeline of record
is [`pipelines/release.md`](../../pipelines/release.md); this skill is the agent-facing
how-to, and it drives the [`tools/release/release_check.py`](../../tools/release/release_check.py)
tool for the mechanical parts (state collection, the verify suite, the owner command plan).
A skill *calls* a tool ([MODEL.md](../../MODEL.md)); the tool is a SHARED dev tool, not a
CI gate — releases are owner-driven, so nothing here is wired into CI.

> **Propose / prepare, never execute (D5).** The release role *prepares* every
> commit / tag / push / publish / pin-bump command and **stops**; the owner runs them.
> The tool defaults to read-only and dry-run for exactly this reason.

## The unit of release: one subject, classified, verified, handed off

A release is cut for **exactly one subject**:

1. **the subject** — a project's **package**, **keystone** (its tag), or a **keystone pin
   bump** recorded inside a consuming project. Fix it *first*; everything downstream is
   relative to this choice.
2. **the impact** — closed work since the last release, grouped into
   `internal` · `consumer-visible` · `migration` · `breaking`.
3. **the handoff** — an exact, owner-ready command set plus the residual risk.

## Steps (the lightweight cut — steps 1–4, 8–11 of the pipeline)

Run the periodic-cadence sweeps (5–7, 12) only deliberately; they **route** findings to
architect / engineer / [`learn`](../../roles/learn.md), they do not fix them here.

1. **Frame the subject** *(gate)*. Ask the owner which subject and, when ambiguous, which
   downstream consumers. Do not read anything against the release until this is fixed.
2. **Collect state.** Run `python3 _forge/keystone/tools/release/release_check.py --state` to read
   `TASKS.md`, `TASKS_ARCHIVE.md`, `CHANGELOG.md`, and `git status` in one pass. Read the
   relevant design/ADRs by hand when the summary points at them.
3. **Classify changes** into the four impact classes. Every `consumer-visible` /
   `migration` / `breaking` change needs a `CHANGELOG.md` line; `breaking` also needs
   explicit owner confirmation before the tag. Write each `breaking`/`migration` line as a
   **verifiable** checklist item — name the file/path/contract that moved — because a consumer's
   bump procedure (BOOTSTRAP "Pull the latest shared layer") walks them as re-attach checks.
4. **Owner gates** *(gate)*. Confirm: version class (`v0.x.y` — bump `x` only for a
   breaking change to layout / required files / a role-pipeline contract; `y` otherwise),
   breaking-change handling, migration notes, deferrals, and which consumers to update.
8. **Prepare release artifacts.** Move `CHANGELOG.md` `Unreleased` → the new version
   heading; keep an empty `Unreleased` so the verify warn stays satisfied. This is the
   **only** file the release role edits — route everything else to its owning role.
9. **Verify.** Run `python3 _forge/keystone/tools/release/release_check.py --check`. It runs the
   subject's release suite (pointer sync, contract verify, and the subject's own checks + tests)
   and is resilient to the test runner (`uv` → project `.venv` → system `pytest`). All green
   before handoff.
10. **Owner handoff** *(gate, D5)*. Run
    `python3 _forge/keystone/tools/release/release_check.py --plan vX.Y.Z` to print the exact
    owner-run command set, then present it with the residual risk and **stop**. The owner
    runs the landing commands.
11. **Propagate** *(only if the owner selected consumers)*. Prepare the per-consumer
    pin/version bump plan; the bump record lives in the **consuming** project, never in
    keystone's release notes. Skip entirely when the subject is keystone-only.

## How to apply it

- **Subject relativity.** Releasing keystone (DEVELOP relative to keystone) does **not**
  imply touching a consuming project. If the owner says "keystone only", do not prepare any
  consumer-side change — propagation (step 11) is skipped.
- **Staged vs committed.** Before printing the tag command, confirm the release work is in
  a **commit**, not just staged — a tag points at a commit. The plan uses explicit
  `git add <file>` (never `git add -A`) so untracked noise (e.g. `__pycache__/`) is not
  swept in.
- **Routing, not doing.** A finding that is not a release artifact becomes a task for the
  owning role — architecture/ADR → architect, code/tooling → engineer, memory/promotion →
  learn. The release role edits only release notes / changelog / bump records / plan files.

## Tool contract — `tools/release/release_check.py`

Subject-parameterized via `--subject {keystone,package}` (default `keystone`); the third
subject — a keystone **pin bump** — is deferred (backlog T18).

| Mode | Does | Writes? |
|---|---|---|
| `--state` | summarize the subject's TASKS / TASKS_ARCHIVE / CHANGELOG / `git status` | no |
| `--check` *(default)* | run the subject's release suite, runner-resilient | no |
| `--plan vX.Y.Z` | print the exact owner-run commit/tag/push command set | no |

- **`--subject keystone`** runs the keystone suite (pointer sync, contract verify, and
  keystone's own self-checks + tests); the plan tags from the submodule tree.
- **`--subject package`** runs the keystone contract check (`verify --strict`) and then
  **defers to the project's own commands** in [`_forge/agents/release/README.md`](../../../agents/release/README.md)
  (tests / lint / build) — it does not guess them. The plan tags from the project root.

The tool never runs `git commit` / `git tag` / `git push` / publish / pin-bump. It prints;
the owner executes (D5).
