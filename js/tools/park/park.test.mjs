/**
 * node:test for `js/tools/park/park.mjs` — the twin of `meta/tests/test_park.py`: the note, the ergon, the
 * lease, the athlos and the derived states, the commands. The byte-level spec shared by both
 * implementations is the `tools/park-*` scenarios of `meta/conformance/scenarios`, run by
 * `runner.py --impl node --area tools`.
 */

import { after, test } from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { embeddedTreeRoot } from "../../akmon/_tree.mjs";
import { read } from "../../common/jsondata.mjs";
import {
  ParkError,
  acquireLease,
  activeUnit,
  checkBody,
  checkFields,
  digest,
  exportErgon,
  findClosedErgon,
  findErgon,
  branchUnit,
  carryCommands,
  formatAthlos,
  formatSummary,
  formatWorktrees,
  gitBranch,
  gitRevisions,
  gitUncommittedPaths,
  holderIdentified,
  holderLabel,
  holderSameAs,
  athlosFolder,
  athlosFileOf,
  moveAthlosFolder,
  ergonState,
  leaseIsStale,
  listErgons,
  listWorktrees,
  main,
  mergeSessions,
  nextLocalId,
  parkBody,
  parkFields,
  parseHeader,
  parseAthlosDoc,
  parseAthlosLine,
  parseLease,
  parseNote,
  parsePlan,
  parseWorktreeList,
  readLease,
  readAthlosDoc,
  readNote,
  readPendingSessions,
  releaseLease,
  removalCommands,
  rememberHolder,
  renderHeader,
  renderAthlosDoc,
  renderLease,
  renderNote,
  sharedPathWarnings,
  unitState,
  worktreeUnit,
  writeAthlosDoc,
  writeErgon,
} from "./park.mjs";
import { ergonRoot, gitCommonRoot } from "../../common/project_root.mjs";

/** @typedef {import("./park.mjs").ParkData} ParkData */
/** @typedef {import("./park.mjs").ParkFields} ParkFields */
/** @typedef {import("./park.mjs").ParkBody} ParkBody */
/** @typedef {import("./park.mjs").Holder} Holder */
/** @typedef {import("./park.mjs").LeaseContext} LeaseContext */

const TEXTS = /** @type {ParkData} */ (read(path.join(embeddedTreeRoot(), "tools", "park", "park.json")));

const NO_QUERY = { plan: "", task: "", state: "", closed: false };
const HOUR = 3600;
// The staleness threshold is park.json's, never restated here: a test that spells out 24 would pass
// while the shipped value said something else.
const STALE_HOURS = TEXTS.stale_after_hours;
const MACHINE = ["--machine", "m1"];
const CLAUDE = ["--harness", "claude", "--session-id", "s1", ...MACHINE];
const CODEX = ["--harness", "codex", "--session-id", "s2", ...MACHINE];

const PLAN_TEXT = `---
id: C1
name: demo
title: Demo plan
tasks: C1, C2
---
# Demo

## Athlos

- C1.1 · Build core · tasks C1 · paths src/a, docs · result: core built
- C1.2 · Write docs · after C1.1 · paths docs/x · result: docs done
- C1.3 · Extra · paths other · harness claude
`;

const FULL_FIELDS = parkFields({
  id: "C183",
  name: "park-helper",
  nextAction: "Twin it: JS | Python",
  plan: "A59",
  athlos: "C183.2",
  row: "C183",
  branch: "_aitna/C183-park-helper",
  revisions: ["abc123", "def456"],
  ownedPaths: ["tools/park/park.py", "meta/tests/test_park.py"],
  tasks: ["C183", "C184"],
  sessions: [
    { harness: "claude", sessionId: "s-1", machine: "laptop" },
    { harness: "codex", sessionId: "s-2", machine: "" },
  ],
  origin: "claude on laptop",
  readiness: "ready for a successor",
  written: "2026-07-01T10:20:30Z",
});
const FULL_BODY = parkBody({
  goal: "Build the park helper\nand its tests",
  decisions: ["D-C183-TWIN", "D-C183-NAME"],
  answers: ["owner: go"],
  checks: ["pytest: green"],
  unverified: ["the JS twin"],
  agents: ["none running"],
  purpose: [
    ["question", "is the note enough?"],
    ["reader_sees", "facts only"],
  ],
});

/**
 * A fresh temporary folder, registered for removal when this file's tests end: a suite that leaves
 * its scratch on disk charges the machine for every run.
 * @param {string} prefix
 * @returns {string}
 */
function tempDir(prefix) {
  const dir = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), prefix)));
  _tempDirs.push(dir);
  return dir;
}
/** @type {string[]} */
const _tempDirs = [];
after(() => {
  for (const dir of _tempDirs) {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});

// A directory that is no git repository and holds no project: the working directory the commands run in.
const NEUTRAL = tempDir("park-neutral-");

/**
 * Run `main` with the process streams captured, from the working directory `cwd`.
 * @param {string[]} argv
 * @param {string} [cwd]
 * @returns {{code: number, stdout: string, stderr: string}}
 */
function run(argv, cwd = NEUTRAL) {
  let stdout = "";
  let stderr = "";
  const out = process.stdout.write;
  const err = process.stderr.write;
  const before = process.cwd();
  process.chdir(cwd);
  process.stdout.write = /** @type {any} */ (
    (/** @type {string} */ text) =>
      ((stdout += text), true)
  );
  process.stderr.write = /** @type {any} */ (
    (/** @type {string} */ text) =>
      ((stderr += text), true)
  );
  try {
    return { code: main(argv), stdout, stderr };
  } finally {
    process.stdout.write = out;
    process.stderr.write = err;
    process.chdir(before);
  }
}

/**
 * A project root: `AGENTS.md` beside the dev layer's integration record (a real path, so the
 * root the tool resolves is the one the test names).
 * @returns {string}
 */
function project() {
  const root = tempDir("park-test-");
  fs.writeFileSync(path.join(root, "AGENTS.md"), "# agents\n");
  fs.mkdirSync(path.join(root, "_aitna"));
  fs.writeFileSync(path.join(root, "_aitna", ".akmon.toml"), "");
  return root;
}

/**
 * @param {string} root
 * @param {string} [name]
 * @returns {string}
 */
function ergonPath(root, name = "C183-park-helper") {
  return path.join(root, "_aitna", ".ergon", name);
}

/**
 * @param {string} file
 * @returns {string}
 */
function readUtf8(file) {
  return fs.readFileSync(file, "utf8");
}

/**
 * `park write` with the fixed goal and next action; `extra` flags follow.
 * @param {string} root
 * @param {string[]} [extra]
 * @param {{ergonId?: string, name?: string}} [who]
 * @returns {{code: number, stdout: string, stderr: string}}
 */
function write(root, extra = [], { ergonId = "C183", name = "park-helper" } = {}) {
  const argv = ["write", ergonId, "--name", name, "--goal", "Build the helper", "--next", "Twin it"];
  return run([...argv, ...extra, "--root", root]);
}

/**
 * Every file under `dir`, recursively.
 * @param {string} dir
 * @returns {string[]}
 */
function walk(dir) {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = path.join(dir, entry.name);
    return entry.isDirectory() ? walk(full) : [full];
  });
}

/**
 * @param {string} message
 * @returns {(error: unknown) => boolean}
 */
function parkError(message) {
  return (error) => error instanceof ParkError && error.message.includes(message);
}

/**
 * An ergon with a plan of three athlos (`PLAN_TEXT`), written through `write`.
 * @param {string} root
 * @returns {string} the ergon folder
 */
function ergonWithPlan(root) {
  const ergon = ergonPath(root, "C1-demo");
  fs.mkdirSync(ergon, { recursive: true });
  fs.writeFileSync(path.join(ergon, "PLAN.md"), PLAN_TEXT);
  return ergon;
}

/**
 * @param {string} root
 * @param {number} count
 * @returns {string}
 */
function ergonWithAnswers(root, count) {
  const body = parkBody({
    goal: "Goal line",
    answers: Array.from({ length: count }, (_value, number) => `answer ${String(number).padStart(2, "0")}`),
  });
  const fields = parkFields({ id: "C9", name: "long", nextAction: "Next" });
  return writeErgon(fields, body, root, TEXTS, root);
}

/**
 * @param {number} now
 * @param {string} [machine]
 * @returns {LeaseContext}
 */
function context(now, machine = "") {
  return { now, staleHours: TEXTS.stale_after_hours, machine };
}

/** @type {Holder} */
const CLAUDE_HOLDER = { harness: "claude", sessionId: "s1", machine: "m1", worktree: "/w1" };
/** @type {Holder} */
const CODEX_HOLDER = { harness: "codex", sessionId: "s2", machine: "m1", worktree: "/w2" };

/**
 * Whether git can be run here.
 * @returns {boolean}
 */
function gitAvailable() {
  try {
    execFileSync("git", ["--version"], { stdio: "ignore" });
    return true;
  } catch {
    return false;
  }
}

/**
 * @param {string} cwd
 * @param {string[]} args
 */
function git(cwd, args) {
  execFileSync("git", args, { cwd, stdio: "ignore" });
}

// --------------------------------------------------------------------------------------
// the header and the note
// --------------------------------------------------------------------------------------

test("header round-trips every field", () => {
  const text = renderHeader(FULL_FIELDS);
  assert.deepEqual(parseHeader(text, "PARK.md", TEXTS), FULL_FIELDS);
});

test("header round-trips with empty fields", () => {
  const fields = parkFields({ id: "_T3", name: "local-task", nextAction: "Continue" });
  const text = renderHeader(fields);
  assert.ok(text.includes("plan:\n") && text.includes("revisions:\n") && text.includes("tasks:\n"));
  assert.deepEqual(parseHeader(text, "PARK.md", TEXTS), fields);
});

test("header text is flat and ordered, with no state and no peers", () => {
  const lines = renderHeader(FULL_FIELDS).split("\n");
  assert.equal(lines[0], "---");
  assert.equal(lines[lines.length - 2], "---");
  const keys = lines
    .slice(1, -2)
    .filter((line) => !line.startsWith("  - "))
    .map((line) => line.split(":")[0]);
  assert.deepEqual(keys, [
    "id",
    "name",
    "plan",
    "athlos",
    "row",
    "branch",
    "revisions",
    "owned_paths",
    "tasks",
    "next",
    "sessions",
    "origin",
    "readiness",
    "written",
  ]);
  assert.ok(lines.includes("  - claude|s-1|laptop"));
  assert.ok(lines.includes("  - codex|s-2|"));
  assert.ok(lines.includes("written: 2026-07-01T10:20:30Z"));
});

test("a note written before the state and the peers were dropped still parses", () => {
  const old =
    "---\nstate: parked\nid: C1\nname: old\nplan:\nrow:\nbranch:\nrevisions:\nowned_paths:\nnext: x\n" +
    "sessions:\npeers:\norigin:\nreadiness:\n---\n\n# C1-old\n\n## Goal\n\nold goal\n";
  const { fields, body } = parseNote(old, "PARK.md", TEXTS);
  assert.deepEqual(fields, parkFields({ id: "C1", name: "old", nextAction: "x" }));
  assert.equal(body.goal, "old goal");
  assert.ok(!renderHeader(fields).includes("state:") && !renderHeader(fields).includes("peers:"));
});

test("a retired peers list with items is ignored too, and the ergon is listed", () => {
  // A retired list key takes its items with it: they are skipped, not read as the list above.
  const old =
    "---\nstate: parked\nid: C1\nname: old\nnext: x\nsessions:\n  - claude|s-1|laptop\n" +
    "peers:\n  - sibling session on B8\n---\n\n## Goal\n\ng\n";
  const fields = parseHeader(old, "PARK.md", TEXTS);
  assert.deepEqual(fields.sessions, [{ harness: "claude", sessionId: "s-1", machine: "laptop" }]);
  const root = project();
  const ergon = ergonPath(root, "C1-old");
  fs.mkdirSync(ergon, { recursive: true });
  fs.writeFileSync(path.join(ergon, "PARK.md"), old);
  const result = run(["list", ...MACHINE, "--root", root]);
  assert.equal(result.code, 0, result.stderr);
  assert.ok(result.stdout.startsWith("C1 | old | "), result.stdout);
});

test("note round-trips header and body", () => {
  const text = renderNote(FULL_FIELDS, FULL_BODY, TEXTS);
  const { fields, body } = parseNote(text, "PARK.md", TEXTS);
  assert.deepEqual(fields, FULL_FIELDS);
  assert.deepEqual(body, FULL_BODY);
});

test("note without purpose has no purpose section", () => {
  const text = renderNote(FULL_FIELDS, parkBody({ goal: "g" }), TEXTS);
  assert.ok(!text.includes("## Purpose"));
  assert.ok(text.includes("## Next action\n\nTwin it: JS | Python"));
});

/** @type {[Partial<ParkFields>, string][]} */
const REFUSED_FIELDS = [
  [{ id: "c1" }, "id c1 is not a task id"],
  [{ id: "C" }, "id C is not a task id"],
  [{ plan: "plan" }, "plan plan is not a task id"],
  [{ athlos: "C183" }, "athlos C183 is not an athlos id"],
  [{ athlos: "C183.x" }, "athlos C183.x is not an athlos id"],
  [{ name: "Park Helper" }, "name Park Helper is not kebab-case"],
  [{ name: "park--helper" }, "is not kebab-case"],
  [{ nextAction: "two\nlines" }, "next must be a single line"],
  [{ branch: "a\rb" }, "branch must be a single line"],
  [{ origin: " padded " }, "origin must be a single line"],
  [{ written: "a\nb" }, "written must be a single line"],
  [{ nextAction: "" }, "next must not be empty"],
  [{ revisions: ["a\nb"] }, "revision must be a single line"],
  [{ tasks: [""] }, "task must not be empty"],
  [{ sessions: [{ harness: "a|b", sessionId: "s", machine: "m" }] }, "is not harness|session_id|machine"],
];

for (const [change, message] of REFUSED_FIELDS) {
  test(`fields are refused at the boundary: ${message}`, () => {
    const fields = { ...FULL_FIELDS, ...change };
    assert.throws(() => checkFields(fields, TEXTS), parkError(message));
    assert.throws(() => renderNote(fields, FULL_BODY, TEXTS), ParkError);
  });
}

/** @type {[Partial<ParkBody>, string][]} */
const REFUSED_BODIES = [
  [{ goal: "" }, "goal must not be empty"],
  [{ goal: "a\n## Goal\nb" }, "goal has a line that starts with '## '"],
  [{ goal: "padded " }, "goal must not have surrounding whitespace"],
  [{ decisions: ["a\nb"] }, "decision must be a single line"],
  [{ purpose: [["Bad Key", "v"]] }, "purpose key Bad Key must be"],
  [{ purpose: [["key", ""]] }, "purpose key must not be empty"],
];

for (const [change, message] of REFUSED_BODIES) {
  test(`body is refused at the boundary: ${message}`, () => {
    const body = { ...FULL_BODY, ...change };
    assert.throws(() => checkBody(body, TEXTS), parkError(message));
  });
}

/** @type {[string, string][]} */
const MALFORMED_HEADERS = [
  ["no header\n", "no header between two '---' lines"],
  ["---\nid: C1\n", "no header between two '---' lines"],
  ["---\nid: C1\nid: C1\n---\n", "header key id is unknown or repeated"],
  ["---\nbogus: 1\n---\n", "header key bogus is unknown or repeated"],
  ["---\n  - orphan\n---\n", "is a list item with no list key above it"],
  ["---\nid: C1\n  - x\n---\n", "is a list item with no list key above it"],
  ["---\nrevisions: a\n---\n", "header key revisions takes a single value"],
  ["---\nSTATE parked\n---\n", "is neither 'key: value' nor an indented '- item'"],
  ["---\nstate: parked\nid: C1\nname: n\n---\n", "no value for next"],
  ["---\nid: c1\nname: n\nnext: x\n---\n", "id c1 is not a task id"],
  ["---\nid: C1\nname: n\nnext: x\nathlos: C1\n---\n", "athlos C1 is not an athlos id"],
];

for (const [text, message] of MALFORMED_HEADERS) {
  test(`malformed headers are refused: ${message}`, () => {
    assert.throws(() => parseHeader(text, "PARK.md", TEXTS), parkError(message));
  });
}

// --------------------------------------------------------------------------------------
// git: the branch and the revisions are read, never passed
// --------------------------------------------------------------------------------------

test("outside a repository there is no branch and no revision", () => {
  assert.equal(gitBranch(NEUTRAL), "");
  assert.deepEqual(gitRevisions(NEUTRAL), []);
  assert.equal(gitBranch(path.join(NEUTRAL, "missing")), "");
});

test("inside a repository the branch and the last revisions are what git says", { skip: !gitAvailable() }, () => {
  const here = path.dirname(fileURLToPath(import.meta.url));
  /**
   * @param {string[]} args
   * @returns {string}
   */
  const ask = (args) => {
    try {
      return execFileSync("git", args, { cwd: here, encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] }).trim();
    } catch {
      return "";
    }
  };
  assert.equal(gitBranch(here), ask(["rev-parse", "--abbrev-ref", "HEAD"]));
  assert.deepEqual(
    gitRevisions(here, 3),
    ask(["log", "-3", "--format=%h"])
      .split("\n")
      .filter((line) => line !== ""),
  );
});

