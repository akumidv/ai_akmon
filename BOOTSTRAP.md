# BOOTSTRAP — attaching keystone to a project

Instructions for the **agent** (Claude / Codex / Gemini) asked to attach or realign the
keystone layer in a project. Also carries **ready prompts for the user**.

Source of rules: [README.md](README.md) (the three axes, the layer decision tree, the
learn loop) and [ARCHETYPES.md](ARCHETYPES.md) (archetypes + the guardrail/profile
map). Note: keystone does **not** exist in the target project until step 1 — the shared
layer lives only in the repo `ai_keystone` and must be cloned in as a submodule **first**.
The agent reads `README.md` only after the submodule is attached.

---

## A. What the agent does on attach

`_forge/` below is the **default** dev-layer root. A project may relocate it by declaring
`FORGE_ROOT` (a project-root-relative path, e.g. `tools/ai`); keystone then mounts at
`<FORGE_ROOT>/keystone` and the tooling derives every path from it. If `FORGE_ROOT` is set,
export it in the shell before running `sync.py` / `verify.py` (and substitute it for `_forge/`
in the mount path and the steps below). Unset → `_forge`.

When the user asks "attach keystone", the agent:

1. **Attach the shared layer as a submodule** (mount path `<FORGE_ROOT>/keystone`, default
   `_forge/keystone`, repo `ai_keystone` — skip if the prompt already ran it):
   ```bash
   git submodule add --name _forge/keystone \
     https://github.com/akumidv/ai_keystone _forge/keystone
   git submodule update --init --recursive
   ```
2. **Read** `_forge/keystone/README.md` in full (now present).
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
   _forge/agents/        _forge/skills/   _forge/tools/   _forge/memory/   _forge/TASKS.md
   ```
   and, if the archetype exports USAGE (e.g. `package`), the root `skills/`.

   **Dev-layer venv (non-Python projects only).** If the archetype **language is not
   `python`/`mixed`**, the project has no Python environment, yet some agent tooling needs
   one (e.g. running the keystone unit tests via `pytest`, or any future tool with a
   third-party dep). Provision a dedicated dev-layer venv at **`_forge/.venv`** (in the LOCAL
   layer, *outside* the submodule so it survives a submodule re-checkout) and install the
   agent-tooling deps. **Prefer `uv`** — it bundles its own installer and provisions a usable
   venv in one step on a host with no Python packaging set up:
   ```bash
   uv venv _forge/.venv
   uv pip install --python _forge/.venv/bin/python pytest
   ```
   Stdlib fallback **only if `uv` is unavailable** — note `python3 -m venv` needs the `venv`/
   `ensurepip` stdlib module, which is a *separate OS package* (`python3-venv`) often absent on
   a non-Python host; install it first, or the venv lands without `pip`:
   ```bash
   python3 -m venv _forge/.venv          # requires python3-venv installed
   _forge/.venv/bin/python -m pip install pytest
   ```
   `pytest` is the only dep today (add more here as agent tools acquire deps). On a
   **Python** project this step is skipped — the project's own env already supplies pytest.
   The consumer's own CI checks (`sync.py --check`, `verify.py --strict`) are stdlib-only and
   never need this venv; it exists for *developing* the dev layer (the keystone-dev validator
   and any future deps-bearing tool). Add `_forge/.venv/` to `.gitignore` (§D).
6. **Generate or update `AGENTS.md`** (§C template), preserving existing content. The
   keystone block records the archetype + language, the SHARED/LOCAL/USAGE declaration,
   the USAGE placement, and the **resolved guardrail/profile links** from step 4 (written
   out, so they aren't recomputed each session). This block *is* the attach record.
   Then **generate/refresh the vendor pointers** (§C): for Claude Code write a `CLAUDE.md`
   that **imports** AGENTS.md via `@AGENTS.md` — Claude Code auto-loads `CLAUDE.md` but
   **not** `AGENTS.md`, so the import makes the canonical rules (including the always-on
   D2/D5 and "read `_forge/memory/` at session start") present at session start instead of
   one hop behind a prose pointer.
7. **Update `.gitignore`** for secrets (see §D).
8. **Wire the hooks** ([`hooks/README.md`](hooks/README.md)) into vendor config, pointing
   at the keystone paths. `sync.py` keeps the supported project-local wiring current:
   - **Claude Code** — `.claude/settings.json`: commit guard, session-start agent,
     role-on-code, and analysis-guard.
   - **Codex** — `.codex/hooks.json`: session-start, role-on-code, and analysis-guard
     reminders. Codex project-local hooks require the project `.codex/` layer to be trusted
     and reviewed with `/hooks`.

   Guardrail logic lives once in `hooks/hook_core.py`; vendor files only adapt payload/output
   and wiring. The rules they back also live in `AGENTS.md` (§C), so assistants still follow
   the rules by reading the doc if a vendor has no hook surface.
9. **Run** `python3 _forge/keystone/bin/sync.py --check`; if it reports stale generated
   pointers, run `python3 _forge/keystone/bin/sync.py` and review the diff. Then run
   `python3 _forge/keystone/bin/verify.py --strict` to validate the keystone project
   contract.
10. **Does NOT commit** — reports it is ready for review. The owner commits `.gitmodules`,
    the keystone pin, hand-reviewed source docs (`AGENTS.md`, role/guardrail/pipeline docs),
    and the generated pointer files covered by §D.

Generated pointer files are committed because they are deterministic, thin entry points
that make a fresh clone usable by each assistant before any local regeneration step runs.
Add `python3 _forge/keystone/bin/sync.py --check` and
`python3 _forge/keystone/bin/verify.py --strict` to the project's CI/preflight checks so
pointer drift and structural contract drift fail before merge.

---

## B. Ready prompts for the user

### B1. New project

```
Attach keystone to this project.
First add the shared layer as a git submodule:
  git submodule add --name _forge/keystone https://github.com/akumidv/ai_keystone _forge/keystone
  git submodule update --init --recursive
