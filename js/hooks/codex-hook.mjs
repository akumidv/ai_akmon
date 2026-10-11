#!/usr/bin/env node
/**
 * Codex command-hook entrypoint for akmon guardrail reminders — the JavaScript twin of
 * `hooks/codex-hook.py` (C104, ADR 0020 D01). The Python module is the spec: the same answers,
 * the same texts, the same exit code and the same stdout and stderr.
 *
 * Usage from `.codex/hooks.json` (`_aitna` is the default dev-layer root; a project that sets
 * `AITNA_ROOT` gets the matching path written by `sync.py`):
 *
 *     node "$(git rev-parse --show-toplevel)/_aitna/akmon/js/hooks/codex-hook.mjs" analysis-guard
 *
 * The guardrail decisions live in `hook_core.mjs`. This wrapper only maps Codex hook payloads
 * into those neutral functions and prints plain-text reminders for Codex to ingest.
 *
 * Data (the C104 convention): `main` reads nothing itself; `lazyHookData()` hands each shared
 * file over on first access, so a broken data file fails only the routes that reach it. The
 * functions that read a data file or a marker take the bundle as `data`.
 *
 * Twin notes:
 * - the Python parses its one positional argument with `argparse`; the contract ported here is
 *   "exactly one route from `codex_hook.json`", optionally beside one `--` (`analysis-guard`,
 *   `-- analysis-guard`, `analysis-guard --`: the three forms argparse accepts). Anything else —
 *   a missing, extra, unknown or option-looking argument — is a `UsageError`, the crash line
 *   `akmon codex-hook hook: UsageError` and exit 1. **Documented divergence:** `-h`, `--help` and
 *   the abbreviations of `--help` print the usage block and exit 0 under `argparse`; here they
 *   print nothing and are a `UsageError`, because a hook has no reader for a usage block;
 * - a route that crashes names `codex-hook <route>`, a bad argument only `codex-hook` (the route
 *   was never read), as the Python's `hook` variable does.
 */

import fs from "node:fs";
import { fileURLToPath } from "node:url";

import { claimDiagnosticMarker, markerKind, unidentifiedIdentity } from "../common/markers.mjs";
import { dictItem, pyIterate, pyPath } from "../common/pyvalue.mjs";
import { fill } from "../common/jsondata.mjs";
import {
  command, cwd, filePaths, loadPayload, payloadShape, printResult, reportFailure, sessionId, toolKind, toolName,
  toolUseId, unmeasuredPathSource, writeStderr,
} from "./codex_adapter.mjs";
import {
  analysisWriteResult, assertEncodablePath, editTool, findProjectRoot, gitCommitGuardResult, privilegeEscalationGuardResult,
  reportUnclassifiedShellRoute, roleOnCodeResult, sessionStartResult, shellTool,
} from "./hook_core.mjs";
import { lazyHookData } from "./hook_data.mjs";

/** @typedef {import("./hook_data.mjs").HookData} HookData */
/** @typedef {import("./hook_core.mjs").HookResult} HookResult */
/** @typedef {import("./codex_adapter.mjs").Payload} Payload */

/**
 * The project root the payload's paths are relative to.
 *
 * Codex patch bodies carry repo-relative paths (`*** Add File: note.txt`), so every path
 * predicate needs the root to normalize against — not only the D2 one (C47).
 * @param {HookData} data
 * @param {Payload} payload
 * @returns {string}
 */
function _payloadRoot(data, payload) {
  return findProjectRoot(_startOf(data, payload));
}

/**
 * `Path(cwd(payload)) if cwd(payload) else None` — and a `cwd` holding NUL (`ValueError`) or a lone
 * surrogate (`UnicodeEncodeError`) is refused here as `Path.resolve()` refuses it in Python.
 * @param {HookData} data
 * @param {Payload} payload
 * @returns {string | null}
 */
