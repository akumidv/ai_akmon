/**
 * What a recording says once it has been recorded: the timeline a person or an agent reads (the whole of it,
 * or the stretch around a mark, which is the "what just went wrong" read), the one-line summary `record stop`
 * prints, and a draft end-to-end test for the project's own runner. Pure functions from events to text: a test
 * reads them without a browser.
 */

import { ACTION_KINDS } from "./record-events.mjs";
import { isFailed } from "./ops.mjs";
import { BrowserError } from "./settings.mjs";

/**
 * @typedef {import("./record-events.mjs").RecordedEvent} RecordedEvent
 * @typedef {import("./record-events.mjs").Descriptor} Descriptor
 */

/** How long after an action a request still counts as caused by it, in milliseconds. */
const _CAUSE_MS = 2000;
/** The default stretch each side of a mark, in seconds. */
export const DEFAULT_WINDOW_SECONDS = 15;
const _ACTIONS = new Set(ACTION_KINDS);

/**
 * The events in time order; events of the same time keep the order of the file.
 * A request is written when it ends but stamped when it began, so the file order is not the time order.
 * @param {readonly RecordedEvent[]} events
 * @returns {RecordedEvent[]}
 */
export function sortedEvents(events) {
  return [...events].sort((a, b) => a.t - b.t);
}

/**
 * The marks of a recording, in time order.
 * @param {readonly RecordedEvent[]} events
 * @returns {RecordedEvent[]}
 */
export function marksOf(events) {
  return sortedEvents(events).filter((event) => event.kind === "mark");
}

/**
 * The mark `--around` names: its number from 1, or `last`.
 * @param {readonly RecordedEvent[]} events
 * @param {string} which `last` or a number from 1
 * @returns {{mark: RecordedEvent, number: number}}
 * @throws {BrowserError} when the recording has no mark, or none has that number
 */
export function markAt(events, which) {
  const marks = marksOf(events);
  if (marks.length === 0) {
    throw new BrowserError("the recording has no mark; add one while it runs: akmon tool browser record mark [NOTE]");
  }
  const number = which === "last" ? marks.length : Number(which);
  if (!Number.isInteger(number) || number < 1 || number > marks.length) {
    throw new BrowserError(
      `--around ${JSON.stringify(which)}: the recording has ${marks.length} mark(s), numbered from 1, or use last`,
    );
  }
  return { mark: marks[number - 1], number };
}

/**
 * The events within `windowSeconds` before and after a time.
 * @param {readonly RecordedEvent[]} events
 * @param {{t: number, windowSeconds: number}} around
 * @returns {RecordedEvent[]}
 */
export function eventsAround(events, around) {
  const reach = around.windowSeconds * 1000;
  return sortedEvents(events).filter((event) => event.t >= around.t - reach && event.t <= around.t + reach);
}

/**
 * @param {string} text
 * @param {number} limit
 * @returns {string}
 */
function _clip(text, limit) {
  const flat = text.replace(/\s+/g, " ").trim();
  return flat.length > limit ? `${flat.slice(0, limit - 1)}…` : flat;
}

/**
 * Where a user event happened, in one phrase: `button "Pay" [testid=pay]`.
 * @param {Descriptor | undefined} target
 * @returns {string}
 */
export function describeTarget(target) {
  if (target === undefined) {
    return "";
  }
  const word = target.role || target.tag || "element";
  const shown = target.name || target.label || target.text;
  const find = target.testid ? ` [testid=${target.testid}]` : target.id ? ` #${target.id}` : "";
  return `${word}${shown ? ` ${JSON.stringify(shown)}` : ""}${find}${target.sensitive ? " (sensitive)" : ""}`;
}

/**
 * @param {RecordedEvent} event an `input` or `change`
 * @returns {string}
 */
function _valueText(event) {
  const length = typeof event["length"] === "number" ? ` (${event["length"]} chars)` : "";
  const state = typeof event["checked"] === "boolean" ? (event["checked"] ? " (checked)" : " (unchecked)") : "";
  return `${describeTarget(event["target"])}${length}${state}`;
}

/**
 * @param {RecordedEvent} event a `console` or `log` event
 * @returns {string}
 */
function _consoleText(event) {
  return `${event["level"] ?? ""} ${_clip(String(event["text"] ?? ""), 200)}`.trim();
}

