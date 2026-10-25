# A22 cold-resumption pilot — C33 acceptance pair

The owner's instruction to continue the A22 pilot covers this planned offline
acceptance case. It compares ordinary repository discovery with a short
record-derived pointer. It performs no C33 or C128 work, owner verification,
operative change, or live transfer.

The [manifest](C33_MANIFEST.json) freezes the clean detached subject snapshot,
source/prompt/key/runner hashes, models, fresh-arm order and resource gates.
The evaluator key is outside the subject worktree. The same read-only Codex
runner used for C98 verifies hashes before and after each arm, retains separate
attempt artifacts, and counts root plus descendant rollouts. A simple-model
reader requirement and first-arm gate stop the second call if violated.

The first-arm and pair monitoring gates are 1,200,000 and 2,500,000 observed
tokens, including cached input. A call can overshoot while running because
there is no provider-enforced hard cap. No automatic retry or replacement is
permitted. Missing usage, model, transcript or a changed snapshot stops the
pair. Blinded scoring uses X (pointer) and Y (current), with six substantive
items and a separate false-closure check. This one case cannot prove a general
benefit or owner attention saved.
