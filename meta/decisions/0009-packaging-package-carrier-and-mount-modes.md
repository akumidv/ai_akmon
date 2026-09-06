# 0009 — Packaging: the `akmon` package as carrier, four mount modes incl. `package`

- **Status:** Base ADR accepted — owner-locked (D2-12 verified; backlog A10 done).
  Implementation is [C37](../TASKS.md). The C68 floor amendment is owner-approved at D2-34
  and awaits landing. The C77 execute-from-the-package amendment is pending at D2-35.
- **Owner:** akuminov@gmail.com
- **References:** design [packaging concept](../design/packaging/README.md) (options
  and mechanics — the operative spec) · ROADMAP §Distribution ·
  [release-versioning](../design/release-versioning.md) (the tag is the reviewed state) ·
  ADR [0001](0001-release-and-roles-model.md) (one version line).

## Context

Attaching akmon means reading a 350-line BOOTSTRAP and running git-submodule incantations —
the single biggest adoption filter. The packaging design (A10) proposed `uvx akmon init`
plus three mount modes, all of which materialize the standard tree at `<AITNA_ROOT>/akmon`.
The alphavar pilot then asked for a fourth shape: **no standard tree in the repo at all** —
akmon pinned in the consumer's dependency manifest like any dev tool, the `_aitna/` dev
layer staying, the mounted tree leaving.

## Decision

1. **Carrier — option C:** one distribution containing the thin CLI (`src/akmon/`) **and**
   the full standard tree (incl. `meta/`, for parity with the submodule) as package data.
   Build backend hatchling; console script `akmon`; **zero runtime dependencies** (the
   stdlib-only property is a contract — verify asserts it); Python floor **3.9**
   *(superseded by the D2-34 amendment below)*. Package
   version == standard version, cut from the same release tag (no separate version line).
2. **PyPI name — `akmon`** (checked free, as is `ai-akmon`; register at first publish).
3. **Mount modes — `submodule | vendored | subtree | package`.** Default unchanged:
   `submodule` for a git repo with network, else `vendored`, always printed. `package` is
   an explicit choice.
4. **Mode `package`:** the consumer pins akmon as a **dev**-group dependency (git-tag pin
   via `git+https` until the first publish, PyPI after); no tree at `<AITNA_ROOT>/akmon`.
   `akmon sync` materializes the **always-on surface only** — `hooks/` (self-contained,
   stdlib-only, venv-free) and `guardrails/` (the AGENTS.md @-import targets) — into
   `<AITNA_ROOT>/.akmon/`, banner-marked and drift-checked by `sync --check`
   *(the executable half is superseded by the C77 amendment below)*. Tree
   resolution decouples from the mount (mount when present, else the embedded tree);
   `.akmon.toml` records `mount = "<mode>"`; `akmon path` prints the resolved tree root.
5. **Version-skew rule:** in mounted modes the launchers `exec` the mounted tree's
   `bin/sync.py`/`bin/verify.py` (the pin governs, with a one-line notice on CLI≠mount);
   in `package` mode the embedded tree governs — no skew by construction.
6. **`init` pin:** latest release tag by default, `--ref` to override.
7. **Sequencing:** the V1 rename sweep lands before the **first PyPI publish**; the
   alphavar `package`-mode pilot via git+https is not a publish and runs first. Publish is
   a release-pipeline step the **owner runs** (D5).

## Consequences

- Attach cost drops to `uvx akmon init` + the two judgment steps init deliberately leaves
  to the agent/owner (archetype/guardrail selection, `[test].runner` pin).
