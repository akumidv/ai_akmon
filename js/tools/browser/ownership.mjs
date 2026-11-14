/**
 * Whose Chrome answers on the DevTools port (ADR 0032/D05). A DevTools answer alone says nothing
 * about whose browser it is, and driving another project's signed-in window, or one nobody started
 * for this project, is the one thing this tool must not do. So a Chrome on the port is used only when
 * its process runs with this project's profile as its `--user-data-dir`; every other one is named
 * (another project's, or one akmon did not start) and refused with the fix.
 */

/**
 * Whose Chrome it is, read from the command lines of the processes listening on the port.
 * @typedef {{owner: "ours"} | {owner: "foreign", project: string | null, profile: string | null} | {owner: "unknown"}} Ownership
 */

/**
 * The state of a port: nothing answers (`null`), or a Chrome does, with its owner and the reason
 * not to drive it (`null` for this project's own).
 * @typedef {object} PortState
 * @property {Record<string, unknown>} version the DevTools `/json/version` answer
 * @property {Ownership} owner
 * @property {string | null} refusal
 */

/**
 * The `--user-data-dir` of a Chrome command line, quotes aside.
 * @param {string} line
 * @returns {string | null}
 */
export function userDataDir(line) {
  const match = line.match(/--user-data-dir=(?:"([^"]+)"|(\S+))/);
  return match === null ? null : (match[1] ?? match[2] ?? null);
}

/**
 * Whether two profile paths are the same folder, trailing separators, the slash direction and, for a
 * Windows path, the case aside.
 * @param {string} left
 * @param {string} right
 * @returns {boolean}
 */
export function samePath(left, right) {
  const normal = (/** @type {string} */ path) => path.replace(/[\\/]+$/, "").replace(/\\/g, "/");
  const windows = /^[a-z]:|^\/\/|^\\\\/i.test(left);
  return windows ? normal(left).toLowerCase() === normal(right).toLowerCase() : normal(left) === normal(right);
}

/**
 * The project an akmon browser profile belongs to — `<project>/<dev root>/.local/.browser/chrome-profile[-cft]`
 * as a Linux, macOS or Windows (`\\wsl.localhost\...`) path, the project being the folder two levels above
 * `.local` — or `null` for any other profile.
 * @param {string | null} profile
 * @returns {string | null}
 */
export function profileProject(profile) {
  const match = String(profile ?? "").match(
    /([^\\/]+)[\\/][^\\/]+[\\/]\.local[\\/]\.browser[\\/]chrome-profile(?:-cft)?[\\/]*$/,
  );
  return match === null ? null : match[1];
}

/**
 * The project a foreign akmon profile belongs to, as its owner recorded it: the profile's sibling
 * `launch.json` (`<dev root>/.local/.browser/launch.json`, written by `start`) holds the project root,
 * whose folder name is the project's, wherever the dev root sits. A profile with no readable record
 * falls back to `profileProject`, the folder two levels above `.local`.
 * @param {string | null} profile
 * @param {(path: string) => string | null} readText reads a file, `null` when there is none
 * @returns {string | null}
 */
export function projectNamed(profile, readText) {
  const tail = /[\\/]chrome-profile(?:-cft)?[\\/]*$/;
  if (profile !== null && profileProject(profile) !== null) {
    const text = readText(_launchRecordPath(profile.replace(tail, "/launch.json")));
    const root = _recordedRoot(text);
    if (root !== null) {
      return root;
    }
  }
  return profileProject(profile);
}

/**
 * The path as this side of the machine reads it: a `\\wsl.localhost\<distro>\...` path, which is how a
 * Windows Chrome under WSL names a Linux folder, is the Linux path `/...`; any other path is read as it is.
 * @param {string} path
 * @returns {string}
 */
function _launchRecordPath(path) {
  const unc = path.match(/^[\\/]{2}wsl(?:\.localhost|\$)[\\/][^\\/]+(.*)$/i);
  return unc === null ? path : unc[1].replace(/\\/g, "/");
}

/**
 * The folder name of the project root a `launch.json` records, or `null` when it records none.
 * @param {string | null} text
 * @returns {string | null}
 */
function _recordedRoot(text) {
  if (text === null) {
    return null;
  }
  try {
    const root = JSON.parse(text)?.project;
    const name =
      typeof root === "string"
        ? root
            .replace(/[\\/]+$/, "")
            .split(/[\\/]/)
            .pop()
        : "";
    return name ? name : null;
  } catch {
    return null;
  }
}

/**
 * Whose Chrome the processes in `commandLines` are. `profiles` are the profile folders this project
 * gives its Chrome: the one it would use now, the one of its last `start` (`launch.json`), and the two
 * defaults, so a Chrome started before a setting changed is still told as the project's. A foreign
 * Chrome is named from its project's own `launch.json` through `readText`, when that is readable.
 * @param {string[]} commandLines the command lines of the processes listening on the port
 * @param {string[]} profiles
 * @param {(path: string) => string | null} [readText] reads a file, `null` when there is none; the
 *   default reads none, so the name comes from the profile's path alone
 * @returns {Ownership}
 */
export function chromeOwnership(commandLines, profiles, readText = () => null) {
  const dirs = commandLines.map(userDataDir);
  if (dirs.length === 0) {
    return { owner: "unknown" };
  }
  if (dirs.some((dir) => dir !== null && profiles.some((profile) => samePath(dir, profile)))) {
    return { owner: "ours" };
  }
  const used = dirs.find(Boolean) ?? null;
  return { owner: "foreign", project: projectNamed(used, readText), profile: used };
}

/**
 * Whose Chrome it is, in words.
 * @param {Ownership} owner
 * @returns {string}
 */
export function describeOwner(owner) {
  if (owner.owner === "unknown") {
    return "a Chrome whose process was not found, so whose it is cannot be told";
  }
  if (owner.owner === "ours") {
    return "this project's Chrome";
  }
  const profile = owner.profile ? `profile ${owner.profile}` : "its default profile";
  return owner.project === null
    ? `a Chrome not started by akmon (${profile})`
    : `the Chrome of project ${owner.project} (${profile})`;
}

/**
 * Why a Chrome on a port that is not this project's is not driven, and how to fix it.
 * @param {Ownership} owner
 * @param {{port: number, project: string}} here the port and this project's name
 * @returns {string}
 */
export function notOursMessage(owner, here) {
  return (
    `the Chrome on 127.0.0.1:${here.port} is ${describeOwner(owner)}, not project ${here.project}'s. ` +
    `akmon does not drive it: close that Chrome, or set AKMON_BROWSER_PORT (or port in [browser] of .akmon.toml) ` +
    `to a free port; then start this project's: akmon tool browser start`
  );
}

/**
 * The Chrome answering on a port, checked: `null` when nothing answers. The one check `start`,
 * `status`, `stop` and the MCP launcher make.
 * @param {number} port
 * @param {{probe: (port: number) => Promise<Record<string, unknown> | null>, owner: (port: number) => Ownership, project: string}} how
 *   `probe` asks DevTools for its version, `owner` reads the processes, `project` is this project's name
 * @returns {Promise<PortState | null>}
 */
export async function checkPort(port, how) {
  const version = await how.probe(port);
  if (version === null) {
    return null;
  }
  const owner = how.owner(port);
  return {
    version,
    owner,
    refusal: owner.owner === "ours" ? null : notOursMessage(owner, { port, project: how.project }),
  };
}
