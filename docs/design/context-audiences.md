# Starting context by audience — the head, the delegate, the autonomous run

Task **A49** (actualize the starting context). Status: **decided** — [ADR 0033](../adr/0033-starting-context-by-audience.md) D01–D06; the trunk
of §5 is built, and the refinements are open.

## 1. Essence

Every session akmon starts receives the same chain of rules, but the sessions are read by different
people:

- the **head** session talks with the owner. It needs the owner-dialogue rules: reply language,
  decision codes, the `Needed from you` block and the role line.
- a **delegate** is a subagent launched by the head, and only the head reads it. The head digests
  the delegate's report for the owner. For a delegate the dialogue rules cost context, and they make
  it talk to an owner who is not there.
- an **autonomous run** has no developer at all. Nobody answers a `Needed from you` block, and a
  stop to ask ends the run.

So the starting context is split into three layers, and each layer goes only to its audience:

| Layer | Audience | Holds | Source |
|---|---|---|---|
| floor | everyone | the prohibitions, the code rules, the language profiles, the project contract | `guardrails/_common.md` minus the head sections of §3, `rules/code.md`, `profiles/*`, `AGENTS.md` |
| head | the session the owner attends | owner dialogue and its shapes | `rules/collaboration.md`, `rules/templates.md`, the head sections of §3 |
| unattended | delegates and autonomous runs | finish without stopping to ask; the report to the head; where an autonomous run records a pending decision | [`rules/unattended.md`](../../rules/unattended.md) |

The unattended layer is a file of its own (owner, on D-A49-UNATTENDED). It starts small and is
filled from practice: when a learning run finds a correction in a delegate's or an autonomous run's
sessions, it proposes the correction there.

## 2. As-is

The figures below come from a replay of this repository's session transcripts made during the A49
analysis. They are not yet a `MEASUREMENTS.md` row.

- **Every `k_*` delegate gets the whole chain.** The last 30 delegate transcripts each carry ten
  instruction files, about 38 KB or 9.5k tokens. The delegates were explorer, implementer, validator,
  reasoner and auditor. The files are `CLAUDE.md`, `AGENTS.md`, the guardrail, collaboration,
  templates, code, three profiles and `MEMORY.md`. The custom agent of M247 confirms the mechanism.
  No SessionStart text reaches a delegate (M39, M247).
- **About 7–9 KB of it is head-only (20–25%).** That is `rules/collaboration.md` and
  `rules/templates.md` (5.3 KB), the guardrail sections of §3, and the owner-dialogue sentences of
  `AGENTS.md`.
- **The head rules leak into delegates' output.** In 139 delegate transcripts, the assistant text
  of 4 carries a `Needed from you` block, 1 carries a bold decision code and 3 carry a role line.
  4 reply in Russian, because the memory note on chat language loads into delegates too.
- **Nothing tells an autonomous run what to do instead.** `rules/collaboration.md` and the guardrail
  say "every agent, every role". The only attended/unattended split in the tree is the hook `ask`
  path (`hooks/README.md`) and the actor matrix (ADR 0031/D07).
- **On Codex the imported floor does not load at all.** Codex never expands `@`-imports (M40), so a
  Codex session and its subagents get only the body of `AGENTS.md`.

## 3. What moves where

- **To the head layer:**
  - `rules/collaboration.md` and `rules/templates.md`, rewritten to say "the head session" instead
    of "every agent";
  - from the guardrail, the Role declaration section;
  - from the guardrail, the owner-facing half of Analysis before mutation: report in chat first,
    write after a go-ahead.

  The other guardrail sections stay in the floor, each with a reading per audience (§7).
- **Stays in the floor:**
  - Language (artifacts English), Secrets, Privilege, Commits, Verify, Documentation hygiene and
    Scope;
  - `rules/code.md` and the profiles (on-demand loading stays closed, ADR 0014 amendment);
  - `AGENTS.md` whole. § Delegation stays inline on purpose, because Codex expands no `@`-import.
  - `AGENTS.md` § Roles points at the guardrail for the role line. That pointer follows the section
    when it moves.
- **To the unattended layer:** `rules/unattended.md`. It starts with the owner's first rule: a stop
  costs a relaunch, so finish. It also holds the report to the head and the place where an
  autonomous run records a pending decision. For a delegate, the go-ahead is its brief.
- **On-demand documents** (`MODEL.md`, `roles/*`, `pipelines/*`, `agents/*`, `skills/*`) are not
  in the starting context, so they cost a delegate nothing. The gain there is one owner per rule:
  - Analysis before mutation is restated in three roles and in design-flow;
  - the owner steps of code-flow (the learning notice, the carry), release and learning have no
    sink in an autonomous run.

  Each such passage gets marked as the head's, with the unattended reading beside it. This is a
  refinement (§5).

## 4. Carriers

Probes P1–P5 measured the cells below
([results](../../meta/experiments/a49-context-audiences.md), M246–M255). An empty or "not measured"
cell is a gap.

