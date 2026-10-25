# C127 evidence — `init` writes the language-profile import, `verify` warns on a missing or unresolved one

Task: [C127](../TASKS.md). Decision: [ADR-0014/D02](../../docs/adr/0014-code-rules-catalog-and-language-profiles.md#d02--init-writes-the-language-profile-import-verify-warns-on-a-missing-or-unresolved-one),
the owner's option (a) from the C127 review. It makes ADR 0014 D01 §2 ("language profiles attach automatically") true at
attach time. ADR 0020 D01/D03: both implementations, identical behaviour.

## What changed (ready for owner review)

- **One mapping, in the standard tree.** `bin/sync.json:141` `language_profiles`: `python.md` for `python` or a
  `pyproject.toml`; `js.md` for `javascript`, `typescript` or a `package.json`. It lives in `bin/sync.json` rather than
  `src/akmon/init.json` because a mounted consumer's `verify` reads it and a mounted tree carries no `src/`. Both twins
  read it: `bin/sync.py:611` `language_profiles(root, languages, data)` and `js/bin/sync.mjs:1239`
  `languageProfiles(data, root, languages)`. A value is split on `/` and compared without case, so the record's
  `package/python` names `python`; table order is the answer's order (Python first); each answer carries what named it
  (the manifest, else the matching language value).
- **The profile-import reader.** `bin/sync.py:657` `profile_imports(text)` and `js/bin/sync.mjs:1275`
  `profileImports(text)` return every `@…profiles/<name>.md` import, skipping code spans and fenced blocks as the
  materialization scan does, as a typed `ProfileImport` (prefix, name, line).
- **The fresh block.** `src/akmon/init.json:125` `agents_block`: the code-span example
  `` `@{{profiles_dir}}/{{language_profile}}` `` is gone; the prose quotes the placeholder form
  `` `@{{profiles_dir}}/<name>.md` `` and the import lines follow `_common.md` as `{{profile_imports}}`. The hard-coded
  `"python.md"` (`src/akmon/_init.py`) and `"js.md"` (`js/akmon/_init.mjs`) values are removed.
  - Python: `src/akmon/_init.py:770` `_language_profiles` asks the embedded sync for `--archetype` and `--language` plus
    the manifests; `src/akmon/_init.py:707` `_Classification` carries archetype, language and profiles into
    `_agents_block` (`:719`), which fills `profile_imports` at `:753` under the attach's prefix
    (`@_aitna/.akmon/profiles/` in package mode, `@_aitna/akmon/profiles/` mounted). The dataclass keeps
    `_agents_block` at four arguments (PLR0913 cannot be waived, `test_ruff_profile`).
  - JS: `js/akmon/_init.mjs:440` `detectedProfiles` and `:420` `profile_imports` (package prefix only).
  - `classify` stays a closing step while the archetype is unclassified **or** no profile was detected
    (`src/akmon/_init.py:1289`, `js/akmon/_init.mjs:940`).
- **`verify`, both twins.** `bin/verify.py:419` `check_profile_imports` (+ `:467` `_check_language_profiles`, called
  from `run()` at `:1527`, right after `check_agents_md`); `js/bin/verify.mjs:760` `checkProfileImports` (+ `:814`, run
  at `:1852`). Two new `warn`/`ok` codes:
  - `agents.profile-import` — a profile import that names a profile the standard does not ship, or one under another
    prefix than `sync.import_prefix` gives for the record's mount (unless it is a file of the project, e.g.
    `@docs/profiles/x.md`). The fix names the exact replacement line.
  - `agents.language-profile` — one warning per profile the record's `attached_archetype` or a manifest calls for that
    AGENTS.md does not import (an import under a wrong prefix counts as present: that is the first code's finding).
    The fix names the exact line to add, after the `_common.md` import.
  - No `verify.json` table and no policy ID: `verify` findings carry their code at the emission site, the canary
    population is `hook_core.*_result` only (ADR-0012/D07), and the coverage gate derives the new codes itself.
- **`sync`.** Behaviour unchanged (it materializes what AGENTS.md imports). The "a line a human adds by hand"
  docstrings are rewritten to the new truth (`bin/sync.py:712`, `js/bin/sync.mjs:1336`), and the code-span comment
  quotes the new placeholder (`bin/sync.py:563`, `js/bin/sync.mjs:1186`).
- **Shipped prose.** `profiles/python.md:3` and `profiles/js.md:3` now say the same thing: `akmon init` imports the
  profile for a project with the manifest or a declared language. `ARCHETYPES.md:94` adds that `init` writes the import
  and `verify` warns. `BOOTSTRAP.md:159` and `:171` (the B0 prompts) ask to check the imports `init` wrote instead of
  adding one.
- **Design.** `docs/design/node-consumers.md:344` (the C110 note on the `js.md` example) and
  `docs/design/code-rules-and-profiles.md:83` point at ADR-0014/D02.
- **Self-CI.** `meta/self_ci.py:331` (wheel smoke: `profiles/python.md` is now materialized) and `:559` (npm smoke:
  `profiles/js.md`). `meta/checks/always_loaded.py:46` builds the block with the largest profile's import line, as
  `init` writes it.

## Measured — the always-loaded cap (C56, ADR 0012 F18)

Built with `meta/checks/always_loaded.py::shipped_population` and, for the mixed case, the same generator with both
profiles.

| population | before | after |
|---|---|---|
| akmon-shipped, one profile (python.md, the largest) — the self-CI measurement | 317 / 320 lines, 20,633 / 21,000 bytes | 318 / 320 lines, 20,712 / 21,000 bytes |
| akmon-shipped, both profiles (a pyproject.toml + package.json project) | — | 396 / 320 lines, 25,907 / 21,000 bytes |
| consumer-total, both profiles, akmon block alone | — | 401 / 570 lines, 26,097 / 34,000 bytes |

The single-profile measurement stays inside the cap, so no cap change. A two-language project is over the
akmon-shipped cap; that scope is not measured by self-CI and the cap is not re-baselined here (open, below).

## Tests

- `meta/tests/test_sync.py`: the mapping (nine rows: flag values, record values, case, unknown, unclassified,
  placeholder), both manifests Python first, manifest over language as the source; `profile_imports` skipping spans,
  fences and a mid-word `@`. The key-set pin gains `language_profiles`.
- `meta/tests/test_verify.py`: resolving import + covered language (two OKs); the consumer's case — the mounted prefix
  in a package attach — warns with the exact replacement and still counts for the language; a profile the standard
  does not ship; a project's own `profiles/` file left alone; a quoted import is not an import (language warn with the
  exact line); the record names the language (`service/typescript` → js.md, the package line); both manifests;
  unknown language (`custom/rust`) all OK.
