# A22 P3 V2: Codex route-check dispatch result

**Role:** `review` · **Model:** GPT-6 Codex  
**Result:** V2 is blocked before route validation and qualification. One technical `q1461` Codex CLI dispatch failed during local startup; no accepted route check or qualification result exists.

## Acceptance and scope

The owner accepted proposal SHA-256 `89de386b05fbd38e70ed90da75a56c6f3aa584598314afdbb54de859c0f9b8f5` and seal SHA-256 `dfa34f9da5ae18a6038b506170ea83226bbf026902db2951ad457b589499d0c9`, authorizing `route_check` and `qualification`, Codex aggregate limit 5,000,000 tokens, technical attempt `q1461`, policy `OBSERVED_NO_RETRY`, and the owner as session operator. The approval record marks the transcript provenance non-cryptographic; its exact quote and hashes match the owner excerpt. Static preflight passed, with no model dispatch in that preflight.

## Finding — local startup failure leaves V2 unqualified

The run evidence records one technical source attempt, `q1461` (`P3-01`, A, strongest, repeat 1), using Codex CLI `gpt-6-astra`, medium effort. Its single `codex exec --json` dispatch exited 1; stdout is empty, the event stream is empty, and stderr reports failure to initialize the in-process app-server client because of a read-only filesystem. The attempt is closed in the ledger as `failed` / `missing_usage`, with `actual_usage: null` and no usage artifact.

Recorded experiment counts: **0 route-check dispatches**, **0 qualification scorer dispatches/readings**, and **1 technical `q1461` CLI dispatch attempt**. `q1461` was the technical source exchange; it is not a route-check reading or qualification score. This is a statement about the recorded experiment artifacts, not proof that the provider was or was not contacted. Actual usage for the failed dispatch is unknown; the recorded aggregate remains 153,614 prior tokens, but that counter is not evidence that this attempt used zero tokens.

V2 cannot advance: it requires accepted live checks for both scorer routes before qualification, and missing usage fails closed. `OBSERVED_NO_RETRY` records only observable CLI/session evidence and cannot establish hidden provider retries. The Codex aggregate ceiling is observed accounting, not a hard provider cap.

## Independent usage audit

The dispatch window for `q1461` is **19:57:08–19:57:12 UTC**. A separate check of local `rollouts/state_5.sqlite` and `thread_history` found no matching usage record. The installed Codex CLI is **0.156.1**; local inspection found no usage-reporting command. This session uses ChatGPT authentication. OpenAI documents organization Usage as an API endpoint, and its `openai` REST CLI exposes the organization usage command with an admin API key; those references do not document per-call attribution for Codex CLI authenticated through ChatGPT ([Usage API](https://developers.openai.com/api/reference/cli/resources/admin/subresources/organization/subresources/usage), [OpenAI CLI reference](https://developers.openai.com/api/reference/cli)).

Therefore the independent audit does not reconcile `q1461` usage: **usage remains unknown**. The V2 gate remains closed; no zero-usage assumption is supported.

## Conservative V3 paths

1. Resolve the local startup prerequisite and prepare a fresh, hash-bound approval/ledger state that explicitly accounts for the unresolved `q1461` usage; then run only a newly identified, one-shot technical source attempt. Keep qualification blocked until usage is reconciled and both route checks pass.
2. Preserve `q1461` as a failed technical attempt and re-seal a V3 plan that starts with a clean technical source attempt under a confirmed writable runtime. Count any new attempt against the same conservative budget unless accounting evidence supports another treatment.
3. Stop the experiment if usage cannot be reconciled or the local runtime cannot be made suitable; retain the failed attempt and do not interpret it as a route result.

These are recovery paths for owner review, not evidence that a retry has occurred or that V2 is ready to resume.

## Evidence

Sources are the q1461 packet at `/tmp/akmon-a22-p3-v2-20261011/meta/experiments/a22-p3/runs/`:

- `owner-approval-v2.json` — SHA-256 `986dc2d304c505f748624c2f261b92f027bf9d165593f9cad8d08a63420ed0e9`
- `accepted-v2-seal.json` — SHA-256 `dfa34f9da5ae18a6038b506170ea83226bbf026902db2951ad457b589499d0c9`
- `q1461.attempt.json` — SHA-256 `b3413b9122fbb50584321c39541e3156253f148a51cefada5beed9aa4a5c0e2f`
- `q1461.turn1.dispatch.json` — SHA-256 `7cf3ff01d378d1f931b413e8d2800e1d26a3d012ebf9bf493ca57e409d562658`
- `q1461.turn1.events.json` — SHA-256 `37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570`
- `q1461.turn1.stdout.txt` — SHA-256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` (empty)
- `q1461.turn1.stderr.txt` — SHA-256 `eae080369e91b8869ecdd955b8e2a9840b501bc2c8dfb0889bae645cc549d4b5`
- `provider-usage-v2.jsonl` — SHA-256 `5d8c4c0bf4870cb48fc2ab13c65532ad4a36b359651b687991183edeba9af076`
- `static-preflight-20261011T193000Z/evidence.json` — SHA-256 `f054922c6e9d2ba086855b57db2fdb92edf6cf4be8a4e71e5a3e0ed1c38757e0`

The accepted proposal bytes are `RUN_PLAN_V2_PROPOSAL.md`, SHA-256 `89de386b05fbd38e70ed90da75a56c6f3aa584598314afdbb54de859c0f9b8f5`.
