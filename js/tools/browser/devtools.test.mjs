import assert from "node:assert/strict";
import { test } from "node:test";

import { holdsProfile, processesOfProfile } from "./devtools.mjs";

const PLAIN = "C:\\Users\\me\\proj\\_aitna\\.local\\.browser\\chrome-profile";
const TESTING = `${PLAIN}-cft`;

test("a Chrome runs with a profile only when its --user-data-dir is exactly that folder", () => {
  const plain = `"C:\\chrome.exe" --remote-debugging-port=9312 --user-data-dir=${PLAIN} --no-first-run`;
  const testing = `"C:\\cft\\chrome.exe" --remote-debugging-port=9312 --user-data-dir=${TESTING} --no-first-run`;
  assert.equal(holdsProfile(plain, PLAIN), true);
  assert.equal(holdsProfile(testing, PLAIN), false, "chrome-profile-cft is not chrome-profile");
  assert.equal(holdsProfile(testing, TESTING), true);
  assert.equal(holdsProfile(plain, TESTING), false);
});

test("the profile may end the line, be quoted, or differ in case, as Windows spells it", () => {
  assert.equal(holdsProfile(`chrome.exe --user-data-dir=${PLAIN}`, PLAIN), true);
  assert.equal(holdsProfile(`chrome.exe "--user-data-dir=${PLAIN}" --x`, PLAIN), true);
  assert.equal(holdsProfile(`chrome.exe --user-data-dir="${PLAIN}" --x`, PLAIN), true);
  assert.equal(holdsProfile(`chrome.exe --user-data-dir=${PLAIN.toUpperCase()} --x`, PLAIN), true);
  assert.equal(holdsProfile(`chrome.exe --user-data-dir=${PLAIN}\\Default --x`, PLAIN), false);
});

test("a wildcard character in the path is itself", () => {
  const odd = "C:\\work\\a[1]\\prof*";
  assert.equal(holdsProfile(`chrome.exe --user-data-dir=${odd} --x`, odd), true);
  assert.equal(holdsProfile("chrome.exe --user-data-dir=C:\\work\\a1\\profile --x", odd), false);
  assert.equal(holdsProfile("chrome.exe --user-data-dir=C:\\work\\a[1]\\prof-x --x", odd), false);
});

test("of a process listing only the processes of the profile are chosen", () => {
  const listing = [
    `11\t"C:\\chrome.exe" --user-data-dir=${PLAIN} --type=renderer`,
    `12\t"C:\\cft\\chrome.exe" --user-data-dir=${TESTING}`,
    `13\t"C:\\chrome.exe" --user-data-dir=${PLAIN}`,
    "not a process line",
    "",
  ].join("\r\n");
  assert.deepEqual(processesOfProfile(listing, PLAIN), [11, 13]);
  assert.deepEqual(processesOfProfile(listing, TESTING), [12]);
});
