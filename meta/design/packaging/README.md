# Design: akmon as an installable package (`uvx akmon init`)

> **Status: locked; steps 1–5 written, step 6 (publish) not started.** The decisions
> marked *lock* are collected in
> [ADR 0009](../../decisions/0009-packaging-package-carrier-and-mount-modes.md) (backlog A10),
> Accepted by the owner (D2-12 verified). Implementation is C37: the CLI, `init` in all four
> mount modes, package mode and the docs cut-over exist and are covered on the current development
> interpreter by tests, the self-CI package leg and a live network probe. C68/D2-34 supersedes the
> former Python 3.9 clause with one **Python >=3.11** floor for the package and every shipped
> venv-free entry point; the [floor note](python-39-floor.md) preserves the measured reason.
> What "landed" does **not** yet mean here: the work is under owner review and uncommitted
> (D5 — the owner commits). C37 owns the carrier and local/git-pin adoption, not publication.
> The first PyPI publish is the separate release task V4, gated on V1, on
> [C69](mount-resolution-owner.md), and on the landing of the
> [C68 floor re-lock](python-39-floor.md).
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

What must still exist as files in the consumer repo is exactly what the **harness** has to
resolve by path: the guardrails the consumer's AGENTS.md @-imports. `akmon sync`
**materializes** those, and only those, into `<AITNA_ROOT>/.akmon/guardrails/`. Pointing the
import into the package instead was considered and rejected in the C77 amendment: AGENTS.md is
committed, the path into the package carries the venv's Python version, and an @-import that
does not resolve reports nothing at all. Because the copy is the consumer's *rules*, it is held
current from two sides: `sync --check` / `verify` on a commit, and a SessionStart line naming any
guardrail the running package has moved past. `common/materialization.py` owns both the format
`sync` writes and the comparison the hook makes, so the writer and the judge cannot drift apart.

The executable surface is *not* materialized — see the C77 amendment in ADR 0009. It was,
until the generated wiring gained a way to name a hook without a path: the wiring is a
committed file and cannot carry `.venv/lib/python3.13/site-packages/…`, so copies into the
repo were the only way to spell a hook at all. `akmon hook <name>` is that way, and the
wiring now reads `"<anchor>/.venv/bin/akmon" hook <name>` in package mode. Everything the
hooks import — `common/`, the routing library, `registry.json` — stays inside the wheel and
is reached from there, because the hook resolves its runtime tree from its own location.

Materialized guardrails carry the generated banner: `sync --check` (CI) flags drift after a
pin bump, `sync` refreshes, hand-edits are overwritten like any generated pointer. The
`.akmon/` directory has no other writer, so `sync` also removes everything unplanned under
it — banner or not, which is what finally clears a previous version's routing registry.
Consequences inside the tools (C37 scope):

- **Standard-tree resolution decouples from the mount:** tree root = `<AITNA_ROOT>/akmon`
  when it exists, else the installed package's embedded tree (`importlib.resources`).
  Project-root discovery accepts `AGENTS.md` + `<AITNA_ROOT>/.akmon.toml` (today
  `bin/sync.py::_find_project_root` requires the mount to exist).
- **Hook wiring becomes mode-aware:** `python3 "<anchor>/{aitna}/akmon/hooks/<hook>.py"`
  (mounted) vs `"<anchor>/.venv/bin/akmon" hook <hook>` (package). Entry recognition covers
  every spelling the generator has emitted, including the retired materialized one, so
  switching modes replaces stale entries instead of leaving them beside the new ones.
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

*As shipped, the "is akmon importable from the project env" check is a **manifest** check —
does the project's `pyproject.toml` declare akmon as a requirement, and **in which dependency
class** — not an import probe. The CLI may be running
from anywhere (a `uvx` ephemeral env, a global tool install), so its own importability says
nothing about the project's env, and probing that env would mean guessing the project's
manager. The consequence is deliberate: `init` reports and prints the line to add, and never
edits the manifest. It does check the class, though — a pin in runtime dependencies or an extra
is reported as wrong, because §4's "dev group, never a runtime dep or an extra" is a lock, not a
preference. A bare mention of the word akmon (in prose, or in a `# add it later` comment) is not
a pin: reading one as declared let a package-mode attach finish green over a project where
`uv run akmon` cannot resolve at all.*

