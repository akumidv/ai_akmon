# Roadmap: one plan model, a digest for the orchestrator, a view for the owner

Living design for [A50](../../meta/TASKS.md) (plan-keeping), with its tool [C152](../../meta/TASKS.md), the
annotation delegate [C153](../../meta/TASKS.md), the skill [C154](../../meta/TASKS.md), the delivery probe
[N17](../../meta/TASKS.md) and the skill-authoring process skill [A58](../../meta/TASKS.md). Nothing here is
accepted: an accepted choice becomes a stable block in the owning thematic ADR first.

## Essence

A plan for one goal is a **trunk** — the smallest set of tasks whose completion meets the goal's
acceptance — and **branches**, refinements that return to the trunk with the condition still met
([MODEL.md](../../MODEL.md) § Mission and priorities). Today the orchestrator rebuilds that picture
by reading `TASKS.md` and spending tokens on it each session, and the owner has no view of it at
all. The design moves the mechanical part into code: one deterministic **plan graph** read from
the backlog, from which a program derives two outputs for two readers.

## The split, and whether it is needed

Formation and visualization read the same fact but serve different readers with different costs
of error:

| | Orchestrator (formation and control) | Owner (visualization) |
|---|---|---|
| Question answered | what is next, what blocks it, what is on the trunk | where the work stands, spatially, at a glance |
| Cost of an error | wrong next step, rework | misreading, a wasted question |
| Size budget | tiny and stable: it enters model context | as large as a screen; costs no tokens |
| Route | context injection (SessionStart, on demand) | owner-only notice or a command, never the model |
| Changes decisions | yes | **must not** |

**Finding.** The split is needed in the outputs and the acceptance, not in the model. One plan
graph is the single owner of the fact; two renderers read it. Two rules keep the split honest:

1. The digest is a strict subset of the graph, and the view adds no input of its own, so a
   visual convenience cannot become a hidden decision input.
2. Anything shown only to the owner is not counted in the model's context; the tool says which
   output it is emitting, and a test pins that the view output never reaches an injection route.

