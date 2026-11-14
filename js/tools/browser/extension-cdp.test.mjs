import { test } from "node:test";
import assert from "node:assert/strict";

import { extensionIdOf, matchExtensions, popupUrlOf, samePath, soleExtension } from "./extension-cdp.mjs";
import { runRequest } from "./ops.mjs";
import { extensionsPage, fakeChrome, SAMPLE_EXTENSION } from "./support.test.mjs";

const ID = SAMPLE_EXTENSION.id;
const OTHER_ID = "ponmlkjihgfedcbaponmlkjihgfedcba";
const OTHER = { ...SAMPLE_EXTENSION, id: OTHER_ID, name: "Other tool", path: "/work/acme/other" };

const TARGETS = [
  { id: "T1", type: "page", title: "Shop", url: "https://shop.example/cart" },
  { id: "P1", type: "page", title: "Bench popup", url: `chrome-extension://${ID}/popup.html` },
  { id: "W1", type: "service_worker", title: "bg", url: `chrome-extension://${ID}/background.js` },
];

/**
 * Run operations against a fake Chrome and return the whole response.
 * @param {ReturnType<typeof fakeChrome>} chrome
 * @param {import("./protocol.mjs").Operation[]} operations
 * @param {Partial<import("./protocol.mjs").Request>} [extra]
 */
function run(chrome, operations, extra = {}) {
  return runRequest({ browserURL: "http://127.0.0.1:9582", page: null, redact: [], operations, ...extra }, chrome.deps);
}

/** @param {Awaited<ReturnType<typeof run>>} response */
function value(response) {
  assert.equal(response.error, undefined);
  const outcome = response.results?.[0];
  assert.ok(outcome?.ok, JSON.stringify(outcome));
  return outcome.value;
}

const methods = (/** @type {ReturnType<typeof fakeChrome>} */ chrome) => chrome.calls.map((call) => call.method);
const attached = (/** @type {ReturnType<typeof fakeChrome>} */ chrome) =>
  chrome.calls.filter((call) => call.method === "Target.attachToTarget").map((call) => call.params.targetId);

/**
 * A fake Chrome that holds extensions: the extensions page, and an evaluation answered by the target it ran in.
 * @param {Record<string, (params: any, control: any) => unknown>} [replies]
 * @param {Parameters<typeof extensionsPage>[0]} [page]
 * @param {Parameters<typeof fakeChrome>[1]} [given]
 */
function extensionChrome(replies = {}, page = {}, given = {}) {
  const pageReplies = extensionsPage(page);
  const evaluateInPage = pageReplies["Runtime.evaluate"];
  return fakeChrome(
    {
      ...pageReplies,
      "Runtime.evaluate": (params) =>
        params.expression === "1+1" ? { result: { type: "number", value: 2 } } : evaluateInPage(params),
      ...replies,
    },
    { targets: TARGETS, ...given },
  );
}

test("an extension's id is read from its chrome-extension URL, and from nothing else", () => {
  assert.equal(extensionIdOf(`chrome-extension://${ID}/popup.html?x=1`), ID);
  assert.equal(extensionIdOf(`chrome-extension://${ID}`), ID);
  assert.equal(extensionIdOf("chrome-extension://short/x.html"), null);
  assert.equal(extensionIdOf("https://shop.example/"), null);
});

test("two folder paths are the same folder across a Windows spelling, and only then", () => {
  assert.ok(samePath("C:\\Users\\Me\\ext\\", "c:/users/me/ext"));
  assert.ok(samePath("/work/acme/ext/", "/work/acme/ext"));
  assert.ok(!samePath("/work/acme/ext", "/work/acme/Ext"));
  assert.ok(!samePath("/work/acme/ext", "/work/acme/other"));
});

test("a selector means the id, the name, part of a name, or by default the configured unpacked ones", () => {
  const store = { ...OTHER, id: "x".repeat(32), name: "Store tool", unpacked: false, path: null };
  const list = [SAMPLE_EXTENSION, OTHER, store];
  const ids = (/** @type {string | null} */ select, /** @type {string[]} */ paths = []) =>
    matchExtensions(list, { select, paths }).map((item) => item.id);
  assert.deepEqual(ids(ID), [ID]);
  assert.deepEqual(ids("other TOOL"), [OTHER_ID]);
  assert.deepEqual(ids("tool"), [OTHER_ID, store.id]);
  assert.deepEqual(ids(null), [ID, OTHER_ID]);
  assert.deepEqual(ids(null, ["/work/acme/other/"]), [OTHER_ID]);
  assert.deepEqual(ids(null, ["/elsewhere"]), []);
});

