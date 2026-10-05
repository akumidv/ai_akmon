/**
 * Once-per-identity diagnostic markers in the system tempdir — the JavaScript twin of
 * `common/markers.py` (ADR 0020 D01); `units/markers.toml` is the spec both must pass. A hook
 * is a fresh process per event, so "say this once per session" needs state outside the
 * process, and every such marker is claimed here: an atomic claim (`O_CREAT | O_EXCL`), a
 * hashed name with mode 0600, a repeat when the identity is unknown, and an age-out after a day.
 * A marker failure makes the diagnostic noisier, never invisible.
 *
 * Data (the C102/C103 convention): this module never reads a file itself. `data` is the parsed
 * `common/markers.json` (name shape, kinds, the unidentified spelling, the delegation
 * state-file templates), read once by the caller at its entry point and passed down.
 *
 * Twin notes, each a place where the stdlib answers differently from Node's:
 * - the tempdir is `gettempdir` below, a port of `tempfile.gettempdir` (TMPDIR, TEMP, TMP in
 *   that order, then /tmp, /var/tmp, /usr/tmp and the cwd, each proven writable) — `os.tmpdir`
 *   reads TMPDIR, TMP, TEMP and probes nothing;
 * - `str.encode()` raises on a lone surrogate where Node would hash U+FFFD, so the identity is
 *   refused the same way (a session id the JSON payload spelled `"\ud800"`);
 * - `Path.glob` matches a name with `fnmatch.translate`, so the release prefix is a pattern —
 *   `fnmatchCase`, the same port the check runner uses; kinds and prefixes are code constants,
 *   never user text, and each is one path component;
 * - a dict lookup that misses raises `KeyError`; here `Object.hasOwn` guards the lookup (a stem
 *   named `constructor` is a miss, not a function) and the error says which stem.
 */

import { createHash, randomInt } from "node:crypto";
import fs from "node:fs";
import { posix } from "node:path";

import { fnmatchCase } from "./glob.mjs";
import { fill } from "./jsondata.mjs";

/** A day: longer than a working session, short enough that a crashed or reused session id does
 * not suppress a diagnostic for long. */
export const MARKER_MAX_AGE_SECONDS = 24 * 60 * 60;

/**
 * The shape of `common/markers.json` — the data file is the owner of these keys.
 * @typedef {object} MarkersData
 * @property {string} name_prefix
 * @property {number} name_sha256_tail
 * @property {string} unidentified
 * @property {Record<string, string>} kinds
 * @property {Record<string, string>} delegation_state_files
 */

/**
 * Whether `error` is a filesystem failure — Python's `OSError`. A non-system error (an
 * argument Node refuses, which Python raises as `ValueError`) is not one and is never swallowed.
 * @param {unknown} error
 * @returns {boolean}
 */
function _isOSError(error) {
  return error instanceof Error && typeof (/** @type {{errno?: unknown}} */ (error).errno) === "number";
}

/** `base/name` with nothing normalized — `Path("")` is the cwd, so an empty base is `.`. */
function _under(/** @type {string} */ base, /** @type {string} */ name) {
  return `${base || "."}/${name}`;
}

/**
 * `tempfile.gettempdir()` ported: the first candidate directory a scratch file can be created
 * and written in. Candidates are the non-empty `TMPDIR`, `TEMP`, `TMP`, then `/tmp`,
 * `/var/tmp`, `/usr/tmp`, then the cwd (`.` when even that cannot be read). Python keeps the
 * answer for the life of the process; a hook is one process and this is not cached, so the
 * environment is read where the answer is asked for.
 * @returns {string}
 */
export function gettempdir() {
  /** @type {string[]} */
  const candidates = [];
  for (const name of ["TMPDIR", "TEMP", "TMP"]) {
    const declared = process.env[name];
    if (declared) {
      candidates.push(declared);
    }
  }
  candidates.push("/tmp", "/var/tmp", "/usr/tmp");
  try {
    candidates.push(process.cwd());
  } catch {
    candidates.push(".");
  }
  const characters = "abcdefghijklmnopqrstuvwxyz0123456789_";
  for (const candidate of candidates) {
    const directory = candidate === "." ? candidate : posix.resolve(candidate);
    for (let attempt = 0; attempt < 100; attempt++) {
      let name = "tmp";
      for (let i = 0; i < 8; i++) {
        name += characters[randomInt(characters.length)];
      }
      const scratch = _under(directory, name);
      let descriptor;
      try {
        descriptor = fs.openSync(scratch, "wx+", 0o600);
      } catch (error) {
        if (/** @type {{code?: string}} */ (error).code === "EEXIST") {
          continue; // a file of that name exists: try another name here
        }
        break; // no point trying more names in this directory
      }
      try {
        fs.writeSync(descriptor, "blat");
        return directory;
      } catch {
        break;
      } finally {
        try {
          fs.closeSync(descriptor);
        } catch {
          // closing a scratch file that was just written cannot change which directory works
        }
        fs.rmSync(scratch, { force: true });
      }
    }
  }
  throw new Error(`No usable temporary directory found in [${candidates.map((c) => `'${c}'`).join(", ")}]`);
}

/** Whether `identity` is one a marker cannot be keyed by: absent, empty or the substitute. */
function _isUnidentified(
  /** @type {MarkersData} */ data,
  /** @type {string | null | undefined} */ identity,
) {
  return !identity || identity === data.unidentified;
}

/**
 * The hashed marker name stem for `identity`: the head of its SHA-256, so an identity holding
 * `/` or `..` cannot name a path.
 * @param {MarkersData} data
 * @param {string} identity
 * @returns {string}
 */
