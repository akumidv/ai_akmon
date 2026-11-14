import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { posix } from "node:path";

import {
  attachCommand,
  attachedStatusCommand,
  attachedStatusLines,
  collectAttachedStatus,
  detachCommand,
  parseEndpointFile,
  readAttach,
  refuseInAttachMode,
  resolveEndpoint,
  writeAttach,
} from "./attach.mjs";
import { restartCommand, startCommand, stopCommand } from "./lifecycle.mjs";
import { redactFloor } from "./redact.mjs";
import { BrowserError } from "./settings.mjs";
import { fakeHost, tempProject } from "./support.test.mjs";

const ENDPOINT_JSON = JSON.stringify({
  browserURL: "http://127.0.0.1:9333",
  by: "playwright",
  pid: 4242,
  release: "test-results/akmon-browser-endpoint.json",
});

/**
 * A context over a throwaway project that collects what is said.
 * @param {string} root
 * @returns {{ctx: any, said: string[], browserDir: string}}
 */
function contextOf(root) {
  /** @type {string[]} */
  const said = [];
  const browserDir = posix.join(root, "_aitna", ".local", ".browser");
  const project = { root, name: posix.basename(root), devRoot: posix.join(root, "_aitna"), browserDir };
  return {
    ctx: {
      project,
      port: 9312,
      host: fakeHost(),
      settings: { extensions: [], extensionsProblem: null, redact: redactFloor([]) },
      say: (/** @type {string} */ line) => said.push(line),
    },
    said,
    browserDir,
  };
}

/**
 * A DevTools probe that answers like a Chrome, or not at all.
 * @param {boolean} answering
 * @returns {(port: number, path?: string) => Promise<any>}
 */
function probeOf(answering) {
  return async (_port, path = "/json/version") => {
    if (!answering) {
      return null;
    }
    return path === "/json/list"
      ? [
          { type: "page", title: "Checkout", url: "https://shop.example/cart" },
          { type: "service_worker", title: "sw", url: "https://shop.example/sw.js" },
        ]
      : { Browser: "Chrome/140" };
  };
}

/** @param {string} root @param {string} name @param {string} text */
function writeIn(root, name, text) {
  const path = posix.join(root, name);
  fs.mkdirSync(posix.dirname(path), { recursive: true });
  fs.writeFileSync(path, text);
  return path;
}

/** @param {() => unknown} action @param {RegExp} message */
function refused(action, message) {
  assert.throws(action, (error) => error instanceof BrowserError && message.test(error.message));
}

test("an endpoint is a bare port, a loopback http or ws URL, or an endpoint file", () => {
  const how = {
    root: "/p",
    readText: (/** @type {string} */ path) => (path === "/p/run/e.json" ? ENDPOINT_JSON : null),
  };
  const url = "http://127.0.0.1:9333";
  assert.deepEqual(resolveEndpoint("9333", how), {
    endpoint: "9333",
    browserURL: url,
    port: 9333,
    by: "user",
    file: null,
  });
  assert.equal(resolveEndpoint("http://127.0.0.1:9333", how).browserURL, url);
  assert.equal(resolveEndpoint("http://127.0.0.1:9333/", how).browserURL, url);
  assert.equal(resolveEndpoint("http://localhost:9333", how).browserURL, url, "localhost is normalized");
  const ws = resolveEndpoint("ws://127.0.0.1:9333/devtools/browser/3f2c", how);
  assert.deepEqual([ws.browserURL, ws.port, ws.by], [url, 9333, "user"]);
  assert.deepEqual(resolveEndpoint("run/e.json", how), {
    endpoint: "run/e.json",
    browserURL: url,
    port: 9333,
    by: "playwright",
    file: "/p/run/e.json",
  });
  assert.equal(resolveEndpoint("/p/run/e.json", how).file, "/p/run/e.json");
});

