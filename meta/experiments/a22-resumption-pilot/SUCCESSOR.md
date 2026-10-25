# A22 A44 pilot — bounded continuation after the first-call ceiling stop

The first package stopped as specified: its current-practice call used 216,859
input and 1,922 output tokens (218,781 total), above the 200,000-token pair
monitoring ceiling. The read-only CLI process that initially failed to
initialize emitted no model transcript or usage; the subsequent successful
call is the only subject reading. Preserve both artifacts. No result was
scored or selected before this continuation was written.

Under the owner's instruction to run the pilot, this distinct continuation
permits only the as-yet-unrun pointer arm. It reuses the exact snapshot, prompts,
model, key, arm order and evaluation rule in `PROTOCOL.md`; it does not retry
the current-practice arm or alter any answer. The cumulative observed ceiling
for the two successful arms is 500,000 Codex tokens including cached input.
There is no additional call if this second call fails or the ceiling is
exceeded. The first result was visible before this continuation, so the pair
is exploratory and cannot support a confirmatory effect claim. An independent
scorer still receives only the two final answers with `X` (pointer) and `Y`
(current) labels before the assignment is revealed.

Before dispatch, recheck the four source hashes and three prompt/key hashes
recorded in `PROTOCOL.md`, clean worktree, and first call's usage. Keep the
pointer call's raw JSONL, final answer and stderr under the same runtime
directory. Do not change A44 or contact the owner as part of the case.