// --------------------------------------------------------------------------------------
// write: the ergon, the resume prompt, no index
// --------------------------------------------------------------------------------------

test("write creates the ergon with both files and a note that says when it was written", () => {
  const root = project();
  const result = write(root, ["--plan", "A59", "--decision", "D-X"]);
  assert.equal(result.code, 0);
  assert.equal(result.stdout, "_aitna/.ergon/C183-park-helper\n");
  const ergon = ergonPath(root);
  const { fields, body } = parseNote(readUtf8(path.join(ergon, "PARK.md")), "PARK.md", TEXTS);
  assert.deepEqual([fields.id, fields.name, fields.plan], ["C183", "park-helper", "A59"]);
  assert.match(fields.written, /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$/);
  assert.equal(body.goal, "Build the helper");
  assert.deepEqual(body.decisions, ["D-X"]);
  assert.ok(fs.statSync(path.join(ergon, "RESUME.md")).isFile());
  assert.deepEqual(fs.readdirSync(ergon).sort(), ["PARK.md", "RESUME.md"]);
});

test("write reads the branch and the revisions from git in the working directory", () => {
  const root = project();
  const ergon = writeErgon(
    parkFields({ id: "C9", name: "git", nextAction: "x" }),
    parkBody({ goal: "g" }),
    root,
    TEXTS,
    NEUTRAL,
  );
  const { fields } = readNote(ergon, TEXTS);
  assert.deepEqual([fields.branch, fields.revisions], ["", []]);
  const here = path.dirname(fileURLToPath(import.meta.url));
  const inRepo = writeErgon(
    parkFields({ id: "C8", name: "git", nextAction: "x" }),
    parkBody({ goal: "g" }),
    root,
    TEXTS,
    here,
  );
  assert.equal(readNote(inRepo, TEXTS).fields.branch, gitBranch(here));
  assert.deepEqual(readNote(inRepo, TEXTS).fields.revisions, gitRevisions(here));
});

test("write flags fill the header fields the command line owns", () => {
  const root = project();
  const flags = [
    ["--plan", "A59"],
    ["--row", "C183"],
    ["--owned-path", "tools/park/park.py"],
    ["--origin", "claude"],
    ["--readiness", "ready"],
    ["--harness", "claude"],
    ["--session-id", "s1"],
    ["--machine", "laptop"],
    ["--check", "pytest"],
    ["--unverified", "twin"],
    ["--answer", "go"],
    ["--agent", "none"],
  ].flat();
  assert.equal(write(root, flags).code, 0);
  const { fields, body } = readNote(ergonPath(root), TEXTS);
  assert.deepEqual(
    { ...fields, written: "" },
    parkFields({
      id: "C183",
      name: "park-helper",
      nextAction: "Twin it",
      plan: "A59",
      row: "C183",
      ownedPaths: ["tools/park/park.py"],
      sessions: [{ harness: "claude", sessionId: "s1", machine: "laptop" }],
      origin: "claude",
      readiness: "ready",
    }),
  );
  assert.deepEqual([body.checks, body.unverified, body.answers, body.agents], [["pytest"], ["twin"], ["go"], ["none"]]);
});

test("the flags the old note header had are no longer there", () => {
  const root = project();
  for (const flag of ["--title", "--branch", "--revision", "--peer", "--role"]) {
    const result = write(root, [flag, "x"]);
    assert.equal(result.code, 2, flag);
    assert.equal(result.stderr, `park.mjs: error: unrecognized arguments: ${flag} x\n`);
  }
});

test("session flags without a harness are refused", () => {
  const root = project();
  for (const flags of [
    ["--session-id", "s1"],
    ["--machine", "m1"],
  ]) {
    const result = write(root, flags);
    assert.equal(result.code, 1);
    assert.equal(result.stderr, "error: --session-id and --machine need --harness\n");
  }
  assert.ok(!fs.existsSync(ergonPath(root)));
});

test("the resume prompt is harness-neutral and dateless", () => {
  const root = project();
  write(root, ["--decision", "D-X", "--plan", "A59"]);
  const resume = readUtf8(path.join(ergonPath(root), "RESUME.md"));
  assert.ok(resume.includes("`_aitna/.ergon/C183-park-helper/PARK.md`"));
  assert.ok(resume.includes("`akmon tool park/park unpark C183`"));
  assert.ok(resume.includes("Twin it") && resume.includes("- D-X"));
  assert.ok(resume.includes("stop is observed") && resume.includes("otherwise report a blocker"));
  assert.ok(resume.includes("(N15)"));
  assert.ok(!resume.includes(root));
  assert.ok(!resume.split("\n").some((line) => line.startsWith("/")));
  assert.doesNotMatch(resume, /\d{4}-\d{2}-\d{2}/);
});

test("write and unpark create no local index and no local folder (ADR 0028 D12)", () => {
  const root = project();
  write(root);
  run(["unpark", "C183", ...CLAUDE, "--root", root]);
  run(["close", "C183", "--root", root]);
  assert.ok(!fs.existsSync(path.join(root, "_aitna", ".local")));
  assert.deepEqual(
    fs
      .readdirSync(path.join(root, "_aitna"), { withFileTypes: true })
      .map((entry) => entry.name)
      .sort(),
    [".akmon.toml", ".ergon"],
  );
});

test("a dev-root pointer moves the ergon", () => {
  const root = tempDir("park-test-");
  fs.writeFileSync(path.join(root, "AGENTS.md"), "");
  fs.writeFileSync(path.join(root, ".aitna-root"), "tools/ai\n");
  assert.equal(write(root).code, 0);
  assert.ok(fs.statSync(path.join(root, "tools/ai/.ergon/C183-park-helper/PARK.md")).isFile());
  assert.ok(!fs.existsSync(path.join(root, "tools/ai/.local")));
  assert.ok(
    readUtf8(path.join(root, "tools/ai/.ergon/C183-park-helper/RESUME.md")).includes(
      "`tools/ai/.ergon/C183-park-helper/PARK.md`",
    ),
  );
});

test("a failure while landing the files leaves nothing behind", (t) => {
  const root = project();
  t.mock.method(fs, "renameSync", () => {
    throw new Error("disk says no");
  });
  assert.throws(() => write(root), /disk says no/);
  assert.ok(!fs.existsSync(ergonPath(root)));
  assert.deepEqual(
    walk(root).filter((file) => file.endsWith(".tmp")),
    [],
  );
});

test("a failure keeps an existing ergon and removes only the temp files", (t) => {
  const root = project();
  write(root);
  const ergon = ergonPath(root);
  /** @returns {Map<string, string>} */
  const snapshot = () => new Map(fs.readdirSync(ergon).map((name) => [name, readUtf8(path.join(ergon, name))]));
  const before = snapshot();
  t.mock.method(fs, "renameSync", () => {
    throw new Error("disk says no");
  });
  assert.throws(() => write(root, ["--decision", "D-NEW"]), /disk says no/);
  assert.deepEqual(snapshot(), before);
});

test("an ergon with the id and another name is refused, live or closed", () => {
  const root = project();
  write(root);
  const result = write(root, [], { name: "renamed" });
  assert.equal(result.code, 1);
  assert.equal(
    result.stderr,
    "error: ergon C183-park-helper already carries id C183; keep its name or retire it before writing renamed\n",
  );
  assert.ok(!fs.existsSync(ergonPath(root, "C183-renamed")));
  run(["close", "C183", "--root", root]);
  const closed = write(root, [], { name: "renamed" });
  assert.equal(closed.code, 1);
  assert.ok(closed.stderr.includes("ergon C183-park-helper already carries id C183"));
});

test("write refuses a bad id and a bad name before any file", () => {
  const root = project();
  const first = write(root, [], { ergonId: "c183" });
  const second = write(root, [], { name: "Bad_Name" });
  assert.equal(first.code, 1);
  assert.equal(second.code, 1);
  assert.ok(first.stderr.startsWith("error: id c183 is not a task id"));
  assert.ok(second.stderr.startsWith("error: name Bad_Name is not kebab-case"));
  assert.ok(!fs.existsSync(path.join(root, "_aitna", ".ergon")));
});

test("write refuses a newline in a scalar", () => {
  const root = project();
  const result = run(["write", "C1", "--name", "n", "--goal", "g", "--next", "a\nb", "--root", root]);
  assert.equal(result.code, 1);
  assert.equal(result.stderr, "error: next must be a single line with no surrounding whitespace\n");
});

test("local ids are accepted, and the next one is counted over the ergons, live and closed", () => {
  const root = project();
  assert.equal(nextLocalId(root), "_T1");
  assert.equal(write(root, [], { ergonId: "_T7", name: "scratch" }).code, 0);
  assert.ok(fs.statSync(ergonPath(root, "_T7-scratch")).isDirectory());
  assert.equal(nextLocalId(root), "_T8");
  run(["close", "_T7", "--root", root]);
  assert.equal(nextLocalId(root), "_T8");
  write(root, [], { ergonId: "C5", name: "typed" });
  write(root, [], { ergonId: "_T2", name: "low" });
  assert.equal(nextLocalId(root), "_T8");
});

test("the next local id skips every number the legacy index holds, and the index is left alone", () => {
  const root = project();
  const local = path.join(root, "_aitna", ".local");
  fs.mkdirSync(local, { recursive: true });
  const legacy = path.join(local, "TASKS.md");
  fs.writeFileSync(
    legacy,
    "# TASKS\n\n- _T6 \u00b7 plan: a \u00b7 active\n- C9 \u00b7 not local\n- _T12 \u00b7 b\n  - _T40 \u00b7 nested\n_T30 \u00b7 no bullet\n",
  );
  const before = fs.readFileSync(legacy);
  fs.mkdirSync(ergonPath(root, "_T2-a"), { recursive: true });
  assert.equal(nextLocalId(root), "_T13");
  fs.mkdirSync(ergonPath(root, ".closed/_T20-gone"), { recursive: true });
  assert.equal(nextLocalId(root), "_T21");
  assert.deepEqual(fs.readFileSync(legacy), before);
});

test("the local-id command prints the next free id on one line and writes nothing", () => {
  const root = project();
  const first = run(["local-id", "--root", root]);
  assert.deepEqual([first.code, first.stdout, first.stderr], [0, "_T1\n", ""]);
  assert.ok(!fs.existsSync(path.join(root, "_aitna", ".ergon")));
  fs.mkdirSync(ergonPath(root, "_T2-a"), { recursive: true });
  fs.mkdirSync(ergonPath(root, ".closed/_T5-gone"), { recursive: true });
  assert.equal(run(["local-id", "--root", root]).stdout, "_T6\n");
  assert.equal(run(["local-id", "--project-root", root, ...MACHINE]).stdout, "_T6\n");
});

// --------------------------------------------------------------------------------------
// unpark and digest
// --------------------------------------------------------------------------------------

test("unpark takes the lease and prints resume then digest", () => {
  const root = project();
  write(root, ["--decision", "D-X", "--answer", "owner: go", "--plan", "A59"]);
  const result = run(["unpark", "C183", ...CLAUDE, "--root", root]);
  assert.equal(result.code, 0);
  const resume = readUtf8(path.join(ergonPath(root), "RESUME.md"));
  assert.ok(result.stdout.startsWith(`${resume.replace(/\n+$/, "")}\n\npark C183-park-helper · active\n`));
  assert.ok(result.stdout.endsWith("Owner answers:\n- owner: go\n"));
  const lease = readLease(ergonPath(root), TEXTS);
  assert.ok(lease !== null && holderSameAs(lease.holder, { ...CLAUDE_HOLDER, worktree: "" }));
  assert.equal(lease.holder.worktree, NEUTRAL);
  // the note itself carries no state: it is what write left
  assert.equal(readNote(ergonPath(root), TEXTS).fields.plan, "A59");
});

test("unpark is refused while another session holds the ergon, and renewed for the same one", () => {
  const root = project();
  write(root);
  assert.equal(run(["unpark", "C183", ...CLAUDE, "--root", root]).code, 0);
  assert.equal(run(["unpark", "C183", ...CLAUDE, "--root", root]).code, 0);
  const refused = run(["unpark", "C183", ...CODEX, "--root", root]);
  assert.equal(refused.code, 1);
  assert.ok(refused.stderr.startsWith("error: C183-park-helper is held by claude s1 m1 "));
  assert.ok(refused.stderr.includes("a stale lease is taken over only on the owner's word (--takeover)"));
});

test("unpark names the candidates when no ergon matches", () => {
  const root = project();
  write(root);
  const result = run(["unpark", "C999", "--root", root]);
  assert.equal(result.code, 1);
  assert.equal(result.stderr, "error: no ergon with id C999 under _aitna/.ergon; ergons: C183-park-helper\n");
});

test("unpark with no ergons at all says none", () => {
  const root = project();
  const result = run(["unpark", "C1", "--root", root]);
  assert.equal(result.code, 1);
  assert.equal(result.stderr, "error: no ergon with id C1 under _aitna/.ergon; ergons: none\n");
});

test("unpark names the ergons when several carry the id", () => {
  const root = project();
  for (const name of ["C5-a", "C5-b", "C50-c"]) {
    fs.mkdirSync(ergonPath(root, name), { recursive: true });
  }
  const result = run(["unpark", "C5", "--root", root]);
  assert.equal(result.code, 1);
  assert.equal(result.stderr, "error: several ergons carry id C5 under _aitna/.ergon: C5-a, C5-b\n");
});

test("a refused unpark leaves no lease behind: the checks come before the lease", () => {
  const root = project();
  const bare = ergonPath(root, "C5-a");
  fs.mkdirSync(bare, { recursive: true });
  const noResume = run(["unpark", "C5", ...CLAUDE, "--root", root]);
  assert.equal(noResume.code, 1);
  assert.equal(noResume.stderr, "error: ergon C5-a has no RESUME.md; write it again to regenerate it\n");
  assert.equal(readLease(bare, TEXTS), null);
  assert.ok(!fs.existsSync(path.join(bare, "HOLDER")));
  fs.writeFileSync(path.join(bare, "RESUME.md"), "# Resume C5-a\n");
  const noNote = run(["unpark", "C5", ...CLAUDE, "--root", root]);
  assert.equal(noNote.code, 1);
  assert.equal(noNote.stderr, "error: ergon C5-a was never parked: it has no PARK.md\n");
  assert.ok(!fs.existsSync(path.join(bare, "HOLDER")));
  fs.writeFileSync(path.join(bare, "PARK.md"), "no header\n");
  assert.equal(run(["unpark", "C5", ...CLAUDE, "--root", root]).code, 1); // a note that does not parse
  assert.ok(!fs.existsSync(path.join(bare, "HOLDER")));
});

test("the digest of an unpark reads the unit as active, because the lease is held by then", () => {
  const root = project();
  write(root);
  const result = run(["unpark", "C183", ...CLAUDE, "--root", root]);
  assert.equal(result.code, 0);
  assert.ok(result.stdout.includes("\n\npark C183-park-helper · active\n"));
});

test("a digest within the cap is whole and has no overflow line", () => {
  const root = project();
  const ergon = ergonWithAnswers(root, 2);
  assert.equal(
    digest(ergon, 3000, root, TEXTS),
    "park C9-long · parked\nGoal: Goal line\nNext action: Next\nOpen decisions: none\n" +
      "Owner answers:\n- answer 00\n- answer 01",
  );
});

test("a digest judges a copied lease on the machine it is given", () => {
  const root = project();
  const ergon = ergonWithAnswers(root, 0);
  acquireLease(ergon, CLAUDE_HOLDER, TEXTS, context(Date.now() / 1000));
  assert.ok(digest(ergon, 3000, root, TEXTS, "m1").startsWith("park C9-long · active\n"));
  assert.ok(digest(ergon, 3000, root, TEXTS, "m1-copy").startsWith("park C9-long · parked\n"));
});

test("a digest names the state of the ergon and the athlos of the note", () => {
  const root = project();
  const ergon = ergonWithAnswers(root, 0);
  acquireLease(ergon, CLAUDE_HOLDER, TEXTS, context(Date.now() / 1000));
  assert.ok(digest(ergon, 3000, root, TEXTS).startsWith("park C9-long · active\n"));
  const withAthlos = parkFields({ id: "C9", name: "long", nextAction: "Next", plan: "A59", athlos: "C9.1" });
  const text = renderNote(withAthlos, parkBody({ goal: "g" }), TEXTS);
  fs.writeFileSync(path.join(ergon, "PARK.md"), text);
  assert.deepEqual(digest(ergon, 3000, root, TEXTS).split("\n").slice(0, 3), [
    "park C9-long · active",
    "plan: A59",
    "athlos: C9.1",
  ]);
});

test("a digest is cut at a whole line and names the overflow", () => {
  const root = project();
  const ergon = ergonWithAnswers(root, 10);
  const full = digest(ergon, 3000, root, TEXTS).split("\n");
  // keep the title, goal, next, decisions-none and the answers heading, plus 2 answers
  const kept = full.slice(0, 7);
  const cap = kept.reduce((sum, line) => sum + line.length + 1, 0);
  const lines = digest(ergon, cap, root, TEXTS).split("\n");
  assert.deepEqual(lines.slice(0, -1), kept);
  assert.equal(lines[lines.length - 1], "… 8 more lines in _aitna/.ergon/C9-long/PARK.md");
  // one character short of the next line: it is dropped whole, never cut; with room for it, it is kept
  const short = digest(ergon, cap + "- answer 02".length, root, TEXTS).split("\n");
  assert.ok(short[short.length - 1].startsWith("… 8 more"));
  const room = digest(ergon, cap + "- answer 02".length + 1, root, TEXTS).split("\n");
  assert.ok(room[room.length - 1].startsWith("… 7 more"));
});

