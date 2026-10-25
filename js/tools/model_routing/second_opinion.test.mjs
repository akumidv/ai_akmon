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
import { spawn } from "node:child_process";

import { digest, main, readJsonObject, reportPrefix, reviewPrompt, unavailableNotice } from "./second_opinion.mjs";

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
 * Put the generated resolved-aliases file in place (what `models.mjs --refresh` writes).
 * @param {string} root
 * @param {Record<string, string>} aliases codex's alias to concrete id
 */
function writeAliases(root, aliases) {
  fs.mkdirSync(path.join(root, "_aitna", "local"), { recursive: true });
  const stored = { codex: { source: SOURCE, client: "0.164.0", aliases } };
  fs.writeFileSync(path.join(root, "_aitna", "local", "model-aliases.json"), `${JSON.stringify(stored, null, 2)}\n`);
}

const SOURCE = "~/.codex/models_cache.json (codex-models-cache)";

/** The concrete ids the shipped codex aliases resolve to in most tests (the shipped row declares `aliases: true`). */
const CODEX_IDS = { luna: "gpt-6-luna", terra: "gpt-6.1-terra", sol: "gpt-6.1-sol" };

/**
 * A scratch project root with a gate pack and, unless `resolved` is false, the codex aliases resolved.
 * @param {boolean} [resolved]
 * @returns {string}
 */
function project(resolved = true) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "second-opinion-test-"));
  fs.writeFileSync(path.join(root, "AGENTS.md"), "x\n");
  fs.writeFileSync(path.join(root, "pack.md"), "material\n");
  if (resolved) {
    writeAliases(root, CODEX_IDS);
  }
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
  const texts = /** @type {any} */ ({ prompt: "G={{gate}} M={{material}}" });
  assert.equal(reviewPrompt(texts, "g1", "mat"), "G=g1 M=mat");
});

test("unavailableNotice states the gate, the rank and the reason, then the three fixed lines", () => {
  const texts = /** @type {any} */ ({
    unavailable_notice: ["skipped {{gate}} at {{rank}}", "why: {{reason}}.", "a", "b", "c"],
  });
  assert.equal(unavailableNotice(texts, "g", 3, "no chain"), "skipped g at 3\nwhy: no chain.\na\nb\nc");
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

const SESSION = ["--session-provider", "claude", "--session-model", "opus"];

/**
 * A directory of stand-in carriers: each `name` is an executable `/bin/sh` script holding `script`.
 * The process's PATH is this directory alone while a test runs, so no real harness is ever found.
 * @param {Record<string, string>} scripts
 * @returns {string}
 */
function bin(scripts) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "second-opinion-bin-"));
  for (const [name, script] of Object.entries(scripts)) {
    fs.writeFileSync(path.join(dir, name), `#!/bin/sh\n${script}\n`, { mode: 0o755 });
  }
  return dir;
}

/**
 * Run `body` with `PATH` set to `dir`, restoring it afterwards.
 * @template T
 * @param {string} dir
 * @param {() => T} body
 * @returns {T}
 */
function withPath(dir, body) {
  const saved = process.env.PATH;
  process.env.PATH = dir;
  try {
    return body();
  } finally {
    process.env.PATH = saved;
  }
}

/**
 * The arguments that run gate `g` over the project's pack.
 * @param {string} root
 * @param {...string} extra
 * @returns {string[]}
 */
function args(root, ...extra) {
  return ["--project-root", root, "--gate", "g", "--gate-pack", path.join(root, "pack.md"), ...extra];
}

/**
 * Put the project overlay in place.
 * @param {string} root
 * @param {object} overlay
 */
function overlay(root, overlay) {
  fs.mkdirSync(path.join(root, "_aitna"), { recursive: true });
  fs.writeFileSync(path.join(root, "_aitna", "model-routing.json"), JSON.stringify(overlay));
}

/**
 * Put the developer-local overlay in place (`<aitna_root>/local/model-routing.json`).
 * @param {string} root
 * @param {object | string} content an object, or raw text
 */
function localOverlay(root, content) {
  fs.mkdirSync(path.join(root, "_aitna", "local"), { recursive: true });
  fs.writeFileSync(
    path.join(root, "_aitna", "local", "model-routing.json"),
    typeof content === "string" ? content : JSON.stringify(content),
  );
}

test("main: usage errors are one line and exit 2; -h prints the usage", () => {
  assert.deepEqual(run([]), {
    code: 2,
    stdout: "",
    stderr: "second_opinion.mjs: error: second-opinion: --gate and --gate-pack are required unless --list is given\n",
  });
  assert.equal(
    run(["--rank", "1", "--list"]).stderr,
    "second_opinion.mjs: error: second-opinion: --rank must be 2 or more (2 second opinion, 3 third opinion, 4 arbiter); got 1\n",
  );
  assert.equal(run(["--rank", "two"]).stderr, "second_opinion.mjs: error: argument --rank: invalid int value: 'two'\n");
  assert.match(run(["--bogus"]).stderr, /^second_opinion\.mjs: error: Unknown option '--bogus'/);
  assert.match(run(["-h"]).stdout, /^usage: second_opinion\.mjs /);
});

