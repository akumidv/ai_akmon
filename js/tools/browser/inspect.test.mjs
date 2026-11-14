import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { posix } from "node:path";

import { buildContext } from "./context.mjs";
import {
  chooseSide,
  evalCommand,
  hostWord,
  logsCommand,
  netCommand,
  outputPath,
  pagesCommand,
  parseRegistry,
  resolveViewport,
  runOperations,
  screenshotCommand,
  selectorsCommand,
  snapshotCommand,
} from "./inspect.mjs";
import { runRequest } from "./ops.mjs";
import { UsageError } from "./arguments.mjs";
import { BrowserError, DEFAULT_VIEWPORTS } from "./settings.mjs";
import { fakeChrome, fakeHost, tempProject } from "./support.test.mjs";

/**
 * A context over a throwaway project, an inspector over a fake Chrome, and what was said.
 * @param {ReturnType<typeof fakeChrome>} chrome
 * @param {string} [record]
 */
function setup(chrome, record = "") {
  const project = tempProject(record);
  /** @type {string[]} */
  const said = [];
  const ctx = buildContext(project.root, { env: {}, host: fakeHost(), say: (line) => said.push(line) });
  /** @type {import("./protocol.mjs").Request[]} */
  const requests = [];
  /** @type {import("./inspect.mjs").Inspector} */
  const how = {
    locate: async () => ({ browserURL: "http://127.0.0.1:9582", port: 9582, mode: "own", side: "here" }),
    targets: async () => await chrome.deps.fetchJson("http://127.0.0.1:9582/json/list"),
    execute: (_browser, request) => {
      requests.push(request);
      return runRequest(request, chrome.deps);
    },
  };
  return { ctx, said, how, requests, root: project.root, dispose: project.dispose };
}

test("the side is here when Chrome answers here, Windows under WSL when only Windows reaches it, else a refusal", () => {
  assert.equal(chooseSide({ isWsl: false, answersHere: true, port: 9582 }), "here");
  assert.equal(chooseSide({ isWsl: true, answersHere: true, port: 9582 }), "here");
  assert.equal(chooseSide({ isWsl: true, answersHere: false, port: 9582 }), "windows");
  assert.throws(
    () => chooseSide({ isWsl: false, answersHere: false, port: 9582 }),
    (error) => error instanceof BrowserError && /127\.0\.0\.1:9582 does not answer from here/.test(error.message),
  );
});

test("a viewport is WxH, a preset or a project name; an unknown one is a usage error listing the names", () => {
  assert.deepEqual(resolveViewport("phone", DEFAULT_VIEWPORTS), {
    viewport: { width: 390, height: 844 },
    label: "phone",
  });
  assert.deepEqual(resolveViewport("1280x720", DEFAULT_VIEWPORTS), {
    viewport: { width: 1280, height: 720 },
    label: "1280x720",
  });
  assert.deepEqual(resolveViewport(null, DEFAULT_VIEWPORTS), { viewport: null, label: "native" });
  assert.deepEqual(resolveViewport("wide", { wide: { width: 1920, height: 1080 } }).viewport, {
    width: 1920,
    height: 1080,
  });
  assert.throws(
    () => resolveViewport("huge", DEFAULT_VIEWPORTS),
    (error) =>
      error instanceof UsageError && /"huge" is neither WxH nor one of desktop, tablet, phone/.test(error.message),
  );
  assert.throws(() => resolveViewport("constructor", DEFAULT_VIEWPORTS), UsageError);
});

test("a file name is the page's host, and an output path is a bare name, a path or a folder", () => {
  assert.equal(hostWord("https://Shop.Example:8443/cart"), "shop.example");
  assert.equal(hostWord("data:text/html,hi"), "page");
  assert.equal(hostWord("not a url"), "page");
  const where = { root: "/p", folder: "/p/_aitna/.local/.browser/shots", name: "h-phone.png", always: true };
  assert.equal(outputPath(null, where), "/p/_aitna/.local/.browser/shots/h-phone.png");
  assert.equal(outputPath(null, { ...where, always: false }), null);
  assert.equal(outputPath("a.png", where), "/p/_aitna/.local/.browser/shots/a.png");
  assert.equal(outputPath("out/a.png", where), "/p/out/a.png");
  assert.equal(outputPath("/abs/a.png", where), "/abs/a.png");
  assert.equal(outputPath("out/", where), "/p/out/h-phone.png");
});

