/**
 * node:test for `js/common/project_root.mjs` — the twin's walk, the markers it accepts and
 * the fallback notice. The corpus carries the shared scenarios; these pin the twin against
 * the Python behavior on the host.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import { posix } from "node:path";

import {
  AITNA_ROOT_DEFAULT,
  aitnaRoot,
  aitnaRootName,
  akmonMount,
  ERGON_DIR_NAME,
  ergonRoot,
  findProjectRoot,
  gitCommonRoot,
  isProjectRoot,
  legacyLocalRoot,
  LOCAL_DIR_NAME,
  localRoot,
  locateProjectRoot,
  resolveProjectRoot,
  validatedDevRootName,
} from "./project_root.mjs";

function tmpdir() {
  // The twin dereferences symlinks, so the paths the assertions compare against must be the
  // physical ones: a temp root reached through a link (macOS `/var` → `/private/var`) would
  // never equal what `findProjectRoot` answers.
  return fs.realpathSync(fs.mkdtempSync(posix.join(os.tmpdir(), "akmon-project-root-")));
}

/**
 * Whether git can be run here.
 * @returns {boolean}
 */
function gitAvailable() {
  try {
    execFileSync("git", ["--version"], { stdio: "ignore" });
    return true;
  } catch {
    return false;
  }
}

/**
 * @param {string} cwd
 * @param {string[]} args
 */
function git(cwd, args) {
  execFileSync("git", args, { cwd, stdio: "ignore" });
}

test("outside a repository the main checkout is the project root itself, and no root answers none", () => {
  assert.equal(gitCommonRoot(null), null);
  const root = tmpdir();
  try {
    assert.equal(gitCommonRoot(root), root);
    assert.equal(ergonRoot(root), `${root}/_aitna/.ergon`);
    // a directory that is not there is no repository either
    assert.equal(gitCommonRoot(`${root}/missing`), `${root}/missing`);
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});

test("a linked worktree resolves its kits to the main checkout (ADR 0028 D11)", { skip: !gitAvailable() }, () => {
  const main = tmpdir();
  try {
    fs.writeFileSync(posix.join(main, "AGENTS.md"), "# agents\n");
    git(main, ["init", "-q"]);
    const linked = posix.join(main, ".worktrees", "C1-demo.1");
    git(main, ["worktree", "add", "-q", "--orphan", "-b", "feat", linked]);
    assert.equal(gitCommonRoot(main), main);
    assert.equal(gitCommonRoot(linked), main);
    assert.equal(ergonRoot(main), `${main}/_aitna/.ergon`);
    assert.equal(ergonRoot(linked), `${main}/_aitna/.ergon`);
    // the dev root is the main checkout's: its declaration is the one that counts
    fs.writeFileSync(posix.join(main, ".aitna-root"), "tools/ai\n");
    assert.equal(ergonRoot(main), `${main}/tools/ai/.ergon`);
  } finally {
    fs.rmSync(main, { recursive: true, force: true });
  }
});

test(
  "a repository whose main checkout is no project keeps the root it was asked about",
  { skip: !gitAvailable() },
  () => {
    const main = tmpdir();
    try {
      git(main, ["init", "-q"]);
      const nested = posix.join(main, "pkg");
      fs.mkdirSync(nested);
      fs.writeFileSync(posix.join(nested, "AGENTS.md"), "# agents\n");
      // the repository root has no AGENTS.md and no .aitna-root: it is not a project root, so the answer stays put
      assert.equal(gitCommonRoot(nested), nested);
      assert.equal(ergonRoot(nested), `${nested}/_aitna/.ergon`);
    } finally {
      fs.rmSync(main, { recursive: true, force: true });
    }
  },
);

test("a project in a repository subfolder keeps its own dev root", { skip: !gitAvailable() }, () => {
  const top = tmpdir();
  try {
    const proj = posix.join(top, "proj");
    fs.mkdirSync(proj);
    fs.writeFileSync(posix.join(top, "AGENTS.md"), "# agents\n");
    fs.writeFileSync(posix.join(proj, "AGENTS.md"), "# agents\n");
    fs.writeFileSync(posix.join(proj, ".aitna-root"), "_aitna\n");
    git(top, ["init", "-q"]);
    assert.equal(gitCommonRoot(proj), proj);
    assert.equal(ergonRoot(proj), `${proj}/_aitna/.ergon`);
    assert.equal(ergonRoot(top), `${top}/_aitna/.ergon`);
  } finally {
    fs.rmSync(top, { recursive: true, force: true });
  }
});

test("a linked worktree of a subfolder project uses the main checkout's subfolder", { skip: !gitAvailable() }, () => {
  const main = tmpdir();
  const linked = tmpdir();
  try {
    const proj = posix.join(main, "proj");
    fs.mkdirSync(proj);
    fs.writeFileSync(posix.join(proj, "AGENTS.md"), "# agents\n");
    git(main, ["init", "-q"]);
    git(main, ["add", "proj/AGENTS.md"]);
    git(main, ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "init"]);
    fs.rmSync(linked, { recursive: true });
    git(main, ["worktree", "add", "-q", "-b", "job-1", linked]);
    assert.equal(gitCommonRoot(posix.join(linked, "proj")), proj);
    assert.equal(ergonRoot(posix.join(linked, "proj")), `${proj}/_aitna/.ergon`);
  } finally {
    fs.rmSync(main, { recursive: true, force: true });
    fs.rmSync(linked, { recursive: true, force: true });
  }
});

