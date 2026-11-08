# Design: model measurement, harness availability and the ranked ladder

> **Status:** living design for task [C197](../../meta/TASKS.md). The method, the three classes, the
> module and its twin, the local state and the first shipped set are accepted in
> [ADR 0030](../adr/0030-models-are-measured-by-one-method-and-ranked-per-role.md); §§ 4–5 beyond the
> runner (the score row, the ladder, availability, the provider fields) are proposals for the tasks
> in § 6. Routing the chosen model into an athlos and the second opinion is
> [C198](../../meta/TASKS.md), outside this document.

## 1. Goal and boundary

Any harness can run an athlos, and any model a harness serves can fill a role. Models are ranked
per role **independently of the harness that serves them**, by one reproducible method; the method,
a runner and a score set live in `tools/model_profile/`. akmon guarantees no harness × model pair
works. It states, for every binding, which of three classes the model is in:

| Class | Meaning | Where the evidence is |
|---|---|---|
| **evaluated** | scored by the shipped suite; its rows ship with the standard | the shipped score set |
| **measured locally** | scored on this machine by the same runner | the local score set |
| **declared** | named by a harness or by the user, never scored | nothing; the binding is marked |

Out of scope here: re-measuring anything already recorded (the earlier survey, cost and pilot
results are carried as records, see § 8), choosing a model for an athlos (C198), and the suite's
item **generator**.

## 2. What already exists and is reused

| Fact | Owner today | Consequence |
|---|---|---|
| tiers, task kinds, the committed ladder | [ADR 0004](../adr/0004-model-routing-capability-tiers.md), [model-routing](model-routing.md) | the ladder this design computes **feeds** `registry.json`'s binding; it does not replace the tiers |
| providers (`claude`, `codex` list models; `qwen`, `opencode`, `pi` list none) | `tools/model_routing/registry.json` | a new harness is a new **provider row**, and a harness's model list stays on its row; no second harness file |
| the local, gitignored generated state | `<dev root>/.local/` (`model-aliases.json`, [ADR 0024/D16](../adr/0024-second-opinion-by-model-priors.md)) | the measured score set and the availability state sit beside it |
| the project overlay | `<aitna-root>/model-routing.json` | the project's rules over the ladder |
| one explicit, user-invoked read of a catalog | `tools/model_routing/models.py --refresh` | availability discovery is a second explicit read of the same kind, never a hook |

## 3. The method (carried, not re-derived)

