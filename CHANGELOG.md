# Changelog — akmon

Consumer-facing release notes for the **akmon standard** (repo `ai_akmon`, mounted as
`_aitna/akmon/`). It tells a consuming project *what changed and whether it breaks them* before
they bump the pin. Convention ([ADR 0001](meta/decisions/0001-release-and-roles-model.md)):

- **Versioning `v0.x.y`** while pre-1.0 — bump `x` for a **breaking** change to layout, required
  files, or a role/pipeline contract; bump `y` for minor/patch.
- Entries are grouped **Added / Changed / Fixed / Breaking**; every `consumer-visible`,
  `migration`, or `breaking` change gets a line. `internal` changes need no entry.
- A `Breaking`/`migration` line is a consumer's **re-attach checklist item** (the bump procedure
  in [BOOTSTRAP.md](BOOTSTRAP.md) diffs the version window and walks them), so write each as
  something a consumer can *verify and act on* — name the file/path/contract that moved — not just
  *read*. The procedure lives in BOOTSTRAP; this changelog stays the record of *what changed*.
- **No dates** — the git tag is the timeline ([tasks](pipelines/tasks.md) §No dates).

## Unreleased

### Added
- **`akmon init` (C37):** one command attaches the standard to a project in any of the four
  mount modes — `submodule` (default when the project is a git repo that can reach the akmon
  repository, pinned at the latest release tag unless `--ref` says otherwise), `vendored`
  (an offline copy of the same tree the wheel ships), `subtree`, and `package` (no tree in the
  repo; the pin lives in the consumer's dev group). It creates the `<AITNA_ROOT>/` layout
  (`agents/{review,architect,engineer}`, `skills/`, `tools/`, `memory/` + index, `TASKS.md`
  seeded in the typed one-line entry grammar), writes the `AGENTS.md` akmon block and the
  `.akmon.toml` integration record, adds the `.gitignore` entries, writes a CI workflow when
  the project has none, then runs `sync` and the model-routing initializer. Judgement steps
  stay with the owner and are printed as next steps: the archetype/guardrail classification and
  the `[test].runner` pin.
  - **Commits stay the owner's (D5).** `init` creates no commit. The only index write is git's
    own: `git submodule add` stages `.gitmodules` and the gitlink, and `init` corrects *that*
    entry to the ref it checked out instead of the commit git happened to clone — on the run
    that creates the submodule and only there. Moving an **existing** pin with `--ref` is a
    bump: the worktree moves, the index is left alone, and staging it is printed as a step.
    Mode `subtree` is *refused* while the subtree is absent — `git subtree add` writes a squash
    commit and a merge commit — and prints the command to run, plus the
    `akmon init --mode subtree --ref <ref>` to run after it. Retiring a mount is a deletion of
    tracked files, so switching between two mounted modes is refused while the old mount is
    still on disk, with the removal commands printed for the owner to run.
  - **A re-run realigns, and refuses what a realign is not.** Existing project text is never
    rewritten (akmon block, backlog, memory index, charters); `.akmon.toml` keys are upserted
    one at a time; an existing submodule pin is not bumped (`--ref` moves it). Which mount a
    project has is answered by **git**, not by the files at the path — a vendored copy and a
    subtree carry the same `bin/sync.py` a submodule does — and a directory is adopted as an
    akmon tree only when it carries several of the standard's markers, never one. Changing the
    *mount mode* is a migration, not a realign, and needs `--switch-mode`, after which the
    edits `init` must not make — re-pointing the akmon block, removing the dead mount, updating
    the CI commands — are printed as steps. Mode `vendored` **replaces** each tree member
    rather than merging into it, so files a later akmon version dropped do not survive forever,
    and it refuses to copy over a directory that is not an akmon tree.
  - **Pins are honest per mode.** `--ref` pins submodule and subtree mounts and selects the
    manifest line printed for package mode; without it package mode queries the requested
    repository and uses its highest existing release tag, never a tag synthesized from the
    installed version. If that tag cannot be proved, `init` asks for an explicit `--ref`.
    `vendored` refuses `--ref` outright, because its pin *is* the installed package's version.
    In package mode the manifest is scanned for the akmon requirement and its dependency class
    (`bin/sync.py::package_pin_status`, shared with `verify` so the two cannot disagree): every
    declaration is read and the worst answer wins; distribution-name matching is case-insensitive;
    a `[tool.uv.sources]` entry is a source override rather than a declaration; and an `akmon` key
    in an unrelated tool table or a bare mention in prose is not a pin. Mode `package` mounts no
    tree, so that declaration *is* the
    mount: `init` **exits 1** while it is missing or sits in runtime dependencies/an extra,
    rather than reporting success over a project where no `akmon` command can resolve
    (ADR 0009 §4).
  - **The dev-layer root must stay inside the project.** `AITNA_ROOT` is a project-root-relative
    path by contract; an absolute path or one climbing out with `..` is refused — whether it
    arrives as `--aitna-root` or from the environment — instead of scattering the dev layer,
    the integration record and the mount outside the project.
  - New flags: `--mode`, `--aitna-root`, `--project-root`, `--repo`, `--ref`, `--archetype`,
    `--language`, `--no-ci`, `--switch-mode`, `--yes`.
- **Codex runtime contract (C39):** self-hosted `AGENTS.md` for akmon itself, a direct
  delegation-default clause in the consumer template, SessionStart defense in depth, and
  verifier coverage that rejects an import-only delegation contract.

- **`verify`: the package-mode pin is now a contract check.** In mount mode `package` with a
  `pyproject.toml` present, `verify` errors on a akmon pin declared as a runtime dependency or
  an extra (dev tooling must not reach the consumer's own users) and warns — so `--strict`
  fails — when there is no dev-group pin at all. Projects with no Python manifest are not
  checked; non-Python consumers stay a design open point.
- **`CAPABILITIES.md` — the vendor capability matrix, six axes per claim (C57).** A new top-level
  document, shipped and mounted beside `MODEL.md`, replaces the glyph grid that used to live in
  `README.md`. Each claim — one capability on one harness — answers six questions separately:
  `documented`, `delivered`, the complete `vendor / version / event / matcher` route, the
  boundary `effect`, the `crash-posture`, and the `evidence` behind whatever it measured. An
  `ask`/`deny` effect over an unmeasured route coordinate is now an error, and any enforcement
  claim standing beside a vendor or harness event *outside* the marked region is rejected as a
  second authority. The conversion demoted claims that were never measured: the Gemini pointer
  now reads `delivered: unmeasured` rather than a bare check-mark, and two Claude enforcement
  rows carry a warning until C52 measures their crash posture. **The second-opinion rows on both
  harnesses also read `delivered: unmeasured`:** akmon builds the argv and its tests pin it, but
  they run only `--dry-run`, so nothing has yet observed the command reaching a harness. A
  dry-run says what akmon emits, not what the harness accepts (probe tracked as N8).
- **A declared runtime contract (C57).** `bin/runtime.py` states what akmon needs on a host —
  POSIX shell and `python3` always, `git` on the Codex route because the generated Codex wiring
  resolves the project root through `$(git rev-parse --show-toplevel)`, `claude` and `codex`
  optional — and Windows is declared unsupported rather than merely untested. The declaration is
  checked against what akmon actually emits, so wiring that stops needing a binary makes the
  declaration fail instead of outliving it. The check tokenizes a generated command as a shell
  would, so a binary behind a `&&`, `;` or `|` cannot stay undeclared, an operator inside a
  quoted argument is not mistaken for one, and a wrapper such as `nice` counts as a requirement
  alongside the command it runs. Command substitutions are read the same way — quoting decides
  whether a `$(…)` is a command or a literal, nesting is counted rather than cut at the first
  `)`, and a head the string does not actually spell (`$RUNNER hook.py`) is refused instead of
  being reported as a binary called `$RUNNER`. The supported grammar is deliberately narrow: a construct
  outside it — a wrapper carrying its own options, a loop, a backtick, arithmetic, a function
  definition, a `[[ … ]]` conditional, or the shell-dependent `time` — is refused outright rather
  than read incompletely, or confidently wrongly, and reported as clean. What the declaration does *not* yet cover is deliberate and
  tracked as **A20**: `git` is needed by `akmon init --mode submodule` and `--mode subtree` — not
  by `vendored` or `package` — while the declaration scopes it to the Codex route.

### Changed
- **One finding shape across every akmon check (C51).** `akmon verify`, `akmon sync --check`
  and akmon's own dev-layer checks now report through a single envelope —
  `severity · code · message · target · fix` — and print one canonical stdout line per finding in the form
  `SEVERITY code target: message → fix`. **The output format changed**: `verify` used to print
  `[warn] some message`, and it now prints e.g.
  `WARN gitignore.env-secrets .gitignore: .gitignore should include '*.env' and '!*.env.example' → Add '*.env' and '!*.env.example' to .gitignore.`
  Anything grepping that output has to move with it — match on the stable `code` slug rather
  than on message prose, which stays review-owned and may be reworded. `sync --check` moves
  from its `ok: <path>` / `would update: <path>` lines to the same envelope; `sync` in write
  and `--dry-run` modes keeps its `updated:` / `would update:` action log unchanged. Exit codes
  are unchanged: the strict-capable checks return 1 for errors and strict warnings; `sync` keeps
  2 for a planning error against 1 for drift and has no warning/strict stream. Child-process
  detail remains available on stderr after failure, while only a line-safe Finding enters stdout.
- **D2 owner gate (C63):** the ledger now distinguishes `Pending` owner review, `Approved`
  work awaiting a landing commit, and `Verified` work with a recorded landing sha. Use
  `d2_ledger.py approve <id>` before landing and `verify <id> --commit <sha>` afterward;
  pre-commit checks warn only for still-pending entries.
- **The vendor matrix now separates Codex capability from Codex delivery (C39/N7).** The
  table reports shipped akmon support, so the measured raw-harness route-level deny remains
  explicitly unshipped while D5 is not wired. Host-delivered Codex cells carry a `†`, and the
  note under the table records what the ordinary persisted, non-bypass path on codex-cli 0.149.1
  requires: a `[projects."<abs root>"]` entry for that exact root
  (trust does not inherit from an ancestor) plus a current `trusted_hash` per entry. Nothing
  in akmon changes — the claim does. Consumer-actionable half: a `sync` that changes an
  approved entry, *including a `matcher` its commands do not touch*, voids that group's
  approval, and the entries then report `enabled: true` while running nothing, silently.
  Re-approve with `/hooks` after every bump; the step is now in the package-mode procedure
  ([BOOTSTRAP](BOOTSTRAP.md) §F) as well as the mounted one. `akmon verify` still does not
  inspect that host state ([N7 evidence](meta/reviews/n7-codex-hook-delivery-20260825.md)).

### Migration
- **`registry.json` second-opinion keys moved (C57).** `second_opinion.cli` is now
  `second_opinion.harness` and `second_opinion.invoke` is now `second_opinion.operation`; both
  refer by name into the single command owner in `bin/runtime.py`, which spells the executable
  and the operation prefix. The ownership is that narrow on purpose: `model_flag` and `report_dir`
  stay in the registry and are unchanged, and `routing.second_opinion_command` still appends the
  model flag and the prompt after the prefix, because a model pin is policy rather than a fact
  about how a vendor's CLI is invoked. A project that overrides
  either key in `<AITNA_ROOT>/model-routing.json` must rename it. Because the change moves
  `registry_hash`, **every consumer's local model-routing config goes stale**: re-run the
  routing initializer (`python3 <tree>/tools/model_routing/init.py`) after the bump — the
  SessionStart hook reports the staleness until you do.
  - **A project routing overlay carrying the retired `cli`/`invoke` keys is now refused, not ignored.** The overlay is deep-merged *over* the shipped registry, so the retired pair does not displace `harness`/`operation` — it sits beside them and the config looks complete while stating one command twice. `verify` names the overlay file and the vendor. **The initializer does not fix this for you** — the overlay is hand-owned input it reads, not an artifact it writes. Edit `<AITNA_ROOT>/model-routing.json` by hand: delete the `cli` and `invoke` keys from each `second_opinion` object and leave the rest of it alone. The merge is recursive, so an overlay never replaces a whole object — `harness`, `operation` and `report_dir` are inherited from the shipped registry unless the overlay deliberately overrides one, and copying them in creates a local pin that silently stops tracking akmon. Keep only the values you mean to override, *then* re-run the initializer to regenerate the local config against the new `registry_hash`.
- **Breaking v0.4 consumer realign:** put the direct phrase `delegation is the default`
  in the root `AGENTS.md` akmon block, run `akmon sync`, then `akmon verify --strict`.
  A nested `@.../_common.md` line remains a pointer for compatible harnesses but does not
  deliver load-bearing instructions to Codex.

### Fixed
- **On Codex, a renamed file is now seen at its destination, not only at its source (C67).**
  `apply_patch` spells a rename as `*** Update File: <source>` followed by
  `*** Move to: <destination>`, and akmon's patch-path extraction read the
  `Add|Update|Delete File:` lines only. A file **moved into** a path a consumer lists in
  `[d2_ledger] sensitive_paths` — or into planning or code territory — therefore drew no
  advisory at all: the reminder was skipped in silence, since a hook with nothing to say and a
  hook that cannot see the path both print nothing. All three path-keyed PreToolUse advisories
  (role-on-code, analysis-guard, d2-ledger-reminder) now run over both endpoints of a rename.
  The rename literal is measured on codex-cli 0.149.1, not guessed
  ([N1/F4 evidence](meta/reviews/n1-f4-codex-timeout-20260825.md)); it was rare enough that
  zero of 345 recorded real `apply_patch` calls contained one, which is why it went unseen.
- **Model-routing recovery names a tree that exists in package mode (C37).** The SessionStart
  status line and the "routing needs initialization" instruction both told the session to run
  `python3 <AITNA_ROOT>/akmon/tools/model_routing/init.py` — a path a package-mode consumer does
  not have, so the one instruction that unblocks a stale or missing routing config was
  unusable there. Both now name the mounted tree in a mounted project and the materialized
  `<AITNA_ROOT>/.akmon/` tree in an ordinary package-mode project. **Known C69 gap:** hook-core
  still chooses by directory existence, so a stale mount left beside a package-mode record wins
  until the recorded-mount owner is locked and implemented.
- **`.akmon.toml` inline comments no longer end up inside the value (C37).** Three readers
  parsed that file and all three kept a trailing `# comment` as part of the value.
  `read_akmon_toml`'s pre-3.11 fallback made the exact shape BOOTSTRAP §C documents
  (`runner = "poetry run pytest"  # optional`) yield a different `[test].runner` on a 3.9/3.10
  host than on 3.11+, and the release check would have run the comment as part of the command.
  The two narrow mount readers — the CLI's dispatch and the model-routing initializer's tree
  resolution — read `mount = "package"  # …` back as `package"  # …`, i.e. not `package`, so a
  stale mount directory shadowed the very pin that field exists to protect. A quoted value now
  ends at its real closing quote in all three (a `#` inside it stays data, and `\"` is an escape,
  not the end of the string) and a bare value is cut at the first `#`, matching `tomllib`.
- **Model-routing init works without a mounted tree (C37).** `tools/model_routing/init.py`
  resolved its registry at `<AITNA_ROOT>/akmon/tools/model_routing/registry.json`, which does
  not exist in mount mode `package` — the attach step crashed there. It now resolves the
  standard tree the same way `bin/sync.py` does (the mount for mounted modes, its own tree
  otherwise, with the recorded `mount` field deciding so a stale mount directory cannot shadow
  a package-mode pin), and finds the project root through `<AITNA_ROOT>/.akmon.toml` as well as
  through the mount.
- **The version-skew notice stops firing on every command (C61).** In a mounted consumer the
  recorded pin is `git describe --tags` (`v0.3.0`) while the CLI's own version is PEP 440
  (`0.4.0.dev0`), so a raw string comparison never matched: the notice printed on every `akmon
  sync` / `akmon verify`, and rendered the pin as `vv0.3.0`. The comparison now normalizes the two
  recorded spellings — a leading `v`, and a `git describe` distance — before comparing; a tree
  that is *past* the tag the CLI matches gets its own distinct notice instead of a mismatch claim;
  and both notices print each version as it was recorded. A PEP 440 pre/post/dev segment is
  deliberately still a different version rather than another spelling of the same one.
- **The `TASKS.md` status check reads the status field (C65).** `verify.py` searched the whole
  entry line for `active|blocked|deferred|done`, which cannot fail on the defect it names: an
  entry whose *prose* contained "blocked" passed with any status text at all, and one whose prose
  contained "done" was reported as needing archiving. Both directions are fixed — the check now
  reads the third `·` field, an indented note under an entry is no longer held to the entry
  grammar, and both warnings name the offending ids instead of only counting them. A consumer
  whose `_aitna/TASKS.md` carries free-form statuses will see a new warning naming them; the
  accepted form is one of the four status words, optionally followed by a qualifier —
  `blocked (after C51)`.
- **Release check subject scoping (C9):** `--subject akmon` now runs upstream self-CI and meta tests from the akmon source root instead of running consumer-only `sync`/`verify` against the wrong layout.
- Package-mode hooks now discover the project from nested working directories through
  `<AITNA_ROOT>/.akmon.toml`, use `<AITNA_ROOT>/.akmon` as their runtime root, and
  materialize the stdlib model-routing/D2 tool dependencies used by wired hooks.
- **The Codex advisory hooks now actually fire (C48 + C47).** `role-on-code`,
  `analysis-guard` and `d2-ledger-reminder` had produced no output in any Codex session since
  they were wired, for two independent reasons: `codex_adapter.file_paths` looked for the patch
  body under a `patch` key that the measured 0.146.0 payload does not send (it puts it in
  `tool_input.command`), and the planning-doc/code path predicates matched only absolute paths
  while patch bodies carry repo-relative ones. Both are fixed and verified against the payload
  captured from codex 0.146.0. An already project-trusted consumer whose affected hook entries
  are approved will start seeing these reminders where it previously saw none — no akmon
  configuration change is needed. Codex host trust remains separate: a fresh consumer must trust
  the project and approve its hooks, and any later `sync` change to an approved `.codex/hooks.json`
  entry invalidates the affected approval and requires review and re-approval through `/hooks`
  ([N7 evidence](meta/reviews/n7-codex-hook-delivery-20260825.md)). New failure signal: when an edit
  matcher fires and no path can be read from the payload, the hook says so on stderr instead of
  staying silent, so the next vendor payload change is visible rather than inert. **Known 3.9
  gap:** the package declares `requires-python >=3.9`, but `hooks/codex-hook.py` evaluates a
  PEP 604 union (`HookResult | None`) at **import** time, which needs 3.10 — so on a 3.9 host
  every wired Codex entry (these three plus `session-start`) exits before any advisory runs. The
  paragraph above holds as written on 3.10+; a 3.9 consumer sees no Codex hooks at all until the
  floor is repaired or the declared floor is raised.
- **Codex malformed-edit diagnostic loudness (C36(c)/D2-21):** the defect signal is emitted
  once across the three handlers for each reliable session/tool-use pair, repeats for a later
  bad event, and repeats fail-visible when either identity is unavailable. Marker lifecycle
  remains open under C36(a), so this item is not an exactly-once-per-session guarantee.
- **Codex PreToolUse matcher now names routes, not spellings (C49).** The generated
  `.codex/hooks.json` matcher changes from `Edit|Write|apply_patch` to **`Bash|apply_patch`**:
  measured on codex 0.146.0, the first three are aliases for one patch call, while the shell
  matches as `Bash` and was named by nothing — so every mutation made through the shell
  (`apply_patch` heredoc, `sed -i`, redirection, `python3 -c`) was invisible to all wired
  hooks. Consumers re-run `sync` to pick the new matcher up — on Codex that re-sync is a
  matcher-only change to an already approved group, so it flips every `PreToolUse` entry in that
  group to `modified`, and those entries stay inert until re-approved through `/hooks`
  ([N7 evidence](meta/reviews/n7-codex-hook-delivery-20260825.md)). A Bash command is classified as an
  edit only when a recognized `apply_patch` invocation carries a valid patch envelope; this
  path depends on the C47/C48 fixes above. Every other Bash call stays unclassified. The three
  separately launched path-keyed hooks share one atomic marker, so exactly the first process emits
  one combined stderr diagnostic per reliable session id that the route **may mutate files unseen**;
  it repeats if no id is available. Whether Codex shows that stderr to the owner is unverified.
  The exact heredoc route is now observable to advisories;
  the original hard-deny bypass remains open because these hooks are advisory and no matcher
  makes a denied effect unbypassable.
- **Overlay brief validation (C50):** per-agent `briefs` keys now match agent names
  case-insensitively and treat `-`/`_` as the same notation, so an unmigrated consumer overlay
  survives the `k-*` → `k_*` rename. An unknown, colliding, or malformed key is now a hard
  error: `init.py` writes nothing and exits 2, and the routing hook refuses a rebind. The
  deliberate cost is that generated agents and their model pin stay stale until the broken
  overlay is fixed, instead of being regenerated after silently dropping project instructions.

## v0.3.0

### Added
- **Model routing — capability tiers** ([MODEL.md](MODEL.md) §10, ADR 0004): task-kind →
  tier matrix and per-vendor semantic selection policy as data in
  [`tools/model_routing/registry.json`](tools/model_routing/registry.json) (project overlay:
  `<aitna-root>/model-routing.json`, deep-merged; may add per-agent `briefs`); the
  idempotent [`tools/model_routing/init.py`](tools/model_routing/init.py) computes the
  tier→model binding relative to the orchestrating model and generates the `k-*` subagent
  definitions (`.claude/agents/`, committed) plus `.claude/model-routing.local.json`
  (per-user — consumers gitignore it, with `.claude/model-routing.log`).
- **Two routing hooks**, wired by `sync.py` for Claude Code:
  [`hooks/model-routing.py`](hooks/model-routing.py) (SessionStart — binding status line /
  init instruction, weak-orchestrator warning) and
  [`hooks/delegation-log.py`](hooks/delegation-log.py) (PreToolUse `Task|Agent` — one TSV
  log line per delegation, zero token cost).
- **Tier floor guardrail** ([guardrails/_common.md](guardrails/_common.md) § Route by task
  kind) and one-line tier annotations in the triad roles and the review/code/design flows.
- **Delegation-nudge hook**: [`hooks/delegation-nudge.py`](hooks/delegation-nudge.py)
  (PreToolUse, combined matcher `Bash|Edit|Write|MultiEdit|Task|Agent`) counts consecutive
  orchestrator edit/shell calls since session start or the last subagent delegation and,
  past a threshold (default 10, env `KEYSTONE_DELEGATION_NUDGE_THRESHOLD`), injects an
  advisory reminder to route by task kind to the `k-*` delegates — once per drift episode;
  a subagent delegation resets the counter and re-arms the reminder. Never blocks. Wired by
  `sync.py`.
- **Statistics digest** (`stats-digest` skill + tool, the on-demand counterpart to the
  zero-token delegation log): [`tools/model_routing/stats.py`](tools/model_routing/stats.py)
  parses the delegation log and the current session transcript (orchestrator + per-subagent
  token usage), queries the Claude OAuth usage API for remaining session/week budget
  (degrades to `unavailable` offline), writes the full report to `.claude/stats/` and prints
  a compact digest; [`skills/stats-digest/SKILL.md`](skills/stats-digest/SKILL.md) drives it
  on the owner's chat trigger and gates learn-loop recommendations on owner confirmation.
  Known limit: the delegation log is append-only across sessions, so delegation counts span
  the log, while token stats are per-session.
- **Cross-vendor second-opinion runner**:
  [`tools/model_routing/second_opinion.py`](tools/model_routing/second_opinion.py) runs an
  advisory review at a verify/align gate through the registry-selected CLI. Claude-led sessions
  default to Codex (`codex exec`); Codex-led sessions default to Claude
  (`claude -p --output-format text`). The runner writes the full report under the configured
  per-vendor report directory and prints a digest; it is not a blocking hook.
- **Onboarding surface**: README rewritten as one coherent top-level document — why akmon
  exists (the failure modes it counters + the two-budget goal function), the three axes in
  brief, the "How a session runs" walkthrough (orchestrator + `k-*` smiths flow diagram,
  routing-is-data, hooks), an annotated repository map, the consumer lifecycle
  (attach → stay current → learn-loop give-back), and start-here pointers for consumers
  (BOOTSTRAP) vs akmon developers (meta/); [MODEL.md §11](MODEL.md#11-principles--the-shape-in-seven-lines)
  names the seven design principles (index lines linking each fact's owner);
  [`examples/gate-anatomy.md`](examples/gate-anatomy.md) walks a real gate end to end
  (yardstick → zone fan-out → synthesis → gate-pack → clean-context audit → validate-loop
  evidence), sourced from the 2026-07-05 self-audit.
- **Privilege-escalation guardrail** ([guardrails/_common.md](guardrails/_common.md) §
  Privilege escalation): `hooks/hook_core.py::privilege_escalation_guard_result` denies any
  Bash command containing `sudo` outright — no ask, unconditional — composed into the same
  PreToolUse entrypoint as the commit guard (`git-commit-guard.py`, and the Codex
  `git-commit-guard` hook mode). A permission boundary (a root-owned file, a denied write) is
  something the agent reports to the owner, never routes around.

### Changed
- **Guardrail posture in unattended sessions (C31/D2-11)**: a hook-forced `ask` was found to
  be a silent no-op in a Claude Code background/child session — no block, no prompt. The
  commit guard (`git-commit-guard.py`) and the delegation nudge's hard rung
  (`delegation-nudge.py`) now escalate any `ask` to a hard `deny` whenever the PreToolUse
  payload's `permission_mode` is not the interactive `default` (a missing field escalates
  too — treated as the worst case). Consumers may see a `deny` where they previously saw a
  silently-passed `ask` in `acceptEdits`/`plan`/`dontAsk`/`bypassPermissions` sessions or
  automation that omits `permission_mode`.

### Migration
- Re-run `bin/sync.py` (wires the two new hooks into `.claude/settings.json`), run
  `tools/model_routing/init.py`, and add `.claude/model-routing.local.json` +
  `.claude/model-routing.log` to the project `.gitignore`.
- To use Codex-led routing or Claude second-opinion review, keep the OpenAI and Anthropic
  selection-policy/second-opinion entries in `tools/model_routing/registry.json` or override
  them in the project overlay (`<aitna-root>/model-routing.json`). Concrete model aliases come
  from local discovery / `--available`, not from committed registry data.

### Fixed
- **README `develop/` links** (README.md:52,54) pointed at a directory that had been renamed
  to `meta/`; MODEL.md §10 restated the pre-ADR-0006 selection policy ("reasoner = highest")
  against the registry's dynamic `reasoner: "orchestrator"` — both now match the tree/registry.
- **`bin/verify.py` / `meta/self_ci.py` drift (C26)**: the same reasoner-policy drift as above
  had also reached the *checker code*, not just docs — `_check_model_routing_registry` asserted
  `reasoner == "highest"` only, false-erroring on the registry's own ADR 0005/0006 dynamic
  default (`"orchestrator"`); `self_ci.py`'s fixture copy-list separately omitted
  `second_opinion.py`. Both made every verify-touching CI leg deterministically red on a clean
  tree. Now accepts `reasoner` in `("orchestrator", "highest")`, copies `second_opinion.py` into
  the self-CI fixture, and a new test asserts the checker passes against the *live* registry
  (not just a fixture that happened to still say `"highest"`).
- **Codex hook output contract**: `hooks/codex-hook.py` now reads the Codex SessionStart `cwd`
  payload and `hooks/codex_adapter.py` serializes hook results as `hookSpecificOutput` JSON, so
  Codex CLI 0.142 accepts the generated SessionStart hook instead of reporting hook failure.

## v0.2.1

### Added
- **Integration record `<AITNA_ROOT>/.akmon.toml`** ([BOOTSTRAP.md](BOOTSTRAP.md) §C) — a
  machine-readable (TOML) record of the akmon version a project sits on, plus its pinned test
  env. The agent writes it on attach/realign (step 6); `verify.py` validates it; the bump procedure
  diffs it against this CHANGELOG to compute which `Breaking`/`migration` entries still need
  verifying. Read via `tomllib`, with a stdlib line-parser fallback for host Python < 3.11.
- **Version-windowed delta-check** in the bump procedure ([BOOTSTRAP.md](BOOTSTRAP.md) "Pull the
  latest shared layer") — `from` = recorded version, `to` = target; walk only the `Breaking`/
  `migration` lines in `(from, to]` as a checklist.
- **Optional `[test].runner`** in `.akmon.toml` ([BOOTSTRAP.md](BOOTSTRAP.md) §A5/§C) —
  attach pins the project's existing test env (its own manager, or a `_aitna/.venv` only when the
  project has no Python env) and `release_check` runs it verbatim instead of guessing. Absent →
  discovery fallback, so projects without the field are unaffected.

### Changed
- **`verify.py` validates `<AITNA_ROOT>/.akmon.toml`** on a consumer (where akmon is a
  mounted submodule); skipped when run against the akmon repo itself. A *missing* record is a
  non-gating note (does not fail `--strict`); only a *present but malformed* record (missing
  required keys) is an error. Adopting the record is optional — a realign writes it.

### Fixed
- `verify.py` now checks `roles/review.md` exists (it was added as a role but left out of the
  required-files list).
- `tools/release/release_check.py` test-runner resolution: it now prefers the dev-layer venv
  (`_aitna/.venv`), invoked as `<venv>/bin/python -m pytest` (not the `bin/pytest` console script,
  whose baked-in shebang breaks on a relocated venv); and when it falls back to `uv` it installs
  pytest on the fly (`uv run --with pytest`) — a bare `uv run pytest` ran in an ephemeral env
  without pytest and failed the release check on hosts with `uv` but no pytest on PATH.

## v0.2.0

### Added
- **`release` skill** ([`skills/release/SKILL.md`](skills/release/SKILL.md)) — the first akmon
  skill; the agent-facing how-to for the release role (frame → collect → classify → gate → verify →
  handoff), with the D5 stop boundary.
- **`tools/release/release_check.py`** — the first akmon `tools/` entry; a propose/prepare release
  tool (`--state` / `--check` / `--plan`), subject-parameterized `--subject {akmon,package}`
  (pin-bump deferred, T18). Runner-resilient verify (`uv` → `.venv` → system `pytest`); never
  commits/tags/pushes. Driven by the `release` skill (T14).
- **`tools/README.md`** — the akmon SHARED `tools/` index, with the `tools/` vs `bin/` boundary.
- **`meta/bin/validate.py`** — the dev-layer validator (counterpart to `bin/verify.py`): checks
  akmon's own tree, runs the synthetic-fixture self-CI, and runs the unit tests. A consumer
  never runs it; akmon runs it in-tree. (C7)
- **BOOTSTRAP dev-layer venv** — attach (§A step 5) now provisions a `_aitna/.venv` and installs
  the agent-tooling deps (pytest) **when the project language is not python/mixed**, so the
  akmon-dev validator and any future deps-bearing tool can run on a non-Python project. The
  venv lives outside the submodule, is gitignored (§D), and is never needed for the stdlib-only
  consumer CI checks. (C8)

### Changed
- **Sharper SessionStart role hint** — the active-agent reminder now carries the DEVELOP routing
  discriminator (decompose → review · construct → architect · realize → engineer) up front, when
  the project has dev agents, instead of a vague "pick the one the task calls for". The agent gets
  the picking rule at session start, not only after a code/planning edit. OPERATE-only projects
  keep the generic line. (A10)
- **Configurable dev-layer root** — `_aitna/` is now the *default*, not a hard-coded literal. A
  project may relocate the dev layer by declaring **`AITNA_ROOT`** (a project-root-relative path,
  e.g. `tools/ai`); akmon then mounts at `<AITNA_ROOT>/akmon` and `sync.py` / `verify.py` /
  the hooks derive every path (generated pointers, hook commands, the do-not-edit banner) from it.
  Unset → `_aitna`, byte-identical to before. Documented in MODEL.md §2 + BOOTSTRAP §A. (A4)
- `verify.py` gains `check_akmon_gitignore` — warns when the akmon submodule has no
  `.gitignore` ignoring `__pycache__/` (so a release commit cut from the submodule stays clean).
- **USE/dev verify split** — `bin/verify.py` is now the **USE-contract verifier only**: it
  dropped the akmon-self layout/CI requirements and no longer references the dev layer at all.
  akmon-self checks moved to the new `meta/bin/validate.py`. Consumer CI is unchanged
  (`sync.py --check` + `verify.py --strict`). (C7)
- **Stricter USE-surface isolation** — the develop-boundary check became
  `check_use_surface_isolation`: it now scans the *whole* USE surface (incl. `skills/`, `tools/`)
  and fails on **any mention** of the dev layer — numbered `ADR ####` / `ROADMAP O#` citations and
  dev-tree paths in links *or* inline code — not just markdown links. Generic vocabulary ("file an
  ADR") stays legal. (C7)
- **Terminology** — the third axis is now consistently called **Archetype** (was "Project type")
  across `MODEL.md`, `ARCHETYPES.md`, `BOOTSTRAP.md`, `README.md`.

### Breaking
- **Dev layer renamed `develop/` → `meta/`.** akmon's own development artifacts (CONCEPT,
  decisions/ADRs, ROADMAP, design, reviews, tests, self_ci) now live under
  `_aitna/akmon/meta/`. The rename avoids colliding with the **DEVELOP** role/mode of the
  model. *Migration:* a consumer that hardcoded any `_aitna/akmon/develop/...` path (CI, docs,
  scripts) must repoint it to `meta/...`. CI that ran `develop/self_ci.py` / `pytest develop/tests`
  should drop them (those are akmon-self checks, run via `meta/bin/validate.py`, not a consumer
  concern). (C7)

## v0.1.0

First tagged release of the akmon standard — the initial reviewed baseline consuming projects
pin to. Everything below is the contract a new consumer adopts on first mount; there is no prior
version to migrate from, so the `Breaking` note applies only to projects that mounted a pre-tag
akmon and still carry old-style skill frontmatter.

### Added
- **`release` role** + [release pipeline](pipelines/release.md): a subject-parameterized DEVELOP
  role (package / akmon tag / pin bump) with a two-mode cycle (lightweight cut · periodic
  cadence). Locked in [ADR 0001](meta/decisions/0001-release-and-roles-model.md).
- **`learn` role** ([learn](roles/learn.md)): the learn loop now has an owning role wrapping the
  `memory-distill` + `learning` pipelines.
- **`decisions/`** — akmon now keeps its own ADRs (this is where standard-level decisions land,
  parallel to a project's `docs/dev/decisions/`).
- **`CHANGELOG.md`** (this file) and the `v0.x.y` versioning convention.
- **Skill contract** — `SKILL.md` frontmatter now requires `name` / `description` / `when_to_use`
  / `owner`, checked by `verify.py`.

### Changed
- `verify.py` is stricter: validates the cross-agent pointer contract (vendor pointers import
  `AGENTS.md`; AGENTS.md stays hand-reviewed, not generated) and the skill contract above.
- `sync.py` now prunes orphaned banner-marked generated skill stubs; `verify.py` flags them.
- CI runs the akmon self-CI fixture (`bin/self_ci.py`) alongside sync/verify/pytest.

### Breaking
- **Skill frontmatter** — consuming projects with existing `skills/*/SKILL.md` must add the
  `when_to_use` and `owner` fields (and ensure `name` matches the skill directory), or
  `verify.py --strict` will fail. Migration: add the two fields to each skill's frontmatter.
