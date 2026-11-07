/**
 * node:test for `js/tools/park/park.mjs` — the twin of `meta/tests/test_park.py`: the note, the kit, the
 * lease, the jobs and the derived states, the commands. The byte-level spec shared by both
 * implementations is the `tools/park-*` scenarios of `meta/conformance/scenarios`, run by
 * `runner.py --impl node --area tools`.
 */

import { test } from "node:test";
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
  exportKit,
  findClosedKit,
  findKit,
  formatJob,
  formatSummary,
  gitBranch,
  gitRevisions,
  gitUncommittedPaths,
  holderIdentified,
  holderLabel,
  holderSameAs,
  jobSlug,
  kitState,
  leaseIsStale,
  listKits,
  main,
  mergeSessions,
  nextLocalId,
  parkBody,
  parkFields,
  parseHeader,
  parseJobDoc,
  parseJobLine,
  parseLease,
  parseNote,
  parsePlan,
  readLease,
  readJobDoc,
  readNote,
  readPendingSessions,
  releaseLease,
  rememberHolder,
  renderHeader,
  renderJobDoc,
  renderLease,
  renderNote,
  sharedPathWarnings,
  unitState,
  worktreeUnit,
  writeJobDoc,
  writeKit,
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

## Jobs

- C1.1 · Build core · tasks C1 · paths src/a, docs · result: core built
- C1.2 · Write docs · after C1.1 · paths docs/x · result: docs done
- C1.3 · Extra · paths other · harness claude
`;

const FULL_FIELDS = parkFields({
  id: "C183",
  name: "park-helper",
  nextAction: "Twin it: JS | Python",
  plan: "A59",
  job: "C183.2",
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

// A directory that is no git repository and holds no project: the working directory the commands run in.
const NEUTRAL = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), "park-neutral-")));

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
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), "park-test-")));
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
function kitPath(root, name = "C183-park-helper") {
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
 * @param {{kitId?: string, name?: string}} [who]
 * @returns {{code: number, stdout: string, stderr: string}}
 */
function write(root, extra = [], { kitId = "C183", name = "park-helper" } = {}) {
  const argv = ["write", kitId, "--name", name, "--goal", "Build the helper", "--next", "Twin it"];
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
 * A kit with a plan of three jobs (`PLAN_TEXT`), written through `write`.
 * @param {string} root
 * @returns {string} the kit folder
 */
function kitWithPlan(root) {
  const kit = kitPath(root, "C1-demo");
  fs.mkdirSync(kit, { recursive: true });
  fs.writeFileSync(path.join(kit, "PLAN.md"), PLAN_TEXT);
  return kit;
}

/**
 * @param {string} root
 * @param {number} count
 * @returns {string}
 */
function kitWithAnswers(root, count) {
  const body = parkBody({
    goal: "Goal line",
    answers: Array.from({ length: count }, (_value, number) => `answer ${String(number).padStart(2, "0")}`),
  });
  const fields = parkFields({ id: "C9", name: "long", nextAction: "Next" });
  return writeKit(fields, body, root, TEXTS, root);
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
    "job",
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

test("a retired peers list with items is ignored too, and the kit is listed", () => {
  // A retired list key takes its items with it: they are skipped, not read as the list above.
  const old =
    "---\nstate: parked\nid: C1\nname: old\nnext: x\nsessions:\n  - claude|s-1|laptop\n" +
    "peers:\n  - sibling session on B8\n---\n\n## Goal\n\ng\n";
  const fields = parseHeader(old, "PARK.md", TEXTS);
  assert.deepEqual(fields.sessions, [{ harness: "claude", sessionId: "s-1", machine: "laptop" }]);
  const root = project();
  const kit = kitPath(root, "C1-old");
  fs.mkdirSync(kit, { recursive: true });
  fs.writeFileSync(path.join(kit, "PARK.md"), old);
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
  [{ job: "C183" }, "job C183 is not a job id"],
  [{ job: "C183.x" }, "job C183.x is not a job id"],
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
  ["---\nid: C1\nname: n\nnext: x\njob: C1\n---\n", "job C1 is not a job id"],
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
// write: the kit, the resume prompt, no index
// --------------------------------------------------------------------------------------

test("write creates the kit with both files and a note that says when it was written", () => {
  const root = project();
  const result = write(root, ["--plan", "A59", "--decision", "D-X"]);
  assert.equal(result.code, 0);
  assert.equal(result.stdout, "_aitna/.ergon/C183-park-helper\n");
  const kit = kitPath(root);
  const { fields, body } = parseNote(readUtf8(path.join(kit, "PARK.md")), "PARK.md", TEXTS);
  assert.deepEqual([fields.id, fields.name, fields.plan], ["C183", "park-helper", "A59"]);
  assert.match(fields.written, /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$/);
  assert.equal(body.goal, "Build the helper");
  assert.deepEqual(body.decisions, ["D-X"]);
  assert.ok(fs.statSync(path.join(kit, "RESUME.md")).isFile());
  assert.deepEqual(fs.readdirSync(kit).sort(), ["PARK.md", "RESUME.md"]);
});

test("write reads the branch and the revisions from git in the working directory", () => {
  const root = project();
  const kit = writeKit(
    parkFields({ id: "C9", name: "git", nextAction: "x" }),
    parkBody({ goal: "g" }),
    root,
    TEXTS,
    NEUTRAL,
  );
  const { fields } = readNote(kit, TEXTS);
  assert.deepEqual([fields.branch, fields.revisions], ["", []]);
  const here = path.dirname(fileURLToPath(import.meta.url));
  const inRepo = writeKit(
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
  const { fields, body } = readNote(kitPath(root), TEXTS);
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
  assert.ok(!fs.existsSync(kitPath(root)));
});

test("the resume prompt is harness-neutral and dateless", () => {
  const root = project();
  write(root, ["--decision", "D-X", "--plan", "A59"]);
  const resume = readUtf8(path.join(kitPath(root), "RESUME.md"));
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

test("a dev-root pointer moves the kit", () => {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), "park-test-")));
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
  assert.ok(!fs.existsSync(kitPath(root)));
  assert.deepEqual(
    walk(root).filter((file) => file.endsWith(".tmp")),
    [],
  );
});

test("a failure keeps an existing kit and removes only the temp files", (t) => {
  const root = project();
  write(root);
  const kit = kitPath(root);
  /** @returns {Map<string, string>} */
  const snapshot = () => new Map(fs.readdirSync(kit).map((name) => [name, readUtf8(path.join(kit, name))]));
  const before = snapshot();
  t.mock.method(fs, "renameSync", () => {
    throw new Error("disk says no");
  });
  assert.throws(() => write(root, ["--decision", "D-NEW"]), /disk says no/);
  assert.deepEqual(snapshot(), before);
});

test("a kit with the id and another name is refused, live or closed", () => {
  const root = project();
  write(root);
  const result = write(root, [], { name: "renamed" });
  assert.equal(result.code, 1);
  assert.equal(
    result.stderr,
    "error: kit C183-park-helper already carries id C183; keep its name or retire it before writing renamed\n",
  );
  assert.ok(!fs.existsSync(kitPath(root, "C183-renamed")));
  run(["close", "C183", "--root", root]);
  const closed = write(root, [], { name: "renamed" });
  assert.equal(closed.code, 1);
  assert.ok(closed.stderr.includes("kit C183-park-helper already carries id C183"));
});

test("write refuses a bad id and a bad name before any file", () => {
  const root = project();
  const first = write(root, [], { kitId: "c183" });
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

test("local ids are accepted, and the next one is counted over the kits, live and closed", () => {
  const root = project();
  assert.equal(nextLocalId(root), "_T1");
  assert.equal(write(root, [], { kitId: "_T7", name: "scratch" }).code, 0);
  assert.ok(fs.statSync(kitPath(root, "_T7-scratch")).isDirectory());
  assert.equal(nextLocalId(root), "_T8");
  run(["close", "_T7", "--root", root]);
  assert.equal(nextLocalId(root), "_T8");
  write(root, [], { kitId: "C5", name: "typed" });
  write(root, [], { kitId: "_T2", name: "low" });
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
  fs.mkdirSync(kitPath(root, "_T2-a"), { recursive: true });
  assert.equal(nextLocalId(root), "_T13");
  fs.mkdirSync(kitPath(root, ".closed/_T20-gone"), { recursive: true });
  assert.equal(nextLocalId(root), "_T21");
  assert.deepEqual(fs.readFileSync(legacy), before);
});

test("the local-id command prints the next free id on one line and writes nothing", () => {
  const root = project();
  const first = run(["local-id", "--root", root]);
  assert.deepEqual([first.code, first.stdout, first.stderr], [0, "_T1\n", ""]);
  assert.ok(!fs.existsSync(path.join(root, "_aitna", ".ergon")));
  fs.mkdirSync(kitPath(root, "_T2-a"), { recursive: true });
  fs.mkdirSync(kitPath(root, ".closed/_T5-gone"), { recursive: true });
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
  const resume = readUtf8(path.join(kitPath(root), "RESUME.md"));
  assert.ok(result.stdout.startsWith(`${resume.replace(/\n+$/, "")}\n\npark C183-park-helper · active\n`));
  assert.ok(result.stdout.endsWith("Owner answers:\n- owner: go\n"));
  const lease = readLease(kitPath(root), TEXTS);
  assert.ok(lease !== null && holderSameAs(lease.holder, { ...CLAUDE_HOLDER, worktree: "" }));
  assert.equal(lease.holder.worktree, NEUTRAL);
  // the note itself carries no state: it is what write left
  assert.equal(readNote(kitPath(root), TEXTS).fields.plan, "A59");
});

test("unpark is refused while another session holds the kit, and renewed for the same one", () => {
  const root = project();
  write(root);
  assert.equal(run(["unpark", "C183", ...CLAUDE, "--root", root]).code, 0);
  assert.equal(run(["unpark", "C183", ...CLAUDE, "--root", root]).code, 0);
  const refused = run(["unpark", "C183", ...CODEX, "--root", root]);
  assert.equal(refused.code, 1);
  assert.ok(refused.stderr.startsWith("error: C183-park-helper is held by claude s1 m1 "));
  assert.ok(refused.stderr.includes("a stale lease is taken over only on the owner's word (--takeover)"));
});

test("unpark names the candidates when no kit matches", () => {
  const root = project();
  write(root);
  const result = run(["unpark", "C999", "--root", root]);
  assert.equal(result.code, 1);
  assert.equal(result.stderr, "error: no kit with id C999 under _aitna/.ergon; kits: C183-park-helper\n");
});

test("unpark with no kits at all says none", () => {
  const root = project();
  const result = run(["unpark", "C1", "--root", root]);
  assert.equal(result.code, 1);
  assert.equal(result.stderr, "error: no kit with id C1 under _aitna/.ergon; kits: none\n");
});

test("unpark names the kits when several carry the id", () => {
  const root = project();
  for (const name of ["C5-a", "C5-b", "C50-c"]) {
    fs.mkdirSync(kitPath(root, name), { recursive: true });
  }
  const result = run(["unpark", "C5", "--root", root]);
  assert.equal(result.code, 1);
  assert.equal(result.stderr, "error: several kits carry id C5 under _aitna/.ergon: C5-a, C5-b\n");
});

test("a refused unpark leaves no lease behind: the checks come before the lease", () => {
  const root = project();
  const bare = kitPath(root, "C5-a");
  fs.mkdirSync(bare, { recursive: true });
  const noResume = run(["unpark", "C5", ...CLAUDE, "--root", root]);
  assert.equal(noResume.code, 1);
  assert.equal(noResume.stderr, "error: kit C5-a has no RESUME.md; write it again to regenerate it\n");
  assert.equal(readLease(bare, TEXTS), null);
  assert.ok(!fs.existsSync(path.join(bare, "HOLDER")));
  fs.writeFileSync(path.join(bare, "RESUME.md"), "# Resume C5-a\n");
  const noNote = run(["unpark", "C5", ...CLAUDE, "--root", root]);
  assert.equal(noNote.code, 1);
  assert.equal(noNote.stderr, "error: kit C5-a was never parked: it has no PARK.md\n");
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
  const kit = kitWithAnswers(root, 2);
  assert.equal(
    digest(kit, 3000, root, TEXTS),
    "park C9-long · parked\nGoal: Goal line\nNext action: Next\nOpen decisions: none\n" +
      "Owner answers:\n- answer 00\n- answer 01",
  );
});

test("a digest names the state of the kit and the job of the note", () => {
  const root = project();
  const kit = kitWithAnswers(root, 0);
  acquireLease(kit, CLAUDE_HOLDER, TEXTS, context(Date.now() / 1000));
  assert.ok(digest(kit, 3000, root, TEXTS).startsWith("park C9-long · active\n"));
  const jobbed = parkFields({ id: "C9", name: "long", nextAction: "Next", plan: "A59", job: "C9.1" });
  const text = renderNote(jobbed, parkBody({ goal: "g" }), TEXTS);
  fs.writeFileSync(path.join(kit, "PARK.md"), text);
  assert.deepEqual(digest(kit, 3000, root, TEXTS).split("\n").slice(0, 3), [
    "park C9-long · active",
    "plan: A59",
    "job: C9.1",
  ]);
});

test("a digest is cut at a whole line and names the overflow", () => {
  const root = project();
  const kit = kitWithAnswers(root, 10);
  const full = digest(kit, 3000, root, TEXTS).split("\n");
  // keep the title, goal, next, decisions-none and the answers heading, plus 2 answers
  const kept = full.slice(0, 7);
  const cap = kept.reduce((sum, line) => sum + line.length + 1, 0);
  const lines = digest(kit, cap, root, TEXTS).split("\n");
  assert.deepEqual(lines.slice(0, -1), kept);
  assert.equal(lines[lines.length - 1], "… 8 more lines in _aitna/.ergon/C9-long/PARK.md");
  // one character short of the next line: it is dropped whole, never cut; with room for it, it is kept
  const short = digest(kit, cap + "- answer 02".length, root, TEXTS).split("\n");
  assert.ok(short[short.length - 1].startsWith("… 8 more"));
  const room = digest(kit, cap + "- answer 02".length + 1, root, TEXTS).split("\n");
  assert.ok(room[room.length - 1].startsWith("… 7 more"));
});

test("a digest with a tiny cap is only the overflow line", () => {
  const root = project();
  const kit = kitWithAnswers(root, 1);
  assert.equal(digest(kit, 0, root, TEXTS), "… 6 more lines in _aitna/.ergon/C9-long/PARK.md");
});

test("a digest without a root names the note by kit", () => {
  const root = project();
  const kit = kitWithAnswers(root, 1);
  assert.ok(digest(kit, 0, null, TEXTS).endsWith("lines in C9-long/PARK.md"));
});

test("a digest reads its own texts when called alone", () => {
  const root = project();
  const kit = kitWithAnswers(root, 1);
  assert.ok(digest(kit, 3000).startsWith("park C9-long · parked"));
});

test("a digest counts code points, not UTF-16 units", () => {
  const root = project();
  const fields = parkFields({ id: "C9", name: "long", nextAction: "Next" });
  const kit = writeKit(fields, parkBody({ goal: "𝒳𝒴" }), root, TEXTS, root);
  // "Goal: 𝒳𝒴" is 8 code points (10 UTF-16 units); the title line is 21 + 1, then this line + 1
  const title = "park C9-long · parked";
  const cap = title.length + 1 + "Goal: 𝒳𝒴".length + 1;
  const lines = digest(kit, cap, root, TEXTS).split("\n");
  assert.deepEqual(lines.slice(0, 2), [title, "Goal: 𝒳𝒴"]);
});

test("a digest indents the continuation of a multiline goal", () => {
  const root = project();
  const fields = parkFields({ id: "C9", name: "long", nextAction: "Next", plan: "A59", readiness: "ready" });
  const kit = writeKit(fields, parkBody({ goal: "one\ntwo" }), root, TEXTS, root);
  assert.deepEqual(digest(kit, 3000, root, TEXTS).split("\n").slice(0, 6), [
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
  const kit = kitWithAnswers(root, 400);
  const lines = run(["digest", "C9", "--root", root]).stdout.split("\n").slice(0, -1);
  const last = lines[lines.length - 1];
  assert.ok(last.startsWith("… ") && last.includes("more lines in _aitna/.ergon/C9-long/PARK.md"));
  assert.ok(lines.slice(0, -1).reduce((sum, line) => sum + line.length + 1, 0) <= 3000);
  assert.ok(fs.statSync(kit).isDirectory());
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

test("a malformed lease is refused, and a bad stamp reads as time zero", () => {
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
    assert.equal(parseLease(`---\nwritten: ${stamp}\n---\n`, "HOLDER", TEXTS).written, 0, stamp);
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
  const fresh = { holder: CLAUDE_HOLDER, written: now - 23 * HOUR };
  const old = { holder: CLAUDE_HOLDER, written: now - 25 * HOUR };
  assert.equal(leaseIsStale(fresh, context(now, "m1")), false);
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
  const unit = kitPath(root, "C1-a");
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
  const unit = kitPath(root, "C1-a");
  fs.mkdirSync(unit, { recursive: true });
  // `acquireLease` found no lease; the file now exists, and the exclusive create refuses it
  const text = renderLease({ holder: CODEX_HOLDER, written: 1_000_000 });
  fs.writeFileSync(path.join(unit, "HOLDER"), text);
  assert.throws(() => fs.openSync(path.join(unit, "HOLDER"), "wx"), { code: "EEXIST" });
  assert.equal(readUtf8(path.join(unit, "HOLDER")), text);
});

test("the same session renews its lease, another is refused with the holder named", () => {
  const root = project();
  const unit = kitPath(root, "C1-a");
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
  const unit = kitPath(root, "C1-a");
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
  const kit = kitPath(root);
  const away = { harness: "claude", sessionId: "s1", machine: "laptop", worktree: "/w1" };
  acquireLease(kit, away, TEXTS, context(Date.now() / 1000, "laptop"));
  const here = context(Date.now() / 1000, "desktop");
  const mine = { harness: "codex", sessionId: "s2", machine: "desktop", worktree: "/w2" };
  assert.equal(unitState(kit, TEXTS, here), "parked");
  assert.throws(() => acquireLease(kit, mine, TEXTS, here), parkError("whose lease is stale"));
  acquireLease(kit, mine, TEXTS, here, { takeover: true });
  const { fields } = readNote(kit, TEXTS);
  assert.deepEqual(fields.sessions, [{ harness: "claude", sessionId: "s1", machine: "laptop" }]);
  // the same holder replaced twice is remembered once
  acquireLease(kit, away, TEXTS, context(Date.now() / 1000, "laptop"), { takeover: true });
  acquireLease(kit, mine, TEXTS, here, { takeover: true });
  assert.equal(readNote(kit, TEXTS).fields.sessions.length, 2);
});

/**
 * A unit folder holding a rendered note, as `write` leaves it (header, a blank line, the body).
 * @param {string} root
 * @returns {{unit: string, note: string}}
 */
function noteUnit(root) {
  const unit = kitPath(root, "C9-long");
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
  const unit = kitPath(root, "C1-a");
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

test("a takeover of a job keeps the replaced holder in the job file", () => {
  const unit = kitPath(project(), "C1-a");
  fs.mkdirSync(unit, { recursive: true });
  const header = parkFields({ id: "C1", name: "a", nextAction: "r", job: "C1.1" });
  fs.writeFileSync(path.join(unit, "JOB.md"), renderJobDoc({ header, steps: [["first", false]], done: false }, TEXTS));
  acquireLease(unit, CLAUDE_HOLDER, TEXTS, context(1_000_000));
  acquireLease(unit, CODEX_HOLDER, TEXTS, context(1_000_100), { takeover: true });
  const kept = parseJobDoc(readUtf8(path.join(unit, "JOB.md")), "JOB.md", TEXTS);
  assert.deepEqual(kept.header.sessions, [{ harness: "claude", sessionId: "s1", machine: "m1" }]);
  assert.deepEqual(kept.steps, [["first", false]]);
  assert.deepEqual(fs.readdirSync(unit).sort(), ["HOLDER", "JOB.md"]);
});

test("a takeover stops before the lease changes when the note does not parse", () => {
  const unit = kitPath(project(), "C1-a");
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
  const unit = kitPath(project(), "C1-a");
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
  const repo = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), "park-repo-")));
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
  staleLease(kitPath(root), repo);
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
    staleLease(kitPath(root), repo);
    assert.equal(
      run(["hold", "C183", ...CODEX, "--takeover", "--root", root]).stdout,
      `C183-park-helper: codex s2 m1 ${NEUTRAL}\n`,
    );
    const gone = path.join(NEUTRAL, "gone");
    staleLease(kitPath(root), gone);
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
  const kit = kitPath(root);
  acquireLease(kit, CLAUDE_HOLDER, TEXTS, context(1_000_000));
  releaseLease(kit);
  assert.equal(readLease(kit, TEXTS), null);
  assert.ok(fs.existsSync(path.join(kit, "PARK.md")));
  releaseLease(kit); // a missing lease is no error
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

test("write is refused into a kit another live session holds, and releases the lease it parks", () => {
  const root = project();
  write(root);
  run(["hold", "C183", ...CLAUDE, "--root", root]);
  const refused = write(root, CODEX);
  assert.equal(refused.code, 1);
  assert.ok(refused.stderr.includes("C183-park-helper is held by claude s1 m1"));
  assert.ok(refused.stderr.includes("read the note, hold another unit, or ask the owner"));
  assert.equal(write(root, CLAUDE).code, 0);
  assert.equal(readLease(kitPath(root), TEXTS), null);
});

test("write over a stale lease is refused in one line and changes nothing", () => {
  const root = project();
  write(root);
  const kit = kitPath(root);
  staleLease(kit);
  const lease = readUtf8(path.join(kit, "HOLDER"));
  const note = readUtf8(path.join(kit, "PARK.md"));
  const refused = write(root, [...CODEX, "--decision", "D-NEW"]);
  assert.equal(refused.code, 1);
  assert.ok(
    refused.stderr.startsWith("error: C183-park-helper is held by claude s1 m1 /work/tree, whose lease is stale;"),
  );
  assert.ok(refused.stderr.includes("hold --takeover"));
  assert.ok(refused.stderr.includes("the owner's word"));
  assert.equal(refused.stderr.split("\n").length, 2);
  assert.equal(readUtf8(path.join(kit, "HOLDER")), lease);
  assert.equal(readUtf8(path.join(kit, "PARK.md")), note);
});

test("write after a takeover goes through and keeps the replaced holder", () => {
  const root = project();
  write(root);
  staleLease(kitPath(root));
  assert.equal(run(["hold", "C183", ...CODEX, "--takeover", "--root", root]).code, 0);
  assert.equal(write(root, CODEX).code, 0);
  assert.equal(readLease(kitPath(root), TEXTS), null);
  assert.deepEqual(readNote(kitPath(root), TEXTS).fields.sessions, [
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
  assert.deepEqual(readNote(kitPath(root), TEXTS).fields.sessions, sessions);
  assert.equal(write(root).code, 0); // a write that names no session keeps the ones the note has
  assert.deepEqual(readNote(kitPath(root), TEXTS).fields.sessions, sessions);
});

test("write merges the holder a takeover kept before the kit had a note", () => {
  const root = project();
  const kit = kitPath(root);
  fs.mkdirSync(kit, { recursive: true });
  assert.equal(run(["hold", "C183", ...CLAUDE, "--root", root]).code, 0);
  staleLease(kit);
  assert.equal(run(["hold", "C183", ...CODEX, "--takeover", "--root", root]).code, 0);
  assert.ok(fs.existsSync(path.join(kit, "SESSIONS")));
  assert.equal(write(root, CODEX).code, 0);
  assert.deepEqual(readNote(kit, TEXTS).fields.sessions, [
    { harness: "claude", sessionId: "s1", machine: "m1" },
    { harness: "codex", sessionId: "s2", machine: "m1" },
  ]);
  assert.deepEqual(fs.readdirSync(kit).sort(), ["PARK.md", "RESUME.md"]);
});

test("a takeover of a job is kept in the job file through the command line", () => {
  const root = project();
  const kit = kitWithPlan(root);
  assert.equal(run(["job", "C1", "--number", "1", "--step", "first", ...CLAUDE, "--root", root]).code, 0);
  const folder = path.join(kit, "jobs", "1-build-core");
  staleLease(folder);
  assert.equal(run(["hold", "C1", "--number", "1", ...CODEX, "--takeover", "--root", root]).code, 0);
  const sessions = [{ harness: "claude", sessionId: "s1", machine: "m1" }];
  assert.deepEqual(parseJobDoc(readUtf8(path.join(folder, "JOB.md")), "JOB.md", TEXTS).header.sessions, sessions);
  assert.equal(run(["job", "C1", "--number", "1", "--step", "second", ...CODEX, "--root", root]).code, 0);
  assert.deepEqual(parseJobDoc(readUtf8(path.join(folder, "JOB.md")), "JOB.md", TEXTS).header.sessions, sessions);
});

test("a write that fails leaves no lease and no folder behind", () => {
  const root = project();
  write(root);
  assert.equal(write(root, [], { name: "other-name" }).code, 1); // the id is taken under another name
  assert.ok(!fs.existsSync(kitPath(root, "C183-other-name")));
  assert.equal(write(root, ["--origin", "two\nlines"], { kitId: "C184", name: "new-kit" }).code, 1);
  assert.ok(!fs.existsSync(kitPath(root, "C184-new-kit")));
});

test("write refuses to reuse the id and name of a closed kit", () => {
  const root = project();
  write(root);
  assert.equal(run(["close", "C183", "--root", root]).code, 0);
  const refused = write(root);
  assert.equal(refused.code, 1);
  assert.equal(
    refused.stderr,
    "error: kit C183-park-helper is closed and keeps its id and name; write under another id or name\n",
  );
  assert.ok(!fs.existsSync(kitPath(root)));
});

test("write by an anonymous session over an anonymous lease is refused", () => {
  const root = project();
  write(root);
  fs.writeFileSync(
    path.join(kitPath(root), "HOLDER"),
    renderLease({ holder: { harness: "", sessionId: "", machine: "", worktree: "" }, written: Date.now() / 1000 }),
  );
  const refused = write(root);
  assert.equal(refused.code, 1);
  assert.ok(refused.stderr.includes("C183-park-helper is held by ? ? ?"));
});

test("a hold on a job that does not exist is refused", () => {
  const root = project();
  write(root);
  const result = run(["hold", "C183", "--number", "4", "--root", root]);
  assert.equal(result.code, 1);
  assert.equal(result.stderr, "error: kit C183-park-helper has no job C183.4\n");
  assert.equal(run(["release", "C183", "--number", "4", "--root", root]).stderr, result.stderr);
});

// --------------------------------------------------------------------------------------
// the plan and its jobs
// --------------------------------------------------------------------------------------

test("a plan's header and job lines are parsed", () => {
  const plan = parsePlan(PLAN_TEXT);
  assert.deepEqual(plan.header, { id: "C1", name: "demo", title: "Demo plan", tasks: ["C1", "C2"] });
  assert.deepEqual(plan.jobs, [
    {
      id: "C1.1",
      number: 1,
      label: "Build core",
      tasks: ["C1"],
      after: [],
      paths: ["src/a", "docs"],
      harness: "",
      result: "core built",
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
    },
    { id: "C1.3", number: 3, label: "Extra", tasks: [], after: [], paths: ["other"], harness: "claude", result: "" },
  ]);
});

test("a plan without a header or a Jobs section has no jobs", () => {
  assert.deepEqual(parsePlan("# just prose\n").jobs, []);
  assert.deepEqual(parsePlan("# just prose\n").header, { id: "", name: "", title: "", tasks: [] });
  assert.deepEqual(parsePlan("---\nid: C1\n---\n## Notes\n\n- C1.1 · a\n").jobs, []);
  assert.deepEqual(parsePlan("---\nid: C1\nno closing fence\n").header.id, "");
});

test("a job line that is not one is skipped", () => {
  for (const line of ["C1.1 · a", "- C1.1", "- C1 · a", "- C1.x · a", "- plain text", "* C1.1 · a"]) {
    assert.equal(parseJobLine(line), null, line);
  }
  assert.equal(parseJobLine("- _T3.2 · local job")?.number, 2);
  assert.deepEqual(parseJobLine("- C1.1 · a · tasks C1, C2 · after C1.0")?.tasks, ["C1", "C2"]);
});

test("a job's folder name is its label as a slug", () => {
  assert.equal(jobSlug("Build the Core!"), "build-the-core");
  assert.equal(jobSlug("  --odd  "), "odd");
  assert.equal(jobSlug("x".repeat(60)), "x".repeat(40));
  assert.equal(jobSlug(`${"a".repeat(39)} b`), "a".repeat(39));
});

test("two jobs that may run at once and share a path are warned of", () => {
  const plan = parsePlan(
    "---\nid: C1\n---\n## Jobs\n\n- C1.1 · a · paths src/a, docs\n- C1.2 · b · paths src/a/deep.py\n- C1.3 · c · paths docs/\n- C1.4 · d · paths other\n",
  );
  assert.deepEqual(sharedPathWarnings(plan, TEXTS), [
    "warning: jobs C1.1 C1.2 may run at once and share path src/a",
    "warning: jobs C1.1 C1.3 may run at once and share path docs",
  ]);
  assert.deepEqual(
    sharedPathWarnings(parsePlan("---\nid: C1\n---\n## Jobs\n\n- C1.1 · a · paths x\n- C1.2 · b · paths y\n"), TEXTS),
    [],
  );
});

test("a job file renders its steps and the done mark, and parses back", () => {
  const header = parkFields({
    id: "C1",
    name: "demo",
    nextAction: "core built",
    plan: "C1",
    job: "C1.1",
    tasks: ["C1"],
  });
  /** @type {import("./park.mjs").JobDoc} */
  const doc = {
    header,
    steps: [
      ["one", true],
      ["two", false],
    ],
    done: true,
  };
  const text = renderJobDoc(doc, TEXTS);
  assert.ok(text.endsWith("## Steps\n\n- [x] one\n- [ ] two\n\ndone\n"));
  assert.deepEqual(parseJobDoc(text, "JOB.md", TEXTS), doc);
  assert.ok(renderJobDoc({ header, steps: [], done: false }, TEXTS).endsWith("## Steps\n\n_none_\n"));
  assert.throws(() => parseJobDoc("no header\n", "JOB.md", TEXTS), parkError("JOB.md: no header"));
});

test("the job command creates a job's file from the plan's line and holds the job", () => {
  const root = project();
  const kit = kitWithPlan(root);
  const result = run(["job", "C1", "--number", "1", "--step", "one", "--step", "two", ...CLAUDE, "--root", root]);
  assert.equal(result.code, 0);
  assert.equal(result.stdout, "_aitna/.ergon/C1-demo/jobs/1-build-core\n");
  const folder = path.join(kit, "jobs", "1-build-core");
  const doc = parseJobDoc(readUtf8(path.join(folder, "JOB.md")), "JOB.md", TEXTS);
  assert.deepEqual(
    {
      job: doc.header.job,
      plan: doc.header.plan,
      tasks: doc.header.tasks,
      next: doc.header.nextAction,
      id: doc.header.id,
    },
    { job: "C1.1", plan: "C1", tasks: ["C1"], next: "core built", id: "C1" },
  );
  assert.deepEqual(doc.steps, [
    ["one", false],
    ["two", false],
  ]);
  assert.equal(readLease(folder, TEXTS)?.holder.sessionId, "s1");
  // a second write adds steps and keeps the first; --done marks the job done
  run(["job", "C1", "--number", "1", "--step", "three", "--done", ...CLAUDE, "--root", root]);
  const again = parseJobDoc(readUtf8(path.join(folder, "JOB.md")), "JOB.md", TEXTS);
  assert.deepEqual(
    again.steps.map(([text]) => text),
    ["one", "two", "three"],
  );
  assert.equal(again.done, true);
});

test("the job command is refused into a job another session holds, and for a job the plan lacks", () => {
  const root = project();
  kitWithPlan(root);
  run(["job", "C1", "--number", "1", "--step", "one", ...CLAUDE, "--root", root]);
  const refused = run(["job", "C1", "--number", "1", "--step", "two", ...CODEX, "--root", root]);
  assert.equal(refused.code, 1);
  assert.ok(refused.stderr.startsWith("error: 1-build-core is held by claude s1 m1 "));
  const missing = run(["job", "C1", "--number", "9", ...CLAUDE, "--root", root]);
  assert.equal(missing.code, 1);
  assert.equal(missing.stderr, "error: kit C1-demo has no job C1.9\n");
});

test("a job in a kit without a plan is refused, and nothing is written", () => {
  const root = project();
  write(root);
  const result = run(["job", "C183", "--number", "1", "--step", "x", ...CLAUDE, "--root", root]);
  assert.equal(result.code, 1);
  assert.equal(result.stderr, "error: kit C183-park-helper has no PLAN.md, so it has no jobs\n");
  assert.ok(!fs.existsSync(path.join(kitPath(root), "jobs")));
  assert.deepEqual(
    walk(kitPath(root)).filter((file) => path.basename(file) === "HOLDER"),
    [],
  );
});

/**
 * A kit `C186-holders-jobs` whose plan is `text`.
 * @param {string} root
 * @param {string} text
 * @returns {string} the kit folder
 */
function planKit(root, text) {
  const kit = kitPath(root, "C186-holders-jobs");
  fs.mkdirSync(kit, { recursive: true });
  fs.writeFileSync(path.join(kit, "PLAN.md"), text);
  return kit;
}

test("a job line the helper cannot write from is refused before anything is written", () => {
  for (const [line, message] of [
    ["- C186.1 ·  · result: r", "error: job C186.1 has no label, so its folder has no name\n"],
    ["- C186.1 · Lease module · tasks C186", "error: kit C186-holders-jobs: job C186.1 has no result\n"],
    ["- C186.1 · Lease module · result:", "error: kit C186-holders-jobs: job C186.1 has no result\n"],
  ]) {
    const root = project();
    const kit = planKit(root, `---\nid: C186\nname: holders-jobs\n---\n\n## Jobs\n\n${line}\n`);
    const result = run(["job", "C186", "--number", "1", "--step", "x", ...CLAUDE, "--root", root]);
    assert.equal(result.code, 1, line);
    assert.equal(result.stderr, message);
    assert.equal(result.stdout, "");
    assert.ok(!fs.existsSync(path.join(kit, "jobs")));
    assert.deepEqual(
      walk(kit).filter((file) => path.basename(file) === "HOLDER"),
      [],
    );
  }
});

