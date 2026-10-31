/**
 * node:test for `js/common/transcripts.mjs` — the twin of the transcript-location half of
 * `meta/tests/test_stats.py` and of the session discovery `akmon learn` reads (C177). The cases
 * and literals are the Python's, so a drift in either twin shows as a failing literal.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import {
  CLAUDE,
  CODEX,
  claudeSessions,
  codexSessions,
  mungedProjectDir,
  newestJsonl,
  pyStem,
  pySuffix,
  transcriptsDir,
} from "./transcripts.mjs";

/** A fresh scratch directory (resolved, so a symlinked tmp does not skew a comparison). */
function scratch() {
  return fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), "akmon-transcripts-")));
}

/**
 * A file stamped at `seconds` since the epoch.
 * @param {string} file
 * @param {string} text
 * @param {number} seconds
 */
function stamped(file, text, seconds) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, text);
  fs.utimesSync(file, seconds, seconds);
}

/**
 * A Codex rollout whose first line is a `session_meta` record.
 * @param {string} file
 * @param {Record<string, unknown>} payload
 * @param {number} seconds
 */
function rollout(file, payload, seconds) {
  stamped(file, `${JSON.stringify({ type: "session_meta", payload })}\n{"type":"event"}\n`, seconds);
}

test("munged names replace every non-alphanumeric character with a dash", () => {
  assert.equal(mungedProjectDir("/a/b"), "-a-b");
  assert.equal(mungedProjectDir("/a/_b.c"), "-a--b-c");
  assert.equal(mungedProjectDir("/home/a/_cto"), "-home-a--cto");
  assert.equal(mungedProjectDir("/a/Z9"), "-a-Z9");
});

test("munged names count a non-ASCII character per UTF-16 code unit", () => {
  assert.equal(mungedProjectDir("/a/é"), "-a--");
  assert.equal(mungedProjectDir("/a/\u{1F600}"), "-a---");
});

test("the transcript dir is <claude-home>/projects/<munged root>", () => {
  assert.equal(transcriptsDir("/a/b", "/h/.claude"), "/h/.claude/projects/-a-b");
  assert.equal(transcriptsDir("/a/b"), path.join(os.homedir(), ".claude", "projects", "-a-b"));
});

test("Path.suffix and Path.stem follow the stdlib's dotfile rules", () => {
  assert.equal(pySuffix("a.jsonl"), ".jsonl");
  assert.equal(pySuffix(".jsonl"), "");
  assert.equal(pySuffix("a."), "");
  assert.equal(pyStem("/x/agent-1.meta.json"), "agent-1.meta");
  assert.equal(pyStem("/x/.jsonl"), ".jsonl");
});

test("newestJsonl ignores non-jsonl files and a missing directory", () => {
  const dir = scratch();
  assert.equal(newestJsonl(path.join(dir, "missing")), null);
  assert.equal(newestJsonl(dir), null);
  stamped(path.join(dir, "old.jsonl"), "", 1000);
  stamped(path.join(dir, "new.jsonl"), "", 2000);
  stamped(path.join(dir, "other.txt"), "", 3000);
  fs.mkdirSync(path.join(dir, "dir.jsonl"));
  assert.equal(newestJsonl(dir), path.join(dir, "new.jsonl"));
});

/** A project root and the Claude home that holds its transcripts. */
function claudeFixture() {
  const base = scratch();
  const root = path.join(base, "proj");
  const claudeHome = path.join(base, "claude");
  fs.mkdirSync(root);
  return { base, root, claudeHome, directory: transcriptsDir(root, claudeHome) };
}