test("one extension is picked out of the matches, and several or none are named so --ext can choose", () => {
  assert.equal(soleExtension([SAMPLE_EXTENSION], "x"), SAMPLE_EXTENSION);
  assert.throws(
    () => soleExtension([SAMPLE_EXTENSION, OTHER], "the configured extensions"),
    new RegExp(`2 extensions match .*Bench \\(${ID}\\), Other tool \\(${OTHER_ID}\\); pick one with --ext`),
  );
  assert.throws(() => soleExtension([], "nothing"), /no extension matches nothing/);
});

test("the popup is the default_popup of the action, in a Manifest V3 or V2 manifest", () => {
  assert.equal(
    popupUrlOf(JSON.stringify({ action: { default_popup: "ui/popup.html" } }), ID),
    `chrome-extension://${ID}/ui/popup.html`,
  );
  assert.equal(
    popupUrlOf(JSON.stringify({ browser_action: { default_popup: "/p.html" } }), ID),
    `chrome-extension://${ID}/p.html`,
  );
  assert.equal(popupUrlOf(JSON.stringify({ action: {} }), ID), null);
  assert.throws(() => popupUrlOf("{", ID), /manifest\.json is not JSON/);
});

test("sw attaches to the one extension's running service worker with no look at the extensions page", async () => {
  const chrome = extensionChrome();
  const response = await run(chrome, [{ op: "eval", expression: "1+1" }], { target: "sw" });
  assert.deepEqual(value(response), { type: "number", value: 2 });
  assert.deepEqual(response.page, { id: "W1", title: "bg", url: `chrome-extension://${ID}/background.js` });
  assert.deepEqual(attached(chrome), ["W1"]);
  assert.ok(!methods(chrome).includes("Target.createTarget"));
});

test("popup attaches to an open page of the extension, the one named popup first", async () => {
  const extra = { id: "P2", type: "page", title: "Options", url: `chrome-extension://${ID}/options.html` };
  const chrome = extensionChrome({}, {}, { targets: [TARGETS[0], extra, TARGETS[1], TARGETS[2]] });
  const response = await run(chrome, [{ op: "eval", expression: "1+1" }], { target: "popup" });
  assert.equal(response.page?.id, "P1");
  assert.deepEqual(attached(chrome), ["P1"]);
});

test("a target id attaches to that target, and an unknown one fails the run naming the way to list them", async () => {
  const chrome = extensionChrome();
  assert.equal((await run(chrome, [{ op: "eval", expression: "1+1" }], { target: "W1" })).page?.id, "W1");
  const missing = await run(extensionChrome(), [{ op: "eval", expression: "1+1" }], { target: "ZZZZ" });
  assert.match(String(missing.error), /no target has the id ZZZZ; `pages --all`/);
  assert.equal(missing.results, undefined);
});

test("with no worker running the run fails saying why a Manifest V3 worker may be missing", async () => {
  const chrome = extensionChrome({}, {}, { targets: [TARGETS[0]] });
  const response = await run(chrome, [{ op: "eval", expression: "1+1" }], { target: "sw" });
  assert.match(String(response.error), /no extension service worker is running; a Manifest V3 worker stops when idle/);
  assert.deepEqual(attached(chrome), []);
});

test("a name picks the worker through the extensions page, an id needs no lookup", async () => {
  const targets = [
    TARGETS[0],
    TARGETS[2],
    { id: "W2", type: "service_worker", title: "bg", url: `chrome-extension://${OTHER_ID}/sw.js` },
  ];
  const seen = /** @type {string[]} */ ([]);
  const chrome = extensionChrome({}, { list: [SAMPLE_EXTENSION, OTHER], seen }, { targets });
  const byName = await run(chrome, [{ op: "eval", expression: "1+1" }], { target: "sw", ext: "other tool" });
  assert.equal(byName.page?.id, "W2");
  assert.ok(seen.some((script) => script.includes("getExtensionsInfo")));
  const direct = extensionChrome({}, { list: [SAMPLE_EXTENSION, OTHER] }, { targets });
  assert.equal((await run(direct, [{ op: "eval", expression: "1+1" }], { target: "sw", ext: ID })).page?.id, "W1");
  assert.ok(!methods(direct).includes("Target.createTarget"));
  const none = extensionChrome({}, {}, { targets });
  const response = await run(none, [{ op: "eval", expression: "1+1" }], { target: "sw", ext: "a".repeat(32) });
  assert.match(String(response.error), /the extension a+ has no a running service worker/);
});

