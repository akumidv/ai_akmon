# N5 — F6 input envelope, measurement rounds 1–3

> **What this is.** The first evidence round for owner choice **F6/C**
> ([stage-1 lock §2](../design/stage1-hardening-contracts.md)), owned by
> [N5](../TASKS.md) and gating [D2-23](../D2_LEDGER.md), which in turn gates only C52.
> Rounds 1–2 answer most of F6's four questions — *which axes exist*, *which entries consume them*,
> *what a real consumer measures today*, and *what the combined supported corpus is*. Round 1
> (§1–§7) mapped the initial axes and measured the file-side ones; round 2 (§8) measured the
> payload-side ones from recorded real tool calls and composed a provisional per-entry corpus. It
> does **not** derive timeout budgets: that is F5 / [N6](../TASKS.md), and it cannot start until the
> caps here are owner-verified, because before the bounds exist timings are a stress corpus rather
> than a worst case.
>
> **Status: proposed, not verified; C66(b) required.** Every cap below is a proposal. F6 requires explicit owner
> verification of each cap, each entry mapping and the combined supported corpus; until that
> happens D2-23 stays pending and C52 stays blocked. Rounds 1–3 are complete, but the axis-7
> boundary fixture refuted the proposed glob envelope. The owner chose C66 option (b): call-local
> matcher memoization, followed by the exact boundary rerun and explicit D2-23 owner verification.
> The two earlier forks — the
> transcript cap and the `sync` boundary — are **decided** (§6); that is not the same as the cap
> table being verified.

## Method and scope

Measured read-only on the attached consumer **alphavar** (`mount = "package"`,
`akmon_version = 0.4.0.dev0`) plus this machine's live Claude transcripts, and — for the one axis
alphavar has no sample of — akmon's own D2 ledger. No wiring was installed and nothing was written.
The vendor-harness half of the evidence packet (F4 Codex timeout mechanics) is N1's and is not
touched here; F4 and F6 do not depend on each other, so this round runs first.

Nothing here is a timing budget. One indicative scan cost appears below because a cap is
meaningless without knowing what processing at the cap costs, and it is labelled where it appears.

## 1. The entry population

Enumerated from the generators rather than from memory (`bin/sync.py::_claude_hooks` /
`_codex_hooks`):

| # | event | matcher | entry |
|---|---|---|---|
| 1 | PreToolUse | `Bash` | `git-commit-guard.py` |
| 2 | PreToolUse | `Edit\|Write\|MultiEdit` | `role-on-code.py` |
| 3 | PreToolUse | `Edit\|Write\|MultiEdit` | `analysis-guard.py` |
| 4 | PreToolUse | `Edit\|Write\|MultiEdit` | `d2-ledger-reminder.py` |
| 5 | PreToolUse | `Task\|Agent` | `delegation-log.py` |
| 6 | PreToolUse | `Bash\|Edit\|Write\|MultiEdit\|Task\|Agent\|Read\|Grep\|Glob` | `delegation-nudge.py` |
| 7 | SessionStart | — | `session-start-agent.py` |
| 8 | SessionStart | — | `model-routing.py` |
| 9 | UserPromptSubmit | — | `model-routing.py` |
| 10–12 | PreToolUse | `Bash\|apply_patch` | `codex-hook.py` × `role-on-code` / `analysis-guard` / `d2-ledger-reminder` |
| 13 | SessionStart | `startup\|resume\|clear\|compact` | `codex-hook.py session-start` |

**Nine Claude command entries across eight distinct scripts**: `model-routing.py` is wired twice,
to `SessionStart` and to `UserPromptSubmit`. F5 maps *entries*, not scripts, so its table has nine
Claude rows and the two `model-routing` rows may end up in the same class but are two rows. Four
Codex entry scopes, all reached through the single `codex-hook.py` process.

## 2. Axis → entry map

Every read reachable from an entry, with the site that performs it.