The method was measured and decided earlier by the owner; its grounds are the survey records
[ranking method](../../meta/reviews/c197-ranking-method.md),
[comparison practice](../../meta/reviews/c197-comparison-practice.md) (§ 6.1 is the suite's rules)
and [probe relevance](../../meta/reviews/c197-probe-relevance.md). In one place, the commitments
this design depends on:

- **Graded, never judged.** Probes are bugs injected into small programs with clean decoy files,
  graded by a hidden test and by line matching; a traceback-given / symptom-only pair on the same
  bug separates localization from repair. No model authors an oracle, and every oracle passes the
  **gold-sanity gate** (fails on the buggy program, passes on the fixed one).
- **A score is keyed by** `(model id, case-set hash, envelope hash, scaffold)`; the scaffold is
  part of the key because one model under two harnesses is two measurements. A row keeps its
  **failed gates** beside the rate, carries an interval, and must be stable across repeats.
- **Banded, not ordered.** A paired comparison against a frozen **reference** (the Claude models,
  measured by hand) with a margin of **5 points** places a model per role in one of three bands:
  below the *worker* bar, between the worker and the *reasoner* bar, at or above the reasoner bar.
  The bars are haiku (mechanical), sonnet (worker) and opus (reasoner); the auditor follows the
  reasoner. The rule behind them: a cheap tier is allowed where a wrong answer is caught.
- **The ladder is a function of the whole score set** and is recomputed when a row is added; the
  scores are the artifact.
- **The reference run is manual** (a subscription login cannot be used in an automated job) and
  its result ships. It is measured under a different envelope than the endpoint models; the
  reference section of the score set says so.

These commitments are accepted as [ADR 0030/D01](../adr/0030-models-are-measured-by-one-method-and-ranked-per-role.md#d01--a-model-is-ranked-per-role-by-a-graded-probe-suite-in-bands-against-a-hand-measured-reference).

## 4. Data

### 4.1 The score row

One JSON object per (model, scaffold, role family), appended, never edited:

`model`, `scaffold`, `family` (`hunt` | `fix-traceback` | `fix-symptom`), `cases_sha`,
`envelope_sha`, `items`, `repeats`, `rate`, `interval`, `malformed`, `deferred`, `failed_gates[]`,
`wall_clock_s`, `tokens`, `run` (an ordinal). A shipped row carries **no timestamp**; the local file
may. A row without its two hashes is refused; a row whose hashes do not match the suite that ships
is flagged, not dropped.

### 4.2 The layers

| Layer | File | Owner | Wins over |
|---|---|---|---|
| shipped scores | `tools/model_profile/scores/` (in the wheel and the npm package) | the standard | — |
| local scores | `<dev root>/.local/model-scores.json` (`meta/.local/` in akmon, `_aitna/.local/` in a project) | the tool, per checkout | shipped, for the same key |
| availability | `<dev root>/.local/model-availability.json` | the tool | — (state, not scores) |
| project rules | the routing overlay | the project | ladder position, for a role it names |

The candidate set is the shipped and local scores merged; the ladder is computed over it; the
project overlay narrows or pins. A pin whose score set has changed since the pin was written is
reported once at session start (C198 carries the report).

### 4.3 Availability

Per harness, the models it serves **now**: `harness`, `served[]` (discovered ids), `source`
(`discovery` | `declared`), `checked`. A model named in a harness's configuration but absent from
the served set is reported as *missing*, with the command that would change the configuration; it is
never removed silently. Discovery is one explicit read per harness (a catalog request or the
harness's own list command), run by the owner or offered once a day; it writes only this file.

### 4.4 A harness is a provider row

The seeds are `claude`, `codex`, `opencode`, `qwen`, `pi` and `mcode`; the list is open. A row adds
fields to the existing provider schema, all optional: `model_list` (how the served set is read),
`model_binding` (where a model is named for a launch: a flag, an agent file key, a config key),
`transcript_model_field` (where a session transcript names the running model, so the orchestrator
is detected on every harness) and `scaffold` (the key part of § 4.1). A harness without them is
*declared*: usable, unmeasured, its availability unknown.

## 5. The module

`tools/model_profile/` is built to be lifted out as a library:

- its own README and schema; standard library only; nothing at import time; a Python and a
  JavaScript implementation (`js/tools/model_profile/`) over shared configuration files — gates, band,
  families, endpoint paths, sandbox limits and the item set are data both read — and equal case-set
  hashes;
- **no import of akmon internals** beyond one adapter module; today `cli.py` imports only
  `common.project_root` to place its output under `<dev root>/.local/`, and the provider rows are
  not read yet; both go through the adapter when it exists;
- the measurement channel is a setting: an OpenAI-compatible endpoint (built first) or a harness's
  own CLI (a later channel behind the same `Transport` protocol);
- the runner needs a container runtime for model-written code and **refuses** to run without one.

| Part | State |
|---|---|
| runner: cases, oracle gate, sandbox, scoring, ledger, `gate` / `plan` / `probe` | ported, Python and JavaScript |
| score row, merge, the banded ladder as a pure function | future task |
| availability discovery and its state file | future task |
| provider-row fields (§ 4.4) and the transcript reader for non-Claude harnesses | future task |
| the once-a-day offer | future task; a hook line, never a write |
| suite generator, the manual reference run, the wide run over all models | open, not blocking |

## 6. Staging

Trunk first (guardrail *Plan shape*). **C197 is the transferred part:** the method, the records and
the runner with its twin. The rest is future work, in priority order and none of it the main
priority: (a) the score row, the merge of shipped and local scores and the banded ladder as a pure
function; (b) availability discovery and its state file, the provider-row fields (§ 4.4), the
non-Claude transcript reader and the daily offer; (c) the suite generator, the manual reference run
and a wide run, which together make the first **evaluated** scores. The shipped set starts with the
`claude` and `codex` harnesses; until (c) exists no model has a shipped score and every one is
*declared* or *measured locally*. The earlier pilot is evidence of cost and plumbing, not of ranking:
its cells are single attempts and its seed set has two cases.

## 7. Risks

The probe's noise may exceed the gap between candidates; the interval must be reported even when it
is wide, and a null is read as *underpowered*, not *equal*. The reference is measured under a
different envelope. A shipped score set ages; what `verify` checks is its hashes, not its freshness.

## 8. Records carried

[Stage-A pilot](../../meta/experiments/c197-stage-a-pilot.md) (cost and plumbing, 21 calls),
the Qwen model-surface facts as `M<n>` rows in [MEASUREMENTS](../../meta/MEASUREMENTS.md), and the
audit of the probe design
[c197-role-probe-design-audit](../../meta/reviews/c197-role-probe-design-audit.md).

## 9. Decisions

All four requests of this stage are answered and recorded in
[ADR 0030](../adr/0030-models-are-measured-by-one-method-and-ranked-per-role.md): the twin
(**D-C197-TWIN**, both implementations over shared configuration, D03), the store
(**D-C197-STORE**, the project's local layer, D04), the method (**D-C197-METHOD**, D01) and the first
set (**D-C197-FIRSTSET**, `claude` and `codex` first, D05). What the ADR leaves out is D06.
