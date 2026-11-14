/**
 * The command line of `akmon tool browser <verb> [options]`: one verb and the options that verb takes.
 * A usage error is a `UsageError`, which the entry point prints as one line and turns into exit 2.
 */

import { parseArgs } from "node:util";

/** A command line that is not valid. */
export class UsageError extends Error {
  /**
   * @param {string} message
   */
  constructor(message) {
    super(message);
    this.name = "UsageError";
  }
}

/** The verbs, in the order the help lists them. */
export const VERBS = /** @type {const} */ ([
  "status",
  "start",
  "stop",
  "restart",
  "attach",
  "detach",
  "install",
  "init",
  "pages",
  "snapshot",
  "screenshot",
  "eval",
  "logs",
  "net",
  "selectors",
  "ext",
  "record",
]);

/** What each verb does, for the help. */
/** @type {Record<(typeof VERBS)[number], string>} */
const _SUMMARY = Object.freeze({
  status: "is the project's Chrome running, whose Chrome answers on the port, tabs, MCP wiring [--json]",
  start: "start Chrome with the project's profile and a loopback DevTools port [--url URL] [--headless]",
  stop: "close the project's Chrome (sign-ins stay in the profile)",
  restart: "stop and start again, to apply a changed proxy or port [--url URL] [--headless]",
  attach:
    "use a Chrome the project did not start, by endpoint: a loopback URL, a port or an endpoint file; never closes it",
  detach: "leave attach mode, closing nothing [--release: also delete the endpoint file a held test run waits on]",
  install:
    "Chrome for Testing into the project when no Chrome is found, or when extensions are configured: a plan, or --yes to run it [--for-extensions]",
  init: "register the akmon-browser MCP server in .mcp.json and look for Chrome (opt-in)",
  pages: "the open page targets: index, id, title, url [--all: every target] [--json]",
  snapshot:
    "the page's accessibility tree as an outline [--page P] [--max-nodes N] [--text: visible text instead] [--json]",
  screenshot:
    "a PNG of the page [--page P] [--viewport WxH|desktop|tablet|phone] [--scheme light|dark] [--full] [--out PATH]",
  eval: "evaluate one JavaScript expression and print its value; it reads, it never changes the page [--page P] [--target T] [--world page|isolated] [--ext E] [--json]",
  logs: "console messages, exceptions and log entries, tagged [page] [extension] [sw] [--page P] [--target T] [--ext E] [--until REGEX] [--timeout SECONDS] [--json]",
  net: "the requests the page makes meanwhile [--page P] [--target T] [--ext E] [--for SECONDS] [--until REGEX] [--failed] [--bodies] [--max-body BYTES] [--out PATH] [--json]",
  selectors:
    "check a selector registry (JSON of name -> [css, fallback ...]) on the page, shadow roots included; exit 1 when one is missing <file> [--page P] [--json]",
  ext: "extensions of the project's Chrome: list [--json] | reload [<id|name>] [--json] | action [<id|name>] [--page P]",
  record:
    "record a session the user drives: start [--name N] [--page P | --all-pages] [--bodies] [--max-body BYTES] | mark [NOTE] | stop | status [--json] | list [--json] | delete <name> | export [NAME] [--around N|last] [--window SECONDS] [--json] | export [NAME] --test playwright [--out PATH]",
});

/** The notes under the verbs in the help. */
const _NOTES = [
  "Inspection verbs (pages ... net) work on the project's Chrome, or on the attached one in attach mode; they never",
  "start a Chrome. --page is an index from `pages`, a target id or part of the URL; the default is the first page.",
  "`net` reloads nothing: the user, or a navigation they asked for, triggers the traffic while it listens.",
  "--target is page (the default), sw (an extension's service worker), popup (an open extension page) or a target id",
  "from `pages --all`; --ext names the extension (an id or a name; the configured one by default).",
  "Secrets are redacted at capture: authorization, cookie and token-like headers, and a floor of JSON keys that [browser] redact adds to.",
  "`record` runs a detached recorder that outlives the command; a typed value is never recorded, a recording stays in the",
  "project's local layer, and nothing leaves the machine unless the user says so.",
];