| # | axis | consuming entries | read site |
|---|---|---|---|
| 1 | raw stdin bytes before decode | all 9 Claude, all 4 Codex | `hooks/claude_adapter.py:29` (`json.load(sys.stdin)`), `hooks/codex_adapter.py:133` (`sys.stdin.read()`) |
| 2 | JSON depth / node count / string bytes | same as 1 | same as 1 — parsed with no structural bound |
| 3 | command and description bytes | 1 (command), 5, 6 (description/tool), 2–4 and 10–12 (`tool_input` paths) | payload fields after decode |
| 4 | patch path count and per-path bytes | 10–12 only | `hooks/codex_adapter.py::file_paths` / `_paths_by_source` |
| 5 | transcript total bytes, line bytes, matching records | 5, 8, 9 | `routing.py:745` `active_role`, `routing.py:828` `_last_main_turn` |
| 6 | D2 ledger bytes / rows | 8 (`model-routing.py` on SessionStart) | `hooks/model-routing.py:141`–`:143` → `hooks/hook_core.py:679` |
| 7 | D2 config bytes, glob count/length/depth, `**` complexity | 4, 8 (SessionStart only), 12 | `hooks/hook_core.py:557`; `hooks/model-routing.py:141` |
| 8 | registry / overlay / local config / settings bytes, depth, items | 5, 8, 9 | `routing.py:65` (+ overlay `:69`), `hooks/model-routing.py:57` (`.claude/settings.local.json` then `settings.json`), `:71` (local config) |
| 9 | briefs and generated agent-file output | 8, 9 | `routing.py::resolve_briefs` / `agent_file_content` — a **derived** axis: briefs live inside the registry (axis 8) and the output is written, not read |
| 10 | agent roster count and name bytes | 7, 13 | `hooks/hook_core.py:327` `agent_names` — two directories (`<aitna>/agents`, `<root>/agents`) |
| 11 | generated-agent directory count, per-file and total bytes, rebind/prune population | 8, 9 | `routing.py:1022` (`agents_dir.glob("*.md")`), `:1048` |
| 12 | marker / counter bytes | 2, 3, 4, 6, 8, 9 | `hooks/hook_core.py:804` and the `tempfile.gettempdir()` markers at `:139`, `:480`, `:523`, `:625`, `:782`–`:784` |

Two mapping facts worth stating because they are easy to get wrong:

- **The transcript is read by three entries, not two.** `delegation-log.py:90` calls `active_role`
  on every `Task|Agent` dispatch, in addition to `model-routing`'s two wirings. The axis therefore
  costs on delegation as well as on every user turn.
- **Axis 10 reads names, not content.** `agent_names` only tests that `README.md` exists; the
  README bytes are never read by a hook. The roster axis is count plus name length.
- **The D2 ledger belongs to SessionStart model routing, not the reminder.** The reminder reads
  only the D2 config globs before deciding whether to speak; the SessionStart branch calls
  `d2_status_counts` and reads the ledger. UserPromptSubmit returns before that branch.

## 3. Measured — round 1

**Axis 5, transcript** (live Claude transcripts on this machine):

| sample | bytes | records | max line bytes | `agent:` lines | `"model"` lines |
|---|---:|---:|---:|---:|---:|
| largest (akmon project) | 19,326,201 | 6,422 | 113,552 | 83 | 2,311 |
| second (akmon project) | 6,410,512 | — | — | — | — |
| alphavar session | 51,355 | — | — | — | — |

**Axes 6–12** (alphavar unless noted):

| axis | measurement | value |
|---|---|---:|
| 6 | D2 ledger — *akmon's own; alphavar has no ledger* | 49,048 bytes · 24 rows · longest row 6,515 bytes |
| 7 | `_aitna/.akmon.toml` | 813 bytes · 4 globs · longest 22 chars · depth 4 · max 2 × `**` |
| 8 | `registry.json` | 2,678 bytes · depth 4 · 116 nodes |
| 8 | `_aitna/model-routing.json` (local config) | 1,289 bytes · depth 3 · 6 nodes |
| 8 | `.claude/settings.json` | 1,968 bytes · depth 7 · 50 nodes |
| 8 | `.claude/settings.local.json` | 263 bytes |
| — | `.codex/hooks.json` — generated, read by `sync --check` only, **not an axis** | 1,201 bytes · depth 7 · 26 nodes |
| 10 | dev roster `_aitna/agents` | 3 agents · longest name 9 chars |
| 10 | desk roster `agents` | 1 agent · longest name 15 chars |
| 11 | `.claude/agents/*.md` | 6 files · 10,977 bytes total · largest 2,413 bytes |
| 12 | `akmon-*` markers/counters | 4 bytes each |
| 3 | longest recorded dispatch description | 93 bytes (41 records in `.claude/model-routing.log`) |
| 1 (proxy) | largest `.py` in the consumer — a plausible `Write` payload | 50,684 bytes |

