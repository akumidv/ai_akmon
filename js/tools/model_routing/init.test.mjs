/**
 * node:test for `js/tools/model_routing/init.mjs` — the arguments, the settings and config
 * readers, and the exit codes. The byte-level spec is the `tools/init-*` scenarios of
 * `meta/conformance/scenarios`, run by `runner.py --impl node --area tools`.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { embeddedTreeRoot } from "../../akmon/_tree.mjs";
import { read } from "../../common/jsondata.mjs";
import { loadRegistry, registryHash } from "./routing.mjs";
import { main } from "./init.mjs";

const TREE = embeddedTreeRoot();
const AGENTS = /** @type {any} */ (read(path.join(TREE, "tools", "model_routing", "agents.json")));

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
 * A scratch project root holding `files`.
 * @param {Record<string, string>} [files]
 * @returns {string}
 */
function project(files = {}) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "init-test-"));
  fs.writeFileSync(path.join(root, "AGENTS.md"), "x");
  for (const [rel, text] of Object.entries(files)) {
    fs.mkdirSync(path.dirname(path.join(root, rel)), { recursive: true });
    fs.writeFileSync(path.join(root, rel), text);
  }
  return root;
}

test("a first run writes the six definitions and the local config, a second run changes nothing", () => {
  const root = project();
  const first = run(["--project-root", root]);
  assert.equal(first.code, 0);
  assert.equal(first.stdout.split("\n").filter((line) => line.startsWith("updated: ")).length, 7);
  assert.ok(fs.existsSync(path.join(root, ".claude", "model-routing.local.json")));
  const second = run(["--project-root", root]);
  assert.equal(second.code, 0);
  assert.equal(second.stdout.split("\n").filter((line) => line.startsWith("ok: ")).length, 7);
});

test("--check writes nothing and exits 1 on a stale tree; --dry-run writes nothing and exits 0", () => {
  const root = project();
  const check = run(["--project-root", root, "--check"]);
  assert.equal(check.code, 1);
  assert.match(check.stdout, /^would update: \.claude\/agents\/k_explorer\.md$/m);
  assert.equal(fs.existsSync(path.join(root, ".claude", "model-routing.local.json")), false);
  assert.equal(run(["--project-root", root, "--dry-run"]).code, 0);
  assert.equal(fs.existsSync(path.join(root, ".claude")), false);
});

test("the settings model is the orchestrator unless --orchestrator names one; local settings win", () => {
  const root = project({
    ".claude/settings.json": JSON.stringify({ model: "haiku" }),
    ".claude/settings.local.json": JSON.stringify({ model: "opus" }),
  });
  assert.match(run(["--project-root", root, "--check"]).stdout, /orchestrator=opus /);
  assert.match(run(["--project-root", root, "--check", "--orchestrator", "sonnet"]).stdout, /orchestrator=sonnet /);
});

test("an unreadable or non-object settings file is skipped, not an error", () => {
  for (const text of ["{nope", "[1]", '{"model": 5}', '{"model": ""}']) {
    const root = project({ ".claude/settings.json": text });
    const result = run(["--project-root", root, "--check"]);
    assert.equal(result.code, 1);
    assert.match(result.stdout, /orchestrator=opus /);
  }
});

test("--available binds the strongest listed alias; blanks are dropped", () => {
  const root = project();
  assert.match(
    run(["--project-root", root, "--check", "--available", " haiku , sonnet ,opus,"]).stdout,
    /orchestrator=opus /,
  );
});

test("the recorded second opinion survives a run without the flag, and the flag overrides it", () => {
  const root = project({ ".claude/model-routing.local.json": JSON.stringify({ second_opinion: true }) });
  assert.match(run(["--project-root", root, "--check"]).stdout, /\(on\)$/m);
  assert.match(run(["--project-root", root, "--check", "--second-opinion", "off"]).stdout, /\(off\)$/m);
  const broken = project({ ".claude/model-routing.local.json": "{bad" });
  assert.match(run(["--project-root", broken, "--check"]).stdout, /\(off\)$/m);
});

test("an overlay brief matching no agent is exit 2 with two error lines and no files", () => {
  const root = project({ "_aitna/model-routing.json": JSON.stringify({ briefs: { k_nobody: "x" } }) });
  const result = run(["--project-root", root]);
  assert.equal(result.code, 2);
  assert.equal(result.stdout, "");
  assert.match(result.stderr, /^error: overlay brief key 'k_nobody' matches no agent/);
  assert.match(result.stderr, /\nerror: fix _aitna\/model-routing\.json; no files were written\n$/);
  assert.equal(fs.existsSync(path.join(root, ".claude")), false);
});