test("a digest with a tiny cap is only the overflow line", () => {
  const root = project();
  const ergon = ergonWithAnswers(root, 1);
  assert.equal(digest(ergon, 0, root, TEXTS), "… 6 more lines in _aitna/.ergon/C9-long/PARK.md");
});

test("a digest without a root names the note by ergon", () => {
  const root = project();
  const ergon = ergonWithAnswers(root, 1);
  assert.ok(digest(ergon, 0, null, TEXTS).endsWith("lines in C9-long/PARK.md"));
});

test("a digest reads its own texts when called alone", () => {
  const root = project();
  const ergon = ergonWithAnswers(root, 1);
  assert.ok(digest(ergon, 3000).startsWith("park C9-long · parked"));
});

test("a digest counts code points, not UTF-16 units", () => {
  const root = project();
  const fields = parkFields({ id: "C9", name: "long", nextAction: "Next" });
  const ergon = writeErgon(fields, parkBody({ goal: "𝒳𝒴" }), root, TEXTS, root);
  // "Goal: 𝒳𝒴" is 8 code points (10 UTF-16 units); the title line is 21 + 1, then this line + 1
  const title = "park C9-long · parked";
  const cap = title.length + 1 + "Goal: 𝒳𝒴".length + 1;
  const lines = digest(ergon, cap, root, TEXTS).split("\n");
  assert.deepEqual(lines.slice(0, 2), [title, "Goal: 𝒳𝒴"]);
});

test("a digest indents the continuation of a multiline goal", () => {
  const root = project();
  const fields = parkFields({ id: "C9", name: "long", nextAction: "Next", plan: "A59", readiness: "ready" });
  const ergon = writeErgon(fields, parkBody({ goal: "one\ntwo" }), root, TEXTS, root);
  assert.deepEqual(digest(ergon, 3000, root, TEXTS).split("\n").slice(0, 6), [
    "park C9-long · parked",
    "plan: A59",
    "readiness: ready",
    "Goal: one",
    "  two",
    "Next action: Next",
  ]);
});

test("the digest command prints the digest and refuses a negative cap", () => {
  const root = project();
  write(root);
  const capped = run(["digest", "C183", "--cap", "40", "--root", root]);
  assert.equal(capped.code, 0);
  assert.equal(
    capped.stdout,
    "park C183-park-helper · parked\n… 4 more lines in _aitna/.ergon/C183-park-helper/PARK.md\n",
  );
  const negative = run(["digest", "C183", "--cap", "-1", "--root", root]);
  assert.equal(negative.code, 1);
  assert.equal(negative.stderr, "error: --cap must be a whole number of at least 0, got -1\n");
});

test("the digest command's default cap is 3000", () => {
  const root = project();
  const ergon = ergonWithAnswers(root, 400);
  const lines = run(["digest", "C9", "--root", root]).stdout.split("\n").slice(0, -1);
  const last = lines[lines.length - 1];
  assert.ok(last.startsWith("… ") && last.includes("more lines in _aitna/.ergon/C9-long/PARK.md"));
  assert.ok(lines.slice(0, -1).reduce((sum, line) => sum + line.length + 1, 0) <= 3000);
  assert.ok(fs.statSync(ergon).isDirectory());
});

// --------------------------------------------------------------------------------------
// the lease: HOLDER, created exclusively, judged stale on read
// --------------------------------------------------------------------------------------

test("a lease renders flat and round-trips, its time to the second", () => {
  const lease = { holder: CLAUDE_HOLDER, written: Date.UTC(2026, 6, 1, 10, 20, 30) / 1000 };
  const text = renderLease(lease);
  assert.equal(
    text,
    "---\nharness: claude\nsession: s1\nmachine: m1\nworktree: /w1\nwritten: 2026-07-01T10:20:30Z\n---\n",
  );
  assert.deepEqual(parseLease(text, "HOLDER", TEXTS), lease);
  const bare = renderLease({ holder: { harness: "", sessionId: "", machine: "", worktree: "" }, written: 0 });
  assert.ok(bare.includes("harness:\n") && bare.includes("worktree:\n"));
});

test("a malformed lease is refused, and so is a stamp that is not one", () => {
  assert.throws(() => parseLease("not a header\n", "HOLDER", TEXTS), parkError("no header between two '---' lines"));
  assert.throws(() => parseLease("---\nbogus: x\n---\n", "HOLDER", TEXTS), parkError("header key bogus is unknown"));
  assert.throws(
    () => parseLease("---\n  - x\n---\n", "HOLDER", TEXTS),
    parkError("is a list item with no list key above it"),
  );
  for (const stamp of [
    "",
    "garbage",
    "2026-02-30T00:00:00Z",
    "2026-01-01T24:00:00Z",
    "2026-01-01T00:00:60Z",
    "2026-01-01 00:00:00",
  ]) {
    assert.throws(
      () => parseLease(`---\nwritten: ${stamp}\n---\n`, "HOLDER", TEXTS),
      parkError("is not a UTC stamp"),
      stamp,
    ); // a corrupt stamp is refused, never read as the epoch: 0 would call a live holder's unit free
  }
  // `strptime` takes the unpadded forms
  assert.equal(
    parseLease("---\nwritten: 2026-1-5T1:2:3Z\n---\n", "HOLDER", TEXTS).written,
    Date.UTC(2026, 0, 5, 1, 2, 3) / 1000,
  );
});

test("holders compare by harness, session and machine, and read as one line", () => {
  assert.ok(holderSameAs(CLAUDE_HOLDER, { ...CLAUDE_HOLDER, worktree: "/elsewhere" }));
  assert.ok(!holderSameAs(CLAUDE_HOLDER, CODEX_HOLDER));
  assert.equal(holderLabel(CLAUDE_HOLDER), "claude s1 m1 /w1");
  assert.equal(holderLabel({ harness: "", sessionId: "", machine: "", worktree: "" }), "? ? ?");
});

test("a lease is stale past the threshold, or at once on another machine", () => {
  const now = 1_000_000;
  const fresh = { holder: CLAUDE_HOLDER, written: now - (STALE_HOURS - 1) * HOUR };
  const exact = { holder: CLAUDE_HOLDER, written: now - STALE_HOURS * HOUR };
  const old = { holder: CLAUDE_HOLDER, written: now - (STALE_HOURS + 1) * HOUR };
  assert.equal(leaseIsStale(fresh, context(now, "m1")), false);
  assert.equal(leaseIsStale(exact, context(now, "m1")), false); // exactly the threshold is not past it
  assert.equal(leaseIsStale(old, context(now, "m1")), true);
  assert.equal(leaseIsStale(fresh, context(now, "elsewhere")), true);
  assert.equal(leaseIsStale(fresh, context(now, "")), false); // no machine named: nothing to compare
  assert.equal(
    leaseIsStale({ holder: { ...CLAUDE_HOLDER, machine: "" }, written: now }, context(now, "elsewhere")),
    false,
  );
  assert.equal(leaseIsStale({ holder: CLAUDE_HOLDER, written: now + HOUR }, context(now, "m1")), false); // a clock behind the file
});

test("a free unit is taken, created exclusively", (t) => {
  const root = project();
  const unit = ergonPath(root, "C1-a");
  /** @type {unknown[]} */
  const flags = [];
  const open = fs.openSync;
  t.mock.method(
    fs,
    "openSync",
    (/** @type {fs.PathLike} */ file, /** @type {string} */ flag, /** @type {number} */ mode) => {
      flags.push(flag);
      return open(file, flag, mode);
    },
  );
  const lease = acquireLease(unit, CLAUDE_HOLDER, TEXTS, context(1_000_000));
  assert.deepEqual(flags, ["wx"]);
  assert.deepEqual(readLease(unit, TEXTS), lease);
  assert.equal(fs.statSync(path.join(unit, "HOLDER")).mode & 0o777, 0o644 & ~process.umask());
});

test("a lease file that appears between the read and the create is never overwritten", () => {
  const root = project();
  const unit = ergonPath(root, "C1-a");
  fs.mkdirSync(unit, { recursive: true });
  // `acquireLease` found no lease; the file now exists, and the exclusive create refuses it
  const text = renderLease({ holder: CODEX_HOLDER, written: 1_000_000 });
  fs.writeFileSync(path.join(unit, "HOLDER"), text);
  assert.throws(() => fs.openSync(path.join(unit, "HOLDER"), "wx"), { code: "EEXIST" });
  assert.equal(readUtf8(path.join(unit, "HOLDER")), text);
});

test("the same session renews its lease, another is refused with the holder named", () => {
  const root = project();
  const unit = ergonPath(root, "C1-a");
  acquireLease(unit, CLAUDE_HOLDER, TEXTS, context(1_000_000));
  const renewed = acquireLease(unit, { ...CLAUDE_HOLDER, worktree: "/w9" }, TEXTS, context(1_000_100));
  assert.equal(renewed.written, 1_000_100);
  assert.equal(readLease(unit, TEXTS)?.written, 1_000_100);
  assert.throws(
    () => acquireLease(unit, CODEX_HOLDER, TEXTS, context(1_000_200)),
    parkError("C1-a is held by claude s1 m1 /w9; a stale lease is taken over only on the owner's word (--takeover)"),
  );
});

test("a stale lease is refused as stale, and taken over only on the owner's word", () => {
  const root = project();
  const unit = ergonPath(root, "C1-a");
  acquireLease(unit, CLAUDE_HOLDER, TEXTS, context(1_000_000));
  const later = context(1_000_000 + 25 * HOUR, "m1");
  assert.throws(
    () => acquireLease(unit, CODEX_HOLDER, TEXTS, later),
    parkError(
      "C1-a is held by claude s1 m1 /w1, whose lease is stale; take it over only on the owner's word (--takeover)",
    ),
  );
  assert.deepEqual(readLease(unit, TEXTS)?.holder, CLAUDE_HOLDER);
  const taken = acquireLease(unit, CODEX_HOLDER, TEXTS, later, { takeover: true });
  assert.deepEqual(readLease(unit, TEXTS), taken);
  assert.deepEqual(readLease(unit, TEXTS)?.holder, CODEX_HOLDER);
});

test("another machine's lease is stale at once, and a takeover leaves a trace in the note", () => {
  const root = project();
  write(root, ["--harness", "claude", "--session-id", "s1", "--machine", "laptop"]);
  const ergon = ergonPath(root);
  const away = { harness: "claude", sessionId: "s1", machine: "laptop", worktree: "/w1" };
  acquireLease(ergon, away, TEXTS, context(Date.now() / 1000, "laptop"));
  const here = context(Date.now() / 1000, "desktop");
  const mine = { harness: "codex", sessionId: "s2", machine: "desktop", worktree: "/w2" };
  assert.equal(unitState(ergon, TEXTS, here), "parked");
  assert.throws(() => acquireLease(ergon, mine, TEXTS, here), parkError("whose lease is stale"));
  acquireLease(ergon, mine, TEXTS, here, { takeover: true });
  const { fields } = readNote(ergon, TEXTS);
  assert.deepEqual(fields.sessions, [{ harness: "claude", sessionId: "s1", machine: "laptop" }]);
  // the same holder replaced twice is remembered once
  acquireLease(ergon, away, TEXTS, context(Date.now() / 1000, "laptop"), { takeover: true });
  acquireLease(ergon, mine, TEXTS, here, { takeover: true });
  assert.equal(readNote(ergon, TEXTS).fields.sessions.length, 2);
});

/**
 * A unit folder holding a rendered note, as `write` leaves it (header, a blank line, the body).
 * @param {string} root
 * @returns {{unit: string, note: string}}
 */
function noteUnit(root) {
  const unit = ergonPath(root, "C9-long");
  fs.mkdirSync(unit, { recursive: true });
  const note = renderNote(parkFields({ id: "C9", name: "long", nextAction: "Next" }), parkBody({ goal: "g" }), TEXTS);
  fs.writeFileSync(path.join(unit, "PARK.md"), note);
  return { unit, note };
}

test("a takeover leaves the note's body byte for byte as it was, however many holders it replaces", () => {
  const { unit, note } = noteUnit(project());
  /** @param {string} text */
  const bodyOf = (text) => text.split("\n---\n").slice(1).join("\n---\n");
  acquireLease(unit, { harness: "claude", sessionId: "s1", machine: "m1", worktree: "/w" }, TEXTS, context(1_000_000));
  for (const session of ["s2", "s3", "s4"]) {
    const holder = { harness: "claude", sessionId: session, machine: "m1", worktree: "/w" };
    acquireLease(unit, holder, TEXTS, context(1_000_000), { takeover: true });
  }
  assert.equal(bodyOf(readUtf8(path.join(unit, "PARK.md"))), bodyOf(note));
  assert.equal(readNote(unit, TEXTS).fields.sessions.length, 3);
});

test("a holder with no harness or no session is not recorded among the sessions", () => {
  for (const holder of [
    { harness: "", sessionId: "s1", machine: "m1", worktree: "/w" },
    { harness: "claude", sessionId: "", machine: "m1", worktree: "/w" },
  ]) {
    const { unit, note } = noteUnit(project());
    acquireLease(unit, holder, TEXTS, context(1_000_000));
    acquireLease(unit, CODEX_HOLDER, TEXTS, context(1_000_000), { takeover: true });
    assert.equal(readUtf8(path.join(unit, "PARK.md")), note);
    assert.deepEqual(readNote(unit, TEXTS).fields.sessions, []);
    rememberHolder(unit, holder, TEXTS);
    assert.equal(readUtf8(path.join(unit, "PARK.md")), note);
  }
});

test("a takeover of a unit with no note keeps the replaced holder in a pending record", () => {
  const root = project();
  const unit = ergonPath(root, "C1-a");
  acquireLease(unit, CLAUDE_HOLDER, TEXTS, context(1_000_000));
  acquireLease(unit, CODEX_HOLDER, TEXTS, context(1_000_100), { takeover: true });
  assert.deepEqual(fs.readdirSync(unit).sort(), ["HOLDER", "SESSIONS"]);
  assert.deepEqual(readPendingSessions(unit, TEXTS), [{ harness: "claude", sessionId: "s1", machine: "m1" }]);
  acquireLease(unit, CLAUDE_HOLDER, TEXTS, context(1_000_200), { takeover: true });
  assert.deepEqual(readPendingSessions(unit, TEXTS), [
    { harness: "claude", sessionId: "s1", machine: "m1" },
    { harness: "codex", sessionId: "s2", machine: "m1" },
  ]);
});

test("a takeover of an athlos keeps the replaced holder in the athlos file", () => {
  const unit = ergonPath(project(), "C1-a");
  fs.mkdirSync(unit, { recursive: true });
  const header = parkFields({ id: "C1", name: "a", nextAction: "r", athlos: "C1.1" });
  fs.writeFileSync(
    path.join(unit, "ATHLOS.md"),
    renderAthlosDoc({ header, steps: [["first", false]], done: false }, TEXTS),
  );
  acquireLease(unit, CLAUDE_HOLDER, TEXTS, context(1_000_000));
  acquireLease(unit, CODEX_HOLDER, TEXTS, context(1_000_100), { takeover: true });
  const kept = parseAthlosDoc(readUtf8(path.join(unit, "ATHLOS.md")), "ATHLOS.md", TEXTS);
  assert.deepEqual(kept.header.sessions, [{ harness: "claude", sessionId: "s1", machine: "m1" }]);
  assert.deepEqual(kept.steps, [["first", false]]);
  assert.deepEqual(fs.readdirSync(unit).sort(), ["ATHLOS.md", "HOLDER"]);
});

test("a takeover stops before the lease changes when the note does not parse", () => {
  const unit = ergonPath(project(), "C1-a");
  fs.mkdirSync(unit, { recursive: true });
  fs.writeFileSync(path.join(unit, "PARK.md"), "not a note\n");
  acquireLease(unit, CLAUDE_HOLDER, TEXTS, context(1_000_000));
  const before = readUtf8(path.join(unit, "HOLDER"));
  assert.throws(
    () => acquireLease(unit, CODEX_HOLDER, TEXTS, context(1_000_100), { takeover: true }),
    parkError("no header between two '---' lines"),
  );
  assert.equal(readUtf8(path.join(unit, "HOLDER")), before);
  assert.equal(readUtf8(path.join(unit, "PARK.md")), "not a note\n");
});

test("a takeover and a renewal leave no temporary file behind", () => {
  const { unit } = noteUnit(project());
  acquireLease(unit, CLAUDE_HOLDER, TEXTS, context(1_000_000));
  acquireLease(unit, CODEX_HOLDER, TEXTS, context(1_000_100), { takeover: true });
  acquireLease(unit, CODEX_HOLDER, TEXTS, context(1_000_200));
  assert.deepEqual(fs.readdirSync(unit).sort(), ["HOLDER", "PARK.md"]);
});

