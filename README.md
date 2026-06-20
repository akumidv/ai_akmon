# keystone — the AI-assistant governance baseline

> The **keystone** of a project group: the first stone you place, the one that holds
> the arch and sets the geometry of everything built after it. This repository is the
> cross-project standard for **how an AI assistant helps develop, and helps use,**
> each project. New projects are bootstrapped from it; existing ones are realigned to
> it.

Mounted into every project as a git submodule at **`_forge/keystone/`** (the repo is
`ai_keystone`; the mount path is `keystone` — see [BOOTSTRAP.md](BOOTSTRAP.md)). It is
**LLM-agnostic**: plain Markdown/JSON any assistant (Claude, Codex, Gemini, …) or human
can read. No vendor's tooling is privileged; the single entry point in a consuming
project is its root `AGENTS.md`.

---

## 1. Three orthogonal axes (do not conflate)

The model stands on **three independent axes**. Conflating them is the usual source of
confusion ("is a layer an agent?" — no).

| Axis | Answers | Values (types) |
|---|---|---|
| **Layer** | *where* an artifact lives + *whom it serves* (its consumer) | SHARED / LOCAL / USAGE |
| **Role** | *who performs* the work + by which pipeline | architect / engineer / … |
| **Project type** | *what* the project exposes outward | package / service / mcp / frontend / job / platform / custom |

Each axis is a **type dimension** — its values are kinds, not concrete things. SHARED is
a kind of layer; `package` is a kind of project; `engineer` is a kind of **role**.

The Layer and Role axes both mention people but ask different questions: **Layer** is
about *whom an artifact serves* (its consumer); **Role** is about *who produces* it (the
actor).

An **agent is not an axis value** — it is a concrete point where the axes meet: a role,
applied in a project, on a layer. So `engineer` (role) × LOCAL (layer) × `package`
(project type) = *alphavar's engineer agent*. A role is the reusable **definition** (in
keystone); an agent is its **incarnation** in a project (in `_forge/agents/`), inheriting
the role and adding specifics. One role can have several agents (e.g. two `engineer`
agents for two subsystems).

---

## 2. Axis "Layer" — a decision tree, not a grid

A layer is defined by *where* an artifact lives and *whom it serves* — not by who writes
it (that is the Role axis). Ask one question; ask the second **only** on the development
branch. This removes the false "shared usage" cell — there is no shared usage layer,
because *using from outside* is inherently local to whoever consumes it.

```
Does this artifact help DEVELOP this project — or USE it from outside?
│
├─ DEVELOP ─────────► is the approach common to all my projects, or specific to this one?
│                     │
│                     ├─ common        → SHARED  → _forge/keystone/   (this submodule)
│                     └─ this project  → LOCAL   → _forge/{skills,tools,memory,agents}/
│
└─ USE from outside ► USAGE → root skills/ (+ tools/ where applicable)
                      (built to travel into the consuming project)
```

| Layer | Job | Consumer | Lives in |
|---|---|---|---|
| **SHARED** | assist development in general | any of my projects | `_forge/keystone/` (submodule) |
| **LOCAL** | assist development of *this* project | this repo's developer | `_forge/{skills,tools,memory,agents}/` |
| **USAGE** | assist *using* what the project exposes | a downstream project | root `skills/` (+ `tools/`) |

SHARED+LOCAL point **inward** (building this repo); USAGE points **outward** (this repo
used elsewhere). `shared` vs `local` is a **development-only** distinction.

**Naming rule in one line:** `_forge/**` = developing this project · `_forge/keystone/**`
= the shared (SHARED) subset of that · everything else (`docs/`, root `skills/`) = the
product and its use (USAGE).

**Scope boundary — what this tree does NOT cover (yet).** The tree spans DEVELOP and USE.
It does **not** cover a third mode, **OPERATE** — an agent that *acts in the world at
runtime* (e.g. a trading agent that places orders; an agent that moves data or money).
OPERATE differs in kind: its risk is not a broken build or a wrong answer but **real
consequences** (lost money, irreversible action), so it needs its own hard runtime
guardrails, not D#/USAGE rules. OPERATE is **deliberately out of scope for keystone for
now** and tracked as an open question in [ROADMAP.md](ROADMAP.md) — do not fold a runtime
actor into USAGE (using a library ≠ operating in a market). When formulated, it becomes a
third branch of this tree, not a layer under DEVELOP.

