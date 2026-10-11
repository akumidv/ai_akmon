#!/usr/bin/env node
/**
 * The `akmon` bin entry of the npm package — the JavaScript twin of `src/akmon/cli.py` (C105,
 * ADR 0020 D01). The Python module is the spec: the same answers, the same texts, the same exit
 * codes and the same stdout and stderr, for the commands that exist here.
 *
 * `init`, `sync`, `verify`, `check`, `path`, `hook` and `version` are real (`init` serves Node
 * package mode only, see `_init.mjs`). `update` is not ported yet: it prints the `not_ported` text
 * of `src/akmon/cli.json` and exits 2.
 *
 * `hook` is the hot path of a session — the generated wiring of a Node project names the hook
 * scripts directly, but `akmon hook <name>` is the same entry for a hand run and for the corpus —
 * so this module is lean on purpose: its static imports are `node:fs`, `node:path`, `node:url`
 * and the tiny `jsondata`; a command loads the one module it needs with a dynamic `import()`
 * (`bin/sync.mjs`, `bin/verify.mjs`, `bin/check.mjs`, the hook), and `hook` imports no `bin/*`, no `node:util`
 * `parseArgs` and no findings module. The hook runs **in this process**: a hook module starts
 * itself only when node was told to run it (`runAsEntryPoint`), so importing it starts nothing,
 * and every hook exports `main`, which is called here with the remaining arguments (the Codex
 * dispatcher reads its route from them — `akmon hook codex-hook role-on-code` is
 * `node codex-hook.mjs role-on-code`).
 *
 * Data (the C102 convention): the shared CLI text is `src/akmon/cli.json`, read on first use —
 * never by the `hook` hot path unless it has something to refuse — and handed down as `data`.
 * A pure function that needs a text takes the bundle first.
 *
 * Twin notes (ADR 0020 D02, D08, `meta/conformance/DIVERGENCES.md`):
 * - there is no mounted tree and no version-skew notice: the tree is the package that holds the
 *   running file (D02), so `path` prints its real path and `version` its `package.json` version;
 * - `hook <name>` accepts `<name>` and `<name>.mjs` (the Python accepts `<name>.py`); the hooks
 *   it lists as `available:` are the stems of `js/hooks/*.mjs` except `hook_data` and the tests;
 * - the top level is not `argparse`: `-h`/`--help` prints the same block, a usage error is the
 *   one line `akmon: error: …` on stderr and exit 2 (`argparse` puts a usage line before it); the
 *   flags of a command belong to the command.
 */

import fs from "node:fs";
import { posix } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

import { fill, read } from "../common/jsondata.mjs";
import { embeddedTreeRoot } from "./_tree.mjs";

/**
 * The shape of `src/akmon/cli.json` the JavaScript CLI reads (the Python reads more keys).
 * @typedef {object} CliData
 * @property {string} epilog
 * @property {string} hook_missing_name
 * @property {string} hook_path_refused
 * @property {string} hook_unknown
 * @property {string} not_ported
 */

/** The tree this module executes from: `<tree>/js/akmon/cli.mjs` → `<tree>`. */
const TREE_ROOT = posix.resolve(posix.dirname(fileURLToPath(import.meta.url)), "..", "..");

/** The commands, in the order the Python lists them. */
const COMMANDS = ["init", "update", "sync", "verify", "check", "path", "hook", "version"];

/** The commands that are not ported yet, and the task that ports each. */
const PORTS = new Map([["update", "C107"]]);

/** The line `-h` prints under the usage line (the Python's `argparse` description). */
const DESCRIPTION = "akmon — the akmon AI-agent development standard, as an installable package.";

/** The keys of `cli.json` the bundle exposes. */
const DATA_KEYS = ["epilog", "hook_missing_name", "hook_path_refused", "hook_unknown", "not_ported"];

/**
 * The CLI text, read from `src/akmon/cli.json` on the first property access and then kept: a
 * command that has nothing to say (`hook` running a hook) never opens the file.
 * @returns {CliData}
 */
function lazyCliData() {
  /** @type {Record<string, unknown> | null} */
  let loaded = null;
  const file = () => (loaded ??= /** @type {Record<string, unknown>} */ (read(posix.join(TREE_ROOT, "src", "akmon", "cli.json"))));
  /** @type {Record<string, unknown>} */
  const bundle = {};
  for (const key of DATA_KEYS) {
    Object.defineProperty(bundle, key, { enumerable: true, get: () => file()[key] });
  }
  return /** @type {CliData} */ (bundle);
}

/**
 * Whether `path` is a regular file (a directory named like one does not count; a link is followed).
 * @param {string} path
 * @returns {boolean}
 */
function _isFile(path) {
  try {
    return fs.statSync(path).isFile();
  } catch {
    return false;
  }
}

/**
 * The stem of a hooks-directory entry, as `Path.stem` spells it for `*.py`: the name without
 * its last suffix, and a name that is only the suffix is its own stem.
 * @param {string} fileName a name that ends in `.mjs`
 * @returns {string}
 */
function _stem(fileName) {
  return fileName === ".mjs" ? fileName : fileName.slice(0, -".mjs".length);
}

/**
 * Whether `stem` names a module `akmon hook` may run: a hook or a hook module, not the data
 * bundle and not a test (`js/hooks` holds both, which `hooks/` of the Python does not).
 * @param {string} stem
 * @returns {boolean}
 */
function _isHookStem(stem) {
  return stem !== "hook_data" && !stem.endsWith(".test");
}

/**
 * The hook stems of `hooksDir`, sorted by code point — empty when the directory cannot be listed.
 * @param {string} hooksDir
 * @returns {Promise<string[]>}
 */
