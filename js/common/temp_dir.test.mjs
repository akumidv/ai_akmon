// The one place the JS tests make a scratch folder (C210): a suite that leaves its scratch in
// `os.tmpdir()` charges the machine for every run, and self-CI runs the suite on every pre-commit.
// This file holds no test of its own — importing it must not start one; the helper's tests are in
// `temp_dir_cleanup.test.mjs`. The `.test.mjs` name keeps it out of the published package.
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

/** @type {Set<string>} */
const _created = new Set();
let _hooked = false;

/** Remove every folder `tempDir` made in this process; runs as the process exits. */
function _removeAll() {
  for (const dir of _created) {
    fs.rmSync(dir, { recursive: true, force: true });
  }
  _created.clear();
}

/**
 * A fresh temporary folder under `os.tmpdir()`, its real path, removed when the process exits —
 * also when a test fails before its own clean-up. `node --test` runs each test file in its own
 * process, so the folders of one file are gone when that file ends.
 * @param {string} prefix the folder name's start, e.g. `"akmon-init-"`
 * @returns {string}
 */
export function tempDir(prefix) {
  if (!_hooked) {
    process.on("exit", _removeAll);
    _hooked = true;
  }
  const dir = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), prefix)));
  _created.add(dir);
  return dir;
}
