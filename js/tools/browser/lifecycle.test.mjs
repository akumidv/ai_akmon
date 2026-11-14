import assert from "node:assert/strict";
import fs from "node:fs";
import { test } from "node:test";

import { buildContext } from "./context.mjs";
import {
  chromeArguments,
  extensionArguments,
  launchRecord,
  noChromeLine,
  proxyReport,
  readLaunch,
  requireStartUrl,
  restartCommand,
  startCommand,
  statusLines,
} from "./lifecycle.mjs";
import { proxyPlan } from "./proxy.mjs";
import { BrowserError } from "./settings.mjs";
import { fakeHost, tempProject } from "./support.test.mjs";

const MCP = { state: /** @type {const} */ ("not wired"), why: "no .mcp.json in the project" };
const report = (extra = {}) => ({
  mode: /** @type {const} */ ("own"),
  project: "acme",
  port: 9312,
  browserURL: "http://127.0.0.1:9312",
  running: true,
  owner: /** @type {const} */ ("ours"),
  refusal: null,
  browser: "Chrome/140",
  tabs: [{ title: "Inbox", url: "https://mail.example/" }],
  proxy: { used: "http://p:3128", now: "http://p:3128", restart: false },
  mcp: MCP,
  node: "v24.0.0",
  extensionsProblem: null,
  ...extra,
});

test("Chrome starts on loopback DevTools with the project's profile, the proxy and the url", () => {
  const ctx = /** @type {any} */ ({ port: 9312 });
  const args = chromeArguments(ctx, {
    profile: "/p/chrome-profile",
    proxy: { args: ["--proxy-server=http://p:3128"], describe: "x" },
    headless: true,
    url: "https://example.org",
  });
  assert.deepEqual(args, [
    "--remote-debugging-port=9312",
    "--remote-debugging-address=127.0.0.1",
    "--user-data-dir=/p/chrome-profile",
    "--no-first-run",
    "--no-default-browser-check",
    "--proxy-server=http://p:3128",
    "--headless=new",
    "https://example.org/",
  ]);
  const plain = chromeArguments(ctx, { profile: "/p", proxy: { args: [], describe: "x" }, headless: false, url: null });
  assert.ok(!plain.includes("--headless=new") && plain.length === 5);
});

test("a start records the project root beside the launch, so another project can name it", () => {
  const ctx = /** @type {any} */ ({ port: 9312, project: { root: "/work/mono/apps/acme", name: "acme" } });
  const record = launchRecord(ctx, {
    exe: "/opt/chrome",
    profile: "/p",
    proxy: "direct",
    headless: false,
    args: ["--x"],
  });
  assert.equal(record.project, "/work/mono/apps/acme");
  assert.equal(record.port, 9312);
  assert.deepEqual(
    [record.exe, record.profile, record.proxy, record.headless, record.args],
    ["/opt/chrome", "/p", "direct", false, ["--x"]],
  );
  assert.match(record.started, /^\d{4}-\d\d-\d\dT/);
});

test("status of this project's Chrome: tabs, proxy, mcp state and node", () => {
  const lines = statusLines(report());
  assert.match(lines[0], /^Chrome Chrome\/140 of project acme on 127\.0\.0\.1:9312, 1 tab\(s\)$/);
  assert.ok(lines.some((line) => line.startsWith("  proxy: http://p:3128")));
  assert.ok(lines.some((line) => line.includes("Inbox") && line.includes("https://mail.example/")));
  assert.ok(lines.some((line) => line.startsWith("  mcp: not wired")));
  assert.ok(lines.some((line) => line.includes("akmon tool browser init")));
  assert.ok(lines.some((line) => line === "  node: v24.0.0"));
});

test("status says restart when the environment's proxy changed since the start", () => {
  const lines = statusLines(
    report({ proxy: { used: "http://p:3128", now: "system proxy (none in the environment)", restart: true } }),
  );
  assert.ok(lines.some((line) => line.includes("NOTE") && line.includes("restart")));
});

test("status of a Chrome akmon did not start has no proxy to report and says restart", () => {
  const lines = statusLines(report({ proxy: { used: null, now: "x", restart: false } }));
  assert.ok(lines.some((line) => line.includes("proxy: unknown") && line.includes("restart")));
});

test("status of nothing running, and of another project's Chrome", () => {
  assert.match(
    statusLines(report({ running: false, owner: null, browser: null, tabs: [] }))[0],
    /^no Chrome DevTools on 127\.0\.0\.1:9312 .*akmon tool browser start$/,
  );
  const foreign = statusLines(
    report({ owner: "other-project", refusal: "the Chrome on 127.0.0.1:9312 is the Chrome of project globex" }),
  );
  assert.match(
    foreign[0],
    /^not this project's browser: the Chrome on 127\.0\.0\.1:9312 is the Chrome of project globex/,
  );
});

