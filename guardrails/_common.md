# Guardrails: common (all languages)

Hard rules that bind **every** agent on **every** project, regardless of language or role, applied
automatically. They are **constraints**, the floor: pipelines say *how* to work, and
[profiles/](../profiles/) layer language, environment and domain rules on top.

## Language — artifacts English

- **Persistent artifacts → always English.** Documentation, agent instructions, skills,
  memory notes, ADRs, development/architecture plans, code comments, commit messages. This
  holds **regardless of the language the user wrote in** — artifacts are read by every future
  agent, so they stay in one canonical language. Chat follows the owner's language
  ([collaboration](../rules/collaboration.md)); the two must not bleed.

## Secrets

- **Config via environment only.** Never hardcode a secret, key, token, or credential.
- **Never in the repo.** No real secret in code, config, fixtures, docs, or a commit.
  Secrets come from `.env` (gitignored); `*.env.example` carries empty placeholders.
- A secret in a diff fails [pre-commit](../pipelines/pre-commit.md).

## Privilege escalation

- **Never run `sudo`, or otherwise try to elevate privileges.** The agent operates as an
  unprivileged user by design. Hitting a permission boundary (a root-owned file, a denied
  write) is information, not an obstacle to route around — explain it to the owner and stop;
  do not `sudo`, `chown`, `chmod` the way past it, or otherwise reach for elevated access.
- **Never write the `env` of a harness settings file** — the launcher sets the run's actor there.

Runtime check: privilege.no-escalation — whole; detail in [hooks/README.md](../hooks/README.md).

## Commits & ownership

- **Never `git add` / `commit` / `push` on the owner's behalf** unless explicitly told.
  The owner stages and commits.
- **No AI `Co-Authored-By` trailer** — the committer is the human.
- **Tests pass before a commit is offered.** No commit on red (see
  [pre-commit](../pipelines/pre-commit.md)).
- Branch for non-trivial work, named by its task id after any prefix (`agent/C12-x`) — the default
  and release branches aside; do not commit straight to the default branch unless asked.
- **Job-branch carve-out** — the one standing exception to the first bullet. A parallel job runs
  in its own worktree, `.worktrees/<id>-<name>.<n>/`, on the local branch
  `_aitna/<id>-<name>.<n>`. Inside that worktree the agent commits its own work on that branch
  without asking. It never pushes or tags — but an `autonomous` run (no developer) pushes its own
  branch and opens a pull request into the default branch, never committing to it or to `develop`.
  Carrying the branch's work into the branch the owner is on is
  started by the owner only. When the job is ready the agent commits it there and prints the squash
  — `git merge --squash <branch>` in the owner's checkout, then a commit with its proposed message —
  which the owner runs or asks the agent to run. The agent confirms a carry by code (`park worktrees
  <branch>` reads it by content) when the owner says it is done, never from the owner's words or the log.
  After the carry the agent prints the worktree's removal (`git worktree remove <path>`, which
  git refuses while anything is uncommitted); the branch stays as a backup and the agent deletes it
  later — at a periodic check, on request, or when the task closes — only after the code check that
  every path the branch changed holds the same content in the owner's branch and no lease is live. A commit once made
  stays as made: the agent does not rewrite it (amend, rebase, reset to an earlier commit) to ease
  the carry unless the owner says so, and brings the owner's branch in by merge. The carve-out covers
  no other branch — the agent moves, renames or deletes no ref but its own `_aitna/` job branches —
  no other commit and no other push.

Runtime check: commits.owner-owned — subset, by actor; detail in [hooks/README.md](../hooks/README.md) and
[access_matrix.json](../common/access_matrix.json). "Tests pass before a commit is offered" and "branch for
non-trivial work" are not machine-checked.

## Verify against reality, not memory

- Confirm names, signatures, enums, env-var names, and file paths **in the code/docs**
  before relying on or documenting them — they drift.
- **Consequential choices in math, data shape or architecture are the owner's,** accepted before
  implementation and recorded in a thematic ADR block. Verify the resulting implementation against
  that intent and its evidence, without requesting acceptance of unchanged design again. Passing
  tests and plausibility are necessary, not sufficient.
- **Knowledge no source gives is gathered with the user; a math question to the owner first gathers
  how the industry does it** ([knowledge-lookup](../pipelines/knowledge-lookup.md)).

## Analysis before mutation

- **Write only on a go-ahead:** an explicit confirmation (*write it, record it, make the change*), or
  a request that was itself an edit command (*write, add, update, fix, implement*). Until then,
  analysis produces words, not edits — backlog, design docs, ADRs, requirements and process docs
  included.
- A rule saying **where** something is recorded applies only **after** the decision to record it —
  never a license to write during analysis.

These two rules, and the owner's consequential choices above, are read by audience: the session the
owner attends asks the owner ([collaboration](../rules/collaboration.md)); a delegate or an autonomous
run takes its brief as the go-ahead and reports a consequential choice instead of making it
([unattended](../rules/unattended.md)).

Runtime check: analysis.before-mutation — subset (the first planning/design doc edit of a session
raises a reminder; whether the turn is analysis-only is not decidable by a hook); detail in [hooks/README.md](../hooks/README.md).

## Documentation hygiene

- **One owner per fact.** Before adding a table / flow / list, check whether another doc
  owns it; if so, link instead of duplicating. Update the owner when the fact changes.
- Accepted decision blocks own commitments and rationale; design/tasks own open questions,
  and tasks/evidence own implementation state. A new block never inherits acceptance from
  its containing ADR. Follow [design-flow](../pipelines/design-flow.md).
- **Records live in the project.** Decisions, dispositions, plans and corrections go into the
  project's own records; scratch or raw-material locations outside it hold inputs only, and no
  record defers to them.
- **No advisory / dev-history files in the live tree.** Point-in-time reviews are archived
  with a banner; decisions become ADRs; git history is the changelog.
- **Keep the entry point single.** `AGENTS.md` is the source of truth; vendor files
  (`CLAUDE.md`, `.github/copilot-instructions.md`, …) stay thin pointers.

## Scope discipline

- Change only what the task needs; no stray edits, no unrelated refactors riding along.
- A material design gap goes back to the [architect](../roles/architect.md) role — do not
  improvise load-bearing architecture inside a code task.

## Plan shape — reach a result, then refine it

- **A plan's first deliverable is the coarsest scale at which its acceptance condition can already
  be met;** refinements come after it, each a branch that returns to that trunk with the condition
  still met ([MODEL.md](../MODEL.md) § Mission and priorities). A plan that finishes every part in
  detail before any part works has no result until its last step.

Not machine-checked; how to carry it beyond prose is open task A52.

## Route by task kind — the tier floor

- **Do not burn the orchestrator or reasoner tier on mechanical work; route by task kind,
  not by the whole task's prestige.** Every delegable kind has a named delegate
  ([MODEL.md](../MODEL.md) § Capability tiers); the orchestrator keeps only decomposition,
  routing, synthesis, and owner dialogue. Name each sub-step's delegate **up front**, in the plan.
- Escalate on signal, not by default: start at the cheapest adequate rung and move up one
  rung only on failure signals (gates red twice, the delegate flags uncertainty, a
  contested fork emerges mid-task).

Runtime check: delegation.tier-floor — subset; detail in [hooks/README.md](../hooks/README.md) (delegation-nudge).
