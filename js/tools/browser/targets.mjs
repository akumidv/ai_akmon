/**
 * The targets of a Chrome (`/json/list`) and the choice of one page among them. Pure apart from the one
 * fetch, which a caller replaces in a test; imports nothing outside Node, for the CDP runner.
 */

import { CdpError } from "./cdp.mjs";
import { redactUrl } from "./redact.mjs";

/**
 * One DevTools target.
 * @typedef {object} Target
 * @property {string} id
 * @property {string} type `page`, `service_worker`, `background_page`, `other` ...
 * @property {string} title
 * @property {string} url
 */

/**
 * The page targets, in the order Chrome lists them (the most recently focused first).
 * @param {readonly Target[]} targets
 * @returns {Target[]}
 */
export function pageTargets(targets) {
  return targets.filter((target) => target.type === "page");
}

/**
 * The page a `--page` selector names: an index into the page targets, a target id, or a substring of a
 * page's URL; with no selector, the first page.
 * @param {readonly Target[]} targets
 * @param {string | null} selector
 * @returns {Target}
 * @throws {CdpError} when there is no page, or none matches
 */
export function selectPage(targets, selector) {
  const pages = pageTargets(targets);
  if (pages.length === 0) {
    throw new CdpError("the browser has no open page; open one in the window, then run the verb again");
  }
  if (selector === null) {
    return pages[0];
  }
  const found = /^\d+$/.test(selector)
    ? pages[Number(selector)]
    : (pages.find((page) => page.id === selector) ?? pages.find((page) => page.url.includes(selector)));
  if (found === undefined) {
    const known = pages.map((page, index) => `${index}: ${redactUrl(page.url, [])}`).join("; ");
    throw new CdpError(`no page matches --page ${JSON.stringify(selector)}; pages are ${known}`);
  }
  return found;
}

/**
 * The targets with every URL redacted: what a verb prints or writes is built from these, never from the
 * listing as it came (an OAuth callback keeps its token in the fragment of the page's URL).
 * @param {readonly Target[]} targets
 * @param {readonly string[]} keys the project's keys, added to the floor
 * @returns {Target[]}
 */
export function redactedTargets(targets, keys) {
  return targets.map((target) => ({ ...target, url: redactUrl(target.url, keys) }));
}

/**
 * The page tabs a status prints, from a `/json/list` answer: title and URL, the URL redacted.
 * @param {readonly {type: string, title: string, url: string}[]} list
 * @param {readonly string[]} keys the project's keys, added to the floor
 * @returns {{title: string, url: string}[]}
 */
export function pageTabs(list, keys) {
  return list.filter((tab) => tab.type === "page").map((tab) => ({ title: tab.title, url: redactUrl(tab.url, keys) }));
}

/**
 * The targets of a Chrome, as `/json/list` says.
 * @param {string} browserURL `http://127.0.0.1:<port>`
 * @param {(url: string) => Promise<any>} fetchJson
 * @returns {Promise<Target[]>}
 * @throws {CdpError} when DevTools does not answer or answers with something else
 */
export async function fetchTargets(browserURL, fetchJson) {
  const list = await fetchJson(`${browserURL}/json/list`);
  if (!Array.isArray(list)) {
    throw new CdpError(`${browserURL}/json/list did not answer with a list of targets`);
  }
  return list.map((entry) => ({
    id: String(entry.id ?? ""),
    type: String(entry.type ?? ""),
    title: String(entry.title ?? ""),
    url: String(entry.url ?? ""),
  }));
}
