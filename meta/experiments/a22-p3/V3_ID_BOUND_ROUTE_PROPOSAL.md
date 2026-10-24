# A22 P3 V3 identity-bound scorer route checks

**Scope:** two unscored one-shot mechanics checks, Qwen then Codex, on identical
blind packet and new three-column scorer prompt. This proposal and its offline
seal/preflight do not authorize provider dispatch or qualification.

Use the saved packet from the terminal qualification successor only as a
mechanics fixture. Its original failed scorer reply stays failed and cannot be
reclassified. The new Qwen and Codex calls each produce a raw three-column TSV;
the runner binds the sealed packet ID to a separate canonical four-column TSV
and validates E1–E4 without changing verdicts or reasons. Both raw and
canonical bytes, usage, session, request, packet, prompt, model and settings
are retained as private evidence. A route pass is a format/mechanics result,
not a qualification reading.

Qwen remains `qwen3.8-27b` on CLI 0.24.7 with default thinking,
`maxRetries: 0`, 20,000 observed input and a 5,000-token local output setting.
Codex remains `gpt-6-astra` medium on CLI 0.162.1 with 20,000 observed input
and 1,000 observed output. Each Codex call requires fresh interpretable
subscription quota below 80% five-hour and 90% weekly use. The V3-only Codex
opening is 559,835 of 5,000,000; V2's known 153,614 and unresolved q1461
stay separately reported. The owner of this chat is the stop operator.

One reservation and one terminal completion are recorded per call. Missing or
uncorrelated usage, malformed TSV, model/version drift, tool/retry marker or
resource stop terminates this seal. There is no automatic retry, repair or
replacement. `OBSERVED_NO_RETRY` is limited to CLI-visible evidence. Raw
runtime remains private outside the repository. A new qualification seal,
preflight and separate owner acceptance are required after both routes pass.
