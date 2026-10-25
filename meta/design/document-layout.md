# Document layout — knowledge in `docs/`, process and evidence in `<DEV>`

Status: **layout accepted** by [ADR 0023](../decisions/0023-project-documents-layout.md); this
document keeps the analysis, the alternatives and the migration steps. Owner: [A64](../TASKS.md)
(records and owner documents), [C159](../TASKS.md) (path accessor), [C160](../TASKS.md)
(akmon's own move). Code has not started.

## Problem

A session asked "where did we decide this" or "what did we measure" got two answers: akmon keeps
decisions, designs, reviews, measurements and experiments under `meta/`, and tells a consumer to
put its ADRs under `docs/dev/decisions/`. Records of two different kinds sat side by side with the
backlog, and nothing said which a newcomer needs and which only the work needs.

## The two kinds

| Kind | The reader asks | Examples |
|---|---|---|
| **Lasting knowledge** | how is this built, and why | accepted decisions, living designs, architecture, requirements, use documentation |
| **Process and evidence** | what is being done, and what did the work find | backlog, roadmap, reviews, measurements, experiments, benchmarks, local layer, development skills, tools, memory |

Evidence supports a document and may be cited by it; it is not itself a document a newcomer reads
first. A review is a point-in-time assessment; a measurement is a fact with the version it was
verified on; an experiment is sealed input and output; a benchmark is a run. None of these is
shaped to be read as an explanation.

## Target layout

```
docs/
  adr/             decisions: NNNN-kebab-title.md, index README.md        (D02)
  design/          living designs: open questions, alternatives, rejected branches
  …                architecture, requirements, use documentation, flat beside them
<DEV>/
  TASKS.md  TASKS_ARCHIVE.md  ROADMAP.md      the backlog and the plan view
  reviews/  MEASUREMENTS.md  experiments/  benchmarks/    evidence
  local/{handoff,plans,tasks}/<id>/  TASKS.md  ignored (0022)
  skills/  tools/  memory/  agents/           development layer
```

`<DEV>` is `<AITNA_ROOT>` (default `_aitna`) in a consumer and `meta/` in akmon
([ADR 0022](../decisions/0022-local-layer-index-and-plans.md)). In akmon the target is
`docs/adr/`, `docs/design/` and `meta/` as before for the rest.

## How a session finds them

A session is told where records live from one place, `AGENTS.md`, and the code looks the paths up
through the accessor (C159); a hook or tool that needs the decision directory never carries its
own literal. A search for a decision starts at `docs/adr/README.md`, the index; a design at
`docs/design/`; evidence is reached from the document that cites it. The path of a record is the
same on every machine and in every project that follows the layout, which is what a consumer's
session gains over today's two answers.

Checked against practice: `adr-tools` keeps ADRs in `doc/adr` by default, allows another location
and marks it in a `.adr-dir` file; that marker is a ready convention for detection. The defaults of
other ADR tooling were not confirmed and the layout does not depend on them. The `doc/`-versus-`docs/`
difference is the reason the path is resolved, not fixed.

## Options weighed

| | A. As is | B. Knowledge in `docs/`, evidence in `<DEV>` | C. Everything in `docs/` |
|---|---|---|---|
| Newcomer finds decisions and designs | two places | one | one |
| Evidence stays out of the way | yes | yes | no, buries the explanation |
| Works in a package-mode consumer (no `<DEV>` tree) | records absent | records present | present |
| Cost for akmon | none | one move, 52 documents | one move, ~500 files |

B is accepted. The move cost counts documents: decisions 23, designs 29; reviews (101) and
experiments (369) stay where they are.

## Path resolution (the shape C159 designs)

The accessor sits with the project-root and dev-root code (`common/project_root.py`, C157). It
returns the decision directory and the design directory. Order of resolution: a declaration in
`<AITNA_ROOT>/.akmon.toml`; else an existing directory (the `.adr-dir` marker, then a short list of
known names); else the default. A project with two candidates is a finding, not a silent pick.
`init` creates nothing; the first record creates its folder. The key names, the list and the
two-candidate behaviour are C159's decision block, written before code.

Hook data that carries these paths today: `planning_doc_segments` and `non_code_segments` in
`hooks/hook_core.json` name `/{{aitna}}/design/` and `/docs/dev/`. They become values from the
accessor, in the Python hook and its JavaScript twin together (ADR 0020).

## Migration of akmon's own records (C160)

1. After C157 and C159, in one commit, one mechanic pass: `meta/decisions/` → `docs/adr/`,
   `meta/design/` → `docs/design/`.
2. Gate: a script resolves every relative link and every `path:line` citation of the touched
   documents before and after; the commit goes in only when the unresolved set does not grow.
   C142's resolver (`common/doc_refs.py`) is the candidate carrier.
3. Carriers to revise with it: `meta/checks/decision_records.py`, `meta/bin/validate.py`, the
   comments naming the old paths in `bin/`, `common/`, `hooks/` and `js/`, the development-tree
   path fragments in `bin/verify.json` (`decisions/`), the tracked documents that name the paths
   (decisions 28, designs 53, reviews 25, MEASUREMENTS 14, experiments 30, TASKS 40 by a count of
   the earlier survey), `AGENTS.md` and `README.md` links.
4. Sealed experiment inputs keep their bytes and names; the old paths they mention are recorded
   as left alone.

## Open

- **A `benchmarks/` home.** akmon has none today; the layout reserves `<DEV>/benchmarks/` beside
  `MEASUREMENTS.md` and `experiments/`, created by the first benchmark.
- **Architecture and requirements.** Placed flat in `docs/` by the layout; neither exists as a file
  in akmon, so the names wait for the first one.
- **A site generator.** A project publishing `docs/` decides whether `adr/` and `design/` publish
  with it; the layout does not.
