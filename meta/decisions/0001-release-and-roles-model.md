# 0001 — Release/versioning standard and the release/learn roles

- **Status:** Accepted (owner-scoped).
- **Owner:** akuminov@gmail.com
- **References:** [ROADMAP O2](../ROADMAP.md) (release/versioning gap, resolved here) ·
  [design/release-versioning.md](../design/release-versioning.md) (the living concept this
  locks) · [roles/architect](../../roles/architect.md), [roles/engineer](../../roles/engineer.md) ·
  D5 (owner owns commits) · backlog T10–T15.

> This is keystone's **first ADR** and therefore also establishes the convention:
> `_forge/keystone/decisions/` holds ADRs for the **standard itself** (SHARED, travels with the
> submodule), parallel to a consuming project's `docs/dev/decisions/`. ADRs are numbered, not
> dated — the commit history is the timeline ([tasks](../../pipelines/tasks.md) §No dates).

## Context

keystone is one submodule consumed by N projects; bumping the pin is a recurring operation, and
the learn loop means the standard retunes itself. ROADMAP O2 asked for a **release / versioning /
compatibility** model so a consumer can decide whether to accept a new pin *without reading raw
commits*, and so keystone maintainers can cut a release by one repeatable pipeline — all without
violating D5.

The design also surfaced a deeper modelling point: the release cycle keeps wanting to "review
memory and promote", "audit architecture", "fix tooling" — i.e. it threatens to become a hidden
super-role. And the act of *using* a published release is relative to which project is the
subject. Both needed pinning before the release role could be specified safely.

The full options analysis (A manual changelog · B role+pipeline · C manifest+tooling) lives in
the design doc; this ADR records only the locked decisions.

## Decision

1. **`release` is a new role on the Role axis** (alongside `architect`/`engineer`), not an
   architect/engineer profile. Role = pipeline + requirements + guardrails: `pipelines/release.md`
   + the impact/version vocabulary + a **D5 guardrail** (the role *prepares* commit/tag/publish/
   pin-bump commands; the owner executes them). It is a **DEVELOP** role.

2. **`learn` is extracted as a sibling role** owning the learn loop
   (`pipelines/learning.md` + `pipelines/memory-distill.md`), which until now was referenced as a
   "learning role" with no role file. Extraction is what lets `release` **hand off** the learning
   gate instead of absorbing it.

3. **Anti-super-role invariant (routing, not doing).** `release` coordinates; it does not
   implement. Every sweep finding becomes a task owned by the owning role — architecture/ADR drift
   → `architect`, code/tooling gap → `engineer`, memory/promotion → `learn` — and `release` itself
   edits **only** release artifacts (release notes, changelog, bump records, release plan files).
   It never edits ADRs, production code, or `_forge/memory/` in-cycle.

4. **The release pipeline runs in two modes.** A **lightweight cut** (default:
   frame → collect → classify → owner gates → prepare → verify → handoff → propagate) for everyday
   releases, and a **periodic cadence** (lightweight cut **plus** the hygiene/architecture sweeps
   and the learn-loop handoff) run deliberately, not on every tag. Frequent releases must not pay
   for a full audit each time.

5. **`release` is parameterized by subject, not split into variants.** Its first gate selects one
   **subject**: *this project's package*, *keystone* (its tag), or *a keystone pin bump recorded
   inside a consuming project*. One role definition in keystone, incarnated per subject; a
   developed project's release agent inherits the same subject choice.

6. **Subject relativity of the Layer axis.** DEVELOP / OPERATE / USAGE are **Layer-axis
   relations between an actor and a chosen subject project**, not roles and not a global mode. One
   session holds two at once: developing alphavar is DEVELOP relative to *alphavar* and USAGE
   relative to *keystone* (consuming the mounted standard). The two consumption relations differ by
   **consequence**: USAGE consumption is build/dev-time and reversible (using a library; following
   keystone); OPERATE consumption is runtime with real, often irreversible consequences (orders,
   money) and is reserved for a runtime actor (ROADMAP O1, out of scope). Mounting keystone is
   USAGE, **not** OPERATE — keystone's USAGE relation *is* the consuming project's DEVELOP relation.

7. **Versioning: `v0.x.y` until the standard stabilizes.** While pre-1.0, the compat signal rides
   on `x`: bump `x` for a breaking change to layout, required files, or a role/pipeline contract;
   bump `y` for minor/patch. Promote to strict SemVer (`1.0.0`) only once the role/pipeline
   contracts stop moving.

8. **One job per artifact** (no duplication): `TASKS.md` = live queue; `TASKS_ARCHIVE.md` =
   maintainer ledger; **release notes / `CHANGELOG.md`** = consumer-facing impact log (with an
   `Unreleased` section); **tag** = published identity; **downstream bump record** = lives in the
   *consuming* project, not in keystone's release notes.

9. **Approach: option B (role + pipeline + changelog).** A machine-readable release manifest and
   productized release tooling (option C) is **deferred** until the release vocabulary stabilizes
   (backlog T14). One cheap machine check lands now: `verify.py` **warns** when `CHANGELOG.md`
   exists without an `Unreleased` section, keeping "consumer-visible task ⇒ changelog entry"
   mechanical rather than trust-based.

## Consequences

- Two new role definitions ship in keystone (`roles/release.md`, `roles/learn.md`) plus
  `pipelines/release.md`; `roles/README.md` gains the two rows and the subject-relativity note.
- The learn loop gains an owning role; existing learn pipelines are wired under it rather than
  floating.
- keystone gains `CHANGELOG.md`, a `decisions/` ADR convention (this file), and a small
  `verify.py` check. `BOOTSTRAP.md` gains a downstream-bump reference.
- Consuming projects inherit the release/learn roles and the subject-parameterized release flow
  when they bump their pin; each may add `_forge/agents/{release,learn}/README.md` incarnations.
- D5 is unchanged and remains the hard boundary at the release handoff.

## Rollout

Phased via the backlog ([TASKS.md](../TASKS.md)); this ADR is the locked source:

- **T10** — extract `learn` role (`roles/learn.md`, README row, pipeline wiring).
- **T11** — `release` role + `pipelines/release.md` (two modes, routing, subject gate).
- **T12** — `v0.x.y` + `CHANGELOG.md` (`Unreleased`) + `BOOTSTRAP.md` bump reference.
- **T13** — `verify.py` `Unreleased` warn + test.
- **T15** — subject-relativity into the layer model (`README.md` / `roles/README.md`).
- **T14** *(deferred)* — release skill/tool (propose/prepare), only after the vocabulary settles.

Open points that do **not** block this lock are kept in the design doc's §Open Points.
