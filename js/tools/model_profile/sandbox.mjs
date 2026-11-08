/**
 * The execution sandbox: model-written Python runs in a container, or not at all — the JavaScript
 * twin of `tools/model_profile/sandbox.py` (ADR 0020 D01); the Python module is the reference, and
 * the `docker run` argv is the same flag for flag.
 *
 * The suite grades answers by running them, so the code a model writes is untrusted input that
 * happens to be executable. The container (the image and every limit are in `profile.json`) has no
 * network, a read-only filesystem, tmpfs for `/tmp` and the work directory, a memory and a process
 * limit, no capabilities, an unprivileged user and no host mount: the case's files travel in as a
 * tar stream over stdin. `containerCommand` builds the one argv that carries these flags; a test
 * pins it.
 *
 * Docker being unavailable is a refusal, never a fallback. The verdict cannot be forged by the code
 * under test: the in-container runner (`container_runner.py.txt`, the same file the Python twin
 * ships) is handed a per-run random nonce in a file it deletes before it imports anything of the
 * model's, and the host accepts only the last stdout line, only with that nonce.
 *
 * Twin note: the Python twin checks that a fix compiles with `ast.parse` on the host; this twin has
 * no Python parser, so `checkCompiles` asks the same container image (no network, no files, the
 * source on stdin, nothing executed) and quotes that interpreter's message.
 */

import { spawnSync } from "node:child_process";
import { randomBytes, randomUUID } from "node:crypto";

import { shlexJoin } from "../../common/shlex.mjs";
import { codePointSort } from "../../common/sort.mjs";
import * as settings from "./settings.mjs";

/** The tar record size Python's `tarfile` pads an archive to. */
const TAR_RECORD_SIZE = 10240;
const TAR_BLOCK_SIZE = 512;
/** The most output a sandboxed run may produce before the host stops reading it. */
const MAX_OUTPUT_BYTES = 64 * 1024 * 1024;

/** The compile check's program: reads the source on stdin, prints the interpreter's message on a failure. */
const COMPILE_CHECK_SOURCE = [
  "import ast, sys",
  "try:",
  "    ast.parse(sys.stdin.read())",
  "except (SyntaxError, ValueError) as exc:",
  "    print(exc)",
  "    sys.exit(1)",
].join("\n");

/** The container runtime is missing or unusable — the run is refused, never downgraded. */
export class SandboxUnavailableError extends Error {
  /** @param {string} message */
  constructor(message) {
    super(message);
    this.name = "SandboxUnavailableError";
  }
}

/** The sandbox could not run the code at all — the attempt is not a model's failure. */
export class SandboxError extends Error {
  /** @param {string} message */
  constructor(message) {
    super(message);
    this.name = "SandboxError";
  }
}

/** The run's stdout carries no verdict line with this run's nonce. */
export class VerdictMissingError extends Error {
  /** @param {string} message */
  constructor(message) {
    super(message);
    this.name = "VerdictMissingError";
  }
}

/**
 * What one sandboxed run produced. `passed` is the whole verdict the graders need; `tests` keeps
 * the per-function breakdown, and `timedOut` separates a slow answer from a wrong one.
 * @typedef {object} SandboxResult
 * @property {boolean} passed
 * @property {Record<string, string>} [tests]
 * @property {string} [stdout]
 * @property {string} [stderr]
 * @property {number} [exitCode]
 * @property {boolean} [timedOut]
 * @property {number} [durationS]
 */

/**
 * What the grader needs from a sandbox run: the program's files, the hidden test's path and the
 * test's own source.
 * @typedef {(files: Record<string, string>, testPath: string, testSource: string) => SandboxResult} TestRunner
 */

/**
 * What the in-container runner reported.
 * @typedef {object} Verdict
 * @property {Record<string, string>} tests
 * @property {string | null} error
 */

/**
 * The names of the hidden-test functions that failed.
 * @param {SandboxResult} result
 * @returns {string[]}
 */
export function failedTests(result) {
  return codePointSort(
    Object.entries(result.tests ?? {})
      .filter(([, outcome]) => outcome !== "passed")
      .map(([name]) => name),
  );
}

/**
 * Throw `SandboxUnavailableError` unless a container runtime can run the suite. The check is the
 * runtime's own answer, not a guess from a binary on the path.
 * @throws {SandboxUnavailableError}
 */
