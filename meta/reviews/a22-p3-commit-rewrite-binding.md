# A22 P3 commit-rewrite binding — Codex GPT-6 review

The owner requested correction of the two Git commit IDs embedded in the P3 packet after rewriting commit email addresses. Both replacements have the same tree and subject as their predecessors:

| Field | Historical ID | Corrected ID |
| --- | --- | --- |
| `arms/manifest.json.repository_commit` | `b84d19a72894bd4ff296ce7d9414cdf3b49cb414` | `7cb5ee145d853c0fe91710fa69abc8be2b66f70a` |
| `seal.json.git_head` | `1fd9de284526982c87499baa04fae7974196dfa9` | `e94c5aeef400820255ae0853d0349d1439e423e7` |

The old manifest, root seal and SHA256SUMS remain byte-for-byte under `runs/commit-rewrite-predecessor/`. Their SHA-256 values are `ea5c9960c8d355de9e6edc8de07a448c97b8e6db2697376d35809a62416db64c` and `62ace0ce353ce059acd2ee442589d81912ffa61d6442787dc17aebd34728dd93` for the manifest and root seal. The corrected manifest SHA-256 is `4d60d19f8d4a8df26cc6ffd707d49b1abba9661f7486f67b98fc05119ecbc53c`; the root seal's manifest entry and SHA256SUMS entry now match it. The corrected root seal SHA-256 is `5a3739279921b8a3d58372ac66aa81bbe7a7dc02d8c26b00094baed4dc11cfd1`.

Historical controls and qualification seals bind the old manifest or root-seal hashes. They remain historical evidence and were not rewritten or represented as approving the corrected bytes. The isolated A runtime worktree also retains the old inputs for exact replay. A future successor must explicitly bind both the historical chain and this corrected mapping; it must not silently substitute the new root seal for the old seal in past ledgers.

The root `check_bundle.py` still cannot pass on the current checkout: it requires `seal.json.git_head` to equal the current HEAD and hashes every current P3 input, whereas this root seal records the packet's source commit and later files were added. Changing the two Git references does not certify the entire live directory as a new sealed experiment. No provider call was made for this correction.
