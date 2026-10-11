/**
 * node:test for `js/common/always_loaded.mjs` — the named pins of the twin: the data file and what
 * is read from it, the frozen value classes, and the counter on a real directory. The patterns
 * (fences, comments, inline code, whitespace boundaries), the chain walk and the report are the
 * spec of `meta/conformance/units/always_loaded.toml`, run through `probe.mjs`.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import { posix } from "node:path";

import {
  CODE, Cap, Member, Population, blockHeading, caps, consumer, importChain, markedBlock, over, populations, readAlwaysLoadedData,
  report, severity, shipped } from "./always_loaded.mjs";

const DATA_FILE = new URL("../../common/always_loaded.json", import.meta.url);
const data = readAlwaysLoadedData();

const COMMON = "_aitna/.akmon/guardrails/_common.md";
const BLOCK = `## Dev layer — akmon\n\nintro line\n\n@${COMMON}\n\n`;
const TAIL = "## Project\n\nhand-owned prose\n";

/** Run `body` with a project directory holding `files`, removed after. */
function withProject(/** @type {Record<string, string>} */ files, /** @type {(root: string) => void} */ body) {
  const root = fs.realpathSync(fs.mkdtempSync(posix.join(os.tmpdir(), "akmon-always-loaded-test-")));
  try {
    for (const [relative, text] of Object.entries({ [COMMON]: "rule one\nrule two\n", ...files })) {
      fs.mkdirSync(posix.dirname(posix.join(root, relative)), { recursive: true });
      fs.writeFileSync(posix.join(root, relative), text);
    }
    body(root);
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
}

test("the readers answer what the data file carries", () => {
  assert.deepEqual(data, JSON.parse(fs.readFileSync(DATA_FILE, "utf-8")));
  assert.equal(CODE, "caps.always-loaded");
  assert.equal(blockHeading(data), "## Dev layer — akmon");
  assert.equal(shipped(data), "akmon-shipped");
  assert.equal(consumer(data), "consumer-total");
  assert.deepEqual(caps(data), { "akmon-shipped": new Cap(320, 21000), "consumer-total": new Cap(570, 34000) });
  assert.deepEqual(severity(data), { "akmon-shipped": "error", "consumer-total": "warn" });
});

test("the readers follow the data they are handed, not the file", () => {
  const other = { block_heading: "## X", scopes: ["a", "b"], caps: { a: { lines: 1, bytes: 2 }, b: { lines: 3, bytes: 4 } }, severity: { a: "warn", b: "error" } };
  assert.equal(blockHeading(other), "## X");
  assert.equal(shipped(other), "a");
  assert.equal(consumer(other), "b");
  assert.deepEqual(caps(other), { a: new Cap(1, 2), b: new Cap(3, 4) });
  assert.equal(markedBlock(other, "## X\nbody\n## Y\n"), "## X\nbody\n");
  assert.equal(markedBlock(other, "## Dev layer — akmon\n"), null);
});

test("severity answers a copy: editing it does not edit the data", () => {
  const copy = severity(data);
  copy["akmon-shipped"] = "ok";
  assert.equal(severity(data)["akmon-shipped"], "error");
});

test("Cap, Member and Population are frozen", () => {
  const cap = new Cap(1, 2);
  const member = new Member("m", "x\n");
  const population = new Population("s", [member]);
  for (const value of [cap, member, population, population.members]) {
    assert.ok(Object.isFrozen(value));
  }
  assert.throws(() => {
    /** @type {any} */ (cap).lines = 9;
  }, TypeError);
  assert.throws(() => {
    /** @type {any} */ (population.members).push(member);
  }, TypeError);
});

test("a Population keeps its members as a copy of what it was given", () => {
  const given = [new Member("a", "1\n")];
  const population = new Population("s", given);
  given.push(new Member("b", "2\n"));
  assert.equal(population.members.length, 1);
  assert.equal(new Population("s", new Set(given).values()).members.length, 2);
});

test("lines and size are the Python measures, and sums have no separator", () => {
  const member = new Member("m", "a\r\nb é");
  assert.equal(member.lines, 2 + 1);
  assert.equal(member.size, Buffer.byteLength("a\r\nb é", "utf8"));
  const population = new Population("s", [new Member("a", "no newline"), new Member("b", "next\n")]);
  assert.equal(population.lines, 2);
  assert.equal(population.size, "no newlinenext\n".length);
  assert.equal(new Population("s", []).lines, 0);
});

test("the shipped scope counts block, chain and selected once; the consumer scope the whole file", () => {
  withProject({ "_aitna/.akmon/profiles/python.md": "py rule\n" }, (root) => {
    const agents = `# AGENTS.md\n\n${BLOCK}${TAIL}`;
    const selected = [posix.join(root, "_aitna/.akmon/profiles/python.md"), posix.join(root, COMMON)];
    const found = /** @type {Record<string, Population>} */ (populations(data, agents, root, selected));
    const names = (/** @type {Population} */ population) => population.members.map((member) => member.name);
    assert.deepEqual(names(found["akmon-shipped"]), ["AGENTS.md (akmon block)", COMMON, "_aitna/.akmon/profiles/python.md"]);
    assert.deepEqual(names(found["consumer-total"]), ["AGENTS.md", COMMON, "_aitna/.akmon/profiles/python.md"]);
    assert.equal(found["akmon-shipped"].lines, BLOCK.split("\n").length - 1 + 2 + 1);
    assert.equal(found["consumer-total"].size - found["akmon-shipped"].size, Buffer.byteLength(agents) - Buffer.byteLength(BLOCK));
  });
});

test("no marked block means no populations", () => {
  withProject({}, (root) => {
    assert.equal(populations(data, "# AGENTS.md\n\n## Other\n", root), null);
  });
});

test("changing one member moves the shipped count by exactly that member", () => {
  /** @type {Population[]} */
  const first = [];
  withProject({}, (root) => {
    first.push(/** @type {Record<string, Population>} */ (populations(data, `# A\n\n${BLOCK}${TAIL}`, root))["akmon-shipped"]);
  });
  const [before] = first;
  withProject({ [COMMON]: "rule one\nrule two\nrule three\n" }, (root) => {
    const after = /** @type {Record<string, Population>} */ (populations(data, `# A\n\n${BLOCK}${TAIL}`, root))["akmon-shipped"];
    assert.deepEqual([after.lines - before.lines, after.size - before.size], [1, Buffer.byteLength("rule three\n")]);
  });
});

test("importChain takes the root as an option and resolves nothing outside it", () => {
  withProject({ "a.md": "a\n", "../outside.md": "o\n" }, (root) => {
    assert.deepEqual(importChain("@a.md\n@../outside.md\n", root, { root }), [posix.join(root, "a.md")]);
    assert.throws(() => importChain("@a.md\n", root, /** @type {any} */ (undefined)), TypeError);
  });
});

test("an unreadable chain file raises UnicodeDecodeError, as read_text does", () => {
  withProject({}, (root) => {
    fs.writeFileSync(posix.join(root, "bad.md"), Buffer.from([0xff, 0x0a]));
    assert.throws(() => importChain("@bad.md\n", root, { root }), { name: "UnicodeDecodeError" });
  });
});

test("the report and the cap check read the same population", () => {
  const cap = new Cap(10, 100);
  const population = new Population("consumer-total", [new Member("m", "ab\ncd\n")]);
  assert.equal(report(population, cap), "consumer-total: lines=2/10 bytes=6/100");
  assert.equal(over(population, new Cap(2, 6)), false);
  assert.equal(over(population, new Cap(1, 6)), true);
  assert.equal(over(population, new Cap(2, 5)), true);
});
