# C79 — what skill vendors ask of a SKILL.md, and what reaches their selectors

> **Verdict: every vendor selects a skill by `name` + `description` read from YAML frontmatter
> in the harness's own skills directory, and until C79 no akmon stub carried any.** Claude Code
> listed each generated stub under its bare name (M54), and Codex refused to load one (M55), so
> no description akmon or a consumer wrote reached a selector. The owner's decisions taken on
> this evidence are [D2-41](../D2_LEDGER.md). Owned by [C79](../TASKS.md).

## Sources — vendor documentation only

| Vendor | Reads skills from | Requires | Says about `description` |
|---|---|---|---|
| [Claude Code](https://code.claude.com/docs/en/skills) | `.claude/skills` (and parents), symlinks followed | nothing; `description` recommended, else the first non-empty line | "What the skill does and when to use it… Put the key use case first"; `when_to_use` is appended, both capped together at 1,536 characters |
| [Anthropic authoring guide](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices) | — | `name` ≤ 64, `description` ≤ 1,024 | what it does **and** when to use it, in the third person, with key terms; "Test with all models you plan to use" |
| [Codex](https://learn.chatgpt.com/docs/build-skills) | `.agents/skills` (cwd, repo root, `$HOME`), `/etc/codex/skills`, symlinks followed | `name`, `description` | "concise descriptions with clear scope and boundaries"; "Front-load the key use case and trigger words" |
| Codex `skill-creator` (shipped in codex-cli 0.154.0) | — | `name`, `description` | "what the skill does and when it applies. Include a meaningful boundary…"; procedure goes in the body |
| [Agent Skills standard](https://agentskills.io/specification) | — | `name` ≤ 64 (lowercase, digits, single inner hyphens, equals the directory), `description` ≤ 1,024 | what it does and when to use it; only six top-level keys, anything else under `metadata` ([`skills-ref`](https://github.com/agentskills/agentskills/tree/main/skills-ref) rejects the rest) |
| [GitHub Copilot in VS Code](https://code.visualstudio.com/docs/agent-customization/agent-skills) | `.github/skills`, `.claude/skills`, `.agents/skills` | `name` (equals the directory), `description` ≤ 1,024 | what it does **and** when to use it |
| [Gemini CLI](https://geminicli.com/docs/cli/creating-skills/) | `.gemini/skills` or `.agents/skills` | `name`, `description` | "the keywords that should trigger it" |
| [Cursor](https://cursor.com/docs/skills) | `.agents/skills`, `.cursor/skills`, also `.claude/skills`, `.codex/skills` | `name` (equals the folder), `description` | what it does and when to use it |

No source outside the vendors' own documentation was used.

## Where the sources disagree, and the owner's choice

- **The trigger's home.** Only Claude Code reads `when_to_use`; every other host selects from
  `description` alone (M55: Codex ignores `when_to_use`). Owner: the trigger goes in
  `description`, and `when_to_use` is dropped rather than duplicated.
- **akmon's `owner` key.** The standard admits custom keys only under `metadata`. Owner:
  `metadata.owner`.
- **Result first.** No vendor asks for it; all ask for "what it does, then when". Owner: the
  description states the expected result in prose, then the trigger — "what it does" phrased
  as the result, so the two agree.
- **Model-specific guidance.** Anthropic asks for testing on every model in use rather than a
  per-model text, so there is no separate text per model (gpt-6-astra, Fable).

## Probes

Scratch skills in the job directory, three forms: the source frontmatter copied after a
YAML-comment banner on line 2 (the new stub), no frontmatter (the old stub), and top-level
`when_to_use` + `owner`. Claude Code 2.1.270 was asked, with hooks off and only the `Skill`
tool, to print its skill listing verbatim — in the scratch directory and in alphavar
(read-only: no file there changed). Codex 0.154.0 ran `codex exec --ephemeral -s read-only`
over the same forms under `.agents/skills`, stderr kept.

- Claude, alphavar: all 7 generated stubs listed as `<name>: <name>`. Scratch: the new form
  listed its full description; the old form its bare name; `when_to_use` appended after ` - `;
  a top-level `owner` tolerated (M54).
- Codex: the new form loaded with its description; the old form failed with `ERROR … failed to
  load skill …: missing YAML frontmatter delimited by ---` and was absent from the list;
  top-level `when_to_use` and `owner` tolerated, `when_to_use` not shown (M55).
- Unquoted YAML, three descriptions on both harnesses and through the standard's validator
  (`skills-ref validate`): one containing ` #` was cut at the `#` by Claude Code and Codex alike
  and passed the validator; one containing `: ` loaded in full on both harnesses and failed the
  validator; the double-quoted form passed everywhere (M56, M57).

## Left to review, not to `verify`

`verify` checks the keys, the standard's limits and the two unquoted YAML shapes above
(`skills.frontmatter-yaml`): ` #`, which the harnesses cut without a word, and `: `, which the
standard's validator rejects. Whether a description names its result and its trigger is judged
on review.
