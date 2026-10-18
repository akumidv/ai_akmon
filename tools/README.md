# `tools/` — akmon SHARED executable tools

Cross-project executable tools that ship *with* the standard (the SHARED dev layer, see
[MODEL.md](../MODEL.md)). A **skill calls a tool** ([MODEL.md](../MODEL.md)): the tool
is the executable; the skill is the know-how that drives it.

> **`tools/` vs `bin/`.** [`bin/`](../bin/) holds the stdlib **CLIs the contract depends on**
> and CI runs every push (`sync.py`, `verify.py`). `tools/` holds executables a
> **role/skill drives on demand** — not CI gates. A release is owner-driven, so the release
> tool lives here, not in `bin/`, and is not wired into CI.

> **Propose / prepare, never execute (D5).** An akmon tool defaults to read-only and
> dry-run. It may print commands, validate state, or draft files; owner-owned landing actions
> (commit / tag / push / publish / pin-bump) are run by the owner.

## Tools

| Tool | Driven by | Does |
|---|---|---|
| [`release/release_check.py`](release/release_check.py) | the [`release`](../skills/release/SKILL.md) skill / role | `--state` (collect), `--check` (join the four version carriers, then run the release suite, runner-resilient), `--plan vX.Y.Z` (version bump + owner-run command set). Never commits/tags/pushes. From the npm package, `--subject akmon --check` is refused: akmon's own suite runs on Python. `--subject akmon --state` reads the mounted `<AITNA_ROOT>/akmon`, else the running tree, and is refused when that tree carries no development record: only the akmon git tree does. |
| [`model_routing/init.py`](model_routing/init.py) | the SessionStart routing hook's init instruction (MODEL.md § Capability tiers) | computes the tier→model binding from [`model_routing/registry.json`](model_routing/registry.json) (+ the project overlay `<aitna-root>/model-routing.json`) relative to the orchestrating model; writes the generated `k_*` subagent definitions and `.claude/model-routing.local.json` (both per-user and gitignored — the delegates are pinned to the current session's orchestrator and rewritten when it changes). Idempotent; `--check`/`--dry-run`. |

Run a tool with `akmon tool <path> [args]`, `<path>` being the tool's path under `tools/`
without the suffix (`akmon tool model_routing/init --check`; `npx akmon tool …` in a Node
project). Both implementations take the same command and the same arguments; the
list of tools is `tools` in [`src/akmon/cli.json`](../src/akmon/cli.json). In a mounted project,
which has no installed CLI, run the script itself: `python3 _aitna/akmon/tools/<path>.py`
(stdlib-only; no install step).

## JavaScript module API

The npm package exports every ported tool as an ES module (`exports` in
[`package.json`](../package.json)), so a JS project can build its own dev-layer
tools on them:

```js
import { buildCoverageMap } from "akmon/tools/model_routing/coverage_map";
import { main as archive } from "akmon/tools/tasks/archive";
process.exitCode = archive(["--tasks", "_aitna/TASKS.md"]);
```

The API is each module's named exports, documented in its JSDoc; every module exports
`main(argv)`, which is what `akmon tool` runs and returns the exit code — except `stats`, whose
`main` is async and returns a Promise of the exit code (its budget call is a `fetch`), so a
module-API caller awaits it. The exported surface is public under the release versioning: a
breaking change to it is a breaking release. Nothing else under `js/` (hooks, `common`,
`model_routing/routing`) is importable by specifier, and its shape is not a promise.

| Specifier | Exports besides `main` |
|---|---|
| `akmon/tools/model_routing/coverage_map` | `buildCoverageMap`, `parseZonePlan`, `unlabelledMarker`, `unlabelledPlanError`, `parseInstant`, `parseBound`, `inScope`, `describeScope`, `IsoError` |
| `akmon/tools/model_routing/gate_pack` | `buildFullPack`, `buildPlanCheckPack`, `roleQuestion`, `planCheckQuestion`, `reportDir`, `reportPrefix`, `digest`, `relativeTo` |
| `akmon/tools/model_routing/init` | — |
| `akmon/tools/model_routing/second_opinion` | `reviewPrompt`, `unavailableNotice`, `reportPrefix`, `digest`, `reportDirError`, `standardTreeRoot`, `readJsonObject` |
| `akmon/tools/model_routing/stats` | `renderReport`, `renderDigest`, `usageFromMessage`, `aggregateDelegationLines`, `parseDelegationLog`, `aggregateTranscriptLines`, `parseMainTranscript`, `aggregateSubagentLines`, `collectSubagentStats`, `agentTierMap`, `labelAndTier`, `mungedProjectDir`, `transcriptsDir`, `newestJsonl`, `parseUsageResponse`, `readAccessToken`, `fetchUsage`, `budgetSummary`, `TokenUsage`, `DelegationStats`, `TranscriptStats`, `SubagentRecord`, `LimitSummary`, `BudgetSummary`, `SessionRef` |
| `akmon/tools/release/release_check` | `checkReleaseVersions`, `runState`, `runCheck`, `runPlan`, `subjects`, `changelogName`, `pyprojectName`, `staticVersionFile` |
| `akmon/tools/tasks/archive` | `parseEntries`, `markDone`, `malformedEntries`, `splitDone`, `insertIntoArchive` |
