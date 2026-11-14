import { test } from "node:test";
import assert from "node:assert/strict";

import { startRecording } from "./record-ops.mjs";
import { REDACTED } from "./redact.mjs";

const TARGETS = [
  { id: "T1", type: "page", title: "Shop", url: "https://shop.example/cart?token=abc&x=1" },
  { id: "T2", type: "page", title: "Docs", url: "https://docs.example/start" },
  { id: "W1", type: "service_worker", title: "sw", url: "https://shop.example/sw.js" },
];

/** @type {import("./stream-protocol.mjs").RecordRequest} */
const REQUEST = {
  browserURL: "http://127.0.0.1:9582",
  page: null,
  allPages: false,
  bodies: false,
  maxBody: 4096,
  redact: ["ssn"],
  binding: "__akmonRecord",
};

const flush = () => new Promise((resolve) => setImmediate(resolve));

/**
 * A fake Chrome with one session per page target (`S-<target id>`), that answers what `replies` says and
 * delivers the events a test sends.
 * @param {{targets?: object[], replies?: Record<string, (params: any, sessionId?: string) => unknown>}} [given]
 */
function fakeBrowser(given = {}) {
  /** @type {{method: string, params: any, sessionId?: string}[]} */
  const calls = [];
  /** @type {import("./cdp.mjs").Transport} */
  const transport = { send: () => {}, close: () => {}, onmessage: null, onclose: null };
  const replies = given.replies ?? {};
  transport.send = (text) => {
    const { id, method, params, sessionId } = JSON.parse(text);
    calls.push({ method, params, ...(sessionId === undefined ? {} : { sessionId }) });
    /** @type {any} */
    let result = {};
    if (method === "Target.attachToTarget") {
      result = { sessionId: `S-${params.targetId}` };
    } else if (method === "Page.addScriptToEvaluateOnNewDocument") {
      result = { identifier: `script-${sessionId}` };
    } else if (method === "Page.getFrameTree") {
      result = { frameTree: { frame: { id: `F-${sessionId}` } } };
    } else if (replies[method] !== undefined) {
      result = replies[method](params, sessionId);
    }
    setImmediate(() => transport.onmessage?.(JSON.stringify({ id, result })));
  };
  const targets = given.targets ?? TARGETS;
  const deps = {
    fetchJson: async (/** @type {string} */ url) =>
      url.endsWith("/json/list") ? targets : { webSocketDebuggerUrl: "ws://fake/browser" },
    open: async () => transport,
    now: () => clock.value,
  };
  const clock = { value: 1_000_000 };
  return {
    calls,
    deps,
    clock,
    page: (/** @type {string} */ sessionId, /** @type {string} */ method, /** @type {unknown} */ params) =>
      transport.onmessage?.(JSON.stringify({ method, params, sessionId })),
    browser: (/** @type {string} */ method, /** @type {unknown} */ params) =>
      transport.onmessage?.(JSON.stringify({ method, params })),
    end: () => transport.onclose?.("the browser closed the connection"),
    methods: (/** @type {string} */ session) =>
      calls.filter((call) => call.sessionId === session).map((call) => call.method),
  };
}

/**
 * Start a recording on a fake browser and collect what it emits.
 * @param {ReturnType<typeof fakeBrowser>} chrome
 * @param {Partial<import("./stream-protocol.mjs").RecordRequest>} [request]
 */
async function recording(chrome, request = {}) {
  /** @type {{event: Record<string, any>, ago: number}[]} */
  const emitted = [];
  const handle = await startRecording({ ...REQUEST, ...request }, chrome.deps, (event, ago = 0) =>
    emitted.push({ event, ago }),
  );
  return { handle, emitted, kinds: () => emitted.map((entry) => entry.event["kind"]) };
}

test("it attaches to the first page, enables the domains and injects the binding and the listener on every document and the open one", async () => {
  const chrome = fakeBrowser();
  const { handle, emitted } = await recording(chrome);
  assert.deepEqual(handle.pages, ["p1"]);
  const methods = chrome.methods("S-T1");
  for (const method of ["Page.enable", "Runtime.enable", "Network.enable", "Log.enable", "Runtime.addBinding"]) {
    assert.ok(methods.includes(method), method);
  }
  const added = chrome.calls.find((call) => call.method === "Page.addScriptToEvaluateOnNewDocument");
  const opened = chrome.calls.find((call) => call.method === "Runtime.evaluate");
  assert.equal(added?.params.source, opened?.params.expression);
  assert.match(added?.params.source, /__akmonRecord/);
  assert.match(added?.params.source, /"ssn"/);
  assert.equal(
    chrome.calls.some((call) => call.sessionId === "S-T2"),
    false,
  );
  assert.deepEqual(emitted[0].event, {
    kind: "page",
    page: "p1",
    url: `https://shop.example/cart?token=${REDACTED}&x=1`,
    title: "Shop",
  });
  await handle.stop();
});

