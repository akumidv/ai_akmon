// The `exports` map resolves (ADR-0020/D06): each tool module imports by its package specifier
// (`akmon/tools/<path>`, through the package's self-reference) and is the very module `akmon tool`
// runs, with its `main`; the rest of `js/` is not importable by specifier.
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { posix } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const TREE = posix.resolve(posix.dirname(fileURLToPath(import.meta.url)), "..", "..");
const manifest = JSON.parse(fs.readFileSync(posix.join(TREE, "package.json"), "utf8"));

test("every exported tool imports by its specifier as the same module, with a main", async () => {
  const tools = Object.keys(manifest.exports).filter((key) => key.startsWith("./tools/"));
  assert.ok(tools.length > 0);
  for (const key of tools) {
    const bySpecifier = await import(`akmon/${key.slice(2)}`);
    const byPath = await import(pathToFileURL(posix.join(TREE, manifest.exports[key])).href);
    assert.equal(bySpecifier, byPath, key);
    assert.equal(typeof bySpecifier.main, "function", key);
  }
});

test("modules outside the map are not importable by specifier", async () => {
  for (const specifier of ["akmon", "akmon/tools/model_routing/routing", "akmon/js/hooks/hook_core.mjs"]) {
    await assert.rejects(import(specifier), { code: /ERR_PACKAGE_PATH_NOT_EXPORTED|ERR_MODULE_NOT_FOUND/ }, specifier);
  }
});

test("tools/README.md documents every exported module and exactly its exports", async () => {
  const readme = fs.readFileSync(posix.join(TREE, "tools", "README.md"), "utf8");
  /** @type {Record<string, string[]>} */
  const documented = {};
  for (const match of readme.matchAll(/^\| `(akmon\/tools\/[a-z_/]+)` \| (.+) \|$/gm)) {
    documented[match[1]] = match[2] === "—" ? [] : [...match[2].matchAll(/`([A-Za-z]+)`/g)].map((m) => m[1]);
  }
  /** @type {Record<string, string[]>} */
  const actual = {};
  for (const key of Object.keys(manifest.exports).filter((k) => k.startsWith("./tools/"))) {
    const module = await import(`akmon/${key.slice(2)}`);
    actual[`akmon/${key.slice(2)}`] = Object.keys(module).filter((name) => name !== "main");
  }
  assert.deepEqual(
    Object.fromEntries(Object.entries(documented).map(([k, v]) => [k, [...v].sort()])),
    Object.fromEntries(Object.entries(actual).map(([k, v]) => [k, [...v].sort()])),
  );
});
