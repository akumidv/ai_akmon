/**
 * Redaction at capture: a secret is replaced before a header, a URL or a body leaves the code that
 * captured it, so nothing printed or written ever held it. Pure, and with no import outside Node, because
 * the code that captures runs in the CDP runner too (`cdp-runner.mjs`).
 */

/** What a redacted value is replaced by. */
export const REDACTED = "[redacted]";

/**
 * The name stems a capture always redacts, in normalized form (see `normalizedName`): a floor the project's
 * list adds to and cannot lower. A name is a secret when it contains any stem, so `accessToken`,
 * `x-goog-api-key`, `client_secret` and `newPassword` are all caught by `token`, `apikey`, `secret` and
 * `password`. A stem is never a short word that common names contain: those are `EXACT_REDACT`.
 */
export const DEFAULT_REDACT = Object.freeze([
  "password",
  "passwd",
  "pwd",
  "secret",
  "token",
  "apikey",
  "auth",
  "session",
  "cookie",
  "jwt",
  "credential",
  "privatekey",
  "otp",
  "signature",
  "csrf",
  "xsrf",
  "saml",
  "assertion",
  "accesskey",
  "subscriptionkey",
  "sessid",
  "hmac",
  "cvv",
  "mfacode",
  "verificationcode",
]);

/**
 * The names a capture redacts only when the whole normalized name is one of them: as stems they would
 * match far too much (`key` is in `monkey` and `keyboard`, `code` in `encode`, `pin` in `shipping`).
 */
export const EXACT_REDACT = Object.freeze(["sig", "code", "sid", "pin", "key", "nonce", "ticket"]);

/**
 * A name reduced to letters and digits, lower case, so `api_key`, `apiKey` and `api-key` are one.
 * @param {unknown} text
 * @returns {string}
 */
export function normalizedName(text) {
  return String(text ?? "")
    .toLowerCase()
    .replace(/[^a-z0-9]/g, "");
}

/**
 * The keys a capture redacts: the defaults, then the project's own after them, each name once (compared
 * normalized). Nothing in `extra` can remove a default.
 * @param {readonly string[]} extra the project's own keys
 * @returns {string[]}
 */
export function redactFloor(extra) {
  /** @type {string[]} */
  const keys = [];
  const seen = new Set();
  for (const key of [...DEFAULT_REDACT, ...extra]) {
    const name = normalizedName(key);
    if (name !== "" && !seen.has(name)) {
      seen.add(name);
      keys.push(key);
    }
  }
  return keys;
}

const _EXACT = new Set(EXACT_REDACT);

/**
 * The one name rule: a function telling whether a name holds a floor stem or a stem of `keys`, or is one of the
 * floor's exact names, compared
 * normalized (lower case, without `-`, `_`, `.` or any other non-alphanumeric). The floor is always part of it,
 * whatever `keys` holds, so no caller can lower it.
 * @param {readonly string[]} keys the project's keys, with or without the floor
 * @returns {(name: unknown) => boolean}
 */
function _secretMatcher(keys) {
  const stems = [...new Set([...DEFAULT_REDACT, ...keys.map(normalizedName)])].filter((stem) => stem !== "");
  return (name) => {
    const normalized = normalizedName(name);
    return normalized !== "" && (_EXACT.has(normalized) || stems.some((stem) => normalized.includes(stem)));
  };
}

/**
 * Whether any of the texts is a secret's name (a field called `csrf_token` holds `token`).
 * @param {readonly unknown[]} texts
 * @param {readonly string[]} keys
 * @returns {boolean}
 */
export function namesSecret(texts, keys) {
  const matches = _secretMatcher(keys);
  return texts.some((text) => matches(text));
}

/**
 * The headers with every secret value replaced: a header whose name is a secret's name.
 * @param {Record<string, string> | undefined} headers
 * @param {readonly string[]} [keys] the project's keys, added to the floor
 * @returns {Record<string, string>}
 */
export function redactHeaders(headers, keys = []) {
  const matches = _secretMatcher(keys);
  /** @type {Record<string, string>} */
  const out = {};
  for (const [name, value] of Object.entries(headers ?? {})) {
    out[name] = matches(name) ? REDACTED : value;
  }
  return out;
}

