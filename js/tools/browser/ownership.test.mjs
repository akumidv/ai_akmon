import { test } from "node:test";
import assert from "node:assert/strict";

import {
  checkPort,
  chromeOwnership,
  notOursMessage,
  profileProject,
  projectNamed,
  samePath,
  userDataDir,
} from "./ownership.mjs";

const ROOT = "/home/user/work/acme";
const OURS = `${ROOT}/_aitna/.local/.browser/chrome-profile`;
/** @param {string} profile @param {number} [port] */
const line = (profile, port = 9312) =>
  `/opt/google/chrome/chrome --remote-debugging-port=${port} --user-data-dir=${profile} --no-first-run`;

test("the user data dir is read from a command line, quoted or not", () => {
  assert.equal(userDataDir(line("/tmp/p")), "/tmp/p");
  assert.equal(userDataDir('chrome.exe --user-data-dir="C:\\Users\\me\\My Profile" --x'), "C:\\Users\\me\\My Profile");
  assert.equal(userDataDir("chrome --no-first-run"), null);
});

test("a profile path names its project, on every side", () => {
  assert.equal(profileProject(OURS), "acme");
  assert.equal(profileProject(`${ROOT}/meta/.local/.browser/chrome-profile-cft`), "acme");
  assert.equal(
    profileProject("\\\\wsl.localhost\\Ubuntu\\home\\user\\globex\\_aitna\\.local\\.browser\\chrome-profile"),
    "globex",
  );
  assert.equal(profileProject("C:\\Users\\user\\AppData\\Local\\Google\\Chrome\\User Data"), null);
  assert.equal(profileProject(null), null);
});

/** A reader of the records other projects left: `files` maps a path to its text. @param {Record<string, string>} files */
const reader = (files) => (/** @type {string} */ path) => files[path] ?? null;

test("a foreign Chrome is named from its project's launch record, so a nested dev root names the project right", () => {
  const nested = "/work/mono/apps/globex/tools/_aitna/.local/.browser/chrome-profile";
  const record = '{"project": "/work/mono/apps/globex", "port": 9400}';
  const read = reader({ "/work/mono/apps/globex/tools/_aitna/.local/.browser/launch.json": record });
  assert.equal(profileProject(nested), "tools", "the folder heuristic alone names the wrong folder");
  assert.equal(projectNamed(nested, read), "globex");
  assert.equal(projectNamed(`${nested}-cft/`, read), "globex", "a Chrome for Testing profile has the same record");
  assert.deepEqual(chromeOwnership([line(nested)], [OURS], read), {
    owner: "foreign",
    project: "globex",
    profile: nested,
  });
});

test("the record is read through a Windows Chrome's WSL path too", () => {
  const unc = "\\\\wsl.localhost\\Ubuntu\\home\\user\\mono\\globex\\tools\\_aitna\\.local\\.browser\\chrome-profile";
  const read = reader({
    "/home/user/mono/globex/tools/_aitna/.local/.browser/launch.json": '{"project": "/home/user/mono/globex"}',
  });
  assert.equal(projectNamed(unc, read), "globex");
});

test("with no readable record, a record with no project, or a bad one, the folder heuristic names the project", () => {
  const other = "/home/user/work/globex/_aitna/.local/.browser/chrome-profile";
  const path = "/home/user/work/globex/_aitna/.local/.browser/launch.json";
  assert.equal(
    projectNamed(other, () => null),
    "globex",
  );
  assert.equal(projectNamed(other, reader({ [path]: '{"port": 9400}' })), "globex");
  assert.equal(projectNamed(other, reader({ [path]: "not json" })), "globex");
  assert.equal(projectNamed(other, reader({ [path]: '{"project": 7}' })), "globex");
  assert.equal(
    projectNamed("/home/user/.config/chrome-debug", () => assert.fail("not an akmon profile")),
    null,
  );
  assert.equal(
    projectNamed(null, () => assert.fail("no profile")),
    null,
  );
  assert.deepEqual(chromeOwnership([line(other)], [OURS]), { owner: "foreign", project: "globex", profile: other });
});