test("pages lists the page targets numbered, and with --all the others; --json prints the rows", async () => {
  const { ctx, said, how, dispose } = setup(fakeChrome());
  try {
    assert.equal(await pagesCommand(ctx, { all: false, json: false }, how), 0);
    assert.equal(said.length, 2);
    assert.match(said[1], /^ 1 {2}T2 {2}page .*Docs/);
    said.length = 0;
    await pagesCommand(ctx, { all: true, json: true }, how);
    const rows = JSON.parse(said.join("\n"));
    assert.deepEqual(
      rows.map((/** @type {any} */ row) => [row.index, row.type]),
      [
        [0, "page"],
        [1, "page"],
        [null, "service_worker"],
      ],
    );
  } finally {
    dispose();
  }
});

test("snapshot prints the outline, --text the visible text and --json the data", async () => {
  const chrome = fakeChrome({
    "Accessibility.getFullAXTree": () => ({
      nodes: [{ nodeId: "1", role: { value: "RootWebArea" }, name: { value: "Shop" } }],
    }),
    "Runtime.evaluate": () => ({ result: { type: "string", value: "Hello" } }),
  });
  const { ctx, said, how, dispose } = setup(chrome);
  try {
    const options = { page: null, json: false, maxNodes: null, text: false };
    await snapshotCommand(ctx, options, how);
    assert.deepEqual(said, ['RootWebArea "Shop"']);
    said.length = 0;
    await snapshotCommand(ctx, { ...options, text: true }, how);
    assert.deepEqual(said, ["Hello"]);
    said.length = 0;
    await snapshotCommand(ctx, { ...options, json: true }, how);
    assert.equal(JSON.parse(said[0]).lines[0].role, "RootWebArea");
  } finally {
    dispose();
  }
});

test("screenshot writes <host>-<viewport>.png under the browser's shots folder and prints the path", async () => {
  const png = Buffer.from("not really a png").toString("base64");
  const chrome = fakeChrome({
    "Page.captureScreenshot": () => ({ data: png }),
    "Page.getLayoutMetrics": () => ({ cssContentSize: { width: 800, height: 2000 } }),
  });
  const { ctx, said, how, dispose } = setup(chrome);
  try {
    const options = { page: null, viewport: "phone", scheme: /** @type {"dark"} */ ("dark"), full: false, out: null };
    assert.equal(await screenshotCommand(ctx, options, how), 0);
    const expected = posix.join(ctx.project.browserDir, "shots", "shop.example-phone-dark.png");
    assert.deepEqual(said, [expected]);
    assert.equal(fs.readFileSync(expected, "utf8"), "not really a png");
    assert.deepEqual(
      chrome.calls.find((call) => call.method === "Emulation.setDeviceMetricsOverride")?.params.width,
      390,
    );
    said.length = 0;
    const custom = posix.join(ctx.project.root, "shot.png");
    await screenshotCommand(ctx, { ...options, viewport: null, scheme: null, full: true, out: "shot.png" }, how);
    assert.deepEqual(said, [posix.join(ctx.project.browserDir, "shots", "shot.png")]);
    said.length = 0;
    await screenshotCommand(ctx, { ...options, viewport: "tablet", scheme: null, out: "./shot.png" }, how);
    assert.deepEqual(said, [custom]);
  } finally {
    dispose();
  }
});

test("a [browser].viewports name is a viewport; an emulation that cannot be undone makes the exit 1 and says so", async () => {
  const chrome = fakeChrome({
    "Page.captureScreenshot": () => ({ data: "eA==" }),
    "Emulation.clearDeviceMetricsOverride": () => {
      throw new Error("gone");
    },
  });
  const { ctx, said, how, dispose } = setup(chrome, '[browser.viewports]\nwide = "1920x1080"\n');
  try {
    const code = await screenshotCommand(
      ctx,
      { page: null, viewport: "wide", scheme: null, full: false, out: null },
      how,
    );
    assert.equal(code, 1);
    assert.match(said[0], /shop\.example-wide\.png$/);
    assert.match(said[1], /^warning: Emulation\.clearDeviceMetricsOverride failed/);
    assert.equal(
      chrome.calls.find((call) => call.method === "Emulation.setDeviceMetricsOverride")?.params.height,
      1080,
    );
  } finally {
    dispose();
  }
});