/** The options each verb takes. */
/** @type {Record<(typeof VERBS)[number], import("node:util").ParseArgsOptionsConfig>} */
const _OPTIONS = Object.freeze({
  status: { json: { type: "boolean" } },
  start: { url: { type: "string" }, headless: { type: "boolean" } },
  stop: {},
  restart: { url: { type: "string" }, headless: { type: "boolean" } },
  attach: {},
  detach: { release: { type: "boolean" } },
  install: { yes: { type: "boolean" }, "for-extensions": { type: "boolean" } },
  init: {},
  pages: { all: { type: "boolean" }, json: { type: "boolean" } },
  snapshot: {
    page: { type: "string" },
    json: { type: "boolean" },
    "max-nodes": { type: "string" },
    text: { type: "boolean" },
  },
  screenshot: {
    page: { type: "string" },
    viewport: { type: "string" },
    scheme: { type: "string" },
    full: { type: "boolean" },
    out: { type: "string" },
  },
  eval: {
    page: { type: "string" },
    json: { type: "boolean" },
    target: { type: "string" },
    world: { type: "string" },
    ext: { type: "string" },
  },
  logs: {
    page: { type: "string" },
    target: { type: "string" },
    ext: { type: "string" },
    until: { type: "string" },
    timeout: { type: "string" },
    json: { type: "boolean" },
  },
  net: {
    page: { type: "string" },
    target: { type: "string" },
    ext: { type: "string" },
    for: { type: "string" },
    until: { type: "string" },
    failed: { type: "boolean" },
    bodies: { type: "boolean" },
    "max-body": { type: "string" },
    out: { type: "string" },
    json: { type: "boolean" },
  },
  selectors: { page: { type: "string" }, json: { type: "boolean" } },
  ext: { page: { type: "string" }, json: { type: "boolean" } },
  record: {
    name: { type: "string" },
    page: { type: "string" },
    "all-pages": { type: "boolean" },
    bodies: { type: "boolean" },
    "max-body": { type: "string" },
    around: { type: "string" },
    window: { type: "string" },
    test: { type: "string" },
    out: { type: "string" },
    json: { type: "boolean" },
  },
});

/**
 * One parsed invocation. The inspection verbs' options are `null` or `false` when not given: the verb
 * applies its defaults.
 * @typedef {object} Invocation
 * @property {"help" | (typeof VERBS)[number]} verb
 * @property {Options} options
 */

/**
 * @typedef {object} Options
 * @property {boolean} json
 * @property {string | null} url
 * @property {boolean} headless
 * @property {boolean} yes
 * @property {boolean} release
 * @property {string | null} endpoint `attach`'s endpoint
 * @property {string | null} expression `eval`'s expression
 * @property {string | null} page `--page`: an index, a target id or part of a URL
 * @property {boolean} all `pages --all`
 * @property {boolean} text `snapshot --text`
 * @property {boolean} full `screenshot --full`
 * @property {number | null} maxNodes `snapshot --max-nodes`
 * @property {string | null} viewport `screenshot --viewport`: `WxH` or a name
 * @property {"light" | "dark" | null} scheme `screenshot --scheme`
 * @property {string | null} out `--out`: where `screenshot` or `net` writes
 * @property {string | null} until `--until`: a regex, validated
 * @property {number | null} timeout `logs --timeout`, seconds
 * @property {number | null} forSeconds `net --for`, seconds
 * @property {boolean} failed `net --failed`
 * @property {boolean} bodies `net --bodies`
 * @property {number | null} maxBody `net --max-body`, bytes
 * @property {boolean} forExtensions `install --for-extensions`
 * @property {string | null} target `--target`: `page`, `sw`, `popup` or a target id
 * @property {"page" | "isolated" | null} world `eval --world`
 * @property {string | null} ext `--ext`, or `ext reload|action`'s `<id|name>`: an extension's id or name
 * @property {string | null} file `selectors`' registry file
 * @property {string | null} sub the sub-command of `ext` (`list`, `reload` or `action`) or of `record` (`start`, `mark`, `stop`, `status`, `list`, `delete`, `export`)
 * @property {string | null} name `record`'s recording: `start --name`, or the `<name>` of `delete` and `export`
 * @property {string | null} note `record mark`'s note
 * @property {boolean} allPages `record start --all-pages`
 * @property {string | null} around `record export --around`: a mark's number from 1, or `last`
 * @property {number | null} window `record export --window`, seconds each side of the mark
 * @property {"playwright" | null} testRunner `record export --test`
 */