- `meta/tests/test_init.py`: `--language python` imports python.md and drops `classify`; a `pyproject.toml` imports it
  and keeps `classify` (archetype unclassified); both manifests write both, Python first; `--language rust` writes no
  profile line and keeps `classify`; the package-mode block uses the materialized prefix and quotes only the
  placeholder. `test_package_attach_verifies_strict_green` now expects `profiles/python.md` materialized.
- `js/bin/sync.test.mjs`, `js/bin/verify.test.mjs`, `js/akmon/_init.test.mjs`: the twin rows (mapping, reader); the
  vendored prefix in a package attach, an unshipped profile, the missing js.md, both manifests; `detectedProfiles`
  rows; a fresh block with js.md (materialized by sync), both manifests, a bare directory with none. The healthy-project
  fixture `AGENTS` constant now imports js.md.
- Corpus:
  - `profiles/js.md` joins the snapshot with a stand-in (`meta/conformance/fixtures/tree/profiles/js.md`); the package
    attach fixture's AGENTS.md imports python.md and js.md, so a healthy fixture stays healthy on both carriers (the
    shared `caps.always-loaded` line moves from 21/917 to 35/1509).
  - `agents.language-profile` is Python-owned whole-code in `coverage.toml`: the profile a fixture calls for follows the
    carrier's manifest, so the line differs per ecosystem; shared scenarios record it out of `findings`.
  - New: `cli/verify-agents-profile-wrong-prefix` (shared, the consumer's case), `cli/verify-language-profile-missing`
    (Python), `cli/verify-node-language-profile-missing` (node), `cli/init-node-fresh-block` (node: AGENTS.md with the
    js.md import and the materialized stand-in; `--ref main` so the block's links do not follow the version).
  - Re-recorded from the Python reference: `cli/init-vendored` (now a Python fresh block: a `pyproject.toml` fixture
    file; only the block prose and the `python.md` import changed), and 50 more `cli/` scenarios (verify, sync, update,
    init-package) whose only diffs are the two new codes, the cap numbers, and the two materialized profiles.
  - Node-only scenarios (19, plus the two new ones) were reseeded from the JS implementation with a scratch call of
    `runner.run_scenarios(..., "node", record=True)` (the CLI refuses `--record` off Python; these have no Python
    reference) and reviewed line by line: same three kinds of diff. That reseed exposed a `--record` defect:
    `_record_block` writes `file_absent` after the `[expected.files]` header, so it lands inside that table;
    `cli/init-node-checks-none` was fixed by hand.

## Gates

- `uv run pytest -q`: 10 failed, 2440 passed — the 9 known `test_a22_p3_*` reds and
  `test_ruff_profile.py::test_akmon_meets_every_size_limit_without_an_exception` (offenders: `test_a22_p3_*` only).
- `uv run ruff check .`: 11 errors, all in `meta/tests/test_a22_p3_*` (I001, PLR0913, C901, RUF100).
  `uv run ruff format --check .`: 131 files already formatted.
- `node --test "js/**/*.test.mjs"`: 626 tests, 626 pass.
- `npx --no-install tsc --checkJs --noEmit -p .`: exit 0. `npx --no-install oxlint .`: exit 0 at the time of the gate
  run. `npx --no-install oxfmt --check .`: all matched files use the correct format.
- `python3 meta/conformance/runner.py --tree .`: 196 scenarios, 168 pass, 28 skip; coverage (143 items, 100 codes) and
  pairing gates ok.
- `python3 meta/conformance/runner.py --tree . --impl node`: 196 scenarios, 175 pass, 21 skip; gates ok.
- `python3 meta/self_ci.py`: the full run exits 0 with every leg OK — `selfci.js-lint` and `selfci.corpus-node` are
  green, alongside fixture sync/verify, the conformance corpus (Python), `selfci.wheel-smoke`, `selfci.npm-smoke`, and
  `caps.always-loaded` (318/320 lines, 20,712/21,000 bytes).

## Open

- **Existing consumers.** A block written before C127 imports no profile; `verify` now warns
  (`agents.language-profile`), and `verify --strict` exits 1 until the named line is added. The consumer who imported
  `@_aitna/akmon/profiles/js.md` in a package attach gets `agents.profile-import` with the replacement line.
- **Two-language projects** load two profiles: over the akmon-shipped cap (table above). A re-baseline or a
  two-profile measurement needs owner acceptance under ADR 0012 F18.
- **Resolved — the `classify` step's wording.** With a profile already imported the step asks for the archetype
  alone (`init.json` `closing_steps.classify_archetype`); tested in `meta/tests/test_init.py:360` and
  `js/akmon/_init.test.mjs:1060`.
- **Resolved — `runner.py --record`** placed `file_absent` inside `[expected.files]` when a scenario had both; fixed by
  C128 (top-level `[expected]` keys are written before the sub-tables), tested in
  `meta/tests/test_conformance_corpus.py:597` (`test_record_writes_file_absent_before_the_sub_tables`).
