import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { join } from "node:path";

import { GateRefusalError } from "./oracle.mjs";
import {
  RunnerError,
  buildPlan,
  evaluateGates,
  formatG,
  isoformat,
  itemBands,
  roundHalfEven,
  runProbe,
} from "./runner.mjs";
import { SandboxError } from "./sandbox.mjs";
import * as settings from "./settings.mjs";
import { InterruptedError } from "./transport.mjs";
import {
  FIX_ANSWER,
  STAMP,
  StubChannel,
  alwaysFails,
  makeAnswer,
  makeDeferral,
  makeFixtureCase,
  makeItemSet,
  readJsonl,
  separatingRunner,
  tempDir,
} from "./support.test.mjs";

/**
 * @param {string} directory
 * @param {Partial<import("./runner.mjs").RunOptions>} [overrides]
 * @returns {import("./runner.mjs").RunOptions}
 */
function options(directory, overrides = {}) {
  return { outDir: join(directory, "out"), runTest: separatingRunner, now: STAMP, ...overrides };
}

test("a refused case stops the run before any model is asked", async () => {
  const directory = tempDir();
  const channel = new StubChannel(() => makeAnswer("pkg/mod.py:compute"));

  await assert.rejects(
    runProbe(makeItemSet(makeFixtureCase()), channel, { models: ["m"] }, options(directory, { runTest: alwaysFails })),
    GateRefusalError,
  );

  assert.deepEqual(channel.calls, []);
  assert.ok(!fs.existsSync(join(directory, "out")));
});

test("a malformed hunt answer is counted apart and left out of the localization rates", async () => {
  const cases = [0, 1, 2].map((index) => makeFixtureCase(`case-${index}`));
  const answers = ["pkg/mod.py:compute", "pkg/mod.py:other", "The defect is in pkg/mod.py, function compute."];
  const channel = new StubChannel((_model, call) => makeAnswer(answers[call - 1]));

  const report = await runProbe(makeItemSet(...cases), channel, { models: ["m"] }, options(tempDir()));

  assert.deepEqual(
    report.attempts.map((attempt) => [attempt.caseId, attempt.outcome.verdict]),
    [
      ["case-0", "pass"],
      ["case-1", "fail"],
      ["case-2", "malformed"],
    ],
  );
  assert.equal(report.attempts[2].outcome.locationHit, null);
  const metrics = report.rows[0].metrics;
  assert.equal(metrics.malformed, 1);
  assert.equal(metrics.scored, 2);
  assert.equal(metrics.location_hit_rate, 0.5);
  assert.equal(metrics.file_localization_rate, 1);
});

test("a deferral is never scored as a miss", async () => {
  const cases = [0, 1, 2].map((index) => makeFixtureCase(`case-${index}`));
  const script = [makeAnswer("pkg/mod.py:compute"), makeDeferral(), makeDeferral()];
  const channel = new StubChannel((_model, call) => script[call - 1]);

  const report = await runProbe(makeItemSet(...cases), channel, { models: ["m"] }, options(tempDir()));

  assert.deepEqual(
    report.attempts.map((attempt) => attempt.outcome.verdict),
    ["pass", "deferred", "deferred"],
  );
  const metrics = report.rows[0].metrics;
  assert.deepEqual([metrics.pass_rate, metrics.scored, metrics.deferred, metrics.n], [1, 1, 2, 3]);
  const failed = evaluateGates(metrics, "hunt");
  assert.ok(failed.some((gate) => gate.startsWith("items_scored")));
  assert.ok(!failed.some((gate) => gate.startsWith("hunt.location_hit")));
});

test("a deferral keeps the usage the stream reported", async () => {
  const deferral = makeDeferral("the answer was cut off by the 4096-token cap", {
    promptTokens: 1091,
    completionTokens: 4096,
  });
  const channel = new StubChannel(() => deferral);

  const report = await runProbe(makeItemSet(makeFixtureCase()), channel, { models: ["m"] }, options(tempDir()));

  const outcome = report.attempts[0].outcome;
  assert.equal(outcome.verdict, "deferred");
  assert.deepEqual([outcome.promptTokens, outcome.completionTokens], [1091, 4096]);
});

test("the detail row carries the answer the model produced", async () => {
  const script = [makeAnswer("pkg/mod.py:compute"), makeDeferral()];
  const channel = new StubChannel((_model, call) => script[call - 1]);

  const report = await runProbe(
    makeItemSet(makeFixtureCase("a"), makeFixtureCase("b")),
    channel,
    { models: ["m"] },
    options(tempDir()),
  );

  assert.deepEqual(
    readJsonl(report.detailFiles[0]).map((row) => [row.verdict, row.answer]),
    [
      ["pass", "pkg/mod.py:compute"],
      ["deferred", ""],
    ],
  );
});