test("the answer for a root is kept: a repository's common directory does not move", { skip: !gitAvailable() }, () => {
  const main = tmpdir();
  try {
    fs.writeFileSync(posix.join(main, "AGENTS.md"), "# agents\n");
    git(main, ["init", "-q"]);
    const linked = posix.join(main, ".worktrees", "C1-demo.1");
    git(main, ["worktree", "add", "-q", "--orphan", "-b", "feat", linked]);
    assert.equal(gitCommonRoot(linked), main);
    // without the link file git would answer the worktree itself; the kept answer is still the main checkout
    fs.rmSync(posix.join(linked, ".git"));
    assert.equal(gitCommonRoot(linked), main);
  } finally {
    fs.rmSync(main, { recursive: true, force: true });
  }
});

test("the default dev-layer name is _aitna, and none found answers it too", () => {
  assert.equal(aitnaRootName(null), AITNA_ROOT_DEFAULT);
  assert.equal(aitnaRootName(null), "_aitna");
  assert.equal(aitnaRoot(null), "_aitna");
  assert.equal(akmonMount(null), "_aitna/akmon");
  const root = tmpdir();
  assert.equal(aitnaRootName(root), "_aitna");
  assert.equal(aitnaRoot(root), `${root}/_aitna`);
  assert.equal(akmonMount(root), `${root}/_aitna/akmon`);
  fs.rmSync(root, { recursive: true, force: true });
});

