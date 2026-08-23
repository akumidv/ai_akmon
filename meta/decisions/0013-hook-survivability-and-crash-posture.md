# 0013 — Hook survivability: crash-open posture, measured timeouts, bounded input envelope

- **Status:** Accepted — the stable protocol was owner-verified at **D2-20** and landed at
  `e89f3fe`. Concrete literals remain gated by **D2-23**, which stays Pending and blocks only
  [C52](../TASKS.md).
- **Owner:** akuminov@gmail.com
- **References:** [design lock `stage1-hardening-contracts` §2, §7](../design/stage1-hardening-contracts.md)
  (full contracts and the F3–F6 rationale) ·
  [ADR 0012](0012-stage1-contracts-and-vocabulary.md) (the stable half — findings envelope and
  policy-ID join) · [codex-runtime-contract](../design/codex-runtime-contract.md) ·
  [ADR 0010](0010-alternatives-adoption-a11-verdicts.md) ·
  [N2 findings](../reviews/alternatives/n2-stage0-probes-inventory-20260807.md) ·
  carriers [C52](../TASKS.md), [C57](../TASKS.md), N1/F4, N5/F6 and N6/F5 ·
  ledger rows D2-20, D2-23.

## Context

akmon's hooks are advisory processes the harness spawns: **nine spawned entry points** — the eight
generated Claude entries (`git-commit-guard`, `role-on-code`, `analysis-guard`, `d2-ledger-reminder`,
`delegation-log`, `delegation-nudge`, `session-start-agent`, `model-routing`) and the single Codex
entry `codex-hook.py`, which carries its route as an argument. The adapters and `hook_core` are
imported, never spawned.

Three properties have no single contract today, and each fails quietly.

**Crash posture is declared nowhere and implemented unevenly.** Five of the nine spawned entries
wrap the whole of `main()` in `except Exception`, print a diagnostic and return 0 —
`d2-ledger-reminder`, `delegation-log`, `delegation-nudge`, `session-start-agent`, `model-routing`.
Four do not: `role-on-code`, `analysis-guard`, the single Codex entry `codex-hook.py`, and
**`git-commit-guard`**, which is the deny-class hook where the difference between "crashes open"
and "crashes closed" is the difference between a missed warning and a repository where no commit
can be made. So what a consumer sees when an akmon hook raises depends on which hook it was.

**The five that exist are not the contract below**, which is why C52 *changes* five entries and
adds four rather than adding nine. They print `{type(exc).__name__}: {exc}` — the exception
*message*, which routinely carries a path, a key or a payload fragment, and the diagnostic rule
below forbids exactly that. They also catch `Exception`, so a `SystemExit` — what `argparse`
raises on a bad argument in the Codex entry — passes straight through. A guard that exists and
discloses is the fail-quiet form of the same defect, so C52's seeded test must be observed red on
today's five as well as on the missing four (the red-before-green rule this stage applies
everywhere else).

**Timeouts are absent on one vendor and unmeasured on the other.** Generated Claude wiring emits no
`timeout` key; whether Codex accepts one at all — and whether an accepted field actually terminates
a hung hook — has never been probed. A number written from intuition would be indistinguishable
from a measured one once it is in the tree.

**Valid inputs are unbounded.** Transcripts, ledgers, agent rosters, glob configurations and patch
path counts all grow with the consumer, and every one is read whole. Without bounds there is no
worst case, so there is no honest budget to time against — and an oversize input degrades into
whatever the reader happens to do, which is the silence stage 1 exists to remove.

**Why this is a separate ADR from [0012](0012-stage1-contracts-and-vocabulary.md)**: register fork
F12, whose rationale is stated once, in that ADR's Context, and is not repeated here.

## Decision

### F3 — crash-open now, with the deny-class fail-closed move gated behind measurement

C52 gives every spawned entry a **top-level exception guard**: any unexpected wrapper, adapter or
handler exception prints the exception class and the hook name to stderr and **exits 0** — including
exceptions in deny-class hooks. A healthy handler's *explicit* deny continues to use the vendor's
deny route: crash posture and decision enforcement are separate claims.

The capability record must therefore carry two independent facts — **"normal-path effect: deny
observed on route R when the hook completes"** and **"crash posture: fail-open"** — and must never
imply that a deny survives an akmon crash, or collapse them into bare `enforced` or an unqualified
checkmark.

