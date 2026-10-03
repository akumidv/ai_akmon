# smol-toml — vendored pin record

Upstream project: [squirrelchat/smol-toml](https://github.com/squirrelchat/smol-toml) (BSD-3-Clause;
the `LICENSE` here is the upstream licence, kept per the decision).

## What is vendored and why

[ADR-0020/D04](../../../meta/decisions/0020-node-consumers-js-implementation.md#d04--form-of-the-javascript-implementation)
pins the form of the JavaScript implementation: TOML is read by a **vendored copy of smol-toml at a
pinned version**, licence kept, verified against the official `toml-test` suite, and updated only
through a recorded task. This directory is that vendored copy: the upstream `dist/` build output,
its `package.json` and `LICENSE`, byte-identical to the published npm tarball (verified at pinning,
C103). The vendored tree has no runtime dependencies of its own — the package manifest's
`devDependencies` are upstream's and unused here.

## Pin

| Field | Value |
| --- | --- |
| Package | `smol-toml` |
| Version | `1.9.0` |
| Source | <https://registry.npmjs.org/smol-toml/-/smol-toml-1.9.0.tgz> |
| Tarball sha256 | `4909da857f775ea729461e552fdc85966e7825c1020605066b3a9ad29642dbdc` |
| Pinned | 2026-09-27 (task C103) |

The machine-readable record is [`pins.json`](pins.json); the offline gate that enforces it is
[`pins.test.mjs`](pins.test.mjs) (host `node --test`, no network): it re-hashes every pinned file,
names any that drifted, cross-checks the version against the vendored `package.json`, and audits
the directory in both directions (§ What the directory may hold).
`README.md` is this record, not upstream material, and so is not itself pinned.

## What the directory may hold

Two kinds of file, and no third: the **pinned upstream set** — every name in `pins.json`'s `files`
map, each hashed above — and **akmon's own three**, `pins.json`, `pins.test.mjs` and `README.md`,
named in `pins.json`'s `akmon_files`. The two lists stay separate on purpose: akmon's own files are
not upstream content, and hashing them into `files` would make the diff at the next bump read as
though akmon had rewritten upstream's bytes.

The gate walks the directory — recursively, in sorted order, reading through no symlink — and fails
on anything else in either direction: a file neither list names, a name either list carries that the
directory does not hold, a record name pointing outside this directory, a symlink or other
non-regular entry. Every finding names the offender and the remedy — hash it into `files` (upstream
content), list it in `akmon_files` (akmon's own), restore it, or delete it. An unexpected **empty**
directory is not a finding: a directory carries no payload and neither carrier ships one, so the
files under an unexpected directory are the finding, each named on its own.

## File sha256 (relative to this directory)

| File | sha256 |
| --- | --- |
| `LICENSE` | `fa5659948374d4f555594f47f6da073b40dc503e921aeeece30df4362b3051a5` |
| `package.json` | `0e35bde6992fef675058596ea0e94c2d3ca65e5f9b73a326d94208be6210f192` |
| `dist/date.d.ts` | `c7ad3531c131f2b5b246b2d208b75c5403475ad155b7661fa2d673104b806791` |
| `dist/date.js` | `ef924a2a42c7f16761e7098c3ed8e04195ecbcb02d5c369db0aee76f251a409c` |
| `dist/error.d.ts` | `02e33cdc5ca75f517f44b31070640be0fe6d0169dd91c266d02a1e2a71e064ac` |
| `dist/error.js` | `76f8e47f5fc57273748242d59570656d7c921a80bceb2291ca5a4d7a723e9f29` |
| `dist/extract.js` | `b964c8f39c737172295b31b9ee61b49e513ff12788e119ddfdbb68c448054c12` |
| `dist/index.cjs` | `09ce310a8bcc1bb5c7dc2813c88b4bfbbeb685e4c186a9631ff54da7e85c880f` |
| `dist/index.d.ts` | `b4556819c2ed0cd4016d05a6bfd7d4773c0b5ffb39c8ed547796ce4a1093d9b8` |
| `dist/index.js` | `dc8e0afc74477e514f5cb8492b587560c1d7d68cec03a994cc8bc4af99c8da2a` |
| `dist/parse.d.ts` | `2b230dc984b6e51b545bfe222f9965cc2ff434164ed9428bec415c5e508a9854` |
| `dist/parse.js` | `195e33ea068bf6f3acb5b3342792ac4aa954bba7e751519ba869c00da395ecdb` |
| `dist/primitive.js` | `be47fe90bf9a410af0b9204b6b34617f4b38e57f08198b10cb024a0272eb5936` |
| `dist/stringify.d.ts` | `628a6a55714fcf4a4eb0e59866ab1e5cc67c1b9e0cfc8524ccc8d6b5ee24ad7c` |
| `dist/stringify.js` | `c717d95456426dc8a0b07c9d03a4e434d5dea8254fca24e5fd93a22de3bcd44c` |
| `dist/struct.js` | `736742cfa645bbd08bc5396c5f7ddbea5c3b7ac5d61fe86031846f5769131deb` |
| `dist/util.d.ts` | `e6b1d3eecb240dc71d0dc28d1beee69cefd6ee014507c822909be0a7117517e0` |
| `dist/util.js` | `6327e40efd957128da15867c3a32293950a925570b457b1b78c735452cebc08e` |

## toml-test verification (the pinning step)

The official `toml-test` binary — a named network prerequisite of this step only — was run against
the decoder adapter, over the `files-toml-1.0.0` subset: the TOML version the Python floor
(`tomllib`, ADR-0009/D04) reads.

| Field | Value |
| --- | --- |
| toml-test version | `v2.2.0` |
| Binary | release asset <https://github.com/toml-lang/toml-test/releases/download/v2.2.0/toml-test-v2.2.0-linux-amd64.gz> (the sha256 below is of the **extracted** `toml-test-v2.2.0-linux-amd64` binary) |
| Binary sha256 | `78b74b9d4136f9561a2c57778920d3c6646ead41079d1b36fc1629641187df30` |
| Decoder adapter | [`meta/conformance/tomltest/decoder.mjs`](../../../meta/conformance/tomltest/decoder.mjs) |
| Subset | `files-toml-1.0.0` (205 valid + 474 invalid cases) |

Result, recorded 2026-09-27 (task C103) — **679 passed / 0 failed under each Node floor**:

| Node | Version | Valid | Invalid | Failed |
| --- | --- | --- | --- | --- |
| Node 22 (the ADR-0020/D04 floor) | `v22.23.3` | 205 passed | 474 passed | 0 |
| Host Node 24 | `v24.21.0` | 205 passed | 474 passed | 0 |

The adapter applies, around the 1.1.0-capable parser, the 1.0.0 strictness smol-toml tolerates by
design (its README footnotes): fatal UTF-8 decoding of stdin, `integersAsBigInt` parsing for full
int/float type preservation, and a raw-text pre-scan rejecting `\x` byte escapes, line breaks at an
inline table's own level, trailing commas before an inline table's `}`, and date/time literals with
out-of-range parts, non-existent calendar dates, or a time part without seconds.

### Skipped cases (67)

Everything in the `files-toml-1.1.0` list that is not in `files-toml-1.0.0` is skipped, one
`-skip` pattern per name at run time. All share one reason: **TOML 1.1.0-only; the Python floor
(`tomllib`) reads 1.0.0.** The canonical per-name list is in `pins.json`
(`toml_test.run.*.skipped`):

- `invalid/control`: `multi-cr`, `rawmulti-cr` (2)
- `invalid/spec-1.1.0`: `common-2`, `common-5`, `common-16-0`, `common-19-0`, `common-46-0`,
  `common-46-1`, `common-49-0`, `common-50-0` (8)
- `valid/datetime`: `no-seconds` (1)
- `valid/inline-table`: `newline`, `newline-comment` (2)
- `valid/spec-1.1.0`: `common-0` … `common-53` except `common-2` and `common-5`, and including the
  suffixed `common-16-0`, `common-19-0`, `common-46-0`, `common-46-1`, `common-49-0`, `common-50-0`
  (52)
- `valid/string`: `escape-esc`, `hex-escape` (2)

## Update rule

This vendor tree is **updated only through a recorded task**: re-vendor the new version's published
tarball, re-hash the files, re-run the pinning step (official `toml-test` binary, pinned release and
sha256, over the `files-toml-1.0.0` subset under both Node floors), and update this README and
`pins.json` with the new record.
