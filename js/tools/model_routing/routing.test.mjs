/**
 * node:test for `js/tools/model_routing/routing.mjs` — the places where a hook payload hands the
 * module a value the Python twin treats by truthiness. The full spec is
 * `meta/conformance/units/routing.toml`, run through `probe.mjs`.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import { posix } from "node:path";

import { embeddedTreeRoot } from "../../akmon/_tree.mjs";
import { read } from "../../common/jsondata.mjs";
import {
  Binding,
  EffortError,
  OverlayError,
  ProviderAliases,
  RetiredKeyError,
  SecondOpinionSession,
  SecondOpinionTarget,
  SessionUnknownError,
  UnpinnableModelError,
  UnresolvedAliasError,
  activeRole,
  bindingArtifacts,
  carrierPresent,
  catalogAliases,
  checkEffort,
  checkSessionFamily,
  detectOrchestrator,
  expandHome,
  familyVocabulary,
  hookOverlayLine,
  isModelAlias,
  ladderPinsDefault,
  lastMainTurn,
  loadRegistry,
  localAliasesPath,
  localConfig,
  localOverlayPath,
  localOverlayRel,
  modelAliasesDocument,
  opinionAsks,
  opinionChain,
  opinionCommand,
  opinionHead,
  opinionLastResort,
  opinionPick,
  opinionSkips,
  overlayPath,
  parseCatalog,
  providerFamily,
  providerRow,
  readModelAliases,
  refuseRetiredKeys,
  resolveOpinionChain,
  resolveOpinionModel,
  resolveSession,
  splitModelEffort,
  splitOpinionEntry,
  statusLines,
  toolCommand,
  vendorRefusal,
} from "./routing.mjs";

const TREE = embeddedTreeRoot();
const AGENTS = /** @type {any} */ (read(posix.join(TREE, "tools", "model_routing", "agents.json")));
const RUNTIME = /** @type {any} */ (read(posix.join(TREE, "common", "runtime.json")));
const SHIPPED = /** @type {any} */ (read(posix.join(TREE, "tools", "model_routing", "registry.json")));

/** A registry whose carriers are declared outright over `/bin/sh` (or a name no host has): presence is deterministic. */
function declared(/** @type {string[]} */ ladder) {
  return {
    ...SHIPPED,
    providers: {
      claude: { argv: ["/bin/sh", "-c", "{model}"], family: "claude", models: ["haiku", "opus"], report_dir: "r/c/" },
      sh1: { argv: ["/bin/sh", "-m", "{model}"], family: "gpt", models: ["m1", "m2"], report_dir: "r/1/" },
      sh2: { argv: ["/bin/sh", "-m", "{model}"], family: "claude", models: ["m3"], report_dir: "r/2/" },
      gone: { argv: ["akmon-no-such-binary"], family: "gemini", report_dir: "r/g/" },
      dup: { argv: ["/bin/sh", "-m", "{model}"], family: "llama", models: ["m2"], report_dir: "r/d/" },
    },
    second_opinion_policy: { ladder, model_rule: "max" },
  };
}

test("a falsy transcript_path of any JSON type is no transcript (Python: `if not transcript_path`)", () => {
  for (const empty of [null, undefined, "", 0, false, [], {}]) {
    assert.equal(activeRole(/** @type {any} */ (empty)), null);
    assert.deepEqual(lastMainTurn(/** @type {any} */ (empty)), [null, null]);
    assert.equal(detectOrchestrator(/** @type {any} */ (empty), ["opus"]), null);
  }
});

