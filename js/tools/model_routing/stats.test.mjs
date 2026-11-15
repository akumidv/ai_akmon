/**
 * node:test for `js/tools/model_routing/stats.mjs` — the aggregation, the budget path (with an
 * injected `fetch`, never the real API), the rendering and a run of `main`. The byte-level spec is
 * the `tools/stats-*` scenarios of `meta/conformance/scenarios`, run by `runner.py --impl node`.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { embeddedTreeRoot } from "../../akmon/_tree.mjs";
import { read } from "../../common/jsondata.mjs";
import {
  BudgetSummary,
  CODE_EDIT,
  CODE_READ,
  NO_CODE,
  SessionRef,
  SessionTouch,
  TranscriptStats,
  aggregateDelegationLines,
  aggregateSubagentLines,
  aggregateTranscriptLines,
  budgetSummary,
  classifySessionLines,
  collectCodeTouch,
  collectSubagentStats,
  labelAndTier,
  main,
  mungedProjectDir,
  newestJsonl,
  parseDelegationLog,
  parseUsageResponse,
  readAccessToken,
  renderDigest,
  renderReport,
  touchRules,
  transcriptsDir,
  usageFromMessage,
} from "./stats.mjs";

const DATA = /** @type {any} */ (read(path.join(embeddedTreeRoot(), "tools", "model_routing", "stats.json")));

/**
 * Run `main` with the process streams captured.
 * @param {string[]} argv
 * @param {any} [deps]
 * @returns {Promise<{code: number, stdout: string, stderr: string}>}
 */
async function run(argv, deps) {
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
    return { code: await main(argv, deps), stdout, stderr };
  } finally {
    process.stdout.write = out;
    process.stderr.write = err;
  }
}

/** @returns {string} a scratch directory */
function scratch() {
  return fs.mkdtempSync(path.join(os.tmpdir(), "stats-test-"));
}

const assistantLine = (/** @type {string} */ model, /** @type {object} */ usage) =>
  JSON.stringify({ type: "assistant", message: { model, usage } });

test("usageFromMessage reads the four counts; a non-int is 0, a missing usage is null", () => {
  assert.equal(usageFromMessage({}), null);
  assert.equal(usageFromMessage({ usage: [] }), null);
  assert.deepEqual(
    {
      ...usageFromMessage({
        usage: { input_tokens: 5, output_tokens: 1.5, cache_read_input_tokens: "x", cache_creation_input_tokens: true },
      }),
    },
    { inputTokens: 5, outputTokens: 0, cacheReadTokens: 0, cacheCreationTokens: 1 },
  );
});

test("aggregateDelegationLines counts per pair, per subagent and per model", () => {
  const stats = aggregateDelegationLines([
    "t\ts\tk_a\thaiku\tz\tone",
    "t\ts\tk_a\thaiku\tz\ttwo",
    "t\ts\tk_b\t-\tz\tthree",
    "t,short",
    "t\tk_c\topus\told style",
  ]);
  assert.equal(stats.total, 4);
  assert.deepEqual(
    [...stats.perSubagent],
    [
      ["k_a", 2],
      ["k_b", 1],
      ["k_c", 1],
    ],
  );
  assert.deepEqual(
    [...stats.perModel],
    [
      ["haiku", 2],
      ["-", 1],
      ["opus", 1],
    ],
  );
});

test("parseDelegationLog is null for a missing file", () => {
  const dir = scratch();
  assert.equal(parseDelegationLog(path.join(dir, "none.log")), null);
  fs.writeFileSync(path.join(dir, "a.log"), "t\ts\tk_a\thaiku\tz\tx\n");
  assert.equal(parseDelegationLog(path.join(dir, "a.log"))?.total, 1);
});

test("aggregateTranscriptLines sums per model, counts users, tolerates junk", () => {
  const stats = aggregateTranscriptLines([
    "",
    "not json",
    "[1]",
    '{"type": "user"}',
    assistantLine("m1", { input_tokens: 10, output_tokens: 2 }),
    assistantLine("m1", { input_tokens: 5, cache_read_input_tokens: 3 }),
    JSON.stringify({ type: "assistant", message: { usage: { input_tokens: 1 } } }),
    JSON.stringify({ type: "assistant", message: { model: "m2" } }),
    '{"type": "system"}',
  ]);
  assert.equal(stats.userMessageCount, 1);
  assert.deepEqual([...stats.perModel.keys()], ["m1", "-"]);
  assert.equal(stats.perModel.get("m1")?.inputTokens, 15);
  assert.equal(stats.perModel.get("m1")?.cacheReadTokens, 3);
});

