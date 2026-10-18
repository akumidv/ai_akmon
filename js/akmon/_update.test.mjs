/**
 * node:test for `js/akmon/_update.mjs` — the Node package-mode `akmon update`: the plan (the six
 * notes, the SemVer development spelling), the registry target, each manager's exact pin command,
 * the printed command where akmon does not drive the manager or cannot run it, every refusal, the
 * launcher `init` and checks, and the closing steps. The manager and the registry are stand-ins
 * (`UpdateDeps`); the byte-level spec is the `cli/update-*` scenarios of `meta/conformance/scenarios`.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import { posix } from "node:path";
import { fileURLToPath } from "node:url";

import { main, moveCommand, newestRelease, pinSpec, plan, readUpdateData } from "./_update.mjs";
import { readInitData } from "./_init.mjs";

const TREE = posix.resolve(posix.dirname(fileURLToPath(import.meta.url)), "..", "..");
const CLI = posix.join(TREE, "js", "akmon", "cli.mjs");
const LAUNCHER_TAIL = "node_modules/akmon/js/akmon/cli.mjs";
const data = readUpdateData();
const managers = readInitData().node_managers;

const RECORD = 'mount = "package"\necosystem = "node"\nakmon_version = "0.4.0"\nlast_realign = "0.4.0"\n';

/**
 * A Node project (links resolved): `package.json` pinning akmon in `devDependencies`, the Node
 * record, `node_modules/akmon` on the running tree — each replaceable through `files` (`null` drops one).
 * @param {Record<string, string | null>} [files]
 * @param {{linked?: boolean}} [options]
 * @returns {string}
 */
function project(files = {}, { linked = true } = {}) {
  const root = fs.realpathSync(fs.mkdtempSync(posix.join(os.tmpdir(), "akmon-update-")));
  /** @type {Record<string, string | null>} */
  const all = {
    "package.json": JSON.stringify({ name: "demo", devDependencies: { akmon: "0.4.0" } }),
    "_aitna/.akmon.toml": RECORD,
    ...files,
  };
  for (const [relative, text] of Object.entries(all)) {
    if (text === null) {
      continue;
    }
    fs.mkdirSync(posix.dirname(posix.join(root, relative)), { recursive: true });
    fs.writeFileSync(posix.join(root, relative), text);
  }
  if (linked) {
    fs.mkdirSync(posix.join(root, "node_modules"), { recursive: true });
    fs.symlinkSync(TREE, posix.join(root, "node_modules", "akmon"));
  }
  return root;
}

/**
 * Stand-ins for the manager, the registry and PATH; every command run is recorded.
 * @param {{codes?: (argv: string[]) => number, registry?: string | null, path?: string[]}} [options]
 */
function deps({ codes = () => 0, registry = null, path = ["npm", "pnpm", "yarn", "bun"] } = {}) {
  /** @type {string[][]} */
  const ran = [];
  /** @type {string[][]} */
  const asked = [];
  return {
    ran,
    asked,
    run(/** @type {string[]} */ argv) {
      ran.push(argv);
      return codes(argv);
    },
    capture(/** @type {string[]} */ argv) {
      asked.push(argv);
      return registry;
    },
    onPath: (/** @type {string} */ name) => path.includes(name),
  };
}

/**
 * Run `main(args, stand-ins)` with both streams captured and `AITNA_ROOT` unset.
 * @param {string[]} args
 * @param {ReturnType<typeof deps>} stand
 */
function run(args, stand) {
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
    return { status: main(args, stand), stdout: out.join(""), stderr: err.join("") };
  } finally {
    process.stdout.write = write.out;
    process.stderr.write = write.err;
    if (saved !== undefined) {
      process.env.AITNA_ROOT = saved;
    }
  }
}

/** The relative tail of each command a stand-in ran past the manager: `init`, `sync`, `verify`. */
const launched = (/** @type {string[][]} */ ran) =>
  ran.filter((argv) => argv[0] === process.execPath && argv[1].endsWith(LAUNCHER_TAIL)).map((argv) => argv[2]);

