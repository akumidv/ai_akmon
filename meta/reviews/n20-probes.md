# N20 and N14 live probes — subagent identity, Codex context, hook `ask`

> **Measured evidence, not a design.** Six short model sessions: Claude Code
> 2.1.312 (4) and codex-cli 0.159.2 (2). Rows M189–M193 in [MEASUREMENTS](../MEASUREMENTS.md).
> Owned by N20 (subagent type in a hook payload, Codex PreToolUse context and output contract)
> and N14 (does a hook `ask` reach the owner, per permission mode and actor). Raw jsonl stayed
> in an untracked scratch directory.

## Method

- A throwaway git repository outside any akmon tree, with a project-level hook config only:
  `.claude/settings.json` (Claude) and `.codex/hooks.json` (Codex). Each entry ran one stdlib
  Python script that appended `{event, payload}` (the raw stdin JSON) to a jsonl file and, in the
  decision variants, printed one `PreToolUse` `hookSpecificOutput` object (`permissionDecision:
  "ask"`, or `additionalContext` carrying a nonce token). No user-level settings or Codex config
  were changed.
- Claude: `claude -p --model haiku --max-turns 6 --setting-sources project --output-format
  stream-json --verbose`, stdin `/dev/null`. Session-identity variables of the parent session
  were unset for the child run: `CLAUDECODE`, `CLAUDE_CODE_ENTRYPOINT`, `CLAUDE_CODE_CHILD_SESSION`,
  `CLAUDE_CODE_SESSION_ID`, `CLAUDE_PID`, `CLAUDE_CODE_MESSAGING_SOCKET`,
  `CLAUDE_CODE_MESSAGING_TOKEN`, `CLAUDE_CODE_SESSION_ATTENDED`, `AI_AGENT`,
  `CLAUDE_AGENT_SDK_VERSION`; auth was left as is. The prompt: run `echo probe-main` with Bash,
  then a general-purpose subagent runs `echo probe-child` with Bash, then stop.
- Codex: `codex --dangerously-bypass-hook-trust -c projects."<dir>".trust_level="trusted" exec
  --json -s workspace-write -m gpt-6-luna "<prompt>" </dev/null` (the C85/C87 recipe).
- `claude --help` lists `acceptEdits, auto, bypassPermissions, manual, dontAsk, plan`; the
  literal `default` is not listed but was accepted and reported back as `permission_mode:
  "default"` in the payloads.

## P1 — Claude, `default`, logging only (one session)