async function _availableHooks(hooksDir) {
  let names;
  try {
    names = fs.readdirSync(hooksDir);
  } catch {
    return [];
  }
  const { codePointSort } = await import("../common/sort.mjs");
  return codePointSort(names.filter((name) => name.endsWith(".mjs")).map(_stem).filter(_isHookStem));
}

/**
 * `akmon hook <name> [args...]` — run one hook out of the running tree.
 *
 * Only generated wiring and the corpus call this, so a path where a name belongs is the
 * caller's error and is refused rather than accommodated. The rest of `argv` is passed to the
 * hook's `main` verbatim. An exception the hook does not handle itself is deliberately not
 * caught here: every akmon hook guarantees "never block a session" in its own `main`, so
 * reaching this frame means the hook is broken before that guarantee applies, and a dispatcher
 * that hid it would leave a guardrail silently off. node reports it and exits 1: visible to the
 * owner, not a block.
 * @param {CliData} data
 * @param {string[]} argv the arguments after `hook`
 * @returns {Promise<number>} The process exit code.
 */
async function _cmdHook(data, argv) {
  if (argv.length === 0) {
    process.stderr.write(`${data.hook_missing_name}\n`);
    return 2;
  }
  const [name, ...rest] = argv;
  const hooksDir = posix.join(TREE_ROOT, "js", "hooks");
  if (name.includes("/") || name.includes("\\") || name.startsWith(".")) {
    const { strRepr } = await import("../common/pyvalue.mjs");
    process.stderr.write(`${fill(data.hook_path_refused, { name: strRepr(name) })}\n`);
    return 2;
  }
  const stem = name.endsWith(".mjs") ? name.slice(0, -".mjs".length) : name;
  const script = posix.join(hooksDir, `${stem}.mjs`);
  if (!_isHookStem(stem) || !_isFile(script)) {
    const { strRepr } = await import("../common/pyvalue.mjs");
    const available = (await _availableHooks(hooksDir)).join(", ") || "(none)";
    process.stderr.write(`${fill(data.hook_unknown, { name: strRepr(name), available })}\n`);
    return 2;
  }
  const hook = await import(pathToFileURL(script).href);
  // A hook module without an entry (`hook_core`, the adapters) runs as an empty script does.
  if (typeof hook.main !== "function") {
    return 0;
  }
  const code = await hook.main(rest);
  return typeof code === "number" ? code : 0;
}

/**
 * The block `akmon -h` prints: the usage line, the description, the one option, and the command
 * list that `cli.json` owns.
 * @param {CliData} data
 * @returns {string}
 */
function _help(data) {
  return (
    `usage: akmon [-h]\n\n${DESCRIPTION}\n\noptions:\n  -h, --help  show this help message and exit\n\n` +
    data.epilog
  );
}

/**
 * One usage error: the one line, and exit 2.
 * @param {string} message
 * @returns {number}
 */
function _usageError(message) {
  process.stderr.write(`akmon: error: ${message}\n`);
  return 2;
}

/**
 * Dispatch the named `akmon` command.
 * @param {string[]} [argv] the arguments after the script (default: the process's)
 * @returns {Promise<number>} The process exit code.
 */
export async function main(argv = process.argv.slice(2)) {
  const [command, ...rest] = argv;
  const data = lazyCliData();
  // `hook` is dispatched before anything else is looked at: it is the hottest entry point there
  // is (a hand-run hook, the corpus), and it takes no flags of its own.
  if (command === "hook") {
    return _cmdHook(data, rest);
  }
  if (command === "-h" || command === "--help") {
    process.stdout.write(_help(data));
    return 0;
  }
  if (command === undefined || command.startsWith("-")) {
    return _usageError("the following arguments are required: command");
  }
  if (!COMMANDS.includes(command)) {
    const choices = COMMANDS.map((choice) => `'${choice}'`).join(", ");
    return _usageError(`argument command: invalid choice: '${command}' (choose from ${choices})`);
  }
  const task = PORTS.get(command);
  if (task !== undefined) {
    process.stderr.write(`${fill(data.not_ported, { command, task })}\n`);
    return 2;
  }
  if (command === "init") {
    return (await import("./_init.mjs")).main(rest);
  }
  if (command === "sync") {
    return (await import("../bin/sync.mjs")).main(rest);
  }
  if (command === "verify") {
    return (await import("../bin/verify.mjs")).main(rest);
  }
  if (command === "check") {
    return (await import("../bin/check.mjs")).main(rest);
  }
  if (command === "path") {
    process.stdout.write(`${embeddedTreeRoot()}\n`);
    return 0;
  }
  // `version`: the `package.json` of the running tree.
  const manifest = /** @type {{version: string}} */ (read(posix.join(fs.realpathSync(TREE_ROOT), "package.json")));
  process.stdout.write(`${manifest.version}\n`);
  return 0;
}

/**
 * Whether node was told to execute `invoked` as this very module. Both sides are dereferenced
 * because npm installs a `bin` entry as a symlink in `node_modules/.bin/`: the path it was
 * given is the link, `import.meta.url` is the target, and the two agree only once resolved.
 * An unresolvable path (a link whose target is gone) falls back to the unresolved comparison:
 * the check answers whether to run, it never crashes the thing it is guarding.
 *
 * @param {string} invoked `process.argv[1]`, the path node was given
 * @returns {boolean}
 */
function runAsEntryPoint(invoked) {
  const self = fileURLToPath(import.meta.url);
  try {
    return fs.realpathSync(invoked) === fs.realpathSync(self);
  } catch {
    return invoked === self;
  }
}

// Run as the entry point, not imported: the ESM way to say so is to compare the file node was
// actually told to execute with this module's own path.
if (process.argv[1] !== undefined && runAsEntryPoint(process.argv[1])) {
  process.exitCode = await main();
}
