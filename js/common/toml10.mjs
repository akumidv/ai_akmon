/**
 * The TOML 1.0.0 fence in front of the vendored smol-toml: what `tomllib` (the Python floor,
 * TOML 1.0.0) refuses and smol-toml 1.9.0 (a TOML 1.1.0 parser with no 1.0.0 mode) accepts.
 * `record.mjs` asks it before `parse`, so a record that is not TOML to the Python twin is not
 * TOML here either (ADR-0020/D10, C115): the lenient reader then
 * takes its line parser and the strict one raises, as `common/record.py` does on a
 * `TOMLDecodeError`.
 *
 * Refused, all measured against `tomllib` on 3.11: a leading byte-order mark; the `\x` and `\e`
 * escapes of a basic string; a line break at an inline table's own level (inside a value array
 * or string of that table it stays legal); a trailing comma before an inline table's `}`; a time
 * without seconds; a calendar date that does not exist; a clock or offset field out of range.
 * `meta/conformance/tomltest/decoder.mjs` runs this same fence for the toml-test pin (C117), so
 * the suite measures the fence akmon reads with. Strings and comments are skipped so their
 * contents never trip a check. Stdlib only, no imports.
 */

/** @typedef {{at: number, reason: string}} Refusal an offset into the text and why */
/** @typedef {{text: string, at: number, open: string[]}} Scan */

/** Days per month, January to December (February of a non-leap year). */
const _MONTH_DAYS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
/** A date-shaped value start: four digits, dash, two, dash, two. */
const _DATE_START = /^\d{4}-\d{2}-\d{2}/;
/** A date, an optional `[Tt]` time (seconds and fraction optional in the match) and offset. */
const _DATE_TOKEN = /^\d{4}-\d{2}-\d{2}(?:[Tt]\d{2}:\d{2}(?::\d{2})?(?:\.\d+)?(?:[Zz]|[+-]\d{2}:\d{2})?)?/;
/** A local time, seconds and fraction optional in the match. */
const _TIME_TOKEN = /^\d{2}:\d{2}(?::\d{2})?(?:\.\d+)?/;
/** The date token with its fields captured. */
const _DATE_FIELDS =
  /^(\d{4})-(\d{2})-(\d{2})(?:[Tt](\d{2}):(\d{2})(?::(\d{2}))?(?:\.\d+)?(?:[Zz]|[+-](\d{2}):(\d{2}))?)?$/;
/** A character a bare key may hold: a digit after one is inside a name or a number, not a date. */
const _BARE_KEY_CHAR = /^[A-Za-z0-9_-]$/;
/** The time token with its fields captured. */
const _TIME_FIELDS = /^(\d{2}):(\d{2})(?::(\d{2}))?(?:\.\d+)?$/;

/**
 * Where `text` stops being TOML 1.0.0 although smol-toml would parse it, or `null` when it does
 * not. `null` is no promise the text parses — the parser still decides everything else.
 * @param {string} text the decoded document, BOM kept
 * @returns {{line: number, column: number, reason: string} | null}
 */
export function toml10Refusal(text) {
  const refusal =
    text.charCodeAt(0) === 0xfeff ? { at: 0, reason: "leading UTF-8 BOM (TOML is BOM-free UTF-8)" } : _scan(text);
  if (refusal === null) {
    return null;
  }
  const before = text.slice(0, refusal.at);
  const lineStart = Math.max(before.lastIndexOf("\n"), before.lastIndexOf("\r")) + 1;
  return {
    line: before.split(/\r\n|\r|\n/).length,
    column: refusal.at - lineStart + 1,
    reason: refusal.reason,
  };
}

/**
 * The first 1.1.0-only construct of the whole text, or `null`.
 * @param {string} text
 * @returns {Refusal | null}
 */
function _scan(text) {
  /** @type {Scan} */
  const scan = { text, at: 0, open: [] };
  while (scan.at < text.length) {
    const refusal = _step(scan);
    if (refusal !== null) {
      return refusal;
    }
  }
  return null;
}

