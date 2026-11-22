# 0033 — The starting context by audience: the head, the delegate, the autonomous run

- **Status:** Accepted for **D01–D06**. The owner answered each code in session under task A49:
  D-A49-AUDIENCE (a), D-A49-UNATTENDED (a) with a file of its own, D-A49-OMIT-NOW (a) with Codex and
  Qwen Code required, D-A49-SELECTOR (a), D-A49-FLOOR-KEEP (a) with a reading per audience,
  D-A49-OMIT-CARRIER (a), D-A49-QWEN-CARRIER (a), and the action codes.
- **Owner:** akuminov@gmail.com
- **Amends:** [0018/D02](0018-release-alignment-and-update-lifecycle.md#d02--attach-sync-and-realign-ownership)
  (what the managed imports region carries); [0012](0012-stage1-contracts-and-vocabulary.md)
  (what the always-loaded count reports).
- **Design and evidence:** [context-audiences](../design/context-audiences.md);
  [a49-context-audiences](../../meta/experiments/a49-context-audiences.md), M246–M258.

## Context

Every session akmon started — the head the owner talks with, each delegate it launches, an
autonomous run nobody attends — loaded one chain of rules: about 38 KB, of which 7–9 KB were the
owner-dialogue rules only the head applies. Delegates echoed them back: in 139 delegate transcripts,
4 carried a `Needed from you` block and 3 a role line. An autonomous run had no rules for working
without an owner: a stop to ask ended it, and a relaunch reloaded the whole context.

## Accepted decision blocks

### D01 — Three layers, each for its audience

`Decision-ID: ADR-0033/D01`

- **Floor**, for every agent: the guardrail's prohibitions, `rules/code.md`, the language profiles
  and the project's entry file.
- **Head**, for the session the owner attends: `rules/collaboration.md` (reply language, codes, the
  closing block, the owner's answers, the role line) and `rules/templates.md`.
- **Unattended**, for a delegate and an autonomous run: `rules/unattended.md`. Its first rule is to
  finish rather than stop to ask, because a relaunch reloads the context. It also holds the report to
  the head and where an autonomous run records a decision for the owner. The file grows from practice,
  through learning runs.

A rule that binds everyone stays in the floor as one core. Each audience then gets its own reading.
Example: the floor says to write only on a go-ahead and that consequential choices are the owner's.
The head asks the owner. An unattended agent takes its brief as the go-ahead and reports a
consequential choice instead of making it.

### D02 — The selector: attended means a developer the harness says is present

`Decision-ID: ADR-0033/D02`

A session gets the head layer only when all three hold:
- the actor is `developer` (0031/D07; a missing actor reads as `developer`);
- the harness's attendance flag is not `0` (M199);
- the second-opinion marker is not set.

Every other session gets the unattended layer. The owner asked to watch this in practice.

### D03 — Carriers per harness; one version where a harness cannot separate

`Decision-ID: ADR-0033/D03`

The session-start hook delivers the head or the unattended layer on every `source` (`startup`,
`resume`, `compact`), because compaction drops a text that was given only at startup (M246). Hook
delivery was followed as well as the same rules in `CLAUDE.md` (M248, exploratory).

| Harness | Head | Delegate |
|---|---|---|
| Claude Code | SessionStart (M39, M246) | `subagent-start` hook (M247) |
| Codex | SessionStart (M249) | `subagent-start` hook (M250); a `spawn-guard` PreToolUse on `collaborationspawn_agent` rewrites `fork_turns` to `none` through `updatedInput`, so a child does not inherit the head's history (M256–M257) |
| Qwen Code | a generated `QWEN.md` imports the head layer | as the head: Qwen cannot keep context from a subagent (M254) |

Where a harness cannot separate the audiences, it gets one version, the developer's, as before. The
audiences are separated only where the harness can carry the split. The entry file's "Who reads
what" line is a fallback for a session whose hook does not run, never the carrier (M252).

### D04 — Hook-delivered rule files are materialized, not imported

`Decision-ID: ADR-0033/D04`

The managed imports region (0018/D02 amendment) now carries the floor's files only:
`guardrails/_common.md` and `rules/code.md`. The head and unattended files are listed as
`hook_delivered` in `bin/sync.json`. `sync` materializes them for the hooks and for `QWEN.md`, and
treats a missing one as a plan error. `subagent-start` and `spawn-guard` are wired by `sync` like
every other hook.

### D05 — The always-loaded count reports each audience

`Decision-ID: ADR-0033/D05`

The always-loaded check reports three numbers:
- the attended head: the chain, plus the session-start ceiling with the head layer;
- the unattended head: the same with the unattended layer;
- a delegate: the chain, plus the SubagentStart text.

The caps did not change and apply to the attended head, the largest. A cap change stays an owner
decision.

### D06 — A request's letter says what is asked

`Decision-ID: ADR-0033/D06`

A request to the owner for a decision is coded **D-**, and one for an action — a go-ahead to write,
commit, run or supply — is coded **G-**. This way the two cannot be confused (`rules/collaboration.md`
§ Codes).

## Rejected alternatives

- **Marking passages as head-only inside the always-loaded files:** the bytes still load into every
  delegate.
- **The entry file's fallback line as the carrier:** a light model ignores it (M252).
- **Holding the split until every harness can carry it:** Qwen keeps one version, and the others
  separate now.

## Reconsider when

- A harness gains a carrier it lacked: Qwen Code project hooks trusted headless, or a way to keep
  context from a subagent; Codex withholding `AGENTS.md`.
- Learning runs show an attended session getting the unattended layer, or the reverse.
- Adherence to hook-delivered rules measurably drops below that of `CLAUDE.md`-delivered ones.

Refinements under the same decisions, in [the design](../design/context-audiences.md) §5:
`omitClaudeMd` on the read-only delegates with the floor in the SubagentStart text, and Qwen Code's
hook route for a consumer.