Events seen, in order: `SessionStart`, `PreToolUse`/`PostToolUse` Bash (main), `PreToolUse`/
`PostToolUse` Agent, `SubagentStart`, `PreToolUse`/`PostToolUse` Bash (child), `SubagentStop`,
`Stop` (twice: the model's turn ended while the subagent ran, and again after it reported).

| payload | key set (trimmed) | child marker |
|---|---|---|
| main Bash Pre | `cwd effort hook_event_name permission_mode prompt_id session_id tool_input tool_name tool_use_id transcript_path` | none |
| Agent Pre | same keys; `tool_name: "Agent"`, `tool_input` = `description, prompt, subagent_type` (`general-purpose`) | none |
| Agent Post | `+ duration_ms tool_response`; `tool_response` = `isAsync: true, status: async_launched, agentId, description, resolvedModel, prompt, outputFile, …` | `agentId` equals the child's `agent_id` |
| `SubagentStart` | `agent_id agent_type cwd hook_event_name prompt_id session_id transcript_path` | `agent_id`, `agent_type: general-purpose` |
| child Bash Pre/Post | main keys `+ agent_id agent_type` | `agent_id`, `agent_type` |
| `SubagentStop` | `agent_id agent_transcript_path agent_type background_tasks cwd effort hook_event_name last_assistant_message permission_mode prompt_id session_crons session_id stop_hook_active transcript_path` | `agent_id`, `agent_type`, `agent_transcript_path` |
| main `Stop` | `… last_assistant_message stop_hook_active …`, no `agent_id` | none |

- `session_id` is identical in the main chain and in every child payload (M36 holds on 2.1.312);
  `transcript_path` stays the main transcript, and the child's own is `agent_transcript_path`
  on `SubagentStop` only.
- The Agent call ran in the background (`async_launched`); `PostToolUse` Agent fired before
  `SubagentStart`.
- `SessionStart` has no `permission_mode`; `SubagentStart` has none either; `SubagentStop` has it.

## P2 — Claude, `ask` on every `PreToolUse` (three sessions)

The hook script returned `permissionDecision: "ask"` for **every** `PreToolUse`, not only for
Bash. The main-chain Agent call was therefore asked as well, and no subagent was ever started.
**The child-chain Bash cell was not measured** (see Inconclusive).

| mode | payload `permission_mode` | main Bash | main Agent | `-p` exit | stdout |
|---|---|---|---|---|---|
| `acceptEdits` | `acceptEdits` | not run, tool result `probe-ask` (error) | not run, same | 0, no stall, 3 turns | `system/permission_denied` (`decision_reason_type: hook`, `decision_reason: probe-ask`) for each; result `permission_denials` lists both |
| `plan` | `plan` | same | same | 0, no stall | same |
| `auto` | `auto` | same | same | 0, no stall | same |

- `auto` exists in this build. No `PermissionRequest` or `PermissionDenied` hook fired (both were
  wired); no prompt appeared and nothing waited for one.
- The `permission_denials` entry names the Agent tool `Task`, while the hook payload's
  `tool_name` is `Agent`.
- The model read the `ask` as an unexplained refusal ("the tool returned an error containing
  `probe-ask`") and stopped; the reason string is the only text it gets.

## P3 — Codex (two sessions)

Session 1 (`additionalContext` nonce `PROBE_NONCE_7QX2` on every `PreToolUse`; one `spawn_agent`
child running `echo probe-child`): events `SessionStart`, Pre/Post `collaborationspawn_agent`,
Pre `collaborationwait_agent`, `SubagentStart`, Pre/Post Bash (child), `SubagentStop`, Post
`collaborationwait_agent`, `Stop`.

| payload | key set (trimmed) | child marker |
|---|---|---|
| parent Pre/Post spawn | `cwd hook_event_name model permission_mode session_id tool_input tool_name tool_use_id transcript_path turn_id` (`+ tool_response` on Post) | none; `tool_name: collaborationspawn_agent`, `tool_input` = `task_name fork_turns message` (opaque) |
| `SubagentStart` | `agent_id agent_type cwd hook_event_name model permission_mode session_id transcript_path turn_id` | `agent_id` (a thread id of its own), `agent_type: default` |
| child Bash Pre/Post | parent keys `+ agent_id agent_type` | `agent_id`, `agent_type: default` |
| `SubagentStop` | `agent_id agent_transcript_path agent_type … last_assistant_message … stop_hook_active …` | same |
| main `Stop` | no `agent_id` | none |

- Child `session_id` equals the parent's; the child's `transcript_path` is its own rollout file;
  `turn_id` differs between the parent and the child.
- The final reply was `probe-child PROBE_NONCE_7QX2: …`: the nonce from the `PreToolUse` context
  reached the model. Whether the child itself received it is not shown (its only reply was the
  command output).
- `permission_mode` in every Codex payload was `bypassPermissions` in this run.

Session 2 (`permissionDecision: "ask"` on `PreToolUse`, one shell command): the payload arrived
(`tool_name: Bash`, `tool_input.command`), the command ran (`exit_code 0`, output `probe-ask`),
the model reported it, `codex exec` exited 0. No prompt, no block, no stall.

## Inconclusive and not covered

- **Claude child chain under `ask`** (N14's subagent cells): not measured; the Agent call was
  denied first. A new Claude probe with the hook limited to `Bash` is needed.
- **Codex `ask`**: the payload said `bypassPermissions`, so the run may be a no-op because of
  that mode and not because `ask` is unsupported. A run under an approval mode that does prompt
  (a pty, not `exec`) and an `ask` in the child chain were not run.
- **Claude interactive `ask`** (a real terminal where a prompt can appear) is outside `-p`.
- Whether the child in Codex receives `PreToolUse` `additionalContext` of its own tool calls is
  unmeasured.
- Claude `Stop` fired twice only because the Agent ran async; a foreground subagent was not seen.

## N14 follow-up

> Three more Claude Code 2.1.312 `-p` sessions and two pty sessions (rows M194–M197). Same method as above
> (project-only hooks, session-identity variables unset, `--setting-sources project`, `--model
> haiku`, the same throwaway project and hook). The hook gained one decision, `askchild`: it
> returns `permissionDecision: "ask"` only when `tool_name` is `Bash` and the payload has
> `agent_id`; everything else passes. Raw jsonl stayed in the scratch directory.

### Q1 — child Bash under `ask`

| mode | main Bash | Agent call | child `PreToolUse` Bash | child Bash result | `PermissionRequest` / `PermissionDenied` hook | `-p` exit | stall |
|---|---|---|---|---|---|---|---|
| `acceptEdits` | ran | ran (foreground) | fired, `agent_id` set, `permission_mode: acceptEdits` | denied: `system/permission_denied` (`decision_reason_type: hook`, `probe-ask-child`), error result | none | 0 | no |
| `auto` | ran | ran (async) | fired, `permission_mode: auto` | same | none | 0 | no |
| `default` | ran | ran (foreground) | fired, `permission_mode: default` | same | none | 0 | no |

- The child received the reason text as the tool result and reported it as the command output;
  the parent relayed the mismatch as unexplained. No mode produced a prompt, and no mode ran the
  child's command.
- No `PostToolUse` Bash fired for the denied child call. A `PostToolUse` Bash for the main call
  and `SubagentStop` fired as usual.
- The `-p` result of the `auto` run came before the async child finished (`num_turns: 3`, the
  parent said the child was still running); the denial was still recorded in `permission_denials`.

### Q2 — unflagged interactive `permission_mode` (session 4, row M196)

- Setup: `python3 pty.fork()` running `claude --model haiku --setting-sources project "<prompt>"`
  in the throwaway project, session env stripped, logging-only hook (`PROBE_DECISION` empty),
  window 50x160, killed after the `PreToolUse` payload or 90 s.
- **Attempt 1:** blocked by the workspace trust dialog ("Is this a project you created or one you
  trust?", default selection `No, exit`) before any hook fired; killed at 91 s; no payload. Setup
  failure.
- **Attempt 2 (the one allowed retry):** the script sent Down then Enter to pick `Yes, I trust this
  folder` for the throwaway directory (this records trust for that directory only; no dangerous
  flag). Hooks fired: `SessionStart` (`source: startup`, no `permission_mode`), `PreToolUse` Bash
  **`permission_mode: auto`**, `PostToolUse` Bash `auto`, `Stop` `auto`. The screen read
  `auto mode on (shift+tab to cycle)`; the command ran, the session was killed at 15 s.
- Config in play: `~/.claude/settings.json` has no `permissions` key; per the owner, neither the
  akmon `.claude/settings.json` nor `settings.local.json` sets `permissions.defaultMode`; the
  project settings of the probe directory set only hooks. Yet the session started in `auto`.
  So `auto` is the unflagged default in this environment; its source is not identified.
- **Inference (not measured):** the owner's recorded `permissionMode: auto` in interactive
  sessions is explained by this same default, or by the VS Code extension's mode selector.
- Not measured: whether a hook `ask` produces a prompt in an interactive `auto` session (the hook
  here only logged), and any other interactive mode.

### Q3 — interactive `ask` in unflagged (`auto`) mode (session 5, row M197)

Same pty script and trusted directory as Q2, hook decision `askbash` (`ask` for every Bash,
main chain). Events: `SessionStart`, `PreToolUse` Bash (`permission_mode: auto`), `PermissionRequest`
Bash (`auto`; its payload has `tool_name`, `tool_input`, no `permission_suggestions`). The screen
showed a prompt, text: `Bash command · Echo probe string · echo probe-tty-ask` then
`Hook PreToolUse:Bash requires confirmation for this command: probe-ask-bash [settings]`,
`Do you want to proceed?`, `1. Yes`, `2. No`, `Esc to cancel · Tab to amend`. The command had not
run. **Gap:** the script killed the session 12 s after the prompt without answering it, so the
"No" outcome (what the model is told) was not captured; that is a harness-script error, and the
approved budget was one session.

### Which cells can and cannot show a prompt (evidence only; the verdict is the owner's)

- **Cannot** (measured: `ask` is a deny, no prompt, no stall): Claude `-p` main chain in
  `acceptEdits`, `plan`, `auto` (M191); Claude `-p` subagent Bash in `acceptEdits`, `auto`,
  `default` (M194). The subagent chain behaves the same as the main chain, so being a subagent
  adds no prompt path.
- **Can** show a prompt: a Claude **interactive** session in `auto` (the unflagged mode, M196),
  main-chain Bash (M197). The same mode under `-p` denies, so the mode is not what decides it:
  the absence of a terminal is. Other interactive modes and an interactive child-chain `ask` are
  unmeasured; the child under `-p` is a deny (M194).
- Codex `ask` ran the command, under `bypassPermissions` (M193); a prompting Codex mode is
  unmeasured.
- So the `ask` to `deny` escalation is supported only for non-interactive runs (`-p`); for an
  interactive session it would remove a prompt that does appear.


## N14 second follow-up

> Two Claude Code 2.1.312 sessions (one `-p`, one pty; the pty one needed a retry), rows M199–M202.
> Question: can a hook process tell an attended session from an unattended one? M198 had seen
> `CLAUDE_CODE_SESSION_ATTENDED=1` only in the Bash tool env of a VS Code session. Raw jsonl
> and the tty capture stayed in the scratch directory.

### Method

- Same throwaway project as the earlier probes (workspace trust already granted, M196), with its
  `.claude/settings.json` replaced for this probe: one stdlib script wired to `SessionStart`,
  `PreToolUse` (matcher-less, so every tool), `PostToolUse`, `SubagentStart`, `SubagentStop`,
  `Stop`, `PermissionRequest` and `PermissionDenied`. Per call it appended the stdin payload,
  the hook process's environment filtered to keys matching `CLAUDE|AI_AGENT|TERM|CI|TTY`
  (values with `TOKEN|SECRET|KEY|PASS|AUTH|CREDENTIAL` in the key name replaced by
  `<redacted>`), and `isatty` of its stdin/stdout/stderr. Decision: a Bash command containing
  `probe-ask` returned `permissionDecision: "ask"` with reason `probe-ask-no`; anything else, no
  output.
- Both sessions: `--model haiku --setting-sources project`, no `--permission-mode`, and the
  session-identity variables of the parent unset before launch (`CLAUDECODE`,
  `CLAUDE_CODE_ENTRYPOINT`, `CLAUDE_CODE_CHILD_SESSION`, `CLAUDE_CODE_SESSION_ID`, `CLAUDE_PID`,
  `CLAUDE_CODE_MESSAGING_SOCKET`, `CLAUDE_CODE_MESSAGING_TOKEN`, `CLAUDE_CODE_SESSION_ATTENDED`,
  `AI_AGENT`, `CLAUDE_AGENT_SDK_VERSION`). The parent had `CLAUDE_CODE_SESSION_ATTENDED=1`; the
  `-p` hook saw `0`, so what a hook sees is set by the child binary, not inherited.
- Session A: `claude -p --max-turns 8 --output-format stream-json --verbose`, stdin `/dev/null`;
  prompt: Bash `echo probe-p-main`, then an Agent subagent running Bash `echo probe-p-child`. Exit
  0 in 8.6 s; `permission_denials: []`.
- Session B: `python3 pty.fork()` running `claude "<prompt>"`, 50x160 window; prompt: the Agent
  tool runs a subagent that runs `echo probe-tty-child`, then Bash `echo probe-ask-tty` itself.
  The driver waited for the `PermissionRequest` log line and the prompt text on screen, sent Down,
  then Enter (option 2, No), waited for the next `Stop`, saved the tty bytes, sent `/exit` and
  waited for the child to exit (it did, without a kill).
- **Attempt 1 of B failed for a driver error** (setup): it matched `Do you want to proceed` on the
  ANSI-stripped screen, where cursor moves had removed the spaces, so it never answered. The
  prompt stayed up for 2 min 28 s (status line `2m 28s`); at the driver's 150 s timeout the
  `/exit` + Enter it sent were taken by the prompt, Enter chose the default `1. Yes`, and the
  command ran (M202). The one retry fixed the match (whitespace-insensitive) and is the session
  reported below.

### Session A — `-p`, hook process (11 hook calls, all identical in these fields)

| call | chain | `permission_mode` | `agent_id` | `CLAUDE_CODE_SESSION_ATTENDED` | `CLAUDE_CODE_CHILD_SESSION` | `CLAUDE_CODE_ENTRYPOINT` | stdio ttys |
|---|---|---|---|---|---|---|---|
| `SessionStart` | main | (none) | no | `0` | `1` | `sdk-cli` | none |
| `PreToolUse`/`PostToolUse` Bash | main | `default` | no | `0` | `1` | `sdk-cli` | none |
| `PreToolUse`/`PostToolUse` Agent | main | `default` | no | `0` | `1` | `sdk-cli` | none |
| `SubagentStart` | child | (none) | yes | `0` | `1` | `sdk-cli` | none |
| `PreToolUse`/`PostToolUse` Bash | child | `default` | yes | `0` | `1` | `sdk-cli` | none |
| `Stop` (x2), `SubagentStop` | main / child | `default` | no / yes | `0` | `1` | `sdk-cli` | none |

Other env keys the hook saw, both sessions: `AI_AGENT=claude-code_2-1-312_harness`,
`CLAUDECODE=1`, `CLAUDE_CODE_EMIT_STARTUP_TIMING=1`, `CLAUDE_CODE_ENABLE_SDK_FILE_CHECKPOINTING=true`,
`CLAUDE_CODE_ENABLE_TASKS=0`, `CLAUDE_CODE_QUESTION_PREVIEW_FORMAT=markdown`,
`CLAUDE_CODE_STARTUP_FAILURE_RESULTS=1`, `CLAUDE_EFFORT=medium`, `CLAUDE_PROJECT_DIR`,
`CLAUDE_CODE_EXECPATH` (the VS Code extension's native binary), `CLAUDE_CODE_SESSION_ID`,
`CLAUDE_PID`, `CLAUDE_CODE_MESSAGING_SOCKET`, `CLAUDE_CODE_MESSAGING_TOKEN` (redacted), `TERM`
(`xterm-256color`, inherited), `HOSTTYPE`.

### Session B (retry) — interactive pty, hook process

| call | chain | `permission_mode` | `agent_id` | `CLAUDE_CODE_SESSION_ATTENDED` | `CLAUDE_CODE_CHILD_SESSION` | `CLAUDE_CODE_ENTRYPOINT` | stdio ttys |
|---|---|---|---|---|---|---|---|
| `SessionStart` | main | (none) | no | `1` | `1` | `cli` | none |
| `PreToolUse` Agent | main | `auto` | no | `1` | `1` | `cli` | none |
| `PreToolUse` Bash `probe-ask-tty` (hook said `ask`) | main | `auto` | no | `1` | `1` | `cli` | none |
| `PermissionRequest` Bash | main | `auto` | no | `1` | `1` | `cli` | none |
| `PostToolUse` Agent, `SubagentStart` | main / child | `auto` / (none) | no / yes | `1` | `1` | `cli` | none |
| `PreToolUse`/`PostToolUse` Bash `probe-tty-child`, `SubagentHandback` | child | `auto` | yes | `1` | `1` | `cli` | none |
| `SubagentStop` (x2), `Stop` | child / main | `auto` | yes / no | `1` | `1` | `cli` | none |

- Only differences against session A's hook environment: `CLAUDE_CODE_SESSION_ATTENDED` (`0` to
  `1`), `CLAUDE_CODE_ENTRYPOINT` (`sdk-cli` to `cli`), and the per-process ones (pid, session id,
  socket). The interactive `PreToolUse` payload had one extra key, `scratchpad_dir`.
- The subagent was launched async: its `SubagentStart`, child Bash and `SubagentStop` came
  after (or while) the main chain was waiting on the prompt. The child's Bash was not asked
  (it carries no `probe-ask`), so a child-chain interactive `ask` is still unmeasured.
- Order seen: `PreToolUse` Bash, `PermissionRequest` Bash, then (after No) no `PostToolUse` for
  that call, no `PermissionDenied`; `Stop` followed the model's reply.

### What No did (the model's side)

Screen after Down + Enter (ANSI-stripped, trimmed): `Interrupted · What should Claude do
instead?`; the status line stayed `auto mode on`; the model replied within about 3 s.

Session transcript, the denied call's `tool_result` (verbatim):

```text
{"type": "tool_result", "is_error": true, "tool_use_id": "toolu_01Sp4u…",
 "content": "The user doesn't want to proceed with this tool use. The tool use was rejected (eg. if it was a file edit, the new_string was NOT written to the file). STOP what you are doing and wait for the user to tell you how to proceed."}
toolUseResult: "User rejected tool use"
```

followed by a user-role text block `[Request interrupted by user for tool use]`. The model's next
text:

```text
The subagent's Bash run reported `probe-tty-child`, but your rejection stopped my `echo probe-ask-tty` from running, so that probe has no result.
```

The hook's reason `probe-ask-no` does not appear in the tool result or the model's text; it is
shown to the owner on the prompt only (`Hook PreToolUse:Bash requires confirmation for this
command: probe-ask-no [settings]`). In `-p`, by contrast, the reason is the tool result (M191,
M194).

### Not measured

- The hook environment of an extension-hosted (`claude-vscode`) attended session: M198 saw
  `CLAUDE_CODE_SESSION_ATTENDED=1` and `CLAUDE_CODE_ENTRYPOINT=claude-vscode` in the Bash tool
  env there, but the probe's sessions were `claude` run directly, in a stripped environment.
- `-p` variants (`--input-format stream-json`, an SDK permission callback, `-p` under a pty), and
  other entrypoints (`sdk-ts`, `mcp`, remote).
- Interactive modes other than `auto`; an interactive child-chain `ask`; answering Yes.
- Whether `CLAUDE_CODE_SESSION_ATTENDED` can be set `0` in a session where a human is present or
  `1` where none is (the value was set by the binary here, but its derivation is not read).
- Verdict on using the variable is the owner's; the evidence is that it separates the two
  measured cells and that `permission_mode` and `CLAUDE_CODE_CHILD_SESSION` do not.