test("munged names and the transcript dir follow the Python spelling", () => {
  assert.equal(mungedProjectDir("/a/b"), "-a-b");
  assert.equal(transcriptsDir("/a/b", "/h/.claude"), "/h/.claude/projects/-a-b");
});

test("newestJsonl picks the most recently modified jsonl", () => {
  const dir = scratch();
  assert.equal(newestJsonl(path.join(dir, "missing")), null);
  assert.equal(newestJsonl(dir), null);
  fs.writeFileSync(path.join(dir, "old.jsonl"), "");
  fs.writeFileSync(path.join(dir, "new.jsonl"), "");
  fs.writeFileSync(path.join(dir, "other.txt"), "");
  fs.utimesSync(path.join(dir, "old.jsonl"), 1000, 1000);
  fs.utimesSync(path.join(dir, "new.jsonl"), 2000, 2000);
  fs.utimesSync(path.join(dir, "other.txt"), 3000, 3000);
  assert.equal(newestJsonl(dir), path.join(dir, "new.jsonl"));
});

test("subagent transcripts: usage, label fallback and tier", () => {
  const [usage, label] = aggregateSubagentLines([
    '{"attributionAgent": "k_x", "type": "user"}',
    assistantLine("m", { input_tokens: 4, output_tokens: 1 }),
  ]);
  assert.equal(usage.inputTokens, 4);
  assert.equal(label, "k_x");
  const tiers = new Map([["k_x", "worker"]]);
  assert.deepEqual(labelAndTier({}, "k_x", tiers), ["k_x", "worker"]);
  assert.deepEqual(labelAndTier({ agentType: "other" }, "k_x", tiers), ["other", "-"]);
  assert.deepEqual(labelAndTier({}, "", tiers), ["-", "-"]);

  const dir = scratch();
  assert.deepEqual(collectSubagentStats(path.join(dir, "none"), tiers), []);
  fs.writeFileSync(path.join(dir, "agent-b.jsonl"), `${assistantLine("m", { input_tokens: 1 })}\n`);
  fs.writeFileSync(path.join(dir, "agent-a.jsonl"), `${assistantLine("m", { input_tokens: 2 })}\n`);
  fs.writeFileSync(path.join(dir, "agent-a.meta.json"), '{"agentType": "k_x"}');
  fs.writeFileSync(path.join(dir, "notes.jsonl"), "");
  const records = collectSubagentStats(dir, tiers);
  assert.deepEqual(
    records.map((r) => [r.agentId, r.label, r.tier, r.usage.inputTokens]),
    [
      ["agent-a", "k_x", "worker", 2],
      ["agent-b", "-", "-", 1],
    ],
  );
});

test("parseUsageResponse: remaining percent rounds as Python does; scoped limits are labelled", () => {
  const budget = parseUsageResponse(DATA, {
    five_hour: { utilization: 37.55, resets_at: "soon" },
    seven_day: { utilization: 12.5 },
    limits: [
      { kind: "weekly_scoped", scope: { model: { display_name: "Opus" } }, percent: 99.75, resets_at: "later" },
      { kind: "other" },
      "junk",
    ],
  });
  assert.equal(budget.unavailable, null);
  assert.equal(budget.session?.remainingPct, 62.5);
  assert.equal(budget.session?.resetsAt, "soon");
  assert.equal(budget.week?.remainingPct, 87.5);
  assert.deepEqual(
    budget.scoped.map((s) => [s.label, s.remainingPct]),
    [["week (Opus)", 0.2]],
  );
  // A missing or non-numeric utilization has no remaining value.
  assert.equal(parseUsageResponse(DATA, {}).session?.remainingPct, null);
  assert.equal(parseUsageResponse(DATA, { five_hour: { utilization: "x" } }).session?.remainingPct, null);
});

