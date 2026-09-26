# 0020 — Node.js consumers: a JavaScript implementation, an npm carrier, one behavioral spec

- **Status:** Accepted
- **Owner:** akuminov@gmail.com
- **References:** [design A34](../design/node-consumers.md) (options, analysis, plan) ·
  [ADR 0009](0009-packaging-package-carrier-and-mount-modes.md) (carriers, mode `package`) ·
  [ADR 0014](0014-code-rules-catalog-and-language-profiles.md) (checks, profiles) ·
  [ADR 0018](0018-release-alignment-and-update-lifecycle.md) (version carriers, update) ·
  [packaging open point](../design/packaging/README.md#open-points)

## Context

akmon reaches a consumer as a git mount or as a Python package pinned in `pyproject.toml`.
Everything it executes is stdlib-only Python: about 12.1k lines in 36 files across `src/akmon`,
`bin`, `common`, `hooks` and `tools` (counted 2026-09-26). A Node.js project can use the mounted
modes, but it needs Python on the host and cannot pin akmon in `package.json`. `init` also
detects only Python linters.

The owner wants Node projects to install akmon from npm as a dev dependency, to get the same
model of hooks, checks, linters and analyzers, and to run **in an environment without Python**. A
thin npm wrapper around the Python code was considered first and rejected by the owner for that
reason (design §3, F1). Reusable tools matter as well: a JS project should be able to build its
own dev-layer tools on akmon's.

## Accepted decision blocks

### D01 — Two implementations, one normative behavioral spec

`Decision-ID: ADR-0020/D01`

akmon keeps **two permanent implementations** of everything a consumer executes: the existing
Python one and a new JavaScript one. Neither is generated from the other. What they share is a
**normative behavioral spec**: a language-neutral conformance corpus of process-level scenarios.
Where the corpus is silent or ambiguous, the Python implementation is the reference, and the
resolution becomes a new corpus scenario. Consolidating on one language is not pursued.

This supersedes, for executable code only, the single-implementation premise of
[ADR-0009/D01](0009-packaging-package-carrier-and-mount-modes.md#d01--supported-carriers-and-source-ownership)
and [ADR-0009/D02](0009-packaging-package-carrier-and-mount-modes.md#d02--executable-and-runtime-surface).
The standard's documents (guardrails, profiles, pipelines, roles, skills) stay single-source, and
generated or materialized files stay derived.

### D02 — Scope: Python-free in Node package mode only

`Decision-ID: ADR-0020/D02`

A Node project running mode `package` from npm needs Node and no Python. The mounted modes
(`submodule`, `vendored`, `subtree`) keep running the Python implementation in every repository,
Node or not, and keep the `python3` requirement. The JavaScript implementation covers everything
a consumer executes: the CLI (`init`, `update`, `sync`, `verify`, `check`, `path`, `hook`,
`version`, `tool`), the hooks, the shared `common` code, and every tool under `tools/`. akmon's
own development tooling under `meta/` stays Python.

Behavior common to both ecosystems is identical in both implementations. Behavior specific to
one ecosystem (the manifest pin reader, package-manager commands, linter detection) exists only
in that ecosystem's implementation and is tagged with the ecosystem in the corpus.

### D03 — How compatibility is proven

`Decision-ID: ADR-0020/D03`

Compatibility is established at the **process boundary**, by running the corpus against both
implementations in self-CI. The corpus covers:

- hook payload and environment → stdout, stderr, exit code;
- project fixture → the files `init`/`sync` write, compared byte for byte;
- the `verify` findings;
- the `check` results;
- the output of each tool.

The rules that normalize paths and interpreter spellings are part of the spec. Three gates enforce
coverage and pairing:

- **Coverage gate.** Every CLI command, hook, tool and finding code has at least one scenario.
- **Pairing gate.** Every consumer-executable Python file has its JavaScript counterpart at the
  mirrored path under `js/`, or an entry in an explicit exemption list with a reason.
- **Differential fuzzing.** Hook payloads, both recorded real ones and mutations of them, are run
  through both implementations.

A change to executable behavior lands in both implementations **with** a scenario, in one
change. A release requires both implementations green on the whole corpus.

### D04 — Form of the JavaScript implementation

`Decision-ID: ADR-0020/D04`

The JavaScript implementation is plain ES-module JavaScript with JSDoc types, type-checked with
`tsc --checkJs --noEmit`. The published files are the repository files, with no build step. It
has no npm runtime dependencies and no lifecycle scripts. The floor is **Node 22**, the oldest
maintained LTS line on 2026-09-26. The floor follows the Node LTS schedule the way the Python
floor follows ADR-0009/D04.

TOML is read by a **vendored copy of smol-toml** at a pinned version, with its licence kept and
verified against the official `toml-test` suite. It is updated only through a recorded task. The
integration record stays TOML.

### D05 — npm carrier and Node package mode

`Decision-ID: ADR-0020/D05`

- **Package.** Name `akmon`, one version line with the wheel. `package.json` is a version carrier
  under ADR-0018/D01; its SemVer spelling of a development version is derived from the PEP 440
  one by the shared version logic, never hand-written. Both carriers ship one file list, which a
  test proves.
- **Pin.** An **exact** version in `package.json` `devDependencies`, or the release git tag before
  the first npm publish. A pin in `dependencies`, `optionalDependencies` or `peerDependencies` is
  a `runtime` finding.
- **Record.** The integration record names the ecosystem of the pin.
- **Supported layouts.** Those with `node_modules/akmon` under the project root: npm, pnpm, Yarn
  with the `node-modules` linker, and Bun. `verify` reports Yarn Plug'n'Play and hoisting only to
  a workspace root, each with its fix.
- **Hook wiring.** Hooks are wired as `node "<anchor>/node_modules/akmon/js/hooks/<script>.mjs"`.
  The path carries no version, and no package-manager shim sits on the hot path. The latency
  budget is JS hook p50 no slower than the Python package-mode hook p50 on the same host,
  measured and recorded in `MEASUREMENTS.md`.
- **Guardrails.** The guardrails that `AGENTS.md` imports are copied into
  `<AITNA_ROOT>/.akmon/guardrails/` as in Python package mode.
- **Runtime declaration and CI.** In Node package mode the runtime declaration requires `node`
  and not `python3`. The generated CI installs no Python.
- **Publish.** The npm publish is a release step the owner runs, after a git-tag pilot on a Node
  consumer.

### D06 — Tools: all ported, one command, a reusable JS API

`Decision-ID: ADR-0020/D06`

Every tool under `tools/` has a JavaScript implementation under D01–D03. In both implementations
the tools are reached through one CLI subcommand, `akmon tool <path> [args]`. Hook and skill
messages name the command of the implementation that is executing, never a `python3` path in
Node package mode. The JavaScript tools are also exported as documented ES modules through the
package's `exports` map, so a JS project can build its own dev-layer tools on them. That exported
surface is a public API under the release versioning (a breaking change is a breaking release).

### D07 — Checks, profile and update for Node projects

`Decision-ID: ADR-0020/D07`

- **Detection.** `init` detects the project's own JavaScript/TypeScript tools (ESLint, Biome,
  oxlint, Prettier, TypeScript) and records them in `[check]` in the ADR 0014 shape.
- **Running.** Each command runs through the project's package manager, never with an implicit
  download. Each check has explicit file patterns, and TypeScript is checked as a whole project.
  `package.json` scripts are named for the owner, never auto-recorded.
- **Offered ruleset.** For a project with no tool, it is a standard `extends` resolved from the
  installed package by name. The tool and the rules are decided in A35 after a baseline on a real
  Node repository; until then a Node project chooses between `own` and `none`.
- **Profile.** A `js` language profile attaches when `package.json` exists and holds only rules
  that no linter checks.
- **Update.** `akmon update` uses the detected manager's exact dev-install command. Any other
  manager gets the command printed (ADR-0018/D03).

## Considered alternatives

- **An npm wrapper that runs the Python code** (a launcher calling host `python3`, or `uvx`).
  Rejected by the owner: the requirement is to run without Python.
- **One implementation in JavaScript for every consumer.** Rejected by the owner: it would force
  Node onto Python consumers and rewrite a working stack.
- **Generating one implementation from the other** (transpiling). Rejected: generated code would
  hide exactly the semantic differences the corpus exists to expose.
- **A bundled Python interpreter in the npm package.** Rejected: it contradicts "without Python"
  in substance, and akmon would own a per-platform supply-chain surface.
- **TypeScript with a build step.** Rejected in favour of JSDoc: the published files are then
  the reviewed files, and nothing is built between review and consumer.
- **The integration record in YAML.** Rejected: Python has no stdlib YAML, so the Python
  implementation would lose its zero-dependency contract. The YAML spec is far larger, with
  implicit typing (`no` → `false`). Python consumers' `pyproject.toml` stays TOML regardless.
- **A TOML parser written for akmon.** Rejected: a home-grown reader of a standard format is the
  failure ADR 0014 records for its withdrawn checker. A vendored, conformance-tested library is
  the standard tool.
- **Hooks through `node_modules/.bin/akmon hook`.** Rejected: it puts a manager shim on every tool
  call, and shims differ per manager.
- **Version ranges in the pin.** Rejected: the lockfile would then decide which rules the agents
  follow, not a reviewed bump.

## Consequences

- Every change to executable behavior costs work in two languages, permanently. The corpus and
  the pairing gate make an omission fail CI instead of shipping.
- Before the port, logic that can be data (policy tables, registries, message templates) moves
  into data files read by both implementations. This shrinks what has to be written twice.
- akmon's repository gains a Node toolchain (`node:test`, `tsc --checkJs`, a JS linter), and
  self-CI needs Node. The verification set in `AGENTS.md` grows accordingly.
- Harness parity for Node consumers is claimed only after a live probe on Claude and Codex in an
  environment without Python.
- The Python consumer's experience does not change, except that tools gain `akmon tool`.
