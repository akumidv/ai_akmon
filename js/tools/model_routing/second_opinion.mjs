#!/usr/bin/env node
/**
 * Run an advisory second-opinion review through the provider the ladder selects — the JavaScript
 * twin of `tools/model_routing/second_opinion.py` (C108, C162, ADR 0020 D01, ADR 0024). The Python
 * module is the spec: the same files in the same bytes, the same stdout lines, the same
 * `second-opinion:` lines, the same exit codes.
 *
 * The provider is chosen by *model priors* (ADR 0024): one walk over the ladder skips the session's
 * own carrier and every provider that answers with priors or a model already taken, so a second
 * opinion comes from a different mind or is disclosed as the weaker run it is. The runner is called
 * explicitly at a verify/align gate, writes the full external review to the chosen provider's report
 * directory, and prints a short digest; `--list` proposes the ranked candidates without running
 * anything. It is not wired as a blocking hook; owner verification remains the decision point.
 *
 * Data (the C102 convention): `main` reads `tools/model_routing/second_opinion.json`, `gate.json`,
 * `agents.json` and `common/runtime.json` once and passes them down.
 *
 * Twin notes (`meta/conformance/DIVERGENCES.md`):
 * - the arguments are parsed by `node:util` `parseArgs` (ADR 0020 D08): a usage error is the one
 *   line `second_opinion.mjs: error: …` on stderr and exit 2 (`argparse` prints its usage block with
 *   every error, names the program `second_opinion.py`, and abbreviates long options — `--dry`),
 *   `-h`/`--help` prints a short usage and exits 0;
 * - the provider CLI runs through `spawnSync`; a CLI that cannot be started is the one
 *   `second-opinion: could not start …` line and exit 2, its reason spelled as Python spells the
 *   `OSError` for the two common causes (`[Errno 2]`, `[Errno 13]`) and as Node words any other.
 */

import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import { join, posix } from "node:path";
import { fileURLToPath } from "node:url";
import { parseArgs } from "node:util";

import { embeddedTreeRoot } from "../../akmon/_tree.mjs";
import { fill, read } from "../../common/jsondata.mjs";
import { JSONDecodeError, jsonLoads } from "../../common/pyjson.mjs";
import { aitnaRoot, isRelativeTo, resolvePath, resolveProjectRoot } from "../../common/project_root.mjs";
import {
  dictGet,
  isDict,
  isFile,
  pyError,
  pyPath,
  pyStr,
  pyStrip,
  readText,
  universalNewlines,
} from "../../common/pyvalue.mjs";
import { readData as readLearningData } from "../../common/learning.mjs";
import { recordsPackageMode } from "../../common/record.mjs";
import {
  createReport,
  nextReportPath,
  reportPrefix as taskPrefix,
  safeName,
  taskError,
} from "../../common/report_path.mjs";
import {
  OPINION_RANK_SECOND,
  EffortError,
  OverlayError,
  RetiredKeyError,
  SecondOpinionTarget,
  SessionUnknownError,
  UnpinnableModelError,
  UnresolvedAliasError,
  carrierPresent,
  defaultModelToken,
  isModelAlias,
  ladderPinsDefault,
  loadRegistry,
  localConfigRel,
  opinionAsks,
  opinionCarrier,
  opinionChain,
  opinionCommand,
  opinionLastResort,
  opinionPick,
  opinionRepo,
  opinionSkips,
  providerFamily,
  providerRow,
  providers,
  readModelAliases,
  refuseRetiredKeys,
  resolveOpinionChain,
  resolveOpinionModel,
  resolveSession,
  splitModelEffort,
  splitOpinionEntry,
} from "./routing.mjs";

/** @typedef {import("./routing.mjs").AgentsData} AgentsData */
/** @typedef {import("./routing.mjs").SecondOpinionSession} SecondOpinionSession */
/** @typedef {import("./routing.mjs").ProviderAliases} ProviderAliases */
/** @typedef {import("../../common/runtime.mjs").RuntimeData} RuntimeData */
/** @typedef {import("../../common/pyvalue.mjs").Json} Json */