test("the job command prints the plan's shared-path warnings on stderr, one line each, stdout unchanged", () => {
  const root = project();
  planKit(
    root,
    "---\nid: C186\nname: holders-jobs\n---\n\n## Jobs\n\n" +
      "- C186.1 · Lease module · paths tools/park · result: r\n" +
      "- C186.2 · Job file · paths tools/park/park.py · result: r\n",
  );
  const result = run(["job", "C186", "--number", "1", "--step", "x", ...CLAUDE, "--root", root]);
  assert.equal(result.code, 0);
  assert.equal(result.stdout, "_aitna/.ergon/C186-holders-jobs/jobs/1-lease-module\n");
  assert.equal(result.stderr, "warning: jobs C186.1 C186.2 may run at once and share path tools/park\n");
  const quiet = project();
  kitWithPlan(quiet);
  assert.equal(run(["job", "C1", "--number", "1", "--step", "x", ...CLAUDE, "--root", quiet]).stderr, "");
});

test("jobs that wait for each other, directly or through a chain, share no warning", () => {
  for (const lines of [
    ["- C1.1 · A · paths x · result: r", "- C1.2 · B · after C1.1 · paths x · result: r"],
    [
      "- C1.1 · A · paths x · result: r",
      "- C1.2 · B · after C1.1 · paths x · result: r",
      "- C1.3 · C · after C1.2 · paths x · result: r",
    ],
  ]) {
    const plan = parsePlan(`---\nid: C1\nname: k\n---\n\n## Jobs\n\n${lines.join("\n")}\n`);
    assert.deepEqual(sharedPathWarnings(plan, TEXTS), []);
  }
});

