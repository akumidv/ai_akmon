/**
 * node:test for `js/bin/sync.mjs` — what only the JavaScript implementation has (the Node wiring
 * spelling, the tree spelling, the `package.json` pin reader, the refusal of any other record) and
 * the named pins of the twin: the settings round trip, the plan errors, the deletions. The pure
 * helpers both implementations share are `meta/conformance/units/sync.toml`, run through `probe.mjs`;
 * the whole command against the Python reference is the differential run of C105.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import { posix } from "node:path";
import { fileURLToPath } from "node:url";

import {
  PlannedFile,
  apply,
  checkFindings,
  claudeHooks,
  claudeSettings,
  codexHooks,
  codexHooksText,
  hasPython,
  importedStandardFiles,
  installedAkmonVersion,
  isAkmonEntry,
  languageProfiles,
  main,
  materializationRoot,
  mergeHookEntries,
  nodeHooksDir,
  packagePinStatus,
  plannedFiles,
  profileImports,
  readJson,
  readMountMode,
  readSyncData,
  skillSources,
  skillStubs,
  standardTreeRoot,
  unsupportedFound,
  unsupportedRecord,
  upsertTomlKey,
} from "./sync.mjs";

const TREE = fs.realpathSync(posix.resolve(posix.dirname(fileURLToPath(import.meta.url)), "..", ".."));
const SYNC = posix.join(TREE, "js", "bin", "sync.mjs");
const data = readSyncData();
const NODE_RECORD = 'mount = "package"\necosystem = "node"\nakmon_version = "0.0.1"\n';
const COMMON = "@_aitna/.akmon/guardrails/_common.md\n";
const MOUNTED_RECORD = 'mount = "submodule"\necosystem = "node"\nakmon_version = "0.0.1"\n';

/**
 * A scratch directory removed after `body`.
 * @param {(scratch: string) => void} body
 */
function withScratch(body) {
  const scratch = fs.realpathSync(fs.mkdtempSync(posix.join(os.tmpdir(), "akmon-sync-test-")));
  try {
    body(scratch);
  } finally {
    fs.rmSync(scratch, { recursive: true, force: true });
  }
}

/** Write `text` at `relative` under `base`, making the directories. */
function put(/** @type {string} */ base, /** @type {string} */ relative, /** @type {string | Buffer} */ text) {
  fs.mkdirSync(posix.dirname(posix.join(base, relative)), { recursive: true });
  fs.writeFileSync(posix.join(base, relative), text);
}

/** `relative` under `base`, as text. */
function get(/** @type {string} */ base, /** @type {string} */ relative) {
  return fs.readFileSync(posix.join(base, relative), "utf-8");
}

/**
 * A Node package-mode project under `scratch`: the record, an AGENTS.md importing the common
 * guardrail, and `node_modules/akmon` linked to this tree (`link: false` leaves it out).
 * @param {string} scratch
 * @param {{record?: string | null, agents?: string | null, link?: boolean}} [options]
 * @returns {string} the project root
 */
function project(scratch, { record = NODE_RECORD, agents = COMMON, link = true } = {}) {
  const root = posix.join(scratch, "project");
  fs.mkdirSync(root);
  if (record !== null) {
    put(root, "_aitna/.akmon.toml", record);
  }
  if (agents !== null) {
    put(root, "AGENTS.md", agents);
  }
  if (link) {
    fs.mkdirSync(posix.join(root, "node_modules"));
    fs.symlinkSync(TREE, posix.join(root, "node_modules", "akmon"));
  }
  return root;
}

/**
 * A Node project under `scratch` attached in a mounted mode (C129): the record, an AGENTS.md importing
 * the common guardrail from the mount, and `<AITNA_ROOT>/akmon` linked to this tree.
 * @param {string} scratch
 * @param {{record?: string}} [options]
 * @returns {string} the project root
 */
function mountedProject(scratch, { record = MOUNTED_RECORD } = {}) {
  const root = posix.join(scratch, "project");
  fs.mkdirSync(root);
  put(root, "_aitna/.akmon.toml", record);
  put(root, "AGENTS.md", "@_aitna/akmon/guardrails/_common.md\n");
  fs.symlinkSync(TREE, posix.join(root, "_aitna", "akmon"));
  return root;
}

/**
 * `body` on a fresh Node package-mode project (see {@link project}).
 * @param {(root: string) => void} body
 */
function withPackageProject(body) {
  withScratch((scratch) => body(project(scratch)));
}

/**
 * Run `body` with `AITNA_ROOT` set as given (`null`: unset), then restored.
 * @template T
 * @param {string | null} aitna
 * @param {() => T} body
 * @returns {T}
 */
function withAitnaRoot(aitna, body) {
  const saved = process.env.AITNA_ROOT;
  try {
    if (aitna === null) {
      delete process.env.AITNA_ROOT;
    } else {
      process.env.AITNA_ROOT = aitna;
    }
    return body();
  } finally {
    if (saved === undefined) {
      delete process.env.AITNA_ROOT;
    } else {
      process.env.AITNA_ROOT = saved;
    }
  }
}

/**
 * `main(argv)` with the streams captured.
 * @param {string[]} argv
 * @returns {{code: number, stdout: string, stderr: string}}
 */
function run(argv) {
  const out = process.stdout.write;
  const err = process.stderr.write;
  let stdout = "";
  let stderr = "";
  process.stdout.write = /** @type {any} */ (
    (/** @type {string} */ chunk) =>
      ((stdout += chunk), true)
  );
  process.stderr.write = /** @type {any} */ (
    (/** @type {string} */ chunk) =>
      ((stderr += chunk), true)
  );
  try {
    const code = main(argv);
    return { code, stdout, stderr };
  } finally {
    process.stdout.write = out;
    process.stderr.write = err;
  }
}

/** The names of the hook scripts in `js/hooks/` that are run as entry points. */
const HOOKS_DIR = posix.join(TREE, "js", "hooks");

// --------------------------------------------------------------------------------------
// the package.json pin
// --------------------------------------------------------------------------------------

/** @param {unknown} manifest @returns {string} */
function pinStatus(manifest) {
  let status = "";
  withScratch((scratch) => {
    put(
      scratch,
      "package.json",
      typeof manifest === "string" || Buffer.isBuffer(manifest) ? manifest : JSON.stringify(manifest),
    );
    status = packagePinStatus(scratch);
  });
  return status;
}

test("packagePinStatus: no package.json is no pin, and pyproject.toml is never read", () => {
  withScratch((scratch) => {
    assert.equal(packagePinStatus(scratch), "none");
    put(scratch, "pyproject.toml", '[dependency-groups]\ndev = ["akmon==0.4.0"]\n');
    assert.equal(packagePinStatus(scratch), "none");
  });
});

test("packagePinStatus: devDependencies is dev; the three shipped classes are runtime", () => {
  assert.equal(pinStatus({ devDependencies: { akmon: "0.4.0" } }), "dev");
  for (const table of ["dependencies", "optionalDependencies", "peerDependencies"]) {
    assert.equal(pinStatus({ [table]: { akmon: "0.4.0" } }), "runtime", table);
  }
  assert.equal(pinStatus({ name: "x", devDependencies: { eslint: "9" } }), "none");
  assert.equal(pinStatus({}), "none");
});

test("packagePinStatus: the worst declaration wins, wherever it sits in the file", () => {
  assert.equal(pinStatus({ devDependencies: { akmon: "0.4.0" }, dependencies: { akmon: "0.4.0" } }), "runtime");
  assert.equal(pinStatus({ dependencies: { akmon: "0.4.0" }, devDependencies: { akmon: "0.4.0" } }), "runtime");
  assert.equal(pinStatus({ devDependencies: { akmon: "0.4.0" }, peerDependencies: { akmon: "*" } }), "runtime");
});

