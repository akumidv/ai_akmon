import { test } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import { join } from "node:path";

import {
  SandboxError,
  SandboxUnavailableError,
  VerdictMissingError,
  checkCompiles,
  containerCommand,
  ensureAvailable,
  extractPythonBlock,
  failedTests,
  parseVerdict,
  runHiddenTest,
  tarStream,
} from "./sandbox.mjs";
import * as settings from "./settings.mjs";
import { hostCanFakeDocker, installFakeDocker, tempDir, withoutDocker } from "./support.test.mjs";

const SKIP_WITHOUT_HOST = hostCanFakeDocker() ? false : "the fake docker needs python3 and tar on PATH";

/**
 * @param {string[]} argv
 * @param {string} flag
 * @returns {string}
 */
const flagValue = (argv, flag) => argv[argv.indexOf(flag) + 1];

test("the container command pins the isolation flags", () => {
  const argv = containerCommand("model-profile-x", "tests/test_mod.py");
  const config = settings.load().sandbox;

  assert.deepEqual(argv.slice(0, 3), ["docker", "run", "--rm"]);
  assert.equal(flagValue(argv, "--network"), "none");
  assert.ok(argv.includes("--read-only"));
  assert.equal(flagValue(argv, "--memory"), "256m");
  assert.equal(flagValue(argv, "--pids-limit"), "128");
  assert.equal(flagValue(argv, "--cap-drop"), "ALL");
  assert.equal(flagValue(argv, "--security-opt"), "no-new-privileges");
  assert.equal(flagValue(argv, "--user"), "65534:65534");
  assert.equal(flagValue(argv, "--name"), "model-profile-x");
  const tmpfs = argv.filter((_token, index) => argv[index - 1] === "--tmpfs");
  assert.equal(tmpfs.length, 2);
  assert.ok(tmpfs.some((spec) => spec.startsWith("/tmp:") && spec.includes("noexec")));
  assert.ok(tmpfs.some((spec) => spec.startsWith("/work:")));
  assert.equal(argv[argv.indexOf(config.image) - 1], "/work");
  assert.ok(argv.includes("--interactive"));
});

test("the container command is the Python twin's argv, flag for flag", () => {
  const argv = containerCommand("n", "tests/test_mod.py");

  assert.deepEqual(argv, [
    "docker",
    "run",
    "--rm",
    "--interactive",
    "--name",
    "n",
    "--network",
    "none",
    "--read-only",
    "--tmpfs",
    "/tmp:rw,noexec,nosuid,size=64m",
    "--tmpfs",
    "/work:rw,size=64m,mode=1777",
    "--memory",
    "256m",
    "--pids-limit",
    "128",
    "--cap-drop",
    "ALL",
    "--security-opt",
    "no-new-privileges",
    "--user",
    "65534:65534",
    "--workdir",
    "/work",
    "python:3.13-slim",
    "sh",
    "-c",
    "tar -xf - -C /work --no-same-owner --no-same-permissions " +
      "&& exec python -B /work/_probe_runner.py tests/test_mod.py /work __MODEL_PROFILE_RESULT__",
  ]);
});

test("the container command mounts nothing from the host and grants nothing", () => {
  const argv = containerCommand("n", "t.py");
  const flags = new Set(argv.slice(0, argv.indexOf(settings.load().sandbox.image)));

  for (const forbidden of ["-v", "--volume", "--mount", "--privileged", "--network=host", "--pid", "--device"]) {
    assert.ok(!flags.has(forbidden), forbidden);
  }
  assert.notEqual(flagValue(argv, "--network"), "host");
});

test("the container command quotes the test path for the shell", () => {
  const argv = containerCommand("n", "tests/a b; rm -rf x.py");

  assert.ok(argv[argv.length - 1].includes("'tests/a b; rm -rf x.py'"));
});

/**
 * The names and the contents the system `tar` reads out of a stream.
 * @param {Buffer} archive
 * @returns {{names: string[], dir: string}}
 */
function untar(archive) {
  const dir = tempDir();
  const listed = spawnSync("tar", ["-tf", "-"], { input: archive });
  assert.equal(listed.status, 0, listed.stderr.toString());
  const extracted = spawnSync("tar", ["-xf", "-", "-C", dir, "--no-same-owner", "--no-same-permissions"], {
    input: archive,
  });
  assert.equal(extracted.status, 0, extracted.stderr.toString());
  return { names: listed.stdout.toString().split("\n").filter(Boolean).sort(), dir };
}

