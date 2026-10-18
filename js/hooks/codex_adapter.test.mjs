/**
 * node:test for `js/hooks/codex_adapter.mjs` and `js/hooks/codex-hook.mjs` — the named pins of the
 * twin: the patch patterns on the inputs where Python's `re` and JavaScript's differ (CRLF,
 * U+2028, the Unicode spaces `re.ASCII` takes out), the Python value semantics of a payload, the
 * stdin reader, `json.loads`'s extra grammar, and the argv contract. The expected values were checked
 * against `hooks/codex_adapter.py` / `hooks/codex-hook.py` by differential runs, not derived.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import { posix } from "node:path";
import { fileURLToPath } from "node:url";

import { JSONDecodeError, jsonLoads } from "../common/pyjson.mjs";
import {
  command,
  cwd,
  filePaths,
  isApplyPatchCommand,
  normalizeTool,
  payloadShape,
  sessionId,
  toolKind,
  toolName,
  toolUseId,
  unmeasuredPathSource,
  writeStderr,
} from "./codex_adapter.mjs";
import { lazyHookData } from "./hook_data.mjs";

const data = lazyHookData();
const ADAPTER = new URL("./codex_adapter.mjs", import.meta.url).href;
const HOOK = fileURLToPath(new URL("./codex-hook.mjs", import.meta.url));

const PATCH = "*** Begin Patch\n*** Add File: x.py\n+1\n*** End Patch\n";

/** `<invocation> <delimiter>\n<body>EOF\n` — a shell call that carries a patch inline. */
function heredoc(/** @type {string} */ invocation, body = PATCH, delimiter = "<<'EOF'") {
  return `${invocation} ${delimiter}\n${body}EOF\n`;
}

