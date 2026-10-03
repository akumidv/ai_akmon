/**
 * Code-point ordering — the JavaScript answer to Python's `sorted` on strings.
 *
 * JS's default `.sort()` compares UTF-16 code units, and an astral character's lead surrogate
 * sorts *before* every high-BMP code point: the units table pins exactly that divergence
 * (`units/sort.toml`, the astral case). The corpus normalizes nothing here, so the mirror must
 * order by Unicode code point, the way Python does.
 */

/**
 * Compare two strings by Unicode code point, without locale normalization.
 * @param {string} a
 * @param {string} b
 * @returns {number} negative, zero or positive, the way a sort comparator wants it
 */
export function codePointCompare(a, b) {
  const ca = Array.from(a);
  const cb = Array.from(b);
  for (let i = 0; i < Math.min(ca.length, cb.length); i++) {
    // `?? 0` only feeds the checker: the index is inside both arrays' common length,
    // so codePointAt never returns undefined here.
    const da = ca[i].codePointAt(0) ?? 0;
    const db = cb[i].codePointAt(0) ?? 0;
    if (da !== db) {
      return da < db ? -1 : 1;
    }
  }
  if (ca.length !== cb.length) {
    return ca.length < cb.length ? -1 : 1;
  }
  return 0;
}

/**
 * A NEW array of `strings` sorted by code point; `strings` is not mutated (Python's `sorted`
 * returns a list, it does not reorder in place).
 * @param {string[]} strings
 * @returns {string[]}
 */
export function codePointSort(strings) {
  return [...strings].sort(codePointCompare);
}