test("activeRole reads `🧭 role:` and the `🧭 agent:` alias, the last declaration winning", () => {
  const dir = fs.mkdtempSync(posix.join(os.tmpdir(), "akmon-role-decl-"));
  try {
    const turn = (/** @type {string} */ text) => JSON.stringify({ type: "assistant", message: { content: text } });
    const transcript = posix.join(dir, "t.jsonl");
    fs.writeFileSync(transcript, `${turn("🧭 agent: Review — alias")}\n`);
    assert.equal(activeRole(transcript), "review");
    fs.writeFileSync(transcript, `${turn("🧭 role: engineer — new")}\n${turn("🧭 agent: architect — alias")}\n`);
    assert.equal(activeRole(transcript), "architect");
    fs.writeFileSync(transcript, `${turn("🧭 agent: architect — alias")}\n${turn("🧭 role: Engineer — new")}\n`);
    assert.equal(activeRole(transcript), "engineer");
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});

test("a truthy transcript_path that is not a string is the TypeError Path() raises", () => {
  for (const bad of [5, true, ["x"], { a: 1 }]) {
    assert.throws(() => activeRole(/** @type {any} */ (bad)), { name: "TypeError" });
    assert.throws(() => lastMainTurn(/** @type {any} */ (bad)), { name: "TypeError" });
  }
});

test("the `$(akmon path)` sentinel names the installed package's carrier, `npx akmon tool` (C12, DV34)", () => {
  // The corpus folds `akmon tool` and `npx akmon tool` to one `{{tool}}`, so the spelling each twin
  // writes for the sentinel is pinned here and in `test_model_routing.py`, never by a scenario.
  const data = /** @type {any} */ (read(posix.join(embeddedTreeRoot(), "tools", "model_routing", "agents.json")));
  assert.equal(toolCommand(data, "$(akmon path)", "model_routing/gate_pack"), "npx akmon tool model_routing/gate_pack");
  assert.notEqual(toolCommand(data, "$(akmon path)", "x"), `akmon tool x`); // not the Python twin's spelling
  // Any other answer is a mounted tree, spelled the Python way — the sentinel is an exact match.
  assert.equal(
    toolCommand(data, "_aitna/akmon", "model_routing/init"),
    "python3 _aitna/akmon/tools/model_routing/init.py",
  );
  assert.equal(toolCommand(data, "$(akmon path) ", "x"), "python3 $(akmon path) /tools/x.py");
});

test("a ladder entry splits on its FIRST colon only; an empty model is no model", () => {
  assert.deepEqual(splitOpinionEntry("claude"), ["claude", null]);
  assert.deepEqual(splitOpinionEntry("opencode:qwen3:8b"), ["opencode", "qwen3:8b"]);
  assert.deepEqual(splitOpinionEntry("claude:"), ["claude", null]);
});

test("presence is a name on PATH, or an absolute path that is executable — never a directory", () => {
  const registry = declared(["claude"]);
  assert.equal(carrierPresent(AGENTS, RUNTIME, registry, "sh1", null), true);
  assert.equal(carrierPresent(AGENTS, RUNTIME, registry, "gone", null), false);
  const nameless = { ...registry, providers: { n: { family: "gpt" }, d: { argv: ["/tmp"] } } };
  assert.equal(carrierPresent(AGENTS, RUNTIME, nameless, "n", null), false);
  assert.equal(carrierPresent(AGENTS, RUNTIME, nameless, "d", null), false);
});

test("the walk skips self, absent, taken priors and a taken concrete model, in that order", () => {
  const registry = declared(["claude", "sh1", "sh2", "gone", "dup"]);
  const session = new SecondOpinionSession("claude", "claude", "opus");
  assert.deepEqual(
    opinionChain(AGENTS, RUNTIME, registry, session, null).map((target) => [
      target.provider,
      target.model,
      target.family,
    ]),
    [["sh1", "m2", "gpt"]],
  );
  assert.deepEqual(opinionSkips(AGENTS, RUNTIME, registry, session, null), [
    ["claude", "self"],
    ["sh2", "same priors as claude"],
    ["gone", "carrier absent"],
    ["dup", "same model as sh1"],
  ]);
  assert.equal(resolveOpinionChain(AGENTS, RUNTIME, registry, session, null, { rank: 3 }), null);
  assert.equal(resolveOpinionChain(AGENTS, RUNTIME, registry, session, null)?.provider, "sh1");
});

test("a session whose priors are unknown has an empty chain and one skip (D08)", () => {
  const registry = declared(["sh1"]);
  const session = new SecondOpinionSession("opencode", null, "x/y");
  assert.deepEqual(opinionChain(AGENTS, RUNTIME, registry, session, null), []);
  assert.deepEqual(opinionSkips(AGENTS, RUNTIME, registry, session, null), [["opencode", "session priors unknown"]]);
});

test("a model named `constructor` is a model, not an inherited property", () => {
  const registry = declared(["sh1"]);
  registry.providers.sh1.models = ["constructor"];
  const session = new SecondOpinionSession("claude", "claude", "constructor");
  assert.deepEqual(opinionSkips(AGENTS, RUNTIME, registry, session, null), [["sh1", "same model as claude"]]);
});

test("the last resort is another declared model of the session's own provider, else the default", () => {
  const registry = declared(["sh1"]);
  const other = opinionLastResort(AGENTS, registry, new SecondOpinionSession("sh1", "gpt", "m2"), null);
  assert.deepEqual({ ...other }, { provider: "sh1", model: "m1", family: "gpt", effort: null });
  const none = opinionLastResort(AGENTS, registry, new SecondOpinionSession("gone", "gemini", "x"), null);
  assert.deepEqual({ ...none }, { provider: "gone", model: null, family: "gemini", effort: null });
});

test("a model's own family wins over the row's; an unnamed multi-family model is unknown", () => {
  const registry = declared(["sh1"]);
  registry.providers.sh1.model_families = { "a/b:c": "gemini" };
  assert.equal(providerFamily(AGENTS, registry, "sh1", null, "a/b:c"), "gemini");
  assert.equal(providerFamily(AGENTS, registry, "sh1", null, "m1"), "gpt");
  assert.equal(providerFamily(AGENTS, SHIPPED, "opencode", null, "x/y"), null);
  assert.throws(() => providerFamily(AGENTS, SHIPPED, "ghost", null), { name: "KeyError" });
});

test("the session: arguments, then the stanza, then the bound vendor; another layer lends nothing", () => {
  const config = { vendor: "anthropic", orchestrator: "opus", session: { provider: "qwen", model: "q3" } };
  assert.deepEqual(
    { ...resolveSession(AGENTS, SHIPPED, { vendor: "anthropic", orchestrator: "opus" }) },
    {
      provider: "claude",
      family: "claude",
      model: "opus",
    },
  );
  assert.deepEqual({ ...resolveSession(AGENTS, SHIPPED, config) }, { provider: "qwen", family: "qwen", model: "q3" });
  assert.deepEqual(
    { ...resolveSession(AGENTS, SHIPPED, config, { provider: "codex" }) },
    {
      provider: "codex",
      family: "gpt",
      model: null,
    },
  );
  assert.throws(() => resolveSession(AGENTS, SHIPPED, {}), SessionUnknownError);
});

test("a declared argv pins by placeholder and never by splitting; a `$&` model is not a replacement pattern", () => {
  const registry = { providers: { d: { argv: ["d-bin", "-m", "{model}", "--flag"] }, u: { argv: ["u-bin"] } } };
  assert.deepEqual(opinionCommand(AGENTS, RUNTIME, registry, "d", null, { model: "a$&b", prompt: "p" }), [
    "d-bin",
    "-m",
    "a$&b",
    "--flag",
    "p",
  ]);
  // Unpinned, the part holding the placeholder goes and the bare flag that pointed at it goes too.
  assert.deepEqual(opinionCommand(AGENTS, RUNTIME, registry, "d", null), ["d-bin", "--flag"]);
  assert.throws(() => opinionCommand(AGENTS, RUNTIME, registry, "u", null, { model: "m" }), UnpinnableModelError);
  const stdin = { providers: { s: { argv: ["s"], prompt: "stdin" } } };
  assert.deepEqual(opinionCommand(AGENTS, RUNTIME, stdin, "s", null, { prompt: "p" }), ["s"]);
});

test("a shipped carrier's command comes from the map plus the row's model flag", () => {
  assert.deepEqual(opinionCommand(AGENTS, RUNTIME, SHIPPED, "claude", null, { model: "opus", prompt: "p" }), [
    "claude",
    "-p",
    "--output-format",
    "text",
    "--model",
    "opus",
    "p",
  ]);
  assert.deepEqual(opinionCommand(AGENTS, RUNTIME, SHIPPED, "opencode", null, { model: "x/y:z", prompt: "p" }), [
    "opencode",
    "run",
    "--agent",
    "plan",
    "-m",
    "x/y:z",
    "p",
  ]);
});

test("a retired key is refused by name and file, in the overlay and in the local config", () => {
  const overlay = { ...SHIPPED, second_opinion_policy: { diversity_ladder: [] }, openai: { second_opinion: {} } };
  assert.throws(
    () => refuseRetiredKeys(AGENTS, overlay, {}, null),
    (error) => {
      assert.ok(error instanceof RetiredKeyError);
      assert.match(error.message, /second_opinion_policy\.diversity_ladder, (?:\w+)\.second_opinion/);
      return true;
    },
  );
  assert.throws(() => refuseRetiredKeys(AGENTS, SHIPPED, { second_opinion_provider: "x" }, null), RetiredKeyError);
  assert.doesNotThrow(() => refuseRetiredKeys(AGENTS, SHIPPED, { vendor: "anthropic", session: {} }, null));
});

test("the head names the first provider, or says why there is none", () => {
  const registry = declared(["claude", "sh1"]);
  const session = { provider: "claude", model: "opus" };
  assert.deepEqual(opinionHead(AGENTS, RUNTIME, registry, { session }, null), ["sh1:m2 priors=gpt", null]);
  const alone = declared(["claude"]);
  const [display, warning] = opinionHead(AGENTS, RUNTIME, alone, { session }, null);
  assert.equal(display, "unavailable");
  assert.match(String(warning), /provider chain is empty/);
  assert.deepEqual(opinionHead(AGENTS, RUNTIME, registry, {}, null)[0], "unavailable priors=unknown");
});

test("the status line shows the head and the on/off state; a retired key costs the whole block", () => {
  const registry = declared(["claude", "sh1"]);
  const config = { vendor: "anthropic", orchestrator: "opus", second_opinion: true, session: { provider: "claude" } };
  const lines = statusLines(AGENTS, RUNTIME, config, registry, "init", null);
  assert.match(lines[0], /second-opinion=sh1:m2 priors=gpt \(on\)$/);
  assert.throws(() => statusLines(AGENTS, RUNTIME, { ...config, second_opinion_provider: "x" }, registry, "i", null), {
    name: "RetiredKeyError",
  });
});

test("the local config records the session stanza only when one is given, and the binding carries no second-opinion cli", () => {
  const binding = new Binding("anthropic", "opus", "opus", "haiku", "sonnet", "opus", ["sonnet"]);
  assert.equal("secondOpinionCli" in binding, false);
  const plain = localConfig(AGENTS, binding, SHIPPED, { secondOpinion: false, available: null });
  assert.equal("session" in plain, false);
  assert.equal("second_opinion_provider" in plain, false);
  const session = { provider: "qwen", model: "q" };
  const stated = localConfig(AGENTS, binding, SHIPPED, { secondOpinion: false, available: null, session });
  assert.deepEqual(stated.session, session);
  assert.notEqual(stated.session, session);
  const files = bindingArtifacts(AGENTS, SHIPPED, binding, { secondOpinion: false, available: null, session });
  assert.match(files[".claude/model-routing.local.json"], /"session"/);
});

/**
 * A scratch project holding the shipped registry under `_aitna/akmon` and the given overlay files.
 * @param {Record<string, string>} [files] project-root-relative path to text
 * @returns {string}
 */
function scratch(files = {}) {
  const root = fs.mkdtempSync(posix.join(os.tmpdir(), "routing-test-"));
  const all = { "_aitna/akmon/tools/model_routing/registry.json": JSON.stringify(SHIPPED), ...files };
  for (const [rel, text] of Object.entries(all)) {
    fs.mkdirSync(posix.dirname(posix.join(root, rel)), { recursive: true });
    fs.writeFileSync(posix.join(root, rel), text);
  }
  return root;
}

test("the developer's overlay sits under the dev layer's local folder, wherever `.aitna-root` puts the layer", () => {
  assert.equal(localOverlayRel(AGENTS), ".local/model-routing.json");
  const root = scratch();
  assert.equal(localOverlayPath(AGENTS, root), `${root}/_aitna/.local/model-routing.json`);
  assert.equal(overlayPath(AGENTS, root), `${root}/_aitna/model-routing.json`);
  fs.writeFileSync(posix.join(root, ".aitna-root"), "meta\n");
  assert.equal(localOverlayPath(AGENTS, root), `${root}/meta/.local/model-routing.json`);
  assert.equal(overlayPath(AGENTS, root), `${root}/meta/model-routing.json`);
  fs.rmSync(root, { recursive: true, force: true });
});

test("the local overlay is the strongest layer, a ladder is replaced whole and a sibling key survives", () => {
  const root = scratch({
    "_aitna/model-routing.json": JSON.stringify({
      second_opinion_policy: { ladder: ["claude", "codex"], model_rule: "max" },
      briefs: { k_explorer: "Team." },
    }),
    "_aitna/.local/model-routing.json": JSON.stringify({
      second_opinion_policy: { ladder: ["codex"] },
      briefs: { k_explorer: "Mine." },
    }),
  });
  const merged = loadRegistry(AGENTS, posix.join(root, "_aitna", "akmon"), root);
  assert.deepEqual(merged.second_opinion_policy.ladder, ["codex"]);
  assert.equal(merged.second_opinion_policy.model_rule, "max");
  assert.deepEqual(merged.briefs, { k_explorer: "Mine." });
});

test("the local overlay alone merges over the shipped registry; a directory is no layer", () => {
  const alone = scratch({ "_aitna/.local/model-routing.json": '{"briefs": {"k_explorer": "Mine."}}' });
  assert.deepEqual(loadRegistry(AGENTS, posix.join(alone, "_aitna", "akmon"), alone).briefs, { k_explorer: "Mine." });
  const folder = scratch();
  fs.mkdirSync(posix.join(folder, "_aitna", ".local", "model-routing.json"), { recursive: true });
  assert.deepEqual(loadRegistry(AGENTS, posix.join(folder, "_aitna", "akmon"), folder), SHIPPED);
});

test("an overlay layer that is not a JSON object is a named one-line error quoting its file", () => {
  for (const [layer, file] of [
    ["_aitna/model-routing.json", "_aitna/model-routing.json"],
    ["_aitna/.local/model-routing.json", "_aitna/.local/model-routing.json"],
  ]) {
    for (const content of ["{ not json", "[1, 2]"]) {
      const root = scratch({ [layer]: content });
      assert.throws(
        () => loadRegistry(AGENTS, posix.join(root, "_aitna", "akmon"), root),
        (error) => {
          assert.ok(error instanceof OverlayError);
          assert.equal(error.name, "OverlayError");
          assert.ok(error.message.includes(file), error.message);
          assert.ok(!error.message.includes("\n"));
          return true;
        },
      );
    }
  }
});

test("a retired key is named in the layer that holds it: the strongest holder first, only its own keys", () => {
  const local = scratch({
    "_aitna/model-routing.json": '{"briefs": {}}',
    "_aitna/.local/model-routing.json": '{"second_opinion_policy": {"diversity_ladder": []}}',
  });
  assert.throws(
    () => refuseRetiredKeys(AGENTS, {}, {}, local, { layered: true }),
    (error) => {
      assert.ok(error instanceof RetiredKeyError);
      assert.match(
        error.message,
        /^the routing overlay _aitna\/.local\/model-routing\.json still carries the retired key\(s\) second_opinion_policy\.diversity_ladder /,
      );
      return true;
    },
  );
  const both = scratch({
    "_aitna/model-routing.json": '{"openai": {"second_opinion": {}}}',
    "_aitna/.local/model-routing.json": '{"second_opinion_policy": {"diversity_ladder": []}}',
  });
  assert.throws(
    () => refuseRetiredKeys(AGENTS, {}, {}, both, { layered: true }),
    /the routing overlay _aitna\/.local\/model-routing\.json still carries the retired key\(s\) second_opinion_policy\.diversity_ladder \(ADR/,
  );
  const project = scratch({
    "_aitna/model-routing.json": '{"openai": {"second_opinion": {"report_dir": "x"}}}',
    "_aitna/.local/model-routing.json": '{"briefs": {}}',
  });
  assert.throws(
    () => refuseRetiredKeys(AGENTS, {}, {}, project, { layered: true }),
    /the routing overlay _aitna\/model-routing\.json still carries the retired key\(s\) openai\.second_opinion \(ADR/,
  );
});

test("without a project root a retired key in the merged registry names both candidate files", () => {
  assert.throws(
    () => refuseRetiredKeys(AGENTS, { second_opinion_policy: { diversity_ladder: [] } }, {}, null),
    /the routing overlay _aitna\/.local\/model-routing\.json or _aitna\/model-routing\.json still carries/,
  );
});

test("an unlayered retired-key refusal names both files under the declared dev root", () => {
  const root = scratch({ ".aitna-root": "tools/ai\n" });
  try {
    assert.throws(
      () => refuseRetiredKeys(AGENTS, { second_opinion_policy: { diversity_ladder: [] } }, {}, root),
      (error) => {
        assert.ok(error instanceof RetiredKeyError);
        assert.ok(error.message.includes("tools/ai/.local/model-routing.json or tools/ai/model-routing.json"));
        assert.ok(!error.message.includes("_aitna"));
        return true;
      },
    );
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});

test("an unpinned declared argv drops each element holding the placeholder and the bare flag that pointed at a lone one", () => {
  const argvOf = (/** @type {string[]} */ ...argv) => ({ providers: { d: { argv } } });
  const run = (/** @type {any} */ registry, /** @type {any} */ options = {}) =>
    opinionCommand(AGENTS, RUNTIME, registry, "d", null, options);
  assert.deepEqual(run(argvOf("qwen", "-m", "{model}")), ["qwen"]);
  assert.deepEqual(run(argvOf("d-bin", "-m", "{model}", "--flag"), { prompt: "p" }), ["d-bin", "--flag", "p"]);
  // `--model={model}` carries its own flag: only that element goes and the one before it stays.
  assert.deepEqual(run(argvOf("d-bin", "--keep", "--model={model}", "--x")), ["d-bin", "--keep", "--x"]);
  // Only a bare flag is paired with the value after it; a subcommand or `--k=v` stays.
  assert.deepEqual(run(argvOf("d-bin", "run", "{model}")), ["d-bin", "run"]);
  assert.deepEqual(run(argvOf("d-bin", "--k=v", "{model}")), ["d-bin", "--k=v"]);
  assert.deepEqual(run(argvOf("{model}", "x")), ["x"]);
  assert.deepEqual(run(argvOf("d-bin", "-m", "{model}", "-n", "1", "--alt", "{model}")), ["d-bin", "-n", "1"]);
  // Pinned, nothing is dropped.
  assert.deepEqual(run(argvOf("d-bin", "-m", "{model}", "--model={model}"), { model: "m1" }), [
    "d-bin",
    "-m",
    "m1",
    "--model=m1",
  ]);
});

test("an ask names the local overlay first and the project overlay second; a session ask then the recorded family", () => {
  const local = "_aitna/.local/model-routing.json";
  const project = "_aitna/model-routing.json";
  const registry = {
    ...SHIPPED,
    providers: {
      claude: { argv: ["/bin/sh"], family: "claude", report_dir: "r/c/" },
      pi: { argv: ["/bin/sh"], report_dir: "r/p/" },
    },
    second_opinion_policy: { ladder: ["claude", "pi"] },
  };
  const asks = opinionAsks(AGENTS, RUNTIME, registry, new SecondOpinionSession("claude", "claude", null), null);
  assert.deepEqual(asks, [
    `pi: priors unknown for its default model; declare providers.pi.family in ${local} to keep it to yourself, or ${project} to share it with the team`,
  ]);
  const [ask] = opinionAsks(
    AGENTS,
    RUNTIME,
    SHIPPED,
    new SecondOpinionSession("opencode", null, "undeclared/model"),
    null,
  );
  assert.ok(ask.indexOf(local) < ask.indexOf(project) && ask.indexOf(project) < ask.indexOf("session.family"), ask);
  assert.ok(ask.includes("to keep it to yourself") && ask.includes("to share it with the team"));
});

test("the project overlay path is still the shared file beside the local folder", () => {
  assert.equal(overlayPath(AGENTS, "/p"), "/p/_aitna/model-routing.json");
});

test("an unknown ladder id names both overlay files to edit", () => {
  assert.throws(
    () => providerRow(AGENTS, { providers: {} }, "ghost", null),
    (/** @type {any} */ error) => {
      assert.equal(error.name, "KeyError");
      assert.match(error.message, /the ladder names 'ghost', which the providers table does not declare; /);
      assert.match(error.message, /declare providers\.ghost or remove it from second_opinion_policy\.ladder in /);
      assert.match(
        error.message,
        /_aitna\/.local\/model-routing\.json \(yours\) or _aitna\/model-routing\.json \(the team's\)/,
      );
      return true;
    },
  );
});

test("the family vocabulary is the keys of second_opinion_policy.families, empty when it is not an object", () => {
  assert.deepEqual(familyVocabulary(SHIPPED), ["claude", "gpt", "qwen", "gemini"]);
  assert.deepEqual(familyVocabulary({}), []);
  assert.deepEqual(familyVocabulary({ second_opinion_policy: { families: ["claude"] } }), []);
  assert.deepEqual(familyVocabulary({ second_opinion_policy: { families: { a: "x", b: "y" } } }), ["a", "b"]);
});

test("checkSessionFamily accepts a member and refuses the rest naming the overlay to extend", () => {
  checkSessionFamily(AGENTS, SHIPPED, "qwen", null);
  assert.throws(
    () => checkSessionFamily(AGENTS, SHIPPED, "mimo", null),
    (/** @type {any} */ error) => {
      assert.equal(error.name, "ValueError");
      assert.match(
        error.message,
        /^--session-family 'mimo' is not in the family vocabulary \(claude, gpt, qwen, gemini\)/,
      );
      assert.match(error.message, /second_opinion_policy\.families\.mimo in _aitna\/.local\/model-routing\.json/);
      return true;
    },
  );
});

test("vendorRefusal tells a carrier where to start and a stranger only the vendors", () => {
  assert.match(
    vendorRefusal(AGENTS, SHIPPED, "qwen", ["anthropic", "openai"]),
    /^--vendor 'qwen' names a carrier.*--session-provider qwen/,
  );
  assert.equal(
    vendorRefusal(AGENTS, SHIPPED, "ghost", ["anthropic", "openai"]),
    "--vendor must be one of: anthropic, openai",
  );
});

test("hookOverlayLine is the hook, the file the error names, and what the hook costs", () => {
  const error = new OverlayError(
    "the routing overlay _aitna/model-routing.json is not a valid JSON object; repair or delete it",
  );
  assert.equal(
    hookOverlayLine(AGENTS, "gate-audit", error),
    "akmon gate-audit hook: the routing overlay _aitna/model-routing.json is not a valid JSON object; repair or delete it — the gate audit is skipped",
  );
});

// -- ADR-0024/D16: aliases resolve locally to concrete ids; `default` is the carrier's own model --

/** A registry whose codex row declares aliases and a catalog, its carrier declared over `/bin/sh` so presence holds. */
const ALIAS_REGISTRY = {
  ...SHIPPED,
  providers: {
    codex: {
      argv: ["/bin/sh", "-m", "{model}"],
      family: "gpt",
      models: ["luna", "terra", "sol"],
      aliases: true,
      catalog: { file: "~/.codex/models_cache.json", format: "codex-models-cache" },
      report_dir: "r/x/",
    },
    claude: { argv: ["/bin/sh", "-c", "{model}"], family: "claude", models: ["opus"], report_dir: "r/c/" },
  },
  second_opinion_policy: { ladder: ["codex:default", "claude"], model_rule: "max" },
};

/** @type {Array<[string, string, number | null]>} */
const HOST_SLUGS = [
  ["gpt-6.1-sol", "list", 0],
  ["gpt-6.1-terra", "list", 1],
  ["gpt-6-astra", "list", 3],
  ["gpt-6-sol", "list", 4],
  ["gpt-reserve", "hide", 4],
  ["gpt-6-luna", "list", 5],
  ["gpt-5.6-sol", "list", 6],
  ["gpt-5.6-terra", "list", 7],
  ["gpt-5.6-luna", "list", 8],
  ["codex-auto-review", "hide", 43],
];

/**
 * A `codex-models-cache` text listing `slugs`.
 * @param {Array<[string, string, number | null]>} [slugs]
 * @returns {string}
 */
function catalogText(slugs = HOST_SLUGS) {
  const models = slugs.map(([slug, visibility, priority]) => ({ slug, visibility, priority }));
  return JSON.stringify({ client_version: "0.164.0", models });
}

/**
 * The catalog `text` read as a codex models cache.
 * @param {string} text
 */
function parsed(text) {
  return parseCatalog(AGENTS, text, "codex-models-cache");
}

test("the host catalog maps each alias to its highest version", () => {
  const catalog = parsed(catalogText());
  assert.equal(catalog.client, "0.164.0");
  assert.deepEqual(catalogAliases(catalog, ["luna", "terra", "sol"]), {
    luna: "gpt-6-luna",
    terra: "gpt-6.1-terra",
    sol: "gpt-6.1-sol",
  });
});

test("a catalog ignores hidden and unversioned slugs and leaves an unmatched alias unmapped", () => {
  const catalog = parsed(catalogText());
  assert.deepEqual(
    catalog.models.map((model) => model.slug),
    [
      "gpt-6.1-sol",
      "gpt-6.1-terra",
      "gpt-6-astra",
      "gpt-6-sol",
      "gpt-6-luna",
      "gpt-5.6-sol",
      "gpt-5.6-terra",
      "gpt-5.6-luna",
    ],
  );
  assert.deepEqual(catalogAliases(catalog, ["sol", "nova"]), { sol: "gpt-6.1-sol" });
});

test("a version tie goes to the lowest priority, then to the first listed", () => {
  const catalog = parsed(
    catalogText([
      ["gpt-6-sol", "list", 9],
      ["acme-6-sol", "list", 2],
      ["zed-6-sol", "list", 2],
      ["gpt-6-luna", "list", null],
    ]),
  );
  assert.deepEqual(catalogAliases(catalog, ["sol", "luna"]), { sol: "acme-6-sol", luna: "gpt-6-luna" });
});

test("a longer version outranks its prefix, and versions compare numerically (6.10 above 6.9)", () => {
  const longer = parsed(
    catalogText([
      ["gpt-6-sol", "list", 0],
      ["gpt-6.0.1-sol", "list", 5],
    ]),
  );
  assert.deepEqual(catalogAliases(longer, ["sol"]), { sol: "gpt-6.0.1-sol" });
  const numeric = parsed(
    catalogText([
      ["gpt-6.9-sol", "list", 0],
      ["gpt-6.10-sol", "list", 5],
    ]),
  );
  assert.deepEqual(catalogAliases(numeric, ["sol"]), { sol: "gpt-6.10-sol" });
});

test("a catalog that cannot be read raises the reason", () => {
  /** @type {Array<[string, string, string]>} */
  const cases = [
    ["{}", "nope", "format 'nope' is not one of: codex-models-cache"],
    ["not json", "codex-models-cache", "is not valid JSON"],
    ["[]", "codex-models-cache", "holds no `models` list"],
    ['{"models": 3}', "codex-models-cache", "holds no `models` list"],
  ];
  for (const [text, format, reason] of cases) {
    assert.throws(() => parseCatalog(AGENTS, text, format), { name: "ValueError", message: reason });
  }
});

test("expandHome takes only a leading tilde", () => {
  assert.equal(expandHome("~/.codex/m.json", "/home/a"), "/home/a/.codex/m.json");
  assert.equal(expandHome("~", "/home/a/"), "/home/a");
  assert.equal(expandHome("~/x", "/"), "/x");
  assert.equal(expandHome("~bob/x", "/home/a"), "~bob/x");
  assert.equal(expandHome("/abs/~/x", "/home/a"), "/abs/~/x");
});

/**
 * A stored map with codex's `aliases`.
 * @param {Record<string, string>} aliases
 * @returns {Record<string, ProviderAliases>}
 */
function stored(aliases) {
  return { codex: new ProviderAliases("src", null, aliases) };
}

test("an alias resolves to the stored concrete id; a concrete id and the default pass through", () => {
  assert.equal(
    resolveOpinionModel(AGENTS, ALIAS_REGISTRY, stored({ sol: "gpt-6.1-sol" }), "codex", "sol", null),
    "gpt-6.1-sol",
  );
  assert.equal(resolveOpinionModel(AGENTS, ALIAS_REGISTRY, {}, "codex", "gpt-6.1-sol", null), "gpt-6.1-sol");
  assert.equal(resolveOpinionModel(AGENTS, ALIAS_REGISTRY, {}, "codex", null, null), null);
});

test("a row without aliases never resolves anything", () => {
  assert.equal(resolveOpinionModel(AGENTS, ALIAS_REGISTRY, {}, "claude", "opus", null), "opus");
});

test("an alias without a mapping is refused naming the refresh", () => {
  assert.throws(
    () => resolveOpinionModel(AGENTS, ALIAS_REGISTRY, stored({ luna: "gpt-6-luna" }), "codex", "sol", null),
    (error) => {
      assert.ok(error instanceof UnresolvedAliasError);
      assert.match(error.message, /'sol'/);
      assert.ok(error.message.includes("_aitna/.local/model-aliases.json"));
      assert.ok(error.message.includes("akmon tool model_routing/models --refresh --provider codex"));
      return true;
    },
  );
});

test("the resolved aliases file round-trips and a missing one is empty", () => {
  const root = fs.mkdtempSync(posix.join(os.tmpdir(), "routing-aliases-"));
  assert.deepEqual(readModelAliases(AGENTS, root), {});
  const entries = {
    codex: new ProviderAliases("~/x (codex-models-cache)", "0.164.0", { sol: "gpt-6.1-sol" }),
  };
  const path = localAliasesPath(AGENTS, root);
  fs.mkdirSync(posix.dirname(path), { recursive: true });
  fs.writeFileSync(path, modelAliasesDocument(entries));
  assert.deepEqual(readModelAliases(AGENTS, root), entries);
  assert.deepEqual(JSON.parse(fs.readFileSync(path, "utf-8")), {
    codex: { source: "~/x (codex-models-cache)", client: "0.164.0", aliases: { sol: "gpt-6.1-sol" } },
  });
  assert.ok(fs.readFileSync(path, "utf-8").endsWith("}\n"));
});

test("a resolved aliases file of the wrong shape is refused naming it", () => {
  const texts = [
    "not json",
    "[]",
    '{"codex": 1}',
    '{"codex": {"source": "s", "client": 3, "aliases": {}}}',
    '{"codex": {"source": "s", "client": null, "aliases": {"sol": 1}}}',
  ];
  for (const text of texts) {
    const root = fs.mkdtempSync(posix.join(os.tmpdir(), "routing-aliases-"));
    const path = localAliasesPath(AGENTS, root);
    fs.mkdirSync(posix.dirname(path), { recursive: true });
    fs.writeFileSync(path, text);
    assert.throws(() => readModelAliases(AGENTS, root), {
      name: "ValueError",
      message: /_aitna\/.local\/model-aliases\.json/,
    });
  }
});

test("the default token drops the pin and no pin keeps the strongest model", () => {
  assert.deepEqual(opinionPick(AGENTS, ALIAS_REGISTRY, "codex", "default", null), [null, null]);
  assert.deepEqual(opinionPick(AGENTS, ALIAS_REGISTRY, "codex", null, null), ["sol", null]);
  assert.deepEqual(opinionPick(AGENTS, ALIAS_REGISTRY, "codex", "gpt-6.1-sol", null), ["gpt-6.1-sol", null]);
});

test("a ladder entry with the default token is found", () => {
  assert.equal(ladderPinsDefault(AGENTS, ALIAS_REGISTRY, "codex"), true);
  assert.equal(ladderPinsDefault(AGENTS, ALIAS_REGISTRY, "claude"), false);
});

test("a default ladder entry walks to a target with no pin", () => {
  const session = new SecondOpinionSession("claude", "claude", "opus");
  const chain = opinionChain(AGENTS, RUNTIME, ALIAS_REGISTRY, session, null);
  assert.deepEqual(
    chain.map((target) => [target.provider, target.model]),
    [["codex", null]],
  );
});

test("agents.json carries the alias file location, the default token and the two error tables", () => {
  assert.equal(AGENTS.local_aliases_rel, ".local/model-aliases.json");
  assert.equal(AGENTS.default_model_token, "default");
  for (const key of ["catalog_errors", "alias_errors"]) {
    assert.equal(typeof AGENTS[key], "object");
  }
});

// -- ADR-0024/D17: a reasoning effort is a parameter of the model, `model@effort` --

const EFFORT_ROW = { flag: "--e {effort}", levels: ["low", "high"] };

/** The Python twin's `_EFFORT_REGISTRY`: harness rows and a declared argv row, each with or without `efforts`. */
const EFFORT_REGISTRY = {
  providers: {
    claude: {
      operation: "review",
      model_flag: "--model {model}",
      family: "claude",
      models: ["haiku", "sonnet", "opus", "opus@high"],
      efforts: { flag: "--effort {effort}", levels: ["low", "medium", "high"] },
    },
    codex: {
      operation: "review",
      model_flag: "--model {model}",
      family: "gpt",
      models: ["luna", "terra", "sol"],
      aliases: true,
      efforts: { flag: "-c model_reasoning_effort={effort}", levels: ["low", "high"] },
    },
    qwen: { operation: "review", model_flag: "-m {model}", family: "qwen", models: [] },
    mine: {
      argv: ["mine", "-m", "{model}"],
      family: "llama",
      models: ["m1", "m1@max"],
      efforts: { flag: "--think {effort}", levels: ["high", "max"] },
    },
  },
  second_opinion_policy: { ladder: ["claude:opus@high", "mine", "qwen"], model_rule: "max" },
};

/**
 * `EFFORT_REGISTRY` with every carrier declared over `/bin/sh`, so presence holds and the walk is deterministic.
 * @param {string[]} ladder
 */
function effortDeclared(ladder) {
  const providers = Object.fromEntries(
    Object.entries(EFFORT_REGISTRY.providers).map(([name, row]) => {
      const { operation: _operation, model_flag: _flag, ...kept } = /** @type {any} */ (row);
      return [name, { ...kept, argv: ["/bin/sh", "-m", "{model}"] }];
    }),
  );
  return { providers, second_opinion_policy: { ladder, model_rule: "max" } };
}

test("a model splits at its last at sign into the model and the effort", () => {
  /** @type {Array<[string | null, [string | null, string | null]]>} */
  const rows = [
    [null, [null, null]],
    ["sol", ["sol", null]],
    ["sol@high", ["sol", "high"]],
    ["acme/qwen3.8-27b-max", ["acme/qwen3.8-27b-max", null]],
    ["a/b@c@d", ["a/b@c", "d"]],
    ["default@high", ["default", "high"]],
    ["@high", [null, "high"]],
    ["m@", ["m", ""]],
  ];
  for (const [text, expected] of rows) {
    assert.deepEqual(splitModelEffort(text), expected, String(text));
  }
});

test("an effort a row lists is accepted and none is always accepted", () => {
  checkEffort(AGENTS, EFFORT_REGISTRY, "claude", "high", null);
  checkEffort(AGENTS, EFFORT_REGISTRY, "qwen", null, null);
});

test("an effort on a carrier with no efforts is refused naming the carrier", () => {
  assert.throws(
    () => checkEffort(AGENTS, EFFORT_REGISTRY, "qwen", "high", null),
    (/** @type {any} */ error) => {
      assert.ok(error instanceof EffortError);
      assert.ok(error instanceof Error);
      assert.ok(
        error.message.startsWith("provider 'qwen' declares no `efforts`, so the effort 'high' cannot be sent to it"),
      );
      assert.ok(error.message.includes("providers.qwen.efforts"));
      return true;
    },
  );
});

test("a level outside the rows levels is refused naming the accepted ones", () => {
  assert.throws(() => checkEffort(AGENTS, EFFORT_REGISTRY, "claude", "max", null), {
    name: "EffortError",
    message: "provider 'claude' does not accept the effort 'max'; its levels are: low, medium, high",
  });
});

test("a pick returns the model and its effort", () => {
  /** @type {Array<[string | null, [string | null, string | null]]>} */
  const rows = [
    [null, ["opus", "high"]],
    ["sonnet", ["sonnet", null]],
    ["sonnet@low", ["sonnet", "low"]],
    ["default", [null, null]],
    ["default@high", [null, "high"]],
    ["@low", ["opus", "low"]],
  ];
  for (const [pinned, expected] of rows) {
    assert.deepEqual(opinionPick(AGENTS, EFFORT_REGISTRY, "claude", pinned, null), expected, String(pinned));
  }
});

test("the strongest declared entry carries its own effort", () => {
  assert.deepEqual(opinionPick(AGENTS, EFFORT_REGISTRY, "mine", null, null), ["m1", "max"]);
});

test("a pick refuses an effort the carrier cannot take", () => {
  assert.throws(() => opinionPick(AGENTS, EFFORT_REGISTRY, "qwen", "q@high", null), EffortError);
  assert.throws(() => opinionPick(AGENTS, EFFORT_REGISTRY, "claude", "opus@max", null), EffortError);
});

test("a harness command appends the effort flag after the model flag", () => {
  assert.deepEqual(
    opinionCommand(AGENTS, RUNTIME, EFFORT_REGISTRY, "claude", null, { model: "opus", effort: "high", prompt: "p" }),
    ["claude", "-p", "--output-format", "text", "--model", "opus", "--effort", "high", "p"],
  );
});

test("an effort without a model sends only the level", () => {
  assert.deepEqual(opinionCommand(AGENTS, RUNTIME, EFFORT_REGISTRY, "codex", null, { effort: "high", prompt: "p" }), [
    "codex",
    "exec",
    "-c",
    "model_reasoning_effort=high",
    "p",
  ]);
});

test("a declared argv row takes the effort flag after its argv", () => {
  assert.deepEqual(
    opinionCommand(AGENTS, RUNTIME, EFFORT_REGISTRY, "mine", null, { model: "m1", effort: "max", prompt: "p" }),
    ["mine", "-m", "m1", "--think", "max", "p"],
  );
});

test("no effort leaves the command as it was", () => {
  assert.deepEqual(opinionCommand(AGENTS, RUNTIME, EFFORT_REGISTRY, "claude", null, { model: "opus", prompt: "p" }), [
    "claude",
    "-p",
    "--output-format",
    "text",
    "--model",
    "opus",
    "p",
  ]);
});

test("a command refuses an effort the row does not take", () => {
  assert.throws(
    () => opinionCommand(AGENTS, RUNTIME, EFFORT_REGISTRY, "qwen", null, { model: "q", effort: "high", prompt: "p" }),
    EffortError,
  );
});

test("an alias is a model whatever effort follows it", () => {
  assert.equal(isModelAlias(AGENTS, EFFORT_REGISTRY, "codex", "sol", null), true);
  const registry = { providers: { codex: { aliases: true, models: ["luna", "sol@high"] } } };
  assert.equal(isModelAlias(AGENTS, registry, "codex", "sol", null), true);
  assert.equal(isModelAlias(AGENTS, registry, "codex", "sol@high", null), false);
});

test("the walk carries the effort of a ladder entry into its target", () => {
  const registry = effortDeclared(["claude:opus@high", "mine", "qwen"]);
  const session = new SecondOpinionSession("qwen", "qwen", "q");
  assert.deepEqual(opinionChain(AGENTS, RUNTIME, registry, session, null), [
    new SecondOpinionTarget("claude", "opus", "claude", "high"),
    new SecondOpinionTarget("mine", "m1", "llama", "max"),
  ]);
});

test("the same model at another effort is still the same model", () => {
  const rows = {
    alpha: { argv: ["/bin/sh", "{model}"], family: "qwen", models: [], efforts: EFFORT_ROW },
    beta: { argv: ["/bin/sh", "{model}"], family: "llama", models: [], efforts: EFFORT_ROW },
  };
  const registry = {
    providers: rows,
    second_opinion_policy: { ladder: ["alpha:m@low", "beta:m@high"], model_rule: "max" },
  };
  const session = new SecondOpinionSession("gamma", "gpt", "z");
  assert.deepEqual(
    opinionChain(AGENTS, RUNTIME, registry, session, null).map((target) => [
      target.provider,
      target.model,
      target.effort,
    ]),
    [["alpha", "m", "low"]],
  );
  assert.deepEqual(opinionSkips(AGENTS, RUNTIME, registry, session, null), [["beta", "same model as alpha"]]);
});

test("a ladder entry with a bad effort is refused even on the sessions own carrier", () => {
  const registry = effortDeclared(["qwen:q@high"]);
  assert.throws(
    () => opinionChain(AGENTS, RUNTIME, registry, new SecondOpinionSession("qwen", "qwen", "q"), null),
    EffortError,
  );
});

test("the last resort compares the model of an entry not its effort", () => {
  const target = opinionLastResort(AGENTS, EFFORT_REGISTRY, new SecondOpinionSession("claude", "claude", "opus"), null);
  assert.deepEqual([target.model, target.effort], ["sonnet", null]);
});

test("a default ladder entry may carry an effort", () => {
  const registry = effortDeclared(["codex:default@high"]);
  const chain = opinionChain(AGENTS, RUNTIME, registry, new SecondOpinionSession("claude", "claude", "x"), null);
  assert.deepEqual(chain, [new SecondOpinionTarget("codex", null, "gpt", "high")]);
  assert.equal(ladderPinsDefault(AGENTS, registry, "codex"), true);
});

test("the shipped codex effort flag keeps its quotes inside one argv element", () => {
  const command = opinionCommand(AGENTS, RUNTIME, SHIPPED, "codex", null, {
    model: "gpt-6.1-sol",
    effort: "high",
    prompt: "p",
  });
  assert.deepEqual(command, ["codex", "exec", "--model", "gpt-6.1-sol", "-c", 'model_reasoning_effort="high"', "p"]);
});

test("the shipped effort rows are the measured ones", () => {
  const rows = SHIPPED.providers;
  assert.deepEqual(rows.claude.efforts, {
    flag: "--effort {effort}",
    levels: ["low", "medium", "high", "xhigh", "max"],
  });
  assert.deepEqual(rows.codex.efforts.levels, ["low", "medium", "high", "xhigh", "max"]);
  assert.deepEqual(rows.pi.efforts, {
    flag: "--thinking {effort}",
    levels: ["off", "minimal", "low", "medium", "high", "xhigh", "max"],
  });
  assert.equal(Object.hasOwn(rows.opencode, "efforts"), false);
  assert.equal(Object.hasOwn(rows.qwen, "efforts"), false);
});

test("a shipped carrier refuses a level it does not list", () => {
  assert.throws(() => opinionCommand(AGENTS, RUNTIME, SHIPPED, "codex", null, { effort: "ultra", prompt: "p" }), {
    name: "EffortError",
    message: /its levels are: low, medium, high, xhigh, max/,
  });
  assert.throws(() => opinionCommand(AGENTS, RUNTIME, SHIPPED, "opencode", null, { effort: "high", prompt: "p" }), {
    name: "EffortError",
    message: /declares no `efforts`/,
  });
});
