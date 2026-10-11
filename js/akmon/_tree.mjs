/**
 * Resolve the standard tree the running module belongs to — the JavaScript twin of
 * `src/akmon/_tree.py` (C105, ADR 0020 D02).
 *
 * The Python resolves an embedded tree (a wheel's `akmon/_tree`, a source checkout's repo root).
 * The JavaScript implementation has no second candidate: the tree is the package that holds the
 * running file, `<tree>/js/akmon/_tree.mjs`, so `embeddedTreeRoot` is two levels up from here,
 * links dereferenced. Stdlib only, and light enough for the `akmon path` hot path.
 */

import fs from "node:fs";
import { posix } from "node:path";
import { fileURLToPath } from "node:url";

/**
 * The real path of the standard tree this module executes from: `<tree>/js/akmon/_tree.mjs` → `<tree>`.
 * @returns {string}
 */
export function embeddedTreeRoot() {
  return fs.realpathSync(posix.resolve(posix.dirname(fileURLToPath(import.meta.url)), "..", ".."));
}