test("the dotted layer folders sit under the dev root, and none found answers the default-name path (ADR 0028 D01)", () => {
  assert.equal(LOCAL_DIR_NAME, ".local");
  assert.equal(ERGON_DIR_NAME, ".ergon");
  assert.equal(localRoot(null), "_aitna/.local");
  assert.equal(ergonRoot(null), "_aitna/.ergon");
  assert.equal(legacyLocalRoot(null), "_aitna/local");
  const root = tmpdir();
  try {
    assert.equal(localRoot(root), `${root}/_aitna/.local`);
    assert.equal(ergonRoot(root), `${root}/_aitna/.ergon`);
    assert.equal(legacyLocalRoot(root), `${root}/_aitna/local`);
    fs.writeFileSync(posix.join(root, ".aitna-root"), "tools/ai\n");
    assert.equal(localRoot(root), `${root}/tools/ai/.local`);
    assert.equal(ergonRoot(root), `${root}/tools/ai/.ergon`);
    assert.equal(legacyLocalRoot(root), `${root}/tools/ai/local`);
    // computed, never a claim that the folder exists
    assert.equal(fs.existsSync(localRoot(root)), false);
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});

test(".aitna-root relocates the dev layer; slashes strip; a refused value raises", () => {
  const root = tmpdir();
  try {
    fs.writeFileSync(posix.join(root, ".aitna-root"), "tools/ai\n");
    assert.equal(aitnaRootName(root), "tools/ai");
    assert.equal(aitnaRoot(root), `${root}/tools/ai`);
    assert.equal(akmonMount(root), `${root}/tools/ai/akmon`);
    fs.writeFileSync(posix.join(root, ".aitna-root"), "tools/ai/\n");
    assert.equal(aitnaRootName(root), "tools/ai");
    for (const refused of ["", "/", "/tools/ai", "../dev", "a\nb"]) {
      fs.writeFileSync(posix.join(root, ".aitna-root"), refused);
      assert.throws(() => aitnaRootName(root), { name: "ValueError" }, JSON.stringify(refused));
    }
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});

test("a mounted tree beside AGENTS.md is a project root", () => {
  const root = tmpdir();
  fs.writeFileSync(posix.join(root, "AGENTS.md"), "# A\n");
  fs.mkdirSync(posix.join(root, "_aitna", "akmon"), { recursive: true });
  assert.equal(isProjectRoot(root), true);
  fs.rmSync(root, { recursive: true, force: true });
});

test("the dev-layer paths keep a `..` as Path does: it is the filesystem's to resolve, not a lexical join's", () => {
  assert.equal(aitnaRoot("a/../b"), "a/../b/_aitna");
  assert.equal(akmonMount("a/../b"), "a/../b/_aitna/akmon");
  // The empty root is the cwd: an empty path reads `.aitna-root` beside the process, so the
  // answer is pinned from a directory that carries none.
  const bare = tmpdir();
  const saved = process.cwd();
  try {
    process.chdir(bare);
    assert.equal(aitnaRoot(""), "_aitna");
  } finally {
    process.chdir(saved);
    fs.rmSync(bare, { recursive: true, force: true });
  }
  assert.equal(aitnaRoot("/p//q/"), "/p/q/_aitna");
  assert.equal(aitnaRoot("//p"), "//p/_aitna");
  assert.equal(aitnaRoot("///p"), "/p/_aitna");
  // `missing/..` cannot be walked through: Python's `Path.is_file` says no, a lexical join said yes
  const root = tmpdir();
  fs.writeFileSync(posix.join(root, "AGENTS.md"), "# A\n");
  fs.mkdirSync(posix.join(root, "_aitna", "akmon"), { recursive: true });
  assert.equal(isProjectRoot(root), true);
  assert.equal(isProjectRoot(`${root}/missing/..`), false);
  assert.equal(isProjectRoot(`${root}/_aitna/..`), true);
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

test("a declaration file beside AGENTS.md is a project root, and the walk reads no content", () => {
  const root = tmpdir();
  fs.writeFileSync(posix.join(root, "AGENTS.md"), "# A\n");
  fs.writeFileSync(posix.join(root, ".aitna-root"), "meta\n");
  assert.equal(isProjectRoot(root), true);
  // `.aitna-root` without AGENTS.md is no root
  fs.rmSync(posix.join(root, "AGENTS.md"));
  assert.equal(isProjectRoot(root), false);
  fs.rmSync(root, { recursive: true, force: true });
});

test("locateProjectRoot answers null where findProjectRoot guesses", () => {
  const start = tmpdir();
  assert.equal(locateProjectRoot(start), null);
  assert.equal(findProjectRoot(start), start);
  fs.writeFileSync(posix.join(start, "AGENTS.md"), "# A\n");
  fs.writeFileSync(posix.join(start, ".aitna-root"), "meta\n");
  fs.mkdirSync(posix.join(start, "a", "b"), { recursive: true });
  assert.equal(locateProjectRoot(posix.join(start, "a", "b")), start);
  fs.rmSync(start, { recursive: true, force: true });
});

test("validatedDevRootName names its source and refuses a link out of the project", () => {
  const root = tmpdir();
  const outside = tmpdir();
  assert.throws(() => validatedDevRootName("/x/", root, ".aitna-root"), {
    name: "ValueError",
    message: /^\.aitna-root must be relative to the project root and stay inside it: '\/x\/'$/,
  });
  assert.equal(validatedDevRootName(" a/b ", root), "a/b");
  assert.throws(() => validatedDevRootName("", root), { name: "ValueError", message: "--aitna-root cannot be empty" });
  assert.throws(() => validatedDevRootName("../x", root, ".aitna-root"), {
    name: "ValueError",
    message: /^\.aitna-root must be relative to the project root and stay inside it: '\.\.\/x'$/,
  });
  fs.symlinkSync(outside, posix.join(root, "escape"));
  assert.throws(() => validatedDevRootName("escape", root), {
    name: "ValueError",
    message: /^--aitna-root resolves outside the project root: /,
  });
  fs.rmSync(root, { recursive: true, force: true });
  fs.rmSync(outside, { recursive: true, force: true });
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
  assert.ok(notice.includes("expected AGENTS.md beside .aitna-root, _aitna/akmon or _aitna/.akmon.toml"));
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

test("a dangling link resolves to its target, as Path.resolve() follows it (C115)", () => {
  const base = tmpdir();
  const tree = posix.join(base, "tree");
  fs.mkdirSync(tree);
  fs.mkdirSync(posix.join(base, "realdir"));
  fs.symlinkSync("nonexistent", posix.join(tree, "dangling"));
  fs.symlinkSync("dangling", posix.join(tree, "chain"));
  fs.symlinkSync(posix.join(base, "abs", "missing"), posix.join(tree, "absolute"));
  fs.symlinkSync("../realdir", posix.join(tree, "linkdir"));
  fs.symlinkSync("linkdir/missing", posix.join(tree, "via"));
  fs.symlinkSync("linkdir/../up", posix.join(tree, "dotdot"));
  try {
    for (const [shape, answer] of [
      ["tree/dangling", "tree/nonexistent"],
      ["tree/dangling/", "tree/nonexistent"],
      ["tree/chain/x", "tree/nonexistent/x"],
      ["tree/absolute/y", "abs/missing/y"],
      ["tree/via", "realdir/missing"],
      ["tree/dotdot", "up"],
      ["tree/dangling/..", "tree"],
    ]) {
      assert.equal(resolveProjectRoot(`${base}/${shape}`, null).root, posix.join(base, answer), shape);
    }
  } finally {
    fs.rmSync(base, { recursive: true, force: true });
  }
});

test("a component the kernel refuses to look up is kept as written, as Python 3.12's resolve() keeps it", () => {
  // Measured on Python 3.12.3: `Path(p).resolve()` takes any OSError from a component's lstat as
  // "not a link" — a name over NAME_MAX (ENAMETOOLONG) or a directory that cannot be searched
  // (EACCES) resolves to the path itself, and a `..` after it pops the component lexically.
  const base = tmpdir();
  const long = "x".repeat(300);
  try {
    assert.equal(resolveProjectRoot(`${base}/${long}`, null).root, `${base}/${long}`);
    assert.equal(resolveProjectRoot(`${base}/${long}/a/b`, null).root, `${base}/${long}/a/b`);
    assert.equal(resolveProjectRoot(`${base}/${long}/../z`, null).root, `${base}/z`);
    // The walk itself asks `is_file()`, which on the 3.12 floor (through 3.13) lets an errno
    // other than ENOENT, ENOTDIR, EBADF or ELOOP through: the over-long name raises (C115).
    assert.throws(() => findProjectRoot(`${base}/${long}`), { code: "ENAMETOOLONG" });
  } finally {
    fs.rmSync(base, { recursive: true, force: true });
  }
});

test("a directory that cannot be searched does not stop the resolution", { skip: process.getuid?.() === 0 }, () => {
  const base = tmpdir();
  fs.mkdirSync(posix.join(base, "locked", "inner"), { recursive: true });
  fs.chmodSync(posix.join(base, "locked"), 0o000);
  try {
    assert.equal(resolveProjectRoot(`${base}/locked/inner/x`, null).root, `${base}/locked/inner/x`);
    assert.equal(resolveProjectRoot(`${base}/locked/inner/../y`, null).root, `${base}/locked/y`);
  } finally {
    fs.chmodSync(posix.join(base, "locked"), 0o755);
    fs.rmSync(base, { recursive: true, force: true });
  }
});

test(
  "a candidate that cannot be searched raises, as Path.is_file() does (C115)",
  { skip: process.getuid?.() === 0 },
  () => {
    const base = tmpdir();
    const locked = posix.join(base, "locked");
    fs.mkdirSync(locked);
    fs.chmodSync(locked, 0o000);
    try {
      assert.throws(() => isProjectRoot(locked), { code: "EACCES" });
    } finally {
      fs.chmodSync(locked, 0o755);
      fs.rmSync(base, { recursive: true, force: true });
    }
  },
);

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

test("an over-long start is refused before it is resolved, in one line (C121)", () => {
  // Fuzz seed 1, case 634: 32,769 `a/` components kept the walk busy for close to a minute.
  const start = `/${"a/".repeat(32_769)}`;
  const began = performance.now();
  for (const call of [() => findProjectRoot(start), () => resolveProjectRoot(null, start)]) {
    assert.throws(call, (/** @type {Error} */ error) => {
      assert.equal(error.name, "ValueError");
      assert.match(error.message, /^project-root start path is 65538 bytes, over the 4096-byte bound: \/a\/a\//);
      assert.ok(error.message.endsWith("..."));
      assert.ok(!error.message.includes("\n"));
      return true;
    });
  }
  assert.ok(performance.now() - began < 1000);
});

test("the bound counts UTF-8 bytes of the Path spelling and is inclusive", () => {
  const base = tmpdir();
  try {
    const filler = 4096 - Buffer.byteLength(base) - 1;
    const atBound = `${base}/${"é".repeat(Math.floor(filler / 2))}${"x".repeat(filler % 2)}`;
    assert.equal(Buffer.byteLength(atBound), 4096);
    // At the bound the walk runs into the kernel's own limit — the OSError is_file() raises.
    assert.throws(() => findProjectRoot(atBound), { code: "ENAMETOOLONG" });
    // A trailing slash is not counted: `Path` drops it before the length is taken.
    assert.throws(() => findProjectRoot(`${atBound}/`), { code: "ENAMETOOLONG" });
    assert.throws(() => findProjectRoot(`${atBound}x`), { name: "ValueError", message: /4097 bytes/ });
  } finally {
    fs.rmSync(base, { recursive: true, force: true });
  }
});

test("a deep start under the bound walks in linear time", () => {
  const base = tmpdir();
  try {
    let deep = base;
    for (let level = 0; level < 600; level += 1) {
      deep += "/a";
      fs.mkdirSync(deep);
    }
    const began = performance.now();
    assert.equal(findProjectRoot(deep), deep);
    assert.ok(performance.now() - began < 5000);
  } finally {
    fs.rmSync(base, { recursive: true, force: true });
  }
});
