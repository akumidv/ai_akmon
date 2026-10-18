/**
 * Bounded live query of Codex host-side hook delivery — the JavaScript twin of
 * `common/codex_hooks.py` (C70; ADR 0012/D03, design §7; ADR 0020 D01);
 * `units/codex_hooks.toml` is the spec both must pass.
 *
 * Generated wiring is structural proof only: a discovered hook entry can be reported
 * `enabled: true` while its persisted trust is absent or stale, and the handler simply never
 * fires. This module derives the expected hook population from generated wiring and compares it
 * against the authoritative `codex app-server` `hooks/list` result. The wire protocol (newline
 * delimited JSON-RPC 2.0 over stdio, `initialize` then `hooks/list`, a response matched on its
 * request id) and the "no vendor output reaches a diagnostic" boundary are the Python module's:
 * a {@link CodexProtocolError} is built from a failure *kind* of the data file's
 * `protocol_failures` table, never from text.
 *
 * Data (the C102/C103 convention): this module never reads a file itself. `data` is the parsed
 * `common/codex_hooks.json`, read once by the caller through {@link readCodexHooksData} and
 * passed down as the first parameter — the error classes included, which is why
 * {@link CodexProtocolError} takes `(data, kind)`.
 *
 * Twin notes, each a place where the stdlib answers differently from Node's:
 * - `defaultRunner` is `child_process.spawn` with piped stdin/stdout and ignored stderr; the
 *   Python reader thread is the `data` events of the stdout stream, the queue timeout a timer.
 *   Python's text mode reads lines with universal newlines (`\r`, `\r\n` and `\n` end a line, all
 *   delivered as `\n`) and strict decoding, a decode failure ending the stream; so does this;
 * - a process that fails to start is an `error` event before `spawn` here and an `OSError` from
 *   `Popen` there — both `unstartable`; a write to a dead process is `EPIPE` on the stdin stream
 *   (asynchronous here), `stdin-closed` while no answer is decided — whether an early exit reads
 *   `stdin-closed` or `stdout-closed` is a race in both languages;
 * - cleanup is the Python sequence: close stdin, `SIGTERM`, a 2 s wait for the exit, `SIGKILL`, a
 *   second 2 s wait; a child alive after both is abandoned (unref'd), never waited on;
 * - `json.loads` is `jsonLoads` of `pyjson.mjs` (`NaN`, big-integer and nesting limits included),
 *   and the handshake JSON is `hookForm` (`json.dumps` with its default separators);
 * - a wiring object's events are visited in JavaScript key order, which differs from Python's
 *   insertion order only for integer-like keys (the first unmapped event named in the error).
 */

import { spawn } from "node:child_process";
import { clearTimeout, setTimeout } from "node:timers";
import { TextDecoder } from "node:util";
import { fileURLToPath } from "node:url";

import { hookForm } from "./json_writer.mjs";
import { read } from "./jsondata.mjs";
import { jsonLoads } from "./pyjson.mjs";
import { isDict, pyRepr } from "./pyvalue.mjs";

/**
 * The shape of `common/codex_hooks.json` — the data file is the owner of these keys.
 * @typedef {object} CodexHooksData
 * @property {Record<string, string>} protocol_failures
 * @property {Record<string, string>} event_names
 * @property {string[]} trust_statuses
 * @property {string[]} live_trust_statuses
 */

/** The bounded wait for a `hooks/list` answer, in seconds. */
export const DEFAULT_TIMEOUT_SECONDS = 5;

/** How long cleanup waits for the app-server to exit, once after `SIGTERM` and once after `SIGKILL`. */
const _EXIT_GRACE_SECONDS = 2;

/** Fixed JSON-RPC request ids: 1 for the handshake, 2 for the query that is read. */
const _INITIALIZE_ID = 1;
const _HOOKS_LIST_ID = 2;

/** The fallback kind a {@link CodexProtocolError} outside the closed table degrades to. */
const _UNCLASSIFIED = "unclassified";

