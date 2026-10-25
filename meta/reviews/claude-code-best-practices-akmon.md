# Review — "Claude Code: Best practices for agentic coding", read for akmon

> **Point-in-time review, not a decision.** Source: Anthropic engineering post, published 2025-04
> (23-page PDF kept under `.tmp/`). Nothing here is accepted or recorded as a task; an item
> becomes a task or a decision request only on the owner's word. Role: learn.

## Verdict

The post is a **coding-workflow** guide for one vendor's harness, written for the Claude Code of
its month. akmon already owns the *principles* it teaches (plan before code, separate writer and
reviewer, scratchpads, delegation, fresh context) and in most cases states them more strongly.
What is left for akmon is a short list of **mechanisms and gaps**, below. Do not read the rest of
the post as a to-do list.

Two cautions before using any row:

- **The mechanics are dated.** `/project:` commands, the `#` key, the "think / ultrathink"
  keywords and `--allowedTools` describe the 2025-04 harness. Re-check any harness behaviour
  against [MEASUREMENTS.md](../MEASUREMENTS.md) and [CAPABILITIES.md](../../CAPABILITIES.md) before
  relying on it; cite an `M<n>` row, not the post.
- **The post is single-vendor.** akmon serves several carriers; a point lifted from it is a
  Claude-only fact until probed on the others (AGENTS.md § Verification: no parity claim without
  a probe). Every candidate in § B carries a portability tag, and § D lists the Claude-only
  features the post describes that look worth a port.

## A. Practice → akmon owner → state