/**
 * The help text.
 * @returns {string}
 */
export function helpText() {
  const rows = VERBS.map((verb) => `  ${verb.padEnd(11)} ${_SUMMARY[verb]}`);
  return `usage: akmon tool browser <verb> [options]\n\nA Chrome the user and the agent share, one per project.\n\nverbs:\n${rows.join("\n")}\n\n${_NOTES.join("\n")}\n`;
}

/**
 * Whether a word is a verb.
 * @param {string} word
 * @returns {word is (typeof VERBS)[number]}
 */
function _isVerb(word) {
  return VERBS.some((verb) => verb === word);
}

/** The sub-commands of `ext`. */
const _EXT_SUBS = ["list", "reload", "action"];

/** The sub-commands of `record`, and the options each takes besides the shared ones. */
const _RECORD_SUBS = Object.freeze({
  start: ["name", "page", "all-pages", "bodies", "max-body"],
  mark: [],
  stop: [],
  status: ["json"],
  list: ["json"],
  delete: [],
  export: ["around", "window", "test", "out", "json"],
});

/**
 * How many positional arguments a verb takes: the exact number, or for `ext` a sub-command and an optional name.
 * @param {(typeof VERBS)[number]} verb
 * @returns {{min: number, max: number, names: string}}
 */
function _positionalsOf(verb) {
  if (verb === "ext") {
    return { min: 1, max: 2, names: "list|reload|action" };
  }
  if (verb === "record") {
    return { min: 1, max: 64, names: "start|mark|stop|status|list|delete|export" };
  }
  if (verb === "attach") {
    return { min: 1, max: 1, names: "endpoint" };
  }
  if (verb === "eval") {
    return { min: 1, max: 1, names: "expression" };
  }
  if (verb === "selectors") {
    return { min: 1, max: 1, names: "file" };
  }
  return { min: 0, max: 0, names: "" };
}

/**
 * The options and the positional arguments of a verb's arguments.
 * @param {(typeof VERBS)[number]} verb
 * @param {string[]} args the arguments after the verb
 * @returns {{values: Record<string, string | boolean | undefined>, positionals: string[]}}
 * @throws {UsageError} on an option the verb does not take, a missing positional or an extra argument
 */
function _optionsOf(verb, args) {
  let parsed;
  try {
    parsed = parseArgs({ args, options: _OPTIONS[verb], allowPositionals: true });
  } catch (exc) {
    throw new UsageError(`${verb}: ${exc instanceof Error ? exc.message : String(exc)}`);
  }
  const wanted = _positionalsOf(verb);
  if (parsed.positionals.length < wanted.min) {
    throw new UsageError(`${verb}: the following arguments are required: ${wanted.names}`);
  }
  if (parsed.positionals.length > wanted.max) {
    const hint = verb === "eval" ? " (quote the expression as one argument)" : "";
    throw new UsageError(`${verb}: unrecognized arguments: ${parsed.positionals.slice(wanted.max).join(" ")}${hint}`);
  }
  return {
    values: /** @type {Record<string, string | boolean | undefined>} */ (parsed.values),
    positionals: parsed.positionals,
  };
}

/**
 * A string option, or `null` when it was not given.
 * @param {Record<string, string | boolean | undefined>} values
 * @param {string} name
 * @returns {string | null}
 */
function _text(values, name) {
  const value = values[name];
  return typeof value === "string" ? value : null;
}

/**
 * A positive number option, or `null` when it was not given.
 * @param {(typeof VERBS)[number]} verb
 * @param {Record<string, string | boolean | undefined>} values
 * @param {string} name
 * @param {boolean} integer the number must be whole
 * @returns {number | null}
 * @throws {UsageError} when the value is not a positive number
 */
