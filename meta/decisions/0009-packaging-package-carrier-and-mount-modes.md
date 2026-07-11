# 0009 — Packaging: the `akmon` package as carrier, four mount modes incl. `package`

- **Status:** Accepted — owner-locked (D2-12 verified; backlog A10 done). Implementation
  is [C37](../TASKS.md).
- **Owner:** akuminov@gmail.com
- **References:** design [packaging-uvx-init.md](../design/packaging-uvx-init.md) (options
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
   stdlib-only property is a contract — verify asserts it); Python floor **3.9**. Package
   version == standard version, cut from the same release tag (no separate version line).
2. **PyPI name — `akmon`** (checked free, as is `ai-akmon`; register at first publish).
3. **Mount modes — `submodule | vendored | subtree | package`.** Default unchanged:
   `submodule` for a git repo with network, else `vendored`, always printed. `package` is
   an explicit choice.
4. **Mode `package`:** the consumer pins akmon as a **dev**-group dependency (git-tag pin
   via `git+https` until the first publish, PyPI after); no tree at `<AITNA_ROOT>/akmon`.
   `akmon sync` materializes the **always-on surface only** — `hooks/` (self-contained,
   stdlib-only, venv-free) and `guardrails/` (the AGENTS.md @-import targets) — into
   `<AITNA_ROOT>/.akmon/`, banner-marked and drift-checked by `sync --check`. Tree
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
  `_aitna/.akmon/{hooks,guardrails}` + `.akmon.toml` checked in — no 90-file tree; the pin
  bump becomes an ordinary dependency bump reviewed like any other (C2's subject).
- The tools grow mount-awareness (root discovery, hook templating, tree resolution) —
  C37 scope; consumer docs must link the standard by GitHub-tag URL or via `akmon path`
  instead of relative mount paths.
- Consumer CI stops running the standard's own self-tests (`self_ci.py`, `meta/tests`) —
  those move to ai_akmon's CI; the consumer keeps `sync --check` + `verify --strict`.
- Non-Python consumers and the co-development workflow stay design open points
  (packaging-uvx-init.md §Open points) — nothing here blocks them.
