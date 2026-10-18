# C104 — evidence

C104 runs in two passes (owner decision, design §6). This file is the evidence of
**pass 1**; pass 2 appends its own section.

## Pass 1 — what the hooks stand on (ready for owner review)

### Scope decision

The plan put the model-routing port in C108, but `gate-audit`, `delegation-log` and `model-routing`
import `tools/model_routing/routing.py`. Measured: 87 of its 91 definitions and 1317 of
its 1688 lines are reachable from those three hooks, so splitting the module (the earlier "variant C")
would have left 85 lines behind. The owner chose to port the whole file with the hooks (variant A);
C108 keeps `init`, `stats`, `gate_pack`, `coverage_map`, `second_opinion`.

### What landed

| Python module | JS twin | Unit table (rows) | Mutations that fail a row |
|---|---|---|---|
| `common/markers.py` | `js/common/markers.mjs` | `units/markers.toml` (41) | 17 on the JS side, 3 on the Python side |
| `common/materialization.py` | `js/common/materialization.mjs` | `units/materialization.toml` (78) | counted with the above |
| `tools/model_routing/routing.py` | `js/tools/model_routing/routing.mjs` | `units/routing.toml` (309) | 37 on a copy of the Python module, 28 on a copy of the JS one |

- Each table has a scenario in `scenarios/units/` and a probe in both `probe.py` and `probe.mjs`;
  the corpus requires the two probes' output documents to be byte-identical.
- `routing` is a generic call table: a row names the Python function, its arguments and the
  expected JSON answer (plus the files, modes, mtimes and environment of the world it runs in, and the
  resulting tree for the writers). Comparison is canonical JSON, so `1.0` is not `1`.
- `pairing.toml`: the exemptions for `common/markers.py` and `common/materialization.py` are gone;
  `tools/*` became one explicit entry per unported tool module (seven), so the list names what is
  outstanding and a new tool module is a gap until it is paired or listed.
- The JS modules take their shared data as a parameter (design §4): `data`/`agentsData`,
  `gateData`, `runtimeData`, `markersData`; the data-file → parameter map is in each header.
- `js/common/markers.mjs` exports `gettempdir`, the port of `tempfile.gettempdir()` (Node's
  `os.tmpdir` answers differently); pass 2's `hook_core` state files must use it.
- `js/common/runtime.mjs`: `harnessCommand` now throws an `Error` named `ValueError`, as its Python
  twin raises. The Python crash handler prints `type(exc).__name__` (`hooks/hook_core.py` lines 125
  and 143), so a class name is owner-visible text.

### Python behavior changed (owner-approved direction: `re.ASCII`, C103)

Seven patterns in `routing.py` are now `re.ASCII` (`_HEADING_WORD_RE` stays Unicode for Cyrillic
headings, C98). On 45 real transcripts nothing changed. Synthetic inputs that now read differently:
a role declaration starting with a no-break space no longer counts; `parse_zone("zone: x y")` and
`parse_zone("zone:x y z")` give different labels; a list item indented with a no-break space (or a
stray U+001C) no longer counts in `count_gate_items`, which turns three `gate_audit_request` answers
on such a message from "ask for an audit" into `None`.

### Documented divergences left in place

- `routing.mjs` reads the registry, its overlay and the local config with float spelling kept
  (`FloatValue`, cost measured at about 0.3 ms per hook call, with a fast path when the text cannot
  contain a whole-number float). Transcript lines use plain `JSON.parse`: a whole float reads as an
  int, an integer beyond 2**53 is inexact, `NaN`/`Infinity` lines are refused where Python accepts them.
- `markers.mjs`: a lone surrogate in an identity raises `TypeError` (Python: `UnicodeEncodeError`);
  an unknown marker kind or state name raises `Error` (Python: `KeyError` whose message is
  `repr(key)`). The table pins that both sides raise; only a `node:test` covers the surrogate.
- `Path.is_dir()`/`is_file()` on EACCES: Python 3.11–3.13 raises, the JS answers false in
  `materialization`; `routing` follows 3.11–3.13. Only Python 3.12.3 was available.
