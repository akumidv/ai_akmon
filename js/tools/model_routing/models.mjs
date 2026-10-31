#!/usr/bin/env node
/**
 * Refresh the concrete ids behind a provider's model aliases, on request only — the JavaScript twin
 * of `tools/model_routing/models.py` (ADR 0024/D16, ADR 0020 D01). The Python module is the spec: the
 * same file in the same bytes, the same stdout lines, the same `models:` lines, the same exit codes.
 *
 * A provider row that says `aliases: true` ships unversioned aliases (`luna`, `terra`, `sol`) that
 * its carrier may not accept; the second-opinion runner sends the concrete id kept in the local,
 * generated file `<aitna_root>/local/model-aliases.json`. This tool is the ONE place that reads a
 * carrier's catalog — the file the row's `catalog` declares — and it reads it only when an owner
 * runs it: `--refresh` writes the file, no flag lists what is stored and what a refresh would
 * write, and `--dry-run` previews a refresh. It never calls a carrier and never guesses an id for
 * an alias the catalog does not list.
 *
 * Data (the C102 convention): `main` reads `tools/model_routing/models.json` and `agents.json`
 * once and passes them down.
 *
 * Twin notes (`meta/conformance/DIVERGENCES.md`): the arguments are parsed by `node:util`
 * `parseArgs` (ADR 0020 D08): a usage error is the one line `models.mjs: error: …` on stderr and
 * exit 2 (`argparse` prints its usage block with every error and abbreviates long options),
 * `-h`/`--help` prints a short usage and exits 0.
 */

import fs from "node:fs";
import os from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { parseArgs } from "node:util";

import { embeddedTreeRoot } from "../../akmon/_tree.mjs";
import { fill, read } from "../../common/jsondata.mjs";
import { aitnaRoot, aitnaRootName, resolveProjectRoot } from "../../common/project_root.mjs";
import { dictGet, isDict, isFile, pyError, pyPath, readText } from "../../common/pyvalue.mjs";
import { recordsPackageMode } from "../../common/record.mjs";
import {
  ProviderAliases,
  catalogAliases,
  expandHome,
  loadRegistry,
  localAliasesRel,
  modelAliasesDocument,
  parseCatalog,
  providerRow,
  providers,
  readModelAliases,
  splitModelEffort,
  writeArtifacts,
} from "./routing.mjs";

/** @typedef {import("./routing.mjs").AgentsData} AgentsData */
/** @typedef {import("../../common/pyvalue.mjs").Json} Json */

/**
 * The keys of `tools/model_routing/models.json`.
 * @typedef {object} ModelsData
 * @property {{unknown_provider: string, no_catalog: string, none_declared: string, bad_catalog: string,
 *   missing: string, unreadable: string, invalid: string}} errors
 * @property {{stored: string, stored_none: string, catalog: string, mapped: string, unmapped: string,
 *   client_unknown: string, wrote: string, unchanged: string, would_write: string,
 *   would_leave: string}} output
 */

/**
 * Everything `main` reads once and passes down (the C102 convention).
 * @typedef {object} Context
 * @property {ModelsData} texts
 * @property {AgentsData} agents
 */

/**
 * What a refresh would store for one provider, and which of its aliases the catalog left unmapped.
 * @typedef {object} Plan
 * @property {string} provider
 * @property {ProviderAliases} entry
 * @property {string[]} unmapped
 */

/**
 * The parsed command line.
 * @typedef {object} Options
 * @property {string | null} projectRoot
 * @property {boolean} refresh
 * @property {string | null} provider
 * @property {boolean} dryRun
 * @property {boolean} help
 */

/** The tree the running module belongs to (it holds `tools/model_routing/`). */
const TREE_ROOT = embeddedTreeRoot();

const PROG = "models.mjs";

const USAGE = `usage: ${PROG} [-h] [--project-root PROJECT_ROOT] [--refresh] [--provider PROVIDER]
                 [--dry-run]

Refresh the concrete ids behind a provider's model aliases, on request only (ADR 0024/D16).

options:
  -h, --help            show this help message and exit
  --project-root PROJECT_ROOT
                        Project root. Defaults to cwd or a parent with AGENTS.md.
  --refresh             Write the resolved aliases from the declared catalog.
  --provider PROVIDER   Cover this provider only; default: every row that declares a catalog.
  --dry-run             With --refresh: print what would be written, write nothing.
`;

/**
 * The tree `registry.json` is read from: the mount for mounted modes, the running tree otherwise
 * (the rule of `init.mjs`: the recorded `mount` field decides, never the mere presence of the directory).
 * @param {string} projectRoot
 * @returns {string}
 */
