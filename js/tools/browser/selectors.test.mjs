import { test } from "node:test";
import assert from "node:assert/strict";
import vm from "node:vm";

import { runRequest } from "./ops.mjs";
import { selectorExpression, selectorFindings } from "./selectors.mjs";
import { fakeChrome } from "./support.test.mjs";

/**
 * @typedef {object} FakeRoot
 * @property {(css: string) => {shadowRoot: FakeRoot | null}[]} querySelectorAll
 */

/**
 * A fake DOM root: `matches` are the selectors that find an element in it, `hosts` the elements that carry an
 * open shadow root; a selector that is `bad[` is a syntax error, as in a browser.
 * @param {{matches?: Record<string, number>, hosts?: FakeRoot[]}} [given]
 * @returns {FakeRoot}
 */
function root(given = {}) {
  const elements = (given.hosts ?? []).map((shadow) => ({ shadowRoot: shadow }));
  return {
    querySelectorAll: (/** @type {string} */ css) => {
      if (css === "bad[") {
        throw new SyntaxError(`'${css}' is not a valid selector`);
      }
      if (css === "*") {
        return elements;
      }
      return Array.from({ length: given.matches?.[css] ?? 0 }, () => ({ shadowRoot: null }));
    },
  };
}

/**
 * Run the page-side script of a registry against a fake document.
 * @param {Record<string, string[]>} registry
 * @param {FakeRoot} document
 * @returns {any}
 */
function inPage(registry, document) {
  return JSON.parse(JSON.stringify(vm.runInNewContext(selectorExpression(registry), { document })));
}

test("the page script counts every selector in the document and in every open shadow root, recursively", () => {
  const inner = root({ matches: { ".buy": 1 } });
  const outer = root({ matches: { ".buy": 2, "#title": 1 }, hosts: [inner] });
  const document = root({ matches: { ".buy": 1 }, hosts: [outer, root()] });
  const answer = inPage({ buy: [".buy"], title: ["#title", "h1"], gone: [".gone"] }, document);
  assert.deepEqual(answer.buy.counts, [4]);
  assert.deepEqual(answer.title.counts, [1, 0]);
  assert.deepEqual(answer.gone.counts, [0]);
});

test("a selector the browser rejects counts as none and is reported with its message", () => {
  const answer = inPage({ odd: ["bad[", ".ok"] }, root({ matches: { ".ok": 1 } }));
  assert.deepEqual(answer.odd.counts, [0, 1]);
  assert.match(answer.odd.errors[0], /not a valid selector/);
  assert.equal(answer.odd.errors[1], null);
});

test("the registry reaches the page as data, never as code", () => {
  const expression = selectorExpression({ 'a"); evil("': ["x'); evil('"] });
  assert.ok(expression.endsWith(`(${JSON.stringify({ 'a"); evil("': ["x'); evil('"] })})`));
  assert.deepEqual(inPage({ 'a"); evil("': ["x'); evil('"] }, root()), {
    'a"); evil("': { counts: [0], errors: [null] },
  });
});

test("a name is matched by its primary, matched by the first fallback that finds something, or missing", () => {
  const registry = { buy: [".buy", ".buy-v2"], title: ["#t", "h1", ".title"], gone: [".gone"], odd: ["bad[", ".x"] };
  const findings = selectorFindings(registry, {
    buy: { counts: [3, 5], errors: [null, null] },
    title: { counts: [0, 0, 2], errors: [null, null, null] },
    gone: { counts: [0], errors: [null] },
    odd: { counts: [0, 0], errors: ["bad selector", null] },
  });
  assert.deepEqual(
    findings.map((finding) => [finding.name, finding.status, finding.index, finding.selector]),
    [
      ["buy", "matched", 0, ".buy"],
      ["title", "fallback", 2, ".title"],
      ["gone", "missing", null, null],
      ["odd", "missing", null, null],
    ],
  );
  assert.deepEqual(findings[3].errors, [{ selector: "bad[", message: "bad selector" }]);
});

test("the selectors operation evaluates in the page world and returns the findings, shadow roots counted by the page", async () => {
  const chrome = fakeChrome({
    "Runtime.evaluate": (params) => {
      assert.equal(params.contextId, undefined);
      assert.equal(params.returnByValue, true);
      const answer = JSON.parse(
        JSON.stringify(
          vm.runInNewContext(String(params.expression), {
            document: root({ matches: { ".fallback": 1 }, hosts: [root({ matches: { ".primary-in-shadow": 2 } })] }),
          }),
        ),
      );
      return { result: { type: "object", value: answer } };
    },
  });
  const response = await runRequest(
    {
      browserURL: "http://127.0.0.1:9582",
      page: null,
      redact: [],
      operations: [
        { op: "selectors", registry: { a: [".primary-in-shadow"], b: [".nope", ".fallback"], c: [".none"] } },
      ],
    },
    chrome.deps,
  );
  const outcome = response.results?.[0];
  assert.ok(outcome?.ok);
  assert.deepEqual(
    outcome.value.findings.map((/** @type {any} */ finding) => [finding.name, finding.status, finding.index]),
    [
      ["a", "matched", 0],
      ["b", "fallback", 1],
      ["c", "missing", null],
    ],
  );
});

test("a page script that throws fails the operation with the exception's text", async () => {
  const chrome = fakeChrome({
    "Runtime.evaluate": () => ({
      exceptionDetails: { text: "Uncaught", exception: { description: "ReferenceError: document is not defined" } },
    }),
  });
  const response = await runRequest(
    {
      browserURL: "http://127.0.0.1:9582",
      page: null,
      redact: [],
      operations: [{ op: "selectors", registry: { a: [".a"] } }],
    },
    chrome.deps,
  );
  const outcome = response.results?.[0];
  assert.ok(outcome && !outcome.ok);
  assert.match(outcome.error, /the expression threw: ReferenceError/);
});
