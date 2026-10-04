/**
 * How akmon spells a version, in one place — the JavaScript twin of `common/versions.py`
 * (ADR 0020 D01): the unit table (units/versions.toml) is the spec both must pass.
 *
 * The same five questions, the same answers: what part of a recorded string names the version
 * (splitVersion), whether it names a release (isFinal), where it sits among releases
 * (orderKey), which of two comes first (compareVersions), and the npm carrier's SemVer
 * spelling of a PEP 440 one (semverSpelling).
 */

/** `git describe --tags` distance from the tag: `-<N>-g<sha>`, optionally `-dirty`. Anchored:
 * a distance is the *end* of the spelling, and an unanchored match would split
 * `0.4.0-3-g1234abcd-x` where the Python twin leaves it whole. */
const DESCRIBE_SUFFIX_RE = /-(\d+)-g[0-9a-f]+(?:-dirty)?$/;

/** A final release version, after `splitVersion` has removed the spelling. */
const FINAL_RE = /^\d+\.\d+\.\d+$/;

/** The release a version names or is on the way to: its leading `X.Y.Z`. */
const RELEASE_PREFIX_RE = /^(\d+)\.(\d+)\.(\d+)/;

/** A development version of the release itself: the `.dev0` of `0.4.0.dev0` — attached to the
 * release, not to a step. Its number is not read — the place is the same for every `.devN`.
 *
 * The divider is a class, not a dot: PEP 440 reads `.`, `-` and `_` as one separator before a
 * labelled component, so `1.0.0-dev1` *is* `1.0.0.dev1`. Reading only the dot was not merely
 * narrower — a hyphen-led tail went to the past-the-release answer below, which ranked
 * `1.0.0-rc2` *above* `1.0.0`. */
const DEV_OF_RELEASE_RE = /^[-_.]?dev\d+$/;

/** A pre-release step of the release, and the development version of that step: `0.5.0a1`,
 * `0.5.0a1.dev0`. PEP 440's spelled-out aliases (`alpha`, `beta`, `pre`, `preview`, `c`) are
 * deliberately absent — the tail this rule cannot name is not quietly read as a step of the
 * chain. */
const PRE_RELEASE_RE = /^[-_.]?(a|b|rc)\d+(?:[-_.]?dev(\d+))?$/;

/** A tail that means the tree sits past the release rather than below it: `1.0.0.post1`,
 * `1.0.0-post1`, and the `-dirty` akmon reads off a dirty work tree. Every other `-` tail is a
 * divider, not a position, so the test below names these instead of looking for a hyphen. */
const PAST_TAIL_RE = /^(?:[-_.]?post\d+(?:[-_.]?dev\d+)?|[-_.]?dirty)$/;

/** `orderKey`'s fourth element for a version at the release itself, and for anything past it
 * (a `git describe` distance, a `-dirty` tree, a `.postN` or a `+local` build). */
const AT_RELEASE_POSITION = 0;
const PAST_RELEASE_POSITION = 1;

/** `orderKey`'s fourth element for each pre-release step, in PEP 440 order. The steps take
 * the odd places below the release so that each has the even place beneath it free for its own
 * development version — `1.0.0rc1.dev0` at -2 sorts before `1.0.0rc1` at -1, the way PEP 440
 * sorts them. */
const PRE_RELEASE_POSITION = { rc: -1, b: -3, a: -5 };

/** A development version of the release precedes every pre-release step of it, so it sits one
 * place below the first step (`a`). */
const DEV_OF_RELEASE_POSITION = -7;

/** A tail that is neither the release, nor past it, nor one of the steps this rule can name:
 * one place before the release, the coarse answer the rule gave every such spelling before the
 * steps were separated. */
const BEFORE_RELEASE_POSITION = -1;

/**
 * Where a release's tail sits below the release, in PEP 440 order — `orderKey`'s fourth element.
 * @param {string} rest what follows the `X.Y.Z` of a version that is neither the release nor past it
 * @returns {number}
 */
function positionBeforeRelease(rest) {
  if (DEV_OF_RELEASE_RE.test(rest)) {
    return DEV_OF_RELEASE_POSITION;
  }
  const match = rest.match(PRE_RELEASE_RE);
  if (match === null) {
    return BEFORE_RELEASE_POSITION;
  }
  // The chain is `.devN < aN < bN < rcN < release`, and PEP 440 puts a development version of a
  // step *before* that step (`1.0.0a1.dev0 < 1.0.0a1`), which is why the steps are two apart.
  const step = PRE_RELEASE_POSITION[/** @type {"a"|"b"|"rc"} */ (match[1])];
  return match[2] ? step - 1 : step;
}

/**
 * @typedef {{base: string, ahead: string | null}} SplitVersion
 */

/**
 * Split a recorded version into the part to compare and its `git describe` distance.
 * @param {string} recorded
 * @returns {SplitVersion} `ahead` is null when the string names a version exactly
 */