// -- the plan ----------------------------------------------------------------------------------

test("the plan takes the Python's six branches, with the same notes", () => {
  const notes = data.plan_notes;
  assert.deepEqual(plan(data, "0.4.0", "v0.5.0", { explicit: false }), {
    target: "v0.5.0",
    current: "0.4.0",
    move: true,
    note: "0.4.0 → v0.5.0",
  });
  assert.equal(plan(data, "0.5.0", "v0.5.0", { explicit: false }).note, "already at v0.5.0 — realigning only");
  assert.equal(plan(data, "0.5.0", "v0.5.0", { explicit: false }).move, false);
  assert.deepEqual(
    [plan(data, "0.6.0", "0.5.0", { explicit: true }).move, plan(data, "0.6.0", "0.5.0", { explicit: true }).note],
    [true, "rolling back 0.6.0 → 0.5.0, as --ref asks"],
  );
  const past = plan(data, "0.6.0", "0.5.0", { explicit: false });
  assert.deepEqual(
    [past.move, past.note],
    [false, "0.6.0 is past the newest release 0.5.0 — the pin stays; pass --ref to move it"],
  );
  assert.equal(
    plan(data, "0.4.0", "latest", { explicit: true }).note,
    notes.not_a_release.replace("{{target}}", "latest"),
  );
  assert.equal(
    plan(data, null, "0.5.0", { explicit: false }).note,
    "moving to 0.5.0 — the record names no comparable version (none)",
  );
});

test("a SemVer development version sorts as its PEP 440 twin: before the release and its candidates", () => {
  assert.equal(plan(data, "0.5.0-dev.0", "0.5.0", { explicit: false }).move, true);
  assert.equal(plan(data, "0.5.0-dev.0", "0.5.0-rc.1", { explicit: true }).note, "0.5.0-dev.0 → 0.5.0-rc.1");
  assert.equal(plan(data, "0.5.0-dev.0", "v0.5.0-dev.0", { explicit: true }).move, false);
});

test("the newest release is the highest final version; a pre-release never is", () => {
  assert.equal(newestRelease(["0.9.0", "0.10.0", "0.11.0-dev.0", "0.10.1-rc.1"]), "0.10.0");
  assert.equal(newestRelease(["0.4.0-dev.0"]), null);
  assert.equal(newestRelease([]), null);
});

test("each manager's exact dev install pins the bare version", () => {
  assert.equal(pinSpec("v0.5.0"), "akmon@0.5.0");
  assert.equal(pinSpec("0.5.0"), "akmon@0.5.0");
  assert.equal(pinSpec("latest"), "akmon@latest");
  assert.deepEqual(moveCommand(managers.npm, "akmon@0.5.0"), ["npm", "install", "-D", "-E", "akmon@0.5.0"]);
  assert.deepEqual(moveCommand(managers.pnpm, "akmon@0.5.0"), ["pnpm", "add", "-D", "-E", "akmon@0.5.0"]);
  assert.deepEqual(moveCommand(managers.yarn, "akmon@0.5.0"), ["yarn", "add", "-D", "-E", "akmon@0.5.0"]);
  assert.deepEqual(moveCommand(managers.bun, "akmon@0.5.0"), ["bun", "add", "-d", "--exact", "akmon@0.5.0"]);
});

// -- the move ----------------------------------------------------------------------------------