// --------------------------------------------------------------------------------------
// derived states and the listing
// --------------------------------------------------------------------------------------

test("the state of a unit is derived: active, parked, not started, done", () => {
  const root = project();
  const now = Date.now() / 1000;
  const kit = kitPath(root, "C1-a");
  fs.mkdirSync(kit, { recursive: true });
  assert.equal(unitState(kit, TEXTS, context(now)), "not started");
  fs.writeFileSync(path.join(kit, "PARK.md"), "x");
  assert.equal(unitState(kit, TEXTS, context(now)), "parked");
  acquireLease(kit, CLAUDE_HOLDER, TEXTS, context(now, "m1"));
  assert.equal(unitState(kit, TEXTS, context(now, "m1")), "active");
  assert.equal(unitState(kit, TEXTS, context(now + 25 * HOUR, "m1")), "parked"); // a stale lease holds nothing
  assert.equal(unitState(kit, TEXTS, context(now, "m1"), { jobDone: true }), "done");
  fs.rmSync(path.join(kit, "PARK.md"));
  assert.equal(unitState(kit, TEXTS, context(now + 25 * HOUR, "m1")), "not started");
});

test("a kit is done when every job its plan lists is done, and a planned job with no folder blocks it", () => {
  const root = project();
  const kit = kitWithPlan(root);
  const now = context(Date.now() / 1000);
  assert.equal(kitState(kit, TEXTS, now), "not started"); // no job folder yet
  run(["job", "C1", "--number", "1", "--step", "one", ...CLAUDE, "--root", root]);
  assert.equal(kitState(kit, TEXTS, now), "active"); // a job is held, so the kit is active though it is free itself
  run(["job", "C1", "--number", "1", "--done", ...CLAUDE, "--root", root]);
  run(["job", "C1", "--number", "2", "--step", "two", ...CLAUDE, "--root", root]);
  run(["job", "C1", "--number", "2", "--done", ...CLAUDE, "--root", root]);
  // the plan's third job has no folder: it has not started (ADR 0028 D08)
  assert.equal(kitState(kit, TEXTS, now), "not started");
  doneJob(kit, 3);
  assert.equal(kitState(kit, TEXTS, now), "done");
  fs.rmSync(path.join(kit, "jobs", "3-extra", "JOB.md"));
  assert.equal(kitState(kit, TEXTS, now), "not started"); // a folder with no job file is not a done job
  fs.rmSync(path.join(kit, "jobs", "2-write-docs", "JOB.md"));
  fs.writeFileSync(path.join(kit, "PARK.md"), "note");
  assert.equal(kitState(kit, TEXTS, now), "parked");
});

