/**
 * `akmon trust` — accept, inspect and revoke the digests of a project's own grant files: the
 * JavaScript twin of `src/akmon/_trust.py` (C172, ADR 0025 D04/D05; ADR 0020 D01). The Python
 * module is the spec: the same subcommands, texts and exit codes.
 *
 * The store, the digest and the log are `common/grant_trust.mjs`'s; this module is the command
 * line over them. Acceptance happens at an interactive terminal and nowhere else: there is
 * deliberately no `--yes` and no non-interactive path. The terminal check and the confirmation
 * read both go through {@link TrustIO}, the one seam, so a test drives them without a terminal.
 *
 * Twin note: the prompt is asynchronous here (`readline`), so `ask` resolves to the answer, or to
 * `null` at end of input where the Python's `input` raises `EOFError`; both count as "no".
 */

import fs from "node:fs";
import { posix } from "node:path";
import { createInterface } from "node:readline";

import { DataFileError } from "../common/jsondata.mjs";
import {
  GrantTrustError,
  SHORT_DIGEST_LENGTH,
  TrustState,
  acceptedContent,
  accept,
  fileTrust,
  grantsDirectory,
  isAccepted,
  lastAccepted,
  lastAcceptedElsewhere,
  listGrantFiles,
  loadGrant,
  resolveDigest,
  resolveStore,
  revoke,
  trustReport,
  unifiedDiff,
} from "../common/grant_trust.mjs";
import { resolvePath, resolveProjectRoot } from "../common/project_root.mjs";

const _SUBCOMMANDS = ["status", "diff", "accept", "revoke", "report"];
const _USAGE =
  "usage: akmon trust status [PATH...] | diff [PATH...] | accept [PATH...] | revoke DIGEST-or-PATH | report\n" +
  "  status   one line per grant file: state, short digest, path; exit 1 when any is not trusted\n" +
  "  diff     each untrusted file against the last accepted version of the same path\n" +
  "  accept   show each untrusted file, then ask at the terminal; refused when stdin is not a terminal\n" +
  "  revoke   forget an accepted digest (a digest of at least 12 hex characters, or a file)\n" +
  "  report   what the trust log records (ADR 0025/D05)\n" +
  "PATH names grant files or directories; none names every file under <dev root>/grants/.\n";
const _NOT_INTERACTIVE =
  "akmon trust accept: acceptance needs an interactive terminal; stdin is not one (ADR 0025/D05: " +
  "there is no non-interactive acceptance)";
const _HEX = /^[0-9a-f]+$/;

/**
 * What the command touches of the process: environment, cwd, streams, the terminal check and the prompt.
 * @typedef {object} TrustIO
 * @property {Record<string, string | undefined>} environ
 * @property {string} cwd
 * @property {{write: (text: string) => unknown}} out
 * @property {{write: (text: string) => unknown}} err
 * @property {boolean} interactive
 * @property {(prompt: string) => Promise<string | null>} ask the answer, or `null` at end of input
 */

/**
 * Ask one question at the terminal.
 * @param {string} prompt
 * @returns {Promise<string | null>}
 */
function _askAtTerminal(prompt) {
  return new Promise((resolve) => {
    const terminal = createInterface({ input: process.stdin, output: process.stdout });
    terminal.on("close", () => resolve(null));
    terminal.question(prompt, (answer) => {
      resolve(answer);
      terminal.close();
    });
  });
}

/**
 * The real process: its environment, cwd and streams; interactive iff stdin is a terminal.
 * @returns {TrustIO}
 */
export function processIo() {
  return {
    environ: process.env,
    cwd: process.cwd(),
    out: process.stdout,
    err: process.stderr,
    interactive: Boolean(process.stdin.isTTY),
    ask: _askAtTerminal,
  };
}

/**
 * Whether `error` is a failure this command reports in one line (the Python's `OSError`,
 * `RuntimeError` and `ValueError`) rather than a defect it must not hide.
 * @param {unknown} error
 * @returns {boolean}
 */
function _isReportable(error) {
  if (!(error instanceof Error)) {
    return false;
  }
  if (error instanceof GrantTrustError || error instanceof DataFileError) {
    return true;
  }
  return (
    typeof (/** @type {{errno?: unknown}} */ (error).errno) === "number" ||
    ["ValueError", "RuntimeError", "UnicodeEncodeError"].includes(error.name)
  );
}

/** One run of `akmon trust` in the project the cwd belongs to. */
class Trust {
  /** @param {TrustIO} io */
  constructor(io) {
    this.io = io;
    const { root, notice } = resolveProjectRoot(null, io.cwd);
    this.rooted = notice === null;
    if (notice) {
      io.err.write(`${notice}\n`);
    }
    this.root = root;
    this.store = resolveStore(io.environ, root);
    this.grantsDir = grantsDirectory(root);
  }

  /** @param {string} line */
  _say(line) {
    this.io.out.write(`${line}\n`);
  }