/**
 * The closed diagnostic table and the status vocabularies, as the data file carries them.
 * @returns {CodexHooksData}
 */
export function readCodexHooksData() {
  return /** @type {CodexHooksData} */ (read(fileURLToPath(new URL("../../common/codex_hooks.json", import.meta.url))));
}

/**
 * codex app-server resolved but its hooks/list exchange could not be trusted.
 *
 * Built from a failure `kind` — a key of the data file's `protocol_failures` — and never from
 * text: `message` is always that key's fixed message, and any other value (arbitrary text, a
 * non-string) becomes `unclassified`. `kind` is kept for callers and carriers.
 */
export class CodexProtocolError extends Error {
  /**
   * @param {CodexHooksData} data
   * @param {unknown} kind
   */
  constructor(data, kind) {
    const known = typeof kind === "string" && Object.hasOwn(data.protocol_failures, kind);
    const chosen = known ? /** @type {string} */ (kind) : _UNCLASSIFIED;
    super(data.protocol_failures[chosen]);
    this.name = "CodexProtocolError";
    this.kind = chosen;
  }
}

/** Wiring handed to {@link expectedCodexHooks} is not the shape akmon's generator emits. */
export class CodexWiringError extends Error {
  /** @param {string} message */
  constructor(message) {
    super(message);
    this.name = "CodexWiringError";
  }
}

/**
 * The `[eventName, matcher, command]` triples one wiring group expects.
 * @param {CodexHooksData} data
 * @param {string} event
 * @param {unknown} group
 * @returns {Array<[string, string | null, string]>}
 */
function _expectedHooksFromGroup(data, event, group) {
  if (!isDict(group)) {
    throw new CodexWiringError(`Codex wiring event ${pyRepr(event)} has a group that is not an object`);
  }
  const wiredGroup = /** @type {Record<string, unknown>} */ (group);
  const matcher = Object.hasOwn(wiredGroup, "matcher") ? wiredGroup.matcher : null;
  if (matcher !== null && typeof matcher !== "string") {
    throw new CodexWiringError(`Codex wiring event ${pyRepr(event)} has a non-string matcher`);
  }
  const hooks = Object.hasOwn(wiredGroup, "hooks") ? wiredGroup.hooks : [];
  if (!Array.isArray(hooks)) {
    throw new CodexWiringError(`Codex wiring event ${pyRepr(event)} has a group whose hooks is not a list`);
  }
  /** @type {Array<[string, string | null, string]>} */
  const expected = [];
  for (const hook of hooks) {
    if (!isDict(hook)) {
      throw new CodexWiringError(`Codex wiring event ${pyRepr(event)} has a hook that is not an object`);
    }
    const wired = /** @type {Record<string, unknown>} */ (hook);
    if (wired.type !== "command") {
      continue;
    }
    const command = Object.hasOwn(wired, "command") ? wired.command : null;
    if (typeof command !== "string") {
      throw new CodexWiringError(`Codex wiring event ${pyRepr(event)} has a command hook without a command`);
    }
    expected.push([data.event_names[event], /** @type {string | null} */ (matcher), command]);
  }
  return expected;
}

/**
 * `[eventName, matcher, command]` triples generated Codex wiring expects to be live.
 *
 * Reads the nested shape `sync` emits and `.codex/hooks.json` carries, and throws
 * {@link CodexWiringError} for anything else — a non-object, an unmapped event, a group or hook
 * list that is not a list, a command that is not a string.
 * @param {CodexHooksData} data
 * @param {unknown} wiring
 * @returns {Array<[string, string | null, string]>}
 */
