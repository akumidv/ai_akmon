/**
 * The words of the inspection verbs: what each prints for what the Chrome side collected (`ops.mjs`).
 * Pure functions from a value to lines, so a test reads them without a browser.
 */

/**
 * @typedef {import("./targets.mjs").Target} Target
 * @typedef {import("./ops.mjs").OutlineLine} OutlineLine
 * @typedef {import("./ops.mjs").LogEntry} LogEntry
 * @typedef {import("./ops.mjs").NetEntry} NetEntry
 */

/**
 * One row of `pages`.
 * @typedef {object} PageRow
 * @property {number | null} index the number `--page` takes; `null` for a target that is not a page
 * @property {string} id
 * @property {string} type
 * @property {string} title
 * @property {string} url
 */

/**
 * The rows of `pages`: the page targets numbered in Chrome's order, and with `all` the others after them.
 * @param {readonly Target[]} targets
 * @param {boolean} all
 * @returns {PageRow[]}
 */
export function pageRows(targets, all) {
  const pages = targets.filter((target) => target.type === "page");
  const rows = pages.map((target, index) => ({ index, ...target }));
  const others = all
    ? targets.filter((target) => target.type !== "page").map((target) => ({ index: null, ...target }))
    : [];
  return [...rows, ...others];
}

/**
 * The lines `pages` prints.
 * @param {readonly PageRow[]} rows
 * @returns {string[]}
 */
export function pageLines(rows) {
  if (rows.length === 0) {
    return ["no open page"];
  }
  return rows.map(
    (row) =>
      `${String(row.index ?? "-").padStart(2)}  ${row.id}  ${row.type.padEnd(15)}  ${_clip(row.title, 50).padEnd(50)}  ${row.url}`,
  );
}

/**
 * @param {string} text
 * @param {number} limit
 * @returns {string}
 */
function _clip(text, limit) {
  return text.length > limit ? `${text.slice(0, limit - 1)}…` : text;
}

/**
 * The lines `snapshot` prints: one per node, indented by depth, `role "name" [value]`.
 * @param {{lines: OutlineLine[], total: number, truncated: boolean}} outline
 * @returns {string[]}
 */
export function outlineLines(outline) {
  const lines = outline.lines.map((line) => {
    const name = line.name === "" ? "" : ` ${JSON.stringify(line.name)}`;
    const value = line.value === "" ? "" : ` [${line.value}]`;
    return `${"  ".repeat(line.depth)}${line.role}${name}${value}`;
  });
  if (outline.truncated) {
    lines.push(
      `… ${outline.total - outline.lines.length} more nodes not shown (${outline.total} in all); raise --max-nodes`,
    );
  }
  return lines;
}

/**
 * The text `eval` prints for a result: a string as it is (as JSON with `json`), anything else as JSON.
 * @param {{type: string, value?: unknown, unserializable?: string, description?: string}} result
 * @param {boolean} json
 * @returns {string}
 */
export function evalText(result, json) {
  if (result.unserializable !== undefined) {
    return result.unserializable;
  }
  if (result.value === undefined) {
    return json ? "null" : (result.description ?? result.type);
  }
  if (typeof result.value === "string" && !json) {
    return result.value;
  }
  return JSON.stringify(result.value, null, json ? undefined : 2);
}

/**
 * The lines `logs` prints: a relative time, the source in brackets (`page`, `extension`, `sw`, `popup`), the
 * kind of line, then its text.
 * @param {readonly LogEntry[]} entries
 * @returns {string[]}
 */
export function logLines(entries) {
  return entries.map((entry) => {
    const time = `${entry.t < 0 ? "-" : "+"}${Math.abs(entry.t).toFixed(2)}s`;
    return `${time.padStart(9)} [${entry.source}] ${entry.tag}: ${entry.text}`;
  });
}

/**
 * Bytes as a short size.
 * @param {number | null} bytes
 * @returns {string}
 */
function _size(bytes) {
  if (bytes === null) {
    return "-";
  }
  return bytes < 1024 ? `${bytes}B` : `${(bytes / 1024).toFixed(1)}kB`;
}

/**
 * The lines `net` prints: method, status or failure, type, size, time, URL; with `bodies` each body under its line.
 * @param {readonly NetEntry[]} entries
 * @param {boolean} bodies print the bodies
 * @returns {string[]}
 */
export function netLines(entries, bodies) {
  return entries.flatMap((entry) => (bodies ? [_netHead(entry), ..._bodyLines(entry)] : [_netHead(entry)]));
}

/**
 * The line of one request.
 * @param {NetEntry} entry
 * @returns {string}
 */
