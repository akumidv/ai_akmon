/**
 * The verbs that run and report on the project's Chrome: `status`, `start`, `stop`, `restart`. Each acts
 * only on this project's Chrome: a Chrome answering on the port is touched only when its process runs
 * with this project's profile (`ownership.mjs`), and a refusal names whose it is and the fix.
 */

import { spawn } from "node:child_process";
import fs from "node:fs";
import { posix } from "node:path";

import { attachedStatusCommand, readAttach, refuseInAttachMode } from "./attach.mjs";
import { findChrome, headlessReason, profileFolder, windowsSide } from "./chrome.mjs";
import { chromeCommandLines, closeBrowser, devtoolsJson, stopWindowsChrome } from "./devtools.mjs";
import { wslPath } from "./host.mjs";
import { checkPort, chromeOwnership } from "./ownership.mjs";
import { argumentsHaveCredentials, proxyPlan, recordableArguments, stripCredentials } from "./proxy.mjs";
import { BrowserError, extensionsProblemLine, readTextOrNull, requireExtensions } from "./settings.mjs";
import { pageTabs } from "./targets.mjs";
import { wiringOf } from "./wiring.mjs";
import { realWindows, windowsNodeLine, windowsNodeVersion } from "./windows.mjs";

/** How long `start` waits for DevTools to answer, and how long `stop` waits for it to stop, in polls of 500 ms. */
const _START_POLLS = 20;
const _STOP_POLLS = 10;
const _POLL_MS = 500;

/**
 * What a `start` recorded in `<browser dir>/launch.json`.
 * @typedef {object} LaunchRecord
 * @property {string} started ISO time
 * @property {string} [project] the project root the Chrome was started for, so another project names it right
 * @property {string} exe
 * @property {string} profile the profile as the Chrome process saw it
 * @property {number} port
 * @property {string} proxy what the proxy was, in words, with its credentials replaced
 * @property {boolean} [proxyCredentials] the proxy carried credentials, which the record does not keep
 * @property {boolean} headless
 * @property {string[]} [extensions] the unpacked extensions loaded with the Chrome, as the Chrome process saw the paths
 * @property {string[]} args the Chrome arguments, with the proxy's credentials replaced
 */

/**
 * @typedef {import("./context.mjs").Context} Context
 */

/**
 * The record of the last `start`, or `null`.
 * @param {Context} ctx
 * @returns {LaunchRecord | null}
 */
export function readLaunch(ctx) {
  try {
    /** @type {LaunchRecord} */
    const record = JSON.parse(fs.readFileSync(posix.join(ctx.project.browserDir, "launch.json"), "utf8"));
    // A record an older `start` wrote may hold credentials: they are never shown from it.
    return typeof record.proxy === "string" ? { ...record, proxy: stripCredentials(record.proxy) } : record;
  } catch {
    return null;
  }
}

/**
 * The Chrome the project would run, or `null` when there is none. A project that configures extensions
 * needs its Chrome for Testing (`testing` defaults to that): a branded Chrome found on the machine is not
 * the project's Chrome.
 * @param {Context} ctx
 * @param {{testing?: boolean}} [options] `testing`: only a Chrome that can load extensions counts
 * @returns {import("./chrome.mjs").ChromeFound | null}
 * @throws {BrowserError} when the configured Chrome does not exist
 */
export function chromeOf(ctx, options = {}) {
  return findChrome(ctx.host, {
    configured: ctx.settings.chrome,
    browserDir: ctx.project.browserDir,
    env: ctx.env,
    testing: options.testing ?? ctx.settings.extensions.length > 0,
  });
}

/**
 * The profile folder as the Chrome process sees it: a Windows path for a Windows Chrome under WSL.
 * @param {Context} ctx
 * @param {import("./chrome.mjs").ChromeFound} chrome
 * @returns {string}
 */
function _profileSeenBy(ctx, chrome) {
  const folder = profileFolder(ctx.project.browserDir, chrome, ctx.settings.profile);
  fs.mkdirSync(folder, { recursive: true });
  if (windowsSide(ctx.host, chrome.path) && folder.startsWith("/")) {
    return wslPath(folder, "windows");
  }
  return folder;
}

