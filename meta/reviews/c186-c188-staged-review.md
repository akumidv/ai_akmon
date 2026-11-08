# Review — the staged C186 and C188 work, before the owner's commit

> **Disposition.** The majors and the prose findings were fixed before the owner's commit. The minors still present in the tree are tracked in C189 (park code, tests and scenarios), C191 (export leftovers) and C196 (fuzz entry and measurement rows) in [`TASKS.md`](../TASKS.md); the verdict and gate tables below describe the staged tree as reviewed.

Scope: the owner's staged tree on `main` over `8ad4287` (100 files): C186's holder lease, jobs, the
active unit, worktrees and the retired local index in `tools/park/park.py`, `common/project_root.py`
and their JavaScript twins; their tests and conformance scenarios; C188's ADR 0029, the merge record
and the prose around them. Checked against `docs/design/park-and-resume.md`, ADR 0028 D08–D12 and
ADR 0029 D01–D09. Four read-only reviews (Python, the JS twin's parity, tests and scenarios, prose)
and one gate run; the gravest Python finding re-read by hand. The words *kit* and *job* in code are
expected until C189 and are not findings.

## Verdict

**Not ready to commit as is: one gate is red, and the lease code breaks D09 in four places.**

- The JS twin matches Python on about 120 side-by-side commands. Its two divergences are on edge
  inputs.
- Unit tests are green: 213 in `test_park.py` and 172 node tests.
- Lint, types and format are green.
- Self-CI fails on three stale scenarios.

## Gates

| Gate | Result |
|---|---|
| `uv run pytest` | 3 failed of 3061, all from the `.venv` being Python 3.14.6, which `requires-python >= 3.12` allows: `fnmatch` writes `\z`, `datetime` has new error wording, and `is_file()` no longer raises `ENAMETOOLONG`. **Fixed in this session**: `meta/tests/test_check_runner.py`, `test_learning.py` and `test_project_root.py` now pass on 3.12.3 and on 3.14.6. |
| ruff check / format, tsc, oxlint, oxfmt, `node --test` (1137) | pass |
| `meta/self_ci.py` | **fail**: `tools/park-list-filter-status`, `tools/park-write-existing-row` and `tools/park-write-row-with-link`, on Python and on node. They test the retired local index (`list --status`, a written `.local/TASKS.md`, `state:`/`peers:` header keys). They were staged as deleted at the session's start and are tracked again now. Their replacements exist: `park-list-status-flag-retired`, `park-project-index-untouched` and `park-write-new`. The wheel and npm legs pass, with network reach present. |

## Findings — code (Python; the twin mirrors it unless noted)

### Major

1. **`write` takes a stale lease silently.**
   - Where: `tools/park/park.py:1860-1866` (`_cmd_write`, `_refuse_foreign_lease`).
   - D09: a stale lease is *offered to the owner*, never taken silently, and the replaced holder is
     kept.
   - The code: `write` without `--takeover` rewrites the note over another session's stale lease,
     then deletes that `HOLDER`. The replaced holder is not recorded.
   - It is also a race: check, write, then unlink whatever `HOLDER` is there. A lease taken in
     between is lost.
   - The docstring calls this intended, so the code and D09 disagree on purpose. Either the design
     or the code changes.
2. **`write` drops the note's earlier sessions.**
   - Where: `write_kit` (`:1342`) rebuilds `sessions` from the command line.
   - Effect: the holder that a `hold --takeover` recorded disappears on the next write. D09 says it
     is kept.
3. **Anonymous holders are equal.**
   - Where: `Holder.same_as` (`:118-120`) with `_holder_of` (`:1729-1736`).
   - Effect: two `hold C1` calls with no `--harness`/`--session-id` both succeed, so a unit has two
     holders. D09 says one holder per unit.
4. **A project in a repository subfolder gets the top level's dev root.**
   - Where: `common/project_root.py:224-225` (`_resolve_git_common_root`).
   - Effect: a monorepo layout `mono/proj` wrote its kit to `mono/_aitna/.ergon/`. That breaks D11:
     "the kits of the project".
5. **`local-id` reuses a `_T` id the legacy index holds.**
   - Where: `next_local_id` (`:1571-1578`) ignores `.local/TASKS.md`.
   - Effect: on this repository it prints `_T6`, and `meta/.local/TASKS.md` already has a `_T6`
     row. That breaks D12: never reused, the old index read as legacy input.
6. **One bad plan stops `park list` for every kit.**
   - Where: `JOB.md` is written unchecked and not atomically (`job_doc_for`/`write_job_doc`,
     `:1358-1375`).
   - Effect: a plan header `id: c3` produced a `JOB.md` that does not read back. After that,
     `park list` fails for every kit with an error that does not name the kit.
7. **A kit's state joins only `done` from its jobs.**
   - Where: `kit_state` (`:1287-1303`).
   - Effect: a held job leaves its kit reading `not started`. D08/D09 say the kit's state is joined
     from its jobs.
8. **Takeover is half-done.**
   - Where: `:895-899`, `:935-954`.
   - The replaced holder is recorded only when the unit has a `PARK.md`, so a job leaves no trace.
   - The replaced holder's uncommitted paths are not named; the design says they are named before
     anything else.
   - The lease is replaced before the note is parsed.
   - `remember_holder` writes non-atomically.
9. **`close` crashes on a second close and frees other sessions' leases.**
   - Where: `:1948-1957`; the JS twin `park.mjs:3170` has the same crash.
   - `close` over an already-closed kit of the same id and name ends in an `OSError` traceback after
     the leases are already gone. `write` accepts reusing a closed kit's id and name.
   - `close` releases another live session's lease with no identity check. Which behaviour is
     intended is not specified.

### Minor

- **Takeover and staleness:**
  - `--takeover` also takes a *fresh* lease, and the `held` message invites it (`:895-897`).
  - A corrupt lease stamp reads as stale: `_parse_stamp` returns `0.0` as a failure (`:824-829`).
  - `digest` passes `machine=""`, so a copied lease reads `active` there and `parked` in `list`
    (`:743`).
- **Robustness:**
  - `renew_lease` is a non-atomic rewrite (`:917-920`).
  - Losing the exclusive-create race gives a raw `FileExistsError` (`:889-890`).
  - The takeover temp file has a fixed name (`:912`).
  - A non-ASCII label makes an empty slug, `jobs/1-` (`:1050-1053`).
  - `write --machine m` without `--harness` is refused (`:1682-1687`).
- **Guardrail § Code design:**
  - `_GIT_COMMON_CACHE` is mutable module state (`common/project_root.py:65`).
  - `Path.cwd()` is read deep in the logic (`:1373`, `:1735`).
  - `export_kit` skips only `HOLDER`, so `HOLDER.new` and `.tmp` leftovers travel (`:1554`).
- **Parity:**
  - A whitespace-only `--harness`/`--session-id` is refused by Python and accepted by JS
    (`park.py:1683` vs `park.mjs:2744`).
  - `tail.isdigit()` lets `²` through to `int()`, so Python crashes where JS returns null
    (`park.py:1517`); use `isdecimal()`.
  - `project_root.mjs:323-325` loads `child_process` through `createRequire`, an import trick.
  - `park.test.mjs:125,163,590` leave temp folders behind (455 under `/tmp`).
- **Beyond the rename (C189, C190 own these):**
  - `parse_job_line` drops unknown cells such as `zone:` silently (`:1003-1014`).
  - The active unit is read from the folder layout and the lease's `worktree` is the cwd, while
    0029/D06 reads the git top level.
- **Ride-along from C187:**
  - The `fuzz.toml:64` DV40 entry has no `scripts` restriction, so under 3.14 it hides every
    `long-string:*` divergence, not only the measured `session-start-agent` case.

## Findings — tests

- **Missing scenarios:**
  - `close` over an existing closed kit.
  - `close` of a kit another session holds.
  - `no_kit` on `hold`, `release`, `job` and `export`.
  - `active` on a stale or other-machine lease.
  - A legacy `.local/TASKS.md` surviving `write` byte for byte (only a pytest exists).
  - `init` ignoring `.worktrees/` on the Python side.
- **Fixtures:**
  - The unit tests restate the 24-hour threshold instead of reading `park.json`
    (`test_park.py:136,975,985,1042`, `park.test.mjs:251`).
  - No test sits at exactly the threshold.
- **Counts:** the C186 row says 57 scenarios. The tree holds 60, and 57 is the green count once the
  three stale ones go.
- **Clean:** date and environment stability. Fixtures use only `2000-01-01` and `2099-01-01`, and
  every lease-holding scenario passes `--machine`.

## Findings — prose

### Major

1. **The merge record and the park design still read as undecided.**
   - `docs/design/ergon-athlos-merge.md:3-5,17,26-28,349` still say "Draft — four owner codes are
     open … no ADR".
   - `docs/design/park-and-resume.md:300,317,676,715-718` and the A59 row say the same.
   - Both contradict ADR 0029 (accepted) and C188 (done).
2. **Two export designs.**
   - `park-and-resume.md:184,360-368`, `pipelines/tasks.md` (~110) and `tools/README.md` describe a
     single bundle file with `import <bundle> --as`.
   - ADR 0029/D07, §11.10 W4 and C191 describe a directory with bundles, a patch, an archive and a
     manifest.
3. **`park-and-resume.md` states superseded rules with no pointer.**
   - Superseded: the folder-name active unit (`:459`), the agent-made worktree (`:482`), and "the
     guard passes any non-default branch" (`:665`).
   - The rules that replace them: 0029/D06, D09 and C190.

### Minor

- **ADR 0029 and its index:**
  - D-C190-DETACHED and D-C191-SOURCE are accepted but appear in no ADR block.
  - 0029 says it amends ADR 0008 §4, but 0008 carries no note.
  - The `docs/adr/README.md` row lists only part of what 0029 amends.
  - The note at 0028/D10 says "before the folder name", while 0029 retires that rule.
- **The commit rule:**
  - D09 and AGENTS say "an agent changes no history in the main checkout", yet "the owner asks the
    agent to merge or squash". That needs "except what the owner asks in so many words".
  - The shipped carve-out still covers only `_aitna/<id>…` job branches (C190).
- **One owner per fact:** the record repeats D01, D04, D05 and D09 in §11.1–§11.12 instead of
  linking.
- **Records live in the project:** the record defers to `EVIDENCE.md` and `materials/`, which are
  in the ignored kit.
- **Language and dates:**
  - Russian quotations sit in the record's P10/P11 (`:56-57`).
  - A full date sits in the C187 row ("seeded on 2026-10-28").
- **TASKS and MEASUREMENTS:**
  - C189 and C184 are `active` with nothing started.
  - M204–M207 lack the `evidence:` field.
  - M208's date is month-only.
  - The M210 anchor was broken; **fixed in this session**.
  - Pre-existing: two broken anchors into `node-consumers.md#f5…`.
- **Internal inconsistencies:**
  - The record gives Codex's worktree path two ways (`:476` vs M220).
  - "this section's earlier draft" (`:576`) is history.
  - "P3" names both a package and a park step.

## Verified true

- **Lease basics:**
  - Exclusive create (`O_EXCL`).
  - Another machine's lease is stale at once.
  - Takeover via `hold --takeover`.
  - The export leaves `HOLDER` out.
- **Jobs:**
  - `JOB.md` comes from the plan line.
  - The refusals `no_plan`, `no_job`, `job_label` and `bad_plan` exist.
- **Notes and listing:**
  - The note has no `state`/`peers`.
  - Branch and revisions are read from git.
  - `list --task/--closed` works.
  - The active unit is read from the worktree folder.
  - `ergon_root` goes through `--git-common-dir`.
- **Local index retirement:**
  - `init` ignores `.worktrees/`.
  - No index row is written.
  - Closed kits move to `.closed/`.
  - `_T` ids are counted over live and closed kits; see finding 5 for the legacy index.
- **Code shape:** stdlib-only, no import-time work, no function past a screen.
- **Prose:**
  - ADR 0029 agrees with the record on levels, words, key, holder, export and commit scope.
  - Every command the design names exists.
  - All links in the touched documents resolve, apart from the two pre-existing ones.
