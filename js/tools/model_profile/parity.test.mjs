// The twins agree: the Python tool (`tools/model_profile/`) and this one compute the same hashes, the
// same scores, the same plan text, the same ledger and detail rows for the same inputs, and a ledger
// written by one reads in the other. The Python side runs as `python3`; the tests skip without it.
import { test } from "node:test";
import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import fs from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

import { loadItemSet, makeEnvelope } from "./cases.mjs";
import { formatG, isoformat, roundHalfEven, runProbe } from "./runner.mjs";
import { huntReason, parseLocation, scoreFix, scoreHunt } from "./scoring.mjs";
import * as settings from "./settings.mjs";
import {
  FIXED_SOURCE,
  STAMP,
  StubChannel,
  fixtureDocument,
  makeAnswer,
  makeDeferral,
  readJsonl,
  tempDir,
  writeItems,
} from "./support.test.mjs";

const REPO = fileURLToPath(new URL("../../../", import.meta.url));
const PYTHON_TOOL = join(REPO, "tools", "model_profile");
const SEED = join(PYTHON_TOOL, "items", "seed_cases.json");
const HAVE_PYTHON = spawnSync("python3", ["--version"]).status === 0;
const SKIP = HAVE_PYTHON ? false : "python3 is not on PATH";

/**
 * Run a Python program against the Python twin's modules; it prints one JSON document.
 * @param {string} program
 * @param {unknown} argument
 * @returns {any}
 */
function python(program, argument) {
  const prelude = `import json, sys\nsys.path.insert(0, ${JSON.stringify(PYTHON_TOOL)})\nargument = json.loads(sys.argv[1])\n`;
  const out = execFileSync("python3", ["-I", "-c", prelude + program, JSON.stringify(argument)], {
    encoding: "utf8",
    cwd: tempDir(),
  });
  return JSON.parse(out);
}

test("the case-set and envelope hashes are identical across the twins", { skip: SKIP }, () => {
  const directory = tempDir();
  const fixture = writeItems(directory, fixtureDocument());
  const paths = [SEED, fixture];
  const knobs = [
    {},
    { maxOutputTokens: 2048 },
    { temperature: 0.7, timeoutS: 60 },
    { temperature: 1, responseFormat: "json" },
  ];

  const fromPython = python(
    `
import cases
from pathlib import Path
rows = []
for path in argument["paths"]:
    for knob in argument["knobs"]:
        envelope = cases.Envelope(
            temperature=float(knob.get("temperature", 0.0)),
            max_output_tokens=knob.get("maxOutputTokens", 4096),
            timeout_s=knob.get("timeoutS", 180),
            response_format=knob.get("responseFormat", "text"),
        )
        item_set = cases.load_item_set(Path(path), envelope)
        rows.append([item_set.version, item_set.cases_sha, item_set.envelope_sha, list(item_set.families), [c.id for c in item_set.cases]])
print(json.dumps(rows))
`,
    { paths, knobs },
  );

  const fromJs = paths.flatMap((path) =>
    knobs.map((knob) => {
      const itemSet = loadItemSet(path, makeEnvelope(knob));
      return [itemSet.version, itemSet.casesSha, itemSet.envelopeSha, itemSet.families, itemSet.cases.map((c) => c.id)];
    }),
  );
  assert.deepEqual(fromJs, fromPython);
});

const HUNT_ANSWERS = [
  "pkg/mod.py:compute",
  "  pkg/mod.py:compute\n",
  "pkg/mod.py:other",
  "other/mod.py:compute",
  "pkg/mod.py",
  "pkg/mod.py:compute\nexplains itself",
  "I think it is pkg/mod.py:compute",
  "",
  "pkg/mod.py:",
  "a b.py:c",
  "pkg/mod.py:2bad",
  "pkg/mod.py:compute:extra",
  "é.py:f",
];