/**
 * The keys of `tools/model_routing/second_opinion.json`.
 * @typedef {object} SecondOpinionData
 * @property {string} prompt
 * @property {string[]} unavailable_notice
 * @property {string} default_report_dir
 * @property {string} report_dir_outside
 * @property {{report_line: string, provider_line: string, result_line: string, skip_line: string,
 *   ask_line: string, warning_line: string}} summary
 * @property {{rank_past_chain: string, no_row: string, carrier_absent: string}} unavailable_reasons
 * @property {{alias: string, unresolved: string, default: string}} model_shown
 * @property {{session: string, candidate: string, empty: string, last_resort: string,
 *   no_last_resort: string, skipped: string, skip: string, asks: string, ask: string,
 *   default_pin: string, alias_ask: string}} listing
 * @property {{own_provider: string, same_priors: string, unknown_priors: string}} pinned_warnings
 * @property {string} last_resort_note
 * @property {{missing_gate: string, bad_rank: string, unknown_vendor: string, default_with_pin: string,
 *   pinned_row: string, not_run: string}} errors
 */

/** The keys of `tools/model_routing/gate.json` this runner reads. */
/** @typedef {{truncation_suffix_report: string}} GateData */

/**
 * Everything `main` reads once and passes down (the C102 convention).
 * @typedef {object} Context
 * @property {SecondOpinionData} texts
 * @property {GateData} gate
 * @property {AgentsData} agents
 * @property {RuntimeData} runtime
 * @property {Record<string, ProviderAliases>} stored the resolved-aliases file, read after the registry (D16)
 * @property {string} root the project root, once resolved: where the overlay files the messages name live (ADR 0022 D09)
 */

/**
 * What a run will use: the target, how it was chosen (D10's `kind`), and the warnings that travel with it.
 * @typedef {object} Choice
 * @property {SecondOpinionTarget} target
 * @property {string} kind
 * @property {string[]} warnings
 */

/**
 * The parsed command line.
 * @typedef {object} Options
 * @property {string | null} projectRoot
 * @property {string | null} provider
 * @property {number} rank
 * @property {boolean} list
 * @property {boolean} defaultModel
 * @property {string | null} sessionProvider
 * @property {string | null} sessionModel
 * @property {string | null} sessionFamily
 * @property {string | null} orchestratorVendor
 * @property {string} gate
 * @property {string} gatePack
 * @property {string | null} task
 * @property {boolean} dryRun
 * @property {boolean} help
 */

/** The tree the running module belongs to (it holds `tools/model_routing/` and `common/runtime.json`). */
const TREE_ROOT = embeddedTreeRoot();

const PROG = "second_opinion.mjs";

const USAGE = `usage: ${PROG} [-h] [--project-root PROJECT_ROOT] [--provider PROVIDER] [--rank RANK]
                         [--list] [--default-model]
                         [--session-provider SESSION_PROVIDER]
                         [--session-model SESSION_MODEL]
                         [--session-family SESSION_FAMILY]
                         [--orchestrator-vendor ORCHESTRATOR_VENDOR] [--gate GATE]
                         [--gate-pack GATE_PACK] [--task TASK] [--dry-run]

Run an advisory second-opinion review through the provider the ladder selects.

options:
  -h, --help            show this help message and exit
  --project-root PROJECT_ROOT
                        Project root. Defaults to cwd or a parent with AGENTS.md.
  --provider PROVIDER   Run this provider, optionally pinned as P[:model], instead of the ladder's choice; it is disclosed as kind=pinned and never counted as diverse.
  --rank RANK           Chain rank to run: 2 second opinion, 3 third, 4 arbiter.
  --list                Print the ranked candidate chain, the skip ledger and the asks, then exit without running.
  --default-model       Run the selected provider on the carrier's own configured model: the pin is dropped for this run. Not with --provider P:model.
  --session-provider SESSION_PROVIDER
                        The provider (harness) the working session runs on.
  --session-model SESSION_MODEL
                        The model the working session runs on.
  --session-family SESSION_FAMILY
                        The priors (model family) of the working session, when not declared.
  --orchestrator-vendor ORCHESTRATOR_VENDOR
                        Deprecated alias of --session-provider: a vendor whose registry block names its \`carrier\`.
  --gate GATE           Verify gate name, e.g. design-align or code-verify.
  --gate-pack GATE_PACK
                        Path to a built gate-pack markdown file (see gate_pack.py).
  --task TASK           Task id the review belongs to; the report is <report_dir>/[<task>-]<gate>-<n>.md, n the next ordinal.
  --dry-run             Print the command and target report path without running it.
`;