**Indicative scan cost — context for the cap, not an F5 budget.** Warm, n=5, single machine, no
environment capture; F5 owns cold/warm separation, repetition and the formula.

| transcript | `active_role` | `_last_main_turn` |
|---|---:|---:|
| 19.3 MB / 6,422 records | 134–169 ms | 210–273 ms |
| 6.4 MB | 31–37 ms | 69–77 ms |
| 51 KB (alphavar) | 0.5 ms | 0.6–0.7 ms |

`model-routing.py` calls both per invocation: **≈ 360 ms warm on the 19.3 MB sample, ≈ 1 ms on
alphavar's**. The first (cold) call measured 184 ms against the 6.4 MB file where the warm median
is 34 ms, so page-cache state moves this by roughly 5×.

## 4. Proposed caps

Method (owner-confirmed after rounds 1–2): one multiplier does not describe axes with different
cost shapes. **Growth axes** target at least one order of magnitude of headroom where that cost is
affordable. **Structural/complexity axes** use an independently measured boundary fixture and
runtime cost, not an observed-max multiplier. **Expensive coupled axes** use an explicit owner-cost
choice, as the transcript does. The final table records the derivation class, observed maximum,
actual ratio, cap, unit and boundary fixture. Caps are inclusive. Units are **decimal bytes** where
the axis is a byte count of text and **counts** otherwise, matching F18's unit choice for the caps
report. The strict universal ≥10× rule was rejected because raising a fail-open envelope merely to
fit that sentence increases timeout cost without evidence.

| axis | measured max | proposed cap | unit |
|---|---:|---:|---|
| 1 raw stdin before decode | 45,167 (§8) | **4,000,000** | bytes |
| 2 JSON nesting depth | 7 (payload 6, §8) | **32** | levels |
| 2 JSON node count | 116 (payload 19, §8) | **100,000** | nodes |
| 2 JSON single string bytes | 113,552 (payload 30,670, §8) | **1,000,000** | bytes |
| 3 command bytes | 45,167 (§8) | **500,000** | bytes — *raised from 100,000 by round 2* |
| 3 description bytes | 73 (§8; 93 was a whole log record) | **8,000** | bytes |
| 4 patch path count | **51** (§9) | **500** | paths |
| 4 per-path bytes | **143** (§9) | **4,000** | bytes |
| 4 per-path depth | **11** (§9) | **64** | segments |
| 5 transcript total bytes | 19,326,201 | **64,000,000** | bytes |
| 5 transcript line bytes | 113,552 | **1,000,000** | bytes |
| 5 transcript matching records | 2,311 | **100,000** | records |
| 6 D2 ledger bytes | 49,048 | **4,000,000** | bytes |
| 6 D2 ledger rows | 24 | **5,000** | rows |
| 7 D2 config bytes | 813 | **1,000,000** | bytes |
| 7 glob count | 4 | **200** | globs |
| 7 glob length | 22 | **500** | chars |
| 7 glob path depth | 4 | **32** | segments |
| 7 `**` per glob | 2 | **4** | occurrences |
| 8 registry / overlay / local config / settings bytes (each) | 2,678 | **1,000,000** | bytes |
| 8 config nesting depth | 7 | **32** | levels |
| 8 config node count | 116 | **100,000** | nodes |
| 10 agent roster count (per directory) | 3 | **200** | agents |
| 10 agent name bytes | 15 | **200** | bytes |
| 11 generated-agent file count | 6 | **500** | files |
| 11 generated-agent per-file bytes | 2,413 | **200,000** | bytes |
| 11 generated-agent total bytes | 10,977 | **20,000,000** | bytes |
| 12 marker / counter bytes | 4 | **4,000** | bytes |

Axis 9 was incomplete in rounds 1–2 and is **closed in §10**, together with the axis-10 rendered
output bound, the measured peak-resident figure, and the structural boundary fixtures. One of those
fixtures did not pass: see §10's axis-7 finding, which is the reason this table is **not yet ready
for owner verification** even though every cell is now filled.

