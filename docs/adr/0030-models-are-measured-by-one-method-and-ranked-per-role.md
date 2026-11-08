# 0030 — Models are measured by one method and ranked per role, apart from the harness that serves them

- **Status:** Accepted for **D01–D06**. The owner confirmed the carried method, the shape of the
  runner (Python and JavaScript, metadata in shared configuration files), where the local scores
  live, and the first shipped set (D-C197-METHOD, D-C197-TWIN, D-C197-STORE, D-C197-FIRSTSET), and
  limited this record to what is **implemented and measured now**: the method and the runner. The
  score row, the ladder function, availability and the provider fields are future tasks, so their
  shape in the [design](../design/model-measurement.md) stays a design until they land.
- **Owner:** akuminov@gmail.com
- **Extends:** [0004](0004-model-routing-capability-tiers.md) (tiers and the committed ladder — the
  measured ranking will feed that binding, it does not replace the tiers) ·
  [0024/D02](0024-second-opinion-by-model-priors.md) (one `providers` table — a harness stays a
  provider row).
- **References:** [design: model measurement](../design/model-measurement.md) ·
  [0020](0020-node-consumers-js-implementation.md) (the JavaScript twin) · the carried records
  [ranking method](../../meta/reviews/c197-ranking-method.md),
  [comparison practice](../../meta/reviews/c197-comparison-practice.md),
  [probe relevance](../../meta/reviews/c197-probe-relevance.md),
  [probe design audit](../../meta/reviews/c197-role-probe-design-audit.md),
  [stage-A pilot](../../meta/experiments/c197-stage-a-pilot.md) · [MEASUREMENTS.md](../../meta/MEASUREMENTS.md)
  M225–M236 · task [C197](../../meta/TASKS.md).

## Context

A project can run an athlos or a second opinion in more than one harness, and each harness serves
its own models, which change without notice. The routing binds a role to a tier through a hand-kept
ladder ([0004](0004-model-routing-capability-tiers.md)); nothing says which of the models a harness
serves is good enough for which role, and a measurement of that is expensive and easy to get wrong
(a noisy probe, a single attempt, an oracle a model wrote, a result tied to a request envelope that
was never recorded). The owner's earlier measurements settled the method and a runner for it; this
record brings both into akmon.

## Accepted decision blocks

### D01 — A model is ranked per role by a graded probe suite, in bands, against a hand-measured reference

`Decision-ID: ADR-0030/D01`

- **Graded, never judged.** Probes are bugs injected into small programs, with clean decoy files,
  graded by a hidden test and by line matching. A traceback-given / symptom-only pair on the same
  bug separates localization from repair. No model writes an oracle, and **every oracle passes the
  gold-sanity gate**: it fails on the buggy program and passes on the fixed one.
- **A score is keyed by** `(model id, case-set hash, envelope hash, scaffold)`. The scaffold is
  part of the key because one model under two harnesses is two measurements. A score keeps its
  failed gates beside the rate and carries an interval; repeated runs of one command must agree.
- **Banded, not ordered.** A paired comparison with a margin of **5 points** against a frozen
  reference places a model, per role, in one of three bands: below the worker bar, between the worker
  and the reasoner bar, at or above the reasoner bar. The bars are haiku (mechanical), sonnet
  (worker) and opus (reasoner); the auditor follows the reasoner. Rule behind the bars: a cheap tier
  is allowed where a wrong answer is caught (M236).
- **The ladder is a function of the whole score set** and is recomputed when a score is added; the
  scores are the artifact.
- **The reference run is manual.** A subscription login cannot be used in an automated job, so the
  owner runs the reference models by hand and the result ships. It is measured under a different
  envelope than the endpoint models, and the score set says so.
- **A null result is read as underpowered, not equal.**

### D02 — A harness is data, and a binding is in one of three classes

`Decision-ID: ADR-0030/D02`

`claude`, `codex`, `opencode`, `qwen`, `pi` and `mcode` are seed harnesses; the list is open, and a
new harness is a declaration (a provider row), not code. Any harness can run an athlos and any
model it serves can fill a role. akmon guarantees no harness × model pair works. It states, for each
binding, one of three classes: **evaluated** (scored by the suite akmon ships), **measured locally**
(scored on the user's machine by the same runner and the same method) and **declared** (named by a
harness or by the user, never scored). One mechanism produces the first two.

### D03 — The runner is a module in `tools/`, with a Python and a JavaScript implementation over shared configuration

`Decision-ID: ADR-0030/D03`

The module is `tools/model_profile/`, with its twin under `js/tools/model_profile/`
([0020](0020-node-consumers-js-implementation.md)); a project is developed in either ecosystem and
both run it. **Metadata is data:** the gates, the pass-rate band, the families, the endpoint paths,
the sandbox limits and the item set live in configuration files the two implementations both read;
code is separate per language, and a case-set hash computed by one equals the other's. The module is
built to be lifted out as a library: standard library only, nothing at import time, no import of
akmon internals beyond one adapter, the measurement channel (an OpenAI-compatible endpoint now; a
harness's own CLI later) a setting. **Model-written code runs in a container with no network and no
host mount, and a missing container runtime refuses the run** rather than falling back to the host.

### D04 — Generated measurement state lives in the project's local layer

`Decision-ID: ADR-0030/D04`

Output and local scores are written under `<dev root>/.local/`, beside the alias file of
[0024/D16](0024-second-opinion-by-model-priors.md): `meta/.local/` while developing akmon,
`_aitna/.local/` in a project that has akmon installed. The location is per checkout; a per-user
directory is not introduced.

### D05 — The first shipped set is the two market-leading harnesses; the rest are measured by akmon or by the user

`Decision-ID: ADR-0030/D05`

The default set is the `claude` and `codex` harnesses, whose models already have provider rows. Models
of other harnesses enter the shipped set when akmon measures them; whatever a user measures or
declares is the third group and stays local. Until a model has a score it is *declared*.

### D06 — What this record does not decide

`Decision-ID: ADR-0030/D06`

It does not decide the score row's file format and the merge of shipped and local scores, the banded
ladder function, availability discovery, the provider-row fields (`model_list`, `model_binding`,
`transcript_model_field`, `scaffold`), the non-Claude transcript reader, the once-a-day offer, the
suite's item generator, the reference run or a wide run over all models. Each is a task; its shape
is proposed in the design and becomes a block here or in a successor when it lands. Choosing a
harness and a model for an athlos and for the second opinion is a separate task.

## Consequences

- The method and its runner are in the tree and reproducible; the earlier results are carried as
  records and are not re-measured.
- The shipped score set is empty until a reference run and a generated suite exist; every model is
  *declared* or *measured locally* until then. The pilot is evidence of cost and plumbing only.
- The runner runs on a machine with a container runtime and an endpoint, so it is a developer's tool;
  the data it writes is read by both implementations of the routing.