test("main: --list needs no gate, prints the ranked chain, the skip ledger and runs nothing", () => {
  const root = project();
  const dir = bin({ codex: "exit 9" });
  const result = withPath(dir, () => run(["--project-root", root, "--list", ...SESSION]));
  assert.deepEqual(result, {
    code: 0,
    stdout:
      "session: provider=claude model=opus priors=claude\n" +
      "rank 2: provider=codex model=sol→gpt-6.1-sol priors=gpt repo=worktree\n" +
      "skipped:\n  claude: self\n  qwen: carrier absent\n  opencode: carrier absent\n  pi: carrier absent\n",
    stderr: "",
  });
});

test("main: --list of an empty chain names the last resort; an unknown-priors provider is asked about", () => {
  const root = project();
  overlay(root, { second_opinion_policy: { ladder: ["claude", "opencode"] } });
  const dir = bin({ claude: "exit 0", opencode: "exit 0" });
  const result = withPath(dir, () => run(["--project-root", root, "--list", ...SESSION]));
  assert.equal(result.code, 0);
  assert.match(result.stdout, /^chain: empty — no ladder provider differs from the session$/m);
  assert.match(
    result.stdout,
    /^last resort at rank 2 \(kind=last-resort\): provider=claude model=sonnet priors=claude repo=worktree$/m,
  );
  assert.match(result.stdout, /^ {2}opencode: priors unknown$/m);
  assert.match(
    result.stdout,
    /^asks:\n {2}opencode: priors unknown for its default model; declare providers\.opencode\.family in _aitna\/local\/model-routing\.json to keep it to yourself, or _aitna\/model-routing\.json to share it with the team$/m,
  );
});

test("main: --list shows the last resort a run takes for a session of unknown priors, or why none exists", () => {
  const root = project();
  const dir = bin({ opencode: "exit 0" });
  const session = ["--session-provider", "opencode", "--session-model", "x/y"];
  const listed = withPath(dir, () => run(["--project-root", root, "--list", ...session]));
  assert.match(listed.stdout, /^session: provider=opencode model=x\/y priors=unknown$/m);
  assert.match(
    listed.stdout,
    /^last resort at rank 2 \(kind=last-resort\): provider=opencode model=\(default\) priors=unknown repo=worktree$/m,
  );
  assert.match(listed.stdout, /^ {2}opencode: session priors unknown$/m);
  const ran = withPath(dir, () => run(args(root, ...session, "--dry-run")));
  assert.match(
    ran.stdout,
    /provider=opencode priors=unknown carrier=harness repo=worktree model=\(default\) kind=last-resort/,
  );
  const norow = withPath(dir, () => run(["--project-root", root, "--list", "--session-provider", "gemini"]));
  assert.match(norow.stdout, /^chain: empty/m);
  assert.match(
    norow.stdout,
    /^no last resort: the session's own provider 'gemini' has no row in the providers table, so the last resort has nothing to run$/m,
  );
  assert.doesNotMatch(norow.stdout, /last resort at rank 2/);
  const absent = withPath(bin({}), () => run(["--project-root", root, "--list", ...session]));
  assert.match(
    absent.stdout,
    /^no last resort: the session's own provider 'opencode' is not on PATH, so the last resort has nothing to run$/m,
  );
});

test("main: a session nothing names is exit 2 naming the flag to pass", () => {
  const root = project();
  const result = withPath(bin({}), () => run(args(root, "--dry-run")));
  assert.equal(result.code, 2);
  assert.equal(result.stdout, "");
  assert.match(result.stderr, /^second-opinion: .*--session-provider/);
});

test("main: the session comes from the recorded stanza, and a flag overrides it", () => {
  const root = project();
  fs.mkdirSync(path.join(root, ".claude"));
  fs.writeFileSync(
    path.join(root, ".claude", "model-routing.local.json"),
    JSON.stringify({ session: { provider: "claude", model: "opus" } }),
  );
  const dir = bin({ claude: "exit 0", codex: "exit 0" });
  const recorded = withPath(dir, () => run(args(root, "--dry-run")));
  assert.match(recorded.stdout, /^codex exec --model gpt-6\.1-sol /);
  const overridden = withPath(dir, () => run(args(root, "--dry-run", "--session-provider", "codex")));
  assert.match(overridden.stdout, /^claude -p --output-format text --model opus /);
});

test("main: the deprecated --orchestrator-vendor maps to the vendor's carrier; a vendor without one is refused", () => {
  const root = project();
  const dir = bin({ codex: "exit 0" });
  const mapped = withPath(dir, () => run(args(root, "--dry-run", "--orchestrator-vendor", "anthropic")));
  assert.equal(mapped.code, 0);
  assert.match(mapped.stdout, /^codex exec --model gpt-6\.1-sol /);
  const refused = withPath(dir, () => run(args(root, "--dry-run", "--orchestrator-vendor", "nobody")));
  assert.equal(refused.code, 2);
  assert.match(refused.stderr, /^second-opinion: second-opinion: --orchestrator-vendor 'nobody' names no vendor/);
});