export function splitVersion(recorded) {
  let base = recorded.trim();
  let ahead = null;
  const match = base.match(DESCRIBE_SUFFIX_RE);
  if (match !== null) {
    ahead = match[1];
    base = base.slice(0, match.index);
  }
  if (base.startsWith("v")) {
    base = base.slice(1);
  }
  return { base, ahead };
}

/**
 * Whether `recorded` names a release: exactly `X.Y.Z`, and not past a tag.
 * @param {string} recorded
 * @returns {boolean}
 */
export function isFinal(recorded) {
  const { base, ahead } = splitVersion(recorded);
  return ahead === null && FINAL_RE.test(base);
}

/**
 * Where `recorded` sits among releases, as a comparable tuple; null when unrecognized.
 * `(X, Y, Z, position)`: 0 for the release itself and 1 for anything past it — a `git describe`
 * distance, a `-dirty` tree, a `.postN` or a `+local` build. Below the release it names the
 * PEP 440 steps apart rather than lumping them: -7 a development version of the release
 * (`.devN`), -6 and -5 an alpha and its own development version, -4 and -3 the same pair of
 * betas, -2 and -1 the same pair of release candidates. Spacing the steps two apart is what
 * leaves room for `1.0.0a1.dev0` to sort before `1.0.0a1`, as PEP 440 does; a tail the rule
 * cannot name keeps -1, one place before the release. Two versions past the same release
 * compare equal, because their order is not a fact a version string carries.
 *
 * The key is data, not a comparator: `<` on two JS arrays compares their string forms
 * (`"0,10,0,0" < "0,9,0,0"`), which is not the ordering. Ask `compareVersions`.
 * @param {string} recorded
 * @returns {[number, number, number, number] | null}
 */
export function orderKey(recorded) {
  const { base, ahead } = splitVersion(recorded);
  const match = base.match(RELEASE_PREFIX_RE);
  if (match === null) {
    return null;
  }
  const rest = base.slice(match[0].length);
  let position;
  if (ahead !== null || rest.startsWith("+") || PAST_TAIL_RE.test(rest)) {
    position = PAST_RELEASE_POSITION;
  } else if (rest.length === 0) {
    position = AT_RELEASE_POSITION;
  } else {
    position = positionBeforeRelease(rest);
  }
  return [Number(match[1]), Number(match[2]), Number(match[3]), position];
}

/**
 * Which of two recorded versions comes first: `-1`, `0` or `1`.
 *
 * `orderKey` answers where one version sits; this is the ordering its callers actually want,
 * so that the comparison has one owner instead of one per language — a JS `<` on two order
 * keys compares their string forms (`"0,10,0,0" < "0,9,0,0"`), which is not the same answer.
 * Unrecognized input throws: a version the rule cannot place cannot be ordered, and guessing
 * would move a pin on a coin flip (A23).
 * @param {string} a
 * @param {string} b
 * @returns {number}
 * @throws {Error} when either version has no order key
 */
export function compareVersions(a, b) {
  const keyA = orderKey(a);
  const keyB = orderKey(b);
  if (keyA === null || keyB === null) {
    const unplaceable = keyA === null ? a : b;
    throw new Error(`'${unplaceable}' is not a version orderKey can place, so the two cannot be compared`);
  }
  for (let i = 0; i < keyA.length; i++) {
    if (keyA[i] !== keyB[i]) {
      return keyA[i] < keyB[i] ? -1 : 1;
    }
  }
  return 0;
}

/**
 * The SemVer carrier spelling of a PEP 440 version (the npm side of the version line).
 *
 * A final release spells itself and a development version of it carries its segment across as a
 * SemVer pre-release (`0.4.0.dev0` → `0.4.0-dev.0`). A leading `v` is a spelling and is dropped.
 * Nothing else is carriable. SemVer §11 compares pre-release identifiers left to right and sorts
 * an alphanumeric one by ASCII, so the chain a derived spelling would form reads
 * `alpha < beta < dev < rc` while PEP 440 reads `dev < a < b < rc`: `aN`/`bN`/`rcN` (each alone
 * or with its own `.devN`) are refused because spelling them would put the npm side in an order
 * its PEP 440 side denies. The same reason refuses a `.postN` (which sorts *after* the release),
 * a `+local` build and a `git describe` distance. Each throws naming the input, because a carrier
 * that cannot be spelled is reported, never guessed.
 *
 * @param {string} recorded
 * @returns {string}
 * @throws {Error} when the version has no SemVer carrier spelling
 */
export function semverSpelling(recorded) {
  const { base, ahead } = splitVersion(recorded);
  if (ahead !== null) {
    throw new Error(
      `'${recorded}' is a distance past its tag — a position, not a version the npm carrier can spell`,
    );
  }
  if (FINAL_RE.test(base)) {
    return base;
  }
  const dev = base.match(/^(\d+\.\d+\.\d+)[-_.]?dev(\d+)$/);
  if (dev !== null) {
    return `${dev[1]}-dev.${dev[2]}`;
  }
  throw new Error(
    `'${recorded}' is not an npm-carriable PEP 440 version: .postN, +local and a pre-release step ` +
      "(aN, bN, rcN, each with or without its own .devN) have no SemVer spelling",
  );
}
