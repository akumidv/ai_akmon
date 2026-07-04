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

The reference table for the axis: what each archetype *is* and whether it exports USAGE. The
**shape** of an exported USAGE skill is one rule for all archetypes — see
[USAGE requirement](#usage-requirement-the-domain-concept--function-map-package-and-any-archetype-with-a-domain-api);
the per-archetype **must-document** list is the next section.

| ID | Kind | Examples | Exports USAGE? | USAGE `tools/`? |
|---|---|---|---|---|
| `package` | reusable library / package | alphavar, a pricer lib | yes — `skills/` for the public API | ❌ call the API directly |
| `service` | HTTP API service | an orchestration API | yes — the endpoint contract | only as a separate client package |
| `mcp` | MCP server | a knowledge/tool server | yes — the MCP tool contract | the server *is* the tool |
| `frontend` | UI application | a web app | no — it *is* the UI | — |
| `job` | scheduled / ETL job | a data-prep job | no — an orchestrator runs it | — |
| `platform` | agent host / platform | an agent runner | no — it *consumes* others' USAGE (mounts `skills/`) | — |
| `custom` | none of the above | — | declared per project | declared |

IDs are immutable contract values (tooling/templates depend on them).

## Required per archetype (beyond the universal set)

**Universal (every archetype):** the Layer/Role/Archetype declaration in `AGENTS.md`; the
secrets policy; the `_aitna/` layout + `bin/sync.py`; archetype ID + owner; the language
profile + matching [guardrails/](guardrails/); any opted-in [profiles/](profiles/).

The USAGE column above says *whether*; this says *what each must document on top of the
universal set*. Where an archetype exports a USAGE skill, its **shape** follows the one
[USAGE requirement](#usage-requirement-the-domain-concept--function-map-package-and-any-archetype-with-a-domain-api) — not restated per row.

| Archetype | Must also document |
|---|---|
| `package` | the USAGE skills + usage docs for the public API; an optional root **`knowledge/`** layer for rich concepts (see *Placement* below); versioning/compat policy; usage examples + failure modes |
| `service` | endpoint contract (routes / auth / error model); async / blocking-I/O rules; unit + service tests; USAGE external unless usage assets ship here |
| `mcp` | the MCP tool contract (names / IO / errors); how a consumer mounts it; unit + tool-contract tests |
| `frontend` | UI/state conventions; build/test/lint in pre-commit; client-side secrets boundary |
| `job` | the orchestration target; inputs/outputs, idempotency, retry/replay; data + secrets boundary |
| `platform` | the runtime agent layer kept **separate** from `_aitna/`; which consumed USAGE contracts it relies on; agent isolation/safety. *(A runtime platform that hosts OPERATE actors is out of akmon scope.)* |
| `custom` | scope, toolchain, runtime, risk profile, USAGE placement, mandatory checks |

## USAGE requirement: the domain-concept → function map (`package`, and any archetype with a domain API)

This is the **usage skill** end of the knowledge → implementation → usage chain
([MODEL.md](MODEL.md)). A USAGE skill is **not** "how to call the API" in the abstract —
it connects three things so an assistant can apply the project to a user's task:

1. **the domain concept** — what it is (placement of its description — `knowledge/` leaf vs
   skill + docstring — is covered under *Placement* below),
2. **the implementing function** — the *actual* public function/class that computes it
   (verified against code, not described in the abstract),
3. **how to apply it** — inputs, units/conventions, failure modes, a worked example.

So the unit of USAGE is a **mapping**: *concept → the function that realizes it → how to
use it* — not a bare API reference.

**Placement:**
- **knowledge is optional.** Add a `knowledge/` leaf only when the concept has substantial
  theory/sources/rationale or is an external resource; otherwise the concept's description
  lives in the SKILL.md (short) + the function docstring (shorter).
- A concept that is **implemented** gets a USAGE skill (and a `knowledge/` leaf if rich).
- A concept that is **planned but not yet coded** is documented (in `knowledge/` if rich,
  else just catalogued) with an impl task in `_aitna/TASKS.md`, but gets **no** skill until
  the code lands.
- A concept that is **neither implemented nor planned** is not stored at all.

**Why an akmon requirement, not a per-project choice.** It keeps domain knowledge
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

Each cell lists profiles *suggested* by the archetype; attach one only if the project has
that concern (the opt-in rule above). `crypto` is suggested wherever crypto/secrets are
plausible — auth, encryption, sealed data, decryption hosting — so it recurs by design.

| Archetype | Profiles to consider (opt-in) |
|---|---|
| `package` | [`quant`](profiles/quant.md) (numerics); `crypto` |
| `service` / `mcp` | `crypto` |
| `job` | `crypto` |
| `platform` | `crypto` |
| `frontend` | a design-tokens profile (when added) |
| `custom` | decide per project |

## Governance

- Archetype is decided at bootstrap and revisited when scope changes; changing it is a
  controlled change with a docs update.
- **Separate agents are not required by default** — prefer profile-based rules/skills, and
  introduce a dedicated agent only by the test in [MODEL.md](MODEL.md) §3 (materially
  different toolchain/runtime *and* safety envelope, where profile controls fall short).