/**
 * The folders of the configured extensions as the Chrome process sees them: Windows paths for a Windows
 * Chrome under WSL.
 * @param {Context} ctx
 * @param {import("./chrome.mjs").ChromeFound} chrome
 * @returns {string[]}
 */
function _extensionsSeenBy(ctx, chrome) {
  const windows = windowsSide(ctx.host, chrome.path);
  return ctx.settings.extensions.map((folder) =>
    windows && folder.startsWith("/") ? wslPath(folder, "windows") : folder,
  );
}

/**
 * The profile folders that count as this project's when telling whose a Chrome is: the one it would use
 * now, the one of its last `start`, the setting, and the two defaults.
 * @param {Context} ctx
 * @returns {string[]}
 */
function _ownProfiles(ctx) {
  const dir = ctx.project.browserDir;
  const own = [
    ctx.settings.profile,
    readLaunch(ctx)?.profile,
    posix.join(dir, "chrome-profile"),
    posix.join(dir, "chrome-profile-cft"),
  ];
  try {
    const chrome = chromeOf(ctx);
    if (chrome !== null) {
      own.push(_profileSeenBy(ctx, chrome));
    }
  } catch {
    // No Chrome to say which profile it would use now: the recorded and default ones still tell.
  }
  return own.filter((profile) => typeof profile === "string");
}

/**
 * The Chrome answering on the project's port, checked: `null` when nothing answers.
 * @param {Context} ctx
 * @returns {Promise<import("./ownership.mjs").PortState | null>}
 */
export function portState(ctx) {
  return checkPort(ctx.port, {
    probe: (port) => devtoolsJson(ctx.host, port),
    owner: (port) => chromeOwnership(chromeCommandLines(ctx.host, port), _ownProfiles(ctx), readTextOrNull),
    project: ctx.project.name,
  });
}

/**
 * What `status` reports, as data: the same object `--json` prints.
 * @typedef {object} StatusReport
 * @property {"own"} mode
 * @property {string} project
 * @property {number} port
 * @property {string} browserURL the endpoint of the project's Chrome, for a run that connects to it
 * @property {boolean} running a Chrome answers on the port
 * @property {"ours" | "other-project" | "not-akmon" | "unknown" | null} owner whose it is; `null` when nothing answers
 * @property {string | null} refusal why the Chrome that answers is not driven
 * @property {string | null} browser the Chrome's version string
 * @property {{title: string, url: string}[]} tabs
 * @property {{used: string | null, now: string, restart: boolean}} proxy the proxy of the running Chrome, the one the environment says now, and whether they differ
 * @property {import("./wiring.mjs").Wiring} mcp
 * @property {string} node
 * @property {string | null} extensionsProblem the configured extension path that cannot be loaded and why, or `null`
 * @property {{version: string | null} | null} [windowsNode] Windows `node`, which the inspection verbs use for a Windows Chrome; `null` when the Chrome is not one
 */

/**
 * The ownership class of a Chrome for the report.
 * @param {import("./ownership.mjs").Ownership} owner
 * @returns {"ours" | "other-project" | "not-akmon" | "unknown"}
 */
function _ownerClass(owner) {
  if (owner.owner === "ours" || owner.owner === "unknown") {
    return owner.owner;
  }
  return owner.project === null ? "not-akmon" : "other-project";
}

/**
 * The open page tabs of the Chrome on the port.
 * @param {Context} ctx
 * @returns {Promise<{title: string, url: string}[]>}
 */
async function _tabs(ctx) {
  const list = (await devtoolsJson(ctx.host, ctx.port, "/json/list")) ?? [];
  return pageTabs(list, ctx.settings.redact);
}

/**
 * What is known about a Chrome that answers: its version, whose it is, its tabs and the proxy it was
 * started with.
 * @param {Context} ctx
 * @param {import("./ownership.mjs").PortState | null} found
 * @returns {Promise<Pick<StatusReport, "running" | "owner" | "refusal" | "browser" | "tabs">>}
 */
