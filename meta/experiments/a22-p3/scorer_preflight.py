#!/usr/bin/env python3
"""Fail-closed scorer mechanics preflight for the pinned P3 routes.

Inventory mode is model-free. Dispatch mode is deliberately gated on an
owner-supplied pricing/stop record and route attestations. It captures raw
stdout/stderr and machine-readable events for every attempted dispatch.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
RUNS = HERE / "runs"
SCORING = HERE / "scoring"
ROUTES = {
    "codex": {"executable": "codex", "version": "codex-cli 0.156.1",
              "model": "gpt-6-astra", "effort": "medium"},
    "qwen": {"executable": "qwen", "version": "0.24.7",
             "model": "qwen3.8-27b", "max_tool_calls": 0},
}
INPUT_CAP = 3_000
OUTPUT_CAP = 1_000
PASS_RESERVATION = 4_000
TOTAL_PASS_CAP = 240
TOTAL_TOKEN_CAP = TOTAL_PASS_CAP * PASS_RESERVATION
SPEND_CAP_USD = 25.0


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(f"refusing to overwrite {path}")
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_inventory() -> None:
    """Capture installed executable paths, versions, and current limit flags."""
    output = RUNS / "scorer-route-inventory"
    output.mkdir(parents=True, exist_ok=True)
    expected_files = [output / f"{route}.{kind}.{stream}.txt"
                      for route in ROUTES for kind in ("version", "help")
                      for stream in ("stdout", "stderr")]
    expected_files.append(output / "inventory.json")
    if any(path.exists() for path in expected_files):
        raise FileExistsError("route inventory already exists; refusing to replace raw evidence")
    result: dict[str, Any] = {"schema": 1, "recorded_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                              "routes": {}}
    for name, route in ROUTES.items():
        executable = shutil.which(route["executable"])
        if executable is None:
            result["routes"][name] = {"status": "UNAVAILABLE", "expected": route}
            continue
        version = subprocess.run([executable, "--version"], capture_output=True, text=True, check=False)
        help_result = subprocess.run([executable, "--help"], capture_output=True, text=True, check=False)
        version_text = (version.stdout + version.stderr).strip()
        help_text = help_result.stdout + help_result.stderr
        (output / f"{name}.version.stdout.txt").write_text(version.stdout, encoding="utf-8")
        (output / f"{name}.version.stderr.txt").write_text(version.stderr, encoding="utf-8")
        (output / f"{name}.help.stdout.txt").write_text(help_result.stdout, encoding="utf-8")
        (output / f"{name}.help.stderr.txt").write_text(help_result.stderr, encoding="utf-8")
        result["routes"][name] = {
            "expected": route, "executable_path": executable,
            "version_output": version_text,
            "version_matches_pin": route["version"] in version_text,
            "help_exit_code": help_result.returncode,
            "output_token_limit_flag_in_help": "max-output-tokens" in help_text,
            "provider_usage_format_verified": False,
            "model_identity_verified": False,
            "dispatch_status": "NOT_RUN",
        }
    write_json(output / "inventory.json", result)
    print(output / "inventory.json")


def _events_and_usage(route: str, stdout: bytes) -> tuple[list[dict], dict | None]:
    text = stdout.decode("utf-8")
    events = []
    for line in text.splitlines():
        if not line.strip():
            continue
        obj = json.loads(line)
        if not isinstance(obj, dict):
            raise ValueError("non-object event")
        events.append(obj)
    if not events:
        raise ValueError("empty event stream")
    # Deliberately accept only explicit provider usage objects; never estimate
    # actual use from character counts or CLI-local counters.
    usages = []
    def visit(value: Any) -> None:
        if isinstance(value, dict):
            usage = value.get("usage")
            if isinstance(usage, dict):
                usages.append(usage)
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)
    visit(events)
    if len(usages) != 1:
        return events, None
    usage = usages[0]
    input_tokens = usage.get("input_tokens", usage.get("prompt_tokens"))
    output_tokens = usage.get("output_tokens", usage.get("completion_tokens"))
    if not isinstance(input_tokens, int) or not isinstance(output_tokens, int):
        return events, None
    return events, {"input_tokens": input_tokens, "output_tokens": output_tokens}


def dispatch(args: argparse.Namespace) -> None:
    # Unknown price, estimate, or named human stop operator means no call.
    if args.input_usd_per_million is None or args.output_usd_per_million is None:
        raise SystemExit("STOP: route prices are unknown; no scorer dispatch made")
    if not args.cost_operator:
        raise SystemExit("STOP: no named manual cost-stop operator; no scorer dispatch made")
    if args.estimated_total_usd is None or args.estimated_total_usd > SPEND_CAP_USD:
        raise SystemExit("STOP: missing or over-ceiling total cost estimate; no scorer dispatch made")
    if not 1 <= args.input_tokens <= INPUT_CAP:
        raise SystemExit("STOP: packet input token count must be known and <= 3000")
    if args.route == "qwen":
        raise SystemExit("STOP: Qwen 0.24.7 --help does not expose an output-token cap; no call made")
    if args.route == "codex" and not args.codex_output_cap_attested:
        raise SystemExit("STOP: Codex output-token cap is not verified; no call made")
    raise SystemExit("STOP: provider usage and actual model identity formats remain unverified; no call made")


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="action", required=True)
    sub.add_parser("inventory", help="capture pinned CLI paths, versions, and help text; no model calls")
    run = sub.add_parser("dispatch", help="run one synthetic scoring control after all gates pass")
    run.add_argument("--route", choices=ROUTES, required=True)
    run.add_argument("--input-tokens", type=int, required=True)
    run.add_argument("--input-usd-per-million", type=float)
    run.add_argument("--output-usd-per-million", type=float)
    run.add_argument("--estimated-total-usd", type=float)
    run.add_argument("--cost-operator")
    run.add_argument("--codex-output-cap-attested", action="store_true")
    return p


def main() -> None:
    args = parser().parse_args()
    if args.action == "inventory":
        run_inventory()
    else:
        dispatch(args)


if __name__ == "__main__":
    main()