| Carrier | Claude Code | Codex | Qwen Code |
|---|---|---|---|
| `@`-imports of the entry file | expanded; head and every custom delegate (M81, M247) | never expanded (M40) | expanded; head and every subagent (M253) |
| entry file body | as above | head and every subagent (M250) | head and every subagent (M254) |
| SessionStart `additionalContext` | head only (M39, M247); fires again on `resume` and `compact`; compaction drops the earlier text (M246) | head (M249); fires again on `resume`; `compact` not measured; copied into a child forked with `fork_turns=all` (M250, one spawn) | head only, `startup` measured (M255); project hooks refused headless (M255); system-level hooks ran (M255) |
| SubagentStart `additionalContext` | reaches the subagent (M247) | reaches the child, never the head (M250) | only through `${hook_context}` in the agent's body (M255) |
| withhold the entry file from one agent | `omitClaudeMd: true` (M247; user-scope `CLAUDE.md` and `.claude/rules/` not measured) | impossible (M251) | impossible (M254) |
| adherence through SessionStart | as `CLAUDE.md`; one prompt, opus, n=6 (M248) | not measured | not measured |
| fallback line in the entry file | not measured | followed by a strong head, not by a light one; subagents did not follow it, 0 of 4, weak (M252) | not measured |

**Choice (D-A49-AUDIENCE (a)):**
- The SessionStart hook delivers the head layer and returns it for every `source`. Compaction drops
  a text that was returned only at `startup` (M246).
- A delegate gets the unattended layer from SubagentStart.
- The entry file holds only what every agent may read: the floor, plus one fallback line for a
  session whose hook does not run.

How the hook chooses between the head layer and the unattended layer is decided (**D-A49-SELECTOR**,
§7). The actor alone is not enough: a missing `AKMON_ACTOR` reads as `developer`, so a headless
run launched without it would get the head layer.

The fallback line is worded by the owner's presence, not by head or delegate:

> *If an owner reads your replies and the owner-dialogue rules are not in your context, read
> `rules/collaboration.md`; otherwise read `rules/unattended.md`.*

The line is a fallback, never the carrier. M252 shows it is weak, and in this wording it is not
measured.

**Per harness:**

- **Claude Code:** the hook carriers above. The refinement adds `omitClaudeMd: true` for the
  read-only delegates. The mechanism that gives those delegates the floor is decided
  (**D-A49-OMIT-CARRIER**, §7).
- **Codex** (required by the owner): the entry file reaches every subagent and cannot be withheld
  (M251), so it holds the floor. SessionStart carries the head layer and SubagentStart the unattended
  layer.
  - A child forked with `fork_turns=all`, the default, inherits the head layer with the parent's
    history (M250).
  - `rules/unattended.md` states that inherited owner-dialogue rules belong to the head. Whether that
    text, or the later SubagentStart message, outweighs the inherited rules is not measured.
  - A PreToolUse guard on `collaborationspawn_agent` could steer the spawn to `fork_turns=none`
    (M62). It needs a probe (**D-A49-PROBE-FORK**, §7).
  - The untrusted-project gating rows (M19–M20) are on codex-cli 0.149.1 and were not re-measured.
  - The floor that reaches a Codex delegate is what the entry file carries inline. That is the
    pre-existing gap of C39; this design does not widen it.
- **Qwen Code** (required by the owner): the entry file and its imports reach every subagent (M253,
  M254), so the entry file holds the floor.
  - Today the head gets the dialogue rules reliably, through the expanded imports. Removing them
    before Qwen has a measured head carrier would weaken the Qwen head. The carrier until then is
    decided (**D-A49-QWEN-CARRIER**, §7).
  - The hook route has three candidates: folder trust, stored approvals, and the system-level
    settings that ran in M255.
  - SessionStart on `resume` and on compaction is not measured.
  - The unattended layer reaches an akmon-written agent through `${hook_context}`, or inline in its
    body. akmon writes no `.qwen/agents/` today.

## 5. Plan — trunk, then refinements

**Trunk acceptance**, judged from transcripts, with no regression for Qwen Code:

- On Claude Code and Codex, the entry file and its imports carry no owner-dialogue rule.
- On Claude Code and Codex, the head's context carries the dialogue rules.
- On Claude Code and Codex, a session that no owner attends carries the unattended layer instead.
- A delegate carries the unattended layer, and no dialogue rule is injected into it fresh. A Codex
  child forked with `fork_turns=all` still inherits the parent's history (M250).
- On Qwen Code, the head keeps the dialogue rules, and delegates get nothing new.

Steps 1, 2 and 5 land in one change. Otherwise a delegate gets contradictory instructions.

1. `bin/sync.json` `always_imported` loses `rules/collaboration.md` and `rules/templates.md`.
   - The head sections of §3 move from `guardrails/_common.md` into `rules/collaboration.md`, with
     their `Runtime check:` lines and their policy ids (`role.declaration`,
     `analysis.before-mutation`).
   - The pointers in `AGENTS.md` and `hooks/README.md` follow them.