test("a hunt answer earns the same verdict and the same reason in both twins", { skip: SKIP }, () => {
  const fromPython = python(
    `
import scoring
rows = []
for answer in argument["answers"]:
    hit = scoring.score_hunt(answer, expected_file="pkg/mod.py", expected_function="compute")
    parsed = scoring.parse_location(answer)
    rows.append([list(parsed) if parsed else None, hit.hit, hit.file_hit, hit.function_hit, hit.malformed,
                 scoring.hunt_reason(hit, expected_file="pkg/mod.py", expected_function="compute")])
print(json.dumps(rows))
`,
    { answers: HUNT_ANSWERS },
  );

  const expected = { expectedFile: "pkg/mod.py", expectedFunction: "compute" };
  const fromJs = HUNT_ANSWERS.map((answer) => {
    const hit = scoreHunt(answer, expected);
    return [parseLocation(answer), hit.hit, hit.fileHit, hit.functionHit, hit.malformed, huntReason(hit, expected)];
  });
  assert.deepEqual(fromJs, fromPython);
});

/**
 * The host interpreter's own answer to "does this compile" — the stand-in for the container's.
 * @param {string} source
 * @returns {{compiled: boolean, detail: string}}
 */
function hostCompileCheck(source) {
  const done = spawnSync(
    "python3",
    [
      "-I",
      "-c",
      "import ast, sys\ntry:\n    ast.parse(sys.stdin.read())\nexcept (SyntaxError, ValueError) as exc:\n    print(exc)\n    sys.exit(1)\n",
    ],
    { input: source, encoding: "utf8" },
  );
  return { compiled: done.status === 0, detail: done.stdout.trim() };
}

const FIX_ANSWERS = [
  `\`\`\`python\n${FIXED_SOURCE}\`\`\`\n`,
  "no code at all",
  `\`\`\`python\n${FIXED_SOURCE}\`\`\`\n\`\`\`python\n${FIXED_SOURCE}\`\`\`\n`,
  "```python\ndef broken(:\n```\n",
  "```python\ndef compute(x):\n    return x + 2\n```\n",
  "```python\nx = '\u0000'\n```\n",
  "intro\n```python\ndef compute(x):\n    return x\n```\ntrailing prose",
];

test("a fix answer earns the same verdict and the same reason in both twins", { skip: SKIP }, () => {
  const document = fixtureDocument();
  const fixturePath = writeItems(tempDir(), document);

  const fromPython = python(
    `
import cases, scoring, sandbox
from pathlib import Path
item = next(c for c in cases.load_item_set(Path(argument["path"])).cases if c.id == "b-fix")
fixed = argument["fixed"]
def run_test(files, test_path, test_source):
    passed = files["pkg/mod.py"] == fixed
    return sandbox.SandboxResult(passed=passed, tests={"test_compute": "passed" if passed else "failed"})
rows = []
for answer in argument["answers"]:
    verdict = scoring.score_fix(answer, item, run_test)
    rows.append([verdict.passed, verdict.reason, verdict.compiled, list(verdict.failed_tests)])
print(json.dumps(rows))
`,
    { path: fixturePath, answers: FIX_ANSWERS, fixed: FIXED_SOURCE },
  );

  const item = loadItemSet(fixturePath).cases.find((candidate) => candidate.id === "b-fix");
  assert.ok(item);
  const runTest = (/** @type {Record<string, string>} */ files) => {
    const passed = files["pkg/mod.py"] === FIXED_SOURCE;
    return { passed, tests: { test_compute: passed ? "passed" : "failed" } };
  };
  const fromJs = FIX_ANSWERS.map((answer) => {
    const verdict = scoreFix(answer, item, runTest, hostCompileCheck);
    return [verdict.passed, verdict.reason, verdict.compiled, verdict.failedTests];
  });
  assert.deepEqual(fromJs, fromPython);
});

test("the plan text and exit code are identical across the twins", { skip: SKIP }, () => {
  const cli = join(REPO, "js", "tools", "model_profile", "cli.mjs");
  const pyCli = join(PYTHON_TOOL, "cli.py");
  const variants = [
    ["plan", "--models", "a", "b"],
    ["plan", "--models", "a", "--families", "hunt"],
    ["plan", "--models", "a", "--families", "fix-symptom", "fix-traceback", "--cases", "invoice-coupon"],
    ["plan", "--models", "x", "y", "z", "--cases", "inventory-available"],
    ["plan", "--models", "a", "--items", SEED],
    ["plan"],
    ["probe", "--token-env", "NO_SUCH_TOKEN_VARIABLE"],
  ];
  for (const argv of variants) {
    const js = spawnSync(process.execPath, [cli, ...argv], { encoding: "utf8" });
    const py = spawnSync("python3", [pyCli, ...argv], { encoding: "utf8" });
    assert.equal(js.status, py.status, argv.join(" "));
    assert.equal(js.stdout, py.stdout, argv.join(" "));
    assert.equal(js.stderr, py.stderr, argv.join(" "));
  }
});

