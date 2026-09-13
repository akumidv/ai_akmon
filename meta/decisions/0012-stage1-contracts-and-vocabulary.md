# 0012 — Stage 1 contracts and vocabulary: findings, policy IDs, ownership, load caps, capabilities, and the seeded-violation yardstick

- **Status:** Accepted — owner-verified at **D2-20** and landed at `e89f3fe`. This is the stable
  half of the A12 stage-1 lock; D2-20 clause (b) verifies its boundary with ADR 0013.
- **Owner:** akuminov@gmail.com
- **References:** [design lock `stage1-hardening-contracts`](../design/stage1-hardening-contracts.md)
  (the full rationale, per-shape contracts and the owner walkthrough register F1–F22) ·
  [ADR 0010](0010-alternatives-adoption-a11-verdicts.md) (A12 owns the decisions riding the N2
  inventory) · [ADR 0011](0011-agent-name-notation-k-underscore.md) (the first, separately locked
  A12 slice) · [ADR 0007](0007-d2-ledger.md) §4 (warn-first, which F8/3 must not contradict) ·
  [ADR 0013](0013-hook-survivability-and-crash-posture.md) (the measurement-amendable half) ·
  carriers [C51](../TASKS.md), [C53](../TASKS.md), [C55](../TASKS.md), [C56](../TASKS.md),
  [C57](../TASKS.md), [C58](../TASKS.md),
  [C59](../TASKS.md), [C46](../TASKS.md) ·
  ledger rows D2-20, D2-23.

## Context

Stage 1 buys one property: **a violation of an akmon rule fails a check instead of degrading to
silence.** The C47–C50 repair wave paid for that formulation — a wrong payload key, a path
predicate that never matched, a matcher that named one route three times and the other not at all.
Each was a rule akmon stated and nothing verified.

The stable contracts below are in that state today and are the subject of this ADR.

**Diagnostics.** `bin/verify.py` owns a `Finding` with a `level` field; `meta/bin/validate.py`
carries an independent one; `sync --check` and `meta/self_ci.py` speak neither, and `self_ci`
reads its siblings by parsing subprocess output. There is no shared field vocabulary, no stable
identity for a check, and no machine-readable form — so nothing can aggregate the checks, and
nothing can assert that two checks disagree about what a finding *is*.

**Guardrail enforcement claims.** `guardrails/_common.md` carries three
`> **Enforced** (not just documented) by …` blocks; `hooks/hook_core.py` carries seven public
`*_result` callables. Neither side names the other in a form a machine can join, so a callable can
be deleted or renamed and the prose keeps asserting enforcement, or prose can claim enforcement
that no callable ever implemented. The P0.3 inventory found exactly one such orphan: the role
declaration rule, asserted only by hook text and the SessionStart message.

**Generated ownership.** `sync.py` plans whole Markdown/Python files, whole structured files and
selected fields inside hand-owned files through one `PlannedFile` shape, but the shape does not say
which ownership relation applies. A universal banner rule is false for JSON and mixed-ownership
files; inferring the relation later from a suffix or path would create a second owner for the
generator's own declaration.

**Always-loaded growth.** The context delivered before the model asks for anything combines an
akmon-owned subset with the consumer-owned remainder of `AGENTS.md`. One undifferentiated hard cap
would either fail over content akmon does not own or leave akmon's own growth advisory. Without an
inclusive line-and-byte ratchet, later additions can consume the current headroom without any check
recording that the contract changed.

**Capability claims.** The current README matrix compresses independent delivery, route, effect,
crash and evidence facts into glyphs, while a global enforcement sentence exceeds the measured
Codex route. The complete matrix needs a stable consumer-facing home and a six-axis vocabulary that
can fail mechanically before A16 later owns its data schema and generation.

**Why this is a separate ADR from [0013](0013-hook-survivability-and-crash-posture.md)** (register
fork **F12**). The decisions below are what other work *cites*: A16's matrix schema, every stage-1
task, and every later check that emits a finding or claims enforcement. The survivability
decisions are expected to be amended by the N1/F4, N5/F6 and N6/F5 measurements. An ADR that must be revised by
measurement should not carry the stable vocabulary along with it, or every timing number formally
disturbs a decision that has already been built on. The cost is a boundary to maintain and two
references where one would do.

## Decision

### F1 — one diagnostic field vocabulary: `severity`, with no alias

One stdlib-only module `common/findings.py` extends the existing `verify.py::Finding` into the shared
envelope **`severity · code · message · target · fix`**, adopted by `bin/verify.py`,
`meta/bin/validate.py`, `sync --check` and `meta/self_ci.py` — the last importing the module
directly rather than parsing subprocess output.

`severity` carries the closed `ok / warn / error` vocabulary. The three strict-capable adopters
(`verify`, `validate`, `self_ci`) share the exit contract: errors exit 1 and warnings exit 1 only
under `--strict`. `sync --check` is the recorded exception: clean exits 0, drift exits 1, a planning
error exits 2, and it has neither `--strict` nor a warning stream. `code` is a stable dotted slug naming the
check (`boundary.missing-banner`, `caps.always-loaded`), unique and never reused after a check is
removed — so C51 records the retired names, which no duplicate check can see. It matches
`[a-z0-9]+(?:-[a-z0-9]+)*(?:\.[a-z0-9]+(?:-[a-z0-9]+)*)+`; whitespace, uppercase, empty segments,
repeated hyphens and a slug with no dot are invalid. `target` is the file or artifact the
finding is about; semantic correctness of that reference is review-owned. Every rendered field is
one logical line. `message` is required and non-empty. `fix` is required, non-empty and one
sentence; on `ok` it states the invariant to keep. The mechanical heuristic rejects a terminator
followed by whitespace and the compact uppercase form; residual natural-language sentence
boundaries and imperative mood are review-owned so ordinary paths stay valid. A finding a reader
cannot act on is a defect of the check, not of the tree.