function _standardTreeRoot(projectRoot) {
  const mounted = pyPath(aitnaRoot(projectRoot), "akmon");
  if (!recordsPackageMode(projectRoot) && fs.existsSync(mounted) && fs.statSync(mounted).isDirectory()) {
    return mounted;
  }
  return TREE_ROOT;
}

/**
 * The row's `catalog` as `[file, format]`; a `ValueError` when the row has none or it is malformed.
 * @param {Context} ctx
 * @param {Json} registry
 * @param {string} provider
 * @param {string} root
 * @returns {[string, string]}
 */
function _catalogDeclaration(ctx, registry, provider, root) {
  const texts = ctx.texts.errors;
  const declared = dictGet(providerRow(ctx.agents, registry, provider, root), "catalog");
  if (declared === null) {
    throw pyError("ValueError", fill(texts.no_catalog, { provider }));
  }
  const file = isDict(declared) ? dictGet(declared, "file") : null;
  const format = isDict(declared) ? dictGet(declared, "format") : null;
  if (typeof file !== "string" || typeof format !== "string") {
    throw pyError("ValueError", fill(texts.bad_catalog, { provider }));
  }
  return [file, format];
}

/**
 * Read the provider's declared catalog and map each of the row's aliases; the only read of a catalog.
 * @param {Context} ctx
 * @param {Json} registry
 * @param {string} provider
 * @param {string} home
 * @param {string} root
 * @returns {Plan}
 */
function _plan(ctx, registry, provider, home, root) {
  const texts = ctx.texts.errors;
  const [file, format] = _catalogDeclaration(ctx, registry, provider, root);
  const values = { file, provider };
  const path = expandHome(file, home);
  if (!isFile(path)) {
    throw pyError("ValueError", fill(texts.missing, values));
  }
  let text;
  try {
    text = readText(path);
  } catch {
    throw pyError("ValueError", fill(texts.unreadable, values));
  }
  let catalog;
  try {
    catalog = parseCatalog(ctx.agents, text, format);
  } catch (exc) {
    if (!(exc instanceof Error) || exc.name !== "ValueError") {
      throw exc;
    }
    throw pyError("ValueError", fill(texts.invalid, { ...values, reason: exc.message }));
  }
  const listed = dictGet(providerRow(ctx.agents, registry, provider, root), "models");
  // An entry may carry an @effort (ADR 0024/D17); the alias is the model before it, listed once.
  const bare = (Array.isArray(listed) ? listed : []).map((entry) => splitModelEffort(String(entry))[0]);
  const models = [...new Set(bare.filter((model) => model !== null))];
  const mapped = catalogAliases(catalog, models);
  return {
    provider,
    entry: new ProviderAliases(`${file} (${format})`, catalog.client, mapped),
    unmapped: models.filter((model) => !Object.hasOwn(mapped, model)),
  };
}

/**
 * The providers a run covers: the named one, else every row that declares a `catalog`.
 * @param {Context} ctx
 * @param {Json} registry
 * @param {string | null} provider
 * @returns {string[]}
 */
function _selected(ctx, registry, provider) {
  const rows = providers(registry);
  if (provider !== null) {
    if (!Object.hasOwn(rows, provider)) {
      throw pyError("ValueError", fill(ctx.texts.errors.unknown_provider, { provider }));
    }
    return [provider];
  }
  const declared = Object.entries(rows)
    .filter(([, row]) => isDict(row) && Object.hasOwn(row, "catalog"))
    .map(([name]) => name);
  if (declared.length === 0) {
    throw pyError("ValueError", ctx.texts.errors.none_declared);
  }
  return declared;
}

/**
 * One provider's block: its header line (`label` says stored or catalog) and one line per alias.
 * @param {Context} ctx
 * @param {string} provider
 * @param {ProviderAliases} entry
 * @param {"stored" | "catalog"} label
 * @param {string[]} [unmapped]
 * @returns {string[]}
 */
function _entryLines(ctx, provider, entry, label, unmapped = []) {
  const output = ctx.texts.output;
  const client = entry.client !== null ? entry.client : output.client_unknown;
  return [
    fill(output[label], { provider, source: entry.source, client }),
    ...Object.entries(entry.aliases).map(([alias, concrete]) => fill(output.mapped, { alias, concrete })),
    ...unmapped.map((alias) => fill(output.unmapped, { alias })),
  ];
}

/**
 * What the local file holds for each of `names`.
 * @param {Context} ctx
 * @param {Record<string, ProviderAliases>} stored
 * @param {string[]} names
 * @returns {string[]}
 */
