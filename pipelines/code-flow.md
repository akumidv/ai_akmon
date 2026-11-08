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

1. **Take** — pick a task from `_aitna/TASKS.md`; confirm its goal, applicable accepted
   decision blocks, and the evidence needed to establish conformance. Restore settled
   rationale without asking for acceptance again. If the design has a gap, return it to
   the [architect](../roles/architect.md) role as a task — do not improvise load-bearing structure.
   - **A load-bearing decision that *emerges mid-build* is the same gate, in reverse.** When,
     while coding, you find yourself *deciding* structure (not just applying it) — a new
     convention, an interface reshape, a contract change — **pause**: switch back to
     `architect`, run the relevant [design-flow](design-flow.md) steps (Design → **Record** →
     Align), and only then resume code-flow. **The record precedes the code that embodies the
     decision** — never decide-and-code first and document after. (The forward seam is the
     [hand-off gate](../roles/README.md#switching-from-design-to-build--the-hand-off-gate); this
     is its mid-build mirror.)
2. **Implement** — write the change. **Reuse** existing abstractions and akmon
   `tools/` rather than duplicating logic or writing ad-hoc scripts. Match the
   surrounding code's naming, idiom, and comment density; for executable dev tooling, keep
   it stdlib-only unless the project explicitly accepts a dependency.
   - **Rolling out a cross-cutting convention is three separate moves, not one:** first a
     **read-only audit** that lists the discrepancies (no edits); then **record the rule**
     (design-flow — so the convention is on the record before any code embodies it); then the
     **mechanical flips as their own tracked task** in `_aitna/TASKS.md`, separate from the
     rule. Do not mix the sweep into the change that introduces the rule (keeps each diff
     reviewable and the rule decided before the churn). A wide rename/reshape always lands as
     its own task.
   - *Tier:* mechanical sub-steps delegate to `worker` (`mech-edit`; a decided contract →
     `implement-under-spec` on the mid rung).
3. **Test** — add or extend tests. A behaviour change without a test is **incomplete**.
   Tests mirror the source layout. *Tier:* skeletons/fixtures from a stated spec delegate
   to `worker` (`test-scaffold`).
4. **Pre-commit** *(gate)* — run the [pre-commit](pre-commit.md) cycle. Tests are
   mandatory; **no commit on red**. *Tier:* the run→parse→fix→re-run loop delegates to
   `worker` (`validate-loop`); a non-mechanical red escalates back.
5. **Verify conformance** *(gate)* — for any change to **math, DataFrame/data shape, or
   architecture**, show actual behavior against the accepted intent and obtain **owner
   verification of the implementation**. Identify the checked subject, deviations,
   limitations and unresolved work. Green tests are necessary, not sufficient; an accepted
   design neither proves the implementation nor needs acceptance again merely to record
   its landing. A changed premise or material decision delta returns to design-flow.
   *Tier:* a `reasoner` review plus an optional
   `second-opinion` advisory may widen what the owner sees — they never replace the
   owner's verification.
6. **Close** — mark the task done in `_aitna/TASKS.md` *only after* owner verification.
   Preserve remaining obligations in actual linked tasks/evidence. Do not require a
   separate ADR lifecycle transition or copied landing SHA. Capture any reusable insight
   to `_aitna/memory/` (feeds the learn loop).
7. **Hand off** *(when the work goes on to a pull request or to integration)* — before the request
   is opened, run `akmon learn status` (a Node project: `npx akmon learn status`) and read its
   `sessions since the last run: N` line. When `N` is 1 or more, tell the owner a learning run is
   due before the pull request and offer the [`learning`](../skills/learning/SKILL.md) skill; do not
   start it yourself, and continue only after the owner chooses. What the owner confirms lands in the
   same pull request.
8. **Carry** *(when the work was done in a worktree)* — commit it there, on the worktree's own
   branch, after the pre-commit gate is green, and print for the owner only `cd <the owner's
   checkout>`, `git merge --squash <branch>` and `git commit -m "<message>"` with the message you
   propose, so the branch's commits become one commit on the owner's branch. When the owner says the
   carry is done, confirm it with `park worktrees <branch>` (carried by content) — never from the
   owner's words or from `git log` — and say which command is missing when it is not. After a
   verified carry, print `git worktree remove <path>`; keep the branch as a backup until a later check shows every
   path it changed holds the same content in the owner's branch, then delete it — at a periodic
   check, on request, or when the task closes.

## Gates (must hold to advance)

- **Before commit (Pre-commit):** tests pass; lint/type checks green.
- **Before Done (Verify):** math/data/architecture changes are owner-verified.
- **At Close:** task marked done; reusable insight recorded.
- **Before a pull request:** the owner has been told a learning run is due, when one is, and has chosen.

## Done

The task's goal is implemented and matches the agreed design; tests cover it and pass;
pre-commit is green; math/data/architecture changes are owner-verified; the task is
marked done and any reusable insight is captured.
