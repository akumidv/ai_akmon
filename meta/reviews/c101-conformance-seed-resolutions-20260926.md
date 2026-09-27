# C101 evidence — conformance corpus seeded against Python

Task: C101 (design [node-consumers.md §6](../design/node-consumers.md#6-implementation-plan)). Date: 2026-09-26.
Implementation under test: the Python tree at `0.4.0.dev0` (the normative reference while the
corpus is being seeded, per ADR 0020 D01).

## What shipped

- `meta/conformance/` — the corpus: `README.md` (the spec: scenario schema, normalization v1,
  fixture model, gates, seed protocol), `normalize.py`, `corpus.py`, `runner.py`
  (with the `--record` seeding half), `coverage.py` + `coverage.toml` (the population gate),
  `probe.py` + the six shared unit tables under `units/`, and `fixtures/base/`.
- Scenarios: 117 across `hooks/` (36), `cli/` (54), `tools/` (20), `units/` (6) — all pass on the
  Python implementation; the coverage gate reports all 85 population items covered
  (8 commands, 9 hooks, 7 tools, 61 finding codes, 6 unit tables).
- `meta/self_ci.py` — the `selfci.conformance` leg (runner + coverage gate).
- Unit tables pinned from the Python reference, including the quirks a naive port would miss
  (`units/shlex.toml`: `#` is not a comment and a newline outside quotes is a separator;
  `units/record.toml`: the lenient fallback keeps a malformed header line as a `"[broke"` key;
  `units/glob.toml`: `*` crosses `/`; `units/sort.toml`: code-point order; `units/json.toml`:
  the three canonical `json.dumps` forms — hook document, wiring, registry hash).

## Resolutions (ambiguities found while seeding; each is now a scenario or a table row)

1. A missing generated file reports under `sync.stale-generated` ("stale or missing"), not a
   separate code — `cli/sync-stale`.
2. `sync --check` exits 1 on drift but 2 on a plan error (bad JSON in the generated settings,
   unresolved `@`-import) — the plan-vs-drift distinction is pinned by `cli/sync-plan-error`.
3. The once-per-session "unclassified shell route" diagnostic fires on the session's **first**
   Bash call, not only on calls the classifier rejects: `git-commit-guard.py` claims the route
   marker before classification, and a later Bash call is silent (marker claimed). Pinned as-is
   by the git-commit-guard scenarios (first call carries the stderr line, the seeded-marker
   clean-silent call does not). Note: the design's known-issue note
   (`test_adapters.py::test_the_claude_shell_diagnostic_leaves_the_guard_decision_intact`
   failing on the pre-A34 tree) is stale as of this tree — the A22 commit updated that test and
   the full suite is green including it (1669 passed on 2026-09-26).
4. The Codex dispatcher's usage error (missing/bad route) exits 1 with the exception class on
   stderr (`codex_adapter.report_failure`), not exit 2 — `hooks/codex-hook-usage-error`
   (python-tagged: the text names a Python exception class).
5. The delegation-log systemMessage renders the zone without its prefix (`[auth]`, not
   `zone: auth`) — `hooks/delegation-log-append` pins the current spelling.
6. The second-opinion ladder-exhausted notice is five lines, not six —
   `tools/second-opinion-skip` pins the current text.
7. A first package-mode `init` asks the remote for its latest release tag (network); the
   offline, deterministic shape is the realign (a record already exists), which
   `cli/init-package` covers. The network round-trip stays outside the corpus on purpose.
8. `verify`'s isolation check scans the **tree-side** operative USE docs (roles/pipelines/
   guardrails/profiles/skills/tools + ARCHETYPES/BOOTSTRAP/MODEL), not the consumer's
   AGENTS.md — the error side is therefore a `tree_files` scenario
   (`cli/verify-isolation-dev-cite`).
9. `release_check --check` prints the host interpreter path and spawns verify/self-CI —
   unrecordable at the corpus's process boundary; `--state` and `--plan` cover the tool
   (`tools/release-state-package`, `tools/release-plan-package`, `tools/release-plan-bad-version`).
10. The `routing.vendor-present` error text reads "Add a openai object" — recorded verbatim
    (message text is spec; grammar is the implementation's, not the corpus's, to fix).
11. `git` exit 129 leaks into the `check.scope` message text — pinned as-is
    (`cli/check-scope`).

## Known gaps (honest boundaries of the seed, not omissions)

- `second_opinion`'s real run shells out to an external CLI: only the hermetic construction
  and failure paths are in the corpus (`tools/second-opinion-dry-run` pins the constructed
  command; skip and unpinnable are pinned).
- `update`'s package path runs `uv add` (network/package-manager); the offline decision paths
  are covered (`cli/update-missing-record`, `cli/update-subtree-move-refused`,
  `cli/update-subtree-realigned`, `cli/dispatch-skew-notice`).
- `codex.host-trust`'s warn side needs a live Codex; the corpus hides the binary by design, so
  only the absent-install skip is pinned. Live harness probes are N10's job.
- Tree-side registry breaks other than the vendor-present case were not seeded; the mechanism
  (`tree_files`) is in place for them.

## Process notes

- Seeding was record-then-review: `runner.py --record` captures live behavior, the recorded
  text is read as the spec, and the review caught three real corpus-mechanics bugs (the
  token-materialization direction, the launcher-wiring regex consuming the JSON closing quote,
  the multi-key JSON → TOML record emitter) before they could become wrong spec.
- Delegation: the hooks, cli and tools areas were seeded by three parallel agents with
  disjoint write scopes under the record-then-review protocol; the orchestrator owned the
  mechanism, the unit tables, the population, and the gap scenarios.