test("--page picks the page by index, id or URL part, and a missing one is refused", async () => {
  const chrome = fakeBrowser();
  const { handle } = await recording(chrome, { page: "docs" });
  assert.ok(chrome.calls.some((call) => call.method === "Target.attachToTarget" && call.params.targetId === "T2"));
  await handle.stop();
  await assert.rejects(recording(fakeBrowser(), { page: "nowhere" }), /no page matches/);
  await assert.rejects(recording(fakeBrowser({ targets: [] })), /no open page/);
});

test("navigations of the main frame are recorded with their URL redacted, a subframe's are not, a same-document one says so", async () => {
  const chrome = fakeBrowser();
  const { handle, emitted } = await recording(chrome);
  chrome.page("S-T1", "Page.frameNavigated", {
    frame: { id: "F-S-T1", url: "https://shop.example/pay?password=p&a=1" },
  });
  chrome.page("S-T1", "Page.frameNavigated", { frame: { id: "F9", parentId: "F-S-T1", url: "https://ads.example/" } });
  chrome.page("S-T1", "Page.navigatedWithinDocument", { frameId: "F-S-T1", url: "https://shop.example/pay#step2" });
  chrome.page("S-T1", "Page.navigatedWithinDocument", { frameId: "F9", url: "https://ads.example/#x" });
  const navigations = emitted.filter((entry) => entry.event["kind"] === "navigation").map((entry) => entry.event);
  assert.deepEqual(navigations, [
    { kind: "navigation", page: "p1", url: `https://shop.example/pay?password=${REDACTED}&a=1` },
    { kind: "navigation", page: "p1", url: "https://shop.example/pay#step2", within: true },
  ]);
  await handle.stop();
});

test("the listener's events come through the binding as checked user events; a forged or foreign call is dropped", async () => {
  const chrome = fakeBrowser();
  const { handle, emitted } = await recording(chrome);
  const send = (/** @type {string} */ name, /** @type {unknown} */ payload) =>
    chrome.page("S-T1", "Runtime.bindingCalled", {
      name,
      payload: typeof payload === "string" ? payload : JSON.stringify(payload),
    });
  send("__akmonRecord", { kind: "click", target: { tag: "button", role: "button", name: "Pay", testid: "pay" } });
  send("__akmonRecord", {
    kind: "input",
    target: { tag: "input", type: "password", nameAttr: "pw" },
    length: 9,
    value: "hunter2",
  });
  send("__akmonRecord", { kind: "eval", target: {} });
  send("__akmonRecord", "not json");
  send("somethingElse", { kind: "click", target: {} });
  const events = emitted.map((entry) => entry.event).filter((event) => event["kind"] !== "page");
  assert.equal(events.length, 2);
  assert.equal(events[0]["kind"], "click");
  assert.equal(events[0]["page"], "p1");
  assert.equal(events[0]["target"].testid, "pay");
  assert.equal(events[1]["length"], null);
  assert.equal(events[1]["target"].sensitive, true);
  assert.equal(JSON.stringify(events).includes("hunter2"), false);
  await handle.stop();
});

test("console lines, exceptions and log entries are recorded with secrets scrubbed", async () => {
  const chrome = fakeBrowser();
  const { handle, emitted } = await recording(chrome);
  chrome.page("S-T1", "Runtime.consoleAPICalled", {
    type: "error",
    args: [
      { type: "string", value: "login failed" },
      { type: "string", value: "token=abc123" },
    ],
  });
  chrome.page("S-T1", "Runtime.exceptionThrown", {
    exceptionDetails: { exception: { description: "TypeError: x is undefined\n    at pay (app.js:1)" } },
  });
  chrome.page("S-T1", "Log.entryAdded", {
    entry: { source: "network", level: "error", text: "Failed to load", url: "https://api.example/x?api_key=k1" },
  });
  const [consoleLine, exception, log] = emitted.slice(1).map((entry) => entry.event);
  assert.deepEqual(consoleLine, {
    kind: "console",
    page: "p1",
    level: "error",
    text: `login failed token=${REDACTED}`,
  });
  assert.equal(exception["kind"], "exception");
  assert.match(exception["text"], /TypeError: x is undefined/);
  assert.equal(log["text"], `Failed to load (https://api.example/x?api_key=${REDACTED})`);
  await handle.stop();
});

