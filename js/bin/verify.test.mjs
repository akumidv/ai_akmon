/**
 * node:test for `js/bin/verify.mjs` — what only the JavaScript implementation has (the Node
 * launcher, pin and hook-file findings, the refusal of any other record) and the named pins of the
 * twin: the Unicode meaning of its text patterns, the glob of the isolation scan, the host-trust
 * seam. The whole command against the Python reference is the shared `cli/verify-*` scenarios of
 * the corpus and the differential run of C105.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import { posix } from "node:path";
import { fileURLToPath } from "node:url";

import { TEXT_PATTERNS, Verifier, main, mergeOverlay, readVerifyData } from "./verify.mjs";
import { apply, codexHooksText, plannedFiles, readSyncData } from "./sync.mjs";
import * as alwaysLoaded from "../common/always_loaded.mjs";
import * as codexHooks from "../common/codex_hooks.mjs";
import { read } from "../common/jsondata.mjs";
import { CATALOG_FORMATS, defaultModelToken } from "../tools/model_routing/routing.mjs";

const TREE = fs.realpathSync(posix.resolve(posix.dirname(fileURLToPath(import.meta.url)), "..", ".."));
const data = readVerifyData();
const AGENTS_DATA = /** @type {any} */ (read(posix.join(TREE, "tools", "model_routing", "agents.json")));
const syncData = readSyncData();
const VERSION = /** @type {{version: string}} */ (
  JSON.parse(fs.readFileSync(posix.join(TREE, "package.json"), "utf-8"))
).version;
const NODE_RECORD = `mount = "package"\necosystem = "node"\nakmon_version = "${VERSION}"\nattached_archetype = "unclassified"\nlast_realign = "${VERSION}"\n`;
const AGENTS =
  "# AGENTS.md\n\n## Dev layer — akmon\n\n@_aitna/.akmon/guardrails/_common.md\n@_aitna/.akmon/profiles/js.md\n\n" +
  "Run `akmon path` to find the standard. Archetype: `ARCHETYPES.md`. Read `_aitna/memory` at session start.\n\n" +
  "The owner verifies consequential decisions. D5 is always-on. Secrets come from `.env`.\n\n" +
  "Skills live in root `skills/`; generated vendor skill stubs are pointers only.\n\n**Delegation is the default.** Delegate.\n";
const CI = "steps:\n  - run: npx akmon sync --check\n  - run: npx akmon verify --strict\n";

/**
 * A scratch directory removed after `body`.
 * @param {(scratch: string) => void | Promise<void>} body
 */
async function withScratch(body) {
  const scratch = fs.realpathSync(fs.mkdtempSync(posix.join(os.tmpdir(), "akmon-verify-test-")));
  try {
    await body(scratch);
  } finally {
    fs.rmSync(scratch, { recursive: true, force: true });
  }
}

/** Write `text` at `relative` under `base`, making the directories. */
function put(/** @type {string} */ base, /** @type {string} */ relative, /** @type {string | Buffer} */ text) {
  fs.mkdirSync(posix.dirname(posix.join(base, relative)), { recursive: true });
  fs.writeFileSync(posix.join(base, relative), text);
}

/**
 * Run `body` with `PATH` set as given, then restored.
 * @template T
 * @param {string} value
 * @param {() => Promise<T>} body
 * @returns {Promise<T>}
 */
async function withPath(value, body) {
  const saved = process.env.PATH;
  process.env.PATH = value;
  try {
    return await body();
  } finally {
    process.env.PATH = saved;
  }
}

/**
 * Run `body` with `AITNA_ROOT` unset, then restored.
 * @template T
 * @param {() => Promise<T>} body
 * @returns {Promise<T>}
 */
async function withoutAitnaRoot(body) {
  const saved = process.env.AITNA_ROOT;
  delete process.env.AITNA_ROOT;
  try {
    return await body();
  } finally {
    if (saved !== undefined) {
      process.env.AITNA_ROOT = saved;
    }
  }
}

/**
 * A Node package-mode project under `scratch` that `verify` finds healthy once synced: the record,
 * a hand-owned AGENTS.md, the dev layer, CI, `.gitignore`, the pin, and `node_modules/akmon`
 * linked to this tree.
 * @param {string} scratch
 * @param {{pin?: string | null, link?: boolean}} [options]
 * @returns {string} the project root
 */
function project(scratch, { pin = VERSION, link = true } = {}) {
  const root = posix.join(scratch, "project");
  put(root, "_aitna/.akmon.toml", NODE_RECORD);
  put(root, "AGENTS.md", AGENTS);
  put(root, "_aitna/TASKS.md", "# Tasks\n\n- T1 · demo · active · engineer · keep valid\n");
  put(root, "_aitna/agents/e/README.md", "# e\n\nFollows the akmon role `_aitna/akmon/roles/review.md`.\n");
  put(root, "_aitna/memory/README.md", "# memory\n- note.md\n");
  put(root, "_aitna/memory/note.md", "fact\n");
  put(root, ".gitignore", "*.env\n!*.env.example\n");
  put(root, ".github/workflows/ci.yml", CI);
  if (pin !== null) {
    put(root, "package.json", `${JSON.stringify({ name: "c", private: true, devDependencies: { akmon: pin } })}\n`);
  }
  if (link) {
    fs.mkdirSync(posix.join(root, "node_modules"));
    fs.symlinkSync(TREE, posix.join(root, "node_modules", "akmon"));
  }
  return root;
}

const MOUNTED_RECORD = `mount = "submodule"\necosystem = "node"\nakmon_version = "${VERSION}"\nattached_archetype = "unclassified"\nlast_realign = "${VERSION}"\n`;
const MOUNTED_AGENTS =
  "# AGENTS.md\n\n## Dev layer — akmon\n\n@_aitna/akmon/guardrails/_common.md\n@_aitna/akmon/profiles/js.md\n\n" +
  "Model: `_aitna/akmon/README.md`. Archetype: `ARCHETYPES.md`. Roles: `_aitna/akmon/roles/`. " +
  "Read `_aitna/memory` at session start.\n\n" +
  "The owner verifies consequential decisions. D5 is always-on. Secrets come from `.env`.\n\n" +
  "Skills live in root `skills/`; generated vendor skill stubs are pointers only.\n\n**Delegation is the default.** Delegate.\n";
const MOUNTED_CI =
  "steps:\n  - run: node _aitna/akmon/js/akmon/cli.mjs sync --check\n  - run: node _aitna/akmon/js/akmon/cli.mjs verify --strict\n";

/**
 * A Node project under `scratch` attached in a mounted mode (C129) that `verify` finds healthy once
 * synced: the package project's dev layer, a mounted record, AGENTS.md and CI, a `package.json` with
 * no akmon pin, and `<dev root>/akmon` linked to this tree (`mount: null` leaves the link out).
 * @param {string} scratch
 * @param {{record?: string, mount?: string | null}} [options]
 * @returns {string} the project root
 */
function mountedProject(scratch, { record = MOUNTED_RECORD, mount = TREE } = {}) {
  const root = project(scratch, { pin: null, link: false });
  put(root, "_aitna/.akmon.toml", record);
  put(root, "AGENTS.md", MOUNTED_AGENTS);
  put(root, ".github/workflows/ci.yml", MOUNTED_CI);
  put(root, "package.json", '{"name": "c", "private": true}\n');
  if (mount !== null) {
    fs.symlinkSync(mount, posix.join(root, "_aitna", "akmon"));
  }
  return root;
}

/**
 * `sync` writes every generated file of `root` (the plan, applied).
 * @param {string} root
 */
function syncWrite(root) {
  const [files] = plannedFiles(syncData, root);
  apply(syncData, files, { write: true, root });
}

/**
 * `main(argv)` with the streams captured.
 * @param {string[]} argv
 * @param {{codexHooksRunner?: import("../common/codex_hooks.mjs").HooksListRunner}} [options]
 * @returns {Promise<{code: number, stdout: string, stderr: string}>}
 */
async function run(argv, options = {}) {
  const out = process.stdout.write;
  const err = process.stderr.write;
  let stdout = "";
  let stderr = "";
  process.stdout.write = /** @type {any} */ (
    (/** @type {string} */ chunk) =>
      ((stdout += chunk), true)
  );
  process.stderr.write = /** @type {any} */ (
    (/** @type {string} */ chunk) =>
      ((stderr += chunk), true)
  );
  try {
    const code = await main(argv, options);
    return { code, stdout, stderr };
  } finally {
    process.stdout.write = out;
    process.stderr.write = err;
  }
}

/**
 * The findings of `verifier` for `code`, as `[severity, target, message, fix]`.
 * @param {Verifier} verifier
 * @param {string} code
 */
function of(verifier, code) {
  return verifier.findings
    .filter((finding) => finding.code === code)
    .map((finding) => [finding.severity, finding.target, finding.message, finding.fix]);
}

// -- hooks.launcher (node) ---------------------------------------------------------------------

test("hooks.launcher: node_modules/akmon/js/hooks present is ok, a real folder or a link alike", async () => {
  await withScratch((scratch) => {
    const root = project(scratch);
    const verifier = new Verifier(root);
    verifier.checkHookLauncher();
    const [[severity, target, message]] = of(verifier, "hooks.launcher");
    assert.equal(severity, "ok");
    assert.equal(target, "node_modules/akmon/js/hooks");
    assert.equal(message, "generated hook wiring runs node on node_modules/akmon/js/hooks, which is present");
  });
});

test("hooks.launcher: a pnpm-style link is present, and the message never names the link's target", async () => {
  await withScratch((scratch) => {
    const root = project(scratch, { link: false });
    put(root, "node_modules/.pnpm/akmon@1.0.0/node_modules/akmon/js/hooks/hook_core.mjs", "");
    fs.symlinkSync(".pnpm/akmon@1.0.0/node_modules/akmon", posix.join(root, "node_modules", "akmon"));
    const verifier = new Verifier(root);
    verifier.checkHookLauncher();
    const found = of(verifier, "hooks.launcher");
    assert.equal(found.length, 1);
    assert.equal(found[0][0], "ok");
    assert.ok(!found[0].join(" ").includes(".pnpm"));
  });
});