export function expectedCodexHooks(data, wiring) {
  if (!isDict(wiring)) {
    throw new CodexWiringError("Codex wiring is not a JSON object");
  }
  const wired = /** @type {Record<string, unknown>} */ (wiring);
  const events = Object.hasOwn(wired, "hooks") ? wired.hooks : {};
  if (!isDict(events)) {
    throw new CodexWiringError("Codex wiring `hooks` is not an object");
  }
  /** @type {Array<[string, string | null, string]>} */
  const expected = [];
  for (const [event, groups] of Object.entries(/** @type {Record<string, unknown>} */ (events))) {
    if (!Object.hasOwn(data.event_names, event)) {
      throw new CodexWiringError(`Codex wiring names event ${pyRepr(event)}, which has no hooks/list mapping`);
    }
    if (!Array.isArray(groups)) {
      throw new CodexWiringError(`Codex wiring event ${pyRepr(event)} is not a list of groups`);
    }
    for (const group of groups) {
      expected.push(..._expectedHooksFromGroup(data, event, group));
    }
  }
  return expected;
}

/**
 * `null` when the entry runs, else its problem category — always a fixed word.
 *
 * `enabled` counts only as the boolean `true`. An unrecognized `trustStatus` is `"unrecognized"`
 * rather than its own value, so no vendor-chosen string becomes a problem name.
 * @param {CodexHooksData} data
 * @param {Record<string, unknown>} hook
 * @returns {string | null}
 */
export function deliveryState(data, hook) {
  if (hook.enabled !== true) {
    return "disabled";
  }
  const trust = hook.trustStatus;
  if (typeof trust !== "string" || !data.trust_statuses.includes(trust)) {
    return "unrecognized";
  }
  return data.live_trust_statuses.includes(trust) ? null : trust;
}

/**
 * `problem -> [command, ...]` for every expected entry that is not live and trusted.
 *
 * `problem` is one of a fixed vocabulary: `missing`, `disabled`, `untrusted`/`modified`,
 * `unrecognized`, `ambiguous` (the host reported the same identity more than once and the copies
 * disagree). The commands listed are akmon's own, taken from `expected`, never from `entries`.
 * @param {CodexHooksData} data
 * @param {ReadonlyArray<readonly [string, string | null, string]>} expected
 * @param {ReadonlyArray<unknown>} entries
 * @returns {Record<string, string[]>}
 */
export function hookTrustProblems(data, expected, entries) {
  /** @type {Map<string, Array<Record<string, unknown>>>} */
  const byIdentity = new Map();
  for (const entry of entries) {
    if (!isDict(entry)) {
      continue;
    }
    const hook = /** @type {Record<string, unknown>} */ (entry);
    if (hook.handlerType !== "command") {
      continue;
    }
    const identity = [hook.eventName ?? null, hook.matcher ?? null, hook.command ?? null];
    if (!identity.every((part) => part === null || typeof part === "string")) {
      continue; // a misshapen identity cannot be an expected one
    }
    const key = JSON.stringify(identity);
    const bucket = byIdentity.get(key);
    if (bucket === undefined) {
      byIdentity.set(key, [hook]);
    } else {
      bucket.push(hook);
    }
  }

  /** @type {Record<string, string[]>} */
  const problems = {};
  for (const identity of expected) {
    const command = identity[2];
    const hooks = byIdentity.get(JSON.stringify([identity[0], identity[1], identity[2]]));
    if (hooks === undefined || hooks.length === 0) {
      (problems.missing ??= []).push(command);
      continue;
    }
    const states = new Set(hooks.map((hook) => deliveryState(data, hook)));
    const state = states.size > 1 ? "ambiguous" : /** @type {string | null} */ (states.values().next().value);
    if (state !== null) {
      (problems[state] ??= []).push(command);
    }
  }
  return problems;
}

/**
 * A `hooks/list` runner: the raw response line, or a thrown error (any `Error`; only a
 * {@link CodexProtocolError}'s `kind` survives the seam).
 * @typedef {(command: ReadonlyArray<string>, cwd: string, timeoutSeconds: number) => Promise<string> | string} HooksListRunner
 */

/** A promise that resolves after `seconds`; the timer never keeps the process alive on its own. */
function _sleep(/** @type {number} */ seconds) {
  return new Promise((resolve) => {
    setTimeout(resolve, seconds * 1000).unref();
  });
}