test("a gate's number and a plan's minutes are spelled as Python spells them", { skip: SKIP }, () => {
  const values = [
    0,
    30,
    0.5,
    0.4,
    1 / 3,
    2 / 3,
    0.0001,
    0.00001,
    0.123456789,
    1234567,
    100000,
    123456.7,
    0.05,
    9.999995,
    1e-7,
  ];
  const ties = [0.5, 1.5, 2.5, 3.5, 4.5, 0.4, 0.6, 7, 12.5];

  const fromPython = python(
    `
print(json.dumps({"g": [format(v, "g") for v in argument["values"]], "round": [format(v, ".0f") for v in argument["ties"]]}))
`,
    { values, ties },
  );

  assert.deepEqual(values.map(formatG), fromPython.g);
  assert.deepEqual(
    ties.map((value) => String(roundHalfEven(value))),
    fromPython.round,
  );
});

test("a moment is written as Python's isoformat writes it", { skip: SKIP }, () => {
  const moments = [
    "2026-03-01T12:00:00.000Z",
    "2026-03-01T12:00:00.250Z",
    "2026-12-31T23:59:59.999Z",
    "1999-01-01T00:00:00.001Z",
  ];

  const fromPython = python(
    `
from datetime import datetime, UTC
print(json.dumps([datetime.fromisoformat(m.replace("Z", "+00:00")).astimezone(UTC).isoformat() for m in argument]))
`,
    moments,
  );

  assert.deepEqual(
    moments.map((moment) => isoformat(new Date(moment))),
    fromPython,
  );
});

/** A scripted channel: answers by call number; the same script runs on both twins. */
const SCRIPT = [
  { kind: "answer", text: `\`\`\`python\n${FIXED_SOURCE}\`\`\`\n`, prompt: 60, completion: 40 },
  { kind: "answer", text: "```python\ndef broken(:\n```\n", prompt: 60, completion: 40 },
  { kind: "answer", text: "pkg/mod.py:compute", prompt: 31, completion: 7 },
  { kind: "deferral", text: "the answer was cut off by the 4096-token cap", prompt: 1091, completion: 4096 },
  { kind: "answer", text: "```python\ndef compute(x):\n    return x + 5\n```\n", prompt: 12, completion: 9 },
  { kind: "answer", text: "I would look at pkg/mod.py", prompt: 20, completion: 3 },
];

/**
 * @param {Record<string, any>} entry
 * @returns {import("./transport.mjs").Completion}
 */
function scripted(entry) {
  const usage = { promptTokens: entry.prompt, completionTokens: entry.completion };
  return entry.kind === "answer" ? makeAnswer(entry.text, usage) : makeDeferral(entry.text, usage);
}

/**
 * Every row of a run directory, parsed: the ledger and each detail file by name.
 * @param {string} directory
 * @returns {Record<string, any[]>}
 */
function readRun(directory) {
  /** @type {Record<string, any[]>} */
  const run = { "ledger.jsonl": readJsonl(join(directory, "ledger.jsonl")) };
  for (const name of fs.readdirSync(join(directory, "detail")).sort()) {
    run[`detail/${name}`] = readJsonl(join(directory, "detail", name));
  }
  return run;
}

/** @type {[string, number | null][]} */
const RUNS = [
  ["no budget", null],
  ["a token budget", 150],
];