function _startOf(data, payload) {
  const given = cwd(data, payload);
  if (!given) {
    return null;
  }
  assertEncodablePath(given);
  return pyPath(given);
}

/**
 * The once-per-event claim the two payload-defect diagnostics share: the session/tool-use pair is
 * the event identity, so one malformed edit produces one diagnostic while a later malformed edit
 * remains visible. A missing component repeats fail-visible instead of creating a global marker
 * that can hide drift.
 * @param {HookData} data
 * @param {string} stem the marker kind's vocabulary stem
 * @param {Payload} payload
 * @returns {boolean} whether to report
 */
function _claimsEvent(data, stem, payload) {
  const sid = sessionId(data, payload);
  const eventId = toolUseId(data, payload);
  return !(
    sid !== unidentifiedIdentity(data.markers) &&
    eventId !== "" &&
    !claimDiagnosticMarker(data.markers, markerKind(data.markers, stem), `${sid}\u0000${eventId}`)
  );
}

/**
 * Report an edit call whose target could not be read out of the payload.
 *
 * The matcher fired, so Codex did route a file-touching call here; extracting no path from it
 * means akmon is reading the wrong key, not that there was nothing to say. C48 was exactly that —
 * three advisory hooks inert from the day they were wired, invisible because a hook with a broken
 * payload reader and a hook with nothing to report both print nothing. Stderr only: the model
 * never sees this, and the call is never blocked.
 * @param {HookData} data
 * @param {Payload} payload
 * @param {string} name
 * @returns {void}
 */
function _reportUnreadableTarget(data, payload, name) {
  if (name !== editTool(data)) {
    return;
  }
  if (!_claimsEvent(data, "codex_unreadable_target", payload)) {
    return;
  }
  writeStderr(
    fill(dictItem(data.codex, "unreadable_target"), {
      tool_name: toolName(data, payload) || "apply_patch",
      payload_shape: payloadShape(data, payload),
    }),
  );
}

/**
 * Report an edit whose paths came only from keys no measured Codex version sends.
 *
 * C48 deleted the invented `patch` keys but left the guessed *path* keys in place, and a guess
 * that happens to match is worse than one that misses: an empty list raises the no-path signal,
 * while a wrong path is classified in silence. So the advisories still run on it — a probable
 * target beats no target — and the provenance is stated instead of being presented as measured
 * fact (ADR-0012/D01, owner choice iii).
 * @param {HookData} data
 * @param {Payload} payload
 * @returns {void}
 */
function _reportUnmeasuredPathSource(data, payload) {
  if (!_claimsEvent(data, "codex_unmeasured_path", payload)) {
    return;
  }
  writeStderr(
    fill(dictItem(data.codex, "unmeasured_path_source"), {
      tool_name: toolName(data, payload) || "apply_patch",
      payload_shape: payloadShape(data, payload),
    }),
  );
}

/**
 * Run one path-keyed advisory over the paths the payload names, first result wins.
 *
 * One body for all three wired advisories: they differed only in the decision function, and a
 * payload-reading defect in a copy is a defect the other copies hide (C48).
 * @param {HookData} data
 * @param {Payload} payload
 * @param {(kind: string, path: string, sid: string, root: string) => HookResult | null} decide
 * @returns {void}
 */
function _advisory(data, payload, decide) {
  const kind = toolKind(data, payload);
  const sid = sessionId(data, payload);
  if (kind === shellTool(data)) {
    reportUnclassifiedShellRoute(data, sid);
    return;
  }
  const paths = filePaths(data, payload);
  if (paths.length === 0) {
    _reportUnreadableTarget(data, payload, kind);
    return;
  }
  if (kind === editTool(data) && unmeasuredPathSource(data, payload)) {
    _reportUnmeasuredPathSource(data, payload);
  }
  const root = _payloadRoot(data, payload);
  for (const path of paths) {
    const result = decide(kind, path, sid, root);
    if (result !== null) {
      printResult(data, result);
      return;
    }
  }
}