test("pages and the selectors line print a URL with its secret parameters redacted", async () => {
  const targets = [{ id: "T1", type: "page", title: "Cb", url: "https://app.example/cb#access_token=SECRETT" }];
  const { ctx, said, how, dispose } = setup(fakeChrome({}, { targets }));
  try {
    await pagesCommand(ctx, { all: false, json: false }, how);
    await pagesCommand(ctx, { all: false, json: true }, how);
    assert.ok(!said.join("\n").includes("SECRETT"));
    assert.ok(said.join("\n").includes("access_token=[redacted]"));
  } finally {
    dispose();
  }
});

test("eval prints the value, and an exception is a refusal carrying its text", async () => {
  const chrome = fakeChrome({
    "Runtime.evaluate": (params) =>
      params.expression === "bad"
        ? {
            result: { type: "object" },
            exceptionDetails: { text: "Uncaught", exception: { description: "ReferenceError: bad" } },
          }
        : { result: { type: "string", value: "Shop" } },
  });
  const { ctx, said, how, dispose } = setup(chrome);
  try {
    assert.equal(await evalCommand(ctx, { page: null, json: false, expression: "document.title" }, how), 0);
    assert.deepEqual(said, ["Shop"]);
    await assert.rejects(
      evalCommand(ctx, { page: null, json: false, expression: "bad" }, how),
      (error) => error instanceof BrowserError && /the expression threw: ReferenceError: bad/.test(error.message),
    );
  } finally {
    dispose();
  }
});

test("logs print the held messages then end at the time (0), or at an unmet --until (1)", async () => {
  const make = () =>
    fakeChrome({
      "Runtime.enable": (_params, control) => {
        control.emit("Runtime.consoleAPICalled", {
          type: "warning",
          args: [{ type: "string", value: "careful" }],
          timestamp: 999_000,
        });
        return {};
      },
    });
  const { ctx, said, how, dispose } = setup(make());
  try {
    const plain = { page: null, until: null, timeout: 0.05, json: false };
    assert.equal(await logsCommand(ctx, plain, how), 0);
    assert.deepEqual(said, ["   -1.00s [page] console.warning: careful", "timeout after 0.05 s"]);
    said.length = 0;
    assert.equal(await logsCommand(ctx, { ...plain, until: "never" }, how), 1);
    assert.equal(said.at(-1), "timeout after 0.05 s; /never/ did not match");
    said.length = 0;
    assert.equal(await logsCommand(ctx, { ...plain, json: true }, how), 0);
    assert.equal(JSON.parse(said.join("\n")).entries[0].text, "careful");
  } finally {
    dispose();
  }
});

test("net prints the requests redacted, writes --out as JSON and keeps secrets out of both", async () => {
  const chrome = fakeChrome({
    "Network.getResponseBody": () => ({ body: '{"ok":true,"token":"SECRETJ"}', base64Encoded: false }),
  });
  const { ctx, said, how, dispose } = setup(chrome);
  try {
    setTimeout(() => {
      const url = "https://shop.example/api?access_token=SECRETQ";
      chrome.emit("Network.requestWillBeSent", {
        requestId: "1",
        timestamp: 1,
        type: "Fetch",
        request: { url, method: "GET", headers: { Authorization: "Bearer SECRETH" } },
      });
      chrome.emit("Network.responseReceived", {
        requestId: "1",
        type: "Fetch",
        response: { url, status: 404, mimeType: "application/json", headers: {} },
      });
      chrome.emit("Network.loadingFinished", { requestId: "1", timestamp: 1.1, encodedDataLength: 30 });
    }, 5);
    const options = {
      page: null,
      forSeconds: 0.1,
      until: null,
      failed: true,
      bodies: true,
      maxBody: null,
      out: "n.json",
      json: false,
    };
    assert.equal(await netCommand(ctx, options, how), 0);
    const file = posix.join(ctx.project.browserDir, "net", "n.json");
    const written = fs.readFileSync(file, "utf8");
    const printed = said.join("\n");
    for (const secret of ["SECRETH", "SECRETQ", "SECRETJ"]) {
      assert.ok(!written.includes(secret) && !printed.includes(secret), secret);
    }
    assert.equal(JSON.parse(written).entries[0].body, '{"ok":true,"token":"[redacted]"}');
    assert.equal(JSON.parse(written).page.url, "https://shop.example/cart");
    assert.match(
      said[0],
      /^GET {4}404 {2}Fetch {2}application\/json {2}30B {2}100ms {2}https:\/\/shop\.example\/api\?access_token=\[redacted\]$/,
    );
    assert.ok(said.includes("1 request(s) failed in the capture"));
    assert.ok(said.includes(`wrote ${file}`));
    assert.ok(!said.some((line) => line.includes("body")), "bodies go to the file when --out is given");
  } finally {
    dispose();
  }
});

