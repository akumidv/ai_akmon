/**
 * The parts of the tool that touch a running Chrome: ask its DevTools port, close it, and read the
 * process table to say whose it is. Everything here reads the real machine, so it is exercised by
 * the tool run by hand and by the stand-in Chrome of the launcher test, never by a unit test.
 */

import { execFileSync } from "node:child_process";
import fs from "node:fs";

import { LOCAL_TIMEOUT_MS } from "./host.mjs";

/** How long a DevTools request or a PowerShell probe may take, in milliseconds. */
const _REQUEST_MS = 2000;
const _POWERSHELL_MS = 30_000;
/** How long `Browser.close` is given to take effect. */
const _CLOSE_MS = 5000;

/**
 * @typedef {import("./host.mjs").Host} Host
 */

/**
 * The PowerShell to run, by side: `powershell.exe` from WSL, `powershell` on Windows.
 * @param {Host} host
 * @returns {string}
 */
function _powershell(host) {
  return host.isWsl ? "powershell.exe" : "powershell";
}

/**
 * Run a PowerShell command and return its output, or `null` when it fails.
 * @param {Host} host
 * @param {string} script
 * @returns {string | null}
 */
function _runPowerShell(host, script) {
  try {
    return execFileSync(_powershell(host), ["-NoProfile", "-Command", script], {
      encoding: "utf8",
      stdio: ["ignore", "pipe", "ignore"],
      timeout: _POWERSHELL_MS,
      cwd: host.isWsl ? "/mnt/c" : undefined,
    });
  } catch {
    return null;
  }
}

/**
 * Under WSL a Windows Chrome's loopback port is reachable only from the Windows side.
 * @param {Host} host
 * @param {string} url
 * @returns {Record<string, unknown> | unknown[] | null}
 */
function _probeViaWindows(host, url) {
  const out = _runPowerShell(host, `(Invoke-WebRequest '${url}' -UseBasicParsing -TimeoutSec 2).Content`);
  try {
    return out === null ? null : JSON.parse(out);
  } catch {
    return null;
  }
}

/**
 * One DevTools JSON answer from `127.0.0.1:<port><path>`, or `null` when nothing answers there.
 * @param {Host} host
 * @param {number} port
 * @param {string} [path]
 * @returns {Promise<any>}
 */
export async function devtoolsJson(host, port, path = "/json/version") {
  const url = `http://127.0.0.1:${port}${path}`;
  try {
    const response = await fetch(url, { signal: AbortSignal.timeout(_REQUEST_MS) });
    if (response.ok) {
      return await response.json();
    }
  } catch {
    // Not answering on this side of the machine.
  }
  return host.isWsl ? _probeViaWindows(host, url) : null;
}

/**
 * The command lines of the processes `keep` accepts, on this side of the machine.
 * @param {string} platformName
 * @param {(line: string, args: string[] | null) => boolean} keep
 * @returns {{lines: string[], complete: boolean}}
 */
function _localCommandLines(platformName, keep) {
  /** @type {string[]} */
  const lines = [];
  if (platformName === "linux") {
    for (const pid of fs.readdirSync("/proc").filter((name) => /^\d+$/.test(name))) {
      try {
        const args = fs.readFileSync(`/proc/${pid}/cmdline`, "utf8").split("\0").filter(Boolean);
        if (keep(args.join(" "), args)) {
          lines.push(args.join(" "));
        }
      } catch {
        // Gone already, or not ours to read.
      }
    }
    return { lines, complete: true };
  }
  if (platformName === "darwin") {
    try {
      const out = execFileSync("ps", ["-axww", "-o", "command="], { encoding: "utf8", timeout: LOCAL_TIMEOUT_MS });
      return { lines: out.split("\n").filter((line) => keep(line, null)), complete: true };
    } catch {
      return { lines, complete: false };
    }
  }
  return { lines, complete: true };
}

/**
 * The command lines of `chrome.exe` processes whose command line holds `fragment`, on the Windows side.
 * @param {Host} host
 * @param {string} fragment
 * @returns {{lines: string[], complete: boolean}}
 */
