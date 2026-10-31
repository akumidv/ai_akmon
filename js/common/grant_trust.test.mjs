/**
 * node:test for `js/common/grant_trust.mjs` — the twin of `meta/tests/test_grant_trust.py` (C172).
 * The log lines and diff texts are the same literals as there, so a drift in either twin shows as
 * a failing literal.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import { posix } from "node:path";

import {
  EVENT_UNTRUSTED,
  GrantTrustError,
  TrustState,
  accept,
  fileDigest,
  fileTrust,
  formatEvent,
  grantsDirectory,
  isAccepted,
  lastAccepted,
  lastAcceptedElsewhere,
  listGrantFiles,
  loadGrant,
  readLog,
  recordUntrusted,
  resolveDigest,
  resolveStore,
  revoke,
  trustReport,
  unifiedDiff,
} from "./grant_trust.mjs";

const ABC_DIGEST = "edeaaff3f1774ad2888673770c6d64097e391bc362d7d6fb34982ddf0efd18cb"; // sha256 of "abc\n"

/** @param {number} second */
const at = (second) => new Date(Date.UTC(2026, 0, 2, 3, 4, second));

function scratch() {
  return fs.realpathSync(fs.mkdtempSync(posix.join(os.tmpdir(), "akmon-grant-trust-")));
}

/** A project root named `name` under `base`, and a store under `base`. */
function project(/** @type {string} */ base, name = "proj") {
  const root = posix.join(base, name);
  fs.mkdirSync(posix.join(root, "_aitna", "akmon"), { recursive: true });
  fs.writeFileSync(posix.join(root, "AGENTS.md"), "# project\n");
  return root;
}

function grant(/** @type {string} */ root, /** @type {string} */ relative, /** @type {string} */ text) {
  const path = posix.join(root, relative);
  fs.mkdirSync(posix.dirname(path), { recursive: true });
  fs.writeFileSync(path, text);
  return loadGrant(path, root);
}

/** @param {string} base */
function storeIn(base) {
  return resolveStore({ AKMON_TRUST_DIR: posix.join(base, "store") }, posix.join(base, "proj"));
}

/** A project root no store path in the resolution tests sits in. */
const ROOT = "/somewhere/proj";

test("the store resolves from the explicit variable, the XDG state home, then HOME; empty is unset", () => {
  assert.deepEqual(resolveStore({ AKMON_TRUST_DIR: "/t", XDG_STATE_HOME: "/x", HOME: "/h" }, ROOT), {
    root: "/t",
    acceptedDir: "/t/accepted",
    logPath: "/t/trust.log",
  });
  assert.equal(resolveStore({ XDG_STATE_HOME: "/x", HOME: "/h" }, ROOT).root, "/x/akmon/trust");
  assert.equal(resolveStore({ HOME: "/h" }, ROOT).root, "/h/.local/state/akmon/trust");
  assert.equal(
    resolveStore({ AKMON_TRUST_DIR: "", XDG_STATE_HOME: "", HOME: "/h" }, ROOT).root,
    "/h/.local/state/akmon/trust",
  );
  assert.equal(resolveStore({}, ROOT).root, posix.join(os.homedir(), ".local/state/akmon/trust"));
});

test("a store inside the project checkout is refused, symlinks followed", () => {
  const base = scratch();
  const root = project(base);
  for (const environment of [
    { AKMON_TRUST_DIR: posix.join(root, "state", "trust") },
    { AKMON_TRUST_DIR: root },
    { XDG_STATE_HOME: posix.join(root, "xdg") },
    { HOME: root },
  ]) {
    assert.throws(
      () => resolveStore(environment, root),
      (error) =>
        error instanceof GrantTrustError &&
        error.message.includes("inside the project") &&
        error.message.includes(root) &&
        !error.message.includes("\n"),
    );
  }
  fs.mkdirSync(posix.join(root, "real"));
  const link = posix.join(base, "link");
  fs.symlinkSync(posix.join(root, "real"), link);
  assert.throws(
    () => resolveStore({ AKMON_TRUST_DIR: posix.join(link, "trust") }, root),
    (error) => error instanceof GrantTrustError && error.message.includes(posix.join(root, "real", "trust")),
  );
  assert.equal(fs.existsSync(posix.join(root, "state")), false);
});

