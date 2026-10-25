/**
 * node:test for `js/hooks/delegation-log.mjs` — the hook run as the harness runs it. The corpus
 * scenarios hold the byte-level spec; this holds what survives a bad hand-owned routing overlay.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import { posix } from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const _HOOK = fileURLToPath(new URL("./delegation-log.mjs", import.meta.url));

test("a bad routing overlay still logs the delegation and loses only the role advisories", () => {
  const root = fs.realpathSync(fs.mkdtempSync(posix.join(os.tmpdir(), "akmon-delegation-log-")));
  try {
    fs.mkdirSync(posix.join(root, "_aitna"));
    fs.mkdirSync(posix.join(root, ".claude"));
    fs.writeFileSync(posix.join(root, "AGENTS.md"), "# A\n");
    fs.writeFileSync(posix.join(root, "_aitna", ".akmon.toml"), 'mount = "package"\n');
    fs.writeFileSync(posix.join(root, "_aitna", "model-routing.json"), "{ not json");
    const payload = JSON.stringify({
      tool_name: "Task",
      tool_input: { subagent_type: "k_mechanic", description: "do the work" },
      session_id: "sess-overlay",
      cwd: root,
    });
    const run = spawnSync(process.execPath, [_HOOK], { input: payload, encoding: "utf8", cwd: root });
    assert.equal(run.status, 0, run.stderr);
    assert.match(JSON.parse(run.stdout).systemMessage, /^\[akmon\] → k_mechanic: do the work$/);
    assert.equal(
      run.stderr,
      "akmon delegation-log hook: the routing overlay _aitna/model-routing.json is not a valid JSON object; " +
        "repair or delete it (it is hand-owned, so akmon never rewrites it) — the role-matrix advisories are skipped\n",
    );
    assert.ok(fs.existsSync(posix.join(root, ".claude", "model-routing.log")));
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});