**`severity` is the sole canonical name.** No property alias, no constructor alias, no
serialization alias, now or later. This accepts a breaking Python API change for every caller
constructing or reading a `Finding`, and requires migration of every in-repository constructor,
attribute read, fixture and test — including the independent Finding in `meta/bin/validate.py` —
in one change. Contract tests assert that `severity` exists, that `level` does not, and that the
constructor rejects `level=`; positional construction alone is not migration evidence.

### F2 — the schema lands with the envelope; the public JSON surface lands with its first consumer

[C51](../TASKS.md) owns exactly **one** canonical pure serializer (`Finding.to_dict()` or one
shared function, never both) and pins its keys and values with contract tests. Any adopter or later
consumer that serializes a Finding calls that serializer; the C51 adopters render text only, and
C59 is its first serialization consumer. A local field mapping in an adopter is rejected by test. Its output
uses JSON-safe stdlib values, preserves Unicode, accepts an empty valid `target`, does not mutate
the Finding, and passes `json.dumps` directly. `Pure` means deterministic field mapping plus input
non-mutation here; it makes no broader functional-purity claim.

The contract suite covers every adopter rather than one representative. It rejects an invalid
severity or code grammar, stale `.level` use or a local `Finding`, a second canonical serializer,
serializer mutation, nondeterminism or non-JSON-safe output, a dependency outside the standard
library in `findings.py`, and a public `--json` mode before C59. It exercises
empty, multi-line and multi-sentence `fix` values, line separators in every rendered field, and
exact rendering across all four adopters. The complete severity × strict-state exit matrix covers
the three strict-capable adopters; `sync --check` has a separate exact 0/1/2 carrier.

C51 adds **no** `--json` mode anywhere. [C59](../TASKS.md) introduces the public JSON rendering
when `akmon status` becomes the first process-boundary consumer, by composing C51's serializer
rather than defining a second schema. Text and JSON must carry the same ordered findings and the
same exit/strict semantics.

**Text rendering changes, and C51 owns the change.** `verify.py` prints `[{level}] {message}`
today (`bin/verify.py`, before C51); the canonical form this envelope introduces is
`SEVERITY code target: message → fix`, one canonical stdout line per finding. Every adopter's text output moves in
the same commit as the `level` → `severity` rename, and the tests pinning the old form move with
it.

**Out of scope: hooks do not adopt the envelope.** They speak the harness's JSON contract on
stdout and prose on stderr; a findings object there would be a third output shape on a channel
whose visibility is unverified.

### F7 — stable policy IDs join prose and code, checked in both directions

A guardrail section with runtime behavior carries `Runtime check: <stable.dotted-policy-id>`. It
never says bare `Enforced by`, because [0013](0013-hook-survivability-and-crash-posture.md)
requires normal-path route, crash posture and input envelope to remain **separate** claims. The
policy prose remains the rule's owner; the marker is only its stable join key.

Every public `hook_core.*_result` carries exactly one machine-readable classification in its own
docstring, parsed from the AST without importing hook code:

- `Policy ID: <stable.dotted-policy-id>` for policy-bearing behavior; or
- `Runtime classification: operational` **plus** `Rationale: <non-empty>` when it carries no
  guardrail policy.

The join is one-to-one: each policy ID occurs once in live guardrail prose and once in callable
metadata; each public result has exactly one classification and cannot carry both forms.
Operational classifications have no prose marker and require a rationale, so they cannot become an
unreviewed exemption. A broad guardrail heading may carry a marker only for the exact subset the
callable observes; the marker never claims the whole section is enforced.

`self_ci` checks both directions and reports the policy ID, the callable and the prose location.
There is **no** `INVARIANTS.md`, central mapping constant, decorator registry or generated
annotation: each fact lives either with the policy prose or with the callable it classifies.
**The shipped set is pinned by a contract test** (F15): six callable→policy-ID bindings plus the
`session_start_result`→operational-classification assignment. An ID renamed consistently on both
sides — which preserves the one-to-one join and passes every structural check — fails where someone
can see it. The pin is a test fixture, not a constant the checker consults; the join still runs
prose→docstring, and what the sentence above forbids is something standing between the two sides.
Function names and paths are not policy identity — a rename that preserves the stable ID preserves
the join.

### F8 — the initial table, exhaustive over the seven current public callables

Six policy IDs and one operational classification. [C53](../TASKS.md) checks this set; a callable
added later joins it the same way or the check fails.