/**
 * A done `JOB.md` for the plan's job `number` of kit `C1-demo`, written by hand.
 * @param {string} kit
 * @param {number} number
 */
function doneJob(kit, number) {
  const folder = path.join(kit, "jobs", `${number}-extra`);
  fs.mkdirSync(folder, { recursive: true });
  const header = parkFields({ id: "C1", name: "demo", nextAction: "r", job: `C1.${number}` });
  fs.writeFileSync(path.join(folder, "JOB.md"), renderJobDoc({ header, steps: [], done: true }, TEXTS));
}

test("a kit with no plan, or a plan with no jobs, is done by the job folders that exist", () => {
  const root = project();
  const bare = kitPath(root, "C5-bare");
  fs.mkdirSync(bare, { recursive: true });
  const now = context(Date.now() / 1000);
  assert.equal(kitState(bare, TEXTS, now), "not started"); // no folder, nothing done
  const empty = planKit(root, "---\nid: C6\nname: empty\n---\n\n## Jobs\n\n");
  for (const kit of [bare, empty]) {
    const folder = path.join(kit, "jobs", "1-only");
    fs.mkdirSync(folder, { recursive: true });
    const header = parkFields({ id: "C5", name: "x", nextAction: "r", job: "C5.1" });
    fs.writeFileSync(path.join(folder, "JOB.md"), renderJobDoc({ header, steps: [], done: true }, TEXTS));
    assert.equal(kitState(kit, TEXTS, now), "done");
  }
});

