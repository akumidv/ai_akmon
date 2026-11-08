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
| [`release/release_check.py`](release/release_check.py) | the [`release`](../skills/release/SKILL.md) skill / role | `--state` (collect), `--check` (join the four version carriers, then run the release suite, runner-resilient), `--plan vX.Y.Z` (version bump + owner-run command set). Never commits/tags/pushes. From the npm package, `--subject akmon --check` is refused: akmon's own suite runs on Python. `--subject akmon --state` reads the mounted `<dev root>/akmon`, else the running tree, and is refused when that tree carries no development record: only the akmon git tree does. |
| [`model_routing/init.py`](model_routing/init.py) | the SessionStart routing hook's init instruction (MODEL.md § Capability tiers) | computes the tier→model binding from [`model_routing/registry.json`](model_routing/registry.json) (+ the project overlay `<aitna-root>/model-routing.json`) relative to the orchestrating model; writes the generated `k_*` subagent definitions and `.claude/model-routing.local.json` (both per-user and gitignored — the delegates are pinned to the current session's orchestrator and rewritten when it changes). Idempotent; `--check`/`--dry-run`. |
| [`model_routing/models.py`](model_routing/models.py) | the owner, on request | `--refresh [--provider P] [--dry-run]` writes `<aitna-root>/.local/model-aliases.json` (the concrete id each alias resolves to) from the provider row's declared `catalog`; with no flag it lists what is stored and what a refresh would write. Reads the declared catalog only when invoked; never calls a carrier. The second-opinion runner's `--default-model` (or a `carrier:default` entry) runs the carrier's own model with no pin and no alias resolution, and `carrier:model@effort` adds the reasoning level of a row that declares `efforts`. |
| [`park/park.py`](park/park.py) | the owner, later the `park` skill | `write <id> --name N --goal G --next X [...]` parks a piece of work into its ergon `<dev root>/.ergon/<id>-<name>/`: `PARK.md` (a flat `key: value` header between two `---` lines, with no `state` and no `peers`, the branch and the revisions read from git and the time of the write) and the harness-neutral `RESUME.md`, both written atomically; there is no local index, the ergon is its own record and `list` is the index, so no row goes to `<dev root>/.local/TASKS.md`. `unpark <id>` takes the ergon's lease and prints `RESUME.md` and the capped digest; `digest <id> [--cap N]` prints the digest alone (default 3000 characters, cut at a whole line, overflow named); `list [--plan ID] [--task ID] [--state S] [--closed]` prints one line per ergon and writes nothing; `hold` and `release <id> [--number N]` take and drop the `HOLDER` lease of a unit (the plan in the ergon root, an athlos in `<n>/`), created exclusively, judged stale on read (24 hours, or another machine's lease at once), and taken over from a stale holder only with `--takeover` on the owner's word; `athlos <id> --number N [--step S] [--done]` writes an athlos's own file `ATHLOS.md` from a usable plan line (its id, label, tasks, after, paths, harness, result, zone) and names the plan's shared paths on stderr; `active` names the unit this session is in, read from the worktree folder `.worktrees/<id>-<name>.<n>/`; `close <id>` moves the ergon to `.ergon/.closed/`; `local-id` prints the next free local id `_T<n>`, counted over the live and the closed ergons and never reused; `export <id> --out F` writes the ergon into one bundle file, leases left out. An ergon's and an athlos's state is derived (active, parked, not started, done), never typed. `write` refuses a unit another session holds, a stale lease included (it is taken with `hold --takeover` first, which names the replaced holder's uncommitted paths and keeps it among the note's `sessions`), and the id and name of a closed ergon; `close` refuses an ergon a live session holds and one whose closed folder already exists; `athlos` refuses a plan with no `PLAN.md`, an athlos the plan does not list, and a line with no label or no result. Only the ergon's folder carries a name: an athlos's folder is the number of its id, `<dev root>/.ergon/<id>-<name>/<n>/ATHLOS.md`, with no label and no folder for the plural, and a record written before it — `jobs/<n>-<label>/JOB.md`, the `job:` key of a note, the retired local index — is read and translated, never written. A path inside the session's project root is named from that root; an ergon outside it (a linked worktree, whose ergons stay in the main checkout) is named by its absolute path. Refuses with exit 1 where no project root is found. Stdlib-only; writes no date into a tracked document, never reads a transcript, never pushes. |

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
| `akmon/tools/model_routing/models` | — |
| `akmon/tools/model_routing/second_opinion` | `reviewPrompt`, `unavailableNotice`, `reportPrefix`, `digest`, `reportDirError`, `standardTreeRoot`, `readJsonObject` |
| `akmon/tools/model_routing/stats` | `renderReport`, `renderDigest`, `usageFromMessage`, `aggregateDelegationLines`, `parseDelegationLog`, `aggregateTranscriptLines`, `parseMainTranscript`, `aggregateSubagentLines`, `collectSubagentStats`, `agentTierMap`, `labelAndTier`, `mungedProjectDir`, `transcriptsDir`, `newestJsonl`, `parseUsageResponse`, `readAccessToken`, `fetchUsage`, `budgetSummary`, `TokenUsage`, `DelegationStats`, `TranscriptStats`, `SubagentRecord`, `LimitSummary`, `BudgetSummary`, `SessionRef` |
| `akmon/tools/park/park` | `NOTE_HEADER`, `LEASE_HEADER`, `ParkError`, `parkFields`, `parkBody`, `checkFields`, `checkBody`, `renderHeader`, `parseHeader`, `renderNote`, `parseNote`, `renderResume`, `digestLines`, `readNote`, `digest`, `gitBranch`, `gitRevisions`, `gitUncommittedPaths`, `nowStamp`, `holderIdentified`, `holderSameAs`, `holderLabel`, `leaseAgeSeconds`, `renderLease`, `parseLease`, `readLease`, `leaseIsStale`, `renewLease`, `releaseLease`, `releaseLeases`, `acquireLease`, `rememberHolder`, `readPendingSessions`, `mergeSessions`, `parseAthlosLine`, `parsePlan`, `readPlan`, `sharedPathWarnings`, `athlosDocNextStep`, `renderAthlosDoc`, `parseAthlosDoc`, `readAthlosDoc`, `writeFiles`, `findErgon`, `findClosedErgon`, `athlosFileOf`, `athlosFolder`, `findAthlosFolder`, `moveAthlosFolder`, `athlosIdOf`, `unitState`, `ergonState`, `writeErgon`, `refuseErgonConflict`, `writeAthlosDoc`, `athlosDocFor`, `summarizeErgon`, `summarizeAthlos`, `listErgons`, `formatSummary`, `formatAthlos`, `worktreeUnit`, `activeUnit`, `exportErgon`, `nextLocalId` |
| `akmon/tools/release/release_check` | `checkReleaseVersions`, `runState`, `runCheck`, `runPlan`, `subjects`, `changelogName`, `pyprojectName`, `staticVersionFile` |
| `akmon/tools/tasks/archive` | `parseEntries`, `markDone`, `malformedEntries`, `splitDone`, `insertIntoArchive` |
