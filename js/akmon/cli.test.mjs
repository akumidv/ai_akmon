/**
 * node:test for `js/akmon/cli.mjs` — the `akmon` bin: each command through `main(argv)` (the
 * exit code, the output captured) and through a spawned `node js/akmon/cli.mjs` (the real
 * process: the entry-point guard, the symlink npm installs, stdout and stderr). A spawned run is
 * the only way to see the entry guard, which settles while the module loads.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import { posix } from "node:path";
import { fileURLToPath } from "node:url";

import { main } from "./cli.mjs";

const cliModule = new URL("./cli.mjs", import.meta.url);
const CLI = fileURLToPath(cliModule);
const TREE = posix.resolve(posix.dirname(CLI), "..", "..");
const HOOKS = posix.join(TREE, "js", "hooks");
const cliData = JSON.parse(fs.readFileSync(posix.join(TREE, "src", "akmon", "cli.json"), "utf8"));
const manifest = JSON.parse(fs.readFileSync(posix.join(TREE, "package.json"), "utf8"));

/** The hook stems a Python `hooks/` lists, as the corpus pins them (`cli/hook-unknown`). */
const HOOK_STEMS = [
  "analysis-guard", "claude_adapter", "codex-hook", "codex_adapter", "delegation-log", "delegation-nudge",
  "gate-audit", "git-commit-guard", "hook_core", "model-routing", "role-on-code", "session-start-agent",
];

function tmpdir() {
  return fs.mkdtempSync(posix.join(os.tmpdir(), "akmon-cli-"));
}

/** A project root: `AGENTS.md` and a package-mode record. */
function project() {
  const root = fs.realpathSync(tmpdir());
  fs.writeFileSync(posix.join(root, "AGENTS.md"), "# project\n");
  fs.mkdirSync(posix.join(root, "_aitna"));
  fs.writeFileSync(posix.join(root, "_aitna", ".akmon.toml"), 'mount = "package"\n[check]\nlint = "echo checked {files}"\n');
  return root;
}

/**
 * Run `node script ...args` with a clean environment of its own: a fresh `TMPDIR` (the hooks'
 * once-per-session markers live there) and no `AITNA_ROOT`.
 * @param {string} script
 * @param {string[]} args
 * @param {{cwd?: string, input?: string}} [options]
 */
function spawnNode(script, args, options = {}) {
  /** @type {NodeJS.ProcessEnv} */
  const env = { ...process.env, TMPDIR: tmpdir() };
  delete env.AITNA_ROOT;
  const result = spawnSync(process.execPath, [script, ...args], {
    cwd: options.cwd ?? os.tmpdir(), env, encoding: "utf8", input: options.input ?? "",
  });
  return { status: result.status, stdout: result.stdout, stderr: result.stderr };
}

/** `node cli.mjs ...args`. */
function akmon(/** @type {string[]} */ args, /** @type {{cwd?: string, input?: string}} */ options = {}) {
  return spawnNode(CLI, args, options);
}

/** Run `main(args)` with both streams captured. */
async function inProcess(/** @type {string[]} */ args) {
  const out = /** @type {string[]} */ ([]);
  const err = /** @type {string[]} */ ([]);
  const write = { out: process.stdout.write, err: process.stderr.write };
  process.stdout.write = /** @type {typeof process.stdout.write} */ ((/** @type {string} */ text) => (out.push(text), true));
  process.stderr.write = /** @type {typeof process.stderr.write} */ ((/** @type {string} */ text) => (err.push(text), true));
  try {
    return { status: await main(args), stdout: out.join(""), stderr: err.join("") };
  } finally {
    process.stdout.write = write.out;
    process.stderr.write = write.err;
  }
}

// -- entry point -------------------------------------------------------------------------------