/**
 * Close stdin, then `SIGTERM`/`SIGKILL` with a bounded wait after each.
 * @param {import("node:child_process").ChildProcess} child
 * @returns {Promise<void>}
 */
async function _cleanupCodexProcess(child) {
  const gone = new Promise((resolve) => {
    if (child.exitCode !== null || child.signalCode !== null) {
      resolve(true);
    } else {
      child.once("exit", () => resolve(true));
    }
  });
  try {
    child.stdin?.end();
  } catch {
    // already closed
  }
  for (const signal of /** @type {const} */ (["SIGTERM", "SIGKILL"])) {
    try {
      child.kill(signal);
    } catch {
      // gone already
    }
    if ((await Promise.race([gone, _sleep(_EXIT_GRACE_SECONDS)])) === true) {
      break;
    }
  }
  child.stdout?.destroy();
  child.stdin?.destroy();
  if (child.exitCode === null && child.signalCode === null) {
    child.unref(); // abandoned: the answer, or its failure, is already decided
  }
}

/**
 * Spawn `codex app-server` and negotiate the minimal handshake.
 *
 * Returns the raw `hooks/list` response line. This is the seam {@link queryHooksList} calls by
 * default; a caller may pass its own `runner` instead.
 * @param {CodexHooksData} data
 * @param {ReadonlyArray<string>} command
 * @param {string} cwd
 * @param {number} timeoutSeconds
 * @returns {Promise<string>}
 */
async function _defaultRunner(data, command, cwd, timeoutSeconds) {
  const fail = (/** @type {string} */ kind) => new CodexProtocolError(data, kind);
  /** @type {import("node:child_process").ChildProcess} */
  let child;
  try {
    child = spawn(command[0], command.slice(1), { cwd, stdio: ["pipe", "pipe", "ignore"] });
  } catch {
    throw fail("unstartable");
  }
  await new Promise((resolve, reject) => {
    child.once("spawn", () => resolve(undefined));
    child.once("error", () => reject(fail("unstartable")));
  });
  // After the spawn an `error` event (a failed kill, a stream fault) decides nothing here.
  child.on("error", () => {});

  /** @type {(error: Error) => void} */
  let settleError = () => {};
  const stdinFailed = new Promise((_resolve, reject) => {
    settleError = reject;
  });
  stdinFailed.catch(() => {});
  child.stdin?.on("error", () => settleError(fail("stdin-closed")));

  const answer = new Promise((resolve, reject) => {
    const deadline = Date.now() + timeoutSeconds * 1000;
    const timer =
      timeoutSeconds > 0 ? setTimeout(() => reject(fail("timeout")), Math.max(0, deadline - Date.now())) : null;
    timer?.unref();
    if (timer === null) {
      reject(fail("timeout"));
    }
    const decoder = new TextDecoder("utf-8", { fatal: true });
    let pending = "";
    let finished = false;
    const done = (/** @type {() => void} */ settle) => {
      if (!finished) {
        finished = true;
        if (timer !== null) {
          clearTimeout(timer);
        }
        settle();
      }
    };
    /** @param {string} line */
    const take = (line) => {
      /** @type {unknown} */
      let message;
      try {
        message = jsonLoads(line);
      } catch (error) {
        if (/** @type {Error} */ (error).name === "JSONDecodeError") {
          return;
        }
        done(() => reject(error));
        return;
      }
      if (isDict(message) && /** @type {Record<string, unknown>} */ (message).id === _HOOKS_LIST_ID) {
        done(() => resolve(line));
      }
    };
    const drain = (/** @type {boolean} */ final) => {
      for (;;) {
        const match = /\r\n|\r|\n/.exec(pending);
        // A trailing `\r` may be the first half of a `\r\n`: wait for the next chunk unless final.
        if (match === null || (!final && match[0] === "\r" && match.index + 1 === pending.length)) {
          break;
        }
        const line = pending.slice(0, match.index) + "\n";
        pending = pending.slice(match.index + match[0].length);
        take(line);
      }
      if (final && pending !== "") {
        const line = pending;
        pending = "";
        take(line);
      }
    };
    const closed = () => {
      drain(true);
      done(() => reject(fail("stdout-closed")));
    };
    child.stdout?.on("data", (/** @type {Buffer} */ chunk) => {
      try {
        pending += decoder.decode(chunk, { stream: true });
      } catch {
        closed(); // a strict decode failure ends the stream, as in the twin's reader thread
        return;
      }
      drain(false);
    });
    child.stdout?.on("end", closed);
    child.stdout?.on("error", closed);
    child.stdout?.on("close", closed);
  });
  answer.catch(() => {});

  try {
    child.stdin?.write(
      hookForm({
        id: _INITIALIZE_ID,
        method: "initialize",
        params: { clientInfo: { name: "akmon", title: "akmon verify", version: "1" } },
      }) +
        "\n" +
        hookForm({ id: _HOOKS_LIST_ID, method: "hooks/list", params: { cwds: [cwd] } }) +
        "\n",
    );
    return /** @type {string} */ (await Promise.race([answer, stdinFailed]));
  } finally {
    await _cleanupCodexProcess(child);
  }
}

