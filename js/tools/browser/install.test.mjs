import { test } from "node:test";
import assert from "node:assert/strict";

import { installFolder } from "./chrome.mjs";
import {
  BROWSERS_PIN,
  failureCause,
  INSTALL_TIMEOUT_MS,
  installCommand,
  installCommandOf,
  librariesCommand,
  planLines,
} from "./install.mjs";
import { BrowserError } from "./settings.mjs";
import { fakeHost } from "./support.test.mjs";

test("the downloader is pinned to one exact version", () => {
  assert.match(BROWSERS_PIN, /^@puppeteer\/browsers@\d+\.\d+\.\d+$/);
});

test("the plan says what, where, the size and the exact command, and runs nothing", () => {
  const folder = "/p/_aitna/.local/.browser/chrome";
  const text = planLines(folder).join("\n");
  assert.ok(text.includes("Chrome for Testing"));
  assert.ok(text.includes(folder));
  assert.ok(text.includes("200 MB"));
  assert.ok(text.includes(`npx --yes ${BROWSERS_PIN} install chrome@stable --path ${folder}`));
  assert.deepEqual(installCommandOf(folder), {
    command: "npx",
    args: ["--yes", BROWSERS_PIN, "install", "chrome@stable", "--path", folder],
  });
});

test("the library command is for the user, built from the build's own dependency list", () => {
  assert.match(librariesCommand("/p/chrome/linux-1/chrome-linux64/chrome"), /deb\.deps/);
});

const BROWSER_DIR = "/work/acme/_aitna/.local/.browser";

/**
 * A context over a fake machine, collecting what was said.
 * @param {string[]} extensions the configured extension folders
 * @param {Parameters<typeof fakeHost>[0]} machine
 * @param {{path: string, defect: string} | null} [extensionsProblem] the configured path that cannot be loaded
 */
function setup(extensions, machine, extensionsProblem = null) {
  /** @type {string[]} */
  const said = [];
  const ctx = /** @type {any} */ ({
    host: fakeHost(machine),
    env: {},
    settings: { chrome: null, extensions, extensionsProblem },
    project: { browserDir: BROWSER_DIR },
    say: (/** @type {string} */ line) => said.push(line),
  });
  return { ctx, said };
}

test("a branded Chrome on the machine means nothing to install, unless the project loads extensions", () => {
  const machine = { files: ["/usr/bin/chromium"], pathDirs: ["/usr/bin"] };
  const plain = setup([], machine);
  assert.equal(installCommand(plain.ctx, { yes: false }), 0);
  assert.match(plain.said[0], /Chrome is available \(system\): \/usr\/bin\/chromium; nothing to install/);
  const extensions = setup(["/work/acme/ext"], machine);
  assert.equal(installCommand(extensions.ctx, { yes: false }), 0);
  assert.match(extensions.said[0], /for extensions: Chrome for Testing is installed beside any other Chrome/);
  assert.ok(extensions.said.some((line) => line.includes(`--path ${installFolder(BROWSER_DIR)}`)));
  assert.ok(!extensions.said.some((line) => line.includes("nothing to install")));
});

test("--for-extensions plans Chrome for Testing without any extension configured, and a project build is nothing to install", () => {
  const machine = { files: ["/usr/bin/chromium"], pathDirs: ["/usr/bin"] };
  const forExtensions = setup([], machine);
  assert.equal(installCommand(forExtensions.ctx, { yes: false, forExtensions: true }), 0);
  assert.ok(forExtensions.said.some((line) => line.startsWith("plan only")));
  const built = `${installFolder(BROWSER_DIR)}/chrome/linux-140/chrome-linux64/chrome`;
  const have = setup(["/work/acme/ext"], {
    files: [built, "/usr/bin/chromium"],
    pathDirs: ["/usr/bin"],
    dirs: { [`${installFolder(BROWSER_DIR)}/chrome`]: [`${installFolder(BROWSER_DIR)}/chrome/linux-140`] },
  });
  assert.equal(installCommand(have.ctx, { yes: true }), 0);
  assert.match(have.said[0], /Chrome for Testing is available \(project\)/);
});

test("a bad extension path refuses install, except --for-extensions, which does not depend on the list", () => {
  const problem = { path: "ext/none", defect: "has no manifest.json" };
  const machine = { files: ["/usr/bin/chromium"], pathDirs: ["/usr/bin"] };
  const plain = setup([], machine, problem);
  assert.throws(
    () => installCommand(plain.ctx, { yes: false }),
    (error) => error instanceof BrowserError && /"ext\/none" has no manifest\.json/.test(error.message),
  );
  const forExtensions = setup([], machine, problem);
  assert.equal(installCommand(forExtensions.ctx, { yes: false, forExtensions: true }), 0);
  assert.ok(!forExtensions.said.some((line) => line.includes("list the unpacked extension folders")));
});

test("the download has a generous time limit, and a run that hit it says so", () => {
  assert.equal(INSTALL_TIMEOUT_MS, 15 * 60 * 1000);
  const timedOut = Object.assign(new Error("spawnSync npx ETIMEDOUT"), { code: "ETIMEDOUT" });
  assert.equal(failureCause({ status: null, error: timedOut }), "it did not finish within 15 minutes and was stopped");
  assert.equal(failureCause({ status: 1 }), "exit 1");
  assert.equal(failureCause({ status: null, error: new Error("spawn npx ENOENT") }), "spawn npx ENOENT");
});