test("net with nothing to say still says so, and a closed browser is a refusal", async () => {
  const { ctx, said, how, dispose } = setup(fakeChrome());
  try {
    assert.equal(
      await netCommand(
        ctx,
        {
          page: null,
          forSeconds: 0.05,
          until: null,
          failed: false,
          bodies: false,
          maxBody: null,
          out: null,
          json: false,
        },
        how,
      ),
      0,
    );
    assert.deepEqual(said, ["0 request(s) in the capture", "timeout after 0.05 s"]);
  } finally {
    dispose();
  }
  const chrome = fakeChrome({
    "Network.enable": () => {
      setTimeout(() => chrome.end(), 5);
      return {};
    },
  });
  const second = setup(chrome);
  try {
    await assert.rejects(
      netCommand(
        second.ctx,
        { page: null, forSeconds: 5, until: null, failed: false, bodies: false, maxBody: null, out: null, json: false },
        second.how,
      ),
      /the browser closed the connection before the capture ended/,
    );
  } finally {
    second.dispose();
  }
});

test("eval, logs and net send the target, the extension and the world they were given, the page as before", async () => {
  const chrome = fakeChrome({ "Runtime.evaluate": () => ({ result: { type: "string", value: "x" } }) });
  const { ctx, how, requests, dispose } = setup(chrome);
  try {
    await evalCommand(ctx, { page: "docs", json: false, expression: "1" }, how);
    assert.deepEqual(
      [requests[0].page, requests[0].target, requests[0].ext, requests[0].operations[0]],
      ["docs", "page", null, { op: "eval", expression: "1", world: "page" }],
    );
    await assert.rejects(
      evalCommand(
        ctx,
        { page: null, json: false, expression: "1", target: "sw", ext: "Bench", world: "isolated" },
        how,
      ),
      BrowserError,
    );
    assert.deepEqual(
      [requests[1].target, requests[1].ext, requests[1].operations[0]],
      ["sw", "Bench", { op: "eval", expression: "1", world: "isolated" }],
    );
    await assert.rejects(
      logsCommand(ctx, { page: null, until: null, timeout: 0.05, json: false, target: "popup", ext: "x" }, how),
      BrowserError,
    );
    assert.deepEqual([requests[2].target, requests[2].ext], ["popup", "x"]);
  } finally {
    dispose();
  }
});

test("the configured extension folders go with a request, as the Chrome spells them: converted for a Windows Chrome", async () => {
  const { root, dispose } = tempProject('[browser]\nextensions = ["ext"]\n');
  fs.mkdirSync(posix.join(root, "ext"));
  fs.writeFileSync(posix.join(root, "ext", "manifest.json"), "{}");
  try {
    /** @type {import("./protocol.mjs").Request[]} */
    const requests = [];
    const ctx = buildContext(root, { env: {}, host: fakeHost(), say: () => {} });
    /** @type {import("./inspect.mjs").Inspector} */
    const how = {
      locate: async () => ({ browserURL: "http://127.0.0.1:9582", port: 9582, mode: "own", side: "windows" }),
      targets: async () => [],
      execute: async (_browser, request) => {
        requests.push(request);
        return { results: [{ ok: true, value: {} }] };
      },
      toChromePath: (path) => `\\\\wsl.localhost\\Ubuntu${path.replaceAll("/", "\\")}`,
    };
    await runOperations(ctx, how, { page: null, operations: [{ op: "ext-list" }] });
    assert.deepEqual(requests[0].extensionPaths, [
      `\\\\wsl.localhost\\Ubuntu${posix.join(root, "ext").replaceAll("/", "\\")}`,
    ]);
    const here = {
      ...how,
      locate: async () => ({
        browserURL: "http://127.0.0.1:9582",
        port: 9582,
        mode: /** @type {const} */ ("own"),
        side: /** @type {const} */ ("here"),
      }),
    };
    await runOperations(ctx, here, { page: null, operations: [{ op: "ext-list" }] });
    assert.deepEqual(requests[1].extensionPaths, [posix.join(root, "ext")]);
  } finally {
    dispose();
  }
});