/**
 * The tree `registry.json` is read from: the mount for mounted modes, the running tree otherwise.
 *
 * The rule of `bin/sync.py::standard_tree_root`: in package mode there is no
 * `<dev root>/akmon` to read, and the recorded `mount` field decides, so a stale mount
 * directory from a prior mode does not shadow the installed tree.
 * @param {string} projectRoot
 * @returns {string}
 */
export function standardTreeRoot(projectRoot) {
  const mounted = pyPath(aitnaRoot(projectRoot), "akmon");
  if (!recordsPackageMode(projectRoot) && fs.existsSync(mounted) && fs.statSync(mounted).isDirectory()) {
    return mounted;
  }
  return TREE_ROOT;
}

/**
 * A JSON object read from `path`: `{}` when the file is absent, unparsable or not an object.
 * @param {string} path
 * @returns {Record<string, Json>}
 */
export function readJsonObject(path) {
  if (!isFile(path)) {
    return {};
  }
  let value;
  try {
    value = jsonLoads(readText(path));
  } catch (error) {
    if (error instanceof JSONDecodeError) {
      return {};
    }
    throw error;
  }
  return isDict(value) ? /** @type {Record<string, Json>} */ (value) : {};
}

/**
 * The review prompt for `gate` over the gate-pack `material`.
 * @param {SecondOpinionData} texts
 * @param {string} gate
 * @param {string} material
 * @returns {string}
 */
export function reviewPrompt(texts, gate, material) {
  return fill(texts.prompt, { gate, material });
}

/**
 * The skip, stated as a fact plus the one option that is left and what it costs.
 *
 * The gate is skipped rather than downgraded to a same-model reviewer: shared weights reproduce
 * the author's systematic errors and return a confident agreement, which reads exactly like a
 * review and is filed like one. That refusal is the machine's; the weaker check is still worth
 * running sometimes, so it is offered here — to a person, with its boundary attached — instead of
 * being taken automatically and labelled as diversity.
 * @param {SecondOpinionData} texts
 * @param {string} gate
 * @param {number} rank
 * @param {string} reason
 * @returns {string}
 */
export function unavailableNotice(texts, gate, rank, reason) {
  const lines = texts.unavailable_notice;
  return [fill(lines[0], { gate, rank: String(rank) }), fill(lines[1], { reason }), lines[2], lines[3], lines[4]].join(
    "\n",
  );
}

/**
 * `[<task>-]<gate>`: the review's name before its `-<n>.md` ordinal (C114).
 * @param {string} gate
 * @param {string | null} [task]
 * @returns {string}
 */
export function reportPrefix(gate, task = null) {
  return taskPrefix(safeName(gate) || "gate", task);
}

/**
 * The error line for a `report_dir` that resolves outside `root`, else `null`.
 *
 * Reports stay inside the project (C9): the check resolves symlinks and `..` first, so an
 * absolute path, a `../outside` and a link inside the project pointing out are all refused, and
 * it runs before the provider is started or any file is written.
 * @param {SecondOpinionData} texts
 * @param {string} root
 * @param {string} reportDir `root` joined with the configured value
 * @param {string} configured the configured `report_dir`, as written
 * @returns {string | null}
 */
export function reportDirError(texts, root, reportDir, configured) {
  if (isRelativeTo(resolvePath(reportDir), resolvePath(root))) {
    return null;
  }
  return fill(texts.report_dir_outside, { report_dir: configured });
}

/**
 * The row's `report_dir` as written, or the shipped `.<provider>/second-opinion/` when it states none (D12).
 * @param {SecondOpinionData} texts
 * @param {Json} row the provider's row
 * @param {string} provider the provider's id
 * @returns {string}
 */
function configuredReportDir(texts, row, provider) {
  if (Object.hasOwn(row, "report_dir")) {
    return pyStr(dictGet(row, "report_dir"));
  }
  return fill(texts.default_report_dir, { provider });
}

/**
 * The leading `limit` characters of `text` (stripped), with the truncation suffix when cut.
 * @param {GateData} gate
 * @param {string} text
 * @param {number} [limit]
 * @returns {string}
 */
export function digest(gate, text, limit = 1200) {
  const stripped = pyStrip(text);
  const chars = Array.from(stripped);
  if (chars.length <= limit) {
    return stripped;
  }
  return pyStrip(chars.slice(0, limit).join("")) + gate.truncation_suffix_report;
}

/**
 * A model as the report prints it: the id, or `(default)` for the carrier's own.
 * @param {string | null} model
 * @returns {string}
 */