| Post (section) | akmon owner | State |
|---|---|---|
| Explore, plan, code, commit; ask for a plan and save it so you can reset (3a) | [design-flow](../../pipelines/design-flow.md), [code-flow](../../pipelines/code-flow.md), [ADR 0022](../../docs/adr/0022-local-layer-index-and-plans.md) plans | **Covered** |
| Course-correct early; plan, confirm, then code (4e) | guardrail § Analysis before mutation | **Covered**, and runtime-checked in part |
| `/clear` between tasks; keep context focused (4f) | [c80-context-fill](c80-context-fill.md), the A22 resumption pilot closed by [ADR 0019 D08](../../docs/adr/0019-collaboration-guidance-from-a22.md#d08--close-the-cold-resumption-pilot-without-a-new-rule) | **Covered** |
| Checklists and scratchpads as working state (4g) | `TASKS.md`, evidence files, the session scratchpad; `k_validator` drives a gate to green | **Covered** |
| One Claude writes, another verifies in a clean context (6a) | `k_auditor`, [ADR 0024](../../docs/adr/0024-second-opinion-by-model-priors.md) second opinion by model priors | **Covered, stronger** — the post stops at "another instance" |
| Fan-out: a script makes a task list, `claude -p` per item with a fixed OK/FAIL return (6d) | delegation by task kind, `k_*` workers, gate packs | **Covered in kind**; see B3 for the completion-string idea |
| Test-first: write tests, confirm they fail, commit them, then code without touching them; verify with an independent subagent that the code does not overfit (3b) | [engineer](../../roles/engineer.md), code-flow | **Partial** — a search of code-flow and the engineer role for the lock-the-tests step and the overfit check found neither; see B1 |
| Claude does 90% of git, including commits and PRs (3f, 3g) | guardrail § Commits & ownership; AGENTS.md "Commits" | **Deliberately different** — akmon reserves commits, pushes and PRs to the owner. Do not adopt |
| Curate the tool allowlist; commit `.claude/settings.json` (1c) | `akmon init`/`sync` write the hook wiring; this repo's `.claude/settings.json` | **Partial** — wiring ships; an allowlist recommendation for consumers was not found (`src/akmon/_init.py` mentions an allowlist only for file mounting, not permissions) — see B4 |
| "Safe YOLO": skip permissions inside a container with no internet (3d) | `permission_mode` handling in the routing and commit hooks, M17, M33, M35 | **Partial** — akmon measures what its hooks see under bypass, but ships no consumer-facing "unattended run" profile; see B4 |
| Several checkouts or git worktrees, one session each (6b, 6c) | [ADR 0022](../../docs/adr/0022-local-layer-index-and-plans.md) states the known limit: an ignored folder does not follow a task into a worktree | **Gap, known** — see B2 |
| CLAUDE.md is a prompt: keep it concise, iterate, tune emphasis, run it through a prompt improver (1b) | AGENTS.md imports, "Runtime check" lines, [claim-evidence-checks](../../docs/design/claim-evidence-checks.md) | **Gap** — see B5 |
| CLAUDE.md in parents, children and home; children load on demand (1a) | Layers SHARED / LOCAL / USAGE | **Different shape**; the on-demand child load is a token mechanism akmon does not use — see B5 |
| Parametrized prompt templates (`$ARGUMENTS`) in markdown (2c) | skills | **Gap** — akmon ships two skills; the lightweight, parametrized authoring unit is not a shipped idea — see B6 |
| Headless triggers: issue triage on a GitHub event, Claude as a subjective linter (5a, 5b) | review role; ROADMAP § O1 OPERATE | **Open by design** — OPERATE is undesigned; see B7 |
| Codebase Q&A as the onboarding workflow (3e) | [BOOTSTRAP.md](../../BOOTSTRAP.md), README | **Partial** — see B8 |
| Specific instructions, images, URLs, piped data (4a–4d, 4h) | owner-facing, not standard content | **Out of scope** unless B8 is taken |
| Jupyter notebooks, `gh`, MCP via `.mcp.json` (1d, 2b, 3h) | MCP registration is parked (A15); notebooks irrelevant | **Not relevant** here |

## B. Candidates worth an owner's look

Ordered by what I think pays most. Each names the gate it would go through; none is a task yet.

**B1 — Tests-first as a named code-flow step, with an independent overfit check.** [portable: prose; the overfit check runs on akmon's own carrier runner] The post's
strongest transferable pattern: the target is fixed and committed *before* the work, the agent may
not edit it, and a separate-context reader checks for overfitting. akmon already has the parts
(engineer, second opinion, `k_auditor`) but not this sequence for a behaviour change. Gate:
engineer role and code-flow text; architect decides whether the "do not edit the tests" clause is
a rule or a hint. The Python profile's "a behaviour change ships with a test" is the floor it
would sit on.

**B2 — Parallel sessions under worktrees: what akmon state follows the task?** [portable idea, harness-specific outcome] The post makes
3–4 simultaneous sessions the normal way to scale one owner. [ADR 0022](../../docs/adr/0022-local-layer-index-and-plans.md)
already records that an ignored folder does not follow a task into a worktree, "not measured
here". The open question is concrete: in a worktree, do the delegation log, the gate packs under
`<AITNA_ROOT>/artifacts/gates/` and the second-opinion reports land in the worktree, in the main
checkout, or nowhere? Gate: a probe by the review role, then a `MEASUREMENTS.md` row. This is
the cheapest item and the one most likely to find a real defect.

**B3 — A machine-checkable completion contract for headless delegates.** [portable] The post's fan-out
prompt demands a literal `OK` or `FAIL`. akmon's delegates return reports; whether an unattended
loop over many items can tell success from failure without reading prose is not stated.
Gate: architect, only if a fan-out use case exists in a consumer; otherwise park.

**B4 — A consumer-facing permission and unattended-run profile.** [harness-specific rendering of one akmon-owned profile] akmon measures how its hooks
behave under bypass and non-default modes, but a consumer who wants unattended work gets no
recommended allowlist, no "container, no network" stance and no statement of which akmon runtime
checks still bind there. The post's own warning (data loss, exfiltration by prompt injection)
makes this a safety statement akmon is better placed to make than the post. Gate: architect;
every carrier row needs its own probe (the post is Claude-only).

**B5 — Treat the instruction text as a prompt with a measured adherence.** [portable, and it bears on a measured Codex gap] The post's one
empirical habit is to *iterate* a context file until the model follows it. AGENTS.md here imports
a long guardrail and three profiles, and several rules are marked "not machine-checked". akmon has
no way to say which of its prose rules an agent actually follows, and no use of on-demand child
files to keep the always-loaded block short. This fits the second product priority (quality per
token). Gate: architect; evidence would come from the claim-evidence design, not from the post.

**B6 — A lightweight, parametrized recipe as the first rung of the skill ladder.** [portable source, per-carrier pointer] A
markdown file of numbered steps plus an argument is the smallest reusable unit the post offers.
akmon's learn loop promotes something general and proven to a skill; a recipe rung below the
skill would give the "repeated in a long session" procedure a place to start. It belongs to
D-AGENT-AUTHORING and D-AGENT-LEARN in [standing-agents.md](../../docs/design/standing-agents.md),
and to the "reach a result, then refine" principle. Gate: fold into A69; do not open separately.
The standing-agent template that A69 is to generate, and why oikos's `desk` is not that template,
is in § F.

**B7 — Event-triggered headless runs are the OPERATE seam.** [portable trigger, per-carrier run] The issue-triage example is the
smallest real OPERATE case: a non-interactive run triggered from outside. It is a second case for
A69's "needs a second case" column, and it shows where propose ≠ execute has to bite: the
triage run may *label*, which is low-risk and reversible, while akmon's O1 concern is the
irreversible kind. Gate: input to A69 and ROADMAP § O1, nothing earlier.

**B8 — Onboarding by asking.** [portable] akmon's BOOTSTRAP is a procedure; the post's onboarding is "ask
the agent the questions you would ask a colleague". A short "ask me about this standard" entry in
the consumer-facing docs, answerable from the tree, would need no new mechanism. Low priority.

## C. What the post does not give akmon

Nothing on evaluating an agent or a standard, on owner decision requests, on cross-vendor
differences, on provenance of facts, or on any role other than the person coding. It reports no
measurements. It supports no claim in [MODEL.md](../../MODEL.md); it is a source of ideas only.

## D. Portability — what runs on every carrier, and the Claude-only features worth porting

akmon's carriers differ in what they deliver ([CAPABILITIES.md](../../CAPABILITIES.md)). Three
tiers decide where an idea can live:

- **Portable floor.** Plain files and CLIs: `AGENTS.md` as the entry point, markdown pipelines and
  skills, `akmon tool …`. Any carrier that reads `AGENTS.md` gets them. Two measured limits apply:
  Codex does not expand `@` imports (the guardrails arrive as literal text, so they never load),
  and Gemini CLI's pointer is `delivered: unmeasured`.
- **akmon-owned carrier runner.** akmon starts a carrier itself, headless, in a clean context
  and with a per-carrier argv: the second-opinion path, with measured rows for Qwen Code
  (M180), OpenCode (M181, M186) and pi (M185), and unmeasured delivery rows for Claude Code and
  Codex CLI. Anything the post does with "a second instance" can ride on this and needs no
  harness feature.
- **Harness-specific.** Hooks that `deny` or `ask`, named subagents, slash commands, plan mode,
  rewind. Today only Claude Code has the commit guard and the delegation nudge shipped; Codex has
  the delegation nudge but no commit guard (`delivered: no`), and hook delivery there also depends
  on host trust state (N7).

### Candidates against those tiers

| Item | Tier | What differs per carrier |
|---|---|---|
| B1 tests-first | floor, plus the runner for the overfit check | Nothing in the pipeline text. The overfit reader needs a carrier with a measured argv; with no second family reachable (OpenCode and pi here reach only open-weight models) the check is a same-family review, which ADR 0024 allows only as a disclosed last resort |
| B2 worktrees | floor | A worktree is a new absolute root. N7 records that Codex trusts a project root only by its own `[projects."<root>"]` entry and that trust does not inherit from an ancestor; if that holds for a worktree, **each new worktree silently runs no hooks on Codex until it is approved.** This is an inference from N7, not a measurement: probe it, then add a row |
| B3 completion contract | floor | M180 shows `qwen` exits 0 when an unknown `-m` name silently falls back, and the exit status on an API or auth failure is unmeasured on several carriers. An **in-band literal** (`OK` / `FAIL` in the last message) is therefore more portable than an exit code. The post chose the in-band form; for akmon that choice is correct for a reason the post does not give |
| B4 permission profile | harness-specific rendering | One akmon-owned vocabulary (for example read-only, draft-only, full), compiled per carrier. The second-opinion argvs are already that compilation for "read-only": Qwen removes `write_file`, `edit` and `run_shell_command`; pi lists only `read,grep,find,ls`; OpenCode's `--agent plan` declines writes by instruction and does **not** deny bash, so it is weaker. A profile must state the effect it achieves on each carrier (`deny`, `ask`, `advisory`) exactly as CAPABILITIES does, never one claim for all |
| B5 adherence, short always-loaded block | floor | Gives the Codex `@`-import gap a different shape: a large always-loaded block is not only costly, on Codex its imported part is not loaded at all. Whether a carrier reads nested `AGENTS.md` files on demand is unmeasured here; probe per carrier |
| B6 recipe | floor source, per-carrier pointer | The source is one markdown file. `sync` already writes per-carrier skill pointers; the open probe is whether each carrier passes an argument through a skill pointer. Where one does not, the fallback is "the text after the name" read by the agent |
| B7 event-triggered run | floor | The trigger lives in CI or a scheduler, outside every harness. Only the run needs the carrier table |
| B8 onboarding | floor | None |

### Claude-only features in the post, and whether a port looks useful

| Feature (post) | Port idea | Worth it? |
|---|---|---|
| Custom slash commands with `$ARGUMENTS` (2c) | One markdown recipe as the source; `sync` renders each carrier's own command or skill pointer; one probe per carrier for argument passing | **Yes** — it is B6, and it is the one place the post names a user-authored unit |
| Nested `CLAUDE.md` loaded on demand (1a) | Keep the always-loaded block short and put role- and directory-specific rules in child `AGENTS.md` files, after probing which carriers read them | **Yes, after a probe** — it is the portable answer to the Codex `@` gap |
| Permission modes and allowlists (1c, 3d) | The B4 profile, with a per-carrier effect statement | **Yes** — it is B4 |
| Headless `-p`, JSON output and `--verbose` (5, 6d) | Already the carrier-runner pattern; the open piece is a stable result shape across carriers, see B3 | **Partly done** |
| Subagents named in the prompt (3a) | akmon's `k_*` delegates are the port; Codex has the generic launch and the named-agent rows, others none | **Done where measured**; do not claim it elsewhere |
| Esc, double-Esc rewind and undo (4e) | Not a carrier feature; the portable analogue is a checkpoint (a commit on a local non-default branch, already allowed by AGENTS.md) before a risky step | **Maybe** — a one-line pipeline habit, no mechanism |
| `/clear` between tasks (4f) | The portable analogue is the fresh-start rule akmon already tests (A22, c80); each carrier has its own reset command | **No** — covered |
| "think / ultrathink" budget keywords (3a) | Vendor knobs for effort; akmon's model routing already owns effort by tier | **No** |
| `#` to append to the context file (1b) | The learn loop's CAPTURE step as a one-line command writing to the memory file | **Maybe** — only if the learn loop shows friction at capture |
| Image paste, Puppeteer MCP screenshots (3c, 4b) | Carrier capability; akmon has no UI to verify | **No** |
| Terminal notifications when the agent waits (6c) | Per-carrier hook or the harness's own notifier | **No** — it is a UX nicety, not part of the standard |

## E. Where the post runs against akmon's own rules

Kept apart on purpose. A row here is **not** a recommendation to adopt the post's advice; it is a
place where the post and a rule disagree, so the owner can decide whether the rule is right, needs
refining, or was written before the case came up. No rule is changed by this review. Three kinds:
**direct** (the post asks for what a rule forbids), **tension** (both can hold, but they pull
apart) and **no rule** (the post assumes a practice akmon has not decided).

| # | Post | Our rule | Kind | Reading |
|---|---|---|---|---|
| E1 | **Parallel sessions on git worktrees or several checkouts** (6b, 6c) | None on worktrees. [ADR 0022](../../docs/adr/0022-local-layer-index-and-plans.md) records as a known limit that an ignored folder does not follow a task into a worktree, so a session there "resumes from the main checkout's `local/`", and leaves it to A39's open question | **No rule, with a known defect.** The owner asked to **return to the discussion** | The post makes worktrees the standard way to scale one owner. We neither allow nor forbid them, and the one place we mention them admits our local layer breaks there. Open points to bring back: (1) which state is per-task and must follow it (plans, handoffs, gate packs, the delegation log) and which is per-owner and must stay shared; (2) whether `local/` resolves to the main checkout or the worktree, and who decides; (3) the Codex hook trust-by-root question in § D (B2); (4) the term itself — ADR 0024 says "worktree" for the carrier's working directory, not for a git worktree, and the two must not share a word |
| E2 | **The agent commits after each step, writes commit messages, opens and updates PRs, fixes review comments and pushes back** (3a, 3b, 3f, 3g) | Guardrail § Commits: no staging or committing unless told. AGENTS.md narrows it for this repo: an agent **may** commit on a local non-default branch and never pushes, merges or tags. The commit hook denies a push, a tag, a merge and a commit on the default branch | **Direct for pushing and PRs; allowed for local commits** | The test-first loop (commit the tests, then the code) fits the local-branch allowance. "Create a PR" and "push back to the PR branch" do not. The post gives speed as the reason; ours is ownership of what leaves the machine. Keep the rule; consider whether the local-branch allowance is stated where a consumer will find it, since the common guardrail alone reads stricter than akmon does |
| E3 | **Skip permissions in a container for unattended work** (3d) | `delegation.tier-floor` and `commits.owner-owned` turn an `ask` into a `deny` when the permission mode is missing or not `default`; the commit guard also denies there | **Tension** | Our checks are built for a watched session: outside `default` mode nothing can answer an `ask`, so it becomes a refusal. An unattended run is therefore blocked at the first guarded action, or rides entirely on the rules that are prose. That is safe and may be right, but it means akmon has **no answer for the post's headline automation case**. Question for the owner: is "unattended" a mode akmon supports, with its own profile (B4), or one it declines on purpose. Seen while writing this review: a shell heredoc whose text merely contained git verbs was denied by the commit guard under a non-default mode ("escalated ask→deny"). The match looks like it was on the prose, not on a git command; I did not isolate which pattern fired, so treat it as a probe lead, not a finding |
| E4 | **A plan or a checklist kept in a GitHub issue** (3a, 4g) | Guardrail § Documentation hygiene: records live in the project; a location outside it holds inputs only and no record defers to it | **Direct** | A plan in an external issue is a record outside the project. For an owner who works from the tracker it can be the only place others see it. Keep the rule; if an external tracker is ever a sanctioned home for plans, that is a decision with its own ADR block, not a side effect |
| E5 | **Headless runs that label, comment on or triage issues on an event** (5a) | Sending content to an external service publishes it; posting stays behind owner approval in the review design; OPERATE is undesigned (ROADMAP O1) | **No rule** | Labelling is low-risk and reversible, but there is no rule saying which outward actions an unattended run may take. This is the O1 question and it should be answered there |
| E6 | **Tune the context file with emphasis ("IMPORTANT", "YOU MUST") until the model follows it** (1b) | Code design: a rule a program can check lives in the checker; prose holds only what no checker can see | **Tension** | Emphasis tuning is the opposite bet to ours. Both are needed for the rules no hook can reach (the "not machine-checked" lines). We have no way to tell which prose rules are followed (B5) |
| E7 | **Stay an active collaborator, approve permission prompts, cycle through 3–4 sessions** (4e, 6b) | MODEL § priority 1: invest owner attention only where it matters; reduce avoidable interruption | **Tension** | The post spends owner attention to buy quality, and a multi-session loop multiplies it. Our model says to measure attention separately from tokens. Worth deciding whether a parallel-session setup is a net saving for the owner, or only for wall-clock time |
| E8 | **Tell the agent to use subagents when you notice the problem is hard** (3a) | AGENTS.md: delegation is the default, before the first sweep, without an owner prompt | **Consistent; ours is stricter** | Not a conflict. The post makes delegation the user's call; we make it the orchestrator's |
| E9 | **The agent does most of the git work, including commits** (3f), asked for by a consumer of akmon rather than by akmon's own development: a project built on oikos, such as a manager's working installation, where akmon is a dependency and the user may not program | Guardrail § Commits & ownership: never `git add`/`commit` unless told; the owner stages and commits. The guard in § E2 | **Direct for that consumer, with a design question for akmon** | **Owner's decision:** for akmon's own development the rule stays unchanged, a developer commits. For oikos-based projects a **different mode** is needed in which the rule is relaxed, but only to **semi-automatic**: the agent asks the user whether to record the change in the history, and a simple **independent review** of the change runs before the question. Never automatic. The relaxation is **initialized from oikos** (its setup turns it on); **how akmon supports it is the question to design** — see the block below. This row is to become a conflict-resolution task |

### E9 — a relaxed commit mode for oikos-based consumers: the open points

Facts read in the tree, not measured live. `git_commit_guard_result` (`hooks/hook_core.py`, policy
`commits.owner-owned`) denies an AI co-author trailer; asks on push, tag and merge; asks on a commit
on `main`, `master` or a detached or unresolved HEAD; and lets a commit on any other branch pass.
An `ask` outside `default` permission mode becomes a `deny`. `git add` is not checked at all. The
guard is delivered on Claude Code and not on Codex ([CAPABILITIES.md](../../CAPABILITIES.md)).
So the rule in prose ("never stage or commit unless told") is wider than what the hook enforces,
and a relaxed mode has to say which of the two it changes.

The required behaviour, from the owner: **semi-automatic** — ask the user, never commit alone —
with an **independent review** before the question. Open design points:

1. **Where the mode lives and who sets it.** akmon owns the mechanism; oikos setup sets it. It
   should be an explicit, opt-in declaration in the consumer's own config (for example a key
   under `<AITNA_ROOT>/.akmon.toml`), never inferred, with akmon's own repository staying on the
   strict default. akmon should not hard-code the name of any consumer: the mode is generic
   ("confirmed commits"), oikos is the first user. `verify` should warn when the mode is declared
   but its enforcement is not wired.
2. **A weaker rule from a layer is new.** Until now a layer narrows the floor (AGENTS.md here is
   narrower than the guardrail). A mode that *relaxes* a guardrail rule reverses the direction.
   Decide whether that is a clause inside the guardrail itself ("unless the project declares the
   confirmed-commits mode"), which keeps one owner per fact, or a profile, which by its place in the
   stack cannot override a floor rule.
3. **What the question is, and who answers it.** The harness's own `ask` shows a raw command,
   which a non-programmer cannot judge. The question should be a plain-words summary produced after
   the review. Deciding whether the hook's `ask` is that question or a second prompt, and
   how an unattended run is refused (it must stay a `deny`, never an automatic yes), is part of the
   design.
4. **How the guard learns the review happened.** A hook cannot read the chat. Two shapes:
   (a) the commit goes only through an akmon tool (review, question, stage named paths, commit) and the
   hook denies a raw commit in this mode, pointing at the tool; (b) the review leaves a stamp tied
   to the staged tree and the hook allows the ask only when the stamp matches. Shape (a) is
   portable, because it lives in a CLI, and (b) is Claude-only like the guard itself. Neither is
   chosen or tested; the point is only that the hook cannot see the review by itself.
5. **The independent review, kept simple.** A clean-context reader, not the agent that made the
   change, on akmon's carrier runner or the audit tier; cheap rung first, escalate on signal. A
   small fixed checklist: does the diff match the stated intent, are secrets or ignored
   or personal files staged, is anything outside the named paths touched, do the project's own
   checks pass where it declares them. ADR 0024 requires a model-prior difference for a second
   opinion; whether a same-family reader is acceptable for a low-risk review, disclosed as such, is
   a decision.
6. **What does not relax, in any mode.** Push, merge and tag stay the owner's (ask, deny when
   unattended); the AI trailer stays denied; staging is by named path, never a sweep.
7. **Per-carrier effect.** Where the guard is not shipped (Codex), the mode rests on the tool path
   alone and must be described as `advisory` for a raw `git commit`, as CAPABILITIES already does
   for every carrier. Do not claim parity without a probe (AGENTS.md § Verification).
8. **Commit message language.** The guardrail makes commit messages persistent artifacts, in
   English, while the user may not write English. Whether the tool composes the message from the
   diff is part of the design.
9. **A branch for commits.** A fresh consumer repository has only its default branch, on which the
   guard asks today. Either the mode commits to a work branch the tool creates, or the guard's ask
   stands in for the question. This interacts with the worktree discussion in E1.
10. **The consumer side.** oikos's B8 (local repository at setup) and its E3 row are the consuming
    half. The two must be split so the oikos task creates the repository and sets the key, and the
    akmon task builds the mechanism and the check.

### What to bring to the owner

1. **E1, worktrees — a discussion, as asked.** The post and the owner's own working style both
   point at parallel sessions; we have a known limit and no rule. This is the one that most needs
   a decision (and a probe per carrier) before anything else here.
2. **E3 and E5 together** — whether unattended runs are in scope. They are one question seen from
   the permission side and the outward-action side, and both land on ROADMAP O1.
3. **E2** — a wording check only: make the local-branch commit allowance visible to a consumer.
4. E4, E6, E7 — hold the rule; record the reasons if asked.
5. **E9 — a relaxed, semi-automatic commit mode for oikos-based consumers.** The direction is the
   owner's; what is left is design (the ten points above), to be split into an akmon task for the
   mechanism and an oikos task for setup.
6. **F — the standing-agent template.** Keep oikos's `desk` out of the standard as a name and as
   a skeleton until a second case separates what is general; see § F.

## F. Standing-agent template: what the oikos review's "desk as the skeleton" means for akmon

The oikos-side review (`claude-code-best-practices-oikos.md` in the oikos repository, its B3) proposes `desk`'s shape as
the default skeleton for an agent a non-programmer creates. That is a sound choice **inside
oikos**. For akmon it is a different question, because akmon plans to own the **requirements for a
standing agent and their generation in other projects** (A69; D-AGENT-AUTHORING and
D-AGENT-DELIVERY in [standing-agents.md](../../docs/design/standing-agents.md)). Two points from
the owner shape this section.

**1. The name.** `desk` is the first case's own name, and the owner notes it collides with the name
of the current work session. akmon has already moved in this direction: the internal roster term
was `desk` and is renamed `operate_agents` under D-AGENT-OPERATE-NAME (task C168), so the
standard does not carry a case's name. What remains is the rule behind it:

- The standard and any generated charter take the agent's name as **a parameter**, never a
  literal borrowed from a case.
- D-AGENT-CONCEPTS already asks for names that collide with neither each other nor a host's own
  "agent". The owner's observation adds a collision class: **a session's name for the work in
  hand**. Whether the generator should reject such a name (a check, not prose) is for that
  decision. I did not verify where akmon or a harness keeps a session name, so the exact set of
  names to reserve is open.
- In oikos the one word `desk` names the agent, its `.local/desk/` folder, its tool
  (`tools/desk/`) and its ADR. A template must separate these (agent name, owned folder, tool
  name) so that renaming one is not a rename of all.

**2. The skeleton is one case.** `standing-agents.md` says nothing may be drafted as a rule until
the "general / specific / needs a second case" columns are written, and today there is one case.
I read `agents/desk/README.md` in oikos to see what a charter generated from it would contain:

| Part of the `desk` charter | Reading for the standard |
|---|---|
| Frontmatter: `name`, `description`, `skills`, `owns`, `metadata.owner` | **Likely general** and checkable by `verify` (a rule a program can check lives in the checker). Whether `metadata.owner` is needed is a second-case question |
| Mission, and "the agent has no rules of its own; it follows the skills it uses and links them" | **Likely general.** It is the "point at skills instead of copying their rules" requirement in D-AGENT-AUTHORING |
| Skills table (skill → used for), limited to what the installation actually uses | **General in shape.** The list is the case's |
| Owns: one folder, a retention rule (30 days to a summary, 90 to one index line), a tool that makes the folders | **General in shape** (owned state, retention, who writes what). The numbers and the `<date>/<topic>/` layout are the case's |
| Never-list (no status move without confirm, no send without a yes per item, no widening a guard, no delete, no invented link, no writing outside the owned folder) | **The most general part**, and the one a generator should require as non-empty. Each item here is oikos-specific in wording; the *kinds* (never widen a guard, never leave the owned state, never act externally without confirmation) are the standard's |
| Session start (read the index, offer compaction, report what is open, then wait) and closing a topic (a card, a summary by a worker) | **Needs a second case.** "Start by reading owned state and reporting" looks general; "topics", "cards" and "units" are the case |
| Topics, units, digest, drafting tasks and messages, `handoff park` | **Specific** to a manager's incoming-material workflow |

So the part worth lifting into requirements is the *shape of the obligations* (owned state with
retention, a never-list, a start step, links to skills instead of copied rules), not `desk`'s
content. A template copied from `desk` would carry its topic and unit vocabulary into every
project the generator touches.

**What the post adds to generation.** Its test-first and writer/reviewer patterns (oikos B5) are
a *creation flow* for a charter: the requester states example requests and the expected and
refused behaviour, the charter is drafted from them, and a clean-context reader tries the
examples. Those examples would also be the check that the never-list holds. That is an input to
D-AGENT-AUTHORING, and the post says nothing about charter requirements themselves, so the
requirements need another source.

**Delivery.** A charter is a plain file, so it is portable by construction. What differs per
carrier is how a standing agent is exposed (skill pointers, an entry file), which is
D-AGENT-DELIVERY; the generator should emit the plain charter and let `sync` render the pointers,
as it does for skills.

**Recommendation, no rule changed.** Keep `desk` as oikos's own skeleton. In akmon, treat it as the
*first row* of the general/specific/second-case table and generate from the general columns only,
with the agent's name as a parameter and a check on name collisions that includes the
session-name class. Bring this to the A69 session with D-AGENT-CONCEPTS (names) and
D-AGENT-AUTHORING (required parts).

## G. Open points found during the review

Findings that surfaced while reading the post against akmon, collected in one place. They are
**not tasks, designs or decisions**; nothing here is implemented or chosen. Each says what was
seen, what is not known, and how well the seeing is backed: **measured** (an `M<n>` row),
**read** (in the tree, not run), **inferred** (reasoning, no check) or **not checked**. The
discussion is in the section named in the last column. They are the raw material for the
conflict-resolution tasks the owner will cut later.

| # | Found | Not known | Backing | See |
|---|---|---|---|---|
| G1 | No rule on git worktrees; [ADR 0022](../../docs/adr/0022-local-layer-index-and-plans.md) itself says an ignored folder does not follow a task into a worktree | Which akmon state is per task and which per owner; whether `local/` resolves to the main checkout or the worktree; where the delegation log, gate packs and second-opinion reports land in a worktree | read (ADR), behaviour **not checked** | B2, E1 |
| G2 | Codex trusts a project root by its own entry and does not inherit from an ancestor (N7) | Whether each new worktree therefore runs no hooks on Codex until approved | **inferred** from N7 | B2, E1, § D |
| G3 | The word "worktree" means two things: a git worktree, and the carrier's working directory in ADR 0024 | Which one keeps the word | read | E1 |
| G4 | The commit rule in prose is wider than the guard: the prose says never stage or commit unless told, the hook checks a co-author trailer, push, tag, merge and a commit on `main`, `master` or a detached HEAD; `git add` and a commit on any other branch are not checked | Whether the gap is intended; what a consumer reading only the guardrail believes is enforced | **read** (`hooks/hook_core.py`), not run | E2, E9 |
| G5 | The commit guard is delivered on Claude Code and not on Codex; Codex hook delivery depends on host trust state | What protects a commit on Codex besides prose | measured/read ([CAPABILITIES.md](../../CAPABILITIES.md), N7) | D, E9 |
| G6 | A shell heredoc whose text merely contained git verbs was denied by the commit guard under a non-default mode ("escalated ask→deny") | Which pattern fired; whether prose can trip the guard in general | seen once, **not isolated** | E3 |
| G7 | An unattended run is blocked at the first guarded action, because an `ask` becomes a `deny` outside `default` mode | Whether akmon supports unattended runs at all, or declines them on purpose | **read** | E3, B4 |
| G8 | No rule says which outward actions a headless, event-triggered run may take; OPERATE is undesigned | Where the line between "label" and "send" sits | read (ROADMAP § O1) | B7, E5 |
| G9 | A relaxed, semi-automatic commit mode is wanted for oikos-based consumers (owner's direction: ask the user, independent review first, never automatic); akmon's own rule stays | Where the mode is declared; whether a layer may relax a floor rule when until now a layer only narrows; how the guard learns that a review took place; which reader is independent enough and whether same-family is acceptable (ADR 0024); the language of the commit message; which branch the commit goes to; how the work splits between akmon and oikos | owner's direction plus **read**; no design | E9 |
| G10 | The harness attribution text given to this session asks for an AI co-author trailer on commits, which `commits.owner-owned` denies | Whether a consumer's agents meet the same conflict between a harness default and the guardrail, and which one wins | seen in session context, **not exercised** | E2 |
| G11 | A search of code-flow and the engineer role found neither a "lock the tests" step nor an overfit check | Whether the step lives elsewhere; whether it is a rule or a hint | **read** (search) | A, B1 |
| G12 | akmon cannot say which of its prose rules an agent follows; rules marked "not machine-checked" have no measurement | How to measure adherence | read | B5, E6 |
| G13 | Whether a carrier loads nested `AGENTS.md` files on demand is unmeasured; Codex does not expand `@` imports (measured) | Per carrier, whether a shorter always-loaded block can lean on child files | Codex measured; others **not checked** | B5, D |
| G14 | Whether each carrier passes an argument through a skill pointer is unmeasured | How a parametrized recipe would reach each carrier | **not checked** | B6, D |
| G15 | The exit status of a carrier on an API or auth failure is unmeasured on several carriers; `qwen` exits 0 when an unknown model name silently falls back (M180) | Which carriers give a usable machine signal | M180 measured; the rest **not checked** | B3, D |
| G16 | `OpenCode --agent plan` declines writes by instruction and does not deny bash (measured), so a "read-only" stance differs per carrier | The effect (`deny`, `ask`, `advisory`) of an unattended-run profile on each carrier | measured for the second-opinion argvs, **not checked** for a general profile | B4, D |
| G17 | The consumer-facing guardrail reads stricter than akmon's own local-branch commit allowance | Whether a consumer can find the allowance | read | E2 |
| G18 | A multi-session working style multiplies owner attention, which MODEL § priority 1 says to spend only where it matters | Whether parallel sessions are a net saving for the owner or only for wall-clock time | **not measured** | E7 |
| G19 | Plans in an external tracker conflict with "records live in the project" | Whether an external tracker may ever be a sanctioned home for plans | read | E4 |
| G20 | oikos's `desk` is one standing agent; standing-agents design says nothing is a rule on one case | Which parts of its charter are general; whether `metadata.owner` is needed | read | F |
| G21 | The owner notes the name `desk` collides with the name of the current work session | Where a session name is kept; which names a generator should reject. The internal roster term is already renamed (C168) | owner's observation; **not checked** | F |
| G22 | The post is from 2025-04 and single-vendor; its mechanics (`/project:`, `#`, "ultrathink", `--allowedTools`) may be stale | Which of them still work in the current harness version | **not checked** | Verdict |