test("main: --dry-run prints the command, the report, the header and the skip ledger", () => {
  const root = project();
  const dir = bin({ codex: "exit 0" });
  const result = withPath(dir, () => run(args(root, "--dry-run", ...SESSION)));
  assert.equal(result.code, 0);
  const lines = result.stdout.split("\n");
  assert.match(lines[0], /^codex exec --model gpt-6\.1-sol You are an independent second-opinion reviewer/);
  assert.match(
    result.stdout,
    /\nreport: \.codex\/second-opinion\/g-1\.md\nprovider=codex priors=gpt carrier=harness repo=worktree model=sol→gpt-6.1-sol kind=chain\nskipped claude: self\nskipped qwen: carrier absent\nskipped opencode: carrier absent\nskipped pi: carrier absent\n$/,
  );
  assert.equal(fs.existsSync(path.join(root, ".codex")), false);
});

test("main: --rank 3 takes the next provider of the chain", () => {
  const root = project();
  const dir = bin({ codex: "exit 0", qwen: "exit 0" });
  const result = withPath(dir, () => run(args(root, "--dry-run", "--rank", "3", ...SESSION)));
  assert.match(result.stdout, /^qwen /);
  assert.match(result.stdout, /\nprovider=qwen priors=qwen /);
});

test("main: a rank past the chain is the skip notice with the reason and the ledger, exit 0, nothing run", () => {
  const root = project();
  const dir = bin({ codex: "touch ran" });
  const result = withPath(dir, () => run(args(root, "--rank", "4", ...SESSION)));
  assert.equal(result.code, 0);
  assert.match(result.stdout, /^second-opinion: skipped at gate 'g' — no provider could be run for rank 4\.\n/);
  assert.match(
    result.stdout,
    /why: the chain holds 1 provider\(s\), fewer than rank 4 asks for; the last resort applies only to an empty chain at rank 2\.\n/,
  );
  assert.match(result.stdout, /\nskipped claude: self\n/);
  assert.equal(fs.existsSync(path.join(root, "ran")), false);
});

test("main: an empty chain on an absent session carrier is the skip notice naming PATH", () => {
  const root = project();
  const result = withPath(bin({}), () => run(args(root, ...SESSION)));
  assert.equal(result.code, 0);
  assert.match(
    result.stdout,
    /\n {2}why: the session's own provider 'claude' is not on PATH, so the last resort has nothing to run\.\n/,
  );
});

test("main: an empty chain takes the disclosed last resort on the session's own provider", () => {
  const root = project();
  overlay(root, { second_opinion_policy: { ladder: ["claude"] } });
  const dir = bin({ claude: 'echo "verdict: again"' });
  const result = withPath(dir, () => run(args(root, "--dry-run", ...SESSION)));
  assert.equal(result.code, 0);
  assert.match(result.stdout, /^claude -p --output-format text --model sonnet /);
  assert.match(
    result.stdout,
    /\nprovider=claude priors=claude carrier=harness repo=worktree model=sonnet kind=last-resort\n/,
  );
  assert.match(
    result.stdout,
    /\nwarning: no ladder provider differs from the session, so this run uses the session's own provider with the strongest declared model that differs from opus, or its default — same priors, filed as kind=last-resort\n/,
  );
});

test("main: --provider runs the owner's pick as kind=pinned with a warning for each way it is not diverse", () => {
  const root = project();
  const dir = bin({});
  const own = withPath(dir, () => run(args(root, "--dry-run", "--provider", "claude:haiku", ...SESSION)));
  assert.equal(own.code, 0);
  assert.match(own.stdout, /^claude -p --output-format text --model haiku /);
  assert.match(own.stdout, /\nprovider=claude priors=claude carrier=harness repo=worktree model=haiku kind=pinned\n/);
  assert.match(
    own.stdout,
    /\nwarning: 'claude' is the session's own provider; this run is not an independent second opinion and is filed as kind=pinned\n/,
  );
  const unknown = withPath(dir, () => run(args(root, "--dry-run", "--provider", "opencode", ...SESSION)));
  assert.match(
    unknown.stdout,
    /\nwarning: the priors of 'opencode' are unknown, so this run is not counted as diverse and is filed as kind=pinned\n/,
  );
  const other = withPath(dir, () => run(args(root, "--dry-run", "--provider", "codex", ...SESSION)));
  assert.doesNotMatch(other.stdout, /warning:/);
  const ghost = withPath(dir, () => run(args(root, "--dry-run", "--provider", "ghost", ...SESSION)));
  assert.equal(ghost.code, 2);
  assert.match(ghost.stderr, /^second-opinion: .*ghost/);
});

test("main: a model the provider declares no flag to pin is exit 2 before anything runs", () => {
  const root = project();
  overlay(root, { providers: { codex: { model_flag: null } } });
  const dir = bin({ codex: "touch ran" });
  const result = withPath(dir, () => run(args(root, ...SESSION)));
  assert.equal(result.code, 2);
  assert.match(
    result.stderr,
    /^second-opinion: second opinion needs model 'gpt-6\.1-sol' on codex, but the providers table declares no model_flag/,
  );
  assert.equal(fs.existsSync(path.join(root, "ran")), false);
});