test("with several workers the configured folder says which extension is meant, and none configured asks for --ext", async () => {
  const targets = [
    TARGETS[2],
    { id: "W2", type: "service_worker", title: "bg", url: `chrome-extension://${OTHER_ID}/sw.js` },
  ];
  const chrome = extensionChrome({}, { list: [SAMPLE_EXTENSION, OTHER] }, { targets });
  const configured = await run(chrome, [{ op: "eval", expression: "1+1" }], {
    target: "sw",
    extensionPaths: ["/work/acme/other"],
  });
  assert.equal(configured.page?.id, "W2");
  const open = extensionChrome({}, { list: [SAMPLE_EXTENSION, OTHER] }, { targets });
  const ambiguous = await run(open, [{ op: "eval", expression: "1+1" }], { target: "sw" });
  assert.match(String(ambiguous.error), /2 extensions match .*pick one with --ext <id\|name>/);
});

test("ext-list reads every extension through developerPrivate and marks the configured ones", async () => {
  const seen = /** @type {string[]} */ ([]);
  const chrome = extensionChrome({}, { list: [SAMPLE_EXTENSION, OTHER], seen });
  const { extensions } = value(await run(chrome, [{ op: "ext-list" }], { extensionPaths: ["/work/acme/extension"] }));
  assert.deepEqual(
    extensions.map((/** @type {any} */ item) => [item.id, item.configured]),
    [
      [ID, true],
      [OTHER_ID, false],
    ],
  );
  assert.ok(seen.some((script) => script.includes("getExtensionsInfo({ includeDisabled: true")));
  // The tab is opened in the background for the call, and is the one tab closed after it.
  assert.deepEqual(
    methods(chrome).filter((method) => ["Target.createTarget", "Target.closeTarget"].includes(method)),
    ["Target.createTarget", "Target.closeTarget"],
  );
  assert.deepEqual(chrome.calls[0].params, { url: "chrome://extensions", background: true });
  assert.deepEqual(chrome.calls.at(-1)?.params, { targetId: "X1" });
});

test("ext-devmode turns developer mode on and reads it back", async () => {
  const seen = /** @type {string[]} */ ([]);
  const chrome = extensionChrome({}, { seen });
  assert.deepEqual(value(await run(chrome, [{ op: "ext-devmode" }])), { inDeveloperMode: true });
  assert.ok(seen.some((script) => script.includes("updateProfileConfiguration({ inDeveloperMode: true })")));
});

test("ext-reload reloads the configured unpacked extensions through developerPrivate, and reports the folders not loaded", async () => {
  const seen = /** @type {string[]} */ ([]);
  const outcome = { id: ID, loadError: null, info: SAMPLE_EXTENSION };
  const chrome = extensionChrome({}, { list: [SAMPLE_EXTENSION, OTHER], reload: [outcome], seen });
  const result = value(
    await run(chrome, [{ op: "ext-reload" }], { extensionPaths: ["/work/acme/extension", "/work/acme/gone"] }),
  );
  assert.deepEqual(result, { reloaded: [outcome], missing: ["/work/acme/gone"] });
  const reload = seen.find((script) => script.includes("dev.reload"));
  assert.match(String(reload), /dev\.reload\(id, \{ failQuietly: true, populateErrorForUnpacked: true \}\)/);
  assert.match(String(reload), new RegExp(`for \\(const id of \\["${ID}"\\]\\)`));
});

test("ext-reload of a name reloads that extension, and a name that matches nothing lists what is loaded", async () => {
  /** @type {string[][]} */
  const asked = [];
  const chrome = extensionChrome(
    {},
    {
      list: [SAMPLE_EXTENSION, OTHER],
      reload: (ids) => {
        asked.push(ids);
        return ids.map((id) => ({ id, loadError: null, info: OTHER }));
      },
    },
  );
  await run(chrome, [{ op: "ext-reload" }], { ext: "other" });
  assert.deepEqual(asked, [[OTHER_ID]]);
  const response = await run(chrome, [{ op: "ext-reload" }], { ext: "nope" });
  assert.match(
    String(response.results?.[0].ok === false && response.results[0].error),
    new RegExp(`no extension matches "nope"; loaded: Bench \\(${ID}\\), Other tool \\(${OTHER_ID}\\)`),
  );
});