test("hooks.launcher: Yarn Plug'n'Play is an error, by either marker, and wins over a folder that is there", async () => {
  for (const marker of [".pnp.cjs", ".pnp.loader.mjs"]) {
    await withScratch((scratch) => {
      // a real node_modules/akmon/js/hooks folder is there too: the PnP marker still decides
      const root = project(scratch, { link: false });
      put(root, "node_modules/akmon/js/hooks/hook_core.mjs", "");
      put(root, marker, "");
      const verifier = new Verifier(root);
      verifier.checkHookLauncher();
      const [[severity, target, message, fix]] = of(verifier, "hooks.launcher");
      assert.equal(severity, "error");
      assert.equal(target, marker);
      assert.match(message, /^Yarn Plug'n'Play is in use \(/);
      assert.ok(message.includes(`${marker} is present`));
      assert.ok(message.includes("fails silently"));
      assert.equal(
        fix,
        "Set nodeLinker: node-modules in .yarnrc.yml and reinstall the dependencies, then re-run akmon sync.",
      );
    });
  }
});

test("hooks.launcher: akmon only in an ancestor's node_modules is an error naming where, with the devDependencies fix", async () => {
  await withScratch((scratch) => {
    put(scratch, "node_modules/akmon/package.json", "{}");
    const root = project(scratch, { link: false });
    const nested = posix.join(root, "packages", "app");
    put(nested, "package.json", "{}");
    put(nested, "_aitna/.akmon.toml", NODE_RECORD);
    const verifier = new Verifier(nested);
    verifier.checkHookLauncher();
    const [[severity, target, message, fix]] = of(verifier, "hooks.launcher");
    assert.equal(severity, "error");
    assert.equal(target, "node_modules/akmon/js/hooks");
    assert.ok(message.includes("but akmon is installed at ../../../node_modules/akmon"), message);
    assert.ok(message.includes("neither the committed wiring nor the generated pointers can reach it"));
    assert.equal(
      fix,
      "Install akmon in this package's own devDependencies so it is linked into its own node_modules, then re-run akmon sync.",
    );
  });
});

test("hooks.launcher: the nearest ancestor holding node_modules/akmon is the one named", async () => {
  await withScratch((scratch) => {
    put(scratch, "node_modules/akmon/package.json", "{}");
    put(scratch, "ws/node_modules/akmon/package.json", "{}");
    const nested = posix.join(scratch, "ws", "pkg");
    put(nested, "_aitna/.akmon.toml", NODE_RECORD);
    const verifier = new Verifier(nested);
    verifier.checkHookLauncher();
    const [[, , message]] = of(verifier, "hooks.launcher");
    assert.ok(message.includes("installed at ../node_modules/akmon"), message);
  });
});

test("hooks.launcher: a local node_modules/akmon wins over a hoisted one", async () => {
  await withScratch((scratch) => {
    put(scratch, "node_modules/akmon/package.json", "{}");
    const root = project(scratch);
    const verifier = new Verifier(root);
    verifier.checkHookLauncher();
    assert.equal(of(verifier, "hooks.launcher")[0][0], "ok");
  });
});

test("hooks.launcher: missing is an error that says every hook command fails silently, and how to fix it", async () => {
  await withScratch((scratch) => {
    const root = project(scratch, { link: false });
    const verifier = new Verifier(root);
    verifier.checkHookLauncher();
    const [[severity, target, message, fix]] = of(verifier, "hooks.launcher");
    assert.equal(severity, "error");
    assert.equal(target, "node_modules/akmon/js/hooks");
    assert.equal(
      message,
      "generated hook wiring runs node on node_modules/akmon/js/hooks, which is missing — every akmon hook command fails " +
        "silently (an unavailable script produces no session-visible error), so the guardrails are off",
    );
    assert.equal(fix, "Install the project's dependencies so node_modules/akmon exists, then re-run akmon sync.");
  });
});

test("hooks.launcher: a link whose target is gone, and a plain file, are missing", async () => {
  await withScratch((scratch) => {
    const root = project(scratch, { link: false });
    fs.mkdirSync(posix.join(root, "node_modules"));
    fs.symlinkSync("nowhere", posix.join(root, "node_modules", "akmon"));
    const verifier = new Verifier(root);
    verifier.checkHookLauncher();
    assert.equal(of(verifier, "hooks.launcher")[0][0], "error");
  });
  await withScratch((scratch) => {
    const root = project(scratch, { link: false });
    put(root, "node_modules/akmon", "file");
    const verifier = new Verifier(root);
    verifier.checkHookLauncher();
    assert.equal(of(verifier, "hooks.launcher")[0][0], "error");
  });
});

test("hooks.launcher: a folder without js/hooks (an old install) is missing, not present", async () => {
  await withScratch((scratch) => {
    const root = project(scratch, { link: false });
    put(root, "node_modules/akmon/package.json", "{}");
    const verifier = new Verifier(root);
    verifier.checkHookLauncher();
    assert.equal(of(verifier, "hooks.launcher")[0][0], "error");
  });
});

// -- package.dev-pin (node) ----------------------------------------------

/**
 * The pin findings of a project whose `package.json` is `manifest` (text), or none when `null`.
 * @param {string | null} manifest
 */
async function pinFindings(manifest) {
  /** @type {Array<[string, string, string, string, string]>} */
  let found = [];
  await withScratch((scratch) => {
    const root = project(scratch, { pin: null });
    if (manifest !== null) {
      put(root, "package.json", manifest);
    }
    const verifier = new Verifier(root);
    verifier.checkPackagePin();
    found = verifier.findings.map((f) => [f.severity, f.code, f.target, f.message, f.fix]);
  });
  return found;
}

test("package.dev-pin: no package.json is no finding at all", async () => {
  assert.deepEqual(await pinFindings(null), []);
});

test("package.dev-pin: dependencies, optionalDependencies and peerDependencies are errors; the worst class wins", async () => {
  for (const table of ["dependencies", "optionalDependencies", "peerDependencies"]) {
    const found = await pinFindings(JSON.stringify({ [table]: { akmon: "1.0.0" } }));
    assert.equal(found.length, 1, table);
    assert.deepEqual(found[0].slice(0, 3), ["error", "package.dev-pin", "package.json"]);
    assert.match(found[0][3], /runtime dependency/);
    assert.equal(found[0][4], "Move the akmon requirement into devDependencies.");
  }
  const both = await pinFindings(
    JSON.stringify({ dependencies: { akmon: "1.0.0" }, devDependencies: { akmon: "1.0.0" } }),
  );
  assert.deepEqual(
    both.map((f) => [f[0], f[1]]),
    [["error", "package.dev-pin"]],
  );
});

test("package.dev-pin: no pin is a warning with the install command; an unreadable manifest is a warning too", async () => {
  const none = await pinFindings(JSON.stringify({ name: "x", devDependencies: { other: "1.0.0" } }));
  assert.deepEqual(
    none.map((f) => [f[0], f[1]]),
    [["warn", "package.dev-pin"]],
  );
  assert.equal(none[0][4], "Pin akmon in devDependencies with `npm install -D -E akmon`.");
  for (const broken of ["{nope", "[]", '"s"', ""]) {
    const found = await pinFindings(broken);
    assert.deepEqual(
      found.map((f) => [f[0], f[1]]),
      [["warn", "package.dev-pin"]],
      JSON.stringify(broken),
    );
    assert.match(found[0][3], /not a valid JSON object/);
  }
});

test("package.dev-pin exactness: an exact version in devDependencies is ok", async () => {
  for (const version of [
    "1.2.3",
    "=1.2.3",
    "0.4.0-dev.0",
    "1.2.3-rc.1",
    "1.2.3+build.5",
    "1.2.3-rc.1+exp.sha.5114f85",
    "10.20.30",
  ]) {
    const found = await pinFindings(JSON.stringify({ devDependencies: { akmon: version } }));
    assert.deepEqual(
      found.map((f) => [f[0], f[1]]),
      [["ok", "package.dev-pin"]],
      version,
    );
    assert.equal(found[0][3], "package.json pins akmon in devDependencies");
  }
});

test("package.dev-pin exactness: a git dependency at an exact release tag is ok", async () => {
  for (const spec of [
    "github:akumidv/ai_akmon#v1.2.3",
    "github:akumidv/ai_akmon#1.2.3",
    "gitlab:group/sub/akmon#v0.4.0-dev.0",
    "bitbucket:o/akmon#v1.2.3+build.5",
    "akumidv/ai_akmon#v1.2.3",
    "git+https://github.com/akumidv/ai_akmon.git#v1.2.3",
    "git+http://example.com/akmon.git#v1.2.3",
    "git+ssh://git@github.com/akumidv/ai_akmon.git#v1.2.3-rc.1",
    "git://github.com/akumidv/ai_akmon.git#v10.20.30",
  ]) {
    const found = await pinFindings(JSON.stringify({ devDependencies: { akmon: spec } }));
    assert.deepEqual(
      found.map((f) => [f[0], f[1]]),
      [["ok", "package.dev-pin"]],
      spec,
    );
  }
});

test("package.dev-pin exactness: a git dependency at a branch, range, commit or no tag is a warning", async () => {
  for (const spec of [
    "github:akumidv/ai_akmon",
    "github:akumidv/ai_akmon#main",
    "github:akumidv/ai_akmon#semver:^1.2.3",
    "github:akumidv/ai_akmon#semver:v1.2.3",
    "github:akumidv/ai_akmon#3f2a9c1d4e5b6a7c8d9e0f1a2b3c4d5e6f7a8b9c",
    "github:akumidv/ai_akmon#v1.2",
    "github:akumidv/ai_akmon#vv1.2.3",
    "github:akumidv/ai_akmon#v1.2.3 ",
    "akumidv/ai_akmon#release",
    "git+https://github.com/akumidv/ai_akmon.git",
    "git+https://github.com/akumidv/ai_akmon.git#main",
    "https://github.com/akumidv/ai_akmon.git#v1.2.3",
    "https://example.com/akmon-1.2.3.tgz",
    "file:../akmon#v1.2.3",
    "../akmon#v1.2.3",
    "npm:akmon@1.2.3#v1.2.3",
  ]) {
    const found = await pinFindings(JSON.stringify({ devDependencies: { akmon: spec } }));
    assert.deepEqual(
      found.map((f) => [f[0], f[1]]),
      [["warn", "package.dev-pin"]],
      spec,
    );
  }
});

test("package.dev-pin exactness: anything that is not an exact version is a warning naming the value", async () => {
  const cases = [
    ["^1.2.3", "'^1.2.3'"],
    ["~1.2.3", "'~1.2.3'"],
    [">=1.0.0", "'>=1.0.0'"],
    ["1.x", "'1.x'"],
    ["1.2", "'1.2'"],
    ["*", "'*'"],
    ["latest", "'latest'"],
    ["workspace:*", "'workspace:*'"],
    ["file:../akmon", "'file:../akmon'"],
    ["git+https://example.com/akmon.git", "'git+https://example.com/akmon.git'"],
    ["https://example.com/a.tgz", "'https://example.com/a.tgz'"],
    ["1.2.3 || 2.0.0", "'1.2.3 || 2.0.0'"],
    ["v1.2.3", "'v1.2.3'"],
    [" 1.2.3", "' 1.2.3'"],
    ["1.2.3\n", "'1.2.3\\n'"],
    ["", "''"],
    ["1.2.3-", "'1.2.3-'"],
    ["npm:akmon@1.2.3", "'npm:akmon@1.2.3'"],
    [7, "7"],
    [null, "null"],
    [["1.2.3"], '["1.2.3"]'],
  ];
  for (const [value, spelled] of cases) {
    const found = await pinFindings(JSON.stringify({ devDependencies: { akmon: value } }));
    assert.deepEqual(
      found.map((f) => [f[0], f[1]]),
      [["warn", "package.dev-pin"]],
      JSON.stringify(value),
    );
    assert.equal(found[0][2], "package.json");
    assert.ok(found[0][3].startsWith(`package.json pins akmon as ${spelled}, not an exact version`), found[0][3]);
    assert.equal(
      found[0][4],
      "Pin an exact version with `npm install -D -E akmon@<version>`, or a release tag with `npm install -D github:akumidv/ai_akmon#v<version>`.",
    );
  }
});

test("package.dev-pin exactness: only the devDependencies class is judged for exactness", async () => {
  const found = await pinFindings(JSON.stringify({ dependencies: { akmon: "^1.0.0" } }));
  assert.deepEqual(
    found.map((f) => f[1]),
    ["package.dev-pin"],
  );
});

// -- layout.standard-path (node) ---------------------------------------------------------------

// -- check.ruff-without-python (C129) ---------------------------------------------------------

/**
 * The ruff.toml `akmon init` writes, for the `.akmon` (package) or `akmon` (mounted) rules path.
 * @param {string} mount
 */
function initRuffToml(mount) {
  return (
    "# ruff with akmon's Python rules; adjust them here with extend-select, extend-ignore and\n" +
    `# per-file-ignores.\nextend = "_aitna/${mount}/profiles/ruff.toml"\n`
  );
}

/**
 * The `check.ruff-without-python` findings of a Node project holding `ruffToml` and `extra` files.
 * @param {string | null} ruffToml
 * @param {string[]} [extra]
 */
async function ruffFindings(ruffToml, extra = []) {
  /** @type {unknown[]} */
  let found = [];
  await withScratch((scratch) => {
    const root = project(scratch, { link: false });
    if (ruffToml !== null) {
      put(root, "ruff.toml", ruffToml);
    }
    for (const name of extra) {
      put(root, name, "");
    }
    const verifier = new Verifier(root);
    verifier.checkRuffWithoutPython();
    found = of(verifier, "check.ruff-without-python");
  });
  return found;
}

test("check.ruff-without-python: init's ruff.toml in a Node project with no Python files warns", async () => {
  for (const mount of [".akmon", "akmon"]) {
    assert.deepEqual(await ruffFindings(initRuffToml(mount)), [
      [
        "warn",
        "ruff.toml",
        "ruff.toml is the one akmon init writes for ruff, but this project has package.json and no Python " +
          "files (pyproject.toml, setup.py, setup.cfg, requirements*.txt, Pipfile, uv.lock, poetry.lock, or a " +
          "*.py file outside <dev root> and node_modules (git-tracked in a work tree)): ruff has nothing to lint here",
        "Remove ruff.toml, and name the project's own checks under [check] in _aitna/.akmon.toml.",
      ],
    ]);
  }
});

test("check.ruff-without-python: Python files, an edited or foreign ruff.toml, or none is never named", async () => {
  for (const marker of [
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "requirements.txt",
    "requirements-dev.txt",
    "Pipfile",
    "uv.lock",
    "poetry.lock",
    "app/x.py",
  ]) {
    assert.deepEqual(await ruffFindings(initRuffToml(".akmon"), [marker]), [], marker);
  }
  // Python under the dev layer, node_modules or a dot-directory is no project code
  for (const elsewhere of ["_aitna/akmon/bin/sync.py", "node_modules/x/y.py", ".venv/z.py"]) {
    assert.equal((await ruffFindings(initRuffToml(".akmon"), [elsewhere])).length, 1, elsewhere);
  }
  assert.deepEqual(await ruffFindings(null), []);
  assert.deepEqual(await ruffFindings(`${initRuffToml(".akmon")}line-length = 100\n`), []);
  assert.deepEqual(await ruffFindings(initRuffToml(".akmon").replaceAll("\n", "\r\n")), []);
  assert.deepEqual(await ruffFindings(initRuffToml("other")), []);
});

test("check.ruff-without-python: the template is sync.json's, the one the Python init writes", () => {
  assert.equal(
    syncData.sync.ruff_toml_template.replace("{{rules_path}}", "_aitna/.akmon/profiles/ruff.toml"),
    initRuffToml(".akmon"),
  );
  assert.deepEqual(syncData.sync.python_markers.files, [
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "requirements*.txt",
    "Pipfile",
    "uv.lock",
    "poetry.lock",
  ]);
});

test("node_wired_hook_scripts: the entry points and every module they import, and nothing else", () => {
  const listed = data.node_wired_hook_scripts;
  const hooksDir = posix.join(TREE, "js", "hooks");
  const entries = [
    "codex-hook",
    "git-commit-guard",
    "session-start-agent",
    "role-on-code",
    "analysis-guard",
    "model-routing",
    "delegation-log",
    "delegation-nudge",
    "gate-audit",
    "learning-reminder",
  ];
  for (const entry of entries) {
    assert.ok(listed.includes(`${entry}.mjs`), entry);
  }
  // every sibling module an entry (or an adapter) imports is wired too
  /** @type {Set<string>} */
  const reached = new Set();
  const visit = (/** @type {string} */ file) => {
    if (reached.has(file)) {
      return;
    }
    reached.add(file);
    const source = fs.readFileSync(posix.join(hooksDir, file), "utf-8");
    for (const match of source.matchAll(/from "\.\/([A-Za-z_-]+\.mjs)"/g)) {
      visit(match[1]);
    }
  };
  entries.forEach((entry) => visit(`${entry}.mjs`));
  assert.deepEqual([...reached].sort(), [...listed].sort());
  for (const file of listed) {
    assert.ok(fs.statSync(posix.join(hooksDir, file)).isFile(), file);
  }
});

test("node_wired_hook_scripts: every hook script the generated wiring runs is on the list", () => {
  const wiring = JSON.stringify([
    codexHooksText(syncData, posix.join(TREE, "no-such-project")),
    JSON.stringify([...Object.values(syncData.sync.claude_hooks)]),
  ]);
  const named = [...new Set([...wiring.matchAll(/js\/hooks\/([A-Za-z-]+)\.mjs/g)].map((m) => `${m[1]}.mjs`))];
  for (const script of Object.values(syncData.sync.claude_hooks).flatMap((entries) =>
    entries.flatMap((entry) => entry.commands),
  )) {
    assert.ok(data.node_wired_hook_scripts.includes(`${script}.mjs`), script);
  }
  assert.ok(named.includes("codex-hook.mjs"));
  assert.ok(data.node_wired_hook_scripts.includes("codex-hook.mjs"));
});

test("checkHooks: each wired file is checked as js/hooks/<file> in the standard tree", async () => {
  await withScratch((scratch) => {
    const root = project(scratch);
    const verifier = new Verifier(root);
    verifier.checkHooks();
    const found = of(verifier, "layout.standard-path");
    assert.equal(found.length, data.node_wired_hook_scripts.length);
    assert.deepEqual(found[0].slice(0, 3), [
      "ok",
      "standard tree:js/hooks/hook_core.mjs",
      "standard tree:js/hooks/hook_core.mjs exists",
    ]);
    // a tree without the files: every one is an error with the restore fix
    const bare = posix.join(scratch, "bare");
    fs.mkdirSync(bare);
    const missing = new Verifier(root);
    missing.standardRoot = bare;
    missing.checkHooks();
    const errors = of(missing, "layout.standard-path");
    assert.ok(errors.every(([severity]) => severity === "error"));
    assert.equal(
      errors[1][3],
      "Restore standard tree:js/hooks/claude_adapter.mjs by re-attaching or updating the akmon standard tree.",
    );
  });
});

// -- the refusal -------------------------------------------------------------------------------

/**
 * `found` for a project whose record is `record` (`null`: none), as the refusal prints it.
 * @param {string | null} record
 * @param {string} found
 */
async function refusal(record, found) {
  await withScratch(async (scratch) => {
    const root = project(scratch, { link: false });
    if (record === null) {
      fs.rmSync(posix.join(root, "_aitna", ".akmon.toml"));
    } else {
      put(root, "_aitna/.akmon.toml", record);
    }
    const result = await withoutAitnaRoot(() => run(["--project-root", root]));
    assert.deepEqual(result, {
      code: 2,
      stdout: "",
      stderr:
        'akmon verify: the JavaScript implementation serves Node projects only (ecosystem = "node" in ' +
        `<dev root>/.akmon.toml), but this project has ${found}; run the Python implementation of akmon for it.\n`,
    });
  });
}

test("a project with no record is refused, exit 2, nothing on stdout", async () => {
  await refusal(null, "no integration record (_aitna/.akmon.toml)");
});

test("a Python mounted record is refused, its ecosystem named (python when it names none)", async () => {
  await refusal('mount = "vendored"\necosystem = "python"\n', 'ecosystem = "python"');
  await refusal('akmon_version = "1"\n', 'ecosystem = "python"');
  await refusal('mount = "subtree"\n', 'ecosystem = "python"');
});

test("a Python package record is refused: no ecosystem, a python one, or one this implementation does not know", async () => {
  await refusal('mount = "package"\nakmon_version = "1"\n', 'ecosystem = "python"');
  await refusal('mount = "package"\necosystem = "python"\n', 'ecosystem = "python"');
  await refusal('mount = "package"\necosystem = "ruby"\n', 'ecosystem = "ruby"');
  await refusal('mount = "package"\necosystem = ""\n', 'ecosystem = "python"');
});

test("the refusal is the same text on both implementations' shape: verify.json's key, sync.json's {{found}}", () => {
  assert.equal(
    data.unsupported_record.replace("akmon verify:", "akmon sync:"),
    syncData.sync.unsupported_record.replace("{{found}}", "{{found}}"),
  );
});

// -- the arguments -----------------------------------------------------------------------------

test("-h prints the usage, exit 0; an unknown flag is one usage line on stderr, exit 2", async () => {
  const help = await run(["--help"]);
  assert.equal(help.code, 0);
  assert.match(help.stdout, /^usage: akmon verify \[-h\] \[--project-root PROJECT_ROOT\] \[--strict\] \[--quiet\]\n/);
  assert.equal(help.stderr, "");
  assert.deepEqual(await run(["--bogus"]), {
    code: 2,
    stdout: "",
    stderr: "akmon verify: error: Unknown option '--bogus'\n",
  });
  assert.deepEqual(await run(["extra"]), {
    code: 2,
    stdout: "",
    stderr: "akmon verify: error: Unexpected argument 'extra'. This command does not take positional arguments\n",
  });
});

// -- a whole run -------------------------------------------------------------------------------

test("a synced Node project is healthy: every finding ok, exit 0 even under --strict, --quiet prints nothing", async () => {
  await withScratch(async (scratch) => {
    const root = project(scratch);
    await withoutAitnaRoot(async () => {
      syncWrite(root);
      const empty = posix.join(scratch, "empty-path");
      fs.mkdirSync(empty);
      await withPath(empty, async () => {
        const result = await run(["--project-root", root]);
        assert.equal(result.stderr, "");
        assert.equal(result.code, 0, result.stdout);
        const lines = result.stdout.trimEnd().split("\n");
        assert.ok(
          lines.every((line) => line.startsWith("OK ")),
          result.stdout,
        );
        const codes = lines.map((line) => line.split(" ")[1].replace(/:$/, ""));
        for (const code of [
          "hooks.launcher",
          "package.dev-pin",
          "layout.standard-path",
          "changelog.package-mode",
          "codex.host-trust",
          "pointers.generated-freshness",
          "attach.record",
          "attach.realign",
          "ci.akmon-checks",
        ]) {
          assert.ok(codes.includes(code), code);
        }
        // the mounted-only checks have no Node twin
        assert.ok(!codes.includes("gitignore.akmon-pycache") && !codes.includes("changelog.unreleased"));
        const strict = await run(["--project-root", root, "--strict", "--quiet"]);
        assert.deepEqual(strict, { code: 0, stdout: "", stderr: "" });
      });
    });
  });
});

/**
 * Run `body` with `AITNA_ROOT` set to `value`, then restored: the entry point reads it to warn
 * that it is ignored, and nothing else does.
 * @template T
 * @param {string} value
 * @param {() => Promise<T>} body
 * @returns {Promise<T>}
 */
async function withAitnaRootSet(value, body) {
  const saved = process.env.AITNA_ROOT;
  process.env.AITNA_ROOT = value;
  try {
    return await body();
  } finally {
    if (saved === undefined) {
      delete process.env.AITNA_ROOT;
    } else {
      process.env.AITNA_ROOT = saved;
    }
  }
}

test("environment.aitna-root-ignored: a Verifier warns while it is handed the retired variable, and not otherwise", async () => {
  await withScratch(async (scratch) => {
    const root = project(scratch);
    const empty = posix.join(scratch, "empty-path");
    fs.mkdirSync(empty);
    await withPath(empty, async () => {
      const unset = new Verifier(root);
      await unset.run();
      assert.deepEqual(of(unset, "environment.aitna-root-ignored"), []);
      const set = new Verifier(root, { aitnaRootEnv: "tools/ai" });
      await set.run();
      const [warning, ...rest] = of(set, "environment.aitna-root-ignored");
      assert.deepEqual(rest, []);
      assert.equal(warning[0], "warn");
      assert.equal(warning[1], "AITNA_ROOT");
      assert.equal(
        warning[2],
        "the AITNA_ROOT environment variable is set (tools/ai) and akmon no longer reads it: the dev layer is _aitna, " +
          "as the project root's .aitna-root declares it (an absent file means _aitna)",
      );
      assert.match(
        String(warning[3]),
        /^Unset AITNA_ROOT; to relocate the dev layer, commit its project-root-relative path/,
      );
    });
  });
});

test("environment.aitna-root-ignored: main warns while AITNA_ROOT is set, absent when unset, and --strict fails it", async () => {
  await withScratch(async (scratch) => {
    const root = project(scratch);
    syncWrite(root);
    const empty = posix.join(scratch, "empty-path");
    fs.mkdirSync(empty);
    await withPath(empty, async () => {
      await withoutAitnaRoot(async () => {
        const clean = await run(["--project-root", root]);
        assert.equal(clean.code, 0, clean.stdout);
        assert.ok(!clean.stdout.includes("environment.aitna-root-ignored"));
        assert.equal((await run(["--project-root", root, "--strict", "--quiet"])).code, 0);
      });
      await withAitnaRootSet("tools/ai", async () => {
        const warned = await run(["--project-root", root]);
        assert.equal(warned.code, 0, "a warning fails nothing without --strict");
        assert.match(
          warned.stdout,
          /^WARN environment\.aitna-root-ignored AITNA_ROOT: the AITNA_ROOT environment variable is set \(tools\/ai\)/m,
        );
        const strict = await run(["--project-root", root, "--strict", "--quiet"]);
        assert.equal(strict.code, 1, "the warning is not strict-exempt");
        assert.match(strict.stdout, /^WARN environment\.aitna-root-ignored /m);
      });
    });
  });
});

test("a role-named charter directory warns and never fails --strict; another warning still does", async () => {
  await withScratch(async (scratch) => {
    const root = project(scratch);
    await withoutAitnaRoot(async () => {
      syncWrite(root);
      put(root, "_aitna/agents/engineer/README.md", "# engineer\nsee akmon/roles/engineer.md\n");
      const empty = posix.join(scratch, "empty-path");
      fs.mkdirSync(empty);
      await withPath(empty, async () => {
        assert.equal((await run(["--project-root", root, "--quiet"])).code, 0);
        const strict = await run(["--project-root", root, "--quiet", "--strict"]);
        assert.equal(strict.code, 0, strict.stdout);
        assert.match(strict.stdout, /^WARN charters\.legacy-role-dir _aitna\/agents\/engineer: /m);
        put(root, ".gitignore", "node_modules\n");
        assert.equal((await run(["--project-root", root, "--quiet", "--strict"])).code, 1);
      });
    });
  });
});

test("an unsynced project fails with the stale files named, exit 1; a warning fails only under --strict", async () => {
  await withScratch(async (scratch) => {
    const root = project(scratch);
    await withoutAitnaRoot(async () => {
      const empty = posix.join(scratch, "empty-path");
      fs.mkdirSync(empty);
      await withPath(empty, async () => {
        const stale = await run(["--project-root", root, "--quiet"]);
        assert.equal(stale.code, 1);
        assert.match(
          stale.stdout,
          /^ERROR pointers\.generated-freshness: generated pointers are stale or missing: CLAUDE\.md, /m,
        );
        syncWrite(root);
        put(root, ".gitignore", "node_modules\n");
        assert.deepEqual((await run(["--project-root", root, "--quiet"])).code, 0);
        const strict = await run(["--project-root", root, "--quiet", "--strict"]);
        assert.equal(strict.code, 1);
        assert.match(strict.stdout, /^WARN gitignore\.env-secrets \.gitignore: /m);
      });
    });
  });
});

test("a missing node_modules/akmon is reported once per kind: launcher and the pin line, not a crash", async () => {
  await withScratch(async (scratch) => {
    const root = project(scratch, { link: false });
    await withoutAitnaRoot(async () => {
      const empty = posix.join(scratch, "empty-path");
      fs.mkdirSync(empty);
      await withPath(empty, async () => {
        const result = await run(["--project-root", root, "--quiet"]);
        assert.equal(result.code, 1);
        assert.match(result.stdout, /^ERROR hooks\.launcher node_modules\/akmon\/js\/hooks: /m);
      });
    });
  });
});

// -- codex.host-trust --------------------------------------------------------------------------

/**
 * A project synced for the live query, with a `codex` on PATH that the runner replaces.
 * @param {string} scratch
 * @returns {{root: string, bin: string, expected: Array<[string, string | null, string]>}}
 */
function codexProject(scratch) {
  const root = project(scratch);
  syncWrite(root);
  const bin = posix.join(scratch, "bin");
  put(bin, "codex", "#!/bin/sh\nexit 0\n");
  fs.chmodSync(posix.join(bin, "codex"), 0o755);
  const codexData = codexHooks.readCodexHooksData();
  const expected = codexHooks.expectedCodexHooks(
    codexData,
    JSON.parse(fs.readFileSync(posix.join(root, ".codex", "hooks.json"), "utf-8")),
  );
  return { root, bin, expected };
}

/**
 * A `hooks/list` answer for `root` holding `hooks`.
 * @param {string} root
 * @param {object[]} hooks
 */
function answer(root, hooks) {
  return JSON.stringify({ id: 2, result: { data: [{ cwd: root, hooks, warnings: [], errors: [] }] } });
}

/**
 * The hooks `expected` stands for, trusted unless `trust` says otherwise.
 * @param {Array<[string, string | null, string]>} expected
 * @param {string} [trust]
 */
function listed(expected, trust = "trusted") {
  return expected.map(([eventName, matcher, command]) => ({
    handlerType: "command",
    enabled: true,
    trustStatus: trust,
    eventName,
    matcher,
    command,
  }));
}

test("codex.host-trust: the injected runner is the whole host — trusted entries are ok, with the runner called once", async () => {
  await withScratch(async (scratch) => {
    const { root, bin, expected } = codexProject(scratch);
    await withoutAitnaRoot(() =>
      withPath(bin, async () => {
        /** @type {Array<[readonly string[], string, number]>} */
        const calls = [];
        const result = await run(["--project-root", root], {
          codexHooksRunner: (command, cwd, timeout) => (
            calls.push([command, cwd, timeout]),
            answer(root, listed(expected))
          ),
        });
        assert.equal(calls.length, 1);
        assert.deepEqual(calls[0][1], root);
        assert.equal(calls[0][0][0], "codex");
        assert.match(
          result.stdout,
          /^OK codex\.host-trust \.codex\/hooks\.json: every generated Codex hook entry is discovered, enabled, and trusted → /m,
        );
      }),
    );
  });
});

test("codex.host-trust: untrusted entries are a warning with the problems counted and sorted, a strict failure", async () => {
  await withScratch(async (scratch) => {
    const { root, bin, expected } = codexProject(scratch);
    await withoutAitnaRoot(() =>
      withPath(bin, async () => {
        const hooks = listed(expected);
        hooks[0].trustStatus = "untrusted";
        hooks[1].trustStatus = "modified";
        const result = await run(["--project-root", root, "--strict", "--quiet"], {
          codexHooksRunner: () => answer(root, hooks),
        });
        assert.match(
          result.stdout,
          /^WARN codex\.host-trust \.codex\/hooks\.json: Codex hook delivery is incomplete: modified \(1\); untrusted \(1\) → Open `\/hooks` in Codex/m,
        );
        assert.equal(result.code, 1);
      }),
    );
  });
});

test("codex.host-trust: a protocol failure is a warning that names the kind, never the vendor's text", async () => {
  await withScratch(async (scratch) => {
    const { root, bin } = codexProject(scratch);
    await withoutAitnaRoot(() =>
      withPath(bin, async () => {
        const result = await run(["--project-root", root, "--quiet"], { codexHooksRunner: () => "not json at all" });
        assert.match(
          result.stdout,
          /^WARN codex\.host-trust codex app-server hooks\/list: codex app-server hooks\/list could not be inspected: hooks\/list response is not valid JSON → Run `codex app-server` manually/m,
        );
        const thrown = await run(["--project-root", root, "--quiet"], {
          codexHooksRunner: () => {
            throw new Error("SECRET vendor text");
          },
        });
        assert.ok(!thrown.stdout.includes("SECRET"));
        assert.match(thrown.stdout, /the hooks\/list runner failed/);
      }),
    );
  });
});

test("codex.host-trust: no codex on PATH is the neutral ok, and the runner is never called", async () => {
  await withScratch(async (scratch) => {
    const { root } = codexProject(scratch);
    const empty = posix.join(scratch, "empty-path");
    fs.mkdirSync(empty);
    await withoutAitnaRoot(() =>
      withPath(empty, async () => {
        const result = await run(["--project-root", root], {
          codexHooksRunner: () => {
            throw new Error("called");
          },
        });
        assert.match(
          result.stdout,
          /^OK codex\.host-trust \.codex\/hooks\.json: codex is not installed; Codex host-trust delivery is not verified → /m,
        );
      }),
    );
  });
});

test("codex.host-trust: a codex that is a directory, or not executable, is not installed", async () => {
  await withScratch(async (scratch) => {
    const { root } = codexProject(scratch);
    const dir = posix.join(scratch, "dirbin");
    fs.mkdirSync(posix.join(dir, "codex"), { recursive: true });
    const plain = posix.join(scratch, "plainbin");
    put(plain, "codex", "x");
    fs.chmodSync(posix.join(plain, "codex"), 0o644);
    await withoutAitnaRoot(async () => {
      for (const path of [dir, plain, `${dir}:${plain}`]) {
        await withPath(path, async () => {
          const result = await run(["--project-root", root]);
          assert.match(result.stdout, /codex is not installed/, path);
        });
      }
    });
  });
});

test("codex.host-trust: the first PATH entry holding an executable codex wins, an empty entry is the working directory", async () => {
  await withScratch(async (scratch) => {
    const { root, bin, expected } = codexProject(scratch);
    const decoy = posix.join(scratch, "decoy");
    fs.mkdirSync(decoy);
    await withoutAitnaRoot(() =>
      withPath(`${decoy}:${bin}`, async () => {
        const result = await run(["--project-root", root], { codexHooksRunner: () => answer(root, listed(expected)) });
        assert.match(result.stdout, /every generated Codex hook entry is discovered/);
      }),
    );
  });
});

test("codex.host-trust: stale or invalid wiring stops the check before any host call", async () => {
  await withScratch(async (scratch) => {
    const { root, bin } = codexProject(scratch);
    await withoutAitnaRoot(() =>
      withPath(bin, async () => {
        const runner = () => {
          throw new Error("must not be called");
        };
        for (const text of ["{nope", "[]", `${codexHooksText(syncData, root)} `, ""]) {
          put(root, ".codex/hooks.json", text);
          const result = await run(["--project-root", root, "--quiet"], { codexHooksRunner: runner });
          assert.ok(!result.stdout.includes("codex.host-trust"), JSON.stringify(text));
        }
        // bytes that are not UTF-8: the plan itself cannot read the file (a crash in both implementations),
        // the host-trust check alone treats it as unusable wiring
        put(root, ".codex/hooks.json", Buffer.from([0xff, 0xfe]));
        const verifier = new Verifier(root, { codexHooksRunner: runner });
        await verifier.checkCodexHostTrust();
        assert.deepEqual(verifier.findings, []);
        fs.rmSync(posix.join(root, ".codex", "hooks.json"));
        assert.ok(
          !(await run(["--project-root", root, "--quiet"], { codexHooksRunner: runner })).stdout.includes(
            "codex.host-trust",
          ),
        );
      }),
    );
  });
});

// -- the text patterns: Unicode, as the Python's str patterns are ------------------------------

/**
 * The findings one check method records on `root`.
 * @param {string} root
 * @param {(verifier: Verifier) => void} check
 */
function recorded(root, check) {
  const verifier = new Verifier(root);
  check(verifier);
  return verifier.findings.map((f) => `${f.severity} ${f.code} ${f.message}`);
}

test("delegation-default and the legacy owner anchor accept ASCII whitespace only, in any case", async () => {
  for (const [text, ok] of /** @type {Array<[string, boolean]>} */ ([
    ["Delegation is the default", true],
    ["DELEGATION\u00a0IS\u2003THE\u3000DEFAULT", false],
    ["delegation\nis\tthe\u2028default", false],
    ["DELEGATION\nIS\tTHE\fDEFAULT", true],
    ["delegation is the defaulty", false],
    ["xdelegation is the default", false],
    ["_delegation is the default", false],
    ["7delegation is the default", false],
    ["édelegation is the default", true],
    ["delegation\u200bis the default", false],
    ["delegation is the default_", false],
    ["delegation is the default\u0662", true],
  ])) {
    await withScratch((scratch) => {
      const root = project(scratch);
      put(root, "AGENTS.md", AGENTS.replace("**Delegation is the default.**", text));
      const messages = recorded(root, (v) => v.checkAgentsMd());
      assert.equal(messages[0].startsWith("ok"), ok, JSON.stringify(text));
    });
  }
  // the legacy owner anchor stands in for "owner verifies" when only the whitespace between the words differs
  for (const [anchor, ok] of /** @type {Array<[string, boolean]>} */ ([
    ["**D2** \u2014 the owner\tverifies", true],
    ["**D2** \u2014 the owner\u00a0verifies", false],
    ["**D2**\u00a0\u2014\u3000the owner\u2003verifies", false],
    ["**D2**\u2014 the owner\u00a0verifies", false],
    ["**D2** \u2014 the owner\u200bverifies", false],
    ["the owner\u00a0verifies", false],
    ["**D2** - the owner\u00a0verifies", false],
  ])) {
    await withScratch((scratch) => {
      const root = project(scratch);
      put(root, "AGENTS.md", AGENTS.replace("The owner verifies", anchor));
      const messages = recorded(root, (v) => v.checkAgentsMd());
      assert.equal(messages[0].startsWith("ok"), ok, anchor);
    });
  }
});

test("the dates of TASKS.md are found with ASCII digits and an ASCII word boundary", async () => {
  for (const [text, found] of [
    ["Started 2026-10-11.", true],
    ["x2026-10-11", false],
    ["2026-10-110", false],
    ["_2026-10-11_", false],
    ["2026-10-11x", false],
    ["\u0662\u0660\u0662\u0666-\u0661\u0660-\u0661\u0661", false],
    ["\uff12\uff10\uff12\uff16-\uff11\uff10-\uff11\uff11", false],
    ["é2026-10-11", true],
    ["\u00b22026-10-11", true],
    ["\u03012026-10-11", true],
    ["\u21602026-10-11", true],
    ["2026-10-11é", true],
    ["a 2026-1-11", false],
    ["(2026-10-11)", true],
    ["\u{1d7ec}2026-10-11", true],
  ]) {
    await withScratch((scratch) => {
      const root = project(scratch);
      put(root, "_aitna/TASKS.md", `# Tasks\n\n${text}\n`);
      const messages = recorded(root, (v) => v.checkTasks());
      assert.equal(
        messages.some((m) => m.startsWith("warn tasks.dates")),
        found,
        JSON.stringify(text),
      );
    });
  }
});

// -- tasks, skills, memory, charters: the parsers ----------------------------------------------

test("entryId and entryStatus read the field, not the line, as the Python does", () => {
  assert.equal(Verifier.entryId("- **T1** · a · done"), "T1");
  assert.equal(Verifier.entryId("- ** · a"), "?");
  assert.equal(Verifier.entryId("T9 · a"), "T9");
  assert.equal(Verifier.entryStatus("- T1 · a · blocked (after C51) · x"), "blocked");
  assert.equal(Verifier.entryStatus("- T1 · a · **active** · x"), "active");
  assert.equal(Verifier.entryStatus("- T1 · a · Active, · x"), "active");
  assert.equal(Verifier.entryStatus("- T1 · a · \u00a0DONE: yes\u3000 · x"), "done");
  assert.equal(Verifier.entryStatus("- T1 · a · \u0130x · x"), "i\u0307x");
  assert.equal(Verifier.entryStatus("- T1 · a"), null);
  assert.equal(Verifier.entryStatus("- T1 · a ·  · x"), null);
  assert.equal(Verifier.entryStatus("- T1 · a · *** · x"), null);
});

test("TASKS.md: statuses, done entries, length and dates are reported with the Python's texts", async () => {
  await withScratch((scratch) => {
    const root = project(scratch);
    const lines = [
      "# Tasks",
      "- T1 · a · done · x",
      "- T2 · b · nope · y",
      "- T3 · b · nope · y",
      "- T4 · b · nope · y",
      "- T5 · b · nope · y",
      "- T6 · b · nope · y",
    ];
    put(root, "_aitna/TASKS.md", `${lines.join("\n")}\n${"- padding · p · active · g\n".repeat(200)}`);
    const messages = recorded(root, (v) => v.checkTasks());
    assert.deepEqual(messages, [
      "warn tasks.index-length _aitna/TASKS.md is 207 lines; keep it an index (pipelines/tasks.md) — detail by reference, not inlined",
      "warn tasks.entry-status 5 TASKS.md entry(ies) carry a status outside active | blocked | deferred | done: T2, T3, T4, T5, +1 more",
      "warn tasks.done-archived TASKS.md has 'done' entries; move them to TASKS_ARCHIVE.md: T1",
    ]);
  });
});

/**
 * The messages of `checkSkillContract` for a SKILL.md with `text` in a directory named `directory`.
 * @param {string} text
 * @param {string} [directory]
 */
async function skillMessages(text, directory = "demo") {
  /** @type {string[]} */
  let messages = [];
  await withScratch((scratch) => {
    const root = project(scratch);
    put(root, `skills/${directory}/SKILL.md`, text);
    const verifier = new Verifier(root);
    verifier.checkSkillContract(posix.join(root, "skills", directory, "SKILL.md"));
    messages = verifier.findings.map((f) => `${f.code}: ${f.message.replace(root, "")}`);
  });
  return messages;
}

test("skill frontmatter: the shapes the Python reads line by line", async () => {
  const good = "---\nname: demo\ndescription: Shows it.\nmetadata:\n  owner: akmon\n---\nbody\n";
  assert.deepEqual(await skillMessages(good), []);
  assert.deepEqual(await skillMessages("# no frontmatter\n"), [
    "skills.frontmatter: skills/demo/SKILL.md is missing required frontmatter",
  ]);
  assert.deepEqual(await skillMessages(""), [
    "skills.frontmatter: skills/demo/SKILL.md is missing required frontmatter",
  ]);
  assert.deepEqual(await skillMessages("---\nname: demo\n"), [
    "skills.frontmatter-close: skills/demo/SKILL.md frontmatter is not closed with ---",
  ]);
  assert.deepEqual(await skillMessages("---\nname: demo\nbroken\n---\n"), [
    "skills.frontmatter-syntax: skills/demo/SKILL.md frontmatter line is not key: value: 'broken'",
    "skills.required-fields: skills/demo/SKILL.md frontmatter is missing: description, metadata.owner",
  ]);
  assert.deepEqual(await skillMessages(good.replaceAll("\n", "\r\n")), []);
  assert.deepEqual(
    await skillMessages(good.replaceAll("\n", "\u2028")),
    ["skills.frontmatter-close: skills/demo/SKILL.md frontmatter is not closed with ---"].slice(0, 0),
  );
  assert.deepEqual(await skillMessages(`  ---  \n${good.slice(4)}`), []);
  assert.deepEqual(
    await skillMessages(good.replace("name: demo", "name:")),
    ["skills.required-fields: skills/demo/SKILL.md frontmatter is missing: "]
      .slice(0, 0)
      .concat(["skills.field-values: skills/demo/SKILL.md frontmatter has empty value(s): name"]),
  );
});

test("skill frontmatter: name, length and YAML checks", async () => {
  const frame = (/** @type {string} */ name, /** @type {string} */ description) =>
    `---\nname: ${name}\ndescription: ${description}\nmetadata:\n  owner: a\n---\n`;
  assert.deepEqual(await skillMessages(frame("other", "d")), [
    "skills.name-matches-dir: skills/demo/SKILL.md frontmatter name must match its skill directory (demo)",
  ]);
  assert.deepEqual(await skillMessages(frame("Demo", "d"), "Demo"), [
    "skills.name-format: skills/Demo/SKILL.md frontmatter name 'Demo' is not 1-64 lowercase letters, digits and single inner hyphens",
  ]);
  for (const name of ["a--b", "a-", "-a", "a_b", "é"]) {
    const messages = await skillMessages(frame(name, "d"), name);
    assert.ok(
      messages.some((m) => m.startsWith("skills.name-format")),
      name,
    );
  }
  const long = "a".repeat(65);
  assert.ok((await skillMessages(frame(long, "d"), long)).some((m) => m.startsWith("skills.name-format")));
  assert.deepEqual(await skillMessages(frame("demo", "x".repeat(1024))), []);
  assert.deepEqual(await skillMessages(frame("demo", "x".repeat(1025))), [
    "skills.description-length: skills/demo/SKILL.md description is 1025 characters; the limit is 1024",
  ]);
  // code points, not UTF-16 units
  assert.deepEqual(await skillMessages(frame("demo", "\u{1d7ec}".repeat(1024))), []);
  assert.deepEqual(await skillMessages(frame("demo", "\u{1d7ec}".repeat(1025))), [
    "skills.description-length: skills/demo/SKILL.md description is 1025 characters; the limit is 1024",
  ]);
  assert.deepEqual(await skillMessages(frame("demo", "use # that")), [
    "skills.frontmatter-yaml: skills/demo/SKILL.md frontmatter description: an unquoted ' #' starts a YAML comment, and Claude Code and Codex cut the value there",
  ]);
  assert.deepEqual(await skillMessages(frame("demo", "#x")), [
    "skills.frontmatter-yaml: skills/demo/SKILL.md frontmatter description: an unquoted ' #' starts a YAML comment, and Claude Code and Codex cut the value there",
  ]);
  assert.deepEqual(await skillMessages(frame("demo", "use: that")), [
    "skills.frontmatter-yaml: skills/demo/SKILL.md frontmatter description: an unquoted ': ' is not valid YAML, and the Agent Skills validator rejects it",
  ]);
  assert.deepEqual(await skillMessages(frame("demo", '"use: that # x"')), []);
  assert.deepEqual(await skillMessages(frame("demo", "'use: that'")), []);
});

test("memory index: README.md, the legacy MEMORY.md, a missing index, and the unindexed files in code point order", async () => {
  await withScratch((scratch) => {
    const root = project(scratch);
    put(root, "_aitna/memory/z.md", "z");
    put(root, "_aitna/memory/B.md", "b");
    put(root, "_aitna/memory/é.md", "e");
    put(root, "_aitna/memory/x.md/inner", "dir named like a file");
    assert.deepEqual(
      recorded(root, (v) => v.checkMemory()),
      [
        "ok memory.index _aitna/memory/README.md exists",
        "warn memory.index-coverage memory files not mentioned in index: B.md, x.md, z.md, é.md",
      ],
    );
    fs.rmSync(posix.join(root, "_aitna", "memory", "README.md"));
    assert.deepEqual(recorded(root, (v) => v.checkMemory()).slice(0, 1), [
      "error memory.index _aitna/memory needs README.md index",
    ]);
    put(root, "_aitna/memory/MEMORY.md", "# old: note.md B.md x.md z.md é.md\n");
    assert.deepEqual(
      recorded(root, (v) => v.checkMemory()),
      [
        "warn memory.index _aitna/memory/MEMORY.md exists; README.md is the preferred index",
        "ok memory.index-coverage memory index mentions all memory markdown files",
      ],
    );
  });
});

test("charters: agent directories in code point order, a link to a directory counts, a plain file does not", async () => {
  await withScratch((scratch) => {
    const root = project(scratch);
    put(root, "_aitna/agents/b/README.md", "# b\nsee akmon/roles/x\n");
    put(root, "_aitna/agents/B/README.md", "# B\nno link\n");
    put(root, "_aitna/agents/c/notes.md", "n");
    put(root, "_aitna/agents/file.md", "not an agent");
    fs.symlinkSync(posix.join(root, "_aitna", "agents", "e"), posix.join(root, "_aitna", "agents", "d"));
    assert.deepEqual(
      recorded(root, (v) => v.checkAgentCharters()),
      [
        "warn charters.role-link _aitna/agents/B/README.md does not link a akmon role",
        "ok charters.role-link _aitna/agents/b/README.md links a akmon role",
        "error charters.readme _aitna/agents/c/README.md is missing",
        "ok charters.role-link _aitna/agents/d/README.md links a akmon role",
        "ok charters.role-link _aitna/agents/e/README.md links a akmon role",
      ],
    );
  });
});

test("charters: a role-named directory still verifies, with the legacy warning; release and development do not warn", async () => {
  await withScratch((scratch) => {
    const root = project(scratch);
    put(root, "_aitna/agents/development/README.md", "# development\nsee akmon/roles/review.md\n");
    put(root, "_aitna/agents/engineer/README.md", "# engineer\nsee akmon/roles/engineer.md\n");
    put(root, "_aitna/agents/review/notes.md", "n");
    put(root, "_aitna/agents/release/README.md", "# release\nsee akmon/agents/release.md\n");
    put(root, "_aitna/agents/learn/README.md", "# learn\nsee akmon/agents/learning.md\n");
    put(root, "_aitna/agents/learning/README.md", "# learning\nsee akmon/agents/learning.md\n");
    const findings = recorded(root, (v) => v.checkAgentCharters());
    // a learn/ directory is legacy and names the learning agent as its successor
    const learn = new Verifier(root);
    learn.checkAgentCharters();
    const legacy = learn.findings.find((finding) => finding.target === "_aitna/agents/learn");
    assert.match(
      String(legacy?.fix),
      /^Move its content into _aitna\/agents\/learning\/README\.md; a charter is one directory/,
    );
    assert.deepEqual(findings, [
      "ok charters.role-link _aitna/agents/development/README.md links a akmon role",
      "ok charters.role-link _aitna/agents/e/README.md links a akmon role", // the helper's own charter
      "warn charters.legacy-role-dir _aitna/agents/engineer is named for a role, not an agent",
      "ok charters.role-link _aitna/agents/engineer/README.md links a akmon role",
      "warn charters.legacy-role-dir _aitna/agents/learn is named for a role, not an agent",
      "ok charters.role-link _aitna/agents/learn/README.md links a akmon role",
      "ok charters.role-link _aitna/agents/learning/README.md links a akmon role",
      "ok charters.role-link _aitna/agents/release/README.md links a akmon role",
      "warn charters.legacy-role-dir _aitna/agents/review is named for a role, not an agent",
      "error charters.readme _aitna/agents/review/README.md is missing",
    ]);
  });
});

test("charters: a link to a role or agent definition the standard tree lacks warns once per target", async () => {
  await withScratch((scratch) => {
    const root = project(scratch);
    put(
      root,
      "_aitna/agents/development/README.md",
      "Roles `_aitna/akmon/roles/review.md`, `_aitna/akmon/roles/nope.md` and `_aitna/akmon/roles/nope.md` again; agent [x](../akmon/agents/ghost.md).\n",
    );
    const verifier = new Verifier(root);
    verifier.checkAgentCharters();
    const missing = verifier.findings.filter((finding) => finding.code === "charters.role-link-target");
    assert.deepEqual(
      missing.map((finding) => [finding.severity, finding.target, finding.message]),
      [
        [
          "warn",
          "_aitna/agents/development/README.md",
          "_aitna/agents/development/README.md links _aitna/akmon/roles/nope.md, which is not in the standard tree",
        ],
        [
          "warn",
          "_aitna/agents/development/README.md",
          "_aitna/agents/development/README.md links _aitna/akmon/agents/ghost.md, which is not in the standard tree",
        ],
      ],
    );
    assert.equal(missing[0].fix, "Link a role definition that exists under _aitna/akmon/roles/.");
    assert.deepEqual(
      verifier.findings.filter((finding) => finding.severity === "ok" && finding.target.includes("development")).length,
      1,
    );
  });
});

test("charters: link targets are not resolved for a legacy role directory", async () => {
  await withScratch((scratch) => {
    const root = project(scratch);
    put(root, "_aitna/agents/learn/README.md", "See `_aitna/akmon/roles/learn.md`.\n");
    const verifier = new Verifier(root);
    verifier.checkAgentCharters();
    assert.equal(verifier.findings.filter((finding) => finding.code === "charters.role-link-target").length, 0);
  });
});

// -- the isolation scan: the glob and the patterns ---------------------------------------------

test("isolation: roles/*.md, skills/**/*.md, tools/**/*.md and the top-level files are scanned; a linked directory is not entered", async () => {
  await withScratch((scratch) => {
    const root = project(scratch);
    const tree = posix.join(scratch, "tree");
    put(tree, "roles/a.md", "see ADR 0012 here\n");
    put(tree, "roles/sub/ignored.md", "ADR 0099\n");
    put(tree, "pipelines/p.md", "[x](meta/design.md) and `decisions/0001.md`\n");
    put(tree, "guardrails/.hidden.md", "run self_ci now\n");
    put(tree, "skills/s/SKILL.md", "ROADMAP O3 and ROADMAP.md\n");
    put(tree, "skills/s/deep/er/more.md", "CONCEPT.md\n");
    put(tree, "skills/top.md", "ADR-12\n");
    put(tree, "tools/t/u/v.md", "`ROADMAP/x` ok\n");
    put(tree, "profiles/none.txt", "ADR 0001\n");
    put(tree, "ARCHETYPES.md", "plain ADR vocabulary: file an ADR\n");
    put(tree, "MODEL.md", "ADR 0005\n");
    put(scratch, "outside/in-link.md", "ADR 0042\n");
    fs.symlinkSync(posix.join(scratch, "outside"), posix.join(tree, "skills", "linked"));
    const verifier = new Verifier(root);
    verifier.standardRoot = tree;
    verifier.checkUseSurfaceIsolation();
    const [[severity, , message]] = of(verifier, "isolation.use-surface");
    assert.equal(severity, "error");
    const parts = message.slice(message.indexOf("): ") + 3).split("; ");
    // `sorted(set(sources))`: by path components, by code point — MODEL.md before guardrails/
    assert.deepEqual(parts, [
      "standard tree:MODEL.md → cites ADR 0005",
      "standard tree:guardrails/.hidden.md → names self_ci",
      "standard tree:pipelines/p.md → path meta/design.md",
      "standard tree:pipelines/p.md → path decisions/0001.md",
      "standard tree:roles/a.md → cites ADR 0012",
      "standard tree:skills/s/SKILL.md → cites ROADMAP O3",
      "standard tree:skills/s/SKILL.md → cites ROADMAP.md",
      "standard tree:skills/s/deep/er/more.md → names CONCEPT.md",
      "standard tree:skills/top.md → cites ADR-12",
      "standard tree:tools/t/u/v.md → path ROADMAP/x",
    ]);
  });
});

test("isolation: a closed code fence does not shift the inline-code pairing (C158)", async () => {
  await withScratch((scratch) => {
    const root = project(scratch);
    const tree = posix.join(scratch, "tree");
    put(
      tree,
      "roles/a.md",
      "# architect\n\nThe gate runs:\n\n```bash\nakmon verify\n```\n\nIt reads `meta/reviews/x.md` first.\n",
    );
    const verifier = new Verifier(root);
    verifier.standardRoot = tree;
    verifier.checkUseSurfaceIsolation();
    const [[severity, , message]] = of(verifier, "isolation.use-surface");
    assert.equal(severity, "error");
    const parts = message.slice(message.indexOf("): ") + 3).split("; ");
    assert.deepEqual(parts, ["standard tree:roles/a.md → path meta/reviews/x.md"]);
  });
});

test("isolation: a clean tree is ok, and a standard tree that is not a directory is silent", async () => {
  await withScratch((scratch) => {
    const root = project(scratch);
    const tree = posix.join(scratch, "tree");
    put(tree, "roles/a.md", "file an ADR; ADR without number; ADR 1; ROADMAP is generic; roadmap O1\n");
    const verifier = new Verifier(root);
    verifier.standardRoot = tree;
    verifier.checkUseSurfaceIsolation();
    assert.deepEqual(
      of(verifier, "isolation.use-surface").map((f) => f[0]),
      ["ok"],
    );
    const none = new Verifier(root);
    none.standardRoot = posix.join(scratch, "absent");
    none.checkUseSurfaceIsolation();
    assert.deepEqual(none.findings, []);
  });
});

// -- model routing: the overlay and the registry shapes ----------------------------------------

test("routing overlay: invalid JSON and a non-object are parse errors; retired keys are named per block", async () => {
  await withScratch((scratch) => {
    const root = project(scratch);
    put(root, "_aitna/model-routing.json", "{nope");
    const bad = recorded(root, (v) => v.checkModelRouting()).filter((m) => m.includes("overlay"));
    assert.equal(bad.length, 1);
    assert.match(bad[0], /^error routing\.overlay-parse .*model-routing\.json: invalid JSON: /);
    put(root, "_aitna/model-routing.json", "[]");
    assert.match(
      recorded(root, (v) => v.checkModelRouting()).join("\n"),
      /error routing\.overlay-parse .*: expected a JSON object/,
    );
    put(
      root,
      "_aitna/model-routing.json",
      JSON.stringify({
        second_opinion_policy: { diversity_ladder: ["other-vendor"], ladder: ["claude"] },
        anthropic: { second_opinion: { harness: "h" } },
        qwen: { second_opinion: {}, family: "qwen" },
        openai: { carrier: "codex" },
        extra: 1,
      }),
    );
    const messages = recorded(root, (v) => v.checkModelRouting());
    assert.ok(messages.includes("ok routing.overlay-parse model-routing project overlay parses"));
    assert.ok(
      messages.includes(
        "error routing.second-opinion project overlay second_opinion_policy carries the retired key(s) diversity_ladder",
      ),
    );
    assert.ok(
      messages.includes(
        "error routing.second-opinion project overlay anthropic carries the retired key(s) second_opinion",
      ),
    );
    assert.ok(
      messages.includes("error routing.second-opinion project overlay qwen carries the retired key(s) second_opinion"),
    );
    assert.ok(!messages.some((m) => m.includes("project overlay openai")));
    put(root, "_aitna/model-routing.json", JSON.stringify({ anthropic: 3, openai: { second_opinion_policy: "x" } }));
    assert.ok(!recorded(root, (v) => v.checkModelRouting()).some((m) => m.includes("retired")));
    // an integer beyond 2**53 is a valid document: verify reads it, it never writes it back (sync would refuse it)
    put(
      root,
      "_aitna/model-routing.json",
      '{"anthropic": {"n": 123456789012345678901234567890, "second_opinion": {"cli": 1}}}',
    );
    const big = recorded(root, (v) => v.checkModelRouting());
    assert.ok(big.includes("ok routing.overlay-parse model-routing project overlay parses"));
    assert.ok(
      big.includes("error routing.second-opinion project overlay anthropic carries the retired key(s) second_opinion"),
    );
  });
});

test("routing registry: the shipped one is ok; a broken policy, fallback and second_opinion are each named", async () => {
  await withScratch((scratch) => {
    const root = project(scratch);
    const tree = posix.join(scratch, "tree");
    const registry = (/** @type {object} */ body) =>
      put(tree, "tools/model_routing/registry.json", JSON.stringify(body));
    const vendor = {
      selection_policy: { reasoner: "orchestrator", worker: "lowest" },
      semantic_fallback: { worker: "w", mid: "m", reasoner: "r", orchestrator: "o" },
      carrier: "claude",
    };
    const providers = {
      claude: { operation: "review", model_flag: "--model {model}", family: "claude", report_dir: "d" },
      qwen: { operation: "review", model_flag: "-m {model}", family: null, report_dir: "q" },
    };
    const policy = { ladder: ["claude", "qwen:big"], families: { claude: "Claude", qwen: "Qwen" } };
    const withTable = (/** @type {object} */ vendors, /** @type {object} */ extra = {}) =>
      registry({ ...vendors, providers, second_opinion_policy: policy, ...extra });
    withTable({ anthropic: vendor, openai: vendor });
    const check = () => {
      const verifier = new Verifier(root);
      verifier.standardRoot = tree;
      verifier.checkModelRouting();
      return verifier.findings
        .map((f) => `${f.severity} ${f.code} ${f.target} ${f.message}`)
        .filter((m) => !m.includes("layout.standard-path"));
    };
    assert.ok(check().every((line) => line.startsWith("ok ")));
    withTable({
      anthropic: {
        selection_policy: { reasoner: "nope", worker: "lowest" },
        semantic_fallback: { worker: "w", mid: "", reasoner: "r", orchestrator: "o" },
        carrier: "nowhere",
      },
    });
    const lines = check();
    assert.ok(
      lines.includes(
        "error routing.selection-policy tools/model_routing/registry.json#anthropic model-routing anthropic needs semantic selection_policy with worker=lowest and reasoner orchestrator or highest",
      ),
    );
    assert.ok(
      lines.includes(
        "error routing.semantic-fallback tools/model_routing/registry.json#anthropic model-routing anthropic semantic_fallback must name worker/mid/reasoner/orchestrator",
      ),
    );
    assert.ok(
      lines.includes(
        "error routing.second-opinion tools/model_routing/registry.json#anthropic model-routing anthropic carrier must name a row of the providers table",
      ),
    );
    assert.ok(
      lines.includes(
        "error routing.vendor-present tools/model_routing/registry.json#openai model-routing registry is missing vendor 'openai'",
      ),
    );
    const withLadder = (/** @type {object} */ change) => {
      withTable({ anthropic: { ...vendor, ...change }, openai: vendor });
      return check();
    };
    assert.ok(
      withLadder({ harness_rungs: ["a", "b"], auditor_only_rungs: ["z"] }).includes(
        "ok routing.ladder tools/model_routing/registry.json#anthropic model-routing anthropic harness ladder is well-formed",
      ),
    );
    for (const [change, message] of /** @type {[object, string][]} */ ([
      [{ harness_rungs: [] }, "harness_rungs must be a non-empty list of unique non-empty strings"],
      [{ harness_rungs: ["a", "a"] }, "harness_rungs must be a non-empty list of unique non-empty strings"],
      [{ harness_rungs: ["a", ""] }, "harness_rungs must be a non-empty list of unique non-empty strings"],
      [{ harness_rungs: "a" }, "harness_rungs must be a non-empty list of unique non-empty strings"],
      [{ auditor_only_rungs: "z" }, "auditor_only_rungs must be a list of strings"],
      [{ auditor_only_rungs: [1] }, "auditor_only_rungs must be a list of strings"],
      [{ harness_rungs: ["a"], auditor_only_rungs: ["a"] }, "auditor_only_rungs must not repeat a harness_rungs alias"],
    ])) {
      assert.ok(
        withLadder(change).some(
          (line) =>
            line.startsWith("error routing.ladder tools/model_routing/registry.json#anthropic ") &&
            line.endsWith(`model-routing anthropic ${message}`),
        ),
        message,
      );
    }
    withTable({ anthropic: { ...vendor, carrier: 3 }, openai: [] });
    const shapes = check();
    assert.ok(
      shapes.includes(
        "error routing.second-opinion tools/model_routing/registry.json#anthropic model-routing anthropic carrier must name a row of the providers table",
      ),
    );
    assert.ok(shapes.some((l) => l.startsWith("error routing.vendor-present")));
    put(tree, "tools/model_routing/registry.json", "[1]");
    assert.match(
      check().join("\n"),
      /error routing\.registry-parse standard tree:tools\/model_routing\/registry\.json .*: expected a JSON object/,
    );
  });
});

test("routing providers table: a row missing a key, an undeclared ladder entry and an absent table are each named", async () => {
  await withScratch((scratch) => {
    const root = project(scratch);
    const tree = posix.join(scratch, "tree");
    const vendor = {
      selection_policy: { reasoner: "orchestrator", worker: "lowest" },
      semantic_fallback: { worker: "w", mid: "m", reasoner: "r", orchestrator: "o" },
      carrier: "claude",
    };
    const row = { operation: "review", model_flag: "--model {model}", family: "claude", report_dir: "d" };
    const check = (/** @type {object} */ body) => {
      put(tree, "tools/model_routing/registry.json", JSON.stringify({ anthropic: vendor, openai: vendor, ...body }));
      const verifier = new Verifier(root);
      verifier.standardRoot = tree;
      verifier.checkModelRouting();
      return verifier.findings
        .map((f) => `${f.severity} ${f.code} ${f.message}`)
        .filter((m) => m.includes("routing.second-opinion"));
    };
    assert.ok(
      check({ providers: { claude: row }, second_opinion_policy: { ladder: ["claude", "claude:opus"] } }).includes(
        "ok routing.second-opinion model-routing provider claude is configured",
      ),
    );
    const broken = check({
      providers: {
        claude: row,
        bare: { operation: "review", report_dir: "d" },
        text: "no",
        multi: { ...row, family: null },
      },
      second_opinion_policy: { ladder: ["claude", "ghost:big"] },
    });
    assert.ok(broken.includes("error routing.second-opinion model-routing provider bare missing: model_flag, family"));
    assert.ok(
      broken.includes(
        "error routing.second-opinion model-routing provider text missing: operation, model_flag, report_dir",
      ),
    );
    assert.ok(broken.includes("ok routing.second-opinion model-routing provider multi is configured"));
    assert.ok(
      broken.includes(
        "error routing.second-opinion model-routing second_opinion_policy.ladder must be a non-empty list of declared providers; undeclared: ghost:big",
      ),
    );
    assert.ok(
      check({ providers: { claude: row }, second_opinion_policy: { ladder: [] } }).includes(
        "error routing.second-opinion model-routing second_opinion_policy.ladder must be a non-empty list of declared providers",
      ),
    );
    assert.ok(check({}).includes("error routing.second-opinion model-routing registry has no providers table"));
  });
});

/**
 * The routing findings (severity, code, target, message) one project overlay produces on the shipped tree.
 * @param {string} root
 * @param {object} overlayBody
 * @returns {string[]}
 */
function overlayFindings(root, overlayBody) {
  put(root, "_aitna/model-routing.json", JSON.stringify(overlayBody));
  const verifier = new Verifier(root);
  verifier.checkModelRouting();
  return verifier.findings
    .filter((f) => f.code === "routing.second-opinion" && f.target.startsWith("_aitna/model-routing.json"))
    .map((f) => `${f.severity} ${f.target} ${f.message}`);
}

test("routing overlay: the merged ladder and each overlay-declared row are checked and quote the overlay file", async () => {
  await withScratch((scratch) => {
    const root = project(scratch);
    assert.deepEqual(overlayFindings(root, { second_opinion_policy: { ladder: ["claude", "ghost"] } }), [
      "error _aitna/model-routing.json#second_opinion_policy second_opinion_policy.ladder as merged with _aitna/model-routing.json must be a non-empty list of declared providers; undeclared: ghost",
    ]);
    assert.deepEqual(
      overlayFindings(root, {
        providers: { mine: { argv: ["mine", "-m", "{model}"], family: "qwen" } },
        second_opinion_policy: { ladder: ["mine:big", "claude"] },
      }),
      [
        "ok _aitna/model-routing.json#providers.mine project overlay _aitna/model-routing.json provider mine is configured",
        "ok _aitna/model-routing.json#second_opinion_policy second-opinion ladder as merged with _aitna/model-routing.json names only declared providers",
      ],
    );
    const bad = /** @type {Array<[object, string]>} */ ([
      [{ argv: ["mine"] }, "family key is missing (null for a multi-family carrier)"],
      [
        { argv: ["mine"], family: "mimo" },
        "family 'mimo' is not in second_opinion_policy.families (claude, gpt, qwen, gemini)",
      ],
      [
        { argv: ["mine"], family: null, model_families: { "x/y": "mimo" } },
        "model_families.x/y 'mimo' is not in second_opinion_policy.families (claude, gpt, qwen, gemini)",
      ],
      [
        { argv: "mine -m {model}", family: "qwen" },
        "argv must be a non-empty list of strings (it is never split or passed through a shell)",
      ],
      [
        { argv: [], family: "qwen" },
        "argv must be a non-empty list of strings (it is never split or passed through a shell)",
      ],
      [
        { argv: ["mine"], family: "qwen", models: ["big"] },
        "argv holds no {model} placeholder, but a model is declared or pinned for it",
      ],
      [{ argv: ["mine"], family: "qwen", prompt: "pipe" }, "prompt must be one of: argv, stdin"],
      [{ argv: ["mine"], family: "qwen", repo: "maybe" }, "repo must be one of: worktree, none, unknown"],
      [{ family: "qwen" }, "carries no argv and akmon ships no command for it"],
      [
        { argv: ["mine", "{model}"], family: "qwen", models: ["big"], aliases: true },
        "aliases: true needs a catalog (file and format) to resolve the aliases from",
      ],
      [
        { argv: ["mine"], family: "qwen", aliases: true, catalog: { file: "~/x.json", format: "nope" } },
        "catalog must be an object with a string file and a format of: codex-models-cache",
      ],
      [
        { argv: ["mine"], family: "qwen", aliases: true, catalog: "~/x.json" },
        "catalog must be an object with a string file and a format of: codex-models-cache",
      ],
      [{ argv: ["mine"], family: "qwen", aliases: "yes" }, "aliases must be true, or the key left out"],
      [
        { argv: ["mine", "{model}"], family: "qwen", models: ["default"] },
        "models must not list the reserved token 'default'; a ladder entry says carrier:default",
      ],
    ]);
    for (const [row, problem] of bad) {
      assert.deepEqual(overlayFindings(root, { providers: { mine: row } }), [
        `error _aitna/model-routing.json#providers.mine project overlay _aitna/model-routing.json provider mine: ${problem}`,
      ]);
    }
    // a ladder pin on a row with no placeholder; an overlay that extends the vocabulary and uses it
    assert.match(
      overlayFindings(root, {
        providers: { mine: { argv: ["mine"], family: "qwen" } },
        second_opinion_policy: { ladder: ["mine:big"] },
      })[0],
      /^error _aitna\/model-routing\.json#providers\.mine .*argv holds no \{model\} placeholder/,
    );
    assert.deepEqual(
      overlayFindings(root, {
        second_opinion_policy: { families: { mimo: "Xiaomi MiMo" } },
        providers: { mine: { argv: ["mine"], family: "mimo" } },
      }),
      [
        "ok _aitna/model-routing.json#second_opinion_policy project overlay _aitna/model-routing.json family vocabulary lists 5 families",
        "ok _aitna/model-routing.json#providers.mine project overlay _aitna/model-routing.json provider mine is configured",
      ],
    );
    // the developer-local overlay is gitignored and absent in CI: it is never read
    put(root, "_aitna/.local/model-routing.json", JSON.stringify({ providers: { x: { family: "mimo" } } }));
    fs.rmSync(posix.join(root, "_aitna/model-routing.json"));
    assert.deepEqual(overlayFindings(root, {}), []);
  });
});

test("routing overlay: a row with aliases and a known catalog is accepted", async () => {
  await withScratch((scratch) => {
    const root = project(scratch);
    const row = {
      argv: ["mine", "{model}"],
      family: "qwen",
      models: ["big"],
      aliases: true,
      catalog: { file: "~/.mine/models.json", format: "codex-models-cache" },
    };
    assert.deepEqual(overlayFindings(root, { providers: { mine: row } }), [
      "ok _aitna/model-routing.json#providers.mine project overlay _aitna/model-routing.json provider mine is configured",
    ]);
  });
});

// -- ADR-0024/D17: the `efforts` row and `model@effort` entries --

const EFFORTS = { flag: "--thinking {effort}", levels: ["low", "high"] };
const EFFORTS_SHAPE = "efforts must be an object with a flag holding {effort}";

test("routing overlay: a row with a bad efforts declaration is one error naming the row", async () => {
  await withScratch((scratch) => {
    const root = project(scratch);
    const base = { argv: ["mine", "{model}"], family: "qwen" };
    const bad = /** @type {Array<[object, string]>} */ ([
      [
        { ...base, efforts: "high" },
        "efforts must be an object with a flag holding {effort} and a non-empty list of unique levels",
      ],
      [{ ...base, efforts: { flag: "--t {effort}", levels: [] } }, EFFORTS_SHAPE],
      [{ ...base, efforts: { flag: "--t {effort}", levels: ["a", "a"] } }, EFFORTS_SHAPE],
      [{ ...base, efforts: { flag: "--t", levels: ["a"] } }, EFFORTS_SHAPE],
      [{ ...base, efforts: { flag: "--t {effort}", levels: ["a", 3] } }, EFFORTS_SHAPE],
      [
        { ...base, models: ["m@max"], efforts: EFFORTS },
        "models entry 'm@max' names the effort 'max', which is not one of: low, high",
      ],
      [{ ...base, models: ["m@high"] }, "models entry 'm@high' carries an effort, but the row declares no efforts"],
      [{ ...base, models: ["default@high"], efforts: EFFORTS }, "models must not list the reserved token 'default'"],
    ]);
    for (const [row, fragment] of bad) {
      const found = overlayFindings(root, { providers: { mine: row } });
      assert.equal(found.length, 1, fragment);
      assert.ok(found[0].startsWith("error _aitna/model-routing.json#providers.mine "), found[0]);
      assert.ok(found[0].includes(fragment), found[0]);
    }
  });
});

test("routing overlay: a row with efforts and effort entries is accepted", async () => {
  await withScratch((scratch) => {
    const root = project(scratch);
    const row = { argv: ["mine", "{model}"], family: "qwen", models: ["m", "m@high"], efforts: EFFORTS };
    assert.deepEqual(overlayFindings(root, { providers: { mine: row } }), [
      "ok _aitna/model-routing.json#providers.mine project overlay _aitna/model-routing.json provider mine is configured",
    ]);
  });
});

test("the catalog formats and the default token of verify.json mirror the routing module", () => {
  assert.deepEqual(data.routing_catalog_formats, [...CATALOG_FORMATS]);
  assert.equal(data.routing_default_model_token, defaultModelToken(AGENTS_DATA));
});

test("the shipped codex row carries aliases and a catalog verify accepts", () => {
  const registry = /** @type {any} */ (
    JSON.parse(fs.readFileSync(posix.join(TREE, "tools", "model_routing", "registry.json"), "utf-8"))
  );
  const row = registry.providers.codex;
  assert.equal(row.aliases, true);
  assert.deepEqual(row.catalog, { file: "~/.codex/models_cache.json", format: "codex-models-cache" });
  assert.ok(data.routing_catalog_formats.includes(row.catalog.format));
});

test("routing registry: a family outside the vocabulary, or no vocabulary at all, is named", async () => {
  await withScratch((scratch) => {
    const root = project(scratch);
    const tree = posix.join(scratch, "tree");
    const vendor = {
      selection_policy: { reasoner: "orchestrator", worker: "lowest" },
      semantic_fallback: { worker: "w", mid: "m", reasoner: "r", orchestrator: "o" },
      carrier: "claude",
    };
    const check = (/** @type {object} */ providers, /** @type {object} */ policy) => {
      put(
        tree,
        "tools/model_routing/registry.json",
        JSON.stringify({ anthropic: vendor, openai: vendor, providers, second_opinion_policy: policy }),
      );
      const verifier = new Verifier(root);
      verifier.standardRoot = tree;
      verifier.checkModelRouting();
      return verifier.findings.map((f) => `${f.severity} ${f.message}`).filter((m) => m.includes("model-routing"));
    };
    const row = { operation: "review", model_flag: "--model {model}", family: "gptt", report_dir: "d" };
    const vocabulary = { claude: "C", gpt: "G" };
    assert.ok(
      check({ claude: row }, { ladder: ["claude"], families: vocabulary }).includes(
        "error model-routing provider claude: family 'gptt' is not in second_opinion_policy.families (claude, gpt)",
      ),
    );
    assert.ok(
      check({ claude: { ...row, family: "gpt" } }, { ladder: ["claude"] }).includes(
        "error model-routing second_opinion_policy.families must be a non-empty object keyed by family name",
      ),
    );
  });
});

test("routing overlay: verify's merge is the loader's — objects key by key, anything else replaced whole", () => {
  const base = { a: { b: 1, c: [1, 2] }, d: { e: 1 }, f: 1 };
  const overlay = { a: { c: [3] }, d: [1], g: { h: 2 } };
  assert.deepEqual(mergeOverlay(base, overlay), { a: { b: 1, c: [3] }, d: [1], f: 1, g: { h: 2 } });
});

// -- the record --------------------------------------------------------------------------------

test("attach record: a TOML date in a version key is truthy and not a string — an invalid-version error, not a missing key", async () => {
  await withScratch((scratch) => {
    const root = project(scratch);
    put(
      root,
      "_aitna/.akmon.toml",
      'mount = "package"\necosystem = "node"\nakmon_version = 2026-10-11\nattached_archetype = "x"\nlast_realign = "1"\n',
    );
    assert.deepEqual(
      recorded(root, (v) => v.checkAttachRecord()),
      ["error attach.record _aitna/.akmon.toml has invalid version key(s): akmon_version; expected non-empty strings"],
    );
    put(
      root,
      "_aitna/.akmon.toml",
      'mount = "package"\necosystem = "node"\nakmon_version = 0\nattached_archetype = "x"\nlast_realign = "1"\n',
    );
    assert.deepEqual(
      recorded(root, (v) => v.checkAttachRecord()),
      ["error attach.record _aitna/.akmon.toml is missing required key(s): akmon_version"],
    );
    put(
      root,
      "_aitna/.akmon.toml",
      'mount = "package"\necosystem = "node"\nakmon_version = "v1.2.3-4-gabc"\nattached_archetype = "x"\nlast_realign = "1.2.3"\n',
    );
    assert.deepEqual(
      recorded(root, (v) => v.checkAttachRecord()),
      [
        "ok attach.record _aitna/.akmon.toml records akmon version v1.2.3-4-gabc",
        "ok attach.realign _aitna/.akmon.toml was realigned at 1.2.3, the version it records",
      ],
    );
    put(
      root,
      "_aitna/.akmon.toml",
      'mount = "package"\necosystem = "node"\nakmon_version = "1.2.4"\nattached_archetype = "x"\nlast_realign = "1.2.3"\n',
    );
    assert.match(
      recorded(root, (v) => v.checkAttachRecord())[1],
      /^error attach\.realign _aitna\/\.akmon\.toml records akmon 1\.2\.4 but was last realigned at 1\.2\.3 — /,
    );
  });
});

test("the [check] table of the record: valid, malformed, and a record that cannot be read", async () => {
  await withScratch((scratch) => {
    const root = project(scratch);
    const write = (/** @type {string} */ extra) => put(root, "_aitna/.akmon.toml", NODE_RECORD + extra);
    write("");
    assert.deepEqual(
      recorded(root, (v) => v.checkCheckConfig()),
      [],
    );
    // An empty table — what `init --checks none` records (C123) — reads as no table: no finding.
    write("\n[check]\n# What `akmon check` runs\n");
    assert.deepEqual(
      recorded(root, (v) => v.checkCheckConfig()),
      [],
    );
    write('[check]\nlint = "echo {files}"\ntypes = { command = "echo b" }\n');
    assert.match(recorded(root, (v) => v.checkCheckConfig())[0], /^ok check\.config \[check\] declares 2 check\(s\)/);
    write("[check]\nlint = 3\n");
    assert.match(recorded(root, (v) => v.checkCheckConfig())[0], /^error check\.config /);
    put(root, "_aitna/.akmon.toml", "mount = [\n");
    assert.match(recorded(root, (v) => v.checkCheckConfig())[0], /^error check\.config /);
  });
});

// -- CI, gitignore, changelog ------------------------------------------------------------------

test("CI: workflows are read in code point order, .yml before .yaml, and the package commands are substrings", async () => {
  await withScratch((scratch) => {
    const root = project(scratch);
    fs.rmSync(posix.join(root, ".github", "workflows", "ci.yml"));
    assert.deepEqual(
      recorded(root, (v) => v.checkCi()),
      ["warn ci.akmon-checks no GitHub Actions workflows found"],
    );
    put(root, ".github/workflows/a.yml", "run: npx akmon sync --check\n");
    assert.deepEqual(
      recorded(root, (v) => v.checkCi()),
      ["warn ci.akmon-checks CI should run: akmon verify --strict"],
    );
    put(root, ".github/workflows/b.yaml", "run: pnpm exec akmon verify --strict\n");
    assert.deepEqual(
      recorded(root, (v) => v.checkCi()),
      ["ok ci.akmon-checks CI checks akmon generated pointers and verify"],
    );
  });
});

// -- the dotted layer (ADR 0028 D01) -----------------------------------------------------------

test("local layer: a project without the folders raises no finding, and a legacy local/ is one warning naming the move", async () => {
  await withScratch((scratch) => {
    const root = project(scratch);
    assert.deepEqual(
      recorded(root, (v) => v.checkLocalLayer()),
      [],
    );
    put(root, "_aitna/local/handoff/C1-x/HANDOFF.md", "x\n");
    const verifier = new Verifier(root);
    verifier.checkLocalLayer();
    const [[severity, target, message, fix], ...rest] = of(verifier, "layout.local-legacy");
    assert.deepEqual(rest, []);
    assert.equal(severity, "warn");
    assert.equal(target, "_aitna/local");
    assert.match(message, /_aitna\/local\/ to _aitna\/\.local\//);
    assert.match(message, /_aitna\/local\/handoff\/ and _aitna\/local\/plans\/ into _aitna\/\.ergon\/<id>-<name>\//);
    assert.match(message, /never moves it silently/);
    assert.match(String(fix), /^Move the content to _aitna\/\.local\/ and _aitna\/\.ergon\/<id>-<name>\/ yourself/);
    assert.equal(fs.existsSync(posix.join(root, "_aitna/local/handoff/C1-x/HANDOFF.md")), true);
    assert.equal(fs.existsSync(posix.join(root, "_aitna/.local")), false);
  });
});

test("local layer: the legacy folder follows a declared dev root", async () => {
  await withScratch((scratch) => {
    const root = project(scratch);
    put(root, ".aitna-root", "tools/ai\n");
    put(root, "tools/ai/local/TASKS.md", "x\n");
    const verifier = new Verifier(root);
    verifier.checkLocalLayer();
    assert.deepEqual(
      of(verifier, "layout.local-legacy").map((row) => row[1]),
      ["tools/ai/local"],
    );
  });
});

test("local layer: an unignored .local or .ergon is a warning on .gitignore, an ignored one is silent", async () => {
  await withScratch((scratch) => {
    const root = project(scratch);
    for (const name of [".local", ".ergon"]) {
      put(root, `_aitna/${name}/x`, "x\n");
      const verifier = new Verifier(root);
      verifier.checkLocalLayer();
      const [[severity, target, message, fix], ...rest] = of(verifier, "gitignore.local-layer");
      assert.deepEqual(rest, [], name);
      assert.equal(severity, "warn");
      assert.equal(target, ".gitignore");
      assert.equal(
        message,
        `_aitna/${name}/ exists but .gitignore does not ignore it, so what only this machine needs could be committed (ADR 0028 D01)`,
      );
      assert.equal(fix, `Add _aitna/${name}/ to .gitignore, the line \`akmon init\` writes for the dotted layer.`);
      fs.rmSync(posix.join(root, "_aitna", name), { recursive: true });
    }
    put(root, "_aitna/.local/x", "x\n");
    put(root, "_aitna/.ergon/x", "x\n");
    for (const [text, expected] of /** @type {Array<[string, number]>} */ ([
      ["*.env\n_aitna/.local/\n_aitna/.ergon/\n", 0],
      ["/_aitna/.local\n.ergon/\n", 0],
      ["_aitna/\n", 0],
      ["# _aitna/.local/\n_aitna/.ergon/\n", 1],
      ["_aitna/.local/\n_aitna/.ergon/\n!_aitna/.ergon/\n", 1],
      ["_aitna/local/\n", 2],
      ["", 2],
    ])) {
      put(root, ".gitignore", text);
      const verifier = new Verifier(root);
      verifier.checkLocalLayer();
      assert.equal(of(verifier, "gitignore.local-layer").length, expected, JSON.stringify(text));
    }
    fs.rmSync(posix.join(root, ".gitignore"));
    const verifier = new Verifier(root);
    verifier.checkLocalLayer();
    assert.equal(of(verifier, "gitignore.local-layer").length, 2);
  });
});

test("local layer: the warnings fail only under --strict", async () => {
  await withScratch(async (scratch) => {
    const root = project(scratch);
    syncWrite(root);
    put(root, "_aitna/local/x", "x\n");
    const empty = posix.join(scratch, "empty-path");
    fs.mkdirSync(empty);
    await withPath(empty, async () => {
      await withoutAitnaRoot(async () => {
        const plain = await run(["--project-root", root]);
        assert.equal(plain.code, 0, plain.stdout);
        assert.match(plain.stdout, /^WARN layout\.local-legacy _aitna\/local: /m);
        assert.equal((await run(["--project-root", root, "--strict", "--quiet"])).code, 1);
      });
    });
  });
});

test("changelog: package mode answers one ok finding with no target", async () => {
  await withScratch((scratch) => {
    const root = project(scratch);
    const verifier = new Verifier(root);
    verifier.checkChangelog();
    assert.deepEqual(of(verifier, "changelog.package-mode"), [
      [
        "ok",
        "",
        "package mode: changelog discipline is owned by the akmon repository",
        "Track the standard's changelog discipline in the akmon repository itself.",
      ],
    ]);
  });
});

// -- the texts ---------------------------------------------------------------------------------

test("the node texts of verify.json build valid findings: one line, a one-sentence fix", () => {
  const texts = data.node;
  const values = {
    found: ".pnp.cjs",
    relative: "node_modules/akmon/js/hooks",
    value: "'^1.2.3'",
    mount: "_aitna/akmon",
  };
  for (const [key, text] of Object.entries(texts)) {
    if (typeof text !== "string") {
      continue;
    }
    const filled = text.replace(/\{\{(\w+)\}\}/g, (_m, name) => /** @type {Record<string, string>} */ (values)[name]);
    assert.ok(!filled.includes("\n"), key);
    if (key.endsWith("_fix")) {
      assert.match(filled, /\.$/, key);
      assert.ok(!/[.!?](?:[ \t\n\r\f\v]+[^ \t\n\r\f\v]|(?=[A-Z]))/.test(filled.slice(0, -1)), `${key} is one sentence`);
    }
  }
  assert.deepEqual(texts.pnp_markers, [".pnp.cjs", ".pnp.loader.mjs"]);
});

test("the always-loaded block heading and cap are read through the twin, once per run", () => {
  const verifier = new Verifier(TREE);
  assert.equal(typeof alwaysLoaded.blockHeading(verifier.alwaysLoadedData), "string");
  assert.strictEqual(verifier.alwaysLoadedData, verifier.alwaysLoadedData);
  assert.strictEqual(verifier.codexHooksData, verifier.codexHooksData);
});

// The text patterns are the Python's under re.ASCII (C105); meta/tests/test_verify.py pins the same rows.
/** @type {[keyof typeof TEXT_PATTERNS, string, boolean][]} */
const ASCII_ROWS = [
  ["date", "2026-10-11", true],
  ["date", "\u0662\u0660\u0662\u0666-\u0661\u0660-\u0661\u0661", false],
  ["date", "\u00e92026-10-11", true],
  ["delegationDefault", "Delegation is the default", true],
  ["delegationDefault", "delegation\u00a0is the default", false],
  ["delegationDefault", "delegation is the default\u00e9", true],
  ["numberedDr", "ADR 12", true],
  ["numberedDr", "ADR-0020", true],
  ["numberedDr", "ADR\u00a012", false],
  ["numberedDr", "ADR\u0661\u0662", false],
  ["roadmapCite", "ROADMAP O1", true],
  ["roadmapCite", "ROADMAP\u3000O1", false],
  ["devName", "\u00e9self_ci", true],
  ["devName", "self_ci\u00df", true],
  ["devName", "xself_ci", false],
  ["legacyOwnerAnchor", "**D2** \u2014 the owner verifies", true],
  ["legacyOwnerAnchor", "**D2**\u00a0\u2014 the owner verifies", false],
];

test("the text patterns have the ASCII meaning of the Python's", () => {
  for (const [name, text, found] of ASCII_ROWS) {
    const pattern = new RegExp(TEXT_PATTERNS[name].source, TEXT_PATTERNS[name].flags.replace("g", ""));
    assert.equal(pattern.test(text), found, `${name} ${JSON.stringify(text)}`);
  }
});

// -- agents.profile-import / agents.language-profile (C127) ------------------------------------

/**
 * The profile findings of a node project whose AGENTS.md has `imports` in place of its js.md import.
 * @param {string} scratch
 * @param {string} imports
 * @param {Record<string, string>} [files]
 */
function profileFindings(scratch, imports, files = {}) {
  const root = project(scratch);
  put(root, "AGENTS.md", AGENTS.replace("@_aitna/.akmon/profiles/js.md\n", imports));
  for (const [relative, body] of Object.entries(files)) {
    put(root, relative, body);
  }
  const verifier = new Verifier(root);
  verifier.checkProfileImports();
  return verifier;
}

test("profile imports: the js.md import of a package.json project resolves and covers it", async () => {
  await withScratch((scratch) => {
    const verifier = profileFindings(scratch, "@_aitna/.akmon/profiles/js.md\n");
    assert.deepEqual(
      verifier.findings.map((finding) => [finding.severity, finding.code]),
      [
        ["ok", "agents.profile-import"],
        ["ok", "agents.language-profile"],
      ],
    );
  });
});

test("profile imports: the vendored prefix in a package attach warns with the line to write", async () => {
  await withScratch((scratch) => {
    const verifier = profileFindings(scratch, "@_aitna/akmon/profiles/js.md\n");
    assert.deepEqual(of(verifier, "agents.profile-import"), [
      [
        "warn",
        "AGENTS.md",
        "AGENTS.md imports @_aitna/akmon/profiles/js.md, which resolves to nothing: a package attach imports the standard's files from @_aitna/.akmon/",
        "Replace the line @_aitna/akmon/profiles/js.md with @_aitna/.akmon/profiles/js.md in AGENTS.md.",
      ],
    ]);
    assert.equal(of(verifier, "agents.language-profile")[0][0], "ok");
  });
});

test("profile imports: a profile the standard does not ship warns, naming what it ships", async () => {
  await withScratch((scratch) => {
    const verifier = profileFindings(scratch, "@_aitna/.akmon/profiles/rust.md\n");
    assert.deepEqual(of(verifier, "agents.profile-import"), [
      [
        "warn",
        "AGENTS.md",
        "AGENTS.md imports @_aitna/.akmon/profiles/rust.md, a profile the standard does not ship, so it loads nothing",
        "Remove the line @_aitna/.akmon/profiles/rust.md from AGENTS.md, or import a profile the standard ships (js.md, python-stdlib.md, python.md, quant.md).",
      ],
    ]);
  });
});

test("profile imports: a project file the standard does not ship is left alone (ADR-0014/D02)", async () => {
  await withScratch((scratch) => {
    const verifier = profileFindings(scratch, "@docs/profiles/house.md\n", { "docs/profiles/house.md": "" });
    assert.deepEqual(
      of(verifier, "agents.profile-import").map(([severity]) => severity),
      ["ok"],
    );
  });
});

test("profile imports: a missing project file the standard does not ship warns", async () => {
  await withScratch((scratch) => {
    const verifier = profileFindings(scratch, "@docs/profiles/house.md\n");
    assert.deepEqual(
      of(verifier, "agents.profile-import").map(([severity, , message]) => [severity, message]),
      [
        [
          "warn",
          "AGENTS.md imports @docs/profiles/house.md, a profile the standard does not ship, so it loads nothing",
        ],
      ],
    );
  });
});

test("language profile: a package.json project with no js.md import warns with the exact line", async () => {
  await withScratch((scratch) => {
    const verifier = profileFindings(scratch, "Add one (`@_aitna/.akmon/profiles/<name>.md`).\n");
    assert.deepEqual(of(verifier, "agents.language-profile"), [
      [
        "warn",
        "AGENTS.md",
        "AGENTS.md imports no js.md language profile, though package.json names the project's language",
        "Add the line @_aitna/.akmon/profiles/js.md to the AGENTS.md akmon block, right after the _common.md import.",
      ],
    ]);
  });
});

test("language profile: both manifests want both profiles, python first", async () => {
  await withScratch((scratch) => {
    const verifier = profileFindings(scratch, "", { "pyproject.toml": "[project]\n" });
    assert.deepEqual(
      of(verifier, "agents.language-profile").map(([severity, , message]) => [severity, message]),
      [
        ["warn", "AGENTS.md imports no python.md language profile, though pyproject.toml names the project's language"],
        ["warn", "AGENTS.md imports no js.md language profile, though package.json names the project's language"],
      ],
    );
  });
});

// -- a mounted Node project (C129) -------------------------------------------------------------

/**
 * A mount under `scratch` that is this tree, entry by entry, with a changelog of its own: the
 * repository's `CHANGELOG.md` loses its `## Unreleased` heading at every release.
 * @param {string} scratch
 * @returns {string}
 */
function treeMount(scratch) {
  const mount = posix.join(scratch, "tree-mount");
  fs.mkdirSync(mount);
  for (const entry of fs.readdirSync(TREE)) {
    if (entry !== "CHANGELOG.md") {
      fs.symlinkSync(posix.join(TREE, entry), posix.join(mount, entry));
    }
  }
  put(mount, "CHANGELOG.md", "# Changelog\n\n## Unreleased\n");
  return mount;
}

test("a synced mounted Node project is healthy: the mounted anchors, the mount's launcher and CI, no pin check", async () => {
  await withScratch(async (scratch) => {
    const root = mountedProject(scratch, { mount: treeMount(scratch) });
    await withoutAitnaRoot(async () => {
      syncWrite(root);
      const empty = posix.join(scratch, "empty-path");
      fs.mkdirSync(empty);
      await withPath(empty, async () => {
        const result = await run(["--project-root", root, "--strict"]);
        assert.equal(result.stderr, "");
        assert.equal(result.code, 0, result.stdout);
        const lines = result.stdout.trimEnd().split("\n");
        assert.ok(
          lines.every((line) => line.startsWith("OK ")),
          result.stdout,
        );
        assert.ok(
          lines.includes(
            "OK layout.standard-path _aitna/akmon/README.md: _aitna/akmon/README.md exists → Keep _aitna/akmon/README.md in the standard tree.",
          ),
        );
        assert.ok(
          lines.includes(
            "OK hooks.launcher _aitna/akmon/js/hooks: generated hook wiring runs node on _aitna/akmon/js/hooks, which is present → Keep the akmon mount at _aitna/akmon in place.",
          ),
          result.stdout,
        );
        assert.ok(
          lines.includes(
            "OK changelog.unreleased _aitna/akmon/CHANGELOG.md: CHANGELOG.md has an Unreleased section → Keep an `## Unreleased` heading for pending changes.",
          ),
          result.stdout,
        );
        const codes = lines.map((line) => line.split(" ")[1].replace(/:$/, ""));
        for (const code of ["agents.block-anchors", "ci.akmon-checks", "attach.record", "attach.realign"]) {
          assert.ok(codes.includes(code), code);
        }
        // no pin to read in a mount, no Python cache to guard, no package-mode changelog answer
        for (const code of ["package.dev-pin", "gitignore.akmon-pycache", "changelog.package-mode"]) {
          assert.ok(!codes.includes(code), code);
        }
        assert.ok(!result.stdout.includes("standard tree:"), result.stdout);
      });
    });
  });
});

test("hooks.launcher of a mount: a mount without js/hooks is an error with the restore fix, and ignores Plug'n'Play", async () => {
  await withScratch(async (scratch) => {
    const bare = posix.join(scratch, "bare-mount");
    put(bare, "README.md", "# a mount without js/\n");
    const root = mountedProject(scratch, { mount: bare });
    put(root, ".pnp.cjs", "");
    await withoutAitnaRoot(async () => {
      const verifier = new Verifier(root);
      verifier.checkHookLauncher();
      assert.deepEqual(of(verifier, "hooks.launcher"), [
        [
          "error",
          "_aitna/akmon/js/hooks",
          "generated hook wiring runs node on _aitna/akmon/js/hooks, which is missing — every akmon hook command fails silently (an unavailable script produces no session-visible error), so the guardrails are off",
          "Restore the akmon mount at _aitna/akmon (for a submodule, `git submodule update --init`), then re-run `node _aitna/akmon/js/akmon/cli.mjs sync`.",
        ],
      ]);
    });
  });
});

test("CI of a mount: the mounted JavaScript CLI's commands are required, the package spelling is not enough", async () => {
  await withScratch(async (scratch) => {
    const root = mountedProject(scratch);
    put(root, ".github/workflows/ci.yml", CI);
    await withoutAitnaRoot(async () => {
      const verifier = new Verifier(root);
      verifier.checkCi();
      assert.deepEqual(of(verifier, "ci.akmon-checks")[0].slice(0, 3), [
        "warn",
        ".github/workflows",
        "CI should run: node _aitna/akmon/js/akmon/cli.mjs sync --check, node _aitna/akmon/js/akmon/cli.mjs verify --strict",
      ]);
    });
  });
});

test("changelog of a mount: no `## Unreleased` heading warns, any case; no CHANGELOG.md is no finding", async () => {
  await withScratch(async (scratch) => {
    const mount = posix.join(scratch, "mount");
    const root = mountedProject(scratch, { mount });
    await withoutAitnaRoot(async () => {
      const findings = (/** @type {string} */ text) => {
        put(mount, "CHANGELOG.md", text);
        const verifier = new Verifier(root);
        verifier.checkChangelog();
        return of(verifier, "changelog.unreleased");
      };
      assert.deepEqual(findings("# Changelog\n\n## 1.0.0\n"), [
        [
          "warn",
          "_aitna/akmon/CHANGELOG.md",
          "CHANGELOG.md has no `## Unreleased` section; add one for pending changes",
          "Add an `## Unreleased` heading above the latest release.",
        ],
      ]);
      assert.equal(findings("# Changelog\n\n##\tunreleased\n")[0][0], "ok");
      // `^` is a line start after `\n` only, and the word ends at an ASCII boundary
      assert.equal(findings("# Changelog ## Unreleased\n")[0][0], "warn");
      assert.equal(findings("## Unreleasedx\n")[0][0], "warn");
      fs.rmSync(posix.join(mount, "CHANGELOG.md"));
      const verifier = new Verifier(root);
      verifier.checkChangelog();
      assert.deepEqual(verifier.findings, []);
    });
  });
});

test("vendored leftovers: each top-level entry a Node copy does not carry warns, in code point order; only vendored", async () => {
  await withScratch(async (scratch) => {
    const mount = posix.join(scratch, "mount");
    for (const entry of ["README.md", "js/x.mjs", ".gitignore", "meta/TASKS.md", "src/a.py", "Zed", "package.json"]) {
      put(mount, entry, "x\n");
    }
    const root = mountedProject(scratch, { mount, record: MOUNTED_RECORD.replace("submodule", "vendored") });
    await withoutAitnaRoot(async () => {
      const verifier = new Verifier(root);
      verifier.checkVendoredLeftovers();
      const found = of(verifier, "layout.vendored-leftover");
      assert.deepEqual(
        found.map(([severity, target]) => [severity, target]),
        // a Node record's copy carries src/ (the CLI data) and package.json (the CLI's version), C129
        [
          ["warn", "_aitna/akmon/Zed"],
          ["warn", "_aitna/akmon/meta"],
        ],
      );
      assert.equal(
        found[1][2],
        // a Node copy is re-made by the JavaScript init through npx, not by `akmon init` (C129)
        "_aitna/akmon/meta is no longer shipped by the akmon carrier; a vendored re-copy (`npx github:akumidv/ai_akmon#<tag> init --mode vendored`, the command `node _aitna/akmon/js/akmon/cli.mjs update` prints) replaces only the standard's members and leaves it in place",
      );
      assert.equal(found[1][3], "Remove _aitna/akmon/meta by hand if the mount should match the carrier.");
      put(
        root,
        "_aitna/.akmon.toml",
        MOUNTED_RECORD.replace("submodule", "vendored").replace('ecosystem = "node"', 'ecosystem = "python"'),
      );
      const python = new Verifier(root);
      python.checkVendoredLeftovers();
      assert.deepEqual(
        of(python, "layout.vendored-leftover").map(([, target]) => target),
        ["_aitna/akmon/Zed", "_aitna/akmon/meta", "_aitna/akmon/package.json", "_aitna/akmon/src"],
      );
      assert.ok(of(python, "layout.vendored-leftover")[0][2].includes("`akmon init --mode vendored` copies only"));
      put(root, "_aitna/.akmon.toml", MOUNTED_RECORD);
      const submodule = new Verifier(root);
      submodule.checkVendoredLeftovers();
      assert.deepEqual(submodule.findings, []);
    });
  });
});

test("a mounted record's standard paths read relative to the root; a missing mount falls back to the running tree", async () => {
  await withScratch(async (scratch) => {
    const root = mountedProject(scratch);
    await withoutAitnaRoot(async () => {
      const verifier = new Verifier(root);
      assert.equal(verifier.standardRoot, posix.join(root, "_aitna", "akmon"));
      verifier.checkHooks();
      assert.deepEqual(of(verifier, "layout.standard-path")[0].slice(0, 2), [
        "ok",
        "_aitna/akmon/js/hooks/hook_core.mjs",
      ]);
      fs.unlinkSync(posix.join(root, "_aitna", "akmon"));
      const unmounted = new Verifier(root);
      assert.equal(unmounted.standardRoot, TREE);
      assert.equal(unmounted.displayPath(posix.join(TREE, "README.md")), "standard tree:README.md");
    });
  });
});