test("paths are the same folder up to separators, trailing slash and a Windows path's case", () => {
  assert.ok(samePath("/a/b/", "/a/b"));
  assert.ok(samePath("C:\\Users\\Me\\p\\", "c:/users/me/p"));
  assert.ok(!samePath("/a/b", "/a/B"));
});

test("whose a Chrome is: this project's, another one's by name, or one akmon did not start", () => {
  const profiles = [OURS, `${ROOT}/_aitna/.local/.browser/chrome-profile-cft`];
  assert.deepEqual(chromeOwnership([line(OURS)], profiles), { owner: "ours" });
  assert.deepEqual(chromeOwnership([line(`${OURS}-cft/`)], profiles), { owner: "ours" });
  assert.deepEqual(
    chromeOwnership([line("/tmp/custom")], [...profiles, "/tmp/custom"]),
    { owner: "ours" },
    "the profile setting",
  );

  const windows = "\\\\wsl.localhost\\Ubuntu\\home\\user\\work\\acme\\_aitna\\.local\\.browser\\chrome-profile";
  const quoted = `"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" --remote-debugging-port=9312 --user-data-dir="${windows.toUpperCase()}"`;
  assert.deepEqual(chromeOwnership([quoted], [windows]), { owner: "ours" }, "a Windows Chrome under WSL");

  const other = "/home/user/work/globex/_aitna/.local/.browser/chrome-profile";
  assert.deepEqual(chromeOwnership([line(other)], profiles), { owner: "foreign", project: "globex", profile: other });
  const twin = "/home/user/old/acme/_aitna/.local/.browser/chrome-profile";
  assert.deepEqual(
    chromeOwnership([line(twin)], profiles),
    { owner: "foreign", project: "acme", profile: twin },
    "the same name elsewhere is another project",
  );
  assert.deepEqual(chromeOwnership([line("/home/user/.config/chrome-debug")], profiles), {
    owner: "foreign",
    project: null,
    profile: "/home/user/.config/chrome-debug",
  });
  assert.deepEqual(chromeOwnership(["/usr/bin/chromium --remote-debugging-port=9312"], profiles), {
    owner: "foreign",
    project: null,
    profile: null,
  });
  assert.deepEqual(chromeOwnership([], profiles), { owner: "unknown" });
});

test("the refusal names the port, whose Chrome answered and the fix", () => {
  const other = {
    owner: /** @type {const} */ ("foreign"),
    project: "globex",
    profile: "/x/globex/_aitna/.local/.browser/chrome-profile",
  };
  assert.equal(
    notOursMessage(other, { port: 9312, project: "acme" }),
    "the Chrome on 127.0.0.1:9312 is the Chrome of project globex (profile /x/globex/_aitna/.local/.browser/chrome-profile), not project acme's. " +
      "akmon does not drive it: close that Chrome, or set AKMON_BROWSER_PORT (or port in [browser] of .akmon.toml) to a free port; " +
      "then start this project's: akmon tool browser start",
  );
  assert.match(
    notOursMessage({ owner: "foreign", project: null, profile: null }, { port: 9312, project: "acme" }),
    /is a Chrome not started by akmon \(its default profile\), not project acme's/,
  );
  assert.match(
    notOursMessage({ owner: "unknown" }, { port: 9312, project: "acme" }),
    /whose it is cannot be told, not project acme's/,
  );
});

test("the port check: nothing answering, this project's Chrome, another one's", async () => {
  const version = { Browser: "Chrome/140" };
  const fail = () => assert.fail("no process is read when nothing answers");
  assert.equal(await checkPort(9312, { probe: async () => null, owner: fail, project: "acme" }), null);
  const ours = await checkPort(9312, { probe: async () => version, owner: () => ({ owner: "ours" }), project: "acme" });
  assert.equal(ours?.refusal, null);
  const other = await checkPort(9312, {
    probe: async () => version,
    owner: () => ({ owner: "foreign", project: "globex", profile: "p" }),
    project: "acme",
  });
  assert.match(other?.refusal ?? "", /project globex .* not project acme's/);
});