test("main: a retired overlay key and a retired local-config key are refused naming the file", () => {
  const stale = project();
  overlay(stale, { anthropic: { second_opinion: { harness: "claude" } } });
  const fromOverlay = withPath(bin({}), () => run(args(stale, "--dry-run", ...SESSION)));
  assert.equal(fromOverlay.code, 2);
  assert.match(fromOverlay.stderr, /^second-opinion: .*_aitna\/model-routing\.json.*anthropic\.second_opinion/);
  const old = project();
  fs.mkdirSync(path.join(old, ".claude"));
  fs.writeFileSync(
    path.join(old, ".claude", "model-routing.local.json"),
    JSON.stringify({ second_opinion_provider: "x" }),
  );
  const fromConfig = withPath(bin({}), () => run(args(old, "--dry-run", ...SESSION)));
  assert.equal(fromConfig.code, 2);
  assert.match(fromConfig.stderr, /^second-opinion: .*model-routing\.local\.json.*second_opinion_provider/);
});

test("main: --list reads the developer's local overlay as the strongest layer, its ladder replacing the project's whole", () => {
  const root = project();
  overlay(root, { second_opinion_policy: { ladder: ["claude", "codex"] } });
  localOverlay(root, {
    providers: { opencode: { family: "gemini" } },
    second_opinion_policy: { ladder: ["opencode"] },
  });
  const dir = bin({ opencode: "exit 0" });
  const result = withPath(dir, () => run(["--project-root", root, "--list", ...SESSION]));
  assert.equal(result.code, 0);
  assert.match(result.stdout, /^rank 2: provider=opencode model=\(default\) priors=gemini repo=worktree$/m);
  assert.doesNotMatch(result.stdout, /^rank 3/m);
});

test("main: a retired key in the local overlay is refused naming that file", () => {
  const root = project();
  localOverlay(root, { second_opinion_policy: { diversity_ladder: [] } });
  const result = withPath(bin({}), () => run(["--project-root", root, "--list", ...SESSION]));
  assert.equal(result.code, 2);
  assert.match(result.stderr, /^second-opinion: .*_aitna\/local\/model-routing\.json.*diversity_ladder/);
});

test("main: an overlay that is not a JSON object is one error line and exit 2, never a stack trace", () => {
  for (const content of ["{ not json", "[1, 2]"]) {
    const root = project();
    localOverlay(root, content);
    const result = withPath(bin({}), () => run(["--project-root", root, "--list", ...SESSION]));
    assert.equal(result.code, 2);
    assert.equal(result.stdout, "");
    assert.equal(
      result.stderr,
      "second-opinion: the routing overlay _aitna/local/model-routing.json is not a valid JSON object; repair or delete it (it is hand-owned, so akmon never rewrites it)\n",
    );
  }
});

test("main: a run writes the header, the ledger and the review to the report, and returns the provider's exit code", () => {
  const root = project();
  const dir = bin({ codex: 'echo "verdict: fine"\necho "warn" >&2\nexit 3' });
  const result = withPath(dir, () => run(args(root, ...SESSION)));
  const header =
    "second-opinion provider=codex priors=gpt carrier=harness repo=worktree model=sol→gpt-6.1-sol kind=chain gate=g exit=3";
  const ledger =
    "skipped claude: self\nskipped qwen: carrier absent\nskipped opencode: carrier absent\nskipped pi: carrier absent";
  assert.equal(result.code, 3);
  assert.equal(
    result.stdout,
    `${header}\nreport: .codex/second-opinion/g-1.md\n${ledger}\n\nverdict: fine\n\n[stderr]\nwarn\n`,
  );
  const report = path.join(root, ".codex", "second-opinion", "g-1.md");
  assert.equal(fs.readFileSync(report, "utf8"), `${header}\n${ledger}\n\nverdict: fine\n\n[stderr]\nwarn\n`);
  const again = withPath(dir, () => run(args(root, "--task", "C7", ...SESSION)));
  assert.match(again.stdout, /\nreport: \.codex\/second-opinion\/C7-g-1\.md\n/);
});

test("main: a declared carrier gets the pack on stdin and never as an argument", () => {
  const root = project();
  overlay(root, {
    providers: {
      sh: {
        argv: ["/bin/sh", "-c", 'read first; echo "stdin:$first"; echo "argc:$#"'],
        prompt: "stdin",
        family: "qwen",
        report_dir: ".sh/second-opinion/",
      },
    },
    second_opinion_policy: { ladder: ["sh"] },
  });
  const result = withPath(bin({}), () => run(args(root, ...SESSION)));
  assert.equal(result.code, 0);
  assert.match(
    result.stdout,
    /^second-opinion provider=sh priors=qwen carrier=declared repo=unknown model=\(default\) kind=chain gate=g exit=0\n/,
  );
  assert.match(
    result.stdout,
    /\nstdin:You are an independent second-opinion reviewer for a akmon verify gate\.\nargc:0\n$/,
  );
});

test("main: a declared row with no report_dir files its report under .<provider>/second-opinion/ (a provider the registry does not ship)", () => {
  const root = project();
  overlay(root, {
    providers: { fakepi: { argv: ["/bin/sh", "-c", "echo verdict: fine"], family: "qwen" } },
    second_opinion_policy: { ladder: ["fakepi"] },
  });
  const result = withPath(bin({}), () => run(args(root, ...SESSION)));
  assert.equal(result.code, 0);
  assert.match(result.stdout, /\nreport: \.fakepi\/second-opinion\/g-1\.md\n/);
  assert.match(fs.readFileSync(path.join(root, ".fakepi", "second-opinion", "g-1.md"), "utf8"), /\n\nverdict: fine\n$/);
});