test("two anonymous holders are not the same session", () => {
  const anonymous = { harness: "", sessionId: "", machine: "m1", worktree: "/w" };
  assert.equal(holderIdentified(anonymous), false);
  assert.equal(holderSameAs(anonymous, anonymous), false);
  assert.equal(holderSameAs({ ...anonymous, harness: "claude" }, { ...anonymous, harness: "claude" }), false);
  assert.equal(holderSameAs(CLAUDE_HOLDER, { ...CLAUDE_HOLDER, worktree: "/elsewhere" }), true);
  const unit = ergonPath(project(), "C1-a");
  acquireLease(unit, anonymous, TEXTS, context(1_000_000));
  assert.throws(() => acquireLease(unit, anonymous, TEXTS, context(1_000_000)), parkError("is held by ? ? m1 /w"));
});

test("a second anonymous hold through the command line is refused", () => {
  const root = project();
  write(root);
  assert.equal(run(["hold", "C183", ...MACHINE, "--root", root]).code, 0);
  const second = run(["hold", "C183", ...MACHINE, "--root", root]);
  assert.equal(second.code, 1);
  assert.ok(second.stderr.includes("C183-park-helper is held by ? ? m1"));
});

test("sessions merge in order, each once", () => {
  const one = { harness: "claude", sessionId: "s1", machine: "m1" };
  const two = { harness: "codex", sessionId: "s2", machine: "m1" };
  assert.deepEqual(mergeSessions([one], [two, one], []), [one, two]);
});

/**
 * Give a unit a lease of claude s1 that is stale (written long ago) and names `worktree`.
 * @param {string} unit
 * @param {string} [worktree]
 */
function staleLease(unit, worktree = "/work/tree") {
  fs.writeFileSync(
    path.join(unit, "HOLDER"),
    `---\nharness: claude\nsession: s1\nmachine: m1\nworktree: ${worktree}\nwritten: 2000-01-01T00:00:00Z\n---\n`,
  );
}

/**
 * A git repository with two commits, outside any project.
 * @returns {string}
 */
function repoWithCommits() {
  const repo = tempDir("park-repo-");
  git(repo, ["init", "-b", "main"]);
  for (const name of ["one", "two"]) {
    fs.writeFileSync(path.join(repo, `${name}.txt`), name);
    git(repo, ["add", `${name}.txt`]);
    git(repo, [
      "-c",
      "user.email=t@example.com",
      "-c",
      "user.name=t",
      "-c",
      "commit.gpgsign=false",
      "commit",
      "-m",
      name,
    ]);
  }
  return repo;
}

test(
  "git_uncommitted_paths reads tracked and untracked paths, and null when unreadable",
  { skip: !gitAvailable() },
  () => {
    const repo = repoWithCommits();
    assert.deepEqual(gitUncommittedPaths(repo), []);
    fs.writeFileSync(path.join(repo, "one.txt"), "changed");
    fs.writeFileSync(path.join(repo, "new.txt"), "new");
    assert.deepEqual(gitUncommittedPaths(repo), ["one.txt", "new.txt"]); // tracked changes first, untracked after
    assert.equal(gitUncommittedPaths(""), null);
    assert.equal(gitUncommittedPaths(path.join(NEUTRAL, "gone")), null);
    assert.equal(gitUncommittedPaths(NEUTRAL), null);
  },
);

test("a takeover names the replaced holder's uncommitted paths before anything else", { skip: !gitAvailable() }, () => {
  const root = project();
  write(root);
  const repo = repoWithCommits();
  fs.writeFileSync(path.join(repo, "scratch.txt"), "x");
  fs.writeFileSync(path.join(repo, "one.txt"), "changed");
  staleLease(ergonPath(root), repo);
  const taken = run(["hold", "C183", ...CODEX, "--takeover", "--root", root]);
  assert.equal(taken.code, 0);
  assert.deepEqual(taken.stdout.split("\n"), [
    `claude s1 m1 ${repo} left uncommitted paths: one.txt, scratch.txt`,
    `C183-park-helper: codex s2 m1 ${NEUTRAL}`,
    "",
  ]);
});

test(
  "a takeover of a clean worktree names no path, and of an unreadable one says so",
  { skip: !gitAvailable() },
  () => {
    const root = project();
    write(root);
    const repo = repoWithCommits();
    staleLease(ergonPath(root), repo);
    assert.equal(
      run(["hold", "C183", ...CODEX, "--takeover", "--root", root]).stdout,
      `C183-park-helper: codex s2 m1 ${NEUTRAL}\n`,
    );
    const gone = path.join(NEUTRAL, "gone");
    staleLease(ergonPath(root), gone);
    assert.equal(
      run(["hold", "C183", ...CODEX, "--takeover", "--root", root]).stdout,
      `the uncommitted paths of claude s1 m1 ${gone} could not be read\nC183-park-helper: codex s2 m1 ${NEUTRAL}\n`,
    );
  },
);

test("a takeover of a free unit or of one's own lease names nothing", () => {
  const root = project();
  write(root);
  for (let round = 0; round < 2; round += 1) {
    const taken = run(["hold", "C183", ...CODEX, "--takeover", "--root", root]);
    assert.equal(taken.stdout, `C183-park-helper: codex s2 m1 ${NEUTRAL}\n`);
  }
});

test("a released lease frees the unit; the note stays", () => {
  const root = project();
  write(root);
  const ergon = ergonPath(root);
  acquireLease(ergon, CLAUDE_HOLDER, TEXTS, context(1_000_000));
  releaseLease(ergon);
  assert.equal(readLease(ergon, TEXTS), null);
  assert.ok(fs.existsSync(path.join(ergon, "PARK.md")));
  releaseLease(ergon); // a missing lease is no error
});

test("the hold and release commands take and free a unit", () => {
  const root = project();
  write(root);
  const held = run(["hold", "C183", ...CLAUDE, "--root", root]);
  assert.equal(held.code, 0);
  assert.equal(held.stdout, `C183-park-helper: claude s1 m1 ${NEUTRAL}\n`);
  const refused = run(["hold", "C183", ...CODEX, "--root", root]);
  assert.equal(refused.code, 1);
  assert.ok(refused.stderr.includes("C183-park-helper is held by claude s1 m1"));
  assert.equal(run(["release", "C183", "--root", root]).stdout, "C183-park-helper\n");
  assert.equal(run(["release", "C183", "--root", root]).stderr, "error: C183-park-helper has no holder file\n");
  assert.equal(run(["hold", "C183", ...CODEX, "--root", root]).code, 0);
});

test("hold --takeover replaces a holder of this machine too, on the owner's word", () => {
  const root = project();
  write(root);
  run(["hold", "C183", ...CLAUDE, "--root", root]);
  const taken = run(["hold", "C183", "--takeover", ...CODEX, "--root", root]);
  assert.equal(taken.code, 0);
  // the replaced worktree is a folder that is no repository: its paths cannot be read, and the line says so
  assert.equal(
    taken.stdout,
    `the uncommitted paths of claude s1 m1 ${NEUTRAL} could not be read\nC183-park-helper: codex s2 m1 ${NEUTRAL}\n`,
  );
});

test("write is refused into an ergon another live session holds, and releases the lease it parks", () => {
  const root = project();
  write(root);
  run(["hold", "C183", ...CLAUDE, "--root", root]);
  const refused = write(root, CODEX);
  assert.equal(refused.code, 1);
  assert.ok(refused.stderr.includes("C183-park-helper is held by claude s1 m1"));
  assert.ok(refused.stderr.includes("read the note, hold another unit, or ask the owner"));
  assert.equal(write(root, CLAUDE).code, 0);
  assert.equal(readLease(ergonPath(root), TEXTS), null);
});

test("write over a stale lease is refused in one line and changes nothing", () => {
  const root = project();
  write(root);
  const ergon = ergonPath(root);
  staleLease(ergon);
  const lease = readUtf8(path.join(ergon, "HOLDER"));
  const note = readUtf8(path.join(ergon, "PARK.md"));
  const refused = write(root, [...CODEX, "--decision", "D-NEW"]);
  assert.equal(refused.code, 1);
  assert.ok(
    refused.stderr.startsWith("error: C183-park-helper is held by claude s1 m1 /work/tree, whose lease is stale;"),
  );
  assert.ok(refused.stderr.includes("hold --takeover"));
  assert.ok(refused.stderr.includes("the owner's word"));
  assert.equal(refused.stderr.split("\n").length, 2);
  assert.equal(readUtf8(path.join(ergon, "HOLDER")), lease);
  assert.equal(readUtf8(path.join(ergon, "PARK.md")), note);
});

test("write after a takeover goes through and keeps the replaced holder", () => {
  const root = project();
  write(root);
  staleLease(ergonPath(root));
  assert.equal(run(["hold", "C183", ...CODEX, "--takeover", "--root", root]).code, 0);
  assert.equal(write(root, CODEX).code, 0);
  assert.equal(readLease(ergonPath(root), TEXTS), null);
  assert.deepEqual(readNote(ergonPath(root), TEXTS).fields.sessions, [
    { harness: "claude", sessionId: "s1", machine: "m1" },
    { harness: "codex", sessionId: "s2", machine: "m1" },
  ]);
});

test("write keeps the sessions of the note and adds the new ones once", () => {
  const root = project();
  assert.equal(write(root, CLAUDE).code, 0);
  assert.equal(write(root, CODEX).code, 0);
  assert.equal(write(root, CLAUDE).code, 0);
  const sessions = [
    { harness: "claude", sessionId: "s1", machine: "m1" },
    { harness: "codex", sessionId: "s2", machine: "m1" },
  ];
  assert.deepEqual(readNote(ergonPath(root), TEXTS).fields.sessions, sessions);
  assert.equal(write(root).code, 0); // a write that names no session keeps the ones the note has
  assert.deepEqual(readNote(ergonPath(root), TEXTS).fields.sessions, sessions);
});

test("write merges the holder a takeover kept before the ergon had a note", () => {
  const root = project();
  const ergon = ergonPath(root);
  fs.mkdirSync(ergon, { recursive: true });
  assert.equal(run(["hold", "C183", ...CLAUDE, "--root", root]).code, 0);
  staleLease(ergon);
  assert.equal(run(["hold", "C183", ...CODEX, "--takeover", "--root", root]).code, 0);
  assert.ok(fs.existsSync(path.join(ergon, "SESSIONS")));
  assert.equal(write(root, CODEX).code, 0);
  assert.deepEqual(readNote(ergon, TEXTS).fields.sessions, [
    { harness: "claude", sessionId: "s1", machine: "m1" },
    { harness: "codex", sessionId: "s2", machine: "m1" },
  ]);
  assert.deepEqual(fs.readdirSync(ergon).sort(), ["PARK.md", "RESUME.md"]);
});

test("a takeover of an athlos is kept in the athlos file through the command line", () => {
  const root = project();
  const ergon = ergonWithPlan(root);
  assert.equal(run(["athlos", "C1", "--number", "1", "--step", "first", ...CLAUDE, "--root", root]).code, 0);
  const folder = path.join(ergon, "1");
  staleLease(folder);
  assert.equal(run(["hold", "C1", "--number", "1", ...CODEX, "--takeover", "--root", root]).code, 0);
  const sessions = [{ harness: "claude", sessionId: "s1", machine: "m1" }];
  assert.deepEqual(
    parseAthlosDoc(readUtf8(path.join(folder, "ATHLOS.md")), "ATHLOS.md", TEXTS).header.sessions,
    sessions,
  );
  assert.equal(run(["athlos", "C1", "--number", "1", "--step", "second", ...CODEX, "--root", root]).code, 0);
  assert.deepEqual(
    parseAthlosDoc(readUtf8(path.join(folder, "ATHLOS.md")), "ATHLOS.md", TEXTS).header.sessions,
    sessions,
  );
});

test("a write that fails leaves no lease and no folder behind", () => {
  const root = project();
  write(root);
  assert.equal(write(root, [], { name: "other-name" }).code, 1); // the id is taken under another name
  assert.ok(!fs.existsSync(ergonPath(root, "C183-other-name")));
  assert.equal(write(root, ["--origin", "two\nlines"], { ergonId: "C184", name: "new-ergon" }).code, 1);
  assert.ok(!fs.existsSync(ergonPath(root, "C184-new-ergon")));
});

test("write refuses to reuse the id and name of a closed ergon", () => {
  const root = project();
  write(root);
  assert.equal(run(["close", "C183", "--root", root]).code, 0);
  const refused = write(root);
  assert.equal(refused.code, 1);
  assert.equal(
    refused.stderr,
    "error: ergon C183-park-helper is closed and keeps its id and name; write under another id or name\n",
  );
  assert.ok(!fs.existsSync(ergonPath(root)));
});

test("write by an anonymous session over an anonymous lease is refused", () => {
  const root = project();
  write(root);
  fs.writeFileSync(
    path.join(ergonPath(root), "HOLDER"),
    renderLease({ holder: { harness: "", sessionId: "", machine: "", worktree: "" }, written: Date.now() / 1000 }),
  );
  const refused = write(root);
  assert.equal(refused.code, 1);
  assert.ok(refused.stderr.includes("C183-park-helper is held by ? ? ?"));
});

test("a hold on an athlos that does not exist is refused", () => {
  const root = project();
  write(root);
  const result = run(["hold", "C183", "--number", "4", "--root", root]);
  assert.equal(result.code, 1);
  assert.equal(result.stderr, "error: ergon C183-park-helper has no athlos C183.4\n");
  assert.equal(run(["release", "C183", "--number", "4", "--root", root]).stderr, result.stderr);
});

// --------------------------------------------------------------------------------------
// the plan and its athlos
// --------------------------------------------------------------------------------------

test("a plan's header and athlos lines are parsed", () => {
  const plan = parsePlan(PLAN_TEXT, TEXTS);
  assert.deepEqual(plan.header, { id: "C1", name: "demo", title: "Demo plan", tasks: ["C1", "C2"] });
  assert.deepEqual(plan.athlos, [
    {
      id: "C1.1",
      number: 1,
      label: "Build core",
      tasks: ["C1"],
      after: [],
      paths: ["src/a", "docs"],
      harness: "",
      result: "core built",
      zone: "",
    },
    {
      id: "C1.2",
      number: 2,
      label: "Write docs",
      tasks: [],
      after: ["C1.1"],
      paths: ["docs/x"],
      harness: "",
      result: "docs done",
      zone: "",
    },
    {
      id: "C1.3",
      number: 3,
      label: "Extra",
      tasks: [],
      after: [],
      paths: ["other"],
      harness: "claude",
      result: "",
      zone: "",
    },
  ]);
});

test("a plan without a header or a Athlos section has no athlos", () => {
  assert.deepEqual(parsePlan("# just prose\n", TEXTS).athlos, []);
  assert.deepEqual(parsePlan("# just prose\n", TEXTS).header, { id: "", name: "", title: "", tasks: [] });
  assert.deepEqual(parsePlan("---\nid: C1\n---\n## Notes\n\n- C1.1 · a\n", TEXTS).athlos, []);
  assert.deepEqual(parsePlan("---\nid: C1\nno closing fence\n", TEXTS).header.id, "");
});

test("an athlos line that is not one is skipped", () => {
  for (const line of ["C1.1 · a", "- C1.1", "- C1 · a", "- C1.x · a", "- plain text", "* C1.1 · a"]) {
    assert.equal(parseAthlosLine(line, TEXTS), null, line);
  }
  assert.equal(parseAthlosLine("- _T3.2 · local athlos", TEXTS)?.number, 2);
  assert.deepEqual(parseAthlosLine("- C1.1 · a · tasks C1, C2 · after C1.0", TEXTS)?.tasks, ["C1", "C2"]);
});

test("the zone of an athlos line sits beside its tasks and is empty when absent", () => {
  assert.equal(parseAthlosLine("- C1.1 · a · tasks C1 · zone: docs · result: r", TEXTS)?.zone, "docs");
  assert.equal(parseAthlosLine("- C1.1 · a · tasks C1 · result: r", TEXTS)?.zone, "");
});

test("a plan line with a field the format does not carry is refused", () => {
  assert.throws(
    () => parsePlan("---\nid: C1\n---\n## Athlos\n\n- C1.1 · a · colour red\n", TEXTS),
    parkError("C1.1: a plan line carries no field colour"),
  );
});

test("a plan written before the rename is read and translated", () => {
  const legacy = parsePlan(PLAN_TEXT.replace("## Athlos", "## Jobs"), TEXTS);
  assert.equal(legacy.athlos.length, 3);
});

test("an athlos folder is named by its number alone", () => {
  const root = project();
  const ergon = ergonWithPlan(root);
  assert.equal(athlosFolder(ergon, 1), null);
  const folder = path.join(ergon, "1");
  fs.mkdirSync(folder, { recursive: true });
  assert.equal(athlosFolder(ergon, 1), folder);
  assert.equal(athlosFileOf(folder), path.join(folder, "ATHLOS.md"));
  // the write target of a number that already sits in the new layout is that folder, unchanged
  assert.equal(moveAthlosFolder(ergon, 1, folder), folder);
});