test("a selector registry is a JSON object of name -> non-empty list of selectors, or a refusal naming the file and the name", () => {
  assert.deepEqual(parseRegistry('{"buy": [".buy", ".buy-v2"]}', "r.json"), { buy: [".buy", ".buy-v2"] });
  /** @type {[string, RegExp][]} */
  const bad = [
    ["nope", /r\.json is not JSON/],
    ["[]", /must be a JSON object of name -> list of CSS selectors/],
    ["{}", /at least one name/],
    ['{"a": ".x"}', /r\.json: "a" must be a non-empty list/],
    ['{"a": []}', /"a" must be a non-empty list/],
    ['{"a": [""]}', /"a" must be a non-empty list/],
    ['{"a": [1]}', /"a" must be a non-empty list/],
  ];
  for (const [text, pattern] of bad) {
    assert.throws(
      () => parseRegistry(text, "r.json"),
      (error) => error instanceof BrowserError && pattern.test(error.message) && !error.message.includes("\n"),
      text,
    );
  }
});

/**
 * A fake Chrome that answers the page script of a registry from the counts it is given.
 * @param {Record<string, number[]>} counts selector counts by registry name
 */
function selectorChrome(counts) {
  return fakeChrome({
    "Runtime.evaluate": () => ({
      result: {
        type: "object",
        value: Object.fromEntries(
          Object.entries(counts).map(([name, list]) => [name, { counts: list, errors: list.map(() => null) }]),
        ),
      },
    }),
  });
}

test("selectors reads the registry file under the project root and exits 1 when a name is missing", async () => {
  const { ctx, said, how, root, dispose } = setup(selectorChrome({ buy: [2], title: [0, 4], gone: [0] }));
  try {
    fs.writeFileSync(
      posix.join(root, "selectors.json"),
      JSON.stringify({ buy: [".buy"], title: ["#t", "h1"], gone: [".gone"] }),
    );
    assert.equal(await selectorsCommand(ctx, { file: "selectors.json", page: null, json: false }, how), 1);
    assert.deepEqual(said, [
      "matched                buy  .buy (2)",
      "matched by fallback 1  title  h1 (4)",
      "missing                gone",
      "3 selector name(s) on https://shop.example/cart: 1 missing",
    ]);
  } finally {
    dispose();
  }
});

test("selectors exits 0 when every name is found, prints --json as data, and reads only", async () => {
  const chrome = selectorChrome({ buy: [1] });
  const { ctx, said, how, root, dispose } = setup(chrome);
  try {
    fs.writeFileSync(posix.join(root, "selectors.json"), JSON.stringify({ buy: [".buy"] }));
    assert.equal(await selectorsCommand(ctx, { file: "selectors.json", page: "docs", json: true }, how), 0);
    const printed = JSON.parse(said.join("\n"));
    assert.equal(printed.page.id, "T2");
    assert.equal(printed.findings[0].status, "matched");
    assert.deepEqual(
      chrome.calls.map((call) => call.method),
      ["Target.attachToTarget", "Runtime.evaluate", "Target.detachFromTarget"],
    );
  } finally {
    dispose();
  }
});

test("selectors refuses an unreadable or invalid registry in one line before it touches the browser", async () => {
  const chrome = selectorChrome({});
  const { ctx, how, root, dispose } = setup(chrome);
  try {
    await assert.rejects(
      selectorsCommand(ctx, { file: "absent.json", page: null, json: false }, how),
      (error) =>
        error instanceof BrowserError && /cannot read the selector registry .*absent\.json/.test(error.message),
    );
    fs.writeFileSync(posix.join(root, "bad.json"), '{"a": []}');
    await assert.rejects(
      selectorsCommand(ctx, { file: "bad.json", page: null, json: false }, how),
      (error) => error instanceof BrowserError && /bad\.json: "a" must be a non-empty list/.test(error.message),
    );
    assert.deepEqual(chrome.calls, []);
  } finally {
    dispose();
  }
});