test("a host that is not loopback, a scheme that is not DevTools and a bad port are refused", () => {
  const how = { root: "/p", readText: () => null };
  for (const spec of ["http://example.com:9333", "ws://10.0.0.5:9222/devtools/browser/x", "http://[::1]:9333"]) {
    refused(() => resolveEndpoint(spec, how), /is not on loopback; only 127\.0\.0\.1 or localhost/);
  }
  refused(() => resolveEndpoint("https://127.0.0.1:9333", how), /not an http:\/\/ or ws:\/\/ DevTools URL/);
  refused(() => resolveEndpoint("http://127.0.0.1", how), /names no DevTools port/);
  refused(() => resolveEndpoint("0", how), /not a number from 1 to 65535/);
  refused(() => resolveEndpoint("70000", how), /not a number from 1 to 65535/);
  refused(() => resolveEndpoint("run/missing.json", how), /not a loopback URL, a port or an endpoint file that exists/);
});

test("an endpoint file is validated where it enters: JSON, object, a loopback browserURL, typed fields", () => {
  assert.deepEqual(parseEndpointFile(ENDPOINT_JSON, "f"), {
    browserURL: "http://127.0.0.1:9333",
    by: "playwright",
    pid: 4242,
    release: "test-results/akmon-browser-endpoint.json",
  });
  assert.deepEqual(parseEndpointFile('{"browserURL":"http://localhost:9333"}', "f"), {
    browserURL: "http://localhost:9333",
    by: "unknown",
  });
  refused(() => parseEndpointFile("{not json", "f.json"), /endpoint file f\.json is not valid JSON/);
  refused(() => parseEndpointFile("[]", "f"), /is not a JSON object/);
  refused(() => parseEndpointFile("{}", "f"), /no "browserURL" string/);
  refused(() => parseEndpointFile('{"browserURL":"http://example.com:9333"}', "f"), /not on loopback/);
  refused(
    () => parseEndpointFile('{"browserURL":"http://127.0.0.1:9333","by":3}', "f"),
    /"by" is not a non-empty string/,
  );
  refused(
    () => parseEndpointFile('{"browserURL":"http://127.0.0.1:9333","pid":"1"}', "f"),
    /"pid" is not a positive integer/,
  );
  refused(
    () => parseEndpointFile('{"browserURL":"http://127.0.0.1:9333","release":1}', "f"),
    /"release" is not a string/,
  );
});