test("ext-reload with nothing configured loaded says how to get Chrome to load it", async () => {
  const chrome = extensionChrome({}, { list: [] });
  const response = await run(chrome, [{ op: "ext-reload" }], { extensionPaths: ["/work/acme/extension"] });
  const outcome = response.results?.[0];
  assert.ok(outcome && !outcome.ok);
  assert.match(
    outcome.error,
    /no unpacked extension is loaded from \/work\/acme\/extension; .*akmon tool browser restart/,
  );
});

test("ext-action runs the action over the DevTools port on the selected page when Chrome offers it", async () => {
  const chrome = extensionChrome({ "Extensions.triggerAction": () => ({}) });
  const outcome = value(await run(chrome, [{ op: "ext-action" }], { page: "shop" }));
  assert.equal(outcome.route, "cdp");
  assert.deepEqual(outcome.extension, { id: ID, name: "Bench" });
  assert.equal(outcome.page.id, "T1");
  const trigger = chrome.calls.find((call) => call.method === "Extensions.triggerAction");
  assert.deepEqual(trigger?.params, { id: ID, targetId: "T1" });
  assert.equal(trigger?.sessionId, undefined);
  assert.ok(!methods(chrome).includes("Target.attachToTarget") || attached(chrome).every((id) => id === "X1"));
});

test("ext-action reports the page's URL with its secret parameters redacted", async () => {
  const targets = [{ id: "T1", type: "page", title: "Cb", url: "https://shop.example/cb#access_token=SECRETT" }];
  const chrome = extensionChrome({ "Extensions.triggerAction": () => ({}) }, {}, { targets });
  const outcome = value(await run(chrome, [{ op: "ext-action" }], { page: "shop" }));
  assert.equal(outcome.page.url, "https://shop.example/cb#access_token=[redacted]");
});

test("ext-action falls back to the popup page in a new tab when Chrome has no such method, saying why", async () => {
  const manifest = JSON.stringify({ action: { default_popup: "popup.html" } });
  const chrome = extensionChrome(
    {
      "Extensions.triggerAction": () => {
        throw new Error("'Extensions.triggerAction' wasn't found");
      },
    },
    {},
    { files: { "/work/acme/extension/manifest.json": manifest } },
  );
  const outcome = value(await run(chrome, [{ op: "ext-action" }]));
  assert.equal(outcome.route, "popup");
  assert.deepEqual(outcome.popup, { targetId: "P9", url: `chrome-extension://${ID}/popup.html` });
  assert.match(outcome.refusal, /Extensions\.triggerAction' wasn't found/);
  const created = chrome.calls.filter((call) => call.method === "Target.createTarget").map((call) => call.params.url);
  assert.deepEqual(created, ["chrome://extensions", `chrome-extension://${ID}/popup.html`]);
});

test("an action with no popup and no DevTools route is refused naming both", async () => {
  const chrome = extensionChrome(
    {
      "Extensions.triggerAction": () => {
        throw new Error("not available");
      },
    },
    {},
    { files: { "/work/acme/extension/manifest.json": JSON.stringify({ action: {} }) } },
  );
  const response = await run(chrome, [{ op: "ext-action" }]);
  const outcome = response.results?.[0];
  assert.ok(outcome && !outcome.ok);
  assert.match(
    outcome.error,
    /does not run an extension's action over the DevTools port \(Extensions\.triggerAction: not available\).*no default_popup/,
  );
});

test("ext-action of a disabled extension is not offered, and several extensions ask for --ext", async () => {
  const disabled = { ...SAMPLE_EXTENSION, state: "DISABLED", enabled: false };
  const chrome = extensionChrome({}, { list: [disabled] });
  const none = (await run(chrome, [{ op: "ext-action" }])).results?.[0];
  assert.ok(none && !none.ok && /no extension matches the configured extensions/.test(none.error));
  const many = extensionChrome({}, { list: [SAMPLE_EXTENSION, OTHER] });
  const ambiguous = (await run(many, [{ op: "ext-action" }])).results?.[0];
  assert.ok(ambiguous && !ambiguous.ok && /pick one with --ext/.test(ambiguous.error));
});
