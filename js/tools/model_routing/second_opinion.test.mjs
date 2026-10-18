/**
 * node:test for `js/tools/model_routing/second_opinion.mjs` — the helpers, the argument errors and
 * a run through a stand-in provider CLI. The byte-level spec is the `tools/second-opinion-*`
 * scenarios of `meta/conformance/scenarios`, run by `runner.py --impl node --area tools`.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { digest, main, readJsonObject, reportPrefix, reviewPrompt } from "./second_opinion.mjs";

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
 * A scratch project root with a gate pack.
 * @returns {string}
 */
function project() {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "second-opinion-test-"));
  fs.writeFileSync(path.join(root, "AGENTS.md"), "x\n");
  fs.writeFileSync(path.join(root, "pack.md"), "material\n");
  return root;
}

test("reportPrefix sanitises the gate and the task, keeping the task's case", () => {
  assert.equal(reportPrefix("design/align!"), "design-align");
  assert.equal(reportPrefix("///"), "gate");
  assert.equal(reportPrefix("g", "C7"), "C7-g");
  assert.equal(reportPrefix("g", "a/b"), "a-b-g");
});

test("digest keeps a short text and truncates a long one with the suffix", () => {
  const gate = { truncation_suffix_report: "\n...cut" };
  assert.equal(digest(gate, "  short \n"), "short");
  assert.equal(digest(gate, `${"a".repeat(1300)}`), `${"a".repeat(1200)}\n...cut`);
});

test("reviewPrompt fills the gate and the material", () => {
  const texts = {
    prompt: "G={{gate}} M={{material}}",
    unavailable_notice: [],
    report_dir_outside: "",
    summary: { report_line: "", provider_line: "", result_line: "" },
  };
  assert.equal(reviewPrompt(texts, "g1", "mat"), "G=g1 M=mat");
});

test("readJsonObject is {} for absent, broken or non-object files", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "second-opinion-json-"));
  fs.writeFileSync(path.join(dir, "ok.json"), '{"a": 1}');
  fs.writeFileSync(path.join(dir, "bad.json"), "{");
  fs.writeFileSync(path.join(dir, "list.json"), "[1]");
  assert.deepEqual(readJsonObject(path.join(dir, "ok.json")), { a: 1 });
  for (const name of ["bad.json", "list.json", "missing.json"]) {
    assert.deepEqual(readJsonObject(path.join(dir, name)), {});
  }
});

test("main: usage errors are one line and exit 2; -h prints the usage", () => {
  assert.deepEqual(run([]), {
    code: 2,
    stdout: "",
    stderr: "second_opinion.mjs: error: the following arguments are required: --gate, --gate-pack\n",
  });
  assert.match(run(["--bogus"]).stderr, /^second_opinion\.mjs: error: Unknown option '--bogus'/);
  assert.match(run(["-h"]).stdout, /^usage: second_opinion\.mjs /);
});

test("main: --dry-run prints the command, the report and the provider", () => {
  const root = project();
  const result = run(["--project-root", root, "--gate", "g", "--gate-pack", path.join(root, "pack.md"), "--dry-run"]);
  assert.equal(result.code, 0);
  const lines = result.stdout.split("\n");
  assert.match(lines[0], /^claude -p --output-format text You are an independent second-opinion reviewer/);
  assert.match(result.stdout, /\nreport: \.codex\/second-opinion\/g-1\.md\nprovider=anthropic model=\(default\)\n$/);
});

test("main: the provider's CRLF and lone CR arrive as LF, as text-mode pipes read them (C115)", () => {
  const root = project();
  const bin = fs.mkdtempSync(path.join(os.tmpdir(), "second-opinion-bin-"));
  fs.writeFileSync(path.join(bin, "claude"), "#!/bin/sh\nprintf 'a\\r\\nb\\rc\\r\\n'\nprintf 'w\\r\\nx\\r' >&2\n", {
    mode: 0o755,
  });
  const saved = process.env.PATH;
  process.env.PATH = `${bin}${path.delimiter}${saved}`;
  try {
    const result = run(["--project-root", root, "--gate", "g", "--gate-pack", path.join(root, "pack.md")]);
    assert.equal(result.code, 0);
    const report = path.join(root, ".codex", "second-opinion", "g-1.md");
    assert.equal(fs.readFileSync(report, "utf8"), "a\nb\nc\n\n[stderr]\nw\nx\n");
    assert.doesNotMatch(result.stdout, /\r/);
  } finally {
    process.env.PATH = saved;
    fs.rmSync(root, { recursive: true, force: true });
    fs.rmSync(bin, { recursive: true, force: true });
  }
});

test("main: an undecodable provider byte reads as U+FFFD and the report is still written (C120)", () => {
  const root = project();
  const bin = fs.mkdtempSync(path.join(os.tmpdir(), "second-opinion-bin-"));
  fs.writeFileSync(path.join(bin, "claude"), "#!/bin/sh\nprintf 'ok\\377x'\nprintf 'e\\377' >&2\n", { mode: 0o755 });
  const saved = process.env.PATH;
  process.env.PATH = `${bin}${path.delimiter}${saved}`;
  try {
    const result = run(["--project-root", root, "--gate", "g", "--gate-pack", path.join(root, "pack.md")]);
    assert.equal(result.code, 0);
    assert.match(result.stdout, /\ufffd/);
    const report = path.join(root, ".codex", "second-opinion", "g-1.md");
    assert.equal(fs.readFileSync(report, "utf8"), "ok\ufffdx\n\n[stderr]\ne\ufffd\n");
  } finally {
    process.env.PATH = saved;
    fs.rmSync(root, { recursive: true, force: true });
    fs.rmSync(bin, { recursive: true, force: true });
  }
});

