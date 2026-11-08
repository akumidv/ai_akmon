# C197 — Qwen Code model surface

A results document for the four Qwen-surface probes of task C197. The facts are recorded as rows M225–M230 of [MEASUREMENTS](../MEASUREMENTS.md); this note holds the detail behind them. Ranking is out of scope here ([c197-ranking-method](../reviews/c197-ranking-method.md)).

**Answers:** the four open probes of task C197 — (a) what `model:` accepts in a
Qwen subagent, (b) whether a Qwen transcript records the running model, (c) whether a rewritten
`.qwen/agents/*.md` takes effect mid-session, (d) whether the served model set is discoverable
through the endpoint.

**Harness:** Qwen Code **0.26.7** — the build this session runs (the VS Code extension bundle of that build, `dist/qwen-cli/`). A second build,
**0.26.2**, is installed system-wide; it was *not* used for the live probes, so
every live claim below is about 0.26.7.

**Settings:** the developer's `~/.qwen/settings.json` — `model.name = minimax-m3.1-flash`,
`model.baseUrl = <endpoint>/v1`, `security.auth.selectedType = openai`. The probe
scratch project is `<scratch>` (`.qwen/agents/probe_*.md`, one `.qwen/settings.json` with
`agents.modelGrades`), removed after the record was written. No credential value is reproduced here.

**Cost:** four headless sessions (two probe rounds, one grade round, one reload round) plus four
subagent launches — the owner's probe budget (the owner's probe budget).

---

## (a) What `model:` accepts in a Qwen subagent

**Source read** — the shipped `qc-helper` docs of the same build
(`bundled/qc-helper/docs/features/sub-agents.md` § Model Selection, and
`configuration/settings.md` § `agents.modelGrades`):

| Form | Meaning |
|---|---|
| omitted | same as `inherit` — the main conversation's model |
| `inherit` | same as `inherit` |
| `fast` | the configured `fastModel`; falls back to `inherit` when it does not resolve |
| a concrete id (`glm-5`) | that model id — resolved against the main conversation's auth type first, then against another configured provider |
| `authType:modelId` (`openai:gpt-4o`) | an explicit provider plus model id |
| a **user-defined grade** (`small`, `high`) | a key of `agents.modelGrades` in `settings.json`, restricted by `agents.allowedGrades` |

Grade rules, as documented and as found in the shipped bundle
(`chunks/chunk-BLIIEKZX.js`, `resolveModelGrade`): a grade resolves only when the agent has **no
explicit `model:`** of its own (an explicit model wins over a grade); unknown or disallowed grades
are rejected; grade selection is rejected for forks and named teammates; `agents.modelGrades`
**requires a restart** to take effect.

**Live confirmation.** Two named agents with concrete ids and one grade round, all in one scratch
project:

```
<scratch>/.qwen/agents/probe_a.md   → model: qwen3.8-27b
<scratch>/.qwen/agents/probe_b.md   → model: qwen3.8-flash-next
<scratch>/.qwen/agents/probe_c.md   → (no model: the caller picks the grade)
<scratch>/.qwen/settings.json        → agents.modelGrades = {small: qwen3.8-27b-nothink,
                                                        big: qwen3.8-flash-next-max}
                                               agents.allowedGrades = [small, big]
```

Command (each round a separate headless session, `-y` so no approval prompt can stall it):

```bash
cd <scratch> && node …/qwen-code/cli-entry.js -y -p "Use the agent tool with
subagent_type 'probe_a' … and 'probe_b' …"          # concrete ids
cd <scratch> && node …/qwen-code/cli-entry.js -y -p "… subagent_type 'probe_c' and
model 'small' … then subagent_type 'general-purpose' and model 'big' …"   # grades
```

Outcome — each launch's own metadata record (`~/.qwen/projects/-tmp-<scratch>/subagents/<session>/
agent-<agent>-*.meta.json`, field `model`):

| Launch | Requested | Recorded model |
|---|---|---|
| `probe_a` | frontmatter `qwen3.8-27b` | `qwen3.8-27b` |
| `probe_b` | frontmatter `qwen3.8-flash-next` | `qwen3.8-flash-next` |
| `probe_c` | caller grade `small` | `qwen3.8-27b-nothink` |
| `general-purpose` | caller grade `big` | `qwen3.8-flash-next-max` |

So the served ids are accepted verbatim as a subagent's `model:`, and a grade defined in
`agents.modelGrades` is honoured for a named agent that declares no model of its own.

**What this costs akmon.** Two ways to bind a delegate to a model, with different lifetimes:

- a concrete id **written into the generated agent file** — applies to the next launch, no restart
  (see (c));
- a **grade** resolved through `agents.modelGrades` in `settings.json` — the map is read at
  start-up, so a changed grade needs a restart, and the map lives in a settings file, not in the
  generated agent.

**Nested delegation.** `probe_a` (on `qwen3.8-27b`) spawned a child of its own; the child's record
carries no `model` of its own and `persistedCliFlags.model = qwen3.8-27b` — a nested delegate
inherits its parent's model when it declares none. akmon's depth limit (`maxSubagentDepth: 5`) is
the harness's, not ours.

## (b) What a Qwen transcript records about the model

A Qwen session writes a JSONL transcript per project
(`~/.qwen/projects/<slug>/chats/<session-id>.jsonl`) plus one metadata file per subagent launch
(`…/subagents/<session-id>/agent-<name>-*.meta.json`). Three fields carry the model:

| Where | Field | Example |
|---|---|---|
| chat transcript, first `system` event | `subtype: "session_model"`, `systemPayload.modelId` | `minimax-m3.1-flash` |
| chat transcript, per user/assistant record | `executionContext.modelId` | `minimax-m3.1-flash` |
| subagent metadata | `model`, and `persistedCliFlags.model` / `.authType` / `.baseUrl` | `qwen3.8-27b` |

Sanitized excerpt (own session, first two events):

```json
{"type":"system","subtype":"session_model","systemPayload":{"modelId":"minimax-m3.1-flash",
 "authType":"openai","baseUrl":"<endpoint>/v1"}}
{"type":"user","executionContext":{"modelId":"minimax-m3.1-flash","authType":"openai",
 "approvalMode":"auto"}}