/**
 * @param {RecordedEvent} event an `exception`, `warning` or `error`
 * @returns {string}
 */
function _messageText(event) {
  return _clip(String(event["text"] ?? ""), 200);
}

/**
 * How each kind of event reads on its line.
 * @type {Record<string, (event: RecordedEvent) => string>}
 */
const _TEXT = {
  page: (event) => `${event["url"]}${event["title"] ? ` "${event["title"]}"` : ""}`,
  navigation: (event) => `${event["url"]}${event["within"] ? " (same document)" : ""}`,
  click: (event) => describeTarget(event["target"]),
  submit: (event) => describeTarget(event["target"]),
  keydown: (event) => `${event["key"]} in ${describeTarget(event["target"])}`,
  input: _valueText,
  change: _valueText,
  console: _consoleText,
  log: _consoleText,
  exception: _messageText,
  warning: _messageText,
  error: _messageText,
  net: (event) => _netText(event),
  start: (event) => `recording ${event["name"]} began`,
  stop: (event) =>
    `recording ended (${event["reason"]})${event["text"] ? `: ${_clip(String(event["text"]), 120)}` : ""}`,
};

/**
 * The one line of text an event is shown as, without its time.
 * @param {RecordedEvent} event
 * @returns {string}
 */
function _eventText(event) {
  const text = Object.hasOwn(_TEXT, event.kind) ? _TEXT[event.kind] : undefined;
  return text === undefined ? _clip(JSON.stringify(event), 200) : text(event);
}

/**
 * @param {RecordedEvent} event a `net` event
 * @returns {string}
 */
function _netText(event) {
  const failed = isFailed(/** @type {any} */ (event));
  const outcome = event["failure"] ? `FAILED ${event["failure"]}` : String(event["status"] ?? "?");
  const took = typeof event["ms"] === "number" ? ` ${event["ms"]} ms` : "";
  const type = event["type"] ? ` [${event["type"]}]` : "";
  return `${failed ? "! " : ""}${event["method"]} ${outcome}${took} ${_clip(String(event["url"]), 160)}${type}`;
}

/**
 * The seconds of an event, as the timeline writes them.
 * @param {number} t milliseconds
 * @returns {string}
 */
function _seconds(t) {
  return `+${(t / 1000).toFixed(3)}s`;
}

/**
 * The first line of a timeline: which recording, and which stretch of it.
 * @param {string} name
 * @param {{all: readonly RecordedEvent[], shown: readonly RecordedEvent[], around: {mark: RecordedEvent, number: number, windowSeconds: number} | null}} what
 * @returns {string}
 */
function _head(name, what) {
  const { all, shown, around } = what;
  if (around === null) {
    return `recording ${name}: ${all.length} events, ${_seconds(all.at(-1)?.t ?? 0).slice(1)}`;
  }
  return `recording ${name}: around mark #${around.number} at ${_seconds(around.mark.t)} (${around.windowSeconds} s each side), ${shown.length} of ${all.length} events`;
}

/**
 * The line that says which action a request followed, or `null` when the action is the line above or too far back.
 * @param {RecordedEvent} request
 * @param {{action: RecordedEvent | null, previous: RecordedEvent | null}} before
 * @returns {string | null}
 */
function _afterLine(request, before) {
  const { action, previous } = before;
  if (action === null || previous === action || request.t - action.t > _CAUSE_MS) {
    return null;
  }
  return `${" ".repeat(11)}after ${action.kind} ${describeTarget(action["target"])} (${_seconds(action.t)}, ${request.t - action.t} ms before)`;
}

/**
 * The lines of the timeline: relative time, kind and one line each. A request is shown with the action that
 * preceded it (within two seconds) on the line above, unless that action is the line above.
 * @param {readonly RecordedEvent[]} events the recording's events
 * @param {{name: string, around: {mark: RecordedEvent, number: number, windowSeconds: number} | null}} how
 * @returns {string[]}
 */
