/**
 * node:test for `js/tools/model_routing/models.mjs` — the alias-refresh tool (ADR 0024/D16), the
 * twin of `meta/tests/test_models.py`. The tool reads a provider's declared catalog only when it is
 * run and writes the generated `<aitna_root>/.local/model-aliases.json`. Every test points `HOME` at
 * a scratch directory, so the real `~/.codex` is never read.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { embeddedTreeRoot } from "../../akmon/_tree.mjs";
import { read } from "../../common/jsondata.mjs";
import { main } from "./models.mjs";
import { ProviderAliases, localAliasesPath, modelAliasesDocument } from "./routing.mjs";

const AGENTS = /** @type {any} */ (read(path.join(embeddedTreeRoot(), "tools", "model_routing", "agents.json")));

/** @type {Array<[string, string, number]>} */
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

const CODEX_ROW = {
  operation: "review",
  model_flag: "--model {model}",
  family: "gpt",
  models: ["luna", "terra", "sol"],
  aliases: true,
  catalog: { file: "~/.codex/models_cache.json", format: "codex-models-cache" },
};
const CLAUDE_ROW = { operation: "review", model_flag: "--model {model}", family: "claude", models: ["opus"] };
const REGISTRY = {
  providers: { codex: CODEX_ROW, claude: CLAUDE_ROW },
  second_opinion_policy: { ladder: ["codex"], model_rule: "max" },
};

const SOURCE = "~/.codex/models_cache.json (codex-models-cache)";
const FILE = "_aitna/.local/model-aliases.json";

/**
 * A scratch directory holding the project (`proj`) and the stand-in home (`home`).
 * @param {object} [registry]
 * @returns {{base: string, root: string}}
 */
function scratch(registry = REGISTRY) {
  const base = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), "models-test-")));
  const root = path.join(base, "proj");
  const routing = path.join(root, "_aitna", "akmon", "tools", "model_routing");
  fs.mkdirSync(routing, { recursive: true });
  fs.writeFileSync(path.join(root, "AGENTS.md"), "# project\n");
  fs.writeFileSync(path.join(routing, "registry.json"), JSON.stringify(registry));
  return { base, root };
}

/**
 * Write the host's catalog under `base`'s stand-in home.
 * @param {string} base
 * @param {{slugs?: Array<[string, string, number]>, text?: string}} [options]
 */
function catalog(base, { slugs = HOST_SLUGS, text } = {}) {
  const file = path.join(base, "home", ".codex", "models_cache.json");
  fs.mkdirSync(path.dirname(file), { recursive: true });
  const body = {
    client_version: "0.164.0",
    models: slugs.map(([slug, visibility, priority]) => ({ slug, visibility, priority })),
  };
  fs.writeFileSync(file, text === undefined ? JSON.stringify(body) : text);
}

/**
 * Run `main` against the scratch project with `HOME` pointed at its stand-in home and the process streams captured.
 * @param {string} base
 * @param {...string} argv
 * @returns {{code: number, stdout: string, stderr: string}}
 */
function run(base, ...argv) {
  let stdout = "";
  let stderr = "";
  const out = process.stdout.write;
  const err = process.stderr.write;
  const home = process.env.HOME;
  process.env.HOME = path.join(base, "home");
  process.stdout.write = /** @type {any} */ (
    (/** @type {string} */ text) =>
      ((stdout += text), true)
  );
  process.stderr.write = /** @type {any} */ (
    (/** @type {string} */ text) =>
      ((stderr += text), true)
  );
  try {
    return { code: main(["--project-root", path.join(base, "proj"), ...argv]), stdout, stderr };
  } finally {
    process.stdout.write = out;
    process.stderr.write = err;
    process.env.HOME = home;
  }
}

/**
 * The generated aliases file, parsed.
 * @param {string} root
 * @returns {any}
 */
function storedFile(root) {
  return JSON.parse(fs.readFileSync(localAliasesPath(AGENTS, root), "utf-8"));
}

test("a refresh writes the file with the highest version of each alias", () => {
  const { base, root } = scratch();
  catalog(base);
  const result = run(base, "--refresh");
  assert.equal(result.code, 0);
  assert.deepEqual(storedFile(root), {
    codex: {
      source: SOURCE,
      client: "0.164.0",
      aliases: { luna: "gpt-6-luna", terra: "gpt-6.1-terra", sol: "gpt-6.1-sol" },
    },
  });
  assert.equal(
    result.stdout,
    `catalog codex: source=${SOURCE} client=0.164.0\n` +
      "  luna → gpt-6-luna\n  terra → gpt-6.1-terra\n  sol → gpt-6.1-sol\n" +
      `wrote ${FILE}\n`,
  );
});