test("packagePinStatus: only the key akmon names the package", () => {
  assert.equal(pinStatus({ devDependencies: { "akmon-extra": "1", "@scope/akmon": "1", Akmon: "1" } }), "none");
  assert.equal(pinStatus({ devDependencies: "akmon", dependencies: ["akmon"], peerDependencies: null }), "none");
  assert.equal(pinStatus({ scripts: { akmon: "akmon sync" }, name: "akmon" }), "none");
});

test("packagePinStatus: a manifest that is not a JSON object is unreadable, not a missing pin", () => {
  for (const text of ["{", "", "[]", '"x"', "null", "42", "{'a': 1}", '{"a": 1,}', Buffer.from([0x7b, 0xff, 0x7d])]) {
    assert.equal(pinStatus(text), "unreadable", String(text));
  }
});

test("packagePinStatus: a byte-order mark is read past, as npm reads it", () => {
  assert.equal(pinStatus('\ufeff{"devDependencies": {"akmon": "0.4.0"}}'), "dev");
});

test("installedAkmonVersion is the version of the tree's own package.json", () => {
  const manifest = JSON.parse(get(TREE, "package.json"));
  assert.equal(installedAkmonVersion(), manifest.version);
});

// --------------------------------------------------------------------------------------
// the tree and its spelling
// --------------------------------------------------------------------------------------

test("standardTreeRoot: a link to the running tree is spelled node_modules/akmon, unresolved", () => {
  withScratch((scratch) => {
    const root = project(scratch);
    assert.equal(standardTreeRoot(root), posix.join(root, "node_modules", "akmon"));
  });
});

test("standardTreeRoot: a pnpm-style link never leaks the version-carrying store path", () => {
  withScratch((scratch) => {
    const root = project(scratch, { link: false });
    const store = posix.join(root, "node_modules", ".pnpm", "akmon@0.4.0", "node_modules");
    fs.mkdirSync(store, { recursive: true });
    fs.symlinkSync(TREE, posix.join(store, "akmon"));
    fs.symlinkSync(".pnpm/akmon@0.4.0/node_modules/akmon", posix.join(root, "node_modules", "akmon"));
    assert.equal(standardTreeRoot(root), posix.join(root, "node_modules", "akmon"));
    const [sources] = skillSources(data, root);
    assert.ok(sources.length > 0);
    assert.ok(
      sources.every((source) => !source.includes(".pnpm")),
      sources.join("\n"),
    );
    for (const stub of sources.flatMap((source) => skillStubs(data, root, source))) {
      assert.ok(!stub.content.includes(".pnpm"), stub.path);
    }
  });
});

test("standardTreeRoot: without a link, or beside a copy that is another tree, it is the running tree", () => {
  withScratch((scratch) => {
    const bare = project(scratch, { link: false });
    assert.equal(standardTreeRoot(bare), TREE);
    fs.mkdirSync(posix.join(bare, "node_modules", "akmon"), { recursive: true });
    assert.equal(standardTreeRoot(bare), TREE);
  });
});

test("a standard skill points at node_modules/akmon with a relative link; outside the root it points through akmon path", () => {
  withScratch((scratch) => {
    const linked = project(scratch);
    const [sources] = skillSources(data, linked);
    const release = /** @type {string} */ (sources.find((source) => source.endsWith("/skills/release/SKILL.md")));
    for (const stub of skillStubs(data, linked, release)) {
      assert.ok(
        stub.content.includes(
          "Source skill: [../../../node_modules/akmon/skills/release/SKILL.md](../../../node_modules/akmon/skills/release/SKILL.md)",
        ),
        stub.content,
      );
      assert.ok(!stub.content.includes("akmon path"));
    }
    const elsewhere = posix.join(scratch, "other");
    fs.mkdirSync(elsewhere);
    const [outside] = skillSources(data, elsewhere);
    const stubs = skillStubs(
      data,
      elsewhere,
      /** @type {string} */ (outside.find((source) => source.endsWith("/skills/release/SKILL.md"))),
    );
    assert.deepEqual(
      stubs.map((stub) => stub.path),
      [
        posix.join(elsewhere, ".claude/skills/release/SKILL.md"),
        posix.join(elsewhere, ".agents/skills/release/SKILL.md"),
      ],
    );
    for (const stub of stubs) {
      assert.ok(stub.content.includes("Source skill: `$(akmon path)/skills/release/SKILL.md`"), stub.content);
    }
  });
});

test("a project's own skill is a relative link whatever the tree", () => {
  withScratch((scratch) => {
    const root = project(scratch, { link: false });
    put(root, "skills/mine/SKILL.md", "---\nname: mine\n---\n# mine\n");
    const [sources] = skillSources(data, root);
    const stubs = skillStubs(data, root, posix.join(root, "skills/mine/SKILL.md"));
    assert.ok(sources.includes(posix.join(root, "skills/mine/SKILL.md")));
    assert.ok(
      stubs[0].content.includes("Source skill: [../../../skills/mine/SKILL.md](../../../skills/mine/SKILL.md)"),
    );
  });
});

// --------------------------------------------------------------------------------------
// the wiring
// --------------------------------------------------------------------------------------

test("Claude wiring: every command is node on the hook's own file under node_modules/akmon", () => {
  /** @type {string[]} */
  const commands = [];
  withPackageProject((root) => {
    for (const [event, entries] of claudeHooks(data, root).get("hooks")) {
      assert.ok(["PreToolUse", "SessionStart", "UserPromptSubmit", "Stop"].includes(event));
      for (const entry of entries) {
        for (const hook of entry.get("hooks")) {
          commands.push(hook.get("command"));
          assert.equal(hook.get("type"), "command");
        }
      }
    }
  });
  assert.ok(commands.length >= 8);
  for (const command of commands) {
    const match = /^node "\$CLAUDE_PROJECT_DIR\/node_modules\/akmon\/js\/hooks\/([a-z-]+)\.mjs"$/.exec(command);
    assert.ok(match, command);
    assert.ok(fs.existsSync(posix.join(HOOKS_DIR, `${match[1]}.mjs`)), `no hook file for ${command}`);
  }
});

test("Claude wiring keeps the table's shape: a matcher-less entry has no matcher key", () => {
  withPackageProject((root) => {
    const session = claudeHooks(data, root).get("hooks").get("SessionStart");
    assert.deepEqual([...session[0].keys()], ["hooks"]);
    const pre = claudeHooks(data, root).get("hooks").get("PreToolUse");
    assert.deepEqual([...pre[0].keys()], ["matcher", "hooks"]);
    assert.equal(pre[0].get("matcher"), "Bash");
  });
});

test("Codex wiring: node on codex-hook.mjs from the git toplevel, the advisory appended, a status message", () => {
  /** @type {string[]} */
  const seen = [];
  withPackageProject((root) => {
    for (const entries of codexHooks(data, root).get("hooks").values()) {
      for (const entry of entries) {
        for (const hook of entry.get("hooks")) {
          seen.push(hook.get("command"));
          assert.deepEqual([...hook.keys()], ["type", "command", "statusMessage"]);
          assert.ok(typeof hook.get("statusMessage") === "string");
        }
      }
    }
  });
  assert.deepEqual(seen, [
    'node "$(git rev-parse --show-toplevel)/node_modules/akmon/js/hooks/codex-hook.mjs" role-on-code',
    'node "$(git rev-parse --show-toplevel)/node_modules/akmon/js/hooks/codex-hook.mjs" analysis-guard',
    'node "$(git rev-parse --show-toplevel)/node_modules/akmon/js/hooks/codex-hook.mjs" session-start',
  ]);
});

