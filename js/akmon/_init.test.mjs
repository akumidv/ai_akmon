/**
 * node:test for `js/akmon/_init.mjs` — the Node package-mode `akmon init`: the package-manager
 * detection, the CI workflow per manager, every refusal, the first attach (exit 1, pin step
 * first), the completed attach (exit 0, `last_realign`), the idempotent re-run, AGENTS.md and
 * `.gitignore` handling, and the real process (confirmation on stdin). The byte-level spec is the
 * `cli/init-node-*` scenarios of `meta/conformance/scenarios`.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import { posix } from "node:path";
import { fileURLToPath } from "node:url";

import { fill } from "../common/jsondata.mjs";
import { readSyncData } from "../bin/sync.mjs";
import { switchTag } from "../common/versions.mjs";
import {
  ciInstall,
  detectManager,
  detectedProfiles,
  detectNodeTools,
  effectiveAitnaRoot,
  firstAttachEcosystem,
  main,
  mergeGitignore,
  newestReleaseTag,
  nodeSwitchCommand,
  npxSpec,
  readInitData,
  shellWord,
  tagForVersion,
  validatedAitnaRoot,
  withoutEmptyChecks,
  withoutRuffDefault,
} from "./_init.mjs";

const TREE = posix.resolve(posix.dirname(fileURLToPath(import.meta.url)), "..", "..");
const CLI = posix.join(TREE, "js", "akmon", "cli.mjs");
const manifest = JSON.parse(fs.readFileSync(posix.join(TREE, "package.json"), "utf8"));
const VERSION = manifest.version;
const data = readInitData();

/**
 * A project root (links resolved) holding `files`; `linked` puts `node_modules/akmon` on the running tree.
 * @param {Record<string, string>} [files]
 * @param {{linked?: boolean}} [options]
 * @returns {string}
 */
function project(files = {}, { linked = false } = {}) {
  const root = fs.realpathSync(fs.mkdtempSync(posix.join(os.tmpdir(), "akmon-init-")));
  for (const [relative, text] of Object.entries(files)) {
    fs.mkdirSync(posix.dirname(posix.join(root, relative)), { recursive: true });
    fs.writeFileSync(posix.join(root, relative), text);
  }
  if (linked) {
    fs.mkdirSync(posix.join(root, "node_modules"), { recursive: true });
    fs.symlinkSync(TREE, posix.join(root, "node_modules", "akmon"));
  }
  return root;
}

/** A manifest that pins akmon in `devDependencies`. */
const PINNED = JSON.stringify({ name: "demo", devDependencies: { akmon: VERSION } });

/**
 * Run `main(args)` with both streams captured and `AITNA_ROOT` unset.
 * @param {string[]} args
 * @returns {Promise<{status: number, stdout: string, stderr: string}>}
 */
async function run(args) {
  const out = /** @type {string[]} */ ([]);
  const err = /** @type {string[]} */ ([]);
  const write = { out: process.stdout.write, err: process.stderr.write };
  const saved = process.env.AITNA_ROOT;
  delete process.env.AITNA_ROOT;
  process.stdout.write = /** @type {typeof process.stdout.write} */ (
    (/** @type {string} */ text) =>
      (out.push(text), true)
  );
  process.stderr.write = /** @type {typeof process.stderr.write} */ (
    (/** @type {string} */ text) =>
      (err.push(text), true)
  );
  try {
    return { status: await main(args), stdout: out.join(""), stderr: err.join("") };
  } finally {
    process.stdout.write = write.out;
    process.stderr.write = write.err;
    if (saved !== undefined) {
      process.env.AITNA_ROOT = saved;
    }
  }
}

/**
 * Every regular file under `root`, relative path → content (links not followed).
 * @param {string} root
 * @param {string} [dir]
 * @returns {Record<string, string>}
 */
function snapshot(root, dir = "") {
  /** @type {Record<string, string>} */
  const files = {};
  for (const entry of fs.readdirSync(posix.join(root, dir), { withFileTypes: true })) {
    const relative = posix.join(dir, entry.name);
    if (entry.isSymbolicLink()) {
      continue;
    }
    if (entry.isDirectory()) {
      Object.assign(files, snapshot(root, relative));
    } else {
      files[relative] = fs.readFileSync(posix.join(root, relative), "utf8");
    }
  }
  return files;
}

/** @param {string} root @param {string} relative */
const text = (root, relative) => fs.readFileSync(posix.join(root, relative), "utf8");

// -- the package manager -----------------------------------------------------------------------

test("the package manager comes from the packageManager field first, then the lockfile, else npm", () => {
  const detect = (/** @type {Record<string, string>} */ files) => detectManager(data, project(files));
  assert.equal(detect({}), "npm");
  assert.equal(detect({ "package.json": "{}" }), "npm");
  assert.equal(detect({ "pnpm-lock.yaml": "" }), "pnpm");
  assert.equal(detect({ "yarn.lock": "" }), "yarn");
  assert.equal(detect({ "bun.lock": "" }), "bun");
  assert.equal(detect({ "bun.lockb": "" }), "bun");
  assert.equal(detect({ "package-lock.json": "{}" }), "npm");
  // the field beats a lockfile, in both directions
  assert.equal(detect({ "package.json": '{"packageManager":"pnpm@9.1.0+sha512.abc"}', "yarn.lock": "" }), "pnpm");
  assert.equal(detect({ "package.json": '{"packageManager":"npm@10.2.0"}', "pnpm-lock.yaml": "" }), "npm");
  assert.equal(detect({ "package.json": '{"packageManager":"bun@1.1.0"}' }), "bun");
  assert.equal(detect({ "package.json": '{"packageManager":"yarn@4.1.0"}', "package-lock.json": "{}" }), "yarn");
  // a field that names no known manager, or a manifest that is not JSON, falls through to the lockfile
  assert.equal(detect({ "package.json": '{"packageManager":"deno@2"}', "yarn.lock": "" }), "yarn");
  assert.equal(detect({ "package.json": "{not json", "pnpm-lock.yaml": "" }), "pnpm");
  assert.equal(detect({ "package.json": '{"packageManager":7}', "bun.lock": "" }), "bun");
  // the lockfile order is the table's: pnpm, yarn, bun, npm
  assert.equal(detect({ "yarn.lock": "", "package-lock.json": "{}" }), "yarn");
  assert.equal(detect({ "pnpm-lock.yaml": "", "yarn.lock": "" }), "pnpm");
});

test("the manager table holds the four managers with the commands the spec names", () => {
  assert.deepEqual(Object.keys(data.node_managers), ["pnpm", "yarn", "bun", "npm"]);
  const exec = Object.fromEntries(Object.entries(data.node_managers).map(([name, manager]) => [name, manager.exec]));
  assert.deepEqual(exec, { pnpm: "pnpm exec ", yarn: "yarn ", bun: "bunx ", npm: "npx " });
  const checkRun = Object.fromEntries(
    Object.entries(data.node_managers).map(([name, manager]) => [name, manager.check_run]),
  );
  assert.deepEqual(checkRun, {
    pnpm: "pnpm exec ",
    yarn: "yarn ",
    bun: "bunx --no-install ",
    npm: "npx --no-install ",
  });
  const runScript = Object.fromEntries(
    Object.entries(data.node_managers).map(([name, manager]) => [name, manager.run_script]),
  );
  assert.deepEqual(runScript, { pnpm: "pnpm run", yarn: "yarn run", bun: "bun run", npm: "npm run" });
  const add = Object.fromEntries(
    Object.entries(data.node_managers).map(([name, manager]) => [name, manager.add_dev_exact]),
  );
  assert.deepEqual(add, {
    pnpm: "pnpm add -D -E",
    yarn: "yarn add -D -E",
    bun: "bun add -d --exact",
    npm: "npm install -D -E",
  });
});

// -- the CI workflow ---------------------------------------------------------------------------

/** The workflow each manager gets. */
const WORKFLOWS = {
  npm: [
    "actions/setup-node@v4",
    "node-version: 22",
    "run: npm ci",
    "run: npx akmon sync --check",
    "run: npx akmon verify --strict",
  ],
  pnpm: [
    "pnpm/action-setup@v4",
    "actions/setup-node@v4",
    "run: pnpm install --frozen-lockfile",
    "run: pnpm exec akmon sync --check",
    "run: pnpm exec akmon verify --strict",
  ],
  yarn: [
    "actions/setup-node@v4",
    "run: yarn install --frozen-lockfile",
    "run: yarn akmon sync --check",
    "run: yarn akmon verify --strict",
  ],
  bun: [
    "oven-sh/setup-bun@v2",
    "run: bun install --frozen-lockfile",
    "run: bunx akmon sync --check",
    "run: bunx akmon verify --strict",
  ],
};
const LOCKFILES = { npm: "package-lock.json", pnpm: "pnpm-lock.yaml", yarn: "yarn.lock", bun: "bun.lock" };

for (const [manager, lines] of Object.entries(WORKFLOWS)) {
  test(`the ${manager} attach writes the ${manager} workflow and no Python anywhere`, async () => {
    const root = project(
      { "package.json": PINNED, [LOCKFILES[/** @type {keyof typeof LOCKFILES} */ (manager)]]: "" },
      { linked: true },
    );
    const result = await run(["--yes", "--project-root", root]);
    assert.equal(result.status, 0, result.stdout + result.stderr);
    const workflow = text(root, ".github/workflows/akmon.yml");
    assert.ok(workflow.startsWith("name: akmon\n\non: [push, pull_request]\n"));
    assert.ok(workflow.includes("      - uses: actions/checkout@v4\n"));
    for (const line of lines) {
      assert.ok(workflow.includes(line), `${manager}: ${line}\n${workflow}`);
    }
    assert.equal(workflow.includes("actions/setup-node@v4"), manager !== "bun");
    assert.ok(!/python|uv\b|pip/i.test(workflow));
    assert.ok(result.stdout.includes("akmon init: wrote .github/workflows/akmon.yml\n"));
  });
}

test("the CI install fits the project: unlocked installs without a lockfile, --immutable for Yarn 2+, a pnpm version only when undeclared", () => {
  const managers = data.node_managers;
  /** @type {Array<[string, Record<string, string>, string, boolean]>} */
  const rows = [
    ["npm", { "package.json": "{}" }, "npm install", false],
    ["npm", { "package.json": "{}", "package-lock.json": "" }, "npm ci", false],
    ["yarn", { "package.json": "{}", "yarn.lock": "" }, "yarn install --frozen-lockfile", false],
    ["yarn", { "package.json": "{}", "yarn.lock": "", ".yarnrc.yml": "" }, "yarn install --immutable", false],
    [
      "yarn",
      { "package.json": JSON.stringify({ packageManager: "yarn@4.5.0" }), "yarn.lock": "" },
      "yarn install --immutable",
      false,
    ],
    [
      "yarn",
      { "package.json": JSON.stringify({ packageManager: "yarn@1.22.22" }), "yarn.lock": "" },
      "yarn install --frozen-lockfile",
      false,
    ],
    ["yarn", { "package.json": JSON.stringify({ packageManager: "yarn@4.5.0" }) }, "yarn install", false],
    ["pnpm", { "package.json": "{}", "pnpm-lock.yaml": "" }, "pnpm install --frozen-lockfile", true],
    [
      "pnpm",
      { "package.json": JSON.stringify({ packageManager: "pnpm@9.1.0" }), "pnpm-lock.yaml": "" },
      "pnpm install --frozen-lockfile",
      false,
    ],
    ["bun", { "package.json": "{}", "bun.lockb": "" }, "bun install --frozen-lockfile", false],
  ];
  for (const [name, files, install, versioned] of rows) {
    const answer = ciInstall(managers[name], project(files));
    assert.equal(answer.install, install, `${name} ${JSON.stringify(files)}`);
    assert.equal(answer.setup.includes("version: latest"), versioned, `${name} ${JSON.stringify(files)}`);
  }
});