## 5. Not measured in this round

- ~~**Axis 1 and 3 have no live sample.**~~ **Closed by round 2 (§8)**, and by a cheaper route than
  the disposable wrapper this section originally proposed: the harness transcripts already record
  every tool call's `tool_input` verbatim, so 1,871 real Claude calls and 6,048 real Codex calls
  could be measured read-only, with no wiring installed anywhere. The round-1 text is kept rather
  than deleted because the method it proposed was the more expensive one and the record of that
  matters more than a tidy page.
- ~~**Axis 4 consumes N1 live evidence.**~~ **Closed in §9** by N1's `apply_patch` payload probe:
  the rename form was captured live, and the axis is now measured from 345 recorded real patches
  rather than proposed. The dependency this bullet described was real and is discharged.
- **`.codex/hooks.json` is generated and compared, never parsed by a hook** — no entry reads it,
  so it carries no runtime envelope; `sync --check` is its only reader. `.claude/settings.json`
  *is* different: `hooks/model-routing.py:51`–`:57` parses it, and `settings.local.json` before it,
  so both are live axis-8 inputs. `settings.local.json` measured 263 bytes in alphavar.
- **Round 1 measured one consumer.** alphavar is small on every axis except the transcript. A cap
  set from one consumer is a starting envelope, not a population statistic. Round 2 widens the
  payload axes to every recorded session on this machine, but the file-side axes (5–12) still rest
  on the single alphavar sample.

## 6. Owner decisions

Both questions this round raised are decided. The reasoning is kept in full rather than compressed
to the verdict, because the cost each choice accepts is what D2-23 verifies.

**The transcript axis does not have a safe cap, and that is the finding of this round.**

Every other axis in alphavar sits three or more orders of magnitude below its proposed cap. The
transcript sits at **19.3 MB today, on a real session, in the akmon project itself** — 380× the
largest other input — and is scanned in full, twice per `model-routing` invocation, on every user
turn and on every delegation.

Three answers, none free:

- **(a) Cap below today's reality** — e.g. 8,000,000 bytes. Honest about cost, but the 19.3 MB
  session immediately degrades: over-cap means fail-open with one diagnostic, so role detection,
  model rebinding and the delegation role-matrix warning all stop for that session. akmon would
  ship a cap its own development sessions exceed.
- **(b) Cap above today's reality** — e.g. 64,000,000 bytes. Nothing breaks now, and F5 must then
  budget a class whose worst supported case is roughly **1.2 s of scan per turn**, which is a
  timeout literal large enough that a genuinely hung hook is indistinguishable from a healthy one.
- **(c) Bound the read instead of the file** — read the transcript tail-first and stop after a
  bounded number of records, since both scanners want the *last* matching entry. This makes the
  axis cheap regardless of file size. It is the right answer and it is **not F6 work**: the lock
  states that streaming or indexing an expensive source is separate architecture and evidence
  work, which must prove equivalence to full processing and rederive the F5 budgets.

**Owner choice: (b).** The transcript total-bytes cap is **64,000,000 bytes**, entered in the table
above. Nothing that works today silently stops working, and the cost is accepted rather than
hidden: F5 must budget a transcript/routing class whose worst supported case is roughly **1.2 s of
scan per turn, warm** — and the cold factor measured here is about 5×, so the honest planning figure
is larger still. That is a timeout literal big enough that a genuinely hung hook and a healthy one
at the cap are hard to tell apart, and N6 has to say so in the class table rather than round the
problem away.

*(a) was rejected rather than left open:* shipping a cap that akmon's own development sessions
already exceed teaches exactly the lesson F18 refused to teach — that the first response to a cap
is a waiver.

*(c) is not dropped, it is relocated.* Reading the transcript tail-first and stopping after a
bounded number of records is the answer that makes this axis cheap regardless of file size, and it
stays outside F6 by the lock's own rule: streaming or indexing an expensive source is separate
architecture and evidence work that must bound time and memory, prove equivalence to full
processing, and rederive the F5 budgets. It carries its own id **[A19](../TASKS.md)** so that the
cost (b) accepts has an owner instead of living in this paragraph.

