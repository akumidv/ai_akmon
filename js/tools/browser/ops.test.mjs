import { test } from "node:test";
import assert from "node:assert/strict";

import { outlineOf, remoteText, runRequest } from "./ops.mjs";
import { REDACTED } from "./redact.mjs";
import { extensionsPage, fakeChrome } from "./support.test.mjs";

/**
 * Run one operation against a fake Chrome and return its outcome.
 * @param {ReturnType<typeof fakeChrome>} chrome
 * @param {import("./protocol.mjs").Operation} operation
 * @param {Partial<import("./protocol.mjs").Request>} [extra] the rest of the request: `page`, `redact`, `target`, `ext` ...
 */
async function run(chrome, operation, extra = {}) {
  const response = await runRequest(
    {
      browserURL: "http://127.0.0.1:9582",
      page: null,
      redact: ["password", "token"],
      operations: [operation],
      ...extra,
    },
    chrome.deps,
  );
  return response;
}

/** @param {Awaited<ReturnType<typeof run>>} response */
function value(response) {
  assert.equal(response.error, undefined);
  const outcome = response.results?.[0];
  assert.ok(outcome?.ok, JSON.stringify(outcome));
  return outcome.value;
}

const methods = (/** @type {ReturnType<typeof fakeChrome>} */ chrome) => chrome.calls.map((call) => call.method);

test("the outline drops ignored, none, nameless generic nodes and repeated text; the rest keep their depth", () => {
  const nodes = [
    { nodeId: "1", role: { value: "RootWebArea" }, name: { value: "Shop" }, childIds: ["2", "3", "6"] },
    { nodeId: "2", parentId: "1", ignored: true, role: { value: "none" }, childIds: ["4"] },
    { nodeId: "4", parentId: "2", role: { value: "heading" }, name: { value: "Cart" }, childIds: ["5"] },
    { nodeId: "5", parentId: "4", role: { value: "StaticText" }, name: { value: "Cart" } },
    { nodeId: "3", parentId: "1", role: { value: "generic" }, name: { value: "" }, childIds: ["7"] },
    { nodeId: "7", parentId: "3", role: { value: "textbox" }, name: { value: "Name" }, value: { value: "Ann" } },
    { nodeId: "6", parentId: "1", role: { value: "button" }, name: { value: " Pay \n now " } },
  ];
  const outline = outlineOf(nodes, 100);
  assert.deepEqual(outline.lines, [
    { depth: 0, role: "RootWebArea", name: "Shop", value: "" },
    { depth: 1, role: "heading", name: "Cart", value: "" },
    { depth: 1, role: "textbox", name: "Name", value: "Ann" },
    { depth: 1, role: "button", name: "Pay now", value: "" },
  ]);
  assert.deepEqual([outline.total, outline.truncated], [4, false]);
});

test("the outline is capped and says how much it left out", () => {
  const nodes = [
    { nodeId: "1", role: { value: "list" }, childIds: ["2", "3", "4"] },
    ...["2", "3", "4"].map((id) => ({ nodeId: id, parentId: "1", role: { value: "listitem" }, name: { value: id } })),
  ];
  const outline = outlineOf(nodes, 2);
  assert.equal(outline.lines.length, 2);
  assert.deepEqual([outline.total, outline.truncated], [4, true]);
});

test("snapshot asks the page's accessibility tree, with the session, and returns the outline", async () => {
  const chrome = fakeChrome({
    "Accessibility.getFullAXTree": () => ({
      nodes: [{ nodeId: "1", role: { value: "RootWebArea" }, name: { value: "Shop" } }],
    }),
  });
  const result = value(await run(chrome, { op: "snapshot", maxNodes: 50, text: false }));
  assert.equal(result.lines[0].role, "RootWebArea");
  assert.deepEqual(methods(chrome), [
    "Target.attachToTarget",
    "Accessibility.getFullAXTree",
    "Target.detachFromTarget",
  ]);
  assert.equal(chrome.calls[1].sessionId, "S1");
  assert.equal(chrome.calls[0].params.targetId, "T1");
});

test("snapshot --text reads the page's visible text", async () => {
  const chrome = fakeChrome({ "Runtime.evaluate": () => ({ result: { type: "string", value: "Hello\nCart" } }) });
  assert.deepEqual(value(await run(chrome, { op: "snapshot", maxNodes: 5, text: true })), { text: "Hello\nCart" });
  assert.match(chrome.calls[1].params.expression, /innerText/);
});

