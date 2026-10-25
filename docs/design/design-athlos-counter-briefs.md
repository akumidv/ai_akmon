# Design — the design athlos and its viewpoints

Living design for ADR [0021/D04](../adr/0021-athlos-deferred-work-packages-and-handoff.md#d04--an-athlos-is-the-labor-not-its-frame-and-not-its-doer):
the bounded labor an approved plan is cut into, and the **viewpoints** — fresh-context positions the
head session may call in over one gate-pack. Tasks [A46](../../meta/TASKS.md) (this design, to its pilot and
a rule) and [A47](../../meta/TASKS.md) (the prose-versus-caps gap); the wait-cost probe is [N15](../../meta/TASKS.md).
The shape — one mechanism, a catalog, an offered launch — is accepted as
[ADR 0021/D07](../adr/0021-athlos-deferred-work-packages-and-handoff.md#d07--viewpoints-one-mechanism-a-catalog-of-positions-one-control);
the thresholds and the catalog are not; the word *viewpoint* is the owner's choice. The file name
keeps the earlier "counter-briefs" so existing links hold.

## 1. What each member is

| member | what it is | already named by |
|---|---|---|
| **zone** | the frame — where the work lands | `routing.parse_zone`, `[zone:LABEL]`, `coverage_map` |
| **athlos** | the labor — a bounded piece with an acceptance condition | 0021/D04 |
| **Kyklops** | the doer — the `k_*` delegate executing one assignment | 0008, `agents.json` |
| **orchestrator** | the head session, which **is the judge** | `MODEL.md` § tiers |
| **viewpoint** | a position taken over one pack to test a result — an instrument of the judge | 0021/D07 |

Three members and an instrument, one relation: *a Kyklops executes an athlos inside a zone; the
orchestrator holds the athloi of its session and judges them, calling in viewpoints to test a result.*
The judge is never one of the viewpoints — that is the owner's ruling, and it keeps the arrangement
cheap to reason about: several opposed arguments, one judge who already exists.

Two families of holder must not be confused. A **zone lead** carries an athlos forward and, if it
may ever spawn, needs the right to (D06 gives it none today). A **viewpoint** only reads and argues; it
returns a position and spawns nothing, so no nesting question applies to it.

**Open, not decided:** under D06 no living lead holds the context of a zone, and the owner's pain —
several parallel sessions with the coordination on the owner — points one level higher, to a
**product-level lead** that keeps the roadmap context across sessions. Whether that is a holder, a
generated plan view ([A50](../../meta/TASKS.md)), or both waits on what [N15](../../meta/TASKS.md) shows a waiting
holder pays.

## 2. Viewpoints and the catalog

All viewpoints over one question read **one gate-pack** — assembled once by the existing
`tools/model_routing/gate_pack.py` path — so they differ by position, never by evidence. A viewpoint
begins as a prompt for a delegate ("you are the advocate of this decision; show what it is worth and
what changing it would cost"), and the catalog is collected from the start:

- **advocate** — the strongest case that the chosen option is right *and* that the rejected options
  were rightly rejected. Its test: name what would have to be true for the rejection to be wrong.
- **critic** — the strongest case against, aimed at the load-bearing premise rather than at style.
  Its test: name one cheap check that would overturn it.
- **review slices** — the same mechanism with a different question: security; reuse of other
  libraries and projects; and any further slice the review role carries.
- **usage patterns** — a client that proceeds strictly in order, one that interrupts and starts over,
  an attacker trying to break the result.

- **idea sources** — the generating kind of assignment ([D07](../adr/0021-athlos-deferred-work-packages-and-handoff.md#d07--viewpoints-one-mechanism-a-catalog-of-positions-one-control)):
  options drawn from the product's own history, from competing or analogous products, from public
  write-ups, or from a brainstorm whose output is filtered. Where the sources live is the
  [alternatives README](../../meta/reviews/alternatives/README.md). A viewpoint that tests a decision may also
  compare it with those alternatives.

The catalog is data and grows by use. A viewpoint may later become a pipeline or a subagent; that is not
decided here, and nothing below assumes it.

Rules the viewpoints inherit, not re-decide here:

- **None decides.** Every viewpoint returns positions with `file:line` evidence; the orchestrator
  judges, and an owner decision stays an owner decision (D2). A viewpoint's text is never acceptance.
- **Fresh context each.** A viewpoint that read the producing conversation is not an opposing view, it
  is the same view arguing with itself — the independence 0004 bought by routing the auditor off the
  orchestrator's model, and the reason [0005](../adr/0005-synthesizer-gate-audit-and-role-routing.md)
  audits a result pack rather than a transcript.
- **Independent of each other.** Contradicting views are the point, so viewpoints over one pack run in
  parallel, or in sequence without sight of earlier output.
- **Dissents that are not answers.** A viewpoint that finds the pack missing the evidence its question
  needs says so and stops; manufacturing a position over an empty pack is the failure C25's gate
  exists to catch.
- **Model diversity where it is real.** Viewpoints run on the routed rung, and may run on other
  vendors' harnesses; if two land on one alias, the record must say the diversity was not achieved
  rather than imply it.

## 3. Launch — the accepted shape and the open numbers

The owner's direction: the **explicit launch always exists**, and an **offer** appears when the role's
own result calls for it — not on a structural anchor, which measured silent here (C98: zero held turns
over 1,139 main-chain turns).

| role | offer the viewpoints when | otherwise |
|---|---|---|
| `architect` | arguments are weak or few, or the options are many and need pruning | the ordinary architect path — ideas came out fine, the owner does not come back |
| `review` | the same, over findings | the ordinary review path |
| `engineer` | never | — |

The offer is made to the owner **before** any spend, and states the spend: one delegate call per
viewpoint chosen. Viewpoints are launched by the head (D06). Two costs, plainly:

- **Wall-clock.** Viewpoints in parallel add the slowest one to the fan-out; in sequence they add all of
  them. Parallelism is what the athlos split buys, and viewpoints spend time on quality — the two must
  not be sold as the same gain.
- **Attention.** A24 pushes the auditor toward every design. If both the auditor *and* the viewpoints ask
  per design, the owner is asked at nearly every design gate — the alarm-fatigue failure D2-8's audit
  named. One ask that offers both over the same pack is cheaper than two; whether to merge them is
  A24's call.

**Open, and to be set by a pilot, not by argument:** what "weak", "few" and "many" mean in numbers.
A first reading is two signals — options with no `file:line` evidence, and the count of genuinely
different options — but the existing `architect_min_options` gate already shows how a count taken
from text behaves: it fires on any turn that lists options, including turns that only relay a
decision. The pilot calibrates against the falsifier in § 4.

## 4. What must be true before any of this can run

Not a wish list — the measured blockers, each with the number that shows it is open:

1. **The mechanism side of the nesting gap is open** (A47). Under D06 the head launches everything,
   so the prose stands; but in `tools/model_routing/agents.json` three of the six specs
   (`k_mechanic`, `k_validator`, `k_implementer`) still carry `tools: null` = **all tools**, and
   `hooks/vocabulary.json` maps `Task`/`Agent` to the `subagent` capability — so the mechanical doers
   could nest and the read-only ones cannot, against [model-routing §13.3](model-routing.md) and the
   `MODEL.md` row. Prose and caps must move **together** — the second-owner class C46 exists to
   remove, and C46's neutral-capability machinery is not in the tree.
2. **A viewpoint has no task kind.** `registry.json` `task_kinds` has thirteen rows, the closest being
   `design-fork`, `audit` and `independent-review`. Reusing `independent-review` would corrupt it: that
   row means "check this independently", not "argue this case". A new row is a registry change (hash
   moves, local configs re-init once) and belongs in the same accepted block.
3. **`gate_pack` has no viewpoint field.** It assembles material for a `--kind` of check; "argue from
   this position" over one pack is a new kind of request, in both implementations per ADR 0020, with
   its own corpus scenarios.
4. **Nothing here is measured as a quality gain.** The method is borrowed from practice, not from
   akmon's evidence, and the nearest local evidence is a warning: three fresh-context auditors scored
   recall 0.28 / 0.58 / 0.23 with false flags 0.22 / 0.44 / 0.22 and none met its thresholds, for want
   of the project's evidence map (A32-E1, M98). The first rule should therefore carry its own
   falsifier, in A22's house shape: a bounded run on real design athla, scoring the options found
   *with* viewpoints against *without*, and a stated margin under which viewpoints are dropped rather than
   kept on faith. A33's distortion register (CD1–CD5) is where a found effect is recorded, since an
   agent's own report of having been helped is the weakest available evidence.
5. **Who launches a viewpoint-running role is unmeasured.** A reviewer that asks the head to launch the
   viewpoints (option A of D06) keeps the head's context in play; a reviewer that launches them itself
   (option B) keeps the head's context clean but pays for the reviewer to wait. [N15](../../meta/TASKS.md)
   measures the wait; [N16](../../meta/TASKS.md) measures the quality, time and head-context comparison for
   review slices.

## 5. Naming

`athlos` is taken from the athletic register, not the forge: 0008 §4 names the reservoir and asks
that future entities be named "from the same scene". This is a deliberate, stated widening — the word
was chosen because it carries an end and an adjudicator in its own root, which `zone` (406 live uses,
one of them a delegation-ledger **column**) and `k_*` (already the doer) cannot. `wave` was measured
and rejected: 44 live uses already mean "a batch of tasks in a plan" (`stage1-hardening-contracts`,
the A11 walkthrough), a different thing.

The briefs themselves keep plain, legible names (`advocate`, `critic`), not a reserve name: the 0008
personal names Brontes / Steropes / Arges are assigned to **smith tiers**, so borrowing one would give
a name two owners. If the owner wants mythonyms anyway, that is an amendment to 0008 §4, not a local
choice here.