test("the pin moves with the detected manager, then the pinned CLI runs init, sync --check, verify --strict", () => {
  /** @type {[Record<string, string>, string[]][]} */
  const cases = [
    [{}, ["npm", "install", "-D", "-E", "akmon@0.5.0"]],
    [{ "pnpm-lock.yaml": "" }, ["pnpm", "add", "-D", "-E", "akmon@0.5.0"]],
    [{ "yarn.lock": "" }, ["yarn", "add", "-D", "-E", "akmon@0.5.0"]],
    [{ "bun.lock": "" }, ["bun", "add", "-d", "--exact", "akmon@0.5.0"]],
    [
      { "package.json": JSON.stringify({ packageManager: "pnpm@9.1.0", devDependencies: { akmon: "0.4.0" } }) },
      ["pnpm", "add", "-D", "-E", "akmon@0.5.0"],
    ],
  ];
  for (const [files, command] of cases) {
    const root = project(files);
    const stand = deps();
    const result = run(["--ref", "v0.5.0", "--project-root", root], stand);
    assert.equal(result.status, 0, result.stderr);
    assert.deepEqual(stand.ran[0], command);
    assert.deepEqual(launched(stand.ran), ["init", "sync", "verify"]);
    assert.deepEqual(stand.ran[1].slice(2), ["init", "--project-root", root, "--yes"]);
    assert.deepEqual(stand.ran[2].slice(2), ["sync", "--check", "--project-root", root]);
    assert.deepEqual(stand.ran[3].slice(2), ["verify", "--strict", "--project-root", root]);
    assert.deepEqual(stand.asked, []);
    assert.ok(result.stdout.startsWith(`akmon update: ${root} · mount mode package · 0.4.0 → v0.5.0\n`));
    assert.ok(result.stdout.includes(`akmon update: moving the pin: ${command.join(" ")}\n`));
    fs.rmSync(root, { recursive: true, force: true });
  }
});

test("an older --ref is an announced rollback and moves the pin back", () => {
  const root = project();
  const stand = deps();
  const result = run(["--ref", "0.3.0", "--project-root", root], stand);
  assert.equal(result.status, 0);
  assert.ok(result.stdout.includes("rolling back 0.4.0 → 0.3.0, as --ref asks"));
  assert.deepEqual(stand.ran[0], ["npm", "install", "-D", "-E", "akmon@0.3.0"]);
  fs.rmSync(root, { recursive: true, force: true });
});

test("without --ref the target is the newest final release the registry lists, asked in the project", () => {
  const root = project();
  const stand = deps({ registry: '["0.3.0", "0.5.0", "0.6.0-dev.0"]\n' });
  const result = run(["--project-root", root], stand);
  assert.equal(result.status, 0);
  assert.deepEqual(stand.asked, [["npm", "view", "akmon", "versions", "--json"]]);
  assert.deepEqual(stand.ran[0], ["npm", "install", "-D", "-E", "akmon@0.5.0"]);
  // npm prints a lone version as a string.
  const lone = deps({ registry: '"0.4.0"\n' });
  const realign = run(["--project-root", root], lone);
  assert.equal(realign.status, 0);
  assert.ok(realign.stdout.includes("already at 0.4.0 — realigning only"));
  assert.deepEqual(launched(lone.ran), ["init", "sync", "verify"]);
  assert.equal(lone.ran.length, 3);
  fs.rmSync(root, { recursive: true, force: true });
});

test("without --ref the pin never moves back: a record past the newest release is realigned in place", () => {
  const root = project({ "_aitna/.akmon.toml": RECORD.replaceAll("0.4.0", "0.6.0") });
  const stand = deps({ registry: '["0.5.0"]' });
  const result = run(["--project-root", root], stand);
  assert.equal(result.status, 0);
  assert.ok(result.stdout.includes("0.6.0 is past the newest release 0.5.0 — the pin stays; pass --ref to move it"));
  assert.deepEqual(launched(stand.ran), ["init", "sync", "verify"]);
  fs.rmSync(root, { recursive: true, force: true });
});

test("a registry that cannot be asked, or lists no release, is refused naming --ref", () => {
  const root = project();
  for (const [registry, text] of [
    [null, data.node_registry_unreachable],
    ["not json", data.node_registry_unreachable],
    ['{"error": 1}', data.node_registry_unreachable],
    ['["0.5.0-dev.0"]', data.node_registry_no_release],
  ]) {
    const stand = deps({ registry });
    assert.deepEqual(run(["--project-root", root], stand), {
      status: 2,
      stdout: "",
      stderr: `akmon update: ${text}\n`,
    });
    assert.deepEqual(stand.ran, []);
  }
  fs.rmSync(root, { recursive: true, force: true });
});