test("every command the wiring writes is one sync recognises as its own, package or mounted", () => {
  for (const build of [project, mountedProject]) {
    withScratch((scratch) => {
      const root = build(scratch);
      for (const wiring of [claudeHooks(data, root), codexHooks(data, root)]) {
        for (const entries of wiring.get("hooks").values()) {
          for (const entry of entries) {
            assert.ok(isAkmonEntry(data, entry), JSON.stringify([...entry]));
          }
        }
      }
    });
  }
});

test("a mounted record's wiring runs node on the mount's hooks, one template for both modes (C129)", () => {
  withScratch((scratch) => {
    const root = mountedProject(scratch);
    assert.equal(nodeHooksDir(root), "_aitna/akmon/js/hooks");
    const pre = claudeHooks(data, root).get("hooks").get("PreToolUse");
    assert.equal(
      pre[0].get("hooks")[0].get("command"),
      'node "$CLAUDE_PROJECT_DIR/_aitna/akmon/js/hooks/git-commit-guard.mjs"',
    );
    const codex = codexHooks(data, root).get("hooks").get("PreToolUse");
    assert.equal(
      codex[0].get("hooks")[0].get("command"),
      'node "$(git rev-parse --show-toplevel)/_aitna/akmon/js/hooks/codex-hook.mjs" role-on-code',
    );
    for (const hook of pre.flatMap((/** @type {Map<string, any>} */ entry) => entry.get("hooks"))) {
      const match = /^node "\$CLAUDE_PROJECT_DIR\/_aitna\/akmon\/js\/hooks\/([a-z-]+)\.mjs"$/.exec(hook.get("command"));
      assert.ok(match, hook.get("command"));
      assert.ok(fs.existsSync(posix.join(root, "_aitna", "akmon", "js", "hooks", `${match[1]}.mjs`)));
    }
  });
});

test("a mounted record's hooks directory follows a relocated dev layer", () => {
  withScratch((scratch) => {
    const root = posix.join(scratch, "project");
    put(root, "tools/ai/.akmon.toml", MOUNTED_RECORD);
    withAitnaRoot("tools/ai", () => {
      assert.equal(nodeHooksDir(root), "tools/ai/akmon/js/hooks");
      const commands = [...codexHooks(data, root).get("hooks").values()].flatMap((entries) =>
        entries.flatMap((/** @type {Map<string, any>} */ entry) =>
          entry.get("hooks").map((/** @type {Map<string, any>} */ hook) => hook.get("command")),
        ),
      );
      assert.ok(
        commands.every((command) => command.includes('/tools/ai/akmon/js/hooks/codex-hook.mjs"')),
        commands.join("\n"),
      );
      assert.ok(isAkmonEntry(data, new Map([["hooks", [new Map([["command", commands[0]]])]]])));
    });
  });
});

test("codexHooksText is the pretty-printed wiring with a trailing newline, ASCII only", () => {
  let text = "";
  withPackageProject((root) => {
    text = codexHooksText(data, root);
  });
  assert.ok(text.endsWith("}\n"));
  assert.ok(text.startsWith('{\n  "hooks": {\n    "PreToolUse": [\n'));
  assert.ok(/^[\x20-\x7e\n]*$/.test(text));
  assert.deepEqual(JSON.parse(text).hooks.SessionStart[0].matcher, "startup|resume|clear|compact");
});

// --------------------------------------------------------------------------------------
// the refusal
// --------------------------------------------------------------------------------------

test("a record that is not a Node one is refused with exit 2 and writes nothing", () => {
  withScratch((scratch) => {
    /** @type {Array<[string | null, string]>} */
    const cases = [
      [null, "no integration record (_aitna/.akmon.toml)"],
      ['akmon_version = "1"\n', 'ecosystem = "python"'],
      ['mount = "submodule"\n', 'ecosystem = "python"'],
      ['mount = "vendored"\n', 'ecosystem = "python"'],
      ['mount = "subtree"\necosystem = "python"\n', 'ecosystem = "python"'],
      ['mount = "package"\n', 'ecosystem = "python"'],
      ['mount = "package"\necosystem = "python"\n', 'ecosystem = "python"'],
      ['mount = "package"\necosystem = "ruby"\n', 'ecosystem = "ruby"'],
      ['mount = "package"\necosystem = ""\n', 'ecosystem = "python"'],
    ];
    for (const [record, found] of cases) {
      fs.rmSync(posix.join(scratch, "project"), { recursive: true, force: true });
      const root = project(scratch, { record });
      const before = fs.readdirSync(root).sort();
      for (const args of [[], ["--check"], ["--dry-run"]]) {
        const result = run(["--project-root", root, ...args]);
        assert.equal(result.code, 2, `${record} ${args}`);
        assert.equal(result.stdout, "", `${record} ${args}`);
        assert.ok(
          result.stderr.startsWith("akmon sync: the JavaScript implementation serves Node projects only"),
          result.stderr,
        );
        assert.ok(result.stderr.includes(`but this project has ${found};`), result.stderr);
        assert.equal(result.stderr.split("\n").length, 2, "one line");
      }
      assert.deepEqual(fs.readdirSync(root).sort(), before);
    }
  });
});

test("a Node record is accepted, and the refusal answers null for it", () => {
  withScratch((scratch) => {
    assert.equal(unsupportedRecord(data, project(scratch)), null);
  });
});

test("a mounted Node record is served in every mounted mode (C129)", () => {
  for (const mount of ["submodule", "vendored", "subtree"]) {
    withScratch((scratch) => {
      const root = mountedProject(scratch, { record: `mount = "${mount}"\necosystem = "node"\n` });
      assert.equal(unsupportedRecord(data, root), null, mount);
      assert.equal(unsupportedFound(data, root), null, mount);
    });
  }
  withScratch((scratch) => {
    const root = mountedProject(scratch, { record: 'ecosystem = "node"\n' });
    assert.equal(unsupportedFound(data, root), null);
  });
});

test("the refusal names the relocated dev layer", () => {
  withScratch((scratch) => {
    const root = project(scratch, { record: null });
    withAitnaRoot("tools/ai", () => {
      assert.ok(
        /** @type {string} */ (unsupportedRecord(data, root)).includes("no integration record (tools/ai/.akmon.toml)"),
      );
    });
  });
});

test("readMountMode defaults to submodule, as the twin does", () => {
  withScratch((scratch) => {
    assert.equal(readMountMode(project(scratch, { record: null })), "submodule");
  });
});

// --------------------------------------------------------------------------------------
// the command
// --------------------------------------------------------------------------------------

test("--dry-run writes nothing and lists what would change; a real run writes; --check is then clean", () => {
  withScratch((scratch) => {
    const root = project(scratch);
    const before = fs.readdirSync(root).sort();
    const dry = run(["--project-root", root, "--dry-run"]);
    assert.equal(dry.code, 0);
    assert.ok(
      dry.stdout.startsWith("would update: CLAUDE.md\nwould update: .github/copilot-instructions.md\n"),
      dry.stdout,
    );
    assert.ok(dry.stdout.includes("would update: .claude/settings.json\n"));
    assert.ok(dry.stdout.includes("would update: _aitna/.akmon/guardrails/_common.md\n"));
    assert.ok(dry.stdout.endsWith("would update: _aitna/.akmon.toml\n"), dry.stdout);
    assert.deepEqual(fs.readdirSync(root).sort(), before);

    const stale = run(["--project-root", root, "--check"]);
    assert.equal(stale.code, 1);
    assert.ok(
      stale.stdout.startsWith(
        "ERROR sync.stale-generated CLAUDE.md: generated file is stale or missing: CLAUDE.md → Run akmon sync to regenerate this file.\n",
      ),
      stale.stdout,
    );

    const written = run(["--project-root", root]);
    assert.equal(written.code, 0);
    assert.ok(written.stdout.startsWith("updated: CLAUDE.md\n"));
    const again = run(["--project-root", root]);
    assert.equal(again.code, 0);
    assert.ok(again.stdout.startsWith("ok: CLAUDE.md\n"));
    assert.ok(again.stdout.endsWith("akmon sync: no changes\n"), again.stdout);
    const clean = run(["--project-root", root, "--check"]);
    assert.equal(clean.code, 0);
    assert.ok(
      clean.stdout
        .split("\n")
        .filter(Boolean)
        .every((line) => line.startsWith("OK sync.up-to-date ")),
      clean.stdout,
    );
    assert.equal(clean.stderr, "");
  });
});