Moving any deny-class hook to fail-closed is outside C52 and requires a separately owner-verified
change whose gate is: (1) an N1 live probe of the exact vendor route and payload, including the
crash/nonzero-exit case; (2) a regression test pinned to that payload and observed behavior; and
(3) a documented owner-controlled recovery/bypass, tested without hand-editing generated files.

**The adapters get no guard of their own.** They have no top level; an exception inside
`claude_adapter.load_payload` propagates into the wrapper's `main()` and is caught there. They are
covered *by* the guard, not *with* it — which is why the adapter modules are also not timeout
scopes under F5. That coverage carries a precondition, so it is a contract and not an observation:
**an adapter assembles its whole output and writes it in one operation**, so the guard can only
ever fire before that write. Without it, a crash mid-render leaves truncated JSON on stdout and the
guard still exits 0.

### F4 — the Codex timeout field is probe-gated, and `unmeasured` is not a terminal result

Terminal N1 evidence is a prerequisite to C52 **as a whole**; C52 is not partially runnable before
it. The evidence artifact records the exact Codex build/version, invocation mode, configuration
source, event, matcher, hook entry, tested literal and units. Each entry scope C52 would modify is
probed separately with a controlled slow hook, a no-timeout control, before/after markers, and an
expiry run, recording elapsed cutoff/tolerance, termination exit or signal, captured stdout/stderr,
and whether the tool call proceeds or blocks.

**`Supported`** means the accepted field actually terminates the slow fixture within the measured
tolerance; parse acceptance alone is insufficient. **`Unsupported`** requires observed rejection or
an accepted-but-ignored field. If supported, C52 emits the exact measured key/value/units only on
the probed entry scopes plus an exact generated-shape regression; if unsupported, it emits no field
on Codex routes and adds a negative regression. Claims stamp the probed version; later versions
inherit neither claim and trigger a re-probe.

Timeout termination is an **external host outcome**: it inherits neither F3's crash-open label nor
its loud-diagnostic requirement.

### F5 — budgets are derived from measurement, by hook class

N6 inventories every generated Claude entry and every Codex entry scope F4 found supported. The
initial class table follows **dominant workload, not vendor or filename**: payload/marker;
project/config scan; git subprocess; transcript/routing I/O. Every generated command entry maps to
exactly one class; entries share a class only where their supported work envelope and measured
runtime profile are equivalent.

After F6 bounds the inputs, each class gets a largest-supported fixture corpus, repeated
actual-process runs, and the machine-reproducible formula
`ceil_to_vendor_unit(max_observed_supported × factor)` with explicit factor, rounding, minimum
floor and proposed production literal. The git-subprocess class must account for the existing
5-second internal git timeout, or change that inner bound in the same design: an outer timeout may
not pre-empt the healthy fallback by accident.

The apparent cycle is broken by sequence: F4 proves mechanics with disposable scratch wiring and a
sentinel literal; F6 bounds supported inputs; N6 measures entry points directly with no host
timeout; F5 derives the literals; scratch wiring live-verifies them; the owner verifies the
class/literal table; only then may C52 implement it. **The sentinel is not the production budget.**
That live validation covers **two** things, not one: individual entry expiry, and the aggregate
latency and behavior where a single event schedules a group of hook processes — a per-entry budget
that is correct alone can still be wrong in a group, and the group is what a consumer actually
experiences.

Ordinary CI does not assert wall-clock timing. Durable regressions prove exhaustive
entry-to-class mapping, exact owner-verified literals and units, omission on unsupported or
unprobed Codex scopes, and failure when a new entry has no class. Timings stay versioned evidence
from a reproducible harness; after C52 that corpus is rerun, and exceeding a literal **re-blocks
the task** rather than silently raising the budget. `hooks/README.md` records the table, the
evidence environment and scope, and states that the budget is an operational bound, not a
cross-machine latency SLA.

### F6 — a bounded synchronous fast path, with fail-visible oversize degradation

N5 first inventories and measures every valid input axis that can grow with a consumer: raw stdin
bytes before decode plus JSON depth/item/string bounds; command and description bytes; extracted
patch path count and per-path bytes/depth; transcript total/line bytes and matching-record count;
D2 ledger bytes/rows; D2 config bytes, glob count/length/depth and `**` complexity; registry,
overlay, local config
and settings bytes/depth/items; brief count/text and generated-output bytes; agent roster
count/name/output bytes; generated-agent directory count, per-file/total bytes and rebind/prune
population; and akmon-owned marker/counter bytes. The evidence proposes a numeric cap and unit for
every applicable generated command entry, and each cap, entry mapping and combined fixture corpus
requires explicit owner verification.

