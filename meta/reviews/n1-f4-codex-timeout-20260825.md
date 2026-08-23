# N1 — F4 Codex hook-timeout probe, terminal

> **Verdict, terminal: `timeout` is SUPPORTED on codex-cli 0.149.1, in seconds, at all four command
> positions akmon wires, on both routes the shipped matcher names.** The exact-matcher completion
> this document previously deferred is now closed in §Exact matcher below: the unmodified generator
> matcher `Bash|apply_patch` was exercised on a real `apply_patch` call, with a timeout observed on
> that route. The key is **`timeout`**, not `timeoutSec`. `timeoutSec` is accepted and silently
> ignored, and so is any other unknown key — which means **parse acceptance carries no information
> at all on this vendor**, exactly the reason [owner choice F4/C](../design/stage1-hardening-contracts.md)
> refuses it as evidence.
>
> Owned by [N1](../TASKS.md); feeds [D2-23](../D2_LEDGER.md), which gates only C52.

## Environment and method

| | |
|---|---|
| vendor build | **codex-cli 0.149.1** (`codex --version`) |
| model / invocation | `gpt-5.6-sol`, `codex exec` non-interactive, `--sandbox read-only` |
| configuration source | project-scoped `.codex/hooks.json`, auto-discovered; trust recorded in `~/.codex/config.toml` `[hooks.state]` keyed `<abs path>:<event>:<group>:<index>` |
| probe location | **alphavar**, the attached consumer — a scratch hook appended to the real generated wiring, then removed |
| slow fixture | a hook that marks `start`, heartbeats every 250 ms for 12 s, marks `end` |
| sentinel literal | `3` |

Every run used `--dangerously-bypass-hook-trust` (the appended entry has no persisted trust hash)
and closed stdin; `codex exec` blocks reading stdin when it is neither a TTY nor piped, which cost
two void runs before it was isolated.

**Cleanup verified.** `.codex/hooks.json` was restored byte-identical to its backup and is absent
from alphavar's `git status`; `~/.codex/config.toml` still holds its original four `[hooks.state]`
entries and no probe residue. **Eleven** `codex exec` turns were spent on the owner's account across
both series, on the order of 100k tokens.

## Runs

| run | wiring | hook reached | terminated at | codex reported | outcome |
|---|---|---|---|---|---|
| **A** | `SessionStart`, `"timeoutSec": 3` | `end` at **12.038 s** | never | `Completed` | **ignored** |
| **B** | `SessionStart`, `"timeout": 3` | `beat11` at **2.758 s** | yes | `Failed` | **honoured** |
| **C** | `SessionStart`, `"bogusFieldXyz": 123`, no timeout | `end` at **12.041 s** | never | `Completed` | unknown key **silently ignored** |
| **D** | `PreToolUse`, `"timeout": 3`, matcher `Bash\|shell\|exec\|exec_command\|apply_patch` | `beat11` at **2.760 s** | yes | `Failed` | **honoured**; the tool call still ran |
| **E** | as D, hook traps `SIGTERM`/`SIGINT`/`SIGHUP` | `beat11` at **2.758 s** | yes | `Failed` | **no catchable signal delivered** |

Run A is the no-timeout control as well as the `timeoutSec` test: with no honoured timeout the hook
runs its full 12 s and the session waits for it (17.5 s wall against ~9 s for a run whose hook is
killed). Runs A–E used a scratch hook appended beside the real wiring; the per-entry series below
then repeated the measurement **at each of the four real entry positions**.

## What the runs establish

**1. The key is `timeout` and the unit is seconds.** `timeout: 3` killed the fixture between its
2.758 s and 3.008 s heartbeats — the tolerance is under one heartbeat interval, so the literal is
seconds and the enforcement is tight. C52 emits `"timeout": <literal>` and nothing else.

**2. `timeoutSec` is a trap.** It appears in the shipped binary's symbol table beside `matcher` and
`statusMessage`, so a probe designed from the strings — or from documentation — would have tested it
first, watched the hook run to completion, and recorded a terminal **`unsupported`**. That verdict
would have been wrong, and it would have been wrong in the direction that ships less safety. The
distinction cost one extra run because the design required an expiry observation rather than an
acceptance check.

**3. Parse acceptance is worth nothing here, and that is now measured rather than assumed.** Run C
put `bogusFieldXyz` in a hook object; codex accepted the file, ran the hook, and reported
`Completed`. Unknown keys are silently dropped, so "codex did not reject my config" is not evidence
of anything. F4/C's rule — *`Supported` means the accepted field actually terminates the slow
fixture* — is the only rule that could have reached the right answer.

