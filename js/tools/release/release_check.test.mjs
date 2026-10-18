/**
 * node:test for `js/tools/release/release_check.mjs` — the version cross-check, the plan, the
 * state summary and the refusal of the akmon-subject check. The byte-level spec is the
 * `tools/release-*` scenarios of `meta/conformance/scenarios`, run by `runner.py --impl node`.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { embeddedTreeRoot } from "../../akmon/_tree.mjs";
import { read } from "../../common/jsondata.mjs";
import {
  changelogName,
  checkReleaseVersions,
  main,
  pyprojectName,
  runCheck,
  runPlan,
  runState,
  staticVersionFile,
  subjects,
} from "./release_check.mjs";

const DATA = /** @type {import("./release_check.mjs").ReleaseData} */ (
  read(path.join(embeddedTreeRoot(), "tools", "release", "release.json"))
);

/**
 * Run `fn` with the process streams captured.
 * @param {() => number} fn
 * @returns {{code: number, stdout: string, stderr: string}}
 */
function capture(fn) {
  let stdout = "";
  let stderr = "";
  const out = process.stdout.write;
  const err = process.stderr.write;
  process.stdout.write = /** @type {any} */ (
    (/** @type {string} */ text) =>
      ((stdout += text), true)
  );
  process.stderr.write = /** @type {any} */ (
    (/** @type {string} */ text) =>
      ((stderr += text), true)
  );
  try {
    return { code: fn(), stdout, stderr };
  } finally {
    process.stdout.write = out;
    process.stderr.write = err;
  }
}

/**
 * A scratch tree holding `files`.
 * @param {Record<string, string>} files
 * @returns {string}
 */
function tree(files) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "release-check-test-"));
  for (const [name, text] of Object.entries(files)) {
    fs.mkdirSync(path.dirname(path.join(dir, name)), { recursive: true });
    fs.writeFileSync(path.join(dir, name), text);
  }
  return dir;
}

/**
 * @param {string} version
 * @returns {string}
 */
const pyproject = (version) => `[project]\nname = "demo"\nversion = "${version}"\n`;

/**
 * `severity code` of each finding.
 * @param {import("../../common/findings.mjs").Finding[]} findings
 */
const brief = (findings) => findings.map((f) => `${f.severity} ${f.code}`);

test("the data accessors return the release.json facts", () => {
  assert.deepEqual(subjects(DATA), ["akmon", "package"]);
  assert.equal(changelogName(DATA), "CHANGELOG.md");
  assert.equal(pyprojectName(DATA), "pyproject.toml");
  assert.equal(staticVersionFile(DATA), "src/akmon/__init__.py");
});

test("matching literals under a topmost Unreleased heading are ok on both rules", () => {
  const root = tree({
    "pyproject.toml": pyproject("1.2.0.dev0"),
    "src/akmon/__init__.py": '_STATIC_VERSION = "1.2.0.dev0"\n',
    "CHANGELOG.md": "# Changelog\n\n## Unreleased\n\n## v1.1.0\n",
  });
  const findings = checkReleaseVersions(DATA, root, "package");
  assert.deepEqual(brief(findings).slice(0, 2), ["ok release.version-literals", "ok release.changelog-window"]);
});

test("disagreeing literals and an uncut final changelog are errors", () => {
  const root = tree({
    "pyproject.toml": pyproject("1.2.0"),
    "src/akmon/__init__.py": '_STATIC_VERSION = "1.1.0"\n',
    "CHANGELOG.md": "# Changelog\n\n## Unreleased\n",
  });
  assert.deepEqual(brief(checkReleaseVersions(DATA, root, "package")).slice(0, 2), [
    "error release.version-literals",
    "error release.changelog-window",
  ]);
});

test("a final version needs its heading topmost, in either heading spelling", () => {
  const ok = tree({ "pyproject.toml": pyproject("1.2.3"), "CHANGELOG.md": "## [1.2.3] - 2024-01-01\n\n## v1.2.2\n" });
  assert.equal(brief(checkReleaseVersions(DATA, ok, "package"))[0], "ok release.changelog-window");
  const older = tree({ "pyproject.toml": pyproject("1.2.3"), "CHANGELOG.md": "## v1.2.2\n\n## v1.2.3\n" });
  assert.equal(brief(checkReleaseVersions(DATA, older, "package"))[0], "error release.changelog-window");
  const pre = tree({ "pyproject.toml": pyproject("1.2.3"), "CHANGELOG.md": "## v1.2.3rc1\n" });
  assert.equal(brief(checkReleaseVersions(DATA, pre, "package"))[0], "error release.changelog-window");
});