test("a record in the old jobs layout is read, and the next write moves it to the new one", () => {
  const root = project();
  const ergon = ergonWithPlan(root);
  const legacy = path.join(ergon, "jobs", "1");
  fs.mkdirSync(legacy, { recursive: true });
  const header = parkFields({ id: "C1", name: "demo", nextAction: "r", athlos: "C1.1" });
  const text = renderAthlosDoc({ header, steps: [], done: false }, TEXTS).replace("\nathlos:", "\njob:");
  fs.writeFileSync(path.join(legacy, "JOB.md"), text);
  assert.equal(athlosFolder(ergon, 1), legacy);
  const read = parseAthlosDoc(readUtf8(athlosFileOf(legacy)), "jobs/1/JOB.md", TEXTS);
  assert.equal(read.header.athlos, "C1.1"); // the old `job:` key reads under its new name
  assert.equal(run(["athlos", "C1", "--number", "1", "--step", "one", ...CLAUDE, "--root", root]).code, 0);
  assert.ok(!fs.existsSync(path.join(ergon, "jobs")));
  assert.ok(fs.existsSync(path.join(ergon, "1", "ATHLOS.md")));
});

test("two athlos that may run at once and share a path are warned of", () => {
  const plan = parsePlan(
    "---\nid: C1\n---\n## Athlos\n\n- C1.1 · a · paths src/a, docs\n- C1.2 · b · paths src/a/deep.py\n- C1.3 · c · paths docs/\n- C1.4 · d · paths other\n",
    TEXTS,
  );
  assert.deepEqual(sharedPathWarnings(plan, TEXTS), [
    "warning: athlos C1.1 C1.2 may run at once and share path src/a",
    "warning: athlos C1.1 C1.3 may run at once and share path docs",
  ]);
  assert.deepEqual(
    sharedPathWarnings(
      parsePlan("---\nid: C1\n---\n## Athlos\n\n- C1.1 · a · paths x\n- C1.2 · b · paths y\n", TEXTS),
      TEXTS,
    ),
    [],
  );
});

test("an athlos file renders its steps and the done mark, and parses back", () => {
  const header = parkFields({
    id: "C1",
    name: "demo",
    nextAction: "core built",
    plan: "C1",
    athlos: "C1.1",
    tasks: ["C1"],
  });
  /** @type {import("./park.mjs").AthlosDoc} */
  const doc = {
    header,
    steps: [
      ["one", true],
      ["two", false],
    ],
    done: true,
  };
  const text = renderAthlosDoc(doc, TEXTS);
  assert.ok(text.endsWith("## Steps\n\n- [x] one\n- [ ] two\n\ndone\n"));
  assert.deepEqual(parseAthlosDoc(text, "ATHLOS.md", TEXTS), doc);
  assert.ok(renderAthlosDoc({ header, steps: [], done: false }, TEXTS).endsWith("## Steps\n\n_none_\n"));
  assert.throws(() => parseAthlosDoc("no header\n", "ATHLOS.md", TEXTS), parkError("ATHLOS.md: no header"));
});

test("a label in another script names no folder, so the athlos is still written", () => {
  const root = project();
  const ergon = ergonPath(root, "C1-demo");
  fs.mkdirSync(ergon, { recursive: true });
  fs.writeFileSync(
    path.join(ergon, "PLAN.md"),
    "---\nid: C1\nname: demo\n---\n\n## Athlos\n\n- C1.1 · Écrire le bail 租约 · tasks C1 · result: le bail existe\n",
  );
  const result = run(["athlos", "C1", "--number", "1", "--step", "écrire", ...CLAUDE, "--root", root]);
  assert.equal(result.code, 0);
  assert.equal(result.stdout, "_aitna/.ergon/C1-demo/1\n");
  assert.ok(fs.existsSync(path.join(ergon, "1", "ATHLOS.md"))); // the folder is the number; the label stays on the plan line
});

test("the athlos command creates an athlos's file from the plan's line and holds the athlos", () => {
  const root = project();
  const ergon = ergonWithPlan(root);
  const result = run(["athlos", "C1", "--number", "1", "--step", "one", "--step", "two", ...CLAUDE, "--root", root]);
  assert.equal(result.code, 0);
  assert.equal(result.stdout, "_aitna/.ergon/C1-demo/1\n");
  const folder = path.join(ergon, "1");
  const doc = parseAthlosDoc(readUtf8(path.join(folder, "ATHLOS.md")), "ATHLOS.md", TEXTS);
  assert.deepEqual(
    {
      athlos: doc.header.athlos,
      plan: doc.header.plan,
      tasks: doc.header.tasks,
      next: doc.header.nextAction,
      id: doc.header.id,
    },
    { athlos: "C1.1", plan: "C1", tasks: ["C1"], next: "core built", id: "C1" },
  );
  assert.deepEqual(doc.steps, [
    ["one", false],
    ["two", false],
  ]);
  assert.equal(readLease(folder, TEXTS)?.holder.sessionId, "s1");
  // a second write adds steps and keeps the first; --done marks the athlos done
  run(["athlos", "C1", "--number", "1", "--step", "three", "--done", ...CLAUDE, "--root", root]);
  const again = parseAthlosDoc(readUtf8(path.join(folder, "ATHLOS.md")), "ATHLOS.md", TEXTS);
  assert.deepEqual(
    again.steps.map(([text]) => text),
    ["one", "two", "three"],
  );
  assert.equal(again.done, true);
});

test("the athlos command is refused into an athlos another session holds, and for an athlos the plan lacks", () => {
  const root = project();
  ergonWithPlan(root);
  run(["athlos", "C1", "--number", "1", "--step", "one", ...CLAUDE, "--root", root]);
  const refused = run(["athlos", "C1", "--number", "1", "--step", "two", ...CODEX, "--root", root]);
  assert.equal(refused.code, 1);
  assert.ok(refused.stderr.startsWith("error: 1 is held by claude s1 m1 "));
  const missing = run(["athlos", "C1", "--number", "9", ...CLAUDE, "--root", root]);
  assert.equal(missing.code, 1);
  assert.equal(missing.stderr, "error: ergon C1-demo has no athlos C1.9\n");
});

test("an athlos in an ergon without a plan is refused, and nothing is written", () => {
  const root = project();
  write(root);
  const result = run(["athlos", "C183", "--number", "1", "--step", "x", ...CLAUDE, "--root", root]);
  assert.equal(result.code, 1);
  assert.equal(result.stderr, "error: ergon C183-park-helper has no PLAN.md, so it has no athlos\n");
  assert.ok(!fs.existsSync(path.join(ergonPath(root), "athlos")));
  assert.deepEqual(
    walk(ergonPath(root)).filter((file) => path.basename(file) === "HOLDER"),
    [],
  );
});

/**
 * An ergon `C186-holders-units` whose plan is `text`.
 * @param {string} root
 * @param {string} text
 * @returns {string} the ergon folder
 */
function planErgon(root, text) {
  const ergon = ergonPath(root, "C186-holders-units");
  fs.mkdirSync(ergon, { recursive: true });
  fs.writeFileSync(path.join(ergon, "PLAN.md"), text);
  return ergon;
}

test("an athlos line the helper cannot write from is refused before anything is written", () => {
  for (const [line, message] of [
    ["- C186.1 ·  · result: r", "error: athlos C186.1 has no label on its plan line\n"],
    ["- C186.1 · Lease module · tasks C186", "error: ergon C186-holders-units: athlos C186.1 has no result\n"],
    ["- C186.1 · Lease module · result:", "error: ergon C186-holders-units: athlos C186.1 has no result\n"],
  ]) {
    const root = project();
    const ergon = planErgon(root, `---\nid: C186\nname: holders-units\n---\n\n## Athlos\n\n${line}\n`);
    const result = run(["athlos", "C186", "--number", "1", "--step", "x", ...CLAUDE, "--root", root]);
    assert.equal(result.code, 1, line);
    assert.equal(result.stderr, message);
    assert.equal(result.stdout, "");
    assert.ok(!fs.existsSync(path.join(ergon, "1")));
    assert.deepEqual(
      walk(ergon).filter((file) => path.basename(file) === "HOLDER"),
      [],
    );
  }
});

test("the athlos command prints the plan's shared-path warnings on stderr, one line each, stdout unchanged", () => {
  const root = project();
  planErgon(
    root,
    "---\nid: C186\nname: holders-units\n---\n\n## Athlos\n\n" +
      "- C186.1 · Lease module · paths tools/park · result: r\n" +
      "- C186.2 · Athlos file · paths tools/park/park.py · result: r\n",
  );
  const result = run(["athlos", "C186", "--number", "1", "--step", "x", ...CLAUDE, "--root", root]);
  assert.equal(result.code, 0);
  assert.equal(result.stdout, "_aitna/.ergon/C186-holders-units/1\n");
  assert.equal(result.stderr, "warning: athlos C186.1 C186.2 may run at once and share path tools/park\n");
  const quiet = project();
  ergonWithPlan(quiet);
  assert.equal(run(["athlos", "C1", "--number", "1", "--step", "x", ...CLAUDE, "--root", quiet]).stderr, "");
});

test("athlos that wait for each other, directly or through a chain, share no warning", () => {
  for (const lines of [
    ["- C1.1 · A · paths x · result: r", "- C1.2 · B · after C1.1 · paths x · result: r"],
    [
      "- C1.1 · A · paths x · result: r",
      "- C1.2 · B · after C1.1 · paths x · result: r",
      "- C1.3 · C · after C1.2 · paths x · result: r",
    ],
  ]) {
    const plan = parsePlan(`---\nid: C1\nname: k\n---\n\n## Athlos\n\n${lines.join("\n")}\n`, TEXTS);
    assert.deepEqual(sharedPathWarnings(plan, TEXTS), []);
  }
});

// --------------------------------------------------------------------------------------
// derived states and the listing
// --------------------------------------------------------------------------------------

test("the state of a unit is derived: active, parked, not started, done", () => {
  const root = project();
  const now = Date.now() / 1000;
  const ergon = ergonPath(root, "C1-a");
  fs.mkdirSync(ergon, { recursive: true });
  assert.equal(unitState(ergon, TEXTS, context(now)), "not started");
  fs.writeFileSync(path.join(ergon, "PARK.md"), "x");
  assert.equal(unitState(ergon, TEXTS, context(now)), "parked");
  acquireLease(ergon, CLAUDE_HOLDER, TEXTS, context(now, "m1"));
  assert.equal(unitState(ergon, TEXTS, context(now, "m1")), "active");
  // a stale lease holds nothing
  assert.equal(unitState(ergon, TEXTS, context(now + (STALE_HOURS + 1) * HOUR, "m1")), "parked");
  assert.equal(unitState(ergon, TEXTS, context(now, "m1"), { athlosDone: true }), "done");
  fs.rmSync(path.join(ergon, "PARK.md"));
  assert.equal(unitState(ergon, TEXTS, context(now + (STALE_HOURS + 1) * HOUR, "m1")), "not started");
});

test("an ergon is done when every athlos its plan lists is done, and a planned athlos with no folder blocks it", () => {
  const root = project();
  const ergon = ergonWithPlan(root);
  const now = context(Date.now() / 1000);
  assert.equal(ergonState(ergon, TEXTS, now), "not started"); // no athlos folder yet
  run(["athlos", "C1", "--number", "1", "--step", "one", ...CLAUDE, "--root", root]);
  assert.equal(ergonState(ergon, TEXTS, now), "active"); // an athlos is held, so the ergon is active though it is free itself
  run(["athlos", "C1", "--number", "1", "--done", ...CLAUDE, "--root", root]);
  run(["athlos", "C1", "--number", "2", "--step", "two", ...CLAUDE, "--root", root]);
  run(["athlos", "C1", "--number", "2", "--done", ...CLAUDE, "--root", root]);
  // the plan's third athlos has no folder: it has not started (ADR 0028 D08)
  assert.equal(ergonState(ergon, TEXTS, now), "not started");
  doneAthlos(ergon, 3);
  assert.equal(ergonState(ergon, TEXTS, now), "done");
  fs.rmSync(path.join(ergon, "3", "ATHLOS.md"));
  assert.equal(ergonState(ergon, TEXTS, now), "not started"); // a folder with no athlos file is not a done athlos
  fs.rmSync(path.join(ergon, "2", "ATHLOS.md"));
  fs.writeFileSync(path.join(ergon, "PARK.md"), "note");
  assert.equal(ergonState(ergon, TEXTS, now), "parked");
});

/**
 * A done `ATHLOS.md` for the plan's athlos `number` of ergon `C1-demo`, written by hand.
 * @param {string} ergon
 * @param {number} number
 */
function doneAthlos(ergon, number) {
  const folder = path.join(ergon, `${number}`);
  fs.mkdirSync(folder, { recursive: true });
  const header = parkFields({ id: "C1", name: "demo", nextAction: "r", athlos: `C1.${number}` });
  fs.writeFileSync(path.join(folder, "ATHLOS.md"), renderAthlosDoc({ header, steps: [], done: true }, TEXTS));
}

test("an ergon with no plan, or a plan with no athlos, is done by the athlos folders that exist", () => {
  const root = project();
  const bare = ergonPath(root, "C5-bare");
  fs.mkdirSync(bare, { recursive: true });
  const now = context(Date.now() / 1000);
  assert.equal(ergonState(bare, TEXTS, now), "not started"); // no folder, nothing done
  const empty = planErgon(root, "---\nid: C6\nname: empty\n---\n\n## Athlos\n\n");
  for (const ergon of [bare, empty]) {
    const folder = path.join(ergon, "1");
    fs.mkdirSync(folder, { recursive: true });
    const header = parkFields({ id: "C5", name: "x", nextAction: "r", athlos: "C5.1" });
    fs.writeFileSync(path.join(folder, "ATHLOS.md"), renderAthlosDoc({ header, steps: [], done: true }, TEXTS));
    assert.equal(ergonState(ergon, TEXTS, now), "done");
  }
});

test("a list of an empty ergon says so", () => {
  const root = project();
  assert.equal(run(["list", "--root", root]).code, 0);
  assert.equal(run(["list", "--root", root]).stdout, "no ergons in _aitna/.ergon\n");
  fs.mkdirSync(path.join(root, "_aitna", ".ergon"), { recursive: true });
  assert.equal(run(["list", "--root", root]).stdout, "no ergons in _aitna/.ergon\n");
});

/**
 * @param {string} root
 */
function populate(root) {
  write(root, ["--plan", "A59", "--decision", "D-X", "--decision", "D-Y"]);
  write(root, ["--plan", "A60"], { ergonId: "A5", name: "second" });
  fs.mkdirSync(ergonPath(root, "C7-never"));
  write(root, [], { ergonId: "C20", name: "third" });
  run(["hold", "C20", ...CLAUDE, "--root", root]);
}

test("list prints one line per ergon, sorted by id, with the derived state", () => {
  const root = project();
  populate(root);
  const result = run(["list", ...MACHINE, "--root", root]);
  assert.equal(result.code, 0);
  assert.deepEqual(result.stdout.split("\n").slice(0, -1), [
    "A5 | second | parked | A60 | Twin it | 0 | - | 0d",
    "C183 | park-helper | parked | A59 | Twin it | 2 | - | 0d",
    "C20 | third | active | - | Twin it | 0 | - | 0d",
    "C7 | never | not started | - | - | 0 | - | -",
  ]);
});

test("list filters by plan, state and task", () => {
  const root = project();
  populate(root);
  /**
   * @param {...string} flags
   * @returns {string[]}
   */
  const listed = (...flags) =>
    run(["list", ...flags, ...MACHINE, "--root", root])
      .stdout.split("\n")
      .slice(0, -1)
      .map((line) => line.split(" | ")[0]);
  assert.deepEqual(listed("--plan", "A59"), ["C183"]);
  assert.deepEqual(listed("--state", "parked"), ["A5", "C183"]);
  assert.deepEqual(listed("--state", "not started"), ["C7"]);
  assert.deepEqual(listed("--state", "active"), ["C20"]);
  assert.deepEqual(listed("--state", "done"), ["no ergon matches the filters"]);
  assert.deepEqual(listed("--plan", "A59", "--state", "active"), ["no ergon matches the filters"]);
  // the local index is retired, so its `--status` filter is gone with it
  assert.equal(run(["list", "--status", "parked", "--root", root]).code, 2);
});

test("list shows the athlos of an ergon under it and filters by task", () => {
  const root = project();
  const ergon = ergonWithPlan(root);
  write(root);
  run(["athlos", "C1", "--number", "1", "--step", "one", "--step", "two", ...CLAUDE, "--root", root]);
  run(["athlos", "C1", "--number", "2", "--done", ...CLAUDE, "--root", root]);
  run(["release", "C1", "--number", "1", "--root", root]);
  fs.writeFileSync(
    path.join(ergon, "PARK.md"),
    renderNote(parkFields({ id: "C1", name: "demo", nextAction: "next", plan: "A1" }), parkBody({ goal: "g" }), TEXTS),
  );
  const result = run(["list", ...MACHINE, "--root", root]);
  assert.deepEqual(result.stdout.split("\n").slice(0, -1), [
    "C1 | demo | parked | A1 | next | 0 | - | 0d",
    "  C1.1 | 1 | not started | C1 | one | - | 0d",
    "  C1.2 | 2 | done | - | - | - | 0d",
    "C183 | park-helper | parked | - | Twin it | 0 | - | 0d",
  ]);
  /**
   * @param {string} task
   * @returns {string[]}
   */
  const withTask = (task) =>
    run(["list", "--task", task, ...MACHINE, "--root", root])
      .stdout.split("\n")
      .slice(0, -1)
      .filter((line) => !line.startsWith(" "))
      .map((line) => line.split(" | ")[0]);
  assert.deepEqual(withTask("C1"), ["C1"]); // the plan's tasks, an athlos line's, an athlos file's
  assert.deepEqual(withTask("C2"), ["C1"]); // named in the plan header only
  assert.deepEqual(withTask("C9"), ["no ergon matches the filters"]);
});

