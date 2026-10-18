#!/usr/bin/env node
/**
 * Initialize model routing for an akmon-consuming project — the JavaScript twin of
 * `tools/model_routing/init.py` (C105, ADR 0020 D01; pulled forward from C108 like `routing.mjs`
 * was into C104). The Python module is the spec: the same files in the same bytes, the same
 * stdout lines, the same `error:` lines, the same exit codes.
 *
 * Computes the tier→model binding from the registry's semantic selection policy (relative to the
 * orchestrating model) and writes the generated artifacts:
 *
 * - `.claude/agents/k_*.md` — subagent definitions (per-user, gitignored; concrete `model:`
 *   frontmatter only when `--available` provides concrete aliases);
 * - `.claude/model-routing.local.json` — the resolved binding, the second-opinion opt-in and the
 *   registry hash.
 *
 * Idempotent: re-running with the same inputs changes nothing. The registry plus the optional
 * project overlay (`<aitna-root>/model-routing.json`) are the data to edit — never the generated
 * files.
 *
 * Data (the C102 convention): `main` reads `tools/model_routing/agents.json` once and passes it
 * down as `data`.
 *
 * Twin notes (`meta/conformance/DIVERGENCES.md`):
 * - the standard tree is always the running tree: the Python answers the mount for a mounted
 *   record, and this implementation serves the package answer only (a Node project has no mount);
 * - the arguments are parsed by `node:util` `parseArgs` (ADR 0020 D08): a usage error is the one
 *   line `init.mjs: error: …` on stderr and exit 2 (`argparse` prints its usage block with every
 *   error, names the program `init.py`, and abbreviates long options — `--avail`), `-h`/`--help`
 *   prints a short usage and exits 0.
 */

import fs from "node:fs";
import { posix } from "node:path";
import { fileURLToPath } from "node:url";
import { parseArgs } from "node:util";

import { embeddedTreeRoot } from "../../akmon/_tree.mjs";
import { read } from "../../common/jsondata.mjs";
import { JSONDecodeError, jsonLoads } from "../../common/pyjson.mjs";
import { aitnaRootName, resolveProjectRoot } from "../../common/project_root.mjs";
import { dictGet, isDict, isFile, pyPath, pyStrip, readText, truthy, writeText } from "../../common/pyvalue.mjs";
import {
  BriefError,
  bindingArtifacts,
  computeBinding,
  loadRegistry,
  localConfigRel,
  overlayName,
  removeObsoleteAgents,
  settingsProbeNames,
  vendorsWithRoutingPolicy,
} from "./routing.mjs";

/** @typedef {any} Json */
/** @typedef {import("./routing.mjs").AgentsData} AgentsData */

/** The tree the running module belongs to (it holds `tools/model_routing/registry.json`). */
const TREE_ROOT = embeddedTreeRoot();

const PROG = "init.mjs";

const USAGE = `usage: ${PROG} [-h] [--project-root PROJECT_ROOT] [--vendor VENDOR]
               [--orchestrator ORCHESTRATOR] [--available AVAILABLE]
               [--second-opinion {on,off}] [--check] [--dry-run]

options:
  -h, --help            show this help message and exit
  --project-root PROJECT_ROOT
                        Project root. Defaults to cwd or a parent with AGENTS.md.
  --vendor VENDOR       Orchestrator vendor selection policy to use (default: anthropic).
  --orchestrator ORCHESTRATOR
                        Alias of the model the session runs on (only the agent knows it).
  --available AVAILABLE
                        Comma-separated model aliases available in the harness.
  --second-opinion {on,off}
                        Enable cross-vendor review (opt-in).
  --check               Do not write; exit 1 when generated files are stale.
  --dry-run             Print changes without writing them.
`;

/**
 * The harness default model, when the settings record one (local settings win).
 * @param {AgentsData} data
 * @param {string} projectRoot
 * @returns {string | null}
 */
