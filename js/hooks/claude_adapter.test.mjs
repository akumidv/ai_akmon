/**
 * node:test for `js/hooks/claude_adapter.mjs` — the named pins of the twin: the documents
 * `render_result` writes, the payload `load_payload` accepts and refuses (the places `JSON.parse`
 * and `json.loads` part ways), the crash guard's two channels, and the five Claude entry points
 * run as processes. The expected documents and class names were produced by the Python module.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import { posix } from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

import { pyError } from "../common/pyvalue.mjs";
import { normalizeTool, parsePayload, projectRoot, renderResult, runGuarded } from "./claude_adapter.mjs";
import { HookResult } from "./hook_core.mjs";
import { lazyHookData } from "./hook_data.mjs";

const data = lazyHookData();
const HOOKS = posix.dirname(fileURLToPath(import.meta.url));

/** Run `body` with a fresh directory, removed after. */
function withDir(/** @type {(dir: string) => void} */ body) {
  const dir = fs.mkdtempSync(posix.join(os.tmpdir(), "akmon-claude-adapter-test-"));
  try {
    body(dir);
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
}

/** `body`'s thrown error, for a test that pins its class. */
function thrown(/** @type {() => unknown} */ body) {
  try {
    body();
  } catch (error) {
    return /** @type {Error} */ (error);
  }
  throw new Error("expected a throw");
}

test("normalizeTool: Claude's edit and read tools map to the neutral kinds, the rest pass through", () => {
  for (const [given, expected] of [
    ["Edit", "edit"], ["Write", "edit"], ["MultiEdit", "edit"], ["Read", "read"], ["Grep", "read"], ["Glob", "read"],
    ["Bash", "Bash"], ["edit", "edit"], ["", ""], ["NotebookEdit", "NotebookEdit"], ["Task", "Task"],
  ]) {
    assert.equal(normalizeTool(data, given), expected, given);
  }
});

test("renderResult: the one document, keys in the order the Python writes them, ASCII only", () => {
  assert.equal(
    renderResult(data, new HookResult({
      eventName: "PreToolUse", additionalContext: "é", permissionDecision: "deny", permissionReason: "r",
      systemMessage: "m", decision: "block", reason: "",
    })),
    '{"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": "\\u00e9", ' +
      '"permissionDecision": "deny", "permissionDecisionReason": "r"}, "decision": "block", "reason": "", "systemMessage": "m"}',
  );
  assert.equal(
    renderResult(data, new HookResult({ eventName: "Stop", decision: "block", reason: "why" })),
    '{"hookSpecificOutput": {"hookEventName": "Stop"}, "decision": "block", "reason": "why"}',
  );
  assert.equal(
    renderResult(data, new HookResult({ eventName: "SessionStart", additionalContext: "a\nb\u2028\u{1f9ed}" })),
    '{"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "a\\nb\\u2028\\ud83e\\udded"}}',
  );
  assert.equal(renderResult(data, new HookResult({ eventName: "X", systemMessage: "" })), '{"hookSpecificOutput": {"hookEventName": "X"}, "systemMessage": ""}');
  assert.equal(renderResult(data, null), null);
});

test("parsePayload: an object, else {} — and json.loads's own grammar, not JSON.parse's", () => {
  const bytes = (/** @type {string} */ text) => Buffer.from(text, "latin1");
  for (const [name, input] of /** @type {[string, string | Uint8Array][]} */ ([
    ["empty", ""], ["blank", "  \n\t "], ["null", "null"], ["list", "[]"], ["list of one", "[1]"], ["string", '"s"'],
    ["number", "5"], ["broken", "{"], ["BOM", "\ufeff{}"], ["trailing data", "{} x"], ["trailing comma", '{"a":1,}'],
    ["single quotes", "{'a':1}"], ["leading zero", '{"a":01}'], ["control character", '{"a":"x\ty"}'], ["NUL", '{"a":"\0"}'],
    ["bad UTF-8", bytes('{"a":"\xff"}')], ["a lone start byte", Buffer.from([0x7b, 0x7d, 0xc3])],
    ["integer of 4301 digits", `{"a":${"1".repeat(4301)}}`], ["negative of 4301 digits", `{"a":-${"1".repeat(4301)}}`],
    ["a list nested 9997 deep", "[".repeat(9997) + "]".repeat(9997)],
  ])) {
    assert.deepEqual(parsePayload(input), {}, name);
  }
  assert.deepEqual(parsePayload('\t{\t"tool_name"\t:\t"Edit"\t}\t'), { tool_name: "Edit" });
  assert.deepEqual(parsePayload('{\r\n"tool_name":"Edit"\r\n}'), { tool_name: "Edit" });
  assert.deepEqual(parsePayload('{"tool_name":"Bash","tool_name":"Edit"}'), { tool_name: "Edit" });
  assert.deepEqual(parsePayload('{"a":"\\ud800","b":"\\u0045"}'), { a: "\ud800", b: "E" });
  assert.deepEqual(parsePayload(`{"a":${"1".repeat(4300)}}`).a > 1e300, true);
  assert.deepEqual(parsePayload(`{"a":${"1".repeat(4301)}.0}`).a > 1e300, true); // a float literal has no digit limit
  const nested = parsePayload(`${'{"a":'.repeat(9997)}1${"}".repeat(9997)}`);
  assert.deepEqual(Object.keys(nested), ["a"]);
});

test("parsePayload: NaN and Infinity are accepted as Python's json accepts them", () => {
  const payload = parsePayload('{"tool_name":"Edit","agent_id":NaN,"up":Infinity,"down":-Infinity,"list":[NaN,-0,1E400]}');
  assert.equal(payload.tool_name, "Edit");
  assert.ok(Number.isNaN(payload.agent_id));
  assert.equal(payload.up, Infinity);
  assert.equal(payload.down, -Infinity);
  assert.deepEqual(payload.list.slice(1), [-0, Infinity]);
  assert.deepEqual(parsePayload('{"a":NaN,"b":'), {}); // and still an error where the grammar breaks
  assert.deepEqual(parsePayload("{NaN:1}"), {});
  assert.deepEqual(parsePayload('{"a":Infinit}'), {});
  assert.deepEqual(parsePayload('{"a":-Inf}'), {});
  assert.deepEqual(parsePayload('{"a":nan}'), {});
});

test("parsePayload: a key named __proto__ is an own entry, as in a dict", () => {
  const payload = parsePayload('{"__proto__":{"x":1},"y":NaN}');
  assert.equal(Object.hasOwn(payload, "__proto__"), true);
  assert.equal(Object.getPrototypeOf(payload), Object.prototype);
});

test("parsePayload: nesting past what Python's scanner takes is the RecursionError it raises, not {}", () => {
  assert.equal(thrown(() => parsePayload("[".repeat(9998) + "]".repeat(9998))).name, "RecursionError");
  assert.equal(thrown(() => parsePayload(`${'{"a":'.repeat(9998)}1${"}".repeat(9998)}`)).name, "RecursionError");
  assert.equal(thrown(() => parsePayload("[".repeat(20000))).name, "RecursionError");
  assert.deepEqual(parsePayload(`{"s":"${"[".repeat(20000)}"}`), { s: "[".repeat(20000) }); // brackets in a string are not nesting
});

test("projectRoot: the payload's cwd, walked up to the project; a path no call can take is the Python exception", () => {
  withDir((dir) => {
    const real = fs.realpathSync(dir);
    fs.mkdirSync(posix.join(real, "_aitna"));
    fs.mkdirSync(posix.join(real, "src/deep"), { recursive: true });
    fs.writeFileSync(posix.join(real, "AGENTS.md"), "# a\n");
    fs.writeFileSync(posix.join(real, "_aitna/.akmon.toml"), 'mount = "package"\n');
    assert.equal(projectRoot({ cwd: `${real}/src/deep` }), real);
    assert.equal(projectRoot({ cwd: `${real}//src/./deep/` }), real);
    assert.equal(projectRoot({ cwd: `${real}/src/deep/..` }), real);
    assert.equal(projectRoot({ cwd: "/nonexistent-akmon-dir/x" }), "/nonexistent-akmon-dir/x"); // no project: the start itself
  });
  assert.equal(thrown(() => projectRoot({ cwd: "/tmp/a\0b" })).name, "ValueError");
  assert.equal(thrown(() => projectRoot({ cwd: "/tmp/\ud800" })).name, "UnicodeEncodeError");
  assert.equal(thrown(() => projectRoot(/** @type {any} */ ([1]))).name, "AttributeError");
});

/** Run `body` with the process's two output streams captured. */
function captured(/** @type {() => number} */ body) {
  /** @type {string[]} */ const out = [];
  /** @type {string[]} */ const err = [];
  const stdoutWrite = process.stdout.write;
  const stderrWrite = process.stderr.write;
  process.stdout.write = /** @type {any} */ ((/** @type {string} */ text) => (out.push(text), true));
  process.stderr.write = /** @type {any} */ ((/** @type {string} */ text) => (err.push(text), true));
  try {
    const code = body();
    return { code, out: out.join(""), err: err.join("") };
  } finally {
    process.stdout.write = stdoutWrite;
    process.stderr.write = stderrWrite;
  }
}

test("runGuarded: the document on stdout, nothing for no result, exit 0 either way", () => {
  const spoke = captured(() => runGuarded("h", data, () => new HookResult({ eventName: "PreToolUse", additionalContext: "hi" })));
  assert.deepEqual(spoke, {
    code: 0, err: "", out: '{"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": "hi"}}\n',
  });
  assert.deepEqual(captured(() => runGuarded("h", data, () => null)), { code: 0, out: "", err: "" });
});

test("runGuarded: a crash is the class on stderr and the owner's notice on stdout, never the message", () => {
  const crashed = captured(() => runGuarded("role-on-code", data, () => {
    throw pyError("KeyError", "secret/path");
  }));
  assert.equal(crashed.code, 0);
  assert.equal(crashed.err, "akmon role-on-code hook: KeyError\n");
  assert.equal(
    crashed.out,
    '{"systemMessage": "\\u26a0 akmon: the role-on-code hook failed (KeyError) and was skipped \\u2014 this action went ahead ' +
      "without it. Check the setup: `akmon verify` (a mounted tree: `python3 _aitna/akmon/bin/verify.py`).\"}\n",
  );
  const system = captured(() => runGuarded("h", data, () => {
    fs.readFileSync("/nonexistent/akmon");
    return null;
  }));
  assert.equal(system.err, "akmon h hook: FileNotFoundError\n");
  assert.equal(JSON.parse(system.out).systemMessage.includes("secret"), false);
});

test("runGuarded: a render failure is a caught crash, and the crash path reads no data file", () => {
  const broken = /** @type {any} */ ({ get vocabulary() { throw pyError("DataFileError", "akmon data file missing: /x"); } });
  const result = captured(() => runGuarded("h", broken, () => new HookResult({ eventName: "PreToolUse" })));
  assert.equal(result.err, "akmon h hook: DataFileError\n");
  assert.match(result.out, /^\{"systemMessage": "\\u26a0 akmon: the h hook failed \(DataFileError\)/);
  assert.equal(result.code, 0);
});

/**
 * Run one entry point as a process on `payload` (an object or raw stdin text).
 * @param {string} script
 * @param {unknown} payload
 * @param {Record<string, string>} [env]
 */
function run(script, payload, env = {}) {
  const input = typeof payload === "string" || payload instanceof Uint8Array ? payload : JSON.stringify(payload);
  const result = spawnSync("node", [`${HOOKS}/${script}.mjs`], {
    input, env: { ...process.env, AITNA_ROOT: "", AKMON_DELEGATION_GRACE: "", ...env }, encoding: "utf8",
  });
  return { stdout: result.stdout, stderr: result.stderr, status: result.status };
}

/** A project (`AGENTS.md`, a package record, one agent) and a private tempdir for the state files. */
function withProject(/** @type {(project: string, tmp: string) => void} */ body) {
  withDir((dir) => {
    const project = fs.realpathSync(dir);
    fs.mkdirSync(posix.join(project, "_aitna/agents/engineer"), { recursive: true });
    fs.mkdirSync(posix.join(project, "tmp"));
    fs.writeFileSync(posix.join(project, "AGENTS.md"), "# a\n");
    fs.writeFileSync(posix.join(project, "_aitna/.akmon.toml"), 'mount = "package"\n');
    fs.writeFileSync(posix.join(project, "_aitna/agents/engineer/README.md"), "e\n");
    body(project, posix.join(project, "tmp"));
  });
}

test("role-on-code and analysis-guard run as processes: first edit speaks, the second is silent", () => {
  withProject((project, tmp) => {
    const env = { TMPDIR: tmp };
    const edit = (/** @type {string} */ file, /** @type {string} */ session) => ({
      tool_name: "Edit", session_id: session, cwd: project, tool_input: { file_path: `${project}/${file}` },
    });
    const first = run("role-on-code", edit("src/a.py", "s1"), env);
    assert.equal(first.status, 0);
    assert.equal(first.stderr, "");
    assert.match(first.stdout, /^\{"hookSpecificOutput": \{"hookEventName": "PreToolUse", "additionalContext": "\[akmon\] Role check /);
    assert.equal(run("role-on-code", edit("src/b.py", "s1"), env).stdout, "");
    assert.equal(run("role-on-code", edit("docs/c.py", "s2"), env).stdout, "");
    assert.match(run("analysis-guard", edit("_aitna/TASKS.md", "s1"), env).stdout, /Analysis-before-mutation check/);
    assert.equal(run("analysis-guard", edit("_aitna/TASKS.md", "s1"), env).stdout, "");
    assert.equal(run("analysis-guard", { ...edit("_aitna/TASKS.md", "s9"), tool_name: "Read" }, env).stdout, "");
    // a tool_input that is not an object is the AttributeError `.get` raises
    const crashed = run("role-on-code", { tool_name: "Edit", tool_input: [1], cwd: project }, env);
    assert.equal(crashed.stderr, "akmon role-on-code hook: AttributeError\n");
    assert.equal(crashed.status, 0);
  });
});

test("git-commit-guard runs as a process: sudo and the AI trailer deny, push asks, the notice goes to stderr once", () => {
  withProject((project, tmp) => {
    const env = { TMPDIR: tmp };
    const bash = (/** @type {unknown} */ command, /** @type {Record<string, unknown>} */ more = {}) => ({
      tool_name: "Bash", session_id: "g1", cwd: project, permission_mode: "default", tool_input: { command }, ...more,
    });
    const sudo = run("git-commit-guard", bash("sudo ls"), env);
    assert.match(sudo.stdout, /"permissionDecision": "deny", "permissionDecisionReason": "Privilege-escalation guardrail/);
    assert.match(sudo.stderr, /^akmon hook: a shell call may mutate the filesystem/);
    assert.equal(run("git-commit-guard", bash("sudo ls"), env).stderr, ""); // once per session
    assert.match(run("git-commit-guard", bash("git commit -m 'Co-Authored-By: x'"), env).stdout, /"permissionDecision": "deny"/);
    assert.match(run("git-commit-guard", bash("git push"), env).stdout, /"permissionDecision": "ask"/);
    assert.match(run("git-commit-guard", bash("git push", { permission_mode: "auto" }), env).stdout, /"permissionDecision": "deny"/);
    assert.equal(run("git-commit-guard", bash("ls"), env).stdout, "");
    assert.equal(run("git-commit-guard", { ...bash("git push"), tool_name: "Edit" }, env).stdout, "");
    // a non-string command is the TypeError re.search raises: crash-open, the command goes ahead
    const crashed = run("git-commit-guard", bash(5), env);
    assert.equal(crashed.stderr, "akmon git-commit-guard hook: TypeError\n");
    assert.equal(crashed.status, 0);
  });
});

test("delegation-nudge runs as a process: it counts, nudges once, and a subagent is exempt", () => {
  withProject((project, tmp) => {
    const env = { TMPDIR: tmp };
    fs.writeFileSync(posix.join(tmp, "akmon-delegation-nudge-n1.count"), "33 30.0");
    const call = (/** @type {string} */ tool, /** @type {Record<string, unknown>} */ more = {}) =>
      run("delegation-nudge", { tool_name: tool, session_id: "n1", cwd: project, permission_mode: "default", ...more }, env);
    assert.match(call("Edit").stdout, /a drift score of 31 \(an edit or shell call counts 1, a read \\u00bd, the first 8 calls of a stretch nothing\)/);
    assert.equal(call("Edit").stdout, "");
    assert.equal(fs.readFileSync(posix.join(tmp, "akmon-delegation-nudge-n1.count"), "utf8"), "35 32.0");
    assert.equal(call("Read", { agent_id: "a1" }).stdout, "");
    assert.equal(fs.readFileSync(posix.join(tmp, "akmon-delegation-nudge-n1.count"), "utf8"), "35 32.0");
    assert.equal(call("Agent").stdout, "");
    assert.equal(fs.readFileSync(posix.join(tmp, "akmon-delegation-nudge-n1.count"), "utf8"), "0");
    assert.equal(fs.existsSync(posix.join(tmp, "akmon-delegation-nudge-n1.marker")), false);
  });
});

test("session-start-agent runs as a process: the roster from the payload's cwd, or CLAUDE_PROJECT_DIR", () => {
  withProject((project, tmp) => {
    const env = { TMPDIR: tmp };
    const viaPayload = run("session-start-agent", { session_id: "x", cwd: project }, env);
    assert.match(viaPayload.stdout, /\\n- DEVELOP \(build the project\): engineer\\n/);
    assert.equal(run("session-start-agent", {}, { ...env, CLAUDE_PROJECT_DIR: project }).stdout, viaPayload.stdout);
    assert.equal(run("session-start-agent", { cwd: "" }, { ...env, CLAUDE_PROJECT_DIR: project }).stdout, viaPayload.stdout);
    // `Path(5)` is a TypeError; the session still starts
    const crashed = run("session-start-agent", { cwd: 5 }, env);
    assert.equal(crashed.stderr, "akmon session-start-agent hook: TypeError\n");
    assert.equal(crashed.status, 0);
    assert.equal(run("session-start-agent", "not json", { ...env, CLAUDE_PROJECT_DIR: project }).stdout, viaPayload.stdout);
  });
});
