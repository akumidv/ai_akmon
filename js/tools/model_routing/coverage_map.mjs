#!/usr/bin/env node
/**
 * Assemble the coverage map from the delegation log (design §9.4 + §10.3, C17) — the JavaScript
 * twin of `tools/model_routing/coverage_map.py` (C108, ADR 0020 D01). The Python module is the
 * spec: the same map bytes, the same stdout lines, the same `error:` lines, the same exit codes.
 *
 * Which zone/module each fan-out worker was *dispatched to*, derived **from the delegation log by
 * code, not by the orchestrator** — the map costs one tool run, not tokens per gate. The log
 * records the observed dispatch request and makes no launch or completion claim, so a delegation
 * the harness refused or aborted still reads as coverage: read a covered zone as "someone was
 * sent there", and the uncovered list — the output the gate leans on — as the sound half. Each
 * fan-out delegation carries a `[zone:LABEL]` marker in its description (parsed at log-write time
 * by `delegationLogLine` into a zone column); this tool groups the in-scope entries by zone and,
 * given the Decompose/Survey zone plan (§10.3), flags the *uncovered seams* — planned zones no
 * worker touched.
 *
 * Scope: the log is one append-only file across sessions, so a run names its scope — `--session`
 * or an explicit `--all-sessions` — optionally narrowed by `--since`/`--until`. There is no
 * unscoped default. Time bounds compare instants, not strings: a bare date covers its whole day, a
 * bound with no offset is read in local time (the zone the log writer stamps in), and a row whose
 * timestamp is not ISO fails a time-scoped run rather than being silently kept or dropped.
 *
 * Output feeds `gate_pack --coverage-map <path>`.
 *
 * Data (the C102 convention): the texts live in `tools/model_routing/gate.json`, shared with the
 * Python twin and read on the call that needs them.
 *
 * Twin notes (`meta/conformance/DIVERGENCES.md`):
 * - the arguments are parsed by `node:util` `parseArgs` (ADR 0020 D08): a usage error is the one
 *   line `coverage_map.mjs: error: …` on stderr and exit 2 (`argparse` prints its usage block with
 *   every error, names the program `coverage_map.py`, and abbreviates long options), `-h`/`--help`
 *   prints a short usage and exits 0;
 * - the ISO grammar of `--since`/`--until` and of a log timestamp is the extended form
 *   `YYYY-MM-DD[<any char>HH[:MM[:SS[.f…]]][Z|±HH[:MM[:SS]]]]`; the basic (`20260501`) and ISO-week
 *   (`2026-W18-5`) spellings Python 3.11+ also reads are refused as "not ISO";
 * - an input file that cannot be read stops the run with the thrown error, not a Python traceback.
 */

import fs from "node:fs";
import { posix } from "node:path";
import { fileURLToPath } from "node:url";
import { parseArgs } from "node:util";

import { embeddedTreeRoot } from "../../akmon/_tree.mjs";
import { fill, read } from "../../common/jsondata.mjs";
import { aitnaRoot, resolveProjectRoot } from "../../common/project_root.mjs";
import { isFile, pyPath, pySplitlines, pyStrip, readText, strRepr, writeText } from "../../common/pyvalue.mjs";
import { createReport, reportPrefix, taskError } from "../../common/report_path.mjs";
import { codePointSort } from "../../common/sort.mjs";
import { relativeTo } from "./gate_pack.mjs";
import { delegationLogRel, parseDelegationEntries } from "./routing.mjs";

/** @typedef {import("./routing.mjs").AgentsData} AgentsData */
/** @typedef {import("./routing.mjs").DelegationEntry} DelegationEntry */
/**
 * @typedef {object} CoverageData the `coverage_map` section of `gate.json`
 * @property {string[]} table_header
 * @property {string} table_row
 * @property {string} empty_sentinel
 * @property {string} uncovered_heading
 * @property {string} off_plan_heading
 * @property {string} zone_item
 * @property {string} all_covered_sentinel
 * @property {string} unlabelled_marker
 * @property {string} unlabelled_note
 * @property {string} all_unlabelled_error
 * @property {string} summary_entries
 * @property {string} scope_session
 * @property {string} scope_all
 * @property {string} scope_all_none
 */

/** The tree the running module belongs to (it holds `tools/model_routing/gate.json`). */
const TREE_ROOT = embeddedTreeRoot();

const PROG = "coverage_map.mjs";