function _digest(data, identity) {
  if (/\p{Surrogate}/u.test(identity)) {
    throw new TypeError("a marker identity must be encodable as UTF-8: it holds a lone surrogate");
  }
  return createHash("sha256").update(identity, "utf8").digest("hex").slice(0, data.name_sha256_tail);
}

/**
 * @param {MarkersData} data
 * @param {string} kind
 * @param {string} identity
 * @param {string | null} directory
 * @returns {string}
 */
function _markerPath(data, kind, identity, directory) {
  const name = `${data.name_prefix}${kind}-${_digest(data, identity)}`;
  return _under(directory ?? gettempdir(), name);
}

/**
 * The tempdir kind spelling for one vocabulary stem (the table is owned by `markers.json`, C102).
 * @param {MarkersData} data the parsed `common/markers.json`
 * @param {string} stem
 * @returns {string}
 * @throws {Error} for a stem the table does not carry (Python: `KeyError`)
 */
export function markerKind(data, stem) {
  if (!Object.hasOwn(data.kinds, stem)) {
    throw new Error(`no marker kind for stem ${JSON.stringify(stem)}`);
  }
  return data.kinds[stem];
}

/**
 * The literal identity payload readers substitute when a session is unknown (C102).
 * @param {MarkersData} data the parsed `common/markers.json`
 * @returns {string}
 */
export function unidentifiedIdentity(data) {
  return data.unidentified;
}

/**
 * One of the delegation drift state-file names for `identity`: counter, marker, ask_marker (C102).
 * @param {MarkersData} data the parsed `common/markers.json`
 * @param {string} which
 * @param {string} identity
 * @returns {string}
 * @throws {Error} for a state file the table does not carry (Python: `KeyError`)
 */
export function delegationStateName(data, which, identity) {
  if (!Object.hasOwn(data.delegation_state_files, which)) {
    throw new Error(`no delegation state file ${JSON.stringify(which)}`);
  }
  return fill(data.delegation_state_files[which], { identity });
}

/** Whether `marker` is older than a day; one that cannot be read is not stale. */
function _isStale(/** @type {string} */ marker, /** @type {number} */ now) {
  try {
    return now - fs.statSync(marker).mtimeMs / 1000 > MARKER_MAX_AGE_SECONDS;
  } catch (error) {
    if (_isOSError(error)) {
      return false;
    }
    throw error;
  }
}

/** Remove `marker`, ignoring a filesystem failure (a vanished file, a directory, no right). */
function _discard(/** @type {string} */ marker) {
  try {
    fs.unlinkSync(marker);
  } catch (error) {
    if (!_isOSError(error)) {
      throw error;
    }
  }
}

/**
 * Atomically claim one diagnostic for `identity`; `true` means "emit now".
 *
 * Two throttle domains, deliberately different and stated here because the difference reads
 * as an inconsistency otherwise (ADR-0012/D02): route-level diagnostics describe what a
 * *route* can do, so they throttle by session id; event-level diagnostics report a defect in
 * one call, so they throttle by a session/tool-use pair — a second malformed call stays visible.
 * @param {MarkersData} data the parsed `common/markers.json`
 * @param {string} kind
 * @param {string | null | undefined} identity
 * @param {{directory?: string | null}} [options] `directory`: where the marker lives (default: the tempdir)
 * @returns {boolean}
 */
export function claimDiagnosticMarker(data, kind, identity, { directory = null } = {}) {
  if (!identity || _isUnidentified(data, identity)) {
    return true; // no identity to throttle by: repeat rather than hide the diagnostic
  }
  const marker = _markerPath(data, kind, identity, directory);
  for (let attempt = 0; attempt < 2; attempt++) {
    let descriptor;
    try {
      descriptor = fs.openSync(marker, "wx", 0o600);
    } catch (error) {
      if (/** @type {{code?: string}} */ (error).code === "EEXIST") {
        if (!_isStale(marker, Date.now() / 1000)) {
          return false;
        }
        _discard(marker);
        continue;
      }
      if (_isOSError(error)) {
        return true; // marker failure must make the diagnostic noisier, never invisible
      }
      throw error;
    }
    try {
      fs.closeSync(descriptor);
    } catch (error) {
      if (!_isOSError(error)) {
        throw error;
      }
      _discard(marker);
    }
    return true;
  }
  return true; // lost the replace race twice: emit rather than stay silent
}

/**
 * Remove this identity's markers whose kind starts with `kindPrefix` — the condition cleared.
 *
 * A content-keyed diagnostic folds its condition into the kind (`<prefix>-<condition>`), so
 * clearing it, or moving to a new condition, re-arms the notice for a later recurrence.
 * `keepKind` spares the marker just claimed.
 * @param {MarkersData} data the parsed `common/markers.json`
 * @param {string} kindPrefix
 * @param {string | null | undefined} identity
 * @param {{keepKind?: string | null, directory?: string | null}} [options]
 * @returns {void}
 */
export function releaseDiagnosticMarkers(data, kindPrefix, identity, { keepKind = null, directory = null } = {}) {
  if (!identity || _isUnidentified(data, identity)) {
    return;
  }
  const keep = keepKind ? posix.basename(_markerPath(data, keepKind, identity, directory)) : null;
  const suffix = _digest(data, identity);
  const folder = directory ?? gettempdir();
  const pattern = `${data.name_prefix}${kindPrefix}*-${suffix}`;
  /** @type {string[]} */
  let names = [];
  try {
    names = fs.readdirSync(folder);
  } catch (error) {
    if (!_isOSError(error)) {
      throw error;
    }
  }
  for (const name of names) {
    if (name !== keep && fnmatchCase(name, pattern)) {
      _discard(_under(folder, name));
    }
  }
}