test("the closing verify step runs through the manager", async () => {
  const root = project({ "package.json": PINNED, "pnpm-lock.yaml": "" }, { linked: true });
  const result = await run(["--yes", "--project-root", root]);
  assert.ok(result.stdout.includes("run `pnpm exec akmon verify --strict` and review the diff"), result.stdout);
});

test("an existing workflow is left alone and the step names the manager's commands; --no-ci names them too", async () => {
  const existing = project(
    { "package.json": PINNED, "pnpm-lock.yaml": "", ".github/workflows/ci.yaml": "name: CI\n" },
    { linked: true },
  );
  const result = await run(["--yes", "--project-root", existing]);
  assert.equal(result.status, 0);
  assert.ok(!fs.existsSync(posix.join(existing, ".github/workflows/akmon.yml")));
  assert.ok(
    result.stdout.includes(
      "add the contract checks to your existing workflow(s): `pnpm exec akmon sync --check` and `pnpm exec akmon verify --strict`",
    ),
  );
  const skipped = project({ "package.json": PINNED }, { linked: true });
  const noCi = await run(["--yes", "--no-ci", "--project-root", skipped]);
  assert.equal(noCi.status, 0);
  assert.ok(!fs.existsSync(posix.join(skipped, ".github", "workflows")));
  assert.ok(
    noCi.stdout.includes("add the contract checks to CI: `npx akmon sync --check` and `npx akmon verify --strict`"),
  );
});

// -- the refusals ------------------------------------------------------------------------------

/**
 * The refusal of a first attach the Python implementation serves (C129).
 * @param {string} why a key of `node_refuses_python_why`
 * @param {string} mode
 * @returns {string}
 */
function pythonRefusal(why, mode) {
  const command = `uvx --from git+${data.akmon_repo}@${tagForVersion(VERSION)} akmon init --mode ${mode}`;
  return `akmon init: ${data.node_refuses_python_ecosystem
    .replace("{{why}}", data.node_refuses_python_why[why])
    .replace("{{command}}", command)}\n`;
}

test("a mounted first attach of a repository that is not package.json-only is the Python implementation's", async () => {
  for (const mode of ["submodule", "vendored", "subtree"]) {
    /** @type {Record<string, string>[]} */
    const cases = [
      { "package.json": PINNED, "pyproject.toml": "[project]\n" },
      { "setup.py": "" },
      // C129, owner accepted (a): a requirements file or a Python source beside package.json is Python
      { "package.json": PINNED, "requirements.txt": "" },
      { "package.json": PINNED, "app/x.py": "" },
    ];
    for (const files of cases) {
      const root = project(files, { linked: true });
      const result = await run(["--mode", mode, "--yes", "--project-root", root]);
      assert.deepEqual(
        { status: result.status, stdout: result.stdout, stderr: result.stderr },
        { status: 2, stdout: "", stderr: pythonRefusal("inferred", mode) },
      );
      assert.deepEqual(Object.keys(snapshot(root)).sort(), Object.keys(files).sort());
    }
  }
});

test("a git-tracked Python source makes the repository Python, an untracked one does not", async () => {
  const root = project({ "package.json": PINNED, "app/x.py": "" }, { linked: true });
  git(["init", "-q", "-b", "main"], root);
  assert.equal(firstAttachEcosystem(root, undefined, "vendored", "_aitna").ecosystem, "node", "untracked");
  git(["add", "--", "app/x.py"], root);
  assert.equal(firstAttachEcosystem(root, undefined, "vendored", "_aitna").ecosystem, "python", "tracked");
  assert.equal(
    firstAttachEcosystem(project({ "package.json": PINNED }), undefined, "vendored", "_aitna").ecosystem,
    "node",
  );
});

test("--ecosystem python is the Python implementation's in package mode too; --ecosystem node overrides the manifests", async () => {
  const root = project({ "package.json": PINNED }, { linked: true });
  const python = await run(["--ecosystem", "python", "--yes", "--project-root", root]);
  assert.deepEqual(python, { status: 2, stdout: "", stderr: pythonRefusal("flag", "package") });
  const mixed = project({ "package.json": "{}", "pyproject.toml": "[project]\n" });
  const node = mountedCli([
    "--mode",
    "vendored",
    "--ecosystem",
    "node",
    "--checks",
    "none",
    "--yes",
    "--project-root",
    mixed,
  ]);
  assert.equal(node.status, 0, node.stdout + node.stderr);
  assert.ok(text(mixed, "_aitna/.akmon.toml").includes('mount = "vendored"\necosystem = "node"\n'));
  const bad = await run(["--ecosystem", "ruby", "--project-root", root]);
  assert.equal(bad.status, 2);
  assert.equal(
    bad.stderr,
    "akmon init: error: argument --ecosystem: invalid choice: 'ruby' (choose from 'python', 'node')\n",
  );
});

test("a Node record does not move back: --ecosystem python on it is refused", async () => {
  const record = 'mount = "package"\necosystem = "node"\n';
  const root = project({ "package.json": PINNED, "_aitna/.akmon.toml": record }, { linked: true });
  const result = await run(["--ecosystem", "python", "--yes", "--project-root", root]);
  assert.deepEqual(result, {
    status: 2,
    stdout: "",
    stderr: `akmon init: ${data.node_refuses_reverse.replace("{{aitna}}", "_aitna")}\n`,
  });
  assert.equal(text(root, "_aitna/.akmon.toml"), record);
});

test("a record that does not name ecosystem node is refused, naming what it holds and, for a Python mount in a Node repository, the switch", async () => {
  const mountSwitch = "node _aitna/akmon/js/akmon/cli.mjs init --ecosystem node";
  /** @type {Array<[string, string, Record<string, string>, string | null]>} */
  const cases = [
    ['mount = "submodule"\n', 'ecosystem = "python"', {}, mountSwitch],
    // a vendored copy switches through npx at the newer of the recorded and the running release
    [
      'mount = "vendored"\necosystem = "python"\nakmon_version = "0.3.0"\n',
      'ecosystem = "python"',
      {},
      `npx github:akumidv/ai_akmon#${switchTag("0.3.0", VERSION)} init --ecosystem node`,
    ],
    [
      'mount = "vendored"\necosystem = "python"\nakmon_version = "99.0.0"\n',
      'ecosystem = "python"',
      {},
      "npx github:akumidv/ai_akmon#v99.0.0 init --ecosystem node",
    ],
    ['mount = "subtree"\n', 'ecosystem = "python"', { "pyproject.toml": "" }, null],
    ['mount = "package"\n', 'ecosystem = "python"', {}, null],
    ['mount = "package"\necosystem = "python"\n', 'ecosystem = "python"', {}, null],
    ['mount = "submodule"\necosystem = "rust"\n', 'ecosystem = "rust"', {}, null],
  ];
  for (const [record, found, files, command] of cases) {
    const root = project({ "package.json": PINNED, "_aitna/.akmon.toml": record, ...files }, { linked: true });
    const result = await run(["--yes", "--project-root", root]);
    const suffix = command === null ? "" : data.node_refuses_record_switch.replace("{{command}}", command);
    assert.equal(result.status, 2, record);
    assert.equal(result.stdout, "");
    assert.equal(result.stderr, `akmon init: ${data["node_refuses_record"].replace("{{found}}", found)}${suffix}\n`);
    assert.equal(text(root, "_aitna/.akmon.toml"), record);
    assert.ok(!fs.existsSync(posix.join(root, "AGENTS.md")));
  }
});

test("--ecosystem node moves a mounted Python record only, between two mounted modes", async () => {
  /** @type {Array<[string, string[], string, string]>} */
  const cases = [
    ['mount = "package"\n', [], "package", "package"],
    ['mount = "vendored"\n', ["--mode", "package", "--switch-mode"], "vendored", "package"],
  ];
  for (const [record, flags, previous, mode] of cases) {
    const root = project({ "package.json": PINNED, "_aitna/.akmon.toml": record }, { linked: true });
    const result = await run(["--ecosystem", "node", ...flags, "--yes", "--project-root", root]);
    const refusal = data.node_switch_mounted_only.replace("{{previous}}", previous).replace("{{mode}}", mode);
    assert.deepEqual(result, { status: 2, stdout: "", stderr: `akmon init: ${refusal}\n` });
    assert.equal(text(root, "_aitna/.akmon.toml"), record);
  }
});

test("nodeSwitchCommand: the mount's CLI for a submodule or a subtree, npx at the ref for a vendored copy", () => {
  assert.equal(
    nodeSwitchCommand(data, "_aitna", "submodule", "v1.0.0"),
    "node _aitna/akmon/js/akmon/cli.mjs init --ecosystem node",
  );
  assert.equal(
    nodeSwitchCommand(data, "dev", "subtree", "main"),
    "node dev/akmon/js/akmon/cli.mjs init --ecosystem node",
  );
  assert.equal(
    nodeSwitchCommand(data, "_aitna", "vendored", "v1.0.0"),
    "npx github:akumidv/ai_akmon#v1.0.0 init --ecosystem node",
  );
});

test("withoutRuffDefault cuts exactly the Python's ruff default out of a record, any run prefix, and nothing else", () => {
  const head = 'mount = "vendored"\n[test]\n# runner = "uv run pytest"\n\n';
  const table = (/** @type {string} */ entry) => `[check]\n${CHECK_HEADER.split("\n")[1]}\n${entry}\n`;
  for (const prefix of ["", "uv run ", "poetry run "]) {
    // the blank line before the table stays; `_recordChecks` trims the end before it appends
    assert.equal(withoutRuffDefault(data, head + table(`ruff = "${prefix}ruff check {files}"`)), head.slice(0, -1));
  }
  // a table followed by another one: only the table goes
  assert.equal(
    withoutRuffDefault(data, `${head}${table('ruff = "ruff check {files}"')}\n[extra]\nx = "1"\n`),
    `${head}[extra]\nx = "1"\n`,
  );
  for (const kept of [
    head,
    head + table('ruff = "ruff check --fix {files}"'),
    head + table('ruff = "pdm run ruff check {files}"'),
    `${head + table('ruff = "ruff check {files}"')}mypy = "mypy {files}"\n`,
    `${head}[check]\nruff = "ruff check {files}"\n`,
    `${head}[check]\n${CHECK_HEADER.split("\n")[1]}\n`,
    `${head + table('ruff = "ruff check {files}"')}[check.ruff]\nfiles = ["*.py"]\n`,
  ]) {
    assert.equal(withoutRuffDefault(data, kept), null, kept);
  }
});