| callable | classification | prose owner and the subset the marker claims |
|---|---|---|
| `privilege_escalation_guard_result` | `privilege.no-escalation` | § Privilege escalation — the whole rule: any `sudo` in a Bash command is denied |
| `git_commit_guard_result` | `commits.owner-owned` | § Commits & ownership — **subset**: the AI `Co-Authored-By` trailer (deny) and `push`/`tag`/`merge`, or a commit on the default branch or detached/unresolved HEAD (ask in interactive `default` permission mode; deny when `permission_mode` is missing or non-default because the ask cannot be trusted to reach the owner). "Tests pass before a commit is offered" and "branch for non-trivial work" are **not** machine-checked and the marker must not imply they are |
| `analysis_write_result` | `analysis.before-mutation` | § Analysis before mutation — **subset**: the first edit to a planning/design document in a session **raises a reminder**. The rule's substance (was this turn analysis-only?) is not decidable by a hook |
| `d2_ledger_reminder_result` | `verify.owner-verify-d2` | § Verify against reality, not memory, the **Owner-verify** bullet — **subset**: an edit matching the consumer's configured `[d2_ledger] sensitive_paths` globs |
| `delegation_nudge_result` | `delegation.tier-floor` | § Route by task kind — the tier floor — **subset**: uninterrupted read/shell/edit volume without a delegation **raises a nudge, then an ask in interactive `default` permission mode; a missing or non-default mode escalates that ask to deny** |
| `role_on_code_result` | `role.declaration` | § Role declaration — **new prose written by C53** — **subset**: the first edit to a code file in a session, which is the design→code switch the SessionStart reminder cannot catch |
| `session_start_result` | `Runtime classification: operational` | — rationale required, see below |

Four clauses fix what the table alone leaves open:

- **The orphan gets prose, not an exemption.** C53 adds a `## Role declaration` section to
  `guardrails/_common.md`. Marking the callable operational instead is the unreviewed exemption F7
  exists to prevent.
- **`session_start_result`'s rationale must say why operational is not a demotion.** It authors no
  rule; it aggregates the agent roster and re-delivers rules owned elsewhere at session start —
  **and on Codex it is the only delivery channel for the delegation rule**, because `@`-imports are
  not expanded there (C39). Delivery is not ownership, so the classification stands; without the
  second half a reader mistakes "operational" for "incidental".
- **`verify.owner-verify-d2` declares that its coverage is the consumer's.** The callable observes
  only the globs a consumer sets in `[d2_ledger] sensitive_paths`; unset, it returns `None`. The
  marker states that dependency, and C53 emits `configured` / `not configured` as a finding so the
  state is visible rather than assumed — C59 only aggregates it. What the unconfigured state
  actually costs is **one channel of three**: the pre-commit `d2_ledger.py check --changed`
  **over**-warns when unconfigured (it cannot discriminate, so it warns on everything — a recorded
  owner decision), and the SessionStart counter still runs off `D2_LEDGER.md`. A future `init` slice
  seeds a narrow archetype-derived default, moving the default from *off* to *on and narrow* without
  touching existing consumers. Erroring on a ledger with no globs is rejected: it contradicts
  [ADR 0007](0007-d2-ledger.md) §4's warn-first decision — a red gate before the habit holds gets
  routed around — and punishes a project that keeps the ledger deliberately by hand. Under the
  former Python 3.9 floor, an older host read the globs as empty because `tomllib` was unavailable.
  C68/D2-34 later removed that supported-host limitation with one Python >=3.11 floor; import
  failure remains conservative but is no longer a supported runtime.
- **Grammar and namespaces are locked.** In `Runtime check: <id> — <prose>` the ID is the **first
  token** and everything after ` — ` is human prose the parser ignores; the tail is not decoration,
  because five of the six markers claim a subset and a subset can only be described in words.
  Policy IDs and F1 finding codes are stable dotted slugs that look alike and are **separate
  namespaces**; the parser reads only `Runtime check:` and `Policy ID:` lines, so no `policy.`
  prefix is added to solve a problem only human readers have.

**Conversion is C53's, deliberately not done at design time.** Converting the prose before the
checker exists would leave the tree asserting a join that nothing verifies — the exact stage-1
defect this shape targets.

**F13 verification carriers.** `self_ci` fixtures independently reject an unknown, duplicate,
malformed or prose-less policy ID; a prose ID with no callable; a public result with no
classification; an operational classification with a prose marker or an empty rationale; dual
classification; a legacy live `Enforced by` / `**Enforced**` declaration; and deletion on either
side. For every seeded join failure, the diagnostic assertion pins the policy ID, callable and prose
location, explicitly naming the absent side when the violated relation has no coordinate. Dropping,
swapping or misreporting any of the three fails the exact-output test.

F15's contract fixture pins the six shipped callable→policy-ID bindings and the one shipped
callable→operational-classification assignment. A coordinated ID rename on both structural sides, or
changing `session_start_result` away from its operational assignment, fails that fixture even though
the live join remains balanced. The five subset marker tails are pinned as shipped text too: deleting
a boundary, widening it to the surrounding section, dropping detached/unresolved HEAD from the
commit subset, or reducing the delegation subset to an unconditional `ask` fails the exact-marker
test.

Two content carriers are separate from structural non-emptiness. Replacing
`session_start_result`'s required rationale with text that omits either “delivery is not ownership”
or Codex's only-delivery-channel fact fails its shipped-rationale test. C53 extends the existing
`tools/d2_ledger/d2_ledger.py` check path with a C51 `Finding` and evaluates coverage before the
current no-pending early return, so an empty ledger cannot hide whether
`[d2_ledger] sensitive_paths` is configured. The named seam is exercised twice: configured paths
must emit `configured`, absent configuration must emit `not configured`, and emitting neither or
the wrong state fails the C53 contract suite. C59 only aggregates those findings and remains outside
their production seam.

### F17 — generated ownership is declared per planned output

`PlannedFile` carries one mandatory ownership mode, beside the path and content that already make
the generator the declaration owner:

- **`bannered-file`** — sync owns the whole file and its syntax admits the generated banner;
- **`structured-file`** — sync owns the whole structured file, whose grammar admits no comment
  banner; exact planned-content drift remains its provenance check;
- **`field-owned`** — sync owns only named keys or entries inside a hand-owned file and preserves
  everything outside that declared region.

Every planned output has exactly one mode; a contract fixture pins the complete path-to-mode
population and, for `field-owned`, its selectors. A missing or fourth mode, two modes on one path,
a field-owned entry without selectors, or a wrong concrete assignment fails. The declaration stays
in the generator rather than in a verifier list. `AGENTS.md` is hand-owned and outside the
planned-file population; it is the split-owned item
in the always-loaded definition, not the only split-ownership relation globally. Inside the planned
population, `.claude/settings.json` and `.akmon.toml` express that relation through `field-owned`.

C55 exposes one pure ownership checker from `bin/sync.py`, the generator side, and returns C51
Findings. Both `verify.py` and `self_ci` call that same function: verify covers each real consumer
tree, while self-CI runs the contract fixtures generated from akmon's mounted- and package-mode
declarations so the standard is not exempt. The two
banner relations have exact error identities:

- `boundary.missing-banner` — a planned `bannered-file` lacks its banner;
- `boundary.stale-generated` — an artifact carries a banner in banner position but no
  `bannered-file` declaration owns its path.

The stale scan is limited to generator-declared bannered output surfaces: the root vendor-pointer
population, generated `.claude/skills` stubs, and configured package materialization. It does not
follow symlinks and inspects only regular UTF-8 files. VCS and cache paths, the mounted akmon source
tree, `AGENTS.md`, structured and field-owned outputs, and arbitrary user paths are excluded. A
candidate must carry the exact HTML-comment or `#`-comment banner within its first four logical
lines. The root embedded in the banner is not required to equal the currently configured root, so
an artifact left by a root rename remains detectable; a later quoted marker is not ownership.

The violations are isolated from existing content-drift and obsolete-skill checks. For the
forward direction, a fixture declares a `bannered-file` whose planned content lacks the banner,
syncs that exact content and then requires `boundary.missing-banner` at error severity — generic
stale-content output cannot satisfy it. For the reverse direction, a non-skill bannered target is
renamed in the generator, the new target is synced while the old one is retained, and verify must
emit `boundary.stale-generated` at error severity — neither a missing new target nor the existing
obsolete-skill path may be the reason it fails. Both mutations run through verify and through a
copied akmon-tree self-CI fixture; omitting either integration or downgrading either finding to warn
fails the contract suite. Separate boundary fixtures cover each included surface; symlink,
non-regular, non-UTF-8, VCS/cache, mounted-source, `AGENTS.md`, arbitrary-user, structured-file and
field-owned candidates are ignored; an exact banner on line four is detected while the same banner
on line five is ignored; and an exact head banner containing an old root is detected. Each oracle
changes one boundary fact while keeping the other facts valid.

**Accepted cost.** Every planned producer names a mode, the fixture duplicates the finite mode
assignment as a regression pin, and the stale scan performs one bounded tree walk. **Rejected:** a
universal banner, which makes valid JSON and mixed-owned outputs red; inference from suffix or path,
which creates an implicit second declaration; a sidecar manifest, which is a second list that can
drift; and content-hash drift alone, which cannot identify an authoritative-looking artifact after
the generator stops owning its path.

### F18 — always-loaded growth is held by a two-scope ratchet

Always-loaded means everything reaching the model before it asks for anything. The two measured
scopes are deliberately different:

- **akmon-shipped** is the marked akmon block in `AGENTS.md`, the complete guardrail chain it
  imports, and the selected per-language guardrail;
- **consumer total** is the whole hand-owned `AGENTS.md` plus that complete imported chain and
  selected per-language guardrail.

The marked block begins at `## Dev layer — akmon` and ends before the next peer `##` heading or
EOF. Imports are resolved transitively and the population is counted as a union, so an imported
selected file is not counted twice. Vendor pointers, hook wiring, roles, pipelines, skills and
on-demand documents are outside both scopes. Lines are `len(text.splitlines())`; bytes are
`len(text.encode("utf-8"))`; member counts are summed with no synthetic separator.

Each scope must satisfy both inclusive dimensions. Decimal bytes are normative: `12 KB` means
`12,000 bytes`, and `25 KB` means `25,000 bytes`.

| scope | inclusive cap | checker and result |
|---|---|---|
| akmon-shipped | `≤210 lines` and `≤12,000 bytes` | `self_ci`: error |
| consumer total | `≤460 lines` and `≤25,000 bytes` | `verify.py`: warn; exit 1 under `--strict` only |

Both checks emit the exact stable code `caps.always-loaded`. Their target distinguishes the scope,
and the diagnostic reports that scope's measured line and byte counts beside both caps. Enforcement
and rendering use the same counters; stale or hard-coded output is a contract failure.

The contract suite pins the populations and excludes the hand-owned remainder of `AGENTS.md` and
on-demand documents from the akmon-shipped scope. For each dimension of each scope, isolated
`cap−1`, `cap`, and `cap+1` fixtures hold the other dimension below its cap. The first two pass;
`cap+1` produces the exact code and scope-specific severity, with the complete consumer
warn/strict-exit matrix. Reporting isolation uses an equal-byte replacement of a one-byte character
with a newline to change only the line count, adds one byte inside an existing logical line to
change only the byte count, and separately mutates each cap without changing either actual or the
other cap. Each corresponding rendered value must change while the other three remain exact.

