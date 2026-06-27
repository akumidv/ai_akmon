# Project archetypes

The **Archetype** axis (see [MODEL.md](MODEL.md) §4): it decides **whether the USAGE
layer exists and what shape it takes**. Chosen by the **contract a project exposes**, not
by its language.

> Language is a *separate* dimension (it selects [guardrails/](guardrails/)). One
> archetype = one runtime/contract. A language change that keeps the contract (a Python vs
> JS *package* — both expose a public API) is the **same** archetype, different language.
> A language change that produces a *different* contract (a JS HTTP API vs a Python
> service) is a **different** archetype — record the decision in the project.

## Taxonomy (canonical IDs)

| ID | Kind | Examples | USAGE it exports | USAGE `tools/`? |
|---|---|---|---|---|
| `package` | reusable library / package | alphavar, a pricer lib | `skills/` + docs for the public API | ❌ call the API directly |
| `service` | HTTP API service | an orchestration API | endpoint contract (auth, error model) | only as a separate client package |
| `mcp` | MCP server | a knowledge/tool server | the MCP tool contract | the server *is* the tool |
| `frontend` | UI application | a web app | usually none (it *is* the UI) | — |
| `job` | scheduled / ETL job | a data-prep job | usually none (an orchestrator runs it) | — |
| `platform` | agent host / platform | an agent runner | *consumes* others' USAGE (mounts `skills/`) | — |
| `custom` | none of the above | — | declared per project | declared |

IDs are immutable contract values (tooling/templates depend on them).

## Required per archetype (beyond the universal set)

**Universal (every archetype):** the Layer/Role/Archetype declaration in `AGENTS.md`; the
secrets policy; the `_forge/` layout + `bin/sync.py`; archetype ID + owner; the language
profile + matching [guardrails/](guardrails/); any opted-in [profiles/](profiles/).

| Archetype | Must also document |
|---|---|
| `package` | a **USAGE `skills/`** (the domain-concept → implementing-function map, see below) + usage docs for the public API; a root **`knowledge/`** layer **only for concepts rich enough to warrant it** (optional — else skill + docstring, see below); versioning/compat policy; usage examples + failure modes; **no USAGE `tools/`** |
| `service` | endpoint contract (routes / auth / error model); async / blocking-I/O rules; unit + service tests; USAGE external unless usage assets ship here |
| `mcp` | the MCP tool contract (names / IO / errors); how a consumer mounts it; unit + tool-contract tests |
| `frontend` | UI/state conventions; build/test/lint in pre-commit; client-side secrets boundary; "no exported USAGE" unless deliberately added |
| `job` | the orchestration target; inputs/outputs, idempotency, retry/replay; data + secrets boundary; "no exported USAGE" |
| `platform` | the runtime agent layer kept **separate** from `_forge/`; which consumed USAGE contracts it relies on; agent isolation/safety. *(A runtime platform that hosts OPERATE actors is out of keystone scope.)* |
| `custom` | scope, toolchain, runtime, risk profile, USAGE placement, mandatory checks |

## USAGE requirement: the domain-concept → function map (`package`, and any archetype with a domain API)

This is the **usage skill** end of the knowledge → implementation → usage chain
([MODEL.md](MODEL.md)). A USAGE skill is **not** "how to call the API" in the abstract —
it connects three things so an assistant can apply the project to a user's task:

1. **the domain concept** — what it is (owned by its `knowledge/` leaf if one exists, else
   stated briefly in the skill + the function docstring),
2. **the implementing function** — the *actual* public function/class that computes it
   (verified against code, not described in the abstract),
3. **how to apply it** — inputs, units/conventions, failure modes, a worked example.

So the unit of USAGE is a **mapping**: *concept → the function that realizes it → how to
use it* — not a bare API reference.

**Placement (per §3b rules):**
- **knowledge is optional.** Add a `knowledge/` leaf only when the concept has substantial
  theory/sources/rationale or is an external resource; otherwise the concept's description
  lives in the SKILL.md (short) + the function docstring (shorter).
- A concept that is **implemented** gets a USAGE skill (and a `knowledge/` leaf if rich).
- A concept that is **planned but not yet coded** is documented (in `knowledge/` if rich,
  else just catalogued) with an impl task in `_forge/TASKS.md`, but gets **no** skill until
  the code lands.
- A concept that is **neither implemented nor planned** is not stored at all.

**Why a keystone requirement, not a per-project choice.** It keeps domain knowledge
*honest* (every usage skill points at real, verified code), makes USAGE travel into a
consumer without re-deriving the domain, and is the natural seam to an MCP knowledge server
later. It is **mandatory for `package`** and for any archetype that exposes a domain API
(`service`/`mcp` where the contract is domain-shaped); `custom` declares its stance.

## Applied guardrails & profiles (the map)

The source of truth for **which shared rules apply to a project**. Bootstrap reads it once
and writes the resulting links into the project's `AGENTS.md` (so agents don't recompute
it each session). When this map changes, re-run bootstrap (or, later, `sync.py`) to
refresh the project's list.

Two kinds of attachment:
- **Guardrails — automatic by language.** Always applied; derived from the language, not
  chosen.
- **Profiles — opt-in by need.** *Suggested* by archetype, attached only if the project
  actually has that concern (don't attach `quant` to an API that does no numerics).

| Language | Guardrails (automatic) |
|---|---|
| Python | [`_common`](guardrails/_common.md) + [`python`](guardrails/python.md) |
| JavaScript/TS | `_common` + `js` *(when added)* |
| Mixed | `_common` + each present language's guardrail |
| Other | `_common` + document the language's rules locally |

| Archetype | Profiles to consider (opt-in) |
|---|---|
| `package` | [`quant`](profiles/quant.md) (numerics packages); `crypto` (if it ships crypto) |
| `service` / `mcp` | `crypto` (if it does auth/encryption) |
| `job` | `crypto` (if it handles secrets/sealed data) |
| `platform` | `crypto` (often — hosts decryption) |
| `frontend` | a design-tokens profile (when added) |
| `custom` | decide per project |

## Governance

- Archetype is decided at bootstrap and revisited when scope changes; changing it is a
  controlled change with a docs update.
- **Separate agents are not required by default** — prefer profile-based rules/skills;
  introduce a dedicated agent only when the toolchain/runtime *and* safety envelope differ
  materially **and** profile controls prove insufficient (this is the same test the Role
  axis uses in [MODEL.md](MODEL.md) §3).
