# Pipeline: release

The cycle the [release](../roles/release.md) role follows to cut a release for one **subject** —
keystone itself, a consuming project's package, or a keystone pin bump inside a consuming project.

> A pipeline is a **declarative, ordered cycle** — the steps and their gates, not a script.
> Release tooling defaults to **propose/prepare**: it may print commands, validate state, or draft
> files, but the owner runs the landing actions (D5).

## When

When accepted work has accumulated for a subject and the owner wants to publish a reviewed state —
or to bump a keystone pin. **Not** every commit. Pick the mode:

- **lightweight cut** (default) — the everyday path; steps 1–4, 8–11.
- **periodic cadence** (deliberate, not every tag) — the lightweight cut **plus** the sweeps
  (steps 5–7) and post-release learning (step 12). Run on a cadence or when drift is suspected.

## Steps (a loop with gates; the mode selects which run)

1. **Frame the subject** *(gate)* — select exactly one subject (package / keystone tag / pin bump)
   and, when ambiguous, the target consumers. Everything downstream is relative to this choice.
2. **Collect state** — read `TASKS.md`, `TASKS_ARCHIVE.md`, relevant design/ADRs, requirements,
   the memory index, skills/tools, CI config, and current `git status`.
3. **Classify changes** — group closed work since the last release into impact classes:
   `internal` · `consumer-visible` · `migration` · `breaking`.
4. **Owner gates** *(gate)* — confirm version class (`v0.x.y`: bump `x` only for a breaking change
   to layout / required files / a role-pipeline contract), breaking-change handling, migration
   notes, deferrals, and which downstream projects to update.
5. **Hygiene sweep** *(cadence — route, don't fix)* — file tasks for stale backlog/orphaned
   generated files/stale memory/missing skill contracts/obsolete tools/missing pointers. The
   owning role fixes them; `release` only files.
6. **Learning sweep** *(cadence — hand off to [learn](../roles/learn.md))* — invoke the `learn`
   role to run the learn loop. `release` does not promote memory itself; candidates become `learn`
   tasks.
7. **Architecture / guardrail sweep** *(cadence — route, don't fix)* — triage requirement/ADR
   drift, role declarations, D#/R# compliance, secrets policy, generated-pointer drift, CI
   coverage; mismatches become architect/engineer tasks.
8. **Prepare release artifacts** — update release notes / `CHANGELOG.md` (`Unreleased` → the new
   version) and downstream bump notes. The archive stays traceability, not release prose.
9. **Verify** — run the subject's release check set via the release tool's `--check`
   (runner-resilient: it picks an available test runner).
10. **Owner handoff** *(gate, D5)* — present exact commit/tag/publish/pin-bump commands and the
    residual risk. **Stop.** The owner runs the landing commands.
11. **Propagate** — for each selected consumer: prepare the owner-run pin/version bump plan,
    then run local sync + verify only after the owner-approved workspace changes exist; record
    the bump **in the consuming project** and hand off owner-owned landing actions.
12. **Post-release learning** *(cadence)* — capture release friction into memory/tasks via
    [learn](../roles/learn.md); promote only through explicit tasks.

## Gates (no step past these without the owner)

- **Frame** — the subject is fixed before anything is read against it.
- **Owner gates** — version class, breaking changes, migration, deferrals, consumers.
- **Owner handoff** — every commit/tag/publish/pin-bump is owner-executed (D5). `release` prepares
  the exact commands; it never runs them.

## Anti-super-role

`release` **coordinates, it does not implement.** Every sweep finding is routed to
the owning role — architecture/ADR → [architect](../roles/architect.md), code/tooling →
[engineer](../roles/engineer.md), memory/promotion → [learn](../roles/learn.md) — and `release`
edits only release artifacts (release notes, changelog, bump records, release plan files). It never
edits ADRs, production code, or `_forge/memory/` in-cycle.

## Done

The subject's reviewed state is classified, its release notes current, its verification green, and
the owner holds an exact, ready-to-run landing command set; selected consumers have a bump plan.
Nothing was committed, tagged, published, or bumped by the role itself.
