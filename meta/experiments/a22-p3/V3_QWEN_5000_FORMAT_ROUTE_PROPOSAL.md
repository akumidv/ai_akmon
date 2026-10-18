# A22 P3 V3 Qwen scorer-format route successor

**Scope:** one new, unscored Qwen mechanics call. The owner's direction to continue with the available thinking model authorizes this route only. Qualification, comparison, repair, and retry remain outside scope.

The prior Qwen 5,000-token route reached the model with default thinking and correlated usage, but its final reply prefaced an otherwise parseable TSV. That call is terminal. The problem is a gap between the scoring prompt and the strict first-nonempty-line parser, not evidence that thinking must be disabled. The installed Qwen model has thinking enabled; preserve provider-default thinking.

Two remedies were considered: clarify the final-answer format while retaining the strict parser, or allow the parser to extract a TSV suffix after arbitrary prose. Select the clarification because it states the existing machine-readable acceptance rule before a new call and does not admit arbitrary extra final text. The old reply cannot be retroactively promoted. Reconsider extraction only if a fresh, format-clarified route still fails and an adversarial parser test is accepted beforehand.

Use the unchanged P3-01 blind packet and subject evidence. Preserve the old scoring criteria verbatim; append only an explicit instruction that the **final reply** contains the TSV header and required rows, with no preface, analysis, Markdown fence, or trailing commentary. Private thinking remains allowed and is not parsed as final text. Bind the new prompt, proposal, runner, terminal predecessor, frozen packet, model, CLI, gateway, and 5,000-token/default-thinking configuration to a distinct seal and one-shot private runtime. Apply the unchanged strict TSV validator, correlated usage check, zero-tool and visible-no-retry policy, and 20,000-input/5,000-output observed limits.

The route can establish Qwen mechanics for this packet only. Because the scorer wording changes, a comparable Codex route using the same new prompt must pass before qualification; then prepare a distinct qualification seal, schedule, ledger, preflight, and authorization. No comparison claim follows from a route check.