export function timelineLines(events, how) {
  const all = sortedEvents(events);
  const shown =
    how.around === null ? all : eventsAround(all, { t: how.around.mark.t, windowSeconds: how.around.windowSeconds });
  const withPage = new Set(all.flatMap((event) => (event.page === undefined ? [] : [event.page]))).size > 1;
  /** @type {string[]} */
  const lines = [_head(how.name, { all, shown, around: how.around })];
  /** @type {RecordedEvent | null} */
  let action = null;
  /** @type {RecordedEvent | null} */
  let previous = null;
  for (const event of all) {
    if (shown.includes(event)) {
      const after = event.kind === "net" ? _afterLine(event, { action, previous }) : null;
      lines.push(...(after === null ? [] : [after]), _line(event, withPage));
      previous = event;
    }
    action = _ACTIONS.has(event.kind) ? event : action;
  }
  return lines;
}

/**
 * @param {RecordedEvent} event
 * @param {boolean} withPage
 * @returns {string}
 */
function _line(event, withPage) {
  const kind = event.kind === "mark" ? `MARK` : event.kind;
  const text = event.kind === "mark" ? `${event["note"] ?? ""}`.trim() : _eventText(event);
  const page = withPage ? `${(event.page ?? "").padEnd(3)}  ` : "";
  return `${_seconds(event.t).padStart(10)}  ${kind.padEnd(10)}  ${page}${text}`;
}

/**
 * The lines `record stop` prints for a recording: what it holds, counted.
 * @param {string} name
 * @param {import("./record-store.mjs").Summary} summary
 * @returns {string[]}
 */
export function summaryLines(name, summary) {
  const kinds = Object.entries(summary.byKind)
    .filter(([kind]) => kind !== "start" && kind !== "stop")
    .map(([kind, count]) => `${kind} ${count}`)
    .join(", ");
  return [
    `recording ${name}: ${summary.events} events over ${(summary.durationMs / 1000).toFixed(1)} s${summary.skipped > 0 ? ` (${summary.skipped} unreadable line(s) left out)` : ""}`,
    `  by kind: ${kinds || "none"}`,
    `  marks: ${summary.marks}; failed requests: ${summary.failedRequests}; exceptions: ${summary.exceptions}`,
  ];
}

// ---------------------------------------------------------------- the draft test

/**
 * A string as a single-quoted JavaScript literal.
 * @param {string} text
 * @returns {string}
 */
function _quote(text) {
  return `'${text.replace(/\\/g, "\\\\").replace(/'/g, "\\'").replace(/\r?\n/g, "\\n")}'`;
}

/**
 * How a Playwright locator finds the element: a test id, a role with its name, a label, a short text, else a
 * CSS path that says it should be replaced.
 * @param {Descriptor} target
 * @returns {{code: string, todo: boolean}}
 */
export function locatorOf(target) {
  if (target.testid) {
    return { code: `page.getByTestId(${_quote(target.testid)})`, todo: false };
  }
  if (target.role && target.name) {
    return { code: `page.getByRole(${_quote(target.role)}, { name: ${_quote(target.name)} })`, todo: false };
  }
  if (target.label) {
    return { code: `page.getByLabel(${_quote(target.label)})`, todo: false };
  }
  if (target.text && !target.sensitive) {
    return { code: `page.getByText(${_quote(target.text)})`, todo: false };
  }
  return { code: `page.locator(${_quote(target.css || "body")})`, todo: true };
}

/**
 * The environment variable a secret field's value is read from in the draft.
 * @param {Descriptor} target
 * @returns {string}
 */
function _envName(target) {
  const word = (target.nameAttr || target.id || target.label || "secret")
    .replace(/[^A-Za-z0-9]+/g, "_")
    .replace(/^[\d_]+|_+$/g, "");
  return (word || "secret").toUpperCase();
}

/**
 * @param {Descriptor | undefined} target
 * @returns {string} a key that tells fields apart
 */
function _fieldKey(target) {
  return target === undefined ? "" : `${target.css}|${target.id}|${target.nameAttr}`;
}

/**
 * @param {Descriptor | undefined} target
 * @returns {boolean} whether it is a form control a user types into or chooses in
 */
function _isControl(target) {
  return target !== undefined && ["input", "textarea", "select"].includes(target.tag);
}

/**
 * One step of the draft: the lines before the action, the action, and the lines after it.
 * @typedef {object} Step
 * @property {RecordedEvent} event the action's last event
 * @property {string} action the statement, without `await` or a trailing comment
 * @property {string} comment a trailing comment, or an empty text
 */

/**
 * The actions of the page the draft follows, folded into steps: a run of `input` and `change` events on one
 * field is one step, and a click that only focuses or toggles a control the next event then fills or changes
 * is left out.
 * @param {readonly RecordedEvent[]} events the page's events in time order
 * @returns {Step[]}
 */