/**
 * Consume one token at `scan.at`, answering a refusal when it is one.
 * @param {Scan} scan
 * @returns {Refusal | null}
 */
function _step(scan) {
  const char = scan.text.charAt(scan.at);
  const handler = _HANDLERS.get(char);
  if (handler !== undefined) {
    return handler(scan, char);
  }
  if (char >= "0" && char <= "9" && !_BARE_KEY_CHAR.test(scan.text.charAt(scan.at - 1))) {
    return _dateOrTime(scan);
  }
  scan.at += 1;
  return null;
}

/** Whether `char` breaks a line. */
function _isBreak(/** @type {string} */ char) {
  return char === "\n" || char === "\r";
}

/**
 * Skip a comment to the line break, not past it: the break still has to clear the inline-table
 * check.
 * @param {Scan} scan
 * @returns {null}
 */
function _comment(scan) {
  while (scan.at < scan.text.length && !_isBreak(scan.text.charAt(scan.at))) {
    scan.at += 1;
  }
  return null;
}

/**
 * Open an inline table or an array (a table header's brackets count as one, harmlessly).
 * @param {Scan} scan
 * @param {string} char
 * @returns {null}
 */
function _open(scan, char) {
  scan.open.push(char);
  scan.at += 1;
  return null;
}

/**
 * Close the innermost container, refusing a trailing comma before an inline table's `}`.
 * @param {Scan} scan
 * @param {string} char
 * @returns {Refusal | null}
 */
function _close(scan, char) {
  const comma = char === "}" ? _trailingComma(scan) : null;
  scan.open.pop();
  scan.at += 1;
  return comma;
}

/**
 * Refuse a line break at an inline table's own level; inside a value array it is 1.0.0.
 * @param {Scan} scan
 * @returns {Refusal | null}
 */
function _break(scan) {
  if (scan.open.at(-1) === "{") {
    return { at: scan.at, reason: "line break inside an inline table (TOML 1.0.0 permits none outside a value)" };
  }
  scan.at += 1;
  return null;
}

/**
 * Skip one string, refusing a 1.1.0 escape in a basic one. A closing delimiter may be followed by
 * up to two more quotes, which belong to the string's content (TOML 1.0.0 §String).
 * @param {Scan} scan
 * @param {string} quote
 * @returns {Refusal | null}
 */
function _string(scan, quote) {
  const multi = scan.text.startsWith(quote.repeat(3), scan.at);
  const close = multi ? quote.repeat(3) : quote;
  scan.at += close.length;
  while (scan.at < scan.text.length && !scan.text.startsWith(close, scan.at)) {
    const refusal = quote === '"' ? _escape(scan) : null;
    if (refusal !== null) {
      return refusal;
    }
    scan.at += 1;
  }
  scan.at += close.length;
  for (let extra = 0; multi && extra < 2 && scan.text.charAt(scan.at) === quote; extra += 1) {
    scan.at += 1;
  }
  return null;
}

/**
 * At a backslash in a basic string: refuse `\x` and `\e`, else step over the escape's backslash
 * so the character it escapes (a quote, another backslash) is never read as syntax.
 * @param {Scan} scan
 * @returns {Refusal | null}
 */
function _escape(scan) {
  if (scan.text.charAt(scan.at) !== "\\") {
    return null;
  }
  const escape = scan.text.charAt(scan.at + 1);
  if (escape === "x" || escape === "e") {
    return { at: scan.at, reason: `the \\${escape} escape is a TOML 1.1.0 feature` };
  }
  scan.at += 1;
  return null;
}

/** @type {Map<string, (scan: Scan, char: string) => Refusal | null>} */
const _HANDLERS = new Map([
  ["#", _comment],
  ['"', _string],
  ["'", _string],
  ["{", _open],
  ["[", _open],
  ["}", _close],
  ["]", _close],
  ["\n", _break],
  ["\r", _break],
]);

/**
 * A comma right before an inline table's `}` (blanks between), or `null`.
 * @param {Scan} scan
 * @returns {Refusal | null}
 */
