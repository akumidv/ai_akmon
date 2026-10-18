# A22 P3 V3 technical controls: current-CLI successor

**Status:** offline candidate; provider dispatch is default-deny until the owner accepts its exact seal for `technical_controls`.

The first approved controls runner stopped before reserving or starting a provider call because the default `codex` executable had advanced from the frozen 0.156.1 pin to 0.162.1. Its isolated ledger contains only a header, and its first output directory is empty. Preserve that runtime and its seal/approval as evidence; do not reinterpret it as a completed control or retry it.

Run the same three fresh, unscored, two-turn P3-01 technical controls, in the same order and under the same case, arms, model, effort, quota, token ceiling, input caps, `OBSERVED_NO_RETRY`, and stop-operator rules as the [original controls proposal](V3_CONTROLS_PROPOSAL.md). The owner directed use of the installed newer Codex CLI rather than the old 0.156.1 pin. This successor binds the local 0.162.1 executable by its absolute release path and SHA-256. The CLI banner and persisted rollout metadata must identify 0.162.1; any changed event or rollout schema that the frozen checks cannot validate stops the phase terminally. This successor has a new isolated runtime and append-only ledger. The old failed startup consumes no provider-call budget because its ledger has no reservation and no dispatch artifact; its failure remains reported separately.

The successor seal binds the original control seal and approval, the failed startup ledger, the frozen inputs and existing technical evidence, this proposal, the successor runner and regression test. The owner must accept this exact new seal for `technical_controls` only. No qualification, scorer or comparison calls are authorized.
