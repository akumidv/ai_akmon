# The conformance corpus (C101)

The language-neutral behavioral spec both permanent implementations of akmon must pass
(ADR 0020 D01/D03; design [node-consumers.md §5](../design/node-consumers.md#5-conformance-corpus-d03--the-spec)).
The corpus lives at the **process boundary**: it invokes a hook, CLI command, tool or probe
exactly the way a harness or an owner would, and compares the normalized observable
(stdout, stderr, exit code, written files) with the recorded expectation. Where the corpus
is silent, the Python implementation is the reference, and the resolution becomes a scenario.

## Layout

| Path | Role |
|---|---|
| `scenarios/<area>/*.toml` | one scenario per file; areas: `hooks`, `cli`, `tools`, `units` |
| `fixtures/<name>/` | static consumer-project files a scenario's project is copied from (`base`) |
| `fixtures/attach/<layer>/` | the files a `native` attach lays over the base: `package` (both package modes), `python` (the Python carrier), `node` (C104: the record, with `ecosystem = "node"`, and the `package.json` dev pin); and a node `mount` attach: `node-mount` (C129: the record with `mount = "submodule"` and `ecosystem = "node"`, a `package.json` without an akmon pin, the `AGENTS.md` profile imports and the CI that runs the mount's JavaScript CLI) |
| `fixtures/tree/` | corpus-owned stand-ins for the standard tree's prose documents (see the snapshot) |
| `units/<name>.toml` | shared unit tables (inputs + expected answers) for a function whose answer a JS port cannot get for free: either a **stdlib gap** (`shlex`, `fnmatch`, `json.dumps`, float spelling) or a **shared data-driven module** whose answers are values (`runtime`, `check_runner`), or a **module that acts on files and the environment** (`markers`, `materialization`), whose table describes a world — a scratch directory, environment variables — that the probe builds, replays against and removes; `routing` (C104) is both kinds at once and too large for per-family mouths, so its table is **generic**: a row names a public function, its JSON arguments and the world it runs in, and pins the whole answer plus the files the call leaves (the row format is the block comment above `probe_routing` in `probe.py`); the three hook tables (`hook_core`, `claude_adapter`, `codex_adapter`, C104 pass 2) use that same mouth over `hooks/*.py` and `js/hooks/*.mjs` — on the JS side the module's `data` (the lazy bundle of `hook_data.mjs`) is handed over as the first argument of the exports that read a data file or a marker — and add the `{{tree}}` and `{{core:<key>}}` tokens, sequences (`steps_json`), links and a working directory to the world |
| `coverage.toml` | the coverage gate's **exceptions**: ecosystem ownership, exemptions, reviewed dynamic sites |
| `pairing.toml` | the pairing gate's two lists: `[[exempt]]` — a `.py` whose port is outstanding, with reason and owning task — and `[[stub]]` — a `js/` counterpart that only announces it |
| `normalize.py` | normalization v2 — the other half of the spec (tokens and rules) |
| `corpus.py` | scenario loading, the snapshot, fixture materialization |
| `runner.py` | executes scenarios against one implementation; `--record` reseeds expectations |
| `coverage.py` | the coverage gate: derives the population from the source and checks it |
| `pairing.py` | the pairing gate: every consumer-executable `.py` paired under `js/` or exempted, with no exemption outliving its port or crediting a stub |
| `probe.py` | the Python implementation's mouth for unit tables |
| `probe.mjs` | the JS implementation's mouth for unit tables (same contract: the `{"ok","failed"}` document, exit 1 on a miss) |
| `fuzz.py` | gate 4, the differential hook fuzz (C111): seeds, mutations, the two-implementation comparison, draft scenarios |
| `fuzz.toml` | the fuzz run's known divergences: signatures, each naming the `DIVERGENCES.md` row that accepts it |
| `fuzz_record.py` | records real hook payloads (`tee`) and scrubs them into `fuzz/seeds/` (`scrub`); how to record is in `fuzz/seeds/README.md` |
| `fuzz/seeds/` | recorded hook payloads the fuzz run mutates beside the scenarios' (scrubbed, owner-reviewed) |

## Ecosystems and attaches

ADR 0020 D02, as its C129 amendment narrows it: the mounted modes (`submodule`, `vendored`,
`subtree`) run the Python implementation unless the record names `ecosystem = "node"`, and the
JavaScript implementation covers Node package mode and those Node mounts. A scenario says both
what it is spec for and how its consumer is connected:

- `ecosystem = "shared"` — spec for both implementations; `"python"` / `"node"` — one only.
- `[fixture] attach = "native"` (default) — the implementation's own package mode: the base
  fixture plus the `package` layer (a package-mode `AGENTS.md` block) and the ecosystem's carrier
  layer (Python: the record with `mount = "package"`, the `pyproject.toml` dev pin (written by `corpus.py`, as the launcher is), CI calling
  `uv run akmon`, and the `.venv/bin/akmon` launcher the runner writes). Hooks run through the
  launcher (`akmon hook <name>`), the way package wiring calls them. Node: the record, the
  `package.json` dev pin, and `node_modules/akmon` linked to the tree (the runner makes the
  link); hooks run as `node node_modules/akmon/js/hooks/<name>.mjs`, the spelling the wiring uses
  (ADR 0020 D05). The node project is synced by the JS `sync` itself (C105), so the hooks and the
  CLI commands under test read a project the implementation wrote, as a consumer's does; its
  record names `ecosystem = "node"`.
- `attach = "mount"` — `<AITNA_ROOT>/akmon` links the snapshot, in either ecosystem (C129), so a
  mounted scenario may be `shared`, `python` or `node`. Python: the base fixture is a
  Python-mounted consumer already, and hooks run as `python3 <tree>/hooks/<name>.py`. Node: the
  `node-mount` layer is laid over the base, the CLI runs from the mount as
  `node <AITNA_ROOT>/akmon/js/akmon/cli.mjs` and hooks as `node <AITNA_ROOT>/akmon/js/hooks/<name>.mjs`
  (the link read unresolved, as the consumer's wiring names it).
- `attach = "none"` — nothing connected (usage errors, `init` onto a bare project).

A shared scenario whose output carries lines of a code an ecosystem owns (the standard-tree
layout, the carrier's pin, the launcher — `coverage.toml [ecosystem]` whole-code entries)
cannot pin that output whole, so it records `findings` instead of `stdout`: every finding line
except those codes'. Those lines are pinned by the owning ecosystem's scenarios, recorded with
their exact `stdout` (e.g. `cli/verify-package-healthy` is the Python carrier's full report).

## Scenario schema

```toml
id = "area/name"          # must equal the file path under scenarios/
ecosystem = "shared"      # shared | python | node — runs on the impl whose scope includes it
kind = "hook"             # hook | cli | tool | unit
covers = ["hook:role-on-code", "code:agents.block-anchors"]   # claims; each must name a derived item

[fixture]                 # omit for the defaults (base, native, synced)
name = "base"             # fixtures/<name>/
attach = "native"         # native | mount | none (above)
files = { "rel/path" = "content" }   # written over base + attach layers ({{version}} materializes)
remove = ["rel/path"]               # base/layer files deleted before the run
branch = "main"                     # the fixture is a fresh git repo on this branch
warmup = "after"                    # the impl's own sync: "after" the files (a synced project; native
                                    # default), "before" them (synced, then the files break it), "none"
git = true                          # false: no repo at all (the not-a-work-tree scenario)
repo = false                        # build a local standard-tree git repo tagged v<version> (for --repo)
tmp_files = { "name" = "content" }  # seeded into the run tempdir (hook markers and counters)
tree_files = { "rel/path" = "…" }   # scenario-local override of the snapshot (tree-side breaks)
tree_remove = ["rel/path"]          # snapshot paths deleted from that scenario-local copy
tags = ["v1.1.0"]                   # git tags on the fixture's baseline commit (release checks)

[env]                     # environment overrides for the process under test
AITNA_ROOT = "_aitna"

[run]
script = "role-on-code"   # hook: the hook name (python: hooks/<script>.py | node: js/hooks/<script>.mjs)
args = []                 # hook: extra argv
payload = { ... }         # hook: the stdin JSON document (tokens materialized)
payload_json = '''{…}'''  # hook: the same document as JSON text, for a nesting TOML refuses
                          # (tomllib: a key of more than 1000 parts, M152); not with payload
argv = ["sync", "--check"]# cli: console argv; tool: argv after the tool path
tool = "model_routing/init"  # tool: tools/<tool>.py (C108: `akmon tool <tool>` in both)
probe = "versions"        # unit: probe subcommand
table = "versions.toml"   # unit: units/<table>

[expected]
exit = 0
stdout = "…"             # exact, normalized — or stdout_json (hooks) — or findings (above)
findings = ["OK …", …]    # the shared finding lines, in output order
stderr = "…"             # exact, normalized — or stderr_contains
stderr_contains = ["…"]   # only for text an argument parser owns (usage banners); hand-written
[expected.files]         # rel path -> exact normalized content, or ref:tree:<path>
"rel/path" = "content"
file_absent = ["rel/path"]
[expected.stdout_json]   # hook: parsed-JSON equality with normalized string leaves
```

A scenario that asserts nothing beyond its exit code is refused. An unseeded scenario (no
`[expected]`) is a red state the loader names loudly. A `code:` claim must appear as a finding
line of the actual stdout (a line match, not a substring). A marker a scenario seeds in
`tmp_files` names the implementation's marker file, so the marker naming (`common/markers.py`)
is part of the spec a port mirrors.

## Normalization v2

A scenario file is written normalized already: it contains the tokens. The runner maps every
observable into the same form before comparing; **anything a rule does not normalize must
match exactly**. Rules, in normative order (see `normalize.py`):

1. **Hook commands** keep their anchor and the hook, however the ecosystem spells the call:
   `python3 "<anchor>/…/hooks/<name>.py"`, `node "<anchor>/…/hooks/<name>.mjs"` and the launcher
   `"<anchor>/<rel>" hook <name>` all become `{{hook <anchor> <name>}}` (raw and JSON-escaped),
   anchor `$CLAUDE_PROJECT_DIR` or `$(git rev-parse --show-toplevel)`. A command hanging from
   anything else is not collapsed, so an absolute path in shared wiring shows as a mismatch.
   The launcher's relative path is the Python carrier's fact, pinned by `hooks.launcher`.
2. **Tool calls** in package-mode spelling, `akmon tool <tool>` (the wheel) and
   `npx akmon tool <tool>` (the npm package), become `{{tool <tool>}}` (ADR-0020/D06). The mounted
   spelling (`python3 <mount>/tools/<tool>.py`) names the mount and stays as written, so a
   package-mode message that names the mount (the C77 class) is caught.
3. **Parser details** after `invalid JSON:` / `cannot be read as TOML:` up to the finding's
   ` → ` become `{{parse-error}}`: that a file failed to parse, and which, is spec; the
   parser's words are the implementation's.
4. **Paths**: mount → `{{mount}}`, tree → `{{tree}}`, project root → `{{root}}` (longest first;
   the mount path contains the root), run tempdir → `{{tmp}}`, the local standard repo → `{{repo}}`. On a node
   native run `<root>/node_modules/akmon` is `{{tree}}` too: that link is the tree the consumer runs, read unresolved.
5. **Point-in-time**: the running version → `{{version}}`; datetimes and `YYYYMMDD-HHMMSS`
   stamps → `{{ts}}` and bare dates → `{{date}}` **only for the run's own day(s)**. A date from
   any other day came from a fixture and is compared literally.

One token is spelled the other way, in the expectation rather than the output: **`{{ref}}`**, the
ref the running version names — `v{{version}}` for a final release, `main` for any other version
(`_init._tag_for_version` and its JS twin; "final" is `common/versions.py::is_final`). An output
that names that ref (an `npx …#<ref>` or `uvx …@<ref>` command, a `git subtree add … <ref>`) is
written with `{{ref}}` in `stdout`, `stderr`, `stderr_contains`, `findings` and `[expected.files]`,
so the scenario holds at a development version and at a release alike. No rule normalizes `main`
in the output — it means other things too. A `--record` keeps an expectation's own spelling while
the output still matches it, so a re-record does not drop the token; one that changed is written
out in full, and its `{{ref}}` is the reviewer's to restore. Where the ref changes more than a
word (a submodule attach pins the release tag, and at a development version finds none), the
scenario names its ref with `--ref` instead.

Changing a rule, or adding one, is a corpus version change: bump `NORM_VERSION` in
`normalize.py` and say what changed here. v2 (C101 review): rule 1 keeps the anchor and covers
the launcher (v1 erased the whole path and kept the launcher's relative path); rules 2 and 3
are new; rule 5 is limited to the run day. v3 (C108): rule 2 matches the `akmon tool` spelling of
both implementations instead of `python3 $(akmon path)/tools/<tool>.py`.

## Fixture model

- The **snapshot** (`corpus.SNAPSHOT_FILES` + the wired hooks + the `js/` tree carried whole via
  its derived list, `corpus.py::snapshot_js`) is the corpus-controlled standard tree: code, data
  and configuration are copied from the repository under test (including `src/akmon`, so a
  native consumer runs the snapshot's own CLI and it resolves the snapshot as its embedded
  tree); the **prose documents** come from `fixtures/tree/` stand-ins. The corpus
  pins behavior, not prose: with the real documents every guardrail edit (the always-loaded cap
  measures the imported guardrail) and every release (the healthy changelog check reads
  `## Unreleased`) would move the spec. A stand-in the snapshot does not list, or a listed path
  the repository no longer has, is refused.
- Every scenario run gets a fresh copy of the fixture, a fresh private tempdir (markers and
  counters land there, isolated from host state and each other), and a fresh git repo on the
  scenario's branch, committed once after the warmup — a synced consumer's sync output is its
  baseline, not a change.
- The `codex` binary is hidden from the process under test's PATH (self-CI's technique):
  `codex.host-trust` takes its absent-install skip, so the corpus never runs a live harness
  RPC. Its warn side is exempt in `coverage.toml`; live harness probes are N10's job.

## Gates

1. **Scope gate** — every scenario in the impl's scope (`shared` + its own tag) passes.
2. **Coverage gate** (`coverage.py`) — the population is **derived from the source** of the tree
   under test, never listed: commands from `src/akmon/cli.py` `_COMMANDS`, hooks and tools from
   their `__main__` blocks, unit tables from `units/`, and `code:<code>:<severity>` from every
   literal emission site (`self.ok|warn|error("code", …)`, `Finding("severity", "code", …)`).
   Evidence comes from each scenario's run and its recorded expectation lines, not from its
   claims. An item is covered only by a `shared` scenario unless `coverage.toml [ecosystem]`
   gives it to one ecosystem. `[exempt]` lists what no hermetic scenario can reach, `[dynamic]`
   the reviewed non-literal emission sites; an unlisted dynamic site, or an entry naming nothing
   derived, fails the gate. The runner runs it last.
3. **Pairing gate** (`pairing.py`) — every consumer-executable `.py` has its `.mjs` counterpart
   under `js/` at the mirrored path (design §4: `X/Y.py` → `js/X/Y.mjs`, the package mapping to
   the package — `src/akmon/cli.py` is `js/akmon/cli.mjs`), or an exemption in
   `meta/conformance/pairing.toml` with a reason and the owning task. The population is the five
   `CODE_ROOTS` (`coverage.py` owns the roots). The gate runs on a full corpus run, after the
   coverage gate, and fails like it does: a gap (`pairing.gap`) is an error, and so is an
   exemption that no longer says anything true (`pairing.stale`) — one covering no file, or one
   covering only files whose port has landed. A counterpart that is a placeholder rather than a
   port is named by a `[[stub]]` entry (its exact `js/` path, plus the task that replaces it) and
   is **not** credited as a port: the `.py` behind it stays exempt and still needs its own
   exemption, so an outstanding task cannot read as done. The exemption list shrinks as the port
   lands (C104 hooks, C105 CLI, C107 update, C108 tools), and the `[[stub]]` entry goes with it.
4. **Differential fuzzing** (`fuzz.py`, C111) — the hook payloads, mutated, through both
   implementations. The seeds are the `[run.payload]` (with the script, args, fixture and env) of
   every `shared` hook scenario, plus the recorded payloads in `fuzz/seeds/` (`<script>--<label>.json`,
   one JSON object each, on the base fixture; recorded only scrubbed of private content — the
   directory's README). A seed member nested deeper than 64 levels (a scenario may pin a payload
   thousands deep) is held as its raw JSON text, one leaf a mutation replaces whole. Each case applies one or more mutations, drawn from
   `random.Random("akmon-fuzz:<seed>:<index>")`, so a case is a pure function of the run's seed and
   its index and reruns alone (`--seed S --case I`). The primary kind cycles through every kind:
   value mutations (drop or add a key, a `__proto__` among the added ones; change a value's type;
   an empty or ≥ 64 KiB string; astral, U+FFFD, U+10FFFF, combining, RTL and BOM characters at a
   string's edges; a lone surrogate escape; control characters; numbers beyond 2**53 and 2**64,
   `-0`, `1e309`, `1.0`; a value nested up to 100 000 deep; `hook_event_name` / `tool_name`
   swapped among the seeds' values; `..`, absolute, spaced and trailing-slash paths in the path
   fields) and stdin mutations (invalid UTF-8 bytes, non-JSON text, truncated JSON, empty or blank
   stdin, duplicate keys). Half the cases spell non-ASCII text as raw UTF-8, half as `\u` escapes.

   Both implementations run each case on the same fixture at the same path: a seed's fixture is
   materialized (and synced) once per implementation, and a pristine copy is restored before every
   case, with a fresh tempdir. Compared: the exit code, stdout (as parsed JSON when it parses,
   normalized like `stdout_json`), stderr, and the files the hook created, changed or removed under
   the project (`.git` aside) and the tempdir, by path and normalized-content hash. A difference is
   **known** when an entry of `fuzz.toml` matches it — script globs, the streams allowed to differ,
   a mutation-label glob, an optional stdin regex and host condition — and that entry names the
   `DIVERGENCES.md` row accepting it (the loader refuses an entry naming no row: a difference is
   accepted here only after it is accepted there); anything else is **divergent**, and the run
   exits 1.

   A divergent case becomes a **draft** scenario under `--emit DIR` (default: a fresh temp dir the
   summary prints), never in `scenarios/`: the corpus format (`kind = "hook"`, `ecosystem =
   "shared"`, the seed's fixture and env, the mutated payload, the Python result as `[expected]`),
   headed by a DRAFT comment with the node result and the reproduce command, plus a `[fuzz]` table
   (seed, case, mutations, the differing streams, the exact stdin in base64). A stdin the schema
   cannot spell (raw bytes, a `null`, a raw number token, a surrogate, an integer beyond int64) gets
   no `[run.payload]`, and the header says so. The draft then follows the Seed protocol: a human
   reads the Python result as a spec, and either fixes the twin that is wrong and keeps the draft
   (header and `[fuzz]` removed) as a scenario, or records a `DIVERGENCES.md` row plus a `fuzz.toml`
   entry and deletes the draft. Removing the `[fuzz]` table is the reviewer's mark: the corpus
   loader (every runner, gate and fuzz run reads scenarios through it) refuses a scenario file that
   still carries one, in one line naming the file, so an unreviewed draft never becomes spec.

   Budgets: `selfci.fuzz` runs the bounded leg, 120 cases at seed 0 (about 45 s on a 4-core host;
   every kind is the primary of at least six cases). `release_check --check` runs `self_ci.py
   --fuzz-depth release`: 2 000 cases at a fresh seed, which the leg's finding prints so a failure
   reproduces. `--jobs` (default: up to 4) runs seeds in parallel, each seed in one worker;
   `--time-budget SEC` stops starting cases after that long and reports how many it left unrun.
   The run needs `node` on PATH and names it when it is missing (exit 2).

## Seed protocol

Seeding is a two-step act, and the split is load-bearing:

1. `runner.py --record --scenario <id>` runs the implementation and writes the `[expected]`
   section from the live behavior (`stdout`, or `findings` where the output carries an
   ecosystem-owned code; `stderr_contains` is hand-written and kept). Unit scenarios are never
   recorded — the table is the expectation.
2. A human reviews that the recorded behavior **is** what the standard means — the recorded
   text is read as a spec, token by token; host facts, absolute paths and accidental drift
   are bugs in the scenario (or the normalization), not expected values.

Only after step 2 does the record become spec. A scenario that passes by recording is not a
scenario that covers.

## Self-CI

The `selfci.conformance` leg of `meta/self_ci.py` runs `runner.py --tree <repo>` (Python
implementation + coverage gate). The corpus is green when the leg is green. The machinery is
pinned by `meta/tests/test_conformance_coverage.py` and `meta/tests/test_conformance_corpus.py`.

From C103 the corpus also runs on the node implementation: `selfci.corpus-node` runs
`runner.py --tree <repo> --impl node --area units --area hooks --area cli --area tools` — the same unit tables through
`probe.mjs`, fixture-free; (from C104) every hook scenario on the JS hooks; and (from C105) every CLI scenario
of a command whose Python file has its port under `js/`, run as `node node_modules/akmon/js/akmon/cli.mjs`
in a Node-package project that the JS `sync` itself warmed up; and every scenario of a tool with a JS port, run as
`node node_modules/akmon/js/tools/<tool>.mjs` (from C105 pass 3, `model_routing/init`). A scenario of a command or tool still unpaired
in `pairing.toml` is *pending* on node and reported as a skip that names the file, so the pairing list is the
one record of what is outstanding. The gates are off (they run on a full run only; `--area` repeats to
name a slice of several areas). The node
toolchain's own checks are independent self-CI legs on the same prerequisite-naming stance as
the wheel smoke: `selfci.js-deps` (`npm ci --ignore-scripts`), `selfci.js-typecheck`
(`npx --no-install tsc --checkJs --noEmit -p .`), `selfci.js-unit` (`node --test 'js/**/*.test.mjs'`),
`selfci.js-lint` (`npx --no-install oxlint .`) and `selfci.js-format` (`npx --no-install oxfmt --check .`).

`selfci.fuzz` (C111) runs `fuzz.py --cases 120 --seed 0`, the bounded differential fuzz of gate 4;
`python3 meta/self_ci.py --fuzz-depth release` (what `release_check --check` runs) makes it 2 000
cases at a fresh seed, printed in the leg's label. The leg is pinned by
`meta/tests/test_conformance_fuzz.py`.
