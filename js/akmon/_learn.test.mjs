/**
 * node:test for `js/akmon/_learn.mjs` — the twin of `akmon learn` in `src/akmon/_learn.py` (C177).
 * The texts and exit codes are the Python's; the process is a fake (`LearnIO`), so the clock, the
 * environment, the cwd and the streams are the test's.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { LearningState, parseUtc, readState, writeState } from "../common/learning.mjs";
import { transcriptsDir } from "../common/transcripts.mjs";
import { main } from "./_learn.mjs";

const NOW = "2026-10-28T12:00:00Z";

/**
 * A fake process over a scratch project, with its Claude and Codex homes.
 * @param {{record?: string, now?: string}} [options]
 */
function terminal({ record = "", now = NOW } = {}) {
  const base = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), "akmon-learn-")));
  const root = path.join(base, "proj");
  fs.mkdirSync(path.join(root, "_aitna"), { recursive: true });
  fs.writeFileSync(path.join(root, "AGENTS.md"), "# a\n");
  fs.writeFileSync(path.join(root, "_aitna", ".akmon.toml"), record);
  const claudeHome = path.join(base, "claude");
  const codexHome = path.join(base, "codex");
  const term = {
    base,
    root,
    claudeHome,
    codexHome,
    state: path.join(root, "_aitna", "local", "learning.json"),
    out: "",
    err: "",
    io: {
      environ: /** @type {Record<string, string | undefined>} */ ({
        CLAUDE_CONFIG_DIR: claudeHome,
        CODEX_HOME: codexHome,
      }),
      cwd: root,
      out: { write: (/** @type {string} */ text) => void (term.out += text) },
      err: { write: (/** @type {string} */ text) => void (term.err += text) },
      now: () => parseUtc(now),
    },
    /** @param {string[]} argv */
    run(argv) {
      term.out = "";
      term.err = "";
      return main(argv, term.io);
    },
  };
  return term;
}

/**
 * A session file stamped at `seconds`.
 * @param {string} file
 * @param {string} text
 * @param {number} seconds
 */
function stamped(file, text, seconds) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, text);
  fs.utimesSync(file, seconds, seconds);
}

const at = (/** @type {string} */ text) => parseUtc(text).getTime() / 1000;

test("status before any run says never run, no counting, and the thresholds", () => {
  const term = terminal();
  assert.equal(term.run(["status"]), 0);
  assert.equal(
    term.out,
    "last run: never\n" +
      "counting since: no session recorded yet\n" +
      "sessions since the last run: 0\n" +
      "days since the last run (or since counting began): -\n" +
      "reminder at 10 sessions or 7 days (from <dev root>/.akmon.toml [learning])\n" +
      "state: _aitna/local/learning.json\n",
  );
  assert.equal(term.err, "");
});

test("status reports the run, the count, the days and the configured thresholds", () => {
  const term = terminal({ record: "[learning]\nreminder_sessions = 4\n" });
  writeState(new LearningState("2026-10-21T12:00:00Z", null, ["a", "b"]), term.state);
  assert.equal(term.run(["status"]), 0);
  assert.equal(
    term.out,
    "last run: 2026-10-21T12:00:00Z\n" +
      "counting since: no session recorded yet\n" +
      "sessions since the last run: 2\n" +
      "days since the last run (or since counting began): 7\n" +
      "reminder at 4 sessions or 7 days (from <dev root>/.akmon.toml [learning])\n" +
      "state: _aitna/local/learning.json\n",
  );
  writeState(new LearningState(null, "2026-10-26T12:00:00Z", ["a"]), term.state);
  term.run(["status"]);
  assert.match(term.out, /^last run: never\ncounting since: 2026-10-26T12:00:00Z\nsessions since the last run: 1\n/);
});

test("mark records the run, resets the count, and says when", () => {
  const term = terminal();
  writeState(new LearningState(null, "2026-10-26T12:00:00Z", ["a", "b"]), term.state);
  assert.equal(term.run(["mark"]), 0);
  assert.equal(term.out, `akmon learn: learning run recorded at ${NOW}; the counted sessions are cleared\n`);
  const state = readState(term.state);
  assert.deepEqual([state.lastRun, state.since, [...state.sessions]], [NOW, null, []]);
});