test("a wired MCP route adds no hint to run init", () => {
  const lines = statusLines(report({ mcp: { state: "wired", why: "the launcher x is there" } }));
  assert.ok(!lines.some((line) => line.includes("akmon tool browser init")));
});

test("extensions load with --load-extension and keep every other extension out with --disable-extensions-except", () => {
  assert.deepEqual(extensionArguments([]), []);
  assert.deepEqual(extensionArguments(["/p/ext", "/p/other"]), [
    "--load-extension=/p/ext,/p/other",
    "--disable-extensions-except=/p/ext,/p/other",
  ]);
  const ctx = /** @type {any} */ ({ port: 9312 });
  const args = chromeArguments(ctx, {
    profile: "/p/prof",
    proxy: { args: [], describe: "x" },
    headless: false,
    url: "https://example.org",
    extensions: ["C:\\Users\\me\\ext", "D:\\other"],
  });
  assert.deepEqual(args.slice(5), [
    "--load-extension=C:\\Users\\me\\ext,D:\\other",
    "--disable-extensions-except=C:\\Users\\me\\ext,D:\\other",
    "https://example.org/",
  ]);
});

test("the launch record keeps the extensions the Chrome was started with", () => {
  const ctx = /** @type {any} */ ({ port: 9312, project: { root: "/work/acme", name: "acme" } });
  const record = launchRecord(ctx, {
    exe: "/opt/cft/chrome",
    profile: "/p",
    proxy: "direct",
    headless: false,
    extensions: ["/work/acme/ext"],
    args: ["--load-extension=/work/acme/ext"],
  });
  assert.deepEqual(record.extensions, ["/work/acme/ext"]);
});

/**
 * A context with the extensions configured or not, over a fake machine.
 * @param {string[]} extensions
 * @param {Parameters<typeof fakeHost>[0]} machine
 */
function extensionCtx(extensions, machine) {
  return /** @type {any} */ ({
    host: fakeHost(machine),
    env: {},
    settings: { chrome: null, extensions },
    project: { browserDir: "/work/acme/_aitna/.local/.browser" },
  });
}

test("start with extensions configured and only a branded Chrome refuses in one line naming install", () => {
  const branded = extensionCtx(["/work/acme/ext"], { files: ["/usr/bin/chromium"], pathDirs: ["/usr/bin"] });
  const line = noChromeLine(branded);
  assert.match(line, /needs Chrome for Testing, and only \/usr\/bin\/chromium was found/);
  assert.match(line, /akmon tool browser install$/);
  assert.ok(!line.includes("\n"));
  assert.match(
    noChromeLine(extensionCtx(["/work/acme/ext"], {})),
    /no Chrome was found; install it .*akmon tool browser install/,
  );
  assert.match(noChromeLine(extensionCtx([], {})), /^Chrome not found; install it with the system/);
});

test("status names a configured extension path that cannot be loaded, and says nothing when all load", () => {
  assert.ok(!statusLines(report()).some((line) => line.includes("extensions:")));
  const lines = statusLines(report({ extensionsProblem: "ext/none has no manifest.json" }));
  assert.ok(lines.includes("  extensions: ext/none has no manifest.json"));
});

test("a bad extension path does not stop the context; start and restart refuse it in one line", async () => {
  const { root, dispose } = tempProject('[browser]\nextensions = ["ext/none"]\n');
  try {
    /** @type {string[]} */
    const said = [];
    const ctx = buildContext(root, { env: {}, host: fakeHost(), say: (line) => said.push(line) });
    assert.equal(ctx.settings.extensionsProblem?.path, "ext/none");
    for (const verb of [startCommand, restartCommand]) {
      await assert.rejects(
        verb(ctx, { url: null, headless: false }),
        (error) =>
          error instanceof BrowserError &&
          /"ext\/none" has no manifest\.json/.test(error.message) &&
          !error.message.includes("\n"),
      );
    }
    assert.deepEqual(said, []);
  } finally {
    dispose();
  }
});