test("a manager akmon does not drive gets the command printed, and nothing runs", () => {
  const root = project({
    "package.json": JSON.stringify({ packageManager: "deno@2.0.0", devDependencies: { akmon: "0.4.0" } }),
  });
  const stand = deps();
  const result = run(["--ref", "v0.5.0", "--project-root", root], stand);
  assert.equal(result.status, 2);
  assert.equal(
    result.stderr,
    'akmon update: package.json names packageManager "deno@2.0.0", a manager akmon does not drive. Point the pin at ' +
      "akmon@0.5.0 with it and install, then run `akmon init`; with npm:\n    npm install -D -E akmon@0.5.0\n",
  );
  assert.deepEqual(stand.ran, []);
  fs.rmSync(root, { recursive: true, force: true });
});

test("a manager that is not on PATH gets its command printed, and nothing runs", () => {
  const root = project({ "pnpm-lock.yaml": "" });
  const stand = deps({ path: ["npm"] });
  const result = run(["--ref", "v0.5.0", "--project-root", root], stand);
  assert.equal(result.status, 2);
  assert.equal(
    result.stderr,
    "akmon update: mode 'package' moves the pin with pnpm, the project's package manager, and `pnpm` is not on PATH. " +
      "Run it where it is, then run `akmon init`:\n    pnpm add -D -E akmon@0.5.0\n",
  );
  assert.deepEqual(stand.ran, []);
  fs.rmSync(root, { recursive: true, force: true });
});

test("a failed move stops before init", () => {
  const root = project();
  const stand = deps({ codes: (argv) => (argv[0] === "npm" ? 1 : 0) });
  const result = run(["--ref", "v0.5.0", "--project-root", root], stand);
  assert.equal(result.status, 2);
  assert.equal(result.stderr, "akmon update: `npm install -D -E akmon@0.5.0` failed (1) — see its output above\n");
  assert.equal(stand.ran.length, 1);
  fs.rmSync(root, { recursive: true, force: true });
});

test("a pin outside devDependencies is refused before the move", () => {
  for (const [manifest, status] of [
    [JSON.stringify({ dependencies: { akmon: "0.4.0" } }), "runtime"],
    [JSON.stringify({ name: "demo" }), "none"],
    ["{", "unreadable"],
  ]) {
    const root = project({ "package.json": manifest });
    const stand = deps();
    const result = run(["--ref", "v0.5.0", "--project-root", root], stand);
    assert.equal(result.status, 2);
    assert.equal(result.stderr, `akmon update: ${data.node_pin_not_dev.replace("{{status}}", status)}\n`);
    assert.deepEqual(stand.ran, []);
    fs.rmSync(root, { recursive: true, force: true });
  }
});

// -- the refusals ------------------------------------------------------------------------------

test("no record is the shared missing-record refusal; a record the Python serves is refused naming it", () => {
  const bare = project({ "_aitna/.akmon.toml": null });
  assert.deepEqual(run(["--project-root", bare], deps()), {
    status: 2,
    stdout: "",
    stderr: `akmon update: ${bare} records no akmon attach (no mount mode in the integration record under _aitna/) — attach it with \`akmon init\`\n`,
  });
  for (const [record, found] of [
    ['mount = "submodule"\nakmon_version = "0.4.0"\n', 'ecosystem = "python"'],
    ['mount = "package"\nakmon_version = "0.4.0"\n', 'ecosystem = "python"'],
  ]) {
    const root = project({ "_aitna/.akmon.toml": record });
    const stand = deps();
    const result = run(["--ref", "v0.5.0", "--project-root", root], stand);
    assert.equal(result.status, 2);
    assert.ok(result.stderr.startsWith("akmon update: this project's integration record is not a Node attach ("));
    assert.ok(result.stderr.includes(found), result.stderr);
    assert.equal(result.stdout, "");
    assert.deepEqual(stand.ran, []);
    fs.rmSync(root, { recursive: true, force: true });
  }
  fs.rmSync(bare, { recursive: true, force: true });
});