async function _answering(ctx, found) {
  if (found === null) {
    return { running: false, owner: null, refusal: null, browser: null, tabs: [] };
  }
  return {
    running: true,
    owner: _ownerClass(found.owner),
    refusal: found.refusal,
    browser: String(found.version["Browser"] ?? ""),
    tabs: found.owner.owner === "ours" ? await _tabs(ctx) : [],
  };
}

/**
 * Windows `node`, when the project's Chrome is a Windows program under WSL, which is what the inspection
 * verbs reach it through; `null` when it is not, or no Chrome is found.
 * @param {Context} ctx
 * @returns {Promise<{version: string | null} | null>}
 */
async function _windowsNode(ctx) {
  try {
    const chrome = chromeOf(ctx);
    if (chrome === null || !windowsSide(ctx.host, chrome.path)) {
      return null;
    }
  } catch {
    return null;
  }
  return { version: await windowsNodeVersion(realWindows()) };
}

/**
 * The proxy of a running Chrome against the one the environment says now. The credentials of a proxy are
 * not recorded, so a change of them alone shows only as the "has credentials" flag changing.
 * @param {import("./ownership.mjs").PortState | null} found
 * @param {LaunchRecord | null} launch the record of the last `start`
 * @param {import("./proxy.mjs").ProxyPlan} plan what a start would use now
 * @returns {StatusReport["proxy"]}
 */
export function proxyReport(found, launch, plan) {
  const used = found === null ? null : (launch?.proxy ?? null);
  const credentialsChanged = (launch?.proxyCredentials ?? false) !== argumentsHaveCredentials(plan.args);
  return {
    used,
    now: plan.describe,
    restart: found?.owner.owner === "ours" && (used !== plan.describe || credentialsChanged),
  };
}

/**
 * Collect the status of the project's browser.
 * @param {Context} ctx
 * @returns {Promise<StatusReport>}
 */
export async function collectStatus(ctx) {
  const found = await portState(ctx);
  const proxy = proxyReport(found, readLaunch(ctx), proxyPlan(ctx.env, ctx.settings.proxy));
  return {
    mode: "own",
    project: ctx.project.name,
    port: ctx.port,
    browserURL: `http://127.0.0.1:${ctx.port}`,
    ...(await _answering(ctx, found)),
    proxy,
    mcp: wiringOf(ctx.project.root),
    node: process.version,
    extensionsProblem: extensionsProblemLine(ctx.settings),
    windowsNode: await _windowsNode(ctx),
  };
}

/**
 * The lines `status` prints for a report.
 * @param {StatusReport} report
 * @returns {string[]}
 */
export function statusLines(report) {
  const lines = [];
  if (!report.running) {
    lines.push(
      `no Chrome DevTools on 127.0.0.1:${report.port} (project ${report.project}); start it: akmon tool browser start`,
    );
  } else if (report.refusal !== null) {
    lines.push(`not this project's browser: ${report.refusal}`);
  } else {
    lines.push(
      `Chrome ${report.browser} of project ${report.project} on 127.0.0.1:${report.port}, ${report.tabs.length} tab(s)`,
    );
    lines.push(..._proxyLines(report.proxy));
    lines.push(...report.tabs.map((tab) => `  ${tab.title.slice(0, 60).padEnd(60)} ${tab.url}`));
  }
  lines.push(`  mcp: ${report.mcp.state}, ${report.mcp.why}`);
  if (report.mcp.state !== "wired") {
    lines.push("  the Bash verbs work without it; for the MCP server run: akmon tool browser init");
  }
  lines.push(`  node: ${report.node}`);
  if (report.windowsNode) {
    lines.push(`  ${windowsNodeLine(report.windowsNode.version)}`);
  }
  if (report.extensionsProblem !== null) {
    lines.push(`  extensions: ${report.extensionsProblem}`);
  }
  return lines;
}

/**
 * The lines about the proxy of a running Chrome.
 * @param {StatusReport["proxy"]} proxy
 * @returns {string[]}
 */