test("the ledger row carries the agreed keys", async () => {
  const directory = tempDir();
  const channel = new StubChannel(() => makeAnswer("pkg/mod.py:compute"));

  const report = await runProbe(
    makeItemSet(makeFixtureCase()),
    channel,
    { models: ["probe/model"] },
    options(directory),
  );

  const row = readJsonl(report.ledger)[0];
  assert.deepEqual(
    Object.keys(row).sort(),
    [
      "date",
      "ts",
      "target",
      "model",
      "endpoint",
      "request",
      "stage",
      "cases_sha",
      "system_sha",
      "sufficient",
      "complete",
      "failed",
      "metrics",
      "detail",
    ].sort(),
  );
  assert.equal(row.date, "2026-03-01");
  assert.equal(row.ts, "2026-03-01T12:00:00+00:00");
  assert.equal(row.target, "direct");
  assert.equal(row.endpoint, "https://endpoint.example/v1/chat/completions");
  assert.equal(row.request.model, "probe/model");
  assert.deepEqual(Object.keys(row.request), ["model", "temperature", "max_output_tokens", "timeout_s", "scaffold"]);
  assert.equal(row.stage, "hunt");
  assert.deepEqual([row.cases_sha, row.system_sha], ["cases-sha", "envelope-sha"]);
  assert.equal(row.complete, true);
  assert.equal(row.detail, "detail/probe_model__hunt.jsonl");
  assert.ok(fs.existsSync(join(directory, "out", row.detail)));
  assert.ok(row.failed[0].includes("items_scored"));
  assert.equal(row.sufficient, false);
});

test("a crash midway keeps every finished attempt and the partial ledger row", async () => {
  const directory = tempDir();
  const channel = new StubChannel((_model, call) => {
    if (call === 3) {
      throw new InterruptedError();
    }
    return makeAnswer("pkg/mod.py:compute");
  });
  const items = makeItemSet(makeFixtureCase("a"), makeFixtureCase("b"), makeFixtureCase("c"));

  await assert.rejects(runProbe(items, channel, { models: ["m"] }, options(directory)), InterruptedError);

  const detail = readJsonl(join(directory, "out", "detail", "m__hunt.jsonl"));
  assert.deepEqual(
    detail.map((row) => row.case_id),
    ["a", "b"],
  );
  const ledger = readJsonl(join(directory, "out", "ledger.jsonl"));
  assert.deepEqual(
    ledger.map((row) => [row.model, row.complete, row.sufficient]),
    [["m", false, false]],
  );
  assert.equal(ledger[0].metrics.scored, 2);
});

test("an interrupt signal stops the run between two questions", async () => {
  const directory = tempDir();
  const controller = new AbortController();
  const channel = new StubChannel(() => {
    controller.abort();
    return makeAnswer("pkg/mod.py:compute");
  });
  const items = makeItemSet(makeFixtureCase("a"), makeFixtureCase("b"));

  await assert.rejects(
    runProbe(items, channel, { models: ["m"] }, options(directory, { signal: controller.signal })),
    InterruptedError,
  );

  assert.deepEqual(channel.calls, ["m"]);
  assert.equal(readJsonl(join(directory, "out", "ledger.jsonl"))[0].complete, false);
});

test("a sandbox failure keeps the answer it could not grade and stops the run", async () => {
  const directory = tempDir();
  let runs = 0;
  /** @type {import("./sandbox.mjs").TestRunner} */
  const flaky = (files) => {
    runs += 1;
    if (runs === 8) {
      // the gate takes two runs for each of the three cases; 7 grades "a", 8 grades "b"
      throw new SandboxError("docker failed");
    }
    return separatingRunner(files);
  };
  const channel = new StubChannel(() => makeAnswer(FIX_ANSWER));
  const items = makeItemSet(
    makeFixtureCase("a", "fix-symptom"),
    makeFixtureCase("b", "fix-symptom"),
    makeFixtureCase("c", "fix-symptom"),
  );
  const stubbed = options(directory, { runTest: flaky, compileCheck: () => ({ compiled: true, detail: "" }) });

  await assert.rejects(runProbe(items, channel, { models: ["m"] }, stubbed), SandboxError);

  const detail = readJsonl(join(directory, "out", "detail", "m__fix-symptom.jsonl"));
  assert.deepEqual(
    detail.map((row) => [row.case_id, row.verdict]),
    [
      ["a", "pass"],
      ["b", "deferred"],
    ],
  );
  assert.equal(detail[1].answer, FIX_ANSWER);
  assert.match(detail[1].reason, /sandbox error/);
  assert.deepEqual(channel.calls, ["m", "m"]);
  assert.equal(readJsonl(join(directory, "out", "ledger.jsonl"))[0].complete, false);
});