function _netHead(entry) {
  const result = entry.failure === null ? String(entry.status ?? "-") : `FAILED ${entry.failure}`;
  const time = entry.ms === null ? "-" : `${entry.ms}ms`;
  return `${(entry.method || "?").padEnd(6)} ${result}  ${entry.type || "-"}  ${entry.mime || "-"}  ${_size(entry.size)}  ${time}  ${entry.url}`;
}

/**
 * The line under a request that says what its body is, or why there is none; nothing for a request
 * whose body was not looked for.
 * @param {NetEntry} entry
 * @returns {string[]}
 */
function _bodyLines(entry) {
  if (entry.body !== undefined) {
    return [`    body${entry.bodyTruncated ? " (cut)" : ""}: ${entry.body}`];
  }
  return entry.bodyNote === undefined ? [] : [`    no body: ${entry.bodyNote}`];
}

/**
 * The lines `ext list` prints: one per extension, then what is wrong with it.
 * @param {readonly (import("./extension-cdp.mjs").ExtensionInfo & {configured: boolean})[]} extensions
 * @returns {string[]}
 */
export function extensionLines(extensions) {
  if (extensions.length === 0) {
    return ["no extension is loaded"];
  }
  return extensions.flatMap((item) => {
    const where = item.unpacked ? `${item.configured ? "configured" : "unpacked"} ${item.path ?? ""}` : "installed";
    return [
      `${item.id}  ${item.state.padEnd(8)}  ${item.name} ${item.version}  (${where})`,
      ...item.disableReasons.map((reason) => `    disabled: ${reason}`),
      ...item.errors.map((error) => `    manifest error: ${error}`),
    ];
  });
}

/**
 * The lines `ext reload` prints: what each extension is after the reload, and the load error of one that
 * did not come back.
 * @param {{reloaded: import("./extension-cdp.mjs").ReloadOutcome[], missing: string[]}} result
 * @returns {string[]}
 */
export function reloadLines(result) {
  const lines = result.reloaded.flatMap((outcome) => {
    const { info } = outcome;
    const head =
      info === null
        ? `${outcome.id}  NOT LOADED`
        : `${info.id}  ${info.state}  ${info.name} ${info.version}${info.enabled ? "" : "  (not running)"}`;
    return [
      head,
      ...(outcome.loadError === null ? [] : [`    load error: ${outcome.loadError}`]),
      ...(info?.disableReasons ?? []).map((reason) => `    disabled: ${reason}`),
      ...(info?.errors ?? []).map((error) => `    manifest error: ${error}`),
    ];
  });
  return [
    ...lines,
    ...result.missing.map(
      (path) =>
        `not loaded: ${path}; the Chrome did not load it (a manifest error, or a Chrome that ignores --load-extension); fix it, then: akmon tool browser restart`,
    ),
  ];
}

/**
 * Whether a reload left every extension enabled and without a load error.
 * @param {{reloaded: import("./extension-cdp.mjs").ReloadOutcome[], missing: string[]}} result
 * @returns {boolean}
 */
export function reloadSucceeded(result) {
  return (
    result.missing.length === 0 &&
    result.reloaded.every((outcome) => outcome.loadError === null && outcome.info?.enabled === true)
  );
}

/**
 * The lines `ext action` prints, saying plainly which route ran and, on the popup route, what it lacks.
 * @param {import("./extension-cdp.mjs").ActionOutcome} outcome
 * @returns {string[]}
 */
export function actionLines(outcome) {
  const { extension, page } = outcome;
  if (outcome.route === "cdp") {
    return [`triggered the action of ${extension.name} (${extension.id}) on ${page.title || page.url} [${page.id}]`];
  }
  return [
    `opened the popup of ${extension.name} (${extension.id}) in a new tab: ${outcome.popup?.url} [${outcome.popup?.targetId}]`,
    `NOTE: this Chrome does not run an extension's action over the DevTools port (${outcome.refusal}), so the popup`,
    `is a page of its own: it lacks the active-tab context, and what it reads as "the current tab" is that tab,`,
    `not ${page.url}. Work in it with --target popup.`,
  ];
}

/**
 * The lines `selectors` prints: one per name, the selector that matched, then any selector the browser rejected.
 * @param {readonly import("./selectors.mjs").SelectorFinding[]} findings
 * @returns {string[]}
 */
export function selectorLines(findings) {
  return findings.flatMap((finding) => {
    const count = finding.index === null ? 0 : finding.counts[finding.index];
    const status =
      finding.status === "matched"
        ? "matched"
        : finding.status === "fallback"
          ? `matched by fallback ${finding.index}`
          : "missing";
    const found = finding.selector === null ? "" : `  ${finding.selector} (${count})`;
    return [
      `${status.padEnd(22)} ${finding.name}${found}`,
      ...finding.errors.map((error) => `    rejected ${error.selector}: ${error.message}`),
    ];
  });
}
