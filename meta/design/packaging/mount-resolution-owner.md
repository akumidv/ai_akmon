# Design note: who answers "which standard tree does this project run?"

> **Closed — [C69](../../TASKS.md), owner-decided and landed at
> [D2-26](../../D2_LEDGER.md); kept because the measurement below is why.** Provenance:
> C37 review side finding, measured on this tree. **The decision: the recorded `mount` is a veto
> over the directory check, not a replacement for it** — records `package` → the materialization,
> else the mount if it exists, else the materialization. Replacement was rejected on a measured
> state, not a preference: see "Do not lose in the fix" below. The question itself is settled by
> [ADR 0009 §4-5](../../decisions/0009-packaging-package-carrier-and-mount-modes.md): the recorded
> `mount` decides. This note records the module that answered it differently, what that cost —
> measured, not argued — and the fork the fix had to pick.

## The split

> Past tense from here on: `akmon_runtime_root` now applies the veto, so the split below is
> the state as found, kept as the record of what it cost.

`hooks/hook_core.py::akmon_runtime_root` answers with **directory existence**:
`<AITNA_ROOT>/akmon` if that directory is there, else `<AITNA_ROOT>/.akmon`. Every other owner
of the same decision reads the record instead — `bin/sync.py::is_package_mode` /
`standard_tree_root`, `src/akmon/cli.py::_mounted_akmon_root`, and (since C37)
`tools/model_routing/init.py::_standard_tree_root` — each carrying a comment that a stale mount
from a prior mode must not shadow a package-mode pin. So one project can answer the question
two ways at once.

## What it costs, measured

A package-mode fixture (`mount = "package"`) with a leftover `_aitna/akmon` carrying a modified
registry:

- `akmon_runtime_root` returned `_aitna/akmon`;
- `routing.load_registry`, through the hook's own path, bound the **stale** registry's worker
  alias;
- `d2_ledger_reminder_message` told the session to run
  `_aitna/akmon/tools/d2_ledger/d2_ledger.py`.

All three silently. The blast radius is every wired hook that resolves runtime files:
`hooks/model-routing.py` (the registry, and the recovery instruction it prints),
`hooks/delegation-log.py` (the registry used for its role-matrix warning), and the D2 reminder —
i.e. the tier→model binding, warning classification and tool paths an agent is told to run, taken
from a tree the project no longer pins. The delegation log row itself is formed from local config
before that registry read.

`akmon init --switch-mode` now prints "remove the now-unused mount" as a migration step, which
narrows the window without closing it: the mount is removed by a human, and until then the
hooks are wrong.

## The fork (why it is not a one-line copy of `is_package_mode`)

`hook_core` must stay stdlib-only **and** runnable from the materialized
`<AITNA_ROOT>/.akmon/hooks/` copy — so it cannot import `sync`, which is not materialized at
all. A local read would have made it another narrow `.akmon.toml` reader. That was the fork:

- **one shared home** for the reader that every carrier can reach, or
- **deliberate duplication**, with each copy stating why it is not the others.

Same shape as the second-owner question in [C64](../../TASKS.md), and the reason C46 exists.

**Resolved: one shared home.** The reader is `common/record.py`, lifted out of `bin/sync.py`
unchanged; `sync` re-exports it and the hooks import it. This note counted a local read as the
*third* such reader — that was understated. There were five, and the hooks would have been the
sixth:

| reader | why it was kept local |
|---|---|
| `bin/sync.py:76` `read_akmon_toml` | the original, and the richest — nested, `tomllib` + stdlib fallback |
| `tools/release/release_check.py:496` | "this tool does not import `sync`" — stale since C74; it imports `common.*` |
| `tools/d2_ledger/d2_ledger.py:272` | self-contained tool |
| `tools/model_routing/init.py:60` | narrow top-level scalar read |
| `src/akmon/cli.py:144` | must not depend on the *consumer's* tree — still true, and it can ask the embedded one |

Only the hooks' reader moved. Folding the other four is [C75](../../TASKS.md): each carries a
justification to re-examine on its own, and three of the four are weaker than when written.

> **Premise corrected, and the shared home now exists ([C73](../../TASKS.md) →
> [C74](../../TASKS.md)).** This note previously said `bin/` "does not exist at all" in the
> materialized tree, and priced the shared home off that. It was already untrue — `_materialized_files`
> had been copying a module there since C57 — and it is now moot: C74 gave the shared stdlib-only
> utilities their own package, `common/`, materialized whole into `<AITNA_ROOT>/.akmon/` beside
> `hooks/` and present at the same tree-relative path in the mounted tree and the wheel's embedded
> tree. `hooks/hook_core.py` already imports from it (the project-root walk, C73/C74), so the
> "one shared home" branch is no longer a proposal to cost — **it is built, it is proven by the
> wheel smoke's materialized-hook leg, and adding the `.akmon.toml` reader to it is one module.**
>
> What this does **not** decide is the question this note is actually about: whether the hooks
> should read the recorded `mount` at all, or keep resolving by directory existence. That is a
> behavioural choice about what the hooks trust, and it stays the owner's. Only the cost argument
> against the shared home is withdrawn — it can no longer be the reason to pick duplication.

## Do not lose in the fix

- A project with **no record and no mount** must still resolve to `.akmon`: records that
  predate the `mount` field default to `submodule` (`sync.py::read_mount_mode`). **This is the
  state that decided the shape** — a record-only rule sends such a project to a mount that is
  not there, so the record vetoes the directory check rather than replacing it.
- The hooks must keep running venv-free from the materialized copy. Held: `common/` is
  materialized whole beside `hooks/`, and the wheel smoke runs `.akmon/hooks/codex-hook.py`.
- ~~The regression needs the state no test covers today~~ — `meta/tests/test_adapters.py` now
  pins all seven states. The previous rule was wrong in exactly two of them (a package record
  beside a stale mount, and the same record in the documented `mount = "package"  # comment`
  form) and unchanged in the other five.
- A record a hook cannot parse must not end the session. Found while landing this:
  `read_akmon_toml` documented "absent or unreadable → `{}`" but let `TOMLDecodeError`
  propagate, so on 3.11+ a malformed record crashed `sync`/`verify` while 3.9 parsed it to a
  partial dict. It now falls through to the stdlib parser, which is what it documents and what
  keeps the two hosts agreeing.
