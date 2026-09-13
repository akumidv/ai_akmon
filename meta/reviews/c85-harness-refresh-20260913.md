# C85 — harness facts on codex-cli 0.153.4 and Claude Code 2.1.266, measured by the owner

> **Verdict: on codex-cli 0.153.4 a Codex child fires `SubagentStart`/`SubagentStop` and takes
> `additionalContext` from `SubagentStart`, so the matrix's "no SubagentStart dispatch" (N2,
> 0.146.0) is stale. A Codex hook that exits 1 is fail-open and shown as `Failed`. The patch and
> shell routes, raw Bash deny, the timeout and per-entry trust behave as the older rows say.**
> The owner ran these probes on 2026-09-09, 2026-09-10 and 2026-09-11, each with disposable
> fixtures outside any repository and a scratch `CODEX_HOME`. They are recorded here as measured,
> not re-run. Rows M58–M68 in [MEASUREMENTS](../MEASUREMENTS.md). Owned by [C85](../TASKS.md).

## A — Codex hook surface, decisions, trust and subagents (0.153.4, 2026-09-09)

**Method.** codex-cli 0.153.4 (`codex --version`), model observed `gpt-6-astra`. `codex exec
--json --sandbox read-only` against a disposable project fixture. A fixture hook recorded its
stdin JSON before returning. Trust was set per leg: ordinary project trust without hook-entry
trust, and `--dangerously-bypass-hook-trust` for the delivery legs. The protocol check used
`codex app-server` `initialize` and `hooks/list`. No source file, repository configuration or
the user's own Codex home was changed.

**Hook envelope.** One Bash call delivered `SessionStart`, `UserPromptSubmit`, `PreToolUse`,
`PostToolUse` and `Stop`. Their payloads carried, in order: the startup `source`; `prompt` and
`turn_id`; `tool_name`, `tool_input.command` and `tool_use_id`; the same tool fields plus
`tool_response`; `last_assistant_message` and `stop_hook_active`. Every payload also carried the
session, turn, model, permission mode, cwd, and a null transcript path in this non-interactive
run.

**Patch route (M58).** One real patch call, with a separate matcher entry per name:

| matcher | fired | observed route |
|---|---|---|
| `Edit` | yes | `tool_name: apply_patch` |
| `Write` | yes | `tool_name: apply_patch` |
| `apply_patch` | yes | `tool_name: apply_patch` |
| `Bash` | no | the shell is a distinct route |
| `exec_command` | no | not a matcher route |
| `.*` | yes | unconditional control |

The patch body was in `tool_input.command`. This is the patch-route half of M30 (0.146.0),
observed again, so `Bash|apply_patch` stays the minimal matcher for the two routes.

**Raw deny (M59).** A fixture `PreToolUse` hook returned the documented Codex deny shape for a
Bash call. Codex reported the action blocked, and the side-effect marker was absent. This is the
vendor route honouring a deny. akmon still wires no Codex deny, so it is not shipped support.

**Timeout (M60).** A `PreToolUse` hook with `timeout: 1` slept five seconds. It recorded entry
but never reached its completion marker, and Codex ran the Bash call, which succeeded. The key
is `timeout`, in seconds. The timeout is a latency bound and fail-open at the tool decision, as
M13/M14 found on 0.149.1.

**Trust (M61).** With a project trust entry but no persisted hook-entry trust, `hooks/list`
discovered the project hooks and reported them `trustStatus: untrusted`. An ordinary `codex
exec` then completed the tool call and delivered zero hook payloads. The same fixture delivered
hooks under `--dangerously-bypass-hook-trust`. This is M19/M20's split, observed again: project
trust makes hooks discoverable, and per-entry trust controls execution.

**Generic subagent lifecycle (M62).** A parent delegated exactly one no-tool task. On the parent
side, the delegation arrived as `PreToolUse.tool_name: collaborationspawn_agent`, with
`task_name`, `fork_turns` and an opaque `message`. The wait arrived as
`PreToolUse`/`PostToolUse.tool_name: collaborationwait_agent`, with `timeout_ms`. Matchers
`Agent`, `spawn_agent` and `Task` did not fire on the delegation. The child emitted both
`SubagentStart` and `SubagentStop`. `SubagentStart` carried `agent_id`, `agent_type: default`,
the parent session id, model, permission mode, cwd and turn id.
`hookSpecificOutput.additionalContext` returned from `SubagentStart` reached the child, which
confirmed the injected marker. `SubagentStop` captured the child's final assistant message. No
named agent definition and no child model pin were part of this launch.

