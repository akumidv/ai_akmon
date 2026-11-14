/**
 * Which Chrome the project's browser runs, and on which profile. The lookup order is the project's
 * decision, not the machine's: what the user set, then what they already installed (PATH, the
 * platform's usual places, and under WSL the Windows side), and only then a Chrome for Testing that
 * `install` put into the project's local layer after the user agreed.
 */

import { posix } from "node:path";

import { BrowserError } from "./settings.mjs";

/** Names a Chrome or Chromium goes by on PATH. */
const _PATH_NAMES = ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser"];

/** The Chrome for Testing layout inside one `@puppeteer/browsers` install folder, by platform. */
const _TESTING_APP = "Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing";
const _PROJECT_EXECUTABLES = [
  "chrome-linux64/chrome",
  `chrome-mac-arm64/${_TESTING_APP}`,
  `chrome-mac-x64/${_TESTING_APP}`,
  "chrome-win64/chrome.exe",
];

/**
 * A found Chrome and where it came from.
 * @typedef {object} ChromeFound
 * @property {string} path the executable
 * @property {"configured" | "system" | "windows" | "project"} source
 */

/**
 * The folder `install` puts Chrome for Testing into, as `@puppeteer/browsers` lays it out:
 * `<this>/chrome/<platform>-<build>/`.
 * @param {string} browserDir
 * @returns {string}
 */
export function installFolder(browserDir) {
  return posix.join(browserDir, "chrome");
}

/**
 * The system's usual install paths of Chrome on a platform.
 * @param {string} platformName
 * @param {Record<string, string | undefined>} env
 * @returns {string[]}
 */
function _systemPaths(platformName, env) {
  if (platformName === "linux") {
    return ["/opt/google/chrome/chrome"];
  }
  if (platformName === "darwin") {
    return ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"];
  }
  if (platformName === "win32") {
    return [
      `${env["PROGRAMFILES"] ?? "C:\\Program Files"}\\Google\\Chrome\\Application\\chrome.exe`,
      `${env["LOCALAPPDATA"] ?? ""}\\Google\\Chrome\\Application\\chrome.exe`,
    ];
  }
  return [];
}

/**
 * The candidates of `names` on PATH. Under WSL the Windows folders it appends are left out: the
 * Windows Chrome is looked for on its own, through the registry.
 * @param {import("./host.mjs").Host} host
 * @returns {string[]}
 */
function _onPath(host) {
  const dirs = host.pathDirs.filter((dir) => !(host.isWsl && dir.startsWith("/mnt/")));
  const suffix = host.platform === "win32" ? ".exe" : "";
  return dirs.flatMap((dir) => _PATH_NAMES.map((name) => posix.join(dir, `${name}${suffix}`)));
}

/**
 * The Chrome for Testing executables an `install` left, the newest build last.
 * @param {import("./host.mjs").Host} host
 * @param {string} browserDir
 * @returns {string[]}
 */
function _projectCandidates(host, browserDir) {
  return host
    .subdirectories(posix.join(installFolder(browserDir), "chrome"))
    .flatMap((dir) => _PROJECT_EXECUTABLES.map((executable) => posix.join(dir, executable)));
}

/**
 * Where Windows says Chrome is installed, when this side can ask (Windows, or WSL).
 * @param {import("./host.mjs").Host} host
 * @returns {string | null}
 */
function _windowsChrome(host) {
  return host.isWsl || host.platform === "win32" ? host.windowsAppPath("chrome.exe") : null;
}

/**
 * The Chrome to use, or `null` when there is none. With `testing` (a project that loads extensions) only a
 * Chrome the user named or the project's own Chrome for Testing counts: a branded Chrome from 137 on ignores
 * `--load-extension`, so one found on the machine is not used, and the project's build is preferred to it.
 * @param {import("./host.mjs").Host} host
 * @param {{configured: string | null, browserDir: string, env: Record<string, string | undefined>, testing?: boolean}} where
 *   `configured` is the `chrome` setting, `browserDir` the project's browser state
 * @returns {ChromeFound | null}
 * @throws {BrowserError} when the configured path does not exist
 */
export function findChrome(host, where) {
  if (where.configured !== null) {
    if (!host.exists(where.configured)) {
      throw new BrowserError(
        `the configured Chrome ${where.configured} does not exist (AKMON_BROWSER_CHROME or [browser] chrome)`,
      );
    }
    return { path: where.configured, source: "configured" };
  }
  if (where.testing === true) {
    return _projectChrome(host, where.browserDir);
  }
  const system = [..._onPath(host), ..._systemPaths(host.platform, where.env)].find((path) => host.exists(path));
  if (system !== undefined) {
    return { path: system, source: "system" };
  }
  const windows = _windowsChrome(host);
  if (windows !== null) {
    return { path: windows, source: host.isWsl ? "windows" : "system" };
  }
  return _projectChrome(host, where.browserDir);
}

/**
 * The newest Chrome for Testing `install` left in the project, or `null`.
 * @param {import("./host.mjs").Host} host
 * @param {string} browserDir
 * @returns {ChromeFound | null}
 */
function _projectChrome(host, browserDir) {
  const own = _projectCandidates(host, browserDir)
    .reverse()
    .find((path) => host.exists(path));
  return own === undefined ? null : { path: own, source: "project" };
}

/**
 * Whether a Chrome path is a Windows program started from WSL: its paths must be Windows paths.
 * @param {import("./host.mjs").Host} host
 * @param {string} chromePath
 * @returns {boolean}
 */
export function windowsSide(host, chromePath) {
  return host.isWsl && /\.exe$/i.test(chromePath);
}

/**
 * The profile folder of the project's Chrome. Chrome refuses remote debugging on its default
 * profile, so the project has its own, and a Chrome for Testing a profile of its own again:
 * cookies are encrypted per build, and a profile one build wrote the other cannot read. A `profile`
 * setting wins as it stands.
 * @param {string} browserDir
 * @param {ChromeFound} chrome
 * @param {string | null} configured the `profile` setting
 * @returns {string}
 */
export function profileFolder(browserDir, chrome, configured) {
  if (configured !== null) {
    return configured;
  }
  return posix.join(browserDir, chrome.source === "project" ? "chrome-profile-cft" : "chrome-profile");
}

/**
 * Why Chrome should start without a window, or `null` for a normal start: nobody could see a window
 * on Linux without a graphical session, unless it is a Windows Chrome under WSL.
 * @param {import("./host.mjs").Host} host
 * @param {string} chromePath
 * @param {boolean} requested `--headless` was given
 * @returns {string | null}
 */
export function headlessReason(host, chromePath, requested) {
  if (requested) {
    return "requested with --headless";
  }
  if (!host.display && !windowsSide(host, chromePath)) {
    return "no graphical session";
  }
  return null;
}
