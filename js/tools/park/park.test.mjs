/**
 * node:test for `js/tools/park/park.mjs` — the twin of `meta/tests/test_park.py`, case for case: the
 * note, the kit, the local index, the commands. The byte-level spec shared by both implementations is
 * the `tools/park-*` scenarios of `meta/conformance/scenarios`, run by `runner.py --impl node --area tools`.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { embeddedTreeRoot } from "../../akmon/_tree.mjs";
import { read } from "../../common/jsondata.mjs";
import {
  ParkError,
  checkBody,
  checkFields,
  digest,
  formatSummary,
  listKits,
  main,
  parkBody,
  parkFields,
  parseHeader,
  parseNote,
  readNote,
  renderHeader,
  renderNote,
  withState,
  writeKit,
} from "./park.mjs";

/** @typedef {import("./park.mjs").ParkData} ParkData */
/** @typedef {import("./park.mjs").ParkFields} ParkFields */
/** @typedef {import("./park.mjs").ParkBody} ParkBody */

const TEXTS = /** @type {ParkData} */ (read(path.join(embeddedTreeRoot(), "tools", "park", "park.json")));

const LOCAL_HEADER = "# TASKS — local index";
const NO_OPTIONS = { title: "", role: "" };
const NO_QUERY = { plan: "", state: "", status: "" };

