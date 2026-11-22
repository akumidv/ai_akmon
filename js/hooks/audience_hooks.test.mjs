/**
 * node:test for the audience layers the hooks deliver (A49): the SessionStart layer on every `source`,
 * with and without an agent roster, for an attended and an unattended session, on Claude and on Codex;
 * the SubagentStart document; and the `agent_id` exemption of `role-on-code` and `analysis-guard`. Each
 * hook runs as a process, the way a harness runs it.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import { posix } from "node:path";

import { layerText } from "../common/audience.mjs";
import { read } from "../common/jsondata.mjs";
import { TREE_ROOT } from "./hook_data.mjs";
import { tempDir } from "../common/temp_dir.test.mjs";

const HOOKS = posix.join(TREE_ROOT, "js", "hooks");
const audience = /** @type {import("../common/audience.mjs").AudienceData} */ (
  read(posix.join(TREE_ROOT, "common", "audience.json"))
);
const HEAD = layerText(audience, TREE_ROOT, true);
const UNATTENDED = layerText(audience, TREE_ROOT, false);
const SOURCES = ["startup", "resume", "clear", "compact"];
const ROSTER_LINE = "[akmon] Role declaration";

/**
 * Run a hook script as a process on `payload`, with the attendance signals cleared first.
 * @param {string} script the file under `js/hooks`
 * @param {string[]} args
 * @param {unknown} payload
 * @param {Record<string, string>} [env]
 * @param {string} [cwd]
 */
function run(script, args, payload, env = {}, cwd = process.cwd()) {
  const result = spawnSync("node", [posix.join(HOOKS, script), ...args], {
    input: JSON.stringify(payload),
    cwd,
    env: {
      ...process.env,
      CLAUDE_CODE_SESSION_ATTENDED: "",
      AKMON_ACTOR: "",
      AKMON_SECOND_OPINION: "",
      AKMON_DELEGATION_GRACE: "",
      ...env,
    },
    encoding: "utf8",
  });
  return { stdout: result.stdout, stderr: result.stderr, status: result.status };
}

/**
 * A scratch project; `roster` adds a development agent charter.
 * @param {{roster: boolean}} options
 * @param {(project: string, tmp: string) => void} body
 */
function withProject({ roster }, body) {
  const project = tempDir("akmon-audience-hooks-");
  fs.mkdirSync(posix.join(project, "_aitna"));
  fs.mkdirSync(posix.join(project, "tmp"));
  fs.writeFileSync(posix.join(project, "AGENTS.md"), "# a\n");
  fs.writeFileSync(posix.join(project, "_aitna/.akmon.toml"), 'mount = "package"\n');
  if (roster) {
    fs.mkdirSync(posix.join(project, "_aitna/agents/engineer"), { recursive: true });
    fs.writeFileSync(posix.join(project, "_aitna/agents/engineer/README.md"), "e\n");
  }
  body(project, posix.join(project, "tmp"));
}

/**
 * The `additionalContext` of the one hook document `stdout` holds.
 * @param {string} stdout
 * @param {string} eventName
 * @returns {string}
 */
function contextOf(stdout, eventName) {
  const output = JSON.parse(stdout).hookSpecificOutput;
  assert.equal(output.hookEventName, eventName);
  return output.additionalContext;
}

/** The two session-start carriers: Claude's entry point and Codex's route. */
const CARRIERS = /** @type {Array<[string, string, string[]]>} */ ([
  ["Claude session-start-agent", "session-start-agent.mjs", []],
  ["Codex session-start route", "codex-hook.mjs", ["session-start"]],
]);

for (const [label, script, args] of CARRIERS) {
  test(`${label}: a project with no agent roster still gets the head layer, on every source (M246)`, () => {
    withProject({ roster: false }, (project, tmp) => {
      for (const source of SOURCES) {
        const result = run(script, args, { session_id: "s1", source, cwd: project }, { TMPDIR: tmp });
        assert.equal(result.stderr, "", source);
        assert.equal(contextOf(result.stdout, "SessionStart"), HEAD, source);
      }
    });
  });

  test(`${label}: with a roster the layer follows the roster lines, on every source`, () => {
    withProject({ roster: true }, (project, tmp) => {
      for (const source of SOURCES) {
        const context = contextOf(
          run(script, args, { session_id: "s1", source, cwd: project }, { TMPDIR: tmp }).stdout,
          "SessionStart",
        );
        assert.ok(context.startsWith(ROSTER_LINE), source);
        assert.ok(context.endsWith(`\n${HEAD}`), source);
      }
    });
  });

  test(`${label}: each unattended signal gives the unattended layer, the attended values the head layer`, () => {
    withProject({ roster: false }, (project, tmp) => {
      /** @type {Array<[Record<string, string>, boolean]>} */
      const cases = [
        [{}, true],
        [{ CLAUDE_CODE_SESSION_ATTENDED: "1" }, true],
        [{ AKMON_ACTOR: "developer" }, true],
        [{ AKMON_ACTOR: "autonomous" }, false],
        [{ CLAUDE_CODE_SESSION_ATTENDED: "0" }, false],
        [{ AKMON_SECOND_OPINION: "1" }, false],
      ];
      for (const [env, attended] of cases) {
        const result = run(
          script,
          args,
          { session_id: "s1", source: "compact", cwd: project },
          { TMPDIR: tmp, ...env },
        );
        assert.equal(contextOf(result.stdout, "SessionStart"), attended ? HEAD : UNATTENDED, JSON.stringify(env));
      }
    });
  });
}

