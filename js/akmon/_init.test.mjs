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

import { ciInstall, detectManager, effectiveAitnaRoot, main, mergeGitignore, readInitData, tagForVersion, validatedAitnaRoot } from "./_init.mjs";

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
  process.stdout.write = /** @type {typeof process.stdout.write} */ ((/** @type {string} */ text) => (out.push(text), true));
  process.stderr.write = /** @type {typeof process.stderr.write} */ ((/** @type {string} */ text) => (err.push(text), true));
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
  const add = Object.fromEntries(Object.entries(data.node_managers).map(([name, manager]) => [name, manager.add_dev_exact]));
  assert.deepEqual(add, {
    pnpm: "pnpm add -D -E", yarn: "yarn add -D -E", bun: "bun add -d --exact", npm: "npm install -D -E",
  });
});

// -- the CI workflow ---------------------------------------------------------------------------

/** The workflow each manager gets. */
const WORKFLOWS = {
  npm: ["actions/setup-node@v4", "node-version: 22", "run: npm ci", "run: npx akmon sync --check", "run: npx akmon verify --strict"],
  pnpm: ["pnpm/action-setup@v4", "actions/setup-node@v4", "run: pnpm install --frozen-lockfile", "run: pnpm exec akmon sync --check", "run: pnpm exec akmon verify --strict"],
  yarn: ["actions/setup-node@v4", "run: yarn install --frozen-lockfile", "run: yarn akmon sync --check", "run: yarn akmon verify --strict"],
  bun: ["oven-sh/setup-bun@v2", "run: bun install --frozen-lockfile", "run: bunx akmon sync --check", "run: bunx akmon verify --strict"],
};
const LOCKFILES = { npm: "package-lock.json", pnpm: "pnpm-lock.yaml", yarn: "yarn.lock", bun: "bun.lock" };

