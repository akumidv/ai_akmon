# Design note: why the Python floor moved from 3.9 to 3.11

> **Decision owner-verified at D2-34; C68 landed in `db9ad7e`.** Provenance: C37 side finding, measured on the tree that
> declared Python 3.9. The filename is retained because this note is the historical evidence for
> retiring that floor. The operative contract is now Python **3.11 or newer** for the package and
> every shipped venv-free entry point; Python 3.9 and 3.10 are unsupported.

## What was measured

The former `requires-python >=3.9` claim was not true. A Python 3.9 run produced
`617 passed, 24 failed, 7 skipped` from two independent causes:

1. `hooks/codex-hook.py` evaluated a PEP 604 union at import time, so all four generated Codex
   hook entries failed before any advisory ran. Eighteen failures reached this one line through
   `meta/tests/test_adapters.py`.
2. Six `meta/tests/test_validate.py` cases asserted Python 3.11+ `tomllib` behaviour without a
   version guard.

The repair was small — one compatibility spelling and six guarded expectations — but retaining
3.9 would keep every venv-free hook, launcher and tool constrained by a legacy interpreter. The
owner chose one modern baseline instead of continuing that obligation.

## Decision

- The single supported floor is **Python >=3.11**. It applies both to package installation and to
  the bare `python3` used by generated hooks in mounted, vendored, subtree and package carriers.
- Python 3.9 and 3.10 consumers must upgrade that host interpreter before adopting the release.
  Raising package metadata alone is insufficient because mounted hooks do not execute inside the
  package environment.
- Zero runtime dependencies and the stdlib-only shipped runtime remain unchanged.
- The change is Breaking and requires a pre-1.0 `x` bump. Its migration names both interpreters:
  the one installing/running the package and the bare `python3` used by generated hooks.

Rejected alternatives:

- **Repair and retain 3.9** — cheapest immediate code change and widest host reach, rejected to
  end the continuing pre-3.11 compatibility obligation.
- **Raise only to 3.10** — fixes the observed PEP 604 import but retains the pre-`tomllib` split
  and creates another near-term floor transition.
- **Package 3.11 / hooks 3.9** — creates two support contracts and preserves the compatibility
  work C68 was meant to retire.
- **Metadata-only 3.11** — protects package installation but leaves mounted bare-Python hooks on
  an unsupported interpreter without a truthful contract.

## Acceptance carriers

- `pyproject.toml` declares `requires-python = ">=3.11"`; the lock repeats it and built wheel
  metadata contains `Requires-Python: >=3.11`.
- Ruff targets `py311`; CI retains an exact 3.11 floor leg and a 3.13 upper compatibility leg.
- The full suite, Ruff, self-CI installed-wheel smoke and build pass on the supported development
  interpreter. The 3.11 CI leg is the lower-bound runtime/import probe.
- A contract test joins the project floor, Ruff target and CI matrix so they cannot drift apart.
- Compatibility fallbacks may remain where harmless or where they also implement malformed-input
  fail-open behaviour; their presence is not a support promise below 3.11.