**4. A hook timeout is fail-open at the decision level.** In run D the `PreToolUse` hook was killed
and the tool call **proceeded**: `/bin/bash -lc 'echo f4D'` ran and succeeded. A Codex hook that
hangs therefore cannot block a tool call; it delays it by the literal and is then discarded. This
matches F3's crash-open posture rather than contradicting it, and it means the timeout literal is a
**latency bound, not a safety bound** — a denied action does not become denied-by-timeout, it becomes
allowed.

**5. Termination is hard and silent.** Run E's fixture trapped `SIGTERM`, `SIGINT` and `SIGHUP` and
wrote no signal marker before dying, so none of the three was delivered — consistent with `SIGKILL`
or a process-group kill. A timed-out hook therefore **cannot clean up and cannot emit its own
diagnostic**. Anything C52 wants to say about a timeout has to be said by the host: codex prints
`hook: <Event> Failed` and nothing more. Recorded because the lock's oversize path requires the hook
itself to emit exactly one safe stderr line — that mechanism is unavailable on the timeout path,
which is a different path and must not be conflated with it.

## Scope coverage — all four positions; exact matcher closed below

akmon's generated Codex wiring has **four command entries in two event scopes**: three `PreToolUse`
hooks sharing one `Bash|apply_patch` group, and one `SessionStart` hook. The owner chose the strict
reading of "each entry scope that C52 would modify is probed separately", so **each of the four was
probed in its own real position**, with the slow fixture standing in for that entry and its siblings
present and fast.

| entry | position | killed at | codex reported | siblings | tool call |
|---|---|---:|---|---|---|
| `role-on-code` | `PreToolUse[0]` | **2.758 s** | `Failed` | both reached `end` | proceeded |
| `analysis-guard` | `PreToolUse[1]` | **2.757 s** | `Failed` | both reached `end` | proceeded |
| `d2-ledger-reminder` | `PreToolUse[2]` | **2.757 s** | `Failed` | both reached `end` | proceeded |
| `session-start` | `SessionStart[0]` | **2.759 s** | `Failed` | n/a (sole hook) | n/a |

The result is uniform across all four: `timeout` is enforced per hook object, at the same tolerance,
regardless of event, group position, or which sibling is slow. **A timed-out entry does not disturb
its siblings** — in every `PreToolUse` run the other two hooks completed normally and the tool call
went through. Enforcement is therefore per entry, not per group.

