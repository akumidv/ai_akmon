# A22 P3 V3 Qwen 5,000-token route successor after network stop

**Status: offline successor candidate; one new provider call only after its
separate seal and preflight are bound to the owner's instruction.**

The preceding one-shot Qwen route emitted a CLI DNS error for the configured
gateway before a model response. Its raw event reported zero API duration and
zero tokens, but no correlated usage record was written. Treat that Qwen usage
as unknown, retain its reservation, stdout, stderr and terminal outcome, and
never reuse its runtime or call ID. This successor is a distinct mechanics
attempt prompted by the observed network failure, not a repair of that call
or a qualification scorer reading.

Use the same frozen P3-01 blind packet, scoring prompt, model, CLI version,
default-thinking configuration, `maxRetries: 0`, zero tool allowance and
5,000-token output setting as the preceding attempt. Keep the existing
first-nonempty-line TSV rule and 20,000 observed input limit. The route must
run where the configured gateway can be resolved; verify DNS reachability
before dispatch. A separate private runtime and one-shot gate ensure that a
failed process remains terminal. Bind the previous route seal, approval,
preflight, reservation, raw event and outcome by exact hashes in the new seal.
The new route remains unscored. It can establish mechanics only; its success
cannot prove the 5,000-token setting will suffice for every case.

The previous qualification failure and charged V3 Codex use of 273,286 of
5,000,000 tokens remain unchanged. No Codex call is part of this route. A
successful route allows preparation of a fresh qualification package with new
IDs, ledger and separate authorization. A failed route is terminal; no
automatic retry, qualification, comparison or repair is authorized here.
