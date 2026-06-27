# Pipeline: review-flow

The cycle the [review](../roles/review.md) role follows to turn a subject + a yardstick into a
findings report that `architect` (or, for a local fix, `engineer`) can act on.

> A pipeline is a **declarative, ordered cycle** — the steps and their gates, not a script.
> review-flow is **analysis only**: it never constructs the fix (that is
> [design-flow](design-flow.md)).

## When

Any time the question is *what is* and *how well does it meet its goal* — a state/quality
assessment of the product, a component, a functional part, or an element; a conformance check
against requirements/vision/environment; a hunt for problems, bottlenecks, or mismatches.
A request to *decide how it should be* goes to design-flow; a request to *build a decided
thing* goes to code-flow.

## Steps

1. **Frame** — fix the **subject** (product / component / element) and the **level**, and name
   the **yardstick** the subject is judged against (goal, vision, requirement, environment,
   user expectation). An unstated yardstick produces unfalsifiable findings.
2. **Decompose** — break the subject into parts and relations. Sweep deliberately: top-down
   (does the structure serve the goal?), bottom-up (do the parts add up?), and horizontal (do
   components and their interfaces fit?). Read the code/docs/runtime — verify against source,
   not memory.
3. **Measure** — compare each part against the yardstick. Record divergences as findings, each
   with **evidence** (file/line/behaviour/violated requirement) and the yardstick it fails.
4. **Calibrate** — rank findings by severity (load-bearing defect vs cosmetic nit) and note
   blast radius (local / crosses one boundary / crosses several).
5. **Hand off** *(gate)* — for each finding, state the **criteria a fix must satisfy**, and
   route it: a local fix → `engineer`; a structure/contract decision → `architect`; a wrong
   yardstick or a problem spanning several boundaries → escalate. **Stop at construction** —
   proposing the new structure is synthesis, not review.
6. **Report** *(gate)* — deliver the findings in chat first. Write it into a review doc or the
   backlog only after the owner agrees (Analysis before mutation).

## Gates (must hold to advance)

- **At Hand off:** every finding carries evidence + criteria and is routed; nothing is
  "fixed in place" inside the review.
- **At Report:** findings reported before anything is recorded; recording is owner-agreed.

## Done

The report states what is — measured against a named yardstick, evidence per finding, ranked
by severity — with criteria and a route for each finding, escalations raised rather than
absorbed, and nothing recorded or changed without owner agreement.
