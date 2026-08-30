# N7 — what makes a consumer's Codex hooks load, terminal

> **Verdict, terminal for the ordinary persisted consumer path on codex-cli 0.149.1: a
> correct `.codex/hooks.json` is NOT sufficient for delivery.** Two independent host-side
> grants were required without a bypass flag, both living in `~/.codex/config.toml`, neither
> written nor currently read by anything akmon ships:
> **(1) project trust gates discovery** — without a `[projects."<abs root>"]` entry the file is
> not read at all, and trust does **not** inherit from an ancestor entry; **(2) persisted
> per-entry hook trust gated the directly probed `SessionStart` and `PreToolUse` execution** —
> discovered entries remained `enabled: true` but did **not** run when their `trusted_hash` was
> absent (`untrusted`) or stale (`modified`). See the addendum for the two `PreToolUse` probes.
>
> The consequence that outranks the fresh-consumer case: **a `sync` that changes approved
> wiring invalidates the affected approvals.** The hash covers the entry's group, so changing
> only a `matcher` flips every entry in that group to `modified`. Silent non-execution was
> measured for both routes, including `PreToolUse` on the exact
> `Edit|Write|apply_patch` → `Bash|apply_patch` transition alphavar faces. akmon's own `verify`
> does not inspect either host-side state.
>
> Owned by [N7](../TASKS.md). Corrects one incidental claim in
> [the N1/F4 probe](n1-f4-codex-timeout-20260825.md) — see §The N1 false negative.

## Environment and method

| | |
|---|---|
| vendor build | **codex-cli 0.149.1** (`codex --version`) |
| subject | a fresh consumer: `git init`, then a **complete** attach — the akmon block in `AGENTS.md`, the `_aitna/` dev layer (`TASKS.md`, `agents/`, `memory/`), akmon vendored at `_aitna/akmon`, wiring written by the **unmodified** `bin/sync.py`. Completeness matters only for finding 5: a partial attach makes `verify` exit 1 on the missing dev layer, which is a different failure than the one measured here |
| free oracle | `codex app-server` → `hooks/list`, which takes arbitrary `cwds` and returns per entry: `key`, `enabled`, `trustStatus` (`managed｜untrusted｜trusted｜modified`), `currentHash`, `source` |
| paid oracle | `codex exec --sandbox read-only -C <consumer>`, stdin closed, prompt `Reply with exactly: OK` |
| firing observable | the generated `SessionStart` command wrapped so it appends a marker file before invoking the real akmon hook |
| isolation | `CODEX_HOME` pointed at a scratch home carrying only `auth.json` + a written `config.toml`, so the owner's `~/.codex/config.toml` was **never edited** |

`hooks/list` answers discovery and trust for free. It cannot answer execution: `thread/start`
fires no `SessionStart` hook — measured against **alphavar**, where the same hooks demonstrably
fire under `codex exec` — so every execution row below cost a real turn. **Three** turns were
spent, 6,333 + 3,375 + 3,583 tokens.

**Cleanup verified.** The owner's `~/.codex/config.toml` is byte-identical to its pre-probe
sha256 (`39e13d18…6460`) and holds no probe residue; all scratch consumers are removed; the
akmon worktree is untouched by the probe.

## The elimination matrix

One fresh consumer, one isolated home, grants added one at a time.

| grant in `config.toml` | entries discovered | `trustStatus` | measured `SessionStart` runs |
|---|---:|---|---|
| none | **0** | — | no |
| **project trust only** | 4 | `untrusted` | **no** — marker absent, exit 0, no diagnostic |
| **hook trust only** (hashes, no project entry) | **0** | — | n/a: never discovered |
| **project trust + hook trust** | 4 | `trusted` | **yes** — `hook: SessionStart Completed`, marker written |

For the ordinary persisted path tested here, the two grants are **not** alternatives and **not**
redundant. The first alone bought visibility but no measured `SessionStart` execution; the second
alone bought nothing, because a hash keyed to a file the host never opens is dead weight. The
bypass path is scoped separately below.

## What the runs establish

**1. Project trust is a discovery gate, and it does not inherit.** The probe home carried
`[projects."/home/ai"]` and `[projects."/home/ai/workspace"]` as trusted. A consumer at
`/home/ai/n7-visible` — a direct child of a trusted entry — still discovered **0** hooks. Only an
entry naming the consumer root itself produced the four. Nothing is logged when discovery finds
nothing: `hooks/list` returns an empty list with an empty `errors` array.

**2. Location is not a factor; the trust entry is.** Three fresh consumers were built at once —
under a hidden path segment (`/home/ai/.claude/jobs/…`), at a visible path under a trusted
ancestor (`/home/ai/n7-visible`), and outside every trusted prefix (`/tmp/n7-untrusted`). All three
discovered 0, and the sole control that discovered 4 was alphavar. This rules out the hidden-path
explanation that the original scratch location invited.