export function ensureAvailable() {
  const config = settings.load().sandbox;
  const completed = spawnSync("docker", ["version", "--format", "{{.Server.Version}}"], {
    encoding: "utf8",
    timeout: config.dockerCommandTimeoutS * 1000,
    killSignal: "SIGKILL",
  });
  if (completed.error !== undefined) {
    const code = /** @type {NodeJS.ErrnoException} */ (completed.error).code;
    if (code === "ENOENT") {
      throw new SandboxUnavailableError(
        "docker is not on the PATH: model-written code is only ever run in a container, " +
          "never on the host, so the probe is refused rather than downgraded",
      );
    }
    throw new SandboxUnavailableError(`docker could not be reached: ${completed.error.message}`);
  }
  if (completed.status !== 0) {
    const detail = (completed.stderr || completed.stdout || "").trim().slice(0, config.detailChars);
    throw new SandboxUnavailableError(`docker is installed but its daemon is not usable: ${detail}`);
  }
}

/**
 * A path as the ustar header's two fields: the directory prefix (at most 155 bytes) and the name
 * (at most 100 bytes), split at a slash only when the path does not fit the name field.
 * @param {string} path
 * @returns {[Buffer, Buffer]} the prefix and the name
 * @throws {SandboxError} the path fits neither field
 */
function splitTarPath(path) {
  const whole = Buffer.from(path, "utf8");
  if (whole.length <= 100) {
    return [Buffer.alloc(0), whole];
  }
  for (let split = path.indexOf("/"); split !== -1; split = path.indexOf("/", split + 1)) {
    const head = Buffer.from(path.slice(0, split), "utf8");
    const tail = Buffer.from(path.slice(split + 1), "utf8");
    if (tail.length <= 100) {
      if (head.length <= 155) {
        return [head, tail];
      }
      break;
    }
  }
  throw new SandboxError(`a file path is too long for the tar stream: ${path}`);
}

/**
 * One file as a ustar entry: a 512-byte header, the payload, padding to the block size.
 * @param {string} path
 * @param {Buffer} payload
 * @returns {Buffer}
 */
function tarEntry(path, payload) {
  const [prefix, name] = splitTarPath(path);
  const header = Buffer.alloc(TAR_BLOCK_SIZE);
  name.copy(header, 0);
  header.write("0000644\0", 100, "latin1");
  header.write("0000000\0", 108, "latin1");
  header.write("0000000\0", 116, "latin1");
  header.write(`${payload.length.toString(8).padStart(11, "0")}\0`, 124, "latin1");
  header.write("00000000000\0", 136, "latin1");
  header.write("        ", 148, "latin1");
  header.write("0", 156, "latin1");
  header.write("ustar\0", 257, "latin1");
  header.write("00", 263, "latin1");
  prefix.copy(header, 345);
  const checksum = header.reduce((sum, byte) => sum + byte, 0);
  header.write(`${checksum.toString(8).padStart(6, "0")}\0 `, 148, "latin1");
  const padding = Buffer.alloc((TAR_BLOCK_SIZE - (payload.length % TAR_BLOCK_SIZE)) % TAR_BLOCK_SIZE);
  return Buffer.concat([header, payload, padding]);
}

/**
 * The case's files as a tar stream, with the in-container runner and the nonce beside them.
 * @param {Record<string, string>} files
 * @param {string} nonce
 * @returns {Buffer}
 * @throws {SandboxError} the case carries a file named like one the sandbox adds itself
 */
export function tarStream(files, nonce) {
  const config = settings.load().sandbox;
  const reserved = codePointSort([config.runnerFile, config.nonceFile].filter((name) => Object.hasOwn(files, name)));
  if (reserved.length > 0) {
    throw new SandboxError(`the case carries a file the sandbox reserves: ${reserved.join(", ")}`);
  }
  const entries = codePointSort(Object.keys(files)).map((path) => tarEntry(path, Buffer.from(files[path], "utf8")));
  entries.push(tarEntry(config.runnerFile, Buffer.from(settings.runnerSource(), "utf8")));
  entries.push(tarEntry(config.nonceFile, Buffer.from(nonce, "utf8")));
  const body = Buffer.concat([...entries, Buffer.alloc(TAR_BLOCK_SIZE * 2)]);
  const rounded = Math.ceil(body.length / TAR_RECORD_SIZE) * TAR_RECORD_SIZE;
  return Buffer.concat([body, Buffer.alloc(rounded - body.length)]);
}

/**
 * The `docker run` flags — the isolation envelope, in one place — up to and including the image.
 * @param {string} name
 * @returns {string[]}
 */
function dockerFlags(name) {
  const config = settings.load().sandbox;
  return [
    "docker",
    "run",
    "--rm",
    "--interactive",
    "--name",
    name,
    "--network",
    "none",
    "--read-only",
    "--tmpfs",
    `/tmp:rw,noexec,nosuid,size=${config.workspaceSize}`,
    "--tmpfs",
    `${config.workDir}:rw,size=${config.workspaceSize},mode=1777`,
    "--memory",
    config.memoryLimit,
    "--pids-limit",
    config.pidsLimit,
    "--cap-drop",
    "ALL",
    "--security-opt",
    "no-new-privileges",
    "--user",
    config.containerUser,
    "--workdir",
    config.workDir,
    config.image,
  ];
}