test("a project without its installed CLI is told how to install it", () => {
  const root = project({}, { linked: false });
  const stand = deps();
  const result = run(["--ref", "v0.4.0", "--project-root", root], stand);
  assert.equal(result.status, 2);
  assert.equal(
    result.stderr,
    "akmon update: node_modules/akmon/js/akmon/cli.mjs does not exist — the Node package mode runs akmon from the " +
      "project's own node_modules; `npm install` installs it\n",
  );
  fs.rmSync(root, { recursive: true, force: true });
});

test("an unusable --aitna-root is refused with the init text", () => {
  const root = project();
  const result = run(["--aitna-root", "../out", "--project-root", root], deps());
  assert.deepEqual(result, {
    status: 2,
    stdout: "",
    stderr: "akmon update: --aitna-root must be relative to the project root and stay inside it: '../out'\n",
  });
  fs.rmSync(root, { recursive: true, force: true });
});

// -- after init --------------------------------------------------------------------------------

test("a failed init or check is the exit code, and the closing steps name what is left", () => {
  const root = project({ ".codex/hooks.json": "{}" });
  const failedInit = deps({ codes: (argv) => (argv[2] === "init" ? 1 : 0) });
  const initResult = run(["--ref", "v0.5.0", "--project-root", root], failedInit);
  assert.equal(initResult.status, 1);
  assert.equal(initResult.stderr, "akmon update: init failed (1); see its output above\n");
  assert.deepEqual(launched(failedInit.ran), ["init"]);

  const failedVerify = deps({ codes: (argv) => (argv[2] === "verify" ? 1 : 0) });
  const verifyResult = run(["--ref", "v0.5.0", "--project-root", root], failedVerify);
  assert.equal(verifyResult.status, 1);
  assert.equal(verifyResult.stderr, "akmon update: `verify --strict` failed (1) — the update is not finished\n");
  assert.ok(
    verifyResult.stdout.endsWith(
      "akmon update: running sync --check\nakmon update: running verify --strict\n\nakmon update: left to you:\n" +
        "  1. read CHANGELOG.md after 0.4.0 up to v0.5.0: each Breaking or Migration line there is a checklist item for this project\n" +
        "  2. review `git diff` and stage `package.json` and its lockfile with the generated files that changed — the commit is the owner's (D5)\n" +
        "  3. record the bump in this project — a `_aitna/TASKS_ARCHIVE.md` line or its own changelog\n" +
        "  4. Codex: if `.codex/hooks.json` changed, re-approve its hooks with /hooks — a changed entry runs nothing until then\n",
    ),
    verifyResult.stdout,
  );
  fs.rmSync(root, { recursive: true, force: true });
});

test("a realign without a move leaves only the review", () => {
  const root = project();
  const result = run(["--ref", "0.4.0", "--project-root", root], deps());
  assert.equal(result.status, 0);
  assert.ok(
    result.stdout.endsWith(
      "\nakmon update: left to you:\n  1. review `git diff` and stage `package.json` and its lockfile with the generated files " +
        "that changed — the commit is the owner's (D5)\n",
    ),
  );
  fs.rmSync(root, { recursive: true, force: true });
});

// -- the real process --------------------------------------------------------------------------

/**
 * This process's PATH with every directory holding `binary` shadowed by a copy that lacks it —
 * the JS twin of `meta/conformance/runner.py`'s `_hide_binary_from_path`: the fixture's
 * `verify --strict` would otherwise query the host's own Codex (`codex.host-trust`).
 * @param {string} binary
 * @param {string} scratch
 * @returns {string}
 */
