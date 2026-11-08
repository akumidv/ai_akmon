#!/usr/bin/env python3
"""The model-profile probe: ask an endpoint's models the same items, grade the answers, write the ledger.

Three commands, in the order a refresh uses them:

* ``gate`` - run the **gold-sanity gate** over the item set and report each case: the hidden
  test must fail on the buggy program and pass on the fixed one. Nothing is asked of any model
  before this passes. It needs docker for the sandbox and no endpoint.
* ``plan`` - print what a run would ask and what it would cost (calls, wall-clock, tokens).
  Nothing is sent; the endpoint is asked only for the list of models when ``--models`` is not
  given.
* ``probe`` - run it: ask every selected model every selected item, grade the answers, and
  write the ledger and the per-cell detail files as the run goes.

**The spend is gated.** ``probe`` prints the plan and refuses to send anything unless it is
given ``--yes``. A measurement that costs a hundred calls must be a decision, not a side
effect of a command line. ``--token-budget N`` caps what each model may spend.

**A deferral is not a failure.** A transport error, an empty answer, an answer cut off by the
output-token cap and an attempt skipped for the budget are counted on their own line and stay
out of the pass rate, so a rate is always a rate over answers the models really produced.

The endpoint is an OpenAI-compatible server given by ``--endpoint URL``. The bearer token is
read from the environment variable *named* by ``--token-env`` (default ``AKMON_MODEL_TOKEN``)
and is never printed or written anywhere.

A run writes under ``<dev root>/.local/model_profile/<run>/`` (the per-user, gitignored local
layer) unless ``--out`` names a directory.

Usage:
    python3 tools/model_profile/cli.py gate
    python3 tools/model_profile/cli.py plan --endpoint URL --models a,b
    python3 tools/model_profile/cli.py probe --endpoint URL --models a --families hunt --token-budget 50000 --yes

Standard library only, and nothing happens at import time but the tree root joining the import
path (so the shared ``common`` package resolves).
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

# The tree root, so the shared ``common`` package resolves from the mounted tree and from a
# materialized copy alike (the way ``park/park.py`` reaches it).
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import cases
import oracle
import runner
import sandbox
import settings
import transport

from common.project_root import local_root, resolve_project_root

# The item set the pilot runs on, the environment variable a token is read from when
# ``--token-env`` names none and the folder under the local layer a run writes to are data
# (``profile.json``, read through ``settings.load().cli``).


class CliError(RuntimeError):
    """The command cannot be made - a broken request, not a model's failure."""


def default_item_set() -> Path:
    """The shipped item set the pilot runs on."""
    return Path(__file__).resolve().parent / settings.load().cli.default_items


def _load_items(path: Path, envelope: cases.Envelope) -> cases.ItemSet:
    """The item set, loaded and validated."""
    try:
        return cases.load_item_set(path, envelope)
    except cases.ItemSetError as exc:
        raise CliError(str(exc)) from exc


def _endpoint_config(args: argparse.Namespace, environ: Mapping[str, str]) -> transport.EndpointConfig:
    """The endpoint configuration, read once here from the command line and the environment."""
    if not args.endpoint:
        raise CliError("--endpoint URL is required: the base URL of an OpenAI-compatible endpoint")
    token = environ.get(args.token_env, "")
    if not token:
        raise CliError(
            f"the environment variable {args.token_env} is not set: it must hold the endpoint's bearer token"
        )
    base_url = args.endpoint.rstrip("/").removesuffix("/v1")
    try:
        return transport.EndpointConfig(base_url=base_url, token=token)
    except ValueError as exc:
        raise CliError(str(exc)) from exc


def _envelope_of(config: transport.EndpointConfig | None) -> cases.Envelope:
    """The envelope the request will carry, as the item set's hash sees it.

    The two must be the same object of facts: a score's envelope hash is only meaningful if it
    is the hash of the envelope the call actually used.
    """
    if config is None:
        return cases.Envelope()
    return cases.Envelope(
        temperature=config.temperature,
        max_output_tokens=config.max_output_tokens,
        timeout_s=config.timeout_s,
    )