test("a store outside the checkout is accepted, even beside it or through a link", () => {
  const base = scratch();
  const root = project(base);
  for (const outside of [posix.join(base, "store"), posix.join(base, "proj-state"), base]) {
    assert.equal(resolveStore({ AKMON_TRUST_DIR: outside }, root).root, outside);
  }
  fs.mkdirSync(posix.join(base, "store"));
  fs.symlinkSync(posix.join(base, "store"), posix.join(base, "out-link"));
  assert.equal(resolveStore({ AKMON_TRUST_DIR: posix.join(base, "out-link") }, root).root, posix.join(base, "store"));
});

test("reads never create the store", () => {
  const base = scratch();
  const root = project(base);
  const store = storeIn(base);
  const one = grant(root, "_aitna/grants/one.toml", "a\n");
  assert.equal(fileTrust(one, store).state, TrustState.NEW);
  assert.deepEqual(readLog(store), []);
  assert.equal(lastAccepted(one.relative, one.project, store), null);
  assert.deepEqual(trustReport(store), {
    accepts: 0,
    reaccepts: 0,
    revokes: 0,
    untrustedDigests: 0,
    acceptedAfterSighting: 0,
    medianSeconds: null,
  });
  assert.equal(isAccepted(one.digest, store), false);
  assert.equal(fs.existsSync(store.root), false);
});

test("the default grant files are every regular file under the grants directory, sorted, links skipped", () => {
  const base = scratch();
  const root = project(base);
  const grants = grantsDirectory(root);
  assert.equal(grants, `${root}/_aitna/grants`);
  assert.deepEqual(listGrantFiles(grants), []);
  for (const [name, text] of [
    ["b.toml", "b"],
    ["a/z.toml", "z"],
    ["a/deep/y.toml", "y"],
    ["a.toml", "a"],
  ]) {
    grant(root, `_aitna/grants/${name}`, text);
  }
  fs.symlinkSync(`${grants}/a.toml`, `${grants}/link.toml`);
  fs.symlinkSync(`${grants}/a`, `${grants}/dirlink`);
  assert.deepEqual(
    listGrantFiles(grants).map((path) => posix.relative(grants, path)),
    ["a.toml", "a/deep/y.toml", "a/z.toml", "b.toml"],
  );
});

test("the digest is the sha256 of the bytes", () => {
  const base = scratch();
  const path = posix.join(base, "f");
  fs.writeFileSync(path, "abc\n");
  assert.equal(fileDigest(path), ABC_DIGEST);
});

test("state is new, then trusted, then changed; trust is keyed by content, not project or path", () => {
  const base = scratch();
  const store = storeIn(base);
  const first = project(base, "first");
  const one = grant(first, "_aitna/grants/one.toml", "a\n");
  assert.deepEqual(fileTrust(one, store), { grant: one, state: TrustState.NEW, previous: null });
  accept(one, store, at(1));
  assert.equal(fileTrust(one, store).state, TrustState.TRUSTED);
  const edited = grant(first, "_aitna/grants/one.toml", "a\nb\n");
  assert.deepEqual(fileTrust(edited, store), { grant: edited, state: TrustState.CHANGED, previous: one.digest });
  const clone = project(posix.join(base, "elsewhere"), "clone");
  const moved = grant(clone, "_aitna/grants/renamed/other.toml", "a\n");
  assert.equal(fileTrust(moved, store).state, TrustState.TRUSTED);
});

test("history is keyed by project and path: another project's file is new, not changed", () => {
  const base = scratch();
  const store = storeIn(base);
  const first = project(base, "first");
  const second = project(base, "second");
  const accepted = grant(first, "_aitna/grants/one.toml", "a\n");
  accept(accepted, store, at(1));
  const other = grant(second, "_aitna/grants/one.toml", "a\nb\n");
  assert.deepEqual(fileTrust(other, store), { grant: other, state: TrustState.NEW, previous: null });
  assert.equal(lastAccepted(other.relative, other.project, store), null);
  const elsewhere = lastAcceptedElsewhere(other.relative, other.project, store);
  assert.deepEqual([elsewhere?.project, elsewhere?.digest], ["first", accepted.digest]);
  assert.equal(lastAcceptedElsewhere(accepted.relative, accepted.project, store), null);
  // a first acceptance in its project: the log's previous field stays "-"
  assert.equal(accept(other, store, at(2)).previous, "-");
  assert.ok(
    formatEvent(readLog(store).at(-1) ?? /** @type {never} */ (null)).endsWith("\t_aitna/grants/one.toml\tsecond\t-"),
  );
  const changed = grant(second, "_aitna/grants/one.toml", "a\nc\n");
  assert.deepEqual(fileTrust(changed, store), { grant: changed, state: TrustState.CHANGED, previous: other.digest });
  assert.equal(recordUntrusted(changed, store, at(3))?.previous, other.digest);
});