function _proxyLines(proxy) {
  if (proxy.used === null) {
    return ["  proxy: unknown, this Chrome was not started by akmon; run `restart` to use the agent's proxy"];
  }
  const lines = [`  proxy: ${proxy.used}`];
  if (proxy.restart) {
    lines.push(`  NOTE: the environment now says "${proxy.now}"; run \`restart\` to apply it`);
  }
  return lines;
}

/**
 * `status [--json]`: exit 0 when this project's Chrome answers (or, in attach mode, the attached one),
 * 1 otherwise.
 * @param {Context} ctx
 * @param {{json: boolean}} options
 * @returns {Promise<number>}
 */
export async function statusCommand(ctx, options) {
  const attachment = readAttach(ctx.project.browserDir);
  if (attachment !== null) {
    return attachedStatusCommand(ctx, attachment, options);
  }
  const report = await collectStatus(ctx);
  if (options.json) {
    ctx.say(JSON.stringify(report, null, 2));
  } else {
    statusLines(report).forEach(ctx.say);
  }
  return report.owner === "ours" && report.extensionsProblem === null ? 0 : 1;
}

/**
 * Sleep.
 * @param {number} ms
 * @returns {Promise<void>}
 */
function _sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Whether DevTools answers within the polls.
 * @param {Context} ctx
 * @param {number} polls
 * @param {boolean} wanted wait for it to answer (`true`) or to stop answering (`false`)
 * @returns {Promise<boolean>} whether the wanted state was reached
 */
async function _waitFor(ctx, polls, wanted) {
  for (let poll = 0; poll < polls; poll += 1) {
    await _sleep(_POLL_MS);
    if (((await devtoolsJson(ctx.host, ctx.port)) !== null) === wanted) {
      return true;
    }
  }
  return false;
}

/**
 * The flags that load unpacked extensions and keep every other extension out: a comma-joined list, the way
 * Chrome takes it.
 * @param {readonly string[]} folders
 * @returns {string[]}
 */
export function extensionArguments(folders) {
  if (folders.length === 0) {
    return [];
  }
  const list = folders.join(",");
  return [`--load-extension=${list}`, `--disable-extensions-except=${list}`];
}

/** The schemes a `--url` may have: a page to open, never a switch. */
const _START_URL = /^(?:https?|file|about|data):/i;

/**
 * Refuse a `--url` that is not a page address. The URL is one more Chrome argument, so one that began with
 * `-` would be a switch (`--remote-debugging-address=0.0.0.0` would open DevTools to the network). The
 * scheme check is the whole defence: a `--` separator before the URL is not relied on, because no live
 * Chrome was probed for how it takes one.
 * @param {string | null} url
 * @throws {BrowserError} when the URL is not an `http:`, `https:`, `file:`, `about:` or `data:` address
 */
export function requireStartUrl(url) {
  if (url !== null && (!_START_URL.test(url) || !URL.canParse(url))) {
    throw new BrowserError(
      `--url must be an http:, https:, file:, about: or data: address, not ${JSON.stringify(url.slice(0, 80))}`,
    );
  }
}

/**
 * The `--url` as the one Chrome argument it is handed as: the normalized `href` (a `"` or a space of an
 * `http:` address is percent-encoded), and any `"` or whitespace an opaque `data:`/`about:` path keeps is
 * encoded too, so no quoting layer (WSL interop to a Windows Chrome) can split it into further switches.
 * @param {string} url an address `requireStartUrl` accepted
 * @returns {string}
 */