test("main: a run writes the provider output to the report and returns the provider's exit code", () => {
  const root = project();
  const bin = fs.mkdtempSync(path.join(os.tmpdir(), "second-opinion-bin-"));
  fs.writeFileSync(path.join(bin, "claude"), '#!/bin/sh\necho "verdict: fine"\necho "warn" >&2\nexit 3\n', {
    mode: 0o755,
  });
  const saved = process.env.PATH;
  process.env.PATH = `${bin}${path.delimiter}${saved}`;
  try {
    const result = run(["--project-root", root, "--gate", "g", "--gate-pack", path.join(root, "pack.md")]);
    assert.equal(result.code, 3);
    assert.match(
      result.stdout,
      /^second-opinion provider=anthropic model=\(default\) gate=g exit=3\nreport: \.codex\/second-opinion\/g-1\.md\n\nverdict: fine\n\n\[stderr\]\nwarn\n$/,
    );
    const dir = path.join(root, ".codex", "second-opinion");
    assert.deepEqual(fs.readdirSync(dir), ["g-1.md"]);
    assert.equal(fs.readFileSync(path.join(dir, "g-1.md"), "utf8"), "verdict: fine\n\n[stderr]\nwarn\n");
    const again = run([
      "--project-root",
      root,
      "--gate",
      "g",
      "--gate-pack",
      path.join(root, "pack.md"),
      "--task",
      "C7",
    ]);
    assert.match(again.stdout, /\nreport: \.codex\/second-opinion\/C7-g-1\.md\n/);
  } finally {
    process.env.PATH = saved;
  }
});

/**
 * A scratch project under its own parent, with `report_dir` set for the default provider through
 * the project overlay, and a stand-in `claude` that leaves a marker when it is started.
 * @param {(base: string, root: string) => {configured: string, outside: string}} place
 * @returns {{base: string, root: string, bin: string, configured: string, outside: string}}
 */
function projectWithReportDir(place) {
  const base = fs.mkdtempSync(path.join(os.tmpdir(), "second-opinion-dir-"));
  const root = path.join(base, "project");
  fs.mkdirSync(path.join(root, "_aitna"), { recursive: true });
  fs.writeFileSync(path.join(root, "AGENTS.md"), "x\n");
  fs.writeFileSync(path.join(root, "pack.md"), "material\n");
  const { configured, outside } = place(base, root);
  fs.writeFileSync(
    path.join(root, "_aitna", "model-routing.json"),
    JSON.stringify({ anthropic: { second_opinion: { report_dir: configured } } }),
  );
  const bin = path.join(base, "bin");
  fs.mkdirSync(bin);
  fs.writeFileSync(
    path.join(bin, "claude"),
    `#!/bin/sh\ntouch "${path.join(base, "provider-ran")}"\necho "verdict: fine"\n`,
    {
      mode: 0o755,
    },
  );
  return { base, root, bin, configured, outside };
}

/** @type {Record<string, (base: string, root: string) => {configured: string, outside: string}>} */
const OUTSIDE = {
  absolute: (base) => ({ configured: path.join(base, "outside", "reviews"), outside: path.join(base, "outside") }),
  dotdot: (base) => ({ configured: "../outside/reviews", outside: path.join(base, "outside") }),
  symlink: (base, root) => {
    fs.mkdirSync(path.join(base, "outside"));
    fs.symlinkSync(path.join(base, "outside"), path.join(root, "link"));
    return { configured: "link/reviews", outside: path.join(base, "outside") };
  },
};

for (const [kind, place] of Object.entries(OUTSIDE)) {
  for (const dryRun of [false, true]) {
    test(`main: a report_dir outside the project (${kind}${dryRun ? ", --dry-run" : ""}) is refused before anything runs (C9)`, () => {
      const { base, root, bin, configured, outside } = projectWithReportDir(place);
      const saved = process.env.PATH;
      process.env.PATH = `${bin}${path.delimiter}${saved}`;
      try {
        const argv = ["--project-root", root, "--gate", "g", "--gate-pack", path.join(root, "pack.md")];
        const result = run(dryRun ? [...argv, "--dry-run"] : argv);
        assert.deepEqual(result, {
          code: 2,
          stdout: "",
          stderr: `second-opinion: report_dir '${configured}' resolves outside the project; it must be a directory inside the project root.\n`,
        });
        assert.equal(fs.existsSync(path.join(outside, "reviews")), false);
        assert.equal(fs.existsSync(path.join(base, "provider-ran")), false);
      } finally {
        process.env.PATH = saved;
        fs.rmSync(base, { recursive: true, force: true });
      }
    });
  }
}

test("main: a report_dir that stays inside the project through `..` and a link still writes its report, named by its resolved path", () => {
  const { base, root, bin } = projectWithReportDir((_base, root) => {
    fs.mkdirSync(path.join(root, "docs"));
    fs.symlinkSync(path.join(root, "docs"), path.join(root, "link"));
    return { configured: "link/../link/reviews", outside: "" };
  });
  const saved = process.env.PATH;
  process.env.PATH = `${bin}${path.delimiter}${saved}`;
  try {
    const result = run(["--project-root", root, "--gate", "g", "--gate-pack", path.join(root, "pack.md")]);
    assert.equal(result.code, 0);
    assert.match(result.stdout, /\nreport: docs\/reviews\/g-1\.md\n/);
    assert.equal(fs.readFileSync(path.join(root, "docs", "reviews", "g-1.md"), "utf8"), "verdict: fine\n");
    assert.equal(fs.existsSync(path.join(base, "provider-ran")), true);
  } finally {
    process.env.PATH = saved;
    fs.rmSync(base, { recursive: true, force: true });
  }
});
