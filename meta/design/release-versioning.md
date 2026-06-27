# Design: keystone release and versioning standard

> **Locked.** The decisions in this concept are folded into
> [ADR 0001](../decisions/0001-release-and-roles-model.md) (resolves ROADMAP O2). This document
> stays as the options/rationale source and the **§Open Points** register; the ADR is the
> authoritative record of *what was decided*. Implementation is phased via backlog T10–T15.

## Frame

keystone is now consumed by multiple projects, and bumping the `_forge/keystone` submodule
pin is a recurring operation. The release/versioning model must therefore be a shared
keystone standard, not a one-off `CHANGELOG.md` in one repository.

Good outcome:

- a project maintainer can decide whether to bump a keystone pin without reading raw task
  archives or every commit;
- keystone maintainers can cut a release using one repeatable pipeline;
- a release agent can guide the owner through the release, ask for decisions at the right
  gates, and stop before owner-owned actions such as commits, tags, pushes, and pin bumps;
- the same release model works for keystone releases and for ordinary project releases that
  adopt keystone;
- `TASKS.md`, `TASKS_ARCHIVE.md`, release notes, version tags, and consuming-project bump
  records each have one job and do not duplicate each other;
- periodic hygiene is part of the cycle: backlog cleanup, memory review, learning/promotion,
  skill/tool review, architecture/requirements drift checks, guardrail compliance, and CI
  verification.

## Current State

- `TASKS.md` is the active backlog index.
- `TASKS_ARCHIVE.md` is the internal done-task ledger.
- `ROADMAP.md` tracks not-yet-formulated model gaps, including O2 versioning.
- Consuming projects pin keystone as a git submodule.
- `sync.py`, `verify.py`, `self_ci.py`, and pytest now provide a runnable validation spine.
- D5 still applies: the owner owns commits, tags, pushes, and release landing actions.

## Working Distinctions

`TASKS.md`:
live work queue. It should never become a release plan or release notes.

`TASKS_ARCHIVE.md`:
maintainer execution ledger. It records closed task IDs and terse goals. It is useful
traceability, but it is not written for consumers.

Release notes / changelog:
consumer-facing impact log. It says what changed, what may break, what to run, and what a
downstream project must review before accepting a new pin.

Version / tag:
published identity of a keystone state. A submodule pin can point anywhere, but a release tag
is the reviewed state projects should normally consume.

Downstream bump record:
the consuming project's record that it accepted a keystone version/pin and refreshed generated
files. This belongs in the consuming project, not in keystone's own release notes.

## Role / Agent Shape

This is a materially distinct role, not just an architect or engineer profile. It is a
**DEVELOP** role: cutting and publishing a release is still developing the project (making a
reviewed state available). **OPERATE** is the *other* side — consuming the published release
(e.g. alphavar running against a live market). Publishing is therefore not an OPERATE action;
the D5 boundary applies because commits/tags/publish are owner-owned, not because release sits
near runtime.

Two new roles fall out of this work, not one:

- `release` — coordinate the release cycle (below).
- `learn` — own the learn loop (`pipelines/learning.md` + `pipelines/memory-distill.md`),
  today referenced as a "learning role" with no role file. Extracting it is what keeps
  `release` from absorbing learning work: at the learning gate `release` **hands off** to
  `learn` rather than promoting memory itself. See [Role-axis placement](#role-axis-placement).

Candidate role: `release`.

Mission:
coordinate a repeatable release cycle from readiness audit through release notes, verification,
owner decisions, tag/publish handoff, downstream propagation, and post-release learning.

Problem it solves:
a project has accumulated completed work, local learning, possible drift, and downstream
consumers; the owner needs to decide whether a version can be released, what kind of version it
is, what changed for consumers, what must be cleaned up or deferred, and how to propagate the
release without violating D5 or bypassing architecture/guardrail checks.

The role definition must state this task explicitly so the release agent is not mistaken for:

- an architect replacement — it audits architecture and files/coordinates architect work, but
  does not make load-bearing architecture decisions;
- an engineer replacement — it runs and coordinates verification, but implementation gaps go to
  engineer tasks;
- a commit bot — it prepares exact handoff commands, but owner-owned commit/tag/push/publish
  actions stay with the owner.

Why a new role is justified:

- the pipeline is neither design-flow nor code-flow;
- the output is an operational release decision and release package, not a design or code diff;
- it crosses artifacts owned by architect, engineer, learning, and project operations;
- it has explicit question gates for the owner: scope, version class, breaking changes,
  migration steps, projects to propagate to, and whether to tag/publish.

Role boundaries:

- `release` may read and audit all dev-layer artifacts: `TASKS.md`, `TASKS_ARCHIVE.md`,
  memory, skills/tools, ADRs, requirements, CI, generated pointers, and project docs.
- `release` may update release-process artifacts once the owner has asked to perform a release
  or record release design.
- `release` does not invent architecture. Architecture drift or requirement mismatch becomes an
  architect task.
- `release` does not implement code/tooling changes. Mechanical or executable gaps become
  engineer tasks.
- `release` does not commit, tag, push, publish, or bump downstream pins. It prepares exact
  commands and asks the owner to execute or explicitly authorize them under D5.
- Release tooling produced by this role must default to **propose/prepare**, not **execute**:
  scripts may print commands, build checklists, validate state, or create draft files, but
  owner-owned landing actions are run by the owner.

Anti-super-role invariant (routing, not doing):

`release` is a coordinator, not a catch-all. The boundaries above are not just intentions —
they are a **routing rule**: every sweep finding becomes a task owned by the role that owns
that artifact, and `release` itself edits **only** release artifacts (release notes, changelog,
bump records, release plan files).

- architecture / requirement / ADR drift → **architect** task;
- code / tooling / executable gap → **engineer** task;
- memory / learning / promotion candidate → **learn** task (hand off to the learn loop);
- `release` never edits ADRs, production code, or `_forge/memory/` in-cycle.

Extracting `learn` as its own role (above) is what makes this invariant mechanically true
rather than aspirational: without a `learn` role, "review memory and promote" has nowhere to
go but back into `release`.

Project agent incarnation:

- keystone defines the reusable roles in `roles/release.md` and `roles/learn.md`, and the
  pipeline in `pipelines/release.md`;
- each consuming project may add `_forge/agents/release/README.md` with local release commands,
  package registry details, project-specific verification, and downstream propagation policy,
  and `_forge/agents/learn/README.md` for project-specific learning sinks.

### Role-axis placement

`release` and `learn` are new values on the **Role** axis, alongside `architect` / `engineer`.
They place on the three orthogonal axes the same way every role does (see `roles/README.md`):

| Axis | `release` | `learn` |
|---|---|---|
| **Role** (definition = pipeline + requirements + guardrails) | `pipelines/release.md` + impact/version vocabulary + D5 guardrail | `pipelines/learning.md` + `memory-distill.md` + "promote only via explicit task" guardrail |
| **Layer** (where the artifact lives / whom it serves) | definition SHARED (`roles/release.md`); incarnation LOCAL (`_forge/agents/release/`); keystone's own release notes SHARED, a consuming project's LOCAL | definition SHARED (`roles/learn.md`); incarnation LOCAL (`_forge/agents/learn/`) |
| **Project type** (what the project exposes) | first-class input: `package` → build/publish + tag; keystone → pin-bump across consumers; `service` → deploy artifact | mostly invariant across project types |

An agent is the meeting point of the three axes, e.g. *alphavar's release agent* = `release`
(role) × LOCAL (incarnation) × `package` (project type). Both roles are **DEVELOP**; neither
introduces an OPERATE branch — OPERATE is consuming the published release, not producing it.

### Subject relativity — DEVELOP/OPERATE/USAGE are relative to a subject

DEVELOP / OPERATE / USAGE are **Layer-axis** relations, **not roles** (the Role axis is
`architect`/`engineer`/`release`/`learn`). And they are not a global mode the actor is "in":
each is a **relation between the actor and a chosen subject project**. One session holds two at
once:

- developing alphavar = **DEVELOP** relative to *alphavar*, and simultaneously **USAGE**
  relative to *keystone* (we consume the mounted standard);
- evolving the standard = **DEVELOP** relative to *keystone* (this design, T3/T10–T13);
- running alphavar against a live market = **OPERATE** relative to *alphavar*
  (out of keystone scope for now — ROADMAP O1).

Two **consumption** relations, split by consequence — do not conflate:

- **USAGE consumption** — build/dev-time, deterministic, reversible: using a library, or
  mounting and following keystone. "Developing alphavar with keystone" is the USAGE relation to
  keystone, **not** OPERATE, even though colloquially we "operate with keystone."
- **OPERATE consumption** — runtime with real, often irreversible consequences (orders, money).
  Reserved for a runtime actor; its guardrails differ in kind from D#/USAGE rules.

The recursion to keep in mind: **keystone's USAGE relation *is* the consuming project's DEVELOP
relation** — the same activity seen from two subjects. That is why mounting keystone feels like
"using keystone while developing alphavar": both are true, because each names a different
subject.

Consequence for `release`: the role is **parameterized by subject**, not split into variants.
Its first gate (Frame, step 1) selects exactly one subject — *this project's package*, or
*keystone* (its tag), or *a keystone pin bump recorded inside this project*. One role definition
in keystone, incarnated per subject. When this standard travels into a developed project, that
project's release agent inherits the same subject choice: it can cut the project's own version
**or** bump its keystone pin — different release subjects, not different roles.

## Release Cycle

The pipeline runs in one of **two modes** — frequent releases must not pay for a full audit
every cut:

- **lightweight cut** (default): `frame → collect → classify → owner gates → prepare artifacts
  → verify → owner handoff → propagate`. Steps 1–4, 8–11 below. The everyday path.
- **periodic cadence** (deliberate, not every release): the lightweight cut **plus** the sweep
  steps 5–7 and post-release learning (step 12). Run on a cadence or when drift is suspected,
  not on every tag.

The sweep steps are where `release` hands off, never does the work itself (see the
anti-super-role invariant): step 6 hands the learn loop to the **`learn`** role; steps 5/7 file
architect/engineer tasks for what they find.

Steps (a loop with gates; the mode selects which run):

1. **Frame release scope** — select the release **subject** (see
   [Subject relativity](#subject-relativity--developoperateusage-are-relative-to-a-subject)):
   keystone itself, the project package, or a keystone pin bump inside a consuming project. Ask
   for target consumers when ambiguous.
2. **Collect state** — read `TASKS.md`, `TASKS_ARCHIVE.md`, relevant design docs/ADRs,
   requirements, memory index, skills/tools, CI config, and current git status.
3. **Classify changes** — group closed work since the last release into impact classes:
   `internal`, `consumer-visible`, `migration`, `breaking`.
4. **Ask owner gates** — confirm version class, breaking-change handling, migration notes,
   whether to defer incomplete items, and downstream projects to update.
5. **Hygiene sweep** *(cadence)* — file tasks for stale backlog entries, orphaned generated
   files, stale memory, missing skill contracts, obsolete local tools, and missing docs
   pointers. `release` files the tasks; the owning role fixes them.
6. **Learning sweep** *(cadence — hand off to `learn`)* — invoke the **`learn`** role to run
   the learn loop (memory → local asset → promote candidates). `release` does not promote
   memory itself; promotion candidates become explicit `learn` tasks.
7. **Architecture / guardrail sweep** *(cadence)* — check current architecture requirements, ADR drift,
   role declarations, D#/R# compliance, secrets policy, generated pointer drift, and CI coverage.
8. **Prepare release artifacts** — update release notes/changelog, optional release manifest,
   and downstream bump notes. Keep task archive as traceability, not release prose.
9. **Verify** — run the project's release check set. For keystone: `sync --check`,
   `verify --strict`, `self_ci.py`, and `pytest _forge/keystone/tests`.
10. **Owner handoff** — present exact commit/tag/publish/pin-bump commands and the residual risk.
    Stop before D5-owned actions. The owner runs the landing commands.
11. **Propagate** — for each selected consuming project, bump the pin/version, run local sync and
    verify, record the bump, and hand off owner-owned landing actions.
12. **Post-release learning** — capture any release friction into memory or tasks; promote only
    through the learning pipeline.

## Release-Time Scope

The release agent coordinates a readiness cycle. It should distinguish **must-do before this
release**, **record as follow-up**, and **out of scope**.

Do inside the release cycle:

- confirm release scope, target consumers, version class, and owner gates;
- inspect current `git status` and separate release-relevant changes from unrelated work;
- check `TASKS.md` for active/blocking/deferred work that affects release readiness;
- check `TASKS_ARCHIVE.md` since the last release and map closed work to consumer impact;
- update or draft release notes/changelog entries for consumer-visible changes;
- run required verification commands and record failures as blockers or follow-up tasks;
- check generated files/pointers (`sync --check`) and project contract (`verify --strict`);
- check CI includes the required release verification spine;
- review `.env` / secret guardrails at the policy level, without exposing secret values;
- review requirement/ADR drift at a triage level: file architect tasks for mismatches;
- review memory and provider-private learnings for distillation candidates;
- review local skills/tools for stale, missing, or promotion-worthy assets;
- identify learning-loop promotion candidates, but promote only through explicit tasks/PRs;
- prepare downstream bump instructions and exact owner handoff commands.

Usually record as follow-up, not inside the release cycle:

- implementing new code or refactors discovered during release;
- writing new skills/tools beyond tiny metadata fixes needed for verification;
- substantial architecture redesign or new ADRs;
- broad dependency upgrades unrelated to release verification;
- large documentation rewrites;
- migrating stored data or user assets;
- expanding CI beyond the release gate unless release verification cannot run without it.

Out of scope for the release role:

- committing, tagging, pushing, publishing, merging, or bumping pins without explicit owner
  execution;
- making load-bearing architecture decisions;
- implementing production code or executable tooling changes;
- runtime/OPERATE actions such as trading, moving money, or irreversible external operations.

## Sensible Release Checks

These checks belong in the release role vocabulary, but individual projects can tailor the exact
commands in their `_forge/agents/release/README.md`.

Common checks:

- backlog hygiene: no `done` entries in live `TASKS.md`; blockers are explicit;
- archive hygiene: closed release-relevant tasks are in `TASKS_ARCHIVE.md`;
- release notes: every `consumer-visible`, `migration`, or `breaking` change has an entry;
- verification: tests/lint/project contract checks pass;
- generated assets: generated pointers or docs are current;
- secrets: no new secret-bearing files are staged or referenced in docs;
- architecture: requirement docs and ADR pointers are not obviously stale;
- memory: `_forge/memory/` is indexed, and release friction is captured;
- learning: promotion candidates are listed as tasks, not silently copied;
- skills/tools: source skills satisfy the shared contract; obsolete generated stubs are pruned;
- packaging/distribution: version metadata, package build, docs build, or artifact checks run
  where the project type requires them;
- downstream propagation: each selected consuming project has a bump plan and local verification
  command list.

Keystone-specific checks:

- `python3 _forge/keystone/bin/sync.py --check`;
- `python3 _forge/keystone/bin/verify.py --strict`;
- `python3 _forge/keystone/bin/self_ci.py`;
- `uv run pytest _forge/keystone/tests`;
- review changes to roles, pipelines, guardrails, hooks, and generated pointer contracts as
  consumer-visible by default.

## Tooling / Skill Shape

The release role likely needs both a skill and a tool, with a strict D5 boundary.

Release skill:

- teaches the agent how to conduct the release conversation;
- lists required owner questions and gates;
- maps project type to verification commands;
- explains how to classify impact and draft release notes;
- tells the agent when to stop and hand commands to the owner.

Release tool:

- runs read-only checks and local validation;
- can generate a release checklist or command plan;
- can draft release notes or bump instructions in files after the owner asks;
- should support dry-run / plan modes by default;
- must not run `git commit`, `git tag`, `git push`, package publish commands, or downstream
  pin-bump commits on its own.

Owner-run command plan example:

```bash
# prepared by release agent/tool, executed by owner
git status
git add <reviewed files>
git commit -m "release keystone vX.Y.Z"
git tag vX.Y.Z
git push origin main --tags
```

Open point: whether the tool should merely print these commands, write them to a reviewed
release plan file, or both.

## Options

### A. Manual changelog only

Add `CHANGELOG.md` with an `Unreleased` section and require maintainers to update it when a
consumer-visible task closes.

Pros:
- fastest path;
- familiar to humans;
- no new tooling.

Cons:
- weak when releases are frequent;
- no standard bump workflow across consuming projects;
- easy to forget links between tasks, release notes, and tags.

### B. Release role + pipeline plus changelog

Add a keystone `release` role and pipeline that defines:

- when a closed task must produce a release-note entry;
- how `TASKS_ARCHIVE.md` feeds release notes without replacing them;
- how to classify impact (`internal`, `consumer-visible`, `breaking`, `migration`);
- release cut checks;
- downstream bump checks.

Pros:
- common rule for all consuming projects;
- keeps archives and changelog separated;
- enough structure for frequent releases without building a productized release tool.
- gives a dedicated agent the authority to coordinate across architect/engineer/learning
  without taking over their decisions.

Cons:
- still partly manual;
- needs discipline at task close and release cut.
- requires careful boundaries so release does not become a hidden super-role.

### C. Release manifest and tooling

Add a machine-readable release manifest and tooling that derives changelog fragments,
validates task IDs, compares pins, and prints upgrade notes.

Pros:
- strongest consistency;
- good long-term fit if many projects bump often.

Cons:
- larger implementation surface;
- premature before the release vocabulary is stable.

## Leaning

Choose option B first.

Rationale: multiple projects and frequent releases justify a shared pipeline, but the model
still needs to stabilize before adding a manifest/tooling layer. The pipeline can leave
explicit extension points for option C.

## Proposed Shape

New/updated keystone artifacts:

- `roles/release.md` — shared release role definition (lightweight cut + periodic cadence).
- `roles/learn.md` — shared learn role, extracted from the existing learn-loop pipelines so
  `release` can hand off to it instead of absorbing learning work.
- `roles/README.md` — add `release` and `learn` rows to the role table (per
  [Role-axis placement](#role-axis-placement)).
- `pipelines/release.md` — shared release pipeline; references `learning.md`/`memory-distill.md`
  for the learning gate rather than restating them.
- `CHANGELOG.md` — consumer-facing release notes for keystone itself, with an `Unreleased`
  section.
- `BOOTSTRAP.md` — downstream bump procedure references release notes and release pipeline.
- `bin/verify.py` — low-risk structural checks only, not semantic release correctness. One
  cheap addition lands now: **warn when `CHANGELOG.md` exists without an `Unreleased`
  section** — keeps the "consumer-visible task ⇒ changelog entry" discipline mechanical
  rather than trust-based.

Possible later artifacts:

- `RELEASES.md` or `releases/<version>.md` if tag-to-task traceability becomes too dense for
  `CHANGELOG.md`.
- release-note fragments under `_forge/changes/` if multiple agents frequently land changes
  before a release cut.

## Release Vocabulary

Impact classes:

- `internal` — no consuming-project action; archive only is enough.
- `consumer-visible` — release-note entry required.
- `migration` — release-note entry with explicit downstream steps.
- `breaking` — release-note entry plus owner confirmation before tag.

Version classes:

- `patch` — fixes or internal process changes with no consuming-project migration.
- `minor` — new capabilities or stricter checks that are backward-compatible.
- `major` — breaking changes to keystone layout, required files, role/pipeline contracts, or
  generated artifacts.

**Decision — `v0.x.y` until the standard stabilizes.** While keystone is pre-1.0, the compat
signal is carried by `x`: bump `x` for any **breaking** change to layout, required files, or a
role/pipeline contract; bump `y` for `minor`/`patch`. This is the cheapest signal that lets a
consumer decide whether to bump a pin without reading commits — the stated goal in §Frame.
Promote to strict SemVer (`1.0.0`) only once the role/pipeline contracts stop moving.

## Open Points

- How much release metadata belongs in `CHANGELOG.md` versus a separate release manifest?
- Should every archived task carry an impact class, or only release-relevant tasks?
- How should consuming projects record a keystone bump: archive entry, dedicated ledger, or
  ordinary project changelog entry?
- Should `sync.py` eventually print "what changed since your pin", and if so does it compare
  git tags, commits, or a release manifest?
- What exact owner prompts are mandatory before a release agent proceeds past classify,
  verify, and publish gates?
- Which architecture checks are generic enough for keystone, and which must stay project-local
  in each `_forge/agents/release/README.md`?

Resolved in this revision (were open points): two-mode cycle (lightweight cut vs periodic
cadence), `v0.x.y` versioning, the `Unreleased` changelog warn, and extracting `learn` as a
sibling role so `release` routes learning work instead of owning it.

## Rejected For Now

Single `CHANGELOG.md` as the whole solution.

Why: it does not define how tasks feed release notes, how releases are cut, or how multiple
consuming projects perform and record pin bumps.

Revisit if keystone stays single-consumer or releases become rare.