test("the page is the one --page names, and a page that is not there fails the run with the choices", async () => {
  const chrome = fakeChrome({ "Runtime.evaluate": () => ({ result: { type: "string", value: "x" } }) });
  const response = await run(chrome, { op: "eval", expression: "1" }, { page: "docs" });
  assert.equal(response.page?.id, "T2");
  assert.equal(chrome.calls[0].params.targetId, "T2");
  const missing = await run(fakeChrome(), { op: "eval", expression: "1" }, { page: "nope" });
  assert.match(String(missing.error), /no page matches --page "nope"/);
  assert.equal(missing.results, undefined);
});

test("screenshot emulates the viewport and scheme, captures, then clears both, in that order", async () => {
  const chrome = fakeChrome({ "Page.captureScreenshot": () => ({ data: "UE5H" }) });
  const result = value(
    await run(chrome, { op: "screenshot", viewport: { width: 390, height: 844 }, scheme: "dark", full: false }),
  );
  assert.deepEqual(result, { data: "UE5H", warnings: [] });
  assert.deepEqual(methods(chrome), [
    "Target.attachToTarget",
    "Emulation.setDeviceMetricsOverride",
    "Emulation.setEmulatedMedia",
    "Page.captureScreenshot",
    "Emulation.clearDeviceMetricsOverride",
    "Emulation.setEmulatedMedia",
    "Target.detachFromTarget",
  ]);
  assert.deepEqual(chrome.calls[1].params, { width: 390, height: 844, deviceScaleFactor: 1, mobile: false });
  assert.deepEqual(chrome.calls[2].params, { features: [{ name: "prefers-color-scheme", value: "dark" }] });
  assert.deepEqual(chrome.calls[5].params, { features: [] });
});

test("a screenshot of the window as it is sets and clears nothing", async () => {
  const chrome = fakeChrome({ "Page.captureScreenshot": () => ({ data: "x" }) });
  value(await run(chrome, { op: "screenshot", viewport: null, scheme: null, full: false }));
  assert.deepEqual(methods(chrome), ["Target.attachToTarget", "Page.captureScreenshot", "Target.detachFromTarget"]);
});

test("a full-page screenshot captures beyond the viewport, clipped to the content size", async () => {
  const chrome = fakeChrome({
    "Page.getLayoutMetrics": () => ({ cssContentSize: { width: 1440, height: 3200.4 } }),
    "Page.captureScreenshot": () => ({ data: "x" }),
  });
  value(await run(chrome, { op: "screenshot", viewport: null, scheme: null, full: true }));
  assert.deepEqual(chrome.calls[2].params, {
    format: "png",
    captureBeyondViewport: true,
    clip: { x: 0, y: 0, width: 1440, height: 3201, scale: 1 },
  });
});

test("the emulation is cleared when the capture fails, and the failure is the answer", async () => {
  const chrome = fakeChrome({
    "Page.captureScreenshot": () => {
      throw new Error("Unable to capture screenshot");
    },
  });
  const response = await run(chrome, {
    op: "screenshot",
    viewport: { width: 390, height: 844 },
    scheme: "light",
    full: false,
  });
  assert.deepEqual(response.results, [{ ok: false, error: "Page.captureScreenshot: Unable to capture screenshot" }]);
  assert.deepEqual(methods(chrome).slice(-3), [
    "Emulation.clearDeviceMetricsOverride",
    "Emulation.setEmulatedMedia",
    "Target.detachFromTarget",
  ]);
});

test("the emulation is cleared even when setting it failed half way", async () => {
  const chrome = fakeChrome({
    "Emulation.setEmulatedMedia": (params) => {
      if (params.features.length > 0) {
        throw new Error("media refused");
      }
      return {};
    },
  });
  const response = await run(chrome, {
    op: "screenshot",
    viewport: { width: 1, height: 1 },
    scheme: "dark",
    full: false,
  });
  assert.match(JSON.stringify(response.results?.[0]), /media refused/);
  assert.ok(methods(chrome).includes("Emulation.clearDeviceMetricsOverride"));
});