test("a list of an empty ergon says so", () => {
  const root = project();
  assert.equal(run(["list", "--root", root]).code, 0);
  assert.equal(run(["list", "--root", root]).stdout, "no kits in _aitna/.ergon\n");
  fs.mkdirSync(path.join(root, "_aitna", ".ergon"), { recursive: true });
  assert.equal(run(["list", "--root", root]).stdout, "no kits in _aitna/.ergon\n");
});

/**
 * @param {string} root
 */
function populate(root) {
  write(root, ["--plan", "A59", "--decision", "D-X", "--decision", "D-Y"]);
  write(root, ["--plan", "A60"], { kitId: "A5", name: "second" });
  fs.mkdirSync(kitPath(root, "C7-never"));
  write(root, [], { kitId: "C20", name: "third" });
  run(["hold", "C20", ...CLAUDE, "--root", root]);
}

test("list prints one line per kit, sorted by id, with the derived state", () => {
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
  assert.deepEqual(listed("--state", "done"), ["no kit matches the filters"]);
  assert.deepEqual(listed("--plan", "A59", "--state", "active"), ["no kit matches the filters"]);
  // the local index is retired, so its `--status` filter is gone with it
  assert.equal(run(["list", "--status", "parked", "--root", root]).code, 2);
});

test("list shows the jobs of a kit under it and filters by task", () => {
  const root = project();
  const kit = kitWithPlan(root);
  write(root);
  run(["job", "C1", "--number", "1", "--step", "one", "--step", "two", ...CLAUDE, "--root", root]);
  run(["job", "C1", "--number", "2", "--done", ...CLAUDE, "--root", root]);
  run(["release", "C1", "--number", "1", "--root", root]);
  fs.writeFileSync(
    path.join(kit, "PARK.md"),
    renderNote(parkFields({ id: "C1", name: "demo", nextAction: "next", plan: "A1" }), parkBody({ goal: "g" }), TEXTS),
  );
  const result = run(["list", ...MACHINE, "--root", root]);
  assert.deepEqual(result.stdout.split("\n").slice(0, -1), [
    "C1 | demo | parked | A1 | next | 0 | - | 0d",
    "  C1.1 | 1-build-core | not started | C1 | one | - | 0d",
    "  C1.2 | 2-write-docs | done | - | - | - | 0d",
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
  assert.deepEqual(withTask("C1"), ["C1"]); // the plan's tasks, a job line's, a job file's
  assert.deepEqual(withTask("C2"), ["C1"]); // named in the plan header only
  assert.deepEqual(withTask("C9"), ["no kit matches the filters"]);
});

test("a job line formats with its tasks, its next step and its age", () => {
  assert.equal(
    formatJob(
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
    formatJob({ id: "C1.1", name: "1-a", state: "done", tasks: [], nextAction: "", branch: "b", ageDays: null }, TEXTS),
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
  const note = path.join(kitPath(root), "PARK.md");
  const now = Date.now() / 1000;
  const old = now - 3 * 86400 - 100;
  fs.utimesSync(note, old, old);
  const [item] = listKits(root, NO_QUERY, TEXTS, context(now)).kits;
  assert.equal(item.ageDays, 3);
  assert.ok(formatSummary(item, TEXTS).endsWith("| 3d"));
  fs.utimesSync(note, now + 500, now + 500); // a clock behind the file never gives a negative age
  assert.equal(listKits(root, NO_QUERY, TEXTS, context(now)).kits[0].ageDays, 0);
});

test("list reads and writes nothing", () => {
  const root = project();
  populate(root);
  kitWithPlan(root);
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

test("list ignores folders that are not kits", () => {
  const root = project();
  write(root);
  fs.mkdirSync(path.join(path.dirname(kitPath(root)), "notes"));
  fs.writeFileSync(path.join(path.dirname(kitPath(root)), "stray.txt"), "x");
  assert.equal(run(["list", "--root", root]).stdout.split("\n").length - 1, 1);
});

test("list reports a kit whose note does not parse on its own line and lists the others", () => {
  const root = project();
  write(root);
  write(root, [], { kitId: "C184", name: "other" });
  fs.writeFileSync(path.join(kitPath(root), "PARK.md"), "broken\n");
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

test("list names the kit and the file of a job file that does not parse, and lists the other kits", () => {
  const root = project();
  const kit = planKit(root, PLAN_TEXT);
  doneJob(kit, 1);
  fs.writeFileSync(path.join(kit, "jobs", "1-extra", "JOB.md"), "no header\n");
  write(root);
  const lines = run(["list", "--root", root]).stdout.split("\n");
  assert.ok(lines[0].startsWith("C183 | park-helper | parked | "));
  assert.equal(
    lines[1],
    "C186 | holders-jobs | unreadable | C186-holders-jobs/jobs/1-extra/JOB.md: no header between two '---' lines at the top of the note",
  );
});

test("an unreadable kit is listed whatever the filters say", () => {
  const root = project();
  write(root);
  fs.writeFileSync(path.join(kitPath(root), "PARK.md"), "broken\n");
  const lines = run(["list", "--state", "active", "--root", root]).stdout.split("\n");
  assert.equal(lines.length, 2);
  assert.ok(lines[0].startsWith("C183 | park-helper | unreadable | "));
});

test("a plan whose id is no task id is refused before the job file or the lease exists", () => {
  const root = project();
  const kit = planKit(
    root,
    "---\nid: c3\nname: holders-jobs\n---\n\n## Jobs\n\n- C186.1 · Lease module · tasks C186 · result: r\n",
  );
  const result = run(["job", "C186", "--number", "1", "--step", "x", ...CLAUDE, "--root", root]);
  assert.equal(result.code, 1);
  assert.equal(result.stdout, "");
  assert.equal(
    result.stderr,
    "error: kit C186-holders-jobs: plan c3 is not a task id (a capital letter or _T followed by digits, e.g. C183 or _T3)\n",
  );
  assert.ok(!fs.existsSync(path.join(kit, "jobs")));
});

test("a job file is replaced atomically and leaves no temporary file", (t) => {
  const root = project();
  const kit = kitWithPlan(root);
  run(["job", "C1", "--number", "1", "--step", "first", ...CLAUDE, "--root", root]);
  const folder = path.join(kit, "jobs", "1-build-core");
  const file = path.join(folder, "JOB.md");
  const before = fs.readFileSync(file);
  const doc = readJobDoc(file, TEXTS);
  assert.ok(doc !== null);
  const mock = t.mock.method(fs, "renameSync", () => {
    throw new Error("disk says no");
  });
  assert.throws(() => writeJobDoc(folder, { ...doc, steps: [["second", false]] }, TEXTS), /disk says no/);
  mock.mock.restore();
  assert.deepEqual(fs.readFileSync(file), before);
  assert.deepEqual(fs.readdirSync(folder).sort(), ["HOLDER", "JOB.md"]);
  writeJobDoc(folder, { ...doc, steps: [["second", false]] }, TEXTS);
  assert.deepEqual(readJobDoc(file, TEXTS)?.steps, [["second", false]]);
  assert.deepEqual(fs.readdirSync(folder).sort(), ["HOLDER", "JOB.md"]);
});

test("a kit is parked when any of its jobs is parked, and active beats parked", () => {
  const root = project();
  const kit = kitWithPlan(root);
  const now = context(Date.now() / 1000);
  doneJob(kit, 1);
  fs.rmSync(path.join(kit, "jobs", "1-extra", "JOB.md"));
  const header = parkFields({ id: "C1", name: "demo", nextAction: "r", job: "C1.1" });
  fs.writeFileSync(
    path.join(kit, "jobs", "1-extra", "JOB.md"),
    renderJobDoc({ header, steps: [], done: false }, TEXTS),
  );
  fs.writeFileSync(
    path.join(kit, "jobs", "1-extra", "PARK.md"),
    renderNote(parkFields({ id: "C1", name: "demo", nextAction: "n" }), parkBody({ goal: "g" }), TEXTS),
  );
  assert.equal(kitState(kit, TEXTS, now), "parked");
  run(["job", "C1", "--number", "2", "--step", "two", ...CLAUDE, "--root", root]);
  assert.equal(kitState(kit, TEXTS, now), "active");
});

test("a kit with every job done is done unless the kit itself is held", () => {
  const root = project();
  const kit = kitWithPlan(root);
  const now = context(Date.now() / 1000);
  for (const number of [1, 2, 3]) {
    const folder = path.join(kit, "jobs", `${number}-job`);
    fs.mkdirSync(folder, { recursive: true });
    const header = parkFields({ id: "C1", name: "demo", nextAction: "r", job: `C1.${number}` });
    fs.writeFileSync(path.join(folder, "JOB.md"), renderJobDoc({ header, steps: [], done: true }, TEXTS));
  }
  fs.writeFileSync(path.join(kit, "PARK.md"), "note"); // a stale note of the plan does not undo done
  assert.equal(kitState(kit, TEXTS, now), "done");
  acquireLease(kit, CLAUDE_HOLDER, TEXTS, now);
  assert.equal(kitState(kit, TEXTS, now), "active");
});

// --------------------------------------------------------------------------------------
// close and export
// --------------------------------------------------------------------------------------

test("close moves the kit to the closed folder and frees its leases", () => {
  const root = project();
  kitWithPlan(root);
  run(["job", "C1", "--number", "1", "--step", "one", ...CLAUDE, "--root", root]);
  run(["hold", "C1", ...CLAUDE, "--root", root]);
  const result = run(["close", "C1", "--root", root]);
  assert.equal(result.code, 0);
  assert.equal(result.stdout, "_aitna/.ergon/.closed/C1-demo\n");
  assert.ok(!fs.existsSync(kitPath(root, "C1-demo")));
  const closed = path.join(kitPath(root, ".closed"), "C1-demo");
  assert.ok(fs.statSync(path.join(closed, "PLAN.md")).isFile());
  assert.deepEqual(
    walk(closed).filter((file) => path.basename(file) === "HOLDER"),
    [],
  );
  assert.equal(findClosedKit(root, "C1", TEXTS), closed);
  assert.equal(findClosedKit(root, "C2", TEXTS), null);
  assert.throws(() => findKit(root, "C1", TEXTS), parkError("no kit with id C1"));
});

test("close refuses a kit a live session holds, naming the holder, and changes nothing", () => {
  const root = project();
  write(root);
  run(["hold", "C183", ...CLAUDE, "--root", root]);
  const refused = run(["close", "C183", ...CODEX, "--root", root]);
  assert.equal(refused.code, 1);
  assert.ok(refused.stderr.startsWith("error: C183-park-helper is held by claude s1 m1 "));
  assert.equal(refused.stderr.split("\n").length, 2);
  assert.ok(fs.existsSync(path.join(kitPath(root), "HOLDER")));
  assert.ok(!fs.existsSync(path.join(kitPath(root, ".closed"), "C183-park-helper")));
});

test("close refuses a kit whose job a live session holds", () => {
  const root = project();
  const kit = kitWithPlan(root);
  run(["job", "C1", "--number", "1", "--step", "one", ...CLAUDE, "--root", root]);
  const refused = run(["close", "C1", ...CODEX, "--root", root]);
  assert.equal(refused.code, 1);
  assert.ok(refused.stderr.startsWith("error: 1-build-core is held by claude s1 m1 "));
  assert.ok(fs.existsSync(path.join(kit, "jobs", "1-build-core", "HOLDER")));
});

test("close by the holder frees its leases, and a stale lease does not block it", () => {
  const root = project();
  write(root);
  run(["hold", "C183", ...CLAUDE, "--root", root]);
  assert.equal(run(["close", "C183", ...CLAUDE, "--root", root]).code, 0);
  assert.deepEqual(
    walk(path.join(kitPath(root, ".closed"), "C183-park-helper")).filter((file) => path.basename(file) === "HOLDER"),
    [],
  );
  write(root, [], { kitId: "C184", name: "second" });
  staleLease(kitPath(root, "C184-second"));
  assert.equal(run(["close", "C184", ...CODEX, "--root", root]).code, 0);
});

test("close over an existing closed kit is one line and changes nothing", () => {
  const root = project();
  write(root);
  const target = path.join(kitPath(root, ".closed"), "C183-park-helper");
  fs.mkdirSync(target, { recursive: true });
  fs.writeFileSync(path.join(target, "mark"), "old");
  run(["hold", "C183", ...CLAUDE, "--root", root]);
  const refused = run(["close", "C183", ...CLAUDE, "--root", root]);
  assert.equal(refused.code, 1);
  assert.equal(
    refused.stderr,
    "error: kit C183-park-helper was not closed: _aitna/.ergon/.closed/C183-park-helper already exists\n",
  );
  assert.ok(fs.existsSync(path.join(kitPath(root), "HOLDER")));
  assert.ok(fs.existsSync(path.join(kitPath(root), "PARK.md")));
  assert.deepEqual(fs.readdirSync(target), ["mark"]);
});

test("list leaves a closed kit out, and --closed brings it back", () => {
  const root = project();
  write(root);
  write(root, [], { kitId: "C2", name: "other" });
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
  assert.equal(run(["list", "--root", root]).stdout, "no kits in _aitna/.ergon\n");
});

test("close of an unknown kit is refused", () => {
  const root = project();
  const result = run(["close", "C9", "--root", root]);
  assert.equal(result.code, 1);
  assert.equal(result.stderr, "error: no kit with id C9 under _aitna/.ergon; kits: none\n");
});

test("export writes the kit's files in path order and leaves the leases out", () => {
  const root = project();
  const kit = kitWithPlan(root);
  write(root, [], { kitId: "C1", name: "demo" });
  run(["job", "C1", "--number", "1", "--step", "one", ...CLAUDE, "--root", root]);
  run(["hold", "C1", ...CLAUDE, "--root", root]);
  assert.ok(fs.existsSync(path.join(kit, "HOLDER")));
  const out = path.join(root, "out", "bundle.md");
  const result = run(["export", "C1", "--out", out, "--root", root]);
  assert.equal(result.code, 0);
  assert.equal(result.stdout, `${out}\n`);
  const bundle = readUtf8(out);
  assert.ok(bundle.startsWith("# akmon kit bundle: C1-demo\n\n--- file: PARK.md\n"));
  const files = [...bundle.matchAll(/^--- file: (.*)$/gm)].map((match) => match[1]);
  assert.deepEqual(files, ["PARK.md", "PLAN.md", "RESUME.md", "jobs/1-build-core/JOB.md"]);
  assert.ok(!bundle.includes("HOLDER") && !bundle.includes("harness: claude\nsession"));
  assert.ok(bundle.endsWith("- [ ] one\n--- end\n"));
  assert.equal(exportKit(kit, path.join(root, "again.md"), TEXTS), path.join(root, "again.md"));
  assert.equal(readUtf8(path.join(root, "again.md")), bundle);
});

test("an export sorts a file by its path components, not by the string", () => {
  const root = project();
  const kit = kitPath(root, "C1-demo");
  fs.mkdirSync(path.join(kit, "a-b"), { recursive: true });
  fs.mkdirSync(path.join(kit, "a"), { recursive: true });
  fs.writeFileSync(path.join(kit, "a-b", "x"), "1\n");
  fs.writeFileSync(path.join(kit, "a", "x"), "2\n");
  exportKit(kit, path.join(root, "bundle.md"), TEXTS);
  const files = [...readUtf8(path.join(root, "bundle.md")).matchAll(/^--- file: (.*)$/gm)].map((match) => match[1]);
  assert.deepEqual(files, ["a/x", "a-b/x"]);
});

// --------------------------------------------------------------------------------------
// the active unit and the worktrees
// --------------------------------------------------------------------------------------

test("a worktree's folder names its kit and its job", () => {
  assert.deepEqual(worktreeUnit("/p/.worktrees/C186-holders-jobs.2"), { kitId: "C186", number: 2 });
  assert.deepEqual(worktreeUnit("/p/.worktrees/_T3-scratch.10"), { kitId: "_T3", number: 10 });
  for (const folder of [
    "/p/.worktrees/C186-holders-jobs",
    "/p/.worktrees/C186.2",
    "/p/.worktrees/main.x",
    "/p/.worktrees/-x.1",
    "/p/.worktrees/x.1.",
  ]) {
    assert.equal(worktreeUnit(folder), null, folder);
  }
});

/**
 * A project whose root is a worktree folder `<outer>/.worktrees/C1-demo.1`, with the kit in it.
 * @returns {string} the worktree root
 */
function worktreeProject() {
  const outer = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), "park-test-")));
  const root = path.join(outer, ".worktrees", "C1-demo.1");
  fs.mkdirSync(path.join(root, "_aitna"), { recursive: true });
  fs.writeFileSync(path.join(root, "AGENTS.md"), "# agents\n");
  fs.writeFileSync(path.join(root, "_aitna", ".akmon.toml"), "");
  kitWithPlan(root);
  return root;
}

test("the active unit is read from the worktree folder", () => {
  const root = worktreeProject();
  const kit = kitPath(root, "C1-demo");
  assert.deepEqual(activeUnit(root, TEXTS), { kit, kitId: "C1", number: 1 });
  const before = run(["active", "--root", root]);
  assert.equal(before.code, 0);
  assert.equal(before.stdout, "kit: C1 | C1-demo | not started | - | _aitna/.ergon/C1-demo\n");
  run(["job", "C1", "--number", "1", "--step", "one", ...CLAUDE, "--root", root]);
  const job = run(["active", ...MACHINE, "--root", root]);
  assert.equal(
    job.stdout,
    `job: C1.1 | 1-build-core | active | claude s1 m1 ${NEUTRAL} | _aitna/.ergon/C1-demo/jobs/1-build-core\n`,
  );
});

test("a session in the main checkout has no active unit", () => {
  const root = project();
  write(root);
  assert.equal(activeUnit(root, TEXTS), null);
  assert.equal(run(["active", "--root", root]).stdout, `${TEXTS.active.none}\n`);
  const named = path.join(root, ".worktrees", "C999-other.1");
  fs.mkdirSync(path.join(named, "_aitna"), { recursive: true });
  fs.writeFileSync(path.join(named, "AGENTS.md"), "");
  assert.equal(activeUnit(named, TEXTS), null); // its kit does not exist
});

// --------------------------------------------------------------------------------------
// a linked worktree sees the main checkout's kits (ADR 0028 D11)
// --------------------------------------------------------------------------------------

test("a repository's common directory leads a worktree to the main checkout", { skip: !gitAvailable() }, () => {
  const main_ = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), "park-test-")));
  fs.writeFileSync(path.join(main_, "AGENTS.md"), "# agents\n");
  fs.mkdirSync(path.join(main_, "_aitna"));
  fs.writeFileSync(path.join(main_, "_aitna", ".akmon.toml"), "");
  git(main_, ["init", "-q"]);
  const linked = path.join(main_, ".worktrees", "C1-demo.1");
  git(main_, ["worktree", "add", "-q", "--orphan", "-b", "feat", linked]);
  assert.equal(gitCommonRoot(main_), main_);
  assert.equal(gitCommonRoot(linked), main_);
  assert.equal(ergonRoot(linked), path.join(main_, "_aitna", ".ergon"));
  // a kit written from the worktree lands in the main checkout, and both see it
  const wrote = run(["write", "C2", "--name", "x", "--goal", "g", "--next", "n", "--root", linked]);
  assert.equal(wrote.code, 0);
  assert.ok(fs.statSync(path.join(main_, "_aitna", ".ergon", "C2-x", "PARK.md")).isFile());
  assert.ok(!fs.existsSync(path.join(linked, "_aitna", ".ergon")));
  assert.ok(run(["list", "--root", linked]).stdout.startsWith("C2 | x | parked"));
  assert.ok(run(["list", "--root", main_]).stdout.startsWith("C2 | x | parked"));
  assert.equal(run(["digest", "C2", "--root", linked]).code, 0);
});

