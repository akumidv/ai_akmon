/**
 * Fixtures for the browser tool's tests: a fake machine and a throwaway project. The file holds no
 * test of its own, so `node --test` reports it as an empty one.
 */

import { test } from "node:test";
import fs from "node:fs";
import os from "node:os";
import { posix } from "node:path";

test("support module loads", () => {});

/**
 * A fake machine: only the paths in `files` exist.
 * @param {{files?: string[], platform?: string, isWsl?: boolean, display?: boolean, pathDirs?: string[], windows?: string | null, dirs?: Record<string, string[]>}} [given]
 * @returns {import("./host.mjs").Host}
 */
export function fakeHost(given = {}) {
  const files = new Set(given.files ?? []);
  return {
    platform: given.platform ?? "linux",
    isWsl: given.isWsl ?? false,
    display: given.display ?? true,
    pathDirs: given.pathDirs ?? [],
    exists: (path) => files.has(path),
    subdirectories: (dir) => given.dirs?.[dir] ?? [],
    windowsAppPath: () => given.windows ?? null,
  };
}

/**
 * A throwaway akmon project: `AGENTS.md` and a dev root `_aitna` holding the record.
 * @param {string} [record] the text of `_aitna/.akmon.toml`
 * @returns {{root: string, dispose: () => void}}
 */
export function tempProject(record = "") {
  const root = fs.realpathSync(fs.mkdtempSync(posix.join(os.tmpdir(), "akmon-browser-")));
  fs.writeFileSync(posix.join(root, "AGENTS.md"), "# agents\n");
  fs.mkdirSync(posix.join(root, "_aitna"));
  fs.writeFileSync(posix.join(root, "_aitna", ".akmon.toml"), record);
  return { root, dispose: () => fs.rmSync(root, { recursive: true, force: true }) };
}

/**
 * A fake Chrome speaking CDP over a fake transport. `replies` maps a method to a function of its
 * parameters that returns the result (or throws, which answers with a protocol error); it may call
 * `control.emit` first, and an event emitted before the return reaches the client before the answer.
 * `Target.attachToTarget` and `Target.detachFromTarget` are answered unless `replies` says otherwise.
 * @param {Record<string, (params: any, control: {emit: (method: string, params: unknown) => void}) => unknown>} [replies]
 * @param {{targets?: object[], now?: number, files?: Record<string, string>}} [given] `files` are the files `deps.readText` reads
 * @returns {{transport: import("./cdp.mjs").Transport, calls: {method: string, params: any, sessionId?: string}[], emit: (method: string, params: unknown) => void, end: () => void, deps: import("./ops.mjs").Deps}}
 */
export function fakeChrome(replies = {}, given = {}) {
  /** @type {{method: string, params: any, sessionId?: string}[]} */
  const calls = [];
  /** @type {import("./cdp.mjs").Transport} */
  const transport = { send: () => {}, close: () => {}, onmessage: null, onclose: null };
  /** @param {unknown} message */
  const deliver = (message) => setImmediate(() => transport.onmessage?.(JSON.stringify(message)));
  /** @type {(method: string, params: unknown) => void} */
  const emit = (method, params) => deliver({ method, params, sessionId: "S1" });
  /** @type {Record<string, (params: any, control: {emit: (method: string, params: unknown) => void}) => unknown>} */
  const all = {
    "Target.attachToTarget": () => ({ sessionId: "S1" }),
    "Target.detachFromTarget": () => ({}),
    ...replies,
  };
  transport.send = (text) => {
    const { id, method, params, sessionId } = JSON.parse(text);
    calls.push({ method, params, ...(sessionId === undefined ? {} : { sessionId }) });
    try {
      const result = all[method]?.(params, { emit }) ?? {};
      Promise.resolve(result).then(
        (value) => deliver({ id, result: value }),
        (error) => deliver({ id, error: { message: error.message } }),
      );
    } catch (exc) {
      deliver({ id, error: { message: exc instanceof Error ? exc.message : String(exc) } });
    }
  };
  const targets = given.targets ?? [
    { id: "T1", type: "page", title: "Shop", url: "https://shop.example/cart" },
    { id: "T2", type: "page", title: "Docs", url: "https://docs.example/start" },
    { id: "W1", type: "service_worker", title: "sw", url: "https://shop.example/sw.js" },
  ];
  return {
    transport,
    calls,
    emit,
    end: () => transport.onclose?.("the browser closed the connection"),
    deps: {
      fetchJson: async (url) => (url.endsWith("/json/list") ? targets : { webSocketDebuggerUrl: "ws://fake/browser" }),
      open: async () => transport,
      now: () => given.now ?? 1_000_000,
      readText: (path) => {
        const text = given.files?.[path];
        if (text === undefined) {
          throw new Error(`ENOENT: no such file ${path}`);
        }
        return text;
      },
    },
  };
}

/** The extension the fake `chrome://extensions` page lists unless a test says otherwise. */
export const SAMPLE_EXTENSION = Object.freeze({
  id: "abcdefghijklmnopabcdefghijklmnop",
  name: "Bench",
  version: "1.2.3",
  state: "ENABLED",
  enabled: true,
  unpacked: true,
  path: "/work/acme/extension",
  disableReasons: /** @type {string[]} */ ([]),
  errors: /** @type {string[]} */ ([]),
});

/**
 * The replies of a fake Chrome that has a `chrome://extensions` page: a background tab is created, readied,
 * asked and closed. Pass them to `fakeChrome`, with the replies of the rest.
 * @param {{list?: object[], reload?: object[] | ((ids: string[]) => object[]), seen?: string[]}} [given]
 *   `seen` collects the scripts that ran in the page
 * @returns {Record<string, (params: any) => unknown>}
 */
export function extensionsPage(given = {}) {
  const list = given.list ?? [SAMPLE_EXTENSION];
  return {
    "Target.createTarget": (params) => ({ targetId: params.url === "chrome://extensions" ? "X1" : "P9" }),
    "Target.closeTarget": () => ({ success: true }),
    "Runtime.evaluate": (params) => {
      const script = String(params.expression);
      given.seen?.push(script);
      if (script.startsWith("typeof chrome")) {
        return { result: { value: true } };
      }
      if (script.includes("updateProfileConfiguration")) {
        return { result: { value: true } };
      }
      if (script.includes("dev.reload")) {
        const ids = /** @type {string[]} */ (JSON.parse(/for \(const id of (\[.*?\])\)/.exec(script)?.[1] ?? "[]"));
        const outcomes = typeof given.reload === "function" ? given.reload(ids) : (given.reload ?? []);
        return { result: { value: outcomes } };
      }
      if (script.includes("getExtensionsInfo")) {
        return { result: { value: list } };
      }
      return { result: { type: "undefined" } };
    },
  };
}