```

**The finding that matters for akmon.** akmon's transcript reader
(the source project's `tools/model_routing/routing.py` → `_last_main_turn`, which is not in this tree, used by `detect_orchestrator` and by the
context-pressure notice) reads **Claude's** shape: `entry["message"]["model"]` and
`entry["message"]["usage"]`. A Qwen transcript has no `message.model` — the model lives in
`executionContext.modelId` (per turn) and in the `session_model` event (per session). The Qwen
adapter therefore resolves to `None` for every Qwen turn today, and the orchestrator detection and
the context-fill warning are **silent on this harness** — not wrong, but never triggered.

## (c) Does a rewritten agent definition take effect mid-session?

**Yes.** One headless session, three steps: launch `probe_d` (frontmatter `model: qwen3.8-27b`),
rewrite `<scratch>/.qwen/agents/probe_d.md` with `model: qwen3.8-flash-next`, launch
`probe_d` again.

Outcome — the two launches' own metadata records:

| Launch | Frontmatter at launch time | Recorded model |
|---|---|---|
| `probe_d` (1st) | `qwen3.8-27b` | `qwen3.8-27b` |
| `probe_d` (2nd) | `qwen3.8-flash-next` (rewritten mid-session) | `qwen3.8-flash-next` |

The agent definition is read **per launch**. A akmon rebind that rewrites the generated
`.qwen/agents/p_*.md` therefore reaches the *next* delegate launch of a running session — the
"delegates follow the live model" claim in
the model-routing decision (not carried here) holds on Qwen, and it needs no restart.
The one exception is the **grade map** (`agents.modelGrades`), which lives in `settings.json` and is
read at start-up.

## (d) Is the served model set discoverable?

**Yes**, through the endpoint's own list route, and it is cheap: one `GET /v1/models`. The
workspace tool of the source project (not carried here) already does this, with
`curl` and the token on curl's **stdin config** — python's `urllib` is answered by Cloudflare
error 1010, and a token on the command line would land in the process list.

Measured once (ids and ceilings, from `GET <endpoint>/v1/models`):

| model id | max_input_tokens | max_output_tokens |
|---|---|---|
| `minimax-m3.1-flash` | 194560 | 65536 |
| `ornith-1.5-9b` | (none reported) | (none reported) |
| `qwen3.8-27b` | 768000 | 16384 |
| `qwen3.8-27b-max` | 718848 | 65536 |
| `qwen3.8-27b-nothink` | 776192 | 8192 |
| `qwen3.8-flash-next` | 718848 | 65536 |
| `qwen3.8-flash-next-max` | 718848 | 65536 |

Two observations that shape the profile:

1. The served set is **7 ids, and one of them is not a Qwen** — `minimax-m3.1-flash` sits in the
   same namespace. akmon's registry treats `qwen` as a *vendor* whose rungs are *this machine's*
   model ids (the model-routing decision, not carried here); the endpoint serves several families under one vendor key, so a profile
   that ranks "qwen models" must rank **served ids**, not a family's name.
2. `-max` and `-nothink` are **separate served ids with different ceilings** (718848/65536 versus
   776192/8192) — a mode suffix is a different model to the endpoint, so it is a different candidate
   in the ranking, not a flag of one.

## What this record does not claim

- Nothing about **opencode** or **pi** — their surfaces are separate probes, not carried here.
- Nothing about the **quality** of the seven models: this record measures the *surface* (what can
  be selected, what is recorded, what is discovered), not the ranking. The method for that is
  .
- No claim about **Claude Code** or **Codex** transcripts: the reader in (b) is Qwen's shape, and
  akmon's existing reader stays Claude's.
- The `session_model` event and `executionContext.modelId` were read from **one** session of this
  build; a `/model` switch mid-session is not probed here (the rebind path depends on it).
