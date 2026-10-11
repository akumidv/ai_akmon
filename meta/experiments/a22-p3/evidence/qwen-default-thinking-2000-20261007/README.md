# Qwen default-thinking mechanics canary — 2026-10-07

This archive preserves only a normalized outcome and hashes of the source artifacts. It contains no packet, scorer prompt, request, raw model output, thinking text, TSV reasons, session identifier, request digest, or authentication material.

## Normalized outcome

- Attempt `g84585008`; Qwen Code 0.24.7; requested and reported model key `qwen3.8-27b`; default thinking.
- One provider request and one provider-process invocation; usage reported 12,679 input tokens and 1,363 output tokens; zero tool calls and zero retries; no billing data reported.
- The final TSV had the exact expected header and four complete rows, E1–E4 all `PASS`. The TSV is deliberately not copied because it includes a packet-specific `reason` column.
- A thinking block was present. The startup event advertised tool names; zero observed tool calls therefore does not establish that tools were unavailable.
- The local output setting was 2,000 tokens. The observed output was below it, so output-cap enforcement was not tested. Gateway honoring of the local setting remains unverified.
- Status: mechanics-only `PASS_UNSCORED`; outside P3 score data and qualification. This attempt exceeded the then-approved 3,000-input limit.
- The initial sandbox attempt `g65993412` failed at DNS resolution, with no provider response and zero usage. The subsequent `g84585008` invocation is the one-request run summarized above.

These are mechanics observations only. They do not establish provider-enforced limits, tool unavailability, scorer validity, or dispatch readiness.

## Provenance and source hashes

SHA-256 values below identify original files under `/tmp/akmon-a22-p3-run`. The files remain outside this archive; paths may be temporary. Content-bearing artifacts are hashed for provenance but intentionally not copied.

| Original artifact | SHA-256 | Disposition |
|---|---|---|
| `meta/experiments/a22-p3/exploratory-real-packet-qwen-default-thinking-2000-20261007/qwen/g65993412.md` | `62d46d92f7520f487b3a451638e892d62ab434f218af9b4c65605db872486795` | Excluded; packet-bearing attempt report |
| `meta/experiments/a22-p3/exploratory-real-packet-qwen-default-thinking-2000-after-dns-20261007/qwen/g84585008.md` | `ed8d2ab48589016f534799805726e424ee1274ecb5f6307f270f6b8b64e3181c` | Excluded; includes packet exchange |
| `meta/experiments/a22-p3/exploratory-real-packet-qwen-default-thinking-2000-after-dns-20261007/qwen/artifacts/attempt.json` | `40de40a032e0c549e4f398efddb1eb489086b7fa4d82a1b6414c8980214c86ca` | Excluded; identifiers and request binding omitted |
| `meta/experiments/a22-p3/exploratory-real-packet-qwen-default-thinking-2000-after-dns-20261007/qwen/artifacts/outcome.json` | `13c4a4766c8e7939a3eb9318698bd83f0d4bc8344a825ce88bfe42b0c1c09ec6` | Excluded; session/project identifiers omitted |
| `meta/experiments/a22-p3/exploratory-real-packet-qwen-default-thinking-2000-after-dns-20261007/qwen/artifacts/command.json` | `6d47e43459dbad1b1cb387ba0315e5db766f0a7729723e6300689ba7aaa9705a` | Excluded; raw command metadata omitted |
| `meta/experiments/a22-p3/exploratory-real-packet-qwen-default-thinking-2000-after-dns-20261007/qwen/artifacts/events.json` | `3cfe5a6b962784f87d96ce94127327f5f604f49484ead8a8fb21ecc059e50242` | Excluded; may contain packet/output content |
| `meta/experiments/a22-p3/exploratory-real-packet-qwen-default-thinking-2000-after-dns-20261007/qwen/artifacts/final.tsv` | `e3c4667776cd9c089a6444a40f0e3c14d41551f89277126a384ebd56ba17bea7` | Excluded; packet-specific reason column |
| `meta/experiments/a22-p3/exploratory-real-packet-qwen-default-thinking-2000-after-dns-20261007/qwen/artifacts/stdout.raw` | `54209e9111db90908bda8c5f9ee1f84f22adaaa57bc9a464fab17a44483aaba8` | Excluded; raw model output/thinking may be present |
| `meta/experiments/a22-p3/exploratory-real-packet-qwen-default-thinking-2000-after-dns-20261007/qwen/artifacts/stderr.raw` | `60a24b00d2c8ab71c99f8d42b2204305b300dca99ccc9a5d018a4ad55d39d625` | Excluded; raw process output omitted |

The common credential-marker scan found no matches in the inspected source artifacts. This is not a general proof that every possible secret format was absent; no raw artifact or credential-bearing field was copied. Packet-specific content was present in the reports and output-bearing artifacts, which is why those files are excluded.
