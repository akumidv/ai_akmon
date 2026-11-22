# A49 — carriers for a starting context split by audience

A results document for probes P1–P5 of task A49 ([design](../../docs/design/context-audiences.md)).
The facts are rows M246–M258 of [MEASUREMENTS](../MEASUREMENTS.md); this note holds what they
answer and what they leave open. Runners, hook scripts, trimmed transcripts and per-run outputs are in
the ergon, `meta/.ergon/A49-startup-context/materials/` (`p1-p3-claude/`, `p2-adherence/`,
`p4-codex/`, `p5-qwen/`, `p6-codex-fork/`).

**Question:** can the owner-dialogue rules reach the head session only, an unattended layer reach
delegates, and the floor reach everyone, on Claude Code, Codex and Qwen Code?

**Harnesses:** Claude Code 2.1.325, codex-cli 0.166.0, Qwen Code 0.27.0; scratch projects, headless
runs, judged from transcripts, rollouts and logged requests rather than from the model's words.

## Answers

| | Claude Code | Codex | Qwen Code |
|---|---|---|---|
| head-only carrier | SessionStart, re-fired on `resume` and `compact` (M246) | SessionStart, re-fired on `resume` (M249); copied into a child forked with `fork_turns=all` (M250) | SessionStart (M255), but project hooks did not load headless (M255) |
| adherence through it | as `CLAUDE.md`, exploratory (M248) | not measured | not measured |
| add to a delegate | SubagentStart (M247) | SubagentStart (M250); a role's `developer_instructions` (M251) | only through `${hook_context}` in the agent's body (M255) |
| withhold the entry file from a delegate | `omitClaudeMd: true` (M247) | impossible (M251) | impossible (M254) |
| `@`-imports | expanded (M81) | never (M40) | expanded (M253) |
| head-only line in the entry file, hooks not running | not measured | model-dependent: followed by a strong head, not by a light one; subagents 0 of 4, weak (M252) | not measured |

## What it means for the design

- **Claude Code can carry the whole split.** The head layer goes by SessionStart on every `source`.
  A delegate with `omitClaudeMd: true` can take the floor and the unattended layer from one
  SubagentStart hook. Whether it does so, or carries a generated charter, is an open owner decision
  in the design.
- **Codex and Qwen Code cannot withhold the entry file from a delegate.** There, whatever the entry
  file holds reaches every subagent, so it holds the floor only; the head layer goes by SessionStart
  and the unattended layer by SubagentStart (Codex) or by `${hook_context}` in akmon-written agent
  bodies (Qwen Code). On Codex a child forked with `fork_turns=all` inherits the head layer with the
  parent's history, so the unattended layer says that inherited owner-dialogue rules are the head's.
- **Qwen Code's hook route for a consumer is open.** Project hooks were refused headless. How a
  consumer's hooks get trusted is not measured: folder trust, stored approvals or system-level
  settings. Today the Qwen head gets the dialogue rules through the expanded imports, so the design
  keeps a Qwen head carrier until that route is measured.

## P6 — steering a Codex spawn away from the parent's history

A PreToolUse hook on `collaborationspawn_agent` sees `fork_turns` (M256) and can rewrite it to
`none` through `updatedInput` with `permissionDecision: "allow"`, carrying the whole received input
(M257). The child then lacks the head layer and keeps its own `AGENTS.md` and SubagentStart text. A
deny with a retry reason works only when the prompt does not say otherwise, and `additionalContext`
comes too late (M258). So the Codex delegate split holds on the default path too.

## Not established

- Claude: automatic compaction, interactive sessions, `--continue`; user-scope `CLAUDE.md` and
  `.claude/rules/` under `omitClaudeMd`.
- Adherence on Codex and Qwen Code; adherence beyond one prompt and n=6.
- Codex: forcing `fork_turns`; the head-only line on other models and phrasings.
- Qwen Code: SessionStart `source` values other than `startup`; hook trust for a consumer project;
  `paths:` rules in a subagent.
