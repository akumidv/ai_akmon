/**
 * `install [--yes] [--for-extensions]`: Chrome for Testing into the project's local layer, only when no
 * Chrome is found (for a project that loads extensions, or with `--for-extensions`: when the project has no
 * Chrome for Testing of its own, a branded Chrome on the machine notwithstanding, because a branded Chrome from
 * 137 on ignores `--load-extension`) and only after the user agreed (ADR 0032/D04). It is `@puppeteer/browsers`, pinned and run through
 * `npx`, so the tool adds no npm dependency. When the download fails, or the system lacks a library
 * Chrome needs, the tool prints the exact command for the user to run and stops: it never installs a
 * runtime and never elevates privileges itself.
 */

import { spawnSync } from "node:child_process";
import { posix } from "node:path";

import { installFolder } from "./chrome.mjs";
import { LOCAL_TIMEOUT_MS } from "./host.mjs";
import { chromeOf } from "./lifecycle.mjs";
import { requireExtensions } from "./settings.mjs";

/** The pinned downloader: an exact version, so the tool's behaviour does not move under the user. */
export const BROWSERS_PIN = "@puppeteer/browsers@3.2.7";

/** The size of the download, said in the plan. */
const _SIZE_NOTE = "about 200 MB";

/**
 * @typedef {import("./context.mjs").Context} Context
 */

/**
 * The command that installs Chrome for Testing into `folder`.
 * @param {string} folder
 * @returns {{command: string, args: string[]}}
 */
export function installCommandOf(folder) {
  return { command: "npx", args: ["--yes", BROWSERS_PIN, "install", "chrome@stable", "--path", folder] };
}

/**
 * The command as a user types it.
 * @param {{command: string, args: string[]}} spec
 * @returns {string}
 */
function _spelled(spec) {
  return [spec.command, ...spec.args].join(" ");
}

/**
 * The lines of the install plan.
 * @param {string} folder
 * @returns {string[]}
 */
export function planLines(folder) {
  return [
    "plan only; nothing is installed without --yes:",
    `  what:    Chrome for Testing (stable), fetched by ${BROWSERS_PIN} through npx`,
    `  where:   ${folder} (inside the project's local layer; nothing system-wide)`,
    `  size:    ${_SIZE_NOTE} to download`,
    `  command: ${_spelled(installCommandOf(folder))}`,
    "run it from here with: akmon tool browser install --yes",
  ];
}

/** How long the download may take before it is given up on: generous, because a build is large and a proxy slow. */
export const INSTALL_TIMEOUT_MS = 15 * 60 * 1000;

/**
 * Why a finished install command failed, in words: the time limit, the error that stopped it, or its exit.
 * @param {{status: number | null, error?: Error & {code?: string}}} run
 * @returns {string}
 */
export function failureCause(run) {
  if (run.error?.code === "ETIMEDOUT") {
    return `it did not finish within ${INSTALL_TIMEOUT_MS / 60_000} minutes and was stopped`;
  }
  return run.error?.message ?? `exit ${run.status}`;
}

/**
 * The shared libraries a Linux binary cannot load, from `ldd`.
 * @param {string} platformName
 * @param {string} binary
 * @returns {string[]}
 */
export function missingLibraries(platformName, binary) {
  if (platformName !== "linux") {
    return [];
  }
  const result = spawnSync("ldd", [binary], { encoding: "utf8", timeout: LOCAL_TIMEOUT_MS });
  return [...(result.stdout ?? "").matchAll(/^\s*(\S+) => not found/gm)].map((match) => match[1]);
}

/**
 * The command the user runs to install what a Chrome for Testing build needs, from the dependency list
 * the build ships beside its executable.
 * @param {string} executable
 * @returns {string}
 */
export function librariesCommand(executable) {
  const deps = posix.join(posix.dirname(executable), "deb.deps");
  return `sudo apt-get satisfy -y --no-install-recommends "$(paste -sd, '${deps}')"`;
}

/**
 * After a successful download: the Chrome that is there now, and what it still lacks.
 * @param {Context} ctx
 * @param {boolean} testing the Chrome wanted is the project's Chrome for Testing
 * @returns {number}
 */
function _verifyInstalled(ctx, testing) {
  const chrome = chromeOf(ctx, { testing });
  if (chrome === null) {
    ctx.say(
      `the download finished but no Chrome was found where it should be; look in ${installFolder(ctx.project.browserDir)}`,
    );
    return 1;
  }
  const missing = missingLibraries(ctx.host.platform, chrome.path);
  if (missing.length > 0) {
    ctx.say(`installed ${chrome.path}, but these system libraries are missing: ${missing.join(", ")}`);
    ctx.say(
      `akmon does not elevate privileges. Run this yourself, then start again:\n  ${librariesCommand(chrome.path)}`,
    );
    return 1;
  }
  ctx.say(`installed: ${chrome.path}\nstart it: akmon tool browser start`);
  if (testing && ctx.settings.extensions.length === 0 && ctx.settings.extensionsProblem === null) {
    ctx.say("it is used for extensions: list the unpacked extension folders under [browser] extensions");
  }
  return 0;
}

/**
 * `install [--yes] [--for-extensions]`.
 * @param {Context} ctx
 * @param {{yes: boolean, forExtensions?: boolean}} options
 * @returns {number} the exit code: 0 when Chrome is there, 1 when it is not or still cannot run
 * @throws {BrowserError} without `--for-extensions`, when a configured extension path is not an unpacked extension
 */
export function installCommand(ctx, options) {
  if (options.forExtensions !== true) {
    requireExtensions(ctx.settings);
  }
  const testing = options.forExtensions === true || ctx.settings.extensions.length > 0;
  const found = chromeOf(ctx, { testing });
  if (found !== null) {
    ctx.say(`Chrome ${testing ? "for Testing " : ""}is available (${found.source}): ${found.path}; nothing to install`);
    return 0;
  }
  const folder = installFolder(ctx.project.browserDir);
  if (testing) {
    ctx.say(
      "for extensions: Chrome for Testing is installed beside any other Chrome, because a branded Chrome from 137 on ignores --load-extension",
    );
  }
  if (!options.yes) {
    planLines(folder).forEach(ctx.say);
    return 0;
  }
  const spec = installCommandOf(folder);
  const run = spawnSync(spec.command, spec.args, {
    stdio: ["ignore", 2, 2],
    shell: ctx.host.platform === "win32",
    timeout: INSTALL_TIMEOUT_MS,
  });
  if (run.status !== 0) {
    const cause = failureCause(run);
    ctx.say(`the install failed (${cause}). Run it yourself, then start again:\n  ${_spelled(spec)}`);
    return 1;
  }
  return _verifyInstalled(ctx, testing);
}