/**
 * A repository with a linked worktree `<main>/.worktrees/C1-demo.1`: the kits stay in the main checkout.
 * @returns {{main: string, linked: string, ergon: string}}
 */
function linkedCheckout() {
  const main_ = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), "park-test-")));
  fs.writeFileSync(path.join(main_, "AGENTS.md"), "# agents\n");
  fs.mkdirSync(path.join(main_, "_aitna"));
  fs.writeFileSync(path.join(main_, "_aitna", ".akmon.toml"), "");
  git(main_, ["init", "-q"]);
  const linked = path.join(main_, ".worktrees", "C1-demo.1");
  git(main_, ["worktree", "add", "-q", "--orphan", "-b", "feat", linked]);
  return { main: main_, linked, ergon: path.join(main_, "_aitna", ".ergon") };
}

test(
  "a path inside the root is printed from it; every command of a linked worktree prints the kits as they are",
  { skip: !gitAvailable() },
  () => {
    const { linked, ergon } = linkedCheckout();
    const empty = run(["list", "--root", linked]);
    assert.equal(empty.stdout, `no kits in ${ergon}\n`);
    const missing = run(["unpark", "C9", "--root", linked]);
    assert.equal(missing.stderr, `error: no kit with id C9 under ${ergon}; kits: none\n`);
    const wrote = run(["write", "C183", "--name", "park-helper", "--goal", "g", "--next", "n", "--root", linked]);
    const kit = path.join(ergon, "C183-park-helper");
    assert.equal(wrote.stdout, `${kit}\n`);
    assert.ok(readUtf8(path.join(kit, "RESUME.md")).includes(`1. Read \`${path.join(kit, "PARK.md")}\`.`));
    const again = run(["unpark", "C9", "--root", linked]);
    assert.equal(again.stderr, `error: no kit with id C9 under ${ergon}; kits: C183-park-helper\n`);
    const cut = run(["digest", "C183", "--cap", "40", "--root", linked]);
    assert.ok(cut.stdout.endsWith(`more lines in ${path.join(kit, "PARK.md")}\n`), cut.stdout);
    const closed = run(["close", "C183", "--root", linked]);
    assert.equal(closed.stdout, `${path.join(ergon, ".closed", "C183-park-helper")}\n`);
  },
);