/**
 * Send the events of one request.
 * @param {ReturnType<typeof fakeBrowser>} chrome
 * @param {{id: string, method?: string, url: string, headers?: Record<string, string>, postData?: string, type?: string, status?: number, mime?: string, respHeaders?: Record<string, string>, fail?: string}} request
 */
function request(chrome, request) {
  chrome.page("S-T1", "Network.requestWillBeSent", {
    requestId: request.id,
    type: request.type ?? "Fetch",
    timestamp: 10,
    request: {
      url: request.url,
      method: request.method ?? "GET",
      headers: request.headers ?? {},
      ...(request.postData === undefined ? {} : { postData: request.postData }),
    },
  });
  if (request.fail !== undefined) {
    chrome.page("S-T1", "Network.loadingFailed", { requestId: request.id, timestamp: 10.1, errorText: request.fail });
    return;
  }
  chrome.page("S-T1", "Network.responseReceived", {
    requestId: request.id,
    type: request.type ?? "Fetch",
    response: {
      url: request.url,
      status: request.status ?? 200,
      mimeType: request.mime ?? "application/json",
      headers: request.respHeaders ?? {},
    },
  });
  chrome.page("S-T1", "Network.loadingFinished", { requestId: request.id, timestamp: 10.25, encodedDataLength: 77 });
}

test("a request is recorded when it ends: method, URL, status, type, timing, with the URL and the headers redacted and how long ago it began", async () => {
  const chrome = fakeBrowser();
  const { handle, emitted } = await recording(chrome);
  chrome.page("S-T1", "Network.requestWillBeSent", {
    requestId: "R1",
    type: "XHR",
    timestamp: 10,
    request: {
      url: "https://api.example/orders?access_token=zzz&page=2",
      method: "POST",
      headers: { Authorization: "Bearer s3cret", Accept: "*/*" },
    },
  });
  chrome.clock.value += 300;
  chrome.page("S-T1", "Network.responseReceived", {
    requestId: "R1",
    type: "XHR",
    response: {
      status: 502,
      mimeType: "application/json",
      headers: { "Set-Cookie": "sid=1", "Content-Type": "application/json" },
    },
  });
  chrome.page("S-T1", "Network.loadingFinished", { requestId: "R1", timestamp: 10.3, encodedDataLength: 120 });
  await flush();
  const entry = emitted.at(-1);
  assert.equal(entry?.ago, 300);
  assert.deepEqual(entry?.event, {
    kind: "net",
    page: "p1",
    id: "R1",
    method: "POST",
    url: `https://api.example/orders?access_token=${REDACTED}&page=2`,
    status: 502,
    type: "XHR",
    mime: "application/json",
    size: 120,
    ms: 300,
    failure: null,
    requestHeaders: { Authorization: REDACTED, Accept: "*/*" },
    responseHeaders: { "Set-Cookie": REDACTED, "Content-Type": "application/json" },
  });
  await handle.stop();
});

test("a request that fails is recorded with its failure, and a redirect is two requests", async () => {
  const chrome = fakeBrowser();
  const { handle, emitted } = await recording(chrome);
  request(chrome, { id: "R1", url: "https://api.example/down", fail: "net::ERR_CONNECTION_REFUSED" });
  chrome.page("S-T1", "Network.requestWillBeSent", {
    requestId: "R2",
    timestamp: 1,
    type: "Document",
    request: { url: "http://shop.example/", method: "GET" },
  });
  chrome.page("S-T1", "Network.requestWillBeSent", {
    requestId: "R2",
    timestamp: 2,
    type: "Document",
    redirectResponse: { status: 301, headers: {} },
    request: { url: "https://shop.example/", method: "GET" },
  });
  await flush();
  const nets = emitted.map((entry) => entry.event).filter((event) => event["kind"] === "net");
  assert.equal(nets[0]["failure"], "net::ERR_CONNECTION_REFUSED");
  assert.deepEqual(
    nets.slice(1).map((event) => [event["url"], event["status"]]),
    [["http://shop.example/", 301]],
  );
  await handle.stop();
});

