/**
 * The machine the tool runs on, as a value: the platform, the environment, and the few questions
 * the Chrome lookup asks of the file system. The real one is built once, at the entry point; the
 * pure modules take it as a parameter, so a test hands them a fake and touches nothing.
 */

import { spawnSync } from "node:child_process";
import fs from "node:fs";
import { platform } from "node:os";

/** How long a local helper program (`wslpath`, `reg.exe`, `ps`, `ldd`) may take before it is given up on, in milliseconds. */
export const LOCAL_TIMEOUT_MS = 10_000;

/**
 * A path in the other side's spelling, through `wslpath`: the Windows form of a Linux path, or the reverse.
 * @param {string} path
 * @param {"windows" | "linux"} to the side the answer is spelled for
 * @returns {string}
 * @throws {Error} when `wslpath` fails or does not answer in time
 */
export function wslPath(path, to) {
  const flag = to === "windows" ? "-w" : "-u";
  const run = spawnSync("wslpath", [flag, path], { encoding: "utf8", timeout: LOCAL_TIMEOUT_MS });
  if (run.error !== undefined || run.status !== 0) {
    const cause = run.error?.message ?? (run.stderr.trim() || `exit ${run.status}`);
    throw new Error(`wslpath ${flag} ${JSON.stringify(path)} failed: ${cause}`);
  }
  return run.stdout.trim();
}

/**
 * @typedef {object} Host
 * @property {string} platform `process.platform`
 * @property {boolean} isWsl Linux under WSL: Windows programs are reached through interop
 * @property {boolean} display a graphical session exists (always true off Linux; WSLg counts)
 * @property {string[]} pathDirs the directories of `PATH`
 * @property {(path: string) => boolean} exists
 * @property {(dir: string) => string[]} subdirectories the sub-folders of `dir`, sorted; empty when it is absent
 * @property {(exe: string) => string | null} windowsAppPath where Windows says `exe` is installed, as a path on this side
 */

/**
 * Whether this Linux is WSL, read from the kernel's version string.
 * @returns {boolean}
 */
function _wsl() {
  if (platform() !== "linux") {
    return false;
  }
  try {
    return /microsoft/i.test(fs.readFileSync("/proc/version", "utf8"));
  } catch {
    return false;
  }
}

/**
 * The App Paths default value of `exe` in one registry hive, as Windows spells it, or `undefined`.
 * @param {boolean} wsl
 * @param {string} hive
 * @param {string} exe
 * @returns {string | undefined}
 */
function _registryValue(wsl, hive, exe) {
  const key = `${hive}\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\App Paths\\${exe}`;
  const query = spawnSync(wsl ? "reg.exe" : "reg", ["query", key, "/ve"], {
    encoding: "utf8",
    cwd: wsl ? "/mnt/c" : undefined,
    timeout: LOCAL_TIMEOUT_MS,
  });
  return (query.stdout ?? "").match(/REG_(?:EXPAND_)?SZ\s+"?([^"\r\n]+?)"?\s*$/m)?.[1];
}

/**
 * A Windows path as this side spells it, or `undefined` when `wslpath` does not answer.
 * @param {string} windows
 * @returns {string | undefined}
 */
function _toLinux(windows) {
  try {
    return wslPath(windows, "linux");
  } catch {
    return undefined;
  }
}

/**
 * Where Windows keeps a program's install location (App Paths, machine then user), as a path on this
 * side: a WSL path under WSL.
 * @param {boolean} wsl
 * @param {string} exe
 * @returns {string | null}
 */
function _registryPath(wsl, exe) {
  for (const hive of ["HKLM", "HKCU"]) {
    const windows = _registryValue(wsl, hive, exe);
    const path = windows && wsl ? _toLinux(windows) : windows;
    if (path && fs.existsSync(path)) {
      return path;
    }
  }
  return null;
}

/**
 * The real machine.
 * @param {Record<string, string | undefined>} env
 * @returns {Host}
 */
export function realHost(env) {
  const wsl = _wsl();
  const os = platform();
  const windowsHere = os === "win32" || wsl;
  return Object.freeze({
    platform: os,
    isWsl: wsl,
    display: os !== "linux" || Boolean(env["DISPLAY"] || env["WAYLAND_DISPLAY"]),
    pathDirs: (env["PATH"] ?? "").split(os === "win32" ? ";" : ":").filter(Boolean),
    exists: (path) => fs.existsSync(path),
    subdirectories: (dir) =>
      fs.existsSync(dir)
        ? fs
            .readdirSync(dir, { withFileTypes: true })
            .filter((entry) => entry.isDirectory())
            .map((entry) => entry.name)
            .sort()
            .map((name) => `${dir}/${name}`)
        : [],
    windowsAppPath: (exe) => (windowsHere ? _registryPath(wsl, exe) : null),
  });
}