const USAGE = `usage: ${PROG} [-h] [--project-root PROJECT_ROOT] [--log LOG]
               (--session SESSION | --all-sessions) [--since SINCE]
               [--until UNTIL] [--zone-plan ZONE_PLAN] [--task TASK] [--out OUT]
               [--stdout]

options:
  -h, --help            show this help message and exit
  --project-root PROJECT_ROOT
                        Project root. Defaults to cwd or a parent with AGENTS.md.
  --log LOG             Delegation log. Defaults to <root>/.claude/model-routing.log.
  --session SESSION     Scope to this session_id (the self-describing round key).
  --all-sessions        Union every session in the log — explicit, because it can hide a zone one round left uncovered.
  --since SINCE         Include entries at or after this ISO date/date-time (a bare date: from its start).
  --until UNTIL         Include entries at or before this ISO date/date-time (a bare date: through its end).
  --zone-plan ZONE_PLAN
                        Zone-plan file (§10.3) — enables uncovered-seam detection.
  --task TASK           Task id the map belongs to; prefixes the default name: <task>-coverage-<n>.md.
  --out OUT             Output path. Defaults to <AITNA_ROOT>/artifacts/gates/[<task>-]coverage-<n>.md (gitignored), n the next ordinal.
  --stdout              Also print the coverage map to stdout.
`;

/**
 * The shared coverage-map texts (`gate.json`), read on the call that needs them.
 * @returns {CoverageData}
 */
function _gateData() {
  return /** @type {{coverage_map: CoverageData}} */ (
    read(posix.join(TREE_ROOT, "tools", "model_routing", "gate.json"))
  ).coverage_map;
}

/**
 * The zone label a delegation that carried no `[zone:…]` marker is grouped under.
 * @returns {string}
 */
export function unlabelledMarker() {
  return _gateData().unlabelled_marker;
}

/**
 * The named zones the fan-out was split by — one per line.
 *
 * Blank lines and `#` comments are dropped; a leading `- `/`* ` bullet is stripped. Order
 * preserved, duplicates collapsed.
 * @param {string} text
 * @returns {string[]}
 */
export function parseZonePlan(text) {
  /** @type {string[]} */ const zones = [];
  for (const raw of pySplitlines(text)) {
    let line = pyStrip(raw);
    if (line === "" || line.startsWith("#")) {
      continue;
    }
    if (line.startsWith("- ") || line.startsWith("* ")) {
      line = pyStrip(line.slice(2));
    }
    if (line !== "" && !zones.includes(line)) {
      zones.push(line);
    }
  }
  return zones;
}

/**
 * Python's `str.casefold()` as an equality key: lower, upper, lower again folds `ß`/`ẞ` to `ss`
 * and both sigmas together, the cases a single `toLowerCase()` leaves apart.
 * @param {string} text
 * @returns {string}
 */
function _casefold(text) {
  return text.toLowerCase().toUpperCase().toLowerCase();
}

/**
 * The refusal for a zone plan no delegation is labelled against, else null (C33 review).
 *
 * With a plan and in-scope delegations that all lack a zone label, every planned zone would read
 * as uncovered — a map that says the fan-out missed everything because nobody wrote the label.
 * That is a broken input, not a finding about coverage, so the run fails instead of writing it.
 * @param {Iterable<DelegationEntry>} entries
 * @param {string[] | null} zonePlan
 * @returns {string | null}
 */
export function unlabelledPlanError(entries, zonePlan) {
  const all = [...entries];
  if (zonePlan === null || all.length === 0 || all.some((entry) => entry.zone)) {
    return null;
  }
  return fill(_gateData().all_unlabelled_error, { count: String(all.length) });
}

/**
 * @param {DelegationEntry} entry
 * @returns {string}
 */
function _worker(entry) {
  return entry.model ? `${entry.subagent}/${entry.model}` : entry.subagent;
}

/**
 * Render the coverage map markdown embedded into a gate-pack.
 *
 * `entries` are already scoped to the fan-out round (the CLI does the filtering). With a
 * `zonePlan`, planned zones with no worker surface as *uncovered seams* and worked zones absent
 * from the plan as *off-plan*; a label matches a planned zone case-insensitively.
 * @param {Iterable<DelegationEntry>} entries
 * @param {string[] | null} [zonePlan]
 * @returns {string}
 */