test("claudeSessions lists this project's top-level transcripts, oldest first", () => {
  const { root, claudeHome, directory } = claudeFixture();
  stamped(path.join(directory, "bbb.jsonl"), "12345", 2000);
  stamped(path.join(directory, "aaa.jsonl"), "1", 1000);
  stamped(path.join(directory, "ccc", "subagents", "agent-1.jsonl"), "x", 3000);
  stamped(path.join(directory, "notes.txt"), "x", 3000);
  stamped(path.join(claudeHome, "projects", "-other-project", "zzz.jsonl"), "x", 3000);
  const found = claudeSessions(root, claudeHome);
  assert.deepEqual(
    found.map((item) => [item.kind, item.sessionId, item.size, item.path]),
    [
      [CLAUDE, "aaa", 1, path.join(directory, "aaa.jsonl")],
      [CLAUDE, "bbb", 5, path.join(directory, "bbb.jsonl")],
    ],
  );
  assert.equal(found[0].modified.getTime(), 1000 * 1000);
});

test("claudeSessions keeps only files modified after `since`, and tolerates an absent directory", () => {
  const { root, claudeHome, directory } = claudeFixture();
  assert.deepEqual(claudeSessions(root, claudeHome), []);
  stamped(path.join(directory, "aaa.jsonl"), "", 1000);
  stamped(path.join(directory, "bbb.jsonl"), "", 2000);
  assert.deepEqual(
    claudeSessions(root, claudeHome, new Date(1000 * 1000)).map((item) => item.sessionId),
    ["bbb"],
  );
  assert.deepEqual(claudeSessions(root, claudeHome, new Date(2000 * 1000)), []);
});

test("sessions of one instant order by modification time, then by name", () => {
  const { root, claudeHome, directory } = claudeFixture();
  stamped(path.join(directory, "b.jsonl"), "", 1000);
  stamped(path.join(directory, "a.jsonl"), "", 1000);
  stamped(path.join(directory, "c.jsonl"), "", 999);
  assert.deepEqual(
    claudeSessions(root, claudeHome).map((item) => item.sessionId),
    ["c", "a", "b"],
  );
});

test("codexSessions keeps rollouts whose recorded cwd is the project, and skips subagent rollouts", () => {
  const base = scratch();
  const root = path.join(base, "proj");
  const codexHome = path.join(base, "codex");
  fs.mkdirSync(root);
  const day = path.join(codexHome, "sessions", "2026", "10", "28");
  rollout(path.join(day, "rollout-1.jsonl"), { id: "cx1", cwd: root }, 2000);
  rollout(path.join(day, "rollout-2.jsonl"), { id: "cx2", cwd: path.join(base, "other") }, 2000);
  rollout(path.join(day, "rollout-3.jsonl"), { id: "cx3", cwd: root, source: { subagent: { parent: "cx1" } } }, 2000);
  rollout(path.join(day, "rollout-4.jsonl"), { id: "cx4", cwd: `${root}/../proj` }, 1000);
  rollout(path.join(codexHome, "sessions", "rollout-5.jsonl"), { id: "cx5", cwd: root, source: "cli" }, 3000);
  const found = codexSessions(root, codexHome);
  assert.deepEqual(
    found.map((item) => [item.kind, item.sessionId]),
    [
      [CODEX, "cx4"],
      [CODEX, "cx1"],
      [CODEX, "cx5"],
    ],
  );
  assert.deepEqual(
    codexSessions(root, codexHome, new Date(1500 * 1000)).map((item) => item.sessionId),
    ["cx1", "cx5"],
  );
});

test("codexSessions skips an unreadable or unrecognised file and an absent sessions directory", () => {
  const base = scratch();
  const root = path.join(base, "proj");
  const codexHome = path.join(base, "codex");
  fs.mkdirSync(root);
  assert.deepEqual(codexSessions(root, codexHome), []);
  const day = path.join(codexHome, "sessions", "d");
  stamped(path.join(day, "empty.jsonl"), "", 2000);
  stamped(path.join(day, "text.jsonl"), "not json\n", 2000);
  stamped(path.join(day, "array.jsonl"), "[1]\n", 2000);
  stamped(path.join(day, "bytes.jsonl"), Buffer.from([0xff, 0xfe, 0x0a]).toString("latin1"), 2000);
  stamped(
    path.join(day, "other-type.jsonl"),
    `${JSON.stringify({ type: "event", payload: { id: "x", cwd: root } })}\n`,
    2000,
  );
  rollout(path.join(day, "no-id.jsonl"), { cwd: root }, 2000);
  rollout(path.join(day, "empty-id.jsonl"), { id: "", cwd: root }, 2000);
  rollout(path.join(day, "no-cwd.jsonl"), { id: "n", cwd: "" }, 2000);
  rollout(path.join(day, "numeric-cwd.jsonl"), { id: "n", cwd: 5 }, 2000);
  fs.mkdirSync(path.join(day, "dir.jsonl"));
  rollout(path.join(day, "good.jsonl"), { id: "good", cwd: root }, 2000);
  assert.deepEqual(
    codexSessions(root, codexHome).map((item) => item.sessionId),
    ["good"],
  );
});