function _steps(events) {
  const actions = events.filter((event) => _ACTIONS.has(event.kind) && event.kind !== "submit");
  /** @type {Step[]} */
  const steps = [];
  for (let at = 0; at < actions.length; at += 1) {
    const event = actions[at];
    if (event.kind === "click") {
      if (!_onlyFocuses(event, actions[at + 1])) {
        steps.push(_step(event, "click()", ""));
      }
    } else if (event.kind === "keydown") {
      steps.push(_step(event, `press(${_quote(String(event["key"]))})`, ""));
    } else {
      const last = _lastOnField(actions, at);
      steps.push(_valueStep(actions[last]));
      at = last;
    }
  }
  return steps;
}

/**
 * Whether an event is a value event on the field of another.
 * @param {RecordedEvent | undefined} event
 * @param {Descriptor} target
 * @returns {boolean}
 */
function _valueOn(event, target) {
  return (
    event !== undefined &&
    (event.kind === "input" || event.kind === "change") &&
    _fieldKey(event["target"]) === _fieldKey(target)
  );
}

/**
 * Whether a click only focuses or toggles a control that the next event then fills or changes.
 * @param {RecordedEvent} click
 * @param {RecordedEvent | undefined} next
 * @returns {boolean}
 */
function _onlyFocuses(click, next) {
  const target = /** @type {Descriptor} */ (click["target"]);
  return _isControl(target) && _valueOn(next, target);
}

/**
 * Where a run of value events on one field ends.
 * @param {readonly RecordedEvent[]} actions
 * @param {number} from the run's first event
 * @returns {number} the index of its last event
 */
function _lastOnField(actions, from) {
  const target = /** @type {Descriptor} */ (actions[from]["target"]);
  let last = from;
  while (_valueOn(actions[last + 1], target)) {
    last += 1;
  }
  return last;
}

/**
 * @param {RecordedEvent} event
 * @param {string} call the method call on the locator
 * @param {string} comment
 * @returns {Step}
 */
function _step(event, call, comment) {
  const locator = locatorOf(event["target"]);
  return {
    event,
    action: `${locator.code}.${call}`,
    comment: [comment, locator.todo ? "TODO: a stable locator" : ""].filter(Boolean).join("; "),
  };
}

/**
 * The step a typed or chosen value becomes: a placeholder, never the value.
 * @param {RecordedEvent} event the last `input` or `change` of the run
 * @returns {Step}
 */
function _valueStep(event) {
  const target = /** @type {Descriptor} */ (event["target"]);
  if (target.type === "checkbox" || target.type === "radio") {
    return _step(event, event["checked"] === false ? "uncheck()" : "check()", "");
  }
  if (target.tag === "select") {
    return _step(event, `selectOption(${_quote("TODO_OPTION")})`, "choose the option the recording chose");
  }
  if (target.sensitive) {
    return _step(
      event,
      `fill(process.env.${_envName(target)} ?? '')`,
      "sensitive field: its value was never recorded; supply it from the environment",
    );
  }
  const typed = typeof event["length"] === "number" ? `typed ${event["length"]} characters` : "";
  return _step(event, `fill(${_quote("TODO_VALUE")})`, typed);
}

/**
 * The first request an action caused: an XHR or fetch to the page's own origin that began within two seconds
 * after it and before the next action.
 * @param {RecordedEvent} action
 * @param {RecordedEvent | undefined} next the action after it
 * @param {{requests: readonly RecordedEvent[], origin: string}} where
 * @returns {RecordedEvent | null}
 */
function _caused(action, next, where) {
  const until = Math.min(action.t + _CAUSE_MS, next === undefined ? Infinity : next.t);
  return (
    where.requests.find(
      (request) =>
        request.t >= action.t &&
        request.t <= until &&
        ["XHR", "Fetch"].includes(String(request["type"])) &&
        _originOf(String(request["url"])) === where.origin,
    ) ?? null
  );
}

/**
 * @param {string} url
 * @returns {string} its origin, or an empty text
 */
function _originOf(url) {
  try {
    return new URL(url).origin;
  } catch {
    return "";
  }
}

/**
 * @param {string} url
 * @returns {string} its path
 */
