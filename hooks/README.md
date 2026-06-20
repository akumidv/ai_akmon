# hooks — portable enforcement of keystone guardrails

Vendor-neutral hook scripts that **enforce** a keystone guardrail at the moment it matters,
so the rule survives a long session (it does not depend on the guardrail doc staying in
context). Stdlib-only, no project imports — they run unchanged in any repo.

> A hook is the *executable* side of a guardrail. The rule lives in
> [`../guardrails/`](../guardrails/); the hook makes it bite.

## Hooks

- [`git-commit-guard.py`](git-commit-guard.py) — enforces
  [`../guardrails/_common.md`](../guardrails/_common.md) "Commits & ownership": denies an AI
  `Co-Authored-By` trailer; asks the owner before `push`/`tag`/`merge` and before a `commit`
  on the default branch (landing history). Runs as a **PreToolUse → Bash** hook.
- [`session-start-agent.py`](session-start-agent.py) — the executable side of the
  [`../roles/README.md`](../roles/README.md) "Role declaration" convention: injects a
  reminder to declare the active agent (and restate it on switch) plus the project's
  **scanned** agent roster (`_forge/agents/` dev + root `agents/` desk), and the "read
  `_forge/memory/` at session start" rule. Runs as a **SessionStart** hook.

> The Role-declaration **rule** also lives in `AGENTS.md` (vendor-neutral), so Codex/Gemini
> follow it by reading the doc; this hook is only the Claude-side *enforcement* of it.

## Wiring (per vendor)

The hooks are the source of truth here; each assistant wires them in its own way.
**BOOTSTRAP** does this on attach; **`bin/sync.py`** keeps it wired (ROADMAP O3).

- **Claude Code** — `.claude/settings.json`:
  ```json
  {
    "hooks": {
      "PreToolUse": [
        { "matcher": "Bash",
          "hooks": [{ "type": "command",
            "command": "python3 \"$CLAUDE_PROJECT_DIR/_forge/keystone/hooks/git-commit-guard.py\"" }] }
      ],
      "SessionStart": [
        { "hooks": [{ "type": "command",
            "command": "python3 \"$CLAUDE_PROJECT_DIR/_forge/keystone/hooks/session-start-agent.py\"" }] }
      ]
    }
  }
  ```
- **Codex / Gemini** — they read `AGENTS.md`, so the rules carried there (commit ownership,
  role declaration) apply by convention. Where an assistant exposes pre-execution /
  session hooks, wire these scripts the same way; until then the AGENTS.md rules stand on
  their own (the Claude hooks add enforcement on top).

A project may point the wiring at the keystone copy (above) or at a local copy under
`.claude/hooks/` — prefer the keystone path so submodule updates propagate the fix.