Then read _forge/keystone/BOOTSTRAP.md and follow section A (it points to README.md for
the model and ARCHETYPES.md for the archetype). Do not commit.
```

### B2. Existing project (already has AGENTS.md / CLAUDE.md)

```
Attach keystone without breaking the current docs.
First add the submodule:
  git submodule add --name _forge/keystone https://github.com/akumidv/ai_keystone _forge/keystone
  git submodule update --init --recursive
Then read _forge/keystone/BOOTSTRAP.md and follow section A. Keep all existing AGENTS.md
content — add/update ONLY the keystone block (§C). Also ensure CLAUDE.md imports AGENTS.md
via `@AGENTS.md` (§C) so the always-on rules load at session start. Show the diff, do not commit.
```

---

## C. Section template for AGENTS.md

The agent inserts/updates this block in the project root `AGENTS.md`. Links are relative
to the project root.

```markdown
## Dev layer — keystone (developing the project)

This project uses the keystone dev layer. Model & notation:
[_forge/keystone/README.md](_forge/keystone/README.md).

- **Archetype / language:** `<package|service|mcp|frontend|job|platform|custom>` /
  `<python|js|mixed|other>` — owner `<name>`. Rules:
  [ARCHETYPES.md](_forge/keystone/ARCHETYPES.md).
- **Layers (README §2):** SHARED = `_forge/keystone/` · LOCAL =
  `_forge/{skills,tools,memory,agents}/` · USAGE = root `skills/` (`<none>` if not
  exposed).
