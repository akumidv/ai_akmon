/**
 * node:test for `js/common/findings.mjs` — the named pins of the twin: the frozen envelope, its
 * serialization, the data file and what is read from it, the stdout writer and the exit matrix.
 * The validation messages and the rendered line are the spec of
 * `meta/conformance/units/findings.toml`, run through `probe.mjs`; what the generic mouth cannot
 * reach (`printFindings` writes stdout, `toDict` is a method, an argument the options object
 * leaves out) is here.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

import {
  CODE_RE,
  Finding,
  exitCode,
  lineSafe,
  printFindings,
  readFindingsData,
  render,
  retiredCodes,
  severities,
} from "./findings.mjs";

const DATA_FILE = new URL("../../common/findings.json", import.meta.url);

/** A finding of the given severity; every other field is a valid constant. */
function finding(
  /** @type {string} */ severity = "warn",
  /** @type {Partial<import("./findings.mjs").FindingFields>} */ over = {},
) {
  return new Finding({
    severity,
    code: "area.rule",
    message: "something is off",
    target: "meta/x.md",
    fix: "Fix it",
    ...over,
  });
}

/** What `printFindings` writes while `body` runs (`process.stdout.write` swapped out, then restored). */
function captured(/** @type {() => void} */ body) {
  const write = process.stdout.write;
  /** @type {string[]} */
  const chunks = [];
  process.stdout.write = /** @type {typeof process.stdout.write} */ (
    (/** @type {string | Uint8Array} */ chunk) => {
      chunks.push(String(chunk));
      return true;
    }
  );
  try {
    body();
  } finally {
    process.stdout.write = write;
  }
  return chunks.join("");
}

test("the data file read by the module is the shipped common/findings.json", () => {
  const onDisk = JSON.parse(fs.readFileSync(DATA_FILE, "utf-8"));
  assert.deepEqual(readFindingsData(), onDisk);
  assert.deepEqual(severities(), ["ok", "warn", "error"]);
  assert.ok(retiredCodes().has("hooks.package-mode"));
});

test("a vocabulary handed in is the one used, and the returned values are not the data's own", () => {
  const data = { severities: ["a", "b"], retired_codes: ["x.y"], render: readFindingsData().render };
  assert.deepEqual(severities(data), ["a", "b"]);
  assert.deepEqual([...retiredCodes(data)], ["x.y"]);
  assert.throws(() => /** @type {string[]} */ (severities(data)).push("c"), TypeError);
  assert.deepEqual(data.severities, ["a", "b"]);
  assert.equal(finding("b", { data }).severity, "b");
});

test("a finding is frozen and carries exactly the five fields", () => {
  const f = finding();
  assert.deepEqual(Object.keys(f), ["severity", "code", "message", "target", "fix"]);
  assert.ok(Object.isFrozen(f));
  assert.throws(() => {
    /** @type {{severity: string}} */ (f).severity = "error";
  }, TypeError);
  assert.equal(f.severity, "warn");
});

test("toDict is the one serialization: five fields, a fresh object, no level key", () => {
  const f = finding("error", { target: "" });
  const first = f.toDict();
  assert.deepEqual(first, {
    severity: "error",
    code: "area.rule",
    message: "something is off",
    target: "",
    fix: "Fix it",
  });
  assert.deepEqual(Object.keys(first), ["severity", "code", "message", "target", "fix"]);
  first.message = "changed";
  assert.equal(f.toDict().message, "something is off");
  assert.notEqual(f.toDict(), f.toDict());
  assert.ok(!("level" in first) && !("data" in first));
});

test("an argument the options object leaves out is the TypeError Python raises, spelled as Python spells it", () => {
  const whole = { severity: "ok", code: "a.b", message: "m", target: "", fix: "Do it" };
  const without = (/** @type {string[]} */ ...names) =>
    Object.fromEntries(Object.entries(whole).filter(([key]) => !names.includes(key)));
  const message = (/** @type {Record<string, string>} */ fields) => {
    try {
      new Finding(/** @type {any} */ (fields));
    } catch (exc) {
      return `${/** @type {Error} */ (exc).name}: ${/** @type {Error} */ (exc).message}`;
    }
    return "no error";
  };
  assert.equal(message(without("fix")), "TypeError: Finding.__init__() missing 1 required positional argument: 'fix'");
  assert.equal(
    message(without("message", "target")),
    "TypeError: Finding.__init__() missing 2 required positional arguments: 'message' and 'target'",
  );
  assert.equal(
    message(without("code", "target", "fix")),
    "TypeError: Finding.__init__() missing 3 required positional arguments: 'code', 'target', and 'fix'",
  );
  assert.equal(
    message({ ...whole, level: "x" }),
    "TypeError: Finding.__init__() got an unexpected keyword argument 'level'",
  );
  assert.equal(message({ ...whole, data: /** @type {any} */ (null) }), "no error");
  // `null` is a value (Python's `None`) and reaches the validation; only an absent field is a TypeError.
  assert.equal(
    message({ ...whole, fix: /** @type {any} */ (null) }),
    "ValueError: fix is required and must be non-empty, got None",
  );
});

