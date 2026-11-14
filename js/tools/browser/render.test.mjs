import { test } from "node:test";
import assert from "node:assert/strict";

import {
  actionLines,
  evalText,
  extensionLines,
  logLines,
  netLines,
  outlineLines,
  pageLines,
  pageRows,
  reloadLines,
  reloadSucceeded,
  selectorLines,
} from "./render.mjs";

const TARGETS = [
  { id: "W1", type: "service_worker", title: "sw", url: "https://shop.example/sw.js" },
  { id: "T1", type: "page", title: "Shop", url: "https://shop.example/cart" },
  { id: "T2", type: "page", title: "Docs", url: "https://docs.example/" },
];

test("pages numbers the page targets and adds the other targets only with --all", () => {
  assert.deepEqual(
    pageRows(TARGETS, false).map((row) => [row.index, row.id]),
    [
      [0, "T1"],
      [1, "T2"],
    ],
  );
  assert.deepEqual(
    pageRows(TARGETS, true).map((row) => [row.index, row.id]),
    [
      [0, "T1"],
      [1, "T2"],
      [null, "W1"],
    ],
  );
  const lines = pageLines(pageRows(TARGETS, true));
  assert.match(lines[0], /^ 0 {2}T1 {2}page .*Shop .*https:\/\/shop\.example\/cart$/);
  assert.match(lines[2], /^ - {2}W1 {2}service_worker/);
  assert.deepEqual(pageLines([]), ["no open page"]);
});

test("the outline reads role, quoted name and value, indented by depth, and says what was cut", () => {
  const lines = outlineLines({
    lines: [
      { depth: 0, role: "RootWebArea", name: "Shop", value: "" },
      { depth: 1, role: "textbox", name: "Name", value: "Ann" },
      { depth: 1, role: "separator", name: "", value: "" },
    ],
    total: 10,
    truncated: true,
  });
  assert.deepEqual(lines, [
    'RootWebArea "Shop"',
    '  textbox "Name" [Ann]',
    "  separator",
    "… 7 more nodes not shown (10 in all); raise --max-nodes",
  ]);
});

test("eval prints a string as it is, anything else as JSON, and JSON mode quotes strings", () => {
  assert.equal(evalText({ type: "string", value: "Shop" }, false), "Shop");
  assert.equal(evalText({ type: "string", value: "Shop" }, true), '"Shop"');
  assert.equal(evalText({ type: "object", value: { a: 1 } }, true), '{"a":1}');
  assert.equal(evalText({ type: "object", value: { a: 1 } }, false), '{\n  "a": 1\n}');
  assert.equal(evalText({ type: "number", unserializable: "NaN" }, false), "NaN");
  assert.equal(evalText({ type: "undefined" }, false), "undefined");
  assert.equal(evalText({ type: "undefined" }, true), "null");
});

test("log lines carry a signed relative time, their source and their kind", () => {
  assert.deepEqual(
    logLines([
      { t: -1.5, source: "page", tag: "console.error", text: "boom" },
      { t: 0.25, source: "extension", tag: "exception", text: "TypeError: x" },
      { t: 0.5, source: "sw", tag: "console.log", text: "woke" },
    ]),
    [
      "   -1.50s [page] console.error: boom",
      "   +0.25s [extension] exception: TypeError: x",
      "   +0.50s [sw] console.log: woke",
    ],
  );
});

test("net lines read method, result, type, mime, size, time and URL; bodies sit under their line", () => {
  const entry = {
    id: "1",
    method: "GET",
    url: "https://a/x",
    status: 200,
    type: "Fetch",
    mime: "application/json",
    size: 2048,
    ms: 250,
    failure: null,
    requestHeaders: {},
    responseHeaders: {},
    body: '{"a":1}',
    bodyTruncated: true,
  };
  const failed = { ...entry, id: "2", status: null, failure: "net::ERR_FAILED", size: null, ms: null, body: undefined };
  assert.deepEqual(netLines([entry, failed], false), [
    "GET    200  Fetch  application/json  2.0kB  250ms  https://a/x",
    "GET    FAILED net::ERR_FAILED  Fetch  application/json  -  -  https://a/x",
  ]);
  assert.equal(netLines([entry], true)[1], '    body (cut): {"a":1}');
  assert.equal(
    netLines([{ ...entry, body: undefined, bodyNote: "binary body not read" }], true)[1],
    "    no body: binary body not read",
  );
});

