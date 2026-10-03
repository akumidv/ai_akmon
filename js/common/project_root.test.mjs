/**
 * node:test for `js/common/project_root.mjs` — the twin's walk, the markers it accepts and
 * the fallback notice. The corpus carries the shared scenarios; these pin the twin against
 * the Python behavior on the host.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import { posix } from "node:path";

import {
  AITNA_ROOT_DEFAULT, aitnaRoot, aitnaRootName, akmonMount, findProjectRoot, isProjectRoot, resolveProjectRoot } from "./project_root.mjs";

function tmpdir() {
  // The twin dereferences symlinks, so the paths the assertions compare against must be the
  // physical ones: a temp root reached through a link (macOS `/var` → `/private/var`) would
  // never equal what `findProjectRoot` answers.
  return fs.realpathSync(fs.mkdtempSync(posix.join(os.tmpdir(), "akmon-project-root-")));
}

test("the default dev-layer name is _aitna", () => {
  const saved = process.env.AITNA_ROOT;
  delete process.env.AITNA_ROOT;
  try {
    assert.equal(aitnaRootName(), AITNA_ROOT_DEFAULT);
    assert.equal(aitnaRootName(), "_aitna");
    assert.equal(aitnaRoot("/proj"), "/proj/_aitna");
    assert.equal(akmonMount("/proj"), "/proj/_aitna/akmon");
  } finally {
    if (saved !== undefined) {
      process.env.AITNA_ROOT = saved;
    }
  }
});

test("AITNA_ROOT relocates the dev layer; slashes strip; empty falls back", () => {
  const saved = process.env.AITNA_ROOT;
  try {
    process.env.AITNA_ROOT = "tools/ai";
    assert.equal(aitnaRootName(), "tools/ai");
    process.env.AITNA_ROOT = "/tools/ai/";
    assert.equal(aitnaRootName(), "tools/ai");
    process.env.AITNA_ROOT = "";
    assert.equal(aitnaRootName(), "_aitna");
    process.env.AITNA_ROOT = "/";
    assert.equal(aitnaRootName(), "_aitna");
  } finally {
    if (saved === undefined) {
      delete process.env.AITNA_ROOT;
    } else {
      process.env.AITNA_ROOT = saved;
    }
  }
});

test("a mounted tree beside AGENTS.md is a project root", () => {
  const root = tmpdir();
  fs.writeFileSync(posix.join(root, "AGENTS.md"), "# A\n");
  fs.mkdirSync(posix.join(root, "_aitna", "akmon"), { recursive: true });
  assert.equal(isProjectRoot(root), true);
  fs.rmSync(root, { recursive: true, force: true });
});

test("an integration record beside AGENTS.md is a project root (package mode)", () => {
  const root = tmpdir();
  fs.writeFileSync(posix.join(root, "AGENTS.md"), "# A\n");
  fs.mkdirSync(posix.join(root, "_aitna"));
  fs.writeFileSync(posix.join(root, "_aitna", ".akmon.toml"), 'mount = "package"\n');
  assert.equal(isProjectRoot(root), true);
  fs.rmSync(root, { recursive: true, force: true });
});

test("AGENTS.md alone is not a project root: neither marker present", () => {
  const root = tmpdir();
  fs.writeFileSync(posix.join(root, "AGENTS.md"), "# A\n");
  assert.equal(isProjectRoot(root), false);
  fs.rmSync(root, { recursive: true, force: true });
});

test("the walk finds the root from a nested directory and stops at the nearest", () => {
  const inner = tmpdir();
  fs.writeFileSync(posix.join(inner, "AGENTS.md"), "# inner\n");
  fs.mkdirSync(posix.join(inner, "_aitna", "akmon"), { recursive: true });
  const nested = posix.join(inner, "a", "b");
  fs.mkdirSync(nested, { recursive: true });
  assert.equal(findProjectRoot(nested), inner);
  fs.rmSync(inner, { recursive: true, force: true });
});

test("a start reached through a symlink finds the dereferenced root", () => {
  // The Python twin anchors the walk with `Path.resolve()`. A Node consumer routinely starts
  // inside a linked directory (`node_modules/.bin`, a linked workspace, a mounted tree), and a
  // lexical start makes the walk answer the alias — a path no other answer will agree with.
  const base = tmpdir();
  const root = posix.join(base, "proj");
  fs.mkdirSync(posix.join(root, "_aitna", "akmon"), { recursive: true });
  fs.writeFileSync(posix.join(root, "AGENTS.md"), "# A\n");
  const alias = posix.join(base, "proj-alias");
  fs.symlinkSync(root, alias);
  assert.equal(findProjectRoot(alias), root);
  const nestedAlias = posix.join(base, "dev-layer-alias");
  fs.symlinkSync(posix.join(root, "_aitna"), nestedAlias);
  assert.equal(findProjectRoot(posix.join(nestedAlias, "akmon")), root);
  fs.rmSync(base, { recursive: true, force: true });
});

test("with nothing found the walk falls back to the start directory", () => {
  const start = tmpdir();
  assert.equal(findProjectRoot(start), start);
  fs.rmSync(start, { recursive: true, force: true });
});

test("an explicit root wins and prints no notice", () => {
  const root = tmpdir();
  const resolved = resolveProjectRoot(root);
  assert.deepEqual(resolved, { root, notice: null });
  fs.rmSync(root, { recursive: true, force: true });
});

test("a guessed root prints the notice naming the expected markers", () => {
  const start = tmpdir();
  const { root, notice } = resolveProjectRoot(null, start);
  assert.equal(root, start);
  assert.ok(notice !== null);
  assert.ok(notice.includes(`no project root at or above ${start}`));
  assert.ok(notice.includes("expected AGENTS.md beside _aitna/akmon or _aitna/.akmon.toml"));
  assert.ok(notice.includes("pass --project-root to name the root instead"));
  fs.rmSync(start, { recursive: true, force: true });
});

test("an entry point whose root is linked answers the real path, explicit or found", () => {
  const base = tmpdir();
  const root = posix.join(base, "proj");
  fs.mkdirSync(posix.join(root, "_aitna", "akmon"), { recursive: true });
  fs.writeFileSync(posix.join(root, "AGENTS.md"), "# A\n");
  fs.mkdirSync(posix.join(root, "src"));
  const alias = posix.join(base, "proj-alias");
  fs.symlinkSync(root, alias);
  assert.deepEqual(resolveProjectRoot(alias), { root, notice: null });
  assert.deepEqual(resolveProjectRoot(null, posix.join(alias, "src")), { root, notice: null });
  fs.rmSync(base, { recursive: true, force: true });
});

// `Path.resolve()` walks a path component by component: a link is expanded where it stands and a
// following `..` applies to what it expanded *into*, while a component that is not on disk is
// kept and resolved no further. Both halves matter here, and each breaks a Node shortcut on its
// own: `path.resolve` and `path.join` collapse `..` against the written path before any link is
// read, and `fs.realpathSync` refuses a path with a missing tail. The table below is the
// answer `common/project_root.py::resolve_project_root` gives for each start — measured from
// `python3` on this host (the sweep that found the JS collapse: 60 shapes x absolute/relative),
// not from this module — and every row is asked twice, once as an absolute start and once
// relative to the directory, because the two forms are where the divergence hid.
const RESOLVE_ANSWERS = [
  ["link", "target/deep"],
  ["link/", "target/deep"],
  ["link/..", "target"],
  ["link/./..", "target"],
  ["link/../sibling", "target/sibling"],
  ["link/../../target", "target"],
  ["link/missing", "target/deep/missing"],
  ["link/../missing", "target/missing"],
  ["link/missing/..", "target/deep"],
  ["link/missing/../x", "target/deep/x"],
  ["rel/deep/..", "target"],
  ["target/../target/deep", "target/deep"],
  ["a/../a", "a"],
  ["file/x/..", "file"],
  ["file/..", "."],
  ["missing/..", "."],
  ["missing/deeper/..", "missing"],
  ["link/../..", "."],
];

test("path resolution matches the twin for links, `..`, and components that are not there", () => {
  const base = tmpdir();
  fs.mkdirSync(posix.join(base, "target", "deep"), { recursive: true });
  fs.mkdirSync(posix.join(base, "target", "sibling"), { recursive: true });
  fs.mkdirSync(posix.join(base, "a"), { recursive: true });
  fs.mkdirSync(posix.join(base, "_aitna", "akmon"), { recursive: true });
  fs.writeFileSync(posix.join(base, "AGENTS.md"), "# A\n");
  fs.writeFileSync(posix.join(base, "file"), "x");
  fs.symlinkSync(posix.join(base, "target", "deep"), posix.join(base, "link"));
  fs.symlinkSync("target", posix.join(base, "rel"));
  const saved = process.cwd();
  try {
    for (const [shape, answer] of RESOLVE_ANSWERS) {
      const expected = answer === "." ? base : posix.join(base, answer);
      process.chdir(base);
      assert.equal(resolveProjectRoot(`${base}/${shape}`, null).root, expected, `absolute ${shape}`);
      process.chdir(base);
      assert.equal(resolveProjectRoot(shape, null).root, expected, `relative ${shape}`);
    }
  } finally {
    process.chdir(saved);
    fs.rmSync(base, { recursive: true, force: true });
  }
});

test("a symlink loop raises naming the loop, as the stdlib's RuntimeError does", () => {
  // The stdlib answers no path for a link that loops, and neither may this one: an answer built
  // on the alias would be a path no other answer agrees with. The message text is shared.
  const base = tmpdir();
  fs.symlinkSync("self", posix.join(base, "self"));
  try {
    assert.throws(() => resolveProjectRoot(posix.join(base, "self"), null), {
      message: `Symlink loop from '${posix.join(base, "self")}'`,
    });
  } finally {
    fs.rmSync(base, { recursive: true, force: true });
  }
});