**Owner choice: `sync` is not covered.** F6 is the hook entry envelope only. `sync --check` reads
the same config and settings files with the same absence of bounds, but it is not a spawned hook
entry, is not on the crash-posture path, and its failure is a visible non-zero exit rather than a
silent degradation. Round 1's assumption stands as the decision. The cost, stated because it is
real: the unbounded reads in `sync` remain unbounded and no axis in this document covers them, so a
future report of a `sync` hang on a large consumer has no envelope to point at.

## 7. Incidental

175 `akmon-*` marker and counter files were present in this machine's tempdir, one per session id
and never pruned. Each is 4 bytes, so it is not an input-envelope problem, but nothing removes
them. Not in scope for F6; recorded here because the sweep found it.

## 8. Round 2 — the payload axes, and the combined supported corpus

### Method, and its limitation

Round 1 proposed a disposable logging wrapper in alphavar to capture real payloads. That turned out
to be unnecessary: **the harness transcripts already record every tool call's `tool_input`
verbatim**, and `tool_input` is the term that dominates a `PreToolUse` payload. So the population
below is real recorded traffic, read-only, with no wiring installed anywhere — **1,871 Claude tool
calls** across every session on this machine, and **6,048 Codex tool calls** across 98 rollouts.

The limitation, stated because it changes what the numbers are worth: this is **reconstruction, not
observation**. The transcript records `tool_input`; the harness wraps it in a fixed envelope
(`session_id`, `transcript_path`, `cwd`, `hook_event_name`, `tool_name`, `permission_mode`), which
is added back here as a flat **320-byte constant**. Any harness-side transformation between the
recorded input and the delivered payload is invisible to this method. The envelope is small and
fixed and the dominant term is measured directly, so the error is bounded and one-directional —
but an entry whose payload is dominated by something the transcript does not record would be
mismeasured, and nothing here would show it.

### Axis 1 — reconstructed payload bytes, Claude

| tool | n | median | p99 | max |
|---|---:|---:|---:|---:|
| `Write` | 54 | 3,151 | 31,456 | **31,456** |
| `Bash` | 1,157 | 536 | 4,913 | 14,062 |
| `Edit` | 418 | 1,307 | 8,572 | 12,822 |
| `Agent` | 8 | 1,113 | 1,800 | 1,800 |
| `Read` | 217 | 408 | 456 | 457 |
| **all tools** | **1,871** | **577** | **10,205** | **31,456** |

### Axis 1/3 — Codex, recorded tool-call input bytes

| tool | n | median | p99 | max |
|---|---:|---:|---:|---:|
| `exec` | 2,408 | 424 | 11,163 | **45,167** |
| `apply_patch` | 345 | 2,507 | 24,567 | 43,790 |
| `send_message` | 242 | 1,067 | 8,727 | 27,159 |
| `exec_command` | 2,193 | 147 | 2,481 | 8,098 |
| `spawn_agent` | 56 | 716 | 4,046 | 4,046 |

**Codex sets the payload maximum, not Claude** — 45,167 bytes against Claude's 31,456. Both routes
matter for the same cap because `codex_adapter` reads its payload from the same unbounded
`sys.stdin.read()`.

### Axis 2 — payload structure

| tool | max depth | max nodes | max single string |
|---|---:|---:|---:|
| `AskUserQuestion` | 6 | 19 | 553 |
| `Write` | 2 | 3 | 30,670 |
| `Bash` | 2 | 4 | 13,438 |
| `Edit` | 2 | 5 | 12,128 |

Real payloads are **flat and small in structure**: depth 6 and 19 nodes at the observed maximum,
against proposed caps of 32 and 100,000. Those caps are independent of the byte cap: many simple
JSON nodes can fit well below 4,000,000 bytes, while deep nesting can fail at a tiny byte size.
Round 3 therefore treated both as structural limits and measured their boundary fixtures rather
than presenting them as observed growth headroom; both passed (§10).

### Axis 3 — the fields akmon's hooks actually read

| field | n | median | p99 | max |
|---|---:|---:|---:|---:|
| `Write.content` | 54 | 2,668 | 30,670 | 30,670 |
| `Bash.command` | 1,157 | 146 | 4,344 | 13,438 |
| `Edit.new_string` | 418 | 580 | 7,843 | 12,128 |
| `Bash.description` | 1,015 | 35 | 67 | **73** |
| `Agent.description` | 8 | 25 | 46 | 46 |

