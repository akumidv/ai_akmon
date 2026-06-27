# Pipeline: code-flow

The cycle the [engineer](../roles/engineer.md) role follows to turn a task into committed
code with tests, proven to do what it claims.

> A pipeline is a **declarative, ordered cycle** — the steps and their gates, not a script.

## When

Every executable change: production code, tests, build config, or development tooling
(hooks, sync scripts, validators, local tools). This includes implementing a design from
[design-flow](design-flow.md), a bug fix, or a behaviour-preserving refactor. A change
that needs a *design decision* goes back to design-flow first — code-flow implements, it
does not decide architecture or process contracts.

## Steps

1. **Take** — pick a task from `_forge/TASKS.md`; confirm its goal and the design it
   implements. If the design has a gap, return it to the [architect](../roles/architect.md)
   role as a task — do not improvise load-bearing structure.
   - **A load-bearing decision that *emerges mid-build* is the same gate, in reverse.** When,
     while coding, you find yourself *deciding* structure (not just applying it) — a new
     convention, an interface reshape, a contract change — **pause**: switch back to
     `architect`, run the relevant [design-flow](design-flow.md) steps (Design → **Record** →
     Align), and only then resume code-flow. **The record precedes the code that embodies the
     decision** — never decide-and-code first and document after. (The forward seam is the
     [hand-off gate](../roles/README.md#switching-from-design-to-build--the-hand-off-gate); this
     is its mid-build mirror.)
2. **Implement** — write the change. **Reuse** existing abstractions and keystone
   `tools/` rather than duplicating logic or writing ad-hoc scripts. Match the
   surrounding code's naming, idiom, and comment density; for executable dev tooling, keep
   it stdlib-only unless the project explicitly accepts a dependency.
   - **Rolling out a cross-cutting convention is three separate moves, not one:** first a
     **read-only audit** that lists the discrepancies (no edits); then **record the rule**
     (design-flow — so the convention is on the record before any code embodies it); then the
     **mechanical flips as their own tracked task** in `_forge/TASKS.md`, separate from the
     rule. Do not mix the sweep into the change that introduces the rule (keeps each diff
     reviewable and the rule decided before the churn). A wide rename/reshape always lands as
     its own task.
3. **Test** — add or extend tests. A behaviour change without a test is **incomplete**.
   Tests mirror the source layout.
4. **Pre-commit** *(gate)* — run the [pre-commit](pre-commit.md) cycle. Tests are
   mandatory; **no commit on red**.
5. **Verify** *(gate)* — for any change to **math, DataFrame/data shape, or
   architecture**, explain it and obtain **owner verification**. Green tests are
   necessary, not sufficient.
6. **Close** — mark the task done in `_forge/TASKS.md` *only after* owner verification.
   Capture any reusable insight to `_forge/memory/` (feeds the learn loop).

## Gates (must hold to advance)

- **Before commit (Pre-commit):** tests pass; lint/type checks green.
- **Before Done (Verify):** math/data/architecture changes are owner-verified.
- **At Close:** task marked done; reusable insight recorded.

## Done

The task's goal is implemented and matches the agreed design; tests cover it and pass;
pre-commit is green; math/data/architecture changes are owner-verified; the task is
marked done and any reusable insight is captured.