**Accepted cost.** One counting implementation produces two scope results across two dimensions and
their regression fixtures, and the ratchet initially blesses today's size instead of reducing it.
Consumer-total excess remains a warning because its largest artifact is hand-owned. **Rejected:**
one hard cap over the total chain, which lets akmon fail a consumer over content it does not own; one
warn-only cap, which makes akmon-owned growth advisory; adopting the borrowed `≤150 lines`
immediately, which is red on arrival and comes from a differently shaped artifact; and waiting for
C60 before adding any ratchet, which leaves growth unbounded. C60 separately justifies a reduction
target and then lowers the caps; relocation versus deletion remains its in-task decision.

### F19 — the capability contract lives in top-level `CAPABILITIES.md`

C57 creates one shipped top-level `CAPABILITIES.md` beside `MODEL.md`. It owns the complete
human-readable matrix; README retains a short delivery summary with no enforcement claim. A16 later
consumes these prose cells and owns the data schema, generation and single-source conversion. That
bounded prose-to-data window is explicit rather than pretending C57 already implements A16.

Every capability row carries exactly six axes:

1. `documented`;
2. `delivered`;
3. the exact `vendor / version / event / matcher` route;
4. normal-path effect from `none / advisory / ask / deny`;
5. crash posture from `fail-open / fail-closed / unmeasured`;
6. `evidence`.

No axis or route coordinate is omitted. A fact without measurement uses an explicit unmeasured
value; any measured assertion requires non-empty evidence, while an unmeasured assertion requires
empty evidence. An `ask` or `deny` claim additionally requires a fully measured route and crash
posture. The encoding remains C57's in-task decision; prose-pattern citations are not the schema.

Inside marked matrix regions, every axis is mandatory. Outside them, shipped vendor-harness claims
may not use bare `enforced`, `enforces`, or `✅`/`⚠️` adjacent to a vendor or harness event. Claims
about akmon's own in-process checkers are outside this scanner, as are C53's guardrail runtime
markers: neither has a vendor route or crash posture to encode here.

The `self_ci` checker reports through C51 with exact error codes:

- `matrix.missing-file` — the top-level file or its marked matrix region is absent;
- `matrix.missing-axis` — any axis or route coordinate is absent;
- `matrix.invalid-value` — an effect or crash value is outside its closed vocabulary;
- `matrix.unqualified-effect` — `ask` or `deny` lacks a measured full route or crash posture;
- `matrix.uncited-claim` — either direction of the evidence relation is violated;
- `matrix.bare-claim` — closed enforcement vocabulary appears in a forbidden location.

> **Amendment — [D2-29], owner-approved: two claims are exempted by name.** The rule above
> stands for every `ask`/`deny` claim with one closed exception: the Claude commit guard (`deny`)
> and the Claude delegation nudge (`ask`) — the two enforcement claims that existed when C57
> landed — carry an unmeasured crash posture as a **warn** that still fails `--strict`, because
> their numbers are C52's measurement campaign and §7 forbids holding C57 behind it. The list
> lives in the checker and only shrinks; a test fails once either claim records a measured crash
> posture while still listed, so C52 landing restores the unexempted rule. Rejected: splitting
> the code for every claim, which would have let each future `ask`/`deny` claim pass an ordinary
> run with no crash measurement, permanently.
>
> **Expired — C90 / D2-47.** Both claims now record a measured crash posture, `fail-open`: the
> C87 guard answers a crash with exit 0 and an owner notice and the tool call runs, and a hook
> that dies with exit 1 is fail-open as well, on every tool either claim's matcher names (M69,
> M70, M77). The list could only shrink; with its last entries gone it went too, so the rule above
> stands for every claim, unexempted.
>
> Two rules were also **strengthened**, closing holes the paragraph above assumed shut:
> `matrix.missing-file` now covers a marked region holding no claim or carrying a second marker
> pair, and `matrix.invalid-value` covers a line inside the region that fits no claim form, an
> unknown axis key, and a repeated axis. Without those, a gutted matrix passed every rule here by
> having no rows to check, and a claim could carry two contradictory readings of one axis.

Each axis, route coordinate, value and closed token has its own parameterized mutation; fixtures for
in-process checker prose and C53 markers assert the scanner's negative boundary. The implementation
is observed red before conversion: the current tree lacks `CAPABILITIES.md`, and legacy README
vendor claims exercise `matrix.bare-claim`. C57 then creates the marked matrix, removes the legacy
matrix and leaves the claim-free README summary; the same checks must go green.

**Accepted cost.** A human-readable matrix is duplicated until A16 consumes it, and the top-level
file adds a shipped artifact. **Rejected:** keeping compressed README cells plus a legend, which
recreates the overloaded glyph under a denser spelling; and placing the matrix under `meta/`, where
the consumers whose harness behavior it describes will not encounter it.

### F20 — vendor tool and matcher names are versioned data behind neutral owners

[Design lock](../design/stage1-hardening-contracts.md) §8 and [C46](../TASKS.md) own the
implementation detail. `hook_core` remains the sole owner of the
neutral capability vocabulary — `edit`, `shell`, `read` and `subagent` — while one
version-stamped harness inventory is the sole owner of vendor tool and matcher spellings. Generated
agent tool sets, generated hook matchers and adapter normalization consume those owners; a generator
may neither restate a vendor spelling outside the inventory nor invent a neutral capability beside
`hook_core`.