const SAMPLE = {
  id: "abcdefghijklmnopabcdefghijklmnop",
  name: "Bench",
  version: "1.0.0",
  state: "ENABLED",
  enabled: true,
  unpacked: true,
  path: "/p/ext",
  disableReasons: /** @type {string[]} */ ([]),
  errors: /** @type {string[]} */ ([]),
  configured: true,
};

test("ext list prints one line per extension and what is wrong under it", () => {
  assert.deepEqual(extensionLines([]), ["no extension is loaded"]);
  const lines = extensionLines([
    SAMPLE,
    {
      ...SAMPLE,
      id: "b".repeat(32),
      name: "Store",
      state: "DISABLED",
      enabled: false,
      unpacked: false,
      path: null,
      configured: false,
      disableReasons: ["unsupportedDeveloperExtension"],
      errors: ["Manifest is not valid"],
    },
  ]);
  assert.deepEqual(lines, [
    `${SAMPLE.id}  ENABLED   Bench 1.0.0  (configured /p/ext)`,
    `${"b".repeat(32)}  DISABLED  Store 1.0.0  (installed)`,
    "    disabled: unsupportedDeveloperExtension",
    "    manifest error: Manifest is not valid",
  ]);
});

test("ext reload prints each state and load error, and succeeds only when all run with no error", () => {
  const ok = { reloaded: [{ id: SAMPLE.id, loadError: null, info: SAMPLE }], missing: [] };
  assert.deepEqual(reloadLines(ok), [`${SAMPLE.id}  ENABLED  Bench 1.0.0`]);
  assert.equal(reloadSucceeded(ok), true);
  const broken = {
    reloaded: [{ id: "c".repeat(32), loadError: "Could not load manifest.", info: null }],
    missing: ["/p/gone"],
  };
  const lines = reloadLines(broken);
  assert.equal(lines[0], `${"c".repeat(32)}  NOT LOADED`);
  assert.equal(lines[1], "    load error: Could not load manifest.");
  assert.match(lines[2], /^not loaded: \/p\/gone; .*akmon tool browser restart$/);
  assert.equal(reloadSucceeded(broken), false);
  assert.equal(
    reloadSucceeded({
      reloaded: [{ id: SAMPLE.id, loadError: null, info: { ...SAMPLE, enabled: false } }],
      missing: [],
    }),
    false,
  );
});

test("ext action says plainly which route ran, and what the popup route lacks", () => {
  const base = {
    extension: { id: SAMPLE.id, name: "Bench" },
    page: { id: "T1", title: "Shop", url: "https://shop.example/cart" },
    popup: null,
    refusal: null,
  };
  assert.deepEqual(actionLines({ ...base, route: "cdp" }), [
    `triggered the action of Bench (${SAMPLE.id}) on Shop [T1]`,
  ]);
  const popup = actionLines({
    ...base,
    route: "popup",
    popup: { targetId: "P9", url: `chrome-extension://${SAMPLE.id}/popup.html` },
    refusal: "Extensions.triggerAction: not found",
  });
  assert.match(popup[0], /opened the popup of Bench .* in a new tab: chrome-extension:\/\/.*popup\.html \[P9\]/);
  assert.match(popup.join(" "), /lacks the active-tab context/);
  assert.match(popup.join(" "), /Extensions\.triggerAction: not found/);
});

test("selector lines say matched, matched by fallback n, or missing, and what the browser rejected", () => {
  const lines = selectorLines([
    { name: "buy", status: "matched", index: 0, counts: [2], selector: ".buy", errors: [] },
    { name: "title", status: "fallback", index: 2, counts: [0, 0, 1], selector: ".t", errors: [] },
    {
      name: "gone",
      status: "missing",
      index: null,
      counts: [0],
      selector: null,
      errors: [{ selector: "bad[", message: "invalid" }],
    },
  ]);
  assert.deepEqual(lines, [
    "matched                buy  .buy (2)",
    "matched by fallback 2  title  .t (1)",
    "missing                gone",
    "    rejected bad[: invalid",
  ]);
});