function _settingsModel(data, projectRoot) {
  for (const name of settingsProbeNames(data)) {
    const path = pyPath(projectRoot, ".claude", name);
    if (!isFile(path)) {
      continue;
    }
    let settings;
    try {
      settings = jsonLoads(readText(path));
    } catch (error) {
      if (error instanceof JSONDecodeError) {
        continue;
      }
      throw error;
    }
    const model = isDict(settings) ? dictGet(settings, "model") : null;
    if (typeof model === "string" && model !== "") {
      return model;
    }
  }
  return null;
}

/**
 * The recorded local config, `{}` when absent, unparsable or not an object.
 * @param {AgentsData} data
 * @param {string} projectRoot
 * @returns {Record<string, Json>}
 */
function _existingConfig(data, projectRoot) {
  const path = pyPath(projectRoot, localConfigRel(data));
  if (!isFile(path)) {
    return {};
  }
  let config;
  try {
    config = jsonLoads(readText(path));
  } catch (error) {
    if (error instanceof JSONDecodeError) {
      return {};
    }
    throw error;
  }
  return isDict(config) ? config : {};
}

/**
 * @param {AgentsData} data
 * @param {string} projectRoot
 * @returns {boolean}
 */
function _existingSecondOpinion(data, projectRoot) {
  return truthy(dictGet(_existingConfig(data, projectRoot), "second_opinion"));
}

/**
 * Parse the arguments.
 * @param {string[]} argv
 * @returns {{projectRoot: string | null, vendor: string, orchestrator: string | null, available: string | null,
 *   secondOpinion: string | null, check: boolean, dryRun: boolean, help: boolean} | string} the options, or the one-line usage error
 */
function _parse(argv) {
  try {
    const { values } = parseArgs({
      args: argv,
      options: {
        "project-root": { type: "string" },
        vendor: { type: "string" },
        orchestrator: { type: "string" },
        available: { type: "string" },
        "second-opinion": { type: "string" },
        check: { type: "boolean" },
        "dry-run": { type: "boolean" },
        help: { type: "boolean", short: "h" },
      },
      allowPositionals: false,
      strict: true,
    });
    const secondOpinion = /** @type {string | undefined} */ (values["second-opinion"]) ?? null;
    if (secondOpinion !== null && secondOpinion !== "on" && secondOpinion !== "off") {
      return `argument --second-opinion: invalid choice: '${secondOpinion}' (choose from 'on', 'off')`;
    }
    return {
      projectRoot: /** @type {string | undefined} */ (values["project-root"]) ?? null,
      vendor: /** @type {string | undefined} */ (values.vendor) ?? "anthropic",
      orchestrator: /** @type {string | undefined} */ (values.orchestrator) ?? null,
      available: /** @type {string | undefined} */ (values.available) ?? null,
      secondOpinion,
      check: values.check === true,
      dryRun: values["dry-run"] === true,
      help: values.help === true,
    };
  } catch (exc) {
    const code = /** @type {{code?: string}} */ (exc).code;
    if (typeof code !== "string" || !code.startsWith("ERR_PARSE_ARGS_")) {
      throw exc;
    }
    // parseArgs words some errors over several lines (the hint for the fix); the first is the fact.
    return /** @type {Error} */ (exc).message.split("\n")[0];
  }
}

/**
 * `path` relative to `root`, spelled as `Path.relative_to` spells it.
 * @param {string} root
 * @param {string} path
 * @returns {string}
 */
function _rel(root, path) {
  return posix.relative(root, path);
}

/**
 * CLI entry point: compute the binding and write (or check) the generated routing artifacts.
 * @param {string[]} [argv] the arguments (default: the process's)
 * @returns {number} The process exit code: 0, 1 when `--check` finds a stale file, 2 on a usage
 *   or overlay-brief error.
 */
