#!/usr/bin/env node
/**
 * The akmon bin entry of the npm package (C103) — a stub.
 *
 * The JavaScript CLI itself lands in C105 (the CLI port). This stub exists so the
 * manifest's `bin` entry is real in the meantime: the binary resolves to a file that
 * runs, names what is missing, and exits non-zero.
 */

import fs from "node:fs";
import { fileURLToPath } from "node:url";

/** The one line the stub writes to stderr. */
export const NOT_PORTED =
  "akmon: the JavaScript CLI is not ported yet (C105); this stub exists so the package's bin entry is real";

/**
 * Report that the JavaScript CLI is not ported yet.
 *
 * @returns {number} The process exit code (2).
 */
export function main() {
  process.stderr.write(`${NOT_PORTED}\n`);
  return 2;
}

/**
 * Whether node was told to execute `invoked` as this very module. Both sides are dereferenced
 * because npm installs a `bin` entry as a symlink in `node_modules/.bin/`: the path it was
 * given is the link, `import.meta.url` is the target, and the two agree only once resolved.
 * An unresolvable path (a link whose target is gone) falls back to the unresolved comparison:
 * the check answers whether to run, it never crashes the thing it is guarding.
 *
 * @param {string} invoked `process.argv[1]`, the path node was given
 * @returns {boolean}
 */
function runAsEntryPoint(invoked) {
  const self = fileURLToPath(import.meta.url);
  try {
    return fs.realpathSync(invoked) === fs.realpathSync(self);
  } catch {
    return invoked === self;
  }
}

// Run as the entry point, not imported: the ESM way to say so is to compare the file node was
// actually told to execute with this module's own path.
if (process.argv[1] !== undefined && runAsEntryPoint(process.argv[1])) {
  process.exitCode = main();
}
