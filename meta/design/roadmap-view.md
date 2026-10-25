# Roadmap: one plan model, a digest for the orchestrator, a view for the owner

Living design for [A50](../TASKS.md) (plan-keeping), with its tool [C152](../TASKS.md), the
annotation delegate [C153](../TASKS.md), the skill [C154](../TASKS.md), the delivery probe
[N17](../TASKS.md) and the skill-authoring process skill [A58](../TASKS.md). Nothing here is
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

- **node**: id, gist (the title), status, kind letter, role derived from the letter.
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
  [M-series](../MEASUREMENTS.md) practice and the A22 claim-calibration rule.

## What goes where

| Output | Reader | Route | In model context |
|---|---|---|---|
| frontier digest (ids with gists, blockers, the next trunk step, ≤ N lines) | orchestrator | injection on demand, JSON sidecar | **yes** |
| plan graph JSON, proposal diff | tool, orchestrator | file | read by the tool; the digest is cut from it |
| console view: spine with ribs, goal × zone matrix, sessions table | owner | owner-only notice or a command | **no** |

The delivery route is measured, not assumed: M69 covers only the `UserPromptSubmit` owner-only
notice; the statusline and Codex are open, and [N17](../TASKS.md) probes them in an attached
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
  making skills is one: it runs the authoring process of [A56](../TASKS.md)'s checklist and is
  built **together with its first product**, the `roadmap` skill, so the process is distilled
  from a task actually done with an agent instead of written from general knowledge.

Today every skill under `skills/` is shipped (`bin/sync.py` skill sources), so where a process
skill lives and how `sync` leaves it out is an open decision (D-SKILL-PROCESS), to be settled
with A55.

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
tokens. It is a branch of this plan, [A59](../TASKS.md), and it waits on the owner's
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
- **D-SKILL-PROCESS** — where a process skill lives and how it stays out of a consumer's tree.
- **D-EDGE-FIELD** — whether a structured dependency field is ever added to the task row; not
  needed for the trunk, because the unparsed list measures how much the free-text parse misses.
- **D-A59-REQ** — the requirements for the sessions branch.
- The answer-form conflict to settle in A58: C79's frontmatter rule asks for a result-first
  description, A56 point 3 for "Use this skill when…"; one form has to own it.