export function buildCoverageMap(entries, zonePlan = null) {
  const data = _gateData();
  const all = [...entries];
  if (all.length === 0) {
    return data.empty_sentinel;
  }
  const unlabelled = data.unlabelled_marker;

  // Group by zone, preserving first-seen order; distinct workers per zone, total count.
  /** @type {Map<string, {workers: string[], count: number}>} */
  const zones = new Map();
  for (const entry of all) {
    const zone = entry.zone || unlabelled;
    let group = zones.get(zone);
    if (group === undefined) {
      group = { workers: [], count: 0 };
      zones.set(zone, group);
    }
    group.count += 1;
    const who = _worker(entry);
    if (!group.workers.includes(who)) {
      group.workers.push(who);
    }
  }
  const order = [...zones.keys()];

  // No "## Coverage map" heading: the gate-pack owns that section header and embeds this
  // body under it (standalone --stdout still reads fine, leading with the table).
  const lines = [...data.table_header];
  for (const zone of order) {
    const group = /** @type {{workers: string[], count: number}} */ (zones.get(zone));
    lines.push(fill(data.table_row, { zone, workers: group.workers.join(", "), count: String(group.count) }));
  }

  if (zonePlan !== null) {
    // Matched case-insensitively (C33 review): `[zone:Auth]` covers a planned `auth`. Both sides
    // keep their spelling in the output; only the comparison folds.
    const labelled = new Set(order.filter((z) => z !== unlabelled).map(_casefold));
    const planned = new Set(zonePlan.map(_casefold));
    const uncovered = zonePlan.filter((z) => !labelled.has(_casefold(z)));
    const offPlan = order.filter((z) => z !== unlabelled && !planned.has(_casefold(z)));

    lines.push("", data.uncovered_heading);
    if (uncovered.length > 0) {
      lines.push(...uncovered.map((z) => fill(data.zone_item, { zone: z })));
    } else {
      lines.push(data.all_covered_sentinel);
    }

    if (offPlan.length > 0) {
      lines.push("", data.off_plan_heading);
      lines.push(...offPlan.map((z) => fill(data.zone_item, { zone: z })));
    }
    const unlabelledGroup = zones.get(unlabelled);
    if (unlabelledGroup !== undefined) {
      lines.push("", fill(data.unlabelled_note, { count: String(unlabelledGroup.count) }));
    }
  }

  return lines.join("\n");
}

// --------------------------------------------------------------------------------------
// CLI
// --------------------------------------------------------------------------------------

/** A timestamp that is not ISO — Python's `ValueError`, which the CLI turns into a usage error. */
export class IsoError extends Error {
  /**
   * @param {string} message
   */
  constructor(message) {
    super(message);
    this.name = "ValueError";
  }
}

// `YYYY-MM-DD`, then optionally one separator character and `HH[:MM[:SS[.f…]]]` with an optional
// `Z` / `±HH[:MM[:SS]]` offset (the extended form `datetime.fromisoformat` reads).
const _ISO =
  /^(\d{4})-(\d{2})-(\d{2})(?:(.)(\d{2})(?::(\d{2})(?::(\d{2})(?:[.,](\d+))?)?)?(Z|[+-]\d{2}(?::?\d{2}(?::?\d{2}(?:[.,]\d+)?)?)?)?)?$/su;

/**
 * An ISO date or date-time as an instant, in microseconds since the epoch; an offset-less value
 * is read in local time (Python's `astimezone()` on a naive `datetime`).
 * @param {string} text
 * @param {boolean} [endOfDay] a bare date: its last instant (`datetime.max.time()`) instead of its first
 * @returns {bigint}
 */
export function parseInstant(text, endOfDay = false) {
  const match = _ISO.exec(text);
  if (match === null) {
    throw new IsoError(`Invalid isoformat string: ${strRepr(text)}`);
  }
  const [, y, mo, d, sep, h, mi, s, frac, zone] = match;
  const year = Number(y);
  const month = Number(mo);
  const day = Number(d);
  if (year < 1) {
    throw new IsoError("year 0 is out of range");
  }
  if (month < 1 || month > 12) {
    throw new IsoError("month must be in 1..12");
  }
  const probe = new Date(Date.UTC(2000, month - 1, 1));
  probe.setUTCFullYear(year, month, 0);
  if (day < 1 || day > probe.getUTCDate()) {
    throw new IsoError("day is out of range for month");
  }
  const bare = sep === undefined;
  if (bare && (h !== undefined || zone !== undefined)) {
    throw new IsoError(`Invalid isoformat string: ${strRepr(text)}`);
  }
  const hour = bare ? (endOfDay ? 23 : 0) : Number(h);
  const minute = bare ? (endOfDay ? 59 : 0) : Number(mi ?? 0);
  const second = bare ? (endOfDay ? 59 : 0) : Number(s ?? 0);
  if (hour > 23) {
    throw new IsoError("hour must be in 0..23");
  }
  if (minute > 59) {
    throw new IsoError("minute must be in 0..59");
  }
  if (second > 59) {
    throw new IsoError("second must be in 0..59");
  }
  const micro = bare ? (endOfDay ? 999999 : 0) : Number((frac ?? "").padEnd(6, "0").slice(0, 6));

  /** @type {number} */ let epochMs;
  if (zone === undefined) {
    // Offset-less: local time.
    const local = new Date(0);
    local.setFullYear(year, month - 1, day);
    local.setHours(hour, minute, second, 0);
    epochMs = local.getTime();
  } else {
    const utc = new Date(0);
    utc.setUTCFullYear(year, month - 1, day);
    utc.setUTCHours(hour, minute, second, 0);
    epochMs = utc.getTime() - _offsetSeconds(zone) * 1000;
  }
  return BigInt(epochMs) * 1000n + BigInt(micro);
}

