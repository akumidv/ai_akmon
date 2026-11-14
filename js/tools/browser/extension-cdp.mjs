/**
 * The Chrome side of extension work: the extensions a Chrome holds and how to reload them, which target an
 * `sw` or `popup` means, and the action of an extension on a page. An extension's state is read and
 * changed the way `chrome://extensions` does it, through its `developerPrivate` API, by evaluating in a
 * `chrome://extensions` tab this module opens and closes (the one tab it ever closes: it made it). Nothing
 * here reads the project: the settings arrive resolved in the request (`protocol.mjs`). The module imports
 * only Node, because the CDP runner loads it on the Windows side too (`ops.mjs`).
 */

import { posix, win32 } from "node:path";

import { attachToPage, CdpError } from "./cdp.mjs";
import { redactFloor, redactUrl } from "./redact.mjs";
import { selectPage } from "./targets.mjs";

/** What an extension id looks like: 32 letters from `a` to `p`. */
export const EXTENSION_ID = /^[a-p]{32}$/;

/** How long the extensions page is given to load, in polls of 250 ms, and how long one script may run. */
const _READY_POLLS = 40;
const _POLL_MS = 250;
const _SCRIPT_MS = 60_000;

/**
 * One extension as the browser reports it.
 * @typedef {object} ExtensionInfo
 * @property {string} id
 * @property {string} name
 * @property {string} version
 * @property {string} state `ENABLED`, `DISABLED`, `TERMINATED` or `BLACKLISTED`
 * @property {boolean} enabled
 * @property {boolean} unpacked loaded from a folder, as the project's extensions are
 * @property {string | null} path the folder of an unpacked extension, as the browser sees it
 * @property {string[]} disableReasons why it is disabled, when it is
 * @property {string[]} errors the manifest errors it carries
 */

/**
 * What a target selector resolved to.
 * @typedef {object} Subject
 * @property {import("./targets.mjs").Target} target
 * @property {"page" | "sw" | "popup"} source what the lines of `logs` from it are tagged with
 */

/**
 * The id of the extension a `chrome-extension://` URL belongs to.
 * @param {string} url
 * @returns {string | null} `null` for any other URL
 */