test("parseUsageResponse degrades an unexpected shape to an unavailable reason", () => {
  assert.equal(parseUsageResponse(DATA, []).unavailable, "AttributeError: 'list' object has no attribute 'get'");
  assert.equal(parseUsageResponse(DATA, { limits: 5 }).unavailable, "TypeError: 'int' object is not iterable");
});

test("readAccessToken and budgetSummary use an injected fetch and never the network", async () => {
  const dir = scratch();
  const creds = path.join(dir, "creds.json");
  assert.equal(readAccessToken(creds), null);
  assert.equal((await budgetSummary(DATA, { credentialsPath: creds })).unavailable, "no credentials found");
  fs.writeFileSync(creds, '{"claudeAiOauth": {"accessToken": "tok"}}');
  assert.equal(readAccessToken(creds), "tok");

  /** @type {string[]} */ const seen = [];
  const ok = await budgetSummary(DATA, {
    credentialsPath: creds,
    fetch: async (url, token) => (seen.push(url, token), { five_hour: { utilization: 10 } }),
  });
  assert.deepEqual(seen, [DATA.usage_url, "tok"]);
  assert.equal(ok.session?.remainingPct, 90);

  const failed = await budgetSummary(DATA, {
    credentialsPath: creds,
    fetch: async () => {
      const error = new Error("HTTP Error 401: Unauthorized");
      error.name = "HTTPError";
      throw error;
    },
  });
  assert.equal(failed.unavailable, "HTTPError: HTTP Error 401: Unauthorized");
});

test("renderDigest and renderReport over a full set of data", () => {
  const delegation = aggregateDelegationLines(["t\ts\tk_a\thaiku\tz\tx", "t\ts\tk_b\t-\tz\ty"]);
  const transcript = aggregateTranscriptLines([
    assistantLine("m1", {
      input_tokens: 10,
      output_tokens: 2,
      cache_read_input_tokens: 1,
      cache_creation_input_tokens: 4,
    }),
  ]);
  const sub = collectSubagentStats(scratch(), new Map());
  const budget = parseUsageResponse(DATA, {
    five_hour: { utilization: 40, resets_at: "r1" },
    seven_day: { utilization: 5.5 },
  });
  assert.equal(
    renderDigest(DATA, delegation, transcript, sub, budget, ".claude/stats/r.md"),
    [
      "delegations: 2 total (k_a=1, k_b=1)",
      "orchestrator tokens: in=10 out=2 cache-read=1",
      "subagent tokens: no subagent transcripts",
      "code touch: no session transcript with a user turn",
      "budget: session 60.0% remaining (resets r1), week 94.5% remaining (resets -)",
      "report: .claude/stats/r.md",
    ].join("\n"),
  );
  const report = renderReport(
    DATA,
    ".claude/model-routing.log",
    new SessionRef("main", "t/main.jsonl"),
    delegation,
    transcript,
    sub,
    budget,
  );
  assert.match(report, /^# Session statistics — main\n\nTranscript: `t\/main\.jsonl`\n\n## Delegations\n\nTotal: 2\n/);
  assert.match(report, /\| orchestrator \(m1\) \| orchestrator \| 10 \| 2 \| 1 \| 4 \|/);
  assert.match(report, /- session remaining: 60\.0% \(resets r1\)/);
  assert.ok(report.endsWith("\n"));
  // Every source absent.
  const bare = renderReport(
    DATA,
    "log",
    new SessionRef("-", null),
    null,
    null,
    [],
    new BudgetSummary({ unavailable: "why" }),
  );
  assert.match(bare, /Transcript: not found/);
  assert.match(bare, /unavailable: why/);
  assert.match(bare, /\| orchestrator \| orchestrator \| - \| - \| - \| - \|/);
});

test("main: usage errors are one line and exit 2; -h prints the usage", async () => {
  assert.match((await run(["--bogus"])).stderr, /^stats\.mjs: error: Unknown option '--bogus'/);
  assert.equal((await run(["--bogus"])).code, 2);
  assert.match((await run(["-h"])).stdout, /^usage: stats\.mjs /);
});

test("main: with every source absent, each section degrades and the exit is 0", async () => {
  const root = scratch();
  const result = await run([
    "--project-root",
    root,
    "--transcript",
    path.join(root, "absent.jsonl"),
    "--no-budget",
    "--report-dir",
    path.join(root, "out"),
  ]);
  assert.equal(result.code, 0);
  assert.match(
    result.stdout,
    /^delegations: no delegations logged\norchestrator tokens: transcript unavailable\nsubagent tokens: no subagent transcripts\ncode touch: no session transcript with a user turn\nbudget: unavailable \(skipped \(--no-budget\)\)\nreport: .*\/out\/stats-1\.md\n$/,
  );
  assert.deepEqual(fs.readdirSync(path.join(root, "out")), ["stats-1.md"]);
  assert.match(fs.readFileSync(path.join(root, "out", "stats-1.md"), "utf8"), /^# Session statistics — absent\n/);
});

test("main: the budget goes through the injected fetch, credentials from HOME", async () => {
  const root = scratch();
  const home = scratch();
  fs.mkdirSync(path.join(home, ".claude"));
  fs.writeFileSync(path.join(home, ".claude", ".credentials.json"), '{"claudeAiOauth": {"accessToken": "tok"}}');
  const saved = process.env.HOME;
  process.env.HOME = home;
  try {
    const result = await run(["--project-root", root, "--report-dir", path.join(root, "out")], {
      fetch: async () => ({ five_hour: { utilization: 25, resets_at: "R" }, seven_day: { utilization: 50 } }),
    });
    assert.equal(result.code, 0);
    assert.match(
      result.stdout,
      /\nbudget: session 75\.0% remaining \(resets R\), week 50\.0% remaining \(resets -\)\n/,
    );
  } finally {
    process.env.HOME = saved;
  }
});

// ---- A49: code touch — which sessions needed code at all ----

const rules = touchRules(DATA);

const prompt = (/** @type {string} */ text = "do it") => JSON.stringify({ type: "user", message: { content: text } });
const toolUse = (/** @type {string} */ name, /** @type {object} */ input) =>
  JSON.stringify({ type: "assistant", message: { content: [{ type: "tool_use", name, input }] } });
const toolResult = () =>
  JSON.stringify({ type: "user", message: { content: [{ type: "tool_result", content: "ok" }] } });

/**
 * A main-session aggregate carrying a code-touch scan, as `main` makes it.
 * @param {import("./stats.mjs").CodeTouchStats | null} codeTouch
 * @returns {TranscriptStats}
 */
function scanned(codeTouch) {
  const stats = new TranscriptStats();
  stats.codeTouch = codeTouch;
  return stats;
}

/**
 * @param {string} file
 * @param {string[]} lines
 */
function writeLines(file, lines) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, `${lines.join("\n")}\n`);
}

