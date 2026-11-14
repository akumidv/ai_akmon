/**
 * The selector check of `akmon tool browser selectors`: a project's registry of
 * `{ "<name>": ["<css selector>", "<fallback>", ...] }` is counted against the live page, shadow roots
 * included, and each name is reported as matched, matched by a fallback or missing. This module holds the
 * page-side script and the pure reading of its answer; it imports nothing, because the CDP runner loads it
 * on the Windows side too (`ops.mjs`). The registry file is read and checked by the verb (`inspect.mjs`).
 */

/**
 * The function run in the page, as source: for every name, how many elements each selector matches in the
 * document and in every open shadow root, found recursively, and the message of a selector the browser
 * rejects. It only reads: it queries, it never changes the page.
 */
const _PAGE_SCRIPT = `(registry) => {
  const roots = [document];
  for (let at = 0; at < roots.length; at += 1) {
    for (const element of roots[at].querySelectorAll("*")) {
      if (element.shadowRoot) {
        roots.push(element.shadowRoot);
      }
    }
  }
  const answer = {};
  for (const [name, selectors] of Object.entries(registry)) {
    const counts = [];
    const errors = [];
    for (const selector of selectors) {
      try {
        counts.push(roots.reduce((sum, root) => sum + root.querySelectorAll(selector).length, 0));
        errors.push(null);
      } catch (error) {
        counts.push(0);
        errors.push(String(error && error.message ? error.message : error));
      }
    }
    answer[name] = { counts, errors };
  }
  return answer;
}`;

/**
 * The expression that evaluates the page-side script for a registry.
 * @param {Readonly<Record<string, readonly string[]>>} registry
 * @returns {string}
 */
export function selectorExpression(registry) {
  return `(${_PAGE_SCRIPT})(${JSON.stringify(registry)})`;
}

/**
 * What the check found for one name.
 * @typedef {object} SelectorFinding
 * @property {string} name
 * @property {"matched" | "fallback" | "missing"} status `fallback`: the first selector found nothing and a later one did
 * @property {number | null} index the position in the list of the selector that matched (0 is the primary); `null` when missing
 * @property {number[]} counts the elements each selector matched
 * @property {string | null} selector the selector that matched, or `null`
 * @property {{selector: string, message: string}[]} errors the selectors the browser rejected
 */

/**
 * The findings for a registry from the page-side script's answer: a name is matched when its first
 * selector finds an element, matched by a fallback when a later one does, and missing when none does.
 * @param {Readonly<Record<string, readonly string[]>>} registry
 * @param {Record<string, {counts: number[], errors: (string | null)[]}>} answer
 * @returns {SelectorFinding[]}
 */
export function selectorFindings(registry, answer) {
  return Object.entries(registry).map(([name, selectors]) => {
    const counts = answer[name]?.counts ?? selectors.map(() => 0);
    const errors = (answer[name]?.errors ?? []).flatMap((message, at) =>
      message === null ? [] : [{ selector: selectors[at], message }],
    );
    const index = counts.findIndex((count) => count > 0);
    if (index < 0) {
      return { name, status: "missing", index: null, counts, selector: null, errors };
    }
    return { name, status: index === 0 ? "matched" : "fallback", index, counts, selector: selectors[index], errors };
  });
}