def _models_of(args: argparse.Namespace, config: transport.EndpointConfig) -> tuple[str, ...]:
    """The models a run asks: the named ones, checked against what the endpoint serves, else all it serves."""
    try:
        served = transport.served_models(config)
    except transport.TransportError as exc:
        raise CliError(str(exc)) from exc
    if not args.models:
        return tuple(served)
    unknown = [name for name in args.models if name not in served]
    if unknown:
        raise CliError(
            f"the endpoint does not serve {', '.join(unknown)}; it serves {', '.join(served) or '(nothing)'}"
        )
    return tuple(args.models)


def _selection(args: argparse.Namespace, models: Sequence[str]) -> runner.Selection:
    return runner.Selection(
        models=tuple(models),
        families=tuple(args.families) if args.families else None,
        case_ids=tuple(args.cases) if args.cases else None,
    )


def _out_dir(args: argparse.Namespace, now: datetime) -> Path:
    """Where the run writes: ``--out``, else a fresh folder in the local layer of the project."""
    if args.out:
        return Path(args.out)
    root, notice = resolve_project_root(None)
    if notice:
        raise CliError(f"{notice}\nOr pass --out DIR to say where the run writes.")
    return local_root(root) / settings.load().cli.out_subdir / now.strftime("%Y%m%dT%H%M%SZ")


def _plan_text(plan: runner.Plan, item_set: cases.ItemSet) -> str:
    """The plan as it is printed: what is asked, against which yardstick, at what cost."""
    return "\n".join(
        [
            f"item set     {item_set.version}  cases_sha {item_set.cases_sha}  envelope_sha {item_set.envelope_sha}",
            f"models       {', '.join(plan.models)}",
            f"items        {len(plan.pairs)} (case, family) pairs x {len(plan.models)} models = {plan.calls} calls",
            f"estimate     ~{plan.estimated_minutes:.0f} min wall-clock, "
            f"~{plan.estimated_input_tokens:,} input tokens, ~{plan.estimated_output_tokens:,} output tokens",
        ]
    )


def cmd_gate(args: argparse.Namespace, environ: Mapping[str, str]) -> int:
    """Run the gold-sanity gate over the item set and report each case."""
    del environ  # the gate needs the sandbox, not the endpoint
    item_set = _load_items(Path(args.items), cases.Envelope())
    sandbox.ensure_available()
    report = oracle.run_gate(
        item_set,
        oracle.sandbox_runner(),
        case_ids=args.cases or None,
        families=args.families or None,
    )
    for outcome in report.outcomes:
        mark = "ok     " if outcome.usable else "REFUSED"
        print(f"{mark} {outcome.case_id}: {outcome.reason}")
    print(f"\n{len(report.usable_case_ids)} of {len(report.outcomes)} case(s) usable")
    return 0 if report.ok else 1


def cmd_plan(args: argparse.Namespace, environ: Mapping[str, str]) -> int:
    """Print what a run would ask and what it would cost - nothing is sent."""
    if args.models:
        config = None
        models: Sequence[str] = args.models
    else:
        config = _endpoint_config(args, environ)
        models = _models_of(args, config)
    item_set = _load_items(Path(args.items), _envelope_of(config))
    print(_plan_text(runner.build_plan(item_set, _selection(args, models)), item_set))
    return 0


def _print_report(report: runner.RunReport) -> None:
    print(f"\nledger      {report.ledger}")
    for row in report.rows:
        metrics = row["metrics"]
        print(
            f"{row['model']:<24} {row['stage']:<14} "
            f"scored {metrics['scored']}/{metrics['n']}  "
            f"pass_rate {metrics['pass_rate']}  "
            f"deferred {metrics['deferred']}  "
            f"malformed {metrics['malformed']}  "
            f"tokens {metrics['median_input_tokens']}+{metrics['median_output_tokens']}  "
            f"latency {metrics['median_latency_s']}s  "
            f"sufficient {row['sufficient']}"
        )
    for band in report.item_bands:
        print(
            f"{settings.load().item_band.name}  {band.case_id}/{band.family}: {band.status} "
            f"(pass rate {band.pass_rate}, scored {band.scored})"
        )


