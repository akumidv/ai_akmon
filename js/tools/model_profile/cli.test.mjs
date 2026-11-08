import { test } from "node:test";
import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import fs from "node:fs";
import { createServer } from "node:http";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";

import { defaultItemSet, parseArgs } from "./cli.mjs";
import { hostCanFakeDocker, installFakeDocker, readJsonl, tempDir, withoutDocker } from "./support.test.mjs";

const SKIP_WITHOUT_HOST = hostCanFakeDocker() ? false : "the fake docker needs python3 and tar on PATH";
const TOKEN = "s3cret-value";

const CLI = fileURLToPath(new URL("./cli.mjs", import.meta.url));
const execFileAsync = promisify(execFile);

/**
 * Run the command as a program, with stdout and stderr captured. The endpoint of these tests lives in
 * this process, so the child is async: a blocking spawn would starve the server.
 * @param {string[]} argv
 * @param {Record<string, string | undefined>} [environ]
 * @param {{cwd?: string}} [options]
 * @returns {Promise<{code: number, out: string, err: string}>}
 */
async function run(argv, environ = {}, { cwd = process.cwd() } = {}) {
  const env = { ...process.env, ...environ };
  delete env.AKMON_MODEL_TOKEN;
  Object.assign(env, environ);
  try {
    const done = await execFileAsync(process.execPath, [CLI, ...argv], { env, cwd, encoding: "utf8" });
    return { code: 0, out: done.stdout, err: done.stderr };
  } catch (exc) {
    const failure = /** @type {{code: number, stdout: string, stderr: string}} */ (exc);
    return { code: failure.code, out: failure.stdout, err: failure.stderr };
  }
}

/**
 * A local OpenAI-compatible endpoint: it lists two models and answers every completion with the
 * same canned stream.
 * @param {(body: any) => string} answerOf
 * @returns {Promise<{url: string, requests: any[], close: () => void}>}
 */