  /**
   * The grant files named by `paths` (the default set when none), each read once.
   * @param {string[]} paths
   * @returns {import("../common/grant_trust.mjs").GrantFile[]}
   */
  _targets(paths) {
    /** @type {string[]} */
    let files = [];
    if (paths.length === 0) {
      files = listGrantFiles(this.grantsDir);
    } else {
      for (const given of paths) {
        const path = resolvePath(posix.isAbsolute(given) ? given : `${this.io.cwd}/${given}`);
        const kind = _kindOf(path);
        if (kind === "directory") {
          files.push(...listGrantFiles(path));
        } else if (kind === "file") {
          files.push(path);
        } else {
          throw new GrantTrustError(`${given}: no such file or directory`);
        }
      }
    }
    return [...new Set(files)].map((path) => loadGrant(path, this.root));
  }

  /**
   * @param {string[]} paths
   * @returns {number}
   */
  _empty(paths) {
    const where = paths.length === 0 ? `under ${posix.relative(this.root, this.grantsDir)}/` : "in the given paths";
    this._say(`akmon trust: no grant files ${where}`);
    return 0;
  }

  /**
   * @param {string[]} paths
   * @returns {number}
   */
  status(paths) {
    const grants = this._targets(paths);
    if (grants.length === 0) {
      return this._empty(paths);
    }
    let untrusted = 0;
    for (const grant of grants) {
      const { state } = fileTrust(grant, this.store);
      if (state !== TrustState.TRUSTED) {
        untrusted++;
      }
      this._say(`${state.padEnd(8)} ${grant.digest.slice(0, SHORT_DIGEST_LENGTH)}  ${grant.relative}`);
    }
    return untrusted > 0 ? 1 : 0;
  }

  /**
   * What the owner reads before accepting: the change since the last accepted version, or the whole file.
   * @param {import("../common/grant_trust.mjs").FileTrust} trust
   */
  _show(trust) {
    const { grant } = trust;
    if (trust.state === TrustState.NEW) {
      const elsewhere = lastAcceptedElsewhere(grant.relative, grant.project, this.store);
      if (elsewhere !== null) {
        this._showAgainstOtherProject(grant, elsewhere);
        return;
      }
      this._say(`=== ${grant.relative}: new, no earlier version accepted; the whole file follows ===`);
      const text = new TextDecoder("utf-8", { fatal: false, ignoreBOM: true }).decode(grant.content);
      this.io.out.write(text === "" || text.endsWith("\n") ? text : `${text}\n`);
      return;
    }
    const previous = /** @type {string} */ (trust.previous);
    this._say(`=== ${grant.relative}: changed since ${previous.slice(0, SHORT_DIGEST_LENGTH)} ===`);
    const text = unifiedDiff(
      acceptedContent(previous, this.store),
      grant.content,
      `${grant.relative} (accepted ${previous.slice(0, SHORT_DIGEST_LENGTH)})`,
      `${grant.relative} (now ${grant.digest.slice(0, SHORT_DIGEST_LENGTH)})`,
    );
    this.io.out.write(text || "(the text is the same; only the final newline differs)\n");
  }

  /**
   * A file new to this project, as the change from the version another project accepted at its path.
   * @param {import("../common/grant_trust.mjs").GrantFile} grant
   * @param {import("../common/grant_trust.mjs").TrustEvent} elsewhere
   */
  _showAgainstOtherProject(grant, elsewhere) {
    const short = elsewhere.digest.slice(0, SHORT_DIGEST_LENGTH);
    this._say(
      `=== ${grant.relative}: new in this project; last accepted in project ${elsewhere.project} ` +
        `as ${short}, the change since that version follows ===`,
    );
    const text = unifiedDiff(
      acceptedContent(elsewhere.digest, this.store),
      grant.content,
      `${grant.relative} (accepted in project ${elsewhere.project}, ${short})`,
      `${grant.relative} (now ${grant.digest.slice(0, SHORT_DIGEST_LENGTH)})`,
    );
    this.io.out.write(text || "(the text is the same; only the final newline differs)\n");
  }

  /**
   * @param {string[]} paths
   * @returns {number}
   */
  diff(paths) {
    const grants = this._targets(paths);
    if (grants.length === 0) {
      return this._empty(paths);
    }
    let shown = 0;
    for (const grant of grants) {
      const trust = fileTrust(grant, this.store);
      if (trust.state !== TrustState.TRUSTED) {
        this._show(trust);
        shown++;
      }
    }
    if (shown === 0) {
      this._say("akmon trust: every grant file is trusted; nothing to show");
    }
    return 0;
  }

  /**
   * @param {string[]} paths
   * @returns {Promise<number>}
   */
  async accept(paths) {
    if (!this.rooted) {
      return 2; // no project root: the notice was printed, and no grant is accepted for a guessed project (ADR 0022 D09)
    }
    if (!this.io.interactive) {
      this.io.err.write(`${_NOT_INTERACTIVE}\n`);
      return 2;
    }
    const grants = this._targets(paths);
    if (grants.length === 0) {
      return this._empty(paths);
    }
    let declined = 0;
    for (const grant of grants) {
      const trust = fileTrust(grant, this.store);
      if (trust.state === TrustState.TRUSTED) {
        this._say(`${grant.relative}: already trusted`);
        continue;
      }
      this._show(trust);
      if (await this._confirmed(`accept ${grant.relative}? [y/N] `)) {
        const event = accept(grant, this.store);
        this._say(`${grant.relative}: accepted ${event.digest.slice(0, SHORT_DIGEST_LENGTH)}`);
      } else {
        declined++;
        this._say(`${grant.relative}: not accepted`);
      }
    }
    return declined > 0 ? 1 : 0;
  }

