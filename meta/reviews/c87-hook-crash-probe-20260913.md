# C87 — what each harness shows the owner when a hook fails

> **Verdict:** on both harnesses a failing hook is fail-open: the action goes ahead. The
> harnesses differ in what they show.
> - **Codex 0.154.0** reports a hook that exits 1 as `Failed`, on `SessionStart` and on both
>   `PreToolUse` routes.
> - **Claude Code 2.1.270** shows nothing for a hook that exits 1 on `PreToolUse` or
>   `UserPromptSubmit`. A `systemMessage` from a hook that exits 0 reaches the owner as a notice
>   and never reaches the model.
>
> So the guard's channel is the exit code on Codex and `systemMessage` on Claude.
> Rows M69–M71 in [MEASUREMENTS](../MEASUREMENTS.md). Owned by [C87](../TASKS.md); the decision is
> D2-45, amending [ADR 0013](../decisions/0013-hook-survivability-and-crash-posture.md) F3.

## Codex — a hook that exits 1 (0.154.0)

**Method.**
- codex-cli 0.154.0, model `gpt-5.6-luna`. Two throwaway git repositories under `/tmp`: a control
  and a crash repo.
- Each repo's `.codex/hooks.json` carries akmon's generated matchers: `SessionStart`
  `startup|resume|clear|compact` and `PreToolUse` `Bash|apply_patch`. Both events run one stdlib
  fixture.
  - Control: the fixture returns `additionalContext` asking for `CTL_OK`, then writes a marker.
  - Crash: the fixture writes a line to stderr, then its marker, then exits 1.
- Run: `codex --dangerously-bypass-hook-trust -c projects.<repo>.trust_level="trusted" exec -s
  workspace-write -m gpt-5.6-luna "<prompt>" < /dev/null`. The prompt asks for one shell command
  (`touch shell_ran.txt`) and one `apply_patch` file.
- The user's Codex home was only read; no trust entry was written.

**Result (M71).**

| leg | hook status lines | markers | shell file | patch file | reply |
|---|---|---|---|---|---|
| control | `SessionStart Completed`, `PreToolUse Completed` × 2 | SessionStart (`source=startup`), PreToolUse `Bash`, PreToolUse `apply_patch` | yes | yes | `DONE CTL_OK` |
| crash | `SessionStart Failed`, `PreToolUse Failed` × 2 | the same three | yes | yes | `DONE` |

The crash leg's hooks ran (markers), each failed in the output, and both actions landed. This is
M68's result (`UserPromptSubmit`, 0.153.4) on the two events akmon wires on Codex. `codex exec`
itself exited 0.

**Method notes.**
- The first attempt ran without `< /dev/null`. Called from a non-terminal with stdin left open,
  `codex exec` printed `Reading additional input from stdin...` and waited until the 400 s timeout
  ran out, with zero markers. A silence like that measures the probe, not the harness.
- The trust override uses the unquoted dotted key (M25). The repository path therefore must not
  contain a dot, which is why the fixtures live under `/tmp`.

## Claude Code — `systemMessage` and exit 1 (2.1.270)

**Method.**
- Claude Code 2.1.270, `claude -p --model haiku --output-format stream-json --verbose
  --allowedTools Bash`, stdin closed.
- Throwaway git repositories under `/tmp`. Each one's `.claude/settings.json` wires one fixture
  on `SessionStart`, `UserPromptSubmit` and `PreToolUse` (matcher `Bash`). The fixture writes a
  marker in every leg.
- The prompt asks for `touch shell_ran.txt`, then for any text containing the marker word, quoted
  verbatim, or `NONE`.
- Three legs:
  - A: exit 0 with `{"hookSpecificOutput": {"hookEventName": …}, "systemMessage": …}`.
  - B: exit 1 with a stderr line and empty stdout.
  - C: exit 0 with a bare `{"systemMessage": …}`.

**Result (M69, M70).**

| event | A — `systemMessage`, exit 0 | C — bare `systemMessage`, exit 0 | B — exit 1 |
|---|---|---|---|
| `SessionStart` | only inside the hook's `system/hook_response` record (its stdout) | same as A | `hook_response` with `exit_code: 1`, `outcome: error`, the stderr text |
| `UserPromptSubmit` | `system/informational`, `level: notice`: `UserPromptSubmit says: <text>` | same as A | no record at all |
| `PreToolUse` (Bash) | `system/informational`, `level: notice`: `PreToolUse:Bash says: <text>` | same as A | no record at all |
| the tool call | ran | ran | ran |
| the model | answered `NONE` | answered `NONE` | answered `NONE` |

So a `systemMessage` is the owner's channel on `UserPromptSubmit` and `PreToolUse`. Claude Code
presents it as a notice and does not put it into the model's context. The bare form behaves the
same as the one beside `hookSpecificOutput`, so the guard needs no event name to write it. An
exit 1 on those two events is fail-open and leaves no trace in the stream. On `SessionStart` both
answers are only recorded in the hook's response.

**Method notes.**
- The first attempt placed the fixtures in the job directory under `~/.claude/`. There, `touch`
  was refused as a *sensitive file* (`system/permission_denied`), so that run measured Claude
  Code's path protection, not the hooks.
- The same attempt named its directories after the modes. Asked to quote any text with the
  marker, the model quoted its working directory. The repeat used a marker word that appears
  nowhere but in the hook output.

## What this does not show

- **The interactive terminal.** This probe reads the `-p` stream, not what the terminal UI
  renders. The owner still has one short step to run: the leg A settings in an interactive
  session, one prompt and one Bash call, then check whether the notices appear. `SessionStart` is
  the open case: the stream records it only as the hook's response.
- **Codex `UserPromptSubmit` on 0.154.0.** M68 has it on 0.153.4, and akmon wires no Codex
  `UserPromptSubmit`.
- **Ask and deny.** No leg returned a decision, so what a crash does to a pending `ask` or
  `deny` is still C52's F3 gate.