function _positive(verb, values, name, integer) {
  const text = _text(values, name);
  if (text === null) {
    return null;
  }
  const number = Number(text);
  if (text.trim() === "" || !Number.isFinite(number) || number <= 0 || (integer && !Number.isInteger(number))) {
    throw new UsageError(
      `${verb}: --${name} must be a positive ${integer ? "whole " : ""}number, not ${JSON.stringify(text)}`,
    );
  }
  return number;
}

/**
 * The `--until` regex: it must compile, so a typo fails here and not after a capture.
 * @param {(typeof VERBS)[number]} verb
 * @param {Record<string, string | boolean | undefined>} values
 * @returns {string | null}
 * @throws {UsageError} when the text is not a regular expression
 */
function _until(verb, values) {
  const text = _text(values, "until");
  if (text !== null) {
    try {
      new RegExp(text);
    } catch (exc) {
      throw new UsageError(
        `${verb}: --until ${JSON.stringify(text)} is not a regular expression (${exc instanceof Error ? exc.message : String(exc)})`,
      );
    }
  }
  return text;
}

/**
 * The `--scheme`: `light` or `dark`.
 * @param {Record<string, string | boolean | undefined>} values
 * @returns {"light" | "dark" | null}
 * @throws {UsageError} for any other value
 */
function _scheme(values) {
  const text = _text(values, "scheme");
  if (text !== null && text !== "light" && text !== "dark") {
    throw new UsageError(`screenshot: --scheme must be light or dark, not ${JSON.stringify(text)}`);
  }
  return /** @type {"light" | "dark" | null} */ (text);
}

/**
 * The `--target`: `page`, `sw`, `popup` or a target id.
 * @param {(typeof VERBS)[number]} verb
 * @param {Record<string, string | boolean | undefined>} values
 * @returns {string | null}
 * @throws {UsageError} for a value that is none of them, or `--page` given with a target that is not a page
 */
function _target(verb, values) {
  const text = _text(values, "target");
  if (text === null) {
    return null;
  }
  if (!/^[A-Za-z0-9_-]+$/.test(text)) {
    throw new UsageError(`${verb}: --target must be page, sw, popup or a target id, not ${JSON.stringify(text)}`);
  }
  if (text !== "page" && _text(values, "page") !== null) {
    throw new UsageError(`${verb}: --page picks a page; it has no meaning with --target ${text}`);
  }
  return text;
}

/**
 * The `--world` of `eval`: the page's own, or the extension's isolated one.
 * @param {Record<string, string | boolean | undefined>} values
 * @param {string | null} target the `--target`
 * @returns {"page" | "isolated" | null}
 * @throws {UsageError} for another value, or `isolated` on a target that is not a page
 */
function _world(values, target) {
  const text = _text(values, "world");
  if (text !== null && text !== "page" && text !== "isolated") {
    throw new UsageError(`eval: --world must be page or isolated, not ${JSON.stringify(text)}`);
  }
  if (text === "isolated" && target !== null && target !== "page") {
    throw new UsageError(
      `eval: --world isolated is the content-script world of a page; it has no meaning with --target ${target}`,
    );
  }
  return /** @type {"page" | "isolated" | null} */ (text);
}

/**
 * The `--around` of `record export`: a mark's number from 1, or `last`.
 * @param {Record<string, string | boolean | undefined>} values
 * @returns {string | null}
 * @throws {UsageError} for any other value
 */
function _around(values) {
  const text = _text(values, "around");
  if (text !== null && text !== "last" && !/^[1-9]\d*$/.test(text)) {
    throw new UsageError(
      `record export: --around must be a mark's number from 1, or last, not ${JSON.stringify(text)}`,
    );
  }
  return text;
}

/**
 * The sub-command and the extension name of `ext`.
 * @param {string[]} positionals
 * @param {Record<string, string | boolean | undefined>} values
 * @returns {{sub: string, ext: string | null}}
 * @throws {UsageError} for an unknown sub-command, a name `list` cannot take or an option the sub-command does not use
 */
