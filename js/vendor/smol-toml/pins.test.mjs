/**
 * Offline pin gate for the vendored smol-toml (ADR 0020 D04, C103): re-hash every file
 * `pins.json` pins and compare, assert the pinned package version against the vendored
 * `package.json`, assert the LICENSE is present, and read the ledger in both directions —
 * every file the directory holds is named by the record, every name the record carries is in
 * the directory. A mismatch names the file. Runs on the host `node --test` with no network
 * and no toml-test binary.
 */

import { createHash } from "node:crypto";
import { mkdir, mkdtemp, readdir, readFile, rm, symlink, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

import { test } from "node:test";
import assert from "node:assert/strict";

const HERE = fileURLToPath(new URL(".", import.meta.url));

// Findings name the repo path rather than a path relative to wherever the run started: the
// directory is read from a copy (a carrier, a sabotage probe) as often as from this checkout.
const VENDORED = "js/vendor/smol-toml";

/** @returns {Promise<{package: string, version: string, source: string, tarball_sha256: string, pinned: string, files: Record<string, string>, akmon_files: string[], toml_test: {run: Record<string, {passed: number, failed: number}>}>}> */
async function _pins() {
  return JSON.parse(await readFile(join(HERE, "pins.json"), "utf8"));
}

/**
 * The sha256 of a vendored file, hex. A name the record carries that cannot be read fails
 * here with its name and its remedy: the bare `ENOENT` reports where the read started, not
 * what the ledger got wrong.
 */
async function _sha256(rel) {
  let bytes;
  try {
    bytes = await readFile(join(HERE, rel));
  } catch (cause) {
    const reason = cause instanceof Error ? cause.message : String(cause);
    throw new Error(`${VENDORED}/${rel} is pinned in pins.json but cannot be read — restore it from the pinned tarball or drop the entry (${reason})`, { cause });
  }
  return createHash("sha256").update(bytes).digest("hex");
}

/**
 * What the directory actually holds: every regular file under `dir` as a `files`-map-relative
 * POSIX path, and every entry that is neither a regular file nor a directory (a symlink, a
 * socket) in a class of its own, both sorted. `readdir` reports a symlink as a symlink rather
 * than as its target, so a link aimed outside the tree is named as an offender instead of
 * being hashed as vendored content.
 *
 * An unexpected directory that holds no files contributes nothing, on purpose: a directory is
 * not payload — neither carrier ships one — while the files under an unexpected directory each
 * arrive as their own finding, named in full.
 *
 * @param {string} dir
 * @returns {Promise<{files: string[], other: string[]}>}
 */
async function _listing(dir) {
  const files = [];
  const other = [];
  /** @param {string} rel */
  async function descend(rel) {
    for (const entry of await readdir(join(dir, rel), { withFileTypes: true })) {
      const name = rel === "" ? entry.name : `${rel}/${entry.name}`;
      if (entry.isDirectory()) await descend(name);
      else if (entry.isFile()) files.push(name);
      else other.push(name);
    }
  }
  await descend("");
  return { files: files.sort(), other: other.sort() };
}

/**
 * Whether a name from the record stays inside this directory. The gate reads `join(HERE, name)`,
 * so a name that walks up out of the directory, or arrives absolute, has it hashing a file it is
 * not vendoring.
 *
 * @param {unknown} name
 */
function _staysInside(name) {
  if (typeof name !== "string" || name === "" || name.startsWith("/")) return false;
  return !name.split("/").some((part) => part === "" || part === "..");
}

/**
 * The ledger, read both ways. Every file on disk is either pinned upstream content (`files`) or
 * akmon's own (`akmon_files`); every name either list carries is on disk; the two lists do not
 * overlap; every name stays inside this directory. Findings are returned rather than thrown so
 * one run names every offender at once, in path order — the caller decides that the empty list
 * is the pass, and the synthetic cases below read the same list the live tree produces.
 *
 * @param {{files: Record<string, string>, akmon_files?: unknown}} pins
 * @param {{files: string[], other: string[]}} listing
 * @returns {string[]} one finding per offender, empty when the directory and the record agree
 */
function _ledgerFindings(pins, listing) {
  const findings = [];
  const upstream = new Set(Object.keys(pins.files));
  const declared = Array.isArray(pins.akmon_files) ? pins.akmon_files : [];
  if (!Array.isArray(pins.akmon_files)) {
    findings.push("pins.json carries no `akmon_files` list — name akmon's own files (README.md, pins.json, pins.test.mjs) there, or the gate cannot tell them from a planted file");
  }
  const own = new Set(declared);
  const present = new Set(listing.files);

  for (const name of [...new Set([...upstream, ...own])].sort()) {
    if (!_staysInside(name)) {
      findings.push(`pins.json names ${JSON.stringify(name)}, which is not a path inside ${VENDORED} — every name in the record is relative to this directory`);
    }
  }
  for (const name of [...upstream].sort()) {
    if (!present.has(name)) {
      findings.push(`${VENDORED}/${name} is pinned in \`files\` but the directory has no such file — restore it from the pinned tarball, or drop the entry`);
    }
  }
  for (const name of [...own].sort()) {
    if (upstream.has(name)) {
      findings.push(`${VENDORED}/${name} is pinned in \`files\` and listed in \`akmon_files\` at once — it is one or the other, and a file akmon wrote belongs in the upstream hash map or the next bump diff lies about who wrote it`);
    }
    if (!present.has(name)) {
      findings.push(`${VENDORED}/${name} is listed in \`akmon_files\` as akmon's own but the directory has no such file — restore it, or drop it from the list`);
    }
  }
  for (const name of listing.files) {
    if (!upstream.has(name) && !own.has(name)) {
      findings.push(`${VENDORED}/${name} is in the vendored directory and named by neither pins.json list — hash it into \`files\` if it is upstream content, list it in \`akmon_files\` if it is akmon's own, or delete it`);
    }
  }
  for (const name of listing.other) {
    findings.push(`${VENDORED}/${name} is not a regular file (a symlink, or a device or socket) — no pin can name it and the gate will not read through it; put the file's own bytes there`);
  }
  return findings;
}

test("every pinned file re-hashes to its recorded sha256", async () => {
  const pins = await _pins();
  const names = Object.keys(pins.files);
  assert.ok(names.length > 0, "pins.json carries no files");
  for (const name of names) {
    const recorded = pins.files[name];
    const actual = await _sha256(name);
    assert.strictEqual(actual, recorded, `js/vendor/smol-toml/${name} no longer matches its pin (recorded ${recorded}, found ${actual})`);
  }
});

test("the pinned version matches the vendored package.json", async () => {
  const pins = await _pins();
  const manifest = JSON.parse(await readFile(join(HERE, "package.json"), "utf8"));
  assert.strictEqual(manifest.version, pins.version, `pins.json pins ${pins.version} but the vendored package.json is ${manifest.version}`);
  assert.strictEqual(manifest.name, pins.package, "pins.json names a different package than the vendored package.json");
});

test("the LICENSE is present and pinned", async () => {
  const pins = await _pins();
  assert.ok(pins.files["LICENSE"], "pins.json pins no LICENSE");
  const actual = await _sha256("LICENSE");
  assert.strictEqual(actual, pins.files["LICENSE"], "js/vendor/smol-toml/LICENSE no longer matches its pin");
});

test("the toml-test run records are green", async () => {
  const pins = await _pins();
  for (const [node, run] of Object.entries(pins.toml_test.run)) {
    assert.strictEqual(run.failed, 0, `${node} records ${run.failed} failed toml-test cases`);
    assert.ok(run.passed > 0, `${node} records no passing toml-test cases`);
    assert.ok(Array.isArray(run.skipped), `${node} records no skipped list`);
    for (const skip of run.skipped) {
      assert.ok(typeof skip.name === "string" && skip.name.length > 0, `${node} skip entry without a name`);
      assert.ok(typeof skip.reason === "string" && skip.reason.length > 0, `${node} skip "${skip.name}" without a reason`);
    }
  }
});

test("the vendored directory holds nothing the record does not account for", async () => {
  const pins = await _pins();
  assert.deepStrictEqual(_ledgerFindings(pins, await _listing(HERE)), []);
});

// The ledger's own cases: one record and one listing, small enough to read at once, each case
// perturbing exactly one thing. The test above pins the live tree; these pin the two directions,
// without planting files in the repository.

/** Two upstream names plus the trio akmon writes into the directory. */
function _ledgerRecord() {
  return {
    files: { LICENSE: "0".repeat(64), "dist/index.js": "1".repeat(64) },
    akmon_files: ["README.md", "pins.json", "pins.test.mjs"],
  };
}

// Every name `_ledgerRecord()` accounts for, in the order the walk returns it.
const LEDGER_OK = ["LICENSE", "README.md", "dist/index.js", "pins.json", "pins.test.mjs"];

/** A listing of `names` the way `_listing` returns one: both classes sorted. */
function _ledgerListing(/** @type {string[]} */ names, /** @type {string[]} */ other = []) {
  return { files: [...names].sort(), other: [...other].sort() };
}

/** A single offender must raise exactly one finding, and that finding must name it. */
function _onlyFinding(/** @type {string[]} */ findings, /** @type {string} */ offender) {
  assert.strictEqual(findings.length, 1, `expected one finding naming ${offender}, got: ${findings.join(" | ")}`);
  assert.ok(findings[0].includes(offender), `the finding does not name ${offender}: ${findings[0]}`);
  return findings[0];
}

test("a directory that is exactly the record leaves the ledger clean", () => {
  assert.deepStrictEqual(_ledgerFindings(_ledgerRecord(), _ledgerListing(LEDGER_OK)), []);
});

test("a file on disk that no list names is a finding that says pin, declare, or delete", () => {
  const finding = _onlyFinding(
    _ledgerFindings(_ledgerRecord(), _ledgerListing([...LEDGER_OK, "extra-unpinned.js"])),
    "js/vendor/smol-toml/extra-unpinned.js",
  );
  assert.ok(finding.includes("`files`") && finding.includes("`akmon_files`") && finding.includes("delete"), finding);
});

test("an extra file under dist/ is named with the same relative form the record uses", () => {
  _onlyFinding(_ledgerFindings(_ledgerRecord(), _ledgerListing([...LEDGER_OK, "dist/stray.js"])), "js/vendor/smol-toml/dist/stray.js");
});

test("an unexpected directory is a finding through every file it holds", () => {
  const findings = _ledgerFindings(_ledgerRecord(), _ledgerListing([...LEDGER_OK, "payload/extra.js", "payload/more.js"]));
  assert.strictEqual(findings.length, 2, findings.join(" | "));
  assert.ok(findings[0].includes("js/vendor/smol-toml/payload/extra.js"), findings[0]);
  assert.ok(findings[1].includes("js/vendor/smol-toml/payload/more.js"), findings[1]);
});

test("a pinned name the directory lacks is a finding naming the file and its remedy", () => {
  const finding = _onlyFinding(
    _ledgerFindings(_ledgerRecord(), _ledgerListing(LEDGER_OK.filter((name) => name !== "LICENSE"))),
    "js/vendor/smol-toml/LICENSE",
  );
  assert.ok(finding.includes("pinned in `files`") && finding.includes("drop the entry"), finding);
});

test("an akmon-owned name the directory lacks is a finding naming the file and its remedy", () => {
  const finding = _onlyFinding(
    _ledgerFindings(_ledgerRecord(), _ledgerListing(LEDGER_OK.filter((name) => name !== "README.md"))),
    "js/vendor/smol-toml/README.md",
  );
  assert.ok(finding.includes("`akmon_files`") && finding.includes("drop"), finding);
});

test("a name in both lists is a finding: akmon's own files stay out of the upstream hash map", () => {
  const pins = _ledgerRecord();
  pins.akmon_files.push("LICENSE");
  const finding = _onlyFinding(_ledgerFindings(pins, _ledgerListing(LEDGER_OK)), "js/vendor/smol-toml/LICENSE");
  assert.ok(finding.includes("one or the other"), finding);
});

test("a name that points outside this directory is a finding", () => {
  const pins = _ledgerRecord();
  pins.files["../../js/common/record.mjs"] = "2".repeat(64);
  const findings = _ledgerFindings(pins, _ledgerListing(LEDGER_OK));
  assert.strictEqual(findings.length, 2, findings.join(" | "));
  assert.ok(findings[0].includes("not a path inside js/vendor/smol-toml"), findings[0]);
  assert.ok(findings[1].includes("pinned in `files`"), findings[1]);
});

test("a symlink or other non-regular entry is a finding the walk raises on its own", () => {
  const finding = _onlyFinding(_ledgerFindings(_ledgerRecord(), _ledgerListing(LEDGER_OK, ["outside"])), "js/vendor/smol-toml/outside");
  assert.ok(finding.includes("not a regular file"), finding);
});

test("a record with no akmon_files list names the gap, then every akmon file as unaccounted", () => {
  const pins = { files: { LICENSE: "0".repeat(64), "dist/index.js": "1".repeat(64) } };
  const findings = _ledgerFindings(pins, _ledgerListing(["LICENSE", "README.md", "dist/index.js"]));
  assert.strictEqual(findings.length, 2, findings.join(" | "));
  assert.ok(findings[0].includes("carries no `akmon_files` list"), findings[0]);
  assert.ok(findings[1].includes("js/vendor/smol-toml/README.md"), findings[1]);
});

test("the walk names files in the record's own relative form, sorted, and follows nothing out", async () => {
  const root = await mkdtemp(join(tmpdir(), "akmon-vendor-walk-"));
  const dir = join(root, "vendor");
  const elsewhere = join(root, "elsewhere");
  try {
    await mkdir(join(dir, "dist"), { recursive: true });
    await mkdir(join(dir, "notes"), { recursive: true });
    await mkdir(join(elsewhere, "inner"), { recursive: true });
    await writeFile(join(dir, "LICENSE"), "l");
    await writeFile(join(dir, "dist", "index.js"), "i");
    await writeFile(join(elsewhere, "inner", "escape.js"), "e");
    await symlink(join(elsewhere, "inner"), join(dir, "outside"), "dir");
    await symlink(join(elsewhere, "inner", "escape.js"), join(dir, "link.js"), "file");

    const listing = await _listing(dir);
    // `notes/` is unexpected and empty, so it reaches no listing at all: the ledger's silence on
    // an empty directory is the decision above, not a hole in the walk.
    assert.deepStrictEqual(listing.files, ["LICENSE", "dist/index.js"]);
    // Both links are named and neither was read through — `escape.js` is outside `dir` and is
    // nowhere here, so no pin of a file in this directory can hash bytes that live elsewhere.
    assert.deepStrictEqual(listing.other, ["link.js", "outside"]);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});