test("a foreign record plus a mount-mode change is refused for the record, --switch-mode or not", async () => {
  // The twin of the Python init's ecosystem-before-switch order (C119): no migration advice.
  const record = 'mount = "submodule"\necosystem = "python"\n';
  for (const flags of [[], ["--switch-mode"]]) {
    const root = project({ "package.json": PINNED, "_aitna/.akmon.toml": record }, { linked: true });
    const result = await run(["--mode", "package", ...flags, "--yes", "--project-root", root]);
    assert.deepEqual(
      { status: result.status, stdout: result.stdout, stderr: result.stderr },
      {
        status: 2,
        stdout: "",
        stderr: `akmon init: ${data["node_refuses_record"].replace("{{found}}", 'ecosystem = "python"')}${data.node_refuses_record_switch.replace("{{command}}", "node _aitna/akmon/js/akmon/cli.mjs init --ecosystem node")}\n`,
      },
    );
    assert.equal(text(root, "_aitna/.akmon.toml"), record);
  }
});

const CHECK_HEADER =
  "[check]\n# What `akmon check` runs: the project's own commands, `{files}` becoming the files a run covers.\n";
// What `--checks none` records (C123): an empty `[check]` table, so a realign keeps the choice.
const EMPTY_CHECK = `\n\n${CHECK_HEADER}`;

test("--checks none records an empty [check] table and writes no oxlint configuration", async () => {
  const none = project({ "package.json": PINNED, "eslint.config.js": "" }, { linked: true });
  assert.equal((await run(["--checks", "none", "--yes", "--project-root", none])).status, 0);
  assert.ok(text(none, "_aitna/.akmon.toml").endsWith(EMPTY_CHECK));
  assert.ok(!fs.existsSync(posix.join(none, ".oxlintrc.json")));
});

test("a realign keeps --checks none: the --yes default does not set up akmon's rules", async () => {
  const none = project({ "package.json": PINNED }, { linked: true });
  assert.equal((await run(["--checks", "none", "--yes", "--project-root", none])).status, 0);
  const recorded = text(none, "_aitna/.akmon.toml");
  const again = await run(["--yes", "--project-root", none]);
  assert.equal(again.status, 0);
  assert.ok(again.stdout.includes("[check] already names this project's checks — left untouched\n"));
  assert.equal(text(none, "_aitna/.akmon.toml"), recorded);
  assert.ok(!fs.existsSync(posix.join(none, ".oxlintrc.json")));
});

test("--checks own with nothing found records an empty [check] table, and a realign keeps it", async () => {
  const own = project({ "package.json": PINNED }, { linked: true });
  const first = await run(["--checks", "own", "--yes", "--project-root", own]);
  assert.equal(first.status, 0);
  assert.ok(
    first.stdout.includes(
      "no linter configuration was found: name the project's checks under `[check]` in .akmon.toml",
    ),
  );
  const recorded = text(own, "_aitna/.akmon.toml");
  assert.ok(recorded.endsWith(EMPTY_CHECK));
  const again = await run(["--yes", "--project-root", own]);
  assert.equal(again.status, 0);
  assert.ok(again.stdout.includes("[check] already names this project's checks — left untouched\n"));
  assert.equal(text(own, "_aitna/.akmon.toml"), recorded);
  assert.ok(!fs.existsSync(posix.join(own, ".oxlintrc.json")));
});

// -- [check]: the project's own JS/TS tools ----------------------------------------------------

test("an explicit --checks decides an empty [check] table again; a table that names checks stays", async () => {
  const root = project({ "package.json": PINNED }, { linked: true });
  assert.equal((await run(["--checks", "none", "--yes", "--project-root", root])).status, 0);
  fs.writeFileSync(posix.join(root, "eslint.config.js"), "");
  const own = await run(["--checks", "own", "--yes", "--project-root", root]);
  assert.equal(own.status, 0, own.stderr);
  assert.ok(own.stdout.includes(`akmon init: ${data.checks_redecided_empty}\n`), own.stdout);
  const record = text(root, "_aitna/.akmon.toml");
  assert.equal(record.split("[check]").length, 2, "one table");
  assert.ok(record.includes('eslint = { command = "npx --no-install eslint {files}"'), record);
  const again = await run(["--checks", "none", "--yes", "--project-root", root]);
  assert.equal(again.status, 0);
  assert.ok(again.stdout.includes("[check] already names this project's checks — left untouched\n"));
  assert.equal(text(root, "_aitna/.akmon.toml"), record);
});

test("withoutEmptyChecks cuts only an empty single [check] table (the Python _without_empty_checks)", () => {
  const empty = `mount = "submodule"\n\n${CHECK_HEADER}`;
  assert.equal(withoutEmptyChecks(empty), 'mount = "submodule"\n');
  assert.equal(withoutEmptyChecks(`${empty}x = "y"\n`), null);
  assert.equal(withoutEmptyChecks(`${empty}[check.sub]\n`), null);
  assert.equal(withoutEmptyChecks('mount = "submodule"\n'), null);
});

const JS_TS = ["*.js", "*.mjs", "*.cjs", "*.jsx", "*.ts", "*.mts", "*.cts", "*.tsx"];

/** @param {Record<string, string>} files @returns {string[]} */
const detected = (files) => detectNodeTools(project(files)).map((tool) => tool.name);

test("detection reads every configuration spelling, in table order", () => {
  for (const name of ["js", "mjs", "cjs", "ts", "mts", "cts"]) {
    assert.deepEqual(detected({ [`eslint.config.${name}`]: "" }), ["eslint"], name);
  }
  assert.deepEqual(detected({ ".eslintrc": "" }), ["eslint"]);
  assert.deepEqual(detected({ ".eslintrc.json": "" }), ["eslint"]);
  assert.deepEqual(detected({ ".eslintrc.cjs": "" }), ["eslint"]);
  assert.deepEqual(detected({ "package.json": '{"eslintConfig":{}}' }), ["eslint"]);
  assert.deepEqual(detected({ "biome.json": "" }), ["biome"]);
  assert.deepEqual(detected({ "biome.jsonc": "" }), ["biome"]);
  assert.deepEqual(detected({ ".oxlintrc.json": "" }), ["oxlint"]);
  assert.deepEqual(detected({ ".prettierrc": "" }), ["prettier"]);
  assert.deepEqual(detected({ ".prettierrc.yaml": "" }), ["prettier"]);
  assert.deepEqual(detected({ "prettier.config.mjs": "" }), ["prettier"]);
  assert.deepEqual(detected({ "package.json": '{"prettier":{}}' }), ["prettier"]);
  assert.deepEqual(detected({ "tsconfig.json": "" }), ["tsc"]);
  // table order, whatever the order of the files; a package.json key joins the files' tools
  assert.deepEqual(
    detected({
      "tsconfig.json": "",
      ".oxlintrc.json": "",
      "biome.json": "",
      "package.json": '{"prettier":1,"eslintConfig":{}}',
    }),
    ["eslint", "biome", "oxlint", "prettier", "tsc"],
  );
  // nothing: no config, near-miss names, an unreadable or non-object manifest, a directory of that name
  assert.deepEqual(detected({}), []);
  assert.deepEqual(
    detected({ "eslint.config.json": "", ".eslintrcx": "", "prettier.configs": "", "package.json": "{bad" }),
    [],
  );
  assert.deepEqual(detected({ "package.json": "[1]" }), []);
  assert.deepEqual(detected({ "package.json": '{"scripts":{"lint":"x"}}' }), []);
  assert.deepEqual(detected({ "tsconfig.json/inner": "" }), []);
});

/**
 * The record of an attach of `files` (a pinned, linked project) run with `args`.
 * @param {Record<string, string>} files
 * @param {string[]} [args]
 */
async function attached(files, args = []) {
  const root = project({ "package.json": PINNED, ...files }, { linked: true });
  const result = await run([...args, "--yes", "--project-root", root]);
  return { root, result, record: text(root, "_aitna/.akmon.toml") };
}

test("the detected tools are recorded as [check] through the manager's run prefix, tsc as a plain string", async () => {
  const { result, record } = await attached({ "eslint.config.js": "", "tsconfig.json": "", "package-lock.json": "{}" });
  assert.equal(result.status, 0);
  assert.ok(result.stdout.includes("akmon init: recorded _aitna/.akmon.toml"));
  assert.ok(result.stdout.includes("akmon init: akmon check will run: eslint, tsc (recorded as [check])\n"));
  assert.ok(
    result.stdout.indexOf("(recorded as [check])") < result.stdout.indexOf("running sync"),
    "the [check] line comes before sync",
  );
  const files = JS_TS.map((pattern) => `"${pattern}"`).join(", ");
  assert.ok(
    record.includes(
      `\n${CHECK_HEADER}eslint = { command = "npx --no-install eslint {files}", files = [${files}] }\ntsc = "npx --no-install tsc --noEmit -p ."\n`,
    ),
    record,
  );
  assert.ok(record.includes('# runner = "npm test"\n\n[check]\n'));
  assert.ok(record.endsWith('tsc = "npx --no-install tsc --noEmit -p ."\n'));
});

test("every tool has its command and file set, and every manager its prefix", async () => {
  /** @type {[Record<string, string>, string][]} */
  const cases = [
    [
      { "biome.json": "", "pnpm-lock.yaml": "" },
      'biome = { command = "pnpm exec biome check {files}", files = [' +
        [...JS_TS, "*.json"].map((p) => `"${p}"`).join(", ") +
        "] }",
    ],
    [
      { ".oxlintrc.json": "", "yarn.lock": "" },
      'oxlint = { command = "yarn oxlint {files}", files = [' + JS_TS.map((p) => `"${p}"`).join(", ") + "] }",
    ],
    [
      { ".prettierrc": "", "bun.lock": "" },
      'prettier = { command = "bunx --no-install prettier --check {files}", files = [' +
        [...JS_TS, "*.json", "*.css", "*.md"].map((p) => `"${p}"`).join(", ") +
        "] }",
    ],
    [{ "tsconfig.json": "", "pnpm-lock.yaml": "" }, 'tsc = "pnpm exec tsc --noEmit -p ."'],
  ];
  for (const [files, line] of cases) {
    const { record } = await attached(files, ["--checks", "own"]);
    assert.ok(record.includes(`${CHECK_HEADER}${line}\n`), `${line}\n${record}`);
  }
});

test("the packageManager field picks the prefix over a lockfile", async () => {
  const { record } = await attached({
    "package.json": JSON.stringify({ packageManager: "pnpm@9.1.0", devDependencies: { akmon: VERSION } }),
    ".eslintrc.json": "{}",
    "package-lock.json": "{}",
  });
  assert.ok(record.includes('command = "pnpm exec eslint {files}"'));
});