test("an emulation that cannot be cleared is reported, with the shot kept", async () => {
  const chrome = fakeChrome({
    "Page.captureScreenshot": () => ({ data: "x" }),
    "Emulation.clearDeviceMetricsOverride": () => {
      throw new Error("gone");
    },
  });
  const result = value(
    await run(chrome, { op: "screenshot", viewport: { width: 1, height: 1 }, scheme: null, full: false }),
  );
  assert.equal(result.data, "x");
  assert.match(result.warnings[0], /clearDeviceMetricsOverride failed \(.*gone\); reload the page/);
});

test("eval returns the value by value, awaits promises and times out on its own", async () => {
  const chrome = fakeChrome({ "Runtime.evaluate": () => ({ result: { type: "object", value: { a: [1, 2] } } }) });
  assert.deepEqual(value(await run(chrome, { op: "eval", expression: "({a: [1,2]})" })), {
    type: "object",
    value: { a: [1, 2] },
  });
  const params = chrome.calls[1].params;
  assert.deepEqual(
    [params.returnByValue, params.awaitPromise, params.userGesture, typeof params.timeout],
    [true, true, false, "number"],
  );
  const odd = fakeChrome({
    "Runtime.evaluate": () => ({ result: { type: "number", unserializableValue: "NaN", description: "NaN" } }),
  });
  assert.equal(value(await run(odd, { op: "eval", expression: "NaN" })).unserializable, "NaN");
});

test("an expression that throws fails the verb with the exception's text", async () => {
  const chrome = fakeChrome({
    "Runtime.evaluate": () => ({
      result: { type: "object" },
      exceptionDetails: {
        text: "Uncaught",
        exception: { description: "ReferenceError: nope is not defined\n    at <anonymous>:1:1" },
      },
    }),
  });
  const response = await run(chrome, { op: "eval", expression: "nope" });
  assert.match(JSON.stringify(response.results?.[0]), /the expression threw: ReferenceError: nope is not defined/);
});

test("console arguments read as their value, a short preview, or their description", () => {
  assert.equal(remoteText({ type: "string", value: "hi" }), "hi");
  assert.equal(remoteText({ type: "number", value: 3 }), "3");
  assert.equal(remoteText({ type: "number", unserializableValue: "NaN" }), "NaN");
  assert.equal(
    remoteText({
      type: "object",
      className: "Object",
      preview: { properties: [{ name: "a", value: "1" }], overflow: true },
    }),
    "Object{a: 1, …}",
  );
  assert.equal(
    remoteText({ type: "object", description: "Error: x\n    at y", preview: { properties: [] } }),
    "Error: x\n    at y",
  );
  assert.equal(remoteText({ type: "function", description: "f()" }), "f()");
});

/**
 * A fake Chrome whose console replays one message and whose log replays another, both before the
 * enable answers, as Chrome does.
 */
function loggingChrome() {
  return fakeChrome({
    "Runtime.enable": (_params, control) => {
      control.emit("Runtime.consoleAPICalled", {
        type: "error",
        args: [{ type: "string", value: "boom at load" }],
        timestamp: 999_000,
      });
      return {};
    },
    "Log.enable": (_params, control) => {
      control.emit("Log.entryAdded", {
        entry: {
          source: "network",
          level: "error",
          text: "Failed to load resource",
          url: "https://x/y.js",
          timestamp: 999_500,
        },
      });
      return {};
    },
  });
}

test("logs print what the domains replay, with times before the start, and stop at the time", async () => {
  const chrome = loggingChrome();
  const result = value(await run(chrome, { op: "logs", until: null, seconds: 0.05 }));
  assert.equal(result.status, "timeout");
  assert.deepEqual(result.entries, [
    { t: -1, source: "page", tag: "console.error", text: "boom at load" },
    { t: -0.5, source: "page", tag: "log.network", text: "Failed to load resource (https://x/y.js)" },
  ]);
  assert.deepEqual(methods(chrome).slice(1, 3), ["Runtime.enable", "Log.enable"]);
});

