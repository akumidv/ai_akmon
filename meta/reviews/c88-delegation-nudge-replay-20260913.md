# C88 — the delegation nudge replayed over recorded sessions (2026-09-13)

> **Question.** Does the delegation nudge as D2-8 set it — every edit, shell or read call counts
> 1, an advisory at 10, a hard ask at 20, which D2-10 turns into a deny outside the interactive
> default mode — measure a failure to delegate, or the length of a session? What would a weighted
> rule do on the same sessions?
>
> **Answer.** On akmon's own sessions it fires in almost every session: 10 of 11 reach both the
> advisory and the ask, and 16 of its 17 asks would be denies, 3 of them on a read. The rule
> chosen for C88 — a read ½, the first 8 calls of a stretch free, 30/120, no ask on a read —
> fires the advisory in 10 of 11 and the ask in 7 of 11, and never denies a `Read`. The weights
> matter less than expected: above a score of 30 every weighting tried reaches the same
> sessions, because those sessions ran for hundreds of calls without a delegation.

## Corpus

- **Claude Code.** Every transcript in the local Claude Code store for the akmon project,
  snapshot 2026-09-13T18:57:32Z (the current session included, cut at the snapshot). Main
  chain only (`isSidechain` false); subagent transcripts are separate files and are not read,
  as the nudge exempts subagent calls (C28d). 11 sessions with at least one tool call; Claude
  Code 2.1.210–2.1.269; 2026-07-15 to 2026-09-13.
- **Tool kinds** as `hooks/claude_adapter.py` and `hooks/delegation-nudge.py` map them:
  `Read`/`Grep`/`Glob` read, `Edit`/`Write`/`MultiEdit` edit, `Bash` shell, `Task`/`Agent`
  subagent; any other tool is not counted. `Grep` and `Glob` never occur (C46).
- **Permission mode**: the last `permissionMode` recorded before the call. Of the 5 651 counted
  calls, 4 076 ran in `auto`, 1 486 in `acceptEdits`, 24 in `plan` and 65 in `default`.
- **The nudge is not wired in akmon's own repo** (there is no `.claude/settings.json`), so none
  of these sessions ever saw it. The replay says what it would have done, not how the agent
  would have reacted.
- **Codex CLI.** The 8 parent rollouts with cwd akmon and `source: cli` (child rollouts, whose
  `source` is a subagent spawn, excluded); 7 have tool calls; codex-cli 0.144.4–0.154.0. Every
  tool call is `exec`, with the command inside it, so a kind-only replay sees shell only;
  `spawn_agent` is the delegation.

## Method

The replay walks each session's calls in order through the nudge's state machine: a drift score
and a call count since the last delegation; the advisory once per stretch when the score reaches
the advisory threshold; the ask once per stretch at the ask threshold; a delegation resets both
and re-arms both markers. An ask in a mode other than `default` counts as the deny D2-10 makes of
it. "On a read" means the call carrying it was a `Read`, or a shell command the look-only
classifier below passes.

| Rule | Weights | Grace | Advisory / ask |
|---|---|---|---|
| D2-8 | every call 1 | 0 | 10 / 20 |
| kind-only (chosen) | read ½, edit 1, shell 1 | 8 | 30 / 120, no ask on `Read` |
| with a classifier | as kind-only, plus ½ for a shell command whose every `&&`/`\|\|`/`;`/`\|` segment starts with a read-only command, and 0 for a call on akmon's own tooling (a path under `.claude/`, the mounted or installed akmon, an `akmon` CLI call) | 8 | 30 / 120, no ask on a read |

## Results

### Claude Code (M72)

| Rule | Advisory | Ask | Denies | Of them on a read |
|---|---|---|---|---|
| D2-8 | 10 of 11 | 10 of 11 | 16 of 17 asks | 3 |
| kind-only (chosen) | 10 of 11 | 7 of 11 | 9 | 1 (a read-only shell command) |
| with a classifier | 7 of 11 | 7 of 11 | 9 | 0 |

**Check against the shipped code.** The snapshot replayed through
`hooks/hook_core.py::delegation_nudge_result` itself — at its defaults, with each call's recorded
permission mode — gives the chosen rule's row: advisory 10 of 11, ask 7 of 11, 9 denies, none on
a `Read`, one on a read-only shell command.

### Where the thresholds bite (M73)

| Sessions reaching a score of | 10 | 20 | 30 | 50 | 80 | 120 | 160 | 240 | 400 |
|---|---|---|---|---|---|---|---|---|---|
| every call 1 | 10 | 10 | 10 | 7 | 7 | 7 | 6 | 6 | 4 |
| kind-only, grace 8 | 10 | 10 | 10 | 7 | 7 | 7 | 6 | 5 | 4 |
| with a classifier | 10 | 10 | 7 | 7 | 7 | 7 | 6 | 4 | 4 |

Only 5 of the 11 sessions delegated at all, after 0, 73, 89, 249 and 679 calls. The median
longest undelegated stretch is 249 calls; the longest is 1 225.

### The look-only classifier (M74)

704 of the 4 266 shell calls pass it. A scan of those 704 for write forms — a redirect other than
to `/dev/null`, `-delete`, `-exec`, `env <command>`, `git config <key> <value>`, `git branch -d`,
`git tag -d`, `git remote add|remove|set-url`, `sed -n … w` — finds one real write,
`git remote set-url … && git remote -v`, passed because `git remote` is on the read-only list,
and two `find … -exec sh -c …` that only read here but could run anything. C28(c) had ruled out
classifying the command text for this reason; on this corpus the classifier would have saved one
deny.

### Codex CLI (M76)

| Rule | Advisory | Ask |
|---|---|---|
| D2-8 | 7 of 7 | 7 of 7 |
| kind-only | 4 of 7 | 2 of 7 |

Codex sessions delegate early — every one within its first 3 calls, 75 delegations in all — and
the median longest undelegated stretch is 44 calls (the longest 232). The nudge is not wired for
Codex (C72).

## An earlier replay on another corpus (M75, owner)

The owner replayed 37 recent sessions of projects wired with the same hooks — 5 396 counted
calls — through the D2-8 rule: the advisory fired in 37 of 37 sessions and the ask in 33 of 37,
and in an unattended mode the ask denied ordinary read-only calls (an onboarding session was
blocked mid-`curl` while reading a ticket). The rule with a classifier fired the advisory in 35 %
of sessions and the ask in 11 %. The median session took 21 calls before its first delegation;
the longest undelegated stretch was 1 582 calls.

The two corpora agree on the D2-8 rule and differ on the weighted one: 35 % / 11 % there, 7 of 11
here. That corpus came from projects attaching and using the hooks, where the owner found about
half of a fresh attach's opening stretch spent on setting up the tooling; akmon's is long
development sessions that rarely delegate.

## What this does not show

- How the agent reacts to the nudge. The nudge never ran in these sessions; a nudged agent may
  delegate sooner and shorten the stretches the replay counts.
- A consumer project. akmon's corpus is its own development; alphavar, the wired consumer, has no
  main-chain tool calls in the local store.
- Statistical weight: 11 Claude sessions and 7 Codex sessions.
- That 30/120 is optimal. The sweep shows where the thresholds bite on this corpus; the choice is
  the owner's (D2-46).
