# Design: `akmon update` — move the pin, then realign (A23)

> **Status: owner-decided in
> [ADR 0018 D03](../../decisions/0018-release-alignment-and-update-lifecycle.md#d03--explicit-update-and-rollback);
> implemented in the tree as C92, awaiting the owner's commit.** Extends the
> [packaging design](README.md) CLI contract.

## Problem

Moving a consumer to another akmon release is a documented manual procedure
([BOOTSTRAP](../../../BOOTSTRAP.md), "Pull the latest shared layer into a project"), different in
each mount mode. Its most easily skipped step, `akmon init` after the pin moved, is the one that
reinitializes the routing binding and advances `last_realign`; in the mounted modes nothing else
catches the skip. `init` already finds the newest release tag and moves an existing submodule pin
with `--ref`. Nothing put the steps in order.

## Owner decisions

| question | decision | rejected |
|---|---|---|
| name | `akmon update`, a flat verb like every other command | `akmon tool update` — the CLI has no command groups |
| target | `--ref` when given; else the newest final release tag the akmon repository advertises (`git ls-remote`); PyPI once published (V4) | a pre-release as "newest" |
| direction | without `--ref` the pin never moves back; an older `--ref` is a rollback, allowed and announced | refusing rollbacks; moving silently |
| package mode | uv only: `uv add --group <the pin's PEP 735 group>`; any other manager gets the command printed | editing `pyproject.toml` directly — `init` never edits the manifest, since it cannot know every dialect, while uv owns its own |
| records | ADR 0018 D03 decision, A23 design, C92 implementation | — |

## Behavior

1. **Read the record.** The mount mode, `akmon_version` and `last_realign` come from
   `<AITNA_ROOT>/.akmon.toml`; a project without one is refused with `akmon init` named.
2. **Resolve and compare.** The target is `--ref` or the newest release.
   `common/versions.py::order_key` places both versions (a development version before its release,
   a `git describe` distance after it). If the target is ahead, the pin moves. If it equals the
   recorded version, or `--ref` is absent and the record is already past it, the pin stays and the
   project is only realigned. An older `--ref` rolls back.
3. **Move the pin, per mount mode, and run `init`:**
   - `submodule`: `git fetch --tags <repo>` in the mount, from the repository the target was read
     from, then `init --ref <target>` checks it out and leaves it unstaged, as every pin bump is.
   - `package`: `uv add --group <group> "akmon @ git+<repo>@<target>"` rewrites the pin in the
     spelling the project keeps it in, and syncs the virtualenv. A bare `akmon` in the group with
     its git URL in `[tool.uv.sources]` (uv's own default) is moved there: uv rewrites that entry
     in place. A PEP 508 pin (`akmon @ git+…`) takes `--raw`: without it uv moved the git URL into
     `[tool.uv.sources]` and left a bare `akmon` in the group. `--raw` over a sources entry fails
     the other way — the stale entry still wins resolution; the live update of the attached
     consumer failed on exactly that. All measured with uv 0.11.21. Then the project's own `.venv/bin/akmon init` runs, never this process's
     `init`, which may be the version uv just replaced. A pin outside `[dependency-groups]` is
     refused: `uv add` could not move it in place.
   - `vendored`: the mount is a copy of the tree of whichever CLI runs `init`, so `init` runs from
     exactly the pinned release — in process when this CLI is that release, otherwise
     `uvx --from git+<repo>@<tag> akmon init`. Realigning with any other CLI would re-copy that
     CLI's tree over the pin without a word.
   - `subtree`: `git subtree pull` commits, so the command and the follow-up `akmon init --ref`
     are printed and nothing runs (exit 2).
4. **Check.** `sync --check`, then `verify --strict`, run by the tree that now governs; the exit
   code is the first failure.
5. **Hand over.** The CHANGELOG window from `last_realign` to the target, what to stage, the
   downstream bump record, and the Codex `/hooks` re-approval when `.codex/hooks.json` exists.

## Boundaries

- **Never commits or stages** (D5). `uv add` changes `pyproject.toml`, `uv.lock` and the
  virtualenv; the submodule checkout changes the working tree. The index is untouched.
- **Does not walk the delta-check.** It prints the CHANGELOG window; reading the Breaking and
  Migration lines stays the owner's or the agent's step.
- **Does not record the bump.** The downstream bump record stays in the consumer (C2 keeps the
  release-subject side); `update` prints the step.
- **Prerequisites are named where they fail**: git and network access for tag discovery (or
  `--ref`), git for the submodule fetch, uv in mode `package`, uvx in mode `vendored`.

## One rule each

"Newest release" had three spellings in `init` (local tags, `ls-remote` for the package pin, and
another `ls-remote` for the subtree command), and none excluded a pre-release. It is now
`_init._newest_release`, shared by all three and by `update`. Version order has one owner,
`common/versions.py::order_key`, beside `split_version` and `is_final`.

## Carriers

`meta/tests/test_update.py`: direction for each plan case; pre-releases ignored; the network
prerequisite and `--ref` named on failure; each mount mode's exact commands; uv and uvx absent →
the command printed and nothing run; a pin outside `[dependency-groups]` refused; vendored never
realigns with a CLI of another version; a failing `init` stops before the checks and a failing
check fails the run; and an end-to-end submodule move over `file://` that moves the mount, leaves
the index at the old pin and creates no commit.