export function main(argv = process.argv.slice(2)) {
  const options = _parse(argv);
  if (typeof options === "string") {
    process.stderr.write(`${PROG}: error: ${options}\n`);
    return 2;
  }
  if (options.help) {
    process.stdout.write(USAGE);
    return 0;
  }

  const { root, notice } = resolveProjectRoot(options.projectRoot);
  if (notice) {
    process.stderr.write(`${notice}\n`);
  }
  const data = /** @type {AgentsData} */ (read(posix.join(TREE_ROOT, "tools", "model_routing", "agents.json")));
  const registry = loadRegistry(data, TREE_ROOT, root);
  const vendors = vendorsWithRoutingPolicy(registry);
  if (!vendors.includes(options.vendor)) {
    process.stderr.write(`${PROG}: error: --vendor must be one of: ${vendors.join(", ")}\n`);
    return 2;
  }
  const available = options.available
    ? options.available
        .split(",")
        .map((alias) => pyStrip(alias))
        .filter((alias) => alias !== "")
    : null;
  const fallback = dictGet(dictGet(registry, options.vendor), "semantic_fallback", {});
  const orchestrator =
    (options.orchestrator || null) ??
    _settingsModel(data, root) ??
    (available && available.length > 0
      ? available[available.length - 1]
      : dictGet(fallback, "orchestrator", "strongest"));
  const secondOpinion =
    options.secondOpinion === null ? _existingSecondOpinion(data, root) : options.secondOpinion === "on";

  const binding = computeBinding(data, registry, orchestrator, available, options.vendor);
  /** @type {Record<string, string>} */ let artifacts;
  try {
    artifacts = bindingArtifacts(data, registry, binding, { secondOpinion, available });
  } catch (exc) {
    if (!(exc instanceof BriefError)) {
      throw exc;
    }
    // Nothing is written: generating the definitions without the overlay's briefs would drop
    // hand-authored project instructions, and the sweep below would then delete the only files
    // still carrying them (C50).
    process.stderr.write(`error: ${exc.message}\n`);
    const overlay = pyPath(aitnaRootName(), overlayName(data));
    process.stderr.write(`error: fix ${overlay}; no files were written\n`);
    return 2;
  }
  /** @type {Map<string, string>} */
  const planned = new Map(Object.entries(artifacts).map(([rel, content]) => [pyPath(root, rel), content]));

  const write = !options.check && !options.dryRun;
  /** @type {string[]} */ const changed = [];
  for (const [path, content] of planned) {
    const current = isFile(path) ? readText(path) : null;
    if (current === content) {
      process.stdout.write(`ok: ${_rel(root, path)}\n`);
      continue;
    }
    changed.push(path);
    process.stdout.write(`${write ? "updated" : "would update"}: ${_rel(root, path)}\n`);
    if (write) {
      fs.mkdirSync(posix.dirname(path), { recursive: true });
      writeText(path, content);
    }
  }

  for (const path of removeObsoleteAgents(data, root, planned.keys(), { write })) {
    changed.push(path);
    process.stdout.write(`${write ? "deleted" : "would delete"}: ${_rel(root, path)}\n`);
  }

  process.stdout.write(
    "model routing: " +
      `vendor=${binding.vendor} · orchestrator=${binding.orchestrator} · reasoner=${binding.reasoner} · ` +
      `auditor=${binding.auditor} · ` +
      `worker=${binding.worker} · mid=${binding.mid} · ` +
      `second-opinion=${binding.secondOpinionCli || "-"}(${secondOpinion ? "on" : "off"})\n`,
  );
  if (binding.warning) {
    process.stdout.write(`⚠ ${binding.warning}\n`);
  }
  if (options.check && changed.length > 0) {
    return 1;
  }
  return 0;
}

/**
 * Whether node was told to execute `invoked` as this very module (see `akmon/cli.mjs`).
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

if (process.argv[1] !== undefined && runAsEntryPoint(process.argv[1])) {
  process.exitCode = main();
}