for (const [name, budget] of RUNS) {
  test(`a run writes the same ledger and detail rows in both twins: ${name}`, { skip: SKIP }, async () => {
    const itemsPath = writeItems(tempDir(), fixtureDocument());
    const pythonOut = join(tempDir(), "py");
    const jsOut = join(tempDir(), "js");

    python(
      `
import cases, runner, sandbox, transport
from datetime import datetime, UTC
from pathlib import Path

script = argument["script"]
fixed = argument["fixed"]

class Stub:
    endpoint = "https://endpoint.example/v1/chat/completions"
    def __init__(self):
        self.calls = 0
    def variant(self, model):
        return transport.RequestVariant(model=model, temperature=0.0, max_output_tokens=4096, timeout_s=180, scaffold="direct")
    def complete(self, model, system, user):
        entry = script[self.calls]
        self.calls += 1
        usage = transport.Usage(prompt_tokens=entry["prompt"], completion_tokens=entry["completion"])
        if entry["kind"] == "answer":
            return transport.Answer(text=entry["text"], usage=usage, latency_s=1.0, variant=self.variant(model))
        return transport.Deferral(reason=entry["text"], latency_s=0.5, variant=self.variant(model), usage=usage)

def run_test(files, test_path, test_source):
    passed = files["pkg/mod.py"] == fixed or files["pkg/mod.py"].endswith("return x\\n")
    return sandbox.SandboxResult(passed=passed, tests={"test_compute": "passed" if passed else "failed"})

item_set = cases.load_item_set(Path(argument["items"]))
options = runner.RunOptions(out_dir=Path(argument["out"]), run_test=run_test,
                            now=datetime(2026, 3, 1, 12, 0, tzinfo=UTC), token_budget=argument["budget"])
runner.run_probe(item_set, Stub(), runner.Selection(models=("m1", "m2")), options)
print("{}")
`,
      { script: SCRIPT, fixed: FIXED_SOURCE, items: itemsPath, out: pythonOut, budget },
    );

    let call = 0;
    const channel = new StubChannel(() => scripted(SCRIPT[call++]));
    /** @type {import("./sandbox.mjs").TestRunner} */
    const runTest = (files) => {
      const source = files["pkg/mod.py"];
      const passed = source === FIXED_SOURCE || source.endsWith("return x\n");
      return { passed, tests: { test_compute: passed ? "passed" : "failed" } };
    };
    await runProbe(
      loadItemSet(itemsPath),
      channel,
      { models: ["m1", "m2"] },
      {
        outDir: jsOut,
        runTest,
        compileCheck: hostCompileCheck,
        now: STAMP,
        tokenBudget: budget,
      },
    );

    assert.deepEqual(readRun(jsOut), readRun(pythonOut));
    assert.ok(readRun(jsOut)["ledger.jsonl"].length >= 4);
  });
}

test("a ledger written by one twin is read by the other", { skip: SKIP }, async () => {
  const itemsPath = writeItems(tempDir(), fixtureDocument());
  const jsOut = join(tempDir(), "js");
  let call = 0;
  await runProbe(
    loadItemSet(itemsPath),
    new StubChannel(() => scripted(SCRIPT[call++])),
    { models: ["m1"] },
    {
      outDir: jsOut,
      runTest: (files) => {
        const passed = files["pkg/mod.py"].endsWith("return x\n");
        return { passed, tests: { test_compute: passed ? "passed" : "failed" } };
      },
      compileCheck: hostCompileCheck,
      now: STAMP,
    },
  );

  const seen = python(
    `
import json
from pathlib import Path
out = Path(argument)
ledger = [json.loads(line) for line in (out / "ledger.jsonl").read_text(encoding="utf-8").splitlines()]
detail = {path.name: [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] for path in (out / "detail").iterdir()}
print(json.dumps({"stages": sorted(row["stage"] for row in ledger),
                  "pass_rates": {row["stage"]: row["metrics"]["pass_rate"] for row in ledger},
                  "details": {name: [row["verdict"] for row in rows] for name, rows in detail.items()}}))
`,
    jsOut,
  );

  assert.deepEqual(seen.stages, ["fix-symptom", "fix-traceback", "hunt"]);
  assert.deepEqual(seen.details, {
    "m1__fix-symptom.jsonl": ["fail"],
    "m1__fix-traceback.jsonl": ["pass"],
    "m1__hunt.jsonl": ["pass"],
  });
  assert.equal(seen.pass_rates.hunt, 1);
});

test("the settings both twins read are the one file", () => {
  assert.equal(settings.dataDir(), PYTHON_TOOL);
  const document = JSON.parse(fs.readFileSync(join(PYTHON_TOOL, settings.PROFILE_FILE), "utf8"));
  assert.equal(document.sandbox.image, settings.load().sandbox.image);
});