function _windowsCommandLines(host, fragment) {
  const needle = fragment.replace(/'/g, "''");
  const script =
    `Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" | ` +
    `Where-Object { $_.CommandLine -like '*${needle}*' } | ForEach-Object { $_.CommandLine }`;
  const out = _runPowerShell(host, script);
  if (out === null) {
    return { lines: [], complete: false };
  }
  return { lines: out.split(/\r?\n/).filter(Boolean), complete: true };
}

/**
 * The command lines of the Chrome processes listening for DevTools on `port`, wherever they run:
 * /proc on Linux, `ps` on macOS, the process table through PowerShell on Windows and, under WSL, on
 * its Windows side too.
 * @param {Host} host
 * @param {number} port
 * @returns {string[]}
 */
export function chromeCommandLines(host, port) {
  const flag = `--remote-debugging-port=${port}`;
  const local = _localCommandLines(host.platform, (line, args) => (args ? args.includes(flag) : line.includes(flag)));
  const windows = host.isWsl || host.platform === "win32" ? _windowsCommandLines(host, flag) : { lines: [] };
  // PowerShell's `-like` takes a longer port (`...=92220` for `...=9222`) too: only the exact flag counts.
  const exact = new RegExp(`${flag}(?!\\d)`);
  return [...local.lines, ...windows.lines.filter((line) => exact.test(line))];
}

/**
 * Whether a Chrome command line runs with exactly this profile folder: `--user-data-dir=<profile>` ending at
 * the end of the line, a space or a quote. A prefix does not count (`chrome-profile` is not
 * `chrome-profile-cft`), and a character such as `[` in the path is itself, never a wildcard.
 * @param {string} commandLine
 * @param {string} profile the profile folder as the Chrome process spells it
 * @returns {boolean}
 */
export function holdsProfile(commandLine, profile) {
  const escaped = profile.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return new RegExp(`--user-data-dir=["']?${escaped}["']?(?:\\s|$)`, "i").test(commandLine);
}

/**
 * The process ids, among `ProcessId<TAB>CommandLine` lines, of the processes that run with `profile`.
 * @param {string} listing
 * @param {string} profile
 * @returns {number[]}
 */
export function processesOfProfile(listing, profile) {
  /** @type {number[]} */
  const ids = [];
  for (const line of listing.split(/\r?\n/)) {
    const tab = line.indexOf("\t");
    if (tab > 0 && /^\d+$/.test(line.slice(0, tab)) && holdsProfile(line.slice(tab + 1), profile)) {
      ids.push(Number(line.slice(0, tab)));
    }
  }
  return ids;
}

/**
 * Close the project's Windows Chrome: the processes whose command line carries exactly its profile. The
 * match is made here, not by a PowerShell `-like`, whose wildcards would also take the other profile
 * of the project (`chrome-profile-cft`) or read `[` in a path as a pattern.
 * @param {Host} host
 * @param {string} profile the profile folder as Windows sees it
 */
export function stopWindowsChrome(host, profile) {
  const listing = _runPowerShell(
    host,
    `Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" | ` +
      `ForEach-Object { "$($_.ProcessId)" + [char]9 + $_.CommandLine }`,
  );
  const ids = listing === null ? [] : processesOfProfile(listing, profile);
  if (ids.length > 0) {
    _runPowerShell(host, `Stop-Process -Id ${ids.join(",")} -Force -ErrorAction SilentlyContinue`);
  }
}

/**
 * Ask a Chrome to close through its DevTools WebSocket, and wait for it to do so.
 * @param {string} webSocketUrl
 * @returns {Promise<void>}
 */
export function closeBrowser(webSocketUrl) {
  return new Promise((resolve) => {
    const socket = new WebSocket(webSocketUrl);
    socket.onopen = () => socket.send(JSON.stringify({ id: 1, method: "Browser.close" }));
    socket.onclose = () => resolve();
    socket.onerror = () => resolve();
    setTimeout(resolve, _CLOSE_MS);
  });
}

/**
 * Whether DevTools answers on `127.0.0.1:<port>` from this side of the machine, without the Windows
 * fallback of `devtoolsJson`: under WSL it tells a Chrome this side reaches from one only Windows does.
 * @param {number} port
 * @returns {Promise<boolean>}
 */
export async function answersHere(port) {
  try {
    const response = await fetch(`http://127.0.0.1:${port}/json/version`, { signal: AbortSignal.timeout(_REQUEST_MS) });
    return response.ok;
  } catch {
    return false;
  }
}
