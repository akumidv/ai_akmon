// Shared fixtures for the model-profile tests — no test of its own. `*.test.mjs` is kept out of both
// carriers, so this helper never ships.
//
// The sandbox is exercised for real without a container daemon: `installFakeDocker` puts a `docker`
// program on PATH that unpacks the tar stream the way the container's `tar -xf -` would and runs the
// shipped in-container runner with the host `python3`. The one test that needs a real daemon
// (`docker.test.mjs`) skips itself when `docker version` fails.
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import { delimiter, join } from "node:path";

import { makeEnvelope } from "./cases.mjs";

/** The defective file of the fixture case, in its buggy and in its fixed form. */
export const BUGGY_SOURCE = "def compute(x):\n    return x + 1\n";
export const FIXED_SOURCE = "def compute(x):\n    return x\n";
export const FIX_ANSWER = `\`\`\`python\n${FIXED_SOURCE}\`\`\`\n`;
export const STAMP = new Date("2026-03-01T12:00:00.000Z");

/**
 * A one-item case: a buggy program, a decoy, its fixed twin, an oracle and one ask.
 * @param {string} [id]
 * @param {string} [family]
 * @returns {import("./cases.mjs").Case}
 */
export function makeFixtureCase(id = "fixture-case", family = "hunt") {
  return {
    id,
    families: [family],
    bug: { file: "pkg/mod.py", function: "compute", kind: "off-by-one" },
    files: { "pkg/mod.py": BUGGY_SOURCE, "pkg/decoy.py": "def other():\n    return 0\n" },
    fixedFiles: { "pkg/mod.py": FIXED_SOURCE },
    hiddenTest: { path: "tests/test_mod.py", content: "def test_compute():\n    assert compute(1) == 1\n" },
    asks: { [family]: { system: "Name the defect.", user: "Where is the defect?" } },
  };
}

/**
 * An item set over the given cases — the hashes are what the ledger row carries.
 * @param {...import("./cases.mjs").Case} cases
 * @returns {import("./cases.mjs").ItemSet}
 */
export function makeItemSet(...cases) {
  return {
    version: "fixture-1",
    cases,
    casesSha: "cases-sha",
    envelopeSha: "envelope-sha",
    families: [...new Set(cases.flatMap((item) => item.families))].sort(),
  };
}

/**
 * A sandbox stub that refuses to run — the container is never reached from a unit test.
 * @returns {import("./sandbox.mjs").SandboxResult}
 */
export function neverRun() {
  throw new Error("the container sandbox must not be reached from a unit test");
}

/** A sandbox stub whose hidden test fails, whatever program it is given. */
export function alwaysFails() {
  return { passed: false, tests: { test_compute: "failed" } };
}

/**
 * A sandbox stub that separates the two programs, as a real hidden test does.
 * @param {Record<string, string>} files
 * @returns {import("./sandbox.mjs").SandboxResult}
 */
export function separatingRunner(files) {
  const buggy = files["pkg/mod.py"].includes(BUGGY_SOURCE);
  return { passed: !buggy, tests: { test_compute: buggy ? "failed" : "passed" } };
}

/**
 * @param {string} [model]
 * @returns {import("./transport.mjs").RequestVariant}
 */
export function makeVariant(model = "probe-model") {
  return { model, temperature: 0, maxOutputTokens: 4096, timeoutS: 180, scaffold: "direct" };
}

/**
 * @param {string} text
 * @param {{promptTokens?: number, completionTokens?: number}} [usage]
 * @returns {import("./transport.mjs").Answer}
 */
export function makeAnswer(text, { promptTokens = 10, completionTokens = 5 } = {}) {
  return { kind: "answer", text, usage: { promptTokens, completionTokens }, latencyS: 1, variant: makeVariant() };
}

/**
 * @param {string} [reason]
 * @param {{promptTokens?: number, completionTokens?: number}} [usage]
 * @returns {import("./transport.mjs").Deferral}
 */
export function makeDeferral(
  reason = "the endpoint could not be reached",
  { promptTokens = 0, completionTokens = 0 } = {},
) {
  return { kind: "deferral", reason, latencyS: 0.5, variant: makeVariant(), usage: { promptTokens, completionTokens } };
}

/** A channel that returns what a script says — no socket, no token. */
export class StubChannel {
  /** @param {(model: string, call: number) => import("./transport.mjs").Completion} script */
  constructor(script) {
    this.endpoint = "https://endpoint.example/v1/chat/completions";
    this._script = script;
    /** @type {string[]} */
    this.calls = [];
  }

  /** @param {string} model */
  variant(model) {
    return makeVariant(model);
  }

  /**
   * @param {string} model
   * @returns {Promise<import("./transport.mjs").Completion>}
   */
  async complete(model) {
    this.calls.push(model);
    return this._script(model, this.calls.length);
  }
}

/**
 * A fresh temporary directory.
 * @returns {string}
 */
