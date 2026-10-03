/**
 * `fnmatch.fnmatchcase` — the case-sensitive matcher the check runner uses to match
 * `changed` filenames against a check's `files` patterns (units/glob.toml is the spec).
 *
 * This is a port of `fnmatch.translate`, not a summary of it, because the details are what the
 * call site depends on: every character that is not `* ? [` is a literal (so `{`, `+` and a
 * space are ordinary characters — a translation that forgets them makes `a{2}` match `aa`); a
 * `[` with no closing `]` is a literal `[`; a class body has its backslashes doubled (so
 * `[\d]` means backslash-or-`d`, not a digit); `[]a]` and `[!]]` take a leading `]` as a member;
 * an empty class never matches and `[!]` matches any character; and a range written the wrong
 * way round (`[z-a]`) is dropped rather than raising, which can empty the class entirely.
 *
 * The stdlib semantics the mirror keeps: `*` crosses `/` (it is `.*`, not a path-segment
 * wildcard), matching is case-sensitive on every platform, and `*`/`?` match a leading dot
 * (fnmatch has no shell-glob "dotfiles are hidden" rule).
 *
 * Two engine gaps the port closes. Python counts *code points*, a JS regex counts UTF-16 code
 * units — compiled with the `u` flag the JS engine counts code points too, so `?` matches an
 * emoji whole instead of half of one. And the two engines disagree about which characters need
 * backslashes: Python's `re` has set-operation syntax (`&&`, `~~`, `||`) and an escaping style
 * that covers `- # $ & ~` and space, none of which the JS unicode-mode parser accepts as an
 * escape — there those characters are ordinary literals and are emitted bare.
 */

// The characters the JS engine treats as syntax outside a class (`]` among them: a closing
// bracket with no class to close is a syntax error in unicode mode). A control character is
// spelled `\uXXXX` rather than embedded raw in the pattern.
const _REGEX_METAS = new Set(["\\", "^", "$", ".", "|", "?", "*", "+", "(", ")", "[", "]", "{", "}", "/"]);

/**
 * Translate one fnmatch pattern to a JavaScript RegExp source (the stdlib `fnmatch.translate`,
 * anchored to the whole name — the JS shape of Python's `\Z`).
 * @param {string} pattern
 * @returns {string}
 */
function _translate(pattern) {
  const pieces = [];
  let i = 0;
  const n = pattern.length;
  while (i < n) {
    const c = pattern[i];
    i += 1;
    if (c === "*") {
      pieces.push(".*"); // consecutive stars need no compressing: `.*.*` reads the same
    } else if (c === "?") {
      pieces.push("."); // with `s`, the stdlib's `(?s:.)`: any character, newline included
    } else if (c === "[") {
      let j = i;
      if (j < n && pattern[j] === "!") {
        j += 1;
      }
      if (j < n && pattern[j] === "]") {
        j += 1; // a `]` first in a class is a member, not the terminator
      }
      while (j < n && pattern[j] !== "]") {
        j += 1;
      }
      if (j >= n) {
        pieces.push("\\["); // no closing bracket: a literal `[`, the scan continues after it
      } else {
        pieces.push(_translateClass(pattern.slice(i, j)));
        i = j + 1;
      }
    } else {
      pieces.push(_escapeLiteral(c));
    }
  }
  return `^(?:${pieces.join("")})$`;
}

/** One ordinary character of a pattern as a regex piece. */
function _escapeLiteral(/** @type {string} */ c) {
  const cp = /** @type {number} */ (c.codePointAt(0));
  if (cp < 0x20) {
    return `\\u${cp.toString(16).padStart(4, "0")}`;
  }
  return _REGEX_METAS.has(c) ? `\\${c}` : c;
}

/**
 * One fnmatch class body (the text between the brackets) as a regex piece: the stdlib's range
 * repair, then its three named answers — never match, any character, or a class.
 * @param {string} body
 * @returns {string}
 */
function _translateClass(body) {
  let content;
  if (!body.includes("-")) {
    content = body.replaceAll("\\", "\\\\");
  } else {
    content = _repairRanges(body);
  }
  if (content === "") {
    return "(?!)"; // empty range: never match
  }
  if (content === "!") {
    return "."; // negated empty range: match any character
  }
  if (content.startsWith("!")) {
    return `[^${_escapeClassLead(content.slice(1))}]`;
  }
  return `[${_escapeClassLead(content)}]`;
}

/**
 * Split a class body at its hyphens, escape the hyphens that are members, and drop a range
 * written the wrong way round — the stdlib's repair, which is also what turns `[z-a]` into an
 * empty class rather than an error. Chunks are rejoined with a bare `-`, so a hyphen that
 * survives between two chunks stays the range operator it was.
 * @param {string} body
 * @returns {string}
 */
function _repairRanges(body) {
  /** @type {string[]} */
  const chunks = [];
  let cut = 0;
  let from = body.startsWith("!") ? 2 : 1;
  for (;;) {
    const at = body.indexOf("-", from);
    if (at < 0) {
      break;
    }
    chunks.push(body.slice(cut, at));
    cut = at + 1;
    from = at + 3;
  }
  const tail = body.slice(cut);
  if (tail !== "") {
    chunks.push(tail);
  } else if (chunks.length > 0) {
    chunks[chunks.length - 1] += "-";
  }
  for (let k = chunks.length - 1; k > 0; k -= 1) {
    // Code points, not code units: Python indexes a str by code point and a JS string by unit,
    // so cutting a chunk that ends in an astral character would otherwise split it in half.
    const before = Array.from(chunks[k - 1]);
    const after = Array.from(chunks[k]);
    if (before.at(-1) !== undefined && after[0] !== undefined && /** @type {string} */ (before.at(-1)) > after[0]) {
      chunks[k - 1] = [...before.slice(0, -1), ...after.slice(1)].join("");
      chunks.splice(k, 1);
    }
  }
  return chunks
    .map((chunk) => chunk.replaceAll("\\", "\\\\").replaceAll("-", "\\-"))
    .join("-");
}

/**
 * Escape a class body whose first member would not read as one: `]` only starts the class if
 * escaped (Python's parser accepts a leading `]` as a member, JS's does not), while `^` and `[`
 * are the stdlib's own two escapes. A negated body arrives with its `!` already replaced.
 * @param {string} content
 * @returns {string}
 */
function _escapeClassLead(content) {
  const lead = content.charAt(0);
  return lead === "]" || lead === "^" || lead === "[" ? `\\${content}` : content;
}

/**
 * Whether `name` matches `pattern` (fnmatchcase: case-sensitive, on every platform).
 * @param {string} name
 * @param {string} pattern
 * @returns {boolean}
 */
export function fnmatchCase(name, pattern) {
  return new RegExp(_translate(pattern), "su").test(name);
}