At runtime: raw stdin is read as **cap+1** before decode; files are preflighted and bounded-read to
survive growth races; directories and lists enumerate at most cap+1 and discard the whole
collection on overflow; structural JSON caps are validated immediately after the bounded parse and
**before** handler dispatch. Every applicable source is preflighted before the entry's first
stdout, marker, log, config write, rebind, prune or deletion — so a later oversized source leaves
none of the earlier side effects behind and invokes no handler with a prefix.

An over-cap entry writes **exactly one** stable stderr diagnostic per invocation, naming only hook,
input dimension, cap and fail-open remediation, then exits 0 with empty stdout: no `ask`, `deny`,
context, system message, malformed or partial JSON, and no throttled-away later warning. Payload
values, paths, content, commands, session ids and secrets are never included. This is a **handled
oversize degradation**, not an exception crash and not a host timeout, so the capability record
states it as its own axis — `input envelope: exceeded → fail-open` — and it gets its own stable
diagnostic code, never the existing no-path one. Other command entries launched for the same event
keep independent envelopes and may still complete.

**Caps are compatibility boundaries, not tuning constants: implementation cannot raise a cap to
make a test pass.** Demand from a larger real consumer starts separate architecture and evidence
work to stream, index, cache or otherwise bound the expensive source. A numeric increase alone is
insufficient — the new design must bound time and memory, prove equivalence to full processing,
make index/cache updates atomic with freshness, invalidation and corruption recovery, preserve safe
fail-open on stale state, rerun live boundary probes, and rederive the F5 budgets.

### How these facts are recorded

A capability records **independent axes** rather than one overloaded grade: `documented`,
`delivered`, the exact vendor/version/event/matcher route, the observed normal-path effect
(`none / advisory / ask / deny`), crash posture (`fail-open / fail-closed / unmeasured`), and
`evidence` — the probe or report the claim comes from. Bare `enforced` and checkmarks are invalid.
A value other than `unmeasured` requires a non-empty `evidence`, and `unmeasured` requires it
empty, so the measured and the unmeasured states stay distinguishable by a check rather than by a
reader's judgement.

Because F6 allows a padded payload to bypass a deny, a normal-path claim is always scoped as
**"deny observed on exact route within the supported input envelope"**. C57 owns the check that
rejects a bare claim, an enforcement-like entry missing its route or crash posture, a measured
claim with no evidence, and an `unmeasured` cell that carries one — the rule above is two-way, and
a check reading a single direction lets a cell be both at once.

### The D2-20 / D2-23 boundary

**D2-20** owns the protocol above: what counts as terminal timeout evidence, how budgets are
derived, and the bounded fast-path and oversize semantics — including the explicit owner
verification of the availability trade F6 accepts. **D2-23** owns what the measurements produce:
concrete F4 support results per Codex entry, F6 caps, units and entry mappings, and F5 timings,
formulas and literals. D2-23 blocks C52 alone, so missing runtime numbers cannot hold C51 or C57
behind an unrelated measurement campaign. Measurements populate the protocol; they reopen D2-20
only if they force a change to it.

### F13 verification carriers

The independently violable rules above keep distinct checker/seed/failure triples. The crash
matrix covers all nine spawned entries and injects at every applicable wrapper, adapter and handler
layer; a Codex-boundary `SystemExit` is separate from ordinary handler exceptions. Every crash must exit 0,
emit exactly one safe class-and-hook diagnostic and no blocking or partial stdout, while the paired
healthy deny remains a deny. A mid-render failure separately proves the adapters' single-write
property, and a BOM-prefixed valid payload must reach its handler.

Generated Claude wiring with no `timeout` fails `sync --check`; disagreement between the generated
entry→class→literal mapping and `hooks/README.md`, including deletion of the contract or omission
of its table, evidence environment/scope or operational-bound-not-SLA statement, fails `self_ci`.
Literal correctness and Codex presence remain gated by D2-23. A relational check
also rejects an outer git-class timeout that can pre-empt the healthy existing 5-second fallback;
ordinary CI does not measure elapsed time.