test("a file outside the project or with an unloggable name is refused", () => {
  const base = scratch();
  const root = project(base);
  fs.writeFileSync(posix.join(base, "outside.toml"), "x");
  assert.throws(() => loadGrant(posix.join(base, "outside.toml"), root), /outside the project root/);
  const tabbed = posix.join(root, "_aitna/grants/a\tb.toml");
  fs.mkdirSync(posix.dirname(tabbed), { recursive: true });
  fs.writeFileSync(tabbed, "x");
  assert.throws(() => loadGrant(tabbed, root), /tab or a line break/);
});

test("accept keeps the bytes and logs one exact line; a re-acceptance names the previous digest", () => {
  const base = scratch();
  const store = storeIn(base);
  const root = project(base);
  const abc = grant(root, "_aitna/grants/one.toml", "abc\n");
  const event = accept(abc, store, at(5));
  assert.equal(fs.readFileSync(`${store.acceptedDir}/${ABC_DIGEST}`, "utf8"), "abc\n");
  assert.equal(
    fs.readFileSync(store.logPath, "utf8"),
    `2026-01-02T03:04:05Z\taccept\t${ABC_DIGEST}\t_aitna/grants/one.toml\tproj\t-\n`,
  );
  assert.equal(`${formatEvent(event)}\n`, fs.readFileSync(store.logPath, "utf8"));
  assert.deepEqual(
    fs.readdirSync(store.acceptedDir).filter((name) => name.endsWith(".tmp")),
    [],
  );
  assert.throws(() => accept(abc, store, at(6)), GrantTrustError);
  const second = grant(root, "_aitna/grants/one.toml", "abc\nmore\n");
  assert.equal(accept(second, store, at(7)).previous, ABC_DIGEST);
  assert.equal(accept(grant(root, "_aitna/grants/two.toml", "x\n"), store, at(8)).previous, "-");
});

test("revoke removes the copy, logs it, and last-accepted falls back to an earlier surviving version", () => {
  const base = scratch();
  const store = storeIn(base);
  const root = project(base);
  const abc = grant(root, "_aitna/grants/one.toml", "abc\n");
  accept(abc, store, at(1));
  const later = grant(root, "_aitna/grants/one.toml", "2\n");
  accept(later, store, at(2));
  const event = revoke(later.digest, store, at(9));
  assert.equal(formatEvent(event), `2026-01-02T03:04:09Z\trevoke\t${later.digest}\t_aitna/grants/one.toml\tproj\t-`);
  assert.equal(lastAccepted("_aitna/grants/one.toml", "proj", store), ABC_DIGEST);
  assert.throws(() => revoke(later.digest, store), /not accepted/);
});

test("an untrusted sighting is logged once per digest", () => {
  const base = scratch();
  const store = storeIn(base);
  const root = project(base);
  const abc = grant(root, "_aitna/grants/one.toml", "abc\n");
  const first = recordUntrusted(abc, store, at(1));
  assert.ok(first);
  assert.equal(
    formatEvent(first),
    `2026-01-02T03:04:01Z\t${EVENT_UNTRUSTED}\t${ABC_DIGEST}\t_aitna/grants/one.toml\tproj\t-`,
  );
  assert.equal(recordUntrusted(abc, store, at(2)), null);
  assert.equal(readLog(store).length, 1);
  accept(abc, store, at(3));
  const changed = grant(root, "_aitna/grants/one.toml", "abcd\n");
  assert.equal(recordUntrusted(changed, store, at(4))?.previous, ABC_DIGEST);
  assert.equal(recordUntrusted(abc, store, at(5)), null);
});

test("a malformed log line names its number; a naive time is refused before anything is written", () => {
  const base = scratch();
  const store = storeIn(base);
  const root = project(base);
  accept(grant(root, "_aitna/grants/one.toml", "a\n"), store, at(1));
  fs.appendFileSync(store.logPath, "not a trust line\n");
  assert.throws(() => readLog(store), /trust\.log:2: malformed trust log line/);
  const fresh = storeIn(scratch());
  assert.throws(() => accept(grant(root, "_aitna/grants/z.toml", "z"), fresh, new Date(Number.NaN)), RangeError);
  assert.equal(fs.existsSync(fresh.root), false);
});