test("the choice flow: own by default with a linter, none for --checks none, own with nothing found names a step, own with tsc records it", async () => {
  const found = await attached({ "eslint.config.js": "" });
  assert.ok(found.record.includes("eslint = "));
  assert.ok(!found.record.includes("oxlint"));

  const bare = await attached({}, ["--checks", "none"]);
  assert.ok(bare.record.endsWith(EMPTY_CHECK));
  assert.ok(bare.result.stdout.includes("akmon init: akmon check: no checks recorded\n"));
  assert.ok(bare.result.stdout.includes("name the project's checks under `[check]` in .akmon.toml when it has any"));

  const none = await attached({ "tsconfig.json": "" }, ["--checks", "none"]);
  assert.ok(none.record.endsWith(EMPTY_CHECK));
  assert.ok(none.result.stdout.includes("akmon check: no checks recorded"));

  const ownEmpty = await attached({}, ["--checks", "own"]);
  assert.equal(ownEmpty.result.status, 0);
  assert.ok(ownEmpty.record.endsWith(EMPTY_CHECK));
  assert.ok(!ownEmpty.result.stdout.includes("no checks recorded"));
  assert.ok(
    ownEmpty.result.stdout.includes(
      "no linter configuration was found: name the project's checks under `[check]` in .akmon.toml",
    ),
  );

  const own = await attached({ "tsconfig.json": "" }, ["--checks", "own"]);
  assert.ok(own.record.includes("[check]"));
});

const RULES = "./node_modules/akmon/profiles/oxlint.json";
const OXLINTRC = `{\n  "extends": ["${RULES}"],\n  "env": { "browser": true, "node": true }\n}\n`;
const JS_TS_LIST = JS_TS.map((pattern) => `"${pattern}"`).join(", ");
const OXLINT_RECORD = `oxlint = { command = "npx --no-install oxlint {files}", files = [${JS_TS_LIST}] }\n`;
const ENV_STEP =
  "narrow `env` in .oxlintrc.json to where the project's code runs (`node`, `browser`, …); oxlint does not read `/* global */` comments, so name globals under `globals`";
const INSTALL_STEP = "add oxlint as a development dependency so `akmon check` can run it: `npm install -D -E oxlint`";
// oxlint's `extends` does not carry `env` (M132), so the step for a project's own config names both.
const OWN_STEP = `.oxlintrc.json is the project's own: to run akmon's JavaScript/TypeScript rules, add \`"${RULES}"\` to its \`extends\` and give it an \`env\` naming where the project's code runs (\`node\`, \`browser\`, …) — \`extends\` does not carry \`env\``;

/**
 * An attach of `files` (a pinned, linked project) without `--yes`, run under `script` so stdin is a
 * terminal and `answers` are the owner's replies, one per line; `null` when there is no `script` binary.
 * @param {Record<string, string>} files
 * @param {string[]} answers
 * @returns {{status: number | null, stdout: string, record: string} | null}
 */
function answered(files, answers) {
  const root = project({ "package.json": PINNED, ...files }, { linked: true });
  const module = posix.join(TREE, "js", "akmon", "_init.mjs");
  const probe = spawnSync(
    "script",
    [
      "-qec",
      `node -e 'import(${JSON.stringify(module)}).then(m => m.main(["--project-root", ${JSON.stringify(root)}])).then(c => process.exit(c))'`,
      "/dev/null",
    ],
    { input: answers.map((answer) => `${answer}\n`).join(""), encoding: "utf8" },
  );
  if (probe.error) {
    return null; // no `script` binary: the terminal path cannot be driven here
  }
  return { status: probe.status, stdout: probe.stdout, record: text(root, "_aitna/.akmon.toml") };
}

const OWN_PROMPT = "`akmon check` runs the project's own eslint? [Y/n]";
const AKMON_PROMPT = "set up oxlint with akmon's JavaScript/TypeScript rules instead? [Y/n]";

test("at a terminal prompt, a linter found with its own declined and akmon's rules accepted records oxlint", (context) => {
  const akmon = answered({ "eslint.config.js": "" }, ["y", "n", "y"]);
  if (akmon === null) {
    context.skip("no `script` binary");
    return;
  }
  assert.equal(akmon.status, 0, akmon.stdout);
  assert.ok(akmon.stdout.includes(OWN_PROMPT) && akmon.stdout.includes(AKMON_PROMPT), akmon.stdout);
  assert.ok(akmon.record.endsWith(`\n${CHECK_HEADER}${OXLINT_RECORD}`), akmon.record);
});

test("at a terminal prompt, a linter found with both offers declined records an empty [check]", (context) => {
  const both = answered({ "eslint.config.js": "" }, ["y", "n", "n"]);
  if (both === null) {
    context.skip("no `script` binary");
    return;
  }
  assert.ok(both.stdout.includes(AKMON_PROMPT), both.stdout);
  assert.ok(both.stdout.includes("akmon init: akmon check: no checks recorded"), both.stdout);
  assert.ok(both.record.endsWith(EMPTY_CHECK), both.record);
});

test("at a terminal prompt, nothing found with akmon's rules declined records an empty [check]", (context) => {
  const nothing = answered({}, ["y", "n"]);
  if (nothing === null) {
    context.skip("no `script` binary");
    return;
  }
  assert.ok(nothing.stdout.includes("no JavaScript/TypeScript linter configured"), nothing.stdout);
  assert.ok(nothing.stdout.includes("akmon init: akmon check: no checks recorded"), nothing.stdout);
  assert.ok(nothing.record.endsWith(EMPTY_CHECK), nothing.record);
});

test("at a terminal prompt, only tsc and Prettier found with akmon's rules declined records them as the project's own", (context) => {
  const tools = answered({ "tsconfig.json": "", ".prettierrc": "" }, ["y", "n"]);
  if (tools === null) {
    context.skip("no `script` binary");
    return;
  }
  assert.ok(tools.stdout.includes("akmon check will run: prettier, tsc (recorded as [check])"), tools.stdout);
  assert.ok(tools.record.includes(`${CHECK_HEADER}prettier = `), tools.record);
  assert.ok(tools.record.endsWith('tsc = "npx --no-install tsc --noEmit -p ."\n'), tools.record);
  assert.ok(!tools.record.includes("oxlint"), tools.record);
});

test("with nothing detected the default is akmon: .oxlintrc.json written, oxlint recorded, both steps named", async () => {
  const { root, result, record } = await attached({});
  assert.equal(result.status, 0);
  assert.equal(text(root, ".oxlintrc.json"), OXLINTRC);
  assert.ok(record.endsWith(`\n${CHECK_HEADER}${OXLINT_RECORD}`), record);
  assert.ok(
    result.stdout.includes(
      `akmon init: wrote .oxlintrc.json extending akmon's JavaScript/TypeScript rules (${RULES})\n`,
    ),
  );
  assert.ok(result.stdout.includes("akmon init: akmon check will run: oxlint (recorded as [check])\n"));
  assert.ok(result.stdout.indexOf(ENV_STEP) < result.stdout.indexOf(INSTALL_STEP), "the extends step comes first");
});

test("akmon with tsconfig.json and Prettier detected records oxlint first, then prettier and tsc", async () => {
  const { result, record } = await attached({ "tsconfig.json": "", ".prettierrc": "" });
  const prettier = JS_TS.concat(["*.json", "*.css", "*.md"])
    .map((pattern) => `"${pattern}"`)
    .join(", ");
  assert.ok(result.stdout.includes("akmon check will run: oxlint, prettier, tsc (recorded as [check])\n"));
  assert.ok(
    record.endsWith(
      `${OXLINT_RECORD}prettier = { command = "npx --no-install prettier --check {files}", files = [${prettier}] }\n` +
        'tsc = "npx --no-install tsc --noEmit -p ."\n',
    ),
    record,
  );
});

test("an existing .oxlintrc.json without the rules is never edited: a step names the extends", async () => {
  const own = '{ "rules": {} }';
  const { root, result, record } = await attached({ ".oxlintrc.json": own }, ["--checks", "akmon"]);
  assert.equal(text(root, ".oxlintrc.json"), own);
  assert.ok(result.stdout.includes(OWN_STEP));
  assert.ok(!result.stdout.includes(ENV_STEP));
  assert.ok(record.includes(OXLINT_RECORD));
});

test("an .oxlintrc.json that already extends the rules is left alone, with no extends step", async () => {
  const own = `{ "extends": ["${RULES}"] }\n`;
  const { root, result } = await attached({ ".oxlintrc.json": own }, ["--checks", "akmon"]);
  assert.equal(text(root, ".oxlintrc.json"), own);
  assert.ok(!result.stdout.includes(OWN_STEP));
  assert.ok(!result.stdout.includes(ENV_STEP));
  assert.ok(result.stdout.includes(INSTALL_STEP));
});

test("a tsc-only project defaults to akmon; a project with a linter defaults to its own", async () => {
  const tsc = await attached({ "tsconfig.json": "" });
  assert.ok(tsc.result.stdout.includes("akmon check will run: oxlint, tsc (recorded as [check])\n"));
  assert.equal(text(tsc.root, ".oxlintrc.json"), OXLINTRC);
  const eslint = await attached({ "eslint.config.js": "", "tsconfig.json": "" });
  assert.ok(eslint.result.stdout.includes("akmon check will run: eslint, tsc (recorded as [check])\n"));
  assert.ok(!fs.existsSync(posix.join(eslint.root, ".oxlintrc.json")));
  const forced = await attached({ "eslint.config.js": "" }, ["--checks", "akmon"]);
  assert.ok(forced.result.stdout.includes("akmon check will run: oxlint (recorded as [check])\n"));
  assert.ok(!forced.record.includes("eslint"));
});

test("no install step when package.json already declares oxlint", async () => {
  for (const table of ["devDependencies", "dependencies"]) {
    const manifest = { devDependencies: { akmon: VERSION } };
    const declared = { ...manifest, [table]: { ...manifest.devDependencies, oxlint: "1.0.0" } };
    const { result } = await attached({ "package.json": JSON.stringify(declared) });
    assert.ok(!result.stdout.includes("add oxlint as a development dependency"), table);
    assert.ok(result.stdout.includes(ENV_STEP));
  }
});

test("a record that already has [check] is left untouched, with no scripts step", async () => {
  const first = await attached({
    "tsconfig.json": "",
    "package.json": JSON.stringify({ devDependencies: { akmon: VERSION }, scripts: { lint: "x" } }),
  });
  const root = first.root;
  const again = await run(["--yes", "--project-root", root]);
  assert.equal(again.status, 0);
  assert.ok(again.stdout.includes("[check] already names this project's checks — left untouched\n"));
  assert.ok(!again.stdout.includes("akmon check will run"));
  assert.ok(!again.stdout.includes("package.json scripts"));
  assert.equal(text(root, "_aitna/.akmon.toml").split("[check]").length, 2);
  // a hand-written [check] stops a different detection from rewriting it
  const hand = await attached({});
  fs.appendFileSync(posix.join(hand.root, "_aitna", ".akmon.toml"), '\n[check]\nmine = "make lint"\n');
  fs.writeFileSync(posix.join(hand.root, "biome.json"), "{}");
  const rerun = await run(["--yes", "--project-root", hand.root]);
  assert.ok(rerun.stdout.includes("left untouched"));
  assert.ok(!text(hand.root, "_aitna/.akmon.toml").includes("biome"));
});

