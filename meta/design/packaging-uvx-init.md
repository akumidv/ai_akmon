# Design: akmon as an installable package (`uvx akmon init`)

> **Status: locked.** The decisions marked *lock* are collected in
> [ADR 0009](../decisions/0009-packaging-package-carrier-and-mount-modes.md) (backlog A10),
> Accepted by the owner (D2-12 verified). Implementation is C37.
> Pilot consumer for the `package` mount mode: **alphavar**.

## Frame

Attaching akmon to a project today means "read a 350-line BOOTSTRAP.md, run a git
submodule incantation, create the local layout by hand, then run two in-tree scripts".
That is the single biggest adoption filter: people adopt standards that install in two
minutes, not standards that open with a long document.

Good outcome:

- `uvx akmon init` in a fresh project attaches the standard end-to-end (mount the shared
  layer, create `_aitna/` local layout, write the integration record, wire vendor
  pointers/hooks via sync, initialize model routing) with zero prior reading;
- `akmon verify` / `akmon sync` work as first-class commands in CI and locally;
- the submodule stops being the only mount mode — subtree / vendored copy become real,
  documented alternatives (submodule friction is a known adoption risk);
- nothing about the standard's content model changes: the package is a **carrier**, the
  contract stays markdown + stdlib tools (ROADMAP §Distribution: this is a step on the
  submodule → product path, orthogonal to the MCP hybrid).

Non-goals: no runtime service, no new governance surface, no dependency the model needs
in order to function (ROADMAP §Build vs buy). The agent-guided parts of BOOTSTRAP
(archetype classification, guardrail/profile selection) stay agent/owner work — `init`
mechanizes the mechanical steps and prints pointers for the judgment steps.

## Current state (what we build on)

- `bin/sync.py`, `bin/verify.py` — stdlib-only, argparse CLIs, project-root discovery via
  `AGENTS.md` + `<AITNA_ROOT>/akmon`; safe to run repeatedly. Already shaped like console
  entry points in everything but packaging.
- `tools/model_routing/init.py` — the routing initializer `init` must invoke as a step.
- `<AITNA_ROOT>/.akmon.toml` — the integration record (version, `[test].runner`); the
  natural place for `init` to record the chosen mount mode.
- `AITNA_ROOT` env — the dev-layer root is already parameterized; the CLI inherits it.
- Versioning `v0.x.y` + CHANGELOG + release role (ADR 0001) — the package rides the same
  release, it does not get its own version line.
- LICENSE (Apache-2.0) present; repo public at `github.com/akumidv/ai_akmon`.

## The core decision: what is inside the package?

| | A — thin bootstrapper | B — standard embedded | C — CLI + embedded tree (proposed) |
|---|---|---|---|
| Package contains | CLI only; content fetched from git at init | full tree as package data; no git needed | CLI **and** the full tree as package data |
| `init` offline | no (needs network + git) | yes | vendored: yes · submodule: needs git |
| Mount modes | submodule only | vendored only | `--mode submodule\|vendored\|subtree\|package` |
| Skew risk | CLI vs fetched tag | none (tree pinned by pkg version) | none for vendored; rule below for submodule |
| Cost | smallest wheel | ~full repo in wheel | ~full repo in wheel |

**Proposed: C.** One PyPI distribution, built from the same git tag the release cuts, so
`package version == standard version`, always. `init --mode submodule` keeps today's
default distribution intent (deterministic pin, PR governance); `--mode vendored` copies
the embedded tree into `<AITNA_ROOT>/akmon` and records the version in `.akmon.toml`
(pin = recorded version, updates via re-run of a future `akmon bump`); `--mode subtree`
documented, delegated to git. Default mode: `submodule` when the project is a git repo
with network, else `vendored` — always printed, never silent. *(lock)*

### Mount mode `package` — no standard tree in the repo

The three modes above all materialize the tree at `<AITNA_ROOT>/akmon`. Mode `package`
removes the in-repo tree entirely: the consumer pins akmon in its own dependency
manifest (a uv dev-group entry — `akmon @ git+https://github.com/akumidv/ai_akmon@vX.Y.Z`
until the first PyPI publish, `akmon==X.Y.Z` after) and the standard lives in
site-packages as the CLI's embedded tree. A **dev**-group pin, never a runtime dep or an
extra: akmon is dev tooling and must not reach the consumer's own users.

What must still exist as files in the consumer repo is exactly the **always-on surface**
— the pieces that fire before any venv is guaranteed (vendor hooks) or that vendor
loaders @-import at session start (guardrails). `akmon sync` **materializes** them into
`<AITNA_ROOT>/.akmon/`:

- `hooks/` — self-contained copies of `hooks/*.py` (incl. `hook_core.py` and the
  adapters); stdlib-only, so `python3 …/<AITNA_ROOT>/.akmon/hooks/<hook>.py` works with
  no venv — the same property the mounted tree gives today;
- `guardrails/` — the files the consumer's AGENTS.md @-imports.

Materialized files carry the generated banner: `sync --check` (CI) flags drift after a
pin bump, `sync` refreshes, hand-edits are overwritten like any generated pointer.
Consequences inside the tools (C37 scope):

- **Standard-tree resolution decouples from the mount:** tree root = `<AITNA_ROOT>/akmon`
  when it exists, else the installed package's embedded tree (`importlib.resources`).
  Project-root discovery accepts `AGENTS.md` + `<AITNA_ROOT>/.akmon.toml` (today
  `bin/sync.py::_find_project_root` requires the mount to exist).
- **Hook-path templating becomes mount-aware:** `{aitna}/akmon/hooks` (mounted) vs
  `{aitna}/.akmon/hooks` (package). `_is_akmon_entry` recognises both markers, so
  switching modes drops stale entries pointing at the old location.
- **`.akmon.toml` records the mode:** `mount = "submodule" | "vendored" | "subtree" |
  "package"`; in package mode sync stamps `akmon_version` from the package version.
- **No version skew by construction:** the installed package *is* the pinned standard;
  `sync`/`verify` run from the embedded tree. The exec-the-mounted-tree rule applies to
  mounted modes only.
- **Reading the rest of the standard** (roles, pipelines, MODEL.md, meta): `akmon path`
  prints the resolved tree root so agents read it locally; human-facing links in the
  consumer's docs point at the GitHub tree at the pinned tag.

`init --mode package` presumes a Python dependency manager is already set up (init
cannot edit every manifest dialect): it verifies akmon is importable from the project
env, writes the local layout + `.akmon.toml`, materializes, syncs, and prints the
manifest line to pin when the import check fails. The default-mode rule above is
unchanged — `package` is an explicit choice. **Pilot: alphavar** (uv project, dev-group
git-tag pin); pilot findings fold back here before the first PyPI publish. *(lock)*

## CLI contract

```
uvx akmon init [--mode submodule|vendored|subtree|package] [--aitna-root PATH] [--yes]
akmon sync  [--check|--dry-run]
akmon verify [--strict]
akmon path
akmon version
```

- **`init`** (new code): mount the standard; create `_aitna/{agents,skills,tools,memory}`
  + `_aitna/TASKS.md` skeleton; write/update `.akmon.toml` (version, mount mode); run
  `sync.py`; run `tools/model_routing/init.py`; print the two judgment steps it did NOT
  do (archetype/guardrails per ARCHETYPES.md; `[test].runner` pin) as next-step pointers.
  Non-interactive by design — flags + defaults, `--yes` for the one confirm; agents are
  first-class callers. Idempotent: re-run realigns, never clobbers project text (same
  contract sync.py already honors).
- **`sync` / `verify`** — thin launchers. **Version-skew rule *(lock)*:** after init, the
  launcher `exec`s the **mounted tree's** `bin/sync.py` / `bin/verify.py`, so the pinned
  standard governs behavior, not whatever CLI version happens to be installed; if
  CLI version ≠ mounted version, print a one-line notice. Only `init` (no mount yet)
  and mode `package` (the package *is* the pin) run from the embedded tree.
- **`path`** — print the resolved standard-tree root (the mount when present, else the
  embedded tree). The package-mode answer to "where do I read roles/pipelines/MODEL.md";
  also useful in scripts.
- Out of scope for now: `akmon bump` (pin bump = deferred C2), publishing an MCP surface.

## Packaging mechanics

- `pyproject.toml` at repo root; src-layout `src/akmon/` containing only the thin CLI
  (`cli.py` + `init` implementation); build backend hatchling; console script
  `akmon = akmon.cli:main`. **Zero runtime dependencies** — the stdlib-only property is a
  contract, verify should assert it stays true.
