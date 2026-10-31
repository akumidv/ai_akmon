#!/usr/bin/env node
/**
 * Initialize model routing for an akmon-consuming project — the JavaScript twin of
 * `tools/model_routing/init.py` (C105, ADR 0020 D01; pulled forward from C108 like `routing.mjs`
 * was into C104). The Python module is the spec: the same files in the same bytes, the same
 * stdout lines, the same `error:` lines, the same exit codes.
 *
 * Computes the tier→model binding from the registry's selection policy over the vendor's committed
 * harness ladder (or an `--available` list), relative to the orchestrating model, and writes the
 * generated artifacts:
 *
 * - `.claude/agents/k_*.md` — subagent definitions (per-user, gitignored; concrete `model:`
 *   frontmatter whenever a ladder binds — the vendor's committed one or `--available` — and
 *   omitted only for a vendor with neither);
 * - `.claude/model-routing.local.json` — the resolved binding, the second-opinion opt-in, the
 *   optional `session` stanza (the harness, model and priors the session runs on, recorded with
 *   `--session-provider`/`--session-model`/`--session-family`) and the registry hash.
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
import {
  dictGet,
  isDict,
  isFile,
  pyError,
  pyPath,
  pyStr,
  pyStrip,
  readText,
  strRepr,
  truthy,
  writeText,
} from "../../common/pyvalue.mjs";
import {
  BriefError,
  OverlayError,
  RetiredKeyError,
  SessionUnknownError,
  bindingArtifacts,
  checkAuditorOptIn,
  checkLadderOrder,
  checkSessionFamily,
  computeBinding,
  loadRegistry,
  localConfigRel,
  opinionHead,
  overlayName,
  refuseRetiredKeys,
  removeObsoleteAgents,
  selectionLadder,
  settingsProbeNames,
  vendorRefusal,
  vendorsWithRoutingPolicy,
} from "./routing.mjs";

/** @typedef {any} Json */
/** @typedef {import("./routing.mjs").AgentsData} AgentsData */
/** @typedef {import("../../common/runtime.mjs").RuntimeData} RuntimeData */

/** The tree the running module belongs to (it holds `tools/model_routing/registry.json`). */
const TREE_ROOT = embeddedTreeRoot();

const PROG = "init.mjs";

