# Design: stage 1 — deterministic hardening contracts (A12 locked)

> **Status: locked.** The register below is walked in full (F1–F22; F8–F22 decided), its
> clean-context coherence findings are repaired, and [D2-20](../D2_LEDGER.md) is Verified at
> `e89f3fe`. ADRs [0012](../decisions/0012-stage1-contracts-and-vocabulary.md) and
> [0013](../decisions/0013-hook-survivability-and-crash-posture.md) are Accepted. D2-23 remains
> the separate gate for C52's measured literals.
> Scope: plan items **P1.1–P1.7** plus the **P0.2 / P0.4 declarations** the stage-0 probes
> made fillable, plus the **tool-name half of [C46](../TASKS.md)**. The lock splits
> implementation per shape into **C51–C59** (+ C46; C60 carries the later cap reduction, outside
> this lock); the umbrella C40 is superseded and archived after D2-20 owner verification. Sources:
> [plan §Phase 0–1](../reviews/alternatives/plan-akmon-from-alternatives-20260718.md),
> [ADR 0010](../decisions/0010-alternatives-adoption-a11-verdicts.md),
> [N2 findings](../reviews/alternatives/n2-stage0-probes-inventory-20260807.md).
> The first slice of A12 locked earlier and separately:
> [ADR 0011](../decisions/0011-agent-name-notation-k-underscore.md) (agent-name notation).

## Frame

Stage 1 buys one property: **a violation of an akmon rule fails a check instead of degrading
to silence.** That is the failure class the whole C47–C50 repair wave just paid for — a wrong
payload key, a path predicate that never matched, a matcher that named one route three times
and the other not at all. Each was a rule akmon states and nothing verified.

So the yardstick for every **rule** below is not "is the rule written down" but **"what seeded
violation makes this check fail, and where is that test"**. A rule that cannot answer is not
in this lock. The unit is the rule and not the shape — **F13**, decided after the
A17(g) audit found the two readings disagreeing across this document; `## Acceptance` states the
consequence in full.

Two boundaries this proposal holds deliberately:

- **Declarations here, data later.** The capability matrix becomes a schema in A16. Stage 1
  writes its cells as prose and declares the seam, accepting a bounded duplication window
  rather than blocking on A16.
- **Advisory stays advisory.** Nothing here converts an advisory hook into enforcement.
  Existing deny decisions remain exact-route claims, with crash posture stated separately;
  stage 1's job is to make advisory behavior *observable*, not to claim a guarantee the
  harnesses do not give (see
  [codex-runtime-contract](codex-runtime-contract.md)).

## Owner walkthrough register

The draft remains unlocked until every material fork is walked, the resulting set is audited
for coherence, the decision set is recorded in ADR(s), and D2-20 is owner-verified.

| # | fork | owner choice | status |
|---|---|---|---|
| F1 | shared finding field vocabulary | **B — canonical `severity`; no `level` alias** | decided |
| F2 | machine-readable finding rendering | **C — schema in C51; public JSON output in C59** | decided |
| F3 | hook crash posture, including deny-class guards | **C — crash-open now; measured gate before deny-class fail-closed** | decided |
| F4 | Codex hook timeout | **C — N1 live probe gates C52 emission** | decided |
| F5 | hook timeout budget for Claude and a supported Codex route | **C — measurement-derived budgets by hook class** | decided |
| F6 | timeout support envelope for currently unbounded valid inputs | **C — bounded fast path; fail-visible/open oversize** | decided |
| F7 | invariant declaration owner and check direction | **B — stable policy IDs in prose and callable metadata; bidirectional** | decided |
| F8 | initial policy-ID and operational classification table | **six policy IDs + `session_start_result` operational; `role.declaration` gains guardrail prose; D2 coverage declared as the consumer's, defaulted narrow at a future `init`** | decided |
| F9 | version/changelog consistent-state repair | **`0.4.0.dev0` + `## Unreleased`, repaired inside C54; two literals joined by an equality check; PEP 440 non-final grammar; missing source and history gaps stay visible, not fatal** | decided |
| F10 | execution-ledger scope (§9) | **dispatch-only now; the completion half spawns its own probe ([N4](../TASKS.md))** | decided |
| F11 | does the acceptance yardstick admit an exemption class | **no — for an aggregating shape the seeded violation is *fidelity to its sources*** | decided |
| F12 | ADR shape for stage 1 | **two: contracts/vocabulary (F1, F2, F7, F8, the F14/F15/F17/F18/F19/F20/F21/F22 amendments, and the F11/F13 yardstick) separate from survivability/crash posture (F3–F6)** | decided |
| F13 | the seeding unit — a shape or a rule | **the independently violable rule; a rule whose seed needs unmeasured evidence is split, not waived** | decided |
| F14 | how `code` stability survives a removed check (§1) | **a retired-name record in `findings.py`; a live code that appears in it fails** | decided |
| F15 | what pins the F8 classification set (§3) | **a contract test binding the seven shipped callable classifications — six callable↔policy-ID pairs plus one operational assignment — a regression pin, not a join mechanism** | decided |
| F16 | what the runtime binary declaration is joined to (§7) | **two populations — generated wiring and akmon's own tooling — each compared against its own source, with modality declared and checked** | decided |
| F17 | how one generator declaration represents files it fully owns, structured files that cannot carry comments, and fields inside hand-owned files (§5) | **A — typed `PlannedFile` ownership modes: `bannered-file`, `structured-file`, and `field-owned`; no parallel exception or ownership list** | decided |
| F18 | how the always-loaded ratchet separates akmon-owned context from the whole consumer context (§6) | **A — two inclusive decimal line/byte caps: shipped ≤210 / 12,000 is a `self_ci` error; consumer total ≤460 / 25,000 is a `verify.py` warn whose strict-mode exit is non-zero** | decided |
| F19 | where the axis-complete vendor capability matrix lives (§7) | **A — shipped top-level `CAPABILITIES.md`; README keeps a claim-free delivery summary; A16 later replaces C57's prose cells with generated data** | decided |
| F20 | how C46 makes neutral and vendor tool-name ownership exhaustive (§8) | **A — one exact neutral vocabulary and agent population; one version-stamped vendor tool/matcher inventory consumed by frontmatter, hook generation and adapters; exact findings and isolated two-direction carrier checks** | decided |
| F21 | how C58 makes a dispatch ledger trustworthy within a bounded local-file contract (§9) | **A — observed Claude dispatch-request event; versioned seven-field records at one neutral path; one writer and two readers; serialized bounded append; explicit migration, failure and no-authenticity/no-rotation boundaries** | decided |
| F22 | what `akmon status` may observe and touch (§10) | **A — fresh `verify` then `sync --check` owner streams; D2/caps once through verify; read-only exact equality with no cache, direct re-read or persisted active-role fiction** | decided |