test("an athlos line formats with its tasks, its next step and its age", () => {
  assert.equal(
    formatAthlos(
      {
        id: "C1.1",
        name: "1-a",
        state: "active",
        tasks: ["C1", "C2"],
        nextAction: "x".repeat(70),
        branch: "",
        ageDays: 2,
      },
      TEXTS,
    ),
    `  C1.1 | 1-a | active | C1, C2 | ${"x".repeat(59)}… | - | 2d`,
  );
  assert.equal(
    formatAthlos(
      { id: "C1.1", name: "1-a", state: "done", tasks: [], nextAction: "", branch: "b", ageDays: null },
      TEXTS,
    ),
    "  C1.1 | 1-a | done | - | - | b | -",
  );
});

test("list truncates the next action at sixty characters", () => {
  const root = project();
  const longNext = "x".repeat(100);
  run(["write", "C1", "--name", "n", "--goal", "g", "--next", longNext, "--root", root]);
  assert.equal(run(["list", "--root", root]).stdout.split(" | ")[4], `${"x".repeat(59)}…`);
  const exact = "y".repeat(60);
  run(["write", "C2", "--name", "n", "--goal", "g", "--next", exact, "--root", root]);
  assert.equal(run(["list", "--root", root]).stdout.split("\n")[1].split(" | ")[4], exact);
});

test("list cuts the next action by code points", () => {
  const root = project();
  const astral = "𝒳".repeat(61);
  run(["write", "C1", "--name", "n", "--goal", "g", "--next", astral, "--root", root]);
  assert.equal(run(["list", "--root", root]).stdout.split(" | ")[4], `${"𝒳".repeat(59)}…`);
});

test("list age is whole days from the note mtime", () => {
  const root = project();
  write(root);
  const note = path.join(ergonPath(root), "PARK.md");
  const now = Date.now() / 1000;
  const old = now - 3 * 86400 - 100;
  fs.utimesSync(note, old, old);
  const [item] = listErgons(root, NO_QUERY, TEXTS, context(now)).ergons;
  assert.equal(item.ageDays, 3);
  assert.ok(formatSummary(item, TEXTS).endsWith("| 3d"));
  fs.utimesSync(note, now + 500, now + 500); // a clock behind the file never gives a negative age
  assert.equal(listErgons(root, NO_QUERY, TEXTS, context(now)).ergons[0].ageDays, 0);
});

test("list reads and writes nothing", () => {
  const root = project();
  populate(root);
  ergonWithPlan(root);
  /** @returns {Map<string, {bytes: string, mtime: number}>} */
  const snapshot = () =>
    new Map(
      walk(root).map((file) => [
        file,
        { bytes: fs.readFileSync(file).toString("base64"), mtime: fs.statSync(file).mtimeMs },
      ]),
    );
  const before = snapshot();
  run(["list", "--root", root]);
  run(["list", "--state", "parked", "--root", root]);
  run(["list", "--closed", "--task", "C1", "--root", root]);
  assert.deepEqual(snapshot(), before);
});

test("list ignores folders that are not ergons", () => {
  const root = project();
  write(root);
  fs.mkdirSync(path.join(path.dirname(ergonPath(root)), "notes"));
  fs.writeFileSync(path.join(path.dirname(ergonPath(root)), "stray.txt"), "x");
  assert.equal(run(["list", "--root", root]).stdout.split("\n").length - 1, 1);
});

test("list reports an ergon whose note does not parse on its own line and lists the others", () => {
  const root = project();
  write(root);
  write(root, [], { ergonId: "C184", name: "other" });
  fs.writeFileSync(path.join(ergonPath(root), "PARK.md"), "broken\n");
  const result = run(["list", "--root", root]);
  assert.equal(result.code, 0);
  assert.equal(result.stderr, "");
  const lines = result.stdout.split("\n");
  assert.equal(
    lines[0],
    "C183 | park-helper | unreadable | C183-park-helper/PARK.md: no header between two '---' lines at the top of the note",
  );
  assert.ok(lines[1].startsWith("C184 | other | parked | "));
});

test("list names the ergon and the file of an athlos file that does not parse, and lists the other ergons", () => {
  const root = project();
  const ergon = planErgon(root, PLAN_TEXT);
  doneAthlos(ergon, 1);
  fs.writeFileSync(path.join(ergon, "1", "ATHLOS.md"), "no header\n");
  write(root);
  const lines = run(["list", "--root", root]).stdout.split("\n");
  assert.ok(lines[0].startsWith("C183 | park-helper | parked | "));
  assert.equal(
    lines[1],
    "C186 | holders-units | unreadable | C186-holders-units/1/ATHLOS.md: no header between two '---' lines at the top of the note",
  );
});

test("an unreadable ergon is listed whatever the filters say", () => {
  const root = project();
  write(root);
  fs.writeFileSync(path.join(ergonPath(root), "PARK.md"), "broken\n");
  const lines = run(["list", "--state", "active", "--root", root]).stdout.split("\n");
  assert.equal(lines.length, 2);
  assert.ok(lines[0].startsWith("C183 | park-helper | unreadable | "));
});

test("a plan whose id is no task id is refused before the athlos file or the lease exists", () => {
  const root = project();
  const ergon = planErgon(
    root,
    "---\nid: c3\nname: holders-units\n---\n\n## Athlos\n\n- C186.1 · Lease module · tasks C186 · result: r\n",
  );
  const result = run(["athlos", "C186", "--number", "1", "--step", "x", ...CLAUDE, "--root", root]);
  assert.equal(result.code, 1);
  assert.equal(result.stdout, "");
  assert.equal(
    result.stderr,
    "error: ergon C186-holders-units: plan c3 is not a task id (a capital letter or _T followed by digits, e.g. C183 or _T3)\n",
  );
  assert.ok(!fs.existsSync(path.join(ergon, "1")));
});

test("an athlos file is replaced atomically and leaves no temporary file", (t) => {
  const root = project();
  const ergon = ergonWithPlan(root);
  run(["athlos", "C1", "--number", "1", "--step", "first", ...CLAUDE, "--root", root]);
  const folder = path.join(ergon, "1");
  const file = path.join(folder, "ATHLOS.md");
  const before = fs.readFileSync(file);
  const doc = readAthlosDoc(file, TEXTS);
  assert.ok(doc !== null);
  const mock = t.mock.method(fs, "renameSync", () => {
    throw new Error("disk says no");
  });
  assert.throws(() => writeAthlosDoc(folder, { ...doc, steps: [["second", false]] }, TEXTS), /disk says no/);
  mock.mock.restore();
  assert.deepEqual(fs.readFileSync(file), before);
  assert.deepEqual(fs.readdirSync(folder).sort(), ["ATHLOS.md", "HOLDER"]);
  writeAthlosDoc(folder, { ...doc, steps: [["second", false]] }, TEXTS);
  assert.deepEqual(readAthlosDoc(file, TEXTS)?.steps, [["second", false]]);
  assert.deepEqual(fs.readdirSync(folder).sort(), ["ATHLOS.md", "HOLDER"]);
});

test("an ergon is parked when any of its athlos is parked, and active beats parked", () => {
  const root = project();
  const ergon = ergonWithPlan(root);
  const now = context(Date.now() / 1000);
  doneAthlos(ergon, 1);
  fs.rmSync(path.join(ergon, "1", "ATHLOS.md"));
  const header = parkFields({ id: "C1", name: "demo", nextAction: "r", athlos: "C1.1" });
  fs.writeFileSync(path.join(ergon, "1", "ATHLOS.md"), renderAthlosDoc({ header, steps: [], done: false }, TEXTS));
  fs.writeFileSync(
    path.join(ergon, "1", "PARK.md"),
    renderNote(parkFields({ id: "C1", name: "demo", nextAction: "n" }), parkBody({ goal: "g" }), TEXTS),
  );
  assert.equal(ergonState(ergon, TEXTS, now), "parked");
  run(["athlos", "C1", "--number", "2", "--step", "two", ...CLAUDE, "--root", root]);
  assert.equal(ergonState(ergon, TEXTS, now), "active");
});

test("an ergon with every athlos done is done unless the ergon itself is held", () => {
  const root = project();
  const ergon = ergonWithPlan(root);
  const now = context(Date.now() / 1000);
  for (const number of [1, 2, 3]) {
    const folder = path.join(ergon, `${number}`);
    fs.mkdirSync(folder, { recursive: true });
    const header = parkFields({ id: "C1", name: "demo", nextAction: "r", athlos: `C1.${number}` });
    fs.writeFileSync(path.join(folder, "ATHLOS.md"), renderAthlosDoc({ header, steps: [], done: true }, TEXTS));
  }
  fs.writeFileSync(path.join(ergon, "PARK.md"), "note"); // a stale note of the plan does not undo done
  assert.equal(ergonState(ergon, TEXTS, now), "done");
  acquireLease(ergon, CLAUDE_HOLDER, TEXTS, now);
  assert.equal(ergonState(ergon, TEXTS, now), "active");
});

// --------------------------------------------------------------------------------------
// close and export
// --------------------------------------------------------------------------------------

test("close moves the ergon to the closed folder and frees its leases", () => {
  const root = project();
  ergonWithPlan(root);
  run(["athlos", "C1", "--number", "1", "--step", "one", ...CLAUDE, "--root", root]);
  run(["hold", "C1", ...CLAUDE, "--root", root]);
  const result = run(["close", "C1", "--root", root]);
  assert.equal(result.code, 0);
  assert.equal(result.stdout, "_aitna/.ergon/.closed/C1-demo\n");
  assert.ok(!fs.existsSync(ergonPath(root, "C1-demo")));
  const closed = path.join(ergonPath(root, ".closed"), "C1-demo");
  assert.ok(fs.statSync(path.join(closed, "PLAN.md")).isFile());
  assert.deepEqual(
    walk(closed).filter((file) => path.basename(file) === "HOLDER"),
    [],
  );
  assert.equal(findClosedErgon(root, "C1", TEXTS), closed);
  assert.equal(findClosedErgon(root, "C2", TEXTS), null);
  assert.throws(() => findErgon(root, "C1", TEXTS), parkError("no ergon with id C1"));
});

test("close refuses an ergon a live session holds, naming the holder, and changes nothing", () => {
  const root = project();
  write(root);
  run(["hold", "C183", ...CLAUDE, "--root", root]);
  const refused = run(["close", "C183", ...CODEX, "--root", root]);
  assert.equal(refused.code, 1);
  assert.ok(refused.stderr.startsWith("error: C183-park-helper is held by claude s1 m1 "));
  assert.equal(refused.stderr.split("\n").length, 2);
  assert.ok(fs.existsSync(path.join(ergonPath(root), "HOLDER")));
  assert.ok(!fs.existsSync(path.join(ergonPath(root, ".closed"), "C183-park-helper")));
});

test("close refuses an ergon whose athlos a live session holds", () => {
  const root = project();
  const ergon = ergonWithPlan(root);
  run(["athlos", "C1", "--number", "1", "--step", "one", ...CLAUDE, "--root", root]);
  const refused = run(["close", "C1", ...CODEX, "--root", root]);
  assert.equal(refused.code, 1);
  assert.ok(refused.stderr.startsWith("error: 1 is held by claude s1 m1 "));
  assert.ok(fs.existsSync(path.join(ergon, "1", "HOLDER")));
});

test("close by the holder frees its leases, and a stale lease does not block it", () => {
  const root = project();
  write(root);
  run(["hold", "C183", ...CLAUDE, "--root", root]);
  assert.equal(run(["close", "C183", ...CLAUDE, "--root", root]).code, 0);
  assert.deepEqual(
    walk(path.join(ergonPath(root, ".closed"), "C183-park-helper")).filter((file) => path.basename(file) === "HOLDER"),
    [],
  );
  write(root, [], { ergonId: "C184", name: "second" });
  staleLease(ergonPath(root, "C184-second"));
  assert.equal(run(["close", "C184", ...CODEX, "--root", root]).code, 0);
});

test("close over an existing closed ergon is one line and changes nothing", () => {
  const root = project();
  write(root);
  const target = path.join(ergonPath(root, ".closed"), "C183-park-helper");
  fs.mkdirSync(target, { recursive: true });
  fs.writeFileSync(path.join(target, "mark"), "old");
  run(["hold", "C183", ...CLAUDE, "--root", root]);
  const refused = run(["close", "C183", ...CLAUDE, "--root", root]);
  assert.equal(refused.code, 1);
  assert.equal(
    refused.stderr,
    "error: ergon C183-park-helper was not closed: _aitna/.ergon/.closed/C183-park-helper already exists\n",
  );
  assert.ok(fs.existsSync(path.join(ergonPath(root), "HOLDER")));
  assert.ok(fs.existsSync(path.join(ergonPath(root), "PARK.md")));
  assert.deepEqual(fs.readdirSync(target), ["mark"]);
});

test("list leaves a closed ergon out, and --closed brings it back", () => {
  const root = project();
  write(root);
  write(root, [], { ergonId: "C2", name: "other" });
  run(["close", "C183", "--root", root]);
  assert.deepEqual(
    run(["list", "--root", root])
      .stdout.split("\n")
      .slice(0, -1)
      .map((line) => line.split(" | ")[0]),
    ["C2"],
  );
  assert.deepEqual(
    run(["list", "--closed", "--root", root])
      .stdout.split("\n")
      .slice(0, -1)
      .map((line) => line.split(" | ")[0]),
    ["C183", "C2"],
  );
  run(["close", "C2", "--root", root]);
  assert.equal(run(["list", "--root", root]).stdout, "no ergons in _aitna/.ergon\n");
});

test("close of an unknown ergon is refused", () => {
  const root = project();
  const result = run(["close", "C9", "--root", root]);
  assert.equal(result.code, 1);
  assert.equal(result.stderr, "error: no ergon with id C9 under _aitna/.ergon; ergons: none\n");
});

test("export writes the ergon's files in path order and leaves the leases out", () => {
  const root = project();
  const ergon = ergonWithPlan(root);
  write(root, [], { ergonId: "C1", name: "demo" });
  run(["athlos", "C1", "--number", "1", "--step", "one", ...CLAUDE, "--root", root]);
  run(["hold", "C1", ...CLAUDE, "--root", root]);
  assert.ok(fs.existsSync(path.join(ergon, "HOLDER")));
  const out = path.join(root, "out", "bundle.md");
  const result = run(["export", "C1", "--out", out, "--root", root]);
  assert.equal(result.code, 0);
  assert.equal(result.stdout, `${out}\n`);
  const bundle = readUtf8(out);
  assert.ok(bundle.startsWith("# akmon ergon bundle: C1-demo\n\n--- file: 1/ATHLOS.md\n"));
  const files = [...bundle.matchAll(/^--- file: (.*)$/gm)].map((match) => match[1]);
  assert.deepEqual(files, ["1/ATHLOS.md", "PARK.md", "PLAN.md", "RESUME.md"]);
  assert.ok(!bundle.includes("HOLDER") && !bundle.includes("harness: claude\nsession"));
  assert.ok(bundle.includes("- [ ] one\n") && bundle.endsWith("--- end\n"));
  assert.equal(exportErgon(ergon, path.join(root, "again.md"), TEXTS), path.join(root, "again.md"));
  assert.equal(readUtf8(path.join(root, "again.md")), bundle);
});

test("an export sorts a file by its path components, not by the string", () => {
  const root = project();
  const ergon = ergonPath(root, "C1-demo");
  fs.mkdirSync(path.join(ergon, "a-b"), { recursive: true });
  fs.mkdirSync(path.join(ergon, "a"), { recursive: true });
  fs.writeFileSync(path.join(ergon, "a-b", "x"), "1\n");
  fs.writeFileSync(path.join(ergon, "a", "x"), "2\n");
  exportErgon(ergon, path.join(root, "bundle.md"), TEXTS);
  const files = [...readUtf8(path.join(root, "bundle.md")).matchAll(/^--- file: (.*)$/gm)].map((match) => match[1]);
  assert.deepEqual(files, ["a/x", "a-b/x"]);
});

// --------------------------------------------------------------------------------------
// the active unit and the worktrees
// --------------------------------------------------------------------------------------

test("a worktree's folder names its ergon and its athlos", () => {
  assert.deepEqual(worktreeUnit("/p/.worktrees/C186-holders-units.2"), { ergonId: "C186", number: 2 });
  assert.deepEqual(worktreeUnit("/p/.worktrees/_T3-scratch.10"), { ergonId: "_T3", number: 10 });
  assert.deepEqual(worktreeUnit("/p/.worktrees/C186-holders-units.\u0663"), { ergonId: "C186", number: 3 }); // a decimal digit
  for (const folder of [
    "/p/.worktrees/C186-holders-units",
    "/p/.worktrees/C186.2",
    "/p/.worktrees/main.x",
    "/p/.worktrees/-x.1",
    "/p/.worktrees/x.1.",
    "/p/.worktrees/C186-holders-units.\u00b2", // a superscript digit is not a decimal one
  ]) {
    assert.equal(worktreeUnit(folder), null, folder);
  }
});

/**
 * A project whose root is a worktree folder `<outer>/.worktrees/C1-demo.1`, with the ergon in it.
 * @returns {string} the worktree root
 */