---

## 3. Axis "Role" — role (here) vs agent (in the project)

A **role** is a *definition*: **role = pipeline + requirements + guardrails**. The Role
axis is what we classify by; its values (`architect`, `engineer`) are roles. An **agent**
is a role *applied in a project* — its incarnation, not an axis value. One role may have
several agents in a project (e.g. under `engineer`: a backend agent and a data-pipeline
agent). So we split definition from incarnation:

- **Role** — the *definition* (pipeline, requirements, guardrails). Cross-project →
  lives here in [`roles/`](roles/). This is "the approaches and requirements for roles".
- **Agent** — the *incarnation in a project*: inherits a role from keystone and adds
  project specifics. Lives in the project at `_forge/agents/`.

Two roles at the start:

| Role | Focus | Output | Pipeline |
|---|---|---|---|
| [**architect**](roles/architect.md) | design, documentation, architecture, requirements, ADRs | design docs, specs, ADRs, requirement updates | [design-flow](pipelines/design-flow.md) |
| [**engineer**](roles/engineer.md) | code, tests, refactoring | commits / PRs | [code-flow](pipelines/code-flow.md) |

Why separate agents and not just profiles: design vs code are **materially different
pipelines** (documentation/architecture vs code/tests), not different settings. That is
when a dedicated agent is justified — otherwise prefer profile-based rules/skills.

Both agents live on the **DEVELOP** branch and both draw shared requirements from
**SHARED** (keystone). architect works mostly in `docs/` (and, for a package, USAGE
`skills/`); engineer works in `src/`/`tests/`.

---

## 3a. The learn loop — how the keystone evolves through use

keystone is a **tuning fork that retunes itself**: knowledge gained while working a
project flows back, is generalized, and — if it proves cross-project — is promoted into
keystone so every project inherits it. Without this loop the standard ossifies; the loop
*is* the mechanism by which the model improves.

The cycle (knowledge climbs from local insight toward the shared standard):

```
1. CAPTURE   an agent hits an insight / friction / repeated manual step
                 → writes one fact to _forge/memory/  (LOCAL, in git, team-visible)
2. DISTILL   recurring facts are turned into something reusable:
                 a LOCAL skill / tool / agent specific   → _forge/{skills,tools,agents}/
                 or a refined requirement / ADR           → docs/ (via the architect role)
3. PROMOTE   if it is general across projects, lift it into keystone (PR):
                 a cross-project skill/tool   → keystone/{skills,tools}/
                 a role requirement/pipeline  → keystone/{roles,pipelines}/
                 a language/domain rule        → keystone/{guardrails,profiles}/
4. PROPAGATE every other project gets it on `git submodule update` (pin bump)
```

Direction of flow is one-way **up** the abstraction ladder: *private provider memory →
shared project memory (`_forge/memory/`) → local reusable asset → keystone*. Each step is
a deliberate, reviewed promotion, never an automatic copy.

**Two kinds of memory, kept distinct:**
- **Shared project memory** — `_forge/memory/` (in git, all developers and agents see it,
  reviewed). This is the raw material of step 1–2.
- **Provider-private memory** — each assistant's own store (e.g. Claude's per-project
  memory). Stays with the individual; the loop *distills* from it into shared memory, it
  is never the shared source of truth.

**Promotion test (when does something move up?)** Promote LOCAL → keystone only when it
is (a) general — not tied to this project's domain/runtime, and (b) proven — used more
than once, or clearly applicable to another project. Otherwise it stays LOCAL. The
mechanics live in the pipelines [`memory-distill`](pipelines/memory-distill.md) (steps
1–2) and [`learning`](pipelines/learning.md) (periodic step 3 review).

---

## 4. Axis "Project type" (archetype) — what is exposed outward

A profile dimension that decides **whether USAGE exists and what shape it takes**.
Chosen by the **contract** the project exposes, not by language. Full taxonomy and
per-type checklists: [ARCHETYPES.md](ARCHETYPES.md).