function pathWithout(binary, scratch) {
  return (process.env.PATH ?? "")
    .split(posix.delimiter)
    .map((entry, index) => {
      const directory = entry ? posix.resolve(entry) : null;
      if (!directory || !fs.existsSync(posix.join(directory, binary))) {
        return entry;
      }
      const shadow = posix.join(scratch, `path-${index}`);
      fs.mkdirSync(shadow, { recursive: true });
      for (const child of fs.readdirSync(directory)) {
        if (child !== binary && !fs.existsSync(posix.join(shadow, child))) {
          fs.symlinkSync(posix.join(directory, child), posix.join(shadow, child));
        }
      }
      return shadow;
    })
    .join(posix.delimiter);
}

test("the real process realigns a Node project through its installed CLI, keeping its --checks none", () => {
  const version = JSON.parse(fs.readFileSync(posix.join(TREE, "package.json"), "utf8")).version;
  // The empty [check] table `init --checks none` records (C123): the realign's `init --yes` keeps it.
  const none =
    "\n[check]\n# What `akmon check` runs: the project's own commands, `{files}` becoming the files a run covers.\n";
  const root = project({
    "package.json": JSON.stringify({ name: "demo", devDependencies: { akmon: version } }),
    "_aitna/.akmon.toml": RECORD.replaceAll("0.4.0", version) + none,
    "AGENTS.md": "# demo\n",
  });
  const scratch = fs.realpathSync(fs.mkdtempSync(posix.join(os.tmpdir(), "akmon-update-path-")));
  const env = { ...process.env };
  env.PATH = pathWithout("codex", scratch);
  delete env.AITNA_ROOT;
  const result = spawnSync(process.execPath, [CLI, "update", "--ref", version, "--project-root", root], {
    encoding: "utf8",
    env,
  });
  assert.equal(result.status, 0, `${result.stderr}${result.stdout}`);
  assert.ok(
    result.stdout.startsWith(`akmon update: ${root} · mount mode package · already at ${version} — realigning only\n`),
  );
  assert.ok(result.stdout.includes("akmon init: attaching to"), result.stdout);
  assert.ok(result.stdout.includes("akmon update: running sync --check\n"), result.stdout);
  assert.ok(result.stdout.includes("akmon update: running verify --strict\n"), result.stdout);
  assert.ok(result.stdout.includes("akmon update: left to you:\n"), result.stdout);
  assert.ok(result.stdout.includes("[check] already names this project's checks — left untouched\n"), result.stdout);
  assert.ok(fs.readFileSync(posix.join(root, "_aitna", ".akmon.toml"), "utf8").endsWith(none));
  assert.ok(!fs.existsSync(posix.join(root, ".oxlintrc.json")));
  fs.rmSync(scratch, { recursive: true, force: true });
  fs.rmSync(root, { recursive: true, force: true });
});

// -- the mounted modes (C129) ------------------------------------------------------------------

/** @param {string} mode */
const mountedRecord = (mode) =>
  `mount = "${mode}"\necosystem = "node"\nakmon_version = "0.1.0"\nlast_realign = "0.1.0"\n`;

test("a mounted record reads its target from the tags of --repo, as the Python does", () => {
  const root = project({ "_aitna/.akmon.toml": mountedRecord("subtree") }, { linked: false });
  const listing = "aaa\trefs/tags/v0.9.0\nbbb\trefs/tags/v0.10.0\nccc\trefs/tags/v1.0.0rc1\n";
  const stand = deps({ registry: listing });
  const result = run(["--repo", "/srv/akmon", "--project-root", root], stand);
  assert.deepEqual(stand.asked, [["git", "ls-remote", "--tags", "--refs", "/srv/akmon", "refs/tags/v*"]]);
  assert.equal(result.status, 2);
  assert.equal(result.stdout, `akmon update: ${root} · mount mode subtree · 0.1.0 → v0.10.0\n`);
  assert.equal(
    result.stderr,
    `akmon update: ${data.subtree_refusal}\n` +
      "    git subtree pull --prefix _aitna/akmon /srv/akmon v0.10.0 --squash\n" +
      "    node _aitna/akmon/js/akmon/cli.mjs init --ref v0.10.0\n",
  );
  const unreachable = run(["--project-root", root], deps({ registry: null }));
  assert.equal(unreachable.status, 2);
  assert.ok(
    unreachable.stderr.includes("cannot discover the latest release tag from 'https://github.com/akumidv/ai_akmon'"),
  );
  fs.rmSync(root, { recursive: true, force: true });
});

