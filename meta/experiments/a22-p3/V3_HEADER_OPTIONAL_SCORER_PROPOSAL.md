# A22 P3 V3 prospective scorer header handling

**Owner direction:** after M155, accept a narrow prospective repair for a three-column scorer reply that omits only its fixed TSV header. The M155 call and its seal remain terminal. This design authorizes no retrospective score, retry, qualification reading, or B/C comparison.

## Problem and fixed scope

The second identity-bound A cell produced one correlated Qwen response with complete E1–E4 rows but no `element\tverdict\treason` header. The frozen parser correctly stopped. A one-packet Qwen/Codex route pass did not expose this variability. The scorer rubric, blinded packet, sealed packet-ID binding, PASS/FAIL meanings, two independent scorers, same-repeat qualification rule, resource ceilings, and `OBSERVED_NO_RETRY` evidence limit stay fixed.

## Options and decision

1. Keep the exact-header parser and strengthen the prompt. This preserves one representation but another single route pass cannot establish that Qwen always prints the header; prompt-only pressure does not remove the observed failure mode.
2. **Accept either an exact header or headerless complete rows (chosen).** On the first nonempty line, consume the header only when it equals the fixed three-column string. Otherwise treat that line as data. Require exactly one valid row for each sealed E element, no extra row or text, exactly three tab-separated columns, PASS or FAIL, and a nonblank reason. Insert only the fixed header in the parser's normalized representation, then bind the sealed packet ID into the canonical four-column TSV. Record `exact_header` or `inserted_header`, raw bytes and hashes, normalized and canonical bytes and hashes. The parser never supplies or changes an E verdict or reason.
3. Tolerate arbitrary prose, near headers, Markdown fences, partial rows, or inferred values. Rejected: these could change the scorer's judgment or hide an invalid response. Reconsider only with a separately accepted scorer contract and new seal.

Option 2 is deliberately narrower than general TSV repair. A missing exact header is detectable without interpreting the substance; all data-row validation still fails closed. The existing strict parser and sealed source are not edited. The new behavior lives in a separately named parser and operational seal. The new route checks use two different previously observed blinded packets, each with a fresh unscored Qwen and Codex call, so the narrow parser is exercised under both scorer paths on more than one packet. A passing route is mechanics evidence only and cannot be included in qualification.

## Verification and dispatch gates

- Synthetic tests cover exact/headerless replies, preservation of verdicts and reasons, leading blanks, malformed or duplicate headers, missing/duplicate/unknown E rows, wrong columns, invalid verdicts, blank reasons, extra prose, CR, malformed packet IDs, and idempotent canonical validation.
- Freeze the two packet hashes, prompt hash, parser and runner source, four fresh call IDs, model/CLI settings, 636,645-token V3-only Codex opening, 5,000,000 ceiling, 80% five-hour and 90% weekly quota stops, and predecessor failure hashes in a distinct seal. Preflight needs a read-only verified-TLS gateway probe and pinned CLI/auth checks.
- Reserve once and record one terminal completion per call. Store private raw, normalized and canonical evidence; publish metadata-only outcomes. Any resource, model, usage, provenance, tool/retry-marker, format, or transport failure ends the seal without replacement.
- A separate fresh 32-cell schedule and qualification seal would be needed after a passing route. This route approval does not authorize those calls.
