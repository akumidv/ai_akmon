# ruff: noqa: ANN001, ANN201, D103, E501
"""Create arm- and tier-blind scorer packets from sealed P3 exchanges."""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main(map_path, out_dir):
    sealed = json.loads(Path(map_path).read_text())
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for run_id, cell in sealed.items():
        exchange_path = HERE / "runs" / f"{run_id}.exchange.json"
        if not exchange_path.exists():
            raise FileNotFoundError(f"missing exchange for sealed run {run_id}")
        case = json.loads((HERE / "cases" / f"{cell['case']}.json").read_text())
        exchange = json.loads(exchange_path.read_text())
        lines = [f"# Run {run_id}", "", "## Exchange"]
        for index, turn in enumerate(exchange["turns"], 1):
            lines += [f"### Turn {index} user", "", turn["user"], "", f"### Turn {index} subject", "", turn["assistant"], ""]
        lines += ["## Elements (PASS or FAIL, with one-line reason)", ""] + case["scoring"]
        (out / f"{run_id}.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main(*sys.argv[1:3])