function _pathOf(url) {
  try {
    return new URL(url).pathname;
  } catch {
    return url;
  }
}

/**
 * A draft Playwright test of the recording: its first page, then the user's actions as steps, with a wait for
 * the response each action caused and `expect` placeholders after navigations and at marks. It follows the first
 * page only. It is a draft for the project's own runner and says so.
 * @param {readonly RecordedEvent[]} events
 * @param {string} name the recording's name, which titles the test
 * @returns {string} the text of a `.spec.ts` file
 */
export function playwrightDraft(events, name) {
  const all = sortedEvents(events);
  const main = (all.find((event) => event.kind === "page") ?? all.find((event) => event.page !== undefined))?.page;
  const own = all.filter((event) => event.page === undefined || event.page === main);
  const steps = _steps(own);
  const requests = own.filter((event) => event.kind === "net");
  const left = new Set(all.flatMap((event) => (event.page === undefined || event.page === main ? [] : [event.page])));
  const body = _bodyLines(own, steps, requests);
  return [
    `// A draft Playwright test generated by \`akmon tool browser record export --test playwright\` from the recording ${_quote(name)}.`,
    "// It is a starting point for the project's own runner, not a finished test: check each locator, fill in the",
    "// values marked TODO and write the assertions the TODO lines ask for. A typed value was never recorded, and a",
    "// secret field reads its value from the environment.",
    ...(left.size > 0
      ? [`// Events of the other pages recorded (${[...left].join(", ")}) are left out: the draft follows ${main}.`]
      : []),
    "import { expect, test } from '@playwright/test';",
    "",
    `test(${_quote(name)}, async ({ page }) => {`,
    ...body.map((line) => (line === "" ? "" : `  ${line}`)),
    "});",
    "",
  ].join("\n");
}

/**
 * The statements of the test body.
 * @param {readonly RecordedEvent[]} own the followed page's events in time order
 * @param {readonly Step[]} steps
 * @param {readonly RecordedEvent[]} requests
 * @returns {string[]}
 */
function _bodyLines(own, steps, requests) {
  /** @type {string[]} */
  const lines = [];
  let origin = "";
  let waits = 0;
  let step = 0;
  const actions = steps.map((entry) => entry.event);
  for (const event of own) {
    if (event.kind === "page") {
      origin = _originOf(String(event["url"]));
      lines.push(..._gotoLines(String(event["url"])));
    } else if (event.kind === "navigation") {
      origin = _originOf(String(event["url"]));
      lines.push(
        `await expect(page).toHaveURL(new RegExp(${_quote(_escapeRegex(_pathOf(String(event["url"]))))}));`,
        "// TODO: expect(...) what the page should show after this navigation",
      );
    } else if (event.kind === "mark") {
      lines.push(
        `// MARK: ${_clip(String(event["note"] ?? ""), 200)}`,
        "// TODO: expect(...) what should hold at this moment",
      );
    } else if (steps[step]?.event === event) {
      const entry = steps[step];
      const response = _caused(event, actions[step + 1], { requests, origin });
      step += 1;
      lines.push(..._stepLines(entry, response, (waits += response === null ? 0 : 1)));
    }
  }
  return lines;
}

/**
 * @param {string} url
 * @returns {string[]}
 */
function _gotoLines(url) {
  return [
    ...(url.includes("[redacted]") ? ["// TODO: a secret in the URL was redacted at capture; supply it"] : []),
    `await page.goto(${_quote(url)});`,
  ];
}

/**
 * @param {string} text
 * @returns {string}
 */
function _escapeRegex(text) {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/**
 * The statements of one step: the action, with a wait for the response it caused set up before it.
 * @param {Step} entry
 * @param {RecordedEvent | null} response the first request the action caused
 * @param {number} number the wait's number
 * @returns {string[]}
 */
function _stepLines(entry, response, number) {
  const action = `await ${entry.action};${entry.comment ? ` // ${entry.comment}` : ""}`;
  if (response === null) {
    return [action];
  }
  const name = `response${number}`;
  return [
    `const ${name} = page.waitForResponse((response) => response.url().includes(${_quote(_pathOf(String(response["url"])))}) && response.request().method() === ${_quote(String(response["method"]))});`,
    action,
    `expect((await ${name}).status()).toBe(${Number(response["status"] ?? 200)});`,
  ];
}