function worktreeProject() {
  const outer = tempDir("park-test-");
  const root = path.join(outer, ".worktrees", "C1-demo.1");
  fs.mkdirSync(path.join(root, "_aitna"), { recursive: true });
  fs.writeFileSync(path.join(root, "AGENTS.md"), "# agents\n");
  fs.writeFileSync(path.join(root, "_aitna", ".akmon.toml"), "");
  ergonWithPlan(root);
  return root;
}

test("the active unit is read from the worktree folder", () => {
  const root = worktreeProject();
  const ergon = ergonPath(root, "C1-demo");
  assert.deepEqual(activeUnit(root, TEXTS), { ergon, ergonId: "C1", number: 1 });
  const before = run(["active", "--root", root]);
  assert.equal(before.code, 0);
  assert.equal(before.stdout, "ergon: C1 | C1-demo | not started | - | _aitna/.ergon/C1-demo\n");
  run(["athlos", "C1", "--number", "1", "--step", "one", ...CLAUDE, "--root", root]);
  const athlos = run(["active", ...MACHINE, "--root", root]);
  assert.equal(athlos.stdout, `athlos: C1.1 | 1 | active | claude s1 m1 ${NEUTRAL} | _aitna/.ergon/C1-demo/1\n`);
});

test("a session in the main checkout has no active unit", () => {
  const root = project();
  write(root);
  assert.equal(activeUnit(root, TEXTS), null);
  assert.equal(run(["active", "--root", root]).stdout, `${TEXTS.active.none}\n`);
  const named = path.join(root, ".worktrees", "C999-other.1");
  fs.mkdirSync(path.join(named, "_aitna"), { recursive: true });
  fs.writeFileSync(path.join(named, "AGENTS.md"), "");
  assert.equal(activeUnit(named, TEXTS), null); // its ergon does not exist
});

// --------------------------------------------------------------------------------------
// a linked worktree sees the main checkout's ergons (ADR 0028 D11)
// --------------------------------------------------------------------------------------

test("a repository's common directory leads a worktree to the main checkout", { skip: !gitAvailable() }, () => {
  const main_ = tempDir("park-test-");
  fs.writeFileSync(path.join(main_, "AGENTS.md"), "# agents\n");
  fs.mkdirSync(path.join(main_, "_aitna"));
  fs.writeFileSync(path.join(main_, "_aitna", ".akmon.toml"), "");
  git(main_, ["init", "-q"]);
  const linked = path.join(main_, ".worktrees", "C1-demo.1");
  git(main_, ["worktree", "add", "-q", "--orphan", "-b", "feat", linked]);
  assert.equal(gitCommonRoot(main_), main_);
  assert.equal(gitCommonRoot(linked), main_);
  assert.equal(ergonRoot(linked), path.join(main_, "_aitna", ".ergon"));
  // an ergon written from the worktree lands in the main checkout, and both see it
  const wrote = run(["write", "C2", "--name", "x", "--goal", "g", "--next", "n", "--root", linked]);
  assert.equal(wrote.code, 0);
  assert.ok(fs.statSync(path.join(main_, "_aitna", ".ergon", "C2-x", "PARK.md")).isFile());
  assert.ok(!fs.existsSync(path.join(linked, "_aitna", ".ergon")));
  assert.ok(run(["list", "--root", linked]).stdout.startsWith("C2 | x | parked"));
  assert.ok(run(["list", "--root", main_]).stdout.startsWith("C2 | x | parked"));
  assert.equal(run(["digest", "C2", "--root", linked]).code, 0);
});

/**
 * A repository with a linked worktree `<main>/.worktrees/C1-demo.1`: the ergons stay in the main checkout.
 * @returns {{main: string, linked: string, ergon: string}}
 */
function linkedCheckout() {
  const main_ = tempDir("park-test-");
  fs.writeFileSync(path.join(main_, "AGENTS.md"), "# agents\n");
  fs.mkdirSync(path.join(main_, "_aitna"));
  fs.writeFileSync(path.join(main_, "_aitna", ".akmon.toml"), "");
  git(main_, ["init", "-q"]);
  const linked = path.join(main_, ".worktrees", "C1-demo.1");
  git(main_, ["worktree", "add", "-q", "--orphan", "-b", "feat", linked]);
  return { main: main_, linked, ergon: path.join(main_, "_aitna", ".ergon") };
}

test(
  "a path inside the root is printed from it; every command of a linked worktree prints the ergons as they are",
  { skip: !gitAvailable() },
  () => {
    const { linked, ergon: layer } = linkedCheckout();
    const empty = run(["list", "--root", linked]);
    assert.equal(empty.stdout, `no ergons in ${layer}\n`);
    const missing = run(["unpark", "C9", "--root", linked]);
    assert.equal(missing.stderr, `error: no ergon with id C9 under ${layer}; ergons: none\n`);
    const wrote = run(["write", "C183", "--name", "park-helper", "--goal", "g", "--next", "n", "--root", linked]);
    const ergon = path.join(layer, "C183-park-helper");
    assert.equal(wrote.stdout, `${ergon}\n`);
    assert.ok(readUtf8(path.join(ergon, "RESUME.md")).includes(`1. Read \`${path.join(ergon, "PARK.md")}\`.`));
    const again = run(["unpark", "C9", "--root", linked]);
    assert.equal(again.stderr, `error: no ergon with id C9 under ${layer}; ergons: C183-park-helper\n`);
    const cut = run(["digest", "C183", "--cap", "40", "--root", linked]);
    assert.ok(cut.stdout.endsWith(`more lines in ${path.join(ergon, "PARK.md")}\n`), cut.stdout);
    const closed = run(["close", "C183", "--root", linked]);
    assert.equal(closed.stdout, `${path.join(layer, ".closed", "C183-park-helper")}\n`);
  },
);

test("the athlos and active commands of a linked worktree print the folder as it is", { skip: !gitAvailable() }, () => {
  const { main: main_, linked, ergon } = linkedCheckout();
  ergonWithPlan(main_);
  const athlos = run(["athlos", "C1", "--number", "1", "--step", "first", ...CLAUDE, "--root", linked]);
  const folder = path.join(ergon, "C1-demo", "1");
  assert.equal(athlos.code, 0);
  assert.equal(athlos.stdout, `${folder}\n`);
  const active = run(["active", ...MACHINE, "--root", linked]);
  assert.equal(active.stdout, `athlos: C1.1 | 1 | active | claude s1 m1 ${NEUTRAL} | ${folder}\n`);
});

test("a path inside the root is printed from it, with no dots", () => {
  const root = project();
  assert.equal(write(root).stdout, "_aitna/.ergon/C183-park-helper\n");
  const cut = run(["digest", "C183", "--cap", "40", "--root", root]);
  assert.ok(cut.stdout.endsWith("more lines in _aitna/.ergon/C183-park-helper/PARK.md\n"), cut.stdout);
  assert.ok(!cut.stdout.includes(".."));
});

// --------------------------------------------------------------------------------------
// project root
// --------------------------------------------------------------------------------------

/**
 * Run `body` with the working directory changed to `directory`, restoring it after.
 * @param {string} directory
 * @param {() => void} body
 */
function inDirectory(directory, body) {
  const before = process.cwd();
  process.chdir(directory);
  try {
    body();
  } finally {
    process.chdir(before);
  }
}

for (const argv of [
  ["list"],
  ["write", "C1", "--name", "n", "--goal", "g", "--next", "x"],
  ["unpark", "C1"],
  ["active"],
]) {
  test(`no project root is refused and nothing is written: ${argv[0]}`, () => {
    const work = path.join(tempDir("park-test-"), "work");
    fs.mkdirSync(work);
    inDirectory(work, () => {
      const result = run(argv, work);
      assert.equal(result.code, 1);
      assert.ok(result.stderr.startsWith("error: [akmon] no project root at or above "));
      assert.equal(result.stderr.split("\n").length - 1, 1);
    });
    assert.deepEqual(fs.readdirSync(work), []);
  });
}

test("an explicit root that is not a directory is refused", () => {
  const missing = path.join(tempDir("park-test-"), "missing");
  const result = run(["list", "--root", missing]);
  assert.equal(result.code, 1);
  assert.equal(result.stderr, `error: --root ${missing} is not a directory\n`);
});

test("the project root is found by walking up", () => {
  const root = project();
  const nested = path.join(root, "src", "deep");
  fs.mkdirSync(nested, { recursive: true });
  const result = run(["write", "C1", "--name", "n", "--goal", "g", "--next", "x"], nested);
  assert.equal(result.code, 0);
  assert.equal(result.stdout, "_aitna/.ergon/C1-n\n");
  assert.ok(fs.statSync(path.join(root, "_aitna", ".ergon", "C1-n", "PARK.md")).isFile());
  assert.ok(!fs.existsSync(path.join(nested, "_aitna")));
});

test("--project-root is an alias of --root", () => {
  const root = project();
  const result = run(["list", "--project-root", root]);
  assert.equal(result.code, 0);
  assert.equal(result.stdout, "no ergons in _aitna/.ergon\n");
});

// --------------------------------------------------------------------------------------
// the command line (argparse-shaped: DV12)
// --------------------------------------------------------------------------------------

const COMMAND_CHOICES =
  "'write', 'unpark', 'digest', 'list', 'hold', 'release', 'athlos', 'active', 'worktrees', 'close', 'export', 'local-id'";

test("a usage error is one line on stderr and exit 2", () => {
  for (const [argv, message] of /** @type {[string[], string][]} */ ([
    [[], "the following arguments are required: command"],
    [["bogus"], `argument command: invalid choice: 'bogus' (choose from ${COMMAND_CHOICES})`],
    [["write", "C1"], "the following arguments are required: --name, --goal, --next"],
    [["write", "--name", "n", "--goal", "g", "--next", "x"], "the following arguments are required: id"],
    [["unpark"], "the following arguments are required: id"],
    [["unpark", "C1", "C2"], "unrecognized arguments: C2"],
    [["list", "--bogus"], "unrecognized arguments: --bogus"],
    [["list", "stray"], "unrecognized arguments: stray"],
    [["list", "--plan"], "argument --plan: expected one argument"],
    [["list", "--plan", "--state", "x"], "argument --plan: expected one argument"],
    [["list", "--closed=x"], "argument --closed: ignored explicit argument 'x'"],
    [["digest", "C1", "--cap", "abc"], "argument --cap: invalid int value: 'abc'"],
    [["hold"], "the following arguments are required: id"],
    [["hold", "C1", "--number", "abc"], "argument --number: invalid int value: 'abc'"],
    [["release"], "the following arguments are required: id"],
    [["athlos", "C1"], "the following arguments are required: --number"],
    [["athlos"], "the following arguments are required: id, --number"],
    [["active", "C1"], "unrecognized arguments: C1"],
    [["close"], "the following arguments are required: id"],
    [["export", "C1"], "the following arguments are required: --out"],
    [["local-id", "--harness", "claude"], "unrecognized arguments: --harness claude"],
    [["--root", "x", "list"], `argument command: invalid choice: '--root' (choose from ${COMMAND_CHOICES})`],
  ])) {
    const result = run(argv);
    assert.equal(result.code, 2, argv.join(" "));
    assert.equal(result.stderr, `park.mjs: error: ${message}\n`);
    assert.equal(result.stdout, "");
  }
});

test("the surplus of a usage error keeps the order of the command line", () => {
  const result = run(["write", "C1", "--name", "n", "--goal", "g", "--next", "x", "--branch", "b", "--peer", "p q"]);
  assert.equal(result.code, 2);
  assert.equal(result.stderr, "park.mjs: error: unrecognized arguments: --branch b --peer p q\n");
  assert.equal(
    run(["unpark", "C1", "--bogus", "C2", "-x", "C3"]).stderr,
    "park.mjs: error: unrecognized arguments: --bogus C2 -x C3\n",
  );
});

test("--help prints the usage and exits 0", () => {
  for (const argv of [["-h"], ["--help"], ["write", "-h"], ["list", "--help"], ["hold", "--help"], ["export", "-h"]]) {
    const result = run(argv);
    assert.equal(result.code, 0, argv.join(" "));
    assert.ok(result.stdout.startsWith("usage: park.mjs"));
  }
});

test("options are accepted before and after the id, and as --flag=value", () => {
  const root = project();
  const argv = ["write", "--name=n", "--goal", "g", "C1", "--next", "x", `--root=${root}`];
  const result = run(argv);
  assert.equal(result.code, 0);
  assert.equal(result.stdout, "_aitna/.ergon/C1-n\n");
});

test("a value that looks like an option is taken as argparse takes it", () => {
  const root = project();
  // `-1` (a negative number) and `- two words` (a space) are values; `-x` is an option.
  const ok = run(["write", "C1", "--name", "n", "--goal", "- two words", "--next", "-1", "--root", root]);
  assert.equal(ok.code, 0);
  const { fields, body } = readNote(ergonPath(root, "C1-n"), TEXTS);
  assert.equal(fields.nextAction, "-1");
  assert.equal(body.goal, "- two words");
  const bad = run(["write", "C2", "--name", "n", "--goal", "g", "--next", "-x", "--root", root]);
  assert.equal(bad.code, 2);
  assert.equal(bad.stderr, "park.mjs: error: argument --next: expected one argument\n");
});

test("a repeated option appends in order, a repeated scalar keeps the last", () => {
  const root = project();
  const flags = ["--owned-path", "b", "--owned-path", "a", "--plan", "A1", "--plan", "A2"];
  assert.equal(write(root, flags).code, 0);
  const { fields } = readNote(ergonPath(root), TEXTS);
  assert.deepEqual(fields.ownedPaths, ["b", "a"]);
  assert.equal(fields.plan, "A2");
});

test("--machine names the machine the session acts as, for the holder and for the staleness", () => {
  const root = project();
  write(root);
  run(["hold", "C183", "--harness", "claude", "--session-id", "s1", "--machine", "laptop", "--root", root]);
  const lease = readLease(ergonPath(root), TEXTS);
  assert.equal(lease?.holder.machine, "laptop");
  // the same machine name: the live lease is this session's, so the ergon is active
  assert.ok(run(["list", "--machine", "laptop", "--root", root]).stdout.includes("| active |"));
  // another machine's view of the same lease: stale at once
  assert.ok(run(["list", "--machine", "desktop", "--root", root]).stdout.includes("| parked |"));
  const stale = run(["hold", "C183", "--harness", "codex", "--machine", "desktop", "--root", root]);
  assert.ok(stale.stderr.includes("whose lease is stale"));
});

test("ergon ids sort by code point, not by locale or length", () => {
  const root = project();
  for (const [ergonId, name] of [
    ["C100", "a"],
    ["C20", "b"],
    ["A1", "c"],
    ["_T2", "d"],
  ]) {
    assert.equal(write(root, [], { ergonId, name }).code, 0);
  }
  const ids = run(["list", "--root", root])
    .stdout.split("\n")
    .slice(0, -1)
    .map((line) => line.split(" | ")[0]);
  assert.deepEqual(ids, ["A1", "C100", "C20", "_T2"]);
});

// --------------------------------------------------------------------------------------
// worktrees: every worktree git knows and every backup branch, by state (C190, D-C190-WORKTREES)
// --------------------------------------------------------------------------------------

/** @typedef {import("./park.mjs").WorktreeRow} WorktreeRow */

const STATES = TEXTS.worktrees.states;
const ERGON_ID = "C186";
const ERGON_NAME = "C186-holders-units";
const PENDING_SUBJECT = 'pending: add the "pending" file';

/**
 * @param {number} number
 * @returns {string}
 */
function athlosBranch(number) {
  return `_aitna/${ERGON_NAME}.${number}`;
}

/**
 * @param {string} main_
 * @param {number} number
 * @returns {string}
 */
function athlosFolderOf(main_, number) {
  return path.join(main_, ".worktrees", `${ERGON_NAME}.${number}`);
}

/**
 * Run git as the test's author and return what it prints.
 * @param {string} cwd
 * @param {string[]} args
 * @returns {string}
 */
function gitAs(cwd, args) {
  const flags = ["-c", "user.email=t@example.com", "-c", "user.name=t", "-c", "commit.gpgsign=false"];
  return execFileSync("git", [...flags, ...args], {
    cwd,
    encoding: "utf8",
    stdio: ["ignore", "pipe", "ignore"],
  }).trim();
}

/**
 * @param {string} folder
 * @param {Record<string, string>} files
 * @param {string} message
 */
function commitFiles(folder, files, message) {
  for (const [name, text] of Object.entries(files)) {
    fs.writeFileSync(path.join(folder, name), text);
    gitAs(folder, ["add", name]);
  }
  gitAs(folder, ["commit", "-m", message]);
}

/**
 * @param {string} main_
 * @param {number} number
 * @param {Record<string, string>} files
 * @param {string} message
 * @returns {string} the worktree's folder
 */
function addAthlosWorktree(main_, number, files, message) {
  const folder = athlosFolderOf(main_, number);
  gitAs(main_, ["worktree", "add", "-b", athlosBranch(number), folder]);
  commitFiles(folder, files, message);
  return folder;
}

/**
 * The owner's carry: one squash commit on main; the branch stays unmerged in git's eyes.
 * @param {string} main_
 * @param {number} number
 */
