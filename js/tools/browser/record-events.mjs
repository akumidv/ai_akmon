/**
 * The shape of a recorded event and what is done to a value before it becomes one: the user events the
 * injected listener reports (`record-listener.mjs`) are checked and reduced here, and a recorded event's
 * text is serialized. Pure, and with no import outside Node and
 * `redact.mjs`, because the recorder's Chrome side runs in the CDP runner too (`cdp-runner.mjs`).
 *
 * Every event is one JSON object on one line: `{t, kind, page, ...}`. `t` is the time the thing began, in
 * milliseconds from the start of the recording (see `record-store.mjs` for the clock).
 */

import { namesSecret } from "./redact.mjs";

/**
 * Where a user event happened: the element, reduced to what finds it again. A field's value is never part of it.
 * @typedef {object} Descriptor
 * @property {string} tag
 * @property {string} role the explicit or implied ARIA role; empty when there is none
 * @property {string} name the accessible name, when cheap to read
 * @property {string} testid `data-testid`, `data-test` or `data-qa`
 * @property {string} id
 * @property {string} nameAttr the `name` attribute of a form control
 * @property {string} label the label text of a form control
 * @property {string} text a short text snippet (at most 60 characters); empty for a form control
 * @property {string} css a CSS path
 * @property {string} type an `input`'s type
 * @property {boolean} sensitive the field holds a secret: its text is never kept
 */

/**
 * One user action as the page reports it, checked.
 * @typedef {object} UserEvent
 * @property {"click" | "input" | "change" | "submit" | "keydown"} kind
 * @property {Descriptor} target
 * @property {number | null} [length] the length of a typed value; `null` for a sensitive field
 * @property {boolean | null} [checked] a checkbox's or radio's state after a change
 * @property {string} [key] the key of a `keydown`: Enter, Escape or Tab
 * @property {string} [method] a `submit`'s form method
 */

/** The kinds that are something the user did. */
export const ACTION_KINDS = Object.freeze(["click", "input", "change", "submit", "keydown"]);

const _USER_KINDS = new Set(ACTION_KINDS);
const _KEYS = new Set(["Enter", "Escape", "Tab"]);
/** How long each piece of a descriptor is kept, in characters: what the page reports is not trusted to be short. */
const _LIMITS = Object.freeze({
  tag: 20,
  role: 30,
  name: 80,
  testid: 80,
  id: 80,
  nameAttr: 80,
  label: 80,
  text: 60,
  css: 300,
  type: 20,
});

/**
 * @param {unknown} value
 * @param {number} limit
 * @returns {string}
 */
function _clip(value, limit) {
  const text = typeof value === "string" ? value.replace(/\s+/g, " ").trim() : "";
  return text.length > limit ? text.slice(0, limit) : text;
}

/**
 * A descriptor from what the page reported: every piece a string cut to its limit, and `sensitive` decided
 * here again, so a page that reports less than it should still gets the field kept secret.
 * @param {unknown} raw
 * @param {readonly string[]} keys the redact keys
 * @returns {Descriptor}
 */
export function descriptorOf(raw, keys) {
  const given = typeof raw === "object" && raw !== null ? /** @type {Record<string, unknown>} */ (raw) : {};
  const out = {
    tag: _clip(given["tag"], _LIMITS.tag),
    role: _clip(given["role"], _LIMITS.role),
    name: _clip(given["name"], _LIMITS.name),
    testid: _clip(given["testid"], _LIMITS.testid),
    id: _clip(given["id"], _LIMITS.id),
    nameAttr: _clip(given["nameAttr"], _LIMITS.nameAttr),
    label: _clip(given["label"], _LIMITS.label),
    text: _clip(given["text"], _LIMITS.text),
    css: _clip(given["css"], _LIMITS.css),
    type: _clip(given["type"], _LIMITS.type).toLowerCase(),
    sensitive: false,
  };
  out.sensitive =
    given["sensitive"] === true || out.type === "password" || namesSecret([out.id, out.nameAttr, out.label], keys);
  if (out.sensitive) {
    out.text = "";
  }
  return out;
}

/**
 * The payload of a binding call as an object with a known kind, or `null`.
 * @param {string} payload
 * @returns {any}
 */
function _parsed(payload) {
  try {
    const data = JSON.parse(payload);
    return typeof data === "object" && data !== null && _USER_KINDS.has(data.kind) ? data : null;
  } catch {
    return null;
  }
}

/**
 * The fields of an `input` or `change`: a length for a field that is not secret, and a toggle's state.
 * @param {any} data
 * @param {Descriptor} target
 * @returns {{length: number | null, checked: boolean | null}}
 */
function _valueFields(data, target) {
  const length = typeof data.length === "number" && Number.isFinite(data.length) ? Math.max(0, data.length) : null;
  return { length: target.sensitive ? null : length, checked: typeof data.checked === "boolean" ? data.checked : null };
}

/**
 * A user event from the payload a page reported through the binding, or `null` when it is not one. The page
 * can call the binding with anything, so nothing is taken as it comes: the kind must be known, every text is
 * cut, and a value is never carried, only the length of one that is not a secret.
 * @param {string} payload the text the listener sent
 * @param {readonly string[]} keys the redact keys
 * @returns {UserEvent | null}
 */
export function userEventOf(payload, keys) {
  const data = _parsed(payload);
  if (data === null) {
    return null;
  }
  const target = descriptorOf(data.target, keys);
  /** @type {UserEvent} */
  const event = { kind: data.kind, target };
  if (data.kind === "input" || data.kind === "change") {
    Object.assign(event, _valueFields(data, target));
  } else if (data.kind === "keydown" && _KEYS.has(data.key)) {
    event.key = data.key;
  } else if (data.kind === "keydown") {
    return null;
  } else if (data.kind === "submit") {
    event.method = _clip(data.method, 10).toLowerCase();
  }
  return event;
}

/**
 * One event as the line the file holds.
 * @param {Record<string, unknown>} event
 * @returns {string} JSON on one line, with its newline
 */
export function eventLine(event) {
  return `${JSON.stringify(event)}\n`;
}

/**
 * One event as the file holds it. `page` is the label of the page it happened on (`p1`, `p2` ...); the rest
 * depends on the kind.
 * @typedef {{t: number, kind: string, page?: string} & Record<string, any>} RecordedEvent
 */

/**
 * The events a file holds, and how many lines could not be read (the tail of a recorder killed mid-write).
 * @param {string} text
 * @returns {{events: RecordedEvent[], skipped: number}}
 */
export function readEvents(text) {
  /** @type {RecordedEvent[]} */
  const events = [];
  let skipped = 0;
  for (const line of text.split("\n")) {
    if (line.trim() === "") {
      continue;
    }
    try {
      const data = JSON.parse(line);
      if (typeof data === "object" && data !== null && typeof data.t === "number" && typeof data.kind === "string") {
        events.push(data);
      } else {
        skipped += 1;
      }
    } catch {
      skipped += 1;
    }
  }
  return { events, skipped };
}