/**
 * @param {HookData} data
 * @param {Payload} payload
 * @returns {void}
 */
function _sessionStart(data, payload) {
  printResult(data, sessionStartResult(data, findProjectRoot(_startOf(data, payload))));
}

/**
 * The hook routes this wrapper dispatches (hooks/codex_hook.json, C102).
 * @param {HookData} data
 * @returns {string[]}
 */
function _routes(data) {
  return pyIterate(dictItem(data.codex, "routes"));
}

/** A bad route argument: where `argparse` would print usage and exit on its own, this is the one crash line. */
export class UsageError extends Error {
  /** @param {string} message */
  constructor(message) {
    super(message);
    this.name = "UsageError";
  }
}

/**
 * The route `argv` names: exactly one of `routes`, optionally beside one `--`.
 * @param {string[]} argv the arguments after the script
 * @param {string[]} routes
 * @returns {string}
 * @throws {UsageError} for anything else, `-h`/`--help` included (see the header)
 */
function _parseRoute(argv, routes) {
  let operands = argv;
  if (argv.length === 2 && (argv[0] === "--" || argv[1] === "--")) {
    operands = argv[0] === "--" ? argv.slice(1) : argv.slice(0, 1);
  }
  if (operands.length === 0) {
    throw new UsageError("the following arguments are required: hook");
  }
  if (operands.length > 1) {
    throw new UsageError(`unrecognized arguments: ${operands.slice(1).join(" ")}`);
  }
  if (!routes.includes(operands[0])) {
    throw new UsageError(`argument hook: invalid choice: '${operands[0]}'`);
  }
  return operands[0];
}

/**
 * @param {HookData} data
 * @param {string} route
 * @param {Payload} payload
 * @returns {void}
 */
function _dispatch(data, route, payload) {
  if (route === "analysis-guard") {
    _advisory(data, payload, (kind, path, sid, root) => analysisWriteResult(data, kind, path, sid, root));
  } else if (route === "role-on-code") {
    _advisory(data, payload, (kind, path, sid, root) => roleOnCodeResult(data, kind, path, sid, root));
  } else if (route === "session-start") {
    _sessionStart(data, payload);
  } else if (route === "git-commit-guard") {
    // Intentionally not wired by sync.py yet; C28(b) owns the exact live-probe,
    // owner verification, then generated-wiring sequence for Bash+git behavior.
    const cmd = command(data, payload);
    printResult(data, privilegeEscalationGuardResult(data, cmd) ?? gitCommitGuardResult(data, cmd));
  }
}

/**
 * Run one route under the crash guard: a crash exits 1 so Codex shows the hook `Failed`.
 *
 * Every route writes at most one document, as its last step, so a crash cannot leave a partial
 * one behind it (ADR-0013/D01).
 * @param {string[] | null} [argv] the arguments after the script (default: the process's)
 * @returns {number} The process exit code.
 */
export function main(argv = null) {
  let hook = "codex-hook";
  try {
    const data = lazyHookData();
    const route = _parseRoute(argv ?? process.argv.slice(2), _routes(data));
    hook = `codex-hook ${route}`;
    _dispatch(data, route, loadPayload());
  } catch (exc) {
    // crash-open: every failure is reported, none blocks
    return reportFailure(hook, exc);
  }
  return 0;
}

/**
 * Whether node was told to execute `invoked` as this very module (see `akmon/cli.mjs`).
 * @param {string} invoked `process.argv[1]`, the path node was given
 * @returns {boolean}
 */
function runAsEntryPoint(invoked) {
  const self = fileURLToPath(import.meta.url);
  try {
    return fs.realpathSync(invoked) === fs.realpathSync(self);
  } catch {
    return invoked === self;
  }
}

if (process.argv[1] !== undefined && runAsEntryPoint(process.argv[1])) {
  process.exitCode = main();
}
