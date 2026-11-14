/**
 * Everything one run of `akmon tool browser` reads from the outside, collected once at the entry
 * point and passed down: the project, its settings, the machine, the environment and where lines go.
 * The verbs read nothing of their own accord.
 */

import { projectAt, portOf, readSettings } from "./settings.mjs";

/**
 * @typedef {object} Context
 * @property {import("./settings.mjs").Project} project
 * @property {import("./settings.mjs").BrowserSettings} settings
 * @property {number} port the project's DevTools port
 * @property {import("./host.mjs").Host} host
 * @property {Record<string, string | undefined>} env
 * @property {(line: string) => void} say write one line of the result (stdout)
 */

/**
 * The context of a run in `cwd`.
 * @param {string} cwd where the run starts; the project is the one at or above it, unless `AKMON_BROWSER_ROOT` names one
 * @param {{env: Record<string, string | undefined>, host: import("./host.mjs").Host, say: (line: string) => void}} given
 * @returns {Context}
 * @throws {import("./settings.mjs").BrowserError} outside a project, or on a setting that is not valid
 */
export function buildContext(cwd, given) {
  const project = projectAt(cwd, given.env);
  const settings = readSettings(project, given.env);
  return { project, settings, port: portOf(project, settings), host: given.host, env: given.env, say: given.say };
}