test("a digest prefix needs at least twelve hex and exactly one match", () => {
  const base = scratch();
  const store = storeIn(base);
  accept(grant(project(base), "_aitna/grants/one.toml", "abc\n"), store, at(1));
  assert.equal(resolveDigest(ABC_DIGEST.slice(0, 12), store), ABC_DIGEST);
  assert.equal(resolveDigest(ABC_DIGEST, store), ABC_DIGEST);
  assert.throws(() => resolveDigest(ABC_DIGEST.slice(0, 11), store), /not a digest/);
  assert.throws(() => resolveDigest("0".repeat(12), store), /names no accepted digest/);
  assert.throws(() => resolveDigest("XYZ".repeat(5), store), /not a digest/);
});

test("the report counts the log and the median wait", () => {
  const base = scratch();
  const store = storeIn(base);
  const root = project(base);
  const [one, two, three] = ["one", "two", "three"].map((name) => grant(root, `_aitna/grants/${name}.toml`, name));
  recordUntrusted(one, store, at(0));
  recordUntrusted(two, store, at(10));
  recordUntrusted(three, store, at(20));
  accept(one, store, at(30));
  accept(two, store, at(50));
  accept(grant(root, "_aitna/grants/one.toml", "one edited"), store, at(55));
  revoke(two.digest, store, at(58));
  assert.deepEqual(trustReport(store), {
    accepts: 3,
    reaccepts: 1,
    revokes: 1,
    untrustedDigests: 3,
    acceptedAfterSighting: 2,
    medianSeconds: 35,
  });
});

test("re-acceptances are counted per project and path", () => {
  const base = scratch();
  const store = storeIn(base);
  const first = project(base, "first");
  const second = project(base, "second");
  accept(grant(first, "_aitna/grants/one.toml", "a\n"), store, at(1));
  accept(grant(second, "_aitna/grants/one.toml", "a\nb\n"), store, at(2)); // a new file, not a re-acceptance
  assert.equal(trustReport(store).reaccepts, 0);
  accept(grant(first, "_aitna/grants/one.toml", "a\nc\n"), store, at(3));
  assert.deepEqual(trustReport(store), {
    accepts: 3,
    reaccepts: 1,
    revokes: 0,
    untrustedDigests: 0,
    acceptedAfterSighting: 0,
    medianSeconds: null,
  });
});

test("the report's median of an odd count", () => {
  const base = scratch();
  const store = storeIn(base);
  const root = project(base);
  const grants = ["a", "b", "c"].map((name) => grant(root, `_aitna/grants/${name}.toml`, name));
  grants.forEach((entry, index) => recordUntrusted(entry, store, at(index)));
  [5, 7, 40].forEach((wait, index) => accept(grants[index], store, at(index + wait)));
  assert.equal(trustReport(store).medianSeconds, 7);
});

const DIFF_VECTORS = [
  [
    "a\nb\nc\nd\ne\nf\ng\nh\n",
    "a\nb\nc\nD\ne\nf\ng\nh\n",
    "--- old\n+++ new\n@@ -1,7 +1,7 @@\n a\n b\n c\n-d\n+D\n e\n f\n g\n",
  ],
  ["a\n", "a\nb\n", "--- old\n+++ new\n@@ -1 +1,2 @@\n a\n+b\n"],
  ["", "x\n", "--- old\n+++ new\n@@ -0,0 +1 @@\n+x\n"],
  ["x\n", "", "--- old\n+++ new\n@@ -1 +0,0 @@\n-x\n"],
  ["same\n", "same\n", ""],
  ["same\n", "same", ""],
  [
    "1\n2\n3\n4\n5\n6\n7\n8\n9\n10\n11\n12\n",
    "1\nTWO\n3\n4\n5\n6\n7\n8\n9\n10\n11\nTWELVE\n",
    "--- old\n+++ new\n@@ -1,5 +1,5 @@\n 1\n-2\n+TWO\n 3\n 4\n 5\n@@ -9,4 +9,4 @@\n 9\n 10\n 11\n-12\n+TWELVE\n",
  ],
];

test("the unified diff prints the same text as the Python twin", () => {
  for (const [oldText, newText, expected] of DIFF_VECTORS) {
    assert.equal(unifiedDiff(Buffer.from(oldText), Buffer.from(newText), "old", "new"), expected);
  }
});