/**
 * Spawn `command` (`codex app-server`) and negotiate the minimal handshake; returns the raw
 * `hooks/list` response line (see the module header for the wire shape).
 *
 * The data file's `protocol_failures` table is read here once per call: the runner takes the
 * Python signature `(command, cwd, timeout)`, so the data cannot be passed down.
 * @param {ReadonlyArray<string>} command
 * @param {string} cwd
 * @param {number} timeoutSeconds
 * @returns {Promise<string>}
 */
export async function defaultRunner(command, cwd, timeoutSeconds) {
  return _defaultRunner(readCodexHooksData(), command, cwd, timeoutSeconds);
}

/**
 * Reject a `hooks` element that is not the measured `HookMetadata` shape.
 *
 * Checked for every element, not only the expected ones: one malformed entry means the answer is
 * not the protocol this module measured.
 * @param {CodexHooksData} data
 * @param {unknown} hook
 */
export function checkHookMetadata(data, hook) {
  if (!isDict(hook)) {
    throw new CodexProtocolError(data, "hook-not-object");
  }
  const meta = /** @type {Record<string, unknown>} */ (hook);
  if (typeof meta.handlerType !== "string") {
    throw new CodexProtocolError(data, "hook-handler");
  }
  if (typeof meta.enabled !== "boolean") {
    throw new CodexProtocolError(data, "hook-enabled");
  }
  const trust = meta.trustStatus;
  if (typeof trust !== "string" || !data.trust_statuses.includes(trust)) {
    throw new CodexProtocolError(data, "hook-trust");
  }
  if (meta.handlerType !== "command") {
    return;
  }
  if (typeof meta.eventName !== "string" || typeof meta.command !== "string") {
    throw new CodexProtocolError(data, "hook-identity");
  }
  const matcher = Object.hasOwn(meta, "matcher") ? meta.matcher : null;
  if (matcher !== null && typeof matcher !== "string") {
    throw new CodexProtocolError(data, "hook-matcher");
  }
}

/**
 * Call `runner` and translate any failure into a {@link CodexProtocolError}.
 *
 * A {@link CodexProtocolError} the runner throws is rebuilt here from its `kind` alone, so a
 * subclass with its own message cannot carry text past this seam. Any other error the runner
 * throws becomes `runner-failed`.
 * @param {CodexHooksData} data
 * @param {HooksListRunner} runner
 * @param {ReadonlyArray<string>} command
 * @param {string} cwd
 * @param {number} timeout
 * @returns {Promise<string>}
 */
async function _callHooksListRunner(data, runner, command, cwd, timeout) {
  try {
    return await runner(command, cwd, timeout);
  } catch (error) {
    if (error instanceof CodexProtocolError) {
      throw new CodexProtocolError(data, error.kind);
    }
    throw new CodexProtocolError(data, "runner-failed");
  }
}