test("a written project holds the Node spellings and the record's pin is the tree's version", () => {
  withScratch((scratch) => {
    const root = project(scratch);
    assert.equal(run(["--project-root", root]).code, 0);
    const settings = JSON.parse(get(root, ".claude/settings.json"));
    assert.equal(
      settings.hooks.PreToolUse[0].hooks[0].command,
      'node "$CLAUDE_PROJECT_DIR/node_modules/akmon/js/hooks/git-commit-guard.mjs"',
    );
    assert.equal(get(root, ".codex/hooks.json"), codexHooksText(data, root));
    const record = get(root, "_aitna/.akmon.toml");
    assert.equal(record, `mount = "package"\necosystem = "node"\nakmon_version = "${installedAkmonVersion()}"\n`);
    assert.ok(
      get(root, ".claude/skills/release/SKILL.md").includes("](../../../node_modules/akmon/skills/release/SKILL.md)"),
    );
    assert.equal(get(root, "_aitna/.akmon/guardrails/_common.md").includes("\r"), false);
    assert.ok(!fs.existsSync(posix.join(root, "_aitna", ".akmon", "hooks")));
  });
});

test("a mounted Node project is written from the mount: its wiring, relative skill links, no materialization (C129)", () => {
  withScratch((scratch) => {
    const root = mountedProject(scratch);
    assert.equal(standardTreeRoot(root), posix.join(root, "_aitna", "akmon"));
    const written = run(["--project-root", root]);
    assert.equal(written.code, 0, written.stderr);
    assert.equal(written.stderr, "");
    const settings = JSON.parse(get(root, ".claude/settings.json"));
    assert.equal(
      settings.hooks.PreToolUse[0].hooks[0].command,
      'node "$CLAUDE_PROJECT_DIR/_aitna/akmon/js/hooks/git-commit-guard.mjs"',
    );
    assert.equal(get(root, ".codex/hooks.json"), codexHooksText(data, root));
    assert.ok(
      get(root, ".claude/skills/release/SKILL.md").includes("](../../../_aitna/akmon/skills/release/SKILL.md)"),
    );
    // A mounted record imports the mount directly: nothing is materialized, the record is not stamped.
    assert.ok(!fs.existsSync(materializationRoot(root)));
    assert.equal(get(root, "_aitna/.akmon.toml"), MOUNTED_RECORD);
    const clean = run(["--project-root", root, "--check"]);
    assert.equal(clean.code, 0, clean.stdout);
  });
});

test("standardTreeRoot: a mounted record without its mount, or a package record beside a stale mount, is the running tree", () => {
  withScratch((scratch) => {
    const root = mountedProject(scratch);
    fs.unlinkSync(posix.join(root, "_aitna", "akmon"));
    assert.equal(standardTreeRoot(root), TREE);
    put(root, "_aitna/.akmon.toml", NODE_RECORD);
    fs.symlinkSync(TREE, posix.join(root, "_aitna", "akmon"));
    assert.equal(standardTreeRoot(root), TREE);
  });
});

test("the record is stamped without touching its other lines or the ecosystem", () => {
  withScratch((scratch) => {
    const root = project(scratch, {
      record: "# mine\nmount = 'package'\necosystem = 'node'\n[check]\nrunner = \"x\"\n",
    });
    assert.equal(run(["--project-root", root]).code, 0);
    assert.equal(
      get(root, "_aitna/.akmon.toml"),
      `# mine\nmount = "package"\necosystem = 'node'\nakmon_version = "${installedAkmonVersion()}"\n[check]\nrunner = "x"\n`,
    );
  });
});

test("a plan error is exit 2: stderr in the writing modes, a finding in --check, and the rest still planned", () => {
  withScratch((scratch) => {
    const root = project(scratch);
    put(root, ".claude/settings.json", '{"hooks": {},}');
    const written = run(["--project-root", root]);
    assert.equal(written.code, 2);
    assert.ok(
      written.stderr.startsWith(
        `error: ${root}/.claude/settings.json: invalid JSON: Expecting property name enclosed in double quotes: line 1 column 14 (char 13)\n`,
      ),
      written.stderr,
    );
    assert.ok(written.stdout.includes("updated: CLAUDE.md\n"));
    assert.equal(get(root, ".claude/settings.json"), '{"hooks": {},}');
    const checked = run(["--project-root", root, "--check"]);
    assert.equal(checked.code, 2);
    assert.ok(
      checked.stdout.includes(`ERROR sync.plan-error: ${root}/.claude/settings.json: invalid JSON`),
      "an empty target collapses the slot",
    );
    assert.ok(
      checked.stdout.includes(
        "invalid JSON: Expecting property name enclosed in double quotes: line 1 column 14 (char 13) → Resolve the reported planning error, then re-run akmon sync.\n",
      ),
    );
  });
});

test("the JavaScript language profile the init block names is materialized like the Python one", () => {
  withScratch((scratch) => {
    const root = project(scratch, { agents: `${COMMON}@_aitna/.akmon/profiles/js.md\n` });
    assert.equal(run(["--project-root", root]).code, 0);
    assert.ok(get(root, "_aitna/.akmon/profiles/js.md").startsWith("# Profile: JavaScript and TypeScript"));
    assert.equal(run(["--project-root", root, "--check"]).code, 0);
  });
});

test("an import the standard does not ship is a plan error naming the line to write", () => {
  withScratch((scratch) => {
    const root = project(scratch, {
      agents: `${COMMON}@_aitna/.akmon/guardrails/python.md\n@_aitna/.akmon/profiles/gone.md\n`,
    });
    const result = run(["--project-root", root, "--dry-run"]);
    assert.equal(result.code, 2);
    assert.equal(
      result.stderr,
      "error: AGENTS.md imports guardrails/python.md, which the standard moved to profiles/python.md: replace the line with @_aitna/.akmon/profiles/python.md\n" +
        "error: AGENTS.md imports a file the standard does not ship: profiles/gone.md\n",
    );
  });
});

test("a duplicate skill name is a plan error; the first source wins", () => {
  withScratch((scratch) => {
    const root = project(scratch);
    put(root, "skills/release/SKILL.md", "---\nname: release\n---\n");
    const result = run(["--project-root", root, "--dry-run"]);
    assert.equal(result.code, 2);
    assert.equal(
      result.stderr,
      `error: duplicate skill name 'release': ${root}/node_modules/akmon/skills/release/SKILL.md and ${root}/skills/release/SKILL.md\n`,
    );
  });
});

test("usage errors are one line and exit 2; --help is exit 0", () => {
  for (const argv of [["--bogus"], ["extra"], ["--project-root"], ["--check", "--dry-run"]]) {
    const result = run(argv);
    assert.equal(result.code, 2, String(argv));
    assert.ok(result.stderr.startsWith("akmon sync: error: "), result.stderr);
    assert.equal(result.stderr.split("\n").length, 2);
    assert.equal(result.stdout, "");
  }
  assert.equal(
    run(["--check", "--dry-run"]).stderr,
    "akmon sync: error: --check and --dry-run are mutually exclusive\n",
  );
  const help = run(["-h"]);
  assert.equal(help.code, 0);
  assert.ok(help.stdout.startsWith("usage: akmon sync [-h] [--project-root PROJECT_ROOT] [--check] [--dry-run]\n"));
  assert.equal(run(["--help"]).stdout, help.stdout);
});