/**
 * The `docker run` invocation that runs the hidden test: the isolation envelope, in one place.
 * @param {string} name
 * @param {string} testPath
 * @returns {string[]}
 */
export function containerCommand(name, testPath) {
  const config = settings.load().sandbox;
  const script =
    `tar -xf - -C ${config.workDir} --no-same-owner --no-same-permissions ` +
    `&& exec python -B ${config.workDir}/${config.runnerFile} ${shlexJoin([testPath])} ${config.workDir} ${config.resultPrefix}`;
  return [...dockerFlags(name), "sh", "-c", script];
}

/**
 * The runner's verdict: the last line of `stdout`, accepted only with this run's nonce.
 * @param {string} stdout
 * @param {string} nonce
 * @returns {Verdict}
 * @throws {VerdictMissingError} the last line is not a verdict line carrying `nonce`, or its JSON is not a verdict
 */
export function parseVerdict(stdout, nonce) {
  const lines = stdout.replace(/[\r\n]+$/, "").split("\n");
  const last = lines[lines.length - 1];
  const head = `${settings.load().sandbox.resultPrefix} ${nonce} `;
  if (!last.startsWith(head)) {
    throw new VerdictMissingError("the last line of stdout is not this run's verdict line");
  }
  let payload;
  try {
    payload = JSON.parse(last.slice(head.length));
  } catch (exc) {
    throw new VerdictMissingError(`the verdict line is not valid JSON: ${/** @type {Error} */ (exc).message}`);
  }
  const verdict = verdictOf(payload);
  if (verdict === null) {
    throw new VerdictMissingError("the verdict line does not have the shape of a verdict");
  }
  return verdict;
}

/**
 * Whether a value is a JSON object (not an array, not null).
 * @param {unknown} value
 * @returns {value is Record<string, any>}
 */
function isObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

/**
 * The verdict a parsed payload carries, or `null` when it does not have the shape of one.
 * @param {unknown} payload
 * @returns {Verdict | null}
 */
function verdictOf(payload) {
  if (!isObject(payload) || !isObject(payload.tests)) {
    return null;
  }
  const error = payload.error ?? null;
  const wellFormed = Object.values(payload.tests).every((outcome) => outcome === "passed" || outcome === "failed");
  if (!wellFormed || !(error === null || typeof error === "string")) {
    return null;
  }
  return { tests: { ...payload.tests }, error };
}

/**
 * Remove a container left behind by a timed-out run — best effort, never fatal.
 * @param {string} name
 */
function removeContainer(name) {
  spawnSync("docker", ["rm", "--force", name], {
    encoding: "utf8",
    timeout: settings.load().sandbox.dockerCommandTimeoutS * 1000,
    killSignal: "SIGKILL",
  });
}

/**
 * Run one `docker run` argv with `input` on stdin under a wall-clock limit.
 * @param {string[]} argv
 * @param {Buffer | string} input
 * @param {number} timeoutS
 * @returns {import("node:child_process").SpawnSyncReturns<Buffer>}
 */
function runDocker(argv, input, timeoutS) {
  return spawnSync(argv[0], argv.slice(1), {
    input,
    timeout: timeoutS * 1000,
    killSignal: "SIGKILL",
    maxBuffer: MAX_OUTPUT_BYTES,
  });
}

/**
 * Run the hidden test at `testPath` against `files` inside the container. `extraFiles` (the hidden
 * test itself) is added to the workspace under its own path.
 *
 * A run that ends without a verdict because the program ended it (a crash, an out-of-memory kill,
 * an `os._exit`) is a failed result; one that ends without a verdict because docker failed is a
 * `SandboxError`.
 * @param {Record<string, string>} files
 * @param {string} testPath
 * @param {{timeoutS?: number | null, extraFiles?: Record<string, string>}} [options]
 * @returns {SandboxResult}
 * @throws {SandboxUnavailableError} no usable container runtime
 * @throws {SandboxError} the container could not be started or docker itself failed
 */
export function runHiddenTest(files, testPath, { timeoutS = null, extraFiles = {} } = {}) {
  ensureAvailable();
  const limit = timeoutS ?? settings.load().sandbox.defaultTimeoutS;
  const nonce = randomBytes(16).toString("hex");
  const name = containerName();
  const payload = tarStream({ ...files, ...extraFiles }, nonce);
  const started = performance.now();
  const completed = runDocker(containerCommand(name, testPath), payload, limit);
  const durationS = (performance.now() - started) / 1000;
  const code = /** @type {NodeJS.ErrnoException | undefined} */ (completed.error)?.code;
  if (code === "ETIMEDOUT") {
    removeContainer(name);
    return {
      passed: false,
      stdout: decode(completed.stdout),
      stderr: `the sandboxed run exceeded its ${limit}s limit`,
      exitCode: -1,
      timedOut: true,
      durationS,
    };
  }
  // A pipe closed before the stream was read (docker refusing at once) or too much output is the run's
  // own ending, as in the Python twin (`subprocess.run` ignores `BrokenPipeError`): the verdict decides.
  if (completed.error !== undefined && code !== "ENOBUFS" && code !== "EPIPE") {
    throw new SandboxError(`the sandbox could not be started: ${completed.error.message}`);
  }
  return resultOf(completed, nonce, durationS);
}