function modelText(model) {
  return model || "(default)";
}

/**
 * The model as the header prints it: `alias→concrete`, or `alias→(unresolved)` without a mapping (D16).
 * @param {Context} ctx
 * @param {Json} registry
 * @param {SecondOpinionTarget} target
 * @returns {string}
 */
function _shownModel(ctx, registry, target) {
  const texts = ctx.texts.model_shown;
  const suffix = target.effort === null ? "" : `@${target.effort}`;
  if (target.model === null || !isModelAlias(ctx.agents, registry, target.provider, target.model, ctx.root)) {
    return modelText(target.model) + suffix;
  }
  try {
    const concrete = resolveOpinionModel(ctx.agents, registry, ctx.stored, target.provider, target.model, ctx.root);
    return fill(texts.alias, { alias: target.model, concrete: String(concrete) }) + suffix;
  } catch (exc) {
    if (exc instanceof UnresolvedAliasError) {
      return fill(texts.unresolved, { alias: target.model }) + suffix;
    }
    throw exc;
  }
}

/**
 * The report-header fields of one run: provider, priors, carrier, repo, model and how it was chosen (D10).
 * @param {Context} ctx
 * @param {Json} registry
 * @param {SecondOpinionTarget} target
 * @param {string} kind
 * @returns {Record<string, string>}
 */
function _identity(ctx, registry, target, kind) {
  return {
    provider: target.provider,
    priors: target.family || "unknown",
    carrier: opinionCarrier(ctx.agents, registry, target.provider, ctx.root),
    repo: opinionRepo(ctx.agents, registry, target.provider, ctx.root),
    model: _shownModel(ctx, registry, target),
    kind,
  };
}

/**
 * The lines that travel with every result: pinned-run warnings, the skip ledger and the asks (D08, D10).
 * @param {Context} ctx
 * @param {Json} registry
 * @param {SecondOpinionSession} session
 * @param {string[]} warnings
 * @returns {string[]}
 */
function _ledgerLines(ctx, registry, session, warnings) {
  const summary = ctx.texts.summary;
  return [
    ...warnings.map((warning) => fill(summary.warning_line, { warning })),
    ...opinionSkips(ctx.agents, ctx.runtime, registry, session, ctx.root).map(([provider, reason]) =>
      fill(summary.skip_line, { provider, reason }),
    ),
    ...opinionAsks(ctx.agents, ctx.runtime, registry, session, ctx.root).map((ask) => fill(summary.ask_line, { ask })),
  ];
}

/**
 * The listing's note that a candidate runs the carrier's own model (`:default` or `--default-model`).
 * @param {Context} ctx
 * @param {Json} registry
 * @param {SecondOpinionTarget} target
 * @param {boolean} defaultModel
 * @returns {string}
 */
function _defaultMark(ctx, registry, target, defaultModel) {
  return defaultModel || ladderPinsDefault(ctx.agents, registry, target.provider) ? ctx.texts.listing.default_pin : "";
}

/**
 * `target` as the run takes it: with `--default-model` the pin is dropped and the carrier's own model runs.
 * @param {SecondOpinionTarget} target
 * @param {boolean} defaultModel
 * @returns {SecondOpinionTarget}
 */
function _unpinned(target, defaultModel) {
  return defaultModel ? new SecondOpinionTarget(target.provider, null, target.family, target.effort) : target;
}

/**
 * One ask per distinct alias among `targets` that has no concrete id yet, naming the refresh command (D16).
 * @param {Context} ctx
 * @param {Json} registry
 * @param {SecondOpinionTarget[]} targets
 * @returns {string[]}
 */
function _aliasAsks(ctx, registry, targets) {
  /** @type {string[]} */
  const asks = [];
  for (const target of targets) {
    if (target.model === null || !isModelAlias(ctx.agents, registry, target.provider, target.model, ctx.root)) {
      continue;
    }
    try {
      resolveOpinionModel(ctx.agents, registry, ctx.stored, target.provider, target.model, ctx.root);
    } catch (exc) {
      if (!(exc instanceof UnresolvedAliasError)) {
        throw exc;
      }
      const ask = fill(ctx.texts.listing.alias_ask, { provider: target.provider, model: target.model });
      if (!asks.includes(ask)) {
        asks.push(ask);
      }
    }
  }
  return asks;
}

