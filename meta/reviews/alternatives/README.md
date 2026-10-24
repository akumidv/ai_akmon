# Alternatives — what other projects were examined, and what akmon did with them

This folder is akmon's own record of which other projects were examined for ideas and what akmon
did with the findings. It serves akmon's development only and is not shipped to consumers.

## When to open it

Open it when you look for alternatives to a design choice, or want to check a decision against how
other projects solved the same thing. It supplies ideas and comparison material. A finding here is
not an akmon decision: decisions live in [`meta/decisions/`](../../decisions/), execution in
[`meta/TASKS.md`](../../TASKS.md).

## Index

| File | Kind | Subject | What it contains |
|---|---|---|---|
| [review-codex-alternatives.md](review-codex-alternatives.md) | review | popular alternatives to akmon | a landscape table of ten projects with a category and a relationship to akmon each, then the closest broad alternatives |
| [review-codex-akmon-top-3.md](review-codex-akmon-top-3.md) | review | Superpowers, OpenSpec, wshobson/agents | why these three cover the most distinct failure surfaces, the akmon baseline and weak spots, candidate experiments |
| [review-claude-ponytail.md](review-claude-ponytail.md) | review | ponytail | what it is and how it differs in class from akmon, then high-value ideas as backlog candidates |
| [review-codex-ponytail.md](review-codex-ponytail.md) | review | ponytail | evaluation criteria for a transferable idea, an executive summary, a ranked comparison with akmon |
| [review-claude-superpowers-openspec-wshobson.md](review-claude-superpowers-openspec-wshobson.md) | review | Superpowers, OpenSpec, wshobson/agents | a deep pass per project: what it is and its high-value ideas; new weaknesses W17+ proposed but not merged by the review itself |
| [review-claude-warp.md](review-claude-warp.md) | review | Warp's orchestration | four orchestration traits set against akmon today, with ideas for the owner to decide |
| [plan-akmon-from-alternatives.md](plan-akmon-from-alternatives.md) | plan | all of the above | the register: weaknesses, borrowed concepts, phased items and a priority view, each tied to its source |
| [walkthrough-a11.md](walkthrough-a11.md) | walkthrough | the plan's priority themes | per-theme essence, as-is, solution, alternatives, owner verdict and pilot criterion |
| [n2-stage0-probes-inventory.md](n2-stage0-probes-inventory.md) | inventory | vendor delivery probes | what a subagent actually receives on Claude and on Codex, plus the guardrail-to-hook invariant inventory |

The plan is the register that merges the reviews. The walkthrough and
[ADR 0010](../../decisions/0010-alternatives-adoption-a11-verdicts.md) are where its verdicts were
accepted. The files do not name an author beyond the `claude` or `codex` tag in the file name.
`review-claude-warp.md` is short and covers Warp's orchestration pages only; product analysis is
deferred as task A48.

## Ways to find alternatives

- **From the product's own history:** earlier decisions, rejected branches and measurements.
- **From competing or analogous products:** their reviews in this folder plus extra research.
- **From articles and public write-ups:** no review in this folder yet.
- **From brainstorming:** filtered by independent agents that have no sight of each other's
  output; no review in this folder yet.

## Adding a review

- Name the file `<kind>-<author>-<subject>.md`, like the existing ones.
- No dates in names or text; git history is the timeline.
- A review stays point-in-time and is never rewritten. New findings go into the plan register.