test("--url takes only a page address, so it can never be read as a Chrome switch", async () => {
  for (const url of [
    "https://a.example/x",
    "http://localhost:3000",
    "file:///tmp/a.html",
    "about:blank",
    "data:text/html,hi",
  ]) {
    requireStartUrl(url);
  }
  requireStartUrl(null);
  for (const url of [
    "--remote-debugging-address=0.0.0.0",
    "-remote-debugging-port=1",
    " --no-sandbox",
    "javascript:alert(1)",
    "chrome://settings",
    "ftp://h/x",
    "",
  ]) {
    assert.throws(
      () => requireStartUrl(url),
      (error) =>
        error instanceof BrowserError && /^--url must be an http:/.test(error.message) && !error.message.includes("\n"),
      url,
    );
  }
  const { root, dispose } = tempProject();
  try {
    /** @type {string[]} */
    const said = [];
    const ctx = buildContext(root, { env: {}, host: fakeHost(), say: (line) => said.push(line) });
    for (const verb of [startCommand, restartCommand]) {
      await assert.rejects(
        verb(ctx, { url: "--remote-debugging-address=0.0.0.0", headless: false }),
        /--url must be an http:/,
      );
    }
    assert.deepEqual(said, [], "nothing was stopped or started");
  } finally {
    dispose();
  }
});

test("--url reaches Chrome as its normalized href, so a quote or a space cannot split into switches", () => {
  const ctx = /** @type {any} */ ({ port: 9312 });
  const plan = { profile: "/p", proxy: { args: [], describe: "x" }, headless: false };
  for (const [url, argument] of [
    [
      'https://a.example/x" --remote-debugging-address=0.0.0.0',
      "https://a.example/x%22%20--remote-debugging-address=0.0.0.0",
    ],
    ["http://h/a b?q=1 --no-sandbox#f g", "http://h/a%20b?q=1%20--no-sandbox#f%20g"],
    ['data:text/html,a "b" --x', "data:text/html,a%20%22b%22%20--x"],
    ["about:blank", "about:blank"],
  ]) {
    requireStartUrl(url);
    const args = chromeArguments(ctx, { ...plan, url });
    assert.equal(args.at(-1), argument);
    assert.ok(!/["\s]/.test(String(args.at(-1))), url);
    assert.equal(args.filter((arg) => arg.startsWith("--") && arg.includes("remote-debugging-address")).length, 1);
  }
  assert.throws(() => requireStartUrl("https:"), BrowserError);
});

test("a proxy's credentials are in Chrome's arguments only: the record and the words never hold them", () => {
  const plan = proxyPlan({ HTTPS_PROXY: "http://ann:s3cret@proxy:3128" }, null);
  assert.deepEqual(plan.args, ["--proxy-server=http://ann:s3cret@proxy:3128"]);
  assert.equal(plan.describe, "http://***@proxy:3128");
  const ctx = /** @type {any} */ ({ port: 9312, project: { root: "/work/acme", name: "acme" } });
  const record = launchRecord(ctx, {
    exe: "/c",
    profile: "/p",
    proxy: plan.describe,
    headless: false,
    args: plan.args,
  });
  assert.ok(!JSON.stringify(record).includes("s3cret"));
  assert.ok(!JSON.stringify(record).includes("ann:"));
  assert.deepEqual(record.args, ["--proxy-server=http://***@proxy:3128"]);
  assert.equal(record.proxyCredentials, true);
});

test("a record an older start wrote is read without its credentials", () => {
  const { root, dispose } = tempProject();
  try {
    const ctx = buildContext(root, { env: {}, host: fakeHost(), say: () => {} });
    fs.mkdirSync(ctx.project.browserDir, { recursive: true });
    fs.writeFileSync(
      `${ctx.project.browserDir}/launch.json`,
      JSON.stringify({ proxy: "http://ann:s3cret@proxy:3128 (bypass: 1 rule(s) from NO_PROXY)" }),
    );
    assert.equal(readLaunch(ctx)?.proxy, "http://***@proxy:3128 (bypass: 1 rule(s) from NO_PROXY)");
  } finally {
    dispose();
  }
});

test("a changed proxy asks for a restart, also when only its credentials appeared or went", () => {
  const ours = /** @type {any} */ ({ owner: { owner: "ours" } });
  const withCreds = proxyPlan({ HTTPS_PROXY: "http://ann:pw@proxy:3128" }, null);
  const without = proxyPlan({ HTTPS_PROXY: "http://proxy:3128" }, null);
  const record = (/** @type {import("./proxy.mjs").ProxyPlan} */ plan, /** @type {boolean} */ credentials) =>
    /** @type {any} */ ({ proxy: plan.describe, proxyCredentials: credentials });
  assert.equal(proxyReport(ours, record(withCreds, true), withCreds).restart, false);
  assert.equal(proxyReport(ours, record(without, false), without).restart, false);
  assert.equal(proxyReport(ours, record(without, false), withCreds).restart, true);
  assert.equal(
    proxyReport(ours, record(withCreds, true), proxyPlan({ HTTPS_PROXY: "http://q:1" }, null)).restart,
    true,
  );
  assert.equal(proxyReport(null, null, withCreds).restart, false);
  assert.equal(proxyReport(ours, record(withCreds, true), withCreds).now, "http://***@proxy:3128");
});