test("with no project root in reach the notice names the fallback and the record check follows", () => {
  withScratch((scratch) => {
    const empty = posix.join(scratch, "empty");
    fs.mkdirSync(empty);
    const saved = process.cwd();
    process.chdir(empty);
    try {
      const result = run([]);
      assert.equal(result.code, 2);
      assert.ok(
        result.stderr.startsWith(
          `[akmon] no project root at or above ${empty}: expected AGENTS.md beside _aitna/akmon or _aitna/.akmon.toml.`,
        ),
        result.stderr,
      );
      assert.ok(result.stderr.includes("but this project has no integration record (_aitna/.akmon.toml);"));
    } finally {
      process.chdir(saved);
    }
  });
});

test("a custom AITNA_ROOT moves the record, the materialization and the markers", () => {
  withScratch((scratch) => {
    const root = posix.join(scratch, "project");
    fs.mkdirSync(root);
    put(root, "tools/ai/.akmon.toml", NODE_RECORD);
    put(root, "AGENTS.md", "@tools/ai/.akmon/guardrails/_common.md\n@tools/ai/.akmon/profiles/python.md\n");
    fs.mkdirSync(posix.join(root, "node_modules"));
    fs.symlinkSync(TREE, posix.join(root, "node_modules", "akmon"));
    withAitnaRoot("tools/ai", () => {
      assert.equal(run(["--project-root", root]).code, 0);
      assert.ok(fs.existsSync(posix.join(root, "tools/ai/.akmon/profiles/python.md")));
      assert.ok(get(root, "CLAUDE.md").includes("tools/ai"));
      assert.equal(run(["--project-root", root, "--check"]).code, 0);
    });
  });
});

// --------------------------------------------------------------------------------------
// the settings round trip
// --------------------------------------------------------------------------------------

/**
 * The settings file the plan writes for `text`.
 * @param {string | Buffer} text
 * @returns {string}
 */
function settingsFor(text) {
  let written = "";
  withScratch((scratch) => {
    const root = project(scratch);
    put(root, ".claude/settings.json", text);
    written = claudeSettings(data, root).content;
  });
  return written;
}

test("settings: everything of the user's file is kept, in its order, and written like json.dumps(indent=2)", () => {
  const text =
    '{"b": 1, "10": {"7": 1, "1": 2}, "2": [1.0, 1e3, -0.0, 2.5], "é": "日本語😀", "hooks": {"Custom": [{"x": 1}]}, "a": null}';
  const written = settingsFor(text);
  const parsed = JSON.parse(written);
  assert.deepEqual(Object.keys(parsed).sort(), ["10", "2", "a", "b", "hooks", "é"]);
  assert.ok(
    written.startsWith(
      '{\n  "b": 1,\n  "10": {\n    "7": 1,\n    "1": 2\n  },\n  "2": [\n    1.0,\n    1000.0,\n    -0.0,\n    2.5\n  ],\n  "\\u00e9": "\\u65e5\\u672c\\u8a9e\\ud83d\\ude00",\n  "hooks": {\n    "Custom": [\n',
    ),
    written,
  );
  assert.ok(written.endsWith("}\n"));
  assert.ok(
    written.indexOf('"\\u00e9"') < written.indexOf('"hooks"') &&
      written.indexOf('"hooks"') < written.indexOf('"a": null'),
    "hooks stays where the file had it",
  );
});

test("settings: a missing file or `{}` gets a `hooks` key last; the wiring is the whole of it", () => {
  const written = JSON.parse(settingsFor("{}"));
  assert.deepEqual(Object.keys(written), ["hooks"]);
  assert.deepEqual(Object.keys(written.hooks), ["PreToolUse", "SessionStart", "UserPromptSubmit", "Stop"]);
  withScratch((scratch) => {
    const content = claudeSettings(data, project(scratch)).content;
    assert.deepEqual(JSON.parse(content), written);
    assert.equal(content, settingsFor("{}"));
  });
});

test("settings: user hooks stay put and the old Python-spelled akmon entries are replaced, not duplicated", () => {
  const old = {
    hooks: {
      PreToolUse: [
        {
          matcher: "Bash",
          hooks: [{ type: "command", command: '"$CLAUDE_PROJECT_DIR/.venv/bin/akmon" hook git-commit-guard' }],
        },
        { matcher: "Bash", hooks: [{ type: "command", command: "echo mine" }] },
        {
          matcher: "Edit",
          hooks: [{ type: "command", command: 'python3 "$CLAUDE_PROJECT_DIR/_aitna/akmon/hooks/role-on-code.py"' }],
        },
      ],
      Stop: [{ hooks: [{ type: "command", command: "user-stop.sh" }] }],
    },
    permissions: { allow: ["Bash(ls)"] },
  };
  const written = JSON.parse(settingsFor(JSON.stringify(old)));
  const commands = written.hooks.PreToolUse.flatMap((/** @type {any} */ entry) =>
    entry.hooks.map((/** @type {any} */ hook) => hook.command),
  );
  assert.deepEqual(commands.slice(0, 1), ["echo mine"]);
  assert.ok(
    commands
      .slice(1)
      .every((/** @type {string} */ command) =>
        command.startsWith('node "$CLAUDE_PROJECT_DIR/node_modules/akmon/js/hooks/'),
      ),
    commands.join("\n"),
  );
  assert.equal(new Set(commands).size, commands.length);
  assert.deepEqual(written.permissions, old.permissions);
  assert.equal(written.hooks.Stop[0].hooks[0].command, "user-stop.sh");
  assert.equal(written.hooks.Stop.length, 2);
  // idempotent: a second pass over its own output is the same text
  const once = settingsFor(JSON.stringify(old));
  assert.equal(settingsFor(once), once);
});

test("settings: the sentences of a file that is not a settings object are the twin's", () => {
  /** @type {Array<[string | Buffer, string]>} */
  const cases = [
    ["", "invalid JSON: Expecting value: line 1 column 1 (char 0)"],
    ["  \n ", "invalid JSON: Expecting value: line 2 column 2 (char 4)"],
    ["{'a': 1}", "invalid JSON: Expecting property name enclosed in double quotes: line 1 column 2 (char 1)"],
    ['{"a" 1}', "invalid JSON: Expecting ':' delimiter: line 1 column 6 (char 5)"],
    ['{"a": 1 "b": 2}', "invalid JSON: Expecting ',' delimiter: line 1 column 9 (char 8)"],
    ['{"a": "x', "invalid JSON: Unterminated string starting at: line 1 column 7 (char 6)"],
    ['{"a": "x\ty"}', "invalid JSON: Invalid control character at: line 1 column 9 (char 8)"],
    ['{"a": "\\q"}', "invalid JSON: Invalid \\escape: line 1 column 8 (char 7)"],
    ['{"a": "\\u12"}', "invalid JSON: Invalid \\uXXXX escape: line 1 column 9 (char 8)"],
    ["{} x", "invalid JSON: Extra data: line 1 column 4 (char 3)"],
    ["\ufeff{}", "invalid JSON: Unexpected UTF-8 BOM (decode using utf-8-sig): line 1 column 1 (char 0)"],
    ['{"😀": 1, "b" 2}', "invalid JSON: Expecting ':' delimiter: line 1 column 14 (char 13)"],
    ['{\n  "a": 1,\n  "b": 2\n  "c": 3\n}', "invalid JSON: Expecting ',' delimiter: line 4 column 3 (char 23)"],
    ["[1, 2]", "expected a JSON object"],
    ['"x"', "expected a JSON object"],
    ["null", "expected a JSON object"],
    ['{"hooks": null}', "expected hooks to be a JSON object"],
    ['{"hooks": []}', "expected hooks to be a JSON object"],
    ['{"hooks": "x"}', "expected hooks to be a JSON object"],
    [Buffer.from('{"a": "\xff"}', "latin1"), "'utf-8' codec can't decode byte 0xff in position 7: invalid start byte"],
    [Buffer.from([0x7b, 0xe2, 0x82]), "'utf-8' codec can't decode bytes in position 1-2: unexpected end of data"],
    [
      Buffer.from([0x7b, 0xed, 0xa0, 0x80]),
      "'utf-8' codec can't decode byte 0xed in position 1: invalid continuation byte",
    ],
  ];
  withScratch((scratch) => {
    const root = project(scratch);
    for (const [text, sentence] of cases) {
      put(root, ".claude/settings.json", text);
      assert.throws(
        () => claudeSettings(data, root),
        (error) => {
          assert.ok(error instanceof Error);
          assert.ok(error.message.endsWith(sentence), `${error.message}\n  wanted: ...${sentence}`);
          assert.ok(["ValueError", "UnicodeDecodeError"].includes(error.name));
          return true;
        },
        String(text),
      );
    }
  });
});