2. The session-start hook adds the head layer or the unattended layer on every `source`, following
   D-A49-SELECTOR. A new SubagentStart hook adds the unattended layer on Claude Code and Codex.
   - Both implementations change (ADR 0020).
   - The wiring goes into `bin/sync.json` and `.claude/settings.json`, pinned by
     `meta/tests/test_self_wiring.py`.
   - `role-on-code` and `analysis-guard` get the `agent_id` exemption that the delegation nudge
     already has (C28d), and their messages stop citing moved sections. Today they tell a delegate to
     declare a role and to stop for confirmation, which contradicts `rules/unattended.md`.
3. The fallback line goes into `AGENTS.md` and into the consumer block (`src/akmon/init.json`).
4. The always-loaded count (ADR 0012) reports a number per audience:
   - the attended head;
   - the unattended head;
   - a Claude delegate;
   - a Codex delegate.

   Any change of a cap is an owner decision, as D-CAP and D-A49-HOOKCOUNT were.
5. `rules/collaboration.md` says "the head session" instead of "every agent".
6. Qwen Code gets the head carrier chosen in D-A49-QWEN-CARRIER.

**Refinements**, each returning to the trunk with its condition still met:

- Claude Code: `omitClaudeMd: true` on `k_explorer`, `k_reasoner` and `k_auditor`
  (D-A49-OMIT-NOW (a)), with the floor carried as D-A49-OMIT-CARRIER decides;
- Codex: the `fork_turns` guard, if its probe holds;
- Qwen Code: the hook route for a consumer, and the unattended layer in akmon-written agent bodies;
- the on-demand documents of §3: one owner for analysis before mutation, and a head and an
  unattended reading for each owner step;
- `rules/unattended.md` grows from learning runs over delegate and autonomous sessions.

## 6. Probes

The probes are run (D-A49-PROBES, owner-approved), as rows M246–M255:

- **P1:** Claude, SessionStart `additionalContext` after `/compact` and on `--resume`.
- **P2:** Claude, adherence to the dialogue rules delivered by the hook against the same rules in
  `CLAUDE.md`. Exploratory, 6 runs per arm.
- **P3:** Claude, what `omitClaudeMd: true` drops (instruction files, imports, memory), and whether
  SubagentStart `additionalContext` reaches a subagent.
- **P4:** Codex, SessionStart on `exec` and on resume, SubagentStart, a way to keep `AGENTS.md`
  out of a subagent, and a head-only line with hooks not running.
- **P5:** Qwen Code, context files and imports, what a subagent receives, and hooks.

Results: [`meta/experiments/a49-context-audiences.md`](../../meta/experiments/a49-context-audiences.md).

## 7. Answered

- **D-A49-SELECTOR (a)**, to be watched in practice: a session gets the head layer only when the
  actor is `developer`, the harness's attendance flag is not `0` (M199) and the second-opinion
  marker is not set; any other session gets the unattended layer.
- **D-A49-FLOOR-KEEP (a)**, with the owner's refinement: Plan shape, Route by task kind and the
  owner's consequential choices stay in the floor as one core each, and each audience gets its own
  reading. The floor says what binds everyone (write only on a go-ahead; consequential choices are the
  owner's); `rules/collaboration.md` says how the head asks the owner; `rules/unattended.md` says that
  the brief is the go-ahead and that a consequential choice is reported, not made. Role declaration
  moved to `rules/collaboration.md`.
- **D-A49-OMIT-CARRIER (a):** read-only delegates get the floor from one SubagentStart text.
- **D-A49-QWEN-CARRIER (a)**, as the owner put it: where a harness cannot separate the audiences,
  it gets one version, the developer's, as today. For Qwen Code a generated `QWEN.md` imports the head
  layer, and its subagents see it as they do today (M254). Audiences are separated only where the
  harness can carry it.
- **Codes:** a request for a decision keeps **D-**, and a request for an action takes **G-**, so the
  two cannot be confused (`rules/collaboration.md` § Codes).
- **Harness forks as a rule of the domain** (owner, on D-A49-PROBE-FORK): the logic that forks per
  harness lives in the hooks and adapters, each harness implementing the shared interface through the
  carriers it has. This is a rule for any project that builds agent tooling, so it is the domain
  profile [`agent-harness`](../../profiles/agent-harness.md), suggested by the new archetype
  `agent-tooling`, which akmon declares for itself.

## 8. Open

- **D-A49-PROBE-FORK:** run (M256–M258): a PreToolUse guard on `collaborationspawn_agent` rewrites
  `fork_turns` to `none` through `updatedInput`; it is wired with the trunk's Codex hooks.

Not on the trunk's path:

- `omitClaudeMd` also drops the auto-memory, so a memory note that is a floor rule for this user,
  such as forbidden keywords, no longer reaches those delegates. The local git hooks still catch it
  at commit time.
- The VS Code extension's attendance flag is not measured (M199 and M200 cover `-p` and the
  terminal).
- The raw evidence behind M246–M255 lives in the gitignored ergon (ADR 0023/D07), so the tree alone
  cannot recheck it.