test(
  "the sandbox adds a runner and a nonce and refuses a case that carries those names",
  { skip: SKIP_WITHOUT_HOST },
  () => {
    const { names, dir } = untar(tarStream({ "a.py": "x = 1\n" }, "n0nce"));

    assert.deepEqual(names, ["_probe_nonce", "_probe_runner.py", "a.py"]);
    assert.equal(fs.readFileSync(join(dir, "_probe_nonce"), "utf8"), "n0nce");
    assert.equal(fs.readFileSync(join(dir, "_probe_runner.py"), "utf8"), settings.runnerSource());
    for (const reserved of [settings.load().sandbox.runnerFile, settings.load().sandbox.nonceFile]) {
      assert.throws(() => tarStream({ [reserved]: "x" }, "n"), /reserves/);
    }
  },
);

test("a tar stream carries non-ASCII sources and long paths intact", { skip: SKIP_WITHOUT_HOST }, () => {
  const long = `${"d".repeat(60)}/${"e".repeat(60)}/module.py`;
  const files = { "café.py": "x = '\u{1F600}'\n", [long]: "y = 2\n", "sp ace/a.py": "z = 3\n" };

  const { names, dir } = untar(tarStream(files, "n"));

  assert.deepEqual(names, [...Object.keys(files), "_probe_nonce", "_probe_runner.py"].sort());
  for (const [path, source] of Object.entries(files)) {
    assert.equal(fs.readFileSync(join(dir, path), "utf8"), source, path);
  }
  assert.throws(() => tarStream({ [`${"d".repeat(300)}.py`]: "x" }, "n"), /too long/);
});

test("a tar stream is a whole number of records, ended by two empty blocks", () => {
  const archive = tarStream({ "a.py": "x" }, "n");

  assert.equal(archive.length % 10240, 0);
  assert.ok(archive.subarray(archive.length - 1024).every((byte) => byte === 0));
});

/**
 * @param {string} nonce
 * @param {Record<string, string>} tests
 * @param {string | null} [error]
 * @returns {string}
 */
const verdictLine = (nonce, tests, error = null) =>
  `${settings.load().sandbox.resultPrefix} ${nonce} ${JSON.stringify({ tests, error })}`;

test("the verdict is the last line with this run's nonce", () => {
  const stdout = `noise\n${verdictLine("abc", { test_a: "passed", test_b: "failed" })}\n`;

  const verdict = parseVerdict(stdout, "abc");

  assert.deepEqual(verdict.tests, { test_a: "passed", test_b: "failed" });
  assert.equal(verdict.error, null);
});

/** @type {[string, string][]} */
const NOT_VERDICTS = [
  ["empty", ""],
  ["no marker", "no marker at all\n"],
  ["wrong nonce", `${verdictLine("someone-elses-guess", { test_a: "passed" })}\n`],
  ["not last", `${verdictLine("abc", { test_a: "passed" })}\ntrailing noise\n`],
  ["glued", `glued ${verdictLine("abc", { test_a: "passed" })}\n`],
  ["bad json", `${settings.load().sandbox.resultPrefix} abc not-json\n`],
  [
    "bad outcome",
    `${settings.load().sandbox.resultPrefix} abc ${JSON.stringify({ tests: { test_a: "maybe" }, error: null })}\n`,
  ],
  ["not an object", `${settings.load().sandbox.resultPrefix} abc ${JSON.stringify(["tests"])}\n`],
  ["tests an array", `${settings.load().sandbox.resultPrefix} abc ${JSON.stringify({ tests: [], error: null })}\n`],
  ["error a number", `${settings.load().sandbox.resultPrefix} abc ${JSON.stringify({ tests: {}, error: 3 })}\n`],
];

for (const [name, stdout] of NOT_VERDICTS) {
  test(`a forged or misplaced verdict line is not a verdict: ${name}`, () => {
    assert.throws(() => parseVerdict(stdout, "abc"), VerdictMissingError);
  });
}

