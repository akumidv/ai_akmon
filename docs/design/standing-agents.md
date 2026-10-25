# Design — standing agents: how a project develops and delivers them

> **Status: proposed — a scoping note for task A69, not a decision.** It exists to fix the
> questions before the architect session answers them. Nothing here is accepted; the answers
> become decision requests (D-AGENT-*) and, once the owner accepts one, an addressable block in a
> thematic ADR. Drafts stay proposed until two or three standing agents exist; today there is one
> case, and anything that rests on it alone is marked **needs a second case**.

## Why this is open

akmon gives a project a model for **skills** and their delivery. Projects now also need
**standing agents**: an agent that lives in a long-open session, owns state of its own (a folder,
an index, a retention rule), uses a set of skills, and is switched on per installation. akmon's
word *agent* today means only the **development charter of a role** (`<DEV>/agents/<name>/README.md`).
The OPERATE side exists as a roster line and nothing more. The question is a contract for the
OPERATE side that does not clash with the charter checks.

## What exists, verified in the tree

| Fact | Where |
|---|---|
| The session-start roster scans two lists: `<DEV>/agents/` (development charters) and the project root `agents/` (the OPERATE side); a charter is a subdirectory holding a `README.md` | `agent_names`, `session_start` in `hooks/hook_core.py` and its twin `js/hooks/hook_core.mjs` |
| The roster prints `OPERATE (run/use from outside): …` from the data key `operate_line` | `hooks/hook_core.json` |
| `verify` checks `<DEV>/agents/` only: `charters.present`, `charters.readme`, `charters.role-link`; root `agents/` is not validated | `checkAgentCharters` in `js/bin/verify.mjs`, the same ids in `bin/verify.py` |
| The `platform` archetype excludes a runtime that hosts OPERATE actors | `ARCHETYPES.md` |
| OPERATE is an undesigned third branch whose hard runtime part is propose ≠ execute | `meta/ROADMAP.md` § O1 |
| A role is the definition, a project's charter its incarnation; `k_*` delegates are workers by task kind | `roles/README.md`, `MODEL.md` § Capability tiers |

## The first case: general or specific

Recorded in the A69 session after reading the first case, in three columns — **general** (holds for
any standing agent), **specific** (belongs to that case alone), **needs a second case**. Until the
column is written, no clause below may be drafted as a rule. The case's own charter format is
interim; akmon is to be the source of the standard.

## Decision requests to answer

Each is a bounded choice; options, pros and cons, and a recommendation come with the A69 draft.
Items 2 and 3 presuppose neither a shared skill nor a rename of the folder.

- **D-AGENT-CONCEPTS** — the relation of role, development charter, standing agent, skill and
  worker (`k_*`); names that collide neither with each other nor with a host's own "agent" (a host
  subagent); which of them akmon owns.
- **D-AGENT-AUTHORING** — when something is an agent and not a skill; the charter's shape
  (frontmatter, mission, skills used, owned state, never-list, session start and close, workers);
  retention of owned state; how a charter points at skills instead of copying their rules; the
  guardrails an agent cannot widen; its tests and checks; its review through review-flow. A shared
  authoring skill is one possible form, not a premise.
- **D-AGENT-DELIVERY** — across Claude Code, Qwen Code and Codex: reuse the skill pointers or
  not; what the roster line validates; a `verify` check for OPERATE-side charters that does not
  clash with `charters.*`; how a project declares which agents are on.
- **D-AGENT-ARCHETYPE** — a standing agent is a charter with no runtime, the thin case of what
  `platform` excludes; whether that needs its own archetype statement.
- **D-AGENT-LEARN** — whether a procedure repeated in a long session is promoted to an agent by the
  skill route; what `memory-distill` must say about retiring and compacting old notes (it is silent
  on both).
- **D-AGENT-OPERATE-NAME** — the internal name of the OPERATE side, below.

Propose is not execute: ROADMAP draws that line for OPERATE, and a standing agent meets it through
confirmation gates, not a runtime. The draft changes no accepted ADR, makes no commit and moves no
pin.

## D-AGENT-OPERATE-NAME — rename the internal term

The owner decided to rename the internal term and confirmed the name **`operate_agents`**; a
consumer's own agent keeps its own name. The alternatives below stay as the record of what was weighed.

**Impact, measured.** The word is internal in code and absent from every delivered file:

| Surface | Occurrences |
|---|---|
| Local variable in the roster | 4 lines in `hooks/hook_core.py`, 4 in `js/hooks/hook_core.mjs` |
| Prose | 1 line in `hooks/README.md` (`root agents/ desk`) |
| History note | 1 line in `meta/ROADMAP.md` § O1 ("as the old `desk/` did") — a past fact, left as written |
| Data key, tests, conformance units, ADRs, generated files | none — the key is already `operate_line`, the printed line already says OPERATE, and the roster is computed at session start rather than materialized |

So the rename touches the two hook twins and one README line and **needs no consumer migration**:
no attached project holds the term in a generated file. The root folder is `agents/`, not `desk/`;
renaming the folder is a different, breaking change and is **not** part of this decision.

**Name.** `operate` — the owner's first thought — matches the data key and the mode word, but as a
bare local it reads as a verb. Alternatives: `operate_agents` (names the thing, not the mode),
`standing` (ties to the concept in D-AGENT-CONCEPTS; wait for it), `runtime_agents` (collides with
the "runtime" that `platform` excludes). **Chosen: `operate_agents`**, which keeps the
mode word and says what the list holds.

**Order.** The rename lands before D-AGENT-CONCEPTS names the concept; if that decision picks another name,
the change is the same few lines. Task C168 carries it.