test("sessions lists this project's Claude transcripts and Codex rollouts, never another project's", () => {
  const term = terminal();
  const mine = transcriptsDir(term.root, term.claudeHome);
  stamped(path.join(mine, "aaa.jsonl"), "1", at("2026-10-27T10:00:00Z"));
  stamped(path.join(mine, "bbb.jsonl"), "12", at("2026-10-27T11:00:00Z"));
  stamped(path.join(mine, "bbb", "subagents", "agent-1.jsonl"), "x", at("2026-10-27T12:00:00Z"));
  stamped(path.join(term.claudeHome, "projects", "-elsewhere", "zzz.jsonl"), "x", at("2026-10-27T12:00:00Z"));
  const day = path.join(term.codexHome, "sessions", "2026", "10", "28");
  const meta = (/** @type {Record<string, unknown>} */ payload) =>
    `${JSON.stringify({ type: "session_meta", payload })}\n`;
  stamped(path.join(day, "rollout-1.jsonl"), meta({ id: "cx1", cwd: term.root }), at("2026-10-27T10:30:00Z"));
  stamped(path.join(day, "rollout-2.jsonl"), meta({ id: "cx2", cwd: "/elsewhere" }), at("2026-10-27T10:30:00Z"));
  stamped(
    path.join(day, "rollout-3.jsonl"),
    meta({ id: "cx3", cwd: term.root, source: { subagent: 1 } }),
    at("2026-10-27T10:30:00Z"),
  );
  assert.equal(term.run(["sessions"]), 0);
  const rollout = path.join(day, "rollout-1.jsonl");
  assert.equal(
    term.out,
    `akmon learn: listed at ${NOW} (pass it as \`akmon learn mark --at ${NOW}\`)\n` +
      "kind\tsession\tmodified\tbytes\tpath\n" +
      `claude\taaa\t2026-10-27T10:00:00Z\t1\t${path.join(mine, "aaa.jsonl")}\n` +
      `codex\tcx1\t2026-10-27T10:30:00Z\t${fs.statSync(rollout).size}\t${rollout}\n` +
      `claude\tbbb\t2026-10-27T11:00:00Z\t2\t${path.join(mine, "bbb.jsonl")}\n`,
  );
});

test("sessions after a run lists only what changed since it, and says so when nothing did", () => {
  const term = terminal();
  const mine = transcriptsDir(term.root, term.claudeHome);
  assert.equal(term.run(["sessions"]), 0);
  assert.deepEqual(term.out.split("\n").slice(1), ["akmon learn: no sessions of this project found", ""]);
  stamped(path.join(mine, "old.jsonl"), "", at("2026-10-20T00:00:00Z"));
  stamped(path.join(mine, "new.jsonl"), "", at("2026-10-27T00:00:00Z"));
  writeState(new LearningState("2026-10-25T00:00:00Z"), term.state);
  term.run(["sessions"]);
  assert.deepEqual(
    term.out
      .split("\n")
      .slice(2, -1)
      .map((line) => line.split("\t")[1]),
    ["new"],
  );
  writeState(new LearningState("2026-10-28T00:00:00Z"), term.state);
  term.run(["sessions"]);
  assert.deepEqual(term.out.split("\n").slice(1), [
    "akmon learn: no sessions of this project since 2026-10-28T00:00:00Z",
    "",
  ]);
});

test("sessions before the first run are bounded by since, and --all lists everything", () => {
  const term = terminal();
  const mine = transcriptsDir(term.root, term.claudeHome);
  stamped(path.join(mine, "old.jsonl"), "", at("2026-09-01T00:00:00Z"));
  stamped(path.join(mine, "new.jsonl"), "", at("2026-10-27T00:00:00Z"));
  writeState(new LearningState(null, "2026-10-25T00:00:00Z", ["new"]), term.state);
  const listed = () =>
    term.out
      .split("\n")
      .slice(2, -1)
      .map((line) => line.split("\t")[1]);
  assert.equal(term.run(["sessions"]), 0);
  assert.deepEqual(listed(), ["new"]);
  assert.equal(term.run(["sessions", "--all"]), 0);
  assert.deepEqual(listed(), ["old", "new"]);
  stamped(path.join(mine, "new.jsonl"), "", at("2026-10-20T00:00:00Z"));
  term.run(["sessions"]);
  assert.equal(term.out.split("\n")[1], "akmon learn: no sessions of this project since 2026-10-25T00:00:00Z");
});

test("mark --at stamps the listing time; a future or malformed time is refused", () => {
  const term = terminal();
  writeState(new LearningState(null, "2026-10-26T12:00:00Z", ["a"]), term.state);
  assert.equal(term.run(["mark", "--at", "2026-10-28T11:59:00Z"]), 0);
  assert.equal(readState(term.state).lastRun, "2026-10-28T11:59:00Z");
  assert.equal(term.run(["mark", "--at", "2999-01-01T00:00:00Z"]), 2);
  assert.match(term.err, /^akmon learn: --at 2999-01-01T00:00:00Z is after the current time 2026-10-28T12:00:00Z\n$/);
  assert.equal(term.run(["mark", "--at", "yesterday"]), 2);
  assert.match(term.err, /^akmon learn: not a UTC ISO-seconds time: 'yesterday'\n$/);
  assert.equal(readState(term.state).lastRun, "2026-10-28T11:59:00Z");
});