/** @param {string} root */
function codeTouchFixture(root) {
  writeLines(path.join(root, "a.jsonl"), [prompt(), toolUse("Edit", { file_path: "/p/a.py" })]);
  writeLines(path.join(root, "b.jsonl"), [prompt(), toolUse("Read", { file_path: "/p/b.js" })]);
  writeLines(path.join(root, "c.jsonl"), [prompt()]);
  writeLines(path.join(root, "d.jsonl"), [toolUse("Edit", { file_path: "/p/a.py" })]); // no user turn: left out
  const one = path.join(root, "a", "subagents");
  writeLines(path.join(one, "agent-1.jsonl"), [prompt(), toolUse("Write", { file_path: "/p/n.ts" })]);
  fs.writeFileSync(path.join(one, "agent-1.meta.json"), '{"agentType": "k_implementer"}');
  writeLines(path.join(one, "agent-2.jsonl"), [prompt()]);
  fs.writeFileSync(path.join(one, "agent-2.meta.json"), '{"agentType": "k_explorer"}');
  writeLines(path.join(root, "b", "subagents", "agent-3.jsonl"), [
    JSON.stringify({ type: "user", attributionAgent: "k_explorer", message: { content: "go" } }),
  ]);
}

test("classifySessionLines: no user turn is not classified; reminders, meta and tool results are not turns", () => {
  assert.equal(classifySessionLines([toolUse("Edit", { file_path: "/p/a.py" }), toolResult()], rules), null);
  const lines = [
    prompt("<system-reminder>context</system-reminder>"),
    JSON.stringify({ type: "user", isMeta: true, message: { content: "meta" } }),
    toolResult(),
    JSON.stringify({ type: "user", message: { content: [{ type: "text", text: "typed" }] } }),
  ];
  assert.deepEqual({ ...classifySessionLines(lines, rules) }, { ...new SessionTouch(NO_CODE, null) });
});