test("subtree realigns in place with this CLI's init at the recorded ref, then checks on the mount's CLI", () => {
  const root = project({ "_aitna/.akmon.toml": mountedRecord("subtree") }, { linked: false });
  const stand = deps();
  const result = run(["--ref", "v0.1.0", "--project-root", root], stand);
  assert.equal(result.status, 0, result.stderr);
  const mountCli = posix.join(root, "_aitna/akmon/js/akmon/cli.mjs");
  assert.deepEqual(stand.ran, [
    [process.execPath, CLI, "init", "--project-root", root, "--yes", "--ref", "0.1.0"],
    [process.execPath, mountCli, "sync", "--check", "--project-root", root],
    [process.execPath, mountCli, "verify", "--strict", "--project-root", root],
  ]);
  assert.ok(result.stdout.includes("review `git diff` and stage `_aitna/akmon` with the generated files that changed"));
  fs.rmSync(root, { recursive: true, force: true });
});

test("vendored prints the npx command of the target release, runs nothing; this CLI's own release runs init", () => {
  const root = project({ "_aitna/.akmon.toml": mountedRecord("vendored") }, { linked: false });
  const stand = deps();
  const result = run(["--ref", "v9.9.9", "--project-root", root], stand);
  assert.equal(result.status, 2);
  const command = `npx github:akumidv/ai_akmon#v9.9.9 init --mode vendored --project-root ${root} --yes`;
  assert.equal(
    result.stderr,
    `akmon update: ${data.node_vendored_command.replace("{{tag}}", "v9.9.9").replace("{{command}}", command)}\n`,
  );
  assert.deepEqual(stand.ran, []);
  const realign = run(["--ref", "0.1.0", "--project-root", root], deps());
  assert.equal(realign.status, 2, "0.1.0 → 0.1.0 is no move, and it is not this CLI's release: v0.1.0's CLI is named");
  assert.ok(realign.stderr.includes("npx github:akumidv/ai_akmon#v0.1.0 init --mode vendored"), realign.stderr);
  fs.writeFileSync(
    posix.join(root, "_aitna/.akmon.toml"),
    mountedRecord("vendored").replace('"0.1.0"', '"0.1.0-3-gabc1234"'),
  );
  const unfetchable = run(["--ref", "0.1.0-3-gabc1234", "--project-root", root], deps());
  assert.equal(unfetchable.status, 2);
  assert.ok(unfetchable.stderr.includes("is not a release this can fetch"), unfetchable.stderr);
  fs.rmSync(root, { recursive: true, force: true });
});

test("submodule fetches the tags into the mount from --repo, then this CLI's init moves the pin", () => {
  const root = project({ "_aitna/.akmon.toml": mountedRecord("submodule") }, { linked: false });
  const stand = deps();
  const result = run(["--ref", "v0.2.0", "--repo", "/srv/akmon", "--project-root", root], stand);
  assert.equal(result.status, 0, result.stderr);
  assert.deepEqual(stand.ran.slice(0, 2), [
    ["git", "fetch", "--quiet", "--tags", "/srv/akmon"],
    [process.execPath, CLI, "init", "--project-root", root, "--yes", "--ref", "v0.2.0"],
  ]);
  assert.ok(result.stdout.includes("akmon update: fetching release tags into _aitna/akmon\n"));
  const failed = run(["--ref", "v0.2.0", "--repo", "/srv/akmon", "--project-root", root], deps({ codes: () => 1 }));
  assert.equal(failed.status, 2);
  assert.equal(
    failed.stderr,
    "akmon update: `git fetch --tags` failed in _aitna/akmon — it needs git and network access to /srv/akmon\n",
  );
  fs.rmSync(root, { recursive: true, force: true });
});