/**
 * `--list`: what a run would do — the ranked chain, the last resort or why none exists, the skips and the asks.
 *
 * The last resort is the one a run takes (`_lastResort`, rank 2), whether or not the session's own
 * priors are known: a session of unknown priors still gets the disclosed same-provider run, beside
 * the ask that would make the chain non-empty (ADR 0024/D07, D08). With `--default-model` every
 * candidate is shown unpinned, as the run would take it (D16).
 * @param {Context} ctx
 * @param {Json} registry
 * @param {SecondOpinionSession} session
 * @param {boolean} defaultModel
 */
function _printListing(ctx, registry, session, defaultModel) {
  const texts = ctx.texts.listing;
  /** @param {string} line */
  const out = (line) => process.stdout.write(`${line}\n`);
  out(
    fill(texts.session, {
      provider: session.provider,
      model: modelText(session.model),
      priors: session.family || "unknown",
    }),
  );
  const chain = opinionChain(ctx.agents, ctx.runtime, registry, session, ctx.root).map((target) =>
    _unpinned(target, defaultModel),
  );
  const shown = [...chain];
  chain.forEach((target, index) => {
    const identity = _identity(ctx, registry, target, "chain");
    out(
      fill(texts.candidate, { ...identity, rank: String(index + OPINION_RANK_SECOND) }) +
        _defaultMark(ctx, registry, target, defaultModel),
    );
  });
  if (chain.length === 0) {
    out(texts.empty);
    const last = _lastResort(ctx, registry, session, OPINION_RANK_SECOND);
    if (typeof last === "string") {
      out(fill(texts.no_last_resort, { reason: last }));
    } else {
      const target = _unpinned(last.target, defaultModel);
      shown.push(target);
      out(
        fill(texts.last_resort, _identity(ctx, registry, target, "last-resort")) +
          _defaultMark(ctx, registry, target, defaultModel),
      );
    }
  }
  const skips = opinionSkips(ctx.agents, ctx.runtime, registry, session, ctx.root);
  if (skips.length > 0) {
    out(texts.skipped);
    for (const [provider, reason] of skips) {
      out(fill(texts.skip, { provider, reason }));
    }
  }
  const asks = [
    ...opinionAsks(ctx.agents, ctx.runtime, registry, session, ctx.root),
    ..._aliasAsks(ctx, registry, shown),
  ];
  if (asks.length > 0) {
    out(texts.asks);
    for (const ask of asks) {
      out(fill(texts.ask, { ask }));
    }
  }
}

/**
 * `--provider P[:model]`: the owner's explicit pick, with a warning for each way it fails to be diverse.
 *
 * It runs even when it is the session's own provider or answers with the session's priors — an
 * owner may want exactly that — but it is disclosed `kind=pinned` and never counted as diverse.
 * @param {Context} ctx
 * @param {Json} registry
 * @param {SecondOpinionSession} session
 * @param {string} choice
 * @returns {Choice}
 */
function _pinnedChoice(ctx, registry, session, choice) {
  const [provider, pinned] = splitOpinionEntry(choice);
  providerRow(ctx.agents, registry, provider, ctx.root);
  const [model, effort] = opinionPick(ctx.agents, registry, provider, pinned, ctx.root);
  const family = providerFamily(ctx.agents, registry, provider, ctx.root, model);
  const texts = ctx.texts.pinned_warnings;
  const values = { provider, priors: family || "unknown" };
  /** @type {string[]} */ const warnings = [];
  if (provider === session.provider) {
    warnings.push(fill(texts.own_provider, values));
  } else if (family === null) {
    warnings.push(fill(texts.unknown_priors, values));
  } else if (family === session.family) {
    warnings.push(fill(texts.same_priors, values));
  }
  return { target: new SecondOpinionTarget(provider, model, family, effort), kind: "pinned", warnings };
}

/**
 * The last resort and its disclosure note, or the reason nothing can be run (for the skip notice).
 *
 * The last resort (ADR 0024/D07) applies only to an empty chain at rank 2, and only on the
 * session's own provider, which must have a row and be on `PATH`: otherwise there is nothing to
 * run and the notice says exactly that.
 * @param {Context} ctx
 * @param {Json} registry
 * @param {SecondOpinionSession} session
 * @param {number} rank
 * @returns {Choice | string}
 */
