/**
 * node:test for `js/common/record.mjs` — every case of the shared units table
 * (`meta/conformance/units/record.toml`) iterated on the host, plus the named pins the
 * twin carries: the BOM fold (C101), an absent record, the strict reader's `RecordError`,
 * and bytes that are not valid UTF-8 — the one input the units table cannot hold, since it
 * is itself a text file.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import { posix } from "node:path";

import { parse as parseToml } from "../vendor/smol-toml/dist/index.js";
import {
  readAkmonToml, readAkmonTomlStrict, recordedMount, recordsPackageMode, stripInlineComment, RecordError } from "./record.mjs";

const _UNITS = new URL("../../meta/conformance/units/record.toml", import.meta.url);

/** The table read once, so the cases and the strip pins come from one source. */
function _units() {
  // The cast only admits the read; the shape is asserted case by case. The unknown bridge
  // is needed because the parser's own return type is the generic table.
  const parsed = /** @type {unknown} */ (parseToml(fs.readFileSync(_UNITS, "utf8")));
  return /** @type {{case: Array<{text?: string, absent?: boolean, expected: Record<string, unknown>}>, strip: Array<{input: string, expected: string}>}} */ (
    parsed
  );
}

/** The empty-table answer the readers return for an absent record (null-prototype, as `parse` builds tables). */
function _emptyTable() {
  return Object.create(null);
}

/** A temp record file; when `content` is `null` the file is left absent. */
function _recordFile(/** @type {string} */ dir, /** @type {string | null} */ content) {
  const path = posix.join(dir, ".akmon.toml");
  // The cases share one path: clear the previous case's file so an absent case is truly absent.
  fs.rmSync(path, { force: true });
  if (content !== null) {
    fs.writeFileSync(path, content);
  }
  return path;
}