**3. A non-`trusted` entry is reported `enabled: true` and still does not run.** This is directly
measured for `SessionStart` and `PreToolUse`, with `PreToolUse` probed under both `untrusted` and
`modified`. `enabled` reflects the *wiring* and `trustStatus` reflects the *grant*, so a check
cannot read `enabled` alone to mean "this will run".

**4. A `sync` that changes approved wiring invalidates the affected approvals.** The
`trusted_hash` covers the entry within its group, not the command alone. Measured on an approved
consumer:

| edit made to an approved `hooks.json` | result |
|---|---|
| the three `PreToolUse` **commands** change (e.g. a mount path `_aitna/akmon` → `_aitna/.akmon`) | those three → `modified`; untouched `SessionStart` stays `trusted` |
| only the group's **matcher** changes, commands byte-identical | **all three** in that group → `modified`; `SessionStart` stays `trusted` |
| the approved `SessionStart` group's matcher changes | that entry → `modified`, and a real run wrote **no marker, no `hook:` line, no warning** |

Invalidation status is per group and per entry, never whole-file. The execution consequence was
measured on the modified `SessionStart` and on the three modified `PreToolUse` entries. In both
cases a matching call ran after invalidation while the affected hook stayed silent; the addendum
records the `PreToolUse` run.

**This is not hypothetical for the owner.** alphavar today carries the pre-C49 matcher
`Edit|Write|apply_patch` against the generator's current `Bash|apply_patch`. The next `sync` there
is a matcher-only change to the approved `PreToolUse` group, so it will flip all three of
alphavar's advisory hooks to `modified`. The addendum runs exactly that transition and measures
all three entries staying silent until re-approval.

**5. No akmon check notices either host-side state.** `bin/verify.py` run inside the fresh
consumer with no project-trust entry exits **0**: it confirms `hooks/codex-hook.py` and its
siblings *exist*, while `hooks/list` discovers zero entries. The two `[warn]` rows verify prints
(`.gitignore` missing, no workflows) are unrelated — they reflect how this subject was attached,
not the state under test; a consumer attached through `akmon init` prints neither and still
exits 0 against zero discovered entries. A consumer can therefore be attached, synced,
verified green, and have no project hooks discovered by Codex. The separate project-trust-only row
first proved silent `SessionStart`; the addendum below independently proves the same absent/stale
entry-trust execution loss on the measured `PreToolUse` route.

## The N1 false negative

The N1/F4 probe recorded that hooks stayed dead "even with … a
`projects."<path>".trust_level="trusted"` override". That override never applied:

| `-c` form | entries discovered |
|---|---:|
| `projects."/home/ai/n7-visible".trust_level="trusted"` — quoted segment | **0** |
| `projects./home/ai/n7-visible.trust_level="trusted"` — unquoted | **4** |

For the exact `/home/ai/n7-visible` path tested, the quoted spelling is accepted and silently does
nothing, matching the vendor behaviour N1 already measured for unknown hook keys: **acceptance
carries no information on this vendor.** So N1's three dead runs are fully explained by cause (1)
alone, and its parenthetical should be read as "the override I wrote did not take", not "trust was
granted and did not help". The unquoted spelling worked for that exact path. Paths containing dots
or requiring other dotted-key escaping were not tested, so this probe makes no claim about a
working `-c` spelling for them.

`--dangerously-bypass-hook-trust` sits outside the ordinary persisted path in the verdict. Its own
help says it runs **enabled** hooks without persisted hook trust. N7 did not complete a fresh-matrix
row combining project trust, an `untrusted` entry and the bypass flag. That execution behavior is
nevertheless already measured by N1: every N1 run used `--dangerously-bypass-hook-trust`, and the
appended entry had no persisted hash; it executed on trusted alphavar for both `SessionStart` and
`PreToolUse`. N7 separately measured that `-c bypass_hook_trust=true` without a project entry still
discovers **0**, so bypass waives persisted per-entry trust only after project discovery and does not
remove the discovery gate. The two-grant verdict therefore does not apply to bypassed execution.

## What this spawns

Delivery is a real gap, and the honest statement of it is narrow: **akmon does not currently grant
or inspect Codex's host-side trust state, but it can stop reporting green when hooks are undiscovered
or their entries are not trusted.** The option space, cheapest first:

- **A `verify` finding that asks the host.** `codex app-server` + `hooks/list` is authoritative,
  needs no config parsing, and returns exactly the two facts that matter (discovered at all;
  `trustStatus` per entry). Costs a subprocess and a codex dependency in a check that must stay
  useful when codex is absent.