test("classifySessionLines: an edit of a code file is code-edit, with the turn of the first touch", () => {
  const lines = [
    prompt(),
    toolUse("Read", { file_path: "/p/docs/a.md" }),
    prompt("again"),
    toolUse("Read", { file_path: "/p/a.py" }),
    prompt("and again"),
    toolUse("Write", { file_path: "/p/b.mjs" }),
  ];
  assert.deepEqual({ ...classifySessionLines(lines, rules) }, { ...new SessionTouch(CODE_EDIT, 2) });
});

test("classifySessionLines: notebook_path is read, a config or notebook file is no touch", () => {
  const kind = (/** @type {string} */ name, /** @type {object} */ input) =>
    classifySessionLines([prompt(), toolUse(name, input)], rules)?.kind;
  assert.equal(kind("Edit", { file_path: "/p/c.toml" }), NO_CODE);
  assert.equal(kind("NotebookEdit", { notebook_path: "/p/n.ipynb" }), NO_CODE);
  assert.equal(kind("NotebookEdit", { notebook_path: "/p/n.py" }), CODE_EDIT);
});

test("classifySessionLines: a read of a code file or a test command is code-read", () => {
  const read = classifySessionLines([prompt(), toolUse("Read", { file_path: "/p/A.PY" })], rules);
  assert.deepEqual({ ...read }, { ...new SessionTouch(CODE_READ, 1) });
  const ran = classifySessionLines([prompt(), prompt(), toolUse("Bash", { command: "uv run pytest -q" })], rules);
  assert.deepEqual({ ...ran }, { ...new SessionTouch(CODE_READ, 2) });
  const none = classifySessionLines(
    [prompt(), toolUse("Bash", { command: "git log --oneline" }), toolUse("Bash", { command: "echo subtsc" })],
    rules,
  );
  assert.equal(none?.kind, NO_CODE);
});

test("classifySessionLines: a Bash write and a search are not counted (the stated limit)", () => {
  const lines = [
    prompt(),
    toolUse("Bash", { command: "cat > tools/a.py <<'EOF'\nx = 1\nEOF" }),
    toolUse("Grep", { pattern: "x", path: "tools" }),
    toolUse("Glob", { pattern: "**/*.py" }),
  ];
  assert.equal(classifySessionLines(lines, rules)?.kind, NO_CODE);
});

test("classifySessionLines: junk lines are passed over; the label is the attribution agent", () => {
  const junk = ["", "not json", "[1]", JSON.stringify({ type: "assistant", message: { content: "text" } }), prompt()];
  assert.deepEqual({ ...classifySessionLines(junk, rules) }, { ...new SessionTouch(NO_CODE, null) });
  const labelled = JSON.stringify({ type: "user", attributionAgent: "k_explorer", message: { content: "go" } });
  assert.equal(classifySessionLines([labelled], rules)?.label, "k_explorer");
});

test("collectCodeTouch: null for a missing directory; main sessions and labelled subagents otherwise", () => {
  const root = scratch();
  assert.equal(collectCodeTouch(path.join(root, "absent"), rules), null);
  codeTouchFixture(root);
  const result = collectCodeTouch(root, rules);
  assert.equal(result?.scanned, root);
  assert.deepEqual(
    result?.main.map((touch) => touch.kind),
    [CODE_EDIT, CODE_READ, NO_CODE],
  );
  assert.deepEqual(
    result?.subagents.map((touch) => [touch.label, touch.kind]),
    [
      ["k_implementer", CODE_EDIT],
      ["k_explorer", NO_CODE],
      ["k_explorer", NO_CODE],
    ],
  );
});