`description` — the field `delegation-log` writes into the dispatch ledger — is **two orders of
magnitude smaller than everything around it**: 73 bytes at the observed maximum. Round 1 recorded 93
from the dispatch log, which was the whole TSV record rather than the field.

### What round 2 changed

One growth cap moved. **Command bytes: 100,000 → 500,000.** Round 1 had no sample and guessed; the measured
maximum is 45,167 (Codex `exec`), which leaves the round-1 proposal only 2.2× of headroom — thinner
than any other axis in the table and thin in the direction that matters, since a heredoc-carrying
shell command is exactly the shape that grows. At 500,000 the axis has the order of magnitude the
rest of the table has. The remaining growth caps did not move in round 2. Round 3 ran the structural
boundary fixtures; JSON passed and the axis-7 glob fixture failed (§10).

### The combined supported fixture corpus — corrected, provisional

The original table conflated two quantities: **unique fixture bytes** (physical input population)
and **processed read bytes** (including repeated passes). It also assigned the D2 ledger to the
reminder instead of SessionStart model routing and combined mutually exclusive model-routing
branches. The owner confirmed that the final table separates both quantities and only composes
reachable branches.

| entry / reachable branch | unique fixture bytes | processed read bytes |
|---|---:|---:|
| `model-routing.py` SessionStart + rebind | **96,008,000** | **161,008,000** |
| `model-routing.py` UserPromptSubmit + rebind | **91,008,000** | **156,008,000** |
| `model-routing.py` SessionStart + no detected model/settings fallback | **78,008,000** | **142,008,000** |
| `delegation-log.py` | **70,000,000** | **70,000,000** |
| `d2-ledger-reminder.py` / codex `d2-ledger-reminder` | **5,004,000** | **5,004,000** |
| `session-start-agent.py` / codex `session-start` | **4,080,000** | **4,080,000** |
| `delegation-nudge.py` | **4,012,000** | **4,012,000** |
| `role-on-code.py`, `analysis-guard.py` (both vendors) | **4,004,000** | **4,004,000** |
| `git-commit-guard.py` | **4,000,000** | **4,000,000** |

These are not timeout literals or memory budgets. `model-routing` scans the transcript twice and
reloads local config after a rebind, which is why processed bytes exceed the unique fixture; N6
measures the actual process on the largest reachable branch rather than materializing duplicate
files. The largest source is read incrementally: the transcript is streamed line by line, so it
contributes at most one capped line (1,000,000 bytes) to resident memory rather than 64,000,000.
The generated agent files are read one at a time. What *is* held whole is the payload
(`json.load(sys.stdin)`, 4,000,000), the D2 ledger (`read_text`, 4,000,000), and the config files
that stay alive for the run — registry plus overlay plus their merge, and the local config. Peak
resident bytes at the combined worst case therefore needs its own round-3 measurement rather than
an estimate inferred from unique or processed bytes.

**The transcript-reading entries dominate everything else.** N6 budgets `model-routing` against
the largest reachable branch and its repeated-read volume, not against the old 93 MB sum or the
64 MB transcript cap alone. `model-routing` is wired to UserPromptSubmit, so that cost is per turn;
`delegation-log` pays its single 64 MB transcript pass on every dispatch.

### Round 3 requirements — completed in §§9–10

Round 3 had to complete three groups before this packet could be offered for owner verification:

1. Measure Codex patch source/destination count, per-path UTF-8 bytes and segment depth across Add,
   Update, Delete and Move-to/rename (§9).
2. Render the maximum brief/generated-agent population, declare brief count/text and pre-write
   per-file/aggregate output caps, and prove the complete render is rejected before any write,
   rebind or prune (§10).
3. Render both roster directories at their count/name bounds and declare an exact UTF-8 output cap
   before stdout (§10).

Round 3 also ran the structural boundary fixtures and measured peak resident use. It completed the
evidence population but found the axis-7 failure assigned to C66. C52 still owns cap−1/cap/cap+1
tests for every axis; whether it materializes the entire unique corpus in one test or proves
composition through preflight ordering remains a C52 test-design choice.


## 9. Axis 4 — measured, and not the shape round 1 assumed

N1's `apply_patch` payload probe (see the
[F4 evidence](n1-f4-codex-timeout-20260825.md)) supplied the live shape, and the recorded Codex
sessions on this machine supplied the population: **345 real `apply_patch` calls**.