for (const [manager, lines] of Object.entries(WORKFLOWS)) {
  test(`the ${manager} attach writes the ${manager} workflow and no Python anywhere`, async () => {
    const root = project({ "package.json": PINNED, [LOCKFILES[/** @type {keyof typeof LOCKFILES} */ (manager)]]: "" }, { linked: true });
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
    ["yarn", { "package.json": JSON.stringify({ packageManager: "yarn@4.5.0" }), "yarn.lock": "" }, "yarn install --immutable", false],
    ["yarn", { "package.json": JSON.stringify({ packageManager: "yarn@1.22.22" }), "yarn.lock": "" }, "yarn install --frozen-lockfile", false],
    ["yarn", { "package.json": JSON.stringify({ packageManager: "yarn@4.5.0" }) }, "yarn install", false],
    ["pnpm", { "package.json": "{}", "pnpm-lock.yaml": "" }, "pnpm install --frozen-lockfile", true],
    ["pnpm", { "package.json": JSON.stringify({ packageManager: "pnpm@9.1.0" }), "pnpm-lock.yaml": "" }, "pnpm install --frozen-lockfile", false],
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
  const existing = project({ "package.json": PINNED, "pnpm-lock.yaml": "", ".github/workflows/ci.yaml": "name: CI\n" }, { linked: true });
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
  assert.ok(noCi.stdout.includes("add the contract checks to CI: `npx akmon sync --check` and `npx akmon verify --strict`"));
});

// -- the refusals ------------------------------------------------------------------------------

test("a mode other than package is refused with exit 2 and one line, before anything is written", async () => {
  for (const mode of ["submodule", "vendored", "subtree"]) {
    const root = project({ "package.json": PINNED }, { linked: true });
    const result = await run(["--mode", mode, "--yes", "--project-root", root]);
    assert.deepEqual(
      { status: result.status, stdout: result.stdout, stderr: result.stderr },
      { status: 2, stdout: "", stderr: `akmon init: ${data["node_refuses_mode"].replace("{{mode}}", mode)}\n` },
    );
    assert.deepEqual(Object.keys(snapshot(root)), ["package.json"]);
  }
});

test("a record that is not Node package mode is refused, naming what it holds", async () => {
  const cases = [
    ['mount = "submodule"\n', 'mount = "submodule"'],
    ['mount = "vendored"\necosystem = "node"\n', 'mount = "vendored"'],
    ['mount = "package"\n', 'ecosystem = "python"'],
    ['mount = "package"\necosystem = "python"\n', 'ecosystem = "python"'],
    ['ecosystem = "node"\n', 'mount = "submodule"'],
  ];
  for (const [record, found] of cases) {
    const root = project({ "package.json": PINNED, "_aitna/.akmon.toml": record }, { linked: true });
    const result = await run(["--yes", "--project-root", root]);
    assert.equal(result.status, 2, record);
    assert.equal(result.stdout, "");
    assert.equal(result.stderr, `akmon init: ${data["node_refuses_record"].replace("{{found}}", found)}\n`);
    assert.equal(text(root, "_aitna/.akmon.toml"), record);
    assert.ok(!fs.existsSync(posix.join(root, "AGENTS.md")));
  }
});

test("--checks own and --checks akmon are refused; --checks none and no flag record nothing", async () => {
  for (const choice of ["own", "akmon"]) {
    const root = project({ "package.json": PINNED }, { linked: true });
    const result = await run(["--checks", choice, "--yes", "--project-root", root]);
    assert.equal(result.status, 2);
    assert.equal(result.stdout, "");
    assert.equal(result.stderr, `akmon init: ${data["node_checks_pending"].replace("{{choice}}", choice)}\n`);
    assert.deepEqual(Object.keys(snapshot(root)), ["package.json"]);
  }
  for (const args of [["--checks", "none"], []]) {
    const root = project({ "package.json": PINNED }, { linked: true });
    assert.equal((await run([...args, "--yes", "--project-root", root])).status, 0);
    assert.ok(!text(root, "_aitna/.akmon.toml").includes("[check]"));
  }
});

test("usage errors are one line on stderr and exit 2; --switch-mode is accepted and does nothing", async () => {
  const root = project({ "package.json": PINNED }, { linked: true });
  const bad = await run(["--mode", "bogus", "--project-root", root]);
  assert.deepEqual(bad, {
    status: 2,
    stdout: "",
    stderr: "akmon init: error: argument --mode: invalid choice: 'bogus' (choose from 'submodule', 'vendored', 'subtree', 'package')\n",
  });
  const checks = await run(["--checks", "x", "--project-root", root]);
  assert.equal(checks.stderr, "akmon init: error: argument --checks: invalid choice: 'x' (choose from 'own', 'akmon', 'none')\n");
  assert.equal((await run(["--nope"])).status, 2);
  assert.equal((await run(["stray"])).status, 2);
  const missing = await run(["--project-root", posix.join(root, "absent")]);
  assert.deepEqual(missing, { status: 2, stdout: "", stderr: `akmon init: ${posix.join(root, "absent")} is not a directory\n` });
  const switched = await run(["--switch-mode", "--yes", "--project-root", root]);
  assert.equal(switched.status, 0);
  assert.ok(!snapshot(root)["AGENTS.md"].includes("--switch-mode"));
});

test("-h prints the usage and exits 0", async () => {
  const result = await run(["--help"]);
  assert.equal(result.status, 0);
  assert.ok(result.stdout.startsWith("usage: akmon init [-h]"));
  assert.equal(result.stderr, "");
});

test("--aitna-root and AITNA_ROOT are validated whichever way they arrive", async () => {
  const root = project({ "package.json": PINNED }, { linked: true });
  assert.equal(validatedAitnaRoot(" dev/ ", root), "dev");
  assert.equal(effectiveAitnaRoot(undefined, root), "_aitna");
  assert.equal(effectiveAitnaRoot("  ", root), "_aitna");
  assert.throws(() => validatedAitnaRoot("/tmp/escaped", root), /--aitna-root must be relative to the project root and stay inside it: '\/tmp\/escaped'/);
  assert.throws(() => validatedAitnaRoot("../up", root), /must be relative to the project root and stay inside it: '\.\.\/up'/);
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
  assert.ok(record.startsWith('# akmon integration record'));
  assert.ok(record.includes(`mount = "package"\necosystem = "node"\nakmon_version = "${VERSION}"\nattached_archetype = "unclassified"\n`));
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
  assert.ok(moved.stdout.includes("  1. **move the akmon pin** out of `dependencies`, `optionalDependencies` or `peerDependencies`"));
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
  assert.ok(result.stdout.includes("akmon init: running model-routing init (subagent definitions + local routing config)\n"));
  const record = text(root, "_aitna/.akmon.toml");
  assert.ok(record.includes('mount = "package"\necosystem = "node"\n'));
  assert.ok(record.includes(`akmon_version = "${VERSION}"`));
  assert.ok(record.includes('attached_archetype = "library/javascript"'));
  assert.ok(record.includes(`last_realign = "${VERSION}"`));
  for (const generated of [".claude/settings.json", "CLAUDE.md", ".claude/agents/k_explorer.md", ".claude/model-routing.local.json"]) {
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
  assert.equal((await run(["--yes", "--archetype", "other", "--project-root", root])).status, 0);
  const after = text(root, "_aitna/.akmon.toml");
  assert.ok(after.includes('attached_archetype = "service/ts"'));
  assert.ok(after.includes("# mine\n") && after.endsWith("[test]\nrunner = \"pnpm vitest\"\n"));
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
  assert.ok(appended.stdout.includes("akmon init: appended the akmon block to AGENTS.md (existing content preserved)\n"));
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
  assert.ok(result.stdout.includes("akmon init: .gitignore: added the akmon entries (secrets, Node dependencies, routing artifacts)\n"));
  const ignore = text(root, ".gitignore");
  assert.ok(ignore.startsWith("dist/\nnode_modules/\n*.env\n\n"));
  assert.equal(ignore.split("\n").filter((line) => line === "node_modules/").length, 1);
  assert.equal(ignore.split("\n").filter((line) => line === "*.env").length, 1);
  assert.ok(ignore.includes("!*.env.example\n") && ignore.includes(".claude/agents/k_*.md\n"));
  assert.ok(!/\.venv|venv/.test(ignore));
  const fresh = project({ "package.json": PINNED }, { linked: true });
  await run(["--yes", "--project-root", fresh]);
  assert.ok(text(fresh, ".gitignore").startsWith("# secrets\n*.env\n!*.env.example\n\n# Node dependencies\nnode_modules/\n\n# akmon model routing"));
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
  assert.equal(mergeGitignore("x y", ["x", "y", "z"]), "x y\n\nz\n");
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