test("settings: an integer beyond 2**53 cannot be written back unchanged and is refused as a plan error", () => {
  withScratch((scratch) => {
    const root = project(scratch);
    put(root, ".claude/settings.json", '{"big": 12345678901234567890, "hooks": {}}');
    const result = run(["--project-root", root, "--dry-run"]);
    assert.equal(result.code, 2);
    assert.ok(result.stderr.includes("integer 12345678901234567890 is beyond 2**53"), result.stderr);
    put(root, ".claude/settings.json", '{"big": 9007199254740991, "hooks": {}}');
    assert.equal(run(["--project-root", root, "--dry-run"]).code, 0);
  });
});

test("readJson: a missing file is an empty object; the document keeps integer-like keys in file order", () => {
  withScratch((scratch) => {
    assert.equal(readJson(posix.join(scratch, "nope.json")).size, 0);
    put(scratch, "a.json", '{"10": 1, "9": 2, "a": 3, "1": 4}');
    assert.deepEqual([...readJson(posix.join(scratch, "a.json")).keys()], ["10", "9", "a", "1"]);
  });
});

test("mergeHookEntries: the stale akmon entry goes, the user's stays, and a repeat changes nothing", () => {
  /** @type {any[]} */
  let wanted = [];
  withPackageProject((root) => {
    wanted = [...claudeHooks(data, root).get("hooks").get("PreToolUse")];
  });
  const user = { matcher: "Bash", hooks: [{ type: "command", command: "echo mine" }] };
  const once = mergeHookEntries(data, [user, wanted[0]], wanted);
  assert.equal(once[0], user);
  assert.equal(once.length, 1 + wanted.length);
  const twice = mergeHookEntries(data, once, wanted);
  assert.deepEqual(
    twice.map((entry) => JSON.stringify(entry instanceof Map ? [...entry] : entry)),
    once.map((entry) => JSON.stringify(entry instanceof Map ? [...entry] : entry)),
  );
});

// --------------------------------------------------------------------------------------
// deletions and the materialization
// --------------------------------------------------------------------------------------

test("the dev layer's .akmon directory is owned outright: everything unplanned goes, in path order, and the empty directories with it", () => {
  withScratch((scratch) => {
    const root = project(scratch);
    assert.equal(run(["--project-root", root]).code, 0);
    put(root, "_aitna/.akmon/a-b/f.txt", "x\n");
    put(root, "_aitna/.akmon/a/c.txt", "x\n");
    put(root, "_aitna/.akmon/a/b/d.txt", "x\n");
    put(root, "_aitna/.akmon/routing.json", "{}\n");
    const check = run(["--project-root", root, "--check"]);
    assert.equal(check.code, 1);
    const deleted = check.stdout.split("\n").filter((line) => line.startsWith("ERROR sync.obsolete-generated "));
    assert.deepEqual(
      deleted.map((line) => line.split(" ")[2].slice(0, -1)),
      ["_aitna/.akmon/a/b/d.txt", "_aitna/.akmon/a/c.txt", "_aitna/.akmon/a-b/f.txt", "_aitna/.akmon/routing.json"],
    );
    const written = run(["--project-root", root]);
    assert.deepEqual(
      written.stdout.split("\n").filter((line) => line.startsWith("deleted: ")),
      [
        "deleted: _aitna/.akmon/a/b/d.txt",
        "deleted: _aitna/.akmon/a/c.txt",
        "deleted: _aitna/.akmon/a-b/f.txt",
        "deleted: _aitna/.akmon/routing.json",
      ],
    );
    assert.deepEqual(fs.readdirSync(posix.join(root, "_aitna", ".akmon")), ["guardrails"]);
  });
});

test("bytecode caches under the materialization are swept silently: no drift, no leftover directories", () => {
  withScratch((scratch) => {
    const root = project(scratch);
    assert.equal(run(["--project-root", root]).code, 0);
    put(root, "_aitna/.akmon/hooks/__pycache__/x.cpython-311.pyc", "x");
    put(root, "_aitna/.akmon/hooks/__pycache__/y.pyo", "x");
    put(root, "_aitna/.akmon/p/__pycache__/q/__pycache__/r.pyc", "x");
    const check = run(["--project-root", root, "--check"]);
    assert.equal(check.code, 0, check.stdout);
    assert.ok(!check.stdout.includes("obsolete"));
    const written = run(["--project-root", root]);
    assert.equal(written.code, 0);
    assert.ok(!written.stdout.includes("deleted: "), written.stdout);
    assert.deepEqual(fs.readdirSync(posix.join(root, "_aitna", ".akmon")), ["guardrails", "hooks", "p"]);
    assert.deepEqual(fs.readdirSync(posix.join(root, "_aitna", ".akmon", "hooks")), []);
  });
});

test("a link in the materialization is judged by what it points at, and a linked directory is never entered", () => {
  withScratch((scratch) => {
    const root = project(scratch);
    assert.equal(run(["--project-root", root]).code, 0);
    put(scratch, "elsewhere/inner/f.txt", "x\n");
    const akmon = posix.join(root, "_aitna", ".akmon");
    fs.symlinkSync(posix.join(scratch, "elsewhere"), posix.join(akmon, "dirlink"));
    fs.symlinkSync(posix.join(scratch, "elsewhere", "inner", "f.txt"), posix.join(akmon, "filelink"));
    fs.symlinkSync(posix.join(scratch, "nowhere"), posix.join(akmon, "dangling"));
    const check = run(["--project-root", root, "--check"]);
    const obsolete = check.stdout.split("\n").filter((line) => line.startsWith("ERROR sync.obsolete-generated "));
    assert.deepEqual(
      obsolete.map((line) => line.split(" ")[2].slice(0, -1)),
      ["_aitna/.akmon/dangling", "_aitna/.akmon/filelink"],
    );
    assert.equal(run(["--project-root", root]).code, 0);
    assert.deepEqual(fs.readdirSync(akmon).sort(), ["dirlink", "guardrails"]);
    assert.equal(fs.readFileSync(posix.join(scratch, "elsewhere", "inner", "f.txt"), "utf-8"), "x\n");
  });
});

test("readSyncData is a lazy bundle of the three data files", () => {
  const bundle = readSyncData();
  assert.deepEqual(Object.keys(bundle), ["sync", "materialization", "findings"]);
  assert.equal(bundle.sync.cli_name, "akmon");
  assert.equal(bundle.sync, bundle.sync, "read once");
  assert.equal(typeof bundle.materialization.generated_banner.prefix, "string");
  assert.deepEqual(bundle.findings.severities, ["ok", "warn", "error"]);
});