- `harnessCommand` reads its table from a plain object (`"constructor"` would be found by
  inheritance) and quotes the name with `'…'` where Python uses `{harness!r}`. Not pinned by a row.

### Python quirks seen while porting, not changed (owner's call)

- `stale_materialized`'s docstring promises it never raises; a non-UTF-8 copy or source raises
  `UnicodeDecodeError`. Both twins do, and table rows pin it.
- `materialized_markdown` on a heading line with no trailing newline glues the banner onto the heading.
- `bin/sync.py` writes the `.akmon` path itself in two places instead of calling `materialized_dir`.
- `ruff format --check` fails on `tools/model_routing/routing.py` at HEAD too (three hunks); not touched.

### Gates (run on the working tree)

- `python3 meta/self_ci.py`: exit 0, every line OK (wheel smoke, fixture sync/verify, `selfci.conformance`,
  `js-deps`, `js-typecheck`, `js-unit`, `js-lint`, `corpus-node`).
- `python3 meta/conformance/runner.py` (Python, full): 137 of 137, coverage gate (130 items, 11 units)
  and pairing gate (40 files: 9 paired, 31 exempt, 1 stub) OK.
- `--impl node --area units`: 11 of 11. `--impl node` on the hook and CLI areas is pass 2's.
- `pytest meta/tests`: 1927 passed, 1 failed — `test_akmon_meets_every_size_limit_without_an_exception`;
  all 19 offenders are in `meta/experiments/a22-p3/` and one a22 test (not part of this change).
- `ruff check common js meta/tests meta/conformance tools/model_routing/routing.py`: clean.
- `npm pack --dry-run`: `js/tools/model_routing/routing.mjs` and the two new `common` modules are in the
  tarball, beside the Python files (one file list, D05).
- Not run: Windows, Python 3.13/3.14, a hook through a live harness (N10).

### For pass 2 (hand-off)

1. `hook_core`'s crash handler prints `type(exc).__name__`: every exception that can reach it needs the
   Python class name in the JS twin. Read-only list of the remaining throws whose Python twin raises
   a named class: `markers.mjs` `gettempdir` (`FileNotFoundError`), `markerKind`/`delegationStateName`
   (`KeyError`), the lone-surrogate identity (`UnicodeEncodeError`); `project_root.mjs` symlink loop
   (`RuntimeError`); `shlex.mjs` two raises and `versions.mjs` three (`ValueError`);
   `check_runner.mjs` `ScopeError` (its class never sets `name`). Decide which are reachable from a hook.
2. `str(KeyError(x))` is `repr(x)`: if the crash-open adapter prints `str(exc)` for the retired-key
   `KeyError` that escapes `status_lines`, the quotes are visible. Pin it with a corpus scenario.
3. Use `markers.mjs` `gettempdir` and `routing.mjs`'s `FloatValue` handling in `hook_core.mjs`; import
   `aitnaRootName` from `project_root.mjs` (routing does not re-export it).
4. `common/findings.py` is not imported by anything the hooks reach; its `pairing.toml` reason
   ("first consumer is hook_core") looks stale (it serves `verify`, C105). Re-check and fix the reason.
5. Measure the JS hooks against the M122 range (178–194 ms) on the same host; the three routing hooks are
   the slowest on the Python side.

## Pass 2 — the hooks (ready for owner review)

### What landed

| Python | JS twin | Unit table (rows) |
|---|---|---|
| `hooks/hook_core.py` | `js/hooks/hook_core.mjs` | `units/hook_core.toml` (815) |
| `hooks/claude_adapter.py` | `js/hooks/claude_adapter.mjs` | `units/claude_adapter.toml` (105) |
| `hooks/codex_adapter.py` | `js/hooks/codex_adapter.mjs` | `units/codex_adapter.toml` (533) |
| `hooks/analysis-guard.py`, `role-on-code.py`, `session-start-agent.py`, `git-commit-guard.py`, `delegation-nudge.py` | the same names under `js/hooks/*.mjs` | the hook corpus (below) |
| `hooks/gate-audit.py`, `delegation-log.py`, `model-routing.py` | the same names under `js/hooks/*.mjs` | the hook corpus |
| `hooks/codex-hook.py` | `js/hooks/codex-hook.mjs` | the hook corpus |

