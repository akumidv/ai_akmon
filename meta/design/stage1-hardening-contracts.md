# Design: stage 1 — deterministic hardening contracts (A12 proposed lock)

> **Status: the register below is walked in full (F1–F12; F8–F12 decided), D2-20 is
> split from D2-23, the internal contradictions are repaired and every shape now carries a
> seeded-violation contract. What remains before the lock is the
> [A17](../TASKS.md) tail — the coherence audit and the two ADRs F12 names — then owner
> verification at [D2-20](../D2_LEDGER.md). Not locked.**
> Scope: plan items **P1.1–P1.7** plus the **P0.2 / P0.4 declarations** the stage-0 probes
> made fillable, plus the **tool-name half of [C46](../TASKS.md)**. The draft proposes splitting
> implementation per shape into **C51–C59** (+ C46; C60 carries the later cap reduction, outside
> this lock); the umbrella
> C40 would be superseded only after D2-20 owner verification. Sources:
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

So the yardstick for every shape below is not "is the rule written down" but **"what seeded
violation makes this check fail, and where is that test"**. A shape that cannot answer is not
in this proposed lock.

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
| F12 | ADR shape for stage 1 | **two: contracts/vocabulary (F1, F2, F7, F8) separate from survivability/crash posture (F3–F6)** | decided |

