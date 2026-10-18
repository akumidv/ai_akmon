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
  MARKER_FUTURE_SLACK_SECONDS,
  MARKER_MAX_AGE_SECONDS,
  claimDiagnosticMarker,
  delegationStateName,
  gettempdir,
  markerKind,
  releaseDiagnosticMarkers,
  unidentifiedIdentity,
} from "./markers.mjs";

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
function withTempEnv(/** @type {Record<string, string | null>} */ values, /** @type {() => void} */ body) {
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

/** Set `file`'s mtime `seconds` in the past (a negative value: in the future). */
function age(/** @type {string} */ file, /** @type {number} */ seconds) {
  const moment = Date.now() / 1000 - seconds;
  fs.utimesSync(file, moment, moment);
}

/** Claim once in `directory` and return the path of the marker that claim left. */
function claimed(/** @type {string} */ directory) {
  assert.equal(claimDiagnosticMarker(data, "shell-route", "s1", { directory }), true);
  const [name] = fs.readdirSync(directory);
  return posix.join(directory, name);
}

test("a marker dated ahead of the clock is stale once past the slack", () => {
  withDir((directory) => {
    const file = claimed(directory);
    age(file, -(MARKER_FUTURE_SLACK_SECONDS / 2)); // a coarse timestamp: still held
    assert.equal(claimDiagnosticMarker(data, "shell-route", "s1", { directory }), false);
    age(file, -3600); // a clock that moved back an hour: no longer suppresses for days
    assert.equal(claimDiagnosticMarker(data, "shell-route", "s1", { directory }), true);
    assert.equal(claimDiagnosticMarker(data, "shell-route", "s1", { directory }), false);
  });
});

test("a symlink at the marker path is not followed and speaks", () => {
  withDir((directory) => {
    const file = claimed(directory);
    const target = posix.join(directory, "target.txt");
    fs.renameSync(file, target); // a fresh regular file of ours: followed, it would read as held
    fs.symlinkSync(target, file);
    assert.equal(claimDiagnosticMarker(data, "shell-route", "s1", { directory }), true);
    assert.equal(claimDiagnosticMarker(data, "shell-route", "s1", { directory }), true);
    assert.equal(fs.lstatSync(file).isSymbolicLink(), true); // the planted path is left alone
    assert.equal(fs.lstatSync(target).isFile(), true);
  });
});

test("a directory at the marker path speaks and stays", () => {
  withDir((directory) => {
    const file = claimed(directory);
    fs.unlinkSync(file);
    fs.mkdirSync(file);
    assert.equal(claimDiagnosticMarker(data, "shell-route", "s1", { directory }), true);
    assert.equal(fs.lstatSync(file).isDirectory(), true);
  });
});

/** Run `body` with `process.getuid` replaced by `getuid` (`undefined`: absent), then restored. */
function withUid(/** @type {(() => number) | undefined} */ getuid, /** @type {() => void} */ body) {
  const saved = Object.getOwnPropertyDescriptor(process, "getuid");
  try {
    Object.defineProperty(process, "getuid", { value: getuid, configurable: true, writable: true });
    body();
  } finally {
    if (saved) {
      Object.defineProperty(process, "getuid", saved);
    } else {
      delete process.getuid;
    }
  }
}

test("a marker another user owns is not our claim", { skip: typeof process.getuid !== "function" }, () => {
  withDir((directory) => {
    const file = claimed(directory);
    const realUid = /** @type {() => number} */ (process.getuid)();
    withUid(
      () => realUid + 1, // a chown needs privilege: fake the uid instead
      () => assert.equal(claimDiagnosticMarker(data, "shell-route", "s1", { directory }), true),
    );
    assert.equal(fs.lstatSync(file).isFile(), true); // someone else's file is not ours to replace
    assert.equal(claimDiagnosticMarker(data, "shell-route", "s1", { directory }), false);
  });
});

test("without user ids a regular file is enough", () => {
  withDir((directory) => {
    claimed(directory);
    withUid(undefined, () => assert.equal(claimDiagnosticMarker(data, "shell-route", "s1", { directory }), false));
  });
});

/** Run `body` with `fs.lstatSync` replaced by `lstat`, then restored. */
function withLstat(/** @type {(file: string) => fs.Stats} */ lstat, /** @type {() => void} */ body) {
  const patched = /** @type {{lstatSync: unknown}} */ (/** @type {unknown} */ (fs));
  const saved = fs.lstatSync;
  try {
    patched.lstatSync = lstat;
    body();
  } finally {
    patched.lstatSync = saved;
  }
}

/** A Node system error with `code` and `errno`, as `fs` throws it. */
function systemError(/** @type {string} */ code, /** @type {number} */ errno) {
  return Object.assign(new Error(`${code}: faked`), { code, errno: -errno });
}

test("a marker that vanishes before its lstat is claimed again", () => {
  withDir((directory) => {
    const file = claimed(directory);
    const real = fs.lstatSync;
    let calls = 0;
    withLstat(
      (path) => {
        calls += 1;
        if (path === file && calls === 1) {
          fs.unlinkSync(file); // another process aged it out between the create and the lstat
        }
        return real(path);
      },
      () => assert.equal(claimDiagnosticMarker(data, "shell-route", "s1", { directory }), true),
    );
    assert.equal(calls, 1);
    assert.equal(fs.lstatSync(file).isFile(), true);
    assert.equal(claimDiagnosticMarker(data, "shell-route", "s1", { directory }), false);
  });
});

test("a marker that keeps vanishing still emits", () => {
  withDir((directory) => {
    claimed(directory);
    withLstat(
      () => {
        throw systemError("ENOENT", 2);
      },
      () => assert.equal(claimDiagnosticMarker(data, "shell-route", "s1", { directory }), true),
    );
  });
});

test("an unreadable existing marker is noisier, never silent", () => {
  withDir((directory) => {
    claimed(directory);
    withLstat(
      () => {
        throw systemError("EACCES", 13);
      },
      () => assert.equal(claimDiagnosticMarker(data, "shell-route", "s1", { directory }), true),
    );
    assert.equal(fs.readdirSync(directory).length, 1); // nothing removed
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
    assert.throws(() => claimDiagnosticMarker(data, "shell-route", "a\ud800b", { directory }), {
      name: "UnicodeEncodeError",
    });
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
  assert.equal(
    delegationStateName(data, "marker", "{{identity}}$&$1"),
    "akmon-delegation-nudge-{{identity}}$&$1.marker",
  );
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

test("a falsy identity of any JSON type is no identity: claim repeats, release does nothing", () => {
  withDir((dir) => {
    for (const empty of [null, undefined, "", 0, false, [], {}]) {
      assert.equal(claimDiagnosticMarker(data, "k", /** @type {any} */ (empty), { directory: dir }), true);
      assert.equal(claimDiagnosticMarker(data, "k", /** @type {any} */ (empty), { directory: dir }), true);
      releaseDiagnosticMarkers(data, "k", /** @type {any} */ (empty), { directory: dir });
    }
    assert.deepEqual(fs.readdirSync(dir), []);
  });
});

test("a truthy non-string identity is the AttributeError of `identity.encode()`, and writes nothing", () => {
  withDir((dir) => {
    for (const bad of [1, 1.5, true, ["x"], { a: 1 }]) {
      assert.throws(() => claimDiagnosticMarker(data, "k", /** @type {any} */ (bad), { directory: dir }), {
        name: "AttributeError",
      });
      assert.throws(() => releaseDiagnosticMarkers(data, "k", /** @type {any} */ (bad), { directory: dir }), {
        name: "AttributeError",
      });
    }
    assert.deepEqual(fs.readdirSync(dir), []);
  });
});
