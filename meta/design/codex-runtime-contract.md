# Design: Codex runtime contract and package-mode hardening

> Implementation task: [C39](../TASKS.md). Owner-verified in
> [D2-13](../D2_LEDGER.md) (clauses a–c, **Approved**), with the capability-matrix clause signed
> against the delivery caveat N7 added to the matrix.

## Frame

akmon `v0.3.0` states that delegation is the default and that always-on guardrails reach every
vendor through `AGENTS.md`. The alphavar package-mode pilot disproved two assumptions:

- Codex loads the literal `AGENTS.md` text but does not expand the nested `@.../_common.md`
  line into model-visible instructions, so the delegation rule never reaches the orchestrator;
- hooks still discovered a project through `<AITNA_ROOT>/akmon`, which does not
  exist in package mode, so SessionStart becomes silent from a nested working directory.

Good means that a fresh Codex session receives the operative delegation rule without an owner
prompt, the wired hooks work from any directory below the project root once Codex's host-side
project and entry trust grants delivery, and documentation
claims no enforcement or model-routing capability that has not been proven against the live
Codex harness.

## Decisions

### Direct operative anchor, verify-only ownership

The root `AGENTS.md` remains hand-reviewed. The akmon block must state the delegation-default
rule directly and link `_common.md` as its normative owner. `verify --strict` rejects a consumer
whose block only contains an `@` line. `BOOTSTRAP.md` supplies the exact concise clause.

This selects **verify-only** over:

- a marker-managed generated region, rejected because it weakens the existing hand-owned
  `AGENTS.md` invariant and makes `sync` mutate the project's primary instruction source;
- a separate generated include, rejected because the live failure is precisely that Codex does
  not expand the include into model-visible context.

The SessionStart hook repeats a capability-neutral reminder as defense in depth. It names task
kinds, not Claude-specific `k_*` files: a harness may provide generic subagents without named
agent definitions or child-model selection.

### Package runtime is self-contained

Project-root discovery accepts `AGENTS.md` plus either a mounted `<AITNA_ROOT>/akmon` tree or the
package integration record `<AITNA_ROOT>/.akmon.toml`.

**Amended by C77.** Runtime paths resolve to the tree the hook is *executing* from, not to a
recorded mode: the mounted tree in mounted modes, the wheel's embedded tree in package mode,
where the Codex wiring calls `"$(git rev-parse --show-toplevel)/.venv/bin/akmon" hook codex-hook
<advisory>`. That replaces the earlier rule that every dependency of a wired hook must be copied
into `<AITNA_ROOT>/.akmon/`: nothing executable is copied any more, and the dependencies are
already installed beside the consumer inside the wheel. A hook still never imports the consumer's
own packages — only the stdlib and the tree it runs from. What mode `package` does require is
that the virtualenv live inside the project root, since the wiring names the console script by a
project-relative path.

### Capability-aware Codex support

The vendor-neutral policy remains mandatory; enforcement depth is vendor-specific. For Codex:

- `AGENTS.md` and SessionStart carry role, memory, and delegation policy;
- edit reminders remain wired;
- D5, delegation log/nudge, model binding, named subagents, and child-model selection are not
  marked supported until live payload and enforcement probes prove their exact contracts;
- generic subagent capability may satisfy delegation even when `k_*` names/model pins are not
  available.

The compatibility matrix distinguishes policy delivery, advisory hooks, hard enforcement,
subagent launch, and model selection instead of collapsing them into one checkmark.

### PreToolUse routes (measured, codex 0.146.0 — C49)

Codex normalizes tool names into Claude's matcher vocabulary, so a matcher names a **route**,
not a tool spelling. Two routes reach the filesystem:

| route | fires on matcher | payload `tool_name` | payload carries |
|---|---|---|---|
| patch | `Edit`, `Write`, `apply_patch` (three aliases, one call) | `apply_patch` | the patch body in `tool_input.command` |
| shell | `Bash` | `Bash` | a command string in `tool_input.command` |

`exec_command` and `shell` — the names the model-facing tool surface uses — match nothing.
The emitted matcher is therefore `Bash|apply_patch`: one name per route, and deliberately not
`.*`, which would put an unconditional hook on the hottest tool for no added precision.

That matcher is minimal by measurement and therefore **silent on drift** (D2-19 a): every
diagnostic below runs inside the hook process, so a codex release that unfolds the three
aliases into separate routes would stop the hooks with nothing to report it. It is not patched
locally by padding the matcher with `Edit|Write` — that asserts as routes two names never
measured as routes. The fix is a version-stamped harness inventory, which is C46's mechanism.

Two consequences akmon states rather than papers over:

- **One narrow Bash exception is path-classified.** Only a command containing a recognized
  `apply_patch` invocation **and** a valid patch envelope is treated as an edit. C48 then extracts
  its paths and C47 normalizes them. A path read from the measured patch body is stated as
  measured; a path produced only by one of the tolerated but unmeasured payload keys still drives
  the advisories and is reported as unmeasured on stderr, because a guess that matches would
  otherwise classify in silence (D2-18 a). Both halves are owner-verified: D2-17 and
  D2-18. Recognized means *in command position* — the start of the command string, after a
  `;`/`&&`/`||`/`|` separator, at the head of a subshell `(`/`$(` or a `{ ` group, or inside a
  `sh -c`/`bash -lc` wrapper — but never after a bare newline, which is how a heredoc carries a
  line of quoted data. Anchoring on the string start alone would let one token in front of the
  call (`cd sub && apply_patch …`) undo the classification, and a bypass is spelled, not typed;
  the set therefore has to cover the ordinary ways a shell opens a command rather than the two
  that happened to be written down first. The width is affordable because the narrowing lives
  elsewhere: the match must also sit on the **first line**, **outside shell quoting**, and open
  the patch heredoc **directly**, so a false positive needs a real invocation rather than a
  lucky character. A brace counts only when a space follows it — `{apply_patch` is one word
  naming a different command. Patch-shaped text without the invocation, and an invocation whose
  envelope lines are not lines of their own, stay on the unclassified Bash route. The width is
  affordable because **every unrecognized form degrades to the reported route, never to
  silence** (D2-19 b): `apply_patch < p.txt`, `env apply_patch <<EOF` and an invocation on the
  second line of a script all stay Bash and draw the diagnostic below, so a false negative
  costs one line of precision in a message that still fires. Chasing further prefixes would go
  back to enumerating spellings, which the `shlex` fork closed.
- **Every other Bash call is unclassified and reported generically.** A command string does not
  reliably reveal either its affected paths or whether it mutates, so akmon guesses neither.
  The three separately launched path-keyed hook processes share one atomic marker for a combined
  stderr diagnostic that the route **may mutate files unseen**. With a reliable `session_id`,
  exactly the first process to claim the marker emits once for the session; without one, the
  diagnostic repeats rather than using a global `nosession` marker that could hide later gaps.
  This is a hook-process diagnostic only: whether Codex surfaces stderr to the owner is unverified.
  The throttle domains differ on purpose (D2-19 c): a **route-level** diagnostic states what a
  route can do and is said once per session; an **event-level** one reports a defect in a single
  call and throttles by session/tool-use pair, so the next defect stays visible.
- **The blind spot is not Codex's** (D2-19 e, owner decision). On Claude the advisories sit on
  `Edit|Write|MultiEdit`, so a write arriving through `Bash` — `python3 - <<EOF`, `cat > f <<EOF`
  — was not merely unclassified there but *unreported*. The diagnostic therefore lives in
  `hook_core.report_unclassified_shell_route`, one implementation and one wording for both
  vendors, and Claude emits it from the `Bash` commit-guard process that was already wired: no
  extra process on the hottest tool. What is **not** carried across is the `apply_patch`
  classification itself — it is measured on codex only, and guessing a second vendor's shell
  idiom is the failure D2-18(a) rejects.

The exact patch-heredoc route is now observable to the advisories, not enforcement. The hard-deny
bypass remains open: these hooks are advisory, and no matcher makes a denied effect unbypassable.

### Host-side hook trust verification (C70, D2-27)

N7 measured a delivery precondition outside generated wiring: on the ordinary persisted,
non-bypass path, project trust controls discovery and per-entry trust controls execution. A
generated entry may therefore remain `enabled: true` while its `SessionStart` or `PreToolUse`
handler is inert after an absent or stale group-scoped hash. Generated wiring is structural proof,
not proof of host delivery.

D2-27 selects an authoritative live query rather than a local reconstruction. After C51 and C57,
C70 runs inside `verify`, after generated wiring has validated, and obtains `hooks/list` through a
bounded `codex app-server` subprocess constructed by C57's sole vendor-command owner. Its expected
population is derived from the generated plan. Missing, disabled, `untrusted`, or `modified`
expected entries collapse into one warning; strict mode exits 1 without escalating its severity.
An absent optional Codex installation is a neutral explicit skip. A resolved installation that
cannot be inspected is a warning and strict failure, never an inferred delivery claim.

The check does not parse `~/.codex/config.toml`, compute vendor hashes, grant trust, or auto-approve
entries. Owner remediation is through `/hooks` only. It writes neither the consumer tree nor host
config; vendor-owned cache, log, or network effects caused by app-server startup are an accepted
bounded operational cost. C59 waits for C70 and receives this finding exactly once as part of the
complete `verify` stream; it never adds a third provider or queries Codex itself. Exact Finding
codes and the timeout literal are mechanical C70 constants pinned by its isolated carrier corpus.

### Release class

This changes an operative role/delegation contract and is therefore a breaking `v0.x` release:
development moves to `0.4.0.dev0`; the owner later cuts `v0.4.0`. The existing `v0.3.0` tag is
immutable. Commit, tag, push, publish, and consumer pin updates remain owner-run.

## Acceptance

- meta tests cover mounted and package root discovery, including nested cwd and custom
  `AITNA_ROOT`;
- a real stdin-to-JSON Codex SessionStart test contains the direct delegation instruction;
- verifier rejects an `AGENTS.md` block with only the guardrail import and accepts the explicit
  anchor;
- package sync materializes the imported guardrails, `sync --check` detects drift, and a
  previous version's materialization is removed in one run;
- self-CI includes an installed-wheel package-mode smoke from a nested cwd, which runs **every
  generated hook command verbatim** and checks exit code, stderr and the size of stdout — the
  last because a hook that cannot find its tree exits 0 with an empty stderr;
- README, BOOTSTRAP, hooks docs, capability matrix, task state, and changelog agree with code;
- tests, ruff, self-CI (including strict consumer-fixture verify), and build pass.

## Open Verification

The following require a live Codex protocol spike and stay explicitly unsupported until proven:

- exact PreToolUse names/payloads for read/search and subagent calls (**shell is now
  measured** — see the route contract below);
- whether subagent calls are observable by project hooks and expose parent/child identity;
- attended and non-interactive `ask`/`deny` behavior;
- user-visible hook output and child model selection.