/**
 * Run the in-container runner with the host interpreter in a temporary work directory.
 * @param {Record<string, string>} files
 * @param {string} [nonce]
 * @returns {{stdout: string, work: string}}
 */
function runRunner(files, nonce = "run-nonce") {
  const { dir } = untar(tarStream(files, nonce));
  const done = spawnSync(
    "python3",
    ["-B", join(dir, "_probe_runner.py"), "test_prog.py", dir, settings.load().sandbox.resultPrefix],
    { cwd: dir, encoding: "utf8", timeout: 60000 },
  );
  return { stdout: done.stdout, work: dir };
}

const FORGER =
  "import sys\n" +
  `forged = '${"__MODEL_PROFILE_RESULT__"} guess {"tests": {"test_x": "passed"}, "error": null}'\n` +
  "print(forged)\nprint(forged, end='')\nsys.stdout.write(forged)\n" +
  "sys.__stdout__.write(forged)  # straight to the real stdout, no newline after it\n" +
  "def f():\n    return 1\n";

test("a program that prints a fake verdict cannot change the real one", { skip: SKIP_WITHOUT_HOST }, () => {
  const { stdout } = runRunner({
    "prog.py": FORGER,
    "test_prog.py": "from prog import f\n\ndef test_x():\n    assert f() == 2\n",
  });

  assert.ok(stdout.includes("guess"), "the forgery did reach the real stdout");
  assert.deepEqual(parseVerdict(stdout, "run-nonce").tests, { test_x: "failed" });
});

test("the runner reports passes and failures per test function", { skip: SKIP_WITHOUT_HOST }, () => {
  const { stdout } = runRunner({
    "prog.py": "def f():\n    return 2\n",
    "test_prog.py":
      "from prog import f\n\ndef test_ok():\n    assert f() == 2\n\ndef test_bad():\n    assert f() == 3\n",
  });

  assert.deepEqual(parseVerdict(stdout, "run-nonce").tests, { test_ok: "passed", test_bad: "failed" });
});

test("the runner reports a collection error", { skip: SKIP_WITHOUT_HOST }, () => {
  const { stdout } = runRunner({ "prog.py": "x = 1\n", "test_prog.py": "import prog\nraise RuntimeError('boom')\n" });

  const verdict = parseVerdict(stdout, "run-nonce");

  assert.deepEqual(verdict.tests, {});
  assert.match(verdict.error ?? "", /boom/);
});

test("the runner deletes the nonce file before it imports anything of the model's", { skip: SKIP_WITHOUT_HOST }, () => {
  const { stdout, work } = runRunner({
    "prog.py": "import pathlib\nassert not pathlib.Path('_probe_nonce').exists()\n",
    "test_prog.py": "import prog\n\ndef test_ok():\n    pass\n",
  });

  assert.deepEqual(parseVerdict(stdout, "run-nonce").tests, { test_ok: "passed" });
  assert.ok(!fs.existsSync(join(work, "_probe_nonce")));
});

test("a program that kills the runner earns no verdict", { skip: SKIP_WITHOUT_HOST }, () => {
  const { stdout } = runRunner({
    "prog.py": "import os\nos._exit(0)\n",
    "test_prog.py": "import prog\n\ndef test_x():\n    pass\n",
  });

  assert.throws(() => parseVerdict(stdout, "run-nonce"), VerdictMissingError);
});

test("docker missing is a refusal, not a fallback", () => {
  withoutDocker(() => {
    assert.throws(
      () => ensureAvailable(),
      (exc) => exc instanceof SandboxUnavailableError && /docker is not on the PATH/.test(exc.message),
    );
    assert.throws(() => runHiddenTest({ "a.py": "x" }, "t.py"), SandboxUnavailableError);
    assert.throws(() => checkCompiles("x = 1\n"), SandboxUnavailableError);
  });
});

const HIDDEN_TEST = "from prog import f\n\ndef test_x():\n    assert f() == 2\n";

