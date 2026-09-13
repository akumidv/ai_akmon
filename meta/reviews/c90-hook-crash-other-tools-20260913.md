# C90 — a crashing `PreToolUse` hook on the other tools the guard and the nudge match (2026-09-13)

> **Question.** M69 and M70 measured a crashing Claude Code hook on `PreToolUse` for `Bash` only.
> The delegation nudge's matcher also names `Read`, `Edit`, `Write`, `MultiEdit`, `Task`, `Agent`,
> `Grep` and `Glob`. Is a crash fail-open there too?
>
> **Answer.** Yes, on every one of them that exists on Claude Code 2.1.270 — `Read`, `Edit`,
> `Write`, `Agent`. A hook answering with exit 0 and a bare `systemMessage` (the shape of the C87
> guard) shows the owner a notice and the call runs; a hook dying with exit 1 leaves no trace and
> the call runs. `Grep`, `Glob` and `MultiEdit` are no tools on 2.x (C46), and `Agent` is the
> delegation tool.

## Method

- Claude Code 2.1.270, `claude -p "<prompt>" --model haiku --output-format stream-json --verbose
  --allowedTools <tools>`, stdin closed. The prompt goes before `--allowedTools`: that option
  takes several values and swallows a prompt placed after it, and the first attempt started with
  no input at all.
- Throwaway git repositories under `/tmp`, one per leg. Each `.claude/settings.json` wires one
  fixture hook on `PreToolUse`; it writes a marker named after the tool on every call, then
  answers.
- Run 1: matcher `Read|Edit|Write`. The prompt asks to read `a.txt`, then replace `old` with
  `new` in `b.txt`, then quote any text containing the marker word, or answer `NONE`.
- Run 2: matcher `Write|Agent|Task`. The prompt asks to write `c.txt`, then start a
  general-purpose subagent that replies `OK` without tools, then the same quote-or-`NONE`.
- Two legs each: N — exit 0 with a bare `{"systemMessage": …}`; X — exit 1 with a stderr line and
  empty stdout.

## Result (M77)

| Call | N — notice, exit 0 | X — exit 1 |
|---|---|---|
| `Read` (×2) | `system/informational`, `level: notice`: `PreToolUse:Read says: <text>`; the file is read | no record; the file is read |
| `Edit` | `PreToolUse:Edit says: <text>`; `b.txt` becomes `new` | no record; `b.txt` becomes `new` |
| `Write` | `PreToolUse:Write says: <text>`; `c.txt` is created | no record; `c.txt` is created |
| `Agent` | `PreToolUse:Agent says: <text>`; the subagent launches (in the background, under `-p`) and completes | no record; the subagent launches and completes |
| the model | answered `NONE` | answered `NONE` |

The markers show the hook ran on every one of those calls in both legs. With M69 and M70 for
`Bash`, a crash is fail-open on every tool the delegation nudge's matcher names that exists, and
on the commit guard's `Bash` route.

## What this does not show

- akmon's own entry points crashing live. The fixture answers the way the C87 guard does; C87's
  carriers in `meta/tests/test_adapters.py` pin that the entry points answer that way.
- The interactive terminal, as in C87: this reads the `-p` stream.
- The routes' normal effect on 2.1.270. Both rows keep the route version they were measured on,
  2.1.221.