- The standard tree ships as package data (hatchling force-include of the repo tree at
  build time, excluding `.git`, `__pycache__`, `tests/` fixtures' caches). Whether
  `meta/` (the DEVELOP tree) ships too: **yes for parity** — the submodule carries it, a
  vendored mount must not be a second, poorer flavor of the standard. *(lock)*
- Python floor: **3.9** (sync.py already carries a pre-3.11 tomllib fallback; do not
  raise the floor just for packaging). *(lock)*
- Name: `akmon` on PyPI — availability unverified; fallback `ai-akmon` (repo name), which
  degrades ergonomics to `uvx --from ai-akmon akmon init`, so check early. *(lock)*
- Publish: building sdist/wheel and `twine`/`uv publish` becomes a step of the release
  pipeline (release role), gated like tags/pushes — **owner runs publish** (D5). Trusted
  publishing via GitHub Actions once releases are tag-driven.

## Implementation plan (C37 touch-list, after A10 locks)

1. **Package skeleton** — `pyproject.toml`, `src/akmon/cli.py` dispatching to
   `bin/sync.py::main` / `bin/verify.py::main` (import, not subprocess, for the embedded
   case; `exec` of the mounted tree per the skew rule), `akmon version`.
2. **`init` command** — submodule mode first (today's default intent): submodule add +
   local layout + `.akmon.toml` + sync + routing init + next-steps print. Tests: a tmp
   git repo fixture end-to-end; `meta/self_ci.py` gets a package leg (build the wheel,
   run `init` in a fixture, `verify --strict` green).
3. **Vendored + subtree modes** — embedded-tree copy with version record; subtree
   documented in BOOTSTRAP. Skew notice in the launchers.
4. **Package mode** — mount-decoupled tree resolution (root discovery via
   `.akmon.toml`; embedded tree via `importlib.resources`), `<AITNA_ROOT>/.akmon/`
   materialization of hooks + guardrails, mount-aware hook templating, `akmon path`,
   `mount` key in `.akmon.toml`. **Pilot on alphavar** (git+https dev-group pin):
   detach the submodule, pin, re-point AGENTS.md @-imports and vendor hook wiring at
   `.akmon/`, CI → `uv run akmon sync --check` / `verify --strict` (the self_ci and
   meta-tests legs move to ai_akmon's own CI — they test the standard, not the
   consumer).
5. **Docs cut-over** — README "Quick start" (≤10 lines, `uvx akmon init` first);
   BOOTSTRAP.md reframed as the reference behind `init` (agent judgment steps + manual
   path), not the entry point. CHANGELOG entry (`consumer-visible`).
6. **Release wiring** — publish step in the release pipeline + PyPI name registration;
   first published version cut from the next release tag.

## Resolved (locked in ADR 0009)

- PyPI name: **`akmon`** — both `akmon` and `ai-akmon` free at check time
  (`pypi.org/pypi/<name>/json` → 404); register on first publish.
- `init` pin: **latest release tag** by default, `--ref` to override (consistent with
  "the tag is the reviewed state", design/release-versioning.md).

## Open points

- Interaction with V1 (keystone→akmon rename): publishing before V1 completes ships the
  remnants to PyPI. **Sequencing: V1 sweep lands before the first publish** — same
  reasoning as the announcement blocker. The alphavar `package`-mode pilot via
  git+https is *not* a publish and may run first.
- `uvx akmon init` runs the *latest* published CLI while a project may want an older
  standard: `uvx akmon@0.2.1 init` covers it; document, don't engineer around it.
- **Non-Python consumers** (e.g. a JS project like tvassistant): the manifest-pin flavor
  of `package` mode is Python-specific, but nothing else is — the CLI is stdlib-only and
  `uvx akmon init/sync/verify` runs ephemerally wherever uv exists, with the pin
  recorded in `.akmon.toml` instead of a manifest (hooks stay `python3`-runnable from
  the materialized `.akmon/`). Candidate flavors, in cost order: (a) document
  `uvx`-driven `package` mode for any-language repos — no new code beyond C37; (b) an
  npm wrapper package (`akmon` on npm shelling to `uvx akmon` / bundling the tree) so JS
  projects pin in `package.json` `devDependencies` the way Python ones pin in
  `pyproject.toml`; (c) mounted modes (submodule/vendored) keep working for any language
  today. Decide after the alphavar pilot.
- **Developing akmon while consuming it as a package:** the dev bench is a plain clone
  of `ai_akmon` (self-hosted: `meta/` carries its own backlog/tests/self-CI). For
  co-development against a consumer, override the pin locally — uv: `[tool.uv.sources]
  akmon = { path = "../ai_akmon", editable = true }` (or an ephemeral
  `uv pip install -e ../ai_akmon`) — then `akmon sync` re-materializes from the working
  copy. Documented in README §akmon's own development — the single home by owner decision:
  BOOTSTRAP stays consumer-only (developing *with* akmon, never akmon itself); no new
  machinery.