## CLI contract

```
uvx akmon init [--mode submodule|vendored|subtree|package] [--aitna-root PATH] [--yes]
akmon sync  [--check|--dry-run]
akmon verify [--strict]
akmon path
akmon hook <name> [args...]
akmon version
```

*As shipped, `init` also takes `--project-root PATH` (attach somewhere other than the cwd —
what the tests drive), `--repo URL` and `--ref REF` (the pin; default the latest release
tag), `--archetype ID` / `--language LANG` (fill the classification in when it is already
known instead of leaving the placeholder), `--no-ci`, and `--switch-mode`.*

*Two mode-specific facts the contract above does not imply, both settled by review:*

- ***`subtree` is refused, not run.** `git subtree add` writes a squash commit **and** a merge
  commit into the consumer's history, and commits are the owner's (D5, BOOTSTRAP §A10). So
  `init --mode subtree` prints the command and the follow-up `akmon init --mode subtree --ref
  <ref>`, and does the rest of the attach on the re-run. `--ref` is required there because a
  merged subtree keeps no git metadata: nothing on disk can tell `init` which ref was taken, and
  the integration record must not invent one.*
- ***`vendored` refuses `--ref`.** The embedded tree it copies *is* the installed package's
  version, so honouring a ref would mean fetching another tree over the network — the one thing
  this mode exists to avoid. Pin a ref with `submodule`/`subtree`, or install the akmon version
  you want to vendor.*

*And one whole-command rule: changing the recorded mount mode is a **migration**, not a
realign — it moves every path the hand-owned `AGENTS.md` block names — so it needs
`--switch-mode`, and then the edits `init` refuses to make (re-point the block, drop the dead
mount, update the CI commands) are printed rather than skipped silently. Between two **mounted**
modes it goes further and refuses to run at all while the old mount is on disk: a submodule's
gitlink, a subtree's tracked files and a vendored copy's plain files are mutually exclusive
states of one path, and retiring one deletes tracked files — the owner's commit (D5). The
removal commands for the previous mode are printed instead. Which mount a project has is
decided by* git *(a staged gitlink or a `.gitmodules` entry), never by the files at the path:
all three mounted modes carry the same `bin/sync.py`, so reading the tree's presence as "already
a submodule" let a `vendored → submodule` switch finish green with no `.gitmodules` at all.*

*Two more rules the contract does not imply:*

- ***Mode `package` exits 1 without a dev-group pin.** It mounts no tree, so the manifest
  declaration* is *the mount (ADR 0009 §4): without it no `akmon` command resolves in the
  project and the CI workflow `init` just wrote cannot run. `init` cannot write the pin — it
  cannot know every manifest dialect — so it says so in the exit code and prints the line.
  The same classifier (`bin/sync.py::package_pin_status`, one owner shared with `verify`) reads
  every declaration and reports the worst: a runtime dependency or an extra is the wrong class,
  a `[tool.uv.sources]` entry is a source override rather than a declaration, and prose is not
  a pin. `verify --strict` keeps the check alive past the attach, for projects that have a
  `pyproject.toml` at all.*
- ***The dev-layer root is validated wherever it comes from.** `--aitna-root` and `AITNA_ROOT`
  are one contract — the flag's whole effect is to set the variable — so both are refused when
  absolute or when they climb out of the project, lexically and after resolution.*