/**
 * A JSON value with every property whose name is a secret's name replaced, at any depth, in objects and arrays alike.
 * @param {unknown} value
 * @param {readonly string[]} keys
 * @returns {unknown}
 */
export function redactJson(value, keys) {
  return _redactJson(value, _secretMatcher(keys));
}

/**
 * @param {unknown} value
 * @param {(name: unknown) => boolean} matches
 * @returns {unknown}
 */
function _redactJson(value, matches) {
  if (Array.isArray(value)) {
    return value.map((item) => _redactJson(item, matches));
  }
  if (typeof value === "object" && value !== null) {
    /** @type {Record<string, unknown>} */
    const out = {};
    for (const [key, item] of Object.entries(value)) {
      out[key] = matches(key) ? REDACTED : _redactJson(item, matches);
    }
    return out;
  }
  return value;
}

/** How many times a value may be decoded and searched again (a URL inside a URL inside a URL). */
const _MAX_DEPTH = 3;
/** A decoded value that is a URL, or holds a query or fragment: it is redacted as one. */
const _URL_LIKE = /^[a-z][a-z0-9+.-]*:\/\/|[?#]/i;
/** A collapsed `data:` URL, as `_dataLabel` writes it: collapsing again changes nothing. */
const _COLLAPSED_PAYLOAD = /^…\[\d+ bytes\]$/;

/**
 * `value` percent-decoded once; a value that is not valid UTF-8 percent-encoding has its ASCII escapes decoded, so
 * a secret in it is still found.
 * @param {string} value
 * @returns {string}
 */
function _decoded(value) {
  try {
    return decodeURIComponent(value);
  } catch {
    return value.replace(/%([0-7][0-9a-f])/gi, (_whole, hex) => String.fromCharCode(Number.parseInt(hex, 16)));
  }
}

/**
 * Text percent-encoded again, with the `[redacted]` marker left readable.
 * @param {string} text
 * @returns {string}
 */
function _reencoded(text) {
  return encodeURIComponent(text).replaceAll("%5Bredacted%5D", REDACTED);
}

/**
 * The label a `data:` URL is shown as: it is content, not an address, so its payload is never kept.
 * @param {string} mime
 * @param {string} payload
 * @returns {string}
 */
function _dataLabel(mime, payload) {
  return `data:${mime.trim()},…[${Buffer.byteLength(payload, "utf8")} bytes]`;
}

/**
 * The URL's collapsed label when it is a `data:` URL, else null.
 * @param {string} url
 * @returns {string | null}
 */
function _collapsedDataUrl(url) {
  const found = /^\s*data:([^,;]*)[^,]*,?([\s\S]*)$/i.exec(url);
  if (found === null) {
    return null;
  }
  return _COLLAPSED_PAYLOAD.test(found[2]) ? `data:${found[1].trim()},${found[2]}` : _dataLabel(found[1], found[2]);
}

/**
 * A value that may hold a secret one or more percent-decodings down: a nested URL (`redirect_uri`, `returnTo`,
 * `next`) or query, in any encoding depth. The decoded form is redacted and, when anything changed, encoded back.
 * @param {string} value
 * @param {(name: unknown) => boolean} matches
 * @param {number} depth how many levels down the value already is
 * @returns {string}
 */
function _redactNested(value, matches, depth) {
  if (depth >= _MAX_DEPTH) {
    return _scrub(value, matches);
  }
  const decoded = _decoded(value);
  const encoded = decoded !== value;
  let inner;
  if (_URL_LIKE.test(decoded)) {
    inner = _redactUrl(decoded, matches, depth + 1);
  } else if (decoded.includes("=")) {
    inner = _redactQuery(decoded, matches, depth + 1);
  } else if (encoded) {
    inner = _redactNested(decoded, matches, depth + 1);
  } else {
    return value;
  }
  if (!encoded) {
    return inner;
  }
  inner = _scrub(inner, matches);
  return inner === decoded ? value : _reencoded(inner);
}

/**
 * Query-string text (`a=1&token=x`), a fragment or a form body with the values of the secret parameters replaced,
 * and every other value searched for a nested, encoded URL or query.
 * @param {string} query
 * @param {(name: unknown) => boolean} matches
 * @param {number} depth
 * @returns {string}
 */
function _redactQuery(query, matches, depth) {
  return query
    .split("&")
    .map((pair) => {
      const at = pair.indexOf("=");
      if (at < 0) {
        return _redactNested(pair, matches, depth);
      }
      let name = pair.slice(0, at);
      try {
        name = decodeURIComponent(name.replace(/\+/g, " "));
      } catch {
        // A name that does not decode is compared as written.
      }
      const head = pair.slice(0, at + 1);
      return matches(name) ? `${head}${REDACTED}` : `${head}${_redactNested(pair.slice(at + 1), matches, depth)}`;
    })
    .join("&");
}

/** `scheme://userinfo@` or the protocol-relative `//userinfo@`: the userinfo of a URL, up to the first `/`, `?` or `#`. */
const _USERINFO = /^((?:[a-z][a-z0-9+.-]*:)?\/\/)[^/?#]*@/i;
/** A path parameter, `;name=value`, such as `;jsessionid=...`. */
const _PATH_PARAMETER = /;([^=;/?#]+)=([^;/?#]*)/g;

/**
 * A URL with its userinfo (`user:password@`) replaced and the values of its secret path (`;jsessionid=`),
 * query and fragment parameters replaced, at any depth of nesting and percent-encoding. A `data:` URL is content,
 * not an address, and is shown as `data:<mime>,…[<n> bytes]`; a `blob:` URL is redacted by the URL it holds.
 * @param {string} url
 * @param {readonly string[]} keys
 * @returns {string}
 */
export function redactUrl(url, keys) {
  return _redactUrl(url, _secretMatcher(keys), 0);
}

/**
 * @param {string} url
 * @param {(name: unknown) => boolean} matches
 * @param {number} depth
 * @returns {string}
 */
function _redactUrl(url, matches, depth) {
  const data = _collapsedDataUrl(url);
  if (data !== null) {
    return data;
  }
  if (/^blob:/i.test(url)) {
    return `${url.slice(0, 5)}${_redactUrl(url.slice(5), matches, depth)}`;
  }
  const hash = url.indexOf("#");
  const fragment = hash < 0 ? "" : `#${_redactQuery(url.slice(hash + 1), matches, depth)}`;
  const rest = hash < 0 ? url : url.slice(0, hash);
  const start = rest.indexOf("?");
  const base = (start < 0 ? rest : rest.slice(0, start))
    .replace(_USERINFO, `$1${REDACTED}@`)
    .replace(_PATH_PARAMETER, (whole, name) => (matches(name) ? `;${name}=${REDACTED}` : whole));
  const query = start < 0 ? "" : `?${_redactQuery(rest.slice(start + 1), matches, depth)}`;
  return `${base}${query}${fragment}`;
}

/**
 * A key not preceded by a percent-escape's hex digits (`%26code`, `%2526code`: the key is `code`), then the key,
 * then a separator that may itself be percent-encoded, once or twice: `key=value`, `"key": "value"`,
 * `'key' => 'value'`, `key%3Dvalue`, `"key"%3A"value"`.
 */
const _PAIR_KEY =
  /(\\?["']?)(?<!%(?:25)*[0-9a-f]?)([\w.-]+)((?:\\?["']?|%(?:25)*2[27])\s*(?:=>|[:=]|%(?:25)*3[ad])(?:\s|%(?:25)*20)*)/gi;
/** The values a pair may have, plain: a quoted string (also one inside a string, with its quotes escaped). */
const _PLAIN_QUOTED = String.raw`\\"(?:(?!\\").)*\\"|\\'(?:(?!\\').)*\\'|"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'`;
/** What ends an unquoted value written with percent-encoding: an encoded space, quote, `&`, `,`, `;`, `]` or `}`. */
const _ENCODED_END = String.raw`%(?:25)*(?:20|22|26|27|2C|3B|5D|7D)`;
/** A quoted string whose quotes are percent-encoded, once or twice. */
const _ENCODED_QUOTED = String.raw`%(?:25)*22(?:(?!%(?:25)*22).)*%(?:25)*22|%(?:25)*27(?:(?!%(?:25)*27).)*%(?:25)*27`;
/**
 * The value that follows: an optional `Bearer`/`Basic` word, then a quoted string or a bare run, which may hold
 * an earlier `[redacted]`.
 */
const _PAIR_VALUE = new RegExp(
  String.raw`((?:Bearer|Basic)\s+)?(\[redacted\]|${_PLAIN_QUOTED}|(?:\[redacted\]|[^\s"',&;}\]])+)`,
  "y",
);
/** The value after a percent-encoded separator: as `_PAIR_VALUE`, and ending at an encoded `&`, quote or space too. */
const _PAIR_VALUE_ENCODED = new RegExp(
  String.raw`((?:Bearer|Basic)\s+)?(\[redacted\]|${_ENCODED_QUOTED}|${_PLAIN_QUOTED}|(?:\[redacted\]|(?!${_ENCODED_END})[^\s"',&;}\]])+)`,
  "iy",
);
/** An `Authorization` or `Proxy-Authorization` header, whatever its scheme: the whole value, to the end of its line. */
const _AUTHORIZATION = /\b((?:proxy-)?authorization["']?\s*[:=]\s*)(?:"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'|[^\r\n]+)/gi;
/** A `Cookie` or `Set-Cookie` header: its value, to the end of its line. */
const _COOKIE = /\b((?:set-)?cookie["']?\s*[:=]\s*)([^\r\n]+)/gi;
/** A `data:` URL in free text, to the next space or quote: its MIME type, then the rest. */
const _DATA_IN_TEXT = /\bdata:(?=[;,]|[\w.+-]+\/[\w.+-]+)([\w.+-]+\/[\w.+-]+)?([^\s'"]*)/gi;

/**
 * How many times `char` occurs in `text`.
 * @param {string} text
 * @param {string} char
 * @returns {number}
 */
function _occurrences(text, char) {
  return text.split(char).length - 1;
}

/**
 * The text of a `data:` URL found in free text, with the `)` that closes a parenthesis opened before it split off:
 * balanced against the URL's own parentheses, or, when the URL directly follows a `(`, its last `)` even when its
 * own parentheses do not balance.
 * @param {string} found
 * @param {boolean} afterOpening whether the URL directly follows a `(`
 * @returns {{body: string, closing: string}}
 */
function _withoutClosing(found, afterOpening) {
  let body = found;
  let closing = "";
  while (body.endsWith(")") && _occurrences(body, ")") > _occurrences(body, "(")) {
    body = body.slice(0, -1);
    closing += ")";
  }
  if (closing === "" && afterOpening && body.endsWith(")")) {
    return { body: body.slice(0, -1), closing: ")" };
  }
  return { body, closing };
}

/**
 * Every `data:` URL in free text collapsed (`_dataLabel`); a `)` that closes a parenthesis opened before the URL
 * stays outside it.
 * @param {string} text
 * @returns {string}
 */
function _withoutDataPayloads(text) {
  return text.replace(_DATA_IN_TEXT, (whole, mime, rest, offset, string) => {
    if (/^,…\[\d+$/.test(rest) && string.startsWith(" bytes]", offset + whole.length)) {
      return whole;
    }
    const { body, closing } = _withoutClosing(whole, string[offset - 1] === "(");
    const afterMime = body.slice(5 + (mime ?? "").length);
    const comma = afterMime.indexOf(",");
    return `${_dataLabel(mime ?? "", comma < 0 ? "" : afterMime.slice(comma + 1))}${closing}`;
  });
}

/**
 * Free text (a console line, an exception, a mark's note) with the value of every `key=value`,
 * `"key": "value"` or `'key' => 'value'` pair whose key is a secret's name replaced — a separator or a quote
 * percent-encoded once or twice (`token%3Dx`, `"token"%3A"x"`) is read too — the whole value of every
 * `Authorization` header (whatever its scheme), every pair of a `Cookie` header, every `Bearer`/`Basic`
 * credential, the userinfo of every URL, and the payload of every `data:` URL. It cannot find a secret that
 * carries no name, which is why a body is only kept when it is textual and one that is not JSON or a form is
 * scrubbed with this.
 * @param {string} text
 * @param {readonly string[]} keys
 * @returns {string}
 */
export function scrubbedText(text, keys) {
  return _scrub(text, _secretMatcher(keys));
}

/**
 * The value that starts at `at`, read by the pattern the separator calls for (a percent-encoded one ends a bare
 * value at an encoded `&`, quote or space too), or null when there is none.
 * @param {string} text
 * @param {number} at
 * @param {string} separator
 * @param {{plain: RegExp, encoded: RegExp}} patterns
 * @returns {RegExpExecArray | null}
 */
function _valueAt(text, at, separator, patterns) {
  const pattern = separator.includes("%") ? patterns.encoded : patterns.plain;
  pattern.lastIndex = at;
  return pattern.exec(text);
}

/**
 * @param {string} text
 * @param {(name: unknown) => boolean} matches
 * @returns {string}
 */
function _scrub(text, matches) {
  const prepared = _withoutDataPayloads(text)
    .replace(_AUTHORIZATION, `$1${REDACTED}`)
    .replace(_COOKIE, (_whole, head, value) => `${head}${value.replace(/=([^;"'\r\n]*)/g, `=${REDACTED}`)}`)
    .replace(/\b(Bearer|Basic)\s+[A-Za-z0-9._~+/=-]+/gi, `$1 ${REDACTED}`)
    .replace(/\b([a-z][a-z0-9+.-]*:\/\/)[^\s/?#@]+@/gi, `$1${REDACTED}@`);
  const keyPattern = new RegExp(_PAIR_KEY);
  const valuePatterns = { plain: new RegExp(_PAIR_VALUE), encoded: new RegExp(_PAIR_VALUE_ENCODED) };
  let out = "";
  let position = 0;
  for (let found = keyPattern.exec(prepared); found !== null; found = keyPattern.exec(prepared)) {
    const valueAt = found.index + found[0].length;
    const value = matches(found[2]) ? _valueAt(prepared, valueAt, found[3], valuePatterns) : null;
    if (value === null) {
      continue;
    }
    out += `${prepared.slice(position, valueAt)}${value[1] ?? ""}${REDACTED}`;
    position = valueAt + value[0].length;
    keyPattern.lastIndex = position;
  }
  return out + prepared.slice(position);
}

/**
 * Whether a MIME type is a text or JSON one, the only bodies a capture reads.
 * @param {string} mime
 * @returns {boolean}
 */
export function textualMime(mime) {
  const type = mime.split(";")[0].trim().toLowerCase();
  return (
    type.startsWith("text/") ||
    type.endsWith("+json") ||
    type.endsWith("+xml") ||
    ["application/json", "application/javascript", "application/xml", "application/x-www-form-urlencoded"].includes(
      type,
    )
  );
}

/**
 * The text of a response body, redacted and cut to `maxBytes`, or a note saying why it is not shown.
 * A JSON body is parsed in full and written again, so the cut never leaves half a secret; one that does
 * not parse is withheld, because it could not be redacted. A form is redacted by its parameters; any other
 * text is only scrubbed (`scrubbedText`), the best a body that carries no names allows, and cut after.
 * @param {string} text
 * @param {string} mime
 * @param {{keys: readonly string[], maxBytes: number}} how
 * @returns {{text: string, truncated: boolean, note: string | null}}
 */
export function redactBody(text, mime, how) {
  const type = mime.split(";")[0].trim().toLowerCase();
  /** @type {string} */
  let shown;
  if (type === "application/json" || type.endsWith("+json")) {
    try {
      shown = JSON.stringify(redactJson(JSON.parse(text), how.keys));
    } catch {
      return { text: "", truncated: false, note: "JSON that did not parse, withheld because it could not be redacted" };
    }
  } else if (type === "application/x-www-form-urlencoded") {
    shown = _redactQuery(text, _secretMatcher(how.keys), 0);
  } else {
    shown = scrubbedText(text, how.keys);
  }
  const bytes = Buffer.from(shown, "utf8");
  if (bytes.length <= how.maxBytes) {
    return { text: shown, truncated: false, note: null };
  }
  return { text: bytes.subarray(0, how.maxBytes).toString("utf8"), truncated: true, note: null };
}