test("the job and active commands of a linked worktree print the folder as it is", { skip: !gitAvailable() }, () => {
  const { main: main_, linked, ergon } = linkedCheckout();
  kitWithPlan(main_);
  const job = run(["job", "C1", "--number", "1", "--step", "first", ...CLAUDE, "--root", linked]);
  const folder = path.join(ergon, "C1-demo", "jobs", "1-build-core");
  assert.equal(job.code, 0);
  assert.equal(job.stdout, `${folder}\n`);
  const active = run(["active", ...MACHINE, "--root", linked]);
  assert.equal(active.stdout, `job: C1.1 | 1-build-core | active | claude s1 m1 ${NEUTRAL} | ${folder}\n`);
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
    const work = path.join(fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), "park-test-"))), "work");
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
  const missing = path.join(fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), "park-test-"))), "missing");
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
  assert.equal(result.stdout, "no kits in _aitna/.ergon\n");
});

// --------------------------------------------------------------------------------------
// the command line (argparse-shaped: DV12)
// --------------------------------------------------------------------------------------

const COMMAND_CHOICES =
  "'write', 'unpark', 'digest', 'list', 'hold', 'release', 'job', 'active', 'close', 'export', 'local-id'";

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
    [["job", "C1"], "the following arguments are required: --number"],
    [["job"], "the following arguments are required: id, --number"],
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
  const { fields, body } = readNote(kitPath(root, "C1-n"), TEXTS);
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
  const { fields } = readNote(kitPath(root), TEXTS);
  assert.deepEqual(fields.ownedPaths, ["b", "a"]);
  assert.equal(fields.plan, "A2");
});