| measurement | median | p99 | max |
|---|---:|---:|---:|
| paths per patch | 1 | 16 | **51** |
| bytes per path | 51 | 124 | **143** |
| path depth (segments) | 5 | 11 | **11** |
| whole patch bytes | 2,507 | 24,567 | 43,790 |

Proposed caps, entered in §4: **500** paths, **4,000** bytes per path, **64** segments of depth —
actual headroom of about **9.8×**, **28.0×** and **5.8×**, respectively. This follows the confirmed
mixed derivation method rather than a universal multiplier.

**Axis 4 is derived, not independent, and round 1 had this wrong.** The whole patch arrives as a
single string in `tool_input.command`; there is no structured path list. So the patch's byte size is
already bounded by the axis-3 command cap (500,000), and path count, per-path bytes and depth are
limits on **what the parser will extract from that one string**, applied after the bounded read
rather than as separate input dimensions. The distinction matters for C52: these three are checked
where `_PATCH_PATH_RE` runs, not at the stdin boundary, and a patch that is under the command cap can
still exceed the path count.

The caps are nonetheless reachable and not redundant. At the 500,000-byte command cap a patch could
name on the order of 25,000 paths at the measured median path length, so the 500-path cap binds well
before the byte cap does.

**The rename form is now in evidence** — `*** Update File: <source>` followed by
`*** Move to: <destination>` — and it is what makes the path population larger than the
`Add|Update|Delete File:` lines alone. Across the 345 recorded calls **zero** contained a rename, so
the live probe was the only way to get it. akmon's extractor did not read the destination at all;
that defect was recorded in the F4 evidence and is now **repaired in C67**, so the destination is in
the extracted population this axis counts. The requirement is unchanged: **the cap has to count
destinations too**, or a rename-heavy patch is undercounted by exactly the paths a checker most
wants to see.


## 10. Round 3 — the output bounds, the measured peak, and one cap that does not survive its own fixture

### Axis 9 — briefs and the rendered agent file

The rendered agent file is `fixed body + brief`, and only the brief grows with a consumer
(`routing.py::agent_file_content`). Measured:

| | value |
|---|---:|
| `AGENT_SPECS` (the ceiling on *resolved* briefs) | 6 |
| largest fixed body | 1,514 bytes |
| largest rendered file with no brief | 1,541 bytes |
| alphavar overlay briefs | 4, largest **421** bytes |

The raw overlay map is consumer-written and unbounded **before** validation — `resolve_briefs`
rejects keys that match no agent, but it iterates the whole map to do so — which is why the count
needs its own cap rather than inheriting the six-slot ceiling.

| axis | measured max | proposed cap | unit |
|---|---:|---:|---|
| 9 overlay brief entries (raw, pre-validation) | 4 | **64** | entries |
| 9 per-brief bytes | 421 | **20,000** | bytes |
| 9 rendered agent file, **bounded before write** | 1,541 | **32,000** | bytes |
| 9 rendered agent files, aggregate before write | 6,872 | **200,000** | bytes |

The write bound is deliberately tighter than axis 11's 200,000-byte read bound: akmon controls what
it renders, and the read side must additionally tolerate files it did not write. The bound is
applied to the **planned render**, before `write_artifacts` (`routing.py:1043`) touches disk, because
bounding a generated file only on its next read is too late — the first rebind has already written
it.

### Axis 10 — the roster's rendered output

`agent_names` reads names only, never README bytes, so the input side was already bounded. The
output side is the SessionStart context block: **922 bytes** with alphavar's 4 agents, of which
≈884 is fixed scaffold, so the names are the only growing term.

| axis | measured max | proposed cap | unit |
|---|---:|---:|---|
| 10 rendered SessionStart roster block | 922 | **64,000** | bytes |

### Peak resident — measured, not inferred

Rounds 1–2 estimated this. Measured directly with `ru_maxrss` around the two transcript scanners:

| transcript | scan | peak RSS delta |
|---|---:|---:|
| 51 KB | 5.8 ms | 128 KiB |
| 7.65 MB | 239 ms | 2,304 KiB |
| 19.3 MB | 689 ms | 3,220 KiB |
| **64,000,204 B — a fixture at the cap** | **1,113–1,180 ms** | **3,532–3,572 KiB** |