At this point in the probe, one strict-evidence field was still missing. The retained run D names a broader scratch matcher
(`Bash|shell|exec|exec_command|apply_patch`), while alphavar's restored consumer wiring is recorded
below as stale (`Edit|Write|apply_patch`) against the generator's current `Bash|apply_patch`.
The per-position table proves hook-object and sibling behavior but records no exact matcher for that
series. D2-23 requires exact event/matcher/entry evidence, so matcher-independence was not inferred
into a terminal route claim. The retained exact-matcher series in
[the later section](#exact-matcher--the-apply_patch-route) closes this gap.

The strict reading was worth taking. It is what produced the group-behaviour result below, which the
event-scope reading would not have reached.

## Hooks in one group run concurrently, not in sequence

A separate run gave all three `PreToolUse` hooks a 6-second sleep and no timeout:

| entry | start offset | end offset |
|---|---:|---:|
| `role-on-code` | 0.000 s | 6.021 s |
| `analysis-guard` | 0.007 s | 6.023 s |
| `d2-ledger-reminder` | 0.008 s | 6.021 s |

All three started within **8 ms** of one another and finished together; total session wall was
17.5 s against a ~9 s baseline, i.e. the group cost ~6 s and not ~18 s.

**A group's latency is `max` of its entries, not `sum`.** This is a direct input to F5/N6: per-entry
literals compose cheaply, an aggregate event group needs no separate budget beyond its slowest
member, and the lock's requirement to "live-test aggregate event groups at proposed literals" is
testing for a `max` relationship rather than an additive one. It also means one slow entry cannot
starve the others — each is killed on its own clock.

## Incidental findings

- **Hooks did not load in an untrusted scratch repository.** The first three runs used a disposable
  repo under the job scratch directory; no hook fired there, for either event, even with
  `--dangerously-bypass-hook-trust` and a `-c projects."<path>".trust_level="trusted"` override.
  The same wiring fired immediately in alphavar, which carries both a `[projects]` trust entry and
  `[hooks.state]` hashes. **The cause was not isolated** and is recorded as an observation, not a
  contract — but it bears directly on delivery: if a freshly attached consumer's Codex hooks stay
  inert until something grants trust, `sync` writing a correct `hooks.json` is not sufficient for
  the hooks to run, and no akmon check would notice. Worth its own probe.
- **Real Codex payload sizes**, captured incidentally by the fixture: `SessionStart` **328 bytes**,
  `PreToolUse` **469 bytes**. Both are three orders of magnitude below N5's proposed 4,000,000-byte
  payload cap.
- **alphavar's wiring is stale.** Its `PreToolUse` matcher is `Edit|Write|apply_patch`, while the
  current generator emits `Bash|apply_patch` (the C49 widening). The consumer has not been re-synced
  since. Outside this probe's scope; recorded because the probe read the file.

## What this unblocks, and what it does not

F4 mechanics are **supported** at all four positions: key `timeout`, unit seconds. The later exact
current `Bash|apply_patch` series makes F4 terminal for D2-23. C52 may emit the measured key on all
four Codex routes and add the exact generated-shape regressions only after the complete F4 + F6 + F5
packet is owner-verified.

It does **not** choose a duration. The sentinel `3` proves mechanics only and is explicitly not a
production budget; the literal is F5's, owned by [N6](../TASKS.md), and still needs N5's caps
verified first. D2-23 stays pending until the F4 + F6 + F5 packet is complete and owner-verified.


## Exact matcher — the `apply_patch` route

The timeout series above ran against **shell** calls. The shipped matcher names two routes, so the
evidence was not terminal until the second one was exercised with the matcher left exactly as
`bin/sync.py::_codex_hooks` emits it: **`Bash|apply_patch`**, unmodified.

**The matcher fires on `apply_patch`.** Four `codex exec` turns with `--sandbox workspace-write`
drove real patch calls; all three `PreToolUse` hooks ran on every one.

**Timeout on the mutating route.** With `timeout: 3` on the first hook and a real `Add File` patch:
the hook was killed at **2.758 s** and reported `Failed`, both siblings completed — and **the patch
was applied anyway**. Fail-open is therefore confirmed on the route where it costs most: a guard that
would have blocked a write does not block it when it times out. The literal is a latency bound on the
mutating route too, not a safety bound.

### The exact payload

```json
{"session_id": "...", "turn_id": "...", "transcript_path": "/home/ai/.codex/sessions/.../rollout-....jsonl",
 "cwd": "/home/ai/workspace/alphavar", "hook_event_name": "PreToolUse", "model": "gpt-5.6-sol",
 "permission_mode": "bypassPermissions", "tool_name": "apply_patch",
 "tool_input": {"command": "*** Begin Patch\n*** Add File: _f4a.txt\n+alpha\n*** End Patch"},
 "tool_use_id": "exec-..."}
```

Two facts N5 needs. **The whole patch arrives as one string** in `tool_input.command` — there is no
structured path list — so patch bytes are bounded by the axis-3 command cap and path count, per-path
bytes and depth are *derived* limits on parsing that string, not independent input dimensions. And
the **fixed Codex envelope measures ≈453 bytes** (598-byte payload around a 145-byte `tool_input`),
against the 320-byte constant round 2 assumed for Claude; measured payloads here were 529–610 bytes.

Incidental: `permission_mode` arrives as **`bypassPermissions`** under these flags — the field
[D2-11](../D2_LEDGER.md)'s ask→deny escalation keys on.

### All four patch forms, and the D2-18 rename gap — closed by observation

| form | measured literal |
|---|---|
| add | `*** Add File: <path>` |
| update | `*** Update File: <path>` |
| delete | `*** Delete File: <path>` |
| **rename** | `*** Update File: <source>` **followed by** `*** Move to: <destination>` |

The rename form is what [D2-18](../D2_LEDGER.md) assigned here as unmeasured, and it behaves exactly
as that row feared. Running the measured rename patch through akmon's own extractor:

```
_PATCH_PATH_RE.findall(patch)  ->  ['_f4a.txt', '_f4b.txt']
destination '_f4renamed.txt' seen:  False
```

`hooks/codex_adapter.py:24` matches `Add|Update|Delete File:` only, so a renamed file is classified
under its **source** path and its **destination** is not seen at all. An advisory keyed on the
destination — a file moved *into* a D2-sensitive path, for instance — is silently skipped. This is
C48's own silent shape, one form over, and it is now observed rather than inferred. The repair
belongs to the C48 successor work, not to F4; recorded here because the probe that closed F4 is what
produced the evidence.

**Why it stayed unmeasured so long:** across **345 recorded real `apply_patch` calls** on this
machine, **zero** contained a rename. The form is rare in practice, which is precisely why inference
survived where a sample would not have.

## Cleanup

`.codex/hooks.json` restored byte-identical after every series; the four scratch files the patch
probes created were deleted; alphavar's `git status` shows no probe residue and
`~/.codex/config.toml` still holds its original four `[hooks.state]` entries. Fifteen `codex exec`
turns total across all series.