function _storedLines(ctx, stored, names) {
  /** @type {string[]} */
  const lines = [];
  for (const provider of names) {
    if (Object.hasOwn(stored, provider)) {
      lines.push(..._entryLines(ctx, provider, stored[provider], "stored"));
    } else {
      lines.push(fill(ctx.texts.output.stored_none, { provider }));
    }
  }
  return lines;
}

/**
 * Parse the arguments.
 * @param {string[]} argv
 * @returns {Options | string} the options, or the one-line usage error
 */
function _parse(argv) {
  try {
    const { values } = parseArgs({
      args: argv,
      options: {
        "project-root": { type: "string" },
        refresh: { type: "boolean" },
        provider: { type: "string" },
        "dry-run": { type: "boolean" },
        help: { type: "boolean", short: "h" },
      },
      allowPositionals: false,
      strict: true,
    });
    return {
      projectRoot: /** @type {string | undefined} */ (values["project-root"]) ?? null,
      refresh: values.refresh === true,
      provider: /** @type {string | undefined} */ (values.provider) ?? null,
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
 * What the local file holds; a generated file that is not valid is replaced by a refresh, not repaired.
 * @param {Context} ctx
 * @param {string} root
 * @param {boolean} refresh
 * @returns {Record<string, ProviderAliases>}
 */
function _stored(ctx, root, refresh) {
  try {
    return readModelAliases(ctx.agents, root);
  } catch (exc) {
    if (!refresh || !_isReportable(exc)) {
      throw exc;
    }
    return {};
  }
}

/**
 * Plan every selected provider (nothing is written unless all of them planned), then list, preview or write.
 * @param {Context} ctx
 * @param {string} root
 * @param {Json} registry
 * @param {Options} options
 * @param {string} home
 * @returns {number}
 */
function _run(ctx, root, registry, options, home) {
  const names = _selected(ctx, registry, options.provider);
  const plans = names.map((provider) => _plan(ctx, registry, provider, home, root));
  const stored = _stored(ctx, root, options.refresh);
  /** @type {string[]} */
  const lines = options.refresh ? [] : _storedLines(ctx, stored, names);
  for (const plan of plans) {
    lines.push(..._entryLines(ctx, plan.provider, plan.entry, "catalog", plan.unmapped));
  }
  /** @type {Record<string, ProviderAliases>} */
  const merged = { ...stored };
  for (const plan of plans) {
    merged[plan.provider] = plan.entry;
  }
  const relative = `${aitnaRootName(root)}/${localAliasesRel(ctx.agents)}`;
  const writing = options.refresh && !options.dryRun;
  const changed = writeArtifacts(root, { [relative]: modelAliasesDocument(merged) }, { write: writing }).length > 0;
  const verdict = /** @type {"wrote" | "unchanged" | "would_write" | "would_leave"} */ (
    writing ? (changed ? "wrote" : "unchanged") : changed ? "would_write" : "would_leave"
  );
  lines.push(fill(ctx.texts.output[verdict], { file: relative }));
  process.stdout.write(`${lines.join("\n")}\n`);
  return 0;
}

/**
 * Whether `exc` is a failure the tool reports as one `models:` line and exit 2.
 * @param {unknown} exc
 * @returns {exc is Error}
 */
function _isReportable(exc) {
  return exc instanceof Error && (exc.name === "ValueError" || exc.name === "KeyError" || exc.name === "OverlayError");
}

/**
 * The data files the tool reads, once.
 * @returns {Context}
 */
function _context() {
  const modelRouting = join(TREE_ROOT, "tools", "model_routing");
  return {
    texts: /** @type {ModelsData} */ (read(join(modelRouting, "models.json"))),
    agents: /** @type {AgentsData} */ (read(join(modelRouting, "agents.json"))),
  };
}

/**
 * CLI entry point: refresh the resolved aliases from the declared catalog, or list what is stored.
 * @param {string[]} [argv] the arguments (default: the process's)
 * @returns {number} The process exit code: 0 on a listing, a preview or a refresh, 2 on a usage
 *   error or a refusal (an unknown provider or one without a catalog, a missing or unreadable catalog).
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
  const ctx = _context();
  const { root, notice } = resolveProjectRoot(options.projectRoot);
  if (notice) {
    process.stderr.write(`${notice}\n`);
    if (options.refresh && !options.dryRun) {
      // The resolved aliases are a file of the local layer, and with no project root there is none (ADR 0022 D09).
      return 2;
    }
  }
  try {
    const registry = loadRegistry(ctx.agents, _standardTreeRoot(root), root);
    return _run(ctx, root, registry, options, process.env.HOME || os.homedir());
  } catch (exc) {
    if (!_isReportable(exc)) {
      throw exc;
    }
    process.stderr.write(`models: ${exc.message}\n`);
    return 2;
  }
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