The agent population is exact too: `k_explorer`, `k_reasoner` and `k_auditor` are restricted to
`{read, shell}`, while `k_mechanic`, `k_validator` and `k_implementer` carry one explicit
unrestricted sentinel rather than an inferred or vendor-named tool list.

At generation time, `sync` maps neutral capabilities through the selected inventory. A mapped name
outside that inventory is an error. A capability with no vendor name degrades explicitly to `shell`
and emits a warning naming the widened boundary. When a declared optional harness binary is present,
the C57-owned query map supplies its detected version for comparison. For each absent harness,
generation independently uses the declared version and records that assumption. An unknown detected
version uses the newest known inventory, emits a warning and records both selected and detected
versions in the generated banner. Hook matcher names follow the same inventory and drift behavior as
agent tool names; they are not a separate spelling authority.

The public finding identities are closed:

- **error `harness.invalid-inventory`** — an unstamped, duplicate or malformed inventory row, or a
  missing required map;
- **error `harness.unknown-name`** — a neutral mapping emits a name outside the selected inventory;
- **warn `harness.capability-degraded`** — a capability uses the selected inventory's shell fallback;
- **warn `harness.unknown-version`** — a detected version uses the newest known inventory;
- **error `harness.duplicate-name-owner`** — executable code declares a second vendor-name set or
  map;
- **error `harness.unknown-capability`** — a consumer uses a neutral token `hook_core` does not own.

Every `harness.*` error exits 1 through both `sync` and `sync --check`. Warn-only operation exits 0
through both callers when `sync --check` has no independent generated drift. The exact checker,
mutation and failure carriers remain in design §8 and C46 rather than being duplicated here.

**Accepted costs.** A shell fallback is wider than a read/sweep tool set, so the read-only boundary
then rests on the agent body's prose. An unknown future harness version may be generated from stale
data rather than blocked; the warning and durable banner make that risk visible. The inventory and
its bidirectional ownership checks add maintenance, and the banner becomes part of C55's generated
surface. The live `AGENT_SPECS` defect remains red until C46 so the implementation proves the
transition against the real failure.

**Rejected:** keeping the map in code; declaration-only version stamps; making harness detection
mandatory; failing generation solely because a detected version is newer than the inventory;
degrading every unknown version wholesale to `shell`; shipping akmon-owned tools over MCP; and
reopening the agent-name half already decided by ADR 0011.

### F21 — one machine-written dispatch ledger with one path and schema

[Design lock](../design/stage1-hardening-contracts.md) §9 and [C58](../TASKS.md) own the detailed
carriers. The ledger has one code owner and one current path. `delegation-log.py` is the sole writer;
`stats.py` and `coverage_map.py` are the complete default-reader population. The current path is
`<AITNA_ROOT>/model-routing.log`, derived from the configured dev-layer root, and the legacy path is
exactly `.claude/model-routing.log`. Default readers read the legacy file first and the current file
second, preserve each file's row order and perform no deduplication. An explicit `--log` reads only
the supplied path.

Every current record is one seven-field TSV row:

`v1 · timestamp · session_id · subagent · model · zone · description`

The first field is the literal `v1`. Each of the six data fields is normalized as
`" ".join(str(value).split())`; an empty result becomes `-`, so tabs, carriage returns and newlines
cannot add columns or records. `timestamp` remains an offset-bearing ISO value. The row records an
observed Claude `PreToolUse` dispatch request normalized through C46's `subagent` capability; it
makes no claim that launch or completion occurred. F10 remains owned by the design lock's register
and §9 rather than being re-decided here.

The public self-CI failures are closed, all at **error** severity and exit 1:

- `ledger.wiring-drift` — the normalized event, matcher or generated hook wiring changes;
- `ledger.owner-drift` — a writer or default reader is missing or extra, or executable code adds a
  rotation or truncation owner;
- `ledger.path-drift` — writer/read order, current or legacy path, explicit-override fallback or the
  guardrail join drifts;
- `ledger.schema-drift` — the marker, field count/order, normalization, empty sentinel, timestamp form
  or legacy/new parser boundary drifts;
- `ledger.ignore-drift` — either the legacy or resolved current ledger path is no longer gitignored.

The new path accepts only exact `v1` rows; the legacy path retains exact four- and six-field read
compatibility. A malformed or unknown-version row makes either reader report path, line and a
structural reason without echoing record content, exit 1 and produce no derived artifact. Readers
never repair either source file.

The normal guarantee is one serialized intact newline-terminated record per successful in-envelope
dispatch request: the writer takes one exclusive file lock around the append and releases it after the
complete record is written. C58 owns no numeric cap, durability or rollback protocol. Total-cap
overflow and lock/open/write failures — including short-write, durability and rollback carriers —
belong to C52's visible fail-open posture and carry no completeness guarantee; D2-23 owns the concrete
literals. This ownership handoff adds no C52/D2-23 dependency edge to C58. Manual tampering is
indistinguishable from a machine-written row; only the sole code owner is checked. There is no
automatic rotation.

**Accepted costs.** Migration temporarily reads two files; preserving per-file order without
deduplication can expose duplicate historical rows, and an explicit path deliberately bypasses the
default pair. A local append-only ledger can be incomplete after a visible fail-open exception and
can be manually forged. The exact schema, path and finite reader/writer population now require an
explicit contract update when they change.