test("no version source and a missing changelog are skip findings, never silence", () => {
  const none = checkReleaseVersions(DATA, tree({}), "package");
  assert.equal(brief(none)[0], "warn release.check-skipped");
  const noLog = checkReleaseVersions(DATA, tree({ "pyproject.toml": pyproject("1.0.0") }), "package");
  assert.equal(brief(noLog)[0], "warn release.check-skipped");
});

test("a pyproject without a project version, or a broken one, declares nothing", () => {
  const other = tree({ "pyproject.toml": '[tool.x]\nversion = "9.9.9"\n', "CHANGELOG.md": "## Unreleased\n" });
  assert.equal(checkReleaseVersions(DATA, other, "package")[0].code, "release.check-skipped");
  const broken = tree({ "pyproject.toml": "[project\nversion = ", "CHANGELOG.md": "## Unreleased\n" });
  assert.equal(checkReleaseVersions(DATA, broken, "package")[0].code, "release.check-skipped");
});

test("the npm carrier is checked for the akmon subject against the derived spelling", () => {
  const files = { "pyproject.toml": pyproject("0.4.0.dev0"), "CHANGELOG.md": "## Unreleased\n" };
  const match = tree({ ...files, "package.json": '{"version": "0.4.0-dev.0"}' });
  assert.deepEqual(brief(checkReleaseVersions(DATA, match, "akmon")).slice(0, 2), [
    "ok release.version-literals",
    "ok release.changelog-window",
  ]);
  const wrong = tree({ ...files, "package.json": '{"version": "0.4.0"}' });
  assert.equal(brief(checkReleaseVersions(DATA, wrong, "akmon"))[0], "error release.version-literals");
  const missing = tree(files);
  assert.equal(brief(checkReleaseVersions(DATA, missing, "akmon"))[0], "error release.version-literals");
  const unrepresentable = tree({ ...files, "pyproject.toml": pyproject("0.4.0rc1") });
  assert.equal(brief(checkReleaseVersions(DATA, unrepresentable, "akmon"))[0], "warn release.check-skipped");
  assert.equal(brief(checkReleaseVersions(DATA, match, "package")).includes("ok release.version-literals"), false);
});

test("tags: spelling, re-release and undocumented tags are warnings", () => {
  const root = tree({ "pyproject.toml": pyproject("1.2.0"), "CHANGELOG.md": "## v1.2.0\n\n## v1.1.0\n" });
  const git = (/** @type {string[]} */ ...args) =>
    spawnSync("git", ["-C", root, "-c", "user.name=t", "-c", "user.email=t@t", ...args], { encoding: "utf8" });
  git("init", "-q");
  git("commit", "-q", "--allow-empty", "-m", "base");
  for (const tag of ["v1.2.0", "1.1.0", "v0.9.0"]) {
    git("tag", tag);
  }
  assert.deepEqual(brief(checkReleaseVersions(DATA, root, "package")), [
    "ok release.changelog-window",
    "warn release.tag-spelling",
    "warn release.retag",
    "warn release.undocumented-tag",
  ]);
});

test("runPlan prints the package plan and refuses a malformed version", () => {
  const ok = capture(() => runPlan(DATA, "v1.2.3", "package"));
  assert.equal(ok.code, 0);
  assert.match(ok.stdout, /git commit -m "release v1\.2\.3"\n/);
  const bad = capture(() => runPlan(DATA, "1.2.3", "package"));
  assert.deepEqual(bad, { code: 2, stdout: "", stderr: "error: version must look like vX.Y.Z, got '1.2.3'\n" });
});

test("runPlan for the akmon subject names the derived SemVer spelling", () => {
  const result = capture(() => runPlan(DATA, "v0.5.0", "akmon"));
  assert.equal(result.code, 0);
  assert.match(result.stdout, /derives from that literal — 0\.5\.0 —/);
  assert.match(result.stdout, /release reopened would read 0\.5\.0-dev\.0/);
});