test("Claude session-start-agent: the layer comes from the payload's cwd, or CLAUDE_PROJECT_DIR", () => {
  withProject({ roster: false }, (project, tmp) => {
    const result = run("session-start-agent.mjs", [], {}, { TMPDIR: tmp, CLAUDE_PROJECT_DIR: project });
    assert.equal(contextOf(result.stdout, "SessionStart"), HEAD);
  });
});

test("SubagentStart on Claude: the unattended layer, for an attended session too (M247)", () => {
  withProject({ roster: true }, (project, tmp) => {
    for (const env of /** @type {Array<Record<string, string>>} */ ([
      {},
      { CLAUDE_CODE_SESSION_ATTENDED: "1" },
      { AKMON_ACTOR: "autonomous" },
    ])) {
      const result = run(
        "subagent-start.mjs",
        [],
        { hook_event_name: "SubagentStart", agent_id: "a1", agent_type: "k_explorer", cwd: project },
        { TMPDIR: tmp, ...env },
      );
      assert.equal(result.status, 0);
      assert.equal(result.stderr, "");
      assert.deepEqual(Object.keys(JSON.parse(result.stdout)), ["hookSpecificOutput"]);
      assert.equal(contextOf(result.stdout, "SubagentStart"), UNATTENDED);
    }
  });
});

test("SubagentStart on Claude: an unreadable payload still delivers the layer, and a crash never blocks the start", () => {
  const empty = spawnSync("node", [posix.join(HOOKS, "subagent-start.mjs")], {
    input: "not json",
    encoding: "utf8",
    env: process.env,
  });
  assert.equal(empty.status, 0);
  assert.equal(contextOf(empty.stdout, "SubagentStart"), UNATTENDED);
});

test("SubagentStart on Codex: the route prints the unattended layer, never a systemMessage (M250)", () => {
  withProject({ roster: true }, (project, tmp) => {
    const result = run(
      "codex-hook.mjs",
      ["subagent-start"],
      { hook_event_name: "SubagentStart", agent_id: "a1", cwd: project },
      { TMPDIR: tmp },
    );
    assert.equal(result.status, 0);
    assert.equal(result.stderr, "");
    assert.deepEqual(Object.keys(JSON.parse(result.stdout)), ["hookSpecificOutput"]);
    assert.equal(contextOf(result.stdout, "SubagentStart"), UNATTENDED);
  });
});

/** A Claude edit payload for `file` in `session`, from the head or, with an `agent_id`, a delegate. */
function claudeEdit(
  /** @type {string} */ project,
  /** @type {string} */ file,
  /** @type {string} */ session,
  /** @type {string | undefined} */ agent,
) {
  return {
    tool_name: "Edit",
    session_id: session,
    cwd: project,
    tool_input: { file_path: `${project}/${file}` },
    ...(agent === undefined ? {} : { agent_id: agent, agent_type: "k_implementer" }),
  };
}

for (const [script, file, speaks] of /** @type {Array<[string, string, RegExp]>} */ ([
  ["role-on-code.mjs", "src/a.py", /Role check/],
  ["analysis-guard.mjs", "_aitna/TASKS.md", /Analysis-before-mutation check/],
])) {
  test(`${script}: a subagent's call is exempt and does not spend the head's once-per-session marker (C28d)`, () => {
    withProject({ roster: true }, (project, tmp) => {
      const env = { TMPDIR: tmp };
      const delegate = run(script, [], claudeEdit(project, file, "s1", "agent-1"), env);
      assert.equal(delegate.status, 0);
      assert.equal(delegate.stdout, "");
      assert.equal(delegate.stderr, "");
      assert.match(run(script, [], claudeEdit(project, file, "s1", undefined), env).stdout, speaks);
      assert.equal(run(script, [], claudeEdit(project, file, "s1", undefined), env).stdout, "");
    });
  });

  test(`${script}: an empty agent_id is not a subagent`, () => {
    withProject({ roster: true }, (project, tmp) => {
      assert.match(run(script, [], claudeEdit(project, file, "s2", ""), { TMPDIR: tmp }).stdout, speaks);
    });
  });
}