export function extensionIdOf(url) {
  return /^chrome-extension:\/\/([a-p]{32})(?:[/?#]|$)/.exec(url)?.[1] ?? null;
}

/**
 * The page-side function that reduces one `developerPrivate` extension record to what the verbs print.
 */
const _SUMMARY = `(info) => ({
  id: info.id,
  name: info.name,
  version: info.version,
  state: info.state,
  enabled: info.state === "ENABLED",
  unpacked: info.location === "UNPACKED",
  path: info.path || null,
  disableReasons: Object.entries(info.disableReasons || {}).filter(([, on]) => on).map(([reason]) => reason),
  errors: (info.manifestErrors || []).map((error) => String(error.message || error.error || error)),
})`;

/** Lists every extension, disabled and terminated ones too. */
const _LIST_SCRIPT = `(async () => {
  const summary = ${_SUMMARY};
  const all = await chrome.developerPrivate.getExtensionsInfo({ includeDisabled: true, includeTerminated: true });
  return all.map(summary);
})()`;

/** Turns developer mode on, which Chrome needs to keep an unpacked extension enabled, and reads it back. */
const _DEVELOPER_MODE_SCRIPT = `(async () => {
  await chrome.developerPrivate.updateProfileConfiguration({ inDeveloperMode: true });
  const configuration = await chrome.developerPrivate.getProfileConfiguration();
  return configuration.inDeveloperMode === true;
})()`;

/**
 * The script that reloads the extensions of `ids` from disk the way the reload button of `chrome://extensions`
 * does (a `chrome.runtime.reload()` from the extension leaves a command-line-loaded extension disabled), and
 * reads each one back: its state, or the load error that kept it from coming back.
 * @param {readonly string[]} ids
 * @returns {string}
 */
function _reloadScript(ids) {
  return `(async () => {
  const summary = ${_SUMMARY};
  const dev = chrome.developerPrivate;
  const outcomes = [];
  for (const id of ${JSON.stringify(ids)}) {
    let loadError = null;
    try {
      const before = await dev.getExtensionInfo(id);
      if (before.state !== "ENABLED") {
        await chrome.management.setEnabled(id, true);
      }
      const error = await dev.reload(id, { failQuietly: true, populateErrorForUnpacked: true });
      if (error) {
        loadError = String(error.error || JSON.stringify(error));
      }
    } catch (error) {
      loadError = String(error && error.message ? error.message : error);
    }
    let info = null;
    for (let poll = 0; poll < 20; poll += 1) {
      try {
        info = await dev.getExtensionInfo(id);
      } catch (error) {
        info = null;
      }
      if ((info && info.state === "ENABLED") || loadError !== null) {
        break;
      }
      await new Promise((done) => setTimeout(done, 250));
    }
    outcomes.push({ id, loadError, info: info ? summary(info) : null });
  }
  return outcomes;
})()`;
}

/**
 * Wait for a number of milliseconds.
 * @param {number} ms
 * @returns {Promise<void>}
 */
function _sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Evaluate a script in a page and return its value.
 * @param {import("./cdp.mjs").PageSession} page
 * @param {string} expression
 * @returns {Promise<any>}
 * @throws {CdpError} with the exception's text when the script throws
 */
async function _evaluate(page, expression) {
  const answer = await page.send(
    "Runtime.evaluate",
    { expression, awaitPromise: true, returnByValue: true },
    _SCRIPT_MS,
  );
  if (answer.exceptionDetails !== undefined) {
    const details = answer.exceptionDetails;
    throw new CdpError(
      `chrome://extensions: ${details.exception?.description ?? details.exception?.value ?? details.text ?? "the script threw"}`,
    );
  }
  return answer.result?.value;
}

/**
 * Wait until the extensions page has its `developerPrivate` API.
 * @param {import("./cdp.mjs").PageSession} page
 * @returns {Promise<void>}
 * @throws {CdpError} when it does not appear
 */
async function _untilReady(page) {
  for (let poll = 0; poll < _READY_POLLS; poll += 1) {
    const ready = await _evaluate(
      page,
      'typeof chrome !== "undefined" && typeof (chrome.developerPrivate || {}).getExtensionsInfo === "function"',
    );
    if (ready === true) {
      return;
    }
    await _sleep(_POLL_MS);
  }
  throw new CdpError("chrome://extensions did not offer its developerPrivate API; this Chrome may not allow it");
}

/**
 * Run a script in a `chrome://extensions` tab opened for it in the background, and close that tab after.
 * @param {import("./cdp.mjs").CdpConnection} connection
 * @param {string} script
 * @returns {Promise<any>}
 */
async function _inExtensionsPage(connection, script) {
  const { targetId } = await connection.send("Target.createTarget", { url: "chrome://extensions", background: true });
  try {
    const page = await attachToPage(connection, String(targetId));
    await _untilReady(page);
    return await _evaluate(page, script);
  } finally {
    try {
      await connection.send("Target.closeTarget", { targetId }, { timeoutMs: 3000 });
    } catch {
      // The tab was this call's own and is gone or going: nothing of the user's is left open by it.
    }
  }
}

/**
 * Turn developer mode on.
 * @param {import("./cdp.mjs").CdpConnection} connection
 * @returns {Promise<{inDeveloperMode: boolean}>}
 */
export async function turnDeveloperModeOn(connection) {
  return { inDeveloperMode: (await _inExtensionsPage(connection, _DEVELOPER_MODE_SCRIPT)) === true };
}

/**
 * Every extension the browser holds.
 * @param {import("./cdp.mjs").CdpConnection} connection
 * @returns {Promise<ExtensionInfo[]>}
 */
export async function listExtensions(connection) {
  const list = await _inExtensionsPage(connection, _LIST_SCRIPT);
  if (!Array.isArray(list)) {
    throw new CdpError("chrome://extensions did not answer with a list of extensions");
  }
  return list;
}

/**
 * Whether two folder paths are the same folder, tolerating a Windows spelling (case, slash direction).
 * @param {string} first
 * @param {string} second
 * @returns {boolean}
 */
export function samePath(first, second) {
  const plain = (/** @type {string} */ path) => path.replaceAll("\\", "/").replace(/\/+$/, "");
  const [one, other] = [plain(first), plain(second)];
  return /^[a-z]:/i.test(one) || /^[a-z]:/i.test(other) ? one.toLowerCase() === other.toLowerCase() : one === other;
}

/**
 * The extensions a selector means: the one `select` names (an id, a name, else part of a name), or with no
 * `select` the unpacked ones, narrowed to the configured folders when there are any.
 * @param {readonly ExtensionInfo[]} list
 * @param {{select: string | null, paths: readonly string[]}} how
 * @returns {ExtensionInfo[]}
 */
export function matchExtensions(list, how) {
  if (how.select !== null) {
    const wanted = how.select.toLowerCase();
    const exact = list.filter((item) => item.id === how.select || item.name.toLowerCase() === wanted);
    return exact.length > 0 ? exact : list.filter((item) => item.name.toLowerCase().includes(wanted));
  }
  const unpacked = list.filter((item) => item.unpacked);
  if (how.paths.length === 0) {
    return unpacked;
  }
  return unpacked.filter((item) => item.path !== null && how.paths.some((path) => samePath(path, String(item.path))));
}

/**
 * One extension out of several matches.
 * @param {readonly ExtensionInfo[]} matches
 * @param {string} what what was looked for, for the message
 * @returns {ExtensionInfo}
 * @throws {CdpError} when there is none or more than one, naming them so `--ext` can pick
 */
export function soleExtension(matches, what) {
  if (matches.length === 1) {
    return matches[0];
  }
  const named = matches.map((item) => `${item.name} (${item.id})`).join(", ");
  throw new CdpError(
    matches.length === 0
      ? `no extension matches ${what}`
      : `${matches.length} extensions match ${what}: ${named}; pick one with --ext <id|name>`,
  );
}

/**
 * The id of the one extension among those that have something to attach to (`ids`): the one asked for, the
 * only one there is, or, among several, the configured one, which needs the browser's list.
 * @param {import("./cdp.mjs").CdpConnection} connection
 * @param {readonly string[]} ids the distinct extension ids that have the target looked for
 * @param {import("./protocol.mjs").Request} request `ext` and `extensionPaths` say which
 * @param {string} what what the extension must have, for the message
 * @returns {Promise<string>}
 * @throws {CdpError} when none or several qualify
 */
export async function extensionAmong(connection, ids, request, what) {
  const select = request.ext ?? null;
  if (select !== null && EXTENSION_ID.test(select)) {
    if (!ids.includes(select)) {
      throw new CdpError(`the extension ${select} has no ${what}`);
    }
    return select;
  }
  if (select === null && ids.length === 1) {
    return ids[0];
  }
  if (ids.length === 0) {
    throw new CdpError(`no extension has ${what}`);
  }
  const listed = await listExtensions(connection);
  const matches = matchExtensions(listed, { select, paths: request.extensionPaths ?? [] }).filter((item) =>
    ids.includes(item.id),
  );
  return soleExtension(matches, select === null ? `the configured extensions with ${what}` : `"${select}" with ${what}`)
    .id;
}

/**
 * The target a request's `target` names. A page is the `--page` one; `sw` is the service worker of the
 * extension the request names or configures, `popup` one of its open extension pages, and anything else is
 * a target id.
 * @param {import("./cdp.mjs").CdpConnection} connection
 * @param {readonly import("./targets.mjs").Target[]} targets
 * @param {import("./protocol.mjs").Request} request
 * @returns {Promise<Subject>}
 * @throws {CdpError} when nothing matches, saying what to do
 */
export async function resolveSubject(connection, targets, request) {
  const kind = request.target ?? "page";
  if (kind === "page") {
    return { target: selectPage(targets, request.page), source: "page" };
  }
  if (kind === "sw" || kind === "popup") {
    return _extensionSubject(connection, targets, request, kind);
  }
  const found = targets.find((target) => target.id === kind);
  if (found === undefined) {
    throw new CdpError(`no target has the id ${kind}; \`pages --all\` lists the targets`);
  }
  if (found.type === "service_worker") {
    return { target: found, source: "sw" };
  }
  return { target: found, source: extensionIdOf(found.url) === null ? "page" : "popup" };
}

/**
 * The service worker or the extension page of an extension.
 * @param {import("./cdp.mjs").CdpConnection} connection
 * @param {readonly import("./targets.mjs").Target[]} targets
 * @param {import("./protocol.mjs").Request} request
 * @param {"sw" | "popup"} kind
 * @returns {Promise<Subject>}
 * @throws {CdpError} when there is none
 */
async function _extensionSubject(connection, targets, request, kind) {
  const worker = kind === "sw";
  const candidates = targets.filter(
    (target) =>
      extensionIdOf(target.url) !== null &&
      (worker ? target.type === "service_worker" : target.type === "page" || target.type === "other"),
  );
  const what = worker ? "a running service worker" : "an open extension page (its popup)";
  const ids = [...new Set(candidates.map((target) => String(extensionIdOf(target.url))))];
  if (ids.length === 0) {
    throw new CdpError(
      worker
        ? "no extension service worker is running; a Manifest V3 worker stops when idle, so use the extension " +
            "(`ext action`, or its page) and run the verb again"
        : "no extension page is open; open the popup by hand, or run `ext action`",
    );
  }
  const id = await extensionAmong(connection, ids, request, what);
  const own = candidates.filter((target) => extensionIdOf(target.url) === id);
  const target = worker ? own[0] : (own.find((item) => /popup/i.test(item.url)) ?? own[0]);
  return { target, source: worker ? "sw" : "popup" };
}

/**
 * The popup page of an extension from its manifest: the `default_popup` of its action.
 * @param {string} manifestText the text of `manifest.json`
 * @param {string} id
 * @returns {string | null} a `chrome-extension://` URL, or `null` when the action has no popup
 * @throws {CdpError} when the text is not a manifest
 */
export function popupUrlOf(manifestText, id) {
  /** @type {any} */
  let manifest;
  try {
    manifest = JSON.parse(manifestText);
  } catch (exc) {
    throw new CdpError(`manifest.json is not JSON (${exc instanceof Error ? exc.message : String(exc)})`);
  }
  const popup = [manifest?.action, manifest?.browser_action, manifest?.page_action]
    .map((action) => action?.default_popup)
    .find((path) => typeof path === "string" && path !== "");
  return popup === undefined ? null : `chrome-extension://${id}/${popup.replace(/^\/+/, "")}`;
}

/**
 * The path of a folder's `manifest.json` in the folder's own spelling (a Windows path stays one).
 * @param {string} folder
 * @returns {string}
 */
function _manifestPath(folder) {
  return folder.includes("\\") || /^[a-z]:/i.test(folder)
    ? win32.join(folder, "manifest.json")
    : posix.join(folder, "manifest.json");
}

/**
 * What an extension's action did.
 * @typedef {object} ActionOutcome
 * @property {"cdp" | "popup"} route `cdp`: Chrome ran the action on the page, which gives the extension the active tab; `popup`: the popup page was opened in a new tab
 * @property {{id: string, name: string}} extension
 * @property {{id: string, title: string, url: string}} page the page the action was for
 * @property {{targetId: string, url: string} | null} popup the tab opened, on the `popup` route
 * @property {string | null} refusal why the browser's own action route was not used
 */

/**
 * Trigger the default action of an extension on the selected page. The browser's `Extensions.triggerAction`
 * runs it with the page as the active tab; when this Chrome does not offer that method over the DevTools
 * port, the action's popup page is opened in a new tab instead, which says so (it lacks the active-tab
 * context) and which the caller reports.
 * @param {import("./cdp.mjs").CdpConnection} connection
 * @param {readonly import("./targets.mjs").Target[]} targets
 * @param {{request: import("./protocol.mjs").Request, readText: (path: string) => string}} how
 * @returns {Promise<ActionOutcome>}
 * @throws {CdpError} when no extension or page matches, or neither route can run the action
 */
export async function triggerAction(connection, targets, how) {
  const { request } = how;
  const listed = await listExtensions(connection);
  const matches = matchExtensions(listed, { select: request.ext ?? null, paths: request.extensionPaths ?? [] }).filter(
    (item) => item.enabled,
  );
  const extension = soleExtension(
    matches,
    request.ext === null || request.ext === undefined ? "the configured extensions" : `"${request.ext}"`,
  );
  const page = selectPage(targets, request.page);
  const shown = { id: extension.id, name: extension.name };
  const where = { id: page.id, title: page.title, url: redactUrl(page.url, redactFloor(request.redact ?? [])) };
  try {
    await connection.send("Extensions.triggerAction", { id: extension.id, targetId: page.id });
    return { route: "cdp", extension: shown, page: where, popup: null, refusal: null };
  } catch (exc) {
    const refusal = exc instanceof Error ? exc.message : String(exc);
    const url = _popupOf(extension, how.readText, refusal);
    const { targetId } = await connection.send("Target.createTarget", { url });
    return { route: "popup", extension: shown, page: where, popup: { targetId: String(targetId), url }, refusal };
  }
}

/**
 * The popup URL of an extension for the fallback route.
 * @param {ExtensionInfo} extension
 * @param {(path: string) => string} readText
 * @param {string} refusal why the browser's own route was not used
 * @returns {string}
 * @throws {CdpError} when the extension has no folder to read or its action has no popup
 */
function _popupOf(extension, readText, refusal) {
  if (extension.path === null) {
    throw new CdpError(`${extension.name} is not an unpacked extension, so its popup is not known (${refusal})`);
  }
  const url = popupUrlOf(readText(_manifestPath(extension.path)), extension.id);
  if (url === null) {
    throw new CdpError(
      `this Chrome does not run an extension's action over the DevTools port (${refusal}) and the action of ` +
        `${extension.name} has no default_popup to open instead; click its toolbar button in the window`,
    );
  }
  return url;
}

/**
 * What a reload found for one extension.
 * @typedef {object} ReloadOutcome
 * @property {string} id
 * @property {string | null} loadError why it did not come back, when it did not
 * @property {ExtensionInfo | null} info its state after the reload; `null` when it is not loaded
 */

/**
 * Reload the extensions a request means from disk, and read each back.
 * @param {import("./cdp.mjs").CdpConnection} connection
 * @param {import("./protocol.mjs").Request} request
 * @returns {Promise<{reloaded: ReloadOutcome[], missing: string[]}>} `missing`: configured folders no loaded extension has
 * @throws {CdpError} when nothing matches
 */
export async function reloadExtensions(connection, request) {
  const select = request.ext ?? null;
  const paths = request.extensionPaths ?? [];
  const listed = await listExtensions(connection);
  const matches = matchExtensions(listed, { select, paths });
  const missing =
    select === null
      ? paths.filter((path) => !matches.some((item) => item.path !== null && samePath(path, item.path)))
      : [];
  if (matches.length === 0) {
    const loaded = listed.map((item) => `${item.name} (${item.id})`).join(", ") || "none";
    throw new CdpError(
      select === null
        ? `no unpacked extension is loaded${paths.length === 0 ? "" : ` from ${paths.join(", ")}`}; ` +
            "a Chrome started for extensions loads them: akmon tool browser restart"
        : `no extension matches "${select}"; loaded: ${loaded}`,
    );
  }
  const reloaded = await _inExtensionsPage(connection, _reloadScript(matches.map((item) => item.id)));
  if (!Array.isArray(reloaded)) {
    throw new CdpError("chrome://extensions did not answer a reload with a list");
  }
  return { reloaded, missing };
}
