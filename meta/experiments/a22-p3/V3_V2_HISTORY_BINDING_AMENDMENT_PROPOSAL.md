# A22 P3 V3 accepted V2 history binding amendment

**Status: additive source-only verification rule.**

The source-phase preflight verifies the V2 inputs excluded from the V3 accounting ceiling
against the accepted V2 snapshot at `/tmp/akmon-a22-p3-v2-20261011/meta/experiments/a22-p3`.
The binding is the SHA-256 digest of each named file, not the path or directory permissions.
The directory is writable; it is a hash-matching preserved snapshot, not immutable storage.

The verified files are `RUN_PLAN_V2_PROPOSAL.md`, `seal.json`,
`runs/accepted-v2-seal.json`, and `runs/owner-approval-v2.json`. Their expected digests are
recorded in the source verifier, source-only owner approval, and source preflight report. The
accepted seal must bind the exact proposal and historical packet seal; the approval must bind
the same proposal and accepted seal. Current V3 packet bytes are not substituted for the
historical V2 packet seal.

This amendment preserves the original V2 and V3 sealed bytes. It does not change the separate
V3 campaign approval, authorize another phase, or make a provider call. It records hashes and
reproducible path selection; it does not claim that the external snapshot is write-protected.