Priority: formation and control first (it is the trunk of this work), the view second (it is the
trunk's first branch, and the part consumers feel most, so it ships in the same task).

## The plan graph — the single contract

Read by code from `TASKS.md` rows, never typed by hand:

- **sources**: the rows of the project index and of the local index ([ADR 0022](../adr/0022-local-layer-index-and-plans.md) D04). A local row's id is `_T<n>` and carries no role letter; a plan row lists its `members`. A tracked output is drawn from the project index only.
- **node**: id, gist (the title), label (short, about three words, see [the focus line](#the-focus-line)), status, kind letter, role derived from the letter.
- **hard edge** `after`: from `blocked (after X)`, `waits for X`, and `after X` in a row. A done
  node never blocks.
- **soft edge** `relates`: from `relates X` and from in-text task ids; it never blocks.
- **goal**: an explicit pick of one or more task ids, the same pick A21's first axis selects on. The tool never guesses a goal.
- **trunk**: the goal's transitive `after`-closure over not-done nodes, ordered topologically,
  with the longest chain by effort marked as the critical path.
- **frontier**: trunk nodes whose hard prerequisites are all done — what can start now.
- **branches**: nodes attached by a soft edge to a trunk node. A branch may carry its own
  branches; depth is shown, not capped.
- **unparsed**: every task id mentioned in a row that produced no edge, listed so a missed
  edge is visible instead of silent.

An edge a program cannot read from the row is a **proposal**, not a fact: see the next section.

## The focus line

A trunk the owner cannot place is lost after the first break, and so is a model after a compaction.
Both outputs therefore open with one line, **goal › now › next**, each a short label, about three
words and not a hard cap, for example `roadmap skill › hand-run trunk › plan-graph ADR`:

- **The whole view is compact: it fits one screen and reads at a glance.** Brevity of the labels
  serves that, not the other way round. A trunk longer than the screen is cut at a whole node and
  the overflow is named (`+12 more`); the height is set in the tool's data file and a test pins it.

- **goal**: the explicit pick; **now**: the active frontier nodes of the trunk, the critical path
  first; **next**: the first node that finishing *now* unblocks.
- **Every node shows its label beside its id**, in the view and in the digest. It is the
  guardrail's rule for a code in a reply, applied to the tool's own output.
- The line is in the digest, a few tokens, because the digest is cut from the graph and the label
  is a node field; the view adds nothing the digest lacks.
- **No recovery or attention benefit is claimed.** [ADR 0019 D08](../adr/0019-collaboration-guidance-from-a22.md#d08--close-the-cold-resumption-pilot-without-a-new-rule)
  closed the cold-resumption pilot: in three offline cases ordinary records sufficed and a pointer
  corrected no failure (M177–M179), and owner attention saved is unmeasured. The line is the
  owner's requirement for the owner's view; its worth for the model is part of the with-and-without
  digest measurement, not an assumption.

Where the label comes from is open (**D-FOCUS-LABEL**):

| Source | Pro | Con |
|---|---|---|
| Derived from the title by code | free, no new field | measured on the backlog: of 132 single-id rows, 29 titles carry a colon and 19 of those a prefix of at most three words, so under 15% yield a usable label |
| A `label` token authored in the row | exact, travels with the row | a new field in the row format, owned by pipelines/tasks.md and an ADR; the same family as D-EDGE-FIELD |
| Named in the plan document, beside its graph | no row-format change; plan steps that are not rows get one too | only for nodes some plan names |
| Proposed by the annotation delegate | no authoring | gated by C153's measurement, unproven |

Recommendation: labels authored in the plan document; a node it does not name prints its id with
the first three words of its title, marked `default` so a guess is never shown as a label. Settle
it with D-EDGE-FIELD after the hand run, which records how many labels the owner corrected.

## Formation: code first, a light model as a proposal layer

The deterministic parse comes first, because it is free, repeatable and checkable. The owner's
point stands that the orchestrator already spends tokens summarizing state and choosing the next
step, so a model-made annotation is acceptable where it **replaces** that spend instead of adding
to it. Rules:

- The model never rewrites the parsed graph. It returns a **proposal diff** — missing edges, an
  impact weight, an effort class — into a sidecar the orchestrator accepts or rejects row by row.
- **No standing role.** A persona with a name implies authority that the head session keeps (a
  tier changes who drafts, never who decides; ADR 0021/D04 and D06), and every other bookkeeping
  duty it could take is already carried without a model: status comes from the backlog, the work
  package fields and git; the athlos resume prompt is composed by a tool (ADR 0021/D02); watching a
  running session on the owner's request is the existing `summarize` kind on a transcript.
- **Only if the measurement earns it,** the lightest tier gets a task kind of its own,
  `plan-annotate`, routed to the worker tier, with a spec named for what it does, as the other
  delegates are: `k_annotator`. The gate is the share of task-id mentions the deterministic parse
  leaves without an edge (the `unparsed` list, measured by the hand run S1): few, and C153 is
  deleted; many, and the kind is added.
- **Priorities** are two numbers per node: *impact* on the goal's acceptance and on technical
  debt (1–5), and *effort* (S, M, L). Impact for a node on the trunk is derived by code from the
  graph (how many nodes it unblocks, whether it is on the critical path); the model adds only
  what the graph cannot see. With no hypothesis for a node the effort is the **mean value**
  (M) and the output marks it `default`, so a guess is never shown as an estimate.
- The saving is a hypothesis. It is measured before it is claimed: orchestrator tokens spent
  on state synthesis and next-step choice with and without the digest, on the same backlog, per
  [M-series](../../meta/MEASUREMENTS.md) practice and the A22 claim-calibration rule.

## What goes where

| Output | Reader | Route | In model context |
|---|---|---|---|
| frontier digest (ids with gists, blockers, the next trunk step, ≤ N lines) | orchestrator | injection on demand, JSON sidecar | **yes** |
| plan graph JSON, proposal diff | tool, orchestrator | file | read by the tool; the digest is cut from it |
| console view: spine with ribs, goal × zone matrix, sessions table | owner | owner-only notice or a command | **no** |

The delivery route is measured, not assumed: M69 covers only the `UserPromptSubmit` owner-only
notice; the statusline and Codex are open, and [N17](../../meta/TASKS.md) probes them in an attached
consumer project, never in this repository.

## The picture: alternatives considered

| Shape | Fit | Use |
|---|---|---|
| **Story map / walking skeleton** — a backbone of steps with slices hung below it | closest to "trunk, then refine"; a slice is a branch that keeps the trunk working | the conceptual model |
| **Critical path over a dependency graph** | gives the trunk's ordering and its longest chain from efforts | the computation |
| **Fishbone (spine with ribs)** | the owner's picture; its cause-and-effect meaning is wrong, its shape is right, and ribs may carry sub-ribs | the console rendering only |
| Layered DAG drawing (rows per dependency depth) | exact, but unreadable in a terminal beyond a few dozen nodes | rejected as the default; a `--layers` option is possible |
| Kanban columns | no dependencies, so no trunk | rejected |
| Gantt | needs dates, which the tracked documents do not carry | rejected |

Recommendation: the story-map model, computed as a critical path, rendered as a fishbone.

## Skills: two classes that must not be mixed

- **User skills** — shipped, applicable to a consumer's work, selected by A55's record and
  applicability condition. The `roadmap` skill (the orchestrator's procedure for reading the
  digest and choosing the next step, applicable where a plan graph exists) is one.
- **Process skills** — how akmon itself is developed; never shipped to a consumer. The skill for
  making skills is one: it runs the authoring process of [A56](../../meta/TASKS.md)'s checklist and is
  built **together with its first product**, the `roadmap` skill, so the process is distilled
  from a task actually done with an agent instead of written from general knowledge.

Today every skill under `skills/` is shipped (`bin/sync.py` skill sources), so where a process
skill lives and how `sync` leaves it out is an open decision (D-SKILL-PROCESS), to be settled
with A55.

**Three skills, one boundary** ([ADR 0022](../adr/0022-local-layer-index-and-plans.md) D05 splits the first two):

| Skill | When it runs | Does | Never does |
|---|---|---|---|
| `plan` (A61, user skill) | once, with the owner, when a change spans several tasks | forms the plan document and the member rows: initial statement, target, criteria, the dependencies the graph is read from | compute the trunk or the frontier |
| `roadmap` (C154, user skill) | every session where a plan graph exists | reads the digest and the focus line, picks the next trunk step, keeps refinements attached, opens reports with the focus line | write the plan or an edge |
| skill authoring (A58, process skill in `meta/skills/`) | when a skill is made or changed | the process both others are written under (A56's points), distilled from the work | restate either skill's procedure |

The tool (C152) is the single owner of the graph computation; both user skills link the facts in
design-flow § Plans and pipelines/tasks.md instead of repeating them. Order: A58's first pass makes
C154; A61 is its second product and is written after A58 is accepted, so the process is applied
twice and never hand-built twice.

What the A22 results bound ([ADR 0019](../adr/0019-collaboration-guidance-from-a22.md), M83–M85, M96–M98),
each a constraint and none a proof that a skill helps:

- **State only what the standard in context does not.** The full standard measurably reduced
  failures, while one added clause or two worked examples did not on top of it (M84, M97). Each
  skill therefore links the pipelines for the facts and carries only its procedure, and an
  instruction is added one at a time and measured.
- **The measured failure is a missing or wrong verification ground, not a lost thread.** With the
  project's verification command absent, models took shown CI output as verification (M85). So the
  plan names, for each frontier node, the check that shows it done, and "done" is never read from a
  claim.
- **A generic small-model judge did not detect these failures** (M98, recall 0.23–0.58). The
  annotation delegate stays a gated proposal layer (C153), never a checker.
- **A22 supports neither splitting `plan` from `roadmap` nor merging them;** the split rests on
  their different triggers (ADR 0022 D05). Each skill's benefit is a hypothesis until its evals run,
  and consumer-side guidance moved models less than guidance about the project itself (M83,
  confounded), so the evals include a case without the skill.

Authoring principles carried into A58, on top of A56's eight points:

- **Minimal sufficiency** is the first criterion: a skill, a reference, a tool or a generated file
  exists because a concrete case needs it, never because it could be useful.
- **Applicability is judged by the consumer**, through A55's condition, not asserted by the skill.
- **References, tools and generation are added on a concrete need**, one at a time.
- **Comparative measurement is done on pilots**, not as a mandatory experiment for every skill.

## Sessions: a third branch

The session surface (a head's checkpoint, the table of parallel sessions the owner coordinates)
is, in the current state of the ecosystem, prose with no code reading or writing it: a Markdown
template of ten labeled lines, no schema, no resume command, no pointer re-injected after a
compaction. The same rule applies — what a program can read, it renders, outside the model's
tokens. It is a branch of this plan, [A59](../../meta/TASKS.md), and it waits on the owner's
requirements; it does not block the trunk.

## The trunk of this work, as the plan graph would print it

Goal: **a `roadmap` skill, shipped, whose digest and view come from code.**

```
trunk   A50 accepted ──▶ C152 tool ──▶ N17 delivery probe ──▶ A58 process skill ──▶ C154 roadmap skill
                              │                                      ▲
branches                      ├── C153 annotation proposals ────────┤ (returns: weights feed the digest)
                              ├── A59 sessions view ─────────────────┘ (returns: same renderer)
                              └── A56 closes after C142, C141 ───────▶ checklist reused by A58
```

## Open

- **Decided:** no standing role (a "secretary"); if the C153 gate passes, the spec is `k_annotator` on task kind `plan-annotate`.
- **D-SKILL-PROCESS** — the location half is answered: development skills live in `<DEV>/skills/`
  ([ADR 0022](../adr/0022-local-layer-index-and-plans.md) D05), `meta/skills/` in akmon, apart from the shipped
  `skills/`; how a harness discovers them is A62.
- **Decided (D-FOCUS-LABEL):** until the hand run, labels are authored in the plan document and a
  node it does not name prints the first three title words marked `default`; the source is settled
  afterwards, with D-EDGE-FIELD. The length is short, not exactly three words; compactness of the
  whole view is the requirement.
- **Decided (D-PLAN-GOAL):** the hand run proposes how a plan row names its main goal: `members`
  lists the scope and does not say which member is the goal, while
  [design-flow § Plans](../../pipelines/design-flow.md#plans) has the owner name one.
- **D-EDGE-FIELD** — whether a structured dependency field is ever added to the task row; not
  needed for the trunk, because the unparsed list measures how much the free-text parse misses.
- **D-A59-REQ** — the requirements for the sessions branch.
- The answer-form conflict to settle in A58: C79's frontmatter rule asks for a result-first
  description, A56 point 3 for "Use this skill when…"; one form has to own it.