test("a generated definition no longer planned is deleted; a hand-written one stays", () => {
  const banner =
    "<!-- Generated by akmon tools/model_routing/init.py from registry.json — edit the registry or the project overlay, not this file. -->";
  const root = project({
    ".claude/agents/k_old.md": `---\nname: x\n---\n\n${banner}\n`,
    ".claude/agents/mine.md": "hand written",
  });
  const dry = run(["--project-root", root, "--dry-run"]);
  assert.match(dry.stdout, /^would delete: \.claude\/agents\/k_old\.md$/m);
  assert.ok(fs.existsSync(path.join(root, ".claude/agents/k_old.md")));
  assert.match(run(["--project-root", root]).stdout, /^deleted: \.claude\/agents\/k_old\.md$/m);
  assert.equal(fs.existsSync(path.join(root, ".claude/agents/k_old.md")), false);
  assert.ok(fs.existsSync(path.join(root, ".claude/agents/mine.md")));
});

test("usage errors are one stderr line and exit 2; --help exits 0", () => {
  const root = project();
  for (const argv of [["--vendor", "nope"], ["--second-opinion", "maybe"], ["--bogus"], ["stray"]]) {
    const result = run(["--project-root", root, ...argv]);
    assert.equal(result.code, 2, argv.join(" "));
    assert.match(result.stderr, /^init\.mjs: error: [^\n]+\n$/);
  }
  assert.match(run(["--vendor", "nope", "--project-root", root]).stderr, /--vendor must be one of: anthropic, openai/);
  const help = run(["--help"]);
  assert.equal(help.code, 0);
  assert.match(help.stdout, /^usage: init\.mjs /);
});

/**
 * The `model:` line of a generated definition, or null when it carries none.
 * @param {string} root
 * @param {string} agent
 * @returns {string | null}
 */
function modelLine(root, agent) {
  const text = fs.readFileSync(path.join(root, ".claude", "agents", `${agent}.md`), "utf8");
  return text.match(/^model: (.+)$/m)?.[1] ?? null;
}

/**
 * The recorded local config of a scratch project.
 * @param {string} root
 * @returns {Record<string, any>}
 */
function localConfig(root) {
  return JSON.parse(fs.readFileSync(path.join(root, ".claude", "model-routing.local.json"), "utf8"));
}

test("without --available the committed ladder binds, every delegate is pinned and the ladder is recorded", () => {
  const root = project();
  assert.equal(run(["--project-root", root]).code, 0);
  for (const agent of ["k_explorer", "k_mechanic", "k_validator"]) {
    assert.equal(modelLine(root, agent), "haiku", agent);
  }
  assert.equal(modelLine(root, "k_implementer"), "sonnet");
  assert.equal(modelLine(root, "k_reasoner"), "opus");
  assert.equal(modelLine(root, "k_auditor"), "opus");
  const config = localConfig(root);
  assert.deepEqual(config.available, ["haiku", "sonnet", "opus"]);
  assert.equal(config.auditor_opt_in, null);
});

test("an auditor-only alias in --available never binds below the auditor", () => {
  const root = project();
  const result = run(["--project-root", root, "--available", "haiku,sonnet,opus,fable"]);
  assert.equal(result.code, 0);
  assert.match(result.stdout, /orchestrator=opus · reasoner=opus · auditor=opus · worker=haiku · mid=sonnet /);
  assert.equal(modelLine(root, "k_auditor"), "opus");
  assert.deepEqual(localConfig(root).available, ["haiku", "sonnet", "opus"]);
});

test("--auditor fable pins the auditor and records the opt-in", () => {
  const root = project();
  assert.equal(run(["--project-root", root, "--auditor", "fable"]).code, 0);
  assert.equal(modelLine(root, "k_auditor"), "fable");
  assert.equal(modelLine(root, "k_reasoner"), "opus");
  const config = localConfig(root);
  assert.equal(config.auditor_opt_in, "fable");
  assert.equal(config.binding.auditor, "fable");
  assert.deepEqual(config.available, ["haiku", "sonnet", "opus"]);
});