function carryBySquash(main_, number) {
  gitAs(main_, ["merge", "--squash", athlosBranch(number)]);
  gitAs(main_, ["commit", "-m", `carry ${number}`]);
}

/**
 * An athlos file written straight from the types, optionally naming a branch.
 * @param {string} ergon
 * @param {number} number
 * @param {string} [branch]
 * @returns {string} the athlos folder
 */
function athlosNote(ergon, number, branch = "") {
  const folder = path.join(ergon, String(number));
  const header = parkFields({
    id: ERGON_ID,
    name: "holders-units",
    nextAction: "x",
    athlos: `${ERGON_ID}.${number}`,
    branch,
  });
  writeAthlosDoc(folder, { header, steps: [], done: false }, TEXTS);
  return folder;
}

/**
 * A main checkout with one worktree or branch of every kind a `worktrees` row can be: 1 carried by a
 * squash, 2 ready (four paths, a quote in its subject), 3 dirty, 4 carried but held by a live lease,
 * 5 a backup carried by a squash, 6 a backup not carried (its note names the branch), 7 carried by a
 * merge commit, and a harness worktree.
 * @returns {string}
 */
function world() {
  const main_ = tempDir("park-world-");
  fs.writeFileSync(path.join(main_, "AGENTS.md"), "# agents\n");
  fs.mkdirSync(path.join(main_, "_aitna"));
  fs.writeFileSync(path.join(main_, "_aitna", ".akmon.toml"), "");
  fs.writeFileSync(path.join(main_, ".gitignore"), ".worktrees/\n_aitna/\n.claude/\n");
  gitAs(main_, ["init", "-b", "main"]);
  gitAs(main_, ["add", "AGENTS.md", ".gitignore"]);
  gitAs(main_, ["commit", "-m", "base"]);
  addAthlosWorktree(main_, 1, { "squashed.txt": "one" }, "one");
  addAthlosWorktree(main_, 2, { "pending.txt": "two", "p1.txt": "1", "p2.txt": "2", "p3.txt": "3" }, PENDING_SUBJECT);
  const dirty = addAthlosWorktree(main_, 3, { "dirty.txt": "three" }, "three");
  fs.writeFileSync(path.join(dirty, "scratch.txt"), "untracked");
  const held = addAthlosWorktree(main_, 4, { "held.txt": "four" }, "four");
  const gone = addAthlosWorktree(main_, 5, { "gone.txt": "five" }, "five");
  gitAs(main_, ["worktree", "remove", gone]);
  const behind = addAthlosWorktree(main_, 6, { "behind.txt": "six" }, "six");
  gitAs(main_, ["worktree", "remove", behind]);
  addAthlosWorktree(main_, 7, { "merged.txt": "seven" }, "seven");
  const harness = path.join(main_, ".claude", "worktrees", "agent-x");
  gitAs(main_, ["worktree", "add", "-b", "worktree-agent-x", harness]);
  commitFiles(harness, { "harness.txt": "h" }, "harness work");
  for (const number of [1, 4, 5]) {
    carryBySquash(main_, number);
  }
  gitAs(main_, ["merge", "--no-ff", "-m", "merge seven", athlosBranch(7)]);
  const ergon = path.join(ergonRoot(main_), ERGON_NAME);
  fs.mkdirSync(ergon, { recursive: true });
  const folder = athlosNote(ergon, 4);
  acquireLease(
    folder,
    { harness: "claude", sessionId: "s1", machine: "m1", worktree: held },
    TEXTS,
    context(Date.now() / 1000, "m1"),
  );
  athlosNote(ergon, 6, athlosBranch(6));
  return main_;
}

/**
 * @param {string} main_
 * @returns {Map<string, WorktreeRow>} the rows by branch
 */
function worldRows(main_) {
  const rows = listWorktrees(main_, TEXTS, context(Date.now() / 1000, "m1"));
  return new Map(rows.map((row) => [row.branch, row]));
}

/**
 * @param {string} main_
 * @param {string} branch
 * @returns {WorktreeRow}
 */
function rowOf(main_, branch) {
  const row = worldRows(main_).get(branch);
  assert.ok(row !== undefined, `no row for ${branch}`);
  return row;
}

/**
 * @param {string} main_
 * @param {string[]} [target]
 * @returns {{code: number, stdout: string, stderr: string}}
 */
function worktreesOut(main_, target = []) {
  return run(["worktrees", ...target, ...MACHINE, "--root", main_]);
}

/**
 * @param {string} text
 * @returns {string}
 */
function lastLine(text) {
  return text.replace(/\n$/, "").split("\n").pop() ?? "";
}

test("the owner's checkout comes first and backup branches last", { skip: !gitAvailable() }, () => {
  const main_ = world();
  const rows = listWorktrees(main_, TEXTS, context(Date.now() / 1000, "m1"));
  assert.equal(rows[0].kind, "main");
  assert.equal(rows[0].path, main_);
  assert.equal(rows[0].state, STATES.main);
  assert.deepEqual(
    rows.slice(-2).map((row) => [row.branch, row.kind]),
    [
      [athlosBranch(5), "branch-only"],
      [athlosBranch(6), "branch-only"],
    ],
  );
});

test("a branch carried by a squash is carried though git calls it unmerged", { skip: !gitAvailable() }, () => {
  const main_ = world();
  const row = rowOf(main_, athlosBranch(1));
  assert.equal(gitAs(main_, ["branch", "--merged", "main", "--list", athlosBranch(1)]), "");
  assert.deepEqual([row.kind, row.state, row.carried, row.removable], ["athlos", STATES.carried, true, true]);
  assert.deepEqual([row.clean, row.ahead, row.differing], [true, 1, []]);
  assert.equal(row.shown, `${ERGON_NAME}.1`);
});

test("a branch merged by a merge commit is carried with nothing ahead", { skip: !gitAvailable() }, () => {
  const row = rowOf(world(), athlosBranch(7));
  assert.deepEqual([row.state, row.carried, row.ahead, row.removable], [STATES.carried, true, 0, true]);
});

test("a clean branch beyond the owner's and not carried is ready with its subject", { skip: !gitAvailable() }, () => {
  const row = rowOf(world(), athlosBranch(2));
  assert.deepEqual([row.state, row.carried, row.ahead, row.removable], [STATES.ready, false, 1, false]);
  assert.deepEqual(row.differing, ["p1.txt", "p2.txt", "p3.txt", "pending.txt"]);
  assert.equal(row.subject, PENDING_SUBJECT);
});

test("a dirty worktree is working and untracked files count", { skip: !gitAvailable() }, () => {
  const row = rowOf(world(), athlosBranch(3));
  assert.deepEqual([row.state, row.clean, row.carried, row.removable], [STATES.working, false, false, false]);
  assert.equal(row.subject, "");
});

test("a live lease on the worktree holds it whatever its content", { skip: !gitAvailable() }, () => {
  const row = rowOf(world(), athlosBranch(4));
  assert.ok(row.carried);
  assert.deepEqual(
    [row.state, row.ergon, row.athlos, row.removable],
    [STATES.working, ERGON_ID, `${ERGON_ID}.4`, false],
  );
});

test("a stale lease holds nothing", { skip: !gitAvailable() }, () => {
  const main_ = world();
  const folder = path.join(ergonRoot(main_), ERGON_NAME, "4");
  fs.writeFileSync(
    path.join(folder, "HOLDER"),
    `---\nharness: claude\nsession: s1\nmachine: m1\nworktree: ${athlosFolderOf(main_, 4)}\nwritten: 2000-01-01T00:00:00Z\n---\n`,
  );
  const row = rowOf(main_, athlosBranch(4));
  assert.deepEqual([row.state, row.removable], [STATES.carried, true]);
});

test("a harness worktree is never removable", { skip: !gitAvailable() }, () => {
  const main_ = world();
  const row = rowOf(main_, "worktree-agent-x");
  assert.deepEqual([row.kind, row.state, row.removable], ["harness", STATES.harness, false]);
  assert.equal(row.shown, path.join(main_, ".claude", "worktrees", "agent-x"));
});

test("a branch with no worktree is a backup and its note names its athlos", { skip: !gitAvailable() }, () => {
  const main_ = world();
  const carried = rowOf(main_, athlosBranch(5));
  const behind = rowOf(main_, athlosBranch(6));
  assert.deepEqual(
    [carried.kind, carried.path, carried.clean, carried.state],
    ["branch-only", "", null, STATES.backup],
  );
  assert.ok(carried.removable);
  assert.deepEqual([behind.state, behind.removable, behind.carried], [STATES.not_carried_backup, false, false]);
  assert.deepEqual([behind.ergon, behind.athlos], [ERGON_ID, `${ERGON_ID}.6`]);
});

test("a backup held by a live lease is working", { skip: !gitAvailable() }, () => {
  const main_ = world();
  const folder = path.join(ergonRoot(main_), ERGON_NAME, "6");
  acquireLease(
    folder,
    { harness: "claude", sessionId: "s9", machine: "m1", worktree: "/elsewhere" },
    TEXTS,
    context(Date.now() / 1000, "m1"),
  );
  assert.equal(rowOf(main_, athlosBranch(6)).state, STATES.working);
});

test("the table and the commands for the ready and the removable", { skip: !gitAvailable() }, () => {
  const main_ = world();
  const { code, stdout } = worktreesOut(main_);
  assert.equal(code, 0);
  const [table, carry, removal] = stdout.replace(/\n$/, "").split("\n\n");
  const lines = table.split("\n");
  assert.deepEqual(
    lines[0].split(" | ").map((cell) => cell.trim()),
    TEXTS.worktrees.columns,
  );
  assert.equal(lines.length, 1 + 9);
  assert.equal(new Set(lines.map((line) => line.indexOf(" | "))).size, 1); // the columns are aligned
  assert.deepEqual(carry.split("\n"), [
    `cd ${main_}`,
    `git merge --squash ${athlosBranch(2)}`,
    'git commit -m "pending: add the \\"pending\\" file"',
  ]);
  assert.deepEqual(removal.split("\n"), [
    `git worktree remove ${athlosFolderOf(main_, 1)}`,
    `git worktree remove ${athlosFolderOf(main_, 7)}`,
    `git branch -D ${athlosBranch(5)}`,
  ]);
});

test("worktrees reads and changes nothing", { skip: !gitAvailable() }, () => {
  const main_ = world();
  const snapshot = () => [
    gitAs(main_, ["for-each-ref"]),
    gitAs(main_, ["worktree", "list"]),
    gitAs(main_, ["status", "--porcelain"]),
  ];
  const before = snapshot();
  worktreesOut(main_);
  worktreesOut(main_, [athlosBranch(2)]);
  assert.deepEqual(snapshot(), before);
});

test("a branch target prints its row and a carried verdict with exit zero", { skip: !gitAvailable() }, () => {
  const main_ = world();
  for (const target of [athlosBranch(1), `${ERGON_NAME}.1`]) {
    const { code, stdout } = worktreesOut(main_, [target]);
    const lines = stdout.replace(/\n$/, "").split("\n");
    assert.equal(code, 0);
    assert.equal(lines.length, 3); // the header, the row and the verdict
    assert.ok(lines[1].startsWith(`${ERGON_NAME}.1 `));
    assert.equal(lines[2], `${athlosBranch(1)}: carried`);
  }
});

test("an athlos key names the row of its unit", { skip: !gitAvailable() }, () => {
  const { code, stdout } = worktreesOut(world(), [`${ERGON_ID}.4`]);
  assert.equal(code, 0);
  assert.equal(lastLine(stdout), `${athlosBranch(4)}: carried`);
});

test("a branch not carried names the first three paths that differ and exits one", { skip: !gitAvailable() }, () => {
  const main_ = world();
  const ready = worktreesOut(main_, [athlosBranch(2)]);
  assert.equal(ready.code, 1);
  assert.equal(lastLine(ready.stdout), `${athlosBranch(2)}: not carried — p1.txt, p2.txt, p3.txt, …`);
  const dirty = worktreesOut(main_, [athlosBranch(3)]);
  assert.equal(dirty.code, 1);
  assert.equal(lastLine(dirty.stdout), `${athlosBranch(3)}: not carried — dirty.txt`);
});

test("a missing branch is said and exits one", { skip: !gitAvailable() }, () => {
  const { code, stdout } = worktreesOut(world(), ["nope"]);
  assert.deepEqual([code, stdout], [1, "nope: no such branch\n"]);
});

test("the verdict follows the content after the owner changes a carried path again", { skip: !gitAvailable() }, () => {
  const main_ = world();
  fs.writeFileSync(path.join(main_, "squashed.txt"), "changed again");
  gitAs(main_, ["commit", "-am", "owner edits it"]);
  const { code, stdout } = worktreesOut(main_, [athlosBranch(1)]);
  assert.equal(code, 1);
  assert.ok(stdout.replace(/\n$/, "").endsWith(`${athlosBranch(1)}: not carried — squashed.txt`));
});

test("worktrees outside a repository is refused in one line", () => {
  const root = project();
  const { code, stderr } = run(["worktrees", "--root", root]);
  assert.equal(code, 1);
  assert.equal(stderr, `error: ${root} is not in a git repository, so there are no worktrees to list\n`);
});

test("a main checkout alone lists one row and no commands", { skip: !gitAvailable() }, () => {
  const root = project();
  gitAs(root, ["init", "-b", "main"]);
  gitAs(root, ["add", "AGENTS.md"]);
  gitAs(root, ["commit", "-m", "base"]);
  const { code, stdout } = worktreesOut(root);
  const lines = stdout.replace(/\n$/, "").split("\n");
  assert.equal(code, 0);
  assert.equal(lines.length, 2);
  assert.equal(lines[1].split(" | ")[0].trim(), root);
  assert.ok(lines[1].endsWith(` | ${STATES.main}`));
});

test("the porcelain listing is parsed in git order and a bare entry is marked", () => {
  const text =
    "worktree /srv/main\nHEAD aaa\nbranch refs/heads/main\n\n" +
    "worktree /srv/main/.worktrees/x.1\nHEAD bbb\nbranch refs/heads/_aitna/C1-x.1\nlocked\n\n" +
    "worktree /srv/detached\nHEAD ccc\ndetached\n\n" +
    "worktree /srv/bare.git\nbare\n";
  assert.deepEqual(parseWorktreeList(text), [
    { path: "/srv/main", head: "aaa", branch: "main", bare: false },
    { path: "/srv/main/.worktrees/x.1", head: "bbb", branch: "_aitna/C1-x.1", bare: false },
    { path: "/srv/detached", head: "ccc", branch: "", bare: false },
    { path: "/srv/bare.git", head: "", branch: "", bare: true },
  ]);
});

test("an athlos branch is in the namespace and names its ergon and number", () => {
  assert.deepEqual(branchUnit("_aitna/C186-holders-units.1"), { ergonId: "C186", number: 1 });
  assert.deepEqual(branchUnit("_aitna/_T3-local-thing.12"), { ergonId: "_T3", number: 12 });
  for (const other of [
    "_aitna/C186-holders-units",
    "_aitna/C186-holders-units.x",
    "feature/C186-holders-units.1",
    "main",
  ]) {
    assert.equal(branchUnit(other), null, other);
  }
});

/**
 * A row to build tables and commands from, with `changes` laid over it.
 * @param {Partial<WorktreeRow>} [changes]
 * @returns {WorktreeRow}
 */
function syntheticRow(changes = {}) {
  return {
    path: "/srv/a b",
    shown: "a b",
    branch: "_aitna/C1-x.1",
    kind: "athlos",
    ergon: "",
    athlos: "",
    clean: true,
    ahead: 2,
    ageSeconds: 0,
    carried: true,
    differing: [],
    state: STATES.carried,
    removable: true,
    subject: "",
    ...changes,
  };
}

test("the table shows short relative ages and the empty cell for what is unknown", () => {
  const rows = [
    syntheticRow({ ageSeconds: 59 * 60 + 59 }),
    syntheticRow({ ageSeconds: 60 * 60 }),
    syntheticRow({ ageSeconds: 24 * 3600 - 1 }),
    syntheticRow({ ageSeconds: 24 * 3600 }),
    syntheticRow({ ageSeconds: null, ahead: null, clean: null, shown: "", path: "", kind: "branch-only" }),
  ];
  const lines = formatWorktrees(rows, TEXTS);
  assert.deepEqual(
    lines.slice(1).map((line) => line.split(" | ")[7].trim()),
    ["59m", "1h", "23h", "1d", "-"],
  );
  const last = lines[lines.length - 1].split(" | ").map((cell) => cell.trim());
  assert.deepEqual([last[0], last[5], last[6]], ["-", "-", "-"]);
});

test("the commands are quoted for the shell and the message for double quotes", () => {
  const ready = syntheticRow({
    state: STATES.ready,
    removable: false,
    carried: false,
    subject: 'fix `a` and "b" $HOME \\ done',
  });
  assert.deepEqual(carryCommands([ready], "/srv/the main", TEXTS), [
    [
      "cd '/srv/the main'",
      "git merge --squash _aitna/C1-x.1",
      'git commit -m "fix \\`a\\` and \\"b\\" \\$HOME \\\\ done"',
    ],
  ]);
  assert.deepEqual(removalCommands([syntheticRow(), syntheticRow({ path: "", branch: "_aitna/it's" })], TEXTS), [
    "git worktree remove '/srv/a b'",
    `git branch -D '_aitna/it'"'"'s'`,
  ]);
});