test("attach records the endpoint, detach clears it, and neither touches a browser", async () => {
  const { root, dispose } = tempProject();
  try {
    const { ctx, said, browserDir } = contextOf(root);
    const file = writeIn(root, "test-results/akmon-browser-endpoint.json", ENDPOINT_JSON);
    assert.equal(readAttach(browserDir), null);
    const code = await attachCommand(
      ctx,
      { endpoint: "test-results/akmon-browser-endpoint.json" },
      { probe: probeOf(true) },
    );
    assert.equal(code, 0);
    const attachment = readAttach(browserDir);
    assert.deepEqual(
      { ...attachment, attached: typeof attachment?.attached },
      {
        endpoint: "test-results/akmon-browser-endpoint.json",
        browserURL: "http://127.0.0.1:9333",
        by: "playwright",
        file,
        browser: "Chrome/140",
        attached: "string",
      },
    );
    assert.match(
      said[0],
      /^Attached to Chrome Chrome\/140 at http:\/\/127\.0\.0\.1:9333 \(written by playwright, endpoint file /,
    );
    assert.ok(said.some((line) => line.includes("never close the window or a page") && line.includes("never sign in")));

    said.length = 0;
    assert.equal(detachCommand(ctx, { release: false }), 0);
    assert.equal(readAttach(browserDir), null);
    assert.ok(!fs.existsSync(posix.join(browserDir, "attach.json")));
    assert.ok(fs.existsSync(file), "a plain detach leaves the endpoint file");
    assert.match(said[0], /detached from http:\/\/127\.0\.0\.1:9333; the browser was left running and untouched/);
    assert.equal(detachCommand(ctx, { release: false }), 0, "detaching twice is harmless");
    assert.match(said.at(-1) ?? "", /not attached/);
  } finally {
    dispose();
  }
});

test("a URL or a port attaches with no endpoint file, and an endpoint that does not answer is refused", async () => {
  const { root, dispose } = tempProject();
  try {
    const { ctx, browserDir } = contextOf(root);
    await attachCommand(ctx, { endpoint: "http://localhost:9333" }, { probe: probeOf(true) });
    const attachment = readAttach(browserDir);
    assert.equal(attachment?.by, "user");
    assert.equal(attachment?.file, undefined);
    assert.ok(!Object.hasOwn(attachment ?? {}, "file"));
    await assert.rejects(
      attachCommand(ctx, { endpoint: "9444" }, { probe: probeOf(false) }),
      /nothing answers on http:\/\/127\.0\.0\.1:9444/,
    );
    assert.equal(readAttach(browserDir)?.browserURL, "http://127.0.0.1:9333", "a failed attach keeps the earlier one");
  } finally {
    dispose();
  }
});

test("detach --release deletes only the endpoint file the attach came from", async () => {
  const { root, dispose } = tempProject();
  try {
    const { ctx, said, browserDir } = contextOf(root);
    const file = writeIn(root, "test-results/akmon-browser-endpoint.json", ENDPOINT_JSON);
    const neighbour = writeIn(root, "test-results/other-endpoint.json", ENDPOINT_JSON);
    const trace = writeIn(root, "test-results/trace.zip", "zip");
    await attachCommand(ctx, { endpoint: file }, { probe: probeOf(true) });
    assert.equal(detachCommand(ctx, { release: true }), 0);
    assert.ok(!fs.existsSync(file), "the attached endpoint file is gone: the hold step may end");
    assert.ok(fs.existsSync(neighbour) && fs.existsSync(trace), "nothing else is deleted");
    assert.equal(readAttach(browserDir), null);
    assert.match(said.at(-1) ?? "", /released: deleted the endpoint file .*akmon-browser-endpoint\.json/);

    writeIn(root, "test-results/akmon-browser-endpoint.json", ENDPOINT_JSON);
    await attachCommand(ctx, { endpoint: file }, { probe: probeOf(true) });
    fs.rmSync(file);
    assert.equal(detachCommand(ctx, { release: true }), 0, "an endpoint file already gone is not an error");
    assert.match(said.at(-1) ?? "", /was already gone/);
  } finally {
    dispose();
  }
});

test("detach --release refuses an attach that came from no file, and a file that is no endpoint file", async () => {
  const { root, dispose } = tempProject();
  try {
    const { ctx, browserDir } = contextOf(root);
    await attachCommand(ctx, { endpoint: "9333" }, { probe: probeOf(true) });
    refused(() => detachCommand(ctx, { release: true }), /came from no endpoint file, so there is nothing to release/);
    assert.notEqual(readAttach(browserDir), null, "a refused release changes nothing");

    const precious = writeIn(root, "precious.txt", "keep me");
    const attachment = /** @type {import("./attach.mjs").Attachment} */ (readAttach(browserDir));
    writeAttach({ ...attachment, file: precious }, browserDir);
    refused(() => detachCommand(ctx, { release: true }), /is not valid JSON/);
    assert.equal(fs.readFileSync(precious, "utf8"), "keep me");
    assert.notEqual(readAttach(browserDir), null);
  } finally {
    dispose();
  }
});

test("an attach record that is not valid is reported, and a plain detach clears it", () => {
  const { root, dispose } = tempProject();
  try {
    const { ctx, said, browserDir } = contextOf(root);
    writeIn(root, "_aitna/.local/.browser/attach.json", '{"endpoint":"9333"}');
    refused(
      () => readAttach(browserDir),
      /is not a valid attach record \("browserURL" is missing or not a string\); run: akmon tool browser detach/,
    );
    refused(() => detachCommand(ctx, { release: true }), /not a valid attach record/);
    assert.equal(detachCommand(ctx, { release: false }), 0);
    assert.match(said[0], /cleared an attach record that was not valid/);
    assert.equal(readAttach(browserDir), null);
  } finally {
    dispose();
  }
});

test("start, stop and restart refuse in attach mode, in one line, before anything is touched", async () => {
  const { root, dispose } = tempProject();
  try {
    const { ctx, browserDir } = contextOf(root);
    refuseInAttachMode(browserDir, "stop");
    await attachCommand(ctx, { endpoint: "9333" }, { probe: probeOf(true) });
    const options = { url: null, headless: false };
    await assert.rejects(startCommand(ctx, options), (error) => {
      assert.ok(error instanceof BrowserError);
      assert.match(
        error.message,
        /^start is refused in attach mode \(attached to http:\/\/127\.0\.0\.1:9333, written by user\): the project's own Chrome is started outside attach mode; run: akmon tool browser detach$/,
      );
      assert.ok(!error.message.includes("\n"));
      return true;
    });
    for (const command of [stopCommand(ctx), restartCommand(ctx, options)]) {
      await assert.rejects(
        command,
        /^BrowserError: (stop|restart) is refused in attach mode .*akmon never closes a browser it did not start/,
      );
    }
    assert.deepEqual(fs.readdirSync(browserDir), ["attach.json"], "no launch record, no profile");
  } finally {
    dispose();
  }
});

test("status in attach mode: a fresh attach lists the tabs and the rules, a stale one says detach", async () => {
  const { root, dispose } = tempProject();
  try {
    const { ctx, said } = contextOf(root);
    const file = writeIn(root, "run/e.json", ENDPOINT_JSON);
    await attachCommand(ctx, { endpoint: file }, { probe: probeOf(true) });
    const attachment = /** @type {import("./attach.mjs").Attachment} */ (readAttach(ctx.project.browserDir));

    const fresh = await collectAttachedStatus(attachment, ctx, probeOf(true));
    assert.deepEqual(
      [fresh.mode, fresh.running, fresh.browser, fresh.by, fresh.file, fresh.tabs],
      ["attached", true, "Chrome/140", "playwright", file, [{ title: "Checkout", url: "https://shop.example/cart" }]],
    );
    const lines = attachedStatusLines(fresh);
    assert.match(
      lines[0],
      /^mode: attached to Chrome Chrome\/140 at http:\/\/127\.0\.0\.1:9333 \(written by playwright, endpoint file .*\), 1 tab\(s\)$/,
    );
    assert.ok(lines.some((line) => line.includes("Checkout") && line.includes("https://shop.example/cart")));
    assert.ok(lines.some((line) => line.includes("never close the window or a page")));

    said.length = 0;
    assert.equal(await attachedStatusCommand(ctx, attachment, { json: false }, probeOf(true)), 0);
    assert.equal(await attachedStatusCommand(ctx, attachment, { json: true }, probeOf(true)), 0);
    assert.equal(JSON.parse(said.at(-1) ?? "").browserURL, "http://127.0.0.1:9333");

    const stale = await collectAttachedStatus(attachment, ctx, probeOf(false));
    assert.deepEqual([stale.running, stale.browser, stale.tabs], [false, null, []]);
    const staleLines = attachedStatusLines(stale);
    assert.match(
      staleLines[0],
      /^mode: attached to http:\/\/127\.0\.0\.1:9333 .* no longer answers: .*run: akmon tool browser detach$/,
    );
    assert.equal(await attachedStatusCommand(ctx, attachment, { json: false }, probeOf(false)), 1);

    const broken = {
      ...ctx,
      settings: {
        extensions: [],
        redact: redactFloor([]),
        extensionsProblem: { path: "ext/none", defect: "has no manifest.json" },
      },
    };
    said.length = 0;
    assert.equal(await attachedStatusCommand(broken, attachment, { json: false }, probeOf(true)), 1);
    assert.ok(said.includes("  extensions: ext/none has no manifest.json"));
    assert.equal(await attachedStatusCommand(broken, attachment, { json: true }, probeOf(true)), 1);
    assert.equal(JSON.parse(said.at(-1) ?? "").extensionsProblem, "ext/none has no manifest.json");
  } finally {
    dispose();
  }
});

test("status in attach mode prints a tab's URL with its secret parameters redacted", async () => {
  const { root, dispose } = tempProject();
  try {
    const { ctx } = contextOf(root);
    const attachment = { browserURL: "http://127.0.0.1:9333", endpoint: "http://127.0.0.1:9333", by: "user" };
    const probe = async (/** @type {number} */ _port, path = "/json/version") =>
      path === "/json/list"
        ? [{ type: "page", title: "Callback", url: "https://app.example/cb#access_token=SECRET" }]
        : { Browser: "Chrome/140" };
    const report = await collectAttachedStatus(/** @type {any} */ (attachment), ctx, probe);
    const text = attachedStatusLines(report).join("\n") + JSON.stringify(report);
    assert.ok(!text.includes("SECRET"));
    assert.ok(text.includes("access_token=[redacted]"));
  } finally {
    dispose();
  }
});