function _trailingComma(scan) {
  const back = _skipBlanks(scan.text, scan.at - 1, -1);
  return scan.text.charAt(back) === ","
    ? { at: back, reason: "trailing comma in an inline table (TOML 1.0.0 permits none)" }
    : null;
}

/**
 * Validate the date or time token starting at a digit, or step over the digit.
 * @param {Scan} scan
 * @returns {Refusal | null}
 */
function _dateOrTime(scan) {
  const rest = scan.text.slice(scan.at);
  const token = (_DATE_START.test(rest) ? _DATE_TOKEN : _TIME_TOKEN).exec(rest)?.[0] ?? null;
  if (token === null) {
    scan.at += 1;
    return null;
  }
  const at = scan.at;
  scan.at += token.length;
  const reason = _isBareKey(scan.text, at, scan.at) ? null : _dateOrTimeReason(token);
  return reason === null ? null : { at, reason };
}

/**
 * Whether the token sits where a bare key does — before `=`, after a dotted key's `.` or a table
 * header's `[` — so it is a name, not a value. An array's `[` opens values.
 * @param {string} text
 * @param {number} start
 * @param {number} end
 * @returns {boolean}
 */
function _isBareKey(text, start, end) {
  const next = _skipBlanks(text, end, 1);
  const previous = _skipBlanks(text, start - 1, -1);
  if (text.charAt(next) === "=" || text.charAt(previous) === ".") {
    return true;
  }
  if (text.charAt(previous) !== "[") {
    return false;
  }
  const before = _skipBlanks(text, text.charAt(previous - 1) === "[" ? previous - 2 : previous - 1, -1);
  return before < 0 || _isBreak(text.charAt(before));
}

/**
 * The first offset from `at`, walking by `step`, that is not a space or a tab.
 * @param {string} text
 * @param {number} at
 * @param {number} step
 * @returns {number}
 */
function _skipBlanks(text, at, step) {
  let index = at;
  while (text.charAt(index) === " " || text.charAt(index) === "\t") {
    index += step;
  }
  return index;
}

/**
 * Why a date or time token is not TOML 1.0.0, or `null`.
 * @param {string} token
 * @returns {string | null}
 */
function _dateOrTimeReason(token) {
  if (!_DATE_START.test(token)) {
    const [, hours, minutes, seconds] = _TIME_FIELDS.exec(token) ?? [];
    return seconds === undefined
      ? `no seconds in time "${token}" (TOML 1.0.0 requires them)`
      : _clock(hours, minutes, seconds);
  }
  const [, year, month, day, hours, minutes, seconds, offsetHours, offsetMinutes] = _DATE_FIELDS.exec(token) ?? [];
  const date = _calendar(Number(year), Number(month), Number(day));
  if (date !== null || hours === undefined) {
    return date;
  }
  if (seconds === undefined) {
    return `no seconds in the time of "${token}" (TOML 1.0.0 requires them)`;
  }
  return (
    _clock(hours, minutes, seconds) ?? (offsetHours === undefined ? null : _clock(offsetHours, offsetMinutes, "00"))
  );
}

/**
 * Why a calendar date does not exist, or `null`.
 * @param {number} year
 * @param {number} month
 * @param {number} day
 * @returns {string | null}
 */
function _calendar(year, month, day) {
  if (month < 1 || month > 12) {
    return `month ${month} out of range`;
  }
  const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
  const last = month === 2 && leap ? 29 : _MONTH_DAYS[month - 1];
  return day < 1 || day > last ? `day ${day} does not exist in month ${month} of ${year}` : null;
}

/**
 * Why a clock is out of range (hours 00–23, minutes and seconds 00–59), or `null`.
 * @param {string} hours
 * @param {string} minutes
 * @param {string} seconds
 * @returns {string | null}
 */
function _clock(hours, minutes, seconds) {
  return Number(hours) > 23 || Number(minutes) > 59 || Number(seconds) > 59
    ? `clock ${hours}:${minutes}:${seconds} out of range (TOML 1.0.0: hours 00–23, minutes and seconds 00–59)`
    : null;
}