test("without --bodies no body is read or kept", async () => {
  const chrome = fakeBrowser({ replies: { "Network.getResponseBody": () => ({ body: '{"a":1}' }) } });
  const { handle, emitted } = await recording(chrome);
  request(chrome, {
    id: "R1",
    url: "https://api.example/x",
    method: "POST",
    postData: '{"a":1}',
    headers: { "content-type": "application/json" },
  });
  await flush();
  const net = emitted.at(-1)?.event ?? {};
  assert.equal("body" in net || "requestBody" in net, false);
  assert.equal(
    chrome.calls.some((call) => call.method === "Network.getResponseBody"),
    false,
  );
  await handle.stop();
});

test("with --bodies a JSON or form body is kept redacted and capped; any other type is noted, not kept", async () => {
  /** @type {Record<string, string>} */
  const answers = {
    R1: '{"user":"ann","password":"hunter2","nested":{"token":"t","n":1}}',
    R3: JSON.stringify({ rows: "x".repeat(5000) }),
  };
  const chrome = fakeBrowser({
    replies: { "Network.getResponseBody": (/** @type {any} */ params) => ({ body: answers[params.requestId] ?? "" }) },
  });
  const { handle, emitted } = await recording(chrome, { bodies: true, maxBody: 200 });
  request(chrome, {
    id: "R1",
    url: "https://api.example/login",
    method: "POST",
    postData: "user=ann&password=hunter2&city=Bern",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
  });
  request(chrome, { id: "R2", url: "https://api.example/page", mime: "text/html" });
  request(chrome, { id: "R3", url: "https://api.example/big" });
  await flush();
  await flush();
  const nets = emitted.map((entry) => entry.event).filter((event) => event["kind"] === "net");
  const byUrl = (/** @type {string} */ url) => nets.find((event) => event["url"] === url) ?? {};
  const login = byUrl("https://api.example/login");
  assert.equal(login["requestBody"], `user=ann&password=${REDACTED}&city=Bern`);
  assert.equal(login["body"], `{"user":"ann","password":"${REDACTED}","nested":{"token":"${REDACTED}","n":1}}`);
  assert.match(String(byUrl("https://api.example/page")["bodyNote"]), /not kept \(text\/html\)/);
  const big = byUrl("https://api.example/big");
  assert.equal(big["bodyTruncated"], true);
  assert.equal(String(big["body"]).length, 200);
  assert.equal(JSON.stringify(nets).includes("hunter2"), false);
  await handle.stop();
});

test("a request body that is not JSON or a form is noted and never kept, because it could not be redacted", async () => {
  const chrome = fakeBrowser();
  const { handle, emitted } = await recording(chrome, { bodies: true });
  request(chrome, {
    id: "R1",
    url: "https://api.example/upload",
    method: "POST",
    postData: "--b\r\nContent-Disposition: form-data; name=token\r\n\r\nsecret\r\n--b--",
    headers: { "Content-Type": "multipart/form-data; boundary=b" },
    mime: "text/plain",
  });
  await flush();
  const net = emitted.at(-1)?.event ?? {};
  assert.match(String(net["requestBodyNote"]), /multipart\/form-data/);
  assert.equal(JSON.stringify(net).includes("secret"), false);
  await handle.stop();
});

test("the redaction floor holds whatever the request's own list says: an empty list still redacts password and token", async () => {
  const chrome = fakeBrowser({
    replies: { "Network.getResponseBody": () => ({ body: '{"password":"p","access_token":"t","ok":true}' }) },
  });
  const { handle, emitted } = await recording(chrome, { redact: [], bodies: true });
  request(chrome, {
    id: "R1",
    url: "https://api.example/x?api_key=k&password=p",
    method: "POST",
    postData: '{"token":"t"}',
    headers: { "content-type": "application/json" },
  });
  await flush();
  const text = JSON.stringify(emitted.map((entry) => entry.event));
  for (const secret of ['"p"', '"t"', "api_key=k", "password=p"]) {
    assert.equal(text.includes(secret), false, secret);
  }
  assert.ok(text.includes(REDACTED));
  await handle.stop();
});

