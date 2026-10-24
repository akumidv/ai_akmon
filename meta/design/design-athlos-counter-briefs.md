# Design — the design athlos and its counter-briefs

Living design for ADR [0021/D04](../decisions/0021-athlos-deferred-work-packages-and-handoff.md#d04--an-athlos-is-the-labor-not-its-frame-and-not-its-doer):
the bounded labor an approved plan is cut into, and the adversarial pair the orchestrator may call
in on a **design** athlos. Tasks [A46](../TASKS.md) (this design, to an accepted block) and
[A47](../TASKS.md) (the nesting mechanism). Not accepted as a rule anywhere until the owner answers
**D-ADJ-TRIGGER** and **D-MIDDLE-LAYER**.

## 1. What each member is

| member | what it is | already named by |
|---|---|---|
| **zone** | the frame — where the work lands | `routing.parse_zone`, `[zone:LABEL]`, `coverage_map` |
| **athlos** | the labor — a bounded piece with an acceptance condition | 0021/D04 |
| **Kyklops** | the doer — the `k_*` delegate executing one assignment | 0008, `agents.json` |
| **orchestrator** | the head session, which **is the judge** | `MODEL.md` § tiers |

Three members, one relation: *a Kyklops executes an athlos inside a zone; the orchestrator holds the
athloi of its session and judges them.* No fourth entity is introduced, and the judge is not one of
the briefs — that is the owner's ruling and it is what keeps the pair cheap to reason about: two
opposed arguments, one judge who already exists.

## 2. The pair, and what each brief owes

Both briefs read **one gate-pack** — the same material, assembled once by the existing
`tools/model_routing/gate_pack.py` path — so they cannot differ by evidence, only by stance:

- **advocate** — the strongest case that the chosen option is right *and* that the rejected options
  were rightly rejected. Its test: name what would have to be true for the rejection to be wrong.
- **antagonist** — the strongest case against, aimed at the load-bearing premise rather than at
  style. Its test: name one cheap check that would overturn it.

Rules the pair inherits, not re-decides here:

- **Neither decides.** Both return positions with `file:line` evidence; the orchestrator judges, and
  an owner decision stays an owner decision (D2). A brief's text is never acceptance.
- **Fresh context each.** A brief that read the producing conversation is not an opposing view, it is
  the same view arguing with itself. This is the same independence 0004 bought by routing the auditor
  off the orchestrator's model, and the same reason [0005](../decisions/0005-synthesizer-gate-audit-and-role-routing.md)
  audits a result pack rather than a transcript.
- **Dissents that are not answers.** A brief that finds the pack missing the evidence its question
  needs says so and stops; manufacturing a position over an empty pack is the failure C25's gate
  exists to catch.
- **Model diversity where it is real.** The pair runs on the routed rung, not on a name; if both land
  on one alias, the record must say the diversity was not achieved rather than imply it.

## 3. Trigger — the open question, with its cost

The owner's direction: **not always — on design work, and asked of the owner first.** Measured cost
of one firing, from the registry and the current binding: two extra delegate calls at the `reasoner`
rung over one pack. So the ask is not politeness, it is a spend the owner authorises, and the notice
must state the spend it is asking for.

The shape, if accepted: a design athlos at its **plan check** (the pre-fan-out gate that already
fires when the decomposition names ≥2 zones) offers the owner the pair for the contested fork, with
the pack already assembled so the price of "yes" is one word. Two costs to say plainly:

- **Wall-clock.** Two sequential opposed briefs after a pack is ready delay the fan-out. Parallelism
  is what the athlos split buys; the pair costs time and spends it on quality, and the two must not be
  sold as the same gain.
- **Attention.** A24 already pushes the auditor toward every design. If both the auditor *and* the
  pair ask per design, the owner is asked at nearly every design gate — the alarm-fatigue failure
  D2-8's audit named. One ask that offers the pair *and* the audit as alternatives over the same pack
  is cheaper than two asks; whether to merge them is A24's call, not this design's.

## 4. What must be true before any of this can run

Not a wish list — the measured blockers, each with the number that shows it is open:

1. **Nesting is undecided** (**D-MIDDLE-LAYER**, A47). `MODEL.md` says orchestration is never
   delegated and [model-routing §13.3](model-routing.md) records a delegate with no `Task` tool that
   «cannot delegate at all»; yet in `tools/model_routing/agents.json` three of the six specs
   (`k_mechanic`, `k_validator`, `k_implementer`) carry `tools: null` = **all tools**, and
   `hooks/vocabulary.json` maps `Task`/`Agent` to the `subagent` capability. So the ones who could
   nest today are the mechanical doers, and the read-only ones who should not, cannot. Whichever way
   the owner decides, prose and caps must be moved **together** — this is the second-owner class C46
   exists to remove.
2. **A pair has no task kind.** `registry.json` `task_kinds` has thirteen rows, the closest being
   `design-fork`, `audit` and `independent-review`. Reusing `independent-review` for an *advocate*
   would corrupt it: that row means "check this independently", not "argue this case". A new row is a
   registry change (hash moves, local configs re-init once) and belongs in the same accepted block.
3. **`gate_pack` has no stance field.** It assembles material for a `--kind` of check; "argue for"
   and "argue against" over one pack is a new kind of request, in both implementations per ADR 0020,
   with its own corpus scenarios.
4. **Nothing here is measured as a quality gain.** No claim that opposed briefs raise alternative
   quality is asserted in this file — the method is borrowed from practice, not from akmon's evidence.
   The first accepted block should therefore carry its own falsifier, in A22's house shape: a bounded
   run on real design athla, scoring the options found *with* the pair against *without* it, and a
   stated margin under which the pair is dropped rather than kept on faith. A33's distortion register
   (CD1–CD5) is the place a found effect gets recorded, since an agent's own report of having been
   helped is the weakest available evidence.

## 5. Naming

`athlos` is taken from the athletic register, not the forge: 0008 §4 names the reservoir and asks
that future entities be named "from the same scene". This is a deliberate, stated widening — the word
was chosen because it carries an end and an adjudicator in its own root, which `zone` (406 live uses,
one of them a delegation-ledger **column**) and `k_*` (already the doer) cannot. `wave` was measured
and rejected: 44 live uses already mean "a batch of tasks in a plan" (`stage1-hardening-contracts`,
the A11 walkthrough), a different thing.

For the pair itself the design uses the plain English **advocate** / **antagonist** and deliberately
does not spend a reservoir name. Two reasons, both about future readers: the 0008 personal names
Brontes / Steropes / Arges are already assigned to **smith tiers**, so borrowing one would give a
name two owners; and a brief's job is legible from its word, which a mythonym is not. If the owner
wants mythonyms anyway, that is an amendment to 0008 §4, not a local choice here.
