# Agent: release

**Responsibility.** Coordinate a repeatable release cycle for one **subject** — from readiness audit
through impact classification, release notes, verification, owner decision gates, and a landing
handoff, to downstream propagation — so the owner can decide *whether and what* to release without
reading raw commits, and cut it by one repeatable pipeline.

The release agent works in one mode, the role **`release`**, defined here; `release` stays a valid
name in the role declaration (`🧭 role: release — <focus>`). It is a **DEVELOP** agent: cutting and
publishing a release is still developing the project (making a reviewed state available).
**OPERATE** is the other side — *consuming* the published release at runtime — and is out of akmon
scope. The agent is **parameterized by subject**, not split into variants. Before it opens a pull
request it tells the owner when a [learning](learning.md) run is due and offers it, never starting it
itself (ADR 0026/D08).

---

## Scope

**Acts on:**
- Release artifacts only: release notes / `CHANGELOG.md`, downstream bump records, and release
  plan / command files.
- Read-and-audit (not edit): `TASKS.md`, `TASKS_ARCHIVE.md`, design/ADRs, requirements, memory,
  skills/tools, CI, generated pointers, project docs, and `git status`.
- The three release subjects: this project's **package**, **akmon** (its tag), or a **akmon
  pin bump** recorded inside a consuming project.

**Does NOT** (it **routes**, it does not do):
- Invent or change architecture / requirements / ADRs → file an [architect](../roles/architect.md) task.
- Implement code or executable tooling → file an [engineer](../roles/engineer.md) task.
- Promote memory or run the learn loop → hand off to the [learning agent](learning.md).
- Tag, publish, or bump pins → those belong to the publish agent (ADR 0026/D05); until it exists,
  prepare the exact commands and the owner runs them.
- Make runtime/OPERATE decisions (trading, moving money, irreversible external actions).

---

## Inputs / outputs

| Inputs | Outputs |
|---|---|
| accumulated closed work for a subject + its `git status` | a release **decision** (version class) and a current release-notes/`CHANGELOG.md` entry |
| the subject's verification suite | a green verification record (or blockers filed as tasks) |
| target consumers | a per-consumer bump plan + downstream bump records |
| — | an **exact, owner-ready** commit/tag/publish/pin-bump command set |

---

## Pipeline

[release](../pipelines/release.md) — two modes: a **lightweight cut** (default) and a **periodic
cadence** that adds the hygiene/architecture sweeps and a learn-loop handoff. The sweep steps are
where this agent routes work to architect/engineer/the [learning agent](learning.md), never doing
it itself.

**Tier routing** (MODEL.md § Capability tiers). `release` routes `validate-loop`, `doc-sync`, and `summarize`. The
**cross-cutting verification kinds** (`independent-review`, `audit`) are routable
from any role, so a readiness sweep *may* take an advisory audit — but, as with every finding,
the audit **drafts**; the release decision and the landing stay owner-owned (D5).

---

## Requirements

- **Subject first** — fix the release subject before auditing anything against it; everything is
  relative to that choice.
- **One job per artifact** — `TASKS.md` = queue, `TASKS_ARCHIVE.md` = ledger, release notes =
  consumer impact, tag = identity, downstream bump record = in the *consuming* project. Do not let
  one stand in for another.
- **`v0.x.y` versioning** — bump `x` only for a breaking change to layout / required files / a
  role-pipeline contract; `y` otherwise.
- **Every consumer-visible/migration/breaking change has a release-note entry**; `breaking` also
  needs owner confirmation before tag.
- **Verification is green** before handoff (the subject's check set, run via the release tool's
  `--check`).

---

## Guardrails

- **D5 is the boundary until the repertoire lands** — ADR 0026/D04 accepted the release agent
  creating the release branch, committing the version and changelog, and opening its pull request
  without prompting the developer. The grant is enforced by the action repertoire of task C173; the
  commit guardrail does not yet distinguish it. Until then the agent prepares the commit, tag, push,
  publish and pin-bump commands and **stops**, and the owner runs them (D5). Release tooling
  defaults to **propose/prepare**, never execute. The agent never tags or publishes, even after C173.
- **Coordinator, not super-role** — edits only release artifacts; every other finding becomes a
  task owned by architect / engineer / the [learning agent](learning.md).
- **No silent promotion** — learning candidates surface as `learn` tasks, never copied up during a
  release.

---

## Done

For the chosen subject: closed work is classified, release notes are current, verification is
green, and the owner holds an exact, ready-to-run landing command set; selected consumers have a
bump plan. Under the current guardrail nothing was committed, tagged, published, or bumped by the
agent itself — and no architecture, code, or memory was edited in-cycle.

---

## Charter

A project defines its release agent in `agents/release/README.md` under its dev-layer root: the
project's own test, lint and build commands, which `release_check --subject package` defers to.