test("the validation messages quote with Python's repr", () => {
  assert.throws(() => finding("fatal"), {
    name: "ValueError",
    message: "severity must be one of ok | warn | error, got 'fatal'",
  });
  assert.throws(() => finding("warn", { code: "Area.rule" }), {
    name: "ValueError",
    message: "code must be a dotted slug like 'area.rule', got 'Area.rule'",
  });
  assert.throws(() => finding("warn", { code: "hooks.package-mode" }), {
    name: "ValueError",
    message: "code 'hooks.package-mode' is retired and must not be reused by a live check",
  });
  assert.throws(() => finding("warn", { message: " \u00a0" }), {
    name: "ValueError",
    message: "message must be non-empty, got ' \\xa0'",
  });
  assert.throws(() => finding("warn", { target: "a\nb" }), {
    name: "ValueError",
    message: "target must be one line, got 'a\\nb'",
  });
  assert.throws(() => finding("warn", { fix: "Do this. Then that" }), {
    name: "ValueError",
    message: "fix must be one sentence, got 'Do this. Then that'",
  });
});

test("the sentence boundary is ASCII whitespace: a no-break space after a full stop is text", () => {
  const nbsp = String.fromCharCode(0xa0);
  assert.equal(finding("warn", { fix: `Do this.${nbsp}then that` }).fix, `Do this.${nbsp}then that`);
  assert.equal(finding("warn", { fix: "Do this. " }).fix, "Do this. ");
  assert.throws(() => finding("warn", { fix: "Do this. then that" }), { name: "ValueError" });
  assert.throws(() => finding("warn", { fix: "Do this.\tthen that" }), { name: "ValueError" });
});

test("every logical line separator is refused in message, target and fix", () => {
  const separators = [
    "\n",
    "\r",
    "\v",
    "\f",
    "\x1c",
    "\x1d",
    "\x1e",
    "\x85",
    String.fromCharCode(0x2028),
    String.fromCharCode(0x2029),
  ];
  for (const separator of separators) {
    for (const field of /** @type {const} */ (["message", "target", "fix"])) {
      assert.throws(
        () => finding("warn", { [field]: `a${separator}b` }),
        { name: "ValueError" },
        `${field} ${separator.charCodeAt(0)}`,
      );
    }
  }
});

test("lineSafe escapes the ten separators and nothing else", () => {
  assert.equal(lineSafe("a\nb\rc\vd\fe"), "a\\nb\\rc\\vd\\fe");
  assert.equal(lineSafe("\x1c\x1d\x1e\x85"), "\\u001c\\u001d\\u001e\\u0085");
  assert.equal(lineSafe(`${String.fromCharCode(0x2028)}${String.fromCharCode(0x2029)}`), "\\u2028\\u2029");
  assert.equal(lineSafe("plain é\u00a0 \\n \x1f"), "plain é\u00a0 \\n \x1f");
  // Called twice in a row: the global pattern behind it must not carry `lastIndex` over.
  assert.equal(lineSafe("a\nb"), lineSafe("a\nb"));
});

test("CODE_RE is the dotted-slug pattern, anchored at both ends", () => {
  assert.ok(CODE_RE.test("caps.always-loaded"));
  assert.ok(!CODE_RE.test("caps.always-loaded\n"));
  assert.ok(!CODE_RE.test("x caps.always"));
  assert.ok(!CODE_RE.test("caps"));
});

test("render: upper-cased severity, the target slot collapses, the skeleton is the data file's", () => {
  assert.equal(render(finding("ok")), "OK area.rule meta/x.md: something is off → Fix it");
  assert.equal(render(finding("error", { target: "" })), "ERROR area.rule: something is off → Fix it");
  const data = readFindingsData();
  data.render = {
    head: "{{code}}/{{severity}}",
    head_with_target: "{{head}}@{{target}}",
    line: "{{message}} <- {{head}}",
  };
  assert.equal(render(finding("ok"), data), "something is off <- area.rule/OK@meta/x.md");
});

test("render does not re-scan what it filled, and $ patterns in a value stay text", () => {
  const f = finding("ok", { message: "see {{head}} for $& and $1", target: "{{message}}", fix: "Pay $$" });
  assert.equal(render(f), "OK area.rule {{message}}: see {{head}} for $& and $1 → Pay $$");
});

test("printFindings writes one canonical line per finding; quiet drops the ok ones", () => {
  const findings = [finding("ok"), finding("warn", { target: "" }), finding("error")];
  assert.equal(
    captured(() => printFindings(findings)),
    "OK area.rule meta/x.md: something is off → Fix it\n" +
      "WARN area.rule: something is off → Fix it\n" +
      "ERROR area.rule meta/x.md: something is off → Fix it\n",
  );
  assert.equal(
    captured(() => printFindings(findings, { quiet: true })),
    "WARN area.rule: something is off → Fix it\nERROR area.rule meta/x.md: something is off → Fix it\n",
  );
  assert.equal(
    captured(() => printFindings([], {})),
    "",
  );
  assert.equal(
    captured(() => printFindings([finding("ok")], { quiet: true })),
    "",
  );
});

test("printFindings takes any iterable", () => {
  function* generated() {
    yield finding("error");
  }
  assert.equal(
    captured(() => printFindings(generated())),
    "ERROR area.rule meta/x.md: something is off → Fix it\n",
  );
});

test("exitCode: errors fail; warnings fail only under strict", () => {
  const [ok, warn, error] = [finding("ok"), finding("warn"), finding("error")];
  for (const [findings, plain, strict] of /** @type {Array<[Finding[], number, number]>} */ ([
    [[], 0, 0],
    [[ok], 0, 0],
    [[warn], 0, 1],
    [[error], 1, 1],
    [[ok, warn], 0, 1],
    [[warn, error], 1, 1],
    [[ok, warn, error], 1, 1],
  ])) {
    assert.equal(exitCode(findings), plain);
    assert.equal(exitCode(findings, {}), plain);
    assert.equal(exitCode(findings, { strict: false }), plain);
    assert.equal(exitCode(findings, { strict: true }), strict);
  }
});