test("main: the default report_dir is still refused when it resolves outside the project", () => {
  const root = project();
  overlay(root, { providers: { "x/../..": { argv: ["/bin/sh", "-c", "true"], family: "qwen" } } });
  const result = withPath(bin({}), () => run(args(root, "--provider", "x/../..", ...SESSION)));
  assert.equal(result.code, 2);
  assert.equal(
    result.stderr,
    "second-opinion: report_dir '.x/../../second-opinion/' resolves outside the project; it must be a directory inside the project root.\n",
  );
});

test("main: a carrier that cannot be started is one error line and exit 2, with no report", () => {
  const root = project();
  overlay(root, { providers: { ghost: { argv: ["/nonexistent/ghost"], family: "qwen", report_dir: ".ghost/" } } });
  const result = withPath(bin({}), () => run(args(root, "--provider", "ghost", ...SESSION)));
  assert.deepEqual(result, {
    code: 2,
    stdout: "",
    stderr:
      "second-opinion: could not start '/nonexistent/ghost': [Errno 2] No such file or directory: '/nonexistent/ghost'\n",
  });
  assert.equal(fs.existsSync(path.join(root, ".ghost")), false);
});

test("main: the provider's CRLF and lone CR arrive as LF, as text-mode pipes read them (C115)", () => {
  const root = project();
  const dir = bin({ codex: "printf 'a\\r\\nb\\rc\\r\\n'\nprintf 'w\\r\\nx\\r' >&2" });
  const result = withPath(dir, () => run(args(root, ...SESSION)));
  assert.equal(result.code, 0);
  const report = fs.readFileSync(path.join(root, ".codex", "second-opinion", "g-1.md"), "utf8");
  assert.ok(report.endsWith("\n\na\nb\nc\n\n[stderr]\nw\nx\n"));
  assert.doesNotMatch(result.stdout, /\r/);
});

test("main: an undecodable provider byte reads as U+FFFD and the report is still written (C120)", () => {
  const root = project();
  const dir = bin({ codex: "printf 'ok\\377x'\nprintf 'e\\377' >&2" });
  const result = withPath(dir, () => run(args(root, ...SESSION)));
  assert.equal(result.code, 0);
  assert.match(result.stdout, /�/);
  const report = fs.readFileSync(path.join(root, ".codex", "second-opinion", "g-1.md"), "utf8");
  assert.ok(report.endsWith("\n\nok�x\n\n[stderr]\ne�\n"));
});

/**
 * A scratch project under its own parent, with the codex `report_dir` set through the overlay.
 * @param {(base: string, root: string) => {configured: string, outside: string}} place
 * @returns {{base: string, root: string, dir: string, configured: string, outside: string}}
 */
function projectWithReportDir(place) {
  const base = fs.mkdtempSync(path.join(os.tmpdir(), "second-opinion-dir-"));
  const root = path.join(base, "project");
  fs.mkdirSync(root);
  fs.writeFileSync(path.join(root, "AGENTS.md"), "x\n");
  fs.writeFileSync(path.join(root, "pack.md"), "material\n");
  writeAliases(root, CODEX_IDS);
  const { configured, outside } = place(base, root);
  overlay(root, { providers: { codex: { report_dir: configured } } });
  const dir = bin({ codex: `: > "${path.join(base, "provider-ran")}"\necho "verdict: fine"` });
  return { base, root, dir, configured, outside };
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
      const { base, root, dir, configured, outside } = projectWithReportDir(place);
      try {
        const result = withPath(dir, () => run(args(root, ...SESSION, ...(dryRun ? ["--dry-run"] : []))));
        assert.deepEqual(result, {
          code: 2,
          stdout: "",
          stderr: `second-opinion: report_dir '${configured}' resolves outside the project; it must be a directory inside the project root.\n`,
        });
        assert.equal(fs.existsSync(path.join(outside, "reviews")), false);
        assert.equal(fs.existsSync(path.join(base, "provider-ran")), false);
      } finally {
        fs.rmSync(base, { recursive: true, force: true });
      }
    });
  }
}

test("main: a report_dir that stays inside the project through `..` and a link still writes its report, named by its resolved path", () => {
  const { base, root, dir } = projectWithReportDir((_base, root) => {
    fs.mkdirSync(path.join(root, "docs"));
    fs.symlinkSync(path.join(root, "docs"), path.join(root, "link"));
    return { configured: "link/../link/reviews", outside: "" };
  });
  try {
    const result = withPath(dir, () => run(args(root, ...SESSION)));
    assert.equal(result.code, 0);
    assert.match(result.stdout, /\nreport: docs\/reviews\/g-1\.md\n/);
    assert.ok(fs.readFileSync(path.join(root, "docs", "reviews", "g-1.md"), "utf8").endsWith("\n\nverdict: fine\n"));
    assert.equal(fs.existsSync(path.join(base, "provider-ran")), true);
  } finally {
    fs.rmSync(base, { recursive: true, force: true });
  }
});

/** A carrier that says whether its stdin is at EOF (a closed or null device) or still open after two seconds. */
const STDIN_PROBE =
  'const t=setTimeout(()=>{console.log("stdin:open");process.exit(0)},2000);' +
  'process.stdin.on("end",()=>{console.log("stdin:eof");clearTimeout(t)});process.stdin.resume();';

