/**
 * POSIX shell word splitting and joining — the JavaScript answers to Python `shlex.split`
 * and `shlex.join` (units/shlex.toml is the spec). `split` feeds the recorded `[check]`
 * commands into argv; `join` renders an argv back into the command a finding displays.
 *
 * The split is a port of the stdlib state machine, not a re-implementation of its summary:
 * `read_token` walks one character at a time through the states ` ` (between words), a quote
 * character, `\` (an escape in flight) and `a` (a word under construction), and the states'
 * order is where every one of its quirks lives — a backslash escapes inside `"` but is literal
 * inside `'`, an escape swallows the character that ends a word, an empty quoted word still
 * emits a token. Branching on the quote character instead (the obvious shortcut) agrees on the
 * common inputs and disagrees on the ones the table pins.
 */

// The config `shlex.split` runs with: whitespace_split on, commenters off, no punctuation
// characters. Whitespace and the quote/escape sets are the stdlib's own.
const _WHITESPACE = " \t\r\n";
const _QUOTES = "\"'";
const _ESCAPE = "\\";
// `shlex.escapedquotes`: the quote characters inside which a backslash escapes at all — `'` is
// deliberately absent, which is why `'a\'` ends the word rather than escaping the quote.
const _ESCAPED_QUOTES = '"';

/**
 * Split a command line the way `shlex.split` does (posix mode).
 *
 * @param {string} input the command line
 * @returns {string[]} the words
 * @throws {Error} `No closing quotation` for a quote left open, `No escaped character` for a
 *   backslash with nothing after it — the two stdlib `ValueError` texts, which callers fill
 *   into a finding
 */
export function shlexSplit(input) {
  const words = [];
  let token = "";
  let state = " ";
  // The stdlib's `escapedstate`: where an in-flight escape returns to. `'a'` for an escape seen
  // between words, otherwise the quote character the escape was seen inside.
  let escapedState = " ";
  // Set once this token has been inside a quote: the stdlib emits a quoted-but-empty token
  // (`''` is one empty word) while a bare empty token is dropped.
  let quoted = false;

  // The character iterator `read_token` reads from: `undefined` is its end-of-file.
  let index = 0;
  const read = () => (index < input.length ? input[index++] : undefined);

  for (;;) {
    const next = read();
    if (state === " ") {
      if (next === undefined) {
        break; // past the end of the line
      } else if (_WHITESPACE.includes(next)) {
        if (token !== "" || quoted) {
          words.push(token);
          token = "";
          quoted = false;
        }
        continue;
      } else if (next === _ESCAPE) {
        escapedState = "a";
        state = next;
      } else if (_QUOTES.includes(next)) {
        state = next;
      } else {
        // The stdlib reaches this branch twice over for `shlex.split`: a word character starts a
        // word, and with `whitespace_split` on and no punctuation characters declared so does
        // anything else. One branch is the same machine — `|` becomes its own token only because
        // of the whitespace around it, not because it is special.
        token = next;
        state = "a";
      }
    } else if (state === "'" || state === '"') {
      quoted = true;
      if (next === undefined) {
        throw new Error("No closing quotation");
      } else if (next === state) {
        state = "a";
      } else if (next === _ESCAPE && _ESCAPED_QUOTES.includes(state)) {
        escapedState = state;
        state = next;
      } else {
        token += next;
      }
    } else if (state === _ESCAPE) {
      if (next === undefined) {
        throw new Error("No escaped character");
      }
      // Inside a quote, only the quote itself or the escape character may be escaped: a
      // backslash before anything else keeps the backslash and the character both.
      if (_QUOTES.includes(escapedState) && next !== state && next !== escapedState) {
        token += state;
      }
      token += next;
      state = escapedState;
    } else {
      // State `a`: a word under construction (state `c` needs punctuation_chars, which are off).
      if (next === undefined) {
        break;
      } else if (_WHITESPACE.includes(next)) {
        state = " ";
        if (token !== "" || quoted) {
          words.push(token);
          token = "";
          quoted = false;
        }
        continue;
      } else if (_QUOTES.includes(next)) {
        state = next;
      } else if (next === _ESCAPE) {
        escapedState = "a";
        state = next;
      } else {
        token += next;
      }
    }
  }

  // The iterator's answer after the break: a token is emitted unless the machine ended with
  // nothing in hand and no quote ever opened.
  if (token !== "" || quoted) {
    words.push(token);
  }
  return words;
}

// shlex.quote's safe set: word characters plus @%+=:,./- (ASCII only — `é` is unsafe).
const _QUOTE_RE = /[^\w@%+=:,./-]/;

/**
 * Quote one argument the way `shlex.quote` does: bare when safe, single-quoted otherwise —
 * an embedded single quote becomes `'"'"'` (close, double-quoted quote, reopen).
 * @param {string} arg
 * @returns {string}
 */
function _quote(arg) {
  if (arg !== "" && !_QUOTE_RE.test(arg)) {
    return arg;
  }
  return "'" + arg.replace(/'/g, "'\"'\"'") + "'";
}

/**
 * Join an argv into the command line `shlex.join` prints (each argument quoted when needed).
 * @param {string[]} argv
 * @returns {string}
 */
export function shlexJoin(argv) {
  return argv.map(_quote).join(" ");
}
