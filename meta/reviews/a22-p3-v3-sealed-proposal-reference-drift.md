# A22 P3 V3 sealed proposal reference drift — Codex GPT-6 review

The owner renumbered local measurement references in main and reported that the six edited V3 proposal files were outside `seal*.json`. A source-and-hash check found that five of those proposals are **directly hash-bound** by earlier seals. The sixth, `V3_SCORER_ID_BINDING_PROPOSAL.md`, was not found as a `proposal_sha256` binding in the available seals. No sealed file was edited in the isolated worktree.

| Main proposal with changed bytes | Earlier seal binding the old bytes |
| --- | --- |
| `V3_HEADER_OPTIONAL_SCORER_PROPOSAL.md` | `v3-header-optional-route-seal-v5.json`, `v3-header-optional-route-seal-v8.json` |
| `V3_ID_BOUND_ROUTE_SUCCESSOR_PROPOSAL.md` | `v3-id-bound-route-successor-seal-v1.json` |
| `V3_QUALIFICATION_HEADER_OPTIONAL_PROPOSAL.md` | `v3-qualification-header-optional-seal-v1.json` |
| `V3_QUALIFICATION_ID_BOUND_PROPOSAL.md` | `v3-qualification-id-bound-seal-v1.json` |
| `V3_QWEN_THINKING_HEADROOM_PROPOSAL.md` | `v3-qualification-headroom-seal-v1.json`, `v3-qwen-thinking-headroom-seal-v1.json` |

For the first row, main SHA-256 is `7253cea321c7535791303390590f8436e998c384208e3911a87d3e8720befa00`, while the sealed worktree bytes and both V5/V8 seals require `9f924100effd1b956ff7a511811e2c40374f505dc17dca29eb0ee3c31b76b836`. Running the second-substitution `status` from main therefore fails in the historical V5 `_v5_terminal_binding` before it reaches the new seal. The same command from `/tmp/a22-p3-v3-qualification-checkout` passes and reports 0/33 new calls with opening charge 1,569,103. A read-only comparison found the V5 route module, root Python source hashes, regression, and runtime path evidence otherwise aligned across the two checkouts.

The current second-substitution packet is valid for execution from the isolated worktree only. The copies in main are review artifacts, not a main-checkout dispatch route. No call was made in this check. To restore reproducibility in main, restore the five old proposal byte streams from the worktree and retain the new M-number mapping in a separate unsealed record; doing so would reverse the owner's recent edits to those five files, so this review leaves them intact. The second-substitution owner decision and default-deny approval remain separate from this repair.
