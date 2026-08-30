# Design note: who answers "which standard tree does this project run?"

> **Open — backlog [C69](../../TASKS.md), blocked pending owner choice, queued as
> [D2-26](../../D2_LEDGER.md).** Provenance:
> C37 review side finding, measured on this tree. Implementation must not begin while the fork
> below is undecided. The question itself is settled by
> [ADR 0009 §4-5](../../decisions/0009-packaging-package-carrier-and-mount-modes.md): the recorded
> `mount` decides. This note records that one module still answers it differently, what that
> costs, and the fork the fix has to pick before any code moves.

## The split

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
`<AITNA_ROOT>/.akmon/hooks/` copy, where `bin/` does not exist at all — so it cannot import
`sync`. The read has to be local, which would make it the **third** narrow `.akmon.toml`
reader (`cli.py` and `tools/model_routing/init.py` already carry one each, both justified in
place). Pick first:

- **one shared home** for the reader that all three can reach from both carriers, or
- **deliberate duplication**, with each copy stating why it is not the others.

Same shape as the second-owner question in [C64](../../TASKS.md), and the reason C46 exists.

## Do not lose in the fix

- A project with **no record and no mount** must still resolve to `.akmon`: records that
  predate the `mount` field default to `submodule` (`sync.py::read_mount_mode`).
- The hooks must keep running venv-free from the materialized copy.
- The regression needs the state no test covers today: `meta/tests/test_adapters.py` pins only
  the *no mount at all* case, never a **stale** one.