`codex features list` on the same build: `hooks`, `plugins` and `multi_agent` stable and on;
`multi_agent_v2` stable and off; `plugin_hooks` removed; `use_agent_identity` under development.

**Limits.** This leg ran headless only. `ask`, as distinct from a hard deny, was not exercised,
and nothing beyond the generic launch was tested on the subagent route.

## B — Codex MCP registration from a project config (0.153.4, 2026-09-10)

**Method.** codex-cli 0.153.4 (npm `@openai/codex`, the musl x86_64 vendor binary), always
against an isolated `CODEX_HOME`. Three steps:
1. `codex mcp --help` and `codex mcp add --help`, to see what the CLI accepts.
2. `codex mcp add <name> --url …` into the scratch home, to see where the CLI itself writes.
3. A project `.codex/config.toml` with two `[mcp_servers.*]` streamable-HTTP entries and
   tool-policy keys, read back with `codex mcp list` and `codex mcp get <name>` from the project
   directory. This ran first with no trust entry, then with `[projects."<proj>"] trust_level =
   "trusted"` in the scratch home.

**Result (M63).** `codex mcp add <NAME> (--url <URL> | -- <COMMAND>...)` supports streamable
HTTP, with `--bearer-token-env-var` and an OAuth login beside it. It answers *"Added global MCP
server"* and writes `[mcp_servers.<name>]` to `$CODEX_HOME/config.toml`. There is no `--project`
flag. The project file is read only once the repository is trusted. Untrusted, `codex mcp list`
reports `No MCP servers configured yet`: the servers are invisible, with no warning. Trusted,
both servers list as `enabled`. The binary's own help text says the same: *"Project
`.codex/config.toml`: settings for a trusted repository, including sandbox, MCP, hooks, model,
and reasoning defaults."* `codex mcp get` echoed `enabled`, `disabled_tools`, `transport:
streamable_http` and `default_tools_approval_mode: prompt`. `mcp_servers`,
`default_tools_approval_mode`, `disabled_tools`, `required` and `approval_mode` all appear as
literal keys in the binary. `Auth: Unsupported` means a server advertises no OAuth metadata,
not a failure.

**Not measured.** It is unknown whether a per-tool `[mcp_servers.<id>.tools.<tool>] approval_mode
= "approve"` actually auto-approves during a run: `codex mcp get` does not echo it back. What a
run does when a registered server is unreachable is also unmeasured.

## C — Claude Code native plan mode under `-p` (2.1.266, 2026-09-11)

**Method.** Claude Code 2.1.266, headless (`claude -p`), in a throwaway project. Its
`.claude/settings.json` wired one `PreToolUse` hook on matcher `ExitPlanMode` to a script that
appends its stdin payload to a file.

**Result (M64).** Run with `claude -p --permission-mode plan "…present the plan"`, the session
wrote its plan as chat text, called no tool, and said `ExitPlanMode` was unavailable. The
payload file was never created. Asked in the same mode for its tool names, the session listed
neither `ExitPlanMode` nor `EnterPlanMode`. So under `-p`, plan mode reproduces the policy
(propose, don't edit) but not the mechanism. The plan-mode tools exist on this build in an
interactive session's tool inventory, and a headless probe cannot reach them.

**Open.** The interactive leg is still to run: the same one-hook `settings.json`, enter plan
mode, leave it once, and read the payload file.

## D — Codex `SessionStart` / `UserPromptSubmit` delivery, sources and rollout (0.153.4, 2026-09-11)

**Method, headless leg.** A throwaway git repository with a project-local `.codex/hooks.json`.
Both events ran one stdlib capture command, which recorded only the payload key names,
`source`, and whether `transcript_path` existed. It returned an event-matched
`hookSpecificOutput.additionalContext` asking the model to include `PLAN_HOOK_OK`. The run used
`codex --dangerously-bypass-hook-trust … exec` only to isolate delivery from persisted trust.

**Result (M65).** `SessionStart` carried `cwd`, `hook_event_name`, `model`, `permission_mode`,
`session_id`, `source` and `transcript_path`, with `source=startup` and an existing transcript.
`UserPromptSubmit` carried the common keys plus `prompt` and `turn_id`; no matcher was needed.
The model replied `PLAN_HOOK_OK`, so `additionalContext` entered the model request on both
events.

**Interactive leg (M66).** Same build and repository, with the `SessionStart` matcher removed so
that any `source` would arrive. The sequence was: one message, `/compact`, one more message,
exit; then `codex resume --last`, one message, exit; then `/new`, one message, exit. The capture
recorded `startup`, `compact`, `resume`, and `startup` again for `/new`, each with a transcript.
Nothing this build offers produces `clear`. The method matters: the `SessionStart` capture is
written at the first *turn* after a transition, not at the transition itself (14:49:07 for a
process started at 14:48:22). Two earlier attempts that exited right after `/compact` recorded
nothing, which looked like proof that no event is raised. A probe of a session-scoped event must
therefore take a turn after the event.

**Rollout envelope (M67).** The same build's rollout JSONL records the assistant message as
`type=response_item`, with `payload.type=message`, `payload.role=assistant`, and
`payload.content[]` blocks of `type=output_text`. It also writes an `event_msg` copy of the same
message, so a reader must skip that copy or it counts every message twice. Codex documents the
transcript format as unstable.

**Limits.** This measures command hooks, not Codex's native Plan mode. Crash posture was not
probed on these routes here; part E covers `UserPromptSubmit`.

## E — a Codex hook that exits 1 (0.153.4, 2026-09-11)

**Method.** A throwaway git repository, one project-local `.codex/hooks.json` entry on
`UserPromptSubmit`, and two interchangeable hook scripts. The runs were headless (`codex exec`)
with `--dangerously-bypass-hook-trust`, and `-s workspace-write` so the hook could write its
marker.
1. **Control.** A healthy hook returned `additionalContext` asking for `CONTROL_OK`. Codex
   printed `hook: UserPromptSubmit` / `Completed`, and the model replied `CONTROL_OK`. The route
   is live.
2. **Crash.** On the same route, a hook appended `hook ran` to a marker, printed to stderr and
   exited 1. Codex printed `hook: UserPromptSubmit` / **`Failed`**, the marker recorded `hook
   ran`, and the model replied `PROBE_RAN`.

**Result (M68).** Fail-open: the harness observes the failure, says so as a status line, and
does not withhold the prompt. The status is `Completed`/`Failed` per hook; it is a status
channel, not a text one. The generated `statusMessage` did not appear in `exec` output, and
whether an interactive session shows it is unprobed. Owner-addressed prose still has no measured
Codex channel ([design](../design/codex-runtime-contract.md)). `SessionStart` and `PreToolUse`
were not exercised for exit 1. Their fail-open rests on the timeout rows M14 and M60, and a
timeout is a different failure from an exit.

**Method note.** An earlier attempt produced a false negative. Both scripts wrote their marker
*before* printing, under the default read-only sandbox, so the write failed, the process died
before its output, and the control's silence looked like an undelivered route. When a probe's
evidence depends on a side effect the sandbox forbids, it measures the sandbox. Print the output
first and write the marker second.

## What this changes in akmon

- **`CAPABILITIES.md`:**
  - The Codex session-start and delegation-policy rows no longer lean on "no SubagentStart
    dispatch", and they note that nothing on 0.153.4 produces `clear` (M62, M66).
  - The Codex generic-subagent row cites the 0.153.4 launch (M62).
  - The Codex delegation-log row no longer calls the subagent payload unverified (M62).
  - The Codex commit-guard row cites the raw deny again on 0.153.4 (M59).
- **No wiring changes.** akmon still wires no Codex `SubagentStart`, delegation log, deny or MCP
  entry. Those stay design questions (A15, C28(b), C72) that now have a measured route.
- The generated `SessionStart` matcher keeps `clear`: an extra alternative can only match, never
  block, and dropping it would lose the source silently if a later build emits it.
