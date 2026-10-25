# 0023 — Where project documents live

- **Status:** Accepted for **D01–D06**. The owner decided each choice in session: lasting knowledge
  in `docs/` and process and evidence in `<DEV>`, the directory names, the flat shape, resolution by
  code, the migration of akmon's own records, and the names of the other folders of `docs/`. The
  owner then ordered akmon's own move ahead of the two accessors (**D05**); it is done in the
  working copy. The accessors are not started.
- **Owner:** akuminov@gmail.com
- **Amends:** the `docs/dev/` split recommended in [CONCEPT](../../meta/CONCEPT.md) § Dev docs — the
  recommendation becomes this layout.
- **References:** [design: document layout](../design/document-layout.md) (analysis, alternatives,
  migration steps) · [0022](0022-local-layer-index-and-plans.md) (the local layer and the dev root) ·
  [pipelines/tasks.md](../../pipelines/tasks.md) · live tasks [A64](../../meta/TASKS.md), [C159](../../meta/TASKS.md),
  [C160](../../meta/TASKS_ARCHIVE.md), [C157](../../meta/TASKS.md).

## Context

A project keeps two kinds of writing. One a newcomer reads to learn how the project is built and
why: the accepted decisions, the designs, the architecture. The other the people and agents
producing the work need: the backlog, the roadmap, reviews, measurements, experiments. They were
placed by habit. akmon keeps `docs/adr/`, `docs/design/`, `meta/reviews/`,
`meta/MEASUREMENTS.md` and `meta/experiments/` side by side with the backlog, and tells a consumer
that its ADRs go to `docs/dev/decisions/` (CONCEPT recommended a `docs/dev/` split, a guideline
not an archetype requirement). A session looking for "where did we decide this" therefore had two
answers, one for akmon and one for a consumer, and the consumer's answer put records in a folder
nobody else names.

The customary names are partly checked. `adr-tools` keeps ADRs in `doc/adr` by default and lets the
log live elsewhere, marking the choice in a `.adr-dir` file (checked in the READMEs of adr-tools and of a port of it). The
defaults of other ADR tooling (`docs/decisions`, `docs/adr`) were not confirmed here and are not
relied on; this record needs only that a project may already have such a folder.

## Decision

1. Lasting knowledge lives in `docs/`; process and evidence live in `<DEV>` (**D01**).
2. Inside `docs/` the layout is flat: decisions in `docs/adr/`, living designs in `docs/design/`
   (**D02**).
3. One code accessor resolves both paths, uses a directory the project already has, and takes an
   override in `.akmon.toml` (**D03**).
4. References run between `docs/` and the evidence in `<DEV>`; nothing references `local/`
   (**D04**).
5. akmon applies the layout to its own records in one commit (**D05**).
6. The other folders of `docs/` have recommended names, and knowledge that one skill alone needs
   lives with that skill (**D06**).

## Alternatives considered

- **Everything in `docs/`.** One place, one search. But reviews, measurements and experiments are
  evidence of the work, large and unreadable as documentation, and would bury what a newcomer
  came for.
- **Everything in `<DEV>`.** Matches akmon today. But `<DEV>` is the dev layer, absent from a
  package-mode consumer and named `_aitna` by default; a decision a team should find does not
  belong behind a tool-specific folder name.
- **`docs/dev/` as the parent.** The earlier recommendation. It adds a level to every path for a
  distinction `docs/adr/` and `docs/design/` already carry.
- **`docs/decisions/` for the ADRs.** Spelled out and used by some tooling. The owner chose the
  accepted short form `adr`.
- **A fixed path with no override.** Simple, but a project with a decision log already in
  `doc/adr` or `docs/decisions` would have to move it or keep two.

## Consequences

- **Carriers.** Owner documents (A64): [MODEL.md](../../MODEL.md) layer text,
  [CONCEPT](../../meta/CONCEPT.md) § Dev docs, [BOOTSTRAP.md](../../BOOTSTRAP.md) step 5,
  [pipelines/tasks.md](../../pipelines/tasks.md) and the index of this directory. Code: the path
  accessor (C159); the migration of akmon's own records (C160).
- **Shared text names the roles, not akmon's folders.** Shipped documents may say `docs/adr/` and
  `docs/design/` as the consumer's convention; they cite no numbered record and link nothing under
  `meta/`.
- **akmon moved before the accessors exist.** The hook data (`hooks/hook_core.json`) still names
  `/docs/dev/` and `/{{aitna}}/design/` until C159; a record under `docs/adr/` or `docs/design/`
  raises no planning-document reminder meanwhile, which is also how `meta/decisions/` and
  `meta/design/` behaved before the move (neither path matched).