- A consumer repo can be standard-governed with only `_aitna/{local assets}` +
  `_aitna/.akmon/guardrails` + `.akmon.toml` checked in — no 90-file tree; the pin
  bump becomes an ordinary dependency bump reviewed like any other (C2's subject).
- The tools grow mount-awareness (root discovery, hook templating, tree resolution) —
  C37 scope; consumer docs must link the standard by GitHub-tag URL or via `akmon path`
  instead of relative mount paths.
- Consumer CI stops running the standard's own self-tests (`self_ci.py`, `meta/tests`) —
  those move to ai_akmon's CI; the consumer keeps `sync --check` + `verify --strict`.
- Non-Python consumers and the co-development workflow stay design open points
  (packaging concept §Open points) — nothing here blocks them.

## Amendment — Python 3.11 floor (C68 / D2-34)

The Python 3.9 clause in decision 1 is superseded. The package and every shipped venv-free
entry point now require **Python >=3.11**; the bare `python3` used by generated hooks is part of
the same floor in every carrier. Python 3.9 and 3.10 consumers must upgrade that host interpreter
before adopting this release. This is a Breaking migration and carries a pre-1.0 `x` bump.

The measured 3.9 repair was small, but the owner chose to end the continuing pre-3.11
compatibility obligation. Retaining 3.9, stopping at 3.10, splitting package and hook floors, and
raising package metadata alone were rejected. Zero runtime dependencies, the stdlib-only runtime,
and every other decision in this ADR remain unchanged. Evidence and acceptance carriers:
[the C68 floor note](../design/packaging/python-39-floor.md).

## Amendment — mode `package` executes from the package (C77)

The materialization clause in decision 4 is narrowed. Mode `package` **puts no executable
surface in the consumer repository and runs the hooks out of the installed package**.

- **New CLI subcommand `akmon hook <name> [args...]`** — the single entry point both vendor
  wirings name. It runs the named hook from the *resolved* standard tree (the mount when one
  exists, the embedded tree otherwise — the same resolution `akmon path` prints), in the same
  process via `runpy`, with the hooks directory on `sys.path` and the remaining argv passed
  through verbatim. For that call, `common` is bound to the same tree as the hook and the
  caller's prior modules are restored afterward, so mounted code cannot use embedded utilities.
- **The generated wiring names the console script, not a path:** in mode `package` the command
  is `"<anchor>/<venv>/bin/akmon" hook <name>`, where `<anchor>` is the vendor's project-root
  expression (`$CLAUDE_PROJECT_DIR` for Claude, `$(git rev-parse --show-toplevel)` for Codex).
  Mounted modes are unchanged: there the path is both spellable and pinned.
- **Exactly one thing is still materialized:** the guardrails the consumer's `AGENTS.md`
  actually `@`-imports, into `<AITNA_ROOT>/.akmon/guardrails/`. The reason is the **path**, not
  containment: the import lives in `AGENTS.md`, a committed hand-owned file, and the only path
  from there into the package carries the venv's Python version — the exact string this
  amendment removed from the wiring, failing harder, since an unresolved `@`-import produces no
  diagnostic in any harness. The names are read from `AGENTS.md` rather
  than derived from the recorded archetype, because the language guardrail is a hand-added line.
  What survives in the repository is the consumer's **rules**, not its plumbing, so the copy is
  held current from both ends — see the freshness consequence below.
- **Mode `package` requires a virtualenv inside the project root.** The wiring is a committed
  shared file, so an absolute path to whichever venv happened to run `sync` is a silent break
  for every other developer. `sync` never fails over a missing launcher (the first attach runs
  it before the pin is installed, by construction); `verify` reports it, in the consumer's CI.
- **Runtime-root resolution moves to the executing tree.** Hooks read their runtime files from
  `Path(__file__).parent.parent` — the carrier they are running from — instead of consulting the
  recorded `mount`. This supersedes D2-26 for that one function; see the
  [note](../design/packaging/mount-resolution-owner.md).

### Considered alternatives

- **Keep materializing the executable surface.** It existed for exactly one reason — the wiring
  named the hook by a path, and a path into the wheel carries the venv's Python version
  (`.venv/lib/python3.13/site-packages/...`), so it breaks on the next interpreter bump and on
  any differently laid out venv, silently, because a hook command the harness cannot find
  produces no output and no error. It was never a second implementation: the same stdlib-only
  files, ~20 of them, rewritten into the consumer's history on every version bump. Once the
  wiring can name a hook *without* a path, the reason is gone and the cost is not.
- **Keep it behind a flag, "just in case".** Rejected: two sources of the same executable files
  is precisely the divergence that is expensive and silent to debug later.
- **Import the guardrails straight out of the package too.** The package is not at a fixed
  location: on the pilot the tree resolves to `.venv/lib/python3.14/site-packages/akmon/_tree`,
  unstable in three places at once — the interpreter's minor version, the venv directory name,
  and `lib/pythonX.Y/site-packages` against Windows' `Lib/site-packages`. `AGENTS.md` is
  committed and hand-owned, so a literal path there is the same defect this amendment removed
  from the wiring, lodged where it reports even less: a hook command with a missing executable
  at least runs, while an unresolved `@`-import produces no diagnostic in any harness — and what
  would be lost is the always-on directives. (Containment is not the obstacle: Claude's import
  syntax accepts absolute paths, and Codex does not expand the import at all.) A gitignored
  **symlink** at `<AITNA_ROOT>/.akmon/guardrails`, rewritten by `sync`, would move the unstable
  string out of git while keeping the committed import path — at the cost of the one property
  the copy has: a fresh clone resolves the guardrails immediately, a link only after someone
  runs `sync`, and silently until then. It would also make symlink support a hard requirement,
  and whether a sandboxed harness follows a link out of the workspace is unverified. Rejected
  for two files, ~10 KB, whose diffs — unlike the hooks' — are the ones a consumer's reviewer
  wants to see: a guardrail change is a change to the rules the agents follow.
- **Solve "venv outside the project root" now.** Deferred. The right answer is a locator shim,
  not an absolute path in a committed file; until then the mode requires a project-local venv
  and `verify` says so.

### Consequences

- What stays in a package-mode consumer's repository: the local dev-layer assets
  (`<AITNA_ROOT>/{agents,skills,tools,memory}`, `TASKS.md`), the imported guardrails under
  `<AITNA_ROOT>/.akmon/guardrails/`, the integration record, and the generated vendor pointers.
  A version-number-only change does not rewrite the guardrails. A bump that changes an imported
  guardrail or generated vendor pointer changes that checked-in file through `sync`; it never
  rewrites a copied executable surface, because none exists.
- `sync` removes a previous version's materialization in one run, including the routing
  registry (which never carried a banner — it must stay parseable JSON), the emptied
  directories, and the `__pycache__` a hook run left behind. The bytecode is swept silently:
  having executed a hook since the last sync is not drift, and reporting it would fail
  `sync --check` in CI.
- `verify` gains `hooks.launcher` (package mode: the console script the wiring names must be a
  regular executable file) and stops short-circuiting its hook check in package mode — the
  scripts' presence in the tree is now what the wiring rests on.
- Package-mode skill stubs and the hooks' recovery instructions reach the standard through
  `akmon path`, never through a version-carrying site-packages path.
- **During package execution, a bump that changes a guardrail is announced in the session, not
  only in CI.** Mounted execution imports from its mount directly, so a leftover package copy is
  inactive and does not warn. `sync
  --check` and `verify` already compare the copy against the installed tree, but they run on a
  commit; the window they cannot see opens earlier and closes silently — a pin bump installs the
  new hooks the instant the dependency resolves, and they run from the package, while the
  repository still holds the previous release's rules. SessionStart now names the files, asks for
  `akmon sync`, and asks for a **new session**: the `@`-import is expanded once, when the session
  starts, so a mid-session sync fixes the file and changes nothing already in context. The
  comparison is against the tree the hook is executing from rather than a recorded version
  string, so a release that leaves the guardrails untouched stays quiet and a hand-edited copy
  does not. It rides `session_start_result`, the SessionStart logic both vendor wirings already
  call, so it needs no new hook and no regenerated wiring — which matters, because a changed
  `.codex/hooks.json` invalidates the host's approval of every group in it. On Codex it arrives
  as context only; that runtime has no documented owner-facing channel.
- The banner rule and the materialized-guardrail format move to `common/materialization.py`, so
  the writer (`sync`) and the judge (`hook_core`) cannot disagree about what "current" means —
  the same one-owner rule the record reader was given at C69/D2-26.
- **Measured on the alphavar pilot** (Python 3.14 venv, median of 30–40 runs), because the
  in-process choice above is only defensible if the residue is small. Running a hook through
  `akmon hook <name>` costs **+3.1 ms** over running the file directly. Getting there took three
  deferrals on the dispatch path, each of which was larger than the dispatch itself:
  `akmon.__version__` made lazy (PEP 562 — `importlib.metadata.version()` walks every installed
  distribution: **89 ms**), `importlib.resources` in `akmon/_tree.py` reached only when the
  data is not a plain directory beside the module (**~45 ms**, it pulls `inspect`, `typing`,
  `tempfile`), and `argparse` (~18 ms) plus `subprocess` (~12 ms) imported where they are used,
  with `main` dispatching `hook` before it builds a parser. `import akmon.cli` fell from 88 ms
  to 32 ms. None of this was visible while the package was a command a human typed; the wiring
  puts it on every tool call.