test("only .pyc and .pyo go from a cache: a cache holding anything else is left, and is not drift", () => {
  withScratch((scratch) => {
    const root = project(scratch);
    assert.equal(run(["--project-root", root]).code, 0);
    for (const name of ["a.pyc", ".pyc", "b.pyc.bak", "keep.txt"]) {
      put(root, `_aitna/.akmon/__pycache__/${name}`, "x");
    }
    assert.equal(run(["--project-root", root, "--check"]).code, 0);
    assert.equal(run(["--project-root", root]).code, 0);
    assert.deepEqual(fs.readdirSync(posix.join(root, "_aitna", ".akmon", "__pycache__")).sort(), [
      ".pyc",
      "b.pyc.bak",
      "keep.txt",
    ]);
  });
});

test("a generated skill stub the plan no longer wants is deleted with its directory; a hand-written one stays", () => {
  withScratch((scratch) => {
    const root = project(scratch);
    const marker = data.materialization.generated_banner.prefix;
    put(root, ".claude/skills/old/SKILL.md", `# old\n\n<!-- ${marker}x -->\n`);
    put(root, ".agents/skills/old/SKILL.md", `---\n# ${marker}x\nname: old\n---\n`);
    put(root, ".claude/skills/mine/SKILL.md", "# mine\n");
    put(root, ".claude/skills/odd/SKILL.md", `<!-- ${marker}x -->\n`);
    put(root, ".claude/skills/odd/notes.txt", "keep\n");
    const result = run(["--project-root", root]);
    assert.equal(result.code, 0);
    assert.ok(result.stdout.includes("deleted: .claude/skills/old/SKILL.md\n"));
    assert.ok(result.stdout.includes("deleted: .agents/skills/old/SKILL.md\n"));
    assert.ok(!fs.existsSync(posix.join(root, ".claude/skills/old")));
    assert.ok(!fs.existsSync(posix.join(root, ".agents/skills/old")));
    assert.ok(fs.existsSync(posix.join(root, ".claude/skills/mine/SKILL.md")));
    assert.ok(fs.existsSync(posix.join(root, ".claude/skills/odd/notes.txt")));
    assert.ok(!fs.existsSync(posix.join(root, ".claude/skills/odd/SKILL.md")));
  });
});

test("skills are listed hidden ones too, in code-point order of the directory name", () => {
  withScratch((scratch) => {
    const root = project(scratch, { link: false });
    for (const name of ["a", "a-b", "a_b", "A", ".hid", "é", "a0"]) {
      put(root, `skills/${name}/SKILL.md`, `# ${name}\n`);
    }
    put(root, "skills/loose.md", "x");
    put(root, "skills/nofile/README.md", "x");
    const own = skillSources(data, root)[0].filter((source) => source.startsWith(posix.join(root, "skills/")));
    assert.deepEqual(
      own.map((source) => posix.basename(posix.dirname(source))),
      [".hid", "A", "a", "a-b", "a0", "a_b", "é"],
    );
  });
});

test("an import under a relocated dev layer matches exactly its own prefix", () => {
  withScratch((scratch) => {
    const root = posix.join(scratch, "project");
    fs.mkdirSync(root);
    put(root, "a.b+c/.akmon.toml", 'mount = "package"\n');
    put(root, "AGENTS.md", "@a.b+c/.akmon/profiles/python.md\n@aXb+c/.akmon/profiles/quant.md\n");
    withAitnaRoot("a.b+c", () => {
      assert.deepEqual(importedStandardFiles(data, root), [["guardrails/_common.md", "profiles/python.md"], []]);
    });
  });
});

test("the scan reads text the way Python does: CRLF, lone CR and U+2028 are not line starts for a fence", () => {
  withScratch((scratch) => {
    const root = project(scratch, { record: NODE_RECORD });
    const prefix = "@_aitna/.akmon/profiles/";
    for (const [text, names] of /** @type {Array<[string, string[]]>} */ ([
      [`\`\`\`\r\n${prefix}python.md\r\n\`\`\`\r\n${prefix}quant.md\r\n`, ["profiles/quant.md"]],
      [`\`\`\`\r${prefix}python.md\r\`\`\`\r${prefix}quant.md\r`, ["profiles/quant.md"]],
      // the closing line opens a fence of its own, which has no end: it takes quant.md with it
      [`text\u2028\`\`\`\n${prefix}python.md\n\`\`\`\n${prefix}quant.md\n`, ["profiles/python.md"]],
      [`a\x0b\`\`\`\n${prefix}python.md\n`, ["profiles/python.md"]],
    ])) {
      put(root, "AGENTS.md", text);
      const [found, errors] = importedStandardFiles(data, root);
      assert.deepEqual(found, ["guardrails/_common.md", ...names], JSON.stringify(text));
      assert.deepEqual(errors, []);
    }
  });
});

test("upsertTomlKey: a byte-order mark is not whitespace, a U+2028 is a line break", () => {
  assert.equal(upsertTomlKey('\ufeffmount = "x"\n', "mount", "package"), '\ufeffmount = "x"\nmount = "package"\n');
  assert.equal(upsertTomlKey('a = 1\u2028mount = "x"\n', "mount", "package"), 'a = 1\nmount = "package"\n');
  assert.equal(upsertTomlKey("", "mount", "package"), 'mount = "package"\n');
  assert.equal(upsertTomlKey("a = 1", "mount", "package"), 'a = 1\nmount = "package"');
});

// --------------------------------------------------------------------------------------
// the plan and the classes
// --------------------------------------------------------------------------------------

test("a PlannedFile is frozen; apply reports what is already right and compares as Python reads the file", () => {
  const planned = new PlannedFile("/x", "y");
  assert.throws(() => {
    /** @type {any} */ (planned).content = "z";
  }, TypeError);
  withScratch((scratch) => {
    const target = posix.join(scratch, "f.txt");
    fs.writeFileSync(target, "a\r\nb\r\n");
    const result = apply(data, [new PlannedFile(target, "a\nb\n")], { write: true });
    assert.deepEqual([result.changed, result.deleted, result.ok, result.errors], [[], [], [target], []]);
    assert.equal(fs.readFileSync(target, "utf-8"), "a\r\nb\r\n");
  });
});

test("apply creates the missing directories; a check or dry run does not", () => {
  withScratch((scratch) => {
    const target = posix.join(scratch, "deep", "er", "f.txt");
    const dry = apply(data, [new PlannedFile(target, "x")], { write: false });
    assert.deepEqual(dry.changed, [target]);
    assert.ok(!fs.existsSync(posix.join(scratch, "deep")));
    apply(data, [new PlannedFile(target, "x")], { write: true });
    assert.equal(fs.readFileSync(target, "utf-8"), "x");
  });
});

test("the plan lists the vendor files first, then settings, skills, the materialization and the record", () => {
  withScratch((scratch) => {
    const root = project(scratch);
    const [files, errors] = plannedFiles(data, root);
    assert.deepEqual(errors, []);
    const relative = files.map((file) => file.path.slice(root.length + 1));
    assert.deepEqual(relative.slice(0, 6), [
      "CLAUDE.md",
      ".github/copilot-instructions.md",
      "GEMINI.md",
      ".codex/README.md",
      ".codex/hooks.json",
      ".claude/settings.json",
    ]);
    assert.equal(relative.at(-1), "_aitna/.akmon.toml");
    assert.ok(relative.includes("_aitna/.akmon/guardrails/_common.md"));
    assert.equal(materializationRoot(root), posix.join(root, "_aitna", ".akmon"));
  });
});