The F6 boundary corpus covers cap−1/cap/cap+1 for every declared source, but its readers are
instrumented too: stdin/files fail on a request beyond cap+1 or decode after overflow; collections
fail on a cap+2 request and must discard the full collection. A preflight seam that reports below
cap and then returns above-cap content seeds the growth race. Handler spies and side-effect
sentinels prove that every overflow is rejected before dispatch or any stdout, marker, log, config,
artifact, rebind, prune or deletion. Adding a synchronous input axis or generated command entry
without an envelope declaration fails the C52 contract suite.

Oversize diagnostics have three independent oracles: their stable code differs from the existing
no-path code; multiple oversized sources still produce exactly one line; and repeated invocations
each produce a line rather than sharing a throttle. The exact line admits only hook, dimension, cap
and remediation, with sentinel path, payload, command, session and secret values forbidden. At the
generated event boundary an oversized entry and a healthy sibling prove independent envelopes: the
healthy sibling must still complete.

Two residuals are explicitly process-owned. C52 pins an owner-verified cap, but a checker cannot
prove that a later increase opened the required architecture/evidence gate; review owns that
process. D2-23's reproducible performance corpus owns re-blocking on a measured regression because
ordinary CI deliberately carries no wall-clock assertion. The residual cost is that bypassing
either process is review-visible rather than mechanically impossible.

## Consequences

- **One missed deny on an akmon crash is accepted**, in exchange for not letting an unmeasured hook
  failure brick every commit in a consumer repository. The trade is stated in the capability record
  rather than left for a reader to discover.
- **A deny-class bypass by padding an otherwise matching payload past a supported cap is
  deliberately allowed.** This is the sharpest cost of the whole ADR and is why D2-20 requires the
  owner to verify the availability trade explicitly rather than as a side effect.
- **C52 is all-or-nothing and blocked behind D2-23.** No partial implementation, no sentinel
  literal shipped as a budget, no field emitted on an unprobed Codex scope. The rest of stage 1
  proceeds without waiting on the measurement campaign.
- **The `timeout` rule is split rather than waived** — a generated Claude entry emitted
  **without** a `timeout` key fails `sync --check` today, while the literal's correctness waits on
  D2-23 and is pinned there by the entry→class→literal table. This is the worked example of
  [0012](0012-stage1-contracts-and-vocabulary.md)'s seeding rule applied to a rule that needs
  evidence it does not have.
- **The adapters' single-write property becomes a tested contract, not an assumption.** A seed
  places the failure mid-render and asserts that the wrapper's stdout is either empty or a complete
  document, never a prefix — because a guard cannot un-write truncated stdout.
- **A performance regression re-blocks C52** instead of quietly raising a literal, so the budget
  keeps meaning what it meant when the owner verified it.
- **This ADR is the one expected to move.** N1/F4 results amend support verdicts, N5/F6 results
  amend caps, and N6/F5 results amend literals.

## Alternatives

- **Fail-closed now for deny-class hooks** — rejected until measured. It sounds stricter and is,
  today, unverifiable: nothing has probed what the vendor does with a nonzero exit on the exact
  route, so the strictness would be asserted rather than observed, and its failure mode is a
  consumer repository that cannot commit.
- **Per-function `try/except` inside the adapters** — rejected. That is not a guard but swallowing:
  the function returns something plausible and the wrapper never learns that its decision ran on
  empty data. A single top-level guard makes the failure visible exactly once.
- **Accept parse acceptance as proof of Codex timeout support** — rejected. An accepted-but-ignored
  field is the worst of the three states, because it produces a generated artifact that looks
  bounded and is not; `Supported` therefore requires observed termination of a slow fixture.
- **Write a plausible timeout literal now and refine later** — rejected. Once a number is in the
  tree nothing distinguishes it from a measured one, and the refinement never has a trigger.
- **Truncate-then-parse an oversize payload**, or **leave valid inputs unbounded** — both rejected.
  Truncation invents a payload the consumer never sent and then acts on it; unbounded inputs leave
  no worst case, so no honest budget can be derived and the degradation stays whatever the reader
  happens to do.
- **Treat a raised cap as a tuning knob** — rejected, and stated as a prohibition because it is the
  natural thing to do under a failing test. Raising the envelope is new design work with new
  measurements and its own owner verification.
