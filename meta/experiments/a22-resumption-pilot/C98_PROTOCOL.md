# A22 cold-resumption pilot — C98 pair

The owner's instruction to continue A22 authorizes this bounded offline pair.
It compares ordinary discovery with a record-derived pointer on a held-out C98
state. It does not implement C98, make its open design choice, change guidance,
or conduct live owner-facing transfer.

The exact worktree, source hashes, prompts, key, model, reader model and gates
are frozen in [C98_MANIFEST.json](C98_MANIFEST.json). The subject worktree is a
clean detached snapshot; the evaluator key is outside it. The current-practice
arm runs first. Each arm uses a fresh read-only `codex exec` session at medium
reasoning. Delegated mechanical readers must use `gpt-6-luna`. The subject
receives the prompt only; the pointer adds no authority.

The runner retains each attempt's stdout, stderr, final answer and session-tree
rollouts under its own runtime directory. It verifies hashes and clean HEAD
before and after each call. It counts root plus all observed descendants from
persisted rollout token totals, including cached input, and stops before the
second call if the first exceeds 1,200,000 tokens or a child's model differs.
The total pair monitoring gate is 2,500,000 tokens. A running call has no hard
provider cap, so an overshoot is reported as a control failure. There is no
automatic retry or replacement. Any missing transcript, usage or model stops
the pair. Preparation and scorer usage are reported separately where known.

Blind scoring receives the two answer texts and [C98_KEY.md](C98_KEY.md),
labeled X (pointer) and Y (current), without that assignment. Score six items
and critical false closure separately. A single pair cannot establish owner
attention savings, transfer, a population effect, or a new operative rule.