test("a held lock is one line and exit 2 for mark", () => {
  const term = terminal();
  fs.mkdirSync(path.dirname(term.state), { recursive: true });
  fs.writeFileSync(`${term.state}.lock`, "1\n");
  assert.equal(term.run(["mark"]), 2);
  assert.match(term.err, /^akmon learn: .*learning\.json\.lock is held by another process\n$/);
});

test("the harness homes default to ~/.claude and ~/.codex when the environment names none", () => {
  const term = terminal();
  term.io.environ = {};
  assert.equal(term.run(["sessions"]), 0, term.err);
  assert.match(term.out, /\nakmon learn: no sessions of this project/);
});

test("no arguments, an unknown command and extra arguments are usage errors", () => {
  const term = terminal();
  assert.equal(term.run([]), 2);
  assert.match(
    term.err,
    /^usage: akmon learn status \| sessions \[--all\] \| mark \[--at TIME\] {3}\(each takes \[--project-root PATH\]\)\n/,
  );
  assert.equal(term.out, "");
  assert.equal(term.run(["bogus"]), 2);
  assert.match(term.err, /^akmon learn: unknown command 'bogus'\nusage: akmon learn status/);
  assert.equal(term.run(["status", "x"]), 2);
  assert.match(term.err, /^akmon learn: status takes no arguments; got 'x'\nusage: /);
  assert.equal(term.run(["mark", "-f"]), 2);
  assert.match(term.err, /^akmon learn: mark takes only --at TIME; got '-f'\n/);
  assert.equal(term.run(["mark", "--at"]), 2);
  assert.match(term.err, /^akmon learn: mark --at takes one time, e\.g\. 2026-10-28T09:30:00Z\n/);
  assert.equal(term.run(["sessions", "--none"]), 2);
  assert.match(term.err, /^akmon learn: sessions takes only --all; got '--none'\n/);
});

test("-h and --help print the usage on stdout and exit 0", () => {
  const term = terminal();
  for (const flag of ["-h", "--help"]) {
    assert.equal(term.run([flag]), 0);
    assert.match(
      term.out,
      /^usage: akmon learn status \| sessions \[--all\] \| mark \[--at TIME\] {3}\(each takes \[--project-root PATH\]\)\n {2}status {9}sessions and days since/,
    );
    assert.equal(term.err, "");
  }
});

test("a failure of the command is one line and exit 2", () => {
  const term = terminal();
  fs.mkdirSync(term.state, { recursive: true }); // a directory where the record belongs: mark cannot replace it
  assert.equal(term.run(["mark"]), 2);
  assert.match(term.err, /^akmon learn: .*\n$/);
  assert.equal(term.out, "");
});

test("a cwd outside any project falls back to it with the shared notice", () => {
  const term = terminal();
  const lone = path.join(term.base, "lone");
  fs.mkdirSync(lone);
  term.io.cwd = lone;
  assert.equal(term.run(["status"]), 0);
  assert.match(term.err, /^\[akmon\] no project root at or above /);
  assert.match(term.out, /^last run: never\n/);
});

test("--project-root names the project from a cwd that is inside none, with no notice", () => {
  const term = terminal();
  const lone = path.join(term.base, "lone");
  fs.mkdirSync(lone);
  term.io.cwd = lone;
  assert.equal(term.run(["status", "--project-root", term.root]), 0, term.err);
  assert.equal(term.err, "");
  assert.match(term.out, /^last run: never\n/);
  assert.match(term.out, /\nstate: _aitna\/local\/learning\.json\n$/);
  // a relative value is taken against the cwd
  term.io.cwd = term.base;
  assert.equal(term.run(["sessions", "--project-root", "proj", "--all"]), 0, term.err);
  assert.equal(term.err, "");
});

test("--project-root with no path, or twice, is a usage error", () => {
  const term = terminal();
  assert.equal(term.run(["status", "--project-root"]), 2);
  assert.match(term.err, /^akmon learn: --project-root takes a path\nusage: /);
  assert.equal(term.run(["status", "--project-root", "--all"]), 2);
  assert.match(term.err, /^akmon learn: --project-root takes a path\nusage: /);
  assert.equal(term.run(["status", "--project-root", term.root, "--project-root", term.root]), 2);
  assert.match(term.err, /^akmon learn: --project-root given twice\nusage: /);
});

test("mark with no project root prints the notice, exits 2 and writes nothing", () => {
  const term = terminal();
  const lone = path.join(term.base, "lone");
  fs.mkdirSync(lone);
  term.io.cwd = lone;
  assert.equal(term.run(["mark"]), 2);
  assert.match(term.err, /^\[akmon\] no project root at or above /);
  assert.ok(term.err.includes("pass --project-root to name the root instead"));
  assert.equal(term.out, "");
  assert.deepEqual(fs.readdirSync(lone), []);
  assert.equal(fs.existsSync(term.state), false);
  // and the same command with the root named does write
  assert.equal(term.run(["mark", "--project-root", term.root]), 0, term.err);
  assert.equal(fs.existsSync(term.state), true);
});
