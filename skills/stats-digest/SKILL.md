---
name: stats-digest
description: Prints a work-statistics digest to chat — delegations by subagent, tier and model from the routing log, tokens per role from the session transcript, the remaining session and week budget — and writes the full report to .claude/stats/, along with learn-loop proposals that are persisted only after the owner confirms them. Use when the owner asks for work statistics in chat, such as "статистика работы", "session stats", "work statistics", "usage report" or "сколько потратили".
metadata:
  owner: akmon
---

# stats-digest

The on-demand counterpart to the zero-token delegation log: that log is written by a hook
at zero model cost on every delegation, and this skill turns it into an on-request digest.
All *parsing* is code — the
[`tools/model_routing/stats.py`](../../tools/model_routing/stats.py) tool — so it costs no
model tokens; the only model work is the learn-loop pass, which runs **in a subagent**,
never in the orchestrator.

> Token discipline: the **digest** goes to chat; the **full report** goes to a file and
> enters context only on request. Nothing is persisted to `memory/` or drafted as a
> skill/tool without the owner's explicit confirmation.

## Steps

1. **Run the tool** (orchestrator, one cheap call — its stdout *is* the digest):

   ```bash
   python3 _aitna/akmon/tools/model_routing/stats.py
   ```

   It parses the delegation log (`.claude/model-routing.log`) and the current session
   transcript, queries the Claude API for remaining session/week budget (degrades to
   `budget: unavailable` without blocking), writes the full report to
   `.claude/stats/stats-<timestamp>.md`, and prints the digest. The report write is the
   tool's own output file — sanctioned, not a project mutation.

2. **Delegate the learn-loop pass** to `k_explorer` (task kind `summarize`; read-only):
   read the full report and skim the session transcript for learn-loop candidates —
   corrections the owner made, facts worth persisting to `memory/`, repeated mechanics
   worth a tool, know-how worth a skill. It returns a short list of *proposals with
   evidence*, nothing more.

3. **Deliver in chat**: the tool digest (delegations by subagent/tier/model · tokens per
   role · remaining budget · report path) plus the learn-loop proposals.

4. **Gate persistence on the owner.** Recommendations are proposals; write to `memory/`
   or draft a skill/tool only after the owner explicitly confirms, per
   [memory-distill](../../pipelines/memory-distill.md) and guardrails
   ([analysis before mutation](../../guardrails/_common.md#analysis-before-mutation)).

## Flags

- `--transcript PATH` — parse a specific transcript instead of auto-locating the newest
  session for this project.
- `--no-budget` — skip the Claude API budget query (offline / no credentials).
- `--report-dir PATH` — write the report elsewhere (default `.claude/stats/`).