/**
 * Run `main` from a directory inside no project, with no `--project-root`, `HOME` at `base`'s stand-in home.
 * @param {string} base
 * @param {string} cwd
 * @param {...string} argv
 * @returns {{code: number, stdout: string, stderr: string}}
 */
function runLone(base, cwd, ...argv) {
  let stdout = "";
  let stderr = "";
  const out = process.stdout.write;
  const err = process.stderr.write;
  const home = process.env.HOME;
  const saved = process.cwd();
  process.env.HOME = path.join(base, "home");
  process.chdir(cwd);
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
    process.env.HOME = home;
    process.chdir(saved);
  }
}

test("a refresh follows the dev root the project declares", () => {
  const { base, root } = scratch();
  catalog(base);
  fs.writeFileSync(path.join(root, ".aitna-root"), "meta\n");
  const result = run(base, "--refresh");
  assert.equal(result.code, 0, result.stderr);
  assert.ok(fs.existsSync(path.join(root, "meta", ".local", "model-aliases.json")));
  assert.equal(fs.existsSync(path.join(root, "_aitna", ".local")), false);
});

test("--refresh with no project root prints the notice, exits 2 and writes nothing; a preview still runs", () => {
  const { base } = scratch();
  catalog(base);
  const lone = path.join(base, "lone");
  fs.mkdirSync(lone);
  const refused = runLone(base, lone, "--refresh");
  assert.equal(refused.code, 2);
  assert.equal(refused.stdout, "");
  assert.match(refused.stderr, /^\[akmon\] no project root at or above /);
  assert.ok(refused.stderr.includes("pass --project-root to name the root instead"));
  assert.deepEqual(fs.readdirSync(lone), []);
  // a preview and a listing write nothing, so the notice does not stop them
  const preview = runLone(base, lone, "--refresh", "--dry-run");
  assert.match(preview.stderr, /^\[akmon\] no project root at or above /);
  assert.notEqual(preview.stdout, "");
  assert.deepEqual(fs.readdirSync(lone), []);
});

test("a second refresh is idempotent and says unchanged", () => {
  const { base, root } = scratch();
  catalog(base);
  assert.equal(run(base, "--refresh").code, 0);
  const file = localAliasesPath(AGENTS, root);
  const first = fs.readFileSync(file);
  const mtime = fs.statSync(file, { bigint: true }).mtimeNs;
  const again = run(base, "--refresh");
  assert.equal(again.code, 0);
  assert.deepEqual(fs.readFileSync(file), first);
  assert.equal(fs.statSync(file, { bigint: true }).mtimeNs, mtime);
  assert.ok(again.stdout.endsWith(`${FILE} unchanged\n`));
});

test("--refresh --dry-run writes nothing and says what it would write", () => {
  const { base, root } = scratch();
  catalog(base);
  const result = run(base, "--refresh", "--dry-run");
  assert.equal(result.code, 0);
  assert.equal(fs.existsSync(localAliasesPath(AGENTS, root)), false);
  assert.ok(result.stdout.endsWith(`would write ${FILE}\n`));
});

test("the listing shows what is stored and what a refresh would write, without writing", () => {
  const { base } = scratch();
  catalog(base);
  const before = run(base);
  assert.equal(before.code, 0);
  assert.equal(run(base, "--refresh").code, 0);
  const after = run(base);
  assert.equal(after.code, 0);
  assert.ok(before.stdout.startsWith("stored codex: none\ncatalog codex: source="));
  assert.ok(before.stdout.endsWith(`would write ${FILE}\n`));
  assert.ok(after.stdout.startsWith(`stored codex: source=${SOURCE} client=0.164.0\n`));
  assert.ok(after.stdout.endsWith(`would leave ${FILE} unchanged\n`));
});

test("an alias the catalog does not list is reported and left unmapped", () => {
  const { base, root } = scratch();
  catalog(base, {
    slugs: [
      ["gpt-6.1-sol", "list", 0],
      ["gpt-6-luna", "list", 5],
    ],
  });
  const result = run(base, "--refresh");
  assert.equal(result.code, 0);
  assert.deepEqual(storedFile(root).codex.aliases, { luna: "gpt-6-luna", sol: "gpt-6.1-sol" });
  assert.ok(result.stdout.includes("  terra: no match in the catalog; left unmapped\n"));
});