/** Run `body` with a fresh directory, removed after. */
function withDir(/** @type {(dir: string) => void} */ body) {
  const dir = fs.mkdtempSync(posix.join(os.tmpdir(), "akmon-codex-adapter-test-"));
  try {
    body(dir);
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
}

/**
 * Run a module-level snippet in a fresh node (so stdin, stdout and stderr are the real ones).
 * @param {string} body statements; `adapter` is the imported module
 * @param {Buffer | string} [input]
 */
function runSnippet(body, input = "") {
  const source = `import * as adapter from ${JSON.stringify(ADAPTER)};\n${body}`;
  return spawnSync(process.execPath, ["--input-type=module", "-e", source], { input });
}

// --------------------------------------------------------------------------------------
// The apply_patch recognition rule
// --------------------------------------------------------------------------------------

test("a command-position apply_patch with a complete inline envelope is a patch", () => {
  for (const [label, text] of [
    ["canonical", heredoc("apply_patch")],
    ["unquoted delimiter", heredoc("apply_patch", PATCH, "<<EOF")],
    ["dash and double quotes", heredoc("apply_patch", PATCH, '<<-"EOF"')],
    ["after cd &&", heredoc("cd sub && apply_patch")],
    ["after ;", heredoc("echo hi; apply_patch")],
    ["after |", heredoc("true | apply_patch")],
    ["subshell", heredoc("(apply_patch")],
    ["group", heredoc("{ apply_patch")],
    ["command substitution", heredoc("$(apply_patch")],
    ["sh -c wrapper", heredoc("sh -c 'apply_patch")],
    ["bash -lc wrapper", heredoc('bash -lc "apply_patch')],
    ["command prefix", heredoc("command apply_patch")],
    ["path prefix", heredoc("/usr/local/bin/apply_patch")],
    ["an escaped quote outside quotes", heredoc("echo \\'; apply_patch")],
    ["a backslash that does not escape inside single quotes", heredoc("echo '\\'; apply_patch")],
    ["CRLF line endings", heredoc("apply_patch").replaceAll("\n", "\r\n")],
    ["a vertical tab after Begin Patch", "apply_patch <<'EOF'\n*** Begin Patch\x0b\n*** Add File: x\n*** End Patch\n"],
  ]) {
    assert.equal(isApplyPatchCommand(text), true, label);
  }
});

test("printed, quoted, truncated or malformed patch text stays shell", () => {
  for (const [label, text] of [
    ["second line", `echo hi\n${heredoc("apply_patch")}`],
    ["inside quotes", heredoc("echo 'apply_patch")],
    ["backslash escapes the quote inside double quotes", heredoc('echo "\\"; apply_patch')],
    ["name suffix", heredoc("apply_patchx")],
    ["name prefix", heredoc("xapply_patch")],
    ["no End Patch", "apply_patch <<'EOF'\n*** Begin Patch\n*** Add File: x.py\n"],
    ["no path line", "apply_patch <<'EOF'\n*** Begin Patch\n*** End Patch\nEOF\n"],
    [
      "envelope not directly after the heredoc",
      "apply_patch <<'EOF'\nhello\n*** Begin Patch\n*** Add File: x\n*** End Patch\n",
    ],
    ["mismatched delimiter quotes", `apply_patch <<'EOF"\n${PATCH}`],
    ["U+2028 for line ends", heredoc("apply_patch").replaceAll("\n", "\u2028")],
    ["no-break space before the heredoc", `apply_patch\u00a0<<'EOF'\n${PATCH}`],
  ]) {
    assert.equal(isApplyPatchCommand(text), false, label);
  }
});

test("the patterns are ASCII: a Unicode space is not a space (re.ASCII, Python changed with this twin)", () => {
  // Each of these read True before `hooks/codex_adapter.py` became `re.ASCII` (Python's Unicode `\s`
  // took U+001C, U+0085, U+00A0 and U+2028 for white space); the JavaScript twin could never agree.
  for (const [label, text] of [
    ["no-break space before the name", heredoc("\u00a0apply_patch")],
    ["U+001C before the name", `x;\x1capply_patch <<'EOF'\n${PATCH}`],
    ["U+001C after Begin Patch", "apply_patch <<'EOF'\n*** Begin Patch\x1c\n*** Add File: x\n*** End Patch\n"],
    ["U+2028 after Begin Patch", "apply_patch <<'EOF'\n*** Begin Patch\u2028\n*** Add File: x\n*** End Patch\n"],
    ["U+0085 after End Patch", "apply_patch <<'EOF'\n*** Begin Patch\n*** Add File: x\n*** End Patch\x85\n"],
    ["U+00A0 after End Patch", "apply_patch <<'EOF'\n*** Begin Patch\n*** Add File: x\n*** End Patch\u00a0\n"],
  ]) {
    assert.equal(isApplyPatchCommand(text), false, label);
  }
});

// --------------------------------------------------------------------------------------
// Tool names and the payload readers
// --------------------------------------------------------------------------------------

test("a Codex tool name maps to the neutral kind; an unknown one passes through", () => {
  assert.equal(normalizeTool(data, "apply_patch"), "edit");
  assert.equal(normalizeTool(data, "Bash"), "shell");
  assert.equal(normalizeTool(data, "Edit"), "Edit");
  assert.equal(normalizeTool(data, ""), "");
});

test("the call acts as what its payload does, not what route it took", () => {
  assert.equal(toolKind(data, {}), "edit"); // no name: apply_patch
  assert.equal(toolKind(data, { tool_name: "Bash", tool_input: { command: "make" } }), "shell");
  assert.equal(toolKind(data, { tool_name: "Bash", tool_input: { command: heredoc("apply_patch") } }), "edit");
  assert.equal(toolKind(data, { tool_name: "Bash", command: heredoc("apply_patch") }), "edit");
  assert.equal(toolKind(data, { tool_name: "Read" }), "Read");
});

test("tool_name tries every spelling in priority order and reads a nested name", () => {
  assert.equal(toolName(data, { tool_name: "a", toolName: "b" }), "a");
  assert.equal(toolName(data, { toolName: "b", tool: "c" }), "b");
  assert.equal(toolName(data, { tool: "c" }), "c");
  assert.equal(toolName(data, { name: "d" }), "d");
  assert.equal(toolName(data, { tool_name: { name: "n" } }), "n");
  // a value that is neither a string nor a dict with a string name moves on to the next spelling
  assert.equal(toolName(data, { tool_name: 5, toolName: ["x"], tool: { name: 4 }, name: "d" }), "d");
  assert.equal(toolName(data, { tool_name: "", toolName: "b" }), ""); // an empty string is a str: it wins
  assert.equal(toolName(data, {}), "");
});

test("the session id skips empty and non-string values, and falls back to the unidentified spelling", () => {
  assert.equal(sessionId(data, { session_id: "", sessionId: "s2" }), "s2");
  assert.equal(sessionId(data, { session_id: 7, conversation_id: "c" }), "c");
  assert.equal(sessionId(data, { thread_id: "t" }), "t");
  assert.equal(sessionId(data, {}), "nosession");
  assert.equal(toolUseId(data, { tool_use_id: "", call_id: "k" }), "k");
  assert.equal(toolUseId(data, { callId: ["k"] }), "");
});

test("the command is the first string found, and an empty tool_input value falls through to the payload", () => {
  assert.equal(command(data, { tool_input: { command: "a" }, command: "b" }), "a");
  assert.equal(command(data, { tool_input: { command: "" }, command: "b" }), "b");
  assert.equal(command(data, { tool_input: { command: 0 }, command: "b" }), "b");
  // a truthy non-string wins the `or` and then fails `isinstance(str)`: the next spelling is tried
  assert.equal(command(data, { tool_input: { command: ["x"], cmd: "c" }, command: "b" }), "c");
  assert.equal(command(data, { tool_input: { command: { a: 1 } }, command: "b" }), "");
  assert.equal(command(data, { tool_input: { command: "" }, command: "" }), "");
  assert.equal(command(data, { toolInput: { cmd: "viaCmd" } }), "viaCmd");
  assert.equal(command(data, { tool_input: [1], command: "p" }), "p"); // a list is not a tool_input dict
  assert.equal(command(data, {}), "");
});

test("the working directory skips empty and non-string values", () => {
  assert.equal(cwd(data, { cwd: "", workdir: "/w" }), "/w");
  assert.equal(cwd(data, { cwd: 3, working_directory: "/d" }), "/d");
  assert.equal(cwd(data, {}), "");
});

// --------------------------------------------------------------------------------------
// Paths
// --------------------------------------------------------------------------------------

test("every patch path form is read, in order, with white space stripped the Python way", () => {
  const patch =
    "*** Begin Patch\n*** Add File: a.py\n*** Update File: b/c.py \n*** Move to: d/e.py\n*** Delete File: f\n*** End Patch\n";
  assert.deepEqual(filePaths(data, { tool_input: { command: patch } }), ["a.py", "b/c.py", "d/e.py", "f"]);
  // CRLF: the `\r` sits in the captured group until strip() takes it
  assert.deepEqual(filePaths(data, { tool_input: { command: patch.replaceAll("\n", "\r\n") } }), [
    "a.py",
    "b/c.py",
    "d/e.py",
    "f",
  ]);
  // a line anchor sees `\n` only: U+2028 does not end the path, it is part of it
  assert.deepEqual(filePaths(data, { tool_input: { command: "*** Add File: a\u2028b\n" } }), ["a\u2028b"]);
  // the capture is a whole line: `strip()` takes U+2028 and the U+00A0 around it, but not a U+FEFF
  assert.deepEqual(filePaths(data, { tool_input: { command: "*** Add File: \u00a0q\u2028\n" } }), ["q"]);
  assert.deepEqual(filePaths(data, { tool_input: { command: "*** Add File: \ufeffq\n" } }), ["\ufeffq"]);
  // the marker must start a line
  assert.deepEqual(filePaths(data, { tool_input: { command: "x*** Add File: y\n" } }), []);
  assert.deepEqual(filePaths(data, { tool_input: { command: "*** Add File: \n" } }), []);
});

test("paths from guessed keys come first, are de-duplicated by backslash-normalized spelling, and are unmeasured", () => {
  const payload = {
    tool_input: { file_path: "src\\a.py", paths: ["src/a.py", "", 3, "b.py"] },
    path: "p.py",
    files: "not-a-list",
  };
  assert.deepEqual(filePaths(data, payload), ["src\\a.py", "b.py", "p.py"]);
  assert.equal(unmeasuredPathSource(data, payload), true);
  // a measured patch path beside them makes the provenance measured
  const both = { ...payload, command: PATCH };
  assert.equal(unmeasuredPathSource(data, both), false);
  assert.deepEqual(filePaths(data, both), ["src\\a.py", "b.py", "p.py", "x.py"]);
  assert.equal(unmeasuredPathSource(data, {}), false);
});

test("the raw fallback is read as a patch only when the payload has no command", () => {
  assert.deepEqual(filePaths(data, { raw: PATCH }), ["x.py"]);
  assert.deepEqual(filePaths(data, { raw: PATCH, tool_input: { command: "echo" } }), []);
  assert.deepEqual(filePaths(data, { raw: 5 }), []);
});

test("the payload shape names the keys sorted by code point, without values", () => {
  assert.equal(payloadShape(data, {}), "tool_input keys: <none>; payload keys: <none>");
  assert.equal(
    payloadShape(data, {
      tool_input: { z: 1, a: 2, "\u{1F600}": 3, "\uffff": 4 },
      b: 1,
      B: 2,
      "\u{1F600}": 5,
      "\uffff": 6,
    }),
    "tool_input keys: a, z, \uffff, \u{1F600}; payload keys: B, b, tool_input, \uffff, \u{1F600}",
  );
  // the first dict among the spellings is the tool_input; a list is skipped
  assert.equal(
    payloadShape(data, { tool_input: [1], input: { q: 1 } }),
    "tool_input keys: q; payload keys: input, tool_input",
  );
});

// --------------------------------------------------------------------------------------
// json.loads
// --------------------------------------------------------------------------------------

test("json.loads accepts NaN, Infinity and -Infinity where JSON.parse refuses", () => {
  assert.ok(Number.isNaN(jsonLoads("NaN")));
  assert.deepEqual(jsonLoads('{"a": [Infinity, -Infinity], "b": 1}'), { a: [Infinity, -Infinity], b: 1 });
  assert.deepEqual(jsonLoads('{"s": "NaN Infinity"}'), { s: "NaN Infinity" });
  assert.throws(() => jsonLoads('{"x": -NaN}'), JSONDecodeError);
  assert.throws(() => jsonLoads("{NaN: 1}"), JSONDecodeError);
  assert.throws(() => jsonLoads('{"x": Infinityx}'), JSONDecodeError);
  assert.throws(() => jsonLoads('{"x": NaN, }'), JSONDecodeError);
});

test("json.loads refuses an integer literal over 4300 digits with ValueError, not JSONDecodeError", () => {
  const digits = (/** @type {number} */ n) => "1".repeat(n);
  assert.doesNotThrow(() => jsonLoads(`{"x": ${digits(4300)}}`));
  for (const text of [`{"x": ${digits(4301)}}`, `{"x": -${digits(4301)}}`, `{"x": ${digits(5000)}, }`]) {
    assert.throws(
      () => jsonLoads(text),
      (error) => error instanceof Error && error.name === "ValueError",
      text.slice(0, 12),
    );
  }
  // a syntax error before the long literal wins, as the left-to-right scan reaches it first
  assert.throws(() => jsonLoads(`{"x": , "y": ${digits(5000)}}`), JSONDecodeError);
  // a long digit run that is not an integer literal is fine
  assert.doesNotThrow(() => jsonLoads(`{"x": 1.${digits(5000)}}`));
  assert.doesNotThrow(() => jsonLoads(`{"x": ${digits(5000)}e0}`));
  assert.doesNotThrow(() => jsonLoads(`{"x": "${digits(5000)}"}`));
});

test("json.loads raises RecursionError past 9997 levels of nesting (Python 3.12.3), not before", () => {
  assert.doesNotThrow(() => jsonLoads(`${"[".repeat(9997)}${"]".repeat(9997)}`));
  assert.throws(
    () => jsonLoads(`${"[".repeat(9998)}${"]".repeat(9998)}`),
    (error) => error instanceof Error && error.name === "RecursionError",
  );
  assert.throws(
    () => jsonLoads(`${'{"a":'.repeat(9998)}1${"}".repeat(9998)}`),
    (error) => error instanceof Error && error.name === "RecursionError",
  );
  // brackets inside strings do not count
  assert.doesNotThrow(() => jsonLoads(`["${"[".repeat(20000)}"]`));
});

test("json.loads is JSON everywhere else: BOM, trailing commas, quotes and control characters are errors", () => {
  for (const text of [
    '\ufeff{"a": 1}',
    '{"a": 1,}',
    "{'a': 1}",
    '{"a": 01}',
    '{"a": +1}',
    '{"a": 1.}',
    '{"a": "\t"}',
    '{"a": "\\x"}',
    '{"a": 1} x',
  ]) {
    assert.throws(() => jsonLoads(text), JSONDecodeError, text);
  }
  assert.deepEqual(jsonLoads('\r\n\t {"a": "\u2028\\u2028\\ud83d\\ude00"} '), { a: "\u2028\u2028\u{1F600}" });
  assert.deepEqual(jsonLoads('{"__proto__": 5, "a": 1, "a": 2}'), JSON.parse('{"__proto__": 5, "a": 2}'));
});

// --------------------------------------------------------------------------------------
// Process behaviour — stdin, stdout, stderr
// --------------------------------------------------------------------------------------

/** The payload `loadPayload` answers for the given stdin bytes, as JSON text, or the exception class name. */
function loaded(/** @type {Buffer | string} */ input) {
  const run = runSnippet(
    `let out; try { out = JSON.stringify(adapter.loadPayload()); } catch (error) { out = "ERR " + error.name; }
     process.stdout.write(out);`,
    input,
  );
  return run.stdout.toString();
}

test("stdin: empty and blank are {}, a non-JSON text is the raw fallback, a non-object is wrapped", () => {
  assert.equal(loaded(""), "{}");
  assert.equal(loaded(" \n\t\x0b\x1c\u00a0"), "{}"); // Python's strip() cuts all of these
  assert.equal(loaded("not json"), '{"raw":"not json"}');
  assert.equal(loaded('\ufeff{"a": 1}'), '{"raw":"\ufeff{\\"a\\": 1}"}'); // the BOM stays, so it is not JSON
  assert.equal(loaded("[1,2]"), '{"payload":[1,2]}');
  assert.equal(loaded("5"), '{"payload":5}');
  assert.equal(loaded("null"), '{"payload":null}');
  assert.equal(loaded('{"a": 1}'), '{"a":1}');
  assert.equal(loaded('{"a": NaN}'), '{"a":null}'); // JSON.stringify spells NaN null; the point is that it parsed
  assert.equal(loaded('{"a": 1, }'), '{"raw":"{\\"a\\": 1, }"}');
});

test("stdin: CRLF is kept (POSIX stdin has no newline translation), invalid UTF-8 is UnicodeDecodeError", () => {
  assert.equal(loaded('{"a":\r\n1}'), '{"a":1}');
  assert.equal(loaded("x\r\ny"), '{"raw":"x\\r\\ny"}');
  assert.equal(loaded(Buffer.from([0x7b, 0xff, 0x7d])), "ERR UnicodeDecodeError");
  assert.equal(loaded(Buffer.from([0xe2, 0x82])), "ERR UnicodeDecodeError"); // truncated at EOF
  assert.equal(loaded(Buffer.from([0xed, 0xa0, 0x80])), "ERR UnicodeDecodeError"); // an encoded surrogate
});

test("stderr: a lone surrogate is written as a backslash escape, as Python's backslashreplace does", () => {
  const run = runSnippet(`adapter.writeStderr("a\\ud800b\\udc00c\\u{1F600}d");`);
  assert.equal(run.stderr.toString(), "a\\ud800b\\udc00c\u{1F600}d\n");
  assert.equal(typeof writeStderr, "function");
});

test("print_result: the document, key order and ASCII escapes of json.dumps; nothing for no result", () => {
  const run = runSnippet(
    `import { HookResult } from "./hook_core.mjs";
     import { lazyHookData } from "./hook_data.mjs";
     const data = lazyHookData();
     adapter.printResult(data, null);
     adapter.printResult(data, new HookResult({ eventName: "PreToolUse", additionalContext: "é\\n\\u{1F600}", permissionDecision: "deny", permissionReason: "r", systemMessage: "dropped" }));
     adapter.printResult(data, new HookResult({ eventName: "SessionStart" }));`
      .replaceAll('"./hook_core.mjs"', JSON.stringify(new URL("./hook_core.mjs", import.meta.url).href))
      .replaceAll('"./hook_data.mjs"', JSON.stringify(new URL("./hook_data.mjs", import.meta.url).href)),
  );
  assert.equal(
    run.stdout.toString(),
    '{"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": "\\u00e9\\n\\ud83d\\ude00", ' +
      '"permissionDecision": "deny", "permissionDecisionReason": "r"}}\n' +
      '{"hookSpecificOutput": {"hookEventName": "SessionStart"}}\n',
  );
});

// --------------------------------------------------------------------------------------
// The entry point
// --------------------------------------------------------------------------------------

/**
 * Run `codex-hook.mjs` in a fresh project with a private tempdir (so markers start empty).
 * @param {string[]} args
 * @param {Buffer | string} input
 * @param {Record<string, string>} [env]
 * @returns {{status: number | null, stdout: string, stderr: string}}
 */
function runHook(args, input = "", env = {}) {
  /** @type {{status: number | null, stdout: string, stderr: string}} */
  let result = { status: null, stdout: "", stderr: "" };
  withDir((dir) => {
    const project = posix.join(dir, "project");
    fs.mkdirSync(posix.join(project, "_aitna", "akmon"), { recursive: true });
    fs.mkdirSync(posix.join(project, "src"), { recursive: true });
    fs.writeFileSync(posix.join(project, "AGENTS.md"), "# a\n");
    const tmp = posix.join(dir, "tmp");
    fs.mkdirSync(tmp);
    const run = spawnSync(process.execPath, [HOOK, ...args], {
      input: typeof input === "string" ? input.replaceAll("{{root}}", project) : input,
      encoding: "utf8",
      cwd: project,
      env: { ...process.env, TMPDIR: tmp, AITNA_ROOT: "", ...env },
    });
    result = { status: run.status, stdout: run.stdout, stderr: run.stderr };
  });
  return result;
}

test("argv: exactly one route, optionally beside one `--`; anything else is UsageError and exit 1", () => {
  const payload = JSON.stringify({ tool_name: "Bash", tool_input: { command: "sudo ls" } });
  const accepted = [["git-commit-guard"], ["--", "git-commit-guard"], ["git-commit-guard", "--"]];
  for (const argv of accepted) {
    const run = runHook(argv, payload);
    assert.equal(run.status, 0, JSON.stringify(argv));
    assert.match(run.stdout, /permissionDecision": "deny"/);
  }
  const refused = [
    [],
    ["--"],
    ["--", "--"],
    ["--", "git-commit-guard", "--"],
    ["--", "--", "git-commit-guard"],
    ["git-commit-guard", "--", "--"],
    ["git-commit-guard", "git-commit-guard"],
    ["git-commit-guard", "role-on-code"],
    ["-h"],
    ["--help"],
    ["--he"],
    ["-"],
    ["-x"],
    ["git-commit-guard", "-x"],
    ["-x", "git-commit-guard"],
    [""],
    ["Git-Commit-Guard"],
    ["unknown"],
    ["git-commit-guard=1"],
  ];
  for (const argv of refused) {
    const run = runHook(argv, payload);
    assert.equal(run.status, 1, JSON.stringify(argv));
    assert.equal(run.stdout, "", JSON.stringify(argv));
    assert.equal(run.stderr, "akmon codex-hook hook: UsageError\n", JSON.stringify(argv));
  }
});

test("a route that crashes names itself; the class is the Python one, the message is never printed", () => {
  const run = runHook(["analysis-guard"], Buffer.from([0x7b, 0xff, 0x7d]));
  assert.equal(run.status, 1);
  assert.equal(run.stdout, "");
  assert.equal(run.stderr, "akmon codex-hook analysis-guard hook: UnicodeDecodeError\n");
  const big = runHook(["analysis-guard"], `{"x": ${"1".repeat(4301)}}`);
  assert.equal(big.stderr, "akmon codex-hook analysis-guard hook: ValueError\n");
});

test("a cwd Path.resolve() refuses is the Python exception, not a Node argument error", () => {
  const nul = runHook(
    ["role-on-code"],
    '{"tool_name": "apply_patch", "cwd": "a\\u0000b", "tool_input": {"command": ' + JSON.stringify(PATCH) + "}}",
  );
  assert.equal(nul.stderr, "akmon codex-hook role-on-code hook: ValueError\n");
  const lone = runHook(["session-start"], '{"cwd": "a\\ud800b"}');
  assert.equal(lone.stderr, "akmon codex-hook session-start hook: UnicodeEncodeError\n");
});

test("an over-long cwd takes the ordinary failure exit and does not hang (C121)", () => {
  // Fuzz seed 1, case 634: the root walk refuses the start before resolving it.
  const cwd = `/${"a/".repeat(32_769)}`;
  const began = performance.now();
  for (const route of ["analysis-guard", "role-on-code", "session-start"]) {
    const run = runHook([route], JSON.stringify({ tool_name: "apply_patch", cwd, tool_input: { command: PATCH } }));
    assert.equal(run.status, 1, route);
    assert.equal(run.stdout, "", route);
    assert.equal(run.stderr, `akmon codex-hook ${route} hook: ValueError\n`, route);
  }
  assert.ok(performance.now() - began < 10_000);
});

test("an edit with no readable path reports once per event on stderr and prints nothing", () => {
  const payload = JSON.stringify({
    tool_name: "apply_patch",
    session_id: "s1",
    tool_use_id: "u1",
    tool_input: { z: 1, a: 2 },
    b: 1,
  });
  const run = runHook(["role-on-code"], payload);
  assert.equal(run.status, 0);
  assert.equal(run.stdout, "");
  assert.equal(
    run.stderr,
    "akmon codex-hook: 'apply_patch' matched but no file path could be read from the payload — the advisory hooks are inert for this call (tool_input keys: a, z; payload keys: b, session_id, tool_input, tool_name, tool_use_id)\n",
  );
  // a lone surrogate in a payload key reaches stderr escaped, never as U+FFFD
  const keyed = runHook(["role-on-code"], '{"tool_name": "apply_patch", "\\ud800k": 1}');
  assert.match(keyed.stderr, /payload keys: tool_name, \\ud800k\)\n$/);
});

test("a patch through apply_patch and through an inline shell heredoc gets the same advisory", () => {
  const body = "*** Begin Patch\n*** Add File: src/mod.py\n+x = 1\n*** End Patch\n";
  const direct = runHook(
    ["role-on-code"],
    JSON.stringify({ tool_name: "apply_patch", session_id: "s2", cwd: "{{root}}", tool_input: { command: body } }),
  );
  const inline = runHook(
    ["role-on-code"],
    JSON.stringify({
      tool_name: "Bash",
      session_id: "s2",
      cwd: "{{root}}",
      tool_input: { command: heredoc("apply_patch", body) },
    }),
  );
  assert.equal(direct.status, 0);
  assert.match(
    direct.stdout,
    /^\{"hookSpecificOutput": \{"hookEventName": "PreToolUse", "additionalContext": "\[akmon\] Role check/,
  );
  assert.equal(inline.stdout, direct.stdout);
  assert.equal(direct.stderr, "");
});

test("a plain shell call is the route-level diagnostic on stderr, once per session", () => {
  const payload = JSON.stringify({ tool_name: "Bash", session_id: "s3", tool_input: { command: "make build" } });
  const run = runHook(["analysis-guard"], payload);
  assert.equal(run.stdout, "");
  assert.match(run.stderr, /^akmon hook: a shell call may mutate the filesystem/);
});