test("runState summarizes a package project root", () => {
  const root = tree({
    "TASKS.md": "- C1 · a · done · e\n- C2 · b · active · e\n",
    "CHANGELOG.md": "## Unreleased\n## v1.0.0\n",
  });
  const result = capture(() => runState(DATA, root, "package"));
  assert.equal(result.code, 0);
  assert.match(result.stdout, /^== release state \(subject: package\) ==\nproject root: /);
  assert.match(result.stdout, /TASKS\.md: 2 entry\(ies\)\n {2}! 1 'done' entry\(ies\)/);
  assert.match(result.stdout, /TASKS_ARCHIVE\.md: \(missing\)/);
  assert.match(result.stdout, /CHANGELOG\.md sections:\n {2}- Unreleased\n {2}- v1\.0\.0\n/);
  assert.match(result.stdout, /\(MISSING — add it/);
});

test("runState: a task line behind a BOM is no entry, as str.lstrip() keeps the BOM (C115)", () => {
  const root = tree({
    "TASKS.md": "\uFEFF- C1 · a · done · e\n- C2 · b · active · e\n",
    "CHANGELOG.md": "## Unreleased\n",
  });
  const result = capture(() => runState(DATA, root, "package"));
  assert.match(result.stdout, /TASKS\.md: 1 entry\(ies\)\n/);
  assert.doesNotMatch(result.stdout, /'done' entry/);
});

test("runState refuses the akmon subject when its whole meta/ is absent", () => {
  const root = tree({ "_aitna/akmon/README.md": "x\n" });
  const result = capture(() => runState(DATA, root, "akmon"));
  assert.deepEqual(result, { code: 2, stdout: "", stderr: `${DATA.run_state.akmon_meta_absent}\n` });
  assert.match(result.stderr, /run it from the akmon git tree: a clone, or a project mounting it/);
});

test("runState reads the running tree when no akmon is mounted: this akmon checkout's meta/", () => {
  // The test runs from the akmon git tree, which carries meta/ and CHANGELOG.md: a clone's case.
  const root = tree({ "AGENTS.md": "x\n" });
  const result = capture(() => runState(DATA, root, "akmon"));
  assert.equal(result.code, 0);
  assert.equal(result.stderr, "");
  assert.match(result.stdout, /\nTASKS\.md: [0-9]+ entry\(ies\)\n/);
  assert.match(result.stdout, /\nCHANGELOG\.md sections:\n {2}- Unreleased\n/);
});

test("runState keeps the (missing) line for one file absent from the akmon meta/", () => {
  const root = tree({ "_aitna/akmon/meta/TASKS.md": "- C1 · a · active · e\n" });
  const result = capture(() => runState(DATA, root, "akmon"));
  assert.equal(result.code, 0);
  assert.match(result.stdout, /TASKS\.md: 1 entry\(ies\)\n/);
  assert.match(result.stdout, /TASKS_ARCHIVE\.md: \(missing\)\n/);
});

test("runCheck refuses the akmon subject: its suite is the Python self-CI", () => {
  const result = capture(() => runCheck(DATA, "/nonexistent", "akmon"));
  assert.deepEqual(result, { code: 2, stdout: "", stderr: `${DATA.run_check.akmon_python_only}\n` });
  assert.match(result.stderr, /python3 tools\/release\/release_check\.py --check\n$/);
});

test("main: the default subject is akmon and the default mode is the refused check", () => {
  const root = tree({ "AGENTS.md": "x\n", "_aitna/.akmon.toml": 'mount = "package"\n' });
  const result = capture(() => main(["--project-root", root]));
  assert.equal(result.code, 2);
  assert.equal(result.stderr, `${DATA.run_check.akmon_python_only}\n`);
});

test("main: usage errors are one line and exit 2", () => {
  assert.equal(
    capture(() => main(["--subject", "x"])).stderr,
    "release_check.mjs: error: argument --subject: invalid choice: 'x' (choose from 'akmon', 'package')\n",
  );
  assert.equal(
    capture(() => main(["--state", "--check"])).stderr,
    "release_check.mjs: error: argument --check: not allowed with argument --state\n",
  );
  assert.equal(capture(() => main(["--bogus"])).code, 2);
  assert.equal(capture(() => main(["--help"])).code, 0);
});

test("main: a stray positional is refused like argparse, exit 2 on stderr", () => {
  const result = capture(() => main(["--plan", "v1.2.3", "extra"]));
  assert.deepEqual(result, {
    code: 2,
    stdout: "",
    stderr: "release_check.mjs: error: unrecognized arguments: extra\n",
  });
});