  /**
   * @param {string} prompt
   * @returns {Promise<boolean>}
   */
  async _confirmed(prompt) {
    const answer = await this.io.ask(prompt);
    return answer !== null && ["y", "yes"].includes(answer.trim().toLowerCase());
  }

  /**
   * @param {string} reference
   * @returns {number}
   */
  revoke(reference) {
    if (!this.rooted) {
      return 2; // no project root: the notice was printed, and nothing is revoked (ADR 0022 D09)
    }
    /** @type {string} */
    let digest;
    if (reference.length >= SHORT_DIGEST_LENGTH && _HEX.test(reference)) {
      digest = resolveDigest(reference, this.store);
    } else {
      const grants = this._targets([reference]);
      if (grants.length !== 1) {
        throw new GrantTrustError(`${reference}: revoke names one file, not ${grants.length}`);
      }
      const [grant] = grants;
      if (isAccepted(grant.digest, this.store)) {
        digest = grant.digest;
      } else {
        const earlier = lastAccepted(grant.relative, grant.project, this.store);
        if (earlier === null) {
          throw new GrantTrustError(`${grant.relative}: no accepted version to revoke`);
        }
        digest = earlier;
      }
    }
    const event = revoke(digest, this.store);
    this._say(`revoked ${digest.slice(0, SHORT_DIGEST_LENGTH)} (${event.path})`);
    return 0;
  }

  /** @returns {number} */
  report() {
    const report = trustReport(this.store);
    const median = report.medianSeconds === null ? "-" : report.medianSeconds.toFixed(1);
    this._say(`accepts: ${report.accepts}`);
    this._say(`re-accepts: ${report.reaccepts}`);
    this._say(`revokes: ${report.revokes}`);
    this._say(`untrusted digests sighted: ${report.untrustedDigests}`);
    this._say(`sighted digests later accepted: ${report.acceptedAfterSighting}`);
    this._say(`median seconds from sighting to acceptance: ${median}`);
    return 0;
  }
}

/**
 * Whether `path` is a directory, a regular file, or neither (a missing path included).
 * @param {string} path
 * @returns {"directory" | "file" | "none"}
 */
function _kindOf(path) {
  try {
    const stats = fs.statSync(path);
    return stats.isDirectory() ? "directory" : stats.isFile() ? "file" : "none";
  } catch {
    return "none";
  }
}

/**
 * @param {TrustIO} io
 * @param {string} message
 * @returns {number}
 */
function _usageError(io, message) {
  io.err.write(`akmon trust: ${message}\n${_USAGE}`);
  return 2;
}

/**
 * What is wrong with the arguments of `command`, or `null` when they can be run.
 * @param {string} command
 * @param {string[]} rest
 * @returns {string | null}
 */
function _argumentProblem(command, rest) {
  if (command === "revoke" && rest.length !== 1) {
    return "revoke takes exactly one DIGEST or PATH";
  }
  if (command === "report" && rest.length > 0) {
    return "report takes no arguments";
  }
  const option = rest.find((argument) => argument.startsWith("-"));
  return option === undefined ? null : `${command} takes no options; got '${option}'`;
}

/**
 * @param {Trust} session
 * @param {string} command
 * @param {string[]} rest
 * @returns {number | Promise<number>}
 */
function _run(session, command, rest) {
  if (command === "revoke") {
    return session.revoke(rest[0]);
  }
  if (command === "report") {
    return session.report();
  }
  if (command === "status") {
    return session.status(rest);
  }
  if (command === "diff") {
    return session.diff(rest);
  }
  return session.accept(rest);
}

/**
 * Run `akmon trust <subcommand>`; `io` is the process unless a test hands in a fake.
 * @param {string[]} argv the arguments after `trust`
 * @param {TrustIO} [io]
 * @returns {Promise<number>} The process exit code.
 */
export async function main(argv, io = processIo()) {
  if (argv.length === 0) {
    io.err.write(_USAGE);
    return 2;
  }
  if (argv[0] === "-h" || argv[0] === "--help") {
    io.out.write(_USAGE);
    return 0;
  }
  const [command, ...rest] = argv;
  const problem = _SUBCOMMANDS.includes(command) ? _argumentProblem(command, rest) : `unknown command '${command}'`;
  if (problem !== null) {
    return _usageError(io, problem);
  }
  try {
    return await _run(new Trust(io), command, rest);
  } catch (error) {
    if (!_isReportable(error)) {
      throw error;
    }
    io.err.write(`akmon trust: ${/** @type {Error} */ (error).message}\n`);
    return 2;
  }
}