export function tempDir() {
  return fs.mkdtempSync(join(os.tmpdir(), "model-profile-test-"));
}

/**
 * The lines of a JSONL file, parsed.
 * @param {string} path
 * @returns {any[]}
 */
export function readJsonl(path) {
  return fs
    .readFileSync(path, "utf8")
    .split("\n")
    .filter((line) => line !== "")
    .map((line) => JSON.parse(line));
}

/** The default envelope, as the tests spell it. */
export function defaultEnvelope() {
  return makeEnvelope();
}

/** @returns {boolean} whether the host has what the fake docker runs the container's program with */
export function hostCanFakeDocker() {
  const python = spawnSync("python3", ["--version"]);
  const tar = spawnSync("tar", ["--version"]);
  return python.status === 0 && tar.status === 0;
}

const FAKE_DOCKER = `#!/usr/bin/env node
// A stand-in for \`docker\`: \`version\` and \`rm\` succeed; \`run\` unpacks the tar on stdin into a scratch
// directory standing for /work and runs the container's program with the host python3.
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const argv = process.argv.slice(2);
if (argv[0] === "version" || argv[0] === "rm") {
  process.exit(0);
}
const image = argv.indexOf("python:3.13-slim");
const command = argv.slice(image + 1);
const stdin = fs.readFileSync(0);
const work = fs.mkdtempSync(path.join(os.tmpdir(), "fake-work-"));
let done;
if (command[0] === "sh") {
  const script = command[2].replaceAll("/work", work).replace("exec python ", "exec python3 ");
  done = spawnSync("sh", ["-c", script], { input: stdin, cwd: work });
} else {
  done = spawnSync("python3", command.slice(1), { input: stdin });
}
fs.rmSync(work, { recursive: true, force: true });
process.stdout.write(done.stdout);
process.stderr.write(done.stderr);
process.exit(done.status ?? 1);
`;

/**
 * Put a fake \`docker\` first on PATH; returns the function that restores it.
 * @returns {() => void}
 */
export function installFakeDocker() {
  const directory = tempDir();
  const binary = join(directory, "docker");
  fs.writeFileSync(binary, FAKE_DOCKER, { mode: 0o755 });
  const saved = process.env.PATH;
  process.env.PATH = `${directory}${delimiter}${saved}`;
  return () => {
    process.env.PATH = saved;
    fs.rmSync(directory, { recursive: true, force: true });
  };
}

/**
 * Run `body` with a PATH that holds no docker at all.
 * @template T
 * @param {() => T} body
 * @returns {T}
 */
export function withoutDocker(body) {
  const saved = process.env.PATH;
  const empty = tempDir();
  process.env.PATH = empty;
  try {
    return body();
  } finally {
    process.env.PATH = saved;
    fs.rmSync(empty, { recursive: true, force: true });
  }
}

/**
 * An item set document the tests write to disk: two cases, with a non-ASCII system prompt and an
 * astral character in a source, so the hashes pin the escaping and the ordering the twins share.
 * @returns {Record<string, any>}
 */
export function fixtureDocument() {
  return {
    version: "fixture-doc-1",
    cases: [
      {
        id: "b-fix",
        families: ["fix-traceback", "fix-symptom"],
        bug: { file: "pkg/mod.py", function: "compute", kind: "off-by-one" },
        files: { "pkg/mod.py": BUGGY_SOURCE, "pkg/decoy.py": "def other():\n    return 0  # \u{1F600} decoy\n" },
        fixed_files: { "pkg/mod.py": FIXED_SOURCE },
        hidden_test: {
          path: "tests/test_mod.py",
          content: "from pkg.mod import compute\n\ndef test_compute():\n    assert compute(1) == 1\n",
        },
        asks: {
          "fix-traceback": {
            system: "Repair the file. Reply with one python block.",
            user: "A traceback: wrong value.",
          },
          "fix-symptom": { system: "Repair the file — symptom only.", user: "compute(1) is 2, not 1." },
        },
      },
      {
        id: "a-hunt",
        families: ["hunt"],
        bug: { file: "pkg/mod.py", function: "compute", kind: "off-by-one" },
        files: { "pkg/mod.py": BUGGY_SOURCE, "pkg/decoy.py": "def other():\n    return 0\n" },
        fixed_files: { "pkg/mod.py": FIXED_SOURCE },
        hidden_test: {
          path: "tests/test_mod.py",
          content: "from pkg.mod import compute\n\ndef test_compute():\n    assert compute(1) == 1\n",
        },
        asks: { hunt: { system: "Name the defect as file.py:function.", user: "Where is the defect?" } },
      },
    ],
  };
}

/**
 * Write a document as an item set file.
 * @param {string} directory
 * @param {Record<string, any>} document
 * @param {string} [name]
 * @returns {string} the path
 */
export function writeItems(directory, document, name = "items.json") {
  const path = join(directory, name);
  fs.writeFileSync(path, JSON.stringify(document), "utf8");
  return path;
}