/**
 * The seconds a `Z` / `±HH[:MM[:SS]]` suffix is ahead of UTC.
 * @param {string} zone
 * @returns {number}
 */
function _offsetSeconds(zone) {
  if (zone === "Z") {
    return 0;
  }
  const digits = zone.slice(1).replace(/:/g, "");
  const hours = Number(digits.slice(0, 2));
  const minutes = Number(digits.slice(2, 4) || 0);
  const seconds = Number(digits.slice(4, 6) || 0);
  if (hours > 23 || minutes > 59 || seconds > 59) {
    throw new IsoError("offset must be a timedelta strictly between -timedelta(hours=24) and timedelta(hours=24).");
  }
  const total = hours * 3600 + minutes * 60 + seconds;
  return zone.startsWith("-") ? -total : total;
}

/**
 * A `--since`/`--until` bound as an instant; {@link IsoError} when it is not ISO.
 *
 * A bare date is the whole day — its first instant as a lower bound, its last as an upper one.
 * Compared as strings instead, `--until 2026-09-02` sorted before every offset-bearing stamp of
 * that day and dropped all of them.
 * @param {string} text
 * @param {boolean} endOfDay
 * @returns {bigint}
 */
export function parseBound(text, endOfDay) {
  return parseInstant(pyStrip(text), endOfDay);
}

/**
 * Whether `entry` is in the run's scope; `session` null is the explicit all-sessions run.
 *
 * Throws {@link IsoError} when a time bound is set and the row's timestamp is not ISO: such a row
 * cannot be placed in time, and keeping or dropping it would both be a guess.
 * @param {DelegationEntry} entry
 * @param {string | null} session
 * @param {bigint | null} since
 * @param {bigint | null} until
 * @returns {boolean}
 */
export function inScope(entry, session, since, until) {
  if (session !== null && entry.sessionId !== session) {
    return false;
  }
  if (since === null && until === null) {
    return true;
  }
  const moment = parseInstant(pyStrip(entry.timestamp));
  return (since === null || moment >= since) && (until === null || moment <= until);
}

/**
 * The session set a run covered — named for the all-sessions run too, since it is a choice.
 * @param {string | null} session
 * @param {DelegationEntry[]} entries
 * @returns {string}
 */
export function describeScope(session, entries) {
  const data = _gateData();
  if (session !== null) {
    return fill(data.scope_session, { session });
  }
  const seen = codePointSort([...new Set(entries.map((entry) => entry.sessionId || "-"))]);
  if (seen.length > 0) {
    return fill(data.scope_all, { count: String(seen.length), sessions: seen.join(", ") });
  }
  return data.scope_all_none;
}

/**
 * Parse the arguments.
 * @param {string[]} argv
 * @returns {{projectRoot: string | null, log: string | null, session: string | null, allSessions: boolean,
 *   since: string | null, until: string | null, zonePlan: string | null, task: string | null, out: string | null,
 *   stdout: boolean, help: boolean} | string} the options, or the one-line usage error
 */
