import { test } from "node:test";
import assert from "node:assert/strict";

import { findChrome, headlessReason, installFolder, profileFolder, windowsSide } from "./chrome.mjs";
import { BrowserError } from "./settings.mjs";
import { fakeHost } from "./support.test.mjs";

const BROWSER_DIR = "/work/acme/_aitna/.local/.browser";
const CFT = `${installFolder(BROWSER_DIR)}/chrome/linux-140/chrome-linux64/chrome`;
const where = (extra = {}) => ({ configured: null, browserDir: BROWSER_DIR, env: {}, ...extra });

test("a configured Chrome wins, and one that does not exist is refused", () => {
  const host = fakeHost({ files: ["/opt/mine/chrome", "/usr/bin/chromium"], pathDirs: ["/usr/bin"] });
  assert.deepEqual(findChrome(host, where({ configured: "/opt/mine/chrome" })), {
    path: "/opt/mine/chrome",
    source: "configured",
  });
  assert.throws(() => findChrome(host, where({ configured: "/nope" })), BrowserError);
});

test("then PATH names, then the system's paths, then the Windows side, then the project's own", () => {
  const onPath = fakeHost({ files: ["/usr/bin/chromium", "/opt/google/chrome/chrome", CFT], pathDirs: ["/usr/bin"] });
  assert.deepEqual(findChrome(onPath, where()), { path: "/usr/bin/chromium", source: "system" });
  const system = fakeHost({ files: ["/opt/google/chrome/chrome", CFT] });
  assert.deepEqual(findChrome(system, where()), { path: "/opt/google/chrome/chrome", source: "system" });
  const wsl = fakeHost({ files: [CFT], isWsl: true, windows: "/mnt/c/Chrome/chrome.exe" });
  assert.deepEqual(findChrome(wsl, where()), { path: "/mnt/c/Chrome/chrome.exe", source: "windows" });
  const own = fakeHost({
    files: [CFT],
    dirs: { [`${installFolder(BROWSER_DIR)}/chrome`]: [`${installFolder(BROWSER_DIR)}/chrome/linux-140`] },
  });
  assert.deepEqual(findChrome(own, where()), { path: CFT, source: "project" });
  assert.equal(findChrome(fakeHost(), where()), null);
});

test("under WSL the Windows folders PATH carries are not taken for a Linux Chrome", () => {
  const host = fakeHost({ files: ["/mnt/c/tools/chromium"], pathDirs: ["/mnt/c/tools"], isWsl: true });
  assert.equal(findChrome(host, where()), null);
});

test("the newest project build is preferred", () => {
  const base = `${installFolder(BROWSER_DIR)}/chrome`;
  const older = `${base}/linux-139/chrome-linux64/chrome`;
  const newer = `${base}/linux-140/chrome-linux64/chrome`;
  const host = fakeHost({ files: [older, newer], dirs: { [base]: [`${base}/linux-139`, `${base}/linux-140`] } });
  assert.equal(findChrome(host, where())?.path, newer);
});

test("a Chrome for Testing has a profile of its own, and a profile setting wins", () => {
  assert.equal(profileFolder(BROWSER_DIR, { path: "/x", source: "system" }, null), `${BROWSER_DIR}/chrome-profile`);
  assert.equal(
    profileFolder(BROWSER_DIR, { path: "/x", source: "project" }, null),
    `${BROWSER_DIR}/chrome-profile-cft`,
  );
  assert.equal(profileFolder(BROWSER_DIR, { path: "/x", source: "project" }, "/tmp/p"), "/tmp/p");
});

test("headless when requested, or on Linux with no display unless it is a Windows Chrome under WSL", () => {
  const server = fakeHost({ display: false });
  assert.equal(headlessReason(server, "/usr/bin/chromium", false), "no graphical session");
  assert.equal(headlessReason(fakeHost({ display: true }), "/usr/bin/chromium", false), null);
  assert.equal(headlessReason(fakeHost({ display: true }), "/usr/bin/chromium", true), "requested with --headless");
  const wsl = fakeHost({ display: false, isWsl: true });
  assert.equal(headlessReason(wsl, "/mnt/c/Chrome/chrome.exe", false), null);
  assert.equal(windowsSide(wsl, "/mnt/c/Chrome/chrome.exe"), true);
  assert.equal(windowsSide(wsl, "/usr/bin/chromium"), false);
});

test("a project that loads extensions takes only a configured Chrome or its own Chrome for Testing, never one found on the machine", () => {
  const base = `${installFolder(BROWSER_DIR)}/chrome`;
  const host = fakeHost({
    files: ["/usr/bin/chromium", "/opt/google/chrome/chrome", CFT],
    pathDirs: ["/usr/bin"],
    dirs: { [base]: [`${base}/linux-140`] },
    isWsl: true,
    windows: "/mnt/c/Chrome/chrome.exe",
  });
  assert.deepEqual(findChrome(host, where({ testing: true })), { path: CFT, source: "project" });
  const branded = fakeHost({ files: ["/usr/bin/chromium", "/opt/google/chrome/chrome"], pathDirs: ["/usr/bin"] });
  assert.equal(findChrome(branded, where({ testing: true })), null);
  assert.deepEqual(findChrome(branded, where()), { path: "/usr/bin/chromium", source: "system" });
  assert.equal(
    findChrome(fakeHost({ isWsl: true, windows: "/mnt/c/Chrome/chrome.exe" }), where({ testing: true })),
    null,
  );
  assert.deepEqual(findChrome(branded, where({ testing: true, configured: "/usr/bin/chromium" })), {
    path: "/usr/bin/chromium",
    source: "configured",
  });
});

test("a project's Chrome for Testing is used with its own -cft profile", () => {
  const found = { path: CFT, source: /** @type {const} */ ("project") };
  assert.equal(profileFolder(BROWSER_DIR, found, null), `${BROWSER_DIR}/chrome-profile-cft`);
});