**Rejected:** a second model-written ledger, whose writer degrades under the context pressure the
record exists to survive; retaining a Claude-owned current path; writing both old and new paths;
automatic migration or deduplication that rewrites local history; inferring launch/completion from a
dispatch request; lock-free best-effort append under normal parallel dispatch; treating manual content
as attestable; and adding automatic rotation before the F6/C52/D2-23 boundary is measured. Detailed
fixture mechanics remain in design §9 and C58.

### F22 — `akmon status` is a fresh, read-only composition of two existing providers

[Design lock](../design/stage1-hardening-contracts.md) §10 and [C59](../TASKS.md) own the detailed
carriers. The exact provider order is **verify, then sync**. The verify provider runs the existing
consumer verifier once against the consumer's current state; its result already contains the D2
coverage/pending findings and always-loaded caps findings, so C59 neither invokes those checks a
second time nor reads their files directly. The sync provider then runs the existing `sync --check`
finding path once against that same current consumer state. The aggregate is the exact ordered
concatenation of those two provider finding sequences.

Both providers are invoked fresh for each status request and only through their existing read-only
interfaces. C59 does not cache a prior status snapshot, parse or reread D2/config/caps/generated
artifacts itself, reimplement either provider, introduce a third provider or add a finding of its
own. “Read-only” is a state-transition guarantee: neither provider may write, repair, regenerate or
otherwise mutate the consumer while answering status.

Text and JSON render that same ordered aggregate. JSON composes C51's sole canonical serializer;
text uses C51's canonical renderer. A finding present in either rendering and absent from the
provider sequences, or a provider finding dropped, duplicated or reordered, is a fidelity failure.
The stable exit matrix is the shared C51 one: any error exits 1; warnings alone exit 0 normally and
1 under strict mode; an all-clean aggregate exits 0. Rendering mode never changes severity or exit.

The active orchestration role remains an explicit residual. Its owner is the live transcript's last
main-chain `🧭 agent:` declaration, which a separate `akmon status` process cannot reliably observe.
C59 therefore reports no active-role fact and creates no persisted role marker or inferred fallback.
The accepted cost is that status cannot answer “which role is active?” outside the transcript that
owns that fact. The provider population and order also become contract surface, and every status
request pays the cost of running both providers fresh.

**Rejected:** a cached snapshot presented as current state; direct reparsing of D2, config, caps or
generated files; a second implementation or owner for either provider; separate D2/caps calls that
duplicate verify's findings; a synthesized summary, sorting or deduplication that breaks exact source
order/equality; and persisting or inferring an active role merely so status can display one. Detailed
source-set, read-only, equality, mutation and exit/rendering fixtures remain in design §10 and C59.

### The yardstick these contracts are held to

The acceptance rule for the whole stage, stated here because it governs how every contract above
is written rather than what any single one says:

- **The unit is the independently violable rule, not the shape** (F13). Rules that cannot fail
  separately may share one seed; a rule that can be violated on its own carries its own; and a rule
  whose seed needs evidence that does not exist yet is **split** — the checkable half is checked
  now and the remainder names the gate it waits on. The boundary ("independently violable") will be
  argued at implementation time, and by standing rule it is argued in favour of the separate seed,
  because a redundant test is cheaper than an unnoticed rule.
- **Review/process ownership is an explicit boundary, not a silent pass.** A semantic or
  process-owned obligation must be labelled, name the mechanical subset that is tested and state
  its residual cost. No rule described as mechanically checked receives that boundary. In F1 the
  bounded sentence heuristic is mechanical, while residual natural-language boundaries and
  imperative mood are review-owned; the F14 append on deletion is process-owned, while live reuse
  of an already recorded code remains a mechanical test.
- **No exemption class exists** (F11). The hard case is an aggregating shape that adds no check of
  its own: it is seeded against **fidelity to its sources** — mutate the source finding set and the
  aggregate must change with it; a finding dropped, reordered, or present in one rendering but not
  the other fails, **and so does one present in the output and in no source** — fidelity is an
  equality, and a one-directional seed leaves an aggregator free to invent findings while copying
  its sources faithfully. An exemption granted to the first shape that asks for one converts the yardstick
  from a rule into a preference.
- **What is a fork at all** (the counting rule locked with F10–F12): all three must hold — two or
  more defensible answers; the answer changes what a task implements or what the lock claims; and
  it cannot be deferred into a task without the lock asserting something unverified. Failing the
  first makes it a repair, failing the third an in-task decision, failing the second a
  parked-elsewhere question. Measurement gates are not forks: there is a number to obtain, not an
  answer to choose.

## Consequences

- **A breaking API change lands in one commit.** Every constructor, attribute read, fixture and
  test moves together, including `meta/bin/validate.py`'s independent Finding and every test that
  pins today's `[{level}] {message}` text. A staged migration is not available, by decision.
- **Findings become aggregatable, which is what makes [C59](../TASKS.md)'s `akmon status` possible
  at all**; it is the one consumer this lock names.
- **The join costs always-loaded budget.** C53 replaces three `> **Enforced**` blocks with six
  marker lines and adds the new section — an estimated +1…+2 lines against a measured slack of 13.
  It is compatible today, and it is recorded as a graph edge because nothing else would show when
  it stops being compatible.
- **An operational classification is auditable rather than silent.** It costs a rationale, and the
  rationale is checked for non-emptiness, so "operational" cannot be used as a quiet waiver. The
  one rationale this ADR dictates — `session_start_result`'s — is additionally pinned as shipped
  text, because non-emptiness cannot see whether a rationale says what is required of it; for
  classifications added later, non-emptiness is the mechanical half and review owns the substance.