New JS-only helpers (no Python twin, so the pairing gate does not see them): `js/hooks/hook_data.mjs`
(the data files one hook reads, as a bundle read lazily on first access — a broken file fails only the hooks
that reach it, as in Python), `js/common/pyvalue.mjs` (the Python value, string and file semantics, moved
out of `routing.mjs` so a hook does not load the 2600-line routing module), `js/common/pyjson.mjs`
(`json.loads` and `sys.stdin.read` as the payloads need them), `js/common/sha256.mjs` (see Latency).

- **The node layer of the hook corpus.** `runner.py --impl node` runs all 36 hook scenarios: a Node-package
  project (`fixtures/attach/node/`: the record and the `package.json` pin; `corpus.py` links
  `node_modules/akmon` to the tree) and the hook as `node node_modules/akmon/js/hooks/<name>.mjs`, the spelling
  ADR 0020/D05 wires. The project is synced by the Python reference until the JS `sync` exists (C105):
  what a hook reads from a synced project is the same files whichever implementation wrote them.
  `--area` repeats; `--record` refuses `--impl node` (Python is the reference). `selfci.corpus-node` runs units
  and hooks.
- **Unit tables.** The `routing` mouth was generalized (`_probe_rows` / `probeRows`) and serves the three
  hook modules: 1453 rows. Mutation audit on copies of the modules (never the repo files): `hook_core` 38
  behaviours, `claude_adapter` 17, `codex_adapter` 30 — every one fails a row on the Python copy and on the
  JS copy, except one JS mutation of `hook_core` (`normpath`'s `///` branch) that no public function can reach:
  `pyPath` collapses it first, and `hook_core.test.mjs` tests `normpath` directly.
- **Node wiring marker.** `bin/sync.json` `akmon_hook_markers` gained `/node_modules/akmon/js/hooks/`, so the
  Python `sync` recognises a Node-wired entry as akmon-managed and replaces it on a mode switch instead of
  leaving it running beside the new one (pinned in `test_sync.py` and `test_package_mode.py`). The *spelling*
  (`node "<anchor>/node_modules/akmon/js/hooks/<script>.mjs"`) is written by the JS `sync`, which is C105's;
  no Python code writes it, so no data key for it was added yet.
- **Pairing.** The `hooks/*` exemption is gone: the gate reads 40 `.py` files, 21 paired, 19 exempt. The
  `common/findings.py` reason was stale (nothing under `hooks/` imports it) and now names its real first
  consumers, `bin/sync.py` / `bin/verify.py`, task C105.

### Python behavior changed (`re.ASCII`, the C103 direction)

| Input | Before | Now |
|---|---|---|
| `"ésudo ls"`, `"sudoé ls"` (a non-ASCII letter next to `sudo`) | not denied | denied |
| `"βgit push"`, `"git pushé"` | no decision | ask |
| a patch invocation or envelope with a no-break space, U+001C, U+0085 or U+2028 where an ASCII blank belongs (six synthetic inputs, e.g. `" apply_patch <<'EOF'…"`, `"*** Begin Patch "`) | recognised as an `apply_patch` command | shell |

Real patches are ASCII, so real answers do not change. The `co-authored-by` pattern stays case-insensitive only:
no non-ASCII code point folds into any of its letters, in Python or in JS.

### Documented divergences left in place

- **`-h` / `--help` on `codex-hook`** (argparse prints usage and exits 0): the JS treats every argument error,
  help included, as a `UsageError` — one crash line, exit 1 — because a hook has no reader for a usage block.
  The Python is unchanged. Decision for the owner: leave it, or make the Python hook refuse `-h` the same way.
- **Payload numbers.** `JSON.parse` reads `1.0` as `1` and a beyond-2**53 integer inexactly. A payload field is
  only tested for type and truthiness or spelled by `str()` into a marker file name, with one exception: a
  `delegation-log` `description` of `1.0` is logged `1.0` by Python and `1` by JS. `NaN`/`Infinity` and the
  4300-digit integer limit are reproduced (`pyjson.mjs` scans Python's grammar when the text could hold them);
  `RecursionError` past 9997 levels of nesting is reproduced for Python 3.12.3 (about 990 on 3.11).
- **stdin.** Python under a C/POSIX locale reads stdin with `surrogateescape` (an invalid byte does not crash);
  the JS is always strict, as under a UTF-8 locale. A closed descriptor 0 is an `AttributeError` in Python; node
  reopens it on `/dev/null`, so it reads as an empty payload.
- **Settings and overlay files with `NaN`** are read by Python and skipped (or refused) by JS (`JSON.parse`);
  an agents or gate data file with missing keys is `KeyError` there and `TypeError` here (an emptied shipped file).
- **Time zone.** With `TZ` set the timestamp's offset is asked of `date` (ICU and libc disagree on POSIX-style
  zones); with `TZ` unset `Date` answers. 23 `TZ` spellings match.
- **`HookResult`** accepts a missing event name or an unknown field where the Python dataclass raises
  `TypeError`; `git_commit_guard_result(branch=[])` (off-contract, typed `str | None`) is an `ask` in Python.
- Carried from pass 1: transcript lines are plain `JSON.parse`; the message texts still name `python3
  $(akmon path)/tools/…` — the Node spelling (`akmon tool`) is C108's, with its normalization rule.

### Python quirks seen, not changed (owner's call)

- **`git_commit_guard_result` matches the words, not the command.** `\bgit\b[^|&;]*\bcommit\b` also fires
  on `git-commit-guard` written anywhere in a command line — a shell command that merely *mentions* the hook
  name (a heredoc, an `echo`, a `grep`) is asked, and denied outside the default permission mode. Seen
  three times in this pass. The JS twin does the same. A fix would be a Python change and a table row.
- **`common/__init__.py` is still exempt as task C104**; it is structural (ES modules have no package init) and
  never gets a twin. Its task label could say C105 or "structural".
- Carried from pass 1: `stale_materialized`'s docstring; `materialized_markdown`'s glued banner; `bin/sync.py`
  writing the `.akmon` path itself in two places.

### Fixes to pass-1 files found by pass 2

`project_root.mjs`: `aitnaRoot` / `akmonMount` / `isProjectRoot` and `materialization.mjs` `materializedDir`
and `record.mjs` joined paths lexically, so a `..` in the project root was collapsed before the filesystem saw
it (`Path` keeps it); `resolvePath` rethrew `ENAMETOOLONG` / `EACCES` where Python 3.12 ignores any `OSError`
except a symlink loop. `markers.mjs`: Python truthiness of an identity (`[]`/`{}` mean none), `AttributeError` for
a truthy non-string identity, and the Python class names on its throws (`FileNotFoundError`, `KeyError`,
`UnicodeEncodeError`; `project_root.mjs` `RuntimeError`). `routing.mjs`: `transcript_path` truthiness.
`exceptionClassName` (`pyvalue.mjs`) names a Node system error as the `OSError` subclass Python raises and a
`SyntaxError` as `JSONDecodeError` — the crash handlers print the class, so it is owner-visible text.

### Latency (ADR 0020/D05; M124)

Two interleaved passes over the 36 payloads, 30 launches per scenario and implementation: JS median of scenario
p50s **144.8 / 151.7 ms**, Python package mode **177.7 / 178.6 ms** (M122: 178.3 / 194.4); JS was not slower in any
scenario of either pass. The first build had only an 8% margin: `node:crypto` costs about 20 ms to import,
so SHA-256 is plain JS (`sha256.mjs`, checked against `node:crypto` on about 500 inputs) and temp-file names no longer
use `randomInt`. `NODE_COMPILE_CACHE` would gain about 7 ms more; not taken.

### Evidence of fidelity

- **Differential, Python hook vs JS hook** (`diffh.py`, scratchpad): each of the 36 scenario payloads and every
  one-field mutation of it (deleted, or replaced by `null`, booleans, numbers, `[]`, `{}`, a list, a dict, `"é"`,
  a lone surrogate, `../..`, an absolute path, …) plus 15 raw stdin shapes (empty, `null`, a list, truncated,
  `NaN`, BOM, invalid UTF-8, duplicate keys, a 30-digit integer, CRLF); 90 variants per scenario, 3131 in all;
  stdout, stderr, exit code, the files left in the project and in the temp dir compared after normalization:
  **0 differ**. The implementing agents ran wider groups each, all green but the divergences above: about 930
  routing-hook cases (broken data files, overlays, transcripts, logs, 41 `TZ` values), 1812 Codex cases and 80000
  pure-function inputs, 2003 path/session/raw cases, and 25000 random table rows.
- **Corpus.** `runner.py` (Python, full): 140 of 140, coverage gate 133 items (14 units) and pairing gate OK;
  `--impl node --area units --area hooks`: 50 of 50.
- **Gates (working tree).** `python3 meta/self_ci.py`: exit 0, every line OK. `pytest meta/tests`: 1929
  passed with the a22 size-limit test deselected (it fails on the a22 files only). `tsc --checkJs`, `eslint js`
  clean; `node --test` 178 of 178. `ruff check` clean on everything but `meta/experiments/a22-p3`; `ruff format
  --check` fails on `hooks/hook_core.py`, `hooks/codex_adapter.py`, `meta/conformance/runner.py` and
  `meta/tests/test_hook_core.py` as it does at HEAD (no new failure). `npm pack --dry-run` lists the 13 hook
  files and `common/py*.mjs`, `sha256.mjs`; the carriers-match test (one file list) passes.
- **Not run:** Windows, Python 3.13/3.14, a hook through a live harness (N10).
- **Process:** two breaches of "Edit only on shared files" were reported by the implementing agents (a
  read-modify-write script on `probe.py` by T; a slice script on `claude_adapter.mjs` / `codex_adapter.mjs` by H1);
  none touched a22 files, and the results were checked by the gates above and the differential.

### Hand-off

- **C105:** the JS `sync` writes the Node wiring spelling and gets its data key; `ecosystem` in the record and the
  node fixture layer then replace the "Python-synced" warmup; `verify`'s `hooks.*` findings for the Node spelling.
- **C108:** message texts that name `python3 $(akmon path)/tools/…` (the init instruction, `second_opinion`,
  the status line's self-check) get the `akmon tool` spelling in Node package mode, with the normalization rule.
- **C111:** `diffh.py` is the seed of the recorded-payload + mutation run; the 15 raw stdin shapes and the field
  mutation list are its first corpus.

## Owner decisions on the pass-2 review

- **`codex-hook -h`** — leave as is. A port is native: where the platform's default differs (argparse help, exit 0), the
  JavaScript keeps its own conventions. This became ADR 0020 D08 and the register
  [`meta/conformance/DIVERGENCES.md`](../conformance/DIVERGENCES.md) (DV1).
- **Float `1.0` in a payload** — accepted as a divergence (DV2 in the register).
- **The commit guard matched words, not the command** — fixed in both implementations. `git` is a command word only when no
  letter, digit, `_`, `.` or `-` touches it, and a subcommand may not continue a name from the left (`pre-commit`,
  `.push`); `git-commit-guard.py`, `.git/hooks/pre-push`, `my_git push`, `git add pre-commit-config.yaml` are no longer
  asked, while `git commit-tree`, `git merge-base` and `/usr/bin/git commit` stay guarded. Nine rows in
  `units/hook_core.toml` (`git/name-*`, `git/word-*`) and two parametrized tests in `test_hook_core.py` pin it.
- **`re.ASCII` on the privilege, `git` and `apply_patch` patterns** — confirmed.
- **Message texts naming `python3 $(akmon path)/tools/…`** — stay for C108.