test("run through the symlink npm installs for a bin entry, the CLI still runs", () => {
  // npm does not copy the `bin` target into `node_modules/.bin/`, it links it, so the path
  // node was given and the path the module was loaded from differ by one hop.
  const dir = tmpdir();
  const linkPath = posix.join(dir, "akmon");
  fs.symlinkSync(CLI, linkPath);
  const result = spawnNode(linkPath, ["version"]);
  assert.deepEqual(result, { status: 0, stdout: `${manifest.version}\n`, stderr: "" });
  fs.rmSync(dir, { recursive: true, force: true });
});

test("imported rather than run, the module writes nothing and leaves the exit code alone", () => {
  const dir = tmpdir();
  const importer = posix.join(dir, "importer.mjs");
  fs.writeFileSync(importer, `await import("${cliModule.href}");\nprocess.stdout.write("imported\\n");\n`);
  const result = spawnNode(importer, []);
  assert.deepEqual(result, { status: 0, stdout: "imported\n", stderr: "" });
  fs.rmSync(dir, { recursive: true, force: true });
});

test("the exit code is process.exitCode: the run ends by itself, never through process.exit", () => {
  assert.ok(!/process\.exit\(/.test(fs.readFileSync(CLI, "utf8")));
  assert.equal(akmon(["update"]).status, 2);
});

// -- the lean hot path -------------------------------------------------------------------------

test("the static imports of the CLI are the few a hook run needs; every command module is a dynamic import", () => {
  const source = fs.readFileSync(CLI, "utf8");
  const statics = [...source.matchAll(/^import [^;]*? from "([^"]+)";$/gms)].map((match) => match[1]);
  assert.deepEqual(statics, ["node:fs", "node:path", "node:url", "../common/jsondata.mjs", "./_tree.mjs"]);
  const dynamics = [...source.matchAll(/\bimport\("([^"]+)"\)/g)].map((match) => match[1]);
  assert.ok(dynamics.includes("../bin/sync.mjs") && dynamics.includes("../bin/check.mjs"));
  assert.ok(dynamics.includes("../bin/verify.mjs") && dynamics.includes("./_init.mjs"));
  assert.ok(!/findings|parseArgs|node:util/.test(statics.join(" ")));
});

// -- version, path -----------------------------------------------------------------------------

test("version prints the package.json version of the running tree", async () => {
  assert.deepEqual(await inProcess(["version"]), { status: 0, stdout: `${manifest.version}\n`, stderr: "" });
  assert.deepEqual(akmon(["version"]), { status: 0, stdout: `${manifest.version}\n`, stderr: "" });
});

test("path prints the real path of the running tree, whatever the cwd", async () => {
  const expected = `${fs.realpathSync(TREE)}\n`;
  assert.deepEqual(await inProcess(["path"]), { status: 0, stdout: expected, stderr: "" });
  const elsewhere = tmpdir();
  assert.deepEqual(akmon(["path"], { cwd: elsewhere }), { status: 0, stdout: expected, stderr: "" });
  fs.rmSync(elsewhere, { recursive: true, force: true });
});

// -- the commands that are not ported ---------------------------------------------------------

test("update names the task that ports it, with or without arguments", async () => {
  const tasks = { update: "C107" };
  for (const [command, task] of Object.entries(tasks)) {
    const expected = `akmon ${command}: not ported to the JavaScript implementation yet (${task})\n`;
    assert.deepEqual(await inProcess([command]), { status: 2, stdout: "", stderr: expected });
    assert.deepEqual(akmon([command, "--help"]), { status: 2, stdout: "", stderr: expected });
  }
  assert.equal(cliData.not_ported, "akmon {{command}}: not ported to the JavaScript implementation yet ({{task}})");
});

// -- the top level -----------------------------------------------------------------------------

test("-h and --help print the usage block with the command list of cli.json, exit 0", async () => {
  const expected =
    "usage: akmon [-h]\n\nakmon — the akmon AI-agent development standard, as an installable package.\n\n" +
    `options:\n  -h, --help  show this help message and exit\n\n${cliData.epilog}`;
  for (const flag of ["-h", "--help"]) {
    assert.deepEqual(await inProcess([flag]), { status: 0, stdout: expected, stderr: "" });
  }
  assert.deepEqual(akmon(["--help"]), { status: 0, stdout: expected, stderr: "" });
});

test("a missing or unknown command is one usage line on stderr and exit 2", async () => {
  assert.deepEqual(await inProcess([]), {
    status: 2, stdout: "", stderr: "akmon: error: the following arguments are required: command\n",
  });
  assert.deepEqual(akmon(["--bogus"]), {
    status: 2, stdout: "", stderr: "akmon: error: the following arguments are required: command\n",
  });
  assert.deepEqual(akmon(["frobnicate"]), {
    status: 2,
    stdout: "",
    stderr:
      "akmon: error: argument command: invalid choice: 'frobnicate' " +
      "(choose from 'init', 'update', 'sync', 'verify', 'check', 'path', 'hook', 'version')\n",
  });
});

// -- sync, check -------------------------------------------------------------------------------

test("check is the check command: same output and exit code as running bin/check.mjs", () => {
  const root = project();
  const direct = spawnNode(posix.join(TREE, "js", "bin", "check.mjs"), [], { cwd: root });
  const viaCli = akmon(["check"], { cwd: root });
  assert.equal(direct.status, 0);
  assert.equal(direct.stdout, "checked .\nOK check.run [check].lint: `echo checked .` passed → Keep it passing\n");
  assert.deepEqual(viaCli, direct);
  const failing = akmon(["check", "--bogus"], { cwd: root });
  assert.deepEqual(failing, { status: 2, stdout: "", stderr: "akmon check: error: Unknown option '--bogus'\n" });
  fs.rmSync(root, { recursive: true, force: true });
});

test("sync is the sync command: same output and exit code as running bin/sync.mjs", () => {
  const root = project();
  for (const args of [["--check"], ["--dry-run"], ["--bogus"]]) {
    const direct = spawnNode(posix.join(TREE, "js", "bin", "sync.mjs"), [...args, "--project-root", root], { cwd: root });
    const viaCli = akmon(["sync", ...args, "--project-root", root], { cwd: root });
    assert.deepEqual(viaCli, direct, args.join(" "));
  }
  fs.rmSync(root, { recursive: true, force: true });
});

test("verify is the verify command: same output and exit code as running bin/verify.mjs", () => {
  const root = project();
  for (const args of [["--quiet"], ["--help"], ["--bogus"]]) {
    const direct = spawnNode(posix.join(TREE, "js", "bin", "verify.mjs"), [...args, "--project-root", root], { cwd: root });
    const viaCli = akmon(["verify", ...args, "--project-root", root], { cwd: root });
    assert.deepEqual(viaCli, direct, args.join(" "));
  }
  fs.rmSync(root, { recursive: true, force: true });
});

// -- hook --------------------------------------------------------------------------------------

test("hook without a name is refused with the data text and exit 2", async () => {
  assert.deepEqual(await inProcess(["hook"]), {
    status: 2, stdout: "", stderr: "akmon hook: missing hook name\n",
  });
});

test("hook refuses a path or a dotted name, quoted as the Python quotes it", async () => {
  const refused = (/** @type {string} */ shown) =>
    `akmon hook: ${shown} is a path; name the hook instead (e.g. 'role-on-code')\n`;
  for (const [name, shown] of [
    ["hooks/role-on-code", "'hooks/role-on-code'"],
    ["..\\role-on-code", "'..\\\\role-on-code'"],
    [".hidden", "'.hidden'"],
    ["it's/x", '"it\'s/x"'],
  ]) {
    assert.deepEqual(await inProcess(["hook", name]), { status: 2, stdout: "", stderr: refused(shown) }, name);
  }
});

test("hook names the hooks it has when it is given an unknown one: no data bundle, no test", async () => {
  const available = HOOK_STEMS.join(", ");
  for (const name of ["no-such-hook", "", "hook_data", "hook_core.test", "claude_adapter.test", "role-on-code.py"]) {
    assert.deepEqual(
      await inProcess(["hook", name]),
      {
        status: 2,
        stdout: "",
        stderr: `akmon hook: unknown hook ${name.includes("'") ? `"${name}"` : `'${name}'`}; available: ${available}\n`,
      },
      name,
    );
  }
  const onDisk = fs.readdirSync(HOOKS).filter((name) => name.endsWith(".mjs") && !name.endsWith(".test.mjs"))
    .map((name) => name.slice(0, -4)).filter((stem) => stem !== "hook_data").sort();
  assert.deepEqual(onDisk, HOOK_STEMS);
});

/** The same payload through `akmon hook <args>` and through `node js/hooks/<script>.mjs <rest>`. */
function sameAsDirect(/** @type {string} */ script, /** @type {string[]} */ rest, /** @type {unknown} */ payload, /** @type {string} */ cwd) {
  const input = JSON.stringify(payload);
  const direct = spawnNode(posix.join(HOOKS, `${script}.mjs`), rest, { cwd, input });
  const viaCli = akmon(["hook", script, ...rest], { cwd, input });
  assert.deepEqual(viaCli, direct, `${script} ${rest.join(" ")}`);
  return direct;
}

test("hook runs a Claude hook in process: byte for byte what node runs on the script itself", () => {
  const root = project();
  const result = sameAsDirect(
    "role-on-code", [],
    { hook_event_name: "PreToolUse", tool_name: "Edit", session_id: "sess-ro", cwd: root, tool_input: { file_path: `${root}/src/app.py` } },
    root,
  );
  assert.equal(result.status, 0);
  assert.match(JSON.parse(result.stdout).hookSpecificOutput.additionalContext, /^\[akmon\] Role check — you are editing project code\./);
  // a name with the suffix is the same hook; a silent hook is silent in both
  const silent = akmon(["hook", "role-on-code.mjs"], { cwd: root, input: JSON.stringify({ tool_name: "Edit", cwd: root, tool_input: { file_path: `${root}/README.md` } }) });
  assert.deepEqual(silent, { status: 0, stdout: "", stderr: "" });
  fs.rmSync(root, { recursive: true, force: true });
});

test("hook runs the Codex dispatcher with the rest of the arguments as its route", () => {
  const root = project();
  const patch = "*** Begin Patch\n*** Add File: src/mod.py\n+x = 1\n*** End Patch\n";
  const payload = { tool_name: "apply_patch", session_id: "sess-ch-roc", cwd: root, tool_input: { command: patch } };
  const result = sameAsDirect("codex-hook", ["role-on-code"], payload, root);
  assert.equal(result.status, 0);
  assert.match(JSON.parse(result.stdout).hookSpecificOutput.additionalContext, /^\[akmon\] Role check/);
  // the dispatcher's own refusals reach the owner the same way: one crash line, exit 1
  assert.deepEqual(sameAsDirect("codex-hook", [], payload, root), { status: 1, stdout: "", stderr: "akmon codex-hook hook: UsageError\n" });
  assert.deepEqual(sameAsDirect("codex-hook", ["nope"], payload, root), { status: 1, stdout: "", stderr: "akmon codex-hook hook: UsageError\n" });
  fs.rmSync(root, { recursive: true, force: true });
});

test("hook model-routing reports through the same single document as the script", () => {
  const root = project();
  const result = sameAsDirect("model-routing", [], { hook_event_name: "SessionStart", session_id: "sess-mr", cwd: root, source: "startup" }, root);
  assert.equal(result.status, 0);
  assert.equal(result.stderr, "");
  fs.rmSync(root, { recursive: true, force: true });
});

test("a hook module without an entry runs as an empty script does: exit 0, no output", async () => {
  assert.deepEqual(await inProcess(["hook", "hook_core"]), { status: 0, stdout: "", stderr: "" });
  assert.deepEqual(akmon(["hook", "claude_adapter"]), { status: 0, stdout: "", stderr: "" });
});