test("a second run into the same directory appends", async () => {
  const directory = tempDir();
  const channel = new StubChannel(() => makeAnswer("pkg/mod.py:compute"));

  await runProbe(makeItemSet(makeFixtureCase()), channel, { models: ["m"] }, options(directory));
  await runProbe(makeItemSet(makeFixtureCase()), channel, { models: ["m"] }, options(directory));

  assert.equal(readJsonl(join(directory, "out", "ledger.jsonl")).length, 2);
  assert.equal(readJsonl(join(directory, "out", "detail", "m__hunt.jsonl")).length, 2);
});

test("the token budget defers a model's remaining attempts with the reason budget", async () => {
  const channel = new StubChannel(() => makeAnswer("pkg/mod.py:compute", { promptTokens: 60, completionTokens: 40 }));
  const items = makeItemSet(...[0, 1, 2, 3].map((index) => makeFixtureCase(`case-${index}`)));

  const report = await runProbe(items, channel, { models: ["m1", "m2"] }, options(tempDir(), { tokenBudget: 150 }));

  assert.deepEqual(channel.calls, ["m1", "m1", "m2", "m2"]);
  for (const model of ["m1", "m2"]) {
    const attempts = report.attempts.filter((attempt) => attempt.model === model);
    assert.deepEqual(
      attempts.map((attempt) => attempt.outcome.verdict),
      ["pass", "pass", "deferred", "deferred"],
    );
    assert.deepEqual(
      attempts.slice(2).map((attempt) => attempt.outcome.reason),
      [settings.load().run.budgetReason, settings.load().run.budgetReason],
    );
  }
  const row = report.rows.find((candidate) => candidate.model === "m1");
  assert.deepEqual([row?.metrics.deferred, row?.metrics.scored], [2, 2]);
});

test("a deferral's spend counts against the budget", async () => {
  const channel = new StubChannel(() => makeDeferral("cut off", { promptTokens: 100, completionTokens: 4096 }));
  const items = makeItemSet(makeFixtureCase("a"), makeFixtureCase("b"));

  const report = await runProbe(items, channel, { models: ["m"] }, options(tempDir(), { tokenBudget: 1000 }));

  assert.deepEqual(channel.calls, ["m"]);
  assert.deepEqual(
    report.attempts.map((attempt) => attempt.outcome.reason),
    ["cut off", settings.load().run.budgetReason],
  );
});

test("without a budget nothing is skipped", async () => {
  const channel = new StubChannel(() => makeAnswer("pkg/mod.py:compute", { promptTokens: 10 ** 6 }));
  const items = makeItemSet(makeFixtureCase("a"), makeFixtureCase("b"));

  const report = await runProbe(items, channel, { models: ["m"] }, options(tempDir()));

  assert.deepEqual(channel.calls, ["m", "m"]);
  assert.deepEqual([...new Set(report.attempts.map((attempt) => attempt.outcome.verdict))], ["pass"]);
});

test("the model gates are declared data in one place", () => {
  const bars = Object.fromEntries(
    settings.load().gates.map((gate) => [gate.name, [gate.family, gate.metric, gate.operator, gate.threshold]]),
  );

  assert.deepEqual(bars, {
    items_scored: [null, "scored", ">=", 30],
    "hunt.location_hit": ["hunt", "location_hit_rate", ">=", 0.5],
    "hunt.file_localization": ["hunt", "file_localization_rate", ">=", 0.5],
    "fix-traceback.pass_rate": ["fix-traceback", "pass_rate", ">=", 0.5],
    "fix-symptom.pass_rate": ["fix-symptom", "pass_rate", ">=", 0.5],
  });
});

test("a failed model gate names itself, its number and what it means", () => {
  assert.deepEqual(evaluateGates({ scored: 40, location_hit_rate: 0.4, file_localization_rate: 0.9 }, "hunt"), [
    "hunt.location_hit 0.4 >= 0.5 - the model cannot name the file and the function that hold the defect",
  ]);
  assert.deepEqual(evaluateGates({ scored: 40, pass_rate: 0.5 }, "fix-symptom"), []);
  assert.ok(evaluateGates({ scored: 40 }, "fix-symptom")[0].startsWith("fix-symptom.pass_rate n/a"));
});

test("a gate's number is written the way Python's :g writes it", () => {
  assert.deepEqual([0, 30, 0.5, 1 / 3, 0.0001, 0.00001, 1234567, 100000, 123456.7].map(formatG), [
    "0",
    "30",
    "0.5",
    "0.333333",
    "0.0001",
    "1e-05",
    "1.23457e+06",
    "100000",
    "123457",
  ]);
});