test("with --all-pages every page is followed, and a page that opens later is attached; other targets are not", async () => {
  const chrome = fakeBrowser();
  const { handle, emitted } = await recording(chrome, { allPages: true });
  assert.deepEqual(handle.pages, ["p1", "p2"]);
  assert.ok(chrome.calls.some((call) => call.method === "Target.setDiscoverTargets"));
  chrome.browser("Target.targetCreated", {
    targetInfo: { targetId: "T3", type: "page", title: "Pop", url: "https://pop.example/" },
  });
  chrome.browser("Target.targetCreated", {
    targetInfo: { targetId: "W2", type: "service_worker", title: "", url: "https://w/" },
  });
  await flush();
  await flush();
  assert.ok(chrome.calls.some((call) => call.method === "Target.attachToTarget" && call.params.targetId === "T3"));
  assert.equal(
    chrome.calls.some((call) => call.method === "Target.attachToTarget" && call.params.targetId === "W2"),
    false,
  );
  chrome.page("S-T2", "Runtime.consoleAPICalled", { type: "log", args: [{ type: "string", value: "hi" }] });
  assert.equal(emitted.at(-1)?.event["page"], "p2");
  await handle.stop();
});

test("a recorded page that closes ends a one-page recording; with --all-pages it only goes quiet", async () => {
  const one = fakeBrowser();
  const single = await recording(one);
  one.browser("Target.targetDestroyed", { targetId: "T1" });
  assert.deepEqual(await single.handle.ended, { reason: "closed", error: null });
  assert.ok(single.emitted.some((entry) => entry.event["kind"] === "warning"));
  const many = fakeBrowser();
  const all = await recording(many, { allPages: true });
  many.browser("Target.targetDestroyed", { targetId: "T1" });
  many.browser("Target.targetDestroyed", { targetId: "T2" });
  const outcome = await Promise.race([all.handle.ended, flush().then(() => "still running")]);
  assert.equal(outcome, "still running");
  await all.handle.stop();
});

test("stop takes the listener out where it can: removes the script, disposes the open document's, removes the binding, detaches, and nothing more is emitted", async () => {
  const chrome = fakeBrowser();
  const { handle, emitted } = await recording(chrome);
  await handle.stop();
  const after = chrome.calls
    .slice(chrome.calls.findLastIndex((call) => call.method === "Runtime.evaluate") - 1)
    .map((call) => call.method);
  assert.deepEqual(after.slice(-4), [
    "Page.removeScriptToEvaluateOnNewDocument",
    "Runtime.evaluate",
    "Runtime.removeBinding",
    "Target.detachFromTarget",
  ]);
  assert.equal(
    chrome.calls.find((call) => call.method === "Page.removeScriptToEvaluateOnNewDocument")?.params.identifier,
    "script-S-T1",
  );
  const dispose = chrome.calls.filter((call) => call.method === "Runtime.evaluate").at(-1);
  assert.match(dispose?.params.expression, /dispose/);
  assert.deepEqual(await handle.ended, { reason: "stopped", error: null });
  const count = emitted.length;
  chrome.page("S-T1", "Runtime.consoleAPICalled", { type: "log", args: [] });
  assert.equal(emitted.length, count);
});

test("the browser going away ends the recording as closed", async () => {
  const chrome = fakeBrowser();
  const { handle } = await recording(chrome);
  chrome.end();
  assert.deepEqual(await handle.ended, { reason: "closed", error: null });
});

test("a sink that fails ends the recording as an error, because events would be lost", async () => {
  const chrome = fakeBrowser();
  const handle = await startRecording(REQUEST, chrome.deps, (event) => {
    if (event["kind"] === "console") {
      throw new Error("disk full");
    }
  });
  chrome.page("S-T1", "Runtime.consoleAPICalled", { type: "log", args: [{ type: "string", value: "x" }] });
  const outcome = await handle.ended;
  assert.equal(outcome.reason, "error");
  assert.match(String(outcome.error), /disk full/);
  await handle.stop();
});

test("a listener that cannot be installed is a warning: the rest is still recorded", async () => {
  const chrome = fakeBrowser({
    replies: {
      "Runtime.evaluate": () => ({
        exceptionDetails: { text: "Uncaught", exception: { description: "SyntaxError: nope" } },
      }),
    },
  });
  const { handle, emitted } = await recording(chrome);
  const warning = emitted.map((entry) => entry.event).find((event) => event["kind"] === "warning");
  assert.match(String(warning?.["text"]), /listener could not be installed.*SyntaxError: nope/);
  await handle.stop();
});
