# BOOTSTRAP — attaching akmon to a project

Instructions for the **agent** (Claude / Codex / Gemini) asked to attach or realign the
akmon layer in a project. Also carries **ready prompts for the user**.

Source of rules: [README.md](README.md) (the three axes, the layer decision tree, the
learn loop) and [ARCHETYPES.md](ARCHETYPES.md) (archetypes + the guardrail/profile
map). Note: akmon does **not** exist in the target project until step 1 — the shared
layer lives only in the repo `ai_akmon` and must be cloned in as a submodule **first**.
The agent reads `README.md` only after the submodule is attached.

The submodule is the default **mount mode**; a tree-less `package` mode — akmon installed
as a pinned dev dependency, no standard tree in the repo — is designed and pending
implementation, see §F.

---

## A. What the agent does on attach

`_aitna/` below is the **default** dev-layer root. A project may relocate it by declaring
`AITNA_ROOT` (a project-root-relative path, e.g. `tools/ai`); akmon then mounts at
`<AITNA_ROOT>/akmon` and the tooling derives every path from it. If `AITNA_ROOT` is set,
export it in the shell before running `sync.py` / `verify.py` (and substitute it for `_aitna/`
in the mount path and the steps below). Unset → `_aitna`.

When the user asks "attach akmon", the agent:

1. **Attach the shared layer as a submodule** (mount path `<AITNA_ROOT>/akmon`, default
   `_aitna/akmon`, repo `ai_akmon` — skip if the prompt already ran it):
   ```bash
   git submodule add --name _aitna/akmon \
     https://github.com/akumidv/ai_akmon _aitna/akmon
   git submodule update --init --recursive
   ```
2. **Read** `_aitna/akmon/README.md` in full (now present).
3. **Classify the project** ([ARCHETYPES.md](ARCHETYPES.md)): pick the **archetype ID** by
   the contract it exposes and the **language**. Inspect `pyproject.toml` / `package.json`,
   any root `skills/`, the runtime entry points. Record the decision if a non-default
   language changes the contract.
4. **Resolve guardrails + profiles** from the map in [ARCHETYPES.md](ARCHETYPES.md):
   language guardrails are automatic; archetype-suggested profiles (`quant`, `crypto`, …)
   attach **only if the project has that concern** — confirm each. Result: a concrete list
   of links.
5. **Create the local layout** if missing:
   ```
   _aitna/agents/        _aitna/skills/   _aitna/tools/   _aitna/memory/   _aitna/TASKS.md
   ```
   and, if the archetype exports USAGE (e.g. `package`), the root `skills/`.

   **Pin the test environment (`[test].runner`).** Some agent tooling needs Python with `pytest`
   (e.g. the akmon unit tests, or any future deps-bearing tool). **Use what the project already
   has; only build a venv when there is none.** Decide the runner once, here, and record it in the
   integration record (`[test].runner` in `<AITNA_ROOT>/.akmon.toml`, §C) so `release_check` uses
   it verbatim rather than guessing per-run — `uv` may be absent, and a Python project usually has
   its own manager:
   - **Python / mixed project** — it already supplies `pytest` through its own manager
     (poetry / pdm / pip-venv / conda / uv). **Do not build `_aitna/.venv`.** Pin that manager,
     e.g. `runner = "poetry run pytest"`, `runner = ".venv/bin/python -m pytest"`.
   - **Non-Python project** (no Python env at all) — provision a dedicated dev-layer venv at
     **`_aitna/.venv`** (LOCAL layer, *outside* the submodule so it survives a submodule
     re-checkout) and install the agent-tooling deps, then pin
     `runner = "_aitna/.venv/bin/python -m pytest"`. Build it with whatever is available:
     ```bash
     uv venv _aitna/.venv && uv pip install --python _aitna/.venv/bin/python pytest   # if uv present
     python3 -m venv _aitna/.venv && _aitna/.venv/bin/python -m pip install pytest     # stdlib fallback
     ```
     `python3 -m venv` needs the `venv`/`ensurepip` stdlib module (a *separate OS package*,
     `python3-venv`, often absent on a non-Python host) — install it first or the venv lands
     without `pip`. Add `_aitna/.venv/` to `.gitignore` (§D).

   Pin the runner as `<interpreter> -m pytest`, **not** a venv's `bin/pytest` console script — that
   script bakes an absolute-path shebang at creation and breaks if the venv is relocated. `pytest`
   is the only agent-tooling dep today (add more to the chosen env as tools acquire deps). The
   consumer's own contract checks (`sync.py --check`, `verify.py --strict`) are stdlib-only and
   never need any of this; the test env exists for *developing* the dev layer.