test("logs scrub a secret from console text, an exception and a log URL, and --until never sees it", async () => {
  const chrome = fakeChrome({
    "Runtime.enable": (_params, control) => {
      control.emit("Runtime.consoleAPICalled", {
        type: "log",
        args: [{ type: "string", value: "login id_token=abc123 Bearer eyJ.x https://u:pw@h.example/p" }],
        timestamp: 999_000,
      });
      control.emit("Runtime.exceptionThrown", {
        timestamp: 999_100,
        exceptionDetails: { text: "Uncaught", exception: { description: 'Error: {"sessionId": "s3cret"}' } },
      });
      return {};
    },
    "Log.enable": (_params, control) => {
      control.emit("Log.entryAdded", {
        entry: {
          source: "network",
          level: "error",
          text: "Failed",
          url: "https://x/y.js?access_token=zzz#id_token=qqq",
          timestamp: 999_500,
        },
      });
      return {};
    },
  });
  const result = value(await run(chrome, { op: "logs", until: null, seconds: 0.05 }));
  const printed = JSON.stringify(result.entries);
  for (const leaked of ["abc123", "eyJ.x", "u:pw", "s3cret", "zzz", "qqq"]) {
    assert.ok(!printed.includes(leaked), `${leaked} leaked: ${printed}`);
  }
  assert.match(printed, /id_token=\[redacted\]/);
  assert.match(printed, /access_token=\[redacted\]#id_token=\[redacted\]/);
});

test("logs follow: a new line that matches --until ends the wait; the replayed ones do not", async () => {
  const chrome = fakeChrome({
    "Runtime.enable": (_params, control) => {
      control.emit("Runtime.consoleAPICalled", {
        type: "log",
        args: [{ type: "string", value: "ready" }],
        timestamp: 999_000,
      });
      return {};
    },
    "Log.enable": (_params, control) => {
      setTimeout(() => {
        control.emit("Runtime.exceptionThrown", {
          timestamp: 1_000_200,
          exceptionDetails: { text: "Uncaught", exception: { description: "TypeError: x is undefined" } },
        });
        control.emit("Runtime.consoleAPICalled", {
          type: "log",
          args: [{ type: "string", value: "ready" }],
          timestamp: 1_000_300,
        });
      }, 10);
      return {};
    },
  });
  const result = value(await run(chrome, { op: "logs", until: "^\\[page\\] console\\.log: ready", seconds: 5 }));
  assert.equal(result.status, "matched");
  assert.deepEqual(
    result.entries.map((/** @type {any} */ entry) => [entry.t, entry.tag]),
    [
      [-1, "console.log"],
      [0.2, "exception"],
      [0.3, "console.log"],
    ],
  );
});

test("logs end with 'closed' when the browser goes away", async () => {
  const chrome = fakeChrome({
    "Log.enable": () => {
      setTimeout(() => chrome.end(), 5);
      return {};
    },
  });
  const response = await run(chrome, { op: "logs", until: null, seconds: 5 });
  assert.equal(value(response).status, "closed");
});

/**
 * Feed a request's events, in the order Chrome sends them.
 * @param {(method: string, params: unknown) => void} emit
 * @param {object[]} events pairs of `[method, params]`
 */
function feed(emit, events) {
  setTimeout(() => {
    for (const [method, params] of /** @type {[string, unknown][]} */ (events)) {
      emit(method, params);
    }
  }, 5);
}

const API = "https://shop.example/api/cart?token=SECRETQ&page=1";
const traffic = (/** @type {number} */ base) => [
  [
    "Network.requestWillBeSent",
    {
      requestId: "1",
      timestamp: base,
      type: "Fetch",
      request: { url: API, method: "GET", headers: { Authorization: "Bearer SECRETH", Accept: "*/*" } },
    },
  ],
  [
    "Network.responseReceived",
    {
      requestId: "1",
      type: "Fetch",
      response: {
        url: API,
        status: 200,
        mimeType: "application/json",
        headers: { "Set-Cookie": "sid=SECRETC", "Content-Type": "application/json" },
      },
    },
  ],
  ["Network.loadingFinished", { requestId: "1", timestamp: base + 0.25, encodedDataLength: 2048 }],
  [
    "Network.requestWillBeSent",
    {
      requestId: "2",
      timestamp: base + 1,
      type: "Fetch",
      request: { url: "https://shop.example/api/pay", method: "POST", headers: {} },
    },
  ],
  [
    "Network.responseReceived",
    {
      requestId: "2",
      type: "Fetch",
      response: { url: "https://shop.example/api/pay", status: 500, mimeType: "application/json", headers: {} },
    },
  ],
  ["Network.loadingFinished", { requestId: "2", timestamp: base + 1.1, encodedDataLength: 40 }],
  [
    "Network.requestWillBeSent",
    {
      requestId: "3",
      timestamp: base + 2,
      type: "Image",
      request: { url: "https://cdn.example/a.png", method: "GET", headers: {} },
    },
  ],
  [
    "Network.loadingFailed",
    { requestId: "3", timestamp: base + 2.5, errorText: "net::ERR_BLOCKED_BY_CLIENT", blockedReason: "inspector" },
  ],
];

test("net collects the requests with status, type, size and time, and says nothing is reloaded", async () => {
  const chrome = fakeChrome({}, {});
  feed(chrome.emit, traffic(10));
  const result = value(
    await run(chrome, { op: "net", seconds: 0.1, until: null, failed: false, bodies: false, maxBody: 100 }),
  );
  assert.equal(result.status, "timeout");
  assert.deepEqual(
    result.entries.map((/** @type {any} */ entry) => [
      entry.method,
      entry.status,
      entry.type,
      entry.size,
      entry.ms,
      entry.failure,
    ]),
    [
      ["GET", 200, "Fetch", 2048, 250, null],
      ["POST", 500, "Fetch", 40, 100, null],
      ["GET", null, "Image", null, 500, "net::ERR_BLOCKED_BY_CLIENT (inspector)"],
    ],
  );
  assert.ok(!methods(chrome).some((method) => method.startsWith("Page.")));
});

test("secrets are redacted at capture: headers and query values never leave the capture", async () => {
  const chrome = fakeChrome();
  feed(chrome.emit, traffic(10));
  const result = value(
    await run(chrome, { op: "net", seconds: 0.1, until: null, failed: false, bodies: false, maxBody: 100 }),
  );
  const text = JSON.stringify(result);
  for (const secret of ["SECRETH", "SECRETC", "SECRETQ"]) {
    assert.ok(!text.includes(secret), secret);
  }
  assert.equal(result.entries[0].requestHeaders.Authorization, REDACTED);
  assert.equal(result.entries[0].requestHeaders.Accept, "*/*");
  assert.equal(result.entries[0].responseHeaders["Set-Cookie"], REDACTED);
  assert.equal(result.entries[0].url, `https://shop.example/api/cart?token=${REDACTED}&page=1`);
});

test("--failed keeps status 400 and above and failures", async () => {
  const chrome = fakeChrome();
  feed(chrome.emit, traffic(10));
  const result = value(
    await run(chrome, { op: "net", seconds: 0.1, until: null, failed: true, bodies: false, maxBody: 100 }),
  );
  assert.deepEqual(
    result.entries.map((/** @type {any} */ entry) => entry.id),
    ["2", "3"],
  );
});

test("--bodies reads text and JSON bodies, redacts nested keys, cuts at the cap and skips the rest", async () => {
  const body = JSON.stringify({ items: [{ sku: "a", token: "SECRETJ" }], note: "n".repeat(200), password: "SECRETP" });
  const chrome = fakeChrome({
    "Network.getResponseBody": (params) =>
      params.requestId === "1" ? { body, base64Encoded: false } : { body: "AAAA", base64Encoded: true },
  });
  feed(chrome.emit, traffic(10));
  const result = value(
    await run(chrome, { op: "net", seconds: 0.1, until: null, failed: false, bodies: true, maxBody: 120 }),
  );
  const [first, second, third] = result.entries;
  assert.equal(first.bodyTruncated, true);
  assert.ok(first.body.length <= 120);
  assert.ok(!JSON.stringify(result).includes("SECRETJ") && !JSON.stringify(result).includes("SECRETP"));
  assert.ok(first.body.includes(REDACTED));
  assert.equal(second.bodyNote, "binary body not read");
  assert.equal(third.body, undefined);
  assert.equal(third.bodyNote, undefined);
  const asked = chrome.calls
    .filter((call) => call.method === "Network.getResponseBody")
    .map((call) => call.params.requestId);
  assert.deepEqual(asked, ["1", "2"]);
});

test("--bodies scrubs a text body that is not JSON or a form, and withholds a binary one", async () => {
  const html = '<script>window.cfg = {"apiToken": "SECRETA"}; Authorization: Token SECRETB</script>';
  const chrome = fakeChrome({
    "Network.getResponseBody": (params) => ({
      body: params.requestId === "1" ? html : "AAAA",
      base64Encoded: params.requestId !== "1",
    }),
  });
  /** @type {(id: string, mimeType: string) => [string, object][]} */
  const exchange = (id, mimeType) => [
    [
      "Network.requestWillBeSent",
      {
        requestId: id,
        timestamp: 10,
        type: "Document",
        request: { url: `https://h.example/${id}`, method: "GET", headers: {} },
      },
    ],
    [
      "Network.responseReceived",
      {
        requestId: id,
        type: "Document",
        response: { url: `https://h.example/${id}`, status: 200, mimeType, headers: {} },
      },
    ],
    ["Network.loadingFinished", { requestId: id, timestamp: 10.1, encodedDataLength: 10 }],
  ];
  feed(chrome.emit, [...exchange("1", "text/html"), ...exchange("2", "application/octet-stream")]);
  const result = value(
    await run(chrome, { op: "net", seconds: 0.1, until: null, failed: false, bodies: true, maxBody: 500 }),
  );
  const [page, binary] = result.entries;
  assert.ok(!JSON.stringify(result).includes("SECRETA") && !JSON.stringify(result).includes("SECRETB"));
  assert.ok(page.body.startsWith("<script>"));
  assert.equal(binary.body, undefined);
  assert.match(binary.bodyNote, /binary/);
});

test("the page URL a run reports is redacted, so an OAuth fragment never reaches a verb's output", async () => {
  const chrome = fakeChrome(
    {},
    { targets: [{ id: "T1", type: "page", title: "Cb", url: "https://app.example/cb#access_token=SECRETT" }] },
  );
  const response = await run(chrome, { op: "eval", expression: "1" });
  assert.equal(response.page?.url, `https://app.example/cb#access_token=${REDACTED}`);
  assert.ok(!JSON.stringify(response).includes("SECRETT"));
});

test("a body Chrome no longer holds is a note, not a failure of the capture", async () => {
  const chrome = fakeChrome({
    "Network.getResponseBody": () => {
      throw new Error("No resource with given identifier found");
    },
  });
  feed(chrome.emit, traffic(10));
  const result = value(
    await run(chrome, { op: "net", seconds: 0.1, until: null, failed: false, bodies: true, maxBody: 100 }),
  );
  assert.match(result.entries[0].bodyNote, /No resource with given identifier/);
});

test("--until ends the capture when a finished request's line matches", async () => {
  const chrome = fakeChrome();
  feed(chrome.emit, traffic(10));
  const result = value(
    await run(chrome, {
      op: "net",
      seconds: 5,
      until: "POST .*/api/pay 500",
      failed: false,
      bodies: false,
      maxBody: 100,
    }),
  );
  assert.equal(result.status, "matched");
  assert.equal(result.entries.length, 2);
});

test("a redirect closes the first request with its own status and starts the next", async () => {
  const chrome = fakeChrome();
  feed(chrome.emit, [
    [
      "Network.requestWillBeSent",
      {
        requestId: "9",
        timestamp: 1,
        type: "Document",
        request: { url: "https://a.example/", method: "GET", headers: {} },
      },
    ],
    [
      "Network.requestWillBeSent",
      {
        requestId: "9",
        timestamp: 1.2,
        type: "Document",
        redirectResponse: { status: 302, mimeType: "text/html", headers: {} },
        request: { url: "https://a.example/home", method: "GET", headers: {} },
      },
    ],
    [
      "Network.responseReceived",
      { requestId: "9", type: "Document", response: { status: 200, mimeType: "text/html", headers: {} } },
    ],
    ["Network.loadingFinished", { requestId: "9", timestamp: 1.5, encodedDataLength: 10 }],
  ]);
  const result = value(
    await run(chrome, { op: "net", seconds: 0.1, until: null, failed: false, bodies: false, maxBody: 100 }),
  );
  assert.deepEqual(
    result.entries.map((/** @type {any} */ entry) => [entry.url, entry.status, entry.ms]),
    [
      ["https://a.example/", 302, 200],
      ["https://a.example/home", 200, 300],
    ],
  );
});

test("one operation failing leaves the others their answers", async () => {
  const chrome = fakeChrome({
    "Runtime.evaluate": () => ({ result: { type: "number", value: 2 } }),
    "Page.captureScreenshot": () => {
      throw new Error("no capture");
    },
  });
  const response = await runRequest(
    {
      browserURL: "http://127.0.0.1:9",
      page: null,
      redact: [],
      operations: [
        { op: "screenshot", viewport: null, scheme: null, full: false },
        { op: "eval", expression: "1+1" },
      ],
    },
    { ...chrome.deps, fetchJson: chrome.deps.fetchJson },
  );
  assert.equal(response.results?.[0].ok, false);
  assert.deepEqual(response.results?.[1], { ok: true, value: { type: "number", value: 2 } });
});

const EXT_ID = "abcdefghijklmnopabcdefghijklmnop";
const OTHER_EXT_ID = "ponmlkjihgfedcbaponmlkjihgfedcba";

/**
 * A fake page with its own world and the content-script worlds of the given extensions, which `Runtime.enable`
 * announces; `Runtime.evaluate` answers with the context it was asked to run in.
 * @param {{extensions?: [string, string][], replies?: Record<string, (params: any, control: any) => unknown>}} [given] pairs of `[id, name]`
 */
function worldsChrome(given = {}) {
  const extensions = given.extensions ?? [[EXT_ID, "Bench"]];
  return fakeChrome({
    "Runtime.enable": (_params, control) => {
      control.emit("Runtime.executionContextCreated", {
        context: { id: 1, origin: "https://shop.example", name: "", auxData: { type: "default", frameId: "F1" } },
      });
      extensions.forEach(([id, name], at) =>
        control.emit("Runtime.executionContextCreated", {
          context: {
            id: 2 + at,
            origin: `chrome-extension://${id}`,
            name,
            auxData: { type: "isolated", frameId: "F1" },
          },
        }),
      );
      return {};
    },
    "Page.getFrameTree": () => ({ frameTree: { frame: { id: "F1" } } }),
    "Runtime.evaluate": (params) => ({
      result: { type: "string", value: `ran in ${params.contextId ?? "the page"}` },
    }),
    ...given.replies,
  });
}

test("eval runs in the page's own world by default and in the extension's isolated world on request", async () => {
  const chrome = worldsChrome();
  assert.equal(value(await run(chrome, { op: "eval", expression: "x" })).value, "ran in the page");
  assert.ok(!methods(chrome).includes("Runtime.enable"));
  const isolated = worldsChrome();
  assert.equal(value(await run(isolated, { op: "eval", expression: "x", world: "isolated" })).value, "ran in 2");
  assert.deepEqual(methods(isolated).slice(0, 3), ["Target.attachToTarget", "Runtime.enable", "Page.getFrameTree"]);
});

test("the isolated world is the one of the extension named by id or by name, and the page's own is never taken for it", async () => {
  const both = /** @type {[string, string][]} */ ([
    [EXT_ID, "Bench"],
    [OTHER_EXT_ID, "Other tool"],
  ]);
  const evalIn = async (/** @type {Partial<import("./protocol.mjs").Request>} */ extra) =>
    value(await run(worldsChrome({ extensions: both }), { op: "eval", expression: "x", world: "isolated" }, extra))
      .value;
  assert.equal(await evalIn({ ext: OTHER_EXT_ID }), "ran in 3");
  assert.equal(await evalIn({ ext: "other TOOL" }), "ran in 3");
  assert.equal(await evalIn({ ext: "bench" }), "ran in 2");
  const response = await run(
    worldsChrome({ extensions: both }),
    { op: "eval", expression: "x", world: "isolated" },
    { ext: "nope" },
  );
  const outcome = response.results?.[0];
  assert.ok(outcome && !outcome.ok);
  assert.match(
    outcome.error,
    /the extension "nope" has no content-script world on this page \(the page has: Bench \(a+.*Other tool/,
  );
});

test("with several extensions on the page the configured folder picks the world, through the extensions page", async () => {
  const both = /** @type {[string, string][]} */ ([
    [EXT_ID, "Bench"],
    [OTHER_EXT_ID, "Other tool"],
  ]);
  const page = extensionsPage({
    list: [
      { id: EXT_ID, name: "Bench", unpacked: true, path: "/work/acme/extension" },
      { id: OTHER_EXT_ID, name: "Other tool", unpacked: true, path: "/work/acme/other" },
    ],
  });
  const evaluateInPage = page["Runtime.evaluate"];
  const chrome = worldsChrome({
    extensions: both,
    replies: {
      ...page,
      "Runtime.evaluate": (params) =>
        params.contextId === undefined
          ? evaluateInPage(params)
          : { result: { type: "string", value: `ran in ${params.contextId}` } },
    },
  });
  const response = await run(
    chrome,
    { op: "eval", expression: "x", world: "isolated" },
    { extensionPaths: ["/work/acme/other"] },
  );
  assert.equal(value(response).value, "ran in 3");
});

test("a page no content script runs on has no isolated world, and the failure says what to try", async () => {
  const chrome = worldsChrome({ extensions: [] });
  const response = await run(chrome, { op: "eval", expression: "x", world: "isolated" });
  const outcome = response.results?.[0];
  assert.ok(outcome && !outcome.ok);
  assert.match(outcome.error, /no extension has content-script world on this page; .* needs a reload/);
});

test("logs tag each line by where it came from: the page, an extension's isolated world, or the service worker", async () => {
  const chrome = worldsChrome({
    replies: {
      "Runtime.enable": (_params, control) => {
        control.emit("Runtime.executionContextCreated", {
          context: { id: 1, origin: "https://shop.example", name: "", auxData: { type: "default" } },
        });
        control.emit("Runtime.executionContextCreated", {
          context: { id: 2, origin: `chrome-extension://${EXT_ID}`, name: "Bench", auxData: { type: "isolated" } },
        });
        control.emit("Runtime.consoleAPICalled", {
          type: "log",
          executionContextId: 1,
          args: [{ type: "string", value: "from the page" }],
          timestamp: 999_000,
        });
        control.emit("Runtime.consoleAPICalled", {
          type: "warning",
          executionContextId: 2,
          args: [{ type: "string", value: "from the content script" }],
          timestamp: 999_100,
        });
        control.emit("Runtime.exceptionThrown", {
          timestamp: 999_200,
          exceptionDetails: { executionContextId: 2, exception: { description: "TypeError: gone" } },
        });
        return {};
      },
    },
  });
  const result = value(await run(chrome, { op: "logs", until: null, seconds: 0.05 }));
  assert.deepEqual(
    result.entries.map((/** @type {any} */ entry) => [entry.source, entry.tag, entry.text]),
    [
      ["page", "console.log", "from the page"],
      ["extension", "console.warning", "from the content script"],
      ["extension", "exception", "TypeError: gone"],
    ],
  );
});

test("logs of a service worker are tagged sw, and --until sees the source", async () => {
  const targets = [{ id: "W1", type: "service_worker", title: "bg", url: `chrome-extension://${EXT_ID}/bg.js` }];
  const chrome = fakeChrome(
    {
      "Log.enable": (_params, control) => {
        setTimeout(
          () =>
            control.emit("Runtime.consoleAPICalled", {
              type: "log",
              args: [{ type: "string", value: "woke" }],
              timestamp: 1_000_100,
            }),
          10,
        );
        return {};
      },
    },
    { targets },
  );
  const response = await run(
    chrome,
    { op: "logs", until: "^\\[sw\\] console\\.log: woke", seconds: 5 },
    { target: "sw" },
  );
  const result = value(response);
  assert.equal(result.status, "matched");
  assert.deepEqual(
    result.entries.map((/** @type {any} */ entry) => entry.source),
    ["sw"],
  );
  assert.equal(chrome.calls[0].params.targetId, "W1");
});

test("net listens on the target the request names, a service worker included", async () => {
  const targets = [{ id: "W1", type: "service_worker", title: "bg", url: `chrome-extension://${EXT_ID}/bg.js` }];
  const chrome = fakeChrome({}, { targets });
  const response = await run(
    chrome,
    { op: "net", seconds: 0.05, until: null, failed: false, bodies: false, maxBody: 10 },
    { target: "sw" },
  );
  assert.equal(value(response).status, "timeout");
  assert.deepEqual(methods(chrome).slice(0, 2), ["Target.attachToTarget", "Network.enable"]);
  assert.equal(response.page?.id, "W1");
});

test("the key floor applies at the Chrome side too: a request cannot lower it", async () => {
  const chrome = fakeChrome();
  feed(chrome.emit, traffic(10));
  const result = value(
    await run(
      chrome,
      { op: "net", seconds: 0.1, until: null, failed: false, bodies: false, maxBody: 100 },
      { redact: ["only-this"] },
    ),
  );
  assert.equal(result.entries[0].url, `https://shop.example/api/cart?token=${REDACTED}&page=1`);
});
