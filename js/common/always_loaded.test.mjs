/**
 * node:test for `js/common/always_loaded.mjs` — the named pins of the twin: the data file and what
 * is read from it, the frozen value classes, and the counter on a real directory. The patterns
 * (fences, comments, inline code, whitespace boundaries), the chain walk and the report are the
 * spec of `meta/conformance/units/always_loaded.toml`, run through `probe.mjs`.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { posix } from "node:path";

import {
  CODE,
  Cap,
  Member,
  OtherAudiences,
  Population,
  blockHeading,
  caps,
  consumer,
  audienceSizes,
  importChain,
  markedBlock,
  over,
  populations,
  readAlwaysLoadedData,
  report,
  severity,
  shipped,
} from "./always_loaded.mjs";
import { tempDir } from "./temp_dir.test.mjs";

const DATA_FILE = new URL("../../common/always_loaded.json", import.meta.url);
const data = readAlwaysLoadedData();

const COMMON = "_aitna/.akmon/guardrails/_common.md";
const BLOCK = `## Dev layer — akmon\n\nintro line\n\n@${COMMON}\n\n`;
const TAIL = "## Project\n\nhand-owned prose\n";

/** Run `body` with a project directory holding `files`, removed after. */
function withProject(/** @type {Record<string, string>} */ files, /** @type {(root: string) => void} */ body) {
  const root = tempDir("akmon-always-loaded-test-");
  for (const [relative, text] of Object.entries({ [COMMON]: "rule one\nrule two\n", ...files })) {
    fs.mkdirSync(posix.dirname(posix.join(root, relative)), { recursive: true });
    fs.writeFileSync(posix.join(root, relative), text);
  }
  body(root);
}

test("the readers answer what the data file carries", () => {
  assert.deepEqual(data, JSON.parse(fs.readFileSync(DATA_FILE, "utf-8")));
  assert.equal(CODE, "caps.always-loaded");
  assert.equal(blockHeading(data), "## Dev layer — akmon");
  assert.equal(shipped(data), "akmon-shipped");
  assert.equal(consumer(data), "consumer-total");
  assert.deepEqual(caps(data), { "akmon-shipped": new Cap(474, 31500), "consumer-total": new Cap(724, 44500) });
  assert.deepEqual(severity(data), { "akmon-shipped": "error", "consumer-total": "warn" });
});

test("the readers follow the data they are handed, not the file", () => {
  const other = {
    block_heading: "## X",
    scopes: ["a", "b"],
    caps: { a: { lines: 1, bytes: 2 }, b: { lines: 3, bytes: 4 } },
    severity: { a: "warn", b: "error" },
  };
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
  const member = new Member("m", "a\r\nb\u2028é");
  assert.equal(member.lines, 2 + 1);
  assert.equal(member.size, Buffer.byteLength("a\r\nb\u2028é", "utf8"));
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
    assert.deepEqual(names(found["akmon-shipped"]), [
      "AGENTS.md (akmon block)",
      COMMON,
      "_aitna/.akmon/profiles/python.md",
    ]);
    assert.deepEqual(names(found["consumer-total"]), ["AGENTS.md", COMMON, "_aitna/.akmon/profiles/python.md"]);
    assert.equal(found["akmon-shipped"].lines, BLOCK.split("\n").length - 1 + 2 + 1);
    assert.equal(
      found["consumer-total"].size - found["akmon-shipped"].size,
      Buffer.byteLength(agents) - Buffer.byteLength(BLOCK),
    );
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
    first.push(
      /** @type {Record<string, Population>} */ (populations(data, `# A\n\n${BLOCK}${TAIL}`, root))["akmon-shipped"],
    );
  });
  const [before] = first;
  withProject({ [COMMON]: "rule one\nrule two\nrule three\n" }, (root) => {
    const after = /** @type {Record<string, Population>} */ (populations(data, `# A\n\n${BLOCK}${TAIL}`, root))[
      "akmon-shipped"
    ];
    assert.deepEqual([after.lines - before.lines, after.size - before.size], [1, Buffer.byteLength("rule three\n")]);
  });
});

test("importChain takes the root as an option and resolves nothing outside it", () => {
  withProject({ "a.md": "a\n", "../outside.md": "o\n" }, (root) => {
    try {
      assert.deepEqual(importChain("@a.md\n@../outside.md\n", root, { root }), [posix.join(root, "a.md")]);
      assert.throws(() => importChain("@a.md\n", root, /** @type {any} */ (undefined)), TypeError);
    } finally {
      // The file sits beside the root, in the temp folder itself, where tempDir's clean-up does not reach.
      fs.rmSync(posix.join(root, "..", "outside.md"), { force: true });
    }
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
  assert.equal(report(population, cap), "consumer-total: lines=2/10 bytes=6/100 hooks=0");
  assert.equal(over(population, new Cap(2, 6)), false);
  assert.equal(over(population, new Cap(1, 6)), true);
  assert.equal(over(population, new Cap(2, 5)), true);
});

test("the other audiences are reported beside the attended head and never summed into the cap's totals (A49)", () => {
  const cap = new Cap(100, 1000);
  const chain = new Member("m", "ab\ncd\n");
  const attended = new Member("hook: head", "one\ntwo\n");
  const unattended = new Member("hook: head", "x\n");
  const delegate = new Member("hook: subagent-start", "abc\n");
  const population = new Population("consumer-total", [chain], [attended]);
  const others = new OtherAudiences([unattended], [delegate]);
  assert.equal(population.size, 6 + 8, "the cap's total is the attended head's alone");
  assert.deepEqual(audienceSizes(population, others), [6 + 2, 6 + 4]);
  assert.ok(Object.isFrozen(others.unattended) && Object.isFrozen(others.delegate));
  assert.equal(
    report(population, cap, others),
    "consumer-total: lines=4/100 bytes=14/1000 hooks=8 unattended-head=8 delegate=10",
  );
  // either other audience alone is enough to report; neither leaves the report as it was
  assert.ok(report(population, cap, new OtherAudiences([], [delegate])).endsWith(" unattended-head=6 delegate=10"));
  assert.ok(report(population, cap, new OtherAudiences([unattended])).endsWith(" unattended-head=8 delegate=6"));
  assert.equal(report(population, cap), "consumer-total: lines=4/100 bytes=14/1000 hooks=8");
});

test("hook text joins both scopes, is summed into the totals and is reported apart", () => {
  withProject({}, (root) => {
    const agents = `# AGENTS.md\n\n${BLOCK}${TAIL}`;
    const hook = new Member("hook: x", "one\ntwo\n");
    const found = /** @type {Record<string, Population>} */ (populations(data, agents, root, [], [hook]));
    const bare = /** @type {Record<string, Population>} */ (populations(data, agents, root));
    for (const scope of ["akmon-shipped", "consumer-total"]) {
      assert.deepEqual(found[scope].hooks, [hook]);
      assert.equal(found[scope].hookSize, 8);
      assert.equal(found[scope].size, bare[scope].size + 8);
      assert.equal(found[scope].lines, bare[scope].lines + 2);
      assert.ok(report(found[scope], new Cap(100, 1000)).endsWith(" hooks=8"));
    }
    assert.equal(bare["consumer-total"].hooks.length, 0);
    assert.ok(Object.isFrozen(found["consumer-total"].hooks));
  });
});