**What enters this register** (the counting rule the `F10+` placeholder lacked, locked with F10–F12):
a fork is registered when **all three** hold — it has two or more defensible answers; the answer
changes what a stage-1 task implements or what the lock claims; and it cannot be deferred into a
task without the lock asserting something unverified. Failing the first makes it a **repair**
([A17](../TASKS.md) (d) and (f)); failing the third makes it an **in-task decision** (C60's
relocation-vs-deletion, C57's git-dependency trigger); failing the second makes it **parked
elsewhere** (D1 mutable status levels, A16 matrix-as-data, N1 measurement, the public
`akmon status` option name). Measurement gates — the F4/F5/F6 literals — are not forks at all:
there is a number to obtain, not an answer to choose. Under this rule the register is **walked in
full**; the placeholder row is not "empty", it was three.

### Pre-lock closure ([A17](../TASKS.md))

The register is not the whole gate. Before D2-20 can be verified, A17 also owns four repairs
to this document and its ledger row:

- **D2-20 is split.** D2-20 retains the architectural F4–F6 protocol alongside F1–F3 and
  F7–F12: what counts as terminal timeout evidence, how budgets are derived, and the bounded
  fast-path/oversize semantics. Concrete vendor results, caps, entry mappings, measurements and
  timeout literals move to **D2-23**, which blocks only C52. The former `Verify (c)` premise is
  obsolete because the F8 table now exists; that table is verified normally as part of the
  consolidated D2-20 architecture gate.
- **Seeded-violation contracts are completed — done** for §7 (C57) and §8 (the C46
  tool-name half); §10 (C59) had left this item earlier via F11. Neither was a missing paragraph.
  §7 had nothing to check in the required form — every cell of today's matrix is a checkmark —
  so the contract carries three additions: `CAPABILITIES.md` as the axis-complete home with
  README reduced to a claim-free summary, a stated scope boundary against akmon's own checkers
  and against C53's guardrail prose, and a **join from the runtime declaration to the generator**
  so that half of §7 stops being unverified prose. §8's version stamp had nothing to compare
  against — no code anywhere reads a harness version — so detection is added where the binary is
  present, an unknown version warns and stamps the generated banner rather than failing, and the
  mechanism is seeded against its **root cause**, a second owner naming vendor tools outside the
  map. Both shapes are observed **red before green**: neither `README.md:200` nor
  `routing.py:364`/`:470`/`:503` is repaired ahead of its task.
- **§9 (C58) is scoped** — settled by **F10**: dispatch-only, completion half spawned as
  [N4](../TASKS.md). The bullet remains here as the record of what the repair was.

The closure also produces **two ADRs, not one** (**F12**): the contract/vocabulary decisions
(F1, F2, F7, F8) — what other work will cite — kept separate from survivability and crash posture
(F3–F6), which N1's measurements are expected to amend. An ADR that must be revised by
measurement should not carry the stable vocabulary along with it, or every timing number formally
disturbs a decision that has already been built on. The cost is a boundary to maintain and two
references where one would do.
- **The internal contradictions are repaired — done** ([A17](../TASKS.md) (f)). Five
  were listed and a sixth surfaced while repairing them; none was purely editorial, so each is
  recorded with what it changed. (1) The order table's C53 row now names the **F8 table**, marked
  as a decision rather than a task to wait for. (2) The C55 row read `P0.4 declaration (§6)`,
  which did not distinguish the declaration from C56's implementation; it now names the
  always-loaded *definition* explicitly, and the consequence is that **C55's only task dependency
  is C51** — it was never waiting for C56. (3) **C60 is removed from the order table**, whose own
  caption limits it to dependencies internal to the proposed package; the `C56 → C60` edge moves
  to *Not in this proposed lock* so it survives the deletion. (4) **A16 becomes `blocked (after
  D2-20)`** in TASKS.md: it cannot settle a vocabulary that inherits F3's axes before F3 is
  locked, and its first job — consuming C57's cells — sits behind the same gate, so the honest
  status costs nothing. A third status level for *decided but not locked* would be more precise
  and is deliberately **not** invented here: that is D1, and it is parked. (5) §2's guard is
  scoped to the **nine spawned entry points**; adapters and `hook_core` are imported, have no top
  level, and are covered by the caller's guard — which turns their single-write output into a
  contract, since a guard cannot un-write truncated stdout. (6) Found while repairing (1): C53
  **writes into the surface C56 caps**, an edge the graph omitted. The numbers do not collide
  today (+1…+2 lines against 13 lines of slack), which is the reason to record the edge rather
  than to skip it — nothing else would show when they begin to.

## Order and dependencies

| # | shape | plan | task | depends on |
|---|---|---|---|---|
| 1 | shared finding envelope | P1.6 | C51 | — |
| 2 | hook survivability | P1.1 | C52 | D2-23 evidence gate |
| 3 | invariant canary | P1.2 | C53 | C51, P0.3 inventory (N2, done), F8 table (§3); writes into the always-loaded surface C56 caps |
| 4 | version ↔ changelog cross-check | P1.3 | C54 | C51 |
| 5 | source/generated boundary check | P1.7 | C55 | C51; always-loaded set definition (§6 declaration — not C56's cap check) |
| 6 | always-loaded caps | P0.4 | C56 | C51 |
| 7 | OS contract + matrix vocabulary | P0.2 | C57 | — |
| 8 | tool names: neutral capability + vendor map | — | C46 | C51, C57; emits a provenance banner line C55 checks |
| 9 | execution ledger | P1.5 | C58 | C57 (matrix cell for the Codex gap) |
| 10 | `akmon status` | P1.4 | C59 | all of the above |

Every implementation edge below also depends on owner verification of D2-20; the table shows
only dependencies internal to the proposed package. C52 alone has the additional D2-23 evidence
gate, so missing runtime numbers cannot hold C51 or C57 behind an unrelated measurement campaign.

Two edges in the table are not task dependencies and are spelled out so they are not read as
such. C53's F8 edge is a **decision** it must have before code, not a task to wait for. C53's
second edge is a **collision**, not an order: C53 replaces three `> **Enforced**` blocks with
six markers and writes the new `## Role declaration` section, all inside the surface C56 caps —
an estimated +1…+2 lines against a measured slack of 13 (§6: ~197 shipped against a 210 cap), so
the two are compatible today and the edge is recorded because a graph that omits it cannot show
when they stop being compatible. C55 needs the always-loaded *definition*, which §6 already
carries; its only task dependency is C51.

P1.6 leads because eight of the nine remaining shapes emit findings. P1.1 shares no findings
dependency and can be engineered in parallel with C51 only after D2-23 is verified. P1.4 is last
on purpose: it aggregates a finished vocabulary
instead of inventing one.

## 1. Shared finding envelope (P1.6 → C51)

**Decision.** Extend the existing `bin/verify.py::Finding` into one shared stdlib-only module
`bin/findings.py`, with fields `severity · code · message · target · fix`. `severity` carries the
`ok / warn / error` vocabulary and preserves the current exit-code contract (errors exit 1;
warnings exit 1 only under `--strict`). `code` is a stable dotted slug naming the check (`boundary.hand-edited`,
`caps.always-loaded`, `invariant.orphan-hook`) — unique, never reused after a check is removed.
`target` is the file or artifact the finding is about. `fix` is one sentence in the imperative,
and it is **required**: a finding a reader cannot act on is a defect of the check, not of the
tree. Adopted by `verify.py`, `meta/bin/validate.py`, `sync --check`, and `meta/self_ci.py` —
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
becomes its first process-boundary consumer. Text rendering remains
`SEVERITY code target: message → fix`, one line per finding. There is exactly one canonical
serializer (method or shared pure function, not both); adopters and C59 must call it rather than
repeat the field mapping. Its output uses JSON-safe stdlib values, preserves Unicode, does not
mutate the Finding, and passes `json.dumps` directly.

**Out of scope.** Hooks do not adopt the envelope: they speak the harness's JSON contract on
stdout and prose on stderr, and a findings object there would be a third output shape on a
channel whose visibility is unverified.

**Seeded violation.** A check constructed without `fix` fails a test; a duplicate `code` across
adopters fails a test; serialization missing a canonical field, adding `level`, or changing a
value fails the exact-schema contract test. The serializer is also tested with Unicode and an
empty valid `target`; a local field mapping in an adopter is rejected by the shared-owner test.

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
   carries the route as an argument (`:203`, `:222`–`:244`). It prints the exception class and
   the hook name to stderr and exits 0. **The adapters and `hook_core` get no guard of their
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

**Owner choice F5 — C: measurement-derived budgets by hook class.** N1 inventories
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
sentinel literal; F6 bounds supported inputs; N1 measures entrypoints directly without a host
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
literals, N1 inventories and measures every valid input axis that can grow with a consumer:
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

**Seeded violation.** A wrapper without the guard fails a test that feeds it a payload
engineered to raise inside the handler and asserts exit 0 + exactly one stderr diagnostic. A
deny-class fixture proves both halves: an explicit handled deny remains deny, while an exception
on the same route exits 0 and is reported. The crash path emits no deny/ask, malformed JSON, or
partial stdout. Its stderr names only the hook and exception class — never payload values,
commands, file content, session ids, or secrets. This contract is parameterized over all nine
spawned entry points rather than demonstrated on one representative.

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
| `git_commit_guard_result` | `commits.owner-owned` | § Commits & ownership — **subset**: the AI `Co-Authored-By` trailer (deny) and `push`/`tag`/`merge` or a commit on the default branch (ask). "Tests pass before a commit is offered" and "branch for non-trivial work" are **not** machine-checked and the marker must not imply they are |
| `analysis_write_result` | `analysis.before-mutation` | § Analysis before mutation — **subset**: the first edit to a planning/design document in a session raises a reminder. The rule's substance (was this turn analysis-only?) is not decidable by a hook |
| `d2_ledger_reminder_result` | `verify.owner-verify-d2` | § Verify against reality, not memory, the **Owner-verify** bullet — **subset**: an edit matching the consumer's configured `[d2_ledger] sensitive_paths` globs (see F8/3 below) |
| `delegation_nudge_result` | `delegation.tier-floor` | § Route by task kind — the tier floor — **subset**: uninterrupted read/shell/edit volume without a delegation raises a nudge, then an ask |
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
holds gets routed around — and punishes a project that keeps the ledger deliberately by hand. Note
the limit neither option removes: `tomllib` is 3.11+ stdlib, so on an older host the globs read as
empty however they are configured, and only the marker's wording describes that state.

**F8/4 — marker line grammar (locked).** `Runtime check: <id>` — the ID is the **first token**;
anything after ` — ` is human prose the parser ignores. The tail is not decoration: three of the
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

- a **non-final** version **requires** a `## Unreleased` heading in CHANGELOG. Non-final is the
  full PEP 440 set — `.devN`, `aN`/`bN`/`rcN`, `.postN`, `+local` — not `.devN` alone; final is
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

**Seeded violation.** A fixture with a mismatched version/heading pair fails `release_check`;
both consistent states pass; disagreeing `pyproject`/`_STATIC_VERSION` literals fail; a tag with
no heading warns without failing; a fixture with no version source at all produces a skip finding
rather than a pass.

## 5. Source/generated boundary (P1.7 → C55)

**Decision.** **The generator is the declaration.** `sync.py`'s owned-file set is the boundary —
there is no hand-maintained second list to drift. The check is two-way:

- a file `sync` owns that carries no generated banner → **error** (someone hand-created or
  hand-stripped it);
- a banner on a file `sync` no longer owns → **error, stale artifact** (a generator's leftover
  that now looks authoritative to a reader and to `sync --check`).

**Fork — content-hash drift detection instead of banner presence.** Rejected as a duplicate:
`sync --check` already compares content. This shape is about *ownership declaration*, which is
what nobody checks today, and the stale-artifact direction is reachable only from ownership.

**Deferred, explicitly rather than silently.** The plan folds doc gardening (dead links,
staleness) into P1.7 "as the same sweep". It is not the same sweep — link checking needs its own
traversal and its own noise budget — so it leaves stage 1 and is carried in **C60**'s
neighborhood as a later item, not dropped.

**Seeded violation.** Stripping a banner fails; renaming a generated file so `sync` stops owning
it, without deleting the old one, fails.

## 6. Always-loaded caps (P0.4 → C56, reduction in C60)

**Declaration.** This block is the shared definition, consumed by C55 as well: the
source/generated boundary has to know that `AGENTS.md` is hand-owned by the consumer while
carrying a generated akmon block — the one artifact with split ownership. C55 depends on the
definition, not on C56's cap check. Always-loaded = every artifact that reaches the model's
context without the model asking: the akmon block in `AGENTS.md`, the guardrail chain it imports, and the
per-language guardrail. Measured on the attached consumer (N2, P0.4): **433 lines / 23 613 bytes**
total, of which **AGENTS.md is 232 lines and hand-owned**, and akmon's own shipped share is
`_common.md` 133 lines / 7 689 B + `python.md` 52 / 2 637 B + the ~12-line pointer ≈ **197 lines /
~10.8 KB**.

**Decision — a ratchet, in two different strengths:**

| scope | cap | severity | where | current |
|---|---|---|---|---|
| akmon-shipped always-loaded | ≤ **210 lines / 12 KB** | error | `self_ci` | ~197 / ~10.8 KB |
| consumer total chain | ≤ **460 lines / 25 KB** | warn (error under `--strict`) | `verify.py` | 433 / 23.6 KB |

The two differ because the largest single item is not akmon's to shrink: `AGENTS.md` is
hand-owned by the consumer, so failing their build over it would be akmon dictating content it
does not own. akmon's own share is an error, because that one is entirely ours.

**Fork — adopt the borrowed ≤150-line reference immediately.** Rejected *here*, adopted as
separate work. A cap that fails on the day it ships either blocks the stage or gets waived, and
a waived cap teaches everyone that caps are advisory. **Stated drawback, since it is the real
one: a ratchet blesses the status quo.** That is exactly why the reduction is a task with its own
id — **C60** — and not a "later we'll tighten it" sentence. C60 also has to *justify* the target
rather than inherit it: ≤150 is wshobson's number for a differently-shaped artifact, and akmon
must argue its own.

**Seeded violation.** A fixture guardrail padded past the cap fails `self_ci`; a padded consumer
fixture warns under `verify` and fails under `verify --strict`.

## 7. OS contract and matrix vocabulary (P0.2 → C57)

**Declaration (runtime).** akmon requires **a POSIX shell and `python3` on PATH**. The Codex
route additionally requires **git on PATH**: the generated Codex wiring resolves the project root
through `$(git rev-parse --show-toplevel)` (`bin/sync.py:203`), where the Claude wiring uses the
harness-provided `$CLAUDE_PROJECT_DIR` (`:252`). **`claude` and `codex` are optional**: §8's
inventory check queries whichever is on PATH and falls back to the declared version when neither
is — so they are declared as optional binaries rather than left unnamed. **Windows is not
supported** — stated as unsupported, not as "untested", because a hedge is what lets a broken
path stay ambiguous.

**The runtime declaration is joined to the generator, not left as prose.** C57 extracts the
external binary names from the command strings `sync.py` emits — they are few and literal — and
compares them against the declared set. An **undeclared** binary in generated wiring is an
**error**; a declared binary no longer used anywhere is a **warn**. The asymmetry is F9's: an
under-declaration breaks a path in a consumer's repository, an over-declaration is only stale
prose. Without this join, half of §7 is a rule akmon states and nothing verifies — the exact
defect class stage 1 exists to remove.

**Declaration (matrix vocabulary).** A capability records independent axes rather than one
overloaded grade: `documented`, `delivered`, the exact vendor/version/event/matcher route, the
observed normal-path effect (`none / advisory / ask / deny`), and crash posture
(`fail-open / fail-closed / unmeasured`). Bare `enforced` and checkmarks are invalid. A normal-path
`ask` or `deny` claim must name its exact route and crash posture — the C49/F3 lesson: an effect
exists only on the route measured, and crash behavior is a different fact. C57 adds a static
check rejecting bare `enforced` and enforcement-like entries missing either qualifier.

**Where the matrix lives.** Five axes over nine capabilities and four vendors do not fit a
README table. The axis-complete matrix moves to a shipped top-level **`CAPABILITIES.md`**,
beside `MODEL.md` and `ARCHETYPES.md`; `README.md` keeps a short delivery summary that makes
**no enforcement claim at all**. A16 then generates one file rather than a section inside
another, which is the cheapest form the seam can take. Rejected: a compact cell notation plus a
legend — a legend is a compression, and a compression reintroduces the checkmark under a new
name; also rejected: hiding the matrix in `meta/`, since it is addressed to consumers.

**What the check covers, and what it deliberately does not.** The subject is **claims about a
vendor harness**. Inside `CAPABILITIES.md`'s marked regions the five axes are mandatory; outside
them, a closed vocabulary (`enforced`, `enforces`, and `✅`/`⚠️` adjacent to a vendor or harness
event name) is rejected in shipped docs. Two boundaries are stated so the audit does not read
them as gaps: **akmon's own checkers are out of scope** — `pipelines/tasks.md`'s "Thresholds
(enforced by `verify.py`)" is an accurate claim about an in-process check, where "route" and
"crash posture" mean nothing — and **guardrail prose belongs to C53**, whose F7/F8 markers
already own `guardrails/_common.md`'s three `> **Enforced**` blocks.

**The conversion happens inside C57, and the tree is the red state.** Every cell of today's
matrix (`README.md:82`–`:92`) is a checkmark, so the check fails on the whole table the day it
exists; converting first would leave it with a fixture where it could have had the tree — F9's
rule for C54, applied unchanged. The live defect it must catch is already visible one screen
below: `README.md:200` claims delegation is **enforced** without qualification, while the
matrix's own delegation-log row records `❌ subagent hook payload unverified` for Codex. The
claim is global; the measurement is one route on one vendor.

**Fork — remove the git dependency now** (resolve the root through `python3` instead, reusing
the discovery already implemented for package mode). Not now, and the trigger is recorded: it
is the right fix, but it rewrites generated wiring that C52 is already touching in the same
stage, and no consumer has hit it. Revisit when a consumer reports it or when P4.2's plugin
carrier changes the wiring anyway.

**Seam — matrix as data stays A16.** C57 writes cells as prose. A16 owns the schema, ownership
and generation, and its first job is to consume these cells. The duplication window is
acknowledged and bounded by A16; it is declared here so A16 does not rediscover it as a defect.

**Seeded violation.** The checker is `self_ci` — the matrix and the generated wiring are akmon's
own, and a consumer writes no vendor claims — reporting through the P1.6 envelope. A bare `✅` or
the word `enforced` inside a marked region fails (`matrix.bare-claim`); a `deny`/`ask` cell
missing its exact route or its crash posture fails (`matrix.unqualified-effect`); replacing an
`unmeasured` cell with an assertion that cites no evidence fails, which is the measured-only rule
made mechanical. On the runtime half: adding a binary such as `jq` to a generated command without
declaring it fails (`runtime.undeclared-binary`); removing `git` from the declaration while the
Codex wiring still calls it fails the same way from the other direction; a declared binary that
no generated command uses warns rather than fails.

## 8. Tool names: neutral capability + vendor map (C46, tool-name half)

**Decision.** Agent tool sets are declared as **neutral capabilities** in the same vocabulary
`hook_core` already uses for tool kinds (`read` / `search` / `shell` / `edit`), and mapped
**neutral → vendor at generation time**. The harness inventory is **version-stamped data**
(harness id + version → available tool names), so drift is a data update and staleness is
visible. Two failure modes, both loud:

- a mapped name that is not in the known inventory → **error at `sync`**;
- a capability the harness has no name for → **explicit degrade to `shell`, plus a warn
  finding** (P1.6 envelope) that names the widened boundary — because Bash is strictly wider
  than Grep/Glob, and after the degrade the read-only property rests on the agent body's prose,
  not on the tool set.

**The stamp needs something to compare against, and today there is nothing.** No code in `bin/`,
`tools/` or `hooks/` reads a harness version — 2.1.221 and 0.146.0 were obtained by hand in N2 —
so a written stamp would make staleness *printed*, not *visible*. **Decision: detect when the
binary is present.** `sync` queries `claude`/`codex` if either is on PATH and compares; if
neither is, it proceeds against the declared version and says which one it assumed. Rejected:
declaration only (honest but toothless, and §8 would have to stop claiming visibility) and
mandatory detection (`sync` runs in repositories where no harness is installed). This is what
adds the two optional binaries to §7's runtime declaration.

**An unknown harness version warns and stamps; it does not fail.** When detection finds a version
the inventory does not cover, `sync` generates from the newest known inventory, emits a warn
finding, and writes the assumption **into the generated artifact's banner** — not only into a
warning that scrolls away: `generated against claude-code 2.1.221 inventory; detected 2.2.0`.
Erroring would brick a consumer on the vendor's release schedule, which akmon cannot preempt
because it cannot ship data for a version that does not exist yet; degrading everything to
`shell` would dismantle the read-only boundary to preserve a formality. The cost is a provenance
line in a generated banner, which is C55's surface — recorded there as an edge.

**Fork — encode the map in code (as `AGENT_SPECS` does today).** Rejected: a code map has no
version stamp, so nothing distinguishes "correct for 2.1.221" from "written in 2025". The
version stamp is the whole point of moving it to data. The mechanism is also **seeded against
its own root cause**: the defect was never a wrong name, it was a *second owner* — `AGENT_SPECS`
naming vendor tools directly instead of going through `hook_core`'s vocabulary. A literal vendor
tool name in generator code, outside the inventory data, is a static failure, the way C51 rejects
a local field mapping in an adopter.

**Seeded violation.** A map emitting `Grep` against a 2.1.221 inventory fails at `sync` and
`sync --check` — the regression is today's live defect, so it must be observed red before green,
and `routing.py:364`/`:470`/`:503` are therefore **not** repaired ahead of C46 (F9's rule for
C54). A capability with no vendor name must produce the shell name **plus** a warn finding naming
the widened boundary; the same degrade **without** the finding fails the test — the silent
degrade is the seed, because tolerance that says nothing is indistinguishable from a rule that
was never there. An inventory entry with no version stamp fails. A detected version outside the
inventory warns and stamps the banner; generating with no stamp fails. Restoring
`tools="Read, Grep, Glob, Bash"` into `routing.py` fails the second-owner check.

**Out of scope, already decided elsewhere.** Shipping akmon's own tools over MCP is P4.3, gated
behind A15/C42 by ADR 0010; the agent-name half is closed by ADR 0011.

## 9. Execution ledger (P1.5 → C58)

**Scope (owner-locked as register fork F10): dispatch-only.** The completion half —
which event marks a dispatch finished, what a completion line contains, and what key correlates
it back to its dispatch — is unknown on both vendors today, so it leaves this lock and becomes
its own probe, [N4](../TASKS.md). Locking a ledger whose second half is guessed is the failure
class this stage exists to remove; a shape narrowed to what is measurable can be extended by
evidence, while a shape locked on a guess has to be *unlocked* first.

**The drawback, stated because it is real:** a dispatch-only ledger cannot answer "what did I
send that never came back", which is a large part of what "after compaction, trust the ledger"
is supposed to buy. Stage 1 therefore ships the smaller promise and says so, rather than writing
a completion column that no signal fills.

**Decision.** **One ledger, machine-written.** Promote the `delegation-log.py` TSV out of
`.claude/` to a neutral `_aitna/` path (vendor-neutral, since the ledger is not Claude's), and
add the clause **"after compaction, trust the ledger and `git log`"** to the orchestration
guardrail. During migration
the tool reads both the old and the new path and writes only the new one; the logs are local and
gitignored, so no migration command is needed.

**Fork — a second, model-written ledger** (the plan's line reads as prose appended per completed
dispatch). Rejected: a ledger the model is asked to maintain degrades exactly when the thing it
guards against happens — under compaction and context pressure. If it is worth having after
compaction, it cannot depend on the compacted party to write it.

**The Codex gap is declared, not papered over.** akmon's delegation-log hook does not fire on
Codex, and whether Codex dispatch is observable at all is unmeasured (N2: the SessionStart
channel is parent-only). That becomes a matrix cell (`delivered: no` for the Codex row) rather
than a claim the ledger is cross-vendor.

**Seeded violation.** A dispatch with no ledger line fails the hook's test; the guardrail clause
is covered by the §3 canary once its enforcer exists.

## 10. `akmon status` (P1.4 → C59)

**Decision.** Read-only aggregation of checks that **already exist** — verify findings, `sync
--check` drift, D2 pending count, caps headroom — rendered through the P1.6 envelope. No new
check, no mutation, no new data source. Sequenced last so it reports a finished vocabulary.
Per owner choice F2, C59 adds the public JSON rendering by composing C51's already-pinned
serializer; it does not define a second Finding schema. The public JSON framing and option name
remain a later `akmon status` fork; text and JSON must contain the same ordered findings and keep
the same exit/strict semantics.

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

## Acceptance

- every shape above ships with a test that **fails on a seeded violation** and passes on the
  repaired tree — the yardstick from the Frame, checked per task, not at the end. **No exemption
  class exists** (F11): a shape that adds no check of its own is seeded against its *fidelity*
  to the sources it composes;
- `meta/tests` and `ruff` clean; `python3 meta/self_ci.py` exit 0; `bin/verify.py --strict`
  clean against the consumer fixture;
- three shapes are accepted against the live tree rather than a fixture, each observed red before
  green: P1.3's check fails on today's version/changelog pair before the repair and passes after;
  C57's fails on the current checkmark matrix and on `README.md:200`'s unqualified enforcement
  claim; C46's fails on `routing.py`'s `Grep`/`Glob` declaration. None of the three is repaired
  ahead of its own task, because a check that never met the defect proves only that it runs;
- the caps checks report the measured numbers, so a later reduction (C60) can be verified
  against the same counter;
- README, `hooks/README.md`, `CAPABILITIES.md` and CHANGELOG agree with the code that shipped.

## Not in this proposed lock

Doc gardening (dead links, staleness); matrix as data (A16/C44); MCP transport (P4.3);
mutable status levels (D1); Codex dispatch observability (N1); the caps *reduction* (C60, which
runs after C56 lands — the edge is kept here because C60 is no longer a row in the order table).