/**
 * Decode `raw` and check it answers this exchange before anything else reads it.
 * @param {CodexHooksData} data
 * @param {unknown} raw
 * @returns {Record<string, unknown>}
 */
export function parseHooksListMessage(data, raw) {
  /** @type {unknown} */
  let message;
  if (typeof raw !== "string") {
    throw new CodexProtocolError(data, "not-json");
  }
  try {
    message = jsonLoads(raw);
  } catch (error) {
    const name = /** @type {Error} */ (error).name;
    if (name === "JSONDecodeError" || name === "ValueError") {
      throw new CodexProtocolError(data, "not-json");
    }
    throw error;
  }
  if (!isDict(message)) {
    throw new CodexProtocolError(data, "not-object");
  }
  const found = /** @type {Record<string, unknown>} */ (message);
  if (found.id !== _HOOKS_LIST_ID) {
    throw new CodexProtocolError(data, "id-mismatch");
  }
  if (Object.hasOwn(found, "error")) {
    throw new CodexProtocolError(data, "jsonrpc-error");
  }
  return found;
}

/**
 * The one `result.data` entry answering `cwd`, checked for shape and discovery errors.
 *
 * Exactly one entry may answer `cwd`: choosing between two answers for it would make the result
 * depend on their order, so a second answer is uninspectable.
 * @param {CodexHooksData} data
 * @param {Record<string, unknown>} message
 * @param {string} cwd
 * @returns {Record<string, unknown>}
 */
export function hooksListProjectEntry(data, message, cwd) {
  const result = message.result;
  const rows = isDict(result) ? /** @type {Record<string, unknown>} */ (result).data : null;
  if (!Array.isArray(rows)) {
    throw new CodexProtocolError(data, "no-data");
  }
  const answers = rows.filter(
    (entry) => isDict(entry) && /** @type {Record<string, unknown>} */ (entry).cwd === String(cwd),
  );
  if (answers.length === 0) {
    throw new CodexProtocolError(data, "no-project");
  }
  if (answers.length > 1) {
    throw new CodexProtocolError(data, "duplicate-project");
  }
  const entry = /** @type {Record<string, unknown>} */ (answers[0]);
  if (!["hooks", "warnings", "errors"].every((field) => Array.isArray(entry[field]))) {
    throw new CodexProtocolError(data, "project-shape");
  }
  if (/** @type {unknown[]} */ (entry.errors).length > 0) {
    throw new CodexProtocolError(data, "discovery-errors");
  }
  return entry;
}

/**
 * The `hooks` entries `hooks/list` reports for `cwd` — the live oracle.
 *
 * Throws {@link CodexProtocolError} for anything short of a clean, well-shaped answer: a timeout,
 * a closed pipe, a JSON-RPC error object, a response id that does not echo this request's, no
 * entry or more than one entry for `cwd`, a per-project `errors` entry, or a response missing or
 * misshaping any field this module reads. A caller must not read a caught error as "no hooks" —
 * that is a distinct, positively reported state (an empty `data[].hooks` list).
 * @param {CodexHooksData} data
 * @param {ReadonlyArray<string>} command
 * @param {string} cwd
 * @param {{runner?: HooksListRunner, timeout?: number}} [options]
 * @returns {Promise<Array<Record<string, unknown>>>}
 */
export async function queryHooksList(
  data,
  command,
  cwd,
  { runner = undefined, timeout = DEFAULT_TIMEOUT_SECONDS } = {},
) {
  const run =
    runner ??
    ((/** @type {ReadonlyArray<string>} */ c, /** @type {string} */ d, /** @type {number} */ t) =>
      _defaultRunner(data, c, d, t));
  const raw = await _callHooksListRunner(data, run, command, cwd, timeout);
  const message = parseHooksListMessage(data, raw);
  const entry = hooksListProjectEntry(data, message, cwd);
  const hooks = /** @type {Array<unknown>} */ (entry.hooks);
  for (const hook of hooks) {
    checkHookMetadata(data, hook);
  }
  return /** @type {Array<Record<string, unknown>>} */ (hooks);
}
