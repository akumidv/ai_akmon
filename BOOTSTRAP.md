# BOOTSTRAP — attaching keystone to a project

Instructions for the **agent** (Claude / Codex / Gemini) asked to attach or realign the
keystone layer in a project. Also carries **ready prompts for the user**.

Source of rules: [README.md](README.md) (the three axes, the layer decision tree, the
learn loop) and [ARCHETYPES.md](ARCHETYPES.md) (project types + the guardrail/profile
map). Note: keystone does **not** exist in the target project until step 1 — the shared
layer lives only in the repo `ai_keystone` and must be cloned in as a submodule **first**.
The agent reads `README.md` only after the submodule is attached.

---

## A. What the agent does on attach

When the user asks "attach keystone", the agent:

1. **Attach the shared layer as a submodule** (mount path `_forge/keystone`, repo
   `ai_keystone` — skip if the prompt already ran it):
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
6. **Generate or update `AGENTS.md`** (§C template), preserving existing content. The
   keystone block records the archetype + language, the SHARED/LOCAL/USAGE declaration,
   the USAGE placement, and the **resolved guardrail/profile links** from step 4 (written
   out, so they aren't recomputed each session). This block *is* the attach record.
7. **Update `.gitignore`** for secrets (see §D).
8. **Wire the commit guard** — add the PreToolUse hook
   [`hooks/git-commit-guard.py`](hooks/README.md) to the vendor config (for Claude Code,
   `.claude/settings.json` → PreToolUse/Bash, pointing at the keystone path). Enforces the
   commit guardrail ([`guardrails/_common.md`](guardrails/_common.md)).
9. **Run** `python3 _forge/keystone/bin/sync.py` (when present — see
   [ROADMAP O3](ROADMAP.md)); dry-run any tools where safe.
10. **Does NOT commit** — reports it is ready for review (the user commits `.gitmodules`,
    the submodule pin, and the generated files).

---

## B. Ready prompts for the user

### B1. New project

```
Attach keystone to this project.
First add the shared layer as a git submodule:
  git submodule add --name _forge/keystone https://github.com/akumidv/ai_keystone _forge/keystone
  git submodule update --init --recursive
Then read _forge/keystone/BOOTSTRAP.md and follow section A (it points to README.md for
the model and ARCHETYPES.md for the project type). Do not commit.
```

### B2. Existing project (already has AGENTS.md / CLAUDE.md)

```
Attach keystone without breaking the current docs.
First add the submodule:
  git submodule add --name _forge/keystone https://github.com/akumidv/ai_keystone _forge/keystone
  git submodule update --init --recursive
Then read _forge/keystone/BOOTSTRAP.md and follow section A. Keep all existing AGENTS.md
content — add/update ONLY the keystone block (§C). Show the diff, do not commit.
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
  [keystone/roles/](_forge/keystone/roles/).
- **Guardrails (applied — by language):** [_common](_forge/keystone/guardrails/_common.md)
  <!-- + the language guardrail(s) per the map, e.g. [python](_forge/keystone/guardrails/python.md) -->
- **Profiles (applied — opt-in by need):**
  <!-- only the profiles this project actually uses, e.g.
       - [quant](_forge/keystone/profiles/quant.md) — numerics -->
- **Pipelines:** [pre-commit](_forge/keystone/pipelines/pre-commit.md) (tests mandatory),
  [design-flow](_forge/keystone/pipelines/design-flow.md),
  [code-flow](_forge/keystone/pipelines/code-flow.md),
  [memory-distill](_forge/keystone/pipelines/memory-distill.md) +
  [learning](_forge/keystone/pipelines/learning.md) (the learn loop).
- **Backlog:** [_forge/TASKS.md](_forge/TASKS.md). **Secrets:** from `.env` (gitignored).
```

For **Codex/Gemini** this AGENTS.md block is enough (they read AGENTS.md). For **Claude**,
the `.claude/skills/` pointers also apply (written by `sync.py`).

---

## D. .gitignore (project root)

```
# secrets
*.env
!*.env.example
```

`_forge/memory/` is **committed** (shared project memory). `_forge/keystone/` is the
submodule. Generated agent pointers (`.claude/skills/`, …) — commit policy per
[ROADMAP O3](ROADMAP.md).

---

## E. Submodule lifecycle (repo: `ai_keystone`, mount `_forge/keystone`)

### Clone a project that already has it
```bash
git clone --recurse-submodules <project-url>
# or after a plain clone:
git submodule update --init --recursive
```

### Pull the latest shared layer into a project
```bash
git submodule update --remote _forge/keystone
python3 _forge/keystone/bin/sync.py          # refresh agent pointers (when present)
git add _forge/keystone && git commit -m "bump keystone"   # if the pin moved
```

### Edit the shared layer itself (changes go to ai_keystone)
Edits **inside** `_forge/keystone/` belong to the `ai_keystone` repo. Commit + push there,
then bump the pin in each consuming project. This is the **PROMOTE/PROPAGATE** end of the
learn loop ([learning](pipelines/learning.md)).

### Promote a local asset to shared
Move it from `_forge/{skills,tools}/` into `_forge/keystone/{skills,tools}/` (or a
role/guardrail/profile into the matching keystone dir), commit + push in `ai_keystone`,
then bump the pin in consuming projects. Apply the **promotion test** first: general *and*
proven (see [learning](pipelines/learning.md)).
