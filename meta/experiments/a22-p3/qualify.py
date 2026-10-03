# ruff: noqa: ANN201, B905, D103, S311
"""Write P3's sealed 32-cell qualification map; do not execute models here."""
import json
import random
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    cells = [(f"P3-{card:02d}", tier, repeat) for card in range(1, 9)
             for tier in ("strongest", "mid") for repeat in (1, 2)]
    ids = random.Random(20261003).sample(range(1000, 10000), len(cells))
    sealed = {f"q{ident}": {"case": case, "arm": "A", "tier": tier, "repeat": repeat}
              for ident, (case, tier, repeat) in zip(ids, cells)}
    (HERE / "runs" / "qual-sealed-map.json").write_text(json.dumps(sealed, indent=2) + "\n")
    print(f"{len(sealed)} qualification cells")


if __name__ == "__main__":
    main()