test("a refresh replaces a stale mapping and keeps the other providers in insertion order", () => {
  const { base, root } = scratch();
  const file = localAliasesPath(AGENTS, root);
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(
    file,
    modelAliasesDocument({
      codex: new ProviderAliases("old", "0.1", { sol: "gpt-5-sol" }),
      other: new ProviderAliases("s", null, { a: "b" }),
    }),
  );
  catalog(base);
  assert.equal(run(base, "--refresh", "--provider", "codex").code, 0);
  const stored = storedFile(root);
  assert.deepEqual(Object.keys(stored), ["codex", "other"]);
  assert.equal(stored.codex.aliases.sol, "gpt-6.1-sol");
  assert.deepEqual(stored.other, { source: "s", client: null, aliases: { a: "b" } });
});

test("a refresh replaces a generated file that is not valid", () => {
  const { base, root } = scratch();
  const file = localAliasesPath(AGENTS, root);
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, "garbage");
  catalog(base);
  assert.equal(run(base, "--refresh").code, 0);
  assert.ok("sol" in storedFile(root).codex.aliases);
});

test("a catalog without a client version stores null", () => {
  const { base, root } = scratch();
  catalog(base, { text: JSON.stringify({ models: [{ slug: "gpt-6-sol", visibility: "list", priority: 1 }] }) });
  assert.equal(run(base, "--refresh").code, 0);
  assert.equal(storedFile(root).codex.client, null);
});

test("a refusal is one line naming the provider, exit 2, nothing on stdout", () => {
  /** @type {Array<[string[], string]>} */
  const cases = [
    [
      ["--refresh", "--provider", "nope"],
      "models: --provider names 'nope', which the providers table does not declare",
    ],
    [
      ["--refresh", "--provider", "claude"],
      "models: providers.claude declares no `catalog`; there is nothing to refresh its model aliases from",
    ],
  ];
  for (const [argv, line] of cases) {
    const { base } = scratch();
    catalog(base);
    assert.deepEqual(run(base, ...argv), { code: 2, stdout: "", stderr: `${line}\n` });
  }
});

test("a missing catalog is refused naming the file and the row key", () => {
  const { base, root } = scratch();
  const result = run(base, "--refresh");
  assert.equal(result.code, 2);
  assert.ok(
    result.stderr.startsWith("models: ~/.codex/models_cache.json (providers.codex.catalog.file) does not exist;"),
  );
  assert.equal(result.stderr.split("\n").length, 2);
  assert.equal(fs.existsSync(localAliasesPath(AGENTS, root)), false);
});

test("an unreadable catalog is refused naming the file and the row key", () => {
  /** @type {Array<[string, string]>} */
  const cases = [
    ["not json", "is not valid JSON"],
    ["[]", "holds no `models` list"],
  ];
  for (const [text, reason] of cases) {
    const { base } = scratch();
    catalog(base, { text });
    const result = run(base, "--refresh");
    assert.equal(result.code, 2);
    assert.equal(result.stderr, `models: ~/.codex/models_cache.json (providers.codex.catalog) ${reason}\n`);
  }
});

test("no provider with a catalog is refused", () => {
  const { base } = scratch({ ...REGISTRY, providers: { claude: CLAUDE_ROW } });
  const result = run(base, "--refresh");
  assert.equal(result.code, 2);
  assert.ok(result.stderr.startsWith("models: no provider row declares a `catalog`;"));
});

test("a row with a malformed catalog is refused", () => {
  const { base } = scratch({ providers: { codex: { ...CODEX_ROW, catalog: "~/x.json" } } });
  const result = run(base, "--refresh");
  assert.equal(result.code, 2);
  assert.ok(result.stderr.startsWith("models: providers.codex.catalog must be an object"));
});

test("a models entry with an effort is the alias before the at sign, listed once", () => {
  const row = {
    ...CODEX_ROW,
    models: ["luna", "sol", "sol@high"],
    efforts: { flag: "-c e={effort}", levels: ["low", "high"] },
  };
  const { base, root } = scratch({ providers: { codex: row } });
  catalog(base);
  const result = run(base, "--refresh");
  assert.equal(result.code, 0);
  assert.deepEqual(storedFile(root).codex.aliases, { luna: "gpt-6-luna", sol: "gpt-6.1-sol" });
  assert.ok(!result.stdout.includes("unmapped"));
});