test("every case of the units table: lenient degrades, strict refuses per the table", () => {
  const units = _units();
  assert.ok(units.case.length > 0, "the units table carries cases");
  const dir = fs.mkdtempSync(posix.join(os.tmpdir(), "akmon-record-units-"));
  try {
    units.case.forEach((unitCase, i) => {
      const path = _recordFile(dir, unitCase.absent ? null : /** @type {string} */ (unitCase.text));
      const expected = /** @type {{lenient?: Record<string, unknown>, strict?: Record<string, unknown>, strict_ok?: boolean}} */ (unitCase.expected);
      // An expected field left out is the null answer (TOML has no null): no lenient
      // value means the empty table, no strict value means the strict reader raised.
      assert.deepStrictEqual(readAkmonToml(path), expected.lenient ?? _emptyTable(), `case ${i}: lenient`);
      if (expected.strict_ok) {
        assert.deepStrictEqual(readAkmonTomlStrict(path), expected.strict ?? _emptyTable(), `case ${i}: strict`);
      } else {
        assert.throws(() => readAkmonTomlStrict(path), RecordError, `case ${i}: strict refuses`);
      }
    });
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});

test("every strip case of the units table pins the quote-aware comment rule", () => {
  const units = _units();
  assert.ok(units.strip.length > 0, "the units table carries strip cases");
  units.strip.forEach((stripCase, i) => {
    assert.equal(stripInlineComment(stripCase.input), stripCase.expected, `strip ${i}`);
  });
});

test("a leading BOM stays out of the first key (C101), strict and lenient included", () => {
  const dir = fs.mkdtempSync(posix.join(os.tmpdir(), "akmon-record-bom-"));
  const saved = process.env.AITNA_ROOT;
  delete process.env.AITNA_ROOT;
  try {
    const root = dir;
    fs.mkdirSync(posix.join(root, "_aitna"));
    const record = posix.join(root, "_aitna", ".akmon.toml");
    // Well-formed save with a BOM: the record must still declare its mount.
    fs.writeFileSync(record, "\uFEFFmount = \"package\"\n");
    assert.equal(recordedMount(root), "package");
    assert.equal(recordsPackageMode(root), true);
    // The line parser itself — the path that used to fold the BOM into the key, forced
    // here by a header that `parse` refuses.
    fs.writeFileSync(record, "\uFEFFmount = \"package\"\n[broke =\n");
    assert.equal(/** @type {Record<string, unknown>} */ (readAkmonToml(record))["mount"], "package");
    // And strict must refuse the BOM the way tomllib does, not fold it in silently.
    assert.throws(() => readAkmonTomlStrict(record), RecordError);
  } finally {
    if (saved !== undefined) {
      process.env.AITNA_ROOT = saved;
    }
    fs.rmSync(dir, { recursive: true, force: true });
  }
});

test("an absent record reads as nothing, and vetoes nothing", () => {
  const dir = fs.mkdtempSync(posix.join(os.tmpdir(), "akmon-record-absent-"));
  try {
    const record = posix.join(dir, "_aitna", ".akmon.toml");
    assert.deepStrictEqual(readAkmonToml(record), _emptyTable());
    assert.deepStrictEqual(readAkmonTomlStrict(record), _emptyTable());
    const saved = process.env.AITNA_ROOT;
    delete process.env.AITNA_ROOT;
    try {
      assert.equal(recordedMount(dir), null);
      assert.equal(recordsPackageMode(dir), false);
    } finally {
      if (saved !== undefined) {
        process.env.AITNA_ROOT = saved;
      }
    }
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});

test("an empty mount declares nothing: null, not a default", () => {
  const dir = fs.mkdtempSync(posix.join(os.tmpdir(), "akmon-record-empty-"));
  const saved = process.env.AITNA_ROOT;
  delete process.env.AITNA_ROOT;
  try {
    fs.mkdirSync(posix.join(dir, "_aitna"));
    fs.writeFileSync(posix.join(dir, "_aitna", ".akmon.toml"), 'mount = ""\n');
    assert.equal(recordedMount(dir), null);
    assert.equal(recordsPackageMode(dir), false);
  } finally {
    if (saved !== undefined) {
      process.env.AITNA_ROOT = saved;
    }
    fs.rmSync(dir, { recursive: true, force: true });
  }
});

test("a strict RecordError names the file and where the parse failed", () => {
  const dir = fs.mkdtempSync(posix.join(os.tmpdir(), "akmon-record-strict-"));
  try {
    const record = _recordFile(dir, "mount = \"a\"\n[broke =\n");
    assert.throws(
      () => readAkmonTomlStrict(record),
      (/** @type {unknown} */ err) => {
        assert.ok(err instanceof RecordError);
        assert.match(/** @type {Error} */ (err).message, /^\.akmon\.toml cannot be read as TOML: parse failed at line \d+, column \d+: /);
        return true;
      },
    );
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});

test("bytes that are not UTF-8 degrade leniently and are refused strictly", () => {
  const dir = fs.mkdtempSync(posix.join(os.tmpdir(), "akmon-record-utf8-"));
  try {
    // The bytes have to reach the disk as 0xff 0xfe: `latin1` maps each code unit to the byte of
    // the same value, while a source-encoded U+FFFD is valid UTF-8 and would test the
    // substitution instead of the refusal. `readFileSync(path, "utf8")` never throws on them —
    // it replaces each invalid sequence — and the lenient line-parser fallback then read that
    // substituted value back out as if the record said it.
    const record = posix.join(dir, ".akmon.toml");
    fs.writeFileSync(record, Buffer.from('[akmon]\nname = "\xff\xfe bad"\n', "latin1"));
    assert.deepStrictEqual(readAkmonToml(record), _emptyTable());
    assert.throws(
      () => readAkmonTomlStrict(record),
      (/** @type {unknown} */ err) => {
        assert.ok(err instanceof RecordError);
        assert.match(/** @type {Error} */ (err).message, /^\.akmon\.toml cannot be read as TOML: invalid UTF-8/);
        return true;
      },
    );
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});