/**
 * Run `main` for a project in a child node process whose own stdin is an open pipe nobody writes to.
 * @param {string[]} argv
 * @returns {Promise<{code: number | null, stdout: string}>}
 */
function runWithOpenStdin(argv) {
  const driver = path.join(fs.mkdtempSync(path.join(os.tmpdir(), "second-opinion-driver-")), "driver.mjs");
  const module = new URL("./second_opinion.mjs", import.meta.url).href;
  fs.writeFileSync(
    driver,
    `import { main } from ${JSON.stringify(module)};\nprocess.exitCode = main(${JSON.stringify(argv)});\n`,
  );
  return new Promise((resolve) => {
    const child = spawn(process.execPath, [driver], { stdio: ["pipe", "pipe", "pipe"] });
    let stdout = "";
    child.stdout.on("data", (chunk) => (stdout += chunk));
    child.on("close", (code) => {
      child.stdin.destroy();
      resolve({ code, stdout });
    });
  });
}

test("main: a carrier fed its prompt as an argument sees EOF on stdin, even when the parent's stdin is an open pipe", async () => {
  const root = project();
  overlay(root, {
    providers: {
      probe: {
        argv: [process.execPath, "-e", STDIN_PROBE, "--"],
        family: "qwen",
        report_dir: ".probe/second-opinion/",
      },
    },
    second_opinion_policy: { ladder: ["probe"] },
  });
  const result = await runWithOpenStdin(args(root, ...SESSION));
  assert.equal(result.code, 0);
  assert.match(result.stdout, /\nstdin:eof\n$/);
});

// -- ADR-0024/D16: aliases resolve to a concrete id from the local file; `default` is the carrier's own model --

const UNMAPPED_LINE =
  "second-opinion: provider 'codex' declares model aliases, and 'sol' has no concrete id in _aitna/local/model-aliases.json; ";
const REFRESH = "akmon tool model_routing/models --refresh --provider codex";

/**
 * Run `argv` with only a stand-in `codex` carrier on PATH.
 * @param {string[]} argv
 * @returns {{code: number, stdout: string, stderr: string}}
 */
function withCodex(argv) {
  return withPath(bin({ codex: "exit 0" }), () => run(argv));
}

test("main: an alias is sent as its concrete id and the header records both", () => {
  const root = project();
  const result = withCodex(args(root, "--dry-run", ...SESSION));
  assert.equal(result.code, 0);
  assert.ok(result.stdout.split("\n")[0].startsWith("codex exec --model gpt-6.1-sol "));
  assert.ok(
    result.stdout.includes("provider=codex priors=gpt carrier=harness repo=worktree model=sol→gpt-6.1-sol kind=chain"),
  );
});

test("main: an alias with no mapping refuses the run with one line and exit 2, spawning nothing", () => {
  const root = project(false);
  const dir = bin({ codex: "touch ran" });
  const result = withPath(dir, () => run(args(root, ...SESSION)));
  assert.equal(result.code, 2);
  assert.equal(result.stdout, "");
  assert.equal(result.stderr.split("\n").length, 2);
  assert.ok(result.stderr.startsWith(UNMAPPED_LINE));
  assert.ok(result.stderr.includes(REFRESH));
  assert.equal(fs.existsSync(path.join(root, "ran")), false);
  assert.equal(fs.existsSync(path.join(root, ".codex")), false);
});

test("main: a dry run also refuses an unmapped alias", () => {
  const root = project(false);
  const result = withCodex(args(root, "--dry-run", ...SESSION));
  assert.equal(result.code, 2);
  assert.ok(result.stderr.includes("has no concrete id"));
});

test("main: a pinned concrete id passes through unchanged with no file needed", () => {
  const root = project(false);
  const result = withCodex(args(root, "--provider", "codex:gpt-6.1-sol", "--dry-run", ...SESSION));
  assert.equal(result.code, 0);
  assert.ok(result.stdout.split("\n")[0].startsWith("codex exec --model gpt-6.1-sol "));
  assert.ok(result.stdout.includes("model=gpt-6.1-sol kind=pinned"));
});

test("main: a pinned alias resolves through the file", () => {
  const root = project(false);
  writeAliases(root, { luna: "gpt-6-luna" });
  const result = withCodex(args(root, "--provider", "codex:luna", "--dry-run", ...SESSION));
  assert.equal(result.code, 0);
  assert.ok(result.stdout.split("\n")[0].startsWith("codex exec --model gpt-6-luna "));
  assert.ok(result.stdout.includes("model=luna→gpt-6-luna kind=pinned"));
});

test("main: --list shows the resolution, and an unmapped alias with its ask", () => {
  const root = project(false);
  const unresolved = withCodex(["--project-root", root, "--list", ...SESSION]);
  assert.equal(unresolved.code, 0);
  writeAliases(root, { sol: "gpt-6.1-sol" });
  const resolved = withCodex(["--project-root", root, "--list", ...SESSION]);
  assert.equal(resolved.code, 0);
  assert.ok(unresolved.stdout.includes("rank 2: provider=codex model=sol→(unresolved) priors=gpt repo=worktree"));
  assert.ok(unresolved.stdout.includes(`  codex: alias 'sol' has no concrete id; run \`${REFRESH}\``));
  assert.ok(resolved.stdout.includes("rank 2: provider=codex model=sol→gpt-6.1-sol priors=gpt repo=worktree"));
  assert.ok(!resolved.stdout.includes("has no concrete id"));
});

