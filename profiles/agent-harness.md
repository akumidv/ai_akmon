# Profile: agent harness (domain)

A **domain** profile for a project that builds what AI coding agents run with — rules, hooks, skills,
agent definitions, launchers — for more than one harness (Claude Code, Codex, Qwen Code, …). The
[`agent-tooling`](../ARCHETYPES.md) archetype suggests it.

## One interface, an adapter per harness

- **Every behaviour is stated once, harness-neutral:** what must reach which audience (the session
  the owner attends, a delegate, an autonomous run), what is denied, what is asked. That statement is
  the single owner; no adapter restates it.
- **Each harness implements it through the carriers it has** — the entry file and its imports, a
  session-start or subagent-start hook, agent frontmatter, a tool guard. The fork per harness lives
  in the hook and adapter layer, not in the rules' text.
- **Where a harness lacks a carrier, its adapter takes the nearest one and states the gap:** what is
  weaker, and which measurement shows it. Missing parity is reported, never papered over.

## Carriers are measured, not assumed

- **A carrier is relied on only after a probe on a named version** shows it reaches its audience,
  judged from what the harness recorded — transcripts, rollouts, request logs — not from the model's
  words. The fact is recorded with that version and probed again when the harness moves past it.
- **No capability parity across harnesses is claimed** without a live probe and a regression test
  for the exact payload and enforcement behaviour.

## Context is a budget per audience

- **A rule loads only for the audience that applies it,** and what each audience loads at session
  start is counted, so a rule meant for one audience cannot grow another's context unseen.