function _lastResort(ctx, registry, session, rank) {
  const texts = ctx.texts.unavailable_reasons;
  const count = opinionChain(ctx.agents, ctx.runtime, registry, session, ctx.root).length;
  if (count > 0 || rank !== OPINION_RANK_SECOND) {
    return fill(texts.rank_past_chain, { count: String(count), rank: String(rank) });
  }
  if (!Object.hasOwn(providers(registry), session.provider)) {
    return fill(texts.no_row, { provider: session.provider });
  }
  if (!carrierPresent(ctx.agents, ctx.runtime, registry, session.provider, ctx.root)) {
    return fill(texts.carrier_absent, { provider: session.provider });
  }
  const note = fill(ctx.texts.last_resort_note, { session_model: modelText(session.model) });
  return {
    target: opinionLastResort(ctx.agents, registry, session, ctx.root),
    kind: "last-resort",
    warnings: [note],
  };
}

/**
 * The run's choice — pinned, the chain's rank, or the disclosed last resort — else the reason nothing can run.
 * @param {Context} ctx
 * @param {Json} registry
 * @param {SecondOpinionSession} session
 * @param {Options} options
 * @returns {Choice | string}
 */
function _choose(ctx, registry, session, options) {
  /** @type {Choice | string} */
  let choice;
  if (options.provider) {
    const [, pinned] = splitOpinionEntry(options.provider);
    const pinnedModel = splitModelEffort(pinned)[0];
    if (options.defaultModel && pinnedModel !== null && pinnedModel !== defaultModelToken(ctx.agents)) {
      throw pyError("ValueError", fill(ctx.texts.errors.default_with_pin, { entry: options.provider }));
    }
    choice = _pinnedChoice(ctx, registry, session, options.provider);
  } else {
    const target = resolveOpinionChain(ctx.agents, ctx.runtime, registry, session, ctx.root, { rank: options.rank });
    choice =
      target !== null ? { target, kind: "chain", warnings: [] } : _lastResort(ctx, registry, session, options.rank);
  }
  return typeof choice === "string" ? choice : { ...choice, target: _unpinned(choice.target, options.defaultModel) };
}

/**
 * The provider the session names on the command line: `--session-provider`, else the deprecated vendor alias.
 *
 * Raises a `ValueError` for a vendor the registry gives no `carrier`, so the owner is told to name
 * the provider instead of the alias resolving to nothing.
 * @param {Context} ctx
 * @param {Json} registry
 * @param {Options} options
 * @returns {string | null}
 */
function _sessionProvider(ctx, registry, options) {
  if (options.sessionProvider || !options.orchestratorVendor) {
    return options.sessionProvider;
  }
  const block = dictGet(registry, options.orchestratorVendor);
  const carrier = isDict(block) ? dictGet(block, "carrier") : null;
  if (!carrier) {
    throw pyError("ValueError", fill(ctx.texts.errors.unknown_vendor, { vendor: options.orchestratorVendor }));
  }
  return pyStr(carrier);
}

/**
 * The reason `spawnSync` could not start a command, spelled as Python's `OSError` is for the common causes.
 * @param {Error & {code?: string}} error
 * @param {string} command
 * @returns {string}
 */