test("package.json scripts lint and typecheck become one step, never a record, spelled per manager", async () => {
  const both = JSON.stringify({
    devDependencies: { akmon: VERSION },
    scripts: { lint: "a", typecheck: "b", test: "c" },
  });
  const none = await attached({ "package.json": both, "yarn.lock": "" }, ["--checks", "none"]);
  assert.ok(none.record.endsWith(EMPTY_CHECK));
  assert.ok(
    none.result.stdout.includes(
      "package.json scripts `lint`, `typecheck`: to have `akmon check` run them, name them under `[check]` in .akmon.toml (`yarn run lint`)",
    ),
  );
  const only = JSON.stringify({ devDependencies: { akmon: VERSION }, scripts: { typecheck: "b" } });
  const one = await attached({ "package.json": only, "bun.lock": "", "tsconfig.json": "" });
  assert.ok(one.record.includes("[check]"));
  assert.ok(!one.record.includes("typecheck"));
  assert.ok(one.result.stdout.includes("package.json scripts `typecheck`: to have `akmon check` run them"));
  assert.ok(one.result.stdout.includes("(`bun run typecheck`)"));
  const pnpm = await attached({ "package.json": both, "pnpm-lock.yaml": "" }, ["--checks", "none"]);
  assert.ok(pnpm.result.stdout.includes("(`pnpm run lint`)"));
  const neither = await attached({
    "package.json": JSON.stringify({ devDependencies: { akmon: VERSION }, scripts: { test: "c" } }),
  });
  assert.ok(!neither.result.stdout.includes("package.json scripts"));
});

test("usage errors are one line on stderr and exit 2; --switch-mode is accepted and does nothing", async () => {
  const root = project({ "package.json": PINNED }, { linked: true });
  const bad = await run(["--mode", "bogus", "--project-root", root]);
  assert.deepEqual(bad, {
    status: 2,
    stdout: "",
    stderr:
      "akmon init: error: argument --mode: invalid choice: 'bogus' (choose from 'submodule', 'vendored', 'subtree', 'package')\n",
  });
  const checks = await run(["--checks", "x", "--project-root", root]);
  assert.equal(
    checks.stderr,
    "akmon init: error: argument --checks: invalid choice: 'x' (choose from 'own', 'akmon', 'none')\n",
  );
  assert.equal((await run(["--nope"])).status, 2);
  assert.equal((await run(["stray"])).status, 2);
  const missing = await run(["--project-root", posix.join(root, "absent")]);
  assert.deepEqual(missing, {
    status: 2,
    stdout: "",
    stderr: `akmon init: ${posix.join(root, "absent")} is not a directory\n`,
  });
  const switched = await run(["--switch-mode", "--yes", "--project-root", root]);
  assert.equal(switched.status, 0);
  assert.ok(!snapshot(root)["AGENTS.md"].includes("--switch-mode"));
});