export function startUrlArgument(url) {
  return new URL(url).href.replace(/["\s]/g, (char) => encodeURIComponent(char));
}

/**
 * The arguments Chrome starts with.
 * @param {Context} ctx
 * @param {{profile: string, proxy: import("./proxy.mjs").ProxyPlan, headless: boolean, url: string | null, extensions?: readonly string[]}} plan
 *   `extensions` are the folders as the Chrome process spells them
 * @returns {string[]}
 */
export function chromeArguments(ctx, plan) {
  const args = [
    `--remote-debugging-port=${ctx.port}`,
    "--remote-debugging-address=127.0.0.1",
    `--user-data-dir=${plan.profile}`,
    "--no-first-run",
    "--no-default-browser-check",
    ...plan.proxy.args,
    ...extensionArguments(plan.extensions ?? []),
  ];
  if (plan.headless) {
    args.push("--headless=new");
  }
  if (plan.url !== null) {
    args.push(startUrlArgument(plan.url));
  }
  return args;
}

/**
 * Start Chrome detached, and say at once whether it could not be run.
 * @param {string} executable
 * @param {string[]} args
 * @returns {{failure: () => string | null}}
 */
function _spawnDetached(executable, args) {
  /** @type {string | null} */
  let failure = null;
  const child = spawn(executable, args, { detached: true, stdio: "ignore" });
  child.on("error", (error) => {
    failure = error.message;
  });
  child.unref();
  return { failure: () => failure };
}

/**
 * The running Chrome of the project is the project's own: refuse a foreign one, report an own one.
 * @param {Context} ctx
 * @param {import("./ownership.mjs").PortState | null} found
 * @returns {boolean} whether this project's Chrome already runs
 * @throws {BrowserError} when the Chrome on the port is not this project's
 */
function _alreadyRunning(ctx, found) {
  if (found === null) {
    return false;
  }
  if (found.refusal !== null) {
    throw new BrowserError(found.refusal);
  }
  const proxy = readLaunch(ctx)?.proxy ?? "unknown";
  ctx.say(
    `The Chrome of project ${ctx.project.name} is already listening on 127.0.0.1:${ctx.port} (proxy: ${proxy}). ` +
      "Use `restart` to relaunch it with the current environment.",
  );
  return true;
}

/**
 * What a `start` records: the launch itself, the port, the time and the project root, so another
 * project that meets this Chrome names its project from the record, not from the folder layout.
 * @param {Context} ctx
 * @param {{exe: string, profile: string, proxy: string, headless: boolean, extensions?: string[], args: string[]}} launch
 *   `proxy` and `args` as the proxy plan has them: the credentials are replaced here, nothing recorded holds one
 * @returns {LaunchRecord}
 */
export function launchRecord(ctx, launch) {
  return {
    started: new Date().toISOString(),
    project: ctx.project.root,
    port: ctx.port,
    ...launch,
    proxy: stripCredentials(launch.proxy),
    proxyCredentials: argumentsHaveCredentials(launch.args),
    args: recordableArguments(launch.args),
  };
}

/**
 * The one line for a start with no usable Chrome: a project that loads extensions needs Chrome for Testing,
 * which a branded Chrome found on the machine is not.
 * @param {Context} ctx
 * @returns {string}
 */
export function noChromeLine(ctx) {
  if (ctx.settings.extensions.length === 0) {
    return "Chrome not found; install it with the system, or into this project: akmon tool browser install";
  }
  const branded = chromeOf(ctx, { testing: false });
  const found =
    branded === null
      ? "no Chrome was found"
      : `only ${branded.path} was found, a branded Chrome that ignores --load-extension from 137 on`;
  return `the project loads extensions, which needs Chrome for Testing, and ${found}; install it into the project: akmon tool browser install`;
}

/**
 * `start [--url URL] [--headless]`: Chrome with the project's profile and a loopback DevTools port.
 * @param {Context} ctx
 * @param {{url: string | null, headless: boolean}} options
 * @returns {Promise<number>}
 * @throws {BrowserError} for a Chrome that is not the project's, or when none is found
 */
export async function startCommand(ctx, options) {
  refuseInAttachMode(ctx.project.browserDir, "start");
  requireStartUrl(options.url);
  requireExtensions(ctx.settings);
  if (_alreadyRunning(ctx, await portState(ctx))) {
    return 0;
  }
  const chrome = chromeOf(ctx);
  if (chrome === null) {
    throw new BrowserError(noChromeLine(ctx));
  }
  const profile = _profileSeenBy(ctx, chrome);
  const proxy = proxyPlan(ctx.env, ctx.settings.proxy);
  const reason = headlessReason(ctx.host, chrome.path, options.headless);
  const extensions = _extensionsSeenBy(ctx, chrome);
  const args = chromeArguments(ctx, { profile, proxy, headless: reason !== null, url: options.url, extensions });
  const launched = _spawnDetached(chrome.path, args);
  fs.mkdirSync(ctx.project.browserDir, { recursive: true });
  const record = launchRecord(ctx, {
    exe: chrome.path,
    profile,
    proxy: proxy.describe,
    headless: reason !== null,
    extensions,
    args,
  });
  fs.writeFileSync(posix.join(ctx.project.browserDir, "launch.json"), `${JSON.stringify(record, null, 2)}\n`);
  ctx.say(`Started the Chrome of project ${ctx.project.name}: ${chrome.path}`);
  ctx.say(`  profile: ${profile}\n  DevTools port: ${ctx.port} (127.0.0.1 only)\n  proxy: ${proxy.describe}`);
  extensions.forEach((folder) => ctx.say(`  extension: ${folder}`));
  if (reason !== null) {
    ctx.say(
      `  headless (${reason}): the user does not see this Chrome; describe the page to them, and a sign-in only the user can do (SSO, MFA) is not possible here`,
    );
  }
  return _reportStart(ctx, launched);
}

/**
 * Wait for the started Chrome and say whether it answers.
 * @param {Context} ctx
 * @param {{failure: () => string | null}} launched
 * @returns {Promise<number>}
 */
async function _reportStart(ctx, launched) {
  if (await _waitFor(ctx, _START_POLLS, true)) {
    ctx.say("Reachable. Sign in to what you need in that window; then ask the agent to work in it.");
    return 0;
  }
  const failure = launched.failure();
  ctx.say(
    failure === null
      ? `Chrome started but 127.0.0.1:${ctx.port} does not answer.`
      : `Chrome could not be run: ${failure}`,
  );
  return 1;
}

/**
 * Close this project's Chrome, wherever it runs.
 * @param {Context} ctx
 * @returns {Promise<void>}
 */
async function _closeChrome(ctx) {
  const launch = readLaunch(ctx);
  if (ctx.host.platform === "win32" || windowsSide(ctx.host, launch?.exe ?? "")) {
    stopWindowsChrome(ctx.host, launch?.profile ?? _ownProfiles(ctx)[0]);
    return;
  }
  const version = await devtoolsJson(ctx.host, ctx.port);
  if (version?.webSocketDebuggerUrl) {
    await closeBrowser(version.webSocketDebuggerUrl);
  }
}

/**
 * `stop`: close this project's Chrome (sign-ins stay in the profile); another Chrome is left running.
 * @param {Context} ctx
 * @returns {Promise<number>}
 */
export async function stopCommand(ctx) {
  refuseInAttachMode(ctx.project.browserDir, "stop");
  const found = await portState(ctx);
  if (found === null) {
    ctx.say(`no Chrome of project ${ctx.project.name} is running on 127.0.0.1:${ctx.port}`);
    return 0;
  }
  if (found.refusal !== null) {
    ctx.say(`left running: ${found.refusal}`);
    return 1;
  }
  await _closeChrome(ctx);
  const stopped = await _waitFor(ctx, _STOP_POLLS, false);
  ctx.say(
    stopped
      ? `stopped the Chrome of project ${ctx.project.name}`
      : `the Chrome of project ${ctx.project.name} still answers; close it by hand`,
  );
  return stopped ? 0 : 1;
}

/**
 * `restart [--url URL]`: stop and start again, to apply a changed proxy or port. A Chrome that is not
 * this project's is left alone and nothing is started.
 * @param {Context} ctx
 * @param {{url: string | null, headless: boolean}} options
 * @returns {Promise<number>}
 */
export async function restartCommand(ctx, options) {
  refuseInAttachMode(ctx.project.browserDir, "restart");
  requireStartUrl(options.url);
  requireExtensions(ctx.settings);
  const code = await stopCommand(ctx);
  return code === 0 ? startCommand(ctx, options) : code;
}
