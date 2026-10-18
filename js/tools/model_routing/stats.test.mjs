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
  SessionRef,
  aggregateDelegationLines,
  aggregateSubagentLines,
  aggregateTranscriptLines,
  budgetSummary,
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
    /^delegations: no delegations logged\norchestrator tokens: transcript unavailable\nsubagent tokens: no subagent transcripts\nbudget: unavailable \(skipped \(--no-budget\)\)\nreport: .*\/out\/stats-1\.md\n$/,
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
