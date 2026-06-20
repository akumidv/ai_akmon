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

## Wiring (per vendor)

The hook is the source of truth here; each assistant wires it in its own way. **BOOTSTRAP**
does this on attach; **`bin/sync.py`** keeps it wired (ROADMAP O3).

- **Claude Code** — `.claude/settings.json`:
  ```json
  {
    "hooks": {
      "PreToolUse": [
        { "matcher": "Bash",
          "hooks": [{ "type": "command",
            "command": "python3 \"$CLAUDE_PROJECT_DIR/_forge/keystone/hooks/git-commit-guard.py\"" }] }
      ]
    }
  }
  ```
- **Codex / Gemini** — as those assistants expose a pre-execution hook; until then the
  guardrail relies on the AGENTS.md rule + this hook under Claude.

A project may point the wiring at the keystone copy (above) or at a local copy under
`.claude/hooks/` — prefer the keystone path so submodule updates propagate the fix.