test("checkFindings: one finding per file, then one per plan error, in the envelope's rendering", () => {
  withScratch((scratch) => {
    const root = project(scratch);
    const result = apply(data, [new PlannedFile(posix.join(root, "a.txt"), "x")], { write: false });
    result.errors.push("boom");
    const findings = checkFindings(data, result, { root });
    assert.deepEqual(
      findings.map((finding) => [finding.severity, finding.code, finding.target]),
      [
        ["error", "sync.stale-generated", "a.txt"],
        ["error", "sync.plan-error", ""],
      ],
    );
    assert.equal(findings[1].message, "boom");
  });
});

// --------------------------------------------------------------------------------------
// the process
// --------------------------------------------------------------------------------------

test("run as a program: the exit code is the command's, through a symlink as npm installs a bin", () => {
  withScratch((scratch) => {
    const root = project(scratch);
    const link = posix.join(scratch, "sync-link.mjs");
    fs.symlinkSync(SYNC, link);
    const env = { ...process.env };
    delete env.AITNA_ROOT;
    for (const entry of [SYNC, link]) {
      const stale = spawnSync(process.execPath, [entry, "--project-root", root, "--check"], { encoding: "utf-8", env });
      assert.equal(stale.status, 1, stale.stderr);
      assert.ok(stale.stdout.startsWith("ERROR sync.stale-generated CLAUDE.md"));
    }
    const written = spawnSync(process.execPath, [link, "--project-root", root], { encoding: "utf-8", env });
    assert.equal(written.status, 0, written.stderr);
    const clean = spawnSync(process.execPath, [SYNC, "--project-root", root, "--check"], { encoding: "utf-8", env });
    assert.equal(clean.status, 0);
    const refused = spawnSync(process.execPath, [SYNC, "--project-root", scratch], { encoding: "utf-8", env });
    assert.equal(refused.status, 2);
    assert.ok(refused.stderr.includes("serves Node projects only"));
  });
});

test("imported as a module, the file runs nothing", () => {
  const done = spawnSync(
    process.execPath,
    ["--input-type=module", "-e", `import ${JSON.stringify(SYNC)}; console.log("quiet")`],
    { encoding: "utf-8" },
  );
  assert.equal(done.stdout, "quiet\n");
  assert.equal(done.stderr, "");
});

// -- language profiles (C127): the mapping init writes from and verify checks against ----------

test("languageProfiles maps the named languages and reads the manifests, python first", () => {
  const scratch = fs.realpathSync(fs.mkdtempSync(posix.join(os.tmpdir(), "akmon-sync-profiles-")));
  try {
    const data = readSyncData();
    const names = (/** @type {string[]} */ languages) =>
      languageProfiles(data, scratch, languages).map((found) => found.profile);
    assert.deepEqual(names(["python"]), ["python.md"]);
    assert.deepEqual(names(["package/python"]), ["python.md"]);
    assert.deepEqual(names(["JavaScript"]), ["js.md"]);
    assert.deepEqual(names(["service/typescript"]), ["js.md"]);
    assert.deepEqual(names(["python", "javascript"]), ["python.md", "js.md"]);
    assert.deepEqual(names(["unclassified"]), []);
    assert.deepEqual(names(["<archetype>/<language>"]), []);
    assert.deepEqual(names(["rust"]), []);
    assert.deepEqual(names([]), []);
    fs.writeFileSync(posix.join(scratch, "pyproject.toml"), "[project]\n");
    assert.deepEqual(languageProfiles(data, scratch, ["package/python", "javascript"]), [
      { profile: "python.md", source: "pyproject.toml" },
      { profile: "js.md", source: "javascript" },
    ]);
    fs.writeFileSync(posix.join(scratch, "package.json"), "{}\n");
    assert.deepEqual(languageProfiles(data, scratch, []), [
      { profile: "python.md", source: "pyproject.toml" },
      { profile: "js.md", source: "package.json" },
    ]);
  } finally {
    fs.rmSync(scratch, { recursive: true, force: true });
  }
});

test("profileImports skips code spans and fenced blocks (the twin's rows)", () => {
  const text =
    "Import one per line (`@_aitna/.akmon/profiles/<name>.md`, `@_aitna/.akmon/profiles/js.md`).\n\n" +
    "```\n@_aitna/.akmon/profiles/quant.md\n```\n\n" +
    "@_aitna/.akmon/guardrails/_common.md\n@_aitna/.akmon/profiles/python.md\n" +
    "  @_aitna/akmon/profiles/js.md\n@profiles/python-stdlib.md\nmail@profiles/x.md\n";
  assert.deepEqual(profileImports(text), [
    { prefix: "_aitna/.akmon/", name: "python.md", line: "@_aitna/.akmon/profiles/python.md" },
    { prefix: "_aitna/akmon/", name: "js.md", line: "@_aitna/akmon/profiles/js.md" },
    { prefix: "", name: "python-stdlib.md", line: "@profiles/python-stdlib.md" },
  ]);
});

// -- what counts as Python (C129) ---------------------------------------------------------------

/**
 * `git <args>` in `cwd`, which must succeed.
 * @param {string[]} args
 * @param {string} cwd
 */
function gitIn(args, cwd) {
  const result = spawnSync("git", ["-c", "user.name=t", "-c", "user.email=t@t", ...args], { cwd, encoding: "utf8" });
  assert.equal(result.status, 0, result.stderr);
}

test("hasPython: a marker file at the root, by glob; package.json alone is no Python", () => {
  for (const marker of [
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "requirements.txt",
    "requirements-dev.txt",
    "Pipfile",
    "uv.lock",
    "poetry.lock",
  ]) {
    withScratch((scratch) => {
      put(scratch, "package.json", "{}");
      put(scratch, marker, "");
      assert.equal(hasPython(data, scratch, "_aitna"), true, marker);
    });
  }
  withScratch((scratch) => {
    put(scratch, "package.json", "{}");
    put(scratch, "docs/requirements.txt", "");
    assert.equal(hasPython(data, scratch, "_aitna"), false, "a marker counts at the root only");
  });
});

test("hasPython: in a git work tree only tracked sources count, outside the dev layer and node_modules", () => {
  withScratch((scratch) => {
    put(scratch, "package.json", "{}");
    put(scratch, "app/x.py", "");
    put(scratch, "_aitna/akmon/bin/sync.py", "");
    put(scratch, "node_modules/pkg/y.py", "");
    gitIn(["init", "-q"], scratch);
    assert.equal(hasPython(data, scratch, "_aitna"), false, "untracked app/x.py");
    gitIn(["add", "-f", "_aitna", "node_modules"], scratch);
    assert.equal(hasPython(data, scratch, "_aitna"), false, "tracked, but the dev layer and node_modules");
    assert.equal(hasPython(data, scratch, "tools/ai"), true, "another dev layer leaves _aitna as project code");
    gitIn(["add", "app/x.py"], scratch);
    assert.equal(hasPython(data, scratch, "_aitna"), true);
  });
});

test("hasPython: outside a work tree a walk finds sources, skipping the dev layer, node_modules and dot-directories, up to walk_limit", () => {
  withScratch((scratch) => {
    put(scratch, "package.json", "{}");
    for (const skipped of ["tools/ai/akmon/x.py", "node_modules/p/x.py", ".venv/x.py"]) {
      put(scratch, skipped, "");
    }
    assert.equal(hasPython(data, scratch, "tools/ai"), false);
    put(scratch, "src/deep/app.py", "");
    assert.equal(hasPython(data, scratch, "tools/ai"), true);
    const bounded = { sync: { ...data.sync, python_markers: { ...data.sync.python_markers, walk_limit: 3 } } };
    assert.equal(hasPython(/** @type {any} */ (bounded), scratch, "tools/ai"), false, "the walk stopped first");
  });
});
