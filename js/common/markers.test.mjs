/**
 * node:test for `js/common/markers.mjs` — the named pins of the twin: the claim contract on a
 * real directory, the marker name and mode, the tempdir the stdlib would answer, and the places
 * Python and Node part ways (lone surrogates, inherited object keys, replacement patterns). The
 * full spec is `meta/conformance/units/markers.toml`, run through `probe.mjs`.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import { posix } from "node:path";

import {
  MARKER_MAX_AGE_SECONDS, claimDiagnosticMarker, delegationStateName, gettempdir, markerKind,
  releaseDiagnosticMarkers, unidentifiedIdentity } from "./markers.mjs";

const data = JSON.parse(fs.readFileSync(new URL("../../common/markers.json", import.meta.url), "utf-8"));

/** Run `body` with a fresh directory, removed after. */
function withDir(/** @type {(dir: string) => void} */ body) {
  const dir = fs.mkdtempSync(posix.join(os.tmpdir(), "akmon-markers-test-"));
  try {
    body(dir);
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
}

/** Run `body` with the three tempdir variables set as given (`null`: unset), then restored. */
function withTempEnv(
  /** @type {Record<string, string | null>} */ values,
  /** @type {() => void} */ body,
) {
  const names = ["TMPDIR", "TEMP", "TMP"];
  const saved = names.map((name) => process.env[name]);
  try {
    for (const name of names) {
      const value = values[name] ?? null;
      if (value === null) {
        delete process.env[name];
      } else {
        process.env[name] = value;
      }
    }
    body();
  } finally {
    names.forEach((name, i) => {
      if (saved[i] === undefined) {
        delete process.env[name];
      } else {
        process.env[name] = saved[i];
      }
    });
  }
}

test("a claim is atomic: the first emits, the repeat is silent, each identity and kind its own", () => {
  withDir((directory) => {
    assert.equal(claimDiagnosticMarker(data, "shell-route", "s1", { directory }), true);
    assert.equal(claimDiagnosticMarker(data, "shell-route", "s1", { directory }), false);
    assert.equal(claimDiagnosticMarker(data, "shell-route", "s2", { directory }), true);
    assert.equal(claimDiagnosticMarker(data, "role-on-code", "s1", { directory }), true);
    assert.equal(fs.readdirSync(directory).length, 3);
  });
});

test("an identity the throttle cannot key by repeats and leaves nothing behind", () => {
  withDir((directory) => {
    for (const identity of [null, undefined, "", unidentifiedIdentity(data)]) {
      assert.equal(claimDiagnosticMarker(data, "shell-route", identity, { directory }), true);
      assert.equal(claimDiagnosticMarker(data, "shell-route", identity, { directory }), true);
    }
    assert.deepEqual(fs.readdirSync(directory), []);
  });
});

test("the marker is a flat, hashed name with mode 0600 whatever the identity holds", () => {
  withDir((directory) => {
    const previous = process.umask(0o022);
    try {
      claimDiagnosticMarker(data, "shell-route", "../../escape/me", { directory });
    } finally {
      process.umask(previous);
    }
    const [name, ...rest] = fs.readdirSync(directory);
    assert.deepEqual(rest, []);
    assert.match(name, /^akmon-shell-route-[0-9a-f]{20}$/);
    assert.equal(fs.statSync(posix.join(directory, name)).mode & 0o777, 0o600);
  });
});

test("a marker older than a day is replaced; one inside the day is kept", () => {
  withDir((directory) => {
    claimDiagnosticMarker(data, "shell-route", "s1", { directory });
    const file = posix.join(directory, fs.readdirSync(directory)[0]);
    const age = (/** @type {number} */ seconds) => {
      const moment = Date.now() / 1000 - seconds;
      fs.utimesSync(file, moment, moment);
    };
    age(MARKER_MAX_AGE_SECONDS + 60);
    assert.equal(claimDiagnosticMarker(data, "shell-route", "s1", { directory }), true);
    assert.equal(claimDiagnosticMarker(data, "shell-route", "s1", { directory }), false);
    age(MARKER_MAX_AGE_SECONDS - 60);
    assert.equal(claimDiagnosticMarker(data, "shell-route", "s1", { directory }), false);
  });
});

test("a marker that cannot be created makes the diagnostic noisier, never invisible", () => {
  withDir((directory) => {
    const missing = posix.join(directory, "gone");
    assert.equal(claimDiagnosticMarker(data, "shell-route", "s1", { directory: missing }), true);
    assert.equal(claimDiagnosticMarker(data, "shell-route", "s1", { directory: missing }), true);
    releaseDiagnosticMarkers(data, "shell-route", "s1", { directory: missing });
  });
});

test("release removes this identity's markers by kind prefix and spares keepKind", () => {
  withDir((directory) => {
    for (const kind of ["role-on-code", "role-on-code-x", "role-on-code-y", "shell-route"]) {
      claimDiagnosticMarker(data, kind, "s1", { directory });
    }
    claimDiagnosticMarker(data, "role-on-code", "s2", { directory });
    releaseDiagnosticMarkers(data, "role-on-code", "s1", { keepKind: "role-on-code-y", directory });
    assert.equal(claimDiagnosticMarker(data, "role-on-code-x", "s1", { directory }), true);
    assert.equal(claimDiagnosticMarker(data, "role-on-code-y", "s1", { directory }), false);
    assert.equal(claimDiagnosticMarker(data, "role-on-code", "s2", { directory }), false);
    assert.equal(claimDiagnosticMarker(data, "shell-route", "s1", { directory }), false);
  });
});

test("an identity with a lone surrogate is refused, as Python's encode() refuses it", () => {
  withDir((directory) => {
    assert.throws(() => claimDiagnosticMarker(data, "shell-route", "a\ud800b", { directory }), TypeError);
    assert.deepEqual(fs.readdirSync(directory), []);
  });
});

test("the vocabulary comes from the data file, and a miss is a refusal, not an inherited member", () => {
  assert.equal(markerKind(data, "shell_route"), "shell-route");
  for (const stem of ["", "shell-route", "constructor", "__proto__", "toString"]) {
    assert.throws(() => markerKind(data, stem), /no marker kind/);
  }
  assert.equal(unidentifiedIdentity(data), "nosession");
});

test("a delegation state name carries the identity as written, replacement patterns included", () => {
  assert.equal(delegationStateName(data, "counter", "abc"), "akmon-delegation-nudge-abc.count");
  assert.equal(delegationStateName(data, "marker", "{{identity}}$&$1"), "akmon-delegation-nudge-{{identity}}$&$1.marker");
  assert.throws(() => delegationStateName(data, "constructor", "abc"), /no delegation state file/);
});

test("the tempdir is the stdlib's: TMPDIR, then TEMP, then TMP — not Node's TMPDIR, TMP, TEMP", () => {
  withDir((root) => {
    const [a, b, c] = ["a", "b", "c"].map((name) => {
      fs.mkdirSync(posix.join(root, name));
      return posix.join(root, name);
    });
    withTempEnv({ TMPDIR: a, TEMP: b, TMP: c }, () => assert.equal(gettempdir(), a));
    withTempEnv({ TEMP: b, TMP: c }, () => assert.equal(gettempdir(), b));
    withTempEnv({ TMP: c }, () => assert.equal(gettempdir(), c));
    withTempEnv({ TMPDIR: "", TEMP: b }, () => assert.equal(gettempdir(), b));
    withTempEnv({ TMPDIR: posix.join(root, "gone"), TEMP: b }, () => assert.equal(gettempdir(), b));
    withTempEnv({ TMPDIR: `${a}/../b/` }, () => assert.equal(gettempdir(), b));
    withTempEnv({}, () => assert.equal(gettempdir(), "/tmp"));
  });
});

test("a candidate that cannot take a file is passed over", { skip: process.getuid?.() === 0 }, () => {
  withDir((root) => {
    const a = posix.join(root, "a");
    const b = posix.join(root, "b");
    fs.mkdirSync(a);
    fs.mkdirSync(b);
    fs.chmodSync(a, 0o500);
    try {
      withTempEnv({ TMPDIR: a, TEMP: b }, () => assert.equal(gettempdir(), b));
    } finally {
      fs.chmodSync(a, 0o700);
    }
  });
});