test("--machine names the machine the session acts as, for the holder and for the staleness", () => {
  const root = project();
  write(root);
  run(["hold", "C183", "--harness", "claude", "--session-id", "s1", "--machine", "laptop", "--root", root]);
  const lease = readLease(kitPath(root), TEXTS);
  assert.equal(lease?.holder.machine, "laptop");
  // the same machine name: the live lease is this session's, so the kit is active
  assert.ok(run(["list", "--machine", "laptop", "--root", root]).stdout.includes("| active |"));
  // another machine's view of the same lease: stale at once
  assert.ok(run(["list", "--machine", "desktop", "--root", root]).stdout.includes("| parked |"));
  const stale = run(["hold", "C183", "--harness", "codex", "--machine", "desktop", "--root", root]);
  assert.ok(stale.stderr.includes("whose lease is stale"));
});

test("kit ids sort by code point, not by locale or length", () => {
  const root = project();
  for (const [kitId, name] of [
    ["C100", "a"],
    ["C20", "b"],
    ["A1", "c"],
    ["_T2", "d"],
  ]) {
    assert.equal(write(root, [], { kitId, name }).code, 0);
  }
  const ids = run(["list", "--root", root])
    .stdout.split("\n")
    .slice(0, -1)
    .map((line) => line.split(" | ")[0]);
  assert.deepEqual(ids, ["A1", "C100", "C20", "_T2"]);
});