test("main: a corrupt aliases file is refused naming it", () => {
  const root = project(false);
  fs.mkdirSync(path.join(root, "_aitna", "local"), { recursive: true });
  fs.writeFileSync(path.join(root, "_aitna", "local", "model-aliases.json"), "[]");
  const result = withCodex(["--project-root", root, "--list", ...SESSION]);
  assert.equal(result.code, 2);
  assert.ok(result.stderr.includes("_aitna/local/model-aliases.json is not a valid alias map"));
});

test("main: the default token runs the carrier's own model without any alias file", () => {
  const root = project(false);
  const result = withCodex(args(root, "--provider", "codex:default", "--dry-run", ...SESSION));
  assert.equal(result.code, 0);
  const first = result.stdout.split("\n")[0];
  assert.ok(first.startsWith("codex exec You are an independent"));
  assert.ok(!first.includes("--model"));
  assert.ok(result.stdout.includes("model=(default) kind=pinned"));
});

test("main: --default-model drops the pin of whichever target the run selects", () => {
  const root = project(false);
  const result = withCodex(args(root, "--default-model", "--dry-run", ...SESSION));
  assert.equal(result.code, 0);
  assert.ok(result.stdout.split("\n")[0].startsWith("codex exec You are an independent"));
  assert.ok(result.stdout.includes("model=(default) kind=chain"));
});

test("main: --default-model with --provider only drops the strongest pin", () => {
  const root = project(false);
  const result = withCodex(args(root, "--default-model", "--provider", "codex", "--dry-run", ...SESSION));
  assert.equal(result.code, 0);
  assert.ok(result.stdout.includes("model=(default) kind=pinned"));
});

test("main: --default-model together with an explicit model is one refused line", () => {
  const root = project(false);
  const result = withCodex(args(root, "--default-model", "--provider", "codex:gpt-6.1-sol", "--dry-run", ...SESSION));
  assert.deepEqual(result, {
    code: 2,
    stdout: "",
    stderr:
      "second-opinion: --default-model cannot be combined with --provider 'codex:gpt-6.1-sol', " +
      "which pins a model; drop one of them\n",
  });
});

test("main: a ladder entry with the default token runs unpinned and the listing marks it", () => {
  const root = project(false);
  overlay(root, { second_opinion_policy: { ladder: ["codex:default", "qwen"] } });
  const dir = bin({ codex: "exit 0", qwen: "exit 0" });
  const listing = withPath(dir, () => run(["--project-root", root, "--list", ...SESSION]));
  const dry = withPath(dir, () => run(args(root, "--dry-run", ...SESSION)));
  assert.equal(listing.code, 0);
  assert.equal(dry.code, 0);
  assert.ok(listing.stdout.includes("rank 2: provider=codex model=(default) priors=gpt repo=worktree pin=default\n"));
  assert.ok(listing.stdout.includes("rank 3: provider=qwen model=(default) priors=qwen repo=worktree\n"));
  assert.ok(!listing.stdout.includes("has no concrete id"));
  assert.ok(dry.stdout.includes("model=(default) kind=chain"));
});

test("main: --list with --default-model marks every candidate", () => {
  const root = project(false);
  const result = withCodex(["--project-root", root, "--list", "--default-model", ...SESSION]);
  assert.equal(result.code, 0);
  assert.ok(result.stdout.includes("rank 2: provider=codex model=(default) priors=gpt repo=worktree pin=default"));
  assert.ok(!result.stdout.includes("has no concrete id"));
});

test("main: a default run on the session's own provider stays a disclosed pinned run", () => {
  const root = project(false);
  const session = ["--session-provider", "codex", "--session-model", "sol"];
  const result = withCodex(args(root, ...session, "--provider", "codex:default", "--dry-run"));
  assert.equal(result.code, 0);
  assert.ok(result.stdout.includes("model=(default) kind=pinned"));
  assert.ok(result.stdout.includes("warning: 'codex' is the session's own provider"));
});

// -- ADR-0024/D17: `carrier:model@effort` --

const EFFORT_PROVIDERS = {
  claude: { efforts: { flag: "--effort {effort}", levels: ["low", "medium", "high"] } },
  codex: { efforts: { flag: "-c model_reasoning_effort={effort}", levels: ["low", "high"] } },
};
const EFFORT_SESSION = ["--session-provider", "qwen", "--session-model", "q"];

/**
 * A project whose claude and codex rows declare `efforts`, optionally with its own ladder.
 * @param {string[] | null} [ladder]
 * @returns {string}
 */
function effortProject(ladder = null) {
  const root = project();
  overlay(root, {
    providers: EFFORT_PROVIDERS,
    ...(ladder ? { second_opinion_policy: { ladder } } : {}),
  });
  return root;
}

/**
 * Run `argv` with stand-in claude, codex and qwen carriers on PATH.
 * @param {string[]} argv
 * @returns {{code: number, stdout: string, stderr: string}}
 */
