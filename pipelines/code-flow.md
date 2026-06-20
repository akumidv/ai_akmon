# Pipeline: code-flow

The cycle the [engineer](../roles/engineer.md) role follows to turn a task into committed
code with tests, proven to do what it claims.

> A pipeline is a **declarative, ordered cycle** — the steps and their gates, not a script.

## When

Every code change: implementing a design from [design-flow](design-flow.md), a bug fix,
or a behaviour-preserving refactor. A change that needs a *design decision* goes back to
design-flow first — code-flow implements, it does not decide architecture.

## Steps

1. **Take** — pick a task from `_forge/TASKS.md`; confirm its goal and the design it
   implements. If the design has a gap, return it to the [architect](../roles/architect.md)
   role as a task — do not improvise load-bearing structure.
2. **Implement** — write the change. **Reuse** existing abstractions and keystone
   `tools/` rather than duplicating logic or writing ad-hoc scripts. Match the
   surrounding code's naming, idiom, and comment density.
3. **Test** — add or extend tests. A behaviour change without a test is **incomplete**.
   Tests mirror the source layout.
4. **Pre-commit** *(gate)* — run the [pre-commit](pre-commit.md) cycle. Tests are
   mandatory; **no commit on red**.
5. **Verify** *(gate)* — for any change to **math, DataFrame/data shape, or
   architecture**, explain it and obtain **owner verification**. Green tests are
   necessary, not sufficient.
6. **Close** — mark the task done in `_forge/TASKS.md` *only after* owner verification.
   Capture any reusable insight to `_forge/memory/` (feeds the [learn loop](../README.md#3a-the-learn-loop--how-the-keystone-evolves-through-use)).

## Gates (must hold to advance)

- **Before commit (Pre-commit):** tests pass; lint/type checks green.
- **Before Done (Verify):** math/data/architecture changes are owner-verified.
- **At Close:** task marked done; reusable insight recorded.

## Done

The task's goal is implemented and matches the agreed design; tests cover it and pass;
pre-commit is green; math/data/architecture changes are owner-verified; the task is
marked done and any reusable insight is captured.
