# A22 cold-resumption pilot review — Codex gpt-6-sol

**Status:** exploratory A44 pair completed; resource and routing controls failed.
The answers are useful as a case observation, but this is not a valid bounded
cost comparison or evidence for a new operative rule.

## Method and retained evidence

The owner instructed the pilot to run. The [first-pair protocol](../experiments/a22-resumption-pilot/PROTOCOL.md)
froze one A44 implementation handoff on clean detached HEAD
`f3f5235f3aa4e6a58ed8237fd295597e3df034cd`. Both fresh read-only
`codex-cli 0.162.1` sessions requested `gpt-6-sol` at medium reasoning and
read the same repository snapshot. The only designed difference was the
[record-derived resume point](../experiments/a22-resumption-pilot/PROMPT_POINTER.md)
added to the [ordinary prompt](../experiments/a22-resumption-pilot/PROMPT_CURRENT.md).
The [key](../experiments/a22-resumption-pilot/KEY.md) remained outside the
subject worktree. Source and prompt hashes matched before and after dispatch;
the worktree stayed clean. The CLI rollout metadata confirms the model in all
seven root and child sessions.

The sandboxed first CLI process failed before a model call while initializing
its app-server client (`Read-only file system (os error 30)`). Its stderr was
overwritten by the successful rerun to the same path, so only the observed
error in the operator transcript survives; no JSONL or usage was emitted.
This is an evidence-retention error. The successful root transcripts and final
answers are retained in [runs](../experiments/a22-resumption-pilot/runs/).
The final answers are raw model output and contain absolute links into the
detached worktree; those links depend on that local worktree remaining present.
After the first successful call exceeded the 200,000-token root-only
monitoring ceiling, the [separate continuation](../experiments/a22-resumption-pilot/SUCCESSOR.md)
allowed only the unrun pointer arm under a 500,000-token cumulative ceiling.
The first answer was already visible when this continuation was written.

## Answer reading

An independent `gpt-6-luna` evaluator saw only [answers X and Y](../experiments/a22-resumption-pilot/runs/blind-answers.md)
and the fixed key. Its [instruction and reported ratings](../experiments/a22-resumption-pilot/runs/blind-score.md)
are retained as a copy of its collaboration reply; a full scorer provider
transcript is unavailable. It scored goal, accepted rationale, truthful state, material
limit, next action, and absence of unnecessary owner intake as **6/6 for X and
6/6 for Y**, with no critical false-closure failure. The assignment was then
revealed: X was the pointer answer and Y was current practice.

Both answers correctly say A44 is implemented but still active pending owner
verification; preserve the passing 52 record/cap checks and the full-tree,
build, and JS-test evidence limits; and direct the next handoff toward owner
verification without reopening ADR 0016 D04. See the [current answer](../experiments/a22-resumption-pilot/runs/current-final.md)
and [pointer answer](../experiments/a22-resumption-pilot/runs/pointer-final.md).
No observable recovery failure was corrected by the pointer in this case.
The pair does not measure owner effort, rework, or transfer to a genuine fresh
task. One comparatively easy implementation handoff cannot establish
equivalence or absence of benefit elsewhere.

## Corrected usage and control failure

The root `--json` streams reported 218,781 and 235,770 total tokens, or
454,551 combined. That **omitted five child sessions** created under the
repository's delegation rule. The operator initially treated 454,551 as the
full account; a later audit of each Codex rollout corrected it. `total_tokens`
below is input plus output, with cached input included in input. Session IDs
locate the local CLI rollouts; their SHA-256 values pin the evidence without
copying the large rollout files into this report.

| Arm | Session | Model | Input | Output | Total | Rollout SHA-256 |
| --- | --- | --- | ---: | ---: | ---: | --- |
| Current root | `01a1723c-fa30-71a3-bb2b-f137bc9c936c` | gpt-6-sol | 216,859 | 1,922 | 218,781 | `400bb516db11ee6f2714684916bc439d79f1fece0059d82e72673420432a9d71` |
| Current child | `01a1723d-2049-7371-b39b-b3891cc2b53b` | gpt-6-sol | 252,731 | 1,836 | 254,567 | `e760c25e58c6f76fce20e6ad0d63581015c47f2aecff3c47cfb9ae84f6019c56` |
| Current child | `01a1723d-1856-79c1-8a53-6fa4096e1a0e` | gpt-6-sol | 262,008 | 1,943 | 263,951 | `708d68080ba0c3b5bf30a788b0e2d642793c2b85aa897265c72df784a16f1818` |
| Pointer root | `01a1723e-b386-7683-8470-a06b2363ac1c` | gpt-6-sol | 233,994 | 1,776 | 235,770 | `283e4254a5bb8288852a80ffc796f86d9057e91f02f7ec4cfcb024575e1fe48b` |
| Pointer child | `01a1723e-d029-7f01-9c96-8c382ced8dac` | gpt-6-sol | 196,474 | 1,526 | 198,000 | `94a90a71163159b4350833117b6f29460c92c0a8dcdabe702981487a19bf91f8` |
| Pointer child | `01a1723e-ddac-73a1-9492-306172b084f8` | gpt-6-sol | 187,465 | 1,579 | 189,044 | `4f87fee5af47eae546596a83785bdc0f4d8ba4bdfe3c45ebccaced102052ebb3` |
| Pointer child | `01a1723e-d6bf-79c2-895b-532a082528ad` | gpt-6-sol | 205,287 | 1,632 | 206,919 | `9e73443d8d063313ba8640b4b62a06bca63f8fc41bb335f8783c62f61bc3eb00` |
| **Subject total** | | | **1,554,818** | **12,214** | **1,567,032** | |

Current practice consumed **737,299** observed tokens; the pointer arm
consumed **829,733**. Both the initial 200,000 ceiling and the successor's
500,000 ceiling were exceeded once child usage was included. The subject
agents also routed mechanical file reading to `gpt-6-sol` children, contrary
to the owner's simpler-model instruction. The different child counts (two
versus three) confound any effort comparison. The separate blinded evaluator
and preparation subagents are outside this subject-session sum; their usage
was not captured in the CLI rollout audit, so **full pilot usage is unknown**.
No further subject calls were made after the descendant undercount was
discovered.

## Disposition and next check

Keep the two correct answer traces as exploratory evidence that ordinary
records can support recovery of A44. Do not adopt a standing resume-point
requirement from this pair. Before another pilot call, freeze a new packet
that counts all descendant sessions, routes delegated file reading to a
simple model, has a realistic inclusive stop threshold, and uses a more
discriminating changed-premise or acceptance case. A live owner-facing
transfer check remains separate; A22 stays active and C86 blocked.