**The streaming claim holds.** Memory does not track file size: 3.3× more file between 19.3 MB and
64 MB buys 10% more resident. The residual ≈3.5 MiB is dominated by the largest individual records
parsed, not by the file. Scan time is linear and lands at **≈1.15 s at the cap**, which confirms the
figure the (b) cap decision accepted.

### Structural boundary fixtures — JSON passes

| fixture at the proposed cap | cost |
|---|---:|
| depth 32 | 0.09 ms |
| depth 1000 (far over cap) | 0.47 ms |
| 100,000 nodes (689 KB) | 46 ms |
| single string 1,000,000 B | 3.05 ms |
| payload 4,000,000 B | 13.4 ms |

All cheap, and depth is not a cliff — the depth cap is a guard against pathological nesting, not a
cost boundary, exactly as §8 said.

### The axis-7 D2 glob caps do not survive their own fixture

`hook_core._segments_match` is naive recursive backtracking: `**` spans zero or more segments via
`any(_segments_match(rest, path[i:]) for i in ...)`, with **no memoization**. Cost grows as roughly
`depth ** stars`. Measured against a non-matching path at the proposed depth cap of 32:

| `**` per glob | 1 glob | 200 globs (the proposed cap) |
|---:|---:|---:|
| 1 | 0.25 ms | ~50 ms |
| 2 | 1.5 ms | ~0.23 s |
| 3 | 17.5 ms | **~3.0 s** |
| 4 | 132–150 ms | **~30 s** |

**At exactly the caps this document proposed — 200 globs, 4 `**` each, path depth 32 — one path
check costs about thirty seconds.** That is a `PreToolUse` hook, on every edit. It is not a
hypothetical over-cap case: it is the boundary the envelope would guarantee as *supported*, and F6's
entire premise is that everything inside the envelope completes on the fast path. The fixture that
was supposed to ratify these caps refuted them instead.

No live consumer is anywhere near it — alphavar has 4 globs, at most 2 `**`, depth 4 — so this is a
latent configuration hazard rather than a current outage. But a cap is a promise about the worst
supported case, and this promise is currently false.

Two remedies were considered:

- **(a) Lower the axis-7 caps** to what the current matcher can carry — `**` per glob ≤ 2 and glob
  count ≤ 50 puts the worst case near 58 ms. Cheap, immediate, and it sets a contract boundary from
  an implementation defect, which is the mirror image of the rule the lock already states: caps are
  compatibility boundaries, and implementation must not move them to make a test pass.
- **(b) Memoize the matcher** on `(pattern index, path index)`, which collapses the cost per glob to
  `O(pattern × path)` and makes the proposed caps comfortably true. It is a change to a pure
  function with **provable equivalence** — memoizing a deterministic predicate returns identical
  results — so it does not carry the burden the lock places on redesigning an expensive source.

**Owner choice: (b).** C66 uses call-local memoization only — no persistent cache, saved state,
freshness or invalidation surface — keyed by pattern and target-path indexes. Option (a) is rejected
because it would freeze a repairable implementation defect into the compatibility boundary.

The implementation acceptance is exact: a differential old-vs-new corpus covers literals, `*`,
`?`, zero/one/multiple/consecutive/trailing `**`, empty paths, matches and non-matches; the full
200-glob, four-`**`, depth-boundary fixture is rerun after implementation. The axis-7 table's
`glob path depth` is the **pattern** depth, not automatically the target-path depth. The rerun must
therefore use the maximum target-path depth admitted by every applicable path-bearing route; if any
route lacks an exact target-side bound, that mapping remains incomplete rather than being inferred
from the glob cap.

The §4 caps remain proposed and unratified after code landing. They become eligible for ratification
only after the differential corpus passes, the exact boundary rerun supports them, and the owner
explicitly verifies D2-23. Recorded as [C66](../TASKS.md).

### Where this leaves the packet

Every axis now has a measured maximum, a proposed cap and a unit; the combined corpus is composed;
peak resident is measured. **F6 is complete as measurement evidence and not yet ready for owner
verification**, because the current matcher cannot support one proposed boundary. C66(b), its
differential corpus and the exact boundary rerun must complete before the table returns to the owner
for explicit D2-23 verification.