def cmd_probe(args: argparse.Namespace, environ: Mapping[str, str]) -> int:
    """Run the probe: ask, grade, and write the ledger as the run goes."""
    config = _endpoint_config(args, environ)
    item_set = _load_items(Path(args.items), _envelope_of(config))
    models = _models_of(args, config)
    selection = _selection(args, models)
    print(_plan_text(runner.build_plan(item_set, selection), item_set))
    if args.token_budget is not None:
        print(f"budget       {args.token_budget:,} tokens per model")
    if not args.yes:
        print("\nnothing was sent: pass --yes to run the plan above")
        return 2
    out_dir = _out_dir(args, datetime.now(UTC))
    print(f"writing      {out_dir}")
    options = runner.RunOptions(out_dir=out_dir, token_budget=args.token_budget)
    try:
        report = runner.run_probe(item_set, transport.EndpointChannel(config), selection, options)
    except KeyboardInterrupt:
        print(f"\ninterrupted: what was finished is kept in {out_dir}", file=sys.stderr)
        return 130
    _print_report(report)
    return 0


def _positive(text: str) -> int:
    value = int(text)
    if value < 1:
        raise argparse.ArgumentTypeError(f"must be a positive integer, got {text}")
    return value


def build_parser() -> argparse.ArgumentParser:
    """The command line: ``gate``, ``plan`` and ``probe``."""
    parser = argparse.ArgumentParser(
        prog="model_profile",
        description="Measure an endpoint's models on the probe suite and write the ledger.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def add_selection(target: argparse.ArgumentParser) -> None:
        target.add_argument(
            "--items", default=str(default_item_set()), help="the item set (default: the shipped seed set)"
        )
        target.add_argument("--families", nargs="*", default=None, help="the families to ask (default: all)")
        target.add_argument("--cases", nargs="*", default=None, help="the case ids to ask (default: all)")

    default_token_env = settings.load().cli.default_token_env

    def add_endpoint(target: argparse.ArgumentParser) -> None:
        target.add_argument("--endpoint", help="base URL of an OpenAI-compatible endpoint")
        target.add_argument(
            "--token-env",
            default=default_token_env,
            help=f"name of the environment variable that holds the bearer token (default: {default_token_env})",
        )
        target.add_argument(
            "--models", nargs="*", default=None, help="the model ids to ask (default: all the endpoint serves)"
        )

    gate = sub.add_parser("gate", help="run the gold-sanity gate over the item set (needs docker)")
    add_selection(gate)
    gate.set_defaults(func=cmd_gate)

    plan = sub.add_parser("plan", help="print what a run would ask and cost")
    add_selection(plan)
    add_endpoint(plan)
    plan.set_defaults(func=cmd_plan)

    probe = sub.add_parser("probe", help="run the probe and write the ledger")
    add_selection(probe)
    add_endpoint(probe)
    probe.add_argument("--out", help="directory to write the run into (default: the project's local layer)")
    probe.add_argument("--yes", action="store_true", help="spend the calls the plan names")
    probe.add_argument(
        "--token-budget",
        type=_positive,
        default=None,
        metavar="N",
        help="stop calling a model once it has spent N tokens; its remaining attempts are deferred as 'budget'",
    )
    probe.set_defaults(func=cmd_probe)
    return parser


def main(argv: Sequence[str] | None = None, environ: Mapping[str, str] | None = None) -> int:
    """Run one command; the environment is read here, once, and passed down."""
    args = build_parser().parse_args(argv)
    try:
        return args.func(args, os.environ if environ is None else environ)
    except (
        CliError,
        runner.RunnerError,
        oracle.GateRefusalError,
        sandbox.SandboxError,
        sandbox.SandboxUnavailableError,
    ) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