- **Agents (roles):** [architect](_forge/agents/architect/README.md),
  [engineer](_forge/agents/engineer/README.md) → roles:
  [keystone/roles/](_forge/keystone/roles/). **Declare the active agent** before doing work
  and restate it on switch (`🧭 agent: <name> — <focus>`) — see
  [Role declaration](_forge/keystone/roles/README.md#role-declaration-announce-the-active-agent).
- **Guardrails (applied — by language):** [_common](_forge/keystone/guardrails/_common.md)
  <!-- + the language guardrail(s) per the map, e.g. [python](_forge/keystone/guardrails/python.md) -->
- **Profiles (applied — opt-in by need):**
  <!-- only the profiles this project actually uses, e.g.
       - [quant](_forge/keystone/profiles/quant.md) — numerics -->
- **Pipelines:** [pre-commit](_forge/keystone/pipelines/pre-commit.md) (tests mandatory),
  [design-flow](_forge/keystone/pipelines/design-flow.md),
  [code-flow](_forge/keystone/pipelines/code-flow.md),
  [tasks](_forge/keystone/pipelines/tasks.md) (backlog format),
  [memory-distill](_forge/keystone/pipelines/memory-distill.md) +
  [learning](_forge/keystone/pipelines/learning.md) (the learn loop).
- **Backlog:** [_forge/TASKS.md](_forge/TASKS.md) — index format per
  [tasks](_forge/keystone/pipelines/tasks.md) (one line/task, detail by reference; done →
  `TASKS_ARCHIVE.md`). **Secrets:** from `.env` (gitignored).
```

For **Codex/Gemini** this AGENTS.md block is enough — they read `AGENTS.md` directly.
**Claude Code does not** read `AGENTS.md` automatically; it only auto-loads `CLAUDE.md`. So
`CLAUDE.md` must **import** AGENTS.md rather than just prose-point at it — otherwise the
always-on rules (D2/D5) sit one hop behind a pointer the agent may never follow in a session
that jumps straight to a task:

```markdown
# CLAUDE.md

This project uses [AGENTS.md](AGENTS.md) as the single source of guidance for AI coding
agents (including Claude Code).

Claude Code auto-loads `CLAUDE.md` but **not** `AGENTS.md`, so AGENTS.md is imported below.
This keeps the canonical rules — including the always-on prime directives (D2, D5) and
"read `_forge/memory/` at session start" — present in context from the start.

@AGENTS.md
```

Mechanically-enforced rules (e.g. D5 via the commit-guard hook, step 8) hold regardless;
the import covers the rules that rely on the agent having *read* them (D2, memory). The
`.claude/skills/` pointers also apply (written by `sync.py`).

---

## D. .gitignore (project root)

```
# secrets
*.env
!*.env.example

# dev-layer venv (non-Python projects; provisioned in §A step 5)
_forge/.venv/
```

`_forge/memory/` is **committed** (shared project memory). `_forge/keystone/` is the
submodule. `_forge/.venv/` (if provisioned) is **local-only** — a per-checkout dev tool
environment, never committed.

**Generated pointer commit policy.** Files written by
`python3 _forge/keystone/bin/sync.py` are deterministic pointers, not sources of truth.
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

**CI/preflight check.** A keystone-consuming project should run:

```bash
python3 _forge/keystone/bin/sync.py --check
python3 _forge/keystone/bin/verify.py --strict
```

Both commands are stdlib-only and can run immediately after checkout, before dependency
installation. `sync.py --check` exits non-zero when generated pointers are stale or
missing; `verify.py --strict` validates the wider keystone structure and treats warnings
as failures for CI.

---

## E. Submodule lifecycle (repo: `ai_keystone`, mount `_forge/keystone`)

### Clone a project that already has it
```bash
git clone --recurse-submodules <project-url>
# or after a plain clone:
git submodule update --init --recursive
```

### Pull the latest shared layer into a project
Before bumping, **read keystone's [CHANGELOG.md](CHANGELOG.md)** for the target version to see
what changed and whether it breaks you (`v0.x.y`: a bumped `x` is breaking). This is the consumer side of the
[release](roles/release.md) cycle; the bump itself is a release **subject** ("keystone pin bump").
```bash
git submodule update --remote _forge/keystone
python3 _forge/keystone/bin/sync.py          # refresh generated pointers
python3 _forge/keystone/bin/sync.py --check  # confirm no pointer drift
python3 _forge/keystone/bin/verify.py --strict
# Codex only: open /hooks and review/trust changed project-local hooks after .codex/hooks.json changes
git add _forge/keystone CLAUDE.md GEMINI.md .codex .github/copilot-instructions.md .claude/settings.json .claude/skills
git commit -m "bump keystone"             # owner commits if the pin/pointers moved
```
**Record the bump** in the consuming project (a `_forge/TASKS_ARCHIVE.md` line or the project's
own changelog) — the **downstream bump record** lives in the consumer, not in keystone's notes.

### Edit the shared layer itself (changes go to ai_keystone)
Edits **inside** `_forge/keystone/` belong to the `ai_keystone` repo. Commit + push there,
then bump the pin in each consuming project. This is the **PROMOTE/PROPAGATE** end of the
learn loop ([learning](pipelines/learning.md)).

### Promote a local asset to shared
Move it from `_forge/{skills,tools}/` into `_forge/keystone/{skills,tools}/` (or a
role/guardrail/profile into the matching keystone dir), commit + push in `ai_keystone`,
then bump the pin in consuming projects. Apply the **promotion test** first: general *and*
proven (see [learning](pipelines/learning.md)).
