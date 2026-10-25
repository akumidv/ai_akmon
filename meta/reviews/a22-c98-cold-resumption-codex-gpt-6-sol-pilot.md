# A22 C98 cold-resumption review — Codex gpt-6-sol

**Result:** the changed-evidence-premise pair completed within its monitoring
gates. Both answers scored 6/6 after a blind rubric clarification; the pointer
corrected no observed recovery failure. This is a case observation, not a
population result or an operative rule.

## Method and evidence

The [C98 protocol](../experiments/a22-resumption-pilot/C98_PROTOCOL.md) and
[manifest](../experiments/a22-resumption-pilot/C98_MANIFEST.json) froze the clean
detached snapshot, six source hashes, two prompts, evaluator key, runner hash,
models and gates before dispatch. The ordinary arm ran first, then the pointer
arm. Both were read-only `codex-cli 0.162.1` calls with `gpt-6-sol` at medium
reasoning; mechanical readers used `gpt-6-luna`. The subject worktree remained
clean and source hashes matched after each call. The key stayed outside it.

The [current answer](../experiments/a22-resumption-pilot/runs/c98-current-final.md)
and [pointer answer](../experiments/a22-resumption-pilot/runs/c98-pointer-final.md)
both recovered C98's active status, settled Unicode/language changes, open
trigger designs, pre-clause evidence limit and next replay. Neither chose a
trigger or asked the owner to repeat the settled language choice. A blinded
`gpt-6-luna` evaluator first scored pointer X 5/6 and current Y 6/6, marking
X down solely for omitting the count of 18 sessions. On a wording-versus-
substance clarification under the frozen key, it corrected X to 6/6: X had
preserved the 1,139-turn zero-hold result and its non-transfer to post-clause
turns. The [score record](../experiments/a22-resumption-pilot/runs/c98-blind-score.md)
preserves this correction. No critical false closure appeared.

## Session-tree account

The automated runner retained stdout, stderr, answer and each rollout in
`/tmp/a22-resumption-c98-runtime/`, with separate directories per arm and no
retry. Its result file has SHA-256
`fc2d97d00fd8dbc6953dce4937ad1d20ba92638f633617c1769c4d344e11d185`.
An independent mechanical audit matched all seven archived rollout hashes,
session IDs, parents, models and last cumulative token totals to that result.

| Arm | Root | Readers | Root tokens | Reader tokens | Total |
| --- | --- | ---: | ---: | ---: | ---: |
| Current | gpt-6-sol | 2 × gpt-6-luna | 317,836 | 398,223 | 716,059 |
| Pointer | gpt-6-sol | 3 × gpt-6-luna | 346,167 | 1,115,159 | 1,461,326 |
| **Both** | | **5** | **664,003** | **1,513,382** | **2,177,385** |

The first-arm 1,200,000 and pair 2,500,000 monitoring gates held. They are
not provider-enforced limits during a call. Different reader counts and paths
prevent attributing the large token difference to the pointer. Preparation
and scorer usage were outside this subject-session ledger and remain unknown.
The full scorer provider transcript is unavailable. The raw answers contain
absolute links to the detached worktree; those links rely on its local path.

## Disposition

This is the second offline case where current practice recovered the material
state and the pointer added no observed recovery benefit. A44's first pair had
failed resource and model-routing controls; C98 corrects those controls but
still has only one case and unequal delegated work. Neither case measures
owner attention or real transfer. Keep A22 active; do not add a standing resume
point from these pairs. Complete the planned acceptance case before an owner
disposition of the pilot, using the automated descendant-inclusive gate.
