/**
 * node:test for `js/common/audience.mjs` (A49): the selector with its three signals, the two layers'
 * file lists and the text each layer reads from a tree. The Python module (`common/audience.py`) is the
 * spec; `common/audience.json` is the data both read.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { posix } from "node:path";
import { fileURLToPath } from "node:url";

import { isAttended, layerFiles, layerText } from "./audience.mjs";
import { read } from "./jsondata.mjs";
import { readData as readLearning } from "./learning.mjs";
import { tempDir } from "./temp_dir.test.mjs";

const TREE = posix.resolve(posix.dirname(fileURLToPath(import.meta.url)), "..", "..");
const data = /** @type {import("./audience.mjs").AudienceData} */ (read(posix.join(TREE, "common", "audience.json")));
const learning = readLearning();

test("the selector: no signal, or every signal at its attended value, is an attended session", () => {
  assert.equal(isAttended(learning, {}), true);
  assert.equal(isAttended(learning, { AKMON_ACTOR: "developer", CLAUDE_CODE_SESSION_ATTENDED: "1" }), true);
  assert.equal(isAttended(learning, { CLAUDE_CODE_SESSION_ATTENDED: "" }), true);
  assert.equal(isAttended(learning, { AKMON_ACTOR: "no-such-actor" }), true, "an unknown actor reads as developer");
});

test("the selector: each of the three signals alone makes the session unattended", () => {
  assert.equal(isAttended(learning, { AKMON_ACTOR: "autonomous" }), false);
  assert.equal(isAttended(learning, { CLAUDE_CODE_SESSION_ATTENDED: "0" }), false);
  assert.equal(isAttended(learning, { AKMON_SECOND_OPINION: "1" }), false);
});

test("the selector: the signals read the variables the learning data names, and only `0` is unattended", () => {
  assert.equal(learning.attended_variable, "CLAUDE_CODE_SESSION_ATTENDED");
  assert.equal(learning.second_opinion_variable, "AKMON_SECOND_OPINION");
  assert.equal(isAttended(learning, { CLAUDE_CODE_SESSION_ATTENDED: "false" }), true);
  assert.equal(isAttended(learning, { AKMON_SECOND_OPINION: "" }), true, "an empty marker is not set");
  assert.equal(isAttended(learning, { AKMON_ACTOR: "autonomous", CLAUDE_CODE_SESSION_ATTENDED: "1" }), false);
});

test("the layers' files: the head layer is collaboration and templates, the unattended layer is its own file", () => {
  assert.deepEqual(layerFiles(data, true), ["rules/collaboration.md", "rules/templates.md"]);
  assert.deepEqual(layerFiles(data, false), ["rules/unattended.md"]);
  const copy = layerFiles(data, true);
  copy.push("x");
  assert.equal(layerFiles(data, true).length, 2, "a caller's change does not reach the data");
});

test("layerText joins the files of a layer with the separator and trims their trailing newlines", () => {
  const root = tempDir("akmon-audience-");
  fs.mkdirSync(posix.join(root, "rules"));
  fs.writeFileSync(posix.join(root, "rules", "collaboration.md"), "# head one\n\n");
  fs.writeFileSync(posix.join(root, "rules", "templates.md"), "# head two\n");
  fs.writeFileSync(posix.join(root, "rules", "unattended.md"), "# unattended\n");
  assert.equal(layerText(data, root, true), `# head one${data.separator}# head two`);
  assert.equal(layerText(data, root, false), "# unattended");
  fs.rmSync(posix.join(root, "rules", "templates.md"));
  assert.throws(() => layerText(data, root, true), { code: "ENOENT" });
});

test("layerText of this tree is the shipped rule files, the two layers sharing nothing", () => {
  const head = layerText(data, TREE, true);
  const unattended = layerText(data, TREE, false);
  assert.ok(head.includes("# Rules: collaboration with the owner"));
  assert.ok(head.includes("# Rules: templates"));
  assert.ok(unattended.startsWith("# Rules: working without the owner"));
  assert.ok(!head.includes("# Rules: working without the owner"));
  assert.ok(!unattended.includes("# Rules: collaboration with the owner"));
});