test("the digest reports both groups, the type shares and the limit; the report has the tables", () => {
  const root = scratch();
  codeTouchFixture(root);
  const codeTouch = collectCodeTouch(root, rules);
  const digest = renderDigest(DATA, null, scanned(codeTouch), [], new BudgetSummary(), "r.md").split("\n");
  assert.ok(
    digest.includes(
      "code touch, main sessions (n=3): code-edit 1 (33%), code-read 1 (33%), no-code 1 (33%); median first touch at user turn 1",
    ),
  );
  assert.ok(
    digest.includes(
      "code touch, subagents (n=3): code-edit 1 (33%), code-read 0 (0%), no-code 2 (67%); median first touch at user turn 1",
    ),
  );
  assert.ok(
    digest.includes("code touch, no-code share by subagent type: k_explorer 100% (n=2), k_implementer 0% (n=1)"),
  );
  assert.ok(digest.some((line) => line.startsWith("code touch: a Bash write")));
  const report = renderReport(
    DATA,
    "log",
    new SessionRef("main", "a.jsonl"),
    null,
    scanned(codeTouch),
    [],
    new BudgetSummary(),
  );
  assert.ok(report.includes("| main sessions | 3 | 1 (33%) | 1 (33%) | 1 (33%) | 1 |"));
  assert.ok(report.includes("| subagents | 3 | 1 (33%) | 0 (0%) | 2 (67%) | 1 |"));
  assert.ok(report.includes("| k_explorer | 2 | 2 | 100% |"));
  assert.ok(report.includes("upper bound"));
  assert.ok(report.indexOf("## Tokens") < report.indexOf("## Code touch"));
  assert.ok(report.indexOf("## Code touch") < report.indexOf("## Budget"));
});

test("the digest with no session says so once; an empty group is named", () => {
  const root = scratch();
  for (const codeTouch of [null, collectCodeTouch(root, rules)]) {
    const lines = renderDigest(DATA, null, scanned(codeTouch), [], new BudgetSummary(), "r.md").split("\n");
    assert.ok(lines.includes("code touch: no session transcript with a user turn"));
    assert.ok(!lines.some((line) => line.startsWith("code touch,")));
  }
  writeLines(path.join(root, "a.jsonl"), [prompt()]);
  const lines = renderDigest(DATA, null, scanned(collectCodeTouch(root, rules)), [], new BudgetSummary(), "r.md").split(
    "\n",
  );
  assert.ok(lines.includes("code touch, subagents: no transcript with a user turn"));
  assert.ok(!lines.some((line) => line.includes("by subagent type")));
});

test("main: the code-touch scan covers the directory of the located transcript", async () => {
  const root = scratch();
  const sessions = path.join(root, "sessions");
  codeTouchFixture(sessions);
  const result = await run([
    "--project-root",
    root,
    "--transcript",
    path.join(sessions, "a.jsonl"),
    "--no-budget",
    "--report-dir",
    path.join(root, "out"),
  ]);
  assert.equal(result.code, 0);
  assert.match(result.stdout, /\ncode touch, main sessions \(n=3\)/);
});

test("the median is whole for an odd count and half steps for an even one", () => {
  const touches = (/** @type {number[]} */ turns) => turns.map((turn) => new SessionTouch(CODE_READ, turn));
  const median = (/** @type {number[]} */ turns) =>
    renderDigest(
      DATA,
      null,
      scanned({ scanned: "d", main: touches(turns), subagents: [] }),
      [],
      new BudgetSummary(),
      "r.md",
    ).match(/median first touch at user turn (\S+)/)?.[1];
  assert.equal(median([3, 1, 2]), "2");
  assert.equal(median([1, 3]), "2");
  assert.equal(median([1, 2]), "1.5");
});

test("a share rounds halves up in integer arithmetic", () => {
  const share = (/** @type {number} */ count) =>
    renderDigest(
      DATA,
      null,
      scanned({
        scanned: "d",
        main: [
          ...Array.from({ length: count }, () => new SessionTouch(CODE_EDIT, 1)),
          ...Array.from({ length: 8 - count }, () => new SessionTouch(NO_CODE, null)),
        ],
        subagents: [],
      }),
      [],
      new BudgetSummary(),
      "r.md",
    ).match(/code-edit \d+ \((\d+)%\)/)?.[1];
  assert.deepEqual([0, 1, 2, 3, 4, 5, 6, 7, 8].map(share), ["0", "13", "25", "38", "50", "63", "75", "88", "100"]);
});