test("a tie rounds to the even neighbour, as Python's .0f does", () => {
  assert.deepEqual([0.5, 1.5, 2.5, 3.5, 0.4, 0.6, 4].map(roundHalfEven), [0, 2, 2, 4, 0, 1, 4]);
});

test("a moment is written the way Python's isoformat writes a UTC one", () => {
  assert.equal(isoformat(new Date("2026-03-01T12:00:00.000Z")), "2026-03-01T12:00:00+00:00");
  assert.equal(isoformat(new Date("2026-03-01T12:00:00.250Z")), "2026-03-01T12:00:00.250000+00:00");
});

/**
 * @param {string} caseId
 * @param {string} model
 * @param {string} verdict
 * @returns {import("./runner.mjs").Attempt}
 */
function scored(caseId, model, verdict) {
  return {
    model,
    caseId,
    family: "hunt",
    scaffold: "direct",
    envelopeSha: "e",
    casesSha: "c",
    seed: "s",
    ts: "t",
    outcome: {
      verdict,
      reason: "r",
      promptTokens: 0,
      completionTokens: 0,
      latencyS: 0,
      answer: "",
      locationHit: null,
      fileHit: null,
    },
  };
}

test("the item band is a separate gate from the model bars", () => {
  const band = settings.load().itemBand;

  assert.deepEqual([band.name, band.low, band.high], ["item_pass_band", 0.3, 0.7]);
  assert.ok(!settings.load().gates.some((gate) => gate.name === band.name));
});

test("item bands flag an item every model passes or fails and keep the discriminating one", () => {
  const models = ["m1", "m2", "m3", "m4"];
  const attempts = [
    ...models.map((model) => scored("easy", model, "pass")),
    ...models.map((model) => scored("hard", model, "fail")),
    ...models.map((model, index) => scored("mid", model, index < 2 ? "pass" : "fail")),
    ...models.map((model, index) => scored("edge", model, index < 3 ? "pass" : "fail")),
    scored("thin", "m1", "pass"),
    scored("thin", "m2", "pass"),
    scored("thin", "m3", "deferred"),
  ];

  const bands = Object.fromEntries(itemBands(attempts).map((band) => [band.caseId, [band.status, band.passRate]]));

  assert.deepEqual(bands, {
    easy: ["outside_band", 1],
    hard: ["outside_band", 0],
    mid: ["in_band", 0.5],
    edge: ["outside_band", 0.75],
    thin: ["pool_too_small", 1],
  });
});

test("the band edges are inclusive", () => {
  const ten = [
    ...Array.from({ length: 10 }, (_, index) => scored("low", `m${index}`, index < 3 ? "pass" : "fail")),
    ...Array.from({ length: 10 }, (_, index) => scored("high", `m${index}`, index < 7 ? "pass" : "fail")),
  ];

  assert.deepEqual(Object.fromEntries(itemBands(ten).map((band) => [band.caseId, band.status])), {
    low: "in_band",
    high: "in_band",
  });
});

test("a run reports the item bands", async () => {
  const channel = new StubChannel(() => makeAnswer("pkg/mod.py:compute"));

  const report = await runProbe(makeItemSet(makeFixtureCase()), channel, { models: ["m"] }, options(tempDir()));

  assert.deepEqual(
    report.itemBands.map((band) => [band.caseId, band.status]),
    [["fixture-case", "pool_too_small"]],
  );
});

test("the plan counts calls and prices the sandbox for fix families only", () => {
  const items = makeItemSet(makeFixtureCase("a", "hunt"), makeFixtureCase("b", "fix-symptom"));

  const plan = buildPlan(items, { models: ["m1", "m2"] });

  assert.deepEqual(plan.pairs, [
    ["a", "hunt"],
    ["b", "fix-symptom"],
  ]);
  assert.equal(plan.calls, 4);
  const { callSeconds, sandboxSeconds, outputTokens } = settings.load().estimate;
  assert.equal(plan.estimatedMinutes, Number(((4 * callSeconds + 2 * sandboxSeconds) / 60).toFixed(1)));
  assert.equal(plan.estimatedOutputTokens, 4 * outputTokens);
  assert.deepEqual(buildPlan(items, { models: ["m"], families: ["hunt"] }).pairs, [["a", "hunt"]]);
});

test("an empty selection is refused", async () => {
  const channel = new StubChannel(() => makeAnswer("x"));
  const items = makeItemSet(makeFixtureCase());

  await assert.rejects(runProbe(items, channel, { models: [] }, options(tempDir())), (exc) => {
    assert.ok(exc instanceof RunnerError);
    assert.match(exc.message, /no model/);
    return true;
  });
  await assert.rejects(
    runProbe(items, channel, { models: ["m"], families: ["fix-symptom"] }, options(tempDir())),
    /no \(case, family\) pair/,
  );
});