test("-h prints the usage and exits 0", async () => {
  const result = await run(["--help"]);
  assert.equal(result.status, 0);
  assert.ok(result.stdout.startsWith("usage: akmon init [-h]"));
  assert.equal(result.stderr, "");
  // --checks akmon is served on Node: the help names what each choice runs
  const checks = result.stdout.slice(result.stdout.indexOf("--checks {own,akmon,none}\n"));
  assert.match(checks, /oxlint with akmon's\s+JavaScript\/TypeScript rules \(default when it has\s+none\)/);
  assert.ok(!result.stdout.includes("not available"));
});

test("end of input at a terminal prompt is not confirmed: nothing is written, exit 1", () => {
  const root = project({ "package.json": PINNED }, { linked: true });
  const script = posix.join(TREE, "js", "akmon", "_init.mjs");
  // `script` gives the child a terminal; stdin at EOF makes the prompt read end of input
  const probe = spawnSync(
    "script",
    [
      "-qec",
      `node -e 'import(${JSON.stringify(script)}).then(m => m.main(["--project-root", ${JSON.stringify(root)}])).then(c => process.exit(c))'`,
      "/dev/null",
    ],
    {
      input: "",
      encoding: "utf8",
    },
  );
  if (probe.error) {
    return; // no `script` binary: the terminal path cannot be driven here
  }
  assert.match(probe.stdout, /attach akmon to .*\[Y\/n\] \r?\nakmon init: aborted/);
  assert.ok(!fs.existsSync(posix.join(root, "_aitna")));
  assert.equal(probe.status, 1);
});

test("--aitna-root and AITNA_ROOT are validated whichever way they arrive", async () => {
  const root = project({ "package.json": PINNED }, { linked: true });
  assert.equal(validatedAitnaRoot(" dev/ ", root), "dev");
  assert.equal(effectiveAitnaRoot(undefined, root), "_aitna");
  assert.equal(effectiveAitnaRoot("  ", root), "_aitna");
  assert.throws(
    () => validatedAitnaRoot("/tmp/escaped", root),
    /--aitna-root must be relative to the project root and stay inside it: '\/tmp\/escaped'/,
  );
  assert.throws(
    () => validatedAitnaRoot("../up", root),
    /must be relative to the project root and stay inside it: '\.\.\/up'/,
  );
  assert.throws(() => validatedAitnaRoot("a/../b", root), /stay inside it/);
  // a value of only slashes is absolute, as it is for `Path`; the "cannot be empty" branch is unreachable
  assert.throws(() => validatedAitnaRoot("///", root), /must be relative to the project root/);
  assert.throws(() => validatedAitnaRoot(".", root), /resolves outside the project root/);
  const outside = project();
  fs.symlinkSync(outside, posix.join(root, "leak"));
  assert.throws(() => validatedAitnaRoot("leak", root), new RegExp(`resolves outside the project root: ${outside}`));
  assert.equal(validatedAitnaRoot("x", root, "AITNA_ROOT"), "x");
  assert.throws(() => validatedAitnaRoot("../x", root, "AITNA_ROOT"), /^Error: AITNA_ROOT must be/);
});

// -- the attach --------------------------------------------------------------------------------

test("a first attach on a bare directory ends with exit 1 and the pin step first", async () => {
  const root = project();
  const result = await run(["--yes", "--project-root", root]);
  assert.equal(result.status, 1, result.stdout + result.stderr);
  assert.equal(result.stderr, "");
  const lines = result.stdout.split("\n");
  assert.equal(lines[0], `akmon init: attaching to ${root}`);
  assert.equal(
    lines[1],
    "akmon init: mount mode: package (the JavaScript implementation attaches in package mode) · dev layer: _aitna/",
  );
  const at = lines.indexOf("akmon init: attached, but INCOMPLETE:");
  assert.ok(at > 0);
  assert.ok(lines[at + 1].startsWith("  1. **pin akmon in `devDependencies`** of package.json at an exact version"));
  assert.ok(lines[at + 1].includes(`\`npm install -D -E akmon@${VERSION}\``));
  assert.ok(lines[at + 2].startsWith("  2. classify the project"));
  assert.equal(
    result.stdout.slice(result.stdout.indexOf("akmon init: exit 1")),
    "akmon init: exit 1: mode 'package' has no akmon pin in devDependencies yet (step 1) — nothing else attaches it, so this attach is not finished. " +
      "Re-run `akmon init` after adding it (it keeps the recorded mode), or `akmon verify --strict` to re-check.\n",
  );
  const record = text(root, "_aitna/.akmon.toml");
  assert.ok(record.startsWith("# akmon integration record"));
  assert.ok(
    record.includes(
      `mount = "package"\necosystem = "node"\nakmon_version = "${VERSION}"\nattached_archetype = "unclassified"\n`,
    ),
  );
  assert.ok(!record.includes("last_realign"), "an incomplete attach claims no completed realign");
  assert.ok(record.includes('# runner = "npm test"'));
});

test("the pin step follows the manager, and a runtime or unreadable manifest has its own step", async () => {
  const bare = project({ "pnpm-lock.yaml": "" });
  assert.ok((await run(["--yes", "--project-root", bare])).stdout.includes(`\`pnpm add -D -E akmon@${VERSION}\``));
  const bun = project({ "package.json": '{"packageManager":"bun@1.1.0"}' });
  assert.ok((await run(["--yes", "--project-root", bun])).stdout.includes(`\`bun add -d --exact akmon@${VERSION}\``));
  const runtime = project({ "package.json": JSON.stringify({ dependencies: { akmon: VERSION } }) }, { linked: true });
  const moved = await run(["--yes", "--project-root", runtime]);
  assert.equal(moved.status, 1);
  assert.ok(
    moved.stdout.includes(
      "  1. **move the akmon pin** out of `dependencies`, `optionalDependencies` or `peerDependencies`",
    ),
  );
  const broken = project({ "package.json": "{nope" });
  const unreadable = await run(["--yes", "--project-root", broken]);
  assert.equal(unreadable.status, 1);
  assert.ok(unreadable.stdout.includes("  1. **fix package.json** — it is not valid JSON"));
  assert.ok(unreadable.stdout.includes("cannot read an akmon pin: package.json is not valid JSON (step 1)"));
  assert.ok(unreadable.stdout.includes("Re-run `akmon init` after fixing it"));
});

test("an attach with a dev exact pin and the package linked completes: exit 0, ecosystem and last_realign recorded", async () => {
  const root = project({ "package.json": PINNED }, { linked: true });
  const result = await run(["--yes", "--archetype", "library", "--language", "javascript", "--project-root", root]);
  assert.equal(result.status, 0, result.stdout + result.stderr);
  assert.equal(result.stderr, "");
  assert.ok(result.stdout.includes("akmon init: attached, with steps left to a human/agent decision:\n"));
  assert.ok(!result.stdout.includes("INCOMPLETE"));
  assert.ok(!result.stdout.includes("classify the project"), "an archetype was given");
  assert.ok(
    result.stdout.includes("akmon init: running model-routing init (subagent definitions + local routing config)\n"),
  );
  const record = text(root, "_aitna/.akmon.toml");
  assert.ok(record.includes('mount = "package"\necosystem = "node"\n'));
  assert.ok(record.includes(`akmon_version = "${VERSION}"`));
  assert.ok(record.includes('attached_archetype = "library/javascript"'));
  assert.ok(record.includes(`last_realign = "${VERSION}"`));
  for (const generated of [
    ".claude/settings.json",
    "CLAUDE.md",
    ".claude/agents/k_explorer.md",
    ".claude/model-routing.local.json",
  ]) {
    assert.ok(fs.existsSync(posix.join(root, generated)), generated);
  }
  assert.ok(text(root, "_aitna/agents/engineer/README.md").includes("`akmon path` prints the standard's root"));
  assert.ok(text(root, "AGENTS.md").includes("`library` / `javascript`"));
  assert.ok(text(root, "AGENTS.md").includes("hooks run from `node_modules/akmon/js/hooks`"));
  assert.ok(text(root, "AGENTS.md").includes("`npx akmon path` locates the rest"));
  assert.equal(process.env.AITNA_ROOT, undefined, "the variable is given back");
});

test("the links of the AGENTS.md block name the standard repository at --ref (--repo changes nothing), else the tag of the installed version", async () => {
  const root = project({ "package.json": PINNED }, { linked: true });
  await run(["--yes", "--repo", "https://example.test/akmon", "--ref", "v9.9.9", "--project-root", root]);
  assert.ok(text(root, "AGENTS.md").includes(`(${data.akmon_repo}/blob/v9.9.9/MODEL.md)`));
  assert.ok(!text(root, "AGENTS.md").includes("example.test"));
  const plain = project({ "package.json": PINNED }, { linked: true });
  await run(["--yes", "--project-root", plain]);
  assert.ok(text(plain, "AGENTS.md").includes(`(${data.akmon_repo}/blob/${tagForVersion(VERSION)}/MODEL.md)`));
  assert.equal(tagForVersion("1.2.3"), "v1.2.3");
  assert.equal(tagForVersion("1.2.3-dev.0"), "main");
  assert.equal(tagForVersion("0.4.0.post1"), "main");
  assert.equal(tagForVersion(null), "main");
});

test("a re-run changes nothing and says what it left alone", async () => {
  const root = project({ "package.json": PINNED, "pnpm-lock.yaml": "" }, { linked: true });
  assert.equal((await run(["--yes", "--project-root", root])).status, 0);
  const before = snapshot(root);
  const again = await run(["--yes", "--project-root", root]);
  assert.equal(again.status, 0);
  assert.deepEqual(snapshot(root), before);
  assert.ok(again.stdout.includes("akmon init: mount mode: package (recorded) · dev layer: _aitna/\n"));
  assert.ok(again.stdout.includes("akmon init: AGENTS.md already carries an akmon block — left untouched\n"));
  assert.ok(!again.stdout.includes("akmon init: wrote "));
});

test("a hand-written record keeps its fields and a resolved archetype; the ecosystem is upserted", async () => {
  const record = `mount = "package"\necosystem = "node"\nattached_archetype = "service/ts"\n# mine\n[test]\nrunner = "pnpm vitest"\n`;
  const root = project({ "package.json": PINNED, "_aitna/.akmon.toml": record }, { linked: true });
  assert.equal((await run(["--yes", "--checks", "none", "--archetype", "other", "--project-root", root])).status, 0);
  const after = text(root, "_aitna/.akmon.toml");
  assert.ok(after.includes('attached_archetype = "service/ts"'));
  assert.ok(after.includes("# mine\n") && after.endsWith(`[test]\nrunner = "pnpm vitest"${EMPTY_CHECK}`));
  assert.ok(after.includes(`akmon_version = "${VERSION}"`) && after.includes(`last_realign = "${VERSION}"`));
});

test("a dev-layer root other than _aitna is used everywhere and named in the export step", async () => {
  const root = project({ "package.json": PINNED }, { linked: true });
  const result = await run(["--yes", "--aitna-root", "dev", "--project-root", root]);
  assert.equal(result.status, 0, result.stdout + result.stderr);
  assert.ok(fs.existsSync(posix.join(root, "dev", ".akmon.toml")));
  assert.ok(!fs.existsSync(posix.join(root, "_aitna")));
  assert.ok(result.stdout.includes("export AITNA_ROOT=dev in every shell and CI job that runs the akmon tooling"));
  assert.equal(process.env.AITNA_ROOT, undefined);
});

// -- AGENTS.md and .gitignore ------------------------------------------------------------------

test("an existing AGENTS.md without the block gains it appended; with the block it is untouched", async () => {
  const without = project({ "package.json": PINNED, "AGENTS.md": "# Mine\n\nHand-written.\n" }, { linked: true });
  const appended = await run(["--yes", "--project-root", without]);
  assert.ok(
    appended.stdout.includes("akmon init: appended the akmon block to AGENTS.md (existing content preserved)\n"),
  );
  const agents = text(without, "AGENTS.md");
  assert.ok(agents.startsWith("# Mine\n\nHand-written.\n\n"));
  assert.ok(agents.includes("(developing the project)"));

  const withBlock = project({ "package.json": PINNED }, { linked: true });
  await run(["--yes", "--project-root", withBlock]);
  const written = text(withBlock, "AGENTS.md");
  const edited = `${written}\nHand edit.\n`;
  fs.writeFileSync(posix.join(withBlock, "AGENTS.md"), edited);
  const again = await run(["--yes", "--project-root", withBlock]);
  assert.equal(text(withBlock, "AGENTS.md"), edited);
  assert.ok(again.stdout.includes("AGENTS.md already carries an akmon block — left untouched"));
  assert.ok(again.stdout.includes("`akmon verify --strict` checks the existing AGENTS.md block against the contract"));
});

test(".gitignore gains only the lines it lacks, with no dev-layer venv block and a node_modules entry", async () => {
  const root = project({ "package.json": PINNED, ".gitignore": "dist/\nnode_modules/\n*.env\n" }, { linked: true });
  const result = await run(["--yes", "--project-root", root]);
  assert.ok(
    result.stdout.includes(
      "akmon init: .gitignore: added the akmon entries (secrets, Node dependencies, routing artifacts)\n",
    ),
  );
  const ignore = text(root, ".gitignore");
  assert.ok(ignore.startsWith("dist/\nnode_modules/\n*.env\n\n"));
  assert.equal(ignore.split("\n").filter((line) => line === "node_modules/").length, 1);
  assert.equal(ignore.split("\n").filter((line) => line === "*.env").length, 1);
  assert.ok(ignore.includes("!*.env.example\n") && ignore.includes(".claude/agents/k_*.md\n"));
  assert.ok(!/\.venv|venv/.test(ignore));
  const fresh = project({ "package.json": PINNED }, { linked: true });
  await run(["--yes", "--project-root", fresh]);
  assert.ok(
    text(fresh, ".gitignore").startsWith(
      "# secrets\n*.env\n!*.env.example\n\n# Node dependencies\nnode_modules/\n\n# akmon model routing",
    ),
  );
});

test("mergeGitignore appends verbatim, collapses blanks, and returns the text itself when nothing is missing", () => {
  const wanted = ["# a", "x", "", "# b", "y"];
  assert.equal(mergeGitignore("", wanted), "# a\nx\n\n# b\ny\n");
  assert.equal(mergeGitignore("keep", wanted), "keep\n\n# a\nx\n\n# b\ny\n");
  assert.equal(mergeGitignore("keep\n\n", wanted), "keep\n\n# a\nx\n\n# b\ny\n");
  assert.equal(mergeGitignore("# a\nx\n\n# b\ny\n", wanted), "# a\nx\n\n# b\ny\n");
  assert.equal(mergeGitignore("# a\n  x  \n# b\n", wanted), "# a\n  x  \n# b\n\ny\n");
  assert.equal(mergeGitignore("x\ny", ["x", "", "y"]), "x\ny");
  // Unicode line breaks split as str.splitlines does; CRLF counts as one
  assert.equal(mergeGitignore("x\r\ny\r\n", ["x", "y", "z"]), "x\r\ny\r\n\nz\n");
  assert.equal(mergeGitignore("x\u2028y", ["x", "y", "z"]), "x\u2028y\n\nz\n");
});

// -- the real process --------------------------------------------------------------------------

/**
 * @param {string[]} args
 * @param {string} input
 */
function spawnCli(args, input) {
  const env = { ...process.env };
  delete env.AITNA_ROOT;
  const result = spawnSync(process.execPath, [CLI, "init", ...args], { env, input, encoding: "utf8" });
  return { status: result.status, stdout: result.stdout, stderr: result.stderr };
}

test("without --yes a stdin that is not a terminal confirms, as the Python does: the attach is not aborted", () => {
  for (const input of ["", "n\n", "y\n"]) {
    const root = project({ "package.json": PINNED }, { linked: true });
    const result = spawnCli(["--project-root", root], input);
    assert.equal(result.status, 0, result.stdout + result.stderr);
    assert.equal(result.stderr, "");
    assert.ok(!result.stdout.includes("[Y/n]"));
    assert.ok(fs.existsSync(posix.join(root, "_aitna", ".akmon.toml")));
  }
});

test("run as a process the stdout is the in-process stdout, and sync's lines come between init's", () => {
  const root = project({ "package.json": PINNED }, { linked: true });
  const result = spawnCli(["--yes", "--project-root", root], "");
  assert.equal(result.status, 0);
  const lines = result.stdout.split("\n");
  const sync = lines.indexOf("akmon init: running sync (generated pointers, hook wiring, imported guardrails)");
  const routing = lines.indexOf("akmon init: running model-routing init (subagent definitions + local routing config)");
  assert.ok(sync > 0 && routing > sync + 1);
  assert.ok(lines[sync + 1].startsWith("updated: ") || lines[sync + 1].startsWith("ok: "));
});

// -- the language-profile imports (C127) -------------------------------------------------------

test("the detected profiles follow the flags and the manifests, python first, none for an unknown language", () => {
  assert.deepEqual(detectedProfiles(project(), undefined, undefined), []);
  assert.deepEqual(detectedProfiles(project(), "custom", "rust"), []);
  assert.deepEqual(detectedProfiles(project(), "package", "python"), ["python.md"]);
  assert.deepEqual(detectedProfiles(project(), undefined, "TypeScript"), ["js.md"]);
  assert.deepEqual(detectedProfiles(project({ "package.json": "{}" }), undefined, undefined), ["js.md"]);
  assert.deepEqual(detectedProfiles(project({ "package.json": "{}", "pyproject.toml": "[project]\n" }), "", ""), [
    "python.md",
    "js.md",
  ]);
});

test("a fresh block imports js.md after the common guardrail and keeps no classify step once classified", async () => {
  const root = project({ "package.json": PINNED }, { linked: true });
  const result = await run(["--yes", "--archetype", "library", "--project-root", root]);
  assert.equal(result.status, 0, result.stdout + result.stderr);
  assert.ok(text(root, "AGENTS.md").includes("@_aitna/.akmon/guardrails/_common.md\n@_aitna/.akmon/profiles/js.md\n"));
  assert.ok(text(root, "AGENTS.md").includes("`@_aitna/.akmon/profiles/<name>.md`"));
  assert.ok(!result.stdout.includes("classify the project"));
  assert.ok(fs.existsSync(posix.join(root, "_aitna/.akmon/profiles/js.md")), "sync materialized the import");
});

test("a fresh block imports both profiles when both manifests are present, python first", async () => {
  const root = project({ "package.json": PINNED, "pyproject.toml": '[project]\nname = "demo"\n' }, { linked: true });
  const result = await run(["--yes", "--checks", "none", "--project-root", root]);
  assert.equal(result.status, 0, result.stdout + result.stderr);
  assert.ok(
    text(root, "AGENTS.md").includes(
      "@_aitna/.akmon/guardrails/_common.md\n@_aitna/.akmon/profiles/python.md\n@_aitna/.akmon/profiles/js.md\n",
    ),
  );
  assert.ok(result.stdout.includes("classify the project's archetype against ARCHETYPES.md"), "still unclassified");
  assert.ok(!result.stdout.includes("import the language profile"), "init already imported it (C127)");
});

test("a bare directory gets no profile import and keeps the classify step", async () => {
  const root = project();
  const result = await run(["--yes", "--project-root", root]);
  assert.ok(text(root, "AGENTS.md").includes("@_aitna/.akmon/guardrails/_common.md\n\n"));
  assert.ok(!/^@\S*profiles\//m.test(text(root, "AGENTS.md")));
  assert.ok(result.stdout.includes("classify the project (archetype + language)"));
  assert.ok(result.stdout.includes("import the language profile in AGENTS.md"));
});

// -- the mounted modes (C129) ------------------------------------------------------------------

/**
 * `init` run as a process with git's `file://` transport allowed for submodules (refused since
 * CVE-2022-39253 unless set) — in the test's own environment, never in the shipped code.
 * @param {string[]} args
 * @param {string} [cwd]
 */
function mountedCli(args, cwd = os.tmpdir()) {
  /** @type {NodeJS.ProcessEnv} */
  const env = {
    ...process.env,
    GIT_CONFIG_COUNT: "1",
    GIT_CONFIG_KEY_0: "protocol.file.allow",
    GIT_CONFIG_VALUE_0: "always",
  };
  delete env.AITNA_ROOT;
  const result = spawnSync(process.execPath, [CLI, "init", ...args], { env, cwd, encoding: "utf8" });
  return { status: result.status, stdout: result.stdout, stderr: result.stderr };
}

/**
 * @param {string[]} args
 * @param {string} cwd
 */
function git(args, cwd) {
  const result = spawnSync("git", ["-c", "user.name=t", "-c", "user.email=t@t", ...args], { cwd, encoding: "utf8" });
  assert.equal(result.status, 0, result.stderr);
  return result.stdout.trim();
}

/**
 * A local standard repository: the running tree's members (what a vendored Node copy holds),
 * recorded once per entry of `tags`, each under that tag, one revision apart; `edit` changes the
 * tree before a tag is recorded.
 * @param {string[]} tags
 * @param {(repo: string, tag: string) => void} [edit]
 * @returns {string}
 */
function standardRepo(tags, edit = () => {}) {
  const repo = fs.realpathSync(fs.mkdtempSync(posix.join(os.tmpdir(), "akmon-standard-")));
  for (const name of [...data.tree_members, ...data.tree_members_node]) {
    if (fs.existsSync(posix.join(TREE, name))) {
      fs.cpSync(posix.join(TREE, name), posix.join(repo, name), {
        recursive: true,
        filter: (source) => !/(?:^|\/)(?:__pycache__|node_modules)(?:\/|$)/.test(source),
      });
    }
  }
  git(["init", "-q", "-b", "main"], repo);
  tags.forEach((tag, index) => {
    fs.appendFileSync(posix.join(repo, "CHANGELOG.md"), `\n<!-- ${index} -->\n`);
    edit(repo, tag);
    git(["add", "-A"], repo);
    git(["commit", "-q", "-m", tag], repo);
    git(["tag", tag], repo);
  });
  return repo;
}

/**
 * A Node consumer that is a git repository: `package.json` and no Python files.
 * @returns {string}
 */
function nodeRepository() {
  const root = project({ "package.json": JSON.stringify({ name: "demo", private: true }) });
  git(["init", "-q", "-b", "main"], root);
  return root;
}

test("vendored: the mount carries the standard, the CLI data and package.json; the mount's CLI verifies it green", () => {
  const root = nodeRepository();
  const result = mountedCli(["--mode", "vendored", "--yes", "--project-root", root]);
  assert.equal(result.status, 0, result.stdout + result.stderr);
  const count = [...data.tree_members, ...data.tree_members_node].filter((name) =>
    fs.existsSync(posix.join(TREE, name)),
  ).length;
  assert.ok(result.stdout.includes(`vendored ${count} standard-tree members into _aitna/akmon (pin: ${VERSION})`));
  for (const member of [
    "package.json",
    "src/akmon/init.json",
    "src/akmon/cli.json",
    "js/akmon/cli.mjs",
    ".gitignore",
  ]) {
    assert.ok(fs.existsSync(posix.join(root, "_aitna/akmon", member)), member);
  }
  assert.ok(!fs.existsSync(posix.join(root, "_aitna/akmon/js/akmon/cli.test.mjs")), "tests stay out of the mount");
  assert.ok(!fs.existsSync(posix.join(root, "_aitna/akmon/meta")));
  assert.ok(
    text(root, "_aitna/.akmon.toml").includes(`mount = "vendored"\necosystem = "node"\nakmon_version = "${VERSION}"\n`),
  );
  const agents = text(root, "AGENTS.md");
  assert.ok(agents.includes("@_aitna/akmon/guardrails/_common.md\n@_aitna/akmon/profiles/js.md\n"));
  assert.ok(agents.includes("[`MODEL.md`](_aitna/akmon/MODEL.md)") && agents.includes("SHARED = `_aitna/akmon/`"));
  assert.ok(text(root, "_aitna/agents/review/README.md").includes("(_aitna/akmon/roles/review.md)"));
  const workflow = text(root, ".github/workflows/akmon.yml");
  assert.ok(workflow.includes("submodules: recursive\n      - uses: actions/setup-node@v4\n"));
  assert.ok(workflow.includes("      - run: node _aitna/akmon/js/akmon/cli.mjs sync --check\n"));
  assert.ok(workflow.includes("      - run: node _aitna/akmon/js/akmon/cli.mjs verify --strict"));
  assert.ok(text(root, ".claude/settings.json").includes('_aitna/akmon/js/hooks/role-on-code.mjs\\"'));
  assert.equal(JSON.parse(text(root, ".oxlintrc.json")).extends[0], "./_aitna/akmon/profiles/oxlint.json");
  assert.ok(result.stdout.includes("run `node _aitna/akmon/js/akmon/cli.mjs verify --strict` and review the diff"));
  assert.ok(result.stdout.includes('`"akmon": "node _aitna/akmon/js/akmon/cli.mjs"`'), "the script is offered");
  assert.ok(!result.stdout.includes("devDependencies"), "a mounted attach needs no manifest pin");
  assert.ok(!fs.existsSync(posix.join(root, "_aitna/.akmon")), "nothing is materialized");
  const verify = spawnSync(
    process.execPath,
    [posix.join(root, "_aitna/akmon", "js/akmon/cli.mjs"), "verify", "--quiet"],
    { cwd: root, encoding: "utf8" },
  );
  assert.equal(verify.status, 0, verify.stdout + verify.stderr);
});

test("vendored: the mount's own CLI realigns in place instead of copying over itself; --ref is refused", () => {
  const root = nodeRepository();
  assert.equal(mountedCli(["--mode", "vendored", "--yes", "--project-root", root]).status, 0);
  const own = spawnSync(process.execPath, [posix.join(root, "_aitna/akmon", "js/akmon/cli.mjs"), "init", "--yes"], {
    cwd: root,
    encoding: "utf8",
  });
  assert.equal(own.status, 0, own.stdout + own.stderr);
  assert.ok(own.stdout.includes(`_aitna/akmon is the tree this CLI runs from — nothing to copy (pin: ${VERSION})`));
  assert.ok(fs.existsSync(posix.join(root, "_aitna/akmon/js/akmon/cli.mjs")), "the mount survived");
  const ref = mountedCli(["--ref", "v1.0.0", "--yes", "--project-root", root]);
  assert.equal(ref.status, 2);
  assert.ok(
    ref.stderr.includes(`its pin is that package's version (${VERSION}) and \`--ref v1.0.0\` cannot change it`),
  );
});

test("submodule: added at the newest release tag, staged as checked out; the mount's CLI generates, with the skew notice", () => {
  const repo = standardRepo(["v9.0.0", "v9.1.0rc1"]);
  const root = nodeRepository();
  const result = mountedCli([
    "--mode",
    "submodule",
    "--repo",
    repo,
    "--checks",
    "none",
    "--yes",
    "--project-root",
    root,
  ]);
  assert.equal(result.status, 0, result.stdout + result.stderr);
  assert.ok(result.stdout.includes(`akmon init: git submodule add ${repo} _aitna/akmon\n`));
  assert.ok(result.stdout.includes("akmon init: pinned _aitna/akmon at v9.0.0\n"), "a release candidate is no release");
  assert.ok(
    result.stderr.includes(`akmon: CLI is ${VERSION}, mounted/pinned standard is v9.0.0 — the mounted tree governs.\n`),
  );
  assert.ok(
    text(root, "_aitna/.akmon.toml").includes('mount = "submodule"\necosystem = "node"\nakmon_version = "v9.0.0"\n'),
  );
  assert.equal(
    git(["ls-files", "--stage", "--", "_aitna/akmon"], root).split(/\s+/)[1],
    git(["rev-parse", "v9.0.0^{commit}"], repo),
  );
  assert.ok(fs.existsSync(posix.join(root, ".gitmodules")));
  const again = mountedCli(["--yes", "--project-root", root]);
  assert.equal(again.status, 0, again.stdout + again.stderr);
  assert.ok(again.stdout.includes("akmon init: _aitna/akmon is already mounted — realigning\n"));
  assert.ok(again.stdout.includes("akmon init: _aitna/akmon left at its current pin (pass --ref to move it)\n"));
});

test("submodule: a pin move by the mount's own CLI generates with the code of the new pin, not the loaded one", () => {
  // The later tag's sync prints a line when it is loaded: only a process started after the
  // checkout runs it — the CLI that moves the pin has the earlier tag's sync in memory.
  const marker = "sync of the moved pin loaded";
  const repo = standardRepo(["v9.0.0", "v9.1.0"], (tree, tag) => {
    if (tag === "v9.1.0") {
      fs.appendFileSync(posix.join(tree, "js/bin/sync.mjs"), `\nprocess.stdout.write("${marker}\\n");\n`);
    }
  });
  const root = nodeRepository();
  const first = mountedCli([
    "--mode",
    "submodule",
    "--repo",
    repo,
    "--ref",
    "v9.0.0",
    "--checks",
    "none",
    "--yes",
    "--project-root",
    root,
  ]);
  assert.equal(first.status, 0, first.stdout + first.stderr);
  assert.ok(!first.stdout.includes(marker));
  const own = posix.join(root, "_aitna/akmon", "js/akmon/cli.mjs");
  const moved = spawnSync(process.execPath, [own, "init", "--ref", "v9.1.0", "--yes"], { cwd: root, encoding: "utf8" });
  assert.equal(moved.status, 0, moved.stdout + moved.stderr);
  assert.ok(moved.stdout.includes("akmon init: moved _aitna/akmon to v9.1.0 — left unstaged\n"), moved.stdout);
  assert.ok(moved.stdout.includes(`${marker}\n`), moved.stdout);
  assert.ok(text(root, "_aitna/.akmon.toml").includes('akmon_version = "v9.1.0"\n'));
});

test("subtree: the command that records history is printed with the mount's CLI, and nothing is written", () => {
  const repo = standardRepo(["v9.0.0"]);
  const root = nodeRepository();
  const result = mountedCli(["--mode", "subtree", "--repo", repo, "--yes", "--project-root", root]);
  assert.equal(result.status, 2);
  assert.ok(
    result.stderr.endsWith(
      `    git subtree add --prefix _aitna/akmon ${repo} v9.0.0 --squash\n` +
        "    node _aitna/akmon/js/akmon/cli.mjs init --mode subtree --ref v9.0.0\n",
    ),
    result.stderr,
  );
  assert.deepEqual(fs.readdirSync(root).sort(), [".git", "package.json"]);
});

test("--ecosystem node moves a Python-vendored mount: the copy gains the CLI data, the record, [check] and the wiring change, ruff.toml stays", () => {
  const root = nodeRepository();
  // What the Python init vendors: `tree_members` only, so the mount's own cli.mjs cannot run.
  for (const name of data.tree_members) {
    if (fs.existsSync(posix.join(TREE, name))) {
      fs.cpSync(posix.join(TREE, name), posix.join(root, "_aitna/akmon", name), { recursive: true });
    }
  }
  const ruff = fill(readSyncData().sync.ruff_toml_template, { rules_path: "_aitna/akmon/profiles/ruff.toml" });
  const record = `mount = "vendored"\nakmon_version = "0.3.0"\n\n[check]\n${CHECK_HEADER.split("\n")[1]}\nruff = "uv run ruff check {files}"\n`;
  const python = 'python3 \\"$CLAUDE_PROJECT_DIR/_aitna/akmon/hooks/git-commit-guard.py\\"';
  fs.mkdirSync(posix.join(root, "_aitna"), { recursive: true });
  fs.writeFileSync(posix.join(root, "_aitna/.akmon.toml"), record);
  fs.writeFileSync(posix.join(root, "ruff.toml"), ruff);
  fs.mkdirSync(posix.join(root, ".claude"));
  fs.writeFileSync(
    posix.join(root, ".claude/settings.json"),
    `{"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "${python}"}]}]}}\n`,
  );
  const result = mountedCli(["--ecosystem", "node", "--yes", "--project-root", root]);
  assert.equal(result.status, 0, result.stdout + result.stderr);
  assert.ok(result.stdout.includes(`${fill(data.node_switch_log, { aitna: "_aitna" })}\n`));
  assert.ok(result.stdout.includes(`${data.node_switch_checks_redecided}\n`));
  assert.ok(fs.existsSync(posix.join(root, "_aitna/akmon/src/akmon/init.json")), "the copy gained the CLI data");
  const written = text(root, "_aitna/.akmon.toml");
  assert.ok(written.includes('ecosystem = "node"\n') && !written.includes("ruff check"), written);
  assert.ok(written.includes('oxlint = { command = "npx --no-install oxlint {files}"'), written);
  assert.equal(text(root, "ruff.toml"), ruff, "ruff.toml is never deleted");
  const settings = text(root, ".claude/settings.json");
  assert.ok(!settings.includes("python3") && settings.includes("_aitna/akmon/js/hooks/git-commit-guard.mjs"), settings);
  assert.ok(text(root, ".codex/hooks.json").includes("_aitna/akmon/js/hooks/codex-hook.mjs"));
  assert.ok(result.stdout.includes(`. ${data.node_switch_codex_step}\n`));
  assert.ok(result.stdout.includes(`. ${data.node_switch_ruff_step}\n`));
  // a realign is no move: no switch line, no Codex or ruff step, [check] left alone
  const again = mountedCli(["--yes", "--project-root", root]);
  assert.equal(again.status, 0, again.stdout + again.stderr);
  assert.ok(!again.stdout.includes(data.node_switch_codex_step) && !again.stdout.includes(data.node_switch_ruff_step));
  assert.ok(again.stdout.includes("[check] already names this project's checks — left untouched"));
});

/**
 * Every file under `root` with its bytes, `.git` left out.
 * @param {string} root
 * @returns {Record<string, string>}
 */
function tree(root) {
  /** @type {Record<string, string>} */
  const files = {};
  for (const entry of fs.readdirSync(root, { recursive: true, withFileTypes: true })) {
    const path = posix.relative(root, posix.join(entry.parentPath, entry.name));
    if (entry.isFile() && !path.split("/").includes(".git")) {
      files[path] = fs.readFileSync(posix.join(root, path), "latin1");
    }
  }
  return files;
}

test("--ecosystem node refuses a subtree mount that predates the switch, naming the update first, and writes nothing", () => {
  const root = nodeRepository();
  const record = 'mount = "subtree"\necosystem = "python"\nakmon_version = "99.0.0"\n';
  fs.mkdirSync(posix.join(root, "_aitna/akmon/src/akmon"), { recursive: true });
  fs.mkdirSync(posix.join(root, "_aitna/akmon/bin"), { recursive: true });
  fs.writeFileSync(posix.join(root, "_aitna/.akmon.toml"), record);
  fs.writeFileSync(posix.join(root, "_aitna/akmon/src/akmon/init.json"), "{}\n");
  fs.writeFileSync(posix.join(root, "_aitna/akmon/bin/sync.json"), '{"node_cli": {}}\n');
  const before = tree(root);
  const result = mountedCli(["--ecosystem", "node", "--ref", "v99.0.0", "--yes", "--project-root", root]);
  assert.equal(result.status, 2, result.stdout + result.stderr);
  const refusal = fill(data.node_switch_mount_predates, {
    relative: "_aitna/akmon",
    file: "src/akmon/init.json",
    key: "node_switch_log",
    ref: "v99.0.0",
    update: `git subtree pull --prefix _aitna/akmon ${data.akmon_repo} v99.0.0 --squash`,
    command: "node _aitna/akmon/js/akmon/cli.mjs init --ecosystem node --ref v99.0.0",
  });
  assert.equal(result.stderr, `akmon init: ${refusal}\n`);
  assert.equal(result.stdout, "");
  assert.deepEqual(tree(root), before, "no file changed");
});

test("--ecosystem node checks a submodule at the --ref it moves to: an older tag is refused before the checkout", () => {
  const repo = standardRepo(["v9.0.0", "v9.1.0"], (standard, tag) => {
    const init = posix.join(standard, "src/akmon/init.json");
    const parsed = JSON.parse(fs.readFileSync(posix.join(TREE, "src/akmon/init.json"), "utf8"));
    if (tag === "v9.0.0") {
      delete parsed.node_switch_log;
    }
    fs.writeFileSync(init, `${JSON.stringify(parsed, null, 2)}\n`);
  });
  const root = nodeRepository();
  const first = mountedCli([
    "--mode",
    "submodule",
    "--repo",
    repo,
    "--ref",
    "v9.1.0",
    "--checks",
    "none",
    "--yes",
    "--project-root",
    root,
  ]);
  assert.equal(first.status, 0, first.stdout + first.stderr);
  // what the Python implementation records for the same mount
  fs.writeFileSync(
    posix.join(root, "_aitna/.akmon.toml"),
    'mount = "submodule"\necosystem = "python"\nakmon_version = "v9.1.0"\n',
  );
  const before = tree(root);
  const head = git(["rev-parse", "HEAD"], posix.join(root, "_aitna/akmon"));
  const result = mountedCli([
    "--ecosystem",
    "node",
    "--ref",
    "v9.0.0",
    "--repo",
    repo,
    "--yes",
    "--project-root",
    root,
  ]);
  assert.equal(result.status, 2, result.stdout + result.stderr);
  assert.ok(
    result.stderr.includes(
      "_aitna/akmon predates the move to this implementation (src/akmon/init.json there has no `node_switch_log`)",
    ),
    result.stderr,
  );
  assert.ok(
    result.stderr.includes("    git -C _aitna/akmon fetch --tags && git -C _aitna/akmon checkout v9.1.0\n"),
    result.stderr,
  );
  assert.deepEqual(tree(root), before, "no file changed");
  assert.equal(git(["rev-parse", "HEAD"], posix.join(root, "_aitna/akmon")), head, "the mount did not move");
  // at a release that has the switch, it completes
  const moved = mountedCli(["--ecosystem", "node", "--yes", "--project-root", root]);
  assert.equal(moved.status, 0, moved.stdout + moved.stderr);
  assert.ok(text(root, "_aitna/.akmon.toml").includes('ecosystem = "node"\n'));
});

test("a mount-mode migration needs --switch-mode, and the old mount gone between two mounted modes", () => {
  const root = nodeRepository();
  assert.equal(mountedCli(["--mode", "vendored", "--yes", "--project-root", root]).status, 0);
  const plain = mountedCli(["--mode", "submodule", "--yes", "--project-root", root]);
  assert.equal(plain.status, 2);
  assert.ok(plain.stderr.includes("this project is attached in mount mode 'vendored'; 'submodule' is a **migration**"));
  assert.ok(plain.stderr.includes("`node _aitna/akmon/js/akmon/cli.mjs verify --strict` red"));
  const flagged = mountedCli(["--mode", "submodule", "--switch-mode", "--yes", "--project-root", root]);
  assert.equal(flagged.status, 2);
  assert.ok(
    flagged.stderr.endsWith("    node _aitna/akmon/js/akmon/cli.mjs init --mode submodule --switch-mode\n"),
    flagged.stderr,
  );
  assert.ok(text(root, "_aitna/.akmon.toml").includes('mount = "vendored"'), "unchanged");
});

test("npxSpec and shellWord spell the hand-over commands as the Python does", () => {
  assert.equal(npxSpec("https://github.com/akumidv/ai_akmon", "v1.0.0"), "github:akumidv/ai_akmon#v1.0.0");
  assert.equal(npxSpec("https://github.com/akumidv/ai_akmon.git", "v1.0.0"), "github:akumidv/ai_akmon#v1.0.0");
  assert.equal(npxSpec("/srv/akmon", "v1.0.0"), "git+file:///srv/akmon#v1.0.0");
  assert.equal(npxSpec("ssh://git@example.org/akmon.git", "v1.0.0"), "git+ssh://git@example.org/akmon.git#v1.0.0");
  assert.equal(shellWord("github:akumidv/ai_akmon#v1.0.0"), "github:akumidv/ai_akmon#v1.0.0");
  assert.equal(shellWord("a b"), "'a b'");
});

test("newestReleaseTag takes final v-tags only, ordered numerically", () => {
  assert.equal(newestReleaseTag(["v0.9.0", "v0.10.0", "v1.0.0rc1", "1.2.0", "v0.10.0-3-gabc"]), "v0.10.0");
  assert.equal(newestReleaseTag(["main", "v1.0.0.dev0"]), null);
});