function _extension(positionals, values) {
  const [sub, name = null] = positionals;
  if (!_EXT_SUBS.includes(sub)) {
    throw new UsageError(
      `ext: unknown sub-command '${sub}' (choose from ${_EXT_SUBS.map((word) => `'${word}'`).join(", ")})`,
    );
  }
  if (sub === "list" && name !== null) {
    throw new UsageError(`ext list: unrecognized arguments: ${name}`);
  }
  if (sub !== "action" && _text(values, "page") !== null) {
    throw new UsageError(`ext ${sub}: --page is only for \`ext action\``);
  }
  if (sub === "action" && values["json"] === true) {
    throw new UsageError("ext action: --json is not offered");
  }
  return { sub, ext: name };
}

/**
 * Whether a sub-command of `record` is one.
 * @param {string} word
 * @returns {word is keyof typeof _RECORD_SUBS}
 */
function _isRecordSub(word) {
  return Object.hasOwn(_RECORD_SUBS, word);
}

/**
 * The options of a sub-command of `record`, each checked against the sub-command that takes it.
 * @param {keyof typeof _RECORD_SUBS} sub
 * @param {Record<string, string | boolean | undefined>} values
 * @throws {UsageError} for an option the sub-command does not take, or two that exclude each other
 */
function _checkRecordOptions(sub, values) {
  /** @type {readonly string[]} */
  const taken = _RECORD_SUBS[sub];
  for (const option of Object.keys(values)) {
    if (!taken.includes(option)) {
      throw new UsageError(`record ${sub}: --${option} is not an option of record ${sub}`);
    }
  }
  if (values["page"] !== undefined && values["all-pages"] === true) {
    throw new UsageError("record start: --page and --all-pages exclude each other");
  }
}

/**
 * The `--test` of `record export`, and the options that cannot go with it or without it.
 * @param {Record<string, string | boolean | undefined>} values
 * @returns {"playwright" | null}
 * @throws {UsageError} for a runner that is not offered, or an option that does not fit
 */
function _draftRunner(values) {
  const test = _text(values, "test");
  if (test !== null && test !== "playwright") {
    throw new UsageError(`record export: --test must be playwright, not ${JSON.stringify(test)}`);
  }
  const reads = values["around"] !== undefined || values["window"] !== undefined || values["json"] === true;
  if (test !== null && reads) {
    throw new UsageError("record export: --test writes a draft test; --around, --window and --json read the timeline");
  }
  _checkTimelineOptions(values, test !== null);
  return test;
}

/**
 * The options of `record export` that depend on which of its two readings it is.
 * @param {Record<string, string | boolean | undefined>} values
 * @param {boolean} draft a test draft is asked for
 * @throws {UsageError} for `--out` without a draft, or `--window` without `--around`
 */
function _checkTimelineOptions(values, draft) {
  if (!draft && values["out"] !== undefined) {
    throw new UsageError("record export: --out is for --test");
  }
  if (values["window"] !== undefined && values["around"] === undefined) {
    throw new UsageError("record export: --window needs --around");
  }
}

/**
 * The sub-command of `record` with its name or note, each option checked against the sub-command that takes it.
 * @param {string[]} positionals
 * @param {Record<string, string | boolean | undefined>} values
 * @returns {{sub: string, name: string | null, note: string | null, testRunner: "playwright" | null}}
 * @throws {UsageError} for an unknown sub-command, an option the sub-command does not take, a missing or extra name, or a conflict
 */
function _record(positionals, values) {
  const [sub, ...rest] = positionals;
  if (!_isRecordSub(sub)) {
    throw new UsageError(
      `record: unknown sub-command '${sub}' (choose from ${Object.keys(_RECORD_SUBS)
        .map((word) => `'${word}'`)
        .join(", ")})`,
    );
  }
  _checkRecordOptions(sub, values);
  return { sub, ..._recordName(sub, rest), testRunner: _draftRunner(values) };
}

/**
 * The name or the note a sub-command of `record` takes after its word.
 * @param {string} sub
 * @param {string[]} rest the positional arguments after the sub-command
 * @returns {{name: string | null, note: string | null}}
 * @throws {UsageError} for a missing name or an argument the sub-command does not take
 */