6. **Generate or update `AGENTS.md`** (§C template), preserving existing content. The
   akmon block records the archetype + language, the SHARED/LOCAL/USAGE declaration,
   the USAGE placement, and the **resolved guardrail/profile links** from step 4 (written
   out, so they aren't recomputed each session). This block *is* the prose attach record.

   **Write the machine-readable integration record** `<AITNA_ROOT>/.akmon.toml` (§C) — the
   version this project sits on, so a later bump can diff the CHANGELOG (see "Pull the latest
   shared layer"). `sync.py` cannot generate it (it is stdlib-only and cannot run `git`), so the
   agent writes it here, reading the version (tag-anchored, SHA-suffixed only between tags) from
   the submodule:
   ```bash
   git -C _aitna/akmon describe --tags        # → akmon_version + last_realign
   ```
   On a **realign/bump** of an existing project, refresh `akmon_version` and `last_realign` to
   the new `describe` value after the delta-check passes.

   Then **generate/refresh the vendor pointers** (§C): for Claude Code write a `CLAUDE.md`
   that **imports** AGENTS.md via `@AGENTS.md` — Claude Code auto-loads `CLAUDE.md` but
   **not** `AGENTS.md`, so the import makes the canonical rules (including the always-on
   D2/D5 and "read `_aitna/memory/` at session start") present at session start instead of
   one hop behind a prose pointer.
7. **Update `.gitignore`** for secrets (see §D).
8. **Wire the hooks** ([`hooks/README.md`](hooks/README.md)) into vendor config, pointing
   at the akmon paths. `sync.py` keeps the supported project-local wiring current:
   - **Claude Code** — `.claude/settings.json`: commit guard, session-start agent,
     role-on-code, and analysis-guard.
   - **Codex** — `.codex/hooks.json`: session-start, role-on-code, and analysis-guard
     reminders. Codex project-local hooks require the project `.codex/` layer to be trusted
     and reviewed with `/hooks`.

   Guardrail logic lives once in `hooks/hook_core.py`; vendor files only adapt payload/output
   and wiring. The rules they back also live in `AGENTS.md` (§C), so assistants still follow
   the rules by reading the doc if a vendor has no hook surface.
9. **Run** `python3 _aitna/akmon/bin/sync.py --check`; if it reports stale generated
   pointers, run `python3 _aitna/akmon/bin/sync.py` and review the diff. Then run
   `python3 _aitna/akmon/bin/verify.py --strict` to validate the akmon project
   contract.
10. **Does NOT commit** — reports it is ready for review. The owner commits `.gitmodules`,
    the akmon pin, hand-reviewed source docs (`AGENTS.md`, role/guardrail/pipeline docs),
    and the generated pointer files covered by §D.

Generated pointer files are committed because they are deterministic, thin entry points
that make a fresh clone usable by each assistant before any local regeneration step runs.
Add `python3 _aitna/akmon/bin/sync.py --check` and
`python3 _aitna/akmon/bin/verify.py --strict` to the project's CI/preflight checks so
pointer drift and structural contract drift fail before merge.

---

## B. Ready prompts for the user

### B1. New project

```
Attach akmon to this project.
First add the shared layer as a git submodule:
  git submodule add --name _aitna/akmon https://github.com/akumidv/ai_akmon _aitna/akmon
  git submodule update --init --recursive
Then read _aitna/akmon/BOOTSTRAP.md and follow section A (it points to README.md for
the model and ARCHETYPES.md for the archetype). Do not commit.
```

### B2. Existing project (already has AGENTS.md / CLAUDE.md)

```
Attach akmon without breaking the current docs.
First add the submodule:
  git submodule add --name _aitna/akmon https://github.com/akumidv/ai_akmon _aitna/akmon
  git submodule update --init --recursive
Then read _aitna/akmon/BOOTSTRAP.md and follow section A. Keep all existing AGENTS.md
content — add/update ONLY the akmon block (§C). Also ensure CLAUDE.md imports AGENTS.md
via `@AGENTS.md` (§C) so the always-on rules load at session start. Show the diff, do not commit.
```

---

## C. Section template for AGENTS.md

The agent inserts/updates this block in the project root `AGENTS.md`. Links are relative
to the project root.

```markdown
## Dev layer — akmon (developing the project)

This project uses the akmon dev layer. Model & notation:
[_aitna/akmon/README.md](_aitna/akmon/README.md).

- **Archetype / language:** `<package|service|mcp|frontend|job|platform|custom>` /
  `<python|js|mixed|other>` — owner `<name>`. Rules:
  [ARCHETYPES.md](_aitna/akmon/ARCHETYPES.md).
- **Layers (README §2):** SHARED = `_aitna/akmon/` · LOCAL =
  `_aitna/{skills,tools,memory,agents}/` · USAGE = root `skills/` (`<none>` if not
  exposed).
- **Agents (roles):** [architect](_aitna/agents/architect/README.md),
  [engineer](_aitna/agents/engineer/README.md) → roles:
  [akmon/roles/](_aitna/akmon/roles/). **Declare the active agent** before doing work
  and restate it on switch (`🧭 agent: <name> — <focus>`) — see
  [Role declaration](_aitna/akmon/roles/README.md#role-declaration-announce-the-active-agent).
- **Delegation (always-on, direct):** **delegation is the default.** For every non-trivial
  task, before the first repository sweep, edit, or test run, decompose the work and delegate
  every independent mechanical sub-step to available subagents without waiting for an owner
  prompt. The orchestrator retains decomposition, routing, synthesis, and owner dialogue. Skip
  only when the task is atomic or the harness exposes no subagents; state the reason. This clause
  is direct because Codex does not expand nested `@` imports in `AGENTS.md`.
- **Guardrails (always-on, by language):** the common guardrail is **imported** (not just
  linked) so its always-on rules load into context at session start. Put each `@`-import on its
  own line, blank-line-separated; akmon is the single owner — do not restate the rules here.

@_aitna/akmon/guardrails/_common.md

  <!-- + each language guardrail per the ARCHETYPES map, on its own line, e.g.
       @_aitna/akmon/guardrails/python.md
       Only guardrails are imported (always-on). Roles/MODEL/pipelines stay links below
       (on-demand) — pulled when an agent enters a role or runs a pipeline, not every session. -->
- **Profiles (applied — opt-in by need):**
  <!-- only the profiles this project actually uses, e.g.
       - [quant](_aitna/akmon/profiles/quant.md) — numerics -->
- **Pipelines:** [pre-commit](_aitna/akmon/pipelines/pre-commit.md) (tests mandatory),
  [design-flow](_aitna/akmon/pipelines/design-flow.md),
  [code-flow](_aitna/akmon/pipelines/code-flow.md),
  [tasks](_aitna/akmon/pipelines/tasks.md) (backlog format),
  [memory-distill](_aitna/akmon/pipelines/memory-distill.md) +
  [learning](_aitna/akmon/pipelines/learning.md) (the learn loop).
- **Backlog:** [_aitna/TASKS.md](_aitna/TASKS.md) — index format per
  [tasks](_aitna/akmon/pipelines/tasks.md) (one line/task, detail by reference; done →
  `TASKS_ARCHIVE.md`). **Secrets:** from `.env` (gitignored).
```

For **Codex/Gemini**, the direct text in this AGENTS.md block is the operative surface.
Do not assume nested `@path` lines are expanded by either harness; load-bearing rules such as
delegation must be stated directly and verified. **Claude Code does not** read `AGENTS.md`
automatically; it only auto-loads `CLAUDE.md`. So
`CLAUDE.md` must **import** AGENTS.md rather than just prose-point at it — otherwise the
always-on rules (D2/D5) sit one hop behind a pointer the agent may never follow in a session
that jumps straight to a task:

```markdown
# CLAUDE.md

This project uses [AGENTS.md](AGENTS.md) as the single source of guidance for AI coding
agents (including Claude Code).

Claude Code auto-loads `CLAUDE.md` but **not** `AGENTS.md`, so AGENTS.md is imported below.
This keeps the canonical rules — including the always-on prime directives (D2, D5) and
"read `_aitna/memory/` at session start" — present in context from the start.

@AGENTS.md
```

Mechanically-enforced rules (e.g. D5 via the commit-guard hook, step 8) hold regardless;
the import covers the rules that rely on the agent having *read* them (D2, memory). The
`.claude/skills/` pointers also apply (written by `sync.py`).

### Integration record — `<AITNA_ROOT>/.akmon.toml`

The machine-readable companion to the AGENTS.md akmon block: the akmon **version** this
project was attached/realigned against, plus the pinned test environment. The agent writes it
(step 6); `verify.py` reads it; a bump diffs it against the CHANGELOG ("Pull the latest shared
layer"). **Committed, not gitignored** — it travels with the repo and shows in the bump diff.
TOML (read with `tomllib`, or a stdlib line-parser fallback when the host Python is < 3.11):

```toml
akmon_version = "v0.2.0"        # `git -C _aitna/akmon describe --tags`
attached_archetype = "frontend/js" # archetype/language from the akmon block
last_realign = "v0.2.0"            # version of the last attach/realign (== akmon_version after a clean bump)

[test]
runner = "poetry run pytest"       # optional — the test env pinned at attach (§A5); release_check uses it verbatim
```

`akmon_version` comes from `git describe --tags`: **the tag is the anchor**. Describe appends
`-N-gSHA` on its own when the submodule sits *between* tags, so the commit hash rides along only
when it adds information — there is no separate pin field to keep in sync, and no chicken-and-egg
(the version is recorded *after* the submodule is on the target commit, when the tag/SHA exist).

`[test].runner` is **optional**: when present, `release_check` runs it verbatim (append the test
path) instead of discovering one; when absent it falls back to discovery (dev venv → system
pytest → uv). Pin it as `<interpreter> -m pytest` or a manager invocation (`poetry run pytest`),
never a venv `bin/pytest` console script (stale-shebang on relocation).

It lives in the LOCAL layer (`<AITNA_ROOT>/`, **outside** the submodule) so it survives a
submodule re-checkout, and is **not** linked from AGENTS.md — so it stays out of context during
development and is read only at attach/verify/bump time.

---

## D. .gitignore (project root)

```
# secrets
*.env
!*.env.example

# dev-layer venv (non-Python projects; provisioned in §A step 5)
_aitna/.venv/

# akmon model routing — per-user/per-session artifacts (never committed)
.claude/model-routing.local.json
.claude/model-routing.log
.claude/second-opinion/
# generated k-* subagent defs: model: frontmatter is per-user (follows the local
# orchestrator) and is regenerated by the model-routing hook — tracking them would churn
.claude/agents/k-*.md
```

`_aitna/memory/` is **committed** (shared project memory). `_aitna/akmon/` is the
submodule. `_aitna/.venv/` (if provisioned) is **local-only** — a per-checkout dev tool
environment, never committed.

**Generated pointer commit policy.** Files written by
`python3 _aitna/akmon/bin/sync.py` are deterministic pointers, not sources of truth.
They are still **committed** so every assistant sees the same entry points on a fresh
clone:

- `CLAUDE.md`
- `GEMINI.md`
- `.codex/README.md`
- `.codex/hooks.json` (project hook wiring only)
- `.github/copilot-instructions.md`
- `.claude/settings.json` (project hook wiring only)
- `.claude/skills/*/SKILL.md` stubs

Do **not** commit vendor-local state or secrets: `.claude/settings.local.json`, caches,
logs, credentials, and real `.env` files stay local/gitignored. `AGENTS.md` is not
generated by `sync.py`; it remains a hand-reviewed source document.

**CI/preflight check.** A akmon-consuming project should run:

```bash
python3 _aitna/akmon/bin/sync.py --check
python3 _aitna/akmon/bin/verify.py --strict
```

Both commands are stdlib-only and can run immediately after checkout, before dependency
installation. `sync.py --check` exits non-zero when generated pointers are stale or
missing; `verify.py --strict` validates the wider akmon structure and treats warnings
as failures for CI.

---

## E. Submodule lifecycle (repo: `ai_akmon`, mount `_aitna/akmon`)

### Clone a project that already has it
```bash
git clone --recurse-submodules <project-url>
# or after a plain clone:
git submodule update --init --recursive
```

### Pull the latest shared layer into a project
This is the consumer side of the [release](roles/release.md) cycle; the bump itself is a release
**subject** ("akmon pin bump").

**Delta-check first (what to verify, not where it is stored).** The delta-check is a *procedure*,
not stored data — it computes a version window and reads the changes from the CHANGELOG; it never
keeps its own copy of them (the CHANGELOG is the single owner of "what changed"):
1. `from` = `akmon_version` in `<AITNA_ROOT>/.akmon.toml` — where the project sits now.
2. `to` = `git -C _aitna/akmon describe --tags` after `git submodule update --remote` — the target.
3. In [CHANGELOG.md](CHANGELOG.md), read only the version sections in the window `(from, to]`
   (`v0.x.y`: a bumped `x` is breaking). Everything `≤ from` is already applied; skip it.
4. Each **`Breaking`/`migration`** line in that window is a **checklist item** — verify the project
   satisfies it (e.g. a new required file, a renamed path, a changed contract). `Added`/`Fixed`
   lines need no action.
5. Realign per §A (refresh the akmon block, re-run `sync.py`), then update `.akmon.toml`
   (`akmon_version` and `last_realign`) to `to`.
```bash
git submodule update --remote _aitna/akmon
python3 _aitna/akmon/bin/sync.py          # refresh generated pointers
python3 _aitna/akmon/bin/sync.py --check  # confirm no pointer drift
python3 _aitna/akmon/bin/verify.py --strict
# Codex only: open /hooks and review/trust changed project-local hooks after .codex/hooks.json changes
git add _aitna/akmon CLAUDE.md GEMINI.md .codex .github/copilot-instructions.md .claude/settings.json .claude/skills
git commit -m "bump akmon"             # owner commits if the pin/pointers moved
```
**Record the bump** in the consuming project (a `_aitna/TASKS_ARCHIVE.md` line or the project's
own changelog) — the **downstream bump record** lives in the consumer, not in akmon's notes.

### Edit the shared layer itself (changes go to ai_akmon)
Edits **inside** `_aitna/akmon/` belong to the `ai_akmon` repo. Commit + push there,
then bump the pin in each consuming project. This is the **PROMOTE/PROPAGATE** end of the
learn loop ([learning](pipelines/learning.md)).

### Promote a local asset to shared
Move it from `_aitna/{skills,tools}/` into `_aitna/akmon/{skills,tools}/` (or a
role/guardrail/profile into the matching akmon dir), commit + push in `ai_akmon`,
then bump the pin in consuming projects. Apply the **promotion test** first: general *and*
proven (see [learning](pipelines/learning.md)).

---

## F. Mount mode `package` — no standard tree in the repo *(designed, pending implementation)*

> **Status:** designed, pending implementation — ships with the `akmon` CLI; pilot
> consumer: alphavar. Until it ships, attach via the submodule (§A). The decision record
> and mechanics live in the standard's own development tree (linked from
> [README.md](README.md), the deliberate bridge).

Alongside the mounted modes (`submodule` — this document's default — plus `vendored` and
`subtree`), akmon will install as an ordinary dev dependency, with **no tree at
`<AITNA_ROOT>/akmon`**:

- The consumer pins akmon in its manifest's **dev group** (never a runtime dep) — a
  git-tag pin `akmon @ git+https://github.com/akumidv/ai_akmon@vX.Y.Z` until the first
  PyPI publish, the `akmon` PyPI package after. A version bump becomes an ordinary
  dependency bump, delta-checked against [CHANGELOG.md](CHANGELOG.md) as usual.
- `akmon sync` materializes the **always-on surface only** into `<AITNA_ROOT>/.akmon/`:
  `hooks/` (self-contained, stdlib-only — vendor hooks keep running venv-free via
  `python3`) and `guardrails/` (the `@`-import targets for AGENTS.md). The copies are
  banner-marked and drift-checked by `sync --check`.
- Everything else (MODEL.md, roles, pipelines, skills) is read from the installed
  package's embedded tree — `akmon path` prints its root; consumer docs link the standard
  by GitHub-tag URL instead of relative mount paths.
- `.akmon.toml` records `mount = "package"`; the CLI and the standard share one version
  cut from the release tag, so there is **no version skew by construction**.
- Checked in: `_aitna/{local assets}` + `_aitna/.akmon/{hooks,guardrails}` +
  `.akmon.toml` — no 90-file tree. Consumer CI runs `uv run akmon sync --check` and
  `uv run akmon verify --strict`; the standard's own self-tests stay in ai_akmon's CI.