/** A Codex apply_patch payload adding `file`, from the head or, with an `agent_id`, a child. */
function codexPatch(
  /** @type {string} */ project,
  /** @type {string} */ file,
  /** @type {string} */ session,
  /** @type {string | undefined} */ agent,
) {
  return {
    tool_name: "apply_patch",
    session_id: session,
    cwd: project,
    tool_input: { command: `*** Begin Patch\n*** Add File: ${file}\n+x = 1\n*** End Patch\n` },
    ...(agent === undefined ? {} : { agent_id: agent, agent_type: "default" }),
  };
}

for (const [route, file, speaks] of /** @type {Array<[string, string, RegExp]>} */ ([
  ["role-on-code", "src/mod.py", /Role check/],
  ["analysis-guard", "_aitna/TASKS.md", /Analysis-before-mutation check/],
])) {
  test(`Codex ${route} route: a child's call (agent_id) is exempt and the head's marker stays unspent (M192)`, () => {
    withProject({ roster: true }, (project, tmp) => {
      const env = { TMPDIR: tmp };
      const child = run("codex-hook.mjs", [route], codexPatch(project, file, "s1", "child-1"), env);
      assert.equal(child.status, 0);
      assert.equal(child.stdout, "");
      assert.equal(child.stderr, "");
      const head = run("codex-hook.mjs", [route], codexPatch(project, file, "s1", undefined), env);
      assert.match(contextOf(head.stdout, "PreToolUse"), speaks);
    });
  });
}

/**
 * Run the Codex `spawn-guard` route on a spawn whose input is `toolInput`.
 * @param {unknown} toolInput
 */
function spawn(toolInput) {
  return run("codex-hook.mjs", ["spawn-guard"], {
    tool_name: "collaborationspawn_agent",
    session_id: "s",
    cwd: TREE_ROOT,
    tool_input: toolInput,
  });
}

for (const forkTurns of ["all", "1", "", undefined, 3]) {
  test(`spawn-guard: fork_turns ${JSON.stringify(forkTurns)} is rewritten to none and every other field survives (M257)`, () => {
    const original = { task_name: "explore", message: "find it — «ünï»\n", extra: { a: [1, 2.5, null, true] } };
    const sent = forkTurns === undefined ? original : { ...original, fork_turns: forkTurns };
    const result = spawn(sent);
    assert.equal(result.status, 0);
    assert.equal(result.stderr, "");
    const document = JSON.parse(result.stdout);
    const updated = document.hookSpecificOutput.updatedInput;
    assert.deepEqual(document, {
      hookSpecificOutput: { hookEventName: "PreToolUse", permissionDecision: "allow", updatedInput: updated },
    });
    assert.equal(updated.fork_turns, "none");
    assert.deepEqual({ ...updated, fork_turns: undefined }, { ...original, fork_turns: undefined });
  });
}

test("spawn-guard: a missing fork_turns lands after the received fields and a present one keeps its place", () => {
  const added = JSON.parse(spawn({ task_name: "t", message: "m" }).stdout);
  assert.deepEqual(Object.keys(added.hookSpecificOutput.updatedInput), ["task_name", "message", "fork_turns"]);
  const kept = JSON.parse(spawn({ task_name: "t", fork_turns: "all", message: "m" }).stdout);
  assert.deepEqual(Object.keys(kept.hookSpecificOutput.updatedInput), ["task_name", "fork_turns", "message"]);
});

test("spawn-guard: a spawn that already says none passes untouched, and so does an input that is not an object", () => {
  for (const toolInput of [{ task_name: "t", fork_turns: "none", message: "m" }, null, [], "text", 7]) {
    const result = spawn(toolInput);
    assert.equal(result.status, 0);
    assert.equal(result.stdout, "");
    assert.equal(result.stderr, "");
  }
});

test("spawnForkResult: pure, never edits its input and carries the allow decision", async () => {
  const { spawnForkResult } = await import("./hook_core.mjs");
  const { lazyHookData } = await import("./hook_data.mjs");
  const data = lazyHookData();
  const received = { task_name: "t", fork_turns: "all", message: "m" };
  const result = spawnForkResult(data, received);
  assert.deepEqual(received, { task_name: "t", fork_turns: "all", message: "m" });
  assert.equal(result?.permissionDecision, "allow");
  assert.deepEqual(result?.updatedInput, { task_name: "t", fork_turns: "none", message: "m" });
  assert.equal(spawnForkResult(data, undefined), null);
});