const FULL_FIELDS = parkFields({
  id: "C183",
  name: "park-helper",
  nextAction: "Twin it: JS | Python",
  state: "parked",
  plan: "A59",
  row: "C183",
  branch: "_aitna/C183-park-helper",
  revisions: ["abc123", "def456"],
  ownedPaths: ["tools/park/park.py", "meta/tests/test_park.py"],
  sessions: [
    { harness: "claude", sessionId: "s-1", machine: "laptop" },
    { harness: "codex", sessionId: "s-2", machine: "" },
  ],
  peers: ["sibling session on B8"],
  origin: "claude on laptop",
  readiness: "ready for a successor",
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
 * Run `main` with the process streams captured.
 * @param {string[]} argv
 * @returns {{code: number, stdout: string, stderr: string}}
 */
function run(argv) {
  let stdout = "";
  let stderr = "";
  const out = process.stdout.write;
  const err = process.stderr.write;
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
 * @param {string} root
 * @returns {string}
 */
function indexPath(root) {
  return path.join(root, "_aitna", ".local", "TASKS.md");
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
  return writeKit(fields, body, root, NO_OPTIONS, TEXTS);
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
  assert.ok(text.includes("plan:\n") && text.includes("revisions:\n"));
  assert.deepEqual(parseHeader(text, "PARK.md", TEXTS), fields);
});

test("header text is flat and ordered", () => {
  const lines = renderHeader(FULL_FIELDS).split("\n");
  assert.equal(lines[0], "---");
  assert.equal(lines[lines.length - 2], "---");
  const keys = lines
    .slice(1, -2)
    .filter((line) => !line.startsWith("  - "))
    .map((line) => line.split(":")[0]);
  assert.deepEqual(keys, [
    "state",
    "id",
    "name",
    "plan",
    "row",
    "branch",
    "revisions",
    "owned_paths",
    "next",
    "sessions",
    "peers",
    "origin",
    "readiness",
  ]);
  assert.ok(lines.includes("  - claude|s-1|laptop"));
  assert.ok(lines.includes("  - codex|s-2|"));
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

test("withState changes only the state and keeps the body", () => {
  const text = `${renderNote(FULL_FIELDS, FULL_BODY, TEXTS)}\nhand-written line\n`;
  const resumed = withState(text, "resumed", "PARK.md", TEXTS);
  const { fields, body } = parseNote(resumed, "PARK.md", TEXTS);
  assert.equal(fields.state, "resumed");
  assert.deepEqual(fields, { ...FULL_FIELDS, state: "resumed" });
  assert.deepEqual(body, FULL_BODY);
  assert.ok(resumed.endsWith("hand-written line\n"));
});

/** @type {[Partial<ParkFields>, string][]} */
const REFUSED_FIELDS = [
  [{ id: "c1" }, "id c1 is not a task id"],
  [{ id: "C" }, "id C is not a task id"],
  [{ plan: "plan" }, "plan plan is not a task id"],
  [{ name: "Park Helper" }, "name Park Helper is not kebab-case"],
  [{ name: "park--helper" }, "is not kebab-case"],
  [{ nextAction: "two\nlines" }, "next must be a single line"],
  [{ branch: "a\rb" }, "branch must be a single line"],
  [{ origin: " padded " }, "origin must be a single line"],
  [{ nextAction: "" }, "next must not be empty"],
  [{ state: "done" }, "state done is not parked or resumed"],
  [{ revisions: ["a\nb"] }, "revision must be a single line"],
  [{ peers: [""] }, "peer must not be empty"],
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
  ["---\nstate: parked\n", "no header between two '---' lines"],
  ["---\nstate: parked\nstate: parked\n---\n", "header key state is unknown or repeated"],
  ["---\nbogus: 1\n---\n", "header key bogus is unknown or repeated"],
  ["---\n  - orphan\n---\n", "is a list item with no list key above it"],
  ["---\nid: C1\n  - x\n---\n", "is a list item with no list key above it"],
  ["---\nrevisions: a\n---\n", "header key revisions takes a single value"],
  ["---\nSTATE parked\n---\n", "is neither 'key: value' nor an indented '- item'"],
  ["---\nstate: parked\nid: C1\nname: n\n---\n", "no value for next"],
  ["---\nstate: parked\nid: c1\nname: n\nnext: x\n---\n", "id c1 is not a task id"],
];

for (const [text, message] of MALFORMED_HEADERS) {
  test(`malformed headers are refused: ${message}`, () => {
    assert.throws(() => parseHeader(text, "PARK.md", TEXTS), parkError(message));
  });
}

// --------------------------------------------------------------------------------------
// write: the kit, the resume prompt, the index
// --------------------------------------------------------------------------------------

test("write creates the kit with both files", () => {
  const root = project();
  const result = write(root, ["--plan", "A59", "--decision", "D-X"]);
  assert.equal(result.code, 0);
  assert.equal(result.stdout, "_aitna/.ergon/C183-park-helper\n");
  const kit = kitPath(root);
  const { fields, body } = parseNote(readUtf8(path.join(kit, "PARK.md")), "PARK.md", TEXTS);
  assert.deepEqual([fields.id, fields.name, fields.state, fields.plan], ["C183", "park-helper", "parked", "A59"]);
  assert.equal(body.goal, "Build the helper");
  assert.deepEqual(body.decisions, ["D-X"]);
  assert.ok(fs.statSync(path.join(kit, "RESUME.md")).isFile());
  assert.deepEqual(fs.readdirSync(kit).sort(), ["PARK.md", "RESUME.md"]);
});

test("a second write rewrites the note as parked again", () => {
  const root = project();
  write(root);
  const kit = kitPath(root);
  const note = path.join(kit, "PARK.md");
  fs.writeFileSync(note, withState(readUtf8(note), "resumed", "PARK.md", TEXTS));
  assert.equal(write(root).code, 0);
  assert.equal(readNote(kit, TEXTS).fields.state, "parked");
});

test("write flags fill every header field", () => {
  const root = project();
  const flags = [
    ["--plan", "A59"],
    ["--row", "C183"],
    ["--branch", "_aitna/C183-park-helper"],
    ["--revision", "abc"],
    ["--revision", "def"],
    ["--owned-path", "tools/park/park.py"],
    ["--peer", "other"],
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
    fields,
    parkFields({
      id: "C183",
      name: "park-helper",
      nextAction: "Twin it",
      plan: "A59",
      row: "C183",
      branch: "_aitna/C183-park-helper",
      revisions: ["abc", "def"],
      ownedPaths: ["tools/park/park.py"],
      sessions: [{ harness: "claude", sessionId: "s1", machine: "laptop" }],
      peers: ["other"],
      origin: "claude",
      readiness: "ready",
    }),
  );
  assert.deepEqual([body.checks, body.unverified, body.answers, body.agents], [["pytest"], ["twin"], ["go"], ["none"]]);
});

test("session flags without a harness are refused", () => {
  const root = project();
  const result = write(root, ["--session-id", "s1"]);
  assert.equal(result.code, 1);
  assert.equal(result.stderr, "error: --session-id and --machine need --harness\n");
  assert.ok(!fs.existsSync(kitPath(root)));
});

test("the resume prompt is harness-neutral and dateless", () => {
  const root = project();
  write(root, ["--decision", "D-X", "--plan", "A59"]);
  const kit = kitPath(root);
  const resume = readUtf8(path.join(kit, "RESUME.md"));
  assert.ok(resume.includes("`_aitna/.ergon/C183-park-helper/PARK.md`"));
  assert.ok(resume.includes("`akmon tool park/park unpark C183`"));
  assert.ok(resume.includes("Twin it") && resume.includes("- D-X"));
  assert.ok(resume.includes("stop is observed") && resume.includes("otherwise report a blocker"));
  assert.ok(resume.includes("(N15)"));
  assert.ok(!resume.includes(root));
  assert.ok(!resume.split("\n").some((line) => line.startsWith("/")));
  for (const name of ["PARK.md", "RESUME.md"]) {
    assert.doesNotMatch(readUtf8(path.join(kit, name)), /\d{4}-\d{2}-\d{2}/);
  }
});

test("the index is created with the one-line header and a parked row", () => {
  const root = project();
  write(root, ["--role", "engineer", "--title", "The park helper"]);
  assert.equal(
    readUtf8(indexPath(root)),
    `${LOCAL_HEADER}\n\n- C183 · The park helper · parked · engineer · Build the helper · ` +
      "[park](../.ergon/C183-park-helper/PARK.md)\n",
  );
});

test("a new row defaults its title to the goal and its role to architect", () => {
  const root = project();
  write(root);
  const lines = readUtf8(indexPath(root)).split("\n");
  assert.equal(
    lines[lines.length - 2],
    "- C183 · Build the helper · parked · architect · Build the helper · [park](../.ergon/C183-park-helper/PARK.md)",
  );
});

test("a new row uses the first line of a multiline goal", () => {
  const root = project();
  const argv = ["write", "C1", "--name", "n", "--goal", "first\nsecond", "--next", "x", "--root", root];
  assert.equal(run(argv).code, 0);
  assert.ok(readUtf8(indexPath(root)).includes("· first · parked · architect · first ·"));
});

test("an existing index is kept and the row appended", () => {
  const root = project();
  fs.mkdirSync(path.dirname(indexPath(root)), { recursive: true });
  const existing = `${LOCAL_HEADER}\n\nprose line\n\n- A71 · plan · active · architect · goal · [plan](x)\n`;
  fs.writeFileSync(indexPath(root), existing);
  write(root);
  const text = readUtf8(indexPath(root));
  assert.ok(text.startsWith(existing));
  assert.equal(text.split("\n- C183 ·").length - 1, 1);
});

test("an existing row is set to parked and gains a park link", () => {
  const root = project();
  fs.mkdirSync(path.dirname(indexPath(root)), { recursive: true });
  fs.writeFileSync(
    indexPath(root),
    `${LOCAL_HEADER}\n\n- C183 · own title  ·  active  · engineer · own goal\n- C184 · other · active · engineer · g\n`,
  );
  write(root);
  const lines = readUtf8(indexPath(root)).split("\n");
  assert.equal(
    lines[2],
    "- C183 · own title  ·  parked  · engineer · own goal · [park](../.ergon/C183-park-helper/PARK.md)",
  );
  assert.equal(lines[3], "- C184 · other · active · engineer · g");
});

test("an existing row with a detail link keeps its link", () => {
  const root = project();
  fs.mkdirSync(path.dirname(indexPath(root)), { recursive: true });
  fs.writeFileSync(indexPath(root), `${LOCAL_HEADER}\n\n- C183 · t · deferred · engineer · g · [detail](../x.md)\n`);
  write(root);
  assert.equal(readUtf8(indexPath(root)).split("\n")[2], "- C183 · t · parked · engineer · g · [detail](../x.md)");
});

test("a row with a tracker tag is found by its id", () => {
  const root = project();
  fs.mkdirSync(path.dirname(indexPath(root)), { recursive: true });
  fs.writeFileSync(indexPath(root), `${LOCAL_HEADER}\n\n- C183[#9] · t · active · engineer · g\n`);
  write(root);
  const text = readUtf8(indexPath(root));
  assert.equal(text.split("- C183").length - 1, 1);
  assert.ok(text.includes("· parked ·"));
});

test("a row with too few fields is refused and nothing is written", () => {
  const root = project();
  fs.mkdirSync(path.dirname(indexPath(root)), { recursive: true });
  fs.writeFileSync(indexPath(root), "- C183 · only title\n");
  assert.equal(write(root).code, 1);
  assert.ok(!fs.existsSync(kitPath(root)));
  assert.equal(readUtf8(indexPath(root)), "- C183 · only title\n");
});

test("a separator in a new row's cell is refused", () => {
  const root = project();
  const result = write(root, ["--title", "a · b"]);
  assert.equal(result.code, 1);
  assert.ok(result.stderr.includes("title must not contain '·'"));
  assert.ok(!fs.existsSync(kitPath(root)));
});

test("the project index is never touched", () => {
  const root = project();
  const projectIndex = path.join(root, "_aitna", "TASKS.md");
  fs.writeFileSync(projectIndex, "- C183 · t · active · engineer · g\n");
  const before = fs.readFileSync(projectIndex);
  write(root);
  run(["unpark", "C183", "--root", root]);
  assert.deepEqual(fs.readFileSync(projectIndex), before);
  const files = fs
    .readdirSync(path.join(root, "_aitna"), { withFileTypes: true })
    .filter((entry) => entry.isFile())
    .map((entry) => entry.name)
    .sort();
  assert.deepEqual(files, [".akmon.toml", "TASKS.md"]);
});

test("a dev-root pointer moves the kit and the index", () => {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), "park-test-")));
  fs.writeFileSync(path.join(root, "AGENTS.md"), "");
  fs.writeFileSync(path.join(root, ".aitna-root"), "tools/ai\n");
  assert.equal(write(root).code, 0);
  assert.ok(fs.statSync(path.join(root, "tools/ai/.ergon/C183-park-helper/PARK.md")).isFile());
  assert.ok(fs.statSync(path.join(root, "tools/ai/.local/TASKS.md")).isFile());
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
  assert.ok(!fs.existsSync(indexPath(root)));
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

test("a kit with the id and another name is refused", () => {
  const root = project();
  write(root);
  const result = write(root, [], { name: "renamed" });
  assert.equal(result.code, 1);
  assert.equal(
    result.stderr,
    "error: kit C183-park-helper already carries id C183; keep its name or retire it before writing renamed\n",
  );
  assert.ok(!fs.existsSync(kitPath(root, "C183-renamed")));
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

test("local ids are accepted", () => {
  const root = project();
  assert.equal(write(root, [], { kitId: "_T7", name: "scratch" }).code, 0);
  assert.ok(fs.statSync(kitPath(root, "_T7-scratch")).isDirectory());
});

// --------------------------------------------------------------------------------------
// unpark and digest
// --------------------------------------------------------------------------------------

test("unpark resumes the note and the row and prints resume then digest", () => {
  const root = project();
  write(root, ["--decision", "D-X", "--answer", "owner: go", "--plan", "A59"]);
  const result = run(["unpark", "C183", "--root", root]);
  assert.equal(result.code, 0);
  const resume = readUtf8(path.join(kitPath(root), "RESUME.md"));
  assert.ok(result.stdout.startsWith(`${resume.replace(/\n+$/, "")}\n\npark C183-park-helper · resumed\n`));
  assert.ok(result.stdout.endsWith("Owner answers:\n- owner: go\n"));
  assert.equal(readNote(kitPath(root), TEXTS).fields.state, "resumed");
  assert.ok(readUtf8(indexPath(root)).includes("· active ·"));
});

test("unpark leaves a row that is not parked alone", () => {
  const root = project();
  write(root);
  fs.writeFileSync(indexPath(root), readUtf8(indexPath(root)).replace("· parked ·", "· blocked ·"));
  run(["unpark", "C183", "--root", root]);
  assert.ok(readUtf8(indexPath(root)).includes("· blocked ·"));
});

test("unpark without an index row or file still resumes", () => {
  const root = project();
  write(root);
  fs.unlinkSync(indexPath(root));
  assert.equal(run(["unpark", "C183", "--root", root]).code, 0);
  assert.ok(!fs.existsSync(indexPath(root)));
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

test("unpark of a kit that was never parked is refused", () => {
  const root = project();
  fs.mkdirSync(kitPath(root, "C5-a"), { recursive: true });
  const result = run(["unpark", "C5", "--root", root]);
  assert.equal(result.code, 1);
  assert.equal(result.stderr, "error: kit C5-a was never parked: it has no PARK.md\n");
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
  const kit = writeKit(fields, parkBody({ goal: "𝒳𝒴" }), root, NO_OPTIONS, TEXTS);
  // "Goal: 𝒳𝒴" is 8 code points (10 UTF-16 units); the title line is 21 + 1, then this line + 1
  const title = "park C9-long · parked";
  const cap = title.length + 1 + "Goal: 𝒳𝒴".length + 1;
  const lines = digest(kit, cap, root, TEXTS).split("\n");
  assert.deepEqual(lines.slice(0, 2), [title, "Goal: 𝒳𝒴"]);
});

test("a digest indents the continuation of a multiline goal", () => {
  const root = project();
  const fields = parkFields({ id: "C9", name: "long", nextAction: "Next", plan: "A59", readiness: "ready" });
  const kit = writeKit(fields, parkBody({ goal: "one\ntwo" }), root, NO_OPTIONS, TEXTS);
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
// list
// --------------------------------------------------------------------------------------

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
  write(root, ["--plan", "A59", "--decision", "D-X", "--decision", "D-Y", "--branch", "_aitna/C183-park-helper"]);
  write(root, ["--plan", "A60"], { kitId: "A5", name: "second" });
  fs.mkdirSync(kitPath(root, "C7-never"));
  write(root, [], { kitId: "C20", name: "third" });
  run(["unpark", "C20", "--root", root]);
}

test("list prints one line per kit, sorted by id", () => {
  const root = project();
  populate(root);
  const result = run(["list", "--root", root]);
  assert.equal(result.code, 0);
  assert.deepEqual(result.stdout.split("\n").slice(0, -1), [
    "A5 | second | parked | A60 | Twin it | 0 | - | 0d",
    "C183 | park-helper | parked | A59 | Twin it | 2 | _aitna/C183-park-helper | 0d",
    "C20 | third | resumed | - | Twin it | 0 | - | 0d",
    "C7 | never | never-parked | - | - | 0 | - | -",
  ]);
});

test("list filters by plan, state and status", () => {
  const root = project();
  populate(root);
  /**
   * @param {...string} flags
   * @returns {string[]}
   */
  const listed = (...flags) =>
    run(["list", ...flags, "--root", root])
      .stdout.split("\n")
      .slice(0, -1)
      .map((line) => line.split(" | ")[0]);
  assert.deepEqual(listed("--plan", "A59"), ["C183"]);
  assert.deepEqual(listed("--state", "parked"), ["A5", "C183"]);
  assert.deepEqual(listed("--state", "never-parked"), ["C7"]);
  assert.deepEqual(listed("--state", "resumed"), ["C20"]);
  assert.deepEqual(listed("--status", "parked"), ["A5", "C183"]);
  assert.deepEqual(listed("--status", "active"), ["C20"]);
  assert.deepEqual(listed("--status", "-"), ["C7"]);
  assert.deepEqual(listed("--plan", "A59", "--state", "resumed"), ["no kit matches the filters"]);
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
  const [item] = listKits(root, NO_QUERY, now, TEXTS);
  assert.equal(item.ageDays, 3);
  assert.ok(formatSummary(item, TEXTS).endsWith("| 3d"));
  fs.utimesSync(note, now + 500, now + 500); // a clock behind the file never gives a negative age
  assert.equal(listKits(root, NO_QUERY, now, TEXTS)[0].ageDays, 0);
});

test("list reads and writes nothing", () => {
  const root = project();
  populate(root);
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
  assert.deepEqual(snapshot(), before);
});

test("list ignores folders that are not kits", () => {
  const root = project();
  write(root);
  fs.mkdirSync(path.join(path.dirname(kitPath(root)), "notes"));
  fs.writeFileSync(path.join(path.dirname(kitPath(root)), "stray.txt"), "x");
  assert.equal(run(["list", "--root", root]).stdout.split("\n").length - 1, 1);
});

test("list names a kit whose note does not parse", () => {
  const root = project();
  write(root);
  fs.writeFileSync(path.join(kitPath(root), "PARK.md"), "broken\n");
  const result = run(["list", "--root", root]);
  assert.equal(result.code, 1);
  assert.equal(
    result.stderr,
    "error: C183-park-helper/PARK.md: no header between two '---' lines at the top of the note\n",
  );
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

for (const argv of [["list"], ["write", "C1", "--name", "n", "--goal", "g", "--next", "x"], ["unpark", "C1"]]) {
  test(`no project root is refused and nothing is written: ${argv[0]}`, () => {
    const work = path.join(fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), "park-test-"))), "work");
    fs.mkdirSync(work);
    inDirectory(work, () => {
      const result = run(argv);
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
  inDirectory(nested, () => {
    const result = run(["write", "C1", "--name", "n", "--goal", "g", "--next", "x"]);
    assert.equal(result.code, 0);
    assert.equal(result.stdout, "_aitna/.ergon/C1-n\n");
  });
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

test("a usage error is one line on stderr and exit 2", () => {
  for (const [argv, message] of /** @type {[string[], string][]} */ ([
    [[], "the following arguments are required: command"],
    [["bogus"], "argument command: invalid choice: 'bogus' (choose from 'write', 'unpark', 'digest', 'list')"],
    [["write", "C1"], "the following arguments are required: --name, --goal, --next"],
    [["write", "--name", "n", "--goal", "g", "--next", "x"], "the following arguments are required: id"],
    [["unpark"], "the following arguments are required: id"],
    [["unpark", "C1", "C2"], "unrecognized arguments: C2"],
    [["list", "--bogus"], "unrecognized arguments: --bogus"],
    [["list", "stray"], "unrecognized arguments: stray"],
    [["list", "--plan"], "argument --plan: expected one argument"],
    [["list", "--plan", "--state", "x"], "argument --plan: expected one argument"],
    [["digest", "C1", "--cap", "abc"], "argument --cap: invalid int value: 'abc'"],
    [
      ["--root", "x", "list"],
      "argument command: invalid choice: '--root' (choose from 'write', 'unpark', 'digest', 'list')",
    ],
  ])) {
    const result = run(argv);
    assert.equal(result.code, 2, argv.join(" "));
    assert.equal(result.stderr, `park.mjs: error: ${message}\n`);
    assert.equal(result.stdout, "");
  }
});

test("--help prints the usage and exits 0", () => {
  for (const argv of [["-h"], ["--help"], ["write", "-h"], ["list", "--help"]]) {
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
  const flags = ["--revision", "b", "--revision", "a", "--plan", "A1", "--plan", "A2"];
  assert.equal(write(root, flags).code, 0);
  const { fields } = readNote(kitPath(root), TEXTS);
  assert.deepEqual(fields.revisions, ["b", "a"]);
  assert.equal(fields.plan, "A2");
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