const USAGE = `usage: ${PROG} [-h] [--project-root PROJECT_ROOT] [--vendor VENDOR]
               [--orchestrator ORCHESTRATOR] [--available AVAILABLE]
               [--auditor AUDITOR] [--second-opinion {on,off}]
               [--session-provider SESSION_PROVIDER]
               [--session-model SESSION_MODEL]
               [--session-family SESSION_FAMILY] [--check] [--dry-run]

options:
  -h, --help            show this help message and exit
  --project-root PROJECT_ROOT
                        Project root. Defaults to cwd or a parent with AGENTS.md.
  --vendor VENDOR       Orchestrator vendor selection policy to use (default: anthropic).
  --orchestrator ORCHESTRATOR
                        Alias of the model the session runs on (only the agent knows it).
  --available AVAILABLE
                        Comma-separated model aliases available in the harness, weakest first;
                        defaults to the vendor's committed ladder.
  --auditor AUDITOR     Opt in to this rung as the auditor: an auditor-only rung of the vendor (e.g.
                        fable) or one of its ladder; with --available it must be listed there.
  --second-opinion {on,off}
                        Enable second-opinion review (opt-in).
  --session-provider SESSION_PROVIDER
                        Record the provider (harness) the session runs on, so the second opinion skips it; record only — it binds no tiers.
  --session-model SESSION_MODEL
                        Record the model the session runs on (with --session-provider).
  --session-family SESSION_FAMILY
                        Record the priors (model family) the session answers with; it must be in the family vocabulary (second_opinion_policy.families), which an overlay may extend.
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
 * The `session` stanza to record: the flags over the one already recorded, else none.
 *
 * Record only: it names the harness, model and priors the session runs on so the second opinion
 * knows which carrier to skip and which family to differ from, and gives the harness no tier
 * binding (tier binding stays owned by a vendor block: `--vendor` selects the one a harness with
 * none borrows). A model or family with no provider borrows the recorded one, else the vendor's
 * `carrier`; a provider alone keeps the recorded model only when it is the same provider, and a
 * recorded family only while the model is unchanged — the family belongs to the model (D15). A
 * `--session-family` outside the closed vocabulary is refused (D01).
 * @param {AgentsData} data
 * @param {{vendor: string, sessionProvider: string | null, sessionModel: string | null,
 *   sessionFamily: string | null}} options
 * @param {Json} registry
 * @param {Record<string, Json>} existing the recorded local config
 * @param {string} root
 * @returns {Record<string, string> | null}
 */
function _sessionStanza(data, options, registry, existing, root) {
  const recordedValue = dictGet(existing, "session");
  /** @type {Record<string, Json>} */
  const recorded = isDict(recordedValue) ? recordedValue : {};
  if (!(options.sessionProvider || options.sessionModel || options.sessionFamily)) {
    return Object.keys(recorded).length > 0 ? { ...recorded } : null;
  }
  if (options.sessionFamily) {
    checkSessionFamily(data, registry, options.sessionFamily, root);
  }
  const vendorBlock = dictGet(registry, options.vendor);
  const carrier = isDict(vendorBlock) ? dictGet(vendorBlock, "carrier") : null;
  const provider = options.sessionProvider || dictGet(recorded, "provider") || carrier;
  if (!provider) {
    const flag = options.sessionModel ? "--session-model" : "--session-family";
    throw pyError(
      "ValueError",
      `${flag} needs a provider: pass --session-provider, ${strRepr(options.vendor)} declares no carrier`,
    );
  }
  const sameProvider = dictGet(recorded, "provider") === provider;
  const model = options.sessionModel || (sameProvider ? dictGet(recorded, "model") : null);
  const family =
    options.sessionFamily ||
    (sameProvider && model === dictGet(recorded, "model") ? dictGet(recorded, "family") : null);
  /** @type {Record<string, string>} */
  const stanza = { provider: pyStr(provider) };
  if (model) {
    stanza.model = pyStr(model);
  }
  if (family) {
    stanza.family = pyStr(family);
  }
  return stanza;
}

/**
 * Parse the arguments.
 * @param {string[]} argv
 * @returns {{projectRoot: string | null, vendor: string, orchestrator: string | null, available: string | null,
 *   auditor: string | null, secondOpinion: string | null, sessionProvider: string | null, sessionModel: string | null,
 *   sessionFamily: string | null, check: boolean, dryRun: boolean, help: boolean} | string} the options, or the one-line usage error
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
        auditor: { type: "string" },
        "second-opinion": { type: "string" },
        "session-provider": { type: "string" },
        "session-model": { type: "string" },
        "session-family": { type: "string" },
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
      auditor: /** @type {string | undefined} */ (values.auditor) ?? null,
      secondOpinion,
      sessionProvider: /** @type {string | undefined} */ (values["session-provider"]) ?? null,
      sessionModel: /** @type {string | undefined} */ (values["session-model"]) ?? null,
      sessionFamily: /** @type {string | undefined} */ (values["session-family"]) ?? null,
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
 * The validated `--available` list and the orchestrator alias; a `ValueError` names a refused flag.
 *
 * The orchestrator is `--orchestrator`, else the settings model, else the top of the ladder (the
 * vendor's committed one without `--available`), else the semantic label.
 * @param {AgentsData} data
 * @param {{vendor: string, orchestrator: string | null, available: string | null, auditor: string | null}} options
 * @param {Json} registry
 * @param {string} root
 * @returns {[string[] | null, string]}
 */
function _bindingInputs(data, options, registry, root) {
  const available = options.available
    ? options.available
        .split(",")
        .map((alias) => pyStrip(alias))
        .filter((alias) => alias !== "")
    : null;
  if (available && available.length > 0) {
    checkLadderOrder(data, registry, options.vendor, available);
  }
  if (options.auditor) {
    checkAuditorOptIn(data, registry, options.vendor, available, options.auditor);
  }
  const [rungs, semantic] = selectionLadder(registry, options.vendor, available);
  const fallback = dictGet(dictGet(registry, options.vendor), "semantic_fallback", {});
  const orchestrator =
    (options.orchestrator || null) ??
    _settingsModel(data, root) ??
    (semantic ? dictGet(fallback, "orchestrator", "strongest") : rungs[rungs.length - 1]);
  return [available, orchestrator];
}

/**
 * Whether `exc` is a refused input the initializer reports as one `error:` line and exit 2: a Python
 * `ValueError` or one of the routing module's own refusals (a retired key, an unnamed session).
 * @param {unknown} exc
 * @returns {exc is Error}
 */
function _isRefusal(exc) {
  return (
    exc instanceof RetiredKeyError ||
    exc instanceof OverlayError ||
    exc instanceof SessionUnknownError ||
    (exc instanceof Error && exc.name === "ValueError")
  );
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
  const runtime = /** @type {RuntimeData} */ (read(posix.join(TREE_ROOT, "common", "runtime.json")));
  /** @type {Json} */ let registry;
  try {
    registry = loadRegistry(data, TREE_ROOT, root);
  } catch (exc) {
    if (!(exc instanceof OverlayError)) {
      throw exc;
    }
    process.stderr.write(`error: ${exc.message}\n`);
    return 2;
  }
  const vendors = vendorsWithRoutingPolicy(registry);
  if (!vendors.includes(options.vendor)) {
    process.stderr.write(`${PROG}: error: ${vendorRefusal(data, registry, options.vendor, vendors)}\n`);
    return 2;
  }
  /** @type {string[] | null} */ let available;
  /** @type {string} */ let orchestrator;
  try {
    [available, orchestrator] = _bindingInputs(data, options, registry, root);
  } catch (exc) {
    if (!(exc instanceof Error) || exc.name !== "ValueError") {
      throw exc;
    }
    process.stderr.write(`error: ${exc.message}\n`);
    return 2;
  }
  const secondOpinion =
    options.secondOpinion === null ? _existingSecondOpinion(data, root) : options.secondOpinion === "on";

  /** @type {Record<string, string> | null} */ let session;
  try {
    refuseRetiredKeys(data, registry, {}, root, { layered: true });
    session = _sessionStanza(data, options, registry, _existingConfig(data, root), root);
  } catch (exc) {
    if (!_isRefusal(exc)) {
      throw exc;
    }
    process.stderr.write(`error: ${exc.message}\n`);
    return 2;
  }
  const binding = computeBinding(data, registry, orchestrator, available, options.vendor, options.auditor || null);
  /** @type {Record<string, string>} */ let artifacts;
  try {
    artifacts = bindingArtifacts(data, registry, binding, { secondOpinion, available, session });
  } catch (exc) {
    if (!(exc instanceof BriefError)) {
      throw exc;
    }
    // Nothing is written: generating the definitions without the overlay's briefs would drop
    // hand-authored project instructions, and the sweep below would then delete the only files
    // still carrying them (C50).
    process.stderr.write(`error: ${exc.message}\n`);
    const overlay = pyPath(aitnaRootName(root), overlayName(data));
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

  const [head] = opinionHead(data, runtime, registry, jsonLoads(artifacts[localConfigRel(data)]), root);
  process.stdout.write(
    "model routing: " +
      `vendor=${binding.vendor} · orchestrator=${binding.orchestrator} · reasoner=${binding.reasoner} · ` +
      `auditor=${binding.auditor} · ` +
      `worker=${binding.worker} · mid=${binding.mid} · ` +
      `second-opinion=${head} (${secondOpinion ? "on" : "off"})\n`,
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