function _startReason(error, command) {
  if (error.code === "ENOENT") {
    return `[Errno 2] No such file or directory: '${command}'`;
  }
  if (error.code === "EACCES") {
    return `[Errno 13] Permission denied: '${command}'`;
  }
  return error.message;
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
        provider: { type: "string" },
        rank: { type: "string" },
        list: { type: "boolean" },
        "default-model": { type: "boolean" },
        "session-provider": { type: "string" },
        "session-model": { type: "string" },
        "session-family": { type: "string" },
        "orchestrator-vendor": { type: "string" },
        gate: { type: "string" },
        "gate-pack": { type: "string" },
        task: { type: "string" },
        "dry-run": { type: "boolean" },
        help: { type: "boolean", short: "h" },
      },
      allowPositionals: false,
      strict: true,
    });
    const rankText = /** @type {string | undefined} */ (values.rank);
    if (rankText !== undefined && !/^\s*[+-]?\d+\s*$/.test(rankText)) {
      return `argument --rank: invalid int value: '${rankText}'`;
    }
    const rank = rankText === undefined ? OPINION_RANK_SECOND : Number(rankText);
    const taskProblem = taskError(/** @type {string | undefined} */ (values.task));
    if (values.help !== true && taskProblem !== null) {
      return taskProblem;
    }
    return {
      projectRoot: /** @type {string | undefined} */ (values["project-root"]) ?? null,
      provider: /** @type {string | undefined} */ (values.provider) ?? null,
      rank,
      list: values.list === true,
      defaultModel: values["default-model"] === true,
      sessionProvider: /** @type {string | undefined} */ (values["session-provider"]) ?? null,
      sessionModel: /** @type {string | undefined} */ (values["session-model"]) ?? null,
      sessionFamily: /** @type {string | undefined} */ (values["session-family"]) ?? null,
      orchestratorVendor: /** @type {string | undefined} */ (values["orchestrator-vendor"]) ?? null,
      gate: /** @type {string | undefined} */ (values.gate) ?? "",
      gatePack: /** @type {string | undefined} */ (values["gate-pack"]) ?? "",
      task: /** @type {string | undefined} */ (values.task) ?? null,
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
 * Whether `exc` is a failure the runner reports as one `second-opinion:` line and exit 2: a Python
 * `ValueError`/`KeyError` or one of the routing module's own refusals.
 * @param {unknown} exc
 * @returns {exc is Error}
 */
function _isReportable(exc) {
  return (
    exc instanceof RetiredKeyError ||
    exc instanceof OverlayError ||
    exc instanceof SessionUnknownError ||
    exc instanceof UnpinnableModelError ||
    exc instanceof UnresolvedAliasError ||
    exc instanceof EffortError ||
    (exc instanceof Error && (exc.name === "ValueError" || exc.name === "KeyError"))
  );
}

/**
 * Choose the target, build its command, and print it (`--dry-run`) or run it and file the report.
 *
 * An alias is replaced by its concrete id before the command is built, and an alias with no id
 * refuses the run, dry or not: the carrier is never sent a name it rejects (ADR 0024/D16).
 * @param {Context} ctx
 * @param {string} root
 * @param {Json} registry
 * @param {SecondOpinionSession} session
 * @param {Options} options
 * @returns {number}
 */
function _run(ctx, root, registry, session, options) {
  const choice = _choose(ctx, registry, session, options);
  if (typeof choice === "string") {
    const notice = unavailableNotice(ctx.texts, options.gate, options.rank, choice);
    process.stdout.write(`${[notice, ..._ledgerLines(ctx, registry, session, [])].join("\n")}\n`);
    return 0;
  }
  const target = choice.target;
  const row = providerRow(ctx.agents, registry, target.provider, ctx.root);
  const configuredDir = configuredReportDir(ctx.texts, row, target.provider);
  const outside = reportDirError(ctx.texts, root, pyPath(root, configuredDir), configuredDir);
  if (outside !== null) {
    process.stderr.write(`${outside}\n`);
    return 2;
  }
  // The resolved form, so the report line is always a path under the (resolved) root.
  const reportDir = resolvePath(pyPath(root, configuredDir));
  const prompt = reviewPrompt(ctx.texts, options.gate, readText(options.gatePack));
  const model = resolveOpinionModel(ctx.agents, registry, ctx.stored, target.provider, target.model, ctx.root);
  const command = opinionCommand(ctx.agents, ctx.runtime, registry, target.provider, ctx.root, {
    model,
    effort: target.effort,
    prompt,
  });
  const prefix = reportPrefix(options.gate, options.task);
  const identity = _identity(ctx, registry, target, choice.kind);
  const summary = ctx.texts.summary;
  const ledger = _ledgerLines(ctx, registry, session, choice.warnings);

  if (options.dryRun) {
    process.stdout.write(`${command.join(" ")}\n`);
    process.stdout.write(
      `${fill(summary.report_line, { path: posix.relative(root, nextReportPath(reportDir, prefix)) })}\n`,
    );
    process.stdout.write(`${fill(summary.provider_line, identity)}\n`);
    for (const line of ledger) {
      process.stdout.write(`${line}\n`);
    }
    return 0;
  }

  const onStdin = pyStr(dictGet(row, "prompt", "argv")) === "stdin";
  // A prompt that travels as an argument leaves the child no use for stdin, and an inherited open
  // pipe can hold a carrier forever (`opencode run` does): fd 0 is the null device, which is EOF.
  // The marker tells hooks of the child this is a second opinion, not a session of the owner's: the
  // learning hook neither counts it nor sends it the reminder (ADR 0026 D07).
  const env = { ...process.env, [readLearningData().second_opinion_variable]: "1" };
  const completed = spawnSync(command[0], command.slice(1), {
    cwd: root,
    env,
    encoding: "utf8",
    maxBuffer: Infinity,
    ...(onStdin ? { input: prompt, stdio: ["pipe", "pipe", "pipe"] } : { stdio: ["ignore", "pipe", "pipe"] }),
  });
  // A child that exits without reading its stdin is not a failure to start (Python's `communicate`
  // swallows the broken pipe the same way).
  if (completed.error && !(onStdin && /** @type {{code?: string}} */ (completed.error).code === "EPIPE")) {
    const reason = _startReason(completed.error, command[0]);
    process.stderr.write(`${fill(ctx.texts.errors.not_run, { command: command[0], reason })}\n`);
    return 2;
  }
  // A signal-killed child is a negative return code in Python.
  const returncode =
    completed.status ?? -(/** @type {Record<string, number>} */ (os.constants.signals)[completed.signal ?? ""] ?? 0);
  // Both twins read the pipes as UTF-8 with an undecodable byte as U+FFFD (`encoding: "utf8"`,
  // C120), then with universal newlines: `\r\n` and a lone `\r` arrive as `\n`, so the report
  // holds the same bytes on both twins (C115).
  const stdout = universalNewlines(completed.stdout);
  const stderr = universalNewlines(completed.stderr);
  let output = pyStrip(stdout);
  if (pyStrip(stderr) !== "") {
    output = pyStrip(`${output}\n\n[stderr]\n${pyStrip(stderr)}`);
  }
  const result = fill(summary.result_line, { ...identity, gate: options.gate, exit: String(returncode) });
  // The report opens with the header and the ledger, so the filed review carries its own provenance.
  const report = createReport(reportDir, prefix, `${[result, ...ledger].join("\n")}\n\n${output}\n`);
  process.stdout.write(`${result}\n`);
  process.stdout.write(`${fill(summary.report_line, { path: posix.relative(root, report) })}\n`);
  for (const line of ledger) {
    process.stdout.write(`${line}\n`);
  }
  if (output) {
    process.stdout.write("\n");
    process.stdout.write(`${digest(ctx.gate, output)}\n`);
  }
  return returncode;
}

/**
 * CLI entry point: pick the provider by priors and run it against a gate pack, or list the candidates.
 * @param {string[]} [argv] the arguments (default: the process's)
 * @returns {number} The process exit code: the provider CLI's, 0 for a skip, a listing or a dry
 *   run, 2 on a usage error, a refused configuration, an unpinnable model, a provider that cannot
 *   be started or a `report_dir` outside the project.
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

  const modelRouting = join(TREE_ROOT, "tools", "model_routing");
  /** @type {Context} */
  const ctx = {
    texts: /** @type {SecondOpinionData} */ (read(join(modelRouting, "second_opinion.json"))),
    gate: /** @type {GateData} */ (read(join(modelRouting, "gate.json"))),
    agents: /** @type {AgentsData} */ (read(join(modelRouting, "agents.json"))),
    runtime: /** @type {RuntimeData} */ (read(join(TREE_ROOT, "common", "runtime.json"))),
    stored: {},
    root: "",
  };
  if (options.rank < OPINION_RANK_SECOND) {
    process.stderr.write(`${PROG}: error: ${fill(ctx.texts.errors.bad_rank, { rank: String(options.rank) })}\n`);
    return 2;
  }
  if (!options.list && !(options.gate && options.gatePack)) {
    process.stderr.write(`${PROG}: error: ${ctx.texts.errors.missing_gate}\n`);
    return 2;
  }

  const { root, notice } = resolveProjectRoot(options.projectRoot);
  if (notice) {
    process.stderr.write(`${notice}\n`);
  }
  ctx.root = root;
  const config = readJsonObject(pyPath(root, localConfigRel(ctx.agents)));
  try {
    const registry = loadRegistry(ctx.agents, standardTreeRoot(root), root);
    refuseRetiredKeys(ctx.agents, registry, config, root, { layered: true });
    ctx.stored = readModelAliases(ctx.agents, root);
    const session = resolveSession(ctx.agents, registry, config, {
      provider: _sessionProvider(ctx, registry, options),
      model: options.sessionModel,
      family: options.sessionFamily,
    });
    if (options.list) {
      _printListing(ctx, registry, session, options.defaultModel);
      return 0;
    }
    return _run(ctx, root, registry, session, options);
  } catch (exc) {
    if (!_isReportable(exc)) {
      throw exc;
    }
    process.stderr.write(`second-opinion: ${exc.message}\n`);
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