function withCarriers(argv) {
  return withPath(bin({ claude: "exit 0", codex: "exit 0", qwen: "exit 0" }), () => run(argv));
}

test("main: a pinned model with an effort sends both and the header shows the effort", () => {
  const result = withCarriers(args(effortProject(), ...EFFORT_SESSION, "--provider", "claude:opus@high", "--dry-run"));
  assert.equal(result.code, 0);
  assert.ok(result.stdout.split("\n")[0].startsWith("claude -p --output-format text --model opus --effort high "));
  assert.ok(result.stdout.includes("model=opus@high kind=pinned"));
});

test("main: an alias is resolved first and the effort follows the concrete id", () => {
  const result = withCarriers(args(effortProject(), ...EFFORT_SESSION, "--provider", "codex:sol@high", "--dry-run"));
  assert.equal(result.code, 0);
  assert.ok(result.stdout.split("\n")[0].startsWith("codex exec --model gpt-6.1-sol -c model_reasoning_effort=high "));
  assert.ok(result.stdout.includes("model=sol→gpt-6.1-sol@high kind=pinned"));
});

test("main: default with an effort pins no model and sends only the level", () => {
  const result = withCarriers(
    args(effortProject(), ...EFFORT_SESSION, "--provider", "codex:default@high", "--dry-run"),
  );
  assert.equal(result.code, 0);
  const first = result.stdout.split("\n")[0];
  assert.ok(first.startsWith("codex exec -c model_reasoning_effort=high "));
  assert.ok(!first.includes("--model"));
  assert.ok(result.stdout.includes("model=(default)@high kind=pinned"));
});

test("main: an effort alone keeps the rules model and adds the level", () => {
  const result = withCarriers(args(effortProject(), ...EFFORT_SESSION, "--provider", "claude:@low", "--dry-run"));
  assert.equal(result.code, 0);
  assert.ok(result.stdout.split("\n")[0].startsWith("claude -p --output-format text --model opus --effort low "));
  assert.ok(result.stdout.includes("model=opus@low kind=pinned"));
});

test("main: an effort on a carrier without efforts is one refused line and exit 2", () => {
  const root = effortProject();
  const result = withCarriers(args(root, ...EFFORT_SESSION, "--provider", "qwen:big@high"));
  assert.equal(result.code, 2);
  assert.equal(result.stdout, "");
  assert.equal(result.stderr.split("\n").length, 2);
  assert.ok(result.stderr.startsWith("second-opinion: provider 'qwen' declares no `efforts`, so the effort 'high'"));
});

test("main: an effort outside the levels is one refused line naming the accepted ones", () => {
  const result = withCarriers(args(effortProject(), ...EFFORT_SESSION, "--provider", "claude:opus@max", "--dry-run"));
  assert.deepEqual(result, {
    code: 2,
    stdout: "",
    stderr: "second-opinion: provider 'claude' does not accept the effort 'max'; its levels are: low, medium, high\n",
  });
});

test("main: a ladder entry with an effort runs with it and the listing shows it", () => {
  const root = effortProject(["claude:opus@high", "qwen"]);
  const session = ["--session-provider", "codex", "--session-model", "sol"];
  const listing = withCarriers(["--project-root", root, "--list", ...session]);
  const dry = withCarriers(args(root, ...session, "--dry-run"));
  assert.equal(listing.code, 0);
  assert.equal(dry.code, 0);
  assert.ok(listing.stdout.includes("rank 2: provider=claude model=opus@high priors=claude repo=worktree"));
  assert.ok(listing.stdout.includes("rank 3: provider=qwen model=(default) priors=qwen repo=worktree\n"));
  assert.ok(dry.stdout.split("\n")[0].startsWith("claude -p --output-format text --model opus --effort high "));
});

test("main: --default-model drops the model pin and keeps the effort", () => {
  const root = effortProject(["codex:sol@high"]);
  const result = withCarriers(
    args(root, "--default-model", "--session-provider", "claude", "--session-model", "opus", "--dry-run"),
  );
  assert.equal(result.code, 0);
  assert.ok(result.stdout.split("\n")[0].startsWith("codex exec -c model_reasoning_effort=high "));
  assert.ok(result.stdout.includes("model=(default)@high kind=chain"));
});

test("main: --default-model with an effort alone or default at an effort is allowed", () => {
  const root = effortProject();
  const first = withCarriers(
    args(root, ...EFFORT_SESSION, "--default-model", "--provider", "codex:@high", "--dry-run"),
  );
  const second = withCarriers(
    args(root, ...EFFORT_SESSION, "--default-model", "--provider", "codex:default@high", "--dry-run"),
  );
  assert.equal(first.code, 0);
  assert.equal(second.code, 0);
  assert.ok(first.stdout.includes("model=(default)@high kind=pinned"));
  assert.ok(second.stdout.includes("model=(default)@high kind=pinned"));
});

test("main: --default-model with an explicit model and effort is still refused", () => {
  const result = withCarriers(
    args(effortProject(), ...EFFORT_SESSION, "--default-model", "--provider", "codex:sol@high", "--dry-run"),
  );
  assert.equal(result.code, 2);
  assert.ok(result.stderr.includes("--default-model cannot be combined with --provider 'codex:sol@high'"));
});