function _parse(argv) {
  try {
    const { values, tokens } = parseArgs({
      args: argv,
      options: {
        "project-root": { type: "string" },
        log: { type: "string" },
        session: { type: "string" },
        "all-sessions": { type: "boolean" },
        since: { type: "string" },
        until: { type: "string" },
        "zone-plan": { type: "string" },
        task: { type: "string" },
        out: { type: "string" },
        stdout: { type: "boolean" },
        help: { type: "boolean", short: "h" },
      },
      allowPositionals: false,
      strict: true,
      tokens: true,
    });
    const str = (/** @type {string} */ key) =>
      /** @type {string | undefined} */ (/** @type {Record<string, unknown>} */ (values)[key]) ?? null;
    const options = {
      projectRoot: str("project-root"),
      log: str("log"),
      session: str("session"),
      allSessions: values["all-sessions"] === true,
      since: str("since"),
      until: str("until"),
      zonePlan: str("zone-plan"),
      task: str("task"),
      out: str("out"),
      stdout: values.stdout === true,
      help: values.help === true,
    };
    if (options.help) {
      return options;
    }
    // The mutually exclusive group: the later flag is the one argparse blames.
    const scope = tokens.filter((t) => t.kind === "option" && (t.name === "session" || t.name === "all-sessions"));
    if (scope.length === 0) {
      return "one of the arguments --session --all-sessions is required";
    }
    const names = scope.map((t) => (t.kind === "option" ? t.name : ""));
    const later = names.find((name) => name !== names[0]);
    if (later !== undefined) {
      return `argument --${later}: not allowed with argument --${names[0]}`;
    }
    return taskError(options.task) ?? options;
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
 * A usage refusal: the one `error:` line on stderr, exit 2 (`argparse`'s `parser.error`).
 * @param {string} message
 * @returns {number}
 */
function _usageError(message) {
  process.stderr.write(`${PROG}: error: ${message}\n`);
  return 2;
}

/**
 * CLI entry point: assemble the scoped coverage map and write it under `artifacts/gates/`.
 * @param {string[]} [argv] the arguments (default: the process's)
 * @returns {number} The process exit code: 0, or 2 on a usage error.
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

  /** @type {Record<string, bigint | null>} */ const bounds = {};
  for (const [flag, text, endOfDay] of /** @type {Array<[string, string | null, boolean]>} */ ([
    ["--since", options.since, false],
    ["--until", options.until, true],
  ])) {
    try {
      bounds[flag] = text !== null ? parseBound(text, endOfDay) : null;
    } catch (exc) {
      if (!(exc instanceof IsoError)) {
        throw exc;
      }
      process.stderr.write(`${PROG}: error: ${flag} ${strRepr(text ?? "")} is not an ISO date or date-time\n`);
      return 2;
    }
  }

  const { root, notice } = resolveProjectRoot(options.projectRoot);
  if (notice) {
    process.stderr.write(`${notice}\n`);
  }
  const data = /** @type {AgentsData} */ (read(posix.join(TREE_ROOT, "tools", "model_routing", "agents.json")));
  const logPath = options.log !== null ? pyPath(options.log) : pyPath(root, delegationLogRel(data));
  if (!isFile(logPath)) {
    return _usageError(`delegation log not found: ${logPath}`);
  }

  /** @type {DelegationEntry[]} */ let entries;
  try {
    entries = parseDelegationEntries(pySplitlines(readText(logPath))).filter((entry) =>
      inScope(entry, options.session, bounds["--since"], bounds["--until"]),
    );
  } catch (exc) {
    if (!(exc instanceof IsoError)) {
      throw exc;
    }
    return _usageError(`a delegation-log row cannot be placed inside --since/--until (${exc.message}); no map written`);
  }
  const zonePlan = options.zonePlan !== null ? parseZonePlan(readText(options.zonePlan)) : null;
  const unlabelled = unlabelledPlanError(entries, zonePlan);
  if (unlabelled !== null) {
    return _usageError(unlabelled);
  }
  const coverage = buildCoverageMap(entries, zonePlan);

  // The default lands under the *configured* dev layer, like every other generated artifact,
  // named [<task>-]coverage-<n>.md, n the next free ordinal, created exclusively (C114).
  /** @type {string} */ let out;
  if (options.out !== null) {
    out = options.out;
    fs.mkdirSync(posix.dirname(out), { recursive: true });
    writeText(out, `${coverage}\n`);
  } else {
    const gatesDir = pyPath(aitnaRoot(root), "artifacts", "gates");
    out = createReport(gatesDir, reportPrefix("coverage", options.task), `${coverage}\n`);
  }

  const marker = unlabelledMarker();
  const zones = new Set(entries.map((e) => e.zone || marker)).size;
  process.stdout.write(
    `${fill(_gateData().summary_entries, { entries: String(entries.length), zones: String(zones) })}\n`,
  );
  process.stdout.write(`scope: ${describeScope(options.session, entries)}\n`);
  process.stdout.write(`map: ${relativeTo(root, out)}\n`);
  if (options.stdout) {
    process.stdout.write("\n");
    process.stdout.write(`${coverage}\n`);
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
