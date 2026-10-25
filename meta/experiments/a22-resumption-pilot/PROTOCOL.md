# A22 cold-resumption pilot — first pair

## Authority and scope

The owner twice requested that the pilot run. This first execution is limited to one
offline A44 case and two fresh Codex sessions, one per condition. It does not
perform A44 work, contact the owner on A44, change operative guidance, or run a
live transfer case. The agent selected this narrow scope under that instruction;
the owner has not separately accepted a population claim or a standing rule.

Question: does a compact pointer to existing records improve truthful recovery
of a paused task over ordinary repository discovery? The comparison is a
mechanics and usability screen, not an effect estimate.

## Frozen input

- Detached worktree: `/tmp/akmon-a22-resumption-pilot`, HEAD
  `f3f5235f3aa4e6a58ed8237fd295597e3df034cd`, clean before dispatch.
- Source hashes (SHA-256): `AGENTS.md`
  `09b24f6f191b14d1f438e89b56b09e4e9611c5a40afdf44780609dee6573f525`;
  `meta/TASKS.md`
  `e9b54996a65f707e0e3d3304e5f434b39bb6006e73293779f7363906440487cb`;
  `meta/decisions/0016-decision-records-and-owner-acceptance.md`
  `4dafff4f02477d7b59142a6dba463da504bd3ba589a2f4b41a625cfe03e7dae2`;
  `pipelines/design-flow.md`
  `6409328576627b70b07a0afba17e6bc793c9a5d9e0bf96057c5339b6cda172fc`.
- Subject: `A44`, not used in the prior P3 cases. The two prompt files are
  frozen before dispatch. The evaluator key is kept outside the subject worktree.
- Prompt/key SHA-256: `PROMPT_CURRENT.md`
  `f1b6c47c5e3bd15251affe26c90d4d9ac1c84ad581d549827a53b2fa6f5c4f96`;
  `PROMPT_POINTER.md`
  `a9becf4c7389c97095f77a211575603ecec5f5b8bc99dff9509e9f671486c313`;
  `KEY.md`
  `40c36598f1ca224b3b8d1235371343c637c6db3a198a34441e6c1dbb41ba9219`.
  Recheck these hashes immediately before dispatch and after both calls.
- Model and harness: `codex-cli 0.162.1`, `gpt-6-sol`, medium reasoning,
  `codex exec --json`, fresh session for each arm, read-only sandbox.
- Arm order: current practice, then pointer. The order is a limitation.

## Budget and stop

At most two subject calls; no automatic retry or replacement. Stop after any
transport failure, source drift, unexpected write, lost transcript, or inability
to identify model/session/usage. Observed Codex usage ceiling for this pair:
200,000 tokens total; inspect usage after the first call before starting the
second. This is a monitoring ceiling, not a provider-enforced hard cap. Do not
inherit the P3 five-million-token account. Raw JSONL and final answers remain
under `/tmp/a22-resumption-pilot-runtime/`; report exact usage or unknown.

## Evaluation

Keep the prompts, model metadata, raw events, final answers, sources inspected,
and usage. Give the independent scorer the answer texts only, labeled `X`
(pointer) then `Y` (current), without the assignment. Reveal the assignment
after its item-level ratings are fixed. Check goal/rationale, current state,
material limit, next authorized action, redundant owner intake, and false
completion separately. Report both case-level observations and the limited
comparison. One pair cannot establish transfer, owner attention saved, or a
population effect. The acceptance case and changed-premise control remain for
later prospective work if this first pair is interpretable.