function _recordName(sub, rest) {
  if (sub === "mark") {
    return { name: null, note: rest.join(" ") };
  }
  if (sub === "delete" || sub === "export") {
    if (sub === "delete" && rest.length === 0) {
      throw new UsageError("record delete: the following arguments are required: name");
    }
    if (rest.length > 1) {
      throw new UsageError(`record ${sub}: unrecognized arguments: ${rest.slice(1).join(" ")}`);
    }
    return { name: rest[0] ?? null, note: null };
  }
  if (rest.length > 0) {
    throw new UsageError(`record ${sub}: unrecognized arguments: ${rest.join(" ")}`);
  }
  return { name: null, note: null };
}

/**
 * The options a verb's positional arguments and its `--target`, `--world` and `--ext` give.
 * @param {(typeof VERBS)[number]} verb
 * @param {{values: Record<string, string | boolean | undefined>, positionals: string[]}} parsed
 * @returns {Pick<Options, "endpoint" | "expression" | "file" | "sub" | "ext" | "target" | "world" | "name" | "note" | "testRunner">}
 */
function _targeting(verb, parsed) {
  const { values, positionals } = parsed;
  const target = _target(verb, values);
  const extension = verb === "ext" ? _extension(positionals, values) : { sub: null, ext: _text(values, "ext") };
  const recording =
    verb === "record" ? _record(positionals, values) : { sub: null, name: null, note: null, testRunner: null };
  return {
    endpoint: verb === "attach" ? positionals[0] : null,
    expression: verb === "eval" ? positionals[0] : null,
    file: verb === "selectors" ? positionals[0] : null,
    sub: verb === "record" ? recording.sub : extension.sub,
    ext: extension.ext,
    name: verb === "record" ? (recording.name ?? _text(values, "name")) : null,
    note: recording.note,
    testRunner: recording.testRunner,
    target,
    world: verb === "eval" ? _world(values, target) : null,
  };
}

/**
 * Parse the arguments after `browser`.
 * @param {string[]} argv
 * @returns {Invocation}
 * @throws {UsageError} on a missing or unknown verb, an option the verb does not take, or an extra argument
 */
export function parseInvocation(argv) {
  const [verb, ...rest] = argv;
  /** @type {Options} */
  const none = {
    json: false,
    url: null,
    headless: false,
    yes: false,
    release: false,
    endpoint: null,
    expression: null,
    page: null,
    all: false,
    text: false,
    full: false,
    maxNodes: null,
    viewport: null,
    scheme: null,
    out: null,
    until: null,
    timeout: null,
    forSeconds: null,
    failed: false,
    bodies: false,
    maxBody: null,
    forExtensions: false,
    target: null,
    world: null,
    ext: null,
    file: null,
    sub: null,
    name: null,
    note: null,
    allPages: false,
    around: null,
    window: null,
    testRunner: null,
  };
  if (verb === undefined || verb === "-h" || verb === "--help" || verb === "help") {
    return { verb: "help", options: none };
  }
  if (!_isVerb(verb)) {
    throw new UsageError(
      `argument verb: invalid choice: '${verb}' (choose from ${VERBS.map((name) => `'${name}'`).join(", ")})`,
    );
  }
  const { values, positionals } = _optionsOf(verb, rest);
  return {
    verb,
    options: {
      ...none,
      ..._targeting(verb, { values, positionals }),
      json: values["json"] === true,
      url: _text(values, "url"),
      headless: values["headless"] === true,
      yes: values["yes"] === true,
      release: values["release"] === true,
      forExtensions: values["for-extensions"] === true,
      page: _text(values, "page"),
      all: values["all"] === true,
      text: values["text"] === true,
      full: values["full"] === true,
      maxNodes: _positive(verb, values, "max-nodes", true),
      viewport: _text(values, "viewport"),
      scheme: _scheme(values),
      out: _text(values, "out"),
      until: _until(verb, values),
      timeout: _positive(verb, values, "timeout", false),
      forSeconds: _positive(verb, values, "for", false),
      failed: values["failed"] === true,
      bodies: values["bodies"] === true,
      maxBody: _positive(verb, values, "max-body", true),
      allPages: values["all-pages"] === true,
      around: _around(values),
      window: _positive(verb, values, "window", false),
    },
  };
}