- **Coverage of the D2 reminder is honestly the consumer's**, and stays visible as a reported
  state. Under the former Python 3.9 floor, an older host read the globs as empty because
  `tomllib` was unavailable. C68/D2-34 later removed that supported-host limitation with one
  Python >=3.11 floor; import failure remains conservative but is no longer a supported runtime.
- **Never-reuse has a manual cost (F14).** Whoever removes a check must append its code to the
  retired-code record; forgetting the append restores the current blind spot, rather than making
  it mechanically impossible.
- **The six shipped callable-to-policy-ID bindings plus one operational-classification assignment
  are duplicated in a contract fixture (F15).** That second list is accepted as a regression pin
  for coordinated two-sided renames, not as a runtime registry or an owner standing between
  guardrail prose and callable docstrings.
- **Generated ownership becomes explicit rather than suffix-shaped (F17).** The extra mode on each
  `PlannedFile` costs an exhaustive regression fixture and one bounded stale-banner walk, while
  keeping the declaration in the generator and leaving structured and field-owned files valid.
- **Always-loaded growth gets two accountable owners (F18).** Akmon's shipped share fails hard;
  consumer-owned excess warns unless strict verification is requested. The cost is duplicated
  population accounting and a ratchet that initially preserves the current shape.
- **Capability claims become inspectable before they become generated (F19).** The top-level matrix
  pays a bounded prose-to-A16 duplication cost so each route, effect, crash posture and evidence
  relation can be checked without compressing them back into a glyph.
- **Vendor names gain one versioned owner (F20).** Tool sets, hook matchers and adapter normalization
  consume one inventory behind `hook_core`'s neutral vocabulary; optional detection and durable
  provenance expose drift without making a vendor release an immediate generation outage.
- **The execution ledger gains one stable owner (F21).** One neutral path, versioned row schema,
  sole writer and complete default-reader population make ownership, migration and guardrail drift
  mechanically visible without claiming that a dispatch request proves launch or completion.
- **Status reports fresh provider-owned state (F22).** Verify then sync are invoked read-only and
  composed exactly once; the cost of refusing a persisted role fiction is that a separate status
  process cannot report the transcript-owned active role.
- **The yardstick costs roughly six to ten additional tests across the stage**, and it will
  occasionally demand a test that looks redundant. That is the intended trade.
- **Not carried here, and the rule for it.** Crash posture, timeout and input envelope are
  [ADR 0013](0013-hook-survivability-and-crash-posture.md). **F9**, **F10** and **F16** are decided in the
  [design lock](../design/stage1-hardening-contracts.md)'s register and are not re-decided here;
  D2-20 verifies them where they are. The governing rule, which replaces an earlier and stricter
  one: **F9, F10 and F16 permit an identifier and a navigational pointer only — never the choice, its
  mechanism or its consequences. F12 permits its scope rationale once, above in this ADR's Context;
  [0013](0013-hook-survivability-and-crash-posture.md) carries a pointer to it and no argument of
  its own.** F12 is treated differently on purpose: it is the decision that gives each ADR its
  scope, and an ADR that cannot say why its scope is what it is fails at being an ADR. The strict
  form — that none of the four may appear at all — was rejected once implementation was
  considered: an implementer reading an ADR with no trace of a neighbouring decision cannot tell
  deliberate absence from a lost requirement, and re-deciding it is the cheaper mistake to make.

## Alternatives

- **Keep `level`, or ship `severity` with a `level` alias** — rejected. A temporary dual
  vocabulary creates migration debt before the shared envelope has any documented external API, and
  the alias would have to be removed later against callers that by then rely on it. One standard
  diagnostic term is clearer than preserving a project-local field name; the breaking change is
  cheapest now, when every caller is in this repository.
- **Add `--json` to every adopter in C51**, or **defer the schema until a consumer needs it** —
  both rejected. The first pins a public option name that the `akmon status` fork owns and this lock
  leaves open; the second leaves F1's *absence* of `level` untestable, because nothing would
  serialize a Finding at all.
- **A central invariant registry** — `INVARIANTS.md`, a mapping constant, a decorator registry or
  generated annotations — rejected. Each is a third place that can drift from both prose and code,
  and it is precisely the drift this shape exists to detect. Keeping each fact with either the
  prose or the callable leaves nothing in between to go stale.
- **Bare `Enforced by <callable>` markers** — rejected. It is one claim where the C49 measurement
  proved three are needed (route, crash posture, input envelope), and it is the collapse that
  produced today's unqualified enforcement prose.
- **Host the role-declaration rule in `roles/README.md`** — rejected. It spends no always-loaded
  budget, but it redefines "live prose" from the always-loaded chain to any policy document, and
  widens what C53 must parse.
- **A separate `role.declaration.session-start` ID beside `role.declaration.switch`** — legal under
  the one-to-one rule, since the subsets differ, but rejected: it spends two IDs and two prose
  markers on one rule.
- **A `policy.` prefix on every policy ID** — rejected. It lengthens every ID to disambiguate two
  namespaces the parser cannot confuse.
- **Seed per shape rather than per rule** — rejected. It is the cheapest answer and it locks §2 of
  the design with half its rules unverified, which is the exact defect this stage exists to remove,
  sitting inside the stage's own acceptance criterion.
- **Seed per rule with a declared exemption list** — rejected. Visible holes beat hidden ones, but
  F11 has already ruled that no exemption class exists, and a list of exemptions is that class
  under another name.