| Type | Contract | USAGE | USAGE `tools/`? |
|---|---|---|---|
| `package` | library / package | `skills/` for the public API + usage docs | ❌ call the API directly |
| `service` | HTTP API | endpoint contract (auth, error model) | only as a separate client package |
| `mcp` | MCP server | the MCP tool contract | the server *is* the tool |
| `frontend` | UI | usually none (it *is* the UI) | — |
| `job` | ETL / scheduled | usually none (an orchestrator runs it) | — |
| `platform` | agent host | *consumes* others' USAGE | — |
| `custom` | none of the above | declared per project | declared |

---

## 5. Profiles & guardrails (the project-independent baseline)

- **[`guardrails/`](guardrails/)** — per language/environment, **applied automatically**
  by the project's language: `_common.md` + `python.md` (+ `js.md`, `rust.md` as needed).
- **[`profiles/`](profiles/)** — per domain, **opt-in by need**, *suggested* by the
  project type: `quant.md` (numerics), `crypto.md`, …

---

## 6. Layout of `_forge/` in a consuming project

```
_forge/
├── keystone/                   # ← THIS submodule (repo ai_keystone)
│   ├── README.md               #   this file — the model's constitution
│   ├── BOOTSTRAP.md            #   attach/realign a project (+ ready prompts)
│   ├── ARCHETYPES.md           #   project types + per-type USAGE/requirement checklists
│   ├── ROADMAP.md              #   forward plan (skill contract, evals, MCP move)
│   ├── roles/                  #   ROLE BASELINE (cross-project): requirements + pipeline
│   │   ├── README.md  architect.md  engineer.md
│   ├── guardrails/             #   per-language rules (for any agent/role)
│   ├── profiles/               #   opt-in domain profiles
│   ├── pipelines/              #   dev cycles: pre-commit, design-flow, code-flow, …
│   ├── skills/  tools/         #   cross-project skills (SKILL.md) + executable tools
│   └── bin/sync.py             #   writes thin pointers into .claude/.codex/GEMINI
│
├── agents/                     # CONCRETE AGENTS of this project (inherit roles)
│   ├── architect/  engineer/   #   each: README.md (charter) + pipeline.md
├── skills/  tools/  memory/    # LOCAL skills/tools + SHARED project memory (in git)
└── TASKS.md                    # single backlog / TODO cycle / learn-loop sink
```

The project root also holds `AGENTS.md` (single source for agents; `CLAUDE.md` is a thin
pointer) and, for a package/service, the USAGE layer (`skills/`, `docs/`).

**Inheritance contract** (agent → role): the agent charter at
`_forge/agents/<role>/README.md` links `keystone/roles/<role>.md` as its source of
requirements and pipeline, and adds only project specifics. The role changes in keystone
(for all projects); the agent changes locally.

---

## 7. Cross-agent: source of truth + generated pointers

The source of truth is the **markdown instruction and the executable code**; each
vendor's entry point is a thin **generated** pointer (no duplicated content).

- **skill** = `SKILL.md` (frontmatter + instruction). Native for Claude; a linked
  document for Codex/Gemini.
- **tool** = code under `tools/<name>/`; secrets from `.env`. A skill *calls* a tool.
- **`bin/sync.py`** writes `.claude/skills/<name>/SKILL.md` stubs and the AGENTS.md skill
  list. Not symlinks (break on Windows / in submodules); not a Claude plugin (Claude-only
  — we feed Claude + Codex + Gemini from one source).

---

## 8. Secrets

From the project `.env` only (`*.env` gitignored; `*.env.example` carries empty
placeholders). Never in code, markdown, or commits.

---

## 9. Distribution — submodule → MCP → product

keystone is designed to survive a change of carrier:

- **Now:** git submodule (deterministic pinning, PR governance).
- **Next:** hybrid — governance/docs stay in the submodule; executable `tools/` and
  validators move behind an MCP server the agent mounts (same contract, new carrier).
- **Later:** a standalone product — the name `keystone` stands on its own.

Forward plan: [ROADMAP.md](ROADMAP.md).

---

## 10. Evolving keystone

- **Add a shared skill/tool/role** → PR into this repo; it reaches all projects after
  `git submodule update`.
- **Add a local skill/tool/agent** → directly in the project's `_forge/`. If broadly
  useful, *promote* it into keystone via PR.
- **Change guardrails/profiles/pipelines** → here only (shared for every project).
- **Attach to / realign a project** → [BOOTSTRAP.md](BOOTSTRAP.md).