- **A `verify` finding that reads `~/.codex/config.toml`.** No dependency, but it reimplements the
  vendor's discovery and hashing — and this probe measured that the hash covers the group, so a
  reimplementation is a standing bug source.
- **Say it at attach time only.** `sync`/`init` print the two grants a consumer still owes,
  and `verify` stays silent. Cheapest, but it is the mode that already failed: it tells the
  consumer once, at the moment they are least able to act, and never again.
- **Do nothing and document it.** Defensible only if the interactive TUI path always grants both,
  which this probe did not measure and which does not cover the re-approval case in finding 4.

**Owner resolution (D2-27).** The first option is selected. C70 uses the authoritative
`codex app-server` `hooks/list` result after generated-wiring validation, derives its expected
population from that wiring, reports inactive trust as one aggregate warning with strict failure,
skips neutrally when optional Codex is absent, and warns when an installed Codex cannot be
inspected. It never reconstructs hashes or grants trust; remediation is through `/hooks`. The owner
accepts a bounded subprocess and possible vendor-owned cache, log, or network effects while the
consumer tree and host config remain read-only. Config parsing, attach-only advice and
documentation-only handling are rejected because they miss or risk missing the *already attached,
previously working* consumer after `sync`. C70 follows C51 and C57; C59 follows C70 and receives the
result only through `verify`. This paragraph records the disposition; the implementation contract
lives in C70 and the linked designs.

## Addendum — the `PreToolUse` execution gaps, measured

Run separately from the three turns above, on the same vendor build and under the same isolation
discipline (scratch `CODEX_HOME`; the owner's `~/.codex/config.toml` untouched and byte-identical
after). The first pair measures the exact three-entry matcher-only transition alphavar faces; the
follow-up independently measures the absent-hash and stale-hash states with one minimal handler.

| | |
|---|---|
| subject | scratch consumer attached through `akmon init --mode package`; every generated hook command wrapped as `sh -c 'date +%s >> <marker>; exec <real command>'` |
| approved wiring | the `PreToolUse` matcher alphavar carries today, `Edit|Write|apply_patch`, all four entries granted project trust **and** `trusted_hash` |
| invalidation | the exact C49 sync change — matcher only, `Edit|Write|apply_patch` → `Bash|apply_patch`, commands byte-identical |
| driver | `codex exec --sandbox workspace-write -c approval_policy="never"`, prompt: create `probe.txt` via `apply_patch` |
| route held constant | `apply_patch` matches **both** matchers, so nothing about routing changes between the runs — only the hash |

| run | `PreToolUse` `trustStatus` | markers written | `hook: PreToolUse` lines | the `apply_patch` call | `SessionStart` (control) |
|---|---|---:|---:|---|---|
| A | `trusted` | **3 of 3** | 3 + 3 `Completed` | ran, patch applied | fired |
| B | `modified` | **0 of 3** | **none** | ran, patch applied | **fired** — group untouched, still `trusted` |

Run B is the result: the tool call those entries name executed, the entries were reported
`enabled: true`, and all three stayed silent — no marker, no `hook:` line, no warning, no
diagnostic anywhere in the session output. The still-trusted `SessionStart` firing in the same
run is the internal control: the hook machinery was alive, and only the invalidated group was
skipped. A matcher-only `sync` therefore does not merely re-label an approval — it takes the
three advisory hooks off the route, invisibly, until they are re-approved.

Cost of the exact generated-population pair: two turns, 12,548 + 6,396 tokens.

### Independent one-handler confirmation

One project-trusted scratch consumer carried a minimal matching `PreToolUse` handler and an
unchanged trusted `SessionStart` control. Both runs omitted
`--dangerously-bypass-hook-trust`; each prompt required one real `apply_patch`, and each patch
completed successfully.

| run | persisted `PreToolUse` hash | matcher | `hooks/list` | target marker | trusted control | usage (input/output) |
|---|---|---|---|---:|---:|---:|
| U | absent | `apply_patch` | `enabled: true`, `untrusted` | **0** | **1** | 28,451 / 87 |
| M | old hash retained | `Bash|apply_patch` after matcher-only change | `enabled: true`, `modified` | **0** | **1** | 29,202 / 209 |

For M, the persisted hash was the current hash of the original `apply_patch` entry; changing only
the matcher produced a different current hash and `modified`. Both result files contained the
requested text, while neither run created the target marker or captured a `PreToolUse` payload.
The owner config retained sha256 `39e13d18…6460`, the akmon worktree status was unchanged, and the
scratch roots were removed. No ordinary persisted-path `PreToolUse` trust state remains inferred.