test("a hidden test runs against the files and passes or fails per function", { skip: SKIP_WITHOUT_HOST }, () => {
  const restore = installFakeDocker();
  try {
    const passing = runHiddenTest({ "prog.py": "def f():\n    return 2\n" }, "test_prog.py", {
      extraFiles: { "test_prog.py": HIDDEN_TEST },
    });
    const failing = runHiddenTest({ "prog.py": "def f():\n    return 1\n" }, "test_prog.py", {
      extraFiles: { "test_prog.py": HIDDEN_TEST },
    });

    assert.ok(passing.passed);
    assert.deepEqual(passing.tests, { test_x: "passed" });
    assert.ok(!failing.passed);
    assert.deepEqual(failedTests(failing), ["test_x"]);
  } finally {
    restore();
  }
});

test(
  "a run the program ended without a verdict is a failed result, not a sandbox error",
  { skip: SKIP_WITHOUT_HOST },
  () => {
    const restore = installFakeDocker();
    try {
      const result = runHiddenTest({ "prog.py": "import os\nos._exit(0)\n" }, "test_prog.py", {
        extraFiles: { "test_prog.py": "import prog\n\ndef test_x():\n    pass\n" },
      });

      assert.ok(!result.passed);
      assert.match(result.stderr ?? "", /no verdict/);
    } finally {
      restore();
    }
  },
);

test("a run that outlasts its limit is a timed-out failure", { skip: SKIP_WITHOUT_HOST }, () => {
  const restore = installFakeDocker();
  try {
    const result = runHiddenTest({ "prog.py": "import time\ntime.sleep(4)\n" }, "test_prog.py", {
      timeoutS: 1,
      extraFiles: { "test_prog.py": "import prog\n\ndef test_x():\n    pass\n" },
    });

    assert.ok(!result.passed);
    assert.ok(result.timedOut);
    assert.match(result.stderr ?? "", /exceeded its 1s limit/);
  } finally {
    restore();
  }
});

test("the compile check answers from the interpreter and never runs the source", { skip: SKIP_WITHOUT_HOST }, () => {
  const restore = installFakeDocker();
  try {
    assert.deepEqual(checkCompiles("def f():\n    return 1\n"), { compiled: true, detail: "" });
    const broken = checkCompiles("def broken(:\n");
    assert.ok(!broken.compiled);
    assert.match(broken.detail, /invalid syntax|expected/);
    const marker = join(tempDir(), "ran");
    assert.ok(checkCompiles(`open(${JSON.stringify(marker)}, "w")\n`).compiled);
    assert.ok(!fs.existsSync(marker), "the source was parsed, not executed");
  } finally {
    restore();
  }
});

test(
  "a verdict with every test passing is a pass; an empty one or a collection error is not",
  { skip: SKIP_WITHOUT_HOST },
  () => {
    const restore = installFakeDocker();
    try {
      const empty = runHiddenTest({ "prog.py": "x = 1\n" }, "test_prog.py", {
        extraFiles: { "test_prog.py": "import prog\n" },
      });
      const broken = runHiddenTest({ "prog.py": "x = 1\n" }, "test_prog.py", {
        extraFiles: { "test_prog.py": "import prog\nraise RuntimeError('boom')\n" },
      });

      assert.ok(!empty.passed);
      assert.ok(!broken.passed);
      assert.match(broken.stderr ?? "", /boom/);
    } finally {
      restore();
    }
  },
);

test("docker failing is a sandbox error, whatever the program did", { skip: SKIP_WITHOUT_HOST }, () => {
  const directory = tempDir();
  fs.writeFileSync(
    join(directory, "docker"),
    "#!/bin/sh\n[ \"$1\" = version ] && exit 0\necho 'docker: daemon error' >&2\nexit 125\n",
    {
      mode: 0o755,
    },
  );
  const saved = process.env.PATH;
  process.env.PATH = `${directory}:${saved}`;
  try {
    assert.throws(
      () =>
        runHiddenTest({ "prog.py": "x = 1\n" }, "test_prog.py", { extraFiles: { "test_prog.py": "import prog\n" } }),
      (exc) => exc instanceof SandboxError && /exit code 125/.test(exc.message),
    );
  } finally {
    process.env.PATH = saved;
  }
});

test("extractPythonBlock wants exactly one fence", () => {
  assert.equal(extractPythonBlock("x\n```python\na = 1\n```\n"), "a = 1\n");
  assert.equal(extractPythonBlock("```python\na\n```\n```python\nb\n```\n"), null);
  assert.equal(extractPythonBlock("none"), null);
});