test("a refused --auditor or an inverted --available is one error line, exit 2 and no files", () => {
  const cases = [
    {
      argv: ["--available", "haiku,sonnet,opus", "--auditor", "fable"],
      error: /^error: --auditor fable must also be listed in --available \(haiku,sonnet,opus\)\n$/,
    },
    {
      argv: ["--auditor", "nope"],
      error: /^error: --auditor nope is not a rung of the anthropic ladder \(haiku,sonnet,opus\)[^\n]*\n$/,
    },
    {
      argv: ["--available", "opus,sonnet,haiku,fable"],
      error: /^error: --available opus,sonnet,haiku,fable is out of order: [^\n]*haiku,sonnet,opus[^\n]*\n$/,
    },
  ];
  for (const { argv, error } of cases) {
    const root = project();
    const result = run(["--project-root", root, ...argv]);
    assert.equal(result.code, 2, argv.join(" "));
    assert.equal(result.stdout, "");
    assert.match(result.stderr, error);
    assert.equal(fs.existsSync(path.join(root, ".claude")), false);
  }
});

test("the openai vendor binds its own committed ladder", () => {
  const root = project();
  assert.equal(run(["--project-root", root, "--vendor", "openai"]).code, 0);
  assert.equal(modelLine(root, "k_explorer"), "luna");
  assert.equal(modelLine(root, "k_implementer"), "terra");
  assert.equal(modelLine(root, "k_auditor"), "sol");
  assert.deepEqual(localConfig(root).available, ["luna", "terra", "sol"]);
  assert.equal(run(["--project-root", project(), "--vendor", "openai", "--auditor", "astra"]).code, 0);
});

test("--session-provider/--session-model record a session stanza; a lone model borrows the recorded provider, else the vendor's carrier", () => {
  const root = project();
  const first = run(["--project-root", root, "--session-provider", "codex", "--session-model", "sol"]);
  assert.equal(first.code, 0);
  assert.deepEqual(localConfig(root).session, { provider: "codex", model: "sol" });
  assert.match(first.stdout, /second-opinion=.+ \(off\)$/m);
  // a lone model keeps the recorded provider; a provider alone drops a model recorded for another one
  run(["--project-root", root, "--session-model", "terra"]);
  assert.deepEqual(localConfig(root).session, { provider: "codex", model: "terra" });
  run(["--project-root", root, "--session-provider", "qwen"]);
  assert.deepEqual(localConfig(root).session, { provider: "qwen" });
  run(["--project-root", root, "--session-provider", "qwen", "--session-model", "q1"]);
  run(["--project-root", root, "--session-provider", "qwen"]);
  assert.deepEqual(localConfig(root).session, { provider: "qwen", model: "q1" });
  // a re-run without the flags keeps the stanza
  run(["--project-root", root]);
  assert.deepEqual(localConfig(root).session, { provider: "qwen", model: "q1" });
  const bare = project();
  run(["--project-root", bare]);
  assert.equal("session" in localConfig(bare), false);
});

test("a lone --session-model with no recorded provider borrows the vendor's carrier", () => {
  const root = project();
  assert.equal(run(["--project-root", root, "--session-model", "opus"]).code, 0);
  assert.deepEqual(localConfig(root).session, { provider: "claude", model: "opus" });
  const openai = project();
  run(["--project-root", openai, "--vendor", "openai", "--session-model", "sol"]);
  assert.deepEqual(localConfig(openai).session, { provider: "codex", model: "sol" });
});

test("--session-family is recorded beside the provider and model, and kept only while the model is unchanged", () => {
  const root = project();
  const first = run([
    "--project-root",
    root,
    "--session-provider",
    "opencode",
    "--session-model",
    "x/y",
    "--session-family",
    "qwen",
  ]);
  assert.equal(first.code, 0);
  assert.deepEqual(localConfig(root).session, { provider: "opencode", model: "x/y", family: "qwen" });
  // a re-run without the flags keeps it; a new model drops the family recorded for the old one
  run(["--project-root", root]);
  assert.deepEqual(localConfig(root).session, { provider: "opencode", model: "x/y", family: "qwen" });
  run(["--project-root", root, "--session-model", "z"]);
  assert.deepEqual(localConfig(root).session, { provider: "opencode", model: "z" });
  // a family alone keeps the recorded provider and model
  run(["--project-root", root, "--session-family", "gemini"]);
  assert.deepEqual(localConfig(root).session, { provider: "opencode", model: "z", family: "gemini" });
});