/**
 * A fresh container name, so a run killed by its own timeout can be removed.
 * @returns {string}
 */
function containerName() {
  return `model-profile-${randomUUID().replaceAll("-", "").slice(0, 12)}`;
}

/**
 * A captured stream as text.
 * @param {Buffer | null | undefined} buffer
 * @returns {string}
 */
function decode(buffer) {
  return buffer ? buffer.toString("utf8") : "";
}

/**
 * What a finished run printed and how it ended.
 * @typedef {object} RunOutput
 * @property {string} stdout
 * @property {string} stderr
 * @property {number} exitCode
 * @property {number} durationS
 */

/**
 * The result of a finished container run — a missing verdict is the program's, unless docker failed.
 * @param {import("node:child_process").SpawnSyncReturns<Buffer>} completed
 * @param {string} nonce
 * @param {number} durationS
 * @returns {SandboxResult}
 */
function resultOf(completed, nonce, durationS) {
  /** @type {RunOutput} */
  const output = {
    stdout: decode(completed.stdout),
    stderr: decode(completed.stderr),
    exitCode: completed.status ?? -1,
    durationS,
  };
  let verdict;
  try {
    verdict = parseVerdict(output.stdout, nonce);
  } catch (exc) {
    return withoutVerdict(exc, output);
  }
  const outcomes = Object.values(verdict.tests);
  return {
    passed: outcomes.length > 0 && verdict.error === null && outcomes.every((outcome) => outcome === "passed"),
    tests: verdict.tests,
    ...output,
    stderr: verdict.error === null ? output.stderr : `${output.stderr}\n${verdict.error}`.trim(),
  };
}

/**
 * The result of a run that printed no verdict: the program's failure, unless docker itself failed.
 * @param {unknown} exc
 * @param {RunOutput} output
 * @returns {SandboxResult}
 * @throws {SandboxError} docker failed
 */
function withoutVerdict(exc, output) {
  if (!(exc instanceof VerdictMissingError)) {
    throw exc;
  }
  const config = settings.load().sandbox;
  if (config.dockerFailureCodes.includes(output.exitCode)) {
    const detail = (output.stderr || output.stdout).trim().slice(0, config.detailChars);
    throw new SandboxError(`the sandboxed run produced no verdict (exit code ${output.exitCode}): ${detail}`);
  }
  return {
    passed: false,
    stdout: output.stdout,
    stderr: `no verdict from the program's run (exit code ${output.exitCode}): ${output.stderr.trim().slice(0, config.detailChars)}`,
    exitCode: output.exitCode,
    durationS: output.durationS,
  };
}

/**
 * Whether `source` is a Python module that compiles, asked of the container's interpreter. The
 * source is parsed, never executed.
 * @param {string} source
 * @param {{timeoutS?: number | null}} [options]
 * @returns {{compiled: boolean, detail: string}} the interpreter's message when it does not compile
 * @throws {SandboxUnavailableError} no usable container runtime
 * @throws {SandboxError} docker itself failed
 */
export function checkCompiles(source, { timeoutS = null } = {}) {
  ensureAvailable();
  const name = containerName();
  const argv = [...dockerFlags(name), "python", "-B", "-c", COMPILE_CHECK_SOURCE];
  const completed = runDocker(argv, source, timeoutS ?? settings.load().sandbox.defaultTimeoutS);
  if (completed.error !== undefined && /** @type {NodeJS.ErrnoException} */ (completed.error).code !== "EPIPE") {
    removeContainer(name);
    throw new SandboxError(`the compile check could not be run: ${completed.error.message}`);
  }
  const stdout = decode(completed.stdout);
  if (completed.status === 0 || completed.status === 1) {
    return { compiled: completed.status === 0, detail: completed.status === 0 ? "" : stdout.trim() };
  }
  const detail = (decode(completed.stderr) || stdout).trim().slice(0, settings.load().sandbox.detailChars);
  throw new SandboxError(`the compile check produced no answer (exit code ${completed.status}): ${detail}`);
}

/**
 * The one fenced python block of an answer, or `null` when there is not exactly one.
 * @param {string} answer
 * @returns {string | null}
 */
export function extractPythonBlock(answer) {
  const blocks = [...answer.matchAll(/```python\n([\s\S]*?)```/g)];
  return blocks.length === 1 ? blocks[0][1] : null;
}