- ***Mode `package` requires the virtualenv inside the project root.** The generated wiring
  names the console script by a project-relative path, and that wiring is a committed file every
  developer on the project runs; an absolute path to whichever venv happened to run `sync` is a
  silent break for everyone else. `sync` never fails over it — the first attach runs `sync`
  before the pin is installed, by construction — and predicts `.venv/bin/akmon` instead;
  `verify` reports the missing script (`hooks.launcher`) until it is there. A venv outside the
  project root stays a design open point; the answer is a locator shim, not an absolute path.*

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
- **`hook`** — run one hook out of that same resolved tree (C77). Called by the generated
  vendor wiring, not by a human: it exists so the wiring can name a hook **without a path**,
  which is what let the executable materialization go. In-process (`runpy`), because these
  hooks sit on the hottest tools of a session and a second interpreter start per tool call
  would be the only cost this indirection adds; safe because the hooks are stdlib-only. The
  argv tail passes through verbatim, so Codex keeps its dispatcher shape
  (`akmon hook codex-hook role-on-code`). A path where a name belongs is refused — only
  generated wiring calls this.
  *Measured on the alphavar pilot (Python 3.14 venv, medians over 30–40 runs): +3.1 ms over
  running the hook file directly. Getting there meant keeping the dispatch path clear of three
  imports, each individually larger than the dispatch — the lazy `__version__` (89 ms of
  distribution-metadata scan), `importlib.resources` in `akmon/_tree.py` (~45 ms, reached only
  when the wheel data is not a plain directory beside the module), and `argparse` (~18 ms) +
  `subprocess` (~12 ms), with `main` dispatching `hook` before it builds a parser.
  `import akmon.cli`: 88 ms → 32 ms. Anything added to that path is paid on every tool call of
  every package-mode session.*
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
- Python floor: **3.11** for the package and all shipped venv-free entry points, including the
  bare `python3` used by generated hooks in every carrier. Python 3.9/3.10 are unsupported;
  zero runtime dependencies remains unchanged. *(D2-34 lock; supersedes only D2-12's floor)*
- Name: `akmon` on PyPI — both `akmon` and fallback `ai-akmon` returned 404 when checked for
  D2-12; availability is historical evidence rather than a reservation, so registration still
  happens at first publish. *(lock)*
- Publish: building sdist/wheel and `twine`/`uv publish` becomes a step of the release
  pipeline (release role), gated like tags/pushes — **owner runs publish** (D5). Trusted
  publishing via GitHub Actions once releases are tag-driven.

## Implementation plan (C37 touch-list, after A10 locks)

*Status: 1–5 written and covered on the current development interpreter (uncommitted, under owner
review), 6 not started; C68's Python 3.11 floor re-lock is owner-approved and awaits its landing
commit. What each step actually shipped is recorded in the CHANGELOG; the notes below stay as the
plan they were.*

1. **Package skeleton** — `pyproject.toml`, `src/akmon/cli.py` dispatching to
   `bin/sync.py::main` / `bin/verify.py::main` (import, not subprocess, for the embedded
   case; `exec` of the mounted tree per the skew rule), `akmon version`.
2. **`init` command** — submodule mode first (today's default intent): submodule add +
   local layout + `.akmon.toml` + sync + routing init + next-steps print. Tests: a tmp
   git repo fixture end-to-end; `meta/self_ci.py` gets a package leg (build the wheel,
   run `init` in a fixture, `verify --strict` green).

   *Shipped as `src/akmon/_init.py` covering all four modes at once rather than submodule
   first — the modes share every step after the mount, so splitting them would have meant
   writing the shared 80% twice. Two decisions the plan did not name, both taken to make the
   `verify --strict` acceptance real rather than nominal: `init` also writes the `.gitignore`
   entries (BOOTSTRAP §A7 — a mechanical step, appended, never rewritten) and a CI workflow
   **only when the project has none** (`--no-ci` opts out, an existing workflow gets a printed
   next step instead), because a consumer without either fails the strict check on warnings
   that no judgement step covers. The submodule end-to-end test clones this repository over
   `file://` — no network, and the pin is real.*
3. **Vendored + subtree modes** — embedded-tree copy with version record; subtree
   documented in BOOTSTRAP. Skew notice in the launchers.
4. **Package mode** — mount-decoupled tree resolution (root discovery via
   `.akmon.toml`; embedded tree via `importlib.resources`), `<AITNA_ROOT>/.akmon/`
   materialization of the imported guardrails, `akmon hook` wiring, `akmon path`,
   `mount` key in `.akmon.toml`. **Pilot on alphavar** (git+https dev-group pin):
   detach the submodule, pin, re-point AGENTS.md @-imports and vendor hook wiring at
   `.akmon/`, CI → `uv run akmon sync --check` / `verify --strict` (the self_ci and
   meta-tests legs move to ai_akmon's own CI — they test the standard, not the
   consumer).
5. **Docs cut-over** — README "Quick start" (≤10 lines, `uvx akmon init` first);
   BOOTSTRAP.md reframed as the reference behind `init` (agent judgment steps + manual
   path), not the entry point. CHANGELOG entry (`consumer-visible`).
6. **Release wiring (V4, separate from C37)** — publish step in the release pipeline + PyPI
   name registration; first published version cut from the next release tag.

## Resolved (locked in ADR 0009)

- PyPI name: **`akmon`** — both `akmon` and `ai-akmon` free at check time
  (`pypi.org/pypi/<name>/json` → 404); register on first publish.
- `init` pin: **latest release tag** by default, `--ref` to override (consistent with
  "the tag is the reviewed state", [release-versioning](../release-versioning.md)).

## Open points

- Interaction with V1 (keystone→akmon rename): publishing before V1 completes ships the
  remnants to PyPI. **Sequencing: V1 sweep lands before the first publish** — same
  reasoning as the announcement blocker. The alphavar `package`-mode pilot via
  git+https is *not* a publish and may run first.
- `uvx akmon init` runs the *latest* published CLI while a project may want an older
  standard: `uvx akmon@0.2.1 init` covers it; document, don't engineer around it.
- **A virtualenv outside the project root** in mode `package`: the generated wiring names the
  console script relative to the project, so a venv elsewhere can only be spelled absolutely,
  and the wiring is committed. Locked for now as a requirement of the mode, with `verify`'s
  `hooks.launcher` reporting it; the eventual answer is a small locator shim, not an absolute
  path in a shared file.
- **Non-Python consumers** (e.g. a JS project like tvassistant): the manifest-pin flavor
  of `package` mode is Python-specific, but nothing else is — the CLI is stdlib-only and
  `uvx akmon init/sync/verify` runs ephemerally wherever uv exists, with the pin
  recorded in `.akmon.toml` instead of a manifest. C77 removes the materialized hook copy, so
  persistent hook execution still needs the project-local launcher required by package mode;
  an ephemeral `uvx` invocation alone does not provide it. Candidate flavors, in cost order:
  (a) document `uvx`-driven `package` mode for any-language repos — no new code beyond C37; (b) an
  npm wrapper package (`akmon` on npm shelling to `uvx akmon` / bundling the tree) so JS
  projects pin in `package.json` `devDependencies` the way Python ones pin in
  `pyproject.toml`; (c) mounted modes (submodule/vendored) keep working for any language
  today. Decide after the alphavar pilot.
- **Developing akmon while consuming it as a package:** the dev bench is a plain clone
  of `ai_akmon` (self-hosted: `meta/` carries its own backlog/tests/self-CI). For
  co-development against a consumer, override the pin locally — uv: `[tool.uv.sources]
  akmon = { path = "../ai_akmon", editable = true }` (or an ephemeral
  `uv pip install -e ../ai_akmon`) — then the wired hooks execute from that working copy and
  `akmon sync` refreshes its imported guardrails. Documented in README §akmon's own development —
  the single home by owner decision:
  BOOTSTRAP stays consumer-only (developing *with* akmon, never akmon itself); no new
  machinery.