- **A consumer laid out otherwise is moved by its owner, by hand.** akmon ships no tool for it and
  records no obligation; until the owner does, the accessor's detection (**D03**) keeps such a
  project working.
- **The use-surface check keeps `decisions/`.** The development-tree path fragments in
  `bin/verify.json` still name `decisions/`: shipped text names no `decisions/` path and the fragment
  stays a guard. A later change of that list is not part of this record.
- **A documentation site** that publishes `docs/` publishes the two folders too, as MADR-style
  repositories already do; excluding them is the project's site configuration.
- **Untouched.** [0022](0022-local-layer-index-and-plans.md) in full, the numbering and block
  rules of this directory, sealed experiment inputs.

## Addressable accepted decision blocks

### D01 — Lasting knowledge in `docs/`, process and evidence in `<DEV>`

`Decision-ID: ADR-0023/D01`

`docs/` holds what a reader learns the project from, and keeps its value without the process that
produced it: accepted decisions, living designs, architecture, requirements, and documentation of
the product's use. `<DEV>` holds how the project is run and what the running produced: the
backlog (`TASKS.md`, `TASKS_ARCHIVE.md`), the roadmap, reviews, measurements, experiments,
benchmarks, the ignored local layer, and development skills, tools and memory.

The test is the reader's need: *does a newcomer read it to learn how the project is built, or is it
a record of how the work was managed and measured?* Reviews, measurements, experiments and
benchmarks are working evidence. A document may reference them; none of them is a document a
newcomer needs.

### D02 — Flat `docs/`: `adr/` and `design/`

`Decision-ID: ADR-0023/D02`

Decisions live in `docs/adr/` — the accepted abbreviation — and living designs in `docs/design/`.
There is no `docs/dev/` level. The conventions of 0001–0022 carry over unchanged: numbered, not
dated file names, thematic records with addressable decision blocks, an index in
`docs/adr/README.md`. A design holds open questions, alternatives and rejected branches until the
owner accepts a bounded scope, which then becomes a decision block (the design-flow rule).

### D03 — Paths resolved by code, existing directories respected

`Decision-ID: ADR-0023/D03`

One code accessor, in the module that owns the project root, returns the decision directory and
the design directory; every tool and hook calls it and none restates a literal. The defaults are
`docs/adr/` and `docs/design/`. A project that already keeps its records elsewhere (`docs/decisions`,
`doc/adr`, a directory named by an `adr-tools` `.adr-dir` file) has the existing directory detected
and used; a declaration in `<AITNA_ROOT>/.akmon.toml` overrides detection. The names of the keys, the
list of detected locations and the fallback when both a default and an existing directory are
present are the work of C159 and are recorded in its own decision block before code, as C157 does
for the dev root.

`akmon init` creates neither directory: the first record creates it.

### D04 — Direction of references

`Decision-ID: ADR-0023/D04`

A document in `docs/` may link to the evidence it rests on in `<DEV>` — a measurement row, a
review, an experiment — and a record in `<DEV>` may link to `docs/`. Neither side references
material under `<DEV>/local/` (0022/D02). A reference to evidence is a pointer, never a
dependency: a document stays readable where `<DEV>` is absent, so it states the fact it needs and
cites the evidence for it.

### D05 — akmon applies the layout to itself

`Decision-ID: ADR-0023/D05`

akmon moves its decisions from `meta/decisions/` to `docs/adr/` and its designs from `meta/design/`
to `docs/design/` in one commit. The first plan was to wait for the dev-root accessor (C157) and the
document-path accessor (C159); the owner ordered the move ahead of them, and the move needs neither. `meta/` keeps
the backlog, roadmap, reviews, measurements, experiments, benchmarks, the local layer, development
skills and the conformance and test trees. The move is mechanical and gated: a script resolves
every relative link and every `path:line` citation of the touched documents before and after, and
the commit goes in only when the unresolved set does not grow. Sealed experiment inputs keep their
bytes and their names; a path they mention in the old place is recorded, not rewritten.

### D06 — The other folders of `docs/`, and what stays with a skill

`Decision-ID: ADR-0023/D06`

Beside `adr/` and `design/`, a project's `docs/` uses these names: `requirements/` for standing
requirements, `guides/` for how to work on the code (conventions, build, deployment), and `reference/`
for reference material about the product (schemas, vocabularies); `reference/` is optional. Only
`adr/` and `design/` are resolved by code (**D03**); the other names are recommended, with no hook
and no check behind them.

Knowledge that one skill alone needs lives with that skill, in `<skill>/references/` — for a
development skill `<DEV>/skills/<name>/references/` — and not in `docs/`. Knowledge about the
product that any developer reads lives in `docs/`, `reference/` included. The test is that of **D01**:
whether a newcomer reads it to understand the product, or only a procedure needs it.