async function endpoint(answerOf) {
  /** @type {any[]} */
  const requests = [];
  const server = createServer((request, response) => {
    let body = "";
    request.on("data", (chunk) => (body += chunk));
    request.on("end", () => {
      if (request.url === "/v1/models") {
        response.end(JSON.stringify({ data: [{ id: "m1" }, { id: "m2" }] }));
        return;
      }
      const parsed = JSON.parse(body);
      requests.push({ auth: request.headers.authorization, body: parsed });
      const lines = [
        { choices: [{ delta: { content: answerOf(parsed) } }] },
        { choices: [{ delta: {}, finish_reason: "stop" }] },
        { choices: [], usage: { prompt_tokens: 20, completion_tokens: 6 } },
      ];
      response.writeHead(200, { "Content-Type": "text/event-stream" });
      response.end(`${lines.map((line) => `data: ${JSON.stringify(line)}\n\n`).join("")}data: [DONE]\n\n`);
    });
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", () => resolve(undefined)));
  const { port } = /** @type {import("node:net").AddressInfo} */ (server.address());
  return {
    url: `http://127.0.0.1:${port}/v1/`,
    requests,
    close: () => {
      server.closeAllConnections();
      server.close();
    },
  };
}

const answerFor = (/** @type {any} */ body) =>
  body.messages[0].content.includes("file.py:function") ? "invoice.py:total" : "```python\nx = 1\n```\n";

test("the arguments are the Python twin's: lists take every value up to the next option", () => {
  const args = parseArgs([
    "probe",
    "--endpoint",
    "https://e.example",
    "--models",
    "a",
    "b",
    "--families",
    "hunt",
    "--yes",
  ]);

  assert.ok(typeof args === "object");
  assert.deepEqual(args.models, ["a", "b"]);
  assert.deepEqual(args.families, ["hunt"]);
  assert.equal(args.yes, true);
  assert.equal(args.tokenBudget, null);
  assert.equal(args.tokenEnv, "AKMON_MODEL_TOKEN");
  assert.equal(args.items, defaultItemSet());
});

test("a token budget must be a positive integer", async () => {
  for (const bad of ["0", "-3", "abc", "1.5"]) {
    const shown = await run(["probe", "--token-budget", bad]);
    assert.equal(shown.code, 2, bad);
    assert.match(shown.err, /^model_profile: error: argument --token-budget: must be a positive integer/);
  }
  assert.equal(/** @type {any} */ (parseArgs(["probe", "--token-budget=5000"])).tokenBudget, 5000);
});

test("a usage error is one line and exit 2; help is exit 0", async () => {
  assert.equal((await run([])).code, 2);
  assert.match((await run(["fly"])).err, /invalid choice: 'fly'/);
  assert.match((await run(["gate", "--endpoint", "x"])).err, /unrecognized arguments: --endpoint/);
  assert.match((await run(["probe", "--out"])).err, /expected one argument/);
  const help = await run(["--help"]);
  assert.equal(help.code, 0);
  assert.match(help.out, /usage: model_profile/);
});

test("plan with named models needs no endpoint", async () => {
  const shown = await run(["plan", "--models", "a", "b", "--families", "hunt"]);

  assert.equal(shown.code, 0);
  assert.match(shown.out, /1 \(case, family\) pairs x 2 models = 2 calls/);
  assert.match(shown.out, /^item set {5}seed-1 {2}cases_sha [0-9a-f]{12} {2}envelope_sha [0-9a-f]{12}$/m);
});

test("probe needs an endpoint and a token, and names the variable, not a value", async () => {
  const noEndpoint = await run(["probe"], { AKMON_MODEL_TOKEN: "t" });
  assert.equal(noEndpoint.code, 1);
  assert.match(noEndpoint.err, /--endpoint/);

  const noToken = await run(["probe", "--endpoint", "https://endpoint.example", "--token-env", "MY_TOKEN"], {});
  assert.equal(noToken.code, 1);
  assert.match(noToken.err, /MY_TOKEN/);
});

test("probe without --yes prints the plan and sends nothing", async () => {
  const server = await endpoint(answerFor);
  try {
    const shown = await run(["probe", "--endpoint", server.url, "--models", "m1", "--token-env", "MY_TOKEN"], {
      MY_TOKEN: TOKEN,
    });

    assert.equal(shown.code, 2);
    assert.match(shown.out, /nothing was sent/);
    assert.match(shown.out, /1 models = 3 calls/);
    assert.ok(!(shown.out + shown.err).includes(TOKEN));
    assert.deepEqual(server.requests, []);
  } finally {
    server.close();
  }
});

test("probe refuses a model the endpoint does not serve", async () => {
  const server = await endpoint(answerFor);
  try {
    const shown = await run(["probe", "--endpoint", server.url, "--models", "ghost"], { AKMON_MODEL_TOKEN: "t" });

    assert.equal(shown.code, 1);
    assert.match(shown.err, /does not serve ghost; it serves m1, m2/);
  } finally {
    server.close();
  }
});

test("gate reports each case, and says docker is needed", { skip: SKIP_WITHOUT_HOST }, async () => {
  const refused = await withoutDocker(() => run(["gate"], { PATH: process.env.PATH }));
  assert.equal(refused.code, 1);
  assert.match(refused.err, /docker/);

  const restore = installFakeDocker();
  try {
    const shown = await run(["gate"]);
    assert.equal(shown.code, 0, shown.out + shown.err);
    assert.match(shown.out, /^ok {5} invoice-coupon: /m);
    assert.match(shown.out, /2 of 2 case\(s\) usable/);
  } finally {
    restore();
  }
});

test("probe with --yes runs the whole path and never writes the token", { skip: SKIP_WITHOUT_HOST }, async () => {
  const server = await endpoint(answerFor);
  const restore = installFakeDocker();
  const out = join(tempDir(), "run");
  try {
    const shown = await run(
      ["probe", "--endpoint", server.url, "--models", "m1", "--yes", "--token-budget", "5000", "--out", out],
      { AKMON_MODEL_TOKEN: TOKEN },
    );

    assert.equal(shown.code, 0, shown.out + shown.err);
    assert.match(shown.out, /budget {7}5,000 tokens per model/);
    assert.match(shown.out, new RegExp(`writing {6}${out}`));
    assert.match(shown.out, /ledger {6}/);
    assert.match(shown.out, /item_pass_band {2}/);
    assert.equal(server.requests.length, 3);
    assert.ok(server.requests.every((request) => request.auth === `Bearer ${TOKEN}`));
    const ledger = readJsonl(join(out, "ledger.jsonl"));
    assert.deepEqual(ledger.map((row) => [row.model, row.stage, row.complete]).sort(), [
      ["m1", "fix-symptom", true],
      ["m1", "fix-traceback", true],
      ["m1", "hunt", true],
    ]);
    for (const name of fs.readdirSync(out, { recursive: true, encoding: "utf8" })) {
      const path = join(out, name);
      if (fs.statSync(path).isFile()) {
        assert.ok(!fs.readFileSync(path, "utf8").includes(TOKEN), name);
      }
    }
    assert.ok(!(shown.out + shown.err).includes(TOKEN));
  } finally {
    restore();
    server.close();
  }
});

test("the default output directory is the local layer of the project", { skip: SKIP_WITHOUT_HOST }, async () => {
  const project = fs.realpathSync(tempDir());
  fs.writeFileSync(join(project, "AGENTS.md"), "project\n");
  fs.writeFileSync(join(project, ".aitna-root"), "meta\n");
  const server = await endpoint(answerFor);
  const restore = installFakeDocker();
  try {
    const shown = await run(
      ["probe", "--endpoint", server.url, "--models", "m1", "--families", "hunt", "--yes"],
      { AKMON_MODEL_TOKEN: TOKEN },
      { cwd: project },
    );

    assert.equal(shown.code, 0, shown.out + shown.err);
    const runs = fs.readdirSync(join(project, "meta", ".local", "model_profile"));
    assert.equal(runs.length, 1);
    assert.match(runs[0], /^\d{8}T\d{6}Z$/);
    assert.ok(fs.existsSync(join(project, "meta", ".local", "model_profile", runs[0], "ledger.jsonl")));
  } finally {
    restore();
    server.close();
  }
});

test("without a project root the default output directory is refused", async () => {
  const server = await endpoint(answerFor);
  try {
    const shown = await run(
      ["probe", "--endpoint", server.url, "--models", "m1", "--yes"],
      { AKMON_MODEL_TOKEN: TOKEN },
      { cwd: tempDir() },
    );

    assert.equal(shown.code, 1);
    assert.match(shown.err, /--out/);
    assert.deepEqual(server.requests, []);
  } finally {
    server.close();
  }
});