test("--session-family outside the vocabulary is exit 2 naming the overlays that extend it; an overlay-added family passes", () => {
  const root = project();
  const refused = run(["--project-root", root, "--session-provider", "opencode", "--session-family", "deepseek"]);
  assert.equal(refused.code, 2);
  assert.match(
    refused.stderr,
    /^error: --session-family 'deepseek' is not in the family vocabulary \(claude, gpt, qwen, gemini\); add it by declaring second_opinion_policy\.families\.deepseek in _aitna\/local\/model-routing\.json to keep it to yourself, or _aitna\/model-routing\.json to share it with the team\n$/,
  );
  assert.equal(fs.existsSync(path.join(root, ".claude", "model-routing.local.json")), false);
  const extended = project({
    "_aitna/local/model-routing.json": JSON.stringify({
      second_opinion_policy: { families: { deepseek: "DeepSeek" } },
    }),
  });
  assert.equal(
    run(["--project-root", extended, "--session-provider", "opencode", "--session-family", "deepseek"]).code,
    0,
  );
  assert.deepEqual(localConfig(extended).session, { provider: "opencode", family: "deepseek" });
});

test("--vendor naming a carrier points at --session-provider; a name nothing declares keeps the plain refusal", () => {
  const root = project();
  const carrier = run(["--project-root", root, "--vendor", "qwen"]);
  assert.equal(carrier.code, 2);
  assert.match(
    carrier.stderr,
    /^init\.mjs: error: --vendor 'qwen' names a carrier, which has no tier-binding block of its own; --vendor must be one of: anthropic, openai/,
  );
  assert.match(carrier.stderr, /--session-provider qwen, with --session-model and --session-family\n$/);
  const unknown = run(["--project-root", root, "--vendor", "ghost"]);
  assert.equal(unknown.stderr, "init.mjs: error: --vendor must be one of: anthropic, openai\n");
});

test("a retired overlay key is exit 2 naming the file and the key, with nothing written", () => {
  const root = project({
    "_aitna/model-routing.json": JSON.stringify({ second_opinion_policy: { diversity_ladder: ["other-vendor"] } }),
  });
  const result = run(["--project-root", root]);
  assert.equal(result.code, 2);
  assert.equal(result.stdout, "");
  assert.match(result.stderr, /^error: .*_aitna\/model-routing\.json.*second_opinion_policy\.diversity_ladder/);
  assert.equal(fs.existsSync(path.join(root, ".claude")), false);
});

test("init reads the local overlay and records the hash of the merged registry", () => {
  const root = project({
    "_aitna/local/model-routing.json": JSON.stringify({ second_opinion_policy: { ladder: ["codex"] } }),
  });
  const first = run(["--project-root", root, "--orchestrator", "opus"]);
  assert.equal(first.code, 0);
  const merged = loadRegistry(AGENTS, TREE, root);
  assert.deepEqual(merged.second_opinion_policy.ladder, ["codex"]);
  assert.equal(localConfig(root).registry_hash, registryHash(merged));
});

test("a retired key in the local overlay is exit 2 naming that file, with nothing written", () => {
  const root = project({
    "_aitna/local/model-routing.json": JSON.stringify({ second_opinion_policy: { diversity_ladder: [] } }),
  });
  const result = run(["--project-root", root, "--orchestrator", "opus"]);
  assert.equal(result.code, 2);
  assert.match(result.stderr, /^error: the routing overlay _aitna\/local\/model-routing\.json still carries/);
  assert.equal(fs.existsSync(path.join(root, ".claude", "model-routing.local.json")), false);
});

test("an overlay that is not a JSON object is one error line and exit 2, with nothing written", () => {
  for (const [rel, content] of [
    ["_aitna/model-routing.json", "{ not json"],
    ["_aitna/local/model-routing.json", "[1, 2]"],
  ]) {
    const root = project({ [rel]: content });
    const result = run(["--project-root", root]);
    assert.equal(result.code, 2);
    assert.equal(result.stdout, "");
    assert.equal(
      result.stderr,
      `error: the routing overlay ${rel} is not a valid JSON object; repair or delete it (it is hand-owned, so akmon never rewrites it)\n`,
    );
    assert.equal(fs.existsSync(path.join(root, ".claude")), false);
  }
});

test("the init summary names what the second opinion would run first, resolved through the walk", () => {
  const root = project();
  const saved = process.env.PATH;
  const empty = fs.mkdtempSync(path.join(os.tmpdir(), "init-path-"));
  process.env.PATH = empty;
  try {
    assert.match(
      run(["--project-root", root, "--check", "--second-opinion", "on"]).stdout,
      /second-opinion=unavailable \(on\)$/m,
    );
  } finally {
    process.env.PATH = saved;
  }
});