test("codexSessions reads only the first line, a long one included, and a recorded cwd with NUL is a ValueError", () => {
  const base = scratch();
  const root = path.join(base, "proj");
  const codexHome = path.join(base, "codex");
  fs.mkdirSync(root);
  const day = path.join(codexHome, "sessions", "d");
  rollout(path.join(day, "long.jsonl"), { id: "long", cwd: root, instructions: "x".repeat(200000) }, 2000);
  assert.deepEqual(
    codexSessions(root, codexHome).map((item) => item.sessionId),
    ["long"],
  );
  rollout(path.join(day, "nul.jsonl"), { id: "nul", cwd: "/a\u0000b" }, 2000);
  assert.throws(() => codexSessions(root, codexHome), { name: "ValueError", message: "embedded null byte" });
});

/**
 * A Claude transcript line that records a working directory.
 * @param {string} cwd
 */
function cwdLine(cwd) {
  return `${JSON.stringify({ type: "user", cwd })}\n`;
}

test("claudeSessions counts directories named by a path inside the root, confirmed by a recorded cwd", () => {
  const dir = scratch();
  const root = path.join(dir, "proj");
  fs.mkdirSync(root);
  const home = path.join(dir, "claude");
  const projects = path.join(home, "projects");
  const name = mungedProjectDir(root);
  const bookkeeping = `${JSON.stringify({ type: "file-history-snapshot" })}\n`;
  stamped(path.join(projects, name, "own.jsonl"), "{}\n", 100);
  stamped(path.join(projects, `${name}-sub`, "inside.jsonl"), bookkeeping + cwdLine(path.join(root, "sub")), 100);
  stamped(path.join(projects, `${name}-sub--hidden`, "deep.jsonl"), cwdLine(path.join(root, "sub", ".hidden")), 101);
  stamped(path.join(projects, `${name}-x`, "sibling.jsonl"), cwdLine(`${root}-x`), 100);
  stamped(path.join(projects, `${name}-nocwd`, "silent.jsonl"), bookkeeping, 100);
  stamped(path.join(projects, `${name}x`, "no-dash.jsonl"), cwdLine(root), 100);
  stamped(path.join(projects, `${name}-file`), "not a directory", 100);
  assert.deepEqual(
    claudeSessions(root, home)
      .map((item) => item.sessionId)
      .sort(),
    ["deep", "inside", "own"],
  );
});

test("codexSessions counts a rollout started inside the root, not a sibling's", () => {
  const dir = scratch();
  const root = path.join(dir, "proj");
  fs.mkdirSync(path.join(root, "sub"), { recursive: true });
  const home = path.join(dir, "codex");
  const day = path.join(home, "sessions", "2026", "10", "28");
  rollout(path.join(day, "rollout-a.jsonl"), { id: "codex-root", cwd: root, source: "cli" }, 100);
  rollout(path.join(day, "rollout-b.jsonl"), { id: "codex-sub", cwd: path.join(root, "sub"), source: "cli" }, 101);
  rollout(path.join(day, "rollout-c.jsonl"), { id: "codex-sibling", cwd: `${root}-x`, source: "cli" }, 102);
  assert.deepEqual(
    codexSessions(root, home).map((item) => item.sessionId),
    ["codex-root", "codex-sub"],
  );
});
