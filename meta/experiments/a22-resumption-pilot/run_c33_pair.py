"""Use the frozen descendant-inclusive runner for the C33 acceptance case."""

import importlib.util
from pathlib import Path


packet = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("a22_pair_runner", packet / "run_c98_pair.py")
assert spec is not None and spec.loader is not None
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
runner.MANIFEST = packet / "C33_MANIFEST.json"


if __name__ == "__main__":
    raise SystemExit(runner.main())
