# The athlos and the job: one entity, one name

**Status:** **Decided** in [ADR 0029](../adr/0029-ergon-athlos-step-one-method-of-work.md), accepted; C188 is done. This record keeps the options, the prices and the draft history behind that decision, so where a passage reads as open, the ADR is the answer. Nothing here is implemented yet: the code is carried by C189–C193.

## Why this record exists

ADR 0021's *athlos* and ADR 0028's *job* describe the same rung of the same ladder. The owner asked
for them to be merged into one entity, named once, and for the correspondence between the entities
and the way they nest to be worked out **from the meaning of the words** — and the result to be
written down as a file with its materials and its measurements, for an independent review.

This record answers that: §1 the premises as they stand, §2 the entities the tree actually has, §3
what a union has to settle, §4 the words and their meanings, §5 the correspondences and the
nesting, §6 the four decisions and a recommendation each, §7 the packages with their prices, §8 the owner's answers, §9 the commands that re-derive every number in this file, §10 what it leaves open, and
§11 the chain designed through as one method of work — the levels, the transfers, the exchange
between sessions and agents, and how it lies on the harnesses' own mechanisms — with the codes it
adds.

The model this record proposes to change is in
[park-and-resume](park-and-resume.md); the merge's analysis of the model (the overlap, the carrier,
the rules that follow) is in [that design's section on the two words](park-and-resume.md#the-athlos-and-the-job--one-rung-two-sides).
This record owns the **options and prices** behind the decision — which word names what, and what a move costs; [ADR 0029](../adr/0029-ergon-athlos-step-one-method-of-work.md) owns the decision, and that design owns the **model**. §11 is the method the merged words name; what the owner accepted of it is in the ADR and in that design, and the rest stays here as the draft.

**How to read every price in this record.** A price is the number of **occurrences of the whole
word**, case-insensitive, over the files git tracks that end in `.md`, `.py`, `.mjs`, `.json`,
`.toml` or `.js` — not lines, not files. The commands are in §9; the measurements behind them, with
their results, are in the kit's `EVIDENCE.md`. This record's own file is not yet tracked, so it is
not counted in any price below.

**Where the materials are.** This record is the **design**. The materials it is read against ride in
the C188 kit's `materials/` folder — in the local layer, so they are not tracked by git and are
copied by hand: `sources.md` (the quoted texts, with `file:line`), `current-implementation.md` (what
the tree does today for the *ergon* side), `ideas-and-alternatives.md` (the owner's ideas, written
out to be designed — including the composite athlos and the two readings of *ergon*) and
`check_links.py` (the link and anchor checker this record's checks were run with). The kit's
`EVIDENCE.md` holds the measurements; `HANDOFF.md` holds what is verified and what is not.

## 1. The premises, as verified

| # | Premise | Where it is | What it says |
|---|---|---|---|
| P1 | The athlos is a bounded piece of a plan's work with an acceptance condition of its own | [ADR 0021/D04](../adr/0021-athlos-deferred-work-packages-and-handoff.md#d04--an-athlos-is-the-labor-not-its-frame-and-not-its-doer) | "one bounded labor of an approved plan: a piece of work with its own acceptance condition, named by the pair (task id, zone) … carried by a session and executed by `k_*` delegates, and it outlives both" |
| P2 | The job is a unit of a plan run in isolation by one holder toward a result of its own | [ADR 0028/D08](../adr/0028-park-and-resume-the-kit-and-the-dotted-layer.md#d08--task-plan-job-and-step) | "A **job** is a unit of a plan, run in isolation by one holder (D09) toward a measurable result of its own … Jobs may run in parallel" |
| P3 | The criterion that separates the ladder's rungs | ADR 0028/D08 | "what runs in parallel in sessions of its own is a job; what one holder does in order is a step; what one holder fans out to subagents is a zone" |
| P4 | The frame word is frozen | ADR 0021/D04, "Why the frame word stays" | `zone` is mechanism — a parsed label, a delegation-ledger column, a coverage-map grouping — so "a rename is a data-format change shipped to every consumer, not a sweep" |
| P5 | The athlos was never given a carrier | ADR 0021/D01 and the design's § Portability | The athlos's record was a work package that no code writes; the ergon's kit is the carrier that was built instead |
| P6 | The ladder's words were chosen in plain English, on the CI-workflow model | ADR 0028/D08 | "Four words, one thing each: task, plan, job, step" — the model of a CI workflow, a job being a sequence of steps |
| P7 | The Greek register holds the actors and the places, not the ladder | [ADR 0008 §4](../adr/0008-mythological-naming-aitna-akmon-kyklopes.md) and its amendments | The reservoir holds *keraunos* (a deliverable), *Hephaistos* (the orchestrator), *Brontes / Steropes / Arges* (smith tiers), *sphyra* / *physa* (tools), *lemnos* (a repository), *ergon* (the work, or the layer — the ADRs carry both readings) — "future entities are named by lookup, not invention" |
| P8 | Two terms for one thing is the complaint | the owner, this session | the athlos and the job are the same rung; the vocabulary must carry it once |
| P9 | The merge's payoff the owner names | the owner, this session | an athlos must be able to run in parallel — which is what the ergon's lease, worktree and note give it |
| P10 | The athlos may be **composite**, not one rung | the owner, this session | «athlos может же быть составным — уровень ergon и внутри как job — их реализация ведь также может быть организована через план и шаги» — the piece of work and the unit inside it, both realized through a plan and steps. The materials folder carries it as Idea 2, with the five questions it has to answer |
| P11 | A task must have an understandable result | the owner, this session | «задача должна иметь SMART модель — т.е. результат у нее понятен». The tree has two carriers for it today: the plan's criteria and the unit's `result` field (`tools/park/park.py:195`) |
| P12 | The word the owner wrote as "ergos" is *ergon* | the owner, this session | the owner's clarification; every file of this record and of the materials folder spells it *ergon* |

## 2. The entities the tree actually has

| # | Entity | Today's word | Where it lives | Record that owns it |
|---|---|---|---|---|
| E1 | a change the backlog records, outside any plan | **task** | the project's `TASKS.md` | ADR 0028/D08 |
| E2 | a target over one or more tasks | **plan** | `PLAN.md` in a kit | ADR 0028/D05, D08 |
| E3 | a unit of a plan run in isolation by one holder | **job** | a line of `PLAN.md`; `jobs/<n>-<name>/` with `JOB.md`, `HOLDER`, `PARK.md`, `RESUME.md` | ADR 0028/D08–D11 |
| E4 | a part of one job, done in order | **step** | a line of `JOB.md` | ADR 0028/D08 |
| E5 | the frame of a holder's fan-out | **zone** | the `[zone:LABEL]` marker → a delegation-ledger column | ADR 0028/D08, 0021/D04 (frozen) |
| E6 | the folder that holds a piece of work whole | **kit** | `<DEV>/.ergon/<id>-<name>/` | ADR 0028/D02, D12 |
| E7 | the labour itself, keyed (task id, zone) | **athlos** | prose only — 106 whole-word uses, **0 in code** | ADR 0021/D04 |
| E8 | the home of work, and the concept "the work and what it has made so far" | **ergon** | the layer `<DEV>/.ergon/` | ADR 0008 §4 amendment (A59), ADR 0028/D01 |
| E9 | the session that holds a unit | **holder** | the `HOLDER` lease file | ADR 0028/D09 |
| E10 | the delegate that does part of a zone | **Kyklōpos** (`k_*`) | the agent roster | ADR 0008 |

E3 and E7 are the same rung: bounded, one acceptance condition of its own, one holder, runnable in
parallel, never leaves its plan. What differs is only **where the record is** (P5) and **how the unit
is keyed** — 0021 keys it by the pair (task id, zone); 0028 keys it by `<kit-id>.<n>` and names the
tasks it serves.

## 3. What a union has to settle

A merged unit needs three things decided, and only the first is the naming.

1. **The word.** One word for the rung (§6.1).
2. **The key.** 0021's `(task id, zone)` pair or 0028's `<kit-id>.<n>` plus a `tasks:` field, or
   both — the id as the unit's place in the plan, the pair as its content (§6.3).
3. **The content.** What the merged unit promises. The union of the two texts, in the tree's own
   terms, would read:

   > A unit of a plan's work with its own acceptance condition, run in isolation by one holder and
   > carried by that holder's session; it serves one or more of the plan's tasks; it may run in
   > parallel with other units of the plan, in its own worktree; it is leased, so that no two
   > holders hold it at once; it is parked and resumed by its own note; and its work is executed by
   > `k_*` delegates inside zones, and outlives both the session and the delegate that carried it.

   Three clauses are new against 0021's text (the lease, the worktree, the note) because the ergon's
   machinery gives them; two are new against 0028's text (the acceptance condition as the unit's own
   rather than the plan's result, and the zone as where the work lands) because the athlos's text
   carries them.

## 4. The words, and what they mean

The register akmon draws on is Greek and mythic (P7). These are the senses the decision is read
against; a reviewer with a lexicon can check each one, and nothing else in this record depends on
them.

| Word | Sense | What it would name |
|---|---|---|
| **ἔργον** (*érgon*) | work; the deed; the thing made, the product. Homeric *ἔργα* — works, structures. It names the work **as a thing**, both the doing and what it has made. | The piece of work as akmon holds it: its description and what it has made so far — which is exactly the gloss ADR 0008's amendment already gives it, and which the layer `<DEV>/.ergon/` holds one of per folder |
| **ἄεθλον** (*áethlon*, pl. *aethla*) | contest, feat of strength, the prize of a contest. It presupposes a **standard** to be measured against and a **verdict**; it is bounded and it is judged. | The unit of work with an acceptance condition of its own — the doing, bounded and judged. 0021 already fixed the spelling and the plural. |
| **ἄργος** (*árgos*) | adjective "swift, white, bright" (of ships); **Ἀργώ**, the ship *Argo*, and the Argonauts, the expedition with many hands; **Ἄργος**, Argus, the all-seeing watcher. | The vessel that carries the crew and the stages, or the watcher that keeps watch — in akmon's terms, the **machinery** around a unit (lease, branch, worktree), not the work itself |
| **Ἄργης** (*Argēs*) | the hundred-handed giant, one of Zeus's smiths | **Already reserved** by ADR 0008 §4 for a **smith tier** — a different rung. Binding it elsewhere is D-RESERVE-BIND's business |
| **job** (English) | a piece of work to be done, typically assigned, often as part of a larger process | The unit, in plain words — exactly what it is |
| **kit** (English) | the set of parts a thing comes in, held together | The folder that holds a piece of work whole |

Two things follow from the senses and the tree, and both are the owner's to weigh:

- **ἔργον is read two ways, and the ADRs carry both.** ADR 0008's amendment says *ergon* "names **the
  work and what it has made so far**" and, a sentence later, "It is a place for work, not a state" —
  the antecedent there being the folder. ADR 0028 calls the layer "the home of work" (D01), calls the
  folder per piece of work "named *ergon*" (its own status header), calls that folder a **kit** (D02's
  body) and, in its alternatives, says "*ergon* names the work and leaves *park* to the act". So
  *ergon* may name the **layer** (the home) or the **piece of work** (the work itself) — and the tree
  says *kit* for the piece of work in 1001 places (740 in code) while the layer's path says *ergon* in
  373 code places. Under the second reading the layer's path needs no move: `<DEV>/.ergon/` already
  reads as the home of ergons. This record does not settle the reading; it is **D-A59-PIECE**, and
  both readings with their sources are in the materials folder (see §9).
- **ἄργος is one letter from ἔργον and one word away from Argo Workflows**, the workflow engine
  whose model ADR 0028/D08 borrowed ("the model is the one of a CI workflow"). A reader who knows
  that engine will read *argos* as Argo; and *Arges*, the reservoir's own Greek for the Argive, is
  reserved for a smith tier.

## 5. The correspondences, and the nesting

### 5.1 Rung by rung

| Rung | What it is | Today | Candidate | What the candidate adds | Price (whole-word occurrences, tracked tree) |
|---|---|---|---|---|---|
| E6 the piece of work whole | one folder: the plan, its units, the briefs, the material | `kit` | **ergon** | the gloss ADR 0008 already gives it; the layer then holds ergons | **1001** — 740 in code (`tools/park/park.py` 159, `js/tools/park/park.mjs` 179, their tests 134 + 164, `tools/park/park.json` 19), 261 in prose of which 24 in shipped prose; the helper's API names (`list_kits`, `kit_state`, `write_kit`) |
| E3+E7 the unit of the plan's work | bounded, own acceptance condition, one holder, parallel, leased, parked | `job` + `athlos` | **athlos** | the Greek for the doing: a bounded trial with a verdict; 0021's spelling and plural are already fixed | **732 + 106** — 535 in code (`park.py` 118, `park.mjs` 111, tests 72 + 97), 197 in prose of which 28 in shipped prose; `jobs/` → ?, `JOB.md` → ?; 15 park scenarios carry one of the two words in their names; the plan's line format |
| ″ | ″ | ″ | **argos** | fits the machinery, not the work; two collisions (§4) | as above, plus an ADR 0008 §4 amendment and a README naming line |
| ″ | ″ | ″ | **job** | plain, exact, already accepted (P6) | **0** |
| E8 the layer the kits live in | the home of work — the folder `<DEV>/.ergon/` | `ergon` | (none) | — | **456** — 373 of them in code, because the layer's *path* is shipped: `init`'s ignore lines, the dev-root accessor and its twin, the corpus |
| E9 the holder | the session that holds a unit; the lease that keeps it exclusive | `holder` | holder | — | 507 |
| E4 a part in order | one part of a unit | `step` | step | — | 898 |
| E5 the fan-out frame | where the work lands | `zone` | zone | frozen (P4) | 623 |
| E2 the target | what the plan aims at | `plan` | plan | — | 2613 |
| E1 the backlog row | what the backlog records | `task` | task | — | 1729 |

### 5.2 How they nest

```
the layer  <DEV>/.ergon/            (ergon — the home of work; ADR 0008's amendment)
└── E6  a piece of work whole       (kit | ergon)   one folder; one transfer
    ├── E2  the plan                (plan)         PLAN.md — the target, the criteria
    │   ├── E3+E7  a unit of the plan's work        (job | athlos)   one line of PLAN.md
    │   │   └── E4  a part, done in order           (step)          a line of the unit's file
    │   │       └── E5  where the work lands        (zone)          a fan-out, frozen
    │   │           └── E10 the delegate            (Kyklōpos)      k_*
    │   └── E9  the holder                          (holder)        the HOLDER lease
    └── briefs, material, PARK.md, RESUME.md
```

The athlos (E7) has no place in this picture today — it is the *same box* as E3, described from the
doing's side, with no carrier of its own (P5). Its two useful clauses are the ones the box does not
have: the **acceptance condition of its own** (0028's unit has the plan's result, not its own) and
the **zone as the place where the work lands** (0028's zone belongs to a step's fan-out, not to the
unit).

## 6. The four decisions, with a recommendation each

### 6.1 D-A59-ATHLOS — the word that names the unit

| | Option | What it buys | What it costs |
|---|---|---|---|
| **A** | **the unit keeps `job`; the athlos retires** | the cheapest possible fix for P8: one term for one thing, no rename anywhere | the name for *the doing* leaves the vocabulary, and 0021's line of thought (the work that outlives its doer) survives only as a paragraph inside ADR 0028's unit; 106 prose mentions swept; ADR 0021/D04–D07 amended |
| **B** | **the unit becomes `athlos`; `job` retires** | the doing gets the word that means a bounded, judged trial — and the merge becomes visible in the vocabulary: an athlos is now something akmon leases, isolates, parks and resumes | 732 renames (535 in code, 28 in shipped prose), `jobs/` and `JOB.md` renamed, 15 park scenarios renamed, the plan's line format re-labelled, one migration release with a compatibility read for kits written before it |

**Recommended: B.** The cost is one migration release over a concentrated surface — four code files,
one config, fifteen scenario files, the shipped prose — which this project has done before
(ADR 0008's own on-disk rename is tracked as one migration release). The gain is that the vocabulary
says what it means: the rung is *the doing, bounded and judged*, and it is also *the thing akmon can
run in parallel* — the owner's own goal (P9). Option A is the honest fallback if the owner does not
want a release.

### 6.2 D-A59-PIECE — the word that names the piece of work

The two readings of *ergon* (§4) decide this code, so the options are stated with the reading they
follow from.

| | Option | What it buys | What it costs |
|---|---|---|---|
| **A** | **`kit` stays** — the reading in which *ergon* names the **layer** | nothing moves; the tree keeps its word for the folder and the reservoir's word stays the home of the kits | the ADRs' own words name the same thing twice ("one folder per piece of work, named *ergon*" against D02's "A **kit** is the one folder…"), and the piece of work keeps a plain English word while its unit takes a Greek one |
| **B** | **`kit` becomes `ergon`** — the reading in which *ergon* names the **work** | the tree says the ADRs' word for the thing it names; one word per member, and the layer's path already reads "the home of ergons" | 1001 renames (740 in code), the helper's API names (`list_kits` → `list_ergons`, `kit_state` → `ergon_state`), 24 occurrences in the shipped prose, and one migration release |

**Recommended: A, for now — with the reading stated, not settled.** The quoted texts lean to the
second reading (*ergon* names the work), and under it option B is the one that matches the ADRs; but
the first reading is not contradicted by any line, and option A is free. The owner takes the reading
first and the word second; both are in the materials folder (Idea 3, with the sources), and the codes
stay open until then.

### 6.3 D-A59-KEY — how the unit is keyed

| | Option | What it buys | What it costs |
|---|---|---|---|
| **A** | **0028's key alone** — id `<kit-id>.<n>`, a `tasks:` field, the zone as a property of a step's fan-out | nothing changes in the formats; the zone stays a frame of the fan-out (P4) | 0021's per-zone acceptance condition is lost: a unit's zone is no longer a thing with its own condition |
| **B** | **0021's key alone** — the pair (task id, zone) | the unit is named by what it does | no id, no place in the plan; the roadmap's `after` edges, the worktree's folder name and the lease have nothing to read — the tree's formats would all have to be rebuilt |
| **C** | **both, split** — the id stays `<kit-id>.<n>`; the unit's line gains a `zone:` field beside `tasks:` | 0028's formats stay; 0021's content survives: one unit per (task, zone), each with its own acceptance condition | one field added to the plan's line format (`read_plan` and its twin, the scenarios, the roadmap's parsing) |

**Recommended: C.** The id is a place and the pair is content; the tree already has the id in five
places (the plan's lines, the folder, the worktree, the lease, the roadmap's edges) and has no
carrier for the pair. One field is the whole price of keeping 0021's clause.

### 6.4 D-A59-ARGOS — whether *argos* enters the vocabulary

**Recommended: no.** The slot it would fill — the machinery around a unit (the lease, the holder,
the branch, the worktree, the note) — is already named once per thing by plain words that are *file
names* in the tree (`HOLDER`, `PARK.md`, `RESUME.md`, the worktree's folder), and it is not a rung:
the ladder's rungs are the work's levels, and the zone (a frame) is the only non-work rung in it.
Against that, the word has two collisions (§4): the reservoir's own *Arges* is reserved for a smith
tier, and *argos* reads as Argo Workflows — the tool whose model ADR 0028/D08 borrowed.

## 7. The packages, with their prices

The four decisions combine into packages. The prices are whole-word occurrences in the tracked tree
(the method is at the top of this record); the code surface is concentrated in `tools/park/` and its
twin and their tests.

| Package | Vocabulary | Renames | Format changes | Consumer impact |
|---|---|---|---|---|
| **P1 — cheapest** | task, plan, **job**, step, zone; kit; layer `.ergon/` | 0 | none | none |
| **P2 — the doing gets a Greek word** (6.1 B + 6.2 A + 6.3 C) | task, plan, **athlos**, step, zone; kit | 732 + 106 | `jobs/` → ?, `JOB.md` → ?, the plan's line gains `zone:`, 15 scenario names | one release: the helper must still read `jobs/` for kits written before it, and say so |
| **P3 — the whole thing Greek** (6.1 B + 6.2 B + 6.3 C) | task, plan, **athlos**, step, zone; **ergon** | 732 + 106 + 1001 | as P2, plus the helper's API names (`list_kits` → `list_ergons`) | as P2, plus the piece's word in the shipped prose (24 occurrences); the layer's path stays — it already reads "the home of ergons" |
| **P4 — the owner's proposal literally** (unit = argos, piece = ergon) | task, plan, **argos**, step, zone; **ergon** | 732 + 106 + 1001 | as P3 | as P3 |
| **P5 — two rungs, one owner each** (the design's earlier shape) | task, plan, **job** → **athlos**, step, zone | 0 | none | none |
| **P6 — the athlos as a composite** (the piece *and* the unit under one name; Idea 2 in the materials) | one name over two levels | not priced — the shape of the composite is what has to be designed first | the plan's line format, the unit's own file, the lease's level | to be designed |

P5 is the shape this design carried before the owner's objection: the job is the slot, the athlos is
the labour it carries. It is the only package with no rename, and the only one that leaves two words
on one rung — which is what the owner rejected. P4 is the owner's proposal read literally; it is
P3 with the unit named *argos*, whose two collisions (§4) are the price of that one word. P6 is the
owner's other proposal — the athlos as a composite of the *ergon* level and the job inside it,
realized through a plan and steps; it is not priced, because what has to be designed first is the
shape of the composite (the materials folder, Idea 2).

**My recommendation: P2, with one reservation.** One rung, one word; the doing is named by the word
that means a bounded trial with a verdict; the container and the layer stay as they are, so no word
carries two levels; 0021's per-zone acceptance condition survives as a field; and the price is one
migration release over a surface of four code files, one config, fifteen scenarios and the shipped
prose. **The reservation:** the reservation is the *ergon* reading (§4, 6.2). If the owner reads
*ergon* as naming the work — as ADR 0008's amendment and ADR 0028's own status header say — then
P3 is the package that matches the ADRs, and P2 leaves the tree saying *kit* where the records say
*ergon*. The materials folder carries both readings with their sources; the reading is the owner's.

## 8. The owner's answers

The four codes were answered by the owner in session; each request is closed, and the decision is
owned by [ADR 0029](../adr/0029-ergon-athlos-step-one-method-of-work.md).

- **D-A59-ATHLOS → B.** The unit is the **athlos**; *job* retires. §6.1.
- **D-A59-PIECE → B.** *Ergon* is read as **the work**, not the layer: the piece of work is the
  **ergon**, *kit* is renamed, and the layer's path `<DEV>/.ergon/` stays — it already reads as the
  home of ergons. §6.2 had leant to A provisionally; the owner took the reading first, as it asked,
  and confirmed it in review: *ergon* names both the folder and the entity, and `.ergon/` needs no
  name of its own — it is the ergons, in the plural.
- **D-A59-KEY → C.** The id `<ergon-id>.<n>` stays, and the athlos's line gains a `zone:` field. §6.3.
- **D-A59-ARGOS → no.** *Argos* does not enter the vocabulary. §6.4.

Together they are **package P3** (§7): task, plan, **athlos**, step, zone; **ergon**. The migration is
one release — the helper and its twin, their tests, the plan's line format, the park scenarios and
the shipped prose — with a compatibility read for kits written before it and the legacy-kit branch
(B16) behind it.

## 9. Review materials

Every number in this record, re-derivable without this conversation. Read-only; run from the
repository root.

```bash
# 1. The two definitions this record merges.
sed -n '205,238p' docs/adr/0021-athlos-deferred-work-packages-and-handoff.md
sed -n '251,275p' docs/adr/0028-park-and-resume-the-kit-and-the-dotted-layer.md

# 2. The frozen frame word, and the reason.
grep -n "Why the frame word stays" -A 12 docs/adr/0021-athlos-deferred-work-packages-and-handoff.md

# 3. The reservoir and its amendments (the Greek register, and *ergon*).
sed -n '45,66p' docs/adr/0008-mythological-naming-aitna-akmon-kyklopes.md
sed -n '81,88p' docs/adr/0008-mythological-naming-aitna-akmon-kyklopes.md

# 4. The word counts behind every price in §5.1 and §7 (occurrences, whole word,
#    case-insensitive, over the tracked files of the six extensions).
for w in ergon argos argo arges athlos job kit holder lease step zone task plan; do
  all=$(git ls-files '*.md' '*.py' '*.mjs' '*.json' '*.toml' '*.js' | xargs grep -o -w -i "$w" | wc -l)
  md=$(git ls-files '*.md' | xargs grep -o -w -i "$w" | wc -l)
  code=$(git ls-files '*.py' '*.mjs' '*.json' '*.toml' '*.js' | xargs grep -o -w -i "$w" | wc -l)
  printf "%-8s all=%-6s md=%-6s code=%-6s\n" "$w" "$all" "$md" "$code"
done

# 5. Where the vocabulary lives in code (the surface a rename would touch).
git ls-files '*.py' '*.mjs' '*.json' '*.toml' '*.js' | xargs grep -o -w -i "job" \
  | cut -d: -f1 | sort | uniq -c | sort -rn
git ls-files '*.py' '*.mjs' '*.json' '*.toml' '*.js' | xargs grep -o -w -i "kit" \
  | cut -d: -f1 | sort | uniq -c | sort -rn

# 6. The scenarios whose names carry the words.
ls meta/conformance/scenarios/tools/ | grep -E "job|kit"

# 7. The shipped prose that carries the words (consumers read these).
for w in job kit; do
  printf "%-4s shipped=%s\n" "$w" \
    "$(git ls-files '*.md' | grep -vE '^(docs/|meta/)' | xargs grep -o -w -i "$w" | wc -l)"
done

# 8. That the athlos has no carrier in code.
git ls-files '*.py' '*.mjs' '*.json' '*.toml' '*.js' | xargs grep -o -w -i "athlos" | wc -l

# 9. The collisions of the candidate word with the reservoir and with Argo.
git ls-files '*.md' '*.py' '*.mjs' '*.json' '*.toml' '*.js' | xargs grep -n -w -i "argos\|argo\|arges"
```

The measured results of these commands, and the state of the tree they were run against, are in the
kit's `EVIDENCE.md` (the C188 kit — the layer's own path is not written here). Re-run them before
trusting any price here: the counts move as the tree moves.

The materials that carry the quoted texts, the current implementation and the ideas that are not
decided yet are in the kit's `materials/` folder — `sources.md`, `current-implementation.md`,
`ideas-and-alternatives.md`, `check_links.py`. The checker used for this record's links and anchors:

```bash
python3 <the C188 kit>/materials/check_links.py \
  docs/design/ergon-athlos-merge.md docs/design/park-and-resume.md meta/TASKS.md meta/conformance/README.md
```

### 9.1 The counts, re-run at the migration (C189)

Command 4 and command 7, run on the tree before the migration (the base commit) and on the tree with
it (tracked files plus the files the change adds). The first block is the price the record quoted;
the second is what the rename left. The words that remain are the readings of the gloss
([ADR 0029/D10](../adr/0029-ergon-athlos-step-one-method-of-work.md#d10--the-words-are-glossed-in-the-entry-file-with-the-words-a-user-may-say)),
the legacy forms the helper translates on read ([D12](../adr/0029-ergon-athlos-step-one-method-of-work.md#d12--the-old-layout-is-translated-on-read)),
the design documents and decision records that keep their history, and unrelated senses (a CI job,
`archetype: job`, "does its job").

| word | before: all / md / code / shipped md | after: all / md / code / shipped md |
|---|---|---|
| ergon | 988 / 553 / 435 / 16 | 2091 / 588 / 1503 / 49 |
| athlos | 370 / 370 / 0 / 2 | 1218 / 399 / 819 / 27 |
| job | 913 / 273 / 640 / 25 | 312 / 265 / 47 / 16 |
| kit | 1301 / 350 / 951 / 26 | 331 / 327 / 4 / 2 |
| step | 844 / 482 / 362 / 82 | 856 / 485 / 371 / 84 |
| zone | 666 / 202 / 464 / 24 | 694 / 203 / 491 / 25 |

Command 8 (the athlos in code) counts 0 before and 819 after. Command 6 finds no scenario name that
carries *job* or *kit*; 24 carry *athlos* or *ergon*. The *job* and *kit* left in the shipped prose
are the gloss itself, `archetype: job`, the guardrail's job-branch carve-out (C190) and unrelated
senses. The *kit* and *job* left in `md` are the design documents, the decision records and the
backlog, which keep the words of their time.

## 10. What this record does not settle

- Whether the athlos's *outliving* clause (0021/D04) becomes a property of the unit or stays a
  property of the kit's machinery — under P2 it is the second, and the wording belongs to the ADR.
- The plural and the folder names: 0021 fixed *aethla*; the folder that holds one unit and the file
  that holds its steps are the migration's business, not this record's.
- The lease's own name (`HOLDER`) and the holder's (507 uses) — untouched by every package here.
- What a consumer's existing kit does when the helper meets a `jobs/` folder after the rename — the
  compatibility read and the release note are the migration's business.

## 11. The chain designed through — one method of work

The owner's chain, `ergon → athlos → step`, is read here as **one method**: how akmon cuts work, how
a piece of it passes to another session, to a delegate or to another environment as an isolated
folder, and how the parties exchange what they know. The names are the working names the merge record started from; [ADR 0029](../adr/0029-ergon-athlos-step-one-method-of-work.md) D02 chose *ergon* and *athlos*, and every rule below survives a different word.

The harness facts this section leans on are cited by their `M<n>` row in
[`MEASUREMENTS.md`](../../meta/MEASUREMENTS.md); a mechanism with no row is marked **unmeasured**,
and nothing here claims parity between harnesses (AGENTS.md § Verification).

### 11.1 The principle: the record is in the folder, the harness is the transport

Every harness offers channels that look like a record — a native resume, a todo list, a plan file,
auto-memory, a subagent's return in context, a message to a running agent. They are bound to one
harness, often to one machine, and some to one session (ADR 0028's alternatives reject native
resume as the record for that reason). The method therefore splits every exchange in two:

- **the record** — what a later reader, of any harness, on any machine, needs to continue — lives in
  the ergon's folder, in files with one writer each;
- **the transport** — how a fact reaches the next reader fast — is whatever the harness gives, used
  where it exists and never relied on as the only copy.

So akmon does not compete with a harness mechanism; it says which file that mechanism's output must
land in before the work is parked. This is the rule every row of §11.6 applies.

### 11.2 Three fixed levels, each with a result of its own

The levels are self-similar: each has a SMART result (P11), one writer, a carrier, and a boundary
at which it can be handed over. What differs is the size of the hand-over.

| Level | Its result | Its writer | Its carrier | Realized through | Unit of transfer |
|---|---|---|---|---|---|
| **ergon** — a piece of work | the plan's criteria: the conjunction of its athla's results plus the integration condition none of them owns | the **head** — the session that holds the ergon (§11.4) | the folder: `PLAN.md`, `PARK.md`, `RESUME.md`, `material/`, `briefs/` | a **plan** | the whole folder — to another machine, environment or harness |
| **athlos** — a unit of the plan | its own acceptance condition, on its plan line (`result`, `tools/park/park.py:195`) and, under D-A59-KEY C, its zone | the athlos's **holder** — one session under the lease | its line in `PLAN.md`; its own file of steps; `HOLDER`; its branch and worktree | **steps** | the athlos — to a sibling session, a worktree, a background agent |
| **step** — a part done in order | a checkable done mark | the same holder | a line of the athlos's file | the holder's own turns, or a **zone** fanned out to `k_*` delegates | none — a step is not handed over; its zone's briefs are |

The zone is not a fourth level: it is the frame of one step's fan-out (ADR 0028/D08) and, read from
ADR 0021, the place that step's work lands. The two readings are one mechanism — the `[zone:LABEL]`
marker that the delegation ledger parses — so the merge keeps both texts true by saying the zone
**belongs to a step and is named in the athlos's line** (D-A59-KEY C).

**The composite athlos (Idea 2) is this table.** The owner's "the *ergon* level and inside it a
job, realized through a plan and steps" is the two upper rows: the ergon is realized through a plan,
the athlos through steps, and each has its own result. The composite needs no word spanning two
levels; it needs the levels to be self-similar, which they are.

**When an athlos outgrows its level.** An athlos whose steps need a plan of their own — parallel
parts, a result made of several results — is **promoted**: it becomes an ergon of its own, linked
from its parent's plan line (`after`/`tasks` already carry edges), and the parent's athlos keeps
only the integration step. The depth stays three. The alternative — an athlos nested in an athlos,
as in a workflow engine's nested templates — is §11.7's Alt-2.

### 11.3 The transfers

Six ways a piece of work changes hands. For each: what carries it, what the harness gives, what is
lost, and what is not built.

| # | Transfer | Record that carries it | Harness transport | What is lost | State in the tree |
|---|---|---|---|---|---|
| T1 | switch inside one session to another ergon or athlos | the lease and the park note | none needed | nothing | `pick` not built (the handler map, `tools/park/park.py:1971-1984`) |
| T2 | the next session, same machine | `PARK.md` + `RESUME.md` (`write_kit`, `park.py:1318`), then `unpark` | native resume — `--resume` keeps the session and its prompt (M82); `codex exec resume` keeps model and effort in the invoking cwd (M90, M92); SessionStart says `resume`/`compact` (M204, M66) | the transcript, live subagents — by design | built; the SessionStart hook does not call park, so the owner pastes the prompt (P3, C184, not built) |
| T3 | a sibling athlos in parallel | its plan line; the lease; its branch | the harness's own worktrees (§11.5, bottleneck N1) | nothing, if the result is carried to the branch | lookup built (`worktree_unit`, `park.py:1510`); no code creates a worktree |
| T4 | a delegate executes part of an athlos | the holder's brief out, the holder's write-back of the return | the harness's subagent call — Claude's Agent tool, Codex's `spawn_agent` (M29, M62); a background run (M190, M202); a message to a running agent (M213) | the delegate's context, unless the holder writes the return down | the return lands only in the head's context; the delegation log is Claude-only (`.claude/model-routing.log`) |
| T5 | another machine, environment or harness | the ergon's folder, exported as one bundle; the branch, if pushed | none that carries an ignored folder: a cloud session clones the repository, and the layer is ignored (**unmeasured** for every cloud harness) | the lease (left out on purpose), `.local/`, any absolute path in the folder | `park export` built (`park.py:1548`); no `import` (B10) |
| T6 | an external reader — a second opinion, a peer, a reviewer | `briefs/<purpose>/<n>/` — brief out, answers in, disposition | the second-opinion runner (ADR 0024) or the owner's hands | whatever the brief did not carry | the series is not built (B8); second opinions land in `.<provider>/second-opinion/` instead |

### 11.4 Who holds what — the head, the holder, the delegate

Three parties, three permissions — and the rule that resolves ADR 0021/D06 against ADR 0028/D08:

- **The head** holds the ergon. It writes `PLAN.md` — the only writer of it — decides the cut into
  athla, launches holders for parallel athla, merges their results into the plan's criteria, and
  talks to the owner. Today nothing marks the head; §11.8 N3 asks whether it needs a lease.
- **A holder** holds one athlos under the lease (`HOLDER`, `acquire_lease`, `park.py:867`). It
  writes the athlos's own file and note, and **fans out** steps to delegates inside zones. It does
  **not launch holders** — ADR 0021/D06's "a holder does not spawn" read precisely: it does not
  spawn *holders*. An athlos that needs a holder of its own is promoted (§11.2).
- **A delegate** (`k_*`) holds nothing. It gets a brief, returns a result, and its result is real
  only once the holder has written it into the athlos's file or its evidence.

**Can a subagent hold an athlos?** The owner wants work handed to subagents as well as to sessions.
Two readings: the subagent **holds** the lease, or it **executes** an athlos whose lease stays with
the session that launched it. The measurements favour the second today: a subagent starts without
akmon's SessionStart context (M37, M39, M41), an `ask` becomes a deny without an attended owner
(M191, M194), and a Claude subagent shares its parent's `session_id` (M36, M189), so a lease keyed
by session could not tell them apart. That is **D-A59-HOLD** (§11.9).

**Retirement and resumption are both true (ADR 0021/D05 against 0028/D09).** The *holder* that wrote
its note retires — its session is not woken; the *athlos* resumes under a new holder by lease
takeover (`hold --takeover`, `park.py:1923`), and the note keeps the former holder in its `sessions`.

### 11.5 Exchange between sessions and agents

A blackboard over files, with one writer per file, pull by the reader, and the harness's live
channels as a shortcut that never replaces the file.

```
                 owner ── codes, go-aheads ──▶ head
                   ▲                            │ writes PLAN.md (only writer)
                   │ Needed from you            ▼
               ┌── head ◀── athlos note, result, branch ──┐
   brief down  │                                          │  result up
               ▼                                          │
           holder (athlos, lease) ── brief ──▶ delegate (zone) ── return ──┘ (written by the holder)
               │
               └── briefs/<purpose>/<n>/ ──▶ external reader ── answers/ ──▶ disposition (head)
```

- **Down** — a brief: the ergon's plan line and the slice of material an athlos needs; the step and
  its zone label for a delegate. A brief is self-sufficient, because the reader may start cold (M37).
- **Up** — a result: a delegate's return, written by the holder into the athlos's file; an athlos's
  note, result field and branch, read by the head into the plan.
- **Sideways** — none directly. Sibling athla see each other only through `PLAN.md` (the `after`
  edges) and shared material, both written by the head. A live channel between them (a harness
  message, a shared agent team) may carry a heads-up; it never carries a fact the head has not
  written down.
- **Out** — a brief series, answered in files, disposed of by the head.

### 11.6 The method laid on the harnesses' own mechanisms

Each row: the harness mechanism, where it sits in the method, and whether akmon **uses** it as
transport, **refines** it (keeps it and says where its output lands), or **does not use** it — with
the evidence.

| Harness mechanism | Level | Stance | What akmon adds or why not | Evidence |
|---|---|---|---|---|
| a session and its native resume | athlos holder | use as transport | the note is the record; native resume is the fast path when the same harness on the same machine resumes the same athlos | M82, M90, M92 |
| SessionStart `source` (`startup`/`resume`/`compact`/`clear`) | athlos holder | use | the return digest after compaction; the trigger for an unpark offer | M204, M66; automatic compaction fires `PreCompact` → `SessionStart` `compact` → `PostCompact` (M218) |
| the subagent call (Agent tool, `spawn_agent`) | zone, step | use | the brief carries the rules the delegate needs; the holder writes the return down | M26, M37, M41, M62 |
| a background subagent; a message to a running one | athlos executor (D-A59-HOLD B) | probe first | would let a session hand a whole athlos to an agent it can steer | M190, M202; a message reaches a running subagent (M213); a subagent can launch one (M212) |
| the harness's own worktrees — Claude's under `.claude/worktrees/<name>`, Codex's under `~/.codex/worktrees/<hash>/<repo>` | athlos isolation | refine | akmon's lookup reads only `.worktrees/<id>-<name>.<n>` (`park.py:1510`, ADR 0028/D10–D11); it should read the athlos from git and the lease and note it already writes (§11.10 W1), so a harness-made worktree is an athlos's worktree | M210 (Claude: base at the remote's branch), M220 (Codex `--worktree`: base at the local `HEAD`) |
| the harness's todo or task list | step | refine | where the harness offers one, the live view of an athlos's steps, mirrored into the athlos's file at park; a current Claude model gets **no todo tool by default**, so the athlos's file is the only list there is | M214, M215 |
| plan mode | ergon plan drafting | use where interactive | the drafted plan is written to `PLAN.md` by the head | M64 (hidden under `-p`); interactive **unmeasured** |
| `AGENTS.md` / `CLAUDE.md`, auto-memory | above the ergon | do not use for work state | cross-ergon knowledge, not one ergon's state; Codex does not expand nested imports | M81, M89, M40 |
| hooks: Stop, SubagentStop, PreCompact | athlos, zone | refine | Stop already gates; SubagentStop carries the delegate's final text (`last_assistant_message`) and can append it to the athlos's evidence — the up-channel written by a machine; it must skip the compaction summarizer's unpaired stop | Stop M87, M150; SubagentStop M216, M219; nesting invisible to hooks M217; SubagentStop and PreCompact not wired |
| cloud and remote sessions | T5 | probe first | they clone the repository, so an ignored ergon does not reach them; it reaches them only through the explicit export (D-A59-CARRY → A, ADR 0029/D07) | M211 — `isolation: remote` stayed local here; a real cloud session **unmeasured** |

### 11.7 Alternatives to the whole chain

| | Alternative | What it buys | Why not, or not yet |
|---|---|---|---|
| Alt-1 | **flat: a task and a session**, no ergon — the harness's own task and resume | nothing to build; every harness's native path | no hand-over across harnesses or machines; no place for a plan over several parallel units — the problem ADR 0028 was written for |
| Alt-2 | **one recursive entity** — an athlos nested in an athlos to any depth, as nested templates in a workflow engine | one word; any depth | one word for two things in every sentence — the inverse of the owner's complaint (P8); the lease, the note and the transfer would each have to say which depth they mean |
| Alt-3 | **the harness's record** — native resume, todo list and memory as the state | no files of akmon's own | one harness, one machine; rejected by ADR 0028's alternatives |
| Alt-4 | **the ergon tracked in git**, on the athlos's branch or a side branch | it reaches any clone, cloud sessions included | the layer is ignored on purpose (ADR 0028/D01); work notes in a branch's history; a result must be cleaned of them before merge |
| **chosen** | **three fixed levels, the record in the ergon's folder, the harness as transport, promotion instead of nesting** | one word per level; any harness can carry any level; the composite is self-similarity, not a shared word | T5 is the explicit export (ADR 0029/D07), a directory for any other machine; several harness mechanisms are unmeasured (§11.6) |

### 11.8 Bottlenecks

- **N1 — the worktree path.** The harnesses make worktrees in their own places; akmon recognizes
  only its own. Left as it is, an athlos run in a harness-made worktree is invisible to `active_unit`
  (`park.py:1524`), and the method goes against the harness. → **D-A59-WORKTREE**.
- **N2 — the folder does not travel by git.** T5 copies by hand, and a cloud session cannot read an
  ignored path at all. Absolute paths written into a kit break it on the next machine — this record's
  own kit carried three. → **D-A59-CARRY**, and a portability check: no absolute path, no `.local/`
  reference, in an exported ergon.
- **N3 — the ergon has no holder.** `PLAN.md` has no writer in code (`parse_plan`, `park.py:1027`, only
  reads), and two sessions can both act as head. Either the head takes a lease on the ergon too, or
  the single-writer rule stays a convention. → **accepted (§11.12):** `PLAN.md` is changed through a
  helper command that checks the ergon's lease (C192).
- **N4 — two machines, two leases.** A lease lives in the ignored layer; a copy on another machine
  is stale at once (`lease_is_stale`, `park.py:857`), and the two machines never see each other's
  lease. Only a shared place — git, or the owner — can prevent double holding.
- **N5 — the up-channel is in context.** A delegate's return exists only in the holder's context until
  someone writes it; a compaction or a crash loses it. SubagentStop carries the delegate's final text
  (M216), so a hook can write it down (§11.6) — on Claude; Codex's equivalent is not measured.
- **N6 — the results do not add up by themselves.** The ergon's criteria and the athla's results are
  two carriers (P11); nothing checks that the athla cover the criteria. A check — every criterion
  names the athlos that meets it, or is the head's integration step — would close it. →
  **accepted (§11.12):** the check runs when the ergon is closed (C193).
- **N7 — the return after compaction** rested on an unmeasured event; M218 measured it on Claude
  (automatic compaction → SessionStart `compact`), so P3 (C184) is unblocked there. Codex's automatic
  case stays unmeasured (M8, M52).
- **N8 — cost.** A fan-out multiplies tokens: five Codex children added 1,112,481 (M177). A brief that
  carries only the slice is also the cheaper brief.
- **N9 — double bookkeeping.** A harness todo list and the athlos's steps drift unless the mirror rule
  of §11.6 holds at every park; on a current Claude model there is no todo list to drift (M214).
- **N10 — the two ADRs still disagree** on the zone, spawning, retirement, the place of a deferral and
  when the lease is taken (ADR 0021/D02, D04–D06 against ADR 0028/D08, D09, D12; and the code releases
  the lease on `write`, `park.py:1865`, where D09 says the first write acquires it). §11.2 and §11.4
  propose a reading for the first three; the last two are the ADR's to settle.

### 11.9 The codes this section adds, and the owner's answers

- **D-A59-DEPTH → A.** Three fixed levels; an athlos that needs a plan of its own is promoted to an
  ergon (§11.2).
- **D-A59-HOLD → A, with the owner's precision.** Only a session holds a lease. The common case is
  **sequential**: the orchestrating session is the head of the ergon and, in turn, the holder of one
  athlos after another — it holds two levels at once, and moving to the next athlos is a pick (T1).
  A subagent may execute a whole athlos under its launcher's lease; **when** to hand an athlos to a
  subagent rather than do it in the session is a task of its own (A80), not settled here.
- **D-A59-WORKTREE → A, to be designed further** — the method follows the harness's worktrees and
  does not make its own beside them where the harness has them. The design is §11.10.
- **D-A59-CARRY → A.** An ergon reaches another environment only by an **explicit export**; *park* is
  local and never transfers. The export gathers the work's changes as well as its folder (§11.10).
- **D-A59-RECORD → accepted.** The record is in the ergon's folder; the harness is the transport
  (§11.1).

**The probes** were run in session; their rows are listed in §11.11.

### 11.10 Worktrees and the export — an overlay on git's worktrees

The owner's rule for this section: the harness's worktree model stays as it is, and akmon adds the
least on top of it; where a harness has no worktrees, akmon uses one of its own of the same shape;
the only thing built over the worktrees is the export; and what is built is code, not prose
(ADR 0029/D08).

**What the harnesses do** (§11.11). Claude Code makes an agent's isolated worktree at
`<checkout>/.claude/worktrees/agent-<agent-id>` on a branch `worktree-agent-<agent-id>`, locked,
and removes it when the agent changed nothing; a session started with a worktree name lands in
`.claude/worktrees/<name>` on `worktree-<name>`. Its base was the remote's default branch, not the
local `HEAD` (M210). Codex's `--worktree` keeps its worktrees under `$CODEX_HOME/worktrees/<hash>/<repo>`,
on a **detached** `HEAD` at the local `HEAD`, and leaves them after the session (M220). **Every one
of them is a plain git worktree:** `git worktree list --porcelain` names each, its `HEAD`, its branch
or `detached`, and whether it is locked, and all of them share the checkout's common directory, so
the ergon's folder — resolved through it (`common/project_root.py:177`, `:228`) — is visible from
each. akmon therefore reads **git**, never a harness's path layout.

**W1 — the binding is read, not added.** akmon already writes the two facts a binding needs: the
lease names its holder's worktree (`HOLDER`'s `worktree` field, `tools/park/park.py:292`) and the
note records the branch and the last revisions, read from git (`write_kit`, `park.py:1342`). The
session's active athlos is found, in order:

1. the live lease whose `worktree` is the session's git top level;
2. the athlos whose latest note's `branch` is this worktree's branch, when that is not the default
   branch;
3. none — the session picks.

The one change is that the lease's `worktree` becomes `git rev-parse --show-toplevel` rather than
the current directory. Nothing new enters the note — the `worktree:` and `base:` fields of this
section's earlier draft are dropped — and the folder-name rule of ADR 0028/D10 retires: akmon's own
worktrees bind the same way, because `hold` takes the lease inside them. *Rejected:* a marker file
in the worktree (every `git status` shows it); a path pattern per harness (it moves with every
harness release).

**W2 — the base is computed, not recorded.** At `hold`, the helper runs
`git merge-base --is-ancestor <head's HEAD> HEAD`, where the head's `HEAD` is the main worktree's, the
first entry of `git worktree list`. If it fails, `hold` says so in one line naming both revisions —
the head's unpushed revisions are missing from the athlos's tree (M210) — and the holder rebases
onto them before its first step. Nothing is stored.

**W3 — akmon's own worktree, of the same shape.** Where the harness has no worktrees, `hold
--worktree` runs `git worktree add <checkout>/.worktrees/<ergon-id>-<name>.<n> -b <branch> <head's
HEAD>` — the branch from ADR 0028/D04's namespace, the base stated rather than defaulted — and then
binds by W1 like any other. The lifecycle is git's and the harness's: akmon removes no worktree, its
own included; closing an athlos prints the `git worktree remove` line when the result is carried and
the tree is clean, and the owner runs it (ADR 0028/D11).

**W4 — the export, as a command contract.** `park export <ergon-id> --out <dir>` writes one
directory; `park import <dir>` reads it. Everything in it is produced by git or by the helper — no
step is left to a reader of this page.

| Entry | Produced by | Notes |
|---|---|---|
| `ergon/` | the helper: the folder without `HOLDER` and scratch | the record (§11.1) |
| `<athlos-id>.bundle` | `git bundle create … <branch> --not --remotes` | only revisions no remote has; absent when there are none; branches are local and publishing them is the owner's |
| `<athlos-id>.patch` | `git diff --binary HEAD` in the athlos's worktree | uncommitted changes, deletions and binaries included; a consumer's agent does not record history |
| `<athlos-id>.untracked.tar` | `git ls-files --others --exclude-standard -z` → tar | untracked files the ignore rules let through |
| `manifest.json` | the helper, from git | the ergon id, the remote's URL, per athlos its branch, head revision and which entries exist; the import checks it before it writes anything |

Before it writes, the export runs the **portability check** and fails in one line on the first
offence: an absolute path of this machine in the folder's text, a reference into `.local/`, a
secret-shaped file. The **import** verifies each bundle (`git bundle verify`), fetches it into its
branch — refusing a branch that exists and is not an ancestor, so a round trip back is a
fast-forward — copies `ergon/` into the layer, refusing an ergon already there, and keeps the patch
and the untracked archive in the athlos's folder until the first `hold` in a worktree on that branch
applies them (`git apply --binary`, then the archive). The import makes no worktree: the receiving
harness or W3 does, and W1 binds it. Leases start absent. Not carried, by design: the transcript,
live subagents, leases, harness session ids.

Uncommitted work travels as a diff and an archive, not as a snapshot object put in the bundle under
a private ref: the snapshot would be one git object written outside a worktree, which ADR 0029/D09
leaves to the owner — and the guard already reads `git commit-tree` that way (in this session it
denied a scratch probe built so).

**W5 — working on the current branch, when no worktree is made.** An athlos runs in the checkout the
session is in, on its current branch, in three cases: the task is simple; the owner says so in so
many words; or no worktree can be made from the right base — the base the work needs is not yet
committed (the owner's work staged in the main checkout is not in any `HEAD` a worktree could start
from), or the harness and W3 cannot make one. Every prohibition stands there: the checkout is the
owner's, so the agent stages nothing, commits nothing and writes no other history (ADR 0029/D09);
the owner reviews and commits. The active athlos is then the pick in that checkout (ADR 0028/D10),
and the lease's `worktree` is that checkout's top level, so a second session that wants the same
athlos meets the lease as usual. This is the fallback, not a second method: once the base is
committed, the next athlos goes back to a worktree. *Owner's word (C194 session).*

**What stays prose.** ADR 0029 says what and why; this section is the design until C190 and C191
build it. Once built, the code and its tests and scenarios are the contract, and this section
shrinks to a pointer at them; the shipped skills name the command, never its steps (D08).

**Left beside this section** — the owner's answers to its requests are in §11.12:

- a detached `HEAD` (Codex, M220) — answered: `hold` makes a branch;
- what the source does after an export — answered: its athla are marked `exported`;
- whether a harness can make its worktree **on an existing branch** — the import relies on that or on
  W3; unmeasured, a probe inside C191;
- a subagent that executes an athlos in its own worktree (A80): the lease is its launcher's, so the
  binding must be written from the subagent's return — whether that return names the worktree and
  the branch is unmeasured;
- the cost of the twin: the export and the import are written twice, in Python and JavaScript
  (ADR 0020).

### 11.11 What the probes measured

Rows added to [`MEASUREMENTS.md`](../../meta/MEASUREMENTS.md) for this section (ids in §11.6 cite
them):

| Row | What it settled | Where it lands |
|---|---|---|
| M210 | Claude's agent worktree: `.claude/worktrees/agent-<id>`, branch `worktree-agent-<id>`, base at the remote's branch, removed when unchanged | W1, W2 |
| M211 | `isolation: remote` stayed local here; a cloud session's view of an ignored path is still unmeasured | T5, C191 |
| M212 | a subagent can launch a subagent — 0021/D06 is a rule, not a limit | §11.4, A80 |
| M213 | a message reaches a running subagent at its next tool round | T4, A80 |
| M214 | no todo tool for a current Claude model by default | §11.6, N9 |
| M215 | the task-list payloads, where the tools are on | §11.6 |
| M216 | SubagentStop carries the delegate's final text and its transcript path | N5, §11.6 |
| M217 | nesting is invisible in hook payloads | A80 |
| M218 | automatic compaction → `PreCompact` → SessionStart `compact` → `PostCompact` | N7, C184 |
| M219 | the compaction summarizer's unpaired SubagentStop | §11.6 |
| M220 | Codex's `--worktree`: `$CODEX_HOME/worktrees/<hash>/<repo>`, base at the local `HEAD`, left after exit | W1, W2 |

Still unmeasured: a real cloud session (T5), Codex's automatic compaction and its subagent-stop
payload, and how a session started *by the owner* in a Claude worktree reports itself.

### 11.12 The requests §11.10 left, and the owner's answers

All answered by the owner in session, each by the recommendation unless said otherwise.

- **The zone stays as it was** — a field of the athlos's line and the label of one step's fan-out,
  not a level between the athlos and its steps (ADR 0029/D03, 0021/D04). The chain is
  `task → ergon : plan → athlos [zone] → step`.
- **D-C190-DETACHED → A.** `hold` on a detached `HEAD` makes a branch there in ADR 0028/D04's
  namespace (`git switch -c`); W1 and W4 then hold unchanged for every harness (C190).
- **D-C191-SOURCE → A.** The export marks each athlos `exported` in its note, and `hold` on the
  source refuses it without `--takeover` (C191).
- **D-C191-CLOUD → dropped.** A cloud session is not a separate case: the export is a directory
  for another machine, wherever that machine is, and carrying it is the owner's. No probe is owed.
- **D-COMMIT-SCOPE → the owner's precision, ADR 0029/D09.** The main checkout is the owner's: an
  agent changes no history there, on any branch, and writes no git object or ref outside a
  worktree, in no scratch repository either. Inside a worktree — one it made (W3) or one the harness
  made for its athlos — it commits on that worktree's branch and may bring other branches or
  worktrees into it, never carry it out; it may propose carrying the worktree into the owner's
  branch, and the owner does it. The guard and the shipped carve-out change with C190.
- **N3 → accepted.** `PLAN.md` is changed through a helper command that checks the ergon's lease
  (C192).
- **N6 → accepted.** Every criterion of the plan names the athlos that meets it or is marked the
  head's integration step; closing the ergon checks it and names an uncovered criterion in one line
  (C193).

## 12. The vocabulary, measured

The owner asked two things of the words. First, whether replacing the everyday words — handoff,
checkpoint, kit, job — by *ergon*, *athlos* and *step* costs an agent work: extra steps, questions
back, a detour into the documentation. Second, whether akmon would do better to translate its names
or drop them for standard terms: efficiency is akmon's first requirement, and a word chosen for its
beauty must not cost work; a precise word, on the other hand, says more exactly what is done and is
found faster. C194 measured both on the lightest model of each route — Claude `haiku`, Codex
`gpt-5.6-luna`, Qwen `qwen3.8-flash-next` — over one small fixture written in several vocabularies,
with and without its definitions: 486 headless runs ([M221](../../meta/MEASUREMENTS.md), M222, M223;
the fixture, the runner and the per-run results are C194's local materials, not part of the tree).

### 12.1 What was measured

Functional score (right in substance, file format aside), mean tool calls, median tokens:

| Vocabulary and carrier | Claude `haiku` | Codex `gpt-5.6-luna` | Qwen |
|---|---|---|---|
| ergon/athlos/step, method document | 12/12 · 5.0 · 81k | 12/12 · 4.7 · 195k | 12/12 · 6.8 · 190k |
| kit/job/handoff, method document | 12/12 · 5.6 · 91k | 12/12 · 4.7 · 192k | 12/12 · 7.9 · 265k |
| everyday prompt over the design's words | 12/12 · 5.7 · 92k | 12/12 · 4.9 · 197k | 12/12 · 7.0 · 224k |
| ergon/athlos/step, no definition | 18/18 · 7.8 · 103k | 16/18 · 6.3 · 247k | 18/18 · 8.3 · 294k |
| kit/job/handoff, no definition | 17/18 · 7.5 · 110k | 15/18 · 5.6 · 223k | 18/18 · 8.2 · 261k |
| epic/task/handoff, method document | 15/18 · 5.4 · 72k | 17/18 · 4.4 · 161k | 18/18 · 8.4 · 256k |
| epic/task/handoff, no definition | 15/18 · 7.7 · 74k | 15/18 · 5.3 · 178k | 18/18 · 9.1 · 307k |
| ergon/athlos/step, one-line gloss in `AGENTS.md` only | 18/18 · 4.4 · 81k | 18/18 · 4.7 · 162k | 18/18 · 7.8 · 263k |

The first three rows ran four tasks, the rest six (two harder ones added: park the unit in progress
without its id, and define the words). No run asked back before acting.

**Five findings.**

1. **The Greek words cost nothing measurable.** With a definition near them, the design's words,
   the everyday words and an everyday prompt over the design's files take the same tool calls
   within noise on every route. Without one, *ergon*, *athlos* and *step* were read from the
   folders and defined correctly in 9/9 runs; Codex twice called *kit* "not defined in this
   project's files".
2. **The standard words collide with the backlog.** Asked to add a unit "for task C14", the
   epic/task fixture took C14 as the new unit's own id, or wrote the epic into the `tasks:` field,
   in 10 of 18 runs (Claude 6/6, Codex 4/6, Qwen 0/6) — with its definition present as well as
   without. Over the 63 runs of the same task in every other vocabulary it happened once. In akmon
   *task* already names the backlog row (`C194`); a unit called *task* inside a plan whose lines
   carry `tasks:` gives one word two referents, and the light models resolve it wrongly.
3. **A missing definition costs about 1.5× the tool calls**, in every vocabulary, and lets format
   drift: unit ids dropped, a unit file added beside the plan line, note sections left out.
4. **The word steers placement where nothing else fixes it.** Without a definition, "park the
   athlos" put the note in the unit's folder in 9/9 runs; "write a handoff" or "a checkpoint" put
   it at the level of the piece of work in 17 of 27. With any definition, every note sat in the
   unit's folder.
5. **A one-sentence gloss in the entry file is the cheapest carrier that is fully right**: 54/54
   functional, at about the tool calls of the full method document, and the words defined in
   0.3–1 tool calls on Claude and Codex. It carries meaning, not format: its strict misses are the
   unit id and the note's sections, which only the code or the method document fixes.

### 12.2 The three ways to name the work, against the measurement

**Keep the design's names (ADR 0029/D02) — as is.**
- For: no measured cost on any route; one referent per word, so no collision with the backlog's
  *task* or a harness's *handoff*; the names are searchable (`athlos` finds only the method); the
  word itself places the note correctly when the definition is missing (finding 4).
- Against: a reader with no definition pays the 1.5× of finding 3, as with any word; a human new to
  the project meets three unfamiliar words.

**Translate the names into plain words (kit/job/handoff, or similar).**
- For: a human reads them without a gloss.
- Against: no saving measured — the same tool calls with a definition, and without one a model may
  still call *kit* undefined (finding 1); *handoff* and *checkpoint* steer the note to the wrong
  level (finding 4); plain words are common in code and prose, so a search for them finds noise;
  the words would change while ADR 0029, the tool and the plans already carry the design's.

**Standard project terms (epic/task/step/handoff).**
- For: the most familiar to a human and to a model's training.
- Against: the only arm that broke the substance of a task, 10 of 18 runs, because *task* is
  already the backlog's word (finding 2); renaming the backlog's *task* instead would spread the
  change to every project akmon serves.

**What the measurement settles and what it does not.** Efficiency is not decided by the words: it is
decided by whether a definition is one hop from the entry file, and by whether format and placement
are carried by code (ADR 0029/D08). Clarity is decided by one referent per word, and there the
design's names win over both alternatives. The beauty of the words neither helps nor costs.

### 12.3 For the design

- **D02's words stand** on M221–M223.
- **Add the gloss** — accepted as [ADR 0029/D10](../adr/0029-ergon-athlos-step-one-method-of-work.md#d10--the-words-are-glossed-in-the-entry-file-with-the-words-a-user-may-say)
  (D-C194-GLOSS): the GL fixture's sentence, widened by the owner with the words a user may say
  instead (epic, kit, work package, job, handoff, checkpoint, check off) and with *task* named as
  ambiguous, goes into the block C189 ships and into akmon's own, beside the pointer to the method.
  The widened sentence is not measured yet; C189 re-runs the GL arm with it.
- **Format and placement stay in code** (D08): the park tool writes the note's sections and its
  place, and `park` adds the plan line with its id. The measurement shows what an agent left to
  the prose gets wrong — exactly those two.
- **Plain words in a prompt need no mapping layer**: "checkpoint for job C12.2" over the design's
  files wrote `PARK.md` in the athlos's folder in 9/9 runs across the three routes.

**What it does not say.**
- n = 3 per cell: a difference of one tool call is noise.
- One small fixture: a long method document, a large backlog or a session deep in other work is
  not measured.
- One standard set and one colliding wording were tried; story/ticket/milestone were not.
- Qwen did not separate the vocabularies at all, and costs the most tokens in every arm.