**What enters this register** (the counting rule the `F10+` placeholder lacked, locked with F10–F12):
a fork is registered when **all three** hold — it has two or more defensible answers; the answer
changes what a stage-1 task implements or what the lock claims; and it cannot be deferred into a
task without the lock asserting something unverified. Failing the first makes it a **repair**
([A17](../TASKS.md) (d) and (f)); failing the third makes it an **in-task decision** (C60's
relocation-vs-deletion, C57's git-dependency trigger); failing the second makes it **parked
elsewhere** (D1 mutable status levels, A16 matrix-as-data, N1/N5/N6 measurement, the public
`akmon status` option name). Measurement gates — the F4/F5/F6 literals — are not forks at all:
there is a number to obtain, not an answer to choose. Under this rule the register is **walked in
full**; the placeholder row is not "empty", it was three.

**F13 arrived from the A17(g) audit, and it is a fork by the rule above rather than a repair.**
The yardstick had no stated *unit*. `## Acceptance` bound the seed to a **shape** ("every shape
above ships with **a** test"); the Frame bound it to a **check** ("what seeded violation makes
*this check* fail"). The gap is not theoretical: §2 states four numbered rules, and two of them —
`utf-8-sig` decoding and `timeout` in the generated wiring — had no mutation, no expected failure
and no test anywhere in this document. Two defensible answers, each changing what five tasks
implement, neither deferrable without the lock claiming a coverage it does not have. **Owner
choice: the unit is the independently violable rule.** Rules that cannot fail separately may share
one seed; a rule that can be violated on its own carries its own; and where a seed needs evidence
that does not exist yet the rule is **split** rather than waived — the checkable part is checked
now and the remainder names its gate. **Rejected: per shape**, as written — the cheapest answer,
and it locks §2 with half its rules unverified, which is the exact defect this stage exists to
remove, sitting inside the stage's own acceptance criterion. **Rejected: per rule with a declared
exemption list** — visible holes beat hidden ones, but F11 has already ruled that *no exemption
class exists*, and a list of exemptions is that class under another name. Accepted cost: roughly
six to ten additional tests across the stage, and a boundary ("independently violable") that will
be argued at implementation time — argued, by standing rule, in favour of the separate seed,
because a redundant test is cheaper than an unnoticed rule.

**The yardstick governs claims presented as mechanically enforced.** A semantic or process-owned
obligation is not allowed to masquerade as a passing check: it must be labelled `review-owned` or
`process-owned`, state the mechanical subset that is tested, and state the residual cost. This is
accounting, not an exemption for a mechanical rule — every rule the lock calls checked still needs
its own seed. In §1 imperative mood and residual natural-language sentence boundaries are
review-owned, while presence and the bounded sentence-shape heuristic are mechanical; the manual
append to the F14 retired-code record is process-owned, while live reuse of an already recorded
code is mechanical.

**F14–F16 arrived the same way F13 did**, from the architect pass over D2-20's clause (d), and
each clears the counting rule above rather than being a repair: two defensible answers, a change
to what C51, C53 and C57 respectively implement, and a lock that would otherwise claim a coverage
it does not have. **F14** — `code` is "never reused after a check is removed", which a
duplicate-code seed cannot see, because two live checks never share the slug; the retired-name
record is the smallest thing that can. *Rejected: dropping the never-reused clause*, which is the
half a consumer greps for. Accepted cost, stated because it is real: the record is appended by
whoever deletes a check and nothing forces the append — a forgotten one restores today's state
rather than making it worse. **F15** — every §3 mutation is structural, so an ID renamed
consistently on both sides passes, and *unknown* has nothing to be unknown against because F7
rejects a central mapping constant; the pin is a test fixture, not a constant the checker consults,
so the join still runs prose→docstring and nothing stands between the two sides. *Rejected:
leaving the set unpinned*, which leaves F8's "C53 checks this set" as prose. Accepted cost: it is a
second list of the same seven callable classifications, and the difference from the registry F7
rejected has to be argued each time someone reads it. **F16** — `claude` and `codex` are invoked
by `sync` itself and
appear in no generated command, so a join reading only the emitted strings warns that the two
optional binaries §8 depends on are stale prose; the populations make the modality checkable
instead of prose. *Rejected: dropping the optional pair from the declaration*, which restores the
silence §7 exists to remove. Accepted cost: the second population's source is a declarative query
map from which akmon builds its own subprocess calls and which the checker also reads. That single
owner adds indirection and is weaker evidence than extracting the first population's literal
emitted strings, so the cost is named here rather than discovered later. **F14, F15, F17, F18,
F19, F20, F21 and F22 are
carried into [0012](../decisions/0012-stage1-contracts-and-vocabulary.md)** with the stable
contracts they amend;
**F16 stays here**, with F9 and F10, because neither ADR carries §7's runtime declaration.

**F17 arrived from the final clean-context pass over §5 and clears the same counting rule.** The
untyped `PlannedFile` population contains three materially different claims: a text file wholly
owned by `sync` and able to carry a banner; a wholly owned structured file whose grammar admits no
comment; and selected fields inside a hand-owned structured file. Treating all three as
"sync-owned file" makes a clean `.codex/hooks.json`, `.claude/settings.json` or `.akmon.toml` fail
the universal-banner rule; exempting them in a second list creates the second owner this section
exists to remove. **Owner choice F17/A:** each `PlannedFile` carries exactly one ownership mode —
`bannered-file`, `structured-file`, or `field-owned` — and a field-owned entry also carries its
owned selectors. The plan remains the single declaration consumed by write, check and boundary
inspection. *Rejected: a universal banner requirement*, which is invalid JSON and falsely claims
whole-file ownership over merged settings. *Rejected: a banner-exemption or field-owner allowlist
beside the plan*, which can drift independently and restores the original defect. Accepted cost:
every planned output must be classified and field selectors add machinery to the declaration;
reverse stale-file discovery is mechanically complete only for `bannered-file`, whose marker is
searchable after its declaration disappears. Structured whole-file and field ownership remain
exactly drift-checked while declared, but do not acquire a fabricated stale marker their formats
cannot safely carry. **F17 is carried into 0012** because the three-mode vocabulary and its
one-declaration rule are stable contracts; no N1 measurement can amend them.

**F18 closes the §6 fork exposed by the same final pass.** One cap over the whole always-loaded
surface either makes akmon dictate the size of a consumer-owned `AGENTS.md`, or reduces akmon's own
fully controlled guardrail budget to an advisory. **Owner choice F18/A:** keep two populations and
two strengths. The akmon-shipped population has an inclusive cap of 210 lines and 12,000 decimal
bytes and is an error in `self_ci`; the whole consumer population has an inclusive cap of 460 lines
and 25,000 decimal bytes and emits a warn in `verify.py`, with the existing strict policy turning
that warning into a non-zero exit without changing its severity. Both use the stable C51 code
`caps.always-loaded`. *Rejected: one hard consumer-total cap*, which lets akmon fail a project over
hand-owned prose. *Rejected: one warn-only cap*, which makes growth of akmon-owned context
advisory. *Rejected: adopting the borrowed 150-line reference now*, which ships red and teaches
that the first response to a cap is a waiver. *Rejected: deferring every cap to C60*, which leaves
C60 without a counter or ratchet to lower. Accepted cost: two populations and two dimensions mean
four dynamic measurements and a severity/strict matrix; the consumer can remain above its cap in a
non-strict run, and the initial shipped cap deliberately blesses today's shape. **F18 is carried
into 0012** as the stable scope, unit, code and severity contract. Current measurements populate the
report, while C60 owns justifying and shipping a later reduction.

**F19 closes the §7 location fork.** The six-axis matrix is a consumer contract, but its full
vendor/version/event/matcher coordinates and evidence do not fit README's delivery table without
compressing the axes back into the overloaded grade C57 removes. **Owner choice F19/A:** ship the
axis-complete prose matrix at top-level `CAPABILITIES.md`; keep only a short delivery summary in
README, with no enforcement claim; and let A16 later replace C57's prose cells with generated data
in that same file. *Rejected: a compact README matrix plus a legend*, because the legend is a
compression and recreates the checkmark under a new spelling. *Rejected: placing the matrix under
`meta/`*, because consumers, not only maintainers, are its audience. Accepted cost: one more shipped
top-level document and a bounded duplication window in which C57 owns prose cells while A16 owns
the future schema, ownership and generation. **F19 is carried into 0012** as stable location and
consumer-vocabulary contract; N1 evidence populates cells but does not choose their home.

**F20 closes the §8 ownership-and-population fork.** A one-owner claim can mean only that
`AGENT_SPECS` stops spelling Claude names, or it can mean that every executable declaration of a
vendor tool or matcher — generated agent frontmatter, generated hook matchers and adapter
normalization — consumes one inventory. **Owner choice F20/A:** take the exhaustive reading. The
neutral vocabulary is exactly `edit` / `shell` / `read` / `subagent`, owned by `hook_core`;
`k_explorer`, `k_reasoner` and `k_auditor` are exactly the restricted `{read, shell}` population,
while `k_mechanic`, `k_validator` and `k_implementer` carry the explicit unrestricted sentinel.
One version-stamped data inventory is the sole owner of vendor tool and matcher names for all three
consumer classes. Rejected: repairing only agent frontmatter, which leaves hook matchers and adapter
sets as independent owners; a source scan over vendor spellings without an exact consumer
population, which can pass after a consumer disappears; and leaving the neutral or agent population
open for the engineer to infer from filenames or today's strings. Accepted cost: adapters and both
generators gain a dependency on the shared inventory, the contract suite pins current populations,
and adding a capability, consumer class or harness version requires an explicit data-and-test update.
The detection, fallback and unknown-version choices already made below remain unchanged. **F20 is
carried into 0012** as a stable ownership/vocabulary amendment; measured inventory rows remain
versioned evidence rather than a new architectural fork.

**F21 closes the §9 event, record and durability fork without reopening F10.** F10 decides that the
ledger records dispatch only; it does not decide whether “dispatch” means a request observed before
launch, a confirmed launch, or a completed run, nor what makes one local line safe to trust after
compaction. **Owner choice F21/A:** record the observed Claude `PreToolUse` dispatch **request** after
C46 normalizes it to `subagent`; make no launch or completion claim. Write versioned seven-field TSV
records to `<AITNA_ROOT>/model-routing.log`; retain `.claude/model-routing.log` as the read-only
legacy path. `delegation-log.py` is the sole writer; statistics and coverage-map are the exact default
readers. Serialize bounded appends and keep migration, gitignore, prose/path and schema joins under
`self_ci`. Rejected: treating PreToolUse as proof of launch, because the harness can still refuse or
abort after the request; retaining the vendor path as the primary ledger, because the record is not
Claude-owned; unversioned records, because later readers cannot distinguish a schema change from
corruption; lock-free best-effort append, because parallel dispatch is the normal workload; and
silent repair, deduplication or rotation, because each rewrites local evidence under a policy this
lock has not designed. Accepted cost: the ledger is a request journal rather than an execution
history; old then new can count duplicate-looking records twice; a structurally valid manually
written row is indistinguishable from hook output; and a full or unwritable ledger fails open with
the C52 diagnostic instead of preserving the dispatch. Completion remains N4. **F21 is carried into
0012** as the stable event/schema/ownership contract.

**F22 closes §10's source and state-observation fork without reopening F2 or F11.** The earlier
contract required fidelity to “its sources” but did not select whether C59 composes the existing
owners' live streams, caches their last result, or re-reads their files into status-specific facts;
nor did it say whether a standalone process should persist an active role that exists only in the
harness transcript. **Owner choice F22/A:** invoke the fresh consumer `verify` stream and then the
fresh `sync --check` stream, with C53's D2 state and C56's caps state present exactly once through
verify; preserve exact ordered equality; write nothing; add no direct read or status cache; and state
the transcript-only active-role residual instead of inventing persistence. Rejected: a cached status
snapshot, because it can be green after materialized state drifts; direct reparsing, because it makes
C59 a second owner; a synthesized summary, sorting or deduplication, because each breaks source
fidelity; and a persisted active-role marker created only to make the CLI claim session visibility.
Accepted cost: the provider population and order become contract surface, each status run pays for
fresh checks, and a standalone `akmon status` cannot report the active role. **F22 is carried into
0012** as the stable source/read-only/actual-state contract; detailed mutations remain in §10/C59.

### Pre-lock closure ([A17](../TASKS.md))

The register is not the whole gate. Before D2-20 can be verified, A17 also owns five repairs
to this document and its ledger row:

- **D2-20 is split.** D2-20 retains the architectural F4–F6 protocol alongside F1–F3 and
  F7–F22: what counts as terminal timeout evidence, how budgets are derived, and the bounded
  fast-path/oversize semantics. Concrete vendor results, caps, entry mappings, measurements and
  timeout literals move to **D2-23**, which blocks only C52. The former `Verify (c)` premise is
  obsolete because the F8 table now exists; that table is verified normally as part of the
  consolidated D2-20 architecture gate.
- **Seeded-violation contracts are completed — done, in two rounds** for §7 (C57) and §8 (the C46
  tool-name half); §10 (C59) had left this item earlier at shape level via F11, and its later
  F22/F13 pass supersedes that conclusion with exact source, read-only, actual-state and exit
  carriers. Neither was merely a missing paragraph.
  §7 had nothing to check in the required form — the current tree has no `CAPABILITIES.md`, and
  README's legacy capability rows carry none of the six mandatory axes — so the contract carries
  three additions: `CAPABILITIES.md` as the axis-complete home with
  README reduced to a claim-free summary, a stated scope boundary against akmon's own checkers
  and against C53's guardrail prose, and a **join from the runtime declaration to the generator**
  so that half of §7 stops being unverified prose. §8's version stamp had nothing to compare
  against — no code anywhere reads a harness version — so detection is added where the binary is
  present, an unknown version warns and stamps the generated banner rather than failing, and the
  mechanism is seeded against its **root cause**, a second owner naming vendor tools outside the
  map. Both shapes are observed **red before green**: neither `README.md:200` nor
  `routing.py:362`/`:470`/`:503` is repaired ahead of its task. **"Completed" was true of the
  paragraph each section lacked and false of its rule set**: the architect pass over D2-20's clause
  (d) found rules with no seed in all three sections named here and in six more. They are closed in
  the sections themselves and recorded in A17(g); the wording stands with its correction rather
  than being narrowed after the fact, because a completeness claim a later pass disproves is the
  defect class this stage removes.
- **§9 (C58) is scoped** — settled by **F10**: dispatch-only, completion half spawned as
  [N4](../TASKS.md). The bullet remains here as the record of what the repair was.

The closure also produces **two ADRs, not one** (**F12**): the contract/vocabulary decisions
(F1, F2, F7, F8, later amended by F14, F15, F17, F18, F19, F20, F21 and F22) plus the F11/F13 yardstick — what other work
will cite — kept separate from
survivability and crash posture
(F3–F6), which the N1/F4, N5/F6 and N6/F5 measurements are expected to amend. An ADR that must be revised by
measurement should not carry the stable vocabulary along with it, or every timing number formally
disturbs a decision that has already been built on. The cost is a boundary to maintain and two
references where one would do. **Both are written** —
[0012](../decisions/0012-stage1-contracts-and-vocabulary.md) and
[0013](../decisions/0013-hook-survivability-and-crash-posture.md) — and both carry
**Status: Proposed** before the gate, against this repository's habit of writing an ADR only once a
decision is locked; both are now Accepted after D2-20 verification. **The convention is amended
with one bounded case rather than excepted for this pair**
([decisions/README](../decisions/README.md)): an ADR whose own owner-verify gate verifies the *ADR
boundary itself* has to exist before that gate can run, so it carries `Proposed` and names the row
that will flip it. Here that row is D2-20, whose clause (b) verifies the two-ADR boundary — which
cannot be verified from a description of two files that do not exist, so the ADRs are the object of
the gate rather than its output. An earlier draft of this paragraph said the habit was *not*
amended while the convention file already carried the new clause; a rule and its exception
disagreeing across two files is the defect this stage removes, so the disagreement is recorded
rather than silently fixed. Four register rows are
**decided here and not re-decided in either ADR**, and D2-20 verifies them in this document:
**F9** is internal to C54 and nothing else cites it, **F10**'s record is the probe it spawned
([N4](../TASKS.md)), **F12** is the ADR pair's own shape — each ADR states once why its scope
is what it is, with the rationale living in 0012 and 0013 pointing at it, which is F12 applied
rather than F12 duplicated — and **F16** owns §7's runtime declaration, which neither ADR carries.
0012 keeps a pointer to F9, F10 and F16 so their absence does not read as an omission. **The
criterion itself was replaced, deliberately and once.** It first read that the four
rows must not appear in either ADR at all; the second audit held the documents to it and was right
to. The strict form is now rejected on implementation grounds: an implementer who finds no trace of
a neighbouring decision cannot distinguish deliberate absence from a lost requirement, and
re-deciding it is the cheaper mistake to make. The rule that replaces it is **not uniform over the
four rows, because F12 is not like the other three**: F9, F10 and F16 are decisions *about other
work*,
while F12 is the decision that gives each ADR its scope, and an ADR that cannot say why its scope
is what it is fails at being an ADR. So — **F9, F10 and F16: identifier and navigational pointer
only, never the choice, its mechanism or its consequences. F12: its scope rationale is stated once, in
0012; 0013 carries a pointer to that rationale and no argument of its own.** Either ADR may still
state plainly *what* it covers, which is self-description rather than a repetition of F12. The
first version of this rule was uniform and therefore contradicted the sentence three lines above
that permits the rationale in 0012; the contradiction was found in the pass after the replacement,
which is the argument for writing a criterion down rather than holding it. The replacement is on
the record because an unrecorded change of criterion is how the next audit legitimately reports the
same finding again. The stage-wide yardstick (F11, F13) travels with 0012, because
it is stable and it governs how every contract in both ADRs is written.
- **The internal contradictions are repaired — done** ([A17](../TASKS.md) (f)). Five
  were listed and a sixth surfaced while repairing them; none was purely editorial, so each is
  recorded with what it changed. (1) The order table's C53 row now names the **F8 table**, marked
  as a decision rather than a task to wait for. (2) The C55 row read `P0.4 declaration (§6)`,
  which did not distinguish the declaration from C56's implementation; it now names the
  always-loaded *definition* explicitly, and the consequence is that **C55's only task dependency
  is C51** — it was never waiting for C56. (3) **C60 is removed from the order table**, whose own
  caption limits it to dependencies internal to the lock; the `C56 → C60` edge moves
  to *Not in this lock* so it survives the deletion. (4) **A16 became `blocked (after
  D2-20)`** in TASKS.md: it cannot settle a vocabulary that inherits F3's axes before F3 is
  locked, and its first job — consuming C57's cells — sits behind the same gate, so the honest
  status cost nothing at that stage; after the lock it remains blocked on C57. A third status
  level for *decided but not locked* would be more precise
  and is deliberately **not** invented here: that is D1, and it is parked. (5) §2's guard is
  scoped to the **nine spawned entry points**; adapters and `hook_core` are imported, have no top
  level, and are covered by the caller's guard — which turns their single-write output into a
  contract, since a guard cannot un-write truncated stdout. (6) Found while repairing (1): C53
  **writes into the surface C56 caps**, an edge the graph omitted. The numbers do not collide
  today (+1…+2 lines against 13 lines of slack), which is the reason to record the edge rather
  than to skip it — nothing else would show when they begin to.
- **The clean-context coherence audit has run — done** ([A17](../TASKS.md) (g)). It was run
  deliberately outside the context that wrote this document, because an author checking a document
  against their memory of what they meant is not checking the document. Twenty-four findings, of
  which four landed on repairs made earlier in A17 — the surest sign the separation was worth its
  cost. The full finding-by-finding record with verdicts lives in A17(g); what changed *here* is:
  **F13** entered the register (above); §7's red-state premise was false and is rewritten, together
  with the **evidence axis** the matrix vocabulary needed for its own seed to be mechanical; §8's
  claim to reuse an existing `hook_core` vocabulary named a token that does not exist and is
  corrected to the real set; §1's "text rendering *remains*" described a form the tree does not
  print and now records a **change**; §5 gained the checker it never named; §9's guardrail clause
  gained a real check instead of a canary that could not reach it; §10's "no new data source" and
  F8/3's coverage report are reconciled; §2 gained separate seeds for its BOM, `timeout` and
  single-write rules, the last because the coverage it claimed was asserted but never exercised;
  §4 and §8 gained the seeds F13 requires; and the order graph gained C58's collision with the
  always-loaded caps — the twin of the C53 edge found at (f), missed by the same reading.
- **The seeded-violation contracts are audited against F13 — done** ([A17](../TASKS.md) (g), the
  architect pass over D2-20's clause (d)). **Twenty-one rules across nine of the ten sections were
  declared normative here and reachable by no named mutation.** F13 makes the independently
  violable rule the seeding unit, so the shape-level reading under which this document would have
  passed is no longer available to it. Six reported items resolve to thirteen findings here; seven
  more came from sweeping every section and both ADRs instead of the ones handed over, three of
  those in sections that pass had declared clean — the lesson I8 recorded about coordinates, in a
  second domain. **Three repairs close a fork rather than add a test**: the retired-code list (§1),
  the shipped-classification pin (§3), and §7's two binary populations — **all three put to the
  owner and accepted**,
  and registered as **F14–F16** above. The last repairs a **false finding this
  document would have shipped** — `claude` and `codex` appear in no generated command, so the
  declaration-to-generator join as written warns that the two optional binaries §8 depends on are
	  stale prose. Under that pass's coarse contract, §9 (C58) was the one section that needed
	  nothing; F21's later owner walkthrough supersedes that conclusion with the C46 → C58 edge and
	  exact carriers.

## Order and dependencies

| # | shape | plan | task | depends on |
|---|---|---|---|---|
| 1 | shared finding envelope | P1.6 | C51 | — |
| 2 | hook survivability | P1.1 | C52 | D2-23 evidence gate |
| 3 | invariant canary | P1.2 | C53 | C51, P0.3 inventory (N2, done), F8 table (§3); writes into the always-loaded surface C56 caps |
| 4 | version ↔ changelog cross-check | P1.3 | C54 | C51 |
| 5 | source/generated boundary check | P1.7 | C55 | C51; always-loaded set definition (§6 declaration — not C56's cap check) |
| 6 | always-loaded caps | P0.4 | C56 | C51 |
| 7 | OS contract + matrix vocabulary | P0.2 | C57 | C51 |
| 8 | tool names: neutral capability + vendor map | — | C46 | C51, C57; emits a provenance banner line C55 checks |
| 9 | execution ledger | P1.5 | C58 | C46, C57 (normalized dispatch event + matrix cell for the Codex gap); writes into the always-loaded surface C56 caps |
| 10 | `akmon status` | P1.4 | C59 | rows 1–9, **C46 included**, plus the D2-27 C70 extension |

Every implementation edge below also depends on owner verification of D2-20; the table shows
only dependencies internal to the proposed package. C52 alone has the additional D2-23 evidence
gate, so missing runtime numbers cannot hold C51 or C57 behind an unrelated measurement campaign.

Four entries in the depends-on column are not task dependencies and are spelled out so they are
not read as such (three of them counted at A17(f), the fourth found at A17(g); the paragraph said
"two" and claimed completeness over a column the audit reads as the lock's contents).

C53's F8 edge is a **decision** it must have before code, not a task to wait for. C53's second
edge is a **collision**, not an order: C53 replaces three `> **Enforced**` blocks with
six markers and writes the new `## Role declaration` section, all inside the surface C56 caps —
an estimated +1…+2 lines against a measured slack of 13 (§6: ~197 shipped against a 210 cap), so
the two are compatible today and the edge is recorded because a graph that omits it cannot show
when they stop being compatible. **C58 carries the same collision**: its guardrail clause is added
to `guardrails/_common.md`, which §6 counts as always-loaded in full, so it draws on the same
slack — one line, against the same 13. C46's entry points the other way and is an **outgoing**
annotation rather than an edge into C46: C46 emits the provenance banner line C55 checks, while
C55's own row lists only C51. C55 needs the always-loaded *definition*, which §6 already
carries; its only task dependency is C51.

Row 10 spells its range out because "all of the above" was read two ways: C59 aggregates the
finding stream `sync --check` surfaces, and C46 emits findings into it (the degrade warn, the
unknown-version warn), so **C46 is inside C59's range** and TASKS' `C51–C58` was one shape short.

**D2-27 post-lock extension.** C70 is not an eleventh stage-1 shape: it repairs the host-delivery
blind spot measured after this lock. Its task edges are C51 and C57; after those land it can proceed
in parallel with the C46/C58 branch. C59 additionally waits for C70, receives the C70 finding inside
the complete `verify` provider, and never gains a third provider or a host query of its own. The
resulting acyclic path is `C51 → C57 → C70 → C59`.

P1.6 leads because eight of the nine remaining shapes emit findings. P1.1 shares no findings
dependency and can be engineered in parallel with C51 only after D2-23 is verified. P1.4 is last
on purpose: it aggregates a finished vocabulary
instead of inventing one.

## 1. Shared finding envelope (P1.6 → C51)

**Decision.** Extend the existing `bin/verify.py::Finding` into one shared stdlib-only module
`common/findings.py`, with fields `severity · code · message · target · fix`. `severity` carries the
`ok / warn / error` vocabulary and preserves the shared exit-code contract (errors exit 1;
warnings exit 1 only under `--strict`) in the three strict-capable adopters; `sync --check` carries
the explicit 0/1/2 exception recorded below. `code` is a stable dotted slug naming the check (`boundary.missing-banner`,
`caps.always-loaded`, `invariant.orphan-hook`) — unique, never reused after a check is removed.
A dotted slug matches `[a-z0-9]+(?:-[a-z0-9]+)*(?:\.[a-z0-9]+(?:-[a-z0-9]+)*)+` — at least two
lowercase ASCII segments, dots between segments and single hyphens only inside them. Whitespace,
uppercase, empty segments and a slug with no dot are invalid. `target` is the file or artifact the
finding is about; whether it names the correct artifact is review-owned. Every rendered field is
one logical line. `fix` is **required**, non-empty and one sentence. The mechanical heuristic
rejects a terminator followed by whitespace and the compact uppercase form; residual
natural-language sentence boundaries and imperative mood are review-owned so ordinary paths stay
valid. A finding a reader cannot act on is a defect of the check, not of the tree. Adopted by
`verify.py`, `meta/bin/validate.py`, `sync --check`, and `meta/self_ci.py` —
the last one imports the module directly for its own findings rather than parsing subprocess
output.

**Owner choice F1 — B: rename `level` to `severity`.** `severity` is the sole
canonical field; C51 does not add a property alias, constructor alias, or serialization alias.
Any later JSON form uses only `severity`. This deliberately accepts a breaking Python API change
for callers constructing or reading `Finding` objects. The rendered values
remain `ok / warn / error`, and the text and exit-code semantics do not change. Architect
rationale: one standard diagnostic term is clearer than preserving a project-local field name,
and a temporary dual vocabulary would create migration debt before the shared envelope has a
documented external API. Migration work in C51 must update every in-repository constructor,
attribute read, fixture, and test in one change, including the independent Finding currently in
`meta/bin/validate.py`. Contract tests assert that `severity` exists, `level` does not, and the
constructor rejects `level=`; positional construction alone is insufficient migration evidence.

**Owner choice F2 — C: schema in C51, public JSON output in C59.** C51 owns a
stdlib-only `Finding.to_dict()` or equivalent pure serializer and pins the exact object keys and
values with contract tests. This keeps serialization beside the shared envelope and makes F1's
absence of `level` testable. C51 does not add `--json` to `verify.py`, `sync --check`,
`meta/bin/validate.py`, or `self_ci`; C59 introduces the public JSON rendering when `akmon status`
becomes its first process-boundary consumer. Text rendering **changes**, and C51 owns the change:
`verify.py` prints `[{level}] {message}` today (`bin/verify.py:691`), while the canonical form
this envelope introduces is `SEVERITY code target: message → fix`, one canonical stdout line per finding. It is
recorded as a change rather than a continuation because the audit at A17(g) found the word
*remains* describing a form the tree does not print — every adopter's text output moves in the
same commit as the `level`→`severity` rename, and the tests pinning the old form move with it.
There is exactly one canonical
serializer (method or shared pure function, not both); here `pure` means a deterministic mapping
of the Finding's fields that does not mutate it, with no broader functional-purity claim. Any
adopter or later consumer that serializes a Finding must call it rather than repeat the field
mapping. The C51 adopters render text only; C59 is its first serialization consumer. Its output uses JSON-safe stdlib values, preserves Unicode, does not
mutate the Finding, and passes `json.dumps` directly.

**Out of scope.** Hooks do not adopt the envelope: they speak the harness's JSON contract on
stdout and prose on stderr, and a findings object there would be a third output shape on a
channel whose visibility is unverified.

**Seeded violation.** A check constructed without `fix` fails a test; a duplicate `code` across
adopters fails a test; serialization missing a canonical field, adding `level`, or changing a
value fails the exact-schema contract test. The serializer is also tested with Unicode and an
empty valid `target`; a local field mapping in an adopter is rejected by the shared-owner test.
**Text rendering carries its own seed** (A17(g), per F13): a rendering that drops `code`, `target`
or `fix`, or emits them in another order, fails an exact-output test — without it the whole text
half of this envelope could regress while every schema test stayed green.

**Three rules of this envelope were declared above and seeded nowhere** (A17(g), per F13).
**Code stability:** `code` is unique and *never reused after a check is removed*, which the
duplicate seed cannot see — at no moment do two live checks share the slug. `findings.py`
therefore carries a **retired-code list**, and a live `code` that appears in it fails. This is not
the central registry F7 rejects in §3: that rule forbids a constant that *carries the
prose↔callable join*, while this list carries no join and is a record of names already spent.
Rejected: dropping the never-reused clause, which is the half a consumer greps for. Appending a
removed code is explicitly **process-owned**: F14's accepted cost is that the checker cannot detect
an omitted append; it guarantees non-reuse for codes present in the record and does not pretend to
mechanize the deletion review.
**`fix` shape:** the seed above proves only that `fix` exists, while the rule is *one sentence in
the imperative*. Split per F13 — non-empty and no line break are checked; the bounded sentence
heuristic rejects a terminator followed by whitespace and the compact uppercase form. **Residual
natural-language sentence boundaries and imperative mood are review-owned and stated here as not
machine-checked**, the same fence F8's table puts around its non-checkable clauses, so that a later
audit reads them as properties of the claim rather than gaps. **Exit and strict semantics:** F1
rewrites every adopter's `Finding`
construction, and "errors exit 1; warnings exit 1 only under `--strict`" is preserved by nothing
but intent. Each of the three strict-capable adopters carries a seed over both severities and both
strict states: a warn that exits 1 without `--strict` fails, and so does an error that exits 0.
`sync` carries its separate exact 0/1/2 seed below.

**Three C51 build-time owner decisions, recorded because each fixes a clause this section
left open.** They are decisions inside the approved lock, not a re-lock of it.

1. **`fix` is required at every severity, `ok` included.** The section already declared `fix`
   required and `target` optionally empty, and the asymmetry is deliberate; the open question was
   only whether `ok` inherits it, because an `ok` finding has nothing to repair. It does: on an
   `ok` finding the sentence states **the invariant to keep** (`OK gitignore.env-secrets
   .gitignore: … → Keep the '*.env' and '!*.env.example' patterns in .gitignore.`), which is what
   a reader who wants to keep it green actually needs. Rejected: making `fix` optional for `ok`,
   which would put a severity-dependent branch into the one field the envelope exists to
   guarantee; and dropping `ok` from the stream, which contradicts the closed vocabulary here and
   the complete-stream requirement F22 puts on C59.
2. **`sync` adopts the envelope in `--check` only, and keeps its own exit vocabulary.** `--check`
   is the non-writing mode F22 names as C59's second stream, and it is the only `sync` output
   that is a *diagnostic*; `--dry-run` and a real write keep their action log, because "updated
   this file" records what happened rather than what is wrong. `sync` also keeps **exit 2** for a
   planning error against **exit 1** for drift, and gains no `--strict`: 2 separates "could not
   even compute the planned files" from "the plan and the tree disagree", and nothing in that
   stream warns. This is the one adopter whose exit codes are *not* `exit_code`'s, so it is
   carried by its own test rather than by the shared matrix. Rejected: collapsing 2 into 1 for
   contract symmetry, which would spend a live distinction to buy a uniformity no consumer asked
   for.
3. **Every rendered field is one logical line.** The section fixes canonical stdout at one line per
   finding; nothing enforced it, so a line separator in `code`, `message`, `target` or `fix` could
   crash an adopter or forge another apparent finding. Checked in the envelope across every
   `str.splitlines()` separator. Subprocess detail may remain multi-line only on stderr; content
   entering a Finding is reduced to one safe line.

**The remaining §1 triples are explicit and population-wide.** The C51 contract suite runs over
all four adopters. An out-of-vocabulary severity such as `fatal`, an invalid dotted slug, a stale
`.level` read or local `Finding`, or an adopter that retains the old renderer fails. The `fix`
shape fails on empty, multi-line, terminator-plus-whitespace or compact-uppercase second-sentence
text; residual natural-language boundaries and imperative wording remain review-owned.
The serializer test compares the Finding before and after the call, calls `json.dumps` directly on
the result, calls it twice to require the same mapping, and fails on mutation, nondeterminism or a
non-JSON-safe value. An AST import check on `findings.py` fails on a dependency outside the Python
standard library. The shared-owner check fails if a
second canonical serializer exists, not only when an adopter copies the mapping. Adding `--json`
to any C51 adopter before C59 fails its CLI contract. Exact rendering is exercised over every
adopter. The full severity × strict-state exit matrix is parameterized over the three
strict-capable adopters, and `sync --check` carries its separate exact 0/1/2 test, so a
representative implementation cannot hide a stale one. The self-CI fixture carries `findings.py`,
executes its mounted launchers, gives successful legs invariant-specific `ok.fix` text, and
suppresses successful child output so `--quiet` remains quiet.

## 2. Hook survivability (P1.1 → C52)

**Decision.** Every hook wrapper gets four things:

1. **Bounded stdin.** Read at most the owner-verified F6 raw-byte cap plus one detection byte;
   the literal is not chosen before F6 evidence. On overflow the wrapper does not decode or
   truncate-then-parse: it follows the distinct F6 oversize contract and exits 0.
2. **BOM tolerance.** Decode as `utf-8-sig`, so a BOM-prefixed payload parses instead of
   landing in the malformed-JSON fallback.
3. **A top-level exception guard** in every **spawned entry point** — nine of them: the eight
   generated Claude entries (`git-commit-guard`, `role-on-code`, `analysis-guard`,
   `d2-ledger-reminder`, `delegation-log`, `delegation-nudge`, `session-start-agent`,
   `model-routing`; `bin/sync.py:270`–`:306`) and the single Codex entry `codex-hook.py`, which
   carries the route as an argument (emitted at `bin/sync.py:203` and `:222`–`:244` — the file
   is named explicitly because the bare form read as coordinates inside `codex-hook.py`, which
   has no such lines). It prints the exception class and
   the hook name to stderr and exits 0. **Five of the nine already carry such a guard and four do
   not** (found at the ADR audit, and measured rather than assumed): `d2-ledger-reminder`,
   `delegation-log`, `delegation-nudge`, `session-start-agent` and `model-routing` wrap the whole of
   `main()`; `git-commit-guard` — the deny-class hook — `role-on-code`, `analysis-guard` and
   `codex-hook.py` do not. C52 therefore **changes five entries and adds four**, and the five that
   exist are red against this contract rather than compliant with it: they print
   `{type(exc).__name__}: {exc}`, disclosing the exception *message* that the diagnostic rule below
   forbids, and they catch `Exception`, so an `argparse` `SystemExit` in the Codex entry passes
   through. The seeded test is observed red on today's five as well as on the missing four. **The adapters and `hook_core` get no guard of their
   own**: they are imported, never spawned, so they have no top level — an exception inside
   `claude_adapter.load_payload` propagates into the wrapper's `main()` and is caught there.
   They are covered *by* the guard, not *with* it, which is also why F5 below states that the
   adapter modules are not timeout scopes. This coverage has a precondition, so it is a
   contract and not an observation: **an adapter assembles its whole output and writes it in one
   operation**, so that the guard can only ever fire before that write. Without it a crash
   mid-render leaves truncated JSON on stdout and the guard still exits 0 — which is precisely
   what C52's seeded crash tests forbid.
4. **`timeout` in the generated Claude wiring**, plus the contract written into
   `hooks/README.md`.

**Owner choice F3 — C: crash-open now; gate deny-class fail-closed.** C52 makes
every unexpected wrapper/adapter/handler exception exit 0 after one loud diagnostic, including
exceptions in deny-class hooks such as `git-commit-guard`. A healthy handler's explicit deny
continues to use the vendor's deny route; crash posture and decision enforcement are separate
claims. The capability matrix must therefore record two independent facts: **"normal-path
effect: deny observed on route R when the hook completes"** and **"crash posture: fail-open"**.
It must never imply that a deny survives an akmon crash or collapse the facts into bare
`enforced` or an unqualified checkmark.

Moving any deny-class hook to fail-closed is outside C52 and requires a separately owner-verified
change. Its gate is: (1) an N1 live probe of the exact vendor route and payload, including the
crash/nonzero-exit case; (2) a regression test pinned to that payload and observed behavior; and
(3) a documented owner-controlled recovery/bypass that is tested without editing generated
files by hand. Until all three exist, crash-open remains the contract. This accepts one missed
deny on an akmon crash in exchange for not allowing an unmeasured hook failure to brick every
commit in a consumer repository.

> **Amended by C87 / D2-45** ([ADR 0013](../decisions/0013-hook-survivability-and-crash-posture.md),
> amendment): the guard in item 3 lands in C87 ahead of C52. A Claude entry also writes the
> owner's `systemMessage` notice, and the Codex entry exits 1 rather than 0, so Codex shows the
> hook `Failed` (M68–M71).

**Owner choice F4 — C: probe-gated Codex timeout.** Terminal N1 evidence is a
prerequisite to C52 as a whole; C52 is not partially runnable before it. The evidence artifact
records the exact Codex build/version, invocation mode, configuration source, event, matcher,
hook entry, tested literal and units. Each entry scope that C52 would modify is probed separately
with a controlled slow hook, a no-timeout control, before/after markers, and an expiry run. It
records elapsed cutoff/tolerance, termination exit or signal, captured stdout/stderr, and whether
the tool call proceeds or blocks. Timeout termination is an external host outcome and does not
inherit F3's crash-open or loud-diagnostic labels.

`Supported` means the accepted field actually terminates the slow fixture within the measured
tolerance; parse acceptance alone is insufficient. `Unsupported` requires observed rejection or
an accepted-but-ignored field. If supported, C52 emits the exact measured key/value/units only on
the probed entry scopes and adds an exact generated-shape regression. If unsupported, it emits no
field on Codex routes and adds a negative regression. Evidence and matrix claims stamp the probed
version; later versions inherit neither claim and trigger N1 re-probe. `Unmeasured` is not a
terminal result. F4 does not choose the duration: F5 owns explicit timeout evidence and budget
for Claude and any supported Codex route.

**Owner choice F5 — C: measurement-derived budgets by hook class.** N6 inventories
every generated Claude entry and every Codex entry scope found supported by F4. The initial class
table follows dominant workload, not vendor or filename: payload/marker; project/config scan; git
subprocess; transcript/routing I/O. Every generated command entry maps to exactly one class; the
adapter modules are not timeout scopes. Entries may share a class only where their supported work
envelope and measured runtime profile are equivalent.

F6 must first bound the currently unbounded valid axes (including transcript/ledger sizes, agent
roster, D2 globs/path depth/config, and patch path count). Before those bounds exist, timings are
honestly a stress corpus, not a worst case. After F6, each class gets a largest supported fixture
corpus, repeated actual-process runs, and the machine-reproducible formula
`ceil_to_vendor_unit(max_observed_supported × factor)`, with explicit factor, rounding, minimum
floor, and proposed production literal. The git-subprocess class must account for the existing
5-second internal git timeout or change that inner bound in the same design; an outer timeout may
not pre-empt the healthy fallback accidentally.

The sequence breaks the apparent cycle: F4 proves mechanics with disposable scratch wiring and a
sentinel literal; F6 bounds supported inputs; N6 measures entrypoints directly without a host
timeout; F5 derives exact literals; scratch wiring live-verifies them; the owner verifies the
class/literal table; only then may C52 implement it. Live validation covers both individual entry
expiry and aggregate latency/behavior where a single event schedules a group of hook processes.
Together this F4 → F6 → F5 packet is the measured evidence owned by D2-23; it does not amend or
reopen D2-20 unless the measurements force a change to the stable architecture protocol.

Ordinary CI does not assert wall-clock timing. Durable regressions prove exhaustive entry-to-class
mapping, exact owner-verified literals/units, omission on unsupported or unprobed Codex scopes, and
failure when a new entry has no class. Timings remain versioned evidence from a reproducible
harness; after C52, that corpus is rerun, and exceeding a literal re-blocks the task rather than
silently raising the budget. `hooks/README.md` records the table, evidence environment and scope,
and states that the budget is an operational bound, not a cross-machine latency SLA.

**Owner choice F6 — C: bounded synchronous fast path.** Before F5 derives timeout
literals, N5 inventories and measures every valid input axis that can grow with a consumer:
raw stdin bytes before decode/JSON plus JSON depth/item/string bounds; command and description
bytes; extracted patch path count and per-path bytes/depth; transcript total/line bytes and
matching-record count; D2 ledger bytes/rows; D2 config bytes, glob count/length/depth and `**`
complexity; registry, overlay, local config and settings bytes/depth/items; brief count/text and
generated-output bytes; agent roster count/name/output bytes; generated-agent directory count,
per-file/total bytes and rebind/prune population; and akmon-owned marker/counter bytes. The
evidence proposes a numeric cap and unit for every applicable generated command entry. Each cap,
entry mapping, and combined supported fixture corpus require explicit owner verification; until
then F6 is decided in direction, D2-23 remains pending, and C52 is blocked.

At runtime, raw stdin is read as cap+1 before decode; files are preflighted and bounded-read to
handle growth races; directories/lists enumerate at most cap+1 and discard the whole collection
on overflow. Structural JSON caps are validated immediately after the bounded parse and before
handler dispatch. Every applicable source is preflighted before the entry's first stdout, marker,
log, config write, rebind, prune, or deletion. A later oversized source therefore leaves none of
the earlier side effects behind and invokes no handler with a prefix.

An over-cap entry writes exactly one stable hook-process stderr diagnostic per invocation naming
only hook, input dimension, cap and fail-open remediation, then exits 0 with empty stdout: no
`ask`, `deny`, context, system message, malformed/partial JSON, or throttled-away later warning.
Payload values, paths/content, commands, session ids, and secrets are never included. This is a
handled **oversize degradation**, not an exception crash or host timeout, so the capability record
states it separately as `input envelope: exceeded → fail-open`. Other command entries launched
for the same event retain independent envelopes and may still complete.

This choice deliberately allows a deny-class bypass by padding an otherwise matching payload
past a supported cap. Therefore a normal-path claim is always scoped as **"deny observed on exact
route within the supported input envelope"**; D2-20 requires the owner to verify that availability
trade explicitly. Oversize is never mislabeled as the existing no-path diagnostic and gets its
own stable diagnostic code.

Caps are compatibility boundaries, not tuning constants: implementation cannot raise them to
make a test pass. Demand from a larger real consumer starts separate architecture/evidence work
to stream, index, cache, or otherwise bound the expensive source; only new measurements and owner
verification may raise the envelope. A numeric increase alone is insufficient: the new design
must bound time/memory, prove equivalence to full processing, make index/cache updates atomic with
freshness/invalidation and corruption recovery, preserve safe fail-open on stale state, rerun live
boundary probes, and rederive F5 budgets. C52's durable tests cover cap−1/cap/cap+1 for every
source, full processing at cap, a handler spy never called at cap+1, zero earlier side effects
when a later source overflows, safe diagnostics, healthy deny at cap and fail-open above it, and
failure when a new synchronous input axis or generated command entry lacks an envelope declaration.

**Seeded violation.** Per F13 the unit is the rule, so the four top-level wrapper additions above
decompose into the independently violable contracts below rather than receiving one representative
seed. A17(g) first exposed the gap; the D2-20(d) walkthrough completed the decomposition.

**Guard.** A wrapper without it fails a test that feeds it a payload
engineered to raise inside the handler and asserts exit 0 + exactly one stderr diagnostic. The
same matrix is parameterized over all nine entries and injects the failure at each applicable
wrapper, adapter and handler layer, so coverage through the wrapper is proved rather than inferred
from one call site. A separate `SystemExit` injection at the Codex argument boundary proves that
the top-level posture covers the non-`Exception` exit already named above. A deny-class fixture
proves both halves: an explicit handled deny remains deny, while an exception
on the same route exits 0 and is reported. The crash path emits no deny/ask, malformed JSON, or
partial stdout. Its stderr names only the hook and exception class — never payload values,
commands, file content, session ids, or secrets. This contract is parameterized over all nine
spawned entry points rather than demonstrated on one representative — and it is **red on five of
them today** for the disclosure clause alone, which is what makes this seed meet the tree rather
than a fixture in the five places a reader would assume were already done.

**Single write.** The guard seed crashes *before* anything is rendered, so it cannot tell a
one-shot write from a prefix-then-crash: the assertion "no partial stdout" passes whether or not
the adapter honours the contract. A second seed places the failure **mid-render** and asserts the
wrapper's stdout is either empty or a complete document, never a prefix. Recorded plainly because
the claim this repairs was not a gap but a false one — §2 said the precondition was "precisely
what C52's seeded crash tests forbid", and the named mutation never reached it.

**BOM.** A valid payload prefixed with a byte-order mark must reach the handler; decoding it as
`utf-8` instead of `utf-8-sig` routes it to the malformed-JSON fallback and fails the test.

**`timeout`.** Split, because the literal and the presence have different gates: a generated
Claude entry emitted **without** a `timeout` key fails `sync --check` now, while the literal's
correctness stays behind the D2-23 evidence gate and is pinned there by C52's entry→class→literal
table. The split is F13's rule applied rather than an exception to it — the half that is
checkable today is checked today, and the remainder names the gate it waits on instead of
disappearing into prose. Deleting the timeout contract from `hooks/README.md`, omitting its table,
evidence environment/scope or operational-bound-not-SLA statement, or making its
entry→class→literal table disagree with the generated wiring, fails `self_ci`. The git-subprocess
mapping also has a relational regression: an outer literal that can expire before the existing
healthy 5-second git fallback fails without a wall-clock assertion.

**Bounded input** uses more than a static cap−1/cap/cap+1 corpus. An instrumented stdin/file
reader fails if the implementation requests more than cap+1 bytes or attempts decode after an
overflow. An instrumented collection fails if cap+2 is requested and asserts that overflow
discards the whole collection rather than dispatching a prefix. Structural overflow injects a
handler spy and side-effect sentinels at every pre-dispatch boundary; any handler call or earlier
stdout, marker, log, config or artifact mutation fails. **The growth race has its own seed**
(A17(g), per F13). The static corpus cannot reach it: a preflight-then-read
implementation passes every cell of it while still reading a file that grew between the two calls —
the case the runtime rule above names in its own sentence. A seam whose size probe returns a value
below the cap and whose read then yields content above it must produce the oversize contract:
fail-open, empty stdout, no handler invoked. An implementation that trusts the preflight result
fails.

**The oversize diagnostic** carries rules that the corpus above must not compress into "safe
diagnostics". It gets **its own stable code**, distinct from the existing no-path diagnostic —
reusing that code is the
mislabelling the rule forbids, and a reader cannot tell an over-cap input from a hook that found
no path. There is **exactly one per invocation**: one fixture presents multiple oversized sources
and fails if more than one line is emitted. A second invokes the same process contract repeatedly
and fails if a session or tool-use throttle suppresses a later invocation. The exact diagnostic
oracle admits only hook, input dimension, cap and remediation; unique sentinel path, payload,
command, session and secret values make any disclosure fail. Each mutation fails its own test.

**Entry independence** is seeded at the generated event boundary: one entry receives an oversized
source while a healthy sibling receives supported input, and the sibling must still complete.
Cancelling the group, sharing the overflowing entry's state, or suppressing the sibling output
fails the fixture.

Two obligations remain explicitly **process-owned**, not silently exempted from F13. Raising a cap
requires the separate architecture/evidence and owner-verification process above; C52 mechanically
pins the verified literal but cannot prove that a future author opened that process. Likewise the
reproducible D2-23 performance corpus, not ordinary CI, decides whether measured runtime has
regressed and must re-block C52. The residual cost is that bypassing either process can only be
caught in review; no wall-clock or intent checker is claimed.

## 3. Invariant canary (P1.2 → C53)

**Owner choice F7 — B: stable policy IDs join prose and code.** A guardrail section
with runtime behavior carries `Runtime check: <stable.dotted-policy-id>`. It never says bare
`Enforced by`, because F3 requires normal-path route, crash posture and input envelope to remain
separate claims. The policy prose remains the rule owner; the marker is its stable join key.

Every public `hook_core.*_result` has exactly one machine-readable classification in its own
docstring, parsed from the AST without importing hook code:

- `Policy ID: <stable.dotted-policy-id>` for policy-bearing behavior; or
- `Runtime classification: operational` plus `Rationale: <non-empty rationale>` when it carries
  no guardrail policy.

The join is one-to-one: each policy ID occurs once in live guardrail prose and once in callable
metadata. Each public result has exactly one classification and cannot carry both forms.
Operational classifications have no prose marker and require a rationale, so they cannot become
an unreviewed exemption. A broad guardrail heading may contain a marker only for the exact subset
the callable observes; the marker never claims the entire section is enforced.

`self_ci` checks both directions and reports the policy ID, callable and prose location. There is
no `INVARIANTS.md`, central mapping constant, decorator registry or generated annotation: each
fact lives either with the policy prose or with the callable it classifies. Function names and
paths are not policy identity; a rename that preserves the stable ID preserves the join.

**Owner choice F8 — the initial table, exhaustive over the seven current public
`hook_core.*_result` callables.** Six policy IDs and one operational classification. C53 checks
this set; a callable added later joins it the same way or the check fails.

| callable | classification | prose owner and the subset the marker claims |
|---|---|---|
| `privilege_escalation_guard_result` | `privilege.no-escalation` | `guardrails/_common.md` § Privilege escalation — the whole rule: any `sudo` in a Bash command is denied |
| `git_commit_guard_result` | `commits.owner-owned` | § Commits & ownership — **subset**: the AI `Co-Authored-By` trailer (deny) and `push`/`tag`/`merge`, or a commit on the default branch or detached/unresolved HEAD (ask in interactive default mode; deny when `permission_mode` is missing or non-default because the ask cannot be trusted to reach the owner). "Tests pass before a commit is offered" and "branch for non-trivial work" are **not** machine-checked and the marker must not imply they are |
| `analysis_write_result` | `analysis.before-mutation` | § Analysis before mutation — **subset**: the first edit to a planning/design document in a session raises a reminder. The rule's substance (was this turn analysis-only?) is not decidable by a hook |
| `d2_ledger_reminder_result` | `verify.owner-verify-d2` | § Verify against reality, not memory, the **Owner-verify** bullet — **subset**: an edit matching the consumer's configured `[d2_ledger] sensitive_paths` globs (see F8/3 below) |
| `delegation_nudge_result` | `delegation.tier-floor` | § Route by task kind — the tier floor — **subset**: uninterrupted read/shell/edit volume without a delegation raises a nudge, then an ask in interactive default mode; a missing or non-default `permission_mode` escalates that ask to deny |
| `role_on_code_result` | `role.declaration` | § Role declaration — **new prose, written by C53** (see F8/1) — **subset**: the first edit to a code file in a session, which is the design→code switch the SessionStart reminder cannot catch |
| `session_start_result` | `Runtime classification: operational` | — see F8/2 for the required rationale |

**F8/1 — `role.declaration` gets prose in the guardrails, not an exemption (owner: a).** The rule
("state which agent you are operating as, and restate it on every switch") is today asserted only
by the hook text and the SessionStart message: the orphan the P0.3 inventory found. C53 adds a
`## Role declaration` section to `guardrails/_common.md`. Rejected: hosting it in
`roles/README.md`, which spends no always-loaded budget but redefines "live prose" from the
always-loaded chain to any policy document and widens what C53 must parse; and marking the
callable operational, which is the unreviewed exemption F7 exists to prevent. Budget: three legacy
`> **Enforced**` blocks (10 lines) are replaced by six marker lines and the new section adds five
to six, so the estimate is **+1 to +2 lines**, confirmed by C56's measurement rather than by this
paragraph.

**F8/2 — `session_start_result` is operational, and its rationale must say why that is not a
demotion (owner: i).** Required rationale, in substance: it authors no rule; it aggregates the
agent roster and re-delivers rules owned elsewhere (role declaration, the memory-read rule,
delegation-by-default) at session start — **and on Codex it is the only delivery channel for the
delegation rule**, because `@`-imports are not expanded there (C39). Delivery is not ownership, so
the classification stands; without the second half a reader mistakes "operational" for
"incidental". Rejected: a separate `role.declaration.session-start` ID beside
`role.declaration.switch`, which is legal under the one-to-one rule (different subsets) but spends
two IDs and two prose markers on one rule.

**F8/3 — `verify.owner-verify-d2` declares that its coverage is the consumer's (owner: a + c3).**
The callable observes only the globs a consumer sets in `[d2_ledger] sensitive_paths`; unset, it
returns `None`. The marker therefore states the dependency, and C59 reports `configured` /
`not configured` so the state is visible rather than assumed. What the unconfigured state actually
costs is one channel of three: the pre-commit `d2_ledger.py check --changed` **over**-warns when
unconfigured (it cannot discriminate, so it warns on everything — a recorded owner decision) and
the SessionStart counter still runs off `D2_LEDGER.md`. **Adopted for later, not here (c3):** the
future `init` slice seeds a narrow archetype-derived default, moving the default from *off* to
*on and narrow* without touching existing consumers — `sync` preserves every key it does not own.
**Rejected (c1):** erroring when a ledger exists with no globs configured contradicts the
warn-first decision in [ADR 0007](../decisions/0007-d2-ledger.md) §4 — a red gate before the habit
holds gets routed around — and punishes a project that keeps the ledger deliberately by hand.
Under the former Python 3.9 floor, an older host read the globs as empty because `tomllib` was
unavailable. C68/D2-34 later removed that supported-host limitation with one Python >=3.11 floor;
import failure remains conservative but is no longer a supported runtime.

**F8/4 — marker line grammar (locked).** `Runtime check: <id>` — the ID is the **first token**;
anything after ` — ` is human prose the parser ignores. The tail is not decoration: five of the
six markers claim a *subset*, and a subset can only be described in words.

**F8/5 — two namespaces, one shape (locked).** Policy IDs (`commits.owner-owned`) and F1 finding
codes (`caps.always-loaded`) are stable dotted slugs that look alike and are **separate
namespaces**. The parser cannot confuse them — it reads only `Runtime check:` and `Policy ID:`
lines — so no `policy.` prefix is added, which would lengthen every ID to solve a problem only
human readers have. C53 must state this rather than leave it to be inferred.

**Implementation scope, deliberately not done at design time.** F8 fixes the table; C53 performs
the tree changes it implies, in one pass under its own gate: convert the three live
`> **Enforced** (not just documented) by …` blocks (Privilege escalation, Commits & ownership,
Analysis before mutation) to marker lines, add the two missing markers (`verify.owner-verify-d2`,
`delegation.tier-floor`), write the `## Role declaration` section, and add `Policy ID:` /
`Runtime classification:` metadata to the seven docstrings. Converting the prose before the
checker exists would leave the tree asserting a join that nothing verifies — the exact stage-1
defect this shape targets. Annotation growth is remeasured by C56 against the always-loaded caps;
the draft no longer assumes a fixed nine-line cost or that it fits before measurement.

**Seeded violation.** Unknown, duplicate or prose-less policy ID; prose ID with no callable;
public result without classification; operational classification with empty rationale or a prose
marker; dual classification; malformed ID; legacy live `Enforced by`/`**Enforced**` declaration;
or delete on either side makes `self_ci` fail.

**Five rules above are not reachable from that list** (A17(g) plus the D2-20(d) owner walkthrough,
per F13). **The F8 set itself is unpinned:** every mutation there is structural, so an ID renamed
consistently on both sides preserves the one-to-one join and passes, and *unknown* has nothing to be
unknown against, because F7 rejects a central mapping constant. C53 therefore ships a **contract
test pinning the seven shipped callable classifications: six callable↔policy-ID pairs plus
`session_start_result`'s operational assignment**; a coordinated ID rename or a changed operational
assignment fails there. It is a regression pin, not a join mechanism — the join still runs
prose→docstring at check time, and what F7 forbids is a constant standing *between* the two sides.

**F8/2's rationale has a required substance,** and the empty-rationale seed proves only that a
string exists. The rationale F8/2 dictates — delivery is not ownership, and on Codex this is the
delegation rule's only delivery channel — is pinned as shipped text; replacing it with a non-empty
but substantively wrong rationale fails the contract fixture. For any operational classification
added later, only non-emptiness is mechanical and review owns the substance, which is stated rather
than left to be inferred.

**F8/3's coverage finding needs its own emitting seam and seed.** C53 extends the existing
`tools/d2_ledger/d2_ledger.py` check path with a C51 `Finding`; coverage is evaluated before the
current no-pending early return, so an empty ledger cannot hide whether `sensitive_paths` is
configured. A configured fixture must produce `configured`, an unconfigured fixture must produce
`not configured`, and emitting neither or the wrong state fails the C53 contract suite — otherwise
C59 reports a state nothing guarantees is emitted.

**The five subset tails are part of the shipped contract even though the join parser ignores their
human prose.** The contract fixture pins the limitation stated for each subset; deleting that tail
or replacing it with a whole-section enforcement claim fails. This is deliberately not semantic
parsing by `self_ci`: the finite shipped set is the F15 regression surface, while review owns the
substance of later prose.

**The diagnostic coordinates are also a contract.** For each seeded join failure, the contract
suite asserts that `self_ci` reports the policy ID, callable and prose location, explicitly naming
the absent side where the violated relation has no coordinate. A detector that fails without those
coordinates fails the test; a red result that cannot lead the reader to both sides does not satisfy
the canary's purpose.

## 4. Version ↔ changelog cross-check (P1.3 → C54)

**Frame — the join that does not exist.** The tree carries **four independent version
carriers** and nothing relates any two of them: `pyproject.toml` (`version = "0.4.0"`, the
literal hatchling stamps into the wheel), `src/akmon/__init__.py::_STATIC_VERSION`
(`"0.4.0.dev0"`, the fallback when the package is not installed), the topmost CHANGELOG
heading, and the git tag. The first two **already disagree with each other** in the live tree,
and no check reads either of them.

This is not a hypothetical. **The defect shipped in the last release**: the tree at tag
`v0.3.0` carries `version = "0.3.0.dev0"`, so a wheel built from the reviewed state is named
`0.3.0.dev0`; the follow-up commit `1a9ab0f`, subject "v0.3.0 package version", then set the
literal to `0.4.0` — the string `0.3.0` never existed in the tree at all. It reproduces because
the release plan (`release_check.run_plan`) tells the owner to stage `CHANGELOG.md` and never
mentions a version literal, while `__init__.py` asserts in a comment that "the release pipeline
cuts the real version from the git tag" — untrue under a static hatchling version, where the tag
influences the built artifact not at all. A rule akmon states and nothing verifies, in the
release domain.

The cost lands on the consumer: package mode stamps `akmon_version` from installed metadata
(PEP 440, no `v` — `bin/sync.py::_package_mode_akmon_toml`), mounted mode stamps
`git describe --tags` (`v0.2.0`-shaped — BOOTSTRAP §`.akmon.toml`), and the bump procedure
computes its window from CHANGELOG headings. `0.3.0.dev0` matches no heading, so the window is
uncomputable and the consumer reads nothing before accepting a pin.

**Decision (owner-locked as register fork F9).** In
`tools/release/release_check.py`:

- a **non-final** version **requires** `## Unreleased` as the topmost CHANGELOG heading.
  Non-final is the full PEP 440 set — `.devN`, `aN`/`bN`/`rcN`, `.postN`, `+local` — not `.devN`
  alone; final is
  exactly `X.Y.Z` (**F9/3**);
- a final version **requires** the topmost released heading to equal it;
- a final version that already has a matching git tag is a **warn** (a re-release), not an
  error — tags are owner-run and the check must not fight a legitimate retag;
- `pyproject.toml`'s version and `_STATIC_VERSION` must be **literally equal** — one release
  bump is two edits, and this is the check that says so (**F9/2**);
- every git tag `vX.Y.Z` **should** have a `## vX.Y.Z` heading — **warn, not error** (**F9/5**);
- when no version source is found at all, the check emits an explicit **skip finding**, never
  silence (**F9/4**);
- version **comparisons normalize** before comparing: strip a leading `v`, and treat a
  `git describe` suffix as "ahead of that tag" rather than as a different version (**F9/6**).

Two repairs outside the checker belong to the same task, because a check that reports a defect
the procedure keeps producing is theatre:

- `run_plan` prints the version bump **before** `git add` — edit `pyproject.toml` and
  `src/akmon/__init__.py`, then stage both explicitly. This is the exact step whose absence put
  `0.3.0.dev0` inside the `v0.3.0` tag;
- the `__init__.py` comment is corrected to say what actually happens: the literal in
  `pyproject.toml` is the built version, the owner bumps it as a release step, and the tag
  records the reviewed state rather than producing the number.

**Current-state repair (F9/1): `0.4.0.dev0` + `## Unreleased`.** Owner choice, over cutting a
`## v0.4.0` heading now. v0.4 is not finished — D2-20 is unverified and the wave is not in
history — and a released heading with no tag names a release that does not exist, against this
changelog's own "no dates — the git tag is the timeline" convention. It also makes the two
literals agree at no cost and matches what the
[codex-runtime-contract release class](codex-runtime-contract.md) already argued and what the
alphavar pilot is already stamped with.

**The repair is executed inside C54, not before it** — deliberately, and this is the one place
where "fix the tree first" would destroy evidence. P1.3's acceptance is the live pair: the
checker must be observed failing on today's `0.4.0` + `## Unreleased` and passing after the
repair, in that order, in one task. Repairing now would leave the check with a fixture where it
could have had the tree.

**Fork — make the git tag authoritative.** Rejected for this stage. A dev version legitimately
runs ahead of every tag, so a tag-equality requirement would fail continuously and get waived.
The tag participates only as the re-release warning above.

**Fork — one version literal (F9/2).** Rejected as impossible, not merely undesirable:
`pyproject.toml` is deliberately excluded from the packaged tree, so an installed package cannot
read it, and the fallback literal has to exist. Deriving the version from the tag at build time
(`hatch-vcs`) is rejected separately — a dev version legitimately runs ahead of the tag, and
vendored/submodule mounts carry no package metadata to derive from. Two literals, one equality
check.

**Fork — error on a missing version source (F9/4).** Rejected: it fails every non-Python
consumer for having no `pyproject.toml`. The opposite failure — passing quietly — is the one this
stage exists to remove, so the skip is a reported finding with its own class, not a silent
return.

**Fork — error on a tag with no heading (F9/5).** Rejected: tags are immutable, so a historical
gap can never be repaired into green and a hard error would be waived within one release. Warn
keeps it visible for the gaps that *can* still be filled. Both this and the tag-matching warn
need `git`; absent, they degrade into the same explicit skip as F9/4.

**Spun off, not decided here (F9/6).** `cli.py::_skew_notice` compares the recorded pin to
`__version__` by raw string equality and prints `v{pinned}`, so a mounted `v0.3.0` pin fires the
notice on every command and renders it "v v0.3.0". That is a defect with a right answer, not a
fork the owner should have to vote on; F9 fixes only the *rule* (normalize before comparing) and
[C61](../TASKS.md) owns the code.

**Seeded violation.** The two consistent states pass. Their negatives are separate: a non-final
version whose topmost CHANGELOG heading is not `## Unreleased` fails `release_check`, and a final
version whose topmost released heading is absent or does not equal that version fails. The
non-final case is parameterized over the full supported PEP 440 non-final corpus — `.devN`, `aN`,
`bN`, `rcN`, `.postN`, `+local`, and
their accepted combinations — rather than proving only `.devN`; every member requires topmost
`## Unreleased`. A CHANGELOG fixture with the matching released heading below a different topmost
released heading fails, so searching for a match anywhere is not sufficient. Disagreeing
`pyproject`/`_STATIC_VERSION` literals fail. Tag coverage is checked across the complete tag set:
with several `vX.Y.Z` tags, any tag lacking its heading warns without failing, even when the newest
tag has one. A fixture with no version source at all produces an explicit skip finding rather than
a pass, and a fixture where `git` is unavailable produces the same explicit skip for each
git-dependent rule rather than silence or failure. **The two repairs outside the checker are seeded
too** (A17(g), per F13): a `run_plan` that stages `CHANGELOG.md` without both version literals
fails, and one that reaches `git add` before the bump step fails. Their absence is what makes this
shape's own defect reproducible — a checker that reports a mismatch the procedure keeps re-creating
is the theatre this section already rejects, and leaving the procedure unseeded left that door open.

**That claim was wider than what it seeded, and two checker rules had no mutation either**
(A17(g), per F13). Both named mutations are `run_plan` mutations, so the second repair outside the
checker — the `__init__.py` comment asserting that the release pipeline cuts the real version from
the git tag — was covered by a sentence and by nothing else. It is a literal string in a source
file, and the false form is half of why the defect reproduces, so the `release_check` contract suite
in `meta/tests/test_release_check.py` pins it: a tree whose comment still claims the tag produces
the number fails that contract test. **F9/6 and the re-release warn:** a
checker comparing raw strings passes every fixture listed above while failing on the `v`-prefixed
and `git describe` forms F9/6 exists for, and one that *errors* on a final version with a matching
tag passes them too, because no fixture there distinguishes warn from error. Normalization is
seeded over `v0.4.0`, `0.4.0` and a `git describe` suffix; the re-release case asserts **warn**,
not merely non-clean.

**Delivered (C54).** `tools/release/release_check.py::check_release_versions` joins the four
carriers and reports through the shared envelope, wired into `--check` (a release-time gate:
the tree's steady mid-cycle state — non-final over `## Unreleased` — is exactly what it accepts,
so it is not also a `self_ci` leg). Codes: `release.version-literals`,
`release.changelog-window`, `release.retag` (warn), `release.undocumented-tag` (warn),
`release.check-skipped` (warn). Eight implementation choices the lock left open are recorded for
owner verification as **D2-31**; two are worth naming here because they close a gap the lock
did not see. First, the final/non-final classification is **binary by construction** — final is
exactly `X.Y.Z` with no `describe` distance, and *every* other spelling is non-final (a leading `v` is a spelling of the same version rather than a difference, since `git describe` supplies it) — so no
version can fall between the two heading rules and escape both; F9/3's PEP 440 enumeration is
then a subset the corpus proves rather than the definition. Second, a rule that does not
**apply** is not reported as skipped: under a non-final version there is no re-release question,
so git's absence skips tag coverage alone. F9/6's normalizer was **lifted** rather than copied,
per C61's carried-forward note: the new stdlib-only `common/versions.py` owns both `split_version`
and `is_final`, and the lift found a *third* owner — `src/akmon/_init.py::_tag_for_version`
classified by substring (`.dev`, `a`, `b`, `rc`, `+`), missing `.postN` and resolving an
installed `0.4.0.post1` to the non-existent tag `v0.4.0.post1`. That repair is a behaviour change
in `akmon init` outside this section's scope and is the part of D2-31 that most needs a look.
**The checker was then reviewed adversarially against itself** (twenty seeded mutations of the
checker, the spelling module, the attach helper and the plan). Fifteen were caught by the
carriers as written; of the five survivors, two were mutations of redundant code — the released
heading is anchored twice, by `^` in the pattern and by `.match`, so removing either alone
changes nothing, and the honest mutation removes both — and three were real. **Two were test
gaps**: "literally equal" was never seeded against an implementation that normalizes first
(`v0.4.0` vs `0.4.0` must still fail), and which literal is authoritative was decided by nothing
(`pyproject` wins, because it is the literal that names the wheel). **Three were defects.** Tag
coverage returned **silently** when `CHANGELOG.md` was absent — the same silence F9/4 exists to
remove, now an explicit skip. The tag list was filtered to `vX.Y.Z`, so a project that cut
`1.2.3` was invisible to *both* git-dependent rules and nothing said so. The owner ruled during
the repair that `vX.Y.Z` **is** the release tag's only admissible spelling, so the fix is not to
widen the population but to stop the silence: such a tag is now reported as
`release.tag-spelling` (warn) and then excluded, which states the rule instead of enforcing it
invisibly. And `--plan` stopped at the push, leaving the tree at a released
version whose tag exists, so every later `--check` reported a re-release — the procedure
re-creating what the checker reports, which is the exact failure this section already named
once. The pattern across both passes is worth recording: every real defect was either a **silent
non-run** or a **rule that read one spelling of something it compares in two**.

One carrier the frame did not count turned up during the repair: `uv.lock` records the project
version as well, making five. It gets no rule, because `uv` rewrites it from `pyproject.toml`
without being asked — it re-synced itself on the first command after the bump — so it is a
derived copy rather than an independently maintained one.

The live tree was observed **red** — `error release.version-literals` (`0.4.0` vs `0.4.0.dev0`)
and `error release.changelog-window` (final `0.4.0` over a topmost released `## v0.3.0`) — before
the F9/1 repair, and green after it, in that order.

## 5. Source/generated boundary (P1.7 → C55)

**Decision (owner-locked as register fork F17/A).** **The generator is the one declaration.** Every
`PlannedFile` produced by `sync.py` carries exactly one required ownership mode; the mode and any
selector live on that object and are consumed by write, `sync --check`, `verify.py` and the
contract suite. There is no banner-exception list, field-owner list or second path inventory.

| ownership mode | declaration and check |
|---|---|
| `bannered-file` | `sync` owns the whole text file; the planned content must carry the exact akmon generated banner in its permitted prefix, and content drift remains checked exactly |
| `structured-file` | `sync` owns the whole file, but the format cannot safely carry a comment; exact planned content is the ownership proof while the declaration exists, with no fabricated banner |
| `field-owned` | the surrounding file is hand-owned; the `PlannedFile` declares the exact keys or entries `sync` owns, merge preserves everything else, and checking compares only those selectors |

The current population is classified in the same declaration. Generated Markdown and Python
pointers/materializations are `bannered-file`; wholly generated JSON such as `.codex/hooks.json`
is `structured-file`; merged `.claude/settings.json` hook
entries and package-mode `.akmon.toml`'s `mount` / `akmon_version` keys are `field-owned`.
*(C77 narrowed the package-mode materialization to the guardrails `AGENTS.md` imports — bannered
Markdown — so the routing registry that used to be this section's `structured-file` example is no
longer written into a consumer at all. `sync` now also removes everything unplanned under
`<aitna>/.akmon/` regardless of banner, since nothing else writes there; the banner rule below
still governs the wider scanner boundary, where other writers do exist.)* Adding a
fourth implicit state is forbidden: a constructor with no mode, a field-owned entry with no
selector, or one path declared in two modes fails the contract suite.

The forward and reverse banner checks are deliberately limited to the population for which both
claims are mechanically true:

- a planned `bannered-file` whose planned content lacks the exact banner produces an **error**
  C51 `Finding` with code **`boundary.missing-banner`**;
- a file carrying that exact banner inside the scanner boundary, but absent from the current
  `bannered-file` planned paths, produces an **error** C51 `Finding` with code
  **`boundary.stale-generated`**.

**Scanner boundary.** The reverse scanner covers only generator-declared bannered output surfaces:
the root vendor-pointer population (`CLAUDE.md`, `GEMINI.md`, `.github/copilot-instructions.md`,
`.codex/README.md`), generated `.claude/skills/*/SKILL.md` and `.agents/skills/*/SKILL.md` stubs
(C79 added the second; a stub carries its banner in the `#`-comment form on line 2, inside its
frontmatter), and banner-capable package materialization below the configured `<aitna>/.akmon/`. It does not turn those parent directories
into general scan roots. Arbitrary consumer-root paths and subtrees are out, as are `AGENTS.md`,
the mounted standard source tree `<aitna>/akmon/`, VCS/cache paths, and every `structured-file` or
`field-owned` output. Do not follow symlinks; inspect regular UTF-8 files only. A candidate must
carry, within its first four logical lines, either the HTML-comment or `#`-comment form of
`Generated by <root>/akmon/bin/sync.py. Do not edit this file by hand.`; a bare `Generated by ` or
the exact marker later in a file is not ownership evidence. The `<root>` segment is accepted
independent of the current configured root so a stale artifact written before a root rename remains
visible. Structured and field-owned entries remain checked through exact content or selectors
while declared; after their declaration disappears they carry no safe, truthful marker by which a
generic scanner can identify them.

`AGENTS.md` is a separate split-ownership case, not an untyped fourth `PlannedFile` mode. The
consumer owns the file; akmon owns the contract of the marked akmon block for attach/verification
and §6 counts that block as shipped context, but `sync` does not materialize the file. Therefore
`AGENTS.md` is outside the generated-banner population and retains its existing verification that
the whole file must not carry an akmon generated banner. In §6, “one artifact with split
ownership” means the one **always-loaded** artifact of that kind; `.claude/settings.json` and
`.akmon.toml` remain the field-owned generator cases declared above.

**Fork — content-hash drift detection instead of ownership modes.** Rejected as a duplicate:
`sync --check` already compares planned content. It cannot find a bannered artifact after the path
has left the plan, and a whole-file comparison falsely claims ownership over hand-written JSON/TOML
fields. This shape checks the declaration and the reachable stale direction rather than renaming
content drift.

**Deferred, explicitly rather than silently.** The plan folds doc gardening (dead links,
staleness) into P1.7 "as the same sweep". It is not the same sweep — link checking needs its own
traversal and its own noise budget — so it leaves stage 1 and is carried in **C60**'s neighborhood
as a later item, not dropped.

**F13 carriers.** **The consumer checker is `verify.py`**, through the C51 finding envelope; the
boundary is a property of a tree `sync` has run in. The contract suite keeps each rule isolated:

- **forward:** mutate a `bannered-file` renderer to omit its banner, run `sync` so disk and planned
  content agree, then require `verify.py` to emit exactly one error
  `boundary.missing-banner`; content comparison is green, so this cannot pass through the old
  drift check;
- **reverse:** write a bannered path from the old declaration, remove that path from the new plan
  without deleting the file, and require exactly one error `boundary.stale-generated`; no planned
  path is stale or missing, so only the scanner can fail it;
- **population:** parameterize mounted and package-mode `_planned_files` and pin every shipped path
  to its mode and, for `field-owned`, its selectors. An unclassified path, a dual mode, a missing
  selector, `.codex/hooks.json` classified as bannered, or merged settings classified as whole-file
  fails the contract test;
- **scanner kinds:** separate fixtures present the same marker through a symlink, a non-regular
  entry and a non-UTF-8 regular file; each produces no boundary finding, while changing the scanner
  to follow, decode or classify that kind fails its exact empty-finding oracle;
- **banner position and root:** an otherwise stale in-scope artifact with the exact marker on
  logical line four produces exactly one error `boundary.stale-generated`; moving that same marker
  to logical line five produces no finding. A separate stale artifact carrying the exact marker
  with a previous configured root in its `<root>` segment produces exactly one error
  `boundary.stale-generated`. Moving the position limit or matching only the current root fails the
  corresponding isolated fixture;
- **scanner population:** four positive stale fixtures independently exercise a root vendor
  pointer, a generated `.claude/skills/*/SKILL.md` stub, a generated `.agents/skills/*/SKILL.md`
  stub and a banner-capable package materialization;
  each must emit exactly one error `boundary.stale-generated`. Separate negative fixtures put the
  exact head marker in `AGENTS.md`, the mounted akmon source tree, an arbitrary root user file, an
  arbitrary file under `.github/`, `.codex/`, `.claude/` or `.agents/`, a VCS path and a cache path; each must
  emit no boundary finding. Dropping or widening any one scope boundary therefore fails without
  another zone masking it;
- **non-banner modes:** representatives of `structured-file` and `field-owned` omit the banner and
  produce no boundary finding while their exact-content or selector checks remain green. Treating
  either mode as banner-required or reverse-scannable fails its isolated empty-finding oracle;
- **self-CI seam:** `meta/self_ci.py` runs the same boundary implementation over fixtures generated
  from akmon's own mounted- and package-mode declarations. A fixture whose renderer omits a banner
  must make `self_ci` fail with `boundary.missing-banner`; removing that invocation therefore
  cannot leave akmon exempt while consumer tests stay green;
- **severity and code:** the forward and reverse fixtures assert C51 `severity == error` and the
  exact codes above, not merely a non-clean exit. Changing either to warn, swapping the codes, or
  emitting an unstructured diagnostic fails its own parameterized oracle.

Rejected: `self_ci` alone — it proves akmon's declaration and fixtures, not an attached consumer
tree. C55's only task dependency remains C51; the §6 always-loaded definition is a declaration it
consumes, not C56 work it waits for.

## 6. Always-loaded caps (P0.4 → C56, reduction in C60)

**Declaration — the two exact populations (owner-locked as F18/A).** This definition is also
consumed by C55; it is not a C56 task edge. `AGENTS.md` is hand-owned, `sync` does not generate it,
and only its marked akmon block belongs to the shipped population. The block begins at
`## Dev layer — akmon` and ends before the next peer `##` heading or EOF. Resolve its always-loaded
guardrail imports transitively; the chain includes `guardrails/_common.md`. Add the selected
language guardrail, then count the union once so an imported selected file is never doubled.

- **akmon-shipped always-loaded** = the marked `AGENTS.md` block + the imported guardrail chain +
  the selected language guardrail;
- **consumer total always-loaded** = the whole consumer `AGENTS.md` + that same resolved guardrail
  chain and language guardrail.

Vendor pointers, hook wiring, roles, pipelines, skills and every on-demand document are outside
both populations. The line unit is `len(text.splitlines())`; the byte unit is
`len(text.encode("utf-8"))`. Counts are summed per member with no synthetic separator. Byte caps are
decimal bytes, not KiB, and both dimensions are inclusive.

Measured on the attached consumer (N2, P0.4): **433 lines / 23,613 bytes** consumer-total, of which
the whole hand-owned `AGENTS.md` is 232 lines; the then-current shipped population is approximately
**197 lines / 10,800 bytes**. These are evidence and report inputs, not replacement thresholds;
C53 and C58 both write into the measured chain and C56 reports the post-change values.

**Decision — one stable code, two strengths:**

| scope | inclusive cap | finding when over cap | checker |
|---|---|---|---|
| akmon-shipped always-loaded | **210 lines / 12,000 bytes** | `error`, code `caps.always-loaded` | `self_ci` |
| consumer total always-loaded | **460 lines / 25,000 bytes** | `warn`, code `caps.always-loaded`; severity remains `warn` under strict mode | `verify.py` (`--strict` exits non-zero) |

The strengths differ because the largest consumer-total member is hand-owned: a normal verify run
must not fail a project over its own `AGENTS.md`. Akmon's shipped population is wholly ours, so its
growth is an error. Strict mode applies the shared exit policy to the consumer warning; it does not
rewrite the finding as an error.

**Rejected here, preserved as separate work.** A single hard consumer-total cap dictates
hand-owned content; a single warn-only cap makes akmon-owned growth advisory. Adopting the borrowed
≤150-line reference immediately ships a red cap that will be waived, and inheriting that number
would confuse a differently shaped artifact with evidence about akmon. Deferring every cap leaves
the reduction without an instrument. The accepted ratchet deliberately blesses today's shape;
therefore reduction has its own task, **C60**, which must justify its target before it moves content
and lowers the caps. C60's relocation-versus-deletion fork remains in-task and outside this lock.

**F13 carriers.** Each rule is isolated:

- **population include/exclude:** parameterized fixtures add and remove, one at a time, the marked
  akmon block, an imported common guardrail and the selected language guardrail; the shipped count
  must change by that member's exact lines and bytes. Replacing the marked block with the whole
  `AGENTS.md` fails the shipped oracle. The consumer-total oracle changes by the whole `AGENTS.md`
  and the same chain. Adding a vendor pointer, hook wiring, role, pipeline, skill or on-demand file
  to either population fails, as does omitting or double-counting a transitive import;
- **inclusive line boundaries:** for each scope, fixtures measure exactly 209/210/211 shipped lines
  or 459/460/461 consumer-total lines while bytes remain below their cap. Cap−1 and cap pass; cap+1
  alone emits exactly one `caps.always-loaded` finding with the scope's declared severity;
- **inclusive byte boundaries:** for each scope, fixtures measure exactly
  11,999/12,000/12,001 shipped bytes or 24,999/25,000/25,001 consumer-total bytes while lines remain
  below their cap. Cap−1 and cap pass; cap+1 alone emits exactly one `caps.always-loaded` finding
  with the scope's declared severity;
- **severity and strict matrix:** shipped cap+1 is one `error caps.always-loaded` and makes
  `self_ci` fail. Consumer cap+1 is one `warn caps.always-loaded`; normal `verify.py` remains zero,
  while `verify.py --strict` exits non-zero with the same warn finding. A changed code, downgraded
  shipped severity, upgraded consumer severity, duplicate finding or wrong exit fails the exact
  matrix oracle;
- **dynamic report:** both checkers report, for their own scope, the exact dynamic
  `lines=<actual>/<cap>` and `bytes=<actual>/<cap>` plus the scope name and code
  `caps.always-loaded`. The line-only mutation replaces one one-byte non-newline character with a
  newline, changing the line actual while holding the byte actual fixed. The byte-only mutation
  adds one byte within an existing logical line, changing the byte actual while holding the line
  actual fixed. Separate line-cap and byte-cap mutations change only their corresponding rendered
  cap while holding both actuals and the other cap fixed. Omitting a dimension, printing the other scope, reporting a stale constant or swapping
  actual and cap fails the exact-output fixture.

## 7. OS contract and matrix vocabulary (P0.2 → C57)

**Declaration (runtime).** Akmon requires **a POSIX shell and `python3` on PATH**. The Codex route
additionally requires **git on PATH**: generated Codex wiring resolves the project root through
`$(git rev-parse --show-toplevel)` (`bin/sync.py:203`), while Claude wiring uses the
harness-provided `$CLAUDE_PROJECT_DIR` (`:258`). **`claude` and `codex` are optional**: §8 queries
each one found on PATH and, independently for each absent harness, falls back to and discloses its
declared version. **Windows is unsupported**, not merely untested.

**F16 — one declaration, two population-specific joins.** Every runtime entry declares its
population and modality. *Generated wiring* contains the implicit POSIX-shell carrier plus literal
`python3` and route-scoped `git`; C57 derives that population from the emitted command entries.
*Akmon's own tooling* contains optional `claude` and `codex`; one declarative vendor-command map is
read by the checker and is also the sole source from which `sync` constructs harness-version
subprocess calls and downstream adopters obtain optional-harness executable operations. C70 later
uses that owner for Codex app-server startup while owning the `hooks/list` protocol and evaluation;
C57 does not wait for its downstream adopter. The
modalities are `required`, `optional`, and `required-on:<route>`; the exact assignments are POSIX
shell=`required`, `python3`=`required`, `git`=`required-on:codex`, and `claude`/`codex`=`optional`.
The map is the single owner, never a manually synchronized copy beside the calls.

**C57 build-time owner decision — the second-opinion command joins the map (owner choice, the
middle path).** *(Ledger: **D2-30**, owner-verified — this amends the
ownership contract D2-20 verified.)* F16 calls the vendor-command map "the sole executable owner and constructor" for
own-tool operations, and implementation found the one live counter-example: no Python source
spelled `claude` or `codex` at all, but `tools/model_routing/registry.json` did, in
`second_opinion.cli` / `invoke`, and `routing.second_opinion_command` built an argv from them.
The owner's decision splits ownership by *kind* rather than moving everything: the map owns the
**executable name and every operation**, while the registry keeps second-opinion **policy**
(`model_flag`, `report_dir`) and refers to the map by harness name — `cli` becomes
`harness: "claude"`, `invoke` becomes `operation: "review"`. The ownership line is exact: the map
owns the **executable and the operation prefix**, and `routing.second_opinion_command` appends the
registry's `model_flag` and the prompt as a **policy tail**. That is not a second constructor — a
model pin and a prompt are policy the registry owns, not facts about how a vendor's CLI is
spelled — and stating it as "one place builds the whole command" would be false the moment a
model flag is inserted. What the map forbids is a second answer to what a harness is called or
how an operation is spelled. Rejected: folding the whole second-opinion command into the map, which pulls policy out of
the registry and reopens an ADR 0005 / C15–C16 contour whose D2-1 is still pending; and fencing
the rule to version/protocol queries only, which would leave `runtime.duplicate-query-owner`
with no live target — the shape §1 calls a defect of the check. Accepted cost: the registry
schema changes, so `registry_hash` moves and every consumer's local model-routing config goes
stale until re-init — the SessionStart hook already reports that, and the CHANGELOG carries it as
a migration line.

**The duplicate-owner scan is scoped to the operative Python surface** (`bin/`, `hooks/`,
`tools/`, `src/akmon/`) and looks for a *bare string constant* equal to a harness binary. Tests
are excluded — a fixture naming a harness describes the map rather than bypassing it — and data
files are excluded because the registry now refers to the map **by name**, which is the point of
the decision above. Measured at implementation: after the change, no source outside
`common/runtime.py` spells either binary.

**Modality is derived, not restated.** A binary present in every vendor's generated wiring is
`required`; one present in a single vendor's wiring is `required-on:<that vendor>`. The
declaration is checked against that derivation, so wiring that stops resolving the root through
`$(git rev-parse …)` makes the `git` declaration fail rather than quietly outliving the fact it
described. Measured on the tree at implementation: `claude → {POSIX shell, python3}`,
`codex → {POSIX shell, python3, git}`, reproducing §7's declaration exactly.

The pure runtime checker reports through C51 with this exact mapping:

| violation | severity and code | normal exit |
|---|---|---|
| source invokes an undeclared runtime | `error runtime.undeclared-binary` | non-zero |
| declaration is unused by its declared population | `warn runtime.unused-binary` | zero |
| runtime is assigned to the wrong population | `error runtime.wrong-population` | non-zero |
| runtime has the wrong modality or route condition | `error runtime.wrong-modality` | non-zero |
| a second query owner or call-site literal bypasses the query map | `error runtime.duplicate-query-owner` | non-zero |
| a generated command uses a construct the parser will not claim to have read | `error runtime.unparsed-command` | non-zero |

The error/warn asymmetry is F9's: an under-declaration breaks a consumer path, while an unused
entry is stale prose. F16's accepted cost is the indirection and weaker extraction evidence of the
own-tool query map; its rejected alternative is dropping `claude` and `codex` from the declaration,
which restores silence around the binaries §8 uses. **Windows support is a fenced scope declaration,
not a mechanically checked rule**; its lack of a seed is explicit rather than an exemption claimed
for a check.

**Declaration (matrix vocabulary).** A capability records exactly **six independent axes**:
`documented`; `delivered`; the complete `vendor / version / event / matcher` route coordinate; the
observed normal-path effect (`none / advisory / ask / deny`); crash posture
(`fail-open / fail-closed / unmeasured`); and `evidence`, the probe or report behind the claim.
Every axis is present. C57 chooses the concrete prose encoding for `documented`, `delivered`, route
and evidence as an in-task decision; this lock pins their presence and the evidence relation, not a
closed spelling for their values. Only effect and crash posture have closed value vocabularies here.
An `ask` or `deny` effect requires all four route coordinates to be present and measured, and a
measured crash posture. A measured assertion requires non-empty evidence; an `unmeasured` assertion
requires empty evidence. Requiring a citation only in free prose is rejected because a pattern
cannot distinguish evidence from decoration.

**F19/A — where the matrix lives.** C57 creates shipped top-level `CAPABILITIES.md`, beside
`MODEL.md` and `ARCHETYPES.md`, and writes the six-axis cells as prose. README retains a short
delivery summary with **no vendor enforcement claim**. A16 later owns schema, data ownership and
generation and consumes these cells into the same file; until then, the acknowledged cost is one
top-level document and a bounded prose/data duplication window. Rejected: compact README cells plus
a legend, which compress the axes back into an overloaded grade; and a matrix under `meta/`, which
hides a consumer contract in maintainer material.

**Checker scope.** The top-level `CAPABILITIES.md` and its marked matrix region are both required;
absence of either is `matrix.missing-file`. Only rows inside that region are eligible matrix rows,
and all six axes, all four route coordinates and the closed effect/crash vocabularies are mandatory
there. There is no fallback to a legacy
README table or to a six-axis matrix anywhere else. In shipped docs outside the marked region,
`enforced`, `enforces`, and `✅`/`⚠️` adjacent to a vendor or harness event are rejected. A retained
detailed README capability table is therefore a second authority and fails as
`matrix.bare-claim`, even if `CAPABILITIES.md` is valid. Two exclusions are exact: claims about
akmon's own in-process checkers remain valid (`pipelines/tasks.md` may say a threshold is enforced
by `verify.py`), and guardrail runtime prose remains C53's F7/F8 surface rather than a second C57
scan.

**C57 build-time owner decision — two named claims carry an unmeasured crash posture as a
warn.** *(Ledger: **D2-29**, owner-approved; the global-warn variant first shipped was rejected.)*
The rule above requires an `ask`/`deny` effect to carry a measured crash posture, and
akmon's only two enforcement claims (the Claude commit guard, `deny`; the Claude delegation
nudge, `ask`) have no such measurement anywhere in the tree: F3 *decided* crash-open, and N1/F4
measured it live for **Codex only**. Converting therefore left the repaired tree red on exactly
two rows, against this section's claim that it then passes. The owner's decision exempts **those
two claim identities**, and only from the crash-posture branch: over their `unmeasured` crash
posture `matrix.unqualified-effect` is a `warn` — non-strict `self_ci` returns zero, `--strict`
still fails — while every other `ask`/`deny` claim with an `unmeasured` crash posture, and every
`unmeasured` route coordinate, stays `error`. The exemption is a closed list in the checker
(`meta/checks/capabilities.py::CRASH_POSTURE_EXEMPT`, whole `###` titles) that only shrinks, and
its removal is a test rather than a promise: a carrier fails once either claim records a measured
crash posture while it is still listed, and fails when a listed title names no live claim. The
two rows are owned by **C52**, whose D2-23 gate exists to produce exactly these numbers; §Order
already states that missing runtime numbers must not hold C57 behind an unrelated measurement
campaign, and an unconditional `error` would have done precisely that. Cost: two hardcoded claim
identities in the checker, so renaming either claim turns the tree red for a reason unrelated to
what changed — loudly, since the renamed claim loses its warn and the carrier names the stale
entry — and C52 inherits a carrier about a checker it does not otherwise touch. Rejected: a
global `warn` for the crash-posture branch, which would pass every *future* `ask`/`deny` claim
with no crash measurement in an ordinary run, permanently; a dated exemption, which needs a date
authority the tree does not have; citing F3 as the report behind `fail-open`, because F3 is a
decision plus vendor documentation rather than a measurement of akmon's own hooks — the
documented/delivered conflation this matrix exists to break, and a pre-payment of C52's gate;
measuring inside C57, which absorbs the campaign the lock detached it from; and lowering the two
effects, which is false in the other direction on the normal path. When C52 lands the
measurement, the two rows record it, the carrier goes red, and deleting the two list entries
restores the unexempted rule. *(Expired in C90 / D2-47: the measurement came from the C87 guard
and a probe — M69, M70, M77 — not from C52; both rows record `fail-open`, and the list went with
its last two entries.)*

**Post-implementation review corrections (N-review of C57).** Three defects in the delivered
checker, fixed inside C57 rather than deferred, because each one made a rule unenforceable:

* **A checked region had to prove it still holds claims.** Every six-axis rule runs over parsed
  rows, so any shape yielding zero rows passed silently: the whole matrix could be deleted down
  to a marker pair and `self_ci` stayed green. An empty region, a region holding only prose, and
  a second marker pair are now `matrix.missing-file`; a line inside the region that fits no claim
  form — prose, or a legacy glyph table smuggled into the one place the bare-claim scan
  deliberately does not read — is `matrix.invalid-value`. Both reuse existing codes rather than
  adding a seventh: the closed list is ADR text D2-20 verified, and a structural absence is what
  `matrix.missing-file` already names. A contract fixture pins the shipped claim population
  (19 claims: 9 Claude Code, 9 Codex CLI, 1 Gemini CLI), so deleting one claim is an edit to that
  list rather than an invisible loss of coverage.
* **The runtime join read one binary per command string.** `_binaries_in_command` took the head
  of the whole string, so `python3 hook.py && jq . | sed …` declared only `python3` and left
  `jq` and `sed` undeclared *and* unseen — a closed join that was not closed. The string is now
  split into executable segments on `&&`, `||`, `;`, `|`, `&` and newlines, each segment's head
  read past `NAME=value` prefixes and shell keywords, with POSIX shell builtins excluded because
  declaring the shell already covers them. akmon's real wiring has no compound command, so the
  derivation is unchanged; the fix also stops `cd` being reported as a host binary.
* **`delivered: yes` stood on a dry-run.** Both second-opinion rows claimed delivery on the
  evidence of `meta/tests/test_second_opinion_cli.py`, whose own docstring states that no test
  ever spawns the real `claude`/`codex`. A dry-run establishes what akmon emits, never what the
  harness accepts, and asserting it across two vendors is exactly the parity claim `AGENTS.md`
  requires a live probe for. Both rows now read `delivered: unmeasured` and cite nothing, which
  the evidence relation requires of an unmeasured row. The per-harness probe is **N8** and the
  regression carriers plus the matrix update are **C72**: a probe produces evidence, and landing
  a carrier is engineer work, so one task holding both would cross the role boundary the typed-id
  contract draws.

The declaration's own scope gap is a scope decision rather than a checker fix, and is **A20**
with its own note: `git` alone appears in four different modalities (route-scoped in generated
wiring, hard for two of the four mount modes, absent for the other two, and *fail-safe* in the
branch lookup, where absence makes the commit guard stricter rather than weaker), while
`uv`/`pytest` are contributor tooling that is not a host requirement in any population.

**Second review pass (same N-review, after the first round of corrections).** Four further
defects, each one a rule that could be satisfied without being true:

* **The segment splitter was a regex over the raw string.** It divided on operators *inside
  quoted arguments* (`--arg "a | b"` yielded a binary named `b`), lost the executable after
  `command` and `exec`, and read `(python3` out of a grouped list. The extractor now tokenizes
  with `shlex` under `punctuation_chars`, which separates operators while leaving the same
  characters inside a quoted token alone, then walks segments past `NAME=value` prefixes, shell
  keywords, wrappers and redirection targets. Constructs it does not read are **refused** as
  `error runtime.unparsed-command` rather than returning a confident under-count; a refusal also
  excludes the command from the derived population, since a refusal that silently shrank the
  population could flip a `required` modality to route-scoped and report a *second* wrong finding.

  **The supported grammar is narrow on purpose, and the refusal set is the honest half of it.**
  A first attempt skipped a wrapper's *name* and then read its first option as the binary —
  `env -i …` reported `-i`, `timeout 5 …` reported `5`, `xargs -n1 jq` reported `-n1`. Encoding
  five wrapper option grammars only relocates that defect to the sixth, so a wrapper is read only
  when the very next token is a plain word; a wrapper carrying options, or one like `timeout`
  whose grammar puts a mandatory positional before the command, is refused. Refused with it:
  backticks, an unbalanced quote, arithmetic expansion (which `$(...)` matching would otherwise
  read as a command substitution), and the `for`/`case`/`select` constructs, whose word lists are
  not command lists — `for f in *.py` reported a binary named `f`. `if`/`while`/`until` are
  *supported*, because each is genuinely followed by a command. An **external** wrapper is also
  counted as a requirement in its own right: `nice python3 hook.py` needs both binaries on the
  host, while `command`/`exec` are shell-provided and need only the shell.

  A second review pass found the refusal set still short by a whole class: constructs that open a
  grammar of their own. `foo() { … ; }` declared `foo` — a *definition* read as an invocation;
  `(( x = 1 ))` declared `x`; `[[ -f a && -f b ]]` declared `[[` and then, because the `&&`
  *inside* the brackets restarted the segment walk, `-f`. Each is now refused by token, not only
  at a head position. `time` joins them for a different reason: it is a shell reserved word in
  some shells and `/usr/bin/time` in others, so no reading of the command string can say whether
  a host binary is required — it was previously counted as an external wrapper, which asserted
  the harder of the two answers. Refusing a token does not narrow the supported surface: the same
  characters inside a quoted argument, and ordinary `( … )` grouping, stay readable, and a
  carrier pins that.

  A third pass found the last regex still in the parser doing the same damage one level down.
  Command substitutions were located with `\$\(([^)]*)\)` over the **raw** string, which knows
  neither quoting nor nesting: `printf %s '$(jq .)'` declared `jq` out of a literal argument, and
  `[^)]*` stopped at the first `)`, so in `$(a $(b))` the outer command went unread. The same
  raw-text blindness applied to the backtick and `$((` refusals — inside single quotes both are
  data. Substitutions are now lifted out by a **quote-aware scanner** that counts parentheses and
  tracks quote state, and the two refusals moved inside it, so what is refused is a construct and
  never a character in a string. Each substitution body is scanned again, so nesting is read to
  the bottom, and each is replaced in the outer string by a marker word rather than by a blank —
  blanking silently promoted the *next* word to head, so `$(which python3) a.py` declared `a.py`.
  A head that is an expansion is refused outright: `$RUNNER hook.py` used to declare a binary
  named `$RUNNER`, which is not a name the host can be asked for.

  The same pass corrected the opposite error. The keyword refusals were applied to **every**
  token, so `python3 hook.py --mode case` was unreadable — a construct is a construct only in
  head position, and an argument opens no grammar. Head-only is also what makes `--sort time`
  and `--pattern "[["` ordinary again. The one refusal that stays position-independent is the
  function definition, because `()` is meaningful precisely *after* the word it defines — and it
  applies to **any** word, since `echo() { jq .; }` and `command() { jq .; }` are valid shell.
  The first version only remembered a word it had already accepted as a binary, so a function
  named after a builtin or a wrapper slipped through and its body was read as a command list.

  **A fourth pass, run against the rewritten parser rather than against the old defects, found
  four more.** Three were confident wrong answers of the same shape as the first: quote removal
  makes `"&&"` and the operator `&&` the same string, so `python3 a.py "&&" evil.py` declared
  `evil.py` — the earlier carrier used a *multi-word* quoted argument, which never produces a
  token equal to an operator and so could not see it; an **empty** token satisfied "made only of
  separator characters" vacuously, so `python3 "" evil.py` declared `evil.py` too; and a
  here-document body was consumed as arguments, so `sh <<EOF … EOF` reported `sh` and nothing
  the script inside it runs. The fourth was dead code: `_SEPARATORS` listed `\n`, but `shlex`
  treats a newline as whitespace, so it never became a token and the second line of a two-line
  command was swallowed as arguments of the first. An unquoted newline is rewritten to `;` by the same
  scanner that lifts substitutions, and `<<` joins the refusal set while `<<<` stays readable, a
  here-string being one word rather than a body.

  The quoted-operator fix was first attempted with **two `shlex` passes** — one preserving
  quotes for structure, one removing them for names — required to agree token for token. That
  reconciliation was itself wrong: the passes disagree on any word that *mixes* the two, which is
  ordinary shell. `"$DIR"/hook.py` is one word to a shell and two to the raw pass, so a
  legitimate command was refused and a backslash was blamed for it — found by seeding the real
  tree, not by reading the code. Tokenization is now done here, over text the scanner has already
  cleared of substitutions, comments, backticks and unbalanced quotes; what remains is words,
  quotes, escapes and operator runs. A quoted operator can no longer *become* one, because
  quoting is resolved in the same pass that decides structure, and an escape now reads as an
  escape instead of as an unreadable command.

  A sixth pass, against that tokenizer, found four more — every one of them a construct the
  previous shape had hidden rather than a regression. **Process substitution** silently lost the
  command it runs: the redirection branch consumed the `(`, so `python3 a.py <(jq .)` reported no
  `jq` while `diff <(jq . a) <(jq . b)` reported one, the same construct read two ways depending
  on where it sat; it is a bash extension and is now refused. A **`(` glued to a word** —
  `x((y`, `foo(bar)` — is a shell syntax error that the walk answered with a binary named `y` or
  `bar`; it is now refused unless it is the `()` of a definition. **`((` away from a head** was
  still read as grouping, so `python3 ((x))` declared `x`; unlike the *words* `case` and `time`,
  `((` can never be a legitimate argument — quoted, it is a word and never arrives as an
  operator — so its refusal is not head-scoped. And a **redirection preceding the command** is
  valid shell whose file-descriptor number is not a binary: `2>&1 python3 a.py` declared `2` and
  missed `python3`.

  A fifth pass, against that rewrite, found two more and one dead entry. `shlex` opens a comment
  at a `#` **anywhere**, while a shell opens one only at a word start, so `python3 a.py#x && jq .`
  lost everything from the `#` and never reported `jq`; comment handling is now switched off in
  the tokenizer and done by the scanner, which knows what a word start is and what is inside
  quotes. An **empty** head — `"" evil.py` — was declared as a runtime whose name is the empty
  string, and is now refused. The dead entry was `<<-` in the here-document set: `punctuation_chars`
  splits `<<-EOF` into `<<` and `-EOF`, so the second spelling could never appear and `<<` alone
  covers both. Each of the five passes found defects of the same two shapes — a confident wrong
  answer, or a silent under-count — which is the argument for the refusal set rather than for
  more grammar.
* **The retired registry keys were never actually refused.** The migration prose claimed a stale
  config fails, and the test only covered a wholly-old standalone registry. The real upgrade path
  is a project overlay deep-merged *over* the shipped registry: `harness`/`operation` survive, the
  retired `cli`/`invoke` ride along beside them, and every presence check passes while the config
  states one command twice. `second_opinion_spec` now raises on the retired keys in **both** the
  required and the optional lookup — a stale configuration is not an absent capability, and
  degrading it to "no second opinion available" would hide the migration behind a quietly weaker
  run — and `verify` reports the pair against the overlay file, because the merged result no
  longer shows which file is stale.
* **The axis list was closed in one direction only.** A repeated axis overwrote the earlier
  value, so a claim could carry two contradictory readings and report whichever came last; an
  unknown key was ignored, so a typo cost only the missing-axis finding and left a seventh answer
  standing in the file. Both are now `matrix.invalid-value`.
* **A malformed `Finding` was reported as a JSON parse failure.** The new overlay check ran inside
  the `try` that guards `_read_json`, so the `ValueError` from `Finding.__post_init__` — raised by
  a two-sentence `fix` — surfaced as `error routing.overlay-parse` against a file that parsed
  perfectly. The check moved to the `else` branch: a defect in a check must not be reported as a
  defect in the file it reads.

**C57 encoding decisions (in-task, as §7 delegates).** `documented` is `yes`/`no`; `delivered` is
`yes`/`no`/`unmeasured`; the route reads `vendor=… ; version=… ; event=… ; matcher=…` with `n/a`
where a capability is not hook-routed; `evidence` is a citation or empty. A row counts as
**measured** — and so must cite — when it settles `delivered`, asserts a crash posture, or
asserts a non-`none` effect; only a row that settles nothing cites nothing. Binding the citation
to a settled `delivered` is deliberate: "the wiring reaches the harness", or measurably does not,
is the claim a reader acts on, and letting it stand uncited is how a vendor grid drifts back into
decoration. One row is one **claim** — one capability on one harness — because `vendor` is a
route coordinate; a harness with no shipped or measured claim has no row, and absence means
akmon asserts nothing rather than that the capability is missing.

**Bare-claim adjacency, as implemented.** Adjacency is per **block** (a contiguous run of
non-blank lines), not per line: a blockquote that says "enforced" and names `PreToolUse` three
lines down is one claim, and a line-scoped rule cannot see it. Vendors match as **proper nouns**,
case-sensitively, so a lowercase `claude` inside `.claude/skills/` stays a filesystem path rather
than a claim. The scan covers shipped documentation and skips `meta/` and `guardrails/`. The
lock's named allowance is implemented as *attribution*, not mere co-occurrence: the claim must
name an akmon in-process checker within the same clause, or any page that happens to mention
`sync.py` would buy itself an exemption.

**Red before green.** The current tree has no `CAPABILITIES.md`, so `self_ci` first emits
`error matrix.missing-file`. Its legacy README capability glyphs and the unqualified delegation
claim independently emit `error matrix.bare-claim` — four blocks in all, measured at
implementation: the glyph legend, the capability table itself, the runtime-hooks bullet claiming
the commit guard *enforces* beside `PreToolUse`, and the delegation blockquote. (The line numbers
this paragraph carried before implementation — `README.md:82`–`:92` and `:200` — had drifted; the
count, not a line, is what this evidence rests on.)
Those legacy rows are forbidden second-authority prose, not candidate matrix rows, and therefore
produce no `matrix.missing-axis` finding.
C57 observes those failures before creating `CAPABILITIES.md` and replacing the legacy README
matrix with the claim-free summary; the repaired tree and fixtures then pass. Converting first is
rejected because it would discard the executable current red state.

**The git dependency stays for now.** Replacing `git rev-parse` with the Python root discovery used
by package mode is the right later repair, but it overlaps generated wiring C52 changes and no
consumer has hit it. Revisit when a consumer reports it or P4.2's plugin carrier changes the wiring.
This trigger is an in-task/future repair boundary, not D2-23 evidence and not a new C57 dependency.

**F13 matrix corpus — checker, mutation, exact failure.** The checker is `self_ci`, through C51.
Fixtures isolate every rule:

- deleting `CAPABILITIES.md` emits exactly one `error matrix.missing-file`; deleting only its
  marked matrix region is a separate fixture and emits that same exact finding;
- moving a complete six-axis matrix under `meta/` while leaving no top-level `CAPABILITIES.md`
  still emits exactly one `error matrix.missing-file`; no alternate-location fallback is accepted;
- for each of the six axes, deleting only that axis emits exactly one
  `error matrix.missing-axis`; these axis-presence fixtures use non-enforcement rows. Separate
  non-enforcement route subfixtures independently delete vendor, version, event and matcher and
  receive the same exact code;
- effect and crash-posture fixtures are parameterized over every accepted value plus one value
  outside the corresponding closed vocabulary; each invalid case emits exactly one
  `error matrix.invalid-value`. C57's chosen encodings for documented, delivered, route and evidence
  have no invalid-value oracle in this lock;
- an otherwise complete `ask` or `deny` cell keeps every axis and route coordinate present but sets,
  one at a time, each **route coordinate** explicitly to `unmeasured`; every case emits exactly one
  `error matrix.unqualified-effect`. Setting the **crash posture** to `unmeasured` emits exactly one
  `error` of the same code on every claim: the D2-29 exemption of two claims by name expired in
  C90 (D2-47), once both recorded a measured posture, and a live-tree carrier fails if a shipped
  `ask`/`deny` claim stands on an unmeasured crash posture again. Deletion is never this code: it is `matrix.missing-axis` as above;
- a measured assertion with empty evidence and an `unmeasured` assertion with non-empty evidence
  are separate mutations, each emitting exactly one `error matrix.uncited-claim`;
- parameterized fixtures place each of `enforced`, `enforces`, `✅` and `⚠️` beside each vendor and
  harness-event spelling outside the marked regions; every case emits exactly one
  `error matrix.bare-claim`. A separate transition fixture keeps the detailed legacy README table
  beside a valid `CAPABILITIES.md` and emits exactly one `error matrix.bare-claim`; it is never
  parsed as a six-axis fallback and never emits `matrix.missing-axis`. Matching prose about an
  akmon-owned checker and matching guardrail prose are two separate negative fixtures and emit no
  C57 finding.

Changing any expected code or severity, combining two violations in one fixture, accepting the
current red state, or leaving either post-conversion artifact red fails the matrix contract suite.

**F13 runtime corpus — checker, mutation, exact failure.** The same `self_ci` entry calls the pure
runtime checker. Fixtures independently:

- add an undeclared generated `jq` invocation and an undeclared own-tool query; each emits exactly
  one `error runtime.undeclared-binary`;
- leave one declaration unused in each population; each emits exactly one
  `warn runtime.unused-binary` and keeps non-strict `self_ci` zero;
- remove the population field from, and assign to the other population, each of POSIX shell,
  `python3`, `git`, `claude` and `codex`, one entry at a time; each emits exactly one
  `error runtime.wrong-population`;
- change POSIX shell or `python3` away from `required`, `git` away from
  `required-on:codex`, and each of `claude` and `codex` away from `optional`; every isolated case
  emits exactly one `error runtime.wrong-modality`;
- add a second query map and, separately, restore a literal `claude` or `codex` subprocess call
  outside the sole map; each emits exactly one `error runtime.duplicate-query-owner`.
- in the downstream C70 corpus, construct the Codex app-server argv outside this map; it emits the
  same single `error runtime.duplicate-query-owner` without making C57 depend on C70;
- remove the implicit POSIX-shell carrier from the derived generated-wiring population while its
  declaration remains; it emits exactly one `warn runtime.unused-binary` and keeps the normal exit
  zero.

Deleting either population join, changing the warn/error severity or a code, duplicating a finding,
or producing the wrong normal exit fails its exact oracle. D2-23 contributes no literal or
measurement to these fixtures and blocks only C52.

## 8. Tool names: neutral capability + vendor map (C46, tool-name half)

**F20/A decision — exact populations and one owner in both directions.** The neutral vocabulary is
exactly `edit` / `shell` / `read` / `subagent`, owned by `hook_core`
(`hooks/hook_core.py:109`–`:115`), where `read` already folds Read/Grep/Glob by that module's own
comment. The exact restricted-agent population is `k_explorer`, `k_reasoner` and `k_auditor`, each
with `{read, shell}`; `k_mechanic`, `k_validator` and `k_implementer` carry one explicit
unrestricted sentinel rather than a vendor-name list. A new capability is added to `hook_core`'s
vocabulary first. A generator token outside that vocabulary fails with exactly one **error
`harness.unknown-capability`**; a missing token, a fifth token, the wrong restricted-agent set, a
wrong member assignment or replacing the unrestricted sentinel with an inferred filename/tool list
fails the exact population contract.

One **version-stamped data inventory** (harness id + version, with separate tool/payload and matcher
names where the harness distinguishes them) is the sole declaration owner of vendor names consumed
by all three classes: generated agent frontmatter, generated Claude/Codex hook matchers, and
Claude/Codex adapter normalization. Executable code may select or compare an inventory value; it may
not redeclare a vendor-name set or map beside the inventory. A second declaration owner in any of
the three classes emits exactly one **error `harness.duplicate-name-owner`**. A missing version,
duplicate harness/version row, malformed name population or absent required map emits exactly one
**error `harness.invalid-inventory`**. A neutral mapping that emits a name outside its selected
inventory emits exactly one **error `harness.unknown-name`**. Thus the check runs in both directions:
every consumer token belongs to `hook_core`, and every vendor name a consumer declares comes from
the selected inventory.

A capability with no vendor name degrades explicitly to the selected inventory's `shell` name and
emits exactly one **warn `harness.capability-degraded`** naming the capability, harness/version and
widened boundary. Bash is strictly wider than Grep/Glob, so after this degrade a read-only boundary
rests on the agent body's prose rather than the tool set. A silent degrade, a different fallback
name, or a warning that omits the widened boundary fails the contract.

**Detection and fallback.** The stamp needs something to compare against, and today there is
nothing: no code in `bin/`, `tools/` or `hooks/` reads a harness version; 2.1.221 and 0.146.0 were
obtained by hand in N2. `sync` queries the sole C57-owned `claude`/`codex` query map for each binary
present on PATH. A detected known version selects its exact inventory. For each absent binary,
generation independently uses the declared version and states that assumption in every affected
generated artifact. A detected version newer than or otherwise absent from the inventory selects the newest
known inventory for that harness, emits exactly one **warn `harness.unknown-version`**, and stamps
both selected and detected versions in every affected banner, for example
`generated against claude-code 2.1.221 inventory; detected 2.2.0`. Warning and banner are both
required. Rejected: declaration-only detection, which makes staleness printed but invisible;
mandatory binaries, which bricks repositories without a harness installed; erroring on a new vendor
release, which puts availability on the vendor's schedule; and degrading every capability to shell,
which dismantles the boundary to preserve a formality. Accepted cost: unknown releases proceed on
possibly stale data, but the warning and durable provenance make that assumption reviewable. The
banner line is C55's surface, recorded as an outgoing annotation rather than a C46 dependency.

**Checker and caller contract.** One pure C46 inventory/resolution checker is called by both `sync`
and `sync --check`; every `harness.*` error above exits 1 in both callers. Warn-only operation exits
0 in normal `sync` and, when there is no independent generated drift, in `sync --check`; C59 later
aggregates the same ordered warnings. `self_ci` calls the source-owner checker over the exact three
consumer classes and the neutral/agent population contract. Contract tests exercise the same pure
resolver and both CLI callers. Deleting any caller's wiring, changing a code or severity, producing
duplicates, or changing the stated exit behavior fails.

**F13 carriers — isolated checker, mutation and exact failure.** The corpus independently:

- adds an unstamped row, a duplicate harness/version row, a malformed name population and a missing
  required map; each emits exactly one `error harness.invalid-inventory` through `sync` and
  `sync --check` and exits 1;
- emits `Grep` against the Claude 2.1.221 inventory; each caller emits exactly one
  `error harness.unknown-name` and exits 1. This is C46's own live red-before-green transition:
  `routing.py:362`/`:470`/`:503` remain unchanged until C46 first observes them red, then the same
  checker passes after conversion. It is not an application of F9, which belongs only to C54;
- removes a vendor mapping for each neutral capability in turn; every case emits the selected shell
  name plus exactly one `warn harness.capability-degraded`, names the widened boundary and exits 0.
  Separate mutations suppress the warning, choose a non-shell fallback or corrupt its disclosure;
  each fails the exact oracle;
- detects each known harness version and requires its exact row, then uses a two-version inventory
  and detects an unknown version to require the newest row, exactly one
  `warn harness.unknown-version`, both versions in every affected banner and exit 0. Selecting an
  older row, omitting either stamp, warning twice or failing exits the oracle;
- removes each binary from PATH separately and then both together; every absent harness requires its
  declared-version assumption in every affected banner with no warning, while any present harness
  still uses its detected row. Omitting, cross-assigning or mis-stating either provenance fails;
- adds a second vendor-name set or map separately in agent-frontmatter generation, Claude hook
  generation, Codex hook generation, Claude adapter normalization and Codex adapter normalization;
  each source-owner case emits exactly one `error harness.duplicate-name-owner` in `self_ci` and
  exits 1. Removing any one consumer from the scanner's pinned population fails before the literal
  oracle, so a missing consumer cannot look clean;
- adds an invented neutral token beside `hook_core`, deletes each of the four owned tokens in turn,
  adds a fifth token, changes each restricted agent's `{read, shell}` assignment, moves each agent
  across the restricted/unrestricted boundary and replaces the unrestricted sentinel with a local
  vendor list. An invented or consumer-only token emits exactly one
  `error harness.unknown-capability`; every exact-population mutation fails the pinned contract.

The same parameterized resolver cases run through `sync` and `sync --check`; the same ownership and
population cases run through `self_ci`. Wrong finding count, code, severity, target, fallback,
selected version, provenance, caller exit or non-isolated fixtures fail the suite.

**Out of scope, already decided elsewhere.** Shipping akmon's own tools over MCP is P4.3, gated
behind A15/C42 by ADR 0010; the agent-name half is closed by ADR 0011.

## 9. Execution ledger (P1.5 → C58)

**F10 remains unchanged: dispatch-only.** Completion — the event proving a run finished, the
completion fields and the correlation key — remains unknown on both vendors and belongs to
[N4](../TASKS.md). **F21/A pins what “dispatch” means now:** one observed Claude `PreToolUse`
dispatch **request**, after the C46 adapter/inventory normalizes its vendor tool name to the neutral
`subagent` capability. The record proves that the request crossed the measured hook event; it does
not prove launch, acceptance, progress or completion. The exact generated Claude matcher and
`delegation-log.py` wiring are part of the checked population. Non-dispatch PreToolUse calls emit no
record. Codex remains `delivered: no`; no Codex event is inferred from Claude evidence.

**Path, writer and readers.** The sole current write path is
`<AITNA_ROOT>/model-routing.log`, resolved from the consumer's declared dev-layer root. The legacy
read-only path is `.claude/model-routing.log`. `hooks/delegation-log.py` is the sole production
writer. The exact default reader population is `tools/model_routing/stats.py` and
`tools/model_routing/coverage_map.py`; no third reader or second writer silently owns migration or
schema behavior. Default reads consume the legacy file first and the new file second, preserving
line order within each file and performing **no deduplication**. Old-only, new-only and both-present
states are valid. `coverage_map.py --log PATH` reads exactly the supplied path and performs no
default-path fallback or two-file merge. Writes always target only the new path; there is no copy or
migration command.

**Exact v1 record.** Every new record has exactly seven TSV fields:
`v1 · timestamp · session_id · subagent · model · zone · description`. `v1` is literal. The six
data fields are normalized independently as `" ".join(str(value).split())`; an empty result becomes
the literal sentinel `-`. Timestamp is offset-bearing ISO. Tabs, CR/LF and other whitespace inside
payload values therefore cannot create a field or record boundary. The new path accepts only v1
records. The legacy path retains its existing unversioned four- and six-field read compatibility,
but no writer may emit either legacy form. A malformed or unknown-version line fails the read
visibly without producing a derived artifact; readers do not rewrite local evidence.

`v1` is **format provenance, not authenticity**. A person or model can manually write a
structurally valid v1 row and it is indistinguishable from hook output. C58 neither signs local rows
nor claims tamper detection; the residual is accepted because an authenticity mechanism would add
identity/key ownership absent from this lock. Rejected: a second model-written ledger, silent repair
of malformed rows, or treating a parseable row as cryptographic proof that a harness emitted it.

**Serialized bounded append.** The writer resolves the project and new path, encodes one complete
in-envelope record, opens the log in append mode, takes one exclusive file lock, appends the complete
newline-terminated record and releases the lock. Parallel dispatch is the normal case: N successful
in-envelope requests produce exactly N intact parseable records, with no loss, interleaving or
duplicate row. C58 owns no numeric cap, durability or rollback protocol: F6/C52 preflight the
per-record and total-ledger inputs before this normal path, and D2-23 owns their concrete literals.

C58 does **not** rotate, truncate, delete or deduplicate the ledger and makes no exceptional-write
completeness claim. Total cap+1 and lock/open/write failures belong to C52's exact fail-open
diagnostic/exit contract; a failed write may leave no record or a malformed trailing record, and the
ledger is explicitly incomplete after that visible operational failure. Rotation requires its own owner/D2 contract covering
segment naming, reader order, crash recovery and retention; introducing any rotation owner inside
C58 fails the source-owner check.

**Gitignore and guardrail join.** Both `.claude/model-routing.log` and the resolved
`<AITNA_ROOT>/model-routing.log` are local/gitignored throughout migration. The orchestration
guardrail carries exactly: **“After compaction, trust the dispatch-request ledger at
`<AITNA_ROOT>/model-routing.log` and `git log`; it records requests, not launches or completions.”**
One pure C58 contract checker, called by `self_ci`, joins that symbolic path and scope to the writer,
both default readers, the explicit override, generated hook wiring, schema owner and declared
gitignore entries. Every isolated contract violation emits exactly one C51 **error** and makes
`self_ci` exit 1:

- `ledger.wiring-drift` — wrong/missing event, matcher or hook entry;
- `ledger.owner-drift` — a missing/extra writer or default reader, or a rotation/truncation owner;
- `ledger.path-drift` — wrong writer/read order, legacy/new path, override fallback or guardrail join;
- `ledger.schema-drift` — wrong marker, field count/order, normalization, sentinel, timestamp form or
  legacy/new parser boundary;
- `ledger.ignore-drift` — either resolved ignore entry is absent or wrong.

**F13 carriers — isolated checker, mutation and exact failure.** The suite independently:

- removes the normalized Claude dispatch matcher, moves it away from `PreToolUse`, wires another
  script or adds a non-dispatch event; each emits exactly one `error ledger.wiring-drift`. A healthy
  observed dispatch request writes one record, while each non-dispatch PreToolUse fixture writes none;
- adds a second writer, removes the sole writer, removes or adds a default reader, or introduces
  rename/truncate/delete/rotation ownership; each emits exactly one `error ledger.owner-drift`;
- changes the new or legacy constant, makes the writer target legacy, reverses default read order,
  adds deduplication, makes either reader omit a path, makes `--log` merge/fallback, deletes the
  guardrail clause, changes only its path or scope, or changes only the writer path; each emits
  exactly one `error ledger.path-drift`. Old-only, new-only and both-present fixtures run through
  stats and coverage; both-present yields old-then-new with duplicate-looking lines retained;
- deletes, adds or reorders every v1 field separately; changes the literal marker; removes
  offset-bearing timestamp form; changes `" ".join(str(value).split())` or empty→`-`; injects tab,
  CR and LF separately into every data field; lets a new-path legacy row pass; or rejects an accepted
  old-path four-/six-field row. Each emits exactly one `error ledger.schema-drift`. At runtime a
  malformed or unknown-version row makes either reader emit one safe diagnostic naming only path,
  line and structural reason, exit 1 and produce no derived artifact; neither file is rewritten;
- removes the legacy ignore entry, removes the resolved new-path entry, or hard-codes `_aitna` in a
  relocated-root fixture; each emits exactly one `error ledger.ignore-drift`;
- runs serialized parallel appends for N in-envelope requests and requires exactly N complete v1
  rows; lost, interleaved or duplicate rows fail. The separate §2/C52 corpus owns every
  cap−1/cap/cap+1, lock/open/write failure and exact diagnostic/exit oracle; C58 neither duplicates
  those seeds nor gains a C52/D2-23 task dependency.

The same pure contract cases run through `self_ci`; deleting its caller wiring, changing any code,
severity, finding count or exit, combining two mutations, or allowing a fixture to pass through an
unrelated failure fails the suite. C58 depends on C46 and C57. Its one guardrail line is remeasured by
C56, but that collision remains an annotation, not a C56 dependency.

## 10. `akmon status` (P1.4 → C59)

**Decision — exact source population and actual-state boundary.** C59 is a read-only aggregation of
checks that **already exist**. It invokes exactly two source providers against the freshly resolved
consumer root, in this order: the complete consumer `verify` finding stream, then the complete `sync
--check` finding stream. The five required logical families are verify findings, sync drift, D2
pending/configuration state, consumer caps headroom and live Codex host-trust state. The latter
three are emitted once inside the verify stream by their owners, **C53**, **C56** and the D2-27
extension **C70** respectively; C59 neither invokes them again nor reads their files or host state
directly. In particular, F8/3's `configured` / `not configured` coverage state is
emitted by the existing `d2_ledger` check owned by C53, which also writes the marker that states the
dependency. (Repaired at A17(g): "no new data source" and F8/3's requirement that C59 report that
state could not both hold while no task was assigned to emit it — C59 would otherwise have had to
read `.akmon.toml` itself.) Sequenced last so it reports a finished vocabulary.

C59 preserves provider order and each provider's finding order. It does not sort, deduplicate,
synthesize a summary finding, cache a status snapshot, create a status file or mutate the consumer
tree. The source providers read the actual materialized consumer state and, for C70, the current
host state returned by the authoritative vendor query; a declaration-only or cached copy is not a
source. C59 and C70 write neither the consumer tree nor host config and never grant approval. The
bounded C70 subprocess may cause vendor-owned cache, log or network activity outside those surfaces;
D2-27 accepts that operational cost, so it is not part of the no-write claim. This satisfies ADR
0010's actual-state boundary for state the project-local checkers can observe. The active role exists only in the harness transcript and a standalone CLI
process has no truthful source for it: C59 does not introduce a persisted active-role marker or claim
to report that state. The accepted residual cost is that `akmon status` cannot report the active role
outside a harness transcript.

Per owner choice F2, C59 adds the public JSON rendering by composing C51's already-pinned canonical
serializer; C59 enters C51's exhaustive adopter population and defines neither a second Finding
schema nor a local field mapping. The public JSON framing and option name remain a later `akmon
status` fork. Text and JSON render the same complete ordered Finding sequence. For both renderings,
only `ok` exits 0 with or without strict mode; a `warn` exits 0 normally and 1 under strict; an
`error` exits 1 in both modes.

**Fork — mutable status levels.** Parked by **D1** in ADR 0010; unchanged by this proposal.

**Seeded violation — fidelity, not a new check (owner-locked as register fork F11).**
C59 is the stage's hard case for its own yardstick: a shape that adds no check appears to have
nothing to seed. It gets **no exemption**. For an aggregating shape the contract is fidelity to
its sources, and that is seedable: mutate the source finding set and the aggregate must change
with it; a finding dropped, reordered, or present in one rendering but not the other fails; and
the exit code must follow the same strict semantics as the underlying checks. This costs C59 a
test seam into its source set — a "pure aggregator" that composes real checkers only — and the
seam is worth it, because an exemption granted on the first shape that asks for one converts the
yardstick from a rule into a preference.

One direction of fidelity was missing (A17(g), per F13): every mutation named above removes or
disturbs a source finding, so an aggregator that copies its sources faithfully and **adds one of
its own** to both renderings passes all of them while breaking the rule this section opens with.
The aggregate is therefore asserted **equal** to the composed source set rather than merely
containing it — a finding present in the output and in no source fails, which is "no data source
of its own" made mechanical.

**F13 carriers — source population, read-only behavior and exact fidelity.** A C59 contract suite
injects the two providers at the aggregation seam while integration fixtures run the same aggregator
against a materialized consumer. The suite independently:

- removes, adds or reorders a provider, or changes either provider's target root; each fails the exact
  `verify`-then-`sync --check` population/order assertion. Re-emitting C53's D2 finding or C56's caps
  finding outside verify, calling Codex from C59, or re-emitting C70's trust finding outside verify
  fails the exactly-once source-set assertion;
- for each of the five logical source families separately, adds, removes, changes and reorders one
  source Finding and requires the aggregate to remain exact ordered equality. Dropping a finding,
  sorting or deduplicating the sequence, adding a synthesized finding, or adding one finding to both
  renderings but to no source fails that equality assertion;
- adds one source finding to text only and then JSON only; each fails the rendering-parity assertion.
  A local JSON field mapping, second serializer or omission of C59 from C51's adopter population fails
  C51's inherited canonical-owner carrier;
- runs `ok`, `warn` and `error` source sets independently through strict and non-strict text and JSON
  modes. Every cell pins the same exit result in both renderings: `ok` is always 0, `warn` is 0/1 and
  `error` is 1/1;
- snapshots the complete fixture tree and host config before and after both renderings and instruments
  project/config/approval write-capable calls; creating an akmon-owned cache/status file, changing an
  existing file or invoking such a writer fails. Vendor-owned cache/log/network effects outside these
  surfaces are not asserted absent. A source
  scanner mutation that reads `.akmon.toml`, the D2 ledger, caps inputs or generated hook settings
  directly from C59 fails the no-own-source assertion;
- changes the actual attach-record pin, materialized hook wiring and injected live Codex trust result
  independently while leaving their declarations and any stale snapshot unchanged; the owning
  provider and aggregate must change. The C70 mutation enters only through one `verify` invocation;
  C59 never makes its own app-server call. A cached or
  declaration-only result fails the actual-state integration oracle. The active-role absence fixture
  invents no role value or transcript provider: the residual is a declared boundary, not a passing
  mechanical claim.

The exact dependency is rows 1–9, including C46, plus the D2-27 C70 extension. These carriers add no
other task edge and do not
bring the parked JSON option spelling or D1 mutable levels into this lock.

## Acceptance

- every **independently violable rule** above ships with a test that **fails on a seeded
  violation** and passes on the repaired tree — the yardstick from the Frame, checked per task,
  not at the end. **The unit is the rule, not the shape** (F13): rules that cannot fail separately
  may share one seed, a rule that can be violated on its own carries its own, and a rule whose seed
  needs evidence that does not exist yet is **split** — the checkable half is checked now and the
  remainder names the gate it waits on, as §2's `timeout` rule does against D2-23. **No exemption
  class exists** (F11): a shape that adds no check of its own is seeded against its *fidelity*
  to the sources it composes. A semantic or process-owned obligation is outside the mechanical
  guarantee only when the lock labels it, names the tested subset and states the residual cost;
  an unlabeled or purportedly checked rule receives no such boundary;
- `meta/tests` and `ruff` clean; `python3 meta/self_ci.py` exit 0; `bin/verify.py --strict`
  clean against the consumer fixture;
- three shapes are accepted against the live tree rather than a fixture, each observed red before
  green: P1.3's check fails on today's version/changelog pair before the repair and passes after;
  C57's emits `matrix.missing-file` for the absent `CAPABILITIES.md` and `matrix.bare-claim` for
  README's legacy glyphs and `README.md:200`'s unqualified enforcement claim before the file and
  claim-free summary land; C46's fails on `routing.py`'s `Grep`/`Glob` declaration. None is repaired
  ahead of its own task, because a check that never met the defect proves only that it runs;
- C55's suite pins every shipped path to exactly one ownership mode in both mount populations and,
  for `field-owned`, its selectors; the forward `boundary.missing-banner` and reverse
  `boundary.stale-generated` seeds with their `error` severity; the scanner's out-of-scope kinds,
  position limit and configured-root segment; and the `self_ci` seam that keeps akmon's own
  declaration inside the same check. Reverse stale discovery is mechanically complete only for
  `bannered-file`, and that limit is stated rather than papered over;
- each caps check reports its scope, exact dynamic line and decimal-byte counts, both caps and
  `caps.always-loaded`, so a later reduction (C60) can be verified against the same counters;
- C57's matrix suite pins all six axes, every route coordinate, the bidirectional evidence rule,
  exact value grammars and the shipped-doc vocabulary exclusions; its runtime suite pins both
  populations, all five modality assignments, the sole query-map owner, exact codes/severities and
  the non-failing normal exit for `runtime.unused-binary`;
- C46's suite pins the four-token neutral vocabulary, the six-agent restricted/unrestricted
  population, all three vendor-name consumer classes, both ownership directions, known-version and
  newest-known selection, fallback and provenance, exact `harness.*` codes/severities/counts and the
  error/warn caller exit matrix;
- C58's suite pins the seven-field versioned v1 record, the sole writer and the exact default-reader
  population, the neutral `<AITNA_ROOT>` path with the vendor path read-only, the serialized bounded
  append, the migration and the gitignore/prose/path joins under `self_ci`, plus the safe
  diagnostic and exit a malformed or unknown-version row produces in either reader. The envelope
  and write-failure oracle stays with the §2/C52 corpus and C58 does not duplicate it. The record
  is a dispatch **request** and claims no launch — completion stays with N4;
- C59's suite pins the exact provider population and order — the fresh `verify` stream, then the
  fresh `sync --check` stream — with C53's D2 state and C56's caps state present exactly once
  through verify and C70's fresh Codex host-trust state present exactly once through the same
  provider; exact ordered equality with those sources; no project/config/approval write, no direct
  re-read or host query from C59 and no status cache; rendering parity between text and JSON with one exit result per source set in
  both; and the transcript-only active-role residual stated rather than synthesized;
- README, `hooks/README.md`, `CAPABILITIES.md` and CHANGELOG agree with the code that shipped.

## Not in this lock

Doc gardening (dead links, staleness); matrix as data (A16/C44); MCP transport (P4.3);
mutable status levels (D1); Codex dispatch **completion** observability ([N4](../TASKS.md), the
probe F10 spawned — this named N1 until A17(g), and N1/F4, N5/F6 and N6/F5 are the separate
measurement carriers parked above); the caps *reduction* (C60, which
runs after C56 lands — the edge is kept here because C60 is no longer a row in the order table).
